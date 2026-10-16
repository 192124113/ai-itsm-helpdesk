"""End-to-end tests of the five mandatory demo scenarios through the HTTP API."""
import time

USER = "demo.user"


def chat(client, message):
    r = client.post("/api/chat", json={"user_id": USER, "message": message})
    assert r.status_code == 200, r.text
    return r.json()


def test_health(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok"
    assert h["knowledge_documents"] >= 5


def test_1_intelligent_ticket_intake(client):
    res = chat(client, "I cannot connect to VPN since this morning. Authentication keeps failing.")
    a = res["analysis"]
    assert a["intent_label"] == "Incident"
    assert (a["category"], a["subcategory"], a["priority"]) == ("Network", "VPN", "P2")
    assert (a["impact"], a["urgency"], a["assignment_group"]) == ("Individual", "High", "Network Support")
    assert a["summary"] == "VPN authentication failure"
    assert a["sources"], "RAG sources should be attached"

    number = res["ticket"]["number"]
    assert number.startswith("INC")
    sn = client.get(f"/api/tickets/{number}").json()["servicenow"]  # Get Incident
    assert sn["short_description"] == "VPN authentication failure"
    assert sn["assignment_group"] == "Network Support"
    assert sn["category"] == "Network" and sn["subcategory"] == "VPN"

    upd = client.patch(f"/api/tickets/{number}", json={"work_notes": "Engineer picked up", "state": "2"})
    assert upd.status_code == 200 and upd.json()["state_label"] == "In Progress"  # Update Incident


def test_2_self_healing_password_reset(client):
    res = chat(client, "My password has expired.")
    names = [s["step"] for s in res["steps"]]
    assert names == ["Identify", "Diagnose", "Knowledge Search", "Determine Automation",
                     "Execute", "Validate", "Update ServiceNow"]
    assert all(s["status"] == "done" for s in res["steps"])
    assert res["analysis"]["automation"]["validated"] is True
    assert res["ticket"]["state"] == "Resolved"

    # the mock directory really changed, and everything was audited
    users = {u["user_id"]: u for u in client.get("/api/users").json()}
    assert users[USER]["password_expired"] is False
    events = {e["event"] for e in client.get("/api/audit").json()}
    assert {"selfheal.executed", "selfheal.validated", "servicenow.updated"} <= events
    assert client.get("/api/automation/actions").json()[0]["status"] == "success"


def test_3_rag_with_sources(client):
    res = chat(client, "How do I troubleshoot Outlook synchronization?")
    a = res["analysis"]
    assert a["intent_label"] == "Knowledge Question"
    assert any("Outlook" in s["title"] for s in a["sources"])
    assert res["ticket"] is None and not res["escalation_suggested"]


def test_4_software_provisioning(client):
    res = chat(client, "I need Visual Studio Code.")
    sw = res["software_request"]
    assert sw["software"] == "Visual Studio Code"
    assert sw["request_id"].startswith("REQ")
    assert sw["status"] == "Provisioning"
    assert res["ticket"]["type"] == "request"

    time.sleep(1.3)  # mock provisioning API finishes after PROVISION_SECONDS=1
    reqs = client.get("/api/software/requests").json()
    assert next(r for r in reqs if r["request_id"] == sw["request_id"])["status"] == "Completed"
    assert client.get(f"/api/tickets/{sw['request_id']}").json()["servicenow"]["request_state"] == "closed_complete"


def test_5_unknown_question_no_hallucination_then_escalation(client):
    res = chat(client, "What is the capital of France?")
    assert res["analysis"]["sources"] == []
    assert res["escalation_suggested"] is True
    assert "won't guess" in res["reply"]
    assert res["ticket"] is None  # nothing is created until the user asks for a human

    esc = client.post("/api/tickets/escalate", json={
        "user_id": USER, "message": "What is the capital of France?", "chat_id": res["id"]})
    assert esc.status_code == 200
    assert esc.json()["ticket"]["number"].startswith("INC")
    tickets = client.get("/api/tickets").json()
    assert any(t["escalated"] for t in tickets)


def test_low_confidence_escalates_instead_of_guessing(client):
    res = chat(client, "purple banana window")
    assert res["analysis"]["confidence"] < res["analysis"]["threshold"]
    assert res["escalation_suggested"] is True and res["ticket"] is None


def test_dashboard_counts(client):
    d = client.get("/api/dashboard").json()
    assert d["tickets"]["total"] >= 4
    assert d["tickets"]["ai_resolved"] >= 1
    assert d["tickets"]["escalated"] >= 1
    assert d["software_requests"]["total"] >= 1
    assert d["automation"]["success"] >= 1
