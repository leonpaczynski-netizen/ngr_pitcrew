"""Group 60 — Real-capture GT7 ``road_distance`` semantics analysis (pure).

WHY IT EXISTS
  Group 59 built a pure validator (``data/road_distance_semantics.py``) that decides
  whether GT7 ``road_distance`` behaves cumulatively or resets per lap — but it needs
  lap-boundary samples. This module turns REAL captured multi-lap telemetry (or a
  session's laps) into those samples, runs the Group 59 validator as the authority,
  and builds a human-readable report so the ``road_distance`` semantics can be
  confirmed (or honestly refused) from real data.

WHAT THIS MODULE IS
  A pure, deterministic analysis layer. It extracts, per lap, the road_distance at
  lap start and lap end (plus the min/max span and sample count as extra evidence),
  feeds start/end to the Group 59 validator, and reports the outcome. It NEVER
  promotes live behaviour — only confirmed semantics may ever do that, and that
  decision lives with the caller, gated by the validator's status.

HONEST FINDING SUPPORT
  A key real-world observation the report surfaces: if a lap's road_distance SPAN
  (max − min) is far below the trusted lap length, the captured field is NOT a
  cumulative lap-distance signal at all — the report says so and refuses to confirm.

SAFETY
  Pure analysis: no Qt, no AI, no DB, no file writes. The only I/O is a thin,
  read-only calibration-file loader kept separate from the pure analysis. Never
  raises on malformed samples (NaN/inf skipped, missing lap numbers tolerated).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from data.road_distance_semantics import (
    RoadDistanceSample,
    RoadDistanceSemanticsResult,
    RoadDistanceSemanticsStatus,
    analyse_road_distance_semantics,
)

# A per-lap span below this fraction of the trusted lap length means the captured
# road_distance does NOT measure cumulative lap distance (honest red flag).
_SPAN_LAP_FRACTION_MIN = 0.5


@dataclass(frozen=True)
class CaptureLapObservation:
    """Per-lap road-distance evidence extracted from a real capture."""
    lap_number: int
    start_distance: float
    end_distance: float
    min_distance: float
    max_distance: float
    sample_count: int

    @property
    def delta(self) -> float:
        return self.end_distance - self.start_distance

    @property
    def span(self) -> float:
        return self.max_distance - self.min_distance


@dataclass(frozen=True)
class CaptureAnalysisResult:
    """Structured outcome of analysing a real capture's road-distance semantics."""
    track_id: str = ""
    layout_id: str = ""
    car_id: str = ""
    lap_count: int = 0
    observations: Tuple[CaptureLapObservation, ...] = ()
    lap_length_m: Optional[float] = None
    semantics: Optional[RoadDistanceSemanticsResult] = None
    max_span_m: Optional[float] = None
    span_covers_lap: Optional[bool] = None   # None when no trusted lap length
    next_action: str = ""
    warnings: Tuple[str, ...] = ()

    @property
    def status(self) -> RoadDistanceSemanticsStatus:
        return (self.semantics.status if self.semantics is not None
                else RoadDistanceSemanticsStatus.UNKNOWN)

    @property
    def confirmed(self) -> bool:
        return bool(self.semantics is not None and self.semantics.is_confirmed)


# ---------------------------------------------------------------------------
# Numeric helpers (reject NaN/inf; never raise)
# ---------------------------------------------------------------------------

def _finite(v) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _int_or_none(v) -> Optional[int]:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _get(obj, *names, default=None):
    for nm in names:
        if isinstance(obj, dict):
            if nm in obj:
                return obj[nm]
        elif hasattr(obj, nm):
            return getattr(obj, nm)
    return default


# ---------------------------------------------------------------------------
# Extraction (pure)
# ---------------------------------------------------------------------------

def extract_lap_observations(laps_data: Sequence) -> List[CaptureLapObservation]:
    """Extract per-lap road-distance observations from capture laps. Never raises.

    Each lap is a dict/object with a ``lap_number`` and a ``samples`` sequence whose
    items carry a ``road_distance``. Laps with fewer than two finite road_distance
    samples are skipped. NaN/inf road_distance values are ignored.
    """
    out: List[CaptureLapObservation] = []
    try:
        for i, lap in enumerate(laps_data or ()):
            samples = _get(lap, "samples", "telemetry", default=None)
            if not isinstance(samples, (list, tuple)):
                continue
            rd = [_finite(_get(s, "road_distance", "road_distance_m", default=None))
                  for s in samples]
            rd = [v for v in rd if v is not None]
            if len(rd) < 2:
                continue
            ln = _int_or_none(_get(lap, "lap_number", "lap", default=None))
            if ln is None:
                ln = i + 1
            out.append(CaptureLapObservation(
                lap_number=ln, start_distance=rd[0], end_distance=rd[-1],
                min_distance=min(rd), max_distance=max(rd), sample_count=len(rd)))
        return out
    except Exception:
        return out


# ---------------------------------------------------------------------------
# Analysis (pure)
# ---------------------------------------------------------------------------

def analyse_capture_road_distance(
    laps_data: Sequence,
    *,
    track_id: str = "",
    layout_id: str = "",
    car_id: str = "",
    lap_length_m=None,
) -> CaptureAnalysisResult:
    """Analyse a real capture's road-distance semantics. Pure; never raises.

    Extracts per-lap observations, runs the Group 59 validator on the start/end
    samples, and augments the result with a span-vs-lap-length red flag and a clear
    next action. It confirms nothing the validator does not confirm.
    """
    try:
        lap_len = _finite(lap_length_m)
        obs = extract_lap_observations(laps_data)
        samples = [RoadDistanceSample(o.lap_number, o.start_distance, o.end_distance)
                   for o in obs]
        semantics = analyse_road_distance_semantics(samples, lap_length_m=lap_len)

        warnings: List[str] = []
        max_span = max((o.span for o in obs), default=None)
        span_covers_lap: Optional[bool] = None
        if lap_len is not None and lap_len > 0 and max_span is not None:
            span_covers_lap = max_span >= _SPAN_LAP_FRACTION_MIN * lap_len
            if not span_covers_lap:
                warnings.append(
                    f"per-lap road_distance span ({max_span:,.0f} m) is far below the "
                    f"trusted lap length ({lap_len:,.0f} m) — the captured road_distance "
                    "does not measure cumulative lap distance in this capture")

        next_action = _next_action(semantics.status, span_covers_lap, len(obs))

        return CaptureAnalysisResult(
            track_id=str(track_id or ""), layout_id=str(layout_id or ""),
            car_id=str(car_id or ""), lap_count=len(obs), observations=tuple(obs),
            lap_length_m=lap_len, semantics=semantics, max_span_m=max_span,
            span_covers_lap=span_covers_lap, next_action=next_action,
            warnings=tuple(dict.fromkeys(list(semantics.warnings) + warnings)))
    except Exception:
        return CaptureAnalysisResult(
            track_id=str(track_id or ""), layout_id=str(layout_id or ""),
            next_action="Analysis error — recapture and retry.",
            warnings=("capture analysis error — treated as unknown",))


def _next_action(status: RoadDistanceSemanticsStatus,
                 span_covers_lap: Optional[bool], lap_count: int) -> str:
    if span_covers_lap is False:
        return ("The captured road_distance does not span the lap — do NOT treat it as "
                "cumulative lap distance. Verify the packet field and capture raw live "
                "packets (not post-processed calibration data) before trusting fallback.")
    if status == RoadDistanceSemanticsStatus.CUMULATIVE_CONFIRMED:
        return ("Cumulative behaviour confirmed. Fallback may keep using a lap-start "
                "reference; confidence stays capped (never HIGH). No change required.")
    if status == RoadDistanceSemanticsStatus.PER_LAP_RESET_CONFIRMED:
        return ("Per-lap reset confirmed. A lap-start reference is unnecessary; "
                "progress ≈ road_distance / lap_length. Confidence stays capped.")
    if status == RoadDistanceSemanticsStatus.INCONSISTENT:
        return ("Inconsistent across laps — do NOT trust this signal. Recapture at "
                "least three clean consecutive laps and re-run.")
    if status == RoadDistanceSemanticsStatus.INSUFFICIENT_EVIDENCE:
        return ("Insufficient evidence. Capture at least two (ideally three) clean "
                "consecutive laps recording road_distance at lap start and end.")
    return ("No usable road-distance samples. Confirm the capture includes a "
            "road_distance field for each sample.")


# ---------------------------------------------------------------------------
# Reporting (pure, human-readable, honest)
# ---------------------------------------------------------------------------

def build_capture_report(result: CaptureAnalysisResult) -> List[str]:
    """Build human-readable report rows. No false-certainty wording. Never raises."""
    rows: List[str] = []
    try:
        rows.append("Road-Distance Semantics — Real Capture Report")
        rows.append(f"Track: {result.track_id or 'unknown'}")
        rows.append(f"Layout: {result.layout_id or 'unknown'}")
        rows.append(f"Car: {result.car_id or 'unknown'}")
        rows.append(f"Usable laps: {result.lap_count}")
        if result.lap_length_m:
            rows.append(f"Trusted lap length: {result.lap_length_m:,.1f} m")
        else:
            rows.append("Trusted lap length: unavailable")
        rows.append("Per-lap road_distance:")
        for o in result.observations:
            diff = ("" if result.lap_length_m is None
                    else f", diff vs lap {o.delta - result.lap_length_m:+,.0f} m")
            rows.append(
                f"  lap {o.lap_number}: start {o.start_distance:,.1f} m, "
                f"end {o.end_distance:,.1f} m, delta {o.delta:,.1f} m, "
                f"span {o.span:,.1f} m ({o.sample_count} samples){diff}")
        if result.max_span_m is not None:
            rows.append(f"Max per-lap span: {result.max_span_m:,.1f} m")
        # Honest status — never claim confirmation the validator did not make.
        rows.append(f"Semantics status: {result.status.value}")
        if result.semantics is not None and result.semantics.message:
            rows.append(f"Reason: {result.semantics.message}")
        if not result.confirmed:
            rows.append("Confidence: NOT confirmed — treat road-distance fallback as "
                        "approximate/lower-confidence (unchanged).")
        for w in result.warnings:
            rows.append(f"Warning: {w}")
        rows.append(f"Next action: {result.next_action}")
        return rows
    except Exception:
        return ["Road-Distance Semantics — Real Capture Report",
                "Report unavailable (analysis error)."]


# ---------------------------------------------------------------------------
# Thin read-only loaders (isolated from the pure analysis; never write; never raise)
# ---------------------------------------------------------------------------

def load_capture_laps_from_calibration_file(path) -> list:
    """Read a calibration-laps JSON file and return its ``laps`` list. Read-only.

    Returns [] when the file is missing/malformed. Never raises; never writes.
    """
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return []
        raw = json.loads(p.read_text(encoding="utf-8"))
        laps = raw.get("laps") if isinstance(raw, dict) else None
        return list(laps) if isinstance(laps, list) else []
    except Exception:
        return []


def analyse_calibration_capture(
    track_id: str,
    layout_id: str,
    *,
    base_dir=None,
    lap_length_m=None,
) -> CaptureAnalysisResult:
    """Load a shipped calibration capture for a track/layout and analyse it. Read-only.

    Resolves the trusted lap length via the Group 58 registry when not supplied.
    Never raises; returns an honest UNKNOWN result when the capture is unavailable.
    """
    try:
        from data.track_calibration import TRACK_MODELS_DIR, calibration_laps_filename
        root = Path(base_dir) if base_dir is not None else Path(TRACK_MODELS_DIR)
        path = root / calibration_laps_filename(track_id, layout_id)
        laps = load_capture_laps_from_calibration_file(path)
        car_id = ""
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8")) if path.exists() else {}
            car_id = str(raw.get("calibration_car_id", "") or "")
        except Exception:
            car_id = ""
        if lap_length_m is None:
            try:
                from data.reference_path_loader import resolve_trusted_lap_length
                lap_length_m = resolve_trusted_lap_length(track_id, layout_id)
            except Exception:
                lap_length_m = None
        return analyse_capture_road_distance(
            laps, track_id=track_id, layout_id=layout_id, car_id=car_id,
            lap_length_m=lap_length_m)
    except Exception:
        return CaptureAnalysisResult(track_id=str(track_id or ""),
                                     layout_id=str(layout_id or ""),
                                     next_action="Capture unavailable — verify the "
                                                 "calibration file exists.")
