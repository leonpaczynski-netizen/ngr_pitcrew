"""Concrete controller / wheel-button push-to-talk input adapter (Program 2, Phase 67).

Implements the Phase-64 ``PushToTalkInputPort`` for a joystick/gamepad/wheel BUTTON using ``ctypes`` +
Win32 ``winmm.joyGetPosEx`` — a POLL of the joystick's button state (wheel buttons are exposed to Windows
as joystick buttons, so this covers direct-drive wheels and controllers without any wheel-specific SDK).
Best-effort: disabled + inert when winmm / the joystick / the button is unavailable. No Fanatec-specific
code, no new dependency (ctypes is stdlib), offline, never a global hook. Never raises.
"""
from __future__ import annotations

from typing import Optional

from voice.ptt_input_port import PushToTalkInputPort

# JOYINFOEX flag to request button state.
_JOY_RETURNBUTTONS = 0x00000080


class JoystickPttInputPort(PushToTalkInputPort):
    """Poll one joystick button as the PTT control. ``joy_id`` is the Win32 joystick id (0..15);
    ``button_index`` is the 0-based button number. Operational configuration only."""

    name = "controller"

    def __init__(self, joy_id: int = 0, button_index: int = 0):
        self._joy = int(joy_id)
        self._button = int(button_index)
        self._winmm = None
        self._struct = None
        self._probed = False

    def _lib(self):
        if self._probed:
            return self._winmm
        self._probed = True
        try:
            import ctypes  # stdlib
            from ctypes import wintypes

            class _JOYINFOEX(ctypes.Structure):
                _fields_ = [
                    ("dwSize", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("dwXpos", wintypes.DWORD), ("dwYpos", wintypes.DWORD), ("dwZpos", wintypes.DWORD),
                    ("dwRpos", wintypes.DWORD), ("dwUpos", wintypes.DWORD), ("dwVpos", wintypes.DWORD),
                    ("dwButtons", wintypes.DWORD), ("dwButtonNumber", wintypes.DWORD),
                    ("dwPOV", wintypes.DWORD), ("dwReserved1", wintypes.DWORD),
                    ("dwReserved2", wintypes.DWORD),
                ]
            self._struct = _JOYINFOEX
            self._winmm = ctypes.windll.winmm  # Windows-only
        except Exception:
            self._winmm = None
            self._struct = None
        return self._winmm

    def _read_buttons(self) -> Optional[int]:
        try:
            lib = self._lib()
            if lib is None or self._struct is None:
                return None
            info = self._struct()
            import ctypes
            info.dwSize = ctypes.sizeof(self._struct)
            info.dwFlags = _JOY_RETURNBUTTONS
            # JOYERR_NOERROR == 0
            if lib.joyGetPosEx(self._joy, ctypes.byref(info)) != 0:
                return None
            return int(info.dwButtons)
        except Exception:  # pragma: no cover - defensive
            return None

    def is_available(self) -> bool:
        return self._read_buttons() is not None

    def is_pressed(self) -> bool:
        buttons = self._read_buttons()
        if buttons is None:
            return False
        return bool(buttons & (1 << self._button))

    def poll(self) -> bool:
        return self.is_pressed()

    def shutdown(self) -> None:
        self._winmm = None
        self._struct = None
        self._probed = False
