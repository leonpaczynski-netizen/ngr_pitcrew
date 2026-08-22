"""Next Gear Racing Pit Crew.

    python -m pitcrew.app
"""
from __future__ import annotations

import os
import sys

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pitcrew import diagnostics
from pitcrew.controller import DEFAULT_PORT, PitCrewController
from pitcrew.export.payload import APP_VERSION
from pitcrew.store.db import DEFAULT_DB_PATH, Store
from pitcrew.ui import theme
from pitcrew.ui.car_screen import CarScreen
from pitcrew.ui.engineer_screen import EngineerScreen
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
# they read as eight peers; named, the rail describes the work.
#
# The order within each group is the order the work happens in - Engineer is
# the last step of the setup loop, not an eighth thing after Race.
NAV_GROUPS = (
    ("Prepare", ("Event", "Car")),
    ("Learn", ("Practice", "Engineer")),
    ("Race day", ("Strategy", "Race")),
    ("", ("Reference", "Settings")),
)
SCREENS = tuple(name for _heading, names in NAV_GROUPS for name in names)
ICON = Path(__file__).resolve().parent.parent / "pitcrew.ico"

# Windows groups taskbar buttons by this id. Without one, a Python GUI app is
# grouped under the interpreter, so a pinned shortcut and the running window
# appear as two separate buttons with two different icons.
APP_ID = "NextGearRacing.PitCrew"


# Held for the life of the process. A named mutex is released by Windows when
# the process ends, however it ends - including a kill - so it cannot be left
# stale by a crash the way a lock file can.
_INSTANCE_MUTEX = None


def _claim_sole_instance() -> str | None:
    """Refuse to start if another Pit Crew already owns the rig.

    **Two copies fighting over one rig is how a bad session became an
    unrecoverable one.** 22 Aug 2026: an instance was left running, a second
    was started, and between them they held COM5 against each other, rendered
    two haptic streams into the same endpoint until it degraded, and thrashed
    the recovery ladder until PortAudio was terminated over an open stream
    and took the process down. The wind, the transducer and the microphone
    are single-owner devices; nothing about this app is safe to run twice.

    Returns None when this process is the only one, or a sentence to show and
    log when it is not. Never raises - a machine where the mutex cannot be
    created is a machine that should still be able to race.

    `PITCREW_ALLOW_MULTIPLE=1` overrides, for a developer running a second
    copy against a different database on purpose.
    """
    global _INSTANCE_MUTEX
    if os.environ.get("PITCREW_ALLOW_MULTIPLE") == "1":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        ERROR_ALREADY_EXISTS = 183
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL,
                                          wintypes.LPCWSTR)
        # `Local\` scopes it to this login session, which is the right scope:
        # two desktops on one machine are two rigs.
        handle = kernel32.CreateMutexW(None, False, "Local\\" + APP_ID)
        if not handle:
            return None
        _INSTANCE_MUTEX = handle
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            return (
                "Pit Crew is already running. Two copies cannot share the "
                "rig - they hold the wind controller against each other and "
                "render two haptic streams into one transducer, which is "
                "what breaks it. Close the other window and start again. If "
                "there is no other window, a previous copy is stuck and the "
                "machine needs restarting.")
    except Exception:                            # noqa: BLE001
        return None                              # not Windows, or too old
    return None


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

    Eight equal peers in one list misrepresented the work. Two loops run
    through this app - prepare the car and learn from it (Event, Car,
    Practice, Engineer), and race it (Strategy, Race) - and the rail showed
    them as siblings of each other and of Reference and Settings, in an order
    that put Engineer, the last step of the first loop, after Race.

    Grouping rather than restructuring: the same eight screens, with the two
    loops named and ruled apart, so the rail describes the work instead of
    listing it.
    """

    def __init__(self, stack: QStackedWidget, groups,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(178)
        self.setStyleSheet(f"background: {theme.RUBBER_DEEP};")
        self._stack = stack
        self._labels: list[StencilLabel] = []
        self._notes: list[StencilLabel] = []

        column = QVBoxLayout(self)
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
                index += 1

        column.addStretch(1)
        self.select(0)

    # What fits on one line in the rail at this size, tracked. A note that
    # clips is worse than a shorter one: "NOTHING ASKED YE" reads as a bug.
    NOTE_CHARS = 15

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

    def set_note(self, index: int, text: str) -> None:
        """A one-line state under a rail item, or "" to clear it."""
        if not 0 <= index < len(self._notes):
            return
        if len(text) > self.NOTE_CHARS:
            text = text[:self.NOTE_CHARS - 1].rstrip() + "…"
        note = self._notes[index]
        note.setText(text)
        note.setVisible(bool(text))

    def select(self, index: int) -> None:
        if index >= self._stack.count():
            return
        self._stack.setCurrentIndex(index)
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


class PitCrewWindow(QMainWindow):
    def __init__(self, store: Store, *, port: int = DEFAULT_PORT) -> None:
        super().__init__()
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

        shell = QWidget()
        row = QHBoxLayout(shell)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self.stack = QStackedWidget()
        self.event_screen = EventScreen()
        self.car_screen = CarScreen()
        self.practice_screen = PracticeScreen()
        self.strategy_screen = StrategyScreen()
        self.race_screen = RaceScreen()
        self.engineer_screen = EngineerScreen()
        self.reference_screen = ReferenceScreen()
        self.settings_screen = SettingsScreen()
        # Order must match SCREENS, which NAV_GROUPS defines: the rail
        # indexes straight into the stack.
        for screen in (self.event_screen, self.car_screen,
                       self.practice_screen, self.engineer_screen,
                       self.strategy_screen, self.race_screen,
                       self.reference_screen, self.settings_screen):
            self.stack.addWidget(screen)

        self.rail = NavRail(self.stack, NAV_GROUPS)
        row.addWidget(self.rail)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(shell)

        self.controller = PitCrewController(
            store, self.event_screen, self.practice_screen,
            self.strategy_screen, self.race_screen,
            car_screen=self.car_screen,
            engineer_screen=self.engineer_screen,
            settings_screen=self.settings_screen, port=port)
        # The rail says where the work stands, not only where it goes. Every
        # figure here is already in the store; nothing new is computed for it.
        self.controller.nav_state_changed.connect(self._update_rail)
        self._update_rail(self.controller.nav_state())
        self._install_shortcuts()

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
        elif current is self.engineer_screen:
            self.engineer_screen.generate_requested.emit(
                self.engineer_screen.kind())

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.controller.shutdown()
        super().closeEvent(event)


def main() -> int:
    # First, before anything can fail. The shortcut launches this through
    # pythonw, which has no console: without a log file a crash leaves nothing
    # at all behind, which is exactly what happened the first time it died.
    log_path = diagnostics.install()
    diagnostics.install_qt_handler()
    diagnostics.banner(version=APP_VERSION, database=DEFAULT_DB_PATH,
                       log=log_path)

    _claim_taskbar_identity()
    app = QApplication(sys.argv)
    # **Before the store, the controller, or any device.** Checked after
    # QApplication exists so the refusal can be shown rather than only
    # logged - the shortcut runs this through pythonw, which has no console,
    # so a bare exit here would look exactly like the app failing to start.
    taken = _claim_sole_instance()
    if taken is not None:
        diagnostics.log().error(taken)
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.warning(None, "Pit Crew is already running", taken)
        return 0
    if ICON.exists():
        app.setWindowIcon(QIcon(str(ICON)))
    theme.apply(app)

    store = Store(DEFAULT_DB_PATH)
    window = PitCrewWindow(store)
    window.show()
    code = app.exec()
    diagnostics.log().info("Pit Crew exited with %s", code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
