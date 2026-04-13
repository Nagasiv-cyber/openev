"""
eaa_engine.py — Efficiency-Adjusted Alpha (EAA) Calculation Engine

The core quantitative formula for GreenArb's sustainable trading thesis:

    EAA = (alpha_gross - S(v) - I(v,sigma) - tau(h)) / (sqrt(Var(r)) * E(t))

Components:
  - alpha_gross  : Raw P&L returns
  - S(v)         : Slippage (Almgren-Chriss linear-temporary model)
  - I(v, sigma)  : Market impact (Kyle 1985 square-root model)
  - tau(h)       : Dynamic carbon tax (fluctuates with grid renewable mix)
  - Var(r)       : Return variance (risk denominator)
  - E(t)         : Energy per trade (Performance-per-Watt denominator)

ESG Metric:
  GAR = net_alpha / kgCO2e_per_1M_traded  (Green Alpha Ratio — target > 500)
"""

import logging
import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Optional

logger = logging.getLogger("EAAEngine")


# ============================================================================
# EAA RESULT DATA STRUCTURE
# ============================================================================

@dataclass
class EAAResult:
    """Complete EAA calculation result with all sub-components."""
    eaa_score: float = 0.0
    alpha_gross: float = 0.0
    slippage_cost: float = 0.0
    market_impact: float = 0.0
    carbon_tax: float = 0.0
    alpha_net: float = 0.0
    return_volatility: float = 0.0
    energy_per_trade_wh: float = 1.0
    green_alpha_ratio: float = 0.0
    carbon_emitted_kg: float = 0.0
    tau_multiplier: float = 1.0

    def to_dict(self) -> Dict:
        return {
            "eaa_score": round(self.eaa_score, 4),
            "alpha_gross_bps": round(self.alpha_gross * 10000, 2),
            "slippage_bps": round(self.slippage_cost * 10000, 2),
            "market_impact_bps": round(self.market_impact * 10000, 2),
            "carbon_tax_bps": round(self.carbon_tax * 10000, 2),
            "alpha_net_bps": round(self.alpha_net * 10000, 2),
            "return_vol": round(self.return_volatility, 4),
            "energy_per_trade_wh": round(self.energy_per_trade_wh, 2),
            "green_alpha_ratio": round(self.green_alpha_ratio, 1),
            "carbon_emitted_kg": round(self.carbon_emitted_kg, 4),
            "tau_multiplier": round(self.tau_multiplier, 2),
        }


# ============================================================================
# SLIPPAGE MODEL (Almgren-Chriss)
# ============================================================================

class AlmgrenChrissSlippage:
    """
    Linear-temporary market impact model (Almgren & Chriss, 2001).

    S(v) = eta * sigma * (v / V_ADV)^0.6

    Parameters:
      eta    : Exchange-specific slippage coefficient
      sigma  : Current asset volatility
      v      : Order volume
      V_ADV  : Average daily volume
    """

    # Exchange-specific coefficients
    EXCHANGE_ETA = {
        "NSE": 0.12,      # National Stock Exchange (India) — wider spreads
        "NYSE": 0.08,     # New York Stock Exchange — tighter spreads
        "BINANCE": 0.10,  # Crypto CEX
        "UNISWAP": 0.15,  # DEX — higher slippage
        "DEFAULT": 0.10,
    }

    @classmethod
    def calculate(cls, order_volume: float, avg_daily_volume: float,
                  volatility: float, exchange: str = "DEFAULT") -> float:
        """Calculate slippage cost as a fraction of order value."""
        eta = cls.EXCHANGE_ETA.get(exchange.upper(), cls.EXCHANGE_ETA["DEFAULT"])

        if avg_daily_volume <= 0:
            return 0.0

        participation_rate = order_volume / avg_daily_volume
        slippage = eta * volatility * (participation_rate ** 0.6)

        return max(0.0, slippage)


# ============================================================================
# MARKET IMPACT MODEL (Kyle 1985)
# ============================================================================

class KyleMarketImpact:
    """
    Square-root permanent impact model (Kyle, 1985).

    I(v, sigma) = gamma * sigma * sqrt(v / V_ADV)

    Parameters:
      gamma  : Permanent impact coefficient (calibrated per instrument)
      sigma  : Current asset volatility
      v      : Order volume
      V_ADV  : Average daily volume
    """

    # Instrument-class gamma calibration
    INSTRUMENT_GAMMA = {
        "EQUITY_LARGE_CAP": 0.05,   # Nifty 50 components
        "EQUITY_MID_CAP": 0.08,     # Mid-cap stocks
        "CRYPTO_MAJOR": 0.06,       # BTC, ETH
        "CRYPTO_ALT": 0.12,         # Altcoins
        "FX_MAJOR": 0.03,           # USD/INR
        "DEFAULT": 0.06,
    }

    @classmethod
    def calculate(cls, order_volume: float, avg_daily_volume: float,
                  volatility: float, instrument_class: str = "DEFAULT") -> float:
        """Calculate permanent market impact as a fraction of order value."""
        gamma = cls.INSTRUMENT_GAMMA.get(instrument_class.upper(),
                                          cls.INSTRUMENT_GAMMA["DEFAULT"])

        if avg_daily_volume <= 0:
            return 0.0

        participation_rate = order_volume / avg_daily_volume
        impact = gamma * volatility * np.sqrt(participation_rate)

        return max(0.0, impact)


# ============================================================================
# DYNAMIC CARBON TAX
# ============================================================================

class DynamicCarbonTax:
    """
    Time-of-day carbon tax that penalizes trading during dirty-grid hours.

    tau(h) = tau_base * (1 + beta * (1 - RE_mix(h)))

    Where:
      h        = hour of day (UTC)
      RE_mix   = renewable energy fraction of grid at hour h
      tau_base = 0.0002 (2 basis points base carbon cost)
      beta     = 3.0 (amplification — coal-heavy hours cost 4x more)
    """

    TAU_BASE = 0.0002   # 2 bps base
    BETA = 3.0           # Amplification

    @classmethod
    def calculate(cls, renewable_mix: float) -> float:
        """
        Calculate carbon tax for a given renewable mix fraction.
        Returns: absolute tax as fraction (e.g. 0.0006 = 6 bps)
        """
        tau = cls.TAU_BASE * (1 + cls.BETA * (1 - renewable_mix))
        return tau

    @classmethod
    def get_multiplier(cls, renewable_mix: float) -> float:
        """Return multiplier relative to base (e.g. 2.8x)."""
        return 1 + cls.BETA * (1 - renewable_mix)


# ============================================================================
# EAA CALCULATOR (Main Engine)
# ============================================================================

class EAACalculator:
    """
    Efficiency-Adjusted Alpha Calculator.

    Core formula:
      EAA = (alpha_gross - S(v) - I(v,sigma) - tau(h)) / (sqrt(Var(r)) * E(t))

    Performance-per-Watt is embedded directly into the alpha formula —
    the less energy you use per trade, the higher your EAA.
    """

    def __init__(self):
        self.slippage_model = AlmgrenChrissSlippage()
        self.impact_model = KyleMarketImpact()
        self.carbon_tax = DynamicCarbonTax()
        self._trade_count = 0
        self._cumulative_returns = []

    def calculate(
        self,
        alpha_gross: float,
        order_volume: float,
        avg_daily_volume: float,
        volatility: float,
        renewable_mix: float,
        energy_per_trade_wh: float,
        returns_history: List[float],
        carbon_emitted_kg: float = 0.0,
        exchange: str = "DEFAULT",
        instrument_class: str = "DEFAULT",
    ) -> EAAResult:
        """
        Calculate the full EAA score.

        Args:
            alpha_gross: Raw P&L return (as fraction, e.g. 0.005 = 50 bps)
            order_volume: Volume of this order
            avg_daily_volume: Average daily volume for this instrument
            volatility: Current realized volatility (annualized)
            renewable_mix: Grid renewable fraction at current hour (0–1)
            energy_per_trade_wh: Watt-hours consumed per trade
            returns_history: List of recent returns for variance calculation
            carbon_emitted_kg: Total CO2 emitted so far
            exchange: Exchange name for slippage calibration
            instrument_class: Instrument type for impact calibration
        """

        # 1. Slippage: S(v)
        slippage = self.slippage_model.calculate(
            order_volume, avg_daily_volume, volatility, exchange
        )

        # 2. Market Impact: I(v, sigma)
        impact = self.impact_model.calculate(
            order_volume, avg_daily_volume, volatility, instrument_class
        )

        # 3. Carbon Tax: tau(h)
        tau = self.carbon_tax.calculate(renewable_mix)
        tau_mult = self.carbon_tax.get_multiplier(renewable_mix)

        # 4. Net Alpha
        alpha_net = alpha_gross - slippage - impact - tau

        # 5. Return Volatility: sqrt(Var(r))
        if len(returns_history) >= 2:
            return_vol = float(np.std(returns_history))
        else:
            return_vol = 0.01  # Default

        # 6. Energy Denominator: E(t)
        energy_denom = max(energy_per_trade_wh, 0.001)  # Prevent div by zero

        # 7. EAA Score
        risk_energy_denom = return_vol * energy_denom
        if risk_energy_denom > 0:
            eaa = alpha_net / risk_energy_denom
        else:
            eaa = 0.0

        # 8. Green Alpha Ratio: GAR = net_alpha / kgCO2e per $1M traded
        if carbon_emitted_kg > 0:
            gar = (alpha_net * 1_000_000) / carbon_emitted_kg
        else:
            gar = float('inf') if alpha_net > 0 else 0.0
        gar = min(gar, 9999.9)  # Cap for display

        return EAAResult(
            eaa_score=eaa,
            alpha_gross=alpha_gross,
            slippage_cost=slippage,
            market_impact=impact,
            carbon_tax=tau,
            alpha_net=alpha_net,
            return_volatility=return_vol,
            energy_per_trade_wh=energy_per_trade_wh,
            green_alpha_ratio=gar,
            carbon_emitted_kg=carbon_emitted_kg,
            tau_multiplier=tau_mult,
        )

    def quick_eaa(self, pnl: float, volatility: float,
                  renewable_mix: float, power_w: float) -> EAAResult:
        """
        Simplified EAA for the dashboard — uses sensible defaults.
        Called once per global metrics update.
        """
        # Sensible defaults for swarm-level aggregation
        alpha_gross = pnl / 1_000_000  # Normalize to $1M AUM
        order_volume = 10.0
        adv = 10_000.0
        energy = max(power_w * 0.5 / 3600, 0.001)  # Power for 0.5s tick → Wh

        self._cumulative_returns.append(alpha_gross)
        if len(self._cumulative_returns) > 200:
            self._cumulative_returns = self._cumulative_returns[-200:]

        carbon_kg = energy * 0.4 / 1000  # Rough: 400 gCO2/kWh

        return self.calculate(
            alpha_gross=alpha_gross,
            order_volume=order_volume,
            avg_daily_volume=adv,
            volatility=volatility,
            renewable_mix=renewable_mix,
            energy_per_trade_wh=energy,
            returns_history=self._cumulative_returns,
            carbon_emitted_kg=carbon_kg,
        )
