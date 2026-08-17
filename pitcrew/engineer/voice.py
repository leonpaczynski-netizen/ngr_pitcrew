"""Saying it out loud.

The driver is in a headset and cannot see any screen, so audio is not a nicety
here — it is the only channel. That has consequences the old implementation
learned the hard way and this one inherits:

* **Speech runs on its own thread.** Synthesising on the Qt thread freezes the
  UI mid-race; synthesising on the telemetry thread drops packets.
* **A newer call outranks an older one.** If two calls queue up, the driver
  wants the one that is still true. The queue is short and drops stale items
  rather than reading a backlog at him three corners too late.
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
import queue
import threading
import wave
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

PACK_ROOT = Path(__file__).resolve().parent / "voice_pack"
PACK_MANIFEST = "manifest.json"


def clip_filename(text: str) -> str:
    """A stable filename for a line. The same string always names the same
    file, on any machine, in any order - so a pack is diffable and a re-render
    overwrites rather than accumulates."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{digest}.wav"

# What a spoken line calls itself while it holds a stream open, for the log
# line a deferred device rebuild writes. See `audio_devices.begin_playback`.
SPOKEN_LINE = "the engineer's line"

# A call older than this has been overtaken by the race.
STALE_AFTER_S = 8.0
# Deliberately shallow: a backlog read at the driver is worse than silence.
MAX_QUEUED = 3

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
        self._queue: queue.Queue = queue.Queue()
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
        if warm is None:
            return

        def run() -> None:
            try:
                warm()
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

    def say(self, text: str) -> None:
        if not text:
            return
        self.spoken.append(text)
        if not self.enabled:
            return
        # Drop the oldest rather than grow a backlog.
        while self._queue.qsize() >= MAX_QUEUED:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._queue.put((_now(), text))

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
            self._engine.speak(text)
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
            item = self._queue.get()
            if item is None:
                return
            queued_at, text = item
            if _now() - queued_at > STALE_AFTER_S:
                # The race has moved on; saying it now would mislead.
                continue
            try:
                self._engine.speak(text)
            except LineCut:
                # A rebuild of the audio device list closed the stream in the
                # middle of the line. Not a failure of the engine, so it does
                # not touch `_failures` - the card is fine and the next line
                # will play - but the driver heard half a sentence, and half a
                # sentence from a race engineer is worse than none.
                #
                # Re-queued with its ORIGINAL timestamp, not a fresh one. The
                # staleness rule above is already the right test for whether a
                # call is still worth making, and restarting the clock here
                # would let a box call arrive ten seconds after it was true.
                age = _now() - queued_at
                if age <= STALE_AFTER_S:
                    log("voice").warning(
                        "the audio devices were rebuilt mid-line and cut %r "
                        "off after %.1fs - saying it again.", text, age)
                    self._queue.put((queued_at, text))
                else:
                    log("voice").warning(
                        "the audio devices were rebuilt mid-line and cut %r "
                        "off. It is %.1fs old now, so it is dropped rather "
                        "than said late.", text, age)
            except Exception as exc:            # noqa: BLE001 - see below
                # Deliberately broad: a synthesis failure mid-race must not
                # take the app with it, and the driver still has the screen
                # and the call log. Reported, never swallowed silently.
                self._failures += 1
                self.last_error = f"{type(exc).__name__}: {exc}"
                log("voice").error("%s (nothing said for %d call(s))",
                                   self.last_error, self._failures,
                                   exc_info=True)
            else:
                if self._failures:
                    log("voice").info("voice recovered after %d silent call(s)",
                                      self._failures)
                self._failures = 0
                self.last_error = None


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
        """Load the model now, so the first real call does not wait for it."""
        self._load()

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
        with _play_lock():
            stream = None
            line = None
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
                    stream.write(samples)
            finally:
                if stream is not None:
                    # stop() drains what is already queued; close() would cut
                    # the last syllable off.
                    stream.stop()
                    stream.close()
                if line is not None:
                    audio_devices.end_playback(line)
        if line is not None and line.interrupted:
            raise LineCut("a device rebuild closed the stream mid-line")


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

    def __init__(self, pack_dir: Path, clips: dict, fallback=None) -> None:
        self._dir = pack_dir
        self._clips = clips
        self._fallback = fallback
        self.hits = 0
        self.misses = 0

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
        with _play_lock():
            stream = None
            line = None
            try:
                for name in segments:
                    samples, rate = self._read(self._clips[name]["file"])
                    if stream is None:
                        # One step, under the enumeration lock, for the two
                        # reasons in `audio_devices.begin_playback`.
                        stream, line = audio_devices.open_and_declare(
                            SPOKEN_LINE, lambda: open_output(rate))
                    stream.write(samples)
            finally:
                if stream is not None:
                    stream.stop()
                    stream.close()
                if line is not None:
                    audio_devices.end_playback(line)
        if line is not None and line.interrupted:
            raise LineCut("a device rebuild closed the stream mid-line")

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
                clips = json.load(handle).get("clips") or {}
        except (OSError, ValueError) as exc:
            log("voice").warning("voice pack %s is unreadable: %s",
                                 folder.name, exc)
            continue
        if clips:
            log("voice").info("voice pack %s loaded, %d clips",
                              folder.name, len(clips))
            return VoicePackEngine(folder, clips, fallback)
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
