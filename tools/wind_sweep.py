"""Find a BAND of duties the fans misbehave at, and say where its edges are.

The driver's report is that the fault is sensitive to how the board is
configured but **not monotonic in drive level** - neither softer nor harder
reliably helped. Nothing built so far looks for that. `wind_bench ramp` walks
0-255 in fifteens with a 1.5 s dwell, which finds a start/stop threshold, not
a band: 15/255 is 5.9% of range per step, and 1.5 s is shorter than a 120 mm
rotor takes to settle.

This walks the range finely, UP and then DOWN, and lets the driver stamp a
mark against whatever duty is on the wire at the moment he hears something
wrong. **Up-then-down is the point.** A duty that misbehaves on the way up but
not on the way down is a *starting* problem. One that misbehaves in both
directions is a *running* problem, and those want opposite fixes.

    python tools/wind_sweep.py sweep --channels 0,1 --step 8      # both fans
    python tools/wind_sweep.py sweep --channels 0 --step 4        # one, fine
    python tools/wind_sweep.py sweep --channels 0 --low 80 --high 140 --step 1
    python tools/wind_sweep.py count                              # outputs?

**Run with Pit Crew closed.** One process owns a serial port.

Two things the driver must NOT mark, because both are normal and marking them
would bury the signal:

* the silence at the bottom of the up-sweep - a fan will not start below some
  duty, and that duty is worth writing down, not marking;
* the fan stopping near the bottom of the down-sweep - it stops lower than it
  starts, that is hysteresis, and `wind_bench ramp` exists to measure it.

`count` asks the board how many outputs it declares. That matters because
`SHShakeitBase::read()` consumes exactly `motorCount()` bytes with no framing:
a board declaring two against an app sending four leaves two bytes behind on
every frame, and the deadman is then never fed. It is the same byte-shift that
stopped the fans on 15 Aug, and it is how a *correct* reconfiguration would
look like a failure.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.rig import arq, wind                            # noqa: E402

try:
    import msvcrt                                            # Windows only
except ImportError:                                          # pragma: no cover
    msvcrt = None

# Where the evening's result lands. **On disk, not in scrollback.** The whole
# point of the sweep is a record that survives being read at eleven at night
# by someone who has been listening to a blower for ten minutes.
TRANSCRIPT_DIR = Path(__file__).resolve().parents[1] / "logs"

# A send slower than this is the transport intruding on a fan test, and the
# two must not end up in the same column.
SLOW_SEND_S = 0.30


def _open_link():
    """Open the board, or explain why not."""
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
            print(f"{port} is held by another process - almost certainly Pit "
                  f"Crew itself. Close the app and run this again.")
        else:
            print(f"could not open {port}: {exc}")
        return None
    return link


def _keys() -> tuple[int, bool]:
    """(marks, abort) since the last call. Never blocks.

    Non-blocking because the send cadence must not wait on a keyboard: the
    firmware zeroes every channel 1000 ms after the last frame it accepted,
    so a blocking read would stop the fans mid-test.
    """
    if msvcrt is None:
        return 0, False
    hits, abort = 0, False
    while msvcrt.kbhit():
        key = msvcrt.getch()
        if key in (b" ", b"\r", b"\n"):
            hits += 1
        elif key in (b"q", b"Q", b"\x03"):
            abort = True
    return hits, abort


def _rehearse() -> bool:
    """Make him prove a keypress registers before ten minutes depend on it.

    `msvcrt` reads THIS console's input. If focus drifts to the camera app or
    a browser - and he is bent over a rig holding a screwdriver and a phone -
    every mark is silently discarded and he finds out at the end of a sweep
    that produced nothing. That is the single most likely way this evening is
    wasted, and one rehearsal keypress removes it.
    """
    if msvcrt is None:
        print("  (no console key support here - marks are unavailable)")
        return False
    while msvcrt.kbhit():
        msvcrt.getch()
    print("\n  REHEARSAL: press SPACE now to prove the marker works.")
    print("  If nothing happens, this window does not have keyboard focus -")
    print("  click it, then press SPACE again.\n")
    waited = 0.0
    while waited < 60.0:
        hits, abort = _keys()
        if abort:
            return False
        if hits:
            print("  marker works. Keep this window in front.\n")
            return True
        time.sleep(0.05)
        waited += 0.05
    print("  no keypress in 60s - stopping rather than sweeping blind.\n")
    return False


def _health(link) -> tuple:
    return (link.resyncs, link.unanswered, link.stale_bytes,
            link.write_timeouts)


def _hold(link, channels, duty, dwell, marks, label, out, listening=True):
    """Drive `duty` for `dwell` seconds. Returns (note, alive, abort).

    A link event during a step is a transport fault wearing a fan's clothes,
    so it is recorded in its own column and never as a mark.
    """
    values = [0] * wind.CHANNELS
    for channel in channels:
        values[channel] = duty
    frame = tuple(values)

    before = _health(link)
    slowest = 0.0
    alive = True
    abort = False
    end = time.monotonic() + dwell
    while time.monotonic() < end:
        started = time.monotonic()
        try:
            alive = link.send(frame) and alive
        except Exception as exc:                             # noqa: BLE001
            return f"RAISED: {exc}", False, False
        slowest = max(slowest, time.monotonic() - started)
        hits, abort = _keys() if listening else (0, False)
        for _ in range(hits):
            when = datetime.now().strftime("%H:%M:%S")
            marks.append((duty, label, when))
            line = f"        <- MARKED at duty {duty} ({duty / 255 * 100:.1f}%)"
            print(line, flush=True)
            out(f"MARK {when} {label} {duty}")
        if abort:
            break
        time.sleep(wind.SEND_INTERVAL_S)

    notes = []
    after = _health(link)
    if after != before:
        notes.append(f"link resync/unans/stale/timeouts {before} -> {after}")
    if slowest > SLOW_SEND_S:
        notes.append(f"slowest send {slowest * 1000:.0f} ms")
    if not alive:
        notes.append("device stopped answering")
    return "; ".join(notes), alive, abort


def _series(low: int, high: int, step: int) -> list[int]:
    """`low`..`high` inclusive of BOTH ends.

    `range(0, 256, 4)` stops at 252, so a full sweep never visited 255 - which
    is the one duty the whole thermal-versus-drive-method question turns on.
    """
    walk = list(range(low, high + 1, step))
    if walk[-1] != high:
        walk.append(high)
    return walk


def cmd_sweep(args) -> int:
    channels = [int(c) for c in args.channels.split(",") if c.strip()]
    for channel in channels:
        if not 0 <= channel < wind.CHANNELS:
            print(f"channel {channel} is outside 0..{wind.CHANNELS - 1}")
            return 2
    if not 0 <= args.low < args.high <= 255:
        print("need 0 <= --low < --high <= 255")
        return 2
    if args.step < 1:
        print("--step must be at least 1")
        return 2
    if args.dwell <= 0:
        print("--dwell must be positive")
        return 2

    up = _series(args.low, args.high, args.step)
    down = list(reversed(up))
    # Plus the send-loop overhead, which the first version left out and
    # under-reported the run by about five per cent.
    total = (len(up) + len(down)) * (args.dwell + wind.SEND_INTERVAL_S)

    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = TRANSCRIPT_DIR / f"wind-sweep-{stamp}.log"
    handle = path.open("w", encoding="utf-8")

    def out(line: str) -> None:
        handle.write(line + "\n")
        handle.flush()

    out(f"# wind sweep {stamp}  channels={channels} low={args.low} "
        f"high={args.high} step={args.step} dwell={args.dwell}")

    link = _open_link()
    if link is None:
        handle.close()
        return 1
    marks: list[tuple[int, str, str]] = []
    notes: list[str] = []
    try:
        if not link.handshake():
            print("no handshake - not driving anything")
            return 1
        out(f"# port={link.port} crc={link.crc.name}")
        print(f"\n  channels {channels}   {args.low}..{args.high} step "
              f"{args.step}   dwell {args.dwell:.1f}s")
        print(f"  {len(up)} steps up then {len(down)} down, about "
              f"{total / 60:.1f} minutes.")
        print(f"  transcript: {path}")

        # **`--no-marks` is for someone else driving the console.** `msvcrt`
        # reads THIS process's input, so when the sweep is launched from
        # another machine or another session the operator at the rig has no
        # keyboard to press. The step log carries a timestamp and a duty for
        # every step, so what he calls out can still be placed afterwards -
        # coarser than a keypress, and honest about being so.
        if not args.no_marks:
            if not _rehearse():
                return 1
            print("  SPACE marks a stutter, stall, restart, growl or "
                  "drop-out.")
        else:
            print("\n  MARKERS OFF - call out what you hear; every step is "
                  "timestamped in the transcript.")
        print("  CLAP ONCE NOW if you are recording audio - that is the sync "
              "mark.")
        print("  Do NOT mark the fan failing to start at the bottom, or "
              "stopping at the bottom on the way down. Both are normal.")
        print("  q aborts and zeroes the fans.\n")
        time.sleep(2.0)

        for label, series in (("up", up), ("down", down)):
            print(f"  --- {label} ---", flush=True)
            for duty in series:
                when = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                print(f"  {when}  {label:<4} {duty:>3}/255 "
                      f"({duty / 255 * 100:>5.1f}%)", flush=True)
                out(f"STEP {when} {label} {duty}")
                note, alive, abort = _hold(link, channels, duty, args.dwell,
                                           marks, label, out,
                                           listening=not args.no_marks)
                if note:
                    notes.append(f"{label} {duty}: {note}")
                    out(f"LINK {label} {duty} {note}")
                    print(f"        [link] {note}", flush=True)
                if "RAISED" in note:
                    return 1
                if not alive:
                    # **Stop, loudly.** Past here the deadman has zeroed the
                    # channels and the fans are off for a reason that has
                    # nothing to do with duty - so every later mark would be
                    # about a dead board, and the sweep would run on for
                    # minutes collecting them.
                    print("\n  *** the board stopped answering. The fans are "
                          "off because the firmware's deadman zeroed them, "
                          "not because of this duty.")
                    print("  *** stopping - marks after this point would mean "
                          "nothing.\n")
                    out("ABORT device stopped answering")
                    return 1
                if abort:
                    print("\n  aborted at your request.\n")
                    out("ABORT by operator")
                    return 0
        return 0
    finally:
        try:
            link.send(tuple([0] * wind.CHANNELS))
        except Exception:                                    # noqa: BLE001
            pass
        link.close()
        print("\nstopped. All channels zeroed.\n" + "=" * 62)
        _summarise(marks, notes, out)
        handle.close()
        print(f"\ntranscript written to {path}")


def _summarise(marks, notes, out) -> None:
    """What was heard, and what it does and does not mean."""
    if not marks:
        print("No marks.")
        print("That means: no band whose onset is under one dwell period.")
        print("It does NOT mean the fault is not duty-dependent - a band that "
              "takes 30 s to show cannot appear in a 3 s dwell. Hold a few "
              "duties for a minute each before concluding anything.")
        out("SUMMARY no marks")
    else:
        ups = sorted({d for d, lab, _ in marks if lab == "up"})
        downs = sorted({d for d, lab, _ in marks if lab == "down"})
        print(f"{len(marks)} marks:")
        for duty, label, when in marks:
            print(f"    {when}  {label:<4} duty {duty:>3} "
                  f"({duty / 255 * 100:.1f}%)")
        print(f"\n  up:   {ups}")
        print(f"  down: {downs}")
        out(f"SUMMARY up={ups} down={downs}")
        both = sorted(set(ups) & set(downs))
        if both:
            print(f"\n  Marked in BOTH directions at {both}.")
            print("  That is a RUNNING failure - it cannot be stiction, a "
                  "start threshold or a gain setting, because the fan was "
                  "already turning when it happened. Strongest evidence for "
                  "the drive method.")
        elif ups and not downs:
            print("\n  Marked going UP only: a STARTING problem. The fan "
                  "would not pick up from a lower duty. Less damning, and "
                  "consistent with a start threshold.")
        elif downs and not ups:
            print("\n  Marked going DOWN only. Note that a fan stops at a "
                  "LOWER duty than it starts at - that is ordinary "
                  "hysteresis, not a fault. If these marks are near the "
                  "bottom of the range, they are probably that.")
    if notes:
        print(f"\n  {len(notes)} link events (transport, not fans):")
        for note in notes:
            print(f"    {note}")


def cmd_count(_args) -> int:
    """How many outputs does the board say it has?

    The gate for any reconfiguration. `SHShakeitBase::read()` takes exactly
    `motorCount()` bytes with no framing, so a mismatch against the app's
    `CHANNELS` shifts every frame and the deadman never gets fed.
    """
    link = _open_link()
    if link is None:
        return 1
    try:
        if not link.handshake():
            print("no handshake")
            return 1
        link._write(arq.motors_count_payload())
        reply = link._read_reply()
        print(f"\n  the app sends wind.CHANNELS = {wind.CHANNELS} bytes "
              f"per frame")
        print(f"  the board replied: {reply.describe() if reply else 'nothing'}")
        print("\n  These must agree. If the board declares fewer than the app "
              "sends, every frame leaves bytes behind, the board never "
              "completes a read, and the deadman stops the fans - which is "
              "how a CORRECT reconfiguration looks like a failure.")
        return 0
    finally:
        try:
            link.send(tuple([0] * wind.CHANNELS))
        except Exception:                                    # noqa: BLE001
            pass
        link.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)

    sweep = subs.add_parser("sweep", help="walk the duty range, up then down")
    sweep.add_argument("--channels", default="0,1")
    sweep.add_argument("--low", type=int, default=0)
    sweep.add_argument("--high", type=int, default=255)
    sweep.add_argument("--step", type=int, default=8)
    sweep.add_argument("--dwell", type=float, default=3.0)
    sweep.add_argument("--no-marks", action="store_true",
                       help="no keypress marker - for when someone else is "
                            "at the console and the operator only listens")
    sweep.set_defaults(run=cmd_sweep)

    subs.add_parser("count", help="how many outputs the board declares"
                    ).set_defaults(run=cmd_count)

    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
