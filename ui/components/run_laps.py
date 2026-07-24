"""RunLapsPanel — what actually happened on the last recorded run (UAT-4).

Practice Review asked the driver how the car felt but never showed them the run: no
lap times, no fuel per lap, nothing to review against. This renders the measured
truth — a lap-by-lap table plus the clean-lap summary — above the feedback form, so
the driver answers from data instead of memory.

Pure presentation over ``strategy.practice_run_review.RunReview``; it measures nothing.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView,
)

from ui import ngr_theme as _t
from ui.components.cards import SectionHeading
from strategy.practice_run_review import RunReview, format_lap_time

_COLUMNS = ("Lap", "Time", "Δ to best", "Fuel", "Compound", "Lock-ups", "Wheelspin", "")


def _tabular() -> QFont:
    f = QFont("Consolas")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(10)
    return f


class RunLapsPanel(QWidget):
    """Lap-by-lap table + summary for one recorded run."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrRunLaps")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(_t.SPACE_SM)

        head = QHBoxLayout()
        head.addWidget(SectionHeading("THIS RUN", level=2))
        head.addStretch(1)
        self._headline = QLabel("")
        self._headline.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-size: {_t.FS_LABEL}pt; font-weight: 700;")
        head.addWidget(self._headline)
        lay.addLayout(head)

        # WHICH run this was. Every run reviewed identically is what made a coaching
        # run indistinguishable from a tyre test after the fact.
        self._kind = QLabel("")
        self._kind.setWordWrap(True)
        self._kind.setStyleSheet(
            f"color: {_t.NGR_GREEN}; font-size: {_t.FS_LABEL}pt; font-weight: 700;")
        self._kind.setVisible(False)
        lay.addWidget(self._kind)

        self._summary = QLabel("")
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_LABEL}pt;")
        lay.addWidget(self._summary)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(list(_COLUMNS))
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.setAlternatingRowColors(True)
        self._table.setStyleSheet(
            f"QTableWidget {{ color: {_t.TEXT_HI}; background: {_t.CARBON_RAISED}; "
            f"alternate-background-color: {_t.CARBON}; gridline-color: {_t.HAIRLINE_SOFT}; "
            f"border: 1px solid {_t.HAIRLINE}; border-radius: {_t.RADIUS_SM}px; }}"
        )
        hh = self._table.horizontalHeader()
        for c in range(len(_COLUMNS) - 1):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(len(_COLUMNS) - 1, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self._table)

        self._empty = QLabel(
            "No recorded run yet — start a run from the Run card, drive it, then press "
            "“End run & record”. The laps you drove will appear here.")
        self._empty.setWordWrap(True)
        self._empty.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        lay.addWidget(self._empty)

        self.set_review(RunReview())

    def set_run_kind(self, run_name: str = "", reports: tuple = "", on: str = "") -> None:
        """Name the kind of run this was, which setup it was on, and what it can tell.

        ``on`` is the discipline's setup ("Qualifying setup"), so a race run and a
        qualifying run read as distinct even when they are the same kind of run — the
        driver asked for race and qualifying practice to be told apart.
        """
        name = str(run_name or "").strip()
        on = str(on or "").strip()
        items = tuple(str(r).strip() for r in (reports or ()) if str(r).strip())
        if not name and not on:
            self._kind.setVisible(False)
            self._kind.setText("")
            return
        text = f"Reviewing your {name}" if name else "Reviewing this run"
        if on:
            text += f" on the {on}"
        if items:
            text += " — it can tell you: " + "; ".join(items).lower()
        self._kind.setText(text)
        self._kind.setVisible(True)

    def set_review(self, review: Optional[RunReview]) -> None:
        """Render a run review. Defensive against None/garbage."""
        if not isinstance(review, RunReview):
            review = RunReview()

        has = review.has_laps
        self._table.setVisible(has)
        self._summary.setVisible(has)
        self._headline.setVisible(has)
        self._empty.setVisible(not has)
        if not has:
            self._table.setRowCount(0)
            self._kind.setVisible(False)
            return

        self._headline.setText(
            f"Best {format_lap_time(review.best_ms)}"
            + (f"  ·  {', '.join(review.compounds)}" if review.compounds else ""))
        self._summary.setText(review.summary_line)

        self._table.setRowCount(len(review.laps))
        for row, lap in enumerate(review.laps):
            cells = (str(lap.lap), lap.time_text, lap.delta_text, lap.fuel_text,
                     lap.compound or "—",
                     str(lap.lock_ups) if lap.lock_ups else "",
                     str(lap.wheelspin) if lap.wheelspin else "",
                     "" if lap.clean else f"excluded — {lap.excluded_reason}")
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col in (1, 2, 3):
                    item.setFont(_tabular())
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                # A compromised lap is dimmed so the clean laps read as the real result.
                if not lap.clean:
                    item.setForeground(QColor(_t.TEXT_MUTE))
                elif col == 1 and lap.time_ms == review.best_ms:
                    item.setForeground(QColor(_t.NGR_GREEN))
                self._table.setItem(row, col, item)
