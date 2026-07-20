"""Phase 66 — canonical live race-state mapping: clock, fuel, pace, tyre, pit, driver reports, cadence."""
from __future__ import annotations

from strategy.canonical_live_race_state import (
    build_canonical_live_race_state, CanonicalLiveRaceState, RaceType, PitPhase,
    LiveRaceStateAvailability, LiveRaceStateConfidence, EvaluationCadence,
    StrategyEvaluationTrigger, LiveStrategyEvaluationContext,
)
from strategy.adaptive_live_strategy import StrategyObjective, decide_replan, StrategyRecommendation, rank_candidates


class _Tracker:
    """Duck-typed stand-in exposing the real RaceStateTracker property surface (Audit A)."""
    def __init__(self, **kw):
        self._d = {
            "race_type": "lap", "laps_recorded": 5, "laps_in_race": 25, "timed_duration_minutes": 0.0,
            "last_fuel": 60.0, "avg_fuel_per_lap": 3.0, "best_lap_ms": 90000, "pit_stops_completed": 0,
            "laps_since_pit": 5, "tyre_age_laps": 5, "in_pit": False, "pit_state_confidence": "high",
            "last_position": 4, "tyre_compound": "RM", "car_name": "Porsche 911 RSR",
            "track": "Fuji", "layout_id": "full_course",
        }
        self._d.update(kw)

    def __getattr__(self, name):
        d = object.__getattribute__(self, "_d")
        if name in d:
            return d[name]
        raise AttributeError(name)


# --- race clock --- #
def test_lap_count_clock():
    s = build_canonical_live_race_state(_Tracker(race_type="lap", laps_recorded=5, laps_in_race=25))
    assert s.clock.race_type == RaceType.LAP
    assert s.clock.laps_remaining == 20
    assert s.to_live_strategy_state().objective == StrategyObjective.LAP_COUNT


def test_time_certain_clock_and_completed_lap_projection():
    s = build_canonical_live_race_state(
        _Tracker(race_type="timed", timed_duration_minutes=30.0, best_lap_ms=90000),
        elapsed_s=600.0, recent_clean_lap_times_s=[90.0, 90.0, 90.0, 90.0])
    assert s.clock.race_type == RaceType.TIMED
    assert s.clock.remaining_s == 1200.0  # 1800 - 600
    # 1200/90 = 13 completed laps
    assert s.clock.expected_completed_laps == 13
    assert s.to_live_strategy_state().objective == StrategyObjective.TIME_CERTAIN


def test_additional_stop_lapcount_effect_flagged():
    s = build_canonical_live_race_state(
        _Tracker(race_type="timed", timed_duration_minutes=30.0),
        elapsed_s=0.0, recent_clean_lap_times_s=[90.0] * 4, pit_loss_s=120.0)
    # with a 120s stop the additional-stop effect on completed laps is computed (True/False, not None)
    assert s.clock.additional_stop_changes_lapcount in (True, False)


# --- fuel model (robust) --- #
def test_fuel_model_robust_to_one_anomalous_lap():
    s = build_canonical_live_race_state(
        _Tracker(), recent_fuel_burn_samples=[3.0, 3.0, 3.0, 9.0])  # one anomalous 9.0
    # robust mean drops the extreme; live burn stays near 3.0, not pulled to ~4.5
    assert s.fuel_per_lap_live is not None and s.fuel_per_lap_live < 3.6


def test_fuel_remaining_measured():
    s = build_canonical_live_race_state(_Tracker(last_fuel=42.0))
    assert s.fuel_remaining_l == 42.0
    fm = s.field_map()["fuel_remaining_l"]
    assert fm.availability == LiveRaceStateAvailability.MEASURED


# --- pace model --- #
def test_pace_uses_clean_lap_median_not_outlier():
    s = build_canonical_live_race_state(
        _Tracker(), recent_clean_lap_times_s=[89.5, 90.0, 90.5, 200.0])  # 200 = traffic/pit outlier
    assert s.lap_time_live_s is not None and s.lap_time_live_s < 100.0


# --- tyre proxy --- #
def test_tyre_degradation_is_labelled_proxy():
    s = build_canonical_live_race_state(
        _Tracker(), recent_clean_lap_times_s=[90.0, 90.3, 90.6, 91.0, 91.5, 92.0])
    assert s.stint.tyre_deg_is_proxy is True
    assert s.stint.tyre_deg_per_lap_s is not None and s.stint.tyre_deg_per_lap_s > 0
    fm = s.field_map()["tyre_deg_per_lap_s"]
    assert fm.confidence == LiveRaceStateConfidence.LOW  # proxy => low confidence


# --- pit state --- #
def test_pit_state_confirmed_when_in_pit():
    s = build_canonical_live_race_state(_Tracker(in_pit=True, pit_stops_completed=1))
    assert s.pit.phase == PitPhase.PIT_CONFIRMED
    assert s.pit.pit_stops_completed == 1


def test_pit_state_uncertain_on_low_confidence():
    s = build_canonical_live_race_state(_Tracker(in_pit=False, pit_state_confidence="low"))
    assert s.pit.phase == PitPhase.UNCERTAIN


# --- driver-reported conditions --- #
def test_driver_reported_rain_never_verified():
    s = build_canonical_live_race_state(_Tracker(), driver_reports={"weather": "rain"})
    assert s.weather == "rain" and s.weather_source == "driver_reported"
    fm = s.field_map()["weather"]
    assert fm.availability == LiveRaceStateAvailability.DRIVER_REPORTED
    # passes into the strategy state labelled driver-reported
    assert s.to_live_strategy_state().weather_source == "driver_reported"


def test_unavailable_weather_is_explicit():
    s = build_canonical_live_race_state(_Tracker())
    assert s.weather is None
    assert s.field_map()["weather"].availability == LiveRaceStateAvailability.UNAVAILABLE


# --- runtime activation: the strategy brain leaves INSUFFICIENT when fed a real valid state --- #
def test_runtime_activation_leaves_insufficient_evidence():
    s = build_canonical_live_race_state(
        _Tracker(race_type="lap", laps_recorded=5, laps_in_race=25),
        fuel_per_lap_plan=3.0, recent_fuel_burn_samples=[3.6, 3.6, 3.6],
        recent_clean_lap_times_s=[90.0, 90.0, 90.0, 90.0], lap_time_plan_s=90.0)
    d = decide_replan(s.to_live_strategy_state())
    # a valid live feed must NOT be INSUFFICIENT_EVIDENCE; high fuel burn -> conservation
    assert d.recommendation != StrategyRecommendation.INSUFFICIENT_EVIDENCE.value


def test_still_insufficient_when_inputs_genuinely_missing():
    s = build_canonical_live_race_state(_Tracker(race_type="unknown", laps_in_race=0, best_lap_ms=0),
                                        recent_clean_lap_times_s=[])
    d = decide_replan(s.to_live_strategy_state())
    assert d.recommendation == StrategyRecommendation.INSUFFICIENT_EVIDENCE.value


# --- evaluation cadence --- #
def test_cadence_triggers_on_lap_and_pit_and_ptt():
    cad = EvaluationCadence()
    s1 = build_canonical_live_race_state(_Tracker(laps_recorded=5, pit_stops_completed=0))
    t1 = cad.triggers(s1, now=10.0)
    assert StrategyEvaluationTrigger.LAP_COMPLETION in t1
    # same lap -> no lap trigger; explicit PTT request still triggers
    t2 = cad.triggers(s1, now=11.0, ptt_request=True)
    assert StrategyEvaluationTrigger.LAP_COMPLETION not in t2
    assert StrategyEvaluationTrigger.EXPLICIT_PTT_REQUEST in t2
    # a confirmed pit stop increment triggers
    s2 = build_canonical_live_race_state(_Tracker(laps_recorded=6, pit_stops_completed=1, in_pit=True))
    t3 = cad.triggers(s2, now=12.0)
    assert StrategyEvaluationTrigger.CONFIRMED_PIT_EVENT in t3


def test_eval_context_key_stable():
    c = LiveStrategyEvaluationContext(cycle_id="c1", activity_id="a1", race_plan_fingerprint="p1")
    assert c.key() == ("c1", "a1", "", "p1", "")


# --- determinism --- #
def test_canonical_state_deterministic_and_excludes_volatile():
    a = build_canonical_live_race_state(_Tracker(), recent_clean_lap_times_s=[90.0, 90.0, 90.0, 90.0])
    b = build_canonical_live_race_state(_Tracker(), recent_clean_lap_times_s=[90.0, 90.0, 90.0, 90.0])
    assert a.fingerprint == b.fingerprint
    # no volatile control field participates in the payload
    assert "throttle" not in a.as_payload() and "speed" not in a.as_payload()


# --- Audit B tie-breaks --- #
def test_equal_lap_candidates_use_meaningful_tiebreak_not_id():
    from strategy.adaptive_live_strategy import StrategyReplanCandidate
    # equal completed laps (20); 'zzz' has the LOWER total time, so it must win despite the later label
    a = StrategyReplanCandidate("zzz-plan", 0, 990.0, 20, "", "", (), "", legal=True)
    b = StrategyReplanCandidate("aaa-plan", 0, 1000.0, 20, "", "", (), "", legal=True)
    ranked = rank_candidates(StrategyObjective.TIME_CERTAIN, [a, b])
    assert ranked[0].label == "zzz-plan"  # 990 < 1000 decides, NOT alphabetical label order


def test_label_is_only_final_tiebreak():
    from strategy.adaptive_live_strategy import StrategyReplanCandidate
    # fully-equal candidates except label -> stable label order
    a = StrategyReplanCandidate("b", 0, 1000.0, 20, "", "", (), "", legal=True)
    b = StrategyReplanCandidate("a", 0, 1000.0, 20, "", "", (), "", legal=True)
    ranked = rank_candidates(StrategyObjective.TIME_CERTAIN, [a, b])
    assert [c.label for c in ranked] == ["a", "b"]
