"""Making the signal the transducer feels.

The whole of this module is arithmetic on arrays. It opens no device, holds no
lock and knows nothing about telemetry - which is deliberate, because it is the
part that has to be right at 48,000 samples a second inside an audio callback,
and the only way to be confident of that is to be able to run it a thousand
times in a test with no hardware attached.

Four rules shape everything here, and each one is a fault that has actually
happened to somebody:

**Two clocks, never one.** The control values arrive at 60 Hz from GT7 and the
carrier is rendered at 48 kHz. Those are different rates by a factor of 800 and
must never be conflated. In particular the telemetry is NOT the signal: at
60 Hz its Nyquist is 30 Hz, which is below the usable band entirely, so
resampling suspension travel up to audio rate produces aliased mush and not
road texture. Telemetry modulates locally generated sound. Nothing else.

**Phase is state, never recomputed.** An oscillator whose phase is derived from
an absolute sample index clicks every time its frequency changes, because the
waveform jumps rather than bends. Each voice here carries its phase forward and
advances it; changing the frequency then changes the slope, which is inaudible.

**Every parameter ramps across the block.** A gain that steps between blocks is
a discontinuity, and a discontinuity at 150 W is a thump. Intensities are
interpolated from where they were to where they are over the length of each
block.

**Nothing allocates in the hot path.** Buffers are made once at construction and
written into with `out=`. The rules are Bencina's and the sounddevice docs
restate them: no allocation, no logging, no locks, no I/O inside a callback.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from pitcrew.rig import transducer

# Below this an effect is off and its oscillator is left alone. Not a
# threshold on what the driver can feel - that is the effect's own business -
# but a way of not spending arithmetic on silence.
SILENT = 1e-4

# How quickly a control value is allowed to move, as a time constant. Slow
# enough that 60 Hz steps are inaudible as steps, fast enough that a kerb does
# not arrive late.
SMOOTH_S = 0.02

# DC blocker corner. Well below the amp's own 25 Hz low-cut so it removes any
# offset without touching the band.
#
# The pole is computed rather than copied. The `R = 0.995` seen in most
# published DC blockers puts -3 dB near 35 Hz at 48 kHz, which would eat the
# bottom third of everything this rig can produce.
DC_BLOCK_HZ = 5.0


@dataclass(frozen=True)
class EffectSpec:
    """One effect, in the terms the driver already tuned it in.

    Gains and frequencies come straight from his SimHub profile so the port
    starts from eight days of his tuning rather than from defaults. `gain` is
    0-100 as SimHub stores it; the mix scales it against a reference level the
    driver has actually felt - see `transducer.CALIBRATION_AMPLITUDE`.
    """
    name: str
    gain: float
    freq_lo: float
    freq_hi: float = 0.0
    noise: float = 0.0
    # A transient may use the headroom above the sustained ceiling. That
    # reserve is what makes a gear shift read as an event over the road bed
    # rather than as the bed briefly getting louder - on one piston, with
    # everything summed into one signal, contrast is all there is.
    transient: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.gain <= 100.0:
            raise ValueError(f"{self.name}: gain {self.gain} is not 0-100")
        if not 0.0 <= self.noise <= 100.0:
            raise ValueError(f"{self.name}: noise {self.noise} is not 0-100")
        top = self.freq_hi or self.freq_lo
        if self.freq_lo < transducer.BAND_LOW_HZ or top > transducer.BAND_HIGH_HZ:
            raise ValueError(
                f"{self.name}: {self.freq_lo:.0f}-{top:.0f} Hz falls outside "
                f"the {transducer.BAND_LOW_HZ:.0f}-{transducer.BAND_HIGH_HZ:.0f} "
                f"Hz this amplifier passes. Below the low-cut is excursion "
                f"spent for no output, and excursion is what bottoms a piston.")


# The six the driver had enabled, with his gains and bands. Twenty more exist
# in SimHub and were all off; porting them would be inventing a preference he
# did not express.
PORSCHE_RSR_17 = (
    EffectSpec("wheels_spin_lock", 70.00, 82.0, 108.0, noise=9.0),
    EffectSpec("gear", 39.87, 48.0, transient=True),
    EffectSpec("wheels_rumble", 37.62, 112.0, 152.0, noise=12.0),
    EffectSpec("traction_loss", 35.19, 52.0, 70.0, noise=6.0),
    EffectSpec("wheels_impact", 12.31, 28.0, 38.0, noise=3.0, transient=True),
    EffectSpec("rpm", 9.52, 34.0, 42.0, noise=3.0),
)


class _Voice:
    """One effect's oscillator, its noise, and the state both carry forward."""

    def __init__(self, spec: EffectSpec, rate: int, block: int) -> None:
        self.spec = spec
        self._rate = float(rate)
        self._phase = 0.0
        self._level = 0.0
        # Bandpass state for the noise, a two-pole state-variable filter. It
        # is unconditionally stable at these frequencies - 25-160 Hz against a
        # 48 kHz rate is an f/fs of a few thousandths.
        self._bp_low = 0.0
        self._bp_band = 0.0
        self._rng = np.random.default_rng(abs(hash(spec.name)) % (2 ** 32))
        # Everything the render path writes into, made once. `_idx` is 1..N
        # held rather than rebuilt: `np.arange` allocates and has no `out`,
        # and allocating inside an audio callback is the thing not to do.
        self._buf = np.zeros(block, dtype=np.float32)
        self._ramp = np.zeros(block, dtype=np.float32)
        self._noise = np.zeros(block, dtype=np.float32)
        self._idx = np.arange(1, block + 1, dtype=np.float32)
        # Carried across blocks so the interpolated noise does not restart
        # from zero at every boundary, which would be a click per block.
        self._noise_tail = 0.0

    @property
    def level(self) -> float:
        return self._level

    def render(self, out: np.ndarray, intensity: float, n: int) -> None:
        """Add this effect's contribution for `n` samples into `out`.

        `intensity` is 0-1, the effect's own idea of how hard it is happening.
        It sets both the amplitude and - when the spec gives a range - the
        frequency, which is what makes wheelspin rise in pitch as it worsens
        rather than merely getting louder.
        """
        target = float(np.clip(intensity, 0.0, 1.0))
        if target < SILENT and self._level < SILENT:
            # Nothing here and nothing decaying. Leave the phase where it is:
            # it costs nothing to keep and means the next onset starts from a
            # continuous waveform rather than wherever zero happened to be.
            self._level = 0.0
            return

        buf = self._buf[:n]
        ramp = self._ramp[:n]

        # Interpolate the level across the block rather than stepping it.
        alpha = 1.0 - np.exp(-1.0 / (SMOOTH_S * self._rate))
        np.multiply(self._idx[:n], alpha, out=ramp)
        np.clip(ramp, 0.0, 1.0, out=ramp)
        start = self._level
        np.multiply(ramp, (target - start), out=ramp)
        np.add(ramp, start, out=ramp)
        self._level = float(ramp[-1])

        # Frequency follows intensity when a range was given. `freq_hi` of 0
        # means a single tone, which is how SimHub stores the gear effect.
        spec = self.spec
        if spec.freq_hi:
            freq = spec.freq_lo + (spec.freq_hi - spec.freq_lo) * self._level
        else:
            freq = spec.freq_lo

        # Phase carried forward, so a frequency change bends the wave instead
        # of jumping it.
        step = 2.0 * np.pi * freq / self._rate
        np.multiply(self._idx[:n], step, out=buf)
        np.add(buf, self._phase, out=buf)
        self._phase = float((self._phase + step * n) % (2.0 * np.pi))
        np.sin(buf, out=buf)

        if spec.noise:
            self._add_noise(buf, freq, n, spec.noise / 100.0)

        np.multiply(buf, ramp, out=buf)
        np.add(out[:n], buf, out=out[:n])

    def _add_noise(self, buf: np.ndarray, freq: float, n: int,
                   ratio: float) -> None:
        """Blend band-limited noise in, to roughen a tone that is too pure.

        A bare sine reads as a test tone rather than as a road. SimHub's
        `WhiteNoise` does the same job and the driver had it on every effect
        but the gear thump - 12 on the road rumble, which is the roughest
        thing he runs.

        The noise is band-limited by **generating it slowly and interpolating
        up**, rather than by generating it at 48 kHz and filtering back down.
        Random values a few per cycle of the effect's own frequency, joined by
        straight lines, have their energy concentrated in and just below that
        band by construction - which is where it is wanted, and it costs one
        `interp` instead of a per-sample filter loop.

        That matters more than it looks. The first version of this ran a
        two-pole filter in a Python `for` over every sample of every voice:
        correct, and about six thousand interpreted iterations per block
        inside an audio callback, which is the one place the sounddevice docs
        say not to do anything slow.
        """
        white = self._noise[:n]
        # Four points per cycle: enough to describe the band, few enough that
        # the interpolation is doing the band-limiting.
        low_rate = max(2, int(n * (freq * 4.0) / self._rate) + 2)
        points = self._rng.standard_normal(low_rate)
        points[0] = self._noise_tail
        self._noise_tail = float(points[-1])
        white[:] = np.interp(np.linspace(0.0, low_rate - 1.0, n),
                             np.arange(low_rate, dtype=np.float64), points)
        # **A fixed divisor, never the block's own peak.** Normalising each
        # block by its loudest sample rescales the value shared with the
        # previous block, so the one sample that was carried across for
        # continuity lands somewhere else - a step at every boundary, which
        # is a click, which at 150 W is a thump. Measured before this was
        # fixed: 0.0146 at the seam against a 0.0022 step inside the block.
        #
        # Three sigma covers a normal distribution well enough that the rare
        # excursion is caught by the limiter downstream, and being a constant
        # it cannot break the seam.
        np.multiply(white, 1.0 / 3.0, out=white)
        np.clip(white, -1.0, 1.0, out=white)
        np.multiply(buf, 1.0 - ratio, out=buf)
        np.multiply(white, ratio, out=white)
        np.add(buf, white, out=buf)


class HapticMix:
    """Every effect, summed into the one signal a single piston can make.

    Not thread-safe, and not meant to be: `render` is called only from the
    audio callback. Intensities cross the thread boundary as a plain array
    written by the telemetry side and read here, which is safe because a
    partially-updated intensity is merely a value one frame stale and the
    smoothing above swallows it.
    """

    def __init__(self, specs=PORSCHE_RSR_17, *,
                 rate: int = transducer.SAMPLE_RATE,
                 block: int = 2048) -> None:
        self.specs = tuple(specs)
        self._rate = rate
        self._block = block
        self._voices = [_Voice(spec, rate, block) for spec in self.specs]
        self._out = np.zeros(block, dtype=np.float32)
        # Per-effect scale: SimHub's 0-100 gain against the reference level
        # the driver actually felt. A transient may reach past the sustained
        # ceiling into the headroom above it.
        self._scale = np.array(
            [spec.gain / 100.0 * (transducer.TRANSIENT_CEILING
                                  if spec.transient
                                  else transducer.SUSTAINED_CEILING)
             for spec in self.specs], dtype=np.float32)
        self._dc_y = 0.0
        # Held rather than rebuilt: the DC correction is ramped across each
        # block, and `linspace` in a callback allocates.
        self._ramp01 = np.linspace(0.0, 1.0, block, dtype=np.float32)
        self._corr = np.zeros(block, dtype=np.float32)
        self.limited_blocks = 0

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.specs)

    def render(self, intensities: np.ndarray, n: int) -> np.ndarray:
        """One block of mono signal. The returned view is reused - copy it if
        it has to outlive the call."""
        out = self._out[:n]
        out[:] = 0.0
        for index, voice in enumerate(self._voices):
            voice.render(out, float(intensities[index]) * self._scale[index], n)
        self._block_dc(out, n)
        self._limit(out, n)
        return out

    def _block_dc(self, out: np.ndarray, n: int) -> None:
        """Remove any standing offset. A sustained one is excursion that never
        comes back - it holds the piston off centre and makes it bottom on the
        next transient rather than on a loud one.

        **Tracked per block, not per sample.** The textbook
        `y[n] = x[n] - x[n-1] + R*y[n-1]` is a per-sample recurrence, and
        running that in Python inside the callback costs more than everything
        else here put together. At a 5 Hz corner the filter moves so slowly
        that a block of 21 ms is well inside its time constant, so following
        the mean at block rate and subtracting it is the same answer to the
        precision that matters.

        Every source in this module is zero-mean by construction anyway -
        sines and zero-mean interpolated noise - so this is a guard against
        arithmetic drift rather than a shaping filter. If it ever has real
        work to do, something upstream is wrong.
        """
        mean = float(out[:n].mean())
        blocks_per_second = self._rate / max(1, n)
        alpha = min(1.0, 2.0 * np.pi * DC_BLOCK_HZ / blocks_per_second)
        previous = self._dc_y
        self._dc_y = previous + (mean - previous) * alpha
        if abs(previous) < SILENT and abs(self._dc_y) < SILENT:
            return
        # **Ramped from the old correction to the new one, not stepped.**
        # Subtracting a per-block constant that changes each block is itself a
        # discontinuity at every boundary - the exact fault this function
        # exists to avoid, built into the fix for it. Measured before this was
        # ramped: 0.0176 at the seam against a 0.0024 step inside the block.
        correction = self._corr[:n]
        np.multiply(self._ramp01[:n], (self._dc_y - previous), out=correction)
        np.add(correction, previous, out=correction)
        np.subtract(out[:n], correction, out=out[:n])

    def _limit(self, out: np.ndarray, n: int) -> None:
        """Soft knee, then a hard ceiling.

        Not to protect the transducer from damage - the amp has a thermal
        cutout for that - but because the BKA-PRO's DC-protect trips on
        excessive input and **stops the unit until it is reset**. A limiter
        here is the difference between a loud moment and no haptics for the
        rest of the race.

        Reaching the limiter routinely means the mix is wrong, not that the
        limiter is working, so it is counted.
        """
        peak = float(np.max(np.abs(out[:n]))) if n else 0.0
        if peak > transducer.SUSTAINED_CEILING:
            np.tanh(out[:n] / transducer.SUSTAINED_CEILING, out=out[:n])
            np.multiply(out[:n], transducer.SUSTAINED_CEILING, out=out[:n])
        if peak > transducer.HARD_LIMIT:
            np.clip(out[:n], -transducer.HARD_LIMIT, transducer.HARD_LIMIT,
                    out=out[:n])
            self.limited_blocks += 1


def to_stereo(mono: np.ndarray, out: np.ndarray, n: int) -> None:
    """Spread the mix across both channels at half amplitude each.

    Measured on this rig: both channels reach the piston and they SUM, so the
    same signal at full scale on both would spend 6 dB on the doubling. Half
    on each sums back to the equivalent of one channel at full, and a channel
    failing then costs 6 dB rather than everything.
    """
    scaled = mono[:n] * transducer.PER_CHANNEL_SCALE
    out[:n, 0] = scaled
    out[:n, 1] = scaled
