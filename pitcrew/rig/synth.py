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
    # **His gamma filter, and the reason the first build felt weak.**
    #
    # `threshold` cuts below a level and `min_force` is applied after it, so an
    # effect that fires at all starts at 12-28% rather than creeping up from
    # nothing. Leaving these out - as the first version did - turns every
    # ordinary event into a whisper, because the raw intensities that come out
    # of `effects` sit low most of the time and a linear map keeps them there.
    # He set these values on the rig over eight days; they are not decoration.
    #
    # `gamma` above 1 makes the effect more sensitive - it lifts the small end
    # without moving the top - which is why it is applied as a 1/gamma
    # exponent. `input_gain` above 100 lets an effect saturate before its input
    # does; only wheelspin uses it, at 115.
    threshold: float = 0.0
    min_force: float = 0.0
    gamma: float = 1.0
    input_gain: float = 100.0
    # **A correction for where an effect sits in the rig's response.**
    #
    # SimHub's gains are not comparable across frequencies, because this rig
    # does not deliver them equally - see `transducer.FELT_RESPONSE`, measured
    # in the seat. An effect on the 40-55 Hz peak carries much further than the
    # same amplitude in the 70 Hz null.
    #
    # His gain stays exactly as he tuned it - that is the provenance and it is
    # worth keeping visible - and this carries the correction, so "gear is too
    # strong" has one number to change and it is obvious which.
    #
    # Three earlier trims were sized against a 1/f-squared model that the
    # measurement has since refuted, which is why gear went from too strong to
    # imperceptible without passing through right. Size these against the
    # curve now, not against arithmetic.
    felt_trim: float = 1.0
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
        if self.gamma <= 0.0:
            raise ValueError(f"{self.name}: gamma {self.gamma} is not positive")
        if not 0.0 <= self.min_force <= 100.0:
            raise ValueError(
                f"{self.name}: minimum force {self.min_force} is not 0-100")
        if not 0.0 < self.felt_trim <= 4.0:
            raise ValueError(
                f"{self.name}: felt trim {self.felt_trim} is not 0-4")

    def shape(self, intensity: float) -> float:
        """The driver's own gain chain: threshold, gamma, then minimum force.

        Order matters and is SimHub's: the threshold decides whether the effect
        happens at all, and the minimum force decides how hard it starts once
        it does. Applying the floor first would make the threshold meaningless,
        because everything would arrive already lifted.
        """
        value = intensity * (self.input_gain / 100.0)
        if value <= 0.0:
            return 0.0
        floor = self.threshold / 100.0
        if value <= floor:
            return 0.0
        if floor < 1.0:
            value = (value - floor) / (1.0 - floor)
        value = min(1.0, value) ** (1.0 / self.gamma)
        minimum = self.min_force / 100.0
        return minimum + (1.0 - minimum) * value


# How far the sustained bed ducks under a full-scale transient, and how
# quickly it gets there and back. 0.70 is about 10 dB at full - and a kerb
# thump does not shape to full, so the bed measured over his laps drops by
# nearer 7, which is what turns a gear shift from 8.5 dB under the road into
# 4 above it.
DUCK_DEPTH = 0.70
DUCK_ATTACK_S = 0.02
DUCK_RELEASE_S = 0.18

# The six the driver had enabled, with his gains and bands. Twenty more exist
# in SimHub and were all off; porting them would be inventing a preference he
# did not express.
PORSCHE_RSR_17 = (
    # **-2.5 dB.** "Rear tyre traction loss on acceleration a little strong",
    # and the replay agrees: it is the only effect that reaches the sustained
    # ceiling, peaking at 0.5000 on 9% of the lap. It stays the loudest thing
    # in the mix - it should be, it is the one that says the car is sliding -
    # but it no longer sets the ceiling on its own.
    EffectSpec("wheels_spin_lock", 70.00, 82.0, 108.0, noise=9.0,
               threshold=14.0, min_force=28.0, gamma=1.60, input_gain=115.0,
               felt_trim=0.75),
    # -20 dB of felt trim, and the number was arrived at twice.
    #
    # The first attempt compared gear's PEAK against the road's PEAK and
    # landed on 0.25. That is the wrong comparison: a gear shift always
    # reaches its own peak, and the road bed almost never does. Measured
    # against the bed actually present at each of thirty shifts on a real
    # lap, gear was 3.9 times more felt - not the 1.45 the peak comparison
    # implied - which is why "still overpowered" survived the first trim.
    #
    # Parity with the bed would be 0.065. A transient should stand above the
    # bed rather than sit level with it, so this leaves it about 1.5x.
    # 48 Hz is the single most efficient frequency this rig has - measured 3.0
    # of 3 - which is why it kept coming back too strong however it was
    # trimmed. 0.25 was too strong and 0.10 could not be felt at all, so the
    # answer is between: this sits nearer the quiet end, because a thump on
    # the peak carries further than the arithmetic suggests.
    # **+11 dB, from 0.16.** Every previous trim here was fitted against a
    # model that has since been measured and refuted, at an amplifier setting
    # he has since moved, with the road bed sitting in the null where it could
    # not compete. All three changed. Replayed over eight real laps, gear
    # fired at -26.8 dBFS, 8.5 dB BELOW the road bed - "gear shift can't
    # feel", and arithmetic rather than taste.
    #
    # 0.55 puts it 2.5 dB above the bed, and the ducking above gives it
    # another 7 for the length of the thump. It reached 1.5x the bed at 0.25
    # once and was called overpowered, which is why this is not simply set
    # back there: the contrast now comes from the bed getting out of the way,
    # not from the thump being large.
    EffectSpec("gear", 39.87, 48.0, transient=True, felt_trim=0.55),
    # **Moved off the null.** His band was 112-152 Hz, which on the measured
    # response is 0.9 of 3 - the dead spot. The road bed is the thing he feels
    # most of the time and it was landing where this rig cannot deliver, which
    # is why the kerb boost riding on it vanished too. 86-104 puts it on the
    # upper peak and keeps it clear of wheel-spin above it.
    # **-2 dB, because it is a different effect now.** Rescaling the texture
    # curve took this from silent-or-full - on for 24% of the lap and pinned
    # whenever it was - to a bed that is live for 95% and varies. Same peak,
    # far more of it, so the same trim would be a louder rig overall.
    EffectSpec("wheels_rumble", 37.62, 86.0, 104.0, noise=12.0,
               threshold=8.0, min_force=28.0, gamma=1.60, felt_trim=0.80),
    # His `TractionLossContainer`, renamed to what it actually carries. The
    # gain, band, noise and filter are all still his; only the input changed,
    # from a saturating yaw-error model to lateral g.
    # **Narrowed so it cannot climb into the null.** His 52-70 band ends
    # exactly on the dead spot, so as he loaded the car harder the effect rose
    # in amplitude and fell in delivery - the signal partly cancelling itself
    # at the very moment it mattered. 44-56 keeps the whole range on the lower
    # peak, so more load is more felt all the way up.
    # **-3 dB.** "A little strong", and it is live for 43% of the lap - more
    # than anything else except the engine bed. It is also sitting on the
    # strongest region this rig has, which the placement change handed it for
    # free. Quieter, still the second loudest thing, and now getting out of
    # the way when a kerb arrives.
    EffectSpec("lateral_load", 35.19, 44.0, 56.0, noise=6.0,
               threshold=9.0, min_force=12.0, gamma=1.40, felt_trim=0.70),
    # Raised off the bottom. 28-38 Hz measures 2.0-2.5 of 3, which is not bad
    # - but the kerb thump living here was a third the amplitude of the test
    # tone and could not be felt, and 40-52 is the strongest region this rig
    # has. Impacts are rare and want authority; kerbs want to be sharp.
    # **+7 dB.** The kerb thump is the whole of this channel in practice, and
    # it fired at -23.4 dBFS: 11.3 dB under the road bed and 7.6 dB under
    # lateral load, which shares its region of the response. Two effects at
    # once burying it, on one piston, in the same twelve hertz - "kerb thump I
    # can't feel". His gain of 12.31 was set for genuine impacts, which are
    # rare; the kerb strike is not rare and it is the one he wants.
    EffectSpec("wheels_impact", 12.31, 40.0, 52.0, noise=3.0, transient=True,
               threshold=55.0, min_force=20.0, gamma=1.20, felt_trim=2.20),
    # The RPM curve is drawn by hand in `effects.RPM_CURVE` and arrives here
    # already shaped, so it takes no gamma of its own.
    #
    # **+8 dB, and it is still the quietest thing in the mix.** Reported weak
    # twice. Replayed, it sat at -27.4 dBFS for the whole lap - his own gain
    # of 9.52 against wheel-spin's 70, faithfully carried over, and inaudible
    # under everything else once the rest of the mix was working.
    #
    # Worth knowing before asking for more: his curve spans 36.91 to 63.06
    # across the revs actually used, so this channel has only **4.6 dB of
    # range in a whole lap** however loud it is made. It is a bed that firms
    # up with revs, not a tachometer. Making it one means redrawing the curve,
    # which is his to draw.
    EffectSpec("rpm", 9.52, 34.0, 42.0, noise=3.0, felt_trim=2.50),
)


class _Voice:
    """One effect's oscillator, its noise, and the state both carry forward."""

    def __init__(self, spec: EffectSpec, rate: int, block: int) -> None:
        self.spec = spec
        self._rate = float(rate)
        self._phase = 0.0
        self._level = 0.0
        # Where in its band the effect currently sits, 0-1. Kept apart from
        # the level - see `render`.
        self._pitch = 0.0
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

    def render(self, out: np.ndarray, intensity: float, pitch: float,
               n: int) -> None:
        """Add this effect's contribution for `n` samples into `out`.

        `intensity` is 0-1, the effect's own idea of how hard it is happening.
        `intensity` is the amplitude to render at - gain, felt trim and
        master already applied. `pitch` is the effect's own 0-1 intensity
        BEFORE any of that, and is what walks the frequency up its band.

        **They have to be two numbers.** They used to be one, and it made the
        pitch of every effect a function of its volume: an effect with a small
        gain could never climb out of the bottom of its own band, and turning
        the master up transposed the entire rig. Lateral load used a quarter
        of its range and the kerb thump a twelfth.
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

        # Frequency follows the effect's own intensity when a range was
        # given. `freq_hi` of 0 means a single tone, which is how SimHub
        # stores the gear effect.
        #
        # Smoothed the same way the level is, and over the same time constant,
        # so a step in intensity bends the pitch rather than stepping it - a
        # pitch jump is heard as a click even when the phase is continuous.
        spec = self.spec
        if spec.freq_hi:
            aim = float(np.clip(pitch, 0.0, 1.0))
            self._pitch += (aim - self._pitch) * float(ramp[-1])
            freq = spec.freq_lo + (spec.freq_hi - spec.freq_lo) * self._pitch
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
                 block: int = 2048, master: float = 1.0) -> None:
        self.specs = tuple(specs)
        # One number over the whole mix, for the driver to turn.
        #
        # The relative balance between effects is his, tuned over eight days,
        # and should be changed by editing an effect rather than by leaning on
        # this. The limiter still holds the peak whatever this is set to - but
        # NOT the duty cycle, which is what an amplifier's protection responds
        # to, so this is not a free control. Measured on a real lap: a master
        # of 2.5 puts 31.5% of blocks into the limiter and holds the mix at
        # -9.1 dBFS sustained, against 0.05% and -16.4 dBFS at 1.0.
        #
        # The amplifier's own knob is the better answer to "not strong
        # enough": it is at 35 of 50, so there is 3 dB sitting unused, and
        # turning it up changes neither the duty cycle nor the mix.
        self.master = max(0.0, min(4.0, float(master)))
        self._rate = rate
        self._block = block
        self._voices = [_Voice(spec, rate, block) for spec in self.specs]
        self._out = np.zeros(block, dtype=np.float32)
        # Per-effect scale: SimHub's 0-100 gain against the reference level
        # the driver actually felt. A transient may reach past the sustained
        # ceiling into the headroom above it.
        # **Relative to the loudest effect, not to an abstract 100.**
        #
        # SimHub's gains are weights inside its own chain - his sat under a
        # profile gain of 49.8 and a global of 100 - so reading them as
        # fractions of full scale here made even the strongest effect peak at
        # 0.35 against a reference of 0.5 that he had described as "very
        # strong", and the quiet ones vanished. Reported from the seat as
        # "worked fine, just very weak".
        #
        # Normalising by the largest gain keeps the balance he tuned - which
        # is the part worth eight days - while letting the mix reach the level
        # the amplifier was actually calibrated against. His loudest is
        # wheelspin at 70; that one now reaches the ceiling and everything
        # else sits below it in the proportions he chose.
        # **One ceiling for every effect, and the headroom is the limiter's
        # business alone.**
        #
        # This used to scale transients by `TRANSIENT_CEILING` and everything
        # else by `SUSTAINED_CEILING`, which quietly rewrote the driver's
        # balance: his gear effect is 39.87 and his road rumble 37.62 - within
        # 6% of each other - and the split ceilings turned that into 0.404
        # against 0.269, half again as loud. Reported from the seat as "gear
        # changes still feel overpowered", which is exactly right and was not
        # a taste question at all.
        #
        # The headroom above the sustained ceiling still exists and transients
        # still reach into it, but by being brief and landing on top of the
        # bed rather than by carrying a larger gain. That is the difference
        # between a peak that stands out and an effect that is simply louder.
        loudest = max(spec.gain for spec in self.specs) or 100.0
        self._scale = np.array(
            [spec.gain / loudest * transducer.SUSTAINED_CEILING
             * spec.felt_trim
             for spec in self.specs], dtype=np.float32)
        # **How far the bed gets out of the way when an event fires.**
        #
        # With one piston every effect sums into one signal, so an event is
        # only legible if it stands above whatever else is playing. Measured
        # over eight of his laps, it did the opposite: the kerb thump fired
        # 11.3 dB BELOW the road bed and 7.6 dB below lateral load - which
        # occupies the same region of the response - and the gear thump 8.5 dB
        # below the bed. Reported as "kerb thump I can't feel" and "gear shift
        # can't feel", and no amount of gain on the events alone fixes it,
        # because raising them raises what they have to beat as well when the
        # limiter closes.
        #
        # So the sustained effects duck. Fast enough to be out of the way
        # before a 90 ms thump has peaked, slow enough coming back that the
        # recovery is not itself an event.
        self._duck = 1.0
        self._transient = np.array([spec.transient for spec in self.specs],
                                   dtype=bool)
        self._dc_y = 0.0
        # Held rather than rebuilt: the DC correction is ramped across each
        # block, and `linspace` in a callback allocates.
        self._ramp01 = np.linspace(0.0, 1.0, block, dtype=np.float32)
        self._corr = np.zeros(block, dtype=np.float32)
        self.limited_blocks = 0
        # The loudest sample rendered since anyone last asked. Read and reset
        # by the health check, which needs to know whether we were producing
        # anything before it can call the card silent.
        self._recent_peak = 0.0

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(spec.name for spec in self.specs)

    def render(self, intensities: np.ndarray, n: int) -> np.ndarray:
        """One block of mono signal. The returned view is reused - copy it if
        it has to outlive the call."""
        out = self._out[:n]
        out[:] = 0.0
        shaped = np.array([voice.spec.shape(float(intensities[index]))
                           for index, voice in enumerate(self._voices)],
                          dtype=np.float32)

        # The loudest transient asking to be heard, and how far the bed steps
        # aside for it. One duck for the whole bed rather than one per pair:
        # the driver feels the sum, not the effects.
        event = float(shaped[self._transient].max()) if self._transient.any() else 0.0
        aim = 1.0 - DUCK_DEPTH * event
        seconds = n / float(self._rate)
        tau = DUCK_ATTACK_S if aim < self._duck else DUCK_RELEASE_S
        self._duck += (aim - self._duck) * min(1.0, seconds / tau)

        for index, voice in enumerate(self._voices):
            level = float(shaped[index]) * self._scale[index] * self.master
            if not self._transient[index]:
                level *= self._duck
            voice.render(out, level, float(shaped[index]), n)
        self._block_dc(out, n)
        self._limit(out, n)
        if n:
            self._recent_peak = max(self._recent_peak,
                                    float(np.max(np.abs(out[:n]))))
        return out

    def take_recent_peak(self) -> float:
        """The loudest thing rendered since this was last called."""
        peak, self._recent_peak = self._recent_peak, 0.0
        return peak

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
        # **The knee is the transient ceiling, not the sustained one.**
        #
        # It used to soft-clip at `SUSTAINED_CEILING`, which defeated the whole
        # reason the headroom above it exists: a gear shift or a kerb is
        # allowed past the bed precisely so it reads as an event, and clamping
        # the summed output at the bed's own ceiling made that impossible.
        # Measured, driving a plausible lap: the peak sat pinned at 0.499 at
        # every master gain from 1 to 4, while 71% of blocks were being
        # compressed at 4. The driver was hearing a compressor rather than a
        # mix - which is why turning it up added fullness but no impact.
        #
        # It is also the likeliest reason the transducer went quiet mid-corner.
        # The BKA-PRO's 150 W rating assumes a one-third duty cycle and its
        # DC-protect trips on sustained excessive input; 71% of blocks held
        # near full scale is exactly that.
        peak = float(np.max(np.abs(out[:n]))) if n else 0.0
        if peak > transducer.TRANSIENT_CEILING:
            np.tanh(out[:n] / transducer.TRANSIENT_CEILING, out=out[:n])
            np.multiply(out[:n], transducer.TRANSIENT_CEILING, out=out[:n])
            self.limited_blocks += 1
        if peak > transducer.HARD_LIMIT:
            np.clip(out[:n], -transducer.HARD_LIMIT, transducer.HARD_LIMIT,
                    out=out[:n])


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
