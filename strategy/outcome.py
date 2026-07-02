"""Deterministic race outcome computation for strategy comparison.

Pure module — no Qt, no API calls, no DB access.
Mirrors the style of strategy/feasibility.py and strategy/relative_degradation.py.

Provides:
  compute_outcome(option, params, degradation) -> dict
  compare_outcomes(options, params, degradation) -> list[dict]
  format_outcome_comparison_for_prompt(compare_result) -> str

Formula (T_race):
  T_race = green_time_s + pit_time_s

  green_time_s = sum over all stints of:
    sum over laps i=1..n of:
      base_lap_s + degradation_penalty(i, compound, deg_entry)

  where degradation_penalty(lap_index_0, compound, deg_entry):
    rate_s_per_lap = (pace_loss_at_cliff_s / cliff_lap_practice) if cliff data present, else 0.0
    scaled_rate = rate_s_per_lap * tyre_wear_multiplier
    linear_penalty = lap_index_0 * scaled_rate
    cliff_penalty = max(0, lap_index_0 - (cliff_lap_practice - 1)) * pace_loss_at_cliff_s
                    when lap_index_0 >= cliff_lap_practice (0-indexed: lap_index_0 >= cliff_lap_practice)
    penalty = linear_penalty + cliff_penalty

  pit_time_s = n_stops * pit_loss_secs + sum_over_stops ceil(fuel_per_stop / refuel_speed_lps)

  fuel_per_stop_i = fuel_burn_per_lap * laps_in_next_stint, capped at 100.0 L

GT7 domain constants:
  - Tank capacity is always 100.0 litres (100% == 100 L; starting fuel == 100).
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from strategy.ai_planner import RaceParams, StrategyOption

# GT7 domain constant: full tank is always 100 litres.
_GT7_TANK_CAPACITY = 100.0


# ---------------------------------------------------------------------------
# Per-stint degradation model
# ---------------------------------------------------------------------------

def _per_lap_penalty_s(
    lap_index_0: int,
    cliff_lap_practice: int,
    pace_loss_at_cliff_s: float,
    tyre_wear_multiplier: float,
) -> float:
    """Compute the degradation penalty in seconds for a single lap.

    Parameters
    ----------
    lap_index_0:
        0-based index of the lap within the stint (lap 1 = 0, lap 2 = 1, ...).
    cliff_lap_practice:
        The practice lap index (1-based) at which the cliff starts.
        0 means no cliff data available.
    pace_loss_at_cliff_s:
        Seconds of pace loss per lap beyond the cliff.
    tyre_wear_multiplier:
        Scales the linear pre-cliff degradation rate (not the cliff step itself).

    Model:
      Linear region (before or at cliff): lap_index_0 * rate_per_lap * tyre_wear_multiplier
        where rate_per_lap = pace_loss_at_cliff_s / cliff_lap_practice
      Cliff step (laps strictly after cliff_lap_practice boundary, 0-indexed >= cliff_lap_practice):
        add pace_loss_at_cliff_s per lap beyond the cliff boundary
    """
    if cliff_lap_practice <= 0 or pace_loss_at_cliff_s <= 0.0:
        return 0.0

    # Linear degradation rate (s per lap) scaled for wear multiplier
    rate_s_per_lap = (pace_loss_at_cliff_s / cliff_lap_practice) * tyre_wear_multiplier

    # Linear component: accumulates every lap in the stint
    linear_penalty = lap_index_0 * rate_s_per_lap

    # Cliff step: added for each lap at or beyond the cliff boundary
    # cliff_lap_practice is 1-indexed; 0-indexed boundary = cliff_lap_practice - 1
    # We apply the cliff step to lap_index_0 >= cliff_lap_practice (0-indexed),
    # i.e. the lap AFTER the cliff boundary.
    cliff_step_count = max(0, lap_index_0 - cliff_lap_practice + 1)
    cliff_penalty = cliff_step_count * pace_loss_at_cliff_s

    return linear_penalty + cliff_penalty


# ---------------------------------------------------------------------------
# compute_outcome
# ---------------------------------------------------------------------------

def compute_outcome(
    option: "StrategyOption",
    params: "RaceParams",
    degradation: dict | None,
) -> dict:
    """Compute a deterministic race outcome for a single strategy option.

    Parameters
    ----------
    option:
        StrategyOption with stints list[dict {compound, laps, ref_lap_ms, pace_threshold_ms}].
    params:
        RaceParams (track, total_laps, tyre_wear_multiplier, fuel_burn_per_lap,
        refuel_speed_lps, pit_loss_secs).
    degradation:
        Per-compound degradation dict as returned by analyse_tyre_degradation,
        keyed by compound code.  May be None or missing entries for a compound.

    Returns
    -------
    dict with keys:
        estimated_time_s  – total race time (green_time_s + pit_time_s)
        pit_time_s        – total pit time
        green_time_s      – driving time only
        n_stops           – number of pit stops (len(stints) - 1)
        per_stint         – list[dict {compound, laps, base_lap_s, deg_penalty_s, stint_time_s}]
        confidence        – "high" | "medium" | "low"
        assumptions       – list[str] of human-readable fallback notes
    """
    degradation = degradation or {}
    assumptions: list[str] = []
    stints: list[dict] = list(option.stints or [])
    n_stops = max(0, len(stints) - 1)

    tyre_wear_mult = float(getattr(params, "tyre_wear_multiplier", 1.0) or 1.0)
    fuel_burn_per_lap = float(getattr(params, "fuel_burn_per_lap", 0.0) or 0.0)
    refuel_speed_lps = float(getattr(params, "refuel_speed_lps", 1.0) or 1.0)
    pit_loss_secs = float(getattr(params, "pit_loss_secs", 0.0) or 0.0)

    # Determine the fastest compound ref_lap_ms across all stints as a fallback base pace.
    # "Fastest" = smallest positive ref_lap_ms.
    _all_refs = [
        float(s.get("ref_lap_ms", 0) or 0)
        for s in stints
        if float(s.get("ref_lap_ms", 0) or 0) > 0
    ]
    _fastest_ref_ms: float = min(_all_refs) if _all_refs else 0.0

    # Representative pace from params (total_laps can give an approximation via estimated_time_s).
    # If everything is zero we fall back to 90 s which is a weak assumption — noted.
    _param_pace_s: float = 0.0
    if hasattr(params, "estimated_time_s"):
        _et = float(getattr(params, "estimated_time_s", 0.0) or 0.0)
        _tl = int(getattr(params, "total_laps", 0) or 0)
        if _et > 0 and _tl > 0:
            _param_pace_s = _et / _tl

    # Confidence tracking: "high" unless degradation data was missing for any compound.
    _any_deg_missing = False
    _any_deg_low = False

    per_stint_results: list[dict] = []
    green_time_s: float = 0.0

    for stint in stints:
        compound: str = str(stint.get("compound", ""))
        laps: int = int(stint.get("laps", 0) or 0)
        ref_lap_ms: float = float(stint.get("ref_lap_ms", 0) or 0)

        # --- Resolve base lap time ---
        if ref_lap_ms > 0:
            base_lap_s = ref_lap_ms / 1000.0
        elif _fastest_ref_ms > 0:
            base_lap_s = _fastest_ref_ms / 1000.0
            assumptions.append(
                f"Stint {compound}: ref_lap_ms missing/zero — "
                f"fell back to fastest compound ref ({_fastest_ref_ms / 1000:.3f}s)."
            )
        elif _param_pace_s > 0:
            base_lap_s = _param_pace_s
            assumptions.append(
                f"Stint {compound}: ref_lap_ms and fastest-ref both missing — "
                f"fell back to param-derived representative pace ({_param_pace_s:.3f}s)."
            )
        else:
            base_lap_s = 90.0  # last-resort assumption
            assumptions.append(
                f"Stint {compound}: no pace reference available — "
                "fell back to 90.0 s/lap placeholder; result is unreliable."
            )

        # --- Resolve degradation entry ---
        deg_entry: dict = degradation.get(compound, {})
        cliff_lap = int(deg_entry.get("cliff_lap_practice", 0) or 0)
        pace_loss = float(deg_entry.get("pace_loss_at_cliff_s", 0.0) or 0.0)
        has_deg_data = cliff_lap > 0 and pace_loss > 0.0

        if not deg_entry:
            _any_deg_missing = True
            assumptions.append(
                f"Stint {compound}: no degradation data available — "
                "degradation penalty set to 0; time will be understated."
            )
        elif not has_deg_data:
            _any_deg_low = True
            assumptions.append(
                f"Stint {compound}: degradation entry present but cliff data incomplete "
                f"(cliff_lap_practice={cliff_lap}, pace_loss_at_cliff_s={pace_loss}) — "
                "degradation penalty set to 0."
            )

        # --- Integrate stint time over laps ---
        stint_time_s: float = 0.0
        total_deg_penalty_s: float = 0.0
        for lap_index_0 in range(laps):
            penalty = _per_lap_penalty_s(
                lap_index_0=lap_index_0,
                cliff_lap_practice=cliff_lap,
                pace_loss_at_cliff_s=pace_loss,
                tyre_wear_multiplier=tyre_wear_mult,
            )
            lap_time_s = base_lap_s + penalty
            stint_time_s += lap_time_s
            total_deg_penalty_s += penalty

        green_time_s += stint_time_s
        per_stint_results.append({
            "compound": compound,
            "laps": laps,
            "base_lap_s": base_lap_s,
            "deg_penalty_s": total_deg_penalty_s,
            "stint_time_s": stint_time_s,
        })

    # --- Compute pit time ---
    # For each stop i (0-indexed, between stint i and stint i+1):
    #   fuel_needed = fuel_burn_per_lap * laps_in_next_stint, capped at tank capacity.
    # Refuel time = ceil(fuel_needed / refuel_speed_lps)
    # Total pit time = n_stops * pit_loss_secs + sum(ceil(fuel_needed_i / refuel_speed_lps))
    pit_time_s: float = 0.0
    if n_stops > 0:
        # Fixed pit-lane loss for all stops
        pit_time_s += n_stops * pit_loss_secs
        # Refuel time per stop
        for stop_idx in range(n_stops):
            # The stop between stint stop_idx and stint stop_idx+1
            # We refuel for the NEXT stint (stop_idx + 1)
            next_stint = stints[stop_idx + 1] if (stop_idx + 1) < len(stints) else {}
            next_laps = int(next_stint.get("laps", 0) or 0)
            if fuel_burn_per_lap > 0 and refuel_speed_lps > 0:
                fuel_needed = min(
                    fuel_burn_per_lap * next_laps,
                    _GT7_TANK_CAPACITY,
                )
                refuel_time_s = math.ceil(fuel_needed / refuel_speed_lps)
                pit_time_s += refuel_time_s
            # If fuel or refuel rate is 0, no refuel time added (noted via assumption if needed)

    if n_stops > 0 and (fuel_burn_per_lap <= 0 or refuel_speed_lps <= 0):
        assumptions.append(
            "Refuel time not calculated — fuel_burn_per_lap or refuel_speed_lps is 0."
        )

    estimated_time_s = green_time_s + pit_time_s

    # --- Determine confidence ---
    if _any_deg_missing:
        confidence = "low"
    elif _any_deg_low:
        confidence = "medium"
    else:
        confidence = "high"

    return {
        "estimated_time_s": estimated_time_s,
        "pit_time_s": pit_time_s,
        "green_time_s": green_time_s,
        "n_stops": n_stops,
        "per_stint": per_stint_results,
        "confidence": confidence,
        "assumptions": assumptions,
    }


# ---------------------------------------------------------------------------
# compare_outcomes
# ---------------------------------------------------------------------------

def compare_outcomes(
    options: list["StrategyOption"],
    params: "RaceParams",
    degradation: dict | None,
) -> list[dict]:
    """Compare deterministic race outcomes for a list of strategy options.

    Parameters
    ----------
    options:
        List of StrategyOption objects.
    params:
        RaceParams.
    degradation:
        Per-compound degradation dict, or None.

    Returns
    -------
    list[dict] in the SAME ORDER as the input options, each entry containing:
        index               – position in the input list (0-based)
        estimated_time_s    – deterministic total race time
        delta_vs_fastest_s  – difference vs the fastest option (0.0 for the fastest)
        rank_by_time        – 1 for fastest, ascending (ties broken by input order)
        confidence          – "high" | "medium" | "low"
        outcome             – the full compute_outcome dict
    """
    if not options:
        return []

    # Compute outcomes for all options
    outcomes = [compute_outcome(opt, params, degradation) for opt in options]

    # Find the fastest estimated_time_s
    min_time = min(o["estimated_time_s"] for o in outcomes)

    # Rank by time (ascending); stable sort by input order for ties
    indexed = list(enumerate(outcomes))
    sorted_by_time = sorted(indexed, key=lambda x: (x[1]["estimated_time_s"], x[0]))

    # Build rank lookup: input_index -> rank_by_time
    rank_lookup: dict[int, int] = {}
    for rank_1based, (orig_idx, _) in enumerate(sorted_by_time, start=1):
        rank_lookup[orig_idx] = rank_1based

    result: list[dict] = []
    for i, outcome in enumerate(outcomes):
        result.append({
            "index": i,
            "estimated_time_s": outcome["estimated_time_s"],
            "delta_vs_fastest_s": outcome["estimated_time_s"] - min_time,
            "rank_by_time": rank_lookup[i],
            "confidence": outcome["confidence"],
            "outcome": outcome,
        })

    return result


# ---------------------------------------------------------------------------
# format_outcome_comparison_for_prompt (optional AI helper)
# ---------------------------------------------------------------------------

def format_outcome_comparison_for_prompt(compare_result: list[dict]) -> str:
    """Format compare_outcomes output as a human-readable text block.

    Suitable for inclusion in an AI prompt to give the model deterministic
    timing context alongside AI-supplied estimates.

    Parameters
    ----------
    compare_result:
        Output of compare_outcomes().

    Returns
    -------
    str — multi-line text block, or empty string if compare_result is empty.
    """
    if not compare_result:
        return ""

    lines = ["## Deterministic race outcome comparison"]
    for entry in compare_result:
        idx = entry["index"]
        t = entry["estimated_time_s"]
        delta = entry["delta_vs_fastest_s"]
        rank = entry["rank_by_time"]
        conf = entry["confidence"]
        minutes, seconds = divmod(t, 60)
        hours, minutes = divmod(int(minutes), 60)
        if hours:
            time_str = f"{hours}h {minutes:02d}m {seconds:05.2f}s"
        else:
            time_str = f"{int(minutes)}m {seconds:05.2f}s"
        delta_str = f"+{delta:.1f}s" if delta > 0 else "fastest"
        lines.append(
            f"  Strategy {idx + 1} (rank by time: {rank}): "
            f"{time_str} — {delta_str} — confidence: {conf}"
        )
    return "\n".join(lines)
