"""Real GT7 runtime adapter (Program 2, Phase 57).

Maps the EXISTING telemetry tracker's published state onto the canonical `LiveActivityRuntimeSnapshot`
(Phase 55). It creates NO new UDP listener / polling loop / telemetry tracker — the dashboard reads the
existing `telemetry.state.RaceStateTracker` (fed by the daemon `UDPListener`) into a normalised
`TrackerRuntimeSnapshot`, and this adapter combines that with the selected activity's expected context.

Unknown values remain unknown — a verified match is never inferred from missing data. Telemetry
freshness is computed from an INJECTED monotonic time (never the wall clock); the monotonic clock may
affect expiry, but not the underlying engineering recommendation.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from strategy.live_activity_bridge import (
    LiveActivityRuntimeSnapshot, LiveActivityMatchResult, classify_live_activity_match)

GT7_LIVE_ADAPTER_VERSION = "gt7_live_adapter_v1"

# telemetry is stale when the last packet is older than this many injected monotonic seconds
DEFAULT_FRESHNESS_SECONDS = 1.5


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _fp(payload) -> str:
    return (f"{GT7_LIVE_ADAPTER_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


@dataclass(frozen=True)
class TrackerRuntimeSnapshot:
    """A normalised, thread-safe read of the existing `RaceStateTracker` at one instant. Built by the
    dashboard from the tracker (a thin read); this domain never touches the tracker directly. Empty
    string / None = unknown."""
    car: str = ""
    track: str = ""
    layout: str = ""
    session_discipline: str = ""        # detected purpose if the tracker can tell (else '')
    applied_setup_fingerprint: str = ""
    live_context_digest: str = ""
    lap: int = 0
    lap_progress: float = 0.0
    session_state: str = ""             # e.g. '', 'running', 'ended'
    current_segment: str = ""
    next_segment: str = ""
    map_match_confidence: float = 0.0
    speed: float = 0.0
    throttle: float = 0.0
    brake: float = 0.0
    steering: float = 0.0
    gear: int = 0
    fuel: str = ""
    tyre_compound: str = ""
    pit_state: str = ""
    clean_lap: bool = False
    invalid_lap: bool = False
    valid_laps: int = 0
    packet_seq: int = 0
    last_packet_monotonic: Optional[float] = None


@dataclass(frozen=True)
class SelectedActivityContext:
    """The expected context of the selected preparation activity. Purpose (discipline) comes ONLY from
    the selected activity — never inferred from telemetry."""
    cycle_id: str = ""
    activity_id: str = ""
    activity_type: str = ""
    discipline: str = ""
    car: str = ""
    track: str = ""
    layout: str = ""
    expected_setup_fingerprint: str = ""
    event_context_digest: str = ""
    run_plan_fingerprint: str = ""
    objective: str = ""
    target_laps: int = 0
    voice_ready: bool = False
    advisory_ready: bool = False


@dataclass(frozen=True)
class RuntimeFreshness:
    fresh: bool
    age_seconds: Optional[float]

    def as_payload(self) -> dict:
        return {"fresh": bool(self.fresh),
                "age_seconds": (round(self.age_seconds, 3) if self.age_seconds is not None else None)}


def evaluate_freshness(last_packet_monotonic: Optional[float], now_monotonic: Optional[float],
                       *, threshold_seconds: float = DEFAULT_FRESHNESS_SECONDS) -> RuntimeFreshness:
    """Deterministic freshness from injected monotonic times. Unknown last-packet time => stale."""
    if last_packet_monotonic is None or now_monotonic is None:
        return RuntimeFreshness(False, None)
    age = float(now_monotonic) - float(last_packet_monotonic)
    return RuntimeFreshness(age <= float(threshold_seconds) and age >= 0.0, age)


class Gt7LiveActivityAdapter:
    """Combines a `TrackerRuntimeSnapshot` + a `SelectedActivityContext` into the canonical
    `LiveActivityRuntimeSnapshot`. Stateless and deterministic."""

    @staticmethod
    def build_runtime_snapshot(tracker: TrackerRuntimeSnapshot, ctx: SelectedActivityContext, *,
                               now_monotonic: Optional[float] = None,
                               freshness_threshold: float = DEFAULT_FRESHNESS_SECONDS
                               ) -> LiveActivityRuntimeSnapshot:
        fresh = evaluate_freshness(tracker.last_packet_monotonic, now_monotonic,
                                   threshold_seconds=freshness_threshold).fresh
        # discipline_live comes from the selected activity by default (purpose is not inferred from
        # telemetry); a tracker-detected discipline, when present, can surface a genuine mismatch.
        discipline_live = _norm(tracker.session_discipline) or _norm(ctx.discipline)
        return LiveActivityRuntimeSnapshot(
            activity_selected=bool(_norm(ctx.activity_id)),
            activity_id=_norm(ctx.activity_id), activity_type=_norm(ctx.activity_type),
            cycle_id=_norm(ctx.cycle_id),
            event_context_digest=_norm(ctx.event_context_digest),
            live_context_digest=_norm(tracker.live_context_digest),
            discipline_expected=_norm(ctx.discipline), discipline_live=discipline_live,
            expected_setup_fingerprint=_norm(ctx.expected_setup_fingerprint),
            live_setup_fingerprint=_norm(tracker.applied_setup_fingerprint),
            car_expected=_norm(ctx.car), car_live=_norm(tracker.car),
            track_expected=_norm(ctx.track), track_live=_norm(tracker.track),
            layout_expected=_norm(ctx.layout), layout_live=_norm(tracker.layout),
            lap=int(tracker.lap or 0), session_state=_norm(tracker.session_state),
            telemetry_fresh=fresh, current_segment=_norm(tracker.current_segment),
            fuel=_norm(tracker.fuel), tyre_compound=_norm(tracker.tyre_compound),
            clean_lap=bool(tracker.clean_lap), invalid_lap=bool(tracker.invalid_lap),
            objective=_norm(ctx.objective), target_laps=int(ctx.target_laps or 0),
            valid_laps=int(tracker.valid_laps or 0), run_plan_fingerprint=_norm(ctx.run_plan_fingerprint),
            voice_ready=bool(ctx.voice_ready), advisory_ready=bool(ctx.advisory_ready))


@dataclass(frozen=True)
class LiveRuntimeEvaluation:
    """One immutable live evaluation: the runtime snapshot + its match classification + evidence progress.
    Built at the advisory cadence, not per telemetry packet."""
    snapshot: LiveActivityRuntimeSnapshot
    match: LiveActivityMatchResult
    evidence_progress: float          # valid_laps / target_laps (0..1), 0 when target unknown
    fingerprint: str = ""

    def as_stable_payload(self) -> dict:
        return {"snapshot": self.snapshot.as_stable_payload(), "match": self.match.as_payload(),
                "evidence_progress": round(self.evidence_progress, 4)}


def evaluate_live_runtime(tracker: TrackerRuntimeSnapshot, ctx: SelectedActivityContext, *,
                          now_monotonic: Optional[float] = None,
                          freshness_threshold: float = DEFAULT_FRESHNESS_SECONDS) -> LiveRuntimeEvaluation:
    """Build the immutable runtime snapshot, classify the activity match (reusing the canonical Phase-55
    classifier — replay and live use the SAME rules), and compute evidence progress. Deterministic."""
    snap = Gt7LiveActivityAdapter.build_runtime_snapshot(
        tracker, ctx, now_monotonic=now_monotonic, freshness_threshold=freshness_threshold)
    match = classify_live_activity_match(snap)
    target = int(ctx.target_laps or 0)
    progress = (min(1.0, max(0.0, int(tracker.valid_laps or 0) / target)) if target > 0 else 0.0)
    ev = LiveRuntimeEvaluation(snap, match, progress, "")
    return LiveRuntimeEvaluation(ev.snapshot, ev.match, ev.evidence_progress, _fp(ev.as_stable_payload()))
