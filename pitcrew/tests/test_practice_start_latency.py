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


class _SilentSocket:
    """A loopback socket nobody answers: records what it was told, then
    fails its connect the way the caller says."""
    made: list = []

    def __init__(self, family, kind, fail):
        self.family, self.kind, self.fail = family, kind, fail
        self.timeouts: list = []
        self.connected_to = None
        self.closed = False
        _SilentSocket.made.append(self)

    def settimeout(self, value):
        self.timeouts.append(value)

    def fileno(self):
        return -1

    def connect(self, address):
        self.connected_to = address
        raise self.fail

    def close(self):
        self.closed = True


@pytest.mark.parametrize("fail", [socket.timeout("timed out"),
                                  ConnectionRefusedError(10061, "refused")])
def test_a_closed_obs_is_answered_by_the_bounded_probe(monkeypatch, fail):
    """Windows re-sends a SYN to a closed loopback port and refuses ~2.0 s
    later (measured 2,014-2,027 ms). Every OBS question goes through the
    probe, with `OBS_LOOPBACK_ANSWER_S` set BEFORE the connect, and a silent
    or refusing port ends the question there: no websocket, not even its
    import. Asserted on the mechanism, not on a clock - a loaded machine
    moves a clock, and did (1.48 s under the full suite)."""
    _SilentSocket.made = []
    monkeypatch.setattr(socket, "socket",
                        lambda family, kind: _SilentSocket(family, kind, fail))
    # Importing the websocket client now would raise ImportError, and the
    # answer would say "not installed" instead.
    monkeypatch.setitem(sys.modules, "websockets.sync.client", None)
    obs = hud.ObsSource("127.0.0.1", 4455, "")
    for ask in (obs.recording, obs.start_recording, obs.grab):
        got, why = ask()
        assert got is None
        assert "nothing is listening on 127.0.0.1:4455" in why, why
    assert len(_SilentSocket.made) == 3
    for made in _SilentSocket.made:
        assert made.timeouts[:1] == [hud.OBS_LOOPBACK_ANSWER_S]
        assert made.connected_to == ("127.0.0.1", 4455)
        assert made.closed


@pytest.mark.skipif(not WINDOWS, reason="a Windows TCP stack behaviour")
def test_a_closed_loopback_port_is_refused_not_waited_out():
    """The two seconds are SYN re-sends after the loopback RST; the probe
    turns them off (`SIO_TCP_INITIAL_RTO`), so a closed port takes the
    REFUSED branch - not the 0.25 s timeout, which is only its backstop."""
    probe = socket.socket()
    try:
        assert hud._refuse_on_first_rst(probe), "the ioctl did not take"
    finally:
        probe.close()
    sock, why = hud._loopback_socket("127.0.0.1", _closed_loopback_port())
    assert sock is None
    assert "(refused on loopback)" in why, why


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
    pytest.importorskip("piper")
    from pitcrew.engineer.voice import PiperEngine

    engine = PiperEngine("not-loaded.onnx")
    engine._voice = object()               # as if loaded: nothing is read
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


def _frames_lap(store, event_id):
    session = store.start_session(event_id, "practice")
    return store.add_lap(session, _a_lap(1, 10_000),
                         frames=_recorded_frames(seconds=2.0))


def test_two_askers_of_the_same_bytes_decode_them_once(store, event_id):
    """A prefetch still decoding when the start asks for the same lap: the
    start waits for that answer rather than decode it beside the prefetch."""
    from pitcrew.store import frame_memo

    frame_memo.clear()
    lap_id = _frames_lap(store, event_id)
    inside, release = threading.Event(), threading.Event()
    computed: list[str] = []

    def slow(stored):
        computed.append(threading.current_thread().name)
        inside.set()
        release.wait(5.0)
        return ("means", len(stored["frames"]))

    got: dict = {}
    first = threading.Thread(
        target=lambda: got.update(
            a=frame_memo.derived(store, lap_id, "k", slow)),
        name="prefetch-like")
    first.start()
    assert inside.wait(5.0)
    second = threading.Thread(
        target=lambda: got.update(
            b=frame_memo.derived(store, lap_id, "k", slow)),
        name="button-like")
    second.start()
    deadline = time.monotonic() + 5.0
    while frame_memo.stats()["waits"] < 1 and time.monotonic() < deadline:
        time.sleep(0.001)
    assert frame_memo.stats()["waits"] == 1, "the second asker did not wait"
    release.set()
    first.join(5.0)
    second.join(5.0)
    assert computed == ["prefetch-like"], "the same bytes were decoded twice"
    assert got["a"] == got["b"]


def test_a_failed_first_asker_leaves_the_second_to_work_it_out(
        store, event_id):
    from pitcrew.store import frame_memo

    frame_memo.clear()
    lap_id = _frames_lap(store, event_id)
    inside, release = threading.Event(), threading.Event()

    def broken(stored):
        inside.set()
        release.wait(5.0)
        raise RuntimeError("a bad blob")

    errors: list = []

    def first():
        try:
            frame_memo.derived(store, lap_id, "k", broken)
        except RuntimeError as exc:
            errors.append(exc)

    thread = threading.Thread(target=first)
    thread.start()
    assert inside.wait(5.0)
    got: list = []
    waiter = threading.Thread(target=lambda: got.append(
        frame_memo.derived(store, lap_id, "k", lambda stored: "worked")))
    waiter.start()
    deadline = time.monotonic() + 5.0
    while frame_memo.stats()["waits"] < 1 and time.monotonic() < deadline:
        time.sleep(0.001)
    release.set()
    thread.join(5.0)
    waiter.join(5.0)
    assert errors and got == ["worked"]


def test_a_stood_down_prefetch_stops_before_its_next_decode(store, event_id):
    """The session start stands the prefetch down: the blob in hand is
    finished and filed, nothing after it is decoded."""
    from pitcrew.store import frame_memo

    frame_memo.clear()
    session = store.start_session(event_id, "practice")
    laps = [store.add_lap(session, _a_lap(n, 10_000 + n),
                          frames=_recorded_frames(seconds=2.0))
            for n in (1, 2, 3)]
    inside, release = threading.Event(), threading.Event()
    decoded: list[int] = []

    def compute(lap_id):
        def run(stored):
            decoded.append(lap_id)
            inside.set()
            release.wait(5.0)
            return lap_id
        return run

    def work():
        for lap_id in laps:
            frame_memo.derived(store, lap_id, "k", compute(lap_id))

    running = frame_memo.prefetch(work, name="test")
    assert inside.wait(5.0)
    running.cancel()
    release.set()
    running.join(5.0)
    assert not running.is_alive()
    assert decoded == [laps[0]]
    # The one in hand was filed: the next asker finds it.
    assert frame_memo.derived(store, laps[0], "k",
                              lambda stored: "again") == laps[0]


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


def test_a_change_never_stored_is_not_kept_on_the_rack(practice_screen,
                                                       monkeypatch):
    """The live rows were changed in place and the fresh read is what was
    drawn - the change never reached the store. Skipping would keep the live
    objects, and with them a compound the store does not have."""
    practice_screen.set_laps(_rows())
    practice_screen._rows[1].compound = "RH"      # in place, never stored
    rebuilds = _count_rebuilds(practice_screen, monkeypatch)
    practice_screen.set_laps(_rows())             # the store: still RM
    assert rebuilds == [1]
    assert practice_screen._rows[1].compound == "RM"
    assert practice_screen._row_widgets[1].row.compound == "RM"


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


def test_a_pre_warm_that_fires_after_the_first_press_does_nothing(
        qt_app, window, monkeypatch):
    """Under load the deferred screens can outlast his wait before the first
    press (seen at 86 % machine load: nothing prefetched at the press). The
    start has paid it all by then; the pre-warm must not then run beside the
    session - the websocket import is a Qt-thread stutter mid-race. It still
    counts as done, so the prefetch works after the session."""
    import builtins

    ctrl = window.controller
    warmed: list[int] = []
    imported: list[str] = []
    monkeypatch.setattr(ctrl.voice, "warm", lambda: warmed.append(1))
    real = builtins.__import__
    monkeypatch.setattr(
        builtins, "__import__",
        lambda name, *a, **k: imported.append(name) or real(name, *a, **k))
    ctrl.settings.driver_board_enabled = True
    ctrl.session_id = 77
    try:
        ctrl.prewarm_for_sessions()
    finally:
        ctrl.session_id = None
        monkeypatch.setattr(builtins, "__import__", real)
    assert warmed == []
    assert ctrl.driver_board is None
    assert "websockets.sync.client" not in imported
    assert ctrl._prewarmed, "the prefetch after the session would never run"


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


def test_a_refused_start_gets_its_prefetch_back_while_the_old_one_winds_down(
        qt_app, window, store, event_id, monkeypatch):
    """The start stood the prefetch down, then the pre-flight refused. The
    stood-down thread may still be finishing its last blob - it must not
    count as 'one already running', or the resume is swallowed and the
    rest of the event is never prefetched. One that is running and NOT
    stood down still does."""
    from pitcrew.store import frame_memo

    ctrl = window.controller
    store.set_state("active_event_id", event_id)
    started: list[str] = []
    monkeypatch.setattr(frame_memo, "prefetch",
                        lambda work, name: started.append(name) or running)
    ctrl._prewarmed = True
    ctrl.session_id = None
    running = _RunningPrefetch()
    running.cancelled = False
    ctrl._frame_prefetch = running
    try:
        ctrl._prefetch_event_frames()
        assert started == [], "two prefetches ran at once"
        running.cancelled = True           # stood down, still alive
        ctrl._prefetch_event_frames()
        assert started == [f"event-{event_id}"]
    finally:
        ctrl._frame_prefetch = None
        ctrl._prewarmed = False


class _RunningPrefetch:
    def __init__(self):
        self.cancelled = 0

    def is_alive(self):
        return True

    def cancel(self):
        self.cancelled += 1


@pytest.mark.parametrize("start", ["start_practice", "start_race"])
def test_a_session_start_stands_the_prefetch_down_first(qt_app, window,
                                                        monkeypatch, start):
    """Before the pre-flight, before anything else: whatever the start does
    next, no prefetch decode runs beside it."""
    ctrl = window.controller
    running = _RunningPrefetch()
    ctrl._frame_prefetch = running
    seen: list[int] = []

    def refuse(what):
        seen.append(running.cancelled)
        return False

    monkeypatch.setattr(ctrl, "gauge_preflight_ok", refuse)
    resumed: list[int] = []
    monkeypatch.setattr(ctrl, "_prefetch_event_frames",
                        lambda: resumed.append(1))
    try:
        getattr(ctrl, start)()
    finally:
        ctrl._frame_prefetch = None
    assert running.cancelled == 1
    assert seen in ([], [1]), "the pre-flight ran beside a live prefetch"
    # Refused, so nothing opened: the prefetch is let carry on.
    assert resumed == [1]


def test_the_pre_warm_imports_the_obs_client(qt_app, window, monkeypatch):
    """The import, not a connection - so the first pre-flight of a launch
    with OBS running does not pay it inside the Qt-joined worker."""
    import builtins

    ctrl = window.controller
    monkeypatch.setattr(ctrl.voice, "warm", lambda: None)
    ctrl.settings.driver_board_enabled = False
    imported: list[str] = []
    real = builtins.__import__

    def record(name, *a, **k):
        imported.append(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", record)
    ctrl.prewarm_for_sessions()
    monkeypatch.setattr(builtins, "__import__", real)
    assert "websockets.sync.client" in imported


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


# ------------------------------------- the last run's debrief, in the next run

def _a_debrief():
    from pitcrew.analysis.debrief import Burn, Census, Debrief, Pace

    return Debrief(
        census=Census(recorded=16, out_laps=3, in_laps=0, excluded=0,
                      excursions=2, analysed=11),
        pace=Pace(n=13, median_ms=106_042, best_ms=104_306, sd_ms=2083.0),
        burn=Burn(n=13, median_l=7.55, sd_l=0.27),
        scatter=(), gears=(), correlations=(), silences=())


def test_a_debrief_landing_in_the_next_session_is_not_said(qt_app, window,
                                                           monkeypatch):
    """Rule 11. The debrief starts when a run closes and takes 2.5-9.4 s on a
    big event; with the button now answering in ~0.1 s a new run can open
    inside that. Its findings are not spoken over the new run's coach, nor
    written over its status."""
    ctrl = window.controller
    said: list = []
    monkeypatch.setattr(ctrl.voice, "say_all",
                        lambda lines, *a, **k: said.extend(lines))
    ctrl._engineer_speaks = True
    ctrl.practice.set_status("Listening on 33740.")
    ctrl.session_id = 43
    try:
        ctrl._on_debriefed(_a_debrief())
    finally:
        ctrl.session_id = None
    assert said == []
    assert ctrl.practice.status_text() == "Listening on 33740."
    # With no session open it is still said and shown, as before.
    ctrl._on_debriefed(_a_debrief())
    assert any("11 laps analysed" in line for line in said)
    assert "11 laps analysed" in ctrl.practice.status_text()


def test_a_debrief_can_be_stood_down():
    """Every store call of the build goes through the stand-down check, so it
    stops within one lap's decode."""
    from pitcrew.analysis.debrief import DebriefCancelled, from_store

    class _Store:
        def get_event(self, event_id):
            raise AssertionError("asked the store after the stand-down")

    with pytest.raises(DebriefCancelled):
        from_store(_Store(), 1, cancelled=lambda: True)


def test_the_corner_analysis_stands_down_between_corners():
    """The corners are pure Python with no store call for the proxy to catch
    - 0.75 s on event 1. A stand-down is honoured at the next corner, and a
    build that is not stood down gives the same answer as before."""
    from pitcrew.analysis.debrief import DebriefCancelled, analyse
    from pitcrew.tests.test_debrief import _BURN, _PACE, MODEL, _census, _lap

    laps = [(_lap(i, t1_min=90.0 + i, t2_min=120.0 - i), 90_000 + i * 100)
            for i in range(1, 9)]
    asked: list[int] = []

    def cancelled():
        asked.append(1)
        return len(asked) > 1          # let the first corner through

    with pytest.raises(DebriefCancelled):
        analyse(MODEL, laps, census=_census(8), pace=_PACE, burn=_BURN,
                cancelled=cancelled)
    assert len(asked) == 2, "not asked once per corner"
    kept = analyse(MODEL, laps, census=_census(8), pace=_PACE, burn=_BURN,
                   cancelled=lambda: False)
    assert kept == analyse(MODEL, laps, census=_census(8), pace=_PACE,
                           burn=_BURN)


class _FramesStore:
    """Hands out a fresh decoded frame list per lap, as the real store does."""

    def __init__(self):
        self.handed: list[list] = []

    def get_lap_frames(self, lap_id):
        frames = [{"t_ms": i, "speed_kph": 100.0} for i in range(500)]
        self.handed.append(frames)
        return {"sample_hz": 60.0, "frames": frames}


@pytest.mark.parametrize("ending", ["finished", "stood down"])
def test_the_debrief_frees_its_frames_a_lap_at_a_time(monkeypatch, ending):
    """1,356 ms: the Qt thread frozen at the end of every debrief on event 1
    while CPython freed 176 decoded laps in ONE deallocation cascade (701 ms
    when a Start stood it down 9 s in). Every frame list the build decoded
    is emptied by hand, one lap per step, however the build ends - so no
    single free is bigger than one lap's."""
    from pitcrew.analysis import debrief

    source = _FramesStore()
    freed_in_order: list[int] = []

    def build(store, event_id, *, session_ids, cancelled):
        for lap_id in (1, 2, 3):
            store.get_lap_frames(lap_id)
        # What the build is holding when it ends: every lap, decoded.
        assert [len(f) for f in source.handed] == [500, 500, 500]
        if ending == "stood down":
            raise debrief.DebriefCancelled("mid-build")
        return "built"

    real_release = debrief._Cancellable.release

    def release(self):
        # Record the lists' sizes as each one is emptied.
        while self._decoded:
            frames = self._decoded.pop()
            frames.clear()
            freed_in_order.append(sum(len(f) for f in source.handed))
        real_release(self)

    monkeypatch.setattr(debrief, "_build", build)
    monkeypatch.setattr(debrief._Cancellable, "release", release)
    if ending == "finished":
        assert debrief.from_store(source, 1) == "built"
    else:
        with pytest.raises(debrief.DebriefCancelled):
            debrief.from_store(source, 1, cancelled=lambda: False)
    assert all(frames == [] for frames in source.handed)
    # One lap at a time: 1,000 dicts left, then 500, then none.
    assert freed_in_order == [1000, 500, 0]


def test_releasing_hands_the_gil_over_after_every_lap(monkeypatch):
    """`sleep(0)` was not enough: the freeing thread took the GIL straight
    back, and a Start 10 s after a stop on event 1 still took 0.66-1.0 s.
    A real sleep after every lap took it to 0.15-0.19 s."""
    from pitcrew.analysis import debrief

    slept: list[float] = []
    real_sleep, me = time.sleep, threading.current_thread()

    def sleep(seconds):
        # `time.sleep` is the process's: any other thread still sleeps.
        if threading.current_thread() is me:
            slept.append(seconds)
        else:
            real_sleep(seconds)

    monkeypatch.setattr(debrief.time, "sleep", sleep)
    proxy = debrief._Cancellable(_FramesStore())
    for lap_id in (1, 2, 3):
        proxy.get_lap_frames(lap_id)
    proxy.release()
    assert slept == [debrief.RELEASE_YIELD_S] * 3
    assert debrief.RELEASE_YIELD_S > 0


def test_releasing_empties_only_what_this_build_decoded():
    from pitcrew.analysis.debrief import _Cancellable

    source = _FramesStore()
    elsewhere = source.get_lap_frames(9)["frames"]      # not via the proxy
    proxy = _Cancellable(source)
    mine = proxy.get_lap_frames(1)["frames"]
    proxy.release()
    assert mine == [] and len(elsewhere) == 500


def test_a_debrief_not_stood_down_sees_the_store_unchanged(store, event_id):
    """The app now always builds the debrief through the stand-down proxy,
    so until the stand-down it must BE the store: every attribute and method
    the store's own, answering the same. Checked on the real store over an
    event, then the same proxy flipped."""
    from pitcrew.analysis.debrief import DebriefCancelled, _Cancellable

    flag = {"down": False}
    proxy = _Cancellable(store, lambda: flag["down"])
    assert proxy.get_event == store.get_event          # the same bound method
    assert proxy.get_event(event_id) == store.get_event(event_id)
    assert proxy.list_sessions(event_id) == store.list_sessions(event_id)
    flag["down"] = True
    with pytest.raises(DebriefCancelled):
        proxy.get_event(event_id)


def test_opening_a_session_stands_the_last_debrief_down(qt_app, window, store,
                                                        event_id):
    ctrl = window.controller
    store.set_state("active_event_id", event_id)
    ctrl.load_active_event()
    stop = threading.Event()
    ctrl._debrief_stop = stop
    try:
        assert ctrl.open_practice_session() is not None
        assert stop.is_set(), "the last run's debrief went on decoding"
        assert ctrl._debrief_stop is None
    finally:
        if ctrl.session_id is not None:
            store.end_session(ctrl.session_id)
        ctrl.session_id = None
        ctrl.session_kind = None


def test_a_refused_start_keeps_the_last_debrief(qt_app, window, monkeypatch):
    """Refused before the session row exists: nothing opened, so the debrief
    of the run he just stopped is still built and said."""
    ctrl = window.controller
    stop = threading.Event()
    ctrl._debrief_stop = stop
    monkeypatch.setattr(ctrl, "gauge_preflight_ok", lambda what: False)
    ctrl.start_practice()
    assert not stop.is_set()
    ctrl._debrief_stop = None
