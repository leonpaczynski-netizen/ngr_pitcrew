"""The cancelled stop, driven through a real race (critic 4 on batch 4).

Batch 4's tests only ever called `note_stop_need()` by hand, so removing it
from `_on_lap` survived them. These drive `RaceCoordinator.handle` with
`fuel_long: drop_stop` granted, the way the critic did, with the burn
scripted either side of the margin through the expectation tracker.
"""
from __future__ import annotations

from pitcrew.race import calls as C
from pitcrew.race.coordinator import PlanContext, RaceCoordinator
from pitcrew.strategy.handover import Handover, PlaybookEntry
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent

LAPS = 20
# Litres a lap either side of the margin, against `_fuel` below. 7.0 rather
# than 6.0: at 6.0 the lap-12 reading sat on the margin itself.
REACH, SHORT = 3.0, 7.0


def _fuel(lap):
    return 100.0 - 3.8 * lap          # what is aboard at the line, lap by lap


def _plan(stints=((10, 1), (10, 11)), grant="drop_stop"):
    plan = {"stints": [{"laps": n, "compound": "RM", "start_lap": s}
                       for n, s in stints],
            "stops": len(stints) - 1, "binding_constraint": "fuel"}
    return Handover(plan=plan, playbook=[PlaybookEntry(
        trigger="fuel_long", action=grant, when="x")]).as_stored(plan)


def _race(plan=None):
    race = RaceCoordinator(plan or _plan(), fuel_per_lap_l=4.5,
                           fuel_capacity_l=100.0, planned_fuel_per_lap_l=4.5,
                           planned_lap_time_ms=90_000, mandatory_stops=0)
    context = PlanContext(car="Huracan", track="Daytona", layout="Road",
                          race_laps=LAPS)
    assert race.arm(context, context)
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": LAPS}))
    burn = [4.5]
    race.expect.current_fuel_per_lap_l = lambda: burn[0]
    race.expect.green_laps = lambda: 10
    race.expect.current_fuel_reference_load_l = lambda: None
    race._test_burn = burn
    return race


def _drive(race, laps):
    """`laps` is [(lap, burn)]; returns [(lap, call)] for what was said."""
    said = []
    for lap, rate in laps:
        race._test_burn[0] = rate
        fuel_end = _fuel(lap)
        call = race.handle(SessionEvent(EventKind.LAP_COMPLETED, {"lap": Lap(
            lap_num=lap, lap_time_ms=90_000, best_lap_ms=90_000, delta_ms=0,
            fuel_start=fuel_end + rate, fuel_end=fuel_end, fuel_used=rate,
            position=3, is_pit_lap=False, is_out_lap=False)}))
        if call is not None:
            race.state.record(call)
            said.append((lap, call))
    return said


def _reversals(said):
    return [(lap, c.kind) for lap, c in said
            if c.kind in (C.STOPS_OFF, C.STOP_BACK)]


def test_a_burn_that_cannot_make_up_its_mind_is_not_spoken_every_lap():
    """The critic's sequence - short, short, long, repeating - cycled the
    two calls eight times in ten laps."""
    race = _race()
    pattern = [SHORT, SHORT, REACH] * 3
    said = _drive(race, list(enumerate(pattern, start=1)))
    reversals = _reversals(said)
    laps = [lap for lap, _kind in reversals]
    for earlier, later in zip(laps, laps[1:]):
        assert later - earlier >= C.STOP_FLIP_LAPS, reversals
    assert len(reversals) <= 1, reversals


def test_the_hold_moves_through_the_lap_hook():
    race = _race()
    said = _drive(race, [(lap, REACH) for lap in range(1, 5)])
    assert any(c.kind == C.STOPS_OFF for _lap, c in said)
    said = _drive(race, [(lap, SHORT) for lap in range(5, 8)])
    assert any(c.kind == C.STOP_BACK for _lap, c in said)


def test_a_stop_back_after_its_box_lap_is_due_now_and_overdue_from_then():
    """Retired all through the planned box lap (10); needed again from lap
    11. He is told to box on the lap it comes back, and a lap later he is one
    lap overdue - not three, counted from the lap he was told it was off."""
    race = _race()
    _drive(race, [(lap, REACH) for lap in range(1, 11)])
    said = _drive(race, [(11, SHORT), (12, SHORT)])
    back = [c for _lap, c in said if c.kind == C.STOP_BACK]
    assert back and back[-1].call.startswith(
        "The stop is back on. Box this lap."), said
    later = _drive(race, [(13, SHORT)])
    reasons = " ".join(c.reason or "" for _lap, c in later)
    assert "3 laps overdue" not in reasons and "2 laps overdue" not in reasons


def test_every_surface_reads_one_answer_lap_by_lap():
    race = _race()
    for lap, rate in enumerate([REACH, REACH, SHORT, REACH, SHORT], start=1):
        _drive(race, [(lap, rate)])
        state = race.state
        if state.stint_ends_on_lap is not None and not state.past_box_lap:
            assert (state.laps_to_stop() is not None) == \
                C.stop_still_needed(state), lap


def test_a_replan_adopted_mid_race_starts_the_stop_afresh():
    race = _race()
    _drive(race, [(lap, REACH) for lap in range(1, 5)])
    assert race.state.stops_off_said is True
    race._apply_stint(race.state.stint_index)
    assert race.state.stops_off_said is False
    assert C.STOPS_OFF not in race.state.said
    assert race.state.stop_needed_held is None
