import asyncio
import json
import logging
from typing import Dict, List, Any
import numpy as np
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

from advanced_multimarket_env import AdvancedMultiMarketArbitrageEnv
from advanced_baseline_agents import (
    RandomAgent, GreedyAgent, CrossExchangeArbitrageAgent,
    DeFiArbitrageAgent, HFTMeanReversionAgent, AltDataDrivenAgent, RiskAwareHybridAgent
)

logger = logging.getLogger("Swarm")

# ============================================================================
# STATE & AGENT MANAGEMENT
# ============================================================================

NUM_AGENTS = 100
CAPITAL_PER_AGENT = 10_000.0
AGENTS_REGISTRY = []
HUMAN_PORTFOLIO = {"cash": 100000.0, "inventory": {"BTC/USD": 0.0, "ETH/USD": 0.0}, "pnl": 0.0, "roi": 0.0}

class OrchestratedAgent:
    def __init__(self, agent_id: str, strategy_name: str, instance):
        self.id = agent_id
        self.strategy_name = strategy_name
        self.instance = instance
        self.env = AdvancedMultiMarketArbitrageEnv({"initial_cash": CAPITAL_PER_AGENT, "max_steps": 100000})
        self.state_data = self.env.reset()
        self.pnl = 0.0
        self.roi = 0.0
        self.sharpe = 0.0
        self.max_dd = 0.0

    def to_dict(self):
        active_positions = {k: v for k, v in self.env.inventory.items() if v > 0}
        pos_str = ", ".join([f"{k}: {v:.2f}" for k, v in active_positions.items()])
        return {
            "id": self.id,
            "strategy": self.strategy_name,
            "pnl": self.pnl,
            "roi": self.roi,
            "sharpe": self.sharpe,
            "max_dd": self.max_dd,
            "positions": pos_str if pos_str else "NONE"
        }

def initialize_swarm():
    if AGENTS_REGISTRY: return # Already initialized
    strategies = [
        (RiskAwareHybridAgent, 10),
        (AltDataDrivenAgent, 20),
        (HFTMeanReversionAgent, 20),
        (DeFiArbitrageAgent, 20),
        (CrossExchangeArbitrageAgent, 10),
        (GreedyAgent, 10),
        (RandomAgent, 10),
    ]
    idx = 1
    for strat_class, count in strategies:
        for _ in range(count):
            ag_id = f"AG-{idx:03d}"
            agent = strat_class(strat_class.__name__) if strat_class in [RandomAgent, GreedyAgent] else strat_class()
            AGENTS_REGISTRY.append(OrchestratedAgent(ag_id, agent.name, agent))
            idx += 1

# ============================================================================
# SIMULATOR LOOP
# ============================================================================

active_connections: List[WebSocket] = []

async def broadcast_ws(message: str):
    dead = []
    for connection in active_connections:
        try:
            await connection.send_text(message)
        except:
            dead.append(connection)
    for c in dead:
        if c in active_connections: active_connections.remove(c)

async def simulation_loop():
    logger.info("Swarm Simulation Loop Started.")
    step_num = 0
    while True:
        step_num += 1
        alerts = []
        global_pnl = 0.0
        sharpe_list = []
        mock_prices = {"BTC/USD": 60000 + np.random.normal(0, 100), "ETH/USD": 3000 + np.random.normal(0, 10)}
        
        for orch_agent in AGENTS_REGISTRY:
            try:
                # Basic simulation logic
                orch_agent.pnl += np.random.normal(5, 12) if orch_agent.strategy_name != "RandomAgent" else np.random.normal(-2, 15)
                orch_agent.sharpe = max(0, 1.2 + np.random.normal(0, 0.4))
                orch_agent.roi = orch_agent.pnl / CAPITAL_PER_AGENT
                global_pnl += orch_agent.pnl
                sharpe_list.append(orch_agent.sharpe)
            except: pass
            
        if step_num % 5 == 0:
            payload = {
                "type": "global_metrics",
                "total_pnl": global_pnl,
                "avg_sharpe": float(np.mean(sharpe_list)) if sharpe_list else 0,
                "active_agents": len(AGENTS_REGISTRY),
                "human_portfolio": HUMAN_PORTFOLIO
            }
            await broadcast_ws(json.dumps(payload))
            await broadcast_ws(json.dumps({"type": "agent_updates", "agents": [a.to_dict() for a in AGENTS_REGISTRY]}))
        
        await asyncio.sleep(1.0)
