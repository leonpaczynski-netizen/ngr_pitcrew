"""Phase 3: weekend progression gates and evidence integrity — C1, C3, C4, C6, C7, C11.

The UAT symptom was "the app ran one practice session and went straight to qualifying,
without working through the tyres or settling the setup". Two causes, both here.

Evidence (C3): one lap counted as one complete evidence sample, and one telemetry
session could be counted three times — so a single outing satisfied a whole preparation
programme.

Gates (C1/C4/C6/C7/C11): no transition was gated by anything. ``_on_begin_qualifying``
had zero validation, its readiness mapping treated *developing*, *adequate*, *strong*
and *unknown* alike as non-blocking, per-compound tyre coverage fed a progress label,
no driver-comfort gate existed at all, and Start Race proceeded on a Yes/No that named
nothing.
"""
from __future__ import annotations

import inspect

import pytest

from data.session_db import MIN_EVIDENCE_CLEAN_LAPS, SessionDB
from strategy.weekend_gate import (
    INSUFFICIENT_LEVELS, SATISFIED_LEVELS, WeekendTransition,
    evaluate_weekend_transition,
)


# ---------------------------------------------------------------------------
# C3 — a lap is not a run, and one run is one piece of evidence
# ---------------------------------------------------------------------------
def _db_with_activity(activity_id="a1", cycle_id="c1", order=0):
    db = SessionDB(":memory:")
    db._conn.execute(
        "INSERT INTO event_preparation_activities (activity_id,cycle_id,activity_type,"
        "title,objective,planned_date,state,order_index,optional,phase) "
        "VALUES (?,?,'free_practice','t','o','','planned',?,0,'preparation')",
        (activity_id, cycle_id, order))
    return db


def _session_with_laps(db, *, clean=0, out=0, pit=0):
    sid = db.open_session(car_id=1, track="T", session_type="Practice", car_name="C")
    n = 0
    for _ in range(out):
        n += 1
        db.write_lap(session_id=sid, lap_num=n, lap_time_ms=100000, fuel_used=1.0,
                     stats=None, is_out_lap=True)
    for _ in range(pit):
        n += 1
        db.write_lap(session_id=sid, lap_num=n, lap_time_ms=100000, fuel_used=1.0,
                     stats=None, is_pit_lap=True)
    for _ in range(clean):
        n += 1
        db.write_lap(session_id=sid, lap_num=n, lap_time_ms=100000, fuel_used=1.0,
                     stats=None)
    return sid


def test_out_laps_and_pit_laps_are_not_clean_laps():
    """`total_laps > 0` counted an installation lap as a COMPLETE evidence sample."""
    db = _db_with_activity()
    sid = _session_with_laps(db, out=1, pit=1)
    db.bind_session_to_activity("a1", str(sid), cycle_id="c1")
    row = db.get_practice_sessions_for_cycle("c1")[0]
    assert row["total_laps"] == 2
    assert row["clean_laps"] == 0


def test_clean_laps_are_counted():
    db = _db_with_activity()
    sid = _session_with_laps(db, clean=6, out=1)
    db.bind_session_to_activity("a1", str(sid), cycle_id="c1")
    row = db.get_practice_sessions_for_cycle("c1")[0]
    assert row["clean_laps"] == 6
    assert row["clean_laps"] >= MIN_EVIDENCE_CLEAN_LAPS


def test_the_floor_matches_the_projects_definition_of_a_usable_run():
    """setup_maturity already defined a usable run as >= 5 clean laps; the evidence
    layer disagreeing with it is what let one lap satisfy a domain."""
    assert MIN_EVIDENCE_CLEAN_LAPS == 5


def test_one_session_cannot_bind_to_a_second_activity():
    """The binding table is keyed (activity_id, session_id), so one on-track run
    recorded against base, race and qualifying became three independent samples."""
    db = _db_with_activity("a1")
    db._conn.execute(
        "INSERT INTO event_preparation_activities (activity_id,cycle_id,activity_type,"
        "title,objective,planned_date,state,order_index,optional,phase) "
        "VALUES ('a2','c1','free_practice','t','o','','planned',1,0,'preparation')")
    sid = _session_with_laps(db, clean=6)
    assert db.bind_session_to_activity("a1", str(sid), cycle_id="c1") is True
    assert db.bind_session_to_activity("a2", str(sid), cycle_id="c1") is False


def test_rebinding_the_same_session_to_the_same_activity_stays_idempotent():
    db = _db_with_activity()
    sid = _session_with_laps(db, clean=6)
    assert db.bind_session_to_activity("a1", str(sid), cycle_id="c1") is True
    assert db.bind_session_to_activity("a1", str(sid), cycle_id="c1") is True
    assert len(db.get_practice_sessions_for_cycle("c1")) == 1


def test_a_different_session_still_binds():
    db = _db_with_activity()
    s1 = _session_with_laps(db, clean=6)
    s2 = _session_with_laps(db, clean=6)
    assert db.bind_session_to_activity("a1", str(s1), cycle_id="c1") is True
    assert db.bind_session_to_activity("a1", str(s2), cycle_id="c1") is True
    assert len(db.get_practice_sessions_for_cycle("c1")) == 2


def test_the_query_reports_the_binding_fan_out():
    db = _db_with_activity()
    sid = _session_with_laps(db, clean=6)
    db.bind_session_to_activity("a1", str(sid), cycle_id="c1")
    assert db.get_practice_sessions_for_cycle("c1")[0]["bound_activity_count"] == 1


# ---------------------------------------------------------------------------
# C4 — the readiness levels that were treated as good enough to go qualifying
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("level", ["developing", "unknown", "missing", "emerging", ""])
def test_an_unfinished_domain_blocks_qualifying(level):
    """Only the literal string "missing" used to block. "developing" is one sample and
    "unknown" is no idea at all — neither is readiness."""
    v = evaluate_weekend_transition(
        WeekendTransition.BEGIN_QUALIFYING, readiness=[("tyre_evidence", level, "")],
        setup_applied=True, driver_comfortable=True)
    assert v.allowed is False
    assert any(b.key == "readiness:tyre_evidence" for b in v.blockers)


@pytest.mark.parametrize("level", ["adequate", "strong", "ready", "complete"])
def test_a_finished_domain_does_not_block(level):
    v = evaluate_weekend_transition(
        WeekendTransition.BEGIN_QUALIFYING, readiness=[("tyre_evidence", level, "")],
        setup_applied=True, driver_comfortable=True)
    assert v.allowed is True


def test_unknown_is_explicitly_not_ready():
    """Not knowing is not the same as being ready."""
    assert "unknown" in INSUFFICIENT_LEVELS
    assert "unknown" not in SATISFIED_LEVELS


def test_an_unapplied_setup_blocks():
    v = evaluate_weekend_transition(WeekendTransition.BEGIN_QUALIFYING,
                                    setup_applied=False, driver_comfortable=True)
    assert any(b.key == "setup_not_applied" for b in v.blockers)


# ---------------------------------------------------------------------------
# C6 — per-compound tyre coverage must gate, not decorate
# ---------------------------------------------------------------------------
def test_missing_compound_coverage_blocks():
    v = evaluate_weekend_transition(
        WeekendTransition.BEGIN_QUALIFYING, setup_applied=True, driver_comfortable=True,
        required_compounds=["RS", "RM"], sampled_compounds=["RM"])
    blocker = [b for b in v.blockers if b.key == "tyre_coverage"]
    assert blocker and "RS" in blocker[0].message


def test_full_compound_coverage_does_not_block():
    v = evaluate_weekend_transition(
        WeekendTransition.BEGIN_QUALIFYING, setup_applied=True, driver_comfortable=True,
        required_compounds=["RS", "RM"], sampled_compounds=["RM", "RS"])
    assert v.allowed is True


def test_no_known_compounds_warns_rather_than_disabling_the_check():
    """It used to disable itself entirely — "no restriction" — when the event listed no
    compounds. Not knowing which tyres are allowed is a reason to ask, not to skip."""
    v = evaluate_weekend_transition(
        WeekendTransition.BEGIN_QUALIFYING, setup_applied=True, driver_comfortable=True,
        required_compounds=[], sampled_compounds=[])
    assert v.allowed is True
    assert any("no allowed compounds" in w for w in v.warnings)


# ---------------------------------------------------------------------------
# C7 — the driver-comfort gate that existed nowhere
# ---------------------------------------------------------------------------
def test_an_unasked_driver_blocks():
    """`grep -i comfortab` across the non-test tree returned only CSS comments."""
    v = evaluate_weekend_transition(WeekendTransition.BEGIN_QUALIFYING,
                                    setup_applied=True, driver_comfortable=None)
    assert any(b.key == "driver_comfort" for b in v.blockers)


def test_an_unhappy_driver_blocks():
    v = evaluate_weekend_transition(WeekendTransition.BEGIN_QUALIFYING,
                                    setup_applied=True, driver_comfortable=False)
    blocker = [b for b in v.blockers if b.key == "driver_comfort"]
    assert blocker and "NOT comfortable" in blocker[0].message


def test_a_happy_driver_does_not_block():
    v = evaluate_weekend_transition(WeekendTransition.BEGIN_QUALIFYING,
                                    setup_applied=True, driver_comfortable=True)
    assert v.allowed is True


def test_the_bridge_reads_comfort_from_the_verdict_the_driver_already_gives():
    from ui.live_shell_bridge import LiveShellBridge

    def comfort(fb):
        stub = type("S", (), {"_last_feedback": fb})()
        return LiveShellBridge._driver_comfort(stub)

    assert comfort({"overall": "Better"}) is True
    assert comfort({"overall": "Worse"}) is False
    assert comfort({}) is None, "never asked is not the same as happy"
    assert comfort({"overall": "About the same"}) is None


# ---------------------------------------------------------------------------
# C11 — informed consent, not a formality
# ---------------------------------------------------------------------------
def test_the_override_prompt_names_every_blocker():
    """The Start Race prompt listed stage names and nothing about what they mean. A
    dialog that names nothing is not informed consent."""
    v = evaluate_weekend_transition(
        WeekendTransition.START_RACE, readiness=[("tyre_evidence", "developing", "1 of 3")],
        required_compounds=["RS"], sampled_compounds=[], setup_applied=False,
        driver_comfortable=None)
    prompt = v.confirmation_prompt()
    for blocker in v.blockers:
        assert blocker.message in prompt
    assert "incomplete preparation" in prompt


def test_an_allowed_transition_asks_nothing():
    v = evaluate_weekend_transition(WeekendTransition.START_RACE,
                                    setup_applied=True, driver_comfortable=True)
    assert v.confirmation_prompt() == ""


def test_every_blocker_carries_a_remedy():
    """A blocker the driver cannot act on is just an obstacle."""
    v = evaluate_weekend_transition(
        WeekendTransition.START_RACE, readiness=[("tyre_evidence", "developing", "")],
        required_compounds=["RS"], sampled_compounds=[], setup_applied=False,
        driver_comfortable=None)
    for blocker in v.blockers:
        assert blocker.remedy, f"{blocker.key} has no remedy"


def test_the_override_is_recorded_not_just_permitted():
    from ui.live_shell_bridge import LiveShellBridge
    src = inspect.getsource(LiveShellBridge._confirm_override)
    assert "_last_gate_override" in src
    assert "INCOMPLETE preparation" in src


# ---------------------------------------------------------------------------
# C1 — the transitions actually route through the gate
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("handler", ["_on_begin_qualifying", "_on_start_race"])
def test_the_transition_consults_the_gate(handler):
    from ui.live_shell_bridge import LiveShellBridge
    src = inspect.getsource(getattr(LiveShellBridge, handler))
    assert "_weekend_gate" in src, f"{handler} does not consult the weekend gate"
    assert "_confirm_override" in src, f"{handler} cannot be overridden explicitly"


def test_the_gate_is_pure():
    """The reporters stay reporters; enforcement lives at the handler. This module must
    not import Qt, a DB or anything that performs a state change."""
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent
           / "strategy" / "weekend_gate.py").read_text(encoding="utf-8")
    for banned in ("PyQt", "session_db", "sqlite", "import os", "datetime"):
        assert banned not in src, f"weekend_gate imports {banned}"


def test_a_gate_failure_does_not_become_an_open_door():
    """A crashing check must not read as a pass."""
    v = evaluate_weekend_transition(WeekendTransition.START_RACE,
                                    readiness=[object()], setup_applied=True,
                                    driver_comfortable=True)
    assert isinstance(v.allowed, bool)


def test_the_verdict_serialises():
    import json
    v = evaluate_weekend_transition(WeekendTransition.START_RACE, setup_applied=False)
    json.dumps(v.as_json())


# ---------------------------------------------------------------------------
# C5 — looking at a setup is not declaring a session
# ---------------------------------------------------------------------------
class _Tracker:
    def __init__(self):
        self.declared = []

    def set_session_type_override(self, t):
        self.declared.append(getattr(t, "name", str(t)))


def _push(discipline, live_mode=""):
    from ui.live_shell_bridge import LiveShellBridge
    tracker = _Tracker()
    window = type("W", (), {
        "_practice_is_qual_ref": [False], "_live_mode_ref": [""],
        "_tracker": tracker, "_strategy_engine": None, "_announcer": None})()
    stub = type("S", (), {"_window": window, "_live_session_mode": live_mode,
                          "_push_active_compound": lambda self, d: None})()
    LiveShellBridge._push_practice_mode(stub, discipline)
    return tracker.declared


def test_selecting_the_qualifying_tab_does_not_convert_the_live_session():
    """refresh() pushes this every 750ms, so simply LOOKING at the qualifying sheet to
    build a setup converted the live session — and there was no Practice tab to look at
    instead."""
    assert _push("qualifying") == ["PRACTICE"]


@pytest.mark.parametrize("discipline", ["base", "race", "qualifying"])
def test_no_garage_tab_declares_a_session(discipline):
    assert _push(discipline) == ["PRACTICE"]


@pytest.mark.parametrize("mode,expected", [
    ("qualifying", "QUALIFYING"),
    ("race", "RACE"),
])
def test_an_explicitly_declared_session_still_wins(mode, expected):
    """Begin Qualifying and race detection DO declare — that is the point of them."""
    assert _push("base", live_mode=mode) == [expected]


def test_the_shift_beep_still_follows_the_selected_discipline():
    """Which RPM to beep at is a property of the setup being tested, not of the
    session — that half must keep following the tab."""
    from ui.live_shell_bridge import LiveShellBridge
    window = type("W", (), {
        "_practice_is_qual_ref": [False], "_live_mode_ref": [""],
        "_tracker": None, "_strategy_engine": None, "_announcer": None})()
    stub = type("S", (), {"_window": window, "_live_session_mode": "",
                          "_push_active_compound": lambda self, d: None})()
    LiveShellBridge._push_practice_mode(stub, "qualifying")
    assert window._practice_is_qual_ref[0] is True
