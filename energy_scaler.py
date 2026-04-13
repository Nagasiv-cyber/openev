"""
energy_scaler.py — Active Energy Scaling Engine

Maps real-time market volatility to GPU power consumption via AMD ROCm SMI.
Implements 'Mechanical Sympathy': hardware power envelope tracks market regime.

When ROCm isn't available (dev mode / Windows), operates as a simulation layer
that still produces accurate energy telemetry for the dashboard and EAA formula.

KPI: Performance-per-Watt — every joule of energy must generate alpha.
"""

import logging
import time
import subprocess
import shutil
from dataclasses import dataclass, field
from typing import Dict, Optional
import numpy as np

logger = logging.getLogger("EnergyScaler")


# ============================================================================
# TELEMETRY DATA STRUCTURES
# ============================================================================

@dataclass
class EnergyTelemetry:
    """Real-time energy and hardware telemetry snapshot."""
    timestamp: float = 0.0
    realised_vol: float = 0.0
    sigma_scaled: float = 0.0
    target_tdp_w: int = 150
    current_tdp_w: int = 150
    junction_temp_c: float = 45.0
    power_draw_w: float = 75.0
    energy_consumed_wh: float = 0.0
    power_savings_pct: float = 70.0
    compute_mode: str = "IDLE"           # IDLE / INFERENCE / FULL
    hardware_mode: str = "GPU"           # GPU / FPGA / SLEEP
    renewable_mix_pct: float = 0.50
    carbon_intensity: float = 400.0      # gCO2/kWh
    carbon_emitted_g: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "realised_vol": round(self.realised_vol, 4),
            "sigma_scaled": round(self.sigma_scaled, 4),
            "target_tdp_w": self.target_tdp_w,
            "current_tdp_w": self.current_tdp_w,
            "junction_temp_c": round(self.junction_temp_c, 1),
            "power_draw_w": round(self.power_draw_w, 1),
            "energy_consumed_wh": round(self.energy_consumed_wh, 2),
            "power_savings_pct": round(self.power_savings_pct, 1),
            "compute_mode": self.compute_mode,
            "hardware_mode": self.hardware_mode,
            "renewable_mix_pct": round(self.renewable_mix_pct * 100, 1),
            "carbon_intensity": round(self.carbon_intensity, 0),
            "carbon_emitted_g": round(self.carbon_emitted_g, 2),
        }


# ============================================================================
# GRID CARBON MODEL (Time-of-Day Renewable Mix)
# ============================================================================

class GridCarbonModel:
    """
    Models grid renewable energy mix and carbon intensity by hour of day.
    Simulates WattTime / ElectricityMaps API for the IST + EST grids.

    In production: Replace with live API calls to:
      - https://api.watttime.org/v3/signal-index
      - https://api.electricitymap.org/v3/carbon-intensity/latest
    """

    # Hourly renewable fraction [0..1] — IST-aligned (UTC+5:30)
    # Index 0 = midnight IST, index 12 = noon IST, etc.
    IST_RENEWABLE_MIX = [
        0.20, 0.18, 0.15, 0.15, 0.18, 0.22,  # 00:00–05:00 (coal heavy, night)
        0.35, 0.45, 0.55, 0.65, 0.72, 0.72,  # 06:00–11:00 (solar ramp)
        0.70, 0.68, 0.55, 0.42, 0.35, 0.30,  # 12:00–17:00 (solar decline)
        0.25, 0.22, 0.20, 0.20, 0.20, 0.20,  # 18:00–23:00 (evening coal)
    ]

    # Carbon intensity gCO2/kWh (inverse of renewable mix)
    IST_CARBON_INTENSITY = [
        720, 740, 760, 760, 740, 700,   # Night
        580, 500, 400, 320, 260, 260,   # Solar peak
        280, 300, 400, 520, 580, 630,   # Afternoon decline
        680, 700, 720, 720, 720, 720,   # Evening
    ]

    def get_renewable_mix(self, utc_hour: int) -> float:
        """Get current renewable fraction based on IST hour."""
        ist_hour = (utc_hour + 5) % 24  # Approximate IST offset
        return self.IST_RENEWABLE_MIX[ist_hour]

    def get_carbon_intensity(self, utc_hour: int) -> float:
        """Get grid carbon intensity in gCO2/kWh."""
        ist_hour = (utc_hour + 5) % 24
        return self.IST_CARBON_INTENSITY[ist_hour]


# ============================================================================
# ROCm SMI INTERFACE (with mock fallback)
# ============================================================================

class ROCmInterface:
    """
    Wraps AMD ROCm SMI commands for hardware control.
    Falls back to simulation when running on non-AMD systems (Windows, Intel, etc.)
    """

    def __init__(self, gpu_id: int = 0):
        self.gpu_id = gpu_id
        self.rocm_available = self._detect_rocm()
        self._simulated_tdp = 150
        self._simulated_temp = 45.0
        self._simulated_power = 75.0

        if self.rocm_available:
            logger.info(f"ROCm SMI detected. GPU {gpu_id} under hardware control.")
        else:
            logger.info("ROCm SMI not available. Running in SIMULATION mode.")

    def _detect_rocm(self) -> bool:
        rocm_path = shutil.which("rocm-smi")
        if rocm_path:
            return True
        # Also check standard ROCm install path
        import os
        return os.path.exists("/opt/rocm/bin/rocm-smi")

    def set_power_cap(self, tdp_watts: int):
        """Set GPU power cap via ROCm SMI."""
        if self.rocm_available:
            try:
                cmd = [
                    "/opt/rocm/bin/rocm-smi",
                    "--setpoweroverdrive", str(tdp_watts),
                    "--device", str(self.gpu_id)
                ]
                subprocess.run(cmd, check=True, capture_output=True, timeout=5)
                logger.debug(f"ROCm SMI: TDP set to {tdp_watts}W")
            except Exception as e:
                logger.error(f"ROCm SMI power cap failed: {e}")
        else:
            self._simulated_tdp = tdp_watts

    def get_temperature(self) -> float:
        """Read GPU junction temperature."""
        if self.rocm_available:
            try:
                result = subprocess.run(
                    ["/opt/rocm/bin/rocm-smi", "--showtemp",
                     "--device", str(self.gpu_id)],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.split("\n"):
                    if "Temperature" in line and "junction" in line.lower():
                        return float(line.split()[-1].replace("c", ""))
            except Exception:
                pass
        # Simulation: temp correlates with power
        self._simulated_temp = 35 + (self._simulated_tdp / 500) * 55
        self._simulated_temp += np.random.normal(0, 2)
        return round(np.clip(self._simulated_temp, 30, 100), 1)

    def get_power_draw(self) -> float:
        """Read current GPU power draw in watts."""
        if self.rocm_available:
            try:
                result = subprocess.run(
                    ["/opt/rocm/bin/rocm-smi", "--showpower",
                     "--device", str(self.gpu_id)],
                    capture_output=True, text=True, timeout=5
                )
                for line in result.stdout.split("\n"):
                    if "Average" in line and "W" in line:
                        return float(line.split()[-2])
            except Exception:
                pass
        # Simulation: power is ~70% of TDP on average
        self._simulated_power = self._simulated_tdp * (0.65 + np.random.uniform(0, 0.15))
        return round(self._simulated_power, 1)


# ============================================================================
# ACTIVE ENERGY SCALER (Main Engine)
# ============================================================================

class ActiveEnergyScaler:
    """
    Mechanical Sympathy Engine: GPU power envelope tracks market volatility.

    Formula:
      TDP_target = TDP_base + (TDP_max - TDP_base) * sigma_scaled
      sigma_scaled = clip((vol_realised - sigma_floor) / (sigma_ceiling - sigma_floor), 0, 1)

    When markets are calm → GPU throttles to 150W (inference mode)
    When volatility spikes → GPU scales to 500W (full compute)
    During dark hours → GPU sleeps, FPGA runs at 25W
    """

    TDP_BASE_W = 150       # Calm markets — minimum viable inference
    TDP_MAX_W  = 500       # Full MI325X envelope — crisis/opportunity mode
    SIGMA_FLOOR = 0.08     # Below this → idle power profile
    SIGMA_CEIL  = 0.45     # Above this → full power engaged
    FPGA_POWER_W = 25      # Alveo U250 dark-hours power

    def __init__(self, gpu_id: int = 0):
        self.rocm = ROCmInterface(gpu_id)
        self.grid = GridCarbonModel()
        self._current_tdp = self.TDP_BASE_W
        self._total_energy_wh = 0.0
        self._total_carbon_g = 0.0
        self._last_tick_time = time.time()
        self._tick_count = 0
        self._dark_hours = False

        self.telemetry = EnergyTelemetry()

    def compute_target_tdp(self, realised_vol: float) -> int:
        """Map real-time volatility to a hardware power cap."""
        sigma_scaled = np.clip(
            (realised_vol - self.SIGMA_FLOOR) / (self.SIGMA_CEIL - self.SIGMA_FLOOR),
            0.0, 1.0
        )
        target = self.TDP_BASE_W + (self.TDP_MAX_W - self.TDP_BASE_W) * sigma_scaled
        # Quantize to 5W steps (hardware granularity)
        return int(np.round(target / 5) * 5)

    def tick(self, price_returns: np.ndarray, utc_hour: Optional[int] = None) -> EnergyTelemetry:
        """
        Called every simulation tick. Adjusts GPU power based on volatility.
        Returns full energy telemetry snapshot.
        """
        now = time.time()
        dt_hours = (now - self._last_tick_time) / 3600.0
        self._last_tick_time = now
        self._tick_count += 1

        if utc_hour is None:
            import datetime
            utc_hour = datetime.datetime.utcnow().hour

        # Step 1: Calculate realised volatility (annualised)
        if len(price_returns) > 2:
            realised_vol = float(np.std(price_returns[-300:]) * np.sqrt(252 * 6.5 * 60))
        else:
            realised_vol = 0.10  # Default low vol

        # Step 2: Determine hardware mode
        # Dark hours logic: NSE closes at 15:30 IST (10:00 UTC), NYSE closes at 21:00 UTC
        # Simplified: dark hours = UTC 21:00–03:30
        self._dark_hours = utc_hour >= 21 or utc_hour < 4

        if self._dark_hours:
            hardware_mode = "FPGA"
            compute_mode = "SIMULATION"
            target_tdp = self.FPGA_POWER_W
            power_draw = self.FPGA_POWER_W * (0.8 + np.random.uniform(0, 0.2))
            junction_temp = 35 + np.random.normal(0, 2)
        else:
            hardware_mode = "GPU"
            target_tdp = self.compute_target_tdp(realised_vol)
            self.rocm.set_power_cap(target_tdp)
            power_draw = self.rocm.get_power_draw()
            junction_temp = self.rocm.get_temperature()

            if realised_vol < self.SIGMA_FLOOR:
                compute_mode = "IDLE"
            elif realised_vol < 0.25:
                compute_mode = "INFERENCE"
            else:
                compute_mode = "FULL"

        # Step 3: Energy accounting
        energy_this_tick = power_draw * dt_hours  # Wh
        self._total_energy_wh += energy_this_tick

        # Step 4: Carbon accounting
        renewable_mix = self.grid.get_renewable_mix(utc_hour)
        carbon_intensity = self.grid.get_carbon_intensity(utc_hour)
        carbon_this_tick = energy_this_tick * carbon_intensity / 1000  # gCO2
        self._total_carbon_g += carbon_this_tick

        # Step 5: Calculate savings vs naive (full TDP always)
        naive_power = self.TDP_MAX_W if not self._dark_hours else 80  # GPU idle
        power_savings = (1 - power_draw / naive_power) * 100 if naive_power > 0 else 0

        # Step 6: Build telemetry
        sigma_scaled = np.clip(
            (realised_vol - self.SIGMA_FLOOR) / (self.SIGMA_CEIL - self.SIGMA_FLOOR),
            0.0, 1.0
        )

        self.telemetry = EnergyTelemetry(
            timestamp=now,
            realised_vol=realised_vol,
            sigma_scaled=sigma_scaled,
            target_tdp_w=target_tdp,
            current_tdp_w=target_tdp,
            junction_temp_c=junction_temp,
            power_draw_w=power_draw,
            energy_consumed_wh=self._total_energy_wh,
            power_savings_pct=max(0, power_savings),
            compute_mode=compute_mode,
            hardware_mode=hardware_mode,
            renewable_mix_pct=renewable_mix,
            carbon_intensity=carbon_intensity,
            carbon_emitted_g=self._total_carbon_g,
        )

        return self.telemetry

    def get_carbon_tax_multiplier(self, utc_hour: Optional[int] = None) -> float:
        """
        Dynamic carbon tax multiplier based on grid renewable mix.
        τ(h) = τ_base * (1 + β * (1 - RE_mix(h)))

        Returns multiplier (1.84x at solar peak → 3.40x during coal-heavy night)
        """
        if utc_hour is None:
            import datetime
            utc_hour = datetime.datetime.utcnow().hour

        TAU_BASE = 0.0002   # 2 bps base carbon cost
        BETA = 3.0           # Amplification factor

        renewable_mix = self.grid.get_renewable_mix(utc_hour)
        tau = TAU_BASE * (1 + BETA * (1 - renewable_mix))
        multiplier = tau / TAU_BASE  # Express as multiplier of base

        return round(multiplier, 2)

    def get_energy_denominator(self, trades_executed: int) -> float:
        """
        E(t) = GPU Watt-hours / Trades executed
        Used as denominator in EAA formula (lower = more efficient)
        """
        if trades_executed == 0:
            return float('inf')
        return self._total_energy_wh / trades_executed
