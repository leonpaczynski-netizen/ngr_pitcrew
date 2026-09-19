"""Interleaved A/B launch timing: a baseline checkout against a changed one.

    python tools/launch_ab.py <baseline_root> <change_root> <pairs> <out.json>

Each launch is a fresh process running `tools/launch_probe.py` (next to this
file) against one root - the real `pitcrew.app.main()`, closed by the probe
once the window has settled. Pairs alternate their order (A,B then B,A), so
neither arm always goes first into a warm file cache.

**Both roots must be sandboxes**: git worktrees with their own copy of
`data/pitcrew.db`, `config.json`, the speech and voice models. The probe opens
`<root>/data/pitcrew.db`.

Machine load is recorded twice per launch from GetSystemTimes: over the
second BEFORE it (is the machine quiet?) and over the launch itself. Other
agents share this machine; a pair whose `cpu_during` is far above the rest is
contention, not the code. Report every pair's delta, the median, and whether
every pair has the same sign.

The first launch of a fresh worktree compiles bytecode and pages the models
in from disk - discard a round 0 before running this.
"""
import ctypes
import json
import os
import statistics
import subprocess
import sys
import time
from ctypes import wintypes

HERE = os.path.dirname(os.path.abspath(__file__))
PROBE = os.path.join(HERE, "launch_probe.py")
HOLD_MS = "4500"
METRICS = ("shown", "first_paint", "settled", "speech_ready")


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


def launch(arm, root, index, scratch):
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


def main() -> None:
    base_root, change_root = sys.argv[1], sys.argv[2]
    pairs, out = int(sys.argv[3]), sys.argv[4]
    scratch = os.path.dirname(os.path.abspath(out))
    rows = []
    for index in range(pairs):
        order = [("A", base_root), ("B", change_root)]
        if index % 2:
            order.reverse()
        pair = {arm: launch(arm, root, index, scratch)
                for arm, root in order}
        rows.append(pair)
        a, b = pair["A"], pair["B"]
        print(f"pair {index}: A paint {a['first_paint']:5d} settled "
              f"{a['settled']:5d} cpu {a['cpu_before']}/{a['cpu_during']}% | "
              f"B paint {b['first_paint']:5d} settled {b['settled']:5d} "
              f"speech {b['speech_ready']:5d} cpu {b['cpu_before']}/"
              f"{b['cpu_during']}% | delta paint "
              f"{b['first_paint'] - a['first_paint']:+6d} settled "
              f"{b['settled'] - a['settled']:+6d}", flush=True)
    summary = {}
    for metric in METRICS:
        deltas = [p["B"][metric] - p["A"][metric] for p in rows]
        summary[metric] = {
            "A_median": statistics.median(p["A"][metric] for p in rows),
            "B_median": statistics.median(p["B"][metric] for p in rows),
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
