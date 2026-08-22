"""The wind simulator's framing and its link, without an Arduino.

The device is a Sector 17 / Redion WSP whose firmware source SimHub deleted on
its way out, so the framing here is reconstructed and the CRC polynomial could
not be read off anything. It was recovered by asking the board instead - see
`test_the_measured_checksum_is_tried_first`. These tests pin the shape of the
protocol and, more importantly, the two behaviours that exist because of that
uncertainty: the handshake determines the checksum rather than assuming it,
and a write failure never closes the port from inside the write.

Nothing here opens a serial port.
"""
from __future__ import annotations

import threading
import time

import pytest

from pitcrew.rig import arq, wind


# ------------------------------------------------------------------ framing

def test_a_frame_is_header_id_length_payload_checksum():
    frame = arq.build_frame(7, b"\x03V", arq.DEFAULT_CRC)
    assert frame[:2] == arq.FRAME_HEADER
    assert frame[2] == 7            # packet id
    assert frame[3] == 2            # length
    assert frame[4:6] == b"\x03V"
    assert len(frame) == 7          # + one checksum byte


def test_the_checksum_covers_the_body_and_not_the_header():
    """Including the two header bytes is the obvious mistake, and it produces
    a device that rejects everything with reason 4."""
    frame = arq.build_frame(7, b"\x03V", arq.DEFAULT_CRC)
    body = frame[2:-1]
    assert frame[-1] == arq.DEFAULT_CRC(body)
    assert frame[-1] != arq.DEFAULT_CRC(frame[:-1])


def test_every_channel_goes_every_time():
    """The firmware reads exactly `motorCount()` raw bytes with no framing, so
    a short write leaves it waiting mid-command for bytes that never come."""
    payload = arq.motors_payload([10, 20, 0, 0])
    assert payload == bytes([arq.MESSAGE_HEADER]) + b"VS" + bytes([10, 20, 0, 0])


def test_a_payload_over_the_firmware_limit_is_refused_here():
    """Better a ValueError than a NACK reason 2 from a fan controller."""
    with pytest.raises(ValueError):
        arq.build_frame(1, b"x" * (arq.MAX_PAYLOAD + 1))


def test_a_channel_value_outside_a_byte_is_refused():
    with pytest.raises(ValueError):
        arq.motors_payload([300])


def test_the_sequence_wraps_at_127_and_never_becomes_the_broadcast_id():
    assert arq.next_id(0) == 1
    assert arq.next_id(126) == 127
    assert arq.next_id(127) == 0
    assert arq.BROADCAST_ID not in {arq.next_id(i) for i in range(128)}


# ------------------------------------------------------------------ replies

def test_an_ack_is_recognised():
    reply = arq.parse_reply(bytes([arq.REPLY_ACK, 12]))
    assert reply.acknowledged is True
    assert reply.packet_id == 12


def test_a_bad_checksum_nack_is_distinguishable_from_every_other_refusal():
    """This is what makes the polynomial knowable rather than guessable."""
    bad_crc = arq.parse_reply(bytes([arq.REPLY_NACK, 3, arq.NACK_BAD_CRC]))
    bad_length = arq.parse_reply(bytes([arq.REPLY_NACK, 3, 2]))
    assert bad_crc.bad_checksum is True
    assert bad_length.bad_checksum is False
    assert "checksum did not match" in bad_crc.describe()


def test_a_truncated_reply_is_not_guessed_at():
    assert arq.parse_reply(bytes([arq.REPLY_ACK])) is None
    assert arq.parse_reply(b"") is None


# ------------------------------------------------------------- fake device

class FakeSerial:
    """An Arduino that accepts exactly one checksum, and says so when wrong."""

    def __init__(self, *, speaks: arq.CrcVariant, dead: bool = False,
                 silent: bool = False) -> None:
        self.speaks = speaks
        self.dead = dead
        self.silent = silent
        self.is_open = True
        self.written: list[bytes] = []
        self.closed = False
        self._pending = b""
        self.dtr_before_open: bool | None = None

    def write(self, data: bytes) -> int:
        if self.dead:
            import serial
            raise serial.SerialException("device stopped functioning")
        self.written.append(data)
        packet_id, length = data[2], data[3]
        body = data[2:-1]
        if self.silent:
            self._pending = b""
        elif data[-1] == self.speaks(body):
            self._pending = bytes([arq.REPLY_ACK, packet_id])
        else:
            self._pending = bytes([arq.REPLY_NACK, packet_id,
                                   arq.NACK_BAD_CRC])
        assert length == len(data) - 5
        return len(data)

    def read(self, size: int = 1) -> bytes:
        out, self._pending = self._pending[:size], self._pending[size:]
        return out

    def flush(self) -> None:
        pass

    def reset_input_buffer(self) -> None:
        pass

    def reset_output_buffer(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True
        self.is_open = False


@pytest.fixture()
def no_reset_delay(monkeypatch):
    monkeypatch.setattr(wind, "RESET_SETTLE_S", 0.0)


def link_onto(fake: FakeSerial) -> wind.WindLink:
    link = wind.WindLink("COM_TEST")
    link._serial = fake
    return link


# --------------------------------------------------------------- handshake

@pytest.mark.parametrize("variant", arq.CRC_VARIANTS)
def test_the_handshake_finds_whichever_checksum_the_device_speaks(variant):
    """SimHub deleted the firmware source before the polynomial could be read
    off it. The device distinguishes a bad checksum from every other fault, so
    the answer is asked for rather than assumed."""
    link = link_onto(FakeSerial(speaks=variant))
    assert link.handshake() is True
    assert link.crc.name == variant.name


def test_a_device_that_rejects_everything_is_reported_not_driven():
    """Guessing on past four rejections would mean sending fan commands the
    firmware will not accept, into hardware, hoping."""
    class RejectsAll(arq.CrcVariant):
        pass

    unknown = RejectsAll("nothing-we-know", 0x9B, reflected=False)
    link = link_onto(FakeSerial(speaks=unknown))
    assert link.handshake() is False


def test_silence_is_not_treated_as_a_wrong_checksum():
    """A board still resetting answers nothing, and trying three more
    polynomials at it neither helps nor tells you anything."""
    fake = FakeSerial(speaks=arq.DEFAULT_CRC, silent=True)
    link = link_onto(fake)
    assert link.handshake() is False
    assert len(fake.written) == 1, "it kept asking a device that was not there"


def test_the_handshake_opens_on_the_broadcast_id():
    """There is no way to know where the sequence stands on a board that has
    been talking to something else all week."""
    fake = FakeSerial(speaks=arq.DEFAULT_CRC)
    link_onto(fake).handshake()
    assert fake.written[0][2] == arq.BROADCAST_ID


# ------------------------------------------------------- the deadlock rule

def test_a_failed_write_does_not_close_the_port():
    """The exact shape of the deadlock that wedged SimHub: a failing write
    called Close() on a handle whose reader was parked in EndRead, and the
    process then survived a force-kill in an unkillable kernel wait."""
    fake = FakeSerial(speaks=arq.DEFAULT_CRC, dead=True)
    link = link_onto(fake)
    with pytest.raises(Exception):
        link.send((0, 0, 0, 0))
    assert fake.closed is False, "closed the port from inside the write"


def test_the_owning_thread_closes_and_stops_the_fans_doing_it():
    fake = FakeSerial(speaks=arq.DEFAULT_CRC)
    link = link_onto(fake)
    link.send((200, 200, 0, 0))
    link.close()
    assert fake.closed is True
    last = fake.written[-1]
    assert last[4:7] == bytes([arq.MESSAGE_HEADER]) + b"VS"
    assert last[7:11] == bytes([0, 0, 0, 0]), "let go without stopping the fans"


# ------------------------------------------------------------- the layer

def test_setting_an_output_never_blocks_and_supersedes_what_is_waiting():
    """A fan command from four seconds ago describes a corner the driver has
    already left. Last wins; nothing queues."""
    sim = wind.WindSim()
    sim.set_output((10, 10, 0, 0))
    sim.set_output((90, 90, 0, 0))
    assert sim._wanted == (90, 90, 0, 0)


def test_values_are_clamped_and_padded_to_the_channel_count():
    sim = wind.WindSim()
    sim.set_output((999, -5))
    assert sim._wanted == (255, 0, 0, 0)


def test_missing_pyserial_disables_the_fans_and_nothing_else(monkeypatch):
    """CLAUDE.md: the app observes and advises. An output that cannot start
    must never be able to stop a session being recorded."""
    monkeypatch.setattr(wind, "available", lambda: False)
    sim = wind.WindSim()
    sim.start()
    assert sim._thread is None
    assert "pyserial" in sim.state.error
    sim.shutdown()


def test_no_device_found_is_reported_rather_than_raised(monkeypatch):
    monkeypatch.setattr(wind, "find_port", lambda: None)
    sim = wind.WindSim()
    assert sim._connect() is False
    assert "not connected" in sim.state.describe().lower() \
        or "no wind simulator" in sim.state.error.lower()


def test_the_thread_keeps_sending_a_value_that_has_not_changed(monkeypatch):
    """The firmware zeroes every channel after 1000 ms without a motors read,
    so send-on-change would make the fans stutter whenever the driver held a
    steady speed."""
    fake = FakeSerial(speaks=arq.DEFAULT_CRC)
    monkeypatch.setattr(wind, "find_port", lambda: "COM_TEST")
    monkeypatch.setattr(wind, "SEND_INTERVAL_S", 0.01)
    monkeypatch.setattr(wind, "RESET_SETTLE_S", 0.0)

    def fake_open(self, settle=True):
        # `settle` is the conditional Optiboot wait - a reconnect to a board
        # that has been running for an hour does not need it, and 1.6 s of
        # dead fans mid-race is what paying for it anyway costs.
        self._serial = fake

    monkeypatch.setattr(wind.WindLink, "open", fake_open)

    sim = wind.WindSim()
    sim.set_output((120, 120, 0, 0))
    sim.start()
    try:
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and sim.state.frames_sent < 5:
            time.sleep(0.01)
    finally:
        sim.shutdown()

    assert sim.state.frames_sent >= 5, (
        "the value never changed, so nothing was resent, and the firmware "
        "deadman would have stopped the fans")
    assert sim.state.crc_name == arq.DEFAULT_CRC.name


def test_the_link_is_rebuilt_after_it_dies(monkeypatch):
    """Windows can hand back a different COM number after a replug, so
    discovery runs again rather than reusing the old one."""
    looked_up: list[int] = []

    def counting_find():
        looked_up.append(1)
        return None

    monkeypatch.setattr(wind, "find_port", counting_find)
    monkeypatch.setattr(wind, "RECONNECT_S", 0.01)
    sim = wind.WindSim()
    sim.start()
    try:
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and len(looked_up) < 3:
            time.sleep(0.01)
    finally:
        sim.shutdown()
    assert len(looked_up) >= 3, "gave up after the first failure"


def test_shutdown_joins_the_thread(monkeypatch):
    monkeypatch.setattr(wind, "find_port", lambda: None)
    monkeypatch.setattr(wind, "RECONNECT_S", 0.01)
    sim = wind.WindSim()
    sim.start()
    thread = sim._thread
    sim.shutdown()
    assert thread is not None
    assert not thread.is_alive()
    assert threading.active_count() >= 1


# ------------------------------------------------------ measured on the rig

def test_the_measured_checksum_is_tried_first():
    """Asked of the Redion on COM5, 15 Aug 2026: it rejected Dallas/Maxim,
    CRC-8/ATM and SAE-J1850 - each with NACK reason 4 - and acknowledged
    DVB-S2. Dallas/Maxim is what a reasonable person would have hardcoded,
    and it would have driven nothing at all."""
    assert arq.DEFAULT_CRC.name == "crc8-dvb-s2"
    assert arq.DEFAULT_CRC.polynomial == 0xD5
    assert arq.DEFAULT_CRC.reflected is False
    assert arq.CRC_VARIANTS[0] is arq.DEFAULT_CRC


def test_the_alternatives_are_kept_so_another_board_can_still_be_found():
    """One device was measured. A reflash or a replacement could differ."""
    assert len(arq.CRC_VARIANTS) >= 4
    assert {v.name for v in arq.CRC_VARIANTS} >= {"dallas-maxim", "crc8-atm"}


def test_channel_zero_is_the_left_fan_and_one_is_the_right():
    """Established by driving one channel at a time and having the driver say
    which moved, seen from the cockpit. Nothing recorded it: SimHub's config
    said only that roles 2 and 3 mapped onto the first two channels."""
    assert wind.CHANNEL_LEFT == 0
    assert wind.CHANNEL_RIGHT == 1
    payload = arq.motors_payload([200, 0, 0, 0])
    assert payload[3 + wind.CHANNEL_LEFT] == 200, "left is not channel 0"


def test_a_missing_device_is_backed_off_rather_than_polled_all_session():
    assert wind.RECONNECT_MAX_S > wind.RECONNECT_S


def test_a_duty_below_the_start_threshold_is_off_rather_than_stalled():
    """Measured on the rig: 0 stopped the fan, 1 and 2 did nothing, 3 moved
    it. The firmware runs RELEASE on zero and FORWARD on anything else, so a
    duty of 1 energises a motor that cannot turn - current and heat, no air.
    """
    assert wind.snap_duty(0) == 0
    assert wind.snap_duty(1) == 0
    assert wind.snap_duty(2) == 0
    assert wind.snap_duty(wind.MIN_MOVING_DUTY) == wind.MIN_MOVING_DUTY
    assert wind.snap_duty(200) == 200


def test_the_deadband_never_raises_a_value_the_driver_did_not_ask_for():
    """Snapping up to the threshold would be wind he did not request. Off is
    the honest answer to "less than this fan can do"."""
    assert wind.snap_duty(2) != wind.MIN_MOVING_DUTY


def test_the_deadband_applies_on_the_way_in():
    sim = wind.WindSim()
    sim.set_output((2, 200, 0, 0))
    assert sim._wanted == (0, 200, 0, 0)


def test_the_measured_floor_is_far_below_what_simhub_was_set_to():
    """SimHub's MinGain was 29.76%. The fan starts at about 1.2%."""
    assert wind.MIN_MOVING_DUTY / 255 * 100 < 2.0


# ------------------------------------------------ the frame that stopped them

def test_every_frame_goes_out_on_the_broadcast_id():
    """The fix for the fans stopping, and it took four sessions to find.

    On sequential ids the fans died at frame 128 - which at four frames a
    second is 33.0 seconds, and the driver reported 33 seconds at 100% duty
    and 33 seconds again at 80%. Identical timing under two different loads is
    not thermal and not a supply limit; it is a count. Frame 128 is where the
    sequence wraps from 127 back to 0.

    The device kept ACKNOWLEDGING after the wrap - zero resyncs, zero
    unanswered - while the motors stayed dead, so the ARQ layer evidently
    reads a wrapped id as a packet it has already seen: it acknowledges the
    duplicate and never passes the payload to the motors handler. `lastRead`
    stops advancing and the firmware's own deadman zeroes the channels.

    Id 255 is the broadcast the firmware accepts whatever it expected. A fan
    value is idempotent and superseded a quarter second later, so there is
    nothing to retransmit and nothing worth de-duplicating.
    """
    fake = FakeSerial(speaks=arq.DEFAULT_CRC)
    link = link_onto(fake)
    for _ in range(200):
        link.send((100, 100, 0, 0))
    ids = {frame[2] for frame in fake.written}
    assert ids == {arq.BROADCAST_ID}, (
        f"the sequence is still being walked: saw ids {sorted(ids)[:8]}...")


def test_the_sequence_never_wraps_because_it_is_never_used():
    """Two hundred frames is well past where 128 would have bitten."""
    fake = FakeSerial(speaks=arq.DEFAULT_CRC)
    link = link_onto(fake)
    for _ in range(200):
        link.send((80, 80, 0, 0))
    assert len(fake.written) == 200
    assert all(frame[2] == arq.BROADCAST_ID for frame in fake.written)


# ------------------------------------------------- the teardown that hung

def test_a_failed_link_is_let_go_without_writing_through_it():
    """**The six seconds that held COM5.** 16 Aug 2026:

        ERROR MainThread the wind thread did not stop within 6s, so COM5 is
        still held. Nothing else can open it until this app exits.

    The wind thread was inside `_stop.wait(0.25)` at the time, which returns
    at once, so the six seconds were spent in `close` - writing a courtesy
    stop and then flushing, through a handle that had just raised. pyserial's
    Windows `flush` is `while self.out_waiting: sleep(0.05)` with no timeout,
    so a device that is present but wedged spins it for ever and raises
    nothing, which is why the `except` around it never caught anything.

    A link being dropped because it failed gets nothing said to it. The
    firmware's own deadman stops the fans a second later regardless.
    """
    fake = FakeSerial(speaks=arq.DEFAULT_CRC)
    link = link_onto(fake)
    link.close(graceful=False)
    assert fake.written == [], "wrote through a handle it had declared dead"
    assert fake.closed is True


def test_a_graceful_close_still_stops_the_fans_now():
    """The deadman is the guarantee; this is so the fans stop at the end of a
    session rather than up to a second later."""
    fake = FakeSerial(speaks=arq.DEFAULT_CRC)
    link = link_onto(fake)
    link.close()
    assert len(fake.written) == 1
    assert fake.written[0][-2] == 0, "the last channel was not zeroed"
    assert fake.closed is True


def test_a_close_that_never_returns_does_not_own_the_thread(monkeypatch):
    """`CancelIoEx` on a surprise-removed CH340 can block inside the driver,
    and this is the path a session shutdown joins. Leaking a handle on a
    device that has already gone is cheaper than freezing the app."""
    monkeypatch.setattr(wind, "CLOSE_TIMEOUT_S", 0.05)
    started = threading.Event()

    class Hangs(FakeSerial):
        def close(self) -> None:
            started.set()
            time.sleep(30.0)

    fake = Hangs(speaks=arq.DEFAULT_CRC)
    link = link_onto(fake)
    began = time.monotonic()
    link.close(graceful=False)
    took = time.monotonic() - began
    assert started.wait(1.0), "the close never even started"
    assert took < 2.0, f"a hung close held the caller for {took:.1f}s"


# ------------------------------------------------------ counting the drops

def test_a_drop_is_counted_even_when_it_heals_between_reports():
    """The health line runs every ten seconds and a drop heals in seven to
    twelve, so an outage the driver felt could leave no trace at all. Ten days
    of logs hold one drop; he reports them repeatedly. A monotonic count
    cannot be missed by a sampling interval."""
    sim = wind.WindSim()
    sim._link = link_onto(FakeSerial(speaks=arq.DEFAULT_CRC))
    sim.state.connected = True

    sim._drop_link(graceful=False)
    assert sim.state.disconnects == 1
    assert sim.state.last_drop_at is not None
    assert sim.state.connected is False

    # Dropping an already-dropped link is not a second outage.
    sim._drop_link()
    assert sim.state.disconnects == 1


# ------------------------------------------ the link outlives the session

def test_a_session_boundary_parks_the_fans_and_keeps_the_link():
    """**Three self-inflicted dropouts a night, recorded as clean
    shutdowns.**

    `stop_practice` tore the `WindSim` down and `start_race` built a new one,
    so every practice -> qualifying -> race paid a full reconnect: close the
    port, reopen it, wait out the 1.6 s bootloader settle, probe the CRC.
    From the seat that is several seconds of dead fans, indistinguishable
    from the hardware dropping - and the log wrote it down as an orderly
    release, so it never looked like a fault. There are 78 of those lines in
    ten days and exactly one real drop.

    The device is not per-session. Only closing the app really lets it go.
    """
    from pitcrew.controller import PitCrewController

    class Sim:
        def __init__(self):
            self.parked = 0
            self.shut = 0

        def stop_fans(self):
            self.parked += 1

        def shutdown(self):
            self.shut += 1

    class Curve:
        level = 0.0
        observed_top_kph = None

        def reset(self):
            pass

    class Bridge:
        def __init__(self):
            self.wind = None
            self.wind_curve = Curve()

    class Settings:
        wind_enabled = True

    class Rack:
        start_wind = PitCrewController.start_wind
        stop_wind = PitCrewController.stop_wind
        shutdown_wind = PitCrewController.shutdown_wind
        active_event = staticmethod(lambda: None)

        def __init__(self):
            self.bridge = Bridge()
            self.settings = Settings()

    rack = Rack()
    rack.bridge.wind = sim = Sim()

    rack.stop_wind()
    assert sim.parked == 1, "the fans were not zeroed at the boundary"
    assert sim.shut == 0, "the link was torn down between sessions"
    assert rack.bridge.wind is sim, "the next session would reconnect"

    # And the next session reuses it rather than building a second one.
    assert rack.start_wind() is True
    assert rack.bridge.wind is sim

    # Closing the app is the one place it really goes.
    rack.shutdown_wind()
    assert sim.shut == 1
    assert rack.bridge.wind is None


def test_switching_the_wind_off_stops_a_link_that_is_already_up():
    """The one non-boundary case that must still tear down: a running link
    when the driver unticks the box."""
    from pitcrew.controller import PitCrewController

    class Sim:
        def __init__(self):
            self.shut = 0

        def stop_fans(self):
            pass

        def shutdown(self):
            self.shut += 1

    class Bridge:
        def __init__(self):
            self.wind = Sim()
            self.wind_curve = None

    class Settings:
        wind_enabled = False

    class Rack:
        start_wind = PitCrewController.start_wind
        shutdown_wind = PitCrewController.shutdown_wind

        def __init__(self):
            self.bridge = Bridge()
            self.settings = Settings()

    rack = Rack()
    sim = rack.bridge.wind
    assert rack.start_wind() is False
    assert sim.shut == 1, "wind was switched off and the fans kept their link"
    assert rack.bridge.wind is None


# --------------------------------------- the value that was held for ever

def test_a_held_value_is_faded_out_rather_than_blown_indefinitely(monkeypatch):
    """Holding the last speed through a telemetry gap is right - the send
    loop is a fixed 250 ms timer, decoupled from the 60 Hz feed, so a hiccup
    must not cut the fans. Holding it for ever is not: if the console sleeps
    or the packet thread dies, two 4000 RPM blowers keep describing a corner
    the driver left ten minutes ago."""
    monkeypatch.setattr(wind, "HOLD_S", 1.0)
    monkeypatch.setattr(wind, "DECAY_S", 1.0)

    clock = {"t": 100.0}
    monkeypatch.setattr(wind.time, "monotonic", lambda: clock["t"])

    sim = wind.WindSim()
    sim.set_output((200, 200, 0, 0))

    with sim._lock:
        assert sim._decayed_locked() == (200, 200, 0, 0), "faded immediately"

    clock["t"] += 0.9                                   # inside the hold
    with sim._lock:
        assert sim._decayed_locked() == (200, 200, 0, 0), "a 0.9s gap faded"

    clock["t"] += 0.6                                   # half way down
    with sim._lock:
        half = sim._decayed_locked()
    assert 0 < half[0] < 200, f"not fading: {half}"

    clock["t"] += 1.0                                   # past the decay
    with sim._lock:
        assert sim._decayed_locked() == (0, 0, 0, 0), "never reached zero"

    # And a fresh value restarts the clock rather than staying faded.
    sim.set_output((180, 180, 0, 0))
    with sim._lock:
        assert sim._decayed_locked() == (180, 180, 0, 0)
