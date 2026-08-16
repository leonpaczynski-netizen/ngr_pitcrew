"""The shift beep: per-gear thresholds and the live short-shift switch.

The rules the beep already had - on-track only, a downshift mute, hysteresis
rather than a level - were learned at the wheel and are covered here too,
because the per-gear change moves the threshold under all three of them and a
regression in any one is a beep firing where he has already told us it must
not.
"""
from __future__ import annotations

from pitcrew.engineer import shift_beep as SB
from pitcrew.engineer.shift_beep import ShiftBeep


class Packet:
    """The five fields the beep reads."""

    def __init__(self, *, gear=3, rpm=7000.0, on_track=True, paused=False,
                 loading=False):
        self.current_gear = gear
        self.engine_rpm = rpm
        self.car_on_track = on_track
        self.paused = paused
        self.loading = loading


def beeper(**kw) -> tuple[ShiftBeep, list]:
    played = []
    beep = ShiftBeep(tone=lambda: played.append(1), **kw)
    return beep, played


def run(beep, frames, start=100.0):
    """Feed packets a frame apart; return the laps... times each beep fired."""
    fired = []
    for index, packet in enumerate(frames):
        now = start + index / 60.0
        if beep.update(packet, now):
            fired.append((index, packet.current_gear, packet.engine_rpm))
    return fired


# --------------------------------------------------------------- per gear

def test_each_gear_beeps_at_its_own_measured_rpm():
    """One number for every gear is a compromise between shift points that
    are genuinely different. Measured on the Shelby the crossover is the same
    in all five upshifts; measured on other cars it need not be, and the beep
    must be able to say so."""
    beep, _ = beeper(rpm=9000.0, per_gear={2: 7000.0, 3: 8000.0})
    assert beep.threshold_for(2) == 7000.0
    assert beep.threshold_for(3) == 8000.0


def test_a_gear_with_no_measured_figure_falls_back_rather_than_inventing_one():
    """A made-up number for one gear inside a measured table is the worst of
    both, because at the wheel it is indistinguishable from the measured
    ones."""
    beep, _ = beeper(rpm=8640.0, per_gear={2: 7000.0})
    assert beep.threshold_for(2) == 7000.0
    assert beep.threshold_for(5) == 8640.0


def test_the_beep_actually_fires_at_the_gears_own_threshold():
    beep, played = beeper(rpm=9000.0, per_gear={3: 7500.0, 4: 8200.0})
    # Third gear, climbing past 7500: fires.
    frames = [Packet(gear=3, rpm=rpm) for rpm in (7000, 7400, 7600, 7800)]
    fired = run(beep, frames)
    assert len(fired) == 1 and fired[0][2] == 7600

    # Fourth gear at the same rpm is below ITS threshold: silent.
    beep, _ = beeper(rpm=9000.0, per_gear={3: 7500.0, 4: 8200.0})
    frames = [Packet(gear=4, rpm=rpm) for rpm in (7000, 7400, 7600, 7800)]
    assert run(beep, frames) == []


# ----------------------------------------------------------- short-shifting

def test_short_shifting_moves_every_threshold_down_and_back():
    """The live switch. He prefers saving fuel this way over leaning the map,
    because a map step costs power everywhere and this costs only the top of
    each gear."""
    beep, _ = beeper(rpm=8000.0, per_gear={3: 8250.0}, short_shift_drop_rpm=500.0)
    assert beep.threshold_for(3) == 8250.0
    beep.short_shifting = True
    assert beep.threshold_for(3) == 7750.0
    assert beep.threshold_for(6) == 7500.0, "the fallback moves too"
    beep.short_shifting = False
    assert beep.threshold_for(3) == 8250.0


def test_a_gear_can_carry_its_own_measured_short_shift_drop():
    beep, _ = beeper(rpm=8000.0, per_gear={2: 8250.0, 3: 8250.0},
                     short_shift_drop_rpm=500.0)
    beep.short_shift_drop_per_gear = {3: 900.0}
    beep.short_shifting = True
    assert beep.threshold_for(2) == 7750.0
    assert beep.threshold_for(3) == 7350.0


def test_short_shifting_cannot_drag_the_beep_out_of_the_powerband():
    """Short-shifting out of the powerband is not fuel saving, it is driving
    badly, and an engineer that asks for it has stopped being useful."""
    beep, _ = beeper(rpm=3200.0, short_shift_drop_rpm=2000.0)
    beep.short_shifting = True
    assert beep.threshold_for(3) == SB.MIN_THRESHOLD_RPM


def test_short_shifting_makes_it_fire_earlier_on_the_same_climb():
    climb = [Packet(gear=3, rpm=rpm)
             for rpm in (7000, 7400, 7800, 8100, 8400)]
    beep, _ = beeper(rpm=9000.0, per_gear={3: 8250.0})
    assert [f[2] for f in run(beep, climb)] == [8400]

    beep, _ = beeper(rpm=9000.0, per_gear={3: 8250.0}, short_shift_drop_rpm=500.0)
    beep.short_shifting = True
    assert [f[2] for f in run(beep, climb)] == [7800]


# ------------------------------------- the rules learned at the wheel, per gear

def test_the_downshift_mute_survives_per_gear_thresholds():
    """Blipping the throttle on a downshift spikes the rpm past the threshold,
    and without the mute every heel-and-toe downshift fired a beep telling him
    to upshift."""
    beep, _ = beeper(rpm=9000.0, per_gear={2: 7000.0, 3: 8000.0})
    frames = [Packet(gear=3, rpm=7000.0),
              Packet(gear=2, rpm=7000.0),      # downshift
              Packet(gear=2, rpm=7600.0),      # the blip, past second's 7000
              Packet(gear=2, rpm=7400.0)]
    assert run(beep, frames) == [], "the downshift blip fired a beep"


def test_hysteresis_survives_per_gear_thresholds():
    """Sitting on the limiter must beep once, not sixty times a second."""
    beep, _ = beeper(rpm=9000.0, per_gear={3: 7500.0})
    frames = [Packet(gear=3, rpm=7000.0)] + [Packet(gear=3, rpm=7900.0)] * 30
    assert len(run(beep, frames)) == 1


def test_it_re_arms_once_the_rpm_drops_back():
    beep, _ = beeper(rpm=9000.0, per_gear={3: 7500.0})
    frames = ([Packet(gear=3, rpm=7000.0)] + [Packet(gear=3, rpm=7900.0)] * 5
              + [Packet(gear=3, rpm=6800.0)] * 5
              + [Packet(gear=3, rpm=7900.0)] * 5)
    assert len(run(beep, frames)) == 2


def test_nothing_beeps_off_track_whatever_the_table_says():
    beep, _ = beeper(rpm=9000.0, per_gear={3: 7000.0})
    frames = [Packet(gear=3, rpm=8500.0, on_track=False)] * 5
    assert run(beep, frames) == []
