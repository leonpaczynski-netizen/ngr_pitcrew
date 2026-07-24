"""ProgrammeMapPage — the whole event programme at a glance (F-UAT6).

Round 6: "I feel like we are going in circles." The engineer nominates one weakest
domain at a time, which is right, but nothing showed how many runs each area needs or
how many remain — so every screen looked the same after every run. This renders the
map: an overall completion figure, each evidence area with its runs-done / runs-needed
and a progress bar, the kind of run that fills it, and the next few runs planned ahead.

Pure presentation over ``strategy.programme_map.ProgrammeMap``; it measures nothing and
decides nothing. The one action starts the next run the map points at.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, QScrollArea,
)

from ui import ngr_theme as _t
from ui.components.cards import Card, SectionHeading
from ui.components.buttons import PrimaryActionButton
from strategy.programme_map import ProgrammeMap, DomainProgress, TARGET_ADEQUATE

_LEVEL_COLOUR = {
    "missing": _t.DANGER,
    "developing": _t.WARN,
    "adequate": _t.SUCCESS,
    "strong": _t.NGR_GREEN,
}
_LEVEL_LABEL = {
    "missing": "No runs yet",
    "developing": "Developing",
    "adequate": "Covered",
    "strong": "Strong",
}


class _ProgressBar(QWidget):
    """A slim done/target bar. Segments = target runs; filled = runs done (capped)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._row = QHBoxLayout(self)
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(3)
        self.setFixedHeight(_t.SPACE_MD)

    def set_progress(self, done: int, target: int, colour: str) -> None:
        while self._row.count():
            w = self._row.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        target = max(1, int(target or 1))
        done = max(0, int(done or 0))
        for i in range(target):
            seg = QFrame()
            seg.setFixedHeight(_t.SPACE_SM)
            seg.setMinimumWidth(22)
            filled = i < done
            seg.setStyleSheet(
                f"background: {colour if filled else _t.CARBON_HI}; "
                f"border: 1px solid {colour if filled else _t.HAIRLINE}; "
                f"border-radius: 2px;")
            self._row.addWidget(seg)
        # Runs beyond the target (a strong domain) show as one extra green tick.
        if done > target:
            extra = QLabel(f"+{done - target}")
            extra.setStyleSheet(f"color: {_t.NGR_GREEN}; font-size: {_t.FS_CAPTION}pt; font-weight: 700;")
            self._row.addWidget(extra)
        self._row.addStretch(1)


class ProgrammeMapPage(QWidget):
    """The event programme as a map of evidence areas and the runs that fill them."""

    #: Start the next run the map points at (domain key of the weakest area).
    start_next_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrProgrammeMap")
        self._map = ProgrammeMap()

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

        head = QHBoxLayout()
        head.addWidget(SectionHeading("PROGRAMME", level=1))
        head.addSpacing(_t.SPACE_MD)
        self._subtitle = QLabel("How far through preparing for this event are we?")
        self._subtitle.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        head.addWidget(self._subtitle)
        head.addStretch(1)
        lay.addLayout(head)

        # Overall completion.
        self._overall_card = Card()
        oc = QHBoxLayout()
        self._pct = QLabel("0%")
        self._pct.setStyleSheet(
            f"color: {_t.NGR_GREEN}; font-size: {_t.FS_H1}pt; font-weight: 800;")
        oc.addWidget(self._pct)
        oc.addSpacing(_t.SPACE_LG)
        self._headline = QLabel("")
        self._headline.setWordWrap(True)
        self._headline.setStyleSheet(f"color: {_t.TEXT_HI}; font-size: {_t.FS_H3}pt;")
        oc.addWidget(self._headline, 1)
        self._overall_card.body.addLayout(oc)
        lay.addWidget(self._overall_card)

        # Per-area rows.
        self._areas_card = Card()
        self._areas_card.add(SectionHeading("EVIDENCE AREAS", level=3))
        self._areas_box = QVBoxLayout()
        self._areas_box.setSpacing(_t.SPACE_SM)
        self._areas_card.body.addLayout(self._areas_box)
        lay.addWidget(self._areas_card)

        # Next runs planned ahead + the one action.
        self._next_card = Card()
        self._next_card.add(SectionHeading("DO THESE NEXT", level=3))
        self._next_box = QVBoxLayout()
        self._next_box.setSpacing(_t.SPACE_XS)
        self._next_card.body.addLayout(self._next_box)
        self._start = PrimaryActionButton("Start the next run")
        self._start.clicked.connect(self._on_start)
        self._next_card.body.addWidget(self._start)
        lay.addWidget(self._next_card)

        self._empty = QLabel(
            "No programme yet — record a practice run and the areas you have covered, "
            "and the runs still to do, will appear here.")
        self._empty.setWordWrap(True)
        self._empty.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        lay.addWidget(self._empty)
        lay.addStretch(1)

        self._next_domain = ""
        self.set_map(ProgrammeMap())

    def set_map(self, m: Optional[ProgrammeMap]) -> None:
        if not isinstance(m, ProgrammeMap):
            m = ProgrammeMap()
        self._map = m
        has = m.has_programme
        for card in (self._overall_card, self._areas_card, self._next_card):
            card.setVisible(has)
        self._empty.setVisible(not has)
        if not has:
            return

        self._pct.setText(f"{m.overall_pct}%")
        self._headline.setText(m.headline)

        _clear(self._areas_box)
        for d in m.domains:
            self._areas_box.addWidget(self._area_row(d))

        _clear(self._next_box)
        for title, run_name in m.next_runs:
            lbl = QLabel(f"•  {title} — {run_name}")
            lbl.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_LABEL}pt;")
            self._next_box.addWidget(lbl)
        # The one action targets the weakest pending area (first in next_runs).
        pending = [d for d in m.domains if not d.is_ready]
        pending.sort(key=lambda x: (x.level != "missing", x.level != "developing"))
        self._next_domain = pending[0].run_type if pending else ""
        if pending:
            self._start.set_action(f"Start a {pending[0].run_name}", enabled=True)
        else:
            self._start.set_action("Everything is covered", enabled=False)

    def _area_row(self, d: DomainProgress) -> QWidget:
        box = QFrame()
        box.setObjectName("ngrProgArea")
        border = _t.NGR_GREEN if d.is_next else _t.HAIRLINE
        box.setStyleSheet(
            f"#ngrProgArea {{ background: {_t.CARBON_RAISED}; "
            f"border: 1px solid {border}; border-radius: {_t.RADIUS_SM}px; }}")
        grid = QGridLayout(box)
        grid.setContentsMargins(_t.SPACE_MD, _t.SPACE_SM, _t.SPACE_MD, _t.SPACE_SM)
        grid.setHorizontalSpacing(_t.SPACE_MD)
        grid.setVerticalSpacing(2)

        colour = _LEVEL_COLOUR.get(d.level, _t.TEXT_DIM)
        title = QLabel(d.title + ("   ← next" if d.is_next else ""))
        title.setStyleSheet(f"color: {_t.TEXT_HI}; font-size: {_t.FS_BODY}pt; font-weight: 600;")
        grid.addWidget(title, 0, 0)

        badge = QLabel(_LEVEL_LABEL.get(d.level, d.level.title()))
        badge.setStyleSheet(f"color: {colour}; font-size: {_t.FS_CAPTION}pt; font-weight: 700;")
        badge.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        grid.addWidget(badge, 0, 1)

        bar = _ProgressBar()
        bar.set_progress(d.done, d.target, colour)
        grid.addWidget(bar, 1, 0, 1, 2)

        detail = QLabel(f"{d.progress_text}   ·   fills from a {d.run_name}")
        detail.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        detail.setWordWrap(True)
        grid.addWidget(detail, 2, 0, 1, 2)

        grid.setColumnStretch(0, 1)
        return box

    def _on_start(self) -> None:
        self.start_next_requested.emit(self._next_domain)


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
