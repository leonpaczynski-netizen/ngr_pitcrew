"""Live Activation 3 — bounded race PTT answers from the canonical race state (pure)."""
from __future__ import annotations

import types

from strategy.race_ptt_answers import RaceQueryIntent, SUPPORTED_RACE_INTENTS, answer_race_query


def _clock(**over):
    d = dict(race_type=types.SimpleNamespace(value="lap"), current_lap=5, scheduled_laps=20,
             laps_remaining=15, remaining_s=None)
    d.update(over)
    return types.SimpleNamespace(**d)


def _state(**over):
    d = dict(
        telemetry_fresh=True, clock=_clock(),
        stint=types.SimpleNamespace(compound="Racing Medium", stint_age_laps=6),
        pit=types.SimpleNamespace(pit_stops_completed=0),
        fuel_remaining_l=30.0, fuel_per_lap_live=2.0, fuel_per_lap_plan=2.1,
        lap_time_live_s=95.2, lap_time_plan_s=95.0, position=4, required_stops=1,
        best_lap_s=94.8)
    d.update(over)
    return types.SimpleNamespace(**d)


def test_all_intents_supported():
    for i in RaceQueryIntent:
        _txt, supported = answer_race_query(i, _state())
        assert supported


def test_unsupported_intent_is_honest_refusal():
    txt, supported = answer_race_query("what is the meaning of life", _state())
    assert not supported and "only answer" in txt.lower()


def test_fuel_from_state():
    txt, _ = answer_race_query(RaceQueryIntent.FUEL, _state(fuel_remaining_l=27.4))
    assert "27.4" in txt


def test_fuel_unknown_is_honest():
    txt, _ = answer_race_query(RaceQueryIntent.FUEL, _state(fuel_remaining_l=None))
    assert "don't have" in txt.lower()


def test_predicted_finish_fuel_spare():
    # 30 L, 2 L/lap, 15 laps → 30 - 30 = 0 spare
    txt, _ = answer_race_query(RaceQueryIntent.FUEL_PREDICTED, _state())
    assert "spare" in txt.lower()


def test_predicted_finish_fuel_short():
    txt, _ = answer_race_query(RaceQueryIntent.FUEL_PREDICTED,
                               _state(fuel_remaining_l=20.0))  # 20 - 30 = -10
    assert "short" in txt.lower() or "save" in txt.lower()


def test_predicted_fuel_unknown_when_missing_evidence():
    txt, _ = answer_race_query(RaceQueryIntent.FUEL_PREDICTED,
                               _state(fuel_per_lap_live=None, fuel_per_lap_plan=None))
    assert "can't predict" in txt.lower()


def test_laps_remaining():
    txt, _ = answer_race_query(RaceQueryIntent.LAPS_REMAINING, _state())
    assert "15 laps" in txt


def test_time_remaining_timed():
    st = _state(clock=_clock(race_type=types.SimpleNamespace(value="timed"), remaining_s=605))
    txt, _ = answer_race_query(RaceQueryIntent.TIME_REMAINING, st)
    assert "10 min" in txt


def test_position_known_and_unknown():
    assert "P4" in answer_race_query(RaceQueryIntent.POSITION, _state())[0]
    assert "don't have your position" in answer_race_query(
        RaceQueryIntent.POSITION, _state(position=None))[0].lower()


def test_delta_vs_plan():
    txt, _ = answer_race_query(RaceQueryIntent.DELTA, _state(lap_time_live_s=95.5, lap_time_plan_s=95.0))
    assert "down" in txt.lower() and "0.500" in txt


def test_pit_window_required_stops():
    txt, _ = answer_race_query(RaceQueryIntent.PIT_WINDOW, _state(required_stops=2))
    assert "2 more stop" in txt


def test_pit_window_unknown_is_honest():
    txt, _ = answer_race_query(RaceQueryIntent.PIT_WINDOW, _state(required_stops=None))
    assert "don't have" in txt.lower()


def test_tyre_unknown_is_honest():
    st = _state(stint=types.SimpleNamespace(compound=None, stint_age_laps=None))
    txt, _ = answer_race_query(RaceQueryIntent.TYRE, st)
    assert "don't have tyre" in txt.lower()


def test_stale_telemetry_blocks_data_answers():
    txt, _ = answer_race_query(RaceQueryIntent.FUEL, _state(telemetry_fresh=False))
    assert "dropped" in txt.lower()


def test_control_intents_work_when_telemetry_stale():
    # push / save / repeat / mute don't need fresh telemetry
    assert answer_race_query(RaceQueryIntent.PUSH, _state(telemetry_fresh=False))[0]
    assert answer_race_query(RaceQueryIntent.FUEL_SAVE, _state(telemetry_fresh=False))[0]


def test_repeat_returns_last_answer():
    txt, _ = answer_race_query(RaceQueryIntent.REPEAT, _state(), last_answer="Fuel is 20 litres.")
    assert txt == "Fuel is 20 litres."


def test_never_raises_on_none_state():
    txt, supported = answer_race_query(RaceQueryIntent.FUEL, None)
    assert supported and "don't have live race data" in txt.lower()


def test_supported_set_matches_enum():
    assert SUPPORTED_RACE_INTENTS == frozenset(i.value for i in RaceQueryIntent)
