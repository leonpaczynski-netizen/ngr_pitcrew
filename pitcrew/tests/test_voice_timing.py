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
    GAPS,
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
    """The data line gives way; a box call is not said ten seconds after it
    was true; a rival in his box is still there fifteen seconds on.

    **And nothing volunteered keeps for 20 s** (15 Sep 2026). No line waits
    for a straight now, so age is time queued behind other speech - and a gap
    figure or a place twenty seconds late is wrong however it got there. The
    longest single line on the radio is the full box call, ~12 s, so a gap or
    a place survives one of those and no more."""
    assert stale_after_s(DATA) == voice_module.DATA_STALE_AFTER_S == 1.5
    assert stale_after_s(BOX_NOW) == voice_module.STALE_AFTER_S == 8.0
    assert stale_after_s(None) == voice_module.STALE_AFTER_S
    assert stale_after_s(STATUS) == voice_module.STALE_AFTER_S
    assert stale_after_s(RIVAL_BOXED) == voice_module.NEWS_STALE_AFTER_S
    assert stale_after_s(POSITION) == voice_module.POSITION_STALE_AFTER_S
    assert stale_after_s(GAPS) == voice_module.GAP_STALE_AFTER_S
    assert (stale_after_s(DATA) < stale_after_s(BOX_NOW)
            < stale_after_s(RIVAL_BOXED))
    for kind in (POSITION, GAPS, RIVAL_BOXED):
        assert 12.0 <= stale_after_s(kind) < 20.0, kind


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
    """**Three DIFFERENT instructions, because three box calls are one.**

    This filled the queue with "Box this lap.", "Box next lap." and "Box in 2
    laps." - a state the queue no longer allows, since a newer stop call
    replaces the one still queued (they answer one question). The claim under
    test is about CLASS, not about the box: a colour line never costs an
    instruction its place, whatever the instructions happen to be.
    """
    from pitcrew.race.calls import FUEL_SAVE, REJOIN

    monkeypatch.setattr(voice_module, "MAX_QUEUED", 3)
    q = _LineQueue()
    filler = [("Box this lap.", BOX_NOW),
              ("Save 0.7 litres a lap to make the flag.", FUEL_SAVE),
              ("You come out behind him.", REJOIN)]
    for text, kind in filler:
        q.offer(q.line(text, kind))
    dropped = q.offer(q.line(DATA_LINE, DATA))
    assert [line.text for line, _ in dropped] == [DATA_LINE]
    assert _texts(q) == [text for text, _ in filler]


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


# ------------------------------------------------- no gate (15 Sep 2026)
#
# The driver: "George can speak at anytime." Replayed over Bathurst, the
# straight gate left 28 of 52 mid-lap lines stale waiting for a straight.

GAP_LINE = "PUNISHED ahead, 2.1."


def test_the_voice_has_no_straight_gate_to_install():
    assert not hasattr(Voice, "listen_on")
    assert not hasattr(voice_module, "GATE_POLL_S")


def test_news_with_no_straight_plays_as_soon_as_the_radio_is_free():
    """Nothing anywhere says the car is on a straight, and nothing is asked:
    a place, a gap and the data line each start the moment the radio is."""
    engine = voice_module.NullEngine()
    speaker = Voice(engine)
    speaker.say(PLACE, kind=POSITION)
    assert _until(lambda: engine.lines == [PLACE], timeout=1.0)
    speaker.say(GAP_LINE, kind=GAPS)
    assert _until(lambda: engine.lines == [PLACE, GAP_LINE], timeout=1.0)
    speaker.say(DATA_LINE, kind=DATA)
    assert _until(lambda: engine.lines == [PLACE, GAP_LINE, DATA_LINE],
                  timeout=1.0)
    assert _until(lambda: not speaker.busy)
    speaker.stop()


def test_news_behind_a_playing_line_starts_when_it_ends():
    engine = Held()
    speaker = Voice(engine)
    heard: list = []
    speaker.say(HEARTBEAT, kind=STATUS)
    assert engine.started.wait(2.0)
    speaker.say(GAP_LINE, kind=GAPS, on_done=heard.append)
    time.sleep(0.1)
    assert engine.lines == [HEARTBEAT], "news cut into a playing line"
    engine.release.set()
    assert _until(lambda: heard == [True])
    assert engine.lines == [HEARTBEAT, GAP_LINE]
    speaker.stop()


def test_a_queued_gap_older_than_its_limit_is_dropped_and_returned(
        monkeypatch):
    """A gap figure queued behind speech for longer than a gap keeps is
    dropped, and its owner is told it was not heard so the race builds the
    next line from the gap as it is then."""
    monkeypatch.setattr(voice_module, "GAP_STALE_AFTER_S", 0.2)
    engine = Held()
    speaker = Voice(engine)
    speaker.say(BOX, kind=BOX_NOW)
    assert engine.started.wait(2.0)
    heard: list = []
    speaker.say(GAP_LINE, kind=GAPS, on_done=heard.append)
    time.sleep(0.4)                          # behind the box call, too long
    engine.release.set()
    assert _until(lambda: heard == [False])
    assert _until(lambda: not speaker.busy)
    speaker.stop()
    assert engine.lines == [BOX]


def test_a_line_offered_to_a_free_radio_is_never_stale():
    """Nothing that was never tried is dropped: taken at the moment it was
    queued, a line of any kind is said, whatever its limit."""
    q = _LineQueue()
    q.offer(q.line(DATA_LINE, DATA, queued_at=100.0))
    line, stale = q.take(100.0)
    assert line is not None and line.text == DATA_LINE and stale == []


def test_take_is_best_class_first_and_drops_the_stale_on_the_way():
    q = _LineQueue()
    q.offer(q.line(GAP_LINE, GAPS, queued_at=0.0))
    q.offer(q.line(PLACE, POSITION, queued_at=5.0))
    q.offer(q.line(BOX, BOX_NOW, queued_at=10.0))
    line, stale = q.take(13.0)
    assert line.text == BOX and stale == []
    line, stale = q.take(13.0)
    # The gap was queued first but 13 s is past its 12; the place is 8 s old.
    assert [(old.text, round(age)) for old, age in stale] == [(GAP_LINE, 13)]
    assert line.text == PLACE
    assert q.take(13.0) == (None, [])


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


def test_a_brief_is_never_truncated_by_the_queue_that_holds_it():
    """**Measured 18 Sep 2026: 5 of 8 brief lines spoken, the first 3 lost.**

    Every line of the brief is the same class, and the eviction rule is
    lowest class then OLDEST - so each line after the fifth threw away the
    front of the brief. What went missing was the shape of his race ("20
    laps, 2 stops, RS onto RH.") and the gauge caveat, while the line that
    DISCLAIMS the caveat - "If I'm quiet about tyres it means I can't see
    them, not that they're fine" - survived. He would have gone to the green
    having heard a disclaimer for a claim nobody made.

    A brief is not a backlog. `MAX_QUEUED` exists so stale race calls cannot
    pile up behind the driver; these are one thing said in parts.
    """
    from pitcrew.engineer.voice import MAX_QUEUED, _LineQueue

    lines = [f"brief line {n}." for n in range(1, 9)]
    assert len(lines) > MAX_QUEUED, "the test must overfill the queue"

    loose = _LineQueue()
    for text in lines:
        loose.offer(loose.line(text, None))
    assert [o.text for o in loose.snapshot()] == lines[-MAX_QUEUED:], (
        "the plain path still drops - that is what `keep` is for")

    held = _LineQueue()
    for text in lines:
        held.offer(held.line(text, None, keep=True))
    assert [o.text for o in held.snapshot()] == lines


def test_a_kept_line_does_not_stop_a_race_call_from_getting_in():
    """`keep` must not turn the brief into a wall an instruction cannot pass.

    It only removes the line from the VICTIM pool; ranking is untouched, so a
    box call still sorts ahead of every brief line waiting behind it.
    """
    from pitcrew.race.calls import BOX_NOW
    from pitcrew.engineer.voice import _LineQueue, class_of

    queue = _LineQueue()
    for n in range(8):
        queue.offer(queue.line(f"brief {n}.", None, keep=True))
    queue.offer(queue.line("Box this lap.", BOX_NOW))
    order = [o.text for o in queue.snapshot()]
    assert order[0] == "Box this lap.", order[:3]
    assert len([o for o in queue.snapshot() if o.keep]) == 8
    assert class_of(BOX_NOW) < class_of(None)


def test_a_newer_stop_call_replaces_the_one_still_queued():
    """**The class with the strictest cost for being late had no replacement
    policy**, while the cheapest - a gap, a place - had one.

    A `BOX_SOON` still queued when `BOX_NOW` arrives is "Box in 2 laps." read
    out immediately before "Box this lap.", and a box call is 10-12 s of
    speech, so the pair is twenty seconds of stop talk whose first half
    stopped being true before it finished saying so.
    """
    from pitcrew.engineer.voice import _LineQueue
    from pitcrew.race.calls import BOX_NOW, BOX_SOON, STOP_BACK, STOPS_OFF

    queue = _LineQueue()
    queue.offer(queue.line("Box in 2 laps. Stop 1, on the plan.", BOX_SOON))
    dropped = queue.offer(queue.line("Box this lap. RH on.", BOX_NOW))
    assert [line.text for line, _ in dropped] == [
        "Box in 2 laps. Stop 1, on the plan."]
    assert [o.text for o in queue.snapshot()] == ["Box this lap. RH on."]

    # The two that REVERSE a stop are the same question, so the newest wins.
    for kind in (STOPS_OFF, STOP_BACK):
        queue = _LineQueue()
        queue.offer(queue.line("Box this lap.", BOX_NOW))
        dropped = queue.offer(queue.line("The stop has moved.", kind))
        assert [line.text for line, _ in dropped] == ["Box this lap."], kind


def test_a_dropped_stop_call_tells_its_owner_it_was_never_said():
    """`on_done(False)` is how a caller learns that queued was not heard - the
    Bathurst defect (eight of ten stops never said) moved one layer down."""
    from pitcrew.engineer.voice import _LineQueue
    from pitcrew.race.calls import BOX_NOW, BOX_SOON

    told = []
    queue = _LineQueue()
    queue.offer(queue.line("Box in 2 laps.", BOX_SOON,
                           on_done=lambda played: told.append(played)))
    dropped = queue.offer(queue.line("Box this lap.", BOX_NOW))
    assert dropped, "the older call must be dropped"
    for line, why in dropped:
        if line.on_done is not None:
            line.on_done(False)
    assert told == [False]


def test_an_unrelated_instruction_is_not_swallowed_by_a_stop_call():
    """Coalescing is per question. A fuel call and a box call are two."""
    from pitcrew.engineer.voice import _LineQueue
    from pitcrew.race.calls import BOX_NOW, FUEL_SHORT

    queue = _LineQueue()
    queue.offer(queue.line("Save 0.7 litres a lap.", FUEL_SHORT))
    dropped = queue.offer(queue.line("Box this lap.", BOX_NOW))
    assert dropped == []
    assert len(queue.snapshot()) == 2
