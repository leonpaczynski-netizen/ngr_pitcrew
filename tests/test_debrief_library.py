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
