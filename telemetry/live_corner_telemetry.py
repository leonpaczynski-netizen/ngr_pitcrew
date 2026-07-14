"""Live per-corner telemetry consumer (Qt-free).

Ties the live pipeline together: for each (sub-sampled) packet it resolves which
reviewed segment the car is in (:mod:`data.live_segment_resolver`), classifies the
frame's wheel slip (:mod:`strategy.wheel_slip`), and folds the result into the
per-corner accumulator (:mod:`strategy.live_corner_aggregator`). Finalised aggregates
become telemetry-grounded Phase-5 corner diagnoses.

Never raises into the packet path — every packet is handled best-effort. Off the hot
path by design: the caller feeds it from the throttled UI-poll hook, and it further
sub-samples internally. Holds no Qt, no DB, no file access.
"""
from __future__ import annotations

from typing import Optional

from data.live_segment_resolver import packet_to_live_position, resolve_live_segment
from strategy.wheel_slip import classify_wheel_slip
from strategy.live_corner_aggregator import (
    LiveCornerAggregator, phase_from_segment_type, diagnoses_from_telemetry,
)


class LiveCornerTelemetry:
    """Accumulate per-corner slip evidence for one car/track/layout over a session."""

    def __init__(self, track_location_id: str, layout_id: str, drivetrain: str = "",
                 offset_calibration=None, sample_every: int = 6):
        self._loc = track_location_id or ""
        self._lay = layout_id or ""
        self._drivetrain = drivetrain or ""
        self._cal = offset_calibration
        self._sample_every = max(1, int(sample_every))
        self._n = 0
        self._agg = LiveCornerAggregator()

    def add_packet(self, packet) -> None:
        """Fold one live packet into the per-corner accumulator (best-effort)."""
        try:
            if not getattr(packet, "car_on_track", True):
                return
            self._n += 1
            if self._n % self._sample_every:
                return
            if not self._loc:
                return
            pos = packet_to_live_position(packet)
            res = resolve_live_segment(self._loc, self._lay, pos,
                                       offset_calibration=self._cal)
            match = getattr(res, "match", None)
            if match is None:
                return
            phase = phase_from_segment_type(getattr(match, "segment_type", ""))
            if not phase:
                return   # not a corner segment (straight/kerb) — nothing to attribute
            slip = classify_wheel_slip(
                packet.wheel_rps, packet.tyre_radius, packet.speed_ms,
                packet.throttle, packet.brake, self._drivetrain)
            self._agg.add_sample(
                segment_id=match.segment_id, turn=getattr(match, "turn_number", None),
                phase=phase, display_name=getattr(match, "display_name", ""),
                direction=getattr(match, "direction", ""), slip=slip,
                throttle=packet.throttle, brake=packet.brake,
                gear=getattr(packet, "current_gear", None),
                rpm=getattr(packet, "engine_rpm", None))
        except Exception:
            return

    def aggregates(self) -> list:
        """Snapshot of the per-corner aggregates accumulated so far."""
        return self._agg.finalize()

    def diagnoses(self, segments: list) -> list:
        """Telemetry-grounded Phase-5 corner diagnoses from the accumulated evidence."""
        try:
            return diagnoses_from_telemetry(self._agg.finalize(), segments)
        except Exception:
            return []

    def has_evidence(self) -> bool:
        return bool(self._agg.finalize())

    def reset(self) -> None:
        self._n = 0
        self._agg.reset()
