"""1.11 wired: a served penalty reaches the lap row and the race; lap one is
evidence after a rolling start and not after a standing one (G26, G27)."""
from __future__ import annotations

from pitcrew.race.calls import PENALTY, RaceState, _penalty
from pitcrew.race.coordinator import PlanContext, RaceCoordinator, context_from_event
from pitcrew.race.expectations import ExpectationTracker
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent


def _lap(num, ms=90_000, fuel=5.0):
    return Lap(lap_num=num, lap_time_ms=ms, best_lap_ms=ms, delta_ms=0,
               fuel_start=50.0, fuel_end=50.0 - fuel, fuel_used=fuel,
               position=3, is_pit_lap=False, is_out_lap=False)


# --------------------------------------------------------- the tracker

def test_a_standing_start_keeps_lap_one_out():
    tracker = ExpectationTracker()
    for n in range(1, 6):
        tracker.note_lap(_lap(n))
    assert tracker.green_laps() == 4


def test_a_rolling_start_admits_lap_one():
    tracker = ExpectationTracker()
    tracker.rolling_start = True
    for n in range(1, 6):
        tracker.note_lap(_lap(n))
    assert tracker.green_laps() == 5


def test_a_penalised_lap_leaves_the_clean_population_whichever_comes_first():
    tracker = ExpectationTracker()
    for n in range(2, 7):
        tracker.note_lap(_lap(n))
    assert tracker.green_laps() == 5
    tracker.note_penalty(4)
    assert tracker.green_laps() == 4
    assert 4 not in tracker.laps_by_number()
    # The read arriving before the row is the same answer.
    tracker.note_penalty(7)
    tracker.note_lap(_lap(7))
    assert tracker.green_laps() == 4


# ------------------------------------------------------ the start type

def test_the_event_s_start_type_reaches_the_context_and_the_tracker():
    context = context_from_event({"car_name": "x", "track": "Spa",
                                  "layout": None, "race_laps": 20,
                                  "race_type": "laps",
                                  "start_type": "Rolling"})
    assert context.start_type == "Rolling"
    race = RaceCoordinator({"stints": [{"laps": 20, "compound": "RM",
                                        "fuel_l": 60.0, "start_lap": 1}]},
                           fuel_per_lap_l=3.0)
    assert race.arm(context, context)
    assert race.expect.rolling_start is True
    standing = PlanContext(car="x", track="Spa", layout=None, race_laps=20,
                           start_type="Standing")
    race.arm(standing, standing)
    assert race.expect.rolling_start is False


def test_the_start_type_is_not_part_of_the_plan_match():
    rolling = PlanContext(car="x", track="Spa", layout=None, race_laps=20,
                          start_type="Rolling")
    standing = PlanContext(car="x", track="Spa", layout=None, race_laps=20,
                           start_type="Standing")
    assert rolling.matches(standing) == (True, "")


# ------------------------------------------------------------ the call

def test_a_served_penalty_is_said_once_with_its_derived_cost():
    state = RaceState(lap=6, laps_total=20, penalty_note=(6, 1.52))
    call = _penalty(state)
    assert call is not None and call.kind == PENALTY
    assert call.call == "Penalty served. About 1.5 seconds."
    assert call.reason == ("Read off the brake trace, not the HUD. "
                           "Lap 6 is out of the pace.")
    state.record(call)
    assert _penalty(state) is None


def test_the_penalty_is_never_spoken_as_a_fact():
    """Critic pass 6. Nothing reads a penalty - the brake trace is read, and
    an avoidance stab is the same shape. LOW, so `spoken()` hedges it."""
    from pitcrew.race.calls import LOW

    call = _penalty(RaceState(lap=6, laps_total=20, penalty_note=(6, 0.31)))
    assert call.confidence == LOW
    assert call.spoken().endswith("Unconfirmed.")


def test_the_coordinator_takes_the_penalty_into_the_race():
    race = RaceCoordinator({"stints": [{"laps": 20, "compound": "RM",
                                        "fuel_l": 60.0, "start_lap": 1}]},
                           fuel_per_lap_l=3.0)
    context = PlanContext(car="x", track="Spa", layout=None, race_laps=20)
    assert race.arm(context, context)
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    for n in range(1, 6):
        race.handle(SessionEvent(EventKind.LAP_COMPLETED, {"lap": _lap(n)}))
    before = race.expect.green_laps()
    race.note_penalty(5, 1.5)
    assert race.expect.green_laps() == before - 1
    assert race.state.penalty_note == (5, 1.5)


def test_a_penalty_read_can_be_withdrawn():
    """Critic pass 6: the place turned out to be a corner the model is
    missing, so the lap it struck goes back into the pace and the note it
    left goes with it."""
    race = RaceCoordinator({"stints": [{"laps": 20, "compound": "RM",
                                        "fuel_l": 60.0, "start_lap": 1}]},
                           fuel_per_lap_l=3.0)
    context = PlanContext(car="x", track="Spa", layout=None, race_laps=20)
    assert race.arm(context, context)
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    for n in range(1, 6):
        race.handle(SessionEvent(EventKind.LAP_COMPLETED, {"lap": _lap(n)}))
    before = race.expect.green_laps()
    race.note_penalty(5, 1.5)
    race.forget_penalty(5)
    assert race.expect.green_laps() == before
    assert race.state.penalty_note is None
    # A lap that was never struck is not disturbed by withdrawing it.
    race.note_penalty(4, 1.5)
    race.forget_penalty(3)
    assert race.state.penalty_note == (4, 1.5)


# ------------------------------------------ the conditions it was read in

class _Stub:
    """Just enough controller to ask the weather question."""

    def __init__(self, event):
        self._event = event

    def active_event(self):
        return self._event


def _readable(event):
    from pitcrew.controller import PitCrewController

    return PitCrewController._penalties_are_readable(_Stub(event))


def test_penalties_are_read_at_a_dry_fixed_event():
    assert _readable({"weather": "dry", "rain_possible": 0}) is None
    assert _readable({"weather": "Dry", "rain_possible": None}) is None


def test_a_session_that_may_be_wet_is_refused_with_its_reason():
    """Critic pass 6: in the wet the brake for a corner the model DOES
    contain starts outside `APPROACH_M` and reads as a penalty on a
    straight. Every frame the detector was calibrated on is dry and the app
    cannot read that it is raining - the hygrometer reader was struck for
    exactly that. So the lap gets `None`, not a zero."""
    assert "not dry" in _readable({"weather": "changeable",
                                   "rain_possible": 0})
    assert "rain is possible" in _readable({"weather": "dry",
                                            "rain_possible": 1})
    assert _readable(None) is not None
    assert _readable({}) is not None, "an event that cannot say is a refusal"


def test_the_ledger_and_the_refusal_have_production_callers():
    """This codebase's own repeated defect is a guard with no caller
    (plan 1.12). Both of these live in `controller._on_lap_completed`."""
    import pathlib

    source = (pathlib.Path(__file__).resolve().parents[1] / "controller.py"
              ).read_text(encoding="utf-8")
    assert "self._road_not_penalty().filter(" in source
    assert "self.race.forget_penalty(handed_back)" in source
    start = source.index("    def _corner_windows(self)")
    end = source.index("\n    def ", start + 10)
    assert "self._penalties_are_readable()" in source[start:end]


# ----------------------------------------------------------- the row

def test_the_lap_row_carries_the_count_and_the_cost(tmp_path):
    from dataclasses import fields

    from pitcrew.store.db import Store
    from pitcrew.telemetry.recorder import LapFrames

    names = {f.name for f in fields(LapFrames)}
    assert {"penalties_served", "penalty_lost_s"} <= names
    store = Store(tmp_path / "p.db")
    try:
        columns = {r[1] for r in store._query("PRAGMA table_info(laps)")}
        assert {"penalties_served", "penalty_lost_s"} <= columns
    finally:
        store.close()
