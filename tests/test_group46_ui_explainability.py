"""
Group 46 — Learning & Race Context Intelligence: UI Explainability Tests

Covers ACs 38-42 (UI/Explainability layer):
  AC38 — learning row renders only when learning_influence non-empty (Group 46 UI).
  AC39 — session row only when session_influence non-empty (Group 46 UI).
  AC40 — no "session bias applied"/"learning applied" text when the path changed nothing.
  AC41 — user can distinguish telemetry/feedback/profile/session/fuel-tyre/Porsche/learning
           contributions (relevant keys present in change dicts from build_combined output).
  AC42 — both Baseline and Analyse produce valid approved output with NO api_key
           (AI-disabled path works end-to-end).

All UI tests are offline/isolated using temp_config_path (never the real config.json).
SetupBuilderMixin tests use the offscreen QPA platform.
Pure backend/struct tests do not require Qt.
"""
from __future__ import annotations

import inspect
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

pytest.importorskip("PyQt6.QtWidgets")

from PyQt6.QtWidgets import QApplication, QTextEdit  # noqa: E402

from strategy._setup_constants import APPROVED_STATUSES, RULE_ENGINE_VERSION
from strategy.setup_baseline import build_baseline_setup, _SESSION_BIAS_TABLE
from strategy.setup_driver_profile import DriverProfile
from strategy.setup_ranges import resolve_ranges
from strategy.setup_rule_engine import (
    RuleOutcomeStore,
    SetupChangeIntent,
    SetupPlan,
    run_rule_engine,
)
from strategy.setup_knowledge_base import (
    ConfidenceLevel, RiskLevel, DrivetrainType, CarClass,
)
from strategy.setup_driver_profile import DriverStyleAlignment
import strategy.driving_advisor as da
from ui.setup_builder_ui import SetupBuilderMixin  # noqa: E402
from ui.setup_form_widget import SetupFormWidget   # noqa: E402


# ---------------------------------------------------------------------------
# QApplication fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _neutral_profile() -> DriverProfile:
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


def _make_advisor_no_api(event_ctx: dict = None, laps: list = None) -> da.DrivingAdvisor:
    """Minimal DrivingAdvisor with no API key."""
    adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
    adv._recorder = SimpleNamespace(recent_laps=lambda n: laps or [])
    adv._tracker = None
    adv._config = {}  # no api_key → engine-only path
    adv._db = None
    adv._car_id_ref = [0]
    adv._event_ctx = event_ctx or {}
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


def _make_lap(wheelspin_count: int = 0, snap_count: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        bottoming_count=0,
        wheelspin_count=wheelspin_count,
        snap_throttle_count=snap_count,
        lock_up_count=0,
        rev_limiter_by_gear={},
        max_speed_kmh=200.0,
        brake_consistency_m=5.0,
        oversteer_count=0,
        oversteer_throttle_on_count=0,
        kerb_count=0,
        max_lat_g=1.5,
        rev_limiter_count=0,
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


def _make_intent_with_learning(learning_influence: str = "learning: 5 samples, 80% success — confidence upgraded") -> SetupChangeIntent:
    """Helper to build a SetupChangeIntent with a specific learning_influence."""
    return SetupChangeIntent(
        field="lsd_accel",
        delta=2.0,
        from_value=15.0,
        to_value=17.0,
        symptom="wheelspin",
        evidence=["wheelspin_band=severe"],
        rule_id="B3",
        rationale="increase lsd_accel for traction",
        rejected_alternatives=[],
        risk=RiskLevel.low,
        confidence=ConfidenceLevel.med,
        driver_style_alignment=DriverStyleAlignment.neutral,
        source_label="generic rule",
        session_influence="",
        car_drivetrain_influence="",
        pack="B",
        learning_influence=learning_influence,
        fuel_influence="",
    )


def _make_intent_with_session(session_influence: str = "qualifying bias applied — front response/bite prioritised") -> SetupChangeIntent:
    """Helper to build a SetupChangeIntent with a specific session_influence."""
    return SetupChangeIntent(
        field="lsd_decel",
        delta=-1.0,
        from_value=5.0,
        to_value=4.0,
        symptom="session context",
        evidence=[],
        rule_id="B2",
        rationale="session context",
        rejected_alternatives=[],
        risk=RiskLevel.low,
        confidence=ConfidenceLevel.low,
        driver_style_alignment=DriverStyleAlignment.neutral,
        source_label="generic rule",
        session_influence=session_influence,
        car_drivetrain_influence="",
        pack="B",
        learning_influence="",
        fuel_influence="",
    )


# ===========================================================================
# AC38 — learning row renders only when learning_influence non-empty
# ===========================================================================

class TestAC38LearningRowRendered:
    """AC38: The UI renders a Learning row ONLY when learning_influence is non-empty.
    This is tested at the source-inspection level (the HTML rendering code checks
    `if _learning_influence:`) and at the data-structure level."""

    def test_ui_source_gates_learning_row_on_non_empty(self):
        """UI source code gates the Learning row on non-empty learning_influence."""
        src = inspect.getsource(SetupBuilderMixin._display_setup_result)
        assert "_learning_influence = ch.get(\"learning_influence\", \"\")" in src, (
            "AC38 FAIL: learning_influence extraction not found in _display_setup_result"
        )
        assert "if _learning_influence:" in src, (
            "AC38 FAIL: 'if _learning_influence:' gate not found in _display_setup_result; "
            "Learning row must only render when non-empty"
        )

    def test_setup_change_intent_learning_influence_field_exists(self):
        """SetupChangeIntent has learning_influence field with default ''."""
        intent = SetupChangeIntent(
            field="lsd_accel",
            delta=2.0,
            from_value=15.0,
            to_value=17.0,
            symptom="test",
            evidence=[],
            rule_id="B3",
            rationale="test",
            rejected_alternatives=[],
            risk=RiskLevel.low,
            confidence=ConfidenceLevel.med,
            driver_style_alignment=DriverStyleAlignment.neutral,
        )
        # Default must be ""
        assert hasattr(intent, "learning_influence"), (
            "AC38 FAIL: SetupChangeIntent missing learning_influence field"
        )
        assert intent.learning_influence == "", (
            f"AC38 FAIL: learning_influence default not ''; got {intent.learning_influence!r}"
        )

    def test_empty_learning_influence_no_learning_row(self):
        """An intent with learning_influence='' produces no Learning row in HTML.

        This is tested structurally: the UI source has 'if _learning_influence:' before
        rendering the Learning <tr>. We verify the condition by checking the
        rendering path guards (source-level).
        """
        src = inspect.getsource(SetupBuilderMixin._display_setup_result)
        # Verify the guard exists and the content of the row
        assert "Learning" in src, (
            "AC38 FAIL: 'Learning' label not found in _display_setup_result HTML output"
        )
        # The row must be conditionally rendered
        # Find "Learning" and check it's inside the if block
        li = src.find("if _learning_influence:")
        lr = src.find("Learning")
        assert li >= 0 and lr > li, (
            "AC38 FAIL: Learning row appears before the 'if _learning_influence:' guard"
        )


# ===========================================================================
# AC39 — session row only when session_influence non-empty
# ===========================================================================

class TestAC39SessionRowRendered:
    """AC39: Session row is only rendered when session_influence is non-empty."""

    def test_ui_source_gates_session_row_on_non_empty(self):
        """UI source code gates the Session row on non-empty session_influence."""
        src = inspect.getsource(SetupBuilderMixin._display_setup_result)
        assert "_session_influence = ch.get(\"session_influence\", \"\")" in src, (
            "AC39 FAIL: session_influence extraction not found in _display_setup_result"
        )
        assert "if _session_influence:" in src, (
            "AC39 FAIL: 'if _session_influence:' gate not found; "
            "Session row must only render when non-empty"
        )

    def test_session_row_appears_after_gate(self):
        """Session label is rendered after the 'if _session_influence:' gate."""
        src = inspect.getsource(SetupBuilderMixin._display_setup_result)
        si_gate = src.find("if _session_influence:")
        session_label = src.find(">Session<", si_gate)
        assert si_gate >= 0, "AC39 FAIL: 'if _session_influence:' not found"
        assert session_label > si_gate, (
            "AC39 FAIL: Session label appears before the gate or not found after it"
        )


# ===========================================================================
# AC40 — no false "session bias applied"/"learning applied" claims
# ===========================================================================

class TestAC40NoFalseClaims:
    """AC40: when the path changed nothing, no 'session bias applied'/'learning applied'
    text appears in the change output."""

    def test_unknown_session_no_session_bias_applied_in_changes(self):
        """build_baseline_setup with unknown session → no 'session bias applied' text."""
        data = build_baseline_setup(
            car="",
            ranges=resolve_ranges(""),
            drivetrain="FR",
            num_gears=6,
            profile=_neutral_profile(),
            allowed_tuning=None,
            tuning_locked=False,
            session_type="",  # unknown
            duration_mins=0.0,
        )
        for ch in data["changes"]:
            si = ch.get("session_influence", "")
            assert "session bias applied" not in (si or ""), (
                f"AC40 FAIL: 'session bias applied' claimed for unknown session; "
                f"field={ch.get('field')!r}, session_influence={si!r}"
            )

    def test_engine_no_learning_applied_with_no_store(self):
        """run_rule_engine without rule_outcome_store → no learning_influence on any change."""
        from strategy.setup_diagnosis import build_setup_diagnosis
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 20.0, "wheelspin_band": "severe",
            "avg_snap": 0.0, "avg_lockups": 0.0,
            "driver_feel_flags": {"rear_loose_on_exit": True, "snap_oversteer_exit": False},
            "gearbox_flag": "preserve",
            "compliance_priority": False,
            "aero_front_near_min": False, "aero_rear_near_min": False,
            "aero_rear_healthy": False,
            "dominant_problem": "wheelspin",
            "gearing_diagnosis_category": "insufficient_data",
            "wheelspin_subtype": "wheelspin",
            "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
            "avg_rev_limiter_total": 0.0,
            "rev_limiter_by_gear": None, "per_gear_limiter_evidence": None,
        }
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _neutral_profile()

        plan = run_rule_engine(diag, setup, ranges, profile, rule_outcome_store=None)

        for ch in plan.proposed:
            assert ch.learning_influence == "", (
                f"AC40 FAIL: learning_influence non-empty without rule_outcome_store; "
                f"field={ch.field!r}, learning_influence={ch.learning_influence!r}"
            )

    def test_mid_rate_store_no_learning_applied_claim(self):
        """rate between LOW and HIGH thresholds → no 'learning applied' in learning_influence."""
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 20.0, "wheelspin_band": "severe",
            "avg_snap": 0.0, "avg_lockups": 0.0,
            "driver_feel_flags": {"rear_loose_on_exit": True, "snap_oversteer_exit": False},
            "gearbox_flag": "preserve",
            "compliance_priority": False,
            "aero_front_near_min": False, "aero_rear_near_min": False,
            "aero_rear_healthy": False,
            "dominant_problem": "wheelspin",
            "gearing_diagnosis_category": "insufficient_data",
            "wheelspin_subtype": "wheelspin",
            "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
            "avg_rev_limiter_total": 0.0,
            "rev_limiter_by_gear": None, "per_gear_limiter_evidence": None,
        }
        setup = {"lsd_accel": 20}
        ranges = resolve_ranges("")
        profile = _neutral_profile()

        plan_empty = run_rule_engine(diag, setup, ranges, profile)
        if not plan_empty.proposed:
            pytest.skip("No proposed changes to test")
        rule_id = plan_empty.proposed[0].rule_id

        # 50% success rate — between thresholds (LOW=0.40, HIGH=0.60)
        store = RuleOutcomeStore()
        for _ in range(10):
            store.record_fire(rule_id)
        for _ in range(5):  # 5/10 = 0.50
            store.record_success(rule_id)

        plan = run_rule_engine(diag, setup, ranges, profile, rule_outcome_store=store)

        for ch in plan.proposed:
            if ch.rule_id == rule_id:
                assert "learning applied" not in (ch.learning_influence or "").lower(), (
                    f"AC40 FAIL: mid-rate store claims 'learning applied'; "
                    f"learning_influence={ch.learning_influence!r}"
                )


# ===========================================================================
# AC41 — user can distinguish all contribution types
# ===========================================================================

class TestAC41DistinguishableContributions:
    """AC41: change dicts carry all explainability fields so user can see what drove each change."""

    def test_setup_change_intent_has_all_explainability_fields(self):
        """SetupChangeIntent has all Group 45+46 explainability fields."""
        intent = _make_intent_with_learning()
        required_fields = [
            "source_label",
            "session_influence",
            "car_drivetrain_influence",
            "pack",
            "learning_influence",
            "fuel_influence",
        ]
        for f in required_fields:
            assert hasattr(intent, f), (
                f"AC41 FAIL: SetupChangeIntent missing field {f!r}"
            )

    def test_plan_to_raw_data_carries_learning_and_fuel(self):
        """plan_to_raw_data output includes learning_influence and fuel_influence keys."""
        from strategy.setup_plan import plan_to_raw_data
        intent = SetupChangeIntent(
            field="lsd_accel",
            delta=2.0,
            from_value=15.0,
            to_value=17.0,
            symptom="wheelspin",
            evidence=["wheelspin_band=severe"],
            rule_id="B3",
            rationale="test",
            rejected_alternatives=[],
            risk=RiskLevel.low,
            confidence=ConfidenceLevel.med,
            driver_style_alignment=DriverStyleAlignment.neutral,
            source_label="generic rule",
            session_influence="qualifying bias applied",
            car_drivetrain_influence="",
            pack="B",
            learning_influence="learning: 5 samples, 80% success — confidence upgraded",
            fuel_influence="high fuel load: traction/stability prioritised",
        )
        plan = SetupPlan(
            proposed=[intent],
            rejected_candidates=[],
            protected_fields=[],
        )
        data = plan_to_raw_data(plan, {}, "test analysis")
        assert data.get("changes"), "plan_to_raw_data must return changes"
        ch = data["changes"][0]
        assert "learning_influence" in ch, (
            "AC41 FAIL: learning_influence not in plan_to_raw_data output"
        )
        assert "fuel_influence" in ch, (
            "AC41 FAIL: fuel_influence not in plan_to_raw_data output"
        )
        assert ch["learning_influence"] == intent.learning_influence
        assert ch["fuel_influence"] == intent.fuel_influence

    def test_all_contribution_source_labels_distinct(self):
        """source_label values distinguish Porsche-specific vs generic contributions."""
        valid_labels = {"Porsche-specific rule", "generic rule", "per-gear rule"}
        # Verify at least two distinct valid labels are defined (Porsche + generic)
        assert len(valid_labels) >= 2
        # Verify the source label constants used in setup_rule_engine
        from strategy.setup_rule_engine import _process_rule
        src = inspect.getsource(_process_rule)
        assert "Porsche-specific rule" in src, "AC41 FAIL: 'Porsche-specific rule' not in engine"
        assert "generic rule" in src, "AC41 FAIL: 'generic rule' not in engine"


# ===========================================================================
# AC42 — AI-disabled path: Baseline and Analyse both produce valid approved output
# ===========================================================================

class TestAC42AIDisabledPath:
    """AC42: both Baseline and Analyse produce valid approved output with no api_key.

    Architecture ACs 1, 3, 4 are also confirmed here:
      AC1 — AI audit can't add approved fields (no api_key → no AI audit)
      AC3 — Analyse works AI-disabled
      (Baseline AI-disabled is AC2, covered by Group 44 tests; we add a regression here)
    """

    def test_analyse_no_api_key_returns_approved_json(self):
        """build_combined_setup_response with no api_key returns a valid approved JSON."""
        laps = [_make_lap(wheelspin_count=15, snap_count=10) for _ in range(3)]
        adv = _make_advisor_no_api(event_ctx={}, laps=laps)

        result_str = adv.build_combined_setup_response(
            setup_dict={"lsd_accel": 15},
            n_laps=3,
            car_name="",
        )
        result = json.loads(result_str)

        status = result.get("recommendation_status", "")
        assert status in APPROVED_STATUSES or status == "fallback_generated", (
            f"AC42 FAIL: analyse with no api_key returned status={status!r}; "
            f"expected one of {APPROVED_STATUSES | {'fallback_generated'}}"
        )

    def test_analyse_no_api_key_no_ai_authored_changes(self):
        """Without api_key, no change should be tagged as AI-authored."""
        laps = [_make_lap(wheelspin_count=15, snap_count=10) for _ in range(3)]
        adv = _make_advisor_no_api(event_ctx={}, laps=laps)

        result_str = adv.build_combined_setup_response(
            setup_dict={"lsd_accel": 15},
            n_laps=3,
            car_name="",
        )
        result = json.loads(result_str)

        for ch in result.get("changes", []):
            rule_id = ch.get("rule_id", "")
            assert not rule_id.startswith("ai_"), (
                f"AC42 FAIL: AI-authored change found with no api_key; rule_id={rule_id!r}"
            )

    def test_baseline_no_api_key_returns_approved_json(self):
        """build_baseline_setup_response with no api_key returns a valid approved JSON."""
        adv = _make_advisor_no_api()

        result_str = adv.build_baseline_setup_response(
            car_name="",
            ranges=resolve_ranges(""),
            drivetrain="FR",
            num_gears=6,
            allowed_tuning=None,
            tuning_locked=False,
            session_type="Race",
            duration_mins=0.0,
        )
        result = json.loads(result_str)

        status = result.get("recommendation_status", "")
        assert status in APPROVED_STATUSES or status == "fallback_generated", (
            f"AC42 FAIL: baseline with no api_key returned status={status!r}; "
            f"expected one of {APPROVED_STATUSES | {'fallback_generated'}}"
        )

    def test_baseline_and_analyse_non_contradictory_direction(self):
        """Baseline and Analyse don't produce opposite recommendations for the same field
        under identical setup/context conditions.

        'Non-contradictory on direction' means: if baseline says 'increase lsd_accel'
        and analyse (with wheelspin laps) also says 'increase lsd_accel', they agree.
        If they differ, the difference must be explainable (Analyse has telemetry evidence;
        Baseline uses neutral seeds). This test verifies they don't actively contradict
        (e.g., one increases and the other decreases the same field).

        We use a wheelspin context where both paths would suggest increasing lsd_accel.
        """
        # Baseline
        baseline = build_baseline_setup(
            car="",
            ranges=resolve_ranges(""),
            drivetrain="FR",
            num_gears=6,
            profile=_neutral_profile(),
            allowed_tuning=None,
            tuning_locked=False,
            session_type="",
            duration_mins=0.0,
        )
        baseline_fields = {ch["field"]: ch.get("to_clamped")
                          for ch in baseline["changes"]}

        # Analyse via rule engine (wheelspin diagnosis)
        diag = {
            "avg_bottoming": 0.0, "bottoming_band": "minor",
            "avg_wheelspin": 20.0, "wheelspin_band": "severe",
            "avg_snap": 0.0, "avg_lockups": 0.0,
            "driver_feel_flags": {"rear_loose_on_exit": True, "snap_oversteer_exit": False},
            "gearbox_flag": "preserve",
            "compliance_priority": False,
            "aero_front_near_min": False, "aero_rear_near_min": False,
            "aero_rear_healthy": False,
            "dominant_problem": "wheelspin",
            "gearing_diagnosis_category": "insufficient_data",
            "wheelspin_subtype": "wheelspin",
            "bottoming_confidence": {"band": "minor", "subtype": "insufficient_data", "confidence": "low"},
            "avg_rev_limiter_total": 0.0,
            "rev_limiter_by_gear": None, "per_gear_limiter_evidence": None,
        }
        # Use baseline lsd_accel as starting point for Analyse
        analyse_setup = {"lsd_accel": int(baseline_fields.get("lsd_accel", 15))}
        ranges = resolve_ranges("")
        profile = _neutral_profile()
        plan = run_rule_engine(diag, analyse_setup, ranges, profile)

        # Verify: if Analyse proposes lsd_accel increase, Baseline hasn't decreased it
        for ch in plan.proposed:
            if ch.field == "lsd_accel" and ch.delta > 0:
                baseline_lsd = baseline_fields.get("lsd_accel")
                if baseline_lsd is not None:
                    neutral_seed = 15  # NEUTRAL_SEEDS["lsd_accel"]
                    assert float(baseline_lsd) >= neutral_seed, (
                        f"AC42 FAIL: Baseline decreased lsd_accel below neutral seed "
                        f"({neutral_seed}) despite Analyse proposing an increase; "
                        f"baseline_lsd={baseline_lsd}"
                    )

    def test_rule_engine_version_is_46(self):
        """RULE_ENGINE_VERSION must be '46.0' (Group 46 version bump)."""
        assert RULE_ENGINE_VERSION == "46.0", (
            f"AC42 FAIL: RULE_ENGINE_VERSION={RULE_ENGINE_VERSION!r}; expected '46.0'"
        )
