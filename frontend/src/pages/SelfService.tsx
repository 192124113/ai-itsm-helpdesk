import { useEffect, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { api } from "../api";
import { Badge, ConfidenceBar, RichText, SourceList, StepList, priorityTone } from "../components";
import type { ChatEntry } from "../types";

const EXAMPLES = [
  "I cannot connect to VPN since this morning. Authentication keeps failing.",
  "My password has expired.",
  "How do I troubleshoot Outlook synchronization?",
  "I need Visual Studio Code.",
  "What is the capital of France?",
];

interface Props {
  userId: string;
  entries: ChatEntry[];
  setEntries: Dispatch<SetStateAction<ChatEntry[]>>;
  onViewAnalysis: (id: string) => void;
}

export default function SelfService({ userId, entries, setEntries, onViewAnalysis }: Props) {
  const [text, setText] = useState("");
  const [pending, setPending] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [swStatus, setSwStatus] = useState<Record<string, string>>({});
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries.length, pending]);

  // Poll provisioning status while any software request is still running.
  const provisioning = entries.some(
    (e) => e.software_request && (swStatus[e.software_request.request_id] ?? e.software_request.status) === "Provisioning"
  );
  useEffect(() => {
    if (!provisioning) return;
    const t = setInterval(async () => {
      try {
        const reqs = await api.softwareRequests();
        setSwStatus(Object.fromEntries(reqs.map((r) => [r.request_id, r.status])));
      } catch {
        /* ignore transient errors */
      }
    }, 3000);
    return () => clearInterval(t);
  }, [provisioning]);

  async function send(message: string) {
    const msg = message.trim();
    if (!msg || pending) return;
    setText("");
    setError(null);
    setPending(msg);
    try {
      const res = await api.chat(userId, msg);
      setEntries((prev) => [...prev, res]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setPending(null);
    }
  }

  async function escalate(entry: ChatEntry) {
    try {
      const res = await api.escalate(userId, entry.message, entry.id);
      setEntries((prev) =>
        prev.map((e) =>
          e.id === entry.id
            ? {
                ...e,
                ticket: res.ticket,
                escalation_suggested: false,
                reply: e.reply + "\n\n" + res.reply,
                analysis: { ...e.analysis, escalated: true, servicenow: res.ticket },
              }
            : e
        )
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Escalation failed");
    }
  }

  return (
    <div className="page chat-page">
      <h1>Employee Self-Service</h1>
      <p className="muted">Ask a question, report a problem or request software. The AI decides the right workflow.</p>

      <div className="chips">
        {EXAMPLES.map((ex) => (
          <button key={ex} className="chip" onClick={() => send(ex)} disabled={!!pending}>
            {ex}
          </button>
        ))}
      </div>

      <div className="chat-window">
        {entries.length === 0 && !pending && (
          <div className="empty">Try one of the example requests above, or type your own below.</div>
        )}
        {entries.map((e) => {
          const sw = e.software_request;
          const status = sw ? swStatus[sw.request_id] ?? sw.status : null;
          const a = e.analysis;
          return (
            <div key={e.id}>
              <div className="bubble user">{e.message}</div>
              <div className="bubble bot">
                <div className="bot-head">
                  <Badge tone="indigo">{a.intent_label}</Badge>
                  {a.category !== "General" && a.intent !== "knowledge_question" && (
                    <Badge>{a.category} / {a.subcategory}</Badge>
                  )}
                  {a.intent === "incident" && <Badge tone={priorityTone(a.priority)}>{a.priority}</Badge>}
                  <span className="grow" />
                  <button className="link" onClick={() => onViewAnalysis(e.id)}>View AI analysis →</button>
                </div>

                <RichText text={e.reply} />

                {e.steps && <StepList steps={e.steps} />}

                {sw && (
                  <div className="card-inline">
                    <div className="kv"><span>Request ID</span><b>{sw.request_id}</b></div>
                    <div className="kv"><span>Software</span><b>{sw.software}</b></div>
                    <div className="kv">
                      <span>Status</span>
                      <Badge tone={status === "Completed" ? "green" : "orange"}>{status}</Badge>
                    </div>
                    <div className="ok-note">✓ ServiceNow Request created successfully</div>
                  </div>
                )}

                {e.ticket && !sw && (
                  <div className="card-inline">
                    <div className="kv"><span>ServiceNow</span><b>{e.ticket.number}</b></div>
                    <div className="kv"><span>State</span><b>{e.ticket.state}</b></div>
                  </div>
                )}

                <SourceList sources={a.sources} />

                <div className="bot-foot">
                  <span className="muted small">AI confidence</span>
                  <ConfidenceBar value={a.confidence} threshold={a.threshold} />
                </div>

                {e.escalation_suggested && (
                  <div className="escalate">
                    <span>Not what you needed?</span>
                    <button className="btn" onClick={() => escalate(e)}>Create a ticket for a human</button>
                  </div>
                )}
              </div>
            </div>
          );
        })}
        {pending && (
          <div>
            <div className="bubble user">{pending}</div>
            <div className="bubble bot typing">Thinking…</div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {error && <div className="error">{error}</div>}

      <form
        className="composer"
        onSubmit={(ev) => {
          ev.preventDefault();
          send(text);
        }}
      >
        <input
          value={text}
          onChange={(ev) => setText(ev.target.value)}
          placeholder="Describe your issue or request…"
          disabled={!!pending}
        />
        <button className="btn primary" type="submit" disabled={!!pending || !text.trim()}>Send</button>
      </form>
    </div>
  );
}
