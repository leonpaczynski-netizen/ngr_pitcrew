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
    QFrame,
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
    Derived,
    EmptyState,
    MarkButton,
    Measured,
    Plate,
    SpecLine,
    StencilLabel,
)

SOURCE_INK = {
    MEASURED: theme.STENCIL,
    DECLARED: theme.CRAYON,
    ASSUMED: theme.DERIVED,
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


class CrossoverBand(QFrame):
    """The compound call, in one sentence, directly under the spec line.

    This is the question the driver asks before a race — is it worth running
    the harder tyre longer to save a stop — so it gets the width of the page
    rather than a row in the evidence column.

    Derived ink, because the app worked it out; nobody measured it and nobody
    typed it. When either compound is planned on a rate that was never
    measured on it, the band says so in warning and the sentence leads with
    that rather than with the verdict.

    Two different kinds of doubt reach this band and they are not the same, so
    the heading names which one:

    * **unconfirmed** — a compound has no measured rate at all, so the
      comparison has not been earned yet;
    * **outside the tyre window** — the rates are real, but one was gathered
      on a tyre that was not working, so it describes the conditions as much
      as the compound.

    The second is the quieter failure. The arithmetic looks complete and the
    numbers are genuinely measured; only the temperature says the answer will
    not reproduce on race day.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QVBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 12)
        row.setSpacing(2)

        self.heading = StencilLabel("Compound call", size=10,
                                    colour=theme.STENCIL_DIM, tracking=14.0)
        row.addWidget(self.heading)
        self.verdict = BodyLabel("", size=14, colour=theme.DERIVED)
        self.verdict.setWordWrap(True)
        row.addWidget(self.verdict)
        self.setVisible(False)

    def show_crossover(self, crossover: dict | None) -> None:  # noqa: N802
        """Nothing to show is not the same as a dead heat, so it hides."""
        if not crossover or not crossover.get("verdict"):
            self.setVisible(False)
            return
        assumed = bool(crossover.get("restsOnAssumption"))
        cold = bool(crossover.get("outsideTyreWindow"))
        ink = theme.WARNING if (assumed or cold) else theme.DERIVED
        self.verdict.setText(crossover["verdict"])
        self.verdict.setStyleSheet(f"color: {ink}; background: transparent;")
        if assumed:
            heading = "Compound call — unconfirmed"
        elif cold:
            heading = "Compound call — outside the tyre window"
        else:
            heading = "Compound call"
        self.heading.setText(heading)
        self.setStyleSheet(
            f"CrossoverBand {{ background: {theme.SHOULDER};"
            # A 1px groove, not a coloured left border - the world's ban list
        # names that explicitly, and the doubt is already carried by the
        # heading and the ink of the sentence itself.
        f" border: 1px solid {theme.TREAD}; }}")
        self.setVisible(True)


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
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"Plan {index + 1}")

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
            head.addWidget(Derived(f"+{plan.delta_s:.1f} s",
                                    colour=theme.STENCIL_DIM))
        # Derived, not measured. The race has not been run: this is the stint
        # model's output against a wear rate that may itself be assumed. The
        # evidence column below holds that line and the headline above it did
        # not.
        head.addWidget(Derived(_race_time(plan.total_time_s), bold=True))
        column.addLayout(head)

        column.addWidget(StintBar(plan.stints))

        detail = ", ".join(
            f"box lap {lap}" for lap in plan.pit_laps) or "run to the flag"
        column.addWidget(BodyLabel(
            f"{detail}. Limited by {plan.binding_constraint}.",
            size=13, colour=theme.STENCIL_DIM, wrap=True))

    def setChosen(self, chosen: bool) -> None:  # noqa: N802 - Qt naming
        self._chosen = chosen
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.selected.emit(self.index)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        # Approve acts on the chosen plan, and the choice could only ever be
        # changed by clicking - so a keyboard user could approve plan 0 and
        # nothing else.
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return,
                           Qt.Key.Key_Enter):
            self.selected.emit(self.index)
            return
        super().keyPressEvent(event)

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

        self.crossover_band = CrossoverBand()
        page.addWidget(self.crossover_band)

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
        # AsNeeded, not AlwaysOff. Hiding the bar did not stop the
        # content overflowing below 1600 wide - it only stopped it
        # being reachable.
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.plan_holder = QWidget()
        self.plan_layout = QVBoxLayout(self.plan_holder)
        self.plan_layout.setContentsMargins(0, 0, 0, 0)
        self.plan_layout.setSpacing(theme.GAP)
        self.plan_empty = EmptyState(
            "No plans yet. Build from practice needs:",
            ("an event, with its race length and pit loss",
             "counted practice laps at race pace",
             "a compound tagged on those laps",
             "a tyre-gauge reading, for the wear rate"))
        self.plan_layout.addWidget(self.plan_empty)
        self.plan_layout.addStretch(1)
        scroller.setWidget(self.plan_holder)

        plate.body.addWidget(scroller, 1)
        return plate

    def _evidence_plate(self) -> Plate:
        plate = Plate("What this rests on")
        self.evidence_empty = EmptyState(
            "Every input the plan would use, and where each one came from, "
            "appears here once a plan is built.")
        plate.body.addWidget(self.evidence_empty)
        self.evidence_layout = QVBoxLayout()
        self.evidence_layout.setSpacing(theme.GAP)
        plate.body.addLayout(self.evidence_layout)
        plate.body.addStretch(1)
        return plate

    def _footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.footer_note = BodyLabel("", size=13, colour=theme.STENCIL_DIM)
        row.addWidget(self.footer_note, 1)
        self.approve_button = MarkButton("Approve for the race", primary=True)
        self.approve_button.setEnabled(False)
        self.approve_button.clicked.connect(
            lambda: self.approve_requested.emit(self._chosen))
        row.addWidget(self.approve_button)
        return row

    # ------------------------------------------------------------------ data

    def _on_save(self) -> None:
        """The primary action, under the name the shell looks for.

        `Ctrl+S` / `Ctrl+Return` probes every screen for `_on_save`,
        `_on_export` or `_on_generate` and then special-cases two by identity.
        Strategy answered to none of them, so the key was silently inert on
        the screen whose primary action is approving the race plan.
        """
        if self._cards:
            self.approve_requested.emit(self._chosen)

    def show_plans(self, plans, evidence, *, approved_index: int | None = None,
                   timed: bool = False) -> None:
        self._clear(self.plan_layout)
        self._cards.clear()
        # The empty state survives _clear so it can come back: a rebuild that
        # produces nothing has to say so again, not leave a blank plate.
        # **Hidden explicitly when it is not wanted.** Taking it out of the
        # layout does not take it off the screen - it stays a child of the
        # holder, keeps its last geometry, and draws underneath the plan
        # cards. On the first real plan that put "a tyre-gauge reading, for
        # the wear rate" through the middle of the fastest strategy.
        self.plan_empty.setVisible(not plans)
        if not plans:
            self.plan_layout.addWidget(self.plan_empty)
        self.evidence_empty.setVisible(not evidence)

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

        # **Cleared whether or not there is anything to put back.** Both the
        # clear and every `add` sat inside `if plans:`, so a refused rebuild -
        # `StrategyImpossible`, caught in the controller, which calls
        # `show_plans([], ...)` and returns - left the previous plan's race
        # time and stop count on the line at DATA_LARGE_PX above a plate
        # reading "No plans yet". The two largest pieces of text on the screen
        # described a plan the app had just refused to make.
        self.spec.clear()
        if plans:
            best = plans[0]
            # **Every figure on this line is derived.** The race has not been
            # run: these are the stint model's outputs, against a wear rate
            # that may itself be assumed. They wore stencil white - the ink
            # for something that came off the telemetry stream - directly
            # above an evidence column whose entire job is to say which parts
            # of the plan are measured and which are guesses.
            self.spec.add("Plan", best.label(), derived=True, emphasis=True)
            # A timed race is won on distance: every plan ends when the clock
            # does, so the headline is how far this one gets, and the time is
            # only when the flag fell.
            if timed:
                self.spec.add("Distance", f"{best.laps_completed} laps",
                              derived=True, emphasis=True)
                self.spec.add("Flag at", _race_time(best.total_time_s),
                              derived=True)
            else:
                self.spec.add("Race time", _race_time(best.total_time_s),
                              derived=True)
            # "unknown" is a gap, not a declaration - nobody typed it. The
            # evidence column already paints MISSING in warning; this matches.
            unknown = best.binding_constraint == "unknown"
            self.spec.add("Limited by", best.binding_constraint,
                          derived=not unknown, warn=unknown)
            self.spec.finish()
            self.subtitle.setText(
                f"{len(plans)} legal plans. "
                f"{best.notes[0] if best.notes else ''}")
            self.crossover_band.show_crossover(best.crossover)
        else:
            self.crossover_band.show_crossover(None)
            # The footer belongs to the last plan too. "Every input measured"
            # under a refusal reads as a verdict on the refusal.
            self.footer_note.setText("")

    def _show_evidence(self, evidence) -> None:
        self._clear(self.evidence_layout)
        for item in evidence:
            self.evidence_layout.addWidget(_EvidenceRow(item))

    def _clear(self, layout) -> None:
        """Empty a layout, keeping the empty-state block alive.

        It is detached rather than destroyed, because a rebuild that produces
        no plans has to say so again - and a deleted widget cannot.
        """
        keep = (getattr(self, "plan_empty", None),
                getattr(self, "evidence_empty", None))
        while layout.count():
            entry = layout.takeAt(0)
            widget = entry.widget()
            if widget is None or widget in keep:
                continue
            widget.deleteLater()

    def _on_selected(self, index: int) -> None:
        self._chosen = index
        self._sync_selection()

    def _sync_selection(self) -> None:
        for card in self._cards:
            card.setChosen(card.index == self._chosen)

    def note(self, text: str, *, warn: bool = False) -> None:
        self.footer_note.setText(text)
        self.footer_note.set_ink(theme.WARNING if warn else theme.CHALK)

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
        # **Wrapped.** A label that will not wrap makes its longest sentence
        # the widget's minimum width, and these notes are prose - the
        # time-of-day one is a paragraph. Unwrapped, one plan pushed the
        # screen's minimum to 6,268 px, which is four times the widest
        # monitor on this rig: the plan was rendered perfectly and every
        # column of it was off the side of the screen. That is "you can't
        # see the plans".
        note = BodyLabel(trailer, size=12, colour=theme.STENCIL_DIM, wrap=True)
        column.addWidget(note)


def _race_time(seconds: float) -> str:
    total = int(round(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
