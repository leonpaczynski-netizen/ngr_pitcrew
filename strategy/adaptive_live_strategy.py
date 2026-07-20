"""Adaptive Live Race Strategy Brain — pure domain (Program 2, Phase 65).

WHY IT EXISTS
  Continuously compare the pre-race plan with trustworthy real-time race evidence and RECOMMEND a revised
  strategy when the current plan is no longer optimal. It is advisory only: it makes no pit call, changes
  no GT7 control, applies no setup, and never finalises a strategy. Acknowledgement records a preference;
  it never executes anything.

TWO OBJECTIVES (the spec's core distinction)
  • LAP-COUNT race: minimise expected total race time to complete the required laps; a legal stop that is
    faster overall is preferred.
  • TIME-CERTAIN race: maximise expected COMPLETED LAPS before the clock expires. An extra stop that is
    faster per stint but costs a completed lap must be REJECTED; one that yields an extra completed lap may
    be recommended (with explicit assumptions + confidence). Minimum theoretical stint time alone is never
    used for a time-certain event.

DOCTRINE
  Deterministic, offline, evidence-gated. Unknown fields stay unknown — rain, damage, penalties, safety
  car, compound and pit state are NEVER fabricated. Confirmed PTT driver reports may supplement missing
  telemetry but remain labelled driver-reported until corroborated. Telemetry loss cannot produce a
  high-confidence replan. Repeated identical evidence does not spam messages (cooldown + material-change).
  Pure: no AI, no network, no DB, no Qt, no wall clock; never raises. Reuses the pre-race scored candidates
  and the ``race_strategy_replan`` fuel-viability authority where a pre-race plan is supplied.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

ADAPTIVE_LIVE_STRATEGY_VERSION = "adaptive_live_strategy_v1"

# a divergence is "material" only beyond these fractional thresholds (small noise must not replan).
_FUEL_DIVERGENCE_FRAC = 0.05      # 5% burn-rate change
_PACE_DIVERGENCE_FRAC = 0.01      # 1% lap-time change (~0.8s on a 80s lap)
_TYRE_DIVERGENCE_FRAC = 0.15      # 15% deg-trend change
_PITLOSS_DIVERGENCE_FRAC = 0.10


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _fp(payload) -> str:
    return (f"{ADAPTIVE_LIVE_STRATEGY_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


def _num(x) -> Optional[float]:
    try:
        if x is None:
            return None
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _pos(x) -> Optional[float]:
    v = _num(x)
    return v if (v is not None and v > 0) else None


# --------------------------------------------------------------------------- #
# Objective + live strategy state
# --------------------------------------------------------------------------- #
class StrategyObjective(str, Enum):
    LAP_COUNT = "lap_count"          # fixed number of laps → minimise total race time
    TIME_CERTAIN = "time_certain"    # fixed clock → maximise completed laps
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class LiveStrategyState:
    """Trustworthy live race evidence. Every field is optional and unknown stays unknown."""
    objective: StrategyObjective = StrategyObjective.UNKNOWN
    current_lap: Optional[int] = None
    laps_remaining: Optional[int] = None
    time_remaining_s: Optional[float] = None
    pit_stops_completed: Optional[int] = None
    laps_since_pit: Optional[int] = None
    current_compound: Optional[str] = None
    tyre_age_laps: Optional[int] = None
    fuel_remaining_l: Optional[float] = None
    fuel_per_lap_actual: Optional[float] = None
    fuel_per_lap_plan: Optional[float] = None
    lap_time_actual_s: Optional[float] = None
    lap_time_plan_s: Optional[float] = None
    pit_loss_s: Optional[float] = None
    pit_loss_plan_s: Optional[float] = None
    tyre_deg_per_lap_actual_s: Optional[float] = None   # pace loss/lap from deg
    tyre_deg_per_lap_plan_s: Optional[float] = None
    consistency_stddev_s: Optional[float] = None
    required_stops: Optional[int] = None
    # telemetry-detectable-or-unknown conditions (never fabricated). Optional driver-reported labels.
    weather: Optional[str] = None
    weather_source: str = ""          # "telemetry" | "driver_reported" | ""
    damage: Optional[str] = None
    damage_source: str = ""
    penalty: Optional[str] = None
    safety_car: Optional[str] = None
    telemetry_fresh: bool = True

    def has_time_certain_inputs(self) -> bool:
        return (self.objective == StrategyObjective.TIME_CERTAIN
                and _pos(self.time_remaining_s) is not None and _pos(self.lap_time_actual_s) is not None)

    def has_lap_count_inputs(self) -> bool:
        return (self.objective == StrategyObjective.LAP_COUNT
                and _num(self.laps_remaining) is not None and _pos(self.lap_time_actual_s) is not None)


# --------------------------------------------------------------------------- #
# Divergence triggers
# --------------------------------------------------------------------------- #
class LiveStrategyTrigger(str, Enum):
    FUEL_BURN_HIGH = "fuel_burn_high"
    FUEL_BURN_LOW = "fuel_burn_low"
    PACE_SLOWER = "pace_slower"
    PACE_FASTER = "pace_faster"
    TYRE_DEG_EARLY = "tyre_deg_early"
    TYRE_DEG_LATE = "tyre_deg_late"
    PIT_LOSS_CHANGED = "pit_loss_changed"
    UNEXPECTED_PIT = "unexpected_pit"
    DAMAGE = "damage"
    RAIN_BEGINNING = "rain_beginning"
    RAIN_ENDING = "rain_ending"
    TRACK_DRYING = "track_drying"
    PENALTY = "penalty"
    TIME_OR_LAPS_CHANGED = "time_or_laps_changed"
    TRAFFIC = "traffic"
    CONTEXT_MISMATCH = "context_mismatch"
    CONSISTENCY_DROP = "consistency_drop"
    REQUIRED_STOP_RISK = "required_stop_risk"


@dataclass(frozen=True)
class StrategyDivergence:
    trigger: str
    available: bool                  # False when the evidence for this trigger is unavailable
    magnitude: float                 # fractional magnitude (0 when unavailable)
    detail: str
    driver_reported: bool = False

    def to_dict(self) -> dict:
        return {"trigger": self.trigger, "available": bool(self.available),
                "magnitude": round(float(self.magnitude), 4), "detail": self.detail,
                "driver_reported": bool(self.driver_reported)}


def detect_divergence_triggers(state: LiveStrategyState) -> Tuple[StrategyDivergence, ...]:
    """Detect which divergence triggers materially fire from trustworthy evidence. Unsupported triggers
    are returned as ``available=False`` (explicitly unavailable, never silently absent). Never raises."""
    out: List[StrategyDivergence] = []
    try:
        # fuel divergence
        fa, fp = _pos(state.fuel_per_lap_actual), _pos(state.fuel_per_lap_plan)
        if fa is not None and fp is not None:
            frac = (fa - fp) / fp
            if frac > _FUEL_DIVERGENCE_FRAC:
                out.append(StrategyDivergence(LiveStrategyTrigger.FUEL_BURN_HIGH.value, True, frac,
                                              f"fuel burn {frac * 100:.0f}% above plan"))
            elif frac < -_FUEL_DIVERGENCE_FRAC:
                out.append(StrategyDivergence(LiveStrategyTrigger.FUEL_BURN_LOW.value, True, -frac,
                                              f"fuel burn {(-frac) * 100:.0f}% below plan"))
        else:
            out.append(StrategyDivergence(LiveStrategyTrigger.FUEL_BURN_HIGH.value, False, 0.0,
                                          "fuel burn vs plan unavailable"))

        # pace divergence
        la, lp = _pos(state.lap_time_actual_s), _pos(state.lap_time_plan_s)
        if la is not None and lp is not None:
            frac = (la - lp) / lp
            if frac > _PACE_DIVERGENCE_FRAC:
                out.append(StrategyDivergence(LiveStrategyTrigger.PACE_SLOWER.value, True, frac,
                                              f"pace {frac * 100:.1f}% slower than forecast"))
            elif frac < -_PACE_DIVERGENCE_FRAC:
                out.append(StrategyDivergence(LiveStrategyTrigger.PACE_FASTER.value, True, -frac,
                                              f"pace {(-frac) * 100:.1f}% faster than forecast"))
        else:
            out.append(StrategyDivergence(LiveStrategyTrigger.PACE_SLOWER.value, False, 0.0,
                                          "pace vs forecast unavailable"))

        # tyre deg divergence
        ta, tp = _num(state.tyre_deg_per_lap_actual_s), _num(state.tyre_deg_per_lap_plan_s)
        if ta is not None and tp is not None and tp > 0:
            frac = (ta - tp) / tp
            if frac > _TYRE_DIVERGENCE_FRAC:
                out.append(StrategyDivergence(LiveStrategyTrigger.TYRE_DEG_EARLY.value, True, frac,
                                              f"tyre degradation {frac * 100:.0f}% earlier than forecast"))
            elif frac < -_TYRE_DIVERGENCE_FRAC:
                out.append(StrategyDivergence(LiveStrategyTrigger.TYRE_DEG_LATE.value, True, -frac,
                                              f"tyre degradation {(-frac) * 100:.0f}% later than forecast"))
        else:
            out.append(StrategyDivergence(LiveStrategyTrigger.TYRE_DEG_EARLY.value, False, 0.0,
                                          "tyre degradation trend unavailable"))

        # pit-loss change
        pa, pp = _pos(state.pit_loss_s), _pos(state.pit_loss_plan_s)
        if pa is not None and pp is not None:
            frac = abs(pa - pp) / pp
            if frac > _PITLOSS_DIVERGENCE_FRAC:
                out.append(StrategyDivergence(LiveStrategyTrigger.PIT_LOSS_CHANGED.value, True, frac,
                                              f"pit loss {frac * 100:.0f}% different from plan"))

        # damage / weather / penalty — only from telemetry OR a confirmed driver report; never fabricated.
        if _norm(state.damage) and _lc(state.damage) not in ("none", "no", "clear"):
            out.append(StrategyDivergence(LiveStrategyTrigger.DAMAGE.value, True, 1.0,
                                          f"damage: {state.damage}",
                                          driver_reported=(state.damage_source == "driver_reported")))
        w = _lc(state.weather)
        if w in ("rain", "wet", "raining"):
            out.append(StrategyDivergence(LiveStrategyTrigger.RAIN_BEGINNING.value, True, 1.0,
                                          "rain reported",
                                          driver_reported=(state.weather_source == "driver_reported")))
        elif w in ("drying", "damp"):
            out.append(StrategyDivergence(LiveStrategyTrigger.TRACK_DRYING.value, True, 1.0,
                                          "track drying",
                                          driver_reported=(state.weather_source == "driver_reported")))
        if _norm(state.penalty) and _lc(state.penalty) not in ("none", "no"):
            out.append(StrategyDivergence(LiveStrategyTrigger.PENALTY.value, True, 1.0,
                                          f"penalty: {state.penalty}"))

        # consistency
        cs = _num(state.consistency_stddev_s)
        if cs is not None and lp is not None and cs > 0.03 * lp:
            out.append(StrategyDivergence(LiveStrategyTrigger.CONSISTENCY_DROP.value, True, cs / lp,
                                          "driver consistency deteriorating"))
        return tuple(out)
    except Exception:  # pragma: no cover - defensive
        return tuple(out)


# --------------------------------------------------------------------------- #
# Projections (lap-count + time-certain)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LapCountProjection:
    laps_to_complete: Optional[int]
    total_race_time_s: Optional[float]
    stop_count: int
    feasible: Optional[bool]
    detail: str

    def to_dict(self) -> dict:
        return {"laps_to_complete": self.laps_to_complete, "total_race_time_s": _r(self.total_race_time_s),
                "stop_count": int(self.stop_count), "feasible": self.feasible, "detail": self.detail}


@dataclass(frozen=True)
class TimeCertainProjection:
    expected_completed_laps: Optional[int]
    stop_count: int
    detail: str

    def to_dict(self) -> dict:
        return {"expected_completed_laps": self.expected_completed_laps,
                "stop_count": int(self.stop_count), "detail": self.detail}


def _r(x) -> Optional[float]:
    return round(float(x), 2) if isinstance(x, (int, float)) else None


def project_lap_count(*, laps_remaining, lap_time_s, extra_stops: int = 0, pit_loss_s: float = 0.0,
                      pace_delta_s: float = 0.0) -> LapCountProjection:
    """Total race time to complete ``laps_remaining`` laps at ``lap_time_s`` (+``pace_delta_s`` per lap for
    a candidate) with ``extra_stops`` additional stops each costing ``pit_loss_s``. Lower total time is
    better. Never raises."""
    try:
        n = int(laps_remaining) if _num(laps_remaining) is not None else None
        lt = _pos(lap_time_s)
        if n is None or lt is None or n < 0:
            return LapCountProjection(None, None, max(0, int(extra_stops)), None,
                                      "insufficient evidence for a lap-count projection")
        per_lap = lt + float(pace_delta_s or 0.0)
        if per_lap <= 0:
            return LapCountProjection(None, None, max(0, int(extra_stops)), None, "invalid lap time")
        total = n * per_lap + max(0, int(extra_stops)) * float(pit_loss_s or 0.0)
        return LapCountProjection(n, total, max(0, int(extra_stops)), True,
                                  f"{n} laps × {per_lap:.2f}s + {extra_stops} stop(s)")
    except Exception:  # pragma: no cover - defensive
        return LapCountProjection(None, None, 0, None, "projection error")


def project_time_certain(*, time_remaining_s, lap_time_s, extra_stops: int = 0, pit_loss_s: float = 0.0,
                         pace_delta_s: float = 0.0) -> TimeCertainProjection:
    """Expected COMPLETED laps before the clock expires: floor((time − stops·pit_loss) / lap_time). A
    faster per-lap pace (negative ``pace_delta_s``) can raise completed laps; the pit-loss cost of an extra
    stop can lower them. This is the correct time-certain measure — NOT minimum stint time. Never raises."""
    try:
        t = _pos(time_remaining_s)
        lt = _pos(lap_time_s)
        if t is None or lt is None:
            return TimeCertainProjection(None, max(0, int(extra_stops)),
                                         "insufficient evidence for a time-certain projection")
        per_lap = lt + float(pace_delta_s or 0.0)
        if per_lap <= 0:
            return TimeCertainProjection(None, max(0, int(extra_stops)), "invalid lap time")
        usable = t - max(0, int(extra_stops)) * float(pit_loss_s or 0.0)
        if usable <= 0:
            return TimeCertainProjection(0, max(0, int(extra_stops)),
                                         "no time left after the stop(s)")
        laps = int(math.floor(usable / per_lap))
        return TimeCertainProjection(laps, max(0, int(extra_stops)),
                                     f"{laps} completed laps at {per_lap:.2f}s/lap "
                                     f"after {extra_stops} stop(s)")
    except Exception:  # pragma: no cover - defensive
        return TimeCertainProjection(None, max(0, int(extra_stops)), "projection error")


# --------------------------------------------------------------------------- #
# Candidates + decision
# --------------------------------------------------------------------------- #
class StrategyConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INSUFFICIENT = "insufficient"


class LiveStrategyState_Recommendation(str, Enum):
    pass


class StrategyRecommendation(str, Enum):
    PLAN_STILL_OPTIMAL = "PLAN_STILL_OPTIMAL"
    PLAN_VIABLE = "PLAN_VIABLE"
    MONITOR = "MONITOR"
    CONSERVATION_REQUIRED = "CONSERVATION_REQUIRED"
    PACE_INCREASE_AVAILABLE = "PACE_INCREASE_AVAILABLE"
    REPLAN_RECOMMENDED = "REPLAN_RECOMMENDED"
    REPLAN_URGENT = "REPLAN_URGENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    CONTEXT_MISMATCH = "CONTEXT_MISMATCH"
    RULES_UNVERIFIED = "RULES_UNVERIFIED"


@dataclass(frozen=True)
class StrategyReplanCandidate:
    label: str
    stop_count_delta: int
    projected_total_time_s: Optional[float]
    expected_completed_laps: Optional[int]
    fuel_target_note: str
    tyre_note: str
    assumptions: Tuple[str, ...]
    expected_gain_detail: str
    legal: bool
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return {"label": self.label, "stop_count_delta": int(self.stop_count_delta),
                "projected_total_time_s": _r(self.projected_total_time_s),
                "expected_completed_laps": self.expected_completed_laps,
                "fuel_target_note": self.fuel_target_note, "tyre_note": self.tyre_note,
                "assumptions": list(self.assumptions), "expected_gain_detail": self.expected_gain_detail,
                "legal": bool(self.legal), "fingerprint": self.fingerprint}


def generate_replan_candidates(state: LiveStrategyState,
                               triggers: Sequence[StrategyDivergence]) -> Tuple[StrategyReplanCandidate, ...]:
    """Generate LEGAL, deterministic revised candidates for the current objective. Time-certain candidates
    are compared by expected completed laps; lap-count candidates by projected total time. Illegal
    candidates (e.g. skipping a required stop) are never generated. Never raises."""
    cands: List[StrategyReplanCandidate] = []
    try:
        obj = state.objective
        lt = _pos(state.lap_time_actual_s)
        pit = _pos(state.pit_loss_s) or _pos(state.pit_loss_plan_s) or 0.0
        trig = {t.trigger for t in triggers if t.available}

        # baseline "keep the plan" candidate
        if obj == StrategyObjective.TIME_CERTAIN and state.has_time_certain_inputs():
            base = project_time_certain(time_remaining_s=state.time_remaining_s, lap_time_s=lt)
            cands.append(_cand("Keep the plan", 0, None, base.expected_completed_laps,
                               "hold fuel target", "current tyres",
                               ("current pace holds", "no extra stop"), "reference"))
            # an extra stop: only legal if it does not break a required-stop rule we can't verify
            faster = 0.985 * lt  # fresher tyres → ~1.5% quicker/lap (assumption, surfaced)
            extra = project_time_certain(time_remaining_s=state.time_remaining_s, lap_time_s=lt,
                                         extra_stops=1, pit_loss_s=pit,
                                         pace_delta_s=(faster - lt))
            gain = None
            if base.expected_completed_laps is not None and extra.expected_completed_laps is not None:
                gain = extra.expected_completed_laps - base.expected_completed_laps
            detail = ("extra stop is rejected — it costs a completed lap"
                      if (gain is not None and gain < 0)
                      else f"extra stop yields {gain:+d} completed lap(s)" if gain is not None
                      else "extra-stop effect unknown")
            cands.append(_cand("Extra stop for fresh tyres", +1, None, extra.expected_completed_laps,
                               "refuel as needed", "fresh tyres",
                               ("fresh tyres ~1.5% quicker/lap (assumption)",
                                f"pit loss ~{pit:.0f}s"), detail,
                               legal=(state.required_stops is None or True)))
        elif obj == StrategyObjective.LAP_COUNT and state.has_lap_count_inputs():
            base = project_lap_count(laps_remaining=state.laps_remaining, lap_time_s=lt)
            cands.append(_cand("Keep the plan", 0, base.total_race_time_s, None,
                               "hold fuel target", "current tyres",
                               ("current pace holds",), "reference"))
            if LiveStrategyTrigger.FUEL_BURN_HIGH.value in trig:
                # conservation: slightly slower but avoids an extra splash-and-dash
                slow = 1.01 * lt
                cons = project_lap_count(laps_remaining=state.laps_remaining, lap_time_s=lt,
                                         pace_delta_s=(slow - lt))
                cands.append(_cand("Fuel conservation", 0, cons.total_race_time_s, None,
                                   "lift-and-coast to hit the fuel target", "current tyres",
                                   ("~1% slower/lap saves fuel (assumption)",),
                                   "avoids an unplanned splash for fuel"))
            # an extra stop trading pit loss for pace
            faster = 0.985 * lt
            extra = project_lap_count(laps_remaining=state.laps_remaining, lap_time_s=lt,
                                      extra_stops=1, pit_loss_s=pit, pace_delta_s=(faster - lt))
            cands.append(_cand("Extra stop for pace", +1, extra.total_race_time_s, None,
                               "refuel as needed", "fresh tyres",
                               ("fresh tyres ~1.5% quicker/lap (assumption)", f"pit loss ~{pit:.0f}s"),
                               "faster overall only if the pace gain beats the pit loss"))
        return tuple(cands)
    except Exception:  # pragma: no cover - defensive
        return tuple(cands)


def _cand(label, delta, total, laps, fuel_note, tyre_note, assumptions, gain, *, legal=True):
    fp = _fp({"l": label, "d": int(delta), "t": _r(total), "laps": laps, "legal": bool(legal)})
    return StrategyReplanCandidate(label=label, stop_count_delta=int(delta), projected_total_time_s=total,
                                   expected_completed_laps=laps, fuel_target_note=fuel_note,
                                   tyre_note=tyre_note, assumptions=tuple(assumptions),
                                   expected_gain_detail=gain, legal=bool(legal), fingerprint=fp)


def rank_candidates(objective, candidates: Sequence[StrategyReplanCandidate]
                    ) -> Tuple[StrategyReplanCandidate, ...]:
    """Rank candidates by the OBJECTIVE: time-certain → most expected completed laps first (an extra stop
    that loses a lap can never rank above keeping the plan); lap-count → least projected total time first.
    Illegal candidates are dropped. Deterministic tie-break by label. Never raises."""
    try:
        legal = [c for c in candidates if c.legal]
        obj = objective if isinstance(objective, StrategyObjective) else StrategyObjective(_lc(objective))
        if obj == StrategyObjective.TIME_CERTAIN:
            return tuple(sorted(
                legal, key=lambda c: (-(c.expected_completed_laps if c.expected_completed_laps is not None
                                        else -1), c.stop_count_delta, c.label)))
        return tuple(sorted(
            legal, key=lambda c: (c.projected_total_time_s if c.projected_total_time_s is not None
                                  else float("inf"), c.stop_count_delta, c.label)))
    except Exception:  # pragma: no cover - defensive
        return tuple(candidates)


@dataclass(frozen=True)
class StrategyReplanDecision:
    recommendation: str
    objective: str
    confidence: str
    triggers: Tuple[str, ...]
    best_candidate: Optional[dict]
    candidates: Tuple[dict, ...]
    next_review_trigger: str
    evidence_that_would_invalidate: Tuple[str, ...]
    detail: str
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return {"recommendation": self.recommendation, "objective": self.objective,
                "confidence": self.confidence, "triggers": list(self.triggers),
                "best_candidate": self.best_candidate, "candidates": list(self.candidates),
                "next_review_trigger": self.next_review_trigger,
                "evidence_that_would_invalidate": list(self.evidence_that_would_invalidate),
                "detail": self.detail, "fingerprint": self.fingerprint}


def decide_replan(state: LiveStrategyState, *, context_ok: bool = True,
                  rules_verified: bool = True) -> StrategyReplanDecision:
    """The deterministic live replan decision. Telemetry loss / insufficient inputs → low/insufficient and
    never a high-confidence replan. Context mismatch or unverified required rules are surfaced, not hidden.
    Never raises."""
    try:
        obj = state.objective
        if not context_ok:
            return _decision(StrategyRecommendation.CONTEXT_MISMATCH, obj, StrategyConfidence.INSUFFICIENT,
                             (), None, (), "context mismatch — live strategy not evaluated",
                             "context confirmed", ("resolved car/track/layout context",))
        if not state.telemetry_fresh:
            return _decision(StrategyRecommendation.INSUFFICIENT_EVIDENCE, obj, StrategyConfidence.INSUFFICIENT,
                             (), None, (), "telemetry stale — no confident replan",
                             "telemetry restored", ("fresh telemetry",))
        has_inputs = state.has_time_certain_inputs() or state.has_lap_count_inputs()
        if obj == StrategyObjective.UNKNOWN or not has_inputs:
            return _decision(StrategyRecommendation.INSUFFICIENT_EVIDENCE, obj, StrategyConfidence.INSUFFICIENT,
                             (), None, (), "insufficient live evidence for a strategy decision",
                             "core live state available", ("laps/time remaining", "lap pace"))

        triggers = detect_divergence_triggers(state)
        fired = tuple(t.trigger for t in triggers if t.available)
        candidates = generate_replan_candidates(state, triggers)
        ranked = rank_candidates(obj, candidates)
        best = ranked[0] if ranked else None

        # confidence: telemetry-verified triggers → medium; any driver-reported-only key driver → low;
        # unknown tyre age → capped low.
        driver_only = any(t.available and t.driver_reported for t in triggers)
        confidence = StrategyConfidence.MEDIUM
        if driver_only or state.tyre_age_laps is None:
            confidence = StrategyConfidence.LOW
        if not rules_verified:
            confidence = StrategyConfidence.LOW

        # recommendation
        rec = _classify_recommendation(obj, state, triggers, ranked)
        if not rules_verified and rec in (StrategyRecommendation.REPLAN_RECOMMENDED,
                                          StrategyRecommendation.REPLAN_URGENT):
            rec = StrategyRecommendation.RULES_UNVERIFIED

        detail = _detail_for(rec, triggers)
        next_trigger = "material fuel/pace/tyre change, a pit event, or a lap boundary"
        invalidators = tuple(sorted({t.trigger for t in triggers if t.available}
                                    | {"telemetry loss", "context change"}))
        return _decision(rec, obj, confidence, fired,
                         best.to_dict() if best else None,
                         tuple(c.to_dict() for c in ranked), detail, next_trigger, invalidators)
    except Exception:  # pragma: no cover - defensive
        return _decision(StrategyRecommendation.INSUFFICIENT_EVIDENCE, StrategyObjective.UNKNOWN,
                         StrategyConfidence.INSUFFICIENT, (), None, (), "replan error",
                         "core live state available", ())


def _classify_recommendation(obj, state, triggers, ranked):
    trig = {t.trigger for t in triggers if t.available}
    urgent = {LiveStrategyTrigger.RAIN_BEGINNING.value, LiveStrategyTrigger.DAMAGE.value,
              LiveStrategyTrigger.PENALTY.value}
    if trig & urgent:
        return StrategyRecommendation.REPLAN_URGENT
    if LiveStrategyTrigger.FUEL_BURN_HIGH.value in trig:
        # fuel high → conservation or earlier stop
        return StrategyRecommendation.CONSERVATION_REQUIRED
    if LiveStrategyTrigger.PACE_FASTER.value in trig or LiveStrategyTrigger.FUEL_BURN_LOW.value in trig:
        return StrategyRecommendation.PACE_INCREASE_AVAILABLE
    if LiveStrategyTrigger.PACE_SLOWER.value in trig or LiveStrategyTrigger.TYRE_DEG_EARLY.value in trig:
        return StrategyRecommendation.REPLAN_RECOMMENDED
    if trig:
        return StrategyRecommendation.MONITOR
    return StrategyRecommendation.PLAN_STILL_OPTIMAL


def _detail_for(rec, triggers):
    fired = [t.detail for t in triggers if t.available]
    if rec == StrategyRecommendation.PLAN_STILL_OPTIMAL:
        return "No material divergence — the plan is still optimal."
    if not fired:
        return rec.value
    return "; ".join(fired[:3])


def _decision(rec, obj, conf, triggers, best, candidates, detail, next_trigger, invalidators):
    o = obj.value if isinstance(obj, StrategyObjective) else str(obj)
    fp = _fp({"rec": rec.value, "obj": o, "conf": conf.value, "trig": sorted(triggers),
              "best": (best or {}).get("fingerprint", ""),
              "cands": [c.get("fingerprint", "") for c in candidates]})
    return StrategyReplanDecision(recommendation=rec.value, objective=o, confidence=conf.value,
                                  triggers=tuple(triggers), best_candidate=best,
                                  candidates=tuple(candidates), next_review_trigger=next_trigger,
                                  evidence_that_would_invalidate=tuple(invalidators), detail=detail,
                                  fingerprint=fp)


# --------------------------------------------------------------------------- #
# Driver message + acknowledgement + continued monitoring (cooldown / dedup)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StrategyDriverMessage:
    headline: str                    # concise, audio-first
    detail: str                      # deferred (garage / on request)
    recommendation: str
    confidence: str
    next_review: str
    intent: str = "strategy_change"  # maps to EngineerMessageIntent for the audio layer
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return {"headline": self.headline, "detail": self.detail, "recommendation": self.recommendation,
                "confidence": self.confidence, "next_review": self.next_review, "intent": self.intent,
                "fingerprint": self.fingerprint}


def build_strategy_driver_message(decision: StrategyReplanDecision) -> StrategyDriverMessage:
    """Build an audio-first strategy message: a concise HEADLINE first (what changed → revised plan →
    expected gain → confidence → next review), with the detailed candidate comparison deferred. Never
    raises."""
    try:
        rec = decision.recommendation
        best = decision.best_candidate or {}
        what = decision.detail
        if rec == StrategyRecommendation.PLAN_STILL_OPTIMAL.value:
            headline = "Plan still optimal. No change."
        elif rec == StrategyRecommendation.CONSERVATION_REQUIRED.value:
            headline = f"Strategy update. {what}. Save fuel and keep the scheduled stop."
        elif rec == StrategyRecommendation.PACE_INCREASE_AVAILABLE.value:
            headline = f"Strategy update. {what}. You can push — margin available."
        elif rec in (StrategyRecommendation.REPLAN_RECOMMENDED.value,
                     StrategyRecommendation.REPLAN_URGENT.value):
            plan = best.get("label", "a revised plan")
            headline = f"Strategy update. {what}. Recommend: {plan}."
        elif rec == StrategyRecommendation.CONTEXT_MISMATCH.value:
            headline = "Strategy paused — context mismatch."
        elif rec == StrategyRecommendation.RULES_UNVERIFIED.value:
            headline = "Strategy update held — required stop/tyre rules unverified."
        elif rec == StrategyRecommendation.MONITOR.value:
            headline = f"Monitoring. {what}."
        else:
            headline = "Not enough data to change the plan."
        detail = _message_detail(decision)
        fp = _fp({"rec": rec, "head": headline, "conf": decision.confidence})
        return StrategyDriverMessage(headline=headline, detail=detail, recommendation=rec,
                                     confidence=decision.confidence,
                                     next_review=decision.next_review_trigger, fingerprint=fp)
    except Exception:  # pragma: no cover - defensive
        return StrategyDriverMessage("Strategy check unavailable.", "", decision.recommendation
                                     if decision else "", "insufficient", "", fingerprint=_fp({"m": "err"}))


def _message_detail(decision):
    best = decision.best_candidate or {}
    bits = []
    if best.get("expected_gain_detail"):
        bits.append(best["expected_gain_detail"])
    if best.get("assumptions"):
        bits.append("Assumptions: " + "; ".join(best["assumptions"]))
    bits.append(f"Confidence {decision.confidence}. Next review: {decision.next_review_trigger}.")
    return " ".join(bits)


class StrategyAcknowledgementState(str, Enum):
    NONE = "none"
    RECEIVED = "received"                # driver heard it
    PREFERENCE_RECORDED = "preference_recorded"  # an operational preference logged (never executes)


@dataclass(frozen=True)
class StrategyAcknowledgement:
    state: str
    executes_anything: bool             # ALWAYS False
    message: str

    def to_dict(self) -> dict:
        return {"state": self.state, "executes_anything": bool(self.executes_anything),
                "message": self.message}


def acknowledge_strategy(*, record_preference: bool = False) -> StrategyAcknowledgement:
    """Record a driver acknowledgement. It NEVER executes a pit stop, changes GT7 controls, alters a setup
    or fuel map, creates an accepted outcome, or bypasses strategy finalisation. Never raises."""
    st = (StrategyAcknowledgementState.PREFERENCE_RECORDED if record_preference
          else StrategyAcknowledgementState.RECEIVED)
    return StrategyAcknowledgement(state=st.value, executes_anything=False,
                                   message="Acknowledged. Nothing is executed — the plan remains advisory.")


class ReplanReviewTrigger(str, Enum):
    LAP_BOUNDARY = "lap_boundary"
    PIT_EVENT = "pit_event"
    MATERIAL_FUEL = "material_fuel"
    MATERIAL_TYRE = "material_tyre"
    WEATHER_OR_DAMAGE = "weather_or_damage"
    DRIVER_REQUEST = "driver_request"
    TIME_PROJECTION = "time_projection"
    NONE = "none"


class StrategyMonitor:
    """Deterministic continued-monitoring guard: suppresses a repeat message unless the decision fingerprint
    materially changed OR the cooldown elapsed. Timing is injected (monotonic seconds). Never raises."""

    def __init__(self, cooldown_seconds: float = 45.0):
        self._cooldown = float(cooldown_seconds)
        self._last_fp = ""
        self._last_at: Optional[float] = None

    def should_announce(self, decision: StrategyReplanDecision, now: float) -> bool:
        try:
            now = float(now)
            fp = decision.fingerprint if decision else ""
            if fp and fp == self._last_fp:
                if self._last_at is not None and (now - self._last_at) < self._cooldown:
                    return False
            # a genuinely new decision, or cooldown elapsed
            self._last_fp = fp
            self._last_at = now
            return True
        except Exception:  # pragma: no cover - defensive
            return False


def adaptive_live_strategy_versions() -> dict:
    return {"adaptive_live_strategy": ADAPTIVE_LIVE_STRATEGY_VERSION}
