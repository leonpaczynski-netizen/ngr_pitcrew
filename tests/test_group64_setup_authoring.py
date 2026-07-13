"""Group 64 — canonical setup-authoring architecture tests.

Prove that the deterministic authoring path:
  * carries the objective as a first-class value (not a label),
  * authors genuinely different Base / Qualifying / Race full-field setups,
  * reaches proven same-car history for authoring (incl. the LSD triplet),
  * assigns EVERY adjustable field an explicit disposition,
  * stays honest on a fresh profile (no invented history),
  * respects legality (values stay in range) and event locks.
"""
from __future__ import annotations

from strategy.setup_authoring import (
    SetupObjective, FieldDisposition, SetupAuthoringContext, FullFieldPlan,
    author_full_field_plan, author_discipline_setups, objective_from_session_type,
    EVIDENCE_PRECEDENCE,
)
from strategy.setup_ranges import resolve_ranges
from strategy.setup_driver_profile import build_driver_profile

_CAR = "Porsche 911 RSR (991) '17"


def _ranges():
    return resolve_ranges(_CAR)


def _prior():
    return {
        "lsd_initial": {"value": 22, "tier": 1, "source": "Watkins Glen", "confidence": "high"},
        "lsd_accel":   {"value": 8,  "tier": 1, "source": "Watkins Glen", "confidence": "high"},
        "lsd_decel":   {"value": 33, "tier": 1, "source": "Watkins Glen", "confidence": "high"},
        "camber_front": {"value": 2.5, "tier": 1, "source": "Watkins Glen", "confidence": "high"},
        "camber_rear":  {"value": 2.1, "tier": 1, "source": "Watkins Glen", "confidence": "high"},
    }


def _ctx(objective, *, prior=None, duration=45.0, drivetrain="MR",
         allowed_tuning=None, tuning_locked=False):
    return SetupAuthoringContext(
        car=_CAR, objective=objective, ranges=_ranges(), drivetrain=drivetrain,
        num_gears=6, profile=build_driver_profile(), history_prior=prior,
        duration_mins=duration, allowed_tuning=allowed_tuning, tuning_locked=tuning_locked,
    )


# ---------------------------------------------------------------- discipline propagation

def test_objective_is_first_class_not_label():
    for obj in (SetupObjective.BASE, SetupObjective.QUALIFYING, SetupObjective.RACE):
        plan = author_full_field_plan(_ctx(obj))
        assert plan.objective is obj
    assert objective_from_session_type("Qualifying Setup") is SetupObjective.QUALIFYING
    assert objective_from_session_type("R NGR Cup Race") is SetupObjective.RACE
    assert objective_from_session_type("") is SetupObjective.BASE


def test_qualifying_and_race_are_separately_engineered():
    quali = author_full_field_plan(_ctx(SetupObjective.QUALIFYING))
    race = author_full_field_plan(_ctx(SetupObjective.RACE))
    differing = [f for f in quali.setup_fields
                 if quali.setup_fields.get(f) != race.setup_fields.get(f)]
    # Quali biases camber/toe/brake/lsd/aero/ride-height differently to race.
    assert len(differing) >= 5, f"quali and race barely differ: {differing}"
    # Qualifying is the more aggressive one-lap trim on the shared fields.
    assert quali.setup_fields["camber_front"] > race.setup_fields["camber_front"]
    assert quali.setup_fields["brake_bias"] < race.setup_fields["brake_bias"]  # more forward
    assert quali.setup_fields["ride_height_front"] <= race.setup_fields["ride_height_front"]


def test_base_is_not_a_discipline_biased_setup():
    base = author_full_field_plan(_ctx(SetupObjective.BASE))
    quali = author_full_field_plan(_ctx(SetupObjective.QUALIFYING))
    # Base carries no qualifying one-lap bias (e.g. brake bias stays neutral).
    assert base.setup_fields["brake_bias"] != quali.setup_fields["brake_bias"] \
        or base.setup_fields["camber_front"] != quali.setup_fields["camber_front"]
    assert base.session_type == "Practice"


# ---------------------------------------------------------------- proven history authoring

def test_proven_history_reaches_authoring_including_lsd():
    plan = author_full_field_plan(_ctx(SetupObjective.BASE, prior=_prior()))
    # The proven LSD triplet + camber are seeded into the authored setup.
    assert set(plan.seeded_from_history) >= {"lsd_initial", "lsd_accel", "lsd_decel",
                                             "camber_front"}
    assert plan.setup_fields["lsd_initial"] == 22
    assert plan.setup_fields["lsd_decel"] == 33
    # Their disposition is explicitly PROVEN_HISTORY_SEED.
    by_field = {e.field: e for e in plan.entries}
    assert by_field["lsd_initial"].disposition is FieldDisposition.PROVEN_HISTORY_SEED
    assert by_field["lsd_initial"].proven_value == 22


def test_fresh_profile_invents_no_history():
    plan = author_full_field_plan(_ctx(SetupObjective.BASE, prior=None))
    assert plan.seeded_from_history == []
    for e in plan.entries:
        assert e.disposition is not FieldDisposition.PROVEN_HISTORY_SEED
        # No proven value fabricated.
        assert e.proven_value is None


# ---------------------------------------------------------------- full-field dispositions

def test_every_adjustable_field_has_a_disposition():
    plan = author_full_field_plan(_ctx(SetupObjective.RACE, prior=_prior()))
    assert len(plan.entries) >= 20
    for e in plan.entries:
        assert isinstance(e.disposition, FieldDisposition)
    # No duplicate field entries.
    fields = [e.field for e in plan.entries]
    assert len(fields) == len(set(fields))


def test_front_diff_not_relevant_on_non_awd():
    plan = author_full_field_plan(_ctx(SetupObjective.RACE, drivetrain="MR"))
    by_field = {e.field: e for e in plan.entries}
    for f in ("lsd_front_initial", "lsd_front_accel", "lsd_front_decel"):
        assert by_field[f].disposition is FieldDisposition.NOT_RELEVANT


def test_event_locked_fields_are_event_constraint():
    # allow only suspension → aero/diff/etc become EVENT_CONSTRAINT
    plan = author_full_field_plan(_ctx(SetupObjective.RACE, allowed_tuning=["suspension"]))
    by_field = {e.field: e for e in plan.entries}
    # aero is not in the 'suspension' category → locked
    assert by_field["aero_front"].disposition is FieldDisposition.EVENT_CONSTRAINT


def test_authored_values_stay_in_car_range():
    plan = author_full_field_plan(_ctx(SetupObjective.QUALIFYING, prior=_prior()))
    ranges = _ranges()
    for f, v in plan.setup_fields.items():
        if f in ranges and isinstance(v, (int, float)):
            lo, hi = ranges[f]
            assert lo <= v <= hi, f"{f}={v} out of range [{lo},{hi}]"


def test_tuning_locked_authors_nothing():
    plan = author_full_field_plan(_ctx(SetupObjective.RACE, tuning_locked=True))
    assert plan.setup_fields == {} or all(v is None for v in plan.setup_fields.values())


# ---------------------------------------------------------------- objective justification

def test_objective_contribution_present_for_biased_fields():
    quali = author_full_field_plan(_ctx(SetupObjective.QUALIFYING))
    by_field = {e.field: e for e in quali.entries}
    assert "one-lap" in by_field["camber_front"].objective_contribution.lower() \
        or "one lap" in by_field["camber_front"].objective_contribution.lower()


def test_discipline_bundle_and_json():
    def mk(obj):
        return _ctx(obj, prior=_prior())
    plans = author_discipline_setups(mk)
    assert set(plans) == {"base", "qualifying", "race"}
    for p in plans.values():
        assert isinstance(p, FullFieldPlan)
        j = p.as_json()
        assert "dispositions" in j and "entries" in j and "objective" in j


def test_evidence_precedence_documented():
    assert EVIDENCE_PRECEDENCE[0].startswith("1.")
    assert any("history" in s.lower() for s in EVIDENCE_PRECEDENCE)
    assert any("conservative" in s.lower() for s in EVIDENCE_PRECEDENCE)
