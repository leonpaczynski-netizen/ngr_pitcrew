"""Session-type-aware live race engineer — talks like a real engineer for the
session you're actually running.

The live engineer's existing output is all race strategy (fuel, stops, gaps), which
is right for a RACE but wrong for practice or qualifying. A real engineer changes what
they say by session:

  * PRACTICE — data-gathering and feel. "Bring me a clean lap; how's the balance?"
    Never talks pit strategy.
  * QUALIFYING — one-lap pace. Out-lap: build temperature. Flying lap: commit.
    Reports the lap and whether it was a personal best. No strategy.
  * RACE — defers to the strategy engine (fuel/tyre management, pit windows, gaps).

Pure, deterministic, offline, never raises. Returns "" to mean "no session-specific
line — let the caller's default (race strategy engine) drive."
"""
from __future__ import annotations

from typing import Optional

PRACTICE, QUALIFYING, RACE = "practice", "qualifying", "race"


def normalise_session_mode(live_session_mode: Optional[str], race_phase: str = "") -> str:
    """Map the bridge's live-session signals to practice/qualifying/race."""
    m = str(live_session_mode or "").strip().lower()
    if m == RACE or str(race_phase or "").upper() == "RACING":
        return RACE
    if m == QUALIFYING:
        return QUALIFYING
    return PRACTICE


def session_engineer_call(
    mode: str,
    *,
    connected: bool,
    lap_count: int,
    last_lap_s: Optional[float] = None,
    best_lap_s: Optional[float] = None,
    out_lap: bool = False,
) -> str:
    """The engineer's line for a practice or qualifying session. "" for race (the
    strategy engine drives that) or when there's no live telemetry."""
    try:
        if not connected:
            return ""
        m = (mode or PRACTICE).strip().lower()
        laps = int(lap_count or 0)

        if m == RACE:
            return ""  # the adaptive strategy engine owns the race

        if m == QUALIFYING:
            if out_lap or laps <= 0:
                return ("Out-lap — build tyre temperature and keep it clean. "
                        "Your flying lap is next.")
            if (last_lap_s and best_lap_s
                    and last_lap_s <= best_lap_s + 1e-6):
                return (f"Personal best, {last_lap_s:.3f}. Tyres are in — "
                        "you've got another one in you, go again.")
            if last_lap_s:
                return (f"Lap in at {last_lap_s:.3f}. This is your lap — "
                        "commit through every corner, everything the car has.")
            return ("This is your lap — commit through every corner, "
                    "everything the car has.")

        # PRACTICE — feel + consistency, never strategy.
        if laps <= 0:
            return ("Bring me a clean lap when you're ready — let's get a read "
                    "on the balance.")
        if laps < 3:
            return (f"{laps} lap{'s' if laps != 1 else ''} in — settle into a "
                    "rhythm, I need a few consistent laps for a read.")
        return (f"{laps} clean laps — I've got a read on the car. Tell me how the "
                "balance feels and we'll tune it from there.")
    except Exception:
        return ""
