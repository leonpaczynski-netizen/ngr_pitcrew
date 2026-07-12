"""Phase 1 — Continuous track-model refinement (candidate build + gate + promote).

Turns live-captured event laps (``data/live_track_path_capture.py``) into a
NON-DESTRUCTIVE *candidate* model, gates it against the accepted model, and only
ever replaces the accepted model through an explicit, gated ``promote_candidate``.

Safety invariants (see ``docs/DESIGN_continuous_track_refinement.md`` §9):
  * S1  the accepted model is written ONLY by ``promote_candidate`` (atomic).
  * S2  a worse-or-equal candidate is never promotable — ``compare_models``
        reports ``improves=False`` and the caller must not promote it.
  * S3  live features read the accepted model only; the candidate is a sibling
        file, invisible to them until promoted.
  * S4  every refinement round is logged to the ledger with why laps were used
        or dropped (no silent contamination).
  * S5  a candidate whose ``base_accepted_at`` != the current accepted model's is
        stale and is rebuilt, never promoted.

Reuses the existing calibration pipeline unchanged: captured laps →
``build_reference_path`` → ``build_track_station_map`` → ``align_track_model`` →
``export_accepted_model_json``.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional, Tuple

from data.track_calibration import (
    CalibrationSession,
    ReferencePath,
    ReferencePathPoint,
    build_reference_path,
)
from data.track_station_map import (
    TrackStationMap,
    STATION_MODELS_DIR,
    build_track_station_map,
)
from data.track_model_alignment import (
    ACCEPTED_MODEL_SCHEMA,
    SectorAlignmentResult,
    TrackModelAlignmentResult,
    TrackModelMatchStatus,
    align_track_model,
    export_accepted_model_json,
    find_accepted_model_path,
    import_accepted_model_json,
)

CANDIDATE_SCHEMA: str = "candidate_track_model_v1"

# Match-status quality ranking (higher = better). Used by the non-regression gate.
_MATCH_RANK: dict = {
    "NOT_READY": 0,
    "FAILED_MATCH": 1,
    "PARTIAL_MATCH": 2,
    "GOOD_MATCH": 3,
    "ACCEPTABLE_MATCH": 4,
}

_CONF_EPS = 1e-3            # confidence changes below this are treated as noise
_LAP_DELTA_IMPROVE_PP = 0.05   # lap-length delta must close by ≥0.05pp to count as improvement

# Phase 2·0 geometry-shift guard: a candidate whose averaged path sits more than
# this far (mean horizontal displacement, metres) from the accepted path is not a
# refinement — it's contamination or a materially different racing line. Hard block.
MAX_MEAN_SHIFT_M: float = 3.0
CANDIDATE_REF_PATH_SCHEMA: str = "candidate_reference_path_v1"

# Phase 2B weighted anchoring: event laps may only NUDGE an established model.
# The candidate path is blended toward the accepted path so event laps contribute
# at most EVENT_WEIGHT_DEFAULT of each point — a bad session can't overturn a
# calibrated model, but consistent laps still refine it.
EVENT_WEIGHT_DEFAULT: float = 0.30


def _xyz_list(points) -> "List[tuple]":
    """Extract (x, y, z) tuples from objects, dicts, or plain (x, y, z) sequences."""
    out: List[tuple] = []
    for p in points or []:
        try:
            if isinstance(p, dict):
                out.append((float(p["x"]), float(p.get("y", 0.0)), float(p["z"])))
            elif isinstance(p, (tuple, list)) and len(p) >= 3:
                out.append((float(p[0]), float(p[1]), float(p[2])))
            else:
                out.append((float(p.x), float(getattr(p, "y", 0.0)), float(p.z)))
        except (KeyError, TypeError, ValueError, AttributeError, IndexError):
            continue
    return out


def _resample_indices(n: int, k: int) -> "List[int]":
    if n <= 0:
        return []
    if n <= k:
        return list(range(n))
    return [round(i * (n - 1) / (k - 1)) for i in range(k)]


def mean_path_shift_m(points_a, points_b, k: int = 200) -> Optional[float]:
    """Mean horizontal (X/Z) displacement between two ordered lap paths.

    Both paths are averaged reference paths normalised S/F→S/F in the same
    direction, so index-alignment approximates progress-alignment. Coarse by
    design (a contamination guard, not a fit metric): both are resampled to at
    most ``k`` evenly-spaced points. Returns None when either path is too short.
    """
    a = _xyz_list(points_a)
    b = _xyz_list(points_b)
    if len(a) < 2 or len(b) < 2:
        return None
    m = min(k, len(a), len(b))
    ia = _resample_indices(len(a), m)
    ib = _resample_indices(len(b), m)
    total = 0.0
    for i in range(m):
        ax, _ay, az = a[ia[i]]
        bx, _by, bz = b[ib[i]]
        total += math.hypot(ax - bx, az - bz)
    return total / m if m else None


def _load_accepted_path_points(track_location_id: str, layout_id: str) -> "List[tuple]":
    """Best-effort load of the accepted reference-path geometry (for the shift guard).

    Returns [] when no approved reference path can be resolved — the caller then
    skips the geometry guard (the scalar-metric gate still applies).
    """
    try:
        from data.reference_path_loader import (
            load_reference_path_for_layout,
            reference_path_to_track_stations,
        )
        res = load_reference_path_for_layout(track_location_id, layout_id)
        if not getattr(res, "has_stations", False):
            return []
        return _xyz_list(reference_path_to_track_stations(res.asset))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ImprovementVerdict:
    """Outcome of the non-regression + improvement gate."""
    improves: bool
    improvement_reasons: List[str] = field(default_factory=list)
    regression_reasons: List[str] = field(default_factory=list)


@dataclass
class RefinementResult:
    """Outcome of one refinement round (candidate built, NOT promoted)."""
    success: bool
    reason: str = ""                                   # why refinement couldn't run
    candidate_align: Optional[TrackModelAlignmentResult] = None
    accepted_align: Optional[TrackModelAlignmentResult] = None
    verdict: Optional[ImprovementVerdict] = None
    contributing_laps: int = 0
    contributing_cars: List[str] = field(default_factory=list)
    candidate_path: Optional[Path] = None
    warnings: List[str] = field(default_factory=list)

    @property
    def promotable(self) -> bool:
        return bool(self.success and self.verdict and self.verdict.improves)


# ---------------------------------------------------------------------------
# Filenames
# ---------------------------------------------------------------------------

def candidate_model_filename(track_location_id: str, layout_id: str) -> str:
    return f"{track_location_id}__{layout_id}.candidate_model.json"


def refinement_ledger_filename(track_location_id: str, layout_id: str) -> str:
    return f"{track_location_id}__{layout_id}.refinement_ledger.jsonl"


def find_candidate_model_path(
    track_location_id: str, layout_id: str, base_dir: Optional[Path] = None
) -> Optional[Path]:
    d = Path(base_dir) if base_dir else STATION_MODELS_DIR
    p = d / candidate_model_filename(track_location_id, layout_id)
    return p if p.exists() else None


REVIEW_PENDING_SUBDIR: str = "_refine_pending"  # staged (resolver-invisible) reviewed segments


def candidate_reference_path_filename(track_location_id: str, layout_id: str) -> str:
    return f"{track_location_id}__{layout_id}.candidate_reference_path.json"


def _staged_review_path(track_location_id: str, layout_id: str, models_dir: Path) -> Path:
    # export_review_json builds "<loc>__<lay>__reviewed_segments__<sid>.json".
    return (Path(models_dir) / REVIEW_PENDING_SUBDIR /
            f"{track_location_id}__{layout_id}__reviewed_segments__pending.json")


def _stage_reviewed_segments(session, station_map, accepted_align,
                             track_location_id: str, layout_id: str, models_dir: Path) -> bool:
    """Phase 2C: detect segments from the (blended) candidate + event laps and stage a
    CONFIRMED reviewed-segments file where the resolver can't see it yet. Best-effort:
    returns False (and stages nothing) on any failure or a degenerate detection."""
    try:
        from data.track_segment_detection import detect_track_segments
        from data.track_segment_review import (
            create_review_from_detection, export_review_json, SegmentReviewStatus,
        )
        seed = SimpleNamespace(
            corners_expected=accepted_align.seed_corners_expected,
            length_m=accepted_align.lap_length_m_seed, sectors=None,
        )
        detection = detect_track_segments(session, layout_seed=seed, station_map=station_map)
        if not getattr(detection, "segments", None):
            return False  # nothing usable — never stage an empty review
        review = create_review_from_detection(detection)
        for seg in review.segments:
            if seg.review_status == SegmentReviewStatus.UNREVIEWED:
                seg.review_status = SegmentReviewStatus.CONFIRMED
        review.track_location_id = track_location_id
        review.layout_id = layout_id
        pending_dir = Path(models_dir) / REVIEW_PENDING_SUBDIR
        export_review_json(review, output_dir=pending_dir, session_id="pending")
        return True
    except Exception:
        return False


def _publish_staged_review(track_location_id: str, layout_id: str,
                           models_dir: Path, min_segments: int = 0) -> bool:
    """Phase 2C: publish the staged reviewed-segments as the live (resolver-visible)
    file with a fresh timestamp (newest wins). Guarded: never publishes fewer
    segments than ``min_segments`` (won't downgrade the AI-ready model)."""
    pending = _staged_review_path(track_location_id, layout_id, models_dir)
    if not pending.exists():
        return False
    try:
        from data.track_segment_review import import_review_json, export_review_json
        review = import_review_json(pending)
        if review is None or len(getattr(review, "segments", []) or []) < max(0, min_segments):
            return False  # would downgrade — leave the existing reviewed segments intact
        export_review_json(review, output_dir=Path(models_dir))  # default sid = now() → newest
        try:
            pending.unlink()
        except OSError:  # pragma: no cover - defensive
            pass
        return True
    except Exception:
        return False


def detect_candidate_pit_lane(session: CalibrationSession, station_map) -> Optional[dict]:
    """Phase 2D: detect the pit-lane corridor from event PIT laps against the
    candidate station map. Returns a small dict (entry/exit station + progress +
    pit-lap count) for visibility, or None when no pit laps / no detection.

    Detection only — this does NOT write to the strategy pit-lane store (that
    write needs live validation of the Group-55 segment schema/confidence and is
    deferred). It surfaces to the user in the refinement Review panel.
    """
    try:
        pit_laps = [lap for lap in getattr(session, "laps", []) if getattr(lap, "is_pit_lap", False)]
        if not pit_laps or station_map is None:
            return None
        from data.track_station_map import detect_pit_lane_from_pit_laps
        boundary = detect_pit_lane_from_pit_laps(pit_laps, station_map)
        if boundary is None:
            return None
        lap_len = float(getattr(station_map, "lap_length_m", 0.0) or 0.0)
        entry_m = float(boundary.entry_station_m)
        exit_m = float(boundary.exit_station_m)
        out = {
            "entry_station_m": round(entry_m, 1),
            "exit_station_m": round(exit_m, 1),
            "source_pit_laps": len(pit_laps),
        }
        if lap_len > 0:
            out["entry_progress"] = round(max(0.0, min(1.0, entry_m / lap_len)), 4)
            out["exit_progress"] = round(max(0.0, min(1.0, exit_m / lap_len)), 4)
        return out
    except Exception:
        return None


def _remove_staged_review(track_location_id: str, layout_id: str, models_dir: Optional[Path]) -> None:
    pending = _staged_review_path(track_location_id, layout_id,
                                  Path(models_dir) if models_dir else STATION_MODELS_DIR)
    try:
        if pending.exists():
            pending.unlink()
    except OSError:  # pragma: no cover - defensive
        pass


def find_candidate_reference_path(
    track_location_id: str, layout_id: str, base_dir: Optional[Path] = None
) -> Optional[Path]:
    d = Path(base_dir) if base_dir else STATION_MODELS_DIR
    p = d / candidate_reference_path_filename(track_location_id, layout_id)
    return p if p.exists() else None


def export_candidate_reference_path(
    reference_path, track_location_id: str, layout_id: str, output_dir: Optional[Path] = None
) -> Optional[Path]:
    """Persist the candidate's averaged path geometry (companion to the candidate
    model) so promotion / reviewed-segment regen (Phase 2C) can rebuild from it."""
    pts = _xyz_list(getattr(reference_path, "points", None) or [])
    if not pts:
        return None
    out_dir = Path(output_dir) if output_dir else STATION_MODELS_DIR
    path = out_dir / candidate_reference_path_filename(track_location_id, layout_id)
    _atomic_write_json(path, {
        "schema": CANDIDATE_REF_PATH_SCHEMA,
        "track_location_id": track_location_id,
        "layout_id": layout_id,
        "points": [{"x": x, "y": y, "z": z} for (x, y, z) in pts],
    })
    return path


def _remove_candidate_reference_path(
    track_location_id: str, layout_id: str, models_dir: Optional[Path] = None
) -> None:
    p = find_candidate_reference_path(track_location_id, layout_id, base_dir=models_dir)
    if p is not None:
        try:
            p.unlink()
        except OSError:
            pass


def _status_str(status) -> str:
    return getattr(status, "value", None) or str(status)


# ---------------------------------------------------------------------------
# Candidate persistence (accepted-model-shaped payload + refinement extras)
# ---------------------------------------------------------------------------

def _align_payload(result: TrackModelAlignmentResult, loc: str, lay: str) -> dict:
    """The accepted-model field set (mirrors export_accepted_model_json)."""
    return {
        "track_location_id":      loc,
        "layout_id":              lay,
        "match_status":           _status_str(result.match_status),
        "accepted":               result.accepted,
        "accepted_at":            result.accepted_at,
        "seed_corners_expected":  result.seed_corners_expected,
        "model_corners_found":    result.model_corners_found,
        "extra_peaks_suppressed": result.extra_peaks_suppressed,
        "placeholder_count":      result.placeholder_count,
        "lap_length_m_model":     result.lap_length_m_model,
        "lap_length_m_seed":      result.lap_length_m_seed,
        "lap_length_delta_pct":   result.lap_length_delta_pct,
        "station_count":          result.station_count,
        "confidence":             result.confidence,
        "blockers":               result.blockers,
        "warnings":               result.warnings,
        "seed_corner_positions_available": result.seed_corner_positions_available,
        "corner_position_match":  result.corner_position_match,
        "corners_matched":        result.corners_matched,
    }


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, path)


def export_candidate_model_json(
    result: TrackModelAlignmentResult,
    track_location_id: str,
    layout_id: str,
    extras: dict,
    output_dir: Optional[Path] = None,
) -> Path:
    """Persist a candidate model (accepted-model payload + refinement extras)."""
    out_dir = Path(output_dir) if output_dir else STATION_MODELS_DIR
    path = out_dir / candidate_model_filename(track_location_id, layout_id)
    payload = {"schema": CANDIDATE_SCHEMA}
    payload.update(_align_payload(result, track_location_id, layout_id))
    payload.update(extras or {})
    _atomic_write_json(path, payload)
    return path


def import_candidate_alignment(path) -> Optional[TrackModelAlignmentResult]:
    """Reconstruct a TrackModelAlignmentResult from a candidate file (for promotion)."""
    try:
        p = Path(path)
        if not p.exists():
            return None
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if data.get("schema") not in (CANDIDATE_SCHEMA, ACCEPTED_MODEL_SCHEMA):
            return None
        return TrackModelAlignmentResult(
            match_status           = TrackModelMatchStatus(data.get("match_status", "NOT_READY")),
            seed_corners_expected  = data.get("seed_corners_expected", 0),
            model_corners_found    = data.get("model_corners_found", 0),
            extra_peaks_suppressed = data.get("extra_peaks_suppressed", 0),
            placeholder_count      = data.get("placeholder_count", 0),
            lap_length_m_model     = data.get("lap_length_m_model", 0.0),
            lap_length_m_seed      = data.get("lap_length_m_seed", 0.0),
            lap_length_delta_pct   = data.get("lap_length_delta_pct", 0.0),
            station_count          = data.get("station_count", 0),
            confidence             = data.get("confidence", 0.0),
            corner_alignments      = [],
            sector_alignment       = SectorAlignmentResult(0, "not_available", "Loaded from candidate"),
            blockers               = data.get("blockers", []),
            warnings               = data.get("warnings", []),
            accepted               = False,
            accepted_at            = data.get("accepted_at", ""),
            seed_corner_positions_available = bool(data.get("seed_corner_positions_available", False)),
            corner_position_match  = data.get("corner_position_match", "NOT_AVAILABLE"),
            corners_matched        = data.get("corners_matched", 0),
        )
    except Exception:
        return None


def append_refinement_ledger(
    track_location_id: str, layout_id: str, entry: dict, models_dir: Optional[Path] = None
) -> None:
    """Append one honest audit line about a refinement round (best-effort)."""
    d = Path(models_dir) if models_dir else STATION_MODELS_DIR
    try:
        d.mkdir(parents=True, exist_ok=True)
        line = dict(entry)
        line.setdefault("ts", datetime.now(timezone.utc).isoformat())
        with open(d / refinement_ledger_filename(track_location_id, layout_id), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(line, ensure_ascii=False) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Candidate build + gate
# ---------------------------------------------------------------------------

def _acc_index(i: int, n_cand: int, n_acc: int) -> int:
    """Map candidate index i (0..n_cand-1) to the aligned accepted index."""
    if n_cand <= 1:
        return 0
    return max(0, min(n_acc - 1, round(i * (n_acc - 1) / (n_cand - 1))))


def blend_reference_path(ref_path: ReferencePath, accepted_xyz, event_weight: float) -> ReferencePath:
    """Blend a candidate reference path toward the accepted path (Phase 2B).

    Returns a new ReferencePath whose points are
    ``event_weight * candidate + (1 - event_weight) * accepted`` (index-aligned,
    both ordered S/F→S/F). ``event_weight`` is clamped to [0, 1]; the accepted
    path is index-mapped to the candidate length. Returns ``ref_path`` unchanged
    when there is nothing to blend (no accepted geometry, or weight ≥ 1)."""
    acc = _xyz_list(accepted_xyz)
    w = max(0.0, min(1.0, float(event_weight)))
    cand_pts = list(getattr(ref_path, "points", []) or [])
    if len(acc) < 2 or len(cand_pts) < 2 or w >= 1.0:
        return ref_path
    n_cand, n_acc = len(cand_pts), len(acc)
    blended: List[ReferencePathPoint] = []
    for i, cp in enumerate(cand_pts):
        ax, ay, az = acc[_acc_index(i, n_cand, n_acc)]
        blended.append(ReferencePathPoint(
            lap_progress=cp.lap_progress,
            distance_along_lap_m=cp.distance_along_lap_m,
            x=w * cp.x + (1.0 - w) * ax,
            y=w * cp.y + (1.0 - w) * ay,
            z=w * cp.z + (1.0 - w) * az,
            speed_kph_avg=cp.speed_kph_avg,
            source_lap_count=cp.source_lap_count,
            yaw_rate_avg=cp.yaw_rate_avg,
        ))
    return ReferencePath(
        track_location_id=ref_path.track_location_id,
        layout_id=ref_path.layout_id,
        calibration_car_id=ref_path.calibration_car_id,
        source_lap_count=ref_path.source_lap_count,
        points=blended,
        confidence=ref_path.confidence,
        warnings=list(getattr(ref_path, "warnings", []) or []),
    )


def build_candidate_alignment(
    session: CalibrationSession,
    accepted_align: TrackModelAlignmentResult,
    anchor_points=None,
    event_weight: Optional[float] = None,
) -> Tuple[Optional[TrackModelAlignmentResult], Optional[TrackStationMap], object]:
    """Build a candidate alignment from captured laps, using the accepted model's
    seed truth (corners_expected / seed lap length).

    When ``anchor_points`` (the accepted path geometry) is supplied, the built
    path is blended toward it at ``event_weight`` (Phase 2B) so event laps only
    nudge an established model. Returns (candidate_align | None, station_map |
    None, build_result)."""
    seed = SimpleNamespace(
        corners_expected=accepted_align.seed_corners_expected,
        length_m=accepted_align.lap_length_m_seed,
        sectors=None,
    )
    build_result = build_reference_path(session)
    ref_path = getattr(build_result, "reference_path", None)
    if not getattr(build_result, "success", False) or ref_path is None or not ref_path.points:
        return None, None, build_result
    if anchor_points and event_weight is not None:
        ref_path = blend_reference_path(ref_path, anchor_points, event_weight)
    station_map = build_track_station_map(ref_path, seed)
    candidate_align = align_track_model(station_map, seed)
    # Expose the (possibly blended) path used, so callers persist the real geometry.
    try:
        build_result.reference_path = ref_path
    except Exception:  # pragma: no cover - defensive (namedtuple/frozen)
        pass
    return candidate_align, station_map, build_result


def compare_models(
    accepted: TrackModelAlignmentResult,
    candidate: TrackModelAlignmentResult,
    geometry_shift_m: Optional[float] = None,
) -> ImprovementVerdict:
    """Non-regression + improvement gate. ``improves`` is True only when the
    candidate does NOT regress on any hard axis AND improves ≥1 axis.

    ``geometry_shift_m`` (Phase 2·0), when provided, is the mean horizontal
    displacement of the candidate path from the accepted path; a shift beyond
    ``MAX_MEAN_SHIFT_M`` is a hard block (contamination / different line)."""
    regression: List[str] = []
    improvement: List[str] = []

    # --- Geometry-shift guard (Phase 2·0) ---
    if geometry_shift_m is not None and geometry_shift_m > MAX_MEAN_SHIFT_M:
        regression.append(
            f"path shifted {geometry_shift_m:.1f}m from the accepted model "
            f"(> {MAX_MEAN_SHIFT_M:.0f}m — likely contamination or a different line)"
        )

    # --- Hard non-regression blocks ---
    if candidate.model_corners_found < accepted.model_corners_found:
        regression.append(
            f"fewer corners ({candidate.model_corners_found} < {accepted.model_corners_found})"
        )
    acc_rank = _MATCH_RANK.get(_status_str(accepted.match_status), 0)
    cand_rank = _MATCH_RANK.get(_status_str(candidate.match_status), 0)
    if cand_rank < acc_rank:
        regression.append(
            f"weaker match ({_status_str(candidate.match_status)} < {_status_str(accepted.match_status)})"
        )
    if candidate.confidence < accepted.confidence - _CONF_EPS:
        regression.append(
            f"lower confidence ({candidate.confidence:.3f} < {accepted.confidence:.3f})"
        )
    if candidate.placeholder_count > accepted.placeholder_count:
        regression.append(
            f"more placeholder corners ({candidate.placeholder_count} > {accepted.placeholder_count})"
        )

    # --- Improvement axes (≥1 required) ---
    acc_delta = abs(accepted.lap_length_delta_pct)
    cand_delta = abs(candidate.lap_length_delta_pct)
    if cand_delta < acc_delta - _LAP_DELTA_IMPROVE_PP:
        improvement.append(
            f"lap length closer to seed ({cand_delta:.2f}% vs {acc_delta:.2f}%)"
        )
    if candidate.model_corners_found > accepted.model_corners_found:
        improvement.append(
            f"more corners found ({candidate.model_corners_found} > {accepted.model_corners_found})"
        )
    if candidate.confidence > accepted.confidence + _CONF_EPS:
        improvement.append(
            f"higher confidence ({candidate.confidence:.3f} > {accepted.confidence:.3f})"
        )

    improves = (not regression) and bool(improvement)
    return ImprovementVerdict(improves, improvement, regression)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def refine_from_session(
    session: CalibrationSession,
    track_location_id: str,
    layout_id: str,
    *,
    contributing_cars: Optional[List[str]] = None,
    source_session_ids: Optional[List[int]] = None,
    models_dir: Optional[Path] = None,
    event_weight: float = EVENT_WEIGHT_DEFAULT,
) -> RefinementResult:
    """Build (never promote) a candidate model from captured event laps.

    Requires an existing accepted model (else refinement is a no-op — there is
    nothing to refine). Event laps are anchored to the accepted geometry at
    ``event_weight`` (Phase 2B) so they nudge, not overturn. Writes the candidate
    file + a ledger line. The caller decides whether to ``promote_candidate``
    based on ``result.promotable``.
    """
    mdir = Path(models_dir) if models_dir else STATION_MODELS_DIR
    cars = sorted({c.strip() for c in (contributing_cars or []) if c and c.strip()})

    accepted_path = find_accepted_model_path(track_location_id, layout_id, base_dir=mdir)
    if accepted_path is None:
        return RefinementResult(False, "no accepted model to refine")
    accepted_align = import_accepted_model_json(accepted_path)
    if accepted_align is None:
        return RefinementResult(False, "accepted model unreadable")

    # Accepted geometry (for anchoring + the shift guard); [] when unresolved, in
    # which case anchoring is skipped and the candidate is event-laps-only.
    accepted_points = _load_accepted_path_points(track_location_id, layout_id)

    try:
        candidate_align, candidate_station_map, build_result = build_candidate_alignment(
            session, accepted_align,
            anchor_points=(accepted_points or None),
            event_weight=(event_weight if accepted_points else None),
        )
    except Exception as exc:  # pragma: no cover - defensive
        append_refinement_ledger(track_location_id, layout_id, {
            "decision": "build_error", "error": str(exc), "cars": cars,
        }, models_dir=mdir)
        return RefinementResult(False, f"candidate build failed: {exc}", accepted_align=accepted_align)

    if candidate_align is None:
        reason = "; ".join(getattr(build_result, "errors", []) or []) or "no usable laps captured"
        append_refinement_ledger(track_location_id, layout_id, {
            "decision": "no_candidate", "reason": reason,
            "usable_laps": getattr(build_result, "usable_lap_count", 0),
            "rejected_laps": getattr(build_result, "rejected_lap_count", 0),
            "cars": cars,
        }, models_dir=mdir)
        return RefinementResult(False, reason, accepted_align=accepted_align,
                                warnings=list(getattr(build_result, "warnings", [])))

    # Phase 2·0 geometry-shift guard: mean horizontal displacement of the
    # candidate path from the accepted path (None when accepted geometry can't be
    # resolved — the scalar-metric gate still applies). With Phase 2B anchoring
    # this stays small by construction, but still guards pathological cases.
    geometry_shift_m: Optional[float] = None
    try:
        _cand_pts = getattr(build_result.reference_path, "points", None)
        if accepted_points and _cand_pts:
            geometry_shift_m = mean_path_shift_m(accepted_points, _cand_pts)
    except Exception:
        geometry_shift_m = None

    verdict = compare_models(accepted_align, candidate_align, geometry_shift_m=geometry_shift_m)
    usable = int(getattr(build_result, "usable_lap_count", 0))

    # Phase 2D: detect a pit-lane corridor from event pit laps (visibility only).
    pit_lane_detected = detect_candidate_pit_lane(session, candidate_station_map)

    extras = {
        "base_accepted_at":   accepted_align.accepted_at,
        "contributing_laps":  usable,
        "contributing_cars":  cars,
        "source_sessions":    list(source_session_ids or []),
        "improves":           verdict.improves,
        "improvement_reasons": verdict.improvement_reasons,
        "regression_reasons": verdict.regression_reasons,
        "geometry_shift_m":   geometry_shift_m,
        "event_weight":       (event_weight if accepted_points else 1.0),
        "anchored":           bool(accepted_points),
        "pit_lane_detected":  pit_lane_detected,
        "delta_vs_accepted": {
            "corner_match_delta": candidate_align.model_corners_found - accepted_align.model_corners_found,
            "lap_length_delta_pct_change": candidate_align.lap_length_delta_pct - accepted_align.lap_length_delta_pct,
            "confidence_delta": candidate_align.confidence - accepted_align.confidence,
        },
    }
    cand_path = export_candidate_model_json(
        candidate_align, track_location_id, layout_id, extras, output_dir=mdir
    )
    # Persist the candidate geometry (companion) for promotion / segment regen.
    try:
        export_candidate_reference_path(
            build_result.reference_path, track_location_id, layout_id, output_dir=mdir
        )
    except Exception:
        pass
    # Phase 2C: stage refined reviewed-segments (best-effort; published on promote).
    _stage_reviewed_segments(
        session, candidate_station_map, accepted_align,
        track_location_id, layout_id, mdir,
    )
    append_refinement_ledger(track_location_id, layout_id, {
        "decision": "candidate_built",
        "improves": verdict.improves,
        "usable_laps": usable,
        "rejected_laps": int(getattr(build_result, "rejected_lap_count", 0)),
        "cars": cars,
        "improvement_reasons": verdict.improvement_reasons,
        "regression_reasons": verdict.regression_reasons,
        "pit_lane_detected": pit_lane_detected,
    }, models_dir=mdir)

    return RefinementResult(
        True, "", candidate_align=candidate_align, accepted_align=accepted_align,
        verdict=verdict, contributing_laps=usable, contributing_cars=cars,
        candidate_path=cand_path, warnings=list(getattr(build_result, "warnings", [])),
    )


def promote_candidate(
    track_location_id: str,
    layout_id: str,
    *,
    models_dir: Optional[Path] = None,
    require_improvement: bool = True,
) -> Optional[Path]:
    """Atomically replace the accepted model with the candidate, then clear it.

    S2/S5: refuses to promote unless the candidate still improves over the
    CURRENT accepted model and was built from it (fresh base). Returns the new
    accepted-model path, or None when nothing was promoted.
    """
    mdir = Path(models_dir) if models_dir else STATION_MODELS_DIR
    cand_path = find_candidate_model_path(track_location_id, layout_id, base_dir=mdir)
    if cand_path is None:
        return None
    candidate_align = import_candidate_alignment(cand_path)
    if candidate_align is None:
        return None

    accepted_path = find_accepted_model_path(track_location_id, layout_id, base_dir=mdir)
    accepted_align = import_accepted_model_json(accepted_path) if accepted_path else None

    # S5: reject a candidate that was refined from a different (stale) accepted model.
    # Also recover the geometry-shift recorded at build time for the S2 re-check.
    base_accepted_at = ""
    stored_shift: Optional[float] = None
    try:
        with open(cand_path, "r", encoding="utf-8") as fh:
            _cand_data = json.load(fh)
        base_accepted_at = _cand_data.get("base_accepted_at", "")
        _sv = _cand_data.get("geometry_shift_m", None)
        stored_shift = float(_sv) if isinstance(_sv, (int, float)) else None
    except OSError:
        base_accepted_at = ""
    if accepted_align is not None and base_accepted_at and base_accepted_at != accepted_align.accepted_at:
        append_refinement_ledger(track_location_id, layout_id, {
            "decision": "promote_rejected_stale_base",
            "candidate_base": base_accepted_at, "current_accepted_at": accepted_align.accepted_at,
        }, models_dir=mdir)
        return None

    # S2: re-check the gate (incl. the geometry-shift guard) against the CURRENT
    # accepted model before writing.
    if require_improvement and accepted_align is not None:
        verdict = compare_models(accepted_align, candidate_align, geometry_shift_m=stored_shift)
        if not verdict.improves:
            append_refinement_ledger(track_location_id, layout_id, {
                "decision": "promote_rejected_no_improvement",
                "regression_reasons": verdict.regression_reasons,
            }, models_dir=mdir)
            return None

    candidate_align.accepted = True
    candidate_align.accepted_at = datetime.now(timezone.utc).isoformat()
    out = export_accepted_model_json(candidate_align, track_location_id, layout_id, output_dir=mdir)

    try:
        cand_path.unlink()
    except OSError:  # pragma: no cover - defensive
        pass
    _remove_candidate_reference_path(track_location_id, layout_id, models_dir=mdir)
    # Phase 2C: publish the refined reviewed-segments so the AI-ready model stays in
    # sync (guarded — never publishes fewer segments than the model's corner count).
    _seg_published = _publish_staged_review(
        track_location_id, layout_id, mdir,
        min_segments=int(getattr(candidate_align, "model_corners_found", 0) or 0),
    )
    append_refinement_ledger(track_location_id, layout_id, {
        "decision": "promoted", "accepted_at": candidate_align.accepted_at,
        "reviewed_segments_published": _seg_published,
    }, models_dir=mdir)
    return out


def discard_candidate(
    track_location_id: str, layout_id: str, models_dir: Optional[Path] = None
) -> bool:
    """Delete the candidate model (user chose Discard). Returns True if removed."""
    cand_path = find_candidate_model_path(track_location_id, layout_id, base_dir=models_dir)
    if cand_path is None:
        return False
    try:
        cand_path.unlink()
    except OSError:  # pragma: no cover - defensive
        return False
    _remove_candidate_reference_path(track_location_id, layout_id, models_dir=models_dir)
    _remove_staged_review(track_location_id, layout_id, models_dir)
    append_refinement_ledger(track_location_id, layout_id, {"decision": "discarded"},
                             models_dir=models_dir)
    return True
