"""The race around him, volunteered (D7 amended by the driver, 14 Sep 2026).

*"want more comms from him about what is going on in the race"* - so George
volunteers the gaps with names, what the stops mean for us, championship
rivals' places and pace against a neighbour. These pin each call's trigger,
its words, what it may claim, and that nothing is booked until it is heard.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from pitcrew.engineer.voice import NEWS, class_of, stale_after_s
from pitcrew.race import news as news_module
from pitcrew.race.call_outcome import (BORNE_OUT, CANNOT_TELL, NOT_BORNE_OUT,
                                       outcome_for)
from pitcrew.race.calls import (GAPS, LOW, MEDIUM, PACE, POSITION,
                                STOPS_PICTURE, URGENCY, WATCHED, Call)
from pitcrew.race.coordinator import RaceCoordinator, RacePhase
from pitcrew.race.gaps import GapTrend
from pitcrew.race.news import (RaceNews, a_person, board_places, gap_figure,
                               gap_sentence, pace_sentence, pace_verdict,
                               picture_words, watched_sentence)
from pitcrew.race.pit_wall import Entered
from pitcrew.race.rival_pace import RivalPace
from pitcrew.telemetry.recorder import SAMPLE_HZ


# ------------------------------------------------------------- the words

def test_a_gap_is_said_to_a_tenth_under_five_seconds_and_whole_above():
    assert gap_figure(2.14) == "2.1"
    assert gap_figure(4.94) == "4.9"
    assert gap_figure(4.96) == "5 seconds"
    assert gap_figure(12.4) == "12 seconds"
    assert gap_figure(0.04) == "under a tenth"


def test_a_name_is_said_and_a_handle_is_the_car_ahead():
    assert gap_sentence("ahead", "PUNISHED", 2.1) == "PUNISHED ahead, 2.1."
    assert gap_sentence("behind", "K.Graebs", 0.6) == "K.Graebs behind, 0.6."
    # Never "Car hash 76": a minted handle is not a person.
    assert gap_sentence("ahead", "Car #76", 2.1) == "The car ahead, 2.1."
    assert gap_sentence("behind", "82", 12.0) == "The car behind, 12 seconds."
    assert a_person("Car #76") is None and a_person("Rocky") == "Rocky"


def test_pace_uses_the_boards_words_on_each_side():
    """Rule 13: ahead, a closing gap is us catching him; behind, him catching
    us. The same signed number, opposite sentences."""
    assert pace_sentence("ahead", "PUNISHED", 0.94) == \
        "Catching PUNISHED, 0.9 seconds a lap."
    assert pace_sentence("ahead", None, -1.2) == \
        "Losing 1.2 seconds a lap to the car ahead."
    assert pace_sentence("behind", "K.Graebs", 0.5) == \
        "K.Graebs is catching, 0.5 seconds a lap."
    assert pace_sentence("behind", None, 0.5) == \
        "The car behind is catching, 0.5 seconds a lap."
    assert pace_sentence("behind", "Rocky", -0.8) == \
        "Pulling away from Rocky, 0.8 seconds a lap."


def test_effectively_is_always_after_the_stops_and_beside_the_road():
    call, reason = picture_words(6, ("effective", 8), 1)
    assert call == "P6 on the road."
    assert reason == "Effectively P8 after the stops. If they stop once."
    call, reason = picture_words(6, ("still", 2), 2)
    assert (call, reason) == ("P6 on the road.", "2 ahead still to stop.")
    assert picture_words(3, ("effective", 2), 2)[1].endswith(
        "If they stop twice.")


def test_a_watched_rival_is_placed_against_us():
    assert watched_sentence("Magical daddy", 4, 7) == "Magical daddy P4, 3 ahead."
    assert watched_sentence("Rocky", 6, 7) == "Rocky P6, the car ahead."
    assert watched_sentence("Rocky", 9, 7) == "Rocky P9, 2 behind."


def test_the_four_kinds_are_news_ranked_in_the_drivers_order():
    for kind in (STOPS_PICTURE, PACE, WATCHED, GAPS):
        assert class_of(kind) == NEWS
    order = [URGENCY.index(k) for k in (STOPS_PICTURE, PACE, WATCHED, GAPS)]
    assert order == sorted(order)
    assert stale_after_s(GAPS) < stale_after_s(PACE)


def test_a_newer_gap_line_replaces_a_queued_older_one():
    from pitcrew.engineer.voice import _LineQueue

    queue = _LineQueue()
    older = queue.line("PUNISHED ahead, 2.1.", GAPS)
    newer = queue.line("PUNISHED ahead, 1.9.", GAPS)
    assert queue.offer(older) == []
    dropped = queue.offer(newer)
    assert [line.text for line, _ in dropped] == ["PUNISHED ahead, 2.1."]
    assert [line.text for line in queue.snapshot()] == ["PUNISHED ahead, 1.9."]


# ------------------------------------------------------------- the board

def test_rows_are_places_on_a_short_board():
    places, visible, windowed = board_places(
        [(1, "Rocky"), (2, None), (3, "Beeni"), (4, "Chook")], 3, 3)
    assert places == {"Rocky": 1, "Beeni": 3, "Chook": 4}
    assert visible == {1, 2, 3, 4} and not windowed


def test_a_windowed_board_is_the_top_three_and_the_rows_round_us():
    """Daytona s142 as read: 1-3 then a window, him tenth on row six."""
    rows = [(1, "TommyTbone"), (2, "Rocky"), (3, "K.Graebs"),
            (4, "PUNISHED"), (5, "Greenmachine 070"), (6, "Beeni"),
            (7, "Corn_flake"), (8, "Magical daddy")]
    places, visible, windowed = board_places(rows, 6, 10)
    assert windowed
    assert places["K.Graebs"] == 3 and places["PUNISHED"] == 8
    assert places["Magical daddy"] == 12


def test_a_board_that_does_not_fit_the_shape_is_refused_not_guessed():
    assert board_places([(1, "Rocky")], None, 5) is None      # no own row
    assert board_places([(1, "Rocky")], 7, 5) is None          # row past place
    assert board_places([(1, "Rocky")], 2, 9) is None          # inside the top
    places, _, _ = board_places([(1, "Rocky"), (2, "Rocky")], 2, 2)
    assert "Rocky" not in places                               # read twice


# ------------------------------------------------------------ a race

@dataclass
class _Packet:
    current_position: int = 7
    cars_in_race: int = 13
    surface_types: tuple = ("T", "T", "T", "T")
    laps_completed: int | None = None


def a_race(*, mandatory_stops: int = 1, acknowledged: bool = False,
           position: int = 7) -> RaceCoordinator:
    plan = {"stops": 1, "stints": [{"laps": 10, "start_lap": 1},
                                   {"laps": 10, "start_lap": 11}]}
    co = RaceCoordinator(plan, mandatory_stops=mandatory_stops)
    co.acknowledged_delivery = acknowledged
    co.phase = RacePhase.RUNNING
    co.state.laps_total = 20
    co.state.lap = 5
    co.state.position = position
    co.state.position_said = position
    co.state.field_size = 13
    co._note_crossing_for_mid_lap()
    co._crossed_at_packet = -10 * 60
    return co


def run(co, seconds: float, packet=None, every=None) -> list[Call]:
    """Frames for `seconds`; `every(second)` is called once a second."""
    out = []
    packet = packet or _Packet(current_position=co.state.position or 7)
    for tick in range(int(seconds * SAMPLE_HZ)):
        if every is not None and tick % SAMPLE_HZ == 0:
            every(tick // SAMPLE_HZ)
        call = co.note_packet(packet)
        if call is not None:
            out.append(call)
    return out


def reads(co, side, gap, name, count=3):
    for _ in range(count):
        co.note_gap_read(side, gap, subject=name, name=name)


# ------------------------------------------------------------ gaps

def test_a_new_car_ahead_is_said_with_his_name_once_held():
    co = a_race()
    reads(co, "ahead", 2.14, "PUNISHED", count=2)
    assert run(co, 1) == []                    # two readings is not a car
    reads(co, "ahead", 2.12, "PUNISHED", count=1)
    said = run(co, 1)
    assert [c.spoken() for c in said] == ["PUNISHED ahead, 2.1."]
    assert said[0].kind == GAPS and said[0].confidence == MEDIUM
    assert "new" in said[0].why_spoken


def test_both_cars_are_said_when_one_is_new_and_the_other_is_near():
    co = a_race()
    reads(co, "behind", 0.62, "K.Graebs")
    reads(co, "ahead", 2.1, "PUNISHED")
    said = run(co, 1)
    assert [c.spoken() for c in said] == [
        "PUNISHED ahead, 2.1. K.Graebs behind, 0.6."]


def test_a_gap_crossing_into_the_tow_band_is_news_and_a_wobble_is_not():
    co = a_race()
    reads(co, "ahead", 2.4, "PUNISHED")
    assert run(co, 1)                           # the car, said and booked
    run(co, RaceCoordinator.MID_LAP_SPACING_S)  # nothing new to say
    # 1.45 is inside the dead band round 1.5 - not across it.
    reads(co, "ahead", 1.45, "PUNISHED", count=2)
    assert run(co, 1) == []
    reads(co, "ahead", 1.3, "PUNISHED", count=2)
    said = run(co, 1)
    assert [c.spoken() for c in said] == ["PUNISHED ahead, 1.3."]
    assert "band" in said[0].why_spoken


def test_the_refresher_is_once_a_lap_and_only_with_a_car_near():
    co = a_race()
    reads(co, "ahead", 3.6, "PUNISHED")
    assert run(co, 1)
    reads(co, "ahead", 3.5, "PUNISHED")
    assert run(co, RaceCoordinator.MID_LAP_SPACING_S + 5) == []  # same lap
    co.state.lap = 6
    reads(co, "ahead", 3.4, "PUNISHED")
    said = run(co, 1)
    assert [c.spoken() for c in said] == ["PUNISHED ahead, 3.4."]
    assert "refresher" in said[0].why_spoken


def test_no_refresher_when_both_cars_are_far():
    co = a_race()
    reads(co, "ahead", 9.0, "PUNISHED")
    reads(co, "behind", 14.0, "Rocky")
    assert run(co, 1)                           # new cars, said once
    co.state.lap = 6
    reads(co, "ahead", 9.1, "PUNISHED")
    reads(co, "behind", 14.2, "Rocky")
    assert run(co, RaceCoordinator.MID_LAP_SPACING_S + 5) == []


def test_a_stale_reading_is_not_the_gap_now():
    co = a_race()
    reads(co, "ahead", 2.0, "PUNISHED")
    run(co, news_module.GAP_FRESH_S + 1, packet=_Packet())
    fresh = a_race()
    reads(fresh, "ahead", 2.0, "PUNISHED")
    # Built only from a reading inside the window.
    assert fresh.news.gaps_call(fresh.state, fresh._packets
                                + int(news_module.GAP_FRESH_S * 60) + 60) \
        is None


def test_a_gap_line_not_heard_is_offered_again_from_the_gap_then():
    co = a_race(acknowledged=True)
    reads(co, "ahead", 2.1, "PUNISHED")
    first = run(co, 1)
    assert [c.spoken() for c in first] == ["PUNISHED ahead, 2.1."]
    reads(co, "ahead", 1.9, "PUNISHED")
    # In flight: nothing else of the race news while the voice holds it.
    assert run(co, RaceCoordinator.MID_LAP_SPACING_S + 1) == []
    co.delivered(first[0], False)
    reads(co, "ahead", 1.9, "PUNISHED", count=1)
    again = run(co, 1)
    assert [c.spoken() for c in again] == ["PUNISHED ahead, 1.9."]
    co.delivered(again[0], True)
    assert run(co, RaceCoordinator.MID_LAP_SPACING_S + 1) == []


def test_nothing_is_volunteered_off_the_road():
    co = a_race()
    reads(co, "ahead", 2.1, "PUNISHED")
    off = _Packet(surface_types=("G",) * 4)
    assert run(co, 3, packet=off) == []


# ------------------------------------------------ one car, or several

def spaced(co, side, gaps, name, *, every_s=2.2, packet=None):
    """Readings `every_s` apart, the race running between them; the calls
    made meanwhile."""
    out = []
    for gap in gaps:
        co.note_gap_read(side, gap, subject=name,
                         name=None if str(name).isdigit() else name)
        out += run(co, every_s, packet=packet)
    return out


def gap_lines(calls):
    return [c.spoken() for c in calls if c.kind == GAPS]


def test_the_envelope_is_a_corner_burst_then_a_drift():
    allowed = news_module.jump_allowed_s
    assert allowed(0.0) == pytest.approx(0.5)
    assert allowed(2.0) == pytest.approx(1.0)          # 0.25 s a second
    assert allowed(30.0) == pytest.approx(3.0)         # not 8.0
    assert allowed(120.0) == pytest.approx(7.5)


def test_a_jump_with_nothing_on_the_circuit_between_is_never_heard():
    """Bathurst, replayed: "The car ahead, 0.5." then "The car ahead, 9
    seconds." Here with no pass, no stop and no off between them."""
    co = a_race()
    first = gap_lines(spaced(co, "ahead", [0.52, 0.50, 0.49], "78")
                      + run(co, 1))
    assert first == ["The car ahead, 0.5."]
    heard = gap_lines(
        spaced(co, "ahead", [9.0, 9.02, 8.98, 9.01, 9.0, 8.97, 9.03], "78")
        + run(co, RaceCoordinator.MID_LAP_SPACING_S))
    co.state.lap = 6                                     # the refresher is due
    heard += gap_lines(spaced(co, "ahead", [9.0, 9.02], "78")
                       + run(co, RaceCoordinator.MID_LAP_SPACING_S))
    assert not any("9" in line for line in heard), heard


def test_one_misread_is_refused_and_the_car_stands():
    co = a_race()
    assert gap_lines(spaced(co, "ahead", [2.1, 2.1, 2.1], "PUNISHED")
                     + run(co, 1)) == ["PUNISHED ahead, 2.1."]
    spaced(co, "ahead", [9.9], "PUNISHED", every_s=0.1)
    assert co.news._run["ahead"] and co.news._ref["ahead"].gap_s == 2.1
    # Nothing is said while a jump is being held.
    assert co.news.gaps_call(co.state, co._packets) is None
    spaced(co, "ahead", [2.0], "PUNISHED")
    assert co.news._run["ahead"] == [] and co.news._ref["ahead"].gap_s == 2.0


def test_the_refresher_does_not_alternate_between_two_cars():
    """One handle, two cars' figures in turn - the board's merged cluster.
    Whatever is said on that side is the car the handle was first."""
    co = a_race()
    said = gap_lines(spaced(co, "ahead", [1.2, 1.2, 1.2], "78") + run(co, 1))
    for lap in range(6, 10):
        co.state.lap = lap
        said += gap_lines(spaced(co, "ahead", [7.8, 1.2] * 8, "78")
                          + run(co, 5))
    figures = {line for line in said}
    assert figures == {"The car ahead, 1.2."}, said


def test_one_car_under_two_handles_is_never_a_new_car():
    """Session 204 (Bathurst, 20 Sep 2026): the slot changed handle 71 times
    for a seven-car field and 43 of those were an immediate A -> B -> A
    return of one driver between two roster clusters - `PUNISHED` and `277`
    alternating 11 times. 22 of the 31 gap calls George made that night were
    triggered by nothing but that churn.

    The figure decides, not the handle: the returning run's first reading is
    continuous with the slot's last, so it is one car's series and nothing
    is announced.
    """
    co = a_race()
    said = [c for c in spaced(co, "ahead", [2.1, 2.1, 2.1], "PUNISHED")
            + run(co, 1) if c.kind == GAPS]
    assert [c.spoken() for c in said] == ["PUNISHED ahead, 2.1."]
    for lap in range(6, 12):
        co.state.lap = lap
        said += [c for c in
                 spaced(co, "ahead", [2.12, 2.14, 2.11], "277")
                 + spaced(co, "ahead", [2.13, 2.1, 2.12], "PUNISHED")
                 + run(co, 5) if c.kind == GAPS]
    # Whatever is said after the first line is the once-a-lap refresher, at a
    # gap that has not moved. No handle change is news.
    triggers = [c.why_spoken.split(";")[0] for c in said[1:]]
    assert triggers and all("new" not in t for t in triggers), triggers
    # Rule 13: one car in the slot, so one name, whichever handle was read.
    assert {c.spoken() for c in said} == {"PUNISHED ahead, 2.1."}
    assert co.news._slot_new["ahead"] == 1       # the first fill, and no more
    assert co.news._slot_bound["ahead"] == 1     # 277, taken as the same car
    assert co.news._bound["ahead"] == {"PUNISHED", "277"}


def test_a_pass_under_a_second_handle_is_a_new_car_on_the_same_reading():
    """The flicker's suppression may not cost a real overtake its call. The
    new car arrives under a handle the slot has never bound, and its figure
    is one no car's gap could have reached - so it is announced on the third
    agreeing reading, exactly as a new handle always was."""
    co = a_race(position=8)
    assert gap_lines(spaced(co, "ahead", [0.4, 0.4, 0.4], "PUNISHED",
                            packet=_Packet(8))
                     + run(co, 1, packet=_Packet(8))) == ["PUNISHED ahead, 0.4."]
    run(co, RaceCoordinator.MID_LAP_SPACING_S, packet=_Packet(8))
    run(co, 2, packet=_Packet(7))                # we pass him
    assert gap_lines(spaced(co, "ahead", [4.0, 4.02], "277",
                            packet=_Packet(7))) == []      # two, held
    said = [c for c in spaced(co, "ahead", [4.04], "277", packet=_Packet(7))
            if c.kind == GAPS]                             # the third
    assert [c.spoken() for c in said] == ["The car ahead, 4.0."]
    assert "a new car is ahead" in said[0].why_spoken
    assert co.news._slot_new["ahead"] == 2
    # Rule 13: the car that left took its name with it - the new one is not
    # PUNISHED, and is not called PUNISHED.
    assert co.news.neighbour("ahead") is None


def test_a_new_car_does_not_wear_the_last_ones_name():
    """Rule 13. The slot keeps one name while one car is in it, whichever
    handle was read - but a name is evidence about a car, not about a box,
    and the car leaving takes it. Otherwise a person's name is said about
    somebody else."""
    co = a_race(position=8)
    spaced(co, "ahead", [0.4, 0.4, 0.4], "PUNISHED", packet=_Packet(8))
    run(co, 1, packet=_Packet(8))
    # The same car read under a bare cluster id: still PUNISHED.
    spaced(co, "ahead", [0.42, 0.41, 0.43], "277", packet=_Packet(8))
    assert co.news.neighbour("ahead") == "PUNISHED"
    assert gap_lines(spaced(co, "ahead", [0.4], "277", packet=_Packet(8))
                     + run(co, RaceCoordinator.MID_LAP_SPACING_S,
                           packet=_Packet(8))) == []
    # We pass him, and the box shows the next car up the road under `277` -
    # a handle the slot has bound, so the break is in the FIGURE. The name
    # belonged to the car that left, and goes with it.
    run(co, 2, packet=_Packet(7))
    said = gap_lines(spaced(co, "ahead", [4.5, 4.52, 4.54], "277",
                            packet=_Packet(7))
                     + run(co, 1, packet=_Packet(7)))
    assert said == ["The car ahead, 4.5."]
    assert co.news.neighbour("ahead") is None
    assert co.news._bound["ahead"] == {"277"}


def test_a_handle_refused_as_a_slot_may_not_name_the_car_through_a_binding():
    """`gaps_call` drops the name of a handle that named a slot rather than
    a car - but it checks the handle the slot is keyed on. A refused handle
    bound to the slot beside it would hand the same name back through the
    side door."""
    co = a_race(position=8)
    spaced(co, "ahead", [0.3, 0.3, 0.3], "78", packet=_Packet(8))
    run(co, 1, packet=_Packet(8))
    run(co, 2, packet=_Packet(7))                # we pass: 78 names the slot
    spaced(co, "ahead", [2.4, 2.4, 2.4], "78", packet=_Packet(7))
    assert "78" in co.news._merged
    co.news._neighbour_name["ahead"] = None
    spaced(co, "ahead", [2.42, 2.41], "PUNISHED", packet=_Packet(7))
    co.news._merged["PUNISHED"] = "held a slot"
    spaced(co, "ahead", [2.43, 2.44, 2.45], "PUNISHED", packet=_Packet(7))
    assert "PUNISHED" in co.news._bound["ahead"]
    assert co.news.neighbour("ahead") is None


def test_a_refusal_that_disagrees_with_every_reading_since_is_retired(caplog):
    """CLAUDE.md rule 10. On session 204 `PUNISHED` held the behind slot
    across one place change at 20:51:32, was written off as naming a slot
    rather than a car - no name, no pace - and nothing could reinstate him.
    He was one of two real names in a seven-car field and went unnamed for
    the last 26 minutes while still racing us.

    A refusal correctly never becomes the baseline, so something else has to
    retire it: `CLEAR_AFTER_CLEAN_READS` readings running that the car in the
    slot accepted as its own. And the accepts are logged with the count
    that set the bar, not only the refusal.
    """
    co = a_race(position=8)
    spaced(co, "ahead", [0.3, 0.3, 0.3], "PUNISHED", packet=_Packet(8))
    run(co, 1, packet=_Packet(8))
    run(co, 2, packet=_Packet(7))
    spaced(co, "ahead", [2.4, 2.4, 2.4], "PUNISHED", packet=_Packet(7))
    assert "PUNISHED" in co.news._merged
    assert not co.news.one_car("PUNISHED")
    with caplog.at_level("INFO", logger="pitcrew.race"):
        spaced(co, "ahead", [2.4] * (news_module.CLEAR_AFTER_CLEAN_READS - 1),
               "PUNISHED", packet=_Packet(7))
        assert "PUNISHED" in co.news._merged      # one short is still refused
        spaced(co, "ahead", [2.4], "PUNISHED", packet=_Packet(7))
    assert co.news.one_car("PUNISHED")
    assert co.news.neighbour("ahead") == "PUNISHED"
    cleared = [r.message for r in caplog.records if "is one car again" in
               r.message]
    assert cleared and str(news_module.CLEAR_AFTER_CLEAN_READS) in cleared[0]


def test_an_unconfirmed_handle_is_believed_again_once_its_readings_are(caplog):
    """Rule 10, the other refusal. `_unreliable` hedges every gap line about
    a handle with "Unconfirmed." and says no pace off it at all, and it
    could not be taken back either: on session 204 `Car #9` earned it on its
    second jump and every later line about the car ahead carried the word to
    the flag.

    **The hedge is not the defect - the latch is.** §5.5 gives him
    "unconfirmed" to act on, so this does not delete the word; it retires it
    on the same sustained clean run that retires `_merged`, and drops the
    jump count with it so the hedge has to be earned from nothing again.

    Replayed over session 204's 2,057 named readings: two handles earned the
    hedge, `PUNISHED` on lap 13 and `Car #9` on lap 18, and neither could
    shed it - 5 of the 29 gap calls carried "Unconfirmed." and both handles
    were still refused at the flag. With the retirement each cleared on the
    next lap, after 12 readings of its own gap: `PUNISHED` held it for 71 s
    and `Car #9` for 74 s. **One call of the 29 still carries the word** -
    the one made inside `Car #9`'s 74 s, which is the call the hedge is for.
    The other four were spoken 250 s, 27 s, 117 s and 427 s after the reader
    had settled. Each handle jumped once more afterwards and neither reached
    the bar again, so the word was not said when it was not earned.
    """
    co = a_race()
    spaced(co, "ahead", [3.0, 3.0, 3.0], "80")
    run(co, 1)
    spaced(co, "ahead", [6.0, 6.0, 6.0], "80")         # jump one
    spaced(co, "ahead", [3.2, 3.2, 3.2], "80")         # jump two
    assert "80" in co.news._unreliable and co.news._jumps["80"] == 2
    run(co, 60)
    co.state.lap = 7
    said = [c for c in spaced(co, "ahead", [3.2, 3.2], "80") + run(co, 1)
            if c.kind == GAPS]
    assert [c.spoken() for c in said] == ["The car ahead, 3.2. Unconfirmed."]
    assert said[0].confidence == LOW
    with caplog.at_level("INFO", logger="pitcrew.race"):
        spaced(co, "ahead", [3.2] * (news_module.CLEAR_AFTER_CLEAN_READS - 3),
               "80")
        assert "80" in co.news._unreliable   # one short is still unconfirmed
        spaced(co, "ahead", [3.2], "80")
    assert "80" not in co.news._unreliable
    assert co.news.one_car("80") and "80" not in co.news._jumps
    cleared = [r.message for r in caplog.records
               if "is one car again" in r.message]
    assert cleared and "jump(s) are forgotten" in cleared[0]
    run(co, 60)
    co.state.lap = 8
    said = [c for c in spaced(co, "ahead", [3.2, 3.2], "80") + run(co, 1)
            if c.kind == GAPS]
    assert [c.spoken() for c in said] == ["The car ahead, 3.2."]
    assert said[0].confidence == MEDIUM


def test_a_reader_that_keeps_jumping_stays_unconfirmed():
    """The other half of rule 10 again: a retirement that lets a real
    refusal go is no better than a latch. Every jump restarts the clean run,
    and after a clear the handle re-earns the hedge from nothing - which a
    reader that really jumps does in seconds."""
    co = a_race()
    spaced(co, "ahead", [3.0, 3.0, 3.0], "80")
    run(co, 1)
    for _ in range(4):
        # A jump, then a clean run that stops short of the bar, over and
        # over: the hedge is earned, cleared, and earned again.
        spaced(co, "ahead", [6.0, 6.0, 6.0], "80")
        spaced(co, "ahead", [3.2, 3.2, 3.2], "80")
        assert "80" in co.news._unreliable
        spaced(co, "ahead", [3.2] * (news_module.CLEAR_AFTER_CLEAN_READS - 4),
               "80")
        assert "80" in co.news._unreliable, "cleared without a clean run"
    # And a handle whose jumps stop is believed again, so the word means
    # something when it is said.
    spaced(co, "ahead", [3.2] * news_module.CLEAR_AFTER_CLEAN_READS, "80")
    assert "80" not in co.news._unreliable


def test_a_handle_that_really_names_a_slot_never_clears():
    """The other half of rule 10: the retirement may not let a genuine
    refusal go. Every fresh hold across a place change writes it again and
    restarts the count, so the handle keeps earning it."""
    co = a_race(position=8)
    spaced(co, "ahead", [0.3, 0.3, 0.3], "78", packet=_Packet(8))
    run(co, 1, packet=_Packet(8))
    place = 7
    for gap in (2.4, 5.0, 8.0, 12.0):
        run(co, 2, packet=_Packet(place))
        spaced(co, "ahead", [gap] * (news_module.CLEAR_AFTER_CLEAN_READS - 2),
               "78", packet=_Packet(place))
        place -= 1
        assert "78" in co.news._merged
    assert not co.news.one_car("78")


def test_a_jump_across_a_place_change_is_a_new_car_once_three_agree():
    co = a_race(position=8)
    assert gap_lines(spaced(co, "ahead", [0.3, 0.3, 0.3], "78",
                            packet=_Packet(8))
                     + run(co, 1, packet=_Packet(8))) == ["The car ahead, 0.3."]
    # The box read every 2.2 s, as the wall reads it.
    spaced(co, "ahead", [0.3] * 14, "78", packet=_Packet(8))
    # We pass him: P7, and the box shows the next car up the road.
    run(co, 2, packet=_Packet(7))
    assert gap_lines(spaced(co, "ahead", [1.9, 1.92], "78",
                            packet=_Packet(7))) == []          # two, held
    said = gap_lines(spaced(co, "ahead", [1.94], "78", packet=_Packet(7))
                     + run(co, 1, packet=_Packet(7)))
    assert said == ["The car ahead, 1.9."]
    # The handle held the slot across the pass: a slot, not a car.
    assert "78" in co.news._merged and "78" not in co.news._unreliable


def test_a_named_handle_that_names_a_slot_loses_its_name_and_its_pace():
    co = a_race(position=8)
    assert gap_lines(spaced(co, "ahead", [0.3, 0.3, 0.3], "PUNISHED",
                            packet=_Packet(8))
                     + run(co, 1, packet=_Packet(8))) == [
        "PUNISHED ahead, 0.3."]
    spaced(co, "ahead", [0.3] * 14, "PUNISHED", packet=_Packet(8))
    run(co, 2, packet=_Packet(7))
    said = gap_lines(spaced(co, "ahead", [2.4, 2.4, 2.4], "PUNISHED",
                            packet=_Packet(7))
                     + run(co, RaceCoordinator.MID_LAP_SPACING_S,
                           packet=_Packet(7)))
    assert said == ["The car ahead, 2.4."]
    trend = co.news._trends["ahead"]
    for key in range(1, 8):
        trend.note(key, 10.0 - key, subject="PUNISHED")
    assert co.news.pace_call(co.state, co._packets) is None


def test_readings_that_jump_twice_with_nothing_to_explain_it_are_unconfirmed():
    co = a_race()
    spaced(co, "ahead", [3.0, 3.0, 3.0], "80")
    run(co, 1)
    spaced(co, "ahead", [6.0, 6.0, 6.0], "80")         # jump one
    spaced(co, "ahead", [3.2, 3.2, 3.2], "80")         # jump two
    assert "80" in co.news._unreliable
    run(co, 60)
    co.state.lap = 7
    said = [c for c in spaced(co, "ahead", [3.2, 3.2], "80") + run(co, 1)
            if c.kind == GAPS]
    assert [c.spoken() for c in said] == ["The car ahead, 3.2. Unconfirmed."]
    assert said[0].confidence == LOW


def test_readings_that_fit_nothing_retire_the_car():
    """Rule 10: a reference that disagrees with everything is what is
    wrong."""
    co = a_race()
    spaced(co, "ahead", [2.0, 2.0, 2.0], "PUNISHED")
    spaced(co, "ahead", [9.0, 15.0, 4.0, 12.0, 20.0, 7.0], "PUNISHED",
           every_s=0.5)
    assert co.news._neighbour["ahead"] is None
    spaced(co, "ahead", [7.1, 7.1, 7.1], "PUNISHED")
    assert co.news._neighbour["ahead"] == "PUNISHED"
    assert co.news._ref["ahead"].gap_s == 7.1


def test_our_own_off_moves_the_gap_and_is_not_a_new_car():
    co = a_race()
    assert gap_lines(spaced(co, "ahead", [2.0, 2.0, 2.0], "PUNISHED")
                     + run(co, 1)) == ["PUNISHED ahead, 2.0."]
    identity = co.news._segment[("ahead", "PUNISHED")]
    run(co, 6, packet=_Packet(surface_types=("G",) * 4))
    spaced(co, "ahead", [9.0, 9.0, 9.0], "PUNISHED")
    assert co.news._segment[("ahead", "PUNISHED")] == identity
    assert "PUNISHED" not in co.news._merged
    assert "PUNISHED" not in co.news._unreliable


def test_the_one_car_state_is_reset_with_the_race():
    co = a_race()
    spaced(co, "ahead", [2.0, 2.0, 2.0], "78")
    run(co, 2, packet=_Packet(6))
    spaced(co, "ahead", [6.0, 6.0, 6.0], "78", packet=_Packet(6))
    assert co.news._merged
    co.news.new_session()
    news = co.news
    assert (news._merged, news._clean_run, news._unreliable, news._jumps,
            news._segment, len(news._moments)) == ({}, {}, {}, {}, {}, 0)
    assert news._ref == {"ahead": None, "behind": None}
    assert news._bound == {"ahead": set(), "behind": set()}
    assert news._slot_seen == news._slot_new == news._slot_bound == {
        "ahead": 0, "behind": 0}


# ------------------------------------------------------------ pace

def _pace_trend(side, gaps, subject="PUNISHED"):
    trend = GapTrend(side=side)
    for key, gap in gaps:
        trend.note(key, gap, subject=subject)
    return trend


def _filed(side, gaps, ours=120.0, subject="PUNISHED", exclude=None):
    pace = RivalPace()
    by_key = dict(gaps)
    for key in sorted(by_key):
        if key - 1 in by_key:
            pace.note_lap(key, ours, by_key[key], by_key[key - 1],
                          ahead=(side == "ahead"), subject=subject,
                          exclude=(exclude or {}).get(key))
    return pace


def test_a_steady_close_beyond_the_noise_is_a_pace_call():
    gaps = [(k, 10.0 - 1.0 * (k - 3) + (0.1 if k % 2 else -0.1))
            for k in range(3, 9)]
    trend = _pace_trend("ahead", gaps)
    verdict, why = pace_verdict(trend, "ahead", _filed("ahead", gaps),
                                {k: 120.0 for k in range(20)}, now_key=9)
    assert verdict is not None, why
    assert verdict.rate > 0.8 and verdict.gain_s_per_lap > 0
    assert abs(verdict.gain_s_per_lap) > verdict.half_width_s


def test_a_noisy_gap_with_a_board_sized_rate_is_refused():
    """The board's rule alone passes this - a trimmed-median 1.0 s a lap - and
    the lap changes (-4, -1, -1, +2.2) put the mean inside its own noise."""
    gaps = [(3, 10.0), (4, 6.0), (5, 5.0), (6, 4.0), (7, 6.2)]
    gaps.append((8, 5.2))
    trend = _pace_trend("ahead", gaps)
    verdict, why = pace_verdict(trend, "ahead", _filed("ahead", gaps),
                                {k: 120.0 for k in range(20)}, now_key=9)
    assert verdict is None
    assert "noise" in why or "board" in why


def test_a_lap_he_was_in_the_lane_is_not_a_lap_of_his_pace():
    gaps = [(k, 10.0 - 1.0 * (k - 3)) for k in range(3, 9)]
    trend = _pace_trend("ahead", gaps)
    pace = _filed("ahead", gaps, exclude={6: "he pitted on this lap"})
    verdict, why = pace_verdict(trend, "ahead", pace,
                                {k: 120.0 for k in range(20)}, now_key=9)
    assert verdict is None and "pitted" in why
    verdict, why = pace_verdict(trend, "ahead", _filed("ahead", gaps),
                                {k: 120.0 for k in range(20)}, now_key=9,
                                dirty_keys=frozenset({7}))
    assert verdict is None and "excluded" in why


def test_the_lap_in_progress_is_not_in_the_verdict():
    gaps = [(k, 10.0 - 1.0 * (k - 3)) for k in range(3, 8)]
    trend = _pace_trend("ahead", gaps)
    verdict, _ = pace_verdict(trend, "ahead", _filed("ahead", gaps),
                              {k: 120.0 for k in range(20)}, now_key=7)
    assert verdict is None                      # only four completed laps


def _closing_ahead(co, first_gap: float) -> None:
    for key in range(1, 9):
        co.state.lap = key
        # A lap apart: a second a lap is a car closing, not a jump.
        co._packets += int(120 * SAMPLE_HZ)
        for _ in range(3):
            co.note_gap_read("ahead", first_gap - 1.0 * key,
                             subject="PUNISHED", name="PUNISHED")
        co.news.note_lap(key, key + 1, 120.0)
    co.state.lap = 9
    news = co.news
    news._said_gap["ahead"] = (
        ("PUNISHED", news._segment[("ahead", "PUNISHED")]),
        news._band["ahead"], news._ref["ahead"])
    co.news._gap_lap = co.state.lap_now()


def test_the_pace_call_through_the_race_names_him_and_says_the_count():
    """Beyond `news.CATCH_WINDOW_S` there is no catch to project, and the
    plain pace figure is the call."""
    co = a_race()
    _closing_ahead(co, 30.0)
    said = run(co, 1)
    assert [c.spoken() for c in said] == [
        "Catching PUNISHED, 1.0 seconds a lap. Over 5 laps."]
    assert said[0].kind == PACE and said[0].confidence == MEDIUM
    assert "95%" in said[0].why_spoken


def test_inside_the_window_the_pace_call_says_when_he_gets_there():
    """Sardegna Rd 9 (session 188, `test_catch_projection_s188`): the same
    close two seconds up the road is a catch lap, through the coordinator."""
    co = a_race()
    _closing_ahead(co, 10.0)
    said = run(co, 1)
    assert [c.spoken() for c in said] == [
        "Catching PUNISHED, 1.0 seconds a lap. On him around lap 12."]
    assert said[0].kind == PACE and said[0].confidence == MEDIUM
    assert said[0].derived.startswith("derived:")


# ------------------------------------------------------------ championship

def board(co, rows, own_row):
    co.note_board(rows, own_row)


def test_a_watched_rivals_first_place_is_a_baseline_and_a_change_is_news():
    co = a_race(position=7)
    co.state.watched_rivals = frozenset({"magical daddy"})
    rows = [(1, "Rocky"), (2, None), (3, "Magical daddy"), (4, None),
            (5, None), (6, None), (7, "Beeni")]
    board(co, rows, 7)
    board(co, rows, 7)
    assert run(co, 1) == []                    # the first sight is not news
    moved = [(1, "Rocky"), (2, "Magical daddy"), (3, None), (4, None),
             (5, None), (6, None), (7, "Beeni")]
    board(co, moved, 7)
    assert run(co, 1) == []                    # not held yet
    board(co, moved, 7)
    said = run(co, 1)
    assert [c.spoken() for c in said] == ["Magical daddy P2, 5 ahead."]
    assert said[0].kind == WATCHED


def test_a_watched_rival_off_the_board_is_given_no_place():
    co = a_race(position=10)
    co.state.watched_rivals = frozenset({"rocky"})
    rows = [(1, "A"), (2, "B"), (3, "C"), (4, "D"), (5, "E"), (6, "Beeni")]
    board(co, rows, 6)
    board(co, rows, 6)
    assert run(co, 2) == []


def test_after_his_stop_his_place_is_said_with_it():
    co = a_race(position=7)
    co.state.watched_rivals = frozenset({"rocky"})
    ahead = [(1, "Rocky")] + [(n, None) for n in range(2, 7)] + [(7, "Beeni")]
    board(co, ahead, 7)
    board(co, ahead, 7)
    run(co, 1)
    co.state.lane.enter(Entered(driver="Rocky", driver_id=1, lap=5,
                                fuel_in_l=10, partial=False), lap=5)
    co.state.lane.left("Rocky", lap=5)
    co.state.lane.tell([co.state.lane.stops()[0].key])
    behind = [(n, None) for n in range(1, 7)] + [(7, "Beeni"), (8, "Rocky")]
    board(co, behind, 7)
    board(co, behind, 7)
    said = [c for c in run(co, 1) if c.kind == WATCHED]
    assert [c.spoken() for c in said] == ["Rocky P8, the car behind. "
                                          "After his stop."]


# ------------------------------------------------------------ the stops

def a_stop(co, driver, *, ahead=None, lap=5, left=True):
    co.state.lane.enter(Entered(driver=driver, driver_id=0, lap=lap,
                                fuel_in_l=10, partial=False,
                                ahead_at_entry=ahead), lap=lap)
    if left:
        co.state.lane.left(driver, lap=lap)


def test_a_place_the_lane_made_carries_the_picture_not_not_passes():
    """Bathurst lap 11: P8 to P6 because Car #31 and Car #28 boxed, and our
    stop still owed - "P6 on the road. Effectively P8 after the stops." One
    call carries it; the board is not in hand, so it is unconfirmed."""
    co = a_race(position=8)
    for driver in ("Car #31", "Car #28"):
        a_stop(co, driver, ahead=True, left=False)
        co.state.lane.tell([co.state.lane.stops()[-1].key])
    said = run(co, 10, packet=_Packet(current_position=6))
    assert [c.spoken() for c in said] == [
        "P6 on the road. Effectively P8 after the stops. If they stop once. "
        "Unconfirmed."]
    call = said[0]
    assert call.kind == STOPS_PICTURE and call.confidence == LOW
    assert call.position_called == 6
    assert co.state.position_said == 6              # booked (no ack here)
    assert len(co.state.lane.dropped_behind()) == 2
    assert "regulations" in call.why_spoken


def test_with_no_stop_requirement_the_lane_line_stands():
    co = a_race(position=8, mandatory_stops=0)
    co._stints = []                                 # no plan either
    for driver in ("Car #31", "Car #28"):
        a_stop(co, driver, ahead=True, left=False)
        co.state.lane.tell([co.state.lane.stops()[-1].key])
    said = run(co, 10, packet=_Packet(current_position=6))
    assert [c.spoken() for c in said] == [
        "P6 of 13. Not passes - 2 cars ahead boxed."]


def test_cars_ahead_still_to_stop_are_counted_off_the_board_after_ours():
    co = a_race(position=6)
    co.state.stint_index = 1                        # we have stopped
    a_stop(co, "PUNISHED")
    co.state.lane.tell([s.key for s in co.state.lane.stops()])
    rows = [(1, "Rocky"), (2, "PUNISHED"), (3, "Chook"), (4, "Boxhead"),
            (5, "Tommy"), (6, "Beeni"), (7, "Zen")]
    for _ in range(2):
        board(co, rows, 6)
    said = []

    def keep_the_board(_second):
        board(co, rows, 6)
    said = run(co, 10, every=keep_the_board)
    pictures = [c for c in said if c.kind == STOPS_PICTURE]
    # We owe nothing; four cars ahead owe one each: P2 effectively.
    assert [c.spoken() for c in pictures] == [
        "P6 on the road. Effectively P2 after the stops. If they stop once."]
    assert pictures[0].confidence == MEDIUM


def test_before_our_stop_cars_ahead_that_still_owe_one_are_counted():
    co = a_race(position=6)
    a_stop(co, "Behind1")
    co.state.lane.tell([s.key for s in co.state.lane.stops()])
    rows = [(1, "Rocky"), (2, "PUNISHED"), (3, "Chook"), (4, "Boxhead"),
            (5, "Tommy"), (6, "Beeni"), (7, "Behind1")]

    def keep_the_board(_second):
        board(co, rows, 6)
    said = [c for c in run(co, 10, every=keep_the_board)
            if c.kind == STOPS_PICTURE]
    assert [c.spoken() for c in said] == ["P6 on the road. 5 ahead still to stop."]


def test_a_board_that_cannot_see_everyone_ahead_is_unconfirmed():
    co = a_race(position=10)
    co.state.stint_index = 1
    a_stop(co, "PUNISHED")
    co.state.lane.tell([s.key for s in co.state.lane.stops()])
    # Windowed: rows 1-3 and 8-12. P4-P7 are not drawn.
    rows = [(1, "A"), (2, "B"), (3, "C"), (4, "D"), (5, "E"), (6, "Beeni"),
            (7, "F")]

    def keep_the_board(_second):
        board(co, rows, 6)
    said = [c for c in run(co, 10, every=keep_the_board)
            if c.kind == STOPS_PICTURE]
    assert said and said[0].confidence == LOW
    assert said[0].spoken().endswith("Unconfirmed.")


# ------------------------------------------------------------ verdicts

@dataclass
class _Lap:
    lap_num: int
    position: int
    is_pit_lap: bool = False


def test_the_road_half_of_a_stop_picture_is_held_to_the_line():
    call = Call(STOPS_PICTURE, 10, "P6 on the road.",
                "Effectively P8 after the stops. If they stop once.", LOW,
                position_called=6)
    held = outcome_for(call, [_Lap(11, 6)])
    assert held.verdict == BORNE_OUT and "regulation minimum" in held.detail
    missed = outcome_for(call, [_Lap(11, 7)])
    assert missed.verdict == NOT_BORNE_OUT
    waiting = outcome_for(call, [_Lap(10, 6)])
    assert waiting.verdict == CANNOT_TELL and not waiting.settled


@pytest.mark.parametrize("kind", [GAPS, PACE, WATCHED])
def test_the_board_read_calls_say_why_they_cannot_be_held(kind):
    outcome = outcome_for(Call(kind, 8, "PUNISHED ahead, 2.1.", ""),
                          [_Lap(9, 7)])
    assert outcome.verdict == CANNOT_TELL and outcome.settled
    assert "board" in outcome.detail


def test_the_race_news_is_reset_with_the_race():
    """Rule 11: a gap said in a rehearsal is not this race's baseline."""
    co = a_race()
    reads(co, "ahead", 2.1, "PUNISHED")
    assert run(co, 1)
    co.arm(None, None)
    co.phase = RacePhase.RUNNING
    co._crossed_at_packet = -10 * 60
    reads(co, "ahead", 2.1, "PUNISHED")
    assert [c.spoken() for c in run(co, 1)] == ["PUNISHED ahead, 2.1."]


def test_a_place_call_is_not_starved_by_the_race_news():
    co = a_race(position=7)
    reads(co, "ahead", 2.1, "PUNISHED")
    said = run(co, 20, packet=_Packet(current_position=6))
    kinds = [c.kind for c in said]
    assert POSITION in kinds
    assert kinds.index(POSITION) == 0 or GAPS in kinds[:1]
