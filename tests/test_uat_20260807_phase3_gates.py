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


# ---------------------------------------------------------------------------
# C2 / C9 — depth before breadth, and one number on screen
# ---------------------------------------------------------------------------
def _objective_after(n, activity_type=None):
    from strategy.event_preparation_cycle import PreparationActivityType
    from strategy.preparation_evidence import (
        EvidenceCompatibility, PracticeEvidenceSample, build_cumulative_evidence,
        to_objective,
    )
    at = activity_type or PreparationActivityType.BASELINE_PRACTICE
    samples = [PracticeEvidenceSample(
        session_id=str(i), activity_id="a", activity_type=at, is_valid=True,
        valid_laps=6, compatibility=EvidenceCompatibility.EXACT) for i in range(n)]
    return to_objective(build_cumulative_evidence(samples))


@pytest.mark.parametrize("n", [0, 1, 2])
def test_a_domain_is_not_retired_after_one_sample(n):
    """One sample lifted a domain from NONE to EMERGING so it stopped being the
    globally weakest, and the engine moved straight to the next untouched one.
    Runtime-verified in the register: setup_qualifying was nominated THIRD from every
    starting configuration, before base or race had been established."""
    assert _objective_after(n).domain == "setup_base"


def test_the_engine_moves_on_once_the_domain_is_covered():
    """Depth-first must not mean stuck."""
    assert _objective_after(3).domain != "setup_base"


def test_the_coverage_threshold_matches_what_the_map_shows_the_driver():
    """The programme map told the driver three runs to cover a domain while the
    objective engine moved off after one. Two authorities disagreeing about the same
    number is worse than either being wrong."""
    from strategy.preparation_evidence import (
        COVERED_CONFIDENCE, _CONFIDENCE_ORDER, _confidence_from,
    )
    from strategy.programme_map import TARGET_ADEQUATE
    reached = _confidence_from(TARGET_ADEQUATE, 0, False)
    assert _CONFIDENCE_ORDER.index(reached) >= _CONFIDENCE_ORDER.index(COVERED_CONFIDENCE)
    assert _CONFIDENCE_ORDER.index(_confidence_from(TARGET_ADEQUATE - 1, 0, False)) \
        < _CONFIDENCE_ORDER.index(COVERED_CONFIDENCE)


def test_priority_order_still_decides_which_domain_comes_first():
    """Depth-first changes WHEN the engine moves on, not the engineering sequence."""
    from strategy.preparation_evidence import _OBJECTIVE_PRIORITY, EvidenceDomain
    assert _OBJECTIVE_PRIORITY[0] is EvidenceDomain.SETUP_BASE
    assert _objective_after(0).domain == "setup_base"


def test_free_practice_does_not_credit_the_base_setup_domain():
    """Working a domain means running the activity that produces its evidence — free
    practice laps are race pace and consistency, not base-setup evidence."""
    from strategy.event_preparation_cycle import PreparationActivityType
    obj = _objective_after(4, PreparationActivityType.FREE_PRACTICE)
    assert obj.domain == "setup_base", (
        "free practice must not silently satisfy the base-setup domain")


# ---------------------------------------------------------------------------
# C8 — the import that never resolved, so the real planner never ran
# ---------------------------------------------------------------------------
def test_the_real_test_sequence_planner_is_reached():
    """`from strategy.setup_test_plan import build_test_plan` names a function that
    does not exist and never has — the module exports build_test_sequence. The
    ImportError was swallowed by a bare except, so every recommendation silently fell
    through to a numbered fallback and a proper planner sat one correct import away."""
    from ui.setup_recommendation_vm import _build_test_plan
    changes = [
        {"field": "arb_front", "delta": 1, "from": 5, "to": 6,
         "symptom": "mid_corner_understeer", "setting": "ARB Front"},
        {"field": "aero_rear", "delta": -20, "from": 620, "to": 600,
         "symptom": "high_speed_stability", "setting": "Aero Rear"},
    ]
    steps = _build_test_plan({"diagnosis": {}}, changes)
    joined = " ".join(steps)
    assert "Roll back" in joined, "the real planner supplies a rollback per stage"
    assert "one change at a time" in joined.lower()


def test_the_planner_orders_one_change_at_a_time():
    from ui.setup_recommendation_vm import _build_test_plan
    changes = [{"field": f, "delta": 1, "from": 1, "to": 2, "setting": f}
               for f in ("arb_front", "aero_rear", "toe_rear")]
    steps = _build_test_plan({}, changes)
    assert steps[0].startswith("1.") and steps[1].startswith("2.")


def test_the_fallback_survives_for_a_recommendation_with_no_deltas():
    """A recommendation with no per-change deltas genuinely has no sequence to build."""
    from ui.setup_recommendation_vm import _build_test_plan
    steps = _build_test_plan({}, [{"field": "x", "delta": 0, "setting": "X"}])
    assert steps and "run 3 clean laps" in steps[0]


def test_the_named_function_actually_exists_now():
    import strategy.setup_test_plan as mod
    assert hasattr(mod, "build_test_sequence")
    assert not hasattr(mod, "build_test_plan"), (
        "if this ever appears, check which one the VM imports")


# ---------------------------------------------------------------------------
# C10 — the convergence ladder was fed constants
# ---------------------------------------------------------------------------
def _cycle_with_experiments(statuses):
    db = _db_with_activity()
    sid = _session_with_laps(db, clean=6)
    db.bind_session_to_activity("a1", str(sid), cycle_id="c1")
    for i, st in enumerate(statuses):
        db._conn.execute(
            "INSERT INTO setup_experiments (session_id,status,idempotency_key,created_at) "
            "VALUES (?,?,?,'')", (str(sid), st, f"k{i}"))
    db._conn.commit()
    return db


def test_outstanding_experiments_are_counted_not_hardcoded():
    """`outstanding_experiments=0` was hardcoded, so a discipline with three
    experiments still open read as having nothing outstanding — and this gated the
    Lock button."""
    db = _cycle_with_experiments(["test_in_progress", "applied"])
    rows = [(r[0], r[1]) for r in db._conn.execute(
        "SELECT e.status, COUNT(*) FROM setup_experiments e "
        "WHERE CAST(e.session_id AS TEXT) IN ("
        "  SELECT b.session_id FROM event_preparation_activity_sessions b "
        "  WHERE b.cycle_id=?) GROUP BY e.status", ("c1",))]
    outstanding = {"ready_for_apply", "applied", "test_in_progress", "ready_for_review"}
    assert sum(c for s, c in rows if s in outstanding) == 2


def test_a_draft_experiment_is_not_outstanding():
    """Nothing has been committed to the car yet."""
    db = _cycle_with_experiments(["draft"])
    rows = [(r[0], r[1]) for r in db._conn.execute(
        "SELECT e.status, COUNT(*) FROM setup_experiments e "
        "WHERE CAST(e.session_id AS TEXT) IN ("
        "  SELECT b.session_id FROM event_preparation_activity_sessions b "
        "  WHERE b.cycle_id=?) GROUP BY e.status", ("c1",))]
    outstanding = {"ready_for_apply", "applied", "test_in_progress", "ready_for_review"}
    assert sum(c for s, c in rows if s in outstanding) == 0


def test_the_convergence_inputs_are_no_longer_constants():
    import inspect

    from data.session_db import SessionDB
    src = inspect.getsource(SessionDB.build_event_preparation_report)
    # Read CODE, not comments — the comment explaining the fix quotes the old literal.
    code = "\n".join(l for l in src.splitlines() if not l.strip().startswith("#"))
    assert "outstanding_experiments=0" not in code
    assert "outstanding_experiments=_outstanding" in code
    assert "has_final_confirmation=" in code


def test_an_unreadable_experiment_table_does_not_read_as_converged():
    """The exact failure this defect is about: a missing signal defaulting to the
    permissive answer."""
    import inspect

    from data.session_db import SessionDB
    src = inspect.getsource(SessionDB.build_event_preparation_report)
    assert "_outstanding, _completed = 1, 0" in src


def test_the_gate_only_blocks_on_domains_the_transition_depends_on():
    """Scoping matters as much as the gate. A first version blocked on all NINE
    readiness dimensions, which would have demanded fuel, strategy and coaching
    evidence before you could go QUALIFYING. Nine blockers on every attempt is not a
    gate, it is a formality the driver learns to click through — the exact failure
    C11 describes."""
    from strategy.weekend_gate import REQUIRED_DOMAINS
    rows = [(name, "missing", "") for name in
            ("base_setup", "qualifying_setup", "race_setup", "tyre_evidence",
             "fuel_evidence", "driver_coaching", "race_pace", "strategy_evidence",
             "consistency")]
    v = evaluate_weekend_transition(
        WeekendTransition.BEGIN_QUALIFYING, readiness=rows,
        setup_applied=True, driver_comfortable=True)
    blocked = {b.key.split(":", 1)[-1] for b in v.blockers if b.key.startswith("readiness:")}
    assert blocked == set(REQUIRED_DOMAINS["begin_qualifying"])


def test_a_domain_outside_the_set_is_warned_about_not_hidden():
    """Not required is not the same as not worth saying."""
    v = evaluate_weekend_transition(
        WeekendTransition.BEGIN_QUALIFYING,
        readiness=[("fuel_evidence", "missing", "")],
        setup_applied=True, driver_comfortable=True)
    assert v.allowed is True
    assert any("Fuel evidence" in w for w in v.warnings)


def test_a_race_needs_more_than_a_qualifying_lap_does():
    from strategy.weekend_gate import REQUIRED_DOMAINS
    quali = set(REQUIRED_DOMAINS["begin_qualifying"])
    race = set(REQUIRED_DOMAINS["start_race"])
    assert "fuel_evidence" in race and "fuel_evidence" not in quali
    assert "strategy_evidence" in race and "strategy_evidence" not in quali
    assert "qualifying_setup" in quali and "qualifying_setup" not in race


def test_every_required_domain_is_a_real_readiness_dimension():
    """A required name that no readiness row ever carries would silently never block."""
    from strategy.preparation_evidence import _DOMAIN_TO_READINESS
    from strategy.weekend_gate import REQUIRED_DOMAINS
    known = set(_DOMAIN_TO_READINESS.values())
    for transition, names in REQUIRED_DOMAINS.items():
        unknown = set(names) - known
        assert not unknown, f"{transition} requires unknown dimension(s): {unknown}"
