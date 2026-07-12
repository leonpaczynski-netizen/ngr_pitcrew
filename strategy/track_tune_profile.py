"""Phase 5 — track-specific tune profile (pure, Qt-free, evidence-honest).

Derives the track characteristics that shape a base tune from the BEST AVAILABLE
approved track evidence — the track seed (length, corners, longest straight,
elevation) and the accepted model (measured lap length + corner count). It NEVER
invents unavailable characteristics: each is tagged with value / source /
confidence / availability, and when no trustworthy model exists the profile says
so and shapes nothing (conservative fallback).

The profile is consumed by ``strategy/setup_baseline.build_baseline_setup`` to
shape aero/gearing to the circuit — e.g. a long-straight, low-corner-density
track trims drag rather than pinning front aero to its ceiling (the base-max-aero
UAT defect). It authors NO setup values itself and applies nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Aero-bias thresholds (documented, conservative).
_STRAIGHT_HEAVY_FRACTION = 0.22   # longest straight ≥ 22% of the lap → drag-sensitive
_TWISTY_CORNERS_PER_KM   = 6.0    # very corner-dense / slow → aero-sensitive


@dataclass(frozen=True)
class TrackCharacteristic:
    """One track characteristic with provenance (never invented)."""
    name: str
    value: object
    source: str        # "accepted_model" | "seed" | "derived" | "missing"
    confidence: str    # "high" | "medium" | "low" | "none"
    available: bool


@dataclass(frozen=True)
class TrackTuneProfile:
    """Track characteristics that shape a base tune. ``trustworthy`` is False when
    no usable track model exists — callers must then fall back conservatively."""
    track_location_id: str
    layout_id: str
    trustworthy: bool
    lap_length_m: Optional[float]
    corner_count: Optional[int]
    corner_density_per_km: Optional[float]
    longest_straight_m: Optional[float]
    straight_fraction: Optional[float]
    elevation_change_m: Optional[float]
    aero_bias: str = "neutral"          # "trim" | "neutral" | "add"
    aero_bias_reason: str = ""
    characteristics: List[TrackCharacteristic] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.trustworthy:
            return ("No trustworthy track model — base tune uses conservative, "
                    "track-neutral defaults.")
        bits = []
        if self.lap_length_m:
            bits.append(f"{self.lap_length_m:.0f} m")
        if self.corner_count is not None:
            bits.append(f"{self.corner_count} corners")
        if self.corner_density_per_km is not None:
            bits.append(f"{self.corner_density_per_km:.1f}/km")
        if self.straight_fraction is not None:
            bits.append(f"longest straight {self.straight_fraction * 100:.0f}% of lap")
        head = ", ".join(bits) if bits else "limited track data"
        return f"{head}. Aero: {self.aero_bias} ({self.aero_bias_reason})."


def _num(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f == f and f not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


def build_track_tune_profile(
    track_location_id: str,
    layout_id: str,
    seed_layout=None,
    accepted_model=None,
) -> TrackTuneProfile:
    """Build a TrackTuneProfile from a seed layout (``TrackLayoutSeed``) and/or an
    accepted model (``TrackModelAlignmentResult``). Both optional; when neither
    yields lap length + corner count the profile is ``trustworthy=False``.

    ``seed_layout`` / ``accepted_model`` are duck-typed so this stays Qt-free and
    dependency-light. Callers resolve them (see the setup-builder UI wiring)."""
    chars: List[TrackCharacteristic] = []
    notes: List[str] = []

    # Lap length: prefer measured accepted-model value, else seed.
    lap_len = _num(getattr(accepted_model, "lap_length_m_model", None))
    lap_src, lap_conf = "accepted_model", "high"
    if lap_len is None:
        lap_len = _num(getattr(seed_layout, "length_m", None))
        lap_src, lap_conf = ("seed", "medium") if lap_len is not None else ("missing", "none")
    chars.append(TrackCharacteristic("lap_length_m", lap_len, lap_src, lap_conf, lap_len is not None))

    # Corner count: prefer measured model corners, else seed corners_expected.
    corners = getattr(accepted_model, "model_corners_found", None)
    corners = int(corners) if isinstance(corners, (int, float)) and corners else None
    c_src, c_conf = "accepted_model", "high"
    if not corners:
        _sc = getattr(seed_layout, "corners_expected", None)
        corners = int(_sc) if isinstance(_sc, (int, float)) and _sc else None
        c_src, c_conf = ("seed", "medium") if corners else ("missing", "none")
    chars.append(TrackCharacteristic("corner_count", corners, c_src, c_conf, bool(corners)))

    # Longest straight + elevation (seed only).
    straight = _num(getattr(seed_layout, "longest_straight_m", None))
    chars.append(TrackCharacteristic("longest_straight_m", straight,
                                     "seed" if straight is not None else "missing",
                                     "medium" if straight is not None else "none",
                                     straight is not None))
    elev = _num(getattr(seed_layout, "elevation_change_m", None))
    chars.append(TrackCharacteristic("elevation_change_m", elev,
                                     "seed" if elev is not None else "missing",
                                     "low" if elev is not None else "none", elev is not None))

    # Derived characteristics.
    corner_density = None
    if corners and lap_len and lap_len > 0:
        corner_density = round(corners / (lap_len / 1000.0), 2)
    chars.append(TrackCharacteristic("corner_density_per_km", corner_density,
                                     "derived" if corner_density is not None else "missing",
                                     "medium" if corner_density is not None else "none",
                                     corner_density is not None))
    straight_fraction = None
    if straight is not None and lap_len and lap_len > 0:
        straight_fraction = round(straight / lap_len, 3)
    chars.append(TrackCharacteristic("straight_fraction", straight_fraction,
                                     "derived" if straight_fraction is not None else "missing",
                                     "medium" if straight_fraction is not None else "none",
                                     straight_fraction is not None))

    trustworthy = bool(lap_len and corners)

    # Aero bias — the headline shaping. Straight-heavy circuits trim drag; very
    # corner-dense circuits can carry more aero; otherwise neutral. Unknown → neutral.
    aero_bias, reason = "neutral", "insufficient track data — conservative default"
    if trustworthy:
        if straight_fraction is not None and straight_fraction >= _STRAIGHT_HEAVY_FRACTION:
            aero_bias = "trim"
            reason = (f"long straight is {straight_fraction * 100:.0f}% of the lap — "
                      "trim drag rather than max downforce")
        elif corner_density is not None and corner_density >= _TWISTY_CORNERS_PER_KM:
            aero_bias = "add"
            reason = (f"corner-dense ({corner_density:.1f}/km) — more downforce helps "
                      "and drag matters less")
        else:
            aero_bias = "neutral"
            reason = "balanced circuit — neutral aero"
    else:
        notes.append("No trustworthy track model for this layout — base tune stays "
                     "track-neutral and conservative; nothing is invented.")

    return TrackTuneProfile(
        track_location_id=track_location_id, layout_id=layout_id,
        trustworthy=trustworthy, lap_length_m=lap_len, corner_count=corners,
        corner_density_per_km=corner_density, longest_straight_m=straight,
        straight_fraction=straight_fraction, elevation_change_m=elev,
        aero_bias=aero_bias, aero_bias_reason=reason,
        characteristics=chars, notes=notes,
    )
