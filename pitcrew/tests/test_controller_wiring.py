"""Wirings asserted by driving the controller, not by reading it.

A whole-session review built one mutant for each of the wirings below and
**all eight survived the suite**. Four were guarded by nothing at all; four by
tests that matched a string in `inspect.getsource`, which a mutant can satisfy
while breaking the behaviour - a line reading `status_every_laps = 5` contains
the string, and a `pass` under a guard leaves the guard's text intact.

That is the defect this whole session kept finding, written into the tests
meant to prevent it. Every test here starts a real race through the real
controller and asserts on what reached the driver, the store, or the
coordinator.
"""
from __future__ import annotations

from dataclasses import replace

from pitcrew.race.calls import STATUS, Call
from pitcrew.strategy.handover import Handover, PlaybookEntry, accept
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent
from pitcrew.ui.strategy_screen import LoadedCard

from .test_race_wiring import a_lap, green, raced, voice  # noqa: F401
from .test_controller import qt_app  # noqa: F401


def a_call_event(controller, *, kind: str = STATUS, drop=None):
    """Put one known call on the next crossing, and hand back the event."""
    controller.race.handle = lambda event, packet=None: Call(
        kind, 3, "Lap 3. 17 laps to go. P4.", "", short_shift_drop_rpm=drop)
    return SessionEvent(EventKind.LAP_COMPLETED, {"lap": Lap(
        lap_num=3, lap_time_ms=94_000, best_lap_ms=94_000, delta_ms=0,
        fuel_start=40.0, fuel_end=36.6, fuel_used=3.4, position=4,
        is_pit_lap=False, is_out_lap=False)})


# ------------------------------------------------------------- the heartbeat

def test_the_interval_comes_from_the_setting(raced):
    """Not "the source mentions it" - the race carries the driver's number."""
    controller, _, _, _ = raced
    controller.settings = replace(controller.settings, status_every_laps=3)

    assert controller.start_race() is True
    assert controller.race.state.status_every_laps == 3


def test_the_heartbeat_does_not_withdraw_a_short_shift(raced):
    """The controller clears the beep on any call that does not ask for one -
    `None` there means "stop short-shifting". At the every-lap setting the
    heartbeat lands on the crossing after almost every real call, so without
    an exemption it withdraws the instruction the lap after it was given,
    silently, every time."""
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    moved: list = []
    controller.bridge.set_short_shift = moved.append

    controller._on_race_event(a_call_event(controller))

    assert moved == [], "the heartbeat reached set_short_shift"


def test_a_call_that_asks_for_one_still_moves_the_beep(raced):
    """The other half: the exemption must not disarm the instruction."""
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    moved: list = []
    controller.bridge.set_short_shift = moved.append

    controller._on_race_event(a_call_event(controller, kind="fuel-short",
                                           drop=450.0))

    assert moved == [450.0]


def test_the_straight_line_survives_a_heartbeat(raced):
    """`_on_straight_reached` stands down when the lap has already had a word,
    and at the every-lap setting the heartbeat is that word on every crossing
    - so the guard, written as `last_said_lap == lap`, retired the mid-lap
    data line for the whole race. The heartbeat reports; it does not occupy
    the lap.

    The colour tier on the CROSSING is a different decision and deliberately
    the other way: §5.5 is one thing at a time, and what that tier held which
    could not be lost - the gauge prompt, the only wear evidence that exists
    in VR - is carried inside the heartbeat itself now.
    """
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    state = controller.race.state
    state.lap = 4
    state.record(Call(STATUS, 4, "Lap 4. 16 laps to go. P4.", ""))
    assert state.only_the_heartbeat_this_lap() is True

    said: list = []
    controller._colour.data_line = lambda **kwargs: said.append(kwargs) or None
    controller.settings = replace(controller.settings, colour_calls="chatty")
    # On a straight or not: since 15 Sep 2026 the line asks only whether the
    # radio is clear. Fed one anyway, so a straight cannot be what refuses it.
    on_a_straight(controller)

    controller._on_straight_reached()

    assert said, "the straight data line was retired by the heartbeat"


def on_a_straight(controller, held_s: float = 6.0) -> None:
    """Feed the live straight detector a flat, full-throttle run."""
    import time

    now = time.monotonic()
    controller.bridge.straight.reset()
    for at in (now - held_s, now):
        controller.bridge.straight.update(throttle_pct=100.0, speed_ms=60.0,
                                          yaw_rate=0.0, now=at)


# ------------------------------------------------------------- the race path

def test_the_clock_is_stamped_before_the_lap_row_is_written(raced, store):
    """Two queued slots on one thread run in order. The stamp lived in the
    coordinator's, which runs second, so all three columns were NULL on every
    lap ever written - a write-only column the next audit would trust."""
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    for lap_num in range(1, 4):
        a_lap(controller, lap_num, 92.0 - lap_num * 3.4)

    rows = store._query(
        "SELECT race_elapsed_s FROM laps WHERE session_id = ? "
        "AND race_elapsed_s IS NOT NULL", (controller.session_id,))
    assert rows, "the clock never reached a lap row"


def test_a_stored_context_is_read_key_by_key(raced):
    """`PlanContext(**stored)` raises `TypeError` on any key the dataclass
    does not declare - on the grid, with nothing catching it. A context is
    data from a file the moment a plan can be authored anywhere else."""
    controller, screen, store, event_id = raced
    approved = store.get_approved_strategy(event_id)
    plan = dict(approved["plan"])
    plan["context"] = {**plan["context"], "written_by": "a later version"}
    strategy_id = store.save_strategy(event_id, plan, label="extra key")
    store.approve_strategy(strategy_id)

    assert controller.start_race() is True, screen.subtitle.text()


def test_the_regulations_reach_the_coordinator(raced):
    """`mandatory_stops` was passed only by a hand-run tool, so
    `mandatory_stops_left` was 0 in every race and `stop_still_needed`
    short-circuited past the regulation test forever - George would cancel a
    stop the rules require, and say so out loud."""
    controller, _, store, event_id = raced
    store.update_event(event_id, mandatory_stops=1)
    controller.load_active_event()

    assert controller.start_race() is True
    assert controller.race._mandatory_stops == 1, \
        "the event's regulation never reached the coordinator"


# ---------------------------------------------------------- the loaded plan

def a_handover() -> Handover:
    return Handover(
        plan={"stints": [{"laps": 12, "compound": "RM", "fuel_l": 80.0},
                         {"laps": 8, "compound": "RM", "fuel_l": 50.0,
                          "tyres": True}],
              "stops": 1, "pit_laps": [12], "binding_constraint": "fuel"},
        playbook=[PlaybookEntry(trigger="fuel_short", action="short_shift",
                                when="more than 0.5 laps short")])


def test_a_loaded_plan_reaches_the_screen_on_a_build(raced):
    controller, _, store, event_id = raced
    accept(store, event_id, a_handover(), label="Ludo")

    controller.build_strategy()

    assert controller.strategy.findChildren(LoadedCard), \
        "the loaded plan never reached the Strategy screen"


def test_approving_a_loaded_plan_is_connected(raced):
    """A screen signal nobody connected is a button that does nothing."""
    controller, _, store, event_id = raced
    strategy_id, _ = accept(store, event_id, a_handover(), label="Ludo")

    controller.strategy.approve_loaded_requested.emit(strategy_id)

    approved = store.get_approved_strategy(event_id)
    assert approved is not None and approved["id"] == strategy_id


def test_a_handover_without_start_laps_does_not_box_every_lap(store,
                                                              event_id):
    """**The worst finding of the review.** `_apply_stint` reads
    `start = stint.get("start_lap") or 1`, and nothing required, validated or
    derived it - not the CLI's help, not `certify`, and there is no handover
    schema document. A plan in the shape the CLI documents put every stint's
    end at lap N, and the box call then fired on the lap after the stop and
    every lap to the flag: twelve in a row, "3 laps overdue", "4 laps
    overdue". `_reconsider_ignored_box` cannot rescue it, because
    `stay_out_call` returns None exactly when the fuel cannot reach.
    """
    strategy_id, problems = accept(store, event_id, a_handover())
    assert strategy_id is not None, problems

    stored = next(r for r in store.list_strategies(event_id)
                  if r["id"] == strategy_id)["plan"]

    assert [s["start_lap"] for s in stored["stints"]] == [1, 13], stored
