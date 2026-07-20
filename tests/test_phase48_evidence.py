"""Phase 48 section 8 — cumulative Practice evidence: accumulation, context safety, session purpose.

Covers task test items: Practice-session accumulation (15), cumulative setup evidence (17),
driver-development accumulation (18), tyre-model (19), fuel-model (20), and the metamorphic invariants
(adding a valid session cannot reduce evidence; invalid cannot raise confidence; coaching-only cannot
alter setup; qualifying evidence cannot become race evidence).
"""
from __future__ import annotations

from strategy.event_preparation_cycle import PreparationActivityType as T
from strategy.preparation_evidence import (
    PracticeEvidenceSample, EvidenceCompatibility as C, EvidenceDomain as Dom, ConfidenceLevel,
    build_cumulative_evidence, to_readiness, to_progress, to_objective, _CONFIDENCE_ORDER,
)


def _s(sid, atype, **kw):
    return PracticeEvidenceSample(session_id=sid, activity_id="act-" + sid, activity_type=atype, **kw)


def _conf_rank(level):
    return _CONFIDENCE_ORDER.index(level)


# --- accumulation ----------------------------------------------------------

def test_setup_confidence_matures_across_valid_sessions():
    e1 = build_cumulative_evidence([_s("s1", T.SETUP_EXPERIMENT, valid_laps=8)])
    e2 = build_cumulative_evidence([_s("s1", T.SETUP_EXPERIMENT), _s("s2", T.SETUP_EXPERIMENT)])
    e3 = build_cumulative_evidence([_s("s1", T.SETUP_EXPERIMENT), _s("s2", T.SETUP_EXPERIMENT),
                                    _s("s3", T.SETUP_EXPERIMENT)])
    assert e1.confidence(Dom.SETUP_BASE) == ConfidenceLevel.EMERGING
    assert e2.confidence(Dom.SETUP_BASE) == ConfidenceLevel.DEVELOPING
    assert e3.confidence(Dom.SETUP_BASE) == ConfidenceLevel.MODERATE


def test_single_quick_session_never_yields_strong():
    e = build_cumulative_evidence([_s("s1", T.SETUP_EXPERIMENT, valid_laps=1)])
    assert e.confidence(Dom.SETUP_BASE) != ConfidenceLevel.STRONG


def test_adding_a_valid_session_never_reduces_evidence_membership():
    base = [_s("s1", T.LONG_RACE_RUN), _s("s2", T.TYRE_TEST)]
    e_before = build_cumulative_evidence(base)
    e_after = build_cumulative_evidence(base + [_s("s3", T.LONG_RACE_RUN)])
    assert set(e_before.evidence_membership) <= set(e_after.evidence_membership)
    assert len(e_after.evidence_membership) >= len(e_before.evidence_membership)


def test_new_session_does_not_reset_prior_evidence():
    prior = build_cumulative_evidence([_s("s1", T.SETUP_EXPERIMENT), _s("s2", T.SETUP_EXPERIMENT)])
    with_new = build_cumulative_evidence([_s("s1", T.SETUP_EXPERIMENT), _s("s2", T.SETUP_EXPERIMENT),
                                          _s("s3", T.COACHING_RUN)])
    # prior setup sessions still in membership; setup confidence not reset
    assert {"s1", "s2"} <= set(with_new.domain(Dom.SETUP_BASE).session_ids)
    assert _conf_rank(with_new.confidence(Dom.SETUP_BASE)) >= _conf_rank(prior.confidence(Dom.SETUP_BASE))


# --- invalid session -------------------------------------------------------

def test_invalid_session_cannot_increase_confidence():
    valid_only = build_cumulative_evidence([_s("s1", T.SETUP_EXPERIMENT)])
    with_invalid = build_cumulative_evidence([_s("s1", T.SETUP_EXPERIMENT),
                                              _s("bad", T.SETUP_EXPERIMENT, is_valid=False)])
    assert with_invalid.confidence(Dom.SETUP_BASE) == valid_only.confidence(Dom.SETUP_BASE)
    assert "bad" not in with_invalid.evidence_membership


# --- session purpose separation --------------------------------------------

def test_coaching_only_run_does_not_touch_setup_or_working_window():
    e = build_cumulative_evidence([_s("c1", T.COACHING_RUN), _s("c2", T.COACHING_RUN)])
    assert e.domain(Dom.SETUP_BASE) is None
    assert e.domain(Dom.WORKING_WINDOW) is None
    assert e.confidence(Dom.DRIVER_COACHING) == ConfidenceLevel.DEVELOPING


def test_fuel_test_does_not_promote_a_setup():
    e = build_cumulative_evidence([_s("f1", T.FUEL_TEST), _s("f2", T.FUEL_TEST), _s("f3", T.FUEL_TEST)])
    assert e.domain(Dom.SETUP_BASE) is None
    assert e.domain(Dom.SETUP_RACE) is None
    assert e.confidence(Dom.FUEL_MODEL) == ConfidenceLevel.MODERATE


def test_qualifying_simulation_never_becomes_race_setup_evidence():
    e = build_cumulative_evidence([_s("q1", T.QUALIFYING_SIMULATION),
                                   _s("q2", T.QUALIFYING_SIMULATION)])
    assert e.confidence(Dom.SETUP_QUALIFYING) == ConfidenceLevel.DEVELOPING
    assert e.domain(Dom.SETUP_RACE) is None  # quali evidence does not silently become race evidence


def test_base_qualifying_race_setups_stay_separate():
    e = build_cumulative_evidence([
        _s("b", T.BASELINE_PRACTICE), _s("q", T.QUALIFYING_SIMULATION), _s("r", T.LONG_RACE_RUN)])
    assert e.domain(Dom.SETUP_BASE) is not None
    assert e.domain(Dom.SETUP_QUALIFYING) is not None
    assert e.domain(Dom.SETUP_RACE) is not None
    # membership per discipline is distinct
    assert e.domain(Dom.SETUP_QUALIFYING).session_ids == ("q",)
    assert e.domain(Dom.SETUP_RACE).session_ids == ("r",)


# --- context safety --------------------------------------------------------

def test_incompatible_context_does_not_strengthen_exact_confidence():
    exact = build_cumulative_evidence([_s("s1", T.SETUP_EXPERIMENT), _s("s2", T.SETUP_EXPERIMENT)])
    plus_incompat = build_cumulative_evidence([
        _s("s1", T.SETUP_EXPERIMENT), _s("s2", T.SETUP_EXPERIMENT),
        _s("other", T.SETUP_EXPERIMENT, compatibility=C.INCOMPATIBLE)])
    assert plus_incompat.confidence(Dom.SETUP_BASE) == exact.confidence(Dom.SETUP_BASE)
    assert "other" not in plus_incompat.domain(Dom.SETUP_BASE).session_ids


def test_partial_context_is_labelled_and_capped():
    e = build_cumulative_evidence([
        _s("p1", T.SETUP_EXPERIMENT, compatibility=C.PARTIAL),
        _s("p2", T.SETUP_EXPERIMENT, compatibility=C.PARTIAL),
        _s("p3", T.SETUP_EXPERIMENT, compatibility=C.PARTIAL),
        _s("p4", T.SETUP_EXPERIMENT, compatibility=C.PARTIAL)])
    de = e.domain(Dom.SETUP_BASE)
    assert de.labelled_transferred is True and de.capped is True
    # partial-only evidence never exceeds EMERGING
    assert de.confidence == ConfidenceLevel.EMERGING


def test_unknown_fuel_multiplier_caps_fuel_confidence():
    # long runs are exact for pace/tyre but fuel multiplier unknown -> fuel domain capped
    samples = [_s(f"r{i}", T.LONG_RACE_RUN, valid_laps=12,
                  domain_overrides={Dom.FUEL_MODEL: C.UNKNOWN}) for i in range(4)]
    e = build_cumulative_evidence(samples)
    # race pace matures with 4 exact samples...
    assert e.confidence(Dom.RACE_PACE) == ConfidenceLevel.STRONG
    # ...but fuel is capped despite 4 samples (unknown multiplier -> partial-only, capped low)
    assert e.domain(Dom.FUEL_MODEL).capped is True
    assert _conf_rank(e.confidence(Dom.FUEL_MODEL)) < _conf_rank(e.confidence(Dom.RACE_PACE))
    assert _conf_rank(e.confidence(Dom.FUEL_MODEL)) <= _conf_rank(ConfidenceLevel.DEVELOPING)


def test_compatible_long_runs_mature_tyre_model():
    samples = [_s(f"r{i}", T.LONG_RACE_RUN, valid_laps=14) for i in range(4)]
    e = build_cumulative_evidence(samples)
    assert e.confidence(Dom.TYRE_MODEL) == ConfidenceLevel.STRONG


def test_incompatible_compound_does_not_strengthen_tyre_model():
    good = [_s(f"r{i}", T.LONG_RACE_RUN) for i in range(2)]
    e_good = build_cumulative_evidence(good)
    e_plus = build_cumulative_evidence(good + [
        _s("wrong", T.LONG_RACE_RUN, domain_overrides={Dom.TYRE_MODEL: C.INCOMPATIBLE})])
    assert e_plus.confidence(Dom.TYRE_MODEL) == e_good.confidence(Dom.TYRE_MODEL)


# --- determinism & projections ---------------------------------------------

def test_aggregation_is_order_independent():
    samples = [_s("a", T.SETUP_EXPERIMENT), _s("b", T.TYRE_TEST), _s("c", T.LONG_RACE_RUN)]
    e1 = build_cumulative_evidence(samples)
    e2 = build_cumulative_evidence(list(reversed(samples)))
    assert e1.fingerprint == e2.fingerprint


def test_progress_only_counts_valid_and_is_monotonic():
    base = [_s("s1", T.SETUP_EXPERIMENT, valid_laps=5), _s("s2", T.COACHING_RUN, valid_laps=3)]
    p_before = to_progress(build_cumulative_evidence(base), base)
    plus = base + [_s("s3", T.LONG_RACE_RUN, valid_laps=12),
                   _s("bad", T.SETUP_EXPERIMENT, valid_laps=99, is_valid=False)]
    p_after = to_progress(build_cumulative_evidence(plus), plus)
    assert p_after.valid_laps == p_before.valid_laps + 12  # invalid 99 laps not counted
    assert p_after.practice_sessions >= p_before.practice_sessions
    assert p_before.setup_experiments_completed == 1 and p_before.coaching_runs_completed == 1


def test_objective_targets_weakest_required_domain():
    # only coaching evidence -> weakest required domains (setup) drive the objective
    e = build_cumulative_evidence([_s("c1", T.COACHING_RUN)])
    obj = to_objective(e)
    assert "setup_base" in obj.headline


def test_readiness_reflects_missing_and_capped_evidence():
    e = build_cumulative_evidence([_s("f1", T.FUEL_TEST, domain_overrides={Dom.FUEL_MODEL: C.UNKNOWN})])
    rdy = to_readiness(e)
    # base setup has no evidence -> MISSING
    from strategy.event_preparation_cycle import ReadinessLevel
    assert rdy.level("base_setup") == ReadinessLevel.MISSING
