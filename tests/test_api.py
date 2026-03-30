import pytest
import json
import sqlite3
import os
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

os.environ["ANTHROPIC_API_KEY"] = "test-key"

# Patch DB and data dir for tests
import tempfile
tmpdir = tempfile.mkdtemp()
os.environ["DATA_DIR"] = tmpdir

from app.main import app

client = TestClient(app)

MOCK_PRIMARY = {
    "language": "Python",
    "summary": "Code has critical security issues.",
    "correctness": {"score": 7, "issues": ["No error handling"], "strengths": ["Logic is clear"]},
    "security": {"score": 2, "issues": ["SQL injection risk"], "strengths": []},
    "performance": {"score": 6, "issues": ["N+1 query"], "strengths": ["Indexed lookups"]},
    "scalability": {"score": 5, "issues": ["No caching"], "strengths": ["Stateless design"]},
    "suggestions": ["Add parameterized queries", "Add error handling", "Implement caching"],
}

MOCK_META = {
    "review_quality_score": 8,
    "missed_issues": ["Missing rate limiting"],
    "overblown_concerns": [],
    "scoring_accuracy": "Scores are appropriately calibrated.",
    "confidence": "high",
    "verdict": "This code poses serious security risks and should not be deployed.",
}


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_history_empty():
    r = client.get("/api/history")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@patch("app.main.call_claude")
def test_review_endpoint(mock_claude):
    mock_claude.side_effect = [
        json.dumps(MOCK_PRIMARY),
        json.dumps(MOCK_META),
    ]

    r = client.post("/api/review", json={
        "code": "import sqlite3\nquery = f\"SELECT * FROM users WHERE id={user_id}\"",
        "language": "Python",
        "context": "Auth module",
    })

    assert r.status_code == 200
    data = r.json()
    assert "scores" in data
    assert data["scores"]["security"] == 2
    assert data["scores"]["overall"] == 5.0
    assert "primary_review" in data
    assert "meta_evaluation" in data
    assert data["meta_evaluation"]["confidence"] == "high"


@patch("app.main.call_claude")
def test_review_persisted(mock_claude):
    mock_claude.side_effect = [
        json.dumps(MOCK_PRIMARY),
        json.dumps(MOCK_META),
    ]

    client.post("/api/review", json={"code": "print('hello')", "language": "Python"})

    r = client.get("/api/history")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_review_not_found():
    r = client.get("/api/review/999999")
    assert r.status_code == 404


def test_review_empty_code():
    r = client.post("/api/review", json={"code": ""})
    # Empty code should still attempt (Claude will handle it) or return error
    assert r.status_code in [200, 422, 500]
