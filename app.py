"""
FastAPI Server for Trading Environment
Serves the environment via HTTP + WebSocket
"""

from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import json
import asyncio

from environment import TradingEnvironment
from models import TradingAction, TradeAction, TradingObservation

# ============================================================================
# Pydantic Models for HTTP Communication
# ============================================================================

class ActionPayload(BaseModel):
    """HTTP request body for step"""
    action: str  # "HOLD", "BUY", "SELL", etc.
    asset_pair: str
    quantity: float
    metadata: Dict[str, Any] = {}


class ResetResponse(BaseModel):
    """Response from reset endpoint"""
    market_snapshots: List[Dict[str, Any]]
    portfolio: Dict[str, Any]
    pnl: float
    pnl_percent: float
    done: bool
    grader_score: Optional[float] = None


class StepResponse(BaseModel):
    """Response from step endpoint"""
    market_snapshots: List[Dict[str, Any]]
    portfolio: Dict[str, Any]
    net_worth: float
    pnl: float
    reward: float
    done: bool
    grader_score: Optional[float] = None
    arbitrage_opportunities: List[Dict[str, Any]]


class StateResponse(BaseModel):
    """Response from state endpoint"""
    episode_id: str
    step_count: int
    elapsed_time: float
    market_volatility: float
    trend: str
    max_drawdown: float
    cumulative_pnl: float
    num_trades: int
    win_rate: float
    total_arbitrage_found: int
    arbitrage_captured: int
    grader_score: Optional[float] = None


# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="OpenEnv Trading Environment",
    description="Production-ready RL environment for quantitative trading and arbitrage detection",
    version="1.0.0"
)

# Global environment instance (per-session in production)
environments: Dict[str, TradingEnvironment] = {}


@app.get("/", response_class=HTMLResponse)
async def root():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>OpenEnv Trading Environment</title>
        <style>
            body { 
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
                display: flex; 
                justify-content: center; 
                align-items: center; 
                height: 100vh; 
                margin: 0; 
                background-color: #0f172a; 
                color: #f8fafc; 
            }
            .container { 
                text-align: center; 
                padding: 3rem; 
                background-color: #1e293b; 
                border-radius: 1rem; 
                box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1), 0 8px 10px -6px rgb(0 0 0 / 0.1); 
                border: 1px solid #334155;
            }
            h1 { color: #38bdf8; margin-top: 0; margin-bottom: 0.5rem; font-size: 2.5rem; }
            .subtitle { color: #94a3b8; font-size: 1.1rem; margin-bottom: 2rem; }
            .status { 
                display: inline-block; 
                padding: 0.5rem 1rem; 
                background-color: rgba(16, 185, 129, 0.1); 
                color: #34d399; 
                border: 1px solid rgba(16, 185, 129, 0.2);
                border-radius: 9999px; 
                font-size: 0.875rem; 
                font-weight: 600; 
                margin-bottom: 2rem; 
            }
            .links { display: flex; gap: 1rem; justify-content: center; }
            a { 
                display: inline-block;
                padding: 0.75rem 1.5rem;
                background-color: #38bdf8;
                color: #0f172a; 
                text-decoration: none; 
                font-weight: 600; 
                border-radius: 0.5rem;
                transition: background-color 0.2s;
            }
            a:hover { background-color: #7dd3fc; }
            .api-link {
                background-color: transparent;
                border: 1px solid #38bdf8;
                color: #38bdf8;
            }
            .api-link:hover {
                background-color: rgba(56, 189, 248, 0.1);
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 OpenEnv Trading</h1>
            <div class="subtitle">Production-ready RL environment for quantitative trading</div>
            <div class="status">● API Status: Operational</div>
            <div class="links">
                <a href="/docs">Interactive Documentation</a>
                <a href="/health" class="api-link">Health Check</a>
            </div>
        </div>
    </body>
    </html>
    """

def _observation_to_dict(obs: TradingObservation) -> Dict[str, Any]:
    """Convert observation to JSON-serializable dict"""
    return {
        "market_snapshots": [
            {
                "timestamp": snap.timestamp,
                "asset_pair": snap.asset_pair,
                "bid_price": snap.bid_price,
                "ask_price": snap.ask_price,
                "bid_volume": snap.bid_volume,
                "ask_volume": snap.ask_volume,
                "mid_price": snap.mid_price,
                "spread": snap.spread,
            }
            for snap in obs.market_snapshots
        ],
        "portfolio": {
            "cash": obs.portfolio.cash,
            "positions": obs.portfolio.positions,
        },
        "net_worth": obs.net_worth,
        "pnl": obs.pnl,
        "pnl_percent": obs.pnl_percent,
        "done": obs.done,
        "reward": obs.reward,
        "grader_score": obs.grader_score,
        "arbitrage_opportunities": obs.arbitrage_opportunities,
    }


# ============================================================================
# HTTP Endpoints (REST API)
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "trading-environment"}


@app.post("/reset")
async def reset(task_id: str = "easy"):
    """
    Reset environment endpoint.
    
    Returns initial observation.
    """
    env = TradingEnvironment(initial_cash=100000.0, num_assets=3, task_id=task_id)
    session_id = f"session_{id(env)}"
    environments[session_id] = env
    
    obs = env.reset()
    
    return {
        "session_id": session_id,
        **_observation_to_dict(obs)
    }


@app.post("/step/{session_id}")
async def step(session_id: str, action: ActionPayload):
    """
    Execute one step.
    
    Args:
        session_id: Session identifier
        action: Trading action to execute
    """
    if session_id not in environments:
        raise HTTPException(status_code=404, detail="Session not found")
    
    env = environments[session_id]
    
    # Parse action
    try:
        action_enum = TradeAction[action.action]
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")
    
    trading_action = TradingAction(
        action=action_enum,
        asset_pair=action.asset_pair,
        quantity=action.quantity,
        metadata=action.metadata,
    )
    
    # Execute step
    obs = env.step(trading_action)
    
    return _observation_to_dict(obs)


@app.get("/state/{session_id}")
async def state(session_id: str):
    """
    Get episode state.
    
    Args:
        session_id: Session identifier
    """
    if session_id not in environments:
        raise HTTPException(status_code=404, detail="Session not found")
    
    env = environments[session_id]
    state = env.state
    
    return {
        "episode_id": state.episode_id,
        "task_id": state.task_id,
        "step_count": state.step_count,
        "elapsed_time": state.elapsed_time,
        "market_volatility": state.market_volatility,
        "trend": state.trend,
        "max_drawdown": state.max_drawdown,
        "cumulative_pnl": state.cumulative_pnl,
        "num_trades": state.num_trades,
        "win_rate": state.win_rate,
        "total_arbitrage_found": state.total_arbitrage_found,
        "arbitrage_captured": state.arbitrage_captured,
        "grader_score": state.grader_score,
    }


@app.get("/grade/{session_id}")
async def grade(session_id: str):
    """
    Grade endpoint — returns a single score strictly in (0, 1).
    
    OpenEnv validator calls this after each episode to get the task score.
    Score is ALWAYS strictly between 0 and 1 (never 0.0, never 1.0).
    """
    if session_id not in environments:
        raise HTTPException(status_code=404, detail="Session not found")
    
    env = environments[session_id]
    state = env.state
    
    # grader_score is already clamped to [0.001, 0.999] by environment
    raw_score = state.grader_score
    
    # Extra safety clamp — validator requires strictly (0, 1) exclusive
    score = max(0.001, min(0.999, float(raw_score) if raw_score is not None else 0.5))
    
    return {
        "score": score,
        "task_id": state.task_id,
        "episode_id": state.episode_id,
        "step_count": state.step_count,
    }


@app.get("/docs")
async def api_docs():
    """API documentation endpoint"""
    return {
        "endpoints": {
            "/health": "GET - Health check",
            "/reset": "POST - Reset environment, returns initial observation",
            "/step/{session_id}": "POST - Execute trading action",
            "/state/{session_id}": "GET - Get episode state",
            "/ws/{session_id}": "WebSocket - Real-time bidirectional communication",
        },
        "action_types": ["HOLD", "BUY", "SELL", "SHORT", "CLOSE_SHORT"],
        "asset_pairs": ["BTC/USD", "ETH/USD", "SOL/USD", "AAPL/USD", "GOLD/USD"],
    }


# ============================================================================
# WebSocket Support (for persistent sessions)
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for persistent trading sessions.
    
    Supports:
    - reset: Initialize new session
    - step: Execute trading action
    - state: Get current state
    """
    await websocket.accept()
    
    env = None
    session_id = None
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            if message_type == "reset":
                # Reset environment
                env = TradingEnvironment(
                    initial_cash=data.get("initial_cash", 100000.0),
                    num_assets=data.get("num_assets", 3),
                )
                session_id = f"session_{id(env)}"
                environments[session_id] = env
                
                obs = env.reset()
                
                await websocket.send_json({
                    "type": "reset_response",
                    "session_id": session_id,
                    **_observation_to_dict(obs)
                })
            
            elif message_type == "step":
                if env is None:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Environment not initialized. Call reset first."
                    })
                    continue
                
                # Parse action
                try:
                    action_enum = TradeAction[data["action"]]
                except KeyError:
                    await websocket.send_json({
                        "type": "error",
                        "message": f"Unknown action: {data['action']}"
                    })
                    continue
                
                trading_action = TradingAction(
                    action=action_enum,
                    asset_pair=data["asset_pair"],
                    quantity=data["quantity"],
                    metadata=data.get("metadata", {}),
                )
                
                # Execute step
                obs = env.step(trading_action)
                
                await websocket.send_json({
                    "type": "step_response",
                    **_observation_to_dict(obs)
                })
            
            elif message_type == "state":
                if env is None:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Environment not initialized. Call reset first."
                    })
                    continue
                
                state = env.state
                
                await websocket.send_json({
                    "type": "state_response",
                    "episode_id": state.episode_id,
                    "step_count": state.step_count,
                    "elapsed_time": state.elapsed_time,
                    "market_volatility": state.market_volatility,
                    "trend": state.trend,
                    "max_drawdown": state.max_drawdown,
                    "cumulative_pnl": state.cumulative_pnl,
                    "num_trades": state.num_trades,
                    "win_rate": state.win_rate,
                    "total_arbitrage_found": state.total_arbitrage_found,
                    "arbitrage_captured": state.arbitrage_captured,
                })
            
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"Unknown message type: {message_type}"
                })
    
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "message": str(e)
        })
    finally:
        await websocket.close()
        if session_id and session_id in environments:
            del environments[session_id]


# ============================================================================
# Startup/Shutdown
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Startup event"""
    print("🚀 Trading Environment Server Started")
    print("   POST   /reset           - Reset environment")
    print("   POST   /step/{sid}      - Execute action")
    print("   GET    /state/{sid}     - Get state")
    print("   WS     /ws              - WebSocket endpoint")
    print("   GET    /docs            - API documentation")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
