"""Concrete keyboard push-to-talk input adapter (Program 2, Phase 67).

Implements the Phase-64 ``PushToTalkInputPort`` for a keyboard key using ``ctypes`` + Win32
``GetAsyncKeyState`` — a POLL of the key's current state, NOT a global hook (so there is nothing to leak
on shutdown, no focus stealing, and no permission prompt). Offline; no network; no new dependency (ctypes
is stdlib). Lazy Win32 access so importing on a non-Windows box never fails; disabled + inert when the
platform or virtual-key code is unavailable. Never raises.
"""
from __future__ import annotations

from typing import Optional

from voice.ptt_input_port import PushToTalkInputPort


class KeyboardPttInputPort(PushToTalkInputPort):
    """Poll a single virtual-key code as the PTT control. ``vk_code`` is a Win32 virtual-key code (e.g.
    0x7C == F13). Operational configuration only — never an engineering value."""

    name = "keyboard"

    def __init__(self, vk_code: Optional[int] = None):
        self._vk = int(vk_code) if vk_code is not None else None
        self._user32 = None
        self._probed = False

    def _lib(self):
        if self._probed:
            return self._user32
        self._probed = True
        try:
            import ctypes  # stdlib
            self._user32 = ctypes.windll.user32  # Windows-only; raises on other platforms
        except Exception:
            self._user32 = None
        return self._user32

    def is_available(self) -> bool:
        return self._vk is not None and self._lib() is not None

    def is_pressed(self) -> bool:
        try:
            lib = self._lib()
            if lib is None or self._vk is None:
                return False
            # GetAsyncKeyState high-order bit (0x8000) = currently down.
            return bool(lib.GetAsyncKeyState(self._vk) & 0x8000)
        except Exception:  # pragma: no cover - defensive
            return False

    def poll(self) -> bool:
        return self.is_pressed()

    def shutdown(self) -> None:
        # nothing to release — polling installs no hook.
        self._user32 = None
        self._probed = False
