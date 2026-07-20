"""Event Preparation Cycle — canonical authority for one upcoming NGR race round (Program 2, Phase 48).

An NGR race event is not a self-contained weekend. Between championship rounds a driver runs a
*preparation cycle* that may span an evening or several weeks: briefings, baseline runs, setup
experiments, coaching runs, tyre/fuel tests, qualifying and race simulations, a setup lock-in, a
strategy meeting, then the official race weekend and a debrief. Every Practice session collected for
the *same upcoming round* belongs to the *same cumulative engineering programme*; the system must never
treat those sessions as disconnected mini-events.

This module owns the *preparation-programme* identity and timeline (Layer B in
``docs/NGR_EVENT_PREPARATION_ARCHITECTURE.md``). It groups typed, ordered activities under one round and
exposes readiness and progress as a deterministic *view*. It references — never redefines — the
immutable event environment (Layer A), the execution authorities (Layer C) and the outcome/learning
authorities (Layer D). It creates no setup value, binds no session, writes nothing.

Flexible duration: an evening, several days, a week, three weeks, a month, or any gap between rounds is
valid. A long gap with no activity is NOT an error and never auto-abandons or auto-completes a cycle.

Determinism / purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock. The
build function is pure — *viewing or refreshing never advances cycle state*; persisted activity states
are inputs, and the derived transitions/readiness are recomputed from those inputs. Scheduled dates and
official session times are semantic event data and enter the fingerprint; a countdown value (days until
race) is runtime *display* state computed from an injected ``now_date`` and is excluded from the
fingerprint. Never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

EVENT_PREPARATION_CYCLE_VERSION = "event_preparation_cycle_v1"
EVENT_PREPARATION_CYCLE_SCHEMA = 1


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{EVENT_PREPARATION_CYCLE_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


def _as_date(v) -> Optional[date]:
    """Parse an ISO ``YYYY-MM-DD`` string to a date; return None on anything unparseable.

    Deterministic and offline — never touches the wall clock. Accepts a date, a full ISO datetime
    string (date part taken) or an empty/None value (None)."""
    if isinstance(v, date):
        return v
    s = _norm(v)
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None


def _iso(v) -> str:
    d = _as_date(v)
    return d.isoformat() if d is not None else ""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PreparationCycleState(str, Enum):
    """Coarse lifecycle bucket of the whole cycle (distinct from the fine-grained current phase)."""
    NOT_STARTED = "not_started"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETE = "complete"
    ABANDONED = "abandoned"


class PreparationPhase(str, Enum):
    """Fine-grained current focus of the preparation cycle. Not every event uses every phase; a
    skipped phase is declared explicitly by the format profile."""
    EVENT_OPEN = "event_open"
    INITIAL_BRIEFING = "initial_briefing"
    BASELINE_ESTABLISHMENT = "baseline_establishment"
    SETUP_DEVELOPMENT = "setup_development"
    DRIVER_DEVELOPMENT = "driver_development"
    TYRE_AND_FUEL_MODELLING = "tyre_and_fuel_modelling"
    QUALIFYING_DEVELOPMENT = "qualifying_development"
    RACE_SIMULATION = "race_simulation"
    ENGINEERING_CONVERGENCE = "engineering_convergence"
    SETUP_LOCK_IN = "setup_lock_in"
    STRATEGY_FINALISATION = "strategy_finalisation"
    RACE_WEEK_READY = "race_week_ready"
    OFFICIAL_EVENT_ACTIVE = "official_event_active"
    POST_RACE_REVIEW = "post_race_review"
    COMPLETE = "complete"
    PAUSED = "paused"
    ABANDONED = "abandoned"


# canonical phase order for timeline rendering / progression comparison
PHASE_ORDER: Tuple[PreparationPhase, ...] = (
    PreparationPhase.EVENT_OPEN,
    PreparationPhase.INITIAL_BRIEFING,
    PreparationPhase.BASELINE_ESTABLISHMENT,
    PreparationPhase.SETUP_DEVELOPMENT,
    PreparationPhase.DRIVER_DEVELOPMENT,
    PreparationPhase.TYRE_AND_FUEL_MODELLING,
    PreparationPhase.QUALIFYING_DEVELOPMENT,
    PreparationPhase.RACE_SIMULATION,
    PreparationPhase.ENGINEERING_CONVERGENCE,
    PreparationPhase.SETUP_LOCK_IN,
    PreparationPhase.STRATEGY_FINALISATION,
    PreparationPhase.RACE_WEEK_READY,
    PreparationPhase.OFFICIAL_EVENT_ACTIVE,
    PreparationPhase.POST_RACE_REVIEW,
    PreparationPhase.COMPLETE,
)


class PreparationActivityType(str, Enum):
    """Reusable NGR preparation activities. Composable — never a hard-coded series format."""
    EVENT_BRIEFING = "event_briefing"
    TECHNICAL_READINESS = "technical_readiness"
    INSTALLATION_RUN = "installation_run"
    BASELINE_PRACTICE = "baseline_practice"
    SETUP_EXPERIMENT = "setup_experiment"
    COACHING_RUN = "coaching_run"
    TYRE_TEST = "tyre_test"
    FUEL_TEST = "fuel_test"
    GEARING_TEST = "gearing_test"
    QUALIFYING_SIMULATION = "qualifying_simulation"
    LONG_RACE_RUN = "long_race_run"
    STRATEGY_VALIDATION_RUN = "strategy_validation_run"
    FINAL_SETUP_CONFIRMATION = "final_setup_confirmation"
    FREE_PRACTICE = "free_practice"
    OFFICIAL_PRACTICE = "official_practice"
    QUALIFYING_BRIEFING = "qualifying_briefing"
    QUALIFYING = "qualifying"
    QUALIFYING_REVIEW = "qualifying_review"
    RACE_STRATEGY_MEETING = "race_strategy_meeting"
    RACE_BRIEFING = "race_briefing"
    RACE = "race"
    POST_RACE_DEBRIEF = "post_race_debrief"


# activity types that produce cumulative Practice engineering evidence when a valid session binds
PRACTICE_EVIDENCE_TYPES: frozenset = frozenset({
    PreparationActivityType.BASELINE_PRACTICE,
    PreparationActivityType.SETUP_EXPERIMENT,
    PreparationActivityType.COACHING_RUN,
    PreparationActivityType.TYRE_TEST,
    PreparationActivityType.FUEL_TEST,
    PreparationActivityType.GEARING_TEST,
    PreparationActivityType.QUALIFYING_SIMULATION,
    PreparationActivityType.LONG_RACE_RUN,
    PreparationActivityType.STRATEGY_VALIDATION_RUN,
    PreparationActivityType.FINAL_SETUP_CONFIRMATION,
    PreparationActivityType.FREE_PRACTICE,
    PreparationActivityType.OFFICIAL_PRACTICE,
})

# official (climax) activity types — the Race Weekend, consumed not re-developed
OFFICIAL_ACTIVITY_TYPES: frozenset = frozenset({
    PreparationActivityType.OFFICIAL_PRACTICE,
    PreparationActivityType.QUALIFYING,
    PreparationActivityType.RACE,
})


class PreparationActivityState(str, Enum):
    PLANNED = "planned"
    OPTIONAL_PENDING = "optional_pending"
    READY = "ready"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"
    BLOCKED = "blocked"


# terminal states: the activity will not run in this cycle
_TERMINAL_STATES: frozenset = frozenset({
    PreparationActivityState.COMPLETED,
    PreparationActivityState.SKIPPED,
    PreparationActivityState.CANCELLED,
})


class PreparationTransitionDecision(str, Enum):
    READY = "ready"
    BLOCKED = "blocked"
    SCHEDULED_LATER = "scheduled_later"
    OPTIONAL = "optional"
    AWAITING_DRIVER_CONFIRMATION = "awaiting_driver_confirmation"
    AWAITING_BRIEFING = "awaiting_briefing"
    AWAITING_SETUP = "awaiting_setup"
    AWAITING_TELEMETRY = "awaiting_telemetry"
    AWAITING_SESSION_BINDING = "awaiting_session_binding"
    AWAITING_FEEDBACK = "awaiting_feedback"
    AWAITING_DEBRIEF = "awaiting_debrief"
    MORE_EVIDENCE_REQUIRED = "more_evidence_required"
    CONFIDENCE_SUFFICIENT = "confidence_sufficient"
    SKIPPED_BY_PROFILE = "skipped_by_profile"
    CANCELLED = "cancelled"
    RESCHEDULED = "rescheduled"
    COMPLETED = "completed"


class OfficialSessionType(str, Enum):
    OFFICIAL_PRACTICE = "official_practice"
    QUALIFYING = "qualifying"
    RACE = "race"


class ReadinessLevel(str, Enum):
    """Readiness of a single preparation dimension. Meaning is carried by the tag, never colour alone."""
    UNKNOWN = "unknown"
    MISSING = "missing"
    DEVELOPING = "developing"
    ADEQUATE = "adequate"
    STRONG = "strong"
    NOT_APPLICABLE = "not_applicable"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OfficialSession:
    """A scheduled official (climax) session. Times are semantic event data (enter the fingerprint)."""
    session_type: OfficialSessionType
    scheduled_date: str = ""      # ISO YYYY-MM-DD
    scheduled_time: str = ""      # free-form local time label, semantic
    label: str = ""

    def as_payload(self) -> dict:
        return {"type": self.session_type.value, "date": _iso(self.scheduled_date),
                "time": _norm(self.scheduled_time), "label": _norm(self.label)}


@dataclass(frozen=True)
class PreparationDeadline:
    """A programme deadline. NGR-neutral: advisory, mandatory, setup-lock, quali-lock, race-lock, etc.
    Parc fermé is NOT assumed universal — its presence is declared by the profile, not hard-coded."""
    kind: str                      # e.g. "setup_lock" | "strategy_final" | "qualifying_lock" | "race_lock"
    deadline_date: str = ""        # ISO YYYY-MM-DD
    mandatory: bool = False
    label: str = ""

    def as_payload(self) -> dict:
        return {"kind": _lc(self.kind), "date": _iso(self.deadline_date),
                "mandatory": bool(self.mandatory), "label": _norm(self.label)}


@dataclass(frozen=True)
class EventMilestone:
    """A dated point on the preparation timeline (event open, practice week, lock, quali, race...)."""
    name: str
    milestone_date: str = ""       # ISO YYYY-MM-DD (may be empty for undated activities)
    kind: str = ""

    def as_payload(self) -> dict:
        return {"name": _norm(self.name), "date": _iso(self.milestone_date), "kind": _lc(self.kind)}


@dataclass(frozen=True)
class EventFormatProfile:
    """Configurable NGR event format. Declares which phases apply, which are explicitly skipped, the
    deadlines, and whether a post-lock setup restriction (parc-fermé style) is in force. Never encodes
    a specific real-world series' rules."""
    profile_id: str
    label: str = ""
    included_phases: Tuple[PreparationPhase, ...] = field(default_factory=tuple)
    skipped_phases: Tuple[PreparationPhase, ...] = field(default_factory=tuple)
    deadlines: Tuple[PreparationDeadline, ...] = field(default_factory=tuple)
    setup_restriction_after_lock: bool = False
    official_sessions_expected: Tuple[OfficialSessionType, ...] = field(default_factory=tuple)

    def as_payload(self) -> dict:
        return {
            "profile_id": _lc(self.profile_id),
            "label": _norm(self.label),
            "included_phases": [p.value for p in self.included_phases],
            "skipped_phases": [p.value for p in self.skipped_phases],
            "deadlines": [d.as_payload() for d in self.deadlines],
            "setup_restriction_after_lock": bool(self.setup_restriction_after_lock),
            "official_sessions_expected": [s.value for s in self.official_sessions_expected],
        }

    def fingerprint(self) -> str:
        return _fp(self.as_payload())


@dataclass(frozen=True)
class EventPreparationCycleIdentity:
    """Identity of one preparation cycle bound to one upcoming NGR round. References the immutable
    environment via ``context_digest`` (a Phase-45 snapshot semantic digest) where available; it does
    not redefine the environment."""
    cycle_id: str
    event_name: str = ""
    series: str = ""
    round_label: str = ""
    driver_id: str = ""
    team: str = ""
    car: str = ""
    track: str = ""
    layout: str = ""
    prep_open_date: str = ""          # ISO YYYY-MM-DD
    official_quali_date: str = ""     # ISO YYYY-MM-DD
    official_race_date: str = ""      # ISO YYYY-MM-DD
    format_profile_id: str = ""
    disciplines: Tuple[str, ...] = field(default_factory=tuple)
    championship_objective: str = ""
    context_digest: str = ""          # immutable environment snapshot digest (Layer A), optional
    gt7_version: str = ""

    def as_payload(self) -> dict:
        return {
            "cycle_id": _norm(self.cycle_id),
            "event_name": _norm(self.event_name),
            "series": _norm(self.series),
            "round": _norm(self.round_label),
            "driver_id": _norm(self.driver_id),
            "team": _norm(self.team),
            "car": _norm(self.car),
            "track": _norm(self.track),
            "layout": _norm(self.layout),
            "prep_open_date": _iso(self.prep_open_date),
            "official_quali_date": _iso(self.official_quali_date),
            "official_race_date": _iso(self.official_race_date),
            "format_profile_id": _lc(self.format_profile_id),
            "disciplines": sorted(_lc(d) for d in self.disciplines if _norm(d)),
            "championship_objective": _norm(self.championship_objective),
            "context_digest": _norm(self.context_digest),
            "gt7_version": _norm(self.gt7_version),
        }

    def fingerprint(self) -> str:
        return _fp(self.as_payload())


@dataclass(frozen=True)
class PreparationActivity:
    """One typed, ordered preparation activity. ``order_index`` fixes deterministic ordering; a missing
    ``planned_date`` is allowed (an activity without a precise date). ``bound_session_ids`` links valid
    telemetry sessions to this activity (binding is explicit and lives elsewhere; here it is data)."""
    activity_id: str
    activity_type: PreparationActivityType
    title: str = ""
    objective: str = ""
    planned_date: str = ""            # ISO YYYY-MM-DD, may be empty
    state: PreparationActivityState = PreparationActivityState.PLANNED
    order_index: int = 0
    optional: bool = False
    bound_session_ids: Tuple[str, ...] = field(default_factory=tuple)
    phase: Optional[PreparationPhase] = None
    notes: str = ""

    def as_payload(self) -> dict:
        return {
            "activity_id": _norm(self.activity_id),
            "type": self.activity_type.value,
            "title": _norm(self.title),
            "objective": _norm(self.objective),
            "planned_date": _iso(self.planned_date),
            "state": self.state.value,
            "order_index": int(self.order_index),
            "optional": bool(self.optional),
            "bound_session_ids": sorted(_norm(s) for s in self.bound_session_ids if _norm(s)),
            "phase": self.phase.value if self.phase is not None else "",
        }

    def fingerprint(self) -> str:
        return _fp(self.as_payload())

    @property
    def is_practice_evidence(self) -> bool:
        return self.activity_type in PRACTICE_EVIDENCE_TYPES

    @property
    def is_official(self) -> bool:
        return self.activity_type in OFFICIAL_ACTIVITY_TYPES


@dataclass(frozen=True)
class PreparationObjective:
    """The current engineering objective and why it is the focus now."""
    headline: str
    rationale: str = ""
    phase: Optional[PreparationPhase] = None

    def as_payload(self) -> dict:
        return {"headline": _norm(self.headline), "rationale": _norm(self.rationale),
                "phase": self.phase.value if self.phase is not None else ""}


@dataclass(frozen=True)
class PreparationReadiness:
    """Readiness across preparation dimensions. Each dimension carries a ReadinessLevel + note."""
    dimensions: Tuple[Tuple[str, ReadinessLevel, str], ...] = field(default_factory=tuple)

    def as_payload(self) -> dict:
        return {"dimensions": [[_lc(name), lvl.value, _norm(note)]
                               for (name, lvl, note) in self.dimensions]}

    def level(self, name: str) -> ReadinessLevel:
        key = _lc(name)
        for (n, lvl, _note) in self.dimensions:
            if _lc(n) == key:
                return lvl
        return ReadinessLevel.UNKNOWN


@dataclass(frozen=True)
class PreparationProgress:
    """Cumulative counts across all valid Practice bound to the cycle. Display counts only; the
    semantic membership that feeds the fingerprint is the bound-session set, not these tallies."""
    valid_laps: int = 0
    practice_sessions: int = 0
    setup_experiments_completed: int = 0
    coaching_runs_completed: int = 0
    tyre_samples: int = 0
    fuel_samples: int = 0
    race_simulations: int = 0
    outstanding_questions: Tuple[str, ...] = field(default_factory=tuple)

    def as_payload(self) -> dict:
        return {
            "valid_laps": int(self.valid_laps),
            "practice_sessions": int(self.practice_sessions),
            "setup_experiments_completed": int(self.setup_experiments_completed),
            "coaching_runs_completed": int(self.coaching_runs_completed),
            "tyre_samples": int(self.tyre_samples),
            "fuel_samples": int(self.fuel_samples),
            "race_simulations": int(self.race_simulations),
            "outstanding_questions": [_norm(q) for q in self.outstanding_questions if _norm(q)],
        }


@dataclass(frozen=True)
class PreparationTimeline:
    """Ordered milestones + phases for the cycle. Derived deterministically from identity, profile,
    official sessions and dated activities. Undated activities keep their order_index position."""
    milestones: Tuple[EventMilestone, ...] = field(default_factory=tuple)
    phases: Tuple[PreparationPhase, ...] = field(default_factory=tuple)
    skipped_phases: Tuple[PreparationPhase, ...] = field(default_factory=tuple)

    def as_payload(self) -> dict:
        return {"milestones": [m.as_payload() for m in self.milestones],
                "phases": [p.value for p in self.phases],
                "skipped_phases": [p.value for p in self.skipped_phases]}

    def fingerprint(self) -> str:
        return _fp(self.as_payload())


@dataclass(frozen=True)
class EventPreparationCycle:
    """The aggregate preparation-cycle view for one upcoming round. ``days_until_race`` is DISPLAY-only
    (computed from an injected now_date) and is deliberately excluded from ``fingerprint``."""
    identity: EventPreparationCycleIdentity
    state: PreparationCycleState
    current_phase: PreparationPhase
    format_profile: EventFormatProfile
    official_sessions: Tuple[OfficialSession, ...]
    timeline: PreparationTimeline
    activities: Tuple[PreparationActivity, ...]
    objective: PreparationObjective
    readiness: PreparationReadiness
    progress: PreparationProgress
    next_activity_id: str = ""
    next_official: Optional[OfficialSession] = None
    preparation_span_days: Optional[int] = None    # semantic: derived from scheduled dates
    days_until_race: Optional[int] = None          # DISPLAY-only; excluded from fingerprint
    fingerprint: str = ""

    def as_semantic_payload(self) -> dict:
        """The semantic content that fixes cycle identity for fingerprinting. Excludes display state
        (countdown), widget/page/machine identity, paths, wall-clock and random ids."""
        return {
            "schema": EVENT_PREPARATION_CYCLE_SCHEMA,
            "identity": self.identity.as_payload(),
            "state": self.state.value,
            "current_phase": self.current_phase.value,
            "format_profile": self.format_profile.as_payload(),
            "official_sessions": [s.as_payload() for s in self.official_sessions],
            "timeline": self.timeline.as_payload(),
            # activity membership + order + status is semantic; render/display is not
            "activities": [a.as_payload() for a in
                           sorted(self.activities, key=lambda a: (a.order_index, a.activity_id))],
            "objective": self.objective.as_payload(),
            "readiness": self.readiness.as_payload(),
            "preparation_span_days": self.preparation_span_days,
            # NOTE: days_until_race intentionally omitted (runtime display)
        }


# ---------------------------------------------------------------------------
# Built-in NGR-neutral format profiles (configurable; not hard-coded schedules)
# ---------------------------------------------------------------------------

_ALL_PREP_PHASES: Tuple[PreparationPhase, ...] = tuple(
    p for p in PHASE_ORDER if p != PreparationPhase.COMPLETE)


def multiweek_profile(*, setup_lock_date: str = "", strategy_final_date: str = "") -> EventFormatProfile:
    """A full multi-week preparation profile (e.g. a monthly Porsche Cup round). Uses every preparation
    phase and declares an advisory setup-lock + strategy-finalisation deadline when dates are given.
    The *schedule* of activities is NOT encoded here — only which phases apply."""
    deadlines = []
    if _iso(setup_lock_date):
        deadlines.append(PreparationDeadline("setup_lock", setup_lock_date, mandatory=False,
                                             label="Advisory setup lock"))
    if _iso(strategy_final_date):
        deadlines.append(PreparationDeadline("strategy_final", strategy_final_date, mandatory=False,
                                             label="Strategy finalisation"))
    return EventFormatProfile(
        profile_id="multiweek",
        label="Multi-week preparation",
        included_phases=_ALL_PREP_PHASES,
        skipped_phases=(),
        deadlines=tuple(deadlines),
        setup_restriction_after_lock=False,
        official_sessions_expected=(OfficialSessionType.QUALIFYING, OfficialSessionType.RACE),
    )


def single_evening_profile() -> EventFormatProfile:
    """A one-evening event: briefing, short practice, qualifying, race, debrief. The multi-week
    development phases are explicitly skipped (not silently absent)."""
    included = (
        PreparationPhase.EVENT_OPEN,
        PreparationPhase.INITIAL_BRIEFING,
        PreparationPhase.BASELINE_ESTABLISHMENT,
        PreparationPhase.RACE_WEEK_READY,
        PreparationPhase.OFFICIAL_EVENT_ACTIVE,
        PreparationPhase.POST_RACE_REVIEW,
    )
    skipped = tuple(p for p in _ALL_PREP_PHASES if p not in included)
    return EventFormatProfile(
        profile_id="single_evening",
        label="Single-evening event",
        included_phases=included,
        skipped_phases=skipped,
        deadlines=(),
        setup_restriction_after_lock=False,
        official_sessions_expected=(OfficialSessionType.QUALIFYING, OfficialSessionType.RACE),
    )


def multi_race_profile() -> EventFormatProfile:
    """A round with more than one official race (e.g. two races off one preparation programme)."""
    p = multiweek_profile()
    return EventFormatProfile(
        profile_id="multi_race",
        label="Multi-race round",
        included_phases=p.included_phases,
        skipped_phases=(),
        deadlines=p.deadlines,
        setup_restriction_after_lock=False,
        official_sessions_expected=(OfficialSessionType.QUALIFYING, OfficialSessionType.RACE,
                                    OfficialSessionType.RACE),
    )


def endurance_profile(*, setup_lock_date: str = "") -> EventFormatProfile:
    """A long-race endurance round: full preparation with a heavier tyre/fuel and strategy emphasis and
    a setup restriction after lock."""
    deadlines = ()
    if _iso(setup_lock_date):
        deadlines = (PreparationDeadline("setup_lock", setup_lock_date, mandatory=True,
                                         label="Endurance setup lock"),)
    return EventFormatProfile(
        profile_id="endurance",
        label="Endurance round",
        included_phases=_ALL_PREP_PHASES,
        skipped_phases=(),
        deadlines=deadlines,
        setup_restriction_after_lock=True,
        official_sessions_expected=(OfficialSessionType.OFFICIAL_PRACTICE,
                                    OfficialSessionType.QUALIFYING, OfficialSessionType.RACE),
    )


BUILTIN_PROFILES: Dict[str, EventFormatProfile] = {
    "multiweek": multiweek_profile(),
    "single_evening": single_evening_profile(),
    "multi_race": multi_race_profile(),
    "endurance": endurance_profile(),
}


def resolve_profile(profile_id: str) -> EventFormatProfile:
    """Return a built-in profile by id, defaulting to the multi-week profile for an unknown id."""
    return BUILTIN_PROFILES.get(_lc(profile_id), BUILTIN_PROFILES["multiweek"])


# ---------------------------------------------------------------------------
# Timeline + cycle assembly
# ---------------------------------------------------------------------------

def _span_days(open_date: str, race_date: str) -> Optional[int]:
    """Deterministic span from preparation open to official race, in days. None if either date is
    missing/unparseable. Any span (0 for one evening, ~30 for a month) is valid - never an error."""
    a, b = _as_date(open_date), _as_date(race_date)
    if a is None or b is None:
        return None
    return (b - a).days


def _days_until(now_date: str, race_date: str) -> Optional[int]:
    """DISPLAY-only countdown from an injected now_date to the race. Never uses the wall clock; None if
    either date is missing. This value must never enter a fingerprint."""
    a, b = _as_date(now_date), _as_date(race_date)
    if a is None or b is None:
        return None
    return (b - a).days


def build_preparation_timeline(
    identity: EventPreparationCycleIdentity,
    profile: EventFormatProfile,
    official_sessions: Sequence[OfficialSession],
    activities: Sequence[PreparationActivity],
) -> PreparationTimeline:
    """Assemble the ordered timeline: event-open + profile deadlines + dated activities + official
    sessions, sorted by (date, order). Undated items sort after dated ones by order_index. Deterministic;
    'Week 1/2/3' labels are never forced - actual activity titles and dates are used."""
    milestones: List[Tuple[Tuple[int, str, int], EventMilestone]] = []

    def _key(iso_date: str, order: int) -> Tuple[int, str, int]:
        # dated items (bucket 0) sort before undated (bucket 1); within a bucket by date then order
        return (0, iso_date, order) if iso_date else (1, "", order)

    if _iso(identity.prep_open_date):
        milestones.append((_key(_iso(identity.prep_open_date), -1),
                           EventMilestone("Event opens", identity.prep_open_date, "event_open")))
    for d in profile.deadlines:
        if _iso(d.deadline_date):
            milestones.append((_key(_iso(d.deadline_date), 0),
                               EventMilestone(d.label or d.kind, d.deadline_date, "deadline")))
    for a in sorted(activities, key=lambda x: (x.order_index, x.activity_id)):
        milestones.append((_key(_iso(a.planned_date), a.order_index),
                           EventMilestone(a.title or a.activity_type.value, a.planned_date,
                                          "activity:" + a.activity_type.value)))
    for s in official_sessions:
        if _iso(s.scheduled_date):
            milestones.append((_key(_iso(s.scheduled_date), 10_000),
                               EventMilestone(s.label or s.session_type.value, s.scheduled_date,
                                              "official:" + s.session_type.value)))

    milestones.sort(key=lambda pair: pair[0])
    ordered = tuple(m for (_k, m) in milestones)

    included = profile.included_phases or _ALL_PREP_PHASES
    # keep canonical phase order regardless of profile declaration order
    phases = tuple(p for p in PHASE_ORDER if p in set(included))
    skipped = tuple(p for p in PHASE_ORDER if p in set(profile.skipped_phases))
    return PreparationTimeline(milestones=ordered, phases=phases, skipped_phases=skipped)


def _pick_next_activity(activities: Sequence[PreparationActivity]) -> str:
    """Deterministically choose the next actionable activity id: the earliest non-terminal, non-optional
    activity by (order_index, activity_id); falls back to the earliest non-terminal optional one; empty
    if none remain. Pure - this is a *recommendation view*, it never advances state."""
    def _sort(items):
        return sorted(items, key=lambda a: (a.order_index, a.activity_id))
    pending = [a for a in activities if a.state not in _TERMINAL_STATES]
    required = [a for a in pending if not a.optional]
    if required:
        return _sort(required)[0].activity_id
    if pending:
        return _sort(pending)[0].activity_id
    return ""


def _derive_cycle_state(
    activities: Sequence[PreparationActivity],
    explicit_state: Optional[PreparationCycleState],
) -> PreparationCycleState:
    """If an explicit lifecycle state is supplied (paused/abandoned/complete) it wins - a long quiet gap
    NEVER auto-abandons or auto-completes. Otherwise: NOT_STARTED when nothing has progressed, else
    ACTIVE; COMPLETE only when every non-optional activity is terminal AND at least one race completed."""
    if explicit_state in (PreparationCycleState.PAUSED, PreparationCycleState.ABANDONED,
                          PreparationCycleState.COMPLETE):
        return explicit_state
    acts = list(activities)
    if not acts:
        return PreparationCycleState.NOT_STARTED
    any_progress = any(a.state != PreparationActivityState.PLANNED for a in acts)
    if not any_progress:
        return PreparationCycleState.NOT_STARTED
    required = [a for a in acts if not a.optional]
    all_required_done = bool(required) and all(a.state in _TERMINAL_STATES for a in required)
    race_done = any(a.activity_type == PreparationActivityType.RACE
                    and a.state == PreparationActivityState.COMPLETED for a in acts)
    if all_required_done and race_done:
        return PreparationCycleState.COMPLETE
    return PreparationCycleState.ACTIVE


def _derive_current_phase(
    activities: Sequence[PreparationActivity],
    timeline: PreparationTimeline,
    state: PreparationCycleState,
) -> PreparationPhase:
    """Current phase = the phase of the next actionable activity if it declares one; else the furthest
    phase reached by completed activities; else the first included phase. Deterministic, view-only."""
    if state == PreparationCycleState.COMPLETE:
        return PreparationPhase.COMPLETE
    if state == PreparationCycleState.PAUSED:
        return PreparationPhase.PAUSED
    if state == PreparationCycleState.ABANDONED:
        return PreparationPhase.ABANDONED
    included = list(timeline.phases) or list(_ALL_PREP_PHASES)
    order_index = {p: i for i, p in enumerate(PHASE_ORDER)}
    next_id = _pick_next_activity(activities)
    for a in activities:
        if a.activity_id == next_id and a.phase is not None and a.phase in set(included):
            return a.phase
    # furthest completed phase
    reached = [a.phase for a in activities
               if a.state == PreparationActivityState.COMPLETED and a.phase is not None
               and a.phase in set(included)]
    if reached:
        return max(reached, key=lambda p: order_index.get(p, 0))
    return included[0]


def build_event_preparation_cycle(
    identity: EventPreparationCycleIdentity,
    activities: Sequence[PreparationActivity],
    *,
    profile: Optional[EventFormatProfile] = None,
    official_sessions: Sequence[OfficialSession] = (),
    now_date: str = "",
    explicit_state: Optional[PreparationCycleState] = None,
    objective: Optional[PreparationObjective] = None,
    readiness: Optional[PreparationReadiness] = None,
    progress: Optional[PreparationProgress] = None,
) -> EventPreparationCycle:
    """Assemble the deterministic preparation-cycle view. Pure and view-only: it computes ordering,
    timeline, next action, span and countdown from its inputs and writes nothing. ``readiness``,
    ``progress`` and ``objective`` may be supplied by the cumulative-evidence orchestration (Phase 48
    section 8); when omitted, empty defaults are used so identity/timeline callers work standalone.

    ``now_date`` is injected (never the wall clock) and only feeds the DISPLAY countdown, which is
    excluded from the fingerprint. Long gaps and any span are valid and never raise."""
    prof = profile if profile is not None else resolve_profile(identity.format_profile_id)
    acts = tuple(sorted(activities, key=lambda a: (a.order_index, a.activity_id)))
    officials = tuple(official_sessions)
    timeline = build_preparation_timeline(identity, prof, officials, acts)
    state = _derive_cycle_state(acts, explicit_state)
    phase = _derive_current_phase(acts, timeline, state)
    next_id = _pick_next_activity(acts)

    # next official session by scheduled date (undated last), deterministic
    def _osort(s: OfficialSession):
        iso = _iso(s.scheduled_date)
        return (0, iso) if iso else (1, s.session_type.value)
    next_official = sorted(officials, key=_osort)[0] if officials else None

    obj = objective or PreparationObjective(headline="", rationale="", phase=phase)
    rdy = readiness or PreparationReadiness()
    prog = progress or PreparationProgress()

    span = _span_days(identity.prep_open_date, identity.official_race_date)
    countdown = _days_until(now_date, identity.official_race_date)

    cycle = EventPreparationCycle(
        identity=identity, state=state, current_phase=phase, format_profile=prof,
        official_sessions=officials, timeline=timeline, activities=acts,
        objective=obj, readiness=rdy, progress=prog, next_activity_id=next_id,
        next_official=next_official, preparation_span_days=span, days_until_race=countdown,
        fingerprint="",
    )
    return _finalise(cycle)


def _finalise(cycle: EventPreparationCycle) -> EventPreparationCycle:
    """Attach the semantic fingerprint (over the display-free semantic payload)."""
    fp = _fp(cycle.as_semantic_payload())
    return EventPreparationCycle(
        identity=cycle.identity, state=cycle.state, current_phase=cycle.current_phase,
        format_profile=cycle.format_profile, official_sessions=cycle.official_sessions,
        timeline=cycle.timeline, activities=cycle.activities, objective=cycle.objective,
        readiness=cycle.readiness, progress=cycle.progress, next_activity_id=cycle.next_activity_id,
        next_official=cycle.next_official, preparation_span_days=cycle.preparation_span_days,
        days_until_race=cycle.days_until_race, fingerprint=fp,
    )
