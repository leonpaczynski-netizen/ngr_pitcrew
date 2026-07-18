"""Canonical push-to-talk button-detection dialog.

This is the single source of truth for detecting a keyboard key, controller
button or wheel button to bind as the push-to-talk (PTT) control.

History / why this module exists
--------------------------------
The dialog was originally defined inside ``ui/dashboard.py``. When the Settings
tab was extracted into ``ui/settings_ui.py`` (decomposition slice 2) the handler
``_on_detect_ptt_button`` moved with it but continued to reference the bare name
``_ButtonDetectDialog`` — which only existed in the ``ui.dashboard`` module
namespace. At runtime that raised ``NameError: name '_ButtonDetectDialog' is not
defined`` and crashed the Settings screen (UAT Finding 5).

The fix is structural, not a caught exception: the dialog now lives in its own
module that both ``ui.dashboard`` and ``ui.settings_ui`` import, so there is
exactly one canonical implementation and no namespace can be missing it.

The dialog is deliberately self-contained: it imports only PyQt6 + stdlib and
optional input libraries (``pynput``, ``pygame``) guarded by try/except, so it
never blocks the settings screen and degrades safely when no input device or
optional dependency is present.
"""
from __future__ import annotations

import threading
import time

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout


# ---------------------------------------------------------------------------
# Qt key -> pynput key-name mapping.
# Keys must produce the same string that pynput's Listener gives in
# QueryListener, so a key bound here matches the same key at listen time.
# ---------------------------------------------------------------------------

_QT_TO_PYNPUT: dict = {
    Qt.Key.Key_F1:  'f1',  Qt.Key.Key_F2:  'f2',  Qt.Key.Key_F3:  'f3',
    Qt.Key.Key_F4:  'f4',  Qt.Key.Key_F5:  'f5',  Qt.Key.Key_F6:  'f6',
    Qt.Key.Key_F7:  'f7',  Qt.Key.Key_F8:  'f8',  Qt.Key.Key_F9:  'f9',
    Qt.Key.Key_F10: 'f10', Qt.Key.Key_F11: 'f11', Qt.Key.Key_F12: 'f12',
    Qt.Key.Key_F13: 'f13', Qt.Key.Key_F14: 'f14', Qt.Key.Key_F15: 'f15',
    Qt.Key.Key_F16: 'f16', Qt.Key.Key_F17: 'f17', Qt.Key.Key_F18: 'f18',
    Qt.Key.Key_F19: 'f19', Qt.Key.Key_F20: 'f20',
    Qt.Key.Key_Tab:        'tab',
    Qt.Key.Key_CapsLock:   'caps_lock',
    Qt.Key.Key_Space:      'space',
    Qt.Key.Key_Return:     'enter',
    Qt.Key.Key_Enter:      'enter',
    Qt.Key.Key_Backspace:  'backspace',
    Qt.Key.Key_Delete:     'delete',
    Qt.Key.Key_Insert:     'insert',
    Qt.Key.Key_Home:       'home',
    Qt.Key.Key_End:        'end',
    Qt.Key.Key_PageUp:     'page_up',
    Qt.Key.Key_PageDown:   'page_down',
    Qt.Key.Key_Left:       'left',
    Qt.Key.Key_Right:      'right',
    Qt.Key.Key_Up:         'up',
    Qt.Key.Key_Down:       'down',
    Qt.Key.Key_Print:      'print_screen',
    Qt.Key.Key_ScrollLock: 'scroll_lock',
    Qt.Key.Key_Pause:      'pause',
    Qt.Key.Key_NumLock:    'num_lock',
}

_QT_MODIFIERS = {
    Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt,
    Qt.Key.Key_Meta, Qt.Key.Key_AltGr,
}


def count_connected_joysticks() -> int:
    """Return the number of connected controllers/wheels, or 0 if pygame is
    unavailable or the joystick subsystem cannot start. Never raises."""
    try:
        import pygame
        pygame.init()
        pygame.joystick.init()
        return int(pygame.joystick.get_count())
    except Exception:
        return 0


class ButtonDetectDialog(QDialog):
    """Modal dialog that waits for a keypress or joystick/wheel button press.

    On accept, ``detected_binding`` holds one of::

        {"type": "keyboard", "key": "<pynput key name>"}
        {"type": "joystick", "button_index": <int>, "device": "<name>"}

    The dialog:
      * listens on three paths (Qt key events, a pynput background thread and a
        pygame joystick polling thread) so keyboard, controller and wheel input
        are all captured;
      * exposes ``joystick_available`` so the caller can show an honest message
        when no controller/wheel is connected;
      * survives a controller disconnect mid-detection (the poll loop catches
        pygame errors and simply stops the joystick path);
      * supports cancellation via the Cancel button, Escape, or a 5s timeout.
    """

    # Emitted from background threads (pynput / joystick) to report detections
    # safely back onto the GUI thread.
    _bg_detected = pyqtSignal(object)

    def __init__(self, parent=None, *, window_seconds: int = 5,
                 _spawn_threads: bool = True) -> None:
        super().__init__(parent)
        self.setWindowTitle("Detect Button")
        self.setModal(True)
        self.setFixedSize(380, 190)
        self.detected_binding: dict = {}

        # Snapshot of connected controllers/wheels at open time. The caller uses
        # this to produce a safe "no controller connected" message when nothing
        # is detected. Defaults optimistically so we never over-warn.
        self.joystick_available: bool = count_connected_joysticks() > 0

        dev_hint = (
            "Keyboard, controller or wheel button — 5-second window."
            if self.joystick_available else
            "No controller/wheel detected — a keyboard key can still be bound."
        )
        self._info_lbl = QLabel(
            "Press the button you want to use as push-to-talk.\n" + dev_hint
        )
        self._info_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info_lbl.setWordWrap(True)

        self._countdown_lbl = QLabel(str(window_seconds))
        self._countdown_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._countdown_lbl.setFont(QFont("Segoe UI", 28, QFont.Weight.Bold))

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self._info_lbl)
        layout.addWidget(self._countdown_lbl)
        layout.addWidget(btn_cancel)

        self._stop = threading.Event()
        self._bg_detected.connect(self._on_detected)

        # grabKeyboard() forces ALL keyboard events to this dialog even if a
        # child widget or the parent window technically has focus.
        self.grabKeyboard()

        # Background threads: a pynput safety net for keys that might not route
        # through Qt (some HID keyboards on Windows), and joystick/wheel polling.
        # ``_spawn_threads=False`` lets tests drive _detect_joystick synchronously
        # (e.g. to assert a mid-detection disconnect is swallowed) without racing
        # real input threads.
        if _spawn_threads:
            threading.Thread(target=self._detect_pynput, daemon=True).start()
            threading.Thread(target=self._detect_joystick, daemon=True).start()

        self._remaining = int(window_seconds)
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._tick)
        self._tick_timer.start(1000)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.activateWindow()
        self.setFocus()
        self.grabKeyboard()

    # ------------------------------------------------------------------
    # Qt path — fastest, runs in main thread
    # ------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        if self._stop.is_set():
            return
        key = event.key()

        if key == Qt.Key.Key_Escape:
            self._stop.set()
            self._tick_timer.stop()
            self.reject()
            return
        if key in _QT_MODIFIERS:
            return

        text = event.text()
        if text and text.isprintable() and text.strip():
            k = text
        else:
            k = _QT_TO_PYNPUT.get(key)
            if k is None:
                try:
                    k = key.name.lower().replace('key_', '')
                except AttributeError:
                    k = str(int(key))

        self._on_detected({"type": "keyboard", "key": k})

    # ------------------------------------------------------------------
    # pynput fallback — background thread, signals back to main thread
    # ------------------------------------------------------------------

    def _detect_pynput(self) -> None:
        try:
            from pynput import keyboard as _kb

            def on_press(key):
                if self._stop.is_set():
                    return False
                try:
                    k = key.char if (hasattr(key, "char") and key.char) else key.name
                except Exception:
                    k = str(key)
                self._stop.set()
                self._bg_detected.emit({"type": "keyboard", "key": k})
                return False

            with _kb.Listener(on_press=on_press) as listener:
                listener.join()
        except ImportError:
            pass
        except Exception as e:  # pragma: no cover - defensive
            print(f"[ButtonDetect] pynput error: {e}")

    # ------------------------------------------------------------------

    def _tick(self) -> None:
        self._remaining -= 1
        self._countdown_lbl.setText(str(max(0, self._remaining)))
        if self._remaining <= 0:
            self._stop.set()
            self.reject()

    def _detect_joystick(self) -> None:
        try:
            import pygame
            pygame.init()
            pygame.joystick.init()
            if pygame.joystick.get_count() == 0:
                return
            joy = pygame.joystick.Joystick(0)
            joy.init()
            name = ""
            try:
                name = str(joy.get_name())
            except Exception:
                name = ""
            prev = [joy.get_button(i) for i in range(joy.get_numbuttons())]
            while not self._stop.is_set():
                pygame.event.pump()
                for i in range(joy.get_numbuttons()):
                    cur = bool(joy.get_button(i))
                    if cur and not prev[i]:
                        self._stop.set()
                        self._bg_detected.emit(
                            {"type": "joystick", "button_index": i, "device": name}
                        )
                        return
                    prev[i] = cur
                time.sleep(0.1)
        except ImportError:
            pass
        except Exception as e:
            # Controller disconnected mid-detection (pygame raises), or any other
            # device error: stop the joystick path cleanly — never crash the
            # dialog. The keyboard/pynput paths remain active.
            print(f"[ButtonDetect] joystick path stopped: {e}")

    def _on_detected(self, binding: dict) -> None:
        if self.detected_binding:
            return  # already accepted (Qt + pynput both fired)
        self._tick_timer.stop()
        self._stop.set()
        self.detected_binding = binding
        self.accept()

    def closeEvent(self, event) -> None:
        self._stop.set()
        try:
            self._tick_timer.stop()
        except Exception:
            pass
        self.releaseKeyboard()
        event.accept()


# Backwards-compatible alias: earlier code (and any external callers) referenced
# the private name. Keep it pointing at the one canonical class.
_ButtonDetectDialog = ButtonDetectDialog
