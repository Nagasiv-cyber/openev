"""
OpenEnv Trading Environment - Complete Demonstration

This notebook demonstrates:
1. Type-safe trading environment setup
2. Realistic market simulation with arbitrage detection
3. Training different trading strategies
4. Performance metrics and analysis
5. Production deployment patterns
"""

from environment import TradingEnvironment
from models import TradingAction, TradeAction
import random
from collections import defaultdict
import statistics


# ============================================================================
# PART 1: Understanding the Trading Environment
# ============================================================================

print("=" * 80)
print("PART 1: Trading Environment Overview")
print("=" * 80)
print("""
🎯 What is this environment?

An RL environment for learning quantitative trading strategies, specifically
focused on detecting and capturing arbitrage opportunities.

📊 Features:
- Multi-asset trading (BTC, ETH, SOL, etc.)
- Realistic price movements (geometric Brownian motion)
- Bid-ask spreads that vary by volatility
- Arbitrage opportunity detection
- Portfolio tracking with P&L calculation
- Transaction costs (0.1% per trade)

🤖 Agent Objective:
- Maximize profit by trading when price mismatches exist
- Capture arbitrage opportunities (buy low, sell high)
- Minimize transaction costs
- Learn when NOT to trade

📋 Action Space:
- HOLD: Do nothing
- BUY: Buy asset at ask price
- SELL: Sell asset at bid price
- SHORT: Bet on price decrease (futures)
- CLOSE_SHORT: Close short position

📊 Observation:
- Current bid/ask prices for all assets
- Portfolio state (cash, positions)
- P&L metrics
- Detected arbitrage opportunities
- Market regime (normal, high volatility, low volatility)
""")

# ============================================================================
# PART 2: Basic Usage
# ============================================================================

print("\n" + "=" * 80)
print("PART 2: Basic Usage - Single Episode")
print("=" * 80)

# Initialize environment
env = TradingEnvironment(initial_cash=100000.0, num_assets=3)
print(f"\n✅ Environment initialized with $100,000")

# Reset to start episode
obs = env.reset()
print(f"\n🎬 Episode Reset")
print(f"   Episode ID: {env.state.episode_id}")
print(f"   Market Snapshots: {len(obs.market_snapshots)} assets")

# Show initial market state
print(f"\n📊 Initial Market State:")
for snap in obs.market_snapshots:
    print(f"   {snap.asset_pair:10} | Bid: ${snap.bid_price:10.2f} | Ask: ${snap.ask_price:10.2f} | Spread: {snap.spread:6.2f}")

# Execute a few steps
print(f"\n🔄 Executing 5 Trading Steps...")
for step in range(5):
    # Random action for demo
    action_choice = random.choice([
        TradeAction.HOLD,
        TradeAction.BUY,
        TradeAction.SELL,
    ])
    
    action = TradingAction(
        action=action_choice,
        asset_pair="BTC/USD",
        quantity=0.1 if action_choice != TradeAction.HOLD else 0.0,
    )
    
    obs = env.step(action)
    
    print(f"\n   Step {step + 1}:")
    print(f"      Action: {action.action.name}")
    print(f"      Net Worth: ${obs.net_worth:10.2f}")
    print(f"      P&L: ${obs.pnl:8.2f} ({obs.pnl_percent:6.2f}%)")
    print(f"      Arbitrage Opportunities Found: {len(obs.arbitrage_opportunities)}")
    if obs.arbitrage_opportunities:
        for arb in obs.arbitrage_opportunities[:1]:  # Show first one
            print(f"         - {arb['asset_pair']}: {arb['spread_percent']:.3f}% spread")


# ============================================================================
# PART 3: Arbitrage Detection in Action
# ============================================================================

print("\n" + "=" * 80)
print("PART 3: Arbitrage Detection")
print("=" * 80)

env = TradingEnvironment(initial_cash=100000.0, num_assets=3)
env.reset()

print("""
🔍 Arbitrage opportunities occur when the same asset trades at different prices
   across different exchanges. An agent can profit by:

   1. Buying at the lower price (Exchange B)
   2. Selling at the higher price (Exchange A)
   3. Capturing the difference (spread)

This is "risk-free" profit in theory, but in practice involves:
- Execution risk (prices move between buy/sell)
- Liquidity constraints
- Latency
- Transaction costs
""")

# Run steps and collect arbitrage data
arb_stats = defaultdict(lambda: {"count": 0, "spreads": []})

for _ in range(100):
    action = TradingAction(
        action=TradeAction.HOLD,
        asset_pair="BTC/USD",
        quantity=0.0,
    )
    obs = env.step(action)
    
    for arb in obs.arbitrage_opportunities:
        pair = arb["asset_pair"]
        spread = arb["spread_percent"]
        arb_stats[pair]["count"] += 1
        arb_stats[pair]["spreads"].append(spread)

print(f"\n📊 Arbitrage Statistics (over 100 steps):")
print(f"\n{'Asset Pair':<12} {'Occurrences':<15} {'Avg Spread':<15} {'Max Spread':<15}")
print("-" * 60)

for pair in sorted(arb_stats.keys()):
    stats = arb_stats[pair]
    if stats["spreads"]:
        avg_spread = statistics.mean(stats["spreads"])
        max_spread = max(stats["spreads"])
        print(f"{pair:<12} {stats['count']:<15} {avg_spread:>6.3f}%          {max_spread:>6.3f}%")


# ============================================================================
# PART 4: Trading Policies
# ============================================================================

print("\n" + "=" * 80)
print("PART 4: Trading Policies")
print("=" * 80)

class RandomPolicy:
    """Random trading - baseline strategy"""
    name = "🎲 Random Trader"
    
    def select_action(self, obs):
        action = random.choice([TradeAction.HOLD, TradeAction.BUY, TradeAction.SELL])
        quantity = random.uniform(0.01, 0.5) if action != TradeAction.HOLD else 0.0
        asset = random.choice(["BTC/USD", "ETH/USD", "SOL/USD"])
        
        return TradingAction(action=action, asset_pair=asset, quantity=quantity)


class HoldPolicy:
    """Do-nothing baseline"""
    name = "🛑 Do Nothing"
    
    def select_action(self, obs):
        return TradingAction(action=TradeAction.HOLD, asset_pair="BTC/USD", quantity=0.0)


class ArbitragePolicy:
    """Smart strategy: capture arbitrage when found"""
    name = "🧠 Arbitrage Hunter"
    
    def select_action(self, obs):
        # If arbitrage opportunities exist, buy from cheapest, sell to highest
        if obs.arbitrage_opportunities:
            arb = obs.arbitrage_opportunities[0]  # Take first opportunity
            
            # For simplicity: buy at the lower price
            return TradingAction(
                action=TradeAction.BUY,
                asset_pair=arb["asset_pair"],
                quantity=0.1,
            )
        
        return TradingAction(action=TradeAction.HOLD, asset_pair="BTC/USD", quantity=0.0)


class SmartPolicy:
    """Combination strategy with momentum + arbitrage"""
    name = "📈 Smart Trader"
    
    def __init__(self):
        self.buy_count = 0
    
    def select_action(self, obs):
        # Capture arbitrage if available
        if obs.arbitrage_opportunities and random.random() < 0.7:
            arb = obs.arbitrage_opportunities[0]
            return TradingAction(
                action=TradeAction.BUY,
                asset_pair=arb["asset_pair"],
                quantity=0.1,
            )
        
        # Occasionally take profits
        if self.buy_count > 0 and random.random() < 0.3:
            self.buy_count -= 1
            return TradingAction(
                action=TradeAction.SELL,
                asset_pair="BTC/USD",
                quantity=0.1,
            )
        
        return TradingAction(action=TradeAction.HOLD, asset_pair="BTC/USD", quantity=0.0)


# ============================================================================
# PART 5: Policy Evaluation
# ============================================================================

print("\n" + "=" * 80)
print("PART 5: Policy Evaluation")
print("=" * 80)

def evaluate_policy(policy, num_episodes=5, steps_per_episode=200):
    """Run policy and collect metrics"""
    profits = []
    max_drawdowns = []
    trades_executed = []
    arb_captured = []
    
    for episode in range(num_episodes):
        env = TradingEnvironment(initial_cash=100000.0, num_assets=3)
        obs = env.reset()
        
        for _ in range(steps_per_episode):
            action = policy.select_action(obs)
            obs = env.step(action)
            
            if obs.done:
                break
        
        state = env.state
        profits.append(obs.pnl)
        max_drawdowns.append(state.max_drawdown)
        trades_executed.append(state.num_trades)
        arb_captured.append(state.arbitrage_captured)
    
    return {
        "avg_profit": statistics.mean(profits),
        "avg_drawdown": statistics.mean(max_drawdowns),
        "avg_trades": statistics.mean(trades_executed),
        "avg_arb_captured": statistics.mean(arb_captured),
        "win_rate": sum(1 for p in profits if p > 0) / len(profits),
    }


policies = [
    HoldPolicy(),
    RandomPolicy(),
    ArbitragePolicy(),
    SmartPolicy(),
]

print(f"\n🏆 POLICY COMPARISON")
print(f"\nEvaluating {len(policies)} policies over 5 episodes, 200 steps each...\n")

results = []
for policy in policies:
    metrics = evaluate_policy(policy, num_episodes=5, steps_per_episode=200)
    results.append((policy.name, metrics))
    print(f"✓ {policy.name}")

# Display results
print(f"\n{'Policy':<25} {'Avg Profit':>12} {'Win Rate':>10} {'Avg Trades':>12} {'Arb Captured':>15}")
print("-" * 75)

for name, metrics in sorted(results, key=lambda x: x[1]["avg_profit"], reverse=True):
    medal = "🥇" if metrics["avg_profit"] == max(m[1]["avg_profit"] for m in results) else "  "
    print(f"{medal} {name:<23} ${metrics['avg_profit']:>10.2f}   {metrics['win_rate']:>8.1%}   {metrics['avg_trades']:>10.1f}   {metrics['avg_arb_captured']:>13.1f}")


# ============================================================================
# PART 6: Environment State Tracking
# ============================================================================

print("\n" + "=" * 80)
print("PART 6: Episode State and Metrics")
print("=" * 80)

env = TradingEnvironment(initial_cash=100000.0, num_assets=3)
obs = env.reset()

print(f"\n📋 Available State Metrics:")
state = env.state
print(f"   episode_id: {state.episode_id}")
print(f"   step_count: {state.step_count}")
print(f"   elapsed_time: {state.elapsed_time:.1f} (minutes)")
print(f"   market_volatility: {state.market_volatility:.3f}")
print(f"   trend: {state.trend}")
print(f"   max_drawdown: {state.max_drawdown:.3%}")
print(f"   cumulative_pnl: ${state.cumulative_pnl:.2f}")
print(f"   num_trades: {state.num_trades}")
print(f"   win_rate: {state.win_rate:.1%}")
print(f"   total_arbitrage_found: {state.total_arbitrage_found}")
print(f"   arbitrage_captured: {state.arbitrage_captured}")

print(f"""
💡 These metrics enable:
   ✅ Tracking agent performance
   ✅ Detecting overfitting (win_rate on new data)
   ✅ Measuring risk (max_drawdown)
   ✅ Evaluating strategy quality (arbitrage_captured)
""")


# ============================================================================
# PART 7: Type Safety Benefits
# ============================================================================

print("\n" + "=" * 80)
print("PART 7: Type Safety")
print("=" * 80)

print("""
🛡️ OpenEnv Type Safety = IDE Autocomplete + Compile-Time Checks

Without type safety (traditional RL):
  ✗ obs[0][3] - What is this? (cryptic array access)
  ✗ KeyError at runtime if obs structure changes
  ✗ No IDE autocomplete
  ✗ Refactoring is dangerous

With OpenEnv type safety:
  ✓ obs.market_snapshots[0].bid_price - Crystal clear!
  ✓ IDE autocompletes all available fields
  ✓ Type checker catches errors before runtime
  ✓ Self-documenting code

Example usage:
""")

env = TradingEnvironment()
obs = env.reset()

print(f"""
# Type-safe access
snapshot = obs.market_snapshots[0]
bid = snapshot.bid_price  # IDE knows this exists!
spread = snapshot.spread

# Portfolio access
portfolio = obs.portfolio
cash = portfolio.cash
btc_position = portfolio.positions["BTC/USD"]

# Metrics
pnl = obs.pnl
net_worth = obs.net_worth
arbitrage_opps = obs.arbitrage_opportunities

# All with full IDE support!
""")


# ============================================================================
# PART 8: Production Deployment
# ============================================================================

print("\n" + "=" * 80)
print("PART 8: Production Deployment")
print("=" * 80)

print("""
🚀 Deployment Options:

1. LOCAL DEVELOPMENT
   uvicorn app:app --host 0.0.0.0 --port 8000 --reload

2. DOCKER CONTAINER
   docker build -t trading-env:latest .
   docker run -d -p 8000:8000 trading-env:latest

3. HUGGING FACE SPACES
   git push to https://huggingface.co/spaces/username/trading-env
   Access at: https://username-trading-env.hf.space

4. KUBERNETES CLUSTER
   kubectl apply -f deployment.yaml
   Scales to 1000s of concurrent agents

📡 Client Usage:

Python Client (HTTP):
  from client import TradingEnvClient
  
  client = TradingEnvClient(base_url="http://localhost:8000")
  obs = client.reset()
  obs = client.step(action)
  state = client.state()

WebSocket (Real-time):
  async with websocket.connect("ws://localhost:8000/ws") as ws:
      await ws.send_json({"type": "reset"})
      result = await ws.recv_json()

🔗 Available Endpoints:
  GET  /health              - Health check
  POST /reset               - Reset environment
  POST /step/{session_id}   - Execute action
  GET  /state/{session_id}  - Get state
  WS   /ws                  - WebSocket connection
  GET  /docs                - API documentation
""")


# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "=" * 80)
print("SUMMARY: OpenEnv Trading Environment")
print("=" * 80)

print("""
✅ What You've Learned:

1. ARCHITECTURE
   - Type-safe models (TradingAction, TradingObservation, TradingState)
   - Environment implementation (reset, step, state)
   - HTTP server for production deployment
   - WebSocket support for real-time agents

2. FEATURES
   - Realistic market simulation (GBM price movements)
   - Arbitrage detection across simulated exchanges
   - Portfolio tracking with P&L metrics
   - Market regime changes (normal, high vol, low vol)
   - Transaction costs and slippage

3. TRAINING
   - Multiple policy implementations (random, hold, smart, arbitrage-focused)
   - Evaluation framework for comparing strategies
   - Reward signals for learning (P&L, arbitrage capture, costs)
   - State metrics for monitoring agent progress

4. PRODUCTION READY
   - Docker containerization
   - HTTP + WebSocket APIs
   - Health checks
   - Session management
   - Multi-agent support

🎯 Next Steps for RL Training:

1. Implement a learning agent (PPO, DQN, or GRPO from TRL)
2. Use trading metrics as reward signals
3. Train on real-time market data (integrate live feeds)
4. Backtesting on historical data
5. Deploy to production with proper risk controls

📚 This environment is ready for:
  • Research (new RL algorithms)
  • Education (learning RL + trading)
  • Production (with proper risk controls)
  • Simulation (testing strategies safely)

Happy trading with RL! 🚀
""")
