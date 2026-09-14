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


def test_the_pace_call_through_the_race_names_him_and_says_the_count():
    co = a_race()
    for key in range(1, 9):
        co.state.lap = key
        for _ in range(3):
            co.note_gap_read("ahead", 10.0 - 1.0 * key, subject="PUNISHED",
                             name="PUNISHED")
        co.news.note_lap(key, key + 1, 120.0)
    co.state.lap = 9
    co.news._said_gap["ahead"] = ("PUNISHED", co.news._band["ahead"])
    co.news._gap_lap = co.state.lap_now()
    said = run(co, 1)
    assert [c.spoken() for c in said] == [
        "Catching PUNISHED, 1.0 seconds a lap. Over 5 laps."]
    assert said[0].kind == PACE and said[0].confidence == MEDIUM
    assert "95%" in said[0].why_spoken


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
