"""Discipline-specific gearbox/RPM objectives (pure domain knowledge).

The UI rebuild's Garage must show what a gearbox is being optimised *for* per
discipline, and must never imply Base/Qualifying/Race gearboxes are identical
without saying why. This module holds that engineering knowledge as deterministic
text so the UI can render it without embedding domain logic (UI-rebuild F2.6).
"""

from __future__ import annotations

from typing import Tuple


def gearbox_headline(discipline: str) -> str:
    d = (discipline or "").strip().lower()
    if d == "qualifying":
        return "Qualifying gearbox — built for one-lap pace"
    if d == "race":
        return "Race gearbox — built for consistent race pace & fuel"
    return "Base gearbox — balanced baseline"


def gearbox_objectives(discipline: str) -> Tuple[str, ...]:
    """Ordered objectives for the given discipline's gearbox. Never raises."""
    d = (discipline or "").strip().lower()
    if d == "qualifying":
        return (
            "One-lap pace — maximise acceleration out of the decisive corners",
            "Use the full power band on the longest straights",
            "Track-specific top speed — don't over-gear",
            "Minimal compromise for fuel economy",
        )
    if d == "race":
        return (
            "Consistent total-race pace, not a single hot lap",
            "Fuel efficiency across the stint",
            "Reduced wheelspin for a cleaner drive-out",
            "Traffic flexibility and stable tyre use",
            "Appropriate speed for the next straight",
        )
    return (
        "Balanced baseline from the car + track profile",
        "Refine per discipline once you have run data",
    )
