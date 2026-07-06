"""Group 49 — Race Strategy Brain Phase 3: Porsche RSR / Fuji SessionDB benchmark.

Proves the end-to-end SessionDB pathway offline: seed an in-memory SessionDB with
realistic Porsche 911 RSR '17 / Fuji practice laps, then run the session-backed
pipeline and show that evidence, candidates, scoring, recommendation, and a
source-aware explanation all come out of REAL stored session data — no AI, no
external services, no runtime files.

Scenario: Porsche 911 RSR '17 · Fuji Full Course · ~50 min · 8× tyre · 3× fuel ·
1 L/s refuel. Driver prefers a stable rear (structured Group 42 DriverProfile), so
the rear is treated as fragile and the push plan is never recommended.

Pure/offline: the only I/O is an in-memory (`:memory:`) SQLite DB created here.
Never writes to disk-backed runtime files.
"""
from __future__ import annotations

from dataclasses import dataclass

from strategy.race_strategy_pipeline import (
    SessionStrategyResult,
    recommend_strategy_from_session,
)

BENCHMARK_CAR = "Porsche 911 RSR '17"
BENCHMARK_CAR_ID = 911
BENCHMARK_TRACK = "Fuji Speedway"
BENCHMARK_LAYOUT = "fuji_speedway__full_course"
BENCHMARK_DURATION_MIN = 50.0
BENCHMARK_TYRE_MULT = 8.0
BENCHMARK_FUEL_MULT = 3.0
BENCHMARK_REFUEL_LPS = 1.0
BENCHMARK_PIT_LOSS_S = 22.0
BENCHMARK_AVAILABLE_COMPOUNDS = ("RM", "RH")

# 12 clean RM practice laps at ~1:40 with a steady +0.08s/lap tyre-wear drift, and
# ~4.0 L/lap fuel (a full 100 L tank cannot cover a 30-lap no-stop).
_BASE_LAP_S = 100.0
_WEAR_PER_LAP_S = 0.08
_FUEL_PER_LAP_L = 4.0
_N_LAPS = 12


@dataclass
class SessionBenchmarkResult:
    db: object
    session_id: int
    result: SessionStrategyResult
    rear_traction_fragile: bool


def _rear_fragile_from_profile() -> bool:
    """Read rear fragility from the structured DriverProfile (never free text)."""
    try:
        from strategy.setup_driver_profile import build_driver_profile
        p = build_driver_profile()
        return bool(p.prefers_rear_stability or p.dislikes_snap_exit)
    except Exception:
        return True


def seed_benchmark_session(db) -> int:
    """Seed the RSR/Fuji practice session into ``db`` and return the session id.

    Writes only via SessionDB's public ``open_session`` / ``write_lap`` methods.
    ``db`` should be an in-memory SessionDB (``SessionDB(':memory:')``).
    """
    session_id = db.open_session(
        car_id=BENCHMARK_CAR_ID,
        track=BENCHMARK_TRACK,
        session_type="Practice",
        car_name=BENCHMARK_CAR,
    )
    fuel_remaining = 100.0
    for i in range(_N_LAPS):
        lap_time_ms = int(round((_BASE_LAP_S + i * _WEAR_PER_LAP_S) * 1000))
        fuel_start = fuel_remaining
        fuel_end = fuel_remaining - _FUEL_PER_LAP_L
        db.write_lap(
            session_id=session_id,
            lap_num=i + 1,
            lap_time_ms=lap_time_ms,
            fuel_used=_FUEL_PER_LAP_L,
            stats=None,
            compound="RM",
            is_out_lap=False,
            is_pit_lap=False,
            fuel_start=fuel_start,
            fuel_end=fuel_end,
        )
        fuel_remaining = fuel_end
    return session_id


def build_benchmark_db():
    """Create an in-memory SessionDB seeded with the benchmark session.

    Returns (db, session_id). The caller owns the db (kept in memory only).
    """
    from data.session_db import SessionDB
    db = SessionDB(":memory:")
    session_id = seed_benchmark_session(db)
    return db, session_id


def run_session_benchmark(db=None, session_id: int = 0) -> SessionBenchmarkResult:
    """Run the full SessionDB-backed pipeline on the RSR/Fuji scenario.

    When ``db``/``session_id`` are not supplied, an in-memory DB is created and
    seeded. Returns a :class:`SessionBenchmarkResult`.
    """
    if db is None or not session_id:
        db, session_id = build_benchmark_db()

    rear_fragile = _rear_fragile_from_profile()
    result = recommend_strategy_from_session(
        db,
        session_id=session_id,
        car_id=BENCHMARK_CAR_ID,
        track=BENCHMARK_TRACK,
        layout_id=BENCHMARK_LAYOUT,
        race_duration_minutes=BENCHMARK_DURATION_MIN,
        race_laps=0,  # timed → estimated from measured race pace
        fuel_multiplier=BENCHMARK_FUEL_MULT,
        tyre_multiplier=BENCHMARK_TYRE_MULT,
        refuel_rate_lps=BENCHMARK_REFUEL_LPS,
        pit_loss_seconds=BENCHMARK_PIT_LOSS_S,
        available_compounds=BENCHMARK_AVAILABLE_COMPOUNDS,
        required_compounds=(),
        mandatory_pit_stops=0,
        weather_context="dry_stable",
        rear_traction_fragile=rear_fragile,
    )
    return SessionBenchmarkResult(
        db=db,
        session_id=session_id,
        result=result,
        rear_traction_fragile=rear_fragile,
    )
