"""Phase 68 — live GT7 / PSVR2 / physical-device certification: per-area, honest caps, overall bounded."""
from __future__ import annotations

from strategy.event_programme_certification import (
    LIVE_VR_CERTIFICATION_AREAS, live_vr_certification, CertificationLevel, EvidenceType,
)


def test_all_areas_present():
    cert = live_vr_certification()
    names = {a.name for a in cert.areas}
    assert set(LIVE_VR_CERTIFICATION_AREAS).issubset(names)
    assert len(LIVE_VR_CERTIFICATION_AREAS) == 31


def test_physical_and_live_areas_are_none_with_next_evidence():
    by = {a.name: a for a in live_vr_certification().areas}
    for name in ("physical_tts", "keyboard_ptt", "controller_ptt", "wheel_ptt", "microphone_recognition",
                 "psvr2_practice", "psvr2_qualifying", "psvr2_race", "session_binding", "debrief",
                 "cumulative_learning", "device_failure"):
        assert by[name].evidence_type == EvidenceType.NONE
        assert by[name].findings and "needs" in by[name].findings[0].message.lower()


def test_domain_areas_automated():
    by = {a.name: a for a in live_vr_certification().areas}
    for name in ("real_tracker_mapping", "race_clock", "fuel_burn", "time_certain_strategy",
                 "revised_candidate_ranking", "command_grammar", "tts_ptt_coordination", "telemetry_loss"):
        assert by[name].evidence_type == EvidenceType.AUTOMATED


def test_ui_areas_offscreen():
    by = {a.name: a for a in live_vr_certification().areas}
    assert by["live_tab_strategy_card"].evidence_type == EvidenceType.OFFSCREEN
    assert by["visual_fallback"].evidence_type == EvidenceType.OFFSCREEN


def test_overall_not_operationally_ready_from_automated():
    cert = live_vr_certification()
    assert cert.overall_level != CertificationLevel.OPERATIONALLY_READY
    assert cert.overall_level != CertificationLevel.OPERATIONALLY_READY_WITH_LIMITATIONS
    # bounded by the NONE live/physical areas
    assert cert.overall_level == CertificationLevel.NOT_TESTED


def test_automated_cannot_grant_physical_or_psvr2_or_live():
    by = {a.name: a for a in live_vr_certification().areas}
    for name in ("physical_tts", "microphone_recognition", "wheel_ptt", "psvr2_race", "session_binding"):
        assert by[name].effective_level == CertificationLevel.NOT_TESTED


def test_deterministic():
    assert live_vr_certification().fingerprint == live_vr_certification().fingerprint
