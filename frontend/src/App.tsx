import { useEffect, useState } from "react";
import { api } from "./api";
import Analysis from "./pages/Analysis";
import Dashboard from "./pages/Dashboard";
import KnowledgeBase from "./pages/KnowledgeBase";
import SelfService from "./pages/SelfService";
import type { ChatEntry, Health, User } from "./types";

type Tab = "chat" | "dashboard" | "analysis" | "kb";

const NAV: { id: Tab; label: string }[] = [
  { id: "chat", label: "Employee Self-Service" },
  { id: "dashboard", label: "ITSM Dashboard" },
  { id: "analysis", label: "AI Analysis" },
  { id: "kb", label: "Knowledge Base" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("chat");
  const [users, setUsers] = useState<User[]>([]);
  const [userId, setUserId] = useState("demo.user");
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    api.users().then(setUsers).catch(() => setOffline(true));
    api.health().then(setHealth).catch(() => setOffline(true));
  }, []);

  useEffect(() => {
    api.history(userId).then(setEntries).catch(() => setEntries([]));
  }, [userId]);

  function viewAnalysis(id: string) {
    setSelected(id);
    setTab("analysis");
  }

  async function resetDemo() {
    await api.resetDemo();
    alert("Demo employees restored (expired password, locked account).");
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">AI ITSM<br /><span>Helpdesk</span></div>
        <nav>
          {NAV.map((n) => (
            <button key={n.id} className={tab === n.id ? "active" : ""} onClick={() => setTab(n.id)}>
              {n.label}
            </button>
          ))}
        </nav>

        <div className="side-block">
          <label>Signed in as</label>
          <select value={userId} onChange={(e) => setUserId(e.target.value)}>
            {(users.length ? users : [{ user_id: "demo.user", name: "Demo User", department: "" }]).map((u) => (
              <option key={u.user_id} value={u.user_id}>{u.name} ({u.user_id})</option>
            ))}
          </select>
          <button className="btn small-btn" onClick={resetDemo}>Reset demo data</button>
        </div>

        <div className="side-block status">
          {offline && <div className="offline">Backend not reachable on :8000</div>}
          {health && (
            <>
              <div><span>DB</span> {health.database}</div>
              <div><span>ServiceNow</span> {health.servicenow}</div>
              <div><span>LLM</span> {health.llm}</div>
              <div><span>Embeddings</span> {health.embedder}</div>
              <div><span>Vector DB</span> {health.vector_store}</div>
            </>
          )}
        </div>
      </aside>

      <main>
        {tab === "chat" && (
          <SelfService userId={userId} entries={entries} setEntries={setEntries} onViewAnalysis={viewAnalysis} />
        )}
        {tab === "dashboard" && <Dashboard />}
        {tab === "analysis" && <Analysis selectedId={selected} onSelect={setSelected} />}
        {tab === "kb" && <KnowledgeBase />}
      </main>
    </div>
  );
}
