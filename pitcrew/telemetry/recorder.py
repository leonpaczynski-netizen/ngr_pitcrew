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
MS_PER_PACKET = 1000.0 / SAMPLE_HZ
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
    "t_ms",              # ms since the lap's first frame, from the packet counter
    # GT7 0xA0. This is the road plane's fourth coefficient, NOT distance
    # around the lap: it reads about -80 to -250 m and covers 125 m over a
    # whole lap of Monza. It was named `road_distance_m` and fed to corner
    # detection, which is why no session ever produced a corner model and why
    # `corners` - the section the contract calls the one to build if only one
    # gets built - has never once been exported. Kept because the on-disk
    # format is append-only, named for what it is so it cannot be mistaken
    # again. Nothing reads it.
    "road_plane_d",
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
    # **Distance around the lap, metres from the line.** GT7 broadcasts no
    # such channel, so it is integrated here from speed against the packet
    # clock. Everything about corner identity depends on it: a corner is a
    # window of lap distance, and without one there are no corners.
    "lap_distance_m",
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


def repair_frames(frames: list[dict],
                  sample_hz: float = SAMPLE_HZ) -> list[dict]:
    """Give laps recorded before this a lap distance and a working clock.

    Two channels were wrong in every lap captured up to now, and both are
    recoverable from what *was* stored:

    * **`lap_distance_m` did not exist.** What was recorded as distance was the
      road plane's fourth coefficient. Speed integrated at the known sample
      rate lands within a percent of the circuit's published length and does so
      consistently lap to lap, which is what corner windows need.
    * **`t_ms` was GT7's in-game clock.** Frozen in a fixed-time event and
      running at many times real speed in a day-to-night one, so laps came out
      spanning 0 s or 970 s where the lap took 110 s. Every corner metric timed
      against it - trail-brake duration, time loss, consistency - was scaled by
      whatever the event's time multiplier happened to be. The frame index at
      the sample rate is the real elapsed time.

    A lap already carrying `lap_distance_m` was recorded after the fix and is
    left exactly as it is. A lap with no speed channel is left alone too: the
    distance stays absent and the corner model reports no corners, which is
    honest.
    """
    if not frames or frames[0].get("lap_distance_m") is not None:
        return frames
    if all(frame.get("speed_kph") is None for frame in frames):
        return frames
    rate = sample_hz or SAMPLE_HZ
    distance = 0.0
    out = []
    for index, frame in enumerate(frames):
        speed = frame.get("speed_kph")
        if speed is not None:
            distance += speed / 3.6 / rate
        out.append({**frame,
                    "lap_distance_m": round(distance, 2),
                    "t_ms": int(round(index * 1000.0 / rate))})
    return out


class LapRecorder:
    """Buffers frames for the lap in progress and hands them over on completion."""

    def __init__(self, sample_every: int = 1) -> None:
        # sample_every=1 is full rate.  Exposed only so a test can thin the
        # stream; the app should never raise it.
        self._sample_every = max(1, sample_every)
        self._lock = threading.Lock()
        self._counter = 0
        self._rows: list[list] = []
        self._lap_start_packet: int | None = None
        self._last_packet_id: int | None = None
        self._distance_m = 0.0
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

            # The clock is the packet counter, not GT7's time of day.
            # `time_of_day_ms` is the *in-game* clock: it is frozen at a fixed
            # time of day and runs at many times real speed in a day-to-night
            # event, so laps recorded through one came out spanning 0 s and
            # laps through the other 970 s - for a 110 s lap. Everything timed
            # off it was wrong by whatever multiplier the event happened to
            # use. The counter ticks once per packet at a known 60 Hz.
            if self._lap_start_packet is None:
                self._lap_start_packet = packet.packet_id
            elapsed = max(0, int(round(
                (packet.packet_id - self._lap_start_packet) * MS_PER_PACKET)))

            # Distance around the lap, integrated from speed. GT7 broadcasts
            # no lap-distance channel at all, and corner identity is a window
            # of lap distance, so this is what makes corners possible. Stepped
            # by the gap since the previous packet so a dropped packet costs
            # its own distance rather than shifting everything after it.
            step = 1 if self._last_packet_id is None else max(
                1, packet.packet_id - self._last_packet_id)
            self._last_packet_id = packet.packet_id
            self._distance_m += packet.speed_ms * step / SAMPLE_HZ

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
                round(self._distance_m, 2),
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
            self._lap_start_packet = None
            self._last_packet_id = None
            self._distance_m = 0.0
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
            self._lap_start_packet = None
            self._last_packet_id = None
            self._distance_m = 0.0
