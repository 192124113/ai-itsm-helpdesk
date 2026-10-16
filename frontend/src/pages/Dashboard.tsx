import { useEffect, useState } from "react";
import { api } from "../api";
import { Badge, fmtTime, priorityTone } from "../components";
import type { AuditEntry, AutomationAction, SoftwareRequest, Stats, Ticket } from "../types";

export default function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [sw, setSw] = useState<SoftwareRequest[]>([]);
  const [actions, setActions] = useState<AutomationAction[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function load() {
      try {
        const [s, t, r, a, au] = await Promise.all([
          api.dashboard(), api.tickets(), api.softwareRequests(), api.actions(), api.audit(),
        ]);
        if (!alive) return;
        setStats(s); setTickets(t); setSw(r); setActions(a); setAudit(au); setError(null);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "Failed to load");
      }
    }
    load();
    const t = setInterval(load, 4000);
    return () => { alive = false; clearInterval(t); };
  }, []);

  const cards = stats
    ? [
        { label: "Total tickets", value: stats.tickets.total },
        { label: "Open", value: stats.tickets.open },
        { label: "AI-resolved", value: stats.tickets.ai_resolved, tone: "green" },
        { label: "Escalated to human", value: stats.tickets.escalated, tone: "orange" },
        { label: "Software requests", value: stats.software_requests.total },
        {
          label: "Automation success",
          value: stats.automation.success_rate === null ? "–" : `${stats.automation.success_rate}%`,
          sub: `${stats.automation.success}/${stats.automation.total} actions`,
        },
      ]
    : [];

  return (
    <div className="page">
      <h1>ITSM Dashboard</h1>
      <p className="muted">Live view of tickets, AI outcomes, software provisioning and automation. Refreshes every 4 seconds.</p>
      {error && <div className="error">{error}</div>}

      <div className="cards">
        {cards.map((c) => (
          <div className={`stat ${c.tone ?? ""}`} key={c.label}>
            <div className="stat-value">{c.value}</div>
            <div className="stat-label">{c.label}</div>
            {c.sub && <div className="stat-sub">{c.sub}</div>}
          </div>
        ))}
      </div>

      <section className="panel">
        <h2>Tickets</h2>
        <table>
          <thead>
            <tr><th>Number</th><th>Type</th><th>Summary</th><th>Priority</th><th>Group</th><th>Status</th><th>AI</th></tr>
          </thead>
          <tbody>
            {tickets.length === 0 && <tr><td colSpan={7} className="muted">No tickets yet - use the Self-Service screen.</td></tr>}
            {tickets.map((t) => (
              <tr key={t.number}>
                <td><b>{t.number}</b></td>
                <td>{t.type === "incident" ? "Incident" : "Request"}</td>
                <td>{t.short_description}</td>
                <td><Badge tone={priorityTone(t.priority)}>{t.priority}</Badge></td>
                <td>{t.assignment_group}</td>
                <td><Badge tone={t.status === "Resolved" ? "green" : "orange"}>{t.state_label ?? t.status}</Badge></td>
                <td>
                  {t.ai_resolved && <Badge tone="green">AI-resolved</Badge>}{" "}
                  {t.escalated && <Badge tone="orange">Escalated</Badge>}{" "}
                  {t.automation && <Badge tone="indigo">Automated</Badge>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className="two-col">
        <section className="panel">
          <h2>Software requests</h2>
          <table>
            <thead><tr><th>Request</th><th>Software</th><th>User</th><th>Status</th></tr></thead>
            <tbody>
              {sw.length === 0 && <tr><td colSpan={4} className="muted">None yet.</td></tr>}
              {sw.map((r) => (
                <tr key={r.request_id}>
                  <td><b>{r.request_id}</b></td>
                  <td>{r.software}</td>
                  <td>{r.user_id}</td>
                  <td><Badge tone={r.status === "Completed" ? "green" : "orange"}>{r.status}</Badge></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="panel">
          <h2>Automation status</h2>
          <table>
            <thead><tr><th>Action</th><th>Ticket</th><th>Result</th></tr></thead>
            <tbody>
              {actions.length === 0 && <tr><td colSpan={3} className="muted">No automated actions yet.</td></tr>}
              {actions.map((a) => (
                <tr key={a.id}>
                  <td>{a.label}<div className="muted small">{a.user_id}</div></td>
                  <td>{a.ticket_number}</td>
                  <td>
                    <Badge tone={a.status === "success" ? "green" : "red"}>{a.status}</Badge>{" "}
                    {a.validated && <Badge tone="green">validated</Badge>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {stats && (
            <div className="muted small" style={{ marginTop: 8 }}>
              Safe-automation allow-list: {stats.automation_catalogue.map((c) => c.label).join(", ")}
            </div>
          )}
        </section>
      </div>

      <section className="panel">
        <h2>Audit log</h2>
        <table>
          <thead><tr><th>Time</th><th>Event</th><th>Actor</th><th>Ref</th><th>Details</th></tr></thead>
          <tbody>
            {audit.length === 0 && <tr><td colSpan={5} className="muted">Nothing recorded yet.</td></tr>}
            {audit.map((a) => (
              <tr key={a.id}>
                <td>{fmtTime(a.ts)}</td>
                <td><code>{a.event}</code></td>
                <td>{a.actor}</td>
                <td>{a.ref}</td>
                <td className="small muted">{JSON.stringify(a.details).slice(0, 110)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
