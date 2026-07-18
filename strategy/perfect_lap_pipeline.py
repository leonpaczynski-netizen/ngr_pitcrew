"""End-to-end perfect-lap pipeline (pure): laps+frames -> coaching report.

Holistic brain — ties Phase 0 (batch telemetry) → Phase 1 (per-corner extraction)
→ Phase 2 (perfect-lap coach) into one call the UI adapter can use. Pure: the
caller supplies the laps (from ``SessionDB.get_laps_with_telemetry``), a
``frame_resolver`` (from the XYZ resolver) and the reviewed segments.
"""
from __future__ import annotations

from typing import Callable, Optional, Sequence, Tuple

from strategy.lap_corner_extraction import (
    extract_lap_corner_metrics, build_segment_corner_map,
)
from strategy.perfect_lap_coach import perfect_lap_report, PerfectLapReport
from strategy.practice_capture import resolve_clean_lap


def coach_from_laps(
    laps: Sequence[dict],
    frame_resolver: Callable[[object], Tuple[str, str]],
    segments: Sequence,
    *,
    best_ms: int = 0,
    outlier_ratio: float = 1.07,
) -> PerfectLapReport:
    """Build a PerfectLapReport from laps-with-frames.

    ``laps`` items: ``{lap_time_ms, is_pit_lap, frames: [...]}`` (extra keys
    ignored). Clean laps (valid + within ``outlier_ratio`` of best) drive the
    ideal; all laps are extracted so the median reflects real execution.
    """
    seg_map = build_segment_corner_map(segments)
    times = [int(l.get("lap_time_ms", 0) or 0) for l in laps]
    best = best_ms or min((t for t in times if t > 0), default=0)

    per_lap = []
    clean_idx = []
    for i, lap in enumerate(laps):
        frames = lap.get("frames") or []
        per_lap.append(extract_lap_corner_metrics(frames, frame_resolver, seg_map))
        if resolve_clean_lap(int(lap.get("lap_time_ms", 0) or 0), best,
                             valid=not bool(lap.get("is_pit_lap")),
                             outlier_ratio=outlier_ratio):
            clean_idx.append(i)

    return perfect_lap_report(per_lap, clean_lap_indices=clean_idx or None)
