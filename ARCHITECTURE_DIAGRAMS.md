# OpenEnv Trading Environment - Architecture Diagrams

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   AGENT / TRAINING CODE                     │
│                                                             │
│  from client import TradingEnvClient                       │
│  env = TradingEnvClient("http://localhost:8000")          │
│  obs = env.reset()                                         │
│  obs = env.step(action)                                    │
│  state = env.state()                                       │
└────────────────────┬────────────────────────────────────────┘
                     │
        ┌────────────┴───────────────┐
        │    HTTP / WebSocket        │
        │    JSON Communication      │
        │                            │
        │  POST /reset               │
        │  POST /step/{session}      │
        │  GET /state/{session}      │
        │  WS /ws                    │
        │                            │
        └────────────┬───────────────┘
                     │
┌────────────────────▼─────────────────────────────────────────┐
│              DOCKER CONTAINER (Isolated)                     │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         FastAPI Server (Uvicorn)                     │  │
│  │                                                      │  │
│  │  ┌────────────────────────────────────────────────┐ │  │
│  │  │  HTTP Request Handler                          │ │  │
│  │  ├─ GET /health                                  │ │  │
│  │  ├─ POST /reset                                 │ │  │
│  │  ├─ POST /step/{session_id}                     │ │  │
│  │  ├─ GET /state/{session_id}                     │ │  │
│  │  └─ WS /ws (WebSocket)                          │ │  │
│  │  └────────────────────────────────────────────────┘ │  │
│  │                     │                                │  │
│  │                     ▼                                │  │
│  │  ┌────────────────────────────────────────────────┐ │  │
│  │  │    TradingEnvironment (Per Session)            │ │  │
│  │  │                                                │ │  │
│  │  │  ┌──────────────────────────────────────────┐ │ │  │
│  │  │  │  Market Simulation                       │ │ │  │
│  │  │  │  ├─ Geometric Brownian Motion           │ │ │  │
│  │  │  │  ├─ Bid-Ask Spread Dynamics            │ │ │  │
│  │  │  │  └─ Market Regime Changes              │ │ │  │
│  │  │  └──────────────────────────────────────────┘ │ │  │
│  │  │                                                │ │  │
│  │  │  ┌──────────────────────────────────────────┐ │ │  │
│  │  │  │  Arbitrage Detection                     │ │ │  │
│  │  │  │  ├─ Find price mismatches               │ │ │  │
│  │  │  │  ├─ Calculate spreads                   │ │ │  │
│  │  │  │  └─ Generate reward signals             │ │ │  │
│  │  │  └──────────────────────────────────────────┘ │ │  │
│  │  │                                                │ │  │
│  │  │  ┌──────────────────────────────────────────┐ │ │  │
│  │  │  │  Portfolio Management                    │ │ │  │
│  │  │  │  ├─ Cash balance                         │ │ │  │
│  │  │  │  ├─ Asset positions                      │ │ │  │
│  │  │  │  ├─ P&L calculation                      │ │ │  │
│  │  │  │  └─ Risk metrics (max drawdown, etc)    │ │ │  │
│  │  │  └──────────────────────────────────────────┘ │ │  │
│  │  │                                                │ │  │
│  │  │  ┌──────────────────────────────────────────┐ │ │  │
│  │  │  │  Reward Calculation                      │ │ │  │
│  │  │  │  ├─ Profit from trades                   │ │ │  │
│  │  │  │  ├─ Arbitrage capture bonus              │ │ │  │
│  │  │  │  └─ Transaction cost penalty             │ │ │  │
│  │  │  └──────────────────────────────────────────┘ │ │  │
│  │  └────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  Isolated • Reproducible • Secure • Scalable               │
└──────────────────────────────────────────────────────────────┘
```

## 2. Data Flow Diagram

```
┌──────────────────┐
│  Reset Request   │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────┐
│  POST /reset                     │
│  ├─ Initialize env               │
│  ├─ Set initial prices           │
│  └─ Create new session           │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│  TradingObservation              │
│  ├─ market_snapshots             │
│  ├─ portfolio                    │
│  ├─ net_worth                    │
│  ├─ pnl                          │
│  └─ arbitrage_opportunities      │
└────────┬─────────────────────────┘
         │
         ▼ (Agent decides action)
┌──────────────────┐
│  Trading Action  │
│  ├─ action type  │
│  ├─ asset_pair   │
│  └─ quantity     │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────┐
│  POST /step/{session_id}         │
│  ├─ Validate action              │
│  ├─ Update market prices         │
│  ├─ Detect arbitrage             │
│  ├─ Execute trade                │
│  ├─ Calculate reward             │
│  └─ Generate observation         │
└────────┬─────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│  TradingObservation (+ reward)   │
│  ├─ market_snapshots (updated)   │
│  ├─ portfolio (updated)          │
│  ├─ pnl (updated)                │
│  ├─ reward (calculated)          │
│  └─ done (episode finished?)     │
└────────┬─────────────────────────┘
         │
         ├─ If not done → New action
         │
         └─ If done:
              │
              ▼
         ┌──────────────────────────────────┐
         │  GET /state/{session_id}         │
         │  ├─ episode_id                   │
         │  ├─ step_count                   │
         │  ├─ max_drawdown                 │
         │  ├─ num_trades                   │
         │  ├─ win_rate                     │
         │  └─ arbitrage_captured           │
         └──────────────────────────────────┘
```

## 3. Type System

```
TradingAction (Input)
├─ action: TradeAction (HOLD | BUY | SELL | SHORT | CLOSE_SHORT)
├─ asset_pair: str ("BTC/USD", "ETH/USD", etc.)
├─ quantity: float
└─ metadata: Dict

    ↓ (execution)

TradingObservation (Output)
├─ market_snapshots: List[MarketSnapshot]
│  └─ MarketSnapshot
│     ├─ timestamp: float
│     ├─ asset_pair: str
│     ├─ bid_price: float
│     ├─ ask_price: float
│     ├─ spread: float
│     └─ mid_price: float
├─ portfolio: PortfolioState
│  ├─ cash: float
│  └─ positions: Dict[str, float]
├─ net_worth: float
├─ pnl: float
├─ pnl_percent: float
├─ arbitrage_opportunities: List[Dict]
│  └─ Dict contains:
│     ├─ asset_pair: str
│     ├─ buy_price: float
│     ├─ sell_price: float
│     ├─ profit_per_unit: float
│     └─ spread_percent: float
├─ reward: Optional[float]
└─ done: bool

    ↓ (end of episode)

TradingState (Metadata)
├─ episode_id: str
├─ step_count: int
├─ elapsed_time: float
├─ market_volatility: float
├─ trend: str
├─ max_drawdown: float
├─ cumulative_pnl: float
├─ num_trades: int
├─ win_rate: float
├─ total_arbitrage_found: int
└─ arbitrage_captured: int
```

## 4. Market Simulation Loop

```
┌─────────────────────────────────────────────────────┐
│  Start of Step                                      │
└────────────┬────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────┐
│  1. Update Market Prices (GBM)                      │
│     P(t+1) = P(t) × e^(μ + σZ)                      │
│     ├─ Drift component: μ (small positive)          │
│     ├─ Volatility: σ (varies by asset/regime)       │
│     └─ Random shock: Z (normal distribution)        │
└────────────┬────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────┐
│  2. Detect Arbitrage Opportunities                  │
│     For each asset:                                 │
│     ├─ Exchange A price (slightly high)             │
│     ├─ Exchange B price (slightly low)              │
│     ├─ Calculate spread %                           │
│     └─ If spread > 0.1%: Mark as opportunity       │
└────────────┬────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────┐
│  3. Execute Trade Action                            │
│     ├─ If HOLD: no-op                               │
│     ├─ If BUY:                                      │
│     │  ├─ Check cash available                      │
│     │  ├─ Deduct transaction cost (0.1%)            │
│     │  └─ Update position                           │
│     └─ If SELL:                                     │
│        ├─ Check position size                       │
│        ├─ Deduct transaction cost (0.1%)            │
│        └─ Update position                           │
└────────────┬────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────┐
│  4. Calculate Reward                                │
│     reward = 0                                      │
│     ├─ If profitable: +pnl_percent                  │
│     ├─ If captured arb: +0.1 × spread_percent      │
│     ├─ Transaction cost: -0.1% of trade            │
│     └─ Result: Single reward signal                 │
└────────────┬────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────┐
│  5. Update Portfolio Metrics                        │
│     ├─ Current net_worth = cash + positions        │
│     ├─ P&L = net_worth - initial_cash              │
│     ├─ Max drawdown tracking                        │
│     └─ Win rate tracking                           │
└────────────┬────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────┐
│  6. Return Observation to Agent                     │
│     ├─ market_snapshots (updated prices)           │
│     ├─ portfolio (updated positions)                │
│     ├─ pnl (current profit/loss)                    │
│     ├─ reward (step reward)                         │
│     ├─ done (check max steps or condition)          │
│     └─ arbitrage_opportunities (for next step)      │
└────────────┬────────────────────────────────────────┘
             │
             └─ Return to Agent
```

## 5. Scaling Architecture

```
Single Machine (Local Development)
┌──────────────────────────┐
│  1 Uvicorn Process       │
│  (8 workers)             │
│  2,048 concurrent        │
│  sessions max            │
└──────────────────────────┘


Docker Container (Scale to many containers)
┌────────────────────────────────────────────┐
│  Docker Container 1         Docker Container 2
│  ┌──────────────────┐     ┌──────────────────┐
│  │  Uvicorn (4W)    │     │  Uvicorn (4W)    │
│  │  256 sessions    │     │  256 sessions    │
│  └──────────────────┘     └──────────────────┘
│           ▲                       ▲
│           └───────────┬───────────┘
│                       │
│        ┌──────────────▼──────────────┐
│        │  Load Balancer (Envoy)      │
│        │  ├─ Round-robin routing     │
│        │  └─ WebSocket support       │
│        └──────────────┬──────────────┘
│                       │
│         Agent 1    Agent 2    Agent N
└────────────────────────────────────────────┘


Kubernetes Cluster (Enterprise Scaling)
┌────────────────────────────────────────────┐
│  Service Mesh (Istio)                      │
│       │                                    │
│       ├─ Replica Set 1                     │
│       │  ├─ Pod 1 (Trading Env)            │
│       │  ├─ Pod 2 (Trading Env)            │
│       │  └─ Pod 3 (Trading Env)            │
│       │                                    │
│       ├─ Replica Set 2                     │
│       │  ├─ Pod 1 (Trading Env)            │
│       │  └─ Pod 2 (Trading Env)            │
│       │                                    │
│       └─ Horizontal Pod Autoscaler         │
│          (scales based on CPU/memory)      │
│                                            │
│  Result: 1000+ concurrent agents           │
└────────────────────────────────────────────┘
```

## 6. Training Loop with TRL

```
┌────────────────────────────────────┐
│  Dataset                           │
│  "Make trading decisions"          │
│  (1000 prompts for training)       │
└────────┬───────────────────────────┘
         │
         ▼
┌────────────────────────────────────┐
│  GRPOTrainer                       │
│  ├─ Model: Qwen/Qwen3-1.7B         │
│  ├─ Reward funcs: [pnl, arb]       │
│  └─ Rollout func: trading_rollout  │
└────────┬───────────────────────────┘
         │
         ├─ For each batch:
         │
         ▼
      ┌────────────────────────────────────┐
      │  1. Generate Completions           │
      │     Model → Action Text            │
      │     "BUY 0.5 BTC/USD"              │
      └────────┬───────────────────────────┘
               │
               ▼
      ┌────────────────────────────────────┐
      │  2. Execute in Environment         │
      │     Action → Environment           │
      │     Environment → Observation      │
      └────────┬───────────────────────────┘
               │
               ▼
      ┌────────────────────────────────────┐
      │  3. Calculate Rewards              │
      │     Observation → Rewards          │
      │     ├─ reward_pnl                  │
      │     ├─ reward_arbitrage            │
      │     └─ reward_sharpe               │
      └────────┬───────────────────────────┘
               │
               ▼
      ┌────────────────────────────────────┐
      │  4. Optimize Model                 │
      │     GRPO algorithm:                │
      │     Compare relative performance   │
      │     Update model weights           │
      └────────────────────────────────────┘
         │
         └─ Next batch
         
After training:
┌────────────────────────────────────┐
│  Trained Model                     │
│  Can be deployed for live trading  │
└────────────────────────────────────┘
```

## 7. File Dependency Graph

```
models.py (Type definitions)
    ↑
    ├─ environment.py (Market simulation)
    │   ├─ Uses: TradingAction, TradingObservation, TradingState
    │   └─ Implements: reset(), step(), state property
    │
    ├─ app.py (FastAPI server)
    │   ├─ Uses: All from models.py
    │   ├─ Uses: TradingEnvironment from environment.py
    │   └─ Provides: HTTP + WebSocket endpoints
    │
    └─ client.py (HTTP abstraction)
        ├─ Uses: All from models.py
        └─ Implements: clean Python interface over HTTP

trl_integration.py
    ├─ Uses: TradingEnvironment
    ├─ Uses: TradingAction, TradingObservation
    └─ Shows: How to train with TRL

demo.py (Complete example)
    ├─ Uses: TradingEnvironment
    ├─ Uses: Models
    └─ Shows: 8 complete usage examples

Dockerfile
    └─ Packages: All Python files into container

requirements.txt
    └─ Specifies: All dependencies
```

---

These diagrams visualize the complete architecture of the OpenEnv Trading Environment.
