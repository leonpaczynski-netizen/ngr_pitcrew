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


def test_a_short_shift_call_is_a_closed_loop_and_says_so():
    """Critic pass 8, fourth round, and it took four rounds to see.

    `laps.short_shift_rpm` looked like the response and is the INSTRUCTION -
    `analysis/driving.py` says so in its first line, "records the APP's
    switch and nothing else". The app sets the beep when it makes the call,
    every frame of the next lap writes the drop back onto the lap, and
    judging on that field asks whether the app did what the app did. A driver
    who ignored the instruction completely and shifted at the limiter all lap
    read ACTED - and, once `disposition` was wired to the verdict, `taken` as
    well, in the field the contract tells a consumer to prefer.
    """
    call = Call(FUEL_SHORT, 6, "Short-shift.", "", short_shift_drop_rpm=400.0)
    # The beep engaged for the whole of the next lap - which says nothing
    # about the driver, and used to read ACTED.
    laps = [SimpleNamespace(lap_num=6, is_pit_lap=False, short_shift_rpm=None),
            SimpleNamespace(lap_num=7, is_pit_lap=False,
                            short_shift_rpm=400.0)]
    outcome = outcome_for(call, laps)
    assert outcome.verdict == CANNOT_TELL and outcome.settled
    # **And the refusal's reason is the one that binds** (critic pass 8,
    # fifth round). The first version said `laps.upshift_rpm` had "no
    # calibrated threshold" - and `analysis/driving.saving_change` has one,
    # runs every lap, and George SPEAKS it: "You've stopped short-shifting
    # since lap 15 - upshifts at 8298 before, 8694 now." One race, one
    # question, two mechanisms, opposite claims. What actually binds is the
    # DIRECTION: only a step upward has ever been calibrated.
    assert "STOP saving, not start" in outcome.detail
    assert "`" not in outcome.detail, "the driver reads this off the screen"
    # And the same answer whatever the field says, because the field is not
    # about him: no further lap changes it, so it is settled at once.
    laps[1].short_shift_rpm = None
    assert outcome_for(call, laps).verdict == CANNOT_TELL


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
    # **`acted`/`not-acted` arise for a box call and nothing else** (critic
    # pass 8, fourth round), so the verdict check sits back inside the
    # instruction branch and the precedence of every other one is unchanged.
    # A short-shift call is `cannot-tell` - the field it was judged on is
    # the app's own switch - and keeps the disposition it always had.
    short = {"lap_num": 10, "accepted": 0, "verdict": CANNOT_TELL,
             "plan": {"kind": FUEL_SHORT}}
    assert _disposition(short, set()) == ("informational", None)
    said = {"lap_num": 10, "accepted": 0, "verdict": CANNOT_TELL,
            "plan": {"kind": TYRE_TEMP}}
    assert _disposition(said, set()) == ("informational", None)
    # An offer's own resolution still wins, whatever the verdict says.
    fold = {"lap_num": 10, "accepted": 1, "verdict": CANNOT_TELL,
            "plan": {"kind": BOX_NOW, "resolution": "driver stayed out"}}
    assert _disposition(fold, set()) == ("driver stayed out", True)


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


def _row(lap_num, *, pit=False, reason=None):
    """One `laps` row as `list_laps` returns it - `SELECT *` into a dict."""
    return {"lap_num": lap_num, "is_pit_lap": pit, "short_shift_rpm": None,
            "excluded": 1 if reason else 0, "exclusion_reason": reason}


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


def test_a_lap_that_was_never_driven_does_not_fill_the_window():
    """Critic pass 8, second round. A phantom row - "two laps driven, three
    recorded", observed twice - is struck as a fragment but stays in
    `list_laps`, which is `SELECT *`, and `outcome_for` counts ROWS. So the
    window filled on a lap he never drove and "no stop on laps 12-14" was
    written and settled.

    **What happens now is a refusal, and the reason is worth stating.** A
    phantom CONSUMES its lap number (`session_state` numbers from the length
    of the list, and `laps` is `UNIQUE(session_id, lap_num)`), so the next
    lap he really drives is 15 and the call's window - which is lap numbers,
    12 to 14 - can never fill. `cannot-tell` is the honest answer and it is
    a strict improvement on the false `not-acted` it replaces; the true
    `acted` is lost with it, and that is the price of a stolen number."""
    box = Call(BOX_NOW, 12, "Box this lap.", "")
    laps = [_row(12), _row(13), _row(14, reason="fragment")]
    controller = _stub(laps, {1: (box, None)})
    controller._judge_filed_calls()
    assert controller.store.written == [], "nothing to say yet"
    assert set(controller._filed_calls) == {1}, "and it stays open"
    # The next lap he really drives is 15, and it is the stop.
    controller.store._laps = laps + [_row(15, pit=True)]
    controller._judge_filed_calls()
    assert controller.store.written == [], "the window still cannot fill"
    controller._judge_filed_calls(final=True)
    assert [v for _, v, _ in controller.store.written] == [CANNOT_TELL]


def test_a_lap_he_drove_and_struck_still_fills_the_window():
    """Critic pass 8, third round. Of the 39 excluded laps on file two are
    fragments and thirty-seven are laps he DROVE - struck by hand, an
    incident, traffic, a crash. Filtering on `excluded` turned "no stop on
    laps 12-14" into "the window it named was never fully driven" about a
    window he had fully driven: rule 12, the reason reported was not the one
    that bound the answer."""
    box = Call(BOX_NOW, 12, "Box this lap.", "")
    laps = [_row(12), _row(13, reason="incident"), _row(14)]
    controller = _stub(laps, {1: (box, None)})
    controller._judge_filed_calls()
    # Laps 13-14: lap 12 closed on the crossing the call was said on.
    assert [(v, d) for _, v, d in controller.store.written] == [
        (NOT_ACTED, "no stop on laps 13-14")]


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


def test_the_suzuka_calls_are_held_to_the_laps_that_can_answer_them():
    """Race run 20, 13 Sep 2026: every verdict read "cannot-tell ... GT7
    broadcasts no fuel map and no brake balance", including a place, "two to
    go" and "3.0 laps short". Replayed through the controller against the
    rows that race stored: no stop, the flag on lap 14 with 2.7 L aboard."""
    from pitcrew.race.call_outcome import BORNE_OUT, NOT_BORNE_OUT
    from pitcrew.race.calls import (GREEN, LAPS_TO_GO, POSITION, TO_THE_FLAG)

    places = {9: 4, 10: 5}
    laps = [dict(_row(n), position=places.get(n, 5), fuel_start=10.0,
                 fuel_end=2.73 if n == 14 else 8.0, laps_dropped=None)
            for n in range(1, 15)]
    filed = {
        468: (Call(GREEN, 0, "Green, green, green.", ""), None),
        471: (Call(FUEL_SHORT, 1, "Short-shift and lift into the slow "
                   "corners.", "You're 3.0 laps short on fuel.",
                   fuel_frame=TO_THE_FLAG), None),
        484: (Call(POSITION, 8, "P4 of 8.", "", position_called=4), None),
        487: (Call(POSITION, 9, "P2 of 8.", "", position_called=2), None),
        495: (Call(LAPS_TO_GO, 13, "Two to go.", "On the clock.",
                   tag="to-go-2"), None),
    }
    controller = _stub(laps, filed)
    controller.race = SimpleNamespace(state=SimpleNamespace(finished=False))
    controller._judge_filed_calls()
    # Settled at the crossing: the green and both places. The flag's two
    # claims wait for the flag.
    assert {rid for rid, *_ in controller.store.written} == {468, 484, 487}
    controller.race.state.finished = True
    controller._judge_filed_calls(final=True)
    verdicts = {rid: (v, d) for rid, v, d in controller.store.written}
    assert verdicts[468][0] == CANNOT_TELL
    assert "fuel map" not in verdicts[468][1]
    assert verdicts[484][0] == BORNE_OUT
    assert verdicts[487][0] == NOT_BORNE_OUT
    assert verdicts[471][0] == NOT_BORNE_OUT and "2.7 L" in verdicts[471][1]
    assert verdicts[495][0] == NOT_BORNE_OUT
    assert "one lap sooner" in verdicts[495][1]


def test_a_race_stopped_without_the_flag_holds_nothing_to_the_last_lap():
    from pitcrew.race.calls import LAPS_TO_GO

    two = Call(LAPS_TO_GO, 13, "Two to go.", "", tag="to-go-2")
    controller = _stub([dict(_row(n), laps_dropped=None)
                        for n in range(1, 15)], {1: (two, None)})
    controller.race = SimpleNamespace(state=SimpleNamespace(finished=False))
    controller._judge_filed_calls(final=True)
    [(_, verdict, detail)] = controller.store.written
    assert verdict == CANNOT_TELL and "flag was never seen" in detail


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
