"""
FastAPI Server for Code Review Environment
OpenEnv-compliant endpoints: /reset, /step, /state, /grade
"""

from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import json

from environment import CodeReviewEnvironment

# ============================================================================
# Pydantic Models
# ============================================================================

class ReviewActionPayload(BaseModel):
    """HTTP body for /step — agent's review decision."""
    action: str             # "APPROVE" or "REJECT"
    severity: Optional[str] = None    # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    comment: Optional[str] = None     # Any explanation text


# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="OpenEnv Code Review Environment",
    description="RL environment where agents review code for vulnerabilities.",
    version="2.0.0",
)

# Session store
environments: Dict[str, CodeReviewEnvironment] = {}


# ── Root ──────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>OpenEnv Code Review</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                display: flex; justify-content: center; align-items: center;
                height: 100vh; margin: 0;
                background-color: #0f172a; color: #f8fafc;
            }
            .container {
                text-align: center; padding: 3rem;
                background-color: #1e293b; border-radius: 1rem;
                box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1);
                border: 1px solid #334155;
            }
            h1 { color: #38bdf8; margin-top: 0; font-size: 2.5rem; }
            .subtitle { color: #94a3b8; font-size: 1.1rem; margin-bottom: 2rem; }
            .status {
                display: inline-block; padding: 0.5rem 1rem;
                background-color: rgba(16, 185, 129, 0.1); color: #34d399;
                border: 1px solid rgba(16, 185, 129, 0.2);
                border-radius: 9999px; font-size: 0.875rem; font-weight: 600;
                margin-bottom: 2rem;
            }
            .links { display: flex; gap: 1rem; justify-content: center; }
            a {
                display: inline-block; padding: 0.75rem 1.5rem;
                background-color: #38bdf8; color: #0f172a;
                text-decoration: none; font-weight: 600; border-radius: 0.5rem;
            }
            a:hover { background-color: #7dd3fc; }
            .api-link {
                background-color: transparent;
                border: 1px solid #38bdf8; color: #38bdf8;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 OpenEnv Code Review</h1>
            <div class="subtitle">AI-powered vulnerability detection benchmark</div>
            <div class="status">● API Status: Operational</div>
            <div class="links">
                <a href="/docs">Interactive Docs</a>
                <a href="/health" class="api-link">Health Check</a>
            </div>
        </div>
    </body>
    </html>
    """


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "code-review-environment"}


# ── Reset ─────────────────────────────────────────────────────────────────────

@app.post("/reset")
async def reset(task_id: str = "easy"):
    """
    Reset environment and return the first code snippet.

    Returns:
        session_id, snippet (code, language, snippet_id)
    """
    env = CodeReviewEnvironment(task_id=task_id)
    session_id = f"session_{id(env)}"
    environments[session_id] = env

    obs = env.reset()

    return {
        "session_id": session_id,
        "episode_id": obs.episode_id,
        "step": obs.step,
        "done": obs.done,
        "snippet": _snippet_to_dict(obs.snippet),
    }


# ── Step ──────────────────────────────────────────────────────────────────────

@app.post("/step/{session_id}")
async def step(session_id: str, payload: ReviewActionPayload):
    """
    Submit a review decision for the current snippet.

    Args:
        action:   APPROVE | REJECT
        severity: LOW | MEDIUM | HIGH | CRITICAL (optional, rewards when correct)
        comment:  Any explanation text (optional, rewards when provided + correct)
    """
    if session_id not in environments:
        raise HTTPException(status_code=404, detail="Session not found")

    env = environments[session_id]
    obs = env.step(
        action=payload.action,
        severity=payload.severity,
        comment=payload.comment,
    )

    resp = {
        "step": obs.step,
        "done": obs.done,
        "reward": obs.reward,
    }
    if obs.snippet:
        resp["snippet"] = _snippet_to_dict(obs.snippet)
    if obs.grader_score is not None:
        resp["grader_score"] = obs.grader_score

    return resp


# ── State ─────────────────────────────────────────────────────────────────────

@app.get("/state/{session_id}")
async def state(session_id: str):
    """Get episode state."""
    if session_id not in environments:
        raise HTTPException(status_code=404, detail="Session not found")

    env = environments[session_id]
    s = env.state

    return {
        "episode_id": s.episode_id,
        "task_id": s.task_id,
        "step_count": s.step_count,
        "elapsed_time": s.elapsed_time,
        "step_scores": s.step_scores,
        "approve_bug_count": s.approve_bug_count,
        "false_positive_count": s.false_positive_count,
        "missed_bug_count": s.missed_bug_count,
        "correct_count": s.correct_count,
        "perfect_count": s.perfect_count,
        "grader_score": s.grader_score,
    }


# ── Grade ─────────────────────────────────────────────────────────────────────

@app.get("/grade/easy/{session_id}")
async def easy_grader(session_id: str):
    """OpenEnv easy grade endpoint."""
    return await _process_grade(session_id, "easy")

@app.get("/grade/medium/{session_id}")
async def medium_grader(session_id: str):
    """OpenEnv medium grade endpoint."""
    return await _process_grade(session_id, "medium")

@app.get("/grade/hard/{session_id}")
async def hard_grader(session_id: str):
    """OpenEnv hard grade endpoint."""
    return await _process_grade(session_id, "hard")


async def _process_grade(session_id: str, expected_task_id: str):
    """
    Returns a single score strictly in (0, 1).
    """
    if session_id not in environments:
        raise HTTPException(status_code=404, detail="Session not found")

    env = environments[session_id]
    s = env.state

    # Already clamped to (0.001, 0.999) inside env.grader_score
    score = float(s.grader_score) if s.grader_score is not None else 0.5
    score = max(0.001, min(0.999, score))

    return {
        "score": score,
        "task_id": s.task_id,
        "episode_id": s.episode_id,
        "step_count": s.step_count,
    }


# ── Docs ──────────────────────────────────────────────────────────────────────

@app.get("/docs-info")
async def docs_info():
    return {
        "endpoints": {
            "/health": "GET — health check",
            "/reset?task_id=easy": "POST — start new episode",
            "/step/{session_id}": "POST — submit review decision",
            "/state/{session_id}": "GET — full episode state",
            "/grade/easy/{session_id}": "GET — final easy grader score (0, 1)",
            "/grade/medium/{session_id}": "GET — final medium grader score (0, 1)",
            "/grade/hard/{session_id}": "GET — final hard grader score (0, 1)",
        },
        "actions": ["APPROVE", "REJECT"],
        "severity_levels": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
        "task_ids": ["easy", "medium", "hard"],
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _snippet_to_dict(snippet) -> Dict[str, Any]:
    if snippet is None:
        return {}
    return {
        "snippet_id": snippet.snippet_id,
        "language": snippet.language,
        "code": snippet.code,
        "difficulty": snippet.difficulty,
        # NOTE: is_vulnerable is NOT exposed — agent must infer from code
    }
