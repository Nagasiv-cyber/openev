"""
Core Trading Environment Implementation
Simulates realistic market conditions and detects arbitrage opportunities
"""

import random
import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from collections import defaultdict

from models import (
    TradingAction, TradeAction, MarketSnapshot, PortfolioState,
    TradingObservation, TradingState
)


class TradingEnvironment:
    """
    Realistic market simulator with arbitrage detection.
    
    Features:
    - Multi-asset trading (spot market simulation)
    - Realistic price movements (geometric Brownian motion)
    - Bid-ask spreads that vary by volatility
    - Transaction costs
    - Arbitrage opportunities (cross-exchange price mismatches)
    - Portfolio tracking with P&L calculation
    """
    
    # Score bounds: strictly between 0 and 1 (excluded) per OpenEnv validator
    _SCORE_MIN = 0.001
    _SCORE_MAX = 0.999

    def __init__(self, initial_cash: float = 100000.0, num_assets: int = 3, task_id: str = "survival"):
        """
        Initialize the trading environment.
        
        Args:
            initial_cash: Starting capital in USD
            num_assets: Number of tradeable assets
            task_id: "survival", "arbitrage", "drawdown", or "momentum"
        """
        self.initial_cash = initial_cash
        self.num_assets = num_assets
        self.task_id = task_id
        
        # Asset pairs to trade
        self.asset_pairs = [
            "BTC/USD", "ETH/USD", "SOL/USD", "AAPL/USD", "GOLD/USD"
        ][:num_assets]
        
        # Market state
        self.current_time = datetime.now()
        self.time_step = 0
        self.market_prices: Dict[str, float] = {}
        self.price_history: Dict[str, List[float]] = defaultdict(list)
        self.volatilities: Dict[str, float] = {}
        
        # Initialize prices
        self._initialize_prices()
        
        # Portfolio state
        self.cash = initial_cash
        self.positions: Dict[str, float] = {pair: 0.0 for pair in self.asset_pairs}
        self.trade_history: List[Dict] = []
        
        # Episode tracking
        self.episode_id = ""
        self.episode_start_net_worth = initial_cash
        self.max_net_worth = initial_cash
        self.max_drawdown = 0.0
        self.trades_executed = 0
        self.winning_trades = 0
        
        # Arbitrage tracking
        self.arbitrage_opportunities_found = 0
        self.arbitrage_captured = 0
        
        # Market regime (affects volatility and momentum)
        self.market_regime = "normal"
        self.regime_change_probability = 0.05
    
    def _initialize_prices(self):
        """Initialize realistic starting prices"""
        base_prices = {
            "BTC/USD": 45000.0,
            "ETH/USD": 2500.0,
            "SOL/USD": 120.0,
            "AAPL/USD": 180.0,
            "GOLD/USD": 2000.0,
        }
        
        for pair in self.asset_pairs:
            self.market_prices[pair] = base_prices[pair]
            self.price_history[pair] = [base_prices[pair]]
            # Volatility as annual %, varies by asset
            base_vol = {"BTC/USD": 0.8, "ETH/USD": 1.0, "SOL/USD": 1.2,
                       "AAPL/USD": 0.3, "GOLD/USD": 0.2}
            self.volatilities[pair] = base_vol.get(pair, 0.5)
    
    def reset(self) -> TradingObservation:
        """
        Reset the environment for a new episode.
        
        Returns:
            Initial observation
        """
        self.episode_id = f"episode_{datetime.now().timestamp():.0f}"
        self.time_step = 0
        self.current_time = datetime.now()
        
        # Reset portfolio
        self.cash = self.initial_cash
        self.positions = {pair: 0.0 for pair in self.asset_pairs}
        self.trade_history = []
        
        # Reset tracking
        self.episode_start_net_worth = self.initial_cash
        self.max_net_worth = self.initial_cash
        self.max_drawdown = 0.0
        self.trades_executed = 0
        self.winning_trades = 0
        self.arbitrage_opportunities_found = 0
        self.arbitrage_captured = 0
        
        # Re-initialize prices
        self._initialize_prices()
        self.market_regime = "normal"
        
        return self._get_observation()
    
    def step(self, action: TradingAction) -> TradingObservation:
        """
        Execute one trading step.
        
        Args:
            action: Trading action to execute
            
        Returns:
            Observation after action
        """
        self.time_step += 1
        self.current_time += timedelta(minutes=1)  # 1-minute candles
        
        # Update market prices (geometric Brownian motion)
        self._update_market_prices()
        
        # Detect arbitrage opportunities before execution
        arb_opps = self._detect_arbitrage()
        
        # Execute the action
        reward = self._execute_action(action, arb_opps)
        
        # Check episode termination
        done = self.time_step >= 1000  # Max 1000 steps per episode
        
        obs = self._get_observation()
        obs.reward = reward
        obs.done = done
        obs.arbitrage_opportunities = arb_opps
        
        return obs
    
    def _update_market_prices(self):
        """Update prices using geometric Brownian motion"""
        # Occasionally change market regime (affects volatility)
        if random.random() < self.regime_change_probability:
            regimes = ["normal", "high_volatility", "low_volatility"]
            self.market_regime = random.choice(regimes)
        
        # Regime multipliers
        regime_mult = {
            "normal": 1.0,
            "high_volatility": 2.0,
            "low_volatility": 0.5
        }[self.market_regime]
        
        for pair in self.asset_pairs:
            current_price = self.market_prices[pair]
            
            # Drift and volatility
            drift = 0.0001  # Small positive drift
            vol = self.volatilities[pair] * regime_mult / math.sqrt(252 * 24 * 60)  # Convert to 1-min volatility
            
            # Random shock
            shock = random.gauss(0, vol)
            
            # Update price
            new_price = current_price * math.exp(drift + shock)
            self.market_prices[pair] = new_price
            self.price_history[pair].append(new_price)
    
    def _detect_arbitrage(self) -> List[Dict]:
        """
        Detect potential arbitrage opportunities.
        
        In reality, arbitrage would be across exchanges.
        Here we simulate it via simulated "exchange rates" that deviate from fair value.
        
        Returns:
            List of detected arbitrage opportunities
        """
        opportunities = []
        
        # Simulate cross-exchange price mismatches
        for pair in self.asset_pairs:
            fair_price = self.market_prices[pair]
            
            # Exchange A (slightly overpriced)
            exchange_a_price = fair_price * (1 + random.uniform(0.0, 0.002))
            
            # Exchange B (slightly underpriced)
            exchange_b_price = fair_price * (1 - random.uniform(0.0, 0.002))
            
            # Arbitrage spread
            spread = exchange_a_price - exchange_b_price
            spread_pct = (spread / fair_price) * 100  # as percentage
            
            # Consider it an opportunity if spread > 0.1%
            if spread_pct > 0.1:
                self.arbitrage_opportunities_found += 1
                opportunities.append({
                    "asset_pair": pair,
                    "buy_exchange": "B",
                    "buy_price": exchange_b_price,
                    "sell_exchange": "A",
                    "sell_price": exchange_a_price,
                    "profit_per_unit": spread,
                    "spread_percent": spread_pct,
                })
        
        return opportunities
    
    def _execute_action(self, action: TradingAction, arb_opps: List[Dict]) -> float:
        """
        Execute a trading action and calculate reward.
        
        Reward signals:
        - Profit from closing positions
        - Bonus for capturing arbitrage
        - Penalty for transaction costs
        
        Returns:
            Immediate reward
        """
        reward = 0.0
        
        if action.action == TradeAction.HOLD:
            reward = 0.0
        
        elif action.action == TradeAction.BUY:
            price = self.market_prices[action.asset_pair]
            transaction_cost = price * action.quantity * 0.001  # 0.1% transaction cost
            
            total_cost = price * action.quantity + transaction_cost
            
            if total_cost <= self.cash:
                self.cash -= total_cost
                self.positions[action.asset_pair] += action.quantity
                self.trades_executed += 1
                
                self.trade_history.append({
                    "time": self.time_step,
                    "type": "BUY",
                    "pair": action.asset_pair,
                    "quantity": action.quantity,
                    "price": price,
                    "cost": total_cost
                })
                
                reward = -0.01  # Small cost to encourage selective trading
            else:
                reward = -0.05  # Penalty for insufficient funds
        
        elif action.action == TradeAction.SELL:
            if action.asset_pair in self.positions and self.positions[action.asset_pair] > 0:
                price = self.market_prices[action.asset_pair]
                quantity = min(action.quantity, self.positions[action.asset_pair])
                
                proceeds = price * quantity
                transaction_cost = proceeds * 0.001  # 0.1% transaction cost
                net_proceeds = proceeds - transaction_cost
                
                self.cash += net_proceeds
                self.positions[action.asset_pair] -= quantity
                self.trades_executed += 1
                
                # Reward based on position P&L
                # (This is simplified - actual P&L tracking would need entry price)
                reward = 0.01  # Small reward for executing
                
                self.trade_history.append({
                    "time": self.time_step,
                    "type": "SELL",
                    "pair": action.asset_pair,
                    "quantity": quantity,
                    "price": price,
                    "proceeds": net_proceeds
                })
        
        # Bonus for capturing arbitrage opportunities
        if arb_opps:
            for opp in arb_opps:
                if (action.asset_pair == opp["asset_pair"] and 
                    action.action in [TradeAction.BUY, TradeAction.SELL]):
                    reward += 0.1 * (opp["spread_percent"] / 100)  # Bonus proportional to spread
                    self.arbitrage_captured += 1
        
        return reward

    def _get_grader_score(self, current_net_worth: float) -> float:
        """
        Calculate score strictly between 0 and 1 (exclusive) based on the current task.
        OpenEnv validator requires: 0.0 < score < 1.0 (not 0.0, not 1.0).
        """
        raw = self._compute_raw_score(current_net_worth)
        # Clamp strictly inside (0, 1) — never exactly 0.0 or 1.0
        return max(self._SCORE_MIN, min(self._SCORE_MAX, raw))

    def _compute_raw_score(self, current_net_worth: float) -> float:
        """Compute unclamped score in [0, 1] range."""
        if self.task_id == "survival":
            # Score based on how much capital was preserved / grown
            ratio = current_net_worth / self.initial_cash  # e.g. 1.05 if up 5%
            # Map: 0.5x -> ~0.1, 1.0x -> 0.5, 1.5x -> 0.9
            score = ratio / (1.0 + ratio)
            return score

        elif self.task_id == "arbitrage":
            # Score based on arbitrage opportunities captured (target: 5)
            # Use a sigmoid-like curve so 0 captured != 0.0 and 5+ captured != 1.0
            captured = max(0, self.arbitrage_captured)
            score = captured / (captured + 5.0)  # never reaches 1.0; approaches 0 asymptotically
            return score

        elif self.task_id == "drawdown":
            # Score based on drawdown control (lower drawdown = higher score)
            # max_drawdown=0 -> score near 0.9; max_drawdown=0.10 -> score near 0.1
            score = 1.0 / (1.0 + self.max_drawdown * 20.0)
            # Bonus if profitable
            if current_net_worth > self.initial_cash:
                score = score * 0.8 + 0.15  # boost into (0.15, 0.95) range
            return score

        elif self.task_id == "momentum":
            # Score based on consecutive profitable steps
            if not self.trade_history:
                return 0.3
            profitable = sum(1 for t in self.trade_history if t.get("proceeds", 0) > t.get("cost", 0))
            ratio = profitable / max(1, len(self.trade_history))
            return 0.1 + ratio * 0.8  # maps to (0.1, 0.9)

        # Fallback: unknown task_id — return mid-range score
        return 0.5
    
    def _get_observation(self) -> TradingObservation:
        """Generate current observation"""
        # Calculate market snapshots
        market_snapshots = []
        for pair in self.asset_pairs:
            price = self.market_prices[pair]
            spread = price * 0.0005  # 0.05% spread
            
            snapshot = MarketSnapshot(
                timestamp=self.time_step,
                asset_pair=pair,
                bid_price=price - spread / 2,
                ask_price=price + spread / 2,
                bid_volume=random.uniform(100, 1000),
                ask_volume=random.uniform(100, 1000),
            )
            market_snapshots.append(snapshot)
        
        # Calculate portfolio state and P&L
        current_net_worth = self.cash
        for pair in self.asset_pairs:
            position_value = self.positions[pair] * self.market_prices[pair]
            current_net_worth += position_value
        
        pnl = current_net_worth - self.episode_start_net_worth
        pnl_percent = (pnl / self.episode_start_net_worth) * 100
        
        # Update max drawdown
        if current_net_worth > self.max_net_worth:
            self.max_net_worth = current_net_worth
        else:
            drawdown = (self.max_net_worth - current_net_worth) / self.max_net_worth
            self.max_drawdown = max(self.max_drawdown, drawdown)
        
        portfolio = PortfolioState(
            cash=self.cash,
            positions=self.positions.copy(),
        )
        
        # Calculate market trend
        if len(self.price_history[self.asset_pairs[0]]) > 20:
            recent_prices = self.price_history[self.asset_pairs[0]][-20:]
            if recent_prices[-1] > recent_prices[0]:
                trend = "bullish"
            else:
                trend = "bearish"
        else:
            trend = "sideways"
        
        return TradingObservation(
            market_snapshots=market_snapshots,
            portfolio=portfolio,
            net_worth=current_net_worth,
            pnl=pnl,
            pnl_percent=pnl_percent,
            done=False,
            grader_score=self._get_grader_score(current_net_worth),
            metadata={
                "market_regime": self.market_regime,
                "trend": trend,
            }
        )
    
    @property
    def state(self) -> TradingState:
        """Get episode state metadata"""
        return TradingState(
            episode_id=self.episode_id,
            step_count=self.time_step,
            elapsed_time=float(self.time_step),  # in minutes
            market_volatility=sum(self.volatilities.values()) / len(self.volatilities),
            trend="bullish" if self.time_step % 100 < 50 else "bearish",
            max_drawdown=self.max_drawdown,
            cumulative_pnl=sum(t.get("proceeds", 0) for t in self.trade_history),
            num_trades=self.trades_executed,
            win_rate=self.winning_trades / max(1, self.trades_executed),
            total_arbitrage_found=self.arbitrage_opportunities_found,
            arbitrage_captured=self.arbitrage_captured,
            grader_score=self._get_grader_score(self.cash + sum(self.positions[p] * self.market_prices[p] for p in self.asset_pairs)),
        )
