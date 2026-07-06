"""Group 49 — Race Strategy Brain Phase 3: read-only SessionDB sample adapter.

WHY IT EXISTS
  Group 48 built a pure strategy brain whose evidence builder took samples from
  the caller. This module is the one place that reaches into SessionDB and pulls
  the *strategy-relevant* signals — clean lap times, fuel use, a derived tyre-wear
  proxy, and per-compound pace — so the rest of the Phase 3 stack can stay pure.

WHAT THIS MODULE IS NOT
  • It is NOT an AI and invents no telemetry. A signal SessionDB does not store is
    recorded in ``missing_fields`` — never guessed.
  • It is strictly READ-ONLY. It calls only SessionDB read methods
    (``get_session_meta``, ``get_session_laps``). It writes nothing — no DB rows,
    no ``data/setup_history.json``, no runtime JSON, no track-model data.
  • It authors no setup values and cannot reach the Apply gate.

TYRE-WEAR HONESTY
  SessionDB has no explicit per-lap tyre-wear column, so tyre degradation is not
  *directly* measured. When ``derive_tyre_wear`` is set (the default) the adapter
  derives a conservative proxy from the MEASURED lap-time drift within a stint
  (positive lap-to-lap increases on the same compound). This is a real measured
  signal (the driver's laps genuinely got slower), clearly labelled as *derived*
  in ``source_summary``; if there is not enough consecutive same-compound data the
  proxy is empty and tyre wear is recorded as missing evidence.

PURITY / SAFETY
  Never raises: every public function wraps its internals and returns a safe empty
  result on any error. Deterministic: identical DB state → identical samples.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Optional, Sequence

# Minimum consecutive same-compound clean laps needed to derive a tyre-wear proxy.
MIN_STINT_LAPS_FOR_WEAR: int = 3

# Missing-field codes (stable identifiers surfaced to the evidence layer).
MISS_SESSION = "session_not_found"
MISS_LAPS = "no_clean_laps"
MISS_FUEL = "no_fuel_samples"
MISS_TYRE = "no_tyre_wear_samples"
MISS_COMPOUND = "no_compound_samples"
MISS_CAR_TRACK_MISMATCH = "car_track_mismatch"


@dataclass(frozen=True)
class SessionStrategySamples:
    """Typed, read-only bundle of strategy samples extracted from SessionDB.

    All sample lists are empty when the underlying signal is unavailable; the
    corresponding code then appears in ``missing_fields``. ``source_summary``
    records provenance (counts + whether tyre wear was derived) so the
    explanation layer can tell the driver what came from real session data.
    """

    session_id: int = 0
    car_id: int = 0
    track: str = ""
    layout_id: str = ""

    lap_samples: tuple[float, ...] = ()          # clean lap times, seconds
    fuel_samples: tuple[float, ...] = ()         # litres per lap
    tyre_samples: tuple[float, ...] = ()         # derived per-lap pace-loss proxy, seconds
    compound_samples: dict = field(default_factory=dict)  # {compound: (lap_time_s, ...)}
    pit_samples: tuple[int, ...] = ()            # lap numbers flagged as pit laps
    weather_samples: tuple[str, ...] = ()        # not stored per-lap; usually empty
    consistency_samples: float = 0.0             # coefficient of variation of lap_samples

    missing_fields: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    source_summary: dict = field(default_factory=dict)

    # -- convenience -----------------------------------------------------
    @property
    def has_laps(self) -> bool:
        return len(self.lap_samples) > 0

    @property
    def clean_lap_count(self) -> int:
        return len(self.lap_samples)

    @property
    def tyre_wear_derived(self) -> bool:
        return bool(self.source_summary.get("tyre_wear_derived"))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_session_strategy_samples(
    db,
    session_id: int,
    *,
    expected_car_id: int = 0,
    expected_track: str = "",
    layout_id: str = "",
    derive_tyre_wear: bool = True,
) -> SessionStrategySamples:
    """Extract strategy samples for one SessionDB session (read-only).

    Parameters
    ----------
    db:
        A SessionDB-like object exposing ``get_session_meta(session_id)`` and
        ``get_session_laps(session_id, exclude_pit=, exclude_out=)``. May be None.
    session_id:
        The session to read. 0/missing → a safe empty result flagged
        ``session_not_found``.
    expected_car_id / expected_track:
        When provided, the session's own car/track are checked against them; a
        mismatch is flagged (``car_track_mismatch``) and NO samples are returned,
        so a strategy is never built from the wrong car's data.
    layout_id:
        Carried through onto the result (SessionDB has no layout column).
    derive_tyre_wear:
        When True (default) derive a tyre-wear proxy from lap-time drift.

    Returns
    -------
    SessionStrategySamples — always valid, never raises.
    """
    try:
        if db is None or not session_id:
            return _empty(session_id, expected_car_id, expected_track, layout_id,
                          [MISS_SESSION, MISS_LAPS, MISS_FUEL, MISS_TYRE, MISS_COMPOUND],
                          ["No SessionDB or session id supplied."])

        meta = None
        try:
            meta = db.get_session_meta(session_id)
        except Exception:
            meta = None

        if not meta:
            return _empty(session_id, expected_car_id, expected_track, layout_id,
                          [MISS_SESSION, MISS_LAPS, MISS_FUEL, MISS_TYRE, MISS_COMPOUND],
                          [f"Session {session_id} not found in SessionDB."])

        car_id = int(meta.get("car_id", 0) or 0)
        track = str(meta.get("track", "") or "")
        config_id = str(meta.get("config_id", "") or "")

        # --- car / track mismatch guard ---
        mismatch = False
        warnings: list[str] = []
        if expected_car_id and car_id and expected_car_id != car_id:
            mismatch = True
            warnings.append(
                f"Session car_id {car_id} does not match expected {expected_car_id}."
            )
        if expected_track and track and _norm(expected_track) != _norm(track):
            mismatch = True
            warnings.append(
                f"Session track '{track}' does not match expected '{expected_track}'."
            )
        if mismatch:
            return _empty(session_id, car_id, track, layout_id,
                          [MISS_CAR_TRACK_MISMATCH, MISS_LAPS, MISS_FUEL,
                           MISS_TYRE, MISS_COMPOUND],
                          warnings,
                          source_summary={"config_id": config_id, "mismatch": True})

        # --- clean laps (exclude pit + out) ---
        clean_rows = _safe_laps(db, session_id, exclude_pit=True, exclude_out=True)
        all_rows = _safe_laps(db, session_id, exclude_pit=False, exclude_out=False)

        lap_samples = tuple(
            r["lap_time_ms"] / 1000.0
            for r in clean_rows
            if _pos(r.get("lap_time_ms"))
        )

        # --- fuel per lap: prefer fuel_used, fall back to fuel_start-fuel_end ---
        fuel_samples = tuple(_lap_fuel(r) for r in clean_rows if _lap_fuel(r) > 0)

        # --- per-compound pace (seconds), session-scoped, clean laps only ---
        compound_samples: dict = {}
        for r in clean_rows:
            comp = str(r.get("compound", "") or "").strip()
            lt = r.get("lap_time_ms")
            if comp and _pos(lt):
                compound_samples.setdefault(comp, []).append(lt / 1000.0)
        compound_samples = {c: tuple(v) for c, v in compound_samples.items()}

        # --- tyre-wear proxy (derived from lap-time drift within a stint) ---
        tyre_derived = False
        tyre_samples: tuple[float, ...] = ()
        if derive_tyre_wear:
            tyre_samples = _derive_tyre_wear(clean_rows)
            tyre_derived = bool(tyre_samples)

        # --- pit laps ---
        pit_samples = tuple(
            int(r.get("lap_num", 0) or 0)
            for r in all_rows
            if int(r.get("is_pit_lap", 0) or 0) == 1
        )

        consistency = _consistency(lap_samples)

        # --- missing-field accounting ---
        missing: list[str] = []
        if not lap_samples:
            missing.append(MISS_LAPS)
        if not fuel_samples:
            missing.append(MISS_FUEL)
        if not tyre_samples:
            missing.append(MISS_TYRE)
        if not compound_samples:
            missing.append(MISS_COMPOUND)

        source_summary = {
            "source": "SessionDB",
            "session_id": session_id,
            "config_id": config_id,
            "clean_lap_count": len(lap_samples),
            "fuel_sample_count": len(fuel_samples),
            "compound_count": len(compound_samples),
            "tyre_wear_derived": tyre_derived,
            "tyre_wear_sample_count": len(tyre_samples),
            "pit_lap_count": len(pit_samples),
        }
        if tyre_derived:
            warnings.append(
                "Tyre-wear is a proxy derived from lap-time drift (SessionDB stores "
                "no explicit tyre-wear signal)."
            )

        return SessionStrategySamples(
            session_id=session_id,
            car_id=car_id,
            track=track,
            layout_id=layout_id,
            lap_samples=lap_samples,
            fuel_samples=fuel_samples,
            tyre_samples=tyre_samples,
            compound_samples=compound_samples,
            pit_samples=pit_samples,
            weather_samples=(),
            consistency_samples=consistency,
            missing_fields=tuple(missing),
            warnings=tuple(warnings),
            source_summary=source_summary,
        )
    except Exception:
        return _empty(session_id, expected_car_id, expected_track, layout_id,
                      [MISS_LAPS, MISS_FUEL, MISS_TYRE, MISS_COMPOUND],
                      ["Unexpected error reading SessionDB; returned empty samples."])


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _empty(
    session_id, car_id, track, layout_id, missing, warnings, source_summary=None
) -> SessionStrategySamples:
    return SessionStrategySamples(
        session_id=int(session_id or 0),
        car_id=int(car_id or 0) if isinstance(car_id, (int, float)) else 0,
        track=str(track or ""),
        layout_id=str(layout_id or ""),
        missing_fields=tuple(missing),
        warnings=tuple(warnings),
        source_summary=source_summary or {"source": "SessionDB", "clean_lap_count": 0},
    )


def _safe_laps(db, session_id, *, exclude_pit, exclude_out) -> list[dict]:
    try:
        rows = db.get_session_laps(
            session_id, exclude_pit=exclude_pit, exclude_out=exclude_out
        )
        return [dict(r) for r in rows] if rows else []
    except Exception:
        return []


def _lap_fuel(row: dict) -> float:
    """Per-lap fuel use: measured fuel_used, else fuel_start-fuel_end, else 0."""
    used = row.get("fuel_used")
    if _pos(used):
        return float(used)
    fs = row.get("fuel_start")
    fe = row.get("fuel_end")
    try:
        if fs is not None and fe is not None:
            delta = float(fs) - float(fe)
            if delta > 0:
                return delta
    except (TypeError, ValueError):
        pass
    return 0.0


def _derive_tyre_wear(clean_rows: list[dict]) -> tuple[float, ...]:
    """Derive per-lap pace-loss increments from within-stint lap-time drift.

    Walks clean laps grouped into consecutive same-compound runs; within each run
    of at least MIN_STINT_LAPS_FOR_WEAR laps, records the positive lap-to-lap
    increases (seconds). Negative deltas (car speeding up on lighter fuel /
    driver improving) contribute nothing. Returns the concatenated increments, or
    an empty tuple when no run is long enough.
    """
    if not clean_rows:
        return ()

    increments: list[float] = []
    run: list[tuple[int, float, str]] = []  # (lap_num, lap_time_s, compound)

    def _flush(r):
        if len(r) < MIN_STINT_LAPS_FOR_WEAR:
            return
        for i in range(1, len(r)):
            d = r[i][1] - r[i - 1][1]
            if d > 0:
                increments.append(round(d, 3))

    prev_lap = None
    prev_comp = None
    for row in clean_rows:
        lt = row.get("lap_time_ms")
        if not _pos(lt):
            continue
        lap_num = int(row.get("lap_num", 0) or 0)
        comp = str(row.get("compound", "") or "").strip()
        contiguous = (prev_lap is None) or (lap_num == prev_lap + 1 and comp == prev_comp)
        if run and not contiguous:
            _flush(run)
            run = []
        run.append((lap_num, lt / 1000.0, comp))
        prev_lap, prev_comp = lap_num, comp
    _flush(run)

    return tuple(increments)


def _consistency(lap_samples: Sequence[float]) -> float:
    try:
        laps = [float(x) for x in lap_samples if float(x) > 0]
        if len(laps) < 2:
            return 0.0
        m = mean(laps)
        return pstdev(laps) / m if m > 0 else 0.0
    except Exception:
        return 0.0


def _pos(x) -> bool:
    try:
        return float(x) > 0.0
    except (TypeError, ValueError):
        return False


def _norm(s: str) -> str:
    return "".join(str(s).lower().split())
