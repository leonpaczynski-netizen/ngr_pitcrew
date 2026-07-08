"""Group 61 — Raw live-packet GT7 ``road_distance`` capture (pure, diagnostic).

WHY IT EXISTS
  Group 60 proved the shipped *calibration* captures do NOT confirm cumulative
  ``road_distance`` semantics — but calibration data is post-processed, so the true
  LIVE behaviour was still unknown. This module is a read-only, diagnostic capturer
  that accumulates RAW live-packet ``road_distance`` samples (with lap markers +
  world position) so a UAT run over ≥3 clean laps can finally settle the semantics
  via the Group 59/60 analysis flow.

WHAT THIS MODULE IS
  A pure accumulator + converters. You feed it packets (or samples); it records the
  raw values, rejects impossible ones, and can emit a ``laps[]`` structure that the
  Group 60 ``analyse_capture_road_distance`` consumes unchanged. It NEVER writes
  files, imports no Qt, no DB, no AI, and never raises. It must not affect strategy,
  setup, pit, or live-replan behaviour — it only observes.

SAFETY
  Read-only and diagnostic. It computes nothing about pit state and changes nothing.
  Serialising to disk (for a saved UAT capture) is done by the CALLER to an explicit
  path — this module does not write.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class RawRoadDistanceSample:
    """One raw live-packet observation used for semantics diagnosis."""
    sample_index: int
    road_distance: float
    lap_number: Optional[int] = None
    monotonic_ms: Optional[float] = None
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    pos_z: Optional[float] = None
    speed_kph: Optional[float] = None
    lap_progress_hint: Optional[float] = None   # any live progress indicator, if present


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


class LiveRoadDistanceCapture:
    """Read-only accumulator of raw live-packet road-distance samples.

    Pure logic (no I/O). Feed packets/samples in; read a ``laps[]`` structure or a
    summary out. Impossible road_distance values (None/NaN/inf) are counted, never
    stored. Negative values ARE kept (GT7 road_distance can legitimately be negative
    near the start/finish line) but are flagged in the summary.
    """

    def __init__(self, *, track_id: str = "", layout_id: str = "", car_id: str = "",
                 session_id: str = ""):
        self.track_id = str(track_id or "")
        self.layout_id = str(layout_id or "")
        self.car_id = str(car_id or "")
        self.session_id = str(session_id or "")
        self._samples: List[RawRoadDistanceSample] = []
        self.packet_count = 0
        self.valid_count = 0
        self.invalid_count = 0     # non-finite road_distance
        self.missing_count = 0     # no road_distance field at all
        self.negative_count = 0    # finite but negative (kept, flagged)
        self.no_lap_number_count = 0

    # -- ingestion -----------------------------------------------------------

    def add_sample(
        self,
        *,
        road_distance,
        lap_number=None,
        monotonic_ms=None,
        pos=None,
        speed_kph=None,
        lap_progress_hint=None,
    ) -> bool:
        """Add one raw sample. Returns True if stored. Never raises."""
        try:
            self.packet_count += 1
            rd = _finite(road_distance)
            if road_distance is None:
                self.missing_count += 1
                return False
            if rd is None:
                self.invalid_count += 1
                return False
            if rd < 0:
                self.negative_count += 1
            ln = _int_or_none(lap_number)
            if ln is None:
                self.no_lap_number_count += 1
            px = py = pz = None
            if pos is not None:
                try:
                    if isinstance(pos, (tuple, list)) and len(pos) >= 3:
                        px, py, pz = _finite(pos[0]), _finite(pos[1]), _finite(pos[2])
                    elif isinstance(pos, dict):
                        px, py, pz = _finite(pos.get("x")), _finite(pos.get("y")), _finite(pos.get("z"))
                except Exception:
                    px = py = pz = None
            self._samples.append(RawRoadDistanceSample(
                sample_index=len(self._samples), road_distance=rd, lap_number=ln,
                monotonic_ms=_finite(monotonic_ms), pos_x=px, pos_y=py, pos_z=pz,
                speed_kph=_finite(speed_kph), lap_progress_hint=_finite(lap_progress_hint)))
            self.valid_count += 1
            return True
        except Exception:
            return False

    def add_packet(self, packet, *, lap_number=None, monotonic_ms=None) -> bool:
        """Add one GT7Packet-like object (read-only). Never mutates it. Never raises."""
        try:
            rd = getattr(packet, "road_distance", None)
            pos = None
            if all(hasattr(packet, a) for a in ("pos_x", "pos_y", "pos_z")):
                pos = (getattr(packet, "pos_x"), getattr(packet, "pos_y"), getattr(packet, "pos_z"))
            speed = getattr(packet, "speed_kmh", None)
            return self.add_sample(road_distance=rd, lap_number=lap_number,
                                   monotonic_ms=monotonic_ms, pos=pos, speed_kph=speed)
        except Exception:
            return False

    # -- readout -------------------------------------------------------------

    @property
    def samples(self) -> Tuple[RawRoadDistanceSample, ...]:
        return tuple(self._samples)

    def lap_numbers_seen(self) -> Tuple[int, ...]:
        seen = []
        for s in self._samples:
            if s.lap_number is not None and s.lap_number not in seen:
                seen.append(s.lap_number)
        return tuple(seen)

    def to_laps(self) -> list:
        """Group samples into a ``laps[]`` structure for the Group 60 analyser.

        Consecutive samples sharing a lap_number form one lap. Samples without a lap
        number are grouped into a single positional lap so nothing is silently lost.
        """
        laps: list = []
        cur_ln = object()  # sentinel distinct from any int/None
        cur_samples: list = []

        def _flush(ln):
            if cur_samples:
                laps.append({"lap_number": ln if isinstance(ln, int) else len(laps) + 1,
                             "samples": [{"road_distance": s.road_distance} for s in cur_samples]})

        for s in self._samples:
            key = s.lap_number if s.lap_number is not None else "unnumbered"
            if key != cur_ln:
                _flush(cur_ln if isinstance(cur_ln, int) else None)
                cur_ln = key
                cur_samples = []
            cur_samples.append(s)
        _flush(cur_ln if isinstance(cur_ln, int) else None)
        return laps

    def to_capture_dict(self) -> dict:
        """A serialisable capture dict (identity + metadata + laps). Pure; no I/O."""
        return {
            "format_version": "raw_live_road_distance_v1",
            "track_location_id": self.track_id,
            "layout_id": self.layout_id,
            "calibration_car_id": self.car_id,
            "session_id": self.session_id,
            "packet_count": self.packet_count,
            "valid_count": self.valid_count,
            "invalid_count": self.invalid_count,
            "missing_count": self.missing_count,
            "negative_count": self.negative_count,
            "no_lap_number_count": self.no_lap_number_count,
            "laps": self.to_laps(),
        }

    def summary(self) -> dict:
        return {
            "track_id": self.track_id, "layout_id": self.layout_id, "car_id": self.car_id,
            "session_id": self.session_id,
            "packet_count": self.packet_count, "valid_count": self.valid_count,
            "invalid_count": self.invalid_count, "missing_count": self.missing_count,
            "negative_count": self.negative_count,
            "no_lap_number_count": self.no_lap_number_count,
            "lap_count": len(self.lap_numbers_seen()) or (1 if self._samples else 0),
            "laps_seen": list(self.lap_numbers_seen()),
        }


# ---------------------------------------------------------------------------
# Analysis convenience (delegates to the Group 60 analyser; pure)
# ---------------------------------------------------------------------------

def analyse_live_capture(capture: LiveRoadDistanceCapture, *, lap_length_m=None):
    """Analyse a live capture through the Group 60 flow. Pure; never raises.

    Resolves a trusted lap length from the registry when not supplied. Returns a
    Group 60 ``CaptureAnalysisResult`` (which exposes ``.capture_status`` incl.
    the Group 61 ``NON_DISTANCE_LIKE`` verdict).
    """
    try:
        from data.road_distance_capture_analysis import analyse_capture_road_distance
        if lap_length_m is None and capture.track_id:
            try:
                from data.reference_path_loader import resolve_trusted_lap_length
                lap_length_m = resolve_trusted_lap_length(capture.track_id, capture.layout_id)
            except Exception:
                lap_length_m = None
        return analyse_capture_road_distance(
            capture.to_laps(), track_id=capture.track_id, layout_id=capture.layout_id,
            car_id=capture.car_id, lap_length_m=lap_length_m)
    except Exception:
        from data.road_distance_capture_analysis import CaptureAnalysisResult
        return CaptureAnalysisResult(track_id=capture.track_id, layout_id=capture.layout_id,
                                     next_action="Live capture analysis error.")
