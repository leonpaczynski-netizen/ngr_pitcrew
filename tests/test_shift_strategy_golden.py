"""Adaptive Per-Gear Shift Strategy — golden-vector byte-stability test.

THESE LITERALS ARE FROZEN FROM THE SHIPPED ALGORITHM.
DO NOT REGENERATE ON FAILURE.  A mismatch means the algorithm changed;
fix the CODE, not the vectors.  Changing these without changing the
SHIFT_STRATEGY_VERSION constant will silently re-key stored strategy data.

Three fixed configs cover the main aspiration families:
  NA6  — 6-gear NA,       500 hp / 1 200 kg
  TC4  — 4-gear Turbo,    400 hp / 1 100 kg
  EV7  — 7-gear Electric

Vectors frozen: 2026-07-25  algorithm shift_strategy_v1
"""
from __future__ import annotations

import pytest

from strategy.shift_strategy_inputs import ShiftStrategyInputs, compute_shift_fingerprint
from strategy.shift_strategy_engine import compute_shift_strategy, ShiftConfidence

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make(gear_ratios, aspiration, peak_power_rpm, peak_torque_rpm, redline,
          weight_kg, car_id) -> ShiftStrategyInputs:
    return ShiftStrategyInputs(
        car_id=car_id,
        gear_ratios=gear_ratios,
        final_drive=4.0,
        ecu_output=100.0,
        power_restrictor=100.0,
        ballast_kg=0.0,
        weight_kg=weight_kg,
        aspiration=aspiration,
        peak_power_rpm=peak_power_rpm,
        peak_torque_rpm=peak_torque_rpm,
        redline=redline,
        active_setup_revision=1,
    )


# ---------------------------------------------------------------------------
# Fixed configs
# ---------------------------------------------------------------------------

_NA6 = _make(
    gear_ratios=(3.5, 2.5, 1.9, 1.4, 1.1, 0.9),
    aspiration="NA",
    peak_power_rpm=7000,
    peak_torque_rpm=5500,
    redline=8000,
    weight_kg=1200,
    car_id="NA6",
)

_TC4 = _make(
    gear_ratios=(2.8, 2.0, 1.5, 1.1),
    aspiration="TC",
    peak_power_rpm=6500,
    peak_torque_rpm=4000,
    redline=7500,
    weight_kg=1100,
    car_id="TC4",
)

_EV7 = _make(
    gear_ratios=(4.0, 3.0, 2.3, 1.8, 1.4, 1.1, 0.9),
    aspiration="EV",
    peak_power_rpm=8000,
    peak_torque_rpm=1000,
    redline=12000,
    weight_kg=1200,
    car_id="EV7",
)

# ---------------------------------------------------------------------------
# Golden vectors
# NEVER REGENERATE — a mismatch means the code changed; fix the code.
# ---------------------------------------------------------------------------

# Fingerprints
_GOLDEN_FP = {
    "NA6": "0236e6f890",
    "TC4": "d07df5f010",
    "EV7": "5b3c44a477",
}

# Per-pair qualifying target RPM at 5% fuel-saving target
# Format: car_id -> list of (from_gear, to_gear, qual_rpm)
_GOLDEN_QUAL = {
    "NA6": [(1, 2, 5250), (2, 3, 5250), (3, 4, 5250), (4, 5, 5250), (5, 6, 5250)],
    "TC4": [(1, 2, 4875), (2, 3, 4875), (3, 4, 4875)],
    "EV7": [
        (1, 2, 11900), (2, 3, 11900), (3, 4, 11900),
        (4, 5, 11900), (5, 6, 11900), (6, 7, 11900),
    ],
}

# Per-pair race target RPM at 5% fuel-saving target
_GOLDEN_RACE = {
    "NA6": [(1, 2, 5250), (2, 3, 5250), (3, 4, 5250), (4, 5, 5250), (5, 6, 4350)],
    "TC4": [(1, 2, 4875), (2, 3, 3975), (3, 4, 4875)],
    "EV7": [
        (1, 2, 11900), (2, 3, 11900), (3, 4, 11900),
        (4, 5, 11900), (5, 6, 11900), (6, 7, 4400),
    ],
}

# Overall confidence for all three configs at 5% target
_GOLDEN_CONFIDENCE = {
    "NA6": ShiftConfidence.PROVISIONAL.value,
    "TC4": ShiftConfidence.PROVISIONAL.value,
    "EV7": ShiftConfidence.PROVISIONAL.value,
}

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cfg,expected_fp", [
    (_NA6, _GOLDEN_FP["NA6"]),
    (_TC4, _GOLDEN_FP["TC4"]),
    (_EV7, _GOLDEN_FP["EV7"]),
])
def test_fingerprint_stable(cfg, expected_fp):
    assert compute_shift_fingerprint(cfg) == expected_fp


@pytest.mark.parametrize("cfg,expected_qual", [
    (_NA6, _GOLDEN_QUAL["NA6"]),
    (_TC4, _GOLDEN_QUAL["TC4"]),
    (_EV7, _GOLDEN_QUAL["EV7"]),
])
def test_qualifying_targets_stable(cfg, expected_qual):
    result = compute_shift_strategy(cfg, required_fuel_saving_pct=5.0)
    decisions = {
        (d.from_gear, d.to_gear): d.qualifying_target_rpm
        for d in result.qualifying_profile.decisions
        if d.valid
    }
    for from_g, to_g, expected_rpm in expected_qual:
        actual = decisions.get((from_g, to_g))
        assert actual == expected_rpm, (
            f"Gear {from_g}->{to_g} qualifying target: expected {expected_rpm}, got {actual}. "
            "DO NOT update this literal — fix the code."
        )


@pytest.mark.parametrize("cfg,expected_race", [
    (_NA6, _GOLDEN_RACE["NA6"]),
    (_TC4, _GOLDEN_RACE["TC4"]),
    (_EV7, _GOLDEN_RACE["EV7"]),
])
def test_race_targets_stable_at_5pct(cfg, expected_race):
    result = compute_shift_strategy(cfg, required_fuel_saving_pct=5.0)
    decisions = {
        (d.from_gear, d.to_gear): d.race_target_rpm
        for d in result.race_profile.decisions
        if d.valid
    }
    for from_g, to_g, expected_rpm in expected_race:
        actual = decisions.get((from_g, to_g))
        assert actual == expected_rpm, (
            f"Gear {from_g}->{to_g} race target: expected {expected_rpm}, got {actual}. "
            "DO NOT update this literal — fix the code."
        )


@pytest.mark.parametrize("cfg,expected_conf", [
    (_NA6, _GOLDEN_CONFIDENCE["NA6"]),
    (_TC4, _GOLDEN_CONFIDENCE["TC4"]),
    (_EV7, _GOLDEN_CONFIDENCE["EV7"]),
])
def test_overall_confidence_stable(cfg, expected_conf):
    result = compute_shift_strategy(cfg, required_fuel_saving_pct=5.0)
    actual = result.overall_confidence.value
    assert actual == expected_conf, (
        f"Overall confidence: expected {expected_conf!r}, got {actual!r}. "
        "DO NOT update this literal — fix the code."
    )
