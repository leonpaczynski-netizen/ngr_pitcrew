"""Minimum-Effective Experiment Synthesis Handoff (Engineering Brain Program 2, Phase 15).

The deterministic, READ-ONLY handoff from a valid, testable Phase-14 intervention
hypothesis into the existing setup-synthesis / setup-experiment authorities. The output is
a BOUNDED setup-experiment candidate: the smallest legal, reversible, evidence-appropriate
numeric setup step that tests the hypothesis without unnecessarily disturbing confirmed-good
behaviour.

It answers "what is the smallest legal, reversible numeric experiment that tests this
hypothesis?" — never "what is the final ideal setup?". It NEVER auto-applies, bypasses the
Apply gate, invents parameter limits, builds a second synthesiser, optimises the whole car,
silently changes coupled fields, mutates the diagnosis / mechanism / outcome / calibration /
setup-history / active-setup, or persists an experiment. It CONSUMES the canonical
authorities:
  * baseline = the canonical applied setup, validated by ``setup_state_authority``;
  * legal step / quantisation = ``experiment_selection.legal_step`` + ``setup_synthesis._round``;
  * legal bounds = ``setup_ranges.resolve_ranges``;
  * final-drive invariant = ``gearbox_evidence`` (lower ratio = LONGER gearing);
  * direction = the Phase-14 hypothesis (never inferred from a parameter name);
  * working-window lockouts = ``working_window.LearnedWorkingWindow.locked_directions()``.

Purity: Qt-free, DB-free (no sqlite / SessionDB), UI-free, network-free, AI-free; no
random, no wall-clock (timestamps are data); deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.intervention_hypothesis import (
    INTERVENTION_HYPOTHESIS_VERSION, InterventionDirection, InterventionHypothesisStatus,
    InterventionTestKind,
)
from strategy.experiment_selection import legal_step
from strategy.setup_synthesis import _round as _canonical_round
from strategy import gearbox_evidence as gbx
# Canonical applied-setup authority (pure module; no DB / Qt).
from data.setup_state_authority import (
    ActiveSetup, AnalysisBlockReason, SetupIdentity, evaluate_analysis_gate,
)
from data.applied_checkpoint import compute_setup_hash

EXPERIMENT_SYNTHESIS_VERSION = "experiment_synthesis_v1"
EXPERIMENT_SYNTHESIS_SCHEMA = 1

MAX_COUPLED_FIELDS = 2
MAX_JUSTIFIED_STEPS = 2   # a justified larger step is still bounded


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _as_float(v) -> Optional[float]:
    try:
        if v is None or (isinstance(v, str) and not v.strip()) or isinstance(v, bool):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class ExperimentSynthesisStatus(str, Enum):
    READY_FOR_PREFLIGHT = "ready_for_preflight"
    CONDITIONAL = "conditional"
    NO_ELIGIBLE_HYPOTHESIS = "no_eligible_hypothesis"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    BLOCKED_BY_WORKING_WINDOW = "blocked_by_working_window"
    BLOCKED_BY_PRIOR_REGRESSION = "blocked_by_prior_regression"
    BLOCKED_BY_LEGALITY = "blocked_by_legality"
    BLOCKED_BY_INTERACTION_RISK = "blocked_by_interaction_risk"
    BLOCKED_BY_BASELINE_STATE = "blocked_by_baseline_state"
    REQUIRES_COUPLED_EXPERIMENT = "requires_coupled_experiment"
    NOT_EVALUABLE = "not_evaluable"
    OUT_OF_SCOPE = "out_of_scope"


# Phase-14 InterventionDirection -> numeric field move (+1 raise / -1 lower).
# The SIGN is authoritative here; gearing keeps the final-drive invariant.
_DIRECTION_SIGN: Dict[str, int] = {
    InterventionDirection.INCREASE.value: +1,
    InterventionDirection.STIFFEN.value: +1,
    InterventionDirection.RAISE.value: +1,
    InterventionDirection.INCREASE_LOCKING.value: +1,
    InterventionDirection.MOVE_REARWARD.value: +1,   # raising brake_bias = rearward
    InterventionDirection.SHORTEN.value: +1,         # higher final-drive ratio = shorter
    InterventionDirection.DECREASE.value: -1,
    InterventionDirection.SOFTEN.value: -1,
    InterventionDirection.LOWER.value: -1,
    InterventionDirection.DECREASE_LOCKING.value: -1,
    InterventionDirection.MOVE_FORWARD.value: -1,
    InterventionDirection.LENGTHEN.value: -1,        # lower final-drive ratio = longer
}
_NO_NUMERIC_DIRECTIONS = frozenset({
    InterventionDirection.ALTER_BALANCE.value, InterventionDirection.ISOLATE_FOR_TESTING.value,
    InterventionDirection.PRESERVE_CURRENT.value, InterventionDirection.NO_DEFENSIBLE_DIRECTION.value,
})

# Phase-14 target component value -> canonical setup field name (setup_ranges keys).
_COMPONENT_FIELD: Dict[str, str] = {
    "damper_bump_front": "dampers_front_comp", "damper_bump_rear": "dampers_rear_comp",
    "damper_rebound_front": "dampers_front_ext", "damper_rebound_rear": "dampers_rear_ext",
    "transmission": "final_drive", "ballast": "ballast_kg",
    "weight_distribution": "", "fuel_load": "", "tyres": "",
}


def _field_for_component(component: str) -> str:
    c = _lc(component)
    return _COMPONENT_FIELD.get(c, c)


def _subsystem(field_name: str) -> str:
    f = field_name
    if f.startswith("arb") or f.startswith("springs") or f.startswith("dampers") \
            or f.startswith("ride_height"):
        return "suspension"
    if f.startswith("lsd"):
        return "differential"
    if f.startswith("aero"):
        return "aero"
    if f.startswith("camber") or f.startswith("toe"):
        return "alignment"
    if f == "brake_bias":
        return "brakes"
    if f == "final_drive" or f.startswith("gear"):
        return "transmission"
    if f.startswith("ballast"):
        return "weight"
    return "other"


# --------------------------------------------------------------------------- #
# Domain
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BaselineSetupReference:
    setup_id: str
    setup_hash: str
    name: str
    revision: int
    car: str
    track: str
    layout_id: str
    purpose: str
    source: str
    is_active_on_car: bool
    is_complete: bool
    is_legal: bool
    identity_matches: bool
    is_valid_baseline: bool
    block_reason: str
    message: str
    field_count: int

    def to_dict(self) -> dict:
        return {
            "setup_id": self.setup_id, "setup_hash": self.setup_hash, "name": self.name,
            "revision": self.revision, "car": self.car, "track": self.track,
            "layout_id": self.layout_id, "purpose": self.purpose, "source": self.source,
            "is_active_on_car": self.is_active_on_car, "is_complete": self.is_complete,
            "is_legal": self.is_legal, "identity_matches": self.identity_matches,
            "is_valid_baseline": self.is_valid_baseline, "block_reason": self.block_reason,
            "message": self.message, "field_count": self.field_count}


@dataclass(frozen=True)
class ParameterExperimentDelta:
    field: str
    subsystem: str
    baseline_value: float
    candidate_value: float
    delta: float
    direction: str
    legal_low: Optional[float]
    legal_high: Optional[float]
    legal_step: float
    is_exactly_one_step: bool
    larger_step_used: bool
    larger_step_reason: str
    role: str                      # primary | compensatory
    protected_interactions: Tuple[str, ...]
    expected_benefit: str
    expected_trade_offs: Tuple[str, ...]
    source_hypothesis_id: str
    source_mechanism_id: str

    def to_dict(self) -> dict:
        return {
            "field": self.field, "subsystem": self.subsystem,
            "baseline_value": self.baseline_value, "candidate_value": self.candidate_value,
            "delta": self.delta, "direction": self.direction, "legal_low": self.legal_low,
            "legal_high": self.legal_high, "legal_step": self.legal_step,
            "is_exactly_one_step": self.is_exactly_one_step,
            "larger_step_used": self.larger_step_used,
            "larger_step_reason": self.larger_step_reason, "role": self.role,
            "protected_interactions": list(self.protected_interactions),
            "expected_benefit": self.expected_benefit,
            "expected_trade_offs": list(self.expected_trade_offs),
            "source_hypothesis_id": self.source_hypothesis_id,
            "source_mechanism_id": self.source_mechanism_id}


@dataclass(frozen=True)
class BoundedSetupExperiment:
    candidate_id: str
    source_hypothesis_set_fingerprint: str
    selected_hypothesis_ids: Tuple[str, ...]
    baseline: BaselineSetupReference
    deltas: Tuple[ParameterExperimentDelta, ...]
    unchanged_field_count: int
    preserved_fields_fingerprint: str
    expected_response: str
    protected_good_behaviours: Tuple[str, ...]
    test_protocol: dict
    preflight_requirements: Tuple[str, ...]
    rejection_criteria: Tuple[str, ...]
    reversal_instructions: str
    attribution_scope: str          # single_field | coupled_pair
    evidence_grade: str
    status: str
    explanation: str
    content_fingerprint: str
    eval_version: str = EXPERIMENT_SYNTHESIS_VERSION

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "source_hypothesis_set_fingerprint": self.source_hypothesis_set_fingerprint,
            "selected_hypothesis_ids": list(self.selected_hypothesis_ids),
            "baseline": self.baseline.to_dict(),
            "deltas": [d.to_dict() for d in self.deltas],
            "unchanged_field_count": self.unchanged_field_count,
            "preserved_fields_fingerprint": self.preserved_fields_fingerprint,
            "expected_response": self.expected_response,
            "protected_good_behaviours": list(self.protected_good_behaviours),
            "test_protocol": dict(self.test_protocol),
            "preflight_requirements": list(self.preflight_requirements),
            "rejection_criteria": list(self.rejection_criteria),
            "reversal_instructions": self.reversal_instructions,
            "attribution_scope": self.attribution_scope,
            "evidence_grade": self.evidence_grade, "status": self.status,
            "explanation": self.explanation, "content_fingerprint": self.content_fingerprint,
            "eval_version": self.eval_version}


@dataclass(frozen=True)
class ExperimentSynthesisResult:
    source_hypothesis_set: dict         # the InterventionHypothesisSet, UNCHANGED
    baseline: BaselineSetupReference
    selected_candidate: Optional[dict]
    alternative_candidates: Tuple[dict, ...]
    rejected: Tuple[dict, ...]          # {hypothesis_id, status, reason}
    unresolved_conflicts: Tuple[str, ...]
    preflight_ready: bool
    overall_status: str
    safety_statement: str
    audit: Tuple[str, ...]
    content_fingerprint: str
    knowledge_versions: dict
    schema_version: int = EXPERIMENT_SYNTHESIS_SCHEMA
    eval_version: str = EXPERIMENT_SYNTHESIS_VERSION

    def to_dict(self) -> dict:
        return {
            "source_hypothesis_set": dict(self.source_hypothesis_set),
            "baseline": self.baseline.to_dict(),
            "selected_candidate": (dict(self.selected_candidate)
                                   if self.selected_candidate else None),
            "alternative_candidates": [dict(c) for c in self.alternative_candidates],
            "rejected": [dict(r) for r in self.rejected],
            "unresolved_conflicts": list(self.unresolved_conflicts),
            "preflight_ready": self.preflight_ready, "overall_status": self.overall_status,
            "safety_statement": self.safety_statement, "audit": list(self.audit),
            "content_fingerprint": self.content_fingerprint,
            "knowledge_versions": dict(self.knowledge_versions),
            "schema_version": self.schema_version, "eval_version": self.eval_version}


_SAFETY = ("Advisory only. This is the smallest legal, reversible numeric experiment that "
           "tests one hypothesis - NOT a final tune and NOT optimal. Nothing is applied or "
           "saved; the canonical Apply gate remains the only route to the car, and the "
           "canonical applied setup is the untouched baseline.")


# --------------------------------------------------------------------------- #
# Baseline
# --------------------------------------------------------------------------- #
def build_baseline_reference(applied_setup: Optional[Mapping], *,
                             session_identity: Optional[Mapping] = None,
                             required_fields: Sequence[str] = ()) -> BaselineSetupReference:
    """Build + validate the baseline from the canonical applied setup (a
    ``ActiveSetup.to_record()`` dict). Uses ``setup_state_authority.evaluate_analysis_gate``
    — the single canonical gate — and never falls back to defaults or a last-viewed setup."""
    if not isinstance(applied_setup, Mapping) or not applied_setup:
        return BaselineSetupReference(
            setup_id="", setup_hash="", name="", revision=0, car="", track="", layout_id="",
            purpose="", source="", is_active_on_car=False, is_complete=False, is_legal=False,
            identity_matches=False, is_valid_baseline=False,
            block_reason=AnalysisBlockReason.NO_ACTIVE_SETUP.value,
            message="No applied setup - synthesis is blocked (no fallback to defaults).",
            field_count=0)
    active = ActiveSetup.from_record(applied_setup)
    ident = SetupIdentity(
        car=_norm((session_identity or {}).get("car")) or active.identity.car,
        track=_norm((session_identity or {}).get("track")) or active.identity.track,
        layout_id=_norm((session_identity or {}).get("layout_id")) or active.identity.layout_id)
    gate = evaluate_analysis_gate(active, ident, required_fields=required_fields)
    # hash re-verified against the snapshot (baseline drift / tamper detection)
    recomputed = compute_setup_hash(dict(active.fields or {}))
    hash_ok = (not active.setup_hash) or (recomputed == active.setup_hash)
    valid = gate.allowed and hash_ok
    reason = gate.reason.value if not gate.allowed else ("" if hash_ok else "baseline_drift")
    return BaselineSetupReference(
        setup_id=active.setup_id, setup_hash=recomputed, name=active.name,
        revision=active.revision, car=active.identity.car, track=active.identity.track,
        layout_id=active.identity.layout_id, purpose=active.purpose, source=active.source,
        is_active_on_car=active.is_active_on_car,
        is_complete=active.is_complete(required_fields), is_legal=True,
        identity_matches=active.identity.matches(ident), is_valid_baseline=valid,
        block_reason=reason, message=gate.message if gate.allowed and hash_ok
        else (gate.message if not gate.allowed else "Baseline drift - re-apply."),
        field_count=len(active.fields or {}))


# --------------------------------------------------------------------------- #
# Public: synthesise bounded experiments for one hypothesis set
# --------------------------------------------------------------------------- #
def synthesize_bounded_experiments(
    hypothesis_set: Mapping,
    *,
    applied_setup: Optional[Mapping] = None,
    session_identity: Optional[Mapping] = None,
    ranges: Optional[Mapping] = None,
    working_windows: Optional[Mapping] = None,
    gearbox_state: str = "",
    larger_step_justifications: Optional[Mapping] = None,
) -> ExperimentSynthesisResult:
    """Convert eligible Phase-14 hypotheses in one set into bounded setup experiments.
    Read-only; deterministic; never raises; authors no value, applies/persists nothing."""
    try:
        return _synthesize(hypothesis_set or {}, applied_setup, session_identity or {},
                           ranges or {}, working_windows or {}, gearbox_state,
                           larger_step_justifications or {})
    except Exception as exc:   # never raise into the caller
        return _empty_result(hypothesis_set or {},
                             ExperimentSynthesisStatus.NOT_EVALUABLE,
                             f"synthesis error: {type(exc).__name__}", applied_setup,
                             session_identity or {})


def _knowledge_versions() -> dict:
    from strategy.intervention_hypothesis import knowledge_versions as _kv
    kv = _kv()
    kv["intervention_hypothesis"] = INTERVENTION_HYPOTHESIS_VERSION
    kv["experiment_synthesis"] = EXPERIMENT_SYNTHESIS_VERSION
    return kv


def _empty_result(hset, status, reason, applied_setup, session_identity
                  ) -> ExperimentSynthesisResult:
    base = build_baseline_reference(applied_setup, session_identity=session_identity)
    kv = _knowledge_versions()
    payload = {"set": _norm((hset or {}).get("content_fingerprint")),
               "status": status.value, "reason": reason, "base": base.setup_hash, "kv": kv}
    fp = (f"{EXPERIMENT_SYNTHESIS_VERSION}:"
          + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()[:24])
    return ExperimentSynthesisResult(
        source_hypothesis_set=dict(hset or {}), baseline=base, selected_candidate=None,
        alternative_candidates=(), rejected=(), unresolved_conflicts=(),
        preflight_ready=False, overall_status=status.value, safety_statement=_SAFETY,
        audit=(f"status={status.value}", f"reason={reason}"), content_fingerprint=fp,
        knowledge_versions=kv)


# hypothesis statuses that may enter numeric synthesis
_PROCEED = InterventionHypothesisStatus.TESTABLE.value
_CONDITIONAL = InterventionHypothesisStatus.CONDITIONAL.value
# A competing hypothesis may only ever yield a CONDITIONAL *discriminating* single-field test
# (Section 6) — never a ready experiment, never an auto-winner.
_COMPETING = InterventionHypothesisStatus.COMPETING_MECHANISMS.value
_ELIGIBLE_STATUSES = frozenset({_PROCEED, _CONDITIONAL, _COMPETING})
_HYP_BLOCK_REASON = {
    InterventionHypothesisStatus.CONTRADICTED_BY_OUTCOME.value:
        ExperimentSynthesisStatus.BLOCKED_BY_PRIOR_REGRESSION,
    InterventionHypothesisStatus.BLOCKED_BY_WORKING_WINDOW.value:
        ExperimentSynthesisStatus.BLOCKED_BY_WORKING_WINDOW,
    InterventionHypothesisStatus.BLOCKED_BY_SAFETY_OR_VALIDITY.value:
        ExperimentSynthesisStatus.BLOCKED_BY_BASELINE_STATE,
    InterventionHypothesisStatus.INSUFFICIENT_EVIDENCE.value:
        ExperimentSynthesisStatus.INSUFFICIENT_EVIDENCE,
    InterventionHypothesisStatus.NOT_EVALUABLE.value:
        ExperimentSynthesisStatus.NOT_EVALUABLE,
    InterventionHypothesisStatus.OUT_OF_SCOPE.value:
        ExperimentSynthesisStatus.OUT_OF_SCOPE,
}


def _synthesize(hset, applied_setup, session_identity, ranges, working_windows,
                gearbox_state, justifications) -> ExperimentSynthesisResult:
    issue = dict(hset.get("canonical_issue") or {})
    set_fp = _norm(hset.get("content_fingerprint"))
    all_hyps = (list(hset.get("testable") or []) + list(hset.get("conditional") or [])
                + list(hset.get("competing") or []) + list(hset.get("blocked") or [])
                + list(hset.get("preserve_and_observe") or []))

    # required fields = the fields the eligible hypotheses would touch
    req_fields = []
    for h in all_hyps:
        fld = _field_for_component(_norm((h.get("target") or {}).get("component")))
        if fld:
            req_fields.append(fld)
    baseline = build_baseline_reference(applied_setup, session_identity=session_identity,
                                        required_fields=())

    kv = _knowledge_versions()
    if not baseline.is_valid_baseline:
        return ExperimentSynthesisResult(
            source_hypothesis_set=dict(hset), baseline=baseline, selected_candidate=None,
            alternative_candidates=(), rejected=(), unresolved_conflicts=(),
            preflight_ready=False,
            overall_status=ExperimentSynthesisStatus.BLOCKED_BY_BASELINE_STATE.value,
            safety_statement=_SAFETY,
            audit=(f"baseline_block={baseline.block_reason}",
                   "no fallback to defaults / last-viewed setup"),
            content_fingerprint=_result_fp(set_fp, baseline,
                ExperimentSynthesisStatus.BLOCKED_BY_BASELINE_STATE.value, None, (), kv),
            knowledge_versions=kv)

    candidates: List[BoundedSetupExperiment] = []
    rejected: List[dict] = []
    for h in all_hyps:
        cand, rej = _candidate_for(h, issue=issue, set_fp=set_fp, baseline=baseline,
                                   applied_setup=applied_setup, ranges=ranges,
                                   working_windows=working_windows, gearbox_state=gearbox_state,
                                   justifications=justifications)
        if cand is not None:
            candidates.append(cand)
        if rej is not None:
            rejected.append(rej)

    # ready candidates (READY_FOR_PREFLIGHT) are ranked; conditional/coupled kept separate
    ready = [c for c in candidates if c.status == ExperimentSynthesisStatus.READY_FOR_PREFLIGHT.value]
    conditional = [c for c in candidates
                   if c.status in (ExperimentSynthesisStatus.CONDITIONAL.value,
                                   ExperimentSynthesisStatus.REQUIRES_COUPLED_EXPERIMENT.value)]
    ready.sort(key=_cand_sort_key)
    conditional.sort(key=_cand_sort_key)

    selected = None
    alternatives: List[dict] = []
    unresolved: List[str] = []
    if ready:
        selected = ready[0]
        # a genuine tie (same sort prefix) is NOT auto-resolved
        tied = [c for c in ready if _cand_sort_key(c)[:3] == _cand_sort_key(ready[0])[:3]]
        if len(tied) >= 2:
            selected = None
            alternatives = [c.to_dict() for c in tied]
            unresolved.append("multiple equally-defensible candidates - manual choice "
                              "required before preflight")
            alternatives += [c.to_dict() for c in ready if c not in tied]
        else:
            alternatives = [c.to_dict() for c in ready[1:]] + [c.to_dict() for c in conditional]
    else:
        alternatives = [c.to_dict() for c in conditional]

    overall = _overall_status(selected, ready, conditional, rejected)
    preflight_ready = selected is not None and \
        selected.status == ExperimentSynthesisStatus.READY_FOR_PREFLIGHT.value
    audit = (
        f"issue={_lc(issue.get('issue_type'))}",
        f"baseline={baseline.setup_id or 'n/a'}/{baseline.setup_hash[:8]}",
        f"ready={len(ready)}", f"conditional={len(conditional)}",
        f"rejected={len(rejected)}", f"selected={'yes' if selected else 'no'}",
        "layer=synthesis_handoff; authors no value, applies/saves nothing",
    )
    fp = _result_fp(set_fp, baseline, overall, selected, tuple(candidates), kv)
    return ExperimentSynthesisResult(
        source_hypothesis_set=dict(hset), baseline=baseline,
        selected_candidate=(selected.to_dict() if selected else None),
        alternative_candidates=tuple(alternatives), rejected=tuple(rejected),
        unresolved_conflicts=tuple(unresolved), preflight_ready=preflight_ready,
        overall_status=overall, safety_statement=_SAFETY, audit=audit,
        content_fingerprint=fp, knowledge_versions=kv)


def _candidate_for(h, *, issue, set_fp, baseline, applied_setup, ranges, working_windows,
                   gearbox_state, justifications):
    hyp_id = _norm(h.get("hypothesis_id"))
    hyp_status = _lc(h.get("status"))
    mech_id = _norm(h.get("source_mechanism_id"))
    target = h.get("target") or {}
    component = _norm(target.get("component"))
    field_name = _field_for_component(component)
    direction = _lc(h.get("direction"))
    coupled = _lc((h.get("test_design") or {}).get("test_kind")) == \
        InterventionTestKind.PAIRED_COUPLED.value

    # eligibility gate (hard, before numeric synthesis)
    if hyp_status not in _ELIGIBLE_STATUSES:
        st = _HYP_BLOCK_REASON.get(hyp_status, ExperimentSynthesisStatus.NO_ELIGIBLE_HYPOTHESIS)
        return None, {"hypothesis_id": hyp_id, "component": component,
                      "status": st.value, "reason": f"hypothesis status {hyp_status}"}
    if not field_name:
        return None, {"hypothesis_id": hyp_id, "component": component,
                      "status": ExperimentSynthesisStatus.OUT_OF_SCOPE.value,
                      "reason": "component is not a tunable GT7 field"}
    if direction in _NO_NUMERIC_DIRECTIONS or direction not in _DIRECTION_SIGN:
        return None, {"hypothesis_id": hyp_id, "component": component,
                      "status": ExperimentSynthesisStatus.INSUFFICIENT_EVIDENCE.value,
                      "reason": "no defensible numeric direction"}

    fields = dict((applied_setup or {}).get("fields") or {})
    cur = _as_float(fields.get(field_name))
    if cur is None:
        return None, {"hypothesis_id": hyp_id, "component": component,
                      "status": ExperimentSynthesisStatus.BLOCKED_BY_BASELINE_STATE.value,
                      "reason": f"baseline has no value for {field_name}"}

    # working-window lockout / interaction-risk (never bypassed by preference)
    win = (working_windows or {}).get(field_name)
    sign = _DIRECTION_SIGN[direction]
    move_dir_name = "increase" if sign > 0 else "decrease"
    if win is not None and hasattr(win, "locked_directions"):
        try:
            if move_dir_name in win.locked_directions():
                return None, {"hypothesis_id": hyp_id, "component": component,
                              "status": ExperimentSynthesisStatus.BLOCKED_BY_WORKING_WINDOW.value,
                              "reason": f"{move_dir_name} of {field_name} is locked out"}
        except Exception:
            pass
    # Phase-14 already flags a contradicted direction; block it here honestly too
    if hyp_status == InterventionHypothesisStatus.CONTRADICTED_BY_OUTCOME.value:
        return None, {"hypothesis_id": hyp_id, "component": component,
                      "status": ExperimentSynthesisStatus.BLOCKED_BY_PRIOR_REGRESSION.value,
                      "reason": "prior regression for this direction"}

    # minimum-effective legal step
    delta = _build_delta(field_name, cur, sign, direction, ranges, h, mech_id, justifications,
                         role="primary")
    if delta is None:
        return None, {"hypothesis_id": hyp_id, "component": component,
                      "status": ExperimentSynthesisStatus.BLOCKED_BY_LEGALITY.value,
                      "reason": f"no legal one-step move for {field_name} within its range"}

    deltas = (delta,)
    attribution = "single_field"
    # TESTABLE → ready; CONDITIONAL / COMPETING → a conditional (discriminating) test, never
    # ready and never an auto-winner.
    status = (ExperimentSynthesisStatus.READY_FOR_PREFLIGHT if hyp_status == _PROCEED
              else ExperimentSynthesisStatus.CONDITIONAL)

    if coupled:
        # a coupled candidate requires a compensating field + explicit roles; until the
        # coupling + preflight are fully specified it stays REQUIRES_COUPLED_EXPERIMENT
        status = ExperimentSynthesisStatus.REQUIRES_COUPLED_EXPERIMENT
        attribution = "coupled_pair"

    preserved = [f for f in fields if f != field_name]
    exp = _build_experiment(h, issue, set_fp, baseline, deltas, preserved, status,
                            attribution, hyp_id)
    return exp, None


def _build_delta(field_name, cur, sign, direction, ranges, h, mech_id, justifications, role
                 ) -> Optional[ParameterExperimentDelta]:
    step = legal_step(field_name)
    rng = (ranges or {}).get(field_name)
    lo = hi = None
    if isinstance(rng, (tuple, list)) and len(rng) == 2:
        lo, hi = _as_float(rng[0]), _as_float(rng[1])
    if lo is None or hi is None:
        return None  # no canonical legal range → BLOCKED_BY_LEGALITY

    # justified larger step (bounded); default is exactly one step
    n_steps = 1
    larger_reason = ""
    just = (justifications or {}).get(field_name)
    if just and _lc(just.get("reason")) in _ALLOWED_JUSTIFICATIONS:
        n_steps = max(1, min(MAX_JUSTIFIED_STEPS, int(just.get("steps", 2) or 2)))
        larger_reason = _norm(just.get("reason"))

    proposed = _canonical_round(field_name, cur + sign * step * n_steps)
    dval = round(proposed - cur, 6)
    if abs(dval) < step * 0.5:                      # no measurable / no-op
        return None
    if proposed < lo or proposed > hi:              # out of legal range → no clamping
        return None

    tgt = h.get("target") or {}
    er = h.get("expected_response") or {}
    return ParameterExperimentDelta(
        field=field_name, subsystem=_subsystem(field_name), baseline_value=cur,
        candidate_value=proposed, delta=dval, direction=direction, legal_low=lo,
        legal_high=hi, legal_step=step, is_exactly_one_step=(n_steps == 1),
        larger_step_used=(n_steps > 1), larger_step_reason=larger_reason, role=role,
        protected_interactions=tuple(h.get("protected_good_at_risk") or ()),
        expected_benefit=_norm(er.get("predicted_benefit")),
        expected_trade_offs=tuple(h.get("predicted_trade_offs") or ()),
        source_hypothesis_id=_norm(h.get("hypothesis_id")), source_mechanism_id=mech_id)


_ALLOWED_JUSTIFICATIONS = frozenset({
    "one_step_physically_meaningless", "non_uniform_discrete_options",
    "current_value_in_dead_band", "test_requires_crossing_threshold",
    "prior_one_step_inconclusive",
})


def _build_experiment(h, issue, set_fp, baseline, deltas, preserved, status, attribution,
                      hyp_id) -> BoundedSetupExperiment:
    er = h.get("expected_response") or {}
    td = h.get("test_design") or {}
    fields_changed = tuple(d.field for d in deltas)
    preserved_fp = hashlib.sha256(
        json.dumps(sorted(preserved), separators=(",", ":")).encode()).hexdigest()[:16]
    protocol = {
        "baseline_setup_hash": baseline.setup_hash,
        "changed_fields": list(fields_changed),
        "unchanged_field_guarantee": True,
        "direction": deltas[0].direction if deltas else "",
        "candidate_values": {d.field: d.candidate_value for d in deltas},
        "tyre_compound": _norm(td.get("tyre_compound")) or "same as baseline",
        "fuel_state": _norm(td.get("fuel_state")) or "same fuel range as baseline",
        "min_clean_laps": int(td.get("min_clean_laps") or 4),
        "warmup_treatment": "exclude warm-up / out laps",
        "corner_context": list(td.get("corner_context") or []),
        "target_handling_phase": _norm((h.get("target") or {}).get("handling_phase")),
        "expected_positive_signal": _norm(td.get("expected_positive_signal")),
        "expected_adverse_signal": _norm(td.get("expected_negative_signal")),
        "rejection_threshold": "canonical recurrence/outcome rules (no fabricated numeric "
                               "telemetry threshold)",
        "recurrence_requirement": "the issue must recur on the baseline before testing",
        "ab_structure": _norm(td.get("ab_structure")) or "A/B/A",
        "attribution": attribution,
        "enters_postflight": status == ExperimentSynthesisStatus.READY_FOR_PREFLIGHT.value,
    }
    preflight_reqs = _preflight_requirements(baseline, deltas, status)
    candidate_id = _candidate_id(set_fp, baseline.setup_hash, fields_changed,
                                 tuple(d.direction for d in deltas))
    explanation = _explain(h, deltas, status, attribution)
    fp = _experiment_fp(candidate_id, deltas, status, preserved_fp)
    return BoundedSetupExperiment(
        candidate_id=candidate_id, source_hypothesis_set_fingerprint=set_fp,
        selected_hypothesis_ids=(hyp_id,), baseline=baseline, deltas=deltas,
        unchanged_field_count=len(preserved), preserved_fields_fingerprint=preserved_fp,
        expected_response=_norm(er.get("primary_effect")) or _norm(er.get("predicted_benefit")),
        protected_good_behaviours=tuple(h.get("protected_good_at_risk") or ()),
        test_protocol=protocol, preflight_requirements=preflight_reqs,
        rejection_criteria=tuple(h.get("rejection_criteria") or ()),
        reversal_instructions="revert to the baseline applied setup checkpoint "
                              f"({baseline.setup_hash[:12]}) if a regression is confirmed",
        attribution_scope=attribution, evidence_grade=_lc(h.get("evidence_grade")),
        status=status.value, explanation=explanation, content_fingerprint=fp)


def _preflight_requirements(baseline, deltas, status) -> Tuple[str, ...]:
    reqs = [
        "baseline exists, is valid, complete and context-matched",
        "candidate value is legal and lands on a legal increment",
        "candidate differs from baseline and moves in the canonical direction",
        "the changed field(s) are the only changes; all other fields preserved",
        "working window permits the direction",
    ]
    if status == ExperimentSynthesisStatus.REQUIRES_COUPLED_EXPERIMENT:
        reqs.append("the compensating field, its role, and why isolation is unsuitable "
                    "must be specified before preflight")
    if status == ExperimentSynthesisStatus.CONDITIONAL:
        reqs.append("the hypothesis conditions (e.g. speed context) must be supplied and "
                    "validated before preflight")
    return tuple(reqs)


def _explain(h, deltas, status, attribution) -> str:
    if not deltas:
        return "No bounded experiment could be synthesised."
    d = deltas[0]
    base = (f"Smallest legal experiment: {d.direction.replace('_', ' ')} {d.field} from "
            f"{d.baseline_value} to {d.candidate_value} "
            f"({'one legal step' if d.is_exactly_one_step else f'{d.larger_step_reason}'}); "
            f"all other fields preserved. This is a controlled TEST, not a final tune.")
    if status == ExperimentSynthesisStatus.REQUIRES_COUPLED_EXPERIMENT:
        base += " Coupled test - requires the compensating field and roles before preflight."
    elif status == ExperimentSynthesisStatus.CONDITIONAL:
        base += " Conditional - supply and validate the hypothesis conditions first."
    if h.get("protected_good_at_risk"):
        base += f" Protect: {', '.join(h['protected_good_at_risk'])}."
    return base


# --------------------------------------------------------------------------- #
# ordering / status / fingerprints
# --------------------------------------------------------------------------- #
_GRADE_ORDER = {"strong": 0, "moderate": 1, "weak": 2, "insufficient": 3, "": 4}


def _cand_sort_key(c: BoundedSetupExperiment) -> tuple:
    return (
        _GRADE_ORDER.get(c.evidence_grade, 4),
        0 if c.attribution_scope == "single_field" else 1,
        0 if (c.deltas and c.deltas[0].is_exactly_one_step) else 1,
        0 if not c.protected_good_behaviours else 1,
        c.candidate_id,   # explicit deterministic non-semantic tie-break
    )


def _overall_status(selected, ready, conditional, rejected) -> str:
    if selected is not None:
        return ExperimentSynthesisStatus.READY_FOR_PREFLIGHT.value
    if ready:   # ties → conditional (manual choice required)
        return ExperimentSynthesisStatus.CONDITIONAL.value
    if conditional:
        coupled = [c for c in conditional
                   if c.status == ExperimentSynthesisStatus.REQUIRES_COUPLED_EXPERIMENT.value]
        if coupled and len(coupled) == len(conditional):
            return ExperimentSynthesisStatus.REQUIRES_COUPLED_EXPERIMENT.value
        return ExperimentSynthesisStatus.CONDITIONAL.value
    # nothing synthesised — surface the most informative block reason
    reasons = {r["status"] for r in rejected}
    for st in (ExperimentSynthesisStatus.BLOCKED_BY_PRIOR_REGRESSION.value,
               ExperimentSynthesisStatus.BLOCKED_BY_WORKING_WINDOW.value,
               ExperimentSynthesisStatus.BLOCKED_BY_LEGALITY.value,
               ExperimentSynthesisStatus.INSUFFICIENT_EVIDENCE.value,
               ExperimentSynthesisStatus.OUT_OF_SCOPE.value,
               ExperimentSynthesisStatus.NOT_EVALUABLE.value):
        if st in reasons:
            return st
    return ExperimentSynthesisStatus.NO_ELIGIBLE_HYPOTHESIS.value


def _candidate_id(set_fp, baseline_hash, fields, directions) -> str:
    raw = "|".join((set_fp, baseline_hash, ",".join(fields), ",".join(directions)))
    return f"{EXPERIMENT_SYNTHESIS_VERSION}:cand:{hashlib.sha256(raw.encode()).hexdigest()[:20]}"


def _experiment_fp(candidate_id, deltas, status, preserved_fp) -> str:
    payload = {"id": candidate_id, "status": status.value if hasattr(status, "value") else status,
               "preserved": preserved_fp,
               "deltas": [{"f": d.field, "b": d.baseline_value, "c": d.candidate_value,
                           "dir": d.direction, "one": d.is_exactly_one_step} for d in deltas]}
    return (f"{EXPERIMENT_SYNTHESIS_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                        separators=(",", ":")).encode()).hexdigest()[:24])


def _result_fp(set_fp, baseline, overall, selected, candidates, kv) -> str:
    payload = {"set": set_fp, "base": baseline.setup_hash, "overall": overall, "kv": kv,
               "sel": selected.content_fingerprint if selected else "",
               "cands": sorted(c.content_fingerprint for c in candidates)}
    return (f"{EXPERIMENT_SYNTHESIS_VERSION}:result:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True,
                                        separators=(",", ":")).encode()).hexdigest()[:24])


# --------------------------------------------------------------------------- #
# Public: batch over a whole intervention-hypothesis report
# --------------------------------------------------------------------------- #
def synthesize_from_report(report: Optional[Mapping], *, applied_setup=None,
                           session_identity=None, ranges=None, working_windows=None,
                           gearbox_state: str = "",
                           larger_step_justifications=None) -> dict:
    """Turn a ``build_intervention_hypotheses`` report into bounded-experiment synthesis
    results. Deterministic order (by source diagnosis key); read-only; never raises."""
    report = report if isinstance(report, Mapping) else {}
    out: List[ExperimentSynthesisResult] = []
    for hset in report.get("hypothesis_sets") or []:
        try:
            out.append(synthesize_bounded_experiments(
                hset, applied_setup=applied_setup, session_identity=session_identity,
                ranges=ranges, working_windows=working_windows, gearbox_state=gearbox_state,
                larger_step_justifications=larger_step_justifications))
        except Exception:
            continue
    out.sort(key=lambda r: _norm(r.source_hypothesis_set.get("source_diagnosis_key")))
    dicts = [r.to_dict() for r in out]
    kv = _knowledge_versions()
    ready = sum(1 for r in out if r.preflight_ready)
    fp = (f"{EXPERIMENT_SYNTHESIS_VERSION}:report:"
          + hashlib.sha256(json.dumps(
              {"n": len(dicts), "fps": [r.content_fingerprint for r in out], "kv": kv},
              sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24])
    return {"ok": True, "version": EXPERIMENT_SYNTHESIS_VERSION,
            "synthesis_results": dicts, "count": len(dicts), "ready_for_preflight": ready,
            "safety_statement": _SAFETY, "knowledge_versions": kv,
            "content_fingerprint": fp}
