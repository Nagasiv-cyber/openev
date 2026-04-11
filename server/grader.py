"""
server/grader.py — OpenEnv grader functions for the Code Review environment.

IMPORTANT: All functions must accept trajectory=None so they survive
Python reflection / parameterless invocations by the cloud validator.

Package path: openev.server.grader
"""

from __future__ import annotations
from typing import Optional

_SCORE_MIN = 0.10
_SCORE_MAX = 0.99


def _clamp(v: float) -> float:
    try:
        return max(_SCORE_MIN, min(_SCORE_MAX, float(v)))
    except (TypeError, ValueError):
        return _SCORE_MIN


def _compute(trajectory: dict, penalty: float) -> float:
    step_scores = trajectory.get("step_scores", [])
    approve_bug_count = int(trajectory.get("approve_bug_count", 0))
    correct_count = int(trajectory.get("correct_count", 0))
    perfect_count = int(trajectory.get("perfect_count", 0))

    if not step_scores:
        return _SCORE_MIN

    n = len(step_scores)
    score = sum(step_scores) / n

    if approve_bug_count > 0:
        score -= penalty * approve_bug_count

    # Consistency bonus
    if correct_count / max(1, n) >= 0.80:
        score += 0.05

    # Explanation bonus
    if perfect_count / max(1, n) >= 0.80:
        score += 0.03

    return _clamp(round(score, 4))


def grade_easy(trajectory: Optional[dict] = None) -> float:
    """
    Grade an easy-tier code review episode.
    Returns a float in [0.10, 0.99].
    """
    return _compute(trajectory or {}, penalty=0.40)


def grade_medium(trajectory: Optional[dict] = None) -> float:
    """
    Grade a medium-tier code review episode.
    Returns a float in [0.10, 0.99].
    """
    return _compute(trajectory or {}, penalty=0.50)


def grade_hard(trajectory: Optional[dict] = None) -> float:
    """
    Grade a hard-tier code review episode.
    Returns a float in [0.10, 0.99].
    """
    return _compute(trajectory or {}, penalty=0.60)
