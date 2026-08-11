"""Practice — the rack.

He is in a headset while driving and cannot see this screen at all, so nothing
here is designed to be read at speed. This is the surface he comes back to
between stints: mark up what was just run, strike out what does not count,
enter what the gauge said, and send it to the tune builder.

One row per lap. The compound band runs the full height of the row down its
left edge, so tagging a session paints the rack and the stint structure becomes
visible without reading a number. Measured values are stencil white; everything
the driver marks is crayon; an excluded lap is struck through and its band
loses its voice while keeping its identity.
"""
from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pitcrew.store.tyres import ALL_COMPOUNDS
from pitcrew.ui import theme
from pitcrew.ui.widgets import (
    BodyLabel,
    CompoundBand,
    Declared,
    MarkButton,
    Measured,
    Plate,
    SpecLine,
    StencilLabel,
    StrikeRow,
)

ROW_HEIGHT = 54
UNTAGGED = "—"

# Column widths, shared by the heads and the rows so the two never drift.
W_LAP = 34
W_TIME = 132
W_DELTA = 78
W_FUEL = 76
W_MARKER = 84
W_COMPOUND = 104
W_WEAR = 78
W_ACTION = 104
# Everything from the compound picker rightward, so the strike can stop before
# it: four controls, three gaps between them, and the row's right margin.
CONTROLS_WIDTH = (W_COMPOUND + W_WEAR * 2 + W_ACTION
                  + theme.GAP * 3 + 16)


@dataclass
class LapRow:
    """What the rack shows for one lap."""
    lap_id: int
    lap_num: int
    lap_time_ms: int
    fuel_used: float
    compound: str | None = None
    is_out_lap: bool = False
    is_pit_lap: bool = False
    excluded: bool = False
    exclusion_reason: str | None = None
    wear_front: float | None = None
    wear_rear: float | None = None

    @property
    def counted(self) -> bool:
        return not (self.excluded or self.is_out_lap or self.is_pit_lap)

    def structural_reason(self) -> str | None:
        if self.is_out_lap:
            return "out-lap"
        if self.is_pit_lap:
            return "in-lap"
        return None


def format_lap_time(ms: int) -> str:
    if ms <= 0:
        return "--:--.---"
    minutes, remainder = divmod(ms, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def format_delta(ms: int) -> str:
    if ms == 0:
        return "—"
    return f"{'+' if ms > 0 else '−'}{abs(ms) / 1000:.3f}"


class RackRow(QWidget):
    """One lap in the rack."""

    changed = pyqtSignal(int)

    def __init__(self, row: LapRow, best_ms: int,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.row = row
        self.setFixedHeight(ROW_HEIGHT)

        shell = QHBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.frame = StrikeRow()
        self.frame.setStrikeRight(CONTROLS_WIDTH + theme.GAP)
        shell.addWidget(self.frame)

        line = QHBoxLayout(self.frame)
        line.setContentsMargins(0, 0, 16, 0)
        line.setSpacing(theme.GAP)

        self.band = CompoundBand(row.compound)
        self.band.setFixedWidth(CompoundBand.WIDTH)
        line.addWidget(self.band)

        self.lap_label = Measured(f"{row.lap_num:>2}", colour=theme.STENCIL_DIM)
        self.lap_label.setFixedWidth(W_LAP)
        line.addWidget(self.lap_label)

        self.time_label = Measured(format_lap_time(row.lap_time_ms),
                                   size=theme.DATA_LARGE_PX, bold=True)
        self.time_label.setFixedWidth(W_TIME)
        line.addWidget(self.time_label)

        delta = row.lap_time_ms - best_ms if best_ms else 0
        self.delta_label = Measured(
            format_delta(delta), colour=theme.STENCIL_DIM)
        self.delta_label.setFixedWidth(W_DELTA)
        line.addWidget(self.delta_label)

        self.fuel_label = Measured(f"{row.fuel_used:.2f} L",
                                   colour=theme.STENCIL_DIM)
        self.fuel_label.setFixedWidth(W_FUEL)
        line.addWidget(self.fuel_label)

        marker = self.row.structural_reason()
        self.marker_label = StencilLabel(marker or "", size=11,
                                         colour=theme.STRUCK, tracking=10.0)
        self.marker_label.setFixedWidth(W_MARKER)
        line.addWidget(self.marker_label)

        line.addStretch(1)

        self.compound_picker = QComboBox()
        self.compound_picker.addItem(UNTAGGED, None)
        for compound in ALL_COMPOUNDS:
            self.compound_picker.addItem(compound.code, compound.code)
        if row.compound:
            self.compound_picker.setCurrentText(row.compound)
        self.compound_picker.setFixedWidth(W_COMPOUND)
        self.compound_picker.currentIndexChanged.connect(self._on_compound)
        self.compound_picker.setToolTip("Which compound this lap ran on")
        line.addWidget(self.compound_picker)

        self.wear_front = self._wear_box("Front tyre gauge, fraction consumed")
        self.wear_rear = self._wear_box("Rear tyre gauge, fraction consumed")
        line.addWidget(self.wear_front)
        line.addWidget(self.wear_rear)

        self.exclude_button = MarkButton("Count", parent=self)
        self.exclude_button.setFixedWidth(W_ACTION)
        self.exclude_button.setMinimumHeight(30)
        self.exclude_button.setFont(theme.stencil_font(12, tracking=6.0))
        self.exclude_button.clicked.connect(self._on_exclude)
        line.addWidget(self.exclude_button)

        self._sync()

    def _wear_box(self, tip: str) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(-0.01, 1.0)
        box.setDecimals(2)
        box.setSingleStep(0.05)
        box.setValue(-0.01)
        box.setSpecialValueText(UNTAGGED)
        box.setFixedWidth(W_WEAR)
        box.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        box.setToolTip(tip)
        box.valueChanged.connect(lambda _: self._on_wear())
        return box

    # --------------------------------------------------------------- actions

    def _on_compound(self) -> None:
        self.row.compound = self.compound_picker.currentData()
        self.band.setCode(self.row.compound)
        self.changed.emit(self.row.lap_id)

    def _on_wear(self) -> None:
        front = self.wear_front.value()
        rear = self.wear_rear.value()
        self.row.wear_front = None if front < 0 else front
        self.row.wear_rear = None if rear < 0 else rear
        self.changed.emit(self.row.lap_id)

    def _on_exclude(self) -> None:
        if self.row.structural_reason():
            return
        self.row.excluded = not self.row.excluded
        self._sync()
        self.changed.emit(self.row.lap_id)

    def _sync(self) -> None:
        struck = not self.row.counted
        self.frame.setStruck(struck)
        self.band.setStruck(struck)

        ink = theme.STRUCK if struck else theme.STENCIL
        self.time_label.setStyleSheet(f"color: {ink}; background: transparent;")

        if self.row.structural_reason():
            # An out-lap or in-lap is structurally uncounted; there is nothing
            # to toggle, and the reason already reads in the marker column.
            self.exclude_button.setEnabled(False)
            self.exclude_button.setText("")
        else:
            self.exclude_button.setText("Struck" if self.row.excluded else "Count")


class PracticeScreen(QWidget):
    """The rack, its spec line, and the export that ends the session."""

    export_requested = pyqtSignal()
    lap_changed = pyqtSignal(int)
    recording_toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list[LapRow] = []
        self._row_widgets: list[RackRow] = []
        self._recording = False
        self._build()

    def _build(self) -> None:
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 24)
        page.setSpacing(theme.GAP_WIDE)

        header = QHBoxLayout()
        header.setSpacing(theme.GAP)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(StencilLabel("Practice", size=theme.TITLE_PX,
                                      colour=theme.STENCIL, tracking=6.0))
        self.subtitle = BodyLabel("Waiting for the car to go out.",
                                  colour=theme.STENCIL_DIM)
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)

        self.record_button = MarkButton("Start practice", primary=True)
        self.record_button.clicked.connect(self._toggle_recording)
        header.addWidget(self.record_button, 0, Qt.AlignmentFlag.AlignBottom)
        page.addLayout(header)

        self.spec = SpecLine()
        page.addWidget(self.spec)

        page.addWidget(self._rack_plate(), 1)
        page.addLayout(self._footer())
        self.refresh()

    def _rack_plate(self) -> Plate:
        plate = Plate("Laps")
        plate.body.setContentsMargins(1, 26, 1, 1)
        plate.body.setSpacing(0)

        plate.body.addWidget(self._column_heads())

        self.scroller = QScrollArea()
        self.scroller.setWidgetResizable(True)
        self.scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.rack = QWidget()
        self.rack_layout = QVBoxLayout(self.rack)
        self.rack_layout.setContentsMargins(0, 0, 0, 0)
        self.rack_layout.setSpacing(0)
        self.rack_layout.addStretch(1)
        self.scroller.setWidget(self.rack)

        plate.body.addWidget(self.scroller, 1)
        return plate

    def _column_heads(self) -> QWidget:
        head = QWidget()
        head.setFixedHeight(30)
        head.setStyleSheet(f"background: {theme.SHOULDER};")
        row = QHBoxLayout(head)
        row.setContentsMargins(0, 0, 16, 0)
        row.setSpacing(theme.GAP)

        def cap(text: str, width: int) -> StencilLabel:
            label = StencilLabel(text, size=10, colour=theme.STRUCK,
                                 tracking=14.0)
            label.setFixedWidth(width)
            return label

        row.addWidget(cap("SET", CompoundBand.WIDTH))
        row.addWidget(cap("LAP", W_LAP))
        row.addWidget(cap("TIME", W_TIME))
        row.addWidget(cap("DELTA", W_DELTA))
        row.addWidget(cap("FUEL", W_FUEL))
        row.addWidget(cap("", W_MARKER))
        row.addStretch(1)
        row.addWidget(cap("COMPOUND", W_COMPOUND))
        row.addWidget(cap("WEAR F", W_WEAR))
        row.addWidget(cap("WEAR R", W_WEAR))
        row.addWidget(cap("", W_ACTION))
        return head

    def _footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.footer_note = BodyLabel(
            "Tag a compound on every counted lap before exporting - fuel and "
            "wear evidence is grouped by compound.",
            size=13, colour=theme.STRUCK)
        row.addWidget(self.footer_note, 1)

        self.export_button = MarkButton("Export for the tune builder",
                                        primary=True)
        self.export_button.clicked.connect(self.export_requested.emit)
        row.addWidget(self.export_button)
        return row

    # ------------------------------------------------------------------ data

    def set_laps(self, rows: list[LapRow]) -> None:
        self._rows = list(rows)
        self._rebuild_rack()
        self.refresh()

    def add_lap(self, row: LapRow) -> None:
        self._rows.append(row)
        self._rebuild_rack()
        self.refresh()

    def rows(self) -> list[LapRow]:
        return list(self._rows)

    def _rebuild_rack(self) -> None:
        while self.rack_layout.count():
            item = self.rack_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._row_widgets.clear()

        best = self._best_ms()
        for row in self._rows:
            widget = RackRow(row, best)
            widget.changed.connect(self._on_row_changed)
            self.rack_layout.addWidget(widget)
            self._row_widgets.append(widget)
        self.rack_layout.addStretch(1)

    def _on_row_changed(self, lap_id: int) -> None:
        self.refresh()
        self.lap_changed.emit(lap_id)

    def _best_ms(self) -> int:
        times = [r.lap_time_ms for r in self._rows if r.counted and r.lap_time_ms > 0]
        return min(times) if times else 0

    def refresh(self) -> None:
        counted = [r for r in self._rows if r.counted]
        times = sorted(r.lap_time_ms for r in counted if r.lap_time_ms > 0)
        burns = [r.fuel_used for r in counted if r.fuel_used > 0]

        self.spec.clear()
        self.spec.add("Counted", f"{len(counted)}/{len(self._rows)}")
        if times:
            self.spec.add("Best", format_lap_time(times[0]), emphasis=True)
            self.spec.add("Median", format_lap_time(times[len(times) // 2]))
        if burns:
            self.spec.add("Fuel", f"{sorted(burns)[len(burns) // 2]:.2f} L/lap")
        untagged = [r for r in counted if not r.compound]
        if untagged:
            self.spec.add("Untagged", str(len(untagged)), declared=True)
        self.spec.finish()

        # The subtitle belongs to the controller: it carries connection and
        # session state, which refresh() has no way of knowing. Lap counts are
        # already in the spec line.
        self.export_button.setEnabled(bool(counted))
        if untagged:
            self.footer_note.setText(
                f"{len(untagged)} counted "
                f"{'lap has' if len(untagged) == 1 else 'laps have'} no "
                "compound. Fuel and wear evidence is grouped by compound.")
            self.footer_note.setStyleSheet(f"color: {theme.WARNING};")
        elif counted:
            self.footer_note.setText("Every counted lap is marked.")
            self.footer_note.setStyleSheet(f"color: {theme.STRUCK};")
        else:
            self.footer_note.setText("Nothing to export yet.")
            self.footer_note.setStyleSheet(f"color: {theme.STRUCK};")

    def _toggle_recording(self) -> None:
        self.recording_toggled.emit(not self._recording)

    def set_recording(self, recording: bool) -> None:  # noqa: N802 - Qt naming
        """Reflect what the controller actually managed to do, not the click."""
        self._recording = recording
        self.record_button.setText(
            "Stop practice" if recording else "Start practice")

    def set_status(self, text: str, *, warn: bool = False) -> None:  # noqa: N802
        self.subtitle.setText(text)
        self.subtitle.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.STENCIL_DIM};"
            f"background: transparent;")

    def note(self, text: str, *, warn: bool = False) -> None:
        self.footer_note.setText(text)
        self.footer_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};")
