"""The guided practice loop: run planning, binding decisions and the DB writer.

Before this, ``upsert_preparation_activity`` / ``bind_session_to_activity`` had no
production caller at all — the event programme could never gain an activity, so no
session was ever bound, so cumulative evidence stayed empty and the engineer's
objective never moved no matter how many laps the driver ran.
"""

import pytest

from strategy.event_preparation_cycle import PreparationActivityType as T
from strategy.practice_run_recording import (
    completed_activity_row, discarded_activity_row, domain_from_objective_headline,
    evaluate_run_binding, plan_practice_run, run_type_for_domain,
)
from ui.practice_run_recorder import PracticeRunRecorder


class _DB:
    """Minimal stand-in for the SessionDB surface the recorder touches."""

    def __init__(self, cycle=None, activities=None, sessions=None):
        self.cycle = cycle or {"cycle_id": "c1", "car": "Porsche Cayman GT4",
                               "track": "Watkins Glen International"}
        self.activities = list(activities or [])
        self.sessions = sessions or {}
        self.bindings = []

    def list_preparation_activities(self, cycle_id):
        return [a for a in self.activities if a.get("cycle_id") == cycle_id]

    def get_preparation_cycle(self, cycle_id):
        return dict(self.cycle) if cycle_id == self.cycle["cycle_id"] else None

    def upsert_preparation_activity(self, row):
        for i, a in enumerate(self.activities):
            if a["activity_id"] == row["activity_id"]:
                self.activities[i] = dict(row)
                return row["activity_id"]
        self.activities.append(dict(row))
        return row["activity_id"]

    def bind_session_to_activity(self, activity_id, session_id, cycle_id="", created_at=""):
        self.bindings.append((activity_id, str(session_id), cycle_id))
        return True

    def get_session_meta(self, session_id):
        return self.sessions.get(int(session_id or 0))


def _meta(laps=9, car="Porsche Cayman GT4", track="Watkins Glen International"):
    return {"id": 7, "total_laps": laps, "car_name": car, "track": track}


class TestObjectiveToRunType:
    def test_domain_parsed_from_the_headline(self):
        assert domain_from_objective_headline("Build setup_base evidence") == "setup_base"
        assert domain_from_objective_headline("Build tyre_model evidence") == "tyre_model"
        assert domain_from_objective_headline(
            "Confirm and protect the current best-known setup") == "convergence"
        assert domain_from_objective_headline("") == ""

    def test_setup_base_plans_a_baseline_practice_run(self):
        assert run_type_for_domain("setup_base") is T.BASELINE_PRACTICE

    def test_unknown_domain_never_credits_setup_evidence(self):
        """Free practice contributes consistency/race pace only — never a setup domain."""
        assert run_type_for_domain("nonsense") is T.FREE_PRACTICE


class TestPlanPracticeRun:
    def test_no_active_event_plans_nothing(self):
        plan = plan_practice_run(cycle_id="", objective_domain="setup_base")
        assert plan.ok is False
        assert "activate" in plan.reason.lower()

    def test_plans_the_run_the_engineer_asked_for(self):
        plan = plan_practice_run(cycle_id="c1", objective_domain="setup_base",
                                 objective_headline="Build setup_base evidence")
        assert plan.ok and not plan.reused
        assert plan.activity_type == T.BASELINE_PRACTICE.value
        assert plan.activity_id == "c1::baseline_practice::1"
        assert plan.objective == "Build setup_base evidence"
        assert plan.state == "in_progress"

    def test_ids_are_deterministic_and_do_not_collide(self):
        first = plan_practice_run(cycle_id="c1", objective_domain="setup_base")
        done = [{"activity_id": first.activity_id, "activity_type": first.activity_type,
                 "state": "completed"}]
        second = plan_practice_run(cycle_id="c1", objective_domain="setup_base",
                                   existing_activities=done)
        assert second.activity_id == "c1::baseline_practice::2"
        # Same inputs, same id — replanning never duplicates.
        again = plan_practice_run(cycle_id="c1", objective_domain="setup_base",
                                  existing_activities=done)
        assert again.activity_id == second.activity_id

    def test_an_open_run_is_reused_not_duplicated(self):
        open_run = [{"activity_id": "c1::baseline_practice::1",
                     "activity_type": "baseline_practice", "state": "in_progress",
                     "title": "Baseline practice run 1", "objective": "Build setup_base evidence"}]
        plan = plan_practice_run(cycle_id="c1", objective_domain="tyre_model",
                                 existing_activities=open_run)
        assert plan.reused is True
        assert plan.activity_id == "c1::baseline_practice::1"

    def test_activity_row_shape(self):
        plan = plan_practice_run(cycle_id="c1", objective_domain="setup_race")
        row = plan.as_activity_row(now_iso="2026-07-23T10:00:00")
        assert row["cycle_id"] == "c1"
        assert row["state"] == "in_progress"
        assert row["updated_at"] == "2026-07-23T10:00:00"
        assert row["optional"] is False


class TestBindingDecision:
    def test_no_open_run_rejects(self):
        d = evaluate_run_binding(activity_id="", cycle_id="c1", session_id=7)
        assert d.ok is False and "Start practice run" in d.reason

    def test_no_session_rejects_with_a_cause(self):
        d = evaluate_run_binding(activity_id="a1", cycle_id="c1", session_id=0)
        assert d.ok is False and "connected" in d.reason

    def test_zero_laps_rejects(self):
        d = evaluate_run_binding(activity_id="a1", cycle_id="c1", session_id=7,
                                 session_meta=_meta(laps=0))
        assert d.ok is False and "no completed laps" in d.reason

    def test_matching_session_is_event_evidence(self):
        cyc = {"car": "Porsche Cayman GT4", "track": "Watkins Glen International"}
        d = evaluate_run_binding(activity_id="a1", cycle_id="c1", session_id=7,
                                 session_meta=_meta(), cycle=cyc)
        assert d.ok and d.compatible and d.laps == 9
        assert d.contributes_event_evidence is True
        assert d.warning == ""

    def test_wrong_car_is_recorded_but_never_counted(self):
        cyc = {"car": "Porsche Cayman GT4", "track": "Watkins Glen International"}
        d = evaluate_run_binding(activity_id="a1", cycle_id="c1", session_id=7,
                                 session_meta=_meta(car="Mazda MX-5"), cycle=cyc)
        assert d.ok is True                       # what happened is still recorded
        assert d.compatible is False
        assert d.contributes_event_evidence is False
        assert "not this event" in d.warning

    def test_unknown_context_stays_unknown(self):
        d = evaluate_run_binding(activity_id="a1", cycle_id="c1", session_id=7,
                                 session_meta=_meta(car="", track=""), cycle={})
        assert d.ok is True and d.compatible is False
        assert "unknown" in d.warning.lower()


class TestRecorderWrites:
    def test_start_writes_one_activity(self):
        db = _DB()
        r = PracticeRunRecorder(db=db, config={"active_cycle_id": "c1"})
        plan = r.start_run(objective_domain="setup_base",
                           objective_headline="Build setup_base evidence")
        assert plan.ok
        assert len(db.activities) == 1
        assert db.activities[0]["state"] == "in_progress"
        assert r.open_run()["activity_id"] == plan.activity_id

    def test_start_twice_does_not_open_two_runs(self):
        db = _DB()
        r = PracticeRunRecorder(db=db, config={"active_cycle_id": "c1"})
        r.start_run(objective_domain="setup_base")
        r.start_run(objective_domain="setup_base")
        assert len(db.activities) == 1

    def test_no_active_event_writes_nothing(self):
        db = _DB()
        r = PracticeRunRecorder(db=db, config={})
        plan = r.start_run(objective_domain="setup_base")
        assert plan.ok is False
        assert db.activities == []

    def test_record_binds_the_session_and_closes_the_run(self):
        db = _DB(sessions={7: _meta()})
        r = PracticeRunRecorder(db=db, config={"active_cycle_id": "c1"})
        plan = r.start_run(objective_domain="setup_base")
        decision = r.record_run(7)
        assert decision.ok and decision.laps == 9
        assert db.bindings == [(plan.activity_id, "7", "c1")]
        assert db.activities[0]["state"] == "completed"
        assert r.open_run() is None

    def test_record_without_a_run_binds_nothing(self):
        db = _DB(sessions={7: _meta()})
        r = PracticeRunRecorder(db=db, config={"active_cycle_id": "c1"})
        decision = r.record_run(7)
        assert decision.ok is False
        assert db.bindings == []

    def test_a_lapless_run_is_never_bound(self):
        db = _DB(sessions={7: _meta(laps=0)})
        r = PracticeRunRecorder(db=db, config={"active_cycle_id": "c1"})
        r.start_run(objective_domain="setup_base")
        decision = r.record_run(7)
        assert decision.ok is False
        assert db.bindings == []
        assert db.activities[0]["state"] == "in_progress"   # still open, not lost

    def test_discard_closes_without_binding(self):
        db = _DB(sessions={7: _meta()})
        r = PracticeRunRecorder(db=db, config={"active_cycle_id": "c1"})
        r.start_run(objective_domain="setup_base")
        assert r.discard_run() is True
        assert db.bindings == []
        assert db.activities[0]["state"] == "cancelled"
        assert r.open_run() is None


class TestRowTransitions:
    def test_completed_row_preserves_identity(self):
        a = {"activity_id": "a1", "cycle_id": "c1", "activity_type": "baseline_practice",
             "title": "Baseline practice run 1", "objective": "obj", "order_index": 3,
             "phase": "baseline_establishment", "created_at": "2026-07-23T09:00:00"}
        row = completed_activity_row(a, now_iso="2026-07-23T10:00:00")
        assert row["state"] == "completed"
        assert row["order_index"] == 3
        assert row["created_at"] == "2026-07-23T09:00:00"
        assert discarded_activity_row(a)["state"] == "cancelled"
