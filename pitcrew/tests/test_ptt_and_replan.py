"""What the driver can ask, and when the plan gets re-thought."""
from __future__ import annotations

import pytest

from pitcrew.engineer.intents import (
    ACCEPT,
    BOX_FUEL,
    BOX_WHAT,
    BOX_WHEN,
    FUEL,
    KEEP,
    LAPS_LEFT,
    PLAN,
    POSITION,
    REPEAT,
    REPORT_OVERSTEER,
    REPORT_UNDERSTEER,
    UNKNOWN,
    answer,
    known_phrases,
    match_intent,
)
from pitcrew.engineer.shift_beep import (
    DOWNSHIFT_MUTE_S,
    ShiftBeep,
    driving_gate,
    should_beep,
)
from pitcrew.race.replan import (
    NONE,
    RECOMMENDED,
    URGENT,
    assess,
    drift,
    observed_fuel_per_lap,
)
from pitcrew.strategy.model import RaceInputs

from .conftest import make_packet
from .test_controller import qt_app  # noqa: F401


def a_snapshot(**overrides) -> dict:
    base = {"lap": 8, "lapsTotal": 20, "lapsRemaining": 12, "position": 3,
            "fuelL": 40.0, "lapsOfFuel": 11.8, "lapsToStop": 2,
            "nextCompound": "RS", "stopFuelL": 37.0, "inPit": False,
            # The coordinator's snapshot says whether there is a plan at all,
            # because "no stop planned, running to the flag" and "there is no
            # plan" both arrive as `lapsToStop is None`.
            "hasPlan": True}
    base.update(overrides)
    return base


# ------------------------------------------------------------------ intents

@pytest.mark.parametrize("heard,expected", [
    ("how much fuel", FUEL),
    ("fuel", FUEL),
    ("where am I", POSITION),
    ("how many laps", LAPS_LEFT),
    ("when do I box", BOX_WHEN),
    ("what tyres", BOX_WHAT),
    ("how much fuel do I take", BOX_FUEL),
    ("what's the plan", PLAN),
    ("say again", REPEAT),
    ("copy that", ACCEPT),
    ("keep the plan", KEEP),
])
def test_phrases_map_to_intents(heard, expected):
    assert match_intent(heard) == expected


def test_the_longest_phrase_wins():
    """'how much fuel do I take' must not be swallowed by 'fuel'."""
    assert match_intent("how much fuel do i take") == BOX_FUEL


def test_nonsense_is_unknown_rather_than_the_nearest_guess():
    assert match_intent("what's the weather in Tokyo") == UNKNOWN
    assert match_intent("") == UNKNOWN


@pytest.mark.parametrize("heard", [
    "blah blah nonsense",                  # matched "no" inside "nonsense"
    "what is the tyre temperature",        # matched "p" in "temperature"
    "not yet",                             # matched "no" inside "not"
])
def test_free_dictation_that_means_nothing_is_unknown(heard):
    """Matching was `if phrase in text`, a substring test, with `"p"` and
    `"no"` in the phrase list. Every one of these came back as a confident
    answer, and one of them - "no" as KEEP - silently declined a re-plan the
    driver never said a word about. UNKNOWN has to be reachable or "say
    again" is dead and the refusal `intents` calls a real outcome is a lie."""
    assert match_intent(heard) == UNKNOWN


@pytest.mark.parametrize("heard,wrong,right", [
    # matched "p" -> position, before whole-word matching
    ("the front is pushing on entry", POSITION, REPORT_UNDERSTEER),
    # matched "no" -> keep, and silently declined a re-plan
    ("i have no grip at the rear", KEEP, REPORT_OVERSTEER),
])
def test_a_sentence_about_the_car_reaches_the_report_that_owns_it(
        heard, wrong, right):
    """**These two used to be asserted UNKNOWN, and that assertion has been
    split rather than deleted.**

    What the original guarded was that a substring match could not turn a
    sentence about the car into a confident wrong answer - "p" inside
    "pushing" answering with a race position. UNKNOWN was the proxy for that,
    and it was the right proxy while the app had no way to receive a handling
    report at all.

    The REPORT family gives these sentences somewhere correct to go, so the
    proxy has stopped describing the property. The property itself is
    unchanged and is now asserted directly: never the old wrong intent, and
    now the right one."""
    got = match_intent(heard)
    assert got != wrong
    assert got == right


def test_a_phrase_only_matches_as_whole_words():
    assert match_intent("keeping it steady") == UNKNOWN     # not "keep"
    assert match_intent("keep the plan") == KEEP
    assert match_intent("strategic") == UNKNOWN             # not "strategy"


def test_nothing_shorter_than_three_letters_is_a_phrase():
    """One- and two-letter phrases cannot be heard reliably and cannot fail to
    match something. They are what made UNKNOWN unreachable."""
    for phrase in known_phrases():
        assert len(phrase) >= 3, phrase


def test_an_unknown_question_asks_him_to_repeat():
    reply = answer(UNKNOWN, a_snapshot())
    assert reply.text == "Say again."
    assert reply.answered is False


# ------------------------------------------------------------------ answers

def test_position_is_answered():
    assert answer(POSITION, a_snapshot()).text == "P3."


def test_laps_left_is_answered():
    assert answer(LAPS_LEFT, a_snapshot()).text == "12 laps to go."


def test_one_lap_is_singular():
    assert answer(LAPS_LEFT, a_snapshot(lapsRemaining=1)).text == "1 lap to go."


def test_fuel_is_answered_in_laps_not_litres():
    """Laps is what he can act on at 200 km/h; litres is arithmetic."""
    assert "11.8 laps of fuel" in answer(FUEL, a_snapshot()).text


def test_the_box_call_is_answered():
    assert answer(BOX_WHEN, a_snapshot()).text == "Box in 2 laps."
    assert answer(BOX_WHEN, a_snapshot(lapsToStop=0)).text == "Box this lap."


def test_no_stop_planned_is_said_plainly():
    """The last stint of a real plan. There IS a plan and it runs to the end."""
    reply = answer(BOX_WHEN, a_snapshot(lapsToStop=None))
    assert "flag" in reply.text
    assert reply.answered is True


def test_no_plan_at_all_is_refused_rather_than_asserted():
    """The other state `lapsToStop is None` covers, and a supported one -
    a race can be armed with no plan, for fuel calls only. Saying "running to
    the flag" there asserts a plan that does not exist."""
    reply = answer(BOX_WHEN, a_snapshot(lapsToStop=None, hasPlan=False))
    assert reply.answered is False
    assert "flag" not in reply.text
    assert "don't have a plan" in reply.text


def test_a_snapshot_that_does_not_say_is_treated_as_no_plan():
    """Missing is missing (CLAUDE.md §4.3). An empty snapshot is what the
    controller returns before a race is armed at all."""
    assert answer(BOX_WHEN, {}).answered is False
    assert answer(BOX_WHAT, {}).answered is False
    assert answer(PLAN, {}).answered is False


def test_the_compound_and_the_plan_refuse_the_same_way():
    assert answer(BOX_WHAT, a_snapshot(nextCompound=None)).answered is True
    assert answer(BOX_WHAT, a_snapshot(nextCompound=None,
                                       hasPlan=False)).answered is False
    assert answer(PLAN, a_snapshot(hasPlan=False)).answered is False


def test_the_compound_is_answered():
    assert answer(BOX_WHAT, a_snapshot()).text == "RS."


def test_the_fuel_target_is_answered():
    assert "37 litres" in answer(BOX_FUEL, a_snapshot()).text


def test_the_plan_is_one_sentence():
    text = answer(PLAN, a_snapshot()).text
    assert text.count(".") == 1
    assert "Box in 2 laps" in text and "RS" in text


# ----------------------------------------------------------------- refusals

def test_missing_position_is_refused_not_guessed():
    reply = answer(POSITION, a_snapshot(position=None))
    assert reply.answered is False
    assert "don't have" in reply.text


def test_missing_fuel_rate_is_refused():
    reply = answer(FUEL, a_snapshot(lapsOfFuel=None))
    assert reply.answered is False
    assert "fuel rate" in reply.text


def test_unknown_race_length_is_refused():
    reply = answer(LAPS_LEFT, a_snapshot(lapsRemaining=None))
    assert reply.answered is False


def test_repeat_with_nothing_said_is_refused():
    assert answer(REPEAT, a_snapshot()).answered is False


def test_repeat_returns_the_last_call():
    reply = answer(REPEAT, a_snapshot(), last_call="Box this lap. RS.")
    assert reply.text == "Box this lap. RS."


def test_accepting_nothing_is_refused():
    assert answer(ACCEPT, a_snapshot()).answered is False


def test_accepting_a_pending_replan_is_confirmed():
    reply = answer(ACCEPT, a_snapshot(), pending_replan="1 stop")
    assert "changing the plan" in reply.text


def test_keeping_the_plan_is_confirmed():
    reply = answer(KEEP, a_snapshot(), pending_replan="1 stop")
    assert "staying on the plan" in reply.text


def test_every_phrase_is_reachable():
    for phrase in known_phrases():
        assert match_intent(phrase) != UNKNOWN


# --------------------------------------------------------------- shift beep

def test_the_beep_only_fires_on_track():
    """It used to beep in the pit lane, the garage and replays."""
    assert driving_gate(True, False, False) is True
    assert driving_gate(False, False, False) is False
    assert driving_gate(True, True, False) is False
    assert driving_gate(True, False, True) is False


def test_the_beep_fires_once_at_the_threshold():
    beep, above, muted = should_beep(
        prev_gear=3, cur_gear=3, rpm=7100, threshold=7000, shift_above=False,
        enabled=True, downshift_muted_until=0.0, now=1.0)
    assert beep is True and above is True

    again, _, _ = should_beep(
        prev_gear=3, cur_gear=3, rpm=7200, threshold=7000, shift_above=above,
        enabled=True, downshift_muted_until=muted, now=1.1)
    assert again is False


def test_the_beep_re_arms_once_rpm_drops():
    _, above, _ = should_beep(
        prev_gear=3, cur_gear=3, rpm=6000, threshold=7000, shift_above=True,
        enabled=True, downshift_muted_until=0.0, now=1.0)
    assert above is False


def test_a_downshift_mutes_the_blip():
    """Heel-and-toe spikes the rpm; without this every downshift beeped."""
    beep, above, muted = should_beep(
        prev_gear=4, cur_gear=3, rpm=7500, threshold=7000, shift_above=False,
        enabled=True, downshift_muted_until=0.0, now=10.0)
    assert beep is False
    assert above is True
    assert muted == pytest.approx(10.0 + DOWNSHIFT_MUTE_S)


def test_neutral_and_reverse_never_beep():
    for gear in (0, 9, -1):
        beep, _, _ = should_beep(
            prev_gear=3, cur_gear=gear, rpm=9000, threshold=7000,
            shift_above=False, enabled=True, downshift_muted_until=0.0,
            now=1.0)
        assert beep is False


def test_disabling_it_silences_it():
    beep, _, _ = should_beep(
        prev_gear=3, cur_gear=3, rpm=9000, threshold=7000, shift_above=False,
        enabled=False, downshift_muted_until=0.0, now=1.0)
    assert beep is False


def test_the_wrapper_beeps_through_a_gear_change():
    tones = []
    beeper = ShiftBeep(per_gear={3: 7000.0},
                       tone=lambda: tones.append(1))
    beeper.update(make_packet(gear_raw=0x13, engine_rpm=6000.0), now=1.0)
    beeper.update(make_packet(gear_raw=0x13, engine_rpm=7200.0), now=1.1)
    assert tones == [1]


def test_the_wrapper_stays_silent_off_track():
    tones = []
    beeper = ShiftBeep(tone=lambda: tones.append(1))
    beeper.update(make_packet(gear_raw=0x13, engine_rpm=9000.0,
                              on_track=False), now=1.0)
    assert tones == []


def test_a_failing_tone_does_not_stop_the_telemetry_thread():
    def explode():
        raise RuntimeError("no audio device")

    beeper = ShiftBeep(per_gear={3: 7000.0}, tone=explode)
    beeper.update(make_packet(gear_raw=0x13, engine_rpm=6000.0), now=1.0)
    assert beeper.update(make_packet(gear_raw=0x13, engine_rpm=7200.0),
                         now=1.1) is True


def test_the_test_button_reports_a_beep_that_did_not_sound():
    """The control exists to prove the beep is audible over the engine, so it
    has to be able to say no. `_play` swallows the exception and `play_now`
    returned True regardless, so a beep into a dead device reported success."""
    def explode():
        raise RuntimeError("no audio device")

    beeper = ShiftBeep(tone=explode)
    assert beeper.play_now() is False
    assert "no audio device" in beeper.last_error


def test_the_test_button_still_reports_a_beep_that_did_sound():
    tones = []
    beeper = ShiftBeep(tone=lambda: tones.append(1))
    assert beeper.play_now() is True
    assert tones == [1] and beeper.last_error is None


def test_no_tone_device_at_all_is_still_a_no():
    """`tone=None` means "find the default"; a machine with no tone device is
    the one where that search comes back empty."""
    beeper = ShiftBeep(tone=lambda: None)
    beeper._tone = None
    assert beeper.play_now() is False


# ------------------------------------------------------------------ replan

def an_inputs(**overrides) -> RaceInputs:
    fields = dict(race_laps=20, lap_time_ms=94_000, fuel_per_lap_l=3.4,
                  fuel_capacity_l=100.0, wear_per_lap=0.05,
                  available_compounds=("RM",))
    fields.update(overrides)
    return RaceInputs(**fields)


def test_burn_is_the_median_so_one_odd_lap_cannot_move_it():
    assert observed_fuel_per_lap([3.4, 3.5, 0.9, 3.4, 3.45]) == 3.4


def test_no_burn_recorded_is_unknown():
    assert observed_fuel_per_lap([]) is None


def test_drift_needs_both_sides():
    assert drift(3.6, 3.4) == pytest.approx(0.059, abs=0.001)
    assert drift(None, 3.4) is None
    assert drift(3.6, None) is None


def test_a_race_on_the_plan_says_nothing():
    """Fifteen laps to run on 45 litres at 3.42 a lap is 13.2 laps of fuel.
    The stop the plan already has is the answer, so the answer has not
    changed."""
    verdict = assess(laps_done=5, laps_total=20, fuel_l=45.0,
                     planned_fuel_per_lap=3.4, observed_fuel_per_lap_l=3.42,
                     lap_time_ms=94_100, planned_lap_time_ms=94_000,
                     current_stops=1, inputs=an_inputs())
    assert verdict.verdict == NONE
    assert verdict.offered is False


def test_running_short_of_the_flag_is_urgent():
    """Whatever the model prefers, not reaching the end outranks it."""
    verdict = assess(laps_done=5, laps_total=20, fuel_l=20.0,
                     planned_fuel_per_lap=3.4, observed_fuel_per_lap_l=3.4,
                     lap_time_ms=94_000, planned_lap_time_ms=94_000,
                     current_stops=0, inputs=an_inputs())
    assert verdict.verdict == URGENT
    assert "short of the flag" in verdict.reason
    assert verdict.confidence == "high"


def test_a_material_fuel_drift_is_noticed():
    verdict = assess(laps_done=8, laps_total=20, fuel_l=60.0,
                     planned_fuel_per_lap=3.4, observed_fuel_per_lap_l=4.2,
                     lap_time_ms=94_000, planned_lap_time_ms=94_000,
                     current_stops=1, inputs=an_inputs())
    assert "more fuel" in verdict.reason


def test_a_small_drift_is_not_itself_the_finding():
    """**The drift no longer gates the thinking, so it no longer gates the
    answer either.** This used to assert silence on a 1.5% drift, because a
    drift under the threshold meant `recommend` was never called at all. The
    engineer now re-solves every lap, and with 60 litres aboard and twelve
    laps left at 3.45 a lap, the honest answer is that the planned stop is not
    needed - which has nothing to do with the size of the drift, and the
    reason says so.

    Whether he HEARS it is `PlanRegister`'s decision, not this function's."""
    verdict = assess(laps_done=8, laps_total=20, fuel_l=60.0,
                     planned_fuel_per_lap=3.4, observed_fuel_per_lap_l=3.45,
                     lap_time_ms=94_200, planned_lap_time_ms=94_000,
                     current_stops=1, inputs=an_inputs())
    assert verdict.stops == 0
    assert "fuel than planned" not in verdict.reason


def test_the_fuel_already_in_the_car_bounds_the_first_stint():
    """`recommend` bounds every stint by a full tank, which is right for a
    race that starts on the grid and wrong for one re-planned on lap five with
    half a tank. Fifteen laps to go at 3.42 needs 51.3 litres; with 45 aboard
    the run to the flag does not fit, and ranking it first would cancel a stop
    the driver cannot do without."""
    verdict = assess(laps_done=5, laps_total=20, fuel_l=45.0,
                     planned_fuel_per_lap=3.4, observed_fuel_per_lap_l=3.42,
                     lap_time_ms=94_100, planned_lap_time_ms=94_000,
                     current_stops=1, inputs=an_inputs())
    assert verdict.verdict == NONE
    assert verdict.stops == 1


def test_a_plan_that_needs_him_to_save_never_pretends_otherwise():
    """Half a lap short is inside what lift-and-coast closes - it is the same
    figure the stay-out fold uses for a car with no measured short-shift
    slope. **But it is never silent.** Recommending a shape that depends on
    him saving fuel, without saying so, would be the app betting his race on a
    lever it never mentioned."""
    verdict = assess(laps_done=5, laps_total=20, fuel_l=50.0,
                     planned_fuel_per_lap=3.4, observed_fuel_per_lap_l=3.42,
                     lap_time_ms=94_100, planned_lap_time_ms=94_000,
                     current_stops=1, inputs=an_inputs())
    assert verdict.stops == 0
    assert "laps short at this burn" in verdict.reason
    assert "short-shift and lift" in verdict.reason
    assert verdict.confidence == "low"


def test_a_drift_the_plan_still_wins_changes_nothing():
    """Something changed, but not enough to be worth the disruption."""
    verdict = assess(laps_done=8, laps_total=20, fuel_l=60.0,
                     planned_fuel_per_lap=3.4, observed_fuel_per_lap_l=3.6,
                     lap_time_ms=94_000, planned_lap_time_ms=94_000,
                     current_stops=1, inputs=an_inputs())
    assert verdict.verdict in (NONE, RECOMMENDED)
    if verdict.verdict == NONE:
        assert "still wins" in verdict.reason


def test_nothing_to_replan_with_says_so_rather_than_inventing():
    verdict = assess(laps_done=8, laps_total=20, fuel_l=60.0,
                     planned_fuel_per_lap=3.4, observed_fuel_per_lap_l=4.5,
                     lap_time_ms=94_000, planned_lap_time_ms=94_000,
                     current_stops=1, inputs=None)
    assert verdict.verdict == RECOMMENDED
    assert verdict.confidence == "low"
    assert verdict.stops is None


def test_a_finished_race_is_not_replanned():
    verdict = assess(laps_done=20, laps_total=20, fuel_l=5.0,
                     planned_fuel_per_lap=3.4, observed_fuel_per_lap_l=3.4,
                     lap_time_ms=94_000, planned_lap_time_ms=94_000,
                     current_stops=1, inputs=an_inputs())
    assert verdict.verdict == NONE


def test_an_offer_is_phrased_as_a_recommendation():
    """Offered, never imposed - the driver is the one racing."""
    verdict = assess(laps_done=5, laps_total=20, fuel_l=20.0,
                     planned_fuel_per_lap=3.4, observed_fuel_per_lap_l=3.4,
                     lap_time_ms=94_000, planned_lap_time_ms=94_000,
                     current_stops=0, inputs=an_inputs())
    assert verdict.call().startswith("Recommend")


def test_a_replan_records_what_it_proposed():
    verdict = assess(laps_done=5, laps_total=20, fuel_l=20.0,
                     planned_fuel_per_lap=3.4, observed_fuel_per_lap_l=3.4,
                     lap_time_ms=94_000, planned_lap_time_ms=94_000,
                     current_stops=0, inputs=an_inputs())
    payload = verdict.as_plan()
    assert payload["verdict"] == URGENT
    assert payload["reason"]
    assert payload["confidence"] == "high"


# ------------------------------------------------- shift beep from the game

def test_the_beep_ignores_the_games_shift_light(qt_app, store):  # noqa: F811
    """**Changed 21 Aug 2026 at the driver's instruction.**

    GT7 sends each car's own shift-light rpm and the beep used to follow it.
    It is one number for the whole gearbox and it is the game's opinion about
    where to shift, not a measurement of where this car stops pulling - and at
    the wheel it was indistinguishable from a measured threshold.

    The thresholds now come off the fitted setup sheet, which is where they
    belong: a shift point is a property of the gearbox, so change a ratio and
    it moves. A car whose sheet carries none does not beep.
    """
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen
    from .test_controller import raw

    controller = PitCrewController(store, EventScreen(), PracticeScreen())
    try:
        controller.bridge.on_packet(raw(speed_ms=50.0, rpm_alert_min=7600))
        # The game named a threshold. Nothing took it.
        assert controller.bridge.shift_beep.per_gear == {}
        assert controller.bridge.shift_beep.threshold_for(3) is None
    finally:
        controller.shutdown()


def test_the_issued_table_is_what_the_beep_uses(qt_app, store):  # noqa: F811
    """And it arrives before the car has turned a wheel, because the table is
    issued ahead of the session while the packet car id is not known yet."""
    from pitcrew.controller import PitCrewController
    from pitcrew.engineer.shift_points import ShiftPoints
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen

    controller = PitCrewController(store, EventScreen(), PracticeScreen())
    try:
        controller.bridge.set_issued_shift_points(ShiftPoints(
            car_name="A", circuit_key="monza",
            performance={1: 8200.0, 2: 8150.0}, fuel_saving={2: 7400.0}))
        assert controller.bridge.shift_beep.threshold_for(1) == 8200.0
        assert controller.bridge.shift_beep.threshold_for(2) == 8150.0
        # A gear the table does not name stays silent.
        assert controller.bridge.shift_beep.threshold_for(6) is None

        # Short-shifting uses the fuel-saving point where one was issued, and
        # the scalar drop where one was not.
        controller.bridge.shift_beep.short_shifting = True
        assert controller.bridge.shift_beep.threshold_for(2) == 7400.0
        assert controller.bridge.shift_beep.threshold_for(1) < 8200.0

        # **Clearing is a real instruction.** A car whose table has not been
        # issued must not keep beeping the last one's.
        controller.bridge.set_issued_shift_points(None)
        assert controller.bridge.shift_beep.threshold_for(1) is None
    finally:
        controller.shutdown()


# ----------------------------------------------------------------- outcome

def a_race_lap(lap_num: int, **overrides):
    from pitcrew.analysis.session import LapInput
    fields = dict(lap_num=lap_num, lap_time_ms=94_000, fuel_start=90.0,
                  fuel_end=86.6)
    fields.update(overrides)
    return LapInput(**fields)


def test_the_outcome_states_what_happened():
    from pitcrew.race.outcome import race_outcome
    laps = [a_race_lap(n) for n in range(1, 21)]
    laps[10] = a_race_lap(11, is_pit_lap=True)
    text = race_outcome(laps, planned_stops=1, final_position=2,
                        binding_constraint="fuel")
    assert "20 laps run" in text
    assert "lap 11" in text
    assert "P2" in text
    assert "fuel-limited" in text


def test_a_plan_that_was_not_followed_is_said():
    from pitcrew.race.outcome import race_outcome
    laps = [a_race_lap(n) for n in range(1, 21)]
    text = race_outcome(laps, planned_stops=1)
    assert "no stops" in text.lower()
    assert "plan called for 1 stop" in text


def test_declined_calls_appear_in_the_outcome():
    from pitcrew.race.outcome import race_outcome
    text = race_outcome([a_race_lap(1)], declined_calls=2)
    assert "2 calls offered and not taken" in text


def test_no_race_gives_no_outcome():
    from pitcrew.race.outcome import race_outcome
    assert race_outcome([]) == ""


def test_the_outcome_states_fuel_left_but_not_tyre_margin():
    """Tyre margin is the driver's judgement; inventing it would fabricate the
    very thing the tune builder is trying to learn."""
    from pitcrew.race.outcome import fuel_left_note
    laps = [a_race_lap(n, fuel_start=90.0 - n * 3.4,
                       fuel_end=86.6 - n * 3.4) for n in range(1, 6)]
    note = fuel_left_note(laps)
    assert "litres" in note
    assert "tyre" not in note.lower()


def test_a_two_stop_run_to_the_plan_is_not_reported_as_a_deviation():
    """`Plan.as_export` carries only the FIRST pit lap, so the comparison had
    [11, 22] against [11] and called a correctly executed plan a deviation.
    An incomplete plan cannot assert one."""
    from pitcrew.race.outcome import race_outcome
    laps = [a_race_lap(n) for n in range(1, 31)]
    laps[10] = a_race_lap(11, is_pit_lap=True)
    laps[21] = a_race_lap(22, is_pit_lap=True)
    text = race_outcome(laps, planned_stops=2, planned_pit_laps=[11])
    assert "against a planned" not in text


def test_a_real_deviation_is_still_said():
    from pitcrew.race.outcome import race_outcome
    laps = [a_race_lap(n) for n in range(1, 31)]
    laps[12] = a_race_lap(13, is_pit_lap=True)
    laps[23] = a_race_lap(24, is_pit_lap=True)
    text = race_outcome(laps, planned_stops=2, planned_pit_laps=[11, 22])
    assert "against a planned lap 11, lap 22" in text


# ------------------------------------------- the two intents that were missing

def test_how_are_my_tyres_answers_the_tyres_and_not_the_compound():
    """**It used to answer the wrong question confidently.** "How are my
    tyres" is the question this whole app exists for, and there was no intent
    for it - it matched BOX_WHAT and came back with the compound planned for
    the stop, which is a different question with a different answer."""
    from pitcrew.engineer.intents import TYRES
    reply = answer(TYRES, {"wearWorst": 0.36, "wearCorner": "rl",
                           "lapsToStop": 4})
    assert reply.answered
    assert "RL 36 percent" in reply.text
    assert "4 laps to the stop" in reply.text


def test_with_no_gauge_it_says_so_rather_than_modelling_one():
    """CLAUDE.md §3.3: there is no tyre wear channel. A number invented in
    reply to a direct question is the worst kind there is - he asked precisely
    because he wanted to know."""
    from pitcrew.engineer.intents import TYRES
    reply = answer(TYRES, {})
    assert not reply.answered
    assert "read it to me" in reply.text
    assert not any(ch.isdigit() for ch in reply.text)


def test_pace_inside_the_noise_is_not_reported_as_a_finding():
    """His lap-to-lap spread puts the detection floor above the whole
    degradation band. A pace figure that has not cleared it is not a finding
    and must not be spoken like one."""
    from pitcrew.engineer.intents import PACE
    reply = answer(PACE, {"paceVsPlanMs": 400, "paceIsReal": False})
    assert "inside the noise" in reply.text
    assert "0.4" not in reply.text


def test_a_real_pace_delta_is_given_with_its_direction():
    from pitcrew.engineer.intents import PACE
    up = answer(PACE, {"paceVsPlanMs": -1200, "paceIsReal": True})
    down = answer(PACE, {"paceVsPlanMs": 900, "paceIsReal": True})
    # Row 1.10: `_on_plan` renders the same figure as "Pace 1.2 a lap up."
    # and this said "1.2 up on the plan", which does not say per-lap at all.
    assert up.text == "1.2 seconds a lap up on the plan."
    assert down.text == "0.9 seconds a lap down on the plan."


def test_the_vocabulary_is_written_the_way_he_talks():
    """**The measurement that prompted the rewrite.** The phrase list was
    SAPI's closed grammar - "fuel", "keep", "again" - and doubled as the
    reference points a semantic matcher measures natural speech against. Six
    of twenty real questions landed outside the act band because nothing in
    the list was near how he says things."""
    from pitcrew.engineer.intents import PHRASES
    natural = [p for phrases in PHRASES.values() for p in phrases
               if " " in p and len(p.split()) >= 4]
    assert len(natural) >= 50, (
        "the vocabulary is still telegraphic - a nearest-neighbour matcher is "
        "only as good as what it is near")


def test_no_phrase_is_a_word_that_appears_inside_a_sentence_about_the_car():
    """**The bug the rewrite introduced and this caught.** A bare "no" added
    to KEEP matched "I have no grip at the rear" - the literal matcher works on
    whole words, so a one-word phrase in common speech swallows real sentences.
    Yes and no are resolved by the confirmation path and were never needed.

    What is asserted is that none of these reaches an ANSWER-shaped intent -
    an acceptance, a refusal, a position. "I have no grip at the rear" is a
    report now and reaching `report-oversteer` is correct; reaching `keep`
    never was, and that is what this holds."""
    for heard in ("i have no grip at the rear", "yes but the rears are gone",
                  "no grip on entry"):
        assert match_intent(heard) not in (KEEP, ACCEPT, POSITION), heard
