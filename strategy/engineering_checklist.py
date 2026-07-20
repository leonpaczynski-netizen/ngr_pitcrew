"""Engineering pre-flight checklist + risk summary (Engineering Brain Phase 10).

Turns the Phase-5 selected experiment + the Phase-9 context (transfers, constraints,
regression risks) + the Phase-8 memory (outstanding issues, familiarity) + the coupled
interaction graph into a deterministic checklist (✓ / ⚠) and a descriptive risk level
(LOW / MODERATE / HIGH / UNKNOWN). Every item explains why, with its supporting
sessions, confidence and context.

The checklist and risk level are DESCRIPTIVE ONLY — they never change the
recommendation, the ranking, the experiment, the priorities, or any evidence.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock; deterministic.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Sequence, Tuple

from strategy.change_consequences import coupled_fields

ENGINEERING_CHECKLIST_VERSION = "engineering_checklist_v1"


class ChecklistStatus(str, Enum):
    OK = "ok"                           # ✓
    CAUTION = "caution"                 # ⚠
    UNKNOWN = "unknown"                 # ?


class RiskLevel(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    UNKNOWN = "unknown"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


@dataclass(frozen=True)
class ChecklistItem:
    status: str                         # ChecklistStatus value
    label: str
    why: str
    supporting_sessions: Tuple[str, ...]
    confidence: str
    context: str
    eval_version: str = ENGINEERING_CHECKLIST_VERSION

    @property
    def glyph(self) -> str:
        return {"ok": "✓", "caution": "⚠", "unknown": "?"}.get(self.status, "•")

    def to_dict(self) -> dict:
        return {"status": self.status, "glyph": self.glyph, "label": self.label,
                "why": self.why, "supporting_sessions": list(self.supporting_sessions),
                "confidence": self.confidence, "context": self.context,
                "eval_version": self.eval_version}


def _field_transfers(context: Mapping, field: str, kind: str) -> list:
    field = _lc(field)
    return [t for t in (context or {}).get("transfers") or []
            if _lc(t.get("field")) == field and t.get("kind") == kind]


def _field_risks(context: Mapping, field: str) -> list:
    field = _lc(field)
    return [r for r in (context or {}).get("regression_risks") or []
            if _lc(r.get("field")) == field]


def build_checklist(
    candidate: Mapping, *, context: Optional[Mapping] = None,
    memory: Optional[Mapping] = None, interactions: Optional[Mapping] = None,
) -> Tuple[Tuple[ChecklistItem, ...], RiskLevel]:
    """Deterministic checklist + descriptive risk level for the exact Phase-5 selection.
    Never changes the recommendation. Returns (items, risk_level)."""
    context = context or {}
    memory = memory or {}
    field = _norm(candidate.get("field"))
    direction = _lc(candidate.get("direction"))
    items: List[ChecklistItem] = []

    def _add(status, label, why, sessions=(), confidence="", ctx=""):
        items.append(ChecklistItem(
            status=status.value, label=_norm(label), why=_norm(why),
            supporting_sessions=tuple(sorted({_norm(s) for s in sessions if _norm(s)})),
            confidence=_norm(confidence), context=_norm(ctx)))

    # --- inside learned window ------------------------------------------------
    wr = _lc(candidate.get("window_relationship"))
    edge_risk = any(r.get("kind") == "working_window_edge" for r in _field_risks(context, field))
    if wr and ("inside" in wr or wr in ("within_window", "in_window")) and not edge_risk:
        _add(ChecklistStatus.OK, "Inside learned window",
             "the proposed value stays within the learned working window",
             confidence="window")
    elif edge_risk or "edge" in wr or "outside" in wr:
        _add(ChecklistStatus.CAUTION, "At working-window edge",
             "the proposed value is at or beyond the learned working-window edge",
             confidence="window")
    elif not wr:
        _add(ChecklistStatus.UNKNOWN, "No learned window yet",
             "no learned working window exists for this field in this context")

    # --- protected behaviour conflict ----------------------------------------
    prot_risk = [r for r in _field_risks(context, field)
                 if r.get("kind") == "protected_field_conflict"]
    at_risk = list(candidate.get("protected_behaviours_at_risk") or ())
    if prot_risk or at_risk:
        r = prot_risk[0] if prot_risk else {}
        _add(ChecklistStatus.CAUTION, "Protected-behaviour conflict",
             _norm(r.get("reason")) or f"touches a protected behaviour ({', '.join(at_risk)})",
             r.get("supporting_sessions") or (), r.get("confidence") or "",
             "protected")
    else:
        _add(ChecklistStatus.OK, "No protected-behaviour conflict",
             "the change does not touch a known protected behaviour")

    # --- similar experiment succeeded / failed -------------------------------
    succ = _field_transfers(context, field, "successful_experiment")
    fail = _field_transfers(context, field, "failed_experiment")
    if succ:
        best = max(succ, key=lambda t: (t.get("confirmed"), len(t.get("supporting_sessions") or [])))
        _add(ChecklistStatus.OK, "Similar experiment succeeded",
             _norm(best.get("detail")) or "a similar change improved a target issue before",
             best.get("supporting_sessions") or (),
             "confirmed" if best.get("confirmed") else "provisional",
             _norm(best.get("strength")))
    if fail:
        worst = fail[0]
        _add(ChecklistStatus.CAUTION, "Similar experiment failed before",
             _norm(worst.get("detail")) or "a similar change regressed before",
             worst.get("supporting_sessions") or (),
             "confirmed" if worst.get("confirmed") else "provisional",
             _norm(worst.get("strength")))
    if not succ and not fail:
        _add(ChecklistStatus.UNKNOWN, "No comparable history",
             "no prior experiment on this field in a compatible context")

    # --- supporting-session strength -----------------------------------------
    supp = set()
    for t in succ + fail:
        supp.update(t.get("supporting_sessions") or [])
    if succ and len(supp) <= 1:
        _add(ChecklistStatus.CAUTION, "Only one supporting session",
             "the supporting evidence comes from a single session",
             tuple(supp), "provisional")

    # --- regression risks (from Phase 9) -------------------------------------
    for r in _field_risks(context, field):
        kind = _norm(r.get("kind"))
        if kind in ("working_window_edge", "protected_field_conflict"):
            continue                     # already covered above
        # direction-scoped filter for a failed direction
        if kind == "known_failed_direction" and _lc(r.get("direction")) not in ("", direction):
            continue
        _add(ChecklistStatus.CAUTION, _risk_label(kind), _norm(r.get("reason")),
             r.get("supporting_sessions") or (), _norm(r.get("confidence")),
             _norm(r.get("severity")))

    # --- coupled interaction --------------------------------------------------
    coupled = coupled_fields(field, interactions)
    if coupled:
        others = ", ".join(sorted({c[0] for c in coupled}))
        _add(ChecklistStatus.CAUTION, "Coupled interaction exists",
             f"changing {field} interacts with {others}", ctx="interaction graph")

    # --- outstanding residual issues -----------------------------------------
    for im in (memory.get("memory") or {}).get("issues") or []:
        if not im.get("currently_resolved"):
            _add(ChecklistStatus.CAUTION,
                 f"{im.get('issue_type', 'issue')} still unresolved",
                 f"a residual {im.get('issue_type', 'issue')} at "
                 f"{im.get('corner') or 'a corner'} remains from prior sessions",
                 (), "history", "residual")

    items.sort(key=_item_sort_key)
    return tuple(items), _risk_level(candidate, context, items)


def _risk_label(kind: str) -> str:
    return {"known_failed_direction": "Known failed direction",
            "previously_unstable_range": "Previously unstable range",
            "repeated_regression": "Repeated regression",
            "confidence_weakness": "Weak supporting confidence"}.get(
        kind, kind.replace("_", " ").title())


_STATUS_ORDER = {"caution": 0, "unknown": 1, "ok": 2}


def _item_sort_key(it: ChecklistItem) -> tuple:
    return (_STATUS_ORDER.get(it.status, 3), it.label)


def _risk_level(candidate: Mapping, context: Mapping, items) -> RiskLevel:
    """Descriptive aggregation — never blocking."""
    field = _lc(candidate.get("field"))
    risks = [r for r in (context or {}).get("regression_risks") or []
             if _lc(r.get("field")) == field]
    transfers = (context or {}).get("transfers") or []
    matched = (context or {}).get("matched_contexts") or []

    high = any(_lc(r.get("severity")) == "high" for r in risks)
    medium = any(_lc(r.get("severity")) in ("medium",) for r in risks)
    has_history = bool(transfers) or bool(matched)
    cautions = [i for i in items if i.status == "caution"]

    if high:
        return RiskLevel.HIGH
    if not has_history and not risks:
        return RiskLevel.UNKNOWN
    if medium or len(cautions) >= 2:
        return RiskLevel.MODERATE
    if cautions:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def checklist_fingerprint(items: Sequence[ChecklistItem], risk: RiskLevel) -> str:
    raw = json.dumps({"items": [i.to_dict() for i in items], "risk": risk.value},
                     sort_keys=True, separators=(",", ":"))
    return f"{ENGINEERING_CHECKLIST_VERSION}:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"
