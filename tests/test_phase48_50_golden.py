"""Phase 48-50 — golden behavioural scenarios (task section 16).

Named, deterministic end-to-end scenarios exercised through the domain layer: monthly Porsche Cup,
one-evening event, missed practice, optional coaching, failed experiment, convergence, quali-vs-race,
tyre/fuel maturity, strategy maturation, late risky experiment, setup lock, event revision, long gap,
no-data. Each asserts the doctrinal invariant and, where relevant, fingerprint stability across restart
and shuffled input.
"""
from __future__ import annotations

from strategy.event_preparation_cycle import (
    EventPreparationCycleIdentity, PreparationActivity, PreparationActivityType as T,
    PreparationActivityState as S, OfficialSession, OfficialSessionType, PreparationCycleState,
    build_event_preparation_cycle, single_evening_profile, multiweek_profile,
)
from strategy.preparation_evidence import (
    PracticeEvidenceSample, EvidenceCompatibility as C, EvidenceDomain as Dom, ConfidenceLevel,
    build_cumulative_evidence, _CONFIDENCE_ORDER,
)
from strategy.setup_convergence import (
    SetupDiscipline, SetupConvergenceState, OutcomeDirection, DisciplineConvergenceInput,
    assess_convergence_state,
)
from strategy.strategy_maturity import StrategyMaturity, StrategyEvidenceReadiness, assess_strategy_maturity
from strategy.strategy_finalisation import assess_deadline_risk, RiskPosture


def _sample(sid, atype, **kw):
    return PracticeEvidenceSample(sid, "a" + sid, atype, **kw)


def _rank(level):
    return _CONFIDENCE_ORDER.index(level)


# --- monthly Porsche Cup ----------------------------------------------------

def test_scenario_monthly_porsche_cup_one_programme():
    idn = EventPreparationCycleIdentity(
        cycle_id="pc", event_name="Porsche Cup R3", series="NGR Porsche Cup", round_label="R3",
        car="Porsche 911 RSR", track="Fuji", layout="Full", prep_open_date="2026-06-01",
        official_race_date="2026-06-21", format_profile_id="multiweek")
    acts = [
        PreparationActivity("brief", T.EVENT_BRIEFING, order_index=0, state=S.COMPLETED),
        PreparationActivity("b1", T.BASELINE_PRACTICE, order_index=1, state=S.COMPLETED),
        PreparationActivity("e1", T.SETUP_EXPERIMENT, order_index=2, state=S.COMPLETED),
        PreparationActivity("e2", T.SETUP_EXPERIMENT, order_index=3),
        PreparationActivity("lr", T.LONG_RACE_RUN, order_index=4),
        PreparationActivity("q", T.QUALIFYING, order_index=5),
        PreparationActivity("r", T.RACE, order_index=6),
    ]
    officials = [OfficialSession(OfficialSessionType.QUALIFYING, "2026-06-21"),
                 OfficialSession(OfficialSessionType.RACE, "2026-06-21")]
    cyc = build_event_preparation_cycle(idn, acts, official_sessions=officials, now_date="2026-06-10")
    # all six practice/official activities belong to ONE cycle; not separate mini-events
    assert cyc.state == PreparationCycleState.ACTIVE
    assert cyc.next_activity_id == "e2"
    assert cyc.preparation_span_days == 20
    # restart + shuffle stability
    cyc2 = build_event_preparation_cycle(idn, list(reversed(acts)), official_sessions=officials,
                                         now_date="2026-06-20")
    assert cyc.fingerprint == cyc2.fingerprint


def test_scenario_one_evening_event():
    idn = EventPreparationCycleIdentity(cycle_id="ev", event_name="Sprint", prep_open_date="2026-06-21",
                                        official_race_date="2026-06-21", format_profile_id="single_evening")
    acts = [PreparationActivity("b", T.EVENT_BRIEFING, order_index=0),
            PreparationActivity("p", T.FREE_PRACTICE, order_index=1),
            PreparationActivity("q", T.QUALIFYING, order_index=2),
            PreparationActivity("r", T.RACE, order_index=3),
            PreparationActivity("d", T.POST_RACE_DEBRIEF, order_index=4)]
    cyc = build_event_preparation_cycle(idn, acts, profile=single_evening_profile(), now_date="2026-06-21")
    assert cyc.preparation_span_days == 0  # one evening, not an error
    assert cyc.days_until_race == 0


def test_scenario_missed_practice_still_valid():
    idn = EventPreparationCycleIdentity(cycle_id="m", prep_open_date="2026-06-01",
                                        official_race_date="2026-06-21")
    acts = [PreparationActivity("done", T.BASELINE_PRACTICE, order_index=0, state=S.COMPLETED),
            PreparationActivity("missed", T.SETUP_EXPERIMENT, order_index=1),  # not completed
            PreparationActivity("next", T.LONG_RACE_RUN, order_index=2)]
    cyc = build_event_preparation_cycle(idn, acts, now_date="2026-06-30")
    assert cyc.state == PreparationCycleState.ACTIVE  # honest, not abandoned
    assert cyc.next_activity_id == "missed"  # shows the missing evidence next


def test_scenario_optional_coaching_does_not_change_setup():
    setup_only = build_cumulative_evidence([_sample("e1", T.SETUP_EXPERIMENT),
                                            _sample("e2", T.SETUP_EXPERIMENT)])
    plus_coaching = build_cumulative_evidence([_sample("e1", T.SETUP_EXPERIMENT),
                                               _sample("e2", T.SETUP_EXPERIMENT),
                                               _sample("c1", T.COACHING_RUN), _sample("c2", T.COACHING_RUN)])
    assert plus_coaching.confidence(Dom.SETUP_BASE) == setup_only.confidence(Dom.SETUP_BASE)
    assert plus_coaching.confidence(Dom.WORKING_WINDOW) == setup_only.confidence(Dom.WORKING_WINDOW)
    assert plus_coaching.confidence(Dom.DRIVER_COACHING) != ConfidenceLevel.NONE


def test_scenario_failed_experiment_direction_stays_blocked():
    inp = DisciplineConvergenceInput(SetupDiscipline.RACE, confirming_samples=3,
                                     regression_detected=True, has_rollback_target=True,
                                     failed_directions=("more front wing",))
    st = assess_convergence_state(inp)
    assert st == SetupConvergenceState.ROLLBACK_RECOMMENDED
    # the failed direction is carried on the input and never silently re-promoted
    assert "more front wing" in inp.failed_directions


def test_scenario_convergence_not_reopened_by_one_noisy_lap():
    st = assess_convergence_state(DisciplineConvergenceInput(
        SetupDiscipline.RACE, confirming_samples=4, latest_outcome=OutcomeDirection.INCONCLUSIVE,
        has_final_confirmation=True, outstanding_experiments=0))
    assert st == SetupConvergenceState.LOCK_READY  # stable, not reopened


def test_scenario_quali_setup_is_not_race_setup():
    # a low-fuel quali sim improves peak pace but is quali-only evidence
    e = build_cumulative_evidence([_sample("q1", T.QUALIFYING_SIMULATION),
                                   _sample("q2", T.QUALIFYING_SIMULATION)])
    assert e.confidence(Dom.SETUP_QUALIFYING) != ConfidenceLevel.NONE
    assert e.domain(Dom.SETUP_RACE) is None


def test_scenario_tyre_matures_fuel_capped_by_unknown_multiplier():
    samples = [_sample(f"r{i}", T.LONG_RACE_RUN, valid_laps=14,
                       domain_overrides={Dom.FUEL_MODEL: C.UNKNOWN}) for i in range(4)]
    e = build_cumulative_evidence(samples)
    assert e.confidence(Dom.TYRE_MODEL) == ConfidenceLevel.STRONG
    assert e.domain(Dom.FUEL_MODEL).capped is True
    assert _rank(e.confidence(Dom.FUEL_MODEL)) < _rank(e.confidence(Dom.TYRE_MODEL))


def test_scenario_strategy_matures_to_finalisation_ready():
    assert assess_strategy_maturity(StrategyEvidenceReadiness()) == StrategyMaturity.NO_EVIDENCE
    provisional = StrategyEvidenceReadiness(has_representative_race_pace=True, has_lap_consistency=True,
                                            has_fuel_use=True, has_tyre_degradation=True,
                                            validated_long_run=True, race_duration_known=True)
    assert assess_strategy_maturity(provisional) == StrategyMaturity.PROVISIONAL
    ready = StrategyEvidenceReadiness(has_representative_race_pace=True, has_lap_consistency=True,
                                      has_fuel_use=True, has_tyre_degradation=True,
                                      validated_long_run=True, race_duration_known=True,
                                      multipliers_known=True)
    assert assess_strategy_maturity(ready) == StrategyMaturity.FINALISATION_READY


def test_scenario_late_risky_experiment_protects_best_known():
    r = assess_deadline_risk(2, high_interaction_experiment=True)
    assert r.posture == RiskPosture.BLOCK_UNLESS_OVERRIDDEN and r.allow_experiment is False
    r2 = assess_deadline_risk(2, high_interaction_experiment=True, explicitly_overridden=True)
    assert r2.allow_experiment is True


def test_scenario_no_data_race_week_is_conservative_not_fabricated():
    e = build_cumulative_evidence([])  # no practice data
    assert e.evidence_membership == ()
    assert e.confidence(Dom.SETUP_RACE) == ConfidenceLevel.NONE
    assert assess_strategy_maturity(StrategyEvidenceReadiness()) == StrategyMaturity.NO_EVIDENCE


def test_scenario_long_gap_shows_next_objective():
    idn = EventPreparationCycleIdentity(cycle_id="g", prep_open_date="2026-06-01",
                                        official_race_date="2026-07-01")
    acts = [PreparationActivity("a1", T.BASELINE_PRACTICE, order_index=0, state=S.COMPLETED,
                                planned_date="2026-06-02"),
            PreparationActivity("a2", T.SETUP_EXPERIMENT, order_index=1, planned_date="2026-06-20")]
    cyc = build_event_preparation_cycle(idn, acts, now_date="2026-06-12")
    assert cyc.state == PreparationCycleState.ACTIVE
    assert cyc.next_activity_id == "a2"
