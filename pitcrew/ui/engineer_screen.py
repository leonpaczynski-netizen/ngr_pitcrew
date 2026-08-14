"""Race Engineer — three prompts, assembled from what the app already knows.

This screen is the whole reason the HTML tool could be retired. Everything on
the left that used to be a text box the driver retyped — car, circuit, event
format, multipliers, compounds, assists, the sheet as run, laps, best lap,
fuel, the strategy and every call — is now read out of the store. What is left
is the half the app genuinely cannot know: what the car felt like.

So the screen is split along that line, and the line is the design. The left
column is perception, and every control on it is crayon, because the driver
declared it. The right column is the assembled prompt, and it is presented as
a read-only block: it is not a form, it is the thing being sent. The reply box
underneath is where the loop closes.

There is no advice anywhere on this screen. It states what happened and asks.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QFrame,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pitcrew.prompts.build import BRIEF, KIND_LABELS, OUTCOME, REFINEMENT
from pitcrew.prompts.report import DriverReport
from pitcrew.store import catalogs
from pitcrew.ui import theme
from pitcrew.ui.widgets import (
    BodyLabel,
    Field,
    MarkButton,
    Plate,
    StencilLabel,
    block_wheel,
)

# When each prompt is written, in the driver's terms rather than the code's.
KIND_WHEN = {
    BRIEF: "Before a new car and circuit are run",
    REFINEMENT: "After a practice run",
    OUTCOME: "After a completed race",
}

# Perception vocabularies. These are the driver's own words for things the
# stream has no channel for, kept as fixed choices so the same feeling is
# reported the same way twice and the knowledge base can compare sessions.
COSTS_MOST = ("", "Slow corners", "Medium-speed corners", "Fast corners",
              "Heavy braking zones", "Kerbs and elevation",
              "Everywhere, consistently", "Only when I push for a lap",
              "Only late in a stint")
BALANCE_DRIFT = ("", "Held steady", "Migrated to understeer",
                 "Migrated to oversteer",
                 "Went off a cliff rather than fading",
                 "Fine until traffic / dirty air", "Too few laps to say")
TYRE_STATE = ("", "Still green", "Working, plenty left", "Past peak but usable",
              "Gone — dropping a second a lap", "One corner gone, rest fine")
PRIORITY = ("", "Fix the problem, keep everything that works",
            "Race pace and tyre life", "One-lap qualifying pace",
            "Drivability — I need to be able to lean on it",
            "Front-end confidence on entry",
            "Rear stability — it's costing me commitment",
            "Fuel and stint length")
CONDITIONS = ("", "Dry, representative", "Dry, cooler than the race",
              "Dry, hotter than the race", "Damp / drying", "Wet", "Night")
CLEAN_AIR = ("", "Clean air, no tow", "Best lap was in a tow",
             "Traffic all session", "Mixed — see notes")

NONE_STANDS_OUT = "— none stands out —"


def _narrow_combo() -> QComboBox:
    """A combo whose collapsed width is not set by its longest option.

    Qt sizes a combo box to fit its widest item, and these hold whole
    sentences — left alone, one of them makes the pane wider than the screen
    gives it and every label in the column gets clipped. The popup is sized
    separately so the choices themselves stay readable.
    """
    combo = QComboBox()
    combo.setSizeAdjustPolicy(
        QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    combo.setMinimumContentsLength(14)
    combo.view().setTextElideMode(Qt.TextElideMode.ElideNone)
    block_wheel(combo)
    return combo


class EngineerScreen(QWidget):
    """Compose a prompt, copy it, and keep what came back."""

    generate_requested = pyqtSignal(str)          # kind
    copy_requested = pyqtSignal()
    reply_saved = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # None, not BRIEF. The constructor calls `set_kind(BRIEF)` below, and
        # that call has to do its work - it is what lays the screen out. With
        # the field pre-set to the same value the no-op guard swallowed it and
        # the plates kept their designer visibility.
        self._kind: str | None = None
        self._symptom_boxes: list[QCheckBox] = []
        self._kind_buttons: dict[str, MarkButton] = {}
        self._build()
        self.set_kind(BRIEF)

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 0)
        page.setSpacing(theme.GAP_WIDE)

        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(StencilLabel("Race Engineer", size=theme.TITLE_PX,
                                      colour=theme.STENCIL, tracking=6.0))
        header.addWidget(BodyLabel(
            "The app fills in everything it knows. You supply what it cannot: "
            "what the car felt like.", colour=theme.STENCIL_DIM))
        page.addLayout(header)
        page.addWidget(self._kind_bar())

        columns = QHBoxLayout()
        columns.setSpacing(theme.GAP_WIDE)
        # The left pane is the wider one: its width is set by the longest
        # symptom in the vocabulary, and a clipped symptom is a symptom the
        # driver cannot tell from its neighbour. The prompt on the right is
        # monospace and scrolls.
        columns.addWidget(self._left_column(), 6)
        columns.addWidget(self._right_column(), 5)
        page.addLayout(columns, 1)
        page.addWidget(self._footer())

    def _kind_bar(self) -> QWidget:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.GAP)
        for kind in (BRIEF, REFINEMENT, OUTCOME):
            button = MarkButton(KIND_LABELS[kind])
            button.setToolTip(KIND_WHEN[kind])
            button.clicked.connect(lambda _=False, k=kind: self.set_kind(k))
            self._kind_buttons[kind] = button
            row.addWidget(button)
        self.kind_note = BodyLabel("", size=13, colour=theme.CHALK)
        row.addWidget(self.kind_note, 1)
        return holder

    # ----------------------------------------------------------- left column

    def _left_column(self) -> QWidget:
        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        # AsNeeded, not AlwaysOff. Hiding the bar did not stop the
        # content overflowing below 1600 wide - it only stopped it
        # being reachable.
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        inner = QWidget()
        stack = QVBoxLayout(inner)
        stack.setContentsMargins(0, 0, 4, 0)
        stack.setSpacing(theme.GAP_WIDE)

        self.knows_plate = Plate("What the app is filling in")
        # Not blank. This plate is the screen's whole argument - the division
        # between what the app knows and what only he does, visible before
        # anything is generated - and it rendered as an empty bordered box on
        # the one run where that division has never been explained.
        self.knows_note = BodyLabel(
            "Nothing yet. Save an event on the Event screen and this fills in "
            "with the car, the circuit and what has been measured.",
            size=14, colour=theme.STENCIL_DIM)
        self.knows_plate.body.addWidget(self.knows_note)
        stack.addWidget(self.knows_plate)

        self.symptoms_plate = self._symptoms_plate()
        stack.addWidget(self.symptoms_plate)
        self.perception_plate = self._perception_plate()
        stack.addWidget(self.perception_plate)
        self.race_plate = self._race_plate()
        stack.addWidget(self.race_plate)
        stack.addWidget(self._notes_plate())
        stack.addStretch(1)

        scroller.setWidget(inner)
        column.addWidget(scroller, 1)
        return holder

    def _symptoms_plate(self) -> Plate:
        plate = Plate("What the car did")
        plate.body.addWidget(BodyLabel(
            "Tick everything the car actually did. These are read literally — "
            "they are the shared vocabulary, so do not soften them.",
            size=13, colour=theme.STENCIL_DIM))

        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP)
        # Two columns, not three: the longest symptom runs to forty characters
        # and a third column pushes the plate wider than the pane, which
        # silently clips the end of every label.
        for index, (group, items) in enumerate(catalogs.symptom_groups()):
            column = QVBoxLayout()
            column.setSpacing(0)
            column.addWidget(StencilLabel(group, size=11, tracking=12.0))
            for symptom in items:
                box = QCheckBox(symptom)
                box.toggled.connect(self._refresh_worst)
                self._symptom_boxes.append(box)
                column.addWidget(box)
            column.addStretch(1)
            holder = QWidget()
            holder.setLayout(column)
            grid.addWidget(holder, index // 2, index % 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        plate.body.addLayout(grid)

        self.worst = _narrow_combo()
        plate.body.addWidget(Field(
            "Biggest single limitation", self.worst,
            hint="Pick from what you ticked above."))
        self._refresh_worst()
        return plate

    def _perception_plate(self) -> Plate:
        plate = Plate("How it changed, and what it cost")
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP)

        self.costs_most = self._choices(COSTS_MOST)
        self.balance_drift = self._choices(BALANCE_DRIFT)
        self.tyre_state = self._choices(TYRE_STATE)
        self.priority = self._choices(PRIORITY)
        self.conditions = self._choices(CONDITIONS)
        self.clean_air = self._choices(CLEAN_AIR)
        self.unrepresentative = QLineEdit()
        self.unrepresentative.setPlaceholderText(
            "e.g. rejoined behind a spun car twice")

        grid.addWidget(Field("Where it costs me most", self.costs_most), 0, 0)
        grid.addWidget(Field("Balance over the run", self.balance_drift), 0, 1)
        grid.addWidget(Field("Tyre state at the end", self.tyre_state), 1, 0)
        grid.addWidget(Field("Priority for the revision", self.priority), 1, 1)
        grid.addWidget(Field("Track conditions", self.conditions), 2, 0)
        # Hints stay short on purpose: a Field's hint does not wrap, so a long
        # one sets a wide minimum for the whole plate and pushes the pane out
        # past its scroll area, which clips every label in it.
        grid.addWidget(Field(
            "Traffic and tow", self.clean_air,
            hint="GT7 sends no proximity."), 2, 1)
        grid.addWidget(Field("What made this unrepresentative",
                             self.unrepresentative), 3, 0, 1, 2)
        plate.body.addLayout(grid)
        return plate

    def _race_plate(self) -> Plate:
        plate = Plate("The race itself")
        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP)
        self.result = QLineEdit()
        self.result.setPlaceholderText("P3 of 14 — lost a place at the stop")
        self.best_quali = QLineEdit()
        self.best_quali.setPlaceholderText("1:33.412")
        grid.addWidget(Field(
            "Result, in your words", self.result,
            hint="The position itself comes off the stream."), 0, 0)
        grid.addWidget(Field(
            "Best qualifying lap", self.best_quali,
            hint="No quali session is recorded."), 0, 1)
        plate.body.addLayout(grid)
        return plate

    def _notes_plate(self) -> Plate:
        plate = Plate("In your own words")
        plate.body.addWidget(BodyLabel(
            "The most valuable field on the screen. Say it the way you would "
            "say it over the radio — it goes into the prompt verbatim and is "
            "read as primary evidence.", size=13, colour=theme.STENCIL_DIM))
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText(
            "What the car did, where you lost confidence, what you changed "
            "mid-run and whether it helped.")
        # A floor, not a fixed height. 110 is comfortable on a big monitor
        # and it was also the smallest this pane could ever be; on the 501px
        # display the two text areas alone put the footer off the bottom.
        self.notes.setMinimumHeight(70)
        plate.body.addWidget(self.notes)
        return plate

    def _choices(self, options) -> QComboBox:
        combo = _narrow_combo()
        for option in options:
            combo.addItem(option or "—", option or None)
        return combo

    # ---------------------------------------------------------- right column

    def _right_column(self) -> QWidget:
        # Scrolled, like the left one. It holds two text areas and their
        # plates, which together set a floor taller than the smallest display
        # this app runs on - and the left column got a scroller while the
        # right, holding the thing you came here to copy, did not.
        outer = QScrollArea()
        outer.setWidgetResizable(True)
        outer.setFrameShape(QFrame.Shape.NoFrame)
        outer.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        holder = QWidget()
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(theme.GAP_WIDE)

        plate = Plate("The prompt")
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        # **Not crayon.** `QPalette.Text` is the declared ink, and this box
        # holds the prompt the *app* composed - so the app's own output was
        # rendering in the register that means the driver typed it. It is
        # stencil: assembled from measurements, and read rather than edited.
        _palette = self.output.palette()
        _palette.setColor(_palette.ColorRole.Text, QColor(theme.STENCIL))
        self.output.setPalette(_palette)
        self.output.setPlaceholderText(
            "Generate, then paste this into the knowledge base session.")
        self.output.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.output.setMinimumHeight(80)
        plate.body.addWidget(self.output, 1)

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.output_note = BodyLabel("Nothing generated yet.", size=13,
                                     colour=theme.STENCIL_DIM)
        row.addWidget(self.output_note, 1)
        # Generate is what you press on arrival; Copy is dead until there is
        # something to copy. The screen shipped with Copy as the primary and
        # disabled, so the only filled button on it did nothing and the one
        # you needed was drawn as secondary.
        generate = MarkButton("Generate", primary=True)
        self.generate_button = generate
        generate.clicked.connect(
            lambda: self.generate_requested.emit(self._kind))
        row.addWidget(generate)
        self.copy_button = MarkButton("Copy")
        self.copy_button.clicked.connect(self.copy_requested.emit)
        self.copy_button.setEnabled(False)
        row.addWidget(self.copy_button)
        plate.body.addLayout(row)
        column.addWidget(plate, 3)

        reply = Plate("What came back")
        reply.body.addWidget(BodyLabel(
            "Paste the whole reply here. It is filed against the prompt that "
            "asked for it, and any setup sheets in it are loaded straight "
            "onto the Event screen — check them there and save.",
            size=13, colour=theme.STENCIL_DIM))
        self.reply = QPlainTextEdit()
        self.reply.setPlaceholderText("Paste the knowledge base's reply…")
        self.reply.setMinimumHeight(60)
        reply.body.addWidget(self.reply, 1)

        reply_row = QHBoxLayout()
        reply_row.setSpacing(theme.GAP)
        self.reply_note = BodyLabel("", size=13, colour=theme.STENCIL_DIM)
        reply_row.addWidget(self.reply_note, 1)
        self.save_reply = MarkButton("File reply")
        self.save_reply.clicked.connect(
            lambda: self.reply_saved.emit(self.reply.toPlainText()))
        self.save_reply.setEnabled(False)
        reply_row.addWidget(self.save_reply)
        reply.body.addLayout(reply_row)
        column.addWidget(reply, 2)
        outer.setWidget(holder)
        return outer

    def _footer(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(52)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, theme.GAP, 0, theme.GAP)
        self.footer_note = BodyLabel("", size=13, colour=theme.STENCIL_DIM)
        row.addWidget(self.footer_note, 1)
        return bar

    # ---------------------------------------------------------------- state

    def set_kind(self, kind: str) -> None:
        # Clicking the kind already selected used to run the whole method,
        # which ends by clearing the output - so reaching for Copy and
        # clipping the button beside it threw the generated prompt away on a
        # click that should have done nothing.
        if kind == self._kind:
            return
        self._kind = kind
        for name, button in self._kind_buttons.items():
            button.set_primary(name == kind)
        self.kind_note.setText(KIND_WHEN.get(kind, ""))
        # A setup brief is written before anything has been run, so there is
        # no session to report on: asking for symptoms there would invite an
        # answer about a different session.
        self.symptoms_plate.setVisible(kind != BRIEF)
        self.perception_plate.setVisible(kind != BRIEF)
        self.race_plate.setVisible(kind == OUTCOME)
        self.output.clear()
        self.copy_button.setEnabled(False)
        self.output_note.setText("Nothing generated yet.")
        self.output_note.set_ink(theme.STENCIL_DIM)

    def kind(self) -> str:
        return self._kind

    def _refresh_worst(self) -> None:
        """The biggest limitation can only be one of the ticked symptoms."""
        ticked = [box.text() for box in self._symptom_boxes if box.isChecked()]
        current = self.worst.currentData()
        self.worst.blockSignals(True)
        self.worst.clear()
        self.worst.addItem(NONE_STANDS_OUT if ticked
                           else "— tick symptoms above first —", None)
        for symptom in ticked:
            self.worst.addItem(symptom, symptom)
        if current in ticked:
            self.worst.setCurrentIndex(ticked.index(current) + 1)
        self.worst.blockSignals(False)

    def clear_report(self) -> None:
        """Empty the perception fields for a new session.

        Nothing on this screen ever reset. After Generate, Copy and File
        reply, everything stayed exactly as typed - so the next session began
        by ticking two new symptoms on top of last week's eleven, and the
        knowledge base received last week's perception as this week's primary
        evidence. That is the product's own first principle inverted.
        """
        for box in self._symptom_boxes:
            box.setChecked(False)
        for combo in (self.costs_most, self.balance_drift, self.tyre_state,
                      self.priority, self.conditions, self.clean_air):
            combo.setCurrentIndex(0)
        self.notes.clear()
        self.result.clear()
        self.unrepresentative.clear()
        self.best_quali.clear()

    def report(self) -> DriverReport:
        """Everything the driver declared, and nothing else."""
        return DriverReport(
            symptoms=tuple(box.text() for box in self._symptom_boxes
                           if box.isChecked()),
            biggest_limitation=self.worst.currentData() or "",
            costs_most_where=self.costs_most.currentData() or "",
            balance_drift=self.balance_drift.currentData() or "",
            tyre_state_at_end=self.tyre_state.currentData() or "",
            priority=self.priority.currentData() or "",
            conditions=self.conditions.currentData() or "",
            unrepresentative=self.unrepresentative.text().strip(),
            clean_air=self.clean_air.currentData() or "",
            best_quali_lap=self.best_quali.text().strip(),
            result=self.result.text().strip(),
            notes=self.notes.toPlainText().strip(),
            session_kind="race" if self._kind == OUTCOME else "practice",
        )

    def show_prompt(self, text: str, *, warnings=()) -> None:
        self.output.setPlainText(text)
        # The run ends on the primary. Once a prompt exists, copying it is
        # the end of the work on this screen and Generate is behind you.
        self.copy_button.setEnabled(bool(text))
        self.copy_button.set_primary(bool(text))
        self.generate_button.set_primary(not text)
        self.save_reply.setEnabled(bool(text))
        if warnings:
            self.output_note.setText("Generated, without: "
                                     + "; ".join(warnings))
            self.output_note.set_ink(theme.WARNING)
        else:
            self.output_note.setText(
                f"Generated · {len(text.splitlines())} lines. "
                "Everything it could fill in, it filled in.")
            self.output_note.set_ink(theme.CHALK)

    def set_context_note(self, text: str) -> None:
        self.knows_note.setText(text)

    def note(self, text: str, *, warn: bool = False) -> None:
        self.footer_note.setText(text)
        self.footer_note.set_ink(theme.WARNING if warn else theme.CHALK)

    def note_reply(self, text: str, *, warn: bool = False) -> None:
        self.reply_note.setText(text)
        self.reply_note.set_ink(theme.WARNING if warn else theme.CHALK)

    def prompt_text(self) -> str:
        return self.output.toPlainText()
