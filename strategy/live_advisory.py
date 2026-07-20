"""Live Advisory Prompt Model & Candidate Builders (Program 2, Phase 44).

Deterministic, offline, text-only live race-engineer advisories. This module defines the advisory
prompt object, the explicit visible priority model, and pure builders that turn an immutable runtime
snapshot into CANDIDATE prompts. Whether a candidate is actually delivered is decided by the arbitration
engine (``live_advisory_engine``) under safety gates + suppression.

Voice output is deferred. No automatic pit calls, fuel targets, tyre-change commands or strategy
commands are produced - strategy prompts are read-only awareness only.

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no WALL-CLOCK (runtime timing is
supplied via an injected monotonic clock to the engine, never read here); deterministic; never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Mapping, Optional, Tuple

LIVE_ADVISORY_VERSION = "live_advisory_v1"
LIVE_ADVISORY_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return f"{LIVE_ADVISORY_VERSION}:" + hashlib.sha256(_dumps(payload).encode()).hexdigest()[:24]


class PromptPriority(int, Enum):
    SAFETY_OR_INVALID_STOP = 1
    CONTEXT_SETUP_MISMATCH = 2
    RUN_PLAN_STOP_CONDITION = 3
    MEASUREMENT_LAP_INSTRUCTION = 4
    TARGET_CORNER_COACHING = 5
    EVIDENCE_COLLECTION = 6
    INFORMATIONAL_PROGRESS = 7
    STRATEGY_AWARENESS = 8


class PromptClass(str, Enum):
    INFORMATIONAL = "informational"
    CAUTIONARY = "cautionary"
    STOP_CRITICAL = "stop_critical"


class DeliveryWindow(str, Enum):
    IMMEDIATE = "immediate"                 # stop-critical: any safe-enough moment
    STRAIGHT = "straight"
    PIT_LANE = "pit_lane"
    BEFORE_MEASUREMENT = "before_measurement_lap"
    AFTER_FINISH_LINE = "after_finish_line"
    AFTER_SESSION = "after_session"
    LOW_WORKLOAD = "low_workload"


class EvidenceFreshness(str, Enum):
    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"


@dataclass(frozen=True)
class AdvisoryPrompt:
    prompt_type: str
    priority: int
    source_authority: str
    context_fingerprint: str
    run_plan_fingerprint: str
    target_segment: str
    delivery_window: str
    message: str
    rationale: str
    confidence: str
    evidence_freshness: str
    expiry_lap: int                 # lap after which the prompt is stale (-1 = no lap expiry)
    cooldown_seconds: float         # min monotonic seconds between deliveries of this suppression key
    suppression_key: str
    ack_required: bool
    prompt_class: str

    def to_dict(self) -> dict:
        return {"prompt_type": self.prompt_type, "priority": self.priority,
                "source_authority": self.source_authority,
                "context_fingerprint": self.context_fingerprint,
                "run_plan_fingerprint": self.run_plan_fingerprint, "target_segment": self.target_segment,
                "delivery_window": self.delivery_window, "message": self.message,
                "rationale": self.rationale, "confidence": self.confidence,
                "evidence_freshness": self.evidence_freshness, "expiry_lap": self.expiry_lap,
                "cooldown_seconds": self.cooldown_seconds, "suppression_key": self.suppression_key,
                "ack_required": self.ack_required, "prompt_class": self.prompt_class}

    def semantic_fingerprint(self) -> str:
        # excludes cooldown/expiry runtime timing; includes semantic identity + priority + window.
        return _fp({"type": self.prompt_type, "prio": self.priority, "seg": self.target_segment,
                    "win": self.delivery_window, "key": self.suppression_key,
                    "ctx": self.context_fingerprint, "plan": self.run_plan_fingerprint})


# confidence rank + per-prompt-type minimum confidence to be eligible.
_CONF_RANK = {"": 0, "low": 1, "medium": 2, "high": 3, "very_high": 4}
_MIN_CONF = {PromptPriority.TARGET_CORNER_COACHING.value: "medium",
             PromptPriority.EVIDENCE_COLLECTION.value: "low",
             PromptPriority.STRATEGY_AWARENESS.value: "low"}


def min_confidence_for(priority: int) -> str:
    return _MIN_CONF.get(priority, "")


def confidence_ok(priority: int, confidence: str) -> bool:
    return _CONF_RANK.get(_lc(confidence), 0) >= _CONF_RANK.get(_MIN_CONF.get(priority, ""), 0)


def _p(prompt_type, priority, window, message, rationale, *, source="run_plan", confidence="high",
       freshness="fresh", target="", expiry_lap=-1, cooldown=30.0, key="", ack=False,
       cls=PromptClass.INFORMATIONAL, ctx_fp="", plan_fp="") -> AdvisoryPrompt:
    return AdvisoryPrompt(
        prompt_type=prompt_type, priority=int(priority), source_authority=source,
        context_fingerprint=ctx_fp, run_plan_fingerprint=plan_fp, target_segment=target,
        delivery_window=window, message=message, rationale=rationale, confidence=confidence,
        evidence_freshness=freshness, expiry_lap=int(expiry_lap), cooldown_seconds=float(cooldown),
        suppression_key=key or prompt_type, ack_required=bool(ack), prompt_class=cls.value)


def build_candidate_prompts(snapshot: Optional[Mapping], run_plan: Optional[Mapping] = None,
                            workflow: Optional[Mapping] = None, coaching_plan: Optional[Mapping] = None,
                            closed_loop: Optional[Mapping] = None) -> List[AdvisoryPrompt]:
    """Build the applicable CANDIDATE prompts from an immutable runtime snapshot. Emits NOTHING when
    nothing is applicable (no generic advice). Deterministic; never raises."""
    try:
        s = snapshot if isinstance(snapshot, Mapping) else {}
        rp = run_plan if isinstance(run_plan, Mapping) else {}
        wf = workflow if isinstance(workflow, Mapping) else {}
        cp = coaching_plan if isinstance(coaching_plan, Mapping) else {}
        ctx_fp = _norm(s.get("context_fingerprint"))
        plan_fp = _norm(rp.get("content_fingerprint"))
        lap = int(s.get("lap") or 0)
        clean = int(s.get("clean_laps") or 0)
        min_clean = int((rp.get("run_structure") or {}).get("minimum_clean_laps") or 0)
        warmup = int((rp.get("run_structure") or {}).get("warm_up_laps") or 0)
        out: List[AdvisoryPrompt] = []

        # 1 safety / invalid-run stop
        if _lc(wf.get("state")) == "invalid" or s.get("run_invalidated"):
            out.append(_p("run_invalidated", PromptPriority.SAFETY_OR_INVALID_STOP.value,
                          DeliveryWindow.IMMEDIATE.value, "Run invalid - stop and reset the test.",
                          "; ".join(wf.get("blockers") or []) or "the run cannot count.",
                          source="assisted_run_workflow", cls=PromptClass.STOP_CRITICAL,
                          key="run_invalidated", cooldown=60.0, ctx_fp=ctx_fp, plan_fp=plan_fp))
        if s.get("stop_condition_reached"):
            out.append(_p("stop_condition", PromptPriority.RUN_PLAN_STOP_CONDITION.value,
                          DeliveryWindow.AFTER_FINISH_LINE.value,
                          "Stop condition reached - end the run.",
                          _norm(s.get("stop_condition_reason")) or "a run stop condition was met.",
                          cls=PromptClass.CAUTIONARY, key="stop_condition", cooldown=60.0,
                          ctx_fp=ctx_fp, plan_fp=plan_fp))

        # 2 context / setup mismatch
        if _lc(s.get("context_trust")) in ("incompatible", "reference_only") or s.get("setup_mismatch"):
            out.append(_p("context_setup_mismatch", PromptPriority.CONTEXT_SETUP_MISMATCH.value,
                          DeliveryWindow.PIT_LANE.value,
                          "Context or setup mismatch - this run may not be comparable.",
                          _norm(s.get("mismatch_reason")) or "the active setup/context does not match "
                          "the plan.", source="material_context", cls=PromptClass.CAUTIONARY,
                          key="context_setup_mismatch", cooldown=45.0, ctx_fp=ctx_fp, plan_fp=plan_fp))

        # wrong tyre / fuel window
        if s.get("wrong_compound"):
            out.append(_p("wrong_compound", PromptPriority.CONTEXT_SETUP_MISMATCH.value,
                          DeliveryWindow.PIT_LANE.value, "Wrong tyre compound for this run.",
                          "the compound does not match the run plan.", cls=PromptClass.CAUTIONARY,
                          key="wrong_compound", cooldown=60.0, ctx_fp=ctx_fp, plan_fp=plan_fp))

        # 4 measurement-lap instruction (after warm-up)
        if s.get("run_active") and lap <= warmup and warmup > 0:
            out.append(_p("insufficient_warmup", PromptPriority.MEASUREMENT_LAP_INSTRUCTION.value,
                          DeliveryWindow.BEFORE_MEASUREMENT.value,
                          f"Warm-up lap {lap}/{warmup} - build temperature before measuring.",
                          "measurement laps start after warm-up.", cls=PromptClass.INFORMATIONAL,
                          key="warmup", cooldown=30.0, ctx_fp=ctx_fp, plan_fp=plan_fp))
        elif s.get("run_active") and warmup and lap == warmup + 1:
            out.append(_p("begin_measurement", PromptPriority.MEASUREMENT_LAP_INSTRUCTION.value,
                          DeliveryWindow.BEFORE_MEASUREMENT.value,
                          "Begin measurement laps - hold everything constant.",
                          "warm-up complete.", cls=PromptClass.INFORMATIONAL, key="begin_measurement",
                          cooldown=60.0, ctx_fp=ctx_fp, plan_fp=plan_fp))

        # 5 target-corner coaching (ONE objective, medium+ confidence)
        priorities = cp.get("priorities") or []
        if s.get("run_active") and priorities and not s.get("coaching_suppressed"):
            p0 = priorities[0]
            corner = _norm(p0.get("corner"))
            approaching = _norm(s.get("approaching_corner"))
            if corner and approaching and _lc(corner) == _lc(approaching):
                out.append(_p("coaching_objective", PromptPriority.TARGET_CORNER_COACHING.value,
                              DeliveryWindow.LOW_WORKLOAD.value,
                              f"{corner}: {p0.get('technique_focus')}",
                              _norm(p0.get("why_it_matters")), source="coaching_priority",
                              confidence=_norm(p0.get("confidence")) or "medium",
                              cls=PromptClass.INFORMATIONAL, target=corner, key=f"coach:{corner}",
                              cooldown=90.0, ctx_fp=ctx_fp, plan_fp=plan_fp))

        # 6 evidence collection
        if s.get("run_active") and min_clean and clean < min_clean:
            out.append(_p("insufficient_clean_laps", PromptPriority.EVIDENCE_COLLECTION.value,
                          DeliveryWindow.AFTER_FINISH_LINE.value,
                          f"{clean}/{min_clean} clean laps - keep going.",
                          "more clean laps are needed for a valid result.", confidence="high",
                          cls=PromptClass.INFORMATIONAL, key="clean_laps", cooldown=60.0,
                          ctx_fp=ctx_fp, plan_fp=plan_fp))
        if s.get("telemetry_unavailable"):
            out.append(_p("telemetry_unavailable", PromptPriority.EVIDENCE_COLLECTION.value,
                          DeliveryWindow.PIT_LANE.value, "Telemetry unavailable - evidence not captured.",
                          "the run cannot be measured without telemetry.", cls=PromptClass.CAUTIONARY,
                          key="telemetry_unavailable", cooldown=60.0, ctx_fp=ctx_fp, plan_fp=plan_fp))

        # 3 enough evidence -> complete the run + feedback (a stop condition variant)
        if s.get("run_active") and min_clean and clean >= min_clean and not s.get("stop_condition_reached"):
            out.append(_p("enough_evidence", PromptPriority.RUN_PLAN_STOP_CONDITION.value,
                          DeliveryWindow.AFTER_FINISH_LINE.value,
                          "Enough valid evidence - complete the run and give feedback.",
                          "the minimum clean-lap target is met.", cls=PromptClass.CAUTIONARY,
                          key="enough_evidence", cooldown=90.0, ack=True, ctx_fp=ctx_fp, plan_fp=plan_fp))

        # 8 strategy awareness (read-only)
        if s.get("event_is_near"):
            out.append(_p("deadline_protect", PromptPriority.STRATEGY_AWARENESS.value,
                          DeliveryWindow.AFTER_SESSION.value,
                          "Event is near - protect the current best-known setup; avoid a high-risk test.",
                          "limited practice time before the event.", source="run_plan",
                          confidence="high", cls=PromptClass.INFORMATIONAL, key="deadline_protect",
                          cooldown=120.0, ctx_fp=ctx_fp, plan_fp=plan_fp))
        if s.get("strategy_evidence_incomplete"):
            out.append(_p("strategy_evidence", PromptPriority.STRATEGY_AWARENESS.value,
                          DeliveryWindow.AFTER_SESSION.value,
                          "Race-plan evidence incomplete - collect tyre/fuel/stint data.",
                          "the race plan cannot be trusted yet.", confidence="low",
                          cls=PromptClass.INFORMATIONAL, key="strategy_evidence", cooldown=120.0,
                          ctx_fp=ctx_fp, plan_fp=plan_fp))
        return out
    except Exception:  # pragma: no cover - defensive
        return []


def advisory_versions() -> dict:
    return {"live_advisory": LIVE_ADVISORY_VERSION, "schema": LIVE_ADVISORY_SCHEMA}
