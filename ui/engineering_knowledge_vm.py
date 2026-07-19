"""Pure view-model for the Engineering Knowledge panel (Qt-free, Phase 12).

Turns the deterministic Vehicle-Dynamics knowledge base
(``strategy.vehicle_dynamics.build_engineering_knowledge``) into the rows the panel
renders, grouped by Suspension / Differential / Aero / Tyres / Brakes / Transmission /
Weight transfer, plus load-transfer, handling-phase and interaction rows.

READ-ONLY presentation: derives display strings only. No Apply controls. Deterministic;
never raises.
"""
from __future__ import annotations

from typing import List, Tuple

COMPONENT_COLUMNS: Tuple[str, ...] = ("Component", "Primary mechanism", "Raising", "GT7 note")
LOAD_COLUMNS: Tuple[str, ...] = ("Transfer", "Mechanism", "Increased by", "Balance effect")
PHASE_COLUMNS: Tuple[str, ...] = ("Phase", "Dominant mechanism", "Understeer if", "Oversteer if")
INTERACTION_COLUMNS: Tuple[str, ...] = ("A", "B", "Type", "Mechanism")

_GROUP_LABEL = {
    "suspension": "Suspension", "differential": "Differential", "aero": "Aero",
    "tyres": "Tyres", "brakes": "Brakes", "transmission": "Transmission",
    "weight_transfer": "Weight Transfer", "alignment": "Alignment",
}
# The UI display order (spec grouping first, then the rest).
_GROUP_ORDER = ["suspension", "differential", "aero", "tyres", "brakes", "transmission",
                "weight_transfer", "alignment"]


def _titledict(v) -> str:
    return str(v or "").replace("_", " ").title()


def build(result=None) -> dict:
    """Load the knowledge base (static/deterministic) if a result is not supplied."""
    if isinstance(result, dict) and result.get("ok"):
        return result
    try:
        from strategy.vehicle_dynamics import build_engineering_knowledge
        return build_engineering_knowledge()
    except Exception:
        return {"ok": False}


def is_empty(result) -> bool:
    r = build(result)
    return not r.get("ok") or not r.get("component_groups")


def group_titles(result=None) -> List[Tuple[str, str]]:
    """(group_key, display_label) in UI order, only for groups that exist."""
    r = build(result)
    present = {g.get("group"): g for g in r.get("component_groups") or []}
    out = []
    for key in _GROUP_ORDER:
        if key in present:
            out.append((key, _GROUP_LABEL.get(key, _titledict(key))))
    # any groups not in the fixed order, appended stably
    for g in r.get("component_groups") or []:
        if g.get("group") not in dict(out):
            out.append((g.get("group"), _GROUP_LABEL.get(g.get("group"),
                                                         _titledict(g.get("group")))))
    return out


def component_rows(result, group_key: str) -> List[Tuple[str, ...]]:
    r = build(result)
    for g in r.get("component_groups") or []:
        if g.get("group") == group_key:
            rows = []
            for c in g.get("components") or []:
                rows.append((
                    _titledict(c.get("component")),
                    str(c.get("primary_mechanism") or "—"),
                    str(c.get("raise_effect") or "—"),
                    (c.get("gt7_limitations") or ["—"])[0],
                ))
            return rows
    return []


def load_transfer_rows(result=None) -> List[Tuple[str, ...]]:
    r = build(result)
    out = []
    for m in r.get("load_transfer") or []:
        out.append((
            _titledict(m.get("mode")), str(m.get("mechanism") or "—"),
            "; ".join(m.get("increased_by") or []) or "—",
            str(m.get("balance_effect") or "—"),
        ))
    return out


def handling_phase_rows(result=None) -> List[Tuple[str, ...]]:
    r = build(result)
    out = []
    for p in r.get("handling_phases") or []:
        out.append((
            _titledict(p.get("phase")), str(p.get("dominant_mechanism") or "—"),
            str(p.get("understeer_if") or "—"), str(p.get("oversteer_if") or "—"),
        ))
    return out


def interaction_rows(result=None) -> List[Tuple[str, ...]]:
    r = build(result)
    out = []
    for i in r.get("interactions") or []:
        out.append((
            _titledict(i.get("a")), _titledict(i.get("b")),
            _titledict(i.get("interaction_type")), str(i.get("mechanism") or "—"),
        ))
    return out


def lsd_rows(result=None) -> List[Tuple[str, str]]:
    r = build(result)
    return [(_titledict(m.get("parameter")), str(m.get("mechanism") or "—"))
            for m in r.get("lsd_model") or []]


def aero_rows(result=None) -> List[Tuple[str, str]]:
    r = build(result)
    return [(_titledict(a.get("aspect")), str(a.get("mechanism") or "—"))
            for a in r.get("aero_model") or []]
