"""The setup engine, headless (single-system stage 2).

Every operation returns a RESULT OBJECT. The classic path reported into a QTextEdit that
the shell had to scrape, which is why "finished with no changes" and "failed" both looked
exactly like "still running" — the hang UAT reported.
"""

import json

import pytest

from services.setup_service import (
    AnalysisResult, BaselineResult, SetupInputs, SetupService,
)
from services.setup_store import SetupSheetStore, scope_key


def _inputs(**kw):
    base = dict(car="Porsche Cayman GT4", track="Watkins Glen International",
                layout="long_course", num_gears=6, drivetrain="MR")
    base.update(kw)
    return SetupInputs(**base)


class _Advisor:
    """Stands in for DrivingAdvisor: both entry points return a JSON string."""

    def __init__(self, baseline=None, combined=None, raise_on=""):
        self._baseline = baseline
        self._combined = combined
        self._raise_on = raise_on
        self.baseline_calls = []
        self.combined_calls = []

    def build_baseline_setup_response(self, **kw):
        self.baseline_calls.append(kw)
        if self._raise_on == "baseline":
            raise RuntimeError("engine exploded")
        if callable(self._baseline):
            return self._baseline(kw)
        return self._baseline

    def build_combined_setup_response(self, setup, **kw):
        self.combined_calls.append((setup, kw))
        if self._raise_on == "combined":
            raise RuntimeError("engine exploded")
        return self._combined


class _Authority:
    def __init__(self):
        self.applied = []

    def mark_applied(self, identity, *, setup_id, name, fields, purpose, applied_at="",
                     source="applied_in_game"):
        self.applied.append((identity, purpose, dict(fields)))
        return type("A", (), {"label": lambda _self: f"{name} · rev 1",
                              "is_active_on_car": True})()

    def active_setup(self, identity, purpose="Race"):
        if not self.applied:
            return None
        return type("A", (), {"label": lambda _self: "Setup 1 · rev 1",
                              "is_active_on_car": True})()


def _svc(tmp_path, advisor=None, inputs=None, authority=None):
    store = SetupSheetStore(str(tmp_path / "sheets.json"))
    return SetupService(store=store, advisor=advisor, authority=authority,
                        inputs_provider=lambda: inputs or _inputs()), store


_BASELINE_OK = json.dumps({"setup_fields": {"arb_front": 6, "arb_rear": 5,
                                            "springs_front": 3.4}})
_COMBINED_OK = json.dumps({
    "analysis": "Front is washing out on entry.",
    "changes": [{"field": "arb_front", "from": 6, "to": 5, "reason": "reduce understeer"}],
    "setup_fields": {"arb_front": 5},
    "recommendation_status": "approved"})
_COMBINED_NO_CHANGE = json.dumps({
    "analysis": "The setup is inside its working window.",
    "changes": [], "setup_fields": {}, "recommendation_status": "approved"})


class TestBuildInitialSetup:
    def test_both_sheets_are_authored(self, tmp_path):
        svc, store = _svc(tmp_path, _Advisor(baseline=_BASELINE_OK))
        result = svc.build_initial_setup()
        assert result.ok is True
        assert result.built == ("race", "qualifying")
        assert "Race sheet ✓" in result.headline and "Qualifying sheet ✓" in result.headline
        scope = scope_key("Porsche Cayman GT4", "Watkins Glen International", "long_course")
        assert store.get(scope, "race").get("arb_front") == 6.0
        assert store.get(scope, "qualifying").get("arb_front") == 6.0

    def test_each_sheet_is_generated_for_its_own_purpose(self, tmp_path):
        advisor = _Advisor(baseline=_BASELINE_OK)
        svc, _store = _svc(tmp_path, advisor)
        svc.build_initial_setup()
        purposes = [c["session_type"] for c in advisor.baseline_calls]
        assert purposes == ["Race Setup", "Qualifying Setup"]

    def test_a_sheet_that_fails_is_reported_not_implied(self, tmp_path):
        """The exact doubt UAT raised: did Qualifying actually build?"""
        def _only_race(kw):
            return _BASELINE_OK if kw["session_type"].startswith("Race") else "{}"
        svc, store = _svc(tmp_path, _Advisor(baseline=_only_race))
        result = svc.build_initial_setup()
        assert result.built == ("race",)
        assert "qualifying" in result.failed
        assert "Qualifying sheet ✓" not in result.headline
        assert "Qualifying:" in result.headline

    def test_no_car_or_track_refuses_with_a_reason(self, tmp_path):
        svc, _s = _svc(tmp_path, _Advisor(baseline=_BASELINE_OK), inputs=SetupInputs())
        result = svc.build_initial_setup()
        assert result.ok is False
        assert "car and track" in result.reason

    def test_a_fully_locked_event_has_nothing_to_build(self, tmp_path):
        svc, _s = _svc(tmp_path, _Advisor(baseline=_BASELINE_OK),
                       inputs=_inputs(tuning_locked=True))
        result = svc.build_initial_setup()
        assert result.ok is False
        assert "locks every tuning category" in result.reason

    def test_an_engine_exception_becomes_a_reason_not_a_crash(self, tmp_path):
        svc, _s = _svc(tmp_path, _Advisor(raise_on="baseline"))
        result = svc.build_initial_setup()
        assert result.ok is False
        assert "engine exploded" in str(result.failed)

    def test_no_advisor_is_reported(self, tmp_path):
        svc, _s = _svc(tmp_path, None)
        assert "not available" in svc.build_initial_setup().reason


class TestAnalyse:
    def _built(self, tmp_path, combined):
        advisor = _Advisor(baseline=_BASELINE_OK, combined=combined)
        svc, store = _svc(tmp_path, advisor)
        svc.build_initial_setup()
        return svc, store, advisor

    def test_a_recommendation_is_returned_as_data(self, tmp_path):
        svc, _s, _a = self._built(tmp_path, _COMBINED_OK)
        result = svc.analyse("race")
        assert result.ok is True
        assert result.has_recommendation is True
        assert result.setup_fields == {"arb_front": 5}
        assert "1 change recommended." == result.headline

    def test_finishing_with_no_change_is_a_SUCCESS_that_says_so(self, tmp_path):
        """Previously indistinguishable from 'still running' — the reported hang."""
        svc, _s, _a = self._built(tmp_path, _COMBINED_NO_CHANGE)
        result = svc.analyse("race")
        assert result.ok is True
        assert result.has_recommendation is False
        assert "No change recommended" in result.headline

    def test_a_failure_says_why(self, tmp_path):
        advisor = _Advisor(baseline=_BASELINE_OK, combined=None, raise_on="combined")
        svc, _store = _svc(tmp_path, advisor)
        svc.build_initial_setup()
        result = svc.analyse("race")
        assert result.ok is False
        assert "engine exploded" in result.headline

    def test_an_unreadable_reply_is_never_shown_raw(self, tmp_path):
        svc, _s, _a = self._built(tmp_path, '{"analysis": "truncated mid')
        result = svc.analyse("race")
        assert result.ok is False
        assert "incomplete" in result.headline

    def test_analysing_an_empty_sheet_explains_the_order_of_work(self, tmp_path):
        svc, _store = _svc(tmp_path, _Advisor(combined=_COMBINED_OK))
        result = svc.analyse("race")
        assert result.ok is False
        assert "build the initial setup first" in result.reason

    def test_the_sheet_analysed_is_the_one_for_that_discipline(self, tmp_path):
        svc, store, advisor = self._built(tmp_path, _COMBINED_OK)
        store.merge(_inputs().scope, "qualifying", {"arb_front": 99})
        svc.analyse("qualifying")
        analysed_setup, kw = advisor.combined_calls[-1]
        assert analysed_setup["arb_front"] == 99.0
        assert kw["purpose"] == "Qualifying"


class TestApplyAndRevert:
    def _built(self, tmp_path):
        svc, store = _svc(tmp_path, _Advisor(baseline=_BASELINE_OK))
        svc.build_initial_setup()
        return svc, store

    def test_applying_writes_the_fields_and_names_them(self, tmp_path):
        svc, store = self._built(tmp_path)
        out = svc.apply("race", {"arb_front": 4})
        assert out.ok is True
        assert out.changed_fields == ("arb_front",)
        assert store.get(_inputs().scope, "race").get("arb_front") == 4.0

    def test_applying_the_values_already_there_is_not_a_change(self, tmp_path):
        svc, _store = self._built(tmp_path)
        out = svc.apply("race", {"arb_front": 6})
        assert out.ok is True and out.changed is False
        assert "already on the sheet" in out.reason

    def test_applying_nothing_is_refused(self, tmp_path):
        svc, _store = self._built(tmp_path)
        assert svc.apply("race", {}).ok is False

    def test_apply_targets_only_its_own_discipline(self, tmp_path):
        svc, store = self._built(tmp_path)
        svc.apply("qualifying", {"arb_front": 2})
        assert store.get(_inputs().scope, "qualifying").get("arb_front") == 2.0
        assert store.get(_inputs().scope, "race").get("arb_front") == 6.0

    def test_revert_undoes_the_last_apply(self, tmp_path):
        svc, store = self._built(tmp_path)
        svc.apply("race", {"arb_front": 4})
        out = svc.revert("race")
        assert out.ok is True
        assert store.get(_inputs().scope, "race").get("arb_front") == 6.0

    def test_revert_with_nothing_to_undo_says_so(self, tmp_path):
        svc, _store = self._built(tmp_path)
        out = svc.revert("race")
        assert out.ok is False
        assert "nothing to undo" in out.reason

    def test_undo_history_is_per_service_not_shared(self, tmp_path):
        svc_a, _sa = self._built(tmp_path)
        svc_b, _sb = self._built(tmp_path / "other")
        svc_a.apply("race", {"arb_front": 4})
        assert svc_b.revert("race").ok is False


class TestConfirmAppliedInGame:
    def _built(self, tmp_path, authority):
        store = SetupSheetStore(str(tmp_path / "sheets.json"))
        svc = SetupService(store=store, advisor=_Advisor(baseline=_BASELINE_OK),
                           authority=authority, inputs_provider=lambda: _inputs())
        svc.build_initial_setup()
        return svc

    def test_confirming_marks_the_setup_active(self, tmp_path):
        auth = _Authority()
        svc = self._built(tmp_path, auth)
        out = svc.confirm_applied_in_game("race")
        assert out.ok is True
        assert "active setup" in out.reason
        assert auth.applied and auth.applied[0][1] == "Race"

    def test_the_whole_sheet_is_recorded_not_just_the_changes(self, tmp_path):
        auth = _Authority()
        svc = self._built(tmp_path, auth)
        svc.confirm_applied_in_game("race")
        _identity, _purpose, fields = auth.applied[0]
        assert fields["arb_front"] == 6.0
        assert "springs_front" in fields

    def test_qualifying_is_a_separate_scope(self, tmp_path):
        auth = _Authority()
        svc = self._built(tmp_path, auth)
        svc.confirm_applied_in_game("qualifying")
        assert auth.applied[0][1] == "Qualifying"

    def test_an_empty_sheet_cannot_be_confirmed(self, tmp_path):
        store = SetupSheetStore(str(tmp_path / "sheets.json"))
        svc = SetupService(store=store, authority=_Authority(),
                           inputs_provider=lambda: _inputs())
        out = svc.confirm_applied_in_game("race")
        assert out.ok is False
        assert "no setup on it" in out.reason

    def test_active_setup_reads_back(self, tmp_path):
        auth = _Authority()
        svc = self._built(tmp_path, auth)
        assert svc.active_setup("race") == ("", False)
        svc.confirm_applied_in_game("race")
        label, on_car = svc.active_setup("race")
        assert label and on_car is True

    def test_no_authority_is_reported(self, tmp_path):
        svc = self._built(tmp_path, None)
        assert "authority is not available" in svc.confirm_applied_in_game("race").reason


class TestNeverRaises:
    def test_a_broken_inputs_provider_degrades_to_unknown(self, tmp_path):
        store = SetupSheetStore(str(tmp_path / "s.json"))

        def _boom():
            raise RuntimeError("nope")

        svc = SetupService(store=store, inputs_provider=_boom)
        assert svc.inputs().is_known is False
        assert svc.build_initial_setup().ok is False
