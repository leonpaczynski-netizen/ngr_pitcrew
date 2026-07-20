"""Integrated Race-Engineer Team Brief — Layer 7 of the Race-Engineer Activation (Program 2, Phase 38).

Assembles the Phase-36 context activation and the Phase-37 setup / driver learning into ONE
deterministic, coordinated crew brief with role-specific but non-duplicated sections (Chief Engineer,
Setup Engineer, Performance/Data Engineer, Driver Coach, Strategy Engineer). These are VIEWS over the
same shared canonical evidence - not five independent authorities or AI personas.

The brief resolves contradictory advice: it never simultaneously recommends mutually opposing setup or
driving actions. Where a setup experiment and a coaching test would confound each other, they are
SEQUENCED (one held constant while the other is tested) and surfaced as ordered, alternative controlled
hypotheses - so the driver receives one coherent plan for the current event, not several disconnected
reports.

Doctrine: newer is not better; a blocked failed direction is never re-recommended; an incremental
experiment is never labelled a complete or "ultimate" setup; missing evidence is stated honestly and
produces a collection plan rather than a fabricated answer.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises. Authors NO setup value; creates no experiment; applies NOTHING.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple

RACE_ENGINEER_TEAM_BRIEF_VERSION = "race_engineer_team_brief_v1"
RACE_ENGINEER_TEAM_BRIEF_SCHEMA = 1

_ADVISORY = ("Read-only, advisory-only integrated race-engineer brief. It coordinates the current "
             "best-PROVEN engineering picture, known working windows, open uncertainty and the next "
             "controlled step. It is NOT a certification, NOT a complete or 'ultimate' setup, NOT an "
             "experiment, and NOT permission to Apply. It carries no setup values and changes nothing.")


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{RACE_ENGINEER_TEAM_BRIEF_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


@dataclass(frozen=True)
class RaceEngineerTeamBrief:
    scope: dict
    context_fingerprint: str
    completeness: str
    chief_engineer: dict
    setup_engineer: dict
    performance_engineer: dict
    driver_coach: dict
    strategy_engineer: dict
    ordered_development_plan: Tuple[dict, ...]
    contradictions: Tuple[dict, ...]
    empty_state: str
    advisory_statement: str
    content_fingerprint: str
    subordinate_fingerprints: dict
    schema_version: int = RACE_ENGINEER_TEAM_BRIEF_SCHEMA
    eval_version: str = RACE_ENGINEER_TEAM_BRIEF_VERSION

    def to_dict(self) -> dict:
        return {"scope": dict(self.scope), "context_fingerprint": self.context_fingerprint,
                "completeness": self.completeness, "chief_engineer": dict(self.chief_engineer),
                "setup_engineer": dict(self.setup_engineer),
                "performance_engineer": dict(self.performance_engineer),
                "driver_coach": dict(self.driver_coach),
                "strategy_engineer": dict(self.strategy_engineer),
                "ordered_development_plan": [dict(a) for a in self.ordered_development_plan],
                "contradictions": [dict(c) for c in self.contradictions],
                "empty_state": self.empty_state, "advisory_statement": self.advisory_statement,
                "content_fingerprint": self.content_fingerprint,
                "subordinate_fingerprints": dict(self.subordinate_fingerprints),
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def build_race_engineer_team_brief(scope: Optional[Mapping], activation: Optional[Mapping],
                                   outcome_learning: Optional[Mapping],
                                   working_windows: Optional[Mapping],
                                   driver_development: Optional[Mapping],
                                   coaching_plan: Optional[Mapping], *,
                                   next_experiment: Optional[Mapping] = None,
                                   strategy_context: Optional[Mapping] = None
                                   ) -> RaceEngineerTeamBrief:
    """Assemble the coordinated crew brief from the already-built Phase-36/37 products (all dicts).
    ``next_experiment`` is an OPTIONAL reference to an existing canonical bounded experiment/candidate
    (never created here). ``strategy_context`` is OPTIONAL race-plan evidence. Deterministic; never
    raises."""
    try:
        return _build(scope or {}, activation or {}, outcome_learning or {}, working_windows or {},
                      driver_development or {}, coaching_plan or {},
                      next_experiment if isinstance(next_experiment, Mapping) else None,
                      strategy_context if isinstance(strategy_context, Mapping) else None)
    except Exception:  # pragma: no cover - defensive
        return RaceEngineerTeamBrief(
            scope={}, context_fingerprint="", completeness="insufficient", chief_engineer={},
            setup_engineer={}, performance_engineer={}, driver_coach={}, strategy_engineer={},
            ordered_development_plan=(), contradictions=(), empty_state="Team brief unavailable.",
            advisory_statement=_ADVISORY, content_fingerprint=_fp({"error": True}),
            subordinate_fingerprints={})


def _sub_fp(d: Optional[Mapping]) -> str:
    return _norm((d or {}).get("content_fingerprint"))


def _build(scope: Mapping, activation: Mapping, outcome: Mapping, windows: Mapping,
           driver: Mapping, coaching: Mapping, next_exp: Optional[Mapping],
           strategy: Optional[Mapping]) -> RaceEngineerTeamBrief:
    completeness = _lc(scope.get("completeness")) or "insufficient"
    ctx_fp = _norm(scope.get("context_fingerprint"))
    objective = (f"{scope.get('label') or 'unknown context'} - "
                 f"{_lc(scope.get('discipline')) or 'unknown'} programme.")

    lineage = outcome.get("lineage") or []
    current_state = outcome.get("current_state") or {}
    rollback = outcome.get("rollback_plan") or {}
    blocked = outcome.get("blocked_directions") or []
    protected = outcome.get("protected_behaviours") or []
    ww = windows.get("windows") or []
    priorities = coaching.get("priorities") or []
    dims = driver.get("dimensions") or []
    counts = activation.get("counts") or {}

    has_any = bool(lineage or dims or ww or priorities)

    # ---- highest-priority problem ---------------------------------------- #
    if rollback.get("needed"):
        highest = ("A recently applied change worsened the car - roll back or reverse the failed "
                   "delta before anything else.")
    elif priorities:
        p0 = priorities[0]
        highest = (f"Driver-attributable limitation: {_lc(p0.get('dimension')).replace('_',' ')}"
                   + (f" at {p0.get('corner')}" if p0.get('corner') else "") + ".")
    elif any(_lc(w.get("status")) == "avoid" for w in ww):
        highest = "A setup field has a regression-associated value to avoid; keep within proven windows."
    elif any(_lc(w.get("status")) == "explore" for w in ww):
        highest = "A promising but unconverged setup field could be improved with a bounded experiment."
    elif not has_any:
        highest = "No established evidence yet - the priority is to collect a first controlled baseline."
    else:
        highest = "Consolidate and protect the current proven windows; collect evidence for blind spots."

    # ---- contradiction resolution ---------------------------------------- #
    contradictions: List[dict] = []
    coaching_needs_hold = any(bool(p.get("hold_setup_constant")) for p in priorities)
    has_next_exp = bool(next_exp)
    if coaching_needs_hold and has_next_exp:
        contradictions.append({
            "kind": "coaching_vs_setup_experiment",
            "description": ("a coaching test needs the setup held constant while a bounded setup "
                            "experiment would change it - these cannot run simultaneously."),
            "resolution": ("sequence them: run the higher-priority test first with the other held "
                           "constant, then the second; do not change both at once."),
            "discriminating_test": ("run the setup experiment and the coaching test in separate "
                                    "sessions so each effect is attributable.")})
    # opposing directional advice on the same field (blocked direction vs a generic push)
    if rollback.get("needed") and any(_lc(w.get("status")) == "explore" for w in ww):
        contradictions.append({
            "kind": "explore_vs_rollback",
            "description": "a field looks worth exploring, but the current state is a regression.",
            "resolution": "resolve the regression (rollback/reverse) first, then explore from a stable base.",
            "discriminating_test": "re-baseline after rollback before starting any new exploration."})

    # ---- ordered development plan (the single coherent plan) ------------- #
    plan: List[dict] = []

    def _add(action, rationale, hold=""):
        plan.append({"step": len(plan) + 1, "action": action, "rationale": rationale,
                     "hold_constant": hold})

    if rollback.get("needed"):
        _add(f"Roll back / reverse the failed delta (target {rollback.get('target') or 'baseline'}).",
             rollback.get("note") or "the last applied change worsened the car.", "the blocked direction")
    # decide setup-experiment vs coaching ordering when they conflict
    coaching_first = bool(priorities) and (not has_next_exp or _lc(current_state.get("verdict"))
                                           != "worsened") and coaching_needs_hold
    if priorities and coaching_first:
        p0 = priorities[0]
        _add(f"Run the coaching test: {p0.get('technique_focus')}"
             + (f" at {p0.get('corner')}" if p0.get('corner') else "") + ".",
             p0.get("why_it_matters") or "highest driver-attributable gain.",
             "the setup" if p0.get("hold_setup_constant") else "")
    if has_next_exp and not rollback.get("needed"):
        _add(f"Run the next bounded experiment: {_describe_experiment(next_exp)}.",
             "the smallest legal reversible step toward the open question; not a final setup.",
             "driver technique" if coaching_needs_hold else "")
    if priorities and not coaching_first:
        p0 = priorities[0]
        _add(f"Coaching focus: {p0.get('technique_focus')}"
             + (f" at {p0.get('corner')}" if p0.get('corner') else "") + ".",
             p0.get("why_it_matters") or "driver-attributable gain.",
             "the setup" if p0.get("hold_setup_constant") else "")
    # evidence collection for blind spots
    missing = _missing_evidence(activation, windows, driver)
    if missing:
        _add("Collect evidence: " + missing[0], "close the highest-value blind spot before deciding.")
    if not plan:
        _add("Collect a first controlled baseline in this exact context.",
             "there is no established evidence to act on yet.")

    # ---- role sections (views over the shared evidence) ------------------ #
    chief = {
        "objective": objective, "context_readiness": completeness,
        "highest_priority_problem": highest,
        "conflicts": [c["description"] for c in contradictions],
        "ordered_actions": [f"{a['step']}. {a['action']}" for a in plan],
        "stop_defer_conditions": _stop_conditions(completeness, rollback, counts)}

    setup_eng = {
        "current_best_known_setup": _current_best(current_state, lineage),
        "not_an_ultimate_setup": ("this is the best currently PROVEN state, not a complete or "
                                  "'ultimate' setup."),
        "confirmed_good_to_protect": [p.get("behaviour") for p in protected],
        "working_windows": [{"field": w.get("field"), "status": w.get("status"),
                             "window": f"{w.get('window_min') or '-'}..{w.get('window_max') or '-'}",
                             "confidence": w.get("confidence")} for w in ww],
        "latest_outcome": current_state,
        "next_experiment": (_describe_experiment(next_exp) if has_next_exp
                            else "no canonical bounded experiment supplied - see the collection plan."),
        "rollback_plan": rollback,
        "success_criteria": ("the targeted behaviour improves without damaging a protected strength; "
                             "the change stays inside the proven window."),
        "failure_criteria": ("a protected strength regresses, a blocked direction is repeated, or the "
                             "change moves outside the proven window.")}

    perf_eng = _performance_engineer(dims, ww, priorities, activation)

    coach = {
        "priorities": [{"dimension": p.get("dimension"), "corner": p.get("corner"),
                        "technique_focus": p.get("technique_focus"),
                        "success_criterion": p.get("success_criterion"),
                        "verification": p.get("confirming_evidence"), "falsifier": p.get("falsifier"),
                        "hold_setup_constant": p.get("hold_setup_constant")}
                       for p in priorities[:2]],
        "note": ("coach one or two priorities at a time; verify each against its measurable criterion "
                 "before moving on.")}

    strat_eng = _strategy_engineer(scope, strategy, priorities, has_next_exp)

    empty = "" if has_any else (
        "No established engineering evidence in this exact context yet. The honest plan is to collect a "
        "first controlled baseline - not to apply generic setup values or invent coaching.")

    subs = {"activation": _sub_fp(activation), "outcome_learning": _sub_fp(outcome),
            "working_windows": _sub_fp(windows), "driver_development": _sub_fp(driver),
            "coaching_plan": _sub_fp(coaching)}
    fp = _fp({"ctx": ctx_fp, "completeness": completeness, "subs": subs,
              "plan": [(a["step"], a["action"]) for a in plan],
              "highest": highest,
              "contradictions": [c["kind"] for c in contradictions]})
    return RaceEngineerTeamBrief(
        scope=dict(scope), context_fingerprint=ctx_fp, completeness=completeness, chief_engineer=chief,
        setup_engineer=setup_eng, performance_engineer=perf_eng, driver_coach=coach,
        strategy_engineer=strat_eng, ordered_development_plan=tuple(plan),
        contradictions=tuple(contradictions), empty_state=empty, advisory_statement=_ADVISORY,
        content_fingerprint=fp, subordinate_fingerprints=subs)


def _describe_experiment(exp: Optional[Mapping]) -> str:
    if not isinstance(exp, Mapping) or not exp:
        return "none"
    fld = _norm(exp.get("field")) or _norm(exp.get("title")) or _norm(exp.get("hypothesis"))
    direction = _norm(exp.get("direction"))
    eid = _norm(exp.get("id") or exp.get("experiment_id"))
    bits = [b for b in (fld, direction) if b]
    return (" ".join(bits) or "existing canonical experiment") + (f" (ref {eid})" if eid else "")


def _current_best(current_state: Mapping, lineage) -> str:
    if not lineage:
        return "no proven applied state yet."
    verdict = _lc(current_state.get("verdict"))
    if verdict == "worsened":
        return ("the last applied change regressed; the best PROVEN state is the prior applied setup "
                "(see rollback plan).")
    rk = _norm(current_state.get("record_key"))
    return f"the most recent non-regressing applied state ({rk or 'latest review'})."


def _stop_conditions(completeness: str, rollback: Mapping, counts: Mapping) -> List[str]:
    out = []
    if completeness in ("insufficient", "partial"):
        out.append("context is incomplete - resolve the missing identity before trusting cross-context "
                   "evidence.")
    if rollback.get("needed"):
        out.append("do not start new exploration until the current regression is resolved.")
    if int(counts.get("excluded", 0) or 0) > 0:
        out.append("excluded (incompatible) evidence exists - it must not drive any recommendation.")
    if not out:
        out.append("stop if a protected strength regresses or a blocked direction is proposed.")
    return out


def _performance_engineer(dims, ww, priorities, activation) -> dict:
    repeatable = [{"dimension": d.get("dimension"), "category": d.get("category"),
                   "trend": d.get("trend"), "attribution": d.get("attribution"),
                   "evidence_count": d.get("evidence_count")}
                  for d in dims if int(d.get("evidence_count") or 0) >= 2]
    losses = [d.get("dimension") for d in dims if _lc(d.get("category")) == "development_area"]
    strengths = [d.get("dimension") for d in dims if _lc(d.get("category")) == "strength"]
    gear = [{"corner": p.get("corner"), "assessment": p.get("gear_drive_out")}
            for p in priorities if p.get("gear_drive_out")]
    missing = _missing_evidence(activation, {"windows": ww}, {"dimensions": dims})
    return {"repeatable_findings": repeatable, "corner_losses": losses,
            "corner_strengths": strengths, "gear_drive_out_findings": gear,
            "confidence": ("higher where evidence_count and independence are higher; single-context "
                           "findings are flagged."),
            "missing_evidence": missing,
            "recommended_collection": (missing[:2] if missing else
                                       ["repeat the highest-value corner across independent sessions."])}


def _strategy_engineer(scope, strategy, priorities, has_next_exp) -> dict:
    discipline = _lc(scope.get("discipline"))
    s = strategy if isinstance(strategy, Mapping) else {}
    have_plan = bool(s)
    implications = []
    if discipline == "race":
        implications.append("Race pace depends on tyre and fuel management across the stint, not one "
                            "lap - protect tyre life and drive-out over peak qualifying gearing.")
    elif discipline == "qualifying":
        implications.append("Qualifying optimises one lap - do not carry this gearing/setup to the "
                            "race without race-context evidence.")
    risk = ("a setup or coaching experiment in this session could compromise race preparation - run it "
            "with the race plan held constant." if (has_next_exp or priorities) else "")
    evidence_required = []
    if not have_plan:
        evidence_required = ["no race-plan evidence supplied - collect stint length, tyre-wear rate, "
                             "fuel-per-lap and pit-loss before trusting a race plan."]
    return {"race_plan_implications": implications,
            "tyre_fuel_stint_evidence": (s.get("evidence") if have_plan else []),
            "experiment_risk_to_race_prep": risk, "evidence_required": evidence_required,
            "note": "Strategy is a view over shared evidence; it fabricates no pit stop or stint."}


def _missing_evidence(activation, windows, driver) -> List[str]:
    out: List[str] = []
    ww = (windows or {}).get("windows") or []
    for w in ww:
        if _lc(w.get("status")) == "insufficient":
            out.append(f"more exact-context evidence for setup field '{w.get('field')}'.")
    for d in ((driver or {}).get("dimensions") or []):
        if _lc(d.get("category")) == "insufficient" or int(d.get("session_count") or 0) < 2:
            out.append(f"repeated evidence for driver dimension '{d.get('dimension')}'.")
    counts = (activation or {}).get("counts") or {}
    if int(counts.get("exact_context", 0) or 0) == 0 and int(counts.get("explicitly_transferable", 0)
                                                             or 0) > 0:
        out.append("exact-context evidence (only transferable evidence exists so far).")
    # de-dup, deterministic order
    return list(dict.fromkeys(out))


def team_brief_versions() -> dict:
    return {"race_engineer_team_brief": RACE_ENGINEER_TEAM_BRIEF_VERSION,
            "schema": RACE_ENGINEER_TEAM_BRIEF_SCHEMA}
