"""
fpga_scheduler.py — Dark-Hours FPGA Simulation Pipeline

During the 12-hour liquidity gap (when both NSE and NYSE are closed),
the MI325X GPU suspends to save power. The AMD Alveo U250 FPGA takes over
at 25W to run:

  Phase 1: Overnight News Digest (sentiment extraction via INT8 NLP)
  Phase 2: Monte Carlo Opening Bell Simulation (100K scenarios)
  Phase 3: Order Book Pre-Staging (Almgren-Chriss optimal sizing)

This module simulates the FPGA pipeline for demo purposes.
On real hardware, the HLS kernels would be deployed via Vitis.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import numpy as np

logger = logging.getLogger("FPGAScheduler")


# ============================================================================
# DATA STRUCTURES
# ============================================================================

@dataclass
class FPGAStatus:
    """Current FPGA pipeline status."""
    active: bool = False
    phase: str = "IDLE"              # IDLE / NEWS_DIGEST / MONTE_CARLO / PRE_STAGING
    phase_progress_pct: float = 0.0
    power_draw_w: float = 0.0
    simulations_completed: int = 0
    opening_prediction: Dict = field(default_factory=dict)
    pre_staged_orders: int = 0
    sentiment_signal: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "active": self.active,
            "phase": self.phase,
            "phase_progress_pct": round(self.phase_progress_pct, 1),
            "power_draw_w": round(self.power_draw_w, 1),
            "simulations_completed": self.simulations_completed,
            "opening_prediction": self.opening_prediction,
            "pre_staged_orders": self.pre_staged_orders,
            "sentiment_signal": round(self.sentiment_signal, 3),
        }


@dataclass
class MonteCarloResult:
    """Result from Monte Carlo opening bell simulation."""
    instrument: str
    expected_open: float
    std_dev: float
    p_up: float           # Probability of gap-up
    p_down: float         # Probability of gap-down
    scenarios_run: int
    confidence: float     # 0–1


@dataclass
class PreStagedOrder:
    """An order pre-computed during dark hours, ready to fire at market open."""
    instrument: str
    side: str             # BUY / SELL
    quantity: float
    limit_price: float
    alpha_expected_bps: float
    confidence: float


# ============================================================================
# FPGA DARK-HOURS PIPELINE
# ============================================================================

class FPGADarkHoursPipeline:
    """
    Manages the 3-phase overnight pipeline running on the FPGA.

    Phases:
      1. NEWS_DIGEST   (21:30–00:00 IST): Parse overnight news → sentiment vector
      2. MONTE_CARLO   (00:00–05:00 IST): Run 100K opening bell simulations
      3. PRE_STAGING   (05:00–09:00 IST): Compute and stage optimal opening orders

    In simulation mode: Advances through phases based on tick count.
    On real FPGA: Would be controlled via Xilinx XRT / Vitis runtime.
    """

    FPGA_POWER_W = 25.0            # Alveo U250 operating power
    TOTAL_SIMULATIONS = 100_000    # Target Monte Carlo scenarios

    INSTRUMENTS = ["NIFTY50", "BANKNIFTY", "SPY", "QQQ",
                   "BTC/USD", "ETH/USD"]

    def __init__(self):
        self._active = False
        self._phase = "IDLE"
        self._tick_in_phase = 0
        self._total_ticks = 0
        self._simulations_done = 0

        # Phase outputs
        self._sentiment_signals: Dict[str, float] = {}
        self._mc_results: Dict[str, MonteCarloResult] = {}
        self._pre_staged: List[PreStagedOrder] = []

        self.status = FPGAStatus()

    def is_dark_hours(self, utc_hour: int) -> bool:
        """Check if we're in the liquidity gap (both markets closed)."""
        # NSE closes ~10:00 UTC, NYSE closes ~21:00 UTC
        # Dark hours: approximately 21:00 UTC → 03:30 UTC
        return utc_hour >= 21 or utc_hour < 4

    def activate(self):
        """Turn on FPGA pipeline (called when entering dark hours)."""
        if self._active:
            return
        self._active = True
        self._phase = "NEWS_DIGEST"
        self._tick_in_phase = 0
        self._simulations_done = 0
        self._sentiment_signals = {}
        self._mc_results = {}
        self._pre_staged = []
        logger.info("FPGA Dark-Hours Pipeline ACTIVATED. Phase: NEWS_DIGEST")

    def deactivate(self):
        """Suspend FPGA (called when market opens)."""
        if not self._active:
            return
        self._active = False
        self._phase = "IDLE"
        logger.info("FPGA Pipeline SUSPENDED. GPU taking over.")

    def tick(self, utc_hour: int) -> FPGAStatus:
        """
        Advance the FPGA pipeline by one tick.
        Called from the swarm simulation loop during dark hours.
        """
        if not self._active:
            self.status = FPGAStatus(active=False, phase="IDLE")
            return self.status

        self._tick_in_phase += 1
        self._total_ticks += 1

        # Phase transitions based on simulated time progression
        if self._phase == "NEWS_DIGEST":
            self._run_news_digest()
            if self._tick_in_phase > 50:  # ~25 seconds of ticks
                self._phase = "MONTE_CARLO"
                self._tick_in_phase = 0
                logger.info("FPGA Phase → MONTE_CARLO")

        elif self._phase == "MONTE_CARLO":
            self._run_monte_carlo()
            if self._simulations_done >= self.TOTAL_SIMULATIONS:
                self._phase = "PRE_STAGING"
                self._tick_in_phase = 0
                logger.info("FPGA Phase → PRE_STAGING (100K sims complete)")

        elif self._phase == "PRE_STAGING":
            self._run_pre_staging()
            if self._tick_in_phase > 30:
                self._phase = "COMPLETE"
                logger.info("FPGA Pipeline COMPLETE. Orders pre-staged.")

        # Build status
        progress = self._calculate_progress()

        self.status = FPGAStatus(
            active=True,
            phase=self._phase,
            phase_progress_pct=progress,
            power_draw_w=self.FPGA_POWER_W * (0.85 + np.random.uniform(0, 0.15)),
            simulations_completed=self._simulations_done,
            opening_prediction=self._get_opening_prediction(),
            pre_staged_orders=len(self._pre_staged),
            sentiment_signal=np.mean(list(self._sentiment_signals.values())) if self._sentiment_signals else 0.0,
        )

        return self.status

    # ── Phase 1: News Digest ──────────────────────────────────────────────

    def _run_news_digest(self):
        """
        Simulate overnight news sentiment extraction.
        On real FPGA: INT8 quantized NLP model processes Reuters/Bloomberg feeds.
        """
        for instrument in self.INSTRUMENTS:
            if instrument not in self._sentiment_signals:
                # Simulate: sentiment drifts based on random overnight events
                self._sentiment_signals[instrument] = np.clip(
                    np.random.normal(0.05, 0.3), -1.0, 1.0
                )

    # ── Phase 2: Monte Carlo Opening Bell ─────────────────────────────────

    def _run_monte_carlo(self):
        """
        Run Monte Carlo simulations of market opening scenarios.
        On real FPGA: Parallel path simulation in FPGA fabric.
        """
        # Each tick processes a batch of simulations
        batch_size = 2000  # FPGA can do 2K paths per tick
        self._simulations_done = min(
            self._simulations_done + batch_size,
            self.TOTAL_SIMULATIONS
        )

        # Generate results for each instrument
        for instrument in self.INSTRUMENTS:
            if instrument not in self._mc_results:
                # Previous close (mock)
                prev_close = {
                    "NIFTY50": 22500, "BANKNIFTY": 48000,
                    "SPY": 530, "QQQ": 450,
                    "BTC/USD": 60000, "ETH/USD": 3000,
                }.get(instrument, 100)

                # Simulate distribution
                sentiment = self._sentiment_signals.get(instrument, 0)
                drift = sentiment * 0.005  # Sentiment biases the drift
                overnight_vol = 0.015      # 1.5% overnight vol

                simulated_opens = prev_close * (1 + np.random.normal(
                    drift, overnight_vol, size=min(self._simulations_done, 10000)
                ))

                self._mc_results[instrument] = MonteCarloResult(
                    instrument=instrument,
                    expected_open=float(np.mean(simulated_opens)),
                    std_dev=float(np.std(simulated_opens)),
                    p_up=float(np.mean(simulated_opens > prev_close)),
                    p_down=float(np.mean(simulated_opens < prev_close)),
                    scenarios_run=self._simulations_done,
                    confidence=min(self._simulations_done / self.TOTAL_SIMULATIONS, 1.0),
                )

    # ── Phase 3: Order Pre-Staging ────────────────────────────────────────

    def _run_pre_staging(self):
        """
        Pre-compute optimal orders using Almgren-Chriss sizing.
        On real FPGA: Stage limit orders in exchange gateway buffer.
        """
        if self._pre_staged:
            return  # Already computed

        for instrument, mc in self._mc_results.items():
            # Only stage orders with high confidence directional signal
            if mc.confidence < 0.5:
                continue

            sentiment = self._sentiment_signals.get(instrument, 0)

            if mc.p_up > 0.6 and sentiment > 0.1:
                self._pre_staged.append(PreStagedOrder(
                    instrument=instrument,
                    side="BUY",
                    quantity=round(0.3 * mc.confidence, 3),
                    limit_price=round(mc.expected_open * 0.998, 2),  # Bid below expected
                    alpha_expected_bps=round((mc.p_up - 0.5) * 100, 1),
                    confidence=round(mc.confidence, 2),
                ))
            elif mc.p_down > 0.6 and sentiment < -0.1:
                self._pre_staged.append(PreStagedOrder(
                    instrument=instrument,
                    side="SELL",
                    quantity=round(0.3 * mc.confidence, 3),
                    limit_price=round(mc.expected_open * 1.002, 2),
                    alpha_expected_bps=round((mc.p_down - 0.5) * 100, 1),
                    confidence=round(mc.confidence, 2),
                ))

    # ── Helpers ────────────────────────────────────────────────────────────

    def _calculate_progress(self) -> float:
        """Overall pipeline progress 0–100%."""
        if self._phase == "IDLE":
            return 0.0
        elif self._phase == "NEWS_DIGEST":
            return min(self._tick_in_phase / 50 * 33, 33)
        elif self._phase == "MONTE_CARLO":
            return 33 + (self._simulations_done / self.TOTAL_SIMULATIONS) * 34
        elif self._phase == "PRE_STAGING":
            return 67 + min(self._tick_in_phase / 30 * 33, 33)
        elif self._phase == "COMPLETE":
            return 100.0
        return 0.0

    def _get_opening_prediction(self) -> Dict:
        """Summarize opening predictions for dashboard display."""
        if not self._mc_results:
            return {}
        summary = {}
        for inst, mc in self._mc_results.items():
            summary[inst] = {
                "expected_open": round(mc.expected_open, 2),
                "p_up": round(mc.p_up * 100, 1),
                "confidence": round(mc.confidence * 100, 1),
                "scenarios": mc.scenarios_run,
            }
        return summary

    def get_pre_staged_orders(self) -> List[Dict]:
        """Return pre-staged orders for the market open."""
        return [
            {
                "instrument": o.instrument,
                "side": o.side,
                "quantity": o.quantity,
                "limit_price": o.limit_price,
                "alpha_bps": o.alpha_expected_bps,
                "confidence": o.confidence,
            }
            for o in self._pre_staged
        ]
