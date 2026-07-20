"""Runtime context resolution (Program 2, Phase 60 — Audit B remediation).

Composes the LIVE context digest from resolved canonical local state (car + track + layout from the
tracker, discipline from the selected activity, applied setup from the active-setup authority) so an
EXACT activity match becomes possible WITHOUT fabricating telemetry. Where a field cannot be verified, an
honest limitation is preserved rather than disguised.

Key honesty rule: GT7 does NOT broadcast the applied setup — the live setup fingerprint is a LOCAL PROXY
from `ActiveSetupAuthority`. An unrecorded in-game setup change is undetectable; this caps setup
attribution but not Practice pace/consistency evidence.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. No setup values.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Tuple

RUNTIME_CONTEXT_RESOLUTION_VERSION = "runtime_context_resolution_v1"

# map-match confidence at/above which the layout is considered confirmed
DEFAULT_MAP_CONFIDENCE_THRESHOLD = 0.7


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _fp(payload) -> str:
    return (f"{RUNTIME_CONTEXT_RESOLUTION_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


@dataclass(frozen=True)
class RuntimeContextResolution:
    """The resolved live context: a composed live-context digest (or empty when unconfirmed), the
    applied-setup proxy fingerprint, whether an exact match is possible, and the honest limitations."""
    live_context_digest: str
    applied_setup_fingerprint: str
    context_confirmed: bool
    exact_possible: bool
    limitations: Tuple[str, ...]
    fingerprint: str = ""

    def as_payload(self) -> dict:
        return {"live_context_digest": _norm(self.live_context_digest),
                "applied_setup_fingerprint": _norm(self.applied_setup_fingerprint),
                "context_confirmed": bool(self.context_confirmed),
                "exact_possible": bool(self.exact_possible),
                "limitations": sorted(_norm(l) for l in self.limitations if _norm(l))}


def _matches(expected: str, live: str) -> bool:
    e, l = _lc(expected), _lc(live)
    return bool(e) and bool(l) and e == l


def resolve_runtime_context(
    *,
    tracker_car: str, tracker_track: str, tracker_layout: str, map_match_confidence: float,
    expected_car: str, expected_track: str, expected_layout: str, expected_context_digest: str,
    applied_setup_fingerprint: str, expected_setup_fingerprint: str,
    map_confidence_threshold: float = DEFAULT_MAP_CONFIDENCE_THRESHOLD,
) -> RuntimeContextResolution:
    """Compose the live context digest. The context is CONFIRMED (and the live digest is set to the
    expected event-context digest — a legitimate composition, not fabrication) only when car + track match
    and the layout matches with sufficient map-match confidence. An exact match is possible only when the
    context is confirmed AND the applied-setup proxy matches the expected fingerprint."""
    car_ok = _matches(expected_car, tracker_car)
    track_ok = _matches(expected_track, tracker_track)
    layout_ok = _matches(expected_layout, tracker_layout)
    map_ok = float(map_match_confidence or 0.0) >= float(map_confidence_threshold)

    limitations = ["applied-setup fingerprint is a local proxy (GT7 does not broadcast the setup); "
                   "an unrecorded in-game setup change is undetectable"]
    if not car_ok:
        limitations.append("car not confirmed")
    if not track_ok:
        limitations.append("track not confirmed")
    if not layout_ok or not map_ok:
        limitations.append("layout unconfirmed / low map-match confidence")

    context_confirmed = car_ok and track_ok and layout_ok and map_ok
    live_digest = _norm(expected_context_digest) if (context_confirmed and _norm(expected_context_digest)) else ""
    setup_ok = _matches(expected_setup_fingerprint, applied_setup_fingerprint)
    exact_possible = context_confirmed and setup_ok

    r = RuntimeContextResolution(live_digest, _norm(applied_setup_fingerprint), context_confirmed,
                                 exact_possible, tuple(limitations), "")
    return RuntimeContextResolution(r.live_context_digest, r.applied_setup_fingerprint, r.context_confirmed,
                                    r.exact_possible, r.limitations, _fp(r.as_payload()))
