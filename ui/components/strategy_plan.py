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
from ui.components.buttons import PrimaryActionButton, SecondaryActionButton


# input source -> semantic tone (measured is trustworthy; missing is a red flag)
_SOURCE_TONE = {
    "measured": "success", "derived": "info", "event": "info",
    "manual": "warn", "assumed": "neutral", "default": "neutral", "missing": "danger",
}


@dataclass(frozen=True)
class StrategyOption:
    name: str
    #: Stable candidate id — what selecting this plan reports back.
    key: str = ""
    total_time: str = ""
    expected_laps: str = ""
    stints: Tuple[str, ...] = field(default_factory=tuple)
    tyre_sequence: str = ""
    fuel_target: str = ""
    pit_windows: str = ""
    confidence: str = "unknown"
    summary: str = ""
    #: "best" or "+12.4s" — how this plan compares with the fastest.
    gap: str = ""
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
    #: Build the plan from the runs recorded against this event.
    build_requested = pyqtSignal()
    #: The driver chose a plan (candidate id) — the recommendation is advice, not a rule.
    plan_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrStrategyPlan")
        self._vm = StrategyPlanVM()
        self._selected_key = ""
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
        self._empty.setWordWrap(True)
        self._empty.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        self._root.addWidget(self._empty)
        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet(
            f"color: {_t.NGR_GREEN}; font-size: {_t.FS_LABEL}pt; font-weight: 600;")
        self._status.setVisible(False)
        self._root.addWidget(self._status)

        act = QHBoxLayout()
        # With no plan yet, BUILDING one is the job — approving is meaningless. With a
        # plan, approving is. One primary action either way, never both.
        self._build = PrimaryActionButton("Build the race plan")
        self._build.clicked.connect(lambda: self.build_requested.emit())
        act.addWidget(self._build)
        self._approve = PrimaryActionButton()
        self._approve.clicked.connect(lambda: self.approve_requested.emit())
        act.addWidget(self._approve)
        act.addStretch(1)
        self._root.addLayout(act)
        self._root.addStretch(1)

        self.set_plan(StrategyPlanVM())

    def set_status(self, text: str) -> None:
        """Show (or clear, with "") what the last build attempt did."""
        text = str(text or "")
        self._status.setText(text)
        self._status.setVisible(bool(text))

    def set_selected_plan(self, key: str) -> None:
        """Mark which plan the driver has chosen, and re-render."""
        self._selected_key = str(key or "")
        self.set_plan(self._vm)

    def selected_plan(self) -> str:
        """The chosen plan, defaulting to the recommended one until the driver picks."""
        if self._selected_key:
            return self._selected_key
        for opt in self._vm.options:
            if opt.recommended and opt.key:
                return opt.key
        return ""

    def set_plan(self, vm: StrategyPlanVM) -> None:
        if not isinstance(vm, StrategyPlanVM):
            vm = StrategyPlanVM()
        self._vm = vm
        _clear_layout(self._body)
        self._empty.setVisible(not vm.has_plan)
        # A selection that is no longer among the options must not linger.
        if self._selected_key and self._selected_key not in {o.key for o in vm.options}:
            self._selected_key = ""

        for opt in vm.options:
            self._body.addWidget(self._option_card(opt))

        if vm.risks:
            self._body.addWidget(self._risks_row(vm.risks))
        if vm.inputs:
            self._body.addWidget(self._inputs_card(vm.inputs))
        if vm.replan_triggers:
            self._body.addWidget(self._triggers_card(vm.replan_triggers))

        self._approve.set_action("Approve Race Plan" if vm.has_plan else "",
                                 enabled=vm.has_plan)
        self._build.set_action("Rebuild the race plan" if vm.has_plan
                               else "Build the race plan", enabled=True)

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
        if opt.key and opt.key == self._selected_key:
            chosen = QLabel("✓ your plan")
            chosen.setStyleSheet(
                f"color: {_t.NGR_GREEN}; font-size: {_t.FS_CAPTION}pt; font-weight: 700;")
            head.addWidget(chosen)
        head.addStretch(1)
        # The gap says plainly how this plan compares with the fastest — the missing
        # answer to "how would a 3 stop be quicker than a 2 stop".
        if opt.gap:
            gap = QLabel("fastest" if opt.gap == "best" else opt.gap)
            gap.setStyleSheet(
                f"color: {_t.NGR_GREEN if opt.gap == 'best' else _t.TEXT_DIM}; "
                f"font-size: {_t.FS_CAPTION}pt; font-weight: 700;")
            head.addWidget(gap)
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
        # Any plan can be chosen — the recommendation is advice, not the only option.
        if opt.key:
            row = QHBoxLayout()
            row.addStretch(1)
            if opt.key != self._selected_key:
                btn = SecondaryActionButton("Use this plan")
                btn.clicked.connect(
                    lambda _=False, k=opt.key: self.plan_selected.emit(k))
                row.addWidget(btn)
            card.body.addLayout(row)
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
