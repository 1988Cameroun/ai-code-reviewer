# CodeSentinel — AI Code Evaluation Pipeline

> A dual-pass LLM evaluation system for automated code quality analysis. Built to mirror real-world AI model training workflows: systematic, auditable, and skeptical of its own output.


---

## What It Does

CodeSentinel submits code through a **two-pass evaluation pipeline**:

**Pass 1 — Primary Analysis**
An LLM evaluates the code across four scored dimensions:
- **Correctness** — logic errors, edge cases, undefined behavior
- **Security** — injection flaws, auth issues, data exposure
- **Performance** — algorithmic complexity, blocking calls, memory leaks
- **Scalability** — statefulness, coupling, horizontal scale constraints

**Pass 2 — Meta-Evaluation**
A second LLM call audits the first review — identifying missed issues, inflated scores, and reasoning gaps. This is the critical design choice: **treating AI output as something that requires rigorous, systematic evaluation, not blind trust.**

All results are persisted to SQLite with full score history.

---

## Architecture

```
┌─────────────┐     POST /api/review      ┌──────────────────────┐
│   Browser   │ ─────────────────────────▶│   FastAPI Backend     │
│  (index.html│ ◀─────────────────────────│                      │
└─────────────┘     JSON response          │  ┌────────────────┐  │
                                           │  │  Pass 1: LLM   │  │
                                           │  │  Primary Review│  │
                                           │  └───────┬────────┘  │
                                           │          │            │
                                           │  ┌───────▼────────┐  │
                                           │  │  Pass 2: LLM   │  │
                                           │  │  Meta-Audit    │  │
                                           │  └───────┬────────┘  │
                                           │          │            │
                                           │  ┌───────▼────────┐  │
                                           │  │   SQLite DB    │  │
                                           │  │  (persisted)   │  │
                                           │  └────────────────┘  │
                                           └──────────────────────┘
```

---

## Quick Start

### With Docker (recommended)

```bash
git clone https://github.com/yourusername/codesentinel
cd codesentinel

# Set your API key
export ANTHROPIC_API_KEY=your_key_here

# Build and run
docker compose up --build
```

Open http://localhost:8000

### Local Development

```bash
pip install -r requirements.txt

export ANTHROPIC_API_KEY=your_key_here

uvicorn app.main:app --reload --port 8000
```

---

## API Reference

### `POST /api/review`
Submit code for evaluation.

```json
{
  "code": "def foo(): pass",
  "language": "Python",
  "context": "Optional description of what this code does"
}
```

**Response:**
```json
{
  "id": 1,
  "scores": {
    "overall": 6.25,
    "correctness": 7,
    "security": 4,
    "performance": 6,
    "scalability": 8
  },
  "primary_review": { ... },
  "meta_evaluation": {
    "review_quality_score": 9,
    "missed_issues": ["Missing rate limiting"],
    "verdict": "Code is functional but has exploitable security gaps.",
    "confidence": "high"
  },
  "created_at": "2024-01-15T12:34:56"
}
```

### `GET /api/history`
Returns the last 20 evaluation records.

### `GET /api/review/{id}`
Returns full details of a specific review.

### `GET /health`
Health check endpoint.

---

## Running Tests

```bash
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

---

## Design Decisions

**Why two LLM passes?**
Single-pass reviews suffer from LLM overconfidence. The meta-evaluation pass catches hallucinated issues, missed vulnerabilities, and poorly calibrated scores — making the pipeline more reliable than any single model call.

**Why SQLite?**
Zero-dependency persistence for a portfolio project. Trivially swappable for PostgreSQL in production via a single connection string change.

**Why FastAPI?**
Async-native, auto-generates OpenAPI docs at `/docs`, and integrates cleanly with Pydantic for structured LLM output validation.

---

## Tech Stack

- **FastAPI** — async Python backend
- **Anthropic Claude API** — LLM evaluation engine
- **SQLite** — evaluation persistence
- **Docker + docker-compose** — containerized deployment
- **GitHub Actions** — CI pipeline with build + smoke test

---

## License

MIT
