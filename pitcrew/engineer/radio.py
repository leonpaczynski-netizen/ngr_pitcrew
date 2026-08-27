"""The two static bursts that bracket a question.

*"I don't have time to hold the button. One press, hear a radio static sound so
I know it's recording, then it records, I talk, radio static to confirm to me
recording has stopped, and then engineer responds."* - the driver, 22 Aug.

**Both halves of that are about not looking at a screen.** Holding a button
occupies a hand that is on a wheel; and with the button no longer held, nothing
tells him whether the microphone is open. A radio has always solved this the
same way: the click in and the click out are how you know you are on the air.

### Why noise and not a tone

The app already owns a tone - the shift beep at 1800 Hz - and it fires during
the same laps. A second tone would be one more thing to tell apart at speed.
Filtered noise is categorically different from anything else the app makes, and
it is the sound the driver named.

The two bursts are deliberately *not* identical. Opening rises, closing falls,
so that a burst heard on its own still says which one it was - he can miss the
first and still know from the second that the radio has closed.
"""
from __future__ import annotations

# Short. It sits between him pressing and him speaking, and every millisecond
# of it is a millisecond he waits.
BURST_MS = 130
# Well under the voice, so it reads as radio furniture rather than as a call.
# It was 13.7 dB under one, which is furniture nobody hears over an engine and
# a headset - the driver, 27 Aug 2026, asked for both bursts louder. Doubled,
# which is +6.2 dB, and still about 10 dB below a spoken line at
# `voice.LINE_GAIN`, so it stays the same kind of sound it was.
LEVEL = 0.45
# The band a squelch burst lives in. Below this it is a thump, above it a hiss.
LOW_HZ = 350.0
HIGH_HZ = 2600.0


def _noise(ms: int, rate: int, *, rising: bool, seed: int):
    """A band-limited noise burst, rising or falling in level.

    Built in the frequency domain so the band edges are exact and there is no
    filter to settle - a 130 ms burst is too short to let an IIR filter's
    transient count as part of the sound.
    """
    import numpy as np

    samples = max(1, int(rate * ms / 1000))
    spectrum = np.fft.rfftfreq(samples, 1.0 / rate)
    generator = np.random.default_rng(seed)
    noise = generator.standard_normal(samples)
    band = np.fft.rfft(noise)
    band[(spectrum < LOW_HZ) | (spectrum > HIGH_HZ)] = 0.0
    wave = np.fft.irfft(band, n=samples)

    peak = float(np.max(np.abs(wave))) or 1.0
    wave = wave / peak

    # The shape that tells the two apart. Both ends still ramp from and to
    # zero, or the burst clicks.
    sweep = np.linspace(0.35, 1.0, samples)
    wave *= sweep if rising else sweep[::-1]
    edge = max(1, int(rate * 0.004))
    wave[:edge] *= np.linspace(0.0, 1.0, edge)
    wave[-edge:] *= np.linspace(1.0, 0.0, edge)
    return (wave * LEVEL * 32767).astype(np.int16)


def bursts(*, rate: int = 44100, ms: int = BURST_MS):
    """`(opening, closing)` - two `Tone`s, or `(None, None)` with no numpy.

    Returning None rather than raising is deliberate: static is confirmation,
    not the question. A machine that cannot render it should still have a
    working radio, and the driver should still get his answer.
    """
    try:
        from pitcrew.engineer.shift_beep import _TonePlayer as Tone

        return (Tone(rate=rate, samples=_noise(ms, rate, rising=True,
                                               seed=17)),
                Tone(rate=rate, samples=_noise(ms, rate, rising=False,
                                               seed=23)))
    except Exception:                            # noqa: BLE001
        return None, None
