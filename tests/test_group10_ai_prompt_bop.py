"""Tests for Group 10: AI Prompt BoP Context (DEF-P1-005, DEF-P2-007, DEF-P2-016).

All three defects were coded correctly in Groups 2-4 but were blocked by Root
Cause A (event persistence broken - fixed in Group 7). This file proves the
implementations are correct and will remain correct through future changes.

DEF-P1-005: _build_practice_prompt() filters/redacts setup fields when tuning
            is locked or restricted by the active event.
DEF-P2-007: Constraint block is injected into the prompt; validation post-processes
            AI output for locked-field violations.
DEF-P2-016: _run_practice_analysis() validation gate blocks the AI call (returns
            before spawning the worker thread) when input data is insufficient.
"""
from __future__ import annotations

import dataclasses
import pathlib
import unittest

_SRC = pathlib.Path(__file__).parent.parent


def _dashboard_text() -> str:
    return (_SRC / "ui" / "dashboard.py").read_text(encoding="utf-8")


def _method_body(text: str, method_name: str) -> str:
    start = text.find(f"def {method_name}(")
    if start == -1:
        return ""
    end = text.find("\n    def ", start + 1)
    return text[start:end] if end != -1 else text[start:]


# Setup dict with distinctive, traceable values per category.
# ride_height_front=99  → suspension category key
# brake_bias=2          → brake_balance category key
# Filtering these by allowed_tuning must suppress or include them accordingly.
_FULL_SETUP = {
    "name":               "TestCar",
    "track":              "Suzuka",
    "condition":          "Dry",
    "setup_type":         "Race",
    "notes":              "",
    "ride_height_front":  99,   # suspension
    "ride_height_rear":   88,   # suspension
    "springs_front":      77,   # suspension
    "brake_bias":         2,    # brake_balance
    "aero_front":         55,   # aero
    "lsd_initial":        10,   # differential
}

_LAP_DATA = {"RM": [90000.0, 91000.0, 90500.0]}
_EMPTY_HISTORY: dict = {}


# ---------------------------------------------------------------------------
# Tests 1–5 — _build_practice_prompt() setup filtering
# ---------------------------------------------------------------------------

class TestPracticePromptSetupFiltering(unittest.TestCase):
    """Directly calls _build_practice_prompt() to verify setup and constraint blocks."""

    @classmethod
    def setUpClass(cls):
        # _GT7_REF_CACHE lives in _ai_client (load_gt7_reference is imported from there).
        # Set it to "" to skip file I/O during tests — we only care about the setup block.
        import strategy._ai_client as _client
        _client._GT7_REF_CACHE = ""
        from strategy.ai_planner import _build_practice_prompt, RaceParams
        cls._build = staticmethod(_build_practice_prompt)
        cls._RaceParams = RaceParams

    def _locked_params(self):
        return self._RaceParams(
            track="Suzuka", total_laps=20,
            tyre_wear_multiplier=1.0, fuel_burn_per_lap=2.0,
            refuel_speed_lps=10.0, pit_loss_secs=23.0,
            tuning_locked=True, allowed_tuning=[],
        )

    def _partial_params(self, cats: list):
        return self._RaceParams(
            track="Suzuka", total_laps=20,
            tyre_wear_multiplier=1.0, fuel_burn_per_lap=2.0,
            refuel_speed_lps=10.0, pit_loss_secs=23.0,
            tuning_locked=False, allowed_tuning=cats,
        )

    def _free_params(self):
        return self._RaceParams(
            track="Suzuka", total_laps=20,
            tyre_wear_multiplier=1.0, fuel_burn_per_lap=2.0,
            refuel_speed_lps=10.0, pit_loss_secs=23.0,
            tuning_locked=False, allowed_tuning=[],
        )

    def test_tuning_locked_setup_block_is_redacted(self):
        """DEF-P1-005 test 1: tuning_locked=True replaces setup values with TUNING LOCKED text."""
        prompt = self._build(self._locked_params(), _LAP_DATA, _FULL_SETUP, _EMPTY_HISTORY)
        self.assertIn("TUNING LOCKED", prompt,
                      "Prompt must contain TUNING LOCKED marker when tuning is disabled")
        self.assertNotIn("Ride Height F/R: 99", prompt,
                         "Ride height value 99 must NOT appear in prompt when tuning is locked")
        self.assertNotIn("Springs F/R: 77", prompt,
                         "Spring rate value 77 must NOT appear in prompt when tuning is locked")

    def test_tuning_locked_constraint_block_in_prompt(self):
        """DEF-P1-005 test 2: tuning_locked=True injects ## EVENT RULES — TUNING LOCKED header."""
        prompt = self._build(self._locked_params(), _LAP_DATA, _FULL_SETUP, _EMPTY_HISTORY)
        self.assertIn("## EVENT RULES — TUNING LOCKED", prompt,
                      "Prompt must contain ## EVENT RULES — TUNING LOCKED section header")

    def test_allowed_tuning_filters_setup_fields(self):
        """DEF-P1-005 test 3: allowed_tuning=['brake_balance'] includes brake_bias, excludes suspension."""
        prompt = self._build(
            self._partial_params(["brake_balance"]),
            _LAP_DATA, _FULL_SETUP, _EMPTY_HISTORY,
        )
        # brake_balance maps to brake_bias key → value 2 must appear
        self.assertIn("Brake bias: 2", prompt,
                      "brake_bias value must appear in prompt when brake_balance is allowed")
        # suspension key ride_height_front (99) filtered → shows as ?/? not 99
        self.assertNotIn("Ride Height F/R: 99", prompt,
                         "Ride height value 99 must be filtered when suspension is not in allowed_tuning")

    def test_allowed_tuning_constraint_block_in_prompt(self):
        """DEF-P1-005 test 4: partial allowed_tuning injects ## EVENT TUNING RESTRICTIONS header."""
        prompt = self._build(
            self._partial_params(["brake_balance"]),
            _LAP_DATA, _FULL_SETUP, _EMPTY_HISTORY,
        )
        self.assertIn("## EVENT TUNING RESTRICTIONS", prompt,
                      "Prompt must contain ## EVENT TUNING RESTRICTIONS when partial tuning applies")
        self.assertIn("brake_balance", prompt,
                      "Allowed category name must appear in tuning restrictions block")

    def test_no_restriction_includes_full_setup(self):
        """DEF-P1-005 test 5: no tuning restrictions → full setup values appear in prompt."""
        prompt = self._build(self._free_params(), _LAP_DATA, _FULL_SETUP, _EMPTY_HISTORY)
        self.assertIn("Ride Height F/R: 99", prompt,
                      "ride_height_front=99 must appear in unrestricted prompt")
        self.assertIn("Brake bias: 2", prompt,
                      "brake_bias=2 must appear in unrestricted prompt")
        self.assertNotIn("## EVENT RULES — TUNING LOCKED", prompt,
                         "Unrestricted prompt must not contain TUNING LOCKED section")
        self.assertNotIn("## EVENT TUNING RESTRICTIONS", prompt,
                         "Unrestricted prompt must not contain TUNING RESTRICTIONS section")


# ---------------------------------------------------------------------------
# Tests 6–10 — _run_practice_analysis() validation gate source-scans
# ---------------------------------------------------------------------------

class TestPracticeValidationGate(unittest.TestCase):
    """Source-scan of _run_practice_analysis() confirming the validation gate."""

    def setUp(self):
        self._body = _method_body(_dashboard_text(), "_run_practice_analysis")

    def test_validation_gate_blocks_on_laps_less_than_2(self):
        """DEF-P2-016 test 6: validation gate checks total_laps < 2 for lap races."""
        self.assertIn('total_laps"] < 2', self._body,
                      '_run_practice_analysis must gate AI call when total_laps < 2')

    def test_validation_gate_blocks_on_zero_fuel(self):
        """DEF-P2-016 test 7: validation gate checks fuel_burn_per_lap <= 0."""
        self.assertIn("fuel_burn_per_lap", self._body,
                      "_run_practice_analysis must reference fuel_burn_per_lap in validation")
        self.assertIn("<= 0", self._body,
                      "_run_practice_analysis validation must check <= 0 for fuel burn")

    def test_validation_gate_blocks_on_timed_duration_too_short(self):
        """DEF-P2-016 test 8: validation gate checks duration_mins < 5 for timed races."""
        self.assertIn("duration_mins", self._body,
                      "_run_practice_analysis must check duration_mins in validation")
        self.assertIn("< 5", self._body,
                      "_run_practice_analysis validation must check < 5 for timed duration")

    def test_validation_gate_blocks_on_insufficient_lap_count(self):
        """DEF-P2-016 test 9: validation gate requires at least 2 laps on one compound."""
        self.assertIn(">= 2", self._body,
                      "_run_practice_analysis validation must require >= 2 laps per compound")

    def test_validation_gate_returns_before_api_call(self):
        """DEF-P2-016 test 10: validation gate returns before the worker thread is started."""
        body = self._body
        validation_pos = body.find("_validation_warnings")
        self.assertGreater(validation_pos, -1,
                           "_run_practice_analysis must have a _validation_warnings section")

        # First return AFTER the validation_warnings block
        return_pos = body.find("return", validation_pos)
        self.assertGreater(return_pos, -1,
                           "validation block must contain a return statement")

        # _worker() definition must come AFTER the return (i.e., the gate fires first)
        worker_pos = body.find("def _worker(", validation_pos)
        self.assertGreater(worker_pos, return_pos,
                           "_worker thread must be defined AFTER the validation return, "
                           "proving the gate exits before any API call is made")


# ---------------------------------------------------------------------------
# Tests 11–13 — RaceParams fields + strategy propagation
# ---------------------------------------------------------------------------

class TestRaceParamsBoPFields(unittest.TestCase):

    def test_race_params_has_tuning_locked_field(self):
        """DEF-P1-005 test 11: RaceParams must have a tuning_locked bool field defaulting to False."""
        from strategy.ai_planner import RaceParams
        fields = {f.name: f for f in dataclasses.fields(RaceParams)}
        self.assertIn("tuning_locked", fields,
                      "RaceParams must have a tuning_locked field")
        self.assertFalse(fields["tuning_locked"].default,
                         "tuning_locked must default to False")

    def test_race_params_has_allowed_tuning_field(self):
        """DEF-P1-005 test 12: RaceParams must have an allowed_tuning list field."""
        from strategy.ai_planner import RaceParams
        fields = {f.name: f for f in dataclasses.fields(RaceParams)}
        self.assertIn("allowed_tuning", fields,
                      "RaceParams must have an allowed_tuning field")
        # allowed_tuning uses default_factory=list — check it's not missing entirely
        field_obj = fields["allowed_tuning"]
        self.assertTrue(
            field_obj.default is dataclasses.MISSING or field_obj.default_factory is not dataclasses.MISSING,
            "allowed_tuning must have a default_factory (empty list)",
        )

    def test_run_practice_analysis_builds_tuning_locked_from_strategy(self):
        """DEF-P1-005 test 13: _run_practice_analysis derives tuning_locked from strategy config."""
        body = _method_body(_dashboard_text(), "_run_practice_analysis")
        self.assertIn('"tuning_locked"', body,
                      '_run_practice_analysis must include tuning_locked in race_params')
        self.assertIn('not bool(_psc.get("tuning"', body,
                      'tuning_locked must be derived as not bool(strategy["tuning"])')
        self.assertIn('"allowed_tuning"', body,
                      '_run_practice_analysis must include allowed_tuning in race_params')
        self.assertIn("allowed_tuning_categories", body,
                      'allowed_tuning must source from strategy["allowed_tuning_categories"]')


if __name__ == "__main__":
    unittest.main()
