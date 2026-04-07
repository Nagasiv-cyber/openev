import os
import json
import requests
from openai import OpenAI

# Environment variables injected by the OpenEnv validator
# DO NOT hardcode these — the validator provides them at runtime
API_BASE_URL = os.environ["API_BASE_URL"]   # LiteLLM proxy URL (required)
API_KEY      = os.environ["API_KEY"]        # LiteLLM proxy key (required)
MODEL_NAME   = os.environ.get("MODEL_NAME", "gpt-4-turbo")
ENV_BASE_URL = os.environ.get("ENV_BASE_URL", "http://localhost:8000")

# Initialize the OpenAI client pointing at the validator's LiteLLM proxy
client = OpenAI(
    base_url=API_BASE_URL,
    api_key=API_KEY,
)


def run_inference(task_id: str = "survival"):
    """Run inference loop compliant with OpenEnv specifications."""

    print("[START]")

    # Reset Environment
    try:
        reset_resp = requests.post(
            f"{ENV_BASE_URL}/reset", params={"task_id": task_id}, timeout=30
        )
        reset_resp.raise_for_status()
        obs = reset_resp.json()
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
        # Emit STEP string strictly containing the observation state
        print(f"[STEP] {json.dumps(obs)}")

        # Format the prompt for the agent
        prompt = f"""
You are an advanced quantitative trading agent.
Current observation:
{json.dumps(obs, indent=2)}

You can execute one of the following actions:
- HOLD
- BUY
- SELL

Respond only with a JSON object in this format:
{{"action": "BUY", "asset_pair": "BTC/USD", "quantity": 1.0}}
"""

        # Query the LLM through the validator's LiteLLM proxy
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            action_text = response.choices[0].message.content.strip()

            # Parse JSON from model output
            if "```json" in action_text:
                action_text = action_text.split("```json")[1].split("```")[0].strip()
            elif "```" in action_text:
                action_text = action_text.split("```")[1].strip()

            action_dict = json.loads(action_text)

        except Exception:
            # Safe fallback — keeps the episode running without crashing
            action_dict = {"action": "HOLD", "asset_pair": "BTC/USD", "quantity": 0.0}

        # Step the environment
        try:
            step_resp = requests.post(
                f"{ENV_BASE_URL}/step/{session_id}", json=action_dict, timeout=30
            )
            step_resp.raise_for_status()
            obs = step_resp.json()
            done = obs.get("done", True)
        except Exception as e:
            print(f"Failed to step environment: {e}")
            break

    # Get final grader score via state evaluation
    try:
        state_resp = requests.get(
            f"{ENV_BASE_URL}/state/{session_id}", timeout=30
        )
        state_resp.raise_for_status()
        final_state = state_resp.json()
    except Exception as e:
        final_state = {"error": str(e)}

    # Emit END string containing the final grader and episode information
    print(f"[END] {json.dumps(final_state)}")


if __name__ == "__main__":
    run_inference("survival")
