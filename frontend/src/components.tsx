import type { ReactNode } from "react";
import type { Source, Step } from "./types";

/** Tiny renderer for the **bold** / _italic_ / line breaks the backend emits. */
export function RichText({ text }: { text: string }) {
  const lines = text.split("\n");
  return (
    <>
      {lines.map((line, i) => (
        <div key={i} className={line.trim() === "" ? "spacer" : undefined}>
          {renderInline(line)}
        </div>
      ))}
    </>
  );
}

function renderInline(line: string): ReactNode[] {
  const parts = line.split(/(\*\*[^*]+\*\*|_[^_]+_)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={i}>{p.slice(2, -2)}</strong>;
    if (p.length > 2 && p.startsWith("_") && p.endsWith("_")) return <em key={i}>{p.slice(1, -1)}</em>;
    return <span key={i}>{p}</span>;
  });
}

export function Badge({ children, tone = "gray" }: { children: ReactNode; tone?: string }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function priorityTone(p: string): string {
  return p === "P1" ? "red" : p === "P2" ? "orange" : p === "P3" ? "blue" : "gray";
}

export function ConfidenceBar({ value, threshold }: { value: number; threshold: number }) {
  const pct = Math.round(value * 100);
  const ok = value >= threshold;
  return (
    <div className="conf">
      <div className="conf-track">
        <div className={`conf-fill ${ok ? "ok" : "low"}`} style={{ width: `${pct}%` }} />
        <div className="conf-threshold" style={{ left: `${Math.round(threshold * 100)}%` }} title="Escalation threshold" />
      </div>
      <span className={ok ? "conf-ok" : "conf-low"}>{pct}%</span>
    </div>
  );
}

export function SourceList({ sources }: { sources: Source[] }) {
  if (!sources.length) return null;
  return (
    <div className="sources">
      <div className="label">Knowledge sources used</div>
      {sources.map((s) => (
        <div className="source" key={s.id} title={s.snippet}>
          <span className="source-id">{s.id}</span>
          <span className="source-title">{s.title}</span>
          <span className="source-score">{Math.round(s.score * 100)}% match</span>
        </div>
      ))}
    </div>
  );
}

export function StepList({ steps }: { steps: Step[] }) {
  const icon = (s: Step["status"]) => (s === "done" ? "✓" : s === "failed" ? "✕" : "–");
  return (
    <ol className="steps">
      {steps.map((s, i) => (
        <li key={i} className={s.status}>
          <span className="step-icon">{icon(s.status)}</span>
          <div>
            <div className="step-name">{s.step}</div>
            <div className="step-detail">{s.detail}</div>
          </div>
        </li>
      ))}
    </ol>
  );
}

export function fmtTime(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
