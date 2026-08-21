"""The count that decides how much fuel goes in.

**The driver's report, 22 Aug:** *"Engineer dropped laps, thinks first lap
isn't counted, so told me to over fuel. Fuelling in a race that is 1 litre a
second is critical to get the exact number and no more."*

He is right, and the database shows the mechanism. Every Monza race on file
recorded **26 rows for 27 laps driven** - the pit row spans 1.94 laps of
distance, with 5.50 L gone against a 5.55 L lap - because GT7 takes the car
over at the pit entry and the crossing inside that sequence never reaches the
app. Watkins, which had no such issue, recorded 20 rows for 20 laps.

The clock already detected this and folded the missing time into its offset.
But `laps_dropped` reached exactly one place - the *wording* of the run-in call
- and never the arithmetic. So the count stayed one light, and one light is one
lap of fuel too many at the stop: about six litres, six seconds standing still,
on a driver who will not carry a spare lap precisely because he counts the stop
in seconds.
"""
from __future__ import annotations

from pitcrew.race.calls import RaceState, fuel_target_l


def a_state(**over) -> RaceState:
    fields = dict(lap=13, laps_total=27, fuel_per_lap_l=5.55,
                  fuel_l=20.0, laps_estimate_firm=True)
    fields.update(over)
    return RaceState(**fields)


def test_a_dropped_crossing_shortens_the_laps_remaining():
    assert a_state(laps_dropped=0).laps_remaining() == 14
    assert a_state(laps_dropped=1).laps_remaining() == 13


def test_and_that_is_a_lap_of_fuel_at_the_stop():
    """The whole point. One lap of extra fuel is about six seconds standing
    still at a litre a second."""
    without = fuel_target_l(a_state(laps_dropped=0))
    corrected = fuel_target_l(a_state(laps_dropped=1))
    assert without is not None and corrected is not None
    saved = without - corrected
    assert 5.0 < saved < 6.5, (
        f"a dropped crossing should cost about one lap of fuel, got {saved:.2f} L")


def test_it_never_goes_negative():
    """A correction that overshoots the flag would be worse than the error."""
    assert a_state(lap=27, laps_dropped=3).laps_remaining() == 0


def test_a_race_with_no_dropped_crossing_is_untouched():
    """Watkins recorded 20 rows for 20 laps. Nothing should move there."""
    assert a_state(lap=5, laps_total=20, laps_dropped=0).laps_remaining() == 15


def test_gt7s_own_count_is_recorded_even_though_it_is_not_trusted(store):
    """**The claim that has never been checked.**

    `session_state` counts laps from `last_lap_ms` and not from GT7's
    `laps_completed`, on the stated grounds that "GT7's lap counter is
    unreliable and its indexing convention differs between race types". That
    may be true. Nothing recorded the field, so the claim and its refutation
    were equally unavailable - and the driver's own instinct is that the count
    is in the UDP.

    It is recorded now, beside the app's own count, so one race settles it.
    """
    from pitcrew.telemetry.session_state import Lap

    event_id = store.create_event(
        name="Monza", track="Autodromo Nazionale Monza", layout="Full",
        car_name="Porsche 911 RSR (991) '17", race_type="laps", race_laps=27,
        game_version="1.71")
    session_id = store.start_session(event_id, "race", game_version="1.71")
    store.add_lap(session_id, Lap(
        lap_num=13, lap_time_ms=110_000, best_lap_ms=109_000, delta_ms=1_000,
        fuel_start=60.0, fuel_end=54.5, fuel_used=5.5, position=1,
        is_pit_lap=True, is_out_lap=False, laps_completed=14))

    row = store._query(
        "SELECT lap_num, laps_completed FROM laps WHERE session_id = ?",
        (session_id,))[0]
    assert row["lap_num"] == 13, "the app's own count"
    assert row["laps_completed"] == 14, "and GT7's, for comparison"
