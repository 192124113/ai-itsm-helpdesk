"""Persistence helpers for the local MongoDB collections (ticket mirror, chat history, stats)."""
from .db import get_db, new_id, now_iso


def _clean(docs):
    return [{k: v for k, v in d.items() if k != "_id"} for d in docs]


# ------------------------------------------------------------------ tickets
def save_ticket(doc: dict) -> dict:
    doc = {"created_at": now_iso(), "updated_at": now_iso(), "status": "Open",
           "ai_resolved": False, "escalated": False, "automation": False, **doc}
    get_db().tickets.insert_one(dict(doc))
    return doc


def update_ticket(number: str, fields: dict) -> None:
    get_db().tickets.update_one({"number": number}, {"$set": {**fields, "updated_at": now_iso()}})


def get_ticket(number: str):
    d = get_db().tickets.find_one({"number": number}, {"_id": 0})
    return d


def list_tickets(limit: int = 100, ticket_type: str | None = None) -> list[dict]:
    q = {"type": ticket_type} if ticket_type else {}
    return _clean(get_db().tickets.find(q, {"_id": 0}).sort("created_at", -1).limit(limit))


# ------------------------------------------------------------------ chat
def save_chat(doc: dict) -> dict:
    doc = {"id": new_id(), "created_at": now_iso(), **doc}
    get_db().chat_history.insert_one(dict(doc))
    return doc


def update_chat(chat_id: str, fields: dict) -> None:
    get_db().chat_history.update_one({"id": chat_id}, {"$set": fields})


def list_chats(user_id: str | None = None, limit: int = 50) -> list[dict]:
    q = {"user_id": user_id} if user_id else {}
    return _clean(get_db().chat_history.find(q, {"_id": 0}).sort("created_at", -1).limit(limit))


# ------------------------------------------------------------------ stats
def get_stats() -> dict:
    db = get_db()
    tickets = _clean(db.tickets.find({}, {"_id": 0}))
    sw = _clean(db.software_requests.find({}, {"_id": 0}))
    actions = _clean(db.automation_actions.find({}, {"_id": 0}))
    chats = _clean(db.chat_history.find({}, {"_id": 0}))

    by_intent: dict[str, int] = {}
    for c in chats:
        label = (c.get("analysis") or {}).get("intent_label", "Unknown")
        by_intent[label] = by_intent.get(label, 0) + 1

    sw_by_status: dict[str, int] = {}
    for r in sw:
        sw_by_status[r["status"]] = sw_by_status.get(r["status"], 0) + 1

    ok = sum(1 for a in actions if a.get("status") == "success")
    return {
        "tickets": {
            "total": len(tickets),
            "open": sum(1 for t in tickets if t["status"] == "Open"),
            "resolved": sum(1 for t in tickets if t["status"] == "Resolved"),
            "ai_resolved": sum(1 for t in tickets if t.get("ai_resolved")),
            "escalated": sum(1 for t in tickets if t.get("escalated")),
            "incidents": sum(1 for t in tickets if t["type"] == "incident"),
            "requests": sum(1 for t in tickets if t["type"] == "request"),
        },
        "software_requests": {"total": len(sw), "by_status": sw_by_status},
        "automation": {
            "total": len(actions),
            "success": ok,
            "failed": sum(1 for a in actions if a.get("status") == "failed"),
            "success_rate": round(ok / len(actions) * 100) if actions else None,
        },
        "conversations": {"total": len(chats), "by_intent": by_intent},
    }
