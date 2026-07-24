"""Tests for the Debrief view + Engineering Library landing (F7/F8)."""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.components.debrief_view import DebriefView, DebriefVM
from ui.components.engineering_library import EngineeringLibrary, LIBRARY_AREAS


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _debrief():
    return DebriefVM(
        what_happened="5-lap diagnosis run on Softs at Watkins Glen.",
        improved=("Mid-corner rotation at the Esses (+1.8 km/h)",),
        regressed=("Slight entry instability into Turn 1",),
        learned=("Rear ARB is the dominant lever for this car/track",),
        predictions_correct=("ARB softening improves rotation",),
        predictions_wrong=("Expected no entry change — there was one",),
        contradictions=(),
        setup_outcome="Quali v3 kept — improved",
        strategy_outcome="No change",
        carry_forward=("Rear ARB working window 4–5 for this layout",),
        primary_action_label="Continue development", primary_action_key="continue",
    )


class TestDebrief:
    def test_renders_and_primary_key(self, qapp):
        w = DebriefView()
        w.set_debrief(_debrief())
        assert w._vm.has_debrief is True
        seen = []
        w.action_requested.connect(lambda k: seen.append(k))
        w._primary.click()
        assert seen == ["continue"]

    def test_regressions_kept_visible(self, qapp):
        # Failed/regressed items must remain visible, never hidden.
        w = DebriefView()
        w.set_debrief(_debrief())
        texts = [w._body.itemAt(i).widget().text()
                 for i in range(w._body.count())
                 if w._body.itemAt(i).widget() is not None]
        joined = " ".join(texts)
        assert "Regressed" in joined and "entry instability" in joined

    def test_empty_shows_placeholder(self, qapp):
        w = DebriefView()
        w.set_debrief(DebriefVM())
        assert w._empty.isHidden() is False
        assert w._primary.isEnabled() is False

    def test_defensive(self, qapp):
        w = DebriefView()
        w.set_debrief("garbage")
        assert w._empty.isHidden() is False


class TestDebriefFromCrossSessionMemory:
    """UAT-6: "debrief page doesn't seem to be doing anything".

    build_cross_session_memory returns the NESTED shape
    {ok, memory, scorecard, comparison, ...}; the adapter read issues/band/regressions
    as TOP-LEVEL keys — none of which exist there — so the Debrief was always empty.
    """

    def _mem(self):
        return {
            "ok": True, "record_count": 3,
            "memory": {
                "issues": [
                    {"issue_type": "understeer", "corner": "Turn 6", "phase": "entry",
                     "currently_resolved": True, "times_regressed": 0},
                    {"issue_type": "oversteer", "corner": "Turn 10", "phase": "exit",
                     "currently_resolved": False, "times_regressed": 2},
                    {"issue_type": "braking_instability", "corner": "Turn 1",
                     "phase": "entry", "currently_resolved": False, "times_regressed": 0},
                ],
                "protected_knowledge": [
                    {"kind": "field_direction", "field": "front_wing",
                     "direction": "higher is better"}],
                "protected_behaviours": [{"label": "stable on entry into Turn 1"}],
            },
            "scorecard": {"band": "consolidating"},
            "comparison": {"earlier_label": "Session 4", "later_label": "Session 7",
                           "verdict": "improved", "issues_resolved_delta": 1,
                           "regressions_delta": -1, "improvements_delta": 2},
        }

    def test_the_nested_shape_populates_the_debrief(self, qapp):
        from ui.shell_feed_adapters import debrief_vm_from_memory
        vm = debrief_vm_from_memory(self._mem())
        assert vm.has_debrief is True
        assert "improved" in vm.what_happened and "consolidating" in vm.what_happened
        assert vm.improved == ("understeer at Turn 6 (entry)",)
        assert vm.regressed == ("oversteer at Turn 10 (exit)",)
        assert vm.learned == ("front_wing — higher is better",)
        assert vm.carry_forward == ("stable on entry into Turn 1",)
        assert "+1 issues resolved" in vm.setup_outcome

    def test_a_resolved_issue_is_never_also_a_regression(self, qapp):
        from ui.shell_feed_adapters import debrief_vm_from_memory
        vm = debrief_vm_from_memory(self._mem())
        assert not (set(vm.improved) & set(vm.regressed))
        # The still-open, non-regressed issue lands under findings, not regressions.
        assert any("braking instability" in f for f in vm.findings)

    def test_an_empty_programme_shows_the_placeholder_not_a_hollow_band(self, qapp):
        from ui.shell_feed_adapters import debrief_vm_from_memory
        empty = {"ok": True, "record_count": 0, "memory": {"issues": []},
                 "scorecard": {"band": "insufficient"}, "comparison": None}
        assert debrief_vm_from_memory(empty).has_debrief is False

    def test_it_never_raises_on_junk(self, qapp):
        from ui.shell_feed_adapters import debrief_vm_from_memory
        for junk in (None, {}, {"ok": False}, {"ok": True}, "nope", 7,
                     {"ok": True, "record_count": 2, "memory": None}):
            assert debrief_vm_from_memory(junk) is not None


class TestEngineeringLibrary:
    def test_lists_all_areas(self, qapp):
        lib = EngineeringLibrary()
        assert set(lib._buttons.keys()) == {a[0] for a in LIBRARY_AREAS}

    def test_open_emits_area_key(self, qapp):
        lib = EngineeringLibrary()
        seen = []
        lib.open_requested.connect(lambda k: seen.append(k))
        lib._buttons["knowledge_graph"].click()
        assert seen == ["knowledge_graph"]

    def test_has_development_history_and_certification(self, qapp):
        keys = {a[0] for a in LIBRARY_AREAS}
        assert "development_history" in keys and "certification" in keys
