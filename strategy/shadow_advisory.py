"""Shadow-Mode Advisory Validation (Program 2, Phase 46).

Runs the Phase-44 advisory engine over a deterministic telemetry replay EXACTLY as live mode would -
evaluating, prioritising, suppressing and timing prompts - but WITHOUT speaking or distracting the
driver, and without any DB write. It maintains a session-scoped in-memory ledger (operational runtime
state, never engineering knowledge) and produces a live-validation readiness result gating voice.

Shadow mode and voice-eligible mode select the SAME advisory (they call the same engine); shadow simply
does not deliver by voice.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no WALL-CLOCK (replay time is
injected); deterministic; never raises. Writes nothing.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

SHADOW_ADVISORY_VERSION = "shadow_advisory_v1"

_HIGH_WORKLOAD = {"braking", "turn_in", "apex", "corner_entry", "corner"}
# nominal available speaking window (seconds) by segment, for the message-duration budget.
_WINDOW_SECONDS = {"pit": 10.0, "straight": 4.0}


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return f"{SHADOW_ADVISORY_VERSION}:" + hashlib.sha256(_dumps(payload).encode()).hexdigest()[:24]


class LiveValidationReadiness(str, Enum):
    NOT_READY = "not_ready"
    REPLAY_VALIDATED = "replay_validated"
    SHADOW_READY = "shadow_ready"
    LIVE_SHADOW_VALIDATED = "live_shadow_validated"
    VOICE_ELIGIBLE_WITH_LIMITATIONS = "voice_eligible_with_limitations"
    VOICE_ELIGIBLE = "voice_eligible"


@dataclass(frozen=True)
class ShadowDeliveryRecord:
    cycle_index: int
    monotonic: float
    segment: str
    prompt_type: str
    priority: int
    suppression_key: str
    delivery_window: str
    prompt_class: str
    estimated_seconds: float
    fits_window: bool
    would_voice: bool
    reason: str

    def to_dict(self) -> dict:
        return {"cycle_index": self.cycle_index, "monotonic": self.monotonic, "segment": self.segment,
                "prompt_type": self.prompt_type, "priority": self.priority,
                "suppression_key": self.suppression_key, "delivery_window": self.delivery_window,
                "prompt_class": self.prompt_class, "estimated_seconds": self.estimated_seconds,
                "fits_window": self.fits_window, "would_voice": self.would_voice, "reason": self.reason}


@dataclass(frozen=True)
class LiveRunValidationSummary:
    readiness: str
    delivered_count: int
    shadow_delivered_count: int
    suppressed_count: int
    high_workload_deliveries: int
    stale_deliveries: int
    voice_eligible_count: int
    records: Tuple[dict, ...]
    suppression_reasons: dict
    content_fingerprint: str
    eval_version: str = SHADOW_ADVISORY_VERSION

    def to_dict(self) -> dict:
        return {"readiness": self.readiness, "delivered_count": self.delivered_count,
                "shadow_delivered_count": self.shadow_delivered_count,
                "suppressed_count": self.suppressed_count,
                "high_workload_deliveries": self.high_workload_deliveries,
                "stale_deliveries": self.stale_deliveries,
                "voice_eligible_count": self.voice_eligible_count,
                "records": [dict(r) for r in self.records],
                "suppression_reasons": dict(self.suppression_reasons),
                "content_fingerprint": self.content_fingerprint, "eval_version": self.eval_version}


def _available_seconds(segment: str) -> float:
    return _WINDOW_SECONDS.get(_lc(segment), 2.0)


def run_shadow_replay(replay_result: Optional[Mapping], *, context_fingerprint: str = "",
                      run_plan: Optional[Mapping] = None, coaching_plan: Optional[Mapping] = None,
                      workflow: Optional[Mapping] = None, live_shadow_confirmed: bool = False
                      ) -> LiveRunValidationSummary:
    """Replay the advisory engine in shadow mode over ``replay_result.cycles``. Deterministic; speaks
    nothing; writes nothing. ``live_shadow_confirmed`` is set only after a real live-GT7 shadow run
    (never in replay), and is required for the voice-eligible gate. Never raises."""
    try:
        from strategy.runtime_snapshot import build_runtime_snapshot
        from strategy.live_advisory import build_candidate_prompts
        from strategy.live_advisory_engine import evaluate_live_advisories
        from strategy.prompt_timing import assess_prompt_timing
    except Exception:  # pragma: no cover - defensive
        return _empty()
    try:
        rr = replay_result if isinstance(replay_result, Mapping) else {}
        rp = run_plan if isinstance(run_plan, Mapping) else {}
        cp = coaching_plan if isinstance(coaching_plan, Mapping) else {}
        wf = workflow if isinstance(workflow, Mapping) else {}
        cycles = rr.get("cycles") or []

        ledger: dict = {}
        records: List[ShadowDeliveryRecord] = []
        suppression_reasons: Dict[str, int] = {}
        delivered = shadow_delivered = suppressed = high_wl = stale_del = voice_ok = 0

        for cyc in cycles:
            frame = cyc.get("frame") or {}
            mono = float(cyc.get("monotonic") or 0.0)
            snap = build_runtime_snapshot(context_fingerprint=context_fingerprint, run_plan=rp,
                                          workflow=wf, telemetry=frame)
            candidates = build_candidate_prompts(snap, rp, wf, cp)
            decision = evaluate_live_advisories(candidates, snap, now_monotonic=mono, state=ledger)
            ledger = decision.state
            for s in (decision.suppressed or []):
                suppressed += 1
                suppression_reasons[s.get("reason", "?")] = \
                    suppression_reasons.get(s.get("reason", "?"), 0) + 1
            dv = decision.delivered
            if not dv:
                continue
            shadow_delivered += 1
            seg = _lc(frame.get("segment_type"))
            timing = assess_prompt_timing(dv, _available_seconds(seg))
            is_high = seg in _HIGH_WORKLOAD or _lc(frame.get("workload")) == "high"
            is_stale = not frame.get("telemetry_fresh", True)
            would_voice = bool(timing.fits) and not is_stale
            if is_high and dv.get("prompt_class") != "stop_critical":
                high_wl += 1   # (should not happen - the engine gates these; recorded for audit)
            if is_stale:
                stale_del += 1
            if would_voice:
                voice_ok += 1
                delivered += 1
            records.append(ShadowDeliveryRecord(
                cycle_index=int(cyc.get("index") or 0), monotonic=mono, segment=seg,
                prompt_type=_norm(dv.get("prompt_type")), priority=int(dv.get("priority") or 0),
                suppression_key=_norm(dv.get("suppression_key")),
                delivery_window=_norm(dv.get("delivery_window")),
                prompt_class=_norm(dv.get("prompt_class")), estimated_seconds=timing.estimated_seconds,
                fits_window=bool(timing.fits), would_voice=would_voice, reason=timing.reason))

        # readiness: coherent shadow decisions => SHADOW_READY; voice needs a real live-shadow run.
        coherent = high_wl == 0 and stale_del == 0
        if not cycles:
            readiness = LiveValidationReadiness.NOT_READY
        elif not coherent:
            readiness = LiveValidationReadiness.REPLAY_VALIDATED
        elif live_shadow_confirmed:
            readiness = LiveValidationReadiness.VOICE_ELIGIBLE
        else:
            readiness = LiveValidationReadiness.SHADOW_READY

        fp = _fp({"ctx": _norm(context_fingerprint), "plan": _norm(rp.get("content_fingerprint")),
                  "records": [(r.cycle_index, r.suppression_key, r.would_voice) for r in records],
                  "readiness": readiness.value})
        return LiveRunValidationSummary(
            readiness=readiness.value, delivered_count=delivered,
            shadow_delivered_count=shadow_delivered, suppressed_count=suppressed,
            high_workload_deliveries=high_wl, stale_deliveries=stale_del, voice_eligible_count=voice_ok,
            records=tuple(r.to_dict() for r in records), suppression_reasons=suppression_reasons,
            content_fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return _empty()


def _empty() -> LiveRunValidationSummary:
    return LiveRunValidationSummary(readiness=LiveValidationReadiness.NOT_READY.value,
                                    delivered_count=0, shadow_delivered_count=0, suppressed_count=0,
                                    high_workload_deliveries=0, stale_deliveries=0,
                                    voice_eligible_count=0, records=(), suppression_reasons={},
                                    content_fingerprint=_fp({"e": 1}))


def voice_gate_allows(readiness: str) -> bool:
    """Voice may only be attempted at VOICE_ELIGIBLE / VOICE_ELIGIBLE_WITH_LIMITATIONS. Everything else
    keeps voice unavailable (shadow only)."""
    return _lc(readiness) in (LiveValidationReadiness.VOICE_ELIGIBLE.value,
                              LiveValidationReadiness.VOICE_ELIGIBLE_WITH_LIMITATIONS.value)


def shadow_versions() -> dict:
    return {"shadow_advisory": SHADOW_ADVISORY_VERSION}
