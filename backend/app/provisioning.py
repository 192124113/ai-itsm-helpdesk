"""Software provisioning automation.

Employee -> intent detection -> software catalogue -> ServiceNow request -> mock
provisioning API -> status update (Provisioning -> Completed).
"""
from datetime import datetime, timezone

from . import mock_apis, store
from .config import settings
from .db import audit, get_db, now_iso
from .servicenow import get_servicenow


def request_software(user_id: str, software: dict, text: str, cls: dict) -> dict:
    user = mock_apis.get_user(user_id) or {"user_id": user_id, "name": user_id}
    sn = get_servicenow()
    req = sn.create_request({
        "short_description": f"Software request: {software['name']}",
        "description": text,
        "requested_for": user_id,
        "special_instructions": f"Software: {software['name']} {software['version']} (catalogue {software['id']})",
        "priority": "4",
        "request_state": "in_process",
    })
    job = mock_apis.start_provisioning(software, user)
    doc = {
        "request_id": req["number"], "software": software["name"], "software_id": software["id"],
        "version": software["version"], "user_id": user_id, "status": "Provisioning",
        "job_id": job["job_id"], "target": job["target"], "created_at": now_iso(), "updated_at": now_iso(),
        "history": [{"status": "Requested", "at": now_iso()}, {"status": "Provisioning", "at": now_iso()}],
        "link": req.get("link"),
    }
    get_db().software_requests.insert_one(dict(doc))
    store.save_ticket({
        "number": req["number"], "type": "request", "short_description": f"Software request: {software['name']}",
        "category": "Software", "subcategory": "Installation", "priority": cls["priority"],
        "assignment_group": "Service Desk", "user_id": user_id, "intent": "service_request",
        "state_label": "Provisioning", "status": "Open", "confidence": cls["confidence"], "link": req.get("link"),
    })
    audit("provisioning.started", "ai-agent", {"software": software["name"], "job": job["job_id"],
                                                "api_call": job["api_call"]}, ref=req["number"])
    doc.pop("history", None)
    return doc


def refresh_statuses() -> int:
    """Advance provisioning jobs that have been running long enough (simulated deployment)."""
    db = get_db()
    done = 0
    for r in list(db.software_requests.find({"status": "Provisioning"})):
        started = datetime.fromisoformat(r["created_at"])
        age = (datetime.now(timezone.utc) - started).total_seconds()
        if age < settings.PROVISION_SECONDS:
            continue
        db.software_requests.update_one(
            {"request_id": r["request_id"]},
            {"$set": {"status": "Completed", "updated_at": now_iso()},
             "$push": {"history": {"status": "Completed", "at": now_iso()}}},
        )
        get_servicenow().update_request(r["request_id"], {
            "request_state": "closed_complete",
            "comments": f"{r['software']} installed on {r['target']} (job {r['job_id']}).",
        })
        store.update_ticket(r["request_id"], {"status": "Resolved", "state_label": "Completed"})
        audit("provisioning.completed", "provisioning-api", {"software": r["software"], "job": r["job_id"]},
              ref=r["request_id"])
        done += 1
    return done


def list_requests() -> list[dict]:
    refresh_statuses()
    docs = get_db().software_requests.find({}, {"_id": 0, "history": 0}).sort("created_at", -1)
    return list(docs)
