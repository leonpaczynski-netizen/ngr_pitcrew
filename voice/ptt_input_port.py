"""Push-to-Talk input port (Program 2, Phase 64).

A hardware-neutral PTT input abstraction. The DEFAULT port is DISABLED (the mic is never listening by
default). A deterministic fake drives tests. A concrete local Windows adapter (keyboard / controller /
wheel button exposed to Windows) may be added later behind this exact boundary — it is the only place
that would import an OS input library, and it must audit shutdown, focus, permission and conflict risks
before installing any global hook.

Purity of the port contract: implementations must never raise into the caller. No network, no API key.
"""
from __future__ import annotations

from typing import List


class PushToTalkInputPort:
    """Abstract PTT input. ``is_available`` reports whether a real input device is bound and usable;
    ``is_pressed`` reports the current held state (press-and-hold) or toggled state."""

    name = "abstract"

    def is_available(self) -> bool:  # pragma: no cover - interface
        return False

    def is_pressed(self) -> bool:  # pragma: no cover - interface
        return False

    def poll(self) -> bool:  # pragma: no cover - interface
        """Poll the current pressed state (never raises)."""
        return False

    def shutdown(self) -> None:  # pragma: no cover - interface
        pass


class DisabledPttInputPort(PushToTalkInputPort):
    """The DEFAULT: no input device, never pressed. Construction listens to nothing."""

    name = "disabled"

    def is_available(self) -> bool:
        return False

    def is_pressed(self) -> bool:
        return False

    def poll(self) -> bool:
        return False

    def shutdown(self) -> None:
        pass


class FakePttInputPort(PushToTalkInputPort):
    """Deterministic test adapter. Press/release are driven explicitly; can simulate an unavailable
    device. Never installs any OS hook."""

    name = "fake"

    def __init__(self, *, available: bool = True):
        self._available = bool(available)
        self._pressed = False
        self.press_events = 0
        self.release_events = 0
        self.shutdowns = 0

    def is_available(self) -> bool:
        return self._available

    def press(self) -> None:
        if self._available and not self._pressed:
            self._pressed = True
            self.press_events += 1

    def release(self) -> None:
        if self._pressed:
            self._pressed = False
            self.release_events += 1

    def is_pressed(self) -> bool:
        return self._available and self._pressed

    def poll(self) -> bool:
        return self.is_pressed()

    def shutdown(self) -> None:
        self._pressed = False
        self.shutdowns += 1
