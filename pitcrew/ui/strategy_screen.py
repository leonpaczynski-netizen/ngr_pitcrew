"""Strategy — the plan, and what it rests on.

A plan is a sequence of sets, so it is drawn as one: a bar of compound bands
whose widths are the stint lengths, broken by a pit mark. Two plans can be
compared at a glance without reading a number, the same way the practice rack
shows the shape of a session.

The evidence column is the other half, and it is not decoration. Every input
renders in the register it came from — stencil for telemetry, crayon for what
the driver entered, struck for the app's own assumptions — so it is obvious
which parts of the plan are measured and which are guesses. A plan whose tyre
wear is a guess is a different object from one whose wear was read off the
gauge, and it must not look the same.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pitcrew.strategy.evidence import ASSUMED, DECLARED, MEASURED, MISSING
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

SOURCE_INK = {
    MEASURED: theme.STENCIL,
    DECLARED: theme.CRAYON,
    ASSUMED: theme.STRUCK,
    MISSING: theme.WARNING,
}
SOURCE_WORD = {
    MEASURED: "measured",
    DECLARED: "entered",
    ASSUMED: "assumed",
    MISSING: "not known",
}


class StintBar(QWidget):
    """The plan as a run of sets: band widths are stint lengths."""

    PIT_MARK = 3

    def __init__(self, stints, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._stints = list(stints)
        self.setMinimumHeight(34)
        self._font = theme.stencil_font(12, tracking=6.0)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(theme.RUBBER_DEEP))

        total = sum(stint.laps for stint in self._stints) or 1
        usable = self.width() - self.PIT_MARK * max(0, len(self._stints) - 1)
        x = 0
        painter.setFont(self._font)

        for index, stint in enumerate(self._stints):
            width = round(usable * stint.laps / total)
            if index == len(self._stints) - 1:
                width = self.width() - x
            colour = theme.band_colour(stint.compound)
            painter.fillRect(x, 0, width, self.height(), colour)

            painter.setPen(QPen(theme.band_ink(stint.compound)))
            label = f"{stint.compound or '—'}  {stint.laps}"
            painter.drawText(x, 0, width, self.height(),
                             Qt.AlignmentFlag.AlignCenter, label)
            x += width

            if index < len(self._stints) - 1:
                painter.fillRect(x, 0, self.PIT_MARK, self.height(),
                                 QColor(theme.RUBBER))
                x += self.PIT_MARK
        painter.end()


class PlanCard(QWidget):
    """One candidate. Clicking selects it; the approved one is the race plan."""

    selected = pyqtSignal(int)

    def __init__(self, index: int, plan, *, best: bool,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.index = index
        self.plan = plan
        self._chosen = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        column = QVBoxLayout(self)
        column.setContentsMargins(16, 12, 16, 14)
        column.setSpacing(theme.GAP_TIGHT)

        head = QHBoxLayout()
        head.setSpacing(theme.GAP)
        head.addWidget(StencilLabel(plan.label(), size=15,
                                    colour=theme.STENCIL, tracking=10.0))
        head.addStretch(1)
        if best:
            head.addWidget(StencilLabel("Fastest", size=10,
                                        colour=theme.CHALK, tracking=14.0))
        else:
            head.addWidget(Measured(f"+{plan.delta_s:.1f} s",
                                    colour=theme.STENCIL_DIM))
        head.addWidget(Measured(_race_time(plan.total_time_s), bold=True))
        column.addLayout(head)

        column.addWidget(StintBar(plan.stints))

        detail = ", ".join(
            f"box lap {lap}" for lap in plan.pit_laps) or "run to the flag"
        column.addWidget(BodyLabel(
            f"{detail}. Limited by {plan.binding_constraint}.",
            size=13, colour=theme.STENCIL_DIM, wrap=False))

    def setChosen(self, chosen: bool) -> None:  # noqa: N802 - Qt naming
        self._chosen = chosen
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.selected.emit(self.index)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(
            theme.SHOULDER_HI if self._chosen else theme.SHOULDER))
        pen = QPen(QColor(theme.CRAYON if self._chosen else theme.TREAD), 1)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()


class StrategyScreen(QWidget):
    """Build a plan from the practice evidence, then approve one."""

    build_requested = pyqtSignal()
    approve_requested = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards: list[PlanCard] = []
        self._chosen = 0
        self._build()

    def _build(self) -> None:
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 24)
        page.setSpacing(theme.GAP_WIDE)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(StencilLabel("Strategy", size=theme.TITLE_PX,
                                      colour=theme.STENCIL, tracking=6.0))
        self.subtitle = BodyLabel("No plan yet.", colour=theme.STENCIL_DIM)
        titles.addWidget(self.subtitle)
        header.addLayout(titles, 1)

        self.build_button = MarkButton("Build from practice")
        self.build_button.clicked.connect(self.build_requested.emit)
        header.addWidget(self.build_button, 0, Qt.AlignmentFlag.AlignBottom)
        page.addLayout(header)

        self.spec = SpecLine()
        page.addWidget(self.spec)

        columns = QHBoxLayout()
        columns.setSpacing(theme.GAP_WIDE)
        columns.addWidget(self._plans_plate(), 5)
        columns.addWidget(self._evidence_plate(), 3)
        page.addLayout(columns, 1)

        page.addLayout(self._footer())

    def _plans_plate(self) -> Plate:
        plate = Plate("Plans")
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.plan_holder = QWidget()
        self.plan_layout = QVBoxLayout(self.plan_holder)
        self.plan_layout.setContentsMargins(0, 0, 0, 0)
        self.plan_layout.setSpacing(theme.GAP)
        self.plan_layout.addStretch(1)
        scroller.setWidget(self.plan_holder)

        plate.body.addWidget(scroller, 1)
        return plate

    def _evidence_plate(self) -> Plate:
        plate = Plate("What this rests on")
        self.evidence_layout = QVBoxLayout()
        self.evidence_layout.setSpacing(theme.GAP)
        plate.body.addLayout(self.evidence_layout)
        plate.body.addStretch(1)
        return plate

    def _footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.footer_note = BodyLabel("", size=13, colour=theme.STRUCK)
        row.addWidget(self.footer_note, 1)
        self.approve_button = MarkButton("Approve for the race", primary=True)
        self.approve_button.setEnabled(False)
        self.approve_button.clicked.connect(
            lambda: self.approve_requested.emit(self._chosen))
        row.addWidget(self.approve_button)
        return row

    # ------------------------------------------------------------------ data

    def show_plans(self, plans, evidence, *, approved_index: int | None = None) -> None:
        self._clear(self.plan_layout)
        self._cards.clear()

        for index, plan in enumerate(plans):
            card = PlanCard(index, plan, best=index == 0)
            card.selected.connect(self._on_selected)
            self.plan_layout.insertWidget(index, card)
            self._cards.append(card)
        self.plan_layout.addStretch(1)

        self._show_evidence(evidence)
        self._chosen = 0 if approved_index is None else approved_index
        self._sync_selection()
        self.approve_button.setEnabled(bool(plans))

        if plans:
            best = plans[0]
            self.spec.clear()
            self.spec.add("Plan", best.label(), emphasis=True)
            self.spec.add("Race time", _race_time(best.total_time_s))
            self.spec.add("Limited by", best.binding_constraint,
                          declared=best.binding_constraint == "unknown")
            self.spec.finish()
            self.subtitle.setText(
                f"{len(plans)} legal plans. "
                f"{best.notes[0] if best.notes else ''}")

    def _show_evidence(self, evidence) -> None:
        self._clear(self.evidence_layout)
        for item in evidence:
            self.evidence_layout.addWidget(_EvidenceRow(item))

    def _clear(self, layout) -> None:
        while layout.count():
            entry = layout.takeAt(0)
            if entry.widget():
                entry.widget().deleteLater()

    def _on_selected(self, index: int) -> None:
        self._chosen = index
        self._sync_selection()

    def _sync_selection(self) -> None:
        for card in self._cards:
            card.setChosen(card.index == self._chosen)

    def note(self, text: str, *, warn: bool = False) -> None:
        self.footer_note.setText(text)
        self.footer_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};")

    def set_status(self, text: str, *, warn: bool = False) -> None:  # noqa: N802
        self.subtitle.setText(text)
        self.subtitle.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.STENCIL_DIM};"
            f"background: transparent;")


class _EvidenceRow(QWidget):
    """One input, rendered in the register it came from."""

    def __init__(self, item, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(1)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.GAP)
        row.addWidget(StencilLabel(item.label, size=11, tracking=12.0), 1)

        ink = SOURCE_INK.get(item.source, theme.STENCIL_DIM)
        cls = Declared if item.source == DECLARED else Measured
        row.addWidget(cls(item.value, colour=ink))
        column.addLayout(row)

        # The word matters as much as the colour: nothing derived may be
        # mistaken for something measured.
        trailer = SOURCE_WORD.get(item.source, item.source)
        if item.note:
            trailer = f"{trailer} — {item.note}"
        column.addWidget(BodyLabel(trailer, size=12, colour=theme.STRUCK,
                                   wrap=False))


def _race_time(seconds: float) -> str:
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
