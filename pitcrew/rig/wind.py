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

**Opening the port resets the board**, so `dtr` is cleared before the port is
opened rather than after - by then the reset pulse has already happened. The
worry was that the PWM pins float through the reset and bootloader window,
and Intel's 4-wire spec says a fan with no control signal shall run at
maximum: two 4000 RPM blowers at 100% would be startling on a desk and worse
in a headset. Bench-tested on this rig with the driver listening - port held
open six seconds, neither fan moved - so there is no startup blast here. The
flag stays because it costs nothing and is correct on a board where the reset
is DTR-driven.

**Every frame is acknowledged, and the acknowledgement is read.** The firmware
NACKs a packet id it did not expect, and `write` succeeds regardless because
the bytes only have to reach the OS buffer. Skipping the reply cost a session:
one lost frame desynchronised the sequence, the device rejected everything
after it, its deadman stopped the fans, and nothing on this side noticed.

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

# **The firmware's deadman, named rather than described.** `SHShakeitBase.h`
# zeroes every channel this long after the last frame it accepted. It is the
# only number that decides whether the fans are turning, so every gap this
# module measures is measured against it.
DEADMAN_S = 1.0

# **20 Hz. It was 60, and 60 broke the link.**
#
# The history, because each step was measured and each measurement was too
# short. This was 0.25 s, a number that came only from the deadman above and
# quantised every change the curve computed to 250 ms. On 30 Aug 2026 it went
# to 1/60 s on the strength of a 9.17 ms median round trip and a 60 s live
# check that acknowledged 100% of frames. The driver, who asked for the
# change, reported Monza T1 as "much smoother and more realistic".
#
# **Then the whole of the log was read, 12 Aug to 3 Sep.** In 10.3 running
# hours before that commit the CH340 hard-failed a `WriteFile`/`ReadFile`
# once. In 4.2 running hours after it, 106 times - Windows error 1460, the
# driver's own timeout, roughly one every 2.4 minutes - and 203 quarter-second
# write stalls against 21. Not load-related: 15 of the 106 came at a
# standstill with the fans idle, and the fan level at a failure matched the
# session baseline. It is the wch.cn 3.5.2019.1 driver under back-to-back
# overlapped I/O, and it followed the board from a chained hub (COM9, ~29/h)
# to a root port (COM5, ~10/h). The 60 s verification could not have seen a
# fault that arrives every two to six minutes.
#
# 103 of the 106 reconnected in 0.13 s, inside the deadman, so they did not
# stop the fans - but three did, one of them for seven minutes, and every one
# of them is a purge, a cancel and a handshake the link should not need.
#
# Twenty is the compromise: five times the old rate, a 50 ms period the
# 60 Hz curve is decimated onto without visible steps, and a third of the
# I/O the driver was failing under. **It is a hypothesis with a prediction:**
# hard losses per running hour should fall from 25 back towards 1. The
# `wind simulator back on` line and the ack-gap warning below are what will
# say whether it did. If they do not, the rate is not the variable and the
# driver is.
#
# `UNANSWERED_LIMIT` and `WRITE_TIMEOUT_LIMIT` are counts, so the rate
# changes what they mean in seconds: their comments carry the figure that
# applies. Falling behind still costs responsiveness and never the fans -
# the deadman is twenty intervals away.
SEND_INTERVAL_S = 1.0 / 20.0
# A write that has not completed in this long is a link that is not working.
WRITE_TIMEOUT_S = 0.25
READ_TIMEOUT_S = 0.15
# How long to wait after opening before talking, so the bootloader is done.
# The Uno's Optiboot window is about a second.
#
# **Opening the port does NOT spin the fans up.** Measured on this rig,
# 15 Aug 2026: the port was opened with DTR held low and held for six seconds
# with the driver listening, and neither fan moved. That was the open question
# this layer was built most defensively around, and the answer is the good
# one - there is no startup blast to design around, and no reason to fear the
# app being started with a headset already on.
RESET_SETTLE_S = 1.6
# **How long to wait for the hello's version packet.** `Command_Hello`
# acknowledges at once and sends `0x08 <letter>` afterwards - measured on
# 3 Sep 2026 at 417 ms after the acknowledgement on a board that had been
# idle, and about 20 ms on one mid-run. A fixed drain never caught it, a
# 150 ms read caught it sometimes, and whatever read came next got it the
# rest of the time: the first motors frame for weeks, then the channel-count
# query, whose own 36-byte reply was lost because the board was still inside
# the hello when the query arrived. Waiting here, up to this long, is what
# makes every later exchange clean. Returns as soon as the packet lands, so
# a warm board costs 20 ms and only a cold one pays the full wait.
VERSION_WAIT_S = 0.6
# How often to retry a dead link, backing off to the cap so a device that is
# unplugged is not polled at a steady rate all session. Discovery runs again
# each time rather than reusing the old port - Windows can hand back a
# different COM number after a replug.
RECONNECT_S = 2.0
RECONNECT_MAX_S = 30.0
# **The first retry after a healthy spell does not wait.** Measured against
# the only drop in ten days of logs - 16 Aug 2026, 11.72 seconds of dead fans
# - the recovery was three attempts of `RECONNECT_S` plus a settle, and the
# device itself was back in about two. A USB re-enumeration completes in one
# to three seconds; pausing two before even looking spends most of the outage
# waiting for something that has already happened.
FIRST_RETRY_S = 0.1
# How long the last commanded value is held verbatim when nothing new
# arrives, and how long it then takes to fade to nothing. Three seconds is
# far longer than any gap in a 60 Hz feed that is merely late; two seconds of
# fade is slow enough not to be a slap.
HOLD_S = 3.0
DECAY_S = 2.0
# How long a close may take before it is abandoned to the operating system.
# `CancelIoEx` on a surprise-removed CH340 can block inside the driver, and
# this is on the path a session shutdown joins.
CLOSE_TIMEOUT_S = 1.0

# How many frames may go unanswered before the link is treated as dead. The
# device replies within a millisecond, so a run this long is not a busy
# moment - it is a cable, a hub, or a board that has stopped listening.
#
# **This said "about two seconds" and meant 3.2.** Each unanswered frame
# costs `READ_TIMEOUT_S` waiting for the reply that never comes AND
# `SEND_INTERVAL_S` before the next one goes out - 0.40 s a frame, not 0.25 -
# so eight of them is 3.2 seconds, sixty per cent longer than the comment
# claimed. The fans have been stopped by the firmware's own deadman for two
# of those seconds and the app is still reporting `connected True`.
#
# Four: 1.6 seconds, which is what "about two seconds" was always meant to
# be, and still comfortably longer than a single late reply.
#
# **At 20 Hz that is 0.8 s** - four times `READ_TIMEOUT_S` plus a 50 ms
# interval. Shorter than the 1.6 s above is the safe direction: the device
# answers in about a millisecond, so four unanswered frames is still far more
# than a busy moment. The paragraph above is the 4 Hz figure; this is the one
# that applies.
UNANSWERED_LIMIT = 4

# **How many write timeouts in a row before the link is given up on.**
#
# Measured, and it is the whole of the fans defect on 24 Aug 2026. A single
# `Write timeout` from `handle.write` was treated as a dead link, so the layer
# tore the port down - and the teardown is the part that cannot be recovered
# from: the close overran its bound, this app went on holding COM5, and the
# fans were off for the rest of the day. Seven such losses since 22 Aug, and
# only two of them ever reopened.
#
# A dropped fan frame is not worth that. The value is idempotent and resent
# 250 ms later, and the firmware's own 1000 ms deadman is the only thing that
# has to be beaten. So a timeout is now a hiccup: cancel what is stuck, purge
# the output buffer, count it, and send the next one.
#
# **"Twenty frames is five seconds" was wrong, and it is the same arithmetic
# error this file already corrected for `UNANSWERED_LIMIT` twenty lines
# above.** A timeout costs `WRITE_TIMEOUT_S` blocked in the write AND
# `SEND_INTERVAL_S` before the next one goes out - 0.50 s a frame, not 0.25.
# Measured off the one run that ever reached the limit, 24 Aug 16:10:20 to
# 16:10:29.674: nineteen timeouts in 9.216 s, **0.512 s each**.
#
# So twenty frames is 9.75 s to the raise and 10.75 s to a torn-down link,
# and about **8.75 s of that is dead fans** - the firmware's deadman fires
# 1.0 s into it. Throughout, `connected` reads True and nothing above INFO is
# written. That is the best explanation on file for the thing the driver
# actually reports: the fans drop, they come back on their own, and the log
# says the link was healthy the whole time.
#
# **At 20 Hz that is 6.0 s, not 10.2**, because each timeout costs
# `WRITE_TIMEOUT_S` plus a 50 ms interval rather than a 250 ms one. A shorter
# dead-fan window for the same count, which is the safe direction and needs
# no adjustment.
#
# The number is left at twenty deliberately. Lowering it makes a teardown
# easier to reach, and a teardown is the expensive failure here - seven of
# eleven link losses orphaned the port and cost between two and thirteen
# hours, one of them a whole race. The fix is to SAY what is happening, which
# `max_ack_gap_s` now does, not to tear the port down sooner. Revisit only
# once the abandoned close is measured at zero over a week.
WRITE_TIMEOUT_LIMIT = 20

# **The width of the app's own fan vector, and the count to fall back on.**
# This device declares four, though only two fans are wired, and every byte
# goes every time: the firmware reads exactly `motorCount()` of them with no
# framing, so a short write leaves it waiting mid-command and a long one
# leaves bytes over that corrupt the frame after.
#
# **A frame wider than the board is harmless; narrower is not.** Measured
# 3 Sep 2026: a four-motor board acknowledged 26,875 eight-wide frames and
# the fans ran, because the firmware's packet layer discards the bytes a
# command does not read. So this is a floor: `WindLink.discover_channels`
# asks the board on every connect, widens the frame if the board declares
# more, and never narrows it. The reflash planned in
# `docs/WIND-SKETCH-REFLASH_2026-09-03.md` makes the board declare two, and
# four-wide frames reach it correctly. Callers keep building vectors of this
# width; `WindLink.send` pads them if the board wants more.
CHANNELS = 4

# Measured on the rig, 15 Aug 2026, by driving one channel at a time and
# having the driver say which fan moved. Seen from the cockpit. Nothing
# recorded this: `WindSettings.json` said only that roles 2 and 3 mapped onto
# the first two channels, and neither SimHub's role numbering nor the
# firmware's channel order says which side that is.
CHANNEL_LEFT = 0
CHANNEL_RIGHT = 1

# The lowest duty that actually turns a fan, measured on this rig the same
# way: 0 stopped it, 1 and 2 did nothing, 3 moved it. About 1.2% - some 25
# times lower than the 29.76% `MinGain` SimHub was configured with, which was
# therefore a comfort setting and not a physical floor.
#
# **1 and 2 are worse than useless, and that is why this is a deadband rather
# than a floor.** The firmware runs `RELEASE` on zero and `FORWARD` on
# anything else, so a duty of 1 energises a motor that cannot overcome its own
# stiction: current, heat, no air. Values below the threshold snap to off
# rather than being passed through or quietly raised to something audible the
# driver did not ask for.
MIN_MOVING_DUTY = 3


def snap_duty(value: int) -> int:
    """A duty the fan can act on: off, or moving. Never stalled."""
    value = max(0, min(255, int(value)))
    return 0 if value < MIN_MOVING_DUTY else value


@dataclass
class WindState:
    """What the layer is doing, for the screen and the logs."""
    connected: bool = False
    # **How many times the link has dropped, and when it last did.** The
    # health report runs every ten seconds and only ever printed `connected`,
    # so an eleven-second outage that healed itself showed up as at most one
    # line saying False - and a seven-second one as nothing whatsoever. The
    # driver reports the fans cutting out; the log has one drop in ten days.
    # These two make the next occurrence a timestamp rather than an
    # impression.
    disconnects: int = 0
    last_drop_at: float | None = None
    port: str | None = None
    firmware: str | None = None
    board: str | None = None
    crc_name: str | None = None
    channels: int = CHANNELS
    last_values: tuple[int, ...] = field(default_factory=tuple)
    frames_sent: int = 0
    write_failures: int = 0
    # Writes that timed out and were ridden out rather than treated as a
    # dead link. Reported separately from `write_failures`, which counts the
    # ones that ended the link - the difference between them is the whole of
    # the 24 Aug fix.
    write_timeouts: int = 0
    resyncs: int = 0
    stale_bytes: int = 0
    # **Frames the device acknowledged, and the worst gap between two of
    # them.** These are about the FIRMWARE, not about the fans.
    #
    # The inference runs one way only. No acknowledgement for longer than the
    # firmware's 1000 ms deadman means the fans were zeroed - that is sound,
    # given a live I2C bus. An acknowledgement means the frame was parsed. It
    # does **not** mean a motor turned: there is no tachometer, no current
    # sense, and no back-channel from the motor shield. Nothing here may ever
    # be phrased as "the fans are running", because that would be a confident
    # well-formed claim about the one thing this app cannot observe.
    frames_accepted: int = 0
    last_ack_at: float | None = None
    max_ack_gap_s: float = 0.0
    # The slowest turn of the 250 ms send loop this session. A loop that
    # overran the deadman is a PC-side cause, and it is otherwise invisible.
    max_loop_s: float = 0.0
    error: str | None = None

    def deadman_gap_s(self, now: float | None = None) -> float | None:
        """How long since the firmware last accepted a frame, or None.

        None before the first acknowledgement of a session - never 0.0, which
        would read as "answered just now" and is the opposite of the truth.
        """
        if self.last_ack_at is None:
            return None
        return (now if now is not None else time.monotonic()) - self.last_ack_at

    def describe(self) -> str:
        if self.error:
            return self.error
        if not self.connected:
            return "The wind simulator is not connected."
        where = f"on {self.port}"
        if self.firmware:
            where += f", firmware {self.firmware}"
        if self.board:
            where += f", {self.board}"
        # Resyncs are surfaced rather than hidden: a link that works only
        # because it keeps resynchronising is not a healthy link, and the
        # driver has no other way to know it is happening.
        note = f", {self.resyncs} resyncs" if self.resyncs else ""
        # The worst gap is said whenever it exceeded the firmware's deadman,
        # because that is the app finally able to state what the driver has
        # been reporting: the fans were off, for this long.
        if self.max_ack_gap_s > DEADMAN_S:
            note += (f", worst {self.max_ack_gap_s:.1f}s without an "
                     f"acknowledgement - the fans were off for "
                     f"{self.max_ack_gap_s - DEADMAN_S:.1f}s of that")
        return (f"Wind simulator {where}. {self.frames_sent} frames sent, "
                f"{self.frames_accepted} accepted{note}.")


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


def _is_write_timeout(exc: BaseException) -> bool:
    """Is this the write that did not complete, or a link that has gone?

    pyserial raises `SerialTimeoutException` for the first and plain
    `SerialException` (or `OSError`) for the second, and only the first is
    survivable - a device that has been unplugged does not start accepting
    bytes again because it was asked twice. Matched on the class rather than
    the message, with the import inside the function so that a machine
    without pyserial still imports this module.
    """
    try:
        import serial
    except ImportError:                                     # pragma: no cover
        return False
    return isinstance(exc, serial.SerialTimeoutException)


class WindLink:
    """One serial connection, owned by one thread.

    Not thread-safe on purpose. `WindSim` below owns an instance and is the
    only thing that touches it, which is what keeps the close-from-send
    deadlock structurally impossible rather than merely avoided.
    """

    # **Closes that never returned, and are therefore still holding a port.**
    # Class-level because they outlive the link that started them - that is the
    # whole problem with them. `{port: thread}`, because the COM number can
    # change across a replug and a claim about the wrong port is exactly the
    # wrong-cause message this exists to remove; and because two abandoned
    # closes must not overwrite each other. See `close` and
    # `WindSim._port_is_held_by_us`.
    _orphaned_closes: dict = {}

    def __init__(self, port: str, *, channels: int = CHANNELS) -> None:
        self.port = port
        self.channels = channels
        self._serial = None
        self._packet_id = arq.BROADCAST_ID
        self.crc = arq.DEFAULT_CRC
        self.firmware: str | None = None
        # The board the firmware says it drives, from the count reply. The
        # reflash changes this string, so it is the line that confirms one.
        self.board: str | None = None
        # Frames the device did not answer, in a row, and rejections it has
        # resynchronised from. Both are reported: a link that works only
        # because it keeps resynchronising is not a healthy link.
        self.unanswered = 0
        self.resyncs = 0
        # Bytes thrown away as stale. Non-zero means a reply arrived late or
        # unread, which is the shape of the fault that stopped the fans twice.
        self.stale_bytes = 0
        # Writes that did not complete inside `WRITE_TIMEOUT_S`, in total and
        # in a row. The run is what decides whether the link is dropped; the
        # total is what says afterwards whether a session was riding out
        # stalls all the way through or met exactly one.
        self.write_timeouts = 0
        self.consecutive_write_timeouts = 0
        # **Acknowledgements, which nothing has ever counted.**
        #
        # `frames_sent` measures intent - it counted a write that timed out -
        # and `connected` only goes False when the link is torn down. Between
        # them they were compatible with ten seconds of dead fans, which is
        # exactly the gap between what the driver reports and what the log
        # says. An accepted frame is the only event that proves the firmware
        # heard us, so it is the only one worth timing.
        self.acks = 0
        self.last_ack_at: float | None = None
        # What became of the most recent frame: "acked", "timeout", "silent",
        # or "rejected". Read by the sender for the per-frame log.
        self.last_outcome: str | None = None

    def open(self, settle: bool = True) -> None:
        """Open without resetting the board into a full-speed blast.

        `settle` waits out the Optiboot window. It is right on a board that
        has just been powered or replugged and pure cost on one that has been
        running for an hour - 1.6 seconds of dead fans, mid-race, for a
        bootloader that finished before the session started. `_connect` tries
        without it first and falls back.
        """
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
        # its bootloader, and bytes sent into that are discarded rather than
        # queued.
        if settle:
            time.sleep(RESET_SETTLE_S)
        handle.reset_input_buffer()
        handle.reset_output_buffer()

    def close(self, graceful: bool = True) -> None:
        """Stop the fans, then let go. Only ever called by the owning thread.

        `graceful` is False when the link is being dropped because it already
        failed. There is then nothing to say to it and no reason to wait for
        it to listen - the firmware's deadman stops the fans a second later
        whatever we do, and the handle we would be writing through is the one
        that just raised.

        **Nothing in here may block without a bound.** On 16 Aug 2026 this
        cost six seconds on the Qt thread and left COM5 held:

            ERROR MainThread the wind thread did not stop within 6s, so COM5
            is still held. Nothing else can open it until this app exits.

        The wind thread had nothing else to do at the time - it was inside
        `_stop.wait(0.25)`, which returns at once - so the six seconds were
        spent here. It is a relative of the SimHub close-from-send deadlock
        this module was told never to copy: the send path is clean, but the
        teardown was writing and flushing through a handle it had already
        decided was dead.
        """
        handle = self._serial
        if handle is None:
            return
        self._serial = None
        if graceful:
            try:
                if handle.is_open:
                    # Courtesy, not the safety mechanism - the firmware's
                    # deadman is what actually guarantees this. But an
                    # explicit zero means the fans stop now rather than up to
                    # a second from now.
                    #
                    # **`handle.flush()` used to follow this, and it is an
                    # unbounded busy-wait.** pyserial's Windows implementation
                    # is `while self.out_waiting: time.sleep(0.05)` with no
                    # timeout and no escape, so a device that is present but
                    # wedged - selective suspend, a stalled endpoint - spins
                    # this thread for ever and raises nothing, which means the
                    # `except` below never sees it. The frame is twelve bytes,
                    # six milliseconds at 19200: there was never anything
                    # worth waiting for on a healthy port, and on an unhealthy
                    # one it was an infinite loop.
                    self._write_through(handle,
                                        arq.motors_payload([0] * self.channels))
            except Exception as exc:                        # noqa: BLE001
                log("wind").debug(
                    "could not stop the fans on the way out: %s", exc)
        # **Closed on a thread of its own, with a bound.** `CancelIoEx` and
        # `CloseHandle` on a surprise-removed CH340 can block inside the
        # driver, and this runs on the path a session shutdown waits for.
        # Leaking a handle on a device that has already gone is cheaper than
        # freezing the app at the end of every session.
        closer = threading.Thread(
            target=self._close_handle, args=(handle,),
            name="PitCrewWindClose", daemon=True)
        closer.start()
        closer.join(CLOSE_TIMEOUT_S)
        if closer.is_alive():
            # **Published, because the reopen has to know.** Leaking the handle
            # is still the right trade against freezing the app - but the port
            # is definitionally still held while this thread runs, so every
            # reopen attempt until it finishes will fail with
            # `PermissionError(13, 'Access is denied.')`, and that error names
            # the symptom rather than the cause.
            #
            # Measured, Road Atlanta 23 Aug 2026: a write timeout at 20:24:05,
            # this warning at 20:24:06, and then sixty-odd identical
            # `Could not open COM5` lines over the next thirty-one minutes -
            # the whole race with the fans dead - none of which mentioned that
            # the app was the thing holding the port.
            WindLink._orphaned_closes[self.port] = closer
            log("wind").warning(
                "closing %s did not return within %.1fs, so it has been left "
                "to the operating system. **This app is still holding the "
                "port** and nothing can reopen it until that close returns.",
                self.port, CLOSE_TIMEOUT_S)

    def _close_handle(self, handle) -> None:
        """Cancel what is still in flight, then close.

        **This is why the close hung, and it is the whole of the fans defect
        on 23 Aug 2026.** The sequence measured that night:

            20:24:05  Lost the wind simulator on COM5: Write timeout
            20:24:06  closing COM5 did not return within 1.0s
            20:24:06  Could not open COM5: PermissionError(13, 'Access is
                      denied.')          ... and again for 31 minutes

        `WRITE_TIMEOUT_S` is 0.25 s, and pyserial's write timeout returns to
        the caller **without cancelling the overlapped write it gave up on**.
        The I/O is still outstanding in the CH340 driver. `close()` then calls
        `CloseHandle`, which blocks until that write completes or is cancelled
        - and it was neither, so the close never returned, the handle was
        abandoned to the operating system, and the port stayed held for the
        rest of the session.

        `cancel_write` is pyserial's own `CancelIoEx` wrapper and exists for
        exactly this. Cancelling first is what lets the close finish inside its
        bound, which is what gives the port back.

        Both cancels are attempted independently and neither may raise: a
        device that has been surprise-removed can fail either one, and getting
        as far as `close()` still matters.
        """
        # **Purge first, then cancel.** `reset_output_buffer` is
        # `PurgeComm(PURGE_TXABORT | PURGE_TXCLEAR)`, which is the documented
        # way to abandon a write that is stuck in the driver; `CancelIoEx`
        # only reaches I/O this process issued on this handle. On 24 Aug 2026
        # the cancels alone were not enough - the close still overran its
        # bound and COM5 stayed held - so both are attempted, cheapest and
        # most specific first.
        for step in ("reset_output_buffer", "cancel_write", "cancel_read"):
            try:
                method = getattr(handle, step, None)
                if method is not None:
                    method()
            except Exception as exc:                        # noqa: BLE001
                log("wind").debug("%s on %s raised: %s", step, self.port, exc)
        try:
            handle.close()
        except Exception as exc:                            # noqa: BLE001
            log("wind").debug("closing %s raised: %s", self.port, exc)

    # ------------------------------------------------------------ protocol

    def _write(self, payload: bytes) -> None:
        """One framed payload. Raises on a dead link; never closes the port.

        **Always the broadcast id, and this is the fix for the fans stopping.**

        Measured, and it is worth writing down because it was hunted across
        four sessions and three wrong diagnoses. Sending sequential ids, the
        fans stopped at frame 128 - which at four frames a second is 33.0
        seconds, and the driver reported 33 seconds at 100% duty and 33
        seconds again at 80%. Identical timing under different loads is not a
        thermal limit and not a supply limit; it is a count.

        Frame 128 is where the sequence wraps from 127 back to 0. The device
        went on ACKNOWLEDGING every frame afterwards - zero resyncs, zero
        unanswered - while the motors stayed dead, so the ARQ layer is
        evidently treating a wrapped id as a packet it has already seen: it
        acknowledges the duplicate and never hands the payload to the motors
        handler. `lastRead` then stops advancing and the firmware's own
        1000 ms deadman zeroes the channels. Permanently, because every frame
        after the wrap looks just as old.

        Id 255 is the broadcast the firmware accepts whatever it was
        expecting - the resync escape hatch - so using it for every frame
        sidesteps the sequence entirely. Nothing is lost by it: a fan value is
        idempotent and superseded a quarter of a second later, so there is
        nothing to retransmit and nothing worth de-duplicating.
        """
        if self._serial is None:
            raise OSError("the port is not open")
        self._write_through(self._serial, payload)

    def _write_through(self, handle, payload: bytes) -> None:
        """The same frame, down a handle named explicitly.

        `close` detaches `_serial` before it says goodbye, so that a failure
        in the middle of a teardown cannot leave a half-closed link behind
        for the next caller. It still needs to write one frame, and it has
        the handle in hand.
        """
        frame = arq.build_frame(arq.BROADCAST_ID, payload, self.crc)
        handle.write(frame)

    def _abandon_stuck_write(self) -> None:
        """Throw away a frame the driver would not take, and clear the way.

        `WRITE_TIMEOUT_S` returns to the caller **without cancelling the
        overlapped write it gave up on** - the same pyserial behaviour that
        made `close` hang. Left in flight it is still there when the next
        frame is written, so one stall becomes every frame afterwards.

        Purge first for the same reason as `_close_handle`, and the input
        buffer too: whatever the device may yet say about the frame that never
        arrived is not an answer to the next one.
        """
        handle = self._serial
        if handle is None:
            return
        for step in ("reset_output_buffer", "cancel_write",
                     "reset_input_buffer"):
            try:
                method = getattr(handle, step, None)
                if method is not None:
                    method()
            except Exception as exc:                        # noqa: BLE001
                log("wind").debug("%s on %s raised: %s", step, self.port, exc)

    def _read_reply(self) -> arq.Reply | None:
        """One reply, read to its own length and no further.

        **A fixed-size read is what broke this.** Asking for three bytes when
        an ACK is two means the third comes out of whatever arrives next, so a
        single unread byte shifts every reply from then on. It happened for
        real: `Command_Hello` answers with the firmware's version letter after
        its acknowledgement, that byte was left in the buffer, and minutes
        later a motors reply came back reading `0x6a` - which is ASCII 'j', the
        version letter from the handshake, finally being consumed as the head
        of somebody else's message. From there the device and this side never
        agreed again, and the fans stopped.

        So the kind byte is read first and decides how much more to take.
        """
        if self._serial is None:
            return None
        # **Value and string packets are read to their length and skipped.**
        # The board sends them for its own reasons - the hello's late
        # version packet is the one that lands mid-stream - and they are not
        # answers to a motors frame. Skipping them to their measured length
        # is what stops one late byte shifting every reply after it. Bounded,
        # so a board streaming junk cannot hold the sender for ever: each
        # read is already bounded by `READ_TIMEOUT_S`, and bytes arrive in
        # bursts, so this rarely waits more than once.
        for _ in range(16):
            head = self._serial.read(1)
            if not head:
                return None
            kind = head[0]
            if kind in (arq.REPLY_ACK, arq.REPLY_NACK):
                wanted = 1 if kind == arq.REPLY_ACK else 2
                return arq.parse_reply(head + self._serial.read(wanted))
            if kind == arq.REPLY_VALUE:
                skipped = head + self._serial.read(1)
            elif kind == arq.REPLY_STRING:
                length = self._serial.read(1)
                skipped = head + length + (
                    self._serial.read(length[0]) if length else b"")
            else:
                skipped = head
            self.stale_bytes += len(skipped)
            log("wind").debug("%s sent %s mid-stream - skipped",
                              self.port, skipped.hex(" "))
        return None

    def _drain(self) -> int:
        """Throw away anything unread. Returns how much there was.

        Called before each frame, because at four frames a second against a
        device that answers in about a millisecond, anything still waiting is
        the last exchange's and cannot be about this one. Belt to the braces
        above: the length-aware read stops the misalignment happening, and
        this stops any that happens anyway from lasting more than one frame.
        """
        if self._serial is None:
            return 0
        waiting = getattr(self._serial, "in_waiting", 0) or 0
        if waiting:
            self._serial.reset_input_buffer()
        return int(waiting)

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
                # **`Command_Hello` answers with a value packet after its
                # acknowledgement: `0x08` then the version letter.** Measured
                # 3 Sep 2026 as `08 6a`, 'j'. It arrives a few milliseconds
                # after the acknowledgement, which is why the drain that used
                # to sit here never caught it: whatever read came next found
                # it instead - for weeks the first motors frame ("replied
                # 0x08, which is not an acknowledgement" after every
                # reconnect), then the channel-count query, which read the
                # marker as a count of eight. Reading it here, to its own
                # length, is what makes every later read clean.
                self._read_version()
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

    def _read_version(self) -> None:
        """Wait for the value packet after a hello's acknowledgement.

        Up to `VERSION_WAIT_S`, returning the moment it lands. Sets
        `firmware` from a printable letter. Anything else that arrives in the
        window is logged as bytes and dropped, because a board whose hello
        tail is not understood must not have it read as the answer to the
        next question - which is exactly what happened to the count query.
        """
        if self._serial is None:
            return
        deadline = time.monotonic() + VERSION_WAIT_S
        while time.monotonic() < deadline:
            head = self._serial.read(1)
            if not head:
                continue
            if head[0] == arq.REPLY_VALUE:
                value = self._serial.read(1)
                if value:
                    letter = value[0]
                    self.firmware = (chr(letter) if 0x20 <= letter < 0x7F
                                     else f"0x{letter:02x}")
                return
            log("wind").info(
                "%s followed its hello with 0x%02x, which is not a version "
                "packet - dropped.", self.port, head[0])
        log("wind").info(
            "%s sent no version packet within %.1fs of its hello.",
            self.port, VERSION_WAIT_S)

    # ------------------------------------------------------- channel count

    def query_channels(self) -> tuple[int | None, bytes]:
        """Ask the board how many channels it drives.

        Returns what it parsed and the raw bytes it parsed it from - the raw
        bytes are the measurement, and they go in the log. Measured 3 Sep
        2026: 36 bytes, arriving 21 ms after the query, naming the count and
        the board - see `arq.split_packets`. Raises on a dead link, like
        every other write here.

        **Only after the hello's tail has landed.** Sent while the board was
        still inside its slow hello, this query was acknowledged and its
        reply never came; `_read_version` waiting first is what fixed that.
        """
        self._drain()
        self._write(arq.motors_count_payload())
        reply = self._read_reply()
        if reply is None or not reply.acknowledged:
            return None, b""
        # The reply is several packets in one burst; the string packet is the
        # long one. Sixty-four bytes is more than any board name SimHub
        # ships, and the read returns at the timeout with what came.
        raw = self._serial.read(64) if self._serial is not None else b""
        return arq.parse_motors_count(raw), raw

    def accepts_width(self, count: int, frames: int = 3) -> bool:
        """Does the board acknowledge zero frames of this width? A
        measurement for the bench, and **not a proof of anything**.

        It was written as a proof and it is not one. **Measured 3 Sep 2026:
        a four-motor board acknowledged 26,875 eight-wide frames in a row
        and the fans ran normally throughout.** The firmware's packet layer
        buffers a frame to its declared length, checks the checksum,
        acknowledges, and hands the payload to the command; the bytes the
        command does not read are discarded with the frame. So an
        acknowledgement says the frame was accepted, and says nothing about
        whether its width matched the board. Over-width is harmless on this
        firmware; under-width is what would hurt, and this cannot detect
        that either. Kept for `wind_bench handshake`, which prints which
        widths are accepted so the next board can be measured the same way.
        """
        if not 1 <= count <= arq.MAX_CHANNELS:
            return False
        for _ in range(frames):
            self._drain()
            self._write(arq.motors_payload([0] * count))
            reply = self._read_reply()
            if reply is None or not reply.acknowledged:
                return False
        return True

    def discover_channels(self, default: int) -> int:
        """Settle `self.channels` against the board, and say how.

        **Never narrower than `default`.** Two facts decide the policy, both
        measured on this board on 3 Sep 2026: the firmware discards the
        bytes of a frame its command does not read, so a frame wider than
        the board is harmless; and an acknowledgement cannot tell a matching
        width from a wider one, so nothing here can PROVE a narrower count
        is safe to send. A declared count wider than the default widens the
        frames; a narrower or unreadable one leaves them at the default, and
        the log says which. The reflash to a two-motor board therefore needs
        no change here: four-wide frames reach it and the surplus is
        dropped.

        The reply format is not known from source. Whatever comes back is
        logged as bytes, and that line is the measurement.
        """
        declared, raw = self.query_channels()
        shown = raw.hex(" ") if raw else "nothing"
        self.board = arq.parse_motors_board(raw)
        on = f" on '{self.board}'" if self.board else ""
        if declared is None:
            width = default
            log("wind").info(
                "%s did not give a channel count this app can read "
                "(reply: %s) - sending %d, the count on file. Wider than "
                "the board is safe, narrower is not, so an unreadable count "
                "never narrows the frame.", self.port, shown, default)
        elif declared > default:
            width = declared
            log("wind").warning(
                "%s declares %d channels%s (reply: %s), more than the %d on "
                "file - frames widened to %d. Channels beyond %d are not "
                "mapped to a fan.", self.port, declared, on, shown, default,
                width, default)
        elif declared < default:
            width = default
            log("wind").info(
                "%s declares %d channels%s (reply: %s); sending %d as on "
                "file - the firmware discards the surplus (measured 3 Sep "
                "2026).", self.port, declared, on, shown, default)
        else:
            width = default
            log("wind").info("%s declares %d channels%s, as on file.",
                             self.port, declared, on)
        self.channels = width
        return width

    def fit(self, values: tuple[int, ...] | list[int]) -> tuple[int, ...]:
        """A vector of exactly the board's width: trimmed, or padded with 0."""
        kept = tuple(values[:self.channels])
        return kept + tuple([0] * (self.channels - len(kept)))

    def send(self, values: tuple[int, ...]) -> bool:
        """Set every channel, and check the device accepted it.

        **Reading the reply is not optional, and leaving it out cost a
        session.** The frames carry a sequential packet id and the firmware
        NACKs one that is not the id it expected. Lose or corrupt a single
        frame - on a CH340 that drops a link ten times in three days, that is
        a matter of when - and its expectation diverges from ours permanently:
        it rejects everything from then on, while `write` goes on succeeding
        because the bytes reach the OS buffer regardless.

        The fans then stop, because the firmware's own deadman zeroes them a
        second after the last frame it accepted. Observed live: wind for one
        corner, then nothing for the rest of the session, and not one line in
        the log - because from this side nothing had gone wrong.

        A rejection is recoverable and cheap to recover from: packet id 255 is
        a broadcast the firmware accepts whatever it was expecting, so the
        next frame resynchronises. Returns whether the device is still with
        us; raises only on a genuinely dead link, and never closes the port.
        """
        stale = self._drain()
        if stale:
            self.stale_bytes += stale
        try:
            self._write(arq.motors_payload(list(self.fit(values))))
        except Exception as exc:                            # noqa: BLE001
            if not _is_write_timeout(exc):
                raise
            self.write_timeouts += 1
            self.consecutive_write_timeouts += 1
            self._abandon_stuck_write()
            if self.consecutive_write_timeouts >= WRITE_TIMEOUT_LIMIT:
                raise
            log("wind").info(
                "%s did not accept a frame within %.2fs (%d in a row, %d "
                "this session) - cancelled and carrying on; the link is kept.",
                self.port, WRITE_TIMEOUT_S, self.consecutive_write_timeouts,
                self.write_timeouts)
            # No frame went out, so there is no reply to wait for. Report the
            # link as alive: this is a hiccup, and the next frame is 250 ms
            # away against a 1000 ms deadman.
            self.last_outcome = "timeout"
            return True
        self.consecutive_write_timeouts = 0
        reply = self._read_reply()
        if reply is None:
            # Silence is not yet a failure. The device answers within a
            # millisecond or so, but a busy moment is not a reason to tear
            # down a working link - `WindSim` counts these and acts on a run
            # of them.
            self.unanswered += 1
            self.last_outcome = "silent"
            return self.unanswered < UNANSWERED_LIMIT
        self.unanswered = 0
        if reply.acknowledged:
            self.acks += 1
            self.last_ack_at = time.monotonic()
            self.last_outcome = "acked"
            return True
        # Rejected. Resynchronise on the broadcast id rather than carrying a
        # disagreement about sequence for the rest of the session.
        # Every frame already goes out on the broadcast id, so there is no
        # sequence left to resynchronise - a rejection here is a checksum or a
        # length fault rather than a lost place. Counted and reported, because
        # a link that keeps being rejected is not a healthy one.
        self.resyncs += 1
        self.last_outcome = "rejected"
        log("wind").info("%s %s", self.port, reply.describe())
        return True


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
        # When it was last set, so a value nobody has refreshed can be faded
        # out rather than blown for ever - see `_decayed_locked`.
        self._wanted_at: float | None = None
        # What the car was doing when the value was set, carried so the frame
        # log can be read against a lap without guessing. None where the
        # caller did not say - never 0.0, which would read as a stopped car.
        self._context: dict = {}
        # A driver-pressed marker waiting to be stamped on the next frame.
        self._marker: str | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._link: WindLink | None = None
        # **What every link before this one counted.** The counters live on
        # the link, and a link is replaced at every reconnect - so for four
        # days the health line read `resyncs 1 · stale 3 · timeouts 0`
        # through 106 teardowns, because each new link started from zero and
        # the report copied it verbatim. These are added in `_drop_link` so
        # the state reports the session, not the most recent link.
        self._acks_before = 0
        self._resyncs_before = 0
        self._stale_before = 0
        self._timeouts_before = 0

    # ------------------------------------------------------------- control

    def set_output(self, values: tuple[int, ...] | list[int],
                   context: dict | None = None) -> None:
        """The value the fans should be at. Supersedes anything waiting.

        Deliberately last-wins rather than queued: a fan command from four
        seconds ago describes a corner the driver has already left, and
        replaying it faithfully is worse than skipping it.

        `context` is whatever the caller knows about the car - speed, whether
        it is on track, whether the game is paused. It is carried only into
        the frame log, never into what is sent, and it is optional because the
        bench and the replay paths have no car to describe.
        """
        clamped = tuple(snap_duty(v) for v in values[:self._channels])
        padded = clamped + tuple([0] * (self._channels - len(clamped)))
        with self._lock:
            self._wanted = padded
            self._wanted_at = time.monotonic()
            if context is not None:
                self._context = context

    def mark(self, note: str) -> None:
        """Stamp the next frame with something the driver noticed.

        **The one channel that carries what no instrument here can see.**
        Nothing on this side observes a fan - no tachometer, no current sense
        - so a driver saying "now" is the only evidence that will ever exist
        for a fan that stopped while the link stayed perfect. Stamped on the
        next frame rather than logged on its own so it lands in the same row
        as the duty and the speed it belongs to.
        """
        with self._lock:
            self._marker = note

    def _log_frame(self, values: tuple[int, ...], outcome: str | None) -> None:
        """One line per frame, at the send rate, continuously.

        **Continuously, and not a ring buffer dumped when something goes
        wrong.** The failure this is built to catch - a fan that stops while
        the link stays healthy - produces no adverse event at all, so a buffer
        waiting for one would never dump and the whole exercise would be blind
        to the case it exists for.

        The wall clock goes in beside the monotonic one so this aligns to
        `lap_frames`, which the last attempt could only do through
        `laps.recorded_at` at one-second truncation - and that slop was large
        enough to swing the finding from below chance to nothing.

        About 115 bytes a frame at 20 Hz is some 8 MB an hour, which is why
        the frame log has its own rotation size - see `diagnostics`. At the
        old 2 MB it rolled every five minutes and had lost tonight's drops
        before anyone looked. `speed_kmh` is
        None rather than 0.0 where the caller did not say, because a stopped
        car and an unknown one need opposite readings.
        """
        with self._lock:
            context = dict(self._context)
            marker, self._marker = self._marker, None
        speed = context.get("speed_kmh")
        log("wind.frames").info(
            "%.3f %.3f duty=%s outcome=%s speed=%s on_track=%s paused=%s%s",
            time.time(), time.monotonic(),
            ",".join(str(v) for v in values), outcome or "none",
            "?" if speed is None else f"{speed:.1f}",
            context.get("on_track", "?"), context.get("paused", "?"),
            f" MARK={marker}" if marker else "")

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
        """Stop the thread and let go of the port.

        The join is generous because the worker can be a couple of seconds
        into opening a link when it is asked to stop - a 1.6 s settle plus a
        handshake - and abandoning it there is what leaves COM5 held.

        **Observed: the port stayed locked with no session running**, so the
        bench tool could not be used without closing the whole app. One
        process owns a serial port; if this one keeps it after the session
        that wanted it has ended, nothing else can talk to the device. A
        thread that will not stop is now said out loud rather than left to be
        discovered as a permission error somewhere else.
        """
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is None:
            return
        thread.join(timeout=6.0)
        if thread.is_alive():
            log("wind").error(
                "the wind thread did not stop within 6s, so %s is still held. "
                "Nothing else can open it until this app exits.",
                self.state.port or "the serial port")
        else:
            log("wind").info("wind simulator released %s",
                             self.state.port or "the serial port")

    # -------------------------------------------------------------- thread

    def _run(self) -> None:
        """Own the link, keep it fed, and rebuild it when it dies.

        The link is opened once and held. Re-opening a serial port to send
        four bytes would be wasteful even if it were harmless, and it resets
        the board every time.
        """
        backoff = RECONNECT_S
        last_turn: float | None = None
        due = time.monotonic()
        # A link that has just dropped after working is a re-enumeration, not
        # an absent device: try it at once, and without the bootloader settle.
        # Only once - if the quick attempt fails, it gets the full treatment.
        quick = False
        while not self._stop.is_set():
            if self._link is None and not self._connect(settle=not quick):
                # Nothing to talk to. Back off rather than poll a missing
                # device at a steady rate for the whole session, and run
                # discovery again each time - the COM number can change
                # across a replug.
                self._stop.wait(FIRST_RETRY_S if quick else backoff)
                if not quick:
                    backoff = min(backoff * 2, RECONNECT_MAX_S)
                quick = False
                continue
            began = time.monotonic()
            if not self._send_once():
                # Not graceful: `_send_once` returning False means the link
                # already failed, so there is nothing to say to it.
                self._drop_link(graceful=False)
                self._stop.wait(FIRST_RETRY_S)
                backoff = RECONNECT_S
                quick = True
                # A turn measured across a reconnect is the outage, not the
                # loop: the reconnect line already reports that figure.
                last_turn = None
                continue
            backoff = RECONNECT_S
            quick = False
            # **How long a turn of this loop actually took, and where.** A
            # turn that overran the deadman is a PC-side cause of dead fans
            # and would otherwise be invisible - every counter looks perfect
            # either side of it. The split says which side of this process
            # to look at: time inside the serial exchange is the CH340
            # driver blocking past its own timeouts; time outside it is this
            # thread not being scheduled - every one of the six overruns on
            # file to 3 Sep 2026 coincided with an audio stream being opened
            # (a voice-pack miss synthesised aloud, or the transducer
            # starting), and this is the number that says whether that is a
            # starved thread or a stalled driver.
            now = time.monotonic()
            inside = now - began
            if last_turn is not None:
                took = now - last_turn
                if took > self.state.max_loop_s:
                    self.state.max_loop_s = took
                    if took > DEADMAN_S:
                        log("wind").warning(
                            "the wind send loop took %.2fs for one turn "
                            "against a %.1fs deadman - the fans were off and "
                            "this side is the reason. %.2fs of it was inside "
                            "the serial exchange, %.2fs waiting to run.",
                            took, DEADMAN_S, inside, took - inside)
            last_turn = now
            # **Wait the remainder of the period, not the whole of it.** The
            # send blocks for the round trip - 9.2 ms measured - and sleeping
            # a further full interval on top made the period the sum of the
            # two. At 250 ms that was a 4% error nobody would notice; at
            # 16.7 ms it is 55%, and the loop ran at 33 Hz while claiming 60.
            # Scheduling against a deadline keeps the rate honest, and a turn
            # that overruns simply sends the next frame at once rather than
            # trying to catch up on a backlog that no longer describes the car.
            due += SEND_INTERVAL_S
            self._stop.wait(max(0.0, due - time.monotonic()))
            if due < time.monotonic() - SEND_INTERVAL_S:
                due = time.monotonic()
        self._drop_link()

    def _port_is_held_by_us(self, port: str) -> bool:
        """Is an abandoned close still sitting on **this** port?

        `WindLink.close` bounds itself and leaks the handle rather than freeze
        the app, which is the right trade - but while that closer thread runs,
        the port is ours and no reopen of it can possibly succeed. Knowing that
        is the difference between an honest message and sixty misleading ones.

        **Keyed by port, because `_run` re-runs `find_port()` on every
        reconnect** - its own comment says the COM number can change across a
        replug. Without the key, an abandoned close on COM5 would make a
        perfectly innocent failure to open COM6 report that this app was
        holding it, and send the driver to restart an app that a settle would
        have fixed. That is the same wrong-cause message from the other side.
        """
        closer = WindLink._orphaned_closes.get(port)
        if closer is None:
            return False
        if closer.is_alive():
            return True
        # It finished after all. Forget it, so a later failure on this port is
        # judged on its own evidence rather than on this one.
        WindLink._orphaned_closes.pop(port, None)
        return False

    def _connect(self, settle: bool = True) -> bool:
        port = find_port()
        if port is None:
            if self.state.error is None:
                self.state.error = (
                    "No wind simulator found. Check it is plugged in and "
                    "powered.")
                log("wind").info(self.state.error)
            return False
        if self._port_is_held_by_us(port):
            # **Do not even try.** The port is ours and the open cannot
            # succeed, so attempting it buys nothing and costs a settle.
            message = (
                f"{port} cannot be reopened because this app is still holding "
                f"it - a close from an earlier failure has not returned. The "
                f"fans stay off until it does, and if it never does they need "
                f"an app restart.")
            if self.state.error != message:
                log("wind").warning(message)
            self.state.error = message
            return False
        link = WindLink(port, channels=self._channels)
        try:
            link.open(settle=settle)
        except Exception as exc:                            # noqa: BLE001
            # **Said once, not sixty times.** Measured at Road Atlanta on
            # 23 Aug 2026: a write timeout dropped the link a minute into the
            # race and the reconnect logged a byte-identical
            # `PermissionError(13, 'Access is denied.')` against COM5 every
            # thirty seconds for the next thirty-one minutes.
            message = f"Could not open {port}: {exc}"
            if self.state.error != message:
                log("wind").warning(message)
            self.state.error = message
            return False
        if not link.handshake():
            if not settle:
                # It opened, so the device is there; it just was not ready to
                # talk. That is the bootloader, which is what the settle is
                # for - so pay for it now, having established it is needed,
                # rather than on every reconnect whether it is or not.
                link.close(graceful=False)
                return self._connect(settle=True)
            self.state.error = (
                f"{port} opened but would not answer. It may not be the wind "
                f"simulator.")
            link.close(graceful=False)
            return False
        try:
            link.discover_channels(self._channels)
        except Exception as exc:                            # noqa: BLE001
            # It answered a hello and then died under the next write: a
            # link that failed, not one to keep.
            message = f"{port} failed while being asked its channel count: {exc}"
            if self.state.error != message:
                log("wind").warning(message)
            self.state.error = message
            link.close(graceful=False)
            return False
        self._link = link
        self.state.connected = True
        self.state.channels = link.channels
        # Read off the hello's value packet - never assigned before 3 Sep
        # 2026, so `describe()` had a firmware clause that never printed.
        self.state.firmware = link.firmware
        self.state.board = link.board
        self.state.port = port
        self.state.crc_name = link.crc.name
        self.state.error = None
        if self.state.last_drop_at is not None:
            # **How long the link was down, said on the line that ends it.**
            # For four days every drop logged only "Lost" and "ready", and
            # whether the fans had stopped in between - which is the only
            # thing the driver cares about - had to be recovered afterwards
            # by subtracting timestamps across 106 pairs of lines. Against
            # the deadman, because that is the number that decides it; the
            # ack-gap warning in `_send_once` carries the exact figure.
            down = time.monotonic() - self.state.last_drop_at
            if down < DEADMAN_S:
                log("wind").info(
                    "wind simulator back on %s after %.2fs - inside the "
                    "firmware's %.1fs deadman.", port, down, DEADMAN_S)
            else:
                log("wind").warning(
                    "wind simulator back on %s after %.2fs - past the "
                    "firmware's %.1fs deadman, so the fans were zeroed for "
                    "at least %.2fs.", port, down, DEADMAN_S,
                    down - DEADMAN_S)
        else:
            log("wind").info("wind simulator ready on %s", port)
        return True

    def _send_once(self) -> bool:
        link = self._link
        if link is None:
            return False
        with self._lock:
            values = self._decayed_locked()
        try:
            alive = link.send(values)
        except Exception as exc:                            # noqa: BLE001
            self.state.write_failures += 1
            self.state.error = f"Lost the wind simulator on {link.port}: {exc}"
            log("wind").warning(self.state.error)
            return False
        if not alive:
            # Writes are still succeeding - the bytes reach the OS buffer
            # whatever the device does - so this is the only way a board that
            # has stopped listening is ever noticed.
            self.state.error = (
                f"{link.port} stopped answering after "
                f"{self.state.frames_sent} frames. Reconnecting.")
            log("wind").warning(self.state.error)
            return False
        self.state.resyncs = self._resyncs_before + link.resyncs
        self.state.stale_bytes = self._stale_before + link.stale_bytes
        self.state.write_timeouts = self._timeouts_before + link.write_timeouts
        # **A frame that timed out did not go anywhere.** Counting it as sent
        # made `frames_sent` a measure of intent while reading as a measure of
        # delivery - rule 3, in the counter the health report leads with.
        if link.last_outcome != "timeout":
            self.state.frames_sent += 1
        self.state.frames_accepted = self._acks_before + link.acks
        # **The gap is measured between consecutive acknowledgements, across
        # links.** It used to be copied from the link and then measured, so
        # an acknowledged frame always read as a gap of nothing, and a new
        # link brought a `None` that erased the last acknowledgement of the
        # old one. The reconnect - 106 of them in four days, three of them
        # long enough to zero the fans - was the one interval this could not
        # see. Now the previous acknowledgement is kept until this link
        # produces one, and the interval that closes is the figure reported.
        previous = self.state.last_ack_at
        if link.last_ack_at is not None:
            self.state.last_ack_at = link.last_ack_at
        if previous is None:
            gap = None
        elif link.last_outcome == "acked":
            gap = self.state.last_ack_at - previous
        else:
            gap = time.monotonic() - previous
        if gap is not None and gap > self.state.max_ack_gap_s:
            self.state.max_ack_gap_s = gap
            # Said once, when it crosses, because this is the line that has
            # been missing from every fan report the driver has ever made.
            if gap > DEADMAN_S:
                if link.last_outcome == "acked":
                    log("wind").warning(
                        "%s went %.2fs between acknowledgements - the "
                        "firmware's %.1fs deadman will have zeroed the fans "
                        "for %.2fs of that.",
                        link.port, gap, DEADMAN_S, gap - DEADMAN_S)
                else:
                    log("wind").warning(
                        "%s has not acknowledged a frame for %.2fs - the "
                        "firmware's %.1fs deadman will have zeroed the fans "
                        "%.2fs ago. Last outcome %s.",
                        link.port, gap, DEADMAN_S, gap - DEADMAN_S,
                        link.last_outcome)
        # What the board was actually sent, at its own width - not the
        # app's vector, which may be wider or narrower than the board.
        sent = link.fit(values)
        self.state.last_values = sent
        self._log_frame(sent, link.last_outcome)
        return True

    def _decayed_locked(self) -> tuple[int, ...]:
        """The value to send, faded out if nothing has set one recently.

        **Holding the last value through a telemetry gap is right, and
        holding it for ever is not.**

        The send loop is a fixed 250 ms timer, completely decoupled from the
        60 Hz feed, so a gap in telemetry leaves `_wanted` frozen and the
        thread goes on transmitting it - which is what keeps the firmware's
        deadman fed and stops the fans cutting out for a stream hiccup that
        cost the driver nothing. That is deliberate and must not change.

        What was missing is an end to it. If the console sleeps, the network
        drops, or the packet thread dies, the fans blow at whatever speed the
        car was doing when the feed stopped, indefinitely - two 4000 RPM
        blowers at a corner the driver left ten minutes ago. So the value is
        held verbatim for `HOLD_S`, which covers any gap worth riding out,
        and then faded rather than cut: a hard stop would be as startling as
        the wind itself.

        The deadman stays fed throughout either way - this changes what is
        sent, never whether.

        Caller holds `_lock`.
        """
        if self._wanted_at is None or not any(self._wanted):
            return self._wanted
        stale_for = time.monotonic() - self._wanted_at
        if stale_for <= HOLD_S:
            return self._wanted
        if stale_for >= HOLD_S + DECAY_S:
            return tuple([0] * self._channels)
        scale = 1.0 - (stale_for - HOLD_S) / DECAY_S
        return tuple(snap_duty(int(v * scale)) for v in self._wanted)

    def _drop_link(self, graceful: bool = True) -> None:
        """Tear the link down here, on the owning thread, and nowhere else.

        `graceful` is False when the link is being dropped because it failed.
        Writing a courtesy stop through a handle that has just raised buys
        nothing - the firmware's deadman has already zeroed the fans - and it
        is the write that used to hang the teardown.
        """
        link, self._link = self._link, None
        if link is not None:
            # Bank what this link counted before it goes, so the next one
            # adds to the session rather than restarting it.
            self._acks_before += link.acks
            self._resyncs_before += link.resyncs
            self._stale_before += link.stale_bytes
            self._timeouts_before += link.write_timeouts
            if self.state.connected:
                # Counted so a drop that heals inside one ten-second report
                # cycle still leaves a mark. Until now a 7-second outage could
                # fall entirely between two reports and leave no trace at all,
                # which is most of why this was so hard to pin down.
                self.state.disconnects += 1
                self.state.last_drop_at = time.monotonic()
            self.state.connected = False
            link.close(graceful=graceful)
        self.state.connected = False
