"""Group 16 — Phase 2 (per-lap telemetry in practice/strategy prompts).

Tests cover:
  2-D: TelemetryFrame / LapStats have per-corner tyre temp fields; recorder
       computes them from per-frame data; record_frame() injects tyre temps.
  DB:  schema v3 migration adds 4 tyre_temp_*_avg columns; write_lap writes them;
       get_session_laps() supports exclude_pit / exclude_out / limit and returns
       telemetry fields; get_recent_fuel_sequence() and
       get_compound_lap_sequences() return correct data.
  2-A: _build_per_lap_telemetry_block() formats table; included in practice prompt.
  2-B: _build_fuel_trend_block() formats fuel trend; included in race prompt.
  2-C: _build_compound_sequence_block() formats sequences; included in race prompt.
  Dashboard source-scan: _run_practice_analysis captures session_id before thread
       and passes per_lap_telemetry; _run_ai_analysis queries fuel/compound seqs
       and passes them to analyse_strategy.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from dataclasses import fields
from statistics import mean


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _function_body(module_path: str, func_name: str) -> str:
    """Return the source body of a top-level function."""
    import importlib.util, sys
    spec = importlib.util.spec_from_file_location("_mod", module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    fn = getattr(mod, func_name, None)
    if fn is None:
        raise AttributeError(f"{func_name} not found in {module_path}")
    return inspect.getsource(fn)


def _method_body(module_path: str, class_name: str, method_name: str) -> str:
    with open(module_path, encoding="utf-8") as f:
        source = f.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return ast.get_source_segment(source, item) or ""
    raise AttributeError(f"{class_name}.{method_name} not found in {module_path}")


def _module_source(module_path: str) -> str:
    with open(module_path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

import os as _os

_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_RECORDER             = _os.path.join(_ROOT, "telemetry", "recorder.py")
_DB                   = _os.path.join(_ROOT, "data", "session_db.py")
_PLANNER              = _os.path.join(_ROOT, "strategy", "ai_planner.py")
_DASHBOARD            = _os.path.join(_ROOT, "ui", "dashboard.py")
_PRACTICE_ORCH        = _os.path.join(_ROOT, "strategy", "practice_orchestrator.py")
_STRATEGY_ORCH        = _os.path.join(_ROOT, "strategy", "strategy_orchestrator.py")


# ===========================================================================
# TestRecorderTyreTempFields (Phase 2-D)
# ===========================================================================

class TestRecorderTyreTempFields:
    def test_telemetry_frame_has_tyre_temp_fl(self):
        from telemetry.recorder import TelemetryFrame
        assert hasattr(TelemetryFrame, "__dataclass_fields__")
        assert "tyre_temp_fl" in TelemetryFrame.__dataclass_fields__

    def test_telemetry_frame_has_tyre_temp_fr(self):
        from telemetry.recorder import TelemetryFrame
        assert "tyre_temp_fr" in TelemetryFrame.__dataclass_fields__

    def test_telemetry_frame_has_tyre_temp_rl(self):
        from telemetry.recorder import TelemetryFrame
        assert "tyre_temp_rl" in TelemetryFrame.__dataclass_fields__

    def test_telemetry_frame_has_tyre_temp_rr(self):
        from telemetry.recorder import TelemetryFrame
        assert "tyre_temp_rr" in TelemetryFrame.__dataclass_fields__

    def test_tyre_temp_frame_defaults_zero(self):
        from telemetry.recorder import TelemetryFrame
        f = TelemetryFrame(
            elapsed_ms=0, speed_kmh=0, throttle=0, brake=0, gear=1, rpm=0,
            road_distance=0,
            wheel_rps=(0, 0, 0, 0), tyre_radius=(0.3, 0.3, 0.3, 0.3),
            suspension=(0, 0, 0, 0),
        )
        assert f.tyre_temp_fl == 0.0
        assert f.tyre_temp_rr == 0.0

    def test_lap_stats_has_tyre_temp_fl_avg(self):
        from telemetry.recorder import LapStats
        assert "tyre_temp_fl_avg" in LapStats.__dataclass_fields__

    def test_lap_stats_has_all_four_corner_avgs(self):
        from telemetry.recorder import LapStats
        for attr in ("tyre_temp_fl_avg", "tyre_temp_fr_avg",
                     "tyre_temp_rl_avg", "tyre_temp_rr_avg"):
            assert attr in LapStats.__dataclass_fields__, f"{attr} missing from LapStats"

    def test_lap_stats_tyre_temp_defaults_zero(self):
        from telemetry.recorder import LapStats
        ls = LapStats(lap_num=1, lap_time_ms=90000,
                      lock_up_count=0, wheelspin_count=0,
                      brake_consistency_m=-1.0, max_speed_kmh=0.0,
                      avg_throttle_pct=0.0, avg_brake_pct=0.0)
        assert ls.tyre_temp_fl_avg == 0.0
        assert ls.tyre_temp_rr_avg == 0.0


# ===========================================================================
# TestComputeStatsTyreTempAvg (Phase 2-D)
# ===========================================================================

class TestComputeStatsTyreTempAvg:
    """_compute_stats() must compute per-corner averages from frame data."""

    def _make_frame(self, fl, fr, rl, rr):
        from telemetry.recorder import TelemetryFrame
        return TelemetryFrame(
            elapsed_ms=1000, speed_kmh=100, throttle=0.5, brake=0.0,
            gear=4, rpm=6000, road_distance=500.0,
            wheel_rps=(10, 10, 10, 10), tyre_radius=(0.3, 0.3, 0.3, 0.3),
            suspension=(0.01, 0.01, 0.01, 0.01),
            angvel_z=0.0, vel_x=0.0, vel_y=27.7, body_height=0.1,
            tyre_temp_fl=fl, tyre_temp_fr=fr, tyre_temp_rl=rl, tyre_temp_rr=rr,
        )

    def test_tyre_temp_avgs_computed_from_frames(self):
        from telemetry.recorder import _compute_stats
        frames = [self._make_frame(80.0, 82.0, 75.0, 77.0)] * 10
        stats = _compute_stats(frames, lap_num=1, lap_time_ms=90000)
        assert stats.tyre_temp_fl_avg == 80.0
        assert stats.tyre_temp_fr_avg == 82.0
        assert stats.tyre_temp_rl_avg == 75.0
        assert stats.tyre_temp_rr_avg == 77.0

    def test_tyre_temp_avgs_zero_when_no_temp_data(self):
        from telemetry.recorder import _compute_stats
        frames = [self._make_frame(0.0, 0.0, 0.0, 0.0)] * 5
        stats = _compute_stats(frames, lap_num=1, lap_time_ms=90000)
        assert stats.tyre_temp_fl_avg == 0.0

    def test_tyre_temp_avgs_rounded_to_one_decimal(self):
        from telemetry.recorder import _compute_stats
        # frames alternating between 80.0 and 81.0 — avg = 80.5
        frames = [self._make_frame(80.0, 80.0, 80.0, 80.0),
                  self._make_frame(81.0, 81.0, 81.0, 81.0)] * 5
        stats = _compute_stats(frames, lap_num=1, lap_time_ms=90000)
        assert stats.tyre_temp_fl_avg == 80.5


# ===========================================================================
# TestRecordFrameInjectsTyreTemps (Phase 2-D)
# ===========================================================================

class TestRecordFrameInjectsTyreTemps:
    """record_frame() must pass packet tyre temps into TelemetryFrame."""

    def test_record_frame_passes_tyre_temps(self):
        src = _module_source(_RECORDER)
        # The tyre_temp fields must be assigned from packet in record_frame body
        assert "tyre_temp_fl  = packet.tyre_temp_fl" in src or \
               "tyre_temp_fl=packet.tyre_temp_fl" in src

    def test_record_frame_passes_all_four_corners(self):
        src = _module_source(_RECORDER)
        for corner in ("fl", "fr", "rl", "rr"):
            assert f"tyre_temp_{corner}" in src and f"packet.tyre_temp_{corner}" in src


# ===========================================================================
# TestSchemaV3Migration
# ===========================================================================

class TestSchemaV3Migration:
    """Schema version 3 adds per-corner tyre temp average columns."""

    def _make_db(self):
        from data.session_db import SessionDB
        return SessionDB(":memory:")

    def test_v3_columns_exist_on_fresh_db(self):
        db = self._make_db()
        cols = [r[1] for r in db._conn.execute(
            "PRAGMA table_info(lap_records)"
        ).fetchall()]
        for col in ("tyre_temp_fl_avg", "tyre_temp_fr_avg",
                    "tyre_temp_rl_avg", "tyre_temp_rr_avg"):
            assert col in cols, f"{col} missing from lap_records"

    def test_user_version_is_3(self):
        db = self._make_db()
        ver = db._conn.execute("PRAGMA user_version").fetchone()[0]
        assert ver >= 3  # v4 added corner_issues table (Group 17)

    def test_v3_columns_default_zero(self):
        db = self._make_db()
        sid = db.open_session(0, "Suzuka", "practice", "Porsche 911")
        db.write_lap(sid, 1, 90000, 3.0, None)
        row = db._conn.execute(
            "SELECT tyre_temp_fl_avg, tyre_temp_rr_avg FROM lap_records WHERE session_id=?",
            (sid,),
        ).fetchone()
        assert row[0] == 0.0
        assert row[1] == 0.0


# ===========================================================================
# TestWriteLapTyreTempColumns
# ===========================================================================

class TestWriteLapTyreTempColumns:
    def _make_stats_with_temps(self):
        from telemetry.recorder import LapStats
        ls = LapStats(
            lap_num=2, lap_time_ms=91000,
            lock_up_count=1, wheelspin_count=0,
            brake_consistency_m=3.5, max_speed_kmh=240.0,
            avg_throttle_pct=60.0, avg_brake_pct=10.0,
            tyre_temp_fl_avg=78.5,
            tyre_temp_fr_avg=91.2,
            tyre_temp_rl_avg=82.0,
            tyre_temp_rr_avg=88.3,
        )
        ls.lock_up_positions = []
        ls.wheelspin_positions = []
        ls.oversteer_positions = []
        ls.snap_throttle_positions = []
        ls.over_braking_positions = []
        ls.off_track_count = 0
        ls.oversteer_count = 0
        ls.oversteer_throttle_on_count = 0
        ls.kerb_count = 0
        ls.bottoming_count = 0
        ls.snap_throttle_count = 0
        ls.over_braking_count = 0
        ls.abrupt_release_count = 0
        ls.rev_limiter_count = 0
        ls.max_lat_g = 0.0
        ls.tyre_temp_avg = 0.0
        return ls

    def test_write_lap_persists_tyre_temps(self):
        from data.session_db import SessionDB
        db = SessionDB(":memory:")
        sid = db.open_session(0, "Monza", "race", "Ferrari")
        stats = self._make_stats_with_temps()
        db.write_lap(sid, 2, 91000, 2.8, stats)
        row = db._conn.execute(
            "SELECT tyre_temp_fl_avg, tyre_temp_fr_avg, tyre_temp_rl_avg, tyre_temp_rr_avg "
            "FROM lap_records WHERE session_id=?",
            (sid,),
        ).fetchone()
        assert abs(row[0] - 78.5) < 0.01
        assert abs(row[1] - 91.2) < 0.01
        assert abs(row[2] - 82.0) < 0.01
        assert abs(row[3] - 88.3) < 0.01


# ===========================================================================
# TestGetSessionLapsEnhanced
# ===========================================================================

class TestGetSessionLapsEnhanced:
    def _make_db_with_laps(self):
        from data.session_db import SessionDB
        db = SessionDB(":memory:")
        sid = db.open_session(0, "Spa", "practice", "McLaren")
        # Normal laps
        for i in range(1, 4):
            db.write_lap(sid, i, 140000 + i * 100, 3.0, None)
        # Pit lap
        db.write_lap(sid, 4, 150000, 3.0, None, is_pit_lap=True)
        # Out lap
        db.write_lap(sid, 5, 145000, 1.0, None, is_out_lap=True)
        return db, sid

    def test_returns_all_laps_by_default(self):
        db, sid = self._make_db_with_laps()
        rows = db.get_session_laps(sid)
        assert len(rows) == 5

    def test_exclude_pit_removes_pit_lap(self):
        db, sid = self._make_db_with_laps()
        rows = db.get_session_laps(sid, exclude_pit=True)
        assert all(not r["is_pit_lap"] for r in rows)
        assert len(rows) == 4

    def test_exclude_out_removes_out_lap(self):
        db, sid = self._make_db_with_laps()
        rows = db.get_session_laps(sid, exclude_out=True)
        assert all(not r["is_out_lap"] for r in rows)
        assert len(rows) == 4

    def test_exclude_pit_and_out_combined(self):
        db, sid = self._make_db_with_laps()
        rows = db.get_session_laps(sid, exclude_pit=True, exclude_out=True)
        assert len(rows) == 3

    def test_limit_respected(self):
        db, sid = self._make_db_with_laps()
        rows = db.get_session_laps(sid, limit=2)
        assert len(rows) == 2

    def test_telemetry_fields_returned(self):
        db, sid = self._make_db_with_laps()
        rows = db.get_session_laps(sid)
        row = rows[0]
        for col in ("lock_up_count", "wheelspin_count", "oversteer_count",
                    "kerb_count", "max_lat_g",
                    "tyre_temp_fl_avg", "tyre_temp_fr_avg",
                    "tyre_temp_rl_avg", "tyre_temp_rr_avg"):
            assert col in row, f"{col} missing from get_session_laps result"

    def test_ordered_by_lap_num(self):
        db, sid = self._make_db_with_laps()
        rows = db.get_session_laps(sid)
        nums = [r["lap_num"] for r in rows]
        assert nums == sorted(nums)


# ===========================================================================
# TestGetRecentFuelSequence
# ===========================================================================

class TestGetRecentFuelSequence:
    def _make_db(self):
        from data.session_db import SessionDB
        db = SessionDB(":memory:")
        cid = db.upsert_car({"name": "Porsche GT3", "manufacturer": "Porsche"})
        sid = db.open_session(cid, "Nurburgring", "practice", "Porsche GT3")
        for i in range(10):
            db.write_lap(sid, i + 1, 480000 + i * 50, 3.0 + i * 0.1, None)
        # Pit lap — should be excluded
        db.write_lap(sid, 11, 500000, 0.5, None, is_pit_lap=True)
        # Out lap — should be excluded
        db.write_lap(sid, 12, 495000, 0.8, None, is_out_lap=True)
        # Lap with fuel_used = 0 — should be excluded
        db.write_lap(sid, 13, 481000, 0.0, None)
        return db, cid

    def test_returns_chronological_order(self):
        db, cid = self._make_db()
        seq = db.get_recent_fuel_sequence(cid, "Nurburgring", limit=10)
        assert seq == sorted(seq)

    def test_excludes_pit_laps(self):
        db, cid = self._make_db()
        seq = db.get_recent_fuel_sequence(cid, "Nurburgring", limit=15)
        # All values should be >= 3.0 (regular laps); pit lap fuel_used=0.5 excluded
        assert all(v >= 2.9 for v in seq)

    def test_excludes_zero_fuel_laps(self):
        db, cid = self._make_db()
        seq = db.get_recent_fuel_sequence(cid, "Nurburgring", limit=20)
        assert all(v > 0 for v in seq)

    def test_limit_respected(self):
        db, cid = self._make_db()
        seq = db.get_recent_fuel_sequence(cid, "Nurburgring", limit=5)
        assert len(seq) <= 5

    def test_empty_when_no_data(self):
        from data.session_db import SessionDB
        db = SessionDB(":memory:")
        seq = db.get_recent_fuel_sequence(99, "Unknown Track", limit=10)
        assert seq == []


# ===========================================================================
# TestGetCompoundLapSequences
# ===========================================================================

class TestGetCompoundLapSequences:
    def _make_db(self):
        from data.session_db import SessionDB
        db = SessionDB(":memory:")
        cid = db.upsert_car({"name": "GT-R", "manufacturer": "Nissan"})
        sid = db.open_session(cid, "Bathurst", "practice", "GT-R")
        # 5 RM laps, 4 RH laps
        for i in range(5):
            db.write_lap(sid, i + 1, 130000 + i * 200, 3.0, None, compound="RM")
        for i in range(4):
            db.write_lap(sid, i + 6, 132000 + i * 150, 3.2, None, compound="RH")
        # Pit lap — excluded
        db.write_lap(sid, 10, 145000, 0.5, None, compound="RM", is_pit_lap=True)
        return db, cid, sid

    def test_returns_compound_dict(self):
        db, cid, sid = self._make_db()
        seqs = db.get_compound_lap_sequences(cid, "Bathurst")
        assert "RM" in seqs
        assert "RH" in seqs

    def test_rm_sequence_length(self):
        db, cid, sid = self._make_db()
        seqs = db.get_compound_lap_sequences(cid, "Bathurst")
        assert len(seqs["RM"]) == 5

    def test_rh_sequence_length(self):
        db, cid, sid = self._make_db()
        seqs = db.get_compound_lap_sequences(cid, "Bathurst")
        assert len(seqs["RH"]) == 4

    def test_pit_laps_excluded(self):
        db, cid, sid = self._make_db()
        seqs = db.get_compound_lap_sequences(cid, "Bathurst")
        # Only 5 RM laps, not 6 (pit lap excluded)
        assert len(seqs["RM"]) == 5

    def test_session_filter(self):
        db, cid, sid = self._make_db()
        # Second session with same car+track
        sid2 = db.open_session(cid, "Bathurst", "practice", "GT-R")
        db.write_lap(sid2, 1, 131000, 3.0, None, compound="RS")
        # Without filter — RS appears
        seqs_all = db.get_compound_lap_sequences(cid, "Bathurst")
        assert "RS" in seqs_all
        # With session filter — RS not in session 1
        seqs_s1 = db.get_compound_lap_sequences(cid, "Bathurst", session_id=sid)
        assert "RS" not in seqs_s1

    def test_chronological_within_compound(self):
        db, cid, sid = self._make_db()
        seqs = db.get_compound_lap_sequences(cid, "Bathurst")
        rm_times = seqs["RM"]
        assert rm_times == sorted(rm_times)  # earliest laps are fastest here

    def test_empty_when_no_data(self):
        from data.session_db import SessionDB
        db = SessionDB(":memory:")
        seqs = db.get_compound_lap_sequences(99, "Nonexistent")
        assert seqs == {}


# ===========================================================================
# TestFuelTrendBlock (Phase 2-B)
# ===========================================================================

class TestFuelTrendBlock:
    def test_empty_when_no_data(self):
        from strategy.ai_planner import _build_fuel_trend_block
        assert _build_fuel_trend_block([]) == ""

    def test_contains_average(self):
        from strategy.ai_planner import _build_fuel_trend_block
        seq = [3.0, 3.2, 3.1, 3.0, 3.1]
        block = _build_fuel_trend_block(seq)
        assert "Average" in block
        assert "3.08" in block or "3.1" in block  # mean ≈ 3.08

    def test_contains_per_lap_values(self):
        from strategy.ai_planner import _build_fuel_trend_block
        seq = [3.0, 3.1]
        block = _build_fuel_trend_block(seq)
        assert "3.00" in block or "3.0" in block
        assert "3.10" in block or "3.1" in block

    def test_contains_worst_case(self):
        from strategy.ai_planner import _build_fuel_trend_block
        seq = [3.0, 3.2, 3.1, 3.4, 3.0, 3.1]
        block = _build_fuel_trend_block(seq)
        assert "Worst case" in block or "95th" in block

    def test_measured_label(self):
        from strategy.ai_planner import _build_fuel_trend_block
        block = _build_fuel_trend_block([3.0, 3.1, 3.2])
        assert "[measured]" in block

    def test_lap_count_in_header(self):
        from strategy.ai_planner import _build_fuel_trend_block
        block = _build_fuel_trend_block([3.0] * 12)
        assert "12" in block


# ===========================================================================
# TestCompoundSequenceBlock (Phase 2-C)
# ===========================================================================

class TestCompoundSequenceBlock:
    def test_empty_when_no_data(self):
        from strategy.ai_planner import _build_compound_sequence_block
        assert _build_compound_sequence_block({}) == ""

    def test_contains_compound_name(self):
        from strategy.ai_planner import _build_compound_sequence_block
        block = _build_compound_sequence_block({"RM": [90000, 90200, 90400]})
        assert "RM" in block

    def test_contains_lap_times(self):
        from strategy.ai_planner import _build_compound_sequence_block
        block = _build_compound_sequence_block({"RM": [90000, 90200]})
        assert "90.000" in block

    def test_contains_degradation_rate_for_enough_laps(self):
        from strategy.ai_planner import _build_compound_sequence_block
        times = [90000 + i * 200 for i in range(8)]
        block = _build_compound_sequence_block({"RM": times})
        assert "Deg rate" in block

    def test_multiple_compounds(self):
        from strategy.ai_planner import _build_compound_sequence_block
        block = _build_compound_sequence_block({"RM": [90000, 90200], "RH": [92000, 92100]})
        assert "RM" in block and "RH" in block

    def test_lap_count_shown(self):
        from strategy.ai_planner import _build_compound_sequence_block
        block = _build_compound_sequence_block({"RS": [88000, 88500, 89000, 90000]})
        assert "4" in block


# ===========================================================================
# TestPerLapTelemetryBlock (Phase 2-A)
# ===========================================================================

class TestPerLapTelemetryBlock:
    def _make_rows(self, n=3, with_temps=False):
        rows = []
        for i in range(n):
            r = {
                "lap_num": i + 1,
                "lap_time_ms": 90000 + i * 100,
                "fuel_used": 3.1,
                "lock_up_count": i,
                "wheelspin_count": 0,
                "oversteer_count": 1,
                "oversteer_throttle_on": 1,
                "kerb_count": 2,
                "max_lat_g": 2.5,
                "tyre_temp_fl_avg": 80.0 if with_temps else 0.0,
                "tyre_temp_fr_avg": 85.0 if with_temps else 0.0,
                "tyre_temp_rl_avg": 78.0 if with_temps else 0.0,
                "tyre_temp_rr_avg": 83.0 if with_temps else 0.0,
            }
            rows.append(r)
        return rows

    def test_empty_when_no_rows(self):
        from strategy.ai_planner import _build_per_lap_telemetry_block
        assert _build_per_lap_telemetry_block([]) == ""

    def test_contains_header(self):
        from strategy.ai_planner import _build_per_lap_telemetry_block
        block = _build_per_lap_telemetry_block(self._make_rows())
        assert "Per-Lap Telemetry" in block

    def test_contains_lap_num(self):
        from strategy.ai_planner import _build_per_lap_telemetry_block
        block = _build_per_lap_telemetry_block(self._make_rows())
        assert "1" in block

    def test_contains_lock_up_count(self):
        from strategy.ai_planner import _build_per_lap_telemetry_block
        rows = self._make_rows()
        rows[1]["lock_up_count"] = 4
        block = _build_per_lap_telemetry_block(rows)
        assert "4" in block

    def test_tyre_temps_shown_when_present(self):
        from strategy.ai_planner import _build_per_lap_telemetry_block
        block = _build_per_lap_telemetry_block(self._make_rows(with_temps=True))
        assert "80" in block  # FL avg
        assert "85" in block  # FR avg

    def test_tyre_temps_omitted_when_zero(self):
        from strategy.ai_planner import _build_per_lap_telemetry_block
        block = _build_per_lap_telemetry_block(self._make_rows(with_temps=False))
        assert "FL" not in block  # no temp column header

    def test_outlap_note_in_footer(self):
        from strategy.ai_planner import _build_per_lap_telemetry_block
        block = _build_per_lap_telemetry_block(self._make_rows())
        assert "Outlap" in block

    def test_throttle_on_oversteer_notation(self):
        from strategy.ai_planner import _build_per_lap_telemetry_block
        rows = self._make_rows()
        rows[0]["oversteer_count"] = 2
        rows[0]["oversteer_throttle_on"] = 1
        block = _build_per_lap_telemetry_block(rows)
        assert "1T" in block or "(T)" in block or "T" in block


# ===========================================================================
# TestPracticePromptPerLapIntegration (Phase 2-A end-to-end)
# ===========================================================================

class TestPracticePromptPerLapIntegration:
    """Confirm per_lap_telemetry flows from analyse_practice_session signature
    through to _build_practice_prompt."""

    def test_analyse_practice_session_signature_has_per_lap_telemetry(self):
        from strategy.ai_planner import analyse_practice_session
        sig = inspect.signature(analyse_practice_session)
        assert "per_lap_telemetry" in sig.parameters

    def test_build_practice_prompt_signature_has_per_lap_telemetry(self):
        from strategy.ai_planner import _build_practice_prompt
        sig = inspect.signature(_build_practice_prompt)
        assert "per_lap_telemetry" in sig.parameters

    def test_prompt_includes_per_lap_section_when_data_provided(self):
        from strategy.ai_planner import _build_practice_prompt, RaceParams
        params = RaceParams(
            track="Suzuka", total_laps=25, tyre_wear_multiplier=2.0,
            fuel_burn_per_lap=3.0, refuel_speed_lps=10.0, pit_loss_secs=23.0,
        )
        rows = [{"lap_num": 5, "lap_time_ms": 90000, "fuel_used": 3.1,
                 "lock_up_count": 2, "wheelspin_count": 0,
                 "oversteer_count": 0, "oversteer_throttle_on": 0,
                 "kerb_count": 1, "max_lat_g": 2.1,
                 "tyre_temp_fl_avg": 0.0, "tyre_temp_fr_avg": 0.0,
                 "tyre_temp_rl_avg": 0.0, "tyre_temp_rr_avg": 0.0}]
        prompt = _build_practice_prompt(
            params, {"RM": [90000, 90200]}, {}, {},
            per_lap_telemetry=rows,
        )
        assert "Per-Lap Telemetry" in prompt

    def test_prompt_skips_per_lap_section_when_empty(self):
        from strategy.ai_planner import _build_practice_prompt, RaceParams
        params = RaceParams(
            track="Monza", total_laps=20, tyre_wear_multiplier=1.0,
            fuel_burn_per_lap=2.5, refuel_speed_lps=10.0, pit_loss_secs=22.0,
        )
        prompt = _build_practice_prompt(
            params, {"RM": [88000]}, {}, {},
            per_lap_telemetry=[],
        )
        assert "Per-Lap Telemetry" not in prompt


# ===========================================================================
# TestRacePromptFuelAndCompound (Phase 2-B/C end-to-end)
# ===========================================================================

class TestRacePromptFuelAndCompound:
    def test_analyse_strategy_signature_has_fuel_sequence(self):
        from strategy.ai_planner import analyse_strategy
        sig = inspect.signature(analyse_strategy)
        assert "fuel_sequence" in sig.parameters

    def test_analyse_strategy_signature_has_compound_sequences(self):
        from strategy.ai_planner import analyse_strategy
        sig = inspect.signature(analyse_strategy)
        assert "compound_sequences" in sig.parameters

    def test_build_race_prompt_signature_has_fuel_sequence(self):
        from strategy.ai_planner import _build_race_prompt
        sig = inspect.signature(_build_race_prompt)
        assert "fuel_sequence" in sig.parameters

    def test_build_race_prompt_signature_has_compound_sequences(self):
        from strategy.ai_planner import _build_race_prompt
        sig = inspect.signature(_build_race_prompt)
        assert "compound_sequences" in sig.parameters

    def test_race_prompt_includes_fuel_trend_when_data(self):
        from strategy.ai_planner import _build_race_prompt, RaceParams
        params = RaceParams(
            track="Spa", total_laps=44, tyre_wear_multiplier=1.5,
            fuel_burn_per_lap=3.2, refuel_speed_lps=10.0, pit_loss_secs=24.0,
        )
        prompt = _build_race_prompt(
            params, {"RM": [102000, 102500]}, None,
            fuel_sequence=[3.1, 3.2, 3.0, 3.3, 3.1],
        )
        assert "Fuel Trend" in prompt

    def test_race_prompt_includes_compound_seq_when_data(self):
        from strategy.ai_planner import _build_race_prompt, RaceParams
        params = RaceParams(
            track="Spa", total_laps=44, tyre_wear_multiplier=1.5,
            fuel_burn_per_lap=3.2, refuel_speed_lps=10.0, pit_loss_secs=24.0,
        )
        prompt = _build_race_prompt(
            params, {"RM": [102000, 102500]}, None,
            compound_sequences={"RM": [102000, 102200, 102400]},
        )
        assert "Degradation Sequences" in prompt

    def test_race_prompt_omits_fuel_trend_when_empty(self):
        from strategy.ai_planner import _build_race_prompt, RaceParams
        params = RaceParams(
            track="Spa", total_laps=44, tyre_wear_multiplier=1.5,
            fuel_burn_per_lap=3.2, refuel_speed_lps=10.0, pit_loss_secs=24.0,
        )
        prompt = _build_race_prompt(
            params, {"RM": [102000]}, None,
            fuel_sequence=[],
        )
        assert "Fuel Trend" not in prompt


# ===========================================================================
# TestDashboardWiring (source scan)
# ===========================================================================

class TestDashboardWiring:
    def test_run_practice_analysis_captures_session_id(self):
        src = _method_body(_DASHBOARD, "MainWindow", "_run_practice_analysis")
        assert "_hist_session_id" in src
        assert "_dispatcher._session_id" in src

    def test_run_practice_analysis_passes_per_lap_telemetry(self):
        # Logic moved to practice_orchestrator after refactor
        src = _module_source(_PRACTICE_ORCH)
        assert "per_lap_telemetry" in src

    def test_run_practice_analysis_calls_get_session_laps_with_exclude_params(self):
        # Logic moved to practice_orchestrator after refactor
        src = _module_source(_PRACTICE_ORCH)
        assert "get_session_laps" in src
        assert "exclude_pit" in src
        assert "exclude_out" in src

    def test_run_ai_analysis_queries_fuel_sequence(self):
        # Logic moved to strategy_orchestrator after refactor
        src = _module_source(_STRATEGY_ORCH)
        assert "get_recent_fuel_sequence" in src or "fuel_seq" in src

    def test_run_ai_analysis_queries_compound_sequences(self):
        # Logic moved to strategy_orchestrator after refactor
        src = _module_source(_STRATEGY_ORCH)
        assert "get_compound_lap_sequences" in src or "compound_seqs" in src

    def test_run_ai_analysis_passes_fuel_sequence_to_analyse_strategy(self):
        # Logic moved to strategy_orchestrator after refactor
        src = _module_source(_STRATEGY_ORCH)
        assert "fuel_sequence" in src

    def test_run_ai_analysis_passes_compound_sequences_to_analyse_strategy(self):
        # Logic moved to strategy_orchestrator after refactor
        src = _module_source(_STRATEGY_ORCH)
        assert "compound_sequences" in src
