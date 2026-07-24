"""Tests for the F0.5 component atoms (StatusPill, ConfidenceMeter, buttons, Card)."""

import pytest

from PyQt6.QtWidgets import QApplication, QLabel

from ui.components import (
    StatusPill, ConfidenceMeter, PrimaryActionButton, SecondaryActionButton,
    Card, SectionHeading,
)
from ui import ngr_theme as theme


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class TestStatusPill:
    def test_sets_text_tone_and_accessible_name(self, qapp):
        p = StatusPill("Applied", tone="success", glyph="✓")
        assert "Applied" in p.text()
        assert p.text().startswith("✓")
        assert p.tone == "success"
        # Colour is never the only signal: full label in tooltip + accessible name.
        assert p.toolTip() == "Applied"
        assert p.accessibleName() == "Applied"

    def test_unknown_tone_falls_back_to_neutral(self, qapp):
        p = StatusPill("x", tone="not-a-tone")
        assert p.tone == "neutral"

    def test_restyle_via_set_status(self, qapp):
        p = StatusPill("a", tone="neutral")
        p.set_status("Blocked", tone="warn", glyph="✕")
        assert "Blocked" in p.text()
        assert p.tone == "warn"


class TestConfidenceMeter:
    def test_levels_map_to_fill(self, qapp):
        assert ConfidenceMeter("high").value() == 100
        assert ConfidenceMeter("medium").value() == 66
        assert ConfidenceMeter("low").value() == 33
        assert ConfidenceMeter("unknown").value() == 0

    def test_unknown_key_defaults_and_labels(self, qapp):
        m = ConfidenceMeter("bogus")
        assert m.value() == 0
        assert "No evidence" in m._label.text()

    def test_set_level_updates(self, qapp):
        m = ConfidenceMeter("low")
        m.set_level("high")
        assert m.value() == 100
        assert m.level == "high"
        assert "High" in m._label.text()


class TestButtons:
    def test_primary_set_action(self, qapp):
        b = PrimaryActionButton()
        b.set_action("Begin Qualifying")
        assert b.text() == "Begin Qualifying"
        assert b.isEnabled() is True

    def test_blank_label_disables_and_hides(self, qapp):
        b = PrimaryActionButton("x")
        b.set_action("", enabled=True)
        assert b.isEnabled() is False
        assert b.isVisible() is False

    def test_disabled_flag_respected(self, qapp):
        b = PrimaryActionButton()
        b.set_action("Locked action", enabled=False)
        assert b.isEnabled() is False

    def test_secondary_constructs(self, qapp):
        b = SecondaryActionButton("More")
        b.set_action("Show reasoning")
        assert b.text() == "Show reasoning"


class TestCardAndHeading:
    def test_card_has_body_layout_and_add(self, qapp):
        c = Card()
        assert c.body is not None
        child = QLabel("hi")
        c.add(child)
        assert child.parent() is c

    def test_section_heading_text(self, qapp):
        h = SectionHeading("GARAGE", level=1)
        assert h.text() == "GARAGE"
        h.set_text("PRACTICE")
        assert h.text() == "PRACTICE"
