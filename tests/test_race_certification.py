"""Live Activation 3 — race-day certification workflow domain + additive report store."""
from __future__ import annotations

import json

from data.race_certification_store import RaceCertificationStore
from strategy.race_certification import (
    CertVerdict, EvidenceKind, STAGE_KEYS, StageState, compute_verdict, new_report,
    record_stage, report_from_payload,
)


def _pass_all(stages, evidence=EvidenceKind.MANUAL):
    for k in STAGE_KEYS:
        stages = record_stage(stages, k, state=StageState.PASS, evidence=evidence)
    return stages


# =============================== stage rules =================================
def test_initial_verdict_is_not_tested():
    r = new_report("controlled-event")
    assert r.verdict == CertVerdict.NOT_TESTED


def test_physical_pass_needs_manual_evidence():
    stages = new_report("e").stages
    # simulated telemetry "passes" a physical stage → NOT credited
    stages = record_stage(stages, "live_race", state=StageState.PASS, evidence=EvidenceKind.SIMULATED)
    live_race = next(s for s in stages if s.spec.key == "live_race")
    assert live_race.state == StageState.PASS
    assert live_race.effective_state == StageState.NOT_TESTED
    assert live_race.credited_downgraded


def test_automated_can_pass_a_non_physical_stage():
    stages = new_report("e").stages
    stages = record_stage(stages, "environment_build", state=StageState.PASS,
                          evidence=EvidenceKind.AUTOMATED)
    s = next(s for s in stages if s.spec.key == "environment_build")
    assert s.effective_state == StageState.PASS  # non-physical → automated is fine


# =============================== verdict rules ===============================
def test_certified_requires_all_mandatory_manual_pass():
    stages = _pass_all(new_report("e").stages)
    v, _ = compute_verdict(stages)
    assert v == CertVerdict.CERTIFIED


def test_not_certified_while_physical_gate_not_tested():
    stages = new_report("e").stages
    # everything simulated → no physical gate is credited
    stages = _pass_all(stages, evidence=EvidenceKind.SIMULATED)
    v, reason = compute_verdict(stages)
    assert v != CertVerdict.CERTIFIED
    assert v in (CertVerdict.IN_PROGRESS, CertVerdict.NOT_TESTED)
    assert "not_tested" in reason.lower() or "in progress" in reason.lower()


def test_any_fail_forces_failed():
    stages = _pass_all(new_report("e").stages)
    stages = record_stage(stages, "voice", state=StageState.FAIL, evidence=EvidenceKind.MANUAL,
                          detail="no audio through PSVR2")
    v, reason = compute_verdict(stages)
    assert v == CertVerdict.FAILED and "Voice" in reason


def test_blocked_forces_failed():
    stages = _pass_all(new_report("e").stages)
    stages = record_stage(stages, "telemetry", state=StageState.BLOCKED, evidence=EvidenceKind.MANUAL)
    assert compute_verdict(stages)[0] == CertVerdict.FAILED


def test_conditional_on_noncore_stage_is_conditionally_certified():
    stages = _pass_all(new_report("e").stages)
    stages = record_stage(stages, "voice", state=StageState.CONDITIONAL, evidence=EvidenceKind.MANUAL,
                          limitations=("occasional TTS clipping under load",))
    v, reason = compute_verdict(stages)
    assert v == CertVerdict.CONDITIONALLY_CERTIFIED
    assert "clipping" in reason


def test_conditional_on_core_safety_is_not_conditionally_certified():
    stages = _pass_all(new_report("e").stages)
    # live_race is core_safety — a CONDITIONAL there cannot yield conditional certification
    stages = record_stage(stages, "live_race", state=StageState.CONDITIONAL, evidence=EvidenceKind.MANUAL)
    v, _ = compute_verdict(stages)
    assert v != CertVerdict.CONDITIONALLY_CERTIFIED
    assert v != CertVerdict.CERTIFIED


# =============================== export ======================================
def test_json_export_has_ids_and_legend():
    ev = {"event_id": "42", "car_id": "333", "car_name": "GT-R", "git_commit": "abc123",
          "db_version": 40, "rule_engine_version": "46.0"}
    r = new_report("league-r3", evidence=ev)
    r = r.__class__(scenario=r.scenario, stages=_pass_all(r.stages), evidence=ev)
    payload = json.loads(r.as_json())
    assert payload["verdict"] == "certified" and payload["certified"] is True
    assert payload["evidence"]["event_id"] == "42"
    assert set(payload["evidence_legend"]) == {"automated", "simulated", "manual"}
    assert len(payload["stages"]) == len(STAGE_KEYS)


def test_markdown_marks_simulated_downgrade():
    stages = new_report("e").stages
    stages = record_stage(stages, "live_race", state=StageState.PASS, evidence=EvidenceKind.SIMULATED)
    r = new_report("e").__class__(scenario="e", stages=stages, evidence={})
    md = r.as_markdown()
    assert "not credited" in md and "manual" in md.lower()


def test_roundtrip_from_payload():
    stages = _pass_all(new_report("rt").stages)
    r = new_report("rt").__class__(scenario="rt", stages=stages, evidence={"event_id": "7"})
    r2 = report_from_payload(json.loads(r.as_json()))
    assert r2.verdict == r.verdict == CertVerdict.CERTIFIED
    assert r2.evidence.get("event_id") == "7"


# =============================== store =======================================
def test_store_save_load_and_export(tmp_path):
    store = RaceCertificationStore(str(tmp_path))
    r = new_report("controlled").__class__(
        scenario="controlled", stages=_pass_all(new_report("c").stages), evidence={"event_id": "42"})
    jpath = store.save("2026-08-02-league-r3", r)
    assert jpath.endswith(".json")
    # both formats written, in the store's own folder (not user runtime data)
    assert "race_certifications" in store.directory
    assert store.list_reports() == ["2026-08-02-league-r3"]
    loaded = store.load("2026-08-02-league-r3")
    assert loaded is not None and loaded.verdict == CertVerdict.CERTIFIED
    md_path = tmp_path / "out.md"
    store.export_markdown(str(md_path), r)
    assert md_path.read_text(encoding="utf-8").startswith("# Race-Day Certification")


def test_store_load_missing_returns_none(tmp_path):
    assert RaceCertificationStore(str(tmp_path)).load("nope") is None
