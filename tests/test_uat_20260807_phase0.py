"""Regression cover for the Phase 0 fixes from the hardware UAT of 6 August 2026.

Each test names the defect it locks down. The register these IDs come from is
``02-uat-defect-register-2026-08-07`` — four reported symptoms (setups wrong,
feedback ignored, practice→qualifying skipped, pit stop not recorded) traced to a
common cause: a rich engineering layer largely unwired from the shell the driver
actually uses.

Phase 0 is the "stop the bleeding" tranche only. The larger remediation (car data
model, provenance tiers, one weekend state machine, pit lane as a first-class
modelling step) is Phases 1-4 and is NOT covered here.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


# --------------------------------------------------------------------------- E1

def test_main_imports_os_so_the_stray_window_guard_can_install():
    """E1 — main.py used os.path without importing os.

    The NameError was swallowed by the guard's own ``except Exception``, printing
    "[StrayWindowGuard] not installed" and leaving the mitigation for the
    focus-stealing flashing box permanently disabled on the rig.
    """
    # Parsed rather than imported: main.py pulls in the whole telemetry/voice stack,
    # and the question here is purely "is the name bound at module level".
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "main.py").read_text(encoding="utf-8"))
    imported = {
        alias.asname or alias.name.split(".")[0]
        for node in tree.body if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "os" in imported, "main.py uses os.path in the stray-window guard"


# --------------------------------------------------------------------------- B4/B5

def test_feedback_key_aliases_rescue_every_capture_surface():
    """B5 — the classic form's label mangling produced keys nothing read.

    ``"Mid-Corner"`` became ``mid-corner`` (the hyphen is not replaced) and
    ``"Rear Under Braking"`` became ``rear_under_braking``; the writer looked for
    ``mid_corner`` and ``rear_braking``, so both fields persisted as empty string on
    every single submission.
    """
    from data.session_db import normalise_feedback

    out = normalise_feedback({
        "mid-corner": "Understeer",
        "rear_under_braking": "Unstable",
        "overall": "worse",
        "fuel_behaviour": "As expected",
        "confidence": "Good",
        "corners": "Turn 6",
    })
    assert out["mid_corner"] == "Understeer"
    assert out["rear_braking"] == "Unstable"
    assert out["vs_previous"] == "worse"
    assert out["fuel_use"] == "As expected"
    assert out["overall_confidence"] == "Good"
    assert out["corner"] == "Turn 6"


def test_normalise_feedback_leaves_unknown_keys_alone():
    from data.session_db import normalise_feedback

    out = normalise_feedback({"traction": "Poor", "something_new": "x"})
    assert out == {"traction": "Poor", "something_new": "x"}


def test_driver_feedback_table_stores_the_whole_practice_review_form(tmp_path):
    """B4 — 9 of the 14 captured fields had no column and were dropped on write."""
    from data.session_db import SessionDB
    from ui.components.practice_feedback import FEEDBACK_FIELDS

    db = SessionDB(str(tmp_path / "s.db"))
    submitted = {
        "overall": "worse",
        "corner_entry": "Understeer",
        "mid_corner": "Strong understeer",
        "exit_stability": "Oversteer",
        "braking_confidence": "Below par",
        "traction": "Poor",
        "rotation": "OK",
        "drive_out": "Good",
        "straight_line": "Excellent",
        "kerb_behaviour": "Noticeable",
        "bottoming": "Minor",
        "gear_choice": "Too long",
        "fuel_behaviour": "Worse than expected",
        "tyre_condition": "As expected",
        "confidence": "Below par",
        "corners": "Turn 6 (Esses)",
        "notes": "front pushes on entry",
    }
    # The form's own field list is the contract — if a field is added there and not
    # persisted, this test fails rather than the data quietly disappearing.
    assert set(k for k, _lbl, _opts in FEEDBACK_FIELDS) <= set(submitted)

    db.write_feedback(session_id=1, lap_num=7, feedback=submitted)
    row = db._conn.execute(
        "SELECT * FROM driver_feedback ORDER BY id DESC LIMIT 1").fetchone()
    stored = dict(row)

    assert stored["vs_previous"] == "worse"
    assert stored["mid_corner"] == "Strong understeer"
    assert stored["braking_confidence"] == "Below par"
    assert stored["traction"] == "Poor"
    assert stored["rotation"] == "OK"
    assert stored["drive_out"] == "Good"
    assert stored["straight_line"] == "Excellent"
    assert stored["kerb_behaviour"] == "Noticeable"
    assert stored["bottoming"] == "Minor"
    assert stored["gear_choice"] == "Too long"
    assert stored["fuel_use"] == "Worse than expected"
    assert stored["overall_confidence"] == "Below par"
    assert stored["corner"] == "Turn 6 (Esses)"
    assert stored["notes"] == "front pushes on entry"


def test_feedback_write_survives_a_classic_form_submission(tmp_path):
    """The classic dashboard's mangled keys must land in the same columns."""
    from data.session_db import SessionDB

    db = SessionDB(str(tmp_path / "s.db"))
    db.write_feedback(session_id=2, lap_num=3, feedback={
        "corner_entry": "Neutral", "mid-corner": "Understeer",
        "rear_under_braking": "Locking", "notes": "",
    }, rating="hated")
    row = dict(db._conn.execute(
        "SELECT * FROM driver_feedback ORDER BY id DESC LIMIT 1").fetchone())
    assert row["mid_corner"] == "Understeer"
    assert row["rear_braking"] == "Locking"
    assert row["rating"] == "hated"


# --------------------------------------------------------------------------- A2

def test_track_seed_is_not_a_measured_model():
    """A2 — ``trustworthy`` was doing duty for ``measured``.

    A seed carries a hand-entered lap length and an EXPECTED corner count. That is
    enough to nudge aero; it is not evidence about this layout, and it must not
    authorise synthesis-primary to replace physics-derived values with a walk from
    the midpoint of the generic legal range.
    """
    from strategy.track_tune_profile import build_track_tune_profile

    seed = SimpleNamespace(length_m=5793.0, corners_expected=16,
                           longest_straight_m=1400.0, elevation_change_m=40.0)
    seeded = build_track_tune_profile("monza", "full", seed_layout=seed)
    assert seeded.trustworthy is True
    assert seeded.measured is False

    accepted = SimpleNamespace(lap_length_m_model=5790.0, model_corners_found=11)
    modelled = build_track_tune_profile("monza", "full", seed_layout=seed,
                                        accepted_model=accepted)
    assert modelled.trustworthy is True
    assert modelled.measured is True


def test_setup_shaping_confidence_requires_a_measured_model():
    from strategy.setup_engineering_context import track_confidence_by_capability

    seed_only = track_confidence_by_capability(
        SimpleNamespace(trustworthy=True, measured=False), None)
    modelled = track_confidence_by_capability(
        SimpleNamespace(trustworthy=True, measured=True), None)
    assert seed_only["setup_shaping"] == "low"
    assert modelled["setup_shaping"] == "high"


# --------------------------------------------------------------------------- A4

def _ranges():
    from strategy.setup_ranges import resolve_ranges
    return resolve_ranges("Porsche 911 RSR (991) '17")


def test_no_gear_count_authors_no_gearbox_at_all():
    """A4 — a final drive was authored with zero gear ratios attached.

    ``num_gears`` is read from data/car_specs.json, which carries that key for NO
    car, so the default runtime path always arrived with 0 and still shipped
    ``final_drive`` = the midpoint of a GLOBAL constant range. That silently
    mismatches the car's stock gearing in the one direction a driver cannot
    diagnose by reading the sheet.
    """
    from strategy.setup_baseline import _build_gearbox_changes

    assert _build_gearbox_changes(_ranges(), 0, set()) == []


def test_a_proven_final_drive_is_still_honoured_without_a_gear_count():
    from strategy.setup_baseline import _build_gearbox_changes

    changes = _build_gearbox_changes(_ranges(), 0, set(),
                                     proven_gearbox={"final_drive": 3.9})
    assert [c["field"] for c in changes] == ["final_drive"]


def test_a_known_gear_count_still_authors_the_gearbox():
    from strategy.setup_baseline import _build_gearbox_changes

    fields = [c["field"] for c in _build_gearbox_changes(_ranges(), 6, set())]
    assert "final_drive" in fields
    assert fields.count("gear_1") == 1 and "gear_6" in fields


# --------------------------------------------------------------------------- A8

def test_a_low_confidence_baseline_is_not_reported_as_plainly_approved():
    """A8 — ``confidence.overall == "low"`` was laundered into status "approved".

    The two structural warnings a full-field baseline always raises are filtered out
    as artifacts, so a 30-field, never-validated setup reached the UI with zero
    warnings — which renders no banner at all and enables Apply.
    """
    from strategy.driving_advisor import DrivingAdvisor
    from strategy.setup_ranges import resolve_ranges

    rec = SimpleNamespace(recent_laps=lambda n: [], last_lap=lambda: None,
                          best_lap=lambda: None)
    advisor = DrivingAdvisor(rec, SimpleNamespace(), {})
    car = "Porsche 911 RSR (991) '17"
    resp = json.loads(advisor.build_baseline_setup_response(
        car, resolve_ranges(car), "RR", 6, None, False,
        session_type="Race", duration_mins=45.0, track_name="Fuji",
        layout_id="full", track_profile=None, historical_setups=None))

    assert str(resp.get("confidence", {}).get("overall")) == "low"
    assert resp["recommendation_status"] == "approved_with_warnings"
    assert any("low-confidence baseline" in w.lower()
               for w in resp.get("validation_warnings") or [])


# --------------------------------------------------------------------------- D2

def test_pit_lane_mapping_baseline_is_read_after_the_session_restarts():
    """D2 — the lap baseline was captured from the session about to be discarded.

    ``_begin_pit_lane_mapping`` read the controller's lap count BEFORE
    ``start_session()`` allocated a fresh CalibrationSession with ``laps = []``. The
    gate in ``_try_map_pit_lane`` is ``len(laps) <= baseline``, so a baseline of 5-7
    (the just-completed modelling session) meant the driver had to drive that many
    MORE laps before one mapping attempt was made — and the pit lap they had just
    driven went with the discarded session. This is the "I boxed and it still told
    me to drive the pit lane" symptom.
    """
    from ui.live_shell_bridge import LiveShellBridge

    class _Controller:
        def __init__(self):
            self._session = SimpleNamespace(laps=[object()] * 6)

        def start_session(self, location_id, layout_id):
            self._session = SimpleNamespace(laps=[])
            return True

    class _Tracks:
        def __init__(self):
            self._controller = _Controller()
            self.session = SimpleNamespace(location_id="monza", layout_id="full")

    bridge = LiveShellBridge.__new__(LiveShellBridge)
    bridge._tracks = _Tracks()
    bridge._pit_lane_mode = False
    bridge._pit_lane_baseline_laps = 0
    bridge._tm_status = ""

    LiveShellBridge._begin_pit_lane_mapping(bridge)

    assert bridge._pit_lane_mode is True
    assert bridge._pit_lane_baseline_laps == 0, (
        "the baseline must reflect the NEW capture session, so the very next "
        "completed lap is offered to the pit-lane detector")


# --------------------------------------------------------------------------- D3

def test_map_pit_lane_falls_back_to_the_station_map_on_disk(monkeypatch):
    """D3 — pit-lane mapping was impossible for an already-approved track.

    ``select_track`` clears the artefact dict and ``refresh_disk_readiness`` only
    restores ``model_active``, so after any restart the in-memory station map is
    gone and mapping refused with "Approve the track model before mapping the pit
    lane" — a message the driver cannot act on, because the model IS approved. The
    map renderer already fell back to disk; the mapper now does too.
    """
    import services.track_modelling as tm

    class _Session:
        location_id = "monza"
        layout_id = "full"
        model_active = True

        def artefact(self, _name):
            return None

        def with_artefact(self, _name, _value):
            return self

    service = tm.TrackModellingService.__new__(tm.TrackModellingService)
    service._session = _Session()

    disk_map = SimpleNamespace(pit_lane=None)
    monkeypatch.setattr(service, "_load_station_map_from_disk", lambda: disk_map)
    monkeypatch.setattr(
        "data.track_station_map.detect_pit_lane_from_pit_laps",
        lambda laps, station_map: SimpleNamespace(entry_station=10, exit_station=40))
    monkeypatch.setattr(
        "data.track_station_map.export_station_map_json", lambda sm, **kw: None)

    result = service.map_pit_lane([SimpleNamespace(samples=[object()])])
    assert result.ok is True
    assert "pit lane mapped" in result.reason.lower()


def test_map_pit_lane_still_refuses_when_nothing_is_on_disk(monkeypatch):
    import services.track_modelling as tm

    class _Session:
        location_id = ""
        layout_id = ""

        def artefact(self, _name):
            return None

    service = tm.TrackModellingService.__new__(tm.TrackModellingService)
    service._session = _Session()
    monkeypatch.setattr(service, "_load_station_map_from_disk", lambda: None)

    result = service.map_pit_lane([])
    assert result.ok is False
    assert "approve the track model" in result.reason.lower()
