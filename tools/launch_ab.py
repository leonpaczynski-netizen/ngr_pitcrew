"""Interleaved A/B launch timing: a baseline checkout against a changed one.

    python tools/launch_ab.py <baseline_root> <change_root> <pairs> <out.json>
    python tools/launch_ab.py --probe <baseline_root> <change_root> <pairs> <out.json>
    python tools/launch_ab.py --one <root> <out.json>

**Timed from outside the process by default.** Each launch is the real
thing the desktop shortcut runs - `pythonw -m pitcrew.app` in the checkout -
and nothing inside it is replaced or instrumented. From outside:

* `visible` - the first poll (every 5 ms) that finds a visible top-level
  window titled "Next Gear Racing Pit Crew" owned by the process, in ms since
  the process was created (GetProcessTimes).
* `answering` - the first `SendMessageTimeout(WM_NULL)` to that window that
  comes back after it is visible: its message loop is running.
* Stalls - the window is pinged every ~10 ms for the whole hold. A ping that
  takes more than 50 ms is a stall. **A control window is pinged the same
  way at the same time** (the taskbar, `Shell_TrayWnd`): a stall during
  which the control was also slow is the whole machine, not the app, and is
  reported apart (`machine_stalls`) rather than charged to the app.
* `settled` - the end of the last app stall in the hold, or `answering` if
  there was none: the window is up AND answering from then on.
* `speech_ready` - read from the app's own log (the wall-clock stamp of the
  speech warm-up's last line) and converted to ms since process creation.
  A checkout that joins the models before the window has no "finished" line;
  its matcher's "phrase embeddings read" line is used, which both write.

The window is closed with WM_CLOSE `hold_s` after it is visible (the app's
own close path); a process that is still alive 30 s later is killed - only
ever the process this script started.

`--probe` runs the old in-process `tools/launch_probe.py` instead (first
paint and settled as the Qt thread sees them).

**Both roots must be sandboxes**: git worktrees with their own copy of
`data/pitcrew.db`, `config.json`, the speech and voice models. The app opens
`<root>/data/pitcrew.db` and writes `<root>/logs/pitcrew.log`.

Machine load is recorded twice per launch from GetSystemTimes: over the
second BEFORE it (is the machine quiet?) and over the launch itself. Other
agents share this machine; interleave, report every pair's delta, the median,
and whether every pair has the same sign.

The first launch of a fresh worktree compiles bytecode and pages the models
in from disk - discard a round 0 before running this.
"""
import ctypes
import datetime
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "launch_probe.py")
HOLD_MS = "4500"
PROBE_METRICS = ("shown", "first_paint", "settled", "speech_ready")
OUTSIDE_METRICS = ("visible", "answering", "settled", "longest_stall",
                   "speech_ready")
TITLE = "Next Gear Racing Pit Crew"
STALL_MS = 50.0
PING_EVERY_S = 0.010
HOLD_S = 8.0

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
WM_NULL = 0x0000
WM_CLOSE = 0x0010
SMTO_NORMAL = 0x0000
EPOCH_AS_FILETIME = 116444736000000000

user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
    wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]
user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
user32.FindWindowW.restype = wintypes.HWND
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [
    wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR,
                                  ctypes.c_int]
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                 wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]


def _ft(value):
    return (value.dwHighDateTime << 32) | value.dwLowDateTime


def system_times():
    idle, kern, user = (wintypes.FILETIME() for _ in range(3))
    ctypes.windll.kernel32.GetSystemTimes(
        ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
    return (_ft(idle), _ft(kern), _ft(user))


def load_between(a, b):
    busy = (b[1] - a[1]) + (b[2] - a[2])
    return round(100.0 * (busy - (b[0] - a[0])) / busy, 1) if busy else None


def _now_filetime() -> int:
    value = wintypes.FILETIME()
    kernel32.GetSystemTimePreciseAsFileTime(ctypes.byref(value))
    return _ft(value)


def _creation_filetime(handle) -> int:
    times = [wintypes.FILETIME() for _ in range(4)]
    ok = kernel32.GetProcessTimes(wintypes.HANDLE(int(handle)),
                                  *(ctypes.byref(t) for t in times))
    if not ok:
        raise OSError(ctypes.get_last_error(), "GetProcessTimes")
    return _ft(times[0])


def _visible_window(pid: int):
    found = []

    def each(hwnd, _param):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            buffer = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buffer, 256)
            if buffer.value == TITLE:
                found.append(hwnd)
                return False
        return True

    user32.EnumWindows(WNDENUMPROC(each), 0)
    return found[0] if found else None


class Pinger:
    """Ping one window with WM_NULL every ~10 ms; record (sent, back) ms."""

    def __init__(self, hwnd, clock) -> None:
        self.hwnd, self.clock = hwnd, clock
        self.pings: list[tuple[float, float, bool]] = []
        self.halt = threading.Event()
        self._thread = threading.Thread(target=self.run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def join(self, timeout=None) -> None:
        self._thread.join(timeout)

    def run(self) -> None:
        result = ctypes.c_size_t()
        while not self.halt.is_set():
            sent = self.clock()
            ok = user32.SendMessageTimeoutW(self.hwnd, WM_NULL, 0, 0,
                                            SMTO_NORMAL, 5000,
                                            ctypes.byref(result))
            self.pings.append((sent, self.clock(), bool(ok)))
            time.sleep(PING_EVERY_S)


_LOG_STAMP = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d{3}) ")


def _log_run(root: str, pid: int) -> list[str]:
    """This process's lines of `<root>/logs/pitcrew.log`.

    **The log rotates at 2 MB, and a launch can straddle the roll:** its
    first lines in `pitcrew.log.1`, the rest in `pitcrew.log` (seen 20 Sep
    2026 - a launch that came up with speech in 2.6 s read as "no speech").
    The rotated file is read first, then the live one, as one run.
    """
    lines = []
    for name in ("pitcrew.log.1", "pitcrew.log"):
        path = os.path.join(root, "logs", name)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            lines.extend(handle.read().splitlines())
    # The first line naming this pid: the early launch line where there is
    # one (`pitcrew.boot`), else the banner.
    # **The last launch with this pid, from its first line.** Windows reuses
    # pids, and the first match in a long log can be an older launch's,
    # which pulled that launch's lines in too. A launch names its pid twice
    # (the early "launching" line, then the banner), so the last early line
    # is taken where there is one, else the last banner line.
    named = [index for index, line in enumerate(lines)
             if line.rstrip().endswith(f"pid: {pid}")]
    if not named:
        return []
    early = [index for index in named if "launching" in lines[index]]
    return lines[(early or named)[-1]:]


def _stamp_ms(line: str, created_epoch: float):
    match = _LOG_STAMP.match(line)
    if not match:
        return None
    wall = datetime.datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    epoch = wall.timestamp() + int(match.group(2)) / 1000.0
    return round((epoch - created_epoch) * 1000.0)


def _stalls(pings, control):
    """App pings over STALL_MS, split into the app's and the machine's."""
    app, machine = [], []
    for sent, back, _ok in pings:
        took = back - sent
        if took <= STALL_MS:
            continue
        # The control's worst ping that overlapped this one.
        overlap = [c_back - c_sent for c_sent, c_back, _ in control
                   if c_back >= sent and c_sent <= back]
        worst = max(overlap, default=0.0)
        row = (round(sent), round(took), round(worst))
        (machine if worst > STALL_MS else app).append(row)
    return app, machine


def launch_outside(root: str, hold_s: float = HOLD_S) -> dict:
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    env = dict(os.environ, PITCREW_ALLOW_MULTIPLE="1")
    before_quiet = system_times()
    time.sleep(1.0)
    quiet = load_between(before_quiet, system_times())
    before = system_times()
    proc = subprocess.Popen([pythonw, "-m", "pitcrew.app"], cwd=root,
                            env=env)
    created = _creation_filetime(proc._handle)
    created_epoch = (created - EPOCH_AS_FILETIME) / 1e7

    def clock() -> float:
        return (_now_filetime() - created) / 1e4

    control = Pinger(user32.FindWindowW("Shell_TrayWnd", None), clock)
    control.start()
    hwnd, visible = None, None
    deadline = time.monotonic() + 120
    while hwnd is None and time.monotonic() < deadline:
        if proc.poll() is not None:
            break
        hwnd = _visible_window(proc.pid)
        if hwnd is None:
            time.sleep(0.005)
    visible = clock() if hwnd is not None else None
    row = {"root": root, "pid": proc.pid, "cpu_before": quiet}
    if hwnd is None:
        control.halt.set()
        if proc.poll() is None:
            proc.kill()
        row["error"] = "no window"
        return row
    pinger = Pinger(hwnd, clock)
    pinger.start()
    time.sleep(hold_s)
    pinger.halt.set()
    control.halt.set()
    pinger.join(10)
    control.join(10)
    row["cpu_during"] = load_between(before, system_times())
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    try:
        proc.wait(30)
    except subprocess.TimeoutExpired:
        proc.kill()                    # ours, and only ours
        row["killed"] = True
    pings = [p for p in pinger.pings if p[0] >= visible]
    answering = next((back for _s, back, ok in pings if ok), None)
    app_stalls, machine_stalls = _stalls(pings, control.pings)
    settled = answering
    for sent, took, _worst in app_stalls:
        settled = max(settled or 0, sent + took)
    lines = _log_run(root, proc.pid)
    speech = None
    for line in lines:
        if "speech warm-up finished" in line:
            speech = _stamp_ms(line, created_epoch)
    if speech is None:
        for line in lines:
            if "phrase embeddings read" in line:
                speech = _stamp_ms(line, created_epoch)
    marks = {}
    for line in lines:
        found = re.search(r"startup: (.+?)\s+(\d+) ms since process start",
                          line)
        if found:
            marks[found.group(1).strip()] = int(found.group(2))
    # Every `diagnostics.timed_step`: {name: [took ms, ended ms since the
    # process was created]}. Only checkouts that log fast steps have these.
    steps = {}
    for line in lines:
        found = re.search(r"(?<!slow )launch step: (.+?)\s+([\d.]+) ms$", line)
        if found:
            steps[found.group(1).strip()] = [
                float(found.group(2)), _stamp_ms(line, created_epoch)]
    row.update({
        "visible": round(visible),
        "answering": round(answering) if answering is not None else None,
        "settled": round(settled) if settled is not None else None,
        "longest_stall": max((t for _s, t, _w in app_stalls), default=0),
        "speech_ready": speech,
        "app_stalls": app_stalls,
        "machine_stalls": machine_stalls,
        "pings": len(pings),
        "marks": marks,
        "steps": steps})
    return row


def launch_probe(arm, root, index, scratch):
    target = os.path.join(scratch, f"launch_{arm}_{index}.json")
    if os.path.exists(target):
        os.remove(target)
    before_quiet = system_times()
    time.sleep(1.0)
    quiet = load_between(before_quiet, system_times())
    before = system_times()
    subprocess.run([sys.executable, PROBE, root, target, HOLD_MS],
                   cwd=root, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=180)
    during = load_between(before, system_times())
    with open(target, encoding="utf-8") as handle:
        got = json.load(handle)
    marks = dict((name, ms) for name, ms in got["marks"])
    state = got["state"]
    speech = state.get("speech_ready")
    if speech is None:
        # Not landed before the probe closed the window: at least this.
        speech = state.get("finish")
    return {"arm": arm, "cpu_before": quiet, "cpu_during": during,
            "shown": round(marks.get("window shown", 0)),
            "first_paint": round(state.get("first_paint") or 0),
            "settled": round(state.get("settled") or 0),
            "speech_ready": round(speech or 0),
            "marks": {k: round(v) for k, v in marks.items()}}


def _describe(row) -> str:
    if "visible" in row:
        return (f"vis {row['visible']:5d} ans {row['answering']:5d} "
                f"settled {row['settled']:5d} stall {row['longest_stall']:4d} "
                f"speech {row['speech_ready'] or 0:5d} "
                f"cpu {row['cpu_before']}/{row['cpu_during']}%")
    return (f"paint {row['first_paint']:5d} settled {row['settled']:5d} "
            f"speech {row['speech_ready']:5d} "
            f"cpu {row['cpu_before']}/{row['cpu_during']}%")


def main() -> None:
    args = sys.argv[1:]
    if args and args[0] == "--one":
        ctypes.windll.winmm.timeBeginPeriod(1)
        row = launch_outside(args[1])
        with open(args[2], "w", encoding="utf-8") as handle:
            json.dump(row, handle, indent=1)
        print(_describe(row))
        print("app stalls", row["app_stalls"])
        print("machine stalls", row["machine_stalls"])
        print("marks", row["marks"])
        return
    probe = bool(args) and args[0] == "--probe"
    if probe:
        args = args[1:]
    base_root, change_root = args[0], args[1]
    pairs, out = int(args[2]), args[3]
    scratch = os.path.dirname(os.path.abspath(out))
    metrics = PROBE_METRICS if probe else OUTSIDE_METRICS
    ctypes.windll.winmm.timeBeginPeriod(1)
    rows = []
    for index in range(pairs):
        order = [("A", base_root), ("B", change_root)]
        if index % 2:
            order.reverse()
        pair = {}
        for arm, root in order:
            if probe:
                pair[arm] = launch_probe(arm, root, index, scratch)
            else:
                pair[arm] = launch_outside(root)
                pair[arm]["arm"] = arm
        rows.append(pair)
        print(f"pair {index}: A {_describe(pair['A'])} | "
              f"B {_describe(pair['B'])}", flush=True)
        with open(out, "w", encoding="utf-8") as handle:
            json.dump({"rows": rows}, handle, indent=1)
    summary = {}
    for metric in metrics:
        usable = [p for p in rows
                  if p["A"].get(metric) is not None
                  and p["B"].get(metric) is not None]
        deltas = [p["B"][metric] - p["A"][metric] for p in usable]
        if not deltas:
            continue
        summary[metric] = {
            "A_median": statistics.median(p["A"][metric] for p in usable),
            "B_median": statistics.median(p["B"][metric] for p in usable),
            "deltas": deltas,
            "delta_median": statistics.median(deltas),
            "all_same_sign": (all(d < 0 for d in deltas)
                              or all(d > 0 for d in deltas))}
        print(f"{metric:13s} A {summary[metric]['A_median']:7.0f}  "
              f"B {summary[metric]['B_median']:7.0f}  delta median "
              f"{summary[metric]['delta_median']:+7.0f}  same sign "
              f"{summary[metric]['all_same_sign']}  {deltas}")
    with open(out, "w", encoding="utf-8") as handle:
        json.dump({"rows": rows, "summary": summary}, handle, indent=1)


if __name__ == "__main__":
    main()
