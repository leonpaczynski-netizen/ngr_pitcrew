"""Phase 63-65 — audio/PTT/strategy certification: per-area, overall NOT validated, honest caps."""
from __future__ import annotations

from strategy.event_programme_certification import (
    AUDIO_STRATEGY_CERTIFICATION_AREAS, audio_strategy_certification, CertificationLevel, EvidenceType,
)


def test_audio_certification_has_all_areas():
    cert = audio_strategy_certification()
    names = {a.name for a in cert.areas}
    assert set(AUDIO_STRATEGY_CERTIFICATION_AREAS).issubset(names)
    assert len(AUDIO_STRATEGY_CERTIFICATION_AREAS) == 23


def test_physical_and_live_areas_are_none_with_next_evidence():
    cert = audio_strategy_certification()
    by = {a.name: a for a in cert.areas}
    for name in ("psvr2_audio_first_mode", "physical_tts", "ptt_input_binding",
                 "offline_speech_recognition", "physical_hardware_testing"):
        assert by[name].evidence_type == EvidenceType.NONE
        assert by[name].findings and "needs" in by[name].findings[0].message.lower()


def test_domain_areas_are_automated():
    cert = audio_strategy_certification()
    by = {a.name: a for a in cert.areas}
    for name in ("message_prioritisation", "command_grammar", "time_certain_optimisation",
                 "fuel_divergence", "acknowledgement", "repeated_replanning"):
        assert by[name].evidence_type == EvidenceType.AUTOMATED


def test_overall_is_not_operationally_ready():
    cert = audio_strategy_certification()
    assert cert.overall_level != CertificationLevel.OPERATIONALLY_READY
    assert cert.overall_level != CertificationLevel.OPERATIONALLY_READY_WITH_LIMITATIONS


def test_automated_cannot_grant_physical_voice_or_psvr2():
    cert = audio_strategy_certification()
    by = {a.name: a for a in cert.areas}
    # the physical areas are strictly NONE — automated tests never lift them
    assert by["physical_tts"].evidence_type == EvidenceType.NONE
    assert by["psvr2_audio_first_mode"].evidence_type == EvidenceType.NONE


def test_deterministic():
    a = audio_strategy_certification()
    b = audio_strategy_certification()
    assert a.fingerprint == b.fingerprint
