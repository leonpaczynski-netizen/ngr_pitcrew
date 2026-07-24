"""The Programme page renders the map and offers the next run (UAT-6)."""

import pytest

from PyQt6.QtWidgets import QApplication

from strategy.programme_map import build_programme_map
from ui.components.programme_map import ProgrammeMapPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _readiness(**levels):
    return [[n, lvl, f"{ex} exact / 0 labelled sample(s)"]
            for n, (lvl, ex) in levels.items()]


_STATE = _readiness(
    base_setup=("developing", 2), race_pace=("adequate", 3),
    consistency=("strong", 5), tyre_evidence=("missing", 0),
)


class TestRendering:
    def test_it_shows_the_completion_figure_and_headline(self, qapp):
        p = ProgrammeMapPage()
        p.set_map(build_programme_map(_STATE))
        assert p._pct.text().endswith("%")
        assert "areas covered" in p._headline.text()

    def test_it_renders_one_row_per_area(self, qapp):
        p = ProgrammeMapPage()
        p.set_map(build_programme_map(_STATE))
        assert p._areas_box.count() == 4

    def test_the_action_names_the_weakest_areas_run(self, qapp):
        p = ProgrammeMapPage()
        p.set_map(build_programme_map(_STATE, next_domain="tyre_model"))
        # tyre_evidence is MISSING — the weakest — so the button starts a tyre test.
        assert "tyre test" in p._start.text().lower()

    def test_the_action_emits_the_weakest_domain(self, qapp):
        p = ProgrammeMapPage()
        seen = []
        p.start_next_requested.connect(seen.append)
        p.set_map(build_programme_map(_STATE))
        p._start.click()
        assert seen == ["tyre_model"]

    def test_a_finished_programme_disables_the_action(self, qapp):
        p = ProgrammeMapPage()
        p.set_map(build_programme_map(_readiness(
            base_setup=("adequate", 3), race_pace=("strong", 4))))
        assert p._start.isEnabled() is False


class TestClickableAreas:
    """UAT-8: "would like to see more information if I click on evidence areas on
    programme page." Clicking an area toggles its full detail."""

    def _labels(self, p, qapp=None):
        from PyQt6.QtWidgets import QLabel
        from PyQt6.QtCore import QEvent
        app = QApplication.instance()
        app.processEvents()
        app.sendPostedEvents(None, QEvent.Type.DeferredDelete)   # flush deleteLater
        app.processEvents()
        return [l.text() for l in p.findChildren(QLabel)]

    def test_detail_is_hidden_until_an_area_is_opened(self, qapp):
        p = ProgrammeMapPage()
        p.set_map(build_programme_map(_STATE))
        assert not any("How to drive it" in t for t in self._labels(p))

    def test_opening_an_area_shows_how_and_reports(self, qapp):
        p = ProgrammeMapPage()
        p.set_map(build_programme_map(_STATE))
        p._toggle_area("base_setup")
        labels = self._labels(p)
        assert any("How to drive it" in t for t in labels)
        assert any("What it will tell you" in t for t in labels)

    def test_opening_the_tyre_area_lists_missing_compounds(self, qapp):
        p = ProgrammeMapPage()
        p.set_map(build_programme_map(_STATE, tyre_required=["RS", "RM", "RH"],
                                      tyre_sampled=["RS"]))
        p._toggle_area("tyre_evidence")
        assert any("Compounds still to run" in t for t in self._labels(p))

    def test_toggling_again_collapses_it(self, qapp):
        p = ProgrammeMapPage()
        p.set_map(build_programme_map(_STATE))
        p._toggle_area("base_setup")
        p._toggle_area("base_setup")
        assert not any("How to drive it" in t for t in self._labels(p))


class TestEmptyAndDefensive:
    def test_no_programme_shows_the_placeholder(self, qapp):
        p = ProgrammeMapPage()
        p.set_map(build_programme_map([]))
        assert p._empty.isHidden() is False
        assert p._areas_card.isHidden() is True

    def test_garbage_never_raises(self, qapp):
        p = ProgrammeMapPage()
        p.set_map("nonsense")
        p.set_map(None)
        assert p._empty.isHidden() is False
