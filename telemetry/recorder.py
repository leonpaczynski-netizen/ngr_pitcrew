"""Per-lap telemetry recorder for GT7 VR Dashboard.

Captures ~10 Hz frames (every 6 packets) during each lap and computes
driving-style statistics on lap completion.  Thread-safe: record_frame()
is called from the UDP thread, finalize_lap() from EventDispatcher.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from statistics import mean, stdev
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from telemetry.packet import GT7Packet


@dataclass
class TelemetryFrame:
    elapsed_ms: int
    speed_kmh: float
    throttle: float                             # 0.0–1.0
    brake: float                                # 0.0–1.0
    gear: int
    rpm: float
    road_distance: float                        # metres along road
    wheel_rps: tuple[float, float, float, float]    # FL FR RL RR
    tyre_radius: tuple[float, float, float, float]  # metres
    suspension: tuple[float, float, float, float]   # metres
    angvel_z: float = 0.0   # yaw angular velocity (rad/s) — positive = turning left
    vel_x: float = 0.0      # world-space lateral velocity (m/s)
    vel_y: float = 0.0      # world-space longitudinal velocity (m/s)
    body_height: float = 0.0  # chassis height above ground (m)
    pos_x: float = 0.0     # world-space X position (m)
    pos_y: float = 0.0     # world-space Y position (m)
    pos_z: float = 0.0     # world-space Z position (m)
    rev_limiter: bool = False
    brake_raw: int = 0      # 0-255
    car_max_speed_raw: int = 0  # uint16 (0.01 m/s units)
    road_plane_y: float = 1.0   # road normal Y component (1.0 = flat tarmac)
    tyre_temp_fl: float = 0.0   # °C measured from GT7 packet
    tyre_temp_fr: float = 0.0
    tyre_temp_rl: float = 0.0
    tyre_temp_rr: float = 0.0


@dataclass
class LapStats:
    lap_num: int
    lap_time_ms: int
    lock_up_count: int
    wheelspin_count: int
    brake_consistency_m: float    # std-dev of braking initiation positions (m); -1 if < 2 zones
    max_speed_kmh: float
    avg_throttle_pct: float       # 0–100
    avg_brake_pct: float          # 0–100
    # Extended physics metrics (default 0 so older callers without these values still work)
    oversteer_count: int = 0             # snap oversteer events (|angvel_z| > 0.8 rad/s)
    oversteer_throttle_on_count: int = 0 # subset: occurred while throttle > 0.5
    kerb_count: int = 0                  # hard kerb events (suspension travel > 40 mm)
    bottoming_count: int = 0             # chassis bottoming events (body_height < 40 mm)
    snap_throttle_count: int = 0         # abrupt full-throttle applications in < 100 ms
    max_lat_g: float = 0.0               # peak lateral G (speed_ms × |angvel_z| / 9.81)
    # B1 — rev limiter
    rev_limiter_count: int = 0
    rev_limiter_by_gear: dict = field(default_factory=dict)   # {gear: hit_count}
    # B2 — world XYZ position logging on events
    lock_up_positions: list = field(default_factory=list)        # [(x,y,z), …]
    wheelspin_positions: list = field(default_factory=list)
    oversteer_positions: list = field(default_factory=list)
    snap_throttle_positions: list = field(default_factory=list)
    over_braking_positions: list = field(default_factory=list)
    # B3 — over-braking (100 % brake into slow corner) and abrupt release
    over_braking_count: int = 0
    abrupt_release_count: int = 0
    # B4 — theoretical vs actual max speed
    car_max_speed_theoretical_kmh: float = 0.0  # from car_max_speed_raw (inferred)
    # B5 — tyre radius wear proxy
    avg_tyre_radius: dict = field(default_factory=dict)  # {"fl":f,"fr":f,"rl":f,"rr":f}
    # B6 — off-track detection (road normal diverges from vertical)
    off_track_count: int = 0
    # B7 — gearbox engineering analysis (limiter events, straights, corner exits)
    gearbox_analysis: dict = field(default_factory=dict)
    frames: list[TelemetryFrame] = field(default_factory=list, repr=False)
    # B8 — per-corner tyre temperature averages (°C; 0.0 if no temp data available)
    tyre_temp_fl_avg: float = 0.0
    tyre_temp_fr_avg: float = 0.0
    tyre_temp_rl_avg: float = 0.0
    tyre_temp_rr_avg: float = 0.0


def _wheel_speed_ms(rps: tuple[float, float, float, float],
                    radius: tuple[float, float, float, float]) -> float:
    """Average linear tyre speed in m/s."""
    vals = [abs(rps[i]) * radius[i] * 2.0 * math.pi for i in range(4)]
    return mean(vals) if vals else 0.0


_TWO_PI = 6.283185307   # 2π — avoids importing math

# Thresholds for per-lap event counters
_OVERSTEER_YAW_THRESHOLD  = 0.8    # rad/s (~46°/s) — onset of snap rotation
_KERB_SUSPENSION_THRESHOLD = 0.04  # m (40 mm) — hard kerb / sharp bump compression
_BOTTOMING_HEIGHT_THRESHOLD = 0.04 # m (40 mm) — chassis very close to ground
_SNAP_THROTTLE_DELTA       = 0.6   # 0–1 change per ~100 ms frame = aggressive stab


def _compute_stats(frames: list[TelemetryFrame], lap_num: int,
                   lap_time_ms: int) -> LapStats:
    if not frames:
        return LapStats(
            lap_num=lap_num, lap_time_ms=lap_time_ms,
            lock_up_count=0, wheelspin_count=0, brake_consistency_m=-1.0,
            max_speed_kmh=0.0, avg_throttle_pct=0.0, avg_brake_pct=0.0,
        )

    max_speed = max(f.speed_kmh for f in frames)
    avg_thr   = mean(f.throttle for f in frames) * 100.0
    avg_brk   = mean(f.brake    for f in frames) * 100.0

    # Lock-up: front wheel speed < 50 % of car speed while braking
    lock_up_count = 0
    in_lockup = False
    for f in frames:
        if f.speed_kmh < 5:
            in_lockup = False
            continue
        speed_ms = f.speed_kmh / 3.6
        wheel_ms = _wheel_speed_ms(f.wheel_rps, f.tyre_radius)
        if f.brake > 0.3 and wheel_ms < speed_ms * 0.5 and speed_ms > 2.0:
            if not in_lockup:
                lock_up_count += 1
                in_lockup = True
        else:
            in_lockup = False

    # Wheelspin: rear wheel speed > 130 % of car speed while accelerating
    wheelspin_count = 0
    in_spin = False
    for f in frames:
        speed_ms = f.speed_kmh / 3.6
        wheel_ms = _wheel_speed_ms(f.wheel_rps, f.tyre_radius)
        if f.throttle > 0.7 and wheel_ms > speed_ms * 1.3 and speed_ms > 2.0:
            if not in_spin:
                wheelspin_count += 1
                in_spin = True
        else:
            in_spin = False

    # Braking consistency: std-dev of road_distance at braking initiation points
    brake_starts: list[float] = []
    prev_brake = 0.0
    for f in frames:
        if prev_brake < 0.2 <= f.brake:
            brake_starts.append(f.road_distance)
        prev_brake = f.brake
    consistency = stdev(brake_starts) if len(brake_starts) >= 2 else -1.0

    # Oversteer: yaw rate spike above threshold (angvel_z, rad/s)
    # Classified as throttle-on (exit) vs entry (braking/coasting)
    oversteer_count = 0
    oversteer_throttle_on = 0
    in_oversteer = False
    for f in frames:
        if abs(f.angvel_z) > _OVERSTEER_YAW_THRESHOLD and f.speed_kmh > 20:
            if not in_oversteer:
                oversteer_count += 1
                if f.throttle > 0.5:
                    oversteer_throttle_on += 1
                in_oversteer = True
        else:
            in_oversteer = False

    # Kerb / hard bump: any wheel suspension travel exceeds threshold
    kerb_count = 0
    in_kerb = False
    for f in frames:
        if max(abs(s) for s in f.suspension) > _KERB_SUSPENSION_THRESHOLD:
            if not in_kerb:
                kerb_count += 1
                in_kerb = True
        else:
            in_kerb = False

    # Bottoming: body_height below ground-clearance threshold
    bottoming_count = 0
    in_bottom = False
    for f in frames:
        if 0.0 < f.body_height < _BOTTOMING_HEIGHT_THRESHOLD:
            if not in_bottom:
                bottoming_count += 1
                in_bottom = True
        else:
            in_bottom = False

    # Snap throttle: throttle application > 0.6 in one ~100 ms frame above 20 km/h
    snap_throttle_count = 0
    snap_throttle_positions: list = []
    prev_thr = frames[0].throttle
    for f in frames[1:]:
        if f.throttle - prev_thr > _SNAP_THROTTLE_DELTA and f.speed_kmh > 20:
            snap_throttle_count += 1
            snap_throttle_positions.append((f.pos_x, f.pos_y, f.pos_z))
        prev_thr = f.throttle

    # Peak lateral G: centripetal = speed × yaw_rate / g
    lat_g_vals = [
        (f.speed_kmh / 3.6) * abs(f.angvel_z) / 9.81
        for f in frames if f.speed_kmh > 10
    ]
    max_lat_g = max(lat_g_vals) if lat_g_vals else 0.0

    # B1 — rev limiter hits per gear
    rev_limiter_count = 0
    rev_limiter_by_gear: dict = {}
    in_limiter = False
    for f in frames:
        if f.rev_limiter:
            if not in_limiter:
                rev_limiter_count += 1
                g = f.gear
                rev_limiter_by_gear[g] = rev_limiter_by_gear.get(g, 0) + 1
                in_limiter = True
        else:
            in_limiter = False

    # B2 — XYZ positions already captured per-event above;
    # re-scan for lock-up / wheelspin / oversteer position lists
    lup_pos: list = []
    wspin_pos: list = []
    over_pos: list = []
    in_lup2 = in_spin2 = in_over2 = False
    for f in frames:
        speed_ms = f.speed_kmh / 3.6
        wms = _wheel_speed_ms(f.wheel_rps, f.tyre_radius)
        # lock-up
        if f.brake > 0.3 and wms < speed_ms * 0.5 and speed_ms > 2.0 and f.speed_kmh >= 5:
            if not in_lup2:
                lup_pos.append((f.pos_x, f.pos_y, f.pos_z))
                in_lup2 = True
        else:
            in_lup2 = False
        # wheelspin
        if f.throttle > 0.7 and wms > speed_ms * 1.3 and speed_ms > 2.0:
            if not in_spin2:
                wspin_pos.append((f.pos_x, f.pos_y, f.pos_z))
                in_spin2 = True
        else:
            in_spin2 = False
        # oversteer
        if abs(f.angvel_z) > _OVERSTEER_YAW_THRESHOLD and f.speed_kmh > 20:
            if not in_over2:
                over_pos.append((f.pos_x, f.pos_y, f.pos_z))
                in_over2 = True
        else:
            in_over2 = False

    # B3 — over-braking (full brake into slow corner) and abrupt release
    over_braking_count = 0
    abrupt_release_count = 0
    over_brake_pos: list = []
    prev_brake_raw = frames[0].brake_raw
    for f in frames[1:]:
        # Over-braking: hard brake (>240/255) entering low speed
        if f.brake_raw > 240 and f.speed_kmh < 120 and prev_brake_raw < 60:
            over_braking_count += 1
            over_brake_pos.append((f.pos_x, f.pos_y, f.pos_z))
        # Abrupt brake release: drops >70 % in one frame at speed
        prev_norm = prev_brake_raw / 255.0
        curr_norm = f.brake_raw / 255.0
        if prev_norm > 0.7 and curr_norm < 0.3 and f.speed_kmh > 40:
            abrupt_release_count += 1
        prev_brake_raw = f.brake_raw

    # B4 — theoretical max speed from car_max_speed_raw (0.01 m/s per unit → km/h)
    max_theoretical = max((f.car_max_speed_raw for f in frames), default=0)
    car_max_speed_theoretical_kmh = max_theoretical * 0.01 * 3.6

    # B5 — average tyre radius per wheel per lap
    radii: dict = {"fl": [], "fr": [], "rl": [], "rr": []}
    for f in frames:
        r = f.tyre_radius
        radii["fl"].append(r[0])
        radii["fr"].append(r[1])
        radii["rl"].append(r[2])
        radii["rr"].append(r[3])
    avg_tyre_radius = {k: mean(v) for k, v in radii.items() if v}

    # B6 — off-track: road normal Y component below threshold at speed
    off_track_count = 0
    in_offtrack = False
    for f in frames:
        if f.road_plane_y < 0.5 and f.speed_kmh > 20:
            if not in_offtrack:
                off_track_count += 1
                in_offtrack = True
        else:
            in_offtrack = False

    gearbox_analysis = _analyse_gearbox(frames)

    # B8 — per-corner tyre temperature averages
    _tfl, _tfr, _trl, _trr = [], [], [], []
    for f in frames:
        if f.tyre_temp_fl > 0:
            _tfl.append(f.tyre_temp_fl)
            _tfr.append(f.tyre_temp_fr)
            _trl.append(f.tyre_temp_rl)
            _trr.append(f.tyre_temp_rr)
    tyre_temp_fl_avg = round(mean(_tfl), 1) if _tfl else 0.0
    tyre_temp_fr_avg = round(mean(_tfr), 1) if _tfr else 0.0
    tyre_temp_rl_avg = round(mean(_trl), 1) if _trl else 0.0
    tyre_temp_rr_avg = round(mean(_trr), 1) if _trr else 0.0

    return LapStats(
        lap_num=lap_num,
        lap_time_ms=lap_time_ms,
        lock_up_count=lock_up_count,
        wheelspin_count=wheelspin_count,
        brake_consistency_m=consistency,
        max_speed_kmh=max_speed,
        avg_throttle_pct=avg_thr,
        avg_brake_pct=avg_brk,
        oversteer_count=oversteer_count,
        oversteer_throttle_on_count=oversteer_throttle_on,
        kerb_count=kerb_count,
        bottoming_count=bottoming_count,
        snap_throttle_count=snap_throttle_count,
        max_lat_g=max_lat_g,
        rev_limiter_count=rev_limiter_count,
        rev_limiter_by_gear=rev_limiter_by_gear,
        lock_up_positions=lup_pos,
        wheelspin_positions=wspin_pos,
        oversteer_positions=over_pos,
        snap_throttle_positions=snap_throttle_positions,
        over_braking_positions=over_brake_pos,
        over_braking_count=over_braking_count,
        abrupt_release_count=abrupt_release_count,
        car_max_speed_theoretical_kmh=car_max_speed_theoretical_kmh,
        avg_tyre_radius=avg_tyre_radius,
        off_track_count=off_track_count,
        gearbox_analysis=gearbox_analysis,
        frames=frames,
        tyre_temp_fl_avg=tyre_temp_fl_avg,
        tyre_temp_fr_avg=tyre_temp_fr_avg,
        tyre_temp_rl_avg=tyre_temp_rl_avg,
        tyre_temp_rr_avg=tyre_temp_rr_avg,
    )


def _analyse_gearbox(frames: list[TelemetryFrame]) -> dict:
    """Compute gearbox engineering metrics from recorded lap frames.

    Returns a dict with limiter_events, longest_straight, corner_exits,
    gear_time_histogram, and top-speed analysis ready for AI consumption.
    """
    if not frames:
        return {}

    _FRAME_DT = 0.1  # ~10 Hz sampling interval in seconds

    # ── Rev limiter events with track position and duration ───────────────
    limiter_events: list[dict] = []
    in_lim = False
    lim_start_dist = 0.0
    lim_start_idx = 0
    lim_gear = 0
    for i, f in enumerate(frames):
        if f.rev_limiter and not in_lim:
            in_lim = True
            lim_start_dist = f.road_distance
            lim_start_idx = i
            lim_gear = f.gear
        elif not f.rev_limiter and in_lim:
            dur = (i - lim_start_idx) * _FRAME_DT
            limiter_events.append({
                "gear": lim_gear,
                "road_dist": round(lim_start_dist, 1),
                "duration_secs": round(dur, 2),
            })
            in_lim = False
    if in_lim:
        dur = (len(frames) - lim_start_idx) * _FRAME_DT
        limiter_events.append({
            "gear": lim_gear,
            "road_dist": round(lim_start_dist, 1),
            "duration_secs": round(dur, 2),
        })

    # ── Limiter summary by gear ───────────────────────────────────────────
    lim_summary: dict[int, dict] = {}
    for ev in limiter_events:
        g = ev["gear"]
        if g not in lim_summary:
            lim_summary[g] = {"count": 0, "total_secs": 0.0, "road_dists": []}
        lim_summary[g]["count"] += 1
        lim_summary[g]["total_secs"] += ev["duration_secs"]
        lim_summary[g]["road_dists"].append(ev["road_dist"])
    for g, s in lim_summary.items():
        s["avg_duration_secs"] = round(s["total_secs"] / s["count"], 2)

    # ── Longest full-throttle section (by road_distance span) ────────────
    best_straight: dict = {}
    th_start: int | None = None
    for i, f in enumerate(frames):
        if f.throttle >= 0.98 and f.speed_kmh > 30:
            if th_start is None:
                th_start = i
        else:
            if th_start is not None:
                seg = frames[th_start:i]
                dist_span = frames[i - 1].road_distance - frames[th_start].road_distance
                if dist_span > best_straight.get("length_m", 0):
                    max_spd = max(s.speed_kmh for s in seg)
                    # Find where limiter was first hit in this segment
                    lim_dist_in_seg = None
                    brk_gear = frames[i].gear if i < len(frames) else seg[-1].gear
                    for s in seg:
                        if s.rev_limiter and lim_dist_in_seg is None:
                            lim_dist_in_seg = s.road_distance
                    lim_lead = None
                    if lim_dist_in_seg is not None:
                        lim_lead = round(frames[i - 1].road_distance - lim_dist_in_seg, 1)
                    best_straight = {
                        "start_dist": round(frames[th_start].road_distance, 1),
                        "end_dist":   round(frames[i - 1].road_distance, 1),
                        "length_m":   round(dist_span, 1),
                        "max_speed_kmh": round(max_spd, 1),
                        "entry_gear": frames[th_start].gear,
                        "braking_gear": brk_gear,
                        "hits_limiter": lim_dist_in_seg is not None,
                        "limiter_lead_dist_m": lim_lead,  # metres BEFORE end of straight
                    }
                th_start = None

    # ── Corner exit events (throttle application after brake release) ─────
    corner_exits: list[dict] = []
    prev_brake = frames[0].brake
    prev_throttle = frames[0].throttle
    for i, f in enumerate(frames[1:], 1):
        # Detect transition: braking just ended AND throttle is being applied
        if prev_brake > 0.1 and f.brake < 0.05 and f.throttle > 0.1 and f.speed_kmh > 20:
            # Find next upshift (gear increase within next 20 frames)
            upshift_ms: int | None = None
            for j in range(i, min(i + 20, len(frames) - 1)):
                if frames[j].gear > f.gear:
                    upshift_ms = int((j - i) * _FRAME_DT * 1000)
                    break
            corner_exits.append({
                "road_dist":       round(f.road_distance, 1),
                "exit_gear":       f.gear,
                "exit_rpm":        round(f.rpm),
                "speed_kmh":       round(f.speed_kmh, 1),
                "time_to_upshift_ms": upshift_ms,
            })
        prev_brake    = f.brake
        prev_throttle = f.throttle

    # ── Gear time histogram (seconds in each gear) ────────────────────────
    gear_time: dict[int, float] = {}
    for f in frames:
        g = f.gear
        if g > 0:
            gear_time[g] = round(gear_time.get(g, 0.0) + _FRAME_DT, 2)

    # ── Top speed analysis ────────────────────────────────────────────────
    top_speed = max(f.speed_kmh for f in frames)
    theoretical = max((f.car_max_speed_raw for f in frames), default=0) * 0.01 * 3.6
    reached_pct = round(top_speed / theoretical * 100, 1) if theoretical > 0 else None

    return {
        "limiter_events":   limiter_events,
        "limiter_by_gear":  lim_summary,
        "longest_straight": best_straight,
        "corner_exits":     corner_exits[:20],  # cap at 20 to avoid huge prompts
        "gear_time_secs":   gear_time,
        "top_speed_kmh":    round(top_speed, 1),
        "theoretical_max_kmh": round(theoretical, 1) if theoretical > 0 else None,
        "top_speed_reached_pct": reached_pct,
    }


class LapTelemetryRecorder:
    """Records throttle/brake/wheel/suspension data at ~10 Hz per lap."""

    def __init__(self, max_laps: int = 20, sample_every: int = 6) -> None:
        self._max_laps     = max_laps
        self._sample_every = sample_every
        self._lock         = threading.Lock()

        self._packet_counter = 0
        self._current_frames: list[TelemetryFrame] = []
        self._current_lap = -1
        self._lap_start_ms: Optional[int] = None

        self._completed: list[LapStats] = []   # newest first

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def record_frame(self, packet: "GT7Packet", lap_num: int) -> None:
        """Called from UDP thread on every packet."""
        with self._lock:
            self._packet_counter += 1
            if self._packet_counter % self._sample_every != 0:
                return
            if not packet.car_on_track:
                return

            if lap_num != self._current_lap:
                self._current_frames = []
                self._current_lap = lap_num
                self._lap_start_ms = packet.time_of_day_ms

            elapsed = 0
            if self._lap_start_ms is not None:
                elapsed = packet.time_of_day_ms - self._lap_start_ms
                if elapsed < 0:
                    elapsed = 0

            self._current_frames.append(TelemetryFrame(
                elapsed_ms    = elapsed,
                speed_kmh     = packet.speed_kmh,
                throttle      = packet.throttle,
                brake         = packet.brake,
                gear          = packet.current_gear,
                rpm           = packet.engine_rpm,
                road_distance = packet.road_distance,
                wheel_rps     = packet.wheel_rps,
                tyre_radius   = packet.tyre_radius,
                suspension    = packet.suspension,
                angvel_z      = packet.angvel_z,
                vel_x         = packet.vel_x,
                vel_y         = packet.vel_y,
                body_height   = packet.body_height,
                pos_x         = packet.pos_x,
                pos_y         = packet.pos_y,
                pos_z         = packet.pos_z,
                rev_limiter   = packet.rev_limiter_active,
                brake_raw     = packet.brake_raw,
                car_max_speed_raw = packet.car_max_speed_raw,
                road_plane_y  = packet.road_plane_y,
                tyre_temp_fl  = packet.tyre_temp_fl,
                tyre_temp_fr  = packet.tyre_temp_fr,
                tyre_temp_rl  = packet.tyre_temp_rl,
                tyre_temp_rr  = packet.tyre_temp_rr,
            ))

    def finalize_lap(self, lap_num: int, lap_time_ms: int) -> None:
        """Called from EventDispatcher thread on LAP_COMPLETED."""
        with self._lock:
            frames = list(self._current_frames)
            self._current_frames = []
        if not frames:
            return
        stats = _compute_stats(frames, lap_num, lap_time_ms)
        with self._lock:
            self._completed.insert(0, stats)
            if len(self._completed) > self._max_laps:
                self._completed.pop()

    def last_lap(self) -> Optional[LapStats]:
        with self._lock:
            return self._completed[0] if self._completed else None

    def last_lap_frames(self) -> "list[TelemetryFrame]":
        with self._lock:
            return list(self._completed[0].frames) if self._completed else []

    def best_lap(self) -> Optional[LapStats]:
        with self._lock:
            if not self._completed:
                return None
            return min(self._completed, key=lambda s: s.lap_time_ms)

    def get_lap(self, lap_num: int) -> Optional[LapStats]:
        with self._lock:
            for s in self._completed:
                if s.lap_num == lap_num:
                    return s
            return None

    def recent_laps(self, n: int = 3) -> list[LapStats]:
        with self._lock:
            return list(self._completed[:n])

    def lap_count(self) -> int:
        with self._lock:
            return len(self._completed)
