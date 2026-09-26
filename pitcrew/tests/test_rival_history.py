"""Tests for rival_history.py — brief_rival_history.md §4 + coordinator fixes.

Tests:
* mark_session_debriefed (MCP tool): sets debriefed_at; repeated call is
  idempotent.
* Due logic: debriefed, 14 days, still running, not ended, rehearsal, practice.
  Only the right ones are due.
* RH-I5: sessions ended < 10 minutes ago are not due.
* Normalisation: positions, gaps, stops with fills, a left-view stop, a rival
  barely in view.  History rows match hand-computed values; NULLs where data
  is missing.
* RH-I2: a driver present only in board_reads (not in board_positions or
  rival_stops) still gets a history row before those reads are deleted.
* places_gained sign: positive = net gain, s188 ZenPhilosopher P8→P6 = +2.
* race_laps_run stored for timed races; fractions computed from it.
* burn_assumed / start_basis flagging (rule 5): first stop flags the assumption.
* Fill verdict: matches the monitor's for the same stop.
* RH-M3: stop_count NULL when no board evidence; 0 when board coverage but no
  stops seen.
* Idempotency: re-running changes nothing.
* Deletion: only board_reads and name_resolutions for due sessions are deleted.
  Every other table and every other session is untouched.
* RH-I1: normalise + verify + delete is one transaction; injected failure rolls
  everything back.
* Failure safety: if normalisation raises, nothing is deleted.
* Renames: rename_driver and rename_driver_session rewrite rival_race_history.
* Profile: history_profile aggregates across two or more races with counts.
  gap_slope_races_n is race count (RH-I4); burn_assumed_n reported separately.
* RH-I3: board_secs_in_view computed from at_s timestamps, not 1s-per-read.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

import pytest

os.environ.setdefault("PITCREW_DB", ":not-a-real-path:")  # guard against live DB

from pitcrew.race.fill_verdict import _rival_verdict, derive_stop_burn
from pitcrew.race.rival_history import (
    _count_pit_windows,
    _secs_in_view_from_reads,
    cleanup_due_sessions,
    history_profile,
    is_race_session_due,
    normalise_session,
)
from pitcrew.store.db import Store


# ---------------------------------------------------------------------------
# Helpers to build a minimal synthetic session
# ---------------------------------------------------------------------------

def _make_store(tmp_path: Path) -> Store:
    return Store(tmp_path / "test.db")


_EVENT_COUNTER = 0


def _make_race_session(store: Store, *, ended: bool = True,
                       rehearsal: bool = False,
                       debriefed: bool = False,
                       kind: str = "race",
                       ended_ago_days: int = 0,
                       race_type: str = "laps",
                       race_laps: int = 20) -> tuple[int, int]:
    """Return (event_id, session_id)."""
    global _EVENT_COUNTER
    _EVENT_COUNTER += 1
    event_id = store.create_event(
        name=f"Test Race {_EVENT_COUNTER}",
        track="Autodromo Nazionale Monza",
        layout="Full Course",
        car_id=None,
        car_name="Porsche 911 RSR",
        race_type=race_type,
        race_laps=race_laps,
        tyre_wear_mult="3x",
        fuel_mult="3x",
    )
    session_id = store.start_session(event_id, kind, rehearsal=rehearsal)
    if ended:
        if ended_ago_days:
            ts = (datetime.datetime.utcnow()
                  - datetime.timedelta(days=ended_ago_days)
                  ).strftime("%Y-%m-%dT%H:%M:%S")
            store.end_session(session_id, at=ts)
        else:
            store.end_session(session_id)
    if debriefed:
        store.mark_session_debriefed(session_id)
    return event_id, session_id


def _seed_board_positions(store: Store, session_id: int) -> None:
    """Rocky: P3 on lap 1, P2 on lap 10, P2 on lap 20."""
    store.record_board_positions(session_id, 1, {"Rocky": 3})
    store.record_board_positions(session_id, 10, {"Rocky": 2})
    store.record_board_positions(session_id, 20, {"Rocky": 2})


def _seed_rival_stop(store: Store, session_id: int, *,
                     driver: str = "Rocky",
                     lap: int = 10,
                     laps_total: int = 20,
                     fuel_in_l: float = 42.0,
                     fuel_out_l: float = 76.0,
                     partial: bool = False,
                     left_view: bool = False) -> int:
    return store.record_rival_stop(
        session_id, driver, lap=lap, laps_total=laps_total,
        fuel_in_l=fuel_in_l, fuel_out_l=fuel_out_l,
        compound="RS", compound_in="RS",
        reads=30, watched_s=25.0,
        partial=partial, left_view=left_view,
        assumed_start_l=100.0,
    )


def _seed_board_reads(store: Store, session_id: int, driver: str = "Rocky",
                      n_pit: int = 25, n_normal: int = 100) -> None:
    """Seed board_reads with some pit rows and some normal rows."""
    rows = []
    base_s = 1000.0
    for i in range(n_normal):
        rows.append({
            "session_id": session_id,
            "at_s": base_s + i,
            "lap": i // 10,
            "position": 3,
            "cluster_id": "1",
            "name": driver,
            "name_source": "handle",
            "pit_columns": 0,
            "fuel_l": None,
            "compound": None,
        })
    # Add a pit window at the end.
    for i in range(n_pit):
        rows.append({
            "session_id": session_id,
            "at_s": base_s + n_normal + i,
            "lap": 10,
            "position": 3,
            "cluster_id": "1",
            "name": driver,
            "name_source": "handle",
            "pit_columns": 1,
            "fuel_l": None,
            "compound": None,
        })
    store.record_board_reads(session_id, rows)


def _seed_laps(store: Store, session_id: int, lap_count: int) -> None:
    """Seed the laps table with `lap_count` dummy laps (direct SQL)."""
    with store._write() as conn:
        for i in range(1, lap_count + 1):
            conn.execute(
                "INSERT INTO laps "
                "(session_id, lap_num, lap_time_ms, delta_ms, "
                "fuel_start, fuel_end, fuel_used, position, recorded_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (session_id, i, 90000, 0, 80.0, 70.0, 10.0, 3,
                 "2026-09-26T12:00:00"),
            )


# ---------------------------------------------------------------------------
# 1. Marking
# ---------------------------------------------------------------------------

class TestMarkSessionDebriefed:
    def test_sets_debriefed_at(self, tmp_path):
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store, ended=True)
        changed = store.mark_session_debriefed(sid)
        assert changed is True
        row = store.get_session(sid)
        assert row["debriefed_at"] is not None

    def test_idempotent(self, tmp_path):
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store, ended=True)
        store.mark_session_debriefed(sid)
        first_at = store.get_session(sid)["debriefed_at"]
        changed = store.mark_session_debriefed(sid)
        assert changed is False
        # timestamp unchanged
        assert store.get_session(sid)["debriefed_at"] == first_at

    def test_records_engineer_write(self, tmp_path):
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store, ended=True)
        store.mark_session_debriefed(sid, note="full debrief done")
        writes = store.list_engineer_writes(kind="session_debrief")
        assert len(writes) == 1
        assert writes[0]["target_id"] == sid

    def test_mcp_tool_marks_and_is_idempotent(self, tmp_path):
        """The MCP tool wraps mark_session_debriefed."""
        import json as _json
        import os as _os
        _os.environ["PITCREW_DB"] = str(tmp_path / "test.db")
        try:
            from pitcrew.mcp import server as mcp_server
            store2 = Store(tmp_path / "test.db")
            eid = store2.create_event(
                name="MCP Test", track="Monza", layout="Full Course",
                car_id=None, car_name="Car", race_type="laps", race_laps=10,
                tyre_wear_mult="3x", fuel_mult="3x")
            sid = store2.start_session(eid, "race")
            store2.end_session(sid)
            store2.close()

            result = _json.loads(mcp_server.mark_session_debriefed(sid))
            assert result["marked"] is True

            result2 = _json.loads(mcp_server.mark_session_debriefed(sid))
            assert result2["marked"] is False
        finally:
            _os.environ.pop("PITCREW_DB", None)


# ---------------------------------------------------------------------------
# 2. Due logic
# ---------------------------------------------------------------------------

NOW = datetime.datetime(2026, 9, 26, 12, 0, 0)


def _sess(*, kind="race", rehearsal=0, ended=True,
          compacted=False, debriefed=False,
          ended_days_ago: int = 0) -> dict:
    ended_at = None
    if ended:
        delta = datetime.timedelta(days=ended_days_ago)
        ended_at = (NOW - delta).strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "kind": kind,
        "rehearsal": rehearsal,
        "ended_at": ended_at,
        "history_compacted_at": "2026-09-25" if compacted else None,
        "debriefed_at": "2026-09-25" if debriefed else None,
    }


class TestDueLogic:
    def test_debriefed_race_is_due(self):
        due, reason = is_race_session_due(_sess(debriefed=True, ended_days_ago=1), [], NOW)
        assert due is True
        assert reason == "debriefed"

    def test_fourteen_days_fallback(self):
        due, reason = is_race_session_due(_sess(ended_days_ago=14), [], NOW)
        assert due is True
        assert "days" in reason

    def test_thirteen_days_not_yet_due(self):
        due, _ = is_race_session_due(_sess(ended_days_ago=13), [], NOW)
        assert due is False

    def test_not_ended_never_due(self):
        due, _ = is_race_session_due(_sess(ended=False), [], NOW)
        assert due is False

    def test_still_running(self):
        """A session with no ended_at is never due."""
        due, _ = is_race_session_due(_sess(ended=False, debriefed=True), [], NOW)
        assert due is False

    def test_rehearsal_never_due(self):
        due, _ = is_race_session_due(_sess(rehearsal=1, debriefed=True, ended_days_ago=1), [], NOW)
        assert due is False

    def test_practice_never_due(self):
        due, _ = is_race_session_due(_sess(kind="practice", debriefed=True, ended_days_ago=1), [], NOW)
        assert due is False

    def test_already_compacted_not_due(self):
        due, _ = is_race_session_due(_sess(debriefed=True, compacted=True, ended_days_ago=1), [], NOW)
        assert due is False

    def test_rhi5_min_age_guard_blocks_recent_session(self):
        """RH-I5: a session ended just now is not due even if debriefed."""
        # ended_at == NOW — age is 0, well below the 10-minute guard.
        sess = {
            "kind": "race",
            "rehearsal": 0,
            "ended_at": NOW.strftime("%Y-%m-%dT%H:%M:%S"),
            "history_compacted_at": None,
            "debriefed_at": "2026-09-25",
        }
        due, _ = is_race_session_due(sess, [], NOW)
        assert due is False

    def test_rhi5_min_age_guard_passes_after_ten_minutes(self):
        """RH-I5: a session ended 11 minutes ago IS due (if debriefed)."""
        ended = NOW - datetime.timedelta(minutes=11)
        sess = {
            "kind": "race",
            "rehearsal": 0,
            "ended_at": ended.strftime("%Y-%m-%dT%H:%M:%S"),
            "history_compacted_at": None,
            "debriefed_at": "2026-09-25",
        }
        due, reason = is_race_session_due(sess, [], NOW)
        assert due is True
        assert reason == "debriefed"


# ---------------------------------------------------------------------------
# 3. Normalisation
# ---------------------------------------------------------------------------

class TestNormalisation:
    def test_basic_row_written(self, tmp_path):
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        _seed_board_positions(store, sid)
        _seed_rival_stop(store, sid)
        n = normalise_session(store, sid)
        assert n == 1
        rows = store.rival_race_history(session_id=sid)
        assert len(rows) == 1
        r = rows[0]
        assert r["driver"] == "Rocky"
        assert r["stop_count"] == 1
        assert r["start_position"] == 3
        assert r["finish_position"] == 2
        assert r["best_position"] == 2
        assert r["worst_position"] == 3

    def test_places_gained_positive_for_net_gain(self, tmp_path):
        """s188 ZenPhilosopher P8→P6: gained 2 → places_gained = +2.

        This is the real-data case from the coordinator's report.
        start - finish = 8 - 6 = 2 (positive = moved forward).
        """
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        store.record_board_positions(sid, 1, {"ZenPhilosopher": 8})
        store.record_board_positions(sid, 20, {"ZenPhilosopher": 6})
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid)
        r = rows[0]
        assert r["places_gained"] == 2   # +2: gained 2 positions

    def test_places_gained_negative_when_losing_positions(self, tmp_path):
        """P1 → P3: lost 2 places → places_gained = 1 - 3 = -2."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        store.record_board_positions(sid, 1, {"Rocky": 1})
        store.record_board_positions(sid, 20, {"Rocky": 3})
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid)
        assert rows[0]["places_gained"] == -2   # lost 2 positions

    def test_places_gained_not_clamped(self, tmp_path):
        """Negative places_gained stored as-is (rule 9)."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        store.record_board_positions(sid, 1, {"Rocky": 1})
        store.record_board_positions(sid, 20, {"Rocky": 3})
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid)
        # -2: lost 2 places; not clamped to 0
        assert rows[0]["places_gained"] == -2

    def test_best_worst_position_correct(self, tmp_path):
        """best_position = lowest number (P1 is best); worst = highest."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        for lap, pos in [(1, 5), (5, 3), (10, 7), (20, 4)]:
            store.record_board_positions(sid, lap, {"Rocky": pos})
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid)
        r = rows[0]
        assert r["best_position"] == 3   # min
        assert r["worst_position"] == 7  # max

    def test_stop_json_contains_fill_verdict(self, tmp_path):
        """stops_json includes a fill_verdict for the stop."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        _seed_board_positions(store, sid)
        _seed_rival_stop(store, sid, fuel_in_l=42.0, fuel_out_l=76.0,
                         lap=10, laps_total=20)
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid)
        stops = json.loads(rows[0]["stops_json"])
        assert len(stops) == 1
        s = stops[0]
        assert s["fill_verdict"] is not None
        assert s["fill_verdict"] != "can't tell"

    def test_fill_verdict_matches_monitor(self, tmp_path):
        """The fill verdict in history must match _rival_verdict directly."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        _seed_board_positions(store, sid)
        _seed_rival_stop(store, sid, fuel_in_l=42.0, fuel_out_l=76.0,
                         lap=10, laps_total=20)
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid)
        stop = json.loads(rows[0]["stops_json"])[0]

        # Compute burn using the shared helper — same path as normalise.
        stop_row = {"fuel_in_l": 42.0, "lap": 10, "assumed_start_l": 100.0}
        burn, _assumed, _basis = derive_stop_burn(stop_row, None, capacity_l=None)
        expected = _rival_verdict(
            76.0, burn, 10, 20,
            partial=False, exit_is_a_bound=False,
        )
        assert stop["fill_verdict"] == expected.verdict

    def test_first_stop_burn_assumed_flagged(self, tmp_path):
        """A first stop using 100 L assumption sets burn_assumed=True (rule 5)."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        _seed_rival_stop(store, sid, fuel_in_l=42.0)
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid)
        stop = json.loads(rows[0]["stops_json"])[0]
        assert stop["burn_assumed"] is True
        assert stop["start_basis"] == "assumed_start_l"  # from assumed_start_l=100

    def test_first_stop_no_assumed_start_uses_100l(self, tmp_path):
        """Without assumed_start_l on the row, 100 L is the fallback."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        # Record a stop without assumed_start_l
        store.record_rival_stop(
            sid, "Ghost", lap=10, laps_total=20,
            fuel_in_l=42.0, fuel_out_l=76.0,
            compound="RS", compound_in="RS",
            reads=10, watched_s=20.0,
            partial=False, assumed_start_l=None,
        )
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid, driver="Ghost")
        stop = json.loads(rows[0]["stops_json"])[0]
        assert stop["burn_assumed"] is True
        assert stop["start_basis"] == "100 L assumed"

    def test_consecutive_stop_burn_not_assumed(self, tmp_path):
        """Second stop derives burn from consecutive stops — burn_assumed=False."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store, race_laps=30)
        # Stop 1: lap 10, fuel_out 70
        store.record_rival_stop(
            sid, "Rocky", lap=10, laps_total=30,
            fuel_in_l=42.0, fuel_out_l=70.0,
            compound="RS", compound_in="RS",
            reads=20, watched_s=20.0,
            partial=False, assumed_start_l=100.0,
        )
        # Stop 2: lap 20, fuel_in 30 (burned 40 in 10 laps = 4 L/lap)
        store.record_rival_stop(
            sid, "Rocky", lap=20, laps_total=30,
            fuel_in_l=30.0, fuel_out_l=70.0,
            compound="RS", compound_in="RS",
            reads=20, watched_s=20.0,
            partial=False, assumed_start_l=None,
        )
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid)
        stops = json.loads(rows[0]["stops_json"])
        assert len(stops) == 2
        # First stop: assumed
        assert stops[0]["burn_assumed"] is True
        # Second stop: consecutive measurement
        assert stops[1]["burn_assumed"] is False
        assert stops[1]["start_basis"] is None
        assert stops[1]["burn_per_lap_l"] == pytest.approx(4.0)  # (70-30)/10

    def test_no_position_data_gives_null_positions(self, tmp_path):
        """A rival seen only in rival_stops (not on board) has null positions."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        _seed_rival_stop(store, sid, driver="Ghost")
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid, driver="Ghost")
        r = rows[0]
        assert r["start_position"] is None
        assert r["finish_position"] is None
        assert r["places_gained"] is None

    def test_left_view_stop_recorded(self, tmp_path):
        """A left-view stop gets a row with left_view=True in stops_json."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        _seed_rival_stop(store, sid, left_view=True)
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid)
        stops = json.loads(rows[0]["stops_json"])
        assert stops[0]["left_view"] is True

    def test_driver_barely_seen_has_low_evidence(self, tmp_path):
        """A rival with 2 board reads has board_reads_n = 2."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        _seed_rival_stop(store, sid, driver="Ghost")
        # Only 2 board_reads rows for Ghost.
        store.record_board_reads(session_id=sid, rows=[
            {"session_id": sid, "at_s": 1.0, "lap": 1, "position": 5,
             "cluster_id": "2", "name": "Ghost", "name_source": "handle",
             "pit_columns": 0, "fuel_l": None, "compound": None},
            {"session_id": sid, "at_s": 2.0, "lap": 1, "position": 5,
             "cluster_id": "2", "name": "Ghost", "name_source": "handle",
             "pit_columns": 0, "fuel_l": None, "compound": None},
        ])
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid, driver="Ghost")
        assert rows[0]["board_reads_n"] == 2

    def test_no_rivals_returns_zero(self, tmp_path):
        """A session with no board data and no stops normalises to 0 rows."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        n = normalise_session(store, sid)
        assert n == 0

    def test_idempotent_normalisation(self, tmp_path):
        """Running normalise_session twice produces the same rows."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        _seed_board_positions(store, sid)
        _seed_rival_stop(store, sid)
        normalise_session(store, sid)
        first = store.rival_race_history(session_id=sid)
        normalise_session(store, sid)
        second = store.rival_race_history(session_id=sid)
        assert len(first) == len(second) == 1
        assert first[0]["stop_count"] == second[0]["stop_count"]
        assert first[0]["places_gained"] == second[0]["places_gained"]


# ---------------------------------------------------------------------------
# 4. race_laps_run
# ---------------------------------------------------------------------------

class TestRaceLapsRun:
    def test_laps_race_stores_race_laps_run(self, tmp_path):
        """For a laps race, race_laps_run = actual laps recorded."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store, race_laps=20)
        _seed_laps(store, sid, 20)
        _seed_rival_stop(store, sid)
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid)
        assert rows[0]["race_laps_run"] == 20

    def test_timed_race_uses_run_laps_for_fraction(self, tmp_path):
        """Timed race: race_laps=50 (cap) but only 29 laps actually run.
        lap_fraction must be computed against 29, not 50.
        """
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store, race_type="time", race_laps=50)
        # Only 29 laps recorded in laps table.
        _seed_laps(store, sid, 29)
        # Rocky stops on lap 14 (of 29 actual).
        _seed_rival_stop(store, sid, lap=14, laps_total=29)
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid)
        r = rows[0]
        assert r["race_laps_run"] == 29
        stop = json.loads(r["stops_json"])[0]
        # lap_fraction = 14 / 29 ≈ 0.483
        assert stop["lap_fraction"] == pytest.approx(14 / 29, rel=1e-4)

    def test_timed_race_wrong_fraction_without_fix(self, tmp_path):
        """Without the fix, lap_fraction would be 14/50=0.28 (wrong)."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store, race_type="time", race_laps=50)
        _seed_laps(store, sid, 29)
        _seed_rival_stop(store, sid, lap=14, laps_total=29)
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid)
        stop = json.loads(rows[0]["stops_json"])[0]
        # Should NOT be 14/50.
        assert stop["lap_fraction"] != pytest.approx(14 / 50, rel=1e-2)

    def test_no_laps_table_falls_back_to_race_laps(self, tmp_path):
        """When no laps are recorded, falls back to event's race_laps."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store, race_laps=20)
        _seed_rival_stop(store, sid, lap=10, laps_total=20)
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid)
        r = rows[0]
        # race_laps_run is None (no laps recorded)
        assert r["race_laps_run"] is None
        # lap_fraction falls back to race_laps = 20
        stop = json.loads(r["stops_json"])[0]
        assert stop["lap_fraction"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# 5. Cleanup (deletion)
# ---------------------------------------------------------------------------

class TestCleanup:
    def _seed_full_session(self, store: Store, *, ended_days_ago=1,
                           debriefed=False) -> tuple[int, int]:
        # Default ended_days_ago=1: session must be > 10 minutes old (RH-I5).
        _eid, sid = _make_race_session(store, ended=True,
                                       debriefed=debriefed,
                                       ended_ago_days=ended_days_ago)
        _seed_board_positions(store, sid)
        _seed_rival_stop(store, sid)
        _seed_board_reads(store, sid)
        store.record_name_resolution(
            session_id=sid, cluster_id="1",
            name="Rocky", source="handle", score=None,
            votes=5, at_s=1.0)
        return _eid, sid

    def test_only_due_sessions_are_cleaned(self, tmp_path):
        store = _make_store(tmp_path)
        # A session due for cleanup (debriefed).
        _eid1, sid1 = self._seed_full_session(store, debriefed=True)
        # A session NOT due (ended only 1 day ago, not debriefed).
        _eid2, sid2 = self._seed_full_session(store, ended_days_ago=1)

        br_before_1 = len(store._query(
            "SELECT id FROM board_reads WHERE session_id=?", (sid1,)))
        br_before_2 = len(store._query(
            "SELECT id FROM board_reads WHERE session_id=?", (sid2,)))
        assert br_before_1 > 0
        assert br_before_2 > 0

        cleanup_due_sessions(store, now=NOW)

        br_after_1 = len(store._query(
            "SELECT id FROM board_reads WHERE session_id=?", (sid1,)))
        br_after_2 = len(store._query(
            "SELECT id FROM board_reads WHERE session_id=?", (sid2,)))

        assert br_after_1 == 0           # deleted
        assert br_after_2 == br_before_2  # untouched

    def test_board_positions_untouched(self, tmp_path):
        """board_positions is NOT deleted by cleanup."""
        store = _make_store(tmp_path)
        _eid, sid = self._seed_full_session(store, debriefed=True)
        bp_before = len(store.board_positions(sid))
        cleanup_due_sessions(store, now=NOW)
        bp_after = len(store.board_positions(sid))
        assert bp_after == bp_before

    def test_rival_stops_untouched(self, tmp_path):
        """rival_stops is NOT deleted by cleanup."""
        store = _make_store(tmp_path)
        _eid, sid = self._seed_full_session(store, debriefed=True)
        rs_before = len(store.rival_stops(session_id=sid))
        cleanup_due_sessions(store, now=NOW)
        rs_after = len(store.rival_stops(session_id=sid))
        assert rs_after == rs_before

    def test_name_resolutions_deleted(self, tmp_path):
        store = _make_store(tmp_path)
        _eid, sid = self._seed_full_session(store, debriefed=True)
        nr_before = len(store._query(
            "SELECT id FROM name_resolutions WHERE session_id=?", (sid,)))
        assert nr_before > 0
        cleanup_due_sessions(store, now=NOW)
        nr_after = len(store._query(
            "SELECT id FROM name_resolutions WHERE session_id=?", (sid,)))
        assert nr_after == 0

    def test_history_rows_written_before_deletion(self, tmp_path):
        """Cleanup writes history rows first, then deletes."""
        store = _make_store(tmp_path)
        _eid, sid = self._seed_full_session(store, debriefed=True)
        cleanup_due_sessions(store, now=NOW)
        rows = store.rival_race_history(session_id=sid)
        assert len(rows) == 1
        assert rows[0]["driver"] == "Rocky"

    def test_history_compacted_at_is_set(self, tmp_path):
        store = _make_store(tmp_path)
        _eid, sid = self._seed_full_session(store, debriefed=True)
        cleanup_due_sessions(store, now=NOW)
        sess = store.get_session(sid)
        assert sess["history_compacted_at"] is not None

    def test_not_run_twice(self, tmp_path):
        """Once history_compacted_at is set, cleanup does not run again."""
        store = _make_store(tmp_path)
        _eid, sid = self._seed_full_session(store, debriefed=True)
        cleanup_due_sessions(store, now=NOW)
        # Re-seed board_reads and run again — they should not be deleted.
        _seed_board_reads(store, sid)
        br_after_seed = len(store._query(
            "SELECT id FROM board_reads WHERE session_id=?", (sid,)))
        assert br_after_seed > 0
        cleanup_due_sessions(store, now=NOW)
        br_second_run = len(store._query(
            "SELECT id FROM board_reads WHERE session_id=?", (sid,)))
        assert br_second_run == br_after_seed  # untouched by second run

    def test_failure_safety(self, tmp_path, monkeypatch):
        """If row-collection raises, nothing is deleted.

        RH-I1: _run_cleanup_for_session now calls _collect_all_rows (not
        normalise_session) to build rows.  Patching that is the correct
        injection point.
        """
        store = _make_store(tmp_path)
        _eid, sid = self._seed_full_session(store, debriefed=True)
        br_before = len(store._query(
            "SELECT id FROM board_reads WHERE session_id=?", (sid,)))

        import pitcrew.race.rival_history as rh
        monkeypatch.setattr(rh, "_collect_all_rows",
                            lambda *a, **kw: (_ for _ in ()).throw(
                                RuntimeError("boom")))
        cleanup_due_sessions(store, now=NOW)

        br_after = len(store._query(
            "SELECT id FROM board_reads WHERE session_id=?", (sid,)))
        assert br_after == br_before   # nothing deleted
        sess = store.get_session(sid)
        assert sess["history_compacted_at"] is None

    def test_rhi1_transaction_rollback_on_mid_upsert_failure(
            self, tmp_path, monkeypatch):
        """RH-I1: if an upsert fails mid-way, the whole transaction rolls back.

        We seed two distinct rivals so there are two upserts.  The second
        upsert raises.  After cleanup, board_reads must be untouched and
        history_compacted_at must be NULL.
        """
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store, ended=True, debriefed=True,
                                       ended_ago_days=1)
        # Seed two drivers in board_positions.
        store.record_board_positions(sid, 1, {"Rocky": 3, "Ghost": 5})
        store.record_board_positions(sid, 10, {"Rocky": 2, "Ghost": 6})
        _seed_board_reads(store, sid)

        import pitcrew.race.rival_history as rh

        call_count = {"n": 0}
        original_upsert = rh._upsert_row_conn

        def failing_upsert(conn, session_id, driver, row):
            call_count["n"] += 1
            if call_count["n"] >= 2:
                raise RuntimeError("injected second-upsert failure")
            return original_upsert(conn, session_id, driver, row)

        monkeypatch.setattr(rh, "_upsert_row_conn", failing_upsert)
        cleanup_due_sessions(store, now=NOW)

        br_after = len(store._query(
            "SELECT id FROM board_reads WHERE session_id=?", (sid,)))
        assert br_after > 0               # nothing deleted
        sess = store.get_session(sid)
        assert sess["history_compacted_at"] is None   # not marked done


# ---------------------------------------------------------------------------
# 6. Renames carry through
# ---------------------------------------------------------------------------

class TestRenames:
    def test_global_rename_rewrites_history(self, tmp_path):
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        _seed_board_positions(store, sid)
        _seed_rival_stop(store, sid)
        normalise_session(store, sid)
        store.rename_driver("Rocky", "K.Rocky")
        rows = store.rival_race_history(driver="K.Rocky")
        assert len(rows) == 1
        assert len(store.rival_race_history(driver="Rocky")) == 0

    def test_session_rename_rewrites_history(self, tmp_path):
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        _seed_board_positions(store, sid)
        _seed_rival_stop(store, sid)
        normalise_session(store, sid)
        store.rename_driver_session(sid, "Rocky", "K.Rocky")
        rows = store.rival_race_history(session_id=sid, driver="K.Rocky")
        assert len(rows) == 1
        assert len(store.rival_race_history(session_id=sid, driver="Rocky")) == 0


# ---------------------------------------------------------------------------
# 7. Profile
# ---------------------------------------------------------------------------

class TestHistoryProfile:
    def _two_race_setup(self, tmp_path) -> tuple[Store, str]:
        store = _make_store(tmp_path)
        driver = "Rocky"
        for i in range(2):
            _eid, sid = _make_race_session(store, race_laps=20)
            _seed_laps(store, sid, 20)
            store.record_board_positions(sid, 1, {driver: 3})
            store.record_board_positions(sid, 20, {driver: 2})
            _seed_rival_stop(store, sid, driver=driver,
                             lap=10, laps_total=20,
                             fuel_in_l=42.0, fuel_out_l=76.0)
            normalise_session(store, sid)
        return store, driver

    def test_profile_has_race_count(self, tmp_path):
        store, driver = self._two_race_setup(tmp_path)
        prof = history_profile(store, driver)
        assert prof["races_n"] == 2

    def test_profile_stop_frac_is_a_median(self, tmp_path):
        store, driver = self._two_race_setup(tmp_path)
        prof = history_profile(store, driver)
        assert prof["stop_lap_frac"] == pytest.approx(0.5)  # lap 10 / laps 20
        assert prof["stop_lap_frac_n"] == 2

    def test_profile_fill_habits_sum_to_one(self, tmp_path):
        store, driver = self._two_race_setup(tmp_path)
        prof = history_profile(store, driver)
        if prof["fill_habits"] is not None:
            assert abs(sum(prof["fill_habits"].values()) - 1.0) < 0.01

    def test_profile_empty_for_unknown_driver(self, tmp_path):
        store = _make_store(tmp_path)
        prof = history_profile(store, "Nobody")
        assert prof["races_n"] == 0
        assert prof["stop_lap_frac"] is None

    def test_profile_counts_not_zero_for_missing_data(self, tmp_path):
        """Rule 4: every aggregate carries its count. None for empty, not 0."""
        store = _make_store(tmp_path)
        prof = history_profile(store, "Nobody")
        # stop_lap_frac_n is 0 (we have 0 stops, that is a count).
        assert prof["stop_lap_frac_n"] == 0

    def test_gap_slope_races_n_is_race_count(self, tmp_path):
        """RH-I4: gap_slope_races_n reports count of races with a slope.

        It is NOT the sum of per-race gap_slope_n (which is lap count).
        """
        store = _make_store(tmp_path)
        driver = "Rocky"
        # Create history rows with gap_slope directly via upsert.
        for i in range(3):
            _eid, sid = _make_race_session(store)
            store.upsert_rival_race_history(sid, driver, {
                "start_position": 3, "finish_position": 2,
                "best_position": 2, "worst_position": 3,
                "places_gained": 1, "places_gained_n": 10,
                "laps_observed": 10,
                "gap_slope_s_per_lap": 0.5 + i * 0.1,
                "gap_slope_n": 8,   # per-race lap count — not summed in profile
                "stops_json": None, "stop_count": 0,
                "pit_stops_board_unseen": None,
                "board_reads_n": None, "board_secs_in_view": None,
            })
        prof = history_profile(store, driver)
        # 3 races contributed a slope → gap_slope_races_n = 3 (not 8+8+8=24).
        assert prof["gap_slope_races_n"] == 3
        assert prof["gap_slope_mean_s_per_lap"] == pytest.approx(0.6)

    def test_gap_slope_null_when_no_rows_have_it(self, tmp_path):
        """If no history rows carry a slope, profile returns None/None."""
        store = _make_store(tmp_path)
        driver = "Ghost"
        _eid, sid = _make_race_session(store)
        store.upsert_rival_race_history(sid, driver, {
            "start_position": None, "finish_position": None,
            "best_position": None, "worst_position": None,
            "places_gained": None, "places_gained_n": None,
            "laps_observed": None,
            "gap_slope_s_per_lap": None,
            "gap_slope_n": None,
            "stops_json": None, "stop_count": None,
            "pit_stops_board_unseen": None,
            "board_reads_n": None, "board_secs_in_view": None,
        })
        prof = history_profile(store, driver)
        assert prof["gap_slope_mean_s_per_lap"] is None
        assert prof["gap_slope_races_n"] is None

    def test_burn_assumed_n_counted(self, tmp_path):
        """burn_assumed_n counts assumed-start burns from stops_json."""
        store = _make_store(tmp_path)
        driver = "Rocky"
        _eid, sid = _make_race_session(store, race_laps=20)
        _seed_rival_stop(store, sid, driver=driver, lap=10, laps_total=20,
                         fuel_in_l=42.0)
        normalise_session(store, sid)
        prof = history_profile(store, driver)
        assert prof["burn_assumed_n"] == 1

    def test_places_gained_mean_positive_for_gainer(self, tmp_path):
        """P8→P6 across two races: mean places_gained = 2."""
        store = _make_store(tmp_path)
        driver = "ZenPhilosopher"
        for _ in range(2):
            _eid, sid = _make_race_session(store)
            store.record_board_positions(sid, 1, {driver: 8})
            store.record_board_positions(sid, 20, {driver: 6})
            normalise_session(store, sid)
        prof = history_profile(store, driver)
        assert prof["places_gained_mean"] == pytest.approx(2.0)
        assert prof["places_gained_n"] == 2


# ---------------------------------------------------------------------------
# 8. _count_pit_windows helper
# ---------------------------------------------------------------------------

class TestCountPitWindows:
    def test_none_on_empty(self):
        assert _count_pit_windows([]) is None

    def test_no_pit_rows(self):
        rows = [{"at_s": i, "pit_columns": 0} for i in range(10)]
        assert _count_pit_windows(rows) is None

    def test_one_window(self):
        rows = (
            [{"at_s": i, "pit_columns": 0} for i in range(5)] +
            [{"at_s": 5 + i, "pit_columns": 1} for i in range(20)] +
            [{"at_s": 25 + i, "pit_columns": 0} for i in range(5)]
        )
        assert _count_pit_windows(rows) == 1

    def test_two_windows_separated(self):
        rows = (
            [{"at_s": i, "pit_columns": 1} for i in range(10)] +
            [{"at_s": 100 + i, "pit_columns": 1} for i in range(10)]
        )
        assert _count_pit_windows(rows) == 2


# ---------------------------------------------------------------------------
# 9. derive_stop_burn shared helper
# ---------------------------------------------------------------------------

class TestDeriveStopBurn:
    def test_first_stop_uses_assumed_start(self):
        stop = {"fuel_in_l": 42.0, "lap": 10, "assumed_start_l": 100.0}
        burn, assumed, basis = derive_stop_burn(stop, None, None)
        assert burn == pytest.approx((100.0 - 42.0) / 10)
        assert assumed is True
        assert basis == "assumed_start_l"

    def test_first_stop_fallback_100l(self):
        stop = {"fuel_in_l": 42.0, "lap": 10}
        burn, assumed, basis = derive_stop_burn(stop, None, None)
        assert burn == pytest.approx((100.0 - 42.0) / 10)
        assert assumed is True
        assert basis == "100 L assumed"

    def test_first_stop_capacity_fallback(self):
        stop = {"fuel_in_l": 42.0, "lap": 10}
        burn, assumed, basis = derive_stop_burn(stop, None, capacity_l=80.0)
        assert burn == pytest.approx((80.0 - 42.0) / 10)
        assert assumed is True
        assert basis == "capacity"

    def test_consecutive_stops_not_assumed(self):
        prev = {"fuel_out_l": 70.0, "lap": 10}
        cur = {"fuel_in_l": 30.0, "lap": 20}
        burn, assumed, basis = derive_stop_burn(cur, prev, None)
        assert burn == pytest.approx(4.0)  # (70-30) / 10
        assert assumed is False
        assert basis is None

    def test_negative_burn_returns_none(self):
        # fuel_in > prev_fuel_out → negative burn (rule 9)
        prev = {"fuel_out_l": 30.0, "lap": 10}
        cur = {"fuel_in_l": 40.0, "lap": 20}
        burn, assumed, basis = derive_stop_burn(cur, prev, None)
        assert burn is None

    def test_electric_car_returns_none(self):
        stop = {"fuel_in_l": 0.0, "lap": 10}
        burn, assumed, basis = derive_stop_burn(stop, None, capacity_l=0)
        assert burn is None


# ---------------------------------------------------------------------------
# 10. RH-I2: driver seen only in board_reads gets a history row
# ---------------------------------------------------------------------------

class TestBoardReadsOnlyDriver:
    def test_board_reads_only_driver_has_history_row(self, tmp_path):
        """RH-I2: a rival present only in board_reads (not in board_positions
        or rival_stops) must still receive a history row so that his evidence
        is not lost when board_reads is deleted during cleanup.
        """
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        # "Rocky" only appears in board_reads, never in board_positions.
        store.record_board_reads(session_id=sid, rows=[
            {"session_id": sid, "at_s": 1.0, "lap": 1, "position": 4,
             "cluster_id": "5", "name": "Rocky", "name_source": "handle",
             "pit_columns": 0, "fuel_l": None, "compound": None},
            {"session_id": sid, "at_s": 2.0, "lap": 1, "position": 4,
             "cluster_id": "5", "name": "Rocky", "name_source": "handle",
             "pit_columns": 0, "fuel_l": None, "compound": None},
        ])
        n = normalise_session(store, sid)
        assert n == 1
        rows = store.rival_race_history(session_id=sid, driver="Rocky")
        assert len(rows) == 1
        r = rows[0]
        # No position data (not in board_positions).
        assert r["start_position"] is None
        assert r["finish_position"] is None
        # But board_reads evidence IS preserved.
        assert r["board_reads_n"] == 2

    def test_phantom_names_from_board_reads_excluded(self, tmp_path):
        """RH-I2: phantom handles like 'Car #3' must not produce history rows."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        store.record_board_reads(session_id=sid, rows=[
            {"session_id": sid, "at_s": 1.0, "lap": 1, "position": 4,
             "cluster_id": "9", "name": "Car #3", "name_source": "handle",
             "pit_columns": 0, "fuel_l": None, "compound": None},
        ])
        n = normalise_session(store, sid)
        assert n == 0  # no real drivers

    def test_verify_includes_board_reads_only_driver(self, tmp_path):
        """RH-I2: _collect_all_rows includes board_reads-only drivers so the
        verify count in cleanup matches, and their rows aren't falsely missed.
        """
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store, ended=True, debriefed=True,
                                       ended_ago_days=1)
        # "Lurker" is only in board_reads.
        store.record_board_reads(session_id=sid, rows=[
            {"session_id": sid, "at_s": 100.0, "lap": 5, "position": 8,
             "cluster_id": "7", "name": "Lurker", "name_source": "handle",
             "pit_columns": 0, "fuel_l": None, "compound": None},
            {"session_id": sid, "at_s": 101.0, "lap": 5, "position": 8,
             "cluster_id": "7", "name": "Lurker", "name_source": "handle",
             "pit_columns": 0, "fuel_l": None, "compound": None},
        ])
        cleanup_due_sessions(store, now=NOW)
        # History row was written for Lurker.
        rows = store.rival_race_history(session_id=sid, driver="Lurker")
        assert len(rows) == 1
        # Cleanup completed successfully.
        assert store.get_session(sid)["history_compacted_at"] is not None


# ---------------------------------------------------------------------------
# 11. RH-I3: board_secs_in_view computed from timestamps
# ---------------------------------------------------------------------------

class TestSecsInView:
    def test_none_on_empty(self):
        assert _secs_in_view_from_reads([]) is None

    def test_none_on_single_read(self):
        assert _secs_in_view_from_reads([{"at_s": 1.0}]) is None

    def test_uniform_intervals(self):
        """10 reads at 0.5 s apart = 9 intervals of 0.5 s = 4.5 s total."""
        rows = [{"at_s": i * 0.5} for i in range(10)]
        result = _secs_in_view_from_reads(rows)
        assert result == pytest.approx(4.5)

    def test_gap_is_capped(self):
        """A 10-second gap between two reads is capped at 2× median interval.

        Reads: 0.0, 0.5, 10.5, 11.0.
        Intervals: 0.5, 10.0, 0.5.  Median = 0.5, cap = 1.0.
        Total = 0.5 + min(10.0, 1.0) + 0.5 = 2.0.
        """
        rows = [{"at_s": s} for s in [0.0, 0.5, 10.5, 11.0]]
        result = _secs_in_view_from_reads(rows)
        assert result == pytest.approx(2.0)

    def test_stored_on_history_row(self, tmp_path):
        """board_secs_in_view on a history row reflects timestamp-based calc."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        # 5 reads at exactly 0.5 s apart → 4 intervals of 0.5 s = 2.0 s.
        store.record_board_reads(session_id=sid, rows=[
            {"session_id": sid, "at_s": float(i) * 0.5,
             "lap": 1, "position": 4, "cluster_id": "1",
             "name": "Rocky", "name_source": "handle",
             "pit_columns": 0, "fuel_l": None, "compound": None}
            for i in range(5)
        ])
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid, driver="Rocky")
        assert rows[0]["board_secs_in_view"] == pytest.approx(2.0)

    def test_not_one_s_per_read(self, tmp_path):
        """board_secs_in_view is NOT simply board_reads_n seconds (old model)."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        # 5 reads at 0.25 s apart → 4 intervals of 0.25 s = 1.0 s.
        # Old model would give 5 s (one second per read).
        store.record_board_reads(session_id=sid, rows=[
            {"session_id": sid, "at_s": float(i) * 0.25,
             "lap": 1, "position": 4, "cluster_id": "1",
             "name": "Rocky", "name_source": "handle",
             "pit_columns": 0, "fuel_l": None, "compound": None}
            for i in range(5)
        ])
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid, driver="Rocky")
        secs = rows[0]["board_secs_in_view"]
        # Must be ~1.0 s (from timestamps), NOT 5.0 s (old 1-per-read model).
        assert secs == pytest.approx(1.0)
        assert secs != pytest.approx(5.0, rel=0.1)


# ---------------------------------------------------------------------------
# 12. RH-M3: stop_count NULL when no board evidence
# ---------------------------------------------------------------------------

class TestStopCountNullNoEvidence:
    def test_stop_count_null_when_no_board_evidence(self, tmp_path):
        """RH-M3: rival seen only in rival_stops (no board) → stop_count NULL.

        We have stop data, but no board_positions or board_reads for this
        driver.  We cannot confirm stops from the board, so stop_count = NULL.
        """
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        # Ghost only appears in rival_stops, never on the board.
        store.record_rival_stop(
            sid, "Ghost", lap=10, laps_total=20,
            fuel_in_l=42.0, fuel_out_l=76.0,
            compound="RS", compound_in="RS",
            reads=10, watched_s=20.0,
            partial=False, assumed_start_l=None,
        )
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid, driver="Ghost")
        assert rows[0]["stop_count"] is None  # no board evidence → NULL

    def test_stop_count_zero_when_board_present_no_stops(self, tmp_path):
        """RH-M3: rival seen on board but no rival_stops → stop_count = 0."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        store.record_board_positions(sid, 1, {"Rocky": 3})
        # No rival_stops for Rocky.
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid, driver="Rocky")
        assert rows[0]["stop_count"] == 0  # board coverage, no stops seen

    def test_stop_count_value_when_stops_and_board_present(self, tmp_path):
        """RH-M3: rival seen on board with 1 stop → stop_count = 1."""
        store = _make_store(tmp_path)
        _eid, sid = _make_race_session(store)
        store.record_board_positions(sid, 1, {"Rocky": 3})
        _seed_rival_stop(store, sid, driver="Rocky")
        normalise_session(store, sid)
        rows = store.rival_race_history(session_id=sid, driver="Rocky")
        assert rows[0]["stop_count"] == 1
