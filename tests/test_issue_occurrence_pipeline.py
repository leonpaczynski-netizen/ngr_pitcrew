"""Sprint 4+5 integration: frames → episodes → occurrences → DB → persistence.

Proves the whole chain composes: the episode extractor collapses many packets
into one episode, the persistence engine only flags same-corner recurrence, and
the additive DB v18 table round-trips occurrences for cross-session analysis.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

from telemetry.slip_events import extract_slip_episodes
from strategy.cross_lap_persistence import (
    occurrence_from_episode, analyse_cross_lap, LapMeta, PersistenceClass,
)
from data.session_db import SessionDB

_TWO_PI = 2.0 * math.pi
_RADIUS = 0.33


def _frame(t_ms, *, throttle, rear_ratio, gear=3, speed_kmh=90.0):
    base = (speed_kmh / 3.6) / (_RADIUS * _TWO_PI)
    rps = (base, base, base * rear_ratio, base * rear_ratio)
    return SimpleNamespace(
        elapsed_ms=t_ms, speed_kmh=speed_kmh, throttle=throttle, brake=0.0,
        gear=gear, rpm=6000.0, road_distance=1500.0,
        wheel_rps=rps, tyre_radius=(_RADIUS,) * 4, suspension=(0.0,) * 4,
        angvel_z=0.1, road_plane_y=1.0,
    )


def _spin_lap():
    # one T3-exit power-on slide sampled as many frames
    return [_frame(i * 10, throttle=1.0, rear_ratio=1.5) for i in range(20)]


def _clean_lap():
    return [_frame(i * 10, throttle=0.3, rear_ratio=1.0) for i in range(20)]


def _seg_resolver(_d, _s, _t, _b):
    return ("T3", "exit")


# --------------------------------------------------------------------------- #
def test_db_schema_is_v18_with_occurrence_table():
    db = SessionDB(":memory:")
    ver = db._conn.execute("PRAGMA user_version").fetchone()[0]
    assert ver >= 18
    # table exists
    row = db._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='corner_issue_occurrences'"
    ).fetchone()
    assert row is not None


def test_occurrence_round_trip_through_db():
    db = SessionDB(":memory:")
    eps = extract_slip_episodes(_spin_lap(), drivetrain="FR", segment_resolver=_seg_resolver)
    occ = [occurrence_from_episode(e, session_id=1, setup_checkpoint_id="cp1",
                                   lap_number=1, track="fuji", layout_id="fuji__full")
           for e in eps]
    n = db.save_issue_occurrences(1, "fuji", "fuji__full", occ)
    assert n == len(occ) >= 1
    rows = db.get_issue_occurrences(1, "fuji", "fuji__full")
    assert len(rows) == n
    assert rows[0]["segment_id"] == "T3"
    assert rows[0]["issue_type"] == "wheelspin"


def test_full_pipeline_persistent_pattern():
    """8 representative laps, T3-exit spin on 6 → PERSISTENT (setup-eligible)."""
    spin_laps = {1, 2, 4, 5, 7, 8}
    occurrences = []
    laps = []
    for lap_no in range(1, 9):
        laps.append(LapMeta(session_id=1, lap_number=lap_no, classification="flying",
                            valid=True, setup_checkpoint_id="cp1"))
        frames = _spin_lap() if lap_no in spin_laps else _clean_lap()
        eps = extract_slip_episodes(frames, drivetrain="FR", segment_resolver=_seg_resolver)
        for e in eps:
            occurrences.append(occurrence_from_episode(
                e, session_id=1, setup_checkpoint_id="cp1", lap_number=lap_no,
                track="fuji", layout_id="fuji__full"))

    results = analyse_cross_lap(occurrences, laps)
    t3 = next((r for r in results if r.signature.segment_id == "T3"), None)
    assert t3 is not None
    assert t3.classification is PersistenceClass.PERSISTENT_PATTERN
    assert t3.affected_representative_laps == 6
    assert t3.eligible_for_setup


def test_full_pipeline_two_bad_laps_not_eligible():
    """Same corner but only 2 of 8 laps → not setup-eligible (the core guard)."""
    spin_laps = {2, 5}
    occurrences, laps = [], []
    for lap_no in range(1, 9):
        laps.append(LapMeta(session_id=1, lap_number=lap_no, classification="flying",
                            valid=True, setup_checkpoint_id="cp1"))
        frames = _spin_lap() if lap_no in spin_laps else _clean_lap()
        eps = extract_slip_episodes(frames, drivetrain="FR", segment_resolver=_seg_resolver)
        for e in eps:
            occurrences.append(occurrence_from_episode(
                e, session_id=1, setup_checkpoint_id="cp1", lap_number=lap_no,
                track="fuji", layout_id="fuji__full"))
    results = analyse_cross_lap(occurrences, laps)
    assert not any(r.eligible_for_setup for r in results)
