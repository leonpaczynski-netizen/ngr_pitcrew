"""Full-rate per-lap telemetry capture.

GT7 sends at 60 Hz.  The old recorder kept every sixth packet (~10 Hz) because
its consumers were summary statistics.  The consumer now is an analysis pass in
Claude, so the requirement is "the best frequency of refresh possible" — this
records every packet.

A lap is roughly 7,200 frames.  Frames are serialised column-header + row-array
rather than a list of objects (no key repetition), rounded to the precision the
channel actually carries, then zlib-compressed: ~150-400 KB per lap on disk.

Threading: `record_frame()` runs on the UDP thread, `take_lap()` on whichever
thread handles lap completion.  Both take the lock; nothing else touches the
buffer.
"""
from __future__ import annotations

import json
import math
import threading
import zlib
from dataclasses import dataclass

from pitcrew.telemetry.packet import GT7Packet

SAMPLE_HZ = 60.0
BLOB_FORMAT = "pitcrew.frames.v1"

# Column order is part of the on-disk format.  Append only — never reorder, or
# previously stored laps decode into the wrong channels.
#
# Units are converted here, at the parser boundary, once.  Everything
# downstream works in the export's units so no layer has to remember which
# convention it is holding.  Missing channels are null, never zero.
#
# Deliberately absent: oil and water temperature.  GT7 pins them at ~110 C and
# ~85 C regardless of what the car is doing, so they carry no information.
FRAME_FIELDS: tuple[str, ...] = (
    "t_ms",              # ms since the lap's first frame
    "road_distance_m",   # m from the start/finish line (GT7 0xA0)
    "speed_kph",
    "throttle_pct",      # 0-100
    "brake_pct",         # 0-100
    "steering_deg",      # degrees, null until the tail offset is verified
    "steering_norm",     # -1..1 fraction of full lock, null likewise
    "gear",
    "rpm",               # captured for short-shift analysis; never exported
    "yaw_rate",          # rad/s, + = turning left
    "lat_g",
    "pos_x", "pos_y", "pos_z",
    "slip_fl", "slip_fr", "slip_rl", "slip_rr",   # wheel surface speed / car speed
    "susp_mm_fl", "susp_mm_fr", "susp_mm_rl", "susp_mm_rr",  # absolute height, mm
    "temp_fl", "temp_fr", "temp_rl", "temp_rr",   # tyre surface, degrees C
    "body_height_mm",
    "surf_fl", "surf_fr", "surf_rl", "surf_rr",   # T/C/D/G/S/s, null before '~'
    "road_plane_y",      # off-track proxy for formats without surface type
    "rev_limiter",
    # Needed to derive the final drive from engine speed against wheel speed.
    # Appended, so laps recorded before this still decode - the blob carries
    # its own field list.
    "tyre_radius_m",
)

# The driver's physical wheel rotation setting (Fanatec DD Extreme).  Reported
# in `derived.steerRotationDeg` so a reader can relate the captured angle to
# what his hands did — it is NOT used to normalise, because the channel we
# capture is the in-game wheel, which saturates at +-pi whatever the rim is set
# to.  Normalisation lives in GT7Packet.steering_norm.
DEFAULT_STEER_ROTATION_DEG = 1080.0

_TWO_PI = 2.0 * math.pi
# Below this the wheel-speed ratio is numerically meaningless (standing start,
# stopped in the pit box) and would report enormous slip.
_MIN_SPEED_FOR_SLIP_MS = 2.0


@dataclass(frozen=True)
class LapFrames:
    """One lap's captured telemetry, ready to store."""
    frame_count: int
    sample_hz: float
    blob: bytes

    @property
    def size_bytes(self) -> int:
        return len(self.blob)


def _slip_ratios(p: GT7Packet) -> tuple[float, float, float, float]:
    """Wheel surface speed / car speed per corner.

    1.0 = rolling true, > 1.0 = spinning up, < 1.0 = locking.  This is the only
    way to get slip out of GT7, which sends wheel rotation and tyre radius but
    no slip channel.
    """
    if p.speed_ms < _MIN_SPEED_FOR_SLIP_MS:
        return (1.0, 1.0, 1.0, 1.0)
    rps = (p.wheel_rps_fl, p.wheel_rps_fr, p.wheel_rps_rl, p.wheel_rps_rr)
    radius = (p.tyre_radius_fl, p.tyre_radius_fr, p.tyre_radius_rl, p.tyre_radius_rr)
    out = []
    for i in range(4):
        surface_ms = abs(rps[i]) * radius[i] * _TWO_PI
        out.append(surface_ms / p.speed_ms)
    return (out[0], out[1], out[2], out[3])


def encode_frames(rows: list[list]) -> bytes:
    payload = {"format": BLOB_FORMAT, "fields": list(FRAME_FIELDS), "rows": rows}
    return zlib.compress(json.dumps(payload, separators=(",", ":")).encode("utf-8"), 6)


def decode_frames(blob: bytes) -> list[dict]:
    """Inverse of `encode_frames`, as a list of per-frame dicts."""
    payload = json.loads(zlib.decompress(blob).decode("utf-8"))
    fields = payload["fields"]
    return [dict(zip(fields, row)) for row in payload["rows"]]


class LapRecorder:
    """Buffers frames for the lap in progress and hands them over on completion."""

    def __init__(self, sample_every: int = 1) -> None:
        # sample_every=1 is full rate.  Exposed only so a test can thin the
        # stream; the app should never raise it.
        self._sample_every = max(1, sample_every)
        self._lock = threading.Lock()
        self._counter = 0
        self._rows: list[list] = []
        self._lap_start_ms: int | None = None
        self._dropped_off_track = 0

    @property
    def frame_count(self) -> int:
        with self._lock:
            return len(self._rows)

    def record_frame(self, packet: GT7Packet) -> None:
        """Called from the UDP thread for every packet."""
        with self._lock:
            self._counter += 1
            if self._counter % self._sample_every != 0:
                return
            if not packet.car_on_track or packet.paused or packet.loading:
                self._dropped_off_track += 1
                return

            if self._lap_start_ms is None:
                self._lap_start_ms = packet.time_of_day_ms
            elapsed = max(0, packet.time_of_day_ms - self._lap_start_ms)

            slip = _slip_ratios(packet)
            lat_g = abs(packet.speed_ms * packet.angvel_z) / 9.81
            steer_rad = packet.steering
            steer_deg = None if steer_rad is None else round(math.degrees(steer_rad), 2)
            steer_norm = packet.steering_norm
            steer_norm = None if steer_norm is None else round(steer_norm, 4)
            surface = packet.surface_types or (None, None, None, None)

            self._rows.append([
                elapsed,
                round(packet.road_distance, 2),
                round(packet.speed_kmh, 2),
                round(packet.throttle * 100.0, 1),
                round(packet.brake * 100.0, 1),
                steer_deg,
                steer_norm,
                packet.current_gear,
                round(packet.engine_rpm, 0),
                round(packet.angvel_z, 4),
                round(lat_g, 3),
                round(packet.pos_x, 2), round(packet.pos_y, 2), round(packet.pos_z, 2),
                round(slip[0], 4), round(slip[1], 4), round(slip[2], 4), round(slip[3], 4),
                round(packet.suspension_fl * 1000.0, 2),
                round(packet.suspension_fr * 1000.0, 2),
                round(packet.suspension_rl * 1000.0, 2),
                round(packet.suspension_rr * 1000.0, 2),
                round(packet.tyre_temp_fl, 1), round(packet.tyre_temp_fr, 1),
                round(packet.tyre_temp_rl, 1), round(packet.tyre_temp_rr, 1),
                round(packet.body_height * 1000.0, 2),
                surface[0], surface[1], surface[2], surface[3],
                round(packet.road_plane_y, 4),
                1 if packet.rev_limiter_active else 0,
                round(packet.tyre_radius_rl, 4),
            ])

    def take_rows(self) -> list[list]:
        """Detach the lap in progress, without compressing it.

        This must run on the telemetry thread the instant a lap completes: any
        frame recorded after the lap boundary but before the swap belongs to
        the next lap, and compressing ~7,200 rows takes long enough to drop
        packets if it happens inline. The caller compresses afterwards, off the
        socket loop.
        """
        with self._lock:
            rows = self._rows
            self._rows = []
            self._lap_start_ms = None
            self._dropped_off_track = 0
        return rows

    def encode(self, rows: list[list]) -> LapFrames | None:
        """Compress detached rows. Safe to call from any thread."""
        if not rows:
            return None
        return LapFrames(
            frame_count=len(rows),
            sample_hz=SAMPLE_HZ / self._sample_every,
            blob=encode_frames(rows),
        )

    def take_lap(self) -> LapFrames | None:
        """Detach and compress in one step. Convenient off the hot path."""
        return self.encode(self.take_rows())

    def discard(self) -> None:
        with self._lock:
            self._rows = []
            self._lap_start_ms = None
