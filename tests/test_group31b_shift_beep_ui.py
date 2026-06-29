"""
Group C (frontend) — shift indicator / RPM beep UI wiring.

Covers the dashboard + setup-builder UI side of the shift-beep feature:
- Live-tab shift-beep settings persist to config["shift_beep"] and mirror to the
  read-only Setup spinboxes.
- Live mode change writes the shared _live_mode_ref snapshot (read by on_packet).
- Setup-tab session-type change writes the _practice_is_qual_ref snapshot.
- Setup spinboxes are made read-only and no longer self-persist via _save_settings.
- The AI setup-apply path writes BOTH shift_rpm_qual and shift_rpm_race to the
  Setup + Live spinboxes and config (overwriting).

These tests use types.MethodType to bind the real methods to lightweight stubs
(no QApplication) plus source-scan assertions for structural guarantees — the
same patterns used by the existing group tests. No audio is played.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui import dashboard as _dash_mod
from ui import setup_builder_ui as _sbu_mod

DASH_SRC = (ROOT / "ui" / "dashboard.py").read_text(encoding="utf-8")
SBU_SRC = (ROOT / "ui" / "setup_builder_ui.py").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# _on_shift_beep_setting_changed — persistence + mirror to Setup spinboxes
# ---------------------------------------------------------------------------
class TestShiftBeepSettingChanged:
    def _make_stub(self, *, enabled=True, qual=7100, race=6600):
        stub = MagicMock()
        stub._config = {}
        stub._chk_shift_beep_enabled.isChecked.return_value = enabled
        stub._spin_live_shift_rpm_qual.value.return_value = qual
        stub._spin_live_shift_rpm_race.value.return_value = race
        stub._on_shift_beep_setting_changed = types.MethodType(
            _dash_mod.MainWindow._on_shift_beep_setting_changed, stub
        )
        return stub

    def test_persists_all_three_values_to_config(self):
        stub = self._make_stub(enabled=True, qual=7100, race=6600)
        stub._on_shift_beep_setting_changed()
        sb = stub._config["shift_beep"]
        assert sb["enabled"] is True
        assert sb["qual_rpm"] == 7100
        assert sb["race_rpm"] == 6600

    def test_calls_persist_config(self):
        stub = self._make_stub()
        stub._on_shift_beep_setting_changed()
        stub._persist_config.assert_called_once()

    def test_disabled_flag_persisted(self):
        stub = self._make_stub(enabled=False)
        stub._on_shift_beep_setting_changed()
        assert stub._config["shift_beep"]["enabled"] is False

    def test_mirrors_values_to_readonly_setup_spinboxes(self):
        stub = self._make_stub(qual=7100, race=6600)
        stub._on_shift_beep_setting_changed()
        stub._spin_shift_rpm_qual.setValue.assert_called_with(7100)
        stub._spin_shift_rpm_race.setValue.assert_called_with(6600)

    def test_mirror_uses_blocksignals_to_avoid_reentrancy(self):
        stub = self._make_stub()
        stub._on_shift_beep_setting_changed()
        # blockSignals(True) then (False) around the setValue on each setup spinbox
        assert stub._spin_shift_rpm_qual.blockSignals.call_count >= 2
        assert stub._spin_shift_rpm_race.blockSignals.call_count >= 2


# ---------------------------------------------------------------------------
# _on_setup_type_changed — writes _practice_is_qual_ref under the shared lock
# ---------------------------------------------------------------------------
class TestSetupTypePracticeRef:
    def _make_stub(self):
        stub = MagicMock()
        stub._practice_is_qual_ref = [None]
        stub._on_setup_type_changed = types.MethodType(
            _sbu_mod.SetupBuilderMixin._on_setup_type_changed, stub
        )
        return stub

    def test_qualifying_setup_sets_true(self):
        stub = self._make_stub()
        stub._on_setup_type_changed("Q — Qualifying Setup")
        assert stub._practice_is_qual_ref[0] is True

    def test_race_setup_sets_false(self):
        stub = self._make_stub()
        stub._on_setup_type_changed("R — Race Setup")
        assert stub._practice_is_qual_ref[0] is False

    def test_missing_ref_is_safe(self):
        # No _practice_is_qual_ref attribute -> must not raise (hasattr guard)
        stub = MagicMock(spec=[])  # spec=[] -> hasattr returns False for the ref
        bound = types.MethodType(
            _sbu_mod.SetupBuilderMixin._on_setup_type_changed, stub
        )
        bound("Qualifying")  # should not raise


# ---------------------------------------------------------------------------
# Source-scan structural guarantees
# ---------------------------------------------------------------------------
class TestStructuralGuarantees:
    def test_setup_spinboxes_made_readonly(self):
        assert "_set_spin_readonly(self._spin_shift_rpm_qual, True)" in SBU_SRC
        assert "_set_spin_readonly(self._spin_shift_rpm_race, True)" in SBU_SRC

    def test_setup_spinboxes_no_longer_self_persist(self):
        # The old editable wiring (valueChanged -> _save_settings) must be gone now
        # that the Setup spinboxes are read-only and the Live tab is the source.
        assert "_spin_shift_rpm_qual.valueChanged" not in SBU_SRC
        assert "_spin_shift_rpm_race.valueChanged" not in SBU_SRC

    def test_live_mode_change_writes_mode_ref(self):
        assert "_live_mode_ref[0] = mode" in DASH_SRC

    def test_setup_type_signal_connected(self):
        assert "self._setup_type.currentTextChanged.connect(self._on_setup_type_changed)" in SBU_SRC

    def test_ai_apply_uses_both_shift_rpm_fields(self):
        assert "shift_rpm_qual" in SBU_SRC
        assert "shift_rpm_race" in SBU_SRC

    def test_ai_apply_writes_live_spinboxes(self):
        assert "_spin_live_shift_rpm_qual" in SBU_SRC
        assert "_spin_live_shift_rpm_race" in SBU_SRC

    def test_live_tab_has_enable_toggle_and_spinboxes(self):
        assert "_chk_shift_beep_enabled" in DASH_SRC
        assert "_spin_live_shift_rpm_qual" in DASH_SRC
        assert "_spin_live_shift_rpm_race" in DASH_SRC


# ---------------------------------------------------------------------------
# Startup sync of the shift-RPM mode/setup-type snapshots (validator C1/I3) and
# split-value history persistence (validator I1).
# ---------------------------------------------------------------------------
class TestStartupSyncAndHistory:
    MAIN_SRC = (ROOT / "main.py").read_text(encoding="utf-8")

    def test_live_mode_snapshot_synced_to_persisted_mode_at_startup(self):
        # After ref injection, before the listener starts, the live-mode snapshot
        # must be seeded from the persisted config mode (default "Race") so early
        # packets use the correct threshold (not the module default "Qualifying").
        assert '_live_mode_snap[0] = config.get("live", {}).get("mode", "Race")' in self.MAIN_SRC

    def test_practice_is_qual_synced_from_setup_type_at_startup(self):
        # Practice threshold must follow the restored Setup-tab session type at
        # startup, not the module default False.
        assert "_practice_is_qual[0] =" in self.MAIN_SRC
        assert "_setup_type.currentText()" in self.MAIN_SRC

    def test_history_save_includes_split_shift_rpm_fields(self):
        # The AI build-history entry must persist both split values (not just the
        # legacy single shift_rpm) so format_for_prompt feeds the AI the right data.
        assert '"shift_rpm_qual": getattr(rec, "shift_rpm_qual", 0)' in SBU_SRC
        assert '"shift_rpm_race": getattr(rec, "shift_rpm_race", 0)' in SBU_SRC
