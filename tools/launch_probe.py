"""Launch Pit Crew the way the shortcut does, time it, and close it.

    python tools/launch_probe.py <checkout> <out.json> [hold_ms]

Runs the real `pitcrew.app.main()` of `<checkout>` in this process, against
that checkout's own `data/pitcrew.db` - so point it at a worktree holding a
sandbox copy, never at the live checkout. Nothing in the app is replaced.
Three things are added around it:

* `diagnostics.mark` is wrapped, so every launch phase the app already logs
  ("store open", "window built", "first paint", ...) is recorded as ms since
  the PROCESS was created (GetProcessTimes), not since `main()`.
* An application-wide event filter records the first Paint event delivered
  to any widget of the `PitCrewWindow` - the moment there is something on
  the screen. This is the number the driver waits for.
* A 5 ms timer samples the event loop. Any gap over 50 ms is a stall: the
  window is up but not answering. `settled` is when the last stall that
  ends after the first idle turn is over - the window is then painted AND
  answering. It also records when push to talk's speech models have landed.

The window is closed `hold_ms` after the first idle turn (default 4500, long
enough for the speech load to land on a quiet machine).

**It does not run `pitcrew.boot`.** It imports `pitcrew.app` as a module,
so the early step the shortcut's `python -m pitcrew.app` takes before the
imports - the QApplication and the font warm-up - is not in its figures,
and a fallback font it would have loaded shows up here as a stall. For the
launch as the driver gets it, use `tools/launch_ab.py`, which times the
real process from outside.

`PITCREW_ALLOW_MULTIPLE=1` is set so a copy running elsewhere on the machine
(another worktree's probe, the real app) never turns this into the 0.7 s
wedge check or a refusal.
"""
import json
import os
import sys
import time

root, out = sys.argv[1], sys.argv[2]
hold_ms = int(sys.argv[3]) if len(sys.argv) > 3 else 4500
os.chdir(root)
sys.path.insert(0, root)
os.environ["PITCREW_ALLOW_MULTIPLE"] = "1"

import pitcrew.diagnostics as diagnostics  # noqa: E402


def since() -> float:
    return diagnostics.seconds_since_process_start() * 1000.0


marks = [("interpreter up", since())]
_orig_mark = diagnostics.mark


def mark(phase):
    marks.append((phase, since()))
    _orig_mark(phase)


diagnostics.mark = mark

import pitcrew.app as app  # noqa: E402

marks.append(("imports done", since()))

from PyQt6.QtCore import QEvent, QObject, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

stalls = []
state = {}


class PaintSpy(QObject):
    def eventFilter(self, obj, event):  # noqa: N802 - Qt naming
        if event.type() == QEvent.Type.Paint and "first_paint" not in state:
            try:
                win = obj.window()
            except Exception:  # noqa: BLE001
                win = None
            if isinstance(win, app.PitCrewWindow):
                state["first_paint"] = since()
        return False


def _speech_landed(window) -> bool:
    talk = window.controller.ptt
    arriving = getattr(talk, "_arriving", None)
    if arriving is None:
        # No pending warm-up: either it has been installed, or this is a
        # checkout that joined the models before the window existed.
        return True
    landed = getattr(app.ptt, "speech_landed", None)
    return bool(landed and landed(arriving))


class ProbeApp(QApplication):
    def exec(self):  # noqa: A003 - Qt naming
        self._spy = PaintSpy()
        self.installEventFilter(self._spy)
        last = [time.perf_counter()]
        state["exec"] = since()

        def windows():
            return [w for w in self.topLevelWidgets()
                    if isinstance(w, app.PitCrewWindow)]

        def tick():
            if "speech_ready" not in state:
                found = windows()
                if found and not hasattr(found[0].controller.ptt,
                                         "_arriving"):
                    # A checkout that joins the models inside the
                    # controller: they were ready when the window was built.
                    state["speech_ready"] = dict(marks).get("window built")
                elif any(_speech_landed(w) for w in found):
                    state["speech_ready"] = since()
            now = time.perf_counter()
            gap = (now - last[0]) * 1000.0
            if gap > 50:
                stalls.append((round(since() - gap), round(gap)))
            last[0] = now

        sampler = QTimer()
        sampler.setInterval(5)
        sampler.timeout.connect(tick)
        sampler.start()

        def first_idle():
            state["first_idle"] = since()
            QTimer.singleShot(hold_ms, finish)

        def finish():
            state["finish"] = since()
            for window in windows():
                window.close()
            self.quit()

        QTimer.singleShot(0, first_idle)
        return super().exec()


app.QApplication = ProbeApp
code = app.main()
settled = state.get("first_idle")
for start, gap in stalls:
    if start + gap > (settled or 0) and start < state.get("finish", 1e12):
        settled = max(settled, start + gap)
state["settled"] = settled
with open(out, "w", encoding="utf-8") as handle:
    json.dump({"marks": marks, "stalls": stalls, "state": state,
               "code": code}, handle, indent=1)
os._exit(0)
