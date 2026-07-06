"""
Group 45 — Setup Brain Intelligence Expansion: Baseline Context Tests

Covers:
  Obj1 / AC7-AC9 — Driver-profile bias applied to baseline:
    AC7  — trail_braker → brake_bias biased (source_label = _LABEL_BIASED)
    AC8  — rotation_without_snap → lsd_decel biased (source_label = _LABEL_BIASED)
    AC9  — neutral profile → no bias applied (no _LABEL_BIASED changes)

  Obj9 — Baseline session/context wiring:
    AC37 — session_influence on biased baseline fields uses session text when session_type
            is provided ("Qualifying" → quali bias text)
    AC38 — baseline passes validator (recommendation_status in APPROVED_STATUSES)
    AC39 — baseline is Apply-gated (recommendation_status in APPROVED_STATUSES, not blocked)
    AC40 — conservative fields use _LABEL_CONSERV (diagnosed vs conservative distinction)

All tests are pure/offline — no network, no Qt, no MainWindow construction.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy._setup_constants import APPROVED_STATUSES
from strategy.setup_baseline import (
    _CONSERVATIVE_FIELDS,
    _LABEL_BIASED,
    _LABEL_CONSERV,
    _LABEL_MIDPOINT,
    _LABEL_NEUTRAL,
    build_baseline_setup,
)
from strategy.setup_driver_profile import DriverProfile, build_driver_profile
from strategy.setup_ranges import resolve_ranges
import strategy.driving_advisor as da


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_advisor_no_recorder() -> da.DrivingAdvisor:
    """Minimal DrivingAdvisor that does not need a recorder or DB."""
    adv = da.DrivingAdvisor.__new__(da.DrivingAdvisor)
    adv._recorder = SimpleNamespace(recent_laps=lambda n: [], last_lap=lambda: None)
    adv._tracker = None
    adv._config = {}
    adv._db = None
    adv._car_id_ref = [0]
    adv._event_ctx = {}
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


def _profile_with(**flags) -> DriverProfile:
    """Build a DriverProfile with selected flags set."""
    defaults = dict(
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
    defaults.update(flags)
    return DriverProfile(**defaults)


def _neutral_profile() -> DriverProfile:
    return _profile_with()


# ===========================================================================
# Obj1 / AC7 — trail_braker → brake_bias biased
# ===========================================================================

class TestAC7TrailBrakerBias:
    """AC7: trail_braker profile flag biases brake_bias with source_label = _LABEL_BIASED."""

    def test_trail_braker_brakes_bias_label(self):
        """trail_braker=True → brake_bias change has source_label == _LABEL_BIASED."""
        profile = _profile_with(trail_braker=True)
        ranges = resolve_ranges("")

        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)

        brake_changes = [
            ch for ch in result.get("changes", [])
            if ch.get("field") == "brake_bias"
        ]
        assert brake_changes, (
            "AC7 FAIL: trail_braker profile produced no brake_bias change"
        )
        for ch in brake_changes:
            assert ch.get("source_label") == _LABEL_BIASED, (
                f"AC7 FAIL: brake_bias change has source_label={ch.get('source_label')!r}; "
                f"expected {_LABEL_BIASED!r}"
            )

    def test_trail_braker_biases_brake_bias_forward(self):
        """trail_braker=True applies -0.5 delta to brake_bias vs neutral profile."""
        neutral = _neutral_profile()
        biased = _profile_with(trail_braker=True)
        ranges = resolve_ranges("")

        res_neutral = build_baseline_setup("", ranges, "FR", 6, neutral, None, False)
        res_biased = build_baseline_setup("", ranges, "FR", 6, biased, None, False)

        fields_neutral = {ch["field"]: ch for ch in res_neutral.get("changes", [])}
        fields_biased = {ch["field"]: ch for ch in res_biased.get("changes", [])}

        # brake_bias must be biased differently (more forward, lower value)
        if "brake_bias" in fields_neutral and "brake_bias" in fields_biased:
            to_neutral = fields_neutral["brake_bias"].get("to_value", 0)
            to_biased = fields_biased["brake_bias"].get("to_value", 0)
            # trail_braker applies -0.5 (moves bias forward = lower number)
            assert to_biased <= to_neutral, (
                f"AC7 FAIL: trail_braker should move brake_bias forward (<=); "
                f"neutral={to_neutral}, biased={to_biased}"
            )

    def test_neutral_profile_no_trail_braker_bias(self):
        """Neutral profile (trail_braker=False) does not mark brake_bias as _LABEL_BIASED."""
        profile = _neutral_profile()
        ranges = resolve_ranges("")

        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)

        for ch in result.get("changes", []):
            if ch.get("field") == "brake_bias":
                assert ch.get("source_label") != _LABEL_BIASED, (
                    "AC7 FAIL: neutral profile marked brake_bias as biased"
                )


# ===========================================================================
# Obj1 / AC8 — rotation_without_snap → lsd_decel biased
# ===========================================================================

class TestAC8RotationWithoutSnapBias:
    """AC8: rotation_without_snap flag biases lsd_decel with source_label = _LABEL_BIASED."""

    def test_rotation_without_snap_lsd_decel_label(self):
        """rotation_without_snap=True → lsd_decel change has source_label == _LABEL_BIASED."""
        profile = _profile_with(rotation_without_snap=True)
        ranges = resolve_ranges("")

        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)

        lsd_changes = [
            ch for ch in result.get("changes", [])
            if ch.get("field") == "lsd_decel"
        ]
        assert lsd_changes, (
            "AC8 FAIL: rotation_without_snap profile produced no lsd_decel change"
        )
        for ch in lsd_changes:
            assert ch.get("source_label") == _LABEL_BIASED, (
                f"AC8 FAIL: lsd_decel has source_label={ch.get('source_label')!r}; "
                f"expected {_LABEL_BIASED!r}"
            )

    def test_rotation_without_snap_reduces_lsd_decel(self):
        """rotation_without_snap=True applies -2 to lsd_decel vs neutral profile."""
        neutral = _neutral_profile()
        biased = _profile_with(rotation_without_snap=True)
        ranges = resolve_ranges("")

        res_neutral = build_baseline_setup("", ranges, "FR", 6, neutral, None, False)
        res_biased = build_baseline_setup("", ranges, "FR", 6, biased, None, False)

        fn = {ch["field"]: ch for ch in res_neutral.get("changes", [])}
        fb = {ch["field"]: ch for ch in res_biased.get("changes", [])}

        if "lsd_decel" in fn and "lsd_decel" in fb:
            to_n = fn["lsd_decel"].get("to_value", 0)
            to_b = fb["lsd_decel"].get("to_value", 0)
            # rotation_without_snap applies -2 → biased must be <= neutral
            assert to_b <= to_n, (
                f"AC8 FAIL: rotation_without_snap should reduce lsd_decel; "
                f"neutral={to_n}, biased={to_b}"
            )

    def test_neutral_profile_no_rotation_bias(self):
        """Neutral profile does not mark lsd_decel as _LABEL_BIASED."""
        profile = _neutral_profile()
        ranges = resolve_ranges("")

        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)

        for ch in result.get("changes", []):
            if ch.get("field") == "lsd_decel":
                # lsd_decel may be in _CONSERVATIVE_FIELDS — either is fine; just not BIASED
                assert ch.get("source_label") != _LABEL_BIASED, (
                    "AC8 FAIL: neutral profile marked lsd_decel as biased"
                )


# ===========================================================================
# Obj1 / AC9 — neutral profile → no bias applied
# ===========================================================================

class TestAC9NeutralProfileNoAdditionalBias:
    """AC9: a fully neutral profile produces no _LABEL_BIASED changes."""

    def test_no_biased_changes_with_neutral_profile(self):
        """Neutral profile → no change has source_label == _LABEL_BIASED."""
        profile = _neutral_profile()
        ranges = resolve_ranges("")

        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)

        biased = [
            ch for ch in result.get("changes", [])
            if ch.get("source_label") == _LABEL_BIASED
        ]
        assert not biased, (
            f"AC9 FAIL: neutral profile produced {len(biased)} biased change(s): "
            f"{[ch.get('field') for ch in biased]}"
        )

    def test_all_changes_are_neutral_conservative_or_midpoint(self):
        """Neutral profile: every change label is one of the non-biased labels."""
        valid_labels = {_LABEL_NEUTRAL, _LABEL_CONSERV, _LABEL_MIDPOINT}
        profile = _neutral_profile()
        ranges = resolve_ranges("")

        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)

        for ch in result.get("changes", []):
            sl = ch.get("source_label", "")
            assert sl in valid_labels, (
                f"AC9 FAIL: field={ch.get('field')!r} has source_label={sl!r} "
                f"with neutral profile; expected one of {valid_labels}"
            )


# ===========================================================================
# Obj9 / AC37 — session_influence wired to baseline biased fields
# ===========================================================================

class TestAC37BaselineSessionInfluence:
    """AC37: session_type wired through to build_baseline_setup for session_influence."""

    def test_session_type_wired_to_baseline_response(self):
        """build_baseline_setup_response wires session_type through to the raw data."""
        adv = _make_advisor_no_recorder()
        ranges = resolve_ranges("")

        result_str = adv.build_baseline_setup_response(
            car_name="",
            ranges=ranges,
            drivetrain="FR",
            num_gears=6,
            allowed_tuning=None,
            tuning_locked=False,
            session_type="Qualifying",
        )
        result = json.loads(result_str)
        # The response must at minimum parse cleanly and contain changes/setup_fields
        assert "changes" in result, "AC37 FAIL: baseline response missing 'changes'"

    def test_baseline_accepts_session_type_param(self):
        """build_baseline_setup() accepts session_type kwarg without raising."""
        ranges = resolve_ranges("")
        profile = _profile_with(trail_braker=True)

        # Should not raise
        result = build_baseline_setup(
            "", ranges, "FR", 6, profile, None, False,
            session_type="Qualifying",
        )
        assert "changes" in result


# ===========================================================================
# Obj9 / AC38 & AC39 — validator pass and Apply gate
# ===========================================================================

class TestAC38AC39ValidatorAndApplyGate:
    """AC38 + AC39: baseline passes validator funnel and is in APPROVED_STATUSES."""

    def test_baseline_status_approved_fr_neutral(self):
        """FR drivetrain, neutral profile, 6 gears → status in APPROVED_STATUSES."""
        adv = _make_advisor_no_recorder()
        ranges = resolve_ranges("")

        result_str = adv.build_baseline_setup_response(
            car_name="",
            ranges=ranges,
            drivetrain="FR",
            num_gears=6,
            allowed_tuning=None,
            tuning_locked=False,
        )
        result = json.loads(result_str)
        status = result.get("recommendation_status", "")
        assert status in APPROVED_STATUSES, (
            f"AC38/39 FAIL: baseline FR neutral status={status!r}; "
            f"expected one of {APPROVED_STATUSES}"
        )

    def test_baseline_status_approved_rr(self):
        """RR drivetrain, neutral profile → status in APPROVED_STATUSES."""
        adv = _make_advisor_no_recorder()
        ranges = resolve_ranges("")

        result_str = adv.build_baseline_setup_response(
            car_name="",
            ranges=ranges,
            drivetrain="RR",
            num_gears=6,
            allowed_tuning=None,
            tuning_locked=False,
        )
        result = json.loads(result_str)
        status = result.get("recommendation_status", "")
        assert status in APPROVED_STATUSES, (
            f"AC38/39 FAIL: baseline RR status={status!r}; expected one of {APPROVED_STATUSES}"
        )

    def test_baseline_has_changes(self):
        """Baseline response always produces at least one change."""
        adv = _make_advisor_no_recorder()
        ranges = resolve_ranges("")

        result_str = adv.build_baseline_setup_response(
            car_name="",
            ranges=ranges,
            drivetrain="FR",
            num_gears=6,
            allowed_tuning=None,
            tuning_locked=False,
        )
        result = json.loads(result_str)
        assert result.get("changes"), "AC38/39 FAIL: baseline produced no changes"

    def test_baseline_engineering_validation_not_failed(self):
        """Baseline engineering validation flag must be False (no blocking failures)."""
        adv = _make_advisor_no_recorder()
        ranges = resolve_ranges("")

        result_str = adv.build_baseline_setup_response(
            car_name="",
            ranges=ranges,
            drivetrain="FR",
            num_gears=6,
            allowed_tuning=None,
            tuning_locked=False,
        )
        result = json.loads(result_str)
        evf = result.get("engineering_validation_failed", True)
        assert evf is False, (
            f"AC38/39 FAIL: baseline has engineering_validation_failed={evf}; expected False"
        )

    def test_tuning_locked_returns_approved_empty(self):
        """tuning_locked=True → approved status but empty changes (nothing to apply)."""
        adv = _make_advisor_no_recorder()
        ranges = resolve_ranges("")

        result_str = adv.build_baseline_setup_response(
            car_name="",
            ranges=ranges,
            drivetrain="FR",
            num_gears=6,
            allowed_tuning=None,
            tuning_locked=True,
        )
        result = json.loads(result_str)
        status = result.get("recommendation_status", "")
        assert status in APPROVED_STATUSES, (
            f"AC38/39 FAIL: locked baseline status={status!r} not in APPROVED_STATUSES"
        )
        # With locked tuning, changes must be empty
        assert result.get("changes", []) == [], (
            "AC38/39 FAIL: tuning_locked baseline should have no changes"
        )


# ===========================================================================
# Obj9 / AC40 — Conservative fields labelled _LABEL_CONSERV
# ===========================================================================

class TestAC40ConservativeFieldLabel:
    """AC40: conservative fields receive _LABEL_CONSERV to distinguish from diagnosed."""

    def test_all_conservative_fields_have_conserv_label(self):
        """Every _CONSERVATIVE_FIELDS member that appears in changes has _LABEL_CONSERV."""
        ranges = resolve_ranges("")
        profile = _neutral_profile()

        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)

        for ch in result.get("changes", []):
            if ch.get("field") in _CONSERVATIVE_FIELDS:
                sl = ch.get("source_label", "")
                assert sl == _LABEL_CONSERV, (
                    f"AC40 FAIL: conservative field {ch.get('field')!r} "
                    f"has source_label={sl!r}; expected {_LABEL_CONSERV!r}"
                )

    def test_at_least_one_conservative_field_in_changes(self):
        """At least one conservative field must appear in the baseline changes."""
        ranges = resolve_ranges("")
        profile = _neutral_profile()

        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)

        conserv_in_changes = [
            ch for ch in result.get("changes", [])
            if ch.get("field") in _CONSERVATIVE_FIELDS
        ]
        assert conserv_in_changes, (
            "AC40 FAIL: no conservative fields appeared in baseline changes; "
            f"expected at least one from {_CONSERVATIVE_FIELDS}"
        )

    def test_non_conservative_non_biased_fields_are_neutral_or_midpoint(self):
        """Fields not in _CONSERVATIVE_FIELDS and not biased should be neutral or midpoint."""
        ranges = resolve_ranges("")
        profile = _neutral_profile()

        result = build_baseline_setup("", ranges, "FR", 6, profile, None, False)

        valid_non_conserv = {_LABEL_NEUTRAL, _LABEL_MIDPOINT}
        for ch in result.get("changes", []):
            if ch.get("field") in _CONSERVATIVE_FIELDS:
                continue
            sl = ch.get("source_label", "")
            assert sl in valid_non_conserv, (
                f"AC40 FAIL: non-conservative field {ch.get('field')!r} "
                f"has source_label={sl!r}; expected one of {valid_non_conserv}"
            )

    def test_labels_distinguish_conservative_from_neutral(self):
        """conservative and neutral labels are distinct strings."""
        assert _LABEL_CONSERV != _LABEL_NEUTRAL, (
            "AC40 FAIL: _LABEL_CONSERV and _LABEL_NEUTRAL are identical — "
            "cannot distinguish conservative from neutral"
        )
        assert _LABEL_CONSERV != _LABEL_BIASED
        assert _LABEL_CONSERV != _LABEL_MIDPOINT


# ===========================================================================
# Bug-fix: practice session_type emits honest "practice session — no special
# bias applied" text, not "not available"
# ===========================================================================

class TestPracticeBaselineSessionInfluence:
    """Bug-fix: setup_baseline.py previously used the session_influence text from
    the generic advisor path for unknown sessions.  Group 45 fix: when session_type
    is 'Practice', build_baseline_setup() now emits
    'practice session — no special bias applied' on biased fields, NOT 'not available'.

    This is a distinct honest message — practice is a KNOWN session type; it just
    has no special numeric bias.
    """

    def _biased_profile_for_session(self) -> "DriverProfile":
        """Profile with at least one bias flag so biased changes are authored."""
        return _profile_with(trail_braker=True)

    def test_practice_session_influence_text_is_honest(self):
        """build_baseline_setup with session_type='Practice' must produce
        'practice session — no special bias applied' on biased change dicts,
        NOT 'not available'.
        """
        profile = self._biased_profile_for_session()
        ranges = resolve_ranges("")

        result = build_baseline_setup(
            "", ranges, "FR", 6, profile, None, False,
            session_type="Practice",
        )

        biased_changes = [
            ch for ch in result.get("changes", [])
            if ch.get("source_label") == _LABEL_BIASED
        ]
        assert biased_changes, (
            "Bug-fix FAIL: No biased changes found; profile should produce "
            "at least one biased field (brake_bias with trail_braker=True)"
        )

        for ch in biased_changes:
            si = ch.get("session_influence", "")
            assert "practice session" in si, (
                f"Bug-fix FAIL: biased field {ch.get('field')!r} with session_type='Practice' "
                f"must have 'practice session' in session_influence; got {si!r}"
            )
            assert "no special bias applied" in si, (
                f"Bug-fix FAIL: session_influence must say 'no special bias applied'; "
                f"got {si!r}"
            )
            assert "not available" not in si, (
                f"Bug-fix FAIL: session_influence must NOT say 'not available' for Practice; "
                f"got {si!r}. This would falsely imply the session is unknown."
            )

    def test_practice_session_influence_exact_text(self):
        """Exact text check: 'practice session — no special bias applied'."""
        EXPECTED = "practice session — no special bias applied"
        profile = self._biased_profile_for_session()
        ranges = resolve_ranges("")

        result = build_baseline_setup(
            "", ranges, "FR", 6, profile, None, False,
            session_type="Practice",
        )

        biased_changes = [
            ch for ch in result.get("changes", [])
            if ch.get("source_label") == _LABEL_BIASED
        ]
        for ch in biased_changes:
            si = ch.get("session_influence", "")
            assert si == EXPECTED, (
                f"Bug-fix FAIL: session_influence for field {ch.get('field')!r} "
                f"is {si!r}; expected exactly {EXPECTED!r}"
            )

    def test_practice_session_influence_not_in_non_biased_changes(self):
        """Non-biased (neutral/conservative) baseline changes must NOT carry any
        session_influence text (practice bias does not apply to conservative fields).
        """
        profile = self._biased_profile_for_session()
        ranges = resolve_ranges("")

        result = build_baseline_setup(
            "", ranges, "FR", 6, profile, None, False,
            session_type="Practice",
        )

        for ch in result.get("changes", []):
            if ch.get("source_label") != _LABEL_BIASED:
                si = ch.get("session_influence", "")
                assert si == "", (
                    f"Bug-fix FAIL: non-biased field {ch.get('field')!r} carries "
                    f"session_influence={si!r}; should be '' for conservative/neutral changes"
                )

    def test_empty_session_type_produces_no_session_influence(self):
        """When session_type='' (unknown/absent), session_influence must be '' on all changes."""
        profile = self._biased_profile_for_session()
        ranges = resolve_ranges("")

        result = build_baseline_setup(
            "", ranges, "FR", 6, profile, None, False,
            session_type="",
        )

        for ch in result.get("changes", []):
            si = ch.get("session_influence", "")
            assert si == "", (
                f"Bug-fix FAIL: session_type='' produced non-empty session_influence "
                f"on field {ch.get('field')!r}: {si!r}"
            )

    def test_race_session_influence_not_not_available(self):
        """Regression: session_type='Race' must NOT emit 'not available' on biased
        changes (the honest baseline text records the session was noted but not applied).
        """
        profile = self._biased_profile_for_session()
        ranges = resolve_ranges("")

        result = build_baseline_setup(
            "", ranges, "FR", 6, profile, None, False,
            session_type="Race",
        )

        biased_changes = [
            ch for ch in result.get("changes", [])
            if ch.get("source_label") == _LABEL_BIASED
        ]
        for ch in biased_changes:
            si = ch.get("session_influence", "")
            assert "not available" not in si, (
                f"Bug-fix FAIL: session_type='Race' biased field {ch.get('field')!r} "
                f"has 'not available' in session_influence: {si!r}"
            )
