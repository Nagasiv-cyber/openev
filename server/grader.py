"""
server/grader.py — OpenEnv-compliant grader functions.

The validator uses Python reflection (inspect.signature) and may call these
with NO arguments. All parameters must have default=None fallbacks.

Package path: openev.server.grader
"""

from __future__ import annotations
from typing import Optional


# ── Clamp helper ──────────────────────────────────────────────────────────────
_SCORE_MIN = 0.10
_SCORE_MAX = 0.99


def _clamp(v: float) -> float:
    """Ensure score is strictly within [0.10, 0.99]."""
    try:
        return max(_SCORE_MIN, min(_SCORE_MAX, float(v)))
    except (TypeError, ValueError):
        return _SCORE_MIN


# ── Grader functions ──────────────────────────────────────────────────────────

def grade_easy(trajectory: Optional[dict] = None) -> float:
    """
    Grade an 'easy' code review episode.
    Accepts a trajectory dict or None (for reflection/probe calls).
    Returns a float in [0.10, 0.99].
    """
    trajectory = trajectory or {}

    # Extract scores from trajectory if present
    step_scores = trajectory.get("step_scores", [])
    approve_bug_count = int(trajectory.get("approve_bug_count", 0))

    if not step_scores:
        return _SCORE_MIN  # safe minimum on probe

    mean = sum(step_scores) / len(step_scores)

    # Easy penalty: -0.40 per approved bug
    if approve_bug_count > 0:
        mean -= 0.40 * approve_bug_count

    return _clamp(mean)


def grade_medium(trajectory: Optional[dict] = None) -> float:
    """
    Grade a 'medium' code review episode.
    Accepts a trajectory dict or None (for reflection/probe calls).
    Returns a float in [0.10, 0.99].
    """
    trajectory = trajectory or {}

    step_scores = trajectory.get("step_scores", [])
    approve_bug_count = int(trajectory.get("approve_bug_count", 0))

    if not step_scores:
        return _SCORE_MIN

    mean = sum(step_scores) / len(step_scores)

    # Medium penalty: -0.50 per approved bug
    if approve_bug_count > 0:
        mean -= 0.50 * approve_bug_count

    return _clamp(mean)


def grade_hard(trajectory: Optional[dict] = None) -> float:
    """
    Grade a 'hard' code review episode.
    Accepts a trajectory dict or None (for reflection/probe calls).
    Returns a float in [0.10, 0.99].
    """
    trajectory = trajectory or {}

    step_scores = trajectory.get("step_scores", [])
    approve_bug_count = int(trajectory.get("approve_bug_count", 0))

    if not step_scores:
        return _SCORE_MIN

    mean = sum(step_scores) / len(step_scores)

    # Hard penalty: -0.60 per approved bug
    if approve_bug_count > 0:
        mean -= 0.60 * approve_bug_count

    return _clamp(mean)
