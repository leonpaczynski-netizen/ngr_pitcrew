"""End-to-end EVENT-LIFECYCLE simulation over the REAL wired stack.

This is the integration layer the unit suite was missing. It builds the *real*
objects the app builds — MainWindow (classic) + SessionDB + PitCrewShell +
LiveShellBridge — against isolated temp paths (the config-safe pattern from
test_ui_structure_smoke.py) and drives them through the whole race-prep
lifecycle a driver actually walks:

    track mapping -> create + activate event -> preparation cycle
      -> practice runs -> programme evidence advances the objective
      -> setup development (baseline/analyse/apply/lock)
      -> race strategy (build + persist) -> live race engineer
      -> event completion.

Why it exists: nearly every UAT defect on the shell has been a wiring/state
defect at the shell<->bridge<->window<->db seams — the class that unit tests
with *fake* collaborators cannot see (a fake drifts from the real object, the
test stays green, the shipped app breaks). This test drives the seams with the
real objects, so that class of regression is caught here instead of in UAT.

Determinism / scope (honest limits — these need a live GT7/PSVR2 rig and are
NOT covered here):
  * runs are recorded via the SessionDB writer path, not the live-telemetry
    capture pipeline (which needs the UDP stream);
  * the setup brain is exercised through a deterministic stub advisor (the real
    DrivingAdvisor needs recorded laps) — the SetupService + bridge WIRING is
    real, the rule engine's telemetry reasoning is not re-tested here;
  * the track model is written as an accepted-model file, not built from a live
    capture;
  * the live decision uses the pure strategy engine; the bridge's per-lap
    adapter is only pumped, not fed a live plan+samples.

The stack, services, and every wiring seam between them ARE real.

Skipped when PyQt6 isn't importable so pure-Python CI still passes.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import queue
import tempfile
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not available for headless simulation")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("NGR_NO_STRAY_GUARD", "1")

CAR = "Porsche 911 RSR"
TRACK = "Fuji International Speedway"
LOC = "fuji_international_speedway"
LAY = "fuji_international_speedway__full_course"


# --------------------------------------------------------------------------- #
# Deterministic setup advisor/authority (mirrors tests/test_setup_service.py). #
# --------------------------------------------------------------------------- #
class _StubAdvisor:
    """DrivingAdvisor stand-in: both entry points return a JSON string."""

    def build_baseline_setup_response(self, **kw):
        return json.dumps({"setup_fields": {"arb_front": 6, "arb_rear": 5,
                                            "springs_front": 3.4}})

    def build_combined_setup_response(self, setup, **kw):
        return json.dumps({
            "analysis": "Front is washing out on entry.",
            "changes": [{"field": "arb_front", "from": 6, "to": 5,
                         "reason": "reduce understeer"}],
            "setup_fields": {"arb_front": 5},
            "recommendation_status": "approved"})


class _StubAuthority:
    def __init__(self):
        self.applied = []

    def mark_applied(self, identity, *, setup_id, name, fields, purpose,
                     applied_at="", source="applied_in_game"):
        self.applied.append((purpose, dict(fields)))
        return type("A", (), {"label": lambda _s: f"{name} · rev 1",
                              "is_active_on_car": True})()

    def active_setup(self, identity, purpose="Race"):
        if not self.applied:
            return None
        return type("A", (), {"label": lambda _s: "Setup 1 · rev 1",
                              "is_active_on_car": True})()


# --------------------------------------------------------------------------- #
# The wired stack + a staged runner that CONTINUES past a failing stage so one  #
# break does not mask later ones (the whole lifecycle is reported at once).     #
# --------------------------------------------------------------------------- #
@dataclass
class _StageResult:
    name: str
    ok: bool
    findings: list = field(default_factory=list)


class _Sim:
    def __init__(self, tmp: str) -> None:
        self.tmp = tmp
        self.results: list = []
        self.app = self.config = self.db = self.win = None
        self.controller = self.shell = self.bridge = None
        self.cfg_path = ""
        self.cycle_id = ""
        self.event_id = 0
        self._initial_domain = None

    def stage(self, name, fn):
        try:
            findings = fn(self) or []
            self.results.append(_StageResult(name, not findings, list(findings)))
        except Exception as exc:  # a raise is itself a failure finding
            import traceback
            self.results.append(_StageResult(
                name, False,
                [f"stage raised: {type(exc).__name__}: {exc}\n"
                 + traceback.format_exc()]))

    def report(self) -> str:
        lines = ["", "FULL EVENT SIMULATION — REPORT"]
        for r in self.results:
            lines.append(f"  [{'PASS' if r.ok else 'FAIL'}] {r.name}")
            for f in r.findings:
                lines.append(f"          - {f}")
        n_pass = sum(1 for r in self.results if r.ok)
        lines.append(f"  {n_pass}/{len(self.results)} stages clean")
        return "\n".join(lines)

    @property
    def all_clean(self) -> bool:
        return all(r.ok for r in self.results) and bool(self.results)


# ---- stages -------------------------------------------------------------- #
def _stage_construct(s: _Sim) -> list:
    from PyQt6.QtWidgets import QApplication
    import config_paths as cp
    s.app = QApplication.instance() or QApplication([])
    s.cfg_path = os.path.join(s.tmp, "config.json")
    cp.write_default_config(s.cfg_path)
    s.config = cp.load_config(s.cfg_path)
    from data.session_db import SessionDB
    s.db = SessionDB(os.path.join(s.tmp, "sim_sessions.db"))
    from ui.dashboard import MainWindow, SignalBridge
    s.win = MainWindow(config=s.config, logger=MagicMock(), announcer=MagicMock(),
                       bridge=SignalBridge(), ui_queue=queue.Queue(),
                       config_path=s.cfg_path, db=s.db)
    from ui.pit_crew_controller import PitCrewController
    from ui.pit_crew_shell import PitCrewShell
    from ui.live_shell_bridge import LiveShellBridge
    s.controller = PitCrewController()
    s.shell = PitCrewShell(s.controller)
    s.bridge = LiveShellBridge(s.shell, s.controller, window=s.win, config=s.config,
                               db=s.db, spawn=(lambda fn: fn()))
    s.bridge.refresh()
    return []


def _stage_track(s: _Sim) -> list:
    import data.track_station_map as tsm
    import data.track_model_alignment as tma
    from data.track_model_alignment import (
        export_accepted_model_json, TrackModelAlignmentResult,
        TrackModelMatchStatus, SectorAlignmentResult)
    models = pathlib.Path(s.tmp) / "track_models"
    models.mkdir(parents=True, exist_ok=True)
    tsm.STATION_MODELS_DIR = models
    tma.STATION_MODELS_DIR = models
    try:
        import data.track_refinement as tr
        tr.STATION_MODELS_DIR = models
    except Exception:
        pass
    result = TrackModelAlignmentResult(
        match_status=TrackModelMatchStatus.ACCEPTABLE_MATCH,
        seed_corners_expected=0, model_corners_found=0, extra_peaks_suppressed=0,
        placeholder_count=0, lap_length_m_model=0.0, lap_length_m_seed=0.0,
        lap_length_delta_pct=0.0, station_count=0, confidence=1.0,
        corner_alignments=[], sector_alignment=SectorAlignmentResult(0, "not_available", "sim"),
        blockers=[], warnings=[], accepted=True,
        accepted_at=datetime.datetime.now().isoformat(timespec="seconds"))
    path = export_accepted_model_json(result, LOC, LAY, output_dir=models)
    findings = []
    if not pathlib.Path(path).exists():
        findings.append(f"accepted_model.json not written to {path}")
    from data.track_readiness_disk import resolve_track_readiness_from_disk
    rr = resolve_track_readiness_from_disk(LOC, LAY)
    if not getattr(rr, "is_approved", False):
        findings.append(f"track NOT approved after writing accepted model "
                        f"(is_approved={getattr(rr, 'is_approved', None)})")
    return findings


def _stage_event(s: _Sim) -> list:
    from services.event_setup import EventDraft
    draft = EventDraft(name="Sim Round 1", car=CAR, track=TRACK,
                       race_type="lap", laps=25).with_rule("avail_tyres",
                                                           ["RH", "RM", "RS"])
    res = s.bridge._events.save_and_activate(draft)
    findings = []
    if not getattr(res, "ok", False):
        return [f"save_and_activate failed: {getattr(res, 'message', '')} "
                f"{getattr(res, 'issues', '')}"]
    s.cycle_id, s.event_id = res.cycle_id, res.event_id
    if s.config.get("active_cycle_id") != s.cycle_id:
        findings.append(f"config active_cycle_id={s.config.get('active_cycle_id')!r} "
                        f"!= {s.cycle_id!r}")
    s.bridge.refresh()
    st = s.controller.state()
    if (st.car or "").strip().lower() != CAR.lower():
        findings.append(f"WIRING: after activating event, controller car={st.car!r} "
                        f"not {CAR!r} (event switch didn't reach the shell)")
    cyc = s.db.get_preparation_cycle(s.cycle_id)
    if cyc is None:
        findings.append("get_preparation_cycle returned None after activation")
    elif (cyc.get("car") or "").lower() != CAR.lower() \
            or (cyc.get("track") or "").lower() != TRACK.lower():
        findings.append(f"cycle car/track mismatch: {cyc.get('car')!r}/{cyc.get('track')!r}")
    return findings


def _stage_programme_initial(s: _Sim) -> list:
    rep = s.db.build_event_preparation_report(s.cycle_id, now_date="2026-08-01")
    if not rep.get("ok"):
        return [f"preparation report not ok: {rep.get('error')}"]
    dom = (rep.get("next_action") or {}).get("domain")
    s._initial_domain = dom
    return [] if dom else ["no initial objective domain in next_action"]


def _record_run(s: _Sim, domain: str, n: int, laps: int = 5, *,
                car: str = None, track: str = None,
                cycle_id: str = None, event_id: int = None) -> int:
    """Record a completed run and bind it to its cycle activity. Overrides let a
    branch test drive an incompatible car/track or a different cycle."""
    from strategy.practice_run_recording import completed_activity_row, run_type_for_domain
    car = car or CAR
    track = track or TRACK
    cid = cycle_id or s.cycle_id
    eid = event_id if event_id is not None else s.event_id
    rt = run_type_for_domain(domain)
    aid = f"{cid}::{rt.value}::{n}"
    s.db.upsert_preparation_activity({
        "activity_id": aid, "cycle_id": cid, "activity_type": rt.value,
        "title": f"{rt.value} {n}", "objective": f"Build {domain} evidence",
        "state": "in_progress", "order_index": n})
    sid = s.db.open_session(car_id=1, track=track, session_type="Practice",
                            car_name=car, event_id=eid)
    for lap in range(1, laps + 1):
        s.db.write_lap(sid, lap, 95_000, 3.0, None, event_id=eid)
    s.db.bind_session_to_activity(aid, sid, cycle_id=cid)
    row = next((a for a in s.db.list_preparation_activities(cid)
                if a["activity_id"] == aid), None)
    if row is not None:
        s.db.upsert_preparation_activity(completed_activity_row(row))
    return sid


def _stage_runs_and_advance(s: _Sim) -> list:
    findings = []
    for i in range(1, 4):
        _record_run(s, "setup_base", i)
    s.bridge.refresh()
    rep = s.db.build_event_preparation_report(s.cycle_id, now_date="2026-08-01")
    prog = rep.get("progress") or {}
    if (prog.get("practice_sessions") or 0) < 3:
        findings.append(f"programme counted {prog.get('practice_sessions')} practice "
                        f"sessions, expected >=3 (runs not recognised as evidence)")
    readiness = {name: (level, note) for name, level, note in (rep.get("readiness") or [])}
    base = readiness.get("base_setup")
    if not base or base[0] in ("missing", None):
        findings.append(f"base_setup still {base} after 3 baseline runs (no evidence credit)")
    new_dom = (rep.get("next_action") or {}).get("domain")
    if new_dom == s._initial_domain and new_dom == "setup_base":
        findings.append("objective did NOT advance after covering setup_base "
                        "(programme frozen — the exact UAT symptom)")
    return findings


def _stage_setup(s: _Sim) -> list:
    findings = []
    s.bridge._setups._advisor = _StubAdvisor()
    s.bridge._setups._authority = _StubAuthority()
    s.bridge._discipline = "race"
    s.bridge._on_build_baseline()
    if s.bridge._setups.sheet("race").get("arb_front") != 6.0:
        findings.append("baseline did not author the race sheet")
    s.bridge._on_analyse()
    la = s.bridge._last_analysis
    if la is None or not getattr(la, "has_recommendation", False):
        return findings + ["analyse produced no recommendation"]
    s.bridge._on_applied_in_game("race")
    after = s.bridge._setups.sheet("race").get("arb_front")
    if after != 5.0:
        findings.append(f"'entered in GT7' did not apply the recommendation "
                        f"(arb_front={after}, expected 5.0)")
    if s.bridge._last_analysis is not None:
        findings.append("recommendation not consumed after 'entered in GT7'")
    s.bridge._on_lock_setup("race", True)
    locks = [str(x).lower() for x in (s.db.setup_locks(s.cycle_id) or ())]
    if "race" not in locks:
        findings.append(f"lock_setup('race') did not persist (setup_locks={locks})")
    return findings


def _stage_strategy(s: _Sim) -> list:
    findings = []
    s.bridge._on_build_plan()  # must not raise; reports a headline either way
    if getattr(s.shell, "strategy_page", None) is None:
        findings.append("shell has no strategy_page")
    plan = {"strategy": "2-stop", "total_laps": 25, "pit_stops": 2,
            "approved_at": "2026-08-10T10:00:00Z"}
    if not s.db.save_approved_strategy(s.cycle_id, plan):
        findings.append("save_approved_strategy returned False")
    got = s.db.get_approved_strategy(s.cycle_id) or {}
    saved = got.get("plan", got)
    if (saved or {}).get("total_laps") != 25:
        findings.append(f"approved strategy did not round-trip (get={got})")
    return findings


def _stage_live(s: _Sim) -> list:
    findings = []
    from strategy.adaptive_live_strategy import LiveStrategyState, StrategyObjective
    from strategy.live_audio_strategy_build import build_live_audio_strategy_view
    state = LiveStrategyState(
        objective=StrategyObjective.LAP_COUNT, current_lap=10, laps_remaining=15,
        fuel_remaining_l=40.0, fuel_per_lap_actual=2.9, fuel_per_lap_plan=2.6,
        lap_time_actual_s=95.2, lap_time_plan_s=94.5, pit_loss_s=22.0,
        tyre_age_laps=10, current_compound="RM", telemetry_fresh=True)
    view = build_live_audio_strategy_view(state, context_ok=True, rules_verified=True)
    if not view.get("ok"):
        return [f"live audio/strategy view not ok: {view}"]
    rec = (view.get("strategy_decision") or {}).get("recommendation")
    valid = {"PLAN_STILL_OPTIMAL", "CONSERVATION_REQUIRED", "PACE_INCREASE_AVAILABLE",
             "REPLAN_RECOMMENDED", "REPLAN_URGENT", "INSUFFICIENT_EVIDENCE",
             "CONTEXT_MISMATCH", "RULES_UNVERIFIED"}
    if rec not in valid:
        findings.append(f"live decision recommendation {rec!r} not a known state")
    try:
        s.bridge._feed_live()
    except Exception as exc:
        findings.append(f"bridge _feed_live raised: {exc}")
    return findings


def _stage_completion(s: _Sim) -> list:
    findings = []
    s.bridge._finish_active_event()  # non-modal underlying method
    cyc = s.db.get_preparation_cycle(s.cycle_id) or {}
    if (cyc.get("explicit_state") or "").lower() != "complete":
        findings.append(f"cycle not marked complete "
                        f"(explicit_state={cyc.get('explicit_state')!r})")
    if s.config.get("active_cycle_id"):
        findings.append(f"active_cycle_id not cleared after finish "
                        f"({s.config.get('active_cycle_id')!r})")
    try:
        s.bridge.refresh()
    except Exception as exc:
        findings.append(f"post-completion refresh raised: {exc}")
    return findings


def test_full_event_lifecycle():
    """Drive the whole race-prep lifecycle over the real wired stack; every seam
    must hold. On failure the per-stage report is the assertion message."""
    # ignore_cleanup_errors: on Windows the WAL sqlite file may still be held
    # open at teardown; the DB is closed below, but tolerate the race regardless.
    with tempfile.TemporaryDirectory(prefix="ngr_sim_",
                                     ignore_cleanup_errors=True) as tmp:
        s = _Sim(tmp)
        try:
            s.stage("0. construct + pump real wired stack", _stage_construct)
            s.stage("1. track mapping — approve model", _stage_track)
            s.stage("2. create + activate event (bridge service)", _stage_event)
            s.stage("3. initial programme objective", _stage_programme_initial)
            s.stage("4. runs -> evidence -> objective advances", _stage_runs_and_advance)
            s.stage("5. setup development (baseline/analyse/apply/lock)", _stage_setup)
            s.stage("6. race strategy (build + persistence)", _stage_strategy)
            s.stage("7. live race engineer (per-lap decision)", _stage_live)
            s.stage("8. event completion", _stage_completion)
            assert s.all_clean, s.report()
        finally:
            try:
                if s.bridge is not None:
                    s.bridge.stop()
            except Exception:
                pass
            try:
                if s.db is not None:
                    s.db.close()
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Widened coverage: the BRANCHES the happy path doesn't hit. These share one    #
# wired stack (built once) and each drives its own event, so a branch defect is #
# isolated to its own test. All are deterministic/offline.                      #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def wired():
    import shutil
    tmp = tempfile.mkdtemp(prefix="ngr_sim_mod_")
    s = _Sim(tmp)
    _stage_construct(s)
    yield s
    try:
        if s.bridge is not None:
            s.bridge.stop()
    except Exception:
        pass
    try:
        if s.db is not None:
            s.db.close()
    except Exception:
        pass
    shutil.rmtree(tmp, ignore_errors=True)


def _activate(s: _Sim, name, *, car=CAR, track=TRACK, race_type="lap",
              laps=25, mins=60, tyres=("RH", "RM", "RS")):
    from services.event_setup import EventDraft
    d = EventDraft(name=name, car=car, track=track, race_type=race_type,
                   laps=laps, duration_mins=mins).with_rule("avail_tyres", list(tyres))
    res = s.bridge._events.save_and_activate(d)
    assert res.ok, (getattr(res, "message", ""), getattr(res, "issues", ""))
    s.cycle_id, s.event_id = res.cycle_id, res.event_id
    return res


def test_incompatible_run_is_excluded_from_evidence(wired):
    """A run driven in a DIFFERENT car must not count as evidence for this event —
    the compatibility gate (the intent behind the event-id/car-track binding)."""
    _activate(wired, "Branch — Wrong Car")
    good = _record_run(wired, "setup_base", 1)                    # this event's car
    bad = _record_run(wired, "setup_base", 2, car="Mazda MX-5")  # wrong car
    wired.bridge.refresh()
    rep = wired.db.build_event_preparation_report(wired.cycle_id, now_date="2026-08-01")
    membership = {str(x) for x in (rep.get("evidence_membership") or [])}
    assert str(good) in membership, "compatible run should be evidence"
    assert str(bad) not in membership, "wrong-car run must NOT count as evidence"


def test_unfinished_run_with_no_completed_laps_is_not_evidence(wired):
    """Opening a session but completing no laps (total_laps == 0) is not a run —
    it must contribute no evidence."""
    _activate(wired, "Branch — Zero Laps")
    from strategy.practice_run_recording import run_type_for_domain
    rt = run_type_for_domain("setup_base")
    aid = f"{wired.cycle_id}::{rt.value}::zero"
    wired.db.upsert_preparation_activity({
        "activity_id": aid, "cycle_id": wired.cycle_id, "activity_type": rt.value,
        "title": "empty", "objective": "Build setup_base evidence",
        "state": "in_progress", "order_index": 1})
    sid = wired.db.open_session(car_id=1, track=TRACK, session_type="Practice",
                                car_name=CAR, event_id=wired.event_id)  # no write_lap
    wired.db.bind_session_to_activity(aid, sid, cycle_id=wired.cycle_id)
    rep = wired.db.build_event_preparation_report(wired.cycle_id, now_date="2026-08-01")
    assert (rep.get("progress") or {}).get("practice_sessions", 0) == 0
    membership = {str(x) for x in (rep.get("evidence_membership") or [])}
    assert str(sid) not in membership


def test_multi_discipline_locks_are_independent(wired):
    """Locking Race must not clear Qualifying, and reopening one must leave the
    other locked (the per-discipline merge in lock_setup)."""
    _activate(wired, "Branch — Locks")
    assert wired.db.lock_setup(wired.cycle_id, "race", locked=True)
    assert wired.db.lock_setup(wired.cycle_id, "qualifying", locked=True)
    locks = {str(x).lower() for x in (wired.db.setup_locks(wired.cycle_id) or ())}
    assert {"race", "qualifying"} <= locks, f"both should be locked, got {locks}"
    # Reopen Race; Qualifying must survive.
    assert wired.db.lock_setup(wired.cycle_id, "race", locked=False)
    locks = {str(x).lower() for x in (wired.db.setup_locks(wired.cycle_id) or ())}
    assert "qualifying" in locks and "race" not in locks, locks


def test_timed_race_event_activates_with_duration(wired):
    """A time-certain race (not lap-count) must validate, activate, and carry its
    duration into the strategy context the rest of the app reads."""
    res = _activate(wired, "Branch — Timed", race_type="timed", laps=0, mins=45)
    assert res.cycle_id
    assert wired.db.get_preparation_cycle(res.cycle_id) is not None
    strat = wired.config.get("strategy") or {}
    assert float(strat.get("race_duration_minutes") or 0) == 45.0, strat


def test_wet_compounds_are_accepted_in_event_setup(wired):
    """Event setup must accept wet compounds (Intermediate / Heavy-Wet), not only
    slicks — a rain event has to be preparable."""
    res = _activate(wired, "Branch — Wet", tyres=("IM", "HW", "RH"))
    assert res.ok
    evt = wired.db.get_event("Branch — Wet") or {}
    avail = [str(t).upper() for t in (evt.get("avail_tyres") or [])]
    assert "IM" in avail and "HW" in avail, f"wet compounds not persisted: {evt.get('avail_tyres')}"
