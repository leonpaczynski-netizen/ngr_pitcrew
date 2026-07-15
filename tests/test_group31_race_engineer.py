"""
Group 31 — Race engineer prompt directives, validation, and classifier

Background
----------
AC1-AC14 tests for the race-engineer prompt overhaul in strategy/driving_advisor.py.
Covers: per-car range authority, Hz/camber units, ride-height escalation, stable-
braking preservation, issue classification, snap-throttle driver-input separation,
structured prior-outcomes, extended JSON schema, zone-context / no invented names,
bottoming classifier, race-objective framing, short-sample warning,
smallest-effective-change instruction, and the validation layer.

All tests are in-memory only: no Qt widgets, no real API calls, no file I/O.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import strategy.driving_advisor as da
import strategy.setup_ranges as sr

DA_SOURCE = (ROOT / "strategy" / "driving_advisor.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Shared _Lap stub (mirrors test_group28 pattern, extended with new fields)
# ---------------------------------------------------------------------------

class _Lap:
    """Minimal LapStats stub for prompt building tests."""
    lap_num = 1
    lap_time_ms = 90000
    lock_up_count = 0
    wheelspin_count = 2
    brake_consistency_m = 5.0      # good braking
    oversteer_count = 1
    oversteer_throttle_on_count = 1
    kerb_count = 0
    bottoming_count = 3
    snap_throttle_count = 1
    max_lat_g = 1.5
    max_speed_kmh = 200.0
    avg_throttle_pct = 55.0
    avg_brake_pct = 15.0
    # position lists
    lock_up_positions = []
    wheelspin_positions = [(100.0, 0.0, 200.0)]
    oversteer_positions = [(100.0, 0.0, 200.0)]
    snap_throttle_positions = [(100.0, 0.0, 200.0)]
    over_braking_positions = []
    bottoming_positions = [(50.0, 0.0, 150.0)]
    # extended fields
    rev_limiter_count = 0
    rev_limiter_by_gear = {}
    over_braking_count = 0
    abrupt_release_count = 0
    car_max_speed_theoretical_kmh = 0.0
    avg_tyre_radius = {}
    off_track_count = 0
    gearbox_analysis = {}
    tyre_temp_fl_avg = 0.0
    tyre_temp_fr_avg = 0.0
    tyre_temp_rl_avg = 0.0
    tyre_temp_rr_avg = 0.0


def _make_advisor(event_ctx=None, config_extra=None):
    """Construct a DrivingAdvisor stub with all collaborators no-oped."""
    adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
    adv._event_ctx = event_ctx or {}
    adv._config = {"strategy": {}}
    if config_extra:
        adv._config["strategy"].update(config_extra)
    adv._summarize_new_telemetry = lambda laps: ""
    adv._car_track_header = lambda *a, **k: ""
    adv._get_event_context_block = lambda: ""
    adv._get_driver_feedback_context = lambda: ""
    adv._get_previous_ai_context = lambda *a, **k: ""
    adv._get_track_intelligence_context = lambda: ""
    adv._get_enriched_issue_context = lambda laps: ""
    adv._get_live_segment_context = lambda live: ""
    adv._DATA_QUALITY_NOTE = ""
    return adv


def _combined_prompt(adv=None, laps=None, setup=None, car_name="", **kwargs):
    if adv is None:
        adv = _make_advisor()
    if laps is None:
        laps = [_Lap()]
    return adv._build_combined_prompt(
        laps, setup or {}, history_str="",
        car_name=car_name, car_specs={}, **kwargs
    )


def _setup_prompt(adv=None, laps=None, setup=None, car_name="", **kwargs):
    if adv is None:
        adv = _make_advisor()
    if laps is None:
        laps = [_Lap()]
    return adv._build_setup_prompt(
        laps, setup or {}, history_str="",
        car_name=car_name, car_specs={}, **kwargs
    )


# ---------------------------------------------------------------------------
# AC1 — Range authority text in both prompts
# ---------------------------------------------------------------------------

class TestAC1RangeAuthority:



    def test_normalise_clamps_out_of_range_to_car_max(self, monkeypatch):
        monkeypatch.setattr(sr, "_load_ranges_json", lambda: {
            "Test Car": {"arb_front": {"min": 1, "max": 5}}
        })
        changes = [{"setting": "ARB Front", "field": "arb_front", "from": "3", "to": 10}]
        result = da._normalise_changes(changes, {}, "Test Car")
        assert result[0]["to_clamped"] == 5


# ---------------------------------------------------------------------------
# AC2 — Hz and positive camber text in both prompts
# ---------------------------------------------------------------------------

class TestAC2Units:




    def test_normalise_negative_camber_clamped_to_zero(self):
        changes = [{"setting": "Front Camber", "field": "camber_front", "from": "1.0", "to": -2.5}]
        result = da._normalise_changes(changes, {}, "")
        assert result[0]["to_clamped"] == 0.0


# ---------------------------------------------------------------------------
# AC3 — No-op stripping and ride-height escalation
# ---------------------------------------------------------------------------

class TestAC3RideHeightEscalation:
    def test_normalise_strips_noop_when_from_equals_clamped(self):
        # from=70, to=70 with range (60, 200) — no-op should be stripped
        changes = [
            {"setting": "Ride Height Front", "field": "ride_height_front",
             "from": "70", "to": 70},
        ]
        result = da._normalise_changes(changes, {}, "")
        assert len(result) == 0, "No-op change must be stripped"

    def test_normalise_keeps_genuine_change(self):
        changes = [
            {"setting": "Ride Height Front", "field": "ride_height_front",
             "from": "70", "to": 80},
        ]
        result = da._normalise_changes(changes, {}, "")
        assert len(result) == 1

    def test_normalise_unparseable_from_keeps_change(self):
        changes = [
            {"setting": "Setting X", "field": "arb_front",
             "from": "n/a", "to": 3},
        ]
        result = da._normalise_changes(changes, {}, "")
        assert len(result) == 1, "Unparseable from must keep the change"





# ---------------------------------------------------------------------------
# AC4 — Stable braking preservation
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# AC5 — Issue classification strings
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# AC6 — Snap-throttle driver input separation
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# AC7 — Structured prior_outcomes block
# ---------------------------------------------------------------------------

class TestAC7PriorOutcomes:
    def _prior(self, applied=True, result="improved"):
        return {
            "setting": "Rear ARB",
            "from_value": "4",
            "to_value": "3",
            "applied": applied,
            "result": result,
        }

    def test_prior_outcomes_block_contains_setting(self):
        adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
        adv._db = None
        adv._car_id_ref = [0]
        adv._config = {"strategy": {"track": ""}}
        ctx = adv._get_previous_ai_context("Setup", prior_outcomes=[self._prior()])
        assert "Rear ARB" in ctx

    def test_prior_outcomes_block_has_do_not_repeat_instruction(self):
        adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
        adv._db = None
        adv._car_id_ref = [0]
        adv._config = {"strategy": {"track": ""}}
        ctx = adv._get_previous_ai_context("Setup", prior_outcomes=[self._prior()])
        assert "do NOT repeat" in ctx or "do not repeat" in ctx.lower()

    def test_prior_outcomes_applied_false_shown(self):
        adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
        adv._db = None
        adv._car_id_ref = [0]
        adv._config = {"strategy": {"track": ""}}
        ctx = adv._get_previous_ai_context("Setup", prior_outcomes=[self._prior(applied=False)])
        assert "not applied" in ctx

    def test_prior_outcomes_empty_list_returns_empty(self):
        adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
        adv._db = None
        adv._car_id_ref = [0]
        adv._config = {"strategy": {"track": ""}}
        ctx = adv._get_previous_ai_context("Setup", prior_outcomes=[])
        assert ctx == ""

    def test_prior_outcomes_none_uses_free_text_db_path(self):
        adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
        adv._db = None
        adv._car_id_ref = [0]
        adv._config = {"strategy": {"track": ""}}
        # When prior_outcomes=None and db=None, should return ""
        ctx = adv._get_previous_ai_context("Setup", prior_outcomes=None)
        assert ctx == ""



# ---------------------------------------------------------------------------
# AC8 — Extended JSON schema keys in both prompts
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# AC9 — Zone context: no invented names, caveat present
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# AC10 — Bottoming location classifier
# ---------------------------------------------------------------------------

class TestAC10BottomingClassifier:
    def test_classifier_returns_unknown_for_empty_positions(self):
        result = da._classify_bottoming_location([], "loc1", "lay1")
        assert result == "unknown"

    def test_classifier_returns_unknown_for_empty_loc_id(self):
        result = da._classify_bottoming_location([(1.0, 0.0, 1.0)], "", "lay1")
        assert result == "unknown"

    def test_classifier_returns_unknown_for_empty_lay_id(self):
        result = da._classify_bottoming_location([(1.0, 0.0, 1.0)], "loc1", "")
        assert result == "unknown"

    def test_classifier_returns_known_category_when_enrichment_stubbed(self, monkeypatch):
        """When enrich_telemetry_issues returns a braking-phase issue, classifier
        should map it to 'braking zone'."""
        from data.track_issue_enrichment import (
            TrackIssueEnrichmentResult,
            EnrichedTelemetryIssue,
            RawTelemetryIssue,
            TrackIssueType,
            TrackIssuePhase,
            TrackIssueEnrichmentConfidence,
        )
        import data.track_issue_enrichment as tie

        # Build a fake EnrichedTelemetryIssue with phase=BRAKING and seg_type=braking_zone
        raw = RawTelemetryIssue(
            issue_type=TrackIssueType.UNKNOWN,
            phase=TrackIssuePhase.BRAKING,
            lap_num=0,
            pos_x=1.0, pos_y=0.0, pos_z=1.0,
            evidence="test",
        )
        ei = EnrichedTelemetryIssue(
            raw=raw,
            matched_segment_type="braking_zone",
            confidence=TrackIssueEnrichmentConfidence.LOW,
        )
        fake_result = TrackIssueEnrichmentResult(
            track_location_id="loc1",
            layout_id="lay1",
            enriched_issues=[ei],
            model_source="seed_only",
        )
        monkeypatch.setattr(tie, "enrich_telemetry_issues", lambda *a, **k: fake_result)

        result = da._classify_bottoming_location([(1.0, 0.0, 1.0)], "loc1", "lay1")
        assert result == "braking zone"

    def test_classifier_gracefully_handles_enrichment_exception(self, monkeypatch):
        import data.track_issue_enrichment as tie
        monkeypatch.setattr(tie, "enrich_telemetry_issues", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fail")))
        result = da._classify_bottoming_location([(1.0, 0.0, 1.0)], "loc1", "lay1")
        assert result == "unknown"



# ---------------------------------------------------------------------------
# AC11 — Race objective framing for lap and timed events
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# AC12 — Short-sample warning
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# AC13 — Smallest effective change instruction
# ---------------------------------------------------------------------------

class TestAC13SmallestChange:


    def test_validate_too_many_changes_produces_warning(self):
        """_validate_setup_response flags > 4 changes with a warning."""
        # Build 5 changes each targeting distinct valid fields
        fields = ["arb_front", "arb_rear", "springs_front", "springs_rear", "brake_bias"]
        changes = [
            {"setting": f"S{i}", "field": f, "from": "3", "to": 4, "to_clamped": 4}
            for i, f in enumerate(fields)
        ]
        sf = {f: 4 for f in fields}
        parsed = {"analysis": "test", "changes": changes, "setup_fields": sf}
        result = da._validate_setup_response(parsed, "", None, None, {})
        errs = result["validation_errors"]
        assert any("too many" in e.lower() for e in errs), \
            f"Expected >4 warning in validation_errors; got: {errs}"


# ---------------------------------------------------------------------------
# AC14 — Validation error modes
# ---------------------------------------------------------------------------

class TestAC14ValidationErrors:
    def _run(self, changes, sf=None, allowed_tuning=None, locked_fields=None, setup=None):
        sf = sf or {}
        parsed = {"analysis": "t", "changes": changes, "setup_fields": sf}
        return da._validate_setup_response(
            parsed, "", allowed_tuning, locked_fields, setup or {}
        )

    def test_unresolvable_field_flagged(self):
        changes = [{"setting": "Unknown", "field": None, "from": "1", "to": 2, "to_clamped": 2}]
        result = self._run(changes)
        errs = result["validation_errors"]
        assert any("no recognisable" in e or "canonical" in e or "None" in e for e in errs), \
            f"Expected unresolvable-field error; got: {errs}"

    def test_locked_field_flagged(self):
        changes = [{"setting": "ARB", "field": "arb_front", "from": "3", "to": 4, "to_clamped": 4}]
        result = self._run(changes, sf={"arb_front": 4}, locked_fields={"arb_front"})
        errs = result["validation_errors"]
        assert any("locked" in e.lower() for e in errs), \
            f"Expected locked-field error; got: {errs}"

    def test_noop_remaining_flagged(self):
        # A no-op that slipped through normalisation (shouldn't happen normally,
        # but validate still checks)
        changes = [{"setting": "ARB", "field": "arb_front", "from": "4", "to": 4, "to_clamped": 4}]
        result = self._run(changes, sf={"arb_front": 4})
        errs = result["validation_errors"]
        assert any("no-op" in e.lower() for e in errs), \
            f"Expected no-op error; got: {errs}"

    def test_string_to_clamped_flagged(self):
        changes = [{"setting": "ARB", "field": "arb_front", "from": "3", "to": "bad", "to_clamped": "bad"}]
        result = self._run(changes)
        errs = result["validation_errors"]
        assert any("string" in e.lower() for e in errs), \
            f"Expected string-not-number error; got: {errs}"

    def test_setup_fields_changes_mismatch_flagged(self):
        # changes has arb_front; setup_fields has arb_rear — mismatch
        changes = [{"setting": "ARB F", "field": "arb_front", "from": "3", "to": 4, "to_clamped": 4}]
        sf = {"arb_rear": 3}  # wrong field
        result = self._run(changes, sf=sf)
        errs = result["validation_errors"]
        assert any("missing from setup_fields" in e or "setup_fields key" in e for e in errs), \
            f"Expected setup_fields/changes mismatch error; got: {errs}"

    def test_valid_change_produces_no_errors(self):
        changes = [{"setting": "ARB F", "field": "arb_front", "from": "3", "to": 4, "to_clamped": 4}]
        sf = {"arb_front": 4}
        result = self._run(changes, sf=sf)
        errs = result["validation_errors"]
        assert errs == [], f"Expected no errors for valid change; got: {errs}"

    def test_out_of_range_to_clamped_flagged(self):
        # to_clamped=999 for arb_front whose generic range is (1,7)
        changes = [{"setting": "ARB F", "field": "arb_front", "from": "3", "to": 999, "to_clamped": 999}]
        sf = {"arb_front": 999}
        result = self._run(changes, sf=sf)
        errs = result["validation_errors"]
        assert any("outside valid range" in e for e in errs), \
            f"Expected out-of-range error; got: {errs}"

    def test_changes_not_dropped_even_when_invalid(self):
        """Validate must surface errors, not silently drop bad changes."""
        changes = [{"setting": "ARB", "field": None, "from": "1", "to": 2, "to_clamped": 2}]
        result = self._run(changes)
        # changes must still be present
        assert len(result["changes"]) == 1
        assert len(result["validation_errors"]) > 0


# ---------------------------------------------------------------------------
# New module-level functions exist in source
# ---------------------------------------------------------------------------

class TestModuleLevelFunctionsExist:
    def test_validate_setup_response_defined(self):
        assert "def _validate_setup_response(" in DA_SOURCE

    def test_classify_bottoming_location_defined(self):
        assert "def _classify_bottoming_location(" in DA_SOURCE

    def test_race_engineer_directives_defined(self):
        assert "def _race_engineer_directives(" in DA_SOURCE

    def test_derive_locked_fields_defined(self):
        assert "def _derive_locked_fields(" in DA_SOURCE

    def test_build_combined_prompt_accepts_prior_outcomes(self):
        # verify parameter in source
        assert "prior_outcomes" in DA_SOURCE



# ---------------------------------------------------------------------------
# Regression: test_group28 _normalise_changes existing tests still pass
# ---------------------------------------------------------------------------

class TestNormaliseChangesRegression:
    def test_out_of_range_still_clamped(self):
        changes = [{"setting": "ARB F", "field": "arb_front", "from": "4", "to": 15}]
        result = da._normalise_changes(changes, {}, "")
        assert len(result) == 1
        assert result[0]["to_clamped"] == 7

    def test_setup_fields_value_preferred(self):
        sf = {"arb_front": 5}
        changes = [{"setting": "ARB F", "field": "arb_front", "from": "4", "to": 99}]
        result = da._normalise_changes(changes, sf, "")
        assert result[0]["to_clamped"] == 5

    def test_camber_negative_clamped_to_zero(self):
        changes = [{"setting": "Camber F", "field": "camber_front", "from": "1.0", "to": -3.0}]
        result = da._normalise_changes(changes, {}, "")
        assert result[0]["to_clamped"] == 0.0


# ===========================================================================
# AUDIT AUGMENTATIONS — added to strengthen weak/superficial assertions and
# add missing coverage identified during the acceptance-criteria audit.
# ===========================================================================

# ---------------------------------------------------------------------------
# AC1 — Range authority: assert _normalise_changes actually clamps to per-car
#         bounds (not just generic defaults).  The existing test uses a stub but
#         doesn't test the REVERSE direction (to < per-car min).
# ---------------------------------------------------------------------------

class TestAC1RangeAuthorityAugmented:
    def test_normalise_clamps_to_per_car_min(self, monkeypatch):
        """to below per-car min is clamped up to that min, not generic default."""
        monkeypatch.setattr(sr, "_load_ranges_json", lambda: {
            "Test Car": {"arb_front": {"min": 3, "max": 7}}
        })
        changes = [{"setting": "ARB Front", "field": "arb_front", "from": "5", "to": 1}]
        result = da._normalise_changes(changes, {}, "Test Car")
        # per-car min is 3; generic default min is also 1 but per-car overrides
        assert result[0]["to_clamped"] == 3, (
            "normalise must clamp to per-car min (3), not generic min (1)"
        )

    def test_normalise_clamps_per_car_overrides_generic_max(self, monkeypatch):
        """Per-car max of 5 should override generic max of 7 for arb_front."""
        monkeypatch.setattr(sr, "_load_ranges_json", lambda: {
            "Tight Car": {"arb_front": {"min": 1, "max": 5}}
        })
        changes = [{"setting": "ARB Front", "field": "arb_front", "from": "3", "to": 6}]
        result = da._normalise_changes(changes, {}, "Tight Car")
        assert result[0]["to_clamped"] == 5, (
            "normalise must use per-car max (5), not generic max (7)"
        )

    def test_valid_ranges_block_respects_per_car_ride_height_max(self, monkeypatch):
        """_valid_ranges_block must show per-car ride_height max, not generic 200."""
        monkeypatch.setattr(sr, "_load_ranges_json", lambda: {
            "Low Car": {"ride_height_front": {"min": 60, "max": 90}}
        })
        block = da._valid_ranges_block("Low Car")
        line = next(l for l in block.splitlines() if "ride_height_front:" in l)
        assert "90" in line, "per-car ride_height_front max (90) must appear in ranges block"
        assert "200" not in line, "generic max (200) must not appear when per-car max is 90"


# ---------------------------------------------------------------------------
# AC2 — Units: stronger assertion on camber positive-value wording in both prompts.
# ---------------------------------------------------------------------------

class TestAC2UnitsAugmented:


    def test_directive_never_output_negative_camber(self):
        """The directive text itself must prohibit negative camber values."""
        result = da._race_engineer_directives(
            avg_lockups=0.0, avg_consist=5.0, avg_snap=0.0, avg_os_ton=0.0,
            avg_bottom=0.0, car_name="", laps_sample_len=5,
            event_ctx={}, wheelspin_positions=[], snap_throttle_positions=[],
            oversteer_positions=[], bottoming_positions=[], loc_id="", lay_id="",
        )
        assert "NEVER output a negative camber value" in result or \
               "never output a negative camber" in result.lower(), \
               "directive must explicitly forbid negative camber"


# ---------------------------------------------------------------------------
# AC3 — Ride-height escalation: SCRUTINISED.
#
# (a) 'escalate' / 'platform-control' is UNCONDITIONAL boilerplate (always present).
# (b) 'already at limit' is CONDITIONAL — only injected when avg_bottom > 0.
# (c) No-op stripping: when AI suggests a value > per-car max, clamping produces
#     the max, and if from == max, the change is stripped as a no-op.
#
# The existing tests only check the unconditional 'escalate' word and a plain
# from==to no-op case.  These tests add the missing conditional checks.
# ---------------------------------------------------------------------------

class TestAC3RideHeightEscalationAugmented:
    def _lap_no_bottoming(self):
        lap = _Lap()
        lap.bottoming_count = 0
        lap.bottoming_positions = []
        return lap

    def _lap_high_bottoming(self):
        lap = _Lap()
        lap.bottoming_count = 5
        lap.bottoming_positions = [(50.0, 0.0, 150.0)]
        return lap

    # ---- (a) unconditional boilerplate present in BOTH prompts ----



    # ---- (b) conditional 'already at limit' only fires when bottoming present ----






    # ---- (c) no-op stripping when AI suggests > per-car max ----

    def test_normalise_strips_noop_when_ai_suggests_above_per_car_max(self, monkeypatch):
        """When AI suggests ride_height_front=95 but per-car max is 90, clamping
        produces 90; if current value (from) is already 90, the change is a no-op
        and must be stripped entirely.  This is the key AC3 failure scenario."""
        monkeypatch.setattr(sr, "_load_ranges_json", lambda: {
            "Porsche 963 '24": {"ride_height_front": {"min": 80, "max": 90}}
        })
        changes = [
            {
                "setting": "Ride Height Front",
                "field": "ride_height_front",
                "from": "90",   # already at the per-car maximum
                "to": 95,       # AI suggests going higher (impossible)
            }
        ]
        result = da._normalise_changes(changes, {}, "Porsche 963 '24")
        assert len(result) == 0, (
            "A ride-height change from=90 to=95 with per-car max=90 must be stripped "
            "as a no-op after clamping (95 → 90 == from 90)"
        )

    def test_normalise_keeps_change_when_not_at_max(self, monkeypatch):
        """A ride-height change from=80 to=95 with max=90 is clamped to 90 but not
        a no-op (80 != 90), so it must be kept."""
        monkeypatch.setattr(sr, "_load_ranges_json", lambda: {
            "Porsche 963 '24": {"ride_height_front": {"min": 80, "max": 90}}
        })
        changes = [
            {
                "setting": "Ride Height Front",
                "field": "ride_height_front",
                "from": "80",
                "to": 95,
            }
        ]
        result = da._normalise_changes(changes, {}, "Porsche 963 '24")
        assert len(result) == 1, "Non-no-op change (80 to clamped 90) must be kept"
        assert result[0]["to_clamped"] == 90


# ---------------------------------------------------------------------------
# AC4 — Stable braking: assert the SPECIFIC directive text, not just 'stable'
#         (which could appear in any part of the prompt).
# ---------------------------------------------------------------------------

class TestAC4StableBrakingAugmented:
    def _lap_stable(self):
        lap = _Lap()
        lap.lock_up_count = 0
        lap.brake_consistency_m = 5.0
        return lap

    def _lap_unstable(self):
        lap = _Lap()
        lap.lock_up_count = 4
        lap.brake_consistency_m = 35.0
        return lap





    def test_directive_fires_at_consistency_boundary(self):
        """avg_consist=14.9 should trigger AC4; 15.0 should not."""
        # consist=14.9 -> fires
        result_ok = da._race_engineer_directives(
            avg_lockups=0.0, avg_consist=14.9, avg_snap=0.0, avg_os_ton=0.0,
            avg_bottom=0.0, car_name="", laps_sample_len=5,
            event_ctx={}, wheelspin_positions=[], snap_throttle_positions=[],
            oversteer_positions=[], bottoming_positions=[], loc_id="", lay_id="",
        )
        assert "do NOT change brake_bias" in result_ok

        # consist=15.0 -> should NOT fire (>= 15 is 'needs work')
        result_nok = da._race_engineer_directives(
            avg_lockups=0.0, avg_consist=15.0, avg_snap=0.0, avg_os_ton=0.0,
            avg_bottom=0.0, car_name="", laps_sample_len=5,
            event_ctx={}, wheelspin_positions=[], snap_throttle_positions=[],
            oversteer_positions=[], bottoming_positions=[], loc_id="", lay_id="",
        )
        assert "do NOT change brake_bias" not in result_nok


# ---------------------------------------------------------------------------
# AC6 — Snap-throttle: stronger assertion using the exact directive label.
# ---------------------------------------------------------------------------

class TestAC6SnapThrottleAugmented:
    def test_ac6_directive_label_present_when_snap_and_os_ton_nonzero(self):
        """The directive text 'AC6 SNAP-THROTTLE DRIVER INPUT' must appear when
        both avg_snap > 0 and avg_os_ton > 0."""
        result = da._race_engineer_directives(
            avg_lockups=0.0, avg_consist=5.0, avg_snap=2.0, avg_os_ton=1.0,
            avg_bottom=0.0, car_name="", laps_sample_len=5,
            event_ctx={}, wheelspin_positions=[], snap_throttle_positions=[],
            oversteer_positions=[], bottoming_positions=[], loc_id="", lay_id="",
        )
        assert "AC6 SNAP-THROTTLE DRIVER INPUT" in result

    def test_ac6_directive_label_absent_when_snap_zero(self):
        """AC6 must NOT fire when snap_throttle_count == 0."""
        result = da._race_engineer_directives(
            avg_lockups=0.0, avg_consist=5.0, avg_snap=0.0, avg_os_ton=1.0,
            avg_bottom=0.0, car_name="", laps_sample_len=5,
            event_ctx={}, wheelspin_positions=[], snap_throttle_positions=[],
            oversteer_positions=[], bottoming_positions=[], loc_id="", lay_id="",
        )
        assert "AC6 SNAP-THROTTLE DRIVER INPUT" not in result

    def test_ac6_directive_label_absent_when_os_ton_zero(self):
        """AC6 must NOT fire when oversteer_throttle_on_count == 0 (snap alone
        is not sufficient — both conditions must be non-zero)."""
        result = da._race_engineer_directives(
            avg_lockups=0.0, avg_consist=5.0, avg_snap=3.0, avg_os_ton=0.0,
            avg_bottom=0.0, car_name="", laps_sample_len=5,
            event_ctx={}, wheelspin_positions=[], snap_throttle_positions=[],
            oversteer_positions=[], bottoming_positions=[], loc_id="", lay_id="",
        )
        assert "AC6 SNAP-THROTTLE DRIVER INPUT" not in result


# ---------------------------------------------------------------------------
# AC10 — Bottoming classifier: verify ALL 6 categories are reachable.
#
# The existing test only covers 'braking zone' via seg_type=braking_zone.
# These tests cover all 6 seg_type paths and the phase fallback path.
# ---------------------------------------------------------------------------

class TestAC10BottomingClassifierAllCategories:
    """Verify every category is reachable with appropriate enrichment stub.

    NOTE: 'kerb strike' can ONLY be reached via seg_type='kerb_zone' —
    there is no phase value that maps to it.  If this test fails, the
    mapping table has regressed.
    """

    def _make_fake_result(self, seg_type, phase=None, monkeypatch=None):
        """Build a fake EnrichedTelemetryIssue with given seg_type / phase."""
        from data.track_issue_enrichment import (
            TrackIssueEnrichmentResult, EnrichedTelemetryIssue,
            RawTelemetryIssue, TrackIssueType, TrackIssuePhase,
            TrackIssueEnrichmentConfidence,
        )
        import data.track_issue_enrichment as tie
        raw = RawTelemetryIssue(
            issue_type=TrackIssueType.UNKNOWN,
            phase=phase or TrackIssuePhase.UNKNOWN,
            lap_num=0, pos_x=1.0, pos_y=0.0, pos_z=1.0, evidence="test",
        )
        ei = EnrichedTelemetryIssue(
            raw=raw,
            matched_segment_type=seg_type,
            confidence=TrackIssueEnrichmentConfidence.LOW,
        )
        return TrackIssueEnrichmentResult(
            track_location_id="loc1", layout_id="lay1",
            enriched_issues=[ei], model_source="seed_only",
        )

    def _run(self, seg_type, monkeypatch):
        import data.track_issue_enrichment as tie
        fake = self._make_fake_result(seg_type)
        monkeypatch.setattr(tie, "enrich_telemetry_issues", lambda *a, **k: fake)
        return da._classify_bottoming_location([(1.0, 0.0, 1.0)], "loc1", "lay1")

    def test_seg_braking_zone_produces_braking_zone(self, monkeypatch):
        assert self._run("braking_zone", monkeypatch) == "braking zone"

    def test_seg_corner_entry_produces_braking_zone(self, monkeypatch):
        assert self._run("corner_entry", monkeypatch) == "braking zone"

    def test_seg_corner_exit_produces_throttle_exit_squat(self, monkeypatch):
        assert self._run("corner_exit", monkeypatch) == "throttle-exit squat"

    def test_seg_traction_zone_produces_throttle_exit_squat(self, monkeypatch):
        assert self._run("traction_zone", monkeypatch) == "throttle-exit squat"

    def test_seg_kerb_zone_produces_kerb_strike(self, monkeypatch):
        """'kerb strike' is ONLY reachable via seg_type='kerb_zone'."""
        assert self._run("kerb_zone", monkeypatch) == "kerb strike"

    def test_seg_banking_zone_produces_banking_compression(self, monkeypatch):
        assert self._run("banking_zone", monkeypatch) == "banking compression"

    def test_seg_straight_produces_infield_bump(self, monkeypatch):
        assert self._run("straight", monkeypatch) == "infield bump"

    def test_unknown_seg_type_falls_back_to_phase_braking(self, monkeypatch):
        """When seg_type is not in the map, the phase fallback is used."""
        from data.track_issue_enrichment import (
            TrackIssueEnrichmentResult, EnrichedTelemetryIssue,
            RawTelemetryIssue, TrackIssueType, TrackIssuePhase,
            TrackIssueEnrichmentConfidence,
        )
        import data.track_issue_enrichment as tie
        raw = RawTelemetryIssue(
            issue_type=TrackIssueType.UNKNOWN, phase=TrackIssuePhase.BRAKING,
            lap_num=0, pos_x=1.0, pos_y=0.0, pos_z=1.0, evidence="test",
        )
        ei = EnrichedTelemetryIssue(
            raw=raw, matched_segment_type="UNMAPPED_TYPE",
            confidence=TrackIssueEnrichmentConfidence.LOW,
        )
        fake = TrackIssueEnrichmentResult(
            track_location_id="loc1", layout_id="lay1",
            enriched_issues=[ei], model_source="seed_only",
        )
        monkeypatch.setattr(tie, "enrich_telemetry_issues", lambda *a, **k: fake)
        result = da._classify_bottoming_location([(1.0, 0.0, 1.0)], "loc1", "lay1")
        assert result == "braking zone", \
            "Phase fallback for BRAKING phase must return 'braking zone'"

    def test_unknown_seg_type_falls_back_to_phase_traction(self, monkeypatch):
        from data.track_issue_enrichment import (
            TrackIssueEnrichmentResult, EnrichedTelemetryIssue,
            RawTelemetryIssue, TrackIssueType, TrackIssuePhase,
            TrackIssueEnrichmentConfidence,
        )
        import data.track_issue_enrichment as tie
        raw = RawTelemetryIssue(
            issue_type=TrackIssueType.UNKNOWN, phase=TrackIssuePhase.TRACTION,
            lap_num=0, pos_x=1.0, pos_y=0.0, pos_z=1.0, evidence="test",
        )
        ei = EnrichedTelemetryIssue(
            raw=raw, matched_segment_type="UNMAPPED_TYPE",
            confidence=TrackIssueEnrichmentConfidence.LOW,
        )
        fake = TrackIssueEnrichmentResult(
            track_location_id="loc1", layout_id="lay1",
            enriched_issues=[ei], model_source="seed_only",
        )
        monkeypatch.setattr(tie, "enrich_telemetry_issues", lambda *a, **k: fake)
        result = da._classify_bottoming_location([(1.0, 0.0, 1.0)], "loc1", "lay1")
        assert result == "throttle-exit squat"

    def test_no_votes_after_enrichment_returns_unknown(self, monkeypatch):
        """If enrichment succeeds but no seg_type or phase maps to a category,
        result must be 'unknown' — not raise."""
        from data.track_issue_enrichment import (
            TrackIssueEnrichmentResult, EnrichedTelemetryIssue,
            RawTelemetryIssue, TrackIssueType, TrackIssuePhase,
            TrackIssueEnrichmentConfidence,
        )
        import data.track_issue_enrichment as tie
        raw = RawTelemetryIssue(
            issue_type=TrackIssueType.UNKNOWN, phase=TrackIssuePhase.UNKNOWN,
            lap_num=0, pos_x=1.0, pos_y=0.0, pos_z=1.0, evidence="test",
        )
        ei = EnrichedTelemetryIssue(
            raw=raw, matched_segment_type="TOTALLY_UNKNOWN",
            confidence=TrackIssueEnrichmentConfidence.LOW,
        )
        fake = TrackIssueEnrichmentResult(
            track_location_id="loc1", layout_id="lay1",
            enriched_issues=[ei], model_source="seed_only",
        )
        monkeypatch.setattr(tie, "enrich_telemetry_issues", lambda *a, **k: fake)
        result = da._classify_bottoming_location([(1.0, 0.0, 1.0)], "loc1", "lay1")
        assert result == "unknown"


# ---------------------------------------------------------------------------
# AC14 — Validation: per-failure-mode surfacing (each as its own test).
#         Augments existing tests with stronger assertions that errors are in
#         validation_errors AND the change survives (not silently dropped).
# ---------------------------------------------------------------------------

class TestAC14ValidationPerFailureModeAugmented:
    """Each AC14 failure mode has its own test asserting BOTH:
      1. The error appears in validation_errors.
      2. The change is NOT silently dropped (changes list unchanged).
    """

    def _run(self, changes, sf=None, locked_fields=None, car_name=""):
        sf = sf or {}
        parsed = {"analysis": "t", "changes": list(changes), "setup_fields": sf}
        return da._validate_setup_response(parsed, car_name, None, locked_fields, {})

    def test_a_out_of_car_range_error_surfaced_and_change_kept(self, monkeypatch):
        """(a) A to_clamped value outside the per-car range must be an error
        AND the change must remain in the changes list."""
        monkeypatch.setattr(sr, "_load_ranges_json", lambda: {
            "Test Car": {"arb_front": {"min": 1, "max": 5}}
        })
        changes = [{"setting": "ARB F", "field": "arb_front",
                    "from": "3", "to": 8, "to_clamped": 8}]
        result = self._run(changes, sf={"arb_front": 8}, car_name="Test Car")
        assert any("outside valid range" in e for e in result["validation_errors"]), \
            "out-of-car-range must produce an 'outside valid range' error"
        assert len(result["changes"]) == 1, "change must NOT be silently dropped"

    def test_b_locked_field_error_surfaced_and_change_kept(self):
        """(b) A change targeting a locked field must appear in validation_errors
        AND the change must remain in the changes list."""
        changes = [{"setting": "Power", "field": "power_restrictor",
                    "from": "100", "to": 95, "to_clamped": 95}]
        locked = {"power_restrictor"}
        result = self._run(changes, sf={"power_restrictor": 95}, locked_fields=locked)
        assert any("locked" in e.lower() for e in result["validation_errors"]), \
            "locked-field change must produce a 'locked' error"
        assert len(result["changes"]) == 1, "change must NOT be silently dropped"

    def test_c_noop_change_error_surfaced_and_change_kept(self):
        """(c) A no-op change (from == to_clamped) must appear in validation_errors
        AND the change must remain in changes (validate never drops)."""
        changes = [{"setting": "ARB", "field": "arb_front",
                    "from": "4", "to": 4, "to_clamped": 4}]
        result = self._run(changes, sf={"arb_front": 4})
        assert any("no-op" in e.lower() for e in result["validation_errors"]), \
            "no-op change must produce a no-op error"
        assert len(result["changes"]) == 1, "change must NOT be silently dropped"

    def test_d_string_to_clamped_error_surfaced_and_change_kept(self):
        """(d) A string to_clamped must produce a string-type error AND the
        change must remain in changes."""
        changes = [{"setting": "ARB", "field": "arb_front",
                    "from": "3", "to": "soft", "to_clamped": "soft"}]
        result = self._run(changes)
        assert any("string" in e.lower() for e in result["validation_errors"]), \
            "string to_clamped must produce a string error"
        assert len(result["changes"]) == 1, "change must NOT be silently dropped"

    def test_e_setup_fields_changes_mismatch_surfaced_and_change_kept(self):
        """(e) Key in changes not in setup_fields must produce a mismatch error
        AND the change must remain."""
        changes = [{"setting": "ARB F", "field": "arb_front",
                    "from": "3", "to": 4, "to_clamped": 4}]
        sf = {"arb_rear": 3}  # different key
        result = self._run(changes, sf=sf)
        errs = result["validation_errors"]
        assert any("missing from setup_fields" in e or "setup_fields key" in e
                   for e in errs), \
            f"Expected setup_fields/changes mismatch error; got: {errs}"
        assert len(result["changes"]) == 1, "change must NOT be silently dropped"

    def test_f_too_many_changes_warning_surfaced(self):
        """(f) >4 changes must produce a 'too many' warning in validation_errors."""
        fields = ["arb_front", "arb_rear", "springs_front", "springs_rear", "brake_bias"]
        changes = [
            {"setting": f"S{i}", "field": f, "from": "3", "to": 4, "to_clamped": 4}
            for i, f in enumerate(fields)
        ]
        sf = {f: 4 for f in fields}
        parsed = {"analysis": "t", "changes": changes, "setup_fields": sf}
        result = da._validate_setup_response(parsed, "", None, None, {})
        errs = result["validation_errors"]
        assert any("too many" in e.lower() for e in errs), \
            f">4 changes must produce 'too many' error; got: {errs}"

    def test_unresolvable_field_error_surfaced_and_change_kept(self):
        """Unresolvable field (field=None) must produce an error AND not be dropped."""
        changes = [{"setting": "Weird Setting", "field": None,
                    "from": "1", "to": 2, "to_clamped": 2}]
        parsed = {"analysis": "t", "changes": changes, "setup_fields": {}}
        result = da._validate_setup_response(parsed, "", None, None, {})
        assert len(result["validation_errors"]) > 0
        assert len(result["changes"]) == 1, \
            "_validate_setup_response must never silently drop changes"


# ---------------------------------------------------------------------------
# AC14 — _derive_locked_fields: verify correct field sets for Porsche 963 case.
# ---------------------------------------------------------------------------

class TestAC14DeriveLockedFieldsPorsche963:
    """Verify _derive_locked_fields with the Porsche 963 Daytona allowed_tuning
    list: brake_balance / suspension / differential / aero allowed;
    transmission, power, ballast, steering locked."""

    _ALLOWED = ["brake_balance", "suspension", "differential", "aero"]

    def test_power_restrictor_is_locked(self):
        locked = da._derive_locked_fields(self._ALLOWED)
        assert "power_restrictor" in locked, \
            "power category locked → power_restrictor must be in locked set"

    def test_transmission_is_locked(self):
        locked = da._derive_locked_fields(self._ALLOWED)
        assert "transmission_max_speed_kmh" in locked, \
            "transmission category locked → transmission_max_speed_kmh must be locked"

    def test_ballast_is_locked(self):
        locked = da._derive_locked_fields(self._ALLOWED)
        assert "ballast_kg" in locked and "ballast_position" in locked, \
            "ballast category locked → ballast_kg and ballast_position must be locked"

    def test_brake_bias_is_not_locked(self):
        locked = da._derive_locked_fields(self._ALLOWED)
        assert "brake_bias" not in locked, \
            "brake_balance is allowed → brake_bias must NOT be locked"

    def test_arb_front_is_not_locked(self):
        locked = da._derive_locked_fields(self._ALLOWED)
        assert "arb_front" not in locked, \
            "suspension is allowed → arb_front must NOT be locked"

    def test_aero_rear_is_not_locked(self):
        locked = da._derive_locked_fields(self._ALLOWED)
        assert "aero_rear" not in locked, \
            "aero is allowed → aero_rear must NOT be locked"

    def test_lsd_accel_is_not_locked(self):
        locked = da._derive_locked_fields(self._ALLOWED)
        assert "lsd_accel" not in locked, \
            "differential is allowed → lsd_accel must NOT be locked"

    def test_none_allowed_tuning_returns_empty_set(self):
        locked = da._derive_locked_fields(None)
        assert locked == set(), \
            "None allowed_tuning → no locked fields (no restrictions)"

    def test_empty_allowed_tuning_returns_empty_set(self):
        locked = da._derive_locked_fields([])
        assert locked == set(), \
            "Empty allowed_tuning → no locked fields ([] means no restrictions)"


# ---------------------------------------------------------------------------
# Reference failure case — Porsche 963 '24 at Daytona Road Course
#
# End-to-end-style test: builds a prompt for the reference scenario and
# validates the exact behaviours called out in the acceptance criteria.
# No API calls.
# ---------------------------------------------------------------------------

class _LapPorsche963:
    """LapStats stub representing the Porsche 963 reference scenario:
    high bottoming, high wheelspin, high snap-throttle, stable braking,
    good entry/mid, rear loose on throttle (RACE setup).
    """
    lap_num = 1
    lap_time_ms = 120_000
    lock_up_count = 0             # stable braking
    wheelspin_count = 8           # high wheelspin
    brake_consistency_m = 6.0    # good (< 15 m)
    oversteer_count = 4
    oversteer_throttle_on_count = 4  # rear loose on throttle
    kerb_count = 1
    bottoming_count = 7           # high bottoming
    snap_throttle_count = 5       # high snap throttle
    max_lat_g = 1.8
    max_speed_kmh = 270.0
    avg_throttle_pct = 58.0
    avg_brake_pct = 14.0
    lock_up_positions = []
    wheelspin_positions = [(200.0, 0.0, 300.0), (210.0, 0.0, 310.0)]
    oversteer_positions = [(200.0, 0.0, 300.0)]
    snap_throttle_positions = [(200.0, 0.0, 300.0)]
    over_braking_positions = []
    bottoming_positions = [(500.0, 0.0, 400.0), (505.0, 0.0, 405.0)]
    rev_limiter_count = 0
    rev_limiter_by_gear = {}
    over_braking_count = 0
    abrupt_release_count = 0
    car_max_speed_theoretical_kmh = 0.0
    avg_tyre_radius = {}
    off_track_count = 0
    gearbox_analysis = {}
    tyre_temp_fl_avg = 0.0
    tyre_temp_fr_avg = 0.0
    tyre_temp_rl_avg = 0.0
    tyre_temp_rr_avg = 0.0


_PORSCHE_963_ALLOWED = ["brake_balance", "suspension", "differential", "aero"]
_PORSCHE_963_CAR = "Porsche 963 '24"

# Per-car ranges: ride_height at max = 90 mm (front and rear)
_PORSCHE_963_RANGES = {
    _PORSCHE_963_CAR: {
        "ride_height_front": {"min": 80, "max": 90},
        "ride_height_rear":  {"min": 80, "max": 90},
        "arb_front":   {"min": 1, "max": 9},
        "arb_rear":    {"min": 1, "max": 9},
        "springs_front": {"min": 2.0, "max": 10.0},
        "springs_rear":  {"min": 2.0, "max": 10.0},
        "aero_front":  {"min": 700, "max": 1000},
        "aero_rear":   {"min": 700, "max": 1000},
        "brake_bias":  {"min": -5, "max": 5},
        "lsd_initial": {"min": 5, "max": 50},
        "lsd_accel":   {"min": 5, "max": 50},
        "lsd_decel":   {"min": 5, "max": 50},
    }
}


class TestPorsche963ReferenceFailureCase:
    """End-to-end prompt + validation tests for the Porsche 963 reference case."""

    def _make_adv(self):
        adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
        adv._event_ctx = {"race_type": "lap", "laps": 25}
        adv._config = {"strategy": {}}
        adv._summarize_new_telemetry = lambda laps: ""
        adv._car_track_header = lambda *a, **k: "Car: Porsche 963 '24 | Gr.1 | AWD"
        adv._get_event_context_block = lambda: (
            "## Event Rules\nTrack: Daytona Road Course\nRace: 25 laps, Lap Race"
        )
        adv._get_driver_feedback_context = lambda: ""
        adv._get_previous_ai_context = lambda *a, **k: ""
        adv._get_track_intelligence_context = lambda: ""
        adv._get_enriched_issue_context = lambda laps: ""
        adv._get_live_segment_context = lambda live: ""
        adv._DATA_QUALITY_NOTE = ""
        return adv







    def test_iii_validate_rejects_locked_power_restrictor(self, monkeypatch):
        """(iii) _validate_setup_response must flag power_restrictor as locked
        when allowed_tuning = brake_balance/suspension/differential/aero."""
        monkeypatch.setattr(sr, "_load_ranges_json", lambda: _PORSCHE_963_RANGES)
        locked = da._derive_locked_fields(_PORSCHE_963_ALLOWED)
        changes = [
            {"setting": "Power Restrictor", "field": "power_restrictor",
             "from": "100", "to": 95, "to_clamped": 95}
        ]
        parsed = {"analysis": "t", "changes": changes, "setup_fields": {"power_restrictor": 95}}
        result = da._validate_setup_response(
            parsed, _PORSCHE_963_CAR, _PORSCHE_963_ALLOWED, locked, {}
        )
        errs = result["validation_errors"]
        assert any("locked" in e.lower() for e in errs), \
            f"power_restrictor must be flagged as locked; got: {errs}"
        assert len(result["changes"]) == 1, "locked change must NOT be silently dropped"

    def test_iii_validate_rejects_noop_ride_height_when_at_max(self, monkeypatch):
        """(iii) When ride_height_front is already at per-car max (90 mm) and
        the AI suggests 95 (clamped to 90 == from), it is a no-op.
        _normalise_changes strips it; _validate_setup_response never sees it.
        This test verifies _normalise_changes does the stripping."""
        monkeypatch.setattr(sr, "_load_ranges_json", lambda: _PORSCHE_963_RANGES)
        changes = [
            {
                "setting": "Ride Height Front",
                "field": "ride_height_front",
                "from": "90",   # currently at max
                "to": 95,       # AI wants to go higher
            }
        ]
        result = da._normalise_changes(changes, {}, _PORSCHE_963_CAR)
        assert len(result) == 0, (
            "A ride_height_front change from=90 to=95 with per-car max=90 must "
            "be stripped by _normalise_changes as a no-op (clamped 95→90 == from 90)"
        )

    def test_iii_validate_flags_noop_if_it_survives_normalise(self, monkeypatch):
        """(iii) If somehow a no-op survives normalise, _validate_setup_response
        must catch it and add a no-op error."""
        monkeypatch.setattr(sr, "_load_ranges_json", lambda: _PORSCHE_963_RANGES)
        locked = da._derive_locked_fields(_PORSCHE_963_ALLOWED)
        # Simulate a no-op that somehow wasn't stripped
        changes = [
            {
                "setting": "Ride Height Front",
                "field": "ride_height_front",
                "from": "90",
                "to": 90,
                "to_clamped": 90,
            }
        ]
        parsed = {
            "analysis": "t",
            "changes": changes,
            "setup_fields": {"ride_height_front": 90},
        }
        result = da._validate_setup_response(
            parsed, _PORSCHE_963_CAR, _PORSCHE_963_ALLOWED, locked, {}
        )
        errs = result["validation_errors"]
        assert any("no-op" in e.lower() for e in errs), \
            f"no-op ride-height must be flagged by validation; got: {errs}"





# ===========================================================================
# DEFECT-FIX TARGETED TESTS (C1, C2, C3a, C3b, I1)
# Added to pin the exact defects fixed by the implementation-validator review.
# ===========================================================================

# ---------------------------------------------------------------------------
# C1 — build_combined_setup_response rebuilds setup_fields after no-op strip
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# C2 — max_tokens behavioural pin for both entry points
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# C3a — Locked fields stripped from changes + setup_fields after validation
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# C3b — _format_validation_errors_banner (pure helper, no Qt)
# ---------------------------------------------------------------------------

class TestC3bValidationErrorsBanner:
    """Tests for the pure _format_validation_errors_banner helper."""

    def test_empty_errors_returns_empty_string(self):
        from ui.setup_builder_ui import _format_validation_errors_banner
        result = _format_validation_errors_banner([])
        assert result == ""

    def test_single_error_appears_in_output(self):
        from ui.setup_builder_ui import _format_validation_errors_banner
        result = _format_validation_errors_banner(["change field 'aero_front' targets a locked field"])
        assert "aero_front" in result
        assert "locked" in result.lower()

    def test_multiple_errors_all_appear(self):
        from ui.setup_builder_ui import _format_validation_errors_banner
        errors = [
            "change field 'arb_front' is out of range",
            "too many changes (>4): 5 changes",
        ]
        result = _format_validation_errors_banner(errors)
        assert "arb_front" in result
        assert "too many" in result.lower()

    def test_banner_contains_warning_label(self):
        from ui.setup_builder_ui import _format_validation_errors_banner
        result = _format_validation_errors_banner(["some error"])
        assert "Validation" in result or "Warning" in result

    def test_banner_is_html(self):
        from ui.setup_builder_ui import _format_validation_errors_banner
        result = _format_validation_errors_banner(["some error"])
        assert "<div" in result and "</div>" in result


# ---------------------------------------------------------------------------
# I1 — AC3 ride-height-at-max: explicit targeted directive when setup is passed
# ---------------------------------------------------------------------------

class TestI1AC3RideHeightAtMax:
    """When ride height is at the per-car maximum AND bottoming is detected,
    _race_engineer_directives must name the field and say 'do NOT recommend
    raising it'. When below max, it must NOT restrict ride-height changes."""

    def _directives(self, setup, avg_bottom=2.0, car_name=""):
        return da._race_engineer_directives(
            avg_lockups=0.0,
            avg_consist=5.0,
            avg_snap=0.0,
            avg_os_ton=0.0,
            avg_bottom=avg_bottom,
            car_name=car_name,
            laps_sample_len=1,
            event_ctx={},
            wheelspin_positions=[],
            snap_throttle_positions=[],
            oversteer_positions=[],
            bottoming_positions=[],
            loc_id="",
            lay_id="",
            setup=setup,
        )

    def test_rh_front_at_max_names_field_and_forbids_raising(self):
        """ride_height_front == max (200 generic) + bottoming → explicit 'do NOT recommend'."""
        setup = {"ride_height_front": 200, "ride_height_rear": 100}
        d = self._directives(setup)
        low = d.lower()
        assert "ride_height_front" in low, "Field name must appear in directive"
        assert "do not" in low or "do NOT" in d, "Must say 'do NOT recommend'"
        assert "200" in d, "Must reference the current value or max"
        assert "already at" in low or "maximum" in low, \
            "Must indicate the field is at its limit"

    def test_rh_rear_at_max_names_rear_field(self):
        """ride_height_rear == max with bottoming → rear field named."""
        setup = {"ride_height_front": 80, "ride_height_rear": 200}
        d = self._directives(setup)
        assert "ride_height_rear" in d.lower()

    def test_rh_below_max_allows_recommendation(self):
        """When ride height is below max, the directive must NOT forbid raising it."""
        setup = {"ride_height_front": 80, "ride_height_rear": 90}  # well below 200 generic max
        d = self._directives(setup)
        # The "below max" branch should say ride height IS permissible
        low = d.lower()
        assert "permissible" in low or "below" in low or "allowed" in low, (
            "Below-max ride height should not be forbidden; "
            f"got directive: {d[:400]}"
        )
        # Must NOT say 'do NOT recommend raising' the ride-height fields
        assert "do NOT recommend raising" not in d

    def test_no_bottoming_no_explicit_rh_directive(self):
        """When avg_bottom == 0, no ride-height-specific sub-bullet should appear."""
        setup = {"ride_height_front": 200, "ride_height_rear": 200}
        d = self._directives(setup, avg_bottom=0.0)
        # The general AC3 text is present but the specific sub-bullet is NOT
        assert "ride_height_front is currently" not in d

