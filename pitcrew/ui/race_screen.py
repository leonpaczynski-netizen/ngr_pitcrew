"""Race — the pit wall.

The driver is in a headset and cannot see this while he is driving, so nothing
here is a live instrument. It is for the moment before the start, the glance
between stints, and the read afterwards. The engineer's job during the race is
done out loud.

So the screen shows two things: the last thing said, large enough to read from
the seat with the headset pushed up, and the log of everything said with its
reason and confidence. The log is the point — a call the driver acted on and a
call he ignored are both evidence about the model, and the export carries them.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pitcrew.race.calls import HIGH, LOW, MEDIUM
from pitcrew.ui import theme
from pitcrew.ui.widgets import (
    BodyLabel,
    Declared,
    MarkButton,
    Measured,
    Plate,
    SpecLine,
    StencilLabel,
)

CONFIDENCE_INK = {
    HIGH: theme.STENCIL,
    MEDIUM: theme.CHALK,
    LOW: theme.WARNING,
}


class CallRow(QWidget):
    """One thing the engineer said."""

    def __init__(self, call, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 6, 0, 6)
        row.setSpacing(theme.GAP)

        lap = Measured(f"{call.lap:>2}", colour=theme.STENCIL_DIM)
        lap.setFixedWidth(34)
        row.addWidget(lap)

        text = QVBoxLayout()
        text.setSpacing(0)
        instruction = BodyLabel(call.call, colour=theme.STENCIL, wrap=False)
        text.addWidget(instruction)
        if call.reason:
            text.addWidget(BodyLabel(call.reason, size=13,
                                     colour=theme.STENCIL_DIM, wrap=False))
        row.addLayout(text, 1)

        # Confidence is shown, not implied: a modelled call and a measured one
        # must not look the same after the race any more than during it.
        badge = StencilLabel(call.confidence, size=10, tracking=14.0,
                             colour=CONFIDENCE_INK.get(call.confidence,
                                                       theme.STRUCK))
        badge.setFixedWidth(70)
        badge.setAlignment(Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(badge)


class RaceScreen(QWidget):
    """Arm the race, then watch what the engineer said."""

    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._armed = False
        self._build()

    def _build(self) -> None:
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 24)
        page.setSpacing(theme.GAP_WIDE)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(StencilLabel("Race", size=theme.TITLE_PX,
                                      colour=theme.STENCIL, tracking=6.0))
        self.subtitle = BodyLabel("No plan armed.", colour=theme.STENCIL_DIM)
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)

        self.start_button = MarkButton("Start race", primary=True)
        self.start_button.clicked.connect(self._on_start)
        header.addWidget(self.start_button, 0, Qt.AlignmentFlag.AlignBottom)
        page.addLayout(header)

        self.spec = SpecLine()
        page.addWidget(self.spec)

        page.addWidget(self._radio_plate())
        page.addWidget(self._log_plate(), 1)

    def _radio_plate(self) -> Plate:
        """The last thing said, large. Read from the seat, headset up."""
        plate = Plate("On the radio")
        self.last_call = Measured("—", size=30, bold=True)
        self.last_call.setWordWrap(True)
        plate.body.addWidget(self.last_call)
        self.last_reason = BodyLabel("", colour=theme.STENCIL_DIM)
        plate.body.addWidget(self.last_reason)
        return plate

    def _log_plate(self) -> Plate:
        plate = Plate("Every call")
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.log = QWidget()
        self.log_layout = QVBoxLayout(self.log)
        self.log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_layout.setSpacing(0)
        self.log_layout.addStretch(1)
        scroller.setWidget(self.log)

        plate.body.addWidget(scroller, 1)
        return plate

    # ---------------------------------------------------------------- actions

    def _on_start(self) -> None:
        if self._armed:
            self.stop_requested.emit()
        else:
            self.start_requested.emit()

    def set_armed(self, armed: bool) -> None:  # noqa: N802 - Qt naming
        self._armed = armed
        self.start_button.setText("End race" if armed else "Start race")

    # ------------------------------------------------------------------ data

    def set_status(self, text: str, *, warn: bool = False) -> None:  # noqa: N802
        self.subtitle.setText(text)
        self.subtitle.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.STENCIL_DIM};"
            f"background: transparent;")

    def show_call(self, call) -> None:
        self.last_call.setText(call.call)
        self.last_call.setStyleSheet(
            f"color: {CONFIDENCE_INK.get(call.confidence, theme.STENCIL)};"
            f"background: transparent;")
        self.last_reason.setText(call.reason)
        self.log_layout.insertWidget(0, CallRow(call))

    def show_exchange(self, heard: str, said: str) -> None:
        """What the driver asked, and what came back."""
        row = QWidget()
        line = QHBoxLayout(row)
        line.setContentsMargins(0, 4, 0, 4)
        line.setSpacing(theme.GAP)
        tag = StencilLabel("radio", size=10, tracking=14.0,
                           colour=theme.CHALK)
        tag.setFixedWidth(34)
        line.addWidget(tag)
        text = QVBoxLayout()
        text.setSpacing(0)
        if heard:
            text.addWidget(BodyLabel(f'"{heard}"', size=13,
                                     colour=theme.STRUCK, wrap=False))
        text.addWidget(BodyLabel(said, colour=theme.CHALK, wrap=False))
        line.addLayout(text, 1)
        self.log_layout.insertWidget(0, row)

    def show_offer(self, verdict) -> None:
        """A re-plan on the table, until he accepts or keeps."""
        self.last_call.setText(verdict.call())
        self.last_call.setStyleSheet(
            f"color: {theme.WARNING}; background: transparent;")
        self.last_reason.setText(f"{verdict.reason}. Say accept, or keep.")

    def clear_log(self) -> None:
        while self.log_layout.count():
            item = self.log_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.log_layout.addStretch(1)
        self.last_call.setText("—")
        self.last_reason.setText("")

    def show_snapshot(self, snapshot: dict) -> None:
        self.spec.clear()
        lap = snapshot.get("lap") or 0
        total = snapshot.get("lapsTotal")
        self.spec.add("Lap", f"{lap}/{total}" if total else str(lap),
                      emphasis=True)
        if snapshot.get("position"):
            self.spec.add("Position", f"P{snapshot['position']}")
        fuel = snapshot.get("lapsOfFuel")
        if fuel is not None:
            self.spec.add("Fuel", f"{fuel:.1f} laps")
        to_stop = snapshot.get("lapsToStop")
        if to_stop is not None:
            self.spec.add("Box in", f"{max(0, to_stop)}", declared=True)
        if snapshot.get("nextCompound"):
            self.spec.add("Then", snapshot["nextCompound"])
        self.spec.finish()
