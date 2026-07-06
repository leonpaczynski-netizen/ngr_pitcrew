"""
Group 45 — Setup Brain Intelligence Expansion: Explainability Tests

Covers AC32-AC36 (Obj8 Explainability):
  AC32 — every approved change has non-empty: symptom, evidence(list), rule_id, rationale,
          source_label, risk_level, confidence_level, driver_style_alignment
  AC33 — session_influence / car_drivetrain_influence populated only when context used
  AC34 — each rejected candidate has rule_id, reason, symptom, risk_level
          (and reason names what blocked it)
  AC35 — baseline changes carry source_label in {_LABEL_NEUTRAL, _LABEL_BIASED,
          _LABEL_MIDPOINT, _LABEL_CONSERV}, symptom="no telemetry baseline",
          NO tyre/fuel claim
  AC36 — Scenario 5 (unknown session/tyre/fuel) → no aware-behaviour text anywhere;
          Scenario 9 baseline distinguishes diagnosed/inferred from conservative default,
          passes validator, Apply-gated

All tests are pure/offline — no network, no Qt event loop.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import strategy.driving_advisor as da
from strategy._setup_constants import APPROVED_STATUSES
from strategy.setup_baseline import (
    _LABEL_NEUTRAL, _LABEL_BIASED, _LABEL_MIDPOINT, _LABEL_CONSERV,
    build_baseline_setup,
)
from strategy.setup_driver_profile import build_driver_profile, DriverProfile
from strategy.setup_ranges import resolve_ranges
from strategy.setup_rule_engine import run_rule_engine
from strategy.setup_knowledge_base import DrivetrainType, CarClass


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_lap(
    bottoming_count: int = 0,
    wheelspin_count: int = 0,
    snap_throttle_count: int = 0,
    lock_up_count: int = 0,
    rev_limiter_by_gear: dict | None = None,
    max_speed_kmh: float = 200.0,
    oversteer_count: int = 0,
    kerb_count: int = 0,
) -> SimpleNamespace:
    rlbg = rev_limiter_by_gear or {}
    return SimpleNamespace(
        bottoming_count=bottoming_count,
        wheelspin_count=wheelspin_count,
        snap_throttle_count=snap_throttle_count,
        lock_up_count=lock_up_count,
        rev_limiter_by_gear=rlbg,
        max_speed_kmh=max_speed_kmh,
        brake_consistency_m=5.0,
        oversteer_count=oversteer_count,
        oversteer_throttle_on_count=0,
        kerb_count=kerb_count,
        max_lat_g=1.5,
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
        frames=[],
    )


def _make_advisor_no_api(event_ctx: dict, laps: list) -> da.DrivingAdvisor:
    adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
    adv._recorder = SimpleNamespace(recent_laps=lambda n: laps)
    adv._tracker = None
    adv._config = {}
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


def _make_neutral_profile() -> DriverProfile:
    return DriverProfile(
        profile_version="v1.0-test",
        style_tags=[],
        hard_constraints=[],
        prefers_rear_stability=False,
        dislikes_snap_exit=False,
        trail_braker=False,
        rotation_without_snap=False,
        prefers_front_bite=False,
        dislikes_floaty_front=False,
        protects_downforce=False,
        race_values_consistency=False,
    )


def _bottoming_wheelspin_laps():
    return [
        _make_lap(bottoming_count=5, wheelspin_count=18),
        _make_lap(bottoming_count=4, wheelspin_count=20),
        _make_lap(bottoming_count=6, wheelspin_count=19),
        _make_lap(bottoming_count=5, wheelspin_count=21),
        _make_lap(bottoming_count=5, wheelspin_count=18),
    ]


# ===========================================================================
# AC32 — every approved change has required explainability keys
# ===========================================================================

class TestAC32RequiredExplainabilityKeys:
    """AC32: every approved change must have non-empty required keys."""

    _REQUIRED_KEYS = (
        "symptom", "evidence", "rule_id", "rationale",
        "source_label", "risk_level", "confidence_level", "driver_style_alignment",
    )

    def test_all_required_keys_present(self):
        """All approved changes have the required explainability keys."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20,
                 "ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        changes = result.get("changes", [])
        if not changes:
            pytest.skip("No changes produced — cannot check explainability keys")

        for i, ch in enumerate(changes):
            for key in self._REQUIRED_KEYS:
                assert key in ch, (
                    f"AC32 FAIL: change #{i} ({ch.get('field')}) missing key '{key}'"
                )
                val = ch[key]
                assert val is not None, (
                    f"AC32 FAIL: change #{i} key '{key}' is None"
                )

    def test_evidence_is_list(self):
        """evidence key must be a list (not a string)."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        for ch in result.get("changes", []):
            ev = ch.get("evidence")
            assert isinstance(ev, list), (
                f"AC32 FAIL: evidence must be a list; got {type(ev).__name__} for {ch.get('field')}"
            )

    def test_source_label_in_valid_values(self):
        """source_label must be one of the known labels."""
        from strategy.setup_baseline import (
            _LABEL_NEUTRAL, _LABEL_BIASED, _LABEL_MIDPOINT, _LABEL_CONSERV,
        )
        valid_sources = {
            "Porsche-specific rule",
            "generic rule",
            _LABEL_NEUTRAL, _LABEL_BIASED, _LABEL_MIDPOINT, _LABEL_CONSERV,
        }
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        for ch in result.get("changes", []):
            sl = ch.get("source_label", "")
            assert sl in valid_sources, (
                f"AC32 FAIL: source_label={sl!r} not in {valid_sources}; "
                f"field={ch.get('field')}"
            )

    def test_symptom_is_nonempty_string(self):
        """symptom must be a non-empty string."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        for ch in result.get("changes", []):
            sym = ch.get("symptom", "")
            assert sym and isinstance(sym, str), (
                f"AC32 FAIL: symptom must be non-empty string; "
                f"got {sym!r} for {ch.get('field')}"
            )


# ===========================================================================
# AC33 — session_influence/car_drivetrain_influence only when context used
# ===========================================================================

class TestAC33ContextualInfluenceKeys:
    """AC33: session/drivetrain influence text only when that context was provided."""

    def test_session_influence_not_claiming_quali_when_no_session(self):
        """Without session purpose, no change should claim qualifying bias."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20}
        adv = _make_advisor_no_api({}, laps)

        # No purpose → session_type=None
        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        for ch in result.get("changes", []):
            si = ch.get("session_influence", "")
            assert "qualifying bias applied" not in si, (
                f"AC33 FAIL: 'qualifying bias applied' claimed without session context; "
                f"field={ch.get('field')}, session_influence={si!r}"
            )

    def test_car_drivetrain_influence_empty_for_fr_drivetrain(self):
        """For an FR car (non-rr), car_drivetrain_influence should not claim RR modifiers."""
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 0.0, "wheelspin_band": "low",
            "avg_snap": 0.0, "avg_lockups": 0.0,
            "driver_feel_flags": {},
            "gearbox_flag": "preserve",
            "compliance_priority": False,
            "aero_front_near_min": False, "aero_rear_near_min": False,
            "aero_rear_healthy": False,
            "dominant_problem": "unknown",
            "gearing_diagnosis_category": "insufficient_data",
            "wheelspin_subtype": "insufficient_data",
            "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
            "avg_rev_limiter_total": 0.0,
            "rev_limiter_by_gear": None,
            "per_gear_limiter_evidence": None,
        }
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(
            diag, setup, ranges, profile,
            session_type=None,
            drivetrain=DrivetrainType.fr,
        )

        for ch in plan.proposed:
            cdi = getattr(ch, "car_drivetrain_influence", "")
            assert "RR drivetrain" not in cdi, (
                f"AC33 FAIL: 'RR drivetrain' claimed for FR car; "
                f"field={ch.field}, car_drivetrain_influence={cdi!r}"
            )


# ===========================================================================
# AC34 — rejected candidates have required keys
# ===========================================================================

class TestAC34RejectedCandidatesKeys:
    """AC34: rejected candidates must have rule_id, reason (rationale), symptom, risk_level."""

    def test_rejected_candidates_have_required_keys(self):
        """Rejected candidates from the plan have the required fields."""
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 20.0, "wheelspin_band": "severe",
            "avg_snap": 8.0, "avg_lockups": 0.0,
            "driver_feel_flags": {
                "snap_oversteer_exit": True,   # causes B3 to fire AND some rules to be blocked
                "rear_loose_on_exit": True,
            },
            "gearbox_flag": "preserve",
            "compliance_priority": False,
            "aero_front_near_min": False, "aero_rear_near_min": False,
            "aero_rear_healthy": False,
            "dominant_problem": "wheelspin",
            "gearing_diagnosis_category": "insufficient_data",
            "wheelspin_subtype": "snap_throttle_induced",
            "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
            "avg_rev_limiter_total": 0.0,
            "rev_limiter_by_gear": None,
            "per_gear_limiter_evidence": None,
        }
        setup = {"lsd_accel": 20, "aero_rear": 50}
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile)

        if not plan.rejected_candidates:
            pytest.skip("No rejected candidates in this scenario")

        for i, rej in enumerate(plan.rejected_candidates):
            # rule_id
            assert rej.rule_id, f"AC34 FAIL: rejected #{i} missing rule_id"
            # rationale (serves as reason — explains what blocked it)
            assert rej.rationale, f"AC34 FAIL: rejected #{i} missing rationale (reason)"
            # symptom
            assert rej.symptom, f"AC34 FAIL: rejected #{i} missing symptom"
            # risk (either RiskLevel enum or its .value string)
            risk_val = rej.risk.value if hasattr(rej.risk, "value") else str(rej.risk)
            assert risk_val in {"low", "med", "high"}, (
                f"AC34 FAIL: rejected #{i} risk_level={risk_val!r} not in {{low, med, high}}"
            )

    def test_rejected_in_json_response_have_field(self):
        """rejected_changes in JSON response have 'field' key."""
        laps = _bottoming_wheelspin_laps()
        setup = {"aero_front": 0, "aero_rear": 50, "lsd_accel": 20,
                 "ride_height_front": 80, "ride_height_rear": 82}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(
            setup_dict=setup, car_name="",
            feeling="snap oversteer on exit, rear loose",
        )
        result = json.loads(result_str)

        for rej in result.get("rejected_changes", []):
            assert "field" in rej or "rule_id" in rej, (
                f"AC34 FAIL: rejected change missing 'field' and 'rule_id'; got {rej.keys()!r}"
            )


# ===========================================================================
# AC35 — baseline changes have correct source labels and symptom
# ===========================================================================

class TestAC35BaselineSourceLabels:
    """AC35: baseline changes carry source_label in {_LABEL_NEUTRAL, _LABEL_BIASED,
    _LABEL_MIDPOINT, _LABEL_CONSERV}, symptom='no telemetry baseline', no tyre/fuel claim."""

    _VALID_LABELS = {_LABEL_NEUTRAL, _LABEL_BIASED, _LABEL_MIDPOINT, _LABEL_CONSERV}

    def test_baseline_source_labels_are_valid(self):
        """All baseline change source_labels must be one of the 4 valid label constants."""
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()
        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)

        for ch in result.get("changes", []):
            sl = ch.get("source_label", "")
            assert sl in self._VALID_LABELS, (
                f"AC35 FAIL: baseline change source_label={sl!r} not in {self._VALID_LABELS}; "
                f"field={ch.get('field')}"
            )

    def test_baseline_symptom_is_no_telemetry(self):
        """All baseline changes must have symptom='no telemetry baseline'."""
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()
        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)

        for ch in result.get("changes", []):
            sym = ch.get("symptom", "")
            assert sym == "no telemetry baseline", (
                f"AC35 FAIL: baseline symptom={sym!r} for field={ch.get('field')!r}; "
                f"expected 'no telemetry baseline'"
            )

    def test_baseline_no_tyre_fuel_claims(self):
        """Baseline changes must not claim tyre/fuel context."""
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()
        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)

        tyre_fuel_terms = ["tyre wear", "fuel", "tyre/fuel", "high wear"]
        for ch in result.get("changes", []):
            rationale = ch.get("rationale", "") + ch.get("why", "")
            for term in tyre_fuel_terms:
                assert term not in rationale.lower(), (
                    f"AC35 FAIL: baseline change claims tyre/fuel context: "
                    f"field={ch.get('field')}, found '{term}' in rationale={rationale!r}"
                )


# ===========================================================================
# AC36 — Scenario 5: unknown session/tyre/fuel → no aware-behaviour text
# ===========================================================================

class TestAC36Scenario5NoClaims:
    """AC36: with unknown session/tyre/fuel context, no aware-behaviour text appears."""

    def test_no_session_specific_claim_without_session(self):
        """Without session purpose, no change claims session-specific behaviour."""
        laps = [_make_lap(wheelspin_count=20)]
        setup = {"aero_rear": 50, "lsd_accel": 20, "ride_height_front": 80}
        adv = _make_advisor_no_api({}, laps)

        # No purpose → session_type=None
        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        aware_phrases = [
            "qualifying bias applied — front response/bite prioritised",
            "race consistency bias applied",
            "endurance bias applied",
        ]
        for ch in result.get("changes", []):
            si = ch.get("session_influence", "")
            for phrase in aware_phrases:
                assert phrase not in si, (
                    f"AC36 FAIL: change claims '{phrase}' without session context; "
                    f"field={ch.get('field')}, session_influence={si!r}"
                )

    def test_no_tyre_aware_claim_without_tyre_context(self):
        """Without tyre context, no change claims tyre-aware behaviour."""
        laps = [_make_lap(wheelspin_count=20)]
        setup = {"aero_rear": 50, "lsd_accel": 20}
        adv = _make_advisor_no_api({}, laps)

        result_str = adv.build_combined_setup_response(setup_dict=setup, car_name="", feeling=None)
        result = json.loads(result_str)

        tyre_claim_phrases = ["tyre wear aware", "high tyre wear applied", "tyre-wear-aware"]
        for ch in result.get("changes", []):
            combined = (
                ch.get("rationale", "") +
                ch.get("why", "") +
                ch.get("symptom", "")
            )
            for phrase in tyre_claim_phrases:
                assert phrase not in combined.lower(), (
                    f"AC36 FAIL: change claims '{phrase}' without tyre context; "
                    f"field={ch.get('field')}"
                )

    def test_baseline_scenario9_distinguishes_labels(self):
        """Scenario 9 baseline: conservative fields labelled differently from neutral/biased."""
        from strategy.setup_baseline import _CONSERVATIVE_FIELDS
        ranges = resolve_ranges("")
        profile = _make_neutral_profile()
        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)

        changes_by_field = {ch["field"]: ch for ch in result.get("changes", [])}

        # Conservative fields must have _LABEL_CONSERV
        for field in _CONSERVATIVE_FIELDS:
            if field in changes_by_field:
                sl = changes_by_field[field].get("source_label", "")
                assert sl == _LABEL_CONSERV, (
                    f"AC36 FAIL: conservative field {field!r} has source_label={sl!r}; "
                    f"expected {_LABEL_CONSERV!r}"
                )

        # Non-conservative, non-biased fields must have _LABEL_NEUTRAL
        for field, ch in changes_by_field.items():
            if field in _CONSERVATIVE_FIELDS:
                continue
            sl = ch.get("source_label", "")
            if sl != _LABEL_BIASED and field != "final_drive":
                # final_drive and gear ratios use _LABEL_MIDPOINT
                if not field.startswith("gear_") and field != "final_drive":
                    assert sl in {_LABEL_NEUTRAL, _LABEL_BIASED}, (
                        f"AC36 FAIL: non-conservative field {field!r} has unexpected label {sl!r}"
                    )

    def test_baseline_passes_validator_and_apply_gate(self):
        """Baseline response passes the validator funnel and is in APPROVED_STATUSES."""
        ranges = resolve_ranges("")
        adv = _make_advisor_no_api({}, [])
        # Override recorder so recent_laps returns [] safely
        adv._recorder = SimpleNamespace(recent_laps=lambda n: [])

        result_str = adv.build_baseline_setup_response(
            car_name="", ranges=ranges, drivetrain="FR", num_gears=6,
            allowed_tuning=None, tuning_locked=False,
        )
        result = json.loads(result_str)

        status = result.get("recommendation_status", "")
        assert status in APPROVED_STATUSES, (
            f"AC36 FAIL: baseline did not pass validator/Apply gate; status={status!r}"
        )
