"""Driver profile module — Group 42: Rule-First Setup Brain.

Derives a structured DriverProfile from the hardcoded PERSONAL_DRIVER_TUNING_MODEL
and DRIVER_HARD_CONSTRAINTS constants in setup_diagnosis.py.

Import contract
---------------
- This module imports FROM setup_diagnosis (to read the driver constants).
- setup_diagnosis does NOT import this module.
- No cycle exists.
- driving_advisor imports this module (lazy, no cycle risk there either).

Usage
-----
    from strategy.setup_driver_profile import build_driver_profile, DriverProfile
    profile = build_driver_profile()
"""
from __future__ import annotations

from enum import Enum
from typing import NamedTuple


class DriverStyleAlignment(str, Enum):
    """How well a candidate setup change aligns with the driver's personal style."""
    aligned = "aligned"
    neutral = "neutral"
    caution = "caution"


class DriverProfile(NamedTuple):
    """Structured representation of the driver's tuning preferences.

    Fields derived from PERSONAL_DRIVER_TUNING_MODEL and DRIVER_HARD_CONSTRAINTS.
    All boolean fields default to False so that build_driver_profile() can return
    a safe neutral profile on any exception.
    """
    profile_version: str
    style_tags: list
    hard_constraints: list
    prefers_rear_stability: bool
    dislikes_snap_exit: bool
    trail_braker: bool
    rotation_without_snap: bool
    prefers_front_bite: bool
    dislikes_floaty_front: bool
    protects_downforce: bool
    race_values_consistency: bool


def build_driver_profile() -> DriverProfile:
    """Build a DriverProfile from the hardcoded driver constants.

    Reads PERSONAL_DRIVER_TUNING_MODEL and DRIVER_HARD_CONSTRAINTS from
    setup_diagnosis.  Returns a conservative neutral profile (all False, empty
    lists) on ANY exception — never raises.

    The style_tags list mirrors the tags used in SetupRule.driver_style_tags
    so the engine can cross-reference them.

    Profile version: "v1.0-hardcoded" — increment when the source constants
    or mapping logic changes materially.
    """
    try:
        from strategy.setup_diagnosis import (
            PERSONAL_DRIVER_TUNING_MODEL,
            DRIVER_HARD_CONSTRAINTS,
        )

        # Derive boolean flags from the text constants via substring matching.
        # The constants are stable prose, so this is deterministic.
        _dtm = (PERSONAL_DRIVER_TUNING_MODEL + DRIVER_HARD_CONSTRAINTS).lower()

        trail_braker = "trail" in _dtm and "brak" in _dtm
        prefers_front_bite = (
            "front bite" in _dtm
            or "nose response" in _dtm
            or "immediate nose" in _dtm
        )
        dislikes_floaty_front = (
            "floaty front" in _dtm
            or "lazy turn" in _dtm
        )
        dislikes_snap_exit = (
            "snap" in _dtm
            or "predictable exit" in _dtm
        )
        rotation_without_snap = (
            "rotation without snap" in _dtm
            or "predictable exit" in _dtm
        )
        prefers_rear_stability = (
            "stable, planted rear" in _dtm
            or "rear stability" in _dtm
            or "increase rear aero to stabilise" in _dtm
        )
        protects_downforce = (
            "low-downforce default" in _dtm
            or "no low-downforce" in _dtm
            or "do not recommend minimum aero" in _dtm
        )
        race_values_consistency = (
            "consistency" in _dtm
            or "tyre life" in _dtm
            or "confidence" in _dtm
        )

        # Style tags for cross-referencing SetupRule.driver_style_tags
        style_tags: list[str] = []
        if trail_braker:
            style_tags.append("trail_braker")
        if prefers_front_bite:
            style_tags.append("prefers_front_bite")
        if dislikes_floaty_front:
            style_tags.append("dislikes_floaty_front")
        if dislikes_snap_exit:
            style_tags.append("dislikes_snap_exit")
        if rotation_without_snap:
            style_tags.append("rotation_without_snap")
        if prefers_rear_stability:
            style_tags.append("prefers_rear_stability")
        if protects_downforce:
            style_tags.append("protects_downforce")
        if race_values_consistency:
            style_tags.append("race_values_consistency")

        # Hard constraints as plain text list (first 8 items, one per line).
        hard_constraints: list[str] = []
        for line in DRIVER_HARD_CONSTRAINTS.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("##"):
                hard_constraints.append(line)

        return DriverProfile(
            profile_version="v1.0-hardcoded",
            style_tags=style_tags,
            hard_constraints=hard_constraints,
            prefers_rear_stability=prefers_rear_stability,
            dislikes_snap_exit=dislikes_snap_exit,
            trail_braker=trail_braker,
            rotation_without_snap=rotation_without_snap,
            prefers_front_bite=prefers_front_bite,
            dislikes_floaty_front=dislikes_floaty_front,
            protects_downforce=protects_downforce,
            race_values_consistency=race_values_consistency,
        )

    except Exception:
        # Never raise — return a safe neutral profile
        return DriverProfile(
            profile_version="v1.0-hardcoded",
            style_tags=[],
            hard_constraints=[],
            prefers_rear_stability=False,
            dislikes_snap_exit=False,
            trail_braker=False,
            rotation_without_snap=False,
            prefers_front_bite=False,
            dislikes_floaty_front=False,
            protects_downforce=False,
            race_values_consistency=False,
        )
