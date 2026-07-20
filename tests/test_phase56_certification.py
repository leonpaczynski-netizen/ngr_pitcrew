"""Phase 56 — end-to-end certification domain + bounds (task items 29-30)."""
from __future__ import annotations

from strategy.event_programme_certification import (
    EvidenceType as E, CertificationLevel as C, CertificationArea, CertificationFinding,
    FindingSeverity as F, build_event_programme_certification, CERTIFICATION_AREAS,
)


def _areas(ev):
    return [CertificationArea("home", ev), CertificationArea("live", ev)]


def test_all_23_areas_defined():
    assert len(CERTIFICATION_AREAS) == 23


def test_overall_bounded_by_weakest():
    areas = [CertificationArea("home", E.LIVE), CertificationArea("live", E.AUTOMATED)]
    cert = build_event_programme_certification(areas)
    assert cert.overall_level == C.AUTOMATED_ONLY and cert.weakest_area == "live"


def test_automated_cannot_award_visual_or_live_or_operational():
    cert = build_event_programme_certification(_areas(E.AUTOMATED), operationally_ready_granted=True)
    assert cert.overall_level == C.AUTOMATED_ONLY  # grant ignored without live evidence


def test_offscreen_cannot_award_visual():
    assert build_event_programme_certification(_areas(E.OFFSCREEN)).overall_level == C.OFFSCREEN_VALIDATED


def test_replay_cannot_award_live():
    assert build_event_programme_certification(_areas(E.REPLAY)).overall_level == C.REPLAY_VALIDATED


def test_visual_and_live_levels():
    assert build_event_programme_certification(_areas(E.VISUAL)).overall_level == C.VISUAL_UAT_VALIDATED
    assert build_event_programme_certification(_areas(E.LIVE)).overall_level == C.LIVE_GT7_VALIDATED


def test_operationally_ready_requires_live_and_grant():
    granted = build_event_programme_certification(_areas(E.LIVE), operationally_ready_granted=True)
    assert granted.overall_level == C.OPERATIONALLY_READY
    partial = build_event_programme_certification(_areas(E.LIVE_PARTIAL), operationally_ready_granted=True)
    assert partial.overall_level == C.OPERATIONALLY_READY_WITH_LIMITATIONS


def test_blocker_withholds_operational_readiness():
    blocked = CertificationArea("live", E.LIVE, findings=(
        CertificationFinding("crash", F.BLOCKER, "live race crashes"),))
    cert = build_event_programme_certification([CertificationArea("home", E.LIVE), blocked],
                                               operationally_ready_granted=True)
    assert cert.overall_level not in (C.OPERATIONALLY_READY, C.OPERATIONALLY_READY_WITH_LIMITATIONS)
    assert cert.blockers


def test_limitations_surfaced():
    area = CertificationArea("home", E.LIVE, findings=(
        CertificationFinding("minor", F.LIMITATION, "no wet-weather test"),))
    cert = build_event_programme_certification([area, CertificationArea("live", E.LIVE)])
    assert any("wet-weather" in l for l in cert.limitations)


def test_certification_deterministic():
    a = build_event_programme_certification(_areas(E.OFFSCREEN))
    b = build_event_programme_certification(_areas(E.OFFSCREEN))
    assert a.fingerprint == b.fingerprint


def test_this_slice_certification_is_bounded_below_live():
    # Phase 54-56 evidence is automated/offscreen/replay only -> never live/operational
    areas = [CertificationArea(n, E.AUTOMATED) for n in ("home", "live_practice", "session_end")]
    areas.append(CertificationArea("home_command_centre", E.OFFSCREEN))
    cert = build_event_programme_certification(areas, operationally_ready_granted=True)
    assert cert.overall_level in (C.AUTOMATED_ONLY,)  # weakest is automated
