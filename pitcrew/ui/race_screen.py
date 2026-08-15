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
    QComboBox,
    QCheckBox,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from pitcrew.race.calls import HIGH, LOW, MEDIUM
from pitcrew.ui import theme
from pitcrew.ui.widgets import (
    block_wheel,
    Field,
    BodyLabel,
    Declared,
    EmptyState,
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
        # Wrapped. A call's reason is a sentence by design, and an
        # unwrapped label makes its longest one the minimum width of the whole
        # log column - the same trap that pushed the Strategy screen to 6,268
        # px, fixed there and left here.
        instruction = BodyLabel(call.call, colour=theme.STENCIL, wrap=True)
        text.addWidget(instruction)
        if call.reason:
            text.addWidget(BodyLabel(call.reason, size=13,
                                     colour=theme.STENCIL_DIM, wrap=False))
        row.addLayout(text, 1)

        # Confidence is shown, not implied: a modelled call and a measured one
        # must not look the same after the race any more than during it.
        badge = StencilLabel(call.confidence, size=10, tracking=14.0,
                             colour=CONFIDENCE_INK.get(call.confidence,
                                                       theme.STENCIL_DIM))
        badge.setFixedWidth(70)
        badge.setAlignment(Qt.AlignmentFlag.AlignRight
                           | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(badge)


class RaceScreen(QWidget):
    """Arm the race, then watch what the engineer said."""

    start_requested = pyqtSignal()
    stop_requested = pyqtSignal()
    # Answering a re-plan offer without the microphone.
    replan_accepted = pyqtSignal()
    replan_declined = pyqtSignal()

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

        # **Three independent choices about how this race runs**, in the
        # same idiom the Practice screen uses for the same job. They were a
        # single checkbox, which could only say one of the three things.
        #
        # A rehearsal is a race in every mechanical sense - it makes real
        # stops under race conditions, which is the only place that evidence
        # comes from - and it is not the league race, so the post-mortem must
        # not read it as one.
        self.mode_picker = QComboBox()
        self.mode_picker.addItem("League race", False)
        self.mode_picker.addItem("Rehearsal vs AI", True)
        block_wheel(self.mode_picker)
        header.addWidget(Field("Running", self.mode_picker,
                               hint="A rehearsal is evidence, not the race"),
                         0, Qt.AlignmentFlag.AlignBottom)

        # Silent still does the work. Every call is computed, shown on this
        # screen and written into the outcome export - it simply is not
        # spoken, and push-to-talk is not armed. That is worth more than
        # switching the engineer off outright: a silent run still says what
        # it would have told him, and the post-mortem can compare that with
        # what he actually did.
        self.engineer_picker = QComboBox()
        self.engineer_picker.addItem("Speaks", True)
        self.engineer_picker.addItem("Silent", False)
        self.engineer_picker.setToolTip(
            "Silent still works out every call and logs it — it just does "
            "not say it, and push-to-talk stays off. Run one silent to see "
            "whether you reach the same decisions it does.")
        block_wheel(self.engineer_picker)
        header.addWidget(Field("Engineer", self.engineer_picker,
                               hint="Silent still logs every call"),
                         0, Qt.AlignmentFlag.AlignBottom)

        # Running without the plan is how you find out what the plan is
        # worth. The engineer falls back to fuel alone, which is what it does
        # when no plan has ever been approved.
        self.plan_picker = QComboBox()
        self.plan_picker.addItem("Approved plan", True)
        self.plan_picker.addItem("No plan", False)
        self.plan_picker.setToolTip(
            "Without the plan the engineer calls fuel only. Run one to find "
            "out what the plan is actually worth.")
        block_wheel(self.plan_picker)
        # `activated` fires only for a choice he made; `currentIndexChanged`
        # also fires when the app moves it. Without that distinction, forcing
        # the picker to "No plan" while none is approved would read as him
        # having chosen it, and approving one later would never move it back.
        self.plan_picker.activated.connect(
            lambda: setattr(self, "_plan_chosen_by_hand", True))
        self._plan_chosen_by_hand = False
        header.addWidget(Field("Strategy", self.plan_picker,
                               hint="Fuel calls only without one"),
                         0, Qt.AlignmentFlag.AlignBottom)

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
        self.last_reason = BodyLabel(
            "Nothing said yet. The engineer speaks once the race is armed "
            "and you cross the line.", colour=theme.STENCIL_DIM)
        plate.body.addWidget(self.last_reason)

        # Shown only while an offer is open. Push-to-talk stays the way to
        # answer at speed; this is the way to answer at all.
        self.offer_row = QWidget()
        offer = QHBoxLayout(self.offer_row)
        offer.setContentsMargins(0, theme.GAP, 0, 0)
        offer.setSpacing(theme.GAP)
        self.accept_button = MarkButton("Accept", primary=True)
        self.accept_button.clicked.connect(self.replan_accepted.emit)
        self.keep_button = MarkButton("Keep the plan")
        self.keep_button.clicked.connect(self.replan_declined.emit)
        offer.addWidget(self.accept_button)
        offer.addWidget(self.keep_button)
        offer.addStretch(1)
        self.offer_row.setVisible(False)
        plate.body.addWidget(self.offer_row)
        return plate

    def _log_plate(self) -> Plate:
        plate = Plate("Every call")
        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        # AsNeeded, not AlwaysOff. Hiding the bar did not stop the
        # content overflowing below 1600 wide - it only stopped it
        # being reachable.
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self.log = QWidget()
        self.log_layout = QVBoxLayout(self.log)
        self.log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_layout.setSpacing(0)
        self.log_empty = EmptyState(
            "No calls yet. The engineer speaks when the race is armed and "
            "you cross the line; everything he says lands here with its "
            "reason and its confidence, including calls you decline.")
        self.log_layout.addWidget(self.log_empty)
        self.log_layout.addStretch(1)
        scroller.setWidget(self.log)

        plate.body.addWidget(scroller, 1)
        return plate

    # ---------------------------------------------------------------- actions

    def rehearsal(self) -> bool:
        return bool(self.mode_picker.currentData())

    def engineer_speaks(self) -> bool:
        return bool(self.engineer_picker.currentData())

    def use_plan(self) -> bool:
        return bool(self.plan_picker.currentData())

    def set_plan_available(self, available: bool) -> None:
        """Grey the choice out when there is no plan to make it about.

        Offering "Approved plan" with none approved is a control that cannot
        do what it says - and the screen already says "No plan armed" in its
        subtitle, so the two would contradict each other.
        """
        index = self.plan_picker.findData(True)
        item = self.plan_picker.model().item(index)
        if item is not None:
            item.setEnabled(available)
        if not available:
            self.plan_picker.setCurrentIndex(self.plan_picker.findData(False))
        elif not self._plan_chosen_by_hand:
            # A plan exists and he has not said otherwise, so use it. This is
            # the state the screen was in before the choice existed.
            self.plan_picker.setCurrentIndex(index)

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
        self.log_empty.setVisible(False)
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
                                     colour=theme.STENCIL_DIM, wrap=False))
        text.addWidget(BodyLabel(said, colour=theme.CHALK, wrap=False))
        line.addLayout(text, 1)
        self.log_layout.insertWidget(0, row)

    def show_offer(self, verdict) -> None:
        """A re-plan on the table, until he accepts or keeps.

        **With buttons.** The only way to answer used to be push-to-talk, so
        with PTT off, the key misbound, or no keyboard hook on this machine -
        all three of which the Settings screen can report - the offer sat
        there as an unanswerable warning-coloured sentence with no timeout
        stated. He is not looking at the screen while driving, but he is
        between stints, and the alternative was a dead end.
        """
        self.last_call.setText(verdict.call())
        self.last_call.setStyleSheet(
            f"color: {theme.WARNING}; background: transparent;")
        self.last_reason.setText(f"{verdict.reason}. Say accept, or keep.")
        self.offer_row.setVisible(True)

    def hide_offer(self) -> None:
        self.offer_row.setVisible(False)

    def clear_log(self) -> None:
        while self.log_layout.count():
            item = self.log_layout.takeAt(0)
            if item.widget() and item.widget() is not self.log_empty:
                item.widget().deleteLater()
        self.log_empty.setVisible(True)
        self.log_layout.addWidget(self.log_empty)
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
            # **Derived, like the Box-in beside it.** Litres in the tank is
            # measured; laps of fuel is `fuel_l / fuel_per_lap_l`, and that
            # rate is the *planned* burn until three laps are in and the
            # median of observed burns after. One spec line was carrying a
            # model output and a stream reading in the same ink, on the
            # surface used at racing speed.
            self.spec.add("Fuel", f"{fuel:.1f} laps", derived=True)
        to_stop = snapshot.get("lapsToStop")
        if to_stop is not None:
            # The model worked this out. It is the highest-consequence
            # number the app emits and it used to wear the ink that means
            # "the driver typed this".
            self.spec.add("Box in", f"{max(0, to_stop)}", derived=True)
        if snapshot.get("nextCompound"):
            # The plan's next stint, not the stream's - nothing has gone on
            # the car yet.
            self.spec.add("Then", snapshot["nextCompound"], derived=True)
        self.spec.finish()
