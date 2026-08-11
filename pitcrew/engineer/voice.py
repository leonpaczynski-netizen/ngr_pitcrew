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
                print(f"[voice] {type(exc).__name__}: {exc}")


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
    """The first speech engine that actually imports on this machine."""
    for factory in (Sapi5Engine,):
        try:
            return factory()
        except Exception:                       # noqa: BLE001
            continue
    return None


def available_engine_name() -> str:
    engine = _best_engine()
    return getattr(engine, "name", "none") if engine else "none"
