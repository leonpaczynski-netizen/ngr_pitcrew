"""How fast the fans should turn, given how fast the car is going.

SimHub's own answer to this is compiled into `SimHub.Plugins.dll` and is not
published, so this is not a port - it is a reconstruction with the driver's own
tuned numbers as its target, and one deliberate improvement over the thing it
replaces.

**The improvement is that the app knows what car it is in.** He spent eight
days moving SimHub's `MaximumSpeed` around and settled on 281.08 km/h. GT7
broadcasts `car_max_speed_raw` in every packet - 299 for the RSR - so the top
of the curve is a measurement rather than an estimate, and it is right on a
Gr.4 and a Gr.1 without being touched. Only the *shape* of the curve is
carried over from his tuning; the scale comes from the car.

His settings, for reference, from `WindSettings.json`:

    Static:   Gain 32, EnableInRace FALSE
    Dynamic:  Gamma 1.0, GammaFactor 10.0, MinGain 29.76, MaxGain 100.0,
              MaximumSpeed 281.08, MaximumSpeedMode 1
              UseCurving false, DraftEffect 0.0

Two of those are easy to misread and both are honoured here:

* **`EnableInRace: false`** means the 32% static floor is suppressed while
  racing. During a race the dynamic curve is the only thing driving the fans,
  so static tuning done at a standstill is not what he feels on track.
* **`DraftEffect: 0.0`** with the effect enabled - switched on and weighted to
  nothing, so it does nothing. Not reproduced, because reproducing it would
  mean writing a tow model to multiply by zero. GT7 broadcasts no proximity
  channel anyway, so it could only ever have been a manual toggle.

**No left/right differential.** SimHub has one and how it is driven is
undocumented; the community explanation is "lateral forces" with no source
behind it. Inventing a differential and presenting it as a port of his setup
would be inventing a preference he never expressed. Both fans get the same
value until something measures what the real one did.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.rig.wind import CHANNELS, MIN_MOVING_DUTY, snap_duty
from pitcrew.telemetry.packet import GT7Packet

# His tuned values, as fractions rather than SimHub's percentages.
DEFAULT_MIN_GAIN = 0.2976
DEFAULT_MAX_GAIN = 1.0
DEFAULT_GAMMA = 1.0
# The static floor, and the flag that suppresses it while racing.
DEFAULT_STATIC_GAIN = 0.32

# Used only when the car does not report a top speed - which no car on the
# live stream has failed to do, but a zero would otherwise divide.
FALLBACK_MAX_KPH = 281.08

# Below this the car is stationary or crawling in the pits and the fans should
# be off rather than at the floor. Blowing at a parked car is not immersion.
MOVING_KPH = 5.0

# Rise fast, fall slow. Wind should arrive promptly and decay gently; the
# reverse sounds like a fault, and a fan that tracks every lift and re-apply
# audibly hunts. Seconds to cover the full range.
RISE_S = 0.25
FALL_S = 0.9


@dataclass(frozen=True)
class WindProfile:
    """The shape of the response, in the driver's own numbers."""
    min_gain: float = DEFAULT_MIN_GAIN
    max_gain: float = DEFAULT_MAX_GAIN
    gamma: float = DEFAULT_GAMMA
    static_gain: float = DEFAULT_STATIC_GAIN
    # **Full, and the history is worth keeping.**
    #
    # This was capped at 0.80 while the fans were stopping mid-lap, on the
    # theory that two 4000 RPM blowers at full were browning out the supply or
    # cooking the shield's drivers. It was the wrong theory. The fans stopped
    # at 33 seconds at 100% duty and at 33 seconds again at 80% - identical
    # timing under two different loads, which cannot be thermal and cannot be
    # current, because both scale with load. It was a count: frame 128, where
    # the ARQ packet id wrapped and the firmware began treating every frame as
    # one it had already seen.
    #
    # With that fixed the cap protects against nothing, so it is gone. The
    # field stays, because a rig with a smaller supply may genuinely need one
    # and finding that out should not mean editing the curve.
    max_duty: float = 1.0
    # `EnableInRace: false` in his config. Static wind is a constant baseline
    # for menus and replays; on track the dynamic curve is the whole story.
    static_in_race: bool = False

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_gain <= self.max_gain <= 1.0:
            raise ValueError(
                f"gains must run 0 <= min <= max <= 1, got "
                f"{self.min_gain} and {self.max_gain}")
        if self.gamma <= 0.0:
            raise ValueError(f"gamma {self.gamma} is not positive")


class WindCurve:
    """Speed in, two fan duties out, with the smoothing the fans need.

    Called on the telemetry thread once per frame. Holds no lock and does no
    arithmetic worth speaking of.
    """

    def __init__(self, profile: WindProfile | None = None) -> None:
        self.profile = profile or WindProfile()
        self._level = 0.0
        self.max_kph = FALLBACK_MAX_KPH

    def reset(self) -> None:
        self._level = 0.0

    def target(self, packet: GT7Packet, *, racing: bool) -> float:
        """Where the fans should be, 0-1, before smoothing.

        Separate from `update` so the curve can be reasoned about and tested
        without the time constants in the way.
        """
        top = float(packet.car_max_speed_raw or 0.0)
        if top > 0.0:
            self.max_kph = top

        if not packet.car_on_track or packet.paused:
            return 0.0

        speed = packet.speed_kmh
        if speed < MOVING_KPH:
            # Standing still. The static floor applies here - it is what makes
            # the rig feel alive in the pits - but only outside a race, which
            # is what `EnableInRace: false` says.
            if self.profile.static_in_race or not racing:
                return self.profile.static_gain
            return 0.0

        fraction = min(1.0, speed / self.max_kph)
        shaped = fraction ** self.profile.gamma
        span = self.profile.max_gain - self.profile.min_gain
        return self.profile.min_gain + span * shaped

    def update(self, packet: GT7Packet, dt: float, *,
               racing: bool = False) -> tuple[int, ...]:
        """The value to send to each channel this frame.

        Slew-limited rather than filtered, so the fans cannot be asked to do
        something they physically cannot: a 4000 rpm blower takes the better
        part of a second to settle a step, and feeding it sixty unsmoothed
        values in that time makes it hunt audibly.
        """
        wanted = min(self.profile.max_duty, self.target(packet, racing=racing))
        limit = dt / (RISE_S if wanted > self._level else FALL_S)
        step = wanted - self._level
        if abs(step) > limit:
            step = limit if step > 0 else -limit
        self._level = max(0.0, min(1.0, self._level + step))

        duty = snap_duty(round(self._level * 255))
        return tuple([duty] * CHANNELS)

    @property
    def level(self) -> float:
        """The smoothed 0-1 the fans are currently being driven at."""
        return self._level

    def describe(self) -> str:
        percent = self._level * 100.0
        duty = snap_duty(round(self._level * 255))
        moving = "off" if duty < MIN_MOVING_DUTY else f"{duty}/255"
        return (f"Wind at {percent:.0f}% ({moving}), scaled to a "
                f"{self.max_kph:.0f} km/h car.")
