"""Live GT7 Activity Execution Bridge — runtime snapshot & activity matching (Program 2, Phase 55).

Connects the selected NGR preparation activity to real GT7 telemetry runtime state while preserving
explicit user control. Each evaluation cycle uses ONE immutable runtime snapshot; the bridge classifies
how the live GT7 session matches the selected activity. Unknown values are NEVER treated as a verified
match. It starts nothing, applies nothing, binds nothing, completes nothing — it is a deterministic
read-only classifier over a snapshot.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple

LIVE_ACTIVITY_BRIDGE_VERSION = "live_activity_bridge_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _dumps(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True,
                      allow_nan=False)


def _fp(payload) -> str:
    return (f"{LIVE_ACTIVITY_BRIDGE_VERSION}:"
            + hashlib.sha256(_dumps(payload).encode("utf-8")).hexdigest()[:24])


class LiveActivityMatch(str, Enum):
    EXACT_ACTIVITY_MATCH = "exact_activity_match"
    MATCH_WITH_LIMITATIONS = "match_with_limitations"
    SETUP_MISMATCH = "setup_mismatch"
    CAR_MISMATCH = "car_mismatch"
    TRACK_MISMATCH = "track_mismatch"
    LAYOUT_MISMATCH = "layout_mismatch"
    DISCIPLINE_MISMATCH = "discipline_mismatch"
    CONTEXT_MISMATCH = "context_mismatch"
    TELEMETRY_STALE = "telemetry_stale"
    ACTIVITY_NOT_SELECTED = "activity_not_selected"
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True)
class LiveActivityRuntimeSnapshot:
    """One immutable runtime evaluation snapshot. Empty string = unknown (never fabricated). Built by the
    dashboard from the live telemetry tracker + the selected activity's execution context, ONCE per
    evaluation (never rebuilt per packet)."""
    activity_selected: bool = False
    activity_id: str = ""
    activity_type: str = ""
    cycle_id: str = ""
    event_context_digest: str = ""
    live_context_digest: str = ""
    discipline_expected: str = ""
    discipline_live: str = ""
    expected_setup_fingerprint: str = ""
    live_setup_fingerprint: str = ""
    car_expected: str = ""
    car_live: str = ""
    track_expected: str = ""
    track_live: str = ""
    layout_expected: str = ""
    layout_live: str = ""
    lap: int = 0
    session_state: str = ""
    telemetry_fresh: bool = False
    current_segment: str = ""
    fuel: str = ""
    tyre_compound: str = ""
    clean_lap: bool = False
    invalid_lap: bool = False
    objective: str = ""
    target_laps: int = 0
    valid_laps: int = 0
    run_plan_fingerprint: str = ""
    voice_ready: bool = False
    advisory_ready: bool = False

    def as_stable_payload(self) -> dict:
        # live counters / segment / fuel / lap are volatile display; the stable identity is the match
        # configuration (selected activity + expected-vs-live context + freshness).
        return {"activity_selected": bool(self.activity_selected), "activity_id": _norm(self.activity_id),
                "activity_type": _lc(self.activity_type), "cycle_id": _norm(self.cycle_id),
                "event_context_digest": _norm(self.event_context_digest),
                "live_context_digest": _norm(self.live_context_digest),
                "discipline_expected": _lc(self.discipline_expected), "discipline_live": _lc(self.discipline_live),
                "expected_setup_fingerprint": _norm(self.expected_setup_fingerprint),
                "live_setup_fingerprint": _norm(self.live_setup_fingerprint),
                "car_expected": _lc(self.car_expected), "car_live": _lc(self.car_live),
                "track_expected": _lc(self.track_expected), "track_live": _lc(self.track_live),
                "layout_expected": _lc(self.layout_expected), "layout_live": _lc(self.layout_live),
                "telemetry_fresh": bool(self.telemetry_fresh)}

    def fingerprint(self) -> str:
        return _fp(self.as_stable_payload())


@dataclass(frozen=True)
class LiveActivityMatchResult:
    match: LiveActivityMatch
    reason: str
    limitations: Tuple[str, ...]
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"match": self.match.value, "reason": _norm(self.reason),
                "limitations": sorted(_norm(l) for l in self.limitations if _norm(l))}


def _cmp(expected: str, live: str) -> str:
    """'match' if both known and equal, 'mismatch' if both known and differ, 'unknown' otherwise."""
    e, l = _lc(expected), _lc(live)
    if not e or not l:
        return "unknown"
    return "match" if e == l else "mismatch"


def classify_live_activity_match(snap: LiveActivityRuntimeSnapshot) -> LiveActivityMatchResult:
    """Deterministically classify the live GT7 session against the selected activity. Hard mismatches are
    reported first; a required unknown field yields UNVERIFIABLE (never a verified match); a full known
    match yields EXACT; a known match with some unknown non-critical field yields MATCH_WITH_LIMITATIONS."""
    M = LiveActivityMatch

    def _r(match, reason, limitations=()):
        res = LiveActivityMatchResult(match, reason, tuple(limitations), "")
        return LiveActivityMatchResult(res.match, res.reason, res.limitations, _fp(res.as_payload()))

    if not snap.activity_selected or not _norm(snap.activity_id):
        return _r(M.ACTIVITY_NOT_SELECTED, "no preparation activity is selected")
    if not snap.telemetry_fresh:
        return _r(M.TELEMETRY_STALE, "telemetry is stale — cannot verify a live match")

    # hard mismatches, in order
    for expected, live, mm, label in (
        (snap.car_expected, snap.car_live, M.CAR_MISMATCH, "car"),
        (snap.track_expected, snap.track_live, M.TRACK_MISMATCH, "track"),
        (snap.layout_expected, snap.layout_live, M.LAYOUT_MISMATCH, "layout"),
        (snap.discipline_expected, snap.discipline_live, M.DISCIPLINE_MISMATCH, "discipline"),
        (snap.expected_setup_fingerprint, snap.live_setup_fingerprint, M.SETUP_MISMATCH, "setup"),
        (snap.event_context_digest, snap.live_context_digest, M.CONTEXT_MISMATCH, "context"),
    ):
        if _cmp(expected, live) == "mismatch":
            return _r(mm, f"{label} does not match the selected activity")

    # required dimensions for a VERIFIED match: car, track, layout, discipline, setup
    required = {
        "car": _cmp(snap.car_expected, snap.car_live),
        "track": _cmp(snap.track_expected, snap.track_live),
        "layout": _cmp(snap.layout_expected, snap.layout_live),
        "discipline": _cmp(snap.discipline_expected, snap.discipline_live),
        "setup": _cmp(snap.expected_setup_fingerprint, snap.live_setup_fingerprint),
    }
    unknowns = [k for k, v in required.items() if v == "unknown"]
    if unknowns:
        # a required field unknown -> cannot claim a verified match
        return _r(M.UNVERIFIABLE, "one or more required fields are unknown; cannot verify a match",
                  limitations=tuple(f"{k} unknown" for k in sorted(unknowns)))

    # all required dimensions matched. Check non-critical dimensions for limitations.
    limitations = []
    if _cmp(snap.event_context_digest, snap.live_context_digest) == "unknown":
        limitations.append("context digest unknown")
    if not _norm(snap.tyre_compound):
        limitations.append("compound unknown")
    if not _norm(snap.run_plan_fingerprint):
        limitations.append("run-plan unverified")
    if limitations:
        return _r(M.MATCH_WITH_LIMITATIONS, "verified match with limitations", limitations)
    return _r(M.EXACT_ACTIVITY_MATCH, "verified exact activity match")


def match_permits_evidence(result: LiveActivityMatchResult) -> bool:
    """Whether the match is good enough for the run to contribute evidence. EXACT and MATCH_WITH_
    LIMITATIONS may (limitations are labelled); every mismatch / stale / unverifiable / not-selected may
    not."""
    return result.match in (LiveActivityMatch.EXACT_ACTIVITY_MATCH,
                            LiveActivityMatch.MATCH_WITH_LIMITATIONS)
