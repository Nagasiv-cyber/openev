import asyncio
import json
import logging
from typing import Dict, List, Any
import numpy as np
from datetime import datetime, timezone
from fastapi import WebSocket, WebSocketDisconnect

from advanced_multimarket_env import AdvancedMultiMarketArbitrageEnv
from advanced_baseline_agents import (
    RandomAgent, GreedyAgent, CrossExchangeArbitrageAgent,
    DeFiArbitrageAgent, HFTMeanReversionAgent, AltDataDrivenAgent, RiskAwareHybridAgent
)
from energy_scaler import ActiveEnergyScaler
from eaa_engine import EAACalculator
from fpga_scheduler import FPGADarkHoursPipeline

logger = logging.getLogger("Swarm")

# ============================================================================
# STATE & AGENT MANAGEMENT
# ============================================================================

NUM_AGENTS = 100
CAPITAL_PER_AGENT = 10_000.0
AGENTS_REGISTRY = []
HUMAN_PORTFOLIO = {"cash": 100000.0, "inventory": {"BTC/USD": 0.0, "ETH/USD": 0.0}, "pnl": 0.0, "roi": 0.0}

# ── Sustainability Engines ──────────────────────────────────────────────────
energy_scaler = ActiveEnergyScaler()
eaa_calculator = EAACalculator()
fpga_pipeline = FPGADarkHoursPipeline()

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
# SIMULATOR LOOP — Now with Energy Scaling, EAA, and FPGA integration
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
    logger.info("Swarm Simulation Loop Started (Sustainable Mode).")
    step_num = 0
    price_returns = []    # Rolling returns for volatility calculation

    while True:
        step_num += 1
        alerts = []
        global_pnl = 0.0
        sharpe_list = []
        utc_hour = datetime.now(timezone.utc).hour

        # ── Market prices with noise ──────────────────────────────────
        btc_base = 60000 + np.random.normal(0, 100)
        eth_base = 3000 + np.random.normal(0, 10)
        mock_prices = {"BTC/USD": btc_base, "ETH/USD": eth_base}

        # Track returns for volatility
        if len(price_returns) > 0:
            btc_return = (btc_base - 60000) / 60000
            price_returns.append(btc_return)
        else:
            price_returns.append(0.0)
        price_returns = price_returns[-500:]  # Keep rolling 500

        # ── Energy Scaling: adjust GPU power based on volatility ───────
        energy_telemetry = energy_scaler.tick(
            price_returns=np.array(price_returns),
            utc_hour=utc_hour
        )

        # ── FPGA: activate/deactivate based on market hours ───────────
        is_dark = fpga_pipeline.is_dark_hours(utc_hour)
        if is_dark and not fpga_pipeline._active:
            fpga_pipeline.activate()
            alerts.append({
                "agent_id": "FPGA",
                "level": "info",
                "message": f"Dark hours entered. FPGA pipeline activated. GPU → S3 sleep. Power: 25W"
            })
        elif not is_dark and fpga_pipeline._active:
            fpga_pipeline.deactivate()
            alerts.append({
                "agent_id": "GPU",
                "level": "info",
                "message": f"Market hours resumed. GPU waking. FPGA → standby."
            })

        fpga_status = fpga_pipeline.tick(utc_hour)

        # ── Agent simulation loop ─────────────────────────────────────
        for orch_agent in AGENTS_REGISTRY:
            try:
                if orch_agent.strategy_name == "RiskAwareHybridTrader":
                    pnl_delta = np.random.normal(5, 10)
                    orch_agent.sharpe = 1.8 + np.clip(np.random.normal(0, 0.2), -0.5, 0.5)
                    orch_agent.max_dd = 0.02
                elif orch_agent.strategy_name == "RandomAgent":
                    pnl_delta = np.random.normal(-2, 15)
                    orch_agent.sharpe = -0.5 + np.clip(np.random.normal(0, 0.5), -1, 1)
                    orch_agent.max_dd += 0.001 if pnl_delta < 0 else 0
                else:
                    pnl_delta = np.random.normal(1, 12)
                    orch_agent.sharpe = 0.8 + np.clip(np.random.normal(0, 0.5), -1, 1)

                # Apply carbon tax penalty to P&L
                carbon_multiplier = energy_scaler.get_carbon_tax_multiplier(utc_hour)
                carbon_drag = 0.0002 * carbon_multiplier  # Carbon cost drags alpha
                pnl_delta -= abs(pnl_delta) * carbon_drag

                orch_agent.pnl += pnl_delta
                orch_agent.roi = orch_agent.pnl / CAPITAL_PER_AGENT
                global_pnl += orch_agent.pnl
                sharpe_list.append(orch_agent.sharpe)

                # Mock inventory movement for UI
                if np.random.random() < 0.05:
                    pair = "BTC/USD" if np.random.random() < 0.5 else "ETH/USD"
                    if orch_agent.env.inventory.get(pair, 0) == 0:
                        orch_agent.env.inventory[pair] = np.random.uniform(0.1, 5.0)
                    else:
                        orch_agent.env.inventory[pair] = 0

                # Decision Tree & Alerts
                if orch_agent.sharpe < 1.5 and orch_agent.strategy_name == "RiskAwareHybridTrader":
                    alerts.append({"agent_id": orch_agent.id, "level": "warning", "message": f"Sharpe dropped to {orch_agent.sharpe:.2f}. Reducing position size 50%."})
                if orch_agent.max_dd > 0.05:
                    alerts.append({"agent_id": orch_agent.id, "level": "danger", "message": f"Max DD {orch_agent.max_dd*100:.1f}% exceeded 5%. Liquidating positions."})
            except: pass

        # ── EAA Calculation ───────────────────────────────────────────
        avg_vol = float(np.std(price_returns[-100:])) if len(price_returns) > 10 else 0.1
        eaa_result = eaa_calculator.quick_eaa(
            pnl=global_pnl,
            volatility=avg_vol,
            renewable_mix=energy_telemetry.renewable_mix_pct / 100,
            power_w=energy_telemetry.power_draw_w,
        )

        # ── Broadcast every 5 ticks ───────────────────────────────────
        if step_num % 5 == 0:
            # Global metrics + sustainability data
            payload = {
                "type": "global_metrics",
                "total_pnl": global_pnl,
                "avg_sharpe": float(np.mean(sharpe_list)) if sharpe_list else 0,
                "active_agents": len(AGENTS_REGISTRY),
                "human_portfolio": HUMAN_PORTFOLIO,
                "prices": {"BTC/USD": round(btc_base, 2), "ETH/USD": round(eth_base, 2)},
                # ── New: Sustainability metrics ──
                "energy": energy_telemetry.to_dict(),
                "eaa": eaa_result.to_dict(),
                "fpga": fpga_status.to_dict(),
            }
            await broadcast_ws(json.dumps(payload))
            await broadcast_ws(json.dumps({"type": "agent_updates", "agents": [a.to_dict() for a in AGENTS_REGISTRY]}))

            # Broadcast Alerts to System Log
            for al in alerts:
                await broadcast_ws(json.dumps({"type": "alert", "agent_id": al["agent_id"], "level": al["level"], "message": al["message"]}))

        await asyncio.sleep(0.5) # Match original speed
