"""Run the screens with sample data, and capture them.

    python -m pitcrew.ui.preview              # interactive
    python -m pitcrew.ui.preview --shot out/  # write PNGs and exit

Writes `event.png`, `practice.png` and `driver-board.png`.

Sample laps are synthetic and labelled as such; they exist so the screens can
be inspected without a PS5 attached.

**The driver board's sample is COMPUTED rather than typed**, and that is not
tidiness. Its tyre splits and its two fuel figures are run through the real
`race/tyre_split.py` and `race/calls.py` off one `RaceState`, so the picture
cannot show a figure the code would not produce from the numbers beside it.
The first version was hand-written and did exactly that twice. What is still
chosen by hand - the two gaps, the last call's sentence - is chosen because
there is no expression behind it to disagree with.
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

# **Corner temperatures built from the SPLITS Daytona session 118 measured**,
# not from its per-corner medians, because those are two different aggregates
# and they do not agree: the medians (FL 62.5 / FR 65.6 / RL 73.2 / RR 75.7)
# make an axle gap of 10.40, while the measured lap-by-lap axle gap reached
# +12.65 by lap 10. The splits are what this block of the board is about, so
# they are what the sample is pinned to - rear-front from +2.90 on lap 1 to
# +12.15 on lap 8, RR-RL from +0.10 to +2.50, both off the 3 Sep measurement
# of that stint.
#
# ⚠️ **The measured axle trend is 1.32 degC/lap against a derived floor of
# 1.25**, so a real Daytona stint clears `RATE_WORTH_SAYING_C` by a hair and
# the rear pair's 0.34 does not clear it at all. That is worth knowing about
# the threshold, and it is why the screenshot shows a trend on one split and
# claims none on the other.
def _sample_temps() -> list[dict[str, float]]:
    laps = []
    for lap in range(8):
        front = 60.0 + 0.5 * lap
        rear = front + 2.90 + (12.15 - 2.90) / 7.0 * lap
        pair = 0.10 + (2.50 - 0.10) / 7.0 * lap
        laps.append({"fl": front - 1.55, "fr": front + 1.55,
                     "rl": rear - pair / 2.0, "rr": rear + pair / 2.0})
    return laps


SAMPLE_TEMPS = _sample_temps()


def sample_board() -> DriverState:
    """The board eight laps into a race, **computed, not typed**.

    The first version of this hand-wrote every figure, and two of them could
    not have come from the numbers beside them: the axle split was set to
    12.15 against four corner temperatures whose axle gap is 10.4, and the
    flag figure to a value the fuel expression does not produce from the rest
    of the state. A screenshot is the acceptance artefact for this row, and
    an artefact that disagrees with the code it is a picture of proves the
    opposite of what it was taken for.

    So the tyre splits are run through the real `SplitHistory` and the two
    fuel figures through the real `race/calls.py`, off one `RaceState`. The
    race is the 20-lap Daytona event: burn 4.19 L/lap, a 100 L tank, eight
    laps completed and the stop on app-lap 11 - which is HUD lap 12, and the
    board draws the HUD one, so "plan: lap 12" beside a countdown of 3 from a
    driver on HUD lap 9 is the two agreeing rather than disagreeing. The gaps and the
    last call are the Deep Forest reconstruction that
    `test_undercut_deep_forest.py` is written against - those two are
    presentation, and there is no expression behind them to disagree with.
    """
    from pitcrew.race.calls import (RaceState, fuel_in_hand_to_flag,
                                    fuel_in_hand_to_stop)
    from pitcrew.race.tyre_split import SplitHistory

    state = RaceState()
    state.laps_total = 20
    state.lap = 8
    state.fuel_l = 38.1
    state.fuel_per_lap_l = 4.19
    state.fuel_capacity_l = 100.0
    # **A measured lap-to-lap burn scatter, because without one the flag
    # figure is the plan's flat fallback lap** and the acceptance picture for
    # this row would be a picture of `FUEL_MARGIN_LAPS`. 0.15 L is the figure
    # the Deep Forest race measured; the margin is then sized on it rather
    # than on a whole lap.
    state.fuel_sd_l = 0.15
    state.stint_ends_on_lap = 11
    state.further_stop_planned = False
    state.mandatory_stops_left = 1

    splits = SplitHistory()
    for temps in SAMPLE_TEMPS:
        splits.note_lap(temps)
    axle_rate, laps = splits.axle_rate()
    to_stop, stop_why = fuel_in_hand_to_stop(state)
    to_flag, flag_why, flag_on = fuel_in_hand_to_flag(state)

    return DriverState(
        temps_c=SAMPLE_TEMPS[-1],
        compound="RS",
        axle_split_c=splits.axle_split_now(), axle_split_rate=axle_rate,
        rear_pair_hotter="rr", rear_pair_split_c=splits.split_now("rr"),
        rear_pair_rate=splits.rate("rr")[0], split_laps=laps,
        laps_to_box=float(state.laps_to_stop()),
        box_on_lap=state.lap_on_screen() + state.laps_to_stop(),
        # **The compound the plan says to FIT.** Without it the artefact
        # draws `plan: lap 12 · new set` and pictures none of what the last
        # two rounds were about - the board naming the set coming OFF.
        tyres_at_stop=True, next_compound="RS", has_plan=True,
        laps_of_fuel=state.laps_of_fuel(), burn_l=state.fuel_per_lap_l,
        fuel_to_stop=to_stop, fuel_to_stop_why=stop_why,
        fuel_to_flag=to_flag, fuel_to_flag_why=flag_why,
        fuel_to_flag_on=flag_on,
        position=3, field_size=12,
        ahead=GapView(seconds=1.2, note="catching 0.4 s a lap - Boxhead",
                      good=True),
        behind=GapView(seconds=4.8, note="he is catching 0.6 s a lap - Rocky",
                       urgent=True),
        last_call=BoardCall(
            text="Faster than Boxhead through 1 and 2. He has you in 3.",
            mark="instruction", lap=state.lap_on_screen()),
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


BOARD_WINDOW = (2480, 1050)


def build_driver_board() -> DriverView:
    """The driver board on its own, at a size it fits in.

    **The one screen that could not be looked at away from a race.** It lives
    in a frameless always-on-top window the controller opens on the grid, so
    before this the only way to see a change to it was to start one - and row
    1.8 asks for a screenshot.

    **Not inside the preview's shell**, and not for tidiness: the board's own
    layout minimum at these type sizes is wider than the shell's whole client
    area. Putting it in
    the stack would either clip it or silently drag the shell to a size no
    other screen is designed for, and a harness that shows you a distorted
    screen is worse than one that shows you none.

    `DriverView` rather than `DriverWindow`: the window's job is to be
    frameless, stay on top and never take focus, and none of that survives
    being screenshotted anyway.
    """
    board = DriverView()
    board.update_state(sample_board())
    # **Not clamped to this screen, and that is the difference between a
    # picture of the board and a picture of this laptop.** `fit_to_screen` is
    # right for the shell, which has to be usable wherever it opens; the board
    # is built for a 2560x1080 panel and its layout minimum is wider than the
    # machine these shots are taken on. Clamped, Qt could not honour the width,
    # the content overflowed downwards, and the artefact came out 1900x1128 -
    # taller than the monitor it is a picture of. `grab()` renders a widget
    # larger than the screen quite happily.
    # `minimumSizeHint`, which is what Qt enforces - the guard test moved
    # to it for the same reason, and the two really do differ.
    minimum = board.minimumSizeHint()
    board.resize(max(BOARD_WINDOW[0], minimum.width()),
                 max(BOARD_WINDOW[1], minimum.height()))
    return board


def _capture(window: PreviewWindow, board: DriverView, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for index, name in ((0, "event"), (1, "practice")):
        window.rail.select(index)
        QApplication.processEvents()
        window.grab().save(str(out / f"{name}.png"))
        print(f"wrote {out / f'{name}.png'}")
    # **Resized here, immediately before the grab.** The board is wider than
    # the machine these shots are taken on, so a window manager that has been
    # given it to show will have clamped and repositioned it - the artefact
    # came out 2480x1128 that way, taller than the panel it is a picture of.
    # `grab()` renders the widget at whatever size it is set to, screen or no
    # screen, so it is set to the panel's size at the last moment.
    board.resize(*BOARD_WINDOW)
    QApplication.processEvents()
    shot = board.grab()
    shot.save(str(out / "driver-board.png"))
    # **The size the grab actually came out at, not the one asked for.** They
    # differ whenever the layout minimum is above `BOARD_WINDOW` - `resize`
    # cannot go under it - and printing the request made the harness state a
    # figure it had not achieved, which is how a 1900x1128 artefact went out
    # once already.
    print(f"wrote {out / 'driver-board.png'} at "
          f"{shot.width()}x{shot.height()}")
    if shot.height() > 1080 or shot.width() > 2560:
        print("  ** WARNING: this does not fit the 2560x1080 panel it is a "
              "picture of **")


def main() -> int:
    app = QApplication(sys.argv)
    theme.apply(app)

    window = PreviewWindow()
    window.show()
    board = build_driver_board()
    shot_index = sys.argv.index("--shot") if "--shot" in sys.argv else -1
    if shot_index < 0:
        # Only for looking at. On a shot run the board is never handed to the
        # window manager at all - see `_capture`.
        board.show()

    if shot_index >= 0:
        out = Path(sys.argv[shot_index + 1])
        QTimer.singleShot(400,
                          lambda: (_capture(window, board, out), app.quit()))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
