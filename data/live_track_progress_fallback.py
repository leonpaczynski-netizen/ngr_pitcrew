"""Group 58 — Road-Distance Fallback for live track progress (pure).

WHY IT EXISTS
  Groups 56/57 resolve live lap progress by map-matching a live world position to
  an APPROVED reference path (MEDIUM/HIGH confidence). When no approved reference
  path is available, there is no progress at all. This module adds a SAFE, clearly
  labelled, LOWER-confidence fallback: estimate normalised progress from GT7's
  cumulative ``road_distance`` and a TRUSTED lap length.

WHAT THIS MODULE IS
  A pure, deterministic numeric resolver. It never map-matches, never touches a
  reference path, and returns a Group 56 ``LiveTrackProgressResult`` tagged with
  ``source = "road_distance_fallback"`` so the pipeline can tell it apart.

HARD SAFETY RULES (Group 58)
  • It NEVER returns HIGH confidence (fallback is always approximate).
  • It NEVER creates a pit event or mutates a pit count — it is display-only
    evidence and is deliberately NOT fed into pit-lane corroboration (the live
    adapter blocks fallback progress from lifting pit confidence).
  • A known identity mismatch → UNKNOWN (never usable).
  • Missing / invalid / NaN / inf / negative inputs → UNKNOWN (never guessed).
  • It does not override a usable approved-reference-path result — precedence is
    enforced by the caller (build_live_replan_snapshot).
  • No Qt, no DB, no AI, no filesystem. Never raises.
"""
from __future__ import annotations

from typing import Optional

from data.live_track_progress import (
    LiveTrackProgressResult,
    TrackProgressConfidence,
)

# Provenance tag distinguishing fallback progress from map-matched progress.
FALLBACK_SOURCE = "road_distance_fallback"

# A lap_distance up to this fraction over one lap is tolerated before wrapping.
_LAP_OVERRUN_TOL = 0.02


def _finite(v) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return f


def _unknown(message: str, warning: str, track_id: str, layout_id: str
             ) -> LiveTrackProgressResult:
    return LiveTrackProgressResult(
        progress=None, distance_along_lap_m=None,
        confidence=TrackProgressConfidence.UNKNOWN,
        source=FALLBACK_SOURCE, message=message,
        warnings=(warning,) if warning else (),
        track_id=str(track_id or ""), layout_id=str(layout_id or ""),
    )


def resolve_progress_from_road_distance(
    *,
    lap_distance_m=None,
    road_distance=None,
    lap_length_m=None,
    identity_ok: bool = True,
    track_id: Optional[str] = None,
    layout_id: Optional[str] = None,
) -> LiveTrackProgressResult:
    """Estimate normalised lap progress from road distance. Never raises.

    Preferred input is ``lap_distance_m`` (distance travelled on the CURRENT lap,
    already lap-relative). If only the cumulative ``road_distance`` is known, a
    cruder ``road_distance mod lap_length`` estimate is used (always LOW).

    Confidence (never HIGH):
      MEDIUM — accurate lap-relative distance, in-bounds, trusted lap length, identity known.
      LOW    — value had to wrap, or only cumulative road_distance was available.
      UNKNOWN— missing/invalid road distance or lap length, or identity mismatch.
    """
    tid = str(track_id or "")
    lid = str(layout_id or "")

    # Identity mismatch → never usable.
    if not identity_ok:
        return _unknown(
            "Road-distance fallback not used — reference identity mismatch.",
            "reference path track/layout mismatch", tid, lid)

    lap = _finite(lap_length_m)
    if lap is None:
        return _unknown(
            "Road-distance fallback unavailable — trusted lap length is unknown.",
            "lap length unavailable for road-distance fallback", tid, lid)
    if lap <= 0:
        return _unknown(
            "Road-distance fallback unavailable — lap length is invalid.",
            "lap length invalid for road-distance fallback", tid, lid)

    ld = _finite(lap_distance_m)
    if ld is not None and ld < 0:
        ld = None
    rd = _finite(road_distance)
    if rd is not None and rd < 0:
        rd = None

    if ld is None and rd is None:
        return _unknown(
            "Road-distance fallback unavailable — no valid road-distance signal.",
            "road-distance signal unavailable", tid, lid)

    warnings = ["fallback progress is approximate and lower confidence than map matching"]

    if ld is not None:
        dist_along = ld
        wrapped = False
        if dist_along > lap * (1.0 + _LAP_OVERRUN_TOL):
            dist_along = dist_along % lap
            wrapped = True
            warnings.append("road-distance value wrapped to estimate lap position")
        conf = TrackProgressConfidence.LOW if wrapped else TrackProgressConfidence.MEDIUM
    else:
        # Only cumulative road_distance — no lap-start reference, so mod-estimate.
        dist_along = rd % lap
        wrapped = True
        conf = TrackProgressConfidence.LOW
        warnings.append(
            "no lap-start reference — using cumulative road distance modulo lap length")

    progress = (dist_along / lap) % 1.0
    if progress < 0.0:
        progress += 1.0

    pct = f"{progress * 100.0:.1f}%"
    conf_word = conf.value.lower()
    message = (f"Track progress {pct} via GT7 road-distance fallback "
               f"(approximate, {conf_word} confidence — lower than map matching).")

    return LiveTrackProgressResult(
        progress=progress,
        distance_along_lap_m=dist_along,
        nearest_station_index=None, nearest_distance_m=None, lateral_offset_m=None,
        confidence=conf, source=FALLBACK_SOURCE, message=message,
        warnings=tuple(warnings), track_id=tid, layout_id=lid,
    )


def is_fallback_result(result) -> bool:
    """True when a LiveTrackProgressResult came from the road-distance fallback."""
    return bool(result is not None and getattr(result, "source", "") == FALLBACK_SOURCE)


def format_road_distance_fallback_evidence(result) -> dict:
    """Return {'found', 'missing', 'warnings'} lines for a fallback result.

    Driver-readable, honest, and always labels the value as approximate/lower
    confidence. No command wording.
    """
    found: list = []
    missing: list = []
    warnings: list = []
    try:
        if result is None:
            return {"found": [], "missing": ["track progress unavailable"], "warnings": []}
        if result.has_progress and result.progress is not None:
            found.append(
                f"track progress: {result.progress * 100.0:.1f}% via GT7 road-distance fallback")
            if result.distance_along_lap_m is not None:
                found.append(f"distance along lap: {result.distance_along_lap_m:,.0f} m (fallback)")
            found.append(f"progress confidence: {result.confidence.value} (fallback)")
            found.append("approved reference path unavailable for this track/layout")
            found.append(
                "fallback progress is approximate and lower confidence than map matching")
        else:
            missing.append(
                "no approved reference path or usable road-distance signal was available")
        for w in (result.warnings or ()):
            if w not in warnings:
                warnings.append(w)
        return {"found": found, "missing": missing, "warnings": warnings}
    except Exception:
        return {"found": [], "missing": ["track progress unavailable"], "warnings": []}
