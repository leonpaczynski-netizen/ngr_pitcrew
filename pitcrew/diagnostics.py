"""Leaving a trace.

The app is launched from a pinned shortcut through `pythonw.exe`, which has no
console. `sys.stdout` and `sys.stderr` are `None`, so every `print()` in the
codebase is a silent no-op and every traceback goes nowhere. The first time it
died mid-session there was nothing to read afterwards — not a line.

`CLAUDE.md` §7 says the app must fail loudly. Loud means written down, because
the driver is in a headset and cannot see the screen it would be shouted on.

Three different things can end this process, and each needs its own catcher:

* **An unhandled exception on the Qt thread.** PyQt calls `sys.excepthook` and
  then aborts the process. Hooking it is the only chance to record the
  traceback before the abort.
* **An unhandled exception on a worker thread** — the UDP listener, the voice
  thread. `threading.excepthook` catches those.
* **A native crash.** Piper runs onnxruntime and plays through PortAudio, both
  native, and a device change under a live stream can take the process out with
  no Python exception at all. `faulthandler` is what turns that from a window
  that vanished into a stack trace.

Nothing here is Qt-aware except `install_qt_handler`, so the telemetry and
voice threads can log without importing a UI toolkit.
"""
from __future__ import annotations

import faulthandler
import logging
import logging.handlers
import platform
import sys
import threading
import time
from pathlib import Path

LOG_DIR = Path("logs")
# Set by `install`, read by `log_dir`. None until then.
_ACTIVE_DIR: Path | None = None
LOG_FILE = LOG_DIR / "pitcrew.log"
# Native faults are written raw by faulthandler, which cannot use the logging
# module - it runs inside a signal handler.
FAULT_FILE = LOG_DIR / "pitcrew-fault.log"
# The 20 Hz wind frame log, kept apart from the main record - see
# `_install_frame_log` for why that separation is not a tidiness preference.
FRAME_FILE = LOG_DIR / "pitcrew-wind-frames.log"

MAX_BYTES = 2_000_000
BACKUPS = 3
# **The frame log has to hold a whole session, and at the main log's size it
# held twenty minutes.** A frame line is about 115 bytes; at 60 Hz that
# rolled a 2 MB file every five minutes, and the three drops of 3 Sep 2026
# had been rotated out of existence before the log was opened. At 20 Hz it
# is ~8 MB an hour, so ten megabytes six deep is a little over seven hours -
# longer than any day on the rig. The instrument built to catch a felt drop
# is worthless if it cannot remember the session the drop was felt in.
FRAME_MAX_BYTES = 10_000_000
FRAME_BACKUPS = 6
LOGGER_NAME = "pitcrew"

_installed = False
_fault_file = None          # kept open for the life of the process on purpose


def log(name: str = "") -> logging.Logger:
    """The app logger, or a named child of it."""
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


def install(*, level: int = logging.INFO, log_dir: Path | None = None) -> Path:
    """Start writing everything down. Safe to call more than once."""
    global _installed, _fault_file, _ACTIVE_DIR
    if _installed:
        return _resolve(log_dir) / LOG_FILE.name

    directory = _resolve(log_dir)
    _ACTIVE_DIR = directory
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / LOG_FILE.name

    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(threadName)-14s %(name)-24s %(message)s"))

    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.propagate = False

    # A console is a bonus, not the record. Under pythonw there is none, and
    # adding a StreamHandler on a None stream would raise at import time.
    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        logger.addHandler(console)

    _install_frame_log(directory)

    _fault_file = (directory / FAULT_FILE.name).open("a", encoding="utf-8")
    faulthandler.enable(file=_fault_file, all_threads=True)

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook

    _installed = True
    return path


def _install_frame_log(directory: Path) -> None:
    """A file of its own for the 20 Hz wind frame log.

    **It must not share `pitcrew.log`.** Twenty lines a second is ~72,000 an
    hour, which would roll the main log past its backups in minutes -
    and the main log's history is the only reason the fan dropouts could be
    investigated at all. Diagnosing one fault must not destroy the record of
    the next.

    `propagate = False`, so these lines go here and nowhere else.
    """
    frames = logging.getLogger(f"{LOGGER_NAME}.wind.frames")
    handler = logging.handlers.RotatingFileHandler(
        directory / FRAME_FILE.name, maxBytes=FRAME_MAX_BYTES,
        backupCount=FRAME_BACKUPS, encoding="utf-8")
    # No level or thread name: every line is INFO from the wind thread, and
    # the row is the data.
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    frames.addHandler(handler)
    frames.propagate = False


def _resolve(log_dir: Path | None) -> Path:
    return Path(log_dir) if log_dir is not None else LOG_DIR


def log_dir() -> Path:
    """Where this run is writing. The claim record goes here too.

    Both are state about the run rather than about the driver's data, and a
    test that redirects the log must be able to redirect the claim with it -
    otherwise a suite run would step on the real app's record.
    """
    return _ACTIVE_DIR or LOG_DIR


def _os_description() -> str:
    """What machine this is, without asking WMI twice to find out.

    `platform.platform()` cost **71 ms of every launch** - measured against
    `sys.getwindowsversion()`'s 0.49 ms for the same build number. It is not
    the string that is expensive, it is how it is assembled:
    `platform.uname()` runs `win32_ver()` and `processor()`, and each of those
    is a separate WMI query. Nothing reads this value; it is one log line.

    The build number is the part a crash investigation actually uses, and it
    survives. What is lost is the marketing name and the service pack -
    `Windows-11-10.0.26200-SP0` becomes `Windows-10.0.26200 (10, 0, 26200)`.

    The raw tuple goes in beside it deliberately. `getwindowsversion` reports
    the **manifested** version, and the Python launcher's manifest is what
    makes it correct here: repackaged without one, this silently returns
    6.2.9200 on a machine running 11. A bare `Windows-6.2.9200` reads as a
    fact about the machine; printed next to its own tuple it reads as what it
    is, which is the manifest talking.
    """
    if sys.platform != "win32":
        return platform.platform()
    version = sys.getwindowsversion()
    return (f"Windows-{version.major}.{version.minor}.{version.build} "
            f"({version.major}, {version.minor}, {version.build})")


def seconds_since_process_start() -> float | None:
    """How long this process has been alive, or `None` where it cannot be asked.

    **The clock the driver is actually running.** Timing from the top of
    `main()` misses the interpreter and the import graph, which the startup
    investigation of 5 Sep measured at 323 ms of imports alone - so a figure
    starting there is a smaller number about a different thing. Windows will
    say when the process was created; this asks it.

    `None` rather than a fallback to "since this function was first called",
    because a duration measured from an arbitrary later point, reported under
    the same name, is the kind of substitution that gets believed.
    """
    try:
        import ctypes
        import ctypes.wintypes as wintypes

        kernel32 = ctypes.windll.kernel32
        # **The signatures are not optional.** Left to ctypes' defaults,
        # `GetCurrentProcess` comes back as a C int and the -1 pseudo-handle
        # is truncated on 64-bit, so `GetProcessTimes` fails and sets no
        # error - it returned 0 with `GetLastError` 0, which reads exactly
        # like "not available on this platform" and is not.
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME)]
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        created = wintypes.FILETIME()
        ended = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        ok = kernel32.GetProcessTimes(
            kernel32.GetCurrentProcess(), ctypes.byref(created),
            ctypes.byref(ended), ctypes.byref(kernel), ctypes.byref(user))
        if not ok:
            return None
        ticks = (created.dwHighDateTime << 32) | created.dwLowDateTime
        # FILETIME counts 100 ns units from 1601-01-01; 11644473600 s to epoch.
        started = ticks / 10_000_000.0 - 11_644_473_600.0
        return max(0.0, time.time() - started)
    except Exception:                                        # noqa: BLE001
        return None


def mark(phase: str) -> None:
    """Log how far into the launch we are, at a named phase.

    **Nothing recorded time-to-window before this**, which is why "the app
    takes ages to open" could not be settled: the 5 Sep investigation measured
    imports and construction and then had to say plainly that it could not
    measure paint, and an adversarial review found the conclusion unsupported
    partly for that reason. One line per phase costs nothing and makes the
    question answerable from the log the driver already has.
    """
    elapsed = seconds_since_process_start()
    if elapsed is None:
        log("startup").info("startup: %s", phase)
        return
    log("startup").info("startup: %-22s %6.0f ms since process start",
                        phase, elapsed * 1000.0)


# A launch step slower than this is written to the log as a WARNING with its
# time. A quiet launch builds the whole window in ~0.3 s and no one step
# takes over 0.12 s, so a second is a fault, not a slow machine.
SLOW_STEP_S = 1.0


class timed_step:
    """`with timed_step("EventScreen"):` - WARN if the body is slow.

    **Why this exists** (19 Sep 2026): one launch under load spent 17.7 s
    building the Event screen, and the log said nothing at all between "store
    open" and "window built" - a repeat on race day would have left no trace
    of where.

    **Every step is written, at INFO, and a slow one at WARNING** (round 4).
    Silent-when-fast left the log unable to say where a normal launch's time
    goes, so the waterfall had to be rebuilt by hand each time it was asked.
    A dozen lines per launch, into a log that already takes hundreds.
    """

    def __init__(self, name: str, warn_after_s: float | None = None) -> None:
        self.name = name
        self.warn_after_s = warn_after_s
        self.took_s = 0.0

    def __enter__(self):
        self._began = time.perf_counter()
        return self

    def __exit__(self, *_exc) -> bool:
        self.took_s = time.perf_counter() - self._began
        limit = SLOW_STEP_S if self.warn_after_s is None else self.warn_after_s
        if self.took_s >= limit:
            log("startup").warning(
                "slow launch step: %s took %.0f ms (warns over %.0f ms)",
                self.name, self.took_s * 1000.0, limit * 1000.0)
        else:
            log("startup").info("launch step: %-24s %6.1f ms",
                                self.name, self.took_s * 1000.0)
        return False


class LaunchWatchdog:
    """Writes where the Qt thread is if the first frame is late.

    A daemon thread that waits on an event. If the window has not drawn its
    first frame `every_s` after this was armed, it logs the Qt thread's
    Python stack as a WARNING, and again every `every_s`, at most `dumps`
    times. A stall inside Qt shows as the Python line that called into it -
    which widget, which call. `disarm()` at the first frame (and on the way
    out) ends it. Nothing here touches Qt; it only reads frames and logs.
    """

    def __init__(self, every_s: float = 3.0, dumps: int = 5) -> None:
        self._done = threading.Event()
        self._every_s = every_s
        self._dumps = dumps
        self._target = threading.current_thread().ident
        self._began = time.perf_counter()
        self.fired = 0
        threading.Thread(target=self._run, name="launch-watchdog",
                         daemon=True).start()

    def disarm(self) -> None:
        self._done.set()

    def _run(self) -> None:
        import traceback

        for _ in range(self._dumps):
            if self._done.wait(self._every_s):
                return
            frame = sys._current_frames().get(self._target)
            if frame is None:
                return                  # the thread it watched has ended
            stack = "".join(traceback.format_stack(frame))
            self.fired += 1
            log("startup").warning(
                "the launch has not drawn its first frame after %.1f s - "
                "the Qt thread is here:\n%s",
                time.perf_counter() - self._began, stack.rstrip())


_WATCHDOG: LaunchWatchdog | None = None


def watch_launch(every_s: float = 3.0, dumps: int = 5) -> LaunchWatchdog:
    """Arm the launch watchdog, from the Qt thread. Once per process."""
    global _WATCHDOG
    if _WATCHDOG is None:
        _WATCHDOG = LaunchWatchdog(every_s, dumps)
    return _WATCHDOG


def launch_drawn() -> None:
    """The first frame is up (or the launch is over): stand the watchdog
    down. Safe to call any number of times, armed or not."""
    if _WATCHDOG is not None:
        _WATCHDOG.disarm()


def banner(**facts) -> None:
    """One line per run, so a log covering three sessions can be told apart."""
    logger = log()
    logger.info("=" * 62)
    logger.info("Pit Crew starting - python %s on %s (%s)",
                platform.python_version(), _os_description(), sys.platform)
    for key, value in facts.items():
        logger.info("  %s: %s", key, value)


def _excepthook(kind, value, traceback) -> None:
    """Record, then hand back to the default.

    PyQt aborts the process after this returns, so this is the last thing that
    runs. Recording first is the whole point.
    """
    log().critical("unhandled exception on %s",
                   threading.current_thread().name,
                   exc_info=(kind, value, traceback))
    sys.__excepthook__(kind, value, traceback)


def _thread_excepthook(args) -> None:
    if args.exc_type is SystemExit:
        return
    log().critical("unhandled exception on thread %s",
                   getattr(args.thread, "name", "?"),
                   exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def install_qt_handler() -> None:
    """Send Qt's own warnings to the same file.

    Qt writes to stderr, which under pythonw is nowhere. A stack of Qt layout
    warnings is often the only sign of what the UI was doing when it went.
    """
    try:
        from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
    except ImportError:                          # pragma: no cover - no Qt
        return

    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handler(mode, context, message) -> None:
        log("qt").log(levels.get(mode, logging.INFO), "%s", message)

    qInstallMessageHandler(handler)
