"""
Code Review Environment — OpenEnv compliant
Each episode presents 5 code snippets. The agent reviews each one:
  - APPROVE or REJECT
  - Assign severity (optional but rewarded)
  - Add a comment (optional but rewarded)

Scoring (per step):
  0.90  Perfect: correct action + correct severity + includes comment
  0.88  Near-perfect: correct action on easy/medium, missed severity
  0.70–0.87  Partial: correct action on hard, incomplete explanation/severity
  0.50  Cautious false negative: rejected safe code
  0.30  Missed bug: ignored a real vulnerability
  0.15  False positive: flagged safe code as vulnerable
  0.10  Catastrophic: approved a vulnerable snippet

Trajectory grader modifiers (applied after averaging):
  approve_bug_penalty: -0.40 (easy) / -0.50 (medium) / -0.60 (hard)
  consistency_bonus:   +0.05 (easy) / +0.10 (medium) / +0.15 (hard)  if ≥80% correct
  explanation_bonus:   +0.03 (easy) / +0.07 (medium) / +0.10 (hard)  if ≥80% perfect
"""

import uuid
import random
from typing import List, Optional, Dict, Any

from models import (
    ReviewAction, SeverityLevel, CodeSnippet,
    ReviewObservation, ReviewState,
)

# ── Snippet Library ────────────────────────────────────────────────────────────
# Each entry: (language, code, is_vulnerable, vuln_type, correct_severity, difficulty)

_SNIPPETS: List[tuple] = [
    # ── EASY vulnerable ──────────────────────────────────────────────────────
    ("python",
     'query = "SELECT * FROM users WHERE id = " + user_id\ncursor.execute(query)',
     True, "SQL_INJECTION", SeverityLevel.CRITICAL, "easy"),

    ("javascript",
     'document.getElementById("output").innerHTML = userInput;',
     True, "XSS", SeverityLevel.HIGH, "easy"),

    ("python",
     'import pickle\ndata = pickle.loads(user_supplied_bytes)',
     True, "INSECURE_DESERIALIZATION", SeverityLevel.HIGH, "easy"),

    ("python",
     'password = "admin123"\nif user_password == password:\n    grant_access()',
     True, "HARDCODED_CREDENTIALS", SeverityLevel.CRITICAL, "easy"),

    # ── EASY safe ────────────────────────────────────────────────────────────
    ("python",
     'cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))',
     False, None, None, "easy"),

    ("javascript",
     'const output = document.createTextNode(userInput);\ndiv.appendChild(output);',
     False, None, None, "easy"),

    ("python",
     'import hashlib\nhashed = hashlib.sha256(password.encode()).hexdigest()',
     False, None, None, "easy"),

    # ── MEDIUM vulnerable ─────────────────────────────────────────────────────
    ("python",
     'def get_file(path):\n    base = "/var/www/"\n    return open(base + path).read()',
     True, "PATH_TRAVERSAL", SeverityLevel.HIGH, "medium"),

    ("javascript",
     'eval(req.query.cmd);',
     True, "CODE_INJECTION", SeverityLevel.CRITICAL, "medium"),

    ("python",
     'import subprocess\nsubprocess.run(user_cmd, shell=True)',
     True, "COMMAND_INJECTION", SeverityLevel.CRITICAL, "medium"),

    ("python",
     'SERVER_KEY = "sk-prod-xxxxxxxxxxxxxxxxxxxxxxxx"\nrequests.get(api_url, headers={"Authorization": SERVER_KEY})',
     True, "HARDCODED_CREDENTIALS", SeverityLevel.HIGH, "medium"),

    # ── MEDIUM safe ───────────────────────────────────────────────────────────
    ("python",
     'import os\npath = os.path.realpath(os.path.join(base, user_path))\nif path.startswith(base):\n    return open(path).read()',
     False, None, None, "medium"),

    ("python",
     'subprocess.run(["ls", "-la", shlex.quote(user_dir)], shell=False)',
     False, None, None, "medium"),

    # ── HARD vulnerable ───────────────────────────────────────────────────────
    ("python",
     'import yaml\ndata = yaml.load(user_input)  # no Loader specified',
     True, "UNSAFE_DESERIALIZATION", SeverityLevel.HIGH, "hard"),

    ("python",
     'def check_time():\n    token_time = jwt_payload["exp"]\n    if time.time() < token_time:\n        return True  # No constant-time comparison',
     True, "TIMING_ATTACK", SeverityLevel.MEDIUM, "hard"),

    ("javascript",
     'const url = new URL(req.query.redirect);\nif (url.hostname === "myapp.com") res.redirect(req.query.redirect);',
     True, "OPEN_REDIRECT", SeverityLevel.MEDIUM, "hard"),

    # ── HARD safe ─────────────────────────────────────────────────────────────
    ("python",
     'import yaml\ndata = yaml.safe_load(user_input)',
     False, None, None, "hard"),

    ("python",
     'import hmac\nif hmac.compare_digest(token_a, token_b):\n    return True',
     False, None, None, "hard"),
]

# ── Score constants ────────────────────────────────────────────────────────────
_SCORE = {
    "perfect":         0.90,
    "near_perfect":    0.88,
    "partial_hard_hi": 0.87,
    "partial_hard_lo": 0.70,
    "cautious":        0.50,   # rejected safe (overcautious, not wrong)
    "missed_bug":      0.30,
    "false_positive":  0.15,
    "approve_bug":     0.10,   # catastrophic
}

# Strict exclusive bounds — score must NEVER be exactly 0.0 or 1.0
_SCORE_MIN = 0.001
_SCORE_MAX = 0.999


def _clamp(v: float) -> float:
    """Clamp any float to strictly open (0, 1) interval."""
    return max(_SCORE_MIN, min(_SCORE_MAX, float(v)))


class CodeReviewEnvironment:
    """
    OpenEnv-compliant code review environment.
    Each episode = 5 review steps drawn from the snippet library.
    """

    STEPS_PER_EPISODE = 5

    def __init__(self, task_id: str = "easy"):
        """
        Args:
            task_id: "easy", "medium", or "hard"
        """
        self.task_id = task_id
        self.episode_id = ""
        self.step_count = 0
        self._snippets: List[CodeSnippet] = []
        self._step_scores: List[float] = []
        self._step_categories: List[str] = []   # track score type per step
        self._current_snippet: Optional[CodeSnippet] = None

        # Trajectory counters
        self.approve_bug_count = 0
        self.false_positive_count = 0
        self.missed_bug_count = 0
        self.correct_count = 0
        self.perfect_count = 0

    # ── Public API ─────────────────────────────────────────────────────────────

    def reset(self) -> ReviewObservation:
        """Start a new episode. Returns first snippet."""
        self.episode_id = str(uuid.uuid4())[:8]
        self.step_count = 0
        self._step_scores = []
        self._step_categories = []
        self.approve_bug_count = 0
        self.false_positive_count = 0
        self.missed_bug_count = 0
        self.correct_count = 0
        self.perfect_count = 0

        # Sample 5 snippets appropriate for this task_id
        pool = [s for s in _SNIPPETS if s[5] == self.task_id]
        if len(pool) < self.STEPS_PER_EPISODE:
            pool = _SNIPPETS  # fallback to entire pool

        chosen = random.sample(pool, min(self.STEPS_PER_EPISODE, len(pool)))
        self._snippets = [
            CodeSnippet(
                snippet_id=f"{self.episode_id}_step{i}",
                language=s[0],
                code=s[1],
                is_vulnerable=s[2],
                vulnerability_type=s[3],
                correct_severity=s[4],
                difficulty=s[5],
            )
            for i, s in enumerate(chosen)
        ]

        self._current_snippet = self._snippets[0]
        return self._build_obs(done=False)

    def step(self, action: str, severity: Optional[str] = None,
             comment: Optional[str] = None) -> ReviewObservation:
        """
        Process one review decision.

        Args:
            action:   "APPROVE" or "REJECT"
            severity: Optional severity string, e.g. "HIGH"
            comment:  Optional explanation string
        """
        if self._current_snippet is None:
            raise RuntimeError("Call reset() before step()")

        snippet = self._current_snippet
        score, category = self._score_step(action, severity, comment, snippet)
        score = _clamp(score)  # enforce strict (0,1) on every raw step score

        self._step_scores.append(score)
        self._step_categories.append(category)
        self.step_count += 1

        # Update trajectory counters
        if category == "approve_bug":
            self.approve_bug_count += 1
        elif category == "false_positive":
            self.false_positive_count += 1
        elif category == "missed_bug":
            self.missed_bug_count += 1
        elif category in ("perfect", "near_perfect", "partial_hard"):
            self.correct_count += 1
            if category == "perfect":
                self.perfect_count += 1
        elif category == "cautious":
            self.correct_count += 1  # not wrong, counts as "not incorrect"

        done = self.step_count >= self.STEPS_PER_EPISODE

        if not done and self.step_count < len(self._snippets):
            self._current_snippet = self._snippets[self.step_count]
        else:
            self._current_snippet = None

        return self._build_obs(done=done, reward=score,
                               grader_score=self.grader_score if done else None)

    # ── Scoring ────────────────────────────────────────────────────────────────

    def _score_step(self, action: str, severity: Optional[str],
                    comment: Optional[str], snippet: CodeSnippet) -> tuple:
        """Returns (raw_score, category_name)."""
        is_reject = action.upper() == "REJECT"
        is_approve = action.upper() == "APPROVE"
        has_comment = bool(comment and len(comment.strip()) > 5)

        # Severity match
        sev_correct = False
        if severity and snippet.correct_severity:
            sev_correct = severity.upper() == snippet.correct_severity.value

        if snippet.is_vulnerable:
            if is_approve:
                # Catastrophic: shipped a bug
                return (_SCORE["approve_bug"], "approve_bug")

            # REJECT on a vulnerable snippet — how well?
            if snippet.difficulty == "easy":
                if sev_correct and has_comment:
                    return (_SCORE["perfect"], "perfect")
                else:
                    return (_SCORE["near_perfect"], "near_perfect")
            elif snippet.difficulty == "medium":
                if sev_correct and has_comment:
                    return (_SCORE["perfect"], "perfect")
                else:
                    return (_SCORE["near_perfect"], "near_perfect")
            else:  # hard
                if sev_correct and has_comment:
                    return (_SCORE["partial_hard_hi"], "partial_hard")
                elif sev_correct or has_comment:
                    return (round(random.uniform(0.75, 0.83), 2), "partial_hard")
                else:
                    return (_SCORE["partial_hard_lo"], "partial_hard")

        else:  # safe code
            if is_reject:
                # False positive or cautious
                if snippet.difficulty == "easy":
                    return (_SCORE["false_positive"], "false_positive")
                else:
                    return (_SCORE["cautious"], "cautious")
            else:
                # Correctly approved safe code
                if has_comment:
                    return (_SCORE["perfect"], "perfect")
                else:
                    return (_SCORE["near_perfect"], "near_perfect")

    # ── Trajectory Grader ─────────────────────────────────────────────────────

    @property
    def grader_score(self) -> float:
        """Compute final trajectory-adjusted score — always strictly in (0.001, 0.999)."""
        if not self._step_scores:
            return 0.5  # mid-range fallback, never 0 or 1

        n = len(self._step_scores)
        mean = sum(self._step_scores) / n

        score = mean
        score = self._apply_grader_modifiers(score, n)

        # Triple-layer protection against 0.0 or 1.0:
        #   1. round to 4dp to kill floating point noise
        #   2. hard clamp using _SCORE_MIN / _SCORE_MAX
        #   3. final type-safe max/min as safety net
        score = round(score, 4)
        return _clamp(score)

    def _apply_grader_modifiers(self, score: float, n: int) -> float:
        """Apply catastrophic penalties and bonuses based on task tier."""
        tid = self.task_id

        # Penalty tiers
        penalty_per_bug = {"easy": 0.40, "medium": 0.50, "hard": 0.60}[tid]
        consistency_bonus = {"easy": 0.05, "medium": 0.10, "hard": 0.15}[tid]
        explanation_bonus = {"easy": 0.03, "medium": 0.07, "hard": 0.10}[tid]

        # Catastrophic penalty
        if self.approve_bug_count > 0:
            score -= penalty_per_bug * self.approve_bug_count

        # Consistency bonus (≥ 80% steps not catastrophically wrong)
        correct_rate = self.correct_count / max(1, n)
        if correct_rate >= 0.80:
            score += consistency_bonus

        # Explanation bonus (≥ 80% perfect)
        perfect_rate = self.perfect_count / max(1, n)
        if perfect_rate >= 0.80:
            score += explanation_bonus

        return score

    # ── State ─────────────────────────────────────────────────────────────────

    @property
    def state(self) -> ReviewState:
        return ReviewState(
            episode_id=self.episode_id,
            task_id=self.task_id,
            step_count=self.step_count,
            elapsed_time=float(self.step_count),
            step_scores=list(self._step_scores),
            approve_bug_count=self.approve_bug_count,
            false_positive_count=self.false_positive_count,
            missed_bug_count=self.missed_bug_count,
            correct_count=self.correct_count,
            perfect_count=self.perfect_count,
            grader_score=self.grader_score,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_obs(self, done: bool, reward: Optional[float] = None,
                   grader_score: Optional[float] = None) -> ReviewObservation:
        return ReviewObservation(
            snippet=self._current_snippet or (self._snippets[-1] if self._snippets else None),
            step=self.step_count,
            episode_id=self.episode_id,
            done=done,
            reward=reward,
            grader_score=grader_score,
        )
