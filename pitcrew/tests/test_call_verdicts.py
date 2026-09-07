"""1.6: a verdict per call, judged as the laps come in, persisted and exported;
the board's positions on file at every crossing."""
from __future__ import annotations

import pathlib
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


def test_a_short_shift_call_is_not_answered_by_the_lap_it_was_made_on():
    """Critic pass 8: `_laps_after` includes the call's own lap, so a driver
    already short-shifting when the call came read "acted - short-shifting
    recorded on lap 6" about the lap the instruction was given ON."""
    call = Call(FUEL_SHORT, 6, "Short-shift.", "", short_shift_drop_rpm=400.0)
    laps = [SimpleNamespace(lap_num=6, is_pit_lap=False,
                            short_shift_rpm=400.0)]
    assert outcome_for(call, laps).settled is False
    laps.append(SimpleNamespace(lap_num=7, is_pit_lap=False,
                                short_shift_rpm=None))
    outcome = outcome_for(call, laps)
    assert outcome.verdict == NOT_ACTED and outcome.settled


def test_the_verdict_reaches_the_payload_and_not_only_the_entry(tmp_path):
    """Critic pass 8's blocker. `_calls_made` carried the field and the
    section builder projected `callsMade[]` down to a fixed key list that did
    not include it, so it reached no file - and widening that list alone
    would have made `_validate_known_keys` refuse the whole export, costing
    the driver everything rather than one field. Three places: the
    projection, `payload.KNOWN_KEYS` and EXPORT-CONTRACT §10."""
    from pitcrew.export.payload import KNOWN_KEYS, _validate_known_keys

    keys = KNOWN_KEYS["strategy.callsMade[]"]
    assert {"verdict", "verdictDetail"} <= keys
    entry = {"lap": 10, "call": "Box this lap.", "reason": "fuel",
             "accepted": None, "disposition": "taken", "confidence": "high",
             "verdict": ACTED, "verdictDetail": "pitted on lap 11"}
    assert _validate_known_keys({"strategy": {"callsMade": [entry]}}) == []
    contract = (pathlib.Path(__file__).resolve().parents[2]
                / "EXPORT-CONTRACT.md").read_text(encoding="utf-8")
    assert "verdictDetail" in contract
    assert "unanswered" in contract
    # **The header a consumer reads first, not just the §16 heading.**
    from pitcrew.export.payload import FORMAT

    assert FORMAT in contract.splitlines()[0]
    assert f'"format": "{FORMAT}"' in contract


def test_the_disposition_of_an_instruction_comes_from_the_verdict():
    """Rule 13, critic pass 8: the two answered the same question two ways -
    the older derivation pools pit laps over EVERY race session of the event,
    rehearsals included, while the verdict is judged against the laps of the
    session the call was made in.

    **And `cannot-tell` does NOT fall through** (critic pass 8, second
    round). It means the window was never fully driven in that race, so the
    same session cannot have supplied a stop in it - a `taken` from the
    fallback could only come from another run's lap, in another numbering,
    and would contradict the verdict beside it in the same object."""
    from pitcrew.export.build import _disposition

    def rev(verdict=None):
        return {"lap_num": 10, "accepted": 0, "verdict": verdict,
                "plan": {"kind": BOX_NOW}}

    assert _disposition(rev(ACTED), set()) == ("taken", None)
    assert _disposition(rev(NOT_ACTED), {11}) == ("not-taken", None)
    assert _disposition(rev(CANNOT_TELL), {11}) == ("unanswered", None)
    # No verdict at all - a row from before 1.9 - is the only fall-through.
    assert _disposition(rev(), {11}) == ("taken", None)


def test_the_verdict_is_on_the_row_and_in_the_export(tmp_path):
    from pitcrew.export.build import _calls_made
    from pitcrew.store.db import Store

    store = Store(tmp_path / "v.db")
    try:
        event_id = store.create_event(name="x", track="Deep Forest Raceway",
                                      layout="Full Course", car_name="car",
                                      race_type="laps", race_laps=20)
        strategy_id = store.save_strategy(
            event_id, {"export": {"stops": 1, "totalRaceTimeS": 1800.0}})
        store.approve_strategy(strategy_id)
        session_id = store.start_session(event_id, "race")
        run_id = store.start_race_run(event_id, strategy_id, session_id)
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
        # **And past the projection**, which is where it stopped: the entry
        # carried the field and `callsMade[]` was built from a fixed key
        # list that dropped it, so it reached no file (critic pass 8).
        from pitcrew.export.build import _strategy_section

        section = _strategy_section(store, event_id)
        assert section and section["callsMade"]
        assert section["callsMade"][0]["verdict"] == ACTED
        assert section["callsMade"][0]["verdictDetail"] == "pitted on lap 11"
        # The bookkeeping keys still stay out.
        assert "kind" not in section["callsMade"][0]
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


# ----------------------------------- the controller half, which was hand-placed

def _controller_source() -> str:
    return (pathlib.Path(__file__).resolve().parents[1] / "controller.py"
            ).read_text(encoding="utf-8")


def test_the_filed_calls_cannot_outlive_their_session():
    """Critic pass 8's second blocker, CLAUDE.md rule 11. `stop_race` did not
    clear `_filed_calls` and `_judge_filed_calls` runs at every crossing of
    every session kind - so a race whose flag was never detected (the Fuji
    failure, on file) left box calls held, and the first PRACTICE crossing
    afterwards judged them against practice laps."""
    source = _controller_source()
    assert "self._filed_session = self.session_id" in source
    assert "if self._filed_session != self.session_id:" in source
    assert "are dropped unjudged" in source
    # Built in __init__ as well, so no reader has to guess whether it exists.
    assert "self._filed_calls: dict = {}" in source
    # And Stop settles what is open before the session id it is judged
    # against goes: a race ended with the button is the class this is for.
    start = source.index("    def stop_race(self)")
    end = source.index("\n    def ", start + 10)
    assert "_judge_filed_calls(final=True)" in source[start:end]
    assert "self._filed_calls = {}" in source[start:end]


class _FakeStore:
    """Just enough store to drive `_judge_filed_calls`."""

    def __init__(self, laps, *, fail_on=()):
        self._laps = laps
        self._fail_on = set(fail_on)
        self.written = []

    def list_laps(self, session_id):
        return self._laps

    def set_revision_verdict(self, rid, verdict, detail):
        if rid in self._fail_on:
            raise RuntimeError("database is locked")
        self.written.append((rid, verdict, detail))


def _stub(laps, filed, *, fail_on=()):
    from pitcrew.controller import PitCrewController

    controller = PitCrewController.__new__(PitCrewController)
    controller.session_id = 5
    controller._filed_session = 5
    controller._filed_calls = dict(filed)
    controller.race_screen = None
    controller.store = _FakeStore(laps, fail_on=fail_on)
    return controller


def _row(lap_num, *, pit=False, excluded=0):
    return {"lap_num": lap_num, "is_pit_lap": pit, "short_shift_rpm": None,
            "excluded": excluded}


def test_a_verdict_is_written_before_the_call_is_dropped():
    """Critic pass 8: popped first, a locked database lost that call's
    verdict for good AND aborted the rest of the loop into a log line that
    named none of them. Driven, not read off the source."""
    box = Call(BOX_NOW, 10, "Box this lap.", "")
    temp = Call(TYRE_TEMP, 10, "Tyres are cold.", "")
    laps = [_row(n) for n in range(10, 14)]
    controller = _stub(laps, {1: (box, None), 2: (temp, None)}, fail_on={1})
    controller._judge_filed_calls()
    # The one that could not be written is still filed, and the other landed.
    assert set(controller._filed_calls) == {1}
    assert [rid for rid, *_ in controller.store.written] == [2]
    # And it lands on the next crossing, once the database lets it.
    controller.store._fail_on = set()
    controller._judge_filed_calls()
    assert controller._filed_calls == {}
    assert [rid for rid, *_ in controller.store.written] == [2, 1]


def test_a_struck_lap_is_not_evidence_that_the_window_was_driven():
    """Critic pass 8, second round. Moving the judging past the fragment
    check stopped the phantom row's OWN crossing from judging - and the next
    crossing judged with the phantom still in `list_laps`, which is
    `SELECT *`. Box call on lap 12, laps 12 and 13 driven, a phantom 14: the
    window read as full and "no stop on laps 12-14" was written and settled
    about a stop he made on the next lap he actually drove."""
    box = Call(BOX_NOW, 12, "Box this lap.", "")
    laps = [_row(12), _row(13), _row(14, excluded=1)]
    controller = _stub(laps, {1: (box, None)})
    controller._judge_filed_calls()
    assert controller.store.written == [], "nothing to say yet"
    assert set(controller._filed_calls) == {1}, "and it stays open"
    # The lap he actually drove, and it is the stop.
    controller.store._laps = laps + [_row(14, pit=True)]
    controller._judge_filed_calls()
    assert [(v, d) for _, v, d in controller.store.written] == [
        (ACTED, "pitted on lap 14, 2 lap(s) after the call")]


def test_calls_from_another_session_are_dropped_not_judged():
    """CLAUDE.md rule 11: a race whose flag was never detected left box calls
    held, and the first crossing of the next session judged them against ITS
    laps."""
    box = Call(BOX_NOW, 10, "Box this lap.", "")
    controller = _stub([_row(n) for n in range(10, 14)], {1: (box, None)})
    controller._filed_session = 4                # a previous race
    controller._judge_filed_calls()
    assert controller.store.written == []
    assert controller._filed_calls == {}
    assert controller._filed_session is None


def test_the_flag_settles_what_the_laps_never_answered():
    box = Call(BOX_NOW, 20, "Box this lap.", "")
    controller = _stub([_row(20)], {1: (box, None)})
    controller._judge_filed_calls()
    assert controller.store.written == []
    controller._judge_filed_calls(final=True)
    assert [v for _, v, _ in controller.store.written] == [CANNOT_TELL]


def test_the_judging_runs_past_the_fragment_check():
    """The ordering itself, which the population filter above does not pin:
    a phantom must not be judged on its own crossing either."""
    source = _controller_source()
    fragment = source.index('self.store.exclude_lap(lap_id, "fragment")')
    judged = source.index("        self._judge_filed_calls()")
    assert judged > fragment


def test_every_call_path_files_for_a_verdict():
    """Critic pass 8: the position-call path discarded both the row and the
    revision id, so its rows kept `verdict = NULL` for the life of the race
    and NULL meant three unrelated things."""
    source = _controller_source()
    assert source.count("self._filed_calls[revision_id] = (call, row)") == 1
    assert source.count("self._filed_calls.setdefault(revision_id,") == 1
    assert source.count("row = self.race_screen.show_call(call)") == 2


def test_a_crossing_with_no_lap_number_files_no_board_row():
    """Rule 3, critic pass 8: `or 0` filed every rival's place under lap 0,
    which sorts first and reads as the grid."""
    source = _controller_source()
    assert 'getattr(lap, "lap_num", 0) or 0' not in source
    assert "if board_lap:" in source
