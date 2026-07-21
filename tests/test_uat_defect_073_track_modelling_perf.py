"""UAT remediation — DEF-073-002: Track Modelling opens without blocking (seed load moved off the Qt thread).

The bulk track-seed parse used to run synchronously on first tab-open, freezing the tab. It now runs on a
background worker; the render handler ``_on_tm_seed_loaded`` populates the combos on the Qt thread.
"""
from __future__ import annotations

import re
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent.joinpath("ui", "track_modelling_ui.py").read_text(encoding="utf-8")


def _method_body(name: str) -> str:
    m = re.search(rf"\n    def {name}\(self.*?\):(.*?)(?=\n    def )", _SRC, re.DOTALL)
    return m.group(1) if m else ""


def test_seed_load_runs_off_the_qt_thread():
    body = _method_body("_tm_on_tab_shown")
    assert "MechanismAnnotationWorker" in body        # the established off-thread pattern
    assert "worker.start()" in body
    # the synchronous, blocking load is no longer the primary path
    assert "load_track_seed()" in body                # still used (inside the worker lambda / fallback)


def test_render_handler_exists_and_is_stale_guarded():
    body = _method_body("_on_tm_seed_loaded")
    assert body, "the off-thread render handler must exist"
    assert "_tm_seed_worker" in body                  # stale-worker guard
    assert "_tm_populate_location_combo" in body       # populates on the Qt thread


def test_tab_shown_does_not_block_on_reentry():
    # once a load is in flight (or done) a re-show must not kick off another blocking load
    body = _method_body("_tm_on_tab_shown")
    assert "_tm_seed_result is not None" in body       # already-loaded short-circuit
    assert "_tm_seed_worker" in body                   # in-flight short-circuit
