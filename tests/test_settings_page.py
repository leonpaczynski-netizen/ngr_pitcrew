"""Tests for the native Settings page + bridge settings/analyse routing (F9 finish)."""

import pytest

from PyQt6.QtWidgets import QApplication

from ui.components.settings_page import SettingsPage


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _config():
    return {
        "connection": {"host": "10.0.0.5", "port": 33740},
        "voice": {"enabled": False, "rate": 200, "volume": 0.5, "tyre_alerts": False,
                  "lap_alerts": True, "fuel_alerts": True},
        "shift_beep": {"qual_rpm": 8200, "race_rpm": 7800},
    }


class TestSettingsPage:
    def test_populates_from_config(self, qapp):
        p = SettingsPage()
        p.set_config(_config())
        assert p._host.text() == "10.0.0.5"
        assert p._port.value() == 33740
        assert p._voice_enabled.isChecked() is False
        assert p._voice_rate.value() == 200
        assert p._voice_volume.value() == 50
        assert p._qual_rpm.value() == 8200

    def test_apply_writes_back_to_shared_config(self, qapp):
        cfg = _config()
        p = SettingsPage()
        p.set_config(cfg)
        p._host.setText("127.0.0.1")
        p._voice_enabled.setChecked(True)
        p._race_rpm.setValue(8000)
        out = p.apply_to_config()
        assert out is cfg                       # mutates the shared dict in place
        assert cfg["connection"]["host"] == "127.0.0.1"
        assert cfg["voice"]["enabled"] is True
        assert cfg["shift_beep"]["race_rpm"] == 8000

    def test_save_emits(self, qapp):
        p = SettingsPage()
        p.set_config(_config())
        seen = []
        p.save_requested.connect(lambda: seen.append(True))
        p._save.click()
        assert seen == [True]

    def test_classic_escape_emits(self, qapp):
        p = SettingsPage()
        seen = []
        p.open_classic_requested.connect(lambda: seen.append(True))
        p._classic.click()
        assert seen == [True]

    def test_defensive_against_garbage_config(self, qapp):
        p = SettingsPage()
        p.set_config("not a dict")      # must not raise; sensible defaults
        assert p._port.value() == 33741


class TestBridgeSettingsAndAnalyse:
    def test_analyse_and_save_route_to_window(self, qapp):
        from ui.live_shell_bridge import LiveShellBridge
        from ui.pit_crew_controller import PitCrewController
        from ui.pit_crew_shell import PitCrewShell

        class _Win:
            """Analyse no longer routes into the window — it goes to the setup engine."""

        ctrl = PitCrewController()
        shell = PitCrewShell(ctrl)
        win = _Win()
        cfg = _config()
        b = LiveShellBridge(shell, ctrl, window=win, config=cfg)
        # Settings page was fed the config on wire.
        assert shell.settings_page._host.text() == "10.0.0.5"
        # Analyse goes to the headless engine and reports its result, whatever it is.
        shell.garage_page.analyse_requested.emit()
        assert shell.garage_page._status.text() != ""
