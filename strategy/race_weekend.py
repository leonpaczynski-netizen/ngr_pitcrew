"""Immersive NGR Race Weekend experience (Program 2, Phase 50).

The official race weekend is the CLIMAX of the preparation cycle — it is built from the accumulated
Practice evidence, never rebuilt from scratch on arrival. This module assembles the ceremonial,
high-stakes weekend views: final arrival, NGR driver briefing, virtual scrutineering, the Chief
Engineer final meeting, a low-density qualifying experience, the race briefing, the race runtime
priority profile, and the post-race debrief. Briefings require explicit acknowledgement.

It reuses (references, never re-implements) the live-advisory / shadow / voice gates: voice remains
disabled by default and may not bypass VOICE_ELIGIBLE. No pit/tyre/fuel command is ever issued
automatically; the app never fabricates checks it cannot perform.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. Authors no setup value.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence, Tuple

RACE_WEEKEND_VERSION = "race_weekend_v1"
RACE_WEEKEND_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{RACE_WEEKEND_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class RaceWeekendPhase(str, Enum):
    FINAL_ARRIVAL = "final_arrival"
    DRIVER_BRIEFING = "driver_briefing"
    GARAGE_READINESS = "garage_readiness"
    FINAL_ENGINEERING_MEETING = "final_engineering_meeting"
    OFFICIAL_PRACTICE = "official_practice"
    QUALIFYING_PREP = "qualifying_prep"
    QUALIFYING = "qualifying"
    QUALIFYING_REVIEW = "qualifying_review"
    RACE_STRATEGY_CONFIRMATION = "race_strategy_confirmation"
    GRID_READINESS = "grid_readiness"
    RACE = "race"
    POST_RACE_DEBRIEF = "post_race_debrief"
    EVENT_COMPLETE = "event_complete"


class ScrutineeringVerdict(str, Enum):
    CLEARED = "cleared"
    CLEARED_WITH_WARNINGS = "cleared_with_warnings"
    GARAGE_HOLD = "garage_hold"
    UNVERIFIABLE = "unverifiable"
    NOT_APPLICABLE = "not_applicable"


class CheckStatus(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    UNVERIFIABLE = "unverifiable"    # cannot be checked here (do not fabricate a result)
    NOT_APPLICABLE = "not_applicable"


# ---------------------------------------------------------------------------
# Final arrival
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FinalArrivalSummary:
    """A read-only snapshot of the preparation programme at race-weekend arrival. Draws from the
    accumulated evidence; it never rebuilds setup or strategy."""
    event_name: str
    series: str
    round_label: str
    track: str
    layout: str
    driver: str
    team: str
    sessions_completed: int
    total_valid_laps: int
    setup_development_summary: str
    driver_development_summary: str
    tyre_model_confidence: str
    fuel_model_confidence: str
    strategy_confidence: str
    qualifying_setup_fingerprint: str
    race_setup_fingerprint: str
    unresolved_risks: Tuple[str, ...]
    readiness_blockers: Tuple[str, ...]
    next_required_action: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {
            "event_name": _norm(self.event_name), "series": _norm(self.series),
            "round": _norm(self.round_label), "track": _norm(self.track), "layout": _norm(self.layout),
            "driver": _norm(self.driver), "team": _norm(self.team),
            "sessions_completed": int(self.sessions_completed),
            "total_valid_laps": int(self.total_valid_laps),
            "setup_development_summary": _norm(self.setup_development_summary),
            "driver_development_summary": _norm(self.driver_development_summary),
            "tyre_model_confidence": _norm(self.tyre_model_confidence),
            "fuel_model_confidence": _norm(self.fuel_model_confidence),
            "strategy_confidence": _norm(self.strategy_confidence),
            "qualifying_setup_fingerprint": _norm(self.qualifying_setup_fingerprint),
            "race_setup_fingerprint": _norm(self.race_setup_fingerprint),
            "unresolved_risks": sorted(_norm(s) for s in self.unresolved_risks if _norm(s)),
            "readiness_blockers": sorted(_norm(s) for s in self.readiness_blockers if _norm(s)),
            "next_required_action": _norm(self.next_required_action)}


def build_final_arrival(**kw) -> FinalArrivalSummary:
    fa = FinalArrivalSummary(
        event_name=kw.get("event_name", ""), series=kw.get("series", ""),
        round_label=kw.get("round_label", ""), track=kw.get("track", ""), layout=kw.get("layout", ""),
        driver=kw.get("driver", ""), team=kw.get("team", ""),
        sessions_completed=int(kw.get("sessions_completed", 0)),
        total_valid_laps=int(kw.get("total_valid_laps", 0)),
        setup_development_summary=kw.get("setup_development_summary", ""),
        driver_development_summary=kw.get("driver_development_summary", ""),
        tyre_model_confidence=kw.get("tyre_model_confidence", ""),
        fuel_model_confidence=kw.get("fuel_model_confidence", ""),
        strategy_confidence=kw.get("strategy_confidence", ""),
        qualifying_setup_fingerprint=kw.get("qualifying_setup_fingerprint", ""),
        race_setup_fingerprint=kw.get("race_setup_fingerprint", ""),
        unresolved_risks=tuple(kw.get("unresolved_risks", ())),
        readiness_blockers=tuple(kw.get("readiness_blockers", ())),
        next_required_action=kw.get("next_required_action", ""), fingerprint="")
    return FinalArrivalSummary(**{**fa.__dict__, "fingerprint": _fp(fa.as_payload())})


# ---------------------------------------------------------------------------
# Driver briefing (explicit acknowledgement required)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BriefingItem:
    topic: str
    detail: str = ""

    def as_payload(self) -> dict:
        return {"topic": _norm(self.topic), "detail": _norm(self.detail)}


@dataclass(frozen=True)
class DriverBriefing:
    """Only event-applicable rules are included (never fabricated). Must be acknowledged before grid."""
    title: str
    items: Tuple[BriefingItem, ...]
    acknowledged: bool = False
    fingerprint: str = ""

    def as_payload(self) -> dict:
        # acknowledgement is runtime state; it is NOT part of the briefing's semantic fingerprint
        return {"title": _norm(self.title), "items": [i.as_payload() for i in self.items]}


def build_driver_briefing(title: str, items: Sequence[BriefingItem]) -> DriverBriefing:
    b = DriverBriefing(title=_norm(title), items=tuple(items), acknowledged=False, fingerprint="")
    return DriverBriefing(title=b.title, items=b.items, acknowledged=False, fingerprint=_fp(b.as_payload()))


def acknowledge_briefing(briefing: DriverBriefing) -> DriverBriefing:
    """Explicit acknowledgement — returns a NEW briefing marked acknowledged (fingerprint unchanged:
    acknowledgement is runtime state, not semantic content)."""
    return DriverBriefing(title=briefing.title, items=briefing.items, acknowledged=True,
                          fingerprint=briefing.fingerprint)


# ---------------------------------------------------------------------------
# Virtual scrutineering
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ScrutineeringCheck:
    name: str
    status: CheckStatus
    detail: str = ""

    def as_payload(self) -> dict:
        return {"name": _norm(self.name), "status": self.status.value, "detail": _norm(self.detail)}


@dataclass(frozen=True)
class VirtualScrutineering:
    checks: Tuple[ScrutineeringCheck, ...]
    verdict: ScrutineeringVerdict
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"checks": [c.as_payload() for c in sorted(self.checks, key=lambda c: _norm(c.name))],
                "verdict": self.verdict.value}


def _aggregate_verdict(checks: Sequence[ScrutineeringCheck]) -> ScrutineeringVerdict:
    if not checks:
        return ScrutineeringVerdict.NOT_APPLICABLE
    statuses = [c.status for c in checks]
    if CheckStatus.FAIL in statuses:
        return ScrutineeringVerdict.GARAGE_HOLD
    non_na = [s for s in statuses if s != CheckStatus.NOT_APPLICABLE]
    if not non_na:
        return ScrutineeringVerdict.NOT_APPLICABLE
    if CheckStatus.UNVERIFIABLE in statuses:
        return ScrutineeringVerdict.UNVERIFIABLE
    if CheckStatus.WARN in statuses:
        return ScrutineeringVerdict.CLEARED_WITH_WARNINGS
    return ScrutineeringVerdict.CLEARED


def build_scrutineering(checks: Sequence[ScrutineeringCheck]) -> VirtualScrutineering:
    ordered = tuple(sorted(checks, key=lambda c: _norm(c.name)))
    verdict = _aggregate_verdict(ordered)
    vs = VirtualScrutineering(checks=ordered, verdict=verdict, fingerprint="")
    return VirtualScrutineering(checks=vs.checks, verdict=vs.verdict, fingerprint=_fp(vs.as_payload()))


# ---------------------------------------------------------------------------
# Chief Engineer final meeting
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ChiefEngineerFinalMeeting:
    event_objective: str
    qualifying_objective: str
    race_objective: str
    qualifying_setup_fingerprint: str
    race_setup_fingerprint: str
    protected_strengths: Tuple[str, ...]
    known_weaknesses: Tuple[str, ...]
    driver_focus: str
    tyre_plan: str
    fuel_plan: str
    strategy_summary: str
    contingency_plan: str
    voice_state: str
    abort_replan_conditions: Tuple[str, ...]
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {
            "event_objective": _norm(self.event_objective),
            "qualifying_objective": _norm(self.qualifying_objective),
            "race_objective": _norm(self.race_objective),
            "qualifying_setup_fingerprint": _norm(self.qualifying_setup_fingerprint),
            "race_setup_fingerprint": _norm(self.race_setup_fingerprint),
            "protected_strengths": sorted(_norm(s) for s in self.protected_strengths if _norm(s)),
            "known_weaknesses": sorted(_norm(s) for s in self.known_weaknesses if _norm(s)),
            "driver_focus": _norm(self.driver_focus), "tyre_plan": _norm(self.tyre_plan),
            "fuel_plan": _norm(self.fuel_plan), "strategy_summary": _norm(self.strategy_summary),
            "contingency_plan": _norm(self.contingency_plan), "voice_state": _norm(self.voice_state),
            "abort_replan_conditions": sorted(_norm(s) for s in self.abort_replan_conditions if _norm(s))}


def build_chief_engineer_meeting(**kw) -> ChiefEngineerFinalMeeting:
    m = ChiefEngineerFinalMeeting(
        event_objective=kw.get("event_objective", ""), qualifying_objective=kw.get("qualifying_objective", ""),
        race_objective=kw.get("race_objective", ""),
        qualifying_setup_fingerprint=kw.get("qualifying_setup_fingerprint", ""),
        race_setup_fingerprint=kw.get("race_setup_fingerprint", ""),
        protected_strengths=tuple(kw.get("protected_strengths", ())),
        known_weaknesses=tuple(kw.get("known_weaknesses", ())),
        driver_focus=kw.get("driver_focus", ""), tyre_plan=kw.get("tyre_plan", ""),
        fuel_plan=kw.get("fuel_plan", ""), strategy_summary=kw.get("strategy_summary", ""),
        contingency_plan=kw.get("contingency_plan", ""), voice_state=kw.get("voice_state", "disabled"),
        abort_replan_conditions=tuple(kw.get("abort_replan_conditions", ())), fingerprint="")
    return ChiefEngineerFinalMeeting(**{**m.__dict__, "fingerprint": _fp(m.as_payload())})


# ---------------------------------------------------------------------------
# Qualifying + Race briefings
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class QualifyingExperience:
    """Deliberately low-density: setup confirmation, tyre/fuel, out-lap plan, attempts, target lap,
    critical corners, concise advisories only."""
    setup_confirmation: str
    tyre: str
    fuel: str
    out_lap_plan: str
    available_attempts: int
    critical_corners: Tuple[str, ...]
    target_lap: str
    concise_advisories: Tuple[str, ...]
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"setup_confirmation": _norm(self.setup_confirmation), "tyre": _norm(self.tyre),
                "fuel": _norm(self.fuel), "out_lap_plan": _norm(self.out_lap_plan),
                "available_attempts": int(self.available_attempts),
                "critical_corners": [_norm(c) for c in self.critical_corners],
                "target_lap": _norm(self.target_lap),
                "concise_advisories": [_norm(a) for a in self.concise_advisories]}


def build_qualifying_experience(**kw) -> QualifyingExperience:
    q = QualifyingExperience(
        setup_confirmation=kw.get("setup_confirmation", ""), tyre=kw.get("tyre", ""),
        fuel=kw.get("fuel", ""), out_lap_plan=kw.get("out_lap_plan", ""),
        available_attempts=int(kw.get("available_attempts", 0)),
        critical_corners=tuple(kw.get("critical_corners", ())), target_lap=kw.get("target_lap", ""),
        concise_advisories=tuple(kw.get("concise_advisories", ())), fingerprint="")
    return QualifyingExperience(**{**q.__dict__, "fingerprint": _fp(q.as_payload())})


@dataclass(frozen=True)
class QualifyingReview:
    grid_position: str
    best_lap: str
    representative_performance: str
    sector_review: Tuple[str, ...]
    corner_review: Tuple[str, ...]
    setup_result: str
    driver_result: str
    race_setup_reconsideration: bool
    strategy_reconsideration: bool
    post_qualifying_restrictions: str
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"grid_position": _norm(self.grid_position), "best_lap": _norm(self.best_lap),
                "representative_performance": _norm(self.representative_performance),
                "sector_review": [_norm(s) for s in self.sector_review],
                "corner_review": [_norm(c) for c in self.corner_review],
                "setup_result": _norm(self.setup_result), "driver_result": _norm(self.driver_result),
                "race_setup_reconsideration": bool(self.race_setup_reconsideration),
                "strategy_reconsideration": bool(self.strategy_reconsideration),
                "post_qualifying_restrictions": _norm(self.post_qualifying_restrictions)}


def build_qualifying_review(**kw) -> QualifyingReview:
    r = QualifyingReview(
        grid_position=kw.get("grid_position", ""), best_lap=kw.get("best_lap", ""),
        representative_performance=kw.get("representative_performance", ""),
        sector_review=tuple(kw.get("sector_review", ())), corner_review=tuple(kw.get("corner_review", ())),
        setup_result=kw.get("setup_result", ""), driver_result=kw.get("driver_result", ""),
        race_setup_reconsideration=bool(kw.get("race_setup_reconsideration", False)),
        strategy_reconsideration=bool(kw.get("strategy_reconsideration", False)),
        post_qualifying_restrictions=kw.get("post_qualifying_restrictions", ""), fingerprint="")
    return QualifyingReview(**{**r.__dict__, "fingerprint": _fp(r.as_payload())})


@dataclass(frozen=True)
class RaceBriefing:
    starting_tyre: str
    starting_fuel: str
    primary_strategy: str
    fallback_strategy: str
    pit_windows: Tuple[str, ...]
    tyre_target: str
    fuel_target: str
    first_lap_priorities: Tuple[str, ...]
    weather_response: str
    traffic_considerations: str
    replan_conditions: Tuple[str, ...]
    setup_confirmation: str
    voice_state: str
    final_blockers: Tuple[str, ...]
    acknowledged: bool = False
    grid_ready: bool = False
    fingerprint: str = ""

    def as_payload(self) -> dict:
        # acknowledgement / grid-ready are runtime state; excluded from the semantic fingerprint
        return {"starting_tyre": _norm(self.starting_tyre), "starting_fuel": _norm(self.starting_fuel),
                "primary_strategy": _norm(self.primary_strategy),
                "fallback_strategy": _norm(self.fallback_strategy),
                "pit_windows": [_norm(p) for p in self.pit_windows], "tyre_target": _norm(self.tyre_target),
                "fuel_target": _norm(self.fuel_target),
                "first_lap_priorities": [_norm(p) for p in self.first_lap_priorities],
                "weather_response": _norm(self.weather_response),
                "traffic_considerations": _norm(self.traffic_considerations),
                "replan_conditions": sorted(_norm(c) for c in self.replan_conditions if _norm(c)),
                "setup_confirmation": _norm(self.setup_confirmation), "voice_state": _norm(self.voice_state),
                "final_blockers": sorted(_norm(b) for b in self.final_blockers if _norm(b))}


def build_race_briefing(**kw) -> RaceBriefing:
    b = RaceBriefing(
        starting_tyre=kw.get("starting_tyre", ""), starting_fuel=kw.get("starting_fuel", ""),
        primary_strategy=kw.get("primary_strategy", ""), fallback_strategy=kw.get("fallback_strategy", ""),
        pit_windows=tuple(kw.get("pit_windows", ())), tyre_target=kw.get("tyre_target", ""),
        fuel_target=kw.get("fuel_target", ""), first_lap_priorities=tuple(kw.get("first_lap_priorities", ())),
        weather_response=kw.get("weather_response", ""), traffic_considerations=kw.get("traffic_considerations", ""),
        replan_conditions=tuple(kw.get("replan_conditions", ())), setup_confirmation=kw.get("setup_confirmation", ""),
        voice_state=kw.get("voice_state", "disabled"), final_blockers=tuple(kw.get("final_blockers", ())),
        acknowledged=False, grid_ready=False, fingerprint="")
    return RaceBriefing(**{**b.__dict__, "fingerprint": _fp(b.as_payload())})


def acknowledge_race_briefing(briefing: RaceBriefing, *, grid_ready: bool = False) -> RaceBriefing:
    """Explicit strategy acknowledgement + grid-readiness confirmation. Runtime state; fingerprint
    unchanged. Grid readiness requires acknowledgement first."""
    ack = True
    return RaceBriefing(**{**briefing.__dict__, "acknowledged": ack,
                          "grid_ready": bool(grid_ready and ack)})


# ---------------------------------------------------------------------------
# Race runtime priority profile (references advisory/voice gates; reimplements none)
# ---------------------------------------------------------------------------

# fixed deterministic priority order for race runtime advisories
RACE_RUNTIME_PRIORITY: Tuple[str, ...] = (
    "safety",
    "setup_or_context_mismatch",
    "car_condition",
    "race_plan_status",
    "tyre_and_fuel_awareness",
    "pit_window_awareness",
    "strategy_viability",
    "restrained_coaching",
    "information_progress",
)


@dataclass(frozen=True)
class RaceRuntimeProfile:
    priority_order: Tuple[str, ...]
    voice_enabled: bool
    voice_eligible: bool
    issues_pit_commands: bool          # always False — no unsupported pit/tyre/fuel commands
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"priority_order": list(self.priority_order), "voice_enabled": bool(self.voice_enabled),
                "voice_eligible": bool(self.voice_eligible),
                "issues_pit_commands": bool(self.issues_pit_commands)}


def build_race_runtime_profile(*, voice_enabled: bool = False,
                               voice_eligible: bool = False) -> RaceRuntimeProfile:
    """Race runtime priority profile. Voice stays disabled by default and can only speak when both
    enabled AND voice-eligible (the VOICE_ELIGIBLE gate lives in shadow_advisory.voice_gate_allows).
    Never issues automatic pit/tyre/fuel commands."""
    p = RaceRuntimeProfile(priority_order=RACE_RUNTIME_PRIORITY, voice_enabled=bool(voice_enabled),
                           voice_eligible=bool(voice_eligible), issues_pit_commands=False, fingerprint="")
    return RaceRuntimeProfile(**{**p.__dict__, "fingerprint": _fp(p.as_payload())})


# ---------------------------------------------------------------------------
# Post-race debrief
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PostRaceDebrief:
    result: str
    race_pace: str
    consistency: str
    tyre_performance: str
    fuel_performance: str
    strategy_execution: str
    pit_performance: str
    incidents: Tuple[str, ...]
    penalties: Tuple[str, ...]
    setup_performance: str
    driver_performance: str
    key_corner_findings: Tuple[str, ...]
    successful_decisions: Tuple[str, ...]
    failed_decisions: Tuple[str, ...]
    unexpected_outcomes: Tuple[str, ...]
    setup_promotion_or_rollback: str
    driver_development_progress: str
    strategy_calibration: str
    lessons_for_next_event: Tuple[str, ...]
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {
            "result": _norm(self.result), "race_pace": _norm(self.race_pace),
            "consistency": _norm(self.consistency), "tyre_performance": _norm(self.tyre_performance),
            "fuel_performance": _norm(self.fuel_performance),
            "strategy_execution": _norm(self.strategy_execution), "pit_performance": _norm(self.pit_performance),
            "incidents": [_norm(i) for i in self.incidents], "penalties": [_norm(p) for p in self.penalties],
            "setup_performance": _norm(self.setup_performance),
            "driver_performance": _norm(self.driver_performance),
            "key_corner_findings": [_norm(c) for c in self.key_corner_findings],
            "successful_decisions": [_norm(d) for d in self.successful_decisions],
            "failed_decisions": [_norm(d) for d in self.failed_decisions],
            "unexpected_outcomes": [_norm(u) for u in self.unexpected_outcomes],
            "setup_promotion_or_rollback": _norm(self.setup_promotion_or_rollback),
            "driver_development_progress": _norm(self.driver_development_progress),
            "strategy_calibration": _norm(self.strategy_calibration),
            "lessons_for_next_event": [_norm(l) for l in self.lessons_for_next_event]}


def build_post_race_debrief(**kw) -> PostRaceDebrief:
    d = PostRaceDebrief(
        result=kw.get("result", ""), race_pace=kw.get("race_pace", ""), consistency=kw.get("consistency", ""),
        tyre_performance=kw.get("tyre_performance", ""), fuel_performance=kw.get("fuel_performance", ""),
        strategy_execution=kw.get("strategy_execution", ""), pit_performance=kw.get("pit_performance", ""),
        incidents=tuple(kw.get("incidents", ())), penalties=tuple(kw.get("penalties", ())),
        setup_performance=kw.get("setup_performance", ""), driver_performance=kw.get("driver_performance", ""),
        key_corner_findings=tuple(kw.get("key_corner_findings", ())),
        successful_decisions=tuple(kw.get("successful_decisions", ())),
        failed_decisions=tuple(kw.get("failed_decisions", ())),
        unexpected_outcomes=tuple(kw.get("unexpected_outcomes", ())),
        setup_promotion_or_rollback=kw.get("setup_promotion_or_rollback", ""),
        driver_development_progress=kw.get("driver_development_progress", ""),
        strategy_calibration=kw.get("strategy_calibration", ""),
        lessons_for_next_event=tuple(kw.get("lessons_for_next_event", ())), fingerprint="")
    return PostRaceDebrief(**{**d.__dict__, "fingerprint": _fp(d.as_payload())})
