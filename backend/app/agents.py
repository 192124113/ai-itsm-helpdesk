"""Auto-resolution / self-heal agent.

Flow: Identify -> Diagnose -> Knowledge Search -> Determine Automation -> Execute ->
      Validate -> Update ServiceNow.   Every executed action is recorded in
`automation_actions` and in the append-only `audit_logs`.
"""
from . import mock_apis, store
from .catalog import AUTOMATIONS
from .db import audit, get_db, new_id, now_iso
from .servicenow import build_incident_fields, get_servicenow


def _ticket_view(rec: dict, ticket_type: str = "incident") -> dict:
    return {"number": rec["number"], "type": ticket_type, "state": rec.get("state_label"),
            "link": rec.get("link"), "sys_id": rec.get("sys_id")}


def run_self_heal(user_id: str, text: str, cls: dict, rag) -> dict:
    key = cls["automation_key"]
    meta = AUTOMATIONS[key]
    steps: list[dict] = []

    def add(name: str, status: str, detail: str) -> None:
        steps.append({"step": name, "status": status, "detail": detail, "at": now_iso()})

    # 1. Identify
    add("Identify", "done", f"Recognised as an automatable issue: {meta['label']} "
                            f"(confidence {int(cls['confidence'] * 100)}%).")
    audit("selfheal.identified", "ai-agent", {"automation": key, "text": text}, ref=user_id)

    # 2. Diagnose
    user = mock_apis.get_user(user_id)
    if not user:
        add("Diagnose", "failed", f"User '{user_id}' not found in the directory.")
        return {"steps": steps, "resolved": False, "ticket": None, "sources": [], "automation": {
            "key": key, "label": meta["label"], "status": "not_attempted", "validated": False},
            "reply": "I couldn't find your account in the directory, so I won't attempt an automated fix. "
                     "I can raise a ticket instead."}
    needed, finding = mock_apis.diagnose(key, user)
    add("Diagnose", "done", finding)

    # 3. Knowledge search
    hits = rag.search(meta["kb_query"], k=3)
    sources = rag.sources_from(hits[:2])
    add("Knowledge Search", "done",
        "Approved guidance found: " + (", ".join(s["title"] for s in sources) or "none") + ".")

    # 4. Determine automation (allow-list = the safety gate)
    if not meta["safe"] or not needed:
        add("Determine Automation", "done",
            "No automated action required." if not needed else "Action is not on the safe-automation list.")
        for name in ("Execute", "Validate", "Update ServiceNow"):
            add(name, "skipped", "Skipped.")
        return {"steps": steps, "resolved": False, "ticket": None, "sources": sources, "automation": {
            "key": key, "label": meta["label"], "status": "no_action", "validated": False},
            "reply": finding + " Nothing needed fixing automatically. If you still have a problem I can raise a ticket."}
    add("Determine Automation", "done",
        f"'{meta['label']}' is on the safe-automation allow-list for standard employee accounts - proceeding.")

    # 5. Execute
    result = mock_apis.execute(key, user_id)
    action = {
        "id": new_id(), "automation": key, "label": meta["label"], "user_id": user_id,
        "api_call": result["api_call"], "result": result["message"],
        "status": "success" if result["success"] else "failed",
        "started_at": now_iso(), "finished_at": now_iso(), "validated": False, "ticket_number": None,
    }
    get_db().automation_actions.insert_one(dict(action))
    audit("selfheal.executed", "ai-agent", {"automation": key, "api_call": result["api_call"],
                                            "success": result["success"], "message": result["message"]},
          ref=action["id"])
    add("Execute", "done" if result["success"] else "failed", f"{result['api_call']} -> {result['message']}")

    # 6. Validate (independent re-check)
    ok, vmsg = mock_apis.validate(key, user_id) if result["success"] else (False, "Execution failed.")
    add("Validate", "done" if ok else "failed", vmsg)
    audit("selfheal.validated", "ai-agent", {"automation": key, "ok": ok, "message": vmsg}, ref=action["id"])

    # 7. Update ServiceNow
    sn = get_servicenow()
    analysis = {**cls, "summary": f"{meta['label']} for {user['name']}", "category": meta["category"],
                "subcategory": meta["subcategory"], "assignment_group": meta["assignment_group"]}
    inc = sn.create_incident(build_incident_fields(analysis, text, user_id, extra_notes=f"Matched KB: {[s['title'] for s in sources]}"))
    if ok:
        inc = sn.update_incident(inc["number"], {
            "state": "6", "close_code": "Solved (Permanently)",
            "close_notes": f"Auto-resolved by AI Self-Heal Agent: {result['message']} Validation: {vmsg}",
            "work_notes": f"Automation '{key}' executed via {result['api_call']} and validated.",
        })
    else:
        inc = sn.update_incident(inc["number"], {
            "state": "2", "work_notes": f"Automation '{key}' did not validate ({vmsg}). Escalated to {meta['assignment_group']}."})
    add("Update ServiceNow", "done", f"{inc['number']} {'resolved' if ok else 'left open and escalated'}.")

    get_db().automation_actions.update_one({"id": action["id"]}, {"$set": {"validated": ok, "ticket_number": inc["number"]}})
    audit("servicenow.updated", "ai-agent", {"number": inc["number"], "resolved": ok}, ref=inc["number"])

    store.save_ticket({
        "number": inc["number"], "type": "incident", "short_description": analysis["summary"],
        "category": meta["category"], "subcategory": meta["subcategory"], "priority": cls["priority"],
        "assignment_group": meta["assignment_group"], "user_id": user_id, "intent": "automatable",
        "state_label": inc.get("state_label"), "status": "Resolved" if ok else "Open",
        "ai_resolved": ok, "escalated": not ok, "automation": True, "confidence": cls["confidence"],
        "link": inc.get("link"),
    })

    reply = (f"Done - {result['message']} I verified the fix ({vmsg}) and recorded it in ServiceNow as "
             f"**{inc['number']}** (Resolved)." if ok else
             f"I tried to fix this automatically but could not verify it ({vmsg}). I've raised "
             f"**{inc['number']}** and assigned it to {meta['assignment_group']}.")
    return {
        "steps": steps, "resolved": ok, "sources": sources, "reply": reply,
        "ticket": _ticket_view(inc),
        "automation": {"key": key, "label": meta["label"], "status": action["status"], "validated": ok,
                       "action_id": action["id"], "api_call": result["api_call"]},
    }
