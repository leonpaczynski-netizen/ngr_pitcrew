"""StrategyPlanView — the race strategy meeting (F5).

Presents the deterministic race plan: the recommended strategy prominently plus
alternatives, total race time / expected laps, stint & tyre sequence, fuel targets,
pit windows, risks, confidence, the measured-vs-assumed provenance of each input,
and the conditions that would trigger a replan. Primary action: Approve Race Plan.

SAFETY: this surface exposes NO setup-apply controls — it is read-only strategy
advice. Pure presentation over a VM the caller maps from race_strategy_vm /
race_strategy_readiness_vm; it fabricates nothing and never changes a setup.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Tuple

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QWidget, QGridLayout

from ui import ngr_theme as _t
from ui.components.cards import SectionHeading, Card
from ui.components.status import StatusPill, ConfidenceMeter, TONE_BASE_COLOR
from ui.components.buttons import PrimaryActionButton


# input source -> semantic tone (measured is trustworthy; missing is a red flag)
_SOURCE_TONE = {
    "measured": "success", "derived": "info", "event": "info",
    "manual": "warn", "assumed": "neutral", "default": "neutral", "missing": "danger",
}


@dataclass(frozen=True)
class StrategyOption:
    name: str
    total_time: str = ""
    expected_laps: str = ""
    stints: Tuple[str, ...] = field(default_factory=tuple)
    tyre_sequence: str = ""
    fuel_target: str = ""
    pit_windows: str = ""
    confidence: str = "unknown"
    summary: str = ""
    recommended: bool = False


@dataclass(frozen=True)
class StrategyInput:
    name: str
    value: str = ""
    source: str = "assumed"   # measured|derived|event|manual|assumed|default|missing


@dataclass(frozen=True)
class StrategyPlanVM:
    options: Tuple[StrategyOption, ...] = field(default_factory=tuple)
    risks: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)   # (label, level)
    inputs: Tuple[StrategyInput, ...] = field(default_factory=tuple)
    replan_triggers: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_plan(self) -> bool:
        return bool(self.options)


class StrategyPlanView(QWidget):
    approve_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrStrategyPlan")
        self._vm = StrategyPlanVM()
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(_t.SPACE_XL, _t.SPACE_LG, _t.SPACE_XL, _t.SPACE_LG)
        self._root.setSpacing(_t.SPACE_MD)

        top = QHBoxLayout()
        top.addWidget(SectionHeading("RACE STRATEGY", level=1))
        top.addSpacing(_t.SPACE_MD)
        sub = QLabel("What is the plan?")
        sub.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        top.addWidget(sub)
        top.addStretch(1)
        # Safety marker — this surface never changes a setup.
        top.addWidget(StatusPill("Read-only · no setup changes", tone="advisory", glyph="●"))
        self._root.addLayout(top)

        self._body = QVBoxLayout()
        self._body.setSpacing(_t.SPACE_MD)
        self._root.addLayout(self._body)

        self._empty = QLabel("No race plan yet — gather practice evidence, then build the plan.")
        self._empty.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        self._root.addWidget(self._empty)

        act = QHBoxLayout()
        self._approve = PrimaryActionButton()
        self._approve.clicked.connect(lambda: self.approve_requested.emit())
        act.addWidget(self._approve)
        act.addStretch(1)
        self._root.addLayout(act)
        self._root.addStretch(1)

        self.set_plan(StrategyPlanVM())

    def set_plan(self, vm: StrategyPlanVM) -> None:
        if not isinstance(vm, StrategyPlanVM):
            vm = StrategyPlanVM()
        self._vm = vm
        _clear_layout(self._body)
        self._empty.setVisible(not vm.has_plan)

        for opt in vm.options:
            self._body.addWidget(self._option_card(opt))

        if vm.risks:
            self._body.addWidget(self._risks_row(vm.risks))
        if vm.inputs:
            self._body.addWidget(self._inputs_card(vm.inputs))
        if vm.replan_triggers:
            self._body.addWidget(self._triggers_card(vm.replan_triggers))

        self._approve.set_action("Approve Race Plan", enabled=vm.has_plan)

    # ---- cards ------------------------------------------------------------
    def _option_card(self, opt: StrategyOption) -> QWidget:
        card = Card()
        card.setStyleSheet(
            f"#ngrCard {{ background: {_t.CARBON_RAISED}; "
            f"border: 1px solid {_t.HAIRLINE}; "
            f"border-left: 3px solid {_t.NGR_GREEN if opt.recommended else _t.HAIRLINE}; "
            f"border-radius: {_t.RADIUS_MD}px; }}")
        head = QHBoxLayout()
        name = QLabel(opt.name + ("  ★ recommended" if opt.recommended else ""))
        name.setStyleSheet(
            f"color: {_t.TEXT_HI if opt.recommended else _t.TEXT}; font-weight: 700; "
            f"font-size: {_t.FS_H3}pt;")
        head.addWidget(name)
        head.addStretch(1)
        head.addWidget(ConfidenceMeter(opt.confidence))
        card.body.addLayout(head)

        grid = QGridLayout()
        grid.setHorizontalSpacing(_t.SPACE_XL)
        grid.setVerticalSpacing(2)
        specs = [("Total time", opt.total_time), ("Expected laps", opt.expected_laps),
                 ("Tyres", opt.tyre_sequence), ("Fuel", opt.fuel_target),
                 ("Pit windows", opt.pit_windows)]
        col = 0
        for cap, val in specs:
            if not val:
                continue
            c = QLabel(cap)
            c.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
            v = QLabel(str(val))
            v.setStyleSheet(f"color: {_t.TEXT_HI}; font-size: {_t.FS_LABEL}pt; font-weight: 600;")
            grid.addWidget(c, 0, col)
            grid.addWidget(v, 1, col)
            col += 1
        card.body.addLayout(grid)

        if opt.stints:
            st = QLabel("Stints:  " + "  →  ".join(opt.stints))
            st.setWordWrap(True)
            st.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
            card.body.addWidget(st)
        if opt.summary:
            s = QLabel(opt.summary)
            s.setWordWrap(True)
            s.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
            card.body.addWidget(s)
        return card

    def _risks_row(self, risks) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(_caption("Risks:"))
        for label, level in risks:
            tone = {"high": "danger", "medium": "warn", "med": "warn", "low": "success"}.get(
                str(level).lower(), "neutral")
            h.addWidget(StatusPill(f"{label}: {level}", tone=tone))
        h.addStretch(1)
        return w

    def _inputs_card(self, inputs) -> QWidget:
        card = Card()
        card.add(_caption("Inputs — measured vs assumed"))
        for inp in inputs:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            nm = QLabel(f"{inp.name}: {inp.value}" if inp.value else inp.name)
            nm.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_CAPTION}pt;")
            tone = _SOURCE_TONE.get(str(inp.source).lower(), "neutral")
            row.addWidget(nm)
            row.addStretch(1)
            row.addWidget(StatusPill(str(inp.source), tone=tone))
            card.body.addLayout(row)
        return card

    def _triggers_card(self, triggers) -> QWidget:
        card = Card()
        card.add(_caption("Replan if…"))
        t = QLabel("• " + "\n• ".join(str(x) for x in triggers))
        t.setWordWrap(True)
        t.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        card.add(t)
        return card


def _caption(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {_t.NGR_GREEN}; font-weight: 700; font-size: {_t.FS_CAPTION}pt;")
    return lbl


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())
