# AI-Powered ITSM & Intelligent Helpdesk Automation Platform

A working prototype for the Sorim.AI technical hackathon. An employee describes an IT problem in plain English; the platform understands it, answers from an approved knowledge base (RAG), creates ServiceNow tickets, fixes common issues automatically, provisions software, keeps an audit trail, and **escalates to a human when it is unsure**.

```
Employee → AI understanding → Knowledge retrieval → Decision → Automation → ServiceNow → Resolution
```

## 1. Quick start (about 10 minutes)

Prerequisites: Python 3.10+, Node.js 18+. Nothing else is required: MongoDB, ServiceNow and the LLM all have working defaults.

**Backend**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env   (all optional, see §6)
uvicorn app.main:app --reload --port 8000
```
Interactive API docs: http://localhost:8000/docs · Health: http://localhost:8000/api/health

**Frontend** (second terminal)
```bash
cd frontend
npm install
npm run dev
```
Open http://localhost:5173.

**Tests**
```bash
cd backend
pytest -v
```

> First start with `EMBEDDING_BACKEND=auto` downloads the ~90 MB `all-MiniLM-L6-v2` model once. If it cannot be downloaded, the app automatically falls back to a TF-IDF embedder and says so in the sidebar and `/api/health`.

## 2. Architecture

```
┌──────────────────────┐   /api   ┌─────────────────────────────────────────────┐
│ React + TypeScript   │ ───────▶ │ FastAPI                                     │
│  • Self-Service chat │          │  orchestrator.py  (classify → route)        │
│  • ITSM Dashboard    │          │   ├─ classifier.py   intent/category/priority│
│  • AI Analysis       │          │   ├─ rag.py          chunk→embed→FAISS→LLM  │
│  • Knowledge Base    │          │   ├─ agents.py       self-heal agent        │
└──────────────────────┘          │   ├─ provisioning.py software requests      │
                                  │   └─ servicenow.py   mock | real REST client│
                                  └───────┬───────────────┬──────────────┬──────┘
                                          │               │              │
                                   MongoDB Atlas     FAISS index   Hugging Face
                                   (tickets, chat,   (in memory,   Inference API
                                   knowledge, audit, built at      (Qwen2.5-7B)
                                   automation, sw)   start-up)
```

| Layer | Choice | Why |
|---|---|---|
| Frontend | React 18 + TypeScript + Vite | Required stack; Vite proxies `/api` so no CORS setup locally |
| Backend | Python + FastAPI | Required; typed models and automatic OpenAPI docs at `/docs` |
| Database | MongoDB Atlas (via `pymongo`) | Required; flexible documents suit tickets, analysis and audit data. Falls back to in-memory `mongomock` when no URI is set |
| LLM | **Qwen/Qwen2.5-7B-Instruct** via the Hugging Face Inference API | Open weights (Apache-2.0), strong instruction following and grounded-answer behaviour for its size, free serverless tier, no GPU needed. Swap with `HF_MODEL` |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` | Open source, 384-dim, fast on CPU, good quality for short support text |
| Vector DB | **FAISS** (`IndexFlatIP` on normalised vectors = cosine) | Zero-service, exact search; ideal for a small KB. NumPy fallback if FAISS cannot be imported |
| ITSM | ServiceNow Table REST API, or the built-in mock | Same interface; switch with `SERVICENOW_MODE` |

## 3. How each required capability works

**① Intelligent Ticket Intake** (`classifier.py`, `orchestrator._incident`)
Transparent rules decide intent, category/sub-category, priority, impact/urgency, assignment group, summary and suggested resolution; an LLM pass is used only when the rules are unsure. For the VPN example it returns exactly: Incident · Network/VPN · P2 · Individual/High · Network Support · "VPN authentication failure" · "VPN troubleshooting". The fields are mapped onto ServiceNow (`category`, `subcategory`, `impact`, `urgency`, `priority`, `assignment_group`, `short_description`, `description`, `work_notes`) and the incident is created. RAG adds approved troubleshooting steps and lists the KB articles in the work notes.

**② Auto-Resolution / Self-Heal** (`agents.py`, `mock_apis.py`)
`Identify → Diagnose → Knowledge Search → Determine Automation → Execute → Validate → Update ServiceNow`. Only actions on an explicit **safe allow-list** (`catalog.AUTOMATIONS`: password reset, account unlock, clear cache, restart Outlook, VPN status check) can run unattended. The result is independently re-checked; if validation fails, the incident stays open and is escalated. Every step writes to `automation_actions` and the append-only `audit_logs`.

**③ Knowledge Management Automation** (`rag.py`, `knowledge_base/*.md`)
8 sample articles → section-aware chunking (≈600 characters, one-line overlap) → embeddings → FAISS → semantic search → LLM → grounded answer with sources and confidence. Metadata is stored in the `knowledge` collection. Without an LLM token the answer is extracted verbatim from the best chunks, so it still works offline.

**④ Self-Service Portal & Chatbot** (`frontend/`)
One input box. The AI classifies each message as Knowledge Question, Incident, Service Request or Automatable Issue and routes it. Responses show the intent, sources, confidence bar (with the escalation threshold marked) and a one-click **Create a ticket for a human** button when appropriate.

**⑤ Software Provisioning** (`provisioning.py`, `catalog.SOFTWARE_CATALOGUE`)
"I need Visual Studio Code" → catalogue match (10 approved titles) → ServiceNow request (`REQ001245`…) → mock provisioning API → status `Provisioning`, which flips to `Completed` after `PROVISION_SECONDS` and updates ServiceNow. Software not in the catalogue is not provisioned; the user is offered a ticket.

## 4. AI safety & governance

| Requirement | Implementation |
|---|---|
| No hallucination | The RAG engine refuses when the best chunk's similarity is below a threshold (or, for the TF-IDF fallback, when too many query words are not in the KB), and the LLM prompt must answer `INSUFFICIENT` if the context is not enough. The reply states that the information is unavailable. |
| Source attribution | Every RAG answer lists article ID, title and match score (chat, AI Analysis and Knowledge Base screens). |
| Confidence | Classification confidence and RAG confidence are shown as bars with the threshold marked. |
| Human escalation | `CONFIDENCE_THRESHOLD` (default 0.6). Below it, or when the KB has no answer, the AI takes no action and offers escalation; `POST /api/tickets/escalate` opens a ServiceNow incident for a human. |
| Audit trail | Every automated action, ServiceNow write and escalation is in `audit_logs` (visible on the Dashboard). |

## 5. API reference (also at `/docs`)

| Method & path | Purpose |
|---|---|
| `POST /api/chat` `{user_id, message}` | Main entry point. Returns reply, analysis, sources, steps, ticket |
| `POST /api/tickets/escalate` `{user_id, message, chat_id?}` | Human escalation → ServiceNow incident |
| `GET /api/tickets` · `GET /api/tickets/{number}` | Local mirror list · **live Get Incident/Request from ServiceNow** |
| `PATCH /api/tickets/{number}` `{state?, work_notes?}` | **Update Incident** in ServiceNow |
| `GET /api/dashboard` | Total/open/AI-resolved/escalated tickets, software requests, automation stats |
| `GET /api/analyses` · `GET /api/chat/history` | AI analysis records · chat history |
| `GET /api/automation/actions` · `GET /api/audit` | Automation log · audit trail |
| `GET /api/software/catalogue` · `GET /api/software/requests` | Catalogue · requests and provisioning status |
| `GET /api/kb/articles` · `GET /api/kb/search?q=` · `POST /api/kb/ask` | Articles · raw semantic search · full RAG answer |
| `GET /api/health` · `GET /api/users` · `POST /api/demo/reset` | Status · demo users · reset demo state |

## 6. Configuration

Copy `backend/.env.example` to `backend/.env`. **Never commit `.env`** (it is git-ignored).

**MongoDB Atlas (optional; recommended before the review)**
1. Create a free account at mongodb.com/atlas and an M0 (free) cluster.
2. Database Access → add a user and password. Network Access → add your IP (or `0.0.0.0/0` for the demo).
3. Connect → Drivers → copy the `mongodb+srv://…` string into `MONGODB_URI`.
Restart the backend; the sidebar shows `DB mongodb-atlas`. Without a URI the sidebar shows `in-memory (mongomock)` and data resets on restart.

**Hugging Face LLM (optional)**
Create a free Read token at huggingface.co/settings/tokens and set `HF_TOKEN`. The sidebar then shows the model name. Without it, answers are extracted from the KB.

**Real ServiceNow (optional)**
1. Get a free Personal Developer Instance at developer.servicenow.com.
2. Set `SERVICENOW_MODE=real`, `SERVICENOW_INSTANCE=https://devXXXXX.service-now.com`, `SERVICENOW_USER`, `SERVICENOW_PASSWORD`.
3. Restart. Incident create/get/update use `/api/now/table/incident`; requests use `/api/now/table/sc_request`.

*Production integration notes:* use OAuth 2.0 rather than basic auth; resolve `assignment_group` and `caller_id` to `sys_id`s (the Table API accepts display values only if configured); catalogue orders would normally go through `/api/sn_sc/servicecatalog/items/{id}/order_now` to create RITMs; impact/urgency are sent as ServiceNow codes (1 High … 3 Low), so a priority "P2" is carried in the `priority` field and the work notes (the instance's priority-calculation rules may recompute it).

## 7. Test scenarios (the five demo scenarios + extras)

| # | Input | Expected |
|---|---|---|
| 1 | "My VPN is not connecting." / "I cannot connect to VPN since this morning. Authentication keeps failing." | Incident, Network/VPN, P2, Individual/High, Network Support, ServiceNow `INC…`, KB sources |
| 2 | "My password has expired." | 7-step agent timeline, password reset, validated, incident auto-resolved, audit entries |
| 3 | "How do I troubleshoot Outlook synchronization?" | Grounded answer + source "Outlook Synchronization Problems" |
| 4 | "I need Visual Studio Code." | `REQ001245`, status Provisioning → Completed |
| 5 | "What is the capital of France?" | "I won't guess" + Create-ticket button → human-escalation incident |
| 6 | "purple banana window" | Low confidence (40% < 60%): no action, escalation offered |
| 7 | "My account is locked" (as Priya) / (as John) | Unlock automated / "not locked, no action needed" |

`pytest -v` in `backend/` runs these through the HTTP API (`tests/test_scenarios.py`) plus unit tests (`tests/test_logic.py`). Use **Reset demo data** in the UI to restore the expired password and locked account between demo runs.

## 8. Suggested 15–20 minute presentation

| Time | Show |
|---|---|
| 2 min | Problem: repetitive L1 tickets, slow resolution. Solution overview |
| 3 min | Architecture diagram (§2) and why each technology |
| 8–10 min | Live demo of scenarios 1–5 in the Self-Service screen; open *AI Analysis* for scenario 1; *Dashboard* at the end |
| 2 min | Knowledge Base screen: search, chunk scores, sources; explain chunking → embeddings → FAISS → LLM |
| 2 min | ServiceNow: mapping table, `GET /api/tickets/{number}`, mock vs real switch, audit log |
| 2–3 min | Limitations and next steps (§9) |

## 9. Known limitations / future improvements

- Classification is rule-based with an optional LLM fallback; a production system would fine-tune or few-shot an LLM classifier and evaluate it on labelled tickets.
- The FAISS index is rebuilt in memory at start-up (fine for ~40 chunks). Production: persist the index or use Qdrant, and re-index on document change.
- The TF-IDF fallback embedder is lexical; the sentence-transformers model is much better at paraphrases. Relevance thresholds are tuned for 8 documents and should be calibrated on a larger KB.
- Authentication, per-user authorisation and rate limiting are out of scope; the "signed in as" selector is a demo shortcut.
- Mock directory/endpoint/provisioning APIs stand in for AD/Entra ID, Intune and a software-deployment tool.
- Provisioning completion is simulated by a timer, not a real callback/webhook.
- The ServiceNow real client has been written against the documented Table API but needs verification against your instance.
- Conversation memory is not passed to the LLM; each message is handled independently.

## 10. Repository layout

```
backend/
  app/            config, db, servicenow, llm, rag, classifier, agents, provisioning, orchestrator, main
  knowledge_base/ 8 sample IT articles (markdown with front matter)
  tests/          unit + end-to-end scenario tests
frontend/src/     App, api, components, pages/{SelfService,Dashboard,Analysis,KnowledgeBase}
```
