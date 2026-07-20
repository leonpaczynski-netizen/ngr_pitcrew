"""Phase 59 — per-area live-event certification + UAT instrumentation (task items 32-35)."""
from __future__ import annotations

from strategy.event_programme_certification import (
    EvidenceType as E, CertificationLevel as C, CertificationArea, CertificationFinding,
    FindingSeverity as F, build_event_programme_certification, LIVE_CERTIFICATION_AREAS,
    live_event_certification, required_next_evidence, CertificationRun,
)


def test_live_areas_defined():
    assert len(LIVE_CERTIFICATION_AREAS) == 31
    for a in ("practice_runtime", "qualifying_runtime", "race_runtime", "voice_gating", "ngr_immersion"):
        assert a in LIVE_CERTIFICATION_AREAS


def test_live_certification_is_differentiated_not_one_undifferentiated_not_tested():
    cert = live_event_certification()
    levels = {a.name: a.effective_level.value for a in cert.areas}
    # overall is NOT_TESTED (bounded by live areas) BUT per-area detail is preserved
    assert cert.overall_level == C.NOT_TESTED
    assert levels["setup_match"] == "automated_only"       # automated area proven
    assert levels["command_centre"] == "offscreen_validated"
    assert levels["practice_runtime"] == "not_tested"       # live area unrun
    # many areas carry real evidence (not all NOT_TESTED)
    proven = [n for n, lv in levels.items() if lv != "not_tested"]
    assert len(proven) >= 15


def test_each_live_area_has_required_next_evidence():
    cert = live_event_certification()
    for a in cert.areas:
        if a.effective_level.value == "not_tested":
            assert required_next_evidence(a.name)  # what evidence would lift it
            assert a.findings and a.findings[0].severity == F.LIMITATION


def test_certification_caps_retained():
    # automated cannot award live/visual/operational; offscreen cannot award visual; replay cannot award live
    assert build_event_programme_certification([CertificationArea("x", E.AUTOMATED)],
                                               operationally_ready_granted=True).overall_level == C.AUTOMATED_ONLY
    assert build_event_programme_certification([CertificationArea("x", E.OFFSCREEN)]).overall_level == C.OFFSCREEN_VALIDATED
    assert build_event_programme_certification([CertificationArea("x", E.REPLAY)]).overall_level == C.REPLAY_VALIDATED


def test_operational_ready_requires_all_live_and_grant_and_no_blocker():
    areas = [CertificationArea(n, E.LIVE) for n in ("a", "b")]
    assert build_event_programme_certification(areas, operationally_ready_granted=True).overall_level == C.OPERATIONALLY_READY
    # add a blocker -> withheld
    areas2 = areas + [CertificationArea("c", E.LIVE, findings=(CertificationFinding("x", F.BLOCKER, "bad"),))]
    cert = build_event_programme_certification(areas2, operationally_ready_granted=True)
    assert cert.overall_level not in (C.OPERATIONALLY_READY, C.OPERATIONALLY_READY_WITH_LIMITATIONS)


# --- certification-run export (deterministic report, no DB) -----------------

def test_certification_run_report_deterministic():
    cert = live_event_certification()
    r1 = CertificationRun("full-journey", cert, captured_label="phase57-59").as_report()
    r2 = CertificationRun("full-journey", cert, captured_label="phase57-59").as_report()
    assert r1 == r2
    assert r1["scenario"] == "full-journey" and r1["certification"]["overall_level"] == "not_tested"
    assert r1["fingerprint"] == cert.fingerprint


def test_certification_deterministic():
    assert live_event_certification().fingerprint == live_event_certification().fingerprint
