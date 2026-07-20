"""Discipline-specific live workflow preconditions (Program 2, Phase 61).

Practice, Qualifying and Race must feel operationally different. This authority checks the discipline-
specific preconditions for a live workflow: Qualifying must use the Qualifying setup discipline and a
low-density view; Race must use the Race setup and a finalised-or-explicitly-accepted strategy state. It
gates nothing autonomously — it reports whether the discipline preconditions hold and what to surface;
the pit-wall mode itself comes from the selected activity type (Phase 58).

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from strategy.event_preparation_cycle import PreparationActivityType
from strategy.ngr_live_pit_wall import LivePitWallMode
from strategy.strategy_maturity import StrategyMaturity

DISCIPLINE_WORKFLOW_VERSION = "discipline_workflow_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _fp(payload) -> str:
    return (f"{DISCIPLINE_WORKFLOW_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


# the expected pit-wall mode for each activity type (mirrors the Phase-58 mode map)
_ACTIVITY_MODE = {
    PreparationActivityType.QUALIFYING: LivePitWallMode.QUALIFYING,
    PreparationActivityType.QUALIFYING_SIMULATION: LivePitWallMode.QUALIFYING,
    PreparationActivityType.RACE: LivePitWallMode.RACE,
    PreparationActivityType.LONG_RACE_RUN: LivePitWallMode.RACE,
    PreparationActivityType.STRATEGY_VALIDATION_RUN: LivePitWallMode.RACE,
}


@dataclass(frozen=True)
class DisciplineWorkflowGate:
    mode: LivePitWallMode
    preconditions_ok: bool
    warnings: Tuple[str, ...]
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"mode": self.mode.value, "preconditions_ok": bool(self.preconditions_ok),
                "warnings": sorted(_norm(w) for w in self.warnings if _norm(w))}


def assess_discipline_workflow(
    activity_type: PreparationActivityType,
    *,
    expected_discipline: str = "",
    strategy_maturity: str = "",
    strategy_finalised: bool = False,
    low_confidence_accepted: bool = False,
) -> DisciplineWorkflowGate:
    """Assess the discipline-specific live workflow preconditions. Qualifying requires the qualifying
    setup discipline; Race requires a finalised (or explicitly low-confidence-accepted) strategy state.
    Warnings are advisory — they never autonomously block driving, but the Race view surfaces them."""
    mode = _ACTIVITY_MODE.get(activity_type, LivePitWallMode.PRACTICE)
    warnings = []
    ok = True

    if mode == LivePitWallMode.QUALIFYING:
        if _norm(expected_discipline).lower() not in ("qualifying", "quali", ""):
            warnings.append("qualifying workflow expects the qualifying setup discipline")
            ok = False
    elif mode == LivePitWallMode.RACE:
        if _norm(expected_discipline).lower() not in ("race", ""):
            warnings.append("race workflow expects the race setup discipline")
            ok = False
        if not (strategy_finalised or low_confidence_accepted):
            warnings.append("race strategy is not finalised or explicitly accepted")
            ok = False

    g = DisciplineWorkflowGate(mode, ok, tuple(warnings), "")
    return DisciplineWorkflowGate(g.mode, g.preconditions_ok, g.warnings, _fp(g.as_payload()))
