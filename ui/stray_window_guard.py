"""Stray top-level window guard.

A bug somewhere was flashing an EMPTY, unstyled top-level window (its own OS title
bar with minimize/maximize/close, blank body) every ~1-2 seconds while the driver
worked in the Garage / Practice Review. Each appearance STOLE KEYBOARD FOCUS, so
the driver could not type in the review notes.

This guard is a deterministic, offline safety net installed at startup. It watches
for top-level widgets being shown that are NOT the main window, NOT a real dialog,
and NOT a menu/combo popup or tooltip — i.e. a bare, usually EMPTY window nothing
intended to show. When it sees one it:

  1. LOGS exactly what it is (class, objectName, title, size, child classes) so the
     underlying source can be found and removed — it prints ONCE per unique window
     class with a repeat counter, never spamming;
  2. NEUTRALISES it — marks it show-without-activating so it can never steal focus
     again, and hides an empty one immediately so it does not flash.

It is conservative by construction (see ``_is_stray``): anything with a window
title, real content, or a Dialog/Popup/Tooltip window type is left completely
untouched, so legitimate dialogs (car ranges editor, transcribe window, message
boxes) and combo/menu popups are never affected.

Disable with the environment variable ``NGR_NO_STRAY_GUARD=1`` if it ever misfires.
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import QObject, QEvent, Qt
from PyQt6.QtWidgets import QWidget, QDialog


#: Window types that are legitimately transient and must NEVER be touched.
_SAFE_WINDOW_TYPES = (
    Qt.WindowType.Popup,        # QComboBox popup, QMenu
    Qt.WindowType.ToolTip,      # QToolTip
    Qt.WindowType.SplashScreen,
    Qt.WindowType.Desktop,
    Qt.WindowType.SubWindow,
)


class StrayWindowGuard(QObject):
    """Application event filter that suppresses stray focus-stealing top-levels."""

    def __init__(self, main_window: Optional[QWidget], logger=None,
                 hide_empty: bool = True) -> None:
        super().__init__()
        self._main = main_window
        self._logger = logger
        self._hide_empty = hide_empty
        #: class name -> times seen, so each culprit is logged once (then counted).
        self._seen: dict[str, int] = {}

    # ---- classification ---------------------------------------------------
    def _is_stray(self, w: QWidget) -> bool:
        """True only for a bare, unexpected top-level window.

        Deliberately narrow: a real dialog, a titled window, a popup/tooltip, or a
        window with meaningful content is NOT stray.
        """
        try:
            if w is None or w is self._main:
                return False
            if not w.isWindow():                       # not a top-level
                return False
            if isinstance(w, QDialog):                 # intentional dialogs
                return False
            wt = w.windowType() & Qt.WindowType.WindowType_Mask
            if wt in _SAFE_WINDOW_TYPES:               # menus, combos, tooltips
                return False
            # A window the driver is meant to see has a title. The stray one is blank.
            if (w.windowTitle() or "").strip():
                return False
            return True
        except Exception:
            return False

    def _looks_empty(self, w: QWidget) -> bool:
        """A stray window with no real content — safe to hide outright."""
        try:
            # A layout-less window with at most one incidental child is 'empty'.
            return len(w.findChildren(QWidget)) <= 1
        except Exception:
            return False

    # ---- logging ----------------------------------------------------------
    def _describe(self, w: QWidget) -> str:
        try:
            kids = [type(c).__name__ for c in w.findChildren(QWidget)][:6]
            g = w.geometry()
            return (f"class={type(w).__name__} objectName={w.objectName()!r} "
                    f"title={w.windowTitle()!r} size={g.width()}x{g.height()} "
                    f"children={len(w.findChildren(QWidget))} child_classes={kids}")
        except Exception:
            return f"class={type(w).__name__} (describe failed)"

    def _report(self, w: QWidget, hidden: bool) -> None:
        key = type(w).__name__ + ":" + (w.objectName() or "")
        count = self._seen.get(key, 0) + 1
        self._seen[key] = count
        if count > 1:
            return   # already reported this culprit; the counter is enough
        msg = (f"[StrayWindowGuard] suppressed a stray top-level window "
               f"({'hidden' if hidden else 'de-focused'}): {self._describe(w)}")
        if self._logger is not None:
            try:
                self._logger.warning(msg)
            except Exception:
                print(msg)
        else:
            print(msg)

    # ---- the filter -------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:
        try:
            if event.type() == QEvent.Type.Show and isinstance(obj, QWidget) \
                    and self._is_stray(obj):
                # Never let it activate/steal focus again.
                obj.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                hidden = False
                if self._hide_empty and self._looks_empty(obj):
                    obj.hide()
                    hidden = True
                self._report(obj, hidden)
                # Return focus to the main window if the stray grabbed it.
                if self._main is not None:
                    try:
                        self._main.activateWindow()
                    except Exception:
                        pass
        except Exception:
            pass
        return super().eventFilter(obj, event)


def install_stray_window_guard(app, main_window: Optional[QWidget],
                               logger=None) -> Optional[StrayWindowGuard]:
    """Install the guard on ``app``. No-op when NGR_NO_STRAY_GUARD=1 or app is None.

    Returns the guard (kept alive by the caller) or None.
    """
    if app is None or os.environ.get("NGR_NO_STRAY_GUARD") == "1":
        return None
    guard = StrayWindowGuard(main_window, logger=logger)
    app.installEventFilter(guard)
    return guard
