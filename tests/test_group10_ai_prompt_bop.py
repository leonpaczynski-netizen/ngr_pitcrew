"""Tests for Group 10: RaceParams BoP / tuning fields (DEF-P1-005).

Post determinism-rebuild: the AI practice-prompt builders and the dashboard
practice-analysis worker were removed. What survives here is the deterministic
data contract — RaceParams still carries the event tuning fields that the
downstream deterministic setup/strategy logic reads.

RaceParams moved from strategy.ai_planner to strategy.race_params.
"""
from __future__ import annotations

import dataclasses
import unittest


# ---------------------------------------------------------------------------
# RaceParams tuning fields
# ---------------------------------------------------------------------------

class TestRaceParamsBoPFields(unittest.TestCase):

    def test_race_params_has_tuning_locked_field(self):
        """DEF-P1-005: RaceParams must have a tuning_locked bool field defaulting to False."""
        from strategy.race_params import RaceParams
        fields = {f.name: f for f in dataclasses.fields(RaceParams)}
        self.assertIn("tuning_locked", fields,
                      "RaceParams must have a tuning_locked field")
        self.assertFalse(fields["tuning_locked"].default,
                         "tuning_locked must default to False")

    def test_race_params_has_allowed_tuning_field(self):
        """DEF-P1-005: RaceParams must have an allowed_tuning list field."""
        from strategy.race_params import RaceParams
        fields = {f.name: f for f in dataclasses.fields(RaceParams)}
        self.assertIn("allowed_tuning", fields,
                      "RaceParams must have an allowed_tuning field")
        field_obj = fields["allowed_tuning"]
        self.assertTrue(
            field_obj.default is dataclasses.MISSING or field_obj.default_factory is not dataclasses.MISSING,
            "allowed_tuning must have a default_factory (empty list)",
        )


if __name__ == "__main__":
    unittest.main()
