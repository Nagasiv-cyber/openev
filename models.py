"""
Type-safe models for OpenEnv Code Review Environment
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class ReviewAction(Enum):
    """Agent's decision on a code snippet"""
    APPROVE = "APPROVE"  # Mark code as safe
    REJECT  = "REJECT"   # Flag code as buggy/vulnerable


class SeverityLevel(Enum):
    """Severity of flagged vulnerability"""
    LOW      = "LOW"
    MEDIUM   = "MEDIUM"
    HIGH     = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class CodeSnippet:
    """A code snippet presented to the agent for review"""
    snippet_id: str
    language: str          # "python", "javascript", "sql", etc.
    code: str              # The code content
    is_vulnerable: bool    # Ground truth
    vulnerability_type: Optional[str] = None  # e.g. "SQL_INJECTION", "XSS", "BUFFER_OVERFLOW"
    correct_severity: Optional[SeverityLevel] = None
    difficulty: str = "easy"  # "easy", "medium", "hard"


@dataclass
class ReviewObservation:
    """Observation returned by the environment per step"""
    snippet: CodeSnippet
    step: int
    episode_id: str
    done: bool = False
    reward: Optional[float] = None
    grader_score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewState:
    """Episode-level state and grader data"""
    episode_id: str
    task_id: str
    step_count: int
    elapsed_time: float

    # Per-step score history (raw, before trajectory modifier)
    step_scores: List[float] = field(default_factory=list)

    # Aggregate counters
    approve_bug_count: int = 0    # Catastrophic: approved a vulnerable snippet
    false_positive_count: int = 0 # Annoying: rejected safe snippet
    missed_bug_count: int = 0     # Bad: ignored a real vulnerability
    correct_count: int = 0        # Correct decisions
    perfect_count: int = 0        # Perfect (correct + severity + comment)

    grader_score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
