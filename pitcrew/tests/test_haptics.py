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
    values = [level] * len(engine._wanted)
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
        engine.set_intensities([0.8] * len(engine._wanted))
        _pump(engine, 1)
    assert engine._fade > 0.5, "the feed returned and nothing came back on"


def test_a_feed_that_keeps_arriving_never_fades():
    engine = _engine()
    out = np.zeros((512, transducer.CHANNELS), dtype=np.float32)
    for _ in range(300):
        engine.set_intensities([0.5] * len(engine._wanted))
        engine._callback(out, 512, None, None)
    assert engine._fade == 1.0
    assert engine.faded_out == 0


def test_repeating_the_same_values_still_counts_as_alive():
    """A driver holding a steady speed sends the same intensities every frame.
    Treating "unchanged" as "stopped" would fade out on the straights."""
    engine = _engine()
    steady = [0.4] * len(engine._wanted)
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
        engine.set_intensities([1.0] * len(engine._wanted))
        engine._callback(out, 512, None, None)
        assert _peak(out) <= transducer.HARD_LIMIT + 1e-6


def test_silence_in_is_silence_out():
    engine = _engine()
    out = np.zeros((512, transducer.CHANNELS), dtype=np.float32)
    for _ in range(60):
        engine.set_intensities([0.0] * len(engine._wanted))
        engine._callback(out, 512, None, None)
    assert _peak(out) < 1e-3


def test_a_block_bigger_than_the_buffer_is_filled_not_overrun():
    """PortAudio chooses the block size and may hand back more than expected.
    Writing part of it and leaving the rest as whatever was in the buffer
    would be a repeating fragment - a buzz."""
    engine = _engine()
    engine.set_intensities([0.5] * len(engine._wanted))
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
    assert len(seen[0]) == (len(bridge.effects.NAMES)
                            + len(bridge.effects.MODIFIERS))


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
        engine.set_intensities([0.0] * len(engine._wanted))
        _pump(engine, 1)
    assert engine.take_recent_peak() < PitCrewController._AUDIBLE_PEAK


# ------------------------------------------------- recovering without dying

class _FakeStream:
    def stop(self):
        pass

    def close(self):
        pass


def test_a_recovery_that_rebuilds_the_device_list_does_not_deadlock(monkeypatch):
    """Session 40 froze the whole app on this. `recover` held the engine's
    lock while `open_output` decided the device list was stale and called
    straight back into `suspend` on the same engine, on the same thread - a
    self-deadlock with a plain Lock, and the driver's stop-practice click
    then queued behind it forever."""
    import threading

    engine = _engine()
    engine._stream = _FakeStream()

    def open_output(*args, **kwargs):
        # What `audio_devices._reinitialise` does to every sustained stream
        # before tearing PortAudio down, on the caller's own thread.
        engine.suspend()
        engine.resume()
        return _FakeStream()

    monkeypatch.setattr(haptics.audio_devices, "open_output", open_output)
    monkeypatch.setattr(haptics.audio_devices, "register_sustained",
                        lambda e: None)
    monkeypatch.setattr(haptics.audio_devices, "unregister_sustained",
                        lambda e: None)

    result = []
    worker = threading.Thread(target=lambda: result.append(engine.recover()),
                              daemon=True)
    worker.start()
    worker.join(timeout=5.0)
    assert result, "recover deadlocked against its own suspend"
    assert result[0] is True
    assert engine.recoveries == 1
    assert engine.running


def test_a_recovery_cannot_resurrect_a_stopped_transducer(monkeypatch):
    """`stop` used to unregister first and lock second, so a recovery that
    won the lock race could reopen and re-register a stream the driver had
    stopped - and the next device rebuild would then resurrect it."""
    engine = _engine()
    engine._stream = _FakeStream()
    monkeypatch.setattr(haptics.audio_devices, "unregister_sustained",
                        lambda e: None)
    engine.stop()
    assert engine.recover() is False
    assert not engine.running
    assert engine.recoveries == 0


# --------------------------------------- the full rebuild, one rung further

def _patch_rebuild_plumbing(monkeypatch, engine, open_output):
    monkeypatch.setattr(haptics, "REBUILD_SETTLE_S", 0.0)
    monkeypatch.setattr(haptics.audio_devices, "open_output", open_output)
    monkeypatch.setattr(haptics.audio_devices, "register_sustained",
                        lambda e: None)
    monkeypatch.setattr(haptics.audio_devices, "unregister_sustained",
                        lambda e: None)


def test_a_rebuild_that_reenumerates_does_not_deadlock(monkeypatch):
    """Same trap as `recover`, one rung up: `open_output` may decide the
    device list is stale and call straight back into `suspend` on this same
    engine, on this same thread. The RLock has to hold for the rebuild too."""
    import threading

    engine = _engine()
    engine._stream = _FakeStream()

    def open_output(*args, **kwargs):
        engine.suspend()
        engine.resume()
        return _FakeStream()

    _patch_rebuild_plumbing(monkeypatch, engine, open_output)

    result = []
    worker = threading.Thread(target=lambda: result.append(engine.rebuild()),
                              daemon=True)
    worker.start()
    worker.join(timeout=5.0)
    assert result, "rebuild deadlocked against its own suspend"
    assert result[0] is True
    assert engine.rebuilds == 1
    assert engine.running


def test_a_rebuild_retries_even_when_the_last_attempt_opened_nothing(
        monkeypatch):
    """`recover` demands a live stream to reopen; a rebuild must not, because
    the attempt before it may have failed to open anything at all - which is
    exactly the state a retry exists for."""
    engine = _engine()
    assert engine._stream is None
    _patch_rebuild_plumbing(monkeypatch, engine,
                            lambda *a, **k: _FakeStream())
    assert engine.rebuild() is True
    assert engine.running


def test_a_stop_during_the_rebuild_settle_wins(monkeypatch):
    """The driver clicking stop while the rebuild is standing back must end
    the session, not race it: the second lock take re-checks `_stopped`, so
    the rebuild opens nothing and stays down."""
    engine = _engine()
    engine._stream = _FakeStream()
    opened = []
    monkeypatch.setattr(haptics.audio_devices, "open_output",
                        lambda *a, **k: opened.append(1) or _FakeStream())
    monkeypatch.setattr(haptics.audio_devices, "unregister_sustained",
                        lambda e: None)
    monkeypatch.setattr(haptics.time, "sleep", lambda s: engine.stop())

    # None, not False: the driver stopping it is an abort, not a failure,
    # and the watchdog must not spend a capped attempt on it.
    assert engine.rebuild() is None
    assert opened == [], "a stopped engine was reopened anyway"
    assert not engine.running
    assert engine.rebuilds == 0


def test_a_recovery_racing_the_settings_picker_cannot_deadlock(monkeypatch):
    """The AB-BA: the picker takes the enumeration lock and then calls
    `suspend` - the engine's lock - on every sustained stream, while a
    recovery that took the engine's lock first arrives at the enumeration
    lock from inside `_open`. Opposite order, both blocking, permanent - and
    the likeliest collision is exactly this feature's scenario: haptics die,
    the driver opens Settings while the watchdog reopens. `recover` now
    takes the enumeration lock strictly first."""
    import threading
    import time as _time

    engine = _engine()
    engine._stream = _FakeStream()

    def open_output(*args, **kwargs):
        # The real one serialises on the enumeration lock too.
        with haptics.audio_devices.enumeration_lock():
            return _FakeStream()

    monkeypatch.setattr(haptics.audio_devices, "open_output", open_output)
    monkeypatch.setattr(haptics.audio_devices, "register_sustained",
                        lambda e: None)
    monkeypatch.setattr(haptics.audio_devices, "unregister_sustained",
                        lambda e: None)

    taken = threading.Event()
    go = threading.Event()

    def settings_picker() -> None:
        # What `devices` does: enumeration lock first, then every sustained
        # holder's suspend/resume.
        with haptics.audio_devices.enumeration_lock():
            taken.set()
            go.wait(timeout=5.0)
            engine.suspend()
            engine.resume()

    picker = threading.Thread(target=settings_picker, daemon=True)
    picker.start()
    assert taken.wait(timeout=5.0)

    result = []
    recovering = threading.Thread(
        target=lambda: result.append(engine.recover()), daemon=True)
    recovering.start()
    _time.sleep(0.2)         # let the recovery reach its first lock acquire
    go.set()
    picker.join(timeout=5.0)
    recovering.join(timeout=5.0)
    assert not picker.is_alive(), "the picker deadlocked against recover"
    assert result, "recover deadlocked against the picker"
    assert result[0] is True
    assert engine.running


def test_a_recovery_waits_for_the_engineer_and_neither_thread_hangs(
        monkeypatch):
    """The third leg of the same lock trap, added by the deferral.

    The settings screen is the caller that made a rebuild wait for the voice
    worth doing, but the recovery path is the one that can deadlock over it,
    so it is the one tested here. `recover` takes the enumeration lock, `_open`
    reaches `_reinitialise`, and `_reinitialise` now waits there for the voice
    to finish its line. The voice holds no enumeration lock while it plays - it
    takes it across the open and the declaration together and drops it before
    the first write - so the wait clears. Holding it through the write, or
    declaring before the open, would be the same two locks in opposite orders
    on two threads, and the whole app would stop.
    """
    import threading
    import time as _time

    engine = _engine()
    engine._stream = _FakeStream()

    def open_output(*args, **kwargs):
        with haptics.audio_devices.enumeration_lock():
            haptics.audio_devices._reinitialise(_FakeSoundDevice())
            return _FakeStream()

    monkeypatch.setattr(haptics.audio_devices, "open_output", open_output)
    monkeypatch.setattr(haptics.audio_devices, "register_sustained",
                        lambda e: None)
    monkeypatch.setattr(haptics.audio_devices, "unregister_sustained",
                        lambda e: None)

    speaking = _speak_for(0.4)
    try:
        result = []
        worker = threading.Thread(
            target=lambda: result.append(engine.recover()), daemon=True)
        started = _time.monotonic()
        worker.start()
        worker.join(timeout=10.0)
        assert not worker.is_alive(), "the recovery deadlocked on the voice"
        assert result == [True]
        assert speaking["line"].interrupted is False, "the line was cut anyway"
        assert _time.monotonic() - started >= 0.3, "it did not wait at all"
    finally:
        speaking["release"].set()
        speaking["thread"].join(timeout=5.0)


def test_the_wait_cannot_hold_a_recovery_down_for_the_race(monkeypatch):
    """The other half of the deadlock discipline: a deferral must have a
    timeout, not a condition that can never be signalled. A voice thread stuck
    forever must cost the transducer seconds, not the session."""
    import time as _time

    engine = _engine()
    engine._stream = _FakeStream()

    monkeypatch.setattr(haptics.audio_devices, "DEFER_CAP_S", 0.2)

    def open_output(*args, **kwargs):
        with haptics.audio_devices.enumeration_lock():
            haptics.audio_devices._reinitialise(_FakeSoundDevice())
            return _FakeStream()

    monkeypatch.setattr(haptics.audio_devices, "open_output", open_output)
    monkeypatch.setattr(haptics.audio_devices, "register_sustained",
                        lambda e: None)
    monkeypatch.setattr(haptics.audio_devices, "unregister_sustained",
                        lambda e: None)

    speaking = _speak_for(30.0)          # a line that never ends
    try:
        started = _time.monotonic()
        assert engine.recover() is True
        assert _time.monotonic() - started < 3.0, "the recovery was starved"
        assert speaking["line"].interrupted is True
    finally:
        speaking["release"].set()
        speaking["thread"].join(timeout=5.0)


def test_a_rebuild_also_waits_and_also_comes_back(monkeypatch):
    """`rebuild` is the escalation past `recover` and takes the same two locks
    in the same order, but by a different route - it drops the engine lock,
    unregisters, sleeps out the settle, and only then takes the enumeration
    lock. Covered separately because "the same discipline" is an assertion
    about code that was written twice."""
    import time as _time

    engine = _engine()
    engine._stream = _FakeStream()

    monkeypatch.setattr(haptics, "REBUILD_SETTLE_S", 0.01)

    def open_output(*args, **kwargs):
        with haptics.audio_devices.enumeration_lock():
            haptics.audio_devices._reinitialise(_FakeSoundDevice())
            return _FakeStream()

    monkeypatch.setattr(haptics.audio_devices, "open_output", open_output)
    monkeypatch.setattr(haptics.audio_devices, "register_sustained",
                        lambda e: None)
    monkeypatch.setattr(haptics.audio_devices, "unregister_sustained",
                        lambda e: None)

    speaking = _speak_for(0.4)
    try:
        started = _time.monotonic()
        assert engine.rebuild() is True
        assert _time.monotonic() - started >= 0.3, "it did not wait at all"
        assert speaking["line"].interrupted is False, "the line was cut anyway"
        assert engine.running
    finally:
        speaking["release"].set()
        speaking["thread"].join(timeout=5.0)


def test_stop_during_a_deferred_recovery_still_wins(monkeypatch):
    """The driver's stop must not queue behind a sentence. `stop` takes only
    the engine's lock, and the deferral holds the enumeration lock - so a
    recovery waiting on the voice cannot make the app unstoppable."""
    import threading

    engine = _engine()
    engine._stream = _FakeStream()

    def open_output(*args, **kwargs):
        with haptics.audio_devices.enumeration_lock():
            haptics.audio_devices._reinitialise(_FakeSoundDevice())
            return _FakeStream()

    monkeypatch.setattr(haptics.audio_devices, "open_output", open_output)
    monkeypatch.setattr(haptics.audio_devices, "register_sustained",
                        lambda e: None)
    monkeypatch.setattr(haptics.audio_devices, "unregister_sustained",
                        lambda e: None)

    speaking = _speak_for(0.5)
    try:
        recovering = threading.Thread(target=engine.recover, daemon=True)
        recovering.start()
        stopper = threading.Thread(target=engine.stop, daemon=True)
        stopper.start()
        stopper.join(timeout=5.0)
        assert not stopper.is_alive(), "stop queued behind the spoken line"
        recovering.join(timeout=10.0)
        assert not recovering.is_alive()
    finally:
        speaking["release"].set()
        speaking["thread"].join(timeout=5.0)


class _FakeSoundDevice:
    """Enough of `sounddevice` for `_reinitialise` to run against nothing."""

    def _terminate(self):
        pass

    def _initialize(self):
        pass


def _speak_for(seconds: float) -> dict:
    """A line playing on a thread of its own, as the voice really plays one.

    On its own thread on purpose: `_wait_for_playback` never waits on the
    calling thread, so a playback declared here would not exercise the wait.
    """
    import threading

    state: dict = {"release": threading.Event()}
    opened = threading.Event()

    def run() -> None:
        state["line"] = audio_devices.begin_playback("the engineer's line")
        opened.set()
        state["release"].wait(timeout=seconds)
        audio_devices.end_playback(state["line"])

    state["thread"] = threading.Thread(target=run, daemon=True)
    state["thread"].start()
    assert opened.wait(timeout=5.0)
    return state


# ------------------------------------ the watchdog that convicts the meter

def _frozen_polls(wd, count, heard=0.054, start=0.0, step=10.0):
    """Loud polls with a varying rendered peak and a meter stuck on one
    number - the race of 16 Aug 2026, distilled."""
    rendered = (0.30, 0.55, 0.42, 0.51, 0.38, 0.47)
    verdicts = []
    for i in range(count):
        verdicts.append(wd.judge(rendered[i % len(rendered)], heard,
                                 start + step * i))
    return verdicts


def test_a_meter_frozen_on_a_live_signal_is_convicted_inside_a_minute():
    wd = haptics.TransducerWatchdog()
    verdicts = _frozen_polls(wd, 10)
    assert "stale" in verdicts, "twenty minutes of 0.054 read as healthy"
    declared_at = verdicts.index("stale") * 10.0
    assert 30.0 <= declared_at <= 60.0, (
        f"declared after {declared_at:.0f}s - wanted the order of 30-60s")
    # And every poll before the threshold withheld judgement - a repeating
    # value is never "live", however early in the run.
    assert set(verdicts[:verdicts.index("stale")]) == {"unsettled"}


def test_a_jittering_meter_is_never_convicted():
    wd = haptics.TransducerWatchdog()
    verdicts = [wd.judge(0.45, 0.080 + 0.001 * (i % 7), i * 10.0)
                for i in range(200)]
    assert "stale" not in verdicts
    # And once enough distinct readings are in, it is confirmed alive.
    assert verdicts[-1] == "live"


def test_a_steady_rendered_level_cannot_convict_the_meter():
    """An identical reading only means anything if what WE rendered varied.
    A dead-steady state gives a working meter every reason to repeat
    itself, so however long it repeats, it is not evidence."""
    wd = haptics.TransducerWatchdog()
    for i in range(200):
        assert wd.judge(0.40, 0.054, i * 10.0) != "stale"


def test_a_quiet_spell_pauses_the_run_rather_than_resetting_it():
    """Staleness is judged only on polls actually taken while loud - the
    controller never asks the meter for a parked car. The frozen run resumes
    after the spell, because the meter is still frozen either way."""
    wd = haptics.TransducerWatchdog()
    assert "stale" not in _frozen_polls(wd, 3, start=0.0)
    # Ten minutes in the pit lane: no polls at all.
    verdicts = _frozen_polls(wd, 2, start=600.0)
    assert verdicts[-1] == "stale"


def test_a_silent_reading_ends_the_frozen_run():
    """Silence is the OTHER wedge and has its own handling; a run that
    straddles it would be counting two different failures as one."""
    wd = haptics.TransducerWatchdog()
    _frozen_polls(wd, 4)
    wd.silent(40.0)
    assert "stale" not in _frozen_polls(wd, 4, start=50.0)


def test_one_changed_reading_is_not_a_recovery():
    """A wedge that survives the endpoint's pump rebuild comes back frozen
    at a NEW float. The first reading of it must be "unsettled", never
    "live" - "live" fires `settled`, and `settled` is what claims a rebuild
    worked and resets the ladder."""
    wd = haptics.TransducerWatchdog()
    _frozen_polls(wd, 6)                        # convicted at 0.054
    wd.reopened(50.0)
    wd.rebuilt(True, 60.0)
    # The endpoint re-froze at a different number.
    assert wd.judge(0.42, 0.061, 70.0) == "unsettled"
    # The ladder did not reset off that single reading...
    assert wd.plan_recovery(80.0) != "reopen"
    # ...and the new value convicts in its own right.
    verdicts = _frozen_polls(wd, 6, heard=0.061, start=80.0)
    assert "stale" in verdicts
    assert "live" not in verdicts


def test_a_ping_ponging_meter_is_still_convicted():
    """A meter alternating between two frozen values is as dead as one stuck
    on a single value. Judging only against the previous reading would reset
    the count on every flip and never convict."""
    wd = haptics.TransducerWatchdog()
    rendered = (0.30, 0.55, 0.42, 0.51)
    verdicts = [wd.judge(rendered[i % len(rendered)],
                         0.054 if i % 2 == 0 else 0.061, i * 10.0)
                for i in range(20)]
    assert "stale" in verdicts, "the A,B,A,B ping-pong was never convicted"
    assert "live" not in verdicts, "a two-value ping-pong read as alive"


# ------------------------------------------------- the cadence as a witness

def test_a_sustained_cadence_drop_is_named_once_and_corroborates(caplog):
    """100/s falling to 64/s and staying there is the endpoint's audio pump
    being rebuilt - a device-side event worth one warning, and worth holding
    as corroboration for the meter's verdict."""
    import logging

    wd = haptics.TransducerWatchdog()
    state = {"t": 0.0, "blocks": 0}

    def cycle(rate):
        state["blocks"] += int(rate * 10)
        state["t"] += 10.0
        wd.note_cadence(state["blocks"], state["t"])

    with caplog.at_level(logging.WARNING, logger="pitcrew.haptics"):
        for _ in range(4):                      # baseline at ~100 blocks/s
            cycle(100)
        assert not wd.corroborated(state["t"])
        cycle(64)                               # one low cycle is jitter
        assert not wd.corroborated(state["t"])
        cycle(64)                               # two is a drop
        assert wd.corroborated(state["t"])
        cycle(64)
        cycle(64)

    warnings = [r for r in caplog.records if "pump" in r.getMessage()]
    assert len(warnings) == 1, "the drop was warned more than once"
    # Corroboration ages out rather than tainting the whole session.
    assert not wd.corroborated(state["t"] + 500.0)


def test_corroboration_shortens_the_meter_verdict_by_one_poll():
    wd = haptics.TransducerWatchdog()
    state = {"blocks": 0}
    for i in range(6):
        state["blocks"] += 1000 if i < 4 else 640
        wd.note_cadence(state["blocks"], 10.0 * (i + 1))
    assert wd.corroborated(60.0)
    verdicts = _frozen_polls(wd, wd.STALE_POLLS_CORROBORATED, start=70.0)
    assert verdicts[-1] == "stale"


def test_a_counter_that_went_backwards_is_not_a_cadence_drop(caplog):
    """A replaced engine restarts its block counter; that is bookkeeping,
    not a device event."""
    import logging

    wd = haptics.TransducerWatchdog()
    for i in range(4):
        wd.note_cadence(1000 * (i + 1), 10.0 * (i + 1))
    with caplog.at_level(logging.WARNING, logger="pitcrew.haptics"):
        wd.note_cadence(100, 50.0)
        wd.note_cadence(1100, 60.0)
    assert not any("pump" in r.getMessage() for r in caplog.records)


# --------------------------------------------------- the ladder of recovery

def test_the_first_wedge_gets_a_reopen_and_a_flap_gets_the_rebuild():
    wd = haptics.TransducerWatchdog()
    assert wd.plan_recovery(0.0) == "reopen"
    wd.reopened(0.0)
    # Evidence back ten seconds later: the reopen did not hold.
    assert wd.plan_recovery(10.0) == "rebuild"


def test_a_reopen_that_held_resets_the_ladder():
    wd = haptics.TransducerWatchdog()
    wd.reopened(0.0)
    # The meter is seen alive well past the flap window: episode over.
    wd.settled(wd.FLAP_WINDOW_S + 20.0)
    assert wd.plan_recovery(wd.FLAP_WINDOW_S + 30.0) == "reopen"


def test_rebuilds_are_capped_backed_off_and_end_in_one_clear_stand_down():
    wd = haptics.TransducerWatchdog()
    wd.reopened(0.0)
    t, rebuilds, waits, stood_down_at = 10.0, 0, 0, None
    while not wd.degraded and t < 1000.0:
        action = wd.plan_recovery(t)
        if action == "rebuild":
            rebuilds += 1
            wd.rebuilt(True, t)
        elif action == "wait":
            waits += 1
        if wd.degraded and stood_down_at is None:
            stood_down_at = t
        t += 10.0
    assert stood_down_at is not None
    assert rebuilds == wd.MAX_REBUILDS
    assert waits > 0, "every rebuild fired back-to-back with no backoff"
    assert wd.degraded
    notice = wd.take_notice()
    assert notice is not None
    written, spoken = notice
    assert "power-cycle" in written
    assert spoken, "nothing for the voice to say"
    assert wd.take_notice() is None, "the notice repeated"
    assert wd.stood_down, "the exhaustion was not recorded"
    # **A stand-down is a pause, not a verdict.** It used to be absorbing -
    # `degraded` was set in one place and cleared in none - so the one state
    # that most needed the ladder was the one state it could not run in, and
    # the seat never came back without restarting the app.
    assert wd.plan_recovery(
        stood_down_at + wd.STAND_DOWN_RETRY_S - 10.0) == "stand-down"
    assert wd.plan_recovery(
        stood_down_at + wd.STAND_DOWN_RETRY_S + 10.0) == "reopen", (
        "the ladder never stood back up")
    assert not wd.degraded, "re-armed but still reporting itself spent"
    # And he is told once, however many times it tries again.
    assert wd.take_notice() is None, "told again on every re-arm"


def test_a_rebuild_is_only_claimed_after_the_meter_is_seen_alive():
    """The stream opening proves nothing - opening is the one thing a wedged
    endpoint still does perfectly. The driver is told when the meter moves."""
    wd = haptics.TransducerWatchdog()
    wd.reopened(0.0)
    wd.rebuilt(True, 10.0)
    assert wd.take_notice() is None, "claimed success off a bare open"
    wd.settled(20.0)
    notice = wd.take_notice()
    assert notice is not None and "came back" in notice[0]
    # And once only, however often it settles afterwards.
    wd.settled(30.0)
    assert wd.take_notice() is None


# ------------------------------- the controller wiring, driven without a card

class _RecordingVoice:
    def __init__(self):
        self.spoken = []

    def say(self, text):
        self.spoken.append(text)


class _WedgedForGood:
    """Recovers and rebuilds on command; the device stays dead regardless."""

    def __init__(self):
        self.reopens = 0
        self.rebuilds_called = 0

    def recover(self):
        self.reopens += 1
        return True

    def rebuild(self):
        self.rebuilds_called += 1
        return True


def _rack(engine):
    """A controller pared down to the endpoint-reading path."""
    from pitcrew.controller import PitCrewController

    class Bridge:
        haptics = engine

    class Rack:
        _act_on_endpoint_reading = PitCrewController._act_on_endpoint_reading
        _climb_ladder = PitCrewController._climb_ladder
        _deliver_rig_notice = PitCrewController._deliver_rig_notice
        _endpoint_note = ""

        def __init__(self):
            self._rig_watchdog = haptics.TransducerWatchdog()
            self.bridge = Bridge()
            self.voice = _RecordingVoice()

    return Rack()


def test_a_frozen_race_night_runs_the_whole_ladder_and_tells_him_once():
    """The 16 Aug 2026 race, replayed against the fix: meter frozen at 0.054
    from 20:32 to the flag. Reopen, then the rebuilds, then one spoken
    instruction and a stand-down - not twenty minutes of `recoveries 0`."""
    engine = _WedgedForGood()
    rack = _rack(engine)
    rendered = (0.30, 0.55, 0.42, 0.51, 0.38, 0.47)
    for i in range(60):                          # ten minutes of 10s polls
        rack._act_on_endpoint_reading(engine, "Speakers (ButtKicker PRO)",
                                      rendered[i % len(rendered)], 0.054,
                                      10.0 * i)
    # Ten minutes at a 5-minute retry is two climbs, not one per poll and
    # not one forever. The cadence is the point: it keeps looking for an
    # endpoint that may have been reset or replugged, without hammering one
    # that is genuinely gone.
    assert engine.reopens == 2
    cap = rack._rig_watchdog.MAX_REBUILDS
    assert cap < engine.rebuilds_called <= 2 * cap, (
        f"{engine.rebuilds_called} rebuilds in ten minutes - one climb, a "
        f"stand-down, and part of a second is the shape; per-poll is not")
    assert rack._rig_watchdog.stood_down
    assert len(rack.voice.spoken) == 1, (
        f"spoken {len(rack.voice.spoken)} times: {rack.voice.spoken}")
    assert "STALE" in rack._endpoint_note
    assert "recovery exhausted" in rack._endpoint_note


def test_a_rebuild_aborted_by_the_drivers_stop_is_not_an_attempt():
    """`rebuild` answers None when a stop or suspend cut it short. That is
    the driver's own action, not the device failing - spending one of the
    three capped attempts on it would degrade a session that merely raced
    its own shutdown."""

    class Aborting:
        def __init__(self):
            self.reopens = 0
            self.rebuild_calls = 0

        def recover(self):
            self.reopens += 1
            return True

        def rebuild(self):
            self.rebuild_calls += 1
            return None

    engine = Aborting()
    rack = _rack(engine)
    rendered = (0.30, 0.55, 0.42, 0.51)
    for i in range(30):
        rack._act_on_endpoint_reading(engine, "ButtKicker",
                                      rendered[i % len(rendered)], 0.054,
                                      10.0 * i)
    assert engine.rebuild_calls >= 2, "an aborted rebuild was never retried"
    assert not rack._rig_watchdog.degraded
    assert rack.voice.spoken == []


def test_a_poll_from_a_stopped_session_cannot_touch_the_watchdog():
    """The meter poll runs on its own thread and can land after the session
    it belonged to was stopped. It must not deposit its reading into - or
    lazily create state for - whatever session comes next."""
    rack = _rack(None)                   # the session has been stopped
    old_engine = _WedgedForGood()
    rack._act_on_endpoint_reading(old_engine, "ButtKicker", 0.5, 0.054, 0.0)
    assert old_engine.reopens == 0
    assert rack._endpoint_note == "", "a dead session's poll wrote the note"
    assert rack._rig_watchdog.stale_details()["count"] == 0


def test_report_rig_feeds_the_engines_block_counter_to_the_watchdog():
    """The cadence watchdog's diet is `haptics.callbacks` AND `haptics.frames`
    once per report cycle. Wiring either to another counter would silently
    blind the corroboration - and without the frames the cadence line cannot
    tell a longer buffer from a slower clock, which is the distinction the
    session of 17 Aug 2026 needed and did not have."""
    from pitcrew.controller import PitCrewController

    engine = _engine()
    _pump_live(engine, 7)
    fed = []

    class Watchdog:
        degraded = False
        clock_hz = None
        clock_suspect = False

        def note_cadence(self, blocks, now, frames=None):
            fed.append((blocks, now, frames))

    class Bridge:
        haptics = engine
        wind = None

    class Rack:
        _report_rig = PitCrewController._report_rig
        _apply_clock_verdict = PitCrewController._apply_clock_verdict

        def __init__(self):
            self.bridge = Bridge()
            self.voice = _RecordingVoice()
            self._rig_watchdog = Watchdog()
            self._endpoint_note = "endpoint not yet asked"
            self._log_haptic_state = lambda h: None
            self._check_transducer_is_heard = lambda h: None

    Rack()._report_rig()
    assert len(fed) == 1
    assert fed[0][0] == engine.callbacks == 7
    assert fed[0][2] == engine.frames == 7 * 512


def test_a_wedge_the_reopen_fixes_stays_quiet():
    """19:58 and 20:12 the same day: one reopen, endpoint back, race goes on.
    No rebuild, no spoken notice - the log lines recover writes are enough."""
    engine = _WedgedForGood()
    rack = _rack(engine)
    rendered = (0.30, 0.55, 0.42, 0.51, 0.38)
    # Frozen until the reopen fires...
    polls = 0
    while engine.reopens == 0:
        rack._act_on_endpoint_reading(engine, "ButtKicker",
                                      rendered[polls % len(rendered)], 0.054,
                                      10.0 * polls)
        polls += 1
    # ...after which the meter jitters again.
    for i in range(polls, polls + 30):
        rack._act_on_endpoint_reading(engine, "ButtKicker",
                                      rendered[i % len(rendered)],
                                      0.080 + 0.001 * (i % 5), 10.0 * i)
    assert engine.reopens == 1
    assert engine.rebuilds_called == 0
    assert rack.voice.spoken == []
    assert "endpoint 0.0" in rack._endpoint_note
    assert not rack._rig_watchdog.degraded


# ---------------------- what the stream became, and whether it is a recovery
#
# **The session of 17 Aug 2026, which the record could not settle.** The meter
# read silent for thirteen minutes and the app said so out loud; the driver
# felt the seat working, badly. Both cannot be true of one stream on one
# endpoint, and nothing was written down that could tell which had moved -
# `_open` logged the name it had ASKED for and nothing about what came back.


class _IndexedPortAudio:
    """A device table `describe_stream` can look a route up in."""

    def __init__(self):
        self.hostapis = [{"name": "Windows WASAPI"}, {"name": "MME"}]
        self.devices = [
            {"name": transducer.DEVICE_NAME, "hostapi": 0,
             "max_output_channels": 2, "max_input_channels": 0},
            {"name": transducer.DEVICE_NAME, "hostapi": 1,
             "max_output_channels": 8, "max_input_channels": 0},
        ]

    def query_devices(self, index=None):
        return self.devices if index is None else self.devices[index]

    def query_hostapis(self, index=None):
        return self.hostapis if index is None else self.hostapis[index]

    def _terminate(self):
        pass

    def _initialize(self):
        pass


class _NegotiatedStream(_FakeStream):
    """A started stream that answers for itself, as PortAudio's does."""

    def __init__(self, *, samplerate=48000.0, blocksize=480, channels=2,
                 dtype="float32", device=0, latency=0.021):
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.channels = channels
        self.dtype = dtype
        self.device = device
        self.latency = latency
        self.closed = False

    def close(self):
        self.closed = True


def _routed(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "sounddevice", _IndexedPortAudio())


def test_a_stream_at_the_wrong_rate_is_named_and_refused(monkeypatch):
    """The one fault the log could not see. The mix is generated at a fixed
    48 kHz; a stream clocked at 44.1 transposes every effect by 0.92, and the
    amplifier passes 25-160 Hz, so the road bed and the engine tone walk out
    of the band the rig can deliver. That is "the vibrations were all wrong",
    and it opened, started and reported success.

    Refused rather than followed, for the same reason `strict=True` refuses
    the default card: wrong output into a 150 W piston is worse than none,
    which is the driver's own verdict.
    """
    _routed(monkeypatch)
    opened = []

    def open_output(*args, **kwargs):
        stream = _NegotiatedStream(samplerate=44100.0, blocksize=441)
        opened.append(stream)
        return stream

    monkeypatch.setattr(haptics.audio_devices, "open_output", open_output)
    monkeypatch.setattr(haptics.audio_devices, "register_sustained",
                        lambda e: None)
    engine = _engine()

    assert engine.start() is False, "it took a stream it cannot render for"
    assert engine.running is False
    assert engine.format_refusals == 1
    assert opened[0].closed, "the refused stream was left open"
    assert "44100" in engine.error and "48000" in engine.error
    # And it says what the consequence is, not only that a number differs.
    assert "amplifier" in engine.error


def test_an_open_that_matches_the_request_is_unremarkable(monkeypatch):
    """The whole check has to be invisible when nothing has moved."""
    _routed(monkeypatch)
    monkeypatch.setattr(haptics.audio_devices, "open_output",
                        lambda *a, **k: _NegotiatedStream())
    monkeypatch.setattr(haptics.audio_devices, "register_sustained",
                        lambda e: None)
    engine = _engine()

    assert engine.start() is True
    assert engine.error is None
    assert engine.format_refusals == 0
    assert engine.last_open_changed == ()
    assert engine.facts.host_api == "Windows WASAPI"
    assert "Windows WASAPI" in engine.describe()


def test_a_rebuild_onto_another_route_is_not_counted_as_a_recovery(
        monkeypatch):
    """`recover` and `rebuild` used to declare success the moment a stream
    opened. Opening is the one thing a wedged endpoint still does perfectly -
    and a stream that opens on a DIFFERENT route is a different output. Two
    of the routes to this card cannot be verified at all: DirectSound buffers
    and discards, WDM-KS renders underneath the audio engine the endpoint
    meter reads. Counting either as a fix is how the app comes to believe it
    repaired what it had just broken.
    """
    _routed(monkeypatch)
    routes = iter([0, 1])                       # WASAPI first, then MME

    def open_output(*args, **kwargs):
        return _NegotiatedStream(device=next(routes), blocksize=1024)

    engine = _engine()
    _patch_rebuild_plumbing(monkeypatch, engine, open_output)

    assert engine.start() is True
    assert engine.rebuild() is False, "a different route was called a recovery"
    # The stream IS open - it may be all he has - but it is not the one that
    # was working, so the ladder must escalate rather than stand down happy.
    assert engine.running is True
    assert engine.route_changes == 1
    assert any("host_api" in line for line in engine.last_open_changed)


def test_a_rebuild_onto_the_same_terms_is_still_a_recovery(monkeypatch):
    """The other half, and the one that must not regress: nothing differs, so
    the ladder behaves exactly as it did."""
    _routed(monkeypatch)
    engine = _engine()
    _patch_rebuild_plumbing(monkeypatch, engine,
                            lambda *a, **k: _NegotiatedStream())

    assert engine.start() is True
    assert engine.rebuild() is True
    assert engine.route_changes == 0
    assert engine.last_open_changed == ()


def test_a_stream_that_says_nothing_about_itself_changes_nothing(monkeypatch):
    """`_FakeStream` and a real stream that will not answer are the same
    case: unknown is not a difference, and must not escalate a recovery that
    was fine."""
    engine = _engine()
    _patch_rebuild_plumbing(monkeypatch, engine,
                            lambda *a, **k: _FakeStream())
    assert engine.start() is True
    assert engine.rebuild() is True
    assert engine.route_changes == 0


# -------------------------------- the frame clock, beside the block cadence

def test_the_frame_clock_tells_a_longer_buffer_from_a_slower_one(caplog):
    """100 blocks a second falling to 64 and staying there is what the log
    held on 16 and 17 Aug, and it is two different faults wearing one number:
    PortAudio handing us 750-frame blocks instead of 480, or the card
    consuming a third fewer samples a second and transposing the whole mix.
    Frames per second separates them in one line."""
    import logging

    wd = haptics.TransducerWatchdog()
    blocks = frames = 0
    with caplog.at_level(logging.WARNING, logger="pitcrew.haptics"):
        for cycle in range(8):
            # 100/s at 480 frames for the first four cycles, then 64/s at 750
            # frames - the same 48000 frames a second throughout.
            per_second, block = (100, 480) if cycle < 4 else (64, 750)
            blocks += per_second * 10
            frames += per_second * block * 10
            wd.note_cadence(blocks, 10.0 * cycle, frames=frames)

    assert wd.clock_hz is not None
    assert abs(wd.clock_hz - transducer.SAMPLE_RATE) < 1.0
    assert wd.clock_suspect is False, "a longer buffer read as a bad clock"
    dropped = [r.message for r in caplog.records
               if "cadence fell" in r.message]
    assert dropped, "the cadence drop was not noticed at all"
    assert "longer buffer" in dropped[0]
    assert "still in tune" in dropped[0]
    # And nothing that cannot be vouched for: a longer buffer is not a doubt.
    assert wd.uncertain is False


def test_a_clock_that_moved_with_the_cadence_is_convicted(caplog):
    """The other half: the block size held and the rate fell, so every effect
    is transposed and the road bed no longer lands where the amp passes it."""
    import logging

    wd = haptics.TransducerWatchdog()
    blocks = frames = 0
    with caplog.at_level(logging.ERROR, logger="pitcrew.haptics"):
        for cycle in range(8):
            per_second = 100 if cycle < 4 else 64
            blocks += per_second * 10
            frames += per_second * 480 * 10     # 480 frames throughout
            wd.note_cadence(blocks, 10.0 * cycle, frames=frames)

    assert wd.clock_suspect is True
    assert abs(wd.clock_hz - 64 * 480) < 1.0
    named = [r.message for r in caplog.records if "frame clock" in r.message]
    assert named, "a transposed mix was never named"
    assert "transposed" in named[0]
    # And it is a reason the app cannot vouch for a silent-meter verdict.
    assert wd.uncertain is True


def test_a_cadence_drop_with_no_frame_count_says_it_cannot_tell(caplog):
    """The state the log was in on 17 Aug: blocks only. It must admit that
    rather than assert the harmless reading."""
    import logging

    wd = haptics.TransducerWatchdog()
    blocks = 0
    with caplog.at_level(logging.WARNING, logger="pitcrew.haptics"):
        for cycle in range(8):
            blocks += (100 if cycle < 4 else 64) * 10
            wd.note_cadence(blocks, 10.0 * cycle)

    dropped = [r.message for r in caplog.records
               if "cadence fell" in r.message]
    assert dropped
    assert "cannot say" in dropped[0]
    assert wd.clock_hz is None


# ----------------- the meter and the stream disagreeing, and what he is told

def _reading(peak, **kwargs):
    from pitcrew.engineer import endpoint_meter
    kwargs.setdefault("matches", 1)
    return endpoint_meter.Reading(peak=peak, **kwargs)


def test_a_meter_that_could_not_be_read_never_runs_the_ladder():
    """`poll_briefly` used to answer 0.0 when the meter could not be opened
    at all, and the controller read that as "the card played nothing" - an
    ERROR, three device rebuilds, and a spoken notice that the haptics were
    gone, on the strength of an instrument that was never there. "Cannot
    measure" is not "failed"; it is this module's oldest rule."""
    engine = _WedgedForGood()
    rack = _rack(engine)
    for i in range(40):
        rack._act_on_endpoint_reading(
            engine, "ButtKicker", 0.5,
            _reading(None, detail="no peak meter for this device"), 10.0 * i)

    assert engine.reopens == 0
    assert engine.rebuilds_called == 0
    assert rack.voice.spoken == []
    assert not rack._rig_watchdog.degraded
    assert "UNREADABLE" in rack._endpoint_note


def test_two_endpoints_of_one_name_make_the_verdict_an_admission():
    """**The contradiction of 17 Aug, reproduced.** The meter resolves an
    endpoint by friendly name and takes the first match; PortAudio resolves
    the stream separately, walking its own list in its own order. Two active
    endpoints spelling themselves identically - one card on two USB ports, or
    a re-enumeration whose old endpoint has not left the ACTIVE list - and
    the two can disagree. "It played nothing" is then a true statement about
    an endpoint nobody was feeding, and the driver hears it while the seat is
    working.
    """
    engine = _WedgedForGood()
    rack = _rack(engine)
    rendered = (0.30, 0.55, 0.42, 0.51, 0.38, 0.47)
    for i in range(60):
        rack._act_on_endpoint_reading(
            engine, transducer.DEVICE_NAME, rendered[i % len(rendered)],
            _reading(0.054, matches=2, endpoint="{0.0.0}.ButtKicker#1"),
            10.0 * i)

    assert rack._rig_watchdog.stood_down
    assert len(rack.voice.spoken) == 1
    spoken = rack.voice.spoken[0]
    assert "lost sight" in spoken, spoken
    assert "if you can still feel them" in spoken.lower(), spoken
    # The confident claim is exactly what it must NOT make.
    assert "Haptics are out" not in spoken
    assert any("2 active endpoints" in d
               for d in rack._rig_watchdog.doubts())


def test_one_endpoint_and_a_readable_meter_still_gets_the_plain_verdict():
    """The confident line survives for the case the app can stand behind -
    one endpoint of that name, a meter it could read, a stream still on the
    terms it opened with. Hedging a verdict that IS sound would cost the
    driver the one instruction he can act on."""
    engine = _WedgedForGood()
    rack = _rack(engine)
    rendered = (0.30, 0.55, 0.42, 0.51, 0.38, 0.47)
    for i in range(60):
        rack._act_on_endpoint_reading(
            engine, transducer.DEVICE_NAME, rendered[i % len(rendered)],
            _reading(0.054, matches=1, endpoint="{0.0.0}.ButtKicker"),
            10.0 * i)

    assert rack._rig_watchdog.stood_down
    assert rack._rig_watchdog.uncertain is False
    assert len(rack.voice.spoken) == 1
    assert "Haptics are out" in rack.voice.spoken[0]


def test_the_metered_endpoint_changing_under_us_is_recorded():
    """Same name, different endpoint ID between two polls: whatever the meter
    said before was about a different device."""
    wd = haptics.TransducerWatchdog()
    wd.note_endpoint("{0.0.0}.ButtKicker#1", 1)
    assert wd.uncertain is False
    wd.note_endpoint("{0.0.0}.ButtKicker#2", 1)
    assert wd.uncertain is True
    assert any("changed mid-session" in d for d in wd.doubts())


def test_a_stream_that_reopened_differently_hedges_the_verdict_too():
    """A route change is the app's own half of the same ambiguity: the meter
    may be perfectly correct about an endpoint the stream no longer feeds."""
    wd = haptics.TransducerWatchdog()
    wd.note_stream_changed(())
    assert wd.uncertain is False
    wd.note_stream_changed(("host_api was Windows WASAPI and is now MME",))
    assert wd.uncertain is True


def test_a_bare_peak_still_means_measured_and_unambiguous():
    """Every existing caller hands a float. It must keep meaning what it
    always meant, or the ladder changes behaviour where nothing differs."""
    from pitcrew.engineer import endpoint_meter

    reading = endpoint_meter.Reading.of(0.054)
    assert reading.measured is True
    assert reading.ambiguous is False
    assert reading.peak == 0.054
    assert endpoint_meter.Reading.of(reading) is reading
    assert endpoint_meter.Reading.of(None).measured is False


# ------------- a stream that is open, correct to hold, and wrong to send to

def test_a_refusal_sends_nothing_and_allowing_brings_it_back():
    """The rule `_open` has always had, applied while the stream is running.

    17 Aug 2026: the stream opened honestly at 48 kHz and was then pulled at
    30.6, so every effect arrived transposed by 0.64x and the two continuous
    beds landed under the amplifier's low-cut. The app named it in the log
    and went on driving the piston with it for nineteen minutes.
    """
    engine = _engine()
    assert _peak(_pump_live(engine, 40)) > 0.05, "nothing to refuse"

    engine.refuse("the card is pulling about 30611 frames a second")
    _pump_live(engine, 40)                       # the fade-out completes
    assert _peak(_pump_live(engine, 10)) == 0.0, "still driving the piston"

    engine.allow()
    _pump_live(engine, 40)
    assert _peak(_pump_live(engine, 10)) > 0.05, "never came back"


def test_a_refusal_fades_rather_than_cutting():
    """An instant mute is a discontinuity and a discontinuity here is a
    thump - the same reason the telemetry watchdog fades."""
    engine = _engine()
    _pump_live(engine, 40)
    engine.refuse("wrong rate")
    assert _peak(_pump_live(engine, 1)) > 0.0, "cut instead of faded"


def test_a_refusal_is_announced_once_and_lifted_once():
    engine = _engine()
    assert engine.refuse("wrong rate") is True
    assert engine.refuse("wrong rate") is False, "would repeat every cycle"
    assert engine.refusals == 1
    assert "nothing is being sent" in engine.describe()
    assert engine.allow() is True
    assert engine.allow() is False


def test_one_off_rate_cycle_cannot_mute_the_seat():
    """A recovery is itself a hole in the frame clock: `rebuild` stands back
    for a second before it reopens, so the cycle containing one reads low
    whatever the card is really doing. 27059 Hz was logged that way on 17 Aug
    against a stream that was really at 30611. One cycle was enough when the
    only cost was a log line; it is not enough now that it silences him."""
    wd = haptics.TransducerWatchdog()
    blocks = frames = 0
    for cycle in range(5):
        blocks += 100 * 10
        frames += 100 * 480 * 10
        wd.note_cadence(blocks, 10.0 * cycle, frames=frames)
    assert wd.clock_suspect is False

    blocks += 90 * 10                 # a second of the stream shut, once
    frames += 90 * 480 * 10
    wd.note_cadence(blocks, 50.0, frames=frames)
    assert wd.clock_suspect is False, "a rebuild transient muted the seat"

    blocks += 100 * 10
    frames += 100 * 480 * 10
    wd.note_cadence(blocks, 60.0, frames=frames)
    assert wd.clock_suspect is False


def test_the_stand_down_says_whether_it_is_still_sending():
    """"I have stopped trying" was heard as "I have stopped sending", and on
    17 Aug the app then fed the piston for nineteen more minutes."""
    wd = haptics.TransducerWatchdog()
    wd.reopened(0.0)
    t = 10.0
    while not wd.degraded and t < 1000.0:
        if wd.plan_recovery(t) == "rebuild":
            wd.rebuilt(True, t)
        t += 10.0
    spoken = wd.take_notice()[1]
    assert "stopped trying to fix" in spoken
    assert "still sending" in spoken, "left him guessing where it came from"


def test_the_stand_down_admits_when_it_has_also_stopped_sending():
    wd = haptics.TransducerWatchdog()
    wd.clock_suspect = True
    wd.reopened(0.0)
    t = 10.0
    while not wd.degraded and t < 1000.0:
        if wd.plan_recovery(t) == "rebuild":
            wd.rebuilt(True, t)
        t += 10.0
    spoken = wd.take_notice()[1]
    assert "no longer sending" in spoken


def test_a_transposed_stream_is_refused_and_he_is_told_once():
    from pitcrew.controller import PitCrewController

    class Watchdog:
        clock_hz = 30611.0
        clock_suspect = True
        settled_at = None

        def settled(self, now):
            # **The ladder's only reset, and until 22 Aug 2026 it could not
            # be reached from here.** `_check_transducer_is_heard` refuses
            # to poll the endpoint meter while the output is refused, and
            # the meter was the sole caller of `settled` - so the attempt
            # counters could never be cleared in the one state that needed
            # them cleared.
            self.settled_at = now

    class Rack:
        _apply_clock_verdict = PitCrewController._apply_clock_verdict

        def __init__(self):
            self.voice = _RecordingVoice()

    engine, rack, wd = _engine(), Rack(), Watchdog()
    rack._apply_clock_verdict(engine, wd)
    assert engine.refused is not None and "30611" in engine.refused
    assert len(rack.voice.spoken) == 1
    assert "wrong speed" in rack.voice.spoken[0]

    rack._apply_clock_verdict(engine, wd)
    assert len(rack.voice.spoken) == 1, "repeated every ten seconds"

    wd.clock_suspect, wd.clock_hz = False, 48000.0
    rack._apply_clock_verdict(engine, wd)
    assert engine.refused is None
    assert len(rack.voice.spoken) == 2, "never said it was back"
    assert wd.settled_at is not None, (
        "a clock back at nominal did not reset the recovery ladder, so the "
        "next fault would start from an already-spent ladder")


def test_the_meter_is_not_asked_about_audio_nobody_sent(monkeypatch):
    """Polling it here would write down "it is accepting the audio and
    playing none of it" - true, and entirely about a silence of our own
    making. The ladder still has to climb, off the clock instead."""
    from pitcrew.controller import PitCrewController
    from pitcrew.engineer import endpoint_meter as meter

    polled = []
    monkeypatch.setattr(meter, "poll_briefly",
                        lambda *a, **k: polled.append(a))

    class Engine:
        refused = "the card is pulling about 30611 frames a second"

        def take_recent_peak(self):
            return 0.5

    climbed = []

    class Settings:
        haptics_device = "Speakers (ButtKicker PRO)"

    class Rack:
        _check_transducer_is_heard =             PitCrewController._check_transducer_is_heard
        _AUDIBLE_PEAK = PitCrewController._AUDIBLE_PEAK
        _endpoint_note = ""

        def __init__(self):
            self._rig_watchdog = haptics.TransducerWatchdog()
            self.settings = Settings()
            self._climb_ladder_off_thread =                 lambda h, w: climbed.append(h)

    rack = Rack()
    rack._check_transducer_is_heard(Engine())
    assert "REFUSED" in rack._endpoint_note
    assert polled == [], "asked a meter about audio it never got"
    assert climbed, "the ladder stopped climbing the moment it went quiet"
