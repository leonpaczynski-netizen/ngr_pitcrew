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
            "nextCompound": "RS", "stopFuelL": 37.0, "inPit": False}
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
    reply = answer(BOX_WHEN, a_snapshot(lapsToStop=None))
    assert "flag" in reply.text
    assert reply.answered is True


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
    beeper = ShiftBeep(rpm=7000, tone=lambda: tones.append(1))
    beeper.update(make_packet(gear_raw=0x13, engine_rpm=6000.0), now=1.0)
    beeper.update(make_packet(gear_raw=0x13, engine_rpm=7200.0), now=1.1)
    assert tones == [1]


def test_the_wrapper_stays_silent_off_track():
    tones = []
    beeper = ShiftBeep(rpm=7000, tone=lambda: tones.append(1))
    beeper.update(make_packet(gear_raw=0x13, engine_rpm=9000.0,
                              on_track=False), now=1.0)
    assert tones == []


def test_a_failing_tone_does_not_stop_the_telemetry_thread():
    def explode():
        raise RuntimeError("no audio device")

    beeper = ShiftBeep(rpm=7000, tone=explode)
    beeper.update(make_packet(gear_raw=0x13, engine_rpm=6000.0), now=1.0)
    assert beeper.update(make_packet(gear_raw=0x13, engine_rpm=7200.0),
                         now=1.1) is True


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
    verdict = assess(laps_done=5, laps_total=20, fuel_l=50.0,
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


def test_a_small_drift_is_not_worth_saying():
    verdict = assess(laps_done=8, laps_total=20, fuel_l=60.0,
                     planned_fuel_per_lap=3.4, observed_fuel_per_lap_l=3.45,
                     lap_time_ms=94_200, planned_lap_time_ms=94_000,
                     current_stops=1, inputs=an_inputs())
    assert verdict.verdict == NONE


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

def test_the_beep_threshold_comes_from_the_car_not_a_config(qt_app, store):  # noqa: F811
    """GT7 sends each car's own shift-light rpm; a configured value per car
    would be a second source of truth that drifts."""
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen
    from .test_controller import raw

    controller = PitCrewController(store, EventScreen(), PracticeScreen())
    assert controller.bridge.shift_beep.enabled is False

    controller.bridge.on_packet(raw(speed_ms=50.0, rpm_alert_min=7600))
    assert controller.bridge.shift_beep.enabled is True
    assert controller.bridge.shift_beep.rpm == 7600.0
    controller.shutdown()


def test_a_nonsense_shift_threshold_leaves_the_beep_off(qt_app, store):  # noqa: F811
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen
    from .test_controller import raw

    controller = PitCrewController(store, EventScreen(), PracticeScreen())
    controller.bridge.on_packet(raw(speed_ms=50.0, rpm_alert_min=0))
    assert controller.bridge.shift_beep.enabled is False
    controller.shutdown()
