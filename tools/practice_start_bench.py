"""How long does "Start practice" take, and where does the time go?

A measurement harness, not product code. It builds the real window against the
database next to the tree it is pointed at, lets it settle the way it does
while the driver sits on the Practice screen, then presses the real button and
times everything up to the session being live:

* ``click``      - the press until the Qt thread is free again (the window is
                   frozen for exactly this long);
* ``first_packet`` - the press until the bridge has taken its first packet off
                   the new listener (the session is recording);
* ``live``       - the later of the two, which is what the driver waits for.

Every step of the start path is wrapped with a timer, so the output is a
waterfall rather than one number. Nothing reaches the console, the speakers or
OBS: a fake PS5 on loopback answers the heartbeat, every spoken line is
recorded instead of said, and the gauge question is answered "go out anyway"
and counted.

Usage (from the tree being measured, or with ``--root``)::

    python tools/practice_start_bench.py --root <tree> --intent practice
    python tools/practice_start_bench.py --root <tree> --intent qualifying

**Never point it at the live checkout.** It refuses a database that is not
under ``--root``, and ``--root`` must not be the main checkout.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import struct
import sys
import threading
import time
from pathlib import Path

T_PROCESS = time.perf_counter()


def parse() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    p.add_argument("--intent", default="practice",
                   choices=("practice", "qualifying"))
    p.add_argument("--settle", type=float, default=8.0,
                   help="seconds the window idles before the press")
    p.add_argument("--platform", default="windows")
    p.add_argument("--profile", default="")
    p.add_argument("--out", default="")
    p.add_argument("--label", default="")
    p.add_argument("--projector", action="store_true",
                   help="open a stand-in 'Windowed Projector (Program)' "
                        "window in another process, so the gauge pre-flight "
                        "finds one - the race-night setup")
    p.add_argument("--ab", default="",
                   help="interleave against the tree at this path")
    p.add_argument("--pairs", type=int, default=6)
    p.add_argument("--second", action="store_true",
                   help="time the second start of the launch, not the first")
    p.add_argument("--gap", type=float, default=None,
                   help="with --second: seconds from the stop to the timed "
                        "press (default --settle). The last 0.3 s of it is "
                        "the CPU-load sample")
    p.add_argument("--first-session", type=float, default=2.0,
                   help="with --second: how long the untimed session runs")
    p.add_argument("--cold-memo", action="store_true",
                   help="with --second: forget the frame memo just before "
                        "the stop, as if the session had written new laps - "
                        "so the stop's prefetch has real decoding to do")
    p.add_argument("--event", type=int, default=None,
                   help="switch to this event before settling")
    p.add_argument("--no-voice-warm", action="store_true",
                   help="experiment: skip the voice warm-up at the press")
    p.add_argument("--dump-at", type=float, nargs="*", default=[],
                   help="print the Qt thread's stack this many ms after "
                        "the press")
    return p.parse_args()


ARGS = parse()


def interleave() -> None:
    """`--ab BASE --pairs N`: run base and this tree alternately, N pairs,
    each in its own process, and print every pair's delta. The arm that goes
    first alternates, so a drift in machine load cannot favour one."""
    import statistics
    import subprocess
    import tempfile

    here = Path(__file__).resolve()
    arms = {"base": Path(ARGS.ab).resolve(),
            "change": Path(ARGS.root).resolve()}
    passthrough = list(sys.argv[1:])
    for flag in ("--ab", "--pairs", "--root", "--out", "--label"):
        while flag in passthrough:
            at = passthrough.index(flag)
            del passthrough[at:at + 2]
    rows = []
    out_dir = Path(tempfile.mkdtemp(prefix="practice-ab-"))
    for pair in range(ARGS.pairs):
        order = ("base", "change") if pair % 2 == 0 else ("change", "base")
        got = {}
        for arm in order:
            out = out_dir / f"{pair}-{arm}.json"
            child = subprocess.Popen(
                [sys.executable, str(here), "--root", str(arms[arm]),
                 "--out", str(out), "--label", arm, *passthrough],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # The result file is the end of the measurement. A child that is
            # still tearing down (a serial port closing, a decode thread)
            # 10 s after writing it is our own process and is ended here.
            deadline = time.monotonic() + 240
            written = None
            while child.poll() is None and time.monotonic() < deadline:
                if out.exists() and written is None:
                    written = time.monotonic()
                if written is not None and time.monotonic() - written > 10:
                    break
                time.sleep(0.2)
            if child.poll() is None:
                child.kill()
                try:
                    child.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    # Measured already; a teardown that outlives a kill must
                    # not lose the rest of the run.
                    print(f"  (child {child.pid} still exiting after kill)",
                          flush=True)
            got[arm] = json.loads(out.read_text(encoding="utf-8"))
        b, c = got["base"], got["change"]
        rows.append((b["live_ms"], c["live_ms"]))
        fuel = (f"  fuel call {b.get('fuel_call_ms')} -> "
                f"{c.get('fuel_call_ms')} ms" if b.get("fuel_call_ms") else "")
        print(f"pair {pair} ({order[0]} first): base live {b['live_ms']} ms "
              f"(click {b['click_ms']}, cpu {b['cpu_load_pct']}%)  change "
              f"live {c['live_ms']} ms (click {c['click_ms']}, cpu "
              f"{c['cpu_load_pct']}%)  delta "
              f"{c['live_ms'] - b['live_ms']:+.1f}{fuel}", flush=True)
    deltas = [c - b for b, c in rows]
    same = all(d < 0 for d in deltas) or all(d > 0 for d in deltas)
    print(f"median base {statistics.median(b for b, _ in rows):.1f} ms, "
          f"median change {statistics.median(c for _, c in rows):.1f} ms, "
          f"median delta {statistics.median(deltas):+.1f} ms, "
          f"all same sign: {same}  (raw results in {out_dir})", flush=True)


if ARGS.ab:
    interleave()
    raise SystemExit(0)
ROOT = Path(ARGS.root).resolve()
if ROOT == Path("C:/Projects/VR_Dashboard").resolve():
    raise SystemExit("refusing to measure against the live checkout")
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
os.environ["QT_QPA_PLATFORM"] = ARGS.platform


# ------------------------------------------------------------ fake console

def encrypted(packet_bytes: bytes, iv1: int = 0x0BADC0DE) -> bytes:
    from Crypto.Cipher import Salsa20

    nonce = struct.pack("<II", iv1 ^ 0xDEADBEEF, iv1)
    buffer = bytearray(Salsa20.new(key=b"Simulator Interface Packet GT7 v",
                                   nonce=nonce).encrypt(packet_bytes))
    struct.pack_into("<I", buffer, 64, iv1)
    return bytes(buffer)


def menu_packet() -> bytes:
    """A car sitting in the pits menu: no speed, not on track - so nothing on
    the rig (transducer, fans) has anything to do."""
    from pitcrew.telemetry.packet import PACKET_SIZE_NEW

    buffer = bytearray(b"0S7G" + bytes(PACKET_SIZE_NEW - 4))
    struct.pack_into("<f", buffer, 0x44, 60.0)        # fuel_level
    struct.pack_into("<f", buffer, 0x48, 100.0)       # fuel_capacity
    return bytes(buffer)


class FakeConsole(threading.Thread):
    """Streams at 60 Hz to whoever heartbeats it, like the real one."""

    def __init__(self, payload: bytes) -> None:
        super().__init__(daemon=True)
        self.payload = payload
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.settimeout(1 / 60)
        self.port = self.sock.getsockname()[1]
        self.asked_by = None
        self.stop_flag = threading.Event()

    def run(self) -> None:
        while not self.stop_flag.is_set():
            try:
                _data, sender = self.sock.recvfrom(64)
                self.asked_by = sender
            except socket.timeout:
                pass
            except OSError:
                pass
            if self.asked_by:
                try:
                    self.sock.sendto(self.payload, self.asked_by)
                except OSError:
                    pass


def free_udp_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# ------------------------------------------------------------------ timers

STEPS: list[tuple[str, float, float, str]] = []   # name, start, end, thread
_T0 = [0.0]


def timed(owner, name: str, label: str | None = None) -> None:
    real = getattr(owner, name)

    def wrapper(*a, **k):
        start = time.perf_counter()
        try:
            return real(*a, **k)
        finally:
            STEPS.append((label or name, start, time.perf_counter(),
                          threading.current_thread().name))

    setattr(owner, name, wrapper)


def main() -> int:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication

    from pitcrew import diagnostics
    from pitcrew.store import db as db_module

    db_path = Path(db_module.DEFAULT_DB_PATH).resolve()
    if ROOT not in db_path.parents:
        raise SystemExit(f"database {db_path} is not under {ROOT}")

    diagnostics.install()
    import pitcrew.controller as controller_module
    import pitcrew.telemetry.listener as listener_module
    from pitcrew import settings as settings_module
    from pitcrew.app import PitCrewWindow
    from pitcrew.engineer import ptt
    from pitcrew.engineer.voice import Voice
    from pitcrew.store.db import Store
    from pitcrew.ui import theme

    said: list[tuple[float, str]] = []

    def say(self, text, *a, **k):
        said.append((time.perf_counter(), str(text)))
        return True

    def say_all(self, lines, *a, **k):
        for line in lines:
            said.append((time.perf_counter(), str(line)))
        return True

    Voice.say = say
    if ARGS.no_voice_warm:
        Voice.warm = lambda self: None
    Voice.say_all = say_all

    projector = None
    if ARGS.projector:
        import subprocess
        projector = subprocess.Popen([
            sys.executable, "-c",
            "import tkinter as tk; r = tk.Tk(); "
            "r.title('Windowed Projector (Program)'); "
            "r.geometry('1720x916+40+40'); r.after(120000, r.destroy); "
            "r.mainloop()"])
    console = FakeConsole(encrypted(menu_packet()))
    console.start()
    listener_module.GT7_HEARTBEAT_PORT = console.port
    stream_port = free_udp_port()
    controller_module.GT7_STREAM_PORT = stream_port
    real_listener = controller_module.UDPListener

    class TimedListener(real_listener):
        def __init__(self, *a, **k):
            start = time.perf_counter()
            super().__init__(*a, **k)
            STEPS.append(("UDPListener()", start, time.perf_counter(),
                          threading.current_thread().name))

        def start(self):
            start = time.perf_counter()
            super().start()
            STEPS.append(("listener.start", start, time.perf_counter(),
                          threading.current_thread().name))

    controller_module.UDPListener = TimedListener

    app = QApplication(sys.argv)
    theme.apply(app)
    store = Store(db_module.DEFAULT_DB_PATH)
    warm = ptt.start_warm_up(settings_module.load(store).speech_backend)
    window = PitCrewWindow(store, warm=warm)
    window.show()
    QTimer.singleShot(0, window.warm_screens)
    ctrl = window.controller

    # The console on loopback rather than the real PS5.
    ctrl.settings.feed_source = settings_module.FEED_PS5
    ctrl.settings.ps5_ip = "127.0.0.1"

    asked: list[str] = []

    def confirm(what, check):
        asked.append(f"{check.source}: {check.reason}")
        return True

    ctrl.confirm_without_gauge = confirm

    # Idle on the practice screen, the way he does before pressing Start.
    window.rail.select(2)
    if ARGS.event is not None:
        pump_until = time.perf_counter() + 1.0
        while time.perf_counter() < pump_until:
            app.processEvents()
            time.sleep(0.005)
        ctrl.switch_event(ARGS.event)
    settle_until = time.perf_counter() + ARGS.settle
    while time.perf_counter() < settle_until:
        app.processEvents()
        time.sleep(0.005)

    picker = window.practice_screen.intent_picker if hasattr(
        window.practice_screen, "intent_picker") else None
    if ARGS.intent == "qualifying":
        from pitcrew.ui.practice_screen import FOR_QUALIFYING  # noqa: F401
        screen = window.practice_screen
        for attr in ("intent_picker", "practising_picker", "purpose_picker"):
            box = getattr(screen, attr, None)
            if box is None:
                continue
            for i in range(box.count()):
                if box.itemData(i) == FOR_QUALIFYING:
                    box.setCurrentIndex(i)
        assert screen.practice_intent() == FOR_QUALIFYING, "intent not set"
    del picker

    if ARGS.second:
        # One untimed start and stop first, so the timed press is the
        # SECOND session of the launch - what every start after the first
        # one of an evening costs.
        window.practice_screen.record_button.click()
        pump_until = time.perf_counter() + ARGS.first_session
        while time.perf_counter() < pump_until:
            app.processEvents()
            time.sleep(0.005)
        if ARGS.cold_memo:
            try:
                from pitcrew.store import frame_memo
                frame_memo.clear()
            except ImportError:          # the base commit has no memo
                pass
        ctrl.stop_practice()
        gap = ARGS.settle if ARGS.gap is None else ARGS.gap
        pump_until = time.perf_counter() + max(0.0, gap - 0.3)
        while time.perf_counter() < pump_until:
            app.processEvents()
            time.sleep(0.005)

    for name in ("gauge_preflight_ok", "open_practice_session",
                 "_start_video", "_new_hud_session", "start_haptics",
                 "start_wind", "_open_driver_board", "announce",
                 "_arm_board_live", "_arm_quali", "_rows_for_event",
                 "_tell_settings_about_the_session", "_announce_quali_fuel"):
        if hasattr(ctrl, name):
            timed(ctrl, name)
    timed(ctrl.store, "start_session", "store.start_session")
    timed(ctrl.store, "shift_points_for", "store.shift_points_for")
    timed(ctrl.practice, "set_laps", "practice.set_laps")
    timed(ctrl.voice, "warm", "voice.warm")
    timed(ctrl.ptt, "start", "ptt.start")
    timed(ctrl._health, "start", "health.start")
    timed(ctrl.bridge, "reset", "bridge.reset")
    timed(ctrl.bridge, "take_corner_means", "bridge.take_corner_means")
    timed(ctrl._splits, "new_session", "splits.new_session")
    timed(ctrl.hud, "preflight", "hud.preflight")
    timed(ctrl, "_push_driver_board")
    board = ctrl.__dict__.get("driver_board")
    if board is not None:
        timed(board, "show", "driver_board.show")
        timed(board, "raise_", "driver_board.raise_")

    first_packet = [None]
    real_on_packet = ctrl.bridge.on_packet

    def on_packet(data, *a, **k):
        if first_packet[0] is None and ctrl.session_id is not None:
            first_packet[0] = time.perf_counter()
        return real_on_packet(data, *a, **k)

    ctrl.bridge.on_packet = on_packet

    profiler = None
    if ARGS.profile:
        import cProfile
        profiler = cProfile.Profile()

    cpu = _cpu_load()
    try:
        from pitcrew.store import frame_memo
        memo_before = frame_memo.stats()
    except ImportError:
        frame_memo, memo_before = None, None
    running = ctrl.__dict__.get("_frame_prefetch")
    prefetch_running = bool(running is not None and running.is_alive())
    # Whether the launch's Piper load (a ~1.5 s GIL hold) had finished before
    # the press - a slow run with it still loading is the pre-warm landing on
    # the button, not the button's own cost.
    engine = getattr(getattr(ctrl, "voice", None), "_engine", None)
    # The phrase pack wraps a fallback pair that wraps Piper; find the engine
    # that loads a model, a few wrappers deep.
    layer = [engine] if engine is not None else []
    engine = None
    for _depth in range(4):
        engine = next((e for e in layer if hasattr(e, "_voice")), None)
        if engine is not None:
            break
        layer = [v for e in layer for v in getattr(e, "__dict__", {}).values()
                 if hasattr(v, "__dict__")]
    voice_loaded = None if engine is None else engine._voice is not None
    press = time.perf_counter()
    _T0[0] = press
    # Every garbage-collector pass from here on that took over 10 ms, with
    # the thread it ran on: a pass is one uninterruptible hold of the GIL.
    import gc
    gc_passes: list = []
    gc_start = [0.0]

    def gc_timer(phase, info):
        if phase == "start":
            gc_start[0] = time.perf_counter()
            return
        took = (time.perf_counter() - gc_start[0]) * 1000
        if took > 10:
            gc_passes.append((round((gc_start[0] - press) * 1000, 1),
                              round(took, 1), info.get("generation"),
                              threading.current_thread().name))

    gc.callbacks.append(gc_timer)
    if ARGS.dump_at:
        main_id = threading.main_thread().ident

        def dump():
            import traceback
            for at in ARGS.dump_at:
                time.sleep(max(0.0, press + at / 1000 - time.perf_counter()))
                names = {t.ident: t.name for t in threading.enumerate()}
                for ident, frame in sys._current_frames().items():
                    if ident == threading.get_ident():
                        continue
                    print(f"--- {names.get(ident, ident)} at +{at} ms ---",
                          file=sys.stderr)
                    traceback.print_stack(frame, limit=8, file=sys.stderr)

        threading.Thread(target=dump, daemon=True).start()
    if profiler:
        profiler.enable()
    window.practice_screen.record_button.click()
    if profiler:
        profiler.disable()
        profiler.dump_stats(ARGS.profile)
    returned = time.perf_counter()
    recording = ctrl.session_id is not None
    deadline = returned + 20.0
    while first_packet[0] is None and time.perf_counter() < deadline:
        app.processEvents()
        time.sleep(0.001)
    first_idle = time.perf_counter()
    fuel_call = None
    if ARGS.intent == "qualifying":
        # The fuel call is the last thing the start says; wait for it.
        until = time.perf_counter() + 15.0
        while time.perf_counter() < until and fuel_call is None:
            for t, line in said:
                if t >= press and "ualifying fuel" in line:
                    fuel_call = t
            app.processEvents()
            time.sleep(0.002)

    result = {
        "label": ARGS.label,
        "second": ARGS.second,
        "projector": ARGS.projector,
        "root": str(ROOT),
        "intent": ARGS.intent,
        "cpu_load_pct": cpu,
        "own_cpu_pct_of_a_core": OWN_CPU[0],
        "recording": recording,
        "click_ms": round((returned - press) * 1000, 1),
        "first_packet_ms": (round((first_packet[0] - press) * 1000, 1)
                            if first_packet[0] else None),
        "live_ms": (round((max(first_packet[0], returned) - press) * 1000, 1)
                    if first_packet[0] else None),
        "fuel_call_ms": (round((fuel_call - press) * 1000, 1)
                         if fuel_call else None),
        "gauge_asked": asked,
        "said": [(round((t - press) * 1000, 1), s) for t, s in said
                 if t >= press],
        "steps": [(n, round((s - press) * 1000, 1), round((e - s) * 1000, 1),
                   th) for n, s, e, th in sorted(STEPS, key=lambda x: x[1])],
        "session_id": ctrl.session_id,
        "event_id": (ctrl.active_event() or {}).get("id") if hasattr(
            ctrl.active_event() or {}, "get") else None,
        "rack_rows": len(ctrl.practice.rows()),
        "prefetch_running_at_press": prefetch_running,
        "voice_loaded_at_press": voice_loaded,
        "memo_before": memo_before,
        "memo_after": frame_memo.stats() if frame_memo else None,
        "gc_passes_over_10ms": gc_passes,
    }
    del first_idle

    # Close the session the way the button does, then the window.
    try:
        ctrl.stop_practice()
    except Exception as exc:                                  # noqa: BLE001
        result["stop_error"] = f"{type(exc).__name__}: {exc}"
    window.close()
    console.stop_flag.set()
    if projector is not None:
        projector.kill()
    text = json.dumps(result, indent=1)
    if ARGS.out:
        Path(ARGS.out).write_text(text, encoding="utf-8")
    print(text)
    sys.stdout.flush()
    os._exit(0)


def _cpu_load() -> float | None:
    """Whole-machine CPU busy % over 0.3 s, from GetSystemTimes."""
    try:
        import ctypes
        from ctypes import wintypes

        def sample():
            idle, kernel, user = (wintypes.FILETIME(), wintypes.FILETIME(),
                                  wintypes.FILETIME())
            ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
            as_int = lambda f: (f.dwHighDateTime << 32) | f.dwLowDateTime  # noqa: E731
            return as_int(idle), as_int(kernel), as_int(user)

        def own():
            times = [wintypes.FILETIME() for _ in range(4)]
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [
                ctypes.POINTER(wintypes.FILETIME)] * 4
            k32.GetProcessTimes(k32.GetCurrentProcess(),
                                *(ctypes.byref(t) for t in times))
            as_int = lambda f: (f.dwHighDateTime << 32) | f.dwLowDateTime  # noqa: E731
            return as_int(times[2]) + as_int(times[3])     # kernel + user

        i0, k0, u0 = sample()
        o0, w0 = own(), time.perf_counter()
        time.sleep(0.3)
        i1, k1, u1 = sample()
        o1, w1 = own(), time.perf_counter()
        # THIS process's CPU over the same window, in cores (100 = one core
        # flat out): says whether a busy machine is us or somebody else.
        OWN_CPU[0] = round(100.0 * (o1 - o0) / 1e7 / (w1 - w0), 1)
        total = (k1 - k0) + (u1 - u0)          # kernel time includes idle
        return round(100.0 * (total - (i1 - i0)) / total, 1) if total else None
    except Exception:                                          # noqa: BLE001
        return None


OWN_CPU: list = [None]


if __name__ == "__main__":
    raise SystemExit(main())
