"""Track modelling runtime check — pure Python pipeline status aggregator.

Aggregates status across:
  - track/layout selection
  - track model resolver result
  - lap offset calibration
  - live position and live segment resolution

Pure Python, no PyQt6 dependency.  Safe to call from tests and view-model layers.
All arguments are duck-typed (object or None) to avoid circular imports.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RuntimeCheckResult:
    """Snapshot of the full track modelling pipeline status at a point in time."""

    loc_id: str = ""
    lay_id: str = ""
    has_track: bool = False

    # Resolver
    resolver_source: str = ""        # e.g. "reviewed_model" / "seed_only" / "missing"
    resolver_ai_ready: bool = False

    # Lap offset calibration
    offset_status: str = "none"      # "none" / "provisional" / "validated"
    offset_m: Optional[float] = None
    offset_track_length_m: Optional[float] = None

    # Live position / segment
    has_road_distance: bool = False
    live_segment_id: Optional[str] = None
    live_segment_name: Optional[str] = None
    live_resolution_status: str = ""

    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary_text(self) -> str:
        """Return a compact multi-line status string suitable for UI display."""
        lines: list[str] = []

        if not self.has_track:
            lines.append("Track: not selected")
        else:
            lines.append(f"Track: {self.loc_id} / {self.lay_id}")

        rs  = self.resolver_source or "not checked"
        ai  = "Yes" if self.resolver_ai_ready else "No"
        lines.append(f"Resolver: {rs}  |  AI-ready: {ai}")

        if self.offset_m is not None:
            lines.append(f"Offset: {self.offset_status}  ({self.offset_m:.1f} m)")
        else:
            lines.append(f"Offset: {self.offset_status}")

        lines.append(
            f"Road distance: {'available' if self.has_road_distance else 'unavailable'}"
        )

        if self.live_segment_id:
            name = self.live_segment_name or self.live_segment_id
            lines.append(f"Segment: {name}  ({self.live_resolution_status})")
        else:
            lines.append(f"Segment: unresolved  ({self.live_resolution_status})")

        for w in self.warnings[:3]:
            lines.append(f"  ⚠ {w}")
        for e in self.errors[:2]:
            lines.append(f"  ✕ {e}")

        return "\n".join(lines)


def run_track_modelling_runtime_check(
    loc_id: str = "",
    lay_id: str = "",
    resolver_result=None,
    offset_calibration=None,
    live_position=None,
    live_segment_result=None,
) -> RuntimeCheckResult:
    """Run a low-risk read-only check across the track modelling pipeline.

    Never raises.  Returns a RuntimeCheckResult with all fields populated.
    Accepts any duck-typed objects to avoid circular imports.
    """
    result = RuntimeCheckResult(
        loc_id=str(loc_id or ""),
        lay_id=str(lay_id or ""),
    )
    result.has_track = bool(str(loc_id).strip()) and bool(str(lay_id).strip())

    # ── Resolver ─────────────────────────────────────────────────────────────
    try:
        if resolver_result is not None:
            resolved = getattr(resolver_result, "resolved_model", None)
            if resolved is not None:
                source = getattr(resolved, "source_type", None)
                result.resolver_source = (
                    source.value if hasattr(source, "value") else str(source or "")
                )
                result.resolver_ai_ready = bool(getattr(resolved, "ai_ready", False))
            else:
                result.resolver_source = "missing"
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Resolver check failed: {exc}")

    # ── Offset calibration ────────────────────────────────────────────────────
    try:
        if offset_calibration is not None:
            conf     = getattr(offset_calibration, "confidence", None)
            conf_val = conf.value if hasattr(conf, "value") else str(conf or "")
            source   = str(getattr(offset_calibration, "calibration_source", "") or "")
            if conf_val in ("high", "medium") and source != "zero_offset":
                result.offset_status = "validated"
            else:
                result.offset_status = "provisional"
            result.offset_m             = getattr(offset_calibration, "offset_m", None)
            result.offset_track_length_m = getattr(offset_calibration, "track_length_m", None)
            for w in list(getattr(offset_calibration, "warnings", []))[:2]:
                if w:
                    result.warnings.append(w)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Offset check failed: {exc}")

    # ── Live position ────────────────────────────────────────────────────────
    try:
        if live_position is not None:
            rd = getattr(live_position, "road_distance_m", None)
            result.has_road_distance = rd is not None
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Live position check failed: {exc}")

    # ── Live segment resolution ───────────────────────────────────────────────
    try:
        if live_segment_result is not None:
            res_status = getattr(live_segment_result, "resolution_status", None)
            result.live_resolution_status = (
                res_status.value if hasattr(res_status, "value") else str(res_status or "")
            )
            match = getattr(live_segment_result, "match", None)
            if match is not None:
                result.live_segment_id   = getattr(match, "segment_id", None)
                result.live_segment_name = getattr(match, "display_name", None)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"Live segment check failed: {exc}")

    return result
