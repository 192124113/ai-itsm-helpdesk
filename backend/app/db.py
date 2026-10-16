"""MongoDB access.

Uses MongoDB Atlas when MONGODB_URI is set and reachable. Otherwise it falls back to an
in-memory `mongomock` database with the same API, so the prototype runs with zero setup
(data is lost on restart in that mode - /api/health reports which mode is active).

Collections: tickets, users, knowledge, chat_history, automation_actions,
software_requests, audit_logs (+ sn_incidents / sn_requests for the mock ServiceNow).
"""
import logging
import uuid
from datetime import datetime, timezone

from .config import settings

log = logging.getLogger(__name__)

_db = None
DB_MODE = "uninitialised"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_db():
    global _db, DB_MODE
    if _db is not None:
        return _db

    if settings.MONGODB_URI and not settings.USE_MOCK_DB:
        try:
            from pymongo import MongoClient

            kwargs = {"serverSelectionTimeoutMS": 5000}
            if settings.MONGODB_URI.startswith("mongodb+srv"):
                import certifi

                kwargs["tlsCAFile"] = certifi.where()
            client = MongoClient(settings.MONGODB_URI, **kwargs)
            client.admin.command("ping")
            _db = client[settings.MONGODB_DB]
            DB_MODE = "mongodb-atlas"
            log.info("Connected to MongoDB (%s)", settings.MONGODB_DB)
            return _db
        except Exception as exc:  # noqa: BLE001
            log.warning("MongoDB unreachable (%s); falling back to in-memory DB", exc)

    import mongomock

    _db = mongomock.MongoClient()[settings.MONGODB_DB]
    DB_MODE = "in-memory (mongomock)"
    return _db


def reset_db() -> None:
    """Drop the cached handle (tests). In-memory DBs start empty again."""
    global _db, DB_MODE
    _db = None
    DB_MODE = "uninitialised"


def next_seq(name: str) -> int:
    """Atomic counter used for INC / REQ numbers."""
    from pymongo import ReturnDocument

    doc = get_db().counters.find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc["seq"])


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def audit(event: str, actor: str, details: dict | None = None, ref: str | None = None) -> None:
    """Append-only audit trail. Every automated action must call this."""
    get_db().audit_logs.insert_one(
        {
            "id": new_id(),
            "ts": now_iso(),
            "event": event,
            "actor": actor,
            "ref": ref,
            "details": details or {},
        }
    )


DEMO_USERS = [
    {
        "user_id": "demo.user",
        "name": "Demo User",
        "email": "demo.user@example.com",
        "department": "Engineering",
        "password_expired": True,
        "locked": False,
        "vpn_enabled": True,
    },
    {
        "user_id": "priya.sharma",
        "name": "Priya Sharma",
        "email": "priya.sharma@example.com",
        "department": "Finance",
        "password_expired": False,
        "locked": True,
        "vpn_enabled": True,
    },
    {
        "user_id": "john.doe",
        "name": "John Doe",
        "email": "john.doe@example.com",
        "department": "Sales",
        "password_expired": False,
        "locked": False,
        "vpn_enabled": True,
    },
]


def seed_users(reset: bool = False) -> None:
    """Create demo employees. reset=True restores their 'broken' state for re-demoing."""
    users = get_db().users
    for u in DEMO_USERS:
        if reset:
            users.replace_one({"user_id": u["user_id"]}, dict(u), upsert=True)
        elif users.count_documents({"user_id": u["user_id"]}) == 0:
            users.insert_one(dict(u))
