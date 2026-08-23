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


# ---------------------------------------------------------------------------
# The live detector - Road Atlanta, 23 Aug 2026
#
# The correction above was right and arrived too late to be worth anything.
# The crossing went missing inside the box; the clock only counts at a
# crossing, so it said nothing until lap 12 finally completed at 20:42:36 -
# two minutes and one second AFTER the in-box fuel call went out at 20:40:35
# asking for "77 litres, 12 laps at this race's burn" against nine laps to
# run. He took 38.72 L, ran nine laps at a measured 6.283 L/lap and crossed
# the line with 13.23 L aboard: six and a half seconds parked at that
# league's 2.00 L/s.
#
# GT7 knew. Its own `laps_completed` moved by exactly 2 across the pit lap
# and by exactly 1 across all twenty others. The app had been storing that
# field on every lap the whole time and never read it.
# ---------------------------------------------------------------------------

# GT7's `laps_completed` as recorded against each app lap of session 77.
# Index 0 is app lap 1. Note the step of two at app lap 12, the pit lap.
ROAD_ATLANTA_GT7_COUNTER = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14,
                            15, 16, 17, 18, 19, 20, 21, 22, 23]


class _Packet:
    def __init__(self, laps_completed):
        self.laps_completed = laps_completed


def test_road_atlanta_the_counter_step_is_real_and_is_on_the_pit_lap():
    """The fixture itself, before any code is asked to interpret it."""
    steps = [b - a for a, b in zip(ROAD_ATLANTA_GT7_COUNTER,
                                   ROAD_ATLANTA_GT7_COUNTER[1:])]
    assert steps.count(2) == 1, "exactly one crossing went missing"
    assert steps.index(2) == 10, "and it was app lap 12, the pit lap"
    assert set(steps) == {1, 2}


def _coordinator_at_road_atlanta():
    from pitcrew.race.coordinator import RaceCoordinator, RacePhase
    co = RaceCoordinator()
    co.phase = RacePhase.RUNNING
    co._gt7_offset = 1          # learned at the first crossing: 2 - 1
    co.state.laps_total = 22
    return co


def test_the_missed_crossing_is_seen_in_the_box_not_at_the_next_crossing():
    """**The fix.** The app is still on lap 11's count, sitting in the box,
    and GT7's counter has already moved twice."""
    from pitcrew.race.coordinator import LAP_COUNTER_HOLD_FRAMES
    co = _coordinator_at_road_atlanta()
    co.state.lap = 11
    assert co.state.laps_dropped_seen == 0

    # GT7 crosses the line inside the pit sequence: 12 -> 13 while the app is
    # still on lap 11. Nothing is believed until the hold has elapsed.
    for _ in range(LAP_COUNTER_HOLD_FRAMES - 1):
        co.note_packet(_Packet(13))
    assert co.state.laps_dropped_seen == 0, "not before the hold"
    co.note_packet(_Packet(13))
    assert co.state.laps_dropped_seen == 1, "and the moment it has elapsed"

    # Which is the whole point: the fuel call now sizes to nine laps, not ten.
    co.state.laps_total = 22
    assert co.state.laps_remaining() == 22 - 12


def test_an_ordinary_crossing_does_not_count_as_a_missed_one():
    """GT7's counter moves a few frames before the app's own LAP_COMPLETED
    lands, so every clean lap shows this discrepancy briefly. Believing it
    would take a lap of fuel off the call and put him out of the race."""
    from pitcrew.race.coordinator import LAP_COUNTER_HOLD_FRAMES
    co = _coordinator_at_road_atlanta()
    co.state.lap = 5
    for _ in range(LAP_COUNTER_HOLD_FRAMES // 4):
        co.note_packet(_Packet(7))          # 7 - 1 - 5 = 1, transiently
    assert co.state.laps_dropped_seen == 0
    co.state.lap = 6                        # the crossing lands
    co._gt7_pending = 0
    co.note_packet(_Packet(7))
    assert co.state.laps_dropped_seen == 0


def test_the_whole_race_replays_with_exactly_one_correction():
    """Twenty-one crossings, one of them missing. Any detector that fires
    twice has double-counted, and one that never fires is the bug.

    The counter is driven the way GT7 actually drives it: it sits on the value
    it held at the last crossing for the whole lap, and steps at the crossing.
    On the pit lap it steps mid-lap instead - which is the missed crossing, and
    the only thing this detector is looking for.
    """
    from pitcrew.race.coordinator import LAP_COUNTER_HOLD_FRAMES
    co = _coordinator_at_road_atlanta()
    at_last_crossing = 1                    # GT7's value before app lap 1
    for app_lap, at_this_crossing in enumerate(ROAD_ATLANTA_GT7_COUNTER,
                                               start=1):
        co.state.lap = app_lap - 1
        co._gt7_pending = 0
        mid_lap = at_last_crossing
        if at_this_crossing - at_last_crossing == 2:
            # The crossing inside the box: GT7 counts it, the app never hears
            # about it, and the rest of the lap is driven out of step.
            mid_lap = at_last_crossing + 1
        for _ in range(LAP_COUNTER_HOLD_FRAMES):
            co.note_packet(_Packet(mid_lap))
        co.state.lap = app_lap              # the crossing the app does see
        co._gt7_pending = 0
        at_last_crossing = at_this_crossing
    assert co.state.laps_dropped_seen == 1


def test_it_fires_on_the_pit_lap_and_no_other():
    """Where the correction appears matters as much as that it appears."""
    from pitcrew.race.coordinator import LAP_COUNTER_HOLD_FRAMES
    co = _coordinator_at_road_atlanta()
    fired_on = []
    at_last_crossing = 1
    for app_lap, at_this_crossing in enumerate(ROAD_ATLANTA_GT7_COUNTER,
                                               start=1):
        before = co.state.laps_dropped_seen
        co.state.lap = app_lap - 1
        co._gt7_pending = 0
        mid_lap = at_last_crossing + (
            1 if at_this_crossing - at_last_crossing == 2 else 0)
        for _ in range(LAP_COUNTER_HOLD_FRAMES):
            co.note_packet(_Packet(mid_lap))
        if co.state.laps_dropped_seen > before:
            fired_on.append(app_lap)
        co.state.lap = app_lap
        co._gt7_pending = 0
        at_last_crossing = at_this_crossing
    assert fired_on == [12], "the pit lap, and nothing else"


def test_nothing_fires_before_the_first_crossing():
    """A detector that can fire on lap zero can fire on a formation lap."""
    from pitcrew.race.coordinator import LAP_COUNTER_HOLD_FRAMES
    co = _coordinator_at_road_atlanta()
    co.state.lap = 0
    for _ in range(LAP_COUNTER_HOLD_FRAMES * 2):
        co.note_packet(_Packet(5))
    assert co.state.laps_dropped_seen == 0


def test_a_counter_that_jumps_absurdly_is_ignored():
    """A restart or a bad read is not a pit stop. Sizing a fill from it is
    exactly the failure the guard exists to prevent."""
    from pitcrew.race.coordinator import LAP_COUNTER_HOLD_FRAMES
    co = _coordinator_at_road_atlanta()
    co.state.lap = 5
    for _ in range(LAP_COUNTER_HOLD_FRAMES * 2):
        co.note_packet(_Packet(40))
    assert co.state.laps_dropped_seen == 0


def test_the_two_detectors_never_double_count():
    """The clock counts at the crossing, GT7's counter within a packet of the
    event. On an ordinary missed lap both report the same one, and adding them
    would take two laps of fuel out of the call."""
    state = a_state(lap=13, laps_total=27, laps_dropped=1)
    state.laps_dropped_seen = 1
    assert state.laps_missed() == 1
    assert state.laps_remaining() == 13


def test_either_detector_alone_still_corrects():
    """They are independent. Whichever sees it first is enough."""
    only_clock = a_state(laps_dropped=1)
    only_clock.laps_dropped_seen = 0
    only_live = a_state(laps_dropped=0)
    only_live.laps_dropped_seen = 1
    assert only_clock.laps_remaining() == only_live.laps_remaining() == 13


# ---------------------------------------------------------------------------
# The wiring, driven through `handle()` rather than around it.
#
# The first version of this fix learned its counter offset from a `packet`
# argument. The only production caller passes no packet at all, so the offset
# stayed None for the whole race and the detector never once ran - while every
# test above passed, because they all set `_gt7_offset` by hand.
# ---------------------------------------------------------------------------

def _a_lap(lap_num: int, counted: int, *, pit: bool = False):
    from pitcrew.telemetry.session_state import Lap

    return Lap(lap_num=lap_num, lap_time_ms=81_500, best_lap_ms=81_500,
               delta_ms=0, fuel_start=90.0, fuel_end=83.7, fuel_used=6.28,
               position=3, is_pit_lap=pit, is_out_lap=False,
               laps_completed=counted)


def _running_coordinator():
    from pitcrew.race.coordinator import RaceCoordinator, RacePhase

    co = RaceCoordinator()
    co.phase = RacePhase.RUNNING
    co.state.laps_total = 22
    return co


def _crossing(co, lap):
    from pitcrew.telemetry.session_state import EventKind, SessionEvent

    co.handle(SessionEvent(kind=EventKind.LAP_COMPLETED, data={"lap": lap}))


def test_the_offset_is_learned_through_handle_with_no_packet():
    """**The defect that shipped.** `handle(event)` is how the controller
    calls this, and it passes no packet."""
    co = _running_coordinator()
    _crossing(co, _a_lap(1, ROAD_ATLANTA_GT7_COUNTER[0]))
    assert co._gt7_offset == 1, (
        "the counter offset was not learned from the lap, so the detector is "
        "dead in every real race")


def test_the_missed_crossing_is_caught_after_a_real_crossing_armed_it():
    """End to end: crossings through `handle`, frames through `note_packet`,
    nothing set by hand."""
    from pitcrew.race.coordinator import LAP_COUNTER_HOLD_FRAMES

    co = _running_coordinator()
    for lap_num in range(1, 12):
        _crossing(co, _a_lap(lap_num, ROAD_ATLANTA_GT7_COUNTER[lap_num - 1]))
    assert co.state.laps_dropped_seen == 0, "eleven clean laps say nothing"

    # In the box. GT7 counts the crossing the app never hears about.
    for _ in range(LAP_COUNTER_HOLD_FRAMES):
        co.note_packet(_Packet(13))
    assert co.state.laps_dropped_seen == 1
    assert co.state.laps_remaining() == 22 - 12, (
        "the fill is sized for what is left, not for the app's short count")


def test_a_slow_crossing_does_not_latch_a_lap_of_fuel_out_of_the_race():
    """`note_packet` runs on the telemetry thread and the crossing arrives on
    the Qt thread behind a queued signal, so the two are briefly out of step
    at EVERY lap. A claim that could not be withdrawn would take a lap of fuel
    off every remaining fill for the rest of the race."""
    from pitcrew.race.coordinator import LAP_COUNTER_HOLD_FRAMES

    co = _running_coordinator()
    _crossing(co, _a_lap(1, 2))
    # GT7 has counted lap 2 while the app's LAP_COMPLETED is still queued.
    for _ in range(LAP_COUNTER_HOLD_FRAMES * 2):
        co.note_packet(_Packet(3))
    assert co.state.laps_dropped_seen == 1, "believed, for now"
    _crossing(co, _a_lap(2, 3))                 # the app catches up
    co.note_packet(_Packet(3))
    assert co.state.laps_dropped_seen == 0, "and withdrawn once it agrees"


def test_paused_frames_cannot_manufacture_a_crossing():
    """The app's lap count is frozen on a pause by construction, so two
    seconds of paused frames would otherwise look exactly like a missed lap."""
    from pitcrew.race.coordinator import LAP_COUNTER_HOLD_FRAMES

    class _Paused(_Packet):
        paused = True

    co = _running_coordinator()
    _crossing(co, _a_lap(1, 2))
    for _ in range(LAP_COUNTER_HOLD_FRAMES * 2):
        co.note_packet(_Paused(3))
    assert co.state.laps_dropped_seen == 0


def test_the_timed_race_distance_absorbs_the_correction_once_only():
    """`laps_total` is recomputed from the clock at each crossing of a timed
    race. If it did not include the correction, `laps_remaining` would apply
    it a SECOND time - which under-fuels, and running dry loses the race."""
    state = a_state(lap=12, laps_total=None)
    state.laps_dropped_seen = 1
    # What `_update_clock_distance` now writes: completed + missed + left.
    left = 9
    state.laps_total = state.lap + state.laps_missed() + left
    assert state.laps_remaining() == left, "exactly the clock's own answer"
