"""Next Gear Racing Pit Crew.

    python -m pitcrew.app
"""
from __future__ import annotations

import os
import sys
import time

from pathlib import Path

if __name__ == "__main__":
    # **The real launch starts here, before the imports below** - about
    # 270 ms of them, none touching a font - so a Qt worker can load the
    # font fallback in that time instead of on the Qt thread later. See
    # `pitcrew.boot`. Only for `python -m pitcrew.app`, which is what the
    # shortcut runs; an import of this module does nothing new.
    from pitcrew import boot as _boot

    _boot.early()

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer  # noqa: E402
from PyQt6.QtGui import (QColor, QFontMetrics, QIcon, QKeySequence,
                         QPainter, QShortcut)
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pitcrew import diagnostics, settings
from pitcrew.engineer import ptt, voice
from pitcrew.controller import DEFAULT_PORT, PitCrewController
from pitcrew.export.payload import APP_VERSION
from pitcrew.store.db import DEFAULT_DB_PATH, Store
from pitcrew.ui import font_warm, theme
from pitcrew.ui.car_screen import CarScreen
from pitcrew.ui.event_screen import EventScreen
from pitcrew.ui.practice_screen import PracticeScreen
from pitcrew.ui.race_screen import RaceScreen
from pitcrew.ui.reference_screen import ReferenceScreen
from pitcrew.ui.settings_screen import SettingsScreen
from pitcrew.ui.strategy_screen import StrategyScreen
from pitcrew.ui.widgets import Rule, StencilLabel

# The size the app wants, not the size it takes. `fit_to_screen` clamps it to
# whatever the display it opens on will actually give.
WINDOW = (1600, 1000)

# Below this the rack cannot show its columns and starts scrolling sideways
# instead. It is a floor on the *window*, not on the layout: the layout has to
# survive being given less than it wants, because a display can be smaller
# than this and refusing to open is not an answer.
MIN_WINDOW = (900, 560)

# The rail, grouped by the job each screen belongs to. Two loops run through
# this app and they are not the same work: PREPARE/LEARN is the setup loop
# that makes the car faster, RACE DAY is the one used under pressure. Flat,
# they read as seven peers; named, the rail describes the work.
#
# **There is no Engineer screen.** It existed to build a prompt, hand it to
# the driver to paste, and take a setup sheet back - and that whole transport
# is gone: the tune builder holds the car and issues changes directly. What
# the app still owes him is what it measured, which is Practice and Race.
# **Strategy is not a race-day screen** (row 1.7). It is where a plan is
# built, approved and qualifying is planned - all of it read with the headset
# off - and the one thing on it the driver needed on the grid, the standing
# orders, is on the Race page now. Leaving it under *Race day* offered him a
# page to go and read at the moment he should be on the page he starts from.
#
# Split rather than relocated, deliberately: `SCREENS` is this flattened and
# the rail indexes straight into the stack, so moving the NAME would renumber
# the stack's build order, `LATE_SCREENS` and the shortcuts. This leaves the
# flattened order identical and changes only what the rail says.
NAV_GROUPS = (
    ("Prepare", ("Event", "Car")),
    ("Learn", ("Practice",)),
    ("Plan", ("Strategy",)),
    ("Race day", ("Race",)),
    ("", ("Reference", "Settings")),
)
SCREENS = tuple(name for _heading, names in NAV_GROUPS for name in names)
ICON = Path(__file__).resolve().parent.parent / "pitcrew.ico"

# The latest the launch holds the speech warm-up and the phone strip back
# after the window is shown - see `PitCrewWindow.finish_launch`. Normally
# released well before.
SPEECH_BACKSTOP_MS = 3000

# How long the launch waits for the window's first paint before warming the
# deferred screens anyway - see `_FirstPaint`.
FIRST_PAINT_BACKSTOP_MS = 1000

# Windows groups taskbar buttons by this id. Without one, a Python GUI app is
# grouped under the interpreter, so a pinned shortcut and the running window
# appear as two separate buttons with two different icons.
from pitcrew.boot import APP_ID  # noqa: E402


# Held for the life of the process, and **released on the way out by
# `_release_sole_instance`.**
#
# The sentence that used to be here - "a named mutex is released by Windows
# when the process ends, however it ends - including a kill - so it cannot be
# left stale by a crash the way a lock file can" - was the defect, written
# down as a reassurance. It assumes the process can end.
#
# **Measured, three times in two days.** The CH340 wind controller stops
# answering, `CloseHandle` on its port blocks inside the driver and never
# returns, and the process is left with one thread parked in a kernel call
# that nothing can retire. 24 Aug 2026, PID 15644: one thread, 0.000 seconds
# of CPU over six, 301 handles, and it **survived `TerminateProcess`**. The
# mutex outlived it, so the guard - added 22 Aug - refused every launch after
# it. He was locked out at 09:54, 12:05, 12:13 and 12:42.
#
# The guard turned a survivable session into an unrecoverable one: on 22 Aug,
# *before* it existed, the app started perfectly well alongside a wedge of
# exactly this shape at 20:42 and again at 20:53. It cost him the fans and a
# UDP bind, not the evening.
#
# `main` completed on every occurrence - the log's last line is "Pit Crew
# exited with 0" - so closing this handle there is enough to fix the observed
# failure. There is exactly one handle to it: `CreateMutexW` is called once,
# nothing in this package spawns a child, and NULL security attributes are
# not inheritable. Closing it drops the refcount to zero and the name goes.
_INSTANCE_MUTEX = None

# The mutex's name, as a module constant so the tests can claim a private one.
# **They must.** Using the real name means the suite cannot run while the app
# is open - which on this rig is most of the time - and a suite that fails for
# reasons the code did not cause is a suite that stops being read.
# `Local\` scopes it to this login session, which is the right scope: two
# desktops on one machine are two rigs.
_INSTANCE_NAME = "Local\\" + APP_ID

# Who is holding it. **The mutex says whether somebody is there; this says
# who, and it is only ever used to decide what to SAY and whether refusing is
# honest.** A missing or unreadable record never blocks a launch - it drops
# us to "cannot tell", which starts.
#
# Deliberately not the mechanism. A pid file alone is exactly the stale-lock
# problem the mutex avoids: it survives a crash and a reboot. The mutex stays
# the authority on existence; this is a hint attached to it, checked against
# the process's own creation time so a recycled pid cannot impersonate it.
_INSTANCE_RECORD = "pitcrew.claim"
# How long to watch a holder's processor time before believing it is wedged.
# A live Pit Crew is never still: the wind link writes four times a second and
# the transducer renders continuously, so any live copy moves this counter
# well inside the window. Long enough to be sure, short enough that a driver
# who double-clicked twice does not think the app has hung.
_WEDGE_SAMPLE_S = 0.7


def _forced() -> bool:
    """Has the driver said start regardless?

    **Two doors, because the environment variable is not one he can use.**
    `PITCREW_ALLOW_MULTIPLE=1` was written for a developer running a second
    copy against another database on purpose; at 19:55 on a race night, with
    the app refusing to open, setting an environment variable is not a
    recovery. `--force` is the same override reachable from a shortcut, which
    is what `tools/install_shortcut.py` now makes one of.
    """
    return (os.environ.get("PITCREW_ALLOW_MULTIPLE") == "1"
            or "--force" in sys.argv[1:])


def _record_path():
    return diagnostics.log_dir() / _INSTANCE_RECORD


def _process_facts(pid: int):
    """`(created_ticks, cpu_seconds)` for a live pid, or None.

    `created_ticks` identifies the process beyond its pid - Windows reuses
    pids, and a fresh process wearing a dead one's number must not be able to
    impersonate it. `cpu_seconds` is kernel plus user, which is the only
    number that separates a copy that is working from one that is parked in a
    driver call it will never return from.
    """
    try:
        import ctypes
        from ctypes import wintypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL,
                                         wintypes.DWORD)
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,
                                      False, int(pid))
        if not handle:
            return None
        try:
            created = wintypes.FILETIME()
            exited = wintypes.FILETIME()
            in_kernel = wintypes.FILETIME()
            in_user = wintypes.FILETIME()
            ok = kernel32.GetProcessTimes(
                handle, ctypes.byref(created), ctypes.byref(exited),
                ctypes.byref(in_kernel), ctypes.byref(in_user))
            if not ok:
                return None

            def _ticks(value) -> int:
                return (value.dwHighDateTime << 32) | value.dwLowDateTime

            # 100 ns units throughout, which is what FILETIME counts in.
            spent = (_ticks(in_kernel) + _ticks(in_user)) / 1e7
            return _ticks(created), spent
        finally:
            kernel32.CloseHandle(handle)
    except Exception:                                        # noqa: BLE001
        return None                                          # not Windows


def _write_claim_record() -> None:
    """Say who took the claim. Never raises - this is a hint, not the lock."""
    try:
        facts = _process_facts(os.getpid())
        created = facts[0] if facts else 0
        path = _record_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{os.getpid()} {created}\n", encoding="utf-8")
    except Exception:                                        # noqa: BLE001
        pass


def _read_claim_record():
    """`(pid, created_ticks)` of the holder, or None if we cannot tell.

    None is the answer that starts the app, so every failure here - missing
    file, half-written line, a pid that has since been reused - has to arrive
    as None rather than as a guess.
    """
    try:
        pid_text, created_text = _record_path().read_text(
            encoding="utf-8").split()
        pid, created = int(pid_text), int(created_text)
    except Exception:                                        # noqa: BLE001
        return None
    if pid == os.getpid():
        return None
    facts = _process_facts(pid)
    if facts is None:
        return None                                          # gone already
    if created and facts[0] != created:
        return None                                          # a recycled pid
    return pid, facts[0]


def _thread_count(pid: int) -> int | None:
    """How many threads the process still has, or None if we cannot look.

    **The second discriminator, and it is the one that makes the verdict
    safe.** Processor time alone is not enough: `GetProcessTimes` has about
    15 ms of resolution, and a live copy sitting in the menus with the
    haptics and the wind both switched off could plausibly burn less than
    that inside the sample window and be mistaken for a corpse. Getting that
    wrong means two live copies, which is the 22 Aug transducer.

    A running Pit Crew has many threads - Qt, the listener, the wind link,
    the transducer, the gauge sampler, push-to-talk. A wedged one has the
    single un-retirable thread left parked in the driver: PID 15644 was
    measured at exactly one.
    """
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPTHREAD = 0x00000004
        INVALID = wintypes.HANDLE(-1).value

        class THREADENTRY32(ctypes.Structure):
            _fields_ = [("dwSize", wintypes.DWORD),
                        ("cntUsage", wintypes.DWORD),
                        ("th32ThreadID", wintypes.DWORD),
                        ("th32OwnerProcessID", wintypes.DWORD),
                        ("tpBasePri", ctypes.c_long),
                        ("tpDeltaPri", ctypes.c_long),
                        ("dwFlags", wintypes.DWORD)]

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0)
        if snapshot == INVALID or not snapshot:
            return None
        try:
            entry = THREADENTRY32()
            entry.dwSize = ctypes.sizeof(THREADENTRY32)
            if not kernel32.Thread32First(snapshot, ctypes.byref(entry)):
                return None
            seen = 0
            while True:
                if entry.th32OwnerProcessID == pid:
                    seen += 1
                if not kernel32.Thread32Next(snapshot, ctypes.byref(entry)):
                    break
            return seen
        finally:
            kernel32.CloseHandle(snapshot)
    except Exception:                                        # noqa: BLE001
        return None


# A running Pit Crew is never this thin. Qt alone brings more than this before
# a single device is opened; the wedge that started all of this had one.
_WEDGED_THREADS = 2


def _holder_is_wedged(pid: int) -> bool:
    """Has this process stopped running altogether?

    **Both signals must agree, and the bias is deliberate.** Any processor
    time at all, or a normal complement of threads, means a live copy and a
    refusal - because the thing on the other side of a wrong answer here is
    the 22 Aug transducer. Not being able to look at all is a different
    question, answered by the caller, and it starts the app.
    """
    first = _process_facts(pid)
    if first is None:
        return True                                          # it just went
    time.sleep(_WEDGE_SAMPLE_S)
    second = _process_facts(pid)
    if second is None:
        return True
    if second[1] > first[1]:
        return False                                         # it is working
    threads = _thread_count(pid)
    if threads is None:
        # Still, but we cannot count its threads. Treat stillness alone as
        # too weak to act on: refusing is recoverable by closing a window,
        # and the override shortcut exists for the case where it is not.
        return False
    return threads <= _WEDGED_THREADS


def _clear_claim_record() -> None:
    try:
        _record_path().unlink(missing_ok=True)
    except Exception:                                        # noqa: BLE001
        pass


def _release_sole_instance() -> None:
    """Give the name back, rather than trusting the process to end.

    Called from a `finally` around `app.exec`, which is the one place that
    runs on every exit path this app has ever actually taken - including the
    three wedges, all of which reached the end of `main`.
    """
    global _INSTANCE_MUTEX
    handle, _INSTANCE_MUTEX = _INSTANCE_MUTEX, None
    _clear_claim_record()
    if not handle:
        return
    try:
        import ctypes

        # **`CloseHandle` alone, and no `ReleaseMutex`.** The mutex is created
        # with `bInitialOwner=False` and never waited on, so no thread has
        # ever owned it - confirmed against the live wedge on 24 Aug, where
        # `WaitForSingleObject` returned WAIT_OBJECT_0 rather than
        # WAIT_ABANDONED. `ReleaseMutex` on a mutex you do not own fails with
        # ERROR_NOT_OWNER and would achieve nothing but a misleading line in
        # a debugger.
        ctypes.WinDLL("kernel32").CloseHandle(handle)
    except Exception:                                        # noqa: BLE001
        pass


class Claim:
    """The verdict on starting, and the sentence that goes with it."""

    def __init__(self, allowed: bool, message: str = "",
                 holder: int | None = None) -> None:
        self.allowed = allowed
        self.message = message
        self.holder = holder


def _claim_sole_instance() -> Claim:
    """Decide whether this copy may start, and say why either way.

    **Two live copies fighting over one rig is how a bad session became an
    unrecoverable one.** 22 Aug 2026: an instance was left running, a second
    was started, and between them they held COM5 against each other, rendered
    two haptic streams into the same endpoint until it degraded, and thrashed
    the recovery ladder until PortAudio was terminated over an open stream
    and took the process down. The wind, the transducer and the microphone
    are single-owner devices; nothing about this app is safe to run twice.

    **But existence is not liveness, and treating it as such cost four
    launches on 24 Aug.** A process wedged in a driver call holds the name
    for ever - it cannot be killed, so Windows never takes it back - and the
    old guard read that as a running copy and refused. It is not a running
    copy. It has no threads, renders nothing and answers nothing, and a
    second instance alongside it gets the whole rig bar the port it leaked.
    Measured on the day: both UDP ports free, only COM5 held.

    So the question asked here is "is there a copy that can still touch the
    hardware", and it is answered from the holder's processor time. Refusing
    needs POSITIVE evidence of a live copy. Everything else starts:

    * no claim record, unreadable, a pid that has gone, a recycled pid, not
      Windows -> start. Cannot tell is not the same as yes, and this is
      race-night software: failing to start is the worst outcome there is.
    * the holder is burning processor time -> refuse. This is 22 Aug, and
      it is the one verdict that does not bend.
    * the holder has stopped altogether -> start, and say what it is holding.

    Never raises. A machine where none of this works is a machine that should
    still be able to race.

    `PITCREW_ALLOW_MULTIPLE=1` overrides the lot, for a developer running a
    second copy against a different database on purpose - and for the driver,
    through the "force start" shortcut, when everything else has gone wrong.
    """
    global _INSTANCE_MUTEX
    if _forced():
        return Claim(True)
    if _INSTANCE_MUTEX is not None:
        # **We already hold it, so we are not our own second instance.**
        # `CreateMutexW` reports ERROR_ALREADY_EXISTS for a name that exists
        # whoever created it - including this process - so asking twice
        # without this would have the app refuse itself. `main` asks once
        # today; a restart-in-place or a test would not.
        return Claim(True)
    try:
        import ctypes
        from ctypes import wintypes

        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL,
                                          wintypes.LPCWSTR)
        handle = kernel32.CreateMutexW(None, False, _INSTANCE_NAME)
        if not handle:
            return Claim(True)
        _INSTANCE_MUTEX = handle
        if ctypes.get_last_error() != ERROR_ALREADY_EXISTS:
            _write_claim_record()
            return Claim(True)
    except Exception:                            # noqa: BLE001
        return Claim(True)                       # not Windows, or too old

    known = _read_claim_record()
    if known is None:
        # The name is taken and we cannot say by what. Start, and leave a
        # line in the log saying so, because this is also what a claim record
        # deleted by hand looks like.
        return Claim(True, "Something already holds the Pit Crew rig claim "
                           "and it left no record of itself. Starting anyway.")
    pid = known[0]
    if not _holder_is_wedged(pid):
        return Claim(False, (
            f"Pit Crew is already running - process {pid}, and it is "
            f"answering. Two copies cannot share the rig: they hold the wind "
            f"controller against each other and render two haptic streams "
            f"into one transducer, which is what breaks it. Switch to the "
            f"other Pit Crew window. This copy will not start."), pid)
    _write_claim_record()
    return Claim(True, (
        f"The previous Pit Crew never finished closing. Process {pid} still "
        f"exists but has stopped running entirely - Windows cannot end it, "
        f"because it is stuck releasing the wind controller. This copy has "
        f"started anyway.\n\nThe fans will not work this session: that "
        f"process still holds the serial port. Everything else - telemetry, "
        f"the tyre gauge, the engineer, push-to-talk and the haptics - is "
        f"unaffected.\n\nWorth trying: unplug the wind controller's USB "
        f"and plug it back in. That may free the port and let the stuck "
        f"process finally end."), pid)


def _claim_taskbar_identity() -> None:
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:                            # noqa: BLE001
        pass                                     # not Windows, or too old


class NavItem(StencilLabel):
    """A rail entry you can reach without a mouse.

    The rail used to be eight labels with `mousePressEvent` reassigned onto
    them. A QLabel takes no focus and answers no key, so the app's entire
    primary navigation was unreachable from the keyboard - while every one of
    the 355 controls inside the screens was focusable. The gap was the rail
    alone, and it is the one thing used on every visit.

    Focus is drawn rather than inherited: Qt paints no focus ring on a label,
    and a focus nobody can see is the same as none.
    """

    def __init__(self, text: str, index: int, rail: "NavRail") -> None:
        super().__init__(text, size=13, tracking=14.0)
        self._index = index
        self._rail = rail
        self.setContentsMargins(0, 6, 0, 0)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"{text} screen")

    def mousePressEvent(self, event) -> None:      # noqa: N802 - Qt naming
        if self.isEnabled():
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._rail.select(self._index)

    def keyPressEvent(self, event) -> None:        # noqa: N802 - Qt naming
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._rail.select(self._index)
        elif key in (Qt.Key.Key_Down, Qt.Key.Key_Right):
            self._rail.focus_item(self._index + 1)
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Left):
            self._rail.focus_item(self._index - 1)
        elif key == Qt.Key.Key_Home:
            self._rail.focus_item(0)
        elif key == Qt.Key.Key_End:
            self._rail.focus_item(-1)
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event) -> None:           # noqa: N802 - Qt naming
        super().paintEvent(event)
        if not self.hasFocus():
            return
        # A crayon bar in the rail's left margin: the same mark the app uses
        # for "this is yours", in the one place a ring would fight the
        # lettering.
        painter = QPainter(self)
        painter.fillRect(0, 6, 3, self.height() - 6, QColor(theme.CRAYON))
        painter.end()


class NavRail(QWidget):
    """Screen selection, lettered like a rack tag and grouped by job.

    Seven equal peers in one list misrepresented the work. Two loops run
    through this app - prepare the car and learn from it, and race it - and
    the rail showed them as siblings of each other and of Reference and
    Settings, in an order that put the last step of the first loop after the
    race.

    Grouping rather than restructuring: the same seven screens, with the
    loops named and ruled apart, so the rail describes the work instead of
    listing it.

    **Four named groups since row 1.7**, because planning is its own step: it
    happens after the practice it rests on and before the race, and it is the
    last thing done with the headset off. Strategy left *Race day* with it -
    the standing orders are on the Race page now, so there is nothing on that
    screen he needs with a helmet on.

    **It scrolls, as of that row.** Bare it wants 425 px; with all seven
    state notes showing, 551; and the smallest display he owns gives 501.
    Nothing was clipped, because the layout spent the bottom margin first,
    but that is a budget rather than a fix and how many notes show is set by
    `nav_state` rather than by the layout. The rail is the one surface used
    on every visit and Settings is the last item on it.
    """

    def __init__(self, stack: QStackedWidget, groups,
                 parent: QWidget | None = None, builder=None) -> None:
        super().__init__(parent)
        # Called with an index just before that screen is shown, for the ones
        # that are not built until they are wanted. None everywhere else -
        # the three tests that build a rail by hand pass nothing.
        self._builder = builder
        self.setFixedWidth(178)
        self.setStyleSheet(f"background: {theme.RUBBER_DEEP};")
        self._stack = stack
        self._labels: list[StencilLabel] = []
        self._notes: list[StencilLabel] = []
        # What `set_note` was given, before elision, so a resize can redo it.
        self._note_text: list[str] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroller.setStyleSheet("background: transparent;")
        inner = QWidget()
        outer.addWidget(scroller)
        # Held because `focus_item` and `select` have to scroll to what they
        # just moved to: `QScrollArea` follows `focusNextPrevChild` and NOT a
        # direct `setFocus`, so End, Down and Ctrl+7 all put the crayon focus
        # bar 71 px below the fold with nothing on screen to say where he is.
        self._scroller = scroller
        scroller.viewport().installEventFilter(self)
        # **No local scrollbar rule.** One was added here on the strength
        # of an unstyled #9f9f9f stripe and a 14 px width - both measured
        # with `theme.apply` NOT loaded. The app-wide sheet already paints
        # the trough RUBBER_DEEP, the handle TREAD and a TREAD_LIGHT hover,
        # at 12 px. The local rule halved it to 6 px with no hover state and
        # a 1.57:1 handle, which is worse than the 2.04:1 this file rejects
        # for this rail twenty lines below.

        column = QVBoxLayout(inner)
        column.setContentsMargins(20, 26, 12, 20)
        column.setSpacing(4)
        column.addWidget(StencilLabel("Pit Crew", size=16, colour=theme.CRAYON,
                                      tracking=14.0))
        column.addSpacing(24)

        index = 0
        for position, (heading, names) in enumerate(groups):
            if position:
                column.addSpacing(14)
            if heading:
                # STENCIL_DIM, not TREAD_LIGHT. That is a border token and
                # it carried this heading and every state note below at 2.04:1
                # - worse than the STRUCK the design rejected for exactly this
                # reason, on the one surface used on every visit.
                column.addWidget(StencilLabel(heading, size=10,
                                              colour=theme.STENCIL_DIM,
                                              tracking=18.0))
                column.addSpacing(2)
                column.addWidget(Rule())
                column.addSpacing(6)
            for name in names:
                label = NavItem(name, index, self)
                if index >= stack.count():
                    label.setEnabled(False)
                    label.setToolTip("Not built yet")
                column.addWidget(label)

                # What the store already knows about this screen, so the rail
                # says where the work stands instead of only where it goes.
                note = StencilLabel("", size=10, colour=theme.STENCIL_DIM,
                                    tracking=8.0)
                note.setContentsMargins(0, 0, 0, 4)
                note.setVisible(False)
                column.addWidget(note)

                self._labels.append(label)
                self._notes.append(note)
                self._note_text.append("")
                index += 1

        column.addStretch(1)
        scroller.setWidget(inner)
        self.select(0)

    # The column's own left and right margins. Everything else about the
    # room a note has is asked of the widget, not held here - the scrollbar
    # takes 12 px when it shows and nothing when it does not, and a constant
    # for the narrow case cut every note 12 px short in the wide one, which
    # is the normal one at his 1600x1000 window.
    NOTE_MARGINS = 32

    # **This was a character count, and a character count cannot be right in
    # a proportional font.** 15 was picked by eye; 12 was then "measured"
    # offscreen, where Qt has no font database and `"W" * 12` and `"i" * 12`
    # measure the same - and that cut `1 stop - box lap 5` in half. Against
    # every strategy label on file, eliding by pixel is better than or equal
    # to the old count on all of them.
    #
    # It still elides: `nav_state` passes a strategy label through verbatim
    # and they run to 306 px against a 178 px rail. That is the rail's width,
    # not this function's - carried, not fixed here.
    def _note_room(self) -> int:
        """The pixels a note has, now.

        **Bounded by the rail's own fixed width.** `_update_rail` runs from
        `PitCrewWindow.__init__`, before `show()`, when the scroll area is
        unlaid and its viewport reports the default 640 - so this returned
        608, nothing elided, and the driver's first painted frame carried a
        307 px note hard-cut inside a 178 px rail with the horizontal bar
        off. A ceiling costs nothing and cannot be wrong before layout.
        """
        ceiling = self.width() - self.NOTE_MARGINS
        return min(self._scroller.viewport().width() - self.NOTE_MARGINS,
                   ceiling)

    def focus_item(self, index: int) -> None:
        """Move focus along the rail, wrapping. Skips what is not built."""
        usable = [i for i in range(len(self._labels))
                  if self._labels[i].isEnabled()]
        if not usable:
            return
        if index < 0:
            index = usable[-1]
        elif index >= len(self._labels):
            index = usable[0]
        while index not in usable:
            index = (index + 1) % len(self._labels)
        self._labels[index].setFocus(Qt.FocusReason.TabFocusReason)
        self._scroller.ensureWidgetVisible(self._labels[index])

    def set_note(self, index: int, text: str) -> None:
        """A one-line state under a rail item, or "" to clear it."""
        if not 0 <= index < len(self._notes):
            return
        # **The raw text is kept, because the room moves.** The scrollbar
        # takes 12 px when it appears, and dragging the window toward its own
        # 560 px minimum brings it in - so a note elided while the bar was
        # hidden kept its old width and had the last 12 px clipped by the
        # inner widget, with the horizontal bar off, until something happened
        # to set it again.
        self._note_text[index] = text
        self._elide_note(index)

    def _elide_note(self, index: int) -> None:
        note = self._notes[index]
        # `note.font()` carries the app-wide sheet's family, so these metrics
        # are the ones the label paints with - measured, not assumed.
        note.setText(QFontMetrics(note.font()).elidedText(
            self._note_text[index], Qt.TextElideMode.ElideRight,
            self._note_room()))
        note.setVisible(bool(self._note_text[index]))

    def resizeEvent(self, event) -> None:            # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._elide_notes()

    def eventFilter(self, watched, event):           # noqa: N802 - Qt naming
        """Re-elide when the VIEWPORT changes, which the rail never does.

        The rail is `setFixedWidth(178)` and its height belongs to the
        window, so `resizeEvent` does not fire when the vertical scrollbar
        appears - and the bar is what takes the 12 px, part-way through
        `_update_rail`'s own loop over the screens. Measured at 1600x501,
        his smallest display: two notes were left with the width they had
        before the bar came in, clipped with the horizontal bar off.
        """
        if watched is self._scroller.viewport() and \
                event.type() == QEvent.Type.Resize:
            self._elide_notes()
        return super().eventFilter(watched, event)

    def _elide_notes(self) -> None:
        for index in range(len(self._notes)):
            self._elide_note(index)

    def select(self, index: int) -> None:
        if index >= self._stack.count():
            return
        # **Built before it is shown, never after.** Switching to a
        # placeholder first would put an empty frame on screen for however
        # long the real screen takes to construct, which on the slowest of
        # them is a third of a second of blank panel.
        if self._builder is not None:
            self._builder(index)
        self._stack.setCurrentIndex(index)
        if 0 <= index < len(self._labels):
            self._scroller.ensureWidgetVisible(self._labels[index])
        for position, label in enumerate(self._labels):
            if position >= self._stack.count():
                label.setStyleSheet(
                    f"color: {theme.TREAD_LIGHT}; background: transparent;")
                continue
            active = position == index
            label.setStyleSheet(
                f"color: {theme.STENCIL if active else theme.STENCIL_DIM};"
                f"background: transparent;")


def fit_to_screen(widget, width: int, height: int) -> tuple[int, int]:
    """The requested size, clipped to what the screen will actually show.

    The app asked for 1600x1000 unconditionally. One of this driver's three
    displays is a 1280x800 desktop at 150% scaling with a 752 px working area
    once the taskbar is taken out, so the window was 320 px wider and 248 px
    taller than the screen it opened on. Everything past the edge was simply
    gone -- which is the whole of "the formatting is corrupt, and it is off
    horizontally on every screen".

    Clamped against `availableGeometry`, which is the work area rather than
    the panel, so the taskbar is already accounted for.
    """
    screen = widget.screen() if hasattr(widget, "screen") else None
    if screen is None:
        return width, height
    available = screen.availableGeometry()
    # A little room for the frame, which `availableGeometry` does not know
    # about: a window sized to the exact work area opens with its title bar
    # off the top on Windows.
    # **`availableGeometry` is in logical pixels, and so is everything Qt
    # sizes.** The first version of this reasoned in physical ones - "752 px of
    # working area" - and at 150% scaling that display reports 853x501
    # logical, not 1280x752. Clamping to a floor of 900x560 then produced a
    # window 47 px wider and 59 px taller than the whole work area, with
    # `setMinimumSize` making it unresizable: the exact defect this function
    # was written to fix, reintroduced by the fix.
    #
    # So the floor gives way to the screen. A window that does not fit is
    # worse than a cramped one, and the panes scroll.
    return (min(width, max(320, available.width() - 20)),
            min(height, max(320, available.height() - 60)))


class _FirstPaint(QObject):
    """Waits for a window's first paint, then runs one callable, once.

    **Also the launch's first honest "the window is on the screen" line.**
    `first idle after show` was the proxy the 5 Sep investigation settled
    for, and it turned out to run BEFORE the paint: every zero-timer queued
    at launch is dispatched ahead of the window's first frame.
    """

    def __init__(self, window: QWidget, then) -> None:
        super().__init__(window)
        self._window = window
        self._then = then
        self._done = False
        window.installEventFilter(self)
        QTimer.singleShot(FIRST_PAINT_BACKSTOP_MS,
                          lambda: self._fire(painted=False))

    def eventFilter(self, watched, event):           # noqa: N802 - Qt naming
        if watched is self._window and event.type() == QEvent.Type.Paint:
            # Queued, so it runs after this paint has finished, not inside it.
            QTimer.singleShot(0, lambda: self._fire(painted=True))
        return False

    def _fire(self, *, painted: bool) -> None:
        if self._done:
            return
        self._done = True
        self._window.removeEventFilter(self)
        diagnostics.mark("first paint" if painted
                         else "no paint yet - warming anyway")
        self._then()


class PitCrewWindow(QMainWindow):
    def __init__(self, store: Store, *, port: int = DEFAULT_PORT,
                 warm=None, voice_engine=None) -> None:
        super().__init__()
        # The launch's speech warm-up, held back until `release_speech`.
        self._warm = warm
        self.setWindowTitle("Next Gear Racing Pit Crew")
        # The floor is the *smaller* of what the layout wants and what the
        # screen can show. Pinning it above the work area makes the window
        # unresizable and puts its own controls off the edge.
        fitted = fit_to_screen(self, *WINDOW)
        self.setMinimumSize(min(MIN_WINDOW[0], fitted[0]),
                            min(MIN_WINDOW[1], fitted[1]))
        self.resize(*fitted)
        if ICON.exists():
            self.setWindowIcon(QIcon(str(ICON)))

        # **Parent first, then fill** (19 Sep 2026). Under the app-wide style
        # sheet, moving a finished subtree under a new parent re-polishes
        # every widget in it that carries its own sheet - which is every
        # label. Built bottom-up, the whole window was polished again by
        # `addWidget` into the stack, again by the stack into the row, and
        # again by `setCentralWidget`: 60-80 ms of the launch, spent redoing
        # work already done. So the shell is the central widget before
        # anything is in it, and each screen is made with the stack as its
        # parent. The rail is inserted in front of the stack once it can be
        # built, which leaves the row's order exactly as it was.
        shell = QWidget()
        row = QHBoxLayout(shell)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.setCentralWidget(shell)

        self.stack = QStackedWidget(shell)
        row.addWidget(self.stack, 1)
        # **Three of the seven are not built here.** Car, Reference and
        # Settings are made in the idle turns straight after the window is
        # shown (`warm_screens`), or on the first visit if that comes sooner.
        # Event and Practice are unconditional in the controller; Strategy
        # and Race are 16 and 8 ms and are wanted on race day, so all four
        # stay eager and none of that is worth the deferral.
        #
        # **Car was eager until 19 Sep 2026, and the reason no longer holds.**
        # Its ~300 ms (210 widgets) hid inside the window's wait for the
        # speech warm-up, so deferring it saved nothing. That wait is gone -
        # see `PushToTalk._take_arrival` - and Car's build is now straight on
        # the path to the window. It is the first screen `warm_screens`
        # builds, so it is ready long before anyone can click it.
        self.event_screen = EventScreen(parent=self.stack)
        self.car_screen = None
        self.practice_screen = PracticeScreen(parent=self.stack)
        self.strategy_screen = StrategyScreen(parent=self.stack)
        self.race_screen = RaceScreen(parent=self.stack)
        self.reference_screen = None
        self.settings_screen = None
        # Order must match SCREENS, which NAV_GROUPS defines: the rail
        # indexes straight into the stack.
        #
        # **The placeholders are load-bearing.** `NavRail` disables an item
        # when its index is past `stack.count()` and labels it "Not built
        # yet". A screen that is merely waiting to be built is not that, and
        # must not read as that - so the stack is seven wide from the start.
        for screen in (self.event_screen, self.car_screen,
                       self.practice_screen,
                       self.strategy_screen, self.race_screen,
                       self.reference_screen, self.settings_screen):
            self.stack.addWidget(screen if screen is not None
                                 else QWidget(self.stack))

        self.rail = NavRail(self.stack, NAV_GROUPS,
                            builder=self._ensure_screen)
        row.insertWidget(0, self.rail)

        self.controller = PitCrewController(
            store, self.event_screen, self.practice_screen,
            self.strategy_screen, self.race_screen,
            car_screen=None, settings_screen=None,
            port=port, warm=warm, voice_engine=voice_engine,
            defer_strip=True)
        # The rail says where the work stands, not only where it goes. Every
        # figure here is already in the store; nothing new is computed for it.
        self.controller.nav_state_changed.connect(self._update_rail)
        self._update_rail(self.controller.nav_state())
        self._install_shortcuts()

    # Index in the stack -> (attribute, class, how to wire it up). The rail
    # indexes straight into the stack, so these are positions in SCREENS.
    LATE_SCREENS = {
        1: ("car_screen", CarScreen, "attach_car_screen"),
        5: ("reference_screen", ReferenceScreen, None),
        6: ("settings_screen", SettingsScreen, "attach_settings_screen"),
    }

    def _ensure_screen(self, index: int):
        """Build a deferred screen, or return the one already there.

        **Idempotent by construction**, not by a flag someone has to
        remember to check: a second call finds a real screen in the stack and
        returns it. A doubled `attach` would connect every signal twice, for
        the life of the process, with nothing to see until one Save wrote two
        records.
        """
        late = self.LATE_SCREENS.get(index)
        if late is None:
            return self.stack.widget(index)
        name, factory, attach = late
        existing = getattr(self, name)
        if existing is not None:
            return existing

        # The stack as its parent from the start - see `__init__`.
        screen = factory(parent=self.stack)
        # The attribute first, then the wiring, and only then the stack.
        # `_trigger_primary` reads these attributes, and the controller's
        # attach can push state into the screen - both must find a screen
        # that is fully itself before anything can show it.
        setattr(self, name, screen)
        if attach is not None:
            getattr(self.controller, attach)(screen)
        placeholder = self.stack.widget(index)
        self.stack.insertWidget(index, screen)
        if placeholder is not None:
            self.stack.removeWidget(placeholder)
            placeholder.deleteLater()
        # The rail's notes come from the store, so they were never wrong -
        # but the newly attached screen may have just changed what they say.
        self._update_rail(self.controller.nav_state())
        return screen

    def warm_screens(self) -> None:
        """Build the deferred screens in the background, one per event-loop
        turn, so the first visit to one is not the first time it is made.

        One per turn rather than all at once: the window stays answerable
        between them. Every index is attempted exactly once - **a chain that
        re-armed on the index it just failed would spin a core for the rest
        of the race with nothing in the log**, which is a worse fault than
        the 90 ms of building it was trying to hide.
        """
        pending = [i for i in sorted(self.LATE_SCREENS)
                   if getattr(self, self.LATE_SCREENS[i][0]) is None]
        if not pending:
            self.finish_launch()
            return
        index = pending[0]
        try:
            self._ensure_screen(index)
        except Exception:                         # noqa: BLE001
            # Named, and with a traceback: under pythonw this is the only
            # trace a screen that cannot be built will ever leave. The rail
            # will try again if he navigates there, and fail visibly.
            diagnostics.log().error(
                "could not warm the %s screen in the background",
                self.LATE_SCREENS[index][0], exc_info=True)
            setattr(self, self.LATE_SCREENS[index][0], None)
            # The chain ends here, and what waits on its end must not.
            self.finish_launch()
            return
        QTimer.singleShot(0, self.warm_screens)

    def after_first_paint(self, then) -> None:
        """Run `then` on the turn after this window first draws.

        With a backstop: a window that never paints - minimised at launch,
        or no display at all - still gets `then` after
        `FIRST_PAINT_BACKSTOP_MS`. Exactly once either way.
        """
        _FirstPaint(self, then)

    def after_launch_paint(self) -> None:
        """The launch's first frame is up: start the speech load, then warm
        the deferred screens.

        **The speech load first, measured 19 Sep 2026** - 6 interleaved
        launch pairs, timed from outside the process, against starting it at
        the end of `warm_screens`: speech ready 146-233 ms sooner on a quiet
        machine (median 358 over all six, every pair the same sign), and the
        window settled no later (-13, -9, +14 ms on the quiet pairs; the
        longest stall 59-62 -> 66-72 ms, still under 100). It was not so
        while each moonshine session spun ONNX Runtime's fourteen-thread pool
        (see `ptt.MOONSHINE_SINGLE_THREAD`): then the loads beside the screens
        roughly doubled them. The loads run on their one warm-up thread, as
        always; nothing here waits for them.
        """
        self.release_speech()
        self.warm_screens()

    def finish_launch(self) -> None:
        """What the launch held back until the window was up: the phone
        strip's server, then the speech load. Both idempotent; called at
        either end of `warm_screens` and by the backstop in `main`."""
        try:
            self.controller.start_deferred_strip()
        except Exception:                         # noqa: BLE001
            # The strip is an output; it must not take speech with it.
            diagnostics.log().error("could not start the phone strip",
                                    exc_info=True)
        self.release_speech()

    def release_speech(self) -> None:
        """Start the speech warm-up the launch built but held back. Once.

        **Why it waits for the first frame** (19 Sep 2026): started before
        the window was up, the two ONNX loads and their imports competed with
        building it - Car 290 -> 410 ms, one calendar read 40 -> 1,260 ms.
        Started on the first frame (`after_launch_paint`), the window is
        already drawn and the deferred screens that follow are small.

        **It cannot be left unreleased.** Called from both ends of
        `warm_screens`, from a timer in `main` as a backstop, and - failing
        all of those - `PushToTalk` starts it itself on the first press or
        the first session (see `_take_arrival`). Idempotent: the second and
        later calls do nothing.
        """
        if self._warm is not None and ptt.begin_warm_up(self._warm):
            diagnostics.mark("speech warm-up started")

    def _update_rail(self, state: dict) -> None:
        for index, name in enumerate(SCREENS):
            self.rail.set_note(index, state.get(name, ""))

    def _install_shortcuts(self) -> None:
        """Keys for the things done every session.

        There were none at all - not to a screen, not to Save, Export or
        Generate. The one user does this weekly and knows exactly where he is
        going; making him aim at a label eight times a session is the app
        working at beginner speed forever.
        """
        for index in range(len(SCREENS)):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self)
            shortcut.activated.connect(
                lambda i=index: self.rail.select(i))

        # The primary action of whichever screen is showing. One key rather
        # than one per screen: the gesture is "do the thing this screen is
        # for", and which thing that is depends on where you are.
        primary = QShortcut(QKeySequence("Ctrl+Return"), self)
        primary.activated.connect(self._trigger_primary)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(
            self._trigger_primary)

    def _trigger_primary(self) -> None:
        current = self.stack.currentWidget()
        for action in ("_on_save", "_on_export", "_on_generate"):
            handler = getattr(current, action, None)
            if callable(handler):
                handler()
                return
        # Screens whose primary action lives on the controller rather than on
        # the screen itself.
        if current is self.practice_screen:
            self.practice_screen.export_requested.emit()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.controller.shutdown()
        super().closeEvent(event)


def main() -> int:
    # First, before anything can fail. The shortcut launches this through
    # pythonw, which has no console: without a log file a crash leaves nothing
    # at all behind, which is exactly what happened the first time it died.
    log_path = diagnostics.install()
    diagnostics.install_qt_handler()
    # **The pid, because every wedge investigation so far has begun by hunting
    # it by hand.** When a copy of this app has to be diagnosed after the
    # fact, the first question is always which process it was.
    diagnostics.banner(pid=os.getpid(), version=APP_VERSION,
                       database=DEFAULT_DB_PATH, log=log_path)

    diagnostics.mark("logging up")
    # The real launch made the QApplication before the imports - see
    # `pitcrew.boot`. Anything else, including a boot that failed, makes it
    # here as it always did.
    from pitcrew import boot

    app = QApplication.instance()
    early = app is not None and app is boot.APP
    if app is None:
        _claim_taskbar_identity()
        app = QApplication(sys.argv)
    diagnostics.mark("QApplication")
    # **Before the store, the controller, or any device.** Checked after
    # QApplication exists so the refusal can be shown rather than only
    # logged - the shortcut runs this through pythonw, which has no console,
    # so a bare exit here would look exactly like the app failing to start.
    claim = _claim_sole_instance()
    if claim.message:
        # Said either way. A copy that starts alongside a wedged one is in a
        # degraded state the driver has to know about mid-race, and a copy
        # that refuses has to say what to do instead.
        diagnostics.log().error(claim.message)
    if not claim.allowed:
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(None, "Pit Crew is already running", claim.message)
        font_warm.stop_all()
        return 0
    if ICON.exists():
        app.setWindowIcon(QIcon(str(ICON)))
    if not early:
        theme.apply(app)
    diagnostics.mark("theme")

    try:
        # **The speech engine is chosen beside the screens, not after them.**
        # Here rather than any earlier: after the sole-instance claim, so a
        # copy about to be refused imports nothing, after `QApplication`,
        # which sets up the Qt thread's COM apartment before this thread's
        # `pythoncom` import sets up its own, and inside the `try`, so the
        # rig claim is given back whatever happens. See
        # `voice.start_engine_build`.
        voice_engine = voice.start_engine_build()
        store = Store(DEFAULT_DB_PATH)
        diagnostics.mark("store open")
        # **Built here, started after the window has drawn, joined by
        # nobody.** The two speech models are 250 MB of ONNX and 2.3-3.1 s
        # to build. The controller used to join them before the window could
        # exist; now `PushToTalk` installs them at the first press after they
        # land (`PushToTalk._take_arrival`), and `release_speech` starts the
        # load on the first frame (`after_launch_paint`). Measured 19 Sep
        # 2026: first paint 3.4 s -> 0.8 s.
        #
        # After the sole-instance claim, deliberately: a second copy that is
        # about to be refused must not first load a quarter of a gigabyte.
        warm = ptt.start_warm_up(settings.load(store).speech_backend,
                                 start=False)
        window = PitCrewWindow(store, warm=warm, voice_engine=voice_engine)
        diagnostics.mark("window built")
        window.show()
        diagnostics.mark("window shown")
        # After `show`, so none of this is between the launch and the window.
        # It only removes the pause on the first visit to a deferred screen;
        # it saves nothing, and it must not be moved above this line.
        # **The one the driver actually experiences.** `show()` returns
        # before anything is painted; the first idle turn of the event loop
        # is the closest honest proxy for "there is a window on the screen",
        # and it is what the 5 Sep investigation could not measure at all.
        QTimer.singleShot(0, lambda: diagnostics.mark("first idle after show"))
        # **After the first frame, not in the first turn** (19 Sep 2026).
        # Zero-timers queued here run before Windows delivers the window's
        # first paint, so a Car screen warmed "in the background" was 350 ms
        # of blank window in front of the driver. `after_first_paint` holds
        # the chain until the window has actually drawn.
        window.after_first_paint(window.after_launch_paint)
        # The backstop for `finish_launch` - the strip, then the speech load.
        # The chain above calls it within half a second; this is for a chain
        # that somehow never ran.
        QTimer.singleShot(SPEECH_BACKSTOP_MS, window.finish_launch)
        if claim.message:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(None, "The previous Pit Crew is stuck",
                                claim.message)
        code = app.exec()
    finally:
        # **The whole fix, and it belongs in a `finally`.** The old code let
        # the process's death release the name, and the process cannot always
        # die - see `_INSTANCE_MUTEX`. Every exit path this app has actually
        # taken runs through here, including all three wedges.
        _release_sole_instance()
        # No font warm-up may outlive the application object: Qt aborts
        # the process if a running QThread is destroyed.
        font_warm.stop_all()
    diagnostics.log().info("Pit Crew exited with %s", code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
