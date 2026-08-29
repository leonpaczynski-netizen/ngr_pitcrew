"""What the desk lets George do on his own.

`strategy/handover.py` states the split and nothing enforced it: the playbook
was validated on the way in, stored, and rendered on the Strategy screen,
while `RaceCoordinator` never read it. So the card told the driver which
adaptations George could make and George made whichever he liked.

**It gates deciding, never reporting.** Anything George says is advice the
driver can ignore, and silencing that because an author left a trigger out
would make the engineer worse rather than more obedient. What it bounds is
the short list of things George changes without being asked: the plan he is
running to, and the cue in the driver's ear.
"""
from __future__ import annotations

from pitcrew.race.calls import BOX_NOW, STAY_OUT, Call, RaceState
from pitcrew.race.coordinator import RaceCoordinator
from pitcrew.strategy.handover import Handover, PlaybookEntry


def a_plan(playbook=None) -> dict:
    plan = {"stints": [{"laps": 10, "compound": "RM", "fuel_l": 60.0,
                        "start_lap": 1},
                       {"laps": 10, "compound": "RM", "fuel_l": 60.0,
                        "start_lap": 11}],
            "stops": 1, "pit_laps": [10], "binding_constraint": "fuel"}
    if playbook is None:
        return plan
    return Handover(plan=plan, playbook=playbook).as_stored(plan)


def an_entry(**over) -> PlaybookEntry:
    fields = dict(trigger="fuel_short", action="short_shift",
                  when="more than 0.5 laps short", until="the deficit clears")
    fields.update(over)
    return PlaybookEntry(**fields)


def ignoring_the_box(plan) -> RaceCoordinator:
    """Two laps past the planned stop, still out, fuel reaching the flag."""
    race = RaceCoordinator(plan)
    state = race.state
    state.lap, state.laps_total = 12, 20
    state.stint_ends_on_lap = 10
    state.fuel_l, state.fuel_per_lap_l = 60.0, 3.0
    state.said.append(BOX_NOW)
    return race


# ------------------------------------------------------------- no playbook

def test_a_plan_with_no_playbook_leaves_george_exactly_as_he_was():
    """**Empty is not the same as absent.** The app's own plans carry none,
    and `Handover.validate` allows a handover with none - a short sprint with
    one stop and no weather in it needs no adaptations. Reading that as "he
    may do nothing" would silence the engineer on every race he has ever run."""
    race = RaceCoordinator(a_plan())
    assert race._may("fuel_short", "short_shift") is True
    assert race._may("stop_missed", "offer_stay_out") is True
    assert race._may("anything", "at_all") is True


# --------------------------------------------------- a playbook that bounds

def test_a_playbook_permits_only_what_it_names():
    race = RaceCoordinator(a_plan([an_entry()]))
    assert race._may("fuel_short", "short_shift") is True
    assert race._may("fuel_short", "lift_and_coast") is False, \
        "a different action for a named trigger is still not what was granted"
    assert race._may("stop_missed", "offer_stay_out") is False


def test_the_shortfall_is_still_spoken_when_the_lever_is_not_granted():
    """**The words stay, the instruction goes.** A fuel call that names the
    shortfall is a report; the rpm drop riding on it moves the shift beep in
    his ear, which is George changing the car's cue on his own."""
    race = RaceCoordinator(a_plan([an_entry(trigger="incident",
                                            action="report_only")]))
    call = Call("fuel-short", 8, "Short-shift and lift into the slow corners.",
                "You're 1.2 laps short on fuel.", short_shift_drop_rpm=450.0)

    kept = race._within_the_playbook(call)

    assert kept.call == call.call, "the report is not the playbook's to take"
    assert kept.reason == call.reason
    assert kept.short_shift_drop_rpm is None, "the beep moved without a grant"


def test_the_lever_survives_when_the_playbook_grants_it():
    race = RaceCoordinator(a_plan([an_entry()]))
    call = Call("fuel-short", 8, "Short-shift.", "1.2 laps short.",
                short_shift_drop_rpm=450.0)

    assert race._within_the_playbook(call).short_shift_drop_rpm == 450.0


# ------------------------------------------- the one plan rewrite he makes alone

def test_a_missed_stop_is_still_said_when_the_fold_is_not_granted():
    """Saying it costs the driver nothing and he answers with his hands.
    REWRITING the plan to a zero-stop retires the box call, moves the fuel
    target to the flag and changes what every later call is measured against -
    that is deciding, and it is the half a playbook is for."""
    race = ignoring_the_box(a_plan([an_entry()]))    # no stop_missed entry
    before = [dict(s) for s in race._stints]

    call = race._reconsider_ignored_box()

    assert call is not None and call.kind == STAY_OUT, "he must still say it"
    assert race._stints == before, "the plan was rewritten without a grant"


def test_a_granted_fold_rewrites_the_plan():
    race = ignoring_the_box(a_plan([an_entry(trigger="stop_missed",
                                             action="offer_stay_out",
                                             when="the box lap has gone by")]))

    call = race._reconsider_ignored_box()

    assert call is not None and call.kind == STAY_OUT
    assert len(race._stints) == race.state.stint_index + 1, \
        "the fold to a zero-stop did not happen"


def test_the_app_s_own_plan_still_folds():
    """The behaviour every race before this had, and the one a playbook must
    not take away by accident."""
    race = ignoring_the_box(a_plan())

    call = race._reconsider_ignored_box()

    assert call is not None and call.kind == STAY_OUT
    assert len(race._stints) == race.state.stint_index + 1


def test_the_gate_is_actually_wired_into_the_call_the_driver_gets():
    """**The mutant that survived the first draft of this file.**

    Every test above called `_within_the_playbook` directly, so removing its
    one call site in `_emit` broke nothing - the gate existed, was correct,
    and reached no race. That is the defect this whole session keeps finding,
    written into the test for the fix for it.

    This drives the real `_emit` with a state that genuinely produces a
    fuel-short call carrying an rpm drop, and asserts on what the driver
    would actually be handed.
    """
    granted = RaceCoordinator(a_plan([an_entry()]))
    withheld = RaceCoordinator(a_plan([an_entry(trigger="incident",
                                                action="report_only")]))
    for race in (granted, withheld):
        state = race.state
        state.lap, state.laps_total = 8, 20
        state.fuel_l, state.fuel_per_lap_l = 12.0, 3.0
        state.position, state.stint_ends_on_lap = 3, 18
        state.laps_since_stop = 8
        state.short_shift_l_per_1000rpm = 0.9

    kept = granted._emit()
    assert kept is not None and kept.kind == "fuel-short"
    assert kept.short_shift_drop_rpm, "the granted lever never reached him"

    stripped = withheld._emit()
    assert stripped is not None and stripped.kind == "fuel-short"
    assert "short" in (stripped.call + stripped.reason).lower(), \
        "the shortfall must still be spoken - the report is not the "\
        "playbook's to take"
    assert stripped.short_shift_drop_rpm is None, \
        "the beep moved with no grant, so the gate is not wired into _emit"
