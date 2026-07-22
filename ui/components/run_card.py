"""RunCard — the Practice run card (F3).

Presents the engineer's specific run plan: objective, the setup under test, the exact
changes being tested, the expected effect, what to monitor, fuel/tyre/laps/push, the
run's purpose, and the conditions that invalidate it. One primary action: Start
Practice Run. Pure presentation over a RunCardVM the caller maps from the canonical
run plan (e.g. strategy.assisted_run_workflow); it computes nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QWidget

from ui import ngr_theme as _t
from ui.components.cards import Card, SectionHeading
from ui.components.buttons import PrimaryActionButton


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


def _tuple(v) -> Tuple[str, ...]:
    if not v:
        return ()
    if isinstance(v, str):
        return (v,)
    try:
        return tuple(str(x).strip() for x in v if str(x).strip())
    except Exception:
        return ()


def _first(d: Mapping, *keys, default=""):
    for k in keys:
        if k in d and d.get(k) not in (None, ""):
            return d.get(k)
    return default


@dataclass(frozen=True)
class RunCardVM:
    objective: str = ""
    setup_label: str = ""
    changes: Tuple[str, ...] = field(default_factory=tuple)
    expected_effect: str = ""
    monitor: Tuple[str, ...] = field(default_factory=tuple)
    fuel: str = ""
    tyre: str = ""
    target_laps: str = ""
    push_level: str = ""
    purpose: str = ""            # pace|consistency|deg|fuel|gearing|diagnosis
    invalidation: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_plan(self) -> bool:
        return bool(self.objective or self.changes or self.setup_label)

    @classmethod
    def from_run_plan(cls, plan: Optional[Mapping]) -> "RunCardVM":
        """Map a run-plan dict to the VM. Tolerant to key naming; never raises."""
        try:
            if not isinstance(plan, Mapping):
                return cls()
            return cls(
                objective=_norm(_first(plan, "objective", "run_objective", "goal")),
                setup_label=_norm(_first(plan, "setup_label", "setup", "setup_name")),
                changes=_tuple(_first(plan, "changes", "changes_tested", "changes_under_test", default=())),
                expected_effect=_norm(_first(plan, "expected_effect", "expected", "hypothesis")),
                monitor=_tuple(_first(plan, "monitor", "monitor_corners", "watch", default=())),
                fuel=_norm(_first(plan, "fuel", "fuel_load", "fuel_liters")),
                tyre=_norm(_first(plan, "tyre", "tyre_compound", "compound")),
                target_laps=_norm(_first(plan, "target_laps", "laps", "lap_count")),
                push_level=_norm(_first(plan, "push_level", "push", "intensity")),
                purpose=_norm(_first(plan, "purpose", "run_type", "run_kind")),
                invalidation=_tuple(_first(plan, "invalidation", "invalidation_conditions",
                                           "abort_conditions", default=())),
            )
        except Exception:
            return cls()


class RunCard(Card):
    start_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrRunCard")
        self._vm = RunCardVM()

        self.body.addWidget(SectionHeading("PRACTICE RUN CARD", level=2))

        self._objective = QLabel()
        self._objective.setWordWrap(True)
        self._objective.setStyleSheet(f"color: {_t.TEXT_HI}; font-size: {_t.FS_H3}pt; font-weight: 600;")
        self.body.addWidget(self._objective)

        self._setup = _dim_label()
        self.body.addWidget(self._setup)

        self._changes = _dim_label()
        self._changes.setWordWrap(True)
        self.body.addWidget(self._changes)

        self._expected = _dim_label()
        self._expected.setWordWrap(True)
        self.body.addWidget(self._expected)

        self._monitor = _dim_label()
        self._monitor.setWordWrap(True)
        self.body.addWidget(self._monitor)

        # Parameter grid: fuel / tyre / laps / push / purpose
        grid = QGridLayout()
        grid.setContentsMargins(0, _t.SPACE_XS, 0, _t.SPACE_XS)
        grid.setHorizontalSpacing(_t.SPACE_LG)
        grid.setVerticalSpacing(2)
        self._params: dict[str, QLabel] = {}
        specs = [("Fuel", "fuel"), ("Tyre", "tyre"), ("Target laps", "target_laps"),
                 ("Push", "push_level"), ("Purpose", "purpose")]
        for i, (cap, key) in enumerate(specs):
            c = QLabel(cap)
            c.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
            v = QLabel("—")
            v.setStyleSheet(f"color: {_t.TEXT_HI}; font-size: {_t.FS_LABEL}pt; font-weight: 600;")
            grid.addWidget(c, 0, i, Qt.AlignmentFlag.AlignHCenter)
            grid.addWidget(v, 1, i, Qt.AlignmentFlag.AlignHCenter)
            self._params[key] = v
        self.body.addLayout(grid)

        self._invalidation = QLabel()
        self._invalidation.setWordWrap(True)
        self._invalidation.setStyleSheet(f"color: {_t.WARN}; font-size: {_t.FS_CAPTION}pt;")
        self.body.addWidget(self._invalidation)

        act = QHBoxLayout()
        self._start = PrimaryActionButton()
        self._start.clicked.connect(lambda: self.start_requested.emit())
        act.addWidget(self._start)
        act.addStretch(1)
        self.body.addLayout(act)

        self._empty = _dim_label()
        self.body.addWidget(self._empty)

        self.set_run(RunCardVM())

    def set_run(self, vm: RunCardVM) -> None:
        if not isinstance(vm, RunCardVM):
            vm = RunCardVM()
        self._vm = vm

        self._objective.setText(vm.objective or "")
        self._objective.setVisible(bool(vm.objective))
        self._set(self._setup, "Setup under test", vm.setup_label)
        self._set(self._changes, "Testing", "  ·  ".join(vm.changes))
        self._set(self._expected, "Expected effect", vm.expected_effect)
        self._set(self._monitor, "Monitor", "  ·  ".join(vm.monitor))

        for key, lbl in self._params.items():
            lbl.setText(getattr(vm, key) or "—")

        if vm.invalidation:
            self._invalidation.setText("Invalidates the run:  " + "  ·  ".join(vm.invalidation))
            self._invalidation.setVisible(True)
        else:
            self._invalidation.setVisible(False)

        self._start.set_action("Start Practice Run", enabled=vm.has_plan)
        self._empty.setText("" if vm.has_plan else "No run planned yet — the engineer will set the next run.")
        self._empty.setVisible(not vm.has_plan)
        # Hide the parameter/section chrome entirely when there's no plan.
        for w in (self._setup, self._changes, self._expected, self._monitor):
            if not vm.has_plan:
                w.setVisible(False)

    @staticmethod
    def _set(label: QLabel, caption: str, value: str) -> None:
        if value:
            label.setText(f"{caption}:  {value}")
            label.setVisible(True)
        else:
            label.setVisible(False)


def _dim_label() -> QLabel:
    lbl = QLabel("")
    lbl.setStyleSheet(f"color: {_t.TEXT}; font-size: {_t.FS_BODY}pt;")
    return lbl
