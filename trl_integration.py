"""
OpenEnv Trading Environment + TRL Integration Example

This demonstrates how to train a language model to make trading decisions
using the GRPO (Group Relative Policy Optimization) algorithm from TRL.
"""

from environment import TradingEnvironment
from models import TradingAction, TradeAction, TradingObservation
from typing import Dict, Any, List
import json


# ============================================================================
# EXAMPLE 1: Trading Action Parsing
# ============================================================================

def parse_model_output_to_action(model_output: str) -> TradingAction:
    """
    Parse language model output to trading action.
    
    Example outputs:
    "I should BUY 0.5 BTC/USD because of arbitrage opportunity"
    "No action needed, HOLD"
    "SELL 0.1 ETH/USD due to profit taking"
    
    Returns:
        TradingAction
    """
    output_upper = model_output.upper()
    
    # Detect action
    if "BUY" in output_upper:
        action = TradeAction.BUY
    elif "SELL" in output_upper:
        action = TradeAction.SELL
    elif "SHORT" in output_upper:
        action = TradeAction.SHORT
    elif "CLOSE" in output_upper:
        action = TradeAction.CLOSE_SHORT
    else:
        action = TradeAction.HOLD
    
    # Extract quantity (simple parsing)
    quantity = 0.0
    words = output_upper.split()
    for i, word in enumerate(words):
        if word in ["BUY", "SELL", "SHORT"]:
            # Next word might be quantity
            if i + 1 < len(words):
                try:
                    quantity = float(words[i + 1])
                except:
                    quantity = 0.1  # Default
    
    # Extract asset pair
    asset_pair = "BTC/USD"  # Default
    for pair in ["BTC/USD", "ETH/USD", "SOL/USD", "AAPL/USD", "GOLD/USD"]:
        if pair in output_upper:
            asset_pair = pair
            break
    
    return TradingAction(
        action=action,
        asset_pair=asset_pair,
        quantity=max(0, quantity),
    )


# ============================================================================
# EXAMPLE 2: Observation to Prompt Conversion
# ============================================================================

def format_observation_as_prompt(obs: TradingObservation, portfolio_value: float) -> str:
    """
    Convert trading observation to natural language prompt for model.
    
    This allows language models to understand the trading state
    in terms they were trained on.
    """
    
    prompt = f"""
=== TRADING STATE ===
Current Portfolio Value: ${portfolio_value:,.2f}
P&L: ${obs.pnl:,.2f} ({obs.pnl_percent:.2f}%)

=== MARKET DATA ===
"""
    
    # Add market snapshots
    for snap in obs.market_snapshots:
        prompt += f"\n{snap.asset_pair}:\n"
        prompt += f"  Bid: ${snap.bid_price:,.2f}\n"
        prompt += f"  Ask: ${snap.ask_price:,.2f}\n"
        prompt += f"  Spread: {snap.spread:.4f} ({(snap.spread/snap.mid_price)*100:.3f}%)\n"
    
    # Add portfolio positions
    prompt += "\n=== YOUR POSITIONS ===\n"
    for asset, quantity in obs.portfolio.positions.items():
        if quantity > 0:
            prompt += f"{asset}: {quantity:.4f} units\n"
    prompt += f"Cash: ${obs.portfolio.cash:,.2f}\n"
    
    # Add arbitrage opportunities
    if obs.arbitrage_opportunities:
        prompt += "\n=== ARBITRAGE OPPORTUNITIES ===\n"
        for i, arb in enumerate(obs.arbitrage_opportunities[:3]):  # Top 3
            prompt += f"\nOpportunity {i+1}:\n"
            prompt += f"  Asset: {arb['asset_pair']}\n"
            prompt += f"  Buy at: ${arb['buy_price']:,.2f}\n"
            prompt += f"  Sell at: ${arb['sell_price']:,.2f}\n"
            prompt += f"  Profit: {arb['spread_percent']:.3f}%\n"
    else:
        prompt += "\n=== NO ARBITRAGE OPPORTUNITIES ===\n"
    
    prompt += "\nWhat is your next trading action?\n"
    
    return prompt


# ============================================================================
# EXAMPLE 3: Rollout Function for TRL
# ============================================================================

def create_trading_rollout_func(num_steps: int = 100):
    """
    Create a rollout function compatible with TRL GRPOTrainer.
    
    This function:
    1. Takes a list of prompts
    2. Generates model completions (trading actions)
    3. Executes actions in the trading environment
    4. Collects rewards
    5. Returns structured data for training
    
    Args:
        num_steps: Max steps per episode
    
    Returns:
        Rollout function
    """
    
    def rollout_func(prompts: List[str], trainer=None, **kwargs):
        """
        Execute one rollout (episode) for each prompt.
        
        In actual training, this would:
        - Use trainer.generate() for model completions
        - Execute actions in environment
        - Collect multi-signal rewards
        
        For this example, we'll show the structure.
        """
        
        prompt_ids = []
        completion_ids = []
        logprobs = []
        
        # Reward signals
        rewards_pnl = []
        rewards_arbitrage = []
        rewards_sharpe = []
        
        for prompt_text in prompts:
            # Initialize environment
            env = TradingEnvironment(initial_cash=100000.0, num_assets=3)
            obs = env.reset()
            
            episode_pnl = 0
            episode_arb_captured = 0
            episode_returns = []
            
            for step in range(num_steps):
                if obs.done:
                    break
                
                # In real training:
                # generated = trainer.generate(
                #     prompt_text,
                #     max_new_tokens=100,
                # )
                # action_text = generated.text
                
                # For demo, use fixed strategy
                if obs.arbitrage_opportunities:
                    arb = obs.arbitrage_opportunities[0]
                    action_text = f"BUY 0.1 {arb['asset_pair']}"
                else:
                    action_text = "HOLD"
                
                # Parse action
                action = parse_model_output_to_action(action_text)
                
                # Execute
                obs = env.step(action)
                
                # Track episode metrics
                episode_pnl = obs.pnl
                episode_arb_captured += len(obs.arbitrage_opportunities)
                episode_returns.append(obs.pnl or 0)
            
            # Compute returns
            final_pnl = obs.pnl or 0
            final_arb = env.state.arbitrage_captured
            
            # Calculate Sharpe ratio (simple version)
            if episode_returns:
                mean_return = sum(episode_returns) / len(episode_returns)
                if mean_return != 0:
                    variance = sum((r - mean_return) ** 2 for r in episode_returns) / len(episode_returns)
                    sharpe = mean_return / (variance ** 0.5) if variance > 0 else 0
                else:
                    sharpe = 0
            else:
                sharpe = 0
            
            # Store results
            # In real implementation: extract from generated output
            prompt_ids.append([0] * 100)  # Placeholder
            completion_ids.append([0] * 100)  # Placeholder
            logprobs.append([0.0] * 100)  # Placeholder
            
            rewards_pnl.append(final_pnl / 100000)  # Normalize
            rewards_arbitrage.append(min(final_arb / 100, 1.0))  # Cap at 1.0
            rewards_sharpe.append(sharpe)
        
        return {
            "prompt_ids": prompt_ids,
            "completion_ids": completion_ids,
            "logprobs": logprobs,
            "rewards_pnl": rewards_pnl,
            "rewards_arbitrage": rewards_arbitrage,
            "rewards_sharpe": rewards_sharpe,
        }
    
    return rollout_func


# ============================================================================
# EXAMPLE 4: Reward Functions for TRL
# ============================================================================

def reward_pnl(completions, **kwargs):
    """Reward based on profit/loss"""
    return kwargs.get("rewards_pnl", [0.0] * len(completions))


def reward_arbitrage(completions, **kwargs):
    """Reward based on arbitrage opportunities captured"""
    return kwargs.get("rewards_arbitrage", [0.0] * len(completions))


def reward_sharpe(completions, **kwargs):
    """Reward based on risk-adjusted returns (Sharpe ratio)"""
    return kwargs.get("rewards_sharpe", [0.0] * len(completions))


# ============================================================================
# EXAMPLE 5: TRL Training Code
# ============================================================================

def setup_trl_training():
    """
    Example of how to set up TRL GRPOTrainer for trading.
    
    Note: This is pseudocode - requires TRL library installed.
    """
    
    code = '''
from trl import GRPOConfig, GRPOTrainer
from transformers import AutoModelForCausalLM, AutoTokenizer
from datasets import Dataset

# Configuration
config = GRPOConfig(
    # Training parameters
    num_train_epochs=3,
    learning_rate=5e-6,
    per_device_train_batch_size=1,
    gradient_accumulation_steps=64,
    
    # Generation parameters
    max_completion_length=128,
    max_prompt_length=2048,
    num_generations=2,
    
    # Infrastructure
    use_vllm=True,
    vllm_mode="colocate",
    
    # Output
    output_dir="trading-agent-grpo",
    logging_steps=1,
    save_steps=10,
)

# Load model and tokenizer
model = "Qwen/Qwen3-1.7B"  # Or any other model
tokenizer = AutoTokenizer.from_pretrained(model)

# Create training dataset
dataset = Dataset.from_dict({
    "prompt": [
        "Make a trading decision based on market conditions."
        for _ in range(1000)
    ]
})

# Create trainer
trainer = GRPOTrainer(
    model=model,
    processing_class=tokenizer,
    reward_funcs=[
        reward_pnl,
        reward_arbitrage,
        reward_sharpe,
    ],
    train_dataset=dataset,
    args=config,
    rollout_func=create_trading_rollout_func(num_steps=100),
)

# Train!
trainer.train()

# Save and push to Hub
trainer.save_model("trading-agent-grpo")
trainer.push_to_hub()
'''
    
    return code


# ============================================================================
# EXAMPLE 6: Live Trading with Trained Model
# ============================================================================

def deploy_trained_model(model_name: str):
    """
    Example of using a trained model for live trading.
    """
    
    code = f'''
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from client import TradingEnvClient
from models import TradingAction

# Load trained model
model = AutoModelForCausalLM.from_pretrained(
    "{model_name}",
    device_map="auto",
    torch_dtype=torch.float16,
)
tokenizer = AutoTokenizer.from_pretrained("{model_name}")

# Connect to live environment
env = TradingEnvClient(base_url="https://trading-env.example.com")

# Trading loop
obs = env.reset()

for step in range(1000):
    # Format observation as prompt
    prompt = format_observation_as_prompt(obs, obs.net_worth)
    
    # Generate action
    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
    outputs = model.generate(**inputs, max_new_tokens=128)
    action_text = tokenizer.decode(outputs[0])
    
    # Parse and execute
    action = parse_model_output_to_action(action_text)
    obs = env.step(action)
    
    print(f"Step {{step}}: {{action.action.name}} {{action.asset_pair}} - P&L: ${{obs.pnl:.2f}}")
    
    if obs.done:
        break

# Summary
state = env.state()
print(f"\\nTrading Summary:")
print(f"  Total Trades: {{state.num_trades}}")
print(f"  Win Rate: {{state.win_rate:.1%}}")
print(f"  Arbitrage Captured: {{state.arbitrage_captured}}")
print(f"  Total P&L: ${{obs.pnl:.2f}}")
'''
    
    return code


# ============================================================================
# DEMONSTRATION
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("OpenEnv Trading Environment + TRL Integration Examples")
    print("=" * 80)
    
    # Example 1: Parse outputs
    print("\n### Example 1: Model Output Parsing ###\n")
    outputs = [
        "I should BUY 0.5 BTC/USD because of strong arbitrage opportunity",
        "HOLD - no clear trading signal",
        "SELL 0.2 ETH/USD to take profits",
    ]
    
    for output in outputs:
        action = parse_model_output_to_action(output)
        print(f"Model: \"{output}\"")
        print(f"  → Action: {action.action.name} {action.asset_pair} x{action.quantity}\n")
    
    # Example 2: Format observations
    print("\n### Example 2: Observation Formatting ###\n")
    env = TradingEnvironment()
    obs = env.reset()
    
    prompt = format_observation_as_prompt(obs, obs.net_worth)
    print(prompt[:500] + "...\n")
    
    # Example 3: Show TRL setup
    print("\n### Example 3: TRL Training Setup ###\n")
    print(setup_trl_training()[:500] + "...\n")
    
    # Example 4: Show deployment
    print("\n### Example 4: Live Trading with Trained Model ###\n")
    print(deploy_trained_model("username/trading-agent-grpo")[:500] + "...\n")
    
    print("=" * 80)
    print("Ready for Integration with TRL!")
    print("=" * 80)
