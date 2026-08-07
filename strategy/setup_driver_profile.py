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


#: Bumped from "v1.0-hardcoded" when the eight fabricated preference flags were
#: removed (UAT 2026-08-07 defect A9). Anything that cached a profile keyed on the old
#: version string will correctly see this as a different profile.
PROFILE_VERSION = "v2.0-no-fabricated-preferences"


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
    """Return the driver profile.

    UAT 2026-08-07 defect A9 — this used to derive eight "driver preference" booleans
    by SUBSTRING-MATCHING the hardcoded PERSONAL_DRIVER_TUNING_MODEL prose in
    setup_diagnosis. Because that prose is a fixed constant, all eight evaluated True
    for every user of the app, and two of them contradicted each other outright:
    ``race_values_consistency`` pushed lsd_decel +2 while ``rotation_without_snap``
    pushed it -2, so the pair cancelled and the "personalisation" was a no-op wearing
    a confident label. That is fictitious personalisation, and a setup that claims to
    be tailored to you when it is not is worse than one that admits it is generic.

    The flags are therefore all False until something real populates them. The
    structure stays: ``strategy.driver_profile_evolution`` learns these from recorded
    sessions and driver feedback, and that is the only thing that should ever set
    them. ``_resolve_driver_profile`` in driving_advisor already prefers an evolved
    profile from the DB when one exists, so a driver with real history is unaffected
    by this change — only the invented default is gone.

    Hard constraints are still read: they are explicit safety rules, not inferred
    preferences, and nothing about them was fabricated.
    """
    hard_constraints: list[str] = []
    try:
        from strategy.setup_diagnosis import DRIVER_HARD_CONSTRAINTS
        for line in DRIVER_HARD_CONSTRAINTS.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                hard_constraints.append(line)
    except Exception:
        hard_constraints = []

    return DriverProfile(
        profile_version=PROFILE_VERSION,
        style_tags=[],
        hard_constraints=hard_constraints,
        prefers_rear_stability=False,
        dislikes_snap_exit=False,
        trail_braker=False,
        rotation_without_snap=False,
        prefers_front_bite=False,
        dislikes_floaty_front=False,
        protects_downforce=False,
        race_values_consistency=False,
    )
