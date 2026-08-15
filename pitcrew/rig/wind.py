"""The wind simulator: two fans on an Arduino, driven from the car's speed.

A Sector 17 / Redion WSP on COM5 - Arduino Uno, CH340 bridge, two fans through
an Adafruit Motor Shield V2. SimHub used to drive it. This replaces that.

Four things shape every decision in here, and all four are measured rather
than assumed:

**The firmware has a deadman, and it is the safety net.** `SHShakeitBase.h`
zeroes every channel after 1000 ms without a successful motors read. The fans
physically cannot stick on if this process dies, is killed, or hangs - which
is worth more than any `atexit` handler, because `atexit` does not run on
SIGKILL. The price is that this must transmit **unconditionally**, at better
than 1 Hz, even when the value has not changed. Send-on-change would make the
fans stutter at exactly the moment the driver is holding a steady speed.

**Opening the port resets the board.** Asserting DTR pulls the Uno's reset
line, and for the second or so of reset and bootloader the PWM pins float. If
these fans are true 4-wire units that means full speed, because Intel's spec
says an absent control signal shall run the fan at maximum. Two 4000 RPM
blowers going to 100% is startling on a desk and genuinely unpleasant in a
headset, so `dtr` is cleared **before** the port is opened. UNVERIFIED for
this unit - it depends on how the fans are wired - which is why the bench
test comes before anything drives this from telemetry.

**Never close the port from inside a write.** This is the exact shape of the
deadlock that wedged SimHub: a failing write called `Close()` while the reader
was parked on the same handle. Here a write failure marks the link dead and
returns; the owning thread does the closing, on its own next pass.

**A stale frame is worth less than no frame.** Fan commands supersede rather
than accumulate, so the queue is one deep and a new value overwrites the one
waiting. Queuing them would mean the fans faithfully replaying a corner the
driver left four seconds ago.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from pitcrew.diagnostics import log
from pitcrew.rig import arq

# The CH340 on the Redion. No serial number - CH340s do not carry one - so two
# of them are genuinely indistinguishable and the driver has to pick.
CH340_VID = 0x1A86
CH340_PID = 0x7523
# Other bridges the same kit ships with, so a replacement board still finds
# itself. Official Uno, FTDI, and CP210x respectively.
KNOWN_BRIDGES = (
    (CH340_VID, CH340_PID),
    (0x2341, 0x0043), (0x2341, 0x0001), (0x2341, 0x0243),
    (0x0403, 0x6001),
    (0x10C4, 0xEA60),
)

# The firmware boots at 19200 and only moves when told to. SimHub negotiated
# 115200 with it, but there is nothing to gain here: a fan command is seven
# bytes at 20 Hz, which is 1% of even the slow rate. Staying at the boot rate
# removes a negotiation step that could fail.
BOOT_BAUD = 19200

# Comfortably inside the firmware's 1000 ms deadman, with room for a missed
# frame or two before the fans drop out.
SEND_INTERVAL_S = 0.25
# A write that has not completed in this long is a link that is not working.
WRITE_TIMEOUT_S = 0.25
READ_TIMEOUT_S = 0.15
# How long to wait after opening before talking, so the bootloader is done.
# The Uno's Optiboot window is about a second.
RESET_SETTLE_S = 1.6
# How often to retry a dead link. Windows can hand back a different COM
# number after a replug, so discovery runs again each time rather than
# reusing the old one.
RECONNECT_S = 2.0

# This device declares four, though only two fans are wired. All four bytes go
# every time: the firmware reads exactly `motorCount()` of them with no
# framing, so a short write leaves it waiting mid-command.
CHANNELS = 4


@dataclass
class WindState:
    """What the layer is doing, for the screen and the logs."""
    connected: bool = False
    port: str | None = None
    firmware: str | None = None
    crc_name: str | None = None
    channels: int = CHANNELS
    last_values: tuple[int, ...] = field(default_factory=tuple)
    frames_sent: int = 0
    write_failures: int = 0
    error: str | None = None

    def describe(self) -> str:
        if self.error:
            return self.error
        if not self.connected:
            return "The wind simulator is not connected."
        where = f"on {self.port}"
        if self.firmware:
            where += f", firmware {self.firmware}"
        return f"Wind simulator {where}. {self.frames_sent} frames sent."


def available() -> bool:
    """Whether pyserial is installed at all."""
    try:
        import serial  # noqa: F401
    except ImportError:
        return False
    return True


def find_port() -> str | None:
    """The first port that looks like this Arduino, or None.

    Matched on VID/PID rather than on the COM number, which Windows reassigns
    when the board moves to a different USB socket - this machine already
    carries a ghost COM7 from exactly that.
    """
    try:
        from serial.tools import list_ports
    except ImportError:
        return None
    candidates = []
    for port in list_ports.comports():
        pair = (port.vid, port.pid)
        if pair in KNOWN_BRIDGES:
            candidates.append((KNOWN_BRIDGES.index(pair), port.device))
    if not candidates:
        return None
    candidates.sort()
    return candidates[0][1]


class WindLink:
    """One serial connection, owned by one thread.

    Not thread-safe on purpose. `WindSim` below owns an instance and is the
    only thing that touches it, which is what keeps the close-from-send
    deadlock structurally impossible rather than merely avoided.
    """

    def __init__(self, port: str, *, channels: int = CHANNELS) -> None:
        self.port = port
        self.channels = channels
        self._serial = None
        self._packet_id = arq.BROADCAST_ID
        self.crc = arq.DEFAULT_CRC
        self.firmware: str | None = None

    def open(self) -> None:
        """Open without resetting the board into a full-speed blast."""
        import serial

        handle = serial.Serial()
        handle.port = self.port
        handle.baudrate = BOOT_BAUD
        handle.timeout = READ_TIMEOUT_S
        handle.write_timeout = WRITE_TIMEOUT_S
        # **Before `open()`, deliberately.** pyserial applies the pre-open DTR
        # state as it opens the handle, so setting it afterwards is too late -
        # the reset pulse has already happened and the fans have already had
        # their second at full tilt. Note this is not `dsrdtr`, which turns on
        # DSR/DTR *flow control* and is a different thing that gets
        # cargo-culted into this problem.
        handle.dtr = False
        handle.rts = False
        handle.open()
        self._serial = handle
        # Even with DTR held low a freshly enumerated board may still be in
        # its bootloader, and bytes sent into that are lost rather than
        # queued.
        time.sleep(RESET_SETTLE_S)
        handle.reset_input_buffer()
        handle.reset_output_buffer()

    def close(self) -> None:
        """Stop the fans, then let go. Only ever called by the owning thread."""
        handle = self._serial
        if handle is None:
            return
        try:
            if handle.is_open:
                # Courtesy, not the safety mechanism - the firmware's deadman
                # is what actually guarantees this. But an explicit zero means
                # the fans stop now rather than up to a second from now.
                #
                # Written BEFORE `_serial` is detached: `_write` refuses to
                # send through a closed link, so clearing the attribute first
                # made this silently a no-op and the fans spun on until the
                # deadman caught them.
                self._write(arq.motors_payload([0] * self.channels))
                handle.flush()
        except Exception as exc:                            # noqa: BLE001
            log("wind").debug("could not stop the fans on the way out: %s", exc)
        self._serial = None
        try:
            handle.close()
        except Exception as exc:                            # noqa: BLE001
            log("wind").debug("closing %s raised: %s", self.port, exc)

    # ------------------------------------------------------------ protocol

    def _write(self, payload: bytes) -> None:
        """One framed payload. Raises on a dead link; never closes the port."""
        if self._serial is None:
            raise OSError("the port is not open")
        frame = arq.build_frame(self._packet_id, payload, self.crc)
        self._serial.write(frame)
        self._packet_id = arq.next_id(self._packet_id)

    def _read_reply(self) -> arq.Reply | None:
        if self._serial is None:
            return None
        data = self._serial.read(3)
        return arq.parse_reply(data) if data else None

    def handshake(self) -> bool:
        """Prove the framing works, and find out which checksum it speaks.

        The CRC polynomial is the one constant that could not be recovered
        when SimHub deleted its own firmware source. Rather than guess and
        hope, this asks the device: a wrong polynomial comes back as NACK
        reason 4, which says precisely "checksum did not match", so the
        candidates can be tried until one is acknowledged.

        Every attempt opens with the broadcast id, because there is no way to
        know where the sequence stands on a board that has been talking to
        something else.
        """
        for variant in arq.CRC_VARIANTS:
            self.crc = variant
            self._packet_id = arq.BROADCAST_ID
            try:
                self._write(arq.hello_payload())
            except Exception as exc:                        # noqa: BLE001
                log("wind").warning("hello failed on %s: %s", self.port, exc)
                return False
            reply = self._read_reply()
            if reply is None:
                # Silence is not a wrong checksum - it is a device that is not
                # listening, and trying three more polynomials at it will not
                # help.
                log("wind").warning(
                    "%s did not answer a hello. The board may still be "
                    "resetting, or it is not running SimHub firmware.",
                    self.port)
                return False
            if reply.acknowledged:
                log("wind").info(
                    "%s speaks the %s checksum - measured, not assumed.",
                    self.port, variant.name)
                return True
            if not reply.bad_checksum:
                log("wind").warning("%s %s", self.port, reply.describe())
                return False
            log("wind").debug("%s rejected the %s checksum, trying the next",
                              self.port, variant.name)
        log("wind").error(
            "%s rejected every checksum this app knows. The framing is not "
            "what the firmware expects, and no fan command will be accepted.",
            self.port)
        return False

    def send(self, values: tuple[int, ...]) -> None:
        """Set every channel. Raises on a dead link, and does not close."""
        self._write(arq.motors_payload(list(values)))


class WindSim:
    """The wind layer: one thread, one link, and a value it keeps sending.

    `set_output` is called from wherever the telemetry lands and never
    blocks - it writes a value and returns. The thread does the talking, so a
    stalled USB write cannot reach the packet handler.
    """

    def __init__(self, *, channels: int = CHANNELS) -> None:
        self.state = WindState(channels=channels)
        self._channels = channels
        self._wanted: tuple[int, ...] = tuple([0] * channels)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._link: WindLink | None = None

    # ------------------------------------------------------------- control

    def set_output(self, values: tuple[int, ...] | list[int]) -> None:
        """The value the fans should be at. Supersedes anything waiting.

        Deliberately last-wins rather than queued: a fan command from four
        seconds ago describes a corner the driver has already left, and
        replaying it faithfully is worse than skipping it.
        """
        clamped = tuple(
            max(0, min(255, int(v))) for v in values[:self._channels])
        padded = clamped + tuple([0] * (self._channels - len(clamped)))
        with self._lock:
            self._wanted = padded

    def stop_fans(self) -> None:
        self.set_output(tuple([0] * self._channels))

    def start(self) -> None:
        if self._thread is not None:
            return
        if not available():
            self.state.error = (
                "pyserial is not installed, so the wind simulator cannot be "
                "driven. Everything else works.")
            log("wind").warning(self.state.error)
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="WindSim", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=3.0)

    # -------------------------------------------------------------- thread

    def _run(self) -> None:
        """Own the link, keep it fed, and rebuild it when it dies."""
        while not self._stop.is_set():
            if self._link is None and not self._connect():
                # Nothing to talk to. Wait rather than spin, and try
                # discovery again - the COM number can change across a replug.
                self._stop.wait(RECONNECT_S)
                continue
            if not self._send_once():
                self._drop_link()
                self._stop.wait(RECONNECT_S)
                continue
            self._stop.wait(SEND_INTERVAL_S)
        self._drop_link()

    def _connect(self) -> bool:
        port = find_port()
        if port is None:
            if self.state.error is None:
                self.state.error = (
                    "No wind simulator found. Check it is plugged in and "
                    "powered.")
                log("wind").info(self.state.error)
            return False
        link = WindLink(port, channels=self._channels)
        try:
            link.open()
        except Exception as exc:                            # noqa: BLE001
            self.state.error = f"Could not open {port}: {exc}"
            log("wind").warning(self.state.error)
            return False
        if not link.handshake():
            self.state.error = (
                f"{port} opened but would not answer. It may not be the wind "
                f"simulator.")
            link.close()
            return False
        self._link = link
        self.state.connected = True
        self.state.port = port
        self.state.crc_name = link.crc.name
        self.state.error = None
        log("wind").info("wind simulator ready on %s", port)
        return True

    def _send_once(self) -> bool:
        link = self._link
        if link is None:
            return False
        with self._lock:
            values = self._wanted
        try:
            link.send(values)
        except Exception as exc:                            # noqa: BLE001
            self.state.write_failures += 1
            self.state.error = f"Lost the wind simulator on {link.port}: {exc}"
            log("wind").warning(self.state.error)
            return False
        self.state.frames_sent += 1
        self.state.last_values = values
        return True

    def _drop_link(self) -> None:
        """Tear the link down here, on the owning thread, and nowhere else."""
        link, self._link = self._link, None
        self.state.connected = False
        if link is not None:
            link.close()
