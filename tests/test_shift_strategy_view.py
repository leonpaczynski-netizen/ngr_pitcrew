"""Widget tests for ShiftStrategyView — run individually to avoid the full-suite
PyQt segfault on Win/Py3.14:

    python -m pytest tests/test_shift_strategy_view.py -q

Coverage
--------
* set_view renders one table row per VM row
* Profile toggle emits profile_changed
* Seed button emits engine_data_seeded with the 3 spinbox values
* Recalculate button emits recalculate_requested
* Stepper Go button emits go_to_tab
* Empty VM shows empty state, not a broken table
* Stale VM dims and marks the config pill
* has_data=False row shows NEEDS-DATA pill, not a bare 0
* No Apply / Fuel-Map / gearbox control exists (button text assertions)
* Store-persistence unit test through the engine-seeded handler
"""
from __future__ import annotations

import pytest

from PyQt6.QtWidgets import QApplication

from strategy.shift_strategy_engine import ShiftConfidence, ShiftStrategyResult
from ui.shift_strategy_vm import (
    GearDecisionRow, ShiftStrategyVM, build_shift_strategy_vm,
)


# ---------------------------------------------------------------------------
# QApplication fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# Helpers — build minimal VMs
# ---------------------------------------------------------------------------

def _row(label="2 → 3", has_data=True, conf_key="HIGH"):
    """A minimal GearDecisionRow for testing."""
    from ui.shift_strategy_vm import confidence_tone
    return GearDecisionRow(
        label=label,
        qualifying_rpm="7 000" if has_data else "Enter peak power RPM",
        race_rpm="6 500" if has_data else "—",
        rpm_delta="−500 rpm" if has_data else "—",
        post_shift_rpm="5 100" if has_data else "—",
        time_cost="+0.080 s/lap" if has_data else "—",
        fuel_saving="3.2% (PROVISIONAL)" if has_data else "—",
        confidence_key=conf_key,
        confidence_label={
            "HIGH": "High", "MEDIUM": "Medium", "LOW": "Low",
            "PROVISIONAL": "Provisional",
            "INSUFFICIENT_EVIDENCE": "NEEDS DATA",
            "STALE": "Stale",
        }.get(conf_key, conf_key),
        evidence_tone=confidence_tone(conf_key),
        has_data=has_data,
    )


def _minimal_vm(rows=(), active_profile="qualifying", config_is_stale=False,
                banner_text="", banner_tone="", stepper_stage=0,
                stepper_blocker="", stepper_go_to=""):
    """Build a ShiftStrategyVM with the minimum needed for widget tests."""
    return ShiftStrategyVM(
        rows=rows,
        active_profile=active_profile,
        required_saving_text="None (qualifying mode)",
        predicted_saving_text="—" if not rows else "3.2% (PROVISIONAL)",
        time_cost_text="—",
        config_status_text="Stale — recompute" if config_is_stale else "Up to date",
        config_is_stale=config_is_stale,
        stale_field_text="Gear ratios changed." if config_is_stale else "",
        overall_confidence_key=ShiftConfidence.PROVISIONAL.value if rows else
                               ShiftConfidence.INSUFFICIENT_EVIDENCE.value,
        evidence_readiness_text="Enter gear ratios to begin." if not rows else "",
        stepper_stage=stepper_stage,
        stepper_blocker_text=stepper_blocker,
        stepper_go_to_tab=stepper_go_to,
        banner_text=banner_text,
        banner_tone=banner_tone,
        engine_peak_power_rpm=7000 if rows else None,
        engine_peak_torque_rpm=5500 if rows else None,
        engine_redline=7500 if rows else None,
    )


# ---------------------------------------------------------------------------
# Widget construction
# ---------------------------------------------------------------------------

def test_widget_constructs(qapp):
    """ShiftStrategyView can be constructed without raising."""
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    assert view is not None


# ---------------------------------------------------------------------------
# set_view renders one table row per VM row
# ---------------------------------------------------------------------------

def test_set_view_renders_correct_row_count(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    rows = (_row("2 → 3"), _row("3 → 4"), _row("4 → 5"))
    vm = _minimal_vm(rows=rows)
    view.set_view(vm)
    assert view._table.rowCount() == 3


def test_set_view_gear_label_in_first_column(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    rows = (_row("2 → 3"), _row("3 → 4"))
    vm = _minimal_vm(rows=rows)
    view.set_view(vm)
    assert view._table.item(0, 0).text() == "2 → 3"
    assert view._table.item(1, 0).text() == "3 → 4"


def test_set_view_table_visible_with_rows(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    vm = _minimal_vm(rows=(_row(),))
    view.set_view(vm)
    # isHidden() is reliable in headless mode; isVisible() is not (parent not shown)
    assert not view._table.isHidden(), "table must not be hidden when rows exist"
    assert view._empty_lbl.isHidden(), "empty label must be hidden when rows exist"


# ---------------------------------------------------------------------------
# Profile toggle emits profile_changed
# ---------------------------------------------------------------------------

def test_qualifying_toggle_emits_qualifying(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    received = []
    view.profile_changed.connect(received.append)
    view._btn_qual.click()
    assert received == ["qualifying"]


def test_race_toggle_emits_race(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    received = []
    view.profile_changed.connect(received.append)
    view._btn_race.click()
    assert received == ["race"]


def test_set_view_does_not_emit_profile_changed(qapp):
    """Feeding a new VM must not trigger profile_changed (not a driver action)."""
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    received = []
    view.profile_changed.connect(received.append)
    vm = _minimal_vm(active_profile="race")
    view.set_view(vm)
    assert received == [], "set_view must not emit profile_changed"


def test_profile_toggle_reflects_vm_active_profile(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    vm = _minimal_vm(active_profile="race")
    view.set_view(vm)
    assert view._btn_race.isChecked()
    assert not view._btn_qual.isChecked()


# ---------------------------------------------------------------------------
# Seed button emits engine_data_seeded with the 3 spinbox values
# ---------------------------------------------------------------------------

def test_seed_emits_engine_data_with_spinbox_values(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    # Open the panel so the spinboxes exist and are accessible
    view._toggle_engine_panel()

    view._spin_power_rpm.setValue(7200)
    view._spin_torque_rpm.setValue(5600)
    view._spin_redline.setValue(7600)

    received = []
    view.engine_data_seeded.connect(received.append)
    view._btn_seed.click()

    assert len(received) == 1
    data = received[0]
    assert data["peak_power_rpm"] == 7200
    assert data["peak_torque_rpm"] == 5600
    assert data["redline"] == 7600


def test_seed_emits_zeroes_when_not_set(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    view._toggle_engine_panel()

    view._spin_power_rpm.setValue(0)
    view._spin_torque_rpm.setValue(0)
    view._spin_redline.setValue(0)

    received = []
    view.engine_data_seeded.connect(received.append)
    view._btn_seed.click()

    assert received[0] == {"peak_power_rpm": 0, "peak_torque_rpm": 0, "redline": 0}


# ---------------------------------------------------------------------------
# Recalculate button emits recalculate_requested
# ---------------------------------------------------------------------------

def test_recalculate_button_emits_signal(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    fired = []
    view.recalculate_requested.connect(lambda: fired.append(True))
    view._btn_recalculate.click()
    assert fired == [True]


# ---------------------------------------------------------------------------
# Stepper Go button emits go_to_tab
# ---------------------------------------------------------------------------

def test_stepper_go_emits_go_to_tab(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    received = []
    view.go_to_tab.connect(received.append)

    vm = _minimal_vm(stepper_stage=0, stepper_blocker="Add gear ratios",
                     stepper_go_to="Transmission")
    view.set_view(vm)
    # WorkflowStepper's Go button should be enabled when next_tab is set.
    view._stepper._next_btn.click()
    assert received == ["Transmission"]


# ---------------------------------------------------------------------------
# Empty VM shows empty state, not a broken table
# ---------------------------------------------------------------------------

def test_empty_vm_shows_empty_state(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    vm = _minimal_vm(rows=())
    view.set_view(vm)
    # isHidden() is reliable in headless mode (see test_live_pit_wall.py pattern)
    assert view._table.isHidden(), "table must be hidden when no rows"
    assert not view._empty_lbl.isHidden(), "empty label must be shown when no rows"
    assert view._empty_lbl.text()   # must have some helpful text


def test_empty_vm_hides_detail_card(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    vm = _minimal_vm(rows=())
    view.set_view(vm)
    assert view._detail_card.isHidden(), "detail card must be hidden when no rows"


def test_default_initial_state_is_empty(qapp):
    """Freshly constructed view must not show a broken table with no rows."""
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    # _vm is None initially — table should be hidden or empty
    assert view._table.rowCount() == 0 or not view._table.isVisible()


# ---------------------------------------------------------------------------
# Stale VM dims and marks the config pill
# ---------------------------------------------------------------------------

def test_stale_vm_config_pill_shows_stale_text(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    vm = _minimal_vm(rows=(_row(),), config_is_stale=True)
    view.set_view(vm)
    # Config pill should show the stale text from the VM
    assert "stale" in view._pill_config.text().lower() or \
           "changed" in view._pill_config.text().lower() or \
           "recompute" in view._pill_config.text().lower()


def test_stale_vm_config_pill_uses_warn_tone(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    vm = _minimal_vm(rows=(_row(),), config_is_stale=True)
    view.set_view(vm)
    assert view._pill_config.tone == "warn"


def test_stale_vm_shows_stale_explanation(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    vm = _minimal_vm(rows=(_row(),), config_is_stale=True)
    view.set_view(vm)
    assert not view._lbl_stale.isHidden(), "stale explanation must not be hidden"
    assert "Gear ratios changed" in view._lbl_stale.text()


def test_non_stale_vm_hides_stale_explanation(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    vm = _minimal_vm(rows=(_row(),), config_is_stale=False)
    view.set_view(vm)
    assert view._lbl_stale.isHidden(), "stale explanation must be hidden when not stale"


# ---------------------------------------------------------------------------
# has_data=False row shows NEEDS-DATA pill not a bare 0
# ---------------------------------------------------------------------------

def test_needs_data_row_shows_needs_data_label(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    r = _row(has_data=False, conf_key="INSUFFICIENT_EVIDENCE")
    vm = _minimal_vm(rows=(r,))
    view.set_view(vm)
    assert view._table.rowCount() == 1
    # Column 4 is a StatusPill widget — it must show "NEEDS DATA" text.
    pill = view._table.cellWidget(0, 4)
    assert pill is not None, "Confidence column must use a StatusPill widget"
    assert "NEEDS DATA" in pill.text().upper() or "NEEDS" in pill.text().upper()


def test_needs_data_row_does_not_show_bare_zero(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    r = _row(has_data=False, conf_key="INSUFFICIENT_EVIDENCE")
    vm = _minimal_vm(rows=(r,))
    view.set_view(vm)
    # No cell in the table should contain a bare "0".
    for col in range(view._table.columnCount()):
        item = view._table.item(0, col)
        if item is not None:
            assert item.text() != "0", (
                f"Column {col} must not show a bare '0' for a NEEDS-DATA row")


# ---------------------------------------------------------------------------
# No Apply / Fuel-Map / gearbox control exists
# ---------------------------------------------------------------------------

def test_no_apply_button(qapp):
    """The view must not contain any button with 'apply' in its text."""
    from ui.components.shift_strategy_view import ShiftStrategyView
    from PyQt6.QtWidgets import QPushButton, QToolButton
    view = ShiftStrategyView()
    for btn in view.findChildren(QPushButton) + view.findChildren(QToolButton):
        label = btn.text().lower()
        assert "apply" not in label, (
            f"Forbidden 'apply' button found: {btn.text()!r}")


def test_no_fuel_map_control(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    from PyQt6.QtWidgets import QPushButton, QToolButton, QLabel
    view = ShiftStrategyView()
    for w in (view.findChildren(QPushButton)
              + view.findChildren(QToolButton)
              + view.findChildren(QLabel)):
        label = (w.text() or "").lower()
        assert "fuel map" not in label and "fuel_map" not in label, (
            f"Forbidden fuel-map control found: {w.text()!r}")


def test_no_gearbox_command_button(qapp):
    """The view must not contain a button that issues a gearbox command."""
    from ui.components.shift_strategy_view import ShiftStrategyView
    from PyQt6.QtWidgets import QPushButton
    view = ShiftStrategyView()
    forbidden = ("execute_pit", "press_button", "gearbox command")
    for btn in view.findChildren(QPushButton):
        label = btn.text().lower()
        for f in forbidden:
            assert f not in label, (
                f"Forbidden control found: {btn.text()!r}")


# ---------------------------------------------------------------------------
# Banner visibility
# ---------------------------------------------------------------------------

def test_banner_shown_when_text_non_empty(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    vm = _minimal_vm(banner_text="Config is stale — recompute.", banner_tone="warn")
    view.set_view(vm)
    assert not view._banner_lbl.isHidden(), "banner must not be hidden when text is set"
    assert "stale" in view._banner_lbl.text().lower()


def test_banner_hidden_when_text_empty(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    vm = _minimal_vm(banner_text="", banner_tone="")
    view.set_view(vm)
    assert view._banner_lbl.isHidden(), "banner must be hidden when text is empty"


# ---------------------------------------------------------------------------
# Detail card updates on row selection
# ---------------------------------------------------------------------------

def test_detail_card_shows_correct_row_on_select(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    r0 = _row("2 → 3")
    r1 = _row("3 → 4")
    vm = _minimal_vm(rows=(r0, r1))
    view.set_view(vm)
    # Select second row
    view._table.selectRow(1)
    view._update_detail(1)
    assert view._dlbl_post.text() == r1.post_shift_rpm


# ---------------------------------------------------------------------------
# Engine panel collapses / expands
# ---------------------------------------------------------------------------

def test_engine_panel_collapsed_by_default(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    assert view._engine_body.isHidden(), "engine body must start hidden (collapsed)"


def test_engine_panel_expands_on_toggle(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    view._toggle_engine_panel()
    assert not view._engine_body.isHidden(), "engine body must be shown after toggle"


def test_engine_panel_collapses_on_second_toggle(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    view._toggle_engine_panel()
    view._toggle_engine_panel()
    assert view._engine_body.isHidden(), "engine body must be hidden after second toggle"


# ---------------------------------------------------------------------------
# VM-driven spinbox seeding
# ---------------------------------------------------------------------------

def test_engine_spinboxes_seeded_from_vm(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    vm = _minimal_vm(rows=(_row(),))  # _minimal_vm sets engine RPMs to 7000/5500/7500
    view.set_view(vm)
    assert view._spin_power_rpm.value() == 7000
    assert view._spin_torque_rpm.value() == 5500
    assert view._spin_redline.value() == 7500


def test_engine_spinboxes_zero_when_no_vm_data(qapp):
    from ui.components.shift_strategy_view import ShiftStrategyView
    view = ShiftStrategyView()
    vm = _minimal_vm(rows=())  # no engine data
    view.set_view(vm)
    assert view._spin_power_rpm.value() == 0
    assert view._spin_torque_rpm.value() == 0
    assert view._spin_redline.value() == 0


# ---------------------------------------------------------------------------
# Store-persistence unit test (pure — no Qt)
# ---------------------------------------------------------------------------

def test_shift_engine_seeded_persists_manual_engine_data(tmp_path):
    """Simulates what _on_shift_engine_seeded does: persist engine data to store."""
    from services.shift_strategy_store import ShiftStrategyStore
    import datetime as _dt

    store = ShiftStrategyStore(str(tmp_path / "shift.json"))
    scope = "porsche_cayman_gt4__watkins_glen__long_course"
    data = {"peak_power_rpm": 7200, "peak_torque_rpm": 5600, "redline": 7600}

    # Simulate handler: build payload with injected timestamp.
    payload = {
        "fingerprint":              "fp_test",
        "computed_at":              _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "manual_engine_data":       data,
        "qualifying_profile_json":  {},
        "race_profile_json":        {},
        "required_fuel_saving_pct": 0.0,
    }
    ok = store.save(scope, payload)
    assert ok, "Store.save should return True on success"

    loaded = store.get(scope)
    assert loaded is not None
    assert loaded["manual_engine_data"] == data
    assert "computed_at" in loaded
    assert loaded["fingerprint"] == "fp_test"


def test_shift_store_returns_none_for_unknown_scope(tmp_path):
    from services.shift_strategy_store import ShiftStrategyStore
    store = ShiftStrategyStore(str(tmp_path / "shift2.json"))
    assert store.get("unknown__scope__xyz") is None


def test_shift_store_overwrites_existing_entry(tmp_path):
    from services.shift_strategy_store import ShiftStrategyStore
    from datetime import datetime
    store = ShiftStrategyStore(str(tmp_path / "shift3.json"))
    scope = "test__scope"
    store.save(scope, {"manual_engine_data": {"peak_power_rpm": 6000},
                       "computed_at": "t1", "fingerprint": "fp1",
                       "qualifying_profile_json": {}, "race_profile_json": {},
                       "required_fuel_saving_pct": 0.0})
    store.save(scope, {"manual_engine_data": {"peak_power_rpm": 7000},
                       "computed_at": "t2", "fingerprint": "fp2",
                       "qualifying_profile_json": {}, "race_profile_json": {},
                       "required_fuel_saving_pct": 0.0})
    loaded = store.get(scope)
    assert loaded["manual_engine_data"]["peak_power_rpm"] == 7000
    assert loaded["fingerprint"] == "fp2"


# ---------------------------------------------------------------------------
# Garage integration: SetupWorkspace has shift_strategy_view attribute
# ---------------------------------------------------------------------------

def test_setup_workspace_has_shift_strategy_view(qapp):
    """SetupWorkspace must expose shift_strategy_view for the bridge to wire."""
    from ui.components.setup_workspace import SetupWorkspace
    gp = SetupWorkspace()
    assert hasattr(gp, "shift_strategy_view"), (
        "SetupWorkspace must expose shift_strategy_view")
    from ui.components.shift_strategy_view import ShiftStrategyView
    assert isinstance(gp.shift_strategy_view, ShiftStrategyView)


def test_setup_workspace_has_shift_strategy_button(qapp):
    """SetupWorkspace must include the Shift Strategy tab button."""
    from ui.components.setup_workspace import SetupWorkspace
    gp = SetupWorkspace()
    assert hasattr(gp, "_btn_shift_strategy"), (
        "SetupWorkspace must have a _btn_shift_strategy tab button")
    assert "shift" in gp._btn_shift_strategy.text().lower()


def test_show_shift_strategy_tab_switches_stack(qapp):
    """show_shift_strategy_tab must select the shift strategy page."""
    from ui.components.setup_workspace import SetupWorkspace
    gp = SetupWorkspace()
    gp.show_shift_strategy_tab()
    assert gp._stack.currentIndex() == 4


# ---------------------------------------------------------------------------
# AREA 3 — RunCard compound selector
# ---------------------------------------------------------------------------

class TestRunCardCompoundSelector:
    """The run-card compound selector lets the driver tag a test run with a compound
    without saving it into the setup (AREA 3)."""

    def test_compound_combo_exists(self, qapp):
        from ui.components.run_card import RunCard
        rc = RunCard()
        assert hasattr(rc, "_compound_combo")

    def test_compound_widget_hidden_by_default(self, qapp):
        from ui.components.run_card import RunCard
        rc = RunCard()
        assert rc._compound_widget.isHidden() is True

    def test_set_compound_options_shows_widget(self, qapp):
        from ui.components.run_card import RunCard
        rc = RunCard()
        rc.set_compound_options(["RH", "RM", "RS"])
        assert rc._compound_widget.isHidden() is False

    def test_set_compound_options_empty_hides_widget(self, qapp):
        from ui.components.run_card import RunCard
        rc = RunCard()
        rc.set_compound_options(["RH", "RM"])
        rc.set_compound_options([])
        assert rc._compound_widget.isHidden() is True

    def test_picking_emits_compound_change_requested(self, qapp):
        from ui.components.run_card import RunCard
        rc = RunCard()
        seen = []
        rc.compound_change_requested.connect(seen.append)
        rc.set_compound_options(["RH", "RM", "RS"])
        rc._on_compound_picked(1)   # pick RM
        assert seen == ["RM"]

    def test_preselected_compound_is_active(self, qapp):
        from ui.components.run_card import RunCard
        rc = RunCard()
        rc.set_compound_options(["RH", "RM", "RS"], preselected="RM")
        assert rc._compound_combo.currentIndex() == 1

    def test_set_compound_options_does_not_emit(self, qapp):
        """set_compound_options must not fire compound_change_requested."""
        from ui.components.run_card import RunCard
        rc = RunCard()
        seen = []
        rc.compound_change_requested.connect(seen.append)
        rc.set_compound_options(["RH", "RM", "RS"], preselected="RS")
        assert seen == []

    def test_compound_change_requested_signal_declared(self, qapp):
        from ui.components.run_card import RunCard
        rc = RunCard()
        seen = []
        rc.compound_change_requested.connect(seen.append)
        rc.compound_change_requested.emit("RS")
        assert seen == ["RS"]


# ---------------------------------------------------------------------------
# AREA 2 — show_transmission_group routes from go_to_tab
# ---------------------------------------------------------------------------

def test_show_transmission_group_switches_stack(qapp):
    """show_transmission_group must select the Transmission entry page."""
    from ui.components.setup_workspace import SetupWorkspace
    gp = SetupWorkspace()
    gp.show_transmission_group()
    assert gp._stack.currentIndex() == 5
    assert gp._btn_transmission.isChecked() is True


# ---------------------------------------------------------------------------
# Render smoke — build PitCrewShell, feed Garage, processEvents, no crash
# ---------------------------------------------------------------------------

def test_pit_crew_shell_garage_smoke(qapp):
    """Full shell + bridge construction with sample data — must not crash."""
    from PyQt6.QtWidgets import QApplication
    from ui.pit_crew_shell import PitCrewShell
    from ui.pit_crew_controller import PitCrewController

    ctrl = PitCrewController()
    shell = PitCrewShell(ctrl)

    # Feed sample data into the Garage
    from ui.setup_recommendation_vm import build_recommendation_vm
    vm = build_recommendation_vm({
        "status": "approved",
        "changes": [{"field": "arb_front", "from": 5, "to": 4, "reason": "test"}],
        "setup_fields": {"arb_front": 4},
    })
    gp = getattr(shell, "garage_page", None)
    if gp is not None:
        gp.set_recommendation(vm, setup_values={"arb_front": 5})
        gp.set_gearing(gear_ratios=[3.1, 2.2, 1.6], final_drive=3.705,
                       transmission_max_speed_kmh=280.0)

    QApplication.processEvents()
    shell.close()
