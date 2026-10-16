"""Retrieval-Augmented Generation over the IT knowledge base.

Pipeline:  Document -> Chunking -> Embedding -> Vector DB (FAISS) -> Semantic search
           -> LLM (Hugging Face) -> Grounded response + sources + confidence

Safety: if the best retrieved chunk is below a relevance threshold the engine refuses to
answer ("not in the approved knowledge base") instead of letting the LLM guess.
"""
import logging
import re

import numpy as np

from .config import settings

log = logging.getLogger(__name__)

_STOP = set(
    """a an and are as at be but by can do does for from had has have how i if in is it its
    me my of on or our so that the their them then there these they this to up us was we
    what when where which who why will with would you your am been being could should
    please need want get got just also any some about into out""".split()
)


_SYNONYMS = {"frozen": "freez", "froze": "freez", "forgot": "forget", "forgotten": "forget",
             "wireless": "wifi", "mail": "email", "e": "email"}


def _stem(word: str) -> str:
    if word in _SYNONYMS:
        return _SYNONYMS[word]
    for suf in ("ing", "ed", "s"):
        if word.endswith(suf) and len(word) - len(suf) >= 3:
            word = word[: -len(suf)]
            if suf != "s" and len(word) > 3 and word[-1] == word[-2] and word[-1] not in "lsz":
                word = word[:-1]  # dropping -> drop
            break
    if word.endswith("e") and len(word) > 3:
        word = word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    text = text.lower().replace("wi-fi", "wifi")
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text) if w not in _STOP and len(w) > 1]


# --------------------------------------------------------------------------- embedders
class TfidfEmbedder:
    """Lightweight offline fallback so the app works without downloading a model."""

    name = "tfidf"
    default_min_relevance = 0.22

    def fit(self, texts: list[str]) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._v = TfidfVectorizer(analyzer=tokenize, sublinear_tf=True)
        self._v.fit(texts)

    def encode(self, texts: list[str]) -> np.ndarray:
        return self._v.transform(texts).toarray().astype("float32")  # L2-normalised

    def coverage(self, text: str) -> float:
        """Share of the query's content words that exist anywhere in the knowledge base.
        Guards against matching on one incidental word ('request', 'day') in an unrelated question."""
        tokens = tokenize(text)
        if not tokens:
            return 0.0
        vocab = self._v.vocabulary_
        return sum(t in vocab for t in tokens) / len(tokens)


class SentenceTransformerEmbedder:
    """Open-source sentence-transformers model (default all-MiniLM-L6-v2, 384-dim)."""

    name = "sentence-transformers"
    default_min_relevance = 0.35

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self._m = SentenceTransformer(model_name)
        self.model_name = model_name

    def fit(self, texts: list[str]) -> None:  # nothing to fit
        return None

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(
            self._m.encode(texts, normalize_embeddings=True, show_progress_bar=False), dtype="float32"
        )


def make_embedder():
    backend = settings.EMBEDDING_BACKEND
    if backend in ("auto", "sentence-transformers", "st"):
        try:
            return SentenceTransformerEmbedder(settings.EMBEDDING_MODEL)
        except Exception as exc:  # noqa: BLE001
            if backend != "auto":
                raise
            log.warning("sentence-transformers unavailable (%s); using TF-IDF fallback", exc)
    return TfidfEmbedder()


# --------------------------------------------------------------------------- vector store
class VectorStore:
    """FAISS inner-product index (cosine on normalised vectors). Falls back to NumPy if
    faiss cannot be imported (e.g. some Windows setups)."""

    def __init__(self, matrix: np.ndarray) -> None:
        self.matrix = matrix
        try:
            import faiss

            self.index = faiss.IndexFlatIP(matrix.shape[1])
            self.index.add(matrix)
            self.backend = "faiss"
        except Exception as exc:  # noqa: BLE001
            log.warning("faiss unavailable (%s); using NumPy search", exc)
            self.index = None
            self.backend = "numpy"

    def search(self, query_vec: np.ndarray, k: int):
        k = min(k, len(self.matrix))
        if self.index is not None:
            scores, idx = self.index.search(query_vec, k)
            return scores[0].tolist(), idx[0].tolist()
        sims = (self.matrix @ query_vec[0]).astype(float)
        idx = np.argsort(-sims)[:k]
        return sims[idx].tolist(), idx.tolist()


# --------------------------------------------------------------------------- documents
def load_documents(kb_dir) -> list[dict]:
    docs = []
    for path in sorted(kb_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta, body = {}, text
        m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            body = m.group(2)
        docs.append(
            {
                "id": meta.get("id", path.stem),
                "title": meta.get("title", path.stem),
                "category": meta.get("category", "General"),
                "file": path.name,
                "body": body.strip(),
            }
        )
    return docs


def chunk_document(doc: dict, max_chars: int = 600) -> list[dict]:
    """Split by '## ' sections, then group lines up to max_chars with a 1-line overlap."""
    chunks = []
    for section in re.split(r"\n(?=## )", doc["body"]):
        lines = [l.rstrip() for l in section.splitlines() if l.strip() and not l.startswith("# ")]
        if not lines:
            continue
        heading = ""
        if lines[0].startswith("## "):
            heading = lines[0][3:].strip()
            lines = lines[1:]
        buf, size = [], 0

        def emit():
            if not buf:
                return
            text = "\n".join(buf)
            chunks.append(
                {
                    "doc_id": doc["id"],
                    "title": doc["title"],
                    "category": doc["category"],
                    "heading": heading,
                    "text": text,
                    "embed_text": f"{doc['title']}. {heading}. {text}",
                }
            )

        for line in lines:
            if buf and size + len(line) > max_chars:
                emit()
                buf, size = [buf[-1]], len(buf[-1])
            buf.append(line)
            size += len(line)
        emit()
    return chunks


# --------------------------------------------------------------------------- engine
class RAGEngine:
    def __init__(self, kb_dir=None) -> None:
        self.kb_dir = kb_dir or settings.KB_DIR
        self.docs: list[dict] = []
        self.chunks: list[dict] = []
        self.embedder = None
        self.store = None

    @property
    def min_relevance(self) -> float:
        if settings.MIN_RELEVANCE is not None:
            return settings.MIN_RELEVANCE
        return self.embedder.default_min_relevance

    def build(self, persist: bool = True) -> "RAGEngine":
        self.docs = load_documents(self.kb_dir)
        self.chunks = [c for d in self.docs for c in chunk_document(d)]
        if not self.chunks:
            raise RuntimeError(f"No knowledge documents found in {self.kb_dir}")
        self.embedder = make_embedder()
        texts = [c["embed_text"] for c in self.chunks]
        self.embedder.fit(texts)
        self.store = VectorStore(self.embedder.encode(texts))
        log.info(
            "KB indexed: %d docs, %d chunks, embedder=%s, store=%s",
            len(self.docs), len(self.chunks), self.embedder.name, self.store.backend,
        )
        if persist:
            self._persist_metadata()
        return self

    def _persist_metadata(self) -> None:
        from .db import get_db, now_iso

        coll = get_db().knowledge
        coll.delete_many({})
        for d in self.docs:
            coll.insert_one(
                {
                    "id": d["id"], "title": d["title"], "category": d["category"], "file": d["file"],
                    "chunk_count": sum(1 for c in self.chunks if c["doc_id"] == d["id"]),
                    "content": d["body"], "indexed_at": now_iso(),
                }
            )

    # ---- retrieval -------------------------------------------------------
    def search(self, query: str, k: int = 4, category: str | None = None) -> list[dict]:
        q = self.embedder.encode([query])
        fetch = len(self.chunks) if category else k
        scores, idx = self.store.search(q, fetch)
        hits = []
        for s, i in zip(scores, idx):
            if i < 0:
                continue
            c = self.chunks[i]
            if category and c["category"].lower() != category.lower():
                continue
            hits.append({**{k_: c[k_] for k_ in ("doc_id", "title", "category", "heading", "text")},
                         "score": round(float(s), 4)})
        return hits[:k]

    @staticmethod
    def sources_from(hits: list[dict]) -> list[dict]:
        best: dict[str, dict] = {}
        for h in hits:
            if h["doc_id"] not in best:
                best[h["doc_id"]] = {
                    "id": h["doc_id"], "title": h["title"], "category": h["category"],
                    "score": h["score"],
                    "snippet": (h["heading"] + ": " if h["heading"] else "") + h["text"].replace("\n", " ")[:220],
                }
        return sorted(best.values(), key=lambda s: -s["score"])

    def _confidence(self, best: float, answered: bool) -> float:
        mr = self.min_relevance
        if not answered:
            return round(max(0.0, min(0.45, best / mr * 0.4 if mr else 0.0)), 2)
        span = max(0.6 - mr, 0.05)
        return round(max(0.5, min(0.97, 0.5 + (best - mr) / span * 0.45)), 2)

    # ---- grounded answer ---------------------------------------------------
    def answer(self, query: str) -> dict:
        hits = self.search(query, k=4)
        best = hits[0]["score"] if hits else 0.0
        mr = self.min_relevance
        coverage = self.embedder.coverage(query) if hasattr(self.embedder, "coverage") else 1.0
        if best < mr or coverage < 0.7:
            return {
                "answered": False,
                "answer": ("I couldn't find this in the approved IT knowledge base, so I won't guess. "
                           "I can raise a ticket so a helpdesk engineer can help."),
                "sources": [], "confidence": self._confidence(best, False), "mode": "refused",
                "relevance": round(best, 3),
            }
        relevant = [h for h in hits if h["score"] >= max(mr, 0.6 * best)][:3]
        sources = self.sources_from(relevant)
        context = "\n\n".join(f"[{h['title']} - {h['heading']}]\n{h['text']}" for h in relevant)

        from . import llm

        generated = llm.generate(
            "You are an IT helpdesk assistant. Answer ONLY from the provided knowledge base context. "
            "Be concise, use numbered steps when giving instructions. If the context does not contain "
            "the answer, reply with exactly: INSUFFICIENT",
            f"Context:\n{context}\n\nQuestion: {query}",
        )
        if generated and "INSUFFICIENT" in generated.upper()[:40]:
            return {
                "answered": False,
                "answer": ("The approved knowledge base doesn't contain enough information to answer this. "
                           "I can raise a ticket for a helpdesk engineer."),
                "sources": [], "confidence": self._confidence(best, False), "mode": "llm-refused",
                "relevance": round(best, 3),
            }
        if generated:
            text, mode = generated, "llm"
        else:
            text, mode = self._extractive(relevant), "extractive"
        return {
            "answered": True, "answer": text, "sources": sources,
            "confidence": self._confidence(best, True), "mode": mode, "relevance": round(best, 3),
        }

    @staticmethod
    def _extractive(hits: list[dict]) -> str:
        """No-LLM fallback: quote the best approved chunk(s) verbatim."""
        parts, seen = [], set()
        for h in hits[:2]:
            if h["text"] in seen:
                continue
            seen.add(h["text"])
            title = f"{h['title']} - {h['heading']}" if h["heading"] else h["title"]
            parts.append(f"**{title}**\n{h['text']}")
        return "From the approved knowledge base:\n\n" + "\n\n".join(parts)


_engine: RAGEngine | None = None


def get_rag() -> RAGEngine:
    global _engine
    if _engine is None:
        _engine = RAGEngine().build()
    return _engine


def reset_rag() -> None:
    global _engine
    _engine = None
