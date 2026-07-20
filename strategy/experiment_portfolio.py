"""Experiment Portfolio Optimisation & Information-Gain Selection (Program 2, Phase 17).

The deterministic engineering PLANNER that sits immediately before Phase 15 and decides
"which experiment should the driver perform next?" — optimising for ENGINEERING VALUE
(information gain first), NOT for lap time. It CONSUMES the existing authorities (Phase-15
bounded experiments, the Phase-14 hypotheses embedded in each synthesis result, outcome
history, prediction calibration, working-window protection, confirmed-good behaviour) and
replaces none of them.

It scores every legal candidate experiment across INDEPENDENT, INDIVIDUALLY-VISIBLE
dimensions (no hidden weighted black box — the weights are exposed), ranks them
deterministically, models experiment dependencies, retires experiments with no remaining
engineering value, and emits an advisory roadmap.

It NEVER: mutates a setup / experiment / outcome / reconciliation / calibration, applies
anything, writes to the database, or duplicates any lifecycle or scoring authority.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock
(timestamps are data); deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.experiment_synthesis import EXPERIMENT_SYNTHESIS_VERSION

EXPERIMENT_PORTFOLIO_VERSION = "experiment_portfolio_v1"
EXPERIMENT_PORTFOLIO_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _clamp(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else round(float(x), 6)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class PortfolioRole(str, Enum):
    HIGHEST_VALUE = "highest_value"
    ALTERNATIVE = "alternative"
    DEFERRED = "deferred"
    BLOCKED = "blocked"
    OBSOLETE = "obsolete"
    REDUNDANT = "redundant"


class DependencyKind(str, Enum):
    DEPENDS_ON = "depends_on"                    # B useful only if A succeeds
    UNNECESSARY_IF_FAILS = "unnecessary_if_fails"  # C unnecessary if A fails
    SUPERSEDES = "supersedes"                    # D supersedes E
    MUTUALLY_EXCLUSIVE = "mutually_exclusive"    # same field, opposite directions


class SessionSuitability(str, Enum):
    SUITABLE = "suitable"
    MARGINAL = "marginal"
    UNSUITABLE = "unsuitable"
    UNKNOWN = "unknown"


# The 13 evaluation dimensions, information-gain weighted highest. WEIGHTS ARE VISIBLE — the
# engineering value is a transparent weighted sum, never a hidden black box.
DIMENSION_WEIGHTS: Dict[str, float] = {
    "information_gain": 3.0,             # PRIMARY optimisation objective
    "mechanism_discrimination": 2.0,
    "attribution_quality": 1.5,
    "reversibility": 1.0,
    "protection_of_confirmed_good": 1.5,
    "low_masking_risk": 1.0,
    "low_interaction_complexity": 1.0,
    "low_driver_workload": 0.75,
    "session_suitability": 1.0,
    "remaining_uncertainty": 1.5,
    "proven_history_usefulness": 0.5,
    "prediction_calibration_benefit": 1.0,
    "future_engineering_value": 1.0,
}
_MAX_VALUE = sum(DIMENSION_WEIGHTS.values())


@dataclass(frozen=True)
class ValueDimension:
    name: str
    score: float                # 0..1 (higher = more engineering value on this axis)
    weight: float
    rationale: str

    def to_dict(self) -> dict:
        return {"name": self.name, "score": self.score, "weight": self.weight,
                "weighted": round(self.score * self.weight, 6), "rationale": self.rationale}


@dataclass(frozen=True)
class ExperimentDependency:
    from_id: str
    to_id: str
    kind: str                   # DependencyKind value
    reason: str

    def to_dict(self) -> dict:
        return {"from_id": self.from_id, "to_id": self.to_id, "kind": self.kind,
                "reason": self.reason}


@dataclass(frozen=True)
class ExperimentValuation:
    candidate_id: str
    diagnosis_key: str
    issue_type: str
    field: str
    direction: str
    mechanism_id: str
    attribution_scope: str
    synthesis_status: str
    dimensions: Tuple[ValueDimension, ...]
    engineering_value: float            # transparent weighted sum, 0..1 (normalised)
    role: str                           # PortfolioRole value
    retirement_reason: str
    depends_on: Tuple[str, ...]
    supersedes: Tuple[str, ...]
    protected_good_at_risk: Tuple[str, ...]
    expected_learning: str
    rank: int
    reasons: Tuple[str, ...]

    def dimension(self, name: str) -> Optional[ValueDimension]:
        for d in self.dimensions:
            if d.name == name:
                return d
        return None

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id, "diagnosis_key": self.diagnosis_key,
            "issue_type": self.issue_type, "field": self.field, "direction": self.direction,
            "mechanism_id": self.mechanism_id, "attribution_scope": self.attribution_scope,
            "synthesis_status": self.synthesis_status,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "engineering_value": self.engineering_value, "role": self.role,
            "retirement_reason": self.retirement_reason,
            "depends_on": list(self.depends_on), "supersedes": list(self.supersedes),
            "protected_good_at_risk": list(self.protected_good_at_risk),
            "expected_learning": self.expected_learning, "rank": self.rank,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class RoadmapStage:
    order: int
    kind: str                   # experiment | review | validate | freeze | race
    candidate_id: str
    detail: str

    def to_dict(self) -> dict:
        return {"order": self.order, "kind": self.kind, "candidate_id": self.candidate_id,
                "detail": self.detail}


@dataclass(frozen=True)
class EngineeringPortfolio:
    context_fingerprint: str
    session_context: dict
    session_suitability: str
    valuations: Tuple[dict, ...]        # ranked, all roles
    highest_value: Optional[dict]
    alternatives: Tuple[dict, ...]
    deferred: Tuple[dict, ...]
    blocked: Tuple[dict, ...]
    obsolete: Tuple[dict, ...]
    redundant: Tuple[dict, ...]
    dependencies: Tuple[dict, ...]
    roadmap: Tuple[dict, ...]
    dimension_weights: dict
    safety_statement: str
    audit: Tuple[str, ...]
    content_fingerprint: str
    knowledge_versions: dict
    schema_version: int = EXPERIMENT_PORTFOLIO_SCHEMA
    eval_version: str = EXPERIMENT_PORTFOLIO_VERSION

    def to_dict(self) -> dict:
        return {
            "context_fingerprint": self.context_fingerprint,
            "session_context": dict(self.session_context),
            "session_suitability": self.session_suitability,
            "valuations": [dict(v) for v in self.valuations],
            "highest_value": (dict(self.highest_value) if self.highest_value else None),
            "alternatives": [dict(v) for v in self.alternatives],
            "deferred": [dict(v) for v in self.deferred],
            "blocked": [dict(v) for v in self.blocked],
            "obsolete": [dict(v) for v in self.obsolete],
            "redundant": [dict(v) for v in self.redundant],
            "dependencies": [dict(d) for d in self.dependencies],
            "roadmap": [dict(s) for s in self.roadmap],
            "dimension_weights": dict(self.dimension_weights),
            "safety_statement": self.safety_statement, "audit": list(self.audit),
            "content_fingerprint": self.content_fingerprint,
            "knowledge_versions": dict(self.knowledge_versions),
            "schema_version": self.schema_version, "eval_version": self.eval_version,
        }


_SAFETY = ("Advisory engineering planner. It ranks legal experiments by ENGINEERING VALUE "
           "(information gain first) - not lap time. It reads existing authorities only, "
           "applies nothing, writes nothing, and mutates no setup / experiment / outcome / "
           "calibration. The frozen Apply gate remains the sole route to the car.")


# --------------------------------------------------------------------------- #
# Candidate extraction
# --------------------------------------------------------------------------- #
def _candidates_from_report(report: Mapping) -> List[Tuple[dict, dict]]:
    """Flatten the Phase-15 synthesis report into (candidate, context) pairs. ``context``
    carries the diagnosis / competing-count / synthesis overall status the planner needs."""
    out: List[Tuple[dict, dict]] = []
    seen = set()
    for res in report.get("synthesis_results") or []:
        if not isinstance(res, Mapping):
            continue
        hset = res.get("source_hypothesis_set") or {}
        issue = hset.get("canonical_issue") or {}
        ctx = {
            "diagnosis_key": _norm(hset.get("source_diagnosis_key")),
            "issue_type": _norm(issue.get("issue_type")),
            "competing_count": len(hset.get("competing") or []),
            "overall_status": _lc(res.get("overall_status")),
            "annotation": hset.get("source_annotation") or {},
        }
        cands = []
        if res.get("selected_candidate"):
            cands.append(res["selected_candidate"])
        cands.extend(res.get("alternative_candidates") or [])
        for c in cands:
            if not isinstance(c, Mapping):
                continue
            cid = _norm(c.get("candidate_id"))
            if not cid or cid in seen:
                continue
            seen.add(cid)
            out.append((dict(c), ctx))
    return out


def _primary_delta(candidate: Mapping) -> dict:
    deltas = candidate.get("deltas") or []
    return dict(deltas[0]) if deltas else {}


# --------------------------------------------------------------------------- #
# Outcome history index (for retirement + calibration benefit)
# --------------------------------------------------------------------------- #
def _history_index(outcome_history: Sequence[Mapping]) -> Dict[Tuple[str, str], str]:
    """{(field, coarse_direction): outcome_status} from prior single-field experiments."""
    idx: Dict[Tuple[str, str], str] = {}
    for oh in outcome_history or ():
        if not isinstance(oh, Mapping):
            continue
        flds = [_lc(f) for f in (oh.get("fields") or []) if _lc(f)]
        if len(flds) != 1:
            continue
        direction = _coarse(_lc(oh.get("direction")))
        st = _lc(oh.get("outcome_status"))
        if flds[0] and st:
            idx[(flds[0], direction)] = st
    return idx


_COARSE = {"stiffen": "increase", "soften": "decrease", "raise": "increase",
           "lower": "decrease", "increase": "increase", "decrease": "decrease",
           "increase_locking": "increase", "decrease_locking": "decrease",
           "move_rearward": "increase", "move_forward": "decrease",
           "shorten": "increase", "lengthen": "decrease"}


def _coarse(direction: str) -> str:
    return _COARSE.get(_lc(direction), _lc(direction))


# --------------------------------------------------------------------------- #
# Dimension scoring (each returns (score, rationale))
# --------------------------------------------------------------------------- #
_GRADE_RANK = {"strong": 3, "moderate": 2, "weak": 1, "insufficient": 0, "": 0}


def _dims(candidate: Mapping, ctx: Mapping, *, session: Mapping,
          session_suit: SessionSuitability, calibration: Mapping,
          reconciled_experiment: bool) -> List[ValueDimension]:
    d = _primary_delta(candidate)
    single = _lc(candidate.get("attribution_scope")) == "single_field"
    grade = _lc(candidate.get("evidence_grade"))
    competing = int(ctx.get("competing_count") or 0)
    protected = tuple(candidate.get("protected_good_at_risk")
                      or candidate.get("protected_good_behaviours") or ())
    one_step = bool(d.get("is_exactly_one_step"))
    status = _lc(candidate.get("synthesis_status") or candidate.get("status"))

    def dim(name, score, why):
        return ValueDimension(name, _clamp(score), DIMENSION_WEIGHTS[name], why)

    # 1 information gain — highest when it discriminates competing mechanisms + isolates one
    #    variable + the current evidence is weak (more to learn); low when already strong.
    ig = 0.35
    if competing >= 2:
        ig += 0.35
    if single:
        ig += 0.15
    ig += 0.15 * (1 - _GRADE_RANK.get(grade, 0) / 3.0)
    info = dim("information_gain", ig,
               f"{'discriminates competing mechanisms; ' if competing >= 2 else ''}"
               f"{'isolates one variable; ' if single else ''}evidence grade {grade or 'n/a'}")

    # 2 mechanism discrimination
    md = 0.9 if competing >= 2 else (0.5 if competing == 1 else 0.2)
    disc = dim("mechanism_discrimination", md,
               f"{competing} competing mechanism(s) for this diagnosis")

    # 3 attribution quality — single-field one-step is cleanest
    aq = 1.0 if (single and one_step) else 0.6 if single else 0.35
    attr = dim("attribution_quality", aq,
               "single-field one-step" if (single and one_step)
               else "single-field" if single else "coupled / multi-step")

    # 4 reversibility — bounded reversible tests; coupled slightly lower
    rev = dim("reversibility", 1.0 if single else 0.8,
              "bounded reversible (revert to baseline checkpoint)")

    # 5 protection of confirmed-good — high when nothing protected is at risk
    prot = dim("protection_of_confirmed_good", 1.0 if not protected else 0.4,
               "no confirmed-good behaviour at risk" if not protected
               else f"puts at risk: {', '.join(protected)}")

    # 6 low masking risk — single-field masks less
    mask = dim("low_masking_risk", 0.9 if single else 0.5,
               "single field is unlikely to mask other issues" if single
               else "coupled change may mask other issues")

    # 7 low interaction complexity
    inter = dim("low_interaction_complexity", 0.9 if single else 0.45,
                "one field, low coupling" if single else "coupled interaction")

    # 8 low driver workload — one-step single-field is the lightest
    wl = dim("low_driver_workload", 0.9 if (single and one_step) else 0.6,
             "one bounded step, single stint" if (single and one_step) else "more setup work")

    # 9 session suitability
    ss = {SessionSuitability.SUITABLE: 1.0, SessionSuitability.MARGINAL: 0.5,
          SessionSuitability.UNSUITABLE: 0.15, SessionSuitability.UNKNOWN: 0.4}[session_suit]
    sess = dim("session_suitability", ss, f"session context: {session_suit.value}")

    # 10 remaining uncertainty — weak/limited evidence => more to resolve
    ru = 1 - _GRADE_RANK.get(grade, 0) / 3.0
    if status == "conditional" or competing >= 2:
        ru = max(ru, 0.7)
    unc = dim("remaining_uncertainty", ru,
              f"evidence grade {grade or 'n/a'}"
              + ("; competing/conditional" if (status == "conditional" or competing >= 2) else ""))

    # 11 proven-history usefulness — a nearby proven direction lowers uncertainty a little
    ph = dim("proven_history_usefulness", 0.4,
             "no strong proven-history signal in this context")

    # 12 prediction-calibration benefit — thin/absent calibration => testing improves it
    n_recon = int((calibration or {}).get("reconciliations") or 0)
    cb = 0.9 if n_recon == 0 else 0.55 if n_recon < 3 else 0.3
    if reconciled_experiment:
        cb = min(cb, 0.25)
    calib = dim("prediction_calibration_benefit", cb,
                f"{n_recon} reconciliation(s) folded so far")

    # 13 future engineering value — recurring / foundational mechanisms are worth learning
    residual = _lc((ctx.get("annotation") or {}).get("canonical_issue", {}).get("residual_state"))
    fev = 0.7 if residual in ("worsened", "new", "unchanged") else 0.5
    fut = dim("future_engineering_value", fev, "recurring / foundational mechanism")

    return [info, disc, attr, rev, prot, mask, inter, wl, sess, unc, ph, calib, fut]


def _engineering_value(dims: Sequence[ValueDimension]) -> float:
    total = sum(d.score * d.weight for d in dims)
    return round(total / _MAX_VALUE, 6) if _MAX_VALUE else 0.0


# --------------------------------------------------------------------------- #
# Session suitability
# --------------------------------------------------------------------------- #
def _session_suitability(session: Mapping) -> SessionSuitability:
    """Deterministic; unknown context lowers confidence (never invented)."""
    if not session:
        return SessionSuitability.UNKNOWN
    mins = session.get("practice_minutes_remaining")
    tyres = session.get("tyre_sets_available")
    if mins is None and tyres is None:
        return SessionSuitability.UNKNOWN
    try:
        m = float(mins) if mins is not None else None
        t = float(tyres) if tyres is not None else None
    except (TypeError, ValueError):
        return SessionSuitability.UNKNOWN
    if (m is not None and m <= 0) or (t is not None and t <= 0):
        return SessionSuitability.UNSUITABLE
    if (m is not None and m < 15) or (t is not None and t < 1):
        return SessionSuitability.MARGINAL
    if m is None or t is None:
        return SessionSuitability.MARGINAL
    return SessionSuitability.SUITABLE


# --------------------------------------------------------------------------- #
# Public: build the portfolio
# --------------------------------------------------------------------------- #
def build_portfolio(synthesis_report: Optional[Mapping], *,
                    outcome_history: Optional[Sequence[Mapping]] = None,
                    calibration: Optional[Mapping] = None,
                    session_context: Optional[Mapping] = None) -> EngineeringPortfolio:
    """Rank the legal experiments in a Phase-15 synthesis report by engineering value.
    Deterministic; read-only; never raises; mutates nothing."""
    try:
        return _build(synthesis_report or {}, list(outcome_history or ()),
                      dict(calibration or {}), dict(session_context or {}))
    except Exception as exc:   # never raise into the caller
        return _empty(f"portfolio error: {type(exc).__name__}", session_context or {})


def _empty(reason: str, session: Mapping) -> EngineeringPortfolio:
    kv = knowledge_versions()
    fp = _fp({"reason": reason, "kv": kv})
    return EngineeringPortfolio(
        context_fingerprint="", session_context=dict(session),
        session_suitability=_session_suitability(session).value, valuations=(),
        highest_value=None, alternatives=(), deferred=(), blocked=(), obsolete=(),
        redundant=(), dependencies=(), roadmap=(), dimension_weights=dict(DIMENSION_WEIGHTS),
        safety_statement=_SAFETY, audit=(f"empty={reason}",), content_fingerprint=fp,
        knowledge_versions=kv)


def _build(report: Mapping, outcome_history: List[Mapping], calibration: Mapping,
           session: Mapping) -> EngineeringPortfolio:
    ctx_fp = _norm(report.get("content_fingerprint"))
    session_suit = _session_suitability(session)
    hist = _history_index(outcome_history)
    calib_summary = (calibration.get("calibration") if isinstance(calibration.get("calibration"),
                     Mapping) else calibration) or {}
    reconciled_experiments = {
        _norm(r.get("experiment_id")) for r in (calibration.get("records") or [])
        if isinstance(r, Mapping)}

    pairs = _candidates_from_report(report)

    # --- valuate every candidate -------------------------------------------
    prelim: List[dict] = []
    for cand, ctx in pairs:
        d = _primary_delta(cand)
        fieldname = _lc(d.get("field"))
        direction = _coarse(_lc(d.get("direction")))
        status = _lc(cand.get("status"))
        recon_exp = bool(reconciled_experiments)   # calibration exists for this context
        dims = _dims(cand, ctx, session=session, session_suit=session_suit,
                     calibration=calib_summary, reconciled_experiment=False)
        value = _engineering_value(dims)
        prelim.append({
            "candidate": cand, "ctx": ctx, "field": fieldname, "direction": direction,
            "status": status, "dims": dims, "value": value,
            "cid": _norm(cand.get("candidate_id")),
            "grade": _lc(cand.get("evidence_grade")),
            "single": _lc(cand.get("attribution_scope")) == "single_field",
            "mech": _norm(d.get("source_mechanism_id")),
            "protected": tuple(cand.get("protected_good_behaviours") or ()),
        })

    # --- retirement (from outcome history) ---------------------------------
    for p in prelim:
        key = (p["field"], p["direction"])
        st = hist.get(key)
        if st in ("confirmed_improvement", "partial_improvement"):
            p["retire"] = "already confirmed for this field/direction"
        elif st in ("regression",):
            p["retire"] = "already rejected (prior regression) for this field/direction"
        else:
            p["retire"] = ""

    # --- redundancy + supersession + dependencies (deterministic) ----------
    dependencies: List[ExperimentDependency] = []
    # group by (field, direction) for redundancy; by field for exclusivity/supersession
    by_fd: Dict[Tuple[str, str], List[dict]] = {}
    by_field: Dict[str, List[dict]] = {}
    for p in prelim:
        by_fd.setdefault((p["field"], p["direction"]), []).append(p)
        by_field.setdefault(p["field"], []).append(p)

    redundant_ids = set()
    superseded_ids = set()
    supersedes_map: Dict[str, List[str]] = {}
    depends_map: Dict[str, List[str]] = {}

    for (fld, direction), grp in by_fd.items():
        if len(grp) < 2:
            continue
        # keep the highest value (tie-break stable id); the rest are redundant
        grp_sorted = sorted(grp, key=lambda p: (-p["value"], p["cid"]))
        keep = grp_sorted[0]
        for p in grp_sorted[1:]:
            redundant_ids.add(p["cid"])
            dependencies.append(ExperimentDependency(
                keep["cid"], p["cid"], DependencyKind.SUPERSEDES.value,
                f"same field+direction ({fld}); higher engineering value kept"))
            supersedes_map.setdefault(keep["cid"], []).append(p["cid"])

    for fld, grp in by_field.items():
        dirs = {p["direction"] for p in grp if p["cid"] not in redundant_ids}
        if {"increase", "decrease"} <= dirs:
            inc = sorted([p for p in grp if p["direction"] == "increase"
                          and p["cid"] not in redundant_ids], key=lambda p: p["cid"])
            dec = sorted([p for p in grp if p["direction"] == "decrease"
                          and p["cid"] not in redundant_ids], key=lambda p: p["cid"])
            if inc and dec:
                dependencies.append(ExperimentDependency(
                    inc[0]["cid"], dec[0]["cid"], DependencyKind.MUTUALLY_EXCLUSIVE.value,
                    f"opposite directions on {fld} cannot both be tested from one baseline"))

    # competing candidates: a single-field discrimination test gates the follow-ups for the
    # SAME diagnosis (unnecessary if the discrimination fails to isolate the mechanism)
    by_diag: Dict[str, List[dict]] = {}
    for p in prelim:
        by_diag.setdefault(p["ctx"].get("diagnosis_key", ""), []).append(p)
    for diag, grp in by_diag.items():
        if int((grp[0]["ctx"].get("competing_count") or 0)) < 2 or len(grp) < 2:
            continue
        ordered = sorted([p for p in grp if p["cid"] not in redundant_ids],
                         key=lambda p: (-p["value"], p["cid"]))
        if len(ordered) < 2:
            continue
        lead = ordered[0]
        for p in ordered[1:]:
            dependencies.append(ExperimentDependency(
                p["cid"], lead["cid"], DependencyKind.UNNECESSARY_IF_FAILS.value,
                "competing mechanisms — run the highest-value discriminating test first; "
                "this one is unnecessary if it isolates the cause"))
            depends_map.setdefault(p["cid"], []).append(lead["cid"])

    # --- roles + ranking ---------------------------------------------------
    def _role(p) -> PortfolioRole:
        if p["retire"]:
            return PortfolioRole.OBSOLETE
        if p["cid"] in redundant_ids:
            return PortfolioRole.REDUNDANT
        if p["status"] in ("blocked_by_working_window", "blocked_by_prior_regression",
                           "blocked_by_legality", "blocked_by_baseline_state",
                           "blocked_by_interaction_risk", "not_evaluable", "out_of_scope"):
            return PortfolioRole.BLOCKED
        if p["status"] in ("conditional", "requires_coupled_experiment"):
            return PortfolioRole.DEFERRED
        return PortfolioRole.ALTERNATIVE   # ready → alternative until the top is chosen

    for p in prelim:
        p["role"] = _role(p)

    # rankable = the actionable (ready) candidates competing for "next experiment"
    rankable = [p for p in prelim if p["role"] == PortfolioRole.ALTERNATIVE]
    rankable.sort(key=lambda p: (-p["value"], p["cid"]))
    # a genuine tie keeps both as alternatives (no artificial winner)
    top = None
    if rankable:
        if len(rankable) == 1 or rankable[0]["value"] > rankable[1]["value"] + 1e-9:
            top = rankable[0]
            top["role"] = PortfolioRole.HIGHEST_VALUE

    # assign ranks across everything (deterministic, stable)
    ordered_all = sorted(prelim, key=lambda p: (
        _ROLE_ORDER[p["role"]], -p["value"], p["cid"]))
    valuations: List[ExperimentValuation] = []
    for rank, p in enumerate(ordered_all):
        d = _primary_delta(p["candidate"])
        reasons = []
        if p["retire"]:
            reasons.append(p["retire"])
        if p["cid"] in redundant_ids:
            reasons.append("superseded by a higher-value same-field experiment")
        if p["role"] == PortfolioRole.HIGHEST_VALUE:
            reasons.append("highest engineering value (information gain leads)")
        if depends_map.get(p["cid"]):
            reasons.append("depends on a discriminating test first")
        valuations.append(ExperimentValuation(
            candidate_id=p["cid"], diagnosis_key=_norm(p["ctx"].get("diagnosis_key")),
            issue_type=_norm(p["ctx"].get("issue_type")), field=p["field"],
            direction=_lc(d.get("direction")), mechanism_id=p["mech"],
            attribution_scope=_lc(p["candidate"].get("attribution_scope")),
            synthesis_status=p["status"], dimensions=tuple(p["dims"]),
            engineering_value=p["value"], role=p["role"].value,
            retirement_reason=p["retire"],
            depends_on=tuple(depends_map.get(p["cid"], [])),
            supersedes=tuple(supersedes_map.get(p["cid"], [])),
            protected_good_at_risk=p["protected"],
            expected_learning=_expected_learning(p),
            rank=rank, reasons=tuple(reasons)))

    vdicts = [v.to_dict() for v in valuations]

    def _bucket(role: PortfolioRole):
        return tuple(v for v in vdicts if v["role"] == role.value)

    highest = next((v for v in vdicts if v["role"] == PortfolioRole.HIGHEST_VALUE.value), None)
    roadmap = _roadmap(highest, _bucket(PortfolioRole.ALTERNATIVE))

    audit = (
        f"candidates={len(prelim)}",
        f"highest={'yes' if highest else 'no (tie or none)'}",
        f"obsolete={len(_bucket(PortfolioRole.OBSOLETE))}",
        f"redundant={len(redundant_ids)}",
        f"deferred={len(_bucket(PortfolioRole.DEFERRED))}",
        f"blocked={len(_bucket(PortfolioRole.BLOCKED))}",
        f"session={session_suit.value}",
        "objective=engineering_value(information_gain_first); optimises learning, not lap time",
    )
    kv = knowledge_versions()
    fp = _fp({"ctx": ctx_fp, "vals": [(v["candidate_id"], v["role"], v["engineering_value"])
                                      for v in vdicts],
              "deps": [d.to_dict() for d in dependencies], "session": session_suit.value,
              "kv": kv})
    return EngineeringPortfolio(
        context_fingerprint=ctx_fp, session_context=dict(session),
        session_suitability=session_suit.value, valuations=tuple(vdicts),
        highest_value=highest, alternatives=_bucket(PortfolioRole.ALTERNATIVE),
        deferred=_bucket(PortfolioRole.DEFERRED), blocked=_bucket(PortfolioRole.BLOCKED),
        obsolete=_bucket(PortfolioRole.OBSOLETE), redundant=_bucket(PortfolioRole.REDUNDANT),
        dependencies=tuple(d.to_dict() for d in dependencies), roadmap=roadmap,
        dimension_weights=dict(DIMENSION_WEIGHTS), safety_statement=_SAFETY, audit=audit,
        content_fingerprint=fp, knowledge_versions=kv)


_ROLE_ORDER = {
    PortfolioRole.HIGHEST_VALUE: 0, PortfolioRole.ALTERNATIVE: 1, PortfolioRole.DEFERRED: 2,
    PortfolioRole.BLOCKED: 3, PortfolioRole.REDUNDANT: 4, PortfolioRole.OBSOLETE: 5,
}


def _expected_learning(p: dict) -> str:
    if int(p["ctx"].get("competing_count") or 0) >= 2:
        return ("distinguishes which of the competing mechanisms is driving "
                f"{p['ctx'].get('issue_type') or 'the issue'}")
    if p["single"]:
        return (f"cleanly attributes {p['ctx'].get('issue_type') or 'the issue'} response to "
                f"{p['field']} (single-field)")
    return f"tests a coupled response for {p['ctx'].get('issue_type') or 'the issue'}"


def _roadmap(highest: Optional[dict], alternatives: Sequence[dict]) -> Tuple[dict, ...]:
    stages: List[RoadmapStage] = []
    o = 0
    lead = highest or (alternatives[0] if alternatives else None)
    if lead is None:
        return ()
    stages.append(RoadmapStage(o, "experiment", lead["candidate_id"],
                               f"run: {lead['direction'].replace('_', ' ')} {lead['field']} "
                               f"({lead['expected_learning']})")); o += 1
    stages.append(RoadmapStage(o, "review", lead["candidate_id"],
                               "review the Phase-3 outcome + Phase-11 reconciliation")); o += 1
    # a second independent experiment (different field, not dependent)
    second = next((a for a in alternatives
                   if a["candidate_id"] != lead["candidate_id"]
                   and a["field"] != lead["field"] and not a["depends_on"]), None)
    if second is not None:
        stages.append(RoadmapStage(o, "experiment", second["candidate_id"],
                                   f"run: {second['direction'].replace('_', ' ')} "
                                   f"{second['field']}")); o += 1
        stages.append(RoadmapStage(o, "review", second["candidate_id"],
                                   "review the outcome")); o += 1
    stages.append(RoadmapStage(o, "validate", lead["candidate_id"],
                               "validate the confirmed direction over more valid laps")); o += 1
    stages.append(RoadmapStage(o, "freeze", "",
                               "freeze the setup once gains are confirmed")); o += 1
    stages.append(RoadmapStage(o, "race", "", "race the frozen setup"))
    return tuple(s.to_dict() for s in stages)


def knowledge_versions() -> dict:
    return {"experiment_portfolio": EXPERIMENT_PORTFOLIO_VERSION,
            "experiment_synthesis": EXPERIMENT_SYNTHESIS_VERSION,
            "schema": EXPERIMENT_PORTFOLIO_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{EXPERIMENT_PORTFOLIO_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
