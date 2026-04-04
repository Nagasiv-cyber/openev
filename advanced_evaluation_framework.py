"""
Advanced Evaluation Framework for Multi-Market Arbitrage RL Environment

Computes real financial metrics:
  - Profit & Loss (absolute)
  - Return on Investment (%)
  - Sharpe Ratio (risk-adjusted returns)
  - Sortino Ratio (downside risk)
  - Maximum Drawdown (peak-to-trough)
  - Calmar Ratio (return/drawdown)
  - Win Rate (% winning trades)
  - Profit Factor (gross wins / gross losses)
  - Trade Efficiency (avg profit per trade)
  - Information Ratio (excess return / tracking error)
  - Stability (variance of monthly returns)
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import numpy as np
from scipy import stats
import json


@dataclass
class Trade:
    """Record of a single trade"""
    timestamp: float
    asset_pair: str
    side: str  # "buy" or "sell"
    quantity: float
    entry_price: float
    exit_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    duration: Optional[float] = None  # Steps held


@dataclass
class FinancialMetrics:
    """Complete financial metrics for an episode"""
    
    # Returns
    total_profit: float
    roi: float  # Return on investment %
    total_return_pct: float
    
    # Risk metrics
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float  # Return / Max Drawdown
    
    # Trade quality
    win_rate: float
    profit_factor: float  # Gross wins / Gross losses
    avg_trade_profit: float
    median_trade_profit: float
    largest_winner: float
    largest_loser: float
    
    # Efficiency
    trades_total: int
    trades_winning: int
    trades_losing: int
    avg_duration: float  # Average holding time
    trade_efficiency: float  # Profit per trade
    
    # Risk-adjusted metrics
    information_ratio: float
    sortino_ratio_custom: float
    
    # Portfolio metrics
    final_portfolio_value: float
    portfolio_volatility: float
    stability: float  # Variance of returns
    
    # Inventory management
    avg_inventory: float
    max_inventory: float
    inventory_cost: float


class PerformanceEvaluator:
    """Evaluate agent performance with financial metrics"""
    
    def __init__(self, initial_capital: float = 100_000, risk_free_rate: float = 0.01):
        self.initial_capital = initial_capital
        self.risk_free_rate = risk_free_rate
    
    def evaluate_episode(
        self,
        portfolio_values: List[float],
        trades: List[Trade],
        inventory_history: List[Dict[str, float]],
    ) -> FinancialMetrics:
        """
        Evaluate a complete episode
        
        Args:
            portfolio_values: List of portfolio values over time
            trades: List of executed trades
            inventory_history: History of inventory positions
        
        Returns:
            Complete metrics
        """
        
        # Basic returns
        final_value = portfolio_values[-1]
        total_profit = final_value - self.initial_capital
        roi = (total_profit / self.initial_capital) * 100
        total_return_pct = (final_value / self.initial_capital - 1) * 100
        
        # Convert to returns
        returns = np.diff(portfolio_values) / portfolio_values[:-1]
        
        # Risk metrics
        sharpe = self._calculate_sharpe(returns)
        sortino = self._calculate_sortino(returns)
        max_dd = self._calculate_max_drawdown(portfolio_values)
        calmar = roi / max(max_dd, 0.01) if max_dd > 0 else 0
        
        # Trade metrics
        win_rate, profit_factor, trades_stats = self._analyze_trades(trades)
        
        # Portfolio metrics
        portfolio_vol = np.std(returns) if len(returns) > 0 else 0
        stability = self._calculate_stability(returns)
        info_ratio = self._calculate_information_ratio(returns)
        
        # Inventory metrics
        avg_inv, max_inv, inv_cost = self._analyze_inventory(inventory_history)
        
        return FinancialMetrics(
            total_profit=total_profit,
            roi=roi,
            total_return_pct=total_return_pct,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=max_dd,
            calmar_ratio=calmar,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_trade_profit=trades_stats["avg"],
            median_trade_profit=trades_stats["median"],
            largest_winner=trades_stats["max"],
            largest_loser=trades_stats["min"],
            trades_total=len(trades),
            trades_winning=sum(1 for t in trades if (t.pnl or 0) > 0),
            trades_losing=sum(1 for t in trades if (t.pnl or 0) < 0),
            avg_duration=trades_stats["avg_duration"],
            trade_efficiency=trades_stats["avg"] if len(trades) > 0 else 0,
            information_ratio=info_ratio,
            sortino_ratio_custom=sortino,
            final_portfolio_value=final_value,
            portfolio_volatility=portfolio_vol,
            stability=stability,
            avg_inventory=avg_inv,
            max_inventory=max_inv,
            inventory_cost=inv_cost,
        )
    
    def _calculate_sharpe(self, returns: np.ndarray, periods: int = 252) -> float:
        """Calculate Sharpe ratio (annual)"""
        if len(returns) < 2:
            return 0.0
        
        excess_returns = returns - (self.risk_free_rate / periods)
        if np.std(excess_returns) == 0:
            return 0.0
        
        sharpe = np.mean(excess_returns) / np.std(excess_returns)
        return sharpe * np.sqrt(periods)  # Annualize
    
    def _calculate_sortino(self, returns: np.ndarray, periods: int = 252) -> float:
        """Calculate Sortino ratio (downside risk only)"""
        if len(returns) < 2:
            return 0.0
        
        excess_returns = returns - (self.risk_free_rate / periods)
        downside_returns = np.minimum(excess_returns, 0)
        downside_std = np.std(downside_returns)
        
        if downside_std == 0:
            return 0.0
        
        sortino = np.mean(excess_returns) / downside_std
        return sortino * np.sqrt(periods)
    
    def _calculate_max_drawdown(self, values: List[float]) -> float:
        """Calculate maximum drawdown"""
        if len(values) < 2:
            return 0.0
        
        peak = values[0]
        max_dd = 0.0
        
        for value in values:
            if value > peak:
                peak = value
            dd = (peak - value) / peak
            max_dd = max(max_dd, dd)
        
        return max_dd
    
    def _calculate_stability(self, returns: np.ndarray) -> float:
        """Calculate return stability (variance)"""
        return np.std(returns) if len(returns) > 0 else 0.0
    
    def _calculate_information_ratio(self, returns: np.ndarray) -> float:
        """Calculate information ratio vs risk-free benchmark"""
        if len(returns) < 2:
            return 0.0
        
        excess_returns = returns - (self.risk_free_rate / 252)
        tracking_error = np.std(excess_returns)
        
        if tracking_error == 0:
            return 0.0
        
        return np.mean(excess_returns) / tracking_error
    
    def _analyze_trades(self, trades: List[Trade]) -> Tuple[float, float, Dict]:
        """Analyze trade quality"""
        if len(trades) == 0:
            return 0.0, 0.0, {
                "avg": 0.0,
                "median": 0.0,
                "max": 0.0,
                "min": 0.0,
                "avg_duration": 0.0,
            }
        
        # Calculate PnL for each trade
        pnls = [t.pnl or 0 for t in trades]
        
        # Win rate
        wins = sum(1 for p in pnls if p > 0)
        win_rate = wins / len(trades)
        
        # Profit factor
        gross_wins = sum(p for p in pnls if p > 0)
        gross_losses = abs(sum(p for p in pnls if p < 0))
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else 0
        
        # Statistics
        durations = [t.duration or 0 for t in trades]
        
        return win_rate, profit_factor, {
            "avg": np.mean(pnls),
            "median": np.median(pnls),
            "max": np.max(pnls),
            "min": np.min(pnls),
            "avg_duration": np.mean(durations),
        }
    
    def _analyze_inventory(self, inventory_history: List[Dict[str, float]]) -> Tuple[float, float, float]:
        """Analyze inventory management"""
        if len(inventory_history) == 0:
            return 0.0, 0.0, 0.0
        
        # Total inventory over time
        total_invs = [sum(inv.values()) for inv in inventory_history]
        
        avg_inv = np.mean(total_invs)
        max_inv = np.max(total_invs)
        
        # Inventory cost (penalty for holding)
        inv_cost = sum(inv**2 for inv in total_invs) * 0.001  # Quadratic penalty
        
        return avg_inv, max_inv, inv_cost


# ============================================================================
# COMPOSITE SCORING SYSTEM
# ============================================================================

class CompositeScorer:
    """Combine multiple metrics into single score (0-1)"""
    
    # Weights for different metrics (must sum to 1.0)
    WEIGHTS = {
        "profitability": 0.25,      # ROI/Return
        "risk_adjustment": 0.25,    # Sharpe Ratio
        "consistency": 0.15,        # Win Rate
        "drawdown": 0.15,           # Max Drawdown (lower is better)
        "efficiency": 0.15,         # Trade efficiency
        "stability": 0.10,          # Return stability
    }
    
    @staticmethod
    def normalize(value: float, min_val: float, max_val: float) -> float:
        """Normalize value to 0-1 range"""
        if max_val == min_val:
            return 0.5
        return max(0, min(1, (value - min_val) / (max_val - min_val)))
    
    @staticmethod
    def compute_score(metrics: FinancialMetrics) -> float:
        """
        Compute composite score from 0 to 1
        
        0.0 = Terrible (losing money)
        0.5 = Average (beating risk-free rate)
        1.0 = Exceptional (top-tier performance)
        """
        
        # Component scores (each 0-1)
        
        # 1. Profitability: ROI (normalize to 0-100%)
        profitability_score = CompositeScorer.normalize(
            metrics.total_return_pct, -50, 100
        )
        
        # 2. Risk adjustment: Sharpe Ratio (0-3 is good)
        sharpe_score = CompositeScorer.normalize(
            metrics.sharpe_ratio, 0, 3
        )
        
        # 3. Consistency: Win Rate (0-100%)
        consistency_score = CompositeScorer.normalize(
            metrics.win_rate * 100, 30, 70
        )
        
        # 4. Drawdown: Lower is better, penalize high drawdown
        drawdown_score = 1 - CompositeScorer.normalize(
            metrics.max_drawdown * 100, 0, 50
        )
        
        # 5. Efficiency: Profit per trade (normalize to $1000 baseline)
        efficiency_score = CompositeScorer.normalize(
            metrics.trade_efficiency, -1000, 5000
        )
        
        # 6. Stability: Lower volatility is better
        stability_score = 1 - CompositeScorer.normalize(
            metrics.portfolio_volatility, 0, 0.5
        )
        
        # Weighted average
        composite_score = (
            profitability_score * CompositeScorer.WEIGHTS["profitability"] +
            sharpe_score * CompositeScorer.WEIGHTS["risk_adjustment"] +
            consistency_score * CompositeScorer.WEIGHTS["consistency"] +
            drawdown_score * CompositeScorer.WEIGHTS["drawdown"] +
            efficiency_score * CompositeScorer.WEIGHTS["efficiency"] +
            stability_score * CompositeScorer.WEIGHTS["stability"]
        )
        
        return composite_score
    
    @staticmethod
    def get_performance_tier(score: float) -> str:
        """Classify performance tier"""
        if score >= 0.8:
            return "Exceptional (A+)"
        elif score >= 0.7:
            return "Excellent (A)"
        elif score >= 0.6:
            return "Very Good (B+)"
        elif score >= 0.5:
            return "Good (B)"
        elif score >= 0.4:
            return "Above Average (C+)"
        elif score >= 0.3:
            return "Average (C)"
        else:
            return "Below Average (D)"


# ============================================================================
# COMPREHENSIVE REPORTING
# ============================================================================

class EvaluationReport:
    """Generate comprehensive evaluation report"""
    
    @staticmethod
    def generate_report(
        agent_name: str,
        metrics: FinancialMetrics,
        benchmark_metrics: Optional[FinancialMetrics] = None,
    ) -> str:
        """Generate formatted evaluation report"""
        
        score = CompositeScorer.compute_score(metrics)
        tier = CompositeScorer.get_performance_tier(score)
        
        report = f"""
╔════════════════════════════════════════════════════════════════╗
║              COMPREHENSIVE EVALUATION REPORT                   ║
║  Agent: {agent_name:50s} ║
╚════════════════════════════════════════════════════════════════╝

📊 PERFORMANCE SCORE: {score:.2f}/1.00 ({tier})

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💰 PROFITABILITY METRICS
  Total Profit:           ${metrics.total_profit:>12,.2f}
  ROI:                    {metrics.roi:>12.2f}%
  Total Return:           {metrics.total_return_pct:>12.2f}%
  Final Portfolio Value:  ${metrics.final_portfolio_value:>12,.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 RISK METRICS
  Sharpe Ratio:           {metrics.sharpe_ratio:>12.3f}
  Sortino Ratio:          {metrics.sortino_ratio:>12.3f}
  Maximum Drawdown:       {metrics.max_drawdown*100:>12.2f}%
  Calmar Ratio:           {metrics.calmar_ratio:>12.3f}
  Portfolio Volatility:   {metrics.portfolio_volatility*100:>12.2f}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 TRADE QUALITY
  Total Trades:           {metrics.trades_total:>12d}
  Winning Trades:         {metrics.trades_winning:>12d}
  Losing Trades:          {metrics.trades_losing:>12d}
  Win Rate:               {metrics.win_rate*100:>12.2f}%
  Profit Factor:          {metrics.profit_factor:>12.3f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚙️  TRADE EFFICIENCY
  Avg Trade Profit:       ${metrics.avg_trade_profit:>12,.2f}
  Median Trade Profit:    ${metrics.median_trade_profit:>12,.2f}
  Largest Winner:         ${metrics.largest_winner:>12,.2f}
  Largest Loser:          ${metrics.largest_loser:>12,.2f}
  Avg Position Duration:  {metrics.avg_duration:>12.1f} steps
  Trade Efficiency:       ${metrics.trade_efficiency:>12,.2f}/trade

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📦 INVENTORY MANAGEMENT
  Avg Inventory:          {metrics.avg_inventory:>12.3f} units
  Max Inventory:          {metrics.max_inventory:>12.3f} units
  Inventory Cost:         ${metrics.inventory_cost:>12,.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎓 ADVANCED METRICS
  Information Ratio:      {metrics.information_ratio:>12.3f}
  Return Stability:       {metrics.stability:>12.3f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        
        if benchmark_metrics:
            report += f"""
📊 COMPARISON TO BENCHMARK

  Metric                  Agent           Benchmark       Advantage
  ─────────────────────────────────────────────────────────────────
  ROI                     {metrics.roi:>6.1f}%         {benchmark_metrics.roi:>6.1f}%        {'✓' if metrics.roi > benchmark_metrics.roi else '✗'}
  Sharpe Ratio            {metrics.sharpe_ratio:>6.2f}            {benchmark_metrics.sharpe_ratio:>6.2f}           {'✓' if metrics.sharpe_ratio > benchmark_metrics.sharpe_ratio else '✗'}
  Win Rate                {metrics.win_rate*100:>6.1f}%         {benchmark_metrics.win_rate*100:>6.1f}%        {'✓' if metrics.win_rate > benchmark_metrics.win_rate else '✗'}
  Max Drawdown            {metrics.max_drawdown*100:>6.1f}%         {benchmark_metrics.max_drawdown*100:>6.1f}%        {'✓' if metrics.max_drawdown < benchmark_metrics.max_drawdown else '✗'}

"""
        
        report += """
╚════════════════════════════════════════════════════════════════╝
"""
        
        return report
    
    @staticmethod
    def compare_agents(agents_metrics: Dict[str, FinancialMetrics]) -> str:
        """Generate comparison of multiple agents"""
        
        report = """
╔════════════════════════════════════════════════════════════════╗
║              AGENT COMPARISON REPORT                           ║
╚════════════════════════════════════════════════════════════════╝

Agent Ranking by Composite Score:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
        
        # Calculate scores for all agents
        scores = {
            name: CompositeScorer.compute_score(metrics)
            for name, metrics in agents_metrics.items()
        }
        
        # Sort by score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        medals = ["🥇", "🥈", "🥉"]
        
        for rank, (agent_name, score) in enumerate(ranked):
            medal = medals[rank] if rank < 3 else "  "
            metrics = agents_metrics[agent_name]
            tier = CompositeScorer.get_performance_tier(score)
            
            report += f"{medal} {rank+1}. {agent_name:30s} {score:.3f} ({tier})\n"
            report += f"    ROI: {metrics.roi:>7.2f}% | Sharpe: {metrics.sharpe_ratio:>6.2f} | Max DD: {metrics.max_drawdown*100:>5.1f}%\n\n"
        
        report += "╚════════════════════════════════════════════════════════════════╝\n"
        
        return report


print("""
✅ EVALUATION FRAMEWORK

Metrics Computed:
  ✓ Profitability (ROI, Return %)
  ✓ Risk Metrics (Sharpe, Sortino, Max Drawdown)
  ✓ Trade Quality (Win Rate, Profit Factor)
  ✓ Efficiency (Profit per trade)
  ✓ Stability (Return consistency)
  ✓ Advanced (Information Ratio)
  
Composite Score: 0-1 scale
  0.0 = Terrible
  0.5 = Average (beats risk-free)
  1.0 = Exceptional
  
Performance Tiers: A+ (0.8+), A (0.7+), B+ (0.6+), etc.
""")
