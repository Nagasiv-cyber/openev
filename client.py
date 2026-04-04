"""
HTTP Client for Trading Environment
Handles serialization/deserialization of trading types over HTTP
"""

from typing import Dict, Any, List, Optional
from dataclasses import asdict

from models import (
    TradingAction, TradeAction, MarketSnapshot, PortfolioState,
    TradingObservation, TradingState
)


class TradingEnvClient:
    """
    HTTP client for trading environment.
    
    Follows OpenEnv pattern:
    - reset() -> StepResult
    - step(action) -> StepResult
    - state() -> TradingState
    
    Communication is abstracted behind clean Python methods.
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        Initialize client.
        
        Args:
            base_url: Base URL of the environment server
        """
        self.base_url = base_url
        self._session_id = None
    
    def reset(self) -> TradingObservation:
        """
        Reset environment and return initial observation.
        
        Returns:
            Initial observation
        """
        # In real implementation: HTTP POST to /reset
        # For now, return mock
        return TradingObservation(
            market_snapshots=[],
            portfolio=PortfolioState(cash=100000.0),
            net_worth=100000.0,
            pnl=0.0,
            pnl_percent=0.0,
        )
    
    def step(self, action: TradingAction) -> TradingObservation:
        """
        Execute one step with the given action.
        
        Args:
            action: Trading action
            
        Returns:
            Observation after step
        """
        # Convert action to JSON
        payload = self._action_to_dict(action)
        
        # In real implementation: HTTP POST to /step with payload
        # Server would parse, execute, and return observation JSON
        
        return TradingObservation(
            market_snapshots=[],
            portfolio=PortfolioState(cash=100000.0),
            net_worth=100000.0,
            pnl=0.0,
            pnl_percent=0.0,
        )
    
    def state(self) -> TradingState:
        """
        Get current episode state.
        
        Returns:
            Episode state
        """
        # In real implementation: HTTP GET to /state
        return TradingState(
            episode_id="episode_0",
            step_count=0,
            elapsed_time=0.0,
            market_volatility=0.5,
            trend="bullish",
            max_drawdown=0.0,
            cumulative_pnl=0.0,
            num_trades=0,
            win_rate=0.0,
            total_arbitrage_found=0,
            arbitrage_captured=0,
        )
    
    @staticmethod
    def _action_to_dict(action: TradingAction) -> Dict[str, Any]:
        """Convert typed action to JSON-serializable dict"""
        return {
            "action": action.action.name,
            "asset_pair": action.asset_pair,
            "quantity": action.quantity,
            "metadata": action.metadata,
        }
    
    @staticmethod
    def _dict_to_observation(data: Dict[str, Any]) -> TradingObservation:
        """Parse JSON response to typed observation"""
        # Parse market snapshots
        market_snapshots = [
            MarketSnapshot(
                timestamp=snap["timestamp"],
                asset_pair=snap["asset_pair"],
                bid_price=snap["bid_price"],
                ask_price=snap["ask_price"],
                bid_volume=snap["bid_volume"],
                ask_volume=snap["ask_volume"],
            )
            for snap in data.get("market_snapshots", [])
        ]
        
        # Parse portfolio
        portfolio_data = data.get("portfolio", {})
        portfolio = PortfolioState(
            cash=portfolio_data.get("cash", 0.0),
            positions=portfolio_data.get("positions", {}),
        )
        
        return TradingObservation(
            market_snapshots=market_snapshots,
            portfolio=portfolio,
            net_worth=data.get("net_worth", 0.0),
            pnl=data.get("pnl", 0.0),
            pnl_percent=data.get("pnl_percent", 0.0),
            done=data.get("done", False),
            reward=data.get("reward", None),
        )
