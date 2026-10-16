"""ServiceNow integration.

Two interchangeable clients with the same interface:

* MockServiceNow  - stores records in MongoDB (sn_incidents / sn_requests). Default.
* RealServiceNow  - calls the ServiceNow Table REST API (developer instance / PDI).

Select with SERVICENOW_MODE=mock|real. Real mode needs SERVICENOW_INSTANCE,
SERVICENOW_USER and SERVICENOW_PASSWORD (see README).
"""
import uuid

from .config import settings
from .db import get_db, next_seq, now_iso

INCIDENT_STATES = {"1": "New", "2": "In Progress", "3": "On Hold", "6": "Resolved", "7": "Closed"}

IMPACT_CODES = {"Enterprise": "1", "Department": "2", "Individual": "3"}
URGENCY_CODES = {"High": "1", "Medium": "2", "Low": "3"}


def build_incident_fields(analysis: dict, description: str, caller: str, extra_notes: str = "") -> dict:
    """Map the AI analysis onto ServiceNow incident fields."""
    notes = (
        f"[AI triage] intent={analysis.get('intent')} confidence={analysis.get('confidence')} "
        f"method={analysis.get('classification_method')}"
    )
    if extra_notes:
        notes += f"\n{extra_notes}"
    return {
        "short_description": analysis["summary"],
        "description": description,
        "category": analysis["category"],
        "subcategory": analysis["subcategory"],
        "impact": IMPACT_CODES.get(analysis["impact"], "3"),
        "urgency": URGENCY_CODES.get(analysis["urgency"], "2"),
        "priority": analysis["priority"].lstrip("Pp"),  # "P2" -> "2"
        "assignment_group": analysis["assignment_group"],
        "caller_id": caller,
        "contact_type": "AI Chatbot",
        "state": "1",
        "work_notes": notes,
    }


class MockServiceNow:
    mode = "mock"

    @property
    def _inc(self):
        return get_db().sn_incidents

    @property
    def _req(self):
        return get_db().sn_requests

    @staticmethod
    def _clean(rec: dict | None) -> dict | None:
        if rec is None:
            return None
        rec = {k: v for k, v in rec.items() if k != "_id"}
        rec["state_label"] = INCIDENT_STATES.get(str(rec.get("state")), rec.get("state"))
        return rec

    # ---- incidents ------------------------------------------------------
    def create_incident(self, fields: dict) -> dict:
        number = f"INC{10000 + next_seq('incident'):07d}"
        rec = {
            **fields,
            "number": number,
            "sys_id": uuid.uuid4().hex,
            "state": fields.get("state", "1"),
            "opened_at": now_iso(),
            "updated_at": now_iso(),
            "work_notes": [fields["work_notes"]] if fields.get("work_notes") else [],
            "link": f"mock://servicenow/incident/{number}",
        }
        self._inc.insert_one(dict(rec))
        return self._clean(rec)

    def get_incident(self, number: str) -> dict | None:
        return self._clean(self._inc.find_one({"number": number}))

    def update_incident(self, number: str, fields: dict) -> dict | None:
        rec = self._inc.find_one({"number": number})
        if not rec:
            return None
        fields = dict(fields)
        notes = list(rec.get("work_notes", []))
        if "work_notes" in fields:
            notes.append(fields.pop("work_notes"))
        self._inc.update_one(
            {"number": number},
            {"$set": {**fields, "work_notes": notes, "updated_at": now_iso()}},
        )
        return self.get_incident(number)

    # ---- service requests -------------------------------------------------
    def create_request(self, fields: dict) -> dict:
        number = f"REQ{1244 + next_seq('request'):06d}"  # first one is REQ001245
        rec = {
            **fields,
            "number": number,
            "sys_id": uuid.uuid4().hex,
            "request_state": fields.get("request_state", "requested"),
            "opened_at": now_iso(),
            "updated_at": now_iso(),
            "link": f"mock://servicenow/request/{number}",
        }
        self._req.insert_one(dict(rec))
        return self._clean(rec)

    def get_request(self, number: str) -> dict | None:
        return self._clean(self._req.find_one({"number": number}))

    def update_request(self, number: str, fields: dict) -> dict | None:
        if not self._req.find_one({"number": number}):
            return None
        self._req.update_one({"number": number}, {"$set": {**fields, "updated_at": now_iso()}})
        return self.get_request(number)


class RealServiceNow:
    """Thin wrapper over the ServiceNow Table API.

    Notes for a real instance:
      * assignment_group / caller_id accept a sys_id or a display value depending on
        instance configuration; resolve names to sys_ids via /table/sys_user_group if needed.
      * Catalog orders normally go through /api/sn_sc/servicecatalog/items/{id}/order_now;
        here we create an sc_request record directly, which is enough for a prototype.
    """

    mode = "real"

    def __init__(self) -> None:
        import requests

        self._s = requests.Session()
        self._s.auth = (settings.SERVICENOW_USER, settings.SERVICENOW_PASSWORD)
        self._s.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        self._base = f"{settings.SERVICENOW_INSTANCE}/api/now/table"

    def _call(self, method: str, table: str, path: str = "", **kw):
        resp = self._s.request(method, f"{self._base}/{table}{path}", timeout=20, **kw)
        resp.raise_for_status()
        return resp.json().get("result")

    def _decorate(self, rec, table):
        if isinstance(rec, dict):
            rec["state_label"] = INCIDENT_STATES.get(str(rec.get("state")), rec.get("state"))
            rec["link"] = f"{settings.SERVICENOW_INSTANCE}/nav_to.do?uri={table}.do?sys_id={rec.get('sys_id')}"
        return rec

    def create_incident(self, fields: dict) -> dict:
        return self._decorate(self._call("POST", "incident", json=fields), "incident")

    def get_incident(self, number: str):
        res = self._call("GET", "incident", params={"sysparm_query": f"number={number}", "sysparm_limit": 1})
        return self._decorate(res[0], "incident") if res else None

    def update_incident(self, number: str, fields: dict):
        current = self.get_incident(number)
        if not current:
            return None
        return self._decorate(self._call("PATCH", "incident", f"/{current['sys_id']}", json=fields), "incident")

    def create_request(self, fields: dict) -> dict:
        return self._decorate(self._call("POST", "sc_request", json=fields), "sc_request")

    def get_request(self, number: str):
        res = self._call("GET", "sc_request", params={"sysparm_query": f"number={number}", "sysparm_limit": 1})
        return self._decorate(res[0], "sc_request") if res else None

    def update_request(self, number: str, fields: dict):
        current = self.get_request(number)
        if not current:
            return None
        return self._decorate(self._call("PATCH", "sc_request", f"/{current['sys_id']}", json=fields), "sc_request")


_client = None


def get_servicenow():
    global _client
    if _client is None:
        if (
            settings.SERVICENOW_MODE == "real"
            and settings.SERVICENOW_INSTANCE
            and settings.SERVICENOW_USER
        ):
            _client = RealServiceNow()
        else:
            _client = MockServiceNow()
    return _client


def reset_servicenow() -> None:
    global _client
    _client = None
