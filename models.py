"""
Type-safe models for OpenEnv Trading Environment
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum


class TradeAction(Enum):
    """Available trading actions"""
    HOLD = 0
    BUY = 1
    SELL = 2
    SHORT = 3
    CLOSE_SHORT = 4


@dataclass
class TradingAction:
    """Type-safe action contract"""
    action: TradeAction  # What to do
    asset_pair: str  # e.g., "BTC/USD", "ETH/BTC"
    quantity: float  # How much to trade
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketSnapshot:
    """Current market state at a point in time"""
    timestamp: float
    asset_pair: str
    bid_price: float
    ask_price: float
    bid_volume: float
    ask_volume: float
    mid_price: float = 0.0
    spread: float = 0.0
    
    def __post_init__(self):
        self.mid_price = (self.bid_price + self.ask_price) / 2.0
        self.spread = self.ask_price - self.bid_price


@dataclass
class PortfolioState:
    """Agent's current holdings"""
    cash: float
    positions: Dict[str, float] = field(default_factory=dict)  # asset -> quantity
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradingObservation:
    """Type-safe observation returned from environment"""
    # Market data
    market_snapshots: List[MarketSnapshot]
    
    # Portfolio state
    portfolio: PortfolioState
    
    # Computed metrics
    net_worth: float
    pnl: float  # Profit/Loss
    pnl_percent: float
    
    # Arbitrage opportunities detected
    arbitrage_opportunities: List[Dict[str, Any]] = field(default_factory=list)
    
    # Episode info
    done: bool = False
    reward: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TradingState:
    """Episode metadata and state tracking"""
    episode_id: str
    step_count: int
    elapsed_time: float
    
    # Market conditions
    market_volatility: float
    trend: str  # "bullish", "bearish", "sideways"
    
    # Performance tracking
    max_drawdown: float
    cumulative_pnl: float
    num_trades: int
    win_rate: float
    
    # Trading statistics
    total_arbitrage_found: int
    arbitrage_captured: int
    
    metadata: Dict[str, Any] = field(default_factory=dict)
