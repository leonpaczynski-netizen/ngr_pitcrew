"""Next Gear Racing Pit Crew.

    python -m pitcrew.app
"""
from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pitcrew.controller import DEFAULT_PORT, PitCrewController
from pitcrew.store.db import DEFAULT_DB_PATH, Store
from pitcrew.ui import theme
from pitcrew.ui.event_screen import EventScreen
from pitcrew.ui.practice_screen import PracticeScreen
from pitcrew.ui.strategy_screen import StrategyScreen
from pitcrew.ui.widgets import StencilLabel

WINDOW = (1600, 1000)
SCREENS = ("Event", "Practice", "Strategy", "Race")


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

        shell = QWidget()
        row = QHBoxLayout(shell)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        self.stack = QStackedWidget()
        self.event_screen = EventScreen()
        self.practice_screen = PracticeScreen()
        self.stack.addWidget(self.event_screen)
        self.strategy_screen = StrategyScreen()
        self.stack.addWidget(self.practice_screen)
        self.stack.addWidget(self.strategy_screen)

        self.rail = NavRail(self.stack, SCREENS)
        row.addWidget(self.rail)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(shell)

        self.controller = PitCrewController(
            store, self.event_screen, self.practice_screen,
            self.strategy_screen, port=port)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.controller.shutdown()
        super().closeEvent(event)


def main() -> int:
    app = QApplication(sys.argv)
    theme.apply(app)

    store = Store(DEFAULT_DB_PATH)
    window = PitCrewWindow(store)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
