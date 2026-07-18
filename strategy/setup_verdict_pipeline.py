"""Assemble cross-session setup verdicts from laps-with-frames (pure).

Holistic brain, Phase 3 wiring. Groups the driver's recent laps by setup revision
(newest first), builds a ``SetupRunSummary`` per setup (best/avg lap, per-corner
median apex speed, avg slip counts), and compares the two most recent setups.
Pure: caller supplies laps (batch reader), a frame_resolver and reviewed segments.
"""
from __future__ import annotations

import statistics
from typing import Callable, List, Mapping, Optional, Sequence, Tuple

from strategy.lap_corner_extraction import (
    extract_lap_corner_metrics, build_segment_corner_map,
)
from strategy.setup_session_verdict import (
    SetupRunSummary, SetupVerdict, compare_setups, MIN_LAPS,
)


def summarise_runs_by_setup(
    laps: Sequence[dict],
    frame_resolver: Callable[[object], Tuple[str, str]],
    segments: Sequence,
    labels: Optional[Mapping] = None,
) -> List[Tuple[object, SetupRunSummary]]:
    """[(setup_id, SetupRunSummary)] grouped by setup, newest-first.

    ``laps`` are the batch-reader rows (newest first), each with ``setup_id,
    lap_time_ms, is_pit_lap, wheelspin_count, lock_up_count, frames``.
    """
    seg_map = build_segment_corner_map(segments)
    labels = dict(labels or {})
    groups: dict = {}
    order: List = []
    for lap in laps:
        sid = lap.get("setup_id", 0)
        if sid not in groups:
            groups[sid] = []
            order.append(sid)
        groups[sid].append(lap)

    out: List[Tuple[object, SetupRunSummary]] = []
    for sid in order:
        glaps = groups[sid]
        times = [int(l.get("lap_time_ms", 0) or 0) for l in glaps
                 if int(l.get("lap_time_ms", 0) or 0) > 0 and not l.get("is_pit_lap")]
        if not times:
            continue
        apex_by_corner: dict = {}
        for lap in glaps:
            for m in extract_lap_corner_metrics(
                    lap.get("frames") or [], frame_resolver, seg_map):
                if m.min_speed_kmh:
                    apex_by_corner.setdefault(m.corner_name, []).append(m.min_speed_kmh)
        per_corner = {k: round(statistics.median(v), 1)
                      for k, v in apex_by_corner.items() if v}
        spins = [float(l.get("wheelspin_count", 0) or 0) for l in glaps]
        locks = [float(l.get("lock_up_count", 0) or 0) for l in glaps]
        out.append((sid, SetupRunSummary(
            label=str(labels.get(sid, f"Setup {sid}")),
            laps=len(times), best_ms=min(times),
            avg_ms=int(statistics.mean(times)),
            per_corner_apex_kmh=per_corner,
            avg_wheelspin=round(statistics.mean(spins), 2) if spins else 0.0,
            avg_lockup=round(statistics.mean(locks), 2) if locks else 0.0)))
    return out


def build_verdict_from_laps(
    laps: Sequence[dict],
    frame_resolver: Callable[[object], Tuple[str, str]],
    segments: Sequence,
    *,
    labels: Optional[Mapping] = None,
    changes: Sequence = (),
    feedback_vs_previous: str = "",
) -> Optional[SetupVerdict]:
    """Compare the two most-recent setups. None if fewer than two qualify."""
    runs = summarise_runs_by_setup(laps, frame_resolver, segments, labels)
    runs = [r for r in runs if r[1].laps >= 1]
    if len(runs) < 2:
        return None
    cur = runs[0][1]     # newest (laps are newest-first)
    prev = runs[1][1]
    return compare_setups(prev, cur, changes=changes,
                          feedback_vs_previous=feedback_vs_previous)
