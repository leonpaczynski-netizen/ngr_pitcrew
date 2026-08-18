"""A rehearsal race is evidence, and until now it was recorded and ignored.

*"should also have the ability to do full race practice against AI as an
option to prove race strat and get consistancy"*

Recording the rehearsal was half the feature. The strategy model read
`kind='practice'` sessions only, so the one run that produces a real pit stop
under race conditions — at race fuel load, at race pace, in traffic, at the
race's time of day — never reached the plan it was run to prove.

**The league race is now included too**, on the driver's instruction: *"race
fuel and pace should be included from race sims and actual race data too - it
all combines with practice session data for the full picture."* The
circularity the old exclusion guarded against does not arise - the in-race
re-planner reads inputs captured once at arming and never rebuilds them - and
what the exclusion actually did was discard the best evidence in the database
at the moment it was gathered. `LapInput.counted` is what keeps a race honest,
and it always did: out-laps, in-laps, struck laps and incident laps are
dropped from pace and fuel on every session kind alike.
"""
from __future__ import annotations

from pitcrew.analysis.recency import REHEARSAL_WEIGHT, weight_of
from pitcrew.analysis.session import LapInput
from pitcrew.store.db import Store
from pitcrew.telemetry.session_state import Lap


def a_lap(lap_num: int, *, burn: float = 6.0) -> Lap:
    return Lap(lap_num=lap_num, lap_time_ms=109_000, best_lap_ms=109_000,
               delta_ms=0, fuel_start=100.0 - burn * (lap_num - 1),
               fuel_end=100.0 - burn * lap_num, fuel_used=burn,
               position=1, is_pit_lap=False, is_out_lap=False,
               compound="RH")


def a_session(store: Store, event_id: int, kind: str, *, laps: int = 5,
              burn: float = 6.0, **overrides) -> int:
    session_id = store.start_session(event_id, kind, **overrides)
    for lap_num in range(1, laps + 1):
        store.add_lap(session_id, a_lap(lap_num, burn=burn))
    return session_id


# ------------------------------------------------------------ what it reads

def test_a_rehearsal_reaches_the_plan(store: Store, event_id):
    a_session(store, event_id, "practice", laps=4)
    a_session(store, event_id, "race", laps=6, rehearsal=True)
    rows = store.list_evidence_laps(event_id)
    assert len(rows) == 10
    assert any(row["rehearsal"] for row in rows)


def test_the_league_race_reaches_the_plan_too(store: Store, event_id):
    """His instruction: it all combines with practice for the full picture.

    A race is the only place some of this is measurable at all - §5.2 wants
    the wear rate taken at the multiplier actually being raced, from a run at
    genuine race pace on a full tank, which is a description of a race stint.
    """
    a_session(store, event_id, "practice", laps=4)
    a_session(store, event_id, "race", laps=6)          # not a rehearsal
    rows = store.list_evidence_laps(event_id)
    assert len(rows) == 10
    assert {row["session_kind"] for row in rows} == {"practice", "race"}


def test_a_race_lap_is_still_held_to_the_same_bar(store: Store, event_id):
    """Opening the scope did not open the gate. What keeps a race honest is
    `counted`, which drops in-laps, out-laps and incidents on every session
    kind alike - and a race has more of all three than practice does."""
    from pitcrew.analysis.session import counted_laps
    from pitcrew.strategy.evidence import _lap_inputs

    session_id = store.start_session(event_id, "race")
    for lap_num in range(1, 5):
        store.add_lap(session_id, a_lap(lap_num))
    pit = Lap(lap_num=5, lap_time_ms=183_000, best_lap_ms=109_000, delta_ms=0,
              fuel_start=76.0, fuel_end=90.0, fuel_used=0.0, position=1,
              is_pit_lap=True, is_out_lap=False, compound="RH")
    store.add_lap(session_id, pit)

    laps = _lap_inputs(store, event_id)
    assert len(laps) == 5
    assert len(counted_laps(laps)) == 4, "the pit lap must not be a pace sample"


def test_practice_alone_is_unchanged(store: Store, event_id):
    a_session(store, event_id, "practice", laps=4)
    assert len(store.list_evidence_laps(event_id)) == 4


def test_the_laps_are_numbered_continuously_across_both(store: Store, event_id):
    """Two laps both called "lap 1" put two different runs at the same number
    where anything keyed on it cannot tell them apart."""
    from pitcrew.export.build import evidence_lap_inputs

    a_session(store, event_id, "practice", laps=3)
    a_session(store, event_id, "race", laps=3, rehearsal=True)
    laps = evidence_lap_inputs(store, event_id, hydrate=set())
    assert [lap.lap_num for lap in laps] == [1, 2, 3, 4, 5, 6]
    assert [lap.rehearsal for lap in laps] == [False] * 3 + [True] * 3


# ---------------------------------------------------------- what it is worth

def test_a_rehearsal_lap_outweighs_a_practice_lap_of_the_same_age():
    rehearsal = LapInput(lap_num=1, lap_time_ms=109_000, fuel_start=100.0,
                         fuel_end=94.0, session_id=1, rehearsal=True)
    practice = LapInput(lap_num=1, lap_time_ms=109_000, fuel_start=100.0,
                        fuel_end=94.0, session_id=1)
    ages = {1: 0}
    assert (weight_of(rehearsal, ages, None)
            == weight_of(practice, ages, None) * REHEARSAL_WEIGHT)


def test_being_better_evidence_does_not_decay():
    """The age term decays; what a lap *is* does not. An old rehearsal still
    describes a race and a new practice lap still does not."""
    old_rehearsal = LapInput(lap_num=1, lap_time_ms=109_000, fuel_start=100.0,
                             fuel_end=94.0, session_id=1, rehearsal=True)
    new_practice = LapInput(lap_num=2, lap_time_ms=109_000, fuel_start=100.0,
                            fuel_end=94.0, session_id=9)
    ages = {1: 6, 9: 0}
    assert weight_of(old_rehearsal, ages, None) > 0
    assert (weight_of(old_rehearsal, ages, None)
            > weight_of(new_practice, ages, None) * 0.1)


def test_the_weighting_says_how_many_rehearsal_laps_it_saw():
    from pitcrew.analysis.recency import weighted

    laps = [LapInput(lap_num=n, lap_time_ms=109_000, fuel_start=100.0,
                     fuel_end=94.0, session_id=1, rehearsal=n > 2)
            for n in range(1, 6)]
    _, weighting = weighted(laps, lambda lap: lap.fuel_start - lap.fuel_end)
    assert weighting.rehearsal_laps == 3
    assert weighting.as_export()["rehearsalWeight"] == REHEARSAL_WEIGHT
