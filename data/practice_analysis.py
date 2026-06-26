"""Pure business-logic helpers for practice session lap analysis.

No Qt, no HTML, no database access. UI layer calls compute_practice_tips()
and renders the result however it likes.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PracticeTips:
    consistency_tip: str = ""
    gap_tip: str = ""
    trend_tip: str = ""
    tyre_tips: list[str] = field(default_factory=list)
    telemetry_tip: str = ""


def compute_practice_tips(
    valid_laps: list[float],
    std_ms: float,
    last_packet,       # GT7Packet | None
    thresholds,        # TyreThresholds | None  (.cold_max, .hot_max)
    last_lap_stats,    # LapStats | None
) -> PracticeTips:
    """Compute human-readable practice tips from lap data and telemetry.

    Parameters
    ----------
    valid_laps:
        List of lap times in milliseconds (may be empty).
    std_ms:
        Standard deviation of valid_laps in milliseconds.
    last_packet:
        Most recent GT7 telemetry packet, or None.
    thresholds:
        Tyre temperature thresholds object with ``cold_max`` and ``hot_max``
        attributes, or None.
    last_lap_stats:
        LapStats for the most recently completed lap, or None.
    """
    tips = PracticeTips()

    # ------------------------------------------------------------------ #
    # Consistency tip
    # ------------------------------------------------------------------ #
    if not valid_laps:
        return tips

    if std_ms > 1500:
        tips.consistency_tip = (
            f"<b>Consistency:</b> High variation ±{std_ms/1000:.2f}s. "
            "Pick one fixed braking marker per corner and commit to it every lap — "
            "time comes from consistency, not heroics."
        )
    elif std_ms > 700:
        tips.consistency_tip = (
            f"<b>Consistency:</b> Moderate variation ±{std_ms/1000:.2f}s. "
            "Good base. Identify your most inconsistent corner and clean that up first."
        )
    else:
        tips.consistency_tip = (
            f"<b>Consistency:</b> Excellent ±{std_ms/1000:.2f}s. "
            "Very repeatable. Shift focus to raw pace — exit speed, late apex, early throttle."
        )

    # ------------------------------------------------------------------ #
    # Gap tip (last lap vs best)
    # ------------------------------------------------------------------ #
    best_ms = min(valid_laps)
    last_ms = valid_laps[-1]
    gap_ms = last_ms - best_ms

    if gap_ms > 2000:
        tips.gap_tip = (
            f"<b>Last lap:</b> {gap_ms/1000:.3f}s off your best. "
            "A large gap usually means one or two specific mistakes — compare braking points "
            "corner by corner."
        )
    elif gap_ms > 400:
        tips.gap_tip = (
            f"<b>Last lap:</b> {gap_ms/1000:.3f}s off your best. "
            "Solid lap. Find your weakest sector and carry 5 km/h more through the apex."
        )
    else:
        tips.gap_tip = (
            f"<b>Last lap:</b> Within {gap_ms/1000:.3f}s of your best. "
            "At the limit — look for last-metre brake release and trail-braking opportunities."
        )

    # ------------------------------------------------------------------ #
    # Trend tip (last 4 laps)
    # ------------------------------------------------------------------ #
    n = len(valid_laps)
    if n >= 4:
        last4 = valid_laps[-4:]
        if last4[-1] < last4[0]:
            tips.trend_tip = (
                "<b>Trend:</b> Getting faster. Keep building momentum. "
                "Avoid making big setup changes mid-session."
            )
        elif last4[-1] > last4[0] + 1000:
            tips.trend_tip = (
                "<b>Trend:</b> Lap times rising. Tyres may be going off or you are fatiguing — "
                "take a cooling lap or check tyre temps on the dashboard."
            )

    # ------------------------------------------------------------------ #
    # Tyre temperature tips
    # ------------------------------------------------------------------ #
    if last_packet is not None and thresholds is not None:
        temps = [
            last_packet.tyre_temp_fl,
            last_packet.tyre_temp_fr,
            last_packet.tyre_temp_rl,
            last_packet.tyre_temp_rr,
        ]
        cold = sum(1 for t in temps if 0 < t < thresholds.cold_max)
        hot = sum(1 for t in temps if t > thresholds.hot_max)
        if cold >= 2:
            tips.tyre_tips.append(
                "<b>Tyres cold:</b> Push harder through corners to generate heat. "
                "Don’t back off mid-corner — keep the load on the tyres."
            )
        elif hot >= 2:
            tips.tyre_tips.append(
                "<b>Tyres hot:</b> Smooth down your inputs. Later throttle on exit and "
                "less aggressive turn-in to bring temps back into range."
            )

    # ------------------------------------------------------------------ #
    # Telemetry tip
    # ------------------------------------------------------------------ #
    if last_lap_stats is not None:
        tel_parts: list[str] = []
        stats = last_lap_stats
        if stats.lock_up_count > 0:
            brk_str = (
                f", braking variance {stats.brake_consistency_m:.1f} m"
                if stats.brake_consistency_m >= 0
                else ""
            )
            tel_parts.append(
                f"<b>Lock-ups:</b> {stats.lock_up_count}{brk_str} — "
                "release brake slightly earlier, trail-brake to the apex"
            )
        if stats.wheelspin_count > 0:
            tel_parts.append(
                f"<b>Wheelspin:</b> {stats.wheelspin_count} — "
                "delay throttle until the car is pointing straighter"
            )
        if stats.oversteer_count > 0:
            exit_os = stats.oversteer_throttle_on_count
            entry_os = stats.oversteer_count - exit_os
            os_parts: list[str] = []
            if entry_os:
                os_parts.append(f"{entry_os} entry")
            if exit_os:
                os_parts.append(f"{exit_os} exit (throttle-on)")
            tel_parts.append(
                f"<b>Oversteer:</b> {stats.oversteer_count} ({', '.join(os_parts)})"
            )
        if stats.snap_throttle_count > 0:
            tel_parts.append(
                f"<b>Snap throttle:</b> {stats.snap_throttle_count} — "
                "roll on gradually from the apex, no pedal stabs"
            )
        tips.telemetry_tip = "<br>".join(tel_parts)

    return tips
