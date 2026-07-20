"""Phase 65 — adaptive live strategy: objectives, divergence, projections, candidates, decision, message."""
from __future__ import annotations

from strategy.adaptive_live_strategy import (
    StrategyObjective, LiveStrategyState, LiveStrategyTrigger, detect_divergence_triggers,
    project_lap_count, project_time_certain, generate_replan_candidates, rank_candidates,
    StrategyRecommendation, StrategyConfidence, decide_replan, build_strategy_driver_message,
    acknowledge_strategy, StrategyMonitor,
)


def _tc_state(**kw):
    base = dict(objective=StrategyObjective.TIME_CERTAIN, time_remaining_s=1800.0,
                lap_time_actual_s=90.0, lap_time_plan_s=90.0, pit_loss_s=25.0, pit_loss_plan_s=25.0,
                tyre_age_laps=10, telemetry_fresh=True)
    base.update(kw)
    return LiveStrategyState(**base)


def _lap_state(**kw):
    base = dict(objective=StrategyObjective.LAP_COUNT, laps_remaining=20, lap_time_actual_s=90.0,
                lap_time_plan_s=90.0, pit_loss_s=25.0, pit_loss_plan_s=25.0, tyre_age_laps=10,
                fuel_per_lap_plan=3.0, fuel_per_lap_actual=3.0, telemetry_fresh=True)
    base.update(kw)
    return LiveStrategyState(**base)


# --- divergence triggers --- #
def test_fuel_divergence_high_and_low():
    hi = detect_divergence_triggers(_lap_state(fuel_per_lap_actual=3.5, fuel_per_lap_plan=3.0))
    assert any(t.trigger == LiveStrategyTrigger.FUEL_BURN_HIGH.value and t.available for t in hi)
    lo = detect_divergence_triggers(_lap_state(fuel_per_lap_actual=2.6, fuel_per_lap_plan=3.0))
    assert any(t.trigger == LiveStrategyTrigger.FUEL_BURN_LOW.value and t.available for t in lo)


def test_small_fuel_noise_does_not_fire():
    noise = detect_divergence_triggers(_lap_state(fuel_per_lap_actual=3.02, fuel_per_lap_plan=3.0))
    assert not any(t.trigger == LiveStrategyTrigger.FUEL_BURN_HIGH.value and t.available for t in noise)


def test_pace_and_tyre_divergence():
    slow = detect_divergence_triggers(_lap_state(lap_time_actual_s=92.0, lap_time_plan_s=90.0))
    assert any(t.trigger == LiveStrategyTrigger.PACE_SLOWER.value and t.available for t in slow)
    tyre = detect_divergence_triggers(_lap_state(tyre_deg_per_lap_actual_s=0.30,
                                                 tyre_deg_per_lap_plan_s=0.10))
    assert any(t.trigger == LiveStrategyTrigger.TYRE_DEG_EARLY.value and t.available for t in tyre)


def test_unavailable_triggers_are_explicit_not_silent():
    trig = detect_divergence_triggers(_lap_state(fuel_per_lap_actual=None, fuel_per_lap_plan=None))
    assert any(t.trigger == LiveStrategyTrigger.FUEL_BURN_HIGH.value and t.available is False for t in trig)


def test_weather_and_damage_only_when_reported_never_fabricated():
    none = detect_divergence_triggers(_tc_state())
    assert not any(t.trigger == LiveStrategyTrigger.RAIN_BEGINNING.value for t in none)
    rain = detect_divergence_triggers(_tc_state(weather="rain", weather_source="driver_reported"))
    r = [t for t in rain if t.trigger == LiveStrategyTrigger.RAIN_BEGINNING.value][0]
    assert r.available and r.driver_reported is True


# --- projections --- #
def test_time_certain_projection_completed_laps():
    p = project_time_certain(time_remaining_s=1800.0, lap_time_s=90.0)
    assert p.expected_completed_laps == 20  # 1800/90


def test_lap_count_projection_total_time():
    p = project_lap_count(laps_remaining=20, lap_time_s=90.0, extra_stops=1, pit_loss_s=25.0)
    assert p.total_race_time_s == 20 * 90.0 + 25.0


# --- the two headline time-certain decisions --- #
def test_time_certain_extra_stop_that_loses_a_lap_is_rejected():
    # 1800s, 90s laps -> 20 laps no stop. An extra 25s stop with only ~1.5% pace gain:
    # (1800-25)/(90*0.985)=1775/88.65=20.02 -> floor 20; but the generator's fresh-tyre gain is modest,
    # so the extra-stop candidate must NOT rank above 'keep the plan' (equal or fewer completed laps).
    state = _tc_state(time_remaining_s=1800.0, lap_time_actual_s=90.0, pit_loss_s=120.0)
    cands = generate_replan_candidates(state, detect_divergence_triggers(state))
    ranked = rank_candidates(StrategyObjective.TIME_CERTAIN, cands)
    keep = [c for c in ranked if c.stop_count_delta == 0][0]
    extra = [c for c in ranked if c.stop_count_delta == 1][0]
    assert extra.expected_completed_laps <= keep.expected_completed_laps
    # ranked best is never the lap-losing extra stop
    assert ranked[0].expected_completed_laps >= extra.expected_completed_laps
    # with a big pit loss the extra stop strictly loses laps
    assert extra.expected_completed_laps < keep.expected_completed_laps


def test_time_certain_extra_stop_that_gains_a_lap_can_win():
    # small pit loss + big pace gain from fresh tyres: model a large deg so the base pace is already slow
    # and a fresh-tyre stop recovers enough to add a completed lap.
    # base 100s/lap over 1800s -> 18 laps. With pit_loss=10 and fresh tyres 12% quicker (88s):
    # (1800-10)/88 = 20.3 -> 20 laps > 18.
    state = _tc_state(time_remaining_s=1800.0, lap_time_actual_s=100.0, pit_loss_s=10.0)
    # override the modest generator assumption by supplying an explicit faster projection check:
    base = project_time_certain(time_remaining_s=1800.0, lap_time_s=100.0)
    gained = project_time_certain(time_remaining_s=1800.0, lap_time_s=100.0, extra_stops=1,
                                  pit_loss_s=10.0, pace_delta_s=-12.0)
    assert gained.expected_completed_laps > base.expected_completed_laps


def test_time_certain_uses_completed_laps_not_min_stint_time():
    # a strategy with a faster average lap but fewer completed laps must never be preferred.
    fewer_but_faster = project_time_certain(time_remaining_s=600.0, lap_time_s=60.0, extra_stops=1,
                                            pit_loss_s=300.0, pace_delta_s=-10.0)  # 300s lost to pit
    keep = project_time_certain(time_remaining_s=600.0, lap_time_s=60.0)
    assert keep.expected_completed_laps > fewer_but_faster.expected_completed_laps


# --- lap-count optimisation --- #
def test_lap_count_conservation_candidate_on_high_fuel_burn():
    state = _lap_state(fuel_per_lap_actual=3.4, fuel_per_lap_plan=3.0)
    cands = generate_replan_candidates(state, detect_divergence_triggers(state))
    assert any("conservation" in c.label.lower() for c in cands)


def test_illegal_candidates_are_filtered_in_ranking():
    from strategy.adaptive_live_strategy import StrategyReplanCandidate
    legal = StrategyReplanCandidate("legal", 0, 100.0, None, "", "", (), "", legal=True)
    illegal = StrategyReplanCandidate("illegal", 0, 1.0, None, "", "", (), "", legal=False)
    ranked = rank_candidates(StrategyObjective.LAP_COUNT, [legal, illegal])
    assert all(c.legal for c in ranked) and illegal not in ranked


# --- decision states --- #
def test_plan_still_optimal_when_no_divergence():
    d = decide_replan(_tc_state())
    assert d.recommendation == StrategyRecommendation.PLAN_STILL_OPTIMAL.value


def test_high_fuel_burn_recommends_conservation():
    d = decide_replan(_lap_state(fuel_per_lap_actual=3.5, fuel_per_lap_plan=3.0))
    assert d.recommendation == StrategyRecommendation.CONSERVATION_REQUIRED.value


def test_telemetry_loss_cannot_produce_high_confidence_replan():
    d = decide_replan(_lap_state(telemetry_fresh=False, fuel_per_lap_actual=3.9, fuel_per_lap_plan=3.0))
    assert d.recommendation == StrategyRecommendation.INSUFFICIENT_EVIDENCE.value
    assert d.confidence == StrategyConfidence.INSUFFICIENT.value


def test_context_mismatch_surfaced():
    d = decide_replan(_tc_state(), context_ok=False)
    assert d.recommendation == StrategyRecommendation.CONTEXT_MISMATCH.value


def test_unverified_rules_hold_a_replan():
    d = decide_replan(_lap_state(lap_time_actual_s=93.0, lap_time_plan_s=90.0), rules_verified=False)
    assert d.recommendation == StrategyRecommendation.RULES_UNVERIFIED.value
    assert d.confidence == StrategyConfidence.LOW.value


def test_driver_reported_only_divergence_is_low_confidence():
    d = decide_replan(_tc_state(weather="rain", weather_source="driver_reported"))
    assert d.recommendation == StrategyRecommendation.REPLAN_URGENT.value
    assert d.confidence == StrategyConfidence.LOW.value


def test_insufficient_when_objective_unknown():
    d = decide_replan(LiveStrategyState(objective=StrategyObjective.UNKNOWN))
    assert d.recommendation == StrategyRecommendation.INSUFFICIENT_EVIDENCE.value


# --- message + acknowledgement --- #
def test_message_is_audio_first_headline_with_deferred_detail():
    d = decide_replan(_lap_state(fuel_per_lap_actual=3.5, fuel_per_lap_plan=3.0))
    m = build_strategy_driver_message(d)
    assert m.headline and "Confidence" in m.detail
    assert m.recommendation == d.recommendation


def test_acknowledge_executes_nothing():
    ack = acknowledge_strategy(record_preference=True)
    assert ack.executes_anything is False


# --- continued monitoring: cooldown + dedup --- #
def test_monitor_suppresses_identical_decision_within_cooldown():
    mon = StrategyMonitor(cooldown_seconds=45.0)
    d = decide_replan(_lap_state(fuel_per_lap_actual=3.5, fuel_per_lap_plan=3.0))
    assert mon.should_announce(d, now=100.0) is True
    assert mon.should_announce(d, now=110.0) is False   # same fp, within cooldown
    assert mon.should_announce(d, now=200.0) is True     # cooldown elapsed


def test_monitor_announces_materially_changed_decision():
    mon = StrategyMonitor(cooldown_seconds=45.0)
    d1 = decide_replan(_lap_state(fuel_per_lap_actual=3.5, fuel_per_lap_plan=3.0))
    d2 = decide_replan(_lap_state(lap_time_actual_s=93.0, lap_time_plan_s=90.0))
    assert mon.should_announce(d1, now=100.0) is True
    assert d1.fingerprint != d2.fingerprint
    assert mon.should_announce(d2, now=105.0) is True   # different decision -> announce despite cooldown


# --- determinism --- #
def test_decision_is_deterministic():
    a = decide_replan(_lap_state(fuel_per_lap_actual=3.5, fuel_per_lap_plan=3.0))
    b = decide_replan(_lap_state(fuel_per_lap_actual=3.5, fuel_per_lap_plan=3.0))
    assert a.fingerprint == b.fingerprint
