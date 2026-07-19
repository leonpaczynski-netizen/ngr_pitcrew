"""Pre-flight checklist validation (Engineering Brain Phase 11).

Evaluates every Phase-10 checklist item against what actually occurred (the Phase-3
outcome + Phase-6 residual state): did the expected risk appear, did the protected
behaviour remain protected, did the interaction occur, did the regression happen, was
the confidence appropriate? Each validation says whether the check MATERIALISED and
whether it was USEFUL (correctly anticipated reality).

READ-ONLY: compares deterministic objects; changes nothing.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises; no random,
no wall-clock; deterministic.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Sequence, Tuple

PREFLIGHT_VALIDATION_VERSION = "preflight_validation_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


class ItemOutcome(str, Enum):
    MATERIALISED = "materialised"               # the thing the item flagged happened
    DID_NOT_MATERIALISE = "did_not_materialise"  # it did not happen
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True)
class ChecklistValidation:
    label: str
    status: str                         # original checklist status (ok/caution/unknown)
    expectation: str                    # what the item asserted/warned
    outcome: str                        # ItemOutcome value
    useful: bool                        # did the check correctly anticipate reality?
    reason: str
    eval_version: str = PREFLIGHT_VALIDATION_VERSION

    def to_dict(self) -> dict:
        return {"label": self.label, "status": self.status,
                "expectation": self.expectation, "outcome": self.outcome,
                "useful": self.useful, "reason": self.reason,
                "eval_version": self.eval_version}


def _observed(outcome: Mapping, residuals: Sequence[Mapping]) -> dict:
    status = _lc(outcome.get("status"))
    regressed = status == "regression" or any(
        r.get("is_new") or r.get("is_regression")
        or _lc(r.get("residual_state")) in ("new", "worsened", "good_behaviour_damaged")
        for r in residuals or ())
    improved = status in ("confirmed_improvement", "partial_improvement")
    insufficient = status in ("insufficient_evidence", "confounded", "")
    protected_damaged = any(
        _lc(p.get("verdict")) in ("material_regression", "minor_regression")
        for p in outcome.get("protected") or ())
    unresolved = {(_lc(r.get("issue_type"))) for r in residuals or ()
                  if _lc(r.get("residual_state")) in
                  ("unchanged", "worsened", "new", "improved_but_present")}
    return {"status": status, "regressed": regressed, "improved": improved,
            "insufficient": insufficient, "protected_damaged": protected_damaged,
            "unresolved": unresolved}


def validate_checklist(
    preflight: Mapping, outcome: Mapping, residuals: Sequence[Mapping],
) -> Tuple[ChecklistValidation, ...]:
    """Evaluate every checklist item against the observed reality. Deterministic;
    never mutates inputs."""
    review = (preflight or {}).get("review") or preflight or {}
    items = review.get("checklist") or []
    obs = _observed(outcome or {}, residuals or [])
    out: List[ChecklistValidation] = []

    def _add(item, expectation, outcome_val, useful, reason):
        out.append(ChecklistValidation(
            label=_norm(item.get("label")), status=_norm(item.get("status")),
            expectation=expectation, outcome=outcome_val.value, useful=bool(useful),
            reason=reason))

    for it in items:
        label = _lc(it.get("label"))
        status = _lc(it.get("status"))

        if obs["insufficient"] and "residual" not in label:
            _add(it, "outcome measurable", ItemOutcome.INSUFFICIENT_EVIDENCE, False,
                 "the outcome was inconclusive")
            continue

        # protected behaviour
        if "protected" in label:
            if status == "ok":            # asserted NO conflict
                mat = ItemOutcome.DID_NOT_MATERIALISE if not obs["protected_damaged"] \
                    else ItemOutcome.MATERIALISED
                useful = not obs["protected_damaged"]
                _add(it, "protected behaviour stays protected", mat, useful,
                     "protected behaviour preserved" if useful
                     else "a protected behaviour was damaged despite the check")
            else:                         # warned of a conflict
                mat = ItemOutcome.MATERIALISED if obs["protected_damaged"] \
                    else ItemOutcome.DID_NOT_MATERIALISE
                _add(it, "protected behaviour may be damaged", mat,
                     obs["protected_damaged"],
                     "the protected behaviour was damaged as warned" if obs["protected_damaged"]
                     else "the protected behaviour held (cautious warning)")

        # window
        elif "window" in label:
            if "inside" in label:         # asserted inside/valid
                mat = ItemOutcome.DID_NOT_MATERIALISE if not obs["regressed"] \
                    else ItemOutcome.MATERIALISED
                _add(it, "value stays inside the working window", mat, not obs["regressed"],
                     "no window violation" if not obs["regressed"]
                     else "a regression occurred despite the window check")
            else:                         # warned of edge
                mat = ItemOutcome.MATERIALISED if obs["regressed"] \
                    else ItemOutcome.DID_NOT_MATERIALISE
                _add(it, "value at window edge may regress", mat, obs["regressed"],
                     "a regression occurred as warned" if obs["regressed"]
                     else "no regression (cautious edge warning)")

        # similar experiment succeeded / failed
        elif "succeeded" in label:
            mat = ItemOutcome.MATERIALISED if obs["improved"] else ItemOutcome.DID_NOT_MATERIALISE
            _add(it, "a similar change improves the issue", mat, obs["improved"],
                 "it improved as history suggested" if obs["improved"]
                 else "it did not improve this time")
        elif "failed before" in label:
            mat = ItemOutcome.MATERIALISED if obs["regressed"] else ItemOutcome.DID_NOT_MATERIALISE
            _add(it, "a similar change may regress again", mat, obs["regressed"],
                 "it regressed as warned" if obs["regressed"]
                 else "it did not regress this time (cautious warning)")

        # regression-type risks
        elif "failed direction" in label or "regression" in label or "unstable" in label:
            mat = ItemOutcome.MATERIALISED if obs["regressed"] else ItemOutcome.DID_NOT_MATERIALISE
            _add(it, "the warned regression may occur", mat, obs["regressed"],
                 "the regression occurred as warned" if obs["regressed"]
                 else "the regression did not occur (cautious warning)")

        # coupled interaction
        elif "coupled" in label or "interaction" in label:
            mat = ItemOutcome.MATERIALISED if obs["regressed"] else ItemOutcome.DID_NOT_MATERIALISE
            _add(it, "a coupled interaction may show", mat, True,
                 "a coupled effect was observed" if obs["regressed"]
                 else "no coupled effect was observed")

        # confidence weakness / one supporting session
        elif "supporting session" in label or "confidence" in label:
            appropriate = obs["improved"]  # low-confidence caution vindicated if it still worked
            _add(it, "confidence was appropriately flagged",
                 ItemOutcome.MATERIALISED if not obs["improved"] else ItemOutcome.DID_NOT_MATERIALISE,
                 True,
                 "low confidence but it worked (conservative flag)" if obs["improved"]
                 else "low confidence and it did not improve (flag warranted)")

        # outstanding residual still unresolved
        elif "unresolved" in label:
            issue = label.split(" still unresolved")[0]
            still = any(issue and issue in u for u in obs["unresolved"])
            mat = ItemOutcome.MATERIALISED if still else ItemOutcome.DID_NOT_MATERIALISE
            _add(it, "the residual issue remains", mat, still,
                 "the residual remains unresolved" if still
                 else "the residual is no longer present")

        else:
            _add(it, _norm(it.get("why")), ItemOutcome.NOT_APPLICABLE, True,
                 "not directly observable")

    return tuple(out)
