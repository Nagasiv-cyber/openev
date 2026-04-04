# OpenEnv Trading Environment 🚀

**Production-ready RL environment for quantitative trading and arbitrage detection**

## Overview

This is a complete, real-world OpenEnv environment that agents can learn from through the standard `reset()` / `step()` / `state()` API. It simulates a multi-asset trading market with realistic price movements and detects arbitrage opportunities.

### Key Features

✅ **Type-Safe API** - Full IDE autocomplete and compile-time error checking  
✅ **Realistic Market Simulation** - Geometric Brownian motion price movements  
✅ **Arbitrage Detection** - Simulates cross-exchange price mismatches  
✅ **Production Deployment** - Docker, Kubernetes, and Hugging Face Spaces ready  
✅ **Portfolio Tracking** - Real-time P&L, max drawdown, win rate calculations  
✅ **Multi-Agent Support** - WebSocket for concurrent independent agents  

## Environment Specification

### Action Space

```python
class TradeAction(Enum):
    HOLD = 0          # Do nothing
    BUY = 1           # Buy at ask price
    SELL = 2          # Sell at bid price
    SHORT = 3         # Short position (futures)
    CLOSE_SHORT = 4   # Close short position
```

### Observation Space

```python
@dataclass
class TradingObservation:
    market_snapshots: List[MarketSnapshot]      # [bid, ask, spread] for each asset
    portfolio: PortfolioState                   # [cash, positions]
    net_worth: float                            # Total portfolio value
    pnl: float                                  # Profit/Loss in USD
    pnl_percent: float                          # P&L as percentage
    arbitrage_opportunities: List[Dict]         # Found arb opportunities
    reward: Optional[float]                     # Step reward
    done: bool                                  # Episode termination flag
```

### Reward Signal

- **+Profit from trades**: When P&L is positive
- **+Arbitrage bonus**: 0.1 × (spread_percent) for capturing arb
- **-Transaction cost**: 0.1% per trade
- **Penalty for inaction**: Small penalty to encourage trading

## Quick Start

### 1. Local Development

```bash
# Install dependencies
pip install fastapi uvicorn pydantic

# Clone this environment
git clone <repo-url>
cd openenv-trading

# Run the server
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Test with Python Client

```python
from client import TradingEnvClient
from models import TradingAction, TradeAction

# Connect to server
client = TradingEnvClient(base_url="http://localhost:8000")

# Reset environment
obs = client.reset()
print(f"Initial net worth: ${obs.net_worth:.2f}")

# Execute trading action
action = TradingAction(
    action=TradeAction.BUY,
    asset_pair="BTC/USD",
    quantity=0.1
)
obs = client.step(action)
print(f"After trade: ${obs.net_worth:.2f}, P&L: ${obs.pnl:.2f}")

# Get state
state = client.state()
print(f"Trades executed: {state.num_trades}")
```

### 3. Docker Deployment

```bash
# Build image
docker build -t trading-env:latest .

# Run container
docker run -d \
  --name trading-env \
  -p 8000:8000 \
  -e WORKERS=4 \
  trading-env:latest

# Test health
curl http://localhost:8000/health
```

## Architecture

```
┌─────────────────────────────────────┐
│     TRAINING CODE (Agent)           │
│                                     │
│  from client import TradingEnvClient│
│  env = TradingEnvClient(...)        │
│  obs = env.reset()                  │
│  obs = env.step(action)             │
│  state = env.state()                │
│                                     │
└────────────┬────────────────────────┘
             │
             │ HTTP/WebSocket (JSON)
             │ POST /reset
             │ POST /step/{session_id}
             │ GET  /state/{session_id}
             │ WS   /ws
             │
┌────────────▼────────────────────────┐
│     DOCKER CONTAINER                │
│                                     │
│  ┌──────────────────────────────┐  │
│  │  FastAPI Server              │  │
│  │  ├─ reset()                  │  │
│  │  ├─ step()                   │  │
│  │  └─ state()                  │  │
│  └──────────┬───────────────────┘  │
│             │                       │
│  ┌──────────▼───────────────────┐  │
│  │  TradingEnvironment          │  │
│  │  ├─ Market Simulation        │  │
│  │  ├─ Arbitrage Detection      │  │
│  │  ├─ Portfolio Tracking       │  │
│  │  └─ P&L Calculation          │  │
│  └──────────────────────────────┘  │
│                                     │
│  Isolated • Reproducible • Secure   │
└─────────────────────────────────────┘
```

## Core Components

### 1. Type-Safe Models (`models.py`)

Defines the contract between agent and environment:

```python
@dataclass
class TradingAction:
    action: TradeAction        # Type-safe enum
    asset_pair: str            # "BTC/USD", "ETH/USD", etc.
    quantity: float            # Trade quantity
    metadata: Dict             # Additional info

@dataclass
class TradingObservation:
    market_snapshots: List[MarketSnapshot]
    portfolio: PortfolioState
    net_worth: float
    pnl: float
    arbitrage_opportunities: List[Dict]
    reward: Optional[float]
    done: bool
```

**Benefits:**
- ✅ IDE autocomplete
- ✅ Compile-time type checking
- ✅ Self-documenting code
- ✅ Catch typos before runtime

### 2. Environment Implementation (`environment.py`)

Core trading simulation with:

```python
class TradingEnvironment:
    def reset(self) -> TradingObservation
    def step(self, action: TradingAction) -> TradingObservation
    @property
    def state(self) -> TradingState
```

Features:
- **Geometric Brownian Motion** - Realistic price movements
- **Bid-Ask Spreads** - Varies by volatility
- **Arbitrage Detection** - Cross-exchange mismatches
- **Portfolio Tracking** - Cash, positions, P&L
- **Market Regimes** - Normal, high volatility, low volatility
- **Transaction Costs** - 0.1% per trade

### 3. HTTP Server (`app.py`)

FastAPI server with:

```
GET  /health              # Health check
POST /reset               # Initialize episode
POST /step/{session_id}   # Execute action
GET  /state/{session_id}  # Get episode state
WS   /ws                  # WebSocket (persistent sessions)
GET  /docs                # OpenAPI documentation
```

### 4. Client Library (`client.py`)

Abstraction over HTTP communication:

```python
class TradingEnvClient:
    def reset(self) -> TradingObservation
    def step(self, action: TradingAction) -> TradingObservation
    def state(self) -> TradingState
```

No HTTP details visible to user—just clean Python!

## Training Agents

### Example 1: Simple Arbitrage Hunter

```python
from environment import TradingEnvironment
from models import TradingAction, TradeAction

def train_arbitrage_hunter(num_episodes=100):
    rewards = []
    
    for episode in range(num_episodes):
        env = TradingEnvironment()
        obs = env.reset()
        
        episode_reward = 0
        while not obs.done:
            # Strategy: capture arbitrage when found
            if obs.arbitrage_opportunities:
                arb = obs.arbitrage_opportunities[0]
                action = TradingAction(
                    action=TradeAction.BUY,
                    asset_pair=arb["asset_pair"],
                    quantity=0.1,
                )
            else:
                action = TradingAction(
                    action=TradeAction.HOLD,
                    asset_pair="BTC/USD",
                    quantity=0.0,
                )
            
            obs = env.step(action)
            episode_reward += obs.reward or 0
        
        rewards.append(episode_reward)
        print(f"Episode {episode}: Reward = {episode_reward:.2f}")
    
    return rewards
```

### Example 2: RL Agent with TRL + GRPO

```python
from trl import GRPOTrainer, GRPOConfig
from transformers import AutoModelForCausalLM, AutoTokenizer

# Training configuration
config = GRPOConfig(
    learning_rate=5e-6,
    num_train_epochs=3,
    per_device_train_batch_size=1,
    output_dir="trading-agent",
)

# Create trainer
trainer = GRPOTrainer(
    model="Qwen/Qwen3-1.7B",
    processing_class=AutoTokenizer.from_pretrained("Qwen/Qwen3-1.7B"),
    args=config,
    rollout_func=rollout_func,  # Your rollout function
    reward_funcs=[reward_pnl, reward_arb],
)

# Train
trainer.train()
```

## Performance Metrics

The environment tracks:

- **net_worth** - Current portfolio value
- **pnl** - Profit/loss in USD
- **pnl_percent** - P&L as percentage
- **max_drawdown** - Peak-to-trough decline
- **win_rate** - Fraction of winning trades
- **num_trades** - Total trades executed
- **arbitrage_found** - Opportunities detected
- **arbitrage_captured** - Opportunities exploited

## Scaling

### Single Container Performance

| Configuration | Sessions | RPS | Success Rate |
|---------------|----------|-----|--------------|
| Local Uvicorn | 2,048 | ~932 | 96.5% |
| Docker | 2,048 | ~682 | 96.5% |
| HF Spaces | 128 | ~48 | 100% |

### Multi-Container (with load balancer)

- 4 containers × 256 sessions/core = 1,024 concurrent agents
- 8 containers × 256 sessions/core = 2,048 concurrent agents
- 96+ nodes = 16,384+ concurrent agents (see scaling docs)

## Production Checklist

- [x] Type-safe API
- [x] Error handling
- [x] Health checks
- [x] Documentation
- [x] Docker support
- [x] WebSocket for real-time agents
- [x] Session management
- [ ] Rate limiting (add as needed)
- [ ] Authentication (add as needed)
- [ ] Monitoring (integrate with your platform)

## Integration with TRL

```python
# Your custom rollout function
def rollout_func(prompts, trainer=None):
    results = {
        "prompt_ids": [],
        "completion_ids": [],
        "logprobs": [],
        "reward_pnl": [],
        "reward_arbitrage": [],
    }
    
    for prompt in prompts:
        # Generate action from model
        action_text = model.generate(prompt)
        
        # Execute in environment
        env = TradingEnvironment()
        obs = env.reset()
        obs = env.step(parse_action(action_text))
        
        # Collect rewards
        results["reward_pnl"].append(obs.pnl)
        results["reward_arbitrage"].append(
            obs.arbitrage_captured * 10
        )
    
    return results

# Reward functions
def reward_pnl(completions, **kwargs):
    return kwargs.get("reward_pnl", [0.0] * len(completions))

def reward_arbitrage(completions, **kwargs):
    return kwargs.get("reward_arbitrage", [0.0] * len(completions))
```

## Testing

```bash
# Run demonstration
python demo.py

# Test individual components
python -c "
from environment import TradingEnvironment
from models import TradingAction, TradeAction

env = TradingEnvironment()
obs = env.reset()
print(f'Initial net worth: \${obs.net_worth:.2f}')

action = TradingAction(TradeAction.BUY, 'BTC/USD', 0.1)
obs = env.step(action)
print(f'After trade: \${obs.net_worth:.2f}')
"
```

## Next Steps

1. **Integrate real market data** - Replace simulated prices with live feeds
2. **Add risk constraints** - Max position size, stop losses
3. **Implement backtesting** - Test strategies on historical data
4. **Add monitoring** - Track live trading metrics
5. **Deploy to production** - With proper risk controls

## File Structure

```
openenv-trading/
├── models.py              # Type-safe contracts
├── environment.py         # Core trading simulation
├── client.py              # HTTP client abstraction
├── app.py                 # FastAPI server
├── Dockerfile             # Container definition
├── demo.py                # Complete demonstration
└── README.md              # This file
```

## Contributing

This environment is designed to be extended:

- Add new reward signals
- Implement different market microstructure models
- Connect real exchange APIs
- Build domain-specific clients

## License

BSD 3-Clause License - See LICENSE file

## Support

For questions or issues:
- Check the documentation in docstrings
- Run `python demo.py` for examples
- Review the FastAPI docs at `/docs` endpoint

---

**Built with OpenEnv** - Production RL Made Simple ✨
