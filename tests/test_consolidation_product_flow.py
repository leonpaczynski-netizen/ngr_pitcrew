"""Product Consolidation Sprint — tests for ui/product_flow.py and the safe
first-pass UI clean-up.

Two kinds of tests, both following the project's no-Qt convention:
  1. Pure unit tests of ui.product_flow (imported directly — it has no PyQt6).
  2. Source-scan tests that the dashboard / track-modelling UI wiring changed as
     intended (no QApplication required).
"""

import re
from pathlib import Path

import pytest

from ui import product_flow as pf


ROOT = Path(__file__).parent.parent


def _method_body(src: str, name: str) -> str:
    m = re.search(rf"\n    def {name}\(.*?(?=\n    def |\n(?:class |# ---)|\Z)",
                  src, re.DOTALL)
    assert m, f"method {name} not found"
    return m.group(0)


@pytest.fixture(scope="module")
def dash_src():
    return (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tm_src():
    return (ROOT / "ui" / "track_modelling_ui.py").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Tab classification
# --------------------------------------------------------------------------- #
class TestTabRoles:
    def test_core_workflow_tabs(self):
        wf = set(pf.workflow_tabs())
        for name in [
            "Live Race Engineer", "Event Planner", "Garage", "Setup Builder",
            "Practice Review", "Strategy Builder", "History",
        ]:
            assert name in wf, f"{name} should be a workflow tab"

    def test_diagnostic_tabs_are_exactly_the_tools(self):
        assert set(pf.diagnostic_tabs()) == {
            "Telemetry", "Diagnostics", "AI Log", "Track Modelling",
        }

    def test_support_tabs(self):
        # Guide tab removed (folded into Home) in the post-UAT overhaul.
        assert set(pf.support_tabs()) == {"Settings"}

    def test_is_diagnostic_tab(self):
        assert pf.is_diagnostic_tab("Track Modelling") is True
        assert pf.is_diagnostic_tab("AI Log") is True
        assert pf.is_diagnostic_tab("Event Planner") is False
        assert pf.is_diagnostic_tab("Setup Builder") is False

    def test_unknown_tab_defaults_to_workflow_never_diagnostic(self):
        # A newly added tab must never be silently treated as a hidden tool.
        assert pf.tab_role("Brand New Tab") == pf.ROLE_WORKFLOW
        assert pf.is_diagnostic_tab("Brand New Tab") is False

    def test_debug_tab_renamed_diagnostics_only(self):
        # The old "Debug" title is no longer a known tab.
        assert "Debug" not in pf.TAB_ROLES
        assert pf.TAB_ROLES["Diagnostics"] == pf.ROLE_DIAGNOSTIC


# --------------------------------------------------------------------------- #
# Tab-title decoration
# --------------------------------------------------------------------------- #
class TestDecorateTabTitle:
    def test_diagnostic_tabs_get_prefix(self):
        for name in pf.diagnostic_tabs():
            out = pf.decorate_tab_title(name)
            assert out.startswith(pf.DIAGNOSTIC_TAB_PREFIX)
            assert out.endswith(name)

    def test_workflow_tabs_unchanged(self):
        for name in pf.workflow_tabs() + pf.support_tabs():
            assert pf.decorate_tab_title(name) == name

    def test_idempotent_no_double_prefix(self):
        once = pf.decorate_tab_title("Track Modelling")
        twice = pf.decorate_tab_title(once)
        assert once == twice
        assert twice.count(pf.DIAGNOSTIC_TAB_PREFIX) == 1

    def test_classification_is_prefix_insensitive(self):
        decorated = pf.decorate_tab_title("Telemetry")
        assert pf.is_diagnostic_tab(decorated) is True
        assert pf.tab_role(decorated) == pf.ROLE_DIAGNOSTIC


# --------------------------------------------------------------------------- #
# The journey
# --------------------------------------------------------------------------- #
class TestProductJourney:
    def test_has_thirteen_ordered_steps(self):
        assert len(pf.PRODUCT_JOURNEY) == 13
        assert [s["step"] for s in pf.PRODUCT_JOURNEY] == [str(i) for i in range(1, 14)]

    def test_every_step_points_at_a_known_tab(self):
        for s in pf.PRODUCT_JOURNEY:
            assert s["tab"] in pf.TAB_ROLES, f"step {s['step']} → unknown tab {s['tab']}"

    def test_journey_only_uses_workflow_tabs(self):
        for s in pf.PRODUCT_JOURNEY:
            assert pf.tab_role(s["tab"]) == pf.ROLE_WORKFLOW, (
                f"journey step {s['step']} routes to non-workflow tab {s['tab']}"
            )


# --------------------------------------------------------------------------- #
# Flow-state summary / next action
# --------------------------------------------------------------------------- #
class TestFlowStateSummary:
    def test_empty_state_first_action_is_create_event(self):
        s = pf.build_flow_state_summary()
        assert s["complete"] is False
        assert s["next_tab"] == "Event Planner"
        assert "event" in s["next_action"].lower()
        assert s["ready"] == []

    def test_event_set_next_is_car_track(self):
        s = pf.build_flow_state_summary(has_event=True)
        assert s["next_tab"] == "Event Planner"
        assert "car" in s["next_action"].lower() or "track" in s["next_action"].lower()

    def test_car_alone_does_not_satisfy_car_track_gate(self):
        # has_car_track needs BOTH car and track.
        s = pf.build_flow_state_summary(has_event=True, has_car=True)
        assert "track" in s["next_action"].lower() or "car" in s["next_action"].lower()
        assert s["complete"] is False

    def test_car_and_track_advances_to_tuning(self):
        s = pf.build_flow_state_summary(has_event=True, has_car=True, has_track=True)
        assert "tuning" in s["next_action"].lower()
        assert s["next_tab"] == "Setup Builder"

    def test_next_action_is_first_unmet_gate(self):
        s = pf.build_flow_state_summary(
            has_event=True, has_car=True, has_track=True, tuning_confirmed=True,
        )
        assert "practice" in s["next_action"].lower()
        assert s["next_tab"] == "Live Race Engineer"

    def test_ready_and_pending_partition_all_gates(self):
        s = pf.build_flow_state_summary(has_event=True, has_car=True, has_track=True)
        # 8 gates total; ready + pending must cover them with no overlap.
        assert len(s["ready"]) + len(s["pending"]) == 8
        assert set(s["ready"]).isdisjoint(set(s["pending"]))

    def test_all_gates_met_is_complete_and_points_to_history(self):
        s = pf.build_flow_state_summary(
            has_event=True, has_car=True, has_track=True, tuning_confirmed=True,
            has_practice_laps=True, has_valid_laps=True, has_setup=True,
            has_strategy=True, live_active=True,
        )
        assert s["complete"] is True
        assert s["next_tab"] == "History"
        assert s["pending"] == []

    def test_complete_and_learning_saved_has_nothing_outstanding(self):
        s = pf.build_flow_state_summary(
            has_event=True, has_car=True, has_track=True, tuning_confirmed=True,
            has_practice_laps=True, has_valid_laps=True, has_setup=True,
            has_strategy=True, live_active=True, learning_saved=True,
        )
        assert s["complete"] is True
        assert "complete" in s["next_action"].lower()

    def test_never_raises_on_defaults(self):
        # Pure/defensive: must produce a dict with the documented keys.
        s = pf.build_flow_state_summary()
        for key in ("ready", "pending", "next_action", "next_tab", "complete"):
            assert key in s


# --------------------------------------------------------------------------- #
# Source-scan: dashboard wiring
# --------------------------------------------------------------------------- #
class TestDashboardWiring:
    def test_debug_tab_renamed_to_diagnostics(self, dash_src):
        line = next(l for l in dash_src.splitlines() if "_build_debug_tab(" in l and "addTab" in l)
        assert '"Diagnostics"' in line
        assert '"Debug"' not in line

    def test_applies_product_flow_tab_markers(self, dash_src):
        assert "_apply_product_flow_tab_markers" in dash_src
        assert "from ui import product_flow" in dash_src

    def test_tab_indices_preserved(self, dash_src):
        # Home Dashboard Promotion (2026-07-03): Home leads at index 0, so the
        # tool tabs shifted down one — Track Modelling index 13, AI Log index 12.
        assert 'self._build_track_modelling_tab(), "Track Modelling")  # 12' in dash_src
        assert '"AI Log")           # 11' in dash_src


# --------------------------------------------------------------------------- #
# Source-scan: track-modelling clarity renames
# --------------------------------------------------------------------------- #
class TestTrackModellingRenames:
    def test_resolver_status_renamed(self, tm_src):
        assert 'QGroupBox("Track Model Status")' in tm_src
        assert 'QGroupBox("Resolver Status")' not in tm_src

    def test_section5_renamed_from_misleading_alignment_title(self, tm_src):
        assert 'QGroupBox("5. Seed Geometry")' in tm_src
        assert 'QGroupBox("5. Track Model Alignment")' not in tm_src

    def test_corner_verify_api_key_not_read_from_nonexistent_ai_section(self, tm_src):
        # Field-consistency fix: the AI corner-verify key must come from the
        # editable field / config["anthropic"], never config["ai"] (which never
        # exists, so the old read always yielded an empty key).
        assert 'self._config.get("ai", {}).get("api_key"' not in tm_src
        assert "self._ai_api_key.text().strip()" in tm_src

    def test_accept_exports_reviewed_segments(self, tm_src):
        # The Accept button must write the reviewed-segments file — without it the
        # track stays seed-only / not AI-ready no matter how good the alignment
        # (the Fuji UAT case). It must also re-resolve so the status flips.
        body = _method_body(tm_src, "_tm_accept_track_model")
        assert "export_review_json" in body, "Accept must export the reviewed segments"
        assert "_tm_refresh_resolver" in body, "Accept must re-resolve the model status"

    def test_accept_not_gated_on_unrelated_seed_geometry(self, tm_src):
        # Accept enables on alignment quality alone; the old extra seed_available
        # requirement forced an unrelated 'Generate Seed Geometry' workflow.
        assert 'states.get("accept", False) and seed_available' not in tm_src
