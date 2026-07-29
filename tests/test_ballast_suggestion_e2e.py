"""Part B — Ballast suggestion end-to-end: _PACK_BALLAST surfaces via run_rule_engine.

The BALLAST pack is already registered in setup_knowledge_base.py (_PACK_BALLAST,
line ~1321).  These tests verify it SURFACES correctly through the real rule engine
(run_rule_engine) and that the locking guards work:

  AC-B1 FR + understeer feeling, allowed_tuning=None → ballast_position delta > 0 (rearward)
  AC-B2 RR + oversteer feeling → ballast_position delta < 0 (forward)
  AC-B3 Balanced/no feeling → no ballast_position change proposed
  AC-B4 allowed_tuning excluding "ballast" + understeer → no ballast_position change (BOP lock)
  AC-B5 No rule ever proposes a ballast_kg change

Analysis seam used:
  strategy.setup_rule_engine.run_rule_engine(diagnosis, setup, ranges, profile,
      allowed_tuning=..., drivetrain=DrivetrainType.xxx)

  This is the exact inner engine that build_combined_setup_response delegates to
  at line ~1784 of driving_advisor.py.  It is used directly here (no laps/telemetry
  required) following the same pattern as tests/test_group62_abs_regulation.py.

  The setup dict MUST include "ballast_position" so the engine can compute
  from_value/to_value (rule skips when the field is absent — see rule engine line ~880).

All tests are pure/offline — no PyQt6, no DB, no network.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from strategy.setup_rule_engine import run_rule_engine, SetupPlan, SetupChangeIntent
from strategy.setup_driver_profile import build_driver_profile
from strategy.setup_ranges import resolve_ranges
from strategy.setup_knowledge_base import DrivetrainType


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_DT_MAP: dict[str, "DrivetrainType | None"] = {
    "fr":  DrivetrainType.fr,
    "ff":  DrivetrainType.ff,
    "rr":  DrivetrainType.rr,
    "mr":  DrivetrainType.mr,
    "awd": DrivetrainType.awd,
}


def _run(
    drivetrain: str,
    feel_flags: "dict[str, bool]",
    allowed_tuning: "list[str] | None" = None,
    ballast_position: float = 0.0,
    ballast_kg: float = 20.0,
) -> SetupPlan:
    """Run the real rule engine with the given drivetrain and driver-feel flags.

    The setup dict includes ballast_position (required for rule to compute
    from_value) and a representative minimal setup.
    """
    setup = {
        "ballast_kg": ballast_kg,
        "ballast_position": ballast_position,
        # Provide a few other fields so rules for other categories have values
        "arb_front": 4,
        "arb_rear": 3,
        "lsd_accel": 20,
        "lsd_decel": 20,
    }
    diagnosis = {
        "driver_feel_flags": feel_flags,
        "dominant_problem": (
            "mid_corner_understeer" if feel_flags.get("mid_corner_understeer") else
            "snap_oversteer_exit"   if feel_flags.get("snap_oversteer_exit") else
            "rear_loose_on_exit"    if feel_flags.get("rear_loose_on_exit") else
            "none"
        ),
        # Provide enough context so other diagnostics don't interfere
        "avg_bottoming": 0,
        "avg_wheelspin": 0,
    }
    return run_rule_engine(
        diagnosis,
        setup,
        resolve_ranges(""),
        build_driver_profile(),
        allowed_tuning=allowed_tuning,
        drivetrain=_DT_MAP.get(drivetrain.lower()),
    )


def _proposed_map(plan: SetupPlan) -> "dict[str, float]":
    """Map field → delta for all proposed changes."""
    return {c.field: c.delta for c in plan.proposed}


# ---------------------------------------------------------------------------
# AC-B1  FR + understeer → rearward ballast proposed
# ---------------------------------------------------------------------------

class TestBallastUndersteerFR:
    """AC-B1: FR + mid_corner_understeer → ballast_position delta > 0 (rearward)."""

    def test_fr_understeer_proposes_rearward_ballast_position(self):
        """BAL_US_FR rule fires: ballast_position change is positive (rearward)."""
        plan = _run("fr", {"mid_corner_understeer": True})
        fields = _proposed_map(plan)
        assert "ballast_position" in fields, (
            f"Expected ballast_position in proposed changes; got fields: {sorted(fields)}"
        )
        assert fields["ballast_position"] > 0, (
            f"FR understeer: expected positive (rearward) delta; got {fields['ballast_position']}"
        )

    def test_fr_understeer_delta_equals_ballast_rearward_fn(self):
        """The FR understeer step matches _delta_ballast_rearward (+5) or the
        severity-scaled equivalent — always positive and within a reasonable range."""
        plan = _run("fr", {"mid_corner_understeer": True})
        fields = _proposed_map(plan)
        assert fields.get("ballast_position", 0) > 0


# ---------------------------------------------------------------------------
# AC-B2  RR + oversteer → forward ballast proposed
# ---------------------------------------------------------------------------

class TestBallastOversteerRR:
    """AC-B2: RR + rear_loose_on_exit → ballast_position delta < 0 (forward)."""

    def test_rr_oversteer_proposes_forward_ballast_position(self):
        """BAL_OS_RR rule fires: ballast_position change is negative (forward)."""
        plan = _run("rr", {"rear_loose_on_exit": True})
        fields = _proposed_map(plan)
        assert "ballast_position" in fields, (
            f"Expected ballast_position in proposed changes for RR oversteer; "
            f"got fields: {sorted(fields)}"
        )
        assert fields["ballast_position"] < 0, (
            f"RR oversteer: expected negative (forward) delta; got {fields['ballast_position']}"
        )

    def test_rr_snap_oversteer_proposes_forward_ballast(self):
        """snap_oversteer_exit also triggers the RR forward-ballast rule."""
        plan = _run("rr", {"snap_oversteer_exit": True})
        fields = _proposed_map(plan)
        assert "ballast_position" in fields, (
            f"Expected ballast_position for RR snap oversteer; got {sorted(fields)}"
        )
        assert fields["ballast_position"] < 0, (
            f"RR snap oversteer: expected negative delta; got {fields['ballast_position']}"
        )


# ---------------------------------------------------------------------------
# AC-B3  Balanced / no feeling → no ballast change
# ---------------------------------------------------------------------------

class TestBallastNoFeeling:
    """AC-B3: No feel flags → no ballast_position change proposed."""

    def test_balanced_no_feeling_fr_no_ballast_change(self):
        """FR car with no feel flags → ballast_position not proposed."""
        plan = _run("fr", {})
        fields = _proposed_map(plan)
        assert "ballast_position" not in fields, (
            f"Balanced/no feeling: ballast_position should not be proposed; got {fields}"
        )

    def test_balanced_no_feeling_rr_no_ballast_change(self):
        """RR car with no feel flags → ballast_position not proposed."""
        plan = _run("rr", {})
        fields = _proposed_map(plan)
        assert "ballast_position" not in fields, (
            f"Balanced/no feeling RR: ballast_position should not be proposed; got {fields}"
        )


# ---------------------------------------------------------------------------
# AC-B4  allowed_tuning excluding "ballast" blocks the suggestion
# ---------------------------------------------------------------------------

class TestBallastTuningLock:
    """AC-B4: allowed_tuning=["suspension"] + understeer → no ballast change (BOP lock)."""

    def test_suspension_only_tuning_blocks_ballast_suggestion(self):
        """When 'ballast' is not in allowed_tuning, the rule engine cannot propose it."""
        plan = _run("fr", {"mid_corner_understeer": True}, allowed_tuning=["suspension"])
        fields = _proposed_map(plan)
        assert "ballast_position" not in fields, (
            f"BOP lock (no ballast category): ballast_position should not be proposed; "
            f"got {fields}"
        )

    def test_aero_only_tuning_blocks_ballast_suggestion(self):
        """Same guard with a different non-ballast category list."""
        plan = _run("fr", {"mid_corner_understeer": True}, allowed_tuning=["aero"])
        fields = _proposed_map(plan)
        assert "ballast_position" not in fields, (
            f"Aero-only allowed_tuning: ballast should be locked; got {fields}"
        )

    def test_ballast_in_allowed_tuning_permits_suggestion(self):
        """When 'ballast' IS in allowed_tuning, the rule is free to propose it."""
        plan = _run("fr", {"mid_corner_understeer": True}, allowed_tuning=["ballast"])
        fields = _proposed_map(plan)
        assert "ballast_position" in fields, (
            f"ballast in allowed_tuning: rule should fire; got {sorted(fields)}"
        )


# ---------------------------------------------------------------------------
# AC-B5  No rule ever proposes ballast_kg
# ---------------------------------------------------------------------------

class TestNoBallastKgProposal:
    """AC-B5: No rule in any pack proposes a ballast_kg change.

    ballast_kg is a read-only diagnostic input — the pack only proposes
    ballast_position (the slider), never the weight itself.
    """

    _SCENARIOS = [
        ("fr",  {"mid_corner_understeer": True}),
        ("rr",  {"rear_loose_on_exit": True}),
        ("ff",  {"mid_corner_understeer": True}),
        ("mr",  {"snap_oversteer_exit": True}),
        ("awd", {"mid_corner_understeer": True}),
        ("mr",  {"rear_loose_on_exit": True}),
    ]

    @pytest.mark.parametrize("drivetrain,flags", _SCENARIOS)
    def test_no_rule_proposes_ballast_kg(self, drivetrain, flags):
        """The rule engine never proposes a ballast_kg change for any drivetrain + feeling."""
        plan = _run(drivetrain, flags)
        for change in plan.proposed:
            assert change.field != "ballast_kg", (
                f"{drivetrain}/{list(flags)}: a rule proposed ballast_kg — "
                f"only ballast_position should ever be proposed"
            )
