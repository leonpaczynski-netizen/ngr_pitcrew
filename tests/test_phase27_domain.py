"""Phase 27 — pure domain unit tests: coverage signals, per-dimension status, blind-spot severity.

Core doctrine: MISSING (untested) is distinct from REGRESSION_ONLY (a negative result); a large
dependent count is never strong coverage; one distinct context is SINGLE_CONTEXT_ONLY; a strong
claim on thin evidence is a material/critical blind spot; an emerging domain gap is informational.
"""
from strategy.coverage_dimension import (
    CoverageDimension, CoverageStatus, BlindSpotSeverity, GAP_STATUSES, DIMENSION_ORDER,
    COVERAGE_STATUS_PRIORITY, BLIND_SPOT_SEVERITY_PRIORITY,
)
from strategy.evidence_coverage import coverage_signals, assess_domain_coverage
from strategy.knowledge_blind_spot import classify_blind_spot


def _rec(track="Fuji", car="GT-R", driver="L", compound="RH", discipline="race",
         gt7_version="1", layout="fc", phase="entry", corner="T1", outcome="confirmed_improvement",
         conf="high"):
    return {"context": {"track": track, "car": car, "driver": driver, "compound": compound,
                        "discipline": discipline, "gt7_version": gt7_version, "layout_id": layout},
            "residual_states": [{"family": "rotation", "phase": phase, "segment_id": corner}],
            "outcome_status": outcome, "confidence_level": conf}


def _conv(**kw):
    base = {"domain": "differential", "convergence_status": "converging",
            "independent_support_count": 1, "dependent_support_count": 0, "regression_count": 0,
            "conflict_count": 0, "confirmed_good": False, "compatible_contexts": 1,
            "current_maturity": "developing", "current_confidence": "medium"}
    base.update(kw)
    return base


def _dim(cov_dict, dim):
    return next(d for d in cov_dict["dimensions"] if d["dimension"] == dim)


# ---- enums / constants ---------------------------------------------------------------------

def test_18_dimensions_and_orders_complete():
    assert len(list(CoverageDimension)) == 18
    for d in CoverageDimension:
        assert d.value in DIMENSION_ORDER
    for s in CoverageStatus:
        assert s.value in COVERAGE_STATUS_PRIORITY
    for s in BlindSpotSeverity:
        assert s.value in BLIND_SPOT_SEVERITY_PRIORITY


def test_missing_and_regression_are_distinct_gap_statuses():
    assert CoverageStatus.MISSING.value in GAP_STATUSES
    assert CoverageStatus.REGRESSION_ONLY.value in GAP_STATUSES
    assert CoverageStatus.MISSING.value != CoverageStatus.REGRESSION_ONLY.value


# ---- coverage_signals ----------------------------------------------------------------------

def test_signals_count_distinct_contexts():
    recs = [_rec(track="Fuji"), _rec(track="Suzuka"), _rec(track="Spa")]
    sig = coverage_signals(recs)
    assert sig["breadth"]["track"] == 3
    assert sig["breadth"]["car"] == 1
    assert sig["record_confirmations"] == 3


def test_signals_empty_safe():
    sig = coverage_signals([])
    assert sig["record_count"] == 0 and sig["breadth"]["track"] == 0


# ---- per-dimension coverage ----------------------------------------------------------------

def test_breadth_three_tracks_well_covered():
    cov = assess_domain_coverage("differential",
                                 [_rec(track=t) for t in ("Fuji", "Suzuka", "Spa")],
                                 _conv(), {}).to_dict()
    assert _dim(cov, "track_variety")["status"] == CoverageStatus.WELL_COVERED.value


def test_breadth_single_track_single_context_only():
    cov = assess_domain_coverage("differential", [_rec(track="Fuji"), _rec(track="Fuji")],
                                 _conv(), {}).to_dict()
    assert _dim(cov, "track_variety")["status"] == CoverageStatus.SINGLE_CONTEXT_ONLY.value


def test_breadth_no_evidence_missing_not_regression():
    cov = assess_domain_coverage("differential", [], _conv(compatible_contexts=0), {}).to_dict()
    assert _dim(cov, "track_variety")["status"] == CoverageStatus.MISSING.value


def test_large_dependent_count_is_not_strong_coverage():
    cov = assess_domain_coverage("differential", [_rec()],
                                 _conv(independent_support_count=1, dependent_support_count=50),
                                 {}).to_dict()
    assert _dim(cov, "independent_replication")["status"] == \
        CoverageStatus.DEPENDENT_EVIDENCE_ONLY.value


def test_two_independent_lines_well_covered():
    cov = assess_domain_coverage("differential", [_rec()],
                                 _conv(independent_support_count=2), {}).to_dict()
    assert _dim(cov, "independent_replication")["status"] == CoverageStatus.WELL_COVERED.value


def test_only_positive_outcomes_regression_check_partial_not_fault():
    cov = assess_domain_coverage("differential", [_rec(outcome="confirmed_improvement")],
                                 _conv(regression_count=0), {}).to_dict()
    rc = _dim(cov, "regression_check")
    assert rc["status"] == CoverageStatus.PARTIALLY_COVERED.value
    assert "untested" in rc["detail"]


def test_regression_observed_regression_check_well_covered():
    cov = assess_domain_coverage("differential", [_rec(outcome="regression")],
                                 _conv(regression_count=1), {}).to_dict()
    assert _dim(cov, "regression_check")["status"] == CoverageStatus.WELL_COVERED.value


def test_confirmed_good_thin_evidence_flagged_single_context():
    cov = assess_domain_coverage("differential", [_rec()],
                                 _conv(confirmed_good=True, independent_support_count=1),
                                 {}).to_dict()
    assert _dim(cov, "confirmed_good_verification")["status"] == \
        CoverageStatus.SINGLE_CONTEXT_ONLY.value


def test_revalidation_currency_reuses_phase26():
    cov = assess_domain_coverage("differential", [_rec()], _conv(),
                                 {"freshness_status": "weakened_by_regression"}).to_dict()
    assert _dim(cov, "revalidation_currency")["status"] == CoverageStatus.REGRESSION_ONLY.value


# ---- blind-spot severity -------------------------------------------------------------------

def test_confirmed_good_mature_thin_is_critical():
    cov = assess_domain_coverage(
        "differential", [_rec()],
        _conv(confirmed_good=True, current_maturity="mature", current_confidence="very_high",
              independent_support_count=1, dependent_support_count=8, compatible_contexts=1),
        {"freshness_status": "current"}).to_dict()
    bs = classify_blind_spot(cov)
    assert bs.severity == BlindSpotSeverity.CRITICAL.value
    assert bs.reliance == "high" and bs.evidence_robustness == "thin"


def test_emerging_domain_gap_is_informational():
    cov = assess_domain_coverage(
        "differential", [_rec()],
        _conv(current_maturity="emerging", current_confidence="low", independent_support_count=1),
        {"freshness_status": "current"}).to_dict()
    bs = classify_blind_spot(cov)
    assert bs.severity == BlindSpotSeverity.INFORMATIONAL.value


def test_unresolved_conflict_relied_upon_is_critical():
    cov = assess_domain_coverage(
        "differential", [_rec()],
        _conv(convergence_status="conflicting", conflict_count=1, current_maturity="established",
              current_confidence="high", independent_support_count=2, compatible_contexts=2),
        {"freshness_status": "weakened_by_conflict"}).to_dict()
    bs = classify_blind_spot(cov)
    assert bs.severity == BlindSpotSeverity.CRITICAL.value


def test_blind_spot_is_never_framed_as_a_fault():
    cov = assess_domain_coverage("differential", [], _conv(), {}).to_dict()
    bs = classify_blind_spot(cov)
    assert "not a fault" in bs.note and "untested" in bs.note
