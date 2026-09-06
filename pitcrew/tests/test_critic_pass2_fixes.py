"""The second critic pass on Phase 0, answered: what the race learns about a
stop is written back; the brief and the green agree on a timed race; a refused
plan leaves a trace; the register suffixes are in the pack.
"""
from __future__ import annotations

import json

from pitcrew.race.brief import Instruments, brief
from pitcrew.store.db import Store
from pitcrew.telemetry.session_state import Lap


def _lap(n, *, pit=False, out=False):
    return Lap(lap_num=n, lap_time_ms=100_000, best_lap_ms=100_000, delta_ms=0,
               fuel_start=50.0, fuel_end=45.0, fuel_used=5.0, position=3,
               is_pit_lap=pit, is_out_lap=out)


def _session(tmp_path):
    store = Store(tmp_path / "wb.db")
    event = store.create_event(name="x", track="Daytona International Speedway",
                               layout="Road Course", car_name="c",
                               race_type="laps", race_laps=20)
    session = store.start_session(event, "race", game_version="1.71")
    return store, session


def test_the_resolution_is_written_onto_the_pit_lap_row(tmp_path):
    """Daytona: the line is crossed in the lane, so the pit lap is the lap
    completed AT pit exit; Deep Forest: it is the one after. Either row."""
    store, session = _session(tmp_path)
    try:
        for n in range(1, 15):
            store.add_lap(session, _lap(n, pit=(n == 13), out=(n == 14)))
        assert store.resolve_stop_tyres(session, 12, True) == 13
        row = next(r for r in store.list_laps(session) if r["lap_num"] == 13)
        assert row["tyres_changed"] == 1
        assert store.resolve_stop_tyres(session, 13, False) == 13
        row = next(r for r in store.list_laps(session) if r["lap_num"] == 13)
        assert row["tyres_changed"] == 0
        assert store.resolve_stop_tyres(session, 5, True) is None
        assert store.resolve_stop_tyres(session, None, True) is None
    finally:
        store.close()


def test_the_brief_says_the_same_count_the_green_will():
    said = brief(Instruments(has_plan=True, race_minutes=30.0, stops=1,
                             compounds=("RS", "RS"), laps_estimate=20))
    assert any(line == "About 20 laps on the clock - I'll firm it up as we go."
               for line in said)
    assert not any("stand behind" in line for line in said)


def test_a_timed_race_with_no_plan_still_promises_no_count():
    said = brief(Instruments(has_plan=False, race_minutes=30.0))
    assert any("stand behind" in line for line in said)


def test_a_refused_plan_is_journalled(tmp_path, monkeypatch):
    from pitcrew.mcp import server

    store, _session_id = _session(tmp_path)
    store.close()
    monkeypatch.setattr(server, "_store", lambda: Store(tmp_path / "wb.db"))
    event_id = 1
    reply = json.loads(server.write_strategy(event_id, json.dumps({
        "stops": 1, "stints": [{"laps": 10, "compound": "RS", "fuel_l": 60.0,
                                 "start_lap": 1}]})))
    assert reply["written"] is False
    reply = json.loads(server.write_strategy(event_id, json.dumps({
        "stops": 1, "stints": [{"laps": 10, "compound": "RS", "fuel_l": 60.0,
                                 "start_lap": 1}],
        "playbook": [{"trigger": "incident", "action": "recost_stints",
                      "when": "x"}]})))
    assert reply["written"] is False
    store = Store(tmp_path / "wb.db")
    try:
        rows = store._query("SELECT summary FROM engineer_writes ORDER BY id")
    finally:
        store.close()
    summaries = [r["summary"] for r in rows]
    assert any(s.startswith("refused: no playbook") for s in summaries)
    assert any(s.startswith("refused: ") and "recost_stints" in s
               for s in summaries)


def test_both_register_suffixes_and_the_timed_green_are_in_the_pack():
    from pitcrew.engineer import phrase_manifest as manifest

    clips = set(manifest.clips())
    assert "Suggestion." in clips and "Unconfirmed." in clips
    segments = manifest.segments_for("About 20 laps on the clock.")
    assert segments == ("About", "twenty", "laps on the clock.")
    assert all(name in clips for name in segments)
