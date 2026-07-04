"""Discipline-aware telemetry blocks for AI setup prompts (OFR-2).

WHY IT EXISTS
  QUALIFYING and RACE sessions demand different telemetry signals in an AI
  setup prompt. Qualifying care about peak metrics (best lap, peak lateral G,
  lock-up frequency, rotation); races care about consistency and efficiency
  (fuel per lap, lock-up/wheelspin *rates*, lap-time std-dev, tyre temps over
  a stint). This module owns both blocks so ai_planner.py can stay focused on
  prompt orchestration rather than discipline-specific formatting.

PURITY CONTRACT
  • No PyQt6.
  • No sqlite3 / file I/O / config reads.
  • Never raises — all public functions wrap internals defensively.

HONESTY
  Data labels follow the [measured]/[calculated]/[estimated] convention
  established in strategy/ai_planner.py's _DATA_QUALITY_NOTE:
    measured  = direct GT7 packet values (lap time, fuel, tyre temp)
    calculated = derived via physics formulas (lock-up threshold, std-dev,
                 brake consistency, wheelspin, snap-throttle, oversteer split)
    estimated  = inferred proxy with uncertainty (lateral G = angvel_z × speed / 9.81)
"""

from __future__ import annotations

import math
from statistics import stdev
from typing import Callable, Optional

from data.setup_context import normalise_purpose, SetupPurpose


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _default_ms_to_str(ms: int) -> str:
    """Fallback lap-time formatter: mm:ss.mmm.  Never raises."""
    try:
        if ms <= 0:
            return "—"
        total_s = ms / 1000.0
        m = int(total_s // 60)
        s = total_s - m * 60
        return f"{m}:{s:06.3f}"
    except Exception:  # pragma: no cover - defensive
        return "—"


def _clean_laps(rows: list) -> list:
    """Return rows where is_pit_lap == 0 AND is_out_lap == 0.

    Deliberately does NOT reuse data/recommendation_scoring.aggregate_lap_window
    because that function aggregates away per-row data; here we need per-lap values.
    Never raises.
    """
    out = []
    for r in rows:
        try:
            if r.get("is_pit_lap", 0) == 0 and r.get("is_out_lap", 0) == 0:
                out.append(r)
        except Exception:  # pragma: no cover - defensive
            pass
    return out


def _safe_mean(values: list) -> float:
    """Mean of a list of numeric values.  Returns 0.0 on empty/error."""
    try:
        if not values:
            return 0.0
        return sum(values) / len(values)
    except Exception:  # pragma: no cover - defensive
        return 0.0


def _safe_float(v, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _safe_int(v, default: int = 0) -> int:
    try:
        if v is None:
            return default
        return int(v)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_discipline_telemetry_block(
    laps: list,
    purpose,
    *,
    ms_to_str: Optional[Callable[[int], str]] = None,
) -> "str | None":
    """Return a discipline-specific telemetry block for AI setup prompts.

    Parameters
    ----------
    laps:
        Per-lap telemetry rows (list of dicts, as returned by
        ``SessionDB.get_session_laps``).  May be empty or None — both are
        handled defensively.
    purpose:
        Session purpose in any form ``normalise_purpose`` accepts: strings
        like "Race Setup", "Qualifying", "Qualifying Setup"; a
        ``SetupPurpose`` enum member; or None.
    ms_to_str:
        Optional callable(int) → str for formatting lap times.  When None a
        local mm:ss.mmm formatter is used.

    Returns
    -------
    str
        The formatted telemetry block (always ends with "\\n").
    None
        Sentinel: the purpose resolved to UNKNOWN — callers must keep the
        generic per-lap telemetry block byte-for-byte unchanged.
    """
    try:
        disc = normalise_purpose(purpose)
    except Exception:  # pragma: no cover - defensive
        disc = SetupPurpose.UNKNOWN

    if disc == SetupPurpose.UNKNOWN:
        return None

    fmt = ms_to_str if callable(ms_to_str) else _default_ms_to_str
    safe_laps = laps if isinstance(laps, list) else []
    clean = _clean_laps(safe_laps)

    if disc == SetupPurpose.QUALIFYING:
        return _build_qualifying_block(clean, fmt)
    if disc == SetupPurpose.RACE:
        return _build_race_block(clean, fmt)
    # PRACTICE, TEST, and any future purpose deliberately return None so callers
    # keep the generic per-lap telemetry block byte-for-byte unchanged (AC5).
    # Real free-practice sessions ARE stored with session_type='practice', so
    # falling through to a RACE block here would corrupt those prompts.
    return None


# ---------------------------------------------------------------------------
# QUALIFYING block
# ---------------------------------------------------------------------------

def _build_qualifying_block(clean: list, ms_to_str: Callable) -> str:
    """Peak-metrics focus for qualifying sessions."""
    lines = [
        "\n## Per-Lap Telemetry — QUALIFYING (peak metrics focus)"
        " [calculated/measured/estimated]"
    ]

    if not clean:
        lines.append("No clean laps available.")
        return "\n".join(lines) + "\n"

    # Best lap [measured]
    lap_times = [_safe_int(r.get("lap_time_ms"), 0) for r in clean]
    valid_times = [t for t in lap_times if t > 0]
    if valid_times:
        best_ms = min(valid_times)
        lines.append(f"Best lap: {ms_to_str(best_ms)} [measured]")

    # Peak lateral G [estimated]
    lat_g_vals = [_safe_float(r.get("max_lat_g"), 0.0) for r in clean]
    peak_lat_g = max(lat_g_vals) if lat_g_vals else 0.0
    lines.append(
        f"Peak lateral G: {peak_lat_g:.2f} g [estimated]"
        " (estimated: angvel_z × speed / 9.81)"
    )

    # Lock-up count [calculated]
    total_lockups = sum(_safe_int(r.get("lock_up_count"), 0) for r in clean)
    lines.append(f"Total lock-ups across clean laps: {total_lockups} [calculated]")

    # Brake consistency [calculated]
    bc_vals = [_safe_float(r.get("brake_consistency_m"), -1.0) for r in clean]
    available_bc = [v for v in bc_vals if v >= 0.0]
    if available_bc:
        avg_bc = _safe_mean(available_bc)
        lines.append(f"Brake consistency (std-dev of brake points): {avg_bc:.1f} m [calculated]")
    else:
        lines.append("Brake consistency: unavailable [calculated]")

    # Rotation breakdown [calculated]
    total_oversteer = sum(_safe_int(r.get("oversteer_count"), 0) for r in clean)
    throttle_on_oversteer = sum(_safe_int(r.get("oversteer_throttle_on"), 0) for r in clean)
    entry_oversteer = total_oversteer - throttle_on_oversteer
    lines.append(
        f"Oversteer events (total): {total_oversteer} — "
        f"throttle-on: {throttle_on_oversteer}, entry: {entry_oversteer} [calculated]"
    )

    lines.append(
        "Steering corrections and rival traffic/dirty-air are not measured signals."
    )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# RACE block
# ---------------------------------------------------------------------------

def _build_race_block(clean: list, ms_to_str: Callable) -> str:
    """Consistency and efficiency focus for race sessions."""
    lines = [
        "\n## Per-Lap Telemetry — RACE (consistency/efficiency focus)"
        " [calculated/measured/estimated]"
    ]

    if not clean:
        lines.append("No clean laps available.")
        return "\n".join(lines) + "\n"

    n = len(clean)

    # Fuel used per lap [measured]
    fuel_vals = [_safe_float(r.get("fuel_used"), 0.0) for r in clean]
    lines.append("Fuel per lap [measured]:")
    for i, (r, f) in enumerate(zip(clean, fuel_vals)):
        lap_n = _safe_int(r.get("lap_num"), i + 1)
        lines.append(f"  Lap {lap_n}: {f:.2f} L")
    avg_fuel = _safe_mean(fuel_vals)
    lines.append(f"  Average: {avg_fuel:.2f} L/lap")

    # Lock-up rate/lap [calculated]
    lockup_vals = [_safe_int(r.get("lock_up_count"), 0) for r in clean]
    avg_lockup = _safe_mean(lockup_vals)
    lines.append(f"Lock-up rate: {avg_lockup:.2f}/lap [calculated]")

    # Wheelspin rate/lap [calculated]
    spin_vals = [_safe_int(r.get("wheelspin_count"), 0) for r in clean]
    avg_spin = _safe_mean(spin_vals)
    lines.append(f"Wheelspin rate: {avg_spin:.2f}/lap [calculated]")

    # Snap-throttle count/lap [calculated]
    snap_vals = [_safe_int(r.get("snap_throttle_count"), 0) for r in clean]
    avg_snap = _safe_mean(snap_vals)
    lines.append(f"Snap-throttle rate: {avg_snap:.2f}/lap [calculated]")

    # Lap-time consistency = std-dev [calculated]
    lap_times = [_safe_int(r.get("lap_time_ms"), 0) for r in clean]
    valid_times = [t for t in lap_times if t > 0]
    if len(valid_times) == 1:
        lines.append("Lap-time consistency (std-dev): N/A (1 lap) [calculated]")
    elif len(valid_times) >= 2:
        sd = stdev(valid_times)
        sd_s = sd / 1000.0
        lines.append(f"Lap-time consistency (std-dev): {sd_s:.3f} s [calculated]")
    else:
        lines.append("Lap-time consistency (std-dev): N/A (no valid lap times) [calculated]")

    # Per-corner tyre temps FL/FR/RL/RR [measured]
    fl_vals = [_safe_float(r.get("tyre_temp_fl_avg"), 0.0) for r in clean]
    fr_vals = [_safe_float(r.get("tyre_temp_fr_avg"), 0.0) for r in clean]
    rl_vals = [_safe_float(r.get("tyre_temp_rl_avg"), 0.0) for r in clean]
    rr_vals = [_safe_float(r.get("tyre_temp_rr_avg"), 0.0) for r in clean]
    avg_fl = _safe_mean(fl_vals)
    avg_fr = _safe_mean(fr_vals)
    avg_rl = _safe_mean(rl_vals)
    avg_rr = _safe_mean(rr_vals)

    if avg_fl == 0.0 and avg_fr == 0.0 and avg_rl == 0.0 and avg_rr == 0.0:
        lines.append("Tyre temps (avg FL/FR/RL/RR): — not recorded [measured]")
    else:
        def _fmt_temp(v: float) -> str:
            return f"{v:.0f}°" if v > 0.0 else "—"
        lines.append(
            f"Tyre temps (avg FL/FR/RL/RR): "
            f"{_fmt_temp(avg_fl)} / {_fmt_temp(avg_fr)} / "
            f"{_fmt_temp(avg_rl)} / {_fmt_temp(avg_rr)} [measured]"
        )

    return "\n".join(lines) + "\n"
