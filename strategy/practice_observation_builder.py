"""Assemble Practice Analysis observations from slip episodes (pure, Qt-free).

UAT Finding 2 wiring. ``telemetry/slip_events.py`` already turns a lap's frames
into consolidated ``SlipEpisode`` objects (merging consecutive packets into one
episode and tagging kerb/airborne/downshift/coast suppression via
``exclusion_reason``). This module maps those per-lap episodes onto the
``EpisodeObservation`` rows the cross-lap engine consumes — resolving the issue
family and carrying the exclusion verdict through so excluded slip never becomes
a recurring authorable issue.

Duck-typed over SlipEpisode (only the attributes used are required) so it is
trivially testable with lightweight stand-ins.
"""
from __future__ import annotations

from typing import Iterable, List, Mapping, Optional, Sequence

from strategy.practice_pattern_analysis import EpisodeObservation


def _issue_type(kind: str, axle: str) -> str:
    kind = (kind or "").lower()
    axle = (axle or "").lower()
    if kind == "lockup":
        if axle in ("front", "rear"):
            return f"{axle}_lock"
        return "lockup"
    if kind == "wheelspin":
        if axle in ("front", "rear"):
            return f"{axle}_wheelspin"
        return "wheelspin"
    return kind or "unknown"


def observation_from_episode(
    episode, *, lap_number: int, is_clean: bool,
    corner_name: str = "",
) -> EpisodeObservation:
    """Map one SlipEpisode-like object to an EpisodeObservation."""
    g = lambda n, d=None: getattr(episode, n, d)
    return EpisodeObservation(
        lap_number=int(lap_number),
        is_clean=bool(is_clean),
        segment_id=str(g("segment_id", "") or ""),
        corner_name=str(corner_name or ""),
        phase=str(g("corner_phase", "") or ""),
        issue_type=_issue_type(g("kind", ""), g("axle", "")),
        duration_s=float(g("duration_s", 0.0) or 0.0),
        magnitude=float(g("max_slip", 0.0) or 0.0),
        throttle=float(g("throttle", 0.0) or 0.0),
        brake=float(g("brake", 0.0) or 0.0),
        steering=float(g("yaw_rate", 0.0) or 0.0),
        excluded=bool(g("exclusion_reason", "")),
        exclusion_reason=str(g("exclusion_reason", "") or ""),
    )


def build_observations(
    lap_episodes: Mapping[int, Iterable],
    *,
    clean_lap_numbers: Sequence[int],
    corner_names: Optional[Mapping[str, str]] = None,
) -> List[EpisodeObservation]:
    """Flatten a {lap_number: [SlipEpisode, ...]} map into observations.

    ``corner_names`` optionally maps segment_id -> display name so the engine can
    report a resolved corner. Episodes on non-clean laps are still mapped (with
    ``is_clean=False``); the engine drops them from persistence conclusions.
    """
    clean = set(int(l) for l in clean_lap_numbers)
    names = dict(corner_names or {})
    out: List[EpisodeObservation] = []
    for lap, episodes in (lap_episodes or {}).items():
        for ep in (episodes or []):
            seg = str(getattr(ep, "segment_id", "") or "")
            out.append(observation_from_episode(
                ep, lap_number=int(lap), is_clean=int(lap) in clean,
                corner_name=names.get(seg, "")))
    return out
