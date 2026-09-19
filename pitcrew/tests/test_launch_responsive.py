"""The window answers from the moment it appears - round 2 of the launch work.

Measured 19 Sep 2026 from OUTSIDE the process (`tools/launch_ab.py`: the
real `pythonw -m pitcrew.app`, its window pinged with WM_NULL every 10 ms
beside the taskbar as a control). What each test here pins:

* **The Car screen's freeze** after the window appeared (300-700 ms) was a
  fallback font: sizing all 608 rows of its picker hit four car names with a
  katakana dot, and Qt spent ~290 ms finding a Japanese face. `uniform_rows`
  sizes one row.
* **The first glyph Bahnschrift lacks** - any, once - costs Qt 170-400 ms.
  `pitcrew.boot` has a Qt worker pay it during the imports, in C++, with no
  font touched on the Qt thread (`font_warm`).
* **Screens are built containers-first**, so no label is re-polished once
  per level it is moved: Car 64 -> 18 ms, Event 84-109 -> 37-65, Settings
  64-71 -> 21-33, Reference 47-72 -> 14-19.
* **The phone strip's server starts after the first paint**, not on the path
  to it - and still exactly once, and never after shutdown.
* **Moonshine runs one ONNX thread per session** - 2.7-3.0 s of load became
  1.3, the wait after the second tap 335-354 ms became 95-120, and the
  desktop stopped stuttering while the models loaded.

Qt's offscreen platform has no fonts, so nothing here times anything. These
pin the mechanisms and the guarantees; the timings are `launch_ab`'s.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("PyQt6.QtWidgets")

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def qt_app():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _pump_until(qt_app, done, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while not done() and time.monotonic() < deadline:
        qt_app.processEvents()
        time.sleep(0.002)
    qt_app.processEvents()
    return done()


# ------------------------------------------------------------- the pickers

def test_a_picker_sizes_one_row_not_six_hundred(qt_app):
    """The Car screen's freeze. Without uniform rows the view sizes every
    row to lay itself out - and one car name with a glyph the face lacks is
    enough to load a fallback face on the Qt thread."""
    from pitcrew.store import catalogs
    from pitcrew.ui.widgets import Picker

    picker = Picker(placeholder="Pick a car",
                    groups=list(catalogs.cars_by_category().items()))
    assert picker.combo.view().uniformItemSizes()


def test_the_cascading_car_picker_does_the_same(qt_app):
    from pitcrew.ui.widgets import CascadingPicker

    picker = CascadingPicker([], placeholder="Pick a car")
    for combo in (picker.category_combo, picker.maker_combo,
                  picker.car_combo):
        assert combo.view().uniformItemSizes()


def test_uniform_rows_leaves_the_rows_and_the_value_alone(qt_app):
    """Rows are sized, not changed: the same items, the same data, the same
    selection, headings still unselectable."""
    from pitcrew.ui.widgets import Picker

    picker = Picker(placeholder="Pick", groups=[("Gr.3", ["A car", "B car"]),
                                                ("Gr.4", ["C car"])])
    assert picker.items() == ["A car", "B car", "C car"]
    picker.setCurrentText("B car")
    assert picker.currentText() == "B car"
    heading = picker.combo.model().item(1)
    assert heading is not None and not heading.isEnabled()


# ------------------------------------------------ containers before contents

def _page_order(screen) -> list[str]:
    page = screen.layout()
    kinds = []
    for i in range(page.count()):
        item = page.itemAt(i)
        kinds.append("widget" if item.widget() is not None
                     else "layout" if item.layout() is not None else "space")
    return kinds


def test_the_car_screen_keeps_its_order_and_every_editor(qt_app):
    """Built top-down now - header, columns, footer, in that order, and every
    range key with both its editors, exactly as before."""
    from pitcrew.setup.vocabulary import RANGE_KEY_NAMES
    from pitcrew.ui.car_screen import CarScreen

    screen = CarScreen()
    assert _page_order(screen) == ["layout", "layout", "widget"]
    columns = screen.layout().itemAt(1).layout()
    assert columns.count() == 2
    assert columns.stretch(0) == 3 and columns.stretch(1) == 5
    assert set(screen._min_editors) == set(RANGE_KEY_NAMES)
    assert set(screen._max_editors) == set(RANGE_KEY_NAMES)
    assert screen.footer_note is not None
    assert screen.car_edit.items()


def test_the_car_screen_measures_the_label_column_once(qt_app, monkeypatch):
    from pitcrew.ui.car_screen import CarScreen

    calls = []
    original = CarScreen._label_column_width

    def counted(self):
        calls.append(1)
        return original(self)

    monkeypatch.setattr(CarScreen, "_label_column_width", counted)
    CarScreen()
    assert len(calls) == 1


def test_the_event_screen_keeps_its_order(qt_app):
    from pitcrew.ui.event_screen import EventScreen

    screen = EventScreen()
    # Header row, the scrolled plates (stretch 1), the footer.
    assert _page_order(screen) == ["layout", "widget", "widget"]
    assert screen.layout().stretch(1) == 1
    assert screen.left_scroller.widget() is not None
    assert screen.footer_note is not None
    assert screen.event_picker is not None


def test_the_settings_screen_keeps_its_order(qt_app):
    from pitcrew.ui.settings_screen import SettingsScreen

    screen = SettingsScreen()
    # Header, the scroller holding both columns, the footer outside it.
    assert _page_order(screen) == ["layout", "widget", "widget"]
    body = screen.layout().itemAt(1).widget().widget()
    columns = body.layout()
    assert columns.count() == 2
    assert columns.stretch(0) == 1 and columns.stretch(1) == 1


def test_the_reference_screen_keeps_its_order(qt_app):
    from pitcrew.ui.reference_screen import ReferenceScreen

    screen = ReferenceScreen()
    # Header, the filter field, then the scroller with every section.
    assert _page_order(screen) == ["layout", "widget", "widget"]
    assert screen.layout().stretch(2) == 1
    sections = screen._reference.get("sections") or []
    assert len(screen._plates) == len(sections)


def test_the_window_is_built_parent_first_in_the_same_order(qt_app, store):
    """Rail then stack in the row, seven wide, the shell central."""
    from pitcrew.app import SCREENS, PitCrewWindow

    window = PitCrewWindow(store)
    try:
        row = window.centralWidget().layout()
        assert row.itemAt(0).widget() is window.rail
        assert row.itemAt(1).widget() is window.stack
        assert window.stack.count() == len(SCREENS)
        assert window.event_screen.parent() is window.stack
    finally:
        window.controller.shutdown()


# ------------------------------------------------------------ the strip

class _StripSpy:
    def __init__(self, monkeypatch):
        from pitcrew.controller import PitCrewController

        self.starts = 0

        def start(controller):
            self.starts += 1

        monkeypatch.setattr(PitCrewController, "_start_strip", start)


def test_the_window_holds_the_strip_until_the_launch_finishes(
        qt_app, store, monkeypatch):
    from pitcrew.app import PitCrewWindow

    spy = _StripSpy(monkeypatch)
    window = PitCrewWindow(store)
    try:
        assert spy.starts == 0, "the strip started on the path to the window"
        window.finish_launch()
        assert spy.starts == 1
        window.finish_launch()
        assert spy.starts == 1, "started twice"
    finally:
        window.controller.shutdown()


def test_the_warm_chain_starts_the_strip_at_its_end(qt_app, store,
                                                    monkeypatch):
    from pitcrew.app import PitCrewWindow

    spy = _StripSpy(monkeypatch)
    window = PitCrewWindow(store)
    try:
        window.warm_screens()
        assert _pump_until(qt_app, lambda: spy.starts == 1)
        assert window.car_screen is not None
        assert window.settings_screen is not None
    finally:
        window.controller.shutdown()


def test_a_screen_that_will_not_build_still_starts_the_strip(
        qt_app, store, monkeypatch):
    from pitcrew.app import PitCrewWindow

    spy = _StripSpy(monkeypatch)
    window = PitCrewWindow(store)

    def boom(**_kwargs):
        raise RuntimeError("this screen will not build")

    monkeypatch.setitem(window.LATE_SCREENS, 1,
                        ("car_screen", boom, "attach_car_screen"))
    try:
        window.warm_screens()
        assert _pump_until(qt_app, lambda: spy.starts == 1)
    finally:
        window.controller.shutdown()


def test_a_strip_that_will_not_start_does_not_take_speech_with_it(
        qt_app, store, monkeypatch):
    from pitcrew.app import PitCrewWindow
    from pitcrew.controller import PitCrewController

    def broken(controller):
        raise OSError("port in use")

    monkeypatch.setattr(PitCrewController, "_start_strip", broken)
    window = PitCrewWindow(store)
    released = []
    monkeypatch.setattr(window, "release_speech",
                        lambda: released.append(1))
    try:
        window.finish_launch()
        assert released == [1]
    finally:
        window.controller.shutdown()


def test_a_controller_built_without_the_window_starts_its_strip_as_before(
        qt_app, store, monkeypatch):
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen

    spy = _StripSpy(monkeypatch)
    controller = PitCrewController(store, EventScreen(), PracticeScreen())
    try:
        assert spy.starts == 1
        controller.start_deferred_strip()
        assert spy.starts == 1, "nothing was deferred, nothing more starts"
    finally:
        controller.shutdown()


def test_no_strip_is_started_after_shutdown(qt_app, store, monkeypatch):
    from pitcrew.controller import PitCrewController
    from pitcrew.ui.event_screen import EventScreen
    from pitcrew.ui.practice_screen import PracticeScreen

    spy = _StripSpy(monkeypatch)
    controller = PitCrewController(store, EventScreen(), PracticeScreen(),
                                   defer_strip=True)
    controller.shutdown()
    controller.start_deferred_strip()
    assert spy.starts == 0


# -------------------------------------------------------- the font warm-up

def test_a_font_warm_up_finishes_and_stops_its_thread(qt_app):
    from pitcrew.ui import font_warm, theme

    warm = font_warm.start("Pit Crew −・", theme.text_font(15),
                           "test-warm")
    assert _pump_until(qt_app, warm.done), "the worker never finished"
    font_warm.stop_all()
    assert warm.done()


def test_stop_all_ends_a_worker_that_is_still_waiting(qt_app):
    """The exit path: `main` calls it in its `finally`, and Qt aborts the
    process if a running QThread is ever destroyed."""
    from pitcrew.ui import font_warm, theme

    warm = font_warm.start("x", theme.text_font(15), "test-stop")
    font_warm.stop_all()
    assert warm.done()


def test_the_fallback_text_carries_every_rare_glyph(qt_app):
    from pitcrew import boot
    from pitcrew.store import catalogs

    text = boot.fallback_text()
    assert "−" in text            # the minus of a practice delta
    names = [n for group in catalogs.cars_by_category().values()
             for n in group] + list(catalogs.track_bases())
    rare = {ch for name in names for ch in name if ord(ch) > 0x7F}
    assert rare <= set(text)
    assert "・" in rare or "･" in rare   # the V･spec dot


def _run(code: str, tmp_path, env=None) -> subprocess.CompletedProcess:
    full = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                PYTHONPATH=str(ROOT), **(env or {}))
    return subprocess.run([sys.executable, "-c", code], cwd=tmp_path,
                          env=full, capture_output=True, text=True,
                          timeout=120)


def test_the_early_boot_makes_the_app_and_the_warm_up(tmp_path):
    """In a process of its own: `early()` makes and themes the one
    QApplication, starts the worker, and the process exits cleanly."""
    code = (
        "import time\n"
        "from pitcrew import boot\n"
        "boot.early()\n"
        "from PyQt6.QtWidgets import QApplication\n"
        "from pitcrew.ui import font_warm\n"
        "app = QApplication.instance()\n"
        "assert app is not None and app is boot.APP\n"
        "assert app.styleSheet(), 'not themed'\n"
        "assert len(font_warm._LIVE) == 1\n"
        "deadline = time.monotonic() + 30\n"
        "while not font_warm._LIVE[0].done() and time.monotonic() < deadline:\n"
        "    app.processEvents(); time.sleep(0.005)\n"
        "assert font_warm._LIVE[0].done()\n"
        "font_warm.stop_all()\n"
        "print('ok')\n")
    done = _run(code, tmp_path)
    assert done.returncode == 0, done.stderr
    assert "ok" in done.stdout


def test_importing_the_app_does_not_boot_it(tmp_path):
    """Only `python -m pitcrew.app` runs the early step; tests and tools
    that import the module build their own QApplication as before."""
    done = _run("import pitcrew.app, pitcrew.boot as b\n"
                "from PyQt6.QtWidgets import QApplication\n"
                "assert b.APP is None\n"
                "assert QApplication.instance() is None\n"
                "print('ok')\n", tmp_path)
    assert done.returncode == 0, done.stderr


def test_the_taskbar_id_is_the_one_the_app_claims():
    from pitcrew import app, boot

    assert app.APP_ID == boot.APP_ID == "NextGearRacing.PitCrew"


# ------------------------------------------------------------- moonshine

def test_moonshine_runs_one_onnx_thread_per_session():
    """Read by moonshine.dll when a session is built, so it must be in the
    environment before either model loads - importing ptt sets it."""
    from pitcrew.engineer import ptt

    assert os.environ.get(ptt.MOONSHINE_SINGLE_THREAD) is not None
    assert ptt.MOONSHINE_SINGLE_THREAD == "MOONSHINE_ORT_SINGLE_THREAD"


def test_a_value_set_outside_the_app_wins(tmp_path):
    done = _run("import os\n"
                "from pitcrew.engineer import ptt\n"
                "print(os.environ['MOONSHINE_ORT_SINGLE_THREAD'])\n",
                tmp_path, env={"MOONSHINE_ORT_SINGLE_THREAD": "0"})
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "0"


def test_unset_it_is_one(tmp_path):
    env = {k: v for k, v in os.environ.items()
           if k != "MOONSHINE_ORT_SINGLE_THREAD"}
    full = dict(env, PYTHONPATH=str(ROOT), QT_QPA_PLATFORM="offscreen")
    done = subprocess.run(
        [sys.executable, "-c",
         "import os\nfrom pitcrew.engineer import ptt\n"
         "print(os.environ['MOONSHINE_ORT_SINGLE_THREAD'])\n"],
        cwd=tmp_path, env=full, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "1"


# ------------------------------------------------------ the outside timer

def _launch_ab():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "launch_ab", ROOT / "tools" / "launch_ab.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 pinger")
def test_a_stall_the_taskbar_shared_is_the_machines_not_the_apps():
    ab = _launch_ab()
    pings = [(0.0, 5.0, True), (10.0, 130.0, True), (200.0, 290.0, True)]
    control = [(15.0, 120.0, True), (200.0, 210.0, True)]
    app, machine = ab._stalls(pings, control)
    assert machine == [(10, 120, 105)]       # the taskbar was slow too
    assert app == [(200, 90, 10)]            # only this one was ours


@pytest.mark.skipif(sys.platform != "win32", reason="Win32 pinger")
def test_the_log_run_starts_at_the_first_line_naming_the_pid(tmp_path):
    ab = _launch_ab()
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "pitcrew.log").write_text(
        "old run\n"
        "x Pit Crew launching - pid: 42\n"
        "y startup: QApplication (early)  120 ms since process start\n"
        "z   pid: 42\n"
        "w startup: first paint  800 ms since process start\n",
        encoding="utf-8")
    lines = ab._log_run(str(tmp_path), 42)
    assert lines[0].endswith("pid: 42") and "launching" in lines[0]
    assert len(lines) == 4
