"""Live practice-capture helpers for the Practice Analysis engine (pure, Qt-free).

UAT Finding 2 wiring completion. These deterministic helpers let the dashboard
turn a completed lap's frames into cross-lap observations:

  * ``resolve_clean_lap`` — the canonical "is this a clean lap?" rule (valid +
    not a pace outlier). Persistence conclusions use clean laps only.
  * ``build_progress_segment_resolver`` — a ``(road_distance, speed, throttle,
    brake) -> (segment_id, phase)`` resolver over reviewed segments, so slip
    episodes resolve to a corner + phase (falls back to unresolved honestly).
  * ``segments_to_corner_names`` / ``segments_to_track_corners`` — feed corner
    names + the strong-corner candidate list to the engine.

No Qt, no I/O; the caller supplies frames, reviewed segments and lap length.
"""
from __future__ import annotations

from typing import Callable, List, Mapping, Optional, Sequence, Tuple


def resolve_clean_lap(
    lap_time_ms: int,
    best_ms: int,
    *,
    valid: bool = True,
    outlier_ratio: float = 1.07,
) -> bool:
    """A lap is clean when it is valid, has a positive time, and is not a pace
    outlier (within ``outlier_ratio`` of the session best). With no best yet,
    a valid positive lap is provisionally clean.

    Phase 5: this is now a COMPATIBILITY ADAPTER over the single canonical
    lap-validity authority (`strategy/engineering_lap_validity`) — the Practice and
    Perfect-Lap live paths route through it, so there is ONE clean-lap authority.
    Behaviour is preserved: valid + positive time + within the pace-outlier ratio.
    The engineering plausibility floor is relaxed here so this pace-focused rule
    keeps its documented semantics for the practice/perfect-lap purposes."""
    if not valid or lap_time_ms <= 0:
        return False
    import dataclasses as _dc
    from strategy.engineering_lap_validity import (
        evaluate_engineering_lap, LapPurpose, policy_for)
    pol = _dc.replace(policy_for(LapPurpose.PRACTICE_PATTERN),
                      reject_pace_outlier=True, pace_outlier_ratio=float(outlier_ratio))
    v = evaluate_engineering_lap(
        {"lap_time_ms": int(lap_time_ms or 0), "is_pit_lap": 0, "is_out_lap": 0},
        purpose=LapPurpose.PRACTICE_PATTERN, best_lap_ms=int(best_ms or 0), policy=pol)
    # This rule's contract is pace/validity only — a positive-time lap that the
    # authority flags solely as implausibly fast is still "clean" for pace purposes.
    from strategy.engineering_lap_validity import R_IMPLAUSIBLE_TIME
    if not v.accepted and set(v.rejection_reasons) <= {R_IMPLAUSIBLE_TIME}:
        # only the plausibility floor rejected it → preserve legacy pace semantics
        if best_ms and best_ms > 0:
            return lap_time_ms <= best_ms * outlier_ratio
        return True
    return v.accepted


def compute_lap_capture(
    frames,
    drivetrain: str,
    resolver: Optional[Callable[[float, float, float, float], Tuple[str, str]]],
    *,
    lap_time_ms: int,
    best_ms: int,
    valid: bool = True,
) -> Tuple[list, bool]:
    """Extract a lap's slip episodes and decide whether the lap is clean.

    Pure orchestration of the episode extractor + clean-lap rule so the dashboard
    hook is a thin store. Returns ``(episodes, is_clean)``.
    """
    from telemetry.slip_events import extract_slip_episodes
    episodes = (extract_slip_episodes(frames, drivetrain, segment_resolver=resolver)
                if frames else [])
    is_clean = resolve_clean_lap(int(lap_time_ms or 0), int(best_ms or 0), valid=valid)
    return episodes, is_clean


def _phase_of(segment_type) -> str:
    try:
        from strategy.live_corner_aggregator import phase_from_segment_type
        # The mapper keys on the enum's string value, not the enum member.
        val = getattr(segment_type, "value", segment_type)
        return phase_from_segment_type(val) or ""
    except Exception:
        # Minimal fallback mapping.
        s = str(getattr(segment_type, "value", segment_type) or "").lower()
        if "brak" in s:
            return "braking"
        if "apex" in s:
            return "apex"
        if "entry" in s:
            return "entry"
        if "exit" in s or "traction" in s:
            return "exit"
        return ""


def _is_rejected(seg) -> bool:
    st = getattr(seg, "review_status", None)
    return str(getattr(st, "value", st) or "").lower() == "rejected"


def _in_span(lp: float, start: float, end: float) -> bool:
    if start <= end:
        return start <= lp <= end
    # Wrapped span across the start/finish line.
    return lp >= start or lp <= end


def build_progress_segment_resolver(
    segments: Sequence,
    lap_length_m: float,
    offset_m: float = 0.0,
) -> Callable[[float, float, float, float], Tuple[str, str]]:
    """Return a resolver mapping road_distance -> (segment_id, phase).

    ``segments`` are reviewed segments carrying lap_progress_start/end and
    segment_type. When lap length is unknown or no segment matches, the resolver
    returns ``("", "")`` and the episode is treated as an unresolved location.
    """
    usable = [s for s in (segments or []) if not _is_rejected(s)]

    def _resolver(road_distance: float, speed_kmh: float,
                  throttle: float, brake: float, *, pos=None) -> Tuple[str, str]:
        if not usable or not lap_length_m or lap_length_m <= 0:
            return "", ""
        lp = ((float(road_distance) - float(offset_m)) / float(lap_length_m)) % 1.0
        for seg in usable:
            if _in_span(lp, float(seg.lap_progress_start), float(seg.lap_progress_end)):
                phase = _phase_of(getattr(seg, "segment_type", ""))
                if not phase:
                    continue  # straight / non-corner — keep looking
                return str(seg.segment_id), phase
        return "", ""

    return _resolver


def episodes_to_occurrences(episodes, *, lap_number: int, session_id: int = 0,
                            setup_checkpoint_id: str = "") -> List[dict]:
    """Map slip episodes (duck-typed SlipEpisode) to corner_issue_occurrence dicts
    for cross-session persistence. Pure — no DB. Both admissible and excluded
    episodes are kept (excluded carry exclusion_reason) so history stays honest.
    """
    out: List[dict] = []
    for e in (episodes or []):
        g = lambda n, d=None: getattr(e, n, d)
        out.append({
            "session_id": int(session_id or 0),
            "setup_checkpoint_id": str(setup_checkpoint_id or ""),
            "lap_number": int(lap_number),
            "segment_id": str(g("segment_id", "") or ""),
            "corner_phase": str(g("corner_phase", "") or ""),
            "issue_type": str(g("kind", "") or ""),
            "issue_subtype": str(g("subtype", "") or ""),
            "axle": str(g("axle", "") or ""),
            "duration_s": float(g("duration_s", 0.0) or 0.0),
            "severity": float(g("max_slip", 0.0) or 0.0),
            "confidence": float(g("confidence", 0.0) or 0.0),
            "throttle": float(g("throttle", 0.0) or 0.0),
            "brake": float(g("brake", 0.0) or 0.0),
            "speed_kmh": float(g("speed_kmh", 0.0) or 0.0),
            "gear": int(g("gear", 0) or 0),
            "exclusion_reason": str(g("exclusion_reason", "") or ""),
            "provenance": str(g("provenance", "") or "practice_capture"),
        })
    return out


def build_xyz_segment_resolver(
    track_location_id: str,
    layout_id: str,
    offset_calibration=None,
    name_sink: Optional[dict] = None,
) -> Callable[..., Tuple[str, str]]:
    """Return a resolver that maps a frame's world position to (segment_id, phase)
    using the PRIMARY XYZ→reference-path path (data.live_segment_resolver), the
    same matcher the live corner telemetry uses.

    ``name_sink`` (if given) is populated segment_id -> display_name as positions
    resolve, so the caller can label corners without a second disk read. Falls
    back to ("", "") when the position can't be matched — honestly unresolved.
    """
    from data.live_segment_resolver import resolve_live_segment, LivePosition

    def _resolver(road_distance: float, speed_kmh: float, throttle: float,
                  brake: float, *, pos=None) -> Tuple[str, str]:
        try:
            px = py = pz = None
            if pos is not None and len(pos) == 3:
                px, py, pz = pos
            lp = LivePosition(
                pos_x=px, pos_y=py, pos_z=pz,
                road_distance_m=float(road_distance) if road_distance is not None else None,
            )
            res = resolve_live_segment(track_location_id, layout_id, lp,
                                       offset_calibration=offset_calibration)
            match = getattr(res, "match", None)
            if match is None:
                return "", ""
            phase = _phase_of(getattr(match, "segment_type", ""))
            if not phase:
                return "", ""
            sid = str(getattr(match, "segment_id", "") or "")
            if name_sink is not None and sid:
                nm = getattr(match, "display_name", "") or ""
                if nm:
                    name_sink[sid] = str(nm)
            return sid, phase
        except Exception:
            return "", ""

    return _resolver


def segments_to_corner_names(segments: Sequence) -> dict:
    out = {}
    for s in (segments or []):
        name = getattr(s, "display_name", "") or getattr(s, "original_display_name", "")
        out[str(getattr(s, "segment_id", ""))] = str(name or "")
    return out


def segments_to_track_corners(segments: Sequence) -> List[Tuple[str, str]]:
    """Corner (apex/exit/entry/braking) segments as (segment_id, name), so the
    engine can flag consistently-clean corners as strengths. Rejected segments
    are excluded."""
    out: List[Tuple[str, str]] = []
    for s in (segments or []):
        if _is_rejected(s):
            continue
        if not _phase_of(getattr(s, "segment_type", "")):
            continue  # not a corner phase
        name = getattr(s, "display_name", "") or getattr(s, "original_display_name", "")
        out.append((str(getattr(s, "segment_id", "")), str(name or "")))
    return out
