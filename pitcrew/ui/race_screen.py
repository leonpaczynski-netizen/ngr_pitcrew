"""Race — the pit wall.

**The premise changed on 5 Sep 2026: he is out of VR and can see this while
he drives.** For the whole life of this file he could not — he was in a PSVR2
headset, so nothing here could be a live instrument and the engineer's job was
done out loud. That is why the numbers that decide the race were a 15px run of
dots shared with the Practice screen's session totals: nobody could read them
anyway.

They can be read now, so the screen is built the way a pit board is. The four
figures that decide what he does next are sized to be read at a glance from
the wheel, with the box-in lap the largest thing on the screen because it is
the only one that says *do something*. The plan sits beside them as one object
— stints, stops, compounds, and which stint he is in — rather than as numbers
to reassemble.

**The engineer still speaks, and that is still the primary channel.** A glance
is a glance; a call in the ear does not need one. What the screen adds is the
ability to check the call against the numbers it came from without waiting for
the flag.

Below that: the last thing said, and the log of everything said with its
reason and its confidence. The log is the point after the race — a call the
driver acted on and a call he ignored are both evidence about the model, and
the export carries them.
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
    BigReading,
    Field,
    BodyLabel,
    Declared,
    EmptyState,
    MarkButton,
    Measured,
    Plate,
    PlanSpine,
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

        # **Beside what it qualifies, not 1,300px away at the far edge.**
        # Confidence was a right-aligned column, so on a wide screen the word
        # that says whether a call was measured or modelled sat across an
        # empty gulf from the call itself - and after the race, reading the
        # log is the whole point of keeping it. It reads as a gutter now:
        # lap, then how sure, then what was said.
        badge = StencilLabel(call.confidence, size=10, tracking=14.0,
                             colour=CONFIDENCE_INK.get(call.confidence,
                                                       theme.STENCIL_DIM))
        badge.setFixedWidth(64)
        badge.setToolTip(
            "How sure the engineer was. A modelled call and a measured one "
            "must not look the same afterwards any more than during.")
        row.addWidget(badge)

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
        # **What the engineer is actually going to run, before the green.**
        # The subtitle cannot carry it: `set_status` owns that line and
        # overwrites it with the last call the moment the race starts, so the
        # plan was only ever visible as the word "armed". A plan that cannot
        # be read is a plan that cannot be checked, and the one thing worth
        # catching on the grid is the engineer holding a different race to the
        # one about to be driven.
        self.plan_line = BodyLabel("", size=13, colour=theme.CHALK)
        titles.addWidget(self.plan_line)
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

        page.addWidget(self._pit_board())
        page.addWidget(self._radio_plate())
        page.addWidget(self._log_plate(), 1)

    def _pit_board(self) -> QWidget:
        """The four figures that decide the race, at a size you can read.

        **The driver is out of VR and can see this screen while he drives.**
        That is a change of premise, not of taste: this file's own docstring
        said nothing here is a live instrument, because nothing here could be
        seen. It can be seen now, so the numbers that decide what he does next
        get the scale they always warranted.

        They were a `SpecLine` - a 15px run of dots shared with the Practice
        screen's session totals - and `Box in 3` is the highest-consequence
        number this product emits. At three metres, glancing up from a wheel,
        there is time to read one thing.

        The registers do the rest of the work and are not decoration here:
        lap and position came off the stream and are `STENCIL`; fuel in hand
        and the box-in lap are `DERIVED`, because a laps-of-fuel figure is
        litres divided by a burn rate that is *planned* until three laps are
        in. One of these is measured and one is a model, and on the surface
        used at racing speed they must not look alike.
        """
        board = QWidget()
        row = QHBoxLayout(board)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.GAP_WIDE * 2)

        # Box in is the biggest thing on the screen, because it is the only
        # one that says do something.
        # **Sized against the smallest display he owns, not against taste.**
        # 1280x800 at 150% reports 501 logical pixels of height less the rail,
        # and `test_every_screen_fits_the_smallest_display_he_owns` holds every
        # screen to it - a guard that exists because Save once sat below the
        # fold on Settings with no bar to reach it.
        #
        # **Measured with the real faces, which matters more than it sounds.**
        # These were first sized against a run where every `StencilLabel` in
        # the app was painting at 15px instead of the 10-13 it asked for - see
        # `widgets.StencilLabel` - so the labels around these figures were
        # inflated and the board had to shrink to 60/44 to fit. With the
        # cascade fixed the surrounding type is the size it always claimed to
        # be, and the readings can have the room back: 68/48 asks 499px
        # against the 501 floor, where 78/56 asks 509 and does not fit.
        self.box_in = BigReading("Box in", size=68, ink=theme.DERIVED)
        self.fuel_left = BigReading("Fuel in hand", size=48, ink=theme.DERIVED)
        self.lap_now = BigReading("Lap", size=48)
        self.position = BigReading("Position", size=48)
        for reading in (self.box_in, self.fuel_left, self.lap_now,
                        self.position):
            row.addWidget(reading, 0, Qt.AlignmentFlag.AlignBottom)
        row.addStretch(1)

        # The plan, as one object rather than four numbers to reassemble.
        spine = QVBoxLayout()
        spine.setSpacing(4)
        spine.addWidget(StencilLabel("The plan", size=11,
                                     colour=theme.STENCIL_DIM, tracking=14.0))
        self.spine = PlanSpine()
        self.spine.setMinimumWidth(360)
        spine.addWidget(self.spine)
        row.addLayout(spine, 1)
        return board

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

    def set_plan(self, strategy: dict | None) -> None:
        """Show the approved plan, or say plainly that there is none.

        Everything here is read straight off the stored plan - the same
        `plan_json` the coordinator arms from - so what is on the screen is
        what will be run rather than a second rendering of the same idea.
        """
        if not strategy:
            self.plan_line.setText(
                "No plan approved — the engineer will call fuel only.")
            self.plan_line.setStyleSheet(
                f"color: {theme.STENCIL_DIM};background: transparent;")
            # An empty spine draws a bare rule rather than nothing, so the
            # absence of a plan is visible in the place a plan would be.
            self.spine.setPlan([])
            return
        plan = strategy.get("plan") or {}
        stints = plan.get("stints") or []
        # The same stints the line below spells out in words, as one object.
        self.spine.setPlan([st.get("laps") for st in stints],
                           [st.get("compound") for st in stints])
        stops = plan.get("stops")
        parts: list[str] = []
        if stops is not None:
            parts.append(f"{stops} stop" if stops == 1 else f"{stops} stops")
        pit_laps = [str(lap) for lap in (plan.get("pit_laps") or [])]
        if pit_laps:
            word = "box lap" if len(pit_laps) == 1 else "box laps"
            parts.append(f"{word} {', '.join(pit_laps)}")
        if stints:
            parts.append(" + ".join(str(st.get("laps", "?")) for st in stints)
                         + " laps")
            compounds = [st.get("compound") for st in stints]
            if any(compounds):
                parts.append(" → ".join(c or "?" for c in compounds))
            fuel = [st.get("fuel_l") for st in stints]
            if any(f is not None for f in fuel):
                parts.append(" + ".join(
                    f"{f:.0f} L" if f is not None else "? L" for f in fuel))
        # **The constraint is the half of the plan that explains it.** "Fuel"
        # and "tyre" are different races, and which one binds is the first
        # thing to check against the evidence he actually has.
        binding = plan.get("binding_constraint")
        if binding == "evidence":
            # Spelled out because "evidence-limited" on its own reads like a
            # measurement, and it is the opposite of one: the tyre and the
            # tank both allowed more, and the cap is only how far anyone has
            # been. He is about to decide whether to trust the stop count.
            parts.append("evidence-limited (nothing has run longer)")
        elif binding:
            parts.append(f"{binding}-limited")
        label = strategy.get("label")
        head = f"{label}: " if label and parts and label not in parts[0] else ""
        self.plan_line.setText(head + " · ".join(parts) if parts
                               else "A plan is approved but carries no stints.")
        self.plan_line.setStyleSheet(
            f"color: {theme.CHALK};background: transparent;")

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
        """The pit board, from whatever the coordinator knows this lap.

        Every figure is set through `BigReading.setValue`, which renders
        `None` struck rather than as a zero. That is not a formality here:
        a race with no plan armed has no box-in lap, and a `0` on this board
        reads as *box now* - the most expensive misreading available on this
        screen.
        """
        lap = snapshot.get("lap")
        total = snapshot.get("lapsTotal")
        self.lap_now.setValue(
            None if lap is None else (f"{lap}/{total}" if total else str(lap)))
        self.position.setValue(
            f"P{snapshot['position']}" if snapshot.get("position") else None)

        # **Derived, like the box-in beside it.** Litres in the tank is
        # measured; laps of fuel is `fuel_l / fuel_per_lap_l`, and that rate
        # is the *planned* burn until three laps are in and the median of
        # observed burns after. A model output and a stream reading may not
        # wear the same ink on the surface used at racing speed.
        fuel = snapshot.get("lapsOfFuel")
        self.fuel_left.setValue(None if fuel is None else f"{fuel:.1f}")

        # **A stop that is overdue says so.** This was `max(0, to_stop)`, and
        # that is CLAUDE.md rule 9 on the highest-consequence number the app
        # emits: a plan he is two laps past reported as `0`, which reads as
        # "box now" and is a different instruction from "you are two laps
        # late". The clamp turned the more urgent of the two into the less
        # urgent one, and nothing downstream could tell them apart.
        to_stop = snapshot.get("lapsToStop")
        if to_stop is None:
            self.box_in.setValue(None)
        elif to_stop < 0:
            self.box_in.setValue(f"{-int(to_stop)} LATE", ink=theme.WARNING)
            self.box_in.name.setText("OVERDUE")
        else:
            self.box_in.setValue(str(int(to_stop)))
            self.box_in.name.setText("BOX IN")

        # Where the car is on the plan. `None` before the green: nobody is on
        # the spine yet, and the plan is still worth reading.
        self.spine.setLap(lap)
