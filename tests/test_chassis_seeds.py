"""Per-car chassis seeds — dampers, camber and toe must differ by CAR and by
race vs qualifying, instead of coming out at one flat constant for every car.

Directive item 1 (scope: personalized authoring). Deterministic / offline.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from strategy.setup_engineering import build_vehicle_model, derive_chassis_seeds
from strategy.setup_baseline import build_baseline_setup, NEUTRAL_SEEDS
from strategy.setup_driver_profile import build_driver_profile
from strategy.setup_ranges import resolve_ranges

_DAMPERS = ("dampers_front_comp", "dampers_front_ext",
            "dampers_rear_comp", "dampers_rear_ext")


def _veh(drivetrain, weight, power=250.0):
    specs = {"weight_kg": weight, "power_hp": power, "category": "test"}
    return build_vehicle_model("Test Car", drivetrain, 6, specs)


class TestSeedsDifferByCar:
    def test_two_different_cars_get_different_dampers(self):
        light_mr = derive_chassis_seeds(_veh("MR", 1250, 500), "base")
        heavy_ff = derive_chassis_seeds(_veh("FF", 1650, 180), "base")
        # Heavier car → more damping on at least one axis; not byte-identical.
        assert any(heavy_ff[f] != light_mr[f] for f in _DAMPERS)
        assert heavy_ff["dampers_front_comp"] > light_mr["dampers_front_comp"]

    def test_camber_is_front_greater_than_rear_and_fwd_gets_more_front(self):
        ff = derive_chassis_seeds(_veh("FF", 1400), "base")   # front-drive
        rr = derive_chassis_seeds(_veh("RR", 1400), "base")   # rear-engined
        # Reference tunes: camber is FRONT > REAR on every car, regardless of drivetrain.
        assert ff["camber_front"] > ff["camber_rear"]
        assert rr["camber_front"] > rr["camber_rear"]
        # Front-drive gets a little extra front camber to fight understeer.
        assert ff["camber_front"] > rr["camber_front"]

    def test_rear_toe_reflects_drivetrain(self):
        rwd = derive_chassis_seeds(_veh("RR", 1400), "base")
        fwd = derive_chassis_seeds(_veh("FF", 1400), "base")
        assert rwd["toe_rear"] > fwd["toe_rear"]              # RWD more rear toe-in

    def test_unknown_mass_still_differentiates_and_invents_nothing(self):
        # No weight → neutral mass factor (1.0), so dampers = base * stiff * objective.
        seeds = derive_chassis_seeds(_veh("MR", 0.0, 0.0), "base")
        assert seeds["dampers_front_comp"] == NEUTRAL_SEEDS["dampers_front_comp"]
        # But drivetrain still shapes camber/toe.
        assert seeds["camber_rear"] != NEUTRAL_SEEDS["camber_rear"]


class TestSeedsDifferByObjective:
    def test_qualifying_is_firmer_than_race(self):
        v = _veh("MR", 1300, 500)
        quali = derive_chassis_seeds(v, "qualifying")
        race = derive_chassis_seeds(v, "race")
        assert quali["dampers_front_comp"] > race["dampers_front_comp"]
        assert quali["camber_front"] > race["camber_front"]     # more camber to qualify
        assert race["toe_rear"] > quali["toe_rear"]             # more stability for race

    def test_race_and_quali_are_not_identical(self):
        v = _veh("FR", 1450, 400)
        quali = derive_chassis_seeds(v, "qualifying")
        race = derive_chassis_seeds(v, "race")
        assert quali != race


class TestBaselineAppliesChassisSeeds:
    def _build(self, drivetrain, overrides):
        return build_baseline_setup(
            "", resolve_ranges(""), drivetrain, 6,
            build_driver_profile(), None, False,
            chassis_seed_overrides=overrides)

    def test_override_reaches_the_setup_fields(self):
        v = _veh("MR", 1250, 500)
        seeds = derive_chassis_seeds(v, "qualifying")
        raw = self._build("MR", seeds)
        fields = raw["setup_fields"]
        # At least the dampers land on the derived (range-clamped) values, not the
        # flat neutral constant.
        assert any(fields.get(f) is not None for f in _DAMPERS)
        for f in _DAMPERS:
            if f in fields:
                lo, hi = resolve_ranges("")[f]
                assert lo <= fields[f] <= hi

    def test_without_overrides_dampers_are_the_neutral_seed(self):
        raw = self._build("MR", None)
        # Backward compatible: no override → flat neutral seed (unchanged behaviour).
        assert raw["setup_fields"]["dampers_front_comp"] == NEUTRAL_SEEDS["dampers_front_comp"]

    def test_two_cars_produce_different_baseline_dampers(self):
        a = self._build("MR", derive_chassis_seeds(_veh("MR", 1200, 520), "race"))
        b = self._build("FF", derive_chassis_seeds(_veh("FF", 1650, 180), "race"))
        assert any(a["setup_fields"].get(f) != b["setup_fields"].get(f) for f in _DAMPERS)
