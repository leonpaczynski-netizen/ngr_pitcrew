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
"""
from __future__ import annotations

import queue
import threading

from pitcrew.diagnostics import log

# A call older than this has been overtaken by the race.
STALE_AFTER_S = 8.0
# Deliberately shallow: a backlog read at the driver is worse than silence.
MAX_QUEUED = 3

# Passing engine=None means "this machine has no speech"; the default
# means "find the best one available". Conflating the two made a test
# asking for silence get SAPI5 instead.
AUTO = object()


class Voice:
    """Speaks queued lines on a background thread.

    `engine` is injectable so the whole race path can be driven in tests, and
    so a machine with no speech synthesis at all still runs the app.
    """

    def __init__(self, engine=AUTO, *, enabled: bool = True) -> None:
        self._engine = _best_engine() if engine is AUTO else engine
        self.enabled = enabled and self._engine is not None
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
            except Exception as exc:            # noqa: BLE001 - see below
                # Deliberately broad: a synthesis failure mid-race must not
                # take the app with it, and the driver still has the screen
                # and the call log. Reported, never swallowed silently.
                log("voice").error("%s: %s", type(exc).__name__, exc,
                                   exc_info=True)


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
    _play_lock = threading.Lock()

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
        import sounddevice as sd

        with self._play_lock:
            stream = None
            try:
                for samples, rate in self.synthesise(text):
                    if stream is None:
                        stream = sd.OutputStream(samplerate=rate, channels=1,
                                                 dtype="int16")
                        stream.start()
                    stream.write(samples)
            finally:
                if stream is not None:
                    # stop() drains what is already queued; close() would cut
                    # the last syllable off.
                    stream.stop()
                    stream.close()


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
    """

    name = "sapi5"

    def __init__(self) -> None:
        import win32com.client  # noqa: F401 - probe that it imports
        self._voice = None

    def speak(self, text: str) -> None:
        import pythoncom
        import win32com.client

        if self._voice is None:
            pythoncom.CoInitialize()
            self._voice = win32com.client.Dispatch("SAPI.SpVoice")
        self._voice.Speak(text)


def _best_engine():
    """The best speech engine this machine can actually run.

    Piper first: it is a neural voice and sounds like a race engineer, where
    SAPI sounds like a screen reader. SAPI is the fallback rather than the
    default, and no speech at all is still a running app.
    """
    for factory in (PiperEngine, Sapi5Engine):
        try:
            return factory()
        except Exception as exc:                # noqa: BLE001
            log("voice").info("%s unavailable: %s: %s", factory.__name__,
                              type(exc).__name__, exc)
    return None


def available_engine_name() -> str:
    engine = _best_engine()
    return getattr(engine, "name", "none") if engine else "none"
