"""Phase 26 — pure domain unit tests: decay signals, reasons, classification, report assembly.

Covers the core doctrine: age alone never decays; version change re-validates only version-sensitive
knowledge; confirmed-good stays protected; retired stays retired; superseded stays inactive; unknown
date/context produces an insufficient status not automatic invalidation; deterministic ordering.
"""
from strategy.knowledge_decay import (
    programme_context_changes, decay_signals, KNOWLEDGE_DECAY_VERSION, MIN_INDEPENDENT_FOR_ROBUST,
)
from strategy.revalidation_reason import (
    RevalidationReason, context_change_reason, reasons_from_signals,
)
from strategy.revalidation_status import (
    KnowledgeFreshnessStatus, FRESHNESS_PRIORITY, classify_revalidation,
)
from strategy.programme_revalidation_report import (
    build_revalidation_report, PROGRAMME_REVALIDATION_REPORT_VERSION,
)


# ---- programme_context_changes -------------------------------------------------------------

def test_version_change_detected_same_car_driver_diff_version():
    comp = {"primary_key": {"car": "GT-R", "driver": "L"},
            "excluded_reasons": [{"compatibility_key": {"car": "GT-R", "driver": "L"},
                                  "differing_fields": ["gt7_version"]}]}
    pc = programme_context_changes(comp)
    assert pc["version_changed"] is True
    assert "gt7_version" in pc["changed_fields"]


def test_version_change_not_detected_when_car_differs():
    comp = {"primary_key": {"car": "GT-R", "driver": "L"},
            "excluded_reasons": [{"compatibility_key": {"car": "Supra", "driver": "L"},
                                  "differing_fields": ["gt7_version", "car"]}]}
    pc = programme_context_changes(comp)
    assert pc["version_changed"] is False  # different car -> not a pure version change
    assert set(pc["changed_fields"]) == {"gt7_version", "car"}


def test_context_changes_empty_safe():
    assert programme_context_changes(None) == {"version_changed": False, "changed_fields": ()}
    assert programme_context_changes({}) == {"version_changed": False, "changed_fields": ()}


# ---- decay_signals -------------------------------------------------------------------------

def _conv(**kw):
    base = {"domain": "differential", "convergence_status": "strongly_converged",
            "independent_support_count": 3, "dependent_support_count": 0, "regression_count": 0,
            "conflict_count": 0, "transfer_limitations": [], "retired_directions": [],
            "confirmed_good": False, "current_maturity": "established",
            "current_confidence": "high", "compatible_contexts": 2}
    base.update(kw)
    return base


def _pts(*dates):
    return [{"knowledge_domain": "differential", "evidence_date": d} for d in dates]


def test_age_alone_does_not_decay():
    # very old but strongly converged, independent, compatible -> stays "current"
    sig = decay_signals(_conv(), _pts("2019-01-01", "2019-02-01", "2019-03-01"),
                        {"version_changed": False, "changed_fields": ()})
    sig["domain"] = "differential"
    st = classify_revalidation(sig, {"gt7_version": "1.0"})
    assert st.freshness_status == KnowledgeFreshnessStatus.CURRENT.value


def test_dependent_heavy_signal():
    sig = decay_signals(_conv(convergence_status="converging", independent_support_count=1,
                              dependent_support_count=4), _pts("2026-01-01"),
                        {"version_changed": False, "changed_fields": ()})
    assert sig["dependent_heavy"] is True
    assert MIN_INDEPENDENT_FOR_ROBUST == 2


def test_all_dates_unknown_signal():
    sig = decay_signals(_conv(), _pts("unknown", ""), {"version_changed": False, "changed_fields": ()})
    assert sig["all_dates_unknown"] is True
    assert sig["last_known_date"] == ""


def test_version_sensitive_from_transfer_limits():
    sig = decay_signals(_conv(transfer_limitations=["depends on gt7_version"]), _pts("2026-01-01"),
                        {"version_changed": True, "changed_fields": ("gt7_version",)})
    assert sig["version_sensitive"] is True
    assert sig["version_changed"] is True


# ---- reasons -------------------------------------------------------------------------------

def test_context_change_reason_map():
    assert context_change_reason("gt7_version") == RevalidationReason.GT7_VERSION_CHANGED.value
    assert context_change_reason("track") == RevalidationReason.TRACK_CHANGED.value
    assert context_change_reason("nonsense") == ""


def test_reasons_only_emitted_when_signal_present():
    assert reasons_from_signals({}) == ()
    rs = reasons_from_signals({"is_superseded": True})
    assert [r["reason"] for r in rs] == [RevalidationReason.KNOWLEDGE_SUPERSEDED.value]


def test_reasons_dedup_and_version_gated():
    # version change only emits GT7 reason when version_sensitive too
    assert reasons_from_signals({"version_changed": True}) == ()
    rs = reasons_from_signals({"version_changed": True, "version_sensitive": True})
    assert any(r["reason"] == RevalidationReason.GT7_VERSION_CHANGED.value for r in rs)


# ---- classify_revalidation ladder ----------------------------------------------------------

def _classify(**sig):
    sig.setdefault("domain", "differential")
    return classify_revalidation(sig, {"gt7_version": "1.0"}).freshness_status


def test_superseded_wins():
    assert _classify(is_superseded=True, is_confirmed_good=True) == \
        KnowledgeFreshnessStatus.SUPERSEDED.value


def test_retired_only_when_not_confirmed_good_and_bad_convergence():
    assert _classify(retired_directions=("d",), convergence_status="regressed") == \
        KnowledgeFreshnessStatus.RETIRED.value
    # confirmed-good protects even if an unrelated direction is retired
    assert _classify(retired_directions=("d",), convergence_status="regressed",
                     is_confirmed_good=True, has_regression=True) == \
        KnowledgeFreshnessStatus.CURRENT.value


def test_conflict_weakens():
    assert _classify(has_conflict=True) == KnowledgeFreshnessStatus.WEAKENED_BY_CONFLICT.value


def test_regression_weakens_unless_confirmed_good():
    assert _classify(has_regression=True) == KnowledgeFreshnessStatus.WEAKENED_BY_REGRESSION.value


def test_version_change_invalidates_only_version_sensitive():
    assert _classify(version_sensitive=True, version_changed=True) == \
        KnowledgeFreshnessStatus.INVALIDATED_BY_VERSION_CHANGE.value
    # version-insensitive knowledge is NOT invalidated by a version change
    assert _classify(version_sensitive=False, version_changed=True,
                     convergence_status="strongly_converged") == \
        KnowledgeFreshnessStatus.CURRENT.value


def test_unknown_date_produces_insufficient_date_evidence():
    assert _classify(all_dates_unknown=True) == \
        KnowledgeFreshnessStatus.INSUFFICIENT_DATE_EVIDENCE.value


def test_context_bound_confirmed_good_context_bound():
    assert _classify(is_confirmed_good=True, is_context_bound=True) == \
        KnowledgeFreshnessStatus.CURRENT_BUT_CONTEXT_BOUND.value


def test_priority_ordering_constant_complete():
    for s in KnowledgeFreshnessStatus:
        assert s.value in FRESHNESS_PRIORITY


# ---- report assembly -----------------------------------------------------------------------

def test_build_report_empty_safe():
    r = build_revalidation_report(None, None).to_dict()
    assert r["items"] == []
    assert r["eval_version"] == PROGRAMME_REVALIDATION_REPORT_VERSION


def test_build_report_buckets_and_fingerprint_stable():
    timeline = {"source_programme": {"car": "GT-R", "discipline": "race", "gt7_version": "1.0",
                                     "driver": "L"},
                "convergence_summaries": [_conv(domain="differential"),
                                          _conv(domain="weight_transfer", convergence_status="conflicting",
                                                conflict_count=1)],
                "timeline_points": _pts("2026-01-01"),
                "content_fingerprint": "p25:xyz"}
    programme = {"compatibility": {}, "content_fingerprint": "p22:abc"}
    a = build_revalidation_report(timeline, programme).to_dict()
    b = build_revalidation_report(timeline, programme).to_dict()
    assert a["content_fingerprint"] == b["content_fingerprint"]
    assert len(a["items"]) == 2
    domains = {i["domain"] for i in a["conflict_weakened"]}
    assert "weight_transfer" in domains
