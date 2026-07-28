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
import traceback
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
                 hide_empty: bool = True, log_path: Optional[str] = None) -> None:
        super().__init__()
        self._main = main_window
        self._logger = logger
        self._hide_empty = hide_empty
        #: A dedicated on-disk sink. The injected ``logger`` is a LapDataLogger with no
        #: ``.warning`` — so the report used to fall back to bare ``print`` and was lost
        #: whenever the app ran without a console. This file always captures it, with the
        #: source traceback, so the culprit can be found from a single real run.
        self._log_path = log_path
        #: class name -> times seen, so each culprit is logged once (then counted).
        self._seen: dict[str, int] = {}
        #: Diagnostic: every top-level window class already logged, so the file gets
        #: ONE traceback per distinct top-level (main window, dialogs, AND whatever is
        #: flashing) — the guard's stray classifier may not recognise the culprit, so
        #: this catches it regardless of type/title.
        self._diag_seen: set = set()

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
            # A window the driver is meant to see has a REAL title. A Qt-internal name
            # ("_q_titlebar" etc.) is never a driver-facing window, so such a window is
            # stray even though technically titled; every other titled window is trusted.
            title = (w.windowTitle() or "").strip()
            if title and not title.startswith("_q_"):
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

    def _source_frames(self) -> str:
        """The project call stack at the moment the stray window was shown.

        A programmatic ``widget.show()`` delivers the Show event SYNCHRONOUSLY inside
        the ``show()`` call, so this stack names the exact code that created and showed
        the window — which is what lets the source be removed (the guard is only a net).
        Qt/stdlib/guard frames are dropped so only the app's own frames remain.
        """
        try:
            frames = traceback.extract_stack()[:-2]   # drop _report + eventFilter
            keep = []
            for fr in frames:
                fn = (fr.filename or "").replace("\\", "/")
                if "/site-packages/" in fn or "/PyQt6/" in fn:
                    continue
                if fn.endswith("ui/stray_window_guard.py"):
                    continue
                keep.append(f"    {fr.filename}:{fr.lineno} in {fr.name}() | {fr.line}")
            tail = keep[-8:] if keep else ["    (no application frames on the stack — "
                                           "likely a spontaneous window-system show)"]
            return "\n".join(tail)
        except Exception:
            return "    (traceback capture failed)"

    def _report(self, w: QWidget, hidden: bool) -> None:
        key = type(w).__name__ + ":" + (w.objectName() or "")
        count = self._seen.get(key, 0) + 1
        self._seen[key] = count
        if count > 1:
            return   # already reported this culprit; the counter is enough
        source = self._source_frames()
        msg = (f"[StrayWindowGuard] suppressed a stray top-level window "
               f"({'hidden' if hidden else 'de-focused'}): {self._describe(w)}\n"
               f"  shown from:\n{source}")
        # Injected logger first (best-effort — it may not have .warning); then a bare
        # print; then always the dedicated file sink so the line + source survive a
        # console-less run.
        logged = False
        if self._logger is not None:
            try:
                self._logger.warning(msg)
                logged = True
            except Exception:
                logged = False
        if not logged:
            print(msg)
        if self._log_path:
            try:
                with open(self._log_path, "a", encoding="utf-8") as fh:
                    fh.write(msg + "\n")
            except Exception:
                pass

    # ---- diagnostic: log EVERY top-level window shown --------------------
    def _diagnostic_log(self, w: QWidget) -> None:
        """Append one traceback per distinct top-level window class to the log file.

        The stray classifier is conservative and may not flag the real culprit (a
        titled window, a dialog, a native flash). This logs ALL of them so a single
        run names every top-level and where it was shown from — the flasher is then
        identifiable by its class/traceback even when ``_is_stray`` returns False.
        """
        if not self._log_path:
            return
        try:
            key = (type(w).__name__ + "|" + (w.objectName() or "") + "|"
                   + (w.windowTitle() or ""))
            if key in self._diag_seen:
                return
            self._diag_seen.add(key)
            wt = int(w.windowType() & Qt.WindowType.WindowType_Mask)
            line = (f"[StrayWindowGuard/diag] top-level shown: {self._describe(w)} "
                    f"windowType={wt}\n  shown from:\n{self._source_frames()}\n")
            with open(self._log_path, "a", encoding="utf-8") as fh:
                fh.write(line)
        except Exception:
            pass

    def _return_focus_to_main(self) -> None:
        if self._main is not None:
            try:
                self._main.activateWindow()
                self._main.raise_()
            except Exception:
                pass

    # ---- the filter -------------------------------------------------------
    def eventFilter(self, obj, event) -> bool:
        try:
            et = event.type()
            is_win = isinstance(obj, QWidget) and obj.isWindow() and obj is not self._main
            # Diagnostic: capture EVERY non-main top-level on Show AND on Activate — a
            # window that steals focus by RAISING/activating (not re-showing) emits no
            # Show event, which is why the culprit had been logging nothing. This names
            # it (class + traceback) in the log on the next run regardless of how it
            # appears.
            if is_win and et in (QEvent.Type.Show, QEvent.Type.WindowActivate):
                self._diagnostic_log(obj)

            if et == QEvent.Type.Show and self._is_stray(obj):
                # Never let it activate/steal focus again.
                obj.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                hidden = False
                if self._hide_empty and self._looks_empty(obj):
                    obj.hide()
                    hidden = True
                self._report(obj, hidden)
                self._return_focus_to_main()

            # Focus-steal net: a non-main top-level that keeps grabbing activation while
            # being empty/stray (the flashing box) — hand focus straight back to the
            # main window so the driver can keep typing. Real, content-bearing dialogs
            # are left alone (they are not empty and not _is_stray), so this cannot
            # steal focus from a genuine dialog the driver opened.
            elif et == QEvent.Type.WindowActivate and is_win \
                    and (self._is_stray(obj) or self._looks_empty(obj)):
                obj.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
                if self._hide_empty and self._looks_empty(obj):
                    try:
                        obj.hide()
                    except Exception:
                        pass
                self._report(obj, hidden=True)
                self._return_focus_to_main()
        except Exception:
            pass
        return super().eventFilter(obj, event)


def install_stray_window_guard(app, main_window: Optional[QWidget],
                               logger=None, log_path: Optional[str] = None
                               ) -> Optional[StrayWindowGuard]:
    """Install the guard on ``app``. No-op when NGR_NO_STRAY_GUARD=1 or app is None.

    ``log_path`` is a dedicated file the guard appends stray-window reports to (with
    the source traceback), so the culprit survives a console-less run. Returns the
    guard (kept alive by the caller) or None.
    """
    if app is None or os.environ.get("NGR_NO_STRAY_GUARD") == "1":
        return None
    guard = StrayWindowGuard(main_window, logger=logger, log_path=log_path)
    app.installEventFilter(guard)
    return guard
