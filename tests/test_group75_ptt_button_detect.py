"""UAT Finding 5 — PTT button-detection repair (Remediation Group 75).

Root cause: after the Settings tab was extracted into ``ui/settings_ui.py``
(decomposition slice 2), ``_on_detect_ptt_button`` still referenced the bare
name ``_ButtonDetectDialog``, which only existed in the ``ui.dashboard`` module
namespace. Clicking "Detect Button…" raised
``NameError: name '_ButtonDetectDialog' is not defined`` and crashed Settings.

The fix makes the dialog a single canonical module
(``ui.button_detect_dialog``) imported by both surfaces, and splits the handler
into a testable factory + apply step. These tests drive the real settings-UI
handler (``MainWindow._on_detect_ptt_button``) with a non-blocking fake dialog,
plus a direct test of the dialog's disconnect resilience.

Covers required tests 19–23:
  19. ``_on_detect_ptt_button`` opens the real detection dialog without exception.
  20. Cancelling PTT detection does not change the binding.
  21. No controller connected produces a safe message.
  22. A detected wheel button persists and restores.
  23. Controller disconnect during detection does not crash.
"""
from __future__ import annotations

import os
import queue
from unittest.mock import MagicMock

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 not available for headless UI test")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication  # noqa: E402

import config_paths as cp  # noqa: E402


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    cfg_path = str(tmp_path / "config.json")
    cp.write_default_config(cfg_path)
    config = cp.load_config(cfg_path)
    from ui.dashboard import MainWindow, SignalBridge
    win = MainWindow(
        config=config,
        logger=MagicMock(),
        announcer=MagicMock(),
        bridge=SignalBridge(),
        ui_queue=queue.Queue(),
        config_path=cfg_path,
        db=None,
    )
    # The detect handler pauses/restarts the live keyboard listener; there is no
    # real listener in a headless test.
    win._query_listener = None
    yield win
    win.close()


class _FakeDetectDialog:
    """Non-blocking stand-in for ButtonDetectDialog.

    Exercises the real MainWindow handler path without opening a modal window
    or touching real input devices.
    """
    def __init__(self, *, detected=None, accepted=True, joystick_available=True):
        self.detected_binding = detected or {}
        self._accepted = accepted
        self.joystick_available = joystick_available
        self.exec_called = False

    def exec(self):
        self.exec_called = True
        # QDialog.Accepted == 1, Rejected == 0
        return 1 if self._accepted else 0


# --------------------------------------------------------------------------- #
# Test 19 — opens the real detection dialog without exception
# --------------------------------------------------------------------------- #

def test_detect_handler_runs_without_exception(window):
    """Regression for the NameError crash: the handler resolves and invokes the
    canonical dialog via the factory and completes cleanly."""
    fake = _FakeDetectDialog(accepted=False)  # user cancels
    window._make_button_detect_dialog = lambda: fake

    window._on_detect_ptt_button()  # must not raise

    assert fake.exec_called, "handler never opened the detection dialog"


def test_factory_returns_canonical_dialog_class(window, monkeypatch):
    """The production factory returns the one canonical ButtonDetectDialog and
    does not spawn input threads under test."""
    from ui.button_detect_dialog import ButtonDetectDialog
    monkeypatch.setattr(ButtonDetectDialog, "__init__",
                        lambda self, parent=None, **kw: None, raising=True)
    dlg = window._make_button_detect_dialog()
    assert isinstance(dlg, ButtonDetectDialog)


# --------------------------------------------------------------------------- #
# Test 20 — cancelling detection does not change the binding
# --------------------------------------------------------------------------- #

def test_cancel_does_not_change_binding(window):
    window._config["query_button"] = {"type": "keyboard", "key": "f8"}
    fake = _FakeDetectDialog(accepted=False, detected={"type": "keyboard", "key": "x"})
    window._make_button_detect_dialog = lambda: fake

    window._on_detect_ptt_button()

    assert window._config["query_button"] == {"type": "keyboard", "key": "f8"}


def test_timeout_with_no_binding_leaves_binding(window):
    window._config["query_button"] = {"type": "joystick", "button_index": 3}
    fake = _FakeDetectDialog(accepted=True, detected={})  # accepted but nothing detected
    window._make_button_detect_dialog = lambda: fake

    window._on_detect_ptt_button()

    assert window._config["query_button"] == {"type": "joystick", "button_index": 3}


# --------------------------------------------------------------------------- #
# Test 21 — no controller connected produces a safe message
# --------------------------------------------------------------------------- #

def test_no_controller_shows_safe_message(window):
    messages = []
    window._show_ptt_message = lambda text, **kw: messages.append(text)
    fake = _FakeDetectDialog(accepted=False, detected={}, joystick_available=False)
    window._make_button_detect_dialog = lambda: fake

    window._on_detect_ptt_button()

    assert messages, "expected a safe 'no controller' message"
    assert "controller" in messages[0].lower() or "wheel" in messages[0].lower()
    # Binding untouched (was unset).
    assert not window._config.get("query_button")


def test_count_connected_joysticks_safe_without_pygame(monkeypatch):
    """count_connected_joysticks never raises, even if pygame is unavailable."""
    import ui.button_detect_dialog as bdd
    import builtins
    real_import = builtins.__import__

    def _no_pygame(name, *a, **k):
        if name == "pygame":
            raise ImportError("no pygame")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _no_pygame)
    assert bdd.count_connected_joysticks() == 0


# --------------------------------------------------------------------------- #
# Test 22 — a detected wheel button persists and restores
# --------------------------------------------------------------------------- #

def test_detected_wheel_button_persists_and_restores(window):
    binding = {"type": "joystick", "button_index": 5, "device": "Fanatec Wheel"}
    fake = _FakeDetectDialog(accepted=True, detected=binding)
    window._make_button_detect_dialog = lambda: fake

    window._on_detect_ptt_button()

    # Stored in the live config...
    assert window._config["query_button"] == binding
    # ...and persisted to disk so it survives a restart.
    reloaded = cp.load_config(window._config_path)
    assert reloaded["query_button"] == binding
    # ...and the label reflects the device.
    label = window._ptt_binding_lbl.text()
    assert "5" in label and "Fanatec Wheel" in label


def test_replacing_existing_binding_requires_confirmation(window):
    window._config["query_button"] = {"type": "keyboard", "key": "f8"}
    new = {"type": "joystick", "button_index": 2, "device": "Pad"}
    fake = _FakeDetectDialog(accepted=True, detected=new)
    window._make_button_detect_dialog = lambda: fake

    # User declines the replace confirmation.
    window._confirm_replace_binding = lambda existing, nb: False
    window._on_detect_ptt_button()
    assert window._config["query_button"] == {"type": "keyboard", "key": "f8"}

    # User accepts the replace confirmation.
    window._confirm_replace_binding = lambda existing, nb: True
    window._on_detect_ptt_button()
    assert window._config["query_button"] == new


def test_duplicate_binding_warns_and_keeps(window):
    existing = {"type": "keyboard", "key": "f8"}
    window._config["query_button"] = dict(existing)
    msgs = []
    window._show_ptt_message = lambda text, **kw: msgs.append(text)
    # Detect the same key again.
    fake = _FakeDetectDialog(accepted=True, detected={"type": "keyboard", "key": "f8"})
    window._make_button_detect_dialog = lambda: fake

    window._on_detect_ptt_button()

    assert window._config["query_button"] == existing
    assert any("already" in m.lower() for m in msgs)


def test_clear_binding_removes_and_persists(window):
    window._config["query_button"] = {"type": "keyboard", "key": "f8"}
    window._confirm_replace_binding = lambda *a, **k: True
    # _on_clear uses QMessageBox.question directly; patch it to "Yes".
    import ui.settings_ui as su
    from PyQt6.QtWidgets import QMessageBox
    orig = QMessageBox.question
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    try:
        window._on_clear_ptt_binding()
    finally:
        QMessageBox.question = orig
    assert not window._config.get("query_button")
    reloaded = cp.load_config(window._config_path)
    assert not reloaded.get("query_button")


# --------------------------------------------------------------------------- #
# Test 23 — controller disconnect during detection does not crash
# --------------------------------------------------------------------------- #

def test_joystick_disconnect_during_detection_is_swallowed(qapp, monkeypatch):
    """The joystick polling path must swallow a mid-detection pygame error
    (device disconnected) rather than propagate and crash the dialog."""
    import sys
    import types

    class _FakeJoystick:
        def __init__(self, idx): pass
        def init(self): pass
        def get_name(self): return "Test Wheel"
        def get_numbuttons(self): return 4
        def get_button(self, i):
            # Simulate the controller vanishing mid-detection.
            raise RuntimeError("Joystick disconnected")

    fake_pygame = types.ModuleType("pygame")
    fake_pygame.init = lambda: None
    fake_joystick_mod = types.SimpleNamespace(
        init=lambda: None,
        get_count=lambda: 1,
        Joystick=_FakeJoystick,
    )
    fake_pygame.joystick = fake_joystick_mod
    fake_pygame.event = types.SimpleNamespace(pump=lambda: None)
    monkeypatch.setitem(sys.modules, "pygame", fake_pygame)

    from ui.button_detect_dialog import ButtonDetectDialog
    # No real input threads; drive the joystick path synchronously.
    dlg = ButtonDetectDialog(_spawn_threads=False)
    try:
        dlg._detect_joystick()  # must not raise
        assert dlg.detected_binding == {}
    finally:
        dlg.close()
