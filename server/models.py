"""
server/models.py — Type-safe Pydantic & dataclass models for OpenEnv Code Review Environment.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class ReviewAction(Enum):
    """Agent's decision on a code snippet."""
    APPROVE = "APPROVE"
    REJECT  = "REJECT"


class SeverityLevel(Enum):
    """Severity of a flagged vulnerability."""
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class CodeSnippet:
    """A code snippet presented to the agent for review."""
    snippet_id: str
    language: str
    code: str
    is_vulnerable: bool
    vulnerability_type: Optional[str] = None
    correct_severity: Optional[SeverityLevel] = None
    difficulty: str = "easy"


@dataclass
class ReviewObservation:
    """Observation returned by the environment per step."""
    snippet: Optional[CodeSnippet]
    step: int
    episode_id: str
    done: bool = False
    reward: Optional[float] = None
    grader_score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewState:
    """Full episode-level state for grading."""
    episode_id: str
    task_id: str
    step_count: int
    elapsed_time: float
    step_scores: List[float] = field(default_factory=list)
    approve_bug_count: int = 0
    false_positive_count: int = 0
    missed_bug_count: int = 0
    correct_count: int = 0
    perfect_count: int = 0
    grader_score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
