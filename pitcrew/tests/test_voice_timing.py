"""When a line is said: what plays first, what is dropped, what goes stale.

Bathurst, 14 Sep 2026. The voice was one FIFO: the straight's data line
arrived a second into the 5.5 s heartbeat and reached the driver 4.8-7.0 s
after it was composed, in the braking zone for Hell Corner; a full queue
dropped its oldest line whatever it was. No audio device here - every engine
is a recorder.
"""
from __future__ import annotations

import threading
import time

import pytest

from pitcrew.engineer import voice as voice_module
from pitcrew.engineer.voice import (
    COLOUR,
    EVENT,
    INSTRUCTION,
    NEWS,
    Voice,
    _LineQueue,
    class_of,
    stale_after_s,
)
from pitcrew.race.calls import (
    BOX_NOW,
    FUEL_SHORT,
    POSITION,
    RIVAL_BOXED,
    STATUS,
    STOP_BACK,
)
from pitcrew.race.colour import BEST_LAP, DATA
from pitcrew.race.refuel import RELEASE


HEARTBEAT = "Lap 6. 15 laps to go. P9. Fuel good to the stop."
PLACE = "P8 of 13. You've made a place."
BOX = "Box this lap. RS on. The regulations need a stop."
DATA_LINE = "6 laps to the stop."


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


def _until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


# ------------------------------------------------------------------ classes

def test_every_kind_has_the_class_its_urgency_earns():
    assert class_of(BOX_NOW) == INSTRUCTION
    assert class_of(FUEL_SHORT) == INSTRUCTION
    assert class_of(STOP_BACK) == INSTRUCTION
    assert class_of(RELEASE) == INSTRUCTION
    # Said at the crossing, which is when it is meant to be said.
    assert class_of(STATUS) == EVENT
    assert class_of(BEST_LAP) == EVENT
    # Said mid-lap, wherever the car happens to be.
    assert class_of(POSITION) == NEWS
    assert class_of(RIVAL_BOXED) == NEWS
    assert class_of(DATA) == COLOUR
    # No kind is the old behaviour, and so is a kind nobody classified.
    assert class_of(None) == EVENT
    assert class_of("something-new") == EVENT


def test_staleness_is_per_kind():
    """A data line five seconds late is worse than none; a rival in his box
    is still there while news waits for a straight; a box call is not said
    ten seconds after it was true."""
    assert stale_after_s(DATA) == voice_module.DATA_STALE_AFTER_S == 1.5
    assert stale_after_s(BOX_NOW) == voice_module.STALE_AFTER_S
    assert stale_after_s(None) == voice_module.STALE_AFTER_S
    assert stale_after_s(STATUS) == voice_module.STALE_AFTER_S
    assert stale_after_s(RIVAL_BOXED) == voice_module.NEWS_STALE_AFTER_S
    assert stale_after_s(POSITION) == voice_module.POSITION_STALE_AFTER_S
    assert (stale_after_s(DATA) < stale_after_s(BOX_NOW)
            < stale_after_s(RIVAL_BOXED))


# ------------------------------------------------------------------ ordering

def test_an_instruction_plays_before_news_queued_ahead_of_it():
    engine = Held()
    speaker = Voice(engine)
    speaker.say("Radio check.")
    assert engine.started.wait(2.0)
    speaker.say(HEARTBEAT, kind=STATUS)
    speaker.say(PLACE, kind=POSITION)
    speaker.say(DATA_LINE, kind=DATA)
    speaker.say(BOX, kind=BOX_NOW)
    engine.release.set()
    assert _until(lambda: len(engine.lines) == 5), engine.lines
    speaker.stop()
    assert engine.lines == ["Radio check.", BOX, HEARTBEAT, PLACE, DATA_LINE], (
        "instruction, then the crossing's event, then news, colour last")


def test_a_playing_line_is_never_cut_for_an_instruction():
    engine = Held()
    speaker = Voice(engine)
    speaker.say(DATA_LINE, kind=DATA)
    assert engine.started.wait(2.0)
    speaker.say(BOX, kind=BOX_NOW)
    time.sleep(0.1)
    assert engine.lines == [DATA_LINE], "the instruction cut in mid-clip"
    engine.release.set()
    assert _until(lambda: engine.lines == [DATA_LINE, BOX])
    speaker.stop()


def test_busy_while_playing_and_while_queued():
    engine = Held()
    speaker = Voice(engine)
    assert speaker.busy is False
    speaker.say(PLACE, kind=POSITION)
    assert engine.started.wait(2.0)
    assert speaker.busy is True
    engine.release.set()
    assert _until(lambda: speaker.busy is False)
    speaker.stop()


# --------------------------------------------------------------- the drops

def _texts(q: _LineQueue) -> list[str]:
    return [line.text for line in q.snapshot()]


def test_a_full_queue_drops_colour_before_an_instruction(monkeypatch):
    monkeypatch.setattr(voice_module, "MAX_QUEUED", 3)
    q = _LineQueue()
    q.offer(q.line(BOX, BOX_NOW))
    q.offer(q.line(DATA_LINE, DATA))
    q.offer(q.line(HEARTBEAT, STATUS))
    dropped = q.offer(q.line("Fuel to 67 litres.", FUEL_SHORT))
    assert [line.text for line, _ in dropped] == [DATA_LINE]
    assert DATA_LINE not in _texts(q)
    assert _texts(q)[:2] == [BOX, "Fuel to 67 litres."]


def test_never_an_instruction_for_a_colour_line(monkeypatch):
    monkeypatch.setattr(voice_module, "MAX_QUEUED", 3)
    q = _LineQueue()
    for text in ("Box this lap.", "Box next lap.", "Box in 2 laps."):
        q.offer(q.line(text, BOX_NOW))
    dropped = q.offer(q.line(DATA_LINE, DATA))
    assert [line.text for line, _ in dropped] == [DATA_LINE]
    assert _texts(q) == ["Box this lap.", "Box next lap.", "Box in 2 laps."]


def test_inside_one_class_the_oldest_goes(monkeypatch):
    monkeypatch.setattr(voice_module, "MAX_QUEUED", 2)
    q = _LineQueue()
    q.offer(q.line("Lap 5. 16 laps to go.", STATUS))
    q.offer(q.line("Worst tyre 19 percent.", BEST_LAP))
    dropped = q.offer(q.line("That's the best lap of the race.", BEST_LAP))
    assert [line.text for line, _ in dropped] == ["Lap 5. 16 laps to go."]


def test_a_newer_place_replaces_a_queued_one():
    q = _LineQueue()
    q.offer(q.line("P9 of 13. You've made a place.", POSITION))
    q.offer(q.line("You're back on it. About 4 seconds off the road.",
                   POSITION))
    dropped = q.offer(q.line(PLACE, POSITION))
    assert [line.text for line, _ in dropped] == [
        "P9 of 13. You've made a place."]
    assert _texts(q) == ["You're back on it. About 4 seconds off the road.",
                         PLACE], "the word back from an off is not a place"


def test_a_newer_heartbeat_replaces_a_queued_one():
    q = _LineQueue()
    q.offer(q.line("Lap 5. 16 laps to go. P10.", STATUS))
    q.offer(q.line(HEARTBEAT, STATUS))
    assert _texts(q) == [HEARTBEAT]


def test_a_stale_data_line_is_dropped_but_an_instruction_of_the_same_age_is_said():
    engine = Held()
    speaker = Voice(engine)
    speaker.say("Radio check.")
    assert engine.started.wait(2.0)
    two_seconds_ago = voice_module._now() - 2.0
    speaker._queue.offer(speaker._queue.line(DATA_LINE, DATA, two_seconds_ago))
    speaker._queue.offer(speaker._queue.line(BOX, BOX_NOW, two_seconds_ago))
    engine.release.set()
    assert _until(lambda: len(engine.lines) == 2)
    time.sleep(0.1)
    speaker.stop()
    assert engine.lines == ["Radio check.", BOX]


# ----------------------------------------------------------------- the gate

def test_news_waits_for_the_gate_and_an_instruction_does_not():
    engine = voice_module.NullEngine()
    speaker = Voice(engine)
    open_ = threading.Event()
    asked: list = []

    def gate(clip_s, strict):
        asked.append((clip_s, strict))
        return open_.is_set()

    speaker.listen_on(gate)
    speaker.say(PLACE, kind=POSITION)
    speaker.say(BOX, kind=BOX_NOW)
    assert _until(lambda: engine.lines == [BOX])
    time.sleep(0.2)
    assert engine.lines == [BOX], "the place was said with the gate shut"
    assert speaker.busy, "a line waiting for a straight is still queued"
    open_.set()
    assert _until(lambda: engine.lines == [BOX, PLACE])
    speaker.stop()
    clip_s, strict = asked[0]
    assert clip_s > 0 and strict is False


def test_the_data_line_asks_the_gate_strictly():
    engine = voice_module.NullEngine()
    speaker = Voice(engine)
    asked: list = []
    speaker.listen_on(lambda clip_s, strict: asked.append(strict) or True)
    speaker.say(DATA_LINE, kind=DATA)
    assert _until(lambda: engine.lines == [DATA_LINE])
    speaker.stop()
    assert asked == [True]


def test_a_gate_that_raises_does_not_silence_the_engineer():
    engine = voice_module.NullEngine()
    speaker = Voice(engine)

    def broken(_clip_s, _strict):
        raise RuntimeError("detector gone")

    speaker.listen_on(broken)
    speaker.say(PLACE, kind=POSITION)
    assert _until(lambda: engine.lines == [PLACE])
    speaker.stop()


def test_a_line_waiting_for_a_straight_goes_stale(monkeypatch):
    monkeypatch.setattr(voice_module, "POSITION_STALE_AFTER_S", 0.2)
    engine = voice_module.NullEngine()
    speaker = Voice(engine)
    speaker.listen_on(lambda _clip_s, _strict: False)
    speaker.say(PLACE, kind=POSITION)
    assert _until(lambda: not speaker.busy, timeout=2.0)
    speaker.stop()
    assert engine.lines == []


def test_a_pack_line_is_timed_off_its_clips(tmp_path):
    clips = {"six": {"file": "a.wav", "samples": 22_050},
             "laps to the stop.": {"file": "b.wav", "samples": 33_075}}
    pack = voice_module.VoicePackEngine(tmp_path, clips, voice_module.NullEngine())
    assert pack.duration_s(DATA_LINE) == pytest.approx(2.5)
    assert pack.duration_s("Not in the pack at all.") is None
    speaker = Voice(pack, enabled=False)
    assert speaker.duration_s(DATA_LINE) == pytest.approx(2.5)
    assert speaker.duration_s("Not in the pack at all.") == pytest.approx(
        len("Not in the pack at all.") * voice_module.LIVE_SECONDS_PER_CHAR)
