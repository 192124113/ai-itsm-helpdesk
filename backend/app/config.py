"""Central configuration. Everything is read from environment variables / .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _float(name: str):
    value = os.getenv(name, "").strip()
    return float(value) if value else None


class Settings:
    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        # --- Database -------------------------------------------------------
        self.MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
        self.MONGODB_DB = os.getenv("MONGODB_DB", "itsm_helpdesk")
        # Force the in-memory database even if a URI is configured (used by tests).
        self.USE_MOCK_DB = _flag("USE_MOCK_DB", False)

        # --- LLM (Hugging Face) ---------------------------------------------
        self.HF_TOKEN = os.getenv("HF_TOKEN", "").strip()
        self.HF_MODEL = os.getenv("HF_MODEL", "Qwen/Qwen2.5-7B-Instruct")
        self.DISABLE_LLM = _flag("DISABLE_LLM", False)

        # --- Embeddings / vector store ---------------------------------------
        # auto -> sentence-transformers if available, else TF-IDF fallback
        self.EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "auto").strip().lower()
        self.EMBEDDING_MODEL = os.getenv(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )
        self.MIN_RELEVANCE = _float("MIN_RELEVANCE")  # None -> backend default
        self.KB_DIR = Path(os.getenv("KB_DIR", str(BASE_DIR / "knowledge_base")))

        # --- AI governance ---------------------------------------------------
        # Below this confidence the AI does not act on its own; it offers escalation.
        self.CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.6"))

        # --- ServiceNow --------------------------------------------------------
        self.SERVICENOW_MODE = os.getenv("SERVICENOW_MODE", "mock").strip().lower()
        self.SERVICENOW_INSTANCE = os.getenv("SERVICENOW_INSTANCE", "").rstrip("/")
        self.SERVICENOW_USER = os.getenv("SERVICENOW_USER", "")
        self.SERVICENOW_PASSWORD = os.getenv("SERVICENOW_PASSWORD", "")

        # --- Mock provisioning -------------------------------------------------
        self.PROVISION_SECONDS = int(os.getenv("PROVISION_SECONDS", "8"))

        self.CORS_ORIGINS = [
            o.strip()
            for o in os.getenv(
                "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",")
            if o.strip()
        ]

    @property
    def llm_available(self) -> bool:
        return bool(self.HF_TOKEN) and not self.DISABLE_LLM


settings = Settings()
