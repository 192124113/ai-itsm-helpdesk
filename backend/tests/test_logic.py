"""Unit tests for the pure AI logic (classifier, catalogue, RAG). No database needed."""
import pytest

from app.catalog import detect_automation, find_software
from app.classifier import classify
from app.rag import RAGEngine


@pytest.fixture(scope="module")
def rag():
    return RAGEngine().build(persist=False)


# --- Intelligent ticket intake: the exact table from the assessment --------------------
def test_vpn_ticket_matches_expected_output():
    c = classify("I cannot connect to VPN since this morning. Authentication keeps failing.")
    assert c["intent_label"] == "Incident"
    assert (c["category"], c["subcategory"]) == ("Network", "VPN")
    assert c["priority"] == "P2"
    assert (c["impact"], c["urgency"]) == ("Individual", "High")
    assert c["assignment_group"] == "Network Support"
    assert c["summary"] == "VPN authentication failure"
    assert c["suggested_resolution"] == "VPN troubleshooting"


@pytest.mark.parametrize(
    "text,intent",
    [
        ("My VPN is not connecting.", "incident"),
        ("My password has expired.", "automatable"),
        ("My account is locked", "automatable"),
        ("How do I troubleshoot Outlook synchronization?", "knowledge_question"),
        ("I need Visual Studio Code.", "service_request"),
        ("I need Visual Studio Code installed on my laptop.", "service_request"),
        ("hello", "smalltalk"),
    ],
)
def test_intent_routing(text, intent):
    assert classify(text)["intent"] == intent


def test_outage_is_p1():
    c = classify("The VPN is down for everyone in the office")
    assert c["priority"] == "P1"


def test_software_catalogue_lookup():
    assert find_software("I need VS Code please")["name"] == "Visual Studio Code"
    assert find_software("install Photoshop") is None
    assert find_software("I want github") is None  # 'git' must not match inside 'github'


def test_automation_whitelist_detection():
    assert detect_automation("my password has expired") == "password_reset"
    assert detect_automation("I'm locked out") == "account_unlock"
    assert detect_automation("My VPN is not connecting") is None  # incident, not automatable


# --- RAG ------------------------------------------------------------------------------
def test_rag_answers_outlook_question_with_sources(rag):
    res = rag.answer("How do I troubleshoot Outlook synchronization?")
    assert res["answered"]
    assert "Outlook Synchronization Problems" in [s["title"] for s in res["sources"]]
    assert res["confidence"] >= 0.6


def test_rag_refuses_unknown_questions(rag):
    for q in ("What is the capital of France?", "Who won the cricket match?", "How do I request a vacation day?"):
        res = rag.answer(q)
        assert not res["answered"], q
        assert res["sources"] == []


def test_kb_has_5_to_10_documents(rag):
    assert 5 <= len(rag.docs) <= 10
    assert len(rag.chunks) > len(rag.docs)
