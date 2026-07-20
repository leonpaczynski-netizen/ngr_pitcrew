"""Engineering Campaigns & Multi-Session Development Planning (Program 2, Phase 18).

A deterministic, READ-ONLY layer that groups a Phase-17 experiment portfolio into coherent,
multi-session vehicle-development CAMPAIGNS. A campaign answers: "what engineering objective
are we pursuing, what have we learned, what remains uncertain, which experiments belong to
this objective, and how close are we to declaring it complete?"

It is NOT a diagnosis / synthesis / experiment-ranking / lifecycle / Apply authority. It
ORCHESTRATES the existing authorities:
  * experiment ranking + dependencies + retirement  = Phase 17 (`ExperimentPortfolio`);
  * bounded legal experiments                        = Phase 15;
  * mechanism hypotheses                             = Phase 14;
  * lifecycle / execution readiness                  = Phase 16;
  * outcome / reconciliation / calibration           = Program 1 (read-only projection).

It NEVER applies/approves/mutates a setup, creates/updates experiments, alters outcomes,
writes engineering records, performs hidden weighting, or re-ranks experiments independently
of Phase 17. It never claims completion merely because no candidates were generated, and it
never marks a successful-but-unvalidated objective complete.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock
(timestamps are data); deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.experiment_portfolio import EXPERIMENT_PORTFOLIO_VERSION

ENGINEERING_CAMPAIGN_VERSION = "engineering_campaign_v1"
ENGINEERING_CAMPAIGN_SCHEMA = 1

# Minimum confirmed-improvement observations (across compatible sessions) to treat a
# direction as validated rather than merely successful-once.
_VALIDATION_MIN_CONFIRMATIONS = 2


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class CampaignStatus(str, Enum):
    NOT_STARTED = "not_started"
    ACTIVE = "active"
    BLOCKED = "blocked"
    VALIDATION_REQUIRED = "validation_required"
    READY_TO_FREEZE = "ready_to_freeze"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    STALE = "stale"


class CampaignStageType(str, Enum):
    DEFINE = "define"
    DISCRIMINATE = "discriminate"
    INTERVENE = "intervene"
    REVIEW = "review"
    VALIDATE = "validate"
    FREEZE = "freeze"
    RACE_READY = "race_ready"


class CampaignRole(str, Enum):
    PRIMARY_DISCRIMINATOR = "primary_discriminator"
    PRIMARY_INTERVENTION = "primary_intervention"
    SECONDARY_INDEPENDENT_TEST = "secondary_independent_test"
    VALIDATION_TEST = "validation_test"
    PROTECTION_CHECK = "protection_check"
    CONTINGENCY = "contingency"
    RETIRED = "retired"


# --------------------------------------------------------------------------- #
# Objective grouping — deterministic, evidence-based (issue family + region)
# --------------------------------------------------------------------------- #
_ISSUE_FAMILY = {
    "front_lock": "braking", "lockup": "braking", "rear_loose_under_braking": "braking",
    "braking_instability": "braking",
    "entry_understeer": "rotation", "mid_corner_understeer": "rotation",
    "front_push": "rotation", "understeer": "rotation",
    "entry_oversteer": "rotation", "oversteer": "rotation", "snap_oversteer": "rotation",
    "rear_loose_on_exit": "traction", "wheelspin": "traction", "rear_wheelspin": "traction",
    "poor_traction": "traction", "poor_drive_out": "drive_out",
    "bottoming": "platform", "kerb": "platform", "tyre_deg": "tyre", "tyre_wear": "tyre",
    "wrong_gear": "gearing", "gearing_too_long": "gearing", "fuel_use_high": "fuel",
}
_ISSUE_REGION = {
    "front_lock": "front", "lockup": "front", "entry_understeer": "front",
    "mid_corner_understeer": "front", "front_push": "front", "understeer": "front",
    "rear_loose_under_braking": "rear", "braking_instability": "rear",
    "entry_oversteer": "rear", "oversteer": "rear", "snap_oversteer": "rear",
    "rear_loose_on_exit": "rear", "wheelspin": "rear", "rear_wheelspin": "rear",
    "poor_traction": "rear", "poor_drive_out": "rear",
    "bottoming": "platform", "kerb": "platform", "tyre_deg": "tyre", "tyre_wear": "tyre",
    "wrong_gear": "drivetrain", "gearing_too_long": "drivetrain", "fuel_use_high": "aero",
}
_OBJECTIVE_TITLE = {
    ("braking", "front"): "Reduce front locking under braking",
    ("braking", "rear"): "Reduce rear instability under braking",
    ("rotation", "front"): "Improve front grip and rotation",
    ("rotation", "rear"): "Reduce rear rotation / power-on oversteer",
    ("traction", "rear"): "Improve corner-exit traction",
    ("drive_out", "rear"): "Improve corner drive-out",
    ("platform", "platform"): "Improve platform / kerb stability",
    ("gearing", "drivetrain"): "Optimise gearing for the corner exit",
    ("tyre", "tyre"): "Protect tyre life",
    ("fuel", "aero"): "Reduce aerodynamic drag / fuel use",
}
_OBJECTIVE_VERB = {
    "braking": "settles braking", "rotation": "improves front grip",
    "traction": "improves exit traction", "drive_out": "improves drive-out",
    "platform": "stabilises the platform", "gearing": "optimises gearing",
    "tyre": "preserves the tyres", "fuel": "reduces drag",
}


def _family(issue_type: str) -> str:
    return _ISSUE_FAMILY.get(_lc(issue_type), "unknown")


def _region(issue_type: str, field: str = "") -> str:
    r = _ISSUE_REGION.get(_lc(issue_type))
    if r:
        return r
    f = _lc(field)
    if f.endswith("_front"):
        return "front"
    if f.endswith("_rear"):
        return "rear"
    return "general"


def _objective_key(issue_type: str, field: str = "") -> Tuple[str, str]:
    return (_family(issue_type), _region(issue_type, field))


# --------------------------------------------------------------------------- #
# Domain dataclasses
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CampaignIdentity:
    driver: str
    car: str
    track: str
    layout: str
    discipline: str
    gt7_version: str
    objective_family: str
    objective_region: str
    source_context: str
    campaign_id: str
    context_fingerprint: str

    def to_dict(self) -> dict:
        return {"driver": self.driver, "car": self.car, "track": self.track,
                "layout": self.layout, "discipline": self.discipline,
                "gt7_version": self.gt7_version, "objective_family": self.objective_family,
                "objective_region": self.objective_region, "source_context": self.source_context,
                "campaign_id": self.campaign_id, "context_fingerprint": self.context_fingerprint}


@dataclass(frozen=True)
class CompletionCriterion:
    criterion_id: str
    description: str
    satisfied: bool
    evidence_refs: Tuple[str, ...]
    blocker_reason: str
    rationale: str

    def to_dict(self) -> dict:
        return {"criterion_id": self.criterion_id, "description": self.description,
                "satisfied": self.satisfied, "evidence_refs": list(self.evidence_refs),
                "blocker_reason": self.blocker_reason, "rationale": self.rationale}


@dataclass(frozen=True)
class CampaignObjective:
    objective_id: str
    title: str
    engineering_question: str
    source_diagnoses: Tuple[str, ...]
    source_mechanisms: Tuple[str, ...]
    affected_phases: Tuple[str, ...]
    protected_good_behaviours: Tuple[str, ...]
    current_uncertainty: str
    completion_criteria: Tuple[CompletionCriterion, ...]
    blocker_reasons: Tuple[str, ...]
    rationale: str

    def to_dict(self) -> dict:
        return {"objective_id": self.objective_id, "title": self.title,
                "engineering_question": self.engineering_question,
                "source_diagnoses": list(self.source_diagnoses),
                "source_mechanisms": list(self.source_mechanisms),
                "affected_phases": list(self.affected_phases),
                "protected_good_behaviours": list(self.protected_good_behaviours),
                "current_uncertainty": self.current_uncertainty,
                "completion_criteria": [c.to_dict() for c in self.completion_criteria],
                "blocker_reasons": list(self.blocker_reasons), "rationale": self.rationale}


@dataclass(frozen=True)
class CampaignExperiment:
    candidate_id: str
    phase17_rank: int
    engineering_value: float
    campaign_role: str
    campaign_stage: str
    field: str
    direction: str
    dependency_state: str
    retirement_state: str
    execution_state: str
    outcome_state: str
    reconciliation_state: str
    prediction_accuracy: Optional[float]
    knowledge_gained: str
    remaining_question: str
    needs_further_testing: bool
    rationale: str

    def to_dict(self) -> dict:
        return {"candidate_id": self.candidate_id, "phase17_rank": self.phase17_rank,
                "engineering_value": self.engineering_value, "campaign_role": self.campaign_role,
                "campaign_stage": self.campaign_stage, "field": self.field,
                "direction": self.direction, "dependency_state": self.dependency_state,
                "retirement_state": self.retirement_state, "execution_state": self.execution_state,
                "outcome_state": self.outcome_state,
                "reconciliation_state": self.reconciliation_state,
                "prediction_accuracy": self.prediction_accuracy,
                "knowledge_gained": self.knowledge_gained,
                "remaining_question": self.remaining_question,
                "needs_further_testing": self.needs_further_testing, "rationale": self.rationale}


@dataclass(frozen=True)
class CampaignStage:
    stage_id: str
    stage_type: str
    purpose: str
    candidate_experiment_ids: Tuple[str, ...]
    dependency_requirements: Tuple[str, ...]
    completion_state: str
    blocker_reasons: Tuple[str, ...]
    expected_knowledge_gain: str
    exit_criteria: str
    advisory_next_action: str

    def to_dict(self) -> dict:
        return {"stage_id": self.stage_id, "stage_type": self.stage_type,
                "purpose": self.purpose,
                "candidate_experiment_ids": list(self.candidate_experiment_ids),
                "dependency_requirements": list(self.dependency_requirements),
                "completion_state": self.completion_state,
                "blocker_reasons": list(self.blocker_reasons),
                "expected_knowledge_gain": self.expected_knowledge_gain,
                "exit_criteria": self.exit_criteria,
                "advisory_next_action": self.advisory_next_action}


@dataclass(frozen=True)
class CampaignProgress:
    total_experiments: int
    active_experiments: int
    completed_useful: int
    confirmed_improvement: int
    partial_improvement: int
    regressions: int
    inconclusive: int
    retired: int
    blocked: int
    validation_remaining: int
    unresolved_mechanisms: int
    confirmed_mechanisms: int
    protected_good: int
    criteria_satisfied: int
    criteria_total: int
    progress_pct: int
    maturity: str
    factors: Tuple[dict, ...]
    rationale: str

    def to_dict(self) -> dict:
        return {"total_experiments": self.total_experiments,
                "active_experiments": self.active_experiments,
                "completed_useful": self.completed_useful,
                "confirmed_improvement": self.confirmed_improvement,
                "partial_improvement": self.partial_improvement,
                "regressions": self.regressions, "inconclusive": self.inconclusive,
                "retired": self.retired, "blocked": self.blocked,
                "validation_remaining": self.validation_remaining,
                "unresolved_mechanisms": self.unresolved_mechanisms,
                "confirmed_mechanisms": self.confirmed_mechanisms,
                "protected_good": self.protected_good,
                "criteria_satisfied": self.criteria_satisfied,
                "criteria_total": self.criteria_total, "progress_pct": self.progress_pct,
                "maturity": self.maturity, "factors": [dict(f) for f in self.factors],
                "rationale": self.rationale}


@dataclass(frozen=True)
class EngineeringCampaign:
    identity: CampaignIdentity
    objective: CampaignObjective
    status: str
    stages: Tuple[CampaignStage, ...]
    experiments: Tuple[CampaignExperiment, ...]
    progress: CampaignProgress
    roadmap: Tuple[str, ...]
    blockers: Tuple[str, ...]
    grouping_rationale: str
    next_action: str
    content_fingerprint: str

    def to_dict(self) -> dict:
        return {"identity": self.identity.to_dict(), "objective": self.objective.to_dict(),
                "status": self.status, "stages": [s.to_dict() for s in self.stages],
                "experiments": [e.to_dict() for e in self.experiments],
                "progress": self.progress.to_dict(), "roadmap": list(self.roadmap),
                "blockers": list(self.blockers), "grouping_rationale": self.grouping_rationale,
                "next_action": self.next_action,
                "content_fingerprint": self.content_fingerprint}


@dataclass(frozen=True)
class EngineeringCampaignProgramme:
    context_summary: dict
    campaigns: Tuple[dict, ...]
    active_count: int
    blocked_count: int
    ready_to_freeze_count: int
    completed_count: int
    stale_count: int
    programme_blockers: Tuple[str, ...]
    recommended_focus: Optional[dict]
    programme_roadmap: Tuple[dict, ...]
    safety_statement: str
    audit: Tuple[str, ...]
    content_fingerprint: str
    knowledge_versions: dict
    schema_version: int = ENGINEERING_CAMPAIGN_SCHEMA
    eval_version: str = ENGINEERING_CAMPAIGN_VERSION

    def to_dict(self) -> dict:
        return {"context_summary": dict(self.context_summary),
                "campaigns": [dict(c) for c in self.campaigns],
                "active_count": self.active_count, "blocked_count": self.blocked_count,
                "ready_to_freeze_count": self.ready_to_freeze_count,
                "completed_count": self.completed_count, "stale_count": self.stale_count,
                "programme_blockers": list(self.programme_blockers),
                "recommended_focus": (dict(self.recommended_focus)
                                      if self.recommended_focus else None),
                "programme_roadmap": [dict(s) for s in self.programme_roadmap],
                "safety_statement": self.safety_statement, "audit": list(self.audit),
                "content_fingerprint": self.content_fingerprint,
                "knowledge_versions": dict(self.knowledge_versions),
                "schema_version": self.schema_version, "eval_version": self.eval_version}


_SAFETY = ("Read-only campaign planner. It groups the Phase-17 portfolio into multi-session "
           "engineering campaigns and projects existing outcome / reconciliation / "
           "calibration evidence - it ranks nothing itself, applies nothing, writes nothing, "
           "and never marks a successful-but-unvalidated objective complete. The frozen Apply "
           "gate and the existing lifecycle remain the only execution routes.")


# --------------------------------------------------------------------------- #
# Multi-session outcome projection (from existing records; never invents)
# --------------------------------------------------------------------------- #
_COARSE = {"stiffen": "increase", "soften": "decrease", "raise": "increase",
           "lower": "decrease", "increase": "increase", "decrease": "decrease",
           "increase_locking": "increase", "decrease_locking": "decrease",
           "move_rearward": "increase", "move_forward": "decrease",
           "shorten": "increase", "lengthen": "decrease"}


def _coarse(direction: str) -> str:
    return _COARSE.get(_lc(direction), _lc(direction))


def _outcome_index(outcome_history: Sequence[Mapping]) -> Dict[str, List[dict]]:
    """{field: [ {direction, outcome_status, session, single, experiment_id} ]} from prior
    experiments (existing records only). Multi-session compatible evidence only."""
    idx: Dict[str, List[dict]] = {}
    for oh in outcome_history or ():
        if not isinstance(oh, Mapping):
            continue
        flds = [_lc(f) for f in (oh.get("fields") or []) if _lc(f)]
        if not flds:
            continue
        entry = {"direction": _coarse(oh.get("direction")),
                 "outcome_status": _lc(oh.get("outcome_status")),
                 "session": _norm(oh.get("session_id") or oh.get("session_date")),
                 "single": bool(oh.get("single_field")) or len(flds) == 1,
                 "experiment_id": _norm(oh.get("experiment_id")),
                 "compatible": bool(oh.get("compatible", True))}
        for f in flds:
            idx.setdefault(f, []).append(entry)
    return idx


# --------------------------------------------------------------------------- #
# Public: build the programme
# --------------------------------------------------------------------------- #
def build_campaign_programme(portfolio: Optional[Mapping], *,
                             outcome_history: Optional[Sequence[Mapping]] = None,
                             calibration: Optional[Mapping] = None,
                             active_context: Optional[Mapping] = None,
                             session_context: Optional[Mapping] = None,
                             scope: Optional[Mapping] = None) -> EngineeringCampaignProgramme:
    """Group a Phase-17 portfolio into engineering campaigns and project the existing
    multi-session evidence. Read-only; deterministic; never raises; mutates nothing."""
    try:
        return _build(portfolio or {}, list(outcome_history or ()), dict(calibration or {}),
                      dict(active_context or {}), dict(session_context or {}), dict(scope or {}))
    except Exception as exc:   # never raise into the caller
        return _empty(f"campaign error: {type(exc).__name__}", scope or {})


def _empty(reason: str, scope: Mapping) -> EngineeringCampaignProgramme:
    kv = knowledge_versions()
    return EngineeringCampaignProgramme(
        context_summary=dict(scope), campaigns=(), active_count=0, blocked_count=0,
        ready_to_freeze_count=0, completed_count=0, stale_count=0,
        programme_blockers=(reason,), recommended_focus=None, programme_roadmap=(),
        safety_statement=_SAFETY, audit=(f"empty={reason}",),
        content_fingerprint=_fp({"reason": reason, "kv": kv}), knowledge_versions=kv)


def _stale_reasons(scope: Mapping, active: Mapping) -> List[str]:
    """Context mismatch is visible and never silently merged."""
    out = []
    for key, label in (("car", "car"), ("track", "track"), ("layout_id", "layout"),
                       ("discipline", "discipline"), ("gt7_version", "GT7 version")):
        a = _lc(active.get(key))
        s = _lc(scope.get(key))
        if a and s and a != s:
            out.append(f"active {label} ({a}) differs from the campaign {label} ({s})")
    return out


def _build(portfolio: Mapping, outcome_history: List[Mapping], calibration: Mapping,
           active_context: Mapping, session_context: Mapping, scope: Mapping
           ) -> EngineeringCampaignProgramme:
    ctx_fp = _norm(portfolio.get("content_fingerprint"))
    valuations = list(portfolio.get("valuations") or [])
    dependencies = list(portfolio.get("dependencies") or [])
    calib_summary = (calibration.get("calibration") if isinstance(calibration.get("calibration"),
                     Mapping) else calibration) or {}
    outcome_idx = _outcome_index(outcome_history)
    stale = _stale_reasons(scope, active_context)

    # candidate id -> mutually-exclusive partner ids (for cross-campaign gating)
    mutex: Dict[str, List[str]] = {}
    for d in dependencies:
        if _lc(d.get("kind")) == "mutually_exclusive":
            a, b = _norm(d.get("from_id")), _norm(d.get("to_id"))
            mutex.setdefault(a, []).append(b)
            mutex.setdefault(b, []).append(a)

    # --- deterministic grouping by objective key ---------------------------
    groups: Dict[Tuple[str, str], List[dict]] = {}
    for v in valuations:
        key = _objective_key(_norm(v.get("issue_type")), _norm(v.get("field")))
        groups.setdefault(key, []).append(v)

    scope_ctx = {
        "driver": _norm(scope.get("driver")), "car": _norm(scope.get("car")),
        "track": _norm(scope.get("track")), "layout": _norm(scope.get("layout_id")),
        "discipline": _norm(scope.get("discipline")),
        "gt7_version": _norm(scope.get("gt7_version")),
    }

    campaigns: List[EngineeringCampaign] = []
    for key in sorted(groups):   # deterministic order
        family, region = key
        camp = _build_campaign(family, region, sorted(groups[key],
                               key=lambda v: (v.get("rank", 999), _norm(v.get("candidate_id")))),
                               outcome_idx=outcome_idx, calib=calib_summary, scope=scope_ctx,
                               ctx_fp=ctx_fp, stale=stale, mutex=mutex)
        campaigns.append(camp)

    # cross-campaign mutual-exclusion gating (deterministic, by value/id) ----
    campaigns = _gate_mutually_exclusive(campaigns, mutex)

    cdicts = [c.to_dict() for c in campaigns]
    active_c = sum(1 for c in campaigns if c.status == CampaignStatus.ACTIVE.value)
    blocked_c = sum(1 for c in campaigns if c.status == CampaignStatus.BLOCKED.value)
    freeze_c = sum(1 for c in campaigns if c.status == CampaignStatus.READY_TO_FREEZE.value)
    done_c = sum(1 for c in campaigns if c.status == CampaignStatus.COMPLETED.value)
    stale_c = sum(1 for c in campaigns if c.status == CampaignStatus.STALE.value)

    focus = _recommended_focus(campaigns)
    programme_roadmap = _programme_roadmap(campaigns, mutex)
    programme_blockers = list(dict.fromkeys(
        stale + [b for c in campaigns for b in c.blockers if c.status == CampaignStatus.BLOCKED.value]))

    kv = knowledge_versions()
    audit = (
        f"campaigns={len(campaigns)}", f"active={active_c}", f"blocked={blocked_c}",
        f"ready_to_freeze={freeze_c}", f"completed={done_c}", f"stale={stale_c}",
        f"portfolio_fp={ctx_fp[:16]}",
        "ranking_owner=phase17; lifecycle_owner=phase16; read-only; mutates nothing",
    )
    fp = _fp({"ctx": ctx_fp, "camps": [(c.identity.campaign_id, c.status,
                                        c.progress.progress_pct) for c in campaigns],
              "focus": (focus or {}).get("objective_id", ""), "stale": stale, "kv": kv})
    return EngineeringCampaignProgramme(
        context_summary={**scope_ctx, "session_context": dict(session_context),
                         "portfolio_fingerprint": ctx_fp,
                         "session_suitability": _norm(portfolio.get("session_suitability"))},
        campaigns=tuple(cdicts), active_count=active_c, blocked_count=blocked_c,
        ready_to_freeze_count=freeze_c, completed_count=done_c, stale_count=stale_c,
        programme_blockers=tuple(programme_blockers), recommended_focus=focus,
        programme_roadmap=tuple(programme_roadmap), safety_statement=_SAFETY, audit=audit,
        content_fingerprint=fp, knowledge_versions=kv)


def _build_campaign(family, region, vals, *, outcome_idx, calib, scope, ctx_fp, stale, mutex
                    ) -> EngineeringCampaign:
    diagnoses = tuple(dict.fromkeys(_norm(v.get("diagnosis_key")) for v in vals
                                    if _norm(v.get("diagnosis_key"))))
    mechanisms = tuple(dict.fromkeys(_norm(v.get("mechanism_id")) for v in vals
                                     if _norm(v.get("mechanism_id"))))
    issue_types = tuple(dict.fromkeys(_norm(v.get("issue_type")) for v in vals))
    protected = tuple(dict.fromkeys(
        b for v in vals for b in (v.get("protected_good_at_risk") or [])))
    fields = tuple(dict.fromkeys(_lc(v.get("field")) for v in vals if _lc(v.get("field"))))

    obj_id = _campaign_id(scope, family, region)
    title = _OBJECTIVE_TITLE.get((family, region),
                                 f"Resolve {family.replace('_', ' ')} ({region})")
    verb = _OBJECTIVE_VERB.get(family, "improves the car")
    question = (f"Is the {(issue_types[0] if issue_types else family).replace('_', ' ')} "
                f"setup-driven, and which bounded change best {verb} while protecting "
                f"confirmed-good behaviour?")

    # per-experiment multi-session projection
    experiments = tuple(_campaign_experiment(v, outcome_idx, calib) for v in vals)

    # outcome tallies across the campaign's fields (compatible sessions only)
    tally = _tally(fields, outcome_idx)
    competing = any(int(_val_competing(v)) >= 2 for v in vals)
    mechanism_confirmed = tally["confirmed"] > 0
    validated = tally["confirmed"] >= _VALIDATION_MIN_CONFIRMATIONS
    protected_regressed = tally["protected_regression"] > 0
    live = [e for e in experiments if e.retirement_state == "" and
            e.campaign_role != CampaignRole.RETIRED.value]
    all_retired = bool(experiments) and not live

    criteria = _completion_criteria(family, competing, tally, validated, protected_regressed,
                                    live, diagnoses)
    status = _status(stale, live, experiments, tally, validated, protected_regressed,
                     all_retired, criteria)
    stages = _stages(family, region, vals, experiments, tally, competing, validated, status)
    progress = _progress(experiments, tally, criteria, mechanisms, mechanism_confirmed,
                         protected, validated)
    blockers = _blockers(stale, live, all_retired, tally, protected_regressed)
    uncertainty = ("resolved" if status == CampaignStatus.COMPLETED.value else
                   "validation pending" if status == CampaignStatus.VALIDATION_REQUIRED.value else
                   "competing mechanisms unresolved" if competing and not mechanism_confirmed else
                   "intervention direction unproven" if live else "no legal experiment")
    grouping = (f"grouped by objective ({family}/{region}); shares diagnosis "
                f"{', '.join(diagnoses) or 'n/a'} and mechanism family")

    objective = CampaignObjective(
        objective_id=obj_id, title=title, engineering_question=question,
        source_diagnoses=diagnoses, source_mechanisms=mechanisms,
        affected_phases=issue_types, protected_good_behaviours=protected,
        current_uncertainty=uncertainty, completion_criteria=criteria,
        blocker_reasons=tuple(blockers), rationale=grouping)
    identity = CampaignIdentity(
        driver=scope["driver"], car=scope["car"], track=scope["track"], layout=scope["layout"],
        discipline=scope["discipline"], gt7_version=scope["gt7_version"],
        objective_family=family, objective_region=region, source_context=ctx_fp[:16],
        campaign_id=obj_id, context_fingerprint=ctx_fp)
    next_action = _next_action(status, stages)
    roadmap = tuple(s.advisory_next_action for s in stages if s.advisory_next_action)
    fp = _fp({"id": obj_id, "status": status, "exps": [e.candidate_id for e in experiments],
              "crit": [(c.criterion_id, c.satisfied) for c in criteria],
              "prog": progress.progress_pct, "ctx": ctx_fp})
    return EngineeringCampaign(
        identity=identity, objective=objective, status=status, stages=stages,
        experiments=experiments, progress=progress, roadmap=roadmap, blockers=tuple(blockers),
        grouping_rationale=grouping, next_action=next_action, content_fingerprint=fp)


def _val_competing(v: Mapping) -> int:
    # information gain / mechanism discrimination dimension reflects competing mechanisms
    for d in v.get("dimensions") or []:
        if d.get("name") == "mechanism_discrimination":
            return 2 if float(d.get("score") or 0) >= 0.85 else 0
    return 0


def _campaign_experiment(v: Mapping, outcome_idx, calib) -> CampaignExperiment:
    field = _lc(v.get("field"))
    direction = _coarse(v.get("direction"))
    role = _lc(v.get("role"))
    retired = _norm(v.get("retirement_reason"))
    entries = [e for e in outcome_idx.get(field, []) if e["direction"] == direction]
    executed = bool(entries)
    statuses = [e["outcome_status"] for e in entries]
    sessions = len({e["session"] for e in entries if e["session"]})
    outcome_state = ("confirmed_improvement" if "confirmed_improvement" in statuses else
                     "partial_improvement" if "partial_improvement" in statuses else
                     "regression" if "regression" in statuses else
                     "no_meaningful_change" if statuses else "not_tested")
    exec_state = ("confirmed_across_sessions" if outcome_state == "confirmed_improvement"
                  and sessions >= _VALIDATION_MIN_CONFIRMATIONS else
                  "tested" if executed else "not_tested")
    camp_role = _map_role(v, retired, outcome_state)
    knowledge = ("prior test confirmed this direction improves the car" if
                 outcome_state == "confirmed_improvement" else
                 "prior test regressed this direction" if outcome_state == "regression" else
                 "not yet tested")
    remaining = ("repeatability / validation" if outcome_state == "confirmed_improvement"
                 and sessions < _VALIDATION_MIN_CONFIRMATIONS else
                 "is this direction contradicted?" if outcome_state == "regression" else
                 v.get("expected_learning") or "attribute the response")
    needs = outcome_state in ("not_tested", "partial_improvement") or (
        outcome_state == "confirmed_improvement" and sessions < _VALIDATION_MIN_CONFIRMATIONS)
    return CampaignExperiment(
        candidate_id=_norm(v.get("candidate_id")), phase17_rank=int(v.get("rank") or 0),
        engineering_value=float(v.get("engineering_value") or 0.0), campaign_role=camp_role,
        campaign_stage=_stage_for_role(camp_role), field=field,
        direction=_norm(v.get("direction")),
        dependency_state=("depends_on_discriminator" if v.get("depends_on") else "independent"),
        retirement_state=retired, execution_state=exec_state, outcome_state=outcome_state,
        reconciliation_state=("reconciled" if int(calib.get("reconciliations") or 0) > 0
                              and executed else "not_reconciled"),
        prediction_accuracy=(calib.get("overall_accuracy") if executed else None),
        knowledge_gained=knowledge, remaining_question=remaining, needs_further_testing=needs,
        rationale=f"Phase-17 rank {v.get('rank')}, value {round(float(v.get('engineering_value') or 0), 3)}")


def _map_role(v: Mapping, retired: str, outcome_state: str) -> str:
    if retired or _lc(v.get("role")) in ("obsolete", "redundant"):
        return CampaignRole.RETIRED.value
    if int(_val_competing(v)) >= 2:
        return CampaignRole.PRIMARY_DISCRIMINATOR.value
    if outcome_state == "confirmed_improvement":
        return CampaignRole.VALIDATION_TEST.value
    if _lc(v.get("role")) == "highest_value":
        return CampaignRole.PRIMARY_INTERVENTION.value
    if v.get("protected_good_at_risk"):
        return CampaignRole.PROTECTION_CHECK.value
    if _lc(v.get("role")) == "deferred":
        return CampaignRole.CONTINGENCY.value
    return CampaignRole.SECONDARY_INDEPENDENT_TEST.value


_ROLE_STAGE = {
    CampaignRole.PRIMARY_DISCRIMINATOR.value: CampaignStageType.DISCRIMINATE.value,
    CampaignRole.PRIMARY_INTERVENTION.value: CampaignStageType.INTERVENE.value,
    CampaignRole.SECONDARY_INDEPENDENT_TEST.value: CampaignStageType.INTERVENE.value,
    CampaignRole.VALIDATION_TEST.value: CampaignStageType.VALIDATE.value,
    CampaignRole.PROTECTION_CHECK.value: CampaignStageType.REVIEW.value,
    CampaignRole.CONTINGENCY.value: CampaignStageType.INTERVENE.value,
    CampaignRole.RETIRED.value: CampaignStageType.REVIEW.value,
}


def _stage_for_role(role: str) -> str:
    return _ROLE_STAGE.get(role, CampaignStageType.INTERVENE.value)


def _tally(fields: Sequence[str], outcome_idx) -> dict:
    t = {"confirmed": 0, "partial": 0, "regression": 0, "inconclusive": 0,
         "protected_regression": 0, "sessions": set()}
    for f in fields:
        for e in outcome_idx.get(f, []):
            st = e["outcome_status"]
            if st == "confirmed_improvement":
                t["confirmed"] += 1
            elif st == "partial_improvement":
                t["partial"] += 1
            elif st == "regression":
                t["regression"] += 1
            elif st in ("no_meaningful_change", "confounded", "insufficient_evidence"):
                t["inconclusive"] += 1
            if e["session"]:
                t["sessions"].add(e["session"])
    t["sessions"] = len(t["sessions"])
    return t


def _completion_criteria(family, competing, tally, validated, protected_regressed, live,
                         diagnoses) -> Tuple[CompletionCriterion, ...]:
    def c(cid, desc, ok, blocker="", why=""):
        return CompletionCriterion(cid, desc, bool(ok), tuple(diagnoses), blocker, why)
    out = [
        c("issue_confirmed", "the target issue is a confirmed recurring diagnosis", True,
          why="campaign exists because a recurring canonical diagnosis was produced"),
        c("mechanism_discriminated",
          "competing mechanisms are sufficiently rejected", (not competing) or tally["confirmed"] > 0,
          "" if (not competing) or tally["confirmed"] > 0 else "run the discriminating test",
          "single supported mechanism, or a confirmed outcome disambiguates"),
        c("intervention_confirmed", "a bounded setup direction is confirmed as an improvement",
          tally["confirmed"] > 0, "" if tally["confirmed"] > 0 else "no confirmed improvement yet",
          "a prior single-field outcome confirmed_improvement on a campaign field"),
        c("no_protected_regression", "no confirmed-good behaviour regressed",
          not protected_regressed, "a protected behaviour regressed" if protected_regressed else "",
          "no protected-good regression observed in the outcome history"),
        c("validated", "the successful direction is validated across the required window",
          validated, "" if validated else "repeat / corroborate the successful direction",
          f"needs >= {_VALIDATION_MIN_CONFIRMATIONS} confirmations"),
        c("freeze_eligible", "the confirmed fields are eligible for freeze via existing authority",
          tally["confirmed"] > 0 and validated and not protected_regressed,
          "" if (tally["confirmed"] > 0 and validated and not protected_regressed)
          else "confirm + validate before freeze", "gated on intervention_confirmed + validated"),
    ]
    return tuple(out)


def _status(stale, live, experiments, tally, validated, protected_regressed, all_retired,
            criteria) -> str:
    if stale:
        return CampaignStatus.STALE.value
    confirmed = tally["confirmed"] > 0
    freeze_ok = all(c.satisfied for c in criteria)
    if freeze_ok:
        return CampaignStatus.COMPLETED.value if tally["sessions"] >= _VALIDATION_MIN_CONFIRMATIONS \
            else CampaignStatus.READY_TO_FREEZE.value
    if confirmed and not validated:
        return CampaignStatus.VALIDATION_REQUIRED.value
    if all_retired and not confirmed:
        # every candidate retired (already confirmed/rejected/superseded) and nothing to test
        return CampaignStatus.ABANDONED.value if tally["regression"] > 0 \
            else CampaignStatus.BLOCKED.value
    if not live:
        return CampaignStatus.BLOCKED.value
    if tally["confirmed"] or tally["partial"] or tally["regression"] or tally["inconclusive"]:
        return CampaignStatus.ACTIVE.value
    return CampaignStatus.NOT_STARTED.value


def _stages(family, region, vals, experiments, tally, competing, validated, status
            ) -> Tuple[CampaignStage, ...]:
    def stage(stype, purpose, done, exp_ids, exit_c, nxt, know, blockers=()):
        return CampaignStage(f"{stype}", stype, purpose, tuple(exp_ids), (),
                             "complete" if done else "open", tuple(blockers), know, exit_c, nxt)
    disc_ids = [e.candidate_id for e in experiments
                if e.campaign_role == CampaignRole.PRIMARY_DISCRIMINATOR.value]
    interv_ids = [e.candidate_id for e in experiments
                  if e.campaign_role in (CampaignRole.PRIMARY_INTERVENTION.value,
                                         CampaignRole.SECONDARY_INDEPENDENT_TEST.value,
                                         CampaignRole.CONTINGENCY.value)]
    valid_ids = [e.candidate_id for e in experiments
                 if e.campaign_role == CampaignRole.VALIDATION_TEST.value]
    stages = [
        stage(CampaignStageType.DEFINE.value,
              "confirm the repeated issue and protect confirmed-good behaviours", True,
              [], "recurring diagnosis + protected-good identified",
              "protect confirmed-good behaviours", "the issue is real and bounded"),
    ]
    if competing:
        stages.append(stage(
            CampaignStageType.DISCRIMINATE.value,
            "run the highest-value test that separates competing mechanisms",
            tally["confirmed"] > 0, disc_ids, "competing mechanisms rejected",
            "run the primary discriminating test", "which mechanism is driving the issue"))
    stages.append(stage(
        CampaignStageType.INTERVENE.value, "run the preferred bounded setup change",
        tally["confirmed"] > 0, interv_ids, "a bounded direction confirmed",
        "run the preferred bounded intervention via the existing lifecycle",
        "does the bounded change improve the issue"))
    stages.append(stage(
        CampaignStageType.REVIEW.value, "evaluate outcome and prediction accuracy",
        tally["confirmed"] > 0 or tally["regression"] > 0, [],
        "outcome + reconciliation reviewed", "review the Phase-3 outcome + Phase-11 reconciliation",
        "did the change do what was predicted"))
    stages.append(stage(
        CampaignStageType.VALIDATE.value, "repeat / corroborate the successful direction",
        validated, valid_ids, f">= {_VALIDATION_MIN_CONFIRMATIONS} confirmations",
        "validate over repeated laps / sessions", "is the improvement repeatable"))
    stages.append(stage(
        CampaignStageType.FREEZE.value, "stop changing the confirmed fields",
        status in (CampaignStatus.COMPLETED.value, CampaignStatus.READY_TO_FREEZE.value), [],
        "confirmed fields frozen via existing authority",
        "freeze confirmed fields through the existing freeze/lifecycle authority",
        "lock the confirmed direction"))
    stages.append(stage(
        CampaignStageType.RACE_READY.value, "use the validated setup under event conditions",
        status == CampaignStatus.COMPLETED.value, [], "validated setup used for the event",
        "race the validated setup", "the objective is met for the event"))
    return tuple(stages)


def _progress(experiments, tally, criteria, mechanisms, mechanism_confirmed, protected,
              validated) -> CampaignProgress:
    total = len(experiments)
    retired = sum(1 for e in experiments if e.campaign_role == CampaignRole.RETIRED.value)
    blocked = sum(1 for e in experiments if e.dependency_state == "depends_on_discriminator"
                  and not mechanism_confirmed)
    active = sum(1 for e in experiments if e.retirement_state == "" and e.needs_further_testing)
    completed_useful = tally["confirmed"] + tally["partial"]
    validation_remaining = 0 if validated else (
        max(0, _VALIDATION_MIN_CONFIRMATIONS - tally["confirmed"]) if tally["confirmed"] else 0)
    unresolved_mech = 0 if mechanism_confirmed else len(mechanisms)
    confirmed_mech = len(mechanisms) if mechanism_confirmed else 0
    crit_ok = sum(1 for c in criteria if c.satisfied)
    crit_total = len(criteria)
    # transparent, visibly-derived progress: satisfied completion criteria / total.
    pct = int(round(100 * crit_ok / crit_total)) if crit_total else 0
    factors = tuple({"factor": c.criterion_id, "value": c.satisfied, "weight": 1,
                     "rationale": c.description} for c in criteria)
    maturity = ("mature" if pct >= 85 else "developing" if pct >= 50 else
                "early" if pct >= 20 else "insufficient_evidence")
    if not any(e.execution_state != "not_tested" for e in experiments):
        maturity = "insufficient_evidence"
    rationale = (f"{crit_ok}/{crit_total} completion criteria satisfied "
                 f"(1 weight each, visible); confirmed={tally['confirmed']}, "
                 f"regressions={tally['regression']}, validated={validated}")
    return CampaignProgress(
        total_experiments=total, active_experiments=active, completed_useful=completed_useful,
        confirmed_improvement=tally["confirmed"], partial_improvement=tally["partial"],
        regressions=tally["regression"], inconclusive=tally["inconclusive"], retired=retired,
        blocked=blocked, validation_remaining=validation_remaining,
        unresolved_mechanisms=unresolved_mech, confirmed_mechanisms=confirmed_mech,
        protected_good=len(protected), criteria_satisfied=crit_ok, criteria_total=crit_total,
        progress_pct=pct, maturity=maturity, factors=factors, rationale=rationale)


def _blockers(stale, live, all_retired, tally, protected_regressed) -> List[str]:
    out = []
    if stale:
        out.extend(stale)
    if all_retired and tally["confirmed"] == 0:
        out.append("all candidate experiments are retired (confirmed / rejected / superseded)")
    elif not live and tally["confirmed"] == 0:
        out.append("no legal experiment currently available for this objective")
    if protected_regressed:
        out.append("a confirmed-good behaviour regressed and must be protected")
    return out


def _next_action(status, stages) -> str:
    nxt = {
        CampaignStatus.STALE.value: "context has changed - do not execute; re-plan for the "
                                    "active car/track/discipline",
        CampaignStatus.BLOCKED.value: "gather the missing evidence before proposing a change",
        CampaignStatus.ABANDONED.value: "objective invalidated by evidence - see alternatives",
        CampaignStatus.VALIDATION_REQUIRED.value: "validate the successful direction over "
                                                  "repeated laps / sessions",
        CampaignStatus.READY_TO_FREEZE.value: "freeze the confirmed fields via the existing "
                                              "freeze / lifecycle authority",
        CampaignStatus.COMPLETED.value: "objective met - use the validated setup for the event",
        CampaignStatus.NOT_STARTED.value: "run the highest-value experiment for this objective",
        CampaignStatus.ACTIVE.value: "continue with the next open stage's experiment",
    }.get(status, "review the campaign")
    return nxt


def _gate_mutually_exclusive(campaigns: List[EngineeringCampaign], mutex
                             ) -> List[EngineeringCampaign]:
    """If two campaigns propose mutually-exclusive candidates, the lower-priority campaign is
    gated (BLOCKED until the other completes). Deterministic by (status priority, best value,
    campaign_id)."""
    # map candidate id -> owning campaign index
    owner: Dict[str, int] = {}
    for i, c in enumerate(campaigns):
        for e in c.experiments:
            owner[e.candidate_id] = i
    # find blocking pairs
    block_idx: Dict[int, str] = {}
    for cid, partners in mutex.items():
        oi = owner.get(cid)
        for p in partners:
            pj = owner.get(p)
            if oi is None or pj is None or oi == pj:
                continue
            # decide the winner deterministically
            ci, cj = campaigns[oi], campaigns[pj]
            keep, drop = (oi, pj) if _campaign_priority(ci) <= _campaign_priority(cj) else (pj, oi)
            if drop not in block_idx and campaigns[drop].status not in (
                    CampaignStatus.STALE.value, CampaignStatus.COMPLETED.value,
                    CampaignStatus.READY_TO_FREEZE.value):
                block_idx[drop] = campaigns[keep].identity.campaign_id
    if not block_idx:
        return campaigns
    out = []
    for i, c in enumerate(campaigns):
        if i in block_idx and c.status in (CampaignStatus.ACTIVE.value,
                                           CampaignStatus.NOT_STARTED.value):
            reason = (f"blocked until {block_idx[i]} completes - both propose mutually-"
                      f"exclusive changes to the same field")
            out.append(_reblock(c, reason))
        else:
            out.append(c)
    return out


def _campaign_priority(c: EngineeringCampaign) -> tuple:
    order = {CampaignStatus.VALIDATION_REQUIRED.value: 0, CampaignStatus.ACTIVE.value: 1,
             CampaignStatus.NOT_STARTED.value: 2}
    best = max((e.engineering_value for e in c.experiments), default=0.0)
    return (order.get(c.status, 5), -round(best, 6), c.identity.campaign_id)


def _reblock(c: EngineeringCampaign, reason: str) -> EngineeringCampaign:
    blockers = tuple(dict.fromkeys(list(c.blockers) + [reason]))
    fp = _fp({"id": c.identity.campaign_id, "status": CampaignStatus.BLOCKED.value,
              "reblock": reason, "base": c.content_fingerprint})
    return EngineeringCampaign(
        identity=c.identity, objective=c.objective, status=CampaignStatus.BLOCKED.value,
        stages=c.stages, experiments=c.experiments, progress=c.progress, roadmap=c.roadmap,
        blockers=blockers, grouping_rationale=c.grouping_rationale,
        next_action="gated by a mutually-exclusive campaign; " + c.next_action,
        content_fingerprint=fp)


def _recommended_focus(campaigns: List[EngineeringCampaign]) -> Optional[dict]:
    """Deterministic focus: prefer campaigns that can progress now, ordered by
    (status priority, best Phase-17 value, campaign_id). Ranking stays owned by Phase 17."""
    eligible = [c for c in campaigns if c.status in (
        CampaignStatus.VALIDATION_REQUIRED.value, CampaignStatus.ACTIVE.value,
        CampaignStatus.NOT_STARTED.value)]
    if not eligible:
        return None
    best = min(eligible, key=_campaign_priority)
    return {"objective_id": best.identity.campaign_id, "title": best.objective.title,
            "status": best.status, "next_action": best.next_action,
            "reason": "can progress now; highest Phase-17 engineering value at the best-ready "
                      "status (ranking owned by Phase 17)"}


def _programme_roadmap(campaigns: List[EngineeringCampaign], mutex) -> List[dict]:
    out = []
    for i, c in enumerate(sorted(campaigns, key=_campaign_priority)):
        out.append({"order": i, "campaign_id": c.identity.campaign_id,
                    "objective": c.objective.title, "status": c.status,
                    "next_action": c.next_action,
                    "blockers": list(c.blockers)})
    return out


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _campaign_id(scope: Mapping, family: str, region: str) -> str:
    raw = "|".join((_lc(scope.get("car")), _lc(scope.get("track")), _lc(scope.get("layout")),
                    _lc(scope.get("discipline")), _lc(scope.get("gt7_version")), family, region))
    return f"{ENGINEERING_CAMPAIGN_VERSION}:camp:{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def knowledge_versions() -> dict:
    return {"engineering_campaign": ENGINEERING_CAMPAIGN_VERSION,
            "experiment_portfolio": EXPERIMENT_PORTFOLIO_VERSION,
            "schema": ENGINEERING_CAMPAIGN_SCHEMA}


def _fp(payload: dict) -> str:
    return (f"{ENGINEERING_CAMPAIGN_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])
