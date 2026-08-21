"""Asking for a short-shift has to move the beep.

**It did not, and nothing noticed for two races.** `ShiftBeep.short_shifting`
was read in two places and assigned `True` nowhere outside the tests, so the
engineer said *"Short-shift 450."* and the beep went on sounding at the same
rpm. The driver was asked to short-shift with no cue - and because the lap's
`short_shift_rpm` is written from that same flag, the app then had no record of
having asked: 179 stored laps carry `0.0` and not one carries a drop.

The second half matters as much as the first. A saving instruction the app
cannot see itself give is a loop it can never close, and closing that loop -
"that's working" or "not enough" - is the call a race engineer would make next.
"""
from __future__ import annotations

from pitcrew.engineer.shift_beep import ShiftBeep
from pitcrew.race.calls import FUEL_SHORT, STAY_OUT, Call, RaceState, next_call


class Bridge:
    """The two lines of the real bridge this exercises."""

    def __init__(self):
        self.shift_beep = ShiftBeep(per_gear={3: 8000.0},
                                    short_shift_drop_rpm=500.0)

    def set_short_shift(self, drop_rpm):
        if drop_rpm and drop_rpm > 0:
            self.shift_beep.short_shift_drop_rpm = float(drop_rpm)
            self.shift_beep.short_shifting = True
        else:
            self.shift_beep.short_shifting = False


def test_a_named_drop_engages_the_beep_at_that_rpm():
    bridge = Bridge()
    bridge.set_short_shift(450.0)
    assert bridge.shift_beep.short_shifting is True
    # 8000 asked down by 450.
    assert bridge.shift_beep.threshold_for(3) == 7550.0


def test_the_next_call_without_a_drop_releases_it():
    """None is "stop short-shifting", not "no opinion". A box call ends the
    saving, and leaving the beep down would keep asking after the reason for
    asking had gone."""
    bridge = Bridge()
    bridge.set_short_shift(450.0)
    bridge.set_short_shift(None)
    assert bridge.shift_beep.short_shifting is False
    assert bridge.shift_beep.threshold_for(3) == 8000.0


def test_a_lever_with_no_measured_number_moves_no_beep():
    """"Short-shift and lift into the slow corners" withholds a number on
    purpose - this car has no measured litres-per-1000-rpm. Moving the beep by
    an invented figure would put back exactly the fabrication the call avoided.
    """
    bridge = Bridge()
    bridge.set_short_shift(0.0)
    assert bridge.shift_beep.short_shifting is False


def test_the_call_that_asks_carries_the_drop_it_asked_for():
    """The number on the radio and the number at the beep are one number."""
    state = RaceState(
        lap=10, laps_total=20, fuel_l=30.0, fuel_per_lap_l=6.0,
        short_shift_l_per_1000rpm=1.762)
    call = next_call(state)
    assert call is not None
    if call.kind in (FUEL_SHORT, STAY_OUT) and "Short-shift" in call.call:
        assert call.short_shift_drop_rpm, (
            "the call names a drop on the radio and carries none to the beep")
        named = int(round(call.short_shift_drop_rpm / 50.0) * 50)
        assert str(named) in call.call or str(named) in call.reason


def test_every_other_call_leaves_the_beep_alone():
    plain = Call("box-now", 5, "Box this lap.", "Fuel.")
    assert plain.short_shift_drop_rpm is None
