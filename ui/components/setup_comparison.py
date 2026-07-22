"""SetupComparison — side-by-side setup diff (F2.5).

Compares two setups field-by-field in GT7 order (Current↔Parent, Base↔Qualifying,
Qualifying↔Race, Recommended↔Active, Best↔Current — the caller supplies the pairs)
and highlights what differs: value A, value B, and direction. Reuses the canonical
``build_transcribe_sections`` for ordering + formatting; the diff itself is pure and
unit-testable. Presentation only — no engineering logic.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from ui import ngr_theme as _t
from ui.setup_transcribe_view import build_transcribe_sections


def _combine(front, rear) -> str:
    if rear is None:
        return "" if front is None else str(front)
    return f"{front} / {rear}"


def build_comparison_rows(a: Optional[dict], b: Optional[dict]) -> List[dict]:
    """Pure GT7-ordered diff of two setups.

    Returns ``[{section, label, a, b, changed}]`` in GT7 row order (from setup A's
    sections), where ``a``/``b`` are display strings ("front / rear" when paired)
    and ``changed`` is True when A and B differ on that field. Never raises.
    """
    try:
        sa = build_transcribe_sections(a or {})
        sb = build_transcribe_sections(b or {})
    except Exception:
        return []
    bidx = {}
    for sec in sb:
        for row in sec.get("rows", []):
            label = row[0]
            front = row[1]
            rear = row[2] if len(row) > 2 else None
            bidx[(sec.get("title"), label)] = (front, rear)

    rows: List[dict] = []
    for sec in sa:
        for row in sec.get("rows", []):
            label = row[0]
            af = row[1]
            ar = row[2] if len(row) > 2 else None
            bf, br = bidx.get((sec.get("title"), label), (None, None))
            changed = (str(af) != str(bf)) or (ar is not None and str(ar) != str(br))
            rows.append({
                "section": sec.get("title", ""),
                "label": label,
                "a": _combine(af, ar),
                "b": _combine(bf, br),
                "changed": changed,
            })
    return rows


class SetupComparison(QWidget):
    """A compare-mode selector + a side-by-side diff table."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrSetupComparison")
        # each mode: (mode_label, a_label, a_dict, b_label, b_dict)
        self._modes: List[Tuple[str, str, dict, str, dict]] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(_t.SPACE_SM)

        controls = QHBoxLayout()
        controls.setSpacing(_t.SPACE_MD)
        self._combo = QComboBox()
        self._combo.currentIndexChanged.connect(lambda _=0: self._render())
        controls.addWidget(QLabel("Compare:"))
        controls.addWidget(self._combo)
        self._changed_only = QCheckBox("Changed only")
        self._changed_only.setChecked(True)
        self._changed_only.toggled.connect(lambda _=False: self._render())
        controls.addWidget(self._changed_only)
        controls.addStretch(1)
        lay.addLayout(controls)

        self._table = QTableWidget(0, 3)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.setStyleSheet(
            f"QTableWidget {{ color: {_t.TEXT_HI}; background: {_t.CARBON_RAISED}; "
            f"alternate-background-color: {_t.CARBON}; gridline-color: {_t.HAIRLINE_SOFT}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; }}"
        )
        self._table.setAlternatingRowColors(True)
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        lay.addWidget(self._table, 1)

        self._empty = QLabel("Nothing to compare yet.")
        self._empty.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        lay.addWidget(self._empty)

    def set_comparisons(self, modes) -> None:
        """``modes`` = list of (mode_label, a_label, a_dict, b_label, b_dict)."""
        self._modes = [m for m in (modes or []) if isinstance(m, (list, tuple)) and len(m) == 5]
        self._combo.blockSignals(True)
        self._combo.clear()
        for m in self._modes:
            self._combo.addItem(m[0])
        self._combo.blockSignals(False)
        self._render()

    def _render(self) -> None:
        idx = self._combo.currentIndex()
        if not self._modes or idx < 0 or idx >= len(self._modes):
            self._table.setRowCount(0)
            self._table.setVisible(False)
            self._empty.setVisible(True)
            return
        _, a_label, a_dict, b_label, b_dict = self._modes[idx]
        self._table.setHorizontalHeaderLabels(["Setting", a_label, b_label])
        rows = build_comparison_rows(a_dict, b_dict)
        if self._changed_only.isChecked():
            rows = [r for r in rows if r["changed"]]
        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            self._table.setItem(i, 0, QTableWidgetItem(r["label"]))
            self._table.setItem(i, 1, QTableWidgetItem(r["a"]))
            b_item = QTableWidgetItem(r["b"])
            if r["changed"]:
                from PyQt6.QtGui import QColor
                b_item.setForeground(QColor(_t.NGR_GREEN))
            self._table.setItem(i, 2, b_item)
        has = bool(rows)
        self._table.setVisible(has)
        self._empty.setVisible(not has)
        self._empty.setText("No differences for this comparison."
                            if self._modes else "Nothing to compare yet.")

    # test/inspection helper
    def current_rows(self) -> int:
        return self._table.rowCount()
