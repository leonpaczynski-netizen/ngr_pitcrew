"""Driver-profile evolution — Phase 3 of the learning setup brain.

Re-derives the driver's STYLE profile from OBSERVED driving over time, so advice
tracks how the driver drives *now* instead of a frozen text description. It reads the
persisted Practice-Review balance feedback across recent sessions and, where a
tendency is CORROBORATED over several sessions, adds the matching style preference on
top of the static baseline.

Doctrine (directive items 3 + 5 + 6):
  * Deterministic, offline, explainable — every adjustment cites its evidence.
  * ADD-only: the driver's stated baseline (the prose profile) is never removed; the
    observed tendency only strengthens/adds a preference.
  * Never flips on a single session — a tendency must recur across several before it
    changes anything (``_MIN_SESSIONS`` / ``_CORROBORATION`` / ``_DOMINANCE``).
  * Bounded to the profile's DIRECTION/confidence bias — it never touches a safety
    gate (that stays with the rule engine's Pack A + clamps).

Why persistent balance feedback reveals style: one understeer report reflects the
current SETUP, but a driver who reports understeer across many cars/sessions is
revealing a persistent sensitivity — start them with more front bite. The opposite
for persistent exit-oversteer. That is what "personalise to how they drive" means.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from strategy.setup_driver_profile import DriverProfile, build_driver_profile

# A tendency must appear in at least this many recent sessions, out of at least this
# many total, AND outweigh the opposite direction by this factor, before it adjusts
# the profile. Conservative by design — style is a slow-moving property.
_MIN_SESSIONS = 4
_CORROBORATION = 3
_DOMINANCE = 2.0

_UNDERSTEER = frozenset({"understeer", "strong understeer"})
_OVERSTEER = frozenset({"oversteer", "strong oversteer"})


def _v(row: Mapping, field: str) -> str:
    return str((row or {}).get(field) or "").strip().lower()


def _row_signals(row: Mapping) -> "tuple[bool, bool]":
    """(understeer, oversteer) reported in this feedback row."""
    understeer = _v(row, "corner_entry") in _UNDERSTEER or _v(row, "mid_corner") in _UNDERSTEER
    oversteer = _v(row, "exit_stability") in _OVERSTEER
    return understeer, oversteer


@dataclass(frozen=True)
class ObservedTendencies:
    sessions: int
    understeer_sessions: int
    oversteer_sessions: int

    @property
    def understeer_averse(self) -> bool:
        return (self.understeer_sessions >= _CORROBORATION
                and self.understeer_sessions >= _DOMINANCE * self.oversteer_sessions)

    @property
    def oversteer_averse(self) -> bool:
        return (self.oversteer_sessions >= _CORROBORATION
                and self.oversteer_sessions >= _DOMINANCE * self.understeer_sessions)


def observe_feedback(rows: Sequence[Mapping]) -> ObservedTendencies:
    """Aggregate recent balance feedback into a persistent tendency. Never raises."""
    try:
        us = os_ = 0
        seen = 0
        for row in (rows or []):
            u, o = _row_signals(row)
            seen += 1
            if u:
                us += 1
            if o:
                os_ += 1
        return ObservedTendencies(sessions=seen, understeer_sessions=us,
                                  oversteer_sessions=os_)
    except Exception:
        return ObservedTendencies(0, 0, 0)


def evolve_profile(base: DriverProfile,
                   tendencies: ObservedTendencies) -> "tuple[DriverProfile, list[str]]":
    """Return (evolved_profile, rationale). ADD-only; returns the base unchanged when
    there is not enough corroborated evidence. Never raises."""
    try:
        rationale: list[str] = []
        if tendencies.sessions < _MIN_SESSIONS:
            return base, rationale

        tags = list(base.style_tags)
        flags = {
            "prefers_rear_stability": base.prefers_rear_stability,
            "dislikes_snap_exit": base.dislikes_snap_exit,
            "trail_braker": base.trail_braker,
            "rotation_without_snap": base.rotation_without_snap,
            "prefers_front_bite": base.prefers_front_bite,
            "dislikes_floaty_front": base.dislikes_floaty_front,
            "protects_downforce": base.protects_downforce,
            "race_values_consistency": base.race_values_consistency,
        }

        def _add(flag: str):
            if not flags[flag]:
                flags[flag] = True
            if flag not in tags:
                tags.append(flag)

        suffix = ""
        if tendencies.understeer_averse:
            _add("prefers_front_bite")
            _add("dislikes_floaty_front")
            suffix += "-fb"
            rationale.append(
                f"Understeer reported in {tendencies.understeer_sessions} of the last "
                f"{tendencies.sessions} sessions — strengthened your front-bite "
                f"preference (bias baselines toward a sharper front).")
        if tendencies.oversteer_averse:
            _add("dislikes_snap_exit")
            _add("prefers_rear_stability")
            suffix += "-rs"
            rationale.append(
                f"Exit oversteer reported in {tendencies.oversteer_sessions} of the last "
                f"{tendencies.sessions} sessions — strengthened your rear-stability "
                f"preference (bias baselines toward a planted rear).")

        if not suffix:
            return base, rationale

        evolved = base._replace(
            profile_version=f"{base.profile_version}+obs{suffix}",
            style_tags=tags,
            prefers_rear_stability=flags["prefers_rear_stability"],
            dislikes_snap_exit=flags["dislikes_snap_exit"],
            trail_braker=flags["trail_braker"],
            rotation_without_snap=flags["rotation_without_snap"],
            prefers_front_bite=flags["prefers_front_bite"],
            dislikes_floaty_front=flags["dislikes_floaty_front"],
            protects_downforce=flags["protects_downforce"],
            race_values_consistency=flags["race_values_consistency"],
        )
        return evolved, rationale
    except Exception:
        return base, []


def build_evolved_driver_profile(db, *, limit: int = 12) -> "tuple[DriverProfile, list[str]]":
    """The driver profile, evolved from recent observed driving. Falls back to the
    static baseline (with no rationale) when there is no db or no evidence. Never raises."""
    base = build_driver_profile()
    try:
        rows = db.get_recent_driver_feedback(limit) if db is not None and hasattr(
            db, "get_recent_driver_feedback") else []
    except Exception:
        rows = []
    return evolve_profile(base, observe_feedback(rows))
