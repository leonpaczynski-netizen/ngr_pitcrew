"""Holistic brain — Phase 0 (data foundation) tests.

Covers: the car_id-scoping fix rationale, the batch telemetry reader, the
corner-issue accumulator (roundtrip), and the pure episode->occurrence mapping.
All at the DB/pure layer (no MainWindow), so deterministic and fast.
"""
from __future__ import annotations

import types

from data.session_db import SessionDB
from telemetry.recorder import TelemetryFrame
from strategy.practice_capture import episodes_to_occurrences


def _db(tmp_path):
    return SessionDB(str(tmp_path / "phase0.db"))


def _frame(ms, rd, x, z, thr, brk, gear, spd):
    return TelemetryFrame(
        elapsed_ms=ms, speed_kmh=spd, throttle=thr, brake=brk, gear=gear,
        rpm=8000, road_distance=rd,
        wheel_rps=(0.0, 0.0, 0.0, 0.0), tyre_radius=(0.3, 0.3, 0.3, 0.3),
        suspension=(0.0, 0.0, 0.0, 0.0),
        pos_x=x, pos_y=0.0, pos_z=z)


# --------------------------------------------------------------------------- #
# car_id scoping — the bug: querying with car_id=0 matches nothing
# --------------------------------------------------------------------------- #

def test_car_id_zero_matches_nothing_real_id_works(tmp_path):
    db = _db(tmp_path)
    sid = db.open_session(car_id=7, track="Fuji", session_type="Practice",
                          car_name="RSR")
    db.write_lap(sid, lap_num=1, lap_time_ms=90000, fuel_used=3.0, stats=None,
                 compound="RH", setup_id=1, session_type="Practice")
    db.write_lap(sid, lap_num=2, lap_time_ms=90500, fuel_used=3.0, stats=None,
                 compound="RH", setup_id=1, session_type="Practice")

    # The old bug: car_id=0 -> empty. The fix: the real car_id -> rows.
    assert db.get_setup_comparison(0, "Fuji") == []
    rows = db.get_setup_comparison(7, "Fuji")
    assert rows and rows[0]["setup_id"] == 1 and rows[0]["laps"] == 2
    db.close()


# --------------------------------------------------------------------------- #
# Batch telemetry reader
# --------------------------------------------------------------------------- #

def test_batch_telemetry_reader(tmp_path):
    db = _db(tmp_path)
    sid = db.open_session(car_id=7, track="Fuji", session_type="Practice")
    frames1 = [_frame(0, 100.0, 1.0, 2.0, 0.0, 0.9, 3, 120),
               _frame(100, 110.0, 1.5, 2.5, 0.2, 0.5, 3, 118)]
    frames2 = [_frame(0, 100.0, 1.0, 2.0, 1.0, 0.0, 4, 130)]
    db.write_lap(sid, 1, 90000, 3.0, None, compound="RH", setup_id=1,
                 session_type="Practice", frames=frames1)
    db.write_lap(sid, 2, 89500, 3.0, None, compound="RH", setup_id=1,
                 session_type="Practice", frames=frames2)

    laps = db.get_laps_with_telemetry(7, "Fuji", session_type="Practice")
    assert len(laps) == 2
    # Newest first.
    assert laps[0]["lap_num"] == 2 and len(laps[0]["frames"]) == 1
    assert laps[1]["lap_num"] == 1 and len(laps[1]["frames"]) == 2
    assert laps[1]["frames"][0]["road_distance"] == 100.0
    # Wrong car_id -> nothing.
    assert db.get_laps_with_telemetry(999, "Fuji") == []
    db.close()


# --------------------------------------------------------------------------- #
# Corner-issue accumulator roundtrip (dormant table now populated)
# --------------------------------------------------------------------------- #

def test_issue_occurrence_roundtrip(tmp_path):
    db = _db(tmp_path)
    occ = [
        {"session_id": 1, "lap_number": 3, "segment_id": "t1",
         "corner_phase": "braking", "issue_type": "lockup", "axle": "front",
         "duration_s": 0.4, "severity": 0.3, "throttle": 0.0, "brake": 0.95,
         "speed_kmh": 120.0, "gear": 3, "exclusion_reason": ""},
    ]
    n = db.save_issue_occurrences(7, "Fuji", "full_course", occ)
    assert n == 1
    rows = db.get_issue_occurrences(7, "Fuji", "full_course")
    assert len(rows) == 1
    assert rows[0]["segment_id"] == "t1" and rows[0]["issue_type"] == "lockup"
    assert rows[0]["lap_number"] == 3
    db.close()


# --------------------------------------------------------------------------- #
# Pure episode -> occurrence mapping
# --------------------------------------------------------------------------- #

def test_episodes_to_occurrences_mapping():
    ep = types.SimpleNamespace(
        segment_id="t4", corner_phase="exit", kind="wheelspin",
        subtype="power_wheelspin", axle="rear", duration_s=0.5, max_slip=0.4,
        confidence=0.8, throttle=0.9, brake=0.0, speed_kmh=95.0, gear=2,
        exclusion_reason="", provenance="episode_extractor_v1")
    occ = episodes_to_occurrences([ep], lap_number=5, session_id=11)
    assert len(occ) == 1
    o = occ[0]
    assert o["segment_id"] == "t4" and o["corner_phase"] == "exit"
    assert o["issue_type"] == "wheelspin" and o["issue_subtype"] == "power_wheelspin"
    assert o["axle"] == "rear" and o["severity"] == 0.4
    assert o["lap_number"] == 5 and o["session_id"] == 11
    assert o["throttle"] == 0.9 and o["gear"] == 2

    # Excluded episodes are kept (honest history).
    kerb = types.SimpleNamespace(
        segment_id="t10", corner_phase="exit", kind="wheelspin", subtype="",
        axle="rear", duration_s=0.2, max_slip=0.3, confidence=0.2, throttle=0.9,
        brake=0.0, speed_kmh=90.0, gear=3, exclusion_reason="kerb_unload",
        provenance="episode_extractor_v1")
    occ2 = episodes_to_occurrences([kerb], lap_number=6)
    assert occ2[0]["exclusion_reason"] == "kerb_unload"
