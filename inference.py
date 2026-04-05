import os
import json
import requests
import time
from openai import OpenAI

# Required Environment Variables
API_BASE_URL = os.environ.get("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME = os.environ.get("MODEL_NAME", "gpt-4-turbo")
HF_TOKEN = os.environ.get("HF_TOKEN", "dummy-token")
ENV_BASE_URL = os.environ.get("ENV_BASE_URL", "http://localhost:8000")

def run_inference(task_id: str = "survival"):
    """Run inference loop compliant with OpenEnv specifications."""
    
    # Initialize OpenAI Client
    client = OpenAI(
        base_url=API_BASE_URL,
        api_key=HF_TOKEN
    )

    print("[START]")
    
    # Reset Environment
    try:
        reset_resp = requests.post(f"{ENV_BASE_URL}/reset", params={"task_id": task_id})
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
        
        # Query the LLM
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            
            action_text = response.choices[0].message.content.strip()
            
            # Simple fallback if the model doesn't return pure JSON
            if "```json" in action_text:
                action_text = action_text.split("```json")[1].split("```")[0].strip()
            elif "```" in action_text:
                action_text = action_text.split("```")[1].strip()
                
            action_dict = json.loads(action_text)
            
        except Exception as e:
            # Fallback action on failure to keep the loop going safely
            action_dict = {"action": "HOLD", "asset_pair": "BTC/USD", "quantity": 0.0}

        # Step the environment
        try:
            step_resp = requests.post(f"{ENV_BASE_URL}/step/{session_id}", json=action_dict)
            step_resp.raise_for_status()
            obs = step_resp.json()
            done = obs.get("done", True)
        except Exception as e:
            print(f"Failed to step environment: {e}")
            break

    # Get final grader score via state evaluation
    try:
        state_resp = requests.get(f"{ENV_BASE_URL}/state/{session_id}")
        state_resp.raise_for_status()
        final_state = state_resp.json()
    except Exception as e:
        final_state = {"error": str(e)}

    # Emit END string containing the final grader and episode information
    print(f"[END] {json.dumps(final_state)}")


if __name__ == "__main__":
    # In an OpenEnv submission context, this would typically be triggered per-task or with arg parsing
    # Defaulting to the survival task for the baseline run
    run_inference("survival")
