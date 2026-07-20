"""Live runtime cadence & cache invalidation (Program 2, Phase 57).

Separates high-frequency telemetry ingestion from bounded advisory evaluation. The live bridge must NOT
rebuild the Event Preparation Cycle / Engineering Brain / strategy model for every telemetry packet.
This module provides:

  * ``runtime_cache_key`` — an OPERATIONAL invalidation key (changes when the active event, selected
    activity, setup fingerprint, event context, run plan, or session-end state changes). It is NOT an
    engineering fingerprint and must never enter one.
  * ``LiveEvaluationCadence`` — decides whether to re-evaluate: when the key changed, or when the cadence
    interval has elapsed (by injected monotonic time). This bounds re-evaluation frequency.

Purity: Qt-free, DB-free, offline, deterministic, no wall-clock, never raises. The cadence object holds
operational cache state only (last key + last monotonic time); it stores no engineering knowledge.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Optional

from strategy.gt7_live_adapter import SelectedActivityContext

LIVE_RUNTIME_CACHE_VERSION = "live_runtime_cache_v1"

# advisory evaluation cadence: at most one re-evaluation per this many injected monotonic seconds while
# the invalidation key is unchanged.
DEFAULT_CADENCE_SECONDS = 0.5


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def runtime_cache_key(ctx: SelectedActivityContext, *, session_ended: bool = False) -> str:
    """The operational invalidation key. Excludes volatile live counters (lap/segment/fuel/speed) so a
    telemetry packet alone does not invalidate the cache; changes only when the active event / activity /
    setup / context / run plan / session-end state changes."""
    payload = {
        "cycle_id": _norm(ctx.cycle_id), "activity_id": _norm(ctx.activity_id),
        "activity_type": _norm(ctx.activity_type), "discipline": _norm(ctx.discipline),
        "expected_setup_fingerprint": _norm(ctx.expected_setup_fingerprint),
        "event_context_digest": _norm(ctx.event_context_digest),
        "run_plan_fingerprint": _norm(ctx.run_plan_fingerprint),
        "session_ended": bool(session_ended),
    }
    return (f"{LIVE_RUNTIME_CACHE_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True).encode()).hexdigest()[:24])


class LiveEvaluationCadence:
    """Bounds advisory re-evaluation. Holds operational cache state only. Thread-safety is the caller's
    responsibility (the dashboard evaluates on a single worker); the object never touches the DB."""

    def __init__(self, cadence_seconds: float = DEFAULT_CADENCE_SECONDS):
        self._cadence = float(cadence_seconds)
        self._last_key: Optional[str] = None
        self._last_monotonic: Optional[float] = None

    def should_evaluate(self, key: str, now_monotonic: Optional[float], *,
                        force: bool = False) -> bool:
        """Re-evaluate when forced (e.g. explicit binding / stale->fresh transition), when the
        invalidation key changed, or when the cadence interval elapsed."""
        if force:
            return True
        if key != self._last_key:
            return True
        if self._last_monotonic is None or now_monotonic is None:
            return True
        return (float(now_monotonic) - float(self._last_monotonic)) >= self._cadence

    def record(self, key: str, now_monotonic: Optional[float]) -> None:
        self._last_key = key
        self._last_monotonic = now_monotonic

    @property
    def last_key(self) -> Optional[str]:
        return self._last_key
