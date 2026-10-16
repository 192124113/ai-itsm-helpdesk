import { useEffect, useState } from "react";
import { api } from "../api";
import { Badge, ConfidenceBar, RichText, SourceList } from "../components";
import type { Article, Hit, RagAnswer } from "../types";

export default function KnowledgeBase() {
  const [articles, setArticles] = useState<Article[]>([]);
  const [category, setCategory] = useState<string>("All");
  const [openId, setOpenId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [answer, setAnswer] = useState<RagAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.articles().then(setArticles).catch((e) => setError(String(e)));
  }, []);

  const categories = ["All", ...Array.from(new Set(articles.map((a) => a.category)))];
  const shown = articles.filter((a) => category === "All" || a.category === category);

  async function search(q: string) {
    if (q.trim().length < 2) return;
    setBusy(true);
    setError(null);
    try {
      const [h, ans] = await Promise.all([api.kbSearch(q), api.kbAsk(q)]);
      setHits(h);
      setAnswer(ans);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <h1>Knowledge Base</h1>
      <p className="muted">
        {articles.length} approved articles, chunked, embedded and indexed in the vector database. Ask a question to see the RAG pipeline in action.
      </p>

      <form className="composer" onSubmit={(e) => { e.preventDefault(); search(query); }}>
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="e.g. How do I troubleshoot Outlook synchronization?" />
        <button className="btn primary" type="submit" disabled={busy || query.trim().length < 2}>{busy ? "Searching…" : "Search"}</button>
      </form>
      {error && <div className="error">{error}</div>}

      {answer && (
        <div className="panel">
          <h2>RAG result</h2>
          <div className="rag-answer">
            <div className="bot-head">
              <Badge tone={answer.answered ? "green" : "orange"}>{answer.answered ? "Grounded answer" : "Not in knowledge base"}</Badge>
              <Badge>{answer.mode}</Badge>
            </div>
            <RichText text={answer.answer} />
            <SourceList sources={answer.sources} />
            <div className="bot-foot">
              <span className="muted small">Confidence</span>
              <ConfidenceBar value={answer.confidence} threshold={0.6} />
            </div>
          </div>

          {hits && hits.length > 0 && (
            <>
              <div className="label" style={{ marginTop: 16 }}>Semantic search - top chunks by similarity</div>
              <table>
                <thead><tr><th>Score</th><th>Article</th><th>Section</th><th>Chunk preview</th></tr></thead>
                <tbody>
                  {hits.map((h, i) => (
                    <tr key={i}>
                      <td><b>{h.score.toFixed(3)}</b></td>
                      <td>{h.title}</td>
                      <td>{h.heading}</td>
                      <td className="small muted">{h.text.replace(/\n/g, " ").slice(0, 120)}…</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}

      <div className="chips">
        {categories.map((c) => (
          <button key={c} className={`chip ${category === c ? "active" : ""}`} onClick={() => setCategory(c)}>{c}</button>
        ))}
      </div>

      <div className="articles">
        {shown.map((a) => (
          <div className="panel article" key={a.id}>
            <button className="article-head" onClick={() => setOpenId(openId === a.id ? null : a.id)}>
              <span><b>{a.title}</b> <span className="muted small">{a.id} · {a.chunks} chunks</span></span>
              <Badge>{a.category}</Badge>
            </button>
            {openId === a.id && (
              <div className="article-body">
                <RichText text={a.content} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
