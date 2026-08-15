"""Bring the wind simulator up one step at a time, with a human listening.

Every step is a separate command on purpose. Two 4000 RPM blowers a foot from
the driver's face are not something to point a script at and hope: the point
is to do one thing, hear what happened, and decide the next thing.

    python tools/wind_bench.py find
    python tools/wind_bench.py open        # does opening the port blast them?
    python tools/wind_bench.py handshake   # which checksum does it speak?
    python tools/wind_bench.py channel 0 --duty 120 --seconds 3
    python tools/wind_bench.py ramp --channel 0
    python tools/wind_bench.py stop

Run `find` first and `stop` whenever anything is unexpected. Every command
that opens the port stops the fans before it lets go, and the firmware's own
deadman zeroes them a second after this process ends however it ends.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from pitcrew.rig import arq, wind  # noqa: E402


def _open_link() -> wind.WindLink | None:
    port = wind.find_port()
    if port is None:
        print("No wind simulator found. Is it plugged in and powered?")
        return None
    link = wind.WindLink(port)
    print(f"opening {port} at {wind.BOOT_BAUD} with DTR held low...")
    try:
        link.open()
    except Exception as exc:                                # noqa: BLE001
        print(f"could not open {port}: {exc}")
        return None
    return link


def cmd_find(_args) -> int:
    """Discovery only. Opens nothing, so the fans cannot move."""
    try:
        from serial.tools import list_ports
    except ImportError:
        print("pyserial is not installed.")
        return 2
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports at all. The board is not enumerated - check "
              "the USB lead and that the rig has power.")
        return 1
    for port in ports:
        known = (port.vid, port.pid) in wind.KNOWN_BRIDGES
        vid = f"{port.vid:04X}" if port.vid is not None else "????"
        pid = f"{port.pid:04X}" if port.pid is not None else "????"
        print(f"  {'->' if known else '  '} {port.device:<8} "
              f"VID_{vid}&PID_{pid}  {port.description}")
    chosen = wind.find_port()
    print(f"\nwould use: {chosen or 'nothing - no known bridge'}")
    return 0 if chosen else 1


def cmd_open(args) -> int:
    """**The one that might be loud.** Open, hold, close - nothing else.

    Opening a serial port normally asserts DTR, which pulls the Uno's reset
    line; through the reset and the bootloader the PWM pins float, and Intel's
    4-wire fan spec says a fan with no control signal shall run at maximum.
    `wind.py` clears DTR before opening to avoid that, and this is how we find
    out whether it worked on this particular unit - which depends on how the
    fans are wired, and is not knowable from the firmware.

    Listen. Nothing should spin.
    """
    link = _open_link()
    if link is None:
        return 1
    print(f"open. holding for {args.seconds:.0f}s - LISTEN.")
    try:
        time.sleep(args.seconds)
    finally:
        link.close()
    print("closed. Did either fan spin up at any point? That is the answer.")
    return 0


def cmd_handshake(args) -> int:
    """Ask the device which checksum it speaks, and what it is."""
    link = _open_link()
    if link is None:
        return 1
    try:
        if not link.handshake():
            print("\nThe device did not acknowledge any checksum this app "
                  "knows.\nEither it is not running SimHub firmware, or the "
                  "framing differs.\nNothing was driven.")
            return 1
        print(f"\n  checksum   {link.crc.name}   <- MEASURED, not assumed")
        print(f"  port       {link.port}")
        print("\nThe framing works. Fan commands will be accepted.")
        return 0
    finally:
        link.close()


def cmd_channel(args) -> int:
    """Drive exactly one channel, so which fan is which becomes known.

    `WindSettings.json` mapped roles 2 and 3 onto the first two of four
    declared channels, but which physical fan each one turns is not written
    down anywhere. One at a time is how that gets established.
    """
    link = _open_link()
    if link is None:
        return 1
    try:
        if not link.handshake():
            print("no handshake - not driving anything")
            return 1
        values = [0] * wind.CHANNELS
        values[args.channel] = args.duty
        print(f"channel {args.channel} -> {args.duty}/255 for "
              f"{args.seconds:.0f}s. Which fan moved?")
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            link.send(tuple(values))
            # Comfortably inside the firmware's 1000 ms deadman.
            time.sleep(wind.SEND_INTERVAL_S)
        return 0
    finally:
        link.close()
        print("stopped.")


def cmd_ramp(args) -> int:
    """Find the duty a stopped fan starts at, and the duty a moving fan stops
    at. They differ - the hysteresis is real, and both are needed before any
    speed curve means anything."""
    link = _open_link()
    if link is None:
        return 1
    try:
        if not link.handshake():
            print("no handshake - not driving anything")
            return 1
        print("Ramping UP. Say when it starts moving.\n")
        for duty in range(0, 256, args.step):
            values = [0] * wind.CHANNELS
            values[args.channel] = duty
            print(f"  {duty:>3}/255  ({duty / 255 * 100:>5.1f}%)", flush=True)
            end = time.monotonic() + args.dwell
            while time.monotonic() < end:
                link.send(tuple(values))
                time.sleep(wind.SEND_INTERVAL_S)
        print("\nRamping DOWN. Say when it stops.\n")
        for duty in range(255, -1, -args.step):
            values = [0] * wind.CHANNELS
            values[args.channel] = duty
            print(f"  {duty:>3}/255  ({duty / 255 * 100:>5.1f}%)", flush=True)
            end = time.monotonic() + args.dwell
            while time.monotonic() < end:
                link.send(tuple(values))
                time.sleep(wind.SEND_INTERVAL_S)
        return 0
    finally:
        link.close()
        print("stopped.")


def cmd_stop(_args) -> int:
    """Zero every channel and let go. Safe to run at any time."""
    link = _open_link()
    if link is None:
        return 1
    try:
        link.handshake()
        link.send(tuple([0] * wind.CHANNELS))
        print("all channels zeroed.")
        return 0
    finally:
        link.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)

    subs.add_parser("find", help="list ports, open nothing").set_defaults(
        run=cmd_find)

    opener = subs.add_parser("open", help="open and hold - listen for a blast")
    opener.add_argument("--seconds", type=float, default=6.0)
    opener.set_defaults(run=cmd_open)

    subs.add_parser("handshake", help="which checksum does it speak"
                    ).set_defaults(run=cmd_handshake)

    channel = subs.add_parser("channel", help="drive one channel")
    channel.add_argument("channel", type=int, choices=range(wind.CHANNELS))
    channel.add_argument("--duty", type=int, default=120)
    channel.add_argument("--seconds", type=float, default=3.0)
    channel.set_defaults(run=cmd_channel)

    ramp = subs.add_parser("ramp", help="find start and stop duty")
    ramp.add_argument("--channel", type=int, default=0,
                      choices=range(wind.CHANNELS))
    ramp.add_argument("--step", type=int, default=15)
    ramp.add_argument("--dwell", type=float, default=1.5)
    ramp.set_defaults(run=cmd_ramp)

    subs.add_parser("stop", help="zero every channel").set_defaults(
        run=cmd_stop)

    args = parser.parse_args()
    if args.command != "find" and not wind.available():
        print("pyserial is not installed: pip install pyserial")
        return 2
    return args.run(args)


if __name__ == "__main__":
    raise SystemExit(main())
