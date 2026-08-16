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


# ------------------------------------------------------ the table, in settings

def test_the_table_survives_the_round_trip_through_the_store(tmp_path):
    """It is written by a tool and read back as JSON. `str(dict)` round-trips
    only through `eval`, and a settings loader that evals stored text runs
    whatever is in the database."""
    from pitcrew import settings as S
    from pitcrew.store.db import Store

    store = Store(str(tmp_path / "pitcrew.db"))
    original = S.Settings(beep_shift_points={"3247": {"3": 8250.0, "4": 8250.0}},
                          beep_short_shift_drop=650.0)
    S.save(store, original)
    back = S.load(store)
    assert back.beep_shift_points == {"3247": {"3": 8250.0, "4": 8250.0}}
    assert back.beep_short_shift_drop == 650.0


def test_a_car_with_no_measured_table_gets_an_empty_one_not_a_neighbours():
    """The whole value of a per-gear threshold is that it was measured on that
    gearbox. A table that quietly filled itself would be indistinguishable at
    the wheel from one that had been measured."""
    from pitcrew import settings as S

    s = S.Settings(beep_shift_points={"3247": {"3": 8250.0}})
    assert s.shift_points_for("3247") == {3: 8250.0}
    assert s.shift_points_for("9999") == {}
    assert s.shift_points_for(None) == {}


def test_an_unreadable_table_costs_the_beep_and_not_every_other_setting(tmp_path):
    from pitcrew import settings as S
    from pitcrew.store.db import Store

    store = Store(str(tmp_path / "pitcrew.db"))
    S.save(store, S.Settings(beep_rpm=8100.0))
    store.set_state(S.PREFIX + "beep_shift_points", "{not json at all")
    back = S.load(store)
    assert back.beep_shift_points == {}
    assert back.beep_rpm == 8100.0, "one bad table reset unrelated settings"


def test_a_shift_point_no_gt7_car_could_have_is_refused():
    from pitcrew import settings as S

    with __import__("pytest").raises(ValueError, match="not a threshold"):
        S.Settings(beep_shift_points={"3247": {"3": 250.0}}).validate()
    with __import__("pytest").raises(ValueError, match="gears 1-8"):
        S.Settings(beep_shift_points={"3247": {"11": 8250.0}}).validate()


def test_a_short_shift_saving_that_is_zero_or_negative_is_refused():
    """The live call divides by this: a zero asks for infinite rpm, and a
    negative says short-shifting BURNS fuel."""
    from pitcrew import settings as S

    for bad in (0.0, -1.5, 25.0):
        with __import__("pytest").raises(ValueError, match="short-shift saving"):
            S.Settings(short_shift_litres_per_1000rpm={"3247": bad}).validate()


# ------------------------------------------------- what the lap records

def test_a_lap_records_how_it_was_shifted_and_null_is_not_zero(tmp_path):
    """A lap driven under the app's own fuel-saving instruction is not
    evidence about the car - a short-shift costs about the same as the pace
    deficit the stint calls hunt for. Null means nobody recorded it; 0.0 means
    it was driven on the normal threshold, and they are different claims."""
    from pitcrew.store.db import Store
    from pitcrew.telemetry.session_state import Lap

    store = Store(str(tmp_path / "pitcrew.db"))
    event = store.create_event(name="Round 1", track="Monza")
    session = store.start_session(event, "practice")

    def a_lap(num, **kw):
        return Lap(lap_num=num, lap_time_ms=94_000, best_lap_ms=94_000,
                   delta_ms=0, fuel_start=40.0, fuel_end=36.6, fuel_used=3.4,
                   position=1, is_pit_lap=False, is_out_lap=False, **kw)

    store.add_lap(session, a_lap(1, short_shift_rpm=None), None)
    store.add_lap(session, a_lap(2, short_shift_rpm=0.0), None)
    store.add_lap(session, a_lap(3, short_shift_rpm=300.0), None)

    import sqlite3
    con = sqlite3.connect(str(tmp_path / "pitcrew.db"))
    seen = dict(con.execute(
        "SELECT lap_num, short_shift_rpm FROM laps ORDER BY lap_num").fetchall())
    assert seen[1] is None, "a lap nobody watched must not claim it was normal"
    assert seen[2] == 0.0
    assert seen[3] == 300.0
