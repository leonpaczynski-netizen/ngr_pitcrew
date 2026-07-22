"""Regression guard: the Settings 'Test Mic' handler must have `threading` available.

_on_test_mic spawns a worker with threading.Thread; threading was used but never imported at module
level, so clicking 'Test Mic' raised NameError: name 'threading' is not defined. This guards the import
so the crash cannot silently return.
"""
from __future__ import annotations


def test_settings_ui_imports_threading_at_module_level():
    import ui.settings_ui as s
    assert hasattr(s, "threading"), "settings_ui must import threading (used by _on_test_mic)"


def test_on_test_mic_body_uses_threading():
    import inspect
    import ui.settings_ui as s
    # find the mixin/class that defines _on_test_mic and confirm it references threading.Thread
    src = inspect.getsource(s)
    assert "threading.Thread(target=_run" in src
