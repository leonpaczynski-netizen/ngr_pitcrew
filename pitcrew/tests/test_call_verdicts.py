"""1.6: a verdict per call, judged as the laps come in, persisted and exported;
the board's positions on file at every crossing."""
from __future__ import annotations

from types import SimpleNamespace

from pitcrew.race.call_outcome import (ACTED, CANNOT_TELL, NOT_ACTED, judge,
                                       outcome_for)
from pitcrew.race.calls import BOX_NOW, FUEL_SHORT, TYRE_TEMP, Call


def _laps(*pit_laps, upto):
    return [SimpleNamespace(lap_num=n, is_pit_lap=(n in pit_laps),
                            short_shift_rpm=None) for n in range(1, upto + 1)]


def test_a_box_call_is_open_until_its_window_is_driven():
    call = Call(BOX_NOW, 10, "Box this lap.", "")
    assert outcome_for(call, _laps(upto=10)).settled is False
    assert outcome_for(call, _laps(upto=11)).settled is False
    done = outcome_for(call, _laps(upto=13))
    assert done.settled and done.verdict == NOT_ACTED
    acted = outcome_for(call, _laps(11, upto=11))
    assert acted.settled and acted.verdict == ACTED


def test_a_kind_nothing_can_answer_is_settled_at_once():
    call = Call(TYRE_TEMP, 4, "Tyres are cold.", "")
    outcome = outcome_for(call, _laps(upto=4))
    assert outcome.verdict == CANNOT_TELL and outcome.settled


def test_judge_returns_only_what_can_be_settled_unless_final():
    box = Call(BOX_NOW, 10, "Box this lap.", "")
    temp = Call(TYRE_TEMP, 10, "Tyres are cold.", "")
    filed = [(1, box), (2, temp)]
    keys = [k for k, _ in judge(filed, _laps(upto=10))]
    assert keys == [2], "the box window is not driven yet"
    keys = [k for k, _ in judge(filed, _laps(upto=10), final=True)]
    assert keys == [1, 2], "the flag settles the open one as it stands"
    keys = [k for k, _ in judge(filed, _laps(11, upto=11))]
    assert keys == [1, 2]


def test_a_short_shift_call_waits_for_the_next_lap():
    call = Call(FUEL_SHORT, 6, "Short-shift.", "", short_shift_drop_rpm=400.0)
    laps = [SimpleNamespace(lap_num=6, is_pit_lap=False, short_shift_rpm=None)]
    assert outcome_for(call, laps).settled is False
    laps.append(SimpleNamespace(lap_num=7, is_pit_lap=False,
                                short_shift_rpm=400.0))
    assert outcome_for(call, laps).verdict == ACTED


def test_the_verdict_is_on_the_row_and_in_the_export(tmp_path):
    from pitcrew.export.build import _calls_made
    from pitcrew.store.db import Store

    store = Store(tmp_path / "v.db")
    try:
        event_id = store.create_event(name="x", track="Deep Forest Raceway",
                                      layout="Full Course", car_name="car",
                                      race_type="laps", race_laps=20)
        session_id = store.start_session(event_id, "race")
        run_id = store.start_race_run(event_id, None, session_id)
        rid = store.append_revision(run_id, 10, "Box this lap.",
                                    {"kind": BOX_NOW, "confidence": "high"})
        assert store.list_revisions(run_id)[0]["verdict"] is None
        store.set_revision_verdict(rid, ACTED, "pitted on lap 11")
        row = store.list_revisions(run_id)[0]
        assert (row["verdict"], row["verdict_detail"]) == (ACTED,
                                                           "pitted on lap 11")
        made = _calls_made(store, event_id)
        assert made and made[0]["verdict"] == ACTED
        assert made[0]["verdictDetail"] == "pitted on lap 11"
    finally:
        store.close()


def test_board_positions_are_filed_per_crossing(tmp_path):
    from pitcrew.store.db import Store

    store = Store(tmp_path / "b.db")
    try:
        event_id = store.create_event(name="x", track="Deep Forest Raceway",
                                      layout="Full Course", car_name="car",
                                      race_type="laps", race_laps=20)
        session_id = store.start_session(event_id, "race")
        assert store.record_board_positions(session_id, 3,
                                            {"Boxhead": 2, "Beeni": 3}) == 2
        assert store.record_board_positions(session_id, 4, {}) == 0
        assert store.record_board_positions(None, 4, {"Boxhead": 2}) == 0
        rows = store.board_positions(session_id)
        assert [(r["lap"], r["driver"], r["position"]) for r in rows] == [
            (3, "Boxhead", 2), (3, "Beeni", 3)]
    finally:
        store.close()
