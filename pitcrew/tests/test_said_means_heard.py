"""A volunteered fact is retired when the driver HEARD it, not when it was queued.

The voice fix (14 Sep 2026) gave every line a class, and NEWS - a rival's
stop, a place - now waits for a straight and can go stale, be replaced by a
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


def test_news_that_goes_stale_waiting_for_a_straight_answers_false(
        monkeypatch):
    monkeypatch.setattr(voice_module, "NEWS_STALE_AFTER_S", 0.1)
    engine = NullEngine()
    speaker = Voice(engine, enabled=True)
    speaker.listen_on(lambda clip_s, strict: False)       # no straight
    answers: list[bool] = []
    try:
        speaker.say("Car #76 has boxed.", kind=RIVAL_BOXED,
                    on_done=answers.append)
        assert _until(lambda: answers == [False])
        assert engine.lines == []
    finally:
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
    """The whole loop on the voice thread: gate shut, the line goes stale,
    the race offers it again, the gate opens, it plays - once."""
    monkeypatch.setattr(voice_module, "NEWS_STALE_AFTER_S", 0.1)
    engine = NullEngine()
    speaker = Voice(engine, enabled=True)
    straight = {"open": False}
    speaker.listen_on(lambda clip_s, strict: straight["open"])
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
        assert _until(lambda: answers == [False])
        straight["open"] = True
        again = offered(co, seconds=RaceCoordinator.MID_LAP_SPACING_S + 1)
        assert len(again) == 1
        hand(again[0])
        assert _until(lambda: answers == [False, True])
        assert offered(co, seconds=2 * RaceCoordinator.MID_LAP_SPACING_S) == []
        assert engine.lines == [first[0].spoken()]
    finally:
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

    def listen_on(self, gate):
        pass

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
