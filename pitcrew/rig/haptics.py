"""Holding the transducer's stream open for a whole race.

`synth` makes the signal; this owns the sound card and the clock. It is the
half where the failure modes are about time rather than arithmetic, and there
is one that matters more than all the others put together:

**A stuck tone.** If telemetry stops - the console sleeps, the network drops,
the packet thread dies, the app hangs - the audio callback keeps running,
because PortAudio's thread is not Python's. It would go on rendering the last
intensities it was given, forever, at 150 W, into a piston six inches from the
driver. The stream closing is not the danger; the stream *surviving* is.

So the watchdog counts frames **inside the callback**, and that placement is
the entire point. A Python timer cannot help here: if the Python side is what
died, the timer never fires either. The only clock that keeps ticking is the
sound card's, and it ticks by handing us blocks to fill. Counting them is the
one measure of elapsed time that survives everything upstream failing.

The second rule is the one the audio layer learned the hard way: **a device
list rebuild closes every open stream in the process, silently.** This stream
lives for the whole race, so it registers as sustained and is suspended and
resumed around a rebuild rather than being quietly destroyed by one. See
`audio_devices._reinitialise`.
"""
from __future__ import annotations

import sys
import threading
import time
from collections import deque

import numpy as np

from pitcrew.diagnostics import log
from pitcrew.engineer import audio_devices
from pitcrew.rig import synth, transducer

# The block PortAudio is asked for. Zero lets it choose, which resolves to
# 480 frames on WASAPI here - 10 ms of audio per callback.
#
# **The block is not only a buffer. It is the rate the rig reads the car.**
# The callback is the one place the mix samples telemetry, so whatever is
# chosen here sets that sampling rate, and it has to stay well above the
# 60 Hz the feed arrives at. That is the constraint the starvation fix ran
# into, below.
#
# The callback is also Python, and cannot run until it is handed the GIL.
# Measured 22 Aug 2026 on this machine, on a healthy endpoint, with the
# callback doing nothing at all beyond counting:
#
#     GIL threads   block 0 (480)   block 2048
#     0                48118 f/s      48297 f/s
#     2                39108 f/s      48059 f/s
#
# Two other Python threads holding the GIL are enough to starve a 10 ms
# callback, because the callback cannot run until it is handed the GIL and
# the default handover interval is 5 ms. The app runs seven or eight threads
# - Qt, the 60 Hz UDP parser, the meter, the ladder, the beep, wind, voice,
# the HUD sampler - so it lives permanently in that condition.
#
# **And a starved callback does not merely gap the audio; it degrades the
# endpoint.** Chronic underfeed drops the ButtKicker's own pump to one block
# per 15.625 ms system tick - 480 x 64 = 30720 frames a second - and it stays
# there across app restarts, which is the "only a reboot clears it" wedge
# this module has been chasing since 16 Aug. Every client of that endpoint is
# throttled once it happens, on any host API.
#
# **It was raised to 2048 and put straight back, and the reason is worth
# keeping.** 2048 frames is 42.7 ms of slack against the tick, which does
# stop the starvation - but the callback is also the only place the mix reads
# the car, so its rate is the rate the whole rig samples telemetry at. 2048
# frames is 23.4 callbacks a second against a 60 Hz feed: the continuous beds
# are unaffected, and every sharp cue - a kerb strike, an impact, a lock -
# is undersampled and smears. Practice, 22 Aug: "something is droning
# everything else out on acceleration". It also cost 85.3 ms of output
# latency, logged, on cues whose whole value is arriving early.
#
# `SWITCH_INTERVAL_S` alone carries the fix, measured at every load level
# tested - 48094 f/s at three contending threads, 48142 at six - so the block
# size was never the load-bearing half. Zero it is, which resolves to 480
# frames on WASAPI here: 10 ms a callback, 100 a second, comfortably faster
# than the feed it is reading.
BLOCKSIZE = 0
# The largest block we will be handed. Buffers are sized for this once, so a
# callback never allocates.
MAX_BLOCK = 8192
# How long a Python thread may hold the GIL before it is asked to hand it
# over. CPython's default is 5 ms, which is half a 10 ms callback and a
# tenth of this one.
#
# The audio callback is Python, so it cannot run until it holds the GIL, and
# under contention it waits roughly one switch interval per competing thread.
# Measured on this machine against a healthy endpoint, block 0, two Python
# threads spinning: 39108 frames a second at the 5 ms default, 48119 at
# 0.5 ms - the whole deficit, closed by one call.
#
# Process-wide, and deliberately so: it is the process's threads that are in
# the way. The cost is more context switches in code that is not
# latency-critical, which on a 14-thread part is not a cost worth measuring
# against a piston that stops working.
SWITCH_INTERVAL_S = 0.0005

# Telemetry arrives at 60 Hz, so a frame every ~16.7 ms. Silence for this long
# means it has stopped rather than merely been late.
STALE_S = 0.2
# How long a full rebuild stands back before reopening. The cadence drop that
# precedes these wedges is the endpoint's audio pump being rebuilt, and
# reopening into the middle of that lands the new stream on a half-built
# endpoint - which is how a "recovery" wedges straight back. One second is
# forever to that renegotiation and nothing to a race.
REBUILD_SETTLE_S = 1.0
# How long to take fading out, and back in. Long enough not to be a click -
# an instant mute is itself a discontinuity, and a discontinuity here is a
# thump - short enough that a real stop is not still buzzing a corner later.
FADE_S = 0.15


def _quicken_the_gil() -> None:
    """Shorten the GIL handover interval, once, for the whole process.

    Called from `start` rather than at import, so a build that never turns
    the transducer on never pays for it, and never has its scheduling
    changed by a module it merely imported.

    Only ever shortens. If something else in the process has already asked
    for a finer interval it keeps the finer one - this is a floor on
    responsiveness, not a setting to be won.
    """
    try:
        if sys.getswitchinterval() > SWITCH_INTERVAL_S:
            sys.setswitchinterval(SWITCH_INTERVAL_S)
    except (ValueError, AttributeError) as exc:              # pragma: no cover
        # Not worth failing an open over: the block size carries the same
        # fix on its own, measured, and this is the cheaper half of a pair.
        log("haptics").debug("could not shorten the GIL interval: %s", exc)


class HapticsEngine:
    """One output stream on the transducer, fed from the telemetry thread.

    `set_intensities` is called from wherever packets land and never blocks:
    it writes into an array and returns. Everything expensive happens on
    PortAudio's thread, so a slow sound card cannot reach the packet handler.
    """

    def __init__(self, *, specs=synth.PROFILE,
                 device: str = transducer.DEVICE_NAME,
                 master: float = 1.0) -> None:
        self._device = device
        self._specs = tuple(specs)
        self._mix = synth.HapticMix(specs, rate=transducer.SAMPLE_RATE,
                                    block=MAX_BLOCK, master=master)
        self._stereo = np.zeros((MAX_BLOCK, transducer.CHANNELS),
                                dtype=np.float32)
        # What the telemetry thread writes and the callback reads. Plain
        # arrays rather than a lock: the callback must never wait on a thread
        # that could be descheduled, and a half-updated intensity is one frame
        # stale, which the smoothing in `synth` swallows anyway.
        # **One slot per effect plus one per modifier.** A modifier renders
        # nothing and changes what the effects do - `unload` pulls the
        # background down so the driver feels the car go light. Sizing this
        # array from the number of VOICES would drop it silently.
        width = len(self._specs) + len(synth.MODIFIERS)
        self._wanted = np.zeros(width, dtype=np.float32)
        self._live = np.zeros(width, dtype=np.float32)
        # Bumped on every update. The callback watches it rather than a clock,
        # because it is the only evidence that anything upstream is alive.
        self._generation = 0
        self._seen_generation = -1
        self._stale_frames = 0
        self._fade = 0.0

        self._stream = None
        # **What the stream actually turned out to be, and what it was when
        # it was known to be working.** See `audio_devices.StreamFacts`. The
        # baseline is set by the first open of a session and never moved: a
        # reopen is measured against the configuration that was rendering
        # into the seat, not against the last thing that happened to open.
        self.facts: audio_devices.StreamFacts | None = None
        self.baseline: audio_devices.StreamFacts | None = None
        self.last_open_changed: tuple[str, ...] = ()
        self.format_refusals = 0
        self.route_changes = 0
        # Reentrant, and it has to be: `recover` holds this lock while it
        # reopens, and `audio_devices.open_output` may decide the device list
        # is stale and rebuild it - which calls straight back into `suspend`
        # on this same engine, on this same thread. With a plain Lock that is
        # a self-deadlock, and the main thread's `stop` then queues behind it
        # forever. Session 40 froze the whole app on exactly this: the driver
        # clicked stop practice in the same second the wedge detector fired
        # its first field recovery. With an RLock the nested suspend/resume
        # see `_stream is None` mid-reopen and fall through as no-ops.
        self._lock = threading.RLock()
        self._suspended = False
        self._stopped = False
        self.error: str | None = None
        # **Refusal: the open-time rule, arriving at runtime.**
        #
        # `_open` refuses a stream whose negotiated rate is not the one the
        # mix is generated for, on the driver's own verdict that wrong output
        # is worse than none. Until 17 Aug 2026 that check ran once, against
        # the terms the stream opened with - and that evening's failure was a
        # stream that opened honestly at 48 kHz and was then pulled at 30.6.
        # Every effect arrived transposed by 0.64x, the engine and road beds
        # landed at 20 and 24 Hz - under the amplifier's fixed 25 Hz low-cut -
        # and the app went on driving the piston with it for nineteen minutes
        # after it had written down exactly what was wrong. The driver felt a
        # constant drone that tracked nothing, and had been told the haptics
        # were finished.
        #
        # Same rule, same reason, now applied while the stream is running:
        # what cannot be rendered correctly is not rendered at all.
        self._refused: str | None = None
        self.refusals = 0
        self.faded_out = 0
        self.callbacks = 0
        # **Frames, not only blocks.** The block count alone cannot tell a
        # longer buffer from a slower clock: 100 blocks a second falling to
        # 64 is either PortAudio handing us 750-frame blocks instead of 480,
        # or the card consuming samples a third slower than the synthesiser
        # makes them. The first is harmless and the second transposes every
        # tone in the mix. On 17 Aug 2026 the log recorded only the blocks,
        # and thirteen minutes of evidence could not distinguish them.
        self.frames = 0
        # **Whether the card asked for frames we failed to supply. Kept, but
        # it must never decide anything on WASAPI, where it does not work.**
        #
        # This was added on 17 Aug to settle the question the frame count
        # could not: whether the card was really consuming 30.7 kframes a
        # second - in which case the mix is transposed, the road bed lands at
        # 24 Hz under the amplifier's fixed 25 Hz low-cut, and refusing is
        # right - or whether the card still wanted 48 k and we were handing
        # it 30.7 k, in which case nothing is transposed and the cues are
        # merely gapped.
        #
        # It shipped at 22:07 on 17 Aug. The race had ended at 20:58 and the
        # transducer was switched off the same day, so it never once ran
        # against the fault. When it was finally put on a bench, 22 Aug, it
        # turned out it could not have answered:
        #
        #     starved to a third of nominal    delivered    output_underflow
        #     WASAPI  (the route this uses)      15960 f/s          0
        #     MME                                12095 f/s        240
        #     DirectSound                        15962 f/s        660
        #
        # PortAudio's WASAPI backend never sets the flag on this machine. A
        # rule of the form "no underruns, therefore the card is slow" can
        # only ever return one answer there, and it is the wrong one.
        #
        # The bench also settled the underlying question outright: the card
        # was healthy at 48 kHz and this process was starving it, because a
        # Python audio callback cannot run until it holds the GIL. See
        # `SWITCH_INTERVAL_S` and `BLOCKSIZE`, which are the fix, and
        # `dac_seconds` below, which is the instrument that replaced this
        # one. Still counted because MME and DirectSound are real fallback
        # routes and it is honest there, and because it costs one bool test.
        self.underflows = 0
        self._underflows_taken = 0
        self.status_blocks = 0
        # **PortAudio's own stream clock, which is the card's and not ours.**
        #
        # `frames / wall seconds` is what this process managed to hand over.
        # For ten days it was logged as "the card is pulling N frames a
        # second" and read as a property of the hardware, and on 17 Aug that
        # misreading muted the seat for the rest of the race. These two make
        # the other measurement available, so the report can say which of the
        # two is happening instead of assuming:
        #
        #     delivery low, DAC clock at 48000  -> we are starving it
        #     delivery low, DAC clock low too   -> the endpoint has degraded
        #
        # The second one is real and is the chronic ButtKicker wedge: chronic
        # underfeed drops the endpoint's own pump to one block per 15.625 ms
        # tick, and it stays there across app restarts until the machine is
        # rebooted. Which is why the first case matters so much - it is the
        # one that causes the second.
        self.dac_seconds = 0.0
        self.dac_frames = 0
        self._dac_first = 0.0
        self.recoveries = 0
        self.rebuilds = 0

    # --------------------------------------------------------- from outside

    def set_intensities(self, values) -> None:
        """The effect levels and modifiers, 0-1 each, on the telemetry thread.

        A shorter array than expected is accepted and the rest left at zero,
        because that is what a caller written before the modifiers existed
        sends and silence is the right answer for a modifier nobody set.
        """
        incoming = np.asarray(values, dtype=np.float32)
        count = min(len(incoming), len(self._wanted))
        np.clip(incoming[:count], 0.0, 1.0, out=self._wanted[:count])
        if count < len(self._wanted):
            self._wanted[count:] = 0.0
        self._generation += 1

    def set_master(self, gain: float) -> None:
        """Change the overall strength without restarting the stream.

        Read by the callback on its next block. Nothing is torn down, so the
        driver can turn it up and feel the difference immediately rather than
        stopping the session to judge a number.
        """
        self._mix.master = max(0.0, min(4.0, float(gain)))

    def take_underflows(self) -> int:
        """How many blocks underran since this was last asked.

        A delta rather than a total, and by the same pattern as
        `take_recent_peak`: the question the report line asks is "is the card
        starving NOW", and a lifetime count answers that only by subtraction
        somewhere else. Keeping the subtraction here keeps the reader
        stateless.
        """
        seen = self.underflows
        delta = seen - self._underflows_taken
        self._underflows_taken = seen
        return delta

    def take_recent_peak(self) -> float:
        """The loudest sample rendered since this was last asked.

        Half of the only question worth asking about a transducer: did WE
        produce a signal? The other half - did the card render it - is
        `endpoint_meter`, and the two together are what separate a quiet lap
        from a dead device.
        """
        return self._mix.take_recent_peak()

    def silence(self) -> None:
        self._wanted[:] = 0.0
        self._generation += 1

    def refuse(self, reason: str) -> bool:
        """Stop sending, because what we would send is wrong.

        Neither a stop nor a suspend, and the difference is the point: the
        stream stays open and the callback goes on being handed blocks, so the
        frame clock - the instrument that convicts a transposed stream, and
        the only one that can see it come back - keeps being measured. What
        changes is that nothing reaches the card.

        It fades rather than mutes, by the same path and for the same reason a
        dead telemetry feed does: an instant zero is a discontinuity, and a
        discontinuity here is a thump.

        Returns True only the first time, so the caller can say it once rather
        than every report cycle.
        """
        first = self._refused is None
        self._refused = reason
        if first:
            self.refusals += 1
        return first

    def allow(self) -> bool:
        """Send again. True only if this actually lifted a refusal."""
        if self._refused is None:
            return False
        self._refused = None
        return True

    @property
    def refused(self) -> str | None:
        """Why nothing is being sent, or None if it is."""
        return self._refused

    @property
    def running(self) -> bool:
        return self._stream is not None and not self._suspended

    @property
    def dac_clock_hz(self) -> float | None:
        """The rate the endpoint is consuming at, off PortAudio's own clock.

        None until there are two callbacks to subtract, and None if the host
        API does not fill `outputBufferDacTime` - both of which mean "no
        reading", never "zero", because a zero here would be read as a dead
        card by something downstream.

        **Not the same number as the delivery rate the watchdog reads, and
        that is the entire point of it.** The delivery rate is frames this
        process handed over per wall-clock second, which falls when the app
        is late whatever the card is doing. This falls only when the card
        itself slows down.
        """
        if self.dac_seconds <= 0.0 or self.dac_frames <= 0:
            return None
        return self.dac_frames / self.dac_seconds

    def explain(self) -> list[dict]:
        """Every number behind the last block rendered, per effect.

        Wired through from the mix so that a driver who felt something odd can
        be answered rather than guessed at. Safe to call from any thread: it
        reads arrays the callback writes and builds its own output.
        """
        return self._mix.explain()

    def describe(self) -> str:
        if self.error:
            return self.error
        if self._refused is not None:
            return (f"The transducer is open but nothing is being sent to "
                    f"it: {self._refused}")
        if not self.running:
            return "The transducer is not running."
        limited = self._mix.limited_blocks
        note = f", {limited} blocks limited" if limited else ""
        # The negotiated terms, not the requested ones - see `_open`.
        route = f" [{self.facts.describe()}]" if self.facts else ""
        return (f"Transducer on {self._device}, {self.callbacks} blocks"
                f"{note}.{route}")

    def recover(self) -> bool:
        """Close and reopen the stream in place, because the endpoint wedged.

        The failure this answers is chronic and hardware-level: the ButtKicker
        USB endpoint periodically enters a state where it accepts every sample
        and renders none - Windows shows it healthy, the meter shows nothing,
        and on the worst days only a reboot brings it back. The health check
        can SEE this (loud in, silence out); until now all it could do was
        write a log line the driver cannot read inside a headset.

        Reopening the WASAPI client is the strongest un-wedge available from
        user space. If the device is too far gone even for that, the reopen
        fails or the meter stays silent, the count says so, and the log can
        then say "power-cycle it" with evidence rather than guessing.

        **"Recovered" means the stream that was working came back, not that
        a stream came back.** A reopen that lands on a different host API, a
        different rate or a different card is a different output, and
        counting it as a fix is how the app would come to believe it had
        repaired the very thing it had just broken. It returns False, so the
        ladder escalates - and `_open` has already written down what changed.

        Thread-safe: called from the health check's own thread, same lock as
        `suspend`/`resume`. **The enumeration lock is taken first, and the
        order is the point.** The settings picker takes the enumeration lock
        and then calls `suspend` - this engine's lock - on every sustained
        stream; `_open` needs the enumeration lock from inside ours. Same two
        locks, opposite order, two threads: the app stops for good, and the
        likeliest collision is the driver opening the settings screen in the
        same seconds this fires. Unregistering first would not close it -
        `_reinitialise` snapshots the holder list before we could leave it -
        so the order is made consistent instead, and the nested acquisitions
        inside `open_output` are re-entrant on this thread.
        """
        with audio_devices.enumeration_lock():
            with self._lock:
                if self._stopped or self._suspended or self._stream is None:
                    return False
                self._close()
                self._fade = 0.0
                opened = self._open()
                changed = self.last_open_changed
        self.recoveries += 1
        if opened and not changed:
            log("haptics").warning(
                "the transducer stream was reopened in place (recovery %d) - "
                "the endpoint had wedged", self.recoveries)
        return opened and not changed

    def rebuild(self) -> bool | None:
        """Tear everything down and reacquire the card from scratch.

        The escalation past `recover`, for the wedge that reopening in place
        does not fix - the race of 16 Aug 2026 dropped at 20:32 and stayed
        dropped for twenty minutes because a reopen was all the app had.
        `recover` closes and reopens against whatever the machine looked like
        a moment ago; this unhooks the stream entirely, waits out the
        device-side renegotiation, and reopens by name against a device list
        rebuilt from nothing - `open_output` re-enumerates for a strict named
        open and walks WASAPI shared, then MME, then DirectSound, so a card
        whose index moved in the drop is found again by its name.

        Allowed to run with no stream open, because the attempt before this
        one may have failed to open anything - that is exactly the state a
        retry exists for. Same lock discipline as `recover`, enumeration lock
        first. Returns None rather than False when the driver's own stop or
        a suspend cut it short: an aborted attempt is not a failed one, and
        counting it against the retry cap would spend a rebuild on nothing.
        """
        with self._lock:
            if self._stopped or self._suspended:
                return None
            self._close()
            self._fade = 0.0
        # Off the register while standing back: a settings-screen enumeration
        # during the settle would otherwise resume - and reopen - the stream
        # this rebuild is about to open itself. `_open` re-registers.
        audio_devices.unregister_sustained(self)
        time.sleep(REBUILD_SETTLE_S)
        try:
            with audio_devices.enumeration_lock():
                with self._lock:
                    if self._stopped or self._suspended:
                        return None
                    opened = self._open()
                    changed = self.last_open_changed
        finally:
            # **Back on the register whatever happened, unless the driver
            # stopped us.** `_open` re-registers on success and only on
            # success, so a rebuild that failed to open used to leave the
            # engine off the sustained list for good: `recover` then refused
            # because there was no stream, `resume` refused because it was
            # not suspended, and no later device rebuild could reach it. The
            # engine was unrecoverable for the rest of the session, by
            # bookkeeping rather than by anything the hardware did.
            if not self._stopped:
                audio_devices.register_sustained(self)
        self.rebuilds += 1
        if opened and not changed:
            log("haptics").warning(
                "the transducer stream was torn down and rebuilt from a fresh "
                "device list (rebuild %d) - reopening in place had not "
                "cleared the wedge", self.rebuilds)
        return opened and not changed

    # ------------------------------------------------------------ lifecycle

    def start(self) -> bool:
        _quicken_the_gil()
        with self._lock:
            self._stopped = False
            return self._open()

    def stop(self) -> None:
        # The flag goes up under the lock BEFORE unregistering. Without it,
        # a recovery that won the lock race could reopen and re-register the
        # stream after this unregistered it - and the next device rebuild
        # would then resurrect a transducer the driver had stopped.
        with self._lock:
            self._stopped = True
            self._close()
        audio_devices.unregister_sustained(self)

    def _open(self) -> bool:
        """Open, then check that what opened is what was asked for.

        **The open succeeding is not the same as the stream being right, and
        until 17 Aug 2026 this logged only the name it had asked for.** The
        synthesiser generates at a fixed 48 kHz; if the stream is clocked at
        anything else every tone in the mix is transposed by that ratio, and
        the amplifier passes 25-160 Hz, so even a modest shift walks the road
        bed and the engine tone out of the band the rig can deliver. That is
        precisely "the vibrations were all wrong", and nothing here could
        name it.

        **A stream at the wrong rate is refused rather than followed.** The
        synthesiser could be rebuilt at whatever rate came back - `HapticMix`
        takes its rate as an argument - and that was the tempting option. It
        is the wrong one, for three reasons, and they are the same reason
        `strict=True` is on the open below:

        * Every band in `transducer.BAND_PLAN` was placed against a response
          measured on this rig at this rate, and every gain is a fraction of
          a reference tone somebody actually felt. A rate the app has never
          rendered at is an untested output into a 150 W piston.
        * Rebuilding the mix mid-race throws away the phase and smoothing
          state of every voice, and a discontinuity here is a thump.
        * The driver's own verdict on the alternative: wrong output "is worse
          than not being on". Silence is the correct answer for a transducer
          that cannot be driven correctly, exactly as it is for one that is
          not connected.

        So a mismatch closes the stream, says why, and leaves the engine
        stopped - which puts the failure in front of the recovery ladder,
        where the next rung re-enumerates and may find a route that will take
        48 kHz.
        """
        if self._stream is not None:
            return True
        try:
            # Shared, not exclusive. Exclusive opens on this transducer,
            # reports a plausible latency, and renders nothing at all - see
            # `audio_devices.open_exclusive_output`.
            stream = audio_devices.open_output(
                transducer.SAMPLE_RATE,
                channels=transducer.CHANNELS,
                dtype="float32",
                device=self._device,
                blocksize=BLOCKSIZE,
                callback=self._callback,
                # **Never the default card.** Without this, a ButtKicker that
                # is switched off sends the road bed to whatever Windows calls
                # default - which here is the driver's headphones, so he would
                # race with 40 Hz in his ears instead of under him. Silence is
                # the right output for a transducer that is not connected.
                strict=True)
        except Exception as exc:                            # noqa: BLE001
            self.error = (f"The transducer would not open on "
                          f"{self._device}: {exc}")
            log("haptics").warning(self.error)
            self._stream = None
            return False

        facts = audio_devices.describe_stream(
            stream, samplerate=transducer.SAMPLE_RATE, blocksize=BLOCKSIZE,
            channels=transducer.CHANNELS, dtype="float32",
            device=self._device)
        wrong = facts.mismatches()
        if wrong:
            self.format_refusals += 1
            self.error = (
                f"The transducer opened on {self._device} but not on the "
                f"terms it was asked for - {'; '.join(wrong)}. The mix is "
                f"generated at {transducer.SAMPLE_RATE} Hz and the amplifier "
                f"passes {transducer.BAND_LOW_HZ:.0f}-"
                f"{transducer.BAND_HIGH_HZ:.0f} Hz, so playing it through "
                f"this stream would transpose every effect out of the band "
                f"the rig can deliver. Refusing it: got {facts.describe()}.")
            log("haptics").error(self.error)
            self._stream = stream
            self._close()
            return False

        self._stream = stream
        self.error = None
        self._suspended = False
        self.facts = facts
        # PortAudio's stream clock starts again with the stream, so the
        # origin has to as well or the DAC rate is measured across a gap
        # that contains a teardown and a one-second settle.
        self._dac_first = 0.0
        self.dac_seconds = 0.0
        self.dac_frames = 0
        changed = facts.differences(self.baseline)
        self.last_open_changed = tuple(changed)
        if self.baseline is None:
            self.baseline = facts
        audio_devices.register_sustained(self)
        log("haptics").info("transducer running on %s - %s",
                            self._device, facts.describe())
        if changed:
            self.route_changes += 1
            # **Loud, because this is the case the record could not see.** A
            # stream on a different host API is a different path to the
            # hardware with different properties: DirectSound buffers and
            # discards, WDM-KS renders underneath the Windows audio engine
            # where the endpoint meter cannot see it at all. Either would
            # produce the contradiction of 17 Aug - a meter reading silence
            # while the seat works.
            log("haptics").error(
                "the transducer reopened onto a DIFFERENT stream from the "
                "one that was working: %s. This is not the configuration "
                "that was rendering into the seat, so it is not a recovery, "
                "and the endpoint meter may no longer be watching what the "
                "stream is feeding.", "; ".join(changed))
        return True

    def _close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is None:
            return
        try:
            stream.stop()
            stream.close()
        except Exception as exc:                            # noqa: BLE001
            log("haptics").debug("closing the transducer raised: %s", exc)

    # ------------------------------- surviving a device list being rebuilt

    def suspend(self) -> None:
        """Called by `audio_devices` before it tears PortAudio down."""
        with self._lock:
            if self._stream is None:
                return
            self._suspended = True
            self._close()

    def resume(self) -> None:
        """Called after. The card may be a different index now, or gone."""
        with self._lock:
            if not self._suspended or self._stopped:
                return
            self._suspended = False
            self._fade = 0.0
            if not self._open():
                # Loud on purpose: the driver cannot see that the haptics
                # stopped, and this is the one place it could happen without
                # anything else going wrong.
                log("haptics").error(
                    "the transducer did not come back after the audio devices "
                    "were rebuilt. There will be no haptics until the session "
                    "is restarted.")

    # ------------------------------------------------------- the hot thread

    def _callback(self, outdata, frames, time_info, status) -> None:
        """PortAudio's thread. No allocation, no logging, no locks.

        `status` is deliberately not LOGGED - writing to a file from here is
        exactly the blocking call that causes the underrun it would be
        reporting - but it is COUNTED.

        **`status.output_underflow` is a dead instrument on the host API this
        engine runs on, and the whole disambiguation was built on it.**
        Measured 22 Aug 2026: a WASAPI callback deliberately starved to a
        third of nominal - 15960 frames a second against 48000 - reported
        `output_underflow` **zero** times. The same starvation on MME
        reported it 240 times and on DirectSound 660. PortAudio's WASAPI
        backend simply never sets the flag here.

        So the reasoning it was added for - "a low clock with no underruns
        is a card genuinely consuming slower" - could only ever reach one
        answer on WASAPI, and it was the wrong one. It is still counted,
        because it is free and because MME and DirectSound are real fallback
        routes where it does work, but nothing may decide anything from a
        zero on WASAPI. `dac_seconds` below is the instrument that replaced
        it.
        """
        self.callbacks += 1
        # `status` is falsy on a healthy block, so the common path is one
        # bool test and no attribute access at all.
        if status:
            self.status_blocks += 1
            if status.output_underflow:
                self.underflows += 1

        # **The device's own clock, not ours.** `frames / wall seconds`
        # measures what this process managed to hand over, which is a
        # statement about the app's scheduling and was read for ten days as
        # a statement about the card. `outputBufferDacTime` is PortAudio's
        # stream clock: the two together separate "we are starving a healthy
        # endpoint" from "the endpoint itself has slowed", which is the
        # question the whole recovery ladder turns on and could not ask.
        #
        # Two floats and a subtraction, on a thread that must not block.
        # Wrapped because `time_info` is a C struct whose fields are not
        # promised by every host API, and a missing attribute here must cost
        # the diagnosis, never the audio.
        try:
            dac = time_info.outputBufferDacTime
        except AttributeError:                               # pragma: no cover
            dac = 0.0
        if dac:
            if self._dac_first == 0.0:
                self._dac_first = dac
            else:
                self.dac_seconds = dac - self._dac_first
                self.dac_frames = self.frames
        # Frames as well as blocks. Divided by wall-clock seconds upstairs
        # this is a direct measurement of the rate the card is actually
        # consuming at, which is the one number that separates "PortAudio
        # chose a longer buffer" from "the clock moved and every tone with
        # it". Both look identical in a block count.
        self.frames += frames
        n = min(frames, MAX_BLOCK)

        # **The watchdog, and the reason it lives here.** If the telemetry
        # side has stopped - or died - nothing else in this process is still
        # running to notice. The sound card is, and it notices by asking for
        # another block. Counting those is the only clock that survives
        # everything upstream failing.
        if self._generation != self._seen_generation:
            self._seen_generation = self._generation
            self._stale_frames = 0
            self._live[:] = self._wanted
        else:
            self._stale_frames += n

        stale_for = self._stale_frames / transducer.SAMPLE_RATE
        step = n / (FADE_S * transducer.SAMPLE_RATE)
        # A refusal leaves by the same door as a dead feed, because it is the
        # same statement: there is nothing correct to send. `_refused` is a
        # plain attribute read, like every other value this callback takes
        # from outside - no lock, and one block of staleness costs nothing.
        if stale_for > STALE_S or self._refused is not None:
            if self._fade > 0.0:
                self._fade = max(0.0, self._fade - step)
                if self._fade == 0.0:
                    self.faded_out += 1
        else:
            self._fade = min(1.0, self._fade + step)

        if self._fade <= 0.0:
            outdata[:] = 0.0
            return

        mono = self._mix.render(self._live, n)
        if self._fade < 1.0:
            np.multiply(mono, self._fade, out=mono)
        synth.to_stereo(mono, self._stereo, n)
        outdata[:n] = self._stereo[:n]
        if frames > n:
            outdata[n:] = 0.0


class TransducerWatchdog:
    """Decides when the endpoint's numbers stop being believable, and what
    to do about it.

    Built after the race of 16 Aug 2026. At 20:32 the endpoint meter froze at
    exactly 0.054 and read exactly 0.054 on every check for the remaining
    twenty minutes, while the engine's own rendered peak went on varying
    normally - and the wedge detector never fired, because it was looking for
    "loud in, NOTHING out", and a stale 0.054 is not nothing. A meter on a
    live signal jitters; the same float five checks running is a dead meter,
    and a dead meter is wedge evidence of exactly the same rank as silence.

    **0.054 is not a special number and nothing here should be tuned to it.**
    It read as one for a while, because it was also the first reading of the
    session of 17 Aug - which then went on varying normally, so it was a live
    value that day. Two things settle it: that session's own freeze latched
    at 0.163, not 0.054, and the log holds live readings below it (0.038,
    0.046, 0.051). It is neither a quantisation floor nor a default the
    meter falls back to; it is whatever the endpoint's last real peak
    happened to be when the pump stopped. The detector is right to key on
    repetition rather than on any particular value.

    The block cadence dropping and staying down - 100/s to 64/s that night,
    at the same moment the meter froze - is the endpoint's audio pump being
    rebuilt, a device-side event. It is not proof on its own, so it
    corroborates the meter verdict rather than triggering on its own.

    **And the cadence alone cannot say WHAT was rebuilt**, which is why the
    frame clock is fed in beside it. 100 blocks a second becoming 64 is
    either a longer buffer at the same rate - harmless - or the same buffer
    at a lower rate, which transposes every effect in the mix and is exactly
    what "the vibrations were all wrong" would feel like. Frames per second
    is the same number the synthesiser generates at when nothing has moved,
    so the two hypotheses stop being indistinguishable the moment it is
    written down.

    This class holds no threads and touches no audio. Observations arrive
    from two threads - cadence from the report cycle, meter readings from the
    health check's worker - so the state sits behind one lock, and the
    controller reads the plan and does the acting.
    """

    # How many consecutive bit-identical readings convict the meter, judged
    # only on polls taken while the engine was loud. Polls arrive every ten
    # seconds, so five is a verdict about forty seconds after the freeze -
    # and four when the cadence drop corroborates it. Any slower is a race
    # lost; any faster starts trusting two coincidentally equal floats.
    STALE_POLLS = 5
    STALE_POLLS_CORROBORATED = 4
    # "The same float". The frozen meter repeats bit-identically; a live one
    # moves by whole percent between ten-second polls.
    STALE_EPSILON = 1e-6
    # An identical reading only convicts the meter if what WE rendered varied
    # across the same polls. A dead-steady state would give a working meter
    # every reason to repeat itself.
    RENDERED_SPREAD = 0.02
    # "Alive" has its own bar: this many consecutive readings, all mutually
    # distinct. One changed reading proves nothing - an endpoint that wedges
    # across a pump rebuild comes back frozen at a NEW float, and calling
    # that first reading alive is how a recovery gets claimed that never
    # happened. Three mutually-distinct readings also refuse an A,B,A
    # ping-pong, which a pairwise-adjacent test would wave through.
    CONFIRM_POLLS = 3
    # How many distinct repeated values are tracked at once. A frozen meter
    # repeats one; a re-wedge after a pump rebuild adds a second; a
    # ping-ponging one alternates two. Four is paranoia priced at nothing.
    STALE_CANDIDATES = 4
    # The cadence baseline is the median of this many report cycles; a drop
    # is real when it is this far below baseline for this many consecutive
    # cycles - two ten-second cycles, so more than ten seconds sustained.
    CADENCE_BASELINE_CYCLES = 3
    CADENCE_DROP_FRACTION = 0.20
    CADENCE_LOW_CYCLES = 2
    # How far the measured frame clock may sit from the rate the synthesiser
    # generates at before it is a different rate rather than scheduling
    # jitter. A report cycle is ten seconds, so a few late blocks are worth
    # well under a percent; the smallest interesting real shift - 48000
    # against 44100 - is 8%.
    CLOCK_TOLERANCE = 0.04
    # How many consecutive cycles must read off-rate before the verdict is
    # latched. **Two, because the verdict now silences the seat**, and a
    # recovery is itself a hole in the frame clock: `rebuild` stands back for
    # `REBUILD_SETTLE_S` and then reopens, so the cycle containing one reads
    # low - 27059 Hz on 17 Aug 2026, against a stream that was really at
    # 30611 - purely because the stream was shut for part of it. One cycle
    # was enough when the only cost was a log line. It is not enough now.
    # Clearing stays immediate: one good reading is proof it is being pulled
    # correctly, and there is no reason to withhold a working transducer.
    CLOCK_SUSPECT_CYCLES = 2
    # How long a cadence drop stays usable as corroboration for the meter.
    CORROBORATION_WINDOW_S = 120.0
    # Wedge evidence returning within this after a recovery means the fix did
    # not hold - the "came and went" flapping - and the next rung is tried.
    # Evidence after a longer clean spell is a fresh episode from the bottom.
    FLAP_WINDOW_S = 180.0
    # Full rebuilds are capped, with a pause before each retry so a device
    # that needs a moment gets one and a device that is gone is not hammered.
    MAX_REBUILDS = 3
    REBUILD_BACKOFF_S = (0.0, 30.0, 90.0)
    # **How long the stand-down lasts before the ladder is allowed to try
    # again from the bottom, and it used to last forever.**
    #
    # `degraded` was set in one place and cleared in none: `plan_recovery`
    # returned "stand-down" on its first line for the rest of the process,
    # and the only reset of the attempt counters - `settled` - was reachable
    # only through the endpoint meter, which the controller deliberately
    # stops polling once the output is refused. So refusal and recovery were
    # mutually exclusive by construction, and the one state that needed the
    # ladder most was the one state the ladder could not run in.
    #
    # That is why the seat never came back without a restart, and it is a
    # separate fault from the starvation that put it there: fixing the
    # starvation alone would still have left this latched for any future
    # cause. The wind simulator, on the same machine and the same USB tree,
    # retries without a cap and recovers by itself - the difference between
    # the two subsystems is this constant existing.
    #
    # Five minutes: long enough that a genuinely dead endpoint is not
    # hammered through a race, short enough that a transient is not paid for
    # in a whole session of silence. The driver notice stays one-shot; it is
    # the repair that repeats, not the announcement.
    STAND_DOWN_RETRY_S = 300.0

    def __init__(self) -> None:
        self._guard = threading.Lock()
        # The last few readings, and the short list of values the meter has
        # repeated. Staleness is judged per repeated VALUE rather than only
        # against the immediately previous reading, so a meter that
        # ping-pongs between two frozen numbers is convicted rather than
        # endlessly resetting the count.
        self._recent: deque = deque(maxlen=self.CONFIRM_POLLS)
        self._candidates: list[dict] = []
        self._matched: dict | None = None
        self._matched_needed = self.STALE_POLLS
        self._matched_first = False
        # The block cadence, and the frame clock beside it.
        self._last_blocks: int | None = None
        self._last_blocks_at: float | None = None
        self._last_frames: int | None = None
        self._baseline_rates: list[float] = []
        self._baseline: float | None = None
        self._low_cycles = 0
        self._cadence_dropped_at: float | None = None
        self.clock_hz: float | None = None
        self.clock_suspect = False
        self._clock_off_cycles = 0
        # Why the app cannot vouch for its own verdict, if it cannot. Each
        # entry is one honest reason - an unreadable meter, two endpoints of
        # one name, the metered endpoint changing under us, the stream
        # reopening onto different terms. Any of them turns the stand-down
        # notice from an assertion into an admission.
        self._doubts: list[str] = []
        self._last_endpoint: str | None = None
        # The recovery ladder.
        self._reopens = 0
        self._rebuilds = 0
        self._last_attempt_at: float | None = None
        self._rebuild_unconfirmed = False
        self._recovered_notice_sent = False
        self.degraded = False
        # When the stand-down began, so `plan_recovery` can re-arm rather
        # than latch. None means "not standing down".
        self._degraded_at: float | None = None
        self._notice: tuple[str, str] | None = None
        # **Has the ladder ever been exhausted?** Latched for the life of
        # the watchdog and never cleared by a re-arm, unlike `degraded`,
        # which now comes and goes as the ladder stands back up. It gates
        # the driver notice - see `_degrade` - and it is the honest thing
        # for a caller to ask, because "is it standing down right now" is a
        # question whose answer flickers.
        self.stood_down = False

    # ------------------------------------------------------- what it watches

    def judge(self, rendered: float, heard: float, now: float) -> str:
        """One meter reading, taken while the engine was loud.

        Three verdicts, because "not stale" and "alive" are not the same
        claim:

        * "stale" - this value has repeated often enough, against a varying
          rendered signal, to convict the meter. Wedge evidence.
        * "live" - the last few readings are all mutually distinct. The
          meter is genuinely moving; only this earns `settled`.
        * "unsettled" - neither yet. In particular, the FIRST reading of a
          new value is never "live": a wedge that survives a pump rebuild
          comes back frozen at a new float, and one changed number is not a
          recovery.

        Only polls actually taken count. The controller never asks the meter
        while the engine is quiet, so a parked car cannot age this - a run of
        identical readings pauses over the quiet spell and resumes with the
        next loud poll, because the meter is still frozen either way.
        """
        with self._guard:
            self._recent.append(heard)
            match = None
            for candidate in self._candidates:
                if abs(heard - candidate["value"]) <= self.STALE_EPSILON:
                    match = candidate
                    break
            if match is None:
                match = {"value": heard, "count": 0,
                         "rendered_low": rendered, "rendered_high": rendered}
            else:
                self._candidates.remove(match)
            self._candidates.insert(0, match)
            del self._candidates[self.STALE_CANDIDATES:]
            match["count"] += 1
            match["rendered_low"] = min(match["rendered_low"], rendered)
            match["rendered_high"] = max(match["rendered_high"], rendered)
            needed = (self.STALE_POLLS_CORROBORATED
                      if self._corroborated(now) else self.STALE_POLLS)
            self._matched, self._matched_needed = match, needed
            varied = (match["rendered_high"]
                      - match["rendered_low"]) >= self.RENDERED_SPREAD
            if match["count"] >= needed and varied:
                # The first conviction of this value is latched on the
                # candidate itself, not derived from count == needed: the
                # cadence corroboration can lower `needed` from 5 to 4
                # between polls 4 and 5, and the convicting poll then walks
                # past the equality without ever being "first".
                self._matched_first = not match.get("reported", False)
                match["reported"] = True
                return "stale"
            readings = list(self._recent)
            if (len(readings) == self.CONFIRM_POLLS
                    and all(abs(a - b) > self.STALE_EPSILON
                            for i, a in enumerate(readings)
                            for b in readings[i + 1:])):
                return "live"
            return "unsettled"

    def stale_details(self) -> dict:
        """The run behind the last verdict, for the line that reports it."""
        with self._guard:
            match = self._matched or {"value": None, "count": 0,
                                      "rendered_low": 0.0,
                                      "rendered_high": 0.0}
            return {**match, "needed": self._matched_needed,
                    "first": self._matched_first}

    def silent(self, now: float) -> None:
        """The meter read ~nothing. A different wedge; the frozen runs are
        over - counting across the two failures would blur both."""
        del now
        with self._guard:
            self._recent.clear()
            self._candidates.clear()
            self._matched = None

    def settled(self, now: float) -> None:
        """A live, varying reading. Closes out any recovery in progress.

        A rebuild is only claimed to have worked when the meter is seen alive
        afterwards - the stream opening proves nothing, because opening is
        the one thing a wedged endpoint still does perfectly.
        """
        with self._guard:
            if self._rebuild_unconfirmed:
                self._rebuild_unconfirmed = False
                if not self._recovered_notice_sent:
                    self._recovered_notice_sent = True
                    self._notice = (
                        "the haptics endpoint dropped mid-session and came "
                        "back after a full rebuild of the audio device. The "
                        "device side is not healthy - after the race, check "
                        "the amplifier and the ButtKicker's USB connection.",
                        "Haptics dropped and are back after a device rebuild. "
                        "Check the amp after the race.")
            if ((self._reopens or self._rebuilds)
                    and self._last_attempt_at is not None
                    and now - self._last_attempt_at > self.FLAP_WINDOW_S):
                self._reopens = 0
                self._rebuilds = 0
                self._last_attempt_at = None

    def note_cadence(self, blocks: int, now: float,
                     frames: int | None = None) -> None:
        """The engine's lifetime block count, once per report cycle.

        The callback rate is the sound card's own clock, and a sustained fall
        is the endpoint's audio pump being rebuilt under the stream - seen
        the night of the drop as 100/s falling to 64/s at the same moment
        the meter froze. Named in the log, and kept as corroboration; it does
        not trigger a recovery by itself.

        `frames` is the lifetime frame count from the same callback, and it
        is what makes the cadence line mean something. Divided by the same
        elapsed seconds it is the rate the card is really consuming at, so a
        block cadence that halves while the frame clock holds is a longer
        buffer, and one that halves with it is a transposed mix. Optional
        only so that a caller written before it existed still works.
        """
        with self._guard:
            last, last_at = self._last_blocks, self._last_blocks_at
            last_frames = self._last_frames
            self._last_blocks, self._last_blocks_at = blocks, now
            self._last_frames = frames
            if last is None or last_at is None or now <= last_at \
                    or blocks < last:
                # First cycle, or the counter went backwards because the
                # engine was replaced under us. No rate to read either way.
                return
            elapsed = now - last_at
            rate = (blocks - last) / elapsed
            clock = None
            if (frames is not None and last_frames is not None
                    and frames >= last_frames):
                clock = (frames - last_frames) / elapsed
                self.clock_hz = clock
                self._judge_clock(clock)
            if self._baseline is None:
                self._baseline_rates.append(rate)
                if len(self._baseline_rates) >= self.CADENCE_BASELINE_CYCLES:
                    ordered = sorted(self._baseline_rates)
                    self._baseline = ordered[len(ordered) // 2]
                return
            if rate < self._baseline * (1.0 - self.CADENCE_DROP_FRACTION):
                self._low_cycles += 1
                if self._low_cycles >= self.CADENCE_LOW_CYCLES:
                    self._cadence_dropped_at = now
                    log("haptics").warning(
                        "the transducer's callback cadence fell from about "
                        "%.0f to about %.0f blocks per second and stayed "
                        "there. That is the endpoint's audio pump being "
                        "rebuilt - a device-side event, not an app fault - "
                        "so the endpoint meter is now under suspicion of "
                        "wedging.%s", self._baseline, rate,
                        self._clock_verdict(clock))
                    # The new rate is the new normal: a rebuilt pump
                    # renegotiates its block size, and holding the old
                    # baseline would repeat this warning to the flag.
                    self._baseline = rate
                    self._low_cycles = 0
            else:
                self._low_cycles = 0

    def _clock_verdict(self, clock: float | None) -> str:
        """The sentence that tells a longer buffer from a slower clock."""
        if clock is None:
            return (" The frame clock was not recorded, so this cannot say "
                    "whether the block size changed or the sample rate did.")
        nominal = float(transducer.SAMPLE_RATE)
        drift = abs(clock - nominal) / nominal
        if drift <= self.CLOCK_TOLERANCE:
            return (f" The frame clock held at about {clock:.0f} Hz against "
                    f"{nominal:.0f}, so this is a longer buffer and not a "
                    f"changed sample rate - the mix is still in tune.")
        return (f" The frame clock moved with it, to about {clock:.0f} Hz "
                f"against the {nominal:.0f} the mix is generated at, so "
                f"every effect is transposed by {clock / nominal:.2f}x and "
                f"the road bed no longer lands where the amplifier can pass "
                f"it.")

    def _judge_clock(self, clock: float) -> None:
        """Latch and name a frame clock that is not the one we generate for.

        Separate from the cadence drop because the two do not have to happen
        together: a stream can be pulled at the wrong rate from the moment it
        opens, with a perfectly steady block cadence, and that is the case
        where the driver feels a working transducer producing the wrong
        thing - which he has told us is worse than none.
        """
        nominal = float(transducer.SAMPLE_RATE)
        off = abs(clock - nominal) / nominal > self.CLOCK_TOLERANCE
        self._clock_off_cycles = self._clock_off_cycles + 1 if off else 0
        if off and not self.clock_suspect:
            if self._clock_off_cycles < self.CLOCK_SUSPECT_CYCLES:
                return
            self.clock_suspect = True
            self._doubt(
                f"the stream is being pulled at about {clock:.0f} frames a "
                f"second against the {nominal:.0f} the mix is generated at")
            log("haptics").error(
                "the transducer's frame clock is about %.0f Hz but the mix "
                "is generated at %.0f Hz. Every effect is transposed by "
                "%.2fx - the road bed at %.0f Hz arrives at %.0f Hz - and "
                "the amplifier only passes %.0f-%.0f Hz. This is a stream "
                "that opened on terms the app does not render for.",
                clock, nominal, clock / nominal, 38.0, 38.0 * clock / nominal,
                transducer.BAND_LOW_HZ, transducer.BAND_HIGH_HZ)
        elif not off and self.clock_suspect:
            self.clock_suspect = False
            log("haptics").warning(
                "the transducer's frame clock is back at about %.0f Hz, "
                "which is what the mix is generated for.", clock)

    # --------------------------------------- what the app cannot vouch for

    def _doubt(self, reason: str) -> None:
        """Record one reason the meter's verdict may not be about the
        transducer. Not called under the guard by every caller, so it takes
        no lock of its own - the list is only ever appended to."""
        if reason not in self._doubts:
            self._doubts.append(reason)

    def unmeasurable(self, detail: str = "") -> None:
        """The meter could not be read at all.

        **Not a failure, and it must never run the ladder.** This is the
        module's oldest rule arriving where it was missing: `poll_briefly`
        answered `0.0` for an unopenable meter, the controller read that as
        "the card played nothing", and the driver was told through the
        headset that his haptics were gone on the strength of an instrument
        that was never there.
        """
        self._doubt("the endpoint meter could not be read"
                    + (f" ({detail})" if detail else ""))

    def note_endpoint(self, identity: str | None, matches: int) -> None:
        """Which endpoint the reading came from, and how many share its name.

        **Several endpoints of one name is no longer a doubt.** It was the
        strongest of them: the meter took the first match while PortAudio
        resolved the stream over its own list in its own order, so a silent
        reading could be a true statement about an endpoint nobody was
        feeding - which is how the app came to tell the driver his haptics
        were dead while he could feel them working.

        `endpoint_meter` now activates a meter on **every** endpoint of the
        name and reports the loudest. A peak from any of them means the audio
        is reaching the hardware; silence from all of them means it is
        reaching none. Neither claim depends on which instance the stream
        picked, so the ambiguity no longer has to be hedged - and the plain,
        confident verdict is available again in the case it was written for.

        The metered endpoint CHANGING between polls is still a doubt, and a
        different one: it means the set moved under us mid-session, which is
        a re-enumeration rather than an ambiguity.
        """
        with self._guard:
            if (identity is not None and self._last_endpoint is not None
                    and identity != self._last_endpoint and matches <= 1):
                # Only when there is one endpoint to be. With several, the
                # reported identity is simply whichever was loudest this
                # poll, and that moving is ordinary rather than suspicious.
                self._doubt("the endpoint being metered changed mid-session")
            if identity is not None:
                self._last_endpoint = identity

    def note_stream_changed(self, changed) -> None:
        """The stream reopened onto different terms - see `_open`."""
        if changed:
            self._doubt("the stream reopened onto different terms ("
                        + "; ".join(changed) + ")")

    @property
    def uncertain(self) -> bool:
        return bool(self._doubts)

    def doubts(self) -> tuple[str, ...]:
        return tuple(self._doubts)

    def corroborated(self, now: float) -> bool:
        """Whether a recent cadence drop backs the meter's verdict up."""
        with self._guard:
            return self._corroborated(now)

    def _corroborated(self, now: float) -> bool:
        return (self._cadence_dropped_at is not None
                and now - self._cadence_dropped_at
                <= self.CORROBORATION_WINDOW_S)

    # ------------------------------------------------------------ the ladder

    def plan_recovery(self, now: float) -> str:
        """The next rung, given fresh wedge evidence.

        "reopen" is `recover` - in place, the fix that has worked for an
        engine-level wedge. "rebuild" is the full teardown, for evidence that
        came back after a reopen. "wait" is a rebuild wanted but inside its
        backoff. "stand-down" is the ladder exhausted: nothing else to try
        from software, and the one driver notice says what to do instead.
        """
        with self._guard:
            if self.degraded:
                if (self._degraded_at is None
                        or now - self._degraded_at < self.STAND_DOWN_RETRY_S):
                    return "stand-down"
                # **Re-arm.** Standing down is a pause, not a verdict. The
                # endpoint may have been reset, replugged, or simply come
                # back; none of those events reach this process, so the only
                # way to find out is to try. Back to the bottom of the
                # ladder, counters cleared, notice not repeated.
                self.degraded = False
                self._degraded_at = None
                self._reopens = 0
                self._rebuilds = 0
                self._rebuild_unconfirmed = False
                log("haptics").info(
                    "standing back up after %.0f minutes: trying the "
                    "transducer again from the top of the ladder.",
                    self.STAND_DOWN_RETRY_S / 60.0)
            if self._reopens == 0:
                return "reopen"
            if self._rebuilds >= self.MAX_REBUILDS:
                self._degrade(now)
                return "stand-down"
            wait = self.REBUILD_BACKOFF_S[self._rebuilds]
            if (self._last_attempt_at is not None
                    and now - self._last_attempt_at < wait):
                return "wait"
            return "rebuild"

    def reopened(self, now: float) -> None:
        with self._guard:
            self._reopens += 1
            self._last_attempt_at = now

    def rebuilt(self, opened: bool, now: float) -> None:
        with self._guard:
            self._rebuilds += 1
            self._last_attempt_at = now
            if opened:
                # Opening proves nothing yet - `settled` confirms it, because
                # a wedged endpoint accepts a fresh stream as happily as a
                # working one.
                self._rebuild_unconfirmed = True
            elif self._rebuilds >= self.MAX_REBUILDS:
                self._degrade(now)

    def _degrade(self, now: float | None = None) -> None:
        """The ladder is spent. Say what is true, and only what is true.

        **The old line asserted "the haptics endpoint dropped and did not
        come back", and on 17 Aug 2026 it may have been false while it was
        being spoken.** The meter read silent for thirteen minutes; the
        driver, in the seat, felt the transducer working - badly, but
        working. One of those is wrong and the app cannot tell which, because
        the meter watches an endpoint resolved by friendly name and the
        stream is resolved separately, by PortAudio, in its own order.

        A confident wrong instruction is the worst thing this can produce
        under a helmet, and the driver has no way to check it mid-race. So
        the confident line survives only for the case the app can actually
        stand behind - one endpoint of that name, a meter it could read, and
        a stream still on the terms it opened with. The moment any of those
        is in doubt it says so instead, and hands him the one test he can do
        from the seat without looking at anything: whether he can feel it.
        """
        if self.degraded:
            return
        self.degraded = True
        # Stamped so `plan_recovery` can stand back up. Defaulted rather
        # than required so a caller that only wants the notice still
        # works; a stand-down with no stamp never re-arms, which is the
        # old behaviour and the safe direction to get it wrong in.
        self._degraded_at = now
        # **The repair repeats. The announcement does not.**
        #
        # `plan_recovery` now stands the ladder back up every
        # STAND_DOWN_RETRY_S, which is right - an endpoint that came back
        # deserves to be found. But each of those cycles ends here, and
        # without this the driver would be told the haptics are gone once
        # every five minutes for the rest of a two-hour race. That is the
        # fault 881e213 fixed in the other direction - "not 119 error
        # lines" - arriving back through a door that did not exist then.
        #
        # He is told once. If it is still true an hour later, telling him
        # again mid-corner does not help him and the post-session log has
        # every cycle in it either way.
        if self.stood_down:
            return
        self.stood_down = True
        attempts = (f"{self._reopens} reopen(s) and {self._rebuilds} full "
                    f"rebuild(s)")
        # **"I have stopped trying" was heard as "I have stopped sending".**
        # On 17 Aug 2026 it meant the recovery ladder and nothing else - the
        # engine went on feeding the piston for nineteen minutes afterwards -
        # and the driver spent that time wondering where the vibration was
        # coming from. The two facts are now stated separately, and which one
        # is true is read off `clock_suspect`, because that is exactly what
        # the controller refuses the output on.
        # Either way it hands him the one test he can run from the seat.
        sending = (
            "I am no longer sending to them either - what the card would "
            "play is transposed out of the band the amplifier passes - so "
            "there should be nothing to feel."
            if self.clock_suspect else
            "I am still sending to them, so if you can still feel them, "
            "ignore me.")
        if self._doubts:
            self._notice = (
                f"the haptics meter has read nothing since the drop and "
                f"{attempts} did not change it, so the app has stopped "
                f"trying - but it cannot prove the transducer is silent: "
                f"{'; '.join(self._doubts)}. If the seat is still doing "
                f"something, the reading is wrong rather than the rig, and "
                f"what is being felt is not what the meter is watching. "
                f"After the race: check the amplifier, and check whether "
                f"more than one endpoint on this machine is called by the "
                f"transducer's name.",
                "I have lost sight of the haptics rather than proved them "
                "dead. " + sending + " I have stopped trying to fix them; if "
                "they really are gone, the amp may be in protection.")
            return
        self._notice = (
            f"the haptics endpoint dropped and did not come back: "
            f"{attempts} later the meter is still dead, so the app has "
            f"stopped trying. The amplifier may be in protection - after the "
            f"race, power-cycle the amp, and restart the PC if the endpoint "
            f"still meters nothing.",
            "Haptics are out and I have stopped trying to fix them. "
            + sending + " The amp may be in protection - deal with it after "
            "the race.")

    def take_notice(self) -> tuple[str, str] | None:
        """The one driver notice, as (log line, spoken line). One-shot."""
        with self._guard:
            notice, self._notice = self._notice, None
            return notice
