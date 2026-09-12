"""What the driver can actually FEEL, by frequency - the floor under the knock curve.

`rig_knock_curve.py` maps the ceiling: where the transducer runs out of travel.
This maps the floor: where a tone stops being perceptible. **Usable range is the
gap between them**, and that gap - not loudness - is what a cue has to carry
severity in. A cue with 3 dB of range is a switch; one with 25 dB is an
instrument. Effects get placed by which frequencies have the widest gap, with
the CRITICAL cues taking the best of it.

**Binary judgements, not ratings.** The 0-3 scale drifted badly on 12 Sep 2026:
50 Hz was called 3, then 4, then corrected back to 3, because the scale had been
broken at 60 Hz and every later answer was anchored against a different top.
"Felt or not felt" cannot drift - there is no scale to move - and an adaptive
staircase converges on the boundary in about ten trials instead of asking for a
number nobody can give reliably.

**It runs as a state machine, not a loop**, because the answers arrive through a
conversation rather than a terminal. Each call plays one tone and records one
answer:

    python tools/rig_perception.py start --freq 40
    python tools/rig_perception.py yes          # felt it
    python tools/rig_perception.py no           # did not
    python tools/rig_perception.py report

**Catch trials.** Roughly one trial in five plays SILENCE. A "yes" on one of
those is a false alarm, and the rate is reported with the thresholds, because a
staircase run by someone answering from expectation converges just as neatly as
one run by someone answering from sensation and looks identical afterwards.

**Bias.** Against a simulated observer with a hard threshold the estimate lands
1.00 dB low, every run, across thresholds and seeds - exactly half the final
step size, which is where a deterministic staircase's reversals straddle. A real
observer answers with some noise and converges on the midpoint, so the real bias
is smaller than that and in the same direction. It is recorded rather than
corrected, because correcting a worst-case bias out of real data overstates it.

**It will not drive into the stops.** If a knock curve is on file the starting
level and the ceiling are capped below that frequency's knock threshold, so
measuring perception can never be the thing that knocks the unit.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import sounddevice as sd

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OUT = "Speakers (ButtKicker PRO)"
RATE = 48000
FADE_S = 0.05
TONE_S = 2.0

STATE = Path(tempfile.gettempdir()) / "pitcrew_perception.json"

# Coarse until the first reversal, then finer. Standard transformed staircase:
# the big steps find the neighbourhood fast, the small ones resolve it.
STEPS_DB = (6.0, 3.0, 2.0, 2.0)
REVERSALS_WANTED = 6
AVERAGE_LAST = 4

FLOOR_DB = -66.0
CEILING_DB = -6.0
CATCH_CHANCE = 0.2


def _device() -> int:
    for i, dev in enumerate(sd.query_devices()):
        if (sd.query_hostapis(dev["hostapi"])["name"] == "Windows WASAPI"
                and dev["max_output_channels"] > 0
                and dev["name"].startswith(OUT[:26])):
            return i
    raise SystemExit(f"no WASAPI output named {OUT!r}")


def _play(freq: float, db: float, *, silent: bool) -> None:
    n = int(RATE * TONE_S)
    if silent:
        block = np.zeros((n, 2), dtype=np.float32)
    else:
        amp = float(10 ** (db / 20))
        t = np.arange(n, dtype=np.float32) / RATE
        wave = (np.sin(2 * np.pi * freq * t) * amp).astype(np.float32)
        fade = max(1, int(RATE * FADE_S))
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        wave[:fade] *= ramp
        wave[-fade:] *= ramp[::-1]
        block = np.column_stack([wave, wave]) * 0.5
    sd.play(block, samplerate=RATE, device=_device(), blocking=True)
    sd.wait()
    time.sleep(0.1)


def _knock_ceiling(freq: float) -> float | None:
    """The knock threshold at this frequency, if a curve has been measured.

    Perception testing must never be the thing that drives the unit into its
    stops, so the staircase is capped below this.
    """
    curves = sorted((REPO / "docs").glob("knock-curve_*.json"))
    if not curves:
        return None
    try:
        data = json.loads(curves[-1].read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    best = None
    for row in data.get("curve", []):
        if row.get("threshold_db") is None:
            continue
        if abs(float(row["freq"]) - freq) <= 12.0:
            db = float(row["threshold_db"])
            best = db if best is None else min(best, db)
    return best


def _load() -> dict:
    if not STATE.exists():
        raise SystemExit("no run in progress - use `start --freq <hz>` first")
    return json.loads(STATE.read_text(encoding="utf-8"))


def _save(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _next_level(state: dict) -> float:
    """Where the staircase goes, given every answer so far."""
    trials = [t for t in state["trials"] if not t["catch"]]
    if not trials:
        return state["start_db"]
    level = trials[-1]["db"]
    felt = trials[-1]["felt"]
    step = STEPS_DB[min(state["reversals"], len(STEPS_DB) - 1)]
    # Down when felt, up when not - the staircase walks onto the boundary and
    # then oscillates across it.
    level = level - step if felt else level + step
    return float(np.clip(level, FLOOR_DB, state["ceiling_db"]))


def _threshold(state: dict) -> float | None:
    levels = state["reversal_levels"]
    if len(levels) < AVERAGE_LAST:
        return None
    return float(np.mean(levels[-AVERAGE_LAST:]))


def _present(state: dict) -> None:
    """Play the next thing - a real tone, or a catch trial."""
    catch = random.random() < CATCH_CHANCE
    db = _next_level(state)
    state["pending"] = {"db": db, "catch": catch}
    _save(state)
    _play(state["freq"], db, silent=catch)
    n = len([t for t in state["trials"] if not t["catch"]])
    print(f"  trial {n + 1}  ({state['reversals']}/{REVERSALS_WANTED} reversals)")
    print("  felt it or not?  ->  rig_perception.py yes   |   no")


def cmd_start(args) -> int:
    ceiling = CEILING_DB
    knock = _knock_ceiling(args.freq)
    if knock is not None:
        ceiling = min(ceiling, knock - 3.0)
        print(f"  capped at {ceiling:+.0f} dBFS - knock at this frequency is "
              f"{knock:+.0f}")
    state = {
        "freq": float(args.freq),
        "amp_volume": args.amp,
        "start_db": float(min(args.start, ceiling)),
        "ceiling_db": float(ceiling),
        "trials": [],
        "catches": [],
        "reversals": 0,
        "reversal_levels": [],
        "last_direction": None,
        "done": False,
        "results": _load().get("results", []) if STATE.exists() else [],
    }
    print(f"{args.freq:.0f} Hz staircase, amp {args.amp}. "
          f"Start {state['start_db']:+.0f} dBFS.")
    print("  Answer only felt / not felt. Some trials are SILENT on purpose.")
    _save(state)
    _present(state)
    return 0


def cmd_answer(args) -> int:
    state = _load()
    if state.get("done"):
        print("  this frequency is finished - `start --freq <hz>` for the next")
        return 0
    pending = state.get("pending")
    if not pending:
        print("  nothing was played - `start --freq <hz>` first")
        return 1
    felt = args.felt

    if pending["catch"]:
        state["catches"].append({"felt": felt})
        if felt:
            print("  ** FALSE ALARM ** - that trial was silent.")
        else:
            print("  (silent trial, correctly rejected)")
        state["pending"] = None
        _save(state)
        _present(state)
        return 0

    trials = [t for t in state["trials"] if not t["catch"]]
    direction = "down" if felt else "up"
    if state["last_direction"] and direction != state["last_direction"]:
        state["reversals"] += 1
        state["reversal_levels"].append(pending["db"])
        print(f"  reversal {state['reversals']} at {pending['db']:+.0f} dBFS")
    state["last_direction"] = direction
    state["trials"].append({"db": pending["db"], "felt": felt, "catch": False})
    state["pending"] = None

    if state["reversals"] >= REVERSALS_WANTED:
        thr = _threshold(state)
        state["done"] = True
        false_alarms = sum(1 for c in state["catches"] if c["felt"])
        state["results"].append({
            "freq": state["freq"],
            "threshold_db": thr,
            "trials": len(state["trials"]),
            "catches": len(state["catches"]),
            "false_alarms": false_alarms,
        })
        _save(state)
        print(f"\n  {state['freq']:.0f} Hz threshold: {thr:+.1f} dBFS"
              f"   ({len(state['trials'])} trials, "
              f"{false_alarms}/{len(state['catches'])} false alarms)")
        if false_alarms:
            print("  false alarms mean some answers came from expectation, "
                  "not sensation - treat this threshold as soft")
        print("  next: rig_perception.py start --freq <hz>")
        return 0

    _save(state)
    _present(state)
    return 0


def cmd_report(_args) -> int:
    state = _load()
    results = state.get("results", [])
    if not state.get("done") and state.get("trials"):
        results = results + [{"freq": state["freq"], "threshold_db": None,
                              "trials": len(state["trials"]),
                              "catches": len(state["catches"]),
                              "false_alarms": sum(1 for c in state["catches"]
                                                  if c["felt"])}]
    if not results:
        print("  nothing measured yet")
        return 0
    print(f"  {'Hz':>5}  {'felt from':>10}  {'knock at':>9}  {'usable':>7}"
          f"  {'trials':>6}  {'false':>5}")
    for r in results:
        knock = _knock_ceiling(r["freq"])
        thr = r["threshold_db"]
        usable = (f"{knock - thr:5.0f} dB" if knock is not None and thr is not None
                  else "     -")
        t = f"{thr:+.1f}" if thr is not None else "(running)"
        k = f"{knock:+.0f} dBFS" if knock is not None else "-"
        print(f"  {r['freq']:5.0f}  {t:>10}  {k:>9}  {usable:>7}"
              f"  {r['trials']:6d}  {r['false_alarms']:5d}")

    done = [r for r in results if r["threshold_db"] is not None]
    if done:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = REPO / "docs" / f"perception_{stamp}.json"
        out.write_text(json.dumps({"measured_utc": stamp,
                                   "amp_volume": state.get("amp_volume"),
                                   "results": done}, indent=2), encoding="utf-8")
        print(f"\n  written to {out.relative_to(REPO)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="command", required=True)

    start = subs.add_parser("start", help="begin one frequency")
    start.add_argument("--freq", type=float, required=True)
    start.add_argument("--start", type=float, default=-18.0)
    start.add_argument("--amp", type=int, default=35)
    start.set_defaults(run=cmd_start)

    yes = subs.add_parser("yes", help="felt it")
    yes.set_defaults(run=cmd_answer, felt=True)

    no = subs.add_parser("no", help="did not feel it")
    no.set_defaults(run=cmd_answer, felt=False)

    rep = subs.add_parser("report", help="thresholds and usable range so far")
    rep.set_defaults(run=cmd_report)

    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
