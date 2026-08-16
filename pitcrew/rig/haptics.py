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

import threading
import time
from collections import deque

import numpy as np

from pitcrew.diagnostics import log
from pitcrew.engineer import audio_devices
from pitcrew.rig import synth, transducer

# The block PortAudio is asked for. Zero lets it choose, which it does better
# than we can - measured, forcing a small block bought nothing and slightly
# worsened the jitter tail.
BLOCKSIZE = 0
# The largest block we will be handed. Buffers are sized for this once, so a
# callback never allocates.
MAX_BLOCK = 8192

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
        self.faded_out = 0
        self.callbacks = 0
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

    @property
    def running(self) -> bool:
        return self._stream is not None and not self._suspended

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
        if not self.running:
            return "The transducer is not running."
        limited = self._mix.limited_blocks
        note = f", {limited} blocks limited" if limited else ""
        return (f"Transducer on {self._device}, {self.callbacks} blocks"
                f"{note}.")

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
        self.recoveries += 1
        if opened:
            log("haptics").warning(
                "the transducer stream was reopened in place (recovery %d) - "
                "the endpoint had wedged", self.recoveries)
        return opened

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
        with audio_devices.enumeration_lock():
            with self._lock:
                if self._stopped or self._suspended:
                    return None
                opened = self._open()
        self.rebuilds += 1
        if opened:
            log("haptics").warning(
                "the transducer stream was torn down and rebuilt from a fresh "
                "device list (rebuild %d) - reopening in place had not "
                "cleared the wedge", self.rebuilds)
        return opened

    # ------------------------------------------------------------ lifecycle

    def start(self) -> bool:
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
        if self._stream is not None:
            return True
        try:
            # Shared, not exclusive. Exclusive opens on this transducer,
            # reports a plausible latency, and renders nothing at all - see
            # `audio_devices.open_exclusive_output`.
            self._stream = audio_devices.open_output(
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
        self.error = None
        self._suspended = False
        audio_devices.register_sustained(self)
        log("haptics").info("transducer running on %s", self._device)
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

    def _callback(self, outdata, frames, _time, status) -> None:
        """PortAudio's thread. No allocation, no logging, no locks.

        `status` is deliberately not logged: writing to a file from here is
        exactly the blocking call that causes the underrun it would be
        reporting.
        """
        self.callbacks += 1
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
        if stale_for > STALE_S:
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

    The block cadence dropping and staying down - 100/s to 64/s that night,
    at the same moment the meter froze - is the endpoint's audio pump being
    rebuilt, a device-side event. It is not proof on its own, so it
    corroborates the meter verdict rather than triggering on its own.

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
        # The block cadence.
        self._last_blocks: int | None = None
        self._last_blocks_at: float | None = None
        self._baseline_rates: list[float] = []
        self._baseline: float | None = None
        self._low_cycles = 0
        self._cadence_dropped_at: float | None = None
        # The recovery ladder.
        self._reopens = 0
        self._rebuilds = 0
        self._last_attempt_at: float | None = None
        self._rebuild_unconfirmed = False
        self._recovered_notice_sent = False
        self.degraded = False
        self._notice: tuple[str, str] | None = None

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

    def note_cadence(self, blocks: int, now: float) -> None:
        """The engine's lifetime block count, once per report cycle.

        The callback rate is the sound card's own clock, and a sustained fall
        is the endpoint's audio pump being rebuilt under the stream - seen
        the night of the drop as 100/s falling to 64/s at the same moment
        the meter froze. Named in the log, and kept as corroboration; it does
        not trigger a recovery by itself.
        """
        with self._guard:
            last, last_at = self._last_blocks, self._last_blocks_at
            self._last_blocks, self._last_blocks_at = blocks, now
            if last is None or last_at is None or now <= last_at \
                    or blocks < last:
                # First cycle, or the counter went backwards because the
                # engine was replaced under us. No rate to read either way.
                return
            rate = (blocks - last) / (now - last_at)
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
                        "wedging.", self._baseline, rate)
                    # The new rate is the new normal: a rebuilt pump
                    # renegotiates its block size, and holding the old
                    # baseline would repeat this warning to the flag.
                    self._baseline = rate
                    self._low_cycles = 0
            else:
                self._low_cycles = 0

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
                return "stand-down"
            if self._reopens == 0:
                return "reopen"
            if self._rebuilds >= self.MAX_REBUILDS:
                self._degrade()
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
                self._degrade()

    def _degrade(self) -> None:
        if self.degraded:
            return
        self.degraded = True
        self._notice = (
            f"the haptics endpoint dropped and did not come back: "
            f"{self._reopens} reopen(s) and {self._rebuilds} full rebuild(s) "
            f"later the meter is still dead, so the app has stopped trying. "
            f"The amplifier may be in protection - after the race, "
            f"power-cycle the amp, and restart the PC if the endpoint still "
            f"meters nothing.",
            "Haptics are out and I have stopped trying to bring them back. "
            "The amp may be in protection - deal with it after the race.")

    def take_notice(self) -> tuple[str, str] | None:
        """The one driver notice, as (log line, spoken line). One-shot."""
        with self._guard:
            notice, self._notice = self._notice, None
            return notice
