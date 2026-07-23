"""EventSetupPage — describing a race, as a guided flow (single-system stage 3).

The classic Event Planner is one screen with eighteen controls, and it is the reason a
driver could not tell which of them actually mattered. This is not that screen rebuilt.

Four steps, one decision at a time, following the bouncing ball:

  1. **What are you racing?**  name, car, track — the only things with no sensible default
  2. **How long is it?**       laps or minutes, chosen by picking the format first
  3. **Any special rules?**    everything else, PRE-FILLED and folded away; the driver
                               opens it only if this event actually differs
  4. **Confirm**               the event read back as one plain sentence, then activate

Rules the page is held to (see docs/SINGLE_SYSTEM_MIGRATION.md §4):
one primary action per step; progress always visible; Back always available; validation
states the cause and the fix next to the field; nothing is asked that has a good default.

Pure presentation over ``services.event_setup`` — it validates nothing and saves nothing.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QCheckBox, QScrollArea, QFrame, QStackedWidget,
    QListWidget, QListWidgetItem,
)

from ui import ngr_theme as _t
from ui.components.cards import Card, SectionHeading
from ui.components.buttons import PrimaryActionButton, SecondaryActionButton
from services.event_setup import (
    DAMAGE_CHOICES, EventDraft, RACE_TYPES, WEATHER_CHOICES, DraftIssue,
)

STEPS: tuple = ("What are you racing?", "How long is it?", "Any special rules?", "Confirm")


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_LABEL}pt;")
    return lbl


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
    return lbl


def _input_qss() -> str:
    return (f"color: {_t.TEXT_HI}; background: {_t.CARBON_HI}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; "
            f"padding: 5px 10px; font-size: {_t.FS_LABEL}pt;")


class _Choice(QWidget):
    """Two or more big, obvious options — a format is a decision, not a dropdown."""

    chosen = pyqtSignal(str)

    def __init__(self, options: Sequence[tuple], parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(_t.SPACE_SM)
        self._buttons: dict = {}
        for key, label in options:
            btn = SecondaryActionButton(label)
            btn.setCheckable(True)
            btn.setMinimumHeight(_t.TOUCH_MIN_H + 8)
            btn.clicked.connect(lambda _=False, k=key: self._pick(k))
            self._buttons[key] = btn
            lay.addWidget(btn)
        lay.addStretch(1)
        self._current = ""

    def _pick(self, key: str) -> None:
        self.set_value(key)
        self.chosen.emit(key)

    def set_value(self, key: str) -> None:
        self._current = key
        for k, b in self._buttons.items():
            b.setChecked(k == key)
            b.setStyleSheet(
                (_t.primary_button_qss() if k == key else _t.secondary_button_qss())
                + f" QPushButton:focus {{ {_t.focus_ring_qss()} }}")

    def value(self) -> str:
        return self._current


class EventSetupPage(QWidget):
    """Create or edit an event, one question at a time."""

    #: The driver finished the flow — carries the completed EventDraft.
    save_requested = pyqtSignal(object)
    cancelled = pyqtSignal()
    #: Edit an existing event by name (from the list on step 1).
    edit_requested = pyqtSignal(str)

    def __init__(self, tracks: Sequence[str] = (), cars: Sequence[str] = (), parent=None):
        super().__init__(parent)
        self.setObjectName("ngrEventSetup")
        self._draft = EventDraft()
        self._step = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(_t.SPACE_XL, _t.SPACE_LG, _t.SPACE_XL, _t.SPACE_LG)
        lay.setSpacing(_t.SPACE_MD)
        scroll.setWidget(inner)

        lay.addWidget(SectionHeading("EVENT SETUP", level=1))

        # Progress — the driver always knows where they are and how much is left.
        self._chips = QHBoxLayout()
        self._chips.setSpacing(_t.SPACE_SM)
        self._chip_labels: List[QLabel] = []
        for i, title in enumerate(STEPS):
            chip = QLabel(f"{i + 1}. {title}")
            self._chip_labels.append(chip)
            self._chips.addWidget(chip)
        self._chips.addStretch(1)
        lay.addLayout(self._chips)

        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_identity())
        self._stack.addWidget(self._build_format())
        self._stack.addWidget(self._build_rules())
        self._stack.addWidget(self._build_confirm())
        lay.addWidget(self._stack)

        # Validation — stated next to the step it belongs to, never as a silent block.
        self._issues = QLabel("")
        self._issues.setWordWrap(True)
        self._issues.setStyleSheet(
            f"color: {_t.DANGER}; font-size: {_t.FS_LABEL}pt; font-weight: 600;")
        self._issues.setVisible(False)
        lay.addWidget(self._issues)

        nav = QHBoxLayout()
        self._back = SecondaryActionButton("‹ Back")
        self._back.clicked.connect(self._on_back)
        nav.addWidget(self._back)
        self._next = PrimaryActionButton("Next")
        self._next.clicked.connect(self._on_next)
        nav.addWidget(self._next)
        self._cancel = SecondaryActionButton("Cancel")
        self._cancel.clicked.connect(lambda: self.cancelled.emit())
        nav.addWidget(self._cancel)
        nav.addStretch(1)
        lay.addLayout(nav)
        lay.addStretch(1)

        self.set_choices(tracks, cars)
        self.set_draft(EventDraft())

    # ---- step 1: identity -------------------------------------------------
    def _build_identity(self) -> QWidget:
        card = Card()
        card.add(_hint("The three things the app cannot guess. Everything else has a "
                       "sensible default you can change later."))
        grid = QGridLayout()
        grid.setHorizontalSpacing(_t.SPACE_MD)
        grid.setVerticalSpacing(_t.SPACE_SM)

        self._name = QLineEdit()
        self._name.setPlaceholderText("e.g. GR Enduro Rd2")
        self._name.setStyleSheet(f"QLineEdit {{ {_input_qss()} }}")
        self._name.setMinimumHeight(_t.TOUCH_MIN_H)
        grid.addWidget(_field_label("Event name"), 0, 0)
        grid.addWidget(self._name, 0, 1)

        self._car = QComboBox()
        self._car.setEditable(True)
        self._car.setMinimumHeight(_t.TOUCH_MIN_H)
        self._car.setStyleSheet(f"QComboBox {{ {_input_qss()} }}")
        grid.addWidget(_field_label("Car"), 1, 0)
        grid.addWidget(self._car, 1, 1)

        self._track = QComboBox()
        self._track.setEditable(True)
        self._track.setMinimumHeight(_t.TOUCH_MIN_H)
        self._track.setStyleSheet(f"QComboBox {{ {_input_qss()} }}")
        grid.addWidget(_field_label("Track"), 2, 0)
        grid.addWidget(self._track, 2, 1)
        grid.setColumnStretch(1, 1)
        card.body.addLayout(grid)

        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(_t.SPACE_MD)
        pl.addWidget(card)

        # Existing events live HERE, on the first step — switching to an event you
        # already made is the same job as creating one, so it is the same screen.
        self._existing_card = Card()
        self._existing_card.add(SectionHeading("OR CONTINUE AN EVENT YOU ALREADY MADE", level=3))
        self._existing = QListWidget()
        self._existing.setMaximumHeight(150)
        self._existing.setStyleSheet(
            f"QListWidget {{ color: {_t.TEXT_HI}; background: {_t.CARBON_RAISED}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; }}")
        self._existing.itemDoubleClicked.connect(
            lambda item: self.edit_requested.emit(item.text()))
        self._existing_card.add(self._existing)
        self._btn_open = SecondaryActionButton("Open this event")
        self._btn_open.clicked.connect(self._on_open_existing)
        self._existing_card.add(self._btn_open)
        pl.addWidget(self._existing_card)
        pl.addStretch(1)
        return page

    # ---- step 2: format ---------------------------------------------------
    def _build_format(self) -> QWidget:
        card = Card()
        card.add(_hint("Pick how the race ends. You only have to fill in one number."))
        self._format = _Choice(RACE_TYPES)
        self._format.chosen.connect(self._on_format_chosen)
        card.body.addWidget(self._format)

        row = QHBoxLayout()
        self._laps_label = _field_label("Number of laps")
        self._laps = QSpinBox()
        self._laps.setRange(1, 999)
        self._laps.setMinimumHeight(_t.TOUCH_MIN_H)
        self._laps.setStyleSheet(f"QSpinBox {{ {_input_qss()} }}")
        self._mins_label = _field_label("Length in minutes")
        self._mins = QSpinBox()
        self._mins.setRange(1, 1440)
        self._mins.setMinimumHeight(_t.TOUCH_MIN_H)
        self._mins.setStyleSheet(f"QSpinBox {{ {_input_qss()} }}")
        for w in (self._laps_label, self._laps, self._mins_label, self._mins):
            row.addWidget(w)
        row.addStretch(1)
        card.body.addLayout(row)

        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(card)
        pl.addStretch(1)
        return page

    def _on_format_chosen(self, key: str) -> None:
        timed = key == "timed"
        self._laps_label.setVisible(not timed)
        self._laps.setVisible(not timed)
        self._mins_label.setVisible(timed)
        self._mins.setVisible(timed)

    # ---- step 3: rules ----------------------------------------------------
    def _build_rules(self) -> QWidget:
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(_t.SPACE_MD)

        head = Card()
        head.add(_hint("Standard rules are already set. Open this only if THIS event "
                       "actually specifies something different — most do not."))
        self._rules_state = QLabel("")
        self._rules_state.setWordWrap(True)
        self._rules_state.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-size: {_t.FS_LABEL}pt; font-weight: 600;")
        head.add(self._rules_state)
        self._btn_rules = SecondaryActionButton("Change the rules")
        self._btn_rules.setCheckable(True)
        self._btn_rules.toggled.connect(self._on_rules_toggled)
        head.add(self._btn_rules)
        pl.addWidget(head)

        self._rules_body = Card()
        grid = QGridLayout()
        grid.setHorizontalSpacing(_t.SPACE_MD)
        grid.setVerticalSpacing(_t.SPACE_SM)
        r = 0

        def _spin(minimum, maximum, decimals=0, step=1.0):
            w = QDoubleSpinBox() if decimals else QSpinBox()
            w.setRange(minimum, maximum)
            if decimals:
                w.setDecimals(decimals)
                w.setSingleStep(step)
            w.setMinimumHeight(_t.TOUCH_MIN_H)
            w.setStyleSheet(f"QAbstractSpinBox {{ {_input_qss()} }}")
            return w

        grid.addWidget(SectionHeading("WEAR & FUEL", level=3), r, 0, 1, 2); r += 1
        self._tyre_wear = _spin(0.0, 20.0, 1, 0.5)
        grid.addWidget(_field_label("Tyre wear multiplier"), r, 0)
        grid.addWidget(self._tyre_wear, r, 1); r += 1
        self._fuel_mult = _spin(0.0, 20.0, 1, 0.5)
        grid.addWidget(_field_label("Fuel use multiplier"), r, 0)
        grid.addWidget(self._fuel_mult, r, 1); r += 1
        self._refuel = _spin(0, 100)
        grid.addWidget(_field_label("Refuel rate (L/s)"), r, 0)
        grid.addWidget(self._refuel, r, 1); r += 1

        grid.addWidget(SectionHeading("PIT RULES", level=3), r, 0, 1, 2); r += 1
        self._stops = _spin(0, 10)
        grid.addWidget(_field_label("Mandatory pit stops"), r, 0)
        grid.addWidget(self._stops, r, 1); r += 1

        grid.addWidget(SectionHeading("CAR RULES", level=3), r, 0, 1, 2); r += 1
        self._bop = QCheckBox("Balance of Performance is applied")
        self._tuning = QCheckBox("Tuning is allowed")
        self._abs = QCheckBox("ABS is allowed")
        for cb in (self._bop, self._tuning, self._abs):
            cb.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_LABEL}pt;")
            grid.addWidget(cb, r, 0, 1, 2); r += 1

        grid.addWidget(SectionHeading("CONDITIONS", level=3), r, 0, 1, 2); r += 1
        self._weather = QComboBox()
        self._weather.addItems(list(WEATHER_CHOICES))
        self._weather.setMinimumHeight(_t.TOUCH_MIN_H)
        self._weather.setStyleSheet(f"QComboBox {{ {_input_qss()} }}")
        grid.addWidget(_field_label("Weather"), r, 0)
        grid.addWidget(self._weather, r, 1); r += 1
        self._damage = QComboBox()
        self._damage.addItems(list(DAMAGE_CHOICES))
        self._damage.setMinimumHeight(_t.TOUCH_MIN_H)
        self._damage.setStyleSheet(f"QComboBox {{ {_input_qss()} }}")
        grid.addWidget(_field_label("Damage"), r, 0)
        grid.addWidget(self._damage, r, 1); r += 1

        grid.addWidget(SectionHeading("TYRES", level=3), r, 0, 1, 2); r += 1
        self._tyre_boxes: dict = {}
        try:
            from data.tyres import ALL_COMPOUNDS
            racing = [c for c in ALL_COMPOUNDS if c.category == "Racing"]
        except Exception:  # pragma: no cover - defensive
            racing = []
        tyres_row = QHBoxLayout()
        for comp in racing:
            cb = QCheckBox(comp.name)
            cb.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_LABEL}pt;")
            self._tyre_boxes[comp.code] = cb
            tyres_row.addWidget(cb)
        tyres_row.addStretch(1)
        grid.addLayout(tyres_row, r, 0, 1, 2); r += 1
        grid.addWidget(_hint("Leave all unticked when the event does not restrict "
                             "compounds."), r, 0, 1, 2)
        grid.setColumnStretch(1, 1)
        self._rules_body.body.addLayout(grid)
        self._rules_body.setVisible(False)
        pl.addWidget(self._rules_body)
        pl.addStretch(1)
        return page

    def _on_rules_toggled(self, checked: bool) -> None:
        self._rules_body.setVisible(bool(checked))
        self._btn_rules.setText("Use standard rules" if checked else "Change the rules")

    # ---- step 4: confirm --------------------------------------------------
    def _build_confirm(self) -> QWidget:
        card = Card()
        card.add(SectionHeading("IS THIS RIGHT?", level=3))
        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(f"color: {_t.TEXT_HI}; font-size: {_t.FS_H3}pt;")
        card.add(self._summary)
        self._confirm_note = _hint(
            "Activating this event makes it the one the engineer prepares: the Garage, "
            "practice runs and strategy all become about this race.")
        card.add(self._confirm_note)
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.addWidget(card)
        pl.addStretch(1)
        return page

    # ---- population -------------------------------------------------------
    def set_choices(self, tracks: Sequence[str] = (), cars: Sequence[str] = ()) -> None:
        for combo, values in ((self._track, tracks), (self._car, cars)):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("")
            for v in values or ():
                combo.addItem(str(v))
            combo.setCurrentText(current)
            combo.blockSignals(False)

    def set_existing_events(self, names: Sequence[str] = ()) -> None:
        self._existing.clear()
        for n in names or ():
            self._existing.addItem(QListWidgetItem(str(n)))
        has = bool(names)
        self._existing_card.setVisible(has)

    def set_draft(self, draft: Optional[EventDraft]) -> None:
        """Render a draft into the controls and go back to step 1."""
        self._draft = draft if isinstance(draft, EventDraft) else EventDraft()
        d = self._draft
        self._name.setText(d.name)
        self._car.setCurrentText(d.car)
        self._track.setCurrentText(d.track)
        self._format.set_value("timed" if d.is_timed else "lap")
        self._on_format_chosen("timed" if d.is_timed else "lap")
        self._laps.setValue(int(d.laps or 1))
        self._mins.setValue(int(d.duration_mins or 1))
        self._tyre_wear.setValue(float(d.rule("tyre_wear") or 1.0))
        self._fuel_mult.setValue(float(d.rule("fuel_mult") or 1.0))
        self._refuel.setValue(int(float(d.rule("refuel_rate_lps") or 10)))
        self._stops.setValue(int(d.rule("mandatory_stops") or 0))
        self._bop.setChecked(bool(d.rule("bop")))
        self._tuning.setChecked(bool(d.rule("tuning")))
        self._abs.setChecked(bool(d.rule("abs")))
        self._weather.setCurrentText(str(d.rule("weather") or "Fixed Dry"))
        self._damage.setCurrentText(str(d.rule("damage") or "None"))
        avail = {str(c) for c in (d.rule("avail_tyres") or ())}
        for code, cb in self._tyre_boxes.items():
            cb.setChecked(code in avail)
        self._btn_rules.setChecked(d.has_custom_rules)
        self._goto(0)

    def current_draft(self) -> EventDraft:
        """The draft as currently described by the controls."""
        avail = [code for code, cb in self._tyre_boxes.items() if cb.isChecked()]
        rules = dict(self._draft.rules)
        rules.update({
            "tyre_wear": round(self._tyre_wear.value(), 1),
            "fuel_mult": round(self._fuel_mult.value(), 1),
            "refuel_rate_lps": float(self._refuel.value()),
            "mandatory_stops": int(self._stops.value()),
            "bop": self._bop.isChecked(),
            "tuning": self._tuning.isChecked(),
            "abs": self._abs.isChecked(),
            "weather": self._weather.currentText(),
            "damage": self._damage.currentText(),
            "avail_tyres": avail,
        })
        return self._draft.with_(
            name=self._name.text().strip(),
            car=self._car.currentText().strip(),
            track=self._track.currentText().strip(),
            race_type=self._format.value() or "lap",
            laps=int(self._laps.value()),
            duration_mins=int(self._mins.value()),
        ).with_(rules=rules)

    def show_issues(self, issues: Sequence[DraftIssue] = ()) -> None:
        """Show validation problems — each states its cause and what to do."""
        issues = tuple(issues or ())
        self._issues.setText("\n".join(f"• {i.message}" for i in issues))
        self._issues.setVisible(bool(issues))

    # ---- navigation -------------------------------------------------------
    def _goto(self, step: int) -> None:
        self._step = max(0, min(step, len(STEPS) - 1))
        self._stack.setCurrentIndex(self._step)
        self.show_issues(())
        for i, chip in enumerate(self._chip_labels):
            done, current = i < self._step, i == self._step
            colour = _t.NGR_GREEN if current else (_t.TEXT if done else _t.TEXT_MUTE)
            weight = "700" if current else "400"
            chip.setStyleSheet(
                f"color: {colour}; font-size: {_t.FS_CAPTION}pt; font-weight: {weight};")
        self._back.setVisible(self._step > 0)
        last = self._step == len(STEPS) - 1
        self._next.set_action("Save & start preparing" if last else "Next")
        if self._step == 2:
            self._refresh_rules_state()
        if last:
            self._summary.setText(self.current_draft().summary())

    def _refresh_rules_state(self) -> None:
        d = self.current_draft()
        if d.has_custom_rules:
            self._rules_state.setText("  ".join(d.rule_sentences()))
        else:
            self._rules_state.setText("Standard rules — nothing unusual about this event.")

    def _on_back(self) -> None:
        self._draft = self.current_draft()
        self._goto(self._step - 1)

    def _on_next(self) -> None:
        self._draft = self.current_draft()
        if self._step == len(STEPS) - 1:
            self.save_requested.emit(self._draft)
            return
        # Identity is the only step that can block progress, and it says why.
        if self._step == 0:
            from services.event_setup import validate
            blocking = [i for i in validate(self._draft)
                        if i.field_name in ("name", "car", "track")]
            if blocking:
                self.show_issues(blocking)
                return
        self._goto(self._step + 1)

    def _on_open_existing(self) -> None:
        item = self._existing.currentItem()
        if item is not None:
            self.edit_requested.emit(item.text())

    def current_step(self) -> int:
        return self._step
