"""The event setup flow — guided, not an eighteen-field wall.

Direction: "I don't want you to replicate the old program... we scrapped the old UI
because it was terrible, I don't want this new one to become the same." These tests pin
the rules that keep it from becoming the same, so a later change cannot quietly undo them.
"""

import pytest

from PyQt6.QtWidgets import QApplication

from services.event_setup import DEFAULT_RULES, EventDraft
from ui.components.event_setup import STEPS, EventSetupPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def page(qapp):
    p = EventSetupPage(tracks=["Watkins Glen International", "Fuji Speedway"],
                       cars=["Porsche Cayman GT4", "Mazda MX-5"])
    return p


def _fill_identity(page, name="GR Enduro Rd2", car="Porsche Cayman GT4",
                   track="Watkins Glen International"):
    page._name.setText(name)
    page._car.setCurrentText(car)
    page._track.setCurrentText(track)


class TestOneQuestionAtATime:
    def test_there_are_four_steps_and_it_opens_on_the_first(self, page):
        assert len(STEPS) == 4
        assert page.current_step() == 0

    def test_only_one_step_is_visible_at_a_time(self, page):
        assert page._stack.count() == 4
        assert page._stack.currentIndex() == 0

    def test_progress_is_always_shown(self, page):
        assert len(page._chip_labels) == 4
        assert all(lbl.text() for lbl in page._chip_labels)

    def test_the_first_step_has_no_back_button(self, page):
        assert page._back.isVisibleTo(page) is False

    def test_back_appears_once_you_move_on(self, page):
        _fill_identity(page)
        page._next.click()
        assert page.current_step() == 1
        assert page._back.isVisibleTo(page) is True

    def test_back_returns_without_losing_what_was_typed(self, page):
        _fill_identity(page)
        page._next.click()
        page._back.click()
        assert page.current_step() == 0
        assert page._name.text() == "GR Enduro Rd2"

    def test_the_last_step_asks_to_save_rather_than_next(self, page):
        _fill_identity(page)
        for _ in range(3):
            page._next.click()
        assert page.current_step() == 3
        assert "Save" in page._next.text()


class TestOnlyTheEssentialsCanBlock:
    def test_missing_identity_blocks_and_says_why(self, page):
        page._next.click()
        assert page.current_step() == 0
        assert page._issues.isVisibleTo(page) is True
        assert "name" in page._issues.text().lower()

    def test_the_message_names_the_fix_not_just_the_problem(self, page):
        page._next.click()
        text = page._issues.text()
        assert "Give the event a name" in text
        assert "Choose the car" in text

    def test_filling_identity_clears_the_complaint_and_moves_on(self, page):
        page._next.click()
        _fill_identity(page)
        page._next.click()
        assert page.current_step() == 1
        assert page._issues.isVisibleTo(page) is False

    def test_no_regulation_can_ever_block_progress(self, page):
        """The whole point: rules are optional, so they can never stop the driver."""
        _fill_identity(page)
        page._next.click()
        page._next.click()          # format -> rules
        page._next.click()          # rules -> confirm, with nothing touched
        assert page.current_step() == 3


class TestFormatIsAChoiceNotAForm:
    def test_choosing_laps_shows_only_the_lap_field(self, page):
        _fill_identity(page)
        page._next.click()
        page._format._pick("lap")
        assert page._laps.isVisibleTo(page) is True
        assert page._mins.isVisibleTo(page) is False

    def test_choosing_timed_shows_only_the_minutes_field(self, page):
        _fill_identity(page)
        page._next.click()
        page._format._pick("timed")
        assert page._mins.isVisibleTo(page) is True
        assert page._laps.isVisibleTo(page) is False


class TestRulesAreFoldedAwayByDefault:
    def _to_rules(self, page):
        _fill_identity(page)
        page._next.click()
        page._next.click()
        return page

    def test_the_rules_body_starts_hidden(self, page):
        self._to_rules(page)
        assert page._rules_body.isVisibleTo(page) is False

    def test_a_standard_event_says_so_in_one_line(self, page):
        self._to_rules(page)
        assert "Standard rules" in page._rules_state.text()

    def test_opening_the_rules_is_an_explicit_choice(self, page):
        self._to_rules(page)
        page._btn_rules.setChecked(True)
        assert page._rules_body.isVisibleTo(page) is True
        assert "standard" in page._btn_rules.text().lower()

    def test_an_event_with_custom_rules_opens_them_and_states_them(self, page):
        page.set_draft(EventDraft(name="X", car="c", track="t")
                       .with_rule("tyre_wear", 4.0).with_rule("mandatory_stops", 1))
        page._next.click()
        page._next.click()
        assert page._btn_rules.isChecked() is True
        state = page._rules_state.text()
        assert "Tyres wear at 4x." in state
        assert "1 mandatory pit stop." in state


class TestConfirmReadsBackInPlainEnglish:
    def test_the_summary_is_a_sentence_not_a_field_list(self, page):
        _fill_identity(page)
        page._next.click()
        page._format._pick("timed")
        page._mins.setValue(120)
        page._next.click()
        page._next.click()
        assert page._summary.text() == (
            "A 120-minute race at Watkins Glen International in the Porsche Cayman GT4.")

    def test_saving_emits_the_completed_draft(self, page):
        seen = []
        page.save_requested.connect(seen.append)
        _fill_identity(page)
        page._next.click()
        page._format._pick("lap")
        page._laps.setValue(30)
        page._next.click()
        page._next.click()
        page._next.click()
        assert len(seen) == 1
        draft = seen[0]
        assert draft.name == "GR Enduro Rd2"
        assert draft.car == "Porsche Cayman GT4"
        assert draft.laps == 30
        assert draft.is_timed is False


class TestExistingEventsShareTheSameScreen:
    def test_the_list_is_hidden_when_there_are_none(self, page):
        page.set_existing_events([])
        assert page._existing_card.isVisibleTo(page) is False

    def test_known_events_are_offered_on_the_first_step(self, page):
        page.set_existing_events(["GR Enduro Rd1", "GR Enduro Rd2"])
        assert page._existing_card.isVisibleTo(page) is True
        assert page._existing.count() == 2

    def test_opening_one_asks_the_host_to_load_it(self, page):
        seen = []
        page.edit_requested.connect(seen.append)
        page.set_existing_events(["GR Enduro Rd1"])
        page._existing.setCurrentRow(0)
        page._btn_open.click()
        assert seen == ["GR Enduro Rd1"]


class TestRoundTrip:
    def test_an_existing_event_renders_into_the_controls(self, page):
        page.set_draft(EventDraft(name="GR Enduro Rd2", car="Porsche Cayman GT4",
                                  track="Watkins Glen International",
                                  race_type="timed", duration_mins=120)
                       .with_rule("tyre_wear", 4.0).with_rule("abs", False))
        assert page._name.text() == "GR Enduro Rd2"
        assert page._mins.value() == 120
        assert page._tyre_wear.value() == 4.0
        assert page._abs.isChecked() is False
        assert page.current_step() == 0        # editing starts at the beginning

    def test_the_draft_read_back_matches_what_is_shown(self, page):
        page.set_draft(EventDraft(name="X", car="c", track="t", race_type="timed",
                                  duration_mins=90))
        d = page.current_draft()
        assert d.name == "X" and d.is_timed and d.duration_mins == 90
        assert d.rules["tyre_wear"] == DEFAULT_RULES["tyre_wear"]

    def test_ticking_compounds_restricts_them_on_the_draft(self, page):
        _fill_identity(page)
        page._tyre_boxes["RM"].setChecked(True)
        page._tyre_boxes["RH"].setChecked(True)
        assert sorted(page.current_draft().rule("avail_tyres")) == ["RH", "RM"]

    def test_no_compounds_ticked_means_no_restriction(self, page):
        _fill_identity(page)
        assert page.current_draft().rule("avail_tyres") == []

    def test_wet_compounds_are_offered_too(self, page):
        """UAT-8: "in event setup not all tyre compounds are available for selection."
        A random-weather race needs Intermediate and Heavy Wet, which were missing."""
        assert "IM" in page._tyre_boxes and "HW" in page._tyre_boxes
        _fill_identity(page)
        page._tyre_boxes["RS"].setChecked(True)
        page._tyre_boxes["IM"].setChecked(True)
        page._tyre_boxes["HW"].setChecked(True)
        assert sorted(page.current_draft().rule("avail_tyres")) == ["HW", "IM", "RS"]
