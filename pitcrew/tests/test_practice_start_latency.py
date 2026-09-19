"""What made "Start practice" take sixteen seconds, pinned so it cannot return.

Measured on 19 Sep 2026 with `tools/practice_start_bench.py`, interleaved
against the base commit: 16.5 s from the press to the session live, of which

* **12.0 s** was the gauge pre-flight deadlocking with the Qt thread -
  `find_projector` asked the app's OWN windows for their titles from a worker
  while the Qt thread, which owns them, sat in `join(12 s)` waiting for that
  worker. It timed out on every one of the 55 starts in the logs;
* **2.0 s** was Windows refusing a connection to a closed loopback port
  slowly (OBS not running), on the Qt thread, once per start - plus the same
  again in the pre-flight's own OBS question;
* **1.6-2.1 s** was the voice model load holding the GIL while
  `listener.start()` and the transducer open waited behind it;
* and on a lap-heavy event, 0.6 s redrawing an unchanged rack and 2.1 s
  decoding lap blobs to arm the qualifying coach and price its fuel call.

Each test below fails on the base commit.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
import types

import pytest

from pitcrew.telemetry import hud

WINDOWS = sys.platform == "win32"


# ------------------------------------------------ the pre-flight deadlock

@pytest.mark.skipif(not WINDOWS, reason="a Win32 window-message deadlock")
def test_the_projector_search_does_not_wait_on_the_thread_that_owns_our_windows():
    """The twelve seconds. A window of THIS process, titled like a projector,
    owned by this (the test's main) thread - exactly what the app's own Qt
    windows are to the pre-flight worker. The main thread then blocks in
    `join`, as `HudSession._bounded` does. Before the fix the worker's
    `GetWindowText` sent WM_GETTEXT to this blocked thread and could not
    return until the join gave up."""
    win32gui = pytest.importorskip("win32gui")
    hwnd = win32gui.CreateWindow(
        "STATIC", "Windowed Projector (Program) - ours", 0,
        0, 0, 64, 64, 0, 0, 0, None)
    out: list = []
    worker = threading.Thread(target=lambda: out.append(hud.find_projector()),
                              daemon=True)
    try:
        started = time.perf_counter()
        worker.start()
        worker.join(timeout=3.0)
        waited = time.perf_counter() - started
        assert not worker.is_alive(), (
            "find_projector blocked on a window owned by the joining thread")
        assert waited < 1.0
        found, _why = out[0]
        # Ours is never the projector, whatever else is open on the machine.
        assert found is None or found[0] != hwnd
    finally:
        win32gui.DestroyWindow(hwnd)
        # Release a worker the old code left parked in SendMessage.
        win32gui.PumpWaitingMessages()
        worker.join(timeout=2.0)


class _FakeWin32:
    """Just enough of `win32gui` for `find_projector`, recording who was
    asked for a title."""

    def __init__(self, windows: dict):
        self.windows = windows
        self.asked: list[int] = []

    def EnumWindows(self, visit, extra):          # noqa: N802 - Win32 name
        for hwnd in self.windows:
            visit(hwnd, extra)

    def GetWindowText(self, hwnd):                # noqa: N802
        self.asked.append(hwnd)
        return self.windows[hwnd]

    def IsWindowVisible(self, hwnd):              # noqa: N802
        return True


def test_our_own_windows_are_skipped_before_their_title_is_asked(monkeypatch):
    fake = _FakeWin32({1: "Windowed Projector (Program)",
                       2: "Windowed Projector (Program)"})
    monkeypatch.setitem(sys.modules, "win32gui", fake)
    monkeypatch.setattr(hud, "_window_pid",
                        lambda hwnd: os.getpid() if hwnd == 1 else 4242)
    found, why = hud.find_projector()
    assert why is None and found[0] == 2
    assert 1 not in fake.asked, "the title of our own window was asked for"


# ---------------------------------------------- OBS closed costs 2 s, not 0.25

def _closed_loopback_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_a_closed_obs_is_known_in_a_quarter_second_not_two():
    """Windows retries a SYN to a closed loopback port and refuses ~2.0 s
    later; a listening socket answers in microseconds."""
    obs = hud.ObsSource("127.0.0.1", _closed_loopback_port(), "")
    for ask in (obs.recording, obs.start_recording, obs.grab):
        started = time.perf_counter()
        got, why = ask()
        assert time.perf_counter() - started < 1.0
        assert got is None
        assert "nothing is listening" in why


def test_the_probe_hands_over_a_connected_socket_to_a_listening_obs():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    try:
        sock, why = hud._loopback_socket("127.0.0.1",
                                         server.getsockname()[1])
        assert why is None and sock is not None
        sock.close()
    finally:
        server.close()


def test_a_remote_obs_keeps_the_ordinary_connect():
    """Only loopback gets the short answer; a LAN is not a kernel."""
    assert hud._loopback_socket("192.168.1.20", 4455) == (None, None)
    assert hud._loopback_socket("obs-pc.local", 4455) == (None, None)


def test_a_listening_obs_is_driven_through_the_probed_socket():
    """End to end against a stand-in obs-websocket 5 server: hello, identify,
    two requests - over the one connection the probe opened."""
    ws_server = pytest.importorskip("websockets.sync.server")
    import json

    seen: list[str] = []
    connections: list[int] = []

    def handler(ws):
        connections.append(1)
        ws.send(json.dumps({"op": 0, "d": {"rpcVersion": 1}}))
        json.loads(ws.recv())
        ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
        for message in ws:
            request = json.loads(message)["d"]
            seen.append(request["requestType"])
            data = ({"outputActive": False}
                    if request["requestType"] == "GetRecordStatus" else {})
            ws.send(json.dumps({"op": 7, "d": {
                "requestId": request["requestId"],
                "requestType": request["requestType"],
                "requestStatus": {"result": True, "code": 100},
                "responseData": data}}))

    with ws_server.serve(handler, "127.0.0.1", 0) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        port = server.socket.getsockname()[1]
        started, why = hud.ObsSource("127.0.0.1", port, "").start_recording()
        server.shutdown()
    assert (started, why) == (True, None)
    assert seen == ["GetRecordStatus", "StartRecord"]
    assert connections == [1]


# ------------------------------------------- the recording, off the Qt thread

class _SlowObs:
    """An OBS that takes `delay` to answer StartRecord."""
    delay = 0.4
    starts: list = []
    stops: list = []

    def __init__(self, *_a):
        pass

    def start_recording(self):
        time.sleep(self.delay)
        _SlowObs.starts.append(time.monotonic())
        return True, None

    def stop_recording(self):
        _SlowObs.stops.append(time.monotonic())
        return "C:/videos/x.mp4", None


class _VideoStore:
    def __init__(self):
        self.video: dict = {}

    def set_session_video(self, session_id, *, path, started_at):
        self.video[session_id] = (path, started_at)

    def get_session(self, session_id):
        path, started = self.video.get(session_id, (None, None))
        return {"video_started_at": started}


def _session(monkeypatch, store=None):
    from pitcrew.telemetry.hud_session import HudSession

    _SlowObs.starts, _SlowObs.stops = [], []
    monkeypatch.setattr(hud, "ObsSource", _SlowObs)
    settings = types.SimpleNamespace(
        obs_record_sessions=True, obs_host="127.0.0.1", obs_port=4455,
        obs_password="", hud_wear_enabled=False)
    return HudSession(settings=settings, store=store or _VideoStore())


def test_starting_the_recording_does_not_hold_the_button(monkeypatch):
    store = _VideoStore()
    session = _session(monkeypatch, store)
    started = time.perf_counter()
    session.start_video(7)
    assert time.perf_counter() - started < 0.1
    assert session.video_settled(timeout_s=3.0)
    # The zero is still stamped, at the moment OBS said it was recording.
    path, stamp = store.video[7]
    assert path is None and stamp
    session.stop_video(7)
    assert len(_SlowObs.stops) == 1
    assert store.video[7][0] == "C:/videos/x.mp4"
    assert store.video[7][1] == stamp, "the zero must survive the stop"


def test_a_stop_waits_for_a_start_still_in_flight(monkeypatch):
    """Otherwise the close finds nothing started and OBS records all night."""
    session = _session(monkeypatch)
    session.start_video(8)
    session.stop_video(8)                  # immediately - the start is in flight
    assert len(_SlowObs.starts) == 1 and len(_SlowObs.stops) == 1


def test_a_start_that_lands_after_the_close_stops_itself(monkeypatch):
    from pitcrew.telemetry import hud_session

    monkeypatch.setattr(hud_session, "VIDEO_START_WAIT_S", 0.05)
    store = _VideoStore()
    session = _session(monkeypatch, store)
    session.start_video(9)
    session.stop_video(9)                  # gives up waiting after 50 ms
    assert _SlowObs.stops == []
    assert session.video_settled(timeout_s=3.0)
    assert len(_SlowObs.stops) == 1, "the late start was left recording"
    assert 9 not in store.video, "a closed session was given a video zero"


# ------------------------------------------------------ the voice model

def test_the_throwaway_synthesis_runs_once_per_process():
    """Every session start calls `warm()`; only the first has anything to
    warm. The rest are a cached load and nothing else."""
    from pitcrew.engineer.voice import PiperEngine

    engine = PiperEngine.__new__(PiperEngine)
    engine._voice = object()
    engine._load_lock = threading.Lock()
    runs: list[str] = []
    engine.synthesise = lambda text: (runs.append(text) or iter(()))
    engine.warm()
    engine.warm()
    engine.warm()
    assert len(runs) == 1


# ----------------------------------------------------------- frame memo

def _recorded_frames(seconds: float = 10.0, speed: float = 50.0):
    from pitcrew.telemetry.recorder import LapRecorder

    from .conftest import make_packet

    recorder = LapRecorder()
    for i in range(int(seconds * 60)):
        recorder.record_frame(make_packet(packet_id=i, speed_ms=speed))
    return recorder.take_lap()


def _a_lap(num: int, ms: int):
    from pitcrew.telemetry.session_state import Lap

    return Lap(lap_num=num, lap_time_ms=ms, best_lap_ms=ms, delta_ms=0,
               fuel_start=60.0 - num, fuel_end=59.0 - num, fuel_used=1.0,
               position=1, is_pit_lap=False, is_out_lap=False)


def test_the_same_bytes_are_decoded_once(store, event_id, monkeypatch):
    from pitcrew.race.qualifying import reference_lap
    from pitcrew.race.temps import measured_temp_window
    from pitcrew.store import frame_memo

    frame_memo.clear()
    session = store.start_session(event_id, "practice")
    for num in range(1, 5):
        store.add_lap(session, _a_lap(num, 10_000 + num),
                      frames=_recorded_frames())
    decodes: list[int] = []
    real = store.decode_lap_frames_row
    monkeypatch.setattr(store, "decode_lap_frames_row",
                        lambda row: decodes.append(1) or real(row))

    cold = (measured_temp_window(store, event_id),
            reference_lap(store, event_id))
    first = len(decodes)
    assert first > 0
    warm = (measured_temp_window(store, event_id),
            reference_lap(store, event_id))
    assert len(decodes) == first, "the same bytes were decoded twice"
    assert warm == cold


def test_new_bytes_for_a_lap_are_worked_out_again(store, event_id):
    """A lap rewritten offline has different bytes and must not be served
    the old answer - the memo keys on content, so there is nothing to
    invalidate."""
    from pitcrew.race.qualifying import reference_lap
    from pitcrew.store import frame_memo

    frame_memo.clear()
    session = store.start_session(event_id, "practice")
    lap_id = store.add_lap(session, _a_lap(1, 10_000),
                           frames=_recorded_frames(speed=50.0))
    before = reference_lap(store, event_id)
    faster = _recorded_frames(speed=60.0)
    store._conn.execute(
        "UPDATE lap_frames SET blob = ?, frame_count = ? WHERE lap_id = ?",
        (faster.blob, faster.frame_count, lap_id))
    store._conn.commit()
    after = reference_lap(store, event_id)
    assert after.total_m == pytest.approx(before.total_m * 1.2, rel=0.02)


def test_a_lap_without_frames_is_not_an_answer(store, event_id):
    from pitcrew.store import frame_memo

    session = store.start_session(event_id, "practice")
    lap_id = store.add_lap(session, _a_lap(1, 10_000))
    assert frame_memo.derived(store, lap_id, "x",
                              lambda stored: 1) is frame_memo.NO_FRAMES


# ------------------------------------------------------------- the rack

@pytest.fixture(scope="module")
def qt_app():
    pytest.importorskip("PyQt6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    # Held for the module: an application nobody references is collected,
    # and the next widget built takes the process down with it.
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def practice_screen(qt_app):
    from pitcrew.ui.practice_screen import PracticeScreen

    return PracticeScreen()


def _rows(n: int = 6):
    from pitcrew.ui.practice_screen import LapRow

    return [LapRow(lap_id=i, lap_num=i, lap_time_ms=100_000 + i,
                   fuel_used=2.0, fuel_start=60.0 - 2 * i,
                   fuel_end=58.0 - 2 * i, compound="RM", session_id=1)
            for i in range(1, n + 1)]


def _count_rebuilds(screen, monkeypatch) -> list:
    calls: list = []
    real = screen._rebuild_rack
    monkeypatch.setattr(screen, "_rebuild_rack",
                        lambda: calls.append(1) or real())
    return calls


def test_the_same_laps_again_do_not_redraw_the_rack(practice_screen,
                                                    monkeypatch):
    practice_screen.set_laps(_rows())
    drawn = practice_screen._rows
    rebuilds = _count_rebuilds(practice_screen, monkeypatch)
    practice_screen.set_laps(_rows())       # what `open_practice_session` does
    assert rebuilds == []
    # The widgets hold these objects; the rack must keep reading them.
    assert practice_screen._rows is drawn
    assert [w.row for w in practice_screen._row_widgets] == drawn


def test_a_changed_lap_still_redraws(practice_screen, monkeypatch):
    practice_screen.set_laps(_rows())
    rebuilds = _count_rebuilds(practice_screen, monkeypatch)
    changed = _rows()
    changed[2].compound = "RS"
    practice_screen.set_laps(changed)
    assert rebuilds == [1]
    more = _rows(7)
    practice_screen.set_laps(more)
    assert rebuilds == [1, 1]


def test_a_row_mutated_under_the_widgets_still_redraws(practice_screen,
                                                       monkeypatch):
    """`repaint_rows` exists because the controller mutates the rows the
    widgets hold. The rows then equal a fresh read from the store while the
    widgets show the old value - so equality with the LIVE rows is not
    enough, and the check is against what was drawn."""
    practice_screen.set_laps(_rows())
    practice_screen._rows[1].compound = "RH"
    rebuilds = _count_rebuilds(practice_screen, monkeypatch)
    fresh = _rows()
    fresh[1].compound = "RH"
    practice_screen.set_laps(fresh)
    assert rebuilds == [1]


def test_new_personal_bests_still_redraw(practice_screen, monkeypatch):
    practice_screen.set_laps(_rows())
    practice_screen._personal_bests = {None: {"lap_ms": 99_000}}
    rebuilds = _count_rebuilds(practice_screen, monkeypatch)
    practice_screen.set_laps(_rows())
    assert rebuilds == [1]


# ------------------------------------------------ the idle pre-warm, wired

@pytest.fixture()
def window(qt_app, store):
    from pitcrew.app import PitCrewWindow

    made = PitCrewWindow(store)
    yield made
    made.controller.shutdown()


def _pump(qt_app, until, seconds: float = 3.0) -> None:
    deadline = time.perf_counter() + seconds
    while not until() and time.perf_counter() < deadline:
        qt_app.processEvents()
        time.sleep(0.005)


def test_the_launch_pre_warms_the_voice_and_the_board_once(qt_app, window,
                                                          monkeypatch):
    """Wired from the window, not left for a caller to remember: the last
    `warm_screens` turn schedules it. Before this the voice model loaded on
    the Practice button and on the grid, holding the GIL for ~1.5 s."""
    from pitcrew import app as app_module

    monkeypatch.setattr(app_module, "PREWARM_DELAY_MS", 0)
    ctrl = window.controller
    warmed: list[int] = []
    monkeypatch.setattr(ctrl.voice, "warm", lambda: warmed.append(1))
    ctrl.settings.driver_board_enabled = True
    assert ctrl.driver_board is None
    window.warm_screens()
    _pump(qt_app, lambda: warmed and ctrl.driver_board is not None)
    assert warmed == [1]
    board = ctrl.driver_board
    assert board is not None and not board.isVisible(), (
        "the board is built hidden - it is shown by the session, not the "
        "launch")
    ctrl.prewarm_for_sessions()
    window.warm_screens()
    _pump(qt_app, lambda: False, seconds=0.2)
    assert warmed == [1], "the pre-warm ran twice"
    assert ctrl.driver_board is board


def test_a_board_built_early_opens_where_he_left_it(qt_app, window):
    """Built at idle, placed at open - from the geometry as it is THEN."""
    ctrl = window.controller
    ctrl.settings.driver_board_enabled = True
    ctrl.prewarm_for_sessions()
    placed: list[str] = []
    ctrl.driver_board.restore_geometry = placed.append
    ctrl.settings.driver_board_geometry = "10,20,300,200"
    ctrl._open_driver_board()
    try:
        assert placed == ["10,20,300,200"]
        ctrl._open_driver_board()          # a second session: not re-placed
        assert placed == ["10,20,300,200"]
    finally:
        ctrl._close_driver_board()


def test_the_frame_prefetch_waits_for_the_pre_warm_and_never_runs_in_a_session(
        qt_app, window, store, event_id, monkeypatch):
    from pitcrew.store import frame_memo

    ctrl = window.controller
    store.set_state("active_event_id", event_id)
    started: list[str] = []

    class _Done:
        def is_alive(self):
            return False

    monkeypatch.setattr(frame_memo, "prefetch",
                        lambda work, name: started.append(name) or _Done())
    ctrl._prefetch_event_frames()
    assert started == [], "a decode was started beside the launch"
    ctrl._prewarmed = True
    ctrl.session_id = 99
    ctrl._prefetch_event_frames()
    assert started == [], "a decode was started during a session"
    ctrl.session_id = None
    ctrl._prefetch_event_frames()
    assert started == [f"event-{event_id}"]


# --------------------------------------------- the qualifying fuel call

def test_the_fuel_call_is_worked_out_off_the_button_and_still_said(
        qt_app, window, monkeypatch):
    ctrl = window.controller
    said: list[str] = []
    monkeypatch.setattr(ctrl.voice, "say",
                        lambda text, *a, **k: said.append(text))
    monkeypatch.setattr(ctrl.practice, "coach_speaks", lambda: True)
    worker_threads: list[str] = []

    def line(event):
        worker_threads.append(threading.current_thread().name)
        time.sleep(0.2)
        return "Qualifying fuel: 17 litres."

    monkeypatch.setattr(ctrl, "_quali_fuel_line", line)
    _pump(qt_app, lambda: False, seconds=0.2)      # let first paint land
    ctrl.session_id = 41
    ctrl.practice.set_status("Listening on 33740.")
    started = time.perf_counter()
    ctrl._announce_quali_fuel({"id": 1})
    assert time.perf_counter() - started < 0.05
    _pump(qt_app, lambda: said)
    ctrl.session_id = None
    assert said == ["Qualifying fuel: 17 litres."]
    assert worker_threads == ["quali-fuel"]
    # Beside the start's status, not over it.
    assert ctrl.practice.status_text() == (
        "Listening on 33740. Qualifying fuel: 17 litres.")


def test_a_fuel_call_for_a_closed_session_is_not_said(qt_app, window,
                                                      monkeypatch):
    """Rule 11: worked out for session 41, landing in session 42."""
    ctrl = window.controller
    said: list[str] = []
    monkeypatch.setattr(ctrl.voice, "say",
                        lambda text, *a, **k: said.append(text))
    monkeypatch.setattr(ctrl.practice, "coach_speaks", lambda: True)
    ctrl.session_id = 42
    ctrl._on_quali_fuel_said(41, "Qualifying fuel: 17 litres.")
    ctrl.session_id = None
    assert said == []
