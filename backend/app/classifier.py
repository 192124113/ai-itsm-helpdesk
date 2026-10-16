"""Intelligent ticket intake: turn free text into structured ITSM fields.

Approach: transparent rules first (fast, deterministic, explainable in a demo), then an
optional LLM pass (Hugging Face) only when the rules are unsure. The output always carries a
confidence score that the orchestrator compares against CONFIDENCE_THRESHOLD.
"""
import json
import re

from . import llm
from .catalog import detect_automation, find_software, AUTOMATIONS

INTENT_LABELS = {
    "incident": "Incident",
    "knowledge_question": "Knowledge Question",
    "service_request": "Service Request",
    "automatable": "Automatable Issue",
    "smalltalk": "Greeting",
    "unknown": "Unknown",
}

# (pattern, category, subcategory, assignment group, suggested resolution)
CATEGORY_RULES = [
    (r"\bvpn\b", "Network", "VPN", "Network Support", "VPN troubleshooting"),
    (r"wi-?fi|wireless|internet|network", "Network", "Wi-Fi", "Network Support", "Wi-Fi troubleshooting"),
    (r"outlook|e-?mail|mailbox|calendar", "Email", "Outlook", "Messaging Support", "Outlook troubleshooting"),
    (r"password|account|locked|log ?in|sign.?in|\bmfa\b|authenticator",
     "Access", "Password / Account", "Identity & Access", "Password and account recovery"),
    (r"laptop|slow|performance|freez|battery|fan\b|blue screen",
     "Hardware", "Laptop", "Desktop Support", "Laptop performance troubleshooting"),
    (r"install|software|licen[cs]e", "Software", "Installation", "Service Desk", "Software installation guidance"),
    (r"application|\bapp\b|portal|\bsap\b|access to", "Application", "Access", "Application Support",
     "Application access review"),
]

_QUESTION_START = re.compile(
    r"^\s*(how|what|where|why|which|who|when|is there|are there|does|do i|do we|can someone explain)\b", re.I
)
_PROBLEM = re.compile(
    r"cannot|can't|can not|unable|not (working|connecting|loading|responding|syncing|opening)|fail|error|"
    r"broken|crash|\bdown\b|slow|issue|problem|stuck|keeps|won't|doesn't|isn't|since (this )?(morning|yesterday)",
    re.I,
)
_FIRST_PERSON = re.compile(r"\bmy\b|\bi('m| am)\b|\bi (cannot|can't|am)\b", re.I)
_INSTALL_VERB = re.compile(r"\b(install|installed|installation|need|want|request|get|download|set ?up|add|provision)\b", re.I)
_BLOCKING = re.compile(r"cannot|can't|can not|unable|not connecting|failing|fails|failed|locked|keeps failing|won't", re.I)
_OUTAGE = re.compile(r"all users|everyone|entire|company-?wide|outage|production (is )?down|whole (office|company)", re.I)
_TEAM = re.compile(r"\bteam\b|department|several (users|people|colleagues)|multiple (users|people)|whole floor", re.I)
_GREETING = re.compile(r"^\s*(hi|hello|hey|good (morning|afternoon|evening)|thanks|thank you)\b[\s!.?]*$", re.I)


def _category(text: str):
    t = text.lower()
    for pattern, cat, sub, group, resolution in CATEGORY_RULES:
        if re.search(pattern, t):
            return cat, sub, group, resolution
    return "General", "Other", "Service Desk", "Service desk triage"


def _summary(text: str, sub: str) -> str:
    t = text.lower()
    if sub == "Outlook" and re.search(r"sync", t):
        return "Outlook synchronization failure"
    if re.search(r"authenticat|credential|log ?in|sign.?in", t):
        return f"{sub} authentication failure"
    if re.search(r"not connect|cannot connect|can't connect|unable to connect|disconnect", t):
        return f"{sub} connectivity failure"
    if "slow" in t:
        return f"{sub} slowness"
    return f"{sub} issue"


def _priority(text: str, cat: str, sub: str):
    """Return (priority, impact, urgency)."""
    if _OUTAGE.search(text):
        return "P1", "Enterprise", "High"
    if _TEAM.search(text) and _PROBLEM.search(text):
        return "P2", "Department", "High"
    critical = (cat, sub) in {("Network", "VPN"), ("Email", "Outlook"), ("Access", "Password / Account")}
    if _BLOCKING.search(text) and critical:
        return "P2", "Individual", "High"
    return "P3", "Individual", "Medium"


def classify(text: str) -> dict:
    cat, sub, group, resolution = _category(text)
    intent, conf = "unknown", 0.4
    method = "rules"

    automation = detect_automation(text)
    software = find_software(text)

    if _GREETING.match(text):
        intent, conf = "smalltalk", 0.99
    elif _QUESTION_START.match(text) and not (_FIRST_PERSON.search(text) and _PROBLEM.search(text)):
        intent, conf = "knowledge_question", 0.85
    elif automation:
        intent, conf = "automatable", 0.92
    elif software and _INSTALL_VERB.search(text):
        intent, conf = "service_request", 0.93
    elif re.search(r"\binstall", text, re.I):
        intent, conf = "service_request", 0.65
    elif _PROBLEM.search(text):
        intent, conf = "incident", 0.9 if cat != "General" else 0.7
    else:
        # Rules are unsure -> ask the LLM (if configured).
        refined = _llm_intent(text)
        if refined:
            intent, conf, method = refined, 0.7, "rules+llm"

    if intent == "automatable" and automation:
        meta = AUTOMATIONS[automation]
        cat, sub, group = meta["category"], meta["subcategory"], meta["assignment_group"]
        resolution = f"Automated: {meta['label']}"

    if intent == "incident":
        priority, impact, urgency = _priority(text, cat, sub)
    elif intent in ("service_request", "automatable"):
        priority, impact, urgency = ("P4", "Individual", "Low") if intent == "service_request" else ("P3", "Individual", "Medium")
    else:
        priority, impact, urgency = "P4", "Individual", "Low"

    if intent == "service_request":
        cat, sub, group, resolution = "Software", "Installation", "Service Desk", "Software provisioning"
        summary = f"Software request: {software['name']}" if software else "Software request (not in catalogue)"
    elif intent == "automatable" and automation:
        summary = AUTOMATIONS[automation]["label"] + " request"
    elif intent == "knowledge_question":
        summary = "Knowledge question: " + text.strip().rstrip("?")[:70]
    else:
        summary = _summary(text, sub)

    return {
        "intent": intent,
        "intent_label": INTENT_LABELS[intent],
        "category": cat,
        "subcategory": sub,
        "priority": priority,
        "impact": impact,
        "urgency": urgency,
        "assignment_group": group,
        "summary": summary,
        "suggested_resolution": resolution,
        "confidence": round(conf, 2),
        "classification_method": method,
        "automation_key": automation if intent == "automatable" else None,
        "software": software["name"] if software and intent == "service_request" else None,
    }


def _llm_intent(text: str):
    out = llm.generate(
        "Classify the IT helpdesk message. Reply with JSON only: "
        '{"intent": "incident|knowledge_question|service_request|unknown"}',
        text,
        max_tokens=40,
    )
    if not out:
        return None
    try:
        intent = json.loads(re.search(r"\{.*\}", out, re.S).group(0)).get("intent")
    except Exception:  # noqa: BLE001
        return None
    return intent if intent in {"incident", "knowledge_question", "service_request"} else None
