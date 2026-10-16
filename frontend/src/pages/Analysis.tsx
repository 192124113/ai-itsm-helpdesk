import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api";
import { Badge, ConfidenceBar, SourceList, StepList, fmtTime, priorityTone } from "../components";
import type { ChatEntry } from "../types";

export default function Analysis({ selectedId, onSelect }: { selectedId: string | null; onSelect: (id: string) => void }) {
  const [items, setItems] = useState<ChatEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.analyses().then(setItems).catch((e) => setError(String(e)));
  }, [selectedId]);

  const current = items.find((i) => i.id === selectedId) ?? items[0];
  const a = current?.analysis;

  return (
    <div className="page">
      <h1>AI Analysis</h1>
      <p className="muted">How the AI understood each request, what it retrieved, what it did and the ServiceNow reference.</p>
      {error && <div className="error">{error}</div>}

      <div className="analysis-layout">
        <div className="analysis-list">
          {items.length === 0 && <div className="muted">No requests analysed yet.</div>}
          {items.map((i) => (
            <button
              key={i.id}
              className={`analysis-item ${current && current.id === i.id ? "active" : ""}`}
              onClick={() => onSelect(i.id)}
            >
              <div className="small muted">{fmtTime(i.created_at)} · {i.analysis.intent_label}</div>
              <div>{i.message.length > 70 ? i.message.slice(0, 70) + "…" : i.message}</div>
            </button>
          ))}
        </div>

        {current && a && (
          <div className="panel analysis-detail">
            <h2>“{current.message}”</h2>
            <div className="grid">
              <Field label="Intent"><Badge tone="indigo">{a.intent_label}</Badge></Field>
              <Field label="Category / Sub-category">{a.category} / {a.subcategory}</Field>
              <Field label="Priority"><Badge tone={priorityTone(a.priority)}>{a.priority}</Badge></Field>
              <Field label="Impact / Urgency">{a.impact} / {a.urgency}</Field>
              <Field label="Assignment group">{a.assignment_group}</Field>
              <Field label="Summary">{a.summary}</Field>
              <Field label="Suggested resolution">{a.suggested_resolution}</Field>
              <Field label="Workflow">{a.workflow}</Field>
              <Field label="Classification method">{a.classification_method}</Field>
              <Field label="AI confidence">
                <ConfidenceBar value={a.confidence} threshold={a.threshold} />
                <div className="muted small">Escalation threshold: {Math.round(a.threshold * 100)}%</div>
              </Field>
              {a.rag_confidence !== null && (
                <Field label="RAG confidence">
                  <ConfidenceBar value={a.rag_confidence} threshold={a.threshold} />
                </Field>
              )}
              <Field label="ServiceNow reference">
                {a.servicenow ? (
                  <>
                    <b>{a.servicenow.number}</b> <span className="muted">({a.servicenow.type}, {a.servicenow.state})</span>
                  </>
                ) : (
                  <span className="muted">None created</span>
                )}
              </Field>
              <Field label="Escalated to human">{a.escalated || current.escalation_suggested ? (a.escalated ? "Yes" : "Offered") : "No"}</Field>
            </div>

            {a.automation && (
              <div className="subpanel">
                <div className="label">Automation</div>
                <div className="grid">
                  <Field label="Action">{a.automation.label}</Field>
                  <Field label="Status">
                    <Badge tone={a.automation.status === "success" ? "green" : "orange"}>{a.automation.status}</Badge>{" "}
                    {a.automation.validated && <Badge tone="green">validated</Badge>}
                  </Field>
                  {a.automation.api_call && <Field label="Mock API call"><code>{a.automation.api_call}</code></Field>}
                </div>
              </div>
            )}

            {current.steps && (
              <div className="subpanel">
                <div className="label">Agent reasoning steps</div>
                <StepList steps={current.steps} />
              </div>
            )}

            <SourceList sources={a.sources} />
            {a.sources.length === 0 && <div className="muted small" style={{ marginTop: 12 }}>No approved knowledge sources were used.</div>}
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="field">
      <div className="label">{label}</div>
      <div>{children}</div>
    </div>
  );
}
