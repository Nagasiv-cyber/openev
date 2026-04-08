"""
inference.py — OpenEnv compliant agent using ZERO third-party dependencies.
All HTTP calls use Python stdlib only (urllib / http.client).
"""
import os
import json
import urllib.request
import urllib.parse
import urllib.error

# ── Environment variables injected by the OpenEnv validator ──────────────────
API_BASE_URL = os.environ["API_BASE_URL"]        # LiteLLM proxy URL (required)
API_KEY      = os.environ["API_KEY"]             # LiteLLM proxy key (required)
MODEL_NAME   = os.environ.get("MODEL_NAME", "gpt-4-turbo")
ENV_BASE_URL = os.environ.get("ENV_BASE_URL", "http://localhost:8000")


# ── Stdlib HTTP helpers ───────────────────────────────────────────────────────

def _http_post(url: str, payload: dict, headers: dict | None = None, timeout: int = 30) -> dict:
    data = json.dumps(payload).encode()
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _http_get(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _query_llm(prompt: str) -> str:
    """Call the validator's LiteLLM proxy using stdlib only."""
    url = f"{API_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
    }
    headers = {"Authorization": f"Bearer {API_KEY}"}
    resp = _http_post(url, payload, headers=headers)
    return resp["choices"][0]["message"]["content"].strip()


# ── Main inference loop ───────────────────────────────────────────────────────

def run_inference(task_id: str = "survival"):
    """Run inference loop compliant with OpenEnv specifications."""
    print("[START]")

    # Reset environment
    try:
        reset_url = f"{ENV_BASE_URL}/reset?task_id={urllib.parse.quote(task_id)}"
        obs = _http_post(reset_url, {})
    except Exception as e:
        print(f"Failed to reset environment: {e}")
        return

    session_id = obs.get("session_id")
    if not session_id:
        print("Failed to get session_id")
        return

    done = obs.get("done", False)

    # Inference loop
    while not done:
        print(f"[STEP] {json.dumps(obs)}")

        prompt = f"""You are an advanced quantitative trading agent.
Current observation:
{json.dumps(obs, indent=2)}

You can execute one of the following actions:
- HOLD
- BUY
- SELL

Respond only with a JSON object in this exact format:
{{"action": "BUY", "asset_pair": "BTC/USD", "quantity": 1.0}}"""

        try:
            action_text = _query_llm(prompt)

            # Strip markdown fences if present
            if "```json" in action_text:
                action_text = action_text.split("```json")[1].split("```")[0].strip()
            elif "```" in action_text:
                action_text = action_text.split("```")[1].strip()

            action_dict = json.loads(action_text)
        except Exception:
            # Safe fallback — keeps episode alive without crashing
            action_dict = {"action": "HOLD", "asset_pair": "BTC/USD", "quantity": 0.0}

        # Step the environment
        try:
            step_url = f"{ENV_BASE_URL}/step/{urllib.parse.quote(session_id)}"
            obs = _http_post(step_url, action_dict)
            done = obs.get("done", True)
        except Exception as e:
            print(f"Failed to step environment: {e}")
            break

    # Final state
    try:
        final_state = _http_get(f"{ENV_BASE_URL}/state/{urllib.parse.quote(session_id)}")
    except Exception as e:
        final_state = {"error": str(e)}

    print(f"[END] {json.dumps(final_state)}")


if __name__ == "__main__":
    run_inference("survival")
