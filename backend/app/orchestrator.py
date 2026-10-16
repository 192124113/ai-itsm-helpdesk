"""Request router: Employee request -> AI understanding -> knowledge retrieval -> decision ->
automation -> ServiceNow -> resolution.

Every message is classified, then routed to one workflow:
  knowledge_question -> RAG answer with sources
  incident           -> RAG troubleshooting steps + ServiceNow incident
  service_request    -> software catalogue + ServiceNow request + mock provisioning
  automatable        -> self-heal agent (diagnose, fix, validate, update ServiceNow)

Governance: below CONFIDENCE_THRESHOLD (or when the knowledge base has no answer) the AI does
not act or guess; it offers one-click escalation to a human via a ServiceNow incident.
"""
from . import agents, provisioning, store
from .catalog import find_software
from .classifier import classify
from .config import settings
from .db import audit
from .rag import get_rag
from .servicenow import build_incident_fields, get_servicenow


def _pct(x: float) -> int:
    return int(round(x * 100))


def _ticket_view(rec: dict, ticket_type: str, status: str = "Open") -> dict:
    return {"number": rec["number"], "type": ticket_type, "state": rec.get("state_label") or status,
            "link": rec.get("link"), "sys_id": rec.get("sys_id")}


def _base_analysis(cls: dict) -> dict:
    keep = ("intent", "intent_label", "category", "subcategory", "priority", "impact", "urgency",
            "assignment_group", "summary", "suggested_resolution", "confidence", "classification_method")
    a = {k: cls[k] for k in keep}
    a.update(sources=[], rag_confidence=None, automation=None, servicenow=None, escalated=False,
             workflow="", threshold=settings.CONFIDENCE_THRESHOLD)
    return a


def handle_message(user_id: str, message: str) -> dict:
    rag = get_rag()
    cls = classify(message)
    analysis = _base_analysis(cls)
    out = {"reply": "", "ticket": None, "steps": None, "software_request": None, "escalation_suggested": False}

    if cls["intent"] == "smalltalk":
        analysis["workflow"] = "Greeting"
        out["reply"] = ("Hi! I'm the IT helpdesk assistant. I can answer IT questions, log incidents, "
                        "fix common issues like expired passwords, and request software for you.")
    elif cls["confidence"] < settings.CONFIDENCE_THRESHOLD and cls["intent"] != "service_request":
        analysis["workflow"] = "Escalation (low confidence)"
        out["escalation_suggested"] = True
        out["reply"] = (f"I'm only {_pct(cls['confidence'])}% sure what you need "
                        f"(my threshold is {_pct(settings.CONFIDENCE_THRESHOLD)}%), so I won't guess. "
                        "I can create a ticket for a helpdesk engineer.")
    elif cls["intent"] == "knowledge_question":
        _knowledge(message, analysis, out, rag)
    elif cls["intent"] == "incident":
        _incident(user_id, message, cls, analysis, out, rag)
    elif cls["intent"] == "service_request":
        _software(user_id, message, cls, analysis, out)
    elif cls["intent"] == "automatable":
        _self_heal(user_id, message, cls, analysis, out, rag)

    audit("chat.handled", "ai-agent", {"intent": cls["intent"], "confidence": cls["confidence"],
                                       "workflow": analysis["workflow"]}, ref=user_id)
    chat = store.save_chat({"user_id": user_id, "message": message, "analysis": analysis, **out})
    return {"id": chat["id"], "created_at": chat["created_at"], "message": message, "analysis": analysis, **out}


# ----------------------------------------------------------------------------- workflows
def _knowledge(message, analysis, out, rag):
    res = rag.answer(message)
    analysis.update(workflow="RAG knowledge answer", sources=res["sources"], rag_confidence=res["confidence"],
                    confidence=res["confidence"], suggested_resolution="Knowledge base answer" if res["answered"] else "No approved content")
    if not res["answered"]:
        out["reply"] = res["answer"]
        out["escalation_suggested"] = True
        analysis["workflow"] = "Escalation (no approved knowledge)"
        return
    out["reply"] = res["answer"]
    if res["confidence"] < settings.CONFIDENCE_THRESHOLD:
        out["reply"] += (f"\n\n_My confidence is only {_pct(res['confidence'])}% - if this doesn't help, "
                         "I can raise a ticket._")
        out["escalation_suggested"] = True


def _incident(user_id, message, cls, analysis, out, rag):
    res = rag.answer(message)  # grounded troubleshooting from approved KB
    analysis.update(workflow="Intelligent ticket intake -> RAG -> ServiceNow incident",
                    sources=res["sources"], rag_confidence=res["confidence"] if res["answered"] else None)
    notes = "Suggested KB articles: " + (", ".join(s["title"] for s in res["sources"]) or "none found")
    inc = get_servicenow().create_incident(build_incident_fields(cls, message, user_id, notes))
    analysis["servicenow"] = {"number": inc["number"], "type": "incident", "state": inc.get("state_label"),
                              "link": inc.get("link")}
    store.save_ticket({
        "number": inc["number"], "type": "incident", "short_description": cls["summary"],
        "category": cls["category"], "subcategory": cls["subcategory"], "priority": cls["priority"],
        "assignment_group": cls["assignment_group"], "user_id": user_id, "intent": "incident",
        "state_label": inc.get("state_label"), "confidence": cls["confidence"], "link": inc.get("link"),
    })
    audit("servicenow.incident_created", "ai-agent", {"number": inc["number"], "priority": cls["priority"]},
          ref=inc["number"])
    out["ticket"] = _ticket_view(inc, "incident")
    reply = (f"I've logged incident **{inc['number']}** - {cls['summary']} "
             f"({cls['priority']}, assigned to {cls['assignment_group']}).")
    if res["answered"]:
        reply += "\n\nWhile you wait, try these approved steps:\n\n" + res["answer"]
    out["reply"] = reply


def _software(user_id, message, cls, analysis, out):
    software = find_software(message)
    analysis["workflow"] = "Software provisioning"
    if not software:
        analysis["suggested_resolution"] = "Not in software catalogue"
        out["escalation_suggested"] = True
        out["reply"] = ("That software isn't in the approved catalogue (Visual Studio Code, Chrome, Slack, "
                        "Zoom, Teams, Python, Git, Postman, Docker Desktop, 7-Zip). I can raise a ticket so it "
                        "can be reviewed.")
        return
    req = provisioning.request_software(user_id, software, message, cls)
    analysis["servicenow"] = {"number": req["request_id"], "type": "request", "state": "Provisioning",
                              "link": req.get("link")}
    out["software_request"] = req
    out["ticket"] = {"number": req["request_id"], "type": "request", "state": "Provisioning", "link": req.get("link")}
    out["reply"] = (f"ServiceNow request **{req['request_id']}** created for **{software['name']}**. "
                    f"Status: **Provisioning** - it will be installed on your laptop shortly.")


def _self_heal(user_id, message, cls, analysis, out, rag):
    res = agents.run_self_heal(user_id, message, cls, rag)
    analysis.update(workflow="Self-heal agent", sources=res["sources"], automation=res["automation"],
                    escalated=res["ticket"] is not None and not res["resolved"])
    if res["ticket"]:
        analysis["servicenow"] = {"number": res["ticket"]["number"], "type": "incident",
                                  "state": res["ticket"]["state"], "link": res["ticket"].get("link")}
    out.update(reply=res["reply"], steps=res["steps"], ticket=res["ticket"],
               escalation_suggested=res["ticket"] is None)


# ----------------------------------------------------------------------------- escalation
def escalate(user_id: str, message: str, reason: str | None = None, chat_id: str | None = None) -> dict:
    """Human escalation: open an incident for a helpdesk engineer (one click from the UI)."""
    cls = classify(message)
    prio = cls["priority"] if cls["intent"] == "incident" else "P3"
    impact = cls["impact"] if cls["intent"] == "incident" else "Individual"
    urgency = cls["urgency"] if cls["intent"] == "incident" else "Medium"
    summary = cls["summary"] if cls["intent"] == "incident" else "Helpdesk assistance needed: " + message.strip()[:70]
    analysis = {**cls, "summary": summary, "priority": prio, "impact": impact, "urgency": urgency,
                "assignment_group": cls["assignment_group"] if cls["category"] != "General" else "Service Desk"}
    reason = reason or "AI could not resolve the request with approved knowledge"
    inc = get_servicenow().create_incident(
        build_incident_fields(analysis, message, user_id, f"ESCALATED BY AI: {reason}"))
    ticket = store.save_ticket({
        "number": inc["number"], "type": "incident", "short_description": summary,
        "category": analysis["category"], "subcategory": analysis["subcategory"], "priority": prio,
        "assignment_group": analysis["assignment_group"], "user_id": user_id, "intent": "escalation",
        "state_label": inc.get("state_label"), "escalated": True, "confidence": cls["confidence"],
        "link": inc.get("link"),
    })
    audit("ticket.escalated", "ai-agent", {"number": inc["number"], "reason": reason}, ref=inc["number"])
    view = _ticket_view(inc, "incident")
    if chat_id:
        store.update_chat(chat_id, {"ticket": view, "escalation_suggested": False,
                                    "analysis.servicenow": {"number": inc["number"], "type": "incident",
                                                            "state": inc.get("state_label"), "link": inc.get("link")},
                                    "analysis.escalated": True})
    return {"ticket": view, "priority": prio, "assignment_group": analysis["assignment_group"],
            "reply": f"I've escalated this to a human: incident **{inc['number']}** "
                     f"({prio}, {analysis['assignment_group']})."}
