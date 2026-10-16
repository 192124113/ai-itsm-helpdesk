"""FastAPI application. Interactive API docs: http://localhost:8000/docs"""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import db, llm, orchestrator, provisioning, store
from .catalog import AUTOMATIONS, SOFTWARE_CATALOGUE
from .config import settings
from .rag import get_rag
from .servicenow import get_servicenow

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.get_db()
    db.seed_users()
    get_rag()  # build the vector index once at start-up
    threading.Thread(target=llm.warmup, daemon=True).start()  # preload the LLM in the background
    yield


app = FastAPI(
    title="AI-Powered ITSM Helpdesk",
    description="Intelligent ticket intake, self-healing, RAG knowledge base, chatbot and software "
                "provisioning, integrated with ServiceNow.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"]
)


# ------------------------------------------------------------------ models
class ChatRequest(BaseModel):
    user_id: str = "demo.user"
    message: str = Field(min_length=2, max_length=2000)


class EscalateRequest(BaseModel):
    user_id: str = "demo.user"
    message: str = Field(min_length=2, max_length=2000)
    reason: str | None = None
    chat_id: str | None = None


class TicketUpdate(BaseModel):
    state: str | None = Field(None, description="ServiceNow state code: 1 New, 2 In Progress, 6 Resolved, 7 Closed")
    work_notes: str | None = None
    priority: str | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


# ------------------------------------------------------------------ health / users
@app.get("/api/health")
def health():
    rag = get_rag()
    return {
        "status": "ok",
        "database": db.DB_MODE,
        "servicenow": get_servicenow().mode,
        "llm": settings.HF_MODEL if settings.llm_available else "disabled (extractive fallback)",
        "embedder": rag.embedder.name,
        "vector_store": rag.store.backend,
        "knowledge_documents": len(rag.docs),
        "knowledge_chunks": len(rag.chunks),
        "confidence_threshold": settings.CONFIDENCE_THRESHOLD,
    }


@app.get("/api/users")
def users():
    return list(db.get_db().users.find({}, {"_id": 0}))


@app.post("/api/demo/reset")
def reset_demo():
    """Restore the demo employees to their 'broken' state (expired password, locked account)."""
    db.seed_users(reset=True)
    db.audit("demo.reset", "admin", {})
    return {"status": "reset"}


# ------------------------------------------------------------------ chat / analysis
@app.post("/api/chat")
def chat(req: ChatRequest):
    return orchestrator.handle_message(req.user_id, req.message)


@app.get("/api/chat/history")
def chat_history(user_id: str | None = None, limit: int = Query(50, le=200)):
    return list(reversed(store.list_chats(user_id, limit)))  # oldest first for the chat window


@app.get("/api/analyses")
def analyses(limit: int = Query(30, le=100)):
    return store.list_chats(None, limit)  # newest first


@app.post("/api/tickets/escalate")
def escalate(req: EscalateRequest):
    return orchestrator.escalate(req.user_id, req.message, req.reason, req.chat_id)


# ------------------------------------------------------------------ tickets / ServiceNow
@app.get("/api/tickets")
def tickets(ticket_type: str | None = None, limit: int = Query(100, le=500)):
    provisioning.refresh_statuses()
    return store.list_tickets(limit, ticket_type)


@app.get("/api/tickets/{number}")
def get_ticket(number: str):
    """Live read from ServiceNow (Get Incident / Get Request)."""
    sn = get_servicenow()
    rec = sn.get_incident(number) if number.startswith("INC") else sn.get_request(number)
    if not rec:
        raise HTTPException(404, f"{number} not found in ServiceNow")
    return {"servicenow": rec, "local": store.get_ticket(number)}


@app.patch("/api/tickets/{number}")
def update_ticket(number: str, body: TicketUpdate):
    """Update Incident in ServiceNow and keep the local mirror in sync."""
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(400, "Nothing to update")
    rec = get_servicenow().update_incident(number, fields)
    if not rec:
        raise HTTPException(404, f"{number} not found in ServiceNow")
    local = {"state_label": rec.get("state_label")}
    if fields.get("state") in {"6", "7"}:
        local["status"] = "Resolved"
    store.update_ticket(number, local)
    db.audit("servicenow.updated", "api", fields, ref=number)
    return rec


# ------------------------------------------------------------------ dashboard
@app.get("/api/dashboard")
def dashboard():
    provisioning.refresh_statuses()
    stats = store.get_stats()
    stats["automation_catalogue"] = [
        {"key": k, "label": v["label"], "safe": v["safe"]} for k, v in AUTOMATIONS.items()
    ]
    return stats


@app.get("/api/automation/actions")
def automation_actions(limit: int = Query(50, le=200)):
    return list(db.get_db().automation_actions.find({}, {"_id": 0}).sort("started_at", -1).limit(limit))


@app.get("/api/audit")
def audit_log(limit: int = Query(100, le=500)):
    return list(db.get_db().audit_logs.find({}, {"_id": 0}).sort("ts", -1).limit(limit))


# ------------------------------------------------------------------ software
@app.get("/api/software/catalogue")
def software_catalogue():
    return SOFTWARE_CATALOGUE


@app.get("/api/software/requests")
def software_requests():
    return provisioning.list_requests()


# ------------------------------------------------------------------ knowledge base
@app.get("/api/kb/articles")
def kb_articles(category: str | None = None, q: str | None = None):
    rag = get_rag()
    docs = [{"id": d["id"], "title": d["title"], "category": d["category"], "file": d["file"],
             "content": d["body"], "chunks": sum(1 for c in rag.chunks if c["doc_id"] == d["id"])}
            for d in rag.docs]
    if category:
        docs = [d for d in docs if d["category"].lower() == category.lower()]
    if q:
        ql = q.lower()
        docs = [d for d in docs if ql in d["title"].lower() or ql in d["content"].lower()]
    return docs


@app.get("/api/kb/search")
def kb_search(q: str = Query(min_length=2), k: int = Query(5, le=10), category: str | None = None):
    """Raw semantic search - returns ranked chunks with similarity scores."""
    return get_rag().search(q, k=k, category=category)


@app.post("/api/kb/ask")
def kb_ask(body: AskRequest):
    """Full RAG: retrieve -> LLM -> grounded answer + sources + confidence."""
    return get_rag().answer(body.question)