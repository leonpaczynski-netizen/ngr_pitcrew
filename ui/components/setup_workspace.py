"""SetupWorkspace — the single focused Garage setup surface (F2).

Replaces the old side-by-side Base/Qualifying/Race scrolling maze with ONE
workspace and a discipline selector. It renders a ``SetupRecommendationVM`` (the
canonical recommendation model) and applies it through ``applied_field_values()``
so what the driver sees is exactly what gets applied (F2.2).

It renders and signals only — it performs no engineering. ``apply_requested`` hands
the caller the exact field→value dict to write via the canonical apply/clamp path;
``discipline_changed`` asks the caller to rebuild for another discipline.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QToolButton, QButtonGroup,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from ui import ngr_theme as _t
from ui.components.cards import SectionHeading
from ui.components.status import StatusPill
from ui.components.buttons import PrimaryActionButton, SecondaryActionButton
from ui.setup_recommendation_vm import SetupRecommendationVM, build_recommendation_vm


DISCIPLINES = (("base", "Base"), ("qualifying", "Qualifying"), ("race", "Race"))


class SetupDisciplineSelector(QWidget):
    """Segmented Base | Qualifying | Race selector (one focused discipline)."""

    discipline_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QToolButton] = {}
        for key, label in DISCIPLINES:
            b = QToolButton(self)
            b.setText(label)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setMinimumHeight(_t.TOUCH_MIN_H)
            b.setStyleSheet(self._qss())
            b.clicked.connect(lambda _=False, k=key: self._on_click(k))
            self._group.addButton(b)
            self._buttons[key] = b
            lay.addWidget(b)
        lay.addStretch(1)
        self._current = "race"
        self.set_discipline("race")

    def _on_click(self, key: str) -> None:
        self._current = key
        self.discipline_changed.emit(key)

    def set_discipline(self, key: str) -> None:
        b = self._buttons.get(key)
        if b is not None:
            self._current = key
            b.setChecked(True)

    def current(self) -> str:
        return self._current

    @staticmethod
    def _qss() -> str:
        return (
            f"QToolButton {{ color: {_t.TEXT_DIM}; background: {_t.CARBON}; "
            f"border: 1px solid {_t.HAIRLINE}; padding: 5px 16px; "
            f"font-size: {_t.FS_LABEL}pt; }}"
            f"QToolButton:hover {{ color: {_t.TEXT_HI}; }}"
            f"QToolButton:checked {{ color: {_t.NGR_GREEN_INK}; background: {_t.NGR_GREEN}; "
            f"border-color: {_t.NGR_GREEN}; font-weight: 700; }}"
            f"QToolButton:focus {{ {_t.focus_ring_qss()} }}"
        )


class SetupWorkspace(QWidget):
    apply_requested = pyqtSignal(dict)     # {field: value} from applied_field_values()
    discipline_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrSetupWorkspace")
        self._vm: SetupRecommendationVM = build_recommendation_vm({})
        lay = QVBoxLayout(self)
        lay.setContentsMargins(_t.SPACE_XL, _t.SPACE_LG, _t.SPACE_XL, _t.SPACE_LG)
        lay.setSpacing(_t.SPACE_MD)

        # Title + discipline selector + active setup
        top = QHBoxLayout()
        top.addWidget(SectionHeading("GARAGE", level=1))
        top.addSpacing(_t.SPACE_LG)
        self._selector = SetupDisciplineSelector()
        self._selector.discipline_changed.connect(self.discipline_changed)
        top.addWidget(self._selector)
        top.addStretch(1)
        self._active = QLabel("")
        self._active.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        top.addWidget(self._active)
        lay.addLayout(top)

        # Status pills
        status_row = QHBoxLayout()
        status_row.setSpacing(_t.SPACE_SM)
        self._pill_saved = StatusPill("Not saved", tone="neutral")
        self._pill_applied = StatusPill("Not applied", tone="neutral")
        self._pill_valid = StatusPill("Not validated", tone="neutral")
        for p in (self._pill_saved, self._pill_applied, self._pill_valid):
            status_row.addWidget(p)
        status_row.addStretch(1)
        lay.addLayout(status_row)

        # Changed-fields table
        self._primary_issue = QLabel("")
        self._primary_issue.setWordWrap(True)
        self._primary_issue.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_BODY}pt;")
        lay.addWidget(self._primary_issue)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(
            ["Setting", "Current", "Recommended", "Δ", "Confidence"])
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, 5):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self._table, 1)

        self._empty = QLabel("No recommendation yet. Run an analysis to get setup guidance.")
        self._empty.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        lay.addWidget(self._empty)

        # Actions
        act = QHBoxLayout()
        self._apply = PrimaryActionButton()
        self._apply.clicked.connect(self._on_apply)
        self._explain = SecondaryActionButton("Why these changes")
        self._explain.setCheckable(True)
        self._explain.toggled.connect(self._on_explain)
        act.addWidget(self._apply)
        act.addWidget(self._explain)
        act.addStretch(1)
        lay.addLayout(act)

        self._why = QLabel("")
        self._why.setWordWrap(True)
        self._why.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        self._why.setVisible(False)
        lay.addWidget(self._why)

        self.set_recommendation(self._vm)

    # ---- population -------------------------------------------------------
    def set_recommendation(
        self, vm: SetupRecommendationVM, *, discipline: str = "race",
        active_setup: str = "", saved: bool = False, applied: bool = False,
        validated: bool = False,
    ) -> None:
        if not isinstance(vm, SetupRecommendationVM):
            vm = build_recommendation_vm({})
        self._vm = vm
        self._selector.set_discipline(discipline)
        self._active.setText(f"Active setup: {active_setup}" if active_setup else "Active setup: —")

        self._pill_saved.set_status("Saved" if saved else "Not saved",
                                    tone="success" if saved else "neutral",
                                    glyph="✓" if saved else "")
        self._pill_applied.set_status("Applied in GT7" if applied else "Not applied",
                                      tone="success" if applied else "neutral",
                                      glyph="✓" if applied else "")
        self._pill_valid.set_status("Validated" if validated else "Not validated",
                                    tone="success" if validated else "neutral",
                                    glyph="✓" if validated else "")

        self._primary_issue.setText(
            f"Primary issue: {vm.header.primary_issue}" if vm.header.primary_issue else "")
        self._primary_issue.setVisible(bool(vm.header.primary_issue))

        rows = vm.proposed_rows()
        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(r.setting))
            self._table.setItem(i, 1, QTableWidgetItem(r.current_value))
            self._table.setItem(i, 2, QTableWidgetItem(r.recommended_value))
            self._table.setItem(i, 3, QTableWidgetItem(r.delta))
            self._table.setItem(i, 4, QTableWidgetItem(r.confidence or "—"))
        self._table.setVisible(bool(rows))
        self._empty.setVisible(not rows)

        self._apply.set_action("Apply recommendation", enabled=bool(rows))
        self._explain.setVisible(bool(vm.why_cards))

        # Compose the engineering explanation (progressive disclosure).
        if vm.why_cards:
            parts = []
            for c in vm.why_cards:
                bits = [f"• {c.setting}: {c.rationale}" if c.rationale else f"• {c.setting}"]
                if c.symptom:
                    bits.append(f"(addresses: {c.symptom})")
                parts.append(" ".join(bits))
            self._why.setText("\n".join(parts))
        else:
            self._why.setText("")

    # ---- signals ----------------------------------------------------------
    def _on_apply(self):
        # Shown == applied: the applied dict comes from the SAME rows displayed.
        self.apply_requested.emit(self._vm.applied_field_values())

    def _on_explain(self, checked: bool):
        self._why.setVisible(bool(checked))
