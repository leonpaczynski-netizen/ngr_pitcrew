"""Drive the fans with a real lap's duty, at the rate the app really sends it.

**The bench tests that came before this one all held a duty, or stepped it
gently, and the fault never appeared.** Racing does neither. Monza T1 takes
the car from 279 to 59 km/h in three and a half seconds, which drags the
commanded duty from 255 down to 114 and holds it there for two - and the
driver's report is that the fans give no air on the way out of exactly that
corner, then "restart" and come back to full flow.

Arriving at a duty from above is not the same experiment as stepping up to it
from below. `wind_sweep` does the second. This does the first, using the
speed trace of a lap he actually drove, through `WindCurve` exactly as the
live app would, sent at `SEND_INTERVAL_S` exactly as the live app would.

    python tools/wind_replay.py laps --track Monza
    python tools/wind_replay.py play --lap 141 --from 8 --to 24 --loops 3
    python tools/wind_replay.py play --lap 141          # the whole lap

**Run with Pit Crew closed.** One process owns a serial port.

What this deliberately does NOT reproduce: the ButtKicker, the wheelbase, the
haptics and the telemetry thread, all of which share a machine and a USB root
hub with this device during a race. A quiet bench cannot clear a co-tenant.
"""
from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.rig import wind                                 # noqa: E402
from pitcrew.rig.wind_curve import WindCurve                 # noqa: E402
from pitcrew.store.db import Store                           # noqa: E402

FRAME_S = 1.0 / 60.0
TRANSCRIPT_DIR = Path(__file__).resolve().parents[1] / "logs"


@dataclass
class Frame:
    """The four fields `WindCurve` reads off a packet, and nothing else."""
    speed_kmh: float
    car_max_speed_raw: float = 299.0
    car_on_track: bool = True
    paused: bool = False


def _open_link():
    port = wind.find_port()
    if port is None:
        print("No wind simulator found. Is it plugged in and powered?")
        return None
    link = wind.WindLink(port)
    print(f"opening {port} at {wind.BOOT_BAUD} with DTR held low...")
    try:
        link.open()
    except Exception as exc:                                 # noqa: BLE001
        if "Access is denied" in str(exc) or "PermissionError" in str(exc):
            print(f"{port} is held by another process - close Pit Crew.")
        else:
            print(f"could not open {port}: {exc}")
        return None
    return link


def _duties(lap_id: int):
    """(t_s, speed, duty) per 60 Hz frame, through the real curve.

    The curve is fed frame by frame at `FRAME_S` so its slew limiter sees the
    same time steps it sees live - handing it the whole trace at once would
    let it move faster than it ever can on track.
    """
    store = Store("data/pitcrew.db")
    payload = store.get_lap_frames(lap_id)
    if not payload:
        return None
    frames = payload["frames"]
    speeds = [f["speed_kph"] for f in frames]
    curve = WindCurve()
    # The circuit's own measured top speed, which is what the live app uses
    # once an event has recorded one. Scaling to the car's 299 instead would
    # put the top of the range out of reach and flatten the whole trace.
    curve.observed_top_kph = max(speeds)
    out = []
    for frame, speed in zip(frames, speeds):
        duty = curve.update(Frame(speed), FRAME_S, racing=True)[0]
        out.append((frame["t_ms"] / 1000.0, speed, duty))
    return out


def cmd_laps(args) -> int:
    """Which laps are available to replay, worst decel first."""
    import sqlite3

    db = sqlite3.connect("file:data/pitcrew.db?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    rows = db.execute("""
        SELECT l.id, l.lap_num, l.lap_time_ms, e.track, e.car_name
        FROM laps l JOIN sessions s ON l.session_id = s.id
        JOIN events e ON s.event_id = e.id
        JOIN lap_frames f ON f.lap_id = l.id
        WHERE e.track LIKE ? ORDER BY l.id DESC LIMIT ?""",
        (f"%{args.track}%", args.limit)).fetchall()
    if not rows:
        print(f"no laps with frames matching {args.track!r}")
        return 1
    print(f"  {'lap':>5}  {'num':>4}  {'track':<32}  car")
    for row in rows:
        print(f"  {row['id']:>5}  {row['lap_num']:>4}  {row['track']:<32}  "
              f"{row['car_name']}")
    return 0


def _worst_decel(trace):
    """Where the speed falls hardest over two seconds, and by how much.

    That is the shape the driver reports the fault at - a fast straight into
    a slow corner - and it is the part of the lap worth looping.
    """
    window = 120
    best, at = 0.0, 0
    for i in range(len(trace) - window):
        drop = trace[i][1] - trace[i + window][1]
        if drop > best:
            best, at = drop, i
    return at, best


def cmd_play(args) -> int:
    trace = _duties(args.lap)
    if trace is None:
        print(f"lap {args.lap} has no frames")
        return 1

    at, drop = _worst_decel(trace)
    print(f"\n  lap {args.lap}: {len(trace)} frames, "
          f"{trace[-1][0]:.1f}s, peak duty {max(d for _, _, d in trace)}")
    print(f"  hardest 2s decel: {trace[at][1]:.0f} -> "
          f"{trace[at + 120][1]:.0f} km/h at t={trace[at][0]:.1f}s")

    if args.to is None:
        # Default to the corner itself, with the straight before it and the
        # exit after - which is the whole of what he described.
        start = max(0.0, trace[at][0] - 3.0)
        end = min(trace[-1][0], trace[at][0] + 12.0)
    else:
        start, end = float(args.at or 0.0), float(args.to)
    window = [row for row in trace if start <= row[0] <= end]
    if not window:
        print("that window has no frames in it")
        return 1

    duties = [d for _, _, d in window]
    print(f"  replaying {start:.1f}s to {end:.1f}s: duty "
          f"{max(duties)} down to {min(duties)}, {args.loops} loop(s)\n")
    print("  WATCH THE FANS. The moment of interest is the exit - does the "
          "air come back smoothly, or is there nothing and then a surge?\n")

    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = TRANSCRIPT_DIR / f"wind-replay-{stamp}.log"
    handle = path.open("w", encoding="utf-8")
    handle.write(f"# replay lap={args.lap} {start:.1f}-{end:.1f}s "
                 f"loops={args.loops}\n")

    # **The send rate is the experiment, not a constant.** `SEND_INTERVAL_S`
    # is 0.25 s in the app and that number came from the firmware's 1000 ms
    # deadman, not from anything about the fans - so every change the curve
    # computes is quantised to 250 ms before the board hears it. Measured
    # round trip on this link is 9.2 ms median, 9.4 p95, so 60 Hz has room.
    interval = 1.0 / args.hz if args.hz else wind.SEND_INTERVAL_S
    print(f"  sending at {1 / interval:.0f} Hz "
          f"({interval * 1000:.0f} ms/frame)\n")

    link = _open_link()
    if link is None:
        handle.close()
        return 1
    try:
        if not link.handshake():
            print("no handshake - not driving anything")
            return 1
        for loop in range(args.loops):
            print(f"  --- loop {loop + 1} of {args.loops} ---", flush=True)
            began = time.monotonic()
            last_print = -1.0
            # **Sent at `SEND_INTERVAL_S`, not per frame.** The board only
            # ever hears from the app four times a second, so a replay that
            # sent every 60 Hz frame would be a kinder test than reality.
            for offset in range(0, int((end - start) / interval)):
                due = offset * interval
                index = min(len(window) - 1, int(due * 60))
                elapsed, speed, duty = window[index]
                values = tuple([duty] * wind.CHANNELS)
                alive = link.send(values)
                handle.write(f"{time.time():.3f} {elapsed:.2f} "
                             f"{speed:.1f} {duty}\n")
                if due - last_print >= 0.5:
                    print(f"    {elapsed:6.1f}s  {speed:5.0f} km/h  "
                          f"duty {duty:3d}  {'#' * int(duty / 8)}", flush=True)
                    last_print = due
                if not alive:
                    print("\n  *** the board stopped answering - the fans are "
                          "off because the deadman zeroed them.\n")
                    handle.write("ABORT device stopped answering\n")
                    return 1
                slip = began + due + interval - time.monotonic()
                if slip > 0:
                    time.sleep(slip)
        return 0
    finally:
        try:
            link.send(tuple([0] * wind.CHANNELS))
        except Exception:                                    # noqa: BLE001
            pass
        link.close()
        handle.close()
        print(f"\nstopped. All channels zeroed.\ntranscript: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)

    laps = subs.add_parser("laps", help="which laps can be replayed")
    laps.add_argument("--track", default="")
    laps.add_argument("--limit", type=int, default=20)
    laps.set_defaults(run=cmd_laps)

    play = subs.add_parser("play", help="drive the fans with a lap's duty")
    play.add_argument("--lap", type=int, required=True)
    play.add_argument("--at", type=float, default=None,
                      help="start second (default: just before the hardest "
                           "deceleration in the lap)")
    play.add_argument("--to", type=float, default=None, help="end second")
    play.add_argument("--loops", type=int, default=3)
    play.add_argument("--hz", type=float, default=None,
                      help="send rate; default is the app's 4 Hz "
                           "(SEND_INTERVAL_S). The link measures 9.2 ms per "
                           "round trip, so 60 is reachable.")
    play.set_defaults(run=cmd_play)

    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
