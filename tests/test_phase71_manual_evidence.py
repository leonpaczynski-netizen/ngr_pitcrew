"""Phase 71 — manual UAT evidence: observation construction, ledger precedence (latest supersedes prior,
history preserved), retest-required, area alignment to the Phase-68 taxonomy, and store persistence."""
from __future__ import annotations

import json
from pathlib import Path

from strategy.manual_uat_evidence import (
    ManualUatLedger, ManualUatObservation, ManualUatStatus, make_observation, MANUAL_UAT_AREAS,
    manual_uat_area_keys, required_physical_live_areas, is_valid_area,
)


def test_areas_align_with_certification_taxonomy():
    from strategy.event_programme_certification import LIVE_VR_CERTIFICATION_AREAS
    cert_areas = set(LIVE_VR_CERTIFICATION_AREAS)
    # every mapped cert_area (non-empty) must be a real Phase-68 area — one taxonomy, never a second one
    for a in MANUAL_UAT_AREAS:
        if a.cert_area:
            assert a.cert_area in cert_areas, a.key
    assert len(manual_uat_area_keys()) == 31


def test_required_physical_live_areas():
    req = required_physical_live_areas()
    assert "physical_tts" in req and "keyboard_ptt" in req and "wheel_joystick_ptt" in req
    assert "psvr2_audibility" in req and "live_gt7_operational_suitability" in req
    # a pure software/strategy area is NOT in the required physical/live set
    assert "fuel_mapping" not in req


def test_make_observation_stamps_and_defaults_retest_on_fail():
    o = make_observation("physical_tts", ManualUatStatus.FAIL, notes="no audio")
    assert o.status == ManualUatStatus.FAIL
    assert o.retest_required is True          # a failed area must be retested
    assert o.fingerprint


def test_pass_does_not_force_retest():
    o = make_observation("physical_tts", ManualUatStatus.PASS)
    assert o.retest_required is False


def test_ledger_latest_supersedes_prior_and_preserves_history():
    led = ManualUatLedger()
    led = led.append(make_observation("keyboard_ptt", ManualUatStatus.FAIL, notes="v1"))
    led = led.append(make_observation("keyboard_ptt", ManualUatStatus.PASS, notes="v2 fixed"))
    assert led.status_of("keyboard_ptt") == ManualUatStatus.PASS
    assert len(led.history("keyboard_ptt")) == 2           # prior preserved for audit
    assert led.active("keyboard_ptt").supersedes            # wired to supersede the prior fingerprint


def test_ledger_never_auto_creates_pass():
    # a fresh ledger reports NOT_RUN for every area — nothing is passed without an explicit append
    led = ManualUatLedger()
    for k in manual_uat_area_keys():
        assert led.status_of(k) == ManualUatStatus.NOT_RUN


def test_observation_roundtrip():
    o = make_observation("psvr2_race", ManualUatStatus.PASS, notes="clear", candidate_commit="abc",
                         evidence_reference="clip1.mp4", hardware_context="PSVR2")
    o2 = ManualUatObservation.from_dict(o.to_dict())
    assert o2.area == "psvr2_race" and o2.status == ManualUatStatus.PASS
    assert o2.evidence_reference == "clip1.mp4"


def test_invalid_area_helper():
    assert is_valid_area("physical_tts")
    assert not is_valid_area("nonexistent_area")


def test_store_persists_and_reloads(tmp_path: Path):
    from data.manual_uat_store import ManualUatStore
    p = tmp_path / "manual_uat_evidence.json"
    store = ManualUatStore(p)
    assert store.record(make_observation("physical_microphone", ManualUatStatus.PASS, notes="works"))
    assert p.exists()
    # a fresh store reloads the same evidence
    store2 = ManualUatStore(p)
    assert store2.ledger.status_of("physical_microphone") == ManualUatStatus.PASS
    # the file is real JSON with the observation
    payload = json.loads(p.read_text(encoding="utf-8"))
    assert payload["observations"] and payload["observations"][0]["area"] == "physical_microphone"


def test_store_survives_corrupt_file(tmp_path: Path):
    from data.manual_uat_store import ManualUatStore
    p = tmp_path / "manual_uat_evidence.json"
    p.write_text("{ this is not valid json", encoding="utf-8")
    store = ManualUatStore(p)   # must not raise
    assert isinstance(store.ledger, ManualUatLedger)
    assert len(store.ledger.observations) == 0
