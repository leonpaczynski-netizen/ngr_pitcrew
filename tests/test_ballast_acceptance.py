"""Acceptance tests — Ballast-aware effective weight distribution (gap-fill).

This file fills the GAPS that are NOT covered by the existing suites listed below.
No existing test is duplicated.

GAPS FILLED HERE
================
A7  Per-discipline: a race sheet with ballast_kg > 0 produces different springs
    than a qualifying sheet with ballast_kg == 0 in the same session context.
    Proven via calls to DrivingAdvisor.build_baseline_setup_response using the
    appropriate session_type for each discipline.

W1→service seam: SetupService._generate_baseline passes SetupInputs.ballast_kg
    and SetupInputs.ballast_position to the advisor call unchanged.
    Proven with a recording fake advisor (same pattern as test_setup_service.py).

EXISTING COVERAGE (NOT DUPLICATED)
===================================
A1  zero kg = byte-identical no-op (front_hz, rear_hz, reasons)
    → TestBallastAdjustment::test_zero_ballast_exact_noop_fr
    → TestBallastAdjustment::test_position_alone_without_kg_is_noop
    → TestBallastIntegration::test_zero_ballast_kg_is_byte_identical_to_no_ballast

A2  sign locked: positive pos (REAR) lowers front fraction
    → TestBallastAdjustment::test_rear_ballast_fr_raises_rear_hz
    → TestBallastAdjustment::test_front_ballast_rr_raises_front_hz
    → TestBallastAdjustment::test_ballast_front_frac_pos_plus50_is_full_rear_observable
    → TestBallastAdjustment::test_ballast_front_frac_pos_minus50_is_full_front_observable

A3  effective fraction clamped (0.30–0.70) + drivetrain invariants survive ballast
    → TestBallastAdjustment::test_heavy_ballast_max_pos_stays_in_race_band_and_gt7
    → TestBallastAdjustment::test_rr_rear_hz_gte_front_hz_with_modest_rear_ballast
    → TestBallastAdjustment::test_ff_front_hz_gte_rear_hz_with_modest_front_ballast
    → TestFrontRearSplit (no-ballast defaults)

A4  deterministic / pure; new params default 0.0 → existing callers unaffected
    → TestBallastAdjustment::test_determinism_same_ballast_inputs_identical
    → TestAC1PurityNoFileRead (test_spring_frequency_acceptance.py)

A5  missing/zero car mass with ballast → base fraction, no crash
    → TestBallastAdjustment::test_zero_car_mass_with_ballast_same_as_no_ballast
    → TestBallastAdjustment::test_zero_weight_kg_with_ballast_same_as_no_ballast

A6  reason string only when |shift| >= 0.005
    → TestBallastAdjustment::test_reason_contains_effective_front_when_shift_gte_0005
    → TestBallastAdjustment::test_reason_unchanged_when_kg_tiny_shift_below_threshold
    → TestBallastAdjustment::test_reason_unchanged_when_kg_zero

B1  FR + understeer → rearward ballast_position proposed
    → TestBallastUndersteerFR (test_ballast_suggestion_e2e.py)

B2  RR + oversteer → forward ballast_position proposed
    → TestBallastOversteerRR (test_ballast_suggestion_e2e.py)

B3  balanced/no feeling → no ballast suggestion
    → TestBallastNoFeeling (test_ballast_suggestion_e2e.py)

B4  allowed_tuning excludes "ballast" → no suggestion
    → TestBallastTuningLock (test_ballast_suggestion_e2e.py)

B5  no rule proposes ballast_kg
    → TestNoBallastKgProposal (test_ballast_suggestion_e2e.py)

W1  bridge _build_inputs reads sheet ballast into SetupInputs
    → TestBuildInputsBallast (test_live_shell_bridge.py)

All tests are Qt-free and offline (no QApplication, no network, no GT7).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from strategy.setup_ranges import resolve_ranges


# ---------------------------------------------------------------------------
# Shared builder for the real DrivingAdvisor
# ---------------------------------------------------------------------------

def _make_advisor():
    from strategy.driving_advisor import DrivingAdvisor
    recorder = SimpleNamespace(
        recent_laps=lambda n: [],
        last_lap=lambda: None,
        best_lap=lambda: None,
    )
    tracker = SimpleNamespace()
    return DrivingAdvisor(recorder, tracker, {})


def _advisor_springs(
    *,
    ballast_kg: float = 0.0,
    ballast_position: float = 0.0,
    session_type: str = "Race Setup",
) -> dict:
    """Run the real advisor for the Porsche 911 RSR (RR) and return setup_fields."""
    adv = _make_advisor()
    raw = adv.build_baseline_setup_response(
        car_name="Porsche 911 RSR (991) '17",
        ranges=resolve_ranges(""),   # generic unclamped 1–20 Hz range so rounding shows
        drivetrain="rr",
        num_gears=6,
        allowed_tuning=None,
        tuning_locked=False,
        session_type=session_type,
        ballast_kg=ballast_kg,
        ballast_position=ballast_position,
    )
    return json.loads(raw).get("setup_fields", {})


# ===========================================================================
# A7 — Per-discipline: race(ballast) vs quali(no-ballast) differ automatically
# ===========================================================================

class TestA7PerDisciplineBallast:
    """A7: the race sheet carries ballast; the qualifying sheet does not.
    Each call to the advisor with the appropriate session_type and ballast
    context produces different spring values — no per-discipline override is
    needed from the caller.

    The Porsche 911 RSR (991) '17 is an RR car (base front-fraction ≈ 0.38).
    60 kg at ballast_position=+30 (rear) lowers the effective front fraction
    further from 0.38, widening the rear-heavier split and raising springs_rear.
    With generic (unclamped, 1–20 Hz) ranges the ~0.04 Hz delta survives
    1-dp quantisation.
    """

    def test_race_with_rear_ballast_springs_differ_from_race_without(self):
        """A7 prerequisite: ballast alone changes the race spring output."""
        sf_no_bal  = _advisor_springs(ballast_kg=0.0, session_type="Race Setup")
        sf_with_bal = _advisor_springs(
            ballast_kg=60.0, ballast_position=30.0, session_type="Race Setup"
        )
        rear_no  = sf_no_bal.get("springs_rear")
        rear_bal = sf_with_bal.get("springs_rear")
        assert rear_no  is not None, "springs_rear absent from no-ballast race response"
        assert rear_bal is not None, "springs_rear absent from ballast race response"
        assert rear_bal != rear_no, (
            f"Race+rear-ballast springs_rear ({rear_bal}) should differ from "
            f"Race+no-ballast ({rear_no}); effective-fraction shift not visible after "
            f"rounding — check ballast_kg magnitude or range configuration."
        )

    def test_race_with_rear_ballast_differs_from_qualifying_without_ballast(self):
        """A7 end-to-end: one 'session', two discipline paths, naturally different output.

        Race discipline: ballast_kg=60, ballast_position=+30 → rear heavier → rear stiffer.
        Qualifying discipline: ballast_kg=0 → no ballast effect, but discipline factor
        ×1.10 raises springs across the board.

        The two effects (ballast shift vs qualifying stiffness) act on different axes:
        ballast changes the front/rear SPLIT; the qualifying factor scales both uniformly.
        The resulting springs_rear values must therefore differ between the paths.
        """
        sf_race_bal = _advisor_springs(
            ballast_kg=60.0, ballast_position=30.0, session_type="Race Setup"
        )
        sf_quali_no = _advisor_springs(
            ballast_kg=0.0, ballast_position=0.0, session_type="Qualifying Setup"
        )
        rear_race = sf_race_bal.get("springs_rear")
        rear_quali = sf_quali_no.get("springs_rear")
        assert rear_race is not None, "springs_rear absent from race+ballast response"
        assert rear_quali is not None, "springs_rear absent from qualifying+no-ballast response"
        assert rear_race != rear_quali, (
            f"Race+ballast springs_rear ({rear_race}) must differ from "
            f"Qualifying+no-ballast springs_rear ({rear_quali}) — both the ballast shift "
            f"and the qualifying stiffness factor change the spring values."
        )

    def test_qualifying_springs_stiffer_than_race_at_zero_ballast(self):
        """A7 sanity check: the qualifying stiffness factor (×1.10) survives the
        full advisor call chain for the Porsche RSR — this is the discipline shape
        that A7 builds on (the race+ballast change adds on top of this foundation)."""
        sf_race  = _advisor_springs(ballast_kg=0.0, session_type="Race Setup")
        sf_quali = _advisor_springs(ballast_kg=0.0, session_type="Qualifying Setup")
        front_race  = sf_race.get("springs_front")
        front_quali = sf_quali.get("springs_front")
        assert front_quali is not None, "springs_front absent from qualifying response"
        assert front_race  is not None, "springs_front absent from race response"
        assert front_quali >= front_race, (
            f"Qualifying springs_front ({front_quali}) should be >= race ({front_race}) "
            f"because the qualifying stiffness factor ×1.10 is always applied."
        )

    def test_large_front_ballast_on_race_differs_from_no_ballast(self):
        """A7 direction check for FRONT ballast: 200 kg at pos=-50 (full front)
        on an RR car shifts the effective front fraction far enough that the 1-dp
        quantised springs_front value visible in setup_fields changes.

        60 kg at pos=-30 shifts frac by only ~0.02, which after derive_spring_frequencies'
        2-dp round then build_baseline_setup's 1-dp round may collapse to the same
        output value — so a larger delta is used here.  The unit-level test
        test_spring_frequencies.py::TestBallastAdjustment::test_front_ballast_rr_raises_front_hz
        already covers the 50-kg case at 2-dp resolution.
        """
        sf_no_bal   = _advisor_springs(ballast_kg=0.0, session_type="Race Setup")
        sf_front_bal = _advisor_springs(
            ballast_kg=200.0, ballast_position=-50.0, session_type="Race Setup"
        )
        front_no  = sf_no_bal.get("springs_front")
        front_bal = sf_front_bal.get("springs_front")
        assert front_no  is not None, "springs_front absent from no-ballast response"
        assert front_bal is not None, "springs_front absent from front-ballast response"
        assert front_bal > front_no, (
            f"RR + 200 kg full-front ballast: springs_front ({front_bal}) should be > "
            f"no-ballast springs_front ({front_no}) — effective front fraction is pulled "
            f"from the RR prior toward 0.70 (clamp ceiling)."
        )


# ===========================================================================
# W1→service seam — SetupInputs.ballast_* flows through _generate_baseline
# ===========================================================================

class _RecordingAdvisor:
    """Minimal fake advisor recording every build_baseline_setup_response call.

    Returns a minimal valid JSON response so SetupService._generate_baseline
    succeeds and build_initial_setup reports ok=True.
    """

    _RESPONSE = json.dumps({
        "setup_fields": {
            "springs_front": 5.8, "springs_rear": 6.2,
            "arb_front": 4,       "arb_rear": 3,
        }
    })

    def __init__(self):
        self.calls: list = []

    def build_baseline_setup_response(self, **kw):
        self.calls.append(dict(kw))
        return self._RESPONSE


def _make_svc_with_ballast(tmp_path, ballast_kg: float, ballast_position: float):
    """Return (SetupService, _RecordingAdvisor) wired with the given ballast inputs."""
    from services.setup_service import SetupInputs, SetupService
    from services.setup_store import SetupSheetStore

    advisor = _RecordingAdvisor()
    store   = SetupSheetStore(str(tmp_path / "sheets.json"))
    inp = SetupInputs(
        car="Porsche 911 RSR (991) '17",
        track="Fuji International Speedway",
        layout="full_course",
        drivetrain="rr",
        num_gears=6,
        ranges=resolve_ranges(""),
        allowed_tuning=None,
        tuning_locked=False,
        ballast_kg=ballast_kg,
        ballast_position=ballast_position,
    )
    svc = SetupService(
        store=store,
        advisor=advisor,
        inputs_provider=lambda: inp,
    )
    return svc, advisor


class TestW1ServiceSeam:
    """SetupService._generate_baseline passes SetupInputs.ballast_kg and
    ballast_position to the advisor call without modification.

    This closes the seam between W1 (bridge → SetupInputs) and the
    derive_spring_frequencies call inside build_baseline_setup_response.
    The bridge half is already proven in
    test_live_shell_bridge.py::TestBuildInputsBallast; this class proves
    the service half.

    Pattern follows test_setup_service.py::TestBuildInitialSetup —
    a recording fake advisor captures every kwarg passed to
    build_baseline_setup_response.
    """

    def test_nonzero_ballast_kg_reaches_advisor_unmodified(self, tmp_path):
        """SetupInputs(ballast_kg=60, ballast_position=30) → every advisor call
        receives exactly those values."""
        svc, adv = _make_svc_with_ballast(tmp_path, ballast_kg=60.0,
                                           ballast_position=30.0)
        result = svc.build_initial_setup()
        assert result.ok, f"build_initial_setup failed unexpectedly: {result}"
        # build_initial_setup calls _generate_baseline for both "race" and "qualifying"
        assert adv.calls, "No advisor calls recorded — _generate_baseline not reached."
        for call in adv.calls:
            assert call.get("ballast_kg") == 60.0, (
                f"Expected ballast_kg=60.0 in advisor call; got {call.get('ballast_kg')!r}"
            )
            assert call.get("ballast_position") == 30.0, (
                f"Expected ballast_position=30.0 in advisor call; "
                f"got {call.get('ballast_position')!r}"
            )

    def test_zero_ballast_kg_passes_zero_not_none(self, tmp_path):
        """SetupInputs(ballast_kg=0) → advisor receives ballast_kg=0.0.

        Zero is the no-op sentinel — the advisor must receive it so that the
        exact-no-op guard inside derive_spring_frequencies fires correctly.
        """
        svc, adv = _make_svc_with_ballast(tmp_path, ballast_kg=0.0,
                                           ballast_position=25.0)
        result = svc.build_initial_setup()
        assert result.ok, f"build_initial_setup failed unexpectedly: {result}"
        assert adv.calls, "No advisor calls recorded."
        for call in adv.calls:
            assert call.get("ballast_kg") == 0.0, (
                f"Expected ballast_kg=0.0; got {call.get('ballast_kg')!r}"
            )

    def test_negative_ballast_position_passes_through_unmodified(self, tmp_path):
        """Front ballast (negative position) is NOT sign-flipped by the service.

        The GT7 convention is −50=full-front, +50=full-rear.  The service must
        pass the raw signed value from SetupInputs to the advisor so that
        derive_spring_frequencies applies the correct direction.
        """
        svc, adv = _make_svc_with_ballast(tmp_path, ballast_kg=80.0,
                                           ballast_position=-20.0)
        result = svc.build_initial_setup()
        assert result.ok, f"build_initial_setup failed unexpectedly: {result}"
        assert adv.calls, "No advisor calls recorded."
        for call in adv.calls:
            assert call.get("ballast_position") == -20.0, (
                f"Negative ballast_position must be passed through unchanged; "
                f"got {call.get('ballast_position')!r}"
            )
            assert call.get("ballast_kg") == 80.0, (
                f"Expected ballast_kg=80.0; got {call.get('ballast_kg')!r}"
            )

    def test_both_race_and_qualifying_calls_receive_same_ballast(self, tmp_path):
        """_generate_baseline is called for both disciplines using the same
        SetupInputs, so both advisor calls receive identical ballast values.

        (The per-discipline differentiation comes from the SHEET's ballast field —
        which is what the bridge reads — not from separate SetupInputs instances.
        This test verifies that the service does not strip or alter the value
        between the two calls.)
        """
        svc, adv = _make_svc_with_ballast(tmp_path, ballast_kg=50.0,
                                           ballast_position=15.0)
        svc.build_initial_setup()
        session_types = [c.get("session_type") for c in adv.calls]
        ballast_kgs   = [c.get("ballast_kg") for c in adv.calls]
        assert "Race Setup" in session_types,       "Race discipline call not found."
        assert "Qualifying Setup" in session_types, "Qualifying discipline call not found."
        assert all(kg == 50.0 for kg in ballast_kgs), (
            f"ballast_kg must be 50.0 in every call; got {ballast_kgs}"
        )
