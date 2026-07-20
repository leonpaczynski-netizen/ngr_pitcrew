"""Live Engineering State Monitor panel (Phase 7).

A READ-ONLY engineering visualisation of "what is happening to the car right now":
a health banner, an active-issues table with a per-lap trend sparkline, resolved
issues, protected behaviours, and an append-only development timeline. It renders the
pure ``ui.live_engineering_vm`` rows produced from ``SessionDB.build_live_engineering_state``.

There are NO Apply buttons and NO setup-authoring controls here — the monitor observes
and reports; it never changes the car, the working windows or any candidate ordering.
Rendering is defensive: a malformed/empty result shows an empty-state note, never a
crash.
"""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QGroupBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from ui import ngr_theme as ngr
from ui import live_engineering_vm as vm


_BAND_TONE = {
    "nominal": ngr.SUCCESS, "settling": ngr.INFO, "developing": ngr.WARN,
    "degrading": ngr.DANGER, "unknown": ngr.NEUTRAL,
}


class LiveEngineeringMonitor(QWidget):
    """Self-contained monitor panel. Call :meth:`update_result` with the orchestrator
    dict each time the live state is recomputed."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(ngr.SPACE_MD)

        title = QLabel("Live Engineering State — What the Car Is Doing Now")
        title.setStyleSheet(ngr.heading_qss(2))
        root.addWidget(title)

        note = QLabel("Read-only observer. Updates every comparable lap — no setup "
                      "is changed here.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
        root.addWidget(note)

        # Health banner
        self._band = QLabel("Building picture…")
        self._band.setStyleSheet(ngr.banner_qss("info"))
        root.addWidget(self._band)

        self._health_grid = QGridLayout()
        health_box = QGroupBox("Session Health")
        health_box.setStyleSheet(ngr.card_qss())
        health_box.setLayout(self._health_grid)
        root.addWidget(health_box)

        # Active issues + sparkline
        self._active = self._make_table(("Issue", "Corner", "Phase", "Status",
                                         "Trend", "Recurrence", "Laps", "Trend/Lap"))
        root.addWidget(self._section("Active Issues", self._active))

        # Resolved issues
        self._resolved = self._make_table(vm.ISSUE_TABLE_COLUMNS)
        root.addWidget(self._section("Resolved This Session", self._resolved))

        # Protected behaviours
        self._protected = self._make_table(vm.ISSUE_TABLE_COLUMNS)
        root.addWidget(self._section("Protected Behaviour", self._protected))

        # Development ledger timeline
        self._timeline = self._make_table(vm.TIMELINE_COLUMNS)
        root.addWidget(self._section("Development Timeline (append-only)",
                                     self._timeline))

        self._empty = QLabel("No comparable laps yet — run a few clean laps.")
        self._empty.setWordWrap(True)
        self._empty.setStyleSheet(f"color:{ngr.TEXT_MUTE}; font-size:{ngr.FS_BODY}pt;")
        root.addWidget(self._empty)
        root.addStretch()

    # -- construction helpers ------------------------------------------------
    def _make_table(self, columns) -> QTableWidget:
        t = QTableWidget(0, len(columns))
        t.setHorizontalHeaderLabels(list(columns))
        t.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        return t

    def _section(self, title: str, table: QTableWidget) -> QGroupBox:
        box = QGroupBox(title)
        box.setStyleSheet(ngr.card_qss())
        lay = QVBoxLayout(box)
        lay.addWidget(table)
        return box

    # -- rendering -----------------------------------------------------------
    def update_result(self, result: Optional[dict]) -> None:
        """Render the orchestrator result. Safe on None / not-ok / empty."""
        result = result if isinstance(result, dict) else {}
        empty = vm.is_empty(result)
        self._empty.setVisible(empty)
        state = result.get("live_state") or {}

        # health banner + grid
        band = (state.get("health") or {}).get("band", "unknown")
        tone = {"nominal": "success", "settling": "info", "developing": "warn",
                "degrading": "danger"}.get(str(band), "info")
        self._band.setText(vm.health_band_label(state))
        self._band.setStyleSheet(ngr.banner_qss(tone))
        self._fill_grid(self._health_grid, vm.health_summary_rows(state))

        valid = (state.get("valid_lap_numbers") or [])
        # active issues with per-lap sparkline (extra last column)
        issues_by_key = {(i.get("identity") or {}).get("key"): i
                         for i in (state.get("issues") or [])}
        active = vm.active_issue_rows(state)
        self._fill_active(active, state, valid, issues_by_key)

        self._fill_table(self._resolved, vm.resolved_issue_rows(state))
        self._fill_table(self._protected, vm.protected_rows(state))
        self._fill_table(self._timeline, vm.timeline_rows(result))

    def _fill_active(self, rows, state, valid, issues_by_key) -> None:
        # map back to the source issue to compute the sparkline
        issues = sorted(state.get("issues") or [], key=vm._sort_key)
        active_issues = [i for i in issues
                         if str(i.get("status")) in ("active", "recovering",
                                                     "new", "damaged")]
        self._active.setRowCount(len(active_issues))
        for r, issue in enumerate(active_issues):
            full = vm._issue_row(issue)
            cells = (full[0], full[1], full[2], full[3], full[4], full[5],
                     full[6], vm.trend_sparkline(issue, valid))
            for c, val in enumerate(cells):
                self._active.setItem(r, c, QTableWidgetItem(str(val)))

    def _fill_table(self, table: QTableWidget, rows) -> None:
        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                table.setItem(r, c, QTableWidgetItem(str(val)))

    def _fill_grid(self, grid: QGridLayout, rows) -> None:
        while grid.count():
            item = grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for i, (label, value) in enumerate(rows):
            row, col = divmod(i, 2)
            lbl = QLabel(f"{label}:")
            lbl.setStyleSheet(f"color:{ngr.TEXT_DIM}; font-size:{ngr.FS_CAPTION}pt;")
            val = QLabel(str(value))
            val.setStyleSheet(f"color:{ngr.TEXT_HI}; font-size:{ngr.FS_BODY}pt;")
            grid.addWidget(lbl, row, col * 2)
            grid.addWidget(val, row, col * 2 + 1)
