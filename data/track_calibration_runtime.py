"""Track calibration runtime — live telemetry adapter and capture session controller.

Pure Python, no PyQt6 dependency.  Provides:
  - can_capture_calibration_sample() — guards sample intake
  - infer_lap_number()              — extracts lap number from a GT7 packet
  - packet_to_calibration_sample()  — maps a GT7Packet to a TelemetrySample
  - CalibrationCaptureState         — session lifecycle enum
  - TrackCalibrationCaptureController — state machine for live capture sessions

Architecture boundary:
  - Depends on: data.track_calibration (data models, builders, I/O)
  - Does NOT import: PyQt6, telemetry.packet, ui.*
  - GT7Packet accepted via duck-typing to avoid circular imports.
  - All methods expected to be called from Qt main thread (via signal slots);
    no internal locking required.

GT7 telemetry limitations (documented here, not worked around):
  - steering:        not in GT7 protocol — always None
  - is_in_pit_lane:  no per-sample flag in GT7 packet — always None
  - laps_completed:  can be -1 in practice/qualifying; use fallback in that case
"""
from __future__ import annotations

import time
from enum import Enum
from pathlib import Path
from typing import Optional

from data.track_calibration import (
    PRIMARY_CALIBRATION_CAR_ID,
    MIN_USABLE_LAPS_FOR_PATH,
    OFF_TRACK_ROAD_PLANE_Y_THRESHOLD,
    CalibrationLap,
    CalibrationLapQuality,
    CalibrationSession,
    CalibrationBuildResult,
    LapQualityResult,
    ReferencePath,
    TelemetrySample,
    assess_session_laps,
    build_reference_path,
    export_reference_path_json,
    export_calibration_laps_json,   # Group 17N UAT
)


# ---------------------------------------------------------------------------
# Packet-level helpers (pure functions, no state)
# ---------------------------------------------------------------------------

def can_capture_calibration_sample(packet) -> bool:
    """Return True if this packet is a valid on-track frame for calibration.

    Accepts any duck-typed object with ``car_on_track``, ``paused``, and
    ``loading`` attributes.  Returns False for paused, loading, or off-track
    states — and on any attribute access exception.
    """
    try:
        return (
            bool(getattr(packet, "car_on_track", False))
            and not bool(getattr(packet, "paused", False))
            and not bool(getattr(packet, "loading", False))
        )
    except Exception:
        return False


def infer_lap_number(packet, fallback: Optional[int] = None) -> Optional[int]:
    """Extract the current in-progress lap number from a GT7 packet.

    GT7 ``laps_completed`` counts finished laps (0 = none completed, currently
    on lap 1).  Returns ``laps_completed + 1`` when the field is ≥ 0.

    Limitation: ``laps_completed`` may be -1 in practice/qualifying modes.
    When unreliable, ``fallback`` is returned.
    """
    try:
        laps_done = getattr(packet, "laps_completed", -1)
        if isinstance(laps_done, int) and laps_done >= 0:
            return laps_done + 1
    except Exception:
        pass
    return fallback


def packet_to_calibration_sample(
    packet, lap_number: int
) -> Optional[TelemetrySample]:
    """Map one GT7 packet to a TelemetrySample suitable for calibration capture.

    Returns None if the packet represents an invalid/off-track state or raises
    an exception (e.g. malformed/missing fields).

    GT7 field mapping:
    - steering       → None  (GT7 protocol does not expose steering angle)
    - is_in_pit_lane → None  (no per-sample pit lane flag in the GT7 packet)
    - is_off_track   → inferred from road_plane_y < threshold AND speed > 20 kph
    - timestamp_ms   → time_of_day_ms  (GT7 wall-clock; not elapsed per lap)
    """
    try:
        if not can_capture_calibration_sample(packet):
            return None

        road_plane_y: Optional[float] = getattr(packet, "road_plane_y", None)
        speed_kph: float = float(getattr(packet, "speed_kmh", 0.0))

        is_off_track: Optional[bool] = None
        if road_plane_y is not None:
            is_off_track = (
                float(road_plane_y) < OFF_TRACK_ROAD_PLANE_Y_THRESHOLD
                and speed_kph > 20.0
            )

        road_y = road_plane_y
        if road_y is None:
            surface_type = "road"
        elif road_y >= 0.85:
            surface_type = "road"
        elif road_y >= 0.50:
            surface_type = "kerb"
        else:
            surface_type = "grass"

        return TelemetrySample(
            timestamp_ms   = int(getattr(packet, "time_of_day_ms", 0)),
            lap_number     = lap_number,
            x              = float(getattr(packet, "pos_x", 0.0)),
            y              = float(getattr(packet, "pos_y", 0.0)),
            z              = float(getattr(packet, "pos_z", 0.0)),
            speed_kph      = speed_kph,
            gear           = int(getattr(packet, "current_gear", 0)),
            rpm            = float(getattr(packet, "engine_rpm", 0.0)),
            throttle       = float(getattr(packet, "throttle", 0.0)),
            brake          = float(getattr(packet, "brake", 0.0)),
            road_distance  = float(getattr(packet, "road_distance", 0.0)),
            steering       = None,          # GT7 protocol: steering angle not in packet
            yaw_rate       = float(getattr(packet, "angvel_z", 0.0)) if getattr(packet, "angvel_z", None) is not None else None,
            road_plane_y   = road_plane_y,
            is_off_track   = is_off_track,
            is_in_pit_lane = None,          # GT7 protocol: no per-sample pit lane flag
            surface_type   = surface_type,
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Session lifecycle enum
# ---------------------------------------------------------------------------

class CalibrationCaptureState(str, Enum):
    """Lifecycle state of TrackCalibrationCaptureController."""
    INACTIVE  = "inactive"
    RECORDING = "recording"
    STOPPED   = "stopped"
    BUILT     = "built"
    ERROR     = "error"


# ---------------------------------------------------------------------------
# Session controller
# ---------------------------------------------------------------------------

class TrackCalibrationCaptureController:
    """State machine that manages a live calibration capture session.

    Accumulates TelemetrySample objects from GT7 packets into CalibrationLap
    objects grouped by lap number.  When stopped, evaluates quality and can
    build a reference path from the usable laps.

    All public methods are expected to be called from the Qt main thread (via
    signal slots).  No internal locking is used.
    """

    def __init__(self) -> None:
        self._state              : CalibrationCaptureState = CalibrationCaptureState.INACTIVE
        self._session            : Optional[CalibrationSession] = None
        self._current_lap_samples: list[TelemetrySample] = []
        self._current_lap_number : Optional[int] = None
        self._total_samples      : int = 0
        self._last_build_result  : Optional[CalibrationBuildResult] = None
        self._saved_path         : Optional[Path] = None
        self._error              : str = ""

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def start_session(
        self,
        track_location_id: str,
        layout_id: str,
        calibration_car_id: str = PRIMARY_CALIBRATION_CAR_ID,
    ) -> bool:
        """Start a new calibration session for the given track/layout.

        Returns True on success.  Returns False (and sets state to ERROR) if
        track_location_id or layout_id is empty/blank.
        """
        if not str(track_location_id).strip() or not str(layout_id).strip():
            self._error = "Cannot start: no track location or layout selected"
            self._state = CalibrationCaptureState.ERROR
            return False

        session_id = (
            f"cal__{track_location_id}__{layout_id}__{int(time.time())}"
        )
        self._session = CalibrationSession(
            session_id         = session_id,
            track_location_id  = track_location_id,
            layout_id          = layout_id,
            calibration_car_id = calibration_car_id,
        )
        self._state               = CalibrationCaptureState.RECORDING
        self._current_lap_samples = []
        self._current_lap_number  = None
        self._total_samples       = 0
        self._last_build_result   = None
        self._saved_path          = None
        self._error               = ""
        return True

    def add_sample_from_packet(self, packet) -> bool:
        """Feed one GT7 packet into the active session.

        Handles lap boundary detection from the packet's ``laps_completed``
        field.  Returns True if a sample was accepted.  Silently skips the
        packet if the session is not recording or the packet is invalid.
        """
        if self._state != CalibrationCaptureState.RECORDING:
            return False
        if self._session is None:
            return False

        lap_num = infer_lap_number(packet, fallback=self._current_lap_number or 1)
        if lap_num is None:
            lap_num = self._current_lap_number or 1

        sample = packet_to_calibration_sample(packet, lap_num)
        if sample is None:
            return False

        # Detect lap boundary: close the previous lap when lap number changes
        if (
            self._current_lap_number is not None
            and lap_num != self._current_lap_number
        ):
            self._close_current_lap()

        self._current_lap_number = lap_num
        self._current_lap_samples.append(sample)
        self._total_samples += 1
        return True

    def stop_session(self) -> bool:
        """Stop recording and flush any in-progress partial lap.

        Returns True on success.  Returns False if not currently recording.
        """
        if self._state != CalibrationCaptureState.RECORDING:
            return False
        self._close_current_lap()
        self._state = CalibrationCaptureState.STOPPED
        return True

    # ── Quality evaluation ───────────────────────────────────────────────────

    def evaluate_laps(self) -> list[LapQualityResult]:
        """Evaluate all completed laps using session-aware quality rules.

        Returns [] if no session exists.
        """
        if self._session is None:
            return []
        return assess_session_laps(self._session)

    # ── Reference path building ──────────────────────────────────────────────

    def build_reference_path(self) -> CalibrationBuildResult:
        """Build a reference path from USABLE laps in the current session.

        Returns a failed result if called while recording, without a session,
        or with insufficient usable laps.  Never raises.
        """
        if self._state == CalibrationCaptureState.RECORDING:
            return CalibrationBuildResult(
                success=False,
                errors=["Cannot build while recording — stop the session first"],
            )
        if self._session is None:
            return CalibrationBuildResult(
                success=False,
                errors=["No active session"],
            )

        result = build_reference_path(self._session)
        self._last_build_result = result
        if result.success:
            self._state = CalibrationCaptureState.BUILT
        return result

    # ── File export ──────────────────────────────────────────────────────────

    def save_reference_path(self, output_dir: Optional[Path] = None) -> Optional[Path]:
        """Export the built reference path and USABLE calibration laps to JSON.

        Two files are written per save:
          - ``<loc>__<lay>.reference_path.json``  — aggregated 200-point path
          - ``<loc>__<lay>.calibration_laps.json`` — raw usable lap telemetry
            (needed by detect_track_segments() after a restart)

        Returns the reference path output Path on success, None if no path has
        been built or on write errors.  output_dir defaults to data/track_models/.
        """
        if self._last_build_result is None or not self._last_build_result.success:
            return None
        if self._last_build_result.reference_path is None:
            return None
        if self._session is None:
            return None
        try:
            saved = export_reference_path_json(
                self._last_build_result.reference_path,
                output_dir=output_dir,
            )
            self._saved_path = saved

            # Also persist usable calibration laps for post-restart detect_segments
            try:
                export_calibration_laps_json(
                    laps      = self._session.laps,
                    loc_id    = self._session.track_location_id,
                    lay_id    = self._session.layout_id,
                    car_id    = self._session.calibration_car_id,
                    output_dir= output_dir,
                )
            except Exception:
                pass  # laps file is best-effort; ref path save already succeeded

            return saved
        except Exception:
            return None

    # ── Status summary ───────────────────────────────────────────────────────

    def get_status_summary(self) -> dict:
        """Return a snapshot of the controller state for UI display."""
        session = self._session
        lap_count = len(session.laps) if session else 0

        ref_path: Optional[ReferencePath] = (
            self._last_build_result.reference_path
            if (self._last_build_result and self._last_build_result.success)
            else None
        )
        warnings: list[str] = (
            self._last_build_result.warnings
            if self._last_build_result
            else []
        )

        return {
            "state"               : self._state.value,
            "track_location_id"   : session.track_location_id if session else "",
            "layout_id"           : session.layout_id          if session else "",
            "total_samples"       : self._total_samples,
            "lap_count"           : lap_count,
            "current_lap_number"  : self._current_lap_number,
            "in_progress_samples" : len(self._current_lap_samples),
            "usable_laps"         : (
                self._last_build_result.usable_lap_count
                if self._last_build_result else 0
            ),
            "rejected_laps"       : (
                self._last_build_result.rejected_lap_count
                if self._last_build_result else 0
            ),
            "low_confidence_laps" : (
                self._last_build_result.low_confidence_lap_count
                if self._last_build_result else 0
            ),
            "reference_path_points": len(ref_path.points) if ref_path else 0,
            "confidence"           : ref_path.confidence if ref_path else 0.0,
            "warnings"             : warnings,
            "saved_path"           : str(self._saved_path) if self._saved_path else "",
            "error"                : self._error,
        }

    # ── UI button state helpers ──────────────────────────────────────────────

    @property
    def can_start(self) -> bool:
        """True when start_session() would be accepted (not currently recording)."""
        return self._state != CalibrationCaptureState.RECORDING

    @property
    def can_stop(self) -> bool:
        """True when stop_session() would be accepted."""
        return self._state == CalibrationCaptureState.RECORDING

    @property
    def can_build(self) -> bool:
        """True when there are enough completed laps to attempt path building."""
        return (
            self._state in (
                CalibrationCaptureState.STOPPED,
                CalibrationCaptureState.BUILT,
            )
            and self._session is not None
            and len(self._session.laps) >= MIN_USABLE_LAPS_FOR_PATH
        )

    @property
    def can_save(self) -> bool:
        """True when a successfully built reference path is ready to save."""
        return (
            self._last_build_result is not None
            and self._last_build_result.success
            and self._last_build_result.reference_path is not None
        )

    @property
    def is_recording(self) -> bool:
        """True when actively recording samples."""
        return self._state == CalibrationCaptureState.RECORDING

    # ── Internal ────────────────────────────────────────────────────────────

    def _close_current_lap(self) -> None:
        """Flush in-progress samples as a completed CalibrationLap."""
        if not self._current_lap_samples or self._current_lap_number is None:
            self._current_lap_samples = []
            return
        if self._session is None:
            self._current_lap_samples = []
            return

        t_start = self._current_lap_samples[0].timestamp_ms
        t_end   = self._current_lap_samples[-1].timestamp_ms
        lap_time_ms = max(0, t_end - t_start)

        lap = CalibrationLap(
            lap_number  = self._current_lap_number,
            lap_time_ms = lap_time_ms,
            samples     = list(self._current_lap_samples),
        )
        self._session.laps.append(lap)
        self._current_lap_samples = []
