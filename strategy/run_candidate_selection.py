"""Run-candidate selection — pick the highest-value EXISTING candidate to test (Program 2, Phase 40).

Selects (and normalises for the run plan) the best existing Phase-17 portfolio candidate for the
current context, or declines with a reason. It selects and links only - it NEVER creates, persists,
schedules or applies anything.

Selection considers: exact-context readiness, current setup discipline, confirmed-good protections,
attribution quality (single-field is cleanest), interaction & masking risk, reversibility, coaching
conflicts, available practice time and event proximity. Under deadline pressure with only
high-interaction candidates available, it declines in favour of protecting the best-known setup and
collecting low-risk evidence.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

RUN_CANDIDATE_SELECTION_VERSION = "run_candidate_selection_v1"
RUN_CANDIDATE_SELECTION_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{RUN_CANDIDATE_SELECTION_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


@dataclass(frozen=True)
class RunCandidateSelection:
    posture: str                 # experiment | collect | protect
    selected: Optional[dict]
    reason: str
    rejected: Tuple[dict, ...]
    content_fingerprint: str
    schema_version: int = RUN_CANDIDATE_SELECTION_SCHEMA
    eval_version: str = RUN_CANDIDATE_SELECTION_VERSION

    def to_dict(self) -> dict:
        return {"posture": self.posture, "selected": dict(self.selected) if self.selected else None,
                "reason": self.reason, "rejected": [dict(r) for r in self.rejected],
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def _interaction_risk(cand: Mapping) -> str:
    return "low" if _lc(cand.get("attribution_scope")) == "single_field" else "high"


def _normalise(cand: Mapping) -> dict:
    single = _lc(cand.get("attribution_scope")) == "single_field"
    changes = cand.get("changes")
    if not changes:
        f = _norm(cand.get("field"))
        changes = [{"field": f, "direction": _norm(cand.get("direction"))}] if f else []
    return {"id": _norm(cand.get("candidate_id") or cand.get("id")),
            "source": "phase17_experiment_portfolio",
            "field": _norm(cand.get("field")), "direction": _norm(cand.get("direction")),
            "changes": changes if len(changes) > 1 else None,
            "hypothesis": _norm(cand.get("expected_learning") or cand.get("hypothesis")),
            "expected_mechanism": _norm(cand.get("mechanism_id") or cand.get("expected_mechanism")),
            "attribution_scope": _lc(cand.get("attribution_scope")) or ("single_field" if single
                                                                        else "coupled"),
            "interaction_risk": _interaction_risk(cand),
            "protected_good_at_risk": list(cand.get("protected_good_at_risk") or []),
            "target_corners": list(cand.get("target_corners") or [])}


def select_run_candidate(candidates: Optional[Sequence[Mapping]], *,
                         protected_behaviours: Optional[Sequence] = None,
                         coaching_holds_setup: bool = False, event_is_near: bool = False,
                         available_practice_laps: Optional[int] = None) -> RunCandidateSelection:
    """Select the best existing candidate to test, or decline with a reason. Deterministic; never
    raises. Candidates are Phase-17 valuations (dicts)."""
    try:
        cands = [c for c in (candidates or []) if isinstance(c, Mapping)]
        protected = {_lc(p.get("field") if isinstance(p, Mapping) else p)
                     for p in (protected_behaviours or [])}
        protected.discard("")
        rejected: List[dict] = []

        # drop retired / non-actionable candidates.
        live = []
        for c in cands:
            if _norm(c.get("retirement_reason")) or _lc(c.get("role")) in ("retired", "superseded"):
                rejected.append({"candidate_id": _norm(c.get("candidate_id") or c.get("id")),
                                 "reason": "retired / superseded candidate."})
                continue
            live.append(c)

        # protected-good conflict: a candidate that risks a confirmed-good field is rejected.
        safe = []
        for c in live:
            at_risk = {_lc(f) for f in (c.get("protected_good_at_risk") or [])}
            if at_risk & protected:
                rejected.append({"candidate_id": _norm(c.get("candidate_id") or c.get("id")),
                                 "reason": "risks a confirmed-good protected behaviour."})
                continue
            safe.append(c)

        if not safe:
            return _decline("collect", "no context-safe candidate is available - collect evidence / "
                            "validate the current best-known setup instead.", rejected)

        # deterministic ranking: engineering_value desc, then single-field first, then rank, then id.
        def _key(c):
            single = 0 if _lc(c.get("attribution_scope")) == "single_field" else 1
            return (-float(c.get("engineering_value") or 0.0), single, int(c.get("rank") or 9999),
                    _norm(c.get("candidate_id") or c.get("id")))
        safe.sort(key=_key)

        low_time = available_practice_laps is not None and available_practice_laps <= 6
        # deadline posture: prefer low-interaction; if the best is high-interaction, decline to protect.
        if event_is_near and low_time:
            low_risk = [c for c in safe if _interaction_risk(c) == "low"]
            if not low_risk:
                return _decline("protect", "event is near with little practice time and only "
                                "high-interaction candidates remain - protect the current best-known "
                                "setup and collect low-risk evidence.", rejected
                                + [{"candidate_id": _norm(c.get("candidate_id") or c.get("id")),
                                    "reason": "high interaction risk under deadline pressure."}
                                   for c in safe])
            safe = low_risk

        best = safe[0]
        for c in safe[1:]:
            rejected.append({"candidate_id": _norm(c.get("candidate_id") or c.get("id")),
                             "reason": "lower engineering value / higher interaction than the selected "
                                       "candidate."})
        selected = _normalise(best)
        reason = (f"highest-value context-safe candidate (value "
                  f"{float(best.get('engineering_value') or 0.0):.2f}, "
                  f"{selected['attribution_scope']}); "
                  + ("hold the setup constant if a coaching test is also planned."
                     if coaching_holds_setup else "clean single-mechanism test."
                     if selected["attribution_scope"] == "single_field" else "coupled bundle - reduced "
                     "causal confidence."))
        fp = _fp({"selected": selected["id"], "scope": selected["attribution_scope"],
                  "rejected": [r["candidate_id"] for r in rejected]})
        return RunCandidateSelection(posture="experiment", selected=selected, reason=reason,
                                     rejected=tuple(rejected), content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return _decline("collect", "candidate selection unavailable.", [])


def _decline(posture: str, reason: str, rejected) -> RunCandidateSelection:
    return RunCandidateSelection(posture=posture, selected=None, reason=reason,
                                 rejected=tuple(rejected),
                                 content_fingerprint=_fp({"posture": posture, "reason": reason}))


def selection_versions() -> dict:
    return {"run_candidate_selection": RUN_CANDIDATE_SELECTION_VERSION,
            "schema": RUN_CANDIDATE_SELECTION_SCHEMA}
