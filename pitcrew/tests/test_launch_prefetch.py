"""The launch's prefetch imports only what the window build imports anyway.

`app.PREFETCH` is imported in `main` before the Event screen, so that it
fills the Event screen's wait for the font warm-up instead of running inside
the controller afterwards (round 4, 20 Sep 2026). That is only free if every
module in it is one the window build would have imported regardless - a
prefetch of something nothing uses is launch time spent for nothing. Checked
in a fresh interpreter, because this suite has imported everything already.
"""
from __future__ import annotations

import inspect
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("PyQt6.QtWidgets")

ROOT = Path(__file__).resolve().parents[2]


def test_every_prefetched_module_is_imported_by_the_window_build(tmp_path):
    script = textwrap.dedent("""
        import os, sys, threading
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
        from PyQt6.QtWidgets import QApplication
        app = QApplication([])
        import pitcrew.app as pc
        from pitcrew import settings
        from pitcrew.engineer import ptt, voice
        from pitcrew.store.db import Store
        store = Store(sys.argv[1])
        # As `main` builds it: the speech load held back, and the voice
        # engine already chosen (here, a silent one), so what is imported
        # below is what the window build itself imports.
        warm = ptt.start_warm_up(settings.load(store).speech_backend,
                                 start=False)
        done = threading.Thread(target=lambda: None)
        done.start()
        done.join()
        before = set(sys.modules)
        window = pc.PitCrewWindow(store, warm=warm,
                                  voice_engine=({"engine": voice.NullEngine()},
                                                done))
        # The radio bursts: `PushToTalk` renders them in the controller on
        # the real launch and never under pytest (they open an output
        # stream), so the rendering is done here the way it does it - the
        # numpy half only, which is what imports numpy's random and fft.
        from pitcrew.engineer import radio
        radio._noise(radio.BURST_MS, 44100, rising=True, seed=17)
        wanted = [m for m in pc.PREFETCH if m not in before]
        missing = [m for m in wanted if m not in sys.modules]
        window.controller.shutdown()
        with open(sys.argv[2], "w") as out:
            out.write("MISSING " + ",".join(missing) + chr(10))
            out.write("CHECKED " + ",".join(wanted) + chr(10))
        os._exit(0)
    """)
    report = tmp_path / "report.txt"
    run = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path / "pitcrew.db"),
         str(report)],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(ROOT)})
    assert report.exists(), run.stdout + run.stderr
    lines = dict(line.split(" ", 1) for line in
                 report.read_text().splitlines())
    # Nothing in PREFETCH may already be imported before the window build,
    # or this checks nothing.
    assert lines["CHECKED"].strip().split(",") == list(
        __import__("pitcrew.app", fromlist=["PREFETCH"]).PREFETCH)
    assert lines["MISSING"].strip() == "", (
        f"prefetched but never imported by the window: {lines['MISSING']}")


def test_main_prefetches_before_it_builds_the_window():
    import pitcrew.app as app_module

    main = inspect.getsource(app_module.main)
    assert main.index("prefetch_while_fonts_load()") < main.index(
        "PitCrewWindow(")


def test_a_module_that_will_not_import_is_logged_not_raised(monkeypatch,
                                                            caplog):
    import pitcrew.app as app_module

    monkeypatch.setattr(app_module, "PREFETCH", ("no_such_module_xyz",))
    with caplog.at_level("WARNING"):
        app_module.prefetch_while_fonts_load()
    assert any("could not prefetch no_such_module_xyz" in r.getMessage()
               for r in caplog.records)
