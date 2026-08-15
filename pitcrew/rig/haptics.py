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
        self._lock = threading.Lock()
        self._suspended = False
        self.error: str | None = None
        self.faded_out = 0
        self.callbacks = 0

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

    # ------------------------------------------------------------ lifecycle

    def start(self) -> bool:
        with self._lock:
            return self._open()

    def stop(self) -> None:
        audio_devices.unregister_sustained(self)
        with self._lock:
            self._close()

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
            if not self._suspended:
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
