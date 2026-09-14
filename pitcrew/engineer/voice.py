"""Saying it out loud.

The driver is in a headset and cannot see any screen, so audio is not a nicety
here — it is the only channel. That has consequences the old implementation
learned the hard way and this one inherits:

* **Speech runs on its own thread.** Synthesising on the Qt thread freezes the
  UI mid-race; synthesising on the telemetry thread drops packets.
* **A newer call outranks an older one.** If two calls queue up, the driver
  wants the one that is still true. The queue is short and drops stale items
  rather than reading a backlog at him three corners too late.
* **An instruction outranks everything else.** Lines carry a class - see
  `INSTRUCTION` and the table above it - and the class decides what plays
  first, what is dropped when the queue is full, how soon a line goes stale,
  and whether it waits for a straight.
* **Failure is silent, never fatal.** No voice is a degraded race; a crash is a
  lost one. Every engine failure falls through to the next, and if none work
  the call still reaches the screen and the call log.
* **Silence is counted, not just logged.** The driver cannot see the log and
  cannot see the screen either, so "the engineer has said nothing for three
  calls" has to be a number something can display. `silent_calls` is it.
  An engine that produced no sound raises rather than returning quietly -
  see `VoicePackEngine.speak` for why that was not always true.
"""
from __future__ import annotations

import hashlib
import itertools
import re
import threading
import wave
from functools import lru_cache
from pathlib import Path

from pitcrew.diagnostics import log
from pitcrew.engineer import audio_devices
from pitcrew.engineer.audio_devices import open_output

# One lock across every engine that opens an audio stream **on this card**,
# not one per class. Overlapping PortAudio streams on one device crash the
# host rather than mixing, and the voice pack and live synthesis are two
# engines that can both be asked to play - a per-class lock would let them
# overlap, which is the crash this prevents.
#
# It lives in `audio_devices` because the shift beep opens a stream too and is
# not part of the voice: a lock private to this module left the one pair of
# sounds most likely to coincide - a call on the voice thread and a beep on
# the telemetry thread - free to overlap.
#
# Resolved per call rather than held as a module constant, because the card
# can change under us when the driver picks a different one, and because the
# lock is now per-device: a transducer on its own card must not be blocked by
# the engineer talking into a headset.
def _play_lock():
    return audio_devices.lock_for(audio_devices.output_device())


# **How often the voice offers the card to the shift beep.**
#
# The beep waits `shift_beep.PRIORITY_WAIT_S` (0.4 s) and then drops itself
# rather than sound at an rpm the engine has left. That deadline was never met
# while a line was playing: both writers below handed PortAudio a whole clip in
# one blocking `write`, so the yield below - documented as happening "between
# written chunks" - could only happen between whole sentences. Measured on the
# rendered pack, every clip is longer than the deadline and the median is
# 1.88 s, so the beep lost the race roughly four times in five and the log
# filled with "the card was still busy 0.4s after the beep asked for it".
#
# 100 ms gives the beep four chances inside its deadline while keeping each
# write long enough that the callback is never short of work.
_YIELD_CHUNK_S = 0.1


# **How much louder the engineer is than the model makes him.**
#
# The driver, 27 Aug 2026: George needs to be a bit louder. There is no
# headroom to raise him with. Piper normalises every chunk it yields to full
# scale, and a rendered call measures a peak of exactly 1.000 against a voiced
# RMS of -14.1 dBFS - so a plain multiplier does not make him louder, it
# clips. The 14 dB of crest factor is the only thing left to lift.
#
# `tanh` lifts it and is memoryless, so it cannot produce a seam at a chunk
# boundary the way a compressor with an envelope would. Below about a third of
# full scale it is a straight multiplier; above that it bends, and a sample at
# 1.0 lands at 0.94 instead of clipping. Measured on a rendered call, 1.7 puts
# +3.1 dB on the voiced samples and takes the peak DOWN from 1.000 to 0.936 -
# so the beep keeps its stated ~3.5 dB over a ducked line unchanged.
#
# Applied in `_write_yielding` rather than in `synthesise` because that is the
# one place every spoken line passes through. The pack was rendered before
# this existed; a gain that only reached live synthesis would make a pack hit
# and a pack miss two audibly different voices.
LINE_GAIN = 1.7


def _louder(chunk):
    """`chunk` at `LINE_GAIN`, soft-limited so no sample can clip."""
    import numpy as np

    if LINE_GAIN == 1.0:
        return chunk
    return (np.tanh(np.asarray(chunk, dtype=np.float32)
                    * (LINE_GAIN / 32767.0)) * 32767.0).astype(np.int16)


class _Mixer:
    """Sums short sounds into a line that is already playing.

    One per spoken line. Holds the tail of an overlay that did not fit in the
    chunk it arrived on - a 60 ms beep landing 80 ms into a 100 ms chunk plays
    20 ms here and 40 ms on the next one, rather than being cut at the chunk
    boundary or delayed to it.

    See `audio_devices.offer_mix` for why the beep hands over a recipe rather
    than a waveform, and why mixing replaced pre-emption at all.
    """

    __slots__ = ("device", "_carry")

    def __init__(self, device) -> None:
        self.device = device
        self._carry = None

    @property
    def active(self) -> bool:
        return self._carry is not None

    def blend(self, chunk, rate: int):
        """`chunk` with anything pending summed into it, ducked underneath.

        Returns `chunk` itself, untouched and unconverted, when there is
        nothing to mix. That is the overwhelmingly common case - it is on the
        voice's inner loop, and a line with no beep in it must not pay for the
        arithmetic of one.
        """
        import numpy as np

        for render in audio_devices.take_mix(self.device):
            try:
                arriving = np.asarray(render(rate), dtype=np.float32)
            except Exception as exc:            # noqa: BLE001 - see below
                # A sound that cannot be built is not worth taking the line
                # down for. The beep is the thing being dropped here, and it
                # is dropped the same way an overlapping beep already is.
                log("voice").warning("could not mix a sound into the line: "
                                     "%s: %s", type(exc).__name__, exc)
                continue
            self._carry = (arriving if self._carry is None
                           else _summed(self._carry, arriving))
        if self._carry is None:
            return chunk
        head, self._carry = self._carry[:len(chunk)], self._carry[len(chunk):]
        if not len(self._carry):
            self._carry = None
        mixed = np.asarray(chunk, dtype=np.float32) * audio_devices.MIX_DUCK
        mixed[:len(head)] += head * audio_devices.MIX_GAIN
        return np.clip(mixed, -32768, 32767).astype(np.int16)


def _summed(a, b):
    """`a` and `b` overlaid from sample zero, long enough to hold both."""
    import numpy as np

    if len(b) > len(a):
        a, b = b, a
    out = a.copy()
    out[:len(b)] += b
    return out


def _write_yielding(stream, samples, rate: int, line, mixer=None) -> bool:
    """Play `samples` at `LINE_GAIN`, mixing in anything urgent on the way.

    Returns True when it stopped early to let a beep through - which now only
    happens when there was no mixer to take it, because a beep that can be
    mixed is never a reason to stop.

    **The chunking is the whole point.** `_yield_to_priority` has always said
    it is checked between written chunks; a clip written in one `write` is one
    chunk, which made the promise vacuous. Nothing about the ownership rule
    changes - the writing thread is still the only one that touches the stream,
    and the beep still never reaches into it.
    """
    step = max(1, int(rate * _YIELD_CHUNK_S))
    for start in range(0, len(samples), step):
        chunk = _louder(samples[start:start + step])
        stream.write(chunk if mixer is None else mixer.blend(chunk, rate))
        # A mixer that is still draining an overlay has a beep sounding right
        # now. Standing aside for a second one mid-tone would cut the first.
        if mixer is not None and mixer.active:
            continue
        if _yield_to_priority(line):
            return True
    return False


def _yield_to_priority(line) -> bool:
    """True when the line should stop here and let the shift beep through.

    Checked between written chunks, never inside one: the only thread allowed
    to close this stream is the one writing to it, and a beep reaching in
    mid-`write` would be the close-from-send deadlock in a new costume - see
    `audio_devices.priority_on`.

    Marking the line `interrupted` is what makes this a deferral rather than a
    loss. The caller raises `LineCut`, the worker re-queues the text with its
    original timestamp, and `STALE_AFTER_S` decides whether it is still true.
    A call worth making survives a beep; one that is no longer worth making
    was going to be dropped anyway.
    """
    if line is None or not audio_devices.priority_wanted(
            audio_devices.output_device()):
        return False
    line.interrupted = True
    line.cut_by = STOOD_ASIDE
    return True


# What a line cut by each of the two things that can cut it says in the log.
# Two causes, two sentences: the Suzuka log of 13 Sep 2026 blamed a device
# rebuild for a cut that was a priority claim, and nothing distinguished them.
REBUILT = "the audio devices were rebuilt mid-line"
STOOD_ASIDE = ("the line stood aside for a more urgent sound on the card "
               "(the shift beep's pre-emption)")


def cut_reason(line) -> str:
    """Why `line` was cut, for `LineCut` and the log line it produces."""
    return getattr(line, "cut_by", None) or REBUILT

PACK_ROOT = Path(__file__).resolve().parent / "voice_pack"
PACK_MANIFEST = "manifest.json"
# What `tools/render_voice_pack.py` writes, for a manifest that does not say.
PACK_SAMPLE_RATE = 22_050


def clip_filename(text: str) -> str:
    """A stable filename for a line. The same string always names the same
    file, on any machine, in any order - so a pack is diffable and a re-render
    overwrites rather than accumulates."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{digest}.wav"

# What a spoken line calls itself while it holds a stream open, for the log
# line a deferred device rebuild writes. See `audio_devices.begin_playback`.
SPOKEN_LINE = "the engineer's line"

# ------------------------------------------------------- what plays first
#
# **The queue was one FIFO, and at Bathurst on 14 Sep 2026 that was the whole
# timing defect.** Synthesis was not the problem; the order was. The status
# line at the crossing runs 5.4-5.7 s, the full box call about 10 s, and the
# straight's data line arrived a second into the status line and waited
# behind it - reaching the driver 4.8 to 7.0 s after it was composed, in the
# braking zone for Hell Corner. A full queue dropped its OLDEST line whatever
# it was, so a box call could be dropped to make room for a wear figure.
#
# So a line carries a class, and the class decides three things:
#
#   INSTRUCTION  box, stop off/back, fuel short/save/reaches, the undercut and
#                rejoin, and the pit-box fill. Plays first. Never dropped for
#                a lower class, never waits for a straight: its lateness costs
#                more than the distraction does, and the fill and the release
#                are said with the car stationary.
#   EVENT        tied to a moment, and above all to the CROSSING: the
#                heartbeat, green, chequer, incident, the run-in, the
#                crossing's colour findings and its advice (wear, temperature,
#                fuel long). The coordinator arbitrates one of these per
#                crossing, and saying it at the line is the design - "Lap 6"
#                twenty seconds later is not the same call. **Every line said
#                without a kind is here too**, which is the safe default:
#                exactly the old behaviour, eight seconds and no gate. So is a
#                push-to-talk answer: he just asked.
#   NEWS         volunteered MID-LAP, at a moment that has nothing to do with
#                where the car is: a place gained, a rival in his box or out
#                of it, closing on a car. Waits for somewhere he can listen
#                (see `listen_on`) and goes stale slowly, because the fact
#                stays true while it waits; a position line is REPLACED by a
#                newer one rather than both being read out. This is the
#                class the driver asked for more of (14 Sep 2026: gaps and
#                names, rival stops, championship rivals, pace - "talk
#                whenever it matters", no cap), so it is the class that must
#                never land in a braking zone.
#   COLOUR       the straight's data line. A number read out on a straight
#                and nowhere else: gated strictly on length, and stale after
#                a second and a half, because a data line five seconds late is
#                worse than none.
#
# **No class may cut a line that is already playing.** An instruction behind
# a colour line waits for it: a data line is held to `straight.UNMODELLED_CLIP_S`
# (2.8 s) to start at all, so that is the most an instruction can wait behind
# one, and the alternative is half a sentence the driver has to parse under
# braking before the instruction starts - which is exactly what `LineCut`'s
# re-queue exists to avoid for the beep. A position line (3.5-4 s from the
# pack) is the longest NEWS line likely to be playing mid-lap; the heartbeat
# is longer but is emitted at the crossing by the same arbitration that picks
# the box call, so the two never contend.
INSTRUCTION = 0
EVENT = 1
NEWS = 2
COLOUR = 3
CLASS_NAMES = {INSTRUCTION: "instruction", EVENT: "event", NEWS: "news",
               COLOUR: "colour"}

# A call older than this has been overtaken by the race. Instructions and
# events, and every line said without a kind.
STALE_AFTER_S = 8.0
# **News waits for a straight, so it may wait longer.** At Bathurst a
# straight held long enough to speak on comes two or three times a lap and
# there is a minute of the Mountain with none; news that goes stale in eight
# seconds is news never said there. A rival standing in his box is still
# standing there twenty seconds on.
NEWS_STALE_AFTER_S = 20.0
# A position line is coalesced (the newest replaces any queued one), so the
# one that is said is the current place however long it waited.
POSITION_STALE_AFTER_S = 30.0
# The straight's number. Late by more than this it lands somewhere he is
# not listening, and the straight it was composed for has gone.
DATA_STALE_AFTER_S = 1.5
# How deep the queue may get. **Staleness bounds lateness per class now, so
# depth does not have to**: it was 3 when depth was the only guard, and with
# more volunteered radio queued for straights three would drop news that was
# still true. The drop takes the lowest class first, oldest first.
MAX_QUEUED = 5
# How often a line waiting for a straight asks again.
GATE_POLL_S = 0.05
# Seconds of speech per character, for a line the pack cannot time. Measured
# on the rendered en_GB-alan-medium pack, 14 Sep 2026: median 0.123 s over
# every clip of 15 characters or more.
LIVE_SECONDS_PER_CHAR = 0.123


@lru_cache(maxsize=1)
def _kind_classes() -> dict[str, int]:
    """Call kind -> class. Imported lazily: the race layer is not needed to
    build a Voice, and a test that holds one should not pay for it."""
    from pitcrew.race import calls, colour, refuel

    instructions = (calls.BOX_NOW, calls.BOX_SOON, calls.STOPS_OFF,
                    calls.STOP_BACK, calls.UNDERCUT, calls.FUEL_SHORT,
                    calls.FUEL_SAVE, calls.FUEL_REACHES, calls.REJOIN,
                    calls.STAY_OUT_FUEL,
                    refuel.TARGET, refuel.RELEASE, refuel.SHORT)
    # Said mid-lap, off a frame or the pit wall's worker - never at the
    # crossing. Everything else not listed is EVENT.
    news = (calls.POSITION, calls.RIVAL_BOXED, calls.RIVAL_COMMITTED,
            calls.RIVAL_SHORT, calls.CLOSING)
    table = {kind: NEWS for kind in news}
    table.update({kind: INSTRUCTION for kind in instructions})
    table[colour.DATA] = COLOUR
    return table


def class_of(kind: str | None) -> int:
    """The class a call kind plays in. An unknown or missing kind is EVENT -
    the old behaviour, so a caller not yet passing a kind loses nothing."""
    if kind is None:
        return EVENT
    return _kind_classes().get(kind, EVENT)


def stale_after_s(kind: str | None) -> float:
    """How long a line of this kind stays worth saying.

    Read from the module constants at call time, so a test that shortens one
    shortens the rule rather than a copy of it.
    """
    from pitcrew.race.calls import POSITION

    cls = class_of(kind)
    if cls == COLOUR:
        return DATA_STALE_AFTER_S
    if kind == POSITION:
        return POSITION_STALE_AFTER_S
    if cls == NEWS:
        return NEWS_STALE_AFTER_S
    return STALE_AFTER_S


def _coalesce_key(kind: str | None, text: str) -> str | None:
    """Lines that a newer line of the same key replaces, or None.

    **The position kind carries two different facts**: the place ("P8 of
    13. You've made a place.") and the word back from an off ("You're back
    on it."), and only the first is superseded by a newer one. So the place
    is recognised by its shape, which `phrase_manifest` already relies on.
    """
    from pitcrew.race.calls import POSITION, STATUS
    from pitcrew.race.colour import DATA

    if kind == POSITION and re.match(r"P\d+\b", text):
        return "position"
    if kind in (STATUS, DATA):
        return kind
    return None


# **"Car #76" is a handle, and Piper reads "#" as "hash".** The store mints
# `Car #N` for a car nobody has named yet (`Store.provisional_driver_name`),
# and it reaches the ear through every call that names a driver - a rival's
# stop, the chase, the rejoin, the tow. Said "Car hash 76" at Bathurst. Turned
# into words here, at the one boundary every spoken line crosses, so no call
# has to remember; the screen and the record keep the handle as it is filed.
_HANDLE_IN_TEXT = re.compile(r"\bCar #(\d+)\b")


def spoken_form(text: str) -> str:
    """`text` as the engine should say it: "Car #76" as "Car 76"."""
    return _HANDLE_IN_TEXT.sub(r"Car \1", text) if text else text


class _Line:
    """One thing to say, and what the queue needs to know about it."""

    __slots__ = ("text", "kind", "cls", "queued_at", "seq", "clip_s",
                 "on_done")

    def __init__(self, text: str, kind: str | None, queued_at: float,
                 seq: int, on_done=None) -> None:
        self.text = text
        self.kind = kind
        self.cls = class_of(kind)
        self.queued_at = queued_at
        self.seq = seq
        self.clip_s: float | None = None
        # `on_done(played)`, once, when the line is finished with - see
        # `Voice.say`.
        self.on_done = on_done

    def __repr__(self) -> str:                      # pragma: no cover
        return f"<{CLASS_NAMES[self.cls]} {self.kind} {self.text!r}>"


class _LineQueue:
    """Lines waiting to be said, taken best class first.

    Holds its lock only for list operations: deciding whether a line may
    start asks the gate and times the clip, and neither may block `say` on
    the Qt thread.

    `put` and `qsize` keep the shape of the `queue.Queue` this replaced, so a
    caller that enqueues `(queued_at, text)` directly still works.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._lines: list[_Line] = []
        self._seq = itertools.count()
        self.closed = False

    def qsize(self) -> int:
        with self._cond:
            return len(self._lines)

    def line(self, text: str, kind: str | None = None,
             queued_at: float | None = None, on_done=None) -> _Line:
        return _Line(text, kind, _now() if queued_at is None else queued_at,
                     next(self._seq), on_done)

    def put(self, item) -> None:
        if item is None:
            self.close()
            return
        if isinstance(item, _Line):
            self.offer(item)
            return
        queued_at, text = item
        self.offer(self.line(text, None, queued_at))

    def offer(self, line: _Line) -> list[tuple[_Line, str]]:
        """Queue `line`; return what was dropped to make room, and why."""
        dropped: list[tuple[_Line, str]] = []
        with self._cond:
            key = _coalesce_key(line.kind, line.text)
            if key is not None:
                for old in [o for o in self._lines
                            if _coalesce_key(o.kind, o.text) == key]:
                    self._lines.remove(old)
                    dropped.append((old, f"replaced by a newer {key} line"))
            while len(self._lines) + 1 > MAX_QUEUED:
                # The lowest class first, and inside it the oldest - the
                # newer of two equal calls is the one still true.
                victim = max([*self._lines, line],
                             key=lambda o: (o.cls, -o.seq))
                if victim is line:
                    dropped.append((line, "the queue is full of lines that "
                                          "outrank it"))
                    return dropped
                self._lines.remove(victim)
                dropped.append((victim, f"dropped for a {CLASS_NAMES[line.cls]}"
                                        f" line with the queue full"))
            self._lines.append(line)
            self._cond.notify_all()
        return dropped

    def requeue(self, line: _Line) -> None:
        """Back in, as it was - its place in its class and its timestamp."""
        with self._cond:
            self._lines.append(line)
            self._cond.notify_all()

    def snapshot(self) -> list[_Line]:
        with self._cond:
            return sorted(self._lines, key=lambda o: (o.cls, o.seq))

    def remove(self, line: _Line) -> bool:
        with self._cond:
            if line in self._lines:
                self._lines.remove(line)
                return True
            return False

    def wait(self, poll_s: float) -> None:
        """Until something changes: `poll_s` while lines are waiting (a gate
        may open without anyone calling), indefinitely while there are none.
        Decided under the lock, so a line offered after the caller last
        looked cannot be missed."""
        with self._cond:
            if not self.closed:
                self._cond.wait(poll_s if self._lines else None)

    def close(self) -> None:
        with self._cond:
            self.closed = True
            self._cond.notify_all()

# Passing engine=None means "this machine has no speech"; the default
# means "find the best one available". Conflating the two made a test
# asking for silence get SAPI5 instead.
AUTO = object()


class LineCut(RuntimeError):
    """A device-list rebuild closed the stream while the line was playing.

    Not an engine failure and not counted as one. `audio_devices` holds a
    rebuild off for as long as `DEFER_CAP_S` so that this stays rare, but the
    wait is bounded on purpose - a rebuild that could never proceed would
    starve the transducer recovery - so the line can still be cut, and when it
    is, `Voice._run` decides whether saying it again is better than silence.
    """


class NotSpoken(RuntimeError):
    """Raised when a line reached an engine and produced no sound.

    The one failure mode that used to be invisible: a `VoicePackEngine` with
    no live engine under it returned normally for every line it did not
    carry, so nothing raised, nothing was logged above INFO, and `enabled`
    still said True.
    """


class Voice:
    """Speaks queued lines on a background thread.

    `engine` is injectable so the whole race path can be driven in tests, and
    so a machine with no speech synthesis at all still runs the app.
    """

    def __init__(self, engine=AUTO, *, enabled: bool = True) -> None:
        self._engine = _best_engine() if engine is AUTO else engine
        self.enabled = enabled and can_speak(self._engine)
        # Consecutive calls that reached the engine and made no sound. The
        # driver is in a headset with no screen, so this is the only way the
        # app can tell him it has gone quiet - see `health()`.
        self._failures = 0
        self.last_error: str | None = None
        self.spoken: list[str] = []
        self._queue = _LineQueue()
        # The line on the card right now, for `busy`.
        self._playing: _Line | None = None
        # Whether a NEWS or COLOUR line may start now. See `listen_on`.
        self._gate = None
        self._gate_failed = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if self.enabled:
            self._thread = threading.Thread(
                target=self._run, name="PitCrewVoice", daemon=True)
            self._thread.start()

    def tune(self, **params: float) -> None:
        """Pass synthesis settings to the engine, if it takes any.

        Forwarded rather than held here: `Voice` owns the queue and the
        thread, and knows nothing about how any particular engine makes sound.
        """
        tune = getattr(self._engine, "tune", None)
        if tune is not None:
            tune(**params)

    def warm(self) -> None:
        """Pay any model-loading cost now, off the caller's thread.

        Called when a session starts rather than when the Voice is built:
        constructing a Voice must stay cheap, or every test and every screen
        that merely holds one pays a second and a half for a model it will
        never speak through.
        """
        warm = getattr(self._engine, "warm", None)
        timed = getattr(self._engine, "duration_s", None)
        if warm is None and timed is None:
            return

        def run() -> None:
            try:
                if warm is not None:
                    warm()
                if timed is not None:
                    # The pack's decomposition tables are built on first
                    # use, and the first use is otherwise a line waiting on
                    # the voice thread to be timed against a straight.
                    timed(WARM_LINE)
            except Exception as exc:            # noqa: BLE001
                log("voice").error("warm-up failed: %s: %s",
                                   type(exc).__name__, exc, exc_info=True)

        threading.Thread(target=run, name="PitCrewVoiceWarm",
                         daemon=True).start()

    @property
    def engine_name(self) -> str:
        if self._engine is None:
            return "none"
        return getattr(self._engine, "name", type(self._engine).__name__)

    @property
    def silent_calls(self) -> int:
        """How many calls in a row reached the engine and made no sound."""
        return self._failures

    def health(self) -> str | None:
        """What is wrong with the audio right now, or None if nothing is.

        Phrased as the driver would experience it - a count of calls he did
        not hear - rather than as the exception, which is in the log for
        afterwards. None means the last call played, not that every call did.
        """
        if not self._failures:
            return None
        calls = "call" if self._failures == 1 else "calls"
        return (f"The engineer has said nothing for {self._failures} "
                f"{calls}: {self.last_error}")

    def say(self, text: str, kind: str | None = None,
            on_done=None) -> None:
        """Queue `text`. `kind` is the call kind (`race.calls`, `race.colour`,
        `race.refuel`) and decides its class - see the table above `_Line`.

        No kind is EVENT: the queue's old behaviour, so a caller that has not
        been given a kind is never made worse.

        **`on_done(played)` is how a caller learns whether it was HEARD.**
        Queued is not said: since lines carry a class a NEWS line can wait for
        a straight and go stale, be replaced by a newer place, or be dropped
        for an instruction with the queue full. A caller that retires a fact
        when it hands it over - a rival's stop, a place - loses it every time
        that happens, which is the Bathurst defect (eight of ten stops never
        said) moved one layer down. So the callback is called exactly once:
        `True` when the engine returned from speaking the line, `False` when
        it was dropped, went stale, failed, or the voice is off.

        **It runs on whichever thread finished the line** - the voice thread
        for a line that played or went stale, the caller's own thread for one
        dropped as it was queued. The callback must hand anything touching
        its owner's state back to the owner's thread (the controller emits a
        Qt signal), and it must not block: it is on the voice's inner loop.
        """
        if not text:
            return
        self.spoken.append(text)
        if not self.enabled:
            if on_done is not None:
                _finish(self._queue.line(text, kind, on_done=on_done), False,
                        "the voice is off")
            return
        line = self._queue.line(text, kind, on_done=on_done)
        for dropped, why in self._queue.offer(line):
            log("voice").info("not saying %r (%s, %s): %s", dropped.text,
                              dropped.kind or "no kind",
                              CLASS_NAMES[dropped.cls], why)
            _finish(dropped, False, why)

    @property
    def busy(self) -> bool:
        """Whether anything is playing or waiting to - so a caller with
        something optional to say can wait for a clear radio instead of
        queueing behind it."""
        return self._playing is not None or self._queue.qsize() > 0

    def listen_on(self, gate) -> None:
        """Hold NEWS and COLOUR lines until `gate(clip_s, strict)` says yes.

        `clip_s` is how long the line will take to say; `strict` is True for
        COLOUR. The race passes `straight.fits` over the live straight
        detector, so a volunteered line starts only where the driver can
        listen for as long as it lasts - never in a braking zone - and waits
        (until it goes stale) where he cannot. Instructions and events are
        never held. None removes the gate.
        """
        self._gate = gate
        self._gate_failed = False

    def duration_s(self, text: str) -> float:
        """How long `text` takes to say: timed off the pack where the pack
        carries it, estimated from its length where it does not."""
        timed = getattr(self._engine, "duration_s", None)
        if timed is not None:
            try:
                seconds = timed(spoken_form(text))
            except Exception:                   # noqa: BLE001 - estimate
                seconds = None
            if seconds is not None:
                return seconds
        return len(spoken_form(text)) * LIVE_SECONDS_PER_CHAR

    def _may_start(self, line: _Line) -> bool:
        if line.cls < NEWS or self._gate is None:
            return True
        if line.clip_s is None:
            line.clip_s = self.duration_s(line.text)
        try:
            return bool(self._gate(line.clip_s, line.cls == COLOUR))
        except Exception as exc:                # noqa: BLE001 - fail open
            # A gate that raises must not silence the engineer: the line is
            # said as it would have been before there was a gate.
            if not self._gate_failed:
                self._gate_failed = True
                log("voice").error("the listening gate raised, so volunteered "
                                   "lines are no longer held for a straight: "
                                   "%s: %s", type(exc).__name__, exc,
                                   exc_info=True)
            return True

    def _next_line(self) -> _Line | None:
        """The best line that may start now, dropping stale ones on the way.

        Blocks until there is one. A line held for a straight does not hold
        up a line behind it that is not held: an instruction arriving while
        the heartbeat waits for the Mountain Straight is said at once.
        """
        while not self._queue.closed:
            now = _now()
            for line in self._queue.snapshot():
                age = now - line.queued_at
                if age > stale_after_s(line.kind):
                    if self._queue.remove(line):
                        # The race has moved on; saying it now would mislead.
                        log("voice").info(
                            "not saying %r (%s, %s): %.1fs old, stale after "
                            "%.1fs", line.text, line.kind or "no kind",
                            CLASS_NAMES[line.cls], age,
                            stale_after_s(line.kind))
                        _finish(line, False, "stale")
                    continue
                if self._may_start(line) and self._queue.remove(line):
                    return line
            self._queue.wait(GATE_POLL_S)
        return None

    def say_now(self, text: str) -> tuple[bool, str]:
        """Speak on the calling thread and report what actually happened.

        `say` is a queue put: it returns before the voice thread has picked the
        line up, let alone synthesised or played it, so a caller that reports
        success off the back of it is reporting that a string was enqueued.
        The Settings self-test used to do exactly that, keyed on `enabled` -
        which is only "an engine object exists" - so it printed "Said it
        through ..." with the audio endpoint gone, a pack with no fallback
        under it, or no output device at all. The one control whose whole
        purpose is proving the voice works could not fail.
        """
        if self._engine is None:
            return False, "no speech engine loaded on this machine"
        try:
            self._engine.speak(spoken_form(text))
        except Exception as exc:                      # noqa: BLE001 - reported
            log("voice").error("say_now failed: %s", exc)
            return False, str(exc)
        self.spoken.append(text)
        return True, ""

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)

    def _run(self) -> None:
        while not self._stop.is_set():
            line = self._next_line()
            if line is None:
                # Closed with lines still waiting: none of them will play.
                for left in self._queue.snapshot():
                    if self._queue.remove(left):
                        _finish(left, False, "the voice stopped")
                return
            self._playing = line
            try:
                self._say_one(line)
            finally:
                self._playing = None

    def _say_one(self, line: _Line) -> None:
        """Play one line; a cut line goes back in, a failure is counted."""
        queued_at, text = line.queued_at, line.text
        try:
            self._engine.speak(spoken_form(text))
        except LineCut as cut:
            # Something closed the stream in the middle of the line - a
            # rebuild of the device list, or the line standing aside for
            # a sound that may pre-empt it. Not a failure of the engine,
            # so it does not touch `_failures` - the card is fine and the
            # next line will play - but the driver heard half a sentence,
            # and half a sentence from a race engineer is worse than none.
            #
            # Re-queued with its ORIGINAL timestamp, not a fresh one. The
            # staleness rule above is already the right test for whether a
            # call is still worth making, and restarting the clock here
            # would let a box call arrive ten seconds after it was true.
            #
            # **The reason is the one the cutter recorded.** This used to
            # say "the audio devices were rebuilt" for every cut, and at
            # Suzuka on 13 Sep 2026 the cut was the radio static.
            why = str(cut) or REBUILT
            age = _now() - queued_at
            if age <= stale_after_s(line.kind):
                log("voice").warning(
                    "%s - cut %r off after %.1fs - saying it again.",
                    why, text, age)
                self._queue.requeue(line)
            else:
                log("voice").warning(
                    "%s - cut %r off. It is %.1fs old now, so it is "
                    "dropped rather than said late.", why, text, age)
                _finish(line, False, "cut off and stale")
        except Exception as exc:            # noqa: BLE001 - see below
            # Deliberately broad: a synthesis failure mid-race must not
            # take the app with it, and the driver still has the screen
            # and the call log. Reported, never swallowed silently.
            self._failures += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            log("voice").error("%s (nothing said for %d call(s))",
                               self.last_error, self._failures,
                               exc_info=True)
            _finish(line, False, "the engine made no sound")
        else:
            if self._failures:
                log("voice").info("voice recovered after %d silent call(s)",
                                  self._failures)
            self._failures = 0
            self.last_error = None
            _finish(line, True)


def _finish(line: _Line, played: bool, why: str = "") -> None:
    """Tell whoever asked whether `line` was heard. Once, and never fatally.

    **The accept is logged as well as the drop** (CLAUDE.md rule 10): a fact
    the race retires on this answer was invisible in the log when only the
    refusals were written, and the retirement is the number that decides
    whether it is offered again.
    """
    done, line.on_done = line.on_done, None
    if done is None:
        return
    if played:
        log("voice").info("said %r (%s, %s) - acknowledged as heard",
                          line.text, line.kind or "no kind",
                          CLASS_NAMES[line.cls])
    else:
        log("voice").info("not heard %r (%s, %s) - acknowledged as dropped: "
                          "%s", line.text, line.kind or "no kind",
                          CLASS_NAMES[line.cls], why)
    try:
        done(played)
    except Exception as exc:                    # noqa: BLE001 - see below
        # The callback is the caller's bookkeeping. A fault in it must cost
        # that fact, not the voice thread and every call after it.
        log("voice").error("the acknowledgement for %r raised: %s: %s",
                           line.text, type(exc).__name__, exc, exc_info=True)


def _now() -> float:
    import time
    return time.monotonic()


class NullEngine:
    """Records what would have been said. Used in tests and when muted."""

    name = "null"

    def __init__(self) -> None:
        self.lines: list[str] = []

    def speak(self, text: str) -> None:
        self.lines.append(text)


# How the engineer sounds, before the driver tunes it. Overridden from the
# Settings screen; see pitcrew/settings.py for what each one does and why
# noise_w_scale is the one that matters.
DEFAULT_TUNING: dict[str, float] = {
    "length_scale": 1.12,
    "noise_scale": 0.60,
    "noise_w_scale": 0.55,
}


# What `PiperEngine.warm` synthesises and throws away. Short, and a real
# sentence, so the warm-up runs the same code path a call does.
WARM_LINE = "Radio check."


class PiperEngine:
    """Local neural speech. Offline, and far better than SAPI on a race radio.

    Three details that matter on the voice thread:

    * **The model is loaded once, ahead of time.** Cold-loading takes about
      1.7 seconds, which arriving in the middle of "box this lap" would make
      the call useless. `warm()` pays that cost before the race starts.
    * **Playback is serialised.** Overlapping sounddevice streams crash the
      PortAudio host rather than mixing, so one call finishes before the next
      begins - which is what a real radio does anyway.
    * **Audio starts on the first chunk.** Synthesising the whole line before
      playing any of it puts the entire synthesis time in front of the first
      word. A real radio call starts as the engineer starts talking, and on a
      long line that is most of a second earlier.
    """

    name = "piper"

    def __init__(self, model_path: str | None = None, *,
                 tuning: dict | None = None) -> None:
        import numpy  # noqa: F401 - required by the synth path
        import sounddevice  # noqa: F401

        self._path = model_path or _default_model()
        if not self._path:
            raise FileNotFoundError(
                "no Piper voice model. Download one with: "
                "python -m piper.download_voices en_GB-alan-medium "
                "pitcrew/engineer/piper_models")
        from piper import PiperVoice  # noqa: F401 - probe it imports
        self._voice = None
        self.tuning = dict(DEFAULT_TUNING)
        if tuning:
            self.tuning.update(tuning)

    def tune(self, **params: float) -> None:
        """Change how it sounds, between calls. Unknown names are ignored so a
        newer settings screen cannot break an older engine."""
        for key, value in params.items():
            if key in DEFAULT_TUNING:
                self.tuning[key] = float(value)

    def warm(self) -> None:
        """Load the model AND run it once, so the first real call waits for
        neither.

        **Loading was only half the cost.** The first synthesis after a load
        pays for the ONNX session's own first run - measured at Bathurst on
        14 Sep 2026, the first pack miss of the race took 550 ms against
        137 ms warm, and it landed on a call at racing speed. One throwaway
        line, synthesised into nothing: no stream is opened, no card is
        claimed, and the driver hears nothing.
        """
        self._load()
        for _samples, _rate in self.synthesise(WARM_LINE):
            pass

    def _load(self):
        if self._voice is None:
            from piper import PiperVoice
            self._voice = PiperVoice.load(self._path)
        return self._voice

    def _config(self):
        from piper.config import SynthesisConfig

        return SynthesisConfig(volume=1.0, normalize_audio=True,
                               **self.tuning)

    def synthesise(self, text: str):
        """Yield (samples, sample_rate) as they are produced.

        Separated from playback so the render tool can write a wav without
        touching an audio device, and so a test can drive synthesis on a
        machine with no sound card at all.
        """
        import numpy as np

        for chunk in self._load().synthesize(text, self._config()):
            yield (np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16),
                   chunk.sample_rate)

    def speak(self, text: str) -> None:
        device = audio_devices.output_device()
        # Declared before the lock body rather than around the write loop, so
        # a beep arriving during synthesis is taken and mixed into the first
        # chunk instead of pre-empting a line that has not been heard yet.
        with _play_lock(), audio_devices.mixing_on(device):
            stream = None
            line = None
            mixer = _Mixer(device)
            try:
                for samples, rate in self.synthesise(text):
                    if stream is None:
                        # Opened and declared as one step, under the
                        # enumeration lock. Declaring first would be an AB-BA
                        # deadlock and declaring a moment later would leave a
                        # gap a rebuild can close the stream in - see
                        # `audio_devices.begin_playback` for both halves.
                        stream, line = audio_devices.open_and_declare(
                            SPOKEN_LINE, lambda: open_output(rate))
                    if _write_yielding(stream, samples, rate, line, mixer):
                        break
            finally:
                if stream is not None:
                    # stop() drains what is already queued; close() would cut
                    # the last syllable off.
                    stream.stop()
                    stream.close()
                if line is not None:
                    audio_devices.end_playback(line)
        if line is not None and line.interrupted:
            raise LineCut(cut_reason(line))


class VoicePackEngine:
    """Plays a pre-rendered line, and delegates anything it does not have.

    Synthesis takes long enough to be heard as a pause before the engineer
    speaks. Almost everything he says comes from a closed template, so almost
    everything is rendered ahead of time and this plays the wav instead - a
    file read rather than a neural forward pass.

    It is a wrapper, not a replacement. A line the pack does not carry goes to
    the live engine underneath exactly as before, and so does any playback
    failure: the pack is an optimisation, and an optimisation that can silence
    the engineer is a bug. **Every miss is logged with the exact string**,
    because the miss log is how the manifest gets finished.

    Two consequences of taking that last sentence seriously:

    * **A playback failure is not a miss.** It used to fall through into the
      miss counter and the miss log, so a dead audio device wrote "not in the
      manifest" against lines that were in it, and `hits`/`misses` stopped
      measuring coverage at all. A device fault is logged as one.
    * **With no live engine underneath, an uncovered line raises.** It used to
      return, having played nothing and said nothing about it, which is how a
      pack with `fallback=None` could present itself as a working voice.
      `_best_engine` no longer builds that object, and if something else does,
      `NotSpoken` says so out loud.
    """

    name = "voice-pack"

    def __init__(self, pack_dir: Path, clips: dict, fallback=None, *,
                 sample_rate: int = PACK_SAMPLE_RATE) -> None:
        self._dir = pack_dir
        self._clips = clips
        self._fallback = fallback
        self._rate = sample_rate
        self.hits = 0
        self.misses = 0

    def duration_s(self, text: str) -> float | None:
        """How long the pack takes to say `text`, off the rendered sample
        counts, or None where it does not carry every clip of it."""
        from pitcrew.engineer.phrase_manifest import segments_for

        segments = segments_for(text)
        if not segments:
            return None
        total = 0
        for name in segments:
            samples = (self._clips.get(name) or {}).get("samples")
            if samples is None:
                return None
            total += samples
        return total / float(self._rate)

    @property
    def has_live_engine(self) -> bool:
        """Whether there is anything behind the pack for a line it lacks.

        A pack covers most of what the engineer says, never all of it, so this
        is the difference between a voice and a voice-shaped object.
        """
        return self._fallback is not None

    @property
    def voice_id(self) -> str:
        return self._dir.name

    def tune(self, **params: float) -> None:
        """The pack is already rendered, so tuning only reaches the live
        engine underneath - which is where it still matters, for misses."""
        tune = getattr(self._fallback, "tune", None)
        if tune is not None:
            tune(**params)

    def warm(self) -> None:
        warm = getattr(self._fallback, "warm", None)
        if warm is not None:
            warm()

    def speak(self, text: str) -> None:
        from pitcrew.engineer.phrase_manifest import (
            segments_for,
            uncovered_reason,
        )

        segments = segments_for(text)
        if segments and all(name in self._clips for name in segments):
            try:
                self._play(segments)
                self.hits += 1
                return
            except LineCut:
                # The pack had the line and played it; the app's own device
                # rebuild cut it short. Counted as the hit it was - hits and
                # misses measure what the manifest covers, not what the card
                # did with it - and passed straight up, because re-speaking is
                # `Voice`'s decision and synthesising it here would say the
                # same line twice in two different voices.
                self.hits += 1
                raise
            except Exception as exc:             # noqa: BLE001
                # A pack that cannot play must not cost the driver the call.
                # Logged as the device fault it is and NOT counted as a miss:
                # the miss log is the list of lines still to render, and a
                # dead output device puts covered lines on it.
                log("voice").warning(
                    "voice pack playback failed for %r (%s: %s) - "
                    "synthesising instead", text, type(exc).__name__, exc)
                if self._fallback is None:
                    raise NotSpoken(
                        f"the pack could not play {text!r} and there is no "
                        f"live engine behind it") from exc
                self._fallback.speak(text)
                return

        self.misses += 1
        reason = uncovered_reason(text)
        log("voice").info(
            "voice pack miss: %r%s", text,
            f" - {reason}" if reason else " - not in the manifest")
        if self._fallback is None:
            raise NotSpoken(
                f"{text!r} is not in the pack and there is no live engine "
                f"behind it, so nothing was said")
        self._fallback.speak(text)

    def _play(self, segments) -> None:
        device = audio_devices.output_device()
        with _play_lock(), audio_devices.mixing_on(device):
            stream = None
            line = None
            mixer = _Mixer(device)
            try:
                for name in segments:
                    samples, rate = self._read(self._clips[name]["file"])
                    if stream is None:
                        # One step, under the enumeration lock, for the two
                        # reasons in `audio_devices.begin_playback`.
                        stream, line = audio_devices.open_and_declare(
                            SPOKEN_LINE, lambda: open_output(rate))
                    if _write_yielding(stream, samples, rate, line, mixer):
                        break
            finally:
                if stream is not None:
                    stream.stop()
                    stream.close()
                if line is not None:
                    audio_devices.end_playback(line)
        if line is not None and line.interrupted:
            raise LineCut(cut_reason(line))

    def _read(self, filename: str):
        import numpy as np

        with wave.open(str(self._dir / filename), "rb") as handle:
            rate = handle.getframerate()
            body = handle.readframes(handle.getnframes())
        return np.frombuffer(body, dtype=np.int16), rate


def load_voice_pack(fallback=None, voice_id: str | None = None):
    """The rendered pack for a voice, or None if there is not one.

    Absent is the normal state before `tools/render_voice_pack.py` has run,
    and it must cost nothing: no pack means the live engine, exactly as
    before.
    """
    if not PACK_ROOT.is_dir():
        return None
    if voice_id:
        candidates = [PACK_ROOT / voice_id]
    else:
        candidates = sorted(p for p in PACK_ROOT.iterdir() if p.is_dir())
    for folder in candidates:
        index = folder / PACK_MANIFEST
        if not index.exists():
            continue
        try:
            import json
            with index.open(encoding="utf-8") as handle:
                loaded = json.load(handle)
            clips = loaded.get("clips") or {}
            rate = int(loaded.get("sampleRate") or PACK_SAMPLE_RATE)
        except (OSError, ValueError) as exc:
            log("voice").warning("voice pack %s is unreadable: %s",
                                 folder.name, exc)
            continue
        if clips:
            log("voice").info("voice pack %s loaded, %d clips",
                              folder.name, len(clips))
            return VoicePackEngine(folder, clips, fallback, sample_rate=rate)
    return None


def _default_model() -> str:
    """The first voice model shipped alongside this module."""
    from pathlib import Path

    folder = Path(__file__).resolve().parent / "piper_models"
    models = sorted(folder.glob("*.onnx")) if folder.is_dir() else []
    return str(models[0]) if models else ""


class Sapi5Engine:
    """Windows SAPI5 through win32com.

    COM must be initialised on the thread that uses it, which is why this
    initialises inside `speak` rather than at construction - the object is
    built on the Qt thread and used on the voice thread.

    **SAPI has its own idea of the output device and does not consult ours.**
    Every other sound this app makes goes through `audio_devices`; this engine
    went to whatever Windows called the default, so the one setting on the
    Settings screen that says where the engineer speaks did not apply to the
    fallback engine. On the machine where the chosen headset is not the
    default that is silence, and it is silence that no counter here can see,
    because SAPI reports success either way. `_route_to_chosen_device` closes
    that: it picks the SAPI audio-output token whose description matches the
    card the driver chose.
    """

    name = "sapi5"

    def __init__(self) -> None:
        import win32com.client  # noqa: F401 - probe that it imports
        self._voice = None
        # Which device the token was last selected for, so the lookup runs
        # when the driver changes cards rather than on every line.
        self._routed_to: object = object()

    def speak(self, text: str) -> None:
        import pythoncom
        import win32com.client

        if self._voice is None:
            pythoncom.CoInitialize()
            self._voice = win32com.client.Dispatch("SAPI.SpVoice")
        self._route_to_chosen_device()
        self._voice.Speak(text)

    def _route_to_chosen_device(self) -> None:
        """Point SAPI at the card the driver chose, if it can be found.

        Matched on the first 31 characters because that is where MME truncates
        device names, and the name stored by the Settings screen may have come
        from either spelling. A device SAPI does not offer leaves the default
        in place and says so once - the wrong speaker beats no call at all.
        """
        chosen = audio_devices.output_device()
        if chosen == self._routed_to:
            return
        self._routed_to = chosen
        if not isinstance(chosen, str) or not chosen:
            return
        wanted = audio_devices.endpoint_key(chosen)
        try:
            outputs = self._voice.GetAudioOutputs()
            for index in range(outputs.Count):
                token = outputs.Item(index)
                if audio_devices.endpoint_key(token.GetDescription()) == wanted:
                    self._voice.AudioOutput = token
                    log("voice").info("SAPI speaking into %r", chosen)
                    return
        except Exception as exc:                # noqa: BLE001
            # Routing is an improvement on the default, not a precondition for
            # speaking: a COM failure here must not cost the driver the call.
            log("voice").warning("could not point SAPI at %r: %s: %s",
                                 chosen, type(exc).__name__, exc)
            return
        log("voice").warning(
            "SAPI does not offer %r - speaking into the system default",
            chosen)


def _best_engine():
    """The best speech engine this machine can actually run.

    A rendered phrase pack in front, because playing a wav beats synthesising
    the same sentence every time. Then Piper: a neural voice that sounds like a
    race engineer, where SAPI sounds like a screen reader. SAPI is the fallback
    rather than the default, and no speech at all is still a running app.

    The pack wraps whatever is underneath rather than replacing it, so the
    chain still degrades pack -> Piper -> SAPI -> silent, and a machine with
    no pack behaves exactly as it did before there was one.

    **A pack with nothing underneath is not the bottom of that chain, it is
    off the end of it.** The models and the rendered pack are gitignored
    independently, so "pack on disk, no Piper model" is a state a real machine
    reaches - and the object it used to produce answered `speak()` for every
    line, played about nine in ten of them, and was silent for the rest
    without raising. Returning None instead means the app says "no speech
    engine on this machine", which is true and which the driver can act on.
    """
    live = None
    for factory in (PiperEngine, Sapi5Engine):
        try:
            live = factory()
            break
        except Exception as exc:                # noqa: BLE001
            log("voice").info("%s unavailable: %s: %s", factory.__name__,
                              type(exc).__name__, exc)

    pack = load_voice_pack(live)
    if live is None:
        if pack is not None:
            log("voice").error(
                "a rendered voice pack is on disk but no live speech engine "
                "loaded, so the pack is not used: it would be silent for "
                "every line it does not carry and could not say so. Install a "
                "Piper voice model to bring both back.")
        return None
    return pack or live


def can_speak(engine) -> bool:
    """Whether this object can actually make a sound, rather than merely exist.

    `enabled` used to be `engine is not None`, which is a test that an object
    was constructed - and the one engine that can be constructed while being
    unable to speak is exactly the one that gets built when speech is broken.
    """
    if engine is None or not callable(getattr(engine, "speak", None)):
        return False
    # Duck-typed: only the voice pack knows it can be hollow, and a test
    # double or a future engine that does not answer is assumed to work.
    return getattr(engine, "has_live_engine", True) is not False


def available_engine_name() -> str:
    engine = _best_engine()
    return getattr(engine, "name", "none") if engine else "none"
