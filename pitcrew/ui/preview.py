"""Run the screens with sample data, and capture them.

    python -m pitcrew.ui.preview              # interactive
    python -m pitcrew.ui.preview --shot out/  # write PNGs and exit

Sample laps are synthetic and labelled as such; they exist so the screens can
be inspected without a PS5 attached.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pitcrew.ui import theme
from pitcrew.ui.event_screen import EventScreen
from pitcrew.ui.practice_screen import LapRow, PracticeScreen
from pitcrew.ui.widgets import StencilLabel

WINDOW = (1600, 1000)

SAMPLE_LAPS = [
    LapRow(1, 1, 140_318, 2.10, is_out_lap=True),
    LapRow(2, 2, 94_102, 3.41, compound="RM"),
    LapRow(3, 3, 93_912, 3.38, compound="RM"),
    LapRow(4, 4, 96_740, 3.52, compound="RM", excluded=True,
           exclusion_reason="traffic"),
    LapRow(5, 5, 94_480, 3.44, compound="RM"),
    LapRow(6, 6, 94_907, 3.40, compound="RM", wear_front=0.42, wear_rear=0.35),
    LapRow(7, 7, 121_664, 3.10, is_pit_lap=True),
    LapRow(8, 8, 138_902, 2.05, is_out_lap=True),
    LapRow(9, 9, 93_780, 3.36, compound="RS"),
    LapRow(10, 10, 93_690, 3.39, compound="RS"),
    LapRow(11, 11, 94_015, 3.42),
]


class NavRail(QWidget):
    """Screen selection, lettered like a rack tag."""

    def __init__(self, stack: QStackedWidget, names: list[str],
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(178)
        self.setStyleSheet(f"background: {theme.RUBBER_DEEP};")
        self._stack = stack
        self._labels: list[StencilLabel] = []

        column = QVBoxLayout(self)
        column.setContentsMargins(20, 26, 12, 20)
        column.setSpacing(4)

        mark = StencilLabel("Pit Crew", size=16, colour=theme.CRAYON,
                            tracking=14.0)
        column.addWidget(mark)
        column.addSpacing(28)

        for index, name in enumerate(names):
            label = StencilLabel(name, size=13, tracking=14.0)
            label.setCursor(Qt.CursorShape.PointingHandCursor)
            label.setContentsMargins(0, 8, 0, 8)
            label.mousePressEvent = lambda _e, i=index: self.select(i)  # noqa: E731
            column.addWidget(label)
            self._labels.append(label)

        column.addStretch(1)
        note = StencilLabel("Synthetic data", size=10, colour=theme.STENCIL_DIM,
                            tracking=10.0)
        column.addWidget(note)
        self.select(0)

    def select(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for position, label in enumerate(self._labels):
            active = position == index
            label.setStyleSheet(
                f"color: {theme.STENCIL if active else theme.STENCIL_DIM};"
                f"background: transparent;")


class PreviewWindow(QMainWindow):
    def __init__(self) -> None:
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
        self.practice_screen.set_laps(SAMPLE_LAPS)
        self.stack.addWidget(self.event_screen)
        self.stack.addWidget(self.practice_screen)

        self.rail = NavRail(self.stack, ["Event", "Practice", "Strategy", "Race"])
        row.addWidget(self.rail)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(shell)


def _capture(window: PreviewWindow, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for index, name in ((0, "event"), (1, "practice")):
        window.rail.select(index)
        QApplication.processEvents()
        window.grab().save(str(out / f"{name}.png"))
        print(f"wrote {out / f'{name}.png'}")


def main() -> int:
    app = QApplication(sys.argv)
    theme.apply(app)

    window = PreviewWindow()
    window.show()

    shot_index = sys.argv.index("--shot") if "--shot" in sys.argv else -1
    if shot_index >= 0:
        out = Path(sys.argv[shot_index + 1])
        QTimer.singleShot(400, lambda: (_capture(window, out), app.quit()))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
