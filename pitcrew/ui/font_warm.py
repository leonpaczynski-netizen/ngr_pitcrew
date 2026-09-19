"""Load fonts on a Qt worker thread, so the Qt thread finds them loaded.

**Two one-time costs, measured 19 Sep 2026, both inside Qt's font database
and both shared by every thread once paid:**

* The first font anything asks for makes Qt read the machine's installed
  faces: 90-250 ms, inside the Event screen's build, on the path to the
  window.
* The first glyph Bahnschrift does not have - the minus sign in a practice
  delta and on the Reference tables, the katakana dot in "Nissan R34 GT-R
  V･spec II" - makes Qt work out the machine's fallback faces: 170-400 ms,
  once, whichever glyph and whichever face asks first. It was being paid
  by whatever happened to show such a glyph first: the Car screen's picker
  (the freeze after the window appeared), then the Reference screen, and -
  with neither built - it would have been the first negative delta of a
  live practice session.

**Why a QThread and a text document, not a Python thread.** PyQt holds the
GIL for the whole of every Qt call it makes, so a Python thread that asks
Qt to measure text blocks the Qt thread's Python for as long as the call
takes - measured: a launch 560 ms slower with one. Here no Python runs on
the worker at all, and nothing on the Qt thread touches a font:

* the text goes into a `QTextDocument` whose page size is null, which is
  the one state in which Qt does not lay a document out - so neither the
  insert nor creating its layout asks for a font (1.4 ms, measured);
* the document is moved to the worker, with a zero-length
  `QPropertyAnimation` of its `textWidth` as its child;
* the animation's `start` - a C++ slot - is queued to the worker. It writes
  the width, and the worker lays the text out: the font database is read
  and the fallback faces are found there, in C++, with the GIL free. A
  Python loop on the Qt thread saw no gap over 3 ms throughout, and the Qt
  thread's own first font and first minus sign then cost 0.5 ms instead of
  40-220 and 200-250.

**What it does not do: nothing waits for it, and nothing depends on it.**
A Qt thread that needs a font while this is loading waits on Qt's own lock
for, at most, the rest of the load it would otherwise have done itself.
A warm-up that never finishes leaves the old cost exactly where it was.
Qt documents fonts, text layout and QTextDocument as safe off the GUI
thread; it is how text is drawn into images in workers.
"""
from __future__ import annotations

import time

from PyQt6 import sip
from PyQt6.QtCore import (QMetaObject, QObject, QPropertyAnimation, QSizeF, Qt,
                          QThread)
from PyQt6.QtGui import QFont, QTextCursor, QTextDocument

# Every warm-up this process started, kept so Python can never collect a
# QThread that is still running - Qt aborts the process if one is destroyed
# mid-run - and so `stop_all` can end them on the way out.
_LIVE: list["FontWarmUp"] = []


class FontWarmUp(QObject):
    """Lay `text` out in `font` on a worker thread, once."""

    def __init__(self, text: str, font: QFont, name: str) -> None:
        super().__init__()
        self._thread = QThread()
        self._thread.setObjectName(name)
        doc = QTextDocument()
        # Null, so that nothing below lays it out on THIS thread. The
        # default is (-1, -1), which is "no limit", not null, and lays out.
        doc.setPageSize(QSizeF(0, 0))
        doc.setDefaultFont(font)
        QTextCursor(doc).insertText(text)
        doc.documentLayout()
        width = QPropertyAnimation(doc, b"textWidth", doc)
        width.setStartValue(4000.0)
        width.setEndValue(4000.0)
        width.setDuration(0)
        # Laid out -> deleted -> the worker stops. All on the worker.
        width.finished.connect(doc.deleteLater)
        doc.destroyed.connect(self._thread.quit,
                              Qt.ConnectionType.DirectConnection)
        doc.moveToThread(self._thread)
        # Owned by C++ from here: the worker deletes the document, and a
        # thread Python cannot collect can never be destroyed while running.
        sip.transferto(doc, None)
        sip.transferto(self._thread, None)
        _LIVE.append(self)
        # **Logged when it ends, with its time** (critic, 19 Sep 2026): a
        # launch that stalls on fonts must leave a trace of how long the
        # load it shares a lock with took. A direct connection, so the time
        # is the worker's own - the one line of Python it ever runs, after
        # every font has loaded, never while the lock is held.
        self._name = name
        self._began = time.perf_counter()
        self.took_s: float | None = None
        self._thread.finished.connect(self._finished,
                                      Qt.ConnectionType.DirectConnection)
        self._thread.start()
        QMetaObject.invokeMethod(width, "start",
                                 Qt.ConnectionType.QueuedConnection)

    def _finished(self) -> None:
        self.took_s = time.perf_counter() - self._began
        from pitcrew import diagnostics

        level = ("warning" if self.took_s >= diagnostics.SLOW_STEP_S
                 else "info")
        getattr(diagnostics.log("startup"), level)(
            "font warm-up %s finished in %.0f ms", self._name,
            self.took_s * 1000.0)

    def done(self) -> bool:
        return self._thread.isFinished()

    def stop(self, wait_ms: int = 2000) -> bool:
        """End the worker. True if it has ended."""
        self._thread.quit()
        return self._thread.wait(wait_ms)


def start(text: str, font: QFont, name: str = "warm-fonts") -> FontWarmUp:
    return FontWarmUp(text, font, name)


def stop_all() -> None:
    """On the way out: no worker may outlive the application object."""
    for warm in _LIVE:
        warm.stop()
