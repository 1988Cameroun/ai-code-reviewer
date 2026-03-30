from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import httpx
import json
import sqlite3
import os
import time
from datetime import datetime

app = FastAPI(title="AI Code Reviewer", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "/data/reviews.db"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")


def init_db():
    os.makedirs("/data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL,
            language TEXT,
            primary_review TEXT,
            meta_evaluation TEXT,
            overall_score REAL,
            correctness_score REAL,
            security_score REAL,
            performance_score REAL,
            scalability_score REAL,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()


class CodeSubmission(BaseModel):
    code: str
    language: Optional[str] = "auto-detect"
    context: Optional[str] = ""


class ReviewResponse(BaseModel):
    id: int
    primary_review: dict
    meta_evaluation: dict
    scores: dict
    created_at: str


async def call_claude(system_prompt: str, user_message: str) -> str:
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not set")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-opus-4-5",
                "max_tokens": 2000,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_message}],
            },
        )
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Claude API error: {response.text}")
        data = response.json()
        return data["content"][0]["text"]


@app.post("/api/review", response_model=ReviewResponse)
async def review_code(submission: CodeSubmission):
    # ── Pass 1: Primary Review ──────────────────────────────────────────────
    primary_system = """You are a senior software engineer and AI code evaluator.
Analyze the submitted code and return ONLY a valid JSON object with this exact structure:
{
  "language": "detected language",
  "summary": "2-3 sentence overall assessment",
  "correctness": {
    "score": 0-10,
    "issues": ["list of correctness issues"],
    "strengths": ["list of correctness strengths"]
  },
  "security": {
    "score": 0-10,
    "issues": ["list of security vulnerabilities"],
    "strengths": ["list of security strengths"]
  },
  "performance": {
    "score": 0-10,
    "issues": ["list of performance problems"],
    "strengths": ["list of performance strengths"]
  },
  "scalability": {
    "score": 0-10,
    "issues": ["list of scalability concerns"],
    "strengths": ["list of scalability strengths"]
  },
  "suggestions": ["top 3-5 concrete improvement suggestions"]
}
Return ONLY the JSON. No markdown, no explanation."""

    user_msg = f"Language hint: {submission.language}\nContext: {submission.context}\n\nCode:\n```\n{submission.code}\n```"
    
    raw_primary = await call_claude(primary_system, user_msg)
    
    try:
        primary_review = json.loads(raw_primary)
    except json.JSONDecodeError:
        # Strip markdown fences if present
        cleaned = raw_primary.strip().strip("```json").strip("```").strip()
        primary_review = json.loads(cleaned)

    # ── Pass 2: Meta-Evaluation ─────────────────────────────────────────────
    meta_system = """You are an expert AI evaluation auditor. Your job is to critique an AI's code review.
Return ONLY a valid JSON object with this exact structure:
{
  "review_quality_score": 0-10,
  "missed_issues": ["issues the reviewer missed"],
  "overblown_concerns": ["concerns the reviewer exaggerated"],
  "scoring_accuracy": "assessment of whether scores are calibrated correctly",
  "confidence": "high | medium | low",
  "verdict": "1-2 sentence final verdict on the code quality"
}
Return ONLY the JSON. No markdown, no explanation."""

    meta_msg = f"Original code:\n```\n{submission.code}\n```\n\nAI Review produced:\n{json.dumps(primary_review, indent=2)}"
    
    raw_meta = await call_claude(meta_system, meta_msg)
    
    try:
        meta_evaluation = json.loads(raw_meta)
    except json.JSONDecodeError:
        cleaned = raw_meta.strip().strip("```json").strip("```").strip()
        meta_evaluation = json.loads(cleaned)

    # ── Compute composite score ─────────────────────────────────────────────
    scores = {
        "correctness": primary_review.get("correctness", {}).get("score", 0),
        "security": primary_review.get("security", {}).get("score", 0),
        "performance": primary_review.get("performance", {}).get("score", 0),
        "scalability": primary_review.get("scalability", {}).get("score", 0),
    }
    overall = round(sum(scores.values()) / len(scores), 2)

    # ── Persist to DB ───────────────────────────────────────────────────────
    created_at = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(
        """INSERT INTO reviews
           (code, language, primary_review, meta_evaluation, overall_score,
            correctness_score, security_score, performance_score, scalability_score, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            submission.code,
            primary_review.get("language", submission.language),
            json.dumps(primary_review),
            json.dumps(meta_evaluation),
            overall,
            scores["correctness"],
            scores["security"],
            scores["performance"],
            scores["scalability"],
            created_at,
        ),
    )
    review_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return ReviewResponse(
        id=review_id,
        primary_review=primary_review,
        meta_evaluation=meta_evaluation,
        scores={**scores, "overall": overall},
        created_at=created_at,
    )


@app.get("/api/history")
async def get_history(limit: int = 20):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, language, overall_score, correctness_score, security_score, "
        "performance_score, scalability_score, created_at FROM reviews ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/review/{review_id}")
async def get_review(review_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Review not found")
    r = dict(row)
    r["primary_review"] = json.loads(r["primary_review"])
    r["meta_evaluation"] = json.loads(r["meta_evaluation"])
    return r


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# Serve frontend
app.mount("/", StaticFiles(directory="/app/frontend", html=True), name="frontend")
