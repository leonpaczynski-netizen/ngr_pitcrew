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
    QSpinBox,
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
    Field,
    block_wheel,
    HintLabel,
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


# Triggers the feed carries nothing for. GT7 broadcasts no weather and no
# flag state in any packet format, so George cannot detect either whatever a
# playbook says - and the card must say "he cannot see it", not "he has no
# rule", because those ask different things of the driver.
CANNOT_SEE = ("rain", "safety_car")


class LoadedCard(QWidget):
    """A plan the app did not write, and the contract that came with it.

    **It must not look like the optimiser's cards, and the reason is this
    world's whole thesis: provenance never looks alike.** A loaded plan is not
    a candidate ranked against the others - it was never costed by the same
    model - so it carries no `+N s` delta. Rendering one would be a fabricated
    comparison, and a fabricated comparison in stencil is exactly the failure
    the registers exist to prevent.

    What it carries instead is the thing the optimiser's plans cannot have:
    an author, and a playbook. `strategy/handover.py` states the split - Ludo
    plans, George executes, and the bounds George may move inside are part of
    the handover rather than something the app decides. The driver has to know
    those bounds before the green, not after, so they are on the card he
    approves rather than a screen away.

    Three registers, doing the work they already do. The author and the plan's
    own figures are **crayon**: a human declared them, the same as a setup
    sheet he pastes in. The certificate is **derived**: the app worked out
    whether the car can execute someone else's plan. What the certificate
    could not check is named too, because silence is never a pass, and a plan
    certified by a gate that skipped half its tests carries the authority
    without the arithmetic.
    """

    selected = pyqtSignal(int)

    def __init__(self, strategy_id: int, row: dict,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        from pitcrew.strategy.handover import author_of, playbook_of

        self.strategy_id = strategy_id
        self._chosen = False
        plan = row.get("plan") or {}
        handover = plan.get("handover") or {}
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        author = author_of(plan) or "the desk"
        self.setAccessibleName(f"{row.get('label') or 'Loaded plan'}, "
                               f"written by {author}")

        column = QVBoxLayout(self)
        column.setContentsMargins(16, 12, 16, 14)
        column.setSpacing(theme.GAP_TIGHT)

        head = QHBoxLayout()
        head.setSpacing(theme.GAP)
        head.addWidget(StencilLabel(row.get("label") or "Loaded plan",
                                    size=15, colour=theme.STENCIL,
                                    tracking=10.0))
        head.addStretch(1)
        # **Who wrote it, where the others carry their ranking.** The
        # optimiser's cards say "Fastest" or "+1.4 s" because they were costed
        # against each other. This one was not, so the slot says the thing
        # that IS true about it.
        head.addWidget(Declared(author.upper()))
        column.addLayout(head)

        stints = plan.get("stints") or []
        column.addWidget(StintBar(_as_stints(stints)))

        laps = plan.get("pit_laps") or []
        detail = ", ".join(f"box lap {lap}" for lap in laps) or "run to the flag"
        constraint = plan.get("binding_constraint") or "an unnamed limit"
        column.addWidget(BodyLabel(
            f"{detail}. Limited by {constraint}.",
            size=13, colour=theme.STENCIL_DIM, wrap=True))

        certificate = handover.get("certificate") or {}
        # **Wrapped, like every other prose line here.** `Derived` does not,
        # and a real certify warning is a sentence: measured, one of them set
        # the card's minimum width to 1,352 px and an `unchecked` line to
        # 1,607 px against a ~733 px plate, pushing the very thing the card
        # exists to carry off the side of the screen. The plate's
        # `ScrollBarAsNeeded` hid it from the width guard.
        for warning in certificate.get("warnings") or ():
            column.addWidget(BodyLabel(warning, size=13,
                                       colour=theme.DERIVED, wrap=True))
        for gap in certificate.get("unchecked") or ():
            # Named, not dropped. A check that could not run is not a check
            # that passed, and the driver is the only one who can decide
            # whether to race on it.
            column.addWidget(BodyLabel(f"Not checked: {gap}", size=13,
                                       colour=theme.STENCIL_DIM, wrap=True))

        entries = playbook_of(plan)
        if entries:
            column.addWidget(StencilLabel(
                "George may, on his own", size=11,
                colour=theme.STENCIL_DIM, tracking=14.0))
            for entry in entries:
                column.addWidget(BodyLabel(
                    f"{entry.trigger.replace('_', ' ')} - "
                    f"{entry.action.replace('_', ' ')} "
                    f"when {entry.when}"
                    + (f", until {entry.until}" if entry.until else ""),
                    size=13, colour=theme.CRAYON, wrap=True))

        unhandled = handover.get("unhandled") or []
        blind = [t for t in unhandled if t in CANNOT_SEE]
        no_rule = [t for t in unhandled if t not in CANNOT_SEE]
        if blind:
            # **These he cannot see at all**, whatever any playbook says. GT7
            # broadcasts no weather and no flag state in any packet format, so
            # a rule for either is a rule that can never fire - which is worse
            # than no rule, because the driver believes it is armed.
            column.addWidget(BodyLabel(
                "He cannot see " + ", ".join(t.replace("_", " ")
                                             for t in blind)
                + " at all - tell him.",
                size=13, colour=theme.STENCIL_DIM, wrap=True))
        if no_rule:
            # **"No rule from the desk", not "he will do nothing".** The card
            # said the second and it was false in the direction that matters:
            # `stop_still_needed` and `stay_out_call` decide fuel and a missed
            # stop with or without a playbook, so a driver told George would
            # stay out of it would have been told the opposite of the truth on
            # the one screen where he is reading the contract.
            # **`STENCIL_DIM`, not `STRUCK`.** Struck means removed from the
            # count - placeholders, disabled controls, an excluded lap. This
            # is prose, and it is the most consequential prose on the card:
            # the driver reading it is learning what George will stay silent
            # about. Setting it in the ink for things that do not count, at
            # 2.93:1, would be the register saying the opposite of the words.
            column.addWidget(BodyLabel(
                "No rule from the desk on "
                + ", ".join(t.replace("_", " ") for t in no_rule)
                + " - George falls back to his own.",
                size=13, colour=theme.STENCIL_DIM, wrap=True))

    def setChosen(self, chosen: bool) -> None:  # noqa: N802 - Qt naming
        self._chosen = chosen
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.selected.emit(self.strategy_id)

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return,
                           Qt.Key.Key_Enter):
            self.selected.emit(self.strategy_id)
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(
            theme.SHOULDER_HI if self._chosen else theme.SHOULDER))
        painter.setPen(QPen(QColor(
            theme.CRAYON if self._chosen else theme.TREAD), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.end()


class _Stint:
    """What `StintBar` reads, off a stored plan's plain dicts."""

    __slots__ = ("laps", "compound")

    def __init__(self, laps: int, compound: str | None) -> None:
        self.laps, self.compound = laps, compound


def _as_stints(rows: list) -> list:
    return [_Stint(int(r.get("laps") or 0), r.get("compound"))
            for r in rows if isinstance(r, dict)]


class StrategyScreen(QWidget):
    """Build a plan from the practice evidence, then approve one."""

    build_requested = pyqtSignal()
    qualifying_requested = pyqtSignal()
    approve_requested = pyqtSignal(int)
    # **A separate signal, because it carries a different kind of number.**
    # `approve_requested` sends an INDEX into the optimiser's list; this sends
    # a stored row's id. One signal carrying both would be two meanings on one
    # wire, which is how a plan gets approved by ordinal against a list it was
    # never in.
    approve_loaded_requested = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._cards: list[PlanCard] = []
        self._loaded_cards: list[LoadedCard] = []
        self._chosen = 0
        # The stored id of a loaded plan the driver picked, or None while the
        # selection is one of the app's own.
        self._chosen_loaded: int | None = None
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
        # **Stacked, not a third column.** At 3:3:3 the plan cards lose the
        # width their stint bars need, and the race is still what this screen
        # is about; qualifying is the smaller job that happens to be a plan.
        side = QVBoxLayout()
        side.setSpacing(theme.GAP_WIDE)
        side.addWidget(self._evidence_plate(), 1)
        side.addWidget(self._qualifying_plate())
        columns.addLayout(side, 3)

        # **The third screen to need a page bar, and for the same reason as
        # the first two.** Settings shipped without one at 1,291 px against a
        # display that gives 501; Practice reached 548 when the debrief landed;
        # this reached 552 when qualifying did. The guard test written after
        # Settings is what caught all three, and the answer is the same every
        # time - the screen gets the bar rather than the content getting cut.
        body = QWidget()
        holder = QVBoxLayout(body)
        holder.setContentsMargins(0, 0, 0, 0)
        holder.setSpacing(0)
        holder.addLayout(columns, 1)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroller.setWidget(body)
        page.addWidget(scroller, 1)

        # Outside the bar: the plan is saved from here and a control that can
        # be scrolled away from is a control that cannot be found.
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
        # **Loaded plans sit above the optimiser's, and the rule says why.**
        # `handover.py`'s own words: Ludo's plan is the plan, and the app's is
        # the fallback and the comparison. Ordering them the other way would
        # put the fallback first on the screen where the choice is made.
        self.loaded_layout = QVBoxLayout()
        self.loaded_layout.setContentsMargins(0, 0, 0, 0)
        self.loaded_layout.setSpacing(theme.GAP)
        self.plan_layout.insertLayout(0, self.loaded_layout)
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

    def _qualifying_plate(self) -> Plate:
        """How much fuel, and how many runs.

        **A qualifying run is not a small race, and the difference is 73 kg.**
        The race plans beside this are about lasting; this is about carrying
        nothing you are not going to burn. It sits on this screen because it is
        a plan - read before the session with the headset off, like the rest
        of it - and in the right column because the race is still the subject.

        The litres are arithmetic on a measured burn and the plan is entitled
        to be firm about them. The seconds beside them are not, and they are
        rendered differently for that reason alone.
        """
        plate = Plate("Qualifying")

        self.quali_minutes = QSpinBox()
        self.quali_minutes.setRange(0, 120)
        self.quali_minutes.setSuffix(" min")
        # **Zero is "nobody said", and the plan treats it that way.** A lobby
        # that does not state a qualifying length is a real state; guessing one
        # would put a run count on the board that nothing supports.
        self.quali_minutes.setSpecialValueText("not stated")
        block_wheel(self.quali_minutes)
        plate.body.addWidget(Field(
            "Session", self.quali_minutes,
            hint="Left unstated it plans one run and says so"))

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.quali_button = MarkButton("Plan qualifying", compact=True)
        self.quali_button.clicked.connect(self.qualifying_requested.emit)
        row.addWidget(self.quali_button)
        row.addStretch(1)
        plate.body.addLayout(row)

        self.quali_body = QVBoxLayout()
        self.quali_body.setContentsMargins(0, 0, 0, 0)
        self.quali_body.setSpacing(0)
        plate.body.addLayout(self.quali_body)

        self.quali_empty = EmptyState(
            "No qualifying plan.",
            needs=("a measured fuel burn for this car",))
        self.quali_body.addWidget(self.quali_empty)
        return plate

    def qualifying_minutes(self) -> float | None:
        value = self.quali_minutes.value()
        return float(value) if value > 0 else None

    def clear_qualifying(self) -> None:
        while self.quali_body.count():
            item = self.quali_body.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self.quali_empty:
                widget.deleteLater()
        self.quali_body.addWidget(self.quali_empty)
        self.quali_empty.setVisible(True)

    def show_qualifying(self, plan) -> None:
        """Render one `race.qualifying_plan.QualifyingPlan`.

        **The refusals are rendered as prose, not as an empty panel.** A plan
        the app declined to make because nothing measured the burn is a
        different thing from one it has not been asked for, and an empty plate
        says the second when it means the first.
        """
        self.clear_qualifying()
        self.quali_empty.setVisible(False)

        if not plan.usable:
            for reason in plan.refusals:
                self.quali_body.addWidget(BodyLabel(
                    reason[0].upper() + reason[1:] + ".", size=13,
                    colour=theme.STENCIL_DIM))
            return

        lines = plan.as_text()
        # The shape of the session: runs, flying laps, laps of fuel. Derived -
        # the app worked it out from the burn and the clock.
        self.quali_body.addWidget(BodyLabel(lines[0], colour=theme.DERIVED))
        # **The instruction, in the register the driver acts on.** "Fuel to 28
        # litres" is what he types into the car, and it is the one line here
        # that becomes a setting rather than a fact.
        fuel = Measured(f"{plan.fuel_l:.0f} L", size=23, bold=True,
                        colour=theme.DERIVED)
        fuel.setContentsMargins(0, 6, 0, 0)
        self.quali_body.addWidget(fuel)
        for line in lines[2:]:
            self.quali_body.addWidget(BodyLabel(line, size=13,
                                                colour=theme.STENCIL_DIM))

        heading = StencilLabel("What it assumed", size=11, tracking=12.0,
                               colour=theme.STENCIL_DIM)
        heading.setContentsMargins(0, 10, 0, 2)
        self.quali_body.addWidget(heading)
        for note in plan.assumptions:
            # **One line each, elided, with the whole thing as a tooltip.**
            # These are full sentences by design - the product's principle is
            # that nothing derived is presented as measured, so every figure
            # states what it rests on - but wrapped, twelve of them are a wall
            # of identical dim prose that buries the answer they qualify.
            # `HintLabel` is this world's existing answer to exactly that, and
            # it is why field hints elide rather than wrap.
            #
            # A note that says the plan is SHORT is a warning rather than a
            # caveat: the tank cannot hold what the runs want, and that one is
            # not something to make him hover to read.
            text = note[0].upper() + note[1:] + "."
            if "SHORT" in note:
                self.quali_body.addWidget(BodyLabel(
                    text, size=13, colour=theme.WARNING))
                continue
            self.quali_body.addWidget(HintLabel(text, size=13))

    def _footer(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.footer_note = BodyLabel("", size=13, colour=theme.STENCIL_DIM)
        row.addWidget(self.footer_note, 1)
        self.approve_button = MarkButton("Approve for the race", primary=True)
        self.approve_button.setEnabled(False)
        self.approve_button.clicked.connect(self._on_approve)
        row.addWidget(self.approve_button)
        return row

    # ------------------------------------------------------------------ data

    def _on_approve(self) -> None:
        """Approve whichever card is chosen, by the route that fits it."""
        if self._chosen_loaded is not None:
            self.approve_loaded_requested.emit(self._chosen_loaded)
            return
        if self._cards:
            self.approve_requested.emit(self._chosen)

    def _on_save(self) -> None:
        """The primary action, under the name the shell looks for.

        `Ctrl+S` / `Ctrl+Return` probes every screen for `_on_save`,
        `_on_export` or `_on_generate` and then special-cases two by identity.
        Strategy answered to none of them, so the key was silently inert on
        the screen whose primary action is approving the race plan.
        """
        self._on_approve()

    def show_loaded(self, rows) -> None:
        """Plans written elsewhere and loaded in, above the app's own.

        `rows` are stored strategy rows carrying a `handover`. They are kept in
        their own layout rather than merged into the optimiser's list, because
        merging them would put a plan nobody costed into a ranking - and the
        ranking is the only thing "+1.4 s" means.
        """
        self._clear(self.loaded_layout)
        self._loaded_cards.clear()
        # **Disarmed with the cards.** It survived them: the layout emptied,
        # nothing rendered as chosen, Approve stayed enabled, and pressing it
        # emitted the id of a card that was no longer on screen. A selection
        # that is invisible and live at the same time is the worst of both.
        if not any(row.get("id") == self._chosen_loaded for row in rows or ()):
            self._chosen_loaded = None
        for row in rows or ():
            card = LoadedCard(row["id"], row)
            card.selected.connect(self._on_loaded_selected)
            self.loaded_layout.addWidget(card)
            self._loaded_cards.append(card)
        if rows:
            # A rule that names the division, the way a `Plate`'s label is
            # struck through its own edge. Without it two groups of cards read
            # as one list with an unexplained gap.
            self.loaded_layout.addWidget(StencilLabel(
                "The app's own, for comparison", size=11,
                colour=theme.STENCIL_DIM, tracking=14.0))
        self._sync_selection()
        self.approve_button.setEnabled(
            bool(self._cards) or bool(self._loaded_cards))

    def _on_loaded_selected(self, strategy_id: int) -> None:
        self._chosen = None
        self._chosen_loaded = strategy_id
        self._sync_selection()

    def show_plans(self, plans, evidence, *, approved_index: int | None = None,
                   timed: bool = False) -> None:
        self._clear(self.plan_layout, keep_layouts=True)
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
            # After the loaded sub-layout, which is item 0.
            self.plan_layout.insertWidget(index + 1, card)
            self._cards.append(card)
        self.plan_layout.addStretch(1)

        self._show_evidence(evidence)
        # **A loaded plan keeps the selection.** Rebuilding the app's own
        # list is not a reason to move the driver off a plan he chose from the
        # desk - and defaulting back to card 0 would silently re-select the
        # optimiser's fastest, which is the plan the load exists to replace.
        if self._chosen_loaded is None:
            self._chosen = 0 if approved_index is None else approved_index
        self._sync_selection()
        self.approve_button.setEnabled(
            bool(plans) or bool(self._loaded_cards))

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

    def _clear(self, layout, *, keep_layouts: bool = False) -> None:
        """Empty a layout, keeping the empty-state block alive.

        It is detached rather than destroyed, because a rebuild that produces
        no plans has to say so again - and a deleted widget cannot.

        `keep_layouts` puts back any nested layout it takes out. The plan
        plate holds the loaded cards in a sub-layout, and rebuilding the app's
        own plans must not throw away a plan the driver loaded from the desk -
        a `takeAt` that drops the layout leaves those cards parented to
        nothing and they vanish on the next build.
        """
        keep = (getattr(self, "plan_empty", None),
                getattr(self, "evidence_empty", None))
        nested = []
        while layout.count():
            entry = layout.takeAt(0)
            if entry.layout() is not None:
                if keep_layouts:
                    nested.append(entry.layout())
                continue
            widget = entry.widget()
            if widget is None or widget in keep:
                continue
            widget.deleteLater()
        for sub in nested:
            layout.insertLayout(0, sub)

    def _on_selected(self, index: int) -> None:
        self._chosen_loaded = None
        self._chosen = index
        self._sync_selection()

    def _sync_selection(self) -> None:
        """One selection across both groups.

        They are two lists on one plate and the driver approves ONE plan, so
        choosing in either has to clear the other - otherwise two cards read
        as chosen and the button acts on whichever branch happens to win.
        """
        for card in self._cards:
            card.setChosen(self._chosen_loaded is None
                           and card.index == self._chosen)
        for loaded in self._loaded_cards:
            loaded.setChosen(loaded.strategy_id == self._chosen_loaded)

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
