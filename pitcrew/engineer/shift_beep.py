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
"""
from __future__ import annotations

from pitcrew.diagnostics import log

# How long a downshift suppresses the beep, to swallow the blip.
DOWNSHIFT_MUTE_S = 0.3
# Re-arm once rpm falls back to this fraction of the threshold.
REARM_FRACTION = 0.95
DEFAULT_RPM = 7000.0


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
                 tone=None) -> None:
        self.rpm = rpm
        self.enabled = enabled
        self._tone = tone if tone is not None else _default_tone()
        self._prev_gear = 0
        self._shift_above = False
        self._muted_until = 0.0
        self.beeps = 0

    def update(self, packet, now: float) -> bool:
        if not driving_gate(packet.car_on_track, packet.paused, packet.loading):
            self._prev_gear = packet.current_gear
            return False

        beep, self._shift_above, self._muted_until = should_beep(
            prev_gear=self._prev_gear,
            cur_gear=packet.current_gear,
            rpm=packet.engine_rpm,
            threshold=self.rpm,
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
        """Sound it once regardless of gate or threshold.

        For the settings screen: he is in a headset while driving and cannot
        see whether the beep fired, so the only way to know it is audible over
        the engine is to press a button and listen.
        """
        if self._tone is None:
            return False
        self._play()
        return True

    def _play(self) -> None:
        if self._tone is None:
            return
        try:
            self._tone()
        except Exception as exc:                # noqa: BLE001
            # A failed beep must never take the telemetry thread down.
            log("beep").warning("%s: %s", type(exc).__name__, exc)


def _default_tone():
    """A short square beep, or None where audio is unavailable."""
    try:
        import winsound
    except ImportError:
        return None

    def tone() -> None:
        # Non-blocking would be better, but winsound.Beep is short enough that
        # the alternative (a thread per beep) costs more than it saves.
        winsound.Beep(1800, 60)

    return tone
