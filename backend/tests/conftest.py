"""Test configuration: no network, no API keys, no real database or ServiceNow."""
import os
import sys
from pathlib import Path

os.environ.update(
    USE_MOCK_DB="1",          # in-memory MongoDB (mongomock)
    EMBEDDING_BACKEND="tfidf",  # no model download
    DISABLE_LLM="1",          # extractive answers, deterministic
    SERVICENOW_MODE="mock",
    HF_TOKEN="",
    PROVISION_SECONDS="1",    # so the status flips to Completed quickly
)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        c.post("/api/demo/reset")
        yield c
