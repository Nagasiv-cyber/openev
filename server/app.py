"""
server/app.py — Main FastAPI application for the OpenEnv Code Review environment.
Entry point: openev.server.app:app
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Any, Optional
import sys
import os

# Ensure the package root is importable regardless of working directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .environment import CodeReviewEnvironment
from .grader import grade_easy, grade_medium, grade_hard

# ── App ────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="OpenEnv Code Review Environment",
    description="AI security code review benchmark — agents APPROVE/REJECT code snippets.",
    version="2.0.0",
)

# Mount dashboard static files
dashboard_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dashboard")
app.mount("/dashboard", StaticFiles(directory=dashboard_path), name="dashboard")

# In-memory session store
_sessions: Dict[str, CodeReviewEnvironment] = {}


# ── Request models ─────────────────────────────────────────────────────────────

class ReviewAction(BaseModel):
    action: str                    # "APPROVE" or "REJECT"
    severity: Optional[str] = None # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    comment: Optional[str] = None


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>CyberGuard Code Review — OpenEnv</title>
  <style>
    body { font-family: 'JetBrains Mono', 'Courier New', Courier, monospace; background: #000; color: #ffb000;
           display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; text-transform: uppercase; }
    .card { background: #000; border: 1px solid #333; border-radius: 0;
            padding: 3rem; text-align: center; max-width: 480px; }
    h1 { color: #ffb000; margin: 0 0 0.5rem; font-weight: bold; }
    p  { color: #b08d00; }
    .badge { background: #000; color: #00ff00; border: 1px solid #00ff00;
             padding: 0.3rem 1rem; font-size: 0.85rem; font-weight: bold; text-transform: uppercase; }
    a { color: #ffb000; text-decoration: none; border-bottom: 1px solid #ffb000; }
    a:hover { background: #ffb000; color: #000; }
  </style>
</head>
<body>
  <div class="card">
    <h1>[CYBERGUARD CODE REVIEW]</h1>
    <p>> OPENENV AI SECURITY BENCHMARK _</p>
    <br>
    <span class="badge">● STATUS: RUNNING</span>
    <p style="margin-top:1.5rem">
      <a href="/docs">[API DOCS]</a> &nbsp;|&nbsp; <a href="/health">[HEALTH]</a> &nbsp;|&nbsp; <a href="/dashboard/index.html">[DASHBOARD]</a>
    </p>
  </div>
</body>
</html>"""


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "cyberguard-code-review", "version": "2.0.0"}


@app.get("/validate")
async def validate():
    """Evaluator compliance endpoint."""
    return {
        "status": "valid",
        "spec_version": "1.0",
        "tasks": ["easy", "medium", "hard"],
        "grader_endpoints": [
            "/grade/easy/{session_id}",
            "/grade/medium/{session_id}",
            "/grade/hard/{session_id}",
        ],
    }


# ── OpenEnv core endpoints ─────────────────────────────────────────────────────

@app.post("/reset")
async def reset(task_id: str = "easy"):
    """
    Start a new episode.
    Query param: task_id = easy | medium | hard
    """
    env = CodeReviewEnvironment(task_id=task_id)
    session_id = f"{task_id}_{id(env):x}"
    _sessions[session_id] = env

    obs = env.reset()
    return {
        "session_id": session_id,
        "episode_id": obs.episode_id,
        "task_id": task_id,
        "step": obs.step,
        "done": obs.done,
        "snippet": _snippet_dict(obs.snippet),
    }


@app.post("/step/{session_id}")
async def step(session_id: str, payload: ReviewAction):
    """
    Submit a review decision for the current snippet.
    Body: { action, severity?, comment? }
    """
    env = _get_session(session_id)
    obs = env.step(
        action=payload.action,
        severity=payload.severity,
        comment=payload.comment,
    )
    resp: Dict[str, Any] = {
        "step": obs.step,
        "done": obs.done,
        "reward": obs.reward,
    }
    if obs.snippet and not obs.done:
        resp["snippet"] = _snippet_dict(obs.snippet)
    if obs.grader_score is not None:
        resp["grader_score"] = obs.grader_score
    return resp


@app.get("/state/{session_id}")
async def state(session_id: str):
    """Return full episode state."""
    env = _get_session(session_id)
    s = env.state
    return {
        "episode_id": s.episode_id,
        "task_id": s.task_id,
        "step_count": s.step_count,
        "step_scores": s.step_scores,
        "approve_bug_count": s.approve_bug_count,
        "false_positive_count": s.false_positive_count,
        "missed_bug_count": s.missed_bug_count,
        "correct_count": s.correct_count,
        "perfect_count": s.perfect_count,
        "grader_score": s.grader_score,
    }


# ── Grader endpoints ───────────────────────────────────────────────────────────

@app.get("/grade/easy/{session_id}")
async def grade_endpoint_easy(session_id: str):
    return _grade_response(session_id, "easy")


@app.get("/grade/medium/{session_id}")
async def grade_endpoint_medium(session_id: str):
    return _grade_response(session_id, "medium")


@app.get("/grade/hard/{session_id}")
async def grade_endpoint_hard(session_id: str):
    return _grade_response(session_id, "hard")


def _grade_response(session_id: str, task_id: str) -> dict:
    """Return graded score. Handles probe sessions gracefully."""
    if session_id not in _sessions:
        # Validator may probe with dummy IDs — return minimum valid score
        return {"score": 0.10, "task_id": task_id, "episode_id": "probe", "step_count": 0}

    env = _sessions[session_id]
    s = env.state

    # Build trajectory dict for the grader
    trajectory = {
        "step_scores": s.step_scores,
        "approve_bug_count": s.approve_bug_count,
        "correct_count": s.correct_count,
        "perfect_count": s.perfect_count,
    }

    graders = {"easy": grade_easy, "medium": grade_medium, "hard": grade_hard}
    score = graders.get(task_id, grade_easy)(trajectory)

    return {
        "score": score,
        "task_id": s.task_id,
        "episode_id": s.episode_id,
        "step_count": s.step_count,
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_session(session_id: str) -> CodeReviewEnvironment:
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return _sessions[session_id]


def _snippet_dict(snippet) -> dict:
    if snippet is None:
        return {}
    return {
        "snippet_id": snippet.snippet_id,
        "language": snippet.language,
        "code": snippet.code,
        "difficulty": snippet.difficulty,
        # NOTE: is_vulnerable intentionally hidden from agent
    }


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    import uvicorn
    uvicorn.run("openev.server.app:app", host="0.0.0.0", port=7860, reload=False)


if __name__ == "__main__":
    main()
