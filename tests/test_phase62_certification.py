"""Phase 62 — production per-area certification + real-tracker field limitations (task items 27-28)."""
from __future__ import annotations

from strategy.event_programme_certification import (
    EvidenceType as E, CertificationLevel as C, CertificationArea, CertificationFinding,
    FindingSeverity as F, build_event_programme_certification, PRODUCTION_CERTIFICATION_AREAS,
    production_event_certification, runtime_field_limitations, RuntimeFieldStatus as RS,
)


def test_28_production_areas():
    assert len(PRODUCTION_CERTIFICATION_AREAS) == 28
    for a in ("tracker_connection", "practice_mode", "qualifying_mode", "race_mode", "voice_gating"):
        assert a in PRODUCTION_CERTIFICATION_AREAS


def test_production_certification_differentiated_not_all_not_tested():
    cert = production_event_certification()
    levels = {a.name: a.effective_level.value for a in cert.areas}
    assert cert.overall_level == C.NOT_TESTED   # bounded by live areas
    assert levels["explicit_binding"] == "automated_only"        # domain proven
    assert levels["event_command_centre"] == "offscreen_validated"
    assert levels["tracker_connection"] == "not_tested"          # live area unrun
    proven = [n for n, lv in levels.items() if lv != "not_tested"]
    assert len(proven) >= 12


def test_live_areas_carry_required_next_evidence():
    for a in production_event_certification().areas:
        if a.effective_level.value == "not_tested":
            assert a.findings and a.findings[0].severity == F.LIMITATION


def test_certification_caps_retained():
    assert build_event_programme_certification([CertificationArea("x", E.AUTOMATED)],
                                               operationally_ready_granted=True).overall_level == C.AUTOMATED_ONLY
    assert build_event_programme_certification([CertificationArea("x", E.REPLAY)]).overall_level == C.REPLAY_VALIDATED
    assert build_event_programme_certification([CertificationArea("x", E.OFFSCREEN)]).overall_level == C.OFFSCREEN_VALIDATED


# --- real-tracker field limitations (Audit B) ------------------------------

def test_field_limitations_recorded():
    lims = {l.field: l for l in runtime_field_limitations()}
    assert lims["car"].status == RS.EXACT and lims["fuel_state"].status == RS.EXACT
    assert lims["layout"].status == RS.LIMITED
    assert lims["event_context"].status == RS.INFERRED


def test_applied_setup_is_a_proxy_blocking_setup_attribution():
    lims = {l.field: l for l in runtime_field_limitations()}
    setup = lims["applied_setup_fingerprint"]
    assert setup.status == RS.LIMITED and "proxy" in setup.source.lower()
    assert "setup_attribution" in setup.blocks and "exact_setup_identity" in setup.blocks


def test_limitations_do_not_block_practice_pace():
    # no limitation blocks Practice pace/consistency (only setup-identity-dependent evidence)
    for l in runtime_field_limitations():
        assert "practice_pace" not in l.blocks and "consistency" not in l.blocks


def test_certification_deterministic():
    assert production_event_certification().fingerprint == production_event_certification().fingerprint
