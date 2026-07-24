"""Tests for the Engineer Guidance VM + card (F0.5/F1).

The VM must map the real Event Command Centre dict faithfully, never fabricate
certainty, and never hide warnings. The card must render it and emit the right
signals — and cannot invent an action the VM didn't carry.
"""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.components.guidance_vm import EngineerGuidanceVM
from ui.components.guidance_card import EngineerGuidanceCard


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _cc_view(**over):
    base = {
        "ok": True,
        "next_action": {
            "category": "lock_setup", "headline": "Lock the qualifying setup",
            "detail": "Convergence is stable across the last 3 runs.",
            "target_surface": "setup", "tone": "info",
        },
        "progress": {
            "valid_laps": 42, "practice_sessions": 3, "setup_experiments": 2,
            "tyre_samples": 0, "fuel_samples": 0, "race_simulations": 0,
            "setup_confidence": "high", "strategy_maturity": "developing",
        },
        "attention": [
            {"kind": "risk", "message": "Rear tyres graining after lap 6", "tone": "warn"},
            {"kind": "info", "message": "ignore me", "tone": "info"},
        ],
        "quick_actions": [
            {"label": "Open Practice", "target_surface": "practice"},
        ],
    }
    base.update(over)
    return base


class TestGuidanceVM:
    def test_maps_command_centre_faithfully(self):
        vm = EngineerGuidanceVM.from_command_centre(_cc_view())
        assert vm.objective == "Lock the qualifying setup"
        assert vm.primary_action_label == "Lock the qualifying setup"
        assert vm.primary_action_surface == "setup"
        assert "Convergence is stable" in vm.message
        assert vm.evidence_summary.startswith("3 practice sessions")
        assert "42 valid laps" in vm.evidence_summary
        assert vm.confidence_level == "high"

    def test_warnings_are_never_hidden(self):
        vm = EngineerGuidanceVM.from_command_centre(_cc_view())
        assert vm.warnings == ("Rear tyres graining after lap 6",)  # only warn/danger

    def test_secondary_is_a_non_primary_quick_action(self):
        vm = EngineerGuidanceVM.from_command_centre(_cc_view())
        assert vm.secondary_action_surface == "practice"

    def test_missing_confidence_stays_unknown(self):
        v = _cc_view()
        v["progress"]["setup_confidence"] = ""
        vm = EngineerGuidanceVM.from_command_centre(v)
        assert vm.confidence_level == "unknown"

    def test_convergence_states_map_to_confidence(self):
        """UAT-8: "right menu isn't updating properly." setup_confidence carries the
        setup CONVERGENCE state ("lock_ready", "improving", …); none of those words is
        "high"/"developing", so a lock-ready setup showed "No evidence"."""
        cases = {"lock_ready": "high", "locked": "high", "ready_for_confirmation": "high",
                 "improving": "medium", "provisional": "medium",
                 "exploring": "low", "insufficient_evidence": "low"}
        for state, expected in cases.items():
            v = _cc_view()
            v["progress"]["setup_confidence"] = state
            assert EngineerGuidanceVM.from_command_centre(v).confidence_level == expected, state

    def test_empty_or_bad_view_falls_back(self):
        # Active Event was folded into Home, so the empty-state CTA routes to Home.
        assert EngineerGuidanceVM.from_command_centre(None).primary_action_surface == "home"
        assert EngineerGuidanceVM.from_command_centre({"ok": False}).objective.startswith("Create or select")
        assert EngineerGuidanceVM.from_command_centre("garbage").primary_action_surface == "home"


class TestGuidanceCard:
    def test_renders_and_emits_primary_surface(self, qapp):
        card = EngineerGuidanceCard()
        card.set_vm(EngineerGuidanceVM.from_command_centre(_cc_view()))
        seen = []
        card.primary_requested.connect(lambda s: seen.append(s))
        card._primary.click()
        assert seen == ["setup"]

    def test_read_aloud_emits_text(self, qapp):
        card = EngineerGuidanceCard()
        card.set_vm(EngineerGuidanceVM.from_command_centre(_cc_view()))
        seen = []
        card.read_aloud_requested.connect(lambda t: seen.append(t))
        card._read_btn.click()
        assert seen and "Lock the qualifying setup" in seen[0]

    def test_warning_visible_when_present(self, qapp):
        # isHidden() reflects the setVisible() flag without needing a shown window.
        card = EngineerGuidanceCard()
        card.set_vm(EngineerGuidanceVM.from_command_centre(_cc_view()))
        assert card._warnings.isHidden() is False
        assert "graining" in card._warnings.text()

    def test_no_warning_hidden_when_absent(self, qapp):
        v = _cc_view(attention=[])
        card = EngineerGuidanceCard()
        card.set_vm(EngineerGuidanceVM.from_command_centre(v))
        assert card._warnings.isHidden() is True

    def test_set_vm_defensive_against_garbage(self, qapp):
        card = EngineerGuidanceCard()
        card.set_vm("not a vm")  # must not raise; falls back to empty
        assert card._primary.text() != ""

    def test_expander_toggles_explanation(self, qapp):
        # explanation present only when detail differs from message; here message
        # equals detail, so force a VM with an explanation.
        vm = EngineerGuidanceVM(
            message="short", objective="Do X", primary_action_label="Do X",
            primary_action_surface="garage", explanation="Because of the evidence trail.",
        )
        card = EngineerGuidanceCard()
        card.set_vm(vm)
        assert card._expander.isHidden() is False
        assert card._explanation.isHidden() is True
        card._expander.setChecked(True)
        assert card._explanation.isHidden() is False
