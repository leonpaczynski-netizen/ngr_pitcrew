"""Canonical Live Race-State Mapping (Program 2, Phase 66).

WHY IT EXISTS
  Phase 65 built the Adaptive Strategy Brain but the production panel showed a perpetual
  INSUFFICIENT_EVIDENCE default because no adapter fed it the REAL runtime. This module is the trustworthy
  adapter from the existing `RaceStateTracker` + canonical local authorities into one immutable
  ``CanonicalLiveRaceState``, and from there into the Phase-65 ``LiveStrategyState`` — activating the
  strategy runtime for real GT7 races.

DOCTRINE
  Deterministic, offline, evidence-gated. It READS the existing tracker (a thin, duck-typed read) — it
  creates no listener/socket/tracker, and never queries the DB. Unknown stays unknown: GT7 does not
  broadcast tyre condition (proxy only), weather, damage, penalties or safety-car, so those are UNAVAILABLE
  unless a CONFIRMED PTT driver report supplies them (and then only labelled driver-reported, never verified
  telemetry). Robust multi-lap evidence — one anomalous lap never drives a decision. No wall clock (elapsed
  time is injected). Volatile control inputs (speed/throttle/brake/steering/gear) are workload-only and are
  excluded from the fingerprint. Never raises.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from strategy.adaptive_live_strategy import LiveStrategyState, StrategyObjective, project_time_certain

CANONICAL_LIVE_RACE_STATE_VERSION = "canonical_live_race_state_v1"

# GT7 domain constant: full tank is always 100 litres.
_GT7_TANK_L = 100.0


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


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


def _fp(payload) -> str:
    return (f"{CANONICAL_LIVE_RACE_STATE_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


def _median(vals: Sequence[float]) -> Optional[float]:
    xs = sorted(float(v) for v in vals if _num(v) is not None)
    if not xs:
        return None
    n = len(xs)
    mid = n // 2
    return xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2.0


# --------------------------------------------------------------------------- #
# Availability / confidence + a single field record
# --------------------------------------------------------------------------- #
class LiveRaceStateAvailability(str, Enum):
    MEASURED = "measured"                 # directly measured from telemetry
    DERIVED = "derived"                   # computed from measured evidence
    DRIVER_REPORTED = "driver_reported"   # from a confirmed PTT report (never verified telemetry)
    UNAVAILABLE = "unavailable"           # GT7 does not provide it and no report exists


class LiveRaceStateConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


@dataclass(frozen=True)
class LiveRaceStateField:
    name: str
    value: Any
    availability: LiveRaceStateAvailability
    confidence: LiveRaceStateConfidence
    in_fingerprint: bool = True

    @property
    def measured(self) -> bool:
        return self.availability == LiveRaceStateAvailability.MEASURED

    @property
    def derived(self) -> bool:
        return self.availability == LiveRaceStateAvailability.DERIVED

    @property
    def driver_reported(self) -> bool:
        return self.availability == LiveRaceStateAvailability.DRIVER_REPORTED

    @property
    def unavailable(self) -> bool:
        return self.availability == LiveRaceStateAvailability.UNAVAILABLE

    def as_payload(self) -> dict:
        return {"name": self.name, "value": self.value, "availability": self.availability.value,
                "confidence": self.confidence.value}


# --------------------------------------------------------------------------- #
# Sub-states
# --------------------------------------------------------------------------- #
class RaceType(str, Enum):
    LAP = "lap"
    TIMED = "timed"
    UNLIMITED = "unlimited"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RaceClockState:
    race_type: RaceType
    current_lap: Optional[int]
    scheduled_laps: Optional[int]
    laps_remaining: Optional[int]
    race_duration_s: Optional[float]
    elapsed_s: Optional[float]
    remaining_s: Optional[float]
    expected_completed_laps: Optional[int]
    additional_stop_changes_lapcount: Optional[bool]   # time-certain: does +1 stop lose/keep a lap?
    finishing_lap_semantics: str = "cross_line_after_time"   # configurable NGR event semantics

    def as_payload(self) -> dict:
        return {"race_type": self.race_type.value, "current_lap": self.current_lap,
                "scheduled_laps": self.scheduled_laps, "laps_remaining": self.laps_remaining,
                "race_duration_s": _r(self.race_duration_s), "elapsed_s": _r(self.elapsed_s),
                "remaining_s": _r(self.remaining_s), "expected_completed_laps": self.expected_completed_laps,
                "additional_stop_changes_lapcount": self.additional_stop_changes_lapcount,
                "finishing_lap_semantics": self.finishing_lap_semantics}


@dataclass(frozen=True)
class StintState:
    stint_start_lap: Optional[int]
    stint_age_laps: Optional[int]
    compound: Optional[str]
    tyre_deg_per_lap_s: Optional[float]      # PROXY from lap-time drift
    tyre_deg_is_proxy: bool = True

    def as_payload(self) -> dict:
        return {"stint_start_lap": self.stint_start_lap, "stint_age_laps": self.stint_age_laps,
                "compound": _norm(self.compound), "tyre_deg_per_lap_s": _r(self.tyre_deg_per_lap_s),
                "tyre_deg_is_proxy": bool(self.tyre_deg_is_proxy)}


class PitPhase(str, Enum):
    NOT_IN_PIT = "not_in_pit"
    PIT_ENTRY_SUSPECTED = "pit_entry_suspected"
    PIT_CONFIRMED = "pit_confirmed"
    PIT_EXIT = "pit_exit"
    STOP_COMPLETED = "stop_completed"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class PitState:
    phase: PitPhase
    pit_stops_completed: Optional[int]
    confidence: LiveRaceStateConfidence

    def as_payload(self) -> dict:
        return {"phase": self.phase.value, "pit_stops_completed": self.pit_stops_completed,
                "confidence": self.confidence.value}


def _r(x) -> Optional[float]:
    return round(float(x), 2) if isinstance(x, (int, float)) else None


# --------------------------------------------------------------------------- #
# The canonical immutable snapshot
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CanonicalLiveRaceState:
    telemetry_fresh: bool
    clock: RaceClockState
    stint: StintState
    pit: PitState
    fuel_remaining_l: Optional[float]
    fuel_per_lap_plan: Optional[float]
    fuel_per_lap_live: Optional[float]
    lap_time_plan_s: Optional[float]
    lap_time_live_s: Optional[float]
    consistency_stddev_s: Optional[float]
    position: Optional[int]
    car: str
    track: str
    layout: str
    weather: Optional[str]
    weather_source: str
    damage: Optional[str]
    damage_source: str
    penalty: Optional[str]
    required_stops: Optional[int]
    context_ok: bool
    rules_verified: bool
    fields: Tuple[LiveRaceStateField, ...] = ()
    fingerprint: str = ""

    def field_map(self) -> Dict[str, LiveRaceStateField]:
        return {f.name: f for f in self.fields}

    def as_payload(self) -> dict:
        # volatile control inputs are excluded from the fingerprint (not present here).
        return {"telemetry_fresh": bool(self.telemetry_fresh), "clock": self.clock.as_payload(),
                "stint": self.stint.as_payload(), "pit": self.pit.as_payload(),
                "fuel_remaining_l": _r(self.fuel_remaining_l),
                "fuel_per_lap_plan": _r(self.fuel_per_lap_plan),
                "fuel_per_lap_live": _r(self.fuel_per_lap_live),
                "lap_time_plan_s": _r(self.lap_time_plan_s), "lap_time_live_s": _r(self.lap_time_live_s),
                "position": self.position, "car": self.car, "track": self.track, "layout": self.layout,
                "weather": _norm(self.weather), "weather_source": self.weather_source,
                "damage": _norm(self.damage), "damage_source": self.damage_source,
                "penalty": _norm(self.penalty), "required_stops": self.required_stops,
                "context_ok": bool(self.context_ok), "rules_verified": bool(self.rules_verified),
                "fields": [f.as_payload() for f in self.fields]}

    def to_dict(self) -> dict:
        d = self.as_payload()
        d["fingerprint"] = self.fingerprint
        return d

    def to_live_strategy_state(self) -> LiveStrategyState:
        """Produce the Phase-65 LiveStrategyState the Adaptive Strategy Brain consumes. Unknown stays
        unknown; driver-reported weather/damage are passed with their labels."""
        objective = (StrategyObjective.TIME_CERTAIN if self.clock.race_type == RaceType.TIMED
                     else StrategyObjective.LAP_COUNT if self.clock.race_type == RaceType.LAP
                     else StrategyObjective.UNKNOWN)
        return LiveStrategyState(
            objective=objective, current_lap=self.clock.current_lap,
            laps_remaining=self.clock.laps_remaining, time_remaining_s=self.clock.remaining_s,
            pit_stops_completed=self.pit.pit_stops_completed, laps_since_pit=self.stint.stint_age_laps,
            current_compound=self.stint.compound, tyre_age_laps=self.stint.stint_age_laps,
            fuel_remaining_l=self.fuel_remaining_l, fuel_per_lap_actual=self.fuel_per_lap_live,
            fuel_per_lap_plan=self.fuel_per_lap_plan, lap_time_actual_s=self.lap_time_live_s,
            lap_time_plan_s=self.lap_time_plan_s, pit_loss_s=None, pit_loss_plan_s=None,
            tyre_deg_per_lap_actual_s=self.stint.tyre_deg_per_lap_s, tyre_deg_per_lap_plan_s=None,
            consistency_stddev_s=self.consistency_stddev_s, required_stops=self.required_stops,
            weather=self.weather, weather_source=self.weather_source, damage=self.damage,
            damage_source=self.damage_source, penalty=self.penalty, safety_car=None,
            telemetry_fresh=self.telemetry_fresh)


# --------------------------------------------------------------------------- #
# The adapter
# --------------------------------------------------------------------------- #
def _race_type(raw) -> RaceType:
    s = _lc(getattr(raw, "value", raw))
    if "lap" in s:
        return RaceType.LAP
    if "timed" in s or "time" in s:
        return RaceType.TIMED
    if "unlimited" in s:
        return RaceType.UNLIMITED
    return RaceType.UNKNOWN


def build_canonical_live_race_state(
    tracker: Any,
    *,
    elapsed_s: Optional[float] = None,
    telemetry_fresh: bool = True,
    fuel_per_lap_plan: Optional[float] = None,
    lap_time_plan_s: Optional[float] = None,
    recent_fuel_burn_samples: Optional[Sequence[float]] = None,
    recent_clean_lap_times_s: Optional[Sequence[float]] = None,
    pit_loss_s: Optional[float] = None,
    required_stops: Optional[int] = None,
    context_ok: bool = True,
    rules_verified: bool = True,
    driver_reports: Optional[Mapping] = None,
    finishing_lap_semantics: str = "cross_line_after_time",
) -> CanonicalLiveRaceState:
    """Compose ONE canonical live race state from the EXISTING tracker (duck-typed read) + injected
    elapsed time + the pre-race plan + confirmed driver reports. DB-free; never raises. Robust multi-lap
    fuel/pace evidence (a single anomalous lap never drives the value). ``driver_reports`` may carry
    confirmed ``weather`` / ``damage`` / ``penalty`` (each stays driver-reported, never verified)."""
    try:
        def g(name, default=None):
            return getattr(tracker, name, default) if tracker is not None else default

        fields: List[LiveRaceStateField] = []

        def add(name, value, avail, conf, in_fp=True):
            fields.append(LiveRaceStateField(name, value, avail, conf, in_fp))
            return value

        A = LiveRaceStateAvailability
        C = LiveRaceStateConfidence

        rtype = _race_type(g("race_type"))
        current_lap = _int(g("laps_recorded"))
        scheduled_laps = _int(g("laps_in_race"))
        duration_min = _num(g("timed_duration_minutes"))
        race_duration_s = duration_min * 60.0 if duration_min else None

        add("race_type", rtype.value, A.MEASURED, C.HIGH)
        add("current_lap", current_lap, A.MEASURED if current_lap is not None else A.UNAVAILABLE,
            C.HIGH if current_lap is not None else C.NONE)

        # --- fuel (robust: median of recent samples, else tracker avg) ---
        fuel_remaining = _pos_or_none(g("last_fuel"))
        live_burn = _robust_mean(recent_fuel_burn_samples) or _pos(g("avg_fuel_per_lap"))
        add("fuel_remaining_l", fuel_remaining, A.MEASURED if fuel_remaining is not None else A.UNAVAILABLE,
            C.HIGH if fuel_remaining is not None else C.NONE)
        add("fuel_per_lap_live", live_burn, A.DERIVED if live_burn is not None else A.UNAVAILABLE,
            C.MEDIUM if live_burn is not None else C.NONE)

        # --- pace (clean-lap median, else best lap) ---
        clean_median = _median(recent_clean_lap_times_s) if recent_clean_lap_times_s else None
        best_ms = _pos(g("best_lap_ms"))
        lap_time_live = clean_median if clean_median is not None else (best_ms / 1000.0 if best_ms else None)
        consistency = _stddev(recent_clean_lap_times_s) if recent_clean_lap_times_s else None
        add("lap_time_live_s", lap_time_live, A.DERIVED if lap_time_live is not None else A.UNAVAILABLE,
            C.MEDIUM if lap_time_live is not None else C.NONE)

        # --- clock ---
        clock = _build_clock(rtype, current_lap, scheduled_laps, race_duration_s, elapsed_s, lap_time_live,
                             pit_loss_s, finishing_lap_semantics)

        # --- stint / tyre (proxy) ---
        stint_age = _int(g("laps_since_pit")) or _int(g("tyre_age_laps"))
        compound = _norm(g("tyre_compound")) or None
        tyre_deg = _tyre_deg_proxy(recent_clean_lap_times_s)
        stint = StintState(stint_start_lap=(current_lap - stint_age if (current_lap is not None
                                                                        and stint_age is not None) else None),
                           stint_age_laps=stint_age, compound=compound, tyre_deg_per_lap_s=tyre_deg,
                           tyre_deg_is_proxy=True)
        add("compound", compound, A.MEASURED if compound else A.UNAVAILABLE,
            C.MEDIUM if compound else C.NONE)
        add("tyre_deg_per_lap_s", tyre_deg, A.DERIVED if tyre_deg is not None else A.UNAVAILABLE,
            C.LOW if tyre_deg is not None else C.NONE)   # PROXY

        # --- pit ---
        pit = _build_pit(g)
        add("pit_stops_completed", pit.pit_stops_completed,
            A.DERIVED if pit.pit_stops_completed is not None else A.UNAVAILABLE, pit.confidence)

        # --- position ---
        position = _int(g("last_position"))
        add("position", position, A.MEASURED if position else A.UNAVAILABLE,
            C.HIGH if position else C.NONE)

        # --- driver-reported conditions (never verified telemetry) ---
        dr = driver_reports if isinstance(driver_reports, Mapping) else {}
        weather = _norm(dr.get("weather")) or None
        damage = _norm(dr.get("damage")) or None
        penalty = _norm(dr.get("penalty")) or None
        add("weather", weather, A.DRIVER_REPORTED if weather else A.UNAVAILABLE,
            C.LOW if weather else C.NONE)
        add("damage", damage, A.DRIVER_REPORTED if damage else A.UNAVAILABLE,
            C.LOW if damage else C.NONE)

        state = CanonicalLiveRaceState(
            telemetry_fresh=bool(telemetry_fresh), clock=clock, stint=stint, pit=pit,
            fuel_remaining_l=fuel_remaining, fuel_per_lap_plan=_pos(fuel_per_lap_plan),
            fuel_per_lap_live=live_burn, lap_time_plan_s=_pos(lap_time_plan_s),
            lap_time_live_s=lap_time_live, consistency_stddev_s=consistency, position=position,
            car=_norm(g("car_name")), track=_norm(g("track")), layout=_norm(g("layout_id")),
            weather=weather, weather_source=("driver_reported" if weather else ""),
            damage=damage, damage_source=("driver_reported" if damage else ""),
            penalty=penalty, required_stops=_int(required_stops), context_ok=bool(context_ok),
            rules_verified=bool(rules_verified), fields=tuple(fields))
        return _stamp(state)
    except Exception:  # pragma: no cover - defensive
        empty_clock = RaceClockState(RaceType.UNKNOWN, None, None, None, None, None, None, None, None)
        return _stamp(CanonicalLiveRaceState(
            telemetry_fresh=False, clock=empty_clock,
            stint=StintState(None, None, None, None), pit=PitState(PitPhase.UNCERTAIN, None,
                                                                   LiveRaceStateConfidence.NONE),
            fuel_remaining_l=None, fuel_per_lap_plan=None, fuel_per_lap_live=None, lap_time_plan_s=None,
            lap_time_live_s=None, consistency_stddev_s=None, position=None, car="", track="", layout="",
            weather=None, weather_source="", damage=None, damage_source="", penalty=None,
            required_stops=None, context_ok=False, rules_verified=False))


def _stamp(state: CanonicalLiveRaceState) -> CanonicalLiveRaceState:
    return CanonicalLiveRaceState(
        telemetry_fresh=state.telemetry_fresh, clock=state.clock, stint=state.stint, pit=state.pit,
        fuel_remaining_l=state.fuel_remaining_l, fuel_per_lap_plan=state.fuel_per_lap_plan,
        fuel_per_lap_live=state.fuel_per_lap_live, lap_time_plan_s=state.lap_time_plan_s,
        lap_time_live_s=state.lap_time_live_s, consistency_stddev_s=state.consistency_stddev_s,
        position=state.position, car=state.car, track=state.track, layout=state.layout,
        weather=state.weather, weather_source=state.weather_source, damage=state.damage,
        damage_source=state.damage_source, penalty=state.penalty, required_stops=state.required_stops,
        context_ok=state.context_ok, rules_verified=state.rules_verified, fields=state.fields,
        fingerprint=_fp(state.as_payload()))


def _build_clock(rtype, current_lap, scheduled_laps, race_duration_s, elapsed_s, lap_time_live,
                 pit_loss_s, finishing_lap_semantics) -> RaceClockState:
    laps_remaining = None
    remaining_s = None
    expected_completed = None
    additional_changes = None
    if rtype == RaceType.LAP and scheduled_laps is not None and current_lap is not None:
        laps_remaining = max(0, int(scheduled_laps) - int(current_lap))
    if rtype == RaceType.TIMED and race_duration_s is not None:
        el = _num(elapsed_s) or 0.0
        remaining_s = max(0.0, race_duration_s - el)
        if lap_time_live:
            base = project_time_certain(time_remaining_s=remaining_s, lap_time_s=lap_time_live)
            expected_completed = base.expected_completed_laps
            if pit_loss_s:
                withstop = project_time_certain(time_remaining_s=remaining_s, lap_time_s=lap_time_live,
                                                extra_stops=1, pit_loss_s=pit_loss_s)
                if (withstop.expected_completed_laps is not None
                        and expected_completed is not None):
                    additional_changes = withstop.expected_completed_laps < expected_completed
    return RaceClockState(race_type=rtype, current_lap=current_lap, scheduled_laps=scheduled_laps,
                          laps_remaining=laps_remaining, race_duration_s=race_duration_s,
                          elapsed_s=_num(elapsed_s), remaining_s=remaining_s,
                          expected_completed_laps=expected_completed,
                          additional_stop_changes_lapcount=additional_changes,
                          finishing_lap_semantics=finishing_lap_semantics)


def _build_pit(g) -> PitState:
    in_pit = bool(g("in_pit", False))
    conf_raw = _lc(g("pit_state_confidence"))
    stops = _int(g("pit_stops_completed"))
    if in_pit:
        phase = PitPhase.PIT_CONFIRMED
    elif conf_raw in ("high", "medium"):
        phase = PitPhase.NOT_IN_PIT
    elif conf_raw == "low":
        phase = PitPhase.UNCERTAIN
    else:
        phase = PitPhase.NOT_IN_PIT
    conf = {"high": LiveRaceStateConfidence.HIGH, "medium": LiveRaceStateConfidence.MEDIUM,
            "low": LiveRaceStateConfidence.LOW}.get(conf_raw, LiveRaceStateConfidence.MEDIUM)
    return PitState(phase=phase, pit_stops_completed=stops, confidence=conf)


def _tyre_deg_proxy(clean_lap_times: Optional[Sequence[float]]) -> Optional[float]:
    """Proxy tyre degradation = average per-lap lap-time increase across a stint (robust; needs >=4 laps).
    GT7 gives no direct tyre condition, so this is clearly a proxy."""
    if not clean_lap_times:
        return None
    xs = [float(v) for v in clean_lap_times if _num(v) is not None]
    if len(xs) < 4:
        return None
    # linear-ish drift: average of second-half minus first-half, per lap.
    mid = len(xs) // 2
    first = sum(xs[:mid]) / mid
    second = sum(xs[mid:]) / (len(xs) - mid)
    span = (len(xs) - mid + mid) / 2.0
    drift = (second - first) / max(1.0, span)
    return round(drift, 4) if drift > 0 else 0.0


def _robust_mean(samples) -> Optional[float]:
    if not samples:
        return None
    xs = [float(v) for v in samples if _pos(v) is not None]
    if not xs:
        return None
    if len(xs) >= 3:
        # drop the single most extreme sample (anomalous-lap robustness)
        med = _median(xs)
        xs_sorted = sorted(xs, key=lambda v: abs(v - med))
        xs = xs_sorted[:-1] if len(xs_sorted) > 3 else xs_sorted
    return sum(xs) / len(xs)


def _stddev(samples) -> Optional[float]:
    if not samples:
        return None
    xs = [float(v) for v in samples if _num(v) is not None]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return round(math.sqrt(sum((v - m) ** 2 for v in xs) / len(xs)), 4)


def _int(x) -> Optional[int]:
    v = _num(x)
    return int(v) if v is not None else None


def _pos_or_none(x) -> Optional[float]:
    v = _num(x)
    return v if (v is not None and v >= 0) else None


# --------------------------------------------------------------------------- #
# Evaluation cadence
# --------------------------------------------------------------------------- #
class StrategyEvaluationTrigger(str, Enum):
    LAP_COMPLETION = "lap_completion"
    CONFIRMED_PIT_EVENT = "confirmed_pit_event"
    MATERIAL_FUEL_CHANGE = "material_fuel_change"
    MATERIAL_PACE_CHANGE = "material_pace_change"
    TYRE_CROSSOVER_CHANGE = "tyre_crossover_change"
    REMAINING_TIME_THRESHOLD = "remaining_time_threshold"
    CONFIRMED_DRIVER_REPORT = "confirmed_driver_report"
    EVENT_RULE_RISK = "event_rule_risk"
    EXPLICIT_PTT_REQUEST = "explicit_ptt_request"
    NONE = "none"


@dataclass(frozen=True)
class LiveStrategyEvaluationContext:
    """Immutable per-invalidation context (event + Race Plan) resolved OUTSIDE packet processing. The
    strategy runtime reuses this and never rebuilds it per packet."""
    cycle_id: str = ""
    activity_id: str = ""
    event_context_digest: str = ""
    race_plan_fingerprint: str = ""
    setup_fingerprint: str = ""

    def key(self) -> Tuple[str, str, str, str, str]:
        return (self.cycle_id, self.activity_id, self.event_context_digest, self.race_plan_fingerprint,
                self.setup_fingerprint)


class EvaluationCadence:
    """Deterministic cadence gate: strategy is (re)evaluated only at bounded triggers, never per packet.
    ``last_lap`` / thresholds are supplied by the caller; timing is injected (monotonic seconds)."""

    def __init__(self, *, min_interval_s: float = 5.0):
        self._min_interval = float(min_interval_s)
        self._last_lap: Optional[int] = None
        self._last_pit_stops: Optional[int] = None
        self._last_eval_mono: Optional[float] = None

    def triggers(self, state: CanonicalLiveRaceState, *, now: float,
                 ptt_request: bool = False, driver_report: bool = False) -> Tuple[StrategyEvaluationTrigger, ...]:
        out: List[StrategyEvaluationTrigger] = []
        try:
            now = float(now)
            lap = state.clock.current_lap
            if lap is not None and lap != self._last_lap:
                out.append(StrategyEvaluationTrigger.LAP_COMPLETION)
                self._last_lap = lap
            stops = state.pit.pit_stops_completed
            if stops is not None and self._last_pit_stops is not None and stops > self._last_pit_stops \
                    and state.pit.phase in (PitPhase.STOP_COMPLETED, PitPhase.PIT_CONFIRMED,
                                            PitPhase.PIT_EXIT):
                out.append(StrategyEvaluationTrigger.CONFIRMED_PIT_EVENT)
            if stops is not None:
                self._last_pit_stops = stops
            if ptt_request:
                out.append(StrategyEvaluationTrigger.EXPLICIT_PTT_REQUEST)
            if driver_report:
                out.append(StrategyEvaluationTrigger.CONFIRMED_DRIVER_REPORT)
            return tuple(out)
        except Exception:  # pragma: no cover - defensive
            return tuple(out)


def canonical_live_race_state_versions() -> dict:
    return {"canonical_live_race_state": CANONICAL_LIVE_RACE_STATE_VERSION}
