"""Phase 1 — Live event-lap path capture for continuous track-model refinement.

Accumulates the world-XYZ path of real event laps (grouped by lap number) into a
``CalibrationSession`` so an already-accepted track model can be REFINED from
fresh laps, without a dedicated calibration session (UAT #6).

This module is PURE and RAM-only: it never writes a model and never mutates
anything on disk. Turning captured laps into a candidate model, gating it against
the accepted model, and promoting it are the job of ``data/track_refinement.py``
(non-destructive, gated). See ``docs/DESIGN_continuous_track_refinement.md``.

It reuses the existing ``TelemetrySample`` / ``CalibrationLap`` /
``CalibrationSession`` types so captured laps feed the SAME
``build_reference_path`` → station-map → alignment pipeline the manual
calibration flow uses. Identity gating (is the driver actually on this
track/layout?) is the caller's responsibility — ``matches()`` is provided to
make that check trivial, and the capture should only be constructed when an
accepted model already exists for the current track/layout.
"""
from __future__ import annotations

import math
from typing import List, Optional

from data.track_calibration import (
    CalibrationLap,
    CalibrationSession,
    CalibrationLapQuality,
    TelemetrySample,
)


def _finite(v) -> Optional[float]:
    """Return v as a float when finite, else None."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


class LiveTrackPathCapture:
    """Accumulate live event-lap paths into a CalibrationSession (RAM only).

    Usage (Phase 1b wiring): construct once per live session when an accepted
    model exists for the current track/layout, feed every live packet via
    ``add_packet``, then hand ``build_session()`` to ``track_refinement`` when the
    session stops.
    """

    def __init__(
        self,
        track_location_id: str,
        layout_id: str,
        car_name: str = "",
        session_id: str = "live-refine",
    ) -> None:
        self.track_location_id = (track_location_id or "").strip()
        self.layout_id = (layout_id or "").strip()
        self.car_name = (car_name or "").strip()
        self.session_id = session_id or "live-refine"

        self._laps: List[CalibrationLap] = []
        self._current_lap_number: Optional[int] = None
        self._current_samples: List[TelemetrySample] = []

        # Honest counters (surfaced in the refinement ledger / UI).
        self.accepted_sample_count: int = 0   # samples with valid finite XYZ
        self.rejected_sample_count: int = 0    # samples dropped (non-finite / zero XYZ)

    # ------------------------------------------------------------------ identity
    def matches(self, track_location_id: str, layout_id: str) -> bool:
        """True when this capture is for the given track/layout (exact, trimmed)."""
        return (
            self.track_location_id == (track_location_id or "").strip()
            and self.layout_id == (layout_id or "").strip()
        )

    # ------------------------------------------------------------------ ingest
    def add_packet(self, packet, lap_number: int) -> bool:
        """Add one live packet to the capture under ``lap_number``.

        ``packet`` is duck-typed (``pos_x/pos_y/pos_z``, ``speed_kmh`` … — the
        same fields ``TelemetrySample.from_frame`` reads). Returns True when the
        sample was kept, False when it was rejected (non-finite or zero XYZ).

        A change in ``lap_number`` finalises the previous lap.
        """
        try:
            ln = int(lap_number)
        except (TypeError, ValueError):
            self.rejected_sample_count += 1
            return False

        # Reject samples without a usable world position — zero/None/NaN XYZ carry
        # no geometry and would poison the averaged path.
        px = _finite(getattr(packet, "pos_x", None))
        py = _finite(getattr(packet, "pos_y", None))
        pz = _finite(getattr(packet, "pos_z", None))
        if px is None or py is None or pz is None or (px == 0.0 and py == 0.0 and pz == 0.0):
            self.rejected_sample_count += 1
            return False

        try:
            sample = TelemetrySample.from_frame(packet, ln)
        except Exception:
            self.rejected_sample_count += 1
            return False
        # from_frame falls back to 0.0 for missing coords; guard again defensively.
        if not sample.has_valid_xyz():
            self.rejected_sample_count += 1
            return False

        if self._current_lap_number is None:
            self._current_lap_number = ln
        elif ln != self._current_lap_number:
            self._finalize_current_lap()
            self._current_lap_number = ln

        self._current_samples.append(sample)
        self.accepted_sample_count += 1
        return True

    def _finalize_current_lap(self) -> None:
        """Move the buffered samples into a CalibrationLap (quality unassessed)."""
        if not self._current_samples:
            return
        samples = self._current_samples
        ln = self._current_lap_number if self._current_lap_number is not None else 0
        # lap_time_ms from the timestamp span of the lap (0 when timestamps flat).
        first_ts = samples[0].timestamp_ms
        last_ts = samples[-1].timestamp_ms
        lap_time_ms = max(0, int(last_ts) - int(first_ts))
        self._laps.append(
            CalibrationLap(
                lap_number=ln,
                lap_time_ms=lap_time_ms,
                samples=list(samples),
                # Quality is (re)assessed by build_reference_path/assess_session_laps.
                quality=CalibrationLapQuality.REJECTED,
            )
        )
        self._current_samples = []

    # ------------------------------------------------------------------ output
    def lap_count(self) -> int:
        """Number of finalised laps (excludes the in-progress lap)."""
        return len(self._laps)

    def build_session(self) -> CalibrationSession:
        """Return a CalibrationSession of all captured laps (finalising the current one).

        Non-destructive on repeated calls: finalising the in-progress lap moves
        its buffered samples into ``_laps`` so a second ``build_session`` after
        more packets simply appends the newly-accumulated lap.
        """
        self._finalize_current_lap()
        self._current_lap_number = None
        return CalibrationSession(
            session_id=self.session_id,
            track_location_id=self.track_location_id,
            layout_id=self.layout_id,
            calibration_car_id=self.car_name or "live",
            laps=list(self._laps),
            notes="Captured from live event laps for continuous refinement.",
        )
