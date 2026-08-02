"""Live Activation 3 — the guided certification panel VM + panel + bridge wiring."""
from __future__ import annotations

import os
import types

import pytest

from strategy.race_certification import (
    CertVerdict, EvidenceKind, STAGE_KEYS, StageState, new_report, record_stage,
)
from ui.components.race_certification_panel import race_certification_vm

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _certified_payload():
    stages = new_report("e").stages
    for k in STAGE_KEYS:
        stages = record_stage(stages, k, state=StageState.PASS, evidence=EvidenceKind.MANUAL)
    return new_report("e").__class__(scenario="e", stages=stages, evidence={}).as_json_payload()


# ================================== VM =======================================
def test_vm_verdict_and_rows():
    vm = race_certification_vm(_certified_payload())
    assert vm["verdict"] == "certified" and vm["verdict_tone"] == "success"
    assert len(vm["rows"]) == len(STAGE_KEYS)
    assert all(r["effective_state"] == "pass" for r in vm["rows"])


def test_vm_marks_downgraded_physical_stage():
    stages = new_report("e").stages
    stages = record_stage(stages, "live_race", state=StageState.PASS, evidence=EvidenceKind.SIMULATED)
    payload = new_report("e").__class__(scenario="e", stages=stages, evidence={}).as_json_payload()
    vm = race_certification_vm(payload)
    race = next(r for r in vm["rows"] if r["key"] == "live_race")
    assert race["effective_state"] == "not_tested"
    assert "manual evidence" in race["note"]


def test_vm_never_raises_on_garbage():
    assert race_certification_vm(None)["verdict"] == "not_tested"


# ================================ panel ======================================
def test_panel_renders_and_emits(qapp):
    from ui.components.race_certification_panel import RaceCertificationPanel
    panel = RaceCertificationPanel()
    captured = []
    panel.stage_recorded.connect(lambda k, s, e: captured.append((k, s, e)))
    exports = []
    panel.export_requested.connect(lambda f: exports.append(f))
    try:
        panel.set_report(_certified_payload())
        # export buttons work
        panel._btn_json.click()
        panel._btn_md.click()
        assert exports == ["json", "markdown"]
        # a physical stage has a manual selector; choosing FAIL emits manual evidence
        combo = panel._selectors.get("voice")
        assert combo is not None
        idx = next(i for i in range(combo.count()) if combo.itemData(i) == "fail")
        combo.setCurrentIndex(idx)
        assert ("voice", "fail", "manual") in captured
    finally:
        panel.deleteLater()
        qapp.processEvents()


# ============================ bridge wiring ==================================
def test_bridge_certification_flow(qapp, tmp_path):
    from data.session_db import SessionDB
    from ui.live_shell_bridge import LiveShellBridge
    from ui.pit_crew_controller import PitCrewController
    from ui.pit_crew_shell import PitCrewShell

    db = SessionDB(str(tmp_path / "s.db"))
    db.upsert_preparation_cycle({"cycle_id": "cyc-1", "event_id": 42, "event_name": "R", "track": "Fuji",
                                 "car": "GT-R", "official_race_date": "2026-06-21",
                                 "format_profile_id": "multiweek", "explicit_state": "active"})
    win = types.SimpleNamespace(
        _dispatcher=types.SimpleNamespace(_session_id=0), _car_id=333, _connected=False,
        _config_path=str(tmp_path / "config.json"),
        _tracker=types.SimpleNamespace(phase="idle", pit_phase="not_in_pit", race_type=None),
        _build_session_context=lambda: types.SimpleNamespace(connected=False),
        _current_car_id=lambda: 333)
    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)
    b = LiveShellBridge(shell, ctrl, window=win, config={"active_cycle_id": "cyc-1"}, db=db,
                        spawn=lambda fn: fn())
    try:
        # start → panel becomes visible and shows an uncertified verdict (physical gates NOT_TESTED)
        b.start_race_certification()
        assert b._race_cert_report is not None
        assert b._race_cert_report.verdict != CertVerdict.CERTIFIED
        # setVisible(True) was applied (isVisible() also needs the top-level shown, which it isn't
        # in an offscreen test — isHidden() reflects the widget's own visibility flag).
        assert not shell.live_page.certification.isHidden()

        # record a manual FAIL on voice → verdict FAILED
        b._on_cert_stage_recorded("voice", "fail", "manual")
        assert b._race_cert_report.verdict == CertVerdict.FAILED

        # a simulated PASS on a physical stage is NOT credited (verdict cannot become certified)
        b._on_cert_stage_recorded("voice", "pass", "simulated")
        assert b._race_cert_report.verdict != CertVerdict.CERTIFIED

        # export writes a report to the store beside config
        b._on_cert_export("json")
        assert b._race_cert_store().list_reports()
    finally:
        shell.close(); shell.deleteLater(); qapp.processEvents()
