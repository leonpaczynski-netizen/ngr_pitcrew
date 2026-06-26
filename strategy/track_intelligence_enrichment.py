"""
Track intelligence enrichment functions for AI prompt injection.

Derives per-sector fuel load, per-corner speed/load, overtaking zones,
and kerb characterisation from calibration telemetry and the station map.
All functions return empty lists when data is insufficient — callers must
guard against empty output.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# Maps calibration profile IDs to display names for car-mismatch warning
_CALIBRATION_CAR_DISPLAY_NAMES: dict[str, str] = {
    "porsche_911_rsr_991_2017": "Porsche 911 RSR (991) '17",
}


def get_calibration_car_display_name(profile_id: str) -> str:
    return _CALIBRATION_CAR_DISPLAY_NAMES.get(profile_id, profile_id)


def compute_corner_speed_load(
    calibration_laps,   # list[CalibrationLap]
    segments,           # list[DetectedTrackSegment] or reviewed segments
) -> list[dict]:
    """Return entry/apex/exit speed and peak lateral-g for each named corner.

    Speed is derived from calibration lap samples bucketed to the corner's
    lap-progress window. Lateral-g is estimated as (v_ms^2 * |curvature|) / 9.81
    but curvature is NOT on TelemetrySample — we approximate using speed
    change across the corner window as a proxy for peak loading.

    Practical approach: use speed at first, min, and last sample in window
    for entry/apex/exit respectively. Peak lateral-g uses the max centripetal
    acceleration estimated from consecutive speed/position changes.

    Corners with no samples are omitted from output.
    """
    import math

    # Collect APEX_ZONE segments only
    apex_segments = [
        s for s in segments
        if getattr(s, "segment_type", None) is not None
        and str(s.segment_type).endswith("APEX_ZONE")
        and getattr(s, "confidence", "LOW") not in ("INSUFFICIENT",)
    ]

    if not apex_segments or not calibration_laps:
        return []

    # Build a combined sorted list of (progress, speed_kph) from all usable laps
    all_samples: list[tuple[float, float]] = []
    for lap in calibration_laps:
        if not getattr(lap, "is_usable", True):
            continue
        for s in getattr(lap, "samples", []):
            prog = getattr(s, "lap_progress", None)
            speed = getattr(s, "speed_kph", None)
            if prog is not None and speed is not None:
                all_samples.append((prog, speed))

    if not all_samples:
        return []

    all_samples.sort(key=lambda x: x[0])
    progs = [x[0] for x in all_samples]
    speeds = [x[1] for x in all_samples]

    results = []
    for seg in apex_segments:
        p_start = getattr(seg, "lap_progress_start", 0.0)
        p_end = getattr(seg, "lap_progress_end", 1.0)

        # Extend window slightly to capture entry/exit
        p_entry_start = max(0.0, p_start - 0.01)
        p_exit_end = min(1.0, p_end + 0.01)

        # Find samples in window
        window_speeds = [
            speeds[i] for i, p in enumerate(progs)
            if p_entry_start <= p <= p_exit_end
        ]
        if not window_speeds:
            continue

        entry_speed = window_speeds[0]
        apex_speed = min(window_speeds)
        exit_speed = window_speeds[-1]

        # Estimate peak lateral-g from speed change and distance
        # Use centripetal approximation: at apex, car is turning; g = v^2 / (r * g_earth)
        # We don't have radius directly, so approximate from speed drop:
        # Higher speed drop into corner = tighter radius = higher g
        speed_drop = max(0.0, entry_speed - apex_speed)
        # Rough empirical: 1 kph speed drop per 1 km/h entry corresponds to ~0.1g
        # Use a conservative estimate based on entry speed and apex speed ratio
        if entry_speed > 0:
            apex_v_ms = apex_speed / 3.6
            # Estimate radius from typical GT car corner geometry
            # For a rough g estimate: g_lateral ≈ (entry_speed / apex_speed)^2 * base_g
            # Better: use the speed minimum as proxy for curvature
            # peak_g ≈ apex_v_ms^2 / (r * 9.81); r unknown, so use speed drop as proxy
            peak_g = round(min(4.0, (entry_speed - apex_speed) / max(1.0, entry_speed) * 3.5), 2)
        else:
            peak_g = 0.0

        corner_id = getattr(seg, "display_name", None) or getattr(seg, "segment_id", f"Corner@{p_start:.2f}")
        results.append({
            "corner_id": corner_id,
            "display_name": corner_id,
            "entry_speed_kph": round(entry_speed, 1),
            "apex_speed_kph": round(apex_speed, 1),
            "exit_speed_kph": round(exit_speed, 1),
            "peak_lateral_g": peak_g,
        })

    return results


def compute_sector_fuel(
    calibration_laps,   # list[CalibrationLap]
    sectors,            # list[dict] with keys: sector_name, start_progress, end_progress
) -> list[dict]:
    """Return throttle-time integral per sector as a fuel load proxy.

    GT7 does not expose a fuel channel in the UDP packet. Throttle × time
    is used as a relative fuel load indicator. The active fuel multiplier
    is NOT applied here — callers must state it separately in the prompt.

    Sectors with no samples are omitted from output (not zeroed).
    """
    if not calibration_laps or not sectors:
        return []

    results = []
    for sector in sectors:
        name = sector.get("sector_name", "Unknown")
        s_start = sector.get("start_progress", 0.0)
        s_end = sector.get("end_progress", 1.0)

        total_integral = 0.0
        total_samples = 0
        lap_count = 0

        for lap in calibration_laps:
            if not getattr(lap, "is_usable", True):
                continue
            lap_samples = getattr(lap, "samples", [])
            sector_samples = [
                s for s in lap_samples
                if s_start <= getattr(s, "lap_progress", -1.0) <= s_end
            ]
            if not sector_samples:
                continue

            lap_count += 1
            prev_ts = None
            for s in sector_samples:
                ts = getattr(s, "timestamp_ms", None)
                throttle = getattr(s, "throttle", 0.0) or 0.0
                if prev_ts is not None and ts is not None:
                    dt_s = (ts - prev_ts) / 1000.0
                    if 0 < dt_s < 2.0:  # guard against lap-boundary jumps
                        total_integral += throttle * dt_s
                        total_samples += 1
                prev_ts = ts

        if lap_count == 0 or total_samples == 0:
            continue  # omit sectors with no data (AC1)

        results.append({
            "sector_name": name,
            "throttle_integral": round(total_integral / lap_count, 2),
            "sample_count": total_samples // lap_count,
            "lap_count": lap_count,
        })

    return results


def compute_overtaking_zones(
    reference_path,     # ReferencePath (has .points list with lap_progress and speed_kph_avg)
    segments,           # list[DetectedTrackSegment]
) -> list[dict]:
    """Return straights where peak speed minus following-corner minimum is >= 80 kph.

    Uses ReferencePath speed_kph_avg values (not StationPoint, which has no speed).
    Wraps around lap end to find following corner for end-of-lap straights.
    """
    if not reference_path or not segments:
        return []

    ref_points = getattr(reference_path, "points", [])
    if not ref_points:
        return []

    def speed_at_progress(p_start, p_end):
        pts = [
            pt for pt in ref_points
            if p_start <= getattr(pt, "lap_progress", -1.0) <= p_end
        ]
        speeds = [getattr(pt, "speed_kph_avg", 0.0) for pt in pts]
        return speeds

    # Identify straight segments and apex segments
    straight_segs = [
        s for s in segments
        if str(getattr(s, "segment_type", "")).endswith("STRAIGHT")
        or str(getattr(s, "segment_type", "")).endswith("FUEL_SAVING_CANDIDATE")
    ]
    apex_segs = sorted(
        [s for s in segments if str(getattr(s, "segment_type", "")).endswith("APEX_ZONE")],
        key=lambda s: getattr(s, "lap_progress_start", 0.0),
    )

    if not straight_segs or not apex_segs:
        return []

    results = []
    for straight in straight_segs:
        s_start = getattr(straight, "lap_progress_start", 0.0)
        s_end = getattr(straight, "lap_progress_end", 1.0)
        straight_speeds = speed_at_progress(s_start, s_end)
        if not straight_speeds:
            continue
        peak_speed = max(straight_speeds)

        # Find the immediately following apex segment (by progress)
        following_apex = None
        for apex in apex_segs:
            if getattr(apex, "lap_progress_start", 0.0) >= s_end:
                following_apex = apex
                break
        if following_apex is None:
            # Wrap: use first apex on the lap
            following_apex = apex_segs[0] if apex_segs else None
        if following_apex is None:
            continue

        apex_start = getattr(following_apex, "lap_progress_start", 0.0)
        apex_end = getattr(following_apex, "lap_progress_end", 1.0)
        apex_speeds = speed_at_progress(apex_start, apex_end)
        if not apex_speeds:
            continue
        min_apex_speed = min(apex_speeds)

        delta = peak_speed - min_apex_speed
        if delta < 80.0:
            continue

        straight_name = getattr(straight, "display_name", None) or f"Straight@{s_start:.2f}–{s_end:.2f}"
        corner_id = getattr(following_apex, "display_name", None) or getattr(following_apex, "segment_id", "corner")

        results.append({
            "straight_id": getattr(straight, "segment_id", straight_name),
            "display_name": straight_name,
            "delta_kph": round(delta, 1),
            "peak_speed_kph": round(peak_speed, 1),
            "following_corner_id": corner_id,
            "following_corner_min_kph": round(min_apex_speed, 1),
            "lap_progress_start": round(s_start, 4),
            "lap_progress_end": round(s_end, 4),
        })

    return results


def compute_kerb_characterisation(
    calibration_laps,   # list[CalibrationLap]
    segments,           # list[DetectedTrackSegment]
) -> list[dict]:
    """Return per-corner kerb and track-limits characterisation from surface telemetry.

    Requires TelemetrySample.surface_type to be populated (GROUP 19A addition).
    If surface_type is missing from samples, all corners return NONE.

    Always returns a result for every named corner (AC9 requirement:
    NONE corners must still appear with a "no kerb contact" note).
    """
    apex_segments = [
        s for s in segments
        if str(getattr(s, "segment_type", "")).endswith("APEX_ZONE")
    ]

    if not apex_segments:
        return []

    results = []
    for seg in apex_segments:
        p_start = getattr(seg, "lap_progress_start", 0.0)
        p_end = getattr(seg, "lap_progress_end", 1.0)
        corner_id = getattr(seg, "display_name", None) or f"Corner@{p_start:.2f}"

        kerb_count = 0
        grass_count = 0
        total_count = 0

        for lap in calibration_laps:
            if not getattr(lap, "is_usable", True):
                continue
            for s in getattr(lap, "samples", []):
                prog = getattr(s, "lap_progress", None)
                if prog is None:
                    continue
                # Handle wrap-around at start/finish
                in_range = (p_start <= prog <= p_end) if p_start <= p_end else (prog >= p_start or prog <= p_end)
                if not in_range:
                    continue
                total_count += 1
                surface = getattr(s, "surface_type", "road")
                if surface == "kerb":
                    kerb_count += 1
                elif surface == "grass":
                    grass_count += 1

        kerb_available = kerb_count > 0
        if total_count == 0 or kerb_count == 0:
            kerb_aggressiveness = "NONE"
        elif kerb_count / total_count > 0.15:
            kerb_aggressiveness = "HIGH"
        else:
            kerb_aggressiveness = "LOW"

        track_limits = "hard_limits" if grass_count > 0 else "runoff_available"

        results.append({
            "corner_id": corner_id,
            "display_name": corner_id,
            "kerb_available": kerb_available,
            "kerb_aggressiveness": kerb_aggressiveness,
            "track_limits_proximity": track_limits,
            "kerb_sample_count": kerb_count,
            "grass_sample_count": grass_count,
            "total_sample_count": total_count,
        })

    return results


def format_sector_fuel_block(sector_fuel: list[dict], fuel_multiplier: float) -> str:
    if not sector_fuel:
        return ""
    lines = [
        "## Calibration Fuel Load by Sector (Porsche 911 RSR reference)",
        f"Fuel multiplier (event setting): {fuel_multiplier}×",
        "Note: fuel load shown as throttle-time integral (no absolute fuel channel in GT7 packet).",
    ]
    for sf in sector_fuel:
        lines.append(
            f"  {sf['sector_name']}: throttle integral {sf['throttle_integral']:.2f} s "
            f"({sf['sample_count']} samples, {sf['lap_count']} laps)"
        )
    lines.append("(Sectors with no calibration data omitted.)")
    return "\n".join(lines)


def format_corner_speed_load_block(corners: list[dict]) -> str:
    if not corners:
        return ""
    lines = ["## Calibration Corner Speed and Load (Porsche 911 RSR reference)"]
    for c in corners:
        lines.append(
            f"  {c['display_name']}: entry {c['entry_speed_kph']:.0f} kph | "
            f"apex {c['apex_speed_kph']:.0f} kph | exit {c['exit_speed_kph']:.0f} kph | "
            f"peak {c['peak_lateral_g']:.2f} g"
        )
    lines.append("(Corners with no calibration data omitted.)")
    return "\n".join(lines)


def format_overtaking_zones_block(zones: list[dict]) -> str:
    if not zones:
        return ""
    lines = ["## Primary Overtaking Opportunities (calibration-derived)"]
    for z in zones:
        lines.append(
            f"  {z['display_name']}: peak {z['peak_speed_kph']:.0f} kph → "
            f"{z['following_corner_id']} min {z['following_corner_min_kph']:.0f} kph | "
            f"delta {z['delta_kph']:.0f} kph"
        )
    lines.append("(Only straights with ≥80 kph speed delta to next corner apex listed.)")
    return "\n".join(lines)


def format_kerb_block(kerb_data: list[dict]) -> str:
    if not kerb_data:
        return ""
    lines = [
        "## Kerb Characterisation by Corner (Porsche 911 RSR reference)",
    ]
    for k in kerb_data:
        lines.append(
            f"  {k['display_name']}: kerb_available={k['kerb_available']} | "
            f"aggressiveness={k['kerb_aggressiveness']} | "
            f"track_limits={k['track_limits_proximity']}"
        )
    lines.append(
        "Note: kerb data reflects calibration car behaviour. "
        "All corners listed; NONE = kerb not used in calibration for that corner."
    )
    return "\n".join(lines)


def compute_corner_gear_usage(
    calibration_laps: list,
    segments: list,
    rev_limit_threshold_pct: float = 0.90,
) -> list[dict]:
    """Per-corner gear and RPM analysis from calibration lap telemetry.

    For each segment identified as an apex zone, buckets samples from all
    calibration laps by lap_progress. Returns entry gear range, apex gear,
    exit gear range, apex RPM, and whether the rev limiter was approached.
    Corners with fewer than 3 samples in any zone are omitted.
    """
    from statistics import mean as _mean, mode as _mode

    apex_segments = [
        s for s in segments
        if str(getattr(s, "segment_type", "")).endswith("APEX_ZONE")
    ]

    if not apex_segments or not calibration_laps:
        return []

    # Build global per-gear max RPM across all calibration laps and all samples
    global_gear_max_rpm: dict[int, float] = {}
    for lap in calibration_laps:
        if not getattr(lap, "is_usable", True):
            continue
        for sample in getattr(lap, "samples", []):
            g = getattr(sample, "gear", None)
            r = getattr(sample, "rpm", None)
            if g is not None and r is not None and r > 0:
                g = int(g)
                r = float(r)
                if g not in global_gear_max_rpm or r > global_gear_max_rpm[g]:
                    global_gear_max_rpm[g] = r

    results = []
    for seg in apex_segments:
        apex_start = getattr(seg, "lap_progress_start", 0.0)
        apex_end = getattr(seg, "lap_progress_end", 1.0)
        entry_start = max(0.0, apex_start - 0.02)
        exit_end = min(1.0, apex_end + 0.025)

        entry_gears: list[int] = []
        apex_gears: list[int] = []
        exit_gears: list[int] = []
        apex_rpms: list[float] = []
        exit_rpms: list[float] = []

        for lap in calibration_laps:
            if not getattr(lap, "is_usable", True):
                continue
            for s in getattr(lap, "samples", []):
                prog = getattr(s, "lap_progress", None)
                gear = getattr(s, "gear", None)
                rpm = getattr(s, "rpm", None)
                if prog is None:
                    continue
                if entry_start <= prog < apex_start:
                    if gear is not None:
                        entry_gears.append(int(gear))
                elif apex_start <= prog <= apex_end:
                    if gear is not None:
                        apex_gears.append(int(gear))
                    if rpm is not None:
                        apex_rpms.append(float(rpm))
                elif apex_end < prog <= exit_end:
                    if gear is not None:
                        exit_gears.append(int(gear))
                    if rpm is not None:
                        exit_rpms.append(float(rpm))

        # Skip corner if any zone has < 3 samples
        if len(entry_gears) < 3 or len(apex_gears) < 3 or len(exit_gears) < 3:
            continue

        # Apex gear: mode (most common value)
        apex_gear = max(set(apex_gears), key=apex_gears.count)

        # Limiter approached: compare mean exit RPM against global ceiling for exit gear
        exit_gear_mode = max(set(exit_gears), key=exit_gears.count) if exit_gears else None
        observed_ceiling = global_gear_max_rpm.get(exit_gear_mode, 0.0) if exit_gear_mode is not None else 0.0
        if exit_rpms and observed_ceiling > 0:
            limiter_approached = _mean(exit_rpms) > rev_limit_threshold_pct * observed_ceiling
        else:
            limiter_approached = False

        corner_id = (
            getattr(seg, "display_name", None)
            or getattr(seg, "segment_id", f"Corner@{apex_start:.2f}")
        )

        results.append({
            "corner_id": corner_id,
            "entry_gear_min": min(entry_gears),
            "entry_gear_max": max(entry_gears),
            "apex_gear": apex_gear,
            "exit_gear_min": min(exit_gears),
            "exit_gear_max": max(exit_gears),
            "apex_rpm_avg": _mean(apex_rpms) if apex_rpms else 0.0,
            "limiter_approached": limiter_approached,
            "observed_ceiling_rpm": observed_ceiling,
        })

    return results


def format_corner_gear_usage(gear_data: list[dict]) -> str:
    """Format corner gear usage for AI prompt injection."""
    lines = []
    for c in gear_data:
        limiter_note = " ⚠ limiter approached" if c.get("limiter_approached") else ""
        lines.append(
            f"  {c['corner_id']}: entry {c['entry_gear_min']}–{c['entry_gear_max']}, "
            f"apex {c['apex_gear']}, exit {c['exit_gear_min']}–{c['exit_gear_max']}, "
            f"apex RPM {c['apex_rpm_avg']:.0f}{limiter_note}"
        )
    return "\n".join(lines)


def format_car_mismatch_warning(active_car_name: str, calib_car_display: str) -> str:
    return (
        f"## Car Mismatch Warning\n"
        f"Active event car \"{active_car_name}\" differs from calibration car \"{calib_car_display}\".\n"
        f"Corner speeds, kerb characterisation, and fuel load data above reflect {calib_car_display} behaviour.\n"
        f"Apply calibration data directionally; absolute values may not transfer to {active_car_name}."
    )
