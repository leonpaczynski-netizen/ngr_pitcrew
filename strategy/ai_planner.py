"""AI-powered pre-race strategy analyser.

Sends practice lap data and race parameters to the Claude API and returns
ranked strategy options the driver can load straight into the race plan.

Also provides practice session analysis: aero/fuel trade-off calculation,
car setup recommendations, and suggestions for further practice.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from statistics import mean, stdev
from typing import Optional

from strategy._ai_client import (
    call_api,
    format_setup_for_prompt,
    load_gt7_reference,
)
from strategy.setup_ranges import resolve_ranges
from ui.gt7_data import build_track_context

_JSON_SYSTEM = (
    "Output ONLY a valid JSON object. Begin your response with { and end with }. "
    "No reasoning, no explanations, no markdown, no text before or after the JSON."
)

_RACE_ENGINEERING_CONTEXT = """
## Race engineering framework (apply this methodology)

**Race time model** — compare strategies by total time, not fastest lap:
  T_race = Σ(laps × degraded_pace) + Σ(pit_loss + ceil(fuel/refuel_speed))
Every strategy comparison must use this formula, not isolated lap pace.

**Fuel saving efficiency** — rank methods by seconds lost per litre saved:
1. Slipstream: free if traffic allows
2. Short shifting: ~0.1–0.2 s/lap loss, ~0.1–0.2 L/lap saved — best first active method
3. Lift and coast before braking zones: ~0.3–0.6 s/lap, ~0.15–0.3 L/lap
4. Lean fuel map: ~0.8–1.5 s/lap — last resort or when a large saving is needed
Calculate required saving = fuel_burn_per_lap − (tank_capacity / race_laps). If < 0.1 L/lap, short shifting alone is likely sufficient. If > 0.3 L/lap, lift-and-coast or fuel map is needed.

**Endurance setup priority order**:
1. Reliability: no bottoming, no tyre contact, no uncontrollable instability
2. Balance: predictable under full fuel AND low fuel
3. Tyre protection: eliminate wheelspin, brake locking, and excessive toe scrub — before pace
4. Fuel efficiency: gearing, aero drag, power delivery
5. Consistency: reduce lap-time variation
6. Peak pace: only after 1–5 are stable

**Axle-limiting identification** — use lockup rate + wheelspin rate from historical data:
- High lockups/lap (> 0.3) → front braking load excessive → front wear accelerating
- High wheelspin/lap (> 0.5) → rear traction limited → rear wear accelerating
- Combine with setup (spring, ARB, toe, camber, LSD) to confirm which axle will cliff first

**Break-even pace required for extra stop**:
  required_gain_per_lap = additional_pit_loss / laps_on_faster_tyre
  Must account for warm-up and degradation — not peak lap pace alone.

**Testing programme** (structure further_practice recommendations around these):
1. Full-fuel baseline (5–8 laps, race tyre, observe heavy-car balance)
2. Full stint until tyre uncompetitive — record every lap
3. Fuel-saving comparison (3–5 laps each: normal / short-shift / lift-and-coast / fuel map)
4. Alternative compound full stint
5. Pit-loss measurement (pit entry to rejoining racing line)
"""


_DATA_QUALITY_NOTE = (
    "## Data Quality Note\n"
    "Measured = direct GT7 packet values (fuel, speed, position, tyre temp).\n"
    "Calculated = derived via physics formulas (lock-up/wheelspin = wheel slip threshold; "
    "braking consistency = std-dev of brake points; fuel used = level delta per lap).\n"
    "Estimated = inferred proxies with uncertainty (lateral G = angvel_z × speed / 9.81; "
    "tyre wear = radius trend — also varies with temperature; "
    "off-track = road normal Y < threshold).\n"
    "Do not state estimated values as fact. Qualify with 'may indicate' or 'suggests'."
)


@dataclass
class RaceParams:
    track: str
    total_laps: int
    tyre_wear_multiplier: float  # 1.0 = normal wear rate, 2.0 = double race wear
    fuel_burn_per_lap: float     # litres
    refuel_speed_lps: float      # litres per second
    pit_loss_secs: float         # fixed time lost per pit stop (lane + work)
    min_mandatory_stops: int = 0                              # 0 = no rule
    mandatory_compounds: list = field(default_factory=list)  # e.g. ["RS", "RM"]
    race_type: str = "lap"       # "lap" or "timed"
    duration_mins: int = 0       # minutes; only used when race_type == "timed"
    tuning_locked: bool = False  # True when Event disallows all tuning
    allowed_tuning: list = field(default_factory=list)  # e.g. ["suspension", "brake_balance"]
    bop: bool = False            # True when Balance of Performance is active
    avail_tyres: list = field(default_factory=list)  # compound codes available, e.g. ["RM", "RH"]
    track_location_id: str = ""   # seed/resolver ID (e.g. "suzuka_circuit"); empty = no Track Intelligence
    layout_id: str = ""           # layout ID (e.g. "suzuka_circuit__full_course"); empty = no Track Intelligence


@dataclass
class StrategyOption:
    rank: int
    name: str
    stints: list[dict]           # [{compound, laps, ref_lap_ms, pace_threshold_ms}, ...]
    estimated_time_s: float
    pit_time_s: float            # total time spent in pit stops
    summary: str
    risks: str
    positives: str = ""
    negatives: str = ""


@dataclass
class PracticeAnalysis:
    strategies: list[StrategyOption]
    setup_changes: list[str]
    further_practice: list[str]
    aero_fuel_analysis: str
    fuel_saving_analysis: str = ""
    tyre_management: str = ""
    raw_response: str = ""


@dataclass
class CarSetupRecommendation:
    ride_height_front: float
    ride_height_rear: float
    springs_front: float   # GT7 natural frequency in Hz (typically 1.5–12.0)
    springs_rear: float    # GT7 natural frequency in Hz
    dampers_front_comp: int
    dampers_front_ext: int
    dampers_rear_comp: int
    dampers_rear_ext: int
    arb_front: int
    arb_rear: int
    camber_front: float
    camber_rear: float
    toe_front: float
    toe_rear: float
    aero_front: int
    aero_rear: int
    lsd_initial: int
    lsd_accel: int
    lsd_decel: int
    brake_bias: int           # GT7 scale −5 (more front) … +5 (more rear)
    ballast_kg: float
    ballast_position: int     # −50 (rear) … +50 (front)
    power_restrictor: float           # 0–100 %, 100 = unrestricted (Settings Sheet slider)
    final_drive: float                # final drive ratio (0.0 = not applicable / unknown)
    transmission_max_speed_kmh: float # GT7 top-speed slider target
    gear_ratios: list                 # G1→Gn individual ratios; may be empty
    reasoning: str
    lsd_front_initial: int = 0         # Front LSD — AWD only (0 = not applicable)
    lsd_front_accel: int = 0
    lsd_front_decel: int = 0
    ecu_recommendation: str = ""      # plain-English advice on ECU stage + Power Restrictor combo
    shift_rpm: int = 0                # engine RPM to upshift for best lap time (0 = unknown)
    raw_response: str = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse_strategy(
    params: RaceParams,
    lap_data_by_compound: dict[str, list[float]],
    api_key: str,
    degradation: Optional[dict] = None,
    setup_history: str = "",
    car_name: str = "",
    car_specs: dict | None = None,
    setup_comparison: str = "",
    fuel_sequence: list | None = None,
    compound_sequences: dict | None = None,
    corner_issues_summary: str = "",
    model: str | None = None,
    car_id: int = 0,
) -> list[StrategyOption]:
    """Call Claude and return up to 3 ranked strategy options."""
    from strategy.track_context_prompt import get_track_context_for_ai as _get_tc
    _track_ctx = _get_tc(params.track_location_id, params.layout_id, car_name=car_name)
    prompt = _build_race_prompt(params, lap_data_by_compound, degradation,
                                setup_history=setup_history,
                                car_name=car_name, car_specs=car_specs or {},
                                setup_comparison=setup_comparison,
                                fuel_sequence=fuel_sequence or [],
                                compound_sequences=compound_sequences or {},
                                corner_issues_summary=corner_issues_summary,
                                track_context=_track_ctx)
    _warnings: list = []
    if not params.track:
        _warnings.append("Track missing — recommendation may be inaccurate")
    if not params.track_location_id or not params.layout_id:
        _warnings.append("Track Intelligence unavailable — no track_location_id/layout_id set")
    _total_laps = sum(len(v) for v in lap_data_by_compound.values())
    if _total_laps < 3:
        _warnings.append(f"Only {_total_laps} valid laps recorded — confidence reduced")
    _payload = {
        "track": params.track,
        "track_location_id": params.track_location_id or None,
        "layout_id": params.layout_id or None,
        "track_context_included": bool(params.track_location_id and params.layout_id),
        "car": car_name,
        "total_laps": params.total_laps,
        "tyre_wear": params.tyre_wear_multiplier,
        "fuel_burn": params.fuel_burn_per_lap,
        "lap_counts_by_compound": {c: len(v) for c, v in lap_data_by_compound.items()},
        "validation_warnings": _warnings,
    }
    raw = call_api(prompt, api_key, max_tokens=6000, system=_JSON_SYSTEM,
                   feature="Strategy Analysis", structured_payload=_payload,
                   model=model, car_id=car_id, track=params.track)
    try:
        return _parse_strategies(raw)
    except Exception as exc:
        preview = raw[:300].replace("\n", " ") if raw else "(empty)"
        raise RuntimeError(
            f"Strategy JSON parse failed: {exc}\n"
            f"API response start: {preview}"
        ) from exc


def analyse_practice_session(
    params: RaceParams,
    lap_data_by_compound: dict[str, list[float]],
    setup: dict,
    history: dict,
    api_key: str,
    car_name: str = "",
    car_specs: dict | None = None,
    setup_comparison: str = "",
    driver_feedback_str: str = "",
    prev_ai_str: str = "",
    per_lap_telemetry: list | None = None,
    corner_issues_summary: str = "",
    model: str | None = None,
    car_id: int = 0,
    session_id: int = 0,
) -> PracticeAnalysis:
    """Analyse a practice session and return strategies + setup advice + further practice."""
    from strategy.track_context_prompt import get_track_context_for_ai as _get_tc
    _track_ctx = _get_tc(params.track_location_id, params.layout_id, car_name=car_name)
    prompt = _build_practice_prompt(params, lap_data_by_compound, setup, history,
                                    car_name=car_name, car_specs=car_specs or {},
                                    setup_comparison=setup_comparison,
                                    driver_feedback_str=driver_feedback_str,
                                    prev_ai_str=prev_ai_str,
                                    per_lap_telemetry=per_lap_telemetry or [],
                                    corner_issues_summary=corner_issues_summary,
                                    track_context=_track_ctx)
    _warnings: list = []
    if not params.track:
        _warnings.append("Track missing — recommendation may be inaccurate")
    if not params.track_location_id or not params.layout_id:
        _warnings.append("Track Intelligence unavailable — no track_location_id/layout_id set")
    _laps = sum(len(v) for v in lap_data_by_compound.values())
    if _laps < 3:
        _warnings.append(f"Only {_laps} valid laps recorded — confidence reduced")
    _payload = {
        "track": params.track,
        "track_location_id": params.track_location_id or None,
        "layout_id": params.layout_id or None,
        "track_context_included": bool(params.track_location_id and params.layout_id),
        "car": car_name,
        "lap_count": _laps,
        "has_history": bool(history),
        "validation_warnings": _warnings,
    }
    _raw = call_api(prompt, api_key, max_tokens=8000, system=_JSON_SYSTEM,
                    feature="Practice Analysis", structured_payload=_payload,
                    model=model, car_id=car_id, track=params.track,
                    session_id=session_id)
    _result = _parse_practice_response(_raw)
    _result.raw_response = _raw
    return _result


def format_gearbox_for_prompt(ga: dict) -> str:
    """Convert a gearbox_analysis dict (from LapStats) into a prompt block for the AI.

    The AI uses this data to recommend gear ratio changes, final drive adjustments,
    and gearbox strategy specific to the track and session type.
    """
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
        # Diagnosis
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
                f"  [OK] No limiter contact on main straight -- gearing is adequate for this straight."
            )

    # Top speed analysis
    ts = ga.get("top_speed_kmh", 0)
    theo = ga.get("theoretical_max_kmh")
    pct  = ga.get("top_speed_reached_pct")
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
        for e in exits[:8]:  # show first 8 for prompt length management
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

    lines.append(
        "\nIMPORTANT: Base ALL gearbox recommendations on the telemetry evidence above. "
        "Do NOT suggest gearbox changes that contradict the telemetry (e.g. do not lengthen "
        "gears if no limiter was detected, do not shorten gears if top speed was already at 97%+)."
    )
    return "\n".join(lines)


def build_car_setup(
    car: str,
    track: str,
    session_type: str,
    race_laps: int,
    min_weight_kg: float,
    max_power_hp: float,
    api_key: str,
    bop_data: dict | None = None,
    actual_bhp: float = 0.0,
    num_gears: int = 0,
    drivetrain: str = "",
    has_aero: bool = False,     # deprecated — inert; aero always applies
    car_specs: dict | None = None,
    allowed_tuning: list[str] | None = None,
    tuning_locked: bool = False,
    gearbox_analysis: dict | None = None,
    tyre_wear_multiplier: float = 1.0,
    fuel_multiplier: float = 1.0,
    avail_tyres: list[str] | None = None,
    req_tyres: list[str] | None = None,
    race_type: str = "lap",
    model: str | None = None,
    car_id: int = 0,
    track_location_id: str = "",
    layout_id: str = "",
    session_id: int = 0,
    setup_history: str = "",
    setup_comparison: str = "",
    duration_mins: int = 0,
    mandatory_stops: int = 0,
    refuel_rate_lps: float = 0.0,
    pit_loss_secs: float = 0.0,
    race_engineer_brief: str = "",
) -> CarSetupRecommendation:
    """Ask Claude to generate a complete from-scratch car setup."""
    # Resolve per-car parameter ranges near the top so both prompt builder and
    # parser share the same ranges object.
    _car_ranges = resolve_ranges(car)

    # Source pit_loss_secs from track library defaults if caller supplies 0.
    # The per-track default is expected to live in the track library seed data
    # (e.g. a "pit_loss_secs" field on the track or layout manifest).
    # Currently no track library entry carries this field, so this always falls
    # back to 0.0 — which means the hybrid_block omits the pit-loss line.
    # When the track library adds per-track pit_loss_secs in future, this will
    # pick it up automatically.
    _pit_loss = pit_loss_secs
    if not _pit_loss and track_location_id:
        try:
            from data.track_library import load_track_metadata as _load_tm
            _tm = _load_tm(track_location_id)
            if _tm is not None:
                # TrackMetadata is a dataclass; use getattr with a default
                _pit_loss = float(getattr(_tm, "pit_loss_secs", 0.0) or 0.0)
        except Exception:
            pass

    from strategy.track_context_prompt import get_track_context_for_ai as _get_tc
    _track_ctx = _get_tc(track_location_id, layout_id, car_name=car)
    prompt = _build_setup_from_scratch_prompt(
        car, track, session_type, race_laps, min_weight_kg, max_power_hp,
        bop_data=bop_data, actual_bhp=actual_bhp, num_gears=num_gears,
        drivetrain=drivetrain, has_aero=has_aero, car_specs=car_specs or {},
        allowed_tuning=allowed_tuning, tuning_locked=tuning_locked,
        gearbox_analysis=gearbox_analysis,
        tyre_wear_multiplier=tyre_wear_multiplier, fuel_multiplier=fuel_multiplier,
        avail_tyres=avail_tyres, req_tyres=req_tyres, race_type=race_type,
        track_context=_track_ctx,
        setup_history=setup_history, setup_comparison=setup_comparison,
        ranges=_car_ranges,
        duration_mins=duration_mins,
        mandatory_stops=mandatory_stops,
        refuel_rate_lps=refuel_rate_lps,
        pit_loss_secs=_pit_loss,
        race_engineer_brief=race_engineer_brief,
    )
    _raw_setup = call_api(prompt, api_key, max_tokens=2500, system=_JSON_SYSTEM,
                          feature="Build Car Setup",
                          structured_payload={"car": car, "track": track,
                                              "track_location_id": track_location_id or None,
                                              "layout_id": layout_id or None,
                                              "track_context_included": bool(track_location_id and layout_id),
                                              "session_type": session_type,
                                              "race_laps": race_laps,
                                              "has_bop": bop_data is not None},
                          model=model, car_id=car_id, track=track,
                          session_id=session_id)
    _setup_result = _parse_setup_recommendation(_raw_setup, ranges=_car_ranges)
    _setup_result.raw_response = _raw_setup
    return _setup_result


def analyse_tyre_degradation(
    lap_sequences: dict[str, list[float]],
    wear_multiplier: float,
    api_key: str,
    model: str | None = None,
) -> dict:
    """Ask Claude to identify the performance cliff for each compound."""
    prompt = _build_degradation_prompt(lap_sequences, wear_multiplier)
    lap_counts = {c: len(s) for c, s in lap_sequences.items()}
    return _parse_degradation_response(
        call_api(prompt, api_key, max_tokens=1500, system=_JSON_SYSTEM,
                 feature="Tyre Degradation",
                 structured_payload={"wear_multiplier": wear_multiplier,
                                     "compounds": list(lap_sequences.keys()),
                                     "lap_counts_by_compound": lap_counts},
                 model=model),
        lap_counts=lap_counts,
    )


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _compound_stats_lines(lap_data: dict[str, list[float]]) -> str:
    lines: list[str] = []
    for compound, times in sorted(lap_data.items()):
        if not times:
            continue
        avg  = mean(times)
        best = min(times)
        sd   = stdev(times) if len(times) > 1 else 0.0
        lines.append(
            f"  {compound}: {len(times)} laps — "
            f"avg {avg / 1000:.3f}s, best {best / 1000:.3f}s, "
            f"std-dev {sd / 1000:.3f}s"
        )
    return "\n".join(lines) if lines else "  (no lap data provided)"


def _race_rules_block(params: RaceParams) -> str:
    """Return a mandatory race-rules paragraph, or empty string if no rules apply."""
    lines: list[str] = []
    if params.min_mandatory_stops > 0:
        lines.append(
            f"- Minimum pit stops required by race rules: **{params.min_mandatory_stops}**. "
            "Any strategy with fewer stops is invalid and must not be proposed."
        )
    if params.mandatory_compounds:
        cpd = ", ".join(params.mandatory_compounds)
        lines.append(
            f"- Mandatory tyre compounds: **{cpd}**. "
            "Each listed compound must appear as at least one stint in the strategy."
        )
    if not lines:
        return ""
    return (
        "## Mandatory race rules (MUST be respected in every strategy option)\n"
        + "\n".join(lines)
    )


def _wear_note(params: RaceParams) -> str:
    if params.tyre_wear_multiplier == 1.0:
        return "Tyre wear rate is the same as in practice."
    extra_pct = (params.tyre_wear_multiplier - 1.0) * 100.0
    return (f"Race tyre wear is {params.tyre_wear_multiplier:.1f}× faster than practice "
            f"(+{extra_pct:.0f}%).")


def _build_fuel_trend_block(fuel_sequence: list) -> str:
    """Format a per-lap fuel trend section for the strategy prompt (Phase 2-B)."""
    if not fuel_sequence:
        return ""
    from statistics import mean as _mean, stdev as _stdev, quantiles as _quantiles
    avg = _mean(fuel_sequence)
    sd  = _stdev(fuel_sequence) if len(fuel_sequence) > 1 else 0.0
    try:
        p95 = _quantiles(fuel_sequence, n=20)[18] if len(fuel_sequence) >= 5 else max(fuel_sequence)
    except Exception:
        p95 = max(fuel_sequence)
    laps_str = ", ".join(f"{v:.2f}" for v in fuel_sequence)
    return (
        f"\n## Fuel Trend (last {len(fuel_sequence)} laps) [measured]\n"
        f"Per-lap: {laps_str}\n"
        f"Average: {avg:.2f} L/lap [measured], Std-dev: {sd:.2f} L/lap [calculated]\n"
        f"Worst case (95th pct): {p95:.2f} L/lap\n"
    )


def _build_compound_sequence_block(compound_sequences: dict) -> str:
    """Format per-compound lap-time sequences for the strategy prompt (Phase 2-C)."""
    if not compound_sequences:
        return ""
    from statistics import mean as _mean
    lines = ["\n## Compound Degradation Sequences [measured/calculated]"]
    for compound, times_ms in sorted(compound_sequences.items()):
        if not times_ms:
            continue
        times_s = [t / 1000.0 for t in times_ms]
        seq_str = " → ".join(f"{t:.3f}s" for t in times_s[:20])
        trend = ""
        if len(times_s) >= 4:
            try:
                n = len(times_s)
                y_mean = _mean(times_s)
                x_mean = (n - 1) / 2.0
                denom = sum((i - x_mean) ** 2 for i in range(n))
                slope = (
                    sum((i - x_mean) * (times_s[i] - y_mean) for i in range(n)) / denom
                    if denom else 0.0
                )
                sign = "+" if slope >= 0 else ""
                trend = f"  Deg rate: {sign}{slope:.3f}s/lap [calculated — linear regression]"
            except Exception:
                pass
        lines.append(f"{compound} ({len(times_ms)} laps):")
        lines.append(f"  {seq_str}")
        if trend:
            lines.append(trend)
    return "\n".join(lines) + "\n"


def _build_race_prompt(
    params: RaceParams,
    lap_data: dict[str, list[float]],
    degradation: Optional[dict] = None,
    setup_history: str = "",
    car_name: str = "",
    car_specs: dict | None = None,
    setup_comparison: str = "",
    fuel_sequence: list | None = None,
    compound_sequences: dict | None = None,
    corner_issues_summary: str = "",
    track_context: str = "",
) -> str:
    car_specs = car_specs or {}
    gt7_ref = load_gt7_reference()

    if degradation:
        deg_lines = []
        for compound, d in sorted(degradation.items()):
            deg_lines.append(
                f"  {compound}: optimal {d.get('optimal_stint_race', '?')} race laps, "
                f"total life {d.get('total_life_race', '?')} race laps, "
                f"pace loss {d.get('pace_loss_at_cliff_s', '?'):.1f}s/lap after "
                f"practice lap {d.get('cliff_lap_practice', '?')} "
                f"(confidence: {d.get('confidence', 'low')})"
            )
        degradation_block = (
            "## Tyre degradation from practice data\n"
            + "\n".join(deg_lines)
            + "\nUse these values for stint length calculation. Ignore generic GT7 compound estimates."
        )
    else:
        degradation_block = (
            "## Tyre degradation estimates (no practice data)\n"
            "GT7 compound estimates: RS ~10–16 race laps, RM ~18–25 race laps, RH ~28–40 race laps.\n"
            "Assume pace drops linearly so that by the tyre life lap the compound is 2.0s slower than reference.\n"
            f"Tyre life in race laps = practice_laps_before_deg / {params.tyre_wear_multiplier:.1f} (wear multiplier)."
        )

    rules_block = _race_rules_block(params)
    mandatory_instruction = ""
    if params.min_mandatory_stops > 0:
        mandatory_instruction += (
            f"\n0. MANDATORY: all 3 strategies must include at least "
            f"{params.min_mandatory_stops} pit stop(s) — this is a race rule."
        )
    if params.mandatory_compounds:
        cpd = ", ".join(params.mandatory_compounds)
        mandatory_instruction += (
            f"\n0b. MANDATORY: each strategy must use every compound in [{cpd}] "
            "as at least one stint."
        )

    if params.race_type == "timed":
        race_len_line = f"Race duration: {params.duration_mins} minutes (Timed Race)"
    else:
        race_len_line = f"Race length: {params.total_laps} laps"

    if params.tuning_locked:
        tuning_block = (
            "\n## EVENT RULES — TUNING LOCKED\n"
            "This event does not permit setup tuning. The player cannot modify any setup parameters.\n"
            "DO NOT recommend any setup changes. Provide driving advice and tyre strategy only.\n\n"
        )
    elif params.allowed_tuning:
        _locked_cats = [c for c in _ALL_TUNING_CATS if c not in params.allowed_tuning]
        tuning_block = (
            f"\n## EVENT TUNING RESTRICTIONS\n"
            f"Allowed to modify: {', '.join(params.allowed_tuning)}\n"
            f"LOCKED (do not recommend changes): {', '.join(_locked_cats)}\n"
            f"Only provide setup advice for the ALLOWED categories. "
            f"Do not suggest changes to locked areas.\n\n"
        )
    else:
        tuning_block = ""

    bop_line = (
        "\n- BoP: ON — car weight and power are regulation-fixed"
        if getattr(params, "bop", False) else ""
    )

    avail_line = ""
    if getattr(params, "avail_tyres", []):
        try:
            from data.tyres import get_by_code as _gbc
            _names = [_gbc(c).name for c in params.avail_tyres if _gbc(c)]
        except Exception:
            _names = list(params.avail_tyres)
        if _names:
            avail_line = f"\n- Available compounds: {', '.join(_names)}"

    # Build compact car line for the prompt
    car_line_parts = [car_name] if car_name else []
    if car_specs.get("category"):    car_line_parts.append(car_specs["category"])
    if car_specs.get("pp_rating"):   car_line_parts.append(f"PP {car_specs['pp_rating']:.0f}")
    if car_specs.get("drivetrain"):  car_line_parts.append(car_specs["drivetrain"])
    if car_specs.get("aspiration"):  car_line_parts.append(car_specs["aspiration"])
    if car_specs.get("power_hp"):    car_line_parts.append(f"{car_specs['power_hp']} hp")
    if car_specs.get("weight_kg"):   car_line_parts.append(f"{car_specs['weight_kg']} kg")
    car_line = " | ".join(car_line_parts) if car_line_parts else ""

    _fuel_trend_block = _build_fuel_trend_block(fuel_sequence or [])
    _compound_seq_block = _build_compound_sequence_block(compound_sequences or {})
    _corner_issues_section = (
        f"\n{corner_issues_summary}\n" if corner_issues_summary.strip() else ""
    )

    return f"""You are an expert Gran Turismo 7 race strategist with deep knowledge of the game's physics and mechanics.

## GT7 Knowledge Base
{gt7_ref}

---

Analyse the race below and produce exactly 3 strategy options ranked by estimated total race time (fastest first).

## Race parameters
{f"- Car: {car_line}" + chr(10) if car_line else ""}- {build_track_context(params.track)}
- {race_len_line}
- Fuel burn: {params.fuel_burn_per_lap:.2f} L/lap
- Refuel speed: {params.refuel_speed_lps:.1f} L/s
- Pit lane time loss (fixed per stop): {params.pit_loss_secs:.1f} s
- {_wear_note(params)}{bop_line}{avail_line}

{(track_context + chr(10) + chr(10)) if track_context else ""}## Practice lap times by compound
{_compound_stats_lines(lap_data)}
{_compound_seq_block}
{degradation_block}
{_fuel_trend_block}{_corner_issues_section}
{(chr(10) + rules_block) if rules_block else ""}{tuning_block}
{(chr(10) + setup_history) if setup_history else ""}{(chr(10) + setup_comparison) if setup_comparison else ""}
{_DATA_QUALITY_NOTE}

## Instructions{mandatory_instruction}
1. Consider 1-stop, 2-stop, and no-stop options (only include no-stop if compound endurance allows and no mandatory stop rule exists).
2. Use the tyre degradation section above for stint lengths — do not exceed the optimal stint.
3. Pit stop time = ceil(fuel_for_next_stint / refuel_speed) + pit_loss_secs.
4. Total time = Σ (laps × pace) + Σ pit_stop_times, accounting for degraded pace in later laps of each stint.
5. Set pace_threshold_ms = 2000 for Soft, 2500 for Medium, 3000 for Hard/Racing Hard.
6. Set ref_lap_ms to the recorded average for that compound.

## Output
Name the three strategies exactly:
- Rank 1: "Safe" (prioritise finishing, minimum risk — conservative compound choice, extra fuel margin)
- Rank 2: "Balanced" (best estimated time with moderate risk)
- Rank 3: "Aggressive" (maximum pace, highest risk — fewest stops, softest compounds)

Reply ONLY with a valid JSON object — no markdown, no extra text:

{{
  "strategies": [
    {{
      "rank": 1,
      "name": "Safe",
      "stints": [
        {{"compound": "Soft", "laps": 14, "ref_lap_ms": 95200, "pace_threshold_ms": 2000}},
        {{"compound": "Hard", "laps": 11, "ref_lap_ms": 97400, "pace_threshold_ms": 3000}}
      ],
      "estimated_time_s": 2401.5,
      "pit_time_s": 22.8,
      "summary": "Safest route to the finish. Conservative compound choice minimises risk.",
      "risks": "Slightly slower overall — but high chance of finishing.",
      "positives": "Low risk of tyre failure or fuel issues.",
      "negatives": "Sacrifices pace in exchange for reliability."
    }}
  ]
}}"""


# Maps Event Planner tuning category codes → setup dict keys used in prompts.
_TUNING_CATEGORY_KEYS: dict[str, list[str]] = {
    "brake_balance": ["brake_bias"],
    "suspension":    ["ride_height_front", "ride_height_rear", "springs_front", "springs_rear",
                      "dampers_front_comp", "dampers_front_ext", "dampers_rear_comp", "dampers_rear_ext",
                      "arb_front", "arb_rear", "camber_front", "camber_rear", "toe_front", "toe_rear"],
    "differential":  ["lsd_initial", "lsd_accel", "lsd_decel",
                      "lsd_front_initial", "lsd_front_accel", "lsd_front_decel"],
    "aero":          ["aero_front", "aero_rear"],
    "transmission":  ["final_drive", "gear_ratios", "transmission_max_speed_kmh"],
    "power":         ["power_restrictor"],
    "ballast":       ["ballast_kg", "ballast_position"],
}

_ALL_TUNING_CATS: list[str] = list(_TUNING_CATEGORY_KEYS.keys())


def _build_per_lap_telemetry_block(rows: list) -> str:
    """Format the per-lap telemetry table for the practice prompt (Phase 2-A)."""
    if not rows:
        return ""
    from data.session_db import ms_to_str as _ms_to_str
    has_temps = any(r.get("tyre_temp_fl_avg", 0) > 0 for r in rows)
    hdr = "Lap | Time    | Fuel  | Lock | Spin | Over(T) | Kerb | Lat-G*"
    if has_temps:
        hdr += " |  FL   FR   RL   RR"
    lines = [
        "\n## Per-Lap Telemetry (last clean laps) [calculated/measured/estimated*]",
        hdr,
        "-" * len(hdr),
    ]
    for r in rows:
        ovr = r.get("oversteer_count", 0)
        ovr_t = r.get("oversteer_throttle_on", 0)
        ovr_str = f"{ovr}({ovr_t}T)" if ovr_t else str(ovr)
        lat_g = r.get("max_lat_g", 0.0)
        row = (
            f"{r['lap_num']:3d} | {_ms_to_str(r['lap_time_ms']):7s} "
            f"| {r.get('fuel_used', 0.0):4.2f}L "
            f"| {r.get('lock_up_count', 0):4d} "
            f"| {r.get('wheelspin_count', 0):4d} "
            f"| {ovr_str:>7s}  "
            f"| {r.get('kerb_count', 0):4d} "
            f"| {lat_g:5.2f}*"
        )
        if has_temps:
            fl = r.get("tyre_temp_fl_avg", 0.0)
            fr = r.get("tyre_temp_fr_avg", 0.0)
            rl = r.get("tyre_temp_rl_avg", 0.0)
            rr = r.get("tyre_temp_rr_avg", 0.0)
            if fl > 0:
                row += f" | {fl:4.0f}° {fr:4.0f}° {rl:4.0f}° {rr:4.0f}°"
            else:
                row += " | — — — —"
        lines.append(row)
    lines.append(
        "(T) = throttle-on oversteer   * = estimated (angvel_z × speed / 9.81)"
        "\nOutlap and pit lap excluded."
    )
    return "\n".join(lines) + "\n"


def _build_practice_prompt(
    params: RaceParams,
    lap_data: dict[str, list[float]],
    setup: dict,
    history: dict,
    car_name: str = "",
    car_specs: dict | None = None,
    setup_comparison: str = "",
    driver_feedback_str: str = "",
    prev_ai_str: str = "",
    per_lap_telemetry: list | None = None,
    corner_issues_summary: str = "",
    track_context: str = "",
) -> str:
    car_specs = car_specs or {}
    gt7_ref = load_gt7_reference()

    if params.race_type == "timed":
        race_len_line = f"Race duration: {params.duration_mins} minutes (Timed Race)"
    else:
        race_len_line = f"Race length: {params.total_laps} laps"

    # Build tuning constraint block and filter setup according to event permissions
    if params.tuning_locked:
        constraint_block = (
            "\n## EVENT RULES — TUNING LOCKED\n"
            "DO NOT recommend any setup changes. Provide driving advice and tyre strategy only.\n"
        )
        setup_block = "  [TUNING LOCKED — setup changes not permitted for this Event]"
    elif params.allowed_tuning:
        locked_cats = [c for c in _ALL_TUNING_CATS if c not in params.allowed_tuning]
        constraint_block = (
            f"\n## EVENT TUNING RESTRICTIONS\n"
            f"Allowed: {', '.join(params.allowed_tuning)}\n"
            f"Locked (do NOT recommend changes): {', '.join(locked_cats)}\n"
        )
        _allowed_keys: set[str] = {"name", "track", "condition", "setup_type", "notes"}
        for _cat in params.allowed_tuning:
            _allowed_keys.update(_TUNING_CATEGORY_KEYS.get(_cat, []))
        setup_block = format_setup_for_prompt({k: v for k, v in setup.items() if k in _allowed_keys})
    else:
        constraint_block = ""
        setup_block = format_setup_for_prompt(setup)

    # Format historical context
    if history and history.get("total_laps", 0) > 0:
        from data.session_db import ms_to_str
        compound_parts = [f"{c}: {ms_to_str(ms)}"
                          for c, ms in sorted(history.get("compound_refs", {}).items())]
        history_block = "\n".join([
            f"  {history['total_laps']} laps across {history.get('sessions_count', 1)} session(s)",
            f"  Best lap: {ms_to_str(history.get('best_lap_ms', 0))}",
            f"  Average lap: {ms_to_str(history.get('avg_lap_ms', 0))}",
            f"  Avg fuel/lap: {history.get('avg_fuel', 0.0):.2f} L",
            f"  Avg lock-ups/lap: {history.get('avg_lockups', 0.0):.1f}",
            f"  Avg wheelspin events/lap: {history.get('avg_wheelspin', 0.0):.1f}",
            f"  Compound references: {', '.join(compound_parts) if compound_parts else 'N/A'}",
        ])
    else:
        history_block = "  (No prior session data for this car and track)"

    rules_block = _race_rules_block(params)

    bop_line = ""
    if getattr(params, "bop", False):
        bop_line = "\n- BoP: ON — car weight and power are regulation-fixed\n"

    avail_line = ""
    if getattr(params, "avail_tyres", []):
        try:
            from data.tyres import get_by_code as _gbc
            _names = [_gbc(c).name for c in params.avail_tyres if _gbc(c)]
        except Exception:
            _names = list(params.avail_tyres)
        if _names:
            avail_line = f"\n- Available compounds: {', '.join(_names)}\n"

    feedback_section = (
        f"\n## Recent Driver Feedback\n{driver_feedback_str}\n"
        if driver_feedback_str.strip() else ""
    )
    prev_ai_section = (
        f"\n## Previous AI Recommendations (Practice Analysis)\n{prev_ai_str}\n"
        if prev_ai_str.strip() else ""
    )
    per_lap_section = _build_per_lap_telemetry_block(per_lap_telemetry or [])
    corner_issues_section = (
        f"\n{corner_issues_summary}\n" if corner_issues_summary.strip() else ""
    )

    # Build compact car line for the prompt
    car_line_parts = [car_name] if car_name else []
    if car_specs.get("category"):    car_line_parts.append(car_specs["category"])
    if car_specs.get("pp_rating"):   car_line_parts.append(f"PP {car_specs['pp_rating']:.0f}")
    if car_specs.get("drivetrain"):  car_line_parts.append(car_specs["drivetrain"])
    if car_specs.get("aspiration"):  car_line_parts.append(car_specs["aspiration"])
    if car_specs.get("power_hp"):    car_line_parts.append(f"{car_specs['power_hp']} hp")
    if car_specs.get("weight_kg"):   car_line_parts.append(f"{car_specs['weight_kg']} kg")
    car_line = " | ".join(car_line_parts) if car_line_parts else ""

    return f"""You are an expert Gran Turismo 7 race engineer and car setup specialist.

## GT7 Knowledge Base (includes driver's personal tuning profile)
{gt7_ref}

---

Analyse the practice session below and provide:
1. Three ranked race strategy options
2. Specific car setup changes tailored to the driver's style
3. A concrete aero/fuel trade-off analysis for this specific race
4. Recommendations for further practice to develop the optimal strategy

## Race parameters
{f"- Car: {car_line}" + chr(10) if car_line else ""}- {build_track_context(params.track)}
- {race_len_line}
- Fuel burn: {params.fuel_burn_per_lap:.2f} L/lap
- Refuel speed: {params.refuel_speed_lps:.1f} L/s
- Pit loss: {params.pit_loss_secs:.1f} s
- {_wear_note(params)}{bop_line}{avail_line}
{(chr(10) + rules_block) if rules_block else ""}{constraint_block}
{(track_context + chr(10) + chr(10)) if track_context else ""}## Practice lap times by compound
{_compound_stats_lines(lap_data)}
{per_lap_section}{corner_issues_section}
## Current car setup
{setup_block}

## Historical data for this car and track
{history_block}
{(setup_comparison + chr(10)) if setup_comparison else ""}{feedback_section}{prev_ai_section}
{_DATA_QUALITY_NOTE}

{_RACE_ENGINEERING_CONTEXT}
## Instructions

**Strategies**: 3 ranked options using the race time model above. Show the break-even lap advantage required for each added stop. {"All strategies must comply with the mandatory race rules above." if rules_block else ""}

**Fuel saving analysis** (output as `fuel_saving_analysis`): Calculate the required saving for this specific race (fuel_burn_per_lap − available_per_lap). Rank the applicable methods by efficiency. State which combination is needed and the lap-time cost. Be specific to the numbers above.

**Tyre management** (output as `tyre_management`): Use the lockup and wheelspin rates from the historical data to identify the limiting axle. State which axle will degrade first and why. Give 2–3 driving technique adjustments (braking point, throttle application, shift timing) to protect it.

{"**Setup changes** (`setup_changes`): 3–5 changes following the endurance priority order — tyre protection first, fuel efficiency second, pace last. Use the driver's vocabulary and reference exact current values where known." if not params.tuning_locked else "**No setup changes** (`setup_changes`): Tuning is locked for this Event — do NOT recommend any setup changes. Leave this section empty or state that tuning is not permitted."}

**Aero/fuel trade-off** (`aero_fuel_analysis`): Calculate specifically whether reducing rear aero by 100 units (approx 0.1 L/lap fuel saving, ~0.2s/lap pace cost) would save enough fuel to eliminate a pit stop or reduce refuel time. Use the actual race parameters. Show the maths. Conclude with a firm recommendation.

**Further practice** (`further_practice`): 4–6 structured tests from the testing programme above. Specify laps, compound, and exactly what to record on each run.

## Output format
Name the three strategies exactly:
- Rank 1: "Safe" (prioritise finishing, minimum risk)
- Rank 2: "Balanced" (best estimated time with moderate risk)
- Rank 3: "Aggressive" (maximum pace, highest risk)

Reply ONLY with valid JSON — no markdown fences, no extra text:

{{
  "strategies": [
    {{
      "rank": 1,
      "name": "Safe",
      "stints": [{{"compound": "...", "laps": 0, "ref_lap_ms": 0, "pace_threshold_ms": 2000}}],
      "estimated_time_s": 0.0,
      "pit_time_s": 0.0,
      "summary": "...",
      "risks": "...",
      "positives": "...",
      "negatives": "..."
    }}
  ],
  "setup_changes": [
    "Change X from Y to Z. Why: ..."
  ],
  "further_practice": [
    "Run N laps on [compound] to test [specific thing] — record [what to note]"
  ],
  "aero_fuel_analysis": "At current rear aero of [value]...",
  "fuel_saving_analysis": "Required saving is X L/lap. Short shifting costs ~0.1s/lap and saves ~0.1 L/lap...",
  "tyre_management": "Lockup rate of X/lap indicates front braking load is excessive..."
}}"""


_ALL_TUNING_CATS = [
    "tyres", "brake_balance", "suspension", "differential",
    "aero", "transmission", "power", "ballast", "steering", "nitrous",
]

# Keywords per tuning category used to detect violations in AI responses.
_LOCKED_CAT_KEYWORDS: dict[str, list[str]] = {
    "brake_balance": ["brake bias", "brake balance"],
    "suspension":    ["ride height", "spring rate", "spring stiffness", "springs", "damper",
                      "anti-roll", "camber", "toe-in", "toe-out", "toe setting", "arb"],
    "differential":  ["lsd", "differential", "limited slip"],
    "aero":          ["downforce", "front wing", "rear wing", "front aero", "rear aero",
                      "aero balance"],
    "transmission":  ["gear ratio", "final drive", "gearbox"],
    "power":         ["ecu output", "power restrictor", "power restriction"],
    "ballast":       ["ballast"],
    "nitrous":       ["nitrous"],
}

_SETUP_ACTION_VERBS: list[str] = [
    "increase", "decrease", "raise", "lower", "soften", "stiffen",
    "adjust", "try", "set to", "change", "modify", "reduce", "add",
    "recommend", "suggest", "consider",
]


def validate_ai_setup_response(
    response: str,
    tuning_locked: bool,
    allowed_tuning: list[str] | None,
) -> list[str]:
    """Return violated category codes when AI recommends changes to locked tuning areas.

    Detects a violation when a locked-category keyword appears within 200 characters
    of a setup-change action verb, indicating a setup change recommendation.
    Returns [] when no tuning restrictions are active or no violations are found.
    """
    if not tuning_locked and not allowed_tuning:
        return []

    text = response.lower()

    if tuning_locked:
        locked_cats = list(_LOCKED_CAT_KEYWORDS.keys())
    else:
        locked_cats = [c for c in _LOCKED_CAT_KEYWORDS if c not in (allowed_tuning or [])]

    violated: list[str] = []
    for cat in locked_cats:
        cat_violated = False
        for kw in _LOCKED_CAT_KEYWORDS.get(cat, []):
            pos = text.find(kw)
            while pos != -1 and not cat_violated:
                window = text[max(0, pos - 200): pos + len(kw) + 200]
                if any(v in window for v in _SETUP_ACTION_VERBS):
                    violated.append(cat)
                    cat_violated = True
                pos = text.find(kw, pos + 1)
    return violated


def _build_setup_from_scratch_prompt(
    car: str,
    track: str,
    session_type: str,
    race_laps: int,
    min_weight_kg: float,
    max_power_hp: float,
    bop_data: dict | None = None,
    actual_bhp: float = 0.0,
    num_gears: int = 0,
    drivetrain: str = "",
    has_aero: bool = False,     # deprecated — inert; aero always applies
    car_specs: dict | None = None,
    allowed_tuning: list[str] | None = None,
    tuning_locked: bool = False,
    gearbox_analysis: dict | None = None,
    tyre_wear_multiplier: float = 1.0,
    fuel_multiplier: float = 1.0,
    avail_tyres: list[str] | None = None,
    req_tyres: list[str] | None = None,
    race_type: str = "lap",
    track_context: str = "",
    setup_history: str = "",
    setup_comparison: str = "",
    ranges: dict | None = None,
    duration_mins: int = 0,
    mandatory_stops: int = 0,
    refuel_rate_lps: float = 0.0,
    pit_loss_secs: float = 0.0,
    race_engineer_brief: str = "",
) -> str:
    car_specs = car_specs or {}
    gt7_ref = load_gt7_reference()
    # Resolve per-car ranges (falls back to generic defaults if car unknown)
    _ranges = ranges if ranges is not None else resolve_ranges(car)
    _is_quali = "qualifying" in session_type.lower()
    if _is_quali:
        session_desc = "1 qualifying lap (maximise single-lap peak pace, tyre warm-up, maximum rotation, no tyre wear concern)"
    elif race_type == "timed":
        session_desc = (
            "timed race (optimise for lowest total race time: minimise tyre degradation, "
            "fuel consumption, cumulative pit stop time, and time lost to traffic and dirty air; "
            "maintain consistency; allow sacrificing small qualifying pace for a faster overall race)"
        )
    else:
        session_desc = (
            f"{race_laps}-lap race (optimise for lowest total race time: minimise tyre degradation, "
            "fuel consumption, cumulative pit stop time, and time lost to traffic and dirty air; "
            "maintain consistency; allow sacrificing small qualifying pace for a faster overall race)"
        )

    # Race context block for the AI prompt
    _race_ctx_lines: list[str] = []
    if tyre_wear_multiplier != 1.0:
        _race_ctx_lines.append(f"  Tyre wear multiplier: {tyre_wear_multiplier:.1f}x "
                               f"(race wears tyres {tyre_wear_multiplier:.1f}x faster than practice)")
    if fuel_multiplier != 1.0:
        _race_ctx_lines.append(f"  Fuel multiplier: {fuel_multiplier:.1f}x")
    if avail_tyres:
        try:
            from data.tyres import get_by_code as _gbc
            _av_names = [_gbc(c).name for c in avail_tyres if _gbc(c)]
        except Exception:
            _av_names = list(avail_tyres)
        if _av_names:
            _race_ctx_lines.append(f"  Available compounds: {', '.join(_av_names)}")
    if req_tyres:
        try:
            from data.tyres import get_by_code as _gbc
            _rq_names = [_gbc(c).name for c in req_tyres if _gbc(c)]
        except Exception:
            _rq_names = list(req_tyres)
        if _rq_names:
            _race_ctx_lines.append(f"  Required compounds (at least one stint each): {', '.join(_rq_names)}")
    _race_ctx_block = (
        "\n## Race Conditions\n" + "\n".join(_race_ctx_lines) + "\n"
    ) if _race_ctx_lines else ""

    # --- Section D: hybrid race-context inputs ---
    _hybrid_lines: list[str] = []
    if duration_mins:
        _hybrid_lines.append(f"  Race duration: {duration_mins} min")
    if mandatory_stops:
        _hybrid_lines.append(f"  Mandatory pit stops: {mandatory_stops}")
    if refuel_rate_lps:
        _hybrid_lines.append(f"  Refuel rate: {refuel_rate_lps:.1f} L/s")
    if pit_loss_secs:
        _hybrid_lines.append(f"  Pit lane time loss: {pit_loss_secs:.1f} s")
    _hybrid_block = (
        "\n## Race Strategy Context\n" + "\n".join(_hybrid_lines) + "\n"
    ) if _hybrid_lines else ""

    # Race engineer brief — injected verbatim before the JSON template
    _brief_stripped = race_engineer_brief.strip() if race_engineer_brief else ""

    if bop_data:
        weight_line = (f"  BOP minimum weight: {bop_data.get('weight_kg', '?')} kg "
                       f"(set by regulations — ballast_kg should reach this if needed)")
        if "power_pct" in bop_data:
            power_line = (f"  BOP power level: {bop_data['power_pct']}% of car maximum "
                          f"(fixed by regulations — set power_restrictor to {bop_data['power_pct']})")
        elif "power_hp" in bop_data:
            power_line = (f"  BOP power level: {bop_data['power_hp']} hp "
                          f"(fixed by regulations — power is locked, leave power_restrictor at 100)")
        else:
            power_line = ("  BOP power level: regulated "
                          "(fixed by regulations — power is locked, leave power_restrictor at 100)")
        bop_block   = (
            "\n⚠️  BOP RACE — the gearbox is LOCKED by the game. "
            "Do NOT recommend gear_ratios or final_drive. "
            "Set gear_ratios to [] and final_drive to 0.0 in your JSON. "
            "Focus entirely on: ride height, springs, dampers, ARB, camber, toe, aero, LSD, brake bias."
        )
    else:
        weight_line = (f"  Minimum weight regulation: {min_weight_kg} kg"
                       if min_weight_kg > 0 else
                       "  Minimum weight regulation: none (use car's base weight — set ballast_kg to 0)")
        power_line  = (f"  Maximum power regulation: {max_power_hp} hp"
                       if max_power_hp > 0 else
                       "  Maximum power regulation: none (full power — set power_restrictor to 100)")
        bop_block   = ""

    # Car specifications block — tells the AI exact hardware fitted to the car
    gear_count_note = (
        f"IMPORTANT: This car has {num_gears} gears. Return exactly {num_gears} values in gear_ratios."
        if num_gears > 0 else
        "Use the car's known gear count for gear_ratios."
    )
    drivetrain_note = drivetrain if drivetrain else "Use car's known drivetrain layout (FR/FF/MR/RR/AWD)."
    if actual_bhp > 0 and max_power_hp > 0:
        power_installed = (
            f"INSTALLED ENGINE POWER (after all performance upgrades): {actual_bhp:.0f} hp\n"
            f"  The power target is {max_power_hp:.0f} hp. Calculate ECU stage and Power Restrictor\n"
            f"  percentage FROM the installed {actual_bhp:.0f} hp figure — NOT from stock power."
        )
    elif actual_bhp > 0:
        power_installed = f"Installed engine power (after all upgrades): {actual_bhp:.0f} hp (no regulation cap)."
    else:
        power_installed = "Installed engine power: not specified — use car's known tuned output."

    # Aero always applies — every car has aero range 0–max in this system.
    # The has_aero parameter is retained in the signature for UI compatibility
    # but no longer changes the aero instruction.
    aero_note = (
        "Return appropriate aero_front and aero_rear downforce values for this track "
        "(range 0–1000; set to 0 if this car has no adjustable aero parts)."
    )

    # Additional spec lines from car_specs.json (scraped from dg-edge.com)
    extra_spec_lines: list[str] = []
    if car_specs.get("pp_rating"):
        extra_spec_lines.append(f"PP rating: {car_specs['pp_rating']:.2f}")
    if car_specs.get("power_rpm"):
        extra_spec_lines.append(
            f"Peak power: {car_specs.get('power_hp', '?')} hp @ {car_specs['power_rpm']} rpm"
        )
    if car_specs.get("torque_kgfm"):
        torq_rpm = f" @ {car_specs['torque_rpm']} rpm" if car_specs.get("torque_rpm") else ""
        extra_spec_lines.append(f"Peak torque: {car_specs['torque_kgfm']} kgfm{torq_rpm}")
    if car_specs.get("weight_kg") and not bop_data:
        extra_spec_lines.append(f"Stock weight: {car_specs['weight_kg']} kg")
    if car_specs.get("aspiration"):
        extra_spec_lines.append(f"Aspiration: {car_specs['aspiration']}")
    if car_specs.get("displacement_cc"):
        extra_spec_lines.append(f"Displacement: {car_specs['displacement_cc']} cc")
    extra_specs_str = ("\n  " + "\n  ".join(extra_spec_lines)) if extra_spec_lines else ""

    car_specs_block = f"""
Car specifications (driver-confirmed — treat as ground truth):
  Drivetrain: {drivetrain_note}
  Gearbox: {gear_count_note}
  {power_installed}
  Aero: {aero_note}{extra_specs_str}
"""

    transmission_section = "" if bop_data else f"""
For transmission fields:
  - final_drive: the final drive ratio (typically 2.5–5.5 for road cars, 3.0–4.5 for race cars). Set 0.0 only if the car has no adjustable final drive.
  - transmission_max_speed_kmh: GT7 top-speed slider target in km/h — choose so the car reaches this at redline in top gear on the longest straight at this track.
  - gear_ratios: list of individual ratios as floats, one per gear. {gear_count_note}"""

    example_num = num_gears if num_gears > 0 else 6
    example_ratios = [3.20, 2.30, 1.75, 1.40, 1.15, 0.95, 0.80, 0.70][:example_num]
    gear_json = "" if bop_data else f"""
  "final_drive": 3.500,
  "transmission_max_speed_kmh": 270,
  "gear_ratios": {example_ratios},"""

    if tuning_locked:
        tuning_block = (
            "\n## EVENT RULES — TUNING LOCKED\n"
            "This event does not permit setup tuning. The player cannot modify any setup parameters.\n"
            "DO NOT recommend any setup changes. Provide driving advice and tyre strategy only.\n\n"
        )
    elif allowed_tuning:
        locked_cats = [c for c in _ALL_TUNING_CATS if c not in allowed_tuning]
        tuning_block = (
            f"\n## EVENT TUNING RESTRICTIONS\n"
            f"Allowed to modify: {', '.join(allowed_tuning)}\n"
            f"LOCKED (do not recommend changes): {', '.join(locked_cats)}\n"
            f"Only provide setup advice for the ALLOWED categories. "
            f"Do not suggest changes to locked areas.\n\n"
        )
    else:
        tuning_block = ""

    gearbox_block = format_gearbox_for_prompt(gearbox_analysis or {}) if not bop_data else ""

    _history_block = (
        f"\n## Previous Setup Recommendations for This Car and Track\n{setup_history}\n"
        if setup_history else ""
    )
    _comparison_block = (
        f"\n## Setup Performance Comparison (Lap Data)\n{setup_comparison}\n"
        if setup_comparison else ""
    )

    # Build the valid-ranges text block from resolved per-car ranges
    def _fmt_range(lo, hi):
        if isinstance(lo, float) or isinstance(hi, float):
            return f"{lo:.2f}–{hi:.2f}"
        return f"{lo}–{hi}"

    _r = _ranges
    _ranges_block = f"""GT7 valid ranges for every field (clamp your values to these — the game will reject anything outside):
  ride_height_front / ride_height_rear : {_fmt_range(*_r['ride_height_front'])} mm
  springs_front / springs_rear         : {_fmt_range(*_r['springs_front'])} Hz  ← GT7 uses NATURAL FREQUENCY in Hz, NOT N/mm or kg/mm
  dampers_front_comp / dampers_rear_comp : {_fmt_range(*_r['dampers_front_comp'])} %  ← Damping Ratio (Compression); this is a guideline only — not a constraint: typical starting point 30–40 %
  dampers_front_ext  / dampers_rear_ext  : {_fmt_range(*_r['dampers_front_ext'])} %  ← Damping Ratio (Expansion); this is a guideline only — not a constraint: typical starting point 35–50 %; extension must usually be ≥ compression
  arb_front / arb_rear                 : {_fmt_range(*_r['arb_front'])}
  camber_front / camber_rear           : {_fmt_range(*_r['camber_front'])} °  ← always negative in GT7 (0.00 = no camber)
  toe_front / toe_rear                 : {_fmt_range(*_r['toe_front'])} °  ← convention: negative front = toe-out, positive rear = toe-in
  aero_front / aero_rear               : {_fmt_range(*_r['aero_front'])} (downforce setting; use 0 for non-aero cars)
  lsd_initial / lsd_accel / lsd_decel  : {_fmt_range(*_r['lsd_initial'])}  ← Rear LSD
  lsd_front_initial / lsd_front_accel / lsd_front_decel : {_fmt_range(*_r['lsd_front_initial'])}  ← Front LSD (AWD only; set to 0 for non-AWD cars)
  brake_bias                           : {_fmt_range(*_r['brake_bias'])}  ← NEGATIVE = more FRONT braking, POSITIVE = more REAR braking
  ballast_kg                           : {_fmt_range(*_r['ballast_kg'])} kg
  ballast_position                     : {_fmt_range(*_r['ballast_position'])}  ← −50 = full rear, +50 = full front
  power_restrictor                     : {_fmt_range(*_r['power_restrictor'])} %
  shift_rpm                            : engine RPM to upshift for best lap time (typically just past peak power RPM;
                                         set to 0 only if car is electric or data is unavailable)"""

    return f"""You are an expert Gran Turismo 7 car setup engineer who knows the game's physics in detail.

## GT7 Knowledge Base (includes this driver's personal tuning philosophy and preferences)
{gt7_ref}

---
{tuning_block}{gearbox_block}
Build a complete from-scratch car setup optimised for:
  Car: {car}
  {build_track_context(track)}
  Session: {session_desc}
{weight_line}
{power_line}{_race_ctx_block}{_hybrid_block}
{(track_context + chr(10) + chr(10)) if track_context else ""}{_history_block}{_comparison_block}{bop_block}{car_specs_block}
{_ranges_block}

GT7 has TWO power-limiting mechanisms — advise on both when max_power is specified:

  1. ECU / Computer (Tuning Shop purchase, installed before the race):
     GT7 sells Sports/Racing Computer upgrades in stages. Each changes the power BAND, not just the ceiling.

  2. Power Restrictor (Settings Sheet slider, 0–100 %):
     Fine-tunes output as a percentage of the installed ECU's max. Adjustable in the lobby.

When max_power is specified, calculate from the INSTALLED power figure above:
  - Reduction ≤15 % of installed: Power Restrictor only.
  - Reduction >15 % of installed: Recommend ECU stage first, then Power Restrictor for exact target.
  - No target: set power_restrictor to 100.

ecu_recommendation must be plain English, e.g.:
  "From the installed 1050 hp (Stage 3 Computer fitted), use Power Restrictor at 62 % to reach 650 hp."

For weight/power management:
  - ballast_kg: kg to ADD to reach minimum weight (0 if not regulated or already at/above min)
  - ballast_position: −50 = full rear, +50 = full front, 0 = neutral
  - power_restrictor: % of ECU max (100 = unrestricted)
{transmission_section}
Tailor every decision to the driver's known style from the knowledge base (braking stability first, rotation on entry, predictable rear).
{(chr(10) + "## Race Engineer Brief" + chr(10) + _brief_stripped + chr(10)) if _brief_stripped else ""}
Reply ONLY with a valid JSON object — no markdown fences, no extra text.
For the reasoning field, explain every significant change with these seven labelled sub-points
(use EXACT label strings, one set per changed parameter, separated by blank lines):
  "Expected lap-time effect": how this setting affects single-lap pace
  "Expected tyre-wear effect": impact on degradation over a stint
  "Expected fuel effect": influence on fuel consumption
  "Expected braking-stability effect": effect on entry and trail-braking behaviour
  "Confidence": how certain you are in this recommendation (high / medium / low) and why
  "Validation method": what the driver should test on circuit to confirm
  "Telemetry indicator": which GT7 telemetry signal or observable to watch
Keep the entire reasoning as one string; separate change-blocks by blank lines.

{{
  "ride_height_front": 80,
  "ride_height_rear": 82,
  "springs_front": 3.50,
  "springs_rear": 3.00,
  "dampers_front_comp": 30,
  "dampers_front_ext": 40,
  "dampers_rear_comp": 30,
  "dampers_rear_ext": 40,
  "arb_front": 4,
  "arb_rear": 3,
  "camber_front": -1.0,
  "camber_rear": -1.5,
  "toe_front": 0.00,
  "toe_rear": 0.05,
  "aero_front": 0,
  "aero_rear": 0,
  "lsd_initial": 10,
  "lsd_accel": 15,
  "lsd_decel": 5,
  "brake_bias": 0,
  "ballast_kg": 0.0,
  "ballast_position": 0,
  "power_restrictor": 100.0,
  "ecu_recommendation": "Stock ECU, no power restriction needed.",
  "shift_rpm": 7200,{gear_json}
  "reasoning": "springs_front set to 3.50 Hz\\nExpected lap-time effect: ...\\nExpected tyre-wear effect: ...\\nExpected fuel effect: ...\\nExpected braking-stability effect: ...\\nConfidence: medium — typical Gr.3 starting point\\nValidation method: run 3 laps and note dive under braking\\nTelemetry indicator: front suspension travel on braking zones\\n\\nNext change..."
}}"""


def _build_degradation_prompt(
    lap_sequences: dict[str, list[float]],
    wear_multiplier: float,
) -> str:
    lines = []
    for compound, times in sorted(lap_sequences.items()):
        lap_list = ", ".join(
            f"lap {i+1}: {t/1000:.3f}s" for i, t in enumerate(times)
        )
        lines.append(f"  {compound} ({len(times)} laps): {lap_list}")
    laps_block = "\n".join(lines) if lines else "  (no data)"

    return f"""You are a GT7 tyre degradation analyst.

Analyse the practice lap sequences below and identify the performance cliff for each compound.
The race wear multiplier is {wear_multiplier:.1f}× (practice laps × multiplier = race equivalent laps).

## Practice lap times (ordered within each stint)
{laps_block}

For each compound determine:
1. cliff_lap_practice — the practice lap number within the stint where pace drops non-linearly (sudden or accelerating degradation, not just normal variation). Use lap 1 as index 1. IMPORTANT: a cliff MUST be sustained across at least 2 consecutive laps. A single slow lap (spin, lock-up, traffic, outlier) does NOT constitute a cliff — set cliff_lap_practice to null if the drop is not confirmed by the following lap.
2. pace_loss_at_cliff_s — how many seconds/lap slower at the cliff vs the early-stint average (laps 1-3).
3. total_life_race — total race laps the compound lasts before it is fully uncompetitive (unscaled: multiply practice total by {1/wear_multiplier:.2f} or estimate if data is short).
4. optimal_stint_race — race laps up to but NOT including the cliff (= (cliff_lap_practice - 1) / {wear_multiplier:.1f}, rounded down, minimum 1).
5. confidence — "high" if ≥8 laps of data, "medium" if 4–7, "low" if <4.

## Compound life ordering constraint (MUST be respected)
GT7 compound physics: RS degrades fastest, RH lasts longest. Your results MUST satisfy:
  total_life_race(RS) < total_life_race(RM) < total_life_race(RH)
  optimal_stint_race(RS) ≤ optimal_stint_race(RM) ≤ optimal_stint_race(RH)
If your data analysis produces values that violate this (e.g. RS life > RM life), it means
the practice data is insufficient or unrepresentative. In that case, cap the softer compound's
total_life_race to (harder_compound_total_life - 2) and adjust optimal_stint_race proportionally.
Apply this correction silently — do not explain it in the JSON.

Reply ONLY with a valid JSON object keyed by compound name — no markdown fences:

{{
  "RM": {{
    "cliff_lap_practice": 14,
    "pace_loss_at_cliff_s": 1.8,
    "total_life_race": 18,
    "optimal_stint_race": 13,
    "confidence": "high"
  }}
}}"""


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    """Extract JSON from a model response, handling reasoning preamble and code fences.

    Handles: bare JSON, ```json ... ``` or ``` ... ``` anywhere in the response,
    and prose reasoning before the JSON block.
    """
    text = text.strip()
    # Prefer a ```json``` or ``` ``` fence anywhere in the response — the model
    # may reason first then emit a fenced JSON block, so we can't check startswith.
    m = re.search(r"```(?:json)?\s*\n([\s\S]*?)\n\s*```", text)
    if m:
        return m.group(1).strip()
    # No fence — find the first { or [ that isn't buried inside reasoning prose.
    # Scan forward; the actual JSON object/array begins at the first { or [.
    if text and text[0] not in "{[":
        for i, ch in enumerate(text):
            if ch in "{[":
                text = text[i:]
                break
    return text


def _parse_strategies(raw: str) -> list[StrategyOption]:
    data = json.loads(_strip_fences(raw))
    options: list[StrategyOption] = []
    for s in data.get("strategies", []):
        options.append(StrategyOption(
            rank=int(s.get("rank", 0)),
            name=str(s.get("name", "Strategy")),
            stints=list(s.get("stints", [])),
            estimated_time_s=float(s.get("estimated_time_s", 0.0)),
            pit_time_s=float(s.get("pit_time_s", 0.0)),
            summary=str(s.get("summary", "")),
            risks=str(s.get("risks", "")),
            positives=str(s.get("positives", "")),
            negatives=str(s.get("negatives", "")),
        ))
    options.sort(key=lambda x: x.rank)
    return options


def _parse_practice_response(raw: str) -> PracticeAnalysis:
    data = json.loads(_strip_fences(raw))
    strategies = _parse_strategies(json.dumps({"strategies": data.get("strategies", [])}))
    return PracticeAnalysis(
        strategies=strategies,
        setup_changes=list(data.get("setup_changes", [])),
        further_practice=list(data.get("further_practice", [])),
        aero_fuel_analysis=str(data.get("aero_fuel_analysis", "")),
        fuel_saving_analysis=str(data.get("fuel_saving_analysis", "")),
        tyre_management=str(data.get("tyre_management", "")),
    )


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


def _parse_setup_recommendation(
    raw: str,
    ranges: dict | None = None,
) -> CarSetupRecommendation:
    """Parse the AI JSON response into a CarSetupRecommendation.

    Parameters
    ----------
    raw:
        Raw JSON string from the AI.
    ranges:
        Resolved parameter ranges dict (from resolve_ranges). If None,
        falls back to pure generic defaults. Gearbox params are NOT
        range-managed and are left unchanged.
    """
    if ranges is None:
        ranges = resolve_ranges("")
    d = json.loads(_strip_fences(raw))
    return CarSetupRecommendation(
        ride_height_front=_clamp(float(d.get("ride_height_front", 80)),   *ranges["ride_height_front"]),
        ride_height_rear= _clamp(float(d.get("ride_height_rear",  80)),   *ranges["ride_height_rear"]),
        springs_front=    _clamp(float(d.get("springs_front", 3.50)),     *ranges["springs_front"]),
        springs_rear=     _clamp(float(d.get("springs_rear",  3.00)),     *ranges["springs_rear"]),
        dampers_front_comp=_clamp(int(d.get("dampers_front_comp", 30)),   *ranges["dampers_front_comp"]),
        dampers_front_ext= _clamp(int(d.get("dampers_front_ext",  40)),   *ranges["dampers_front_ext"]),
        dampers_rear_comp= _clamp(int(d.get("dampers_rear_comp",  25)),   *ranges["dampers_rear_comp"]),
        dampers_rear_ext=  _clamp(int(d.get("dampers_rear_ext",   35)),   *ranges["dampers_rear_ext"]),
        arb_front=  _clamp(int(d.get("arb_front", 5)),                    *ranges["arb_front"]),
        arb_rear=   _clamp(int(d.get("arb_rear",  4)),                    *ranges["arb_rear"]),
        camber_front=_clamp(float(d.get("camber_front", -1.0)),           *ranges["camber_front"]),
        camber_rear= _clamp(float(d.get("camber_rear",  -1.5)),           *ranges["camber_rear"]),
        toe_front=   _clamp(float(d.get("toe_front",  0.00)),             *ranges["toe_front"]),
        toe_rear=    _clamp(float(d.get("toe_rear",   0.05)),             *ranges["toe_rear"]),
        aero_front=  _clamp(int(d.get("aero_front", 400)),                *ranges["aero_front"]),
        aero_rear=   _clamp(int(d.get("aero_rear",  600)),                *ranges["aero_rear"]),
        lsd_initial= _clamp(int(d.get("lsd_initial", 10)),                *ranges["lsd_initial"]),
        lsd_accel=   _clamp(int(d.get("lsd_accel",  15)),                 *ranges["lsd_accel"]),
        lsd_decel=   _clamp(int(d.get("lsd_decel",   5)),                 *ranges["lsd_decel"]),
        lsd_front_initial=_clamp(int(d.get("lsd_front_initial", 0)),      *ranges["lsd_front_initial"]),
        lsd_front_accel=  _clamp(int(d.get("lsd_front_accel",   0)),      *ranges["lsd_front_accel"]),
        lsd_front_decel=  _clamp(int(d.get("lsd_front_decel",   0)),      *ranges["lsd_front_decel"]),
        brake_bias=  _clamp(int(d.get("brake_bias",   0)),                *ranges["brake_bias"]),
        ballast_kg=      _clamp(float(d.get("ballast_kg",      0.0)),     *ranges["ballast_kg"]),
        ballast_position=_clamp(int(d.get("ballast_position",  0)),       *ranges["ballast_position"]),
        power_restrictor=_clamp(float(d.get("power_restrictor", 100.0)), *ranges["power_restrictor"]),
        # Gearbox params are NOT range-managed — leave unchanged
        final_drive=float(d.get("final_drive", 0.0)),
        transmission_max_speed_kmh=float(d.get("transmission_max_speed_kmh", 0.0)),
        gear_ratios=[float(x) for x in d.get("gear_ratios", [])],
        reasoning=str(d.get("reasoning", "")),
        ecu_recommendation=str(d.get("ecu_recommendation", "")),
        shift_rpm=_clamp(int(d.get("shift_rpm", 0)), 0, 20000),
    )


def _parse_degradation_response(raw: str, lap_counts: dict[str, int] | None = None) -> dict:
    data = json.loads(_strip_fences(raw))
    result = {}
    for compound, d in data.items():
        cliff = d.get("cliff_lap_practice")
        try:
            cliff = int(cliff) if cliff is not None else 0
        except (TypeError, ValueError):
            cliff = 0
        conf = str(d.get("confidence", "low"))
        total_laps = (lap_counts or {}).get(compound, 0)
        # Zero out cliff if it falls on the very last lap and confidence is low —
        # this pattern indicates an outlier final lap rather than a real degradation cliff.
        if cliff and conf == "low" and total_laps > 0 and cliff >= total_laps:
            cliff = 0
        result[compound] = {
            "cliff_lap_practice": cliff,
            "pace_loss_at_cliff_s": float(d.get("pace_loss_at_cliff_s", 0.0)),
            "total_life_race": int(d.get("total_life_race", 0)),
            "optimal_stint_race": int(d.get("optimal_stint_race", 0)),
            "confidence": conf,
        }
    return result
