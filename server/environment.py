"""
server/environment.py — Core CodeReviewEnvironment logic.

Scoring per step:
  0.90  Perfect: correct action + correct severity + includes comment
  0.88  Near-perfect: correct action, missed severity or comment
  0.70-0.87  Partial: correct on hard, incomplete explanation
  0.50  Cautious: rejected safe code (overcautious)
  0.30  Missed bug: approved a real vulnerability
  0.15  False positive: rejected safe code (easy tasks)
  0.10  Catastrophic: approved a vulnerable snippet

Trajectory modifiers (applied after averaging):
  easy:   approve_bug_penalty=-0.40, consistency_bonus=+0.05, explanation_bonus=+0.03
  medium: approve_bug_penalty=-0.50, consistency_bonus=+0.10, explanation_bonus=+0.07
  hard:   approve_bug_penalty=-0.60, consistency_bonus=+0.15, explanation_bonus=+0.10
"""

import uuid
import random
from typing import List, Optional

from .models import (
    ReviewAction, SeverityLevel, CodeSnippet,
    ReviewObservation, ReviewState,
)

# ── Snippet library ────────────────────────────────────────────────────────────
# (language, code, is_vulnerable, vuln_type, correct_severity, difficulty)
_SNIPPETS: List[tuple] = [
    # EASY — vulnerable
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
    # EASY — safe
    ("python",
     'cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))',
     False, None, None, "easy"),
    ("javascript",
     'const output = document.createTextNode(userInput);\ndiv.appendChild(output);',
     False, None, None, "easy"),
    ("python",
     'import hashlib\nhashed = hashlib.sha256(password.encode()).hexdigest()',
     False, None, None, "easy"),

    # MEDIUM — vulnerable
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
     'SERVER_KEY = "sk-prod-xxxxxxxx"\nrequests.get(api_url, headers={"Authorization": SERVER_KEY})',
     True, "HARDCODED_CREDENTIALS", SeverityLevel.HIGH, "medium"),
    # MEDIUM — safe
    ("python",
     'import os\npath = os.path.realpath(os.path.join(base, user_path))\nif path.startswith(base):\n    return open(path).read()',
     False, None, None, "medium"),
    ("python",
     'subprocess.run(["ls", "-la", shlex.quote(user_dir)], shell=False)',
     False, None, None, "medium"),

    # HARD — vulnerable
    ("python",
     'import yaml\ndata = yaml.load(user_input)  # no Loader specified',
     True, "UNSAFE_DESERIALIZATION", SeverityLevel.HIGH, "hard"),
    ("python",
     'def check_time():\n    token_time = jwt_payload["exp"]\n    if time.time() < token_time:\n        return True  # No constant-time comparison',
     True, "TIMING_ATTACK", SeverityLevel.MEDIUM, "hard"),
    ("javascript",
     'const url = new URL(req.query.redirect);\nif (url.hostname === "myapp.com") res.redirect(req.query.redirect);',
     True, "OPEN_REDIRECT", SeverityLevel.MEDIUM, "hard"),
    # HARD — safe
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
    "cautious":        0.50,
    "missed_bug":      0.30,
    "false_positive":  0.15,
    "approve_bug":     0.10,
}

_SCORE_MIN = 0.10
_SCORE_MAX = 0.99


def _clamp(v: float) -> float:
    return max(_SCORE_MIN, min(_SCORE_MAX, float(v)))


class CodeReviewEnvironment:
    """
    OpenEnv-compliant code review environment.
    Each episode presents 5 code snippets for the agent to APPROVE or REJECT.
    """

    STEPS_PER_EPISODE = 5

    def __init__(self, task_id: str = "easy"):
        self.task_id = task_id
        self.episode_id = ""
        self.step_count = 0
        self._snippets: List[CodeSnippet] = []
        self._step_scores: List[float] = []
        self._step_categories: List[str] = []
        self._current_snippet: Optional[CodeSnippet] = None
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

        pool = [s for s in _SNIPPETS if s[5] == self.task_id]
        if len(pool) < self.STEPS_PER_EPISODE:
            pool = _SNIPPETS  # fallback to all

        chosen = random.sample(pool, min(self.STEPS_PER_EPISODE, len(pool)))
        self._snippets = [
            CodeSnippet(
                snippet_id=f"{self.task_id}_{i}",
                language=s[0], code=s[1],
                is_vulnerable=s[2], vulnerability_type=s[3],
                correct_severity=s[4], difficulty=s[5],
            )
            for i, s in enumerate(chosen)
        ]

        self._current_snippet = self._snippets[0]
        return self._build_obs(done=False)

    def step(self, action: str, severity: Optional[str] = None,
             comment: Optional[str] = None) -> ReviewObservation:
        """Submit a review decision. Returns next observation."""
        if self._current_snippet is None:
            raise RuntimeError("Call reset() before step()")

        score, category = self._score_step(
            self._current_snippet, action, severity, comment
        )
        self._step_scores.append(score)
        self._step_categories.append(category)
        self._update_counters(category)
        self.step_count += 1

        done = self.step_count >= self.STEPS_PER_EPISODE
        if not done:
            self._current_snippet = self._snippets[self.step_count]
        else:
            self._current_snippet = None

        return self._build_obs(done=done, reward=score,
                                grader_score=self.grader_score if done else None)

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

    # ── Scoring ────────────────────────────────────────────────────────────────

    def _score_step(self, snippet: CodeSnippet, action: str,
                    severity: Optional[str], comment: Optional[str]):
        is_reject = action.upper() == "REJECT"
        has_comment = bool(comment and len(comment.strip()) > 3)
        sev_correct = (
            severity is not None and
            snippet.correct_severity is not None and
            severity.upper() == snippet.correct_severity.value
        )

        if snippet.is_vulnerable:
            if not is_reject:
                self.approve_bug_count += 1
                return (_SCORE["approve_bug"], "approve_bug")
            # correctly rejected
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
        else:
            if is_reject:
                if snippet.difficulty == "easy":
                    return (_SCORE["false_positive"], "false_positive")
                else:
                    return (_SCORE["cautious"], "cautious")
            else:
                if has_comment:
                    return (_SCORE["perfect"], "perfect")
                else:
                    return (_SCORE["near_perfect"], "near_perfect")

    def _update_counters(self, category: str):
        if category == "approve_bug":
            pass
        elif category in ("perfect", "near_perfect", "partial_hard"):
            self.correct_count += 1
            if category == "perfect":
                self.perfect_count += 1
        elif category == "false_positive":
            self.false_positive_count += 1
        elif category == "missed_bug":
            self.missed_bug_count += 1

    @property
    def grader_score(self) -> float:
        """Final trajectory-adjusted score, always in [0.10, 0.99]."""
        if not self._step_scores:
            return _SCORE_MIN

        n = len(self._step_scores)
        score = sum(self._step_scores) / n
        score = self._apply_modifiers(score, n)
        return _clamp(round(score, 4))

    def _apply_modifiers(self, score: float, n: int) -> float:
        tid = self.task_id
        penalty  = {"easy": 0.40, "medium": 0.50, "hard": 0.60}.get(tid, 0.40)
        c_bonus  = {"easy": 0.05, "medium": 0.10, "hard": 0.15}.get(tid, 0.05)
        e_bonus  = {"easy": 0.03, "medium": 0.07, "hard": 0.10}.get(tid, 0.03)

        if self.approve_bug_count > 0:
            score -= penalty * self.approve_bug_count

        if self.correct_count / max(1, n) >= 0.80:
            score += c_bonus

        if self.perfect_count / max(1, n) >= 0.80:
            score += e_bonus

        return score

    # ── Internal ───────────────────────────────────────────────────────────────

    def _build_obs(self, done: bool, reward: Optional[float] = None,
                   grader_score: Optional[float] = None) -> ReviewObservation:
        return ReviewObservation(
            snippet=self._current_snippet,
            step=self.step_count,
            episode_id=self.episode_id,
            done=done,
            reward=reward,
            grader_score=grader_score,
        )
