"""Sardegna Rd 9, 16 Sep 2026 (session 188): when does the car behind get here?

The driver, afterwards: *"George wasn't calling that he was gradually closing
the gap and would have been great to know if he was going to catch me before
the race ended or not and if so what predicted lap."*

On file (`fixtures/race_comms_s188.json`, poured by
`tools/extract_race_comms_fixture.py --session 188`): Rocky behind at 7.9 s at
the end of read key 15, closing to 0.7 s by key 23; he was on the bumper
through lap 25 and passed on lap 26, and the flag fell after lap 29. George
gave the gap as a number every lap or two and said "Rocky is catching, 1.0
seconds a lap." once, on lap 22 at 1.8 s - never when, and never whether the
race was long enough (brain measurement 169).

The projection is a multi-lap trend, which CLAUDE.md allows; it is never a
per-corner claim. What it may say rests on the noise of THIS car on THIS night:
the lap-to-lap changes in the gap and their own 95% interval.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pitcrew.race.calls import LOW, MEDIUM, PACE, RaceState
from pitcrew.race.gaps import GapTrend
from pitcrew.race.news import RaceNews, catch_projection
from pitcrew.telemetry.recorder import SAMPLE_HZ

FIXTURE = Path(__file__).parent / "fixtures" / "race_comms_s188.json"
FLAG = 29                     # laps in the race as run: 12 + 17 on the plan


@lru_cache(maxsize=1)
def record() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def rocky_behind() -> GapTrend:
    """The wall's trend of Rocky behind: the last reading of each read key."""
    trend = GapTrend(side="behind")
    for read in sorted(record()["gap_reads"], key=lambda r: r["race_s"]):
        if read["side"] == "behind" and read["subject"] == "Rocky":
            trend.note(read["key"], read["gap_s"], subject="Rocky")
    return trend


# ------------------------------------------------------------ the projection

def test_the_fixture_is_the_race_the_driver_described():
    seen = rocky_behind().seen
    assert round(seen[15], 1) == 7.9 and round(seen[19], 1) == 4.2
    assert round(seen[23], 1) == 0.7


def test_four_laps_of_closing_is_not_yet_a_projection():
    """Keys 15-18: three changes, a slope through noise - the board's own
    five-lap rule (`gaps.MIN_LAPS_FOR_TREND`) holds here too."""
    found, why = catch_projection(rocky_behind(), "behind", now_key=19,
                                  flag_key=FLAG)
    assert found is None and "laps" in why


def test_from_lap_20_rocky_is_on_him_around_lap_25_unconfirmed():
    """Keys 15-19, 4.2 s back: closing 0.93 s a lap with a 95% interval that
    only just excludes zero. The mean lands the catch in lap 25, which is when
    he arrived - but the slow end of the interval never gets there, so the
    range straddles the flag and the claim is not yet a sure one."""
    found, why = catch_projection(rocky_behind(), "behind", now_key=20,
                                  flag_key=FLAG)
    assert found is not None, why
    assert round(found.rate, 1) == 0.9
    assert found.changes == 4 and (found.first_key, found.last_key) == (15, 19)
    assert found.catch_lap(screen_offset=1) == 25
    assert found.before_flag is True
    assert found.sure is False


def test_by_lap_22_the_whole_range_is_before_the_flag():
    found, why = catch_projection(rocky_behind(), "behind", now_key=22,
                                  flag_key=FLAG)
    assert found is not None, why
    assert found.catch_lap(screen_offset=1) == 25
    assert found.before_flag and found.sure


def test_a_car_already_on_the_bumper_is_not_projected():
    """Key 23 closes at 0.7 s: he is there, and the gap line says so."""
    found, _ = catch_projection(rocky_behind(), "behind", now_key=24,
                                flag_key=FLAG)
    assert found is None


def test_a_trend_that_stopped_being_read_projects_nothing():
    """The newest completed key must be the lap just driven: a history last
    read three laps ago is not the car behind now."""
    trend = rocky_behind()
    trend.seen = {k: v for k, v in trend.seen.items() if k <= 21}
    found, why = catch_projection(trend, "behind", now_key=25, flag_key=FLAG)
    assert found is None and "stale" in why


def test_a_dirty_lap_in_the_window_projects_nothing():
    found, why = catch_projection(rocky_behind(), "behind", now_key=22,
                                  flag_key=FLAG, dirty_keys=frozenset({19}))
    assert found is None and "19" in why


def test_a_gap_that_is_not_closing_consistently_projects_nothing():
    """A random walk with a closing-sized mean: the changes' own spread puts
    zero inside the interval."""
    trend = GapTrend(side="behind")
    for key, gap in ((3, 8.0), (4, 5.5), (5, 6.9), (6, 4.6), (7, 5.2)):
        trend.note(key, gap, subject="Rocky")
    found, why = catch_projection(trend, "behind", now_key=8, flag_key=20)
    assert found is None and "noise" in why


def test_a_flag_before_the_catch_says_he_will_not_get_there():
    # Keys 17-21 at the flag after lap 23: even the fast end of the interval
    # arrives after it.
    found, _ = catch_projection(rocky_behind(), "behind", now_key=22,
                                flag_key=23)
    assert found is not None
    assert found.before_flag is False and found.sure is True
    # After lap 24 the mean misses the flag and the fast end does not.
    found, _ = catch_projection(rocky_behind(), "behind", now_key=22,
                                flag_key=24)
    assert found.before_flag is False and found.sure is False


# ----------------------------------------------------------------- the words

def _state(lap: int, *, flag: int = FLAG) -> RaceState:
    state = RaceState()
    state.lap = lap
    state.screen_lap = lap + 1
    state.laps_total = flag
    return state


def _news_with(trend: GapTrend, side: str, name: str | None) -> RaceNews:
    news = RaceNews()
    news._trends[side] = trend
    news._neighbour_name[side] = name
    return news


def test_behind_the_call_says_when_he_gets_here():
    news = _news_with(rocky_behind(), "behind", "Rocky")
    call = news.pace_call(_state(20), 0)
    assert call is not None and call.kind == PACE
    assert call.spoken() == ("Rocky is catching, 0.9 seconds a lap. "
                             "On you around lap 25. Unconfirmed.")
    assert call.confidence == LOW
    # Rule 5: a projection is derived, and the export is told so with its
    # model and its count (rule 4).
    assert call.derived.startswith("derived:")
    assert "4 clean lap changes" in call.derived and "95%" in call.derived


def test_behind_and_confirmed_it_carries_no_hedge():
    news = _news_with(rocky_behind(), "behind", "Rocky")
    call = news.pace_call(_state(22), 0)
    assert call.spoken() == ("Rocky is catching, 1.0 seconds a lap. "
                             "On you around lap 25.")
    assert call.confidence == MEDIUM


def test_behind_with_the_flag_first_he_will_not_get_there():
    news = _news_with(rocky_behind(), "behind", "Rocky")
    call = news.pace_call(_state(22, flag=23), 0)
    assert call.spoken() == ("Rocky is catching, 1.0 seconds a lap. "
                             "Not on you before the flag.")
    assert call.confidence == MEDIUM


def test_ahead_the_mirror_says_when_he_gets_to_him():
    trend = GapTrend(side="ahead")
    for key, gap in ((3, 9.0), (4, 8.0), (5, 7.1), (6, 6.0), (7, 5.1)):
        trend.note(key, gap, subject="PUNISHED")
    news = _news_with(trend, "ahead", "PUNISHED")
    call = news.pace_call(_state(8, flag=20), 0)
    assert call.spoken() == ("Catching PUNISHED, 0.9 seconds a lap. "
                             "On him around lap 14.")
    assert call.confidence == MEDIUM
    call = _news_with(trend, "ahead", "PUNISHED").pace_call(
        _state(8, flag=11), 0)
    assert call.spoken() == ("Catching PUNISHED, 0.9 seconds a lap. "
                             "Not on him before the flag.")


def test_a_handle_whose_readings_jump_is_projected_unconfirmed():
    news = _news_with(rocky_behind(), "behind", "Rocky")
    news._unreliable["Rocky"] = "2 jump(s) nothing on the circuit explains"
    call = news.pace_call(_state(22), 0)
    assert call.confidence == LOW and call.spoken().endswith("Unconfirmed.")


def test_a_handle_that_names_a_slot_is_not_projected():
    news = _news_with(rocky_behind(), "behind", "Rocky")
    news._merged["Rocky"] = "held the slot across a place change"
    assert news.pace_call(_state(22), 0) is None


def test_a_timed_race_whose_distance_is_not_firm_is_unconfirmed():
    news = _news_with(rocky_behind(), "behind", "Rocky")
    state = _state(22)
    state.race_minutes = 50
    state.laps_estimate_firm = False
    assert news.pace_call(state, 0).confidence == LOW


# ------------------------------------------------- one call per real change

def test_the_same_projection_is_not_said_twice():
    news = _news_with(rocky_behind(), "behind", "Rocky")
    first = news.pace_call(_state(22), 0)
    news.book(first)
    assert news.pace_call(_state(23), 0) is None


def test_an_unheard_projection_is_offered_again():
    news = _news_with(rocky_behind(), "behind", "Rocky")
    news.release(news.pace_call(_state(22), 0))
    assert news.pace_call(_state(22), 0) is not None


def test_a_catch_lap_that_moves_two_laps_is_said_again():
    trend = GapTrend(side="behind")
    for key, gap in ((3, 12.0), (4, 11.0), (5, 10.1), (6, 9.0), (7, 8.1)):
        trend.note(key, gap, subject="Rocky")
    news = _news_with(trend, "behind", "Rocky")
    first = news.pace_call(_state(8, flag=30), 0)
    assert "around lap 17" in first.spoken()
    news.book(first)
    # He eases off: the catch drifts out a lap - not news.
    trend.note(8, 7.5, subject="Rocky")
    assert news.pace_call(_state(9, flag=30), 0) is None
    # And further: past a lap either way, it is news.
    trend.note(9, 7.2, subject="Rocky")
    trend.note(10, 6.9, subject="Rocky")
    later = news.pace_call(_state(11, flag=30), 0)
    assert later is not None and "around lap" in later.spoken()


def test_the_plain_pace_figure_does_not_follow_a_projection_of_the_same_car():
    """Rule 13: one car, one rate. Once the catch has been said, the board's
    trimmed-median figure for the same car and direction must not follow it
    as a second, different "seconds a lap"."""
    news = _news_with(rocky_behind(), "behind", "Rocky")
    news.book(news.pace_call(_state(20), 0))
    for lap in (21, 22, 23, 24):
        call = news.pace_call(_state(lap), 0)
        if call is not None:
            assert "around lap" in call.spoken(), call.spoken()
            news.book(call)


def test_a_confirmed_catch_speaks_the_boards_own_figure():
    """Rule 13, critic 19 Sep: at s188 lap 22 George said "0.9 seconds a lap"
    off the mean of the changes while the board and push-to-talk said
    "catching 1.0 s a lap" for the same car. Once the board is saying a rate,
    the call says that rate - the mean still sets the lap."""
    from pitcrew.race.gaps import trend_words
    trend = rocky_behind()
    call = _news_with(trend, "behind", "Rocky").pace_call(_state(22), 0)
    found, _ = catch_projection(trend, "behind", now_key=_state(22).lap_now(),
                                flag_key=FLAG)
    board = trend_words("behind", found.board_rate, found.changes + 1)
    assert board is not None
    assert f"{abs(found.board_rate):.1f} seconds a lap" in call.spoken()
    assert f"{found.rate:.2f} s/lap" in call.derived      # the mean, audited
    assert f"board rate {found.board_rate:+.2f} s/lap" in call.derived


def test_a_hud_behind_our_count_withholds_the_lap_rather_than_clamping():
    """Rule 9: GT7's lap number behind our drop-corrected count means the
    correction is wrong. It was `max(0, ...)`, which named a lap anyway."""
    state = _state(22)
    state.screen_lap = 21                  # the HUD a lap BEHIND lap_now()
    assert state.lap_on_screen() - state.lap_now() < 0
    assert _news_with(rocky_behind(), "behind", "Rocky").pace_call(
        state, 0) is None


# ---------------------------------------------------- the race as it was run

def replay() -> list[tuple[int, str, str]]:
    """Every gap reading at its moment, every crossing, the pace slot asked
    after every reading - `(lap, spoken, confidence)` for each pace call."""
    data = record()
    news = RaceNews()
    state = RaceState()
    state.laps_total = FLAG
    crossings = sorted(data["laps"], key=lambda lap: lap["race_elapsed_s"])
    said = []
    for read in sorted(data["gap_reads"], key=lambda r: r["race_s"]):
        while crossings and crossings[0]["race_elapsed_s"] <= read["race_s"]:
            lap = crossings.pop(0)
            dirty = ("our pit lap" if lap["is_pit_lap"] else
                     "our out lap" if lap["is_out_lap"] else
                     "lap one" if lap["lap_num"] <= 1 else None)
            news.note_lap(state.lap_now(), lap["lap_num"],
                          lap["lap_time_ms"] / 1000.0, dirty)
            state.lap = lap["lap_num"]
            state.screen_lap = lap["laps_completed"]
        subject = read["subject"]
        name = None if subject is None or str(subject).isdigit() else subject
        packet = int(read["race_s"] * SAMPLE_HZ)
        news.note_gap(read["side"], read["gap_s"], subject, name,
                      packet=packet, lap_key=state.lap_now())
        call = news.pace_call(state, packet)
        if call is not None:
            said.append((state.lap, call.spoken(), call.confidence))
            news.book(call)
    return said


def test_session_188_hears_when_rocky_arrives_from_lap_20():
    about_rocky = [(lap, words, conf) for lap, words, conf in replay()
                   if "Rocky" in words]
    assert about_rocky == [
        (20, "Rocky is catching, 0.9 seconds a lap. On you around lap 25. "
             "Unconfirmed.", LOW),
        (22, "Rocky is catching, 1.0 seconds a lap. On you around lap 25.",
         MEDIUM),
    ]


def test_session_188_the_other_pace_calls_are_unchanged():
    others = [words for _, words, _ in replay() if "Rocky" not in words]
    assert others == [
        "Pulling away from TommyTbone, 1.7 seconds a lap. Over 5 laps.",
        "Losing 0.9 seconds a lap to the car ahead. Over 5 laps. "
        "Unconfirmed.",
    ]


# ------------------------------------------------------------ the export

def test_the_projection_reaches_the_export_labelled_derived(tmp_path):
    """Rule 5, three places deep: the revision payload, `_calls_made`, and the
    `callsMade[]` projection - with `payload.KNOWN_KEYS` and the contract
    agreeing, or the validator refuses the whole export."""
    from pitcrew.export.build import _calls_made, _strategy_section
    from pitcrew.export.payload import KNOWN_KEYS, _validate_known_keys
    from pitcrew.store.db import Store

    call = _news_with(rocky_behind(), "behind", "Rocky").pace_call(
        _state(20), 0)
    store = Store(tmp_path / "catch.db")
    try:
        event_id = store.create_event(name="x", track="Sardegna",
                                      layout="Road Track - A",
                                      car_name="car", race_type="laps",
                                      race_laps=29)
        strategy_id = store.save_strategy(
            event_id, {"export": {"stops": 1, "totalRaceTimeS": 3000.0}})
        store.approve_strategy(strategy_id)
        session_id = store.start_session(event_id, "race")
        run_id = store.start_race_run(event_id, strategy_id, session_id)
        store.append_revision(run_id, call.lap, call.call, {
            "call": call.as_export(), "confidence": call.confidence,
            "kind": call.kind, "why_spoken": call.why_spoken,
            "informational": True, "derived": call.derived})
        store.append_revision(run_id, 21, "Rocky behind, 3.0.",
                              {"kind": "gaps", "confidence": "medium"})
        made = _calls_made(store, event_id)
        assert made[0]["derived"] == call.derived
        assert "derived" not in made[1], "absent where nothing was projected"
        section = _strategy_section(store, event_id)
        exported = section["callsMade"]
        assert exported[0]["derived"].startswith("derived:")
        assert "derived" not in exported[1]
        assert "derived" in KNOWN_KEYS["strategy.callsMade[]"]
        assert _validate_known_keys({"strategy": {"callsMade": exported}}) \
            == []
    finally:
        store.close()
    contract = (Path(__file__).resolve().parents[2]
                / "EXPORT-CONTRACT.md").read_text(encoding="utf-8")
    assert "`derived` is present only on a call" in contract



# --------------------------------------------- his tyres (19 Sep 2026)
#
# The driver, the day after: *"using our tyre model george should be able to
# tell me how his tyres will be when he is catching me ... Rocky is catching
# but based on his last stop his tyres will be off the cliff in the last lap
# so keep fighting. This is critical information for george to pass to me."*
#
# Rocky stopped at the end of his lap 14 on medium - read off the race video
# frame by frame, because the pit wall of the night refused every medium disc
# on shape and never filed his stop (fixed in 6aa64aa). Our RM rate at this
# circuit and multiplier is 0.068 worn a lap over 3 stints (race_knowledge 13).
# He ran 15 laps on the set; on the final lap he fell from 0.6 s ahead in P3
# to 17 s behind in P5.

RM_RATE = 0.068
# **Gauge readings, not stints** (critic, 19 Sep): Sardegna's RM rate rests on
# 24 readings from two stints, and this was labelled "3 stints".
RM_READINGS = 24
RM_STINTS = RM_READINGS                  # the older tests' name for it


def _rocky_stopped(seen=False):
    """Rocky's stop at the end of his lap 14, on medium. `seen` is whether the
    disc was caught changing as he left the lane (it read M both sides)."""
    from pitcrew.race.rival_calls import Rival
    from pitcrew.race.rivals import Stop

    return Rival(name="Rocky", pitted=True,
                 stop=Stop(lap=14, fuel_in_l=19.0, fuel_out_l=89.0,
                           compound="M", compound_in="M",
                           tyres_changed=True if seen else None))


class _Knowledge:
    """`Knowledge.wear_per_lap`, holding the one rate on file for RM here."""

    def __init__(self, rate=RM_RATE):
        self.rate = rate

    def wear_per_lap(self, code, multiplier=None):
        return (self.rate, RM_READINGS) if code == "RM" else (None, 0)


def _race_at(lap, *, rival=None, rate=RM_RATE, side="behind"):
    """A coordinator at `lap` of Sardegna Rd 9, Rocky filed as `rival`."""
    from pitcrew.race.coordinator import RaceCoordinator

    co = RaceCoordinator()
    co.state.lap = lap
    co.state.screen_lap = lap + 1
    co.state.laps_total = FLAG
    co.state.tyre_compound = "RH"
    co.state.tyre_wear_mult = "8"
    co.knowledge = _Knowledge(rate)
    if rival is not None:
        co.state.rivals = {"Rocky": rival}
    co.news._neighbour_name[side] = "Rocky"
    return co


def test_george_says_rockys_tyres_go_off_before_the_flag():
    """**The call he asked for, on the race he asked it about.**

    Its own call now, not a clause on the catch call - which spoke only when
    the catch CHANGED, went silent inside 1.5 s, named the car (so no clip
    could hold it) and put the instruction fourth (critic, 19 Sep).
    """
    co = _race_at(22, rival=_rocky_stopped(seen=True))
    call = co._rival_tyres_call(co.state)
    assert call is not None
    assert call.spoken() == ("Keep fighting. "
                             "The car behind's tyres go off around lap 28.")
    assert "[DERIVED]" in call.derived
    assert "[READ] he left on RM" in call.derived
    # Rule 4, and labelled as what it is: gauge readings, not stints.
    assert f"{RM_READINGS} gauge readings" in call.derived
    assert "x8" in call.derived                    # the multiplier, stated


def test_an_assumed_compound_gets_the_fact_and_not_the_instruction():
    """**"Keep fighting." only where it is earned.** With no change seen at
    the lane exit, arriving on RM and leaving on RH looks identical to a
    refit - and at RH's rate the cliff falls after the flag. So he hears the
    fact, marked unconfirmed, and no instruction to defend on it."""
    co = _race_at(22, rival=_rocky_stopped(seen=False))
    call = co._rival_tyres_call(co.state)
    assert call.spoken() == ("The car behind's tyres go off around lap 28. "
                             "Unconfirmed.")
    assert "Keep fighting" not in call.spoken()
    assert "[ASSUMED] he left on the RM he arrived on" in call.derived


def test_it_is_said_even_with_him_on_the_bumper():
    """The catch call went quiet inside 1.5 s. This does not look at the gap
    at all - the lap he is on the bumper is the lap it matters."""
    co = _race_at(24, rival=_rocky_stopped(seen=True))
    assert co._rival_tyres_call(co.state) is not None


def test_once_heard_a_set_is_not_told_again_but_a_dropped_one_is():
    """Booked when HEARD, like the rival stop - so a line the voice drops is
    tried again, and one he heard is not repeated every lap."""
    co = _race_at(22, rival=_rocky_stopped(seen=True))
    call = co._rival_tyres_call(co.state)
    assert co._heard_matters(call)
    co._book(call)                                  # heard
    assert co._rival_tyres_call(co.state) is None
    fresh = _race_at(22, rival=_rocky_stopped(seen=True))
    first = fresh._rival_tyres_call(fresh.state)
    fresh._release(first)                           # dropped
    assert fresh._rival_tyres_call(fresh.state) is not None


def test_a_car_ahead_going_off_is_news_not_an_instruction():
    co = _race_at(22, rival=_rocky_stopped(seen=True), side="ahead")
    call = co._rival_tyres_call(co.state)
    assert call.spoken() == "The car ahead's tyres go off around lap 28."


def test_with_no_stop_on_file_nothing_is_said():
    """What happened that night: the wall never filed his medium stop."""
    co = _race_at(22)
    assert co._rival_tyres_call(co.state) is None


def test_a_set_that_lasts_past_the_flag_is_not_mentioned():
    """At half our rate his set would last 26 laps from lap 14 - past the
    flag, so it changes nothing he does."""
    co = _race_at(22, rival=_rocky_stopped(seen=True), rate=0.034)
    assert co._rival_tyres_call(co.state) is None


def test_a_cliff_already_behind_him_is_not_claimed():
    from pitcrew.race.rival_calls import Rival
    from pitcrew.race.rivals import Stop

    old = Rival(name="Rocky", pitted=True,
                stop=Stop(lap=4, fuel_in_l=19.0, fuel_out_l=89.0,
                          compound="M", compound_in="M", tyres_changed=True))
    co = _race_at(22, rival=old)
    assert co._rival_tyres_call(co.state) is None


def test_no_rate_for_his_compound_here_means_no_claim():
    """`Knowledge.wear_per_lap` refuses a rate measured at another multiplier
    (§5.2) and has nothing for a compound never run here."""
    co = _race_at(22, rival=_rocky_stopped(seen=True), rate=None)
    assert co._rival_tyres_call(co.state) is None


def test_the_projection_puts_rocky_at_the_cliff_on_lap_28():
    from pitcrew.race.rival_tyres import CLIFF_WORN, rival_tyres

    got = rival_tyres(_rocky_stopped(), now_key=22, our_compound="RH",
                      wear_rate=lambda code: (RM_RATE, RM_STINTS))
    assert got.compound == "RM"             # "M" on the disc, R from the race
    assert got.laps_on_set == 8
    assert abs(got.worn_now - 0.544) < 0.01
    assert CLIFF_WORN == 0.90               # the cliff, not our 0.85 limit
    assert abs(got.cliff_key - (14 + 0.90 / RM_RATE)) < 1e-9
    assert got.cliff_lap(screen_offset=1) == 28


def test_a_compound_letter_takes_the_races_family_or_nothing():
    from pitcrew.race.rival_tyres import full_code

    assert full_code("M", "RH") == "RM"
    assert full_code("S", "SM") == "SS"
    assert full_code(None, "RH") is None            # nothing read
    assert full_code("M", None) is None             # no family to give it
    assert full_code("M", "IM") is None             # a wet race is not dry
    assert full_code("IM", "RH") == "IM"            # a whole code stands


def test_a_stop_filed_ahead_of_now_is_not_a_negative_set():
    """Rule 9: a stop in another lap domain is refused, not clamped to zero
    laps on the set."""
    from pitcrew.race.rival_tyres import rival_tyres

    assert rival_tyres(_rocky_stopped(), now_key=10, our_compound="RH",
                       wear_rate=lambda code: (RM_RATE, RM_STINTS)) is None


def test_a_compound_change_seen_at_the_lane_exit_is_a_reading():
    """**The disc changes only as the car exits the pit lane** (the driver,
    19 Sep 2026). So the last read is the tyre he fitted, and where it
    differs from the one he arrived on the change was SEEN - no assumption
    about his compound is left in the call."""
    from pitcrew.race.rival_calls import Rival
    from pitcrew.race.rival_tyres import rival_tyres
    from pitcrew.race.rivals import Stop

    changed = Rival(name="Rocky", pitted=True,
                    stop=Stop(lap=14, fuel_in_l=19.0, fuel_out_l=89.0,
                              compound="H", compound_in="M",
                              tyres_changed=True))
    got = rival_tyres(changed, now_key=22, our_compound="RH",
                      wear_rate=lambda code: (0.04, 2) if code == "RH"
                      else (None, 0))
    assert got.compound == "RH" and got.compound_seen is True
    assert "[READ] he left on RH" in got.model()
    assert "arrived on" not in got.model()


def test_the_wall_files_the_tyre_he_left_on_not_the_one_he_came_in_on():
    """A vote across the stop is the ARRIVAL tyre: the disc shows it for the
    whole stand and flips for a frame or two as he goes. Filing the vote -
    as the wall did until 19 Sep - filed every compound change backwards."""
    from pitcrew.race.pit_wall import Visit

    def flipped(**over):
        """A stand on M, then the flip as he leaves: read off his own disc,
        on the last frame his columns showed, with the fill finished, and
        the visit closed on seeing his row back without columns."""
        visit = Visit(driver=1, lap=14, started_s=0.0, last_s=90.0,
                      readings=[19, 60, 89, 89],
                      compounds=["M"] * 18 + ["H"],
                      last_compound_l=89, last_compound_s=90.0,
                      closed_on_absence=True)
        for key, value in over.items():
            setattr(visit, key, value)
        return visit

    visit = flipped()
    assert visit.arrived_on == "M"
    assert visit.left_on == "H"
    assert visit.compound == "H"
    assert visit.compound_changed is True
    stop = visit.as_stop()
    assert (stop.compound, stop.compound_in, stop.tyres_changed) == (
        "H", "M", True)

    # **One frame is all a flip gets, so one frame is all scenery needs**
    # (critic, 19 Sep: 197 of 211 scenery reads on that race came back H).
    # Each condition refuses on its own, and a refused flip files the
    # arrival tyre with nothing claiming a change.
    for why, over in (
            ("closed on the silence clock - its last read was mid-stand",
             {"closed_on_absence": False}),
            ("not the tail - a later frame of columns had no tyre read",
             {"last_s": 92.0}),
            ("mid-fill - the flip frame's fuel is not the final figure",
             {"last_compound_l": 60})):
        refused = flipped(**over)
        assert refused.left_on is None, why
        stop = refused.as_stop()
        assert (stop.compound, stop.tyres_changed) == ("M", None), why
    # Where the digits did not read on the flip frame, that is not a refusal.
    assert flipped(last_compound_l=None).left_on == "H"

    # No flip seen: a same-compound refit, or one the grab missed. The best
    # estimate is the arrival tyre, and nothing claims the tyres changed.
    same = Visit(driver=1, lap=14, started_s=0.0, compounds=["M"] * 19)
    stop = same.as_stop()
    assert (stop.compound, stop.compound_in) == ("M", "M")
    assert stop.tyres_changed is None
