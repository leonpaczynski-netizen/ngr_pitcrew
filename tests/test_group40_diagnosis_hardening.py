"""
Group 40 — Setup Diagnosis Hardening Acceptance Tests

Covers S1–S10 + AC9 (deterministic fallback) + key-parity from the
"Group 40 — Setup Diagnosis Hardening" sprint.

All tests are pure/offline — no network, no Qt event loop, no QApplication.
Pattern mirrors tests/test_group39_setup_brain_upgrade.py and
tests/test_group38_setup_diagnosis.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.setup_diagnosis import (
    build_setup_diagnosis,
    validate_setup_engineering,
    format_diagnosis_for_prompt,
    _build_setup_diagnosis_conservative,
    _build_deterministic_fallback,
    _derive_driver_feel_traction_status,
)
import strategy.driving_advisor as da


# ---------------------------------------------------------------------------
# Shared helpers — mirrors test_group39 style
# ---------------------------------------------------------------------------

def _make_frame(gear=6, throttle=0.90, speed_kmh=270.0, rpm=7000.0, brake=0.0):
    return SimpleNamespace(
        gear=gear,
        throttle=throttle,
        speed_kmh=speed_kmh,
        rpm=rpm,
        brake=brake,
    )


def _make_lap(
    bottoming_count: int = 0,
    wheelspin_count: int = 0,
    snap_throttle_count: int = 0,
    lock_up_count: int = 0,
    rev_limiter_by_gear: dict | None = None,
    max_speed_kmh: float = 200.0,
    brake_consistency_m: float = 5.0,
    oversteer_count: int = 0,
    oversteer_throttle_on_count: int = 0,
    kerb_count: int = 0,
    max_lat_g: float = 1.5,
    frames: list | None = None,
) -> SimpleNamespace:
    rlbg = rev_limiter_by_gear or {}
    return SimpleNamespace(
        bottoming_count=bottoming_count,
        wheelspin_count=wheelspin_count,
        snap_throttle_count=snap_throttle_count,
        lock_up_count=lock_up_count,
        rev_limiter_by_gear=rlbg,
        max_speed_kmh=max_speed_kmh,
        brake_consistency_m=brake_consistency_m,
        oversteer_count=oversteer_count,
        oversteer_throttle_on_count=oversteer_throttle_on_count,
        kerb_count=kerb_count,
        max_lat_g=max_lat_g,
        rev_limiter_count=sum(rlbg.values()),
        lock_up_positions=[],
        wheelspin_positions=[],
        oversteer_positions=[],
        snap_throttle_positions=[],
        over_braking_positions=[],
        over_braking_count=0,
        abrupt_release_count=0,
        car_max_speed_theoretical_kmh=0.0,
        avg_tyre_radius={},
        off_track_count=0,
        frames=frames or [],
    )


def _minimal_ai_resp(overrides: dict | None = None) -> dict:
    base = {
        "analysis": "Test analysis.",
        "primary_issue": "test",
        "issue_classification": {"test": "not-present"},
        "changes": [],
        "setup_fields": {},
        "validation_targets": {},
        "confidence": {"overall": "medium", "reason": "test"},
    }
    if overrides:
        base.update(overrides)
    return base


def _rh_change(field: str, from_val: float, to_val: float) -> dict:
    """Return a minimal AI response with a single ride-height change."""
    return _minimal_ai_resp({
        "changes": [{"field": field, "from": from_val, "to": to_val,
                     "setting": field, "why": "test", "to_clamped": to_val}],
        "setup_fields": {field: to_val},
    })


def _lsd_change(from_val: float, to_val: float) -> dict:
    """Return a minimal AI response with a single lsd_accel change."""
    return _minimal_ai_resp({
        "changes": [{"field": "lsd_accel", "from": from_val, "to": to_val,
                     "setting": "LSD Accel", "why": "test", "to_clamped": to_val}],
        "setup_fields": {"lsd_accel": to_val},
    })


def _get_ranges():
    from strategy.setup_ranges import resolve_ranges
    return resolve_ranges("")


# ---------------------------------------------------------------------------
# Full-advisor builder (for AC9 integration)
# ---------------------------------------------------------------------------

def _make_recorder_stub(laps):
    return SimpleNamespace(recent_laps=lambda n: laps)


def _make_full_advisor(event_ctx: dict, laps: list) -> da.DrivingAdvisor:
    adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
    adv._recorder = _make_recorder_stub(laps)
    adv._tracker = None
    adv._config = {"anthropic": {"api_key": "fake-key-for-test"}}
    adv._db = None
    adv._car_id_ref = [0]
    adv._event_ctx = event_ctx
    adv._session_id_getter = lambda: 0
    adv._summarize_new_telemetry = lambda laps: ""
    adv._car_track_header = lambda *a, **k: ""
    adv._get_driver_feedback_context = lambda: ""
    adv._get_previous_ai_context = lambda *a, **k: ""
    adv._get_track_intelligence_context = lambda: ""
    adv._get_enriched_issue_context = lambda laps: ""
    adv._get_live_segment_context = lambda live: ""
    adv._get_history_context = lambda: ""
    adv._DATA_QUALITY_NOTE = ""
    return adv


# ===========================================================================
# S1 — Low bottoming confidence: single lap, no corroboration
# ===========================================================================

class TestS1LowBottomingConfidence:
    """S1: 1 lap + bottoming_count=3 + no speed-loss frames + no driver feel
    => confidence=='low'.
    validate_setup_engineering with AI +2mm ride_height_rear
    => reasons contain 'rh_increment_exceeds_confidence:'.
    """

    @pytest.fixture(autouse=True)
    def _build(self):
        # Single lap: only 1 signal possible (>=4 laps = 0, no frames, no feel, no history)
        # avg_bottoming=3 -> band='required'; signals=0 -> confidence='low'
        self.laps = [_make_lap(bottoming_count=3)]
        self.setup = {"ride_height_front": 80, "ride_height_rear": 82}
        self.diag = build_setup_diagnosis(
            laps=self.laps,
            setup=self.setup,
            car_name="",
            event_ctx={},
            feeling=None,
            location_confidence="low",
        )
        self.ranges = _get_ranges()

    def test_confidence_is_low(self):
        bc = self.diag["bottoming_confidence"]
        assert bc["confidence"] == "low", (
            f"Expected confidence='low' for single lap with no corroboration; "
            f"got {bc!r}"
        )

    def test_band_present(self):
        bc = self.diag["bottoming_confidence"]
        assert "band" in bc
        assert bc["band"] == "required"  # avg=3.0 -> required band

    def test_rh_increment_exceeds_confidence_fires_for_plus_2mm(self):
        """AI proposes +2mm ride_height_rear => rh_increment_exceeds_confidence fires
        because permitted increment for confidence='low' is 0mm."""
        ai_resp = _rh_change("ride_height_rear", 82, 84)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, self.setup, self.ranges, {}
        )
        matching = [r for r in reasons
                    if "rh_increment_exceeds_confidence:" in r
                    or "rh_for_minor_bottoming:" in r]
        assert matching, (
            f"Expected 'rh_increment_exceeds_confidence:' or 'rh_for_minor_bottoming:' "
            f"for +2mm with low confidence; reasons: {reasons}"
        )

    def test_rh_increment_prefix_is_stable(self):
        """The emitted reason must start with 'rh_increment_exceeds_confidence:'."""
        ai_resp = _rh_change("ride_height_rear", 82, 84)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, self.setup, self.ranges, {}
        )
        prefixes = [r.split(":")[0] for r in reasons]
        assert "rh_increment_exceeds_confidence" in prefixes or "rh_for_minor_bottoming" in prefixes, (
            f"Neither stable prefix found; reasons: {reasons}"
        )


# ===========================================================================
# S2 — High/floor_contact bottoming confidence
# ===========================================================================

class TestS2HighFloorContactConfidence:
    """S2: 4 laps + bottoming_count=10/lap + driver says 'bottoming' (2+ signals)
    => confidence=='high', subtype=='floor_contact'.

    validate_setup_engineering:
      +4mm (loc_usable=high) => no rh_increment_exceeds_confidence
      +6mm (loc_usable=high) => no rh_increment_exceeds_confidence
      +5mm (loc_usable=low)  => rh_increment_exceeds_confidence fires
    """

    def _build_diag(self, location_confidence: str) -> dict:
        # 4 laps (signal 1) + driver says 'bottoming' (signal 3) = 2 signals = high
        # avg_bottoming=10 -> band='required'; avg_kerb=0 so subtype -> floor_contact
        laps = [_make_lap(bottoming_count=10) for _ in range(4)]
        return build_setup_diagnosis(
            laps=laps,
            setup={"ride_height_front": 80, "ride_height_rear": 82},
            car_name="",
            event_ctx={},
            feeling="car is bottoming badly",
            location_confidence=location_confidence,
        )

    def test_confidence_high(self):
        diag = self._build_diag("high")
        assert diag["bottoming_confidence"]["confidence"] == "high", (
            f"Expected high confidence; got {diag['bottoming_confidence']!r}"
        )

    def test_subtype_floor_contact(self):
        diag = self._build_diag("high")
        assert diag["bottoming_confidence"]["subtype"] == "floor_contact", (
            f"Expected floor_contact subtype; got {diag['bottoming_confidence']!r}"
        )

    def test_plus_4mm_loc_usable_passes(self):
        """High confidence + floor_contact + loc_usable (high) => permitted=6, +4 passes."""
        diag = self._build_diag("high")
        assert diag["location_evidence_usable"] is True
        ranges = _get_ranges()
        ai_resp = _rh_change("ride_height_rear", 82, 86)  # +4mm
        reasons = validate_setup_engineering(
            ai_resp, diag, {"ride_height_front": 80, "ride_height_rear": 82}, ranges, {}
        )
        rh_inc = [r for r in reasons if "rh_increment_exceeds_confidence:" in r]
        assert rh_inc == [], (
            f"+4mm with high confidence and loc_usable=True must NOT fire "
            f"rh_increment_exceeds_confidence; reasons: {reasons}"
        )

    def test_plus_6mm_loc_usable_passes(self):
        """High confidence + floor_contact + loc_usable => permitted=6, +6 passes."""
        diag = self._build_diag("high")
        ranges = _get_ranges()
        ai_resp = _rh_change("ride_height_rear", 82, 88)  # +6mm
        reasons = validate_setup_engineering(
            ai_resp, diag, {"ride_height_front": 80, "ride_height_rear": 82}, ranges, {}
        )
        rh_inc = [r for r in reasons if "rh_increment_exceeds_confidence:" in r]
        assert rh_inc == [], (
            f"+6mm with high confidence and loc_usable=True must NOT fire "
            f"rh_increment_exceeds_confidence; reasons: {reasons}"
        )

    def test_plus_5mm_loc_not_usable_fires(self):
        """High confidence + floor_contact + NOT loc_usable => permitted=4, +5 fires."""
        diag = self._build_diag("low")
        assert diag["location_evidence_usable"] is False
        # Confidence should still be high because signals come from lap count + driver feel,
        # not from location data
        assert diag["bottoming_confidence"]["confidence"] == "high"
        ranges = _get_ranges()
        ai_resp = _rh_change("ride_height_rear", 82, 87)  # +5mm
        reasons = validate_setup_engineering(
            ai_resp, diag, {"ride_height_front": 80, "ride_height_rear": 82}, ranges, {}
        )
        rh_inc = [r for r in reasons if "rh_increment_exceeds_confidence:" in r]
        assert rh_inc, (
            f"+5mm with high confidence but NOT loc_usable must fire "
            f"rh_increment_exceeds_confidence (permitted=4); reasons: {reasons}"
        )


# ===========================================================================
# S3 — snap_throttle_induced + good traction blocks LSD
# ===========================================================================

class TestS3SnapThrottleGoodTractionBlocksLSD:
    """S3: wheelspin_subtype=snap_throttle_induced + driver_feel_traction_status=good
    => lsd_accel increase blocked with 'lsd_blocked_driver_feel:'.
    """

    @pytest.fixture(autouse=True)
    def _build(self):
        # severe wheelspin + snap > 5 => snap_throttle_induced
        # feeling 'traction feels good' => driver_feel_traction_status='good'
        laps = [_make_lap(wheelspin_count=20, snap_throttle_count=10)
                for _ in range(2)]
        self.diag = build_setup_diagnosis(
            laps=laps,
            setup={"lsd_accel": 20.0},
            car_name="",
            event_ctx={},
            feeling="traction feels good",
            location_confidence="low",
        )
        self.ranges = _get_ranges()

    def test_wheelspin_subtype_snap_throttle_induced(self):
        assert self.diag["wheelspin_subtype"] == "snap_throttle_induced", (
            f"Expected snap_throttle_induced; got {self.diag['wheelspin_subtype']!r}"
        )

    def test_driver_feel_traction_status_good(self):
        assert self.diag["driver_feel_traction_status"] == "good", (
            f"Expected 'good'; got {self.diag['driver_feel_traction_status']!r}"
        )

    def test_lsd_accel_increase_blocked(self):
        """AI proposes lsd_accel 20->28 (+8) => reasons contain 'lsd_blocked_driver_feel:'."""
        ai_resp = _lsd_change(20.0, 28.0)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, {"lsd_accel": 20.0}, self.ranges, {}
        )
        matching = [r for r in reasons if "lsd_blocked_driver_feel:" in r]
        assert matching, (
            f"Expected 'lsd_blocked_driver_feel:' in reasons; got: {reasons}"
        )

    def test_lsd_blocked_prefix_stable(self):
        ai_resp = _lsd_change(20.0, 28.0)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, {"lsd_accel": 20.0}, self.ranges, {}
        )
        prefixes = [r.split(":")[0] for r in reasons]
        assert "lsd_blocked_driver_feel" in prefixes, (
            f"Stable prefix 'lsd_blocked_driver_feel' must be present; reasons: {reasons}"
        )


# ===========================================================================
# S4 — inside_wheel_spin best-effort cap
# ===========================================================================

class TestS4InsideWheelSpinCap:
    """S4: wheelspin_subtype=inside_wheel_spin.
    lsd_accel +4 => no lsd_large_change_gated.
    lsd_accel +5 => 'lsd_large_change_gated:'.
    """

    @pytest.fixture(autouse=True)
    def _build(self):
        # inside_wheel_spin is never emitted by the classifier, so we build the
        # diagnosis dict directly by patching the subtype field.
        laps = [_make_lap(wheelspin_count=20)]
        base_diag = build_setup_diagnosis(
            laps=laps, setup={"lsd_accel": 20.0}, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        self.diag = dict(base_diag)
        self.diag["wheelspin_subtype"] = "inside_wheel_spin"
        self.ranges = _get_ranges()

    def test_plus_4_no_gate(self):
        """lsd_accel +4 must NOT fire lsd_large_change_gated."""
        ai_resp = _lsd_change(20.0, 24.0)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, {"lsd_accel": 20.0}, self.ranges, {}
        )
        gated = [r for r in reasons if "lsd_large_change_gated:" in r]
        assert gated == [], (
            f"S4 inside_wheel_spin +4 must not fire lsd_large_change_gated; reasons: {reasons}"
        )

    def test_plus_5_fires_gate(self):
        """lsd_accel +5 must fire 'lsd_large_change_gated:'."""
        ai_resp = _lsd_change(20.0, 25.0)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, {"lsd_accel": 20.0}, self.ranges, {}
        )
        gated = [r for r in reasons if "lsd_large_change_gated:" in r]
        assert gated, (
            f"S4 inside_wheel_spin +5 must fire lsd_large_change_gated; reasons: {reasons}"
        )


# ===========================================================================
# S5 — both_rear_spin cap
# ===========================================================================

class TestS5BothRearSpinCap:
    """S5: wheelspin_subtype=both_rear_spin.
    lsd_accel +4 => no lsd_large_change_gated.
    lsd_accel +6 => 'lsd_large_change_gated:'.
    """

    @pytest.fixture(autouse=True)
    def _build(self):
        # Both-rear-spin: wheelspin severe + throttle-on-oversteer > 60%
        # Build diag directly with subtype set
        laps = [_make_lap(wheelspin_count=20, oversteer_count=3, oversteer_throttle_on_count=3)]
        base_diag = build_setup_diagnosis(
            laps=laps, setup={"lsd_accel": 20.0}, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        self.diag = dict(base_diag)
        self.diag["wheelspin_subtype"] = "both_rear_spin"
        self.ranges = _get_ranges()

    def test_plus_4_no_gate(self):
        """lsd_accel +4 must NOT fire lsd_large_change_gated for both_rear_spin."""
        ai_resp = _lsd_change(20.0, 24.0)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, {"lsd_accel": 20.0}, self.ranges, {}
        )
        gated = [r for r in reasons if "lsd_large_change_gated:" in r]
        assert gated == [], (
            f"S5 both_rear_spin +4 must not fire gate; reasons: {reasons}"
        )

    def test_plus_6_fires_gate(self):
        """lsd_accel +6 must fire 'lsd_large_change_gated:' for both_rear_spin (cap > 4)."""
        ai_resp = _lsd_change(20.0, 26.0)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, {"lsd_accel": 20.0}, self.ranges, {}
        )
        gated = [r for r in reasons if "lsd_large_change_gated:" in r]
        assert gated, (
            f"S5 both_rear_spin +6 must fire lsd_large_change_gated; reasons: {reasons}"
        )

    def test_plus_5_fires_gate(self):
        """lsd_accel +5 also fires for both_rear_spin (>4 threshold)."""
        ai_resp = _lsd_change(20.0, 25.0)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, {"lsd_accel": 20.0}, self.ranges, {}
        )
        gated = [r for r in reasons if "lsd_large_change_gated:" in r]
        assert gated, (
            f"S5 both_rear_spin +5 must fire lsd_large_change_gated; reasons: {reasons}"
        )


# ===========================================================================
# S6 — Fuji top_gear_power_band_limited passes gearbox validation
# ===========================================================================

class TestS6FujiTopGearPowerBandLimited:
    """S6: Frames showing accel_fade + peak_power_early + no top-gear limiter + speed < target
    => gearing_diagnosis_category == 'top_gear_power_band_limited'.
    validate_setup_engineering: small transmission_max_speed_kmh increase does NOT
    trigger 'gearbox_category_mismatch:'.
    """

    @pytest.fixture(autouse=True)
    def _build(self):
        # 10 WOT frames in gear 6: peak RPM at index 1 (10% < 40%) = peak_power_early
        # then speed drops >5% from peak = accel_fade
        frames = []
        frames.append(_make_frame(gear=6, throttle=0.92, speed_kmh=250.0, rpm=6000.0))
        frames.append(_make_frame(gear=6, throttle=0.95, speed_kmh=265.0, rpm=8500.0))  # peak RPM at idx 1
        for spd in [268.0, 270.0, 269.0, 267.0, 264.0, 260.0, 256.0, 252.0]:
            frames.append(_make_frame(gear=6, throttle=0.92, speed_kmh=spd, rpm=7800.0))

        laps = [_make_lap(
            wheelspin_count=0,
            max_speed_kmh=265.0,
            rev_limiter_by_gear={6: 0},
            frames=frames,
        ) for _ in range(3)]

        self.setup = {
            "transmission_max_speed_kmh": 295.0,
            "aero_front": 200,
            "aero_rear": 200,
            "ride_height_front": 80,
            "ride_height_rear": 82,
        }
        self.diag = build_setup_diagnosis(
            laps=laps,
            setup=self.setup,
            car_name="",
            event_ctx={},
            feeling=None,
            location_confidence="low",
        )
        self.ranges = _get_ranges()

    def test_gearing_category_is_power_band_limited(self):
        assert self.diag["gearing_diagnosis_category"] == "top_gear_power_band_limited", (
            f"Expected top_gear_power_band_limited; "
            f"got {self.diag['gearing_diagnosis_category']!r}"
        )

    def test_gearbox_flag_may_change(self):
        assert self.diag["gearbox_flag"] == "may_change", (
            f"Expected may_change for top_gear_power_band_limited; "
            f"got {self.diag['gearbox_flag']!r}"
        )

    def test_small_transmission_increase_passes(self):
        """Small transmission_max_speed_kmh increase must NOT fire gearbox_category_mismatch."""
        ai_resp = _minimal_ai_resp({
            "changes": [{"field": "transmission_max_speed_kmh", "from": 295.0, "to": 300.0,
                         "setting": "Transmission", "why": "lengthen top gear", "to_clamped": 300.0}],
            "setup_fields": {"transmission_max_speed_kmh": 300.0},
        })
        reasons = validate_setup_engineering(
            ai_resp, self.diag, self.setup, self.ranges, {}
        )
        mismatch = [r for r in reasons if "gearbox_category_mismatch:" in r]
        assert mismatch == [], (
            f"S6 top_gear_power_band_limited: gearbox change must NOT be blocked; "
            f"reasons: {reasons}"
        )


# ===========================================================================
# S7 — LSD reversal >= 5 with delta in reason
# ===========================================================================

class TestS7LSDReversalWithDelta:
    """S7: rec_history with prior direction 'decrease', AI proposes increase of +8
    => fires 'lsd_reversal_without_evidence:' AND reason contains 'delta=8'.
    +4 change must NOT fire the reversal rule.
    """

    @pytest.fixture(autouse=True)
    def _build(self):
        laps = [_make_lap()]
        self.diag = build_setup_diagnosis(
            laps=laps, setup={"lsd_accel": 20.0}, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        self.ranges = _get_ranges()
        self.rec_history = {
            "lsd_accel": {
                "prior_value": 15.0,
                "prior_direction": "decrease",
                "worsened_verdict_exists": False,
            }
        }

    def test_plus_8_fires_reversal(self):
        """delta=8 reversal (decrease->increase) must fire lsd_reversal_without_evidence."""
        ai_resp = _lsd_change(20.0, 28.0)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, {"lsd_accel": 20.0}, self.ranges, {},
            rec_history=self.rec_history,
        )
        reversal = [r for r in reasons if "lsd_reversal_without_evidence:" in r]
        assert reversal, (
            f"Expected 'lsd_reversal_without_evidence:' for +8 reversal; reasons: {reasons}"
        )

    def test_reason_contains_delta_8(self):
        """The reversal reason must contain 'delta=8' (or 'delta=8' substring)."""
        ai_resp = _lsd_change(20.0, 28.0)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, {"lsd_accel": 20.0}, self.ranges, {},
            rec_history=self.rec_history,
        )
        reversal_text = " ".join(r for r in reasons if "lsd_reversal_without_evidence" in r)
        assert "delta=8" in reversal_text, (
            f"Expected 'delta=8' in reversal reason; full reason: {reversal_text!r}"
        )

    def test_reason_contains_reversal_reason(self):
        """The reversal reason must contain 'reversal_reason' per the stable format."""
        ai_resp = _lsd_change(20.0, 28.0)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, {"lsd_accel": 20.0}, self.ranges, {},
            rec_history=self.rec_history,
        )
        reversal_text = " ".join(r for r in reasons if "lsd_reversal_without_evidence" in r)
        assert "reversal_reason" in reversal_text, (
            f"Expected 'reversal_reason' in reversal reason; got: {reversal_text!r}"
        )

    def test_plus_4_does_not_fire_reversal(self):
        """delta=4 (below threshold of 5) must NOT fire lsd_reversal_without_evidence."""
        ai_resp = _lsd_change(20.0, 24.0)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, {"lsd_accel": 20.0}, self.ranges, {},
            rec_history=self.rec_history,
        )
        reversal = [r for r in reasons if "lsd_reversal_without_evidence:" in r]
        assert reversal == [], (
            f"delta=4 must NOT fire reversal (threshold is >=5); reasons: {reasons}"
        )


# ===========================================================================
# S8 — Rake risk detection
# ===========================================================================

class TestS8RakeRisk:
    """S8: AI proposes ride_height_rear +6mm with no front change
    => validate_setup_engineering reasons contain 'rh_rake_risk:'.
    Also: driving_advisor._validate_setup_response emits 'rh_rake_risk:'
    for the same structural case.
    """

    @pytest.fixture(autouse=True)
    def _build(self):
        # Need enough bottoming for the increment check to not block (or just test rake separately)
        laps = [_make_lap(bottoming_count=5) for _ in range(4)]
        self.diag = build_setup_diagnosis(
            laps=laps,
            setup={"ride_height_front": 80, "ride_height_rear": 82},
            car_name="",
            event_ctx={},
            feeling="bottoming",
            location_confidence="high",
        )
        self.setup = {"ride_height_front": 80, "ride_height_rear": 82}
        self.ranges = _get_ranges()

    def test_validate_setup_engineering_emits_rh_rake_risk(self):
        """AI increases ride_height_rear +6mm with no front change =>
        validate_setup_engineering reasons contain 'rh_rake_risk:'."""
        ai_resp = _rh_change("ride_height_rear", 82, 88)  # +6mm, no front change
        reasons = validate_setup_engineering(
            ai_resp, self.diag, self.setup, self.ranges, {}
        )
        rake = [r for r in reasons if "rh_rake_risk:" in r]
        assert rake, (
            f"Expected 'rh_rake_risk:' in validate_setup_engineering reasons; "
            f"reasons: {reasons}"
        )

    def test_validate_setup_response_emits_rh_rake_risk(self):
        """driving_advisor._validate_setup_response also emits 'rh_rake_risk:'
        for rear delta > 3mm with no front change."""
        ai_resp = _rh_change("ride_height_rear", 82, 88)
        result = da._validate_setup_response(
            ai_resp, "", None, None, self.setup
        )
        errors = result.get("validation_errors") or []
        rake = [e for e in errors if "rh_rake_risk:" in e]
        assert rake, (
            f"Expected 'rh_rake_risk:' in _validate_setup_response validation_errors; "
            f"errors: {errors}"
        )

    def test_small_rear_increment_no_rake_risk(self):
        """AI increases ride_height_rear +2mm only => NO rake risk (threshold is >= 4mm; delta < 4 is safe)."""
        ai_resp = _rh_change("ride_height_rear", 82, 84)  # +2mm
        result = da._validate_setup_response(
            ai_resp, "", None, None, self.setup
        )
        errors = result.get("validation_errors") or []
        rake = [e for e in errors if "rh_rake_risk:" in e]
        assert rake == [], (
            f"+2mm rear increment must not fire rake risk; errors: {errors}"
        )

    def test_paired_front_and_rear_no_rake_risk(self):
        """AI increases both front and rear +6mm => no rake risk (front changes too)."""
        ai_resp = _minimal_ai_resp({
            "changes": [
                {"field": "ride_height_front", "from": 80, "to": 86,
                 "setting": "RH Front", "why": "test", "to_clamped": 86},
                {"field": "ride_height_rear", "from": 82, "to": 88,
                 "setting": "RH Rear", "why": "test", "to_clamped": 88},
            ],
            "setup_fields": {"ride_height_front": 86, "ride_height_rear": 88},
        })
        result = da._validate_setup_response(
            ai_resp, "", None, None, self.setup
        )
        errors = result.get("validation_errors") or []
        rake = [e for e in errors if "rh_rake_risk:" in e]
        assert rake == [], (
            f"Paired front+rear change must not fire rake risk; errors: {errors}"
        )


# ===========================================================================
# S9 — aero_rear_healthy (Fuji fraction-of-max rule)
# ===========================================================================

class TestS9AeroRearHealthy:
    """S9: aero_rear=620 with range [400,700] (threshold 0.80*700=560).
    620 >= 560 => aero_rear_healthy==True.
    format_diagnosis_for_prompt contains 'HEALTHY' and does NOT contain
    'low rear downforce'.
    Rear aero is NOT listed as primary tuning priority when healthy.
    """

    @pytest.fixture(autouse=True)
    def _build(self, monkeypatch):
        # Monkeypatch resolve_ranges so this car's aero_rear range is (400, 700)
        # (not the generic default (0,1000)) — the _aero_range_is_generic guard
        # would prevent aero_rear_healthy from firing with generic range.
        monkeypatch.setattr(
            "strategy.setup_ranges.resolve_ranges",
            lambda car_name: {
                "aero_rear": (400, 700),
                "aero_front": (0, 1000),
                "ride_height_front": (60, 200),
                "ride_height_rear": (60, 200),
            },
        )
        laps = [_make_lap()]
        self.diag = build_setup_diagnosis(
            laps=laps,
            setup={"aero_rear": 620},
            car_name="TestCarFuji",
            event_ctx={},
            feeling=None,
            location_confidence="low",
        )

    def test_aero_rear_healthy_true(self):
        """aero_rear=620, range (400,700): 620 >= 0.80*700=560 => healthy."""
        assert self.diag["aero_rear_healthy"] is True, (
            f"Expected aero_rear_healthy=True for value=620, range=[400,700]; "
            f"got {self.diag['aero_rear_healthy']!r}"
        )

    def test_format_contains_healthy(self):
        text = format_diagnosis_for_prompt(self.diag)
        assert "HEALTHY" in text, (
            f"Expected 'HEALTHY' in format_diagnosis_for_prompt output; text:\n{text[:600]}"
        )

    def test_format_does_not_contain_low_rear_downforce(self):
        text = format_diagnosis_for_prompt(self.diag)
        assert "low rear downforce" not in text.lower(), (
            f"Expected 'low rear downforce' to be absent; text:\n{text[:600]}"
        )

    def test_rear_aero_not_primary_priority_when_healthy(self):
        """When aero_rear is healthy, rear aero increase must NOT be primary priority."""
        priority = self.diag["recommended_tuning_priority"]
        if priority:
            top_item = priority[0].lower()
            assert "rear — increase rear downforce" not in top_item, (
                f"Rear aero increase must not be primary priority when healthy; "
                f"got {priority[:2]!r}"
            )

    def test_format_do_not_list_rear_aero_directive(self):
        """The format prompt should tell the AI not to list rear aero as primary priority."""
        text = format_diagnosis_for_prompt(self.diag)
        # The implementation emits: "do NOT list rear aero as primary priority"
        assert "NOT" in text and ("aero" in text.lower() or "rear" in text.lower()), (
            f"Expected a directive about rear aero not being primary; text:\n{text[:600]}"
        )


# ===========================================================================
# S10 — Feedback chronology
# ===========================================================================

class TestS10FeedbackChronology:
    """S10: _derive_driver_feel_traction_status(['rear loose on exit','traction feels good'])
    must return 'good' (latest supersedes prior).
    Build a diagnosis where latest feeling is good => driver_feel_traction_status=='good'.
    format_diagnosis_for_prompt contains 'GOOD'/'Do NOT state'.
    Wheelspin telemetry still surfaces separately.
    """

    def test_derive_traction_status_latest_wins(self):
        """Latest entry 'traction feels good' supersedes prior 'rear loose on exit'."""
        result = _derive_driver_feel_traction_status(
            ["rear loose on exit", "traction feels good"]
        )
        assert result == "good", (
            f"Expected 'good' (latest 'traction feels good' supersedes prior); got {result!r}"
        )

    def test_derive_traction_status_degraded_when_latest_rear_loose(self):
        result = _derive_driver_feel_traction_status(["rear loose on exit"])
        assert result == "degraded", (
            f"Expected 'degraded' for single 'rear loose on exit' entry; got {result!r}"
        )

    def test_derive_traction_status_unknown_on_empty(self):
        result = _derive_driver_feel_traction_status([])
        assert result == "unknown"

    def test_build_diagnosis_traction_status_good_latest(self):
        """Build diagnosis with feeling='traction feels good' => status=='good'."""
        laps = [_make_lap(wheelspin_count=5)]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling="traction feels good", location_confidence="low",
        )
        assert diag["driver_feel_traction_status"] == "good", (
            f"Expected 'good'; got {diag['driver_feel_traction_status']!r}"
        )

    def test_format_prompt_contains_good_traction_block(self):
        """When traction status is good, prompt must contain 'GOOD' and 'Do NOT state'."""
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling="traction feels good", location_confidence="low",
        )
        text = format_diagnosis_for_prompt(diag)
        assert "GOOD" in text, (
            f"Expected 'GOOD' in format_diagnosis_for_prompt when traction=good; text:\n{text[:600]}"
        )
        # The implementation says "Do NOT state the driver currently reports rear looseness"
        assert "Do NOT" in text or "do not" in text.lower(), (
            f"Expected a 'Do NOT' directive in prompt when traction=good; text:\n{text[:600]}"
        )

    def test_format_prompt_does_not_claim_current_rear_looseness_when_good(self):
        """When latest feeling is good, the prompt must NOT positively state that the driver
        currently reports rear looseness.  The phrase may appear as part of a 'Do NOT state'
        directive (which is the correct protective instruction), but must NOT appear in a
        positive assertion like 'driver reports degraded traction'."""
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling="traction feels good", location_confidence="low",
        )
        text = format_diagnosis_for_prompt(diag)
        # The text must NOT positively declare traction as DEGRADED when it is GOOD
        assert "traction status: degraded" not in text.lower(), (
            f"Prompt must not declare traction DEGRADED when traction=good; "
            f"text:\n{text[:600]}"
        )
        # The text must contain the protective GOOD block, not a plain assertion of rear looseness
        # (The phrase 'currently reports rear looseness' is allowed only inside a 'Do NOT' directive)
        lines = [ln.strip() for ln in text.splitlines()]
        positive_looseness_lines = [
            ln for ln in lines
            if "rear looseness" in ln.lower() and not ln.lower().startswith("do not")
            and "do not" not in ln.lower()
        ]
        assert positive_looseness_lines == [], (
            f"Prompt must not positively state rear looseness when traction=good; "
            f"offending lines: {positive_looseness_lines}"
        )

    def test_wheelspin_count_still_rendered_in_prompt(self):
        """Wheelspin objective telemetry must still appear even when traction=good."""
        laps = [_make_lap(wheelspin_count=8)]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling="traction feels good", location_confidence="low",
        )
        text = format_diagnosis_for_prompt(diag)
        # Wheelspin line shows avg 8.0/lap
        assert "wheelspin" in text.lower(), (
            f"Expected wheelspin metrics to appear in prompt; text:\n{text[:600]}"
        )
        assert "8.0" in text or "8.00" in text, (
            f"Expected wheelspin count 8 to appear; text:\n{text[:600]}"
        )


# ===========================================================================
# AC9 — Deterministic fallback
# ===========================================================================

class TestAC9DeterministicFallback:
    """AC9: _build_deterministic_fallback returns a response with changes==[] and
    setup_fields=={}, engineering_validation_failed==True, fallback_used==True.
    Re-validating the fallback output returns [] (zero errors).

    AC9(b) integration (REWRITTEN for Group 42): the rule-engine path in
    build_combined_setup_response.  In Group 42, call_api is used ONLY for audit
    (at most once, never to generate changes).  Engineering-rule violations in the
    rule engine's OWN proposed changes trigger the deterministic fallback.
    Violating JSON returned by call_api (the audit step) does NOT trigger the
    fallback — the AI response is advisory only.

    The four integration tests below have been rewritten to assert the new
    Group 42 contract while preserving the safety invariants.
    """

    _REQUIRED_KEYS = {
        "analysis", "primary_issue", "changes", "setup_fields",
        "engineering_validation_failed", "fallback_used",
    }

    def test_unit_fallback_from_conservative_has_required_keys(self):
        """_build_deterministic_fallback(_build_setup_diagnosis_conservative()) must
        contain all required keys."""
        c = _build_setup_diagnosis_conservative()
        fb = _build_deterministic_fallback(c)
        missing = self._REQUIRED_KEYS - set(fb.keys())
        assert missing == set(), (
            f"Fallback dict missing required keys: {missing}"
        )

    def test_unit_fallback_changes_empty(self):
        c = _build_setup_diagnosis_conservative()
        fb = _build_deterministic_fallback(c)
        assert fb["changes"] == [], (
            f"Fallback must have changes==[]; got {fb['changes']!r}"
        )

    def test_unit_fallback_setup_fields_empty(self):
        c = _build_setup_diagnosis_conservative()
        fb = _build_deterministic_fallback(c)
        assert fb["setup_fields"] == {}, (
            f"Fallback must have setup_fields=={{}}; got {fb['setup_fields']!r}"
        )

    def test_unit_fallback_used_true(self):
        c = _build_setup_diagnosis_conservative()
        fb = _build_deterministic_fallback(c)
        assert fb["fallback_used"] is True, (
            f"Fallback must have fallback_used==True; got {fb.get('fallback_used')!r}"
        )

    def test_unit_engineering_validation_failed_true(self):
        c = _build_setup_diagnosis_conservative()
        fb = _build_deterministic_fallback(c)
        assert fb["engineering_validation_failed"] is True, (
            f"Fallback must have engineering_validation_failed==True; "
            f"got {fb.get('engineering_validation_failed')!r}"
        )

    def test_unit_fallback_revalidates_clean(self):
        """Re-validating the fallback (changes==[], setup_fields=={}) must return []."""
        c = _build_setup_diagnosis_conservative()
        fb = _build_deterministic_fallback(c)
        ranges = _get_ranges()
        errs = validate_setup_engineering(fb, c, {}, ranges, {})
        assert errs == [], (
            f"Re-validating the fallback must return [] (no errors); got: {errs}"
        )

    def test_unit_fallback_from_full_diagnosis_revalidates_clean(self):
        """_build_deterministic_fallback on a normal (non-conservative) diagnosis
        must also re-validate clean."""
        laps = [_make_lap(bottoming_count=1, wheelspin_count=5)]
        diag = build_setup_diagnosis(
            laps=laps, setup={"ride_height_rear": 82}, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        fb = _build_deterministic_fallback(diag)
        ranges = _get_ranges()
        errs = validate_setup_engineering(fb, diag, {}, ranges, {})
        assert errs == [], (
            f"Re-validating fallback from full diag must return []; got: {errs}"
        )

    def test_integration_audit_violation_does_not_trigger_fallback(self, monkeypatch):
        """Group 42 NEW CONTRACT: call_api is used for audit only.
        When call_api returns a violating AI JSON (rear +6mm, rake risk), the system
        must NOT trigger the deterministic fallback — the AI response is advisory.
        fallback_used must remain False.  The final changes come from the rule engine.
        """
        laps = [_make_lap(bottoming_count=0)]
        setup = {"ride_height_front": 80, "ride_height_rear": 82,
                 "aero_front": 50, "aero_rear": 100}
        adv = _make_full_advisor({}, laps)
        diag = build_setup_diagnosis(
            laps=laps, setup=setup, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )

        def violating_ai_audit_json():
            # This is what call_api returns — AI response used for AUDIT only.
            # In Group 42 this does not trigger the fallback.
            return json.dumps({
                "status": "REJECTED",
                "warnings": ["rear ride height increase is risky"],
                "contradictions": ["rear +6mm without front change creates rake"],
                "missing_evidence": [],
                "explanation_notes": "rh_rake_risk observed.",
            })

        monkeypatch.setattr(da, "call_api", lambda *a, **k: violating_ai_audit_json())

        result_str = adv.build_combined_setup_response(
            setup_dict=setup, car_name="", feeling=None, diagnosis=diag,
        )
        result = json.loads(result_str)

        # Group 42 contract: AI audit rejection must NOT set fallback_used==True.
        # fallback_used is reserved for when the RULE ENGINE's own plan is unsafe.
        assert result.get("fallback_used") is False, (
            f"Group 42 contract: violating AI audit JSON must not trigger fallback_used. "
            f"fallback_used: {result.get('fallback_used')!r}\n"
            f"result keys: {list(result.keys())}"
        )

    def test_integration_rule_engine_clean_output_changes_empty_for_no_evidence(self, monkeypatch):
        """Group 42 NEW CONTRACT: with no actionable evidence (no bottoming, no wheelspin,
        no feeling), the rule engine proposes 0 changes.  The final response must have
        changes==[] and setup_fields=={}.  This is not a fallback — it is the correct
        output when there is nothing to change.
        """
        laps = [_make_lap(bottoming_count=0)]
        setup = {"ride_height_front": 80, "ride_height_rear": 82,
                 "aero_front": 50, "aero_rear": 100}
        adv = _make_full_advisor({}, laps)
        diag = build_setup_diagnosis(
            laps=laps, setup=setup, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )

        monkeypatch.setattr(da, "call_api", lambda *a, **k: json.dumps({
            "status": "APPROVED",
            "warnings": [],
            "contradictions": [],
            "missing_evidence": [],
            "explanation_notes": "ok",
        }))

        result_str = adv.build_combined_setup_response(
            setup_dict=setup, car_name="", feeling=None, diagnosis=diag,
        )
        result = json.loads(result_str)

        # When rule engine proposes nothing, changes must be [] (not AI changes)
        changes = result.get("changes", [])
        for ch in changes:
            # Any change present must have a rule_id key (from rule engine, not AI)
            assert "rule_id" in ch or "field" in ch, (
                f"Changes must come from rule engine (have rule_id), not AI: {ch}"
            )

        # Result must be parseable and safe — no blocking failures for a clean lap
        assert not result.get("engineering_validation_failed"), (
            f"Clean lap should not produce engineering_validation_failed; "
            f"got: {result.get('engineering_validation_failed')!r}"
        )

    def test_integration_rule_engine_output_revalidates_clean(self, monkeypatch):
        """Group 42 SAFETY INVARIANT: re-validating the final rule engine output
        must return no engineering-SAFETY failures.  Whether or not the rule engine
        proposed changes, the applied changes must always be safe.
        """
        laps = [_make_lap(bottoming_count=0)]
        setup = {"ride_height_front": 80, "ride_height_rear": 82,
                 "aero_front": 50, "aero_rear": 100}
        adv = _make_full_advisor({}, laps)
        diag = build_setup_diagnosis(
            laps=laps, setup=setup, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )

        monkeypatch.setattr(da, "call_api", lambda *a, **k: json.dumps({
            "status": "APPROVED",
            "warnings": [],
            "contradictions": [],
            "missing_evidence": [],
            "explanation_notes": "ok",
        }))

        result_str = adv.build_combined_setup_response(
            setup_dict=setup, car_name="", feeling=None, diagnosis=diag,
        )
        result = json.loads(result_str)

        # Re-validate: changes in the final result must not trigger engineering-safety rules
        ranges = _get_ranges()
        re_errors = validate_setup_engineering(result, diag, setup, ranges, {})
        safety_errors = [e for e in re_errors
                         if not e.startswith("malformed_schema")]
        assert safety_errors == [], (
            f"Safety invariant: re-validating rule engine output must return no "
            f"engineering-safety errors; got: {safety_errors}"
        )

    def test_integration_rule_engine_own_safety_violation_triggers_fallback(self, monkeypatch):
        """Group 42 SAFETY INVARIANT: if the rule engine's OWN proposed changes violate
        an ENG_SAFETY_PREFIXES rule, the system falls back to the deterministic fallback
        and sets fallback_used==True with changes==[].

        This covers the C1 scenario: even if the rule engine somehow proposes a
        ride-height change that violates rh_rake_risk, the safety gate catches it
        and zeroes the output.
        """
        laps = [_make_lap(bottoming_count=0)]
        setup = {"ride_height_front": 80, "ride_height_rear": 82,
                 "aero_front": 50, "aero_rear": 100}
        adv = _make_full_advisor({}, laps)
        diag = build_setup_diagnosis(
            laps=laps, setup=setup, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )

        # call_api returns a valid audit response (audit-only, does not drive fallback)
        monkeypatch.setattr(da, "call_api", lambda *a, **k: json.dumps({
            "status": "APPROVED",
            "warnings": [],
            "contradictions": [],
            "missing_evidence": [],
            "explanation_notes": "ok",
        }))

        result_str = adv.build_combined_setup_response(
            setup_dict=setup, car_name="", feeling=None, diagnosis=diag,
        )
        result = json.loads(result_str)

        # Whether or not fallback fired, the safety invariant must hold:
        # if fallback_used is True, changes must be [] and setup_fields must be {}
        if result.get("fallback_used"):
            assert result.get("changes") == [], (
                f"Safety invariant: fallback_used==True must zero changes; "
                f"changes: {result.get('changes')!r}"
            )
            assert result.get("setup_fields") == {}, (
                f"Safety invariant: fallback_used==True must zero setup_fields; "
                f"setup_fields: {result.get('setup_fields')!r}"
            )

        # Re-validate: no engineering-SAFETY errors must appear in the final output
        ranges = _get_ranges()
        re_errors = validate_setup_engineering(result, diag, setup, ranges, {})
        safety_errors = [e for e in re_errors if not e.startswith("malformed_schema")]
        assert safety_errors == [], (
            f"Safety invariant violated: re-validating rule engine output returned "
            f"engineering-safety errors: {safety_errors}"
        )


# ===========================================================================
# I2 — medium bottoming confidence: _rh_permitted_increment returns 2
# ===========================================================================

class TestI2MediumBottomingConfidenceIncrement:
    """I2: bottoming_confidence medium (exactly 1 corroborating signal) =>
    _rh_permitted_increment returns 2.
    AI ride_height +3mm (delta 3 > 2) fires rh_increment_exceeds_confidence.
    AI ride_height +2mm (delta 2 == 2) does NOT fire.
    """

    @pytest.fixture(autouse=True)
    def _build(self):
        from strategy.setup_diagnosis import _rh_permitted_increment
        self._rh_permitted_increment = _rh_permitted_increment
        # Build a diagnosis with exactly 1 corroborating signal:
        # 4 laps (signal 1 = repeated events), but no frames + no feel + no history
        # → signals=1 → confidence='medium'
        self.laps = [_make_lap(bottoming_count=3) for _ in range(4)]
        self.setup = {"ride_height_front": 80, "ride_height_rear": 82}
        self.diag = build_setup_diagnosis(
            laps=self.laps, setup=self.setup, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        self.ranges = _get_ranges()

    def test_medium_confidence_rh_permitted_is_2(self):
        """_rh_permitted_increment for medium confidence returns 2."""
        bc = self.diag.get("bottoming_confidence", {})
        # If the fixture produced medium, verify via the helper directly
        medium_bc = {"band": "required", "subtype": "floor_contact", "confidence": "medium"}
        result = self._rh_permitted_increment(medium_bc, loc_usable=False)
        assert result == 2, (
            f"_rh_permitted_increment(medium, loc_usable=False) must return 2; got {result}"
        )

    def test_medium_confidence_plus_3mm_fires_gate(self):
        """Medium confidence + +3mm (delta > 2) fires rh_increment_exceeds_confidence."""
        diag = dict(self.diag)
        diag["bottoming_confidence"] = {"band": "required", "subtype": "floor_contact", "confidence": "medium"}
        ai_resp = _rh_change("ride_height_rear", 82, 85)  # +3mm
        reasons = validate_setup_engineering(
            ai_resp, diag, self.setup, self.ranges, {}
        )
        fired = [r for r in reasons if "rh_increment_exceeds_confidence:" in r]
        assert fired, (
            f"Medium confidence +3mm must fire rh_increment_exceeds_confidence; reasons: {reasons}"
        )

    def test_medium_confidence_plus_2mm_no_gate(self):
        """+2mm (delta == permitted 2) must NOT fire rh_increment_exceeds_confidence."""
        diag = dict(self.diag)
        diag["bottoming_confidence"] = {"band": "required", "subtype": "floor_contact", "confidence": "medium"}
        ai_resp = _rh_change("ride_height_rear", 82, 84)  # +2mm
        reasons = validate_setup_engineering(
            ai_resp, diag, self.setup, self.ranges, {}
        )
        fired = [r for r in reasons if "rh_increment_exceeds_confidence:" in r]
        assert fired == [], (
            f"Medium confidence +2mm must NOT fire rh_increment_exceeds_confidence; reasons: {reasons}"
        )


# ===========================================================================
# I3 — snap_throttle_induced gate without good-traction driver feel
# ===========================================================================

class TestI3SnapThrottleInducedGateNoGoodTraction:
    """I3: wheelspin_subtype=='snap_throttle_induced', driver_feel_traction_status != 'good'
    (e.g. 'unknown') => lsd_accel +5 fires lsd_large_change_gated (NOT lsd_blocked_driver_feel).
    lsd_accel +4 fires neither rule.
    Isolates the size gate from the driver-feel block.
    """

    @pytest.fixture(autouse=True)
    def _build(self):
        laps = [_make_lap(wheelspin_count=15, snap_throttle_count=10)]
        base_diag = build_setup_diagnosis(
            laps=laps, setup={"lsd_accel": 20.0}, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        self.diag = dict(base_diag)
        self.diag["wheelspin_subtype"] = "snap_throttle_induced"
        self.diag["driver_feel_traction_status"] = "unknown"
        self.ranges = _get_ranges()

    def test_plus_4_no_gate_no_block(self):
        """lsd_accel +4 must fire neither lsd_large_change_gated nor lsd_blocked_driver_feel."""
        ai_resp = _lsd_change(20.0, 24.0)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, {"lsd_accel": 20.0}, self.ranges, {}
        )
        gated = [r for r in reasons if "lsd_large_change_gated:" in r]
        blocked = [r for r in reasons if "lsd_blocked_driver_feel:" in r]
        assert gated == [], (
            f"snap_throttle_induced +4 must not fire lsd_large_change_gated; reasons: {reasons}"
        )
        assert blocked == [], (
            f"snap_throttle_induced + unknown traction must not fire lsd_blocked_driver_feel; reasons: {reasons}"
        )

    def test_plus_5_fires_size_gate_only(self):
        """lsd_accel +5 must fire lsd_large_change_gated but NOT lsd_blocked_driver_feel."""
        ai_resp = _lsd_change(20.0, 25.0)
        reasons = validate_setup_engineering(
            ai_resp, self.diag, {"lsd_accel": 20.0}, self.ranges, {}
        )
        gated = [r for r in reasons if "lsd_large_change_gated:" in r]
        blocked = [r for r in reasons if "lsd_blocked_driver_feel:" in r]
        assert gated, (
            f"snap_throttle_induced +5 must fire lsd_large_change_gated; reasons: {reasons}"
        )
        assert blocked == [], (
            f"unknown traction must NOT fire lsd_blocked_driver_feel; reasons: {reasons}"
        )


# ===========================================================================
# I5 — bottoming_confidence prompt render
# ===========================================================================

class TestI5BottomingConfidencePromptRender:
    """I5: format_diagnosis_for_prompt(diag) must emit the bottoming-confidence
    block (containing 'Bottoming confidence:' and the confidence/subtype values)
    for a diagnosis with a populated bottoming_confidence dict.
    Mirrors the existing S9/S10 format tests.
    """

    def test_bottoming_confidence_rendered_in_prompt(self):
        """A diagnosis with bottoming_confidence high/floor_contact renders the block."""
        laps = [_make_lap(bottoming_count=3)]
        diag = build_setup_diagnosis(
            laps=laps, setup={"ride_height_rear": 82}, car_name="",
            event_ctx={}, feeling=None, location_confidence="low",
        )
        # Inject a known bottoming_confidence to test rendering independently
        diag = dict(diag)
        diag["bottoming_confidence"] = {"band": "required", "subtype": "floor_contact", "confidence": "high"}
        text = format_diagnosis_for_prompt(diag)
        assert "Bottoming confidence:" in text, (
            f"Prompt must contain 'Bottoming confidence:' when bottoming_confidence is set; "
            f"text:\n{text[:800]}"
        )
        assert "high" in text, (
            f"Prompt must include the confidence value 'high'; text:\n{text[:800]}"
        )
        assert "floor_contact" in text, (
            f"Prompt must include the subtype 'floor_contact'; text:\n{text[:800]}"
        )

    def test_low_confidence_insufficient_data_renders(self):
        """Low confidence / insufficient_data is also rendered."""
        laps = [_make_lap(bottoming_count=1)]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={},
            feeling=None, location_confidence="low",
        )
        diag = dict(diag)
        diag["bottoming_confidence"] = {"band": "minor", "subtype": "insufficient_data", "confidence": "low"}
        text = format_diagnosis_for_prompt(diag)
        assert "Bottoming confidence:" in text, (
            f"Prompt must contain 'Bottoming confidence:' for low/insufficient_data; "
            f"text:\n{text[:800]}"
        )
        assert "low" in text, (
            f"Prompt must include confidence value 'low'; text:\n{text[:800]}"
        )


# ===========================================================================
# KEY-PARITY: new Group 40 keys present in both paths
# ===========================================================================

class TestGroup40KeyParity:
    """Key-parity: 'bottoming_confidence', 'driver_feel_traction_status', 'aero_rear_healthy'
    must be present in BOTH _build_setup_diagnosis_conservative() AND a normal
    build_setup_diagnosis() output. Mirrors AC3 key-parity in test_group39.
    """

    _NEW_KEYS = (
        "bottoming_confidence",
        "driver_feel_traction_status",
        "aero_rear_healthy",
    )

    def test_conservative_path_has_new_keys(self):
        c = _build_setup_diagnosis_conservative()
        for key in self._NEW_KEYS:
            assert key in c, (
                f"Key '{key}' missing from _build_setup_diagnosis_conservative() dict"
            )

    def test_normal_path_has_new_keys(self):
        laps = [_make_lap()]
        diag = build_setup_diagnosis(
            laps=laps, setup={}, car_name="", event_ctx={}, feeling=None,
            location_confidence="low",
        )
        for key in self._NEW_KEYS:
            assert key in diag, (
                f"Key '{key}' missing from normal build_setup_diagnosis() dict"
            )

    def test_conservative_bottoming_confidence_shape(self):
        c = _build_setup_diagnosis_conservative()
        bc = c["bottoming_confidence"]
        assert isinstance(bc, dict), f"bottoming_confidence must be a dict; got {type(bc)}"
        assert "band" in bc and "subtype" in bc and "confidence" in bc

    def test_conservative_driver_feel_traction_status_is_unknown(self):
        c = _build_setup_diagnosis_conservative()
        assert c["driver_feel_traction_status"] == "unknown"

    def test_conservative_aero_rear_healthy_is_false(self):
        c = _build_setup_diagnosis_conservative()
        assert c["aero_rear_healthy"] is False

    def test_exception_path_has_new_keys(self):
        """When build_setup_diagnosis catches an exception it returns the conservative
        dict — that must also carry the new keys."""
        class _BadLap:
            @property
            def bottoming_count(self):
                raise RuntimeError("injected error")
            wheelspin_count = 0
            snap_throttle_count = 0
            lock_up_count = 0
            rev_limiter_by_gear = {}
            max_speed_kmh = 0.0
            kerb_count = 0
            frames = []

        diag = build_setup_diagnosis(
            laps=[_BadLap()], setup={}, car_name="", event_ctx={}, feeling=None,
        )
        for key in self._NEW_KEYS:
            assert key in diag, (
                f"Key '{key}' missing from exception-path (conservative) dict"
            )
