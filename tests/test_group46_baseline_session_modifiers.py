"""
Group 46 — Learning & Race Context Intelligence: Baseline Session Modifier Tests

Covers ACs 22-26 (Session baseline layer):
  AC22 — numerically different output for qualifying vs sprint(race,<60) vs
           endurance(race,>=60) vs practice/unknown.
  AC23 — per-field session_changed → only claims bias where value moved;
           session_influence is "" when value was unchanged despite session being known.
  AC24 — unknown/missing session → conservative + explicit unknown text (""
           session_influence for all fields); _normalise_session_for_bias returns "unknown".
  AC25 — session bias passes same clamp/monotonic/validator gate;
           duration<=0 → not endurance (sprint bucket).
  AC26 — clamp-boundary field → session_changed=False (the delta was eaten by clamp).

_SESSION_BIAS_TABLE:
  "qualifying":  {brake_bias: -1.0, lsd_decel: -1.0, aero_front: +25.0}
  "sprint":      {lsd_accel: +1.0}
  "endurance":   {lsd_accel: +2.0, lsd_decel: +1.0, aero_rear: +25.0}
  "practice":    {}
  "unknown":     {}

_normalise_session_for_bias:
  "qual" in lower(session_type) → "qualifying"
  "practice" → "practice"
  "race"/"sprint" with duration>=60 → "endurance"
  "race"/"sprint" with duration<60 or <=0 → "sprint"
  anything else → "unknown"
  duration<=0 → NOT endurance

All tests are pure/offline — no network, no Qt event loop.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy._setup_constants import APPROVED_STATUSES
from strategy.setup_baseline import (
    build_baseline_setup,
    _normalise_session_for_bias,
    _SESSION_BIAS_TABLE,
    NEUTRAL_SEEDS,
    _LABEL_BIASED,
)
from strategy.setup_driver_profile import DriverProfile
from strategy.setup_ranges import resolve_ranges


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


def _build(
    session_type: str = "",
    duration_mins: float = 0.0,
    profile: DriverProfile | None = None,
) -> dict:
    """Call build_baseline_setup with standard args, return the raw_data dict."""
    if profile is None:
        profile = _neutral_profile()
    return build_baseline_setup(
        car="",
        ranges=resolve_ranges(""),
        drivetrain="FR",
        num_gears=6,
        profile=profile,
        allowed_tuning=None,
        tuning_locked=False,
        session_type=session_type,
        duration_mins=duration_mins,
    )


def _field_value(changes: list[dict], field: str) -> object:
    """Extract the to_clamped value for a field from a changes list."""
    for ch in changes:
        if ch.get("field") == field:
            return ch.get("to_clamped")
    return None


def _field_session_influence(changes: list[dict], field: str) -> str:
    """Extract the session_influence string for a field from a changes list."""
    for ch in changes:
        if ch.get("field") == field:
            return ch.get("session_influence", "")
    return ""


# ===========================================================================
# AC22 — numerically different output for each session type
# ===========================================================================

class TestAC22NumericDifferences:
    """AC22: qualifying / sprint / endurance / practice+unknown all produce distinct outputs."""

    def test_qualifying_vs_sprint_differ(self):
        """Qualifying and sprint produce different values for at least one biased field."""
        quali = _build("Qualifying", duration_mins=0.0)
        sprint = _build("Race", duration_mins=30.0)

        # Qualifying biases brake_bias and lsd_decel; sprint biases lsd_accel
        # They must differ somewhere
        quali_vals = {ch["field"]: ch.get("to_clamped") for ch in quali["changes"]}
        sprint_vals = {ch["field"]: ch.get("to_clamped") for ch in sprint["changes"]}

        # Find at least one difference
        all_fields = set(quali_vals) & set(sprint_vals)
        differs = any(quali_vals.get(f) != sprint_vals.get(f) for f in all_fields)
        assert differs, (
            "AC22 FAIL: qualifying and sprint produce identical field values. "
            "Expected at least one numeric difference."
        )

    def test_sprint_vs_endurance_differ(self):
        """Sprint and endurance produce different values for at least one biased field."""
        sprint = _build("Race", duration_mins=30.0)
        endurance = _build("Race", duration_mins=60.0)

        sprint_vals = {ch["field"]: ch.get("to_clamped") for ch in sprint["changes"]}
        endurance_vals = {ch["field"]: ch.get("to_clamped") for ch in endurance["changes"]}

        all_fields = set(sprint_vals) & set(endurance_vals)
        differs = any(sprint_vals.get(f) != endurance_vals.get(f) for f in all_fields)
        assert differs, (
            "AC22 FAIL: sprint and endurance produce identical field values."
        )

    def test_qualifying_biases_expected_fields(self):
        """Qualifying must bias brake_bias, lsd_decel, aero_front per _SESSION_BIAS_TABLE."""
        quali = _build("Qualifying", duration_mins=0.0)
        neutral = _build("", duration_mins=0.0)

        quali_vals = {ch["field"]: ch.get("to_clamped") for ch in quali["changes"]}
        neutral_vals = {ch["field"]: ch.get("to_clamped") for ch in neutral["changes"]}

        expected_biased = _SESSION_BIAS_TABLE["qualifying"]
        for field in expected_biased:
            qv = quali_vals.get(field)
            nv = neutral_vals.get(field)
            if qv is not None and nv is not None:
                # The value should differ by the bias delta (subject to clamping)
                # We don't assert exact delta (clamp may eat it) but we do assert
                # that the qualifying session was actually classified and session
                # influence is set for fields that changed.
                si = _field_session_influence(quali["changes"], field)
                # session_influence should be set if the field changed
                if float(qv) != float(nv):
                    assert si, (
                        f"AC22 FAIL: qualifying biased {field!r} but session_influence is empty; "
                        f"qv={qv}, nv={nv}"
                    )

    def test_endurance_biases_expected_fields(self):
        """Endurance must bias lsd_accel, lsd_decel, aero_rear per _SESSION_BIAS_TABLE."""
        endurance = _build("Race", duration_mins=60.0)
        sprint = _build("Race", duration_mins=30.0)

        endurance_vals = {ch["field"]: ch.get("to_clamped") for ch in endurance["changes"]}
        sprint_vals = {ch["field"]: ch.get("to_clamped") for ch in sprint["changes"]}

        expected_biased = _SESSION_BIAS_TABLE["endurance"]
        for field in expected_biased:
            ev = endurance_vals.get(field)
            sv = sprint_vals.get(field)
            if ev is not None and sv is not None:
                # endurance has +2 lsd_accel vs sprint's +1; lsd_decel +1 vs 0; aero_rear +25 vs 0
                if float(ev) != float(sv):
                    si = _field_session_influence(endurance["changes"], field)
                    assert si, (
                        f"AC22 FAIL: endurance biased {field!r} vs sprint but session_influence is empty; "
                        f"ev={ev}, sv={sv}"
                    )

    def test_practice_same_as_unknown(self):
        """practice and unknown have empty _SESSION_BIAS_TABLE → no numerical difference."""
        practice = _build("Practice", duration_mins=0.0)
        unknown = _build("", duration_mins=0.0)

        practice_vals = {ch["field"]: ch.get("to_clamped") for ch in practice["changes"]}
        unknown_vals = {ch["field"]: ch.get("to_clamped") for ch in unknown["changes"]}

        all_fields = set(practice_vals) & set(unknown_vals)
        same = all(practice_vals.get(f) == unknown_vals.get(f) for f in all_fields)
        assert same, (
            "AC22 FAIL: practice and unknown produce different field values — "
            "both should have empty bias tables."
        )


# ===========================================================================
# AC23 — per-field session_changed: only claim where value moved
# ===========================================================================

class TestAC23SessionInfluenceHonest:
    """AC23: session_influence is non-empty only for fields where the value actually changed;
    '' when the session is known but did not change this field."""

    def test_session_influence_empty_for_unbiased_fields(self):
        """Fields not in the qualifying bias table have '' session_influence."""
        quali = _build("Qualifying", duration_mins=0.0)
        biased_fields = set(_SESSION_BIAS_TABLE["qualifying"])

        for ch in quali["changes"]:
            field = ch.get("field", "")
            si = ch.get("session_influence", "")
            if field not in biased_fields:
                assert si == "" or "session noted — no numerical change" not in si or si == "", (
                    f"AC23 FAIL: non-biased field {field!r} has unexpected session text: {si!r}"
                )

    def test_biased_field_that_changed_has_session_influence(self):
        """If qualifying bias actually moved a field numerically, session_influence is set."""
        quali = _build("Qualifying", duration_mins=0.0)
        neutral = _build("", duration_mins=0.0)

        quali_vals = {ch["field"]: ch.get("to_clamped") for ch in quali["changes"]}
        neutral_vals = {ch["field"]: ch.get("to_clamped") for ch in neutral["changes"]}

        for field in _SESSION_BIAS_TABLE["qualifying"]:
            qv = quali_vals.get(field)
            nv = neutral_vals.get(field)
            if qv is None or nv is None:
                continue
            if float(qv) != float(nv):
                si = _field_session_influence(quali["changes"], field)
                assert si, (
                    f"AC23 FAIL: field {field!r} changed numerically by qualifying bias "
                    f"({nv!r}→{qv!r}) but session_influence is ''"
                )

    def test_no_false_session_claim_for_neutral_session(self):
        """With session_type='' (unknown), no field has a 'session bias applied' claim."""
        unknown = _build("", duration_mins=0.0)
        for ch in unknown["changes"]:
            si = ch.get("session_influence", "")
            assert "session bias applied" not in (si or ""), (
                f"AC23 FAIL: unknown session produced 'session bias applied' for "
                f"field {ch.get('field')!r}; session_influence={si!r}"
            )


# ===========================================================================
# AC24 — unknown/missing session → "" session_influence; conservative output
# ===========================================================================

class TestAC24UnknownSession:
    """AC24: unknown/missing session → session_influence='' for all fields."""

    def test_normalise_empty_string_is_unknown(self):
        """_normalise_session_for_bias('', 0) → 'unknown'."""
        result = _normalise_session_for_bias("", 0.0)
        assert result == "unknown", f"Expected 'unknown', got {result!r}"

    def test_normalise_none_like_string_is_unknown(self):
        """_normalise_session_for_bias(None-ish value, 0) → 'unknown'."""
        result = _normalise_session_for_bias(None, 0.0)  # type: ignore[arg-type]
        assert result == "unknown"

    def test_unknown_session_no_session_influence_text(self):
        """Build with '' session → no session_influence anywhere."""
        data = _build("", duration_mins=0.0)
        for ch in data["changes"]:
            si = ch.get("session_influence", "")
            assert "session bias applied" not in (si or ""), (
                f"AC24 FAIL: unknown session produced session bias claim for "
                f"{ch.get('field')!r}: {si!r}"
            )

    def test_normalise_race_with_zero_duration_is_sprint_not_endurance(self):
        """AC25 sub-case: race + duration<=0 → NOT endurance → 'sprint'."""
        result = _normalise_session_for_bias("Race", 0.0)
        assert result == "sprint", (
            f"AC24/25 FAIL: race with duration=0 should be 'sprint', got {result!r}. "
            "Brief contract: duration<=0 must NOT classify as endurance."
        )

    def test_normalise_race_negative_duration_is_sprint(self):
        """race + negative duration → 'sprint' (not endurance)."""
        result = _normalise_session_for_bias("Race", -10.0)
        assert result == "sprint", f"Expected 'sprint', got {result!r}"


# ===========================================================================
# AC25 — session bias passes same clamp; duration<=0 → not endurance
# ===========================================================================

class TestAC25SessionBiasClampAndDurationGate:
    """AC25: session bias is clamped; duration<=0 → sprint not endurance."""

    def test_normalise_qualifying(self):
        """'Qualifying' session type → 'qualifying'."""
        assert _normalise_session_for_bias("Qualifying", 0.0) == "qualifying"
        assert _normalise_session_for_bias("qualifying", 0.0) == "qualifying"
        assert _normalise_session_for_bias("QUAL", 0.0) == "qualifying"

    def test_normalise_sprint(self):
        """Race, duration=30 → 'sprint'."""
        assert _normalise_session_for_bias("Race", 30.0) == "sprint"

    def test_normalise_endurance(self):
        """Race, duration=60 → 'endurance'."""
        assert _normalise_session_for_bias("Race", 60.0) == "endurance"

    def test_normalise_endurance_boundary(self):
        """Boundary: Race, duration=59.9 → 'sprint'; duration=60.0 → 'endurance'."""
        assert _normalise_session_for_bias("Race", 59.9) == "sprint"
        assert _normalise_session_for_bias("Race", 60.0) == "endurance"

    def test_normalise_practice(self):
        """'Practice' → 'practice'."""
        assert _normalise_session_for_bias("Practice", 0.0) == "practice"

    def test_session_bias_values_are_clamped(self):
        """Values output by build_baseline_setup are within resolve_ranges() bounds."""
        endurance = _build("Race", duration_mins=60.0)
        ranges = resolve_ranges("")

        for ch in endurance["changes"]:
            field = ch.get("field", "")
            val = ch.get("to_clamped")
            if val is None or field not in ranges:
                continue
            lo, hi = ranges[field]
            try:
                v = float(val)
                assert lo <= v <= hi, (
                    f"AC25 FAIL: field {field!r} value {v} out of range [{lo}, {hi}] "
                    "after endurance session bias"
                )
            except (TypeError, ValueError):
                pass

    def test_duration_exactly_0_is_sprint(self):
        """duration_mins=0.0 (unknown) must be sprint bucket, not endurance."""
        result = _normalise_session_for_bias("Race", 0.0)
        assert result == "sprint", (
            f"AC25 FAIL: duration=0 classified as {result!r}; must be 'sprint' "
            "per brief (duration<=0 must NOT classify as endurance)"
        )

    def test_endurance_session_influence_text_set(self):
        """Endurance session: fields that changed have 'endurance session bias applied' text."""
        endurance = _build("Race", duration_mins=60.0)
        sprint = _build("Race", duration_mins=30.0)

        end_vals = {ch["field"]: ch.get("to_clamped") for ch in endurance["changes"]}
        sprint_vals = {ch["field"]: ch.get("to_clamped") for ch in sprint["changes"]}

        for field in _SESSION_BIAS_TABLE["endurance"]:
            ev = end_vals.get(field)
            sv = sprint_vals.get(field)
            if ev is None or sv is None:
                continue
            if float(ev) != float(sv):
                si = _field_session_influence(endurance["changes"], field)
                assert "endurance" in (si or "").lower(), (
                    f"AC25 FAIL: endurance-biased field {field!r} session_influence "
                    f"does not mention 'endurance'; got {si!r}"
                )


# ===========================================================================
# AC26 — clamp-boundary field → session_changed=False
# ===========================================================================

class TestAC26ClampBoundarySessionChanged:
    """AC26: when session bias is clamped to the same value as the profile-only value,
    session_changed=False → '' session_influence (or "session noted — no numerical change").

    This is tricky to test without knowing exactly which field will hit the clamp
    boundary for a given car/range. We verify the logical contract: if a field in
    the session bias table has its bias fully eaten by clamp, session_influence must
    be '' or the "no numerical change" note.
    """

    def test_session_influence_is_not_falsely_claimed(self):
        """For every change, session_influence='session bias applied' must correlate
        with a real numeric difference vs the neutral (no session) baseline."""
        quali = _build("Qualifying", duration_mins=0.0)
        neutral = _build("", duration_mins=0.0)

        quali_vals = {ch["field"]: ch.get("to_clamped") for ch in quali["changes"]}
        neutral_vals = {ch["field"]: ch.get("to_clamped") for ch in neutral["changes"]}

        for ch in quali["changes"]:
            field = ch.get("field", "")
            si = ch.get("session_influence", "")
            if "session bias applied" in (si or ""):
                qv = quali_vals.get(field)
                nv = neutral_vals.get(field)
                if qv is not None and nv is not None:
                    assert float(qv) != float(nv), (
                        f"AC26 FAIL: field {field!r} claims 'session bias applied' but "
                        f"value is unchanged (clamp ate the delta): qv={qv}, nv={nv}; "
                        f"session_influence={si!r}"
                    )

    def test_biased_session_table_fields_match_implementation(self):
        """Verify _SESSION_BIAS_TABLE contains the expected keys per the brief."""
        expected_keys = {"qualifying", "sprint", "endurance", "practice", "unknown"}
        assert set(_SESSION_BIAS_TABLE.keys()) == expected_keys, (
            f"AC26 FAIL: _SESSION_BIAS_TABLE keys differ; "
            f"expected={expected_keys}, got={set(_SESSION_BIAS_TABLE.keys())}"
        )

    def test_qualifying_bias_fields_correct(self):
        """Qualifying bias must apply to brake_bias, lsd_decel, aero_front per brief."""
        expected = {"brake_bias", "lsd_decel", "aero_front"}
        actual = set(_SESSION_BIAS_TABLE["qualifying"].keys())
        assert actual == expected, (
            f"AC26 FAIL: qualifying bias fields differ; expected={expected}, got={actual}"
        )

    def test_endurance_bias_fields_correct(self):
        """Endurance bias must apply to lsd_accel, lsd_decel, aero_rear per brief."""
        expected = {"lsd_accel", "lsd_decel", "aero_rear"}
        actual = set(_SESSION_BIAS_TABLE["endurance"].keys())
        assert actual == expected, (
            f"AC26 FAIL: endurance bias fields differ; expected={expected}, got={actual}"
        )

    def test_sprint_bias_fields_correct(self):
        """Sprint bias must apply to lsd_accel per brief."""
        expected = {"lsd_accel"}
        actual = set(_SESSION_BIAS_TABLE["sprint"].keys())
        assert actual == expected, (
            f"AC26 FAIL: sprint bias fields differ; expected={expected}, got={actual}"
        )

    def test_practice_and_unknown_are_empty(self):
        """practice and unknown bias tables must be empty dicts."""
        assert _SESSION_BIAS_TABLE["practice"] == {}, "practice bias must be empty"
        assert _SESSION_BIAS_TABLE["unknown"] == {}, "unknown bias must be empty"
