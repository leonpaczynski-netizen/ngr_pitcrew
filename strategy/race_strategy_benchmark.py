"""Group 48 — Race Strategy Brain Phase 2: Porsche RSR / Fuji benchmark scenario.

WHY IT EXISTS
  A fixed, realistic scenario that proves the strategy brain optimises the RACE,
  not the hot lap.  It wires the evidence model → candidate generator → scorer →
  explanation end-to-end for:

      Car:        Porsche 911 RSR '17
      Track:      Fuji Full Course  (~50-minute race)
      Tyre wear:  8×      Fuel: 3×      Refuel rate: 1 L/sec
      Driver:     front bite, stable rear platform, smooth throttle, trail braking

  With a high fuel burn against a slow 1 L/s refuel, an extra pit stop is
  expensive, so a one-stop should beat a two-stop on TOTAL race time even though
  the two-stop carries fresher tyres.  The driver's "stable rear" preference
  (structured Group 42 driver profile) marks the rear as fragile, so the push
  two-stop is flagged and never recommended.

PURITY
  No PyQt6, no DB, no I/O, no AI.  Sample values are realistic but fixed so the
  benchmark is deterministic.  The rear-fragility flag is read from the existing
  structured DriverProfile — nothing is scraped from free text.
"""
from __future__ import annotations

from dataclasses import dataclass

from strategy.race_strategy_evidence import (
    RaceStrategyEvidence,
    build_strategy_evidence,
)
from strategy.race_strategy_scorer import (
    StrategyRecommendation,
    recommend_strategy,
)
from strategy.race_strategy_explain import StrategyExplanation, build_explanation


# ---------------------------------------------------------------------------
# Fixed scenario inputs (realistic, deterministic)
# ---------------------------------------------------------------------------

BENCHMARK_CAR = "Porsche 911 RSR '17"
BENCHMARK_CAR_ID = 911
BENCHMARK_TRACK = "Fuji Speedway"
BENCHMARK_LAYOUT = "fuji_speedway__full_course"
BENCHMARK_DURATION_MIN = 50.0
BENCHMARK_TYRE_MULT = 8.0
BENCHMARK_FUEL_MULT = 3.0
BENCHMARK_REFUEL_LPS = 1.0
BENCHMARK_PIT_LOSS_S = 22.0

# ~1:40 laps, smooth/consistent driver → tight spread (12 samples = long-run).
_LAP_SAMPLES = (
    100.1, 100.0, 100.3, 99.9, 100.2, 100.4,
    100.0, 100.2, 99.8, 100.3, 100.1, 100.2,
)
# ~4.0 L/lap at 3× fuel — a full 100 L tank cannot cover a 30-lap no-stop.
_FUEL_SAMPLES = (4.0, 3.95, 4.05, 4.0, 3.9, 4.1, 4.0, 4.0)
# 8× wear → meaningful per-lap pace loss; 12 samples = long-run degradation data.
_TYRE_WEAR_SAMPLES = (0.08,) * 12
# Measured per-compound pace: RM is the reference, RH ~1.5s slower.
_COMPOUND_SAMPLES = {
    "RM": (100.1, 100.0, 100.2, 99.9, 100.3),
    "RH": (101.6, 101.5, 101.7, 101.4, 101.6),
}
BENCHMARK_AVAILABLE_COMPOUNDS = ("RM", "RH")


@dataclass
class BenchmarkResult:
    evidence: RaceStrategyEvidence
    recommendation: StrategyRecommendation
    explanation: StrategyExplanation
    rear_traction_fragile: bool


def _rear_fragile_from_profile() -> bool:
    """Read rear fragility from the structured DriverProfile (never free text).

    The scenario driver wants a stable rear platform and dislikes snap exits, so
    the rear traction is treated as something to PROTECT.  Falls back to True
    (protect the rear) if the profile cannot be built — the safe default for this
    driver, and never raises.
    """
    try:
        from strategy.setup_driver_profile import build_driver_profile
        p = build_driver_profile()
        return bool(p.prefers_rear_stability or p.dislikes_snap_exit)
    except Exception:
        return True


def build_benchmark_evidence() -> RaceStrategyEvidence:
    """Construct the fixed Porsche-RSR / Fuji evidence snapshot."""
    return build_strategy_evidence(
        car_id=BENCHMARK_CAR_ID,
        track=BENCHMARK_TRACK,
        layout_id=BENCHMARK_LAYOUT,
        race_duration_minutes=BENCHMARK_DURATION_MIN,
        race_laps=0,  # timed race — laps are estimated from the race pace
        fuel_multiplier=BENCHMARK_FUEL_MULT,
        tyre_multiplier=BENCHMARK_TYRE_MULT,
        refuel_rate_lps=BENCHMARK_REFUEL_LPS,
        pit_loss_seconds=BENCHMARK_PIT_LOSS_S,
        available_compounds=BENCHMARK_AVAILABLE_COMPOUNDS,
        required_compounds=(),
        mandatory_pit_stops=0,
        weather_context="dry_stable",
        lap_time_samples=_LAP_SAMPLES,
        fuel_use_samples=_FUEL_SAMPLES,
        tyre_wear_samples=_TYRE_WEAR_SAMPLES,
        compound_samples=_COMPOUND_SAMPLES,
    )


def run_benchmark() -> BenchmarkResult:
    """Run the full evidence → recommendation → explanation pipeline."""
    evidence = build_benchmark_evidence()
    rear_fragile = _rear_fragile_from_profile()
    recommendation = recommend_strategy(evidence, rear_traction_fragile=rear_fragile)
    explanation = build_explanation(recommendation, evidence)
    return BenchmarkResult(
        evidence=evidence,
        recommendation=recommendation,
        explanation=explanation,
        rear_traction_fragile=rear_fragile,
    )
