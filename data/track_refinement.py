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

from data.track_calibration import CalibrationSession, build_reference_path
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


def _xyz_list(points) -> "List[tuple]":
    """Extract (x, y, z) tuples from objects (or dicts) exposing x/y/z."""
    out: List[tuple] = []
    for p in points or []:
        try:
            if isinstance(p, dict):
                out.append((float(p["x"]), float(p.get("y", 0.0)), float(p["z"])))
            else:
                out.append((float(p.x), float(getattr(p, "y", 0.0)), float(p.z)))
        except (KeyError, TypeError, ValueError, AttributeError):
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


def candidate_reference_path_filename(track_location_id: str, layout_id: str) -> str:
    return f"{track_location_id}__{layout_id}.candidate_reference_path.json"


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

def build_candidate_alignment(
    session: CalibrationSession,
    accepted_align: TrackModelAlignmentResult,
) -> Tuple[Optional[TrackModelAlignmentResult], Optional[TrackStationMap], object]:
    """Build a candidate alignment from captured laps, using the accepted model's
    seed truth (corners_expected / seed lap length). Returns
    (candidate_align | None, station_map | None, build_result)."""
    seed = SimpleNamespace(
        corners_expected=accepted_align.seed_corners_expected,
        length_m=accepted_align.lap_length_m_seed,
        sectors=None,
    )
    build_result = build_reference_path(session)
    ref_path = getattr(build_result, "reference_path", None)
    if not getattr(build_result, "success", False) or ref_path is None or not ref_path.points:
        return None, None, build_result
    station_map = build_track_station_map(ref_path, seed)
    candidate_align = align_track_model(station_map, seed)
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
) -> RefinementResult:
    """Build (never promote) a candidate model from captured event laps.

    Requires an existing accepted model (else refinement is a no-op — there is
    nothing to refine). Writes the candidate file + a ledger line. The caller
    decides whether to ``promote_candidate`` based on ``result.promotable``.
    """
    mdir = Path(models_dir) if models_dir else STATION_MODELS_DIR
    cars = sorted({c.strip() for c in (contributing_cars or []) if c and c.strip()})

    accepted_path = find_accepted_model_path(track_location_id, layout_id, base_dir=mdir)
    if accepted_path is None:
        return RefinementResult(False, "no accepted model to refine")
    accepted_align = import_accepted_model_json(accepted_path)
    if accepted_align is None:
        return RefinementResult(False, "accepted model unreadable")

    try:
        candidate_align, _sm, build_result = build_candidate_alignment(session, accepted_align)
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
    # resolved — the scalar-metric gate still applies).
    geometry_shift_m: Optional[float] = None
    try:
        _cand_pts = getattr(build_result.reference_path, "points", None)
        _acc_pts = _load_accepted_path_points(track_location_id, layout_id)
        if _acc_pts and _cand_pts:
            geometry_shift_m = mean_path_shift_m(_acc_pts, _cand_pts)
    except Exception:
        geometry_shift_m = None

    verdict = compare_models(accepted_align, candidate_align, geometry_shift_m=geometry_shift_m)
    usable = int(getattr(build_result, "usable_lap_count", 0))

    extras = {
        "base_accepted_at":   accepted_align.accepted_at,
        "contributing_laps":  usable,
        "contributing_cars":  cars,
        "source_sessions":    list(source_session_ids or []),
        "improves":           verdict.improves,
        "improvement_reasons": verdict.improvement_reasons,
        "regression_reasons": verdict.regression_reasons,
        "geometry_shift_m":   geometry_shift_m,
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
    append_refinement_ledger(track_location_id, layout_id, {
        "decision": "candidate_built",
        "improves": verdict.improves,
        "usable_laps": usable,
        "rejected_laps": int(getattr(build_result, "rejected_lap_count", 0)),
        "cars": cars,
        "improvement_reasons": verdict.improvement_reasons,
        "regression_reasons": verdict.regression_reasons,
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
    append_refinement_ledger(track_location_id, layout_id, {
        "decision": "promoted", "accepted_at": candidate_align.accepted_at,
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
    append_refinement_ledger(track_location_id, layout_id, {"decision": "discarded"},
                             models_dir=models_dir)
    return True
