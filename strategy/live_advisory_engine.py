"""Live Advisory Arbitration Engine (Program 2, Phase 44).

Decides, from a set of CANDIDATE prompts + an immutable runtime snapshot + a suppression state + an
INJECTED monotonic clock, which single prompt (if any) to deliver. It applies explicit safety-delivery
gates, priority arbitration/supersession, and deterministic suppression (semantic keys, cooldowns,
per-lap and per-session limits, expiry, stale-plan / stale-telemetry rejection).

Determinism: runtime elapsed time (``now_monotonic``) is used ONLY for cooldown behaviour and is passed
in - it never enters a semantic fingerprint. No wall-clock, no random. Delivers at most one prompt;
emits nothing when nothing is deliverable (no dashboard woodpecker).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.live_advisory import (
    LIVE_ADVISORY_VERSION, PromptClass, DeliveryWindow, AdvisoryPrompt, confidence_ok,
)

LIVE_ADVISORY_ENGINE_VERSION = "live_advisory_engine_v1"
LIVE_ADVISORY_ENGINE_SCHEMA = 1

_PER_LAP_LIMIT = 1
_PER_SESSION_LIMIT = 10
_HIGH_WORKLOAD_SEGMENTS = {"braking", "turn_in", "apex", "corner_entry", "corner"}


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{LIVE_ADVISORY_ENGINE_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


@dataclass(frozen=True)
class AdvisoryDecision:
    delivered: Optional[dict]
    suppressed: Tuple[dict, ...]
    active_objective: str
    state: dict
    content_fingerprint: str
    schema_version: int = LIVE_ADVISORY_ENGINE_SCHEMA
    eval_version: str = LIVE_ADVISORY_ENGINE_VERSION

    def to_dict(self) -> dict:
        return {"delivered": dict(self.delivered) if self.delivered else None,
                "suppressed": [dict(s) for s in self.suppressed],
                "active_objective": self.active_objective, "state": dict(self.state),
                "content_fingerprint": self.content_fingerprint,
                "schema_version": self.schema_version, "eval_version": self.eval_version}


def _as_prompt(p) -> AdvisoryPrompt:
    if isinstance(p, AdvisoryPrompt):
        return p
    d = p if isinstance(p, Mapping) else {}
    return AdvisoryPrompt(
        prompt_type=_norm(d.get("prompt_type")), priority=int(d.get("priority") or 99),
        source_authority=_norm(d.get("source_authority")),
        context_fingerprint=_norm(d.get("context_fingerprint")),
        run_plan_fingerprint=_norm(d.get("run_plan_fingerprint")),
        target_segment=_norm(d.get("target_segment")), delivery_window=_norm(d.get("delivery_window")),
        message=_norm(d.get("message")), rationale=_norm(d.get("rationale")),
        confidence=_norm(d.get("confidence")), evidence_freshness=_norm(d.get("evidence_freshness")),
        expiry_lap=int(d.get("expiry_lap") if d.get("expiry_lap") is not None else -1),
        cooldown_seconds=float(d.get("cooldown_seconds") or 0.0),
        suppression_key=_norm(d.get("suppression_key")), ack_required=bool(d.get("ack_required")),
        prompt_class=_norm(d.get("prompt_class")))


def _staleness_gate(p: AdvisoryPrompt, snap: Mapping) -> str:
    """Hard gates that suppress ANY prompt regardless of class. Returns a reason or ''."""
    if not snap.get("telemetry_fresh", True):
        return "telemetry is stale"
    if _norm(snap.get("context_fingerprint")) and p.context_fingerprint \
            and _norm(snap.get("context_fingerprint")) != p.context_fingerprint:
        return "context changed since the prompt was generated"
    if snap.get("plan_current") is False:
        return "the run plan is no longer current"
    if p.run_plan_fingerprint and _norm(snap.get("run_plan_fingerprint")) \
            and p.run_plan_fingerprint != _norm(snap.get("run_plan_fingerprint")):
        return "the run-plan fingerprint changed"
    lap = int(snap.get("lap") or 0)
    if p.expiry_lap >= 0 and lap > p.expiry_lap:
        return f"expired (lap {lap} > expiry {p.expiry_lap})"
    if p.target_segment and _lc(p.target_segment) in {_lc(c) for c in (snap.get("passed_corners") or [])}:
        return "the target corner was already passed"
    if _lc(snap.get(f"conflict:{p.suppression_key}")) in ("1", "true", "yes") \
            or p.suppression_key in {_norm(k) for k in (snap.get("plan_conflicts") or [])}:
        return "the advice conflicts with the current run plan"
    return ""


def _window_gate(p: AdvisoryPrompt, snap: Mapping) -> str:
    """Safe-delivery-window gate (skipped for stop-critical). Returns a reason or ''."""
    if p.prompt_class == PromptClass.STOP_CRITICAL.value:
        return ""   # a safety stop may be delivered at any non-stale moment
    if not confidence_ok(p.priority, p.confidence):
        return f"confidence '{p.confidence}' below the minimum for this prompt type"
    workload = _lc(snap.get("workload"))
    segment = _lc(snap.get("segment_type"))
    high_workload = workload == "high" or segment in _HIGH_WORKLOAD_SEGMENTS
    if high_workload:
        return "driver is in a high-workload segment - delayed to a safe window"
    win = p.delivery_window
    if win == DeliveryWindow.STRAIGHT.value and segment != "straight":
        return "not on a straight"
    if win == DeliveryWindow.PIT_LANE.value and not snap.get("in_pit"):
        return "not in the pit lane"
    if win == DeliveryWindow.AFTER_FINISH_LINE.value and not snap.get("at_finish_line"):
        return "not at the finish line yet"
    if win == DeliveryWindow.AFTER_SESSION.value and snap.get("session_active", True):
        return "session still active"
    if win == DeliveryWindow.BEFORE_MEASUREMENT.value and not (snap.get("before_measurement")
                                                              or segment == "straight"):
        return "not before a measurement lap"
    if win == DeliveryWindow.LOW_WORKLOAD.value and workload not in ("low", ""):
        return "not a low-workload window"
    return ""


def _session_gate(snap: Mapping) -> str:
    # a prompt whose window is not after_session cannot deliver once the session ends.
    return ""  # handled per-window (after_session) above


def evaluate_live_advisories(candidates: Optional[Sequence], snapshot: Optional[Mapping], *,
                             now_monotonic: float, state: Optional[Mapping] = None
                             ) -> AdvisoryDecision:
    """Arbitrate candidates into at most one delivered prompt. ``now_monotonic`` is the injected test/
    runtime clock (seconds); it drives cooldown only and never enters the fingerprint. Deterministic;
    never raises."""
    try:
        snap = snapshot if isinstance(snapshot, Mapping) else {}
        cands = [_as_prompt(c) for c in (candidates or [])]
        st = {"last_delivered": dict((state or {}).get("last_delivered") or {}),
              "lap_counts": {str(k): int(v) for k, v in ((state or {}).get("lap_counts") or {}).items()},
              "session_counts": {str(k): int(v) for k, v in
                                 ((state or {}).get("session_counts") or {}).items()}}
        lap = int(snap.get("lap") or 0)
        suppressed: List[dict] = []

        # stage 1: hard staleness + window gates
        eligible: List[AdvisoryPrompt] = []
        for p in cands:
            reason = _staleness_gate(p, snap) or _window_gate(p, snap)
            if reason:
                suppressed.append({"suppression_key": p.suppression_key, "priority": p.priority,
                                   "reason": reason})
            else:
                eligible.append(p)

        # stage 2: priority arbitration (supersession) - only the top-priority survivor may deliver.
        eligible.sort(key=lambda x: (x.priority, x.suppression_key))
        chosen = None
        for i, p in enumerate(eligible):
            if i == 0:
                chosen = p
            else:
                suppressed.append({"suppression_key": p.suppression_key, "priority": p.priority,
                                   "reason": f"superseded by higher-priority '{eligible[0].suppression_key}'"})

        delivered = None
        if chosen is not None:
            key = chosen.suppression_key
            last = st["last_delivered"].get(key)
            lap_key = f"{key}@{lap}"
            lap_n = st["lap_counts"].get(lap_key, 0)
            sess_n = st["session_counts"].get(key, 0)
            if last is not None and (float(now_monotonic) - float(last)) < chosen.cooldown_seconds:
                suppressed.append({"suppression_key": key, "priority": chosen.priority,
                                   "reason": "within cooldown"})
            elif lap_n >= _PER_LAP_LIMIT and not snap.get("repetition_permitted"):
                suppressed.append({"suppression_key": key, "priority": chosen.priority,
                                   "reason": "per-lap repetition limit reached"})
            elif sess_n >= _PER_SESSION_LIMIT:
                suppressed.append({"suppression_key": key, "priority": chosen.priority,
                                   "reason": "per-session repetition limit reached"})
            else:
                delivered = chosen.to_dict()
                st["last_delivered"][key] = float(now_monotonic)
                st["lap_counts"][lap_key] = lap_n + 1
                st["session_counts"][key] = sess_n + 1

        active_objective = ""
        for p in cands:
            if p.priority == 5:  # target-corner coaching = the active objective
                active_objective = p.message
                break

        suppressed.sort(key=lambda d: (d["priority"], d["suppression_key"], d["reason"]))
        fp = _fp({"delivered": (_as_prompt(delivered).semantic_fingerprint() if delivered else ""),
                  "suppressed": [(s["suppression_key"], s["reason"]) for s in suppressed],
                  "objective": active_objective})
        return AdvisoryDecision(delivered=delivered, suppressed=tuple(suppressed),
                                active_objective=active_objective, state=st, content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return AdvisoryDecision(delivered=None, suppressed=(), active_objective="",
                                state=dict(state or {}), content_fingerprint=_fp({"e": 1}))


def engine_versions() -> dict:
    return {"live_advisory_engine": LIVE_ADVISORY_ENGINE_VERSION,
            "live_advisory": LIVE_ADVISORY_VERSION, "schema": LIVE_ADVISORY_ENGINE_SCHEMA}
