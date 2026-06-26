"""Single source of truth for GT7 tyre compound definitions.

All tabs, AI prompts, and telemetry import from here so compound lists
stay consistent without editing multiple files.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TyreCompound:
    name: str          # "Racing Soft"
    code: str          # "RS" — used in saves, strategy stints, DB
    category: str      # "Racing" | "Sports" | "Comfort" | "Wet"
    wet: bool          # True for Intermediate and Heavy Wet
    cold_max: float    # °C — below this is COLD
    warming_max: float # °C — WARMING below this
    optimal_max: float # °C — OPTIMAL below this
    hot_max: float     # °C — HOT below this; above = OVERHEATING


ALL_COMPOUNDS: tuple[TyreCompound, ...] = (
    TyreCompound("Comfort Hard",   "CH", "Comfort", False, 45, 55, 72,  82),
    TyreCompound("Comfort Medium", "CM", "Comfort", False, 45, 55, 75,  85),
    TyreCompound("Comfort Soft",   "CS", "Comfort", False, 45, 55, 78,  88),
    TyreCompound("Sports Hard",    "SH", "Sports",  False, 55, 65, 75,  90),
    TyreCompound("Sports Medium",  "SM", "Sports",  False, 55, 67, 79,  92),
    TyreCompound("Sports Soft",    "SS", "Sports",  False, 55, 68, 83,  95),
    TyreCompound("Racing Hard",    "RH", "Racing",  False, 60, 75, 100, 110),
    TyreCompound("Racing Medium",  "RM", "Racing",  False, 65, 80, 105, 115),
    TyreCompound("Racing Soft",    "RS", "Racing",  False, 70, 85, 110, 120),
    TyreCompound("Intermediate",   "IM", "Wet",     True,  45, 60, 90,  100),
    TyreCompound("Heavy Wet",      "HW", "Wet",     True,  35, 50, 80,  90),
)

_BY_CODE: dict[str, TyreCompound] = {c.code: c for c in ALL_COMPOUNDS}

_ALIASES: dict[str, str] = {c.name.lower(): c.code for c in ALL_COMPOUNDS}
_ALIASES.update({
    # Old "Racing: Soft" style used in Setup Builder before Phase 7
    "racing: soft":         "RS",
    "racing: medium":       "RM",
    "racing: hard":         "RH",
    # Old parenthetical style used in TYRE_TEMP_PRESETS before Phase 7
    "racing soft (rs)":     "RS",
    "racing medium (rm)":   "RM",
    "racing hard (rh)":     "RH",
    "intermediate (im)":    "IM",
    "wet (w)":              "HW",
    # Short codes
    "rs": "RS", "rm": "RM", "rh": "RH",
    "sh": "SH", "sm": "SM", "ss": "SS",
    "ch": "CH", "cm": "CM", "cs": "CS",
    "im": "IM",
    "w":  "HW", "hw": "HW",
    # Common English words
    "soft":   "RS",
    "medium": "RM",
    "hard":   "RH",
    "inter":  "IM",
    "rain":   "HW",
    "wet":    "HW",
})


def compound_names() -> list[str]:
    """Ordered display names for UI dropdowns (Comfort → Sports → Racing → Wet)."""
    return [c.name for c in ALL_COMPOUNDS]


def compound_codes() -> list[str]:
    """Ordered short codes for DB, session tags, and strategy stints."""
    return [c.code for c in ALL_COMPOUNDS]


def get_by_code(code: str) -> TyreCompound | None:
    """Look up a compound by its short code (case-insensitive)."""
    return _BY_CODE.get(code.upper())


def normalise_code(s: str) -> str | None:
    """Map any user-entered string to a canonical short code. Returns None if unrecognised."""
    return _ALIASES.get(s.strip().lower())


def normalise_name(s: str) -> str | None:
    """Map any user-entered string to a canonical display name. Returns None if unrecognised."""
    code = normalise_code(s)
    tc = _BY_CODE.get(code) if code else None
    return tc.name if tc else None


def temp_preset(code_or_name: str) -> dict | None:
    """Return {cold_max, warming_max, optimal_max, hot_max} for use with TyreThresholds.

    Accepts short codes, canonical names, or any alias understood by normalise_code.
    """
    tc = _BY_CODE.get(code_or_name.upper())
    if tc is None:
        resolved = normalise_code(code_or_name)
        tc = _BY_CODE.get(resolved) if resolved else None
    if tc is None:
        return None
    return {
        "cold_max":    tc.cold_max,
        "warming_max": tc.warming_max,
        "optimal_max": tc.optimal_max,
        "hot_max":     tc.hot_max,
    }
