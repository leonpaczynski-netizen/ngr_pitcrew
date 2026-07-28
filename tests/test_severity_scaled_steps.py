"""Severity-scaled corrective steps — the setup brain makes BIGGER changes when the
car is diagnosed as handling badly overall, while staying bounded by the safe range.

Directive item 4 (personalize the move: scale magnitude to how badly the car is off).
Deterministic / offline — no Qt, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.setup_diagnosis import (
    build_setup_diagnosis, overall_handling_severity,
    _driver_reported_severity, _telemetry_severity,
)
from strategy.setup_rule_engine import _severity_scaled_delta, run_rule_engine
from strategy.setup_driver_profile import build_driver_profile
from strategy.setup_ranges import resolve_ranges


# ---------------------------------------------------------------------------
# overall_handling_severity — "either signal" (driver OR telemetry, the worse)
# ---------------------------------------------------------------------------
class TestOverallHandlingSeverity:
    def test_driver_strong_grade_is_severe(self):
        fb = {"corner_entry": "strong understeer"}
        assert overall_handling_severity(fb, "low", "minor") == ("severe", "driver")

    def test_driver_plain_imbalance_is_moderate(self):
        fb = {"mid_corner": "understeer"}
        assert overall_handling_severity(fb, "low", "minor") == ("moderate", "driver")

    def test_telemetry_severe_band_is_severe(self):
        assert overall_handling_severity(None, "severe", "minor") == ("severe", "telemetry")

    def test_telemetry_major_band_is_moderate(self):
        assert overall_handling_severity(None, "major", "minor") == ("moderate", "telemetry")

    def test_either_signal_escalates_worse_wins(self):
        # driver moderate ('below par'), telemetry severe → severe (telemetry drove it)
        fb = {"rotation": "below par"}
        assert overall_handling_severity(fb, "severe", "minor") == ("severe", "telemetry")

    def test_a_poor_scale_rating_alone_reads_severe(self):
        # "rear won't put power down" → traction Poor → severe, even with calm telemetry.
        assert overall_handling_severity({"traction": "poor"}, "low", "minor") == ("severe", "driver")

    def test_below_par_reads_moderate(self):
        assert overall_handling_severity({"drive_out": "below par"}, "low", "minor") == ("moderate", "driver")

    def test_both_at_same_level_reports_both(self):
        fb = {"exit_stability": "strong oversteer"}
        assert overall_handling_severity(fb, "severe", "minor") == ("severe", "both")

    def test_quiet_car_is_mild_with_no_source(self):
        assert overall_handling_severity({}, "low", "minor") == ("mild", "")

    def test_bottoming_severe_rating_from_driver(self):
        assert _driver_reported_severity({"bottoming": "severe"}) == "severe"

    def test_telemetry_bottoming_band(self):
        assert _telemetry_severity("low", "severe") == "severe"
        assert _telemetry_severity("low", "moderate") == "moderate"


# ---------------------------------------------------------------------------
# _severity_scaled_delta — sizing toward the operating-band edge, bounded
# ---------------------------------------------------------------------------
_RANGES = {"arb_rear": (1.0, 10.0)}


class TestSeverityScaledDelta:
    def test_mild_leaves_delta_untouched(self):
        d, f, lvl = _severity_scaled_delta("arb_rear", 5.0, 1.0, _RANGES,
                                           {"handling_severity": "mild"})
        assert (d, f, lvl) == (1.0, 1.0, "mild")

    def test_missing_key_is_treated_as_mild(self):
        d, f, _ = _severity_scaled_delta("arb_rear", 5.0, 1.0, _RANGES, {})
        assert (d, f) == (1.0, 1.0)

    def test_severe_sizes_to_the_operating_band_edge(self):
        # span 9 → reserve 0.9 → upper edge 9.1; room from 5 = 4.1
        d, f, lvl = _severity_scaled_delta("arb_rear", 5.0, 1.0, _RANGES,
                                           {"handling_severity": "severe"})
        assert lvl == "severe"
        assert abs(d - 4.1) < 1e-9         # moved to the edge, not a fixed step
        assert f > 1.0

    def test_moderate_is_halfway_to_the_edge(self):
        d, _f, _ = _severity_scaled_delta("arb_rear", 5.0, 1.0, _RANGES,
                                          {"handling_severity": "moderate"})
        assert abs(d - 4.1 / 2) < 1e-9

    def test_never_smaller_than_the_base_step(self):
        # from 8.9: room to edge (9.1) is only 0.2 < base 1.0 → keep the base step
        d, f, _ = _severity_scaled_delta("arb_rear", 8.9, 1.0, _RANGES,
                                         {"handling_severity": "severe"})
        assert (d, f) == (1.0, 1.0)

    def test_already_inside_reserve_keeps_base_step(self):
        # from 9.5 (inside the 10% reserve) an increase keeps the base step
        d, f, _ = _severity_scaled_delta("arb_rear", 9.5, 1.0, _RANGES,
                                         {"handling_severity": "severe"})
        assert (d, f) == (1.0, 1.0)

    def test_negative_corrective_direction_scales_toward_lower_edge(self):
        d, _f, _ = _severity_scaled_delta("arb_rear", 5.0, -1.0, _RANGES,
                                          {"handling_severity": "severe"})
        # lower edge = 1 + 0.9 = 1.9; room = 1.9 - 5 = -3.1
        assert abs(d - (-3.1)) < 1e-9

    def test_rangeless_field_uses_multiplier_fallback(self):
        d, f, _ = _severity_scaled_delta("final_drive", 4.0, -0.05, {},
                                         {"handling_severity": "severe"})
        assert abs(d - (-0.15)) < 1e-9 and f == 3.0


# ---------------------------------------------------------------------------
# End-to-end through the real rule engine
# ---------------------------------------------------------------------------
def _make_lap(**kw):
    base = dict(bottoming_count=0, wheelspin_count=0, snap_throttle_count=0,
                lock_up_count=0, rev_limiter_by_gear={}, max_speed_kmh=200.0,
                brake_consistency_m=5.0, oversteer_count=0,
                oversteer_throttle_on_count=0, kerb_count=0, max_lat_g=1.5,
                lock_up_positions=[], wheelspin_positions=[], oversteer_positions=[],
                snap_throttle_positions=[], over_braking_positions=[],
                over_braking_count=0, abrupt_release_count=0,
                car_max_speed_theoretical_kmh=0.0, avg_tyre_radius={},
                off_track_count=0, frames=[])
    base.update(kw)
    base["rev_limiter_count"] = sum(base["rev_limiter_by_gear"].values())
    return SimpleNamespace(**base)


class TestEndToEndBiggerWhenBad:
    def _plan_for(self, severity, setup):
        laps = [_make_lap(wheelspin_count=20, bottoming_count=1) for _ in range(5)]
        diag = build_setup_diagnosis(laps, setup, "", {}, None)
        diag = dict(diag)
        diag["handling_severity"] = severity
        ranges = resolve_ranges("")
        profile = build_driver_profile()
        return run_rule_engine(diag, setup, ranges, profile)

    def test_severe_moves_further_than_mild_for_the_same_field(self):
        setup = {"lsd_accel": 20, "aero_rear": 300, "arb_rear": 5,
                 "aero_front": 300, "lsd_decel": 20, "brake_bias": 0}
        mild = {p.field: p for p in self._plan_for("mild", setup).proposed}
        severe = {p.field: p for p in self._plan_for("severe", setup).proposed}
        common = set(mild) & set(severe)
        assert common, "expected at least one field proposed under both severities"
        # For every shared field the severe move is at least as large, and at least
        # one is strictly larger (the whole point of the feature).
        assert all(abs(severe[f].delta) >= abs(mild[f].delta) - 1e-9 for f in common)
        assert any(abs(severe[f].delta) > abs(mild[f].delta) + 1e-9 for f in common)

    def test_severe_moves_stay_within_range(self):
        setup = {"lsd_accel": 20, "aero_rear": 300, "arb_rear": 5, "aero_front": 300}
        ranges = resolve_ranges("")
        for p in self._plan_for("severe", setup).proposed:
            if p.field in ranges:
                lo, hi = ranges[p.field]
                assert lo <= p.to_value <= hi, f"{p.field} {p.to_value} outside [{lo},{hi}]"

    def test_enlargement_is_disclosed_in_the_rationale(self):
        setup = {"lsd_accel": 20, "aero_rear": 300, "arb_rear": 5, "aero_front": 300}
        proposed = self._plan_for("severe", setup).proposed
        enlarged = [p for p in proposed if "enlarged for severe handling" in p.rationale]
        assert enlarged, "a severe-scaled change should disclose the enlargement"
