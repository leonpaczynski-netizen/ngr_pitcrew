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
* **Nothing is beeped in the top gear.** There is no seventh gear in a
  six-speed, so a beep there is an instruction that cannot be obeyed - and it
  arrives on the fastest part of the lap, which is where a meaningless sound
  is most expensive. The car's gear count is read off the packet's own ratio
  table rather than configured, because it is already broadcast and a number
  the driver has to keep in step with his gearbox is a number that goes stale.

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
# How long the beep will wait for the card once it has asked the engineer to
# stand aside. The voice yields between written chunks, so the real wait is
# one clip - a few hundred milliseconds at worst. This is the backstop for a
# chunk that runs long, and it is short on purpose: past it the beep is no
# longer describing the rpm the engine is at. **A beep that cannot be played
# on time is dropped, not queued** - the same rule `_TonePlayer.__call__`
# already applies to an overlapping beep, for the same reason.
PRIORITY_WAIT_S = 0.4
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
                now: float,
                top_gear: int | None = None) -> tuple[bool, bool, float]:
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
        if top_gear is not None and cur_gear >= top_gear:
            # Top gear: there is nothing to shift into. The hysteresis is
            # still armed exactly as it would have been, so that suppressing
            # the sound cannot change when the NEXT beep - after a downshift,
            # in a gear that does have one above it - falls due. Returning
            # early from higher up would have left `shift_above` stale and
            # made the top gear silently re-time the rest of the lap.
            return False, True, downshift_muted_until
        return True, True, downshift_muted_until

    return False, re_armed, downshift_muted_until


class ShiftBeep:
    """Stateful wrapper around `should_beep`, fed one packet at a time."""

    def __init__(self, *, enabled: bool = True,
                 tone=None, per_gear: dict[int, float] | None = None,
                 short_shift_drop_rpm: float | None = None,
                 top_gear: int | None = None) -> None:
        self.enabled = enabled
        # The highest gear the fitted gearbox has, or None while it is not
        # known. **None means beep in every gear**, which is what this did
        # before the top gear was read at all: a car whose ratios have not
        # arrived yet is not a reason to go quiet, and a wrong silence is
        # harder to notice than a wrong beep.
        self.top_gear = top_gear
        # **Measured per-gear thresholds, keyed by gear, and the only source
        # there is.** They are issued by the tune builder with the setup they
        # belong to, because a shift point belongs to the gearbox: change a
        # ratio and the rpm worth shifting at moves with it. See
        # `engineer/shift_points.py`. A gear not in here does not beep - the global
        # fallback and GT7's own shift light both used to fill the gap, and
        # both sounded at the wheel exactly like a measurement without being
        # one.
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

    def threshold_for(self, gear: int) -> float | None:
        """The rpm this gear beeps at, right now, or None for silence.

        **A gear with no measured threshold does not beep.** It used to fall
        back to one global rpm, and before that to GT7's own shift light -
        both of which sound exactly like a measurement and are not one. One
        car wants the limiter in every gear and another wants 8250 in all
        five, which is the whole reason this is a table, and a fallback quietly
        told the driver a number nobody had taken on that gearbox.

        The thresholds are issued with the setup, because a shift point
        belongs to the gearbox: change a ratio and it moves. No table issued
        for this box means nobody has designed one, and silence is the honest
        answer.

        Public because the export has to be able to show what the driver was
        actually being told, and a threshold that can only be inferred from
        behaviour is one nobody can check.
        """
        base = self.per_gear.get(int(gear))
        if base is None:
            return None
        if not self.short_shifting:
            return base
        drop = self.short_shift_drop_per_gear.get(
            int(gear), self.short_shift_drop_rpm)
        return max(MIN_THRESHOLD_RPM, base - drop)

    def note_gear_ratios(self, ratios) -> None:
        """Learn the top gear from the ratio table the packet broadcasts.

        GT7 sends eight slots and zeroes the ones the gearbox does not have,
        so the count of non-zero ratios is the gear count. Read every packet
        rather than once: the driver changes cars without restarting the app,
        and a stale gear count would silence a real beep in the new car's
        fifth gear.

        A table that is entirely zero - the car has not loaded yet - leaves
        the last known count alone rather than clearing it, so the beep does
        not lose the gearbox every time the session pauses.
        """
        fitted = [r for r in (ratios or []) if r]
        if fitted:
            self.top_gear = len(fitted)

    def update(self, packet, now: float) -> bool:
        self.note_gear_ratios(getattr(packet, "gear_ratios", None))
        if not driving_gate(packet.car_on_track, packet.paused, packet.loading):
            self._prev_gear = packet.current_gear
            return False

        threshold = self.threshold_for(packet.current_gear)
        if threshold is None:
            # No measured threshold for this gear, so nothing to be above.
            # State still advances: the beep must not fire on the first gear
            # that does have one purely because the last one was silent.
            self._prev_gear = packet.current_gear
            self._shift_above = False
            return False

        beep, self._shift_above, self._muted_until = should_beep(
            prev_gear=self._prev_gear,
            cur_gear=packet.current_gear,
            rpm=packet.engine_rpm,
            threshold=threshold,
            shift_above=self._shift_above,
            enabled=self.enabled,
            downshift_muted_until=self._muted_until,
            now=now,
            top_gear=self.top_gear,
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
                 rate: int = 44100, samples=None) -> None:
        self._rate = rate
        # `samples` lets a caller supply its own waveform and inherit the rest:
        # the shared audio lock, the drop-rather-than-queue rule, and the
        # fire-and-forget thread. The radio static that brackets a push-to-talk
        # question uses it - same machinery, different sound.
        self._samples = (_square_wave(freq, ms, rate) if samples is None
                         else samples)
        # How to build this sound again at somebody else's sample rate, for
        # `audio_devices.offer_mix`. Only the synthesised beep can do it: a
        # caller-supplied waveform exists at one rate and resampling it is how
        # you get the click `_square_wave` ramps its edges to avoid. Those
        # callers keep the pre-emption path, which is what they had.
        self._recipe = (None if samples is not None
                        else lambda at: _square_wave(freq, ms, at))
        # Held for the duration of a beep. Non-blocking acquisition is what
        # makes an overlapping beep a drop rather than a queue.
        self._busy = threading.Lock()
        # Beeps that were due and did not sound, for the settings screen and
        # the per-session log line. A number nobody can see is a number that
        # cannot be traded off against `PRIORITY_WAIT_S`.
        self.dropped = 0

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
        #
        # **Taken with priority, and with a deadline.** Waiting on it plainly
        # is what used to make a spoken line swallow a shift point: the beep
        # arrived a whole sentence late, naming an rpm the engine had left.
        # `priority_on` asks the voice to close after its current chunk - see
        # `audio_devices.priority_on` for why the voice closes its own stream
        # and the beep never touches it - and the deadline below is what
        # happens when even that is too slow.
        device = audio_devices.output_device()
        lock = audio_devices.lock_for(device)

        # **Free card first.** Nothing below changes the common case, which is
        # a beep with no line in flight: take the lock, open, play, at the
        # latency it has always had.
        if lock.acquire(blocking=False):
            try:
                self._render_locked()
            finally:
                lock.release()
            return

        # **Busy card: play over the top rather than instead of.** Measured in
        # the Fuji race, pre-emption cut nine calls mid-sentence and restarted
        # the race-start call four times. Handing the waveform to the thread
        # already writing this card costs one chunk of latency - well inside
        # `PRIORITY_WAIT_S` - and costs the line nothing at all.
        if self._recipe is not None and audio_devices.offer_mix(device,
                                                                self._recipe):
            return

        # Nobody could mix it: the card is held by something that does not
        # write in chunks. Pre-empt, exactly as before.
        with audio_devices.priority_on(device):
            if not lock.acquire(timeout=PRIORITY_WAIT_S):
                self.dropped += 1
                raise TimeoutError(
                    f"the card was still busy {PRIORITY_WAIT_S:.1f}s after "
                    f"the beep asked for it - dropped rather than played at "
                    f"the wrong rpm")
            try:
                self._render_locked()
            finally:
                lock.release()

    def _render_locked(self) -> None:
        """Play it, with the card already held."""
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
