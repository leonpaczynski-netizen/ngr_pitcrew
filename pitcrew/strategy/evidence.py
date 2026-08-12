"""Turning recorded practice into strategy inputs, with provenance attached.

The screen renders each input in the register it came from — telemetry in
stencil, driver-entered in crayon, the app's own assumptions struck — so the
driver can see at a glance which parts of the plan rest on measurement and
which rest on a guess. That is the difference between a plan he can trust
under pressure and one he cannot.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from pitcrew.analysis.session import LapInput, counted_laps, green_lap_reference_ms
from pitcrew.analysis.wear import wear_per_lap as wear_rate
from pitcrew.strategy.model import (
    FUEL_WEIGHT_S_PER_L_PER_LAP,
    PIT_DEAD_TIME_S,
    RaceInputs,
    laps_from_minutes,
)

MEASURED = "measured"      # off the telemetry stream
DECLARED = "declared"      # the driver entered it
ASSUMED = "assumed"        # the app's own working figure
MISSING = "missing"        # not known, and not invented


@dataclass(frozen=True)
class Evidence:
    label: str
    value: str
    source: str
    note: str = ""


def _lap_inputs(store, event_id: int) -> list[LapInput]:
    rows = store.list_event_laps(event_id, "practice")
    return [
        LapInput(
            lap_num=row["lap_num"],
            lap_time_ms=row["lap_time_ms"],
            fuel_start=row["fuel_start"],
            fuel_end=row["fuel_end"],
            compound=row["compound"],
            is_pit_lap=bool(row["is_pit_lap"]),
            is_out_lap=bool(row["is_out_lap"]),
            excluded=bool(row["excluded"]),
            exclusion_reason=row["exclusion_reason"],
            wear_fl=row["wear_fl"],
            wear_fr=row["wear_fr"],
            wear_rl=row["wear_rl"],
            wear_rr=row["wear_rr"],
        )
        for row in rows
    ]


def _fuel_capacity(store, event_id: int) -> float | None:
    for session in store.list_sessions(event_id, "practice"):
        if session["fuel_capacity_l"] is not None:
            return session["fuel_capacity_l"]
    return None


def build_inputs(store, event_id: int) -> tuple[RaceInputs, list[Evidence]]:
    """Assemble the model's inputs from the event and its practice laps."""
    event = store.get_event(event_id)
    if event is None:
        raise ValueError(f"no event with id {event_id}")

    laps = _lap_inputs(store, event_id)
    counted = counted_laps(laps)

    burns = [lap.fuel_start - lap.fuel_end for lap in counted
             if lap.fuel_start > lap.fuel_end]
    fuel_per_lap = round(median(burns), 3) if burns else None
    reference_ms = green_lap_reference_ms(laps)
    wear = wear_rate(laps)
    capacity = _fuel_capacity(store, event_id)

    # The compound the evidence came from. Stints default to it, because a
    # wear rate measured on one compound does not describe another.
    tagged = [lap.compound for lap in counted if lap.compound]
    evidence_compound = None
    if tagged:
        evidence_compound = max(set(tagged), key=tagged.count)

    race_laps = event["race_laps"] or 0
    if event["race_type"] == "time" and reference_ms:
        race_laps = laps_from_minutes(event["race_laps"] or 0, reference_ms)

    inputs = RaceInputs(
        race_laps=race_laps,
        lap_time_ms=reference_ms or 0,
        fuel_per_lap_l=fuel_per_lap,
        fuel_capacity_l=capacity,
        refuel_rate_lps=event["refuel_rate_lps"],
        pit_loss_s=event["pit_loss_secs"],
        wear_per_lap=wear,
        mandatory_stops=event["mandatory_stops"] or 0,
        available_compounds=tuple(event["available_compounds"]),
        required_compounds=tuple(event["required_compounds"]),
        evidence_compound=evidence_compound,
    )

    evidence = [
        Evidence("Race length", f"{race_laps} laps",
                 DECLARED if event["race_type"] == "laps" else ASSUMED,
                 "" if event["race_type"] == "laps"
                 else "converted from race minutes at the reference lap"),
        Evidence("Reference lap",
                 _lap_time(reference_ms), MEASURED if reference_ms else MISSING,
                 f"fastest of the first counted laps, {len(counted)} counted"
                 if reference_ms else "run a practice lap"),
        Evidence("Fuel per lap",
                 f"{fuel_per_lap:.2f} L" if fuel_per_lap else "—",
                 MEASURED if fuel_per_lap else MISSING,
                 f"median of {len(burns)} laps" if burns else "no fuel burn recorded"),
        Evidence("Fuel capacity",
                 f"{capacity:.0f} L" if capacity is not None else "—",
                 MEASURED if capacity is not None else MISSING,
                 "from the stream" if capacity is not None else ""),
        Evidence("Tyre wear",
                 f"{wear:.1%} per lap" if wear else "—",
                 DECLARED if wear else MISSING,
                 "from your gauge reading" if wear
                 else "read the in-game gauge and enter it on a practice lap"),
        Evidence("Evidence compound", evidence_compound or "—",
                 DECLARED if evidence_compound else MISSING,
                 "wear and fuel describe this compound only"
                 if evidence_compound else "tag your practice laps"),
        Evidence("Pit loss", f"{event['pit_loss_secs']:.1f} s", DECLARED,
                 "a track constant"),
        Evidence("Pit dead time", f"{PIT_DEAD_TIME_S:.1f} s", ASSUMED,
                 "before refuelling begins"),
        Evidence("Refuel rate", f"{event['refuel_rate_lps']:.2f} L/s", DECLARED),
        Evidence("Fuel weight",
                 f"{FUEL_WEIGHT_S_PER_L_PER_LAP:.3f} s/L/lap", ASSUMED,
                 "derived, not measured - overwrite it if you measure it"),
    ]
    return inputs, evidence


def _lap_time(ms: int | None) -> str:
    if not ms:
        return "—"
    minutes, remainder = divmod(ms, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"
