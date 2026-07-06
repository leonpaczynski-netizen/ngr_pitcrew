"""Group 51 — Race Strategy Brain Phase 5: Porsche RSR / Fuji manual-UAT support.

A small, deterministic, offline helper that reproduces the recommended manual-UAT
scenario end to end (seed a SessionDB, read samples, grade readiness/diagnostics,
and run the session-backed recommendation). It exists so a reviewer can confirm the
Race Plan surface behaves correctly WITHOUT the game, an API key, or production data.

    Porsche 911 RSR '17 · Fuji Full Course · 50 min · 8× tyre · 3× fuel · 1 L/s refuel

Pure/offline: the only I/O is an in-memory (`:memory:`) SQLite DB created here. No Qt,
no AI, no writes to disk-backed runtime files. Lives in `ui/` because it composes the
`ui` readiness layer with the `strategy` pipeline (ui → strategy dependency direction).
"""
from __future__ import annotations

from dataclasses import dataclass

from strategy.race_strategy_pipeline import SessionStrategyResult, recommend_strategy_from_session
from strategy.race_strategy_session_adapter import (
    SessionStrategySamples,
    extract_session_strategy_samples,
)
from ui.race_strategy_readiness_vm import (
    RacePlanReadiness,
    SessionDiagnostics,
    build_race_plan_readiness,
    build_session_diagnostics,
    empty_state_messages,
)


FUJI_UAT_CAR = "Porsche 911 RSR '17"
FUJI_UAT_CAR_ID = 911
FUJI_UAT_TRACK = "Fuji Speedway"
FUJI_UAT_LAYOUT = "fuji_speedway__full_course"

# Canonical event settings for the scenario (mirrors the Group 49/50 benchmark).
FUJI_UAT_EVENT_SETTINGS = {
    "car_id": FUJI_UAT_CAR_ID,
    "track": FUJI_UAT_TRACK,
    "layout_id": FUJI_UAT_LAYOUT,
    "race_duration_minutes": 50.0,
    "race_laps": 0,
    "fuel_multiplier": 3.0,
    "tyre_multiplier": 8.0,
    "refuel_rate_lps": 1.0,
    "pit_loss_seconds": 22.0,
    "starting_fuel_pct": 100.0,
    "available_compounds": ("RM", "RH"),
    "required_compounds": (),
    "mandatory_pit_stops": 0,
}

_BASE_LAP_S = 100.0
_WEAR_PER_LAP_S = 0.08
_FUEL_PER_LAP_L = 4.0


@dataclass
class FujiUatContext:
    db: object
    session_id: int
    samples: SessionStrategySamples
    diagnostics: SessionDiagnostics
    readiness: RacePlanReadiness
    empty_state_messages: list
    event_settings: dict


def build_fuji_uat_db(n_laps: int = 12, fuel: float = _FUEL_PER_LAP_L):
    """Create an in-memory SessionDB seeded with the RSR/Fuji practice session.

    Returns (db, session_id). ``n_laps``/``fuel`` let a caller simulate an
    incomplete session (short run / no fuel signal) to exercise missing-evidence.
    """
    from data.session_db import SessionDB
    db = SessionDB(":memory:")
    sid = db.open_session(
        car_id=FUJI_UAT_CAR_ID, track=FUJI_UAT_TRACK,
        session_type="Practice", car_name=FUJI_UAT_CAR,
    )
    remaining = 100.0
    for i in range(n_laps):
        lap_ms = int(round((_BASE_LAP_S + i * _WEAR_PER_LAP_S) * 1000))
        db.write_lap(
            session_id=sid, lap_num=i + 1, lap_time_ms=lap_ms,
            fuel_used=fuel, stats=None, compound="RM",
            fuel_start=remaining, fuel_end=remaining - fuel,
        )
        remaining -= fuel
    return db, sid


def build_fuji_uat_context(n_laps: int = 12, fuel: float = _FUEL_PER_LAP_L) -> FujiUatContext:
    """Build the full offline UAT context (samples + diagnostics + readiness)."""
    db, sid = build_fuji_uat_db(n_laps=n_laps, fuel=fuel)
    es = dict(FUJI_UAT_EVENT_SETTINGS)
    samples = extract_session_strategy_samples(
        db, sid, expected_car_id=FUJI_UAT_CAR_ID, expected_track=FUJI_UAT_TRACK,
        layout_id=FUJI_UAT_LAYOUT,
    )
    diagnostics = build_session_diagnostics(
        samples, event_car_id=FUJI_UAT_CAR_ID, event_track=FUJI_UAT_TRACK,
        event_layout=FUJI_UAT_LAYOUT,
    )
    readiness = build_race_plan_readiness(samples=samples, event_settings=es)
    msgs = empty_state_messages(samples, es)
    return FujiUatContext(
        db=db, session_id=sid, samples=samples,
        diagnostics=diagnostics, readiness=readiness,
        empty_state_messages=msgs, event_settings=es,
    )


def run_fuji_uat(n_laps: int = 12, fuel: float = _FUEL_PER_LAP_L) -> SessionStrategyResult:
    """Run the full session-backed recommendation for the RSR/Fuji scenario.

    Rear-fragility is read from the structured driver profile (never free text),
    so the push plan is demoted exactly as in the live surface.
    """
    db, sid = build_fuji_uat_db(n_laps=n_laps, fuel=fuel)
    rear_fragile = _rear_fragile_from_profile()
    es = dict(FUJI_UAT_EVENT_SETTINGS)
    return recommend_strategy_from_session(
        db,
        session_id=sid,
        car_id=es["car_id"],
        track=es["track"],
        layout_id=es["layout_id"],
        race_duration_minutes=es["race_duration_minutes"],
        race_laps=es["race_laps"],
        fuel_multiplier=es["fuel_multiplier"],
        tyre_multiplier=es["tyre_multiplier"],
        refuel_rate_lps=es["refuel_rate_lps"],
        pit_loss_seconds=es["pit_loss_seconds"],
        starting_fuel_pct=es["starting_fuel_pct"],
        available_compounds=es["available_compounds"],
        required_compounds=es["required_compounds"],
        mandatory_pit_stops=es["mandatory_pit_stops"],
        rear_traction_fragile=rear_fragile,
    )


def _rear_fragile_from_profile() -> bool:
    try:
        from strategy.setup_driver_profile import build_driver_profile
        p = build_driver_profile()
        return bool(p.prefers_rear_stability or p.dislikes_snap_exit)
    except Exception:
        return True
