"""Feasibility gate for race strategy analysis.

Pure module — no Qt, no API calls, no DB access.
Mirrors the style of strategy/setup_ranges.py.

Provides:
  - RejectedStrategy, DataGap, FeasibilityReport dataclasses
  - estimate_race_laps(duration_s, representative_lap_s) -> int
  - check_compound_eligibility(compound, clean_lap_times_ms, degradation_entry) -> (bool, str|None)
  - compute_feasibility(params, lap_data_by_compound, degradation, estimated_laps) -> FeasibilityReport

GT7 domain facts encoded here:
  - Tank capacity is always 100.0 litres (100% == 100 litres; starting fuel == 100).
  - Do NOT add tank_capacity to RaceParams.
  - Minimum 8 clean laps required for a compound to be eligible for a calculated stint.
  - Pit work is sequential: refuel time adds on top of fixed pit_loss_secs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# GT7 domain constant: full tank is always 100 litres.
_GT7_TANK_CAPACITY = 100.0


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RejectedStrategy:
    name: str
    reason: str


@dataclass
class DataGap:
    name: str
    description: str


@dataclass
class FeasibilityReport:
    estimated_laps: int
    feasible_stop_counts: list[int]
    rejected_strategies: list[RejectedStrategy]
    data_gaps: list[DataGap]
    assumptions: list[str]
    calculation_notes: list[str]
    eligible_compounds: list[str]
    ineligible_compounds: list[str]


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def estimate_race_laps(duration_s: float, representative_lap_s: float) -> int:
    """Estimate race laps for a timed event.

    Returns math.ceil(duration_s / representative_lap_s).
    Guards against representative_lap_s <= 0 (returns 0).
    """
    if representative_lap_s <= 0:
        return 0
    return math.ceil(duration_s / representative_lap_s)


def check_compound_eligibility(
    compound: str,
    clean_lap_times_ms: list[float],
    degradation_entry: dict | None,
) -> tuple[bool, str | None]:
    """Check whether a compound has enough data for a calculated race stint.

    Eligibility rules:
    1. At least 8 clean lap times recorded.
    2. degradation_entry must not be None.
    3. degradation_entry must have a non-None optimal_stint_race.
    4. degradation_entry must have a max-stint signal: total_life_race > 0
       OR (pace_loss_at_cliff_s is not None AND cliff_lap_practice > 0).
    5. degradation_entry must have a confidence value.

    Returns (True, None) when eligible.
    Returns (False, human_reason) when ineligible.
    """
    lap_count = len(clean_lap_times_ms)
    reasons: list[str] = []

    if lap_count < 8:
        reasons.append(f"only {lap_count} clean laps recorded (minimum 8 required)")

    if degradation_entry is None:
        reasons.append("no degradation analysis available")
        # If there is no degradation entry we have at least 2 reasons (lap count + this)
        # but we can short-circuit since remaining checks require degradation_entry.
        return False, f"{compound}: {'; '.join(reasons)}"

    # Check optimal_stint_race
    optimal = degradation_entry.get("optimal_stint_race")
    if optimal is None or int(optimal) <= 0:
        reasons.append("optimal_stint_race is missing or zero")

    # Check max-stint signal: either total_life_race > 0 OR cliff data present
    total_life = degradation_entry.get("total_life_race", 0)
    pace_loss = degradation_entry.get("pace_loss_at_cliff_s")
    cliff_lap = degradation_entry.get("cliff_lap_practice", 0)
    has_total_life = (total_life is not None and int(total_life) > 0)
    has_cliff = (pace_loss is not None and cliff_lap is not None and int(cliff_lap) > 0)
    if not (has_total_life or has_cliff):
        reasons.append(
            "no max-stint signal (total_life_race is zero/missing and cliff data is incomplete)"
        )

    # Check confidence
    confidence = degradation_entry.get("confidence")
    if not confidence:
        reasons.append("confidence is missing")

    if reasons:
        return False, f"{compound}: {'; '.join(reasons)}"
    return True, None


def compute_feasibility(
    params,                                  # RaceParams
    lap_data_by_compound: dict[str, list[float]],
    degradation: dict | None,
    estimated_laps: int,
) -> FeasibilityReport:
    """Compute feasibility of all candidate stop-count strategies.

    Steps:
    1. Global field validation → DataGaps (and early return for fatal gaps).
    2. Per-compound eligibility.
    3. Candidate stop-count evaluation (0 to min(estimated_laps - 1, 4)).
    4. Populate standard assumptions and calculation notes.

    Returns a FeasibilityReport; never raises on bad/missing data.

    Parameters
    ----------
    params:
        RaceParams instance.  pit_loss_secs is the authoritative pit loss;
        seed-track pit_loss data is NOT used (that path is dead in the codebase).
    lap_data_by_compound:
        {compound_code: [clean_lap_time_ms, ...]}
    degradation:
        Parsed degradation dict {compound: {...}} or None.
    estimated_laps:
        For timed races, from estimate_race_laps(); for lap races, params.total_laps.
    """
    data_gaps: list[DataGap] = []
    rejected_strategies: list[RejectedStrategy] = []
    assumptions: list[str] = []
    calculation_notes: list[str] = []
    eligible_compounds: list[str] = []
    ineligible_compounds: list[str] = []

    # ------------------------------------------------------------------
    # Step 1: Global field validation
    # ------------------------------------------------------------------
    _fatal = False

    refuel_speed = getattr(params, "refuel_speed_lps", 0.0) or 0.0
    if refuel_speed <= 0:
        data_gaps.append(DataGap(
            name="missing_refuel_speed",
            description=(
                "refuel_speed_lps is 0 or missing — cannot calculate pit stop duration. "
                "Measure the refuel rate from a practice pit stop."
            ),
        ))
        _fatal = True

    pit_loss = getattr(params, "pit_loss_secs", 0.0) or 0.0
    if pit_loss <= 0:
        data_gaps.append(DataGap(
            name="missing_pit_loss",
            description=(
                "pit_loss_secs is 0 or missing — cannot calculate pit stop duration. "
                "Record pit entry-to-racing-line time from a practice pit stop."
            ),
        ))
        # Not immediately fatal but makes stop-count math unreliable; note it.

    has_any_lap_data = any(len(v) > 0 for v in lap_data_by_compound.values())
    if not has_any_lap_data:
        data_gaps.append(DataGap(
            name="no_lap_data",
            description=(
                "No clean lap times recorded for any compound. "
                "Complete at least 8 clean laps per compound to enable strategy analysis."
            ),
        ))
        _fatal = True

    fuel_burn = getattr(params, "fuel_burn_per_lap", 0.0) or 0.0
    if fuel_burn <= 0:
        data_gaps.append(DataGap(
            name="missing_fuel_burn",
            description=(
                "fuel_burn_per_lap is 0 or missing — cannot calculate fuel requirements. "
                "Record fuel used per lap from practice telemetry."
            ),
        ))

    tyre_wear_mult = getattr(params, "tyre_wear_multiplier", 0.0)
    if tyre_wear_mult == 0:
        data_gaps.append(DataGap(
            name="missing_tyre_wear_multiplier",
            description=(
                "tyre_wear_multiplier is 0 — this is an invalid value. "
                "Standard wear is 1.0; high-wear events are typically 2.0–4.0."
            ),
        ))

    # ------------------------------------------------------------------
    # Validate race duration / lap count (AC1: race duration must be present)
    # estimated_laps is computed by the caller (analyse_strategy) before this
    # function is invoked, so we guard it here as the single source of truth.
    # A value of 0 means the caller could not derive a meaningful race length
    # (e.g. timed race with duration_mins=0, or lap race with total_laps=0,
    # or no representative clean lap available to estimate laps).
    # ------------------------------------------------------------------
    if estimated_laps <= 0:
        data_gaps.append(DataGap(
            name="missing_race_duration",
            description=(
                "Race duration or lap count is absent or invalid (estimated_laps = 0). "
                "For a timed race, set duration_mins > 0 and ensure at least one clean lap "
                "is recorded so laps can be estimated. For a lap race, set total_laps > 0."
            ),
        ))
        _fatal = True

    # ------------------------------------------------------------------
    # Populate standard assumptions (always included for timed/lap races)
    # ------------------------------------------------------------------
    assumptions.append(
        "GT7 may require completing the lap in progress when the timer expires — "
        f"actual laps may be {estimated_laps} + 1."
    )
    assumptions.append(
        f"Event pit_loss_secs ({pit_loss:.1f}s) is authoritative; "
        "seed-track pit delta data is not used."
    )
    assumptions.append(
        "Pit work is sequential: refuel time adds on top of the fixed pit-lane loss "
        "which already covers the tyre swap."
    )

    # Calculation note for estimated_laps
    if params.race_type == "timed":
        duration_s = (getattr(params, "duration_mins", 0) or 0) * 60.0
        calculation_notes.append(
            f"Race laps estimated as ceil({duration_s:.0f}s / representative_lap_s) = {estimated_laps} laps "
            f"(representative lap chosen as the minimum clean lap time for the fastest compound)."
        )
    else:
        calculation_notes.append(
            f"Race laps taken directly from params.total_laps = {estimated_laps}."
        )

    # Early return for fatal gaps
    if _fatal:
        return FeasibilityReport(
            estimated_laps=estimated_laps,
            feasible_stop_counts=[],
            rejected_strategies=rejected_strategies,
            data_gaps=data_gaps,
            assumptions=assumptions,
            calculation_notes=calculation_notes,
            eligible_compounds=[],
            ineligible_compounds=[],
        )

    # ------------------------------------------------------------------
    # Step 2: Per-compound eligibility
    # ------------------------------------------------------------------
    # Determine the compound list to evaluate
    avail_tyres = list(getattr(params, "avail_tyres", []) or [])
    if avail_tyres:
        compounds_to_check = avail_tyres
    else:
        compounds_to_check = list(lap_data_by_compound.keys())

    for compound in compounds_to_check:
        laps = lap_data_by_compound.get(compound, [])
        deg_entry = (degradation or {}).get(compound)
        eligible, reason = check_compound_eligibility(compound, laps, deg_entry)
        if eligible:
            eligible_compounds.append(compound)
            calculation_notes.append(
                f"{compound}: eligible — {len(laps)} clean laps, "
                f"optimal_stint_race={deg_entry.get('optimal_stint_race')}, "  # type: ignore[union-attr]
                f"confidence={deg_entry.get('confidence')}."  # type: ignore[union-attr]
            )
        else:
            ineligible_compounds.append(compound)
            data_gaps.append(DataGap(
                name=f"compound_{compound}_insufficient_data",
                description=(
                    f"{reason}. This compound will not appear in calculated stints. "
                    "Complete ≥8 clean laps and run tyre degradation analysis to unlock it."
                ),
            ))
            calculation_notes.append(
                f"{compound}: ineligible — {reason}."
            )

    # ------------------------------------------------------------------
    # Step 3: Mandatory compound validation
    # ------------------------------------------------------------------
    mandatory_compounds = list(getattr(params, "mandatory_compounds", []) or [])
    mandatory_data_fatal: dict[str, str] = {}  # compound → reason
    for mc in mandatory_compounds:
        mc_laps = lap_data_by_compound.get(mc, [])
        if not mc_laps:
            gap_name = f"mandatory_compound_{mc}_no_data"
            data_gaps.append(DataGap(
                name=gap_name,
                description=(
                    f"Mandatory compound {mc} has no lap data. "
                    "Any stop count that requires this compound cannot be validated."
                ),
            ))
            mandatory_data_fatal[mc] = f"mandatory compound {mc} has no lap data"
            calculation_notes.append(
                f"Mandatory compound {mc}: no lap data — all stop counts that require it will be rejected."
            )

    # ------------------------------------------------------------------
    # Step 4: Candidate stop-count evaluation
    # ------------------------------------------------------------------
    min_mandatory = getattr(params, "min_mandatory_stops", 0) or 0

    # Cap to min(estimated_laps - 1, 4) stops
    max_stops = min(max(estimated_laps - 1, 0), 4)
    feasible_stop_counts: list[int] = []

    for n in range(0, max_stops + 1):
        per_stint_laps = math.ceil(estimated_laps / (n + 1))
        reject_reason: str | None = None

        # Reject if below mandatory stop minimum
        if n < min_mandatory:
            reject_reason = (
                f"{n}-stop: rejected — race rules require at least {min_mandatory} pit stop(s)."
            )
            rejected_strategies.append(RejectedStrategy(
                name=f"{n}-stop",
                reason=reject_reason,
            ))
            calculation_notes.append(reject_reason)
            continue

        # Reject if mandatory compounds have no data
        if mandatory_data_fatal:
            missing_mc = ", ".join(mandatory_data_fatal.keys())
            reject_reason = (
                f"{n}-stop: rejected — mandatory compound(s) {missing_mc} have no lap data; "
                "strategy cannot be validated."
            )
            rejected_strategies.append(RejectedStrategy(
                name=f"{n}-stop",
                reason=reject_reason,
            ))
            calculation_notes.append(reject_reason)
            continue

        # Reject if no eligible compound's optimal_stint covers the per-stint laps
        if eligible_compounds:
            best_optimal = 0
            best_compound = ""
            for ec in eligible_compounds:
                deg_entry = (degradation or {}).get(ec, {})
                opt = int(deg_entry.get("optimal_stint_race", 0) or 0)
                if opt > best_optimal:
                    best_optimal = opt
                    best_compound = ec
            if per_stint_laps > best_optimal:
                reject_reason = (
                    f"{n}-stop: rejected — requires {per_stint_laps}-lap average stints "
                    f"but best validated optimal stint is {best_optimal} laps"
                    f"{(' (' + best_compound + ')') if best_compound else ''}. "
                    "No eligible compound can cover this stint length."
                )
                rejected_strategies.append(RejectedStrategy(
                    name=f"{n}-stop",
                    reason=reject_reason,
                ))
                calculation_notes.append(reject_reason)
                continue
        else:
            # No eligible compounds — all stop counts are infeasible
            reject_reason = (
                f"{n}-stop: rejected — no compound has sufficient data for a calculated stint."
            )
            rejected_strategies.append(RejectedStrategy(
                name=f"{n}-stop",
                reason=reject_reason,
            ))
            calculation_notes.append(reject_reason)
            continue

        # Fuel check for 0-stop: if fuel_burn is known, validate that a full tank covers the race
        if n == 0 and fuel_burn > 0:
            max_fuel_laps = math.floor(_GT7_TANK_CAPACITY / fuel_burn)
            if max_fuel_laps < estimated_laps:
                reject_reason = (
                    f"0-stop: rejected — fuel-limited. A full 100L tank covers only "
                    f"{max_fuel_laps} laps at {fuel_burn:.2f} L/lap, "
                    f"but {estimated_laps} laps are needed."
                )
                rejected_strategies.append(RejectedStrategy(
                    name="0-stop",
                    reason=reject_reason,
                ))
                calculation_notes.append(reject_reason)
                continue

        # Survived all checks
        feasible_stop_counts.append(n)
        calculation_notes.append(
            f"{n}-stop: feasible — per-stint laps needed = {per_stint_laps}, "
            f"best optimal stint = {best_optimal if eligible_compounds else 'N/A'} laps."
        )

    return FeasibilityReport(
        estimated_laps=estimated_laps,
        feasible_stop_counts=feasible_stop_counts,
        rejected_strategies=rejected_strategies,
        data_gaps=data_gaps,
        assumptions=assumptions,
        calculation_notes=calculation_notes,
        eligible_compounds=eligible_compounds,
        ineligible_compounds=ineligible_compounds,
    )
