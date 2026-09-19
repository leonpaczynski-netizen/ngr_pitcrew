"""A volunteered fact is retired when the driver HEARD it, not when it was queued.

The voice fix (14 Sep 2026) gave every line a class, and NEWS - a rival's
stop, a place - can wait behind other speech and go stale, be replaced by a
newer place, or be dropped for an instruction. The rival fix retired a stop
and booked a place when it was handed to the voice. Put together, a dropped
line lost the fact exactly as the Bathurst queue did: eight of ten stops never
said. So the voice answers (`say(..., on_done=)`), the controller carries the
answer back to the Qt thread, and the race retires on "heard" only.

And the call sites pass their kinds, so the classes the voice fix built are
the classes the race actually plays in.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from pitcrew.engineer import voice as voice_module
from pitcrew.engineer.voice import NEWS, NullEngine, Voice, class_of
from pitcrew.race.calls import (BOX_NOW, POSITION, RIVAL_BOXED, STATUS, Call)
from pitcrew.race.coordinator import RaceCoordinator, RacePhase
from pitcrew.race.pit_wall import Entered
from pitcrew.telemetry.recorder import SAMPLE_HZ

from .test_controller import qt_app  # noqa: F401
from .test_controller_wiring import a_call_event
from .test_race_wiring import green, raced, voice  # noqa: F401


def _until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


# ------------------------------------------------------------ the voice

class Held:
    """Records every line; the first one plays until released."""

    name = "held"

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.started = threading.Event()
        self.release = threading.Event()

    def speak(self, text: str) -> None:
        self.lines.append(text)
        self.started.set()
        self.release.wait(5.0)


def test_a_line_that_plays_answers_true_once():
    engine = NullEngine()
    speaker = Voice(engine, enabled=True)
    answers: list[bool] = []
    try:
        speaker.say("Car #76 has boxed.", kind=RIVAL_BOXED,
                    on_done=answers.append)
        assert _until(lambda: answers == [True])
        time.sleep(0.05)
        assert answers == [True]
    finally:
        speaker.stop()


def test_news_that_goes_stale_behind_other_speech_answers_false(
        monkeypatch):
    monkeypatch.setattr(voice_module, "NEWS_STALE_AFTER_S", 0.1)
    engine = Held()
    speaker = Voice(engine, enabled=True)
    answers: list[bool] = []
    try:
        speaker.say("Box this lap.", kind=BOX_NOW)        # holds the card
        assert engine.started.wait(2.0)
        speaker.say("Car #76 has boxed.", kind=RIVAL_BOXED,
                    on_done=answers.append)
        time.sleep(0.3)
        engine.release.set()
        assert _until(lambda: answers == [False])
        assert engine.lines == ["Box this lap."]
    finally:
        engine.release.set()
        speaker.stop()


def test_a_place_replaced_by_a_newer_one_answers_false():
    engine = Held()
    speaker = Voice(engine, enabled=True)
    older: list[bool] = []
    newer: list[bool] = []
    try:
        speaker.say("Lap 6.", kind=STATUS)                # holds the card
        assert engine.started.wait(2.0)
        speaker.say("P8 of 13. You've made a place.", kind=POSITION,
                    on_done=older.append)
        speaker.say("P7 of 13. You've made a place.", kind=POSITION,
                    on_done=newer.append)
        assert older == [False]                           # replaced, at once
        engine.release.set()
        assert _until(lambda: newer == [True])
    finally:
        engine.release.set()
        speaker.stop()


def test_a_voice_that_is_off_answers_false_and_a_raising_callback_is_survived():
    off = Voice(NullEngine(), enabled=False)
    answers: list[bool] = []
    off.say("Car #76 has boxed.", kind=RIVAL_BOXED, on_done=answers.append)
    assert answers == [False]

    engine = NullEngine()
    speaker = Voice(engine, enabled=True)

    def broken(_played):
        raise RuntimeError("the caller's bookkeeping")

    try:
        speaker.say("First.", on_done=broken)
        speaker.say("Second.")
        assert _until(lambda: engine.lines == ["First.", "Second."])
    finally:
        speaker.stop()


def test_car_hash_n_is_said_as_car_n_everywhere_the_voice_speaks():
    assert voice_module.spoken_form("Car #76 has boxed on 5 litres.") == \
        "Car 76 has boxed on 5 litres."
    assert voice_module.spoken_form("A stop now puts you behind Car #4.") == \
        "A stop now puts you behind Car 4."
    assert voice_module.spoken_form("Box this lap.") == "Box this lap."
    engine = NullEngine()
    voice = Voice(engine, enabled=True)
    try:
        voice.say("Car #31 and Car #28 have boxed.")
        deadline = time.monotonic() + 2.0
        while not engine.lines and time.monotonic() < deadline:
            time.sleep(0.01)
        assert engine.lines == ["Car 31 and Car 28 have boxed."]
    finally:
        voice.stop()


# ------------------------------------------------------------ the race

@dataclass
class _Packet:
    current_position: int = 9
    cars_in_race: int = 13
    surface_types: tuple = ("T", "T", "T", "T")
    laps_completed: int | None = None


def a_race() -> RaceCoordinator:
    co = RaceCoordinator()
    co.acknowledged_delivery = True
    co.phase = RacePhase.RUNNING
    co.state.laps_total = 20
    co.state.lap = 8
    co.state.position = 9
    co.state.position_said = 9
    co._note_crossing_for_mid_lap()
    co._crossed_at_packet = -10 * 60        # the crossing is well past
    return co


def a_stop(co, driver="Car #76"):
    co.note_rival_entered(Entered(driver=driver, driver_id=0, lap=8,
                                  fuel_in_l=5, partial=False))


def offered(co, packet=None, seconds: float = 1.0) -> list[Call]:
    """Every call the mid-lap slot hands out over `seconds` of frames."""
    out = []
    for _ in range(int(seconds * SAMPLE_HZ)):
        call = co.note_packet(packet or _Packet())
        if call is not None:
            out.append(call)
    return out


def test_a_dropped_rival_stop_is_offered_again_and_said_once():
    co = a_race()
    a_stop(co)
    first = offered(co)
    assert [c.kind for c in first] == [RIVAL_BOXED]
    # In flight: not offered again while the voice holds it.
    assert offered(co, seconds=RaceCoordinator.MID_LAP_SPACING_S + 1) == []

    co.delivered(first[0], False)                     # stale, never heard
    again = offered(co, seconds=RaceCoordinator.MID_LAP_SPACING_S + 1)
    assert [c.spoken() for c in again] == [first[0].spoken()]

    co.delivered(again[0], True)                      # heard
    assert offered(co, seconds=2 * RaceCoordinator.MID_LAP_SPACING_S) == []
    assert co.state.lane.untold(co.state.lap) == []


def test_a_rival_stop_heard_is_never_repeated():
    co = a_race()
    a_stop(co)
    call = offered(co)[0]
    co.delivered(call, True)
    co.delivered(call, False)                         # a late, stray answer
    assert offered(co, seconds=3 * RaceCoordinator.MID_LAP_SPACING_S) == []


def test_a_dropped_stop_still_goes_stale():
    """Released, it is untold again - and `LaneLog.stale` still applies."""
    co = a_race()
    a_stop(co)
    call = offered(co)[0]
    co.state.lane.left("Car #76", lap=8)
    co.state.lap = 10                                 # a lap since he left
    co.delivered(call, False)
    assert co.state.lane.untold(co.state.lap) == []


def test_a_place_is_booked_only_when_heard():
    co = a_race()
    packet = _Packet(current_position=8)
    place = [c for c in offered(co, packet, seconds=10) if c.kind == POSITION]
    assert [c.position_called for c in place] == [8]
    assert co.state.position_said == 9                # handed over, not heard

    co.delivered(place[0], False)
    assert co.state.position_said == 9
    again = [c for c in offered(co, packet,
                                seconds=RaceCoordinator.MID_LAP_SPACING_S + 1)
             if c.kind == POSITION]
    assert [c.position_called for c in again] == [8]
    co.delivered(again[0], True)
    assert co.state.position_said == 8
    assert offered(co, packet, seconds=RaceCoordinator.MID_LAP_SPACING_S + 1) \
        == []


def test_a_hand_over_nobody_answers_is_released():
    """Rule 10: a fact nothing can retire is a latch."""
    co = a_race()
    a_stop(co)
    first = offered(co)
    assert first
    seconds = RaceCoordinator.ACK_TIMEOUT_S + 2
    again = offered(co, seconds=seconds)
    assert [c.spoken() for c in again] == [first[0].spoken()]


def test_a_crossing_rival_call_unheard_is_sayable_again():
    """The crossing path books a rival fact by its tag; unheard, it is not."""
    co = a_race()
    a_stop(co)
    from pitcrew.race.rival_calls import boxed_call

    call = boxed_call(co.state)
    co.state.record(call)
    co._hand_out(call)
    assert call.tag in co.state.said_tags
    assert co.state.lane.untold(co.state.lap) == []
    co.delivered(call, False)
    assert call.tag not in co.state.said_tags
    assert [s.driver for s in co.state.lane.untold(co.state.lap)] == ["Car #76"]


def test_through_a_real_voice_a_stale_stop_comes_back_and_is_said_once(
        monkeypatch):
    """The whole loop on the voice thread: queued behind a long line, the
    stop goes stale, the race offers it again onto a free radio, it plays -
    once."""
    monkeypatch.setattr(voice_module, "NEWS_STALE_AFTER_S", 0.1)
    engine = Held()
    speaker = Voice(engine, enabled=True)
    speaker.say("Box this lap.", kind=BOX_NOW)            # holds the card
    assert engine.started.wait(2.0)
    co = a_race()
    a_stop(co)
    answers: list[bool] = []

    def hand(call):
        def done(played):
            answers.append(played)
            co.delivered(call, played)
        speaker.say(call.spoken(), kind=call.kind, on_done=done)

    try:
        first = offered(co)
        hand(first[0])
        time.sleep(0.3)
        engine.release.set()                              # the box call ends
        assert _until(lambda: answers == [False])
        again = offered(co, seconds=RaceCoordinator.MID_LAP_SPACING_S + 1)
        assert len(again) == 1
        hand(again[0])
        assert _until(lambda: answers == [False, True])
        assert offered(co, seconds=2 * RaceCoordinator.MID_LAP_SPACING_S) == []
        # Said once - and said as words, not "Car hash 76" (D7, 14 Sep 2026).
        assert engine.lines == [
            "Box this lap.", voice_module.spoken_form(first[0].spoken())]
        assert engine.lines[1] == "Car 76 boxed."
    finally:
        engine.release.set()
        speaker.stop()


# ------------------------------------------------------------ the controller

class Recorder:
    """A voice that records the kind and the acknowledgement it was given."""

    enabled = True
    busy = False

    def __init__(self) -> None:
        self.said: list[tuple[str, str | None, object]] = []

    def say(self, text, kind=None, on_done=None):
        self.said.append((text, kind, on_done))

    def stop(self):
        pass


def test_the_crossing_passes_its_kind(raced):
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    controller.voice = Recorder()
    controller._on_race_event(a_call_event(controller, kind=BOX_NOW))
    assert [kind for _, kind, _ in controller.voice.said] == [BOX_NOW]


def test_a_box_call_plays_ahead_of_a_queued_status_line(raced):
    """Through the controller's own call sites and a real queue."""
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    engine = Held()
    controller.voice = Voice(engine, enabled=True)
    try:
        controller.voice.say("Radio check.")          # on the card
        assert engine.started.wait(2.0)
        controller._on_race_event(a_call_event(controller, kind=STATUS))
        event = a_call_event(controller, kind=BOX_NOW)
        box = Call(BOX_NOW, 4, "Box this lap.", "On the plan.")
        controller.race.handle = lambda event, packet=None: box
        controller._on_race_event(event)
        engine.release.set()
        assert _until(lambda: len(engine.lines) == 3)
        assert engine.lines[1] == "Box this lap. On the plan."
        assert engine.lines[2].startswith("Lap 3.")
    finally:
        engine.release.set()
        controller.voice.stop()


def test_a_rival_stop_mid_lap_is_news_and_is_retired_when_heard(raced, qt_app):  # noqa: F811
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    race = controller.race
    assert race.acknowledged_delivery is True
    race.state.lap = 8
    race.state.laps_total = 20
    race._crossed_at_packet = -10 * 60
    a_stop(race)
    call = offered(race)[0]
    recorder = Recorder()
    controller.voice = recorder

    controller._on_position_changed(call)

    (text, kind, on_done), = recorder.said
    assert kind == RIVAL_BOXED and class_of(kind) == NEWS
    assert on_done is not None
    assert race.awaits_delivery(call)
    # Answered on another thread, delivered on this one through the signal.
    worker = threading.Thread(target=on_done, args=(True,))
    worker.start()
    worker.join()
    assert _until(lambda: (qt_app.processEvents() or True)
                  and not race.awaits_delivery(call))
    assert race.state.lane.told(race.state.lane.keys_in_tag(
        RIVAL_BOXED, call.tag)[0])


def test_the_league_line_queues_behind_the_place_it_follows(raced):
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    controller.voice = Recorder()
    controller._league_moved = lambda: "Up to championship P4."
    place = Call(POSITION, 3, "P8 of 13.", "You've made a place.",
                 position_called=8)
    controller._on_position_changed(place)
    assert [kind for _, kind, _ in controller.voice.said] == [POSITION,
                                                               POSITION]


def test_the_fill_in_the_box_is_an_instruction(raced):
    from pitcrew.engineer.voice import INSTRUCTION
    from pitcrew.race.refuel import TARGET

    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    controller.voice = Recorder()
    controller._voice_refuel(Call(TARGET, 11, "Fuel to 67 litres.",
                                  "8 laps to the flag."))
    (_, kind, _), = controller.voice.said
    assert kind == TARGET and class_of(kind) == INSTRUCTION


def test_a_silent_engineer_books_what_the_screen_showed(raced):
    controller, _, _, _ = raced
    controller.start_race()
    green(controller)
    race = controller.race
    race.state.lap = 8
    race._crossed_at_packet = -10 * 60
    a_stop(race)
    call = offered(race)[0]
    controller._engineer_speaks = False
    controller._on_position_changed(call)
    assert not race.awaits_delivery(call)
    assert race.state.lane.untold(race.state.lap) == []


def test_a_box_call_re_fires_on_its_own_without_any_release():
    """**The premise of 9e91674 was wrong, and this pins why.**

    That commit said a dropped box call left the next crossing on a heartbeat
    - "Lap 8. 13 laps to go." - and put `BOX_NOW` into the delivery protocol
    to fix it. The heartbeat came from a test that built a FRESH `RaceState`
    and copied `said` without `said_at`. On the real object the overdue
    crossing already says the whole call, compound and fill included, so the
    release fixed nothing and cost a lap of the stay-out fold.
    """
    from pitcrew.race.calls import BOX_NOW, RaceState, next_call

    state = RaceState(lap=6, laps_total=20, stint_ends_on_lap=7,
                      fuel_per_lap_l=3.4, fuel_capacity_l=100.0,
                      mandatory_stops_left=1, next_compound="RS",
                      next_tyres=True)
    state.last_said_lap = 0
    first = next_call(state)
    assert first.kind == BOX_NOW
    state.record(first)                 # made - and, say, never heard

    state.lap = 7                       # the SAME object, one lap on
    state.last_said_lap = 0
    again = next_call(state)
    assert again is not None and again.kind == BOX_NOW
    assert "RS on." in again.spoken() and "Fuel to" in again.spoken()


def test_the_box_calls_are_not_in_the_delivery_protocol():
    """They self-heal; the two stop reversals do not, so only they are in."""
    from pitcrew.race.calls import (BOX_NOW, BOX_SOON, MEDIUM, STOP_BACK,
                                    STOPS_OFF, Call)

    for kind in (BOX_NOW, BOX_SOON):
        assert not RaceCoordinator._heard_matters(
            Call(kind, 6, "Box this lap.", "On the plan.", MEDIUM)), kind
    for kind in (STOPS_OFF, STOP_BACK):
        assert RaceCoordinator._heard_matters(
            Call(kind, 6, "x.", "y.", MEDIUM)), kind


def test_an_unheard_stop_reversal_is_said_again_while_it_is_still_true():
    """**The two calls where silence is the worst answer.** A lost "You're
    fuelled to the flag." sends him into a stop he does not need; a lost "The
    stop is back on." runs him out of fuel. Both are made once behind a flag
    `record()` flips - and the release now reopens that flag."""
    from pitcrew.race.calls import MEDIUM, STOP_BACK, STOPS_OFF, Call

    co = RaceCoordinator()

    # Fuelled to the flag, and the latch still agrees: reopened.
    co.state.stop_needed_held = False
    co.state.stops_off_said = True
    co.state.said.append(STOPS_OFF)
    co._release(Call(STOPS_OFF, 8, "You're fuelled to the flag.", "", MEDIUM))
    assert co.state.stops_off_said is False and STOPS_OFF not in co.state.said

    # The stop is back on, and the latch still agrees: reopened.
    co.state.stop_needed_held = True
    co.state.stop_back_due = False
    co.state.said.append(STOP_BACK)
    co._release(Call(STOP_BACK, 9, "The stop is back on.", "", MEDIUM))
    assert co.state.stop_back_due is True and STOP_BACK not in co.state.said


def test_a_stop_reversal_that_is_no_longer_true_is_not_revived():
    """The gate reopens only while the latch still says what the call said -
    a stop retired again since must not be un-retired by a late release."""
    from pitcrew.race.calls import MEDIUM, STOP_BACK, Call

    co = RaceCoordinator()
    co.state.stop_needed_held = False          # retired again since
    co.state.stop_back_due = False
    co._release(Call(STOP_BACK, 9, "The stop is back on.", "", MEDIUM))
    assert co.state.stop_back_due is False
