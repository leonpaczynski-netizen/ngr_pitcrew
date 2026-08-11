"""Next Gear Racing Pit Crew.

    python -m pitcrew.app
"""
from __future__ import annotations

import sys

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
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
from pitcrew.ui.widgets import StencilLabel

WINDOW = (1600, 1000)
# Preparation, then the running of it, then what is done with what it produced.
# Settings last: it is set once and then left alone.
SCREENS = ("Event", "Car", "Practice", "Strategy", "Race", "Engineer",
           "Reference", "Settings")
ICON = Path(__file__).resolve().parent.parent / "pitcrew.ico"

# Windows groups taskbar buttons by this id. Without one, a Python GUI app is
# grouped under the interpreter, so a pinned shortcut and the running window
# appear as two separate buttons with two different icons.
APP_ID = "NextGearRacing.PitCrew"


def _claim_taskbar_identity() -> None:
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:                            # noqa: BLE001
        pass                                     # not Windows, or too old


class NavRail(QWidget):
    """Screen selection, lettered like a rack tag."""

    def __init__(self, stack: QStackedWidget, names,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(178)
        self.setStyleSheet(f"background: {theme.RUBBER_DEEP};")
        self._stack = stack
        self._labels: list[StencilLabel] = []

        column = QVBoxLayout(self)
        column.setContentsMargins(20, 26, 12, 20)
        column.setSpacing(4)
        column.addWidget(StencilLabel("Pit Crew", size=16, colour=theme.CRAYON,
                                      tracking=14.0))
        column.addSpacing(28)

        for index, name in enumerate(names):
            label = StencilLabel(name, size=13, tracking=14.0)
            built = index < stack.count()
            if built:
                label.setCursor(Qt.CursorShape.PointingHandCursor)
                label.mousePressEvent = lambda _e, i=index: self.select(i)  # noqa: E731
            else:
                label.setToolTip("Not built yet")
            label.setContentsMargins(0, 8, 0, 8)
            column.addWidget(label)
            self._labels.append(label)

        column.addStretch(1)
        self.select(0)

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
                f"color: {theme.STENCIL if active else theme.STRUCK};"
                f"background: transparent;")


class PitCrewWindow(QMainWindow):
    def __init__(self, store: Store, *, port: int = DEFAULT_PORT) -> None:
        super().__init__()
        self.setWindowTitle("Next Gear Racing Pit Crew")
        self.resize(*WINDOW)
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
        # Order matches SCREENS: the rail indexes into the stack.
        for screen in (self.event_screen, self.car_screen,
                       self.practice_screen, self.strategy_screen,
                       self.race_screen, self.engineer_screen,
                       self.reference_screen, self.settings_screen):
            self.stack.addWidget(screen)

        self.rail = NavRail(self.stack, SCREENS)
        row.addWidget(self.rail)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(shell)

        self.controller = PitCrewController(
            store, self.event_screen, self.practice_screen,
            self.strategy_screen, self.race_screen,
            car_screen=self.car_screen,
            engineer_screen=self.engineer_screen,
            settings_screen=self.settings_screen, port=port)

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
