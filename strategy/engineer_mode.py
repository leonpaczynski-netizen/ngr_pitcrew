"""The single engineer-mode authority (Program 3 Phase E1).

The active engineer mode was decided in two places that disagreed on how many modes
exist: ``strategy.live_engineer_session.normalise_session_mode`` knew three
(practice / qualifying / race), while the announcer's ``_session_mode`` string also
carried ``track_modelling`` on a separate path. This module makes the mode ONE
enum, resolved from the driver-declared session type (never inferred from telemetry).

Pure, deterministic, offline, never raises. Coaching is deliberately NOT a session
mode here — it is a push-to-talk / driving-advisor concern.
"""

from __future__ import annotations

import enum
from typing import Optional


class EngineerMode(str, enum.Enum):
    """The four live engineer session modes. ``str`` values match the legacy
    lowercase strings (``normalise_session_mode`` / ``announcer.set_session_mode``)
    so the enum drops into existing call sites without a data change."""

    TRACK_MODELLING = "track_modelling"
    PRACTICE = "practice"
    QUALIFYING = "qualifying"
    RACE = "race"


def resolve_engineer_mode(
    *,
    live_session_mode: Optional[str] = None,
    race_phase: str = "",
    track_modelling_active: bool = False,
) -> EngineerMode:
    """Resolve the one active engineer mode from the driver-declared session.

    Track modelling is a distinct capture activity and wins when active. Otherwise
    this preserves ``normalise_session_mode``'s exact truth table: RACE when the
    declared mode is race OR the race phase is RACING (GT7 auto-classifies any
    multi-car lobby as a race, so the declared override matters); QUALIFYING when
    declared; PRACTICE as the safe default. Never infers a mode from telemetry
    shape, lap count or fuel use."""
    if track_modelling_active:
        return EngineerMode.TRACK_MODELLING
    m = str(live_session_mode or "").strip().lower()
    if m == EngineerMode.RACE.value or str(race_phase or "").upper() == "RACING":
        return EngineerMode.RACE
    if m == EngineerMode.QUALIFYING.value:
        return EngineerMode.QUALIFYING
    return EngineerMode.PRACTICE
