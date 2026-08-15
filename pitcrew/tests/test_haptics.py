"""The transducer's stream, driven without a sound card.

The callback is exercised directly, which is the only honest way to test a
watchdog that has to work when everything around it has stopped: a test that
waits for real time to pass proves the test can sleep, not that the fade
happens.

The one being tested hardest is the stuck tone. If telemetry stops and the
callback keeps rendering the last thing it was told, the driver gets a
continuous 150 W tone through the seat until he pulls a plug.
"""
from __future__ import annotations

import numpy as np

from pitcrew.engineer import audio_devices
from pitcrew.rig import haptics, transducer


def _engine() -> haptics.HapticsEngine:
    return haptics.HapticsEngine()


def _pump(engine, blocks: int, frames: int = 512) -> np.ndarray:
    """Run the callback `blocks` times with NOTHING arriving. Time passes."""
    out = np.zeros((frames, transducer.CHANNELS), dtype=np.float32)
    for _ in range(blocks):
        engine._callback(out, frames, None, None)
    return out.copy()


def _pump_live(engine, blocks: int, level: float = 0.8,
               frames: int = 512) -> np.ndarray:
    """The same, with telemetry still arriving each block.

    Needed because `_pump` alone lets the watchdog fire: 40 blocks of 512 is
    0.43 s, against a 0.2 s staleness threshold. A warm-up that does not feed
    the engine is measuring an engine that has already faded out - which is
    how the first version of `test_it_fades_rather_than_cutting` came to
    assert against a row of zeros.
    """
    out = np.zeros((frames, transducer.CHANNELS), dtype=np.float32)
    values = [level] * len(engine._specs)
    for _ in range(blocks):
        engine.set_intensities(values)
        engine._callback(out, frames, None, None)
    return out.copy()


def _peak(block: np.ndarray) -> float:
    return float(np.max(np.abs(block)))


# ------------------------------------------------------------- the watchdog

def test_a_stopped_feed_fades_to_silence_rather_than_holding_a_tone():
    """The failure this whole class exists to prevent.

    PortAudio's thread is not Python's, so a telemetry side that dies leaves
    the callback running and rendering the last intensities it was given -
    forever, at 150 W, into a piston beside the driver.
    """
    engine = _engine()
    assert _peak(_pump_live(engine, 30)) > 0.01, "it never made a sound at all"

    # Telemetry stops. Nothing else changes - the card keeps asking.
    quiet = _pump(engine, 200)
    assert _peak(quiet) < 1e-4, "the tone was still going after the feed died"
    assert engine.faded_out >= 1


def test_the_watchdog_counts_frames_and_not_wall_clock():
    """It has to work when the Python side is what died, and then a timer
    never fires either. The sound card asking for another block is the only
    clock still ticking."""
    engine = _engine()
    _pump_live(engine, 30)

    # No sleeping anywhere: time passes only because blocks were consumed.
    frames_for_stale = int(
        transducer.SAMPLE_RATE * (haptics.STALE_S + haptics.FADE_S)) + 4096
    _pump(engine, blocks=frames_for_stale // 512 + 4)
    assert engine._fade == 0.0


def test_it_fades_rather_than_cutting():
    """An instant mute is itself a discontinuity, and a discontinuity here is
    a thump."""
    engine = _engine()
    _pump_live(engine, 40)

    peaks = []
    out = np.zeros((512, transducer.CHANNELS), dtype=np.float32)
    for _ in range(60):
        engine._callback(out, 512, None, None)
        peaks.append(_peak(out))

    # Counting consecutive decreases is the wrong measure - the signal itself
    # is noisy, so a peak can rise between two blocks of a falling envelope.
    # What matters is that it passed THROUGH the middle rather than jumping
    # the gap, so look for blocks at partial level.
    loudest = max(peaks)
    partial = [p for p in peaks if 0.1 * loudest < p < 0.8 * loudest]
    assert len(partial) >= 3, (
        f"it went from full to nothing without passing through - peaks "
        f"{[round(p, 4) for p in peaks[::6]]}")


def test_the_feed_coming_back_fades_in_again():
    engine = _engine()
    _pump_live(engine, 30)
    _pump(engine, 200)
    assert engine._fade == 0.0

    for _ in range(60):
        engine.set_intensities([0.8] * len(engine._specs))
        _pump(engine, 1)
    assert engine._fade > 0.5, "the feed returned and nothing came back on"


def test_a_feed_that_keeps_arriving_never_fades():
    engine = _engine()
    out = np.zeros((512, transducer.CHANNELS), dtype=np.float32)
    for _ in range(300):
        engine.set_intensities([0.5] * len(engine._specs))
        engine._callback(out, 512, None, None)
    assert engine._fade == 1.0
    assert engine.faded_out == 0


def test_repeating_the_same_values_still_counts_as_alive():
    """A driver holding a steady speed sends the same intensities every frame.
    Treating "unchanged" as "stopped" would fade out on the straights."""
    engine = _engine()
    steady = [0.4] * len(engine._specs)
    out = np.zeros((512, transducer.CHANNELS), dtype=np.float32)
    for _ in range(300):
        engine.set_intensities(steady)
        engine._callback(out, 512, None, None)
    assert engine._fade == 1.0


# ---------------------------------------------------------------- the mix

def test_both_channels_carry_the_same_signal():
    engine = _engine()
    block = _pump_live(engine, 40, level=0.7)
    assert np.allclose(block[:, 0], block[:, 1])


def test_nothing_leaves_that_would_trip_the_amps_protection():
    engine = _engine()
    out = np.zeros((512, transducer.CHANNELS), dtype=np.float32)
    for _ in range(120):
        engine.set_intensities([1.0] * len(engine._specs))
        engine._callback(out, 512, None, None)
        assert _peak(out) <= transducer.HARD_LIMIT + 1e-6


def test_silence_in_is_silence_out():
    engine = _engine()
    out = np.zeros((512, transducer.CHANNELS), dtype=np.float32)
    for _ in range(60):
        engine.set_intensities([0.0] * len(engine._specs))
        engine._callback(out, 512, None, None)
    assert _peak(out) < 1e-3


def test_a_block_bigger_than_the_buffer_is_filled_not_overrun():
    """PortAudio chooses the block size and may hand back more than expected.
    Writing part of it and leaving the rest as whatever was in the buffer
    would be a repeating fragment - a buzz."""
    engine = _engine()
    engine.set_intensities([0.5] * len(engine._specs))
    frames = haptics.MAX_BLOCK + 512
    out = np.full((frames, transducer.CHANNELS), 9.0, dtype=np.float32)
    engine._callback(out, frames, None, None)
    assert _peak(out) <= transducer.HARD_LIMIT + 1e-6
    assert np.all(out[haptics.MAX_BLOCK:] == 0.0)


# ---------------------------------------------- surviving a device rebuild

def test_it_registers_so_a_device_rebuild_cannot_kill_it_silently():
    """`sd._terminate()` closes every open stream in the process with nothing
    raised. This stream is meant to live for a whole race."""
    engine = _engine()
    calls = []
    engine._open = lambda: calls.append("open") or True     # type: ignore
    engine._close = lambda: calls.append("close")           # type: ignore
    engine._stream = object()

    audio_devices.register_sustained(engine)
    try:
        engine.suspend()
        assert engine._suspended is True
        engine.resume()
        assert engine._suspended is False
        assert calls == ["close", "open"]
    finally:
        audio_devices.unregister_sustained(engine)


def test_a_stream_that_will_not_reopen_leaves_the_engine_stopped_not_lying():
    engine = _engine()
    engine._stream = object()
    # The real `_close` on purpose - it is what clears `_stream`, and stubbing
    # it out would have this test asserting against a state the running app
    # can never be in.
    engine._open = lambda: False                            # type: ignore
    audio_devices.register_sustained(engine)
    try:
        engine.suspend()
        engine.resume()
        assert engine.running is False
    finally:
        audio_devices.unregister_sustained(engine)


def test_a_device_that_will_not_open_is_reported_not_raised():
    """An output must never be able to stop the app recording a session."""
    engine = haptics.HapticsEngine(device="No Such Card")
    assert engine.start() is False
    assert engine.error is not None
    assert engine.running is False


# ------------------------------------------------ wired into the packet path

def _bridge():
    from pitcrew.controller import TelemetryBridge
    return TelemetryBridge()


def _encoded(**overrides) -> bytes:
    """A real encrypted packet, so the bridge does its real parse."""
    from .conftest import make_packet
    from .test_direct_feed import a_car_on_track, encrypted
    del make_packet, overrides
    return encrypted(a_car_on_track())


def test_the_transducer_is_off_until_it_is_switched_on():
    """It drives 150 W into a piston under the seat. An output that starts
    making itself felt because the app was updated is not a pleasant
    surprise."""
    from pitcrew.settings import Settings

    assert Settings().haptics_enabled is False


def test_a_packet_reaches_the_transducer():
    bridge = _bridge()
    seen = []

    class Sink:
        def set_intensities(self, values):
            seen.append(np.asarray(values).copy())

    bridge.haptics = Sink()
    assert bridge.on_packet(_encoded()) is True
    assert len(seen) == 1
    assert len(seen[0]) == len(bridge.effects.NAMES)


def test_a_transducer_that_raises_cannot_cost_him_the_session():
    """CLAUDE.md: the app observes and advises. An output must never be able
    to stop a lap being recorded - so it is dropped for the session and the
    packet still counts as decoded."""
    bridge = _bridge()

    class Broken:
        def set_intensities(self, values):
            raise RuntimeError("the card went away mid-corner")

    bridge.haptics = Broken()
    assert bridge.on_packet(_encoded()) is True
    assert bridge.haptics is None, "a broken output stayed wired in"
    # And the recorder still got the frame.
    assert bridge.recorder.frame_count >= 1


def test_an_undecodable_packet_never_reaches_the_transducer():
    """`on_packet` returns early on a parse failure, so this consumer is
    skipped - which is correct, and is why it has to tolerate being skipped."""
    bridge = _bridge()
    seen = []

    class Sink:
        def set_intensities(self, values):
            seen.append(1)

    bridge.haptics = Sink()
    assert bridge.on_packet(b"not telemetry") is False
    assert seen == []


def test_the_transducer_runs_after_everything_that_carries_state():
    """Lap distance is INTEGRATED from the packet clock, and corner windows
    are keyed on it. A consumer that ran before the recorder - or that threw
    where the recorder could see it - would move every corner at the
    circuit."""
    bridge = _bridge()
    order = []

    real_record = bridge.recorder.record_frame
    bridge.recorder.record_frame = lambda p: (order.append("recorder"),
                                              real_record(p))[1]

    class Sink:
        def set_intensities(self, values):
            order.append("haptics")

    bridge.haptics = Sink()
    bridge.on_packet(_encoded())
    assert order == ["recorder", "haptics"]


def test_a_session_boundary_clears_the_state_behind_the_effects():
    """Velocity carried across a garage visit is a collision that never
    happened, at full scale, the instant he rejoins."""
    bridge = _bridge()

    class Sink:
        def set_intensities(self, values):
            pass

    # A sink is needed: the deriver only runs when something is listening,
    # which is deliberate - there is no point computing six intensities that
    # nobody consumes on every packet of every session.
    bridge.haptics = Sink()
    bridge.on_packet(_encoded())
    assert bridge.effects._prev_velocity is not None
    bridge.reset()
    assert bridge.effects._prev_velocity is None


# ------------------------------------------- noticing a card that plays none

def test_the_mix_reports_what_it_actually_rendered():
    """Half of the only question worth asking about a transducer. The other
    half is the endpoint's own meter, and the two together are what separate
    a quiet lap from a dead device."""
    engine = _engine()
    assert engine.take_recent_peak() == 0.0
    _pump_live(engine, 40)
    peak = engine.take_recent_peak()
    assert peak > 0.01, "it rendered nothing to report"
    assert engine.take_recent_peak() == 0.0, "the peak was not reset"


def test_a_silent_lap_is_not_mistaken_for_a_dead_transducer():
    """A driver crawling out of the pits produces almost nothing. Asking the
    card whether it played that would prove nothing either way, so the check
    only fires when we know we were loud."""
    from pitcrew.controller import PitCrewController

    engine = _engine()
    for _ in range(40):
        engine.set_intensities([0.0] * len(engine._specs))
        _pump(engine, 1)
    assert engine.take_recent_peak() < PitCrewController._AUDIBLE_PEAK
