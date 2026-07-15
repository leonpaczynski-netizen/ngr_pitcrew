"""Deterministic gearbox-analysis text formatter.

Turns a ``gearbox_analysis`` dict (from ``LapStats``) into a human-readable
summary block used by the diagnostic gearbox view. Pure formatting; no AI,
network, or Qt dependencies.

Extracted from the former ``strategy.ai_planner.format_gearbox_for_prompt``
during the determinism rebuild (Sprint 1); the trailing AI-instruction
paragraph was dropped as it only made sense inside an LLM prompt.
"""
from __future__ import annotations


def format_gearbox_summary(ga: dict) -> str:
    """Convert a gearbox_analysis dict into a readable diagnostic block."""
    if not ga:
        return ""
    lines = ["\n## GEARBOX TELEMETRY ANALYSIS (last recorded lap)\n"]

    # Rev limiter summary
    lim_by_gear = ga.get("limiter_by_gear", {})
    if lim_by_gear:
        lines.append("### Rev Limiter Events")
        for g, info in sorted(lim_by_gear.items()):
            dists = ", ".join(f"{d:.0f}m" for d in info.get("road_dists", []))
            lines.append(
                f"  Gear {g}: {info['count']} hit(s), avg {info['avg_duration_secs']:.1f}s, "
                f"at road dist {dists}"
            )
        top_lim_gear = max(lim_by_gear, key=lambda g: lim_by_gear[g]["avg_duration_secs"])
        top_dur = lim_by_gear[top_lim_gear]["avg_duration_secs"]
        if top_dur > 0.5:
            lines.append(
                f"  [!] Gear {top_lim_gear} is hitting the limiter for {top_dur:.1f}s on average -- "
                f"gearing is TOO SHORT. Extend gear {top_lim_gear} ratio or lengthen final drive."
            )
        elif top_dur > 0.1:
            lines.append(
                f"  Gear {top_lim_gear} briefly touches limiter ({top_dur:.1f}s avg). "
                f"Marginal -- acceptable for qualifying, consider lengthening for race."
            )
    else:
        lines.append("### Rev Limiter: No limiter events detected — gearing is not too short.")

    # Longest straight
    ls = ga.get("longest_straight", {})
    if ls:
        lines.append("\n### Longest Full-Throttle Section")
        lines.append(
            f"  {ls['length_m']:.0f}m  ({ls['start_dist']:.0f}m -> {ls['end_dist']:.0f}m)  "
            f"Max speed: {ls['max_speed_kmh']:.1f} km/h  "
            f"Entry gear: {ls['entry_gear']}  Braking gear: {ls['braking_gear']}"
        )
        if ls.get("hits_limiter"):
            lead = ls.get("limiter_lead_dist_m")
            lead_str = f"{lead:.0f}m BEFORE braking" if lead else "before braking"
            lines.append(
                f"  [!] Rev limiter reached {lead_str} -- gearing is too short for this straight. "
                f"Extend top gear ratio or final drive to eliminate limiter contact."
            )
        else:
            lines.append(
                "  [OK] No limiter contact on main straight -- gearing is adequate for this straight."
            )

    # Top speed analysis
    ts = ga.get("top_speed_kmh", 0)
    theo = ga.get("theoretical_max_kmh")
    pct = ga.get("top_speed_reached_pct")
    if ts > 0:
        lines.append("\n### Top Speed")
        if theo and pct is not None:
            lines.append(f"  Achieved: {ts:.1f} km/h  |  Theoretical max: {theo:.1f} km/h  |  {pct:.1f}% of maximum")
            if pct < 90:
                lines.append(
                    f"  [!] Only {pct:.0f}% of theoretical max reached -- gearing may be too LONG "
                    f"or the track is too short/slow for top gear. Consider shorter final drive."
                )
        else:
            lines.append(f"  Achieved: {ts:.1f} km/h")

    # Corner exits
    exits = ga.get("corner_exits", [])
    if exits:
        lines.append("\n### Corner Exit Analysis (throttle-on events)")
        low_rpm_exits = [e for e in exits if e["exit_rpm"] < 4500]
        for e in exits[:8]:
            upshift = f"{e['time_to_upshift_ms']}ms to upshift" if e.get("time_to_upshift_ms") else "no upshift needed"
            lines.append(
                f"  {e['road_dist']:.0f}m: gear {e['exit_gear']}  RPM {e['exit_rpm']:.0f}  "
                f"{e['speed_kmh']:.0f} km/h  [{upshift}]"
            )
        if low_rpm_exits:
            avg_rpm = sum(e["exit_rpm"] for e in low_rpm_exits) / len(low_rpm_exits)
            lines.append(
                f"  [!] {len(low_rpm_exits)} corner exit(s) below 4500 RPM (avg {avg_rpm:.0f} RPM) -- "
                f"engine is below peak power band at exit. Consider shortening 1st-2nd gear ratios "
                f"for better acceleration out of slow corners."
            )

    # Gear time histogram
    hist = ga.get("gear_time_secs", {})
    if hist:
        lines.append("\n### Time in Each Gear")
        gear_line = "  " + "  |  ".join(
            f"G{g}: {t:.1f}s" for g, t in sorted(hist.items())
        )
        lines.append(gear_line)

    return "\n".join(lines)
