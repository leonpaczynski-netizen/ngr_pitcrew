"""Run the screens with sample data, and capture them.

    python -m pitcrew.ui.preview              # interactive
    python -m pitcrew.ui.preview --shot out/  # write PNGs and exit

Writes `event.png`, `practice.png` and `driver-board.png`.

Sample laps are synthetic and labelled as such; they exist so the screens can
be inspected without a PS5 attached. **The driver board's sample is not
synthetic in the same sense** - every figure on it is a measurement off the
archive, named where it is defined below, because a board picture made of
invented numbers cannot show whether the board reads well.
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

from pitcrew.app import fit_to_screen
from pitcrew.ui import theme
from pitcrew.ui.driver_view import BoardCall, DriverState, DriverView, GapView
from pitcrew.ui.event_screen import EventScreen
from pitcrew.ui.practice_screen import LapRow, PracticeScreen
from pitcrew.ui.widgets import StencilLabel

WINDOW = (1600, 1000)

# **The driver board as it looks eight laps into a race**, for the row-1.8
# screenshot. Every figure is taken from something on file rather than
# invented, so this is a picture of a state that has happened:
#
# * the tyres are Daytona session 118 at lap 8 - rear-front +12.15 degC,
#   RR-RL +2.50, corner medians FL 62.5 / FR 65.6 / RL 73.2 / RR 75.7;
# * the fuel is the 20-lap Daytona race at the burn its plan was built on;
# * the gaps and the last call are the Deep Forest reconstruction that
#   `test_undercut_deep_forest.py` is written against.
#
# `fuel_to_flag` is deliberately the SMALL positive it should be when a fill
# is sized correctly - it is the plan's own margin - because the thing worth
# seeing in a screenshot is that the two fuel numbers do not read as two
# copies of one.
SAMPLE_BOARD = DriverState(
    temps_c={"fl": 62.5, "fr": 65.6, "rl": 73.2, "rr": 75.7},
    compound="RS",
    axle_split_c=12.15, axle_split_rate=1.42,
    rear_pair_hotter="rr", rear_pair_split_c=2.50, rear_pair_rate=None,
    split_laps=8,
    laps_to_box=3, box_on_lap=11, tyres_at_stop=True, has_plan=True,
    laps_of_fuel=9.1, fuel_l=38.1, burn_l=4.19,
    fuel_to_stop=6.1, fuel_to_flag=0.4,
    position=3, field_size=12,
    ahead=GapView(seconds=1.2, note="catching 0.4 s a lap - Boxhead",
                  good=True),
    behind=GapView(seconds=4.8, note="he is catching 0.6 s a lap - Rocky",
                   urgent=True),
    last_call=BoardCall(
        text="Faster than Boxhead through 1 and 2. He has you in 3.",
        mark="instruction", lap=9),
)

SAMPLE_LAPS = [
    LapRow(1, 1, 140_318, 2.10, is_out_lap=True),
    LapRow(2, 2, 94_102, 3.41, compound="RM"),
    LapRow(3, 3, 93_912, 3.38, compound="RM"),
    LapRow(4, 4, 96_740, 3.52, compound="RM", excluded=True,
           exclusion_reason="traffic"),
    LapRow(5, 5, 94_480, 3.44, compound="RM"),
    LapRow(6, 6, 94_907, 3.40, compound="RM", wear_fl=0.48, wear_fr=0.42,
           wear_rl=0.36, wear_rr=0.35),
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
        if not 0 <= index < self._stack.count():
            # **A rail item with no screen behind it is a silent no-op**, and
            # for a long time two of the four were. The guard stays because a
            # rail longer than its stack is a mistake worth surviving, but
            # every name the rail carries now has a screen: adding one
            # without the other is how the board went two months with no
            # harness at all.
            return
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
        # Clamped, like the real shell. A harness that opens bigger than the
        # screen cannot show you what the screen will look like.
        self.resize(*fit_to_screen(self, *WINDOW))

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

        self.rail = NavRail(self.stack, ["Event", "Practice"])
        row.addWidget(self.rail)
        row.addWidget(self.stack, 1)
        self.setCentralWidget(shell)


BOARD_WINDOW = (2160, 1040)


def build_driver_board() -> DriverView:
    """The driver board on its own, at a size it fits in.

    **The one screen that could not be looked at away from a race.** It lives
    in a frameless always-on-top window the controller opens on the grid, so
    before this the only way to see a change to it was to start one - and row
    1.8 asks for a screenshot.

    **Not inside the preview's shell**, and not for tidiness: the board's own
    layout minimum is about 1920x1010 at the type sizes the ranks are built
    from, which is wider than the shell's whole client area. Putting it in
    the stack would either clip it or silently drag the shell to a size no
    other screen is designed for, and a harness that shows you a distorted
    screen is worse than one that shows you none.

    `DriverView` rather than `DriverWindow`: the window's job is to be
    frameless, stay on top and never take focus, and none of that survives
    being screenshotted anyway.
    """
    board = DriverView()
    board.resize(*fit_to_screen(board, *BOARD_WINDOW))
    board.update_state(SAMPLE_BOARD)
    return board


def _capture(window: PreviewWindow, board: DriverView, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for index, name in ((0, "event"), (1, "practice")):
        window.rail.select(index)
        QApplication.processEvents()
        window.grab().save(str(out / f"{name}.png"))
        print(f"wrote {out / f'{name}.png'}")
    QApplication.processEvents()
    board.grab().save(str(out / "driver-board.png"))
    print(f"wrote {out / 'driver-board.png'}")


def main() -> int:
    app = QApplication(sys.argv)
    theme.apply(app)

    window = PreviewWindow()
    window.show()
    board = build_driver_board()
    board.show()

    shot_index = sys.argv.index("--shot") if "--shot" in sys.argv else -1
    if shot_index >= 0:
        out = Path(sys.argv[shot_index + 1])
        QTimer.singleShot(400,
                          lambda: (_capture(window, board, out), app.quit()))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
