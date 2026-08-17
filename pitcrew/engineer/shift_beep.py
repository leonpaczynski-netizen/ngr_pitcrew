"""The shift beep.

Ported from the old app rather than rewritten: the rules below were arrived at
by finding out the hard way where a beep is unwanted, and re-deriving them
would mean rediscovering the same annoyances at the wheel.

Three of them cost real sessions to learn:

* **On track only.** Gating on "moving and in gear" let it beep in the pit
  lane, in replays and in the garage. It gates on `car_on_track` alone.
* **A downshift mutes it briefly.** Blipping the throttle on the downshift
  spikes the rpm past the threshold, and without the mute every heel-and-toe
  downshift fired a beep telling him to upshift.
* **Hysteresis, not a level.** It re-arms only once rpm falls back below 95%
  of the threshold, so sitting on the limiter beeps once rather than sixty
  times a second.

**The threshold is per gear, and it is measured.** One number for every gear
is a compromise between shift points that are genuinely different, and it was
costing real time: measured over his own laps, the Shelby GT350R's crossover
sits at about 8250 rpm in all five upshifts while the beep was set to 8640, so
he was holding every gear several hundred rpm into the part of the curve where
the next gear already pulls harder. The Porsche RSR, measured the same way,
shows no crossover at all inside the rpm range it was driven in.

That difference is why the number cannot be a constant, a default, or a guess.
`tools/shift_points.py` derives it per car and per gear from recorded laps:
acceleration is the derivative of the measured speed channel, and the upshift
point is where the next gear's acceleration - at the rpm the engine lands on,
which is the same road speed and therefore the same drag - beats this gear's.
GT7 broadcasts no torque curve, so this is derived rather than measured; what
makes it honest is that it is derived from his own car and is re-checkable.

**Short-shifting is a live switch, not a second profile to configure.** He
prefers saving fuel by short-shifting over leaning the fuel map, because a map
step costs power everywhere while a short-shift costs only the top of each
gear - and it drops rear tyre temperature as well. So the race threshold moves
down by a stated number of rpm when the engineer asks for fuel, and back up
when it stops asking. Anything that reads this must know which mode produced a
lap: laps driven short-shifted cost about half a second, which is the same
size as the pace deficit the stint calls look for, and a lap-time series that
does not exclude them measures the app's own instruction.
"""
from __future__ import annotations

import threading

from pitcrew.diagnostics import log
from pitcrew.engineer import audio_devices

# How long a downshift suppresses the beep, to swallow the blip.
DOWNSHIFT_MUTE_S = 0.3
# Re-arm once rpm falls back to this fraction of the threshold.
REARM_FRACTION = 0.95
DEFAULT_RPM = 7000.0
# How far below the performance threshold a short-shift sits, when no measured
# figure has been supplied for the car. Deliberately modest: the whole point is
# that the cost is bounded and known, and 500 rpm off a crossover in the
# 8000-8500 region is inside the band where the measured acceleration curves
# are still close together. A car whose curve falls off a cliff wants its own
# number from `tools/shift_points.py`, not this one.
DEFAULT_SHORT_SHIFT_DROP_RPM = 500.0
# What the beep calls itself while it holds a stream open, for the log line a
# deferred device rebuild writes. See `audio_devices.begin_playback`.
BEEP = "the shift beep"
# No threshold may be dragged below this by a short-shift request. Short-
# shifting out of the powerband is not fuel saving, it is driving badly, and
# an engineer that asks for it has stopped being useful.
MIN_THRESHOLD_RPM = 3000.0


def driving_gate(car_on_track: bool, paused: bool, loading: bool) -> bool:
    """True only when the car is actually on track.

    Deliberately narrow. An earlier version also let any moving, in-gear car
    through, which is exactly how it ended up beeping in the pit lane.
    """
    if paused or loading:
        return False
    return bool(car_on_track)


def should_beep(*, prev_gear: int, cur_gear: int, rpm: float,
                threshold: float, shift_above: bool, enabled: bool,
                downshift_muted_until: float,
                now: float) -> tuple[bool, bool, float]:
    """Decide whether to beep this packet.

    Returns `(beep, shift_above, downshift_muted_until)` - the caller keeps the
    latter two and hands them back next packet, so this stays a pure function
    with no state of its own and can be tested exhaustively.
    """
    if not enabled:
        return False, shift_above, downshift_muted_until

    if not 1 <= cur_gear <= 8:
        # Neutral or reverse: nothing to shift.
        return False, shift_above, downshift_muted_until

    if prev_gear > 0 and cur_gear < prev_gear:
        # Downshift. Hold shift_above True so the throttle blip that follows
        # cannot fire a beep the moment the rpm spikes.
        return False, True, now + DOWNSHIFT_MUTE_S

    re_armed = shift_above
    if rpm < threshold * REARM_FRACTION:
        re_armed = False

    if (rpm >= threshold and not re_armed
            and now >= downshift_muted_until):
        return True, True, downshift_muted_until

    return False, re_armed, downshift_muted_until


class ShiftBeep:
    """Stateful wrapper around `should_beep`, fed one packet at a time."""

    def __init__(self, *, rpm: float = DEFAULT_RPM, enabled: bool = True,
                 tone=None, per_gear: dict[int, float] | None = None,
                 short_shift_drop_rpm: float | None = None) -> None:
        self.rpm = rpm
        self.enabled = enabled
        # Measured per-gear thresholds, keyed by gear. A gear with no measured
        # figure falls back to `rpm` rather than to a default: a made-up number
        # for one gear inside a measured table is the worst of both, because it
        # is indistinguishable from the measured ones at the wheel.
        self.per_gear: dict[int, float] = dict(per_gear or {})
        # How far down a short-shift moves the threshold. Per gear where it has
        # been measured, otherwise the scalar.
        self.short_shift_drop_rpm = (DEFAULT_SHORT_SHIFT_DROP_RPM
                                     if short_shift_drop_rpm is None
                                     else float(short_shift_drop_rpm))
        self.short_shift_drop_per_gear: dict[int, float] = {}
        # The live switch. Flipped by the engineer when fuel needs saving and
        # cleared when it does not - see the module docstring.
        self.short_shifting = False
        self._tone = tone if tone is not None else _default_tone()
        self._prev_gear = 0
        self._shift_above = False
        self._muted_until = 0.0
        self.beeps = 0
        # Why the last beep did not sound, for the settings screen to report.
        self.last_error: str | None = None

    def threshold_for(self, gear: int) -> float:
        """The rpm this gear beeps at, right now.

        Public because the settings screen and the export both have to be able
        to show what the driver is actually being told, and because a threshold
        that can only be inferred from behaviour is one nobody can check.
        """
        base = self.per_gear.get(int(gear), self.rpm)
        if not self.short_shifting:
            return base
        drop = self.short_shift_drop_per_gear.get(
            int(gear), self.short_shift_drop_rpm)
        return max(MIN_THRESHOLD_RPM, base - drop)

    def update(self, packet, now: float) -> bool:
        if not driving_gate(packet.car_on_track, packet.paused, packet.loading):
            self._prev_gear = packet.current_gear
            return False

        beep, self._shift_above, self._muted_until = should_beep(
            prev_gear=self._prev_gear,
            cur_gear=packet.current_gear,
            rpm=packet.engine_rpm,
            threshold=self.threshold_for(packet.current_gear),
            shift_above=self._shift_above,
            enabled=self.enabled,
            downshift_muted_until=self._muted_until,
            now=now,
        )
        self._prev_gear = packet.current_gear
        if beep:
            self.beeps += 1
            self._play()
        return beep

    def play_now(self) -> bool:
        """Sound it once regardless of gate or threshold. True if it sounded.

        For the settings screen: he is in a headset while driving and cannot
        see whether the beep fired, so the only way to know it is audible over
        the engine is to press a button and listen.

        Which is exactly why the answer has to be able to be no. This used to
        return True whenever a tone function existed, and `_play` swallows the
        exception - so the one control that exists to prove the beep works
        reported success for a beep that raised.

        Played **on this thread**, unlike the in-race path: a button that
        reports what happened cannot report on a beep that has not been
        attempted yet.
        """
        return self._play(blocking=True)

    def _play(self, *, blocking: bool = False) -> bool:
        """Sound the tone. False when it did not, for whatever reason.

        The in-race caller is the telemetry thread and must not wait on
        PortAudio - opening a stream costs over a second on some host APIs,
        which is packets on the floor. So the default is fire-and-forget and
        the test button asks for the blocking form.
        """
        if self._tone is None:
            return False
        try:
            # A test double is a bare callable with no blocking form; that is
            # the seam the beep tests drive, so fall back to calling it.
            play = (getattr(self._tone, "play_blocking", self._tone)
                    if blocking else self._tone)
            play()
        except Exception as exc:                # noqa: BLE001
            # A failed beep must never take the telemetry thread down - but
            # the caller is told, so a test button can say so.
            log("beep").warning("%s: %s", type(exc).__name__, exc)
            self.last_error = f"{type(exc).__name__}: {exc}"
            return False
        self.last_error = None
        return True


class _TonePlayer:
    """A short beep on the card the driver chose.

    This used to be `winsound.Beep`, which is a one-liner and was wrong in a
    way that only shows up at the rig: it plays through whatever Windows calls
    the default output and has no way to be pointed anywhere else. Every other
    sound this app makes follows the Settings screen's device; the beep did
    not, so "Test beep" proved a device the driver had not chosen. It looked
    correct for as long as his headset happened to also be the default.

    Two consequences of making it a real audio stream:

    * **It is played off the caller's thread.** `winsound.Beep` blocks for the
      length of the beep and nothing else; opening a PortAudio stream can cost
      over a second, and the in-race caller is the telemetry thread.
    * **A beep that arrives while one is still playing is dropped, not
      queued.** Two beeps a corner apart are information; a backlog of them is
      noise, and the hysteresis in `should_beep` already exists to stop the
      limiter firing sixty a second.
    """

    def __init__(self, *, freq: float = 1800.0, ms: int = 60,
                 rate: int = 44100) -> None:
        self._rate = rate
        self._samples = _square_wave(freq, ms, rate)
        # Held for the duration of a beep. Non-blocking acquisition is what
        # makes an overlapping beep a drop rather than a queue.
        self._busy = threading.Lock()

    def __call__(self) -> None:
        """Fire and forget, for the telemetry thread."""
        if not self._busy.acquire(blocking=False):
            return
        threading.Thread(target=self._play_and_release, name="PitCrewBeep",
                         daemon=True).start()

    def play_blocking(self) -> None:
        """Play it here and now, raising if it did not sound.

        The test button's whole purpose is to be able to answer no, which it
        cannot do about a beep still queued on another thread.
        """
        with self._busy:
            self._render()

    def _play_and_release(self) -> None:
        try:
            self._render()
        except Exception as exc:                # noqa: BLE001
            # Nothing is waiting on this thread, so the log is the only place
            # it can be said. The test button uses the blocking path, which
            # raises properly.
            log("beep").warning("beep failed: %s: %s",
                                type(exc).__name__, exc)
        finally:
            self._busy.release()

    def _render(self) -> None:
        # The same lock the engineer's voice holds: overlapping PortAudio
        # streams crash the host rather than mixing, and a beep landing on top
        # of a call is exactly when that would happen.
        with audio_devices.lock_for(audio_devices.output_device()):
            # The beep is behind the same gate as the engineer's line, so a
            # device-list rebuild waits for it too - see
            # `audio_devices.begin_playback` for why the open and the
            # declaration are one step.
            #
            # Its exposure is smaller than the voice's in every direction and
            # worth stating rather than assuming. The stream is open for the
            # sixty milliseconds of the tone instead of a whole sentence, so a
            # rebuild has to land in a much narrower window to catch it, and
            # holding a rebuild for sixty milliseconds costs the caller
            # nothing worth naming. It never overlaps a spoken line - both
            # take `lock_for(output_device())` first - so it can only ever be
            # the one thing a rebuild is waiting on.
            #
            # **A cut beep is not fired again**, unlike a cut line. A beep is
            # an instruction about the rpm the engine is at right now; played
            # late it names the wrong shift point, which is worse than the
            # missed one. `_TonePlayer.__call__` already drops an overlapping
            # beep for the same reason, so this is the existing rule and not a
            # second one. `interrupted` is therefore read by nobody here - the
            # gate exists to make the rebuild wait, and the marking is only
            # of interest to a caller that can act on it.
            stream, _beep = audio_devices.open_and_declare(
                BEEP, lambda: audio_devices.open_output(self._rate))
            try:
                stream.write(self._samples)
            finally:
                stream.stop()
                stream.close()
                audio_devices.end_playback(_beep)


def _square_wave(freq: float, ms: int, rate: int):
    """The beep itself: a square wave, as `winsound.Beep` produced.

    Ramped in and out over a millisecond because a square wave that starts at
    full amplitude clicks, and a click in a headset at racing speed reads as a
    fault in the audio rather than as the beep.
    """
    import numpy as np

    samples = int(rate * ms / 1000)
    t = np.arange(samples) / rate
    wave = np.sign(np.sin(2 * np.pi * freq * t))
    ramp = max(1, int(rate * 0.001))
    envelope = np.ones(samples)
    envelope[:ramp] = np.linspace(0.0, 1.0, ramp)
    envelope[-ramp:] = np.linspace(1.0, 0.0, ramp)
    return (wave * envelope * 16000).astype(np.int16)


def _default_tone():
    """A short square beep on the chosen card, or None where audio is not
    available at all - which is what `ShiftBeep` reports as "this machine has
    no tone device"."""
    try:
        import numpy  # noqa: F401 - required to build the wave
        import sounddevice  # noqa: F401 - required to play it
    except ImportError as exc:
        log("beep").warning("no beep on this machine: %s", exc)
        return None
    return _TonePlayer()
