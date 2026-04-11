"""
inference.py — OpenEnv Code Review Agent
Reads API credentials from environment variables and runs a full episode
for each task tier (easy / medium / hard).

Required environment variables:
  API_BASE_URL  — LiteLLM proxy base URL
  HF_TOKEN      — Bearer token / API key
  MODEL_NAME    — Model identifier (default: gpt-4o-mini)
  ENV_BASE_URL  — Environment server URL (default: http://localhost:7860)

Log format (strictly required by validator):
  [START] task=<task_id>
  [STEP] step=<n> action=<APPROVE|REJECT> reward=<float>
  [END] task=<task_id> score=<float>
"""

import os
import sys
import json
import time

from openai import OpenAI

# ── Config ─────────────────────────────────────────────────────────────────────

API_BASE_URL = os.environ.get("API_BASE_URL", "").rstrip("/")
HF_TOKEN     = os.environ.get("HF_TOKEN", "")
MODEL_NAME   = os.environ.get("MODEL_NAME", "gpt-4o-mini")
ENV_BASE_URL = os.environ.get("ENV_BASE_URL", "http://localhost:7860").rstrip("/")

if not API_BASE_URL or not HF_TOKEN:
    print("[WARNING] API_BASE_URL or HF_TOKEN not set — running in fallback mode.")

# Build the OpenAI client pointing at the LiteLLM proxy
_llm_base = API_BASE_URL
if _llm_base and not _llm_base.endswith("/v1"):
    _llm_base = f"{_llm_base}/v1"

client = OpenAI(
    base_url=_llm_base or "http://localhost:11434/v1",
    api_key=HF_TOKEN or "fallback",
)

# ── HTTP helpers (stdlib only — no requests dependency needed) ─────────────────

import urllib.request
import urllib.parse
import urllib.error


def _post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


# ── LLM helpers ────────────────────────────────────────────────────────────────

_PROMPT = """\
You are a security code reviewer. Review the following {language} code snippet.

Code:
```{language}
{code}
```

Decide:
- action: "APPROVE" if the code is safe, "REJECT" if it contains a vulnerability.
- severity: If rejecting, one of: "LOW", "MEDIUM", "HIGH", "CRITICAL".
- comment: A one-sentence explanation.

Respond ONLY with valid JSON. Example:
{{"action": "REJECT", "severity": "CRITICAL", "comment": "SQL Injection via string concatenation."}}
"""


def _query_llm(language: str, code: str, retries: int = 3) -> dict:
    prompt = _PROMPT.format(language=language, code=code)
    for attempt in range(1, retries + 1):
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=150,
            )
            raw = resp.choices[0].message.content.strip()
            # Strip markdown fences if present
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0].strip()
            elif "```" in raw:
                raw = raw.split("```")[1].strip()
            decision = json.loads(raw)
            if "action" not in decision:
                decision["action"] = "REJECT"
            decision["action"] = decision["action"].upper()
            return decision
        except Exception as e:
            print(f"[LLM] Attempt {attempt}/{retries} failed: {e}")
            if attempt < retries:
                time.sleep(2 * attempt)

    # Safe fallback — never crash
    return {"action": "REJECT", "severity": "LOW", "comment": "Fallback: LLM unavailable."}


# ── Episode runner ─────────────────────────────────────────────────────────────

def run_episode(task_id: str) -> float:
    """
    Run one full episode for the given task_id.
    Emits [START], [STEP]*, [END] logs.
    Returns final grader score.
    """
    print(f"[START] task={task_id}")

    # Reset
    try:
        obs = _post(f"{ENV_BASE_URL}/reset?task_id={urllib.parse.quote(task_id)}", {})
    except Exception as e:
        print(f"[ERROR] reset failed: {e}")
        print(f"[END] task={task_id} score=0.10")
        return 0.10

    session_id = obs.get("session_id", "")
    done = obs.get("done", False)
    step_num = 0
    score = 0.10

    # Step loop
    while not done:
        step_num += 1
        snippet = obs.get("snippet", {})
        language = snippet.get("language", "python")
        code = snippet.get("code", "# empty")

        decision = _query_llm(language, code)
        action   = decision.get("action", "REJECT")
        severity = decision.get("severity")
        comment  = decision.get("comment", "")

        try:
            obs = _post(
                f"{ENV_BASE_URL}/step/{urllib.parse.quote(session_id)}",
                {"action": action, "severity": severity, "comment": comment},
            )
            reward = obs.get("reward", 0.0)
            done   = obs.get("done", True)
            print(f"[STEP] step={step_num} action={action} reward={reward:.4f}")
        except Exception as e:
            print(f"[STEP] step={step_num} failed: {e}")
            break

    # Grade
    try:
        grade = _get(
            f"{ENV_BASE_URL}/grade/{urllib.parse.quote(task_id)}/{urllib.parse.quote(session_id)}"
        )
        score = float(grade.get("score", 0.10))
    except Exception as e:
        print(f"[ERROR] grade failed: {e}")
        score = 0.10

    print(f"[END] task={task_id} score={score:.4f}")
    return score


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    results = {}
    for task in ["easy", "medium", "hard"]:
        print(f"\n{'='*50}")
        s = run_episode(task)
        results[task] = s
        print(f"{'='*50}")

    print("\n[SUMMARY]")
    for task, s in results.items():
        print(f"  {task}: {s:.4f}")
