"""Building the race plan without the classic tab (single-system slice 1).

The Race Strategy surface could only DISPLAY a plan — it read
``window._last_race_plan_result``, which only the classic Race Plan tab could set. A
driver working entirely in the new shell had a page that stayed empty forever with no
way to fill it.
"""

import pytest

from services.race_plan import RacePlanResult, RacePlanService


class _DB:
    def __init__(self, sessions=None, car_id=3):
        self._sessions = sessions if sessions is not None else []
        self._car_id = car_id
        self.planned_with = []

    def get_practice_sessions_for_cycle(self, cycle_id):
        return list(self._sessions)

    def get_car_id(self, name):
        return self._car_id

    def get_event(self, name):
        return None


def _config(**strategy):
    base = {"car": "Porsche Cayman GT4", "track": "Watkins Glen International",
            "race_type": "lap", "laps": 25}
    base.update(strategy)
    return {"active_cycle_id": "c1", "strategy": base}


def _recorded(*ids, laps=9):
    return [{"session_id": str(i), "total_laps": laps} for i in ids]


class TestRecordedSessionsAreTheEvidence:
    def test_only_recorded_runs_count(self):
        svc = RacePlanService(db=_DB(_recorded(4, 7)), config=_config())
        assert svc.recorded_sessions() == (7, 4)          # most recent first

    def test_a_run_with_no_laps_is_not_evidence(self):
        db = _DB([{"session_id": "4", "total_laps": 0},
                  {"session_id": "7", "total_laps": 9}])
        assert RacePlanService(db=db, config=_config()).recorded_sessions() == (7,)

    def test_no_active_event_means_no_evidence(self):
        svc = RacePlanService(db=_DB(_recorded(7)), config={"strategy": {}})
        assert svc.recorded_sessions() == ()

    def test_no_database_is_safe(self):
        assert RacePlanService(db=None, config=_config()).recorded_sessions() == ()


class TestRefusalsExplainThemselves:
    def test_with_no_recorded_run_it_says_how_to_get_one(self):
        result = RacePlanService(db=_DB([]), config=_config()).build_plan()
        assert result.ok is False
        assert "End run & record" in result.reason
        assert result.headline == result.reason

    def test_no_car_or_track_is_refused(self):
        svc = RacePlanService(db=_DB(_recorded(7)),
                              config={"active_cycle_id": "c1", "strategy": {}})
        result = svc.build_plan()
        assert result.ok is False
        assert "car and track" in result.reason

    def test_an_event_with_no_race_length_is_refused(self):
        svc = RacePlanService(db=_DB(_recorded(7)),
                              config=_config(laps=0, race_type="lap"))
        result = svc.build_plan()
        assert result.ok is False
        assert "no race length" in result.reason


class TestInputs:
    def test_the_event_supplies_the_race_settings(self):
        svc = RacePlanService(db=_DB(_recorded(7)), config=_config(laps=30))
        inputs = svc.build_inputs(7)
        assert inputs["race_laps"] == 30
        assert inputs["race_duration_minutes"] == 0.0
        assert inputs["car_name"] == "Porsche Cayman GT4"
        assert inputs["track"] == "Watkins Glen International"

    def test_a_timed_race_carries_minutes_and_no_laps(self):
        svc = RacePlanService(db=_DB(_recorded(7)),
                              config=_config(race_type="timed",
                                             race_duration_minutes=120))
        inputs = svc.build_inputs(7)
        assert inputs["race_duration_minutes"] == 120.0
        assert inputs["race_laps"] == 0

    def test_starting_fuel_is_a_full_tank(self):
        """GT7's tank is always 100% = 100 L."""
        assert RacePlanService(db=_DB(), config=_config()).build_inputs(7)[
            "starting_fuel_pct"] == 100.0

    def test_pit_loss_comes_from_the_frozen_strategy_snapshot(self):
        """The same fallback the classic tab uses when its manual field is left at
        zero. The snapshot supplies its own default when nothing has been measured, so
        this is NOT 'unknown' — the plan's measured-vs-assumed reporting is what tells
        the driver which it was."""
        value = RacePlanService(db=_DB(), config=_config()).build_inputs(7)["pit_loss_seconds"]
        assert value > 0
        assert isinstance(value, float)

    def test_inputs_never_raise_on_an_empty_config(self):
        inputs = RacePlanService(db=None, config={}).build_inputs(0)
        assert inputs["track"] == "" and inputs["car_name"] == ""


class TestBuilding:
    def test_the_most_recent_recorded_run_is_used_when_none_is_named(self, monkeypatch):
        seen = {}

        def _fake(db, **kw):
            seen.update(kw)
            return {"ok": True}

        monkeypatch.setattr("strategy.race_strategy_pipeline.recommend_strategy_from_session",
                            _fake)
        monkeypatch.setattr("ui.race_strategy_vm.build_race_plan_view_model",
                            lambda r: {"vm": True})
        svc = RacePlanService(db=_DB(_recorded(4, 7)), config=_config())
        plan = svc.build_plan()
        assert plan.ok is True
        assert plan.session_id == 7
        assert seen["session_id"] == 7
        assert seen["race_laps"] == 25

    def test_a_named_session_is_honoured(self, monkeypatch):
        monkeypatch.setattr("strategy.race_strategy_pipeline.recommend_strategy_from_session",
                            lambda db, **kw: {"ok": True})
        monkeypatch.setattr("ui.race_strategy_vm.build_race_plan_view_model",
                            lambda r: {"vm": True})
        svc = RacePlanService(db=_DB(_recorded(4, 7)), config=_config())
        assert svc.build_plan(4).session_id == 4

    def test_a_successful_plan_is_retained_for_the_live_replan_compare(self, monkeypatch):
        monkeypatch.setattr("strategy.race_strategy_pipeline.recommend_strategy_from_session",
                            lambda db, **kw: {"raw": True})
        monkeypatch.setattr("ui.race_strategy_vm.build_race_plan_view_model",
                            lambda r: {"vm": True})
        svc = RacePlanService(db=_DB(_recorded(7)), config=_config())
        svc.build_plan()
        assert svc.last_plan.result == {"raw": True}
        assert svc.last_plan.view_model == {"vm": True}

    def test_a_pipeline_failure_reports_its_reason(self, monkeypatch):
        def _boom(db, **kw):
            raise RuntimeError("not enough laps")

        monkeypatch.setattr("strategy.race_strategy_pipeline.recommend_strategy_from_session",
                            _boom)
        svc = RacePlanService(db=_DB(_recorded(7)), config=_config())
        plan = svc.build_plan()
        assert plan.ok is False
        assert "not enough laps" in plan.reason

    def test_a_failed_build_does_not_replace_the_last_good_plan(self, monkeypatch):
        monkeypatch.setattr("strategy.race_strategy_pipeline.recommend_strategy_from_session",
                            lambda db, **kw: {"raw": True})
        monkeypatch.setattr("ui.race_strategy_vm.build_race_plan_view_model",
                            lambda r: {"vm": True})
        svc = RacePlanService(db=_DB(_recorded(7)), config=_config())
        svc.build_plan()

        def _boom(db, **kw):
            raise RuntimeError("nope")

        monkeypatch.setattr("strategy.race_strategy_pipeline.recommend_strategy_from_session",
                            _boom)
        svc.build_plan()
        assert svc.last_plan.ok is True                # the good one survives


class TestResultObject:
    def test_an_empty_result_is_not_ok(self):
        assert RacePlanResult().ok is False

    def test_the_headline_always_says_something(self):
        assert RacePlanResult(ok=True, session_id=7).headline
        assert RacePlanResult().headline
