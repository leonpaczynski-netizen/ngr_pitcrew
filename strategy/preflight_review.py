"""Engineering experiment pre-flight review (Engineering Brain Phase 10).

Before the selected experiment is presented to the driver, this READ-ONLY module
performs a deterministic engineering pre-flight review of the EXACT Phase-5 selection:
what engineering consequences the driver should know before trying it. It assembles
fixed review sections, the change consequences and the engineering checklist + risk
level — all from already-canonical outputs (Phase-5 candidate, Phase-9 context, Phase-8
memory, the coupled interaction graph).

Phase 10 NEVER creates experiments, changes priorities/ranking, changes setup values,
blocks recommendations, changes working windows, or mutates evidence/memory/outcomes.
It receives the selection verbatim and reports.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock; deterministic re-projection only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Sequence, Tuple

from strategy.change_consequences import (
    ChangeConsequence, coupled_fields, derive_consequences,
)
from strategy.engineering_checklist import (
    ChecklistItem, RiskLevel, build_checklist,
)

PREFLIGHT_REVIEW_VERSION = "preflight_review_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


class SectionSeverity(str, Enum):
    OK = "ok"
    INFO = "info"
    CAUTION = "caution"
    RISK = "risk"


@dataclass(frozen=True)
class ReviewLine:
    text: str
    evidence: str = ""
    supporting_sessions: Tuple[str, ...] = ()
    confidence: str = ""

    def to_dict(self) -> dict:
        return {"text": self.text, "evidence": self.evidence,
                "supporting_sessions": list(self.supporting_sessions),
                "confidence": self.confidence}


@dataclass(frozen=True)
class PreFlightSection:
    key: str
    title: str
    severity: str                       # SectionSeverity value
    lines: Tuple[ReviewLine, ...]

    def to_dict(self) -> dict:
        return {"key": self.key, "title": self.title, "severity": self.severity,
                "lines": [l.to_dict() for l in self.lines]}


@dataclass(frozen=True)
class PreFlightReview:
    experiment: dict                    # the EXACT Phase-5 selection (echoed, unmodified)
    sections: Tuple[PreFlightSection, ...]
    consequences: Tuple[ChangeConsequence, ...]
    checklist: Tuple[ChecklistItem, ...]
    risk_level: str                     # RiskLevel value
    summary: str
    content_fingerprint: str
    eval_version: str = PREFLIGHT_REVIEW_VERSION

    def to_dict(self) -> dict:
        return {
            "experiment": self.experiment,
            "sections": [s.to_dict() for s in self.sections],
            "consequences": [c.to_dict() for c in self.consequences],
            "checklist": [c.to_dict() for c in self.checklist],
            "risk_level": self.risk_level, "summary": self.summary,
            "content_fingerprint": self.content_fingerprint,
            "eval_version": self.eval_version,
        }


def _experiment_echo(candidate: Mapping) -> dict:
    """Echo the exact Phase-5 selection — never modified, never re-selected."""
    keys = ("candidate_id", "target_issue", "target_phase", "target_corners", "field",
            "subsystem", "current_value", "proposed_value", "delta", "direction",
            "hypothesis", "expected_positive_effect", "window_relationship",
            "evidence_grade", "supporting_evidence", "selection_rationale")
    return {k: candidate.get(k) for k in keys if k in candidate}


def _field_transfers(context: Mapping, field: str, kind: str) -> list:
    field = _lc(field)
    return [t for t in (context or {}).get("transfers") or []
            if _lc(t.get("field")) == field and t.get("kind") == kind]


def build_preflight_review(
    candidate: Mapping, *, context: Optional[Mapping] = None,
    memory: Optional[Mapping] = None, interactions: Optional[Mapping] = None,
) -> PreFlightReview:
    """Assemble the deterministic pre-flight review for the exact Phase-5 selection.
    ``candidate`` = the Phase-5 selection dict, ``context`` = the Phase-9
    ``build_engineering_context`` result for the proposed change, ``memory`` = the
    Phase-8 ``build_cross_session_memory`` result. All inputs are read-only."""
    context = context or {}
    memory = memory or {}
    field = _norm(candidate.get("field"))
    direction = _norm(candidate.get("direction"))

    consequences = derive_consequences(candidate, context=context,
                                       interactions=interactions)
    checklist, risk = build_checklist(candidate, context=context, memory=memory,
                                      interactions=interactions)

    sections: List[PreFlightSection] = []

    def _sec(key, title, severity, lines):
        if lines:
            sections.append(PreFlightSection(key=key, title=title,
                                             severity=severity.value,
                                             lines=tuple(lines)))

    # 1) Evidence quality
    ev_lines = [ReviewLine(f"evidence grade: {_norm(candidate.get('evidence_grade')) or 'unknown'}")]
    for e in (candidate.get("supporting_evidence") or ())[:6]:
        if _norm(e):
            ev_lines.append(ReviewLine(_norm(e), evidence="phase5 selection"))
    _sec("evidence_quality", "Evidence quality", SectionSeverity.INFO, ev_lines)

    # 2) Working-window confidence
    wr = _norm(candidate.get("window_relationship"))
    win_sev = (SectionSeverity.CAUTION
               if ("edge" in _lc(wr) or "outside" in _lc(wr)) else SectionSeverity.OK)
    _sec("working_window", "Working-window confidence", win_sev,
         [ReviewLine(f"window relationship: {wr or 'no learned window'}",
                     evidence="phase5 working window")])

    # 3) Protected behaviour impact
    at_risk = list(candidate.get("protected_behaviours_at_risk") or ())
    prot_risks = [r for r in (context.get("regression_risks") or [])
                  if r.get("kind") == "protected_field_conflict"
                  and _lc(r.get("field")) == _lc(field)]
    prot_lines = [ReviewLine(f"at risk: {b}", evidence="phase5 selection") for b in at_risk]
    prot_lines += [ReviewLine(_norm(r.get("reason")), evidence=_norm(r.get("evidence_source")),
                              supporting_sessions=tuple(r.get("supporting_sessions") or ()),
                              confidence=_norm(r.get("confidence"))) for r in prot_risks]
    if not prot_lines:
        prot_lines = [ReviewLine("no protected behaviour is touched by this change")]
    _sec("protected_impact", "Protected behaviour impact",
         SectionSeverity.RISK if (at_risk or prot_risks) else SectionSeverity.OK, prot_lines)

    # 4) Historical success / 5) Historical failure
    succ = _field_transfers(context, field, "successful_experiment")
    _sec("historical_success", "Historical success", SectionSeverity.OK,
         [ReviewLine(_norm(t.get("detail")), evidence=f"{t.get('strength')} match",
                     supporting_sessions=tuple(t.get("supporting_sessions") or ()),
                     confidence="confirmed" if t.get("confirmed") else "provisional")
          for t in succ])
    fail = _field_transfers(context, field, "failed_experiment")
    _sec("historical_failure", "Historical failure", SectionSeverity.CAUTION,
         [ReviewLine(_norm(t.get("detail")), evidence=f"{t.get('strength')} match",
                     supporting_sessions=tuple(t.get("supporting_sessions") or ()),
                     confidence="confirmed" if t.get("confirmed") else "provisional")
          for t in fail])

    # 6) Regression risk
    risks = [r for r in (context.get("regression_risks") or [])
             if _lc(r.get("field")) == _lc(field)]
    _sec("regression_risk", "Regression risk", SectionSeverity.RISK,
         [ReviewLine(_norm(r.get("reason")),
                     evidence=f"{r.get('severity')} · {r.get('evidence_source')}",
                     supporting_sessions=tuple(r.get("supporting_sessions") or ()),
                     confidence=_norm(r.get("confidence"))) for r in risks])

    # 7) Known constraints
    cons = [c for c in (context.get("constraints") or [])
            if _lc(c.get("field")) == _lc(field)]
    _sec("known_constraints", "Known constraints", SectionSeverity.CAUTION,
         [ReviewLine(_norm(c.get("detail")), evidence=_norm(c.get("evidence_source")),
                     supporting_sessions=tuple(c.get("supporting_sessions") or ()),
                     confidence=_norm(c.get("confidence"))) for c in cons])

    # 8) Interaction risks (the candidate's coupled negatives)
    _sec("interaction_risks", "Interaction risks", SectionSeverity.CAUTION,
         [ReviewLine(_norm(n), evidence="phase5 interaction graph")
          for n in (candidate.get("expected_negative_effects") or ()) if _norm(n)])

    # 9) Coupled fields
    _sec("coupled_fields", "Coupled fields", SectionSeverity.INFO,
         [ReviewLine(f"{other} (shared {axis.replace('_', ' ')})",
                     evidence="parameter interaction graph")
          for other, axis in coupled_fields(field, interactions)])

    # 10) Driver familiarity
    tried = len({e for t in (succ + fail) for e in (t.get("supporting_experiments") or [])})
    fam = (f"tried {tried} time(s) before in compatible contexts" if tried
           else "new field for this context")
    _sec("driver_familiarity", "Driver familiarity", SectionSeverity.INFO,
         [ReviewLine(fam, evidence="development history")])

    # 11) Outstanding residual issues
    remaining = [im for im in (memory.get("memory") or {}).get("issues") or []
                 if not im.get("currently_resolved")]
    _sec("outstanding_residuals", "Outstanding residual issues", SectionSeverity.CAUTION,
         [ReviewLine(f"{im.get('issue_type', 'issue')} @ {im.get('corner') or '—'} "
                     f"({im.get('latest_state', '')})", evidence="cross-session memory")
          for im in remaining])

    # 12) Current engineering state
    scb = (memory.get("scorecard") or {}).get("band")
    met = memory.get("metrics") or {}
    _sec("current_state", "Current engineering state", SectionSeverity.INFO,
         [ReviewLine(f"development band: {scb or 'building picture'}",
                     evidence="cross-session scorecard"),
          ReviewLine(f"issues remaining: {met.get('issues_remaining', 0)}, "
                     f"solved: {met.get('issues_solved', 0)}",
                     evidence="progress metrics")])

    summary = (f"Pre-flight for {field} {direction} → {candidate.get('proposed_value')}: "
               f"risk {risk.value}; {sum(1 for i in checklist if i.status == 'caution')} caution(s), "
               f"{sum(1 for i in checklist if i.status == 'ok')} clear.")

    fp = _fingerprint(candidate, sections, consequences, checklist, risk)
    return PreFlightReview(
        experiment=_experiment_echo(candidate), sections=tuple(sections),
        consequences=consequences, checklist=checklist, risk_level=risk.value,
        summary=summary, content_fingerprint=fp)


def _fingerprint(candidate, sections, consequences, checklist, risk) -> str:
    payload = {
        "v": PREFLIGHT_REVIEW_VERSION,
        "exp": {k: candidate.get(k) for k in ("field", "direction", "proposed_value",
                                              "target_issue", "candidate_id")},
        "sections": [s.to_dict() for s in sections],
        "consequences": [c.to_dict() for c in consequences],
        "checklist": [c.to_dict() for c in checklist],
        "risk": risk.value,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return f"{PREFLIGHT_REVIEW_VERSION}:{hashlib.sha256(raw.encode()).hexdigest()[:24]}"
