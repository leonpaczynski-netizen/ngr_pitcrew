"""The shift beep: per-gear thresholds and the live short-shift switch.

The rules the beep already had - on-track only, a downshift mute, hysteresis
rather than a level - were learned at the wheel and are covered here too,
because the per-gear change moves the threshold under all three of them and a
regression in any one is a beep firing where he has already told us it must
not.
"""
from __future__ import annotations

import time

import pytest

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
    beep, _ = beeper(per_gear={2: 7000.0, 3: 8000.0})
    assert beep.threshold_for(2) == 7000.0
    assert beep.threshold_for(3) == 8000.0


def test_a_gear_with_no_measured_figure_is_silent():
    """**Changed 21 Aug 2026 at the driver's instruction**, and the old
    behaviour is worth stating because it sounded reasonable.

    An unmeasured gear used to fall back to one global rpm, and before that to
    GT7's own shift light. Both sound at the wheel exactly like a measured
    threshold and neither is one - and the whole reason this is a table is that
    one car wants the limiter in every gear while another wants 8250 in all
    five. A fallback quietly told him a number nobody had taken on that
    gearbox.

    The thresholds are issued with the setup, because a shift point belongs
    to the gearbox: change a ratio and it moves. No table issued means the
    box has not been measured, and silence is the honest answer.
    """
    beep, played = beeper(per_gear={2: 7000.0})
    assert beep.threshold_for(2) == 7000.0
    assert beep.threshold_for(5) is None

    # And it does not merely report None - it does not sound.
    frames = [Packet(gear=5, rpm=rpm) for rpm in (8000, 8500, 8800, 9200)]
    assert run(beep, frames) == []
    assert played == []


def test_a_gearbox_with_no_table_at_all_never_beeps():
    """The normal state of a gearbox nobody has measured yet."""
    beep, played = beeper(per_gear={})
    for gear in (1, 2, 3, 4, 5, 6):
        assert beep.threshold_for(gear) is None
    frames = [Packet(gear=3, rpm=rpm) for rpm in (7000, 8000, 8600, 9000)]
    assert run(beep, frames) == []
    assert played == []


def test_the_beep_actually_fires_at_the_gears_own_threshold():
    beep, played = beeper(per_gear={3: 7500.0, 4: 8200.0})
    # Third gear, climbing past 7500: fires.
    frames = [Packet(gear=3, rpm=rpm) for rpm in (7000, 7400, 7600, 7800)]
    fired = run(beep, frames)
    assert len(fired) == 1 and fired[0][2] == 7600

    # Fourth gear at the same rpm is below ITS threshold: silent.
    beep, _ = beeper(per_gear={3: 7500.0, 4: 8200.0})
    frames = [Packet(gear=4, rpm=rpm) for rpm in (7000, 7400, 7600, 7800)]
    assert run(beep, frames) == []


# ----------------------------------------------------------- short-shifting

def test_short_shifting_moves_every_threshold_down_and_back():
    """The live switch. He prefers saving fuel this way over leaning the map,
    because a map step costs power everywhere and this costs only the top of
    each gear."""
    beep, _ = beeper(per_gear={3: 8250.0}, short_shift_drop_rpm=500.0)
    assert beep.threshold_for(3) == 8250.0
    beep.short_shifting = True
    assert beep.threshold_for(3) == 7750.0
    # Sixth has no measured threshold, so there is nothing to move: short
    # shifting cannot conjure a beep for a gear that does not have one.
    assert beep.threshold_for(6) is None
    beep.short_shifting = False
    assert beep.threshold_for(3) == 8250.0


def test_a_gear_can_carry_its_own_measured_short_shift_drop():
    beep, _ = beeper(per_gear={2: 8250.0, 3: 8250.0},
                     short_shift_drop_rpm=500.0)
    beep.short_shift_drop_per_gear = {3: 900.0}
    beep.short_shifting = True
    assert beep.threshold_for(2) == 7750.0
    assert beep.threshold_for(3) == 7350.0


def test_short_shifting_cannot_drag_the_beep_out_of_the_powerband():
    """Short-shifting out of the powerband is not fuel saving, it is driving
    badly, and an engineer that asks for it has stopped being useful."""
    beep, _ = beeper(per_gear={3: 3200.0},
                     short_shift_drop_rpm=2000.0)
    beep.short_shifting = True
    assert beep.threshold_for(3) == SB.MIN_THRESHOLD_RPM


def test_short_shifting_makes_it_fire_earlier_on_the_same_climb():
    climb = [Packet(gear=3, rpm=rpm)
             for rpm in (7000, 7400, 7800, 8100, 8400)]
    beep, _ = beeper(per_gear={3: 8250.0})
    assert [f[2] for f in run(beep, climb)] == [8400]

    beep, _ = beeper(per_gear={3: 8250.0}, short_shift_drop_rpm=500.0)
    beep.short_shifting = True
    assert [f[2] for f in run(beep, climb)] == [7800]


# ------------------------------------- the rules learned at the wheel, per gear

def test_the_downshift_mute_survives_per_gear_thresholds():
    """Blipping the throttle on a downshift spikes the rpm past the threshold,
    and without the mute every heel-and-toe downshift fired a beep telling him
    to upshift."""
    beep, _ = beeper(per_gear={2: 7000.0, 3: 8000.0})
    frames = [Packet(gear=3, rpm=7000.0),
              Packet(gear=2, rpm=7000.0),      # downshift
              Packet(gear=2, rpm=7600.0),      # the blip, past second's 7000
              Packet(gear=2, rpm=7400.0)]
    assert run(beep, frames) == [], "the downshift blip fired a beep"


def test_hysteresis_survives_per_gear_thresholds():
    """Sitting on the limiter must beep once, not sixty times a second."""
    beep, _ = beeper(per_gear={3: 7500.0})
    frames = [Packet(gear=3, rpm=7000.0)] + [Packet(gear=3, rpm=7900.0)] * 30
    assert len(run(beep, frames)) == 1


def test_it_re_arms_once_the_rpm_drops_back():
    beep, _ = beeper(per_gear={3: 7500.0})
    frames = ([Packet(gear=3, rpm=7000.0)] + [Packet(gear=3, rpm=7900.0)] * 5
              + [Packet(gear=3, rpm=6800.0)] * 5
              + [Packet(gear=3, rpm=7900.0)] * 5)
    assert len(run(beep, frames)) == 2


def test_nothing_beeps_off_track_whatever_the_table_says():
    beep, _ = beeper(per_gear={3: 7000.0})
    frames = [Packet(gear=3, rpm=8500.0, on_track=False)] * 5
    assert run(beep, frames) == []


# ------------------------------------------- the table, as the engineer issues it

def test_the_table_survives_the_round_trip_through_the_store(tmp_path):
    """**Moved off the setup sheet and into its own record, 5 Sep 2026.**

    It is written over MCP and read back as JSON, and JSON turns integer keys
    into strings - so a table has to come home keyed the way it went out, or
    every lookup by gear number silently misses.
    """
    from pitcrew.engineer.shift_points import ShiftPoints
    from pitcrew.store.db import Store

    store = Store(str(tmp_path / "pitcrew.db"))
    store.save_shift_points(ShiftPoints(
        car_name="Ford Shelby GT350R '16", circuit_key="yas-marina",
        performance={3: 8250.0, 4: 8250.0}, fuel_saving={4: 7500.0}))
    back = store.shift_points_for("Ford Shelby GT350R '16", "yas-marina")
    assert back.performance == {3: 8250.0, 4: 8250.0}
    assert all(isinstance(gear, int) for gear in back.performance)
    assert back.drops() == {4: 750.0}
    store.close()


def test_a_car_with_no_table_gets_an_empty_one_not_a_neighbours(tmp_path):
    """The whole value of a per-gear threshold is that somebody designed it
    for that gearbox. A table that quietly filled itself would be
    indistinguishable at the wheel from one that had been - and there is no
    fallback left to fill it from."""
    from pitcrew.engineer.shift_points import ShiftPoints
    from pitcrew.store.db import Store

    store = Store(str(tmp_path / "pitcrew.db"))
    store.save_shift_points(ShiftPoints(
        car_name="A", circuit_key="monza", performance={3: 8250.0}))
    assert store.shift_points_for("A", "monza").performance == {3: 8250.0}
    assert store.shift_points_for("B", "monza") is None
    store.close()


def test_a_table_does_not_cross_circuits(tmp_path):
    """A gearbox is cut for the circuit, so the same car at two tracks is two
    boxes. Returning the other one's rpm would sound at the wheel exactly like
    a table designed for the box that is fitted."""
    from pitcrew.engineer.shift_points import ShiftPoints
    from pitcrew.store.db import Store

    store = Store(str(tmp_path / "pitcrew.db"))
    store.save_shift_points(ShiftPoints(
        car_name="A", circuit_key="monza", performance={6: 8000.0}))
    assert store.shift_points_for("A", "daytona-road") is None
    assert store.shift_points_for("A", None) is None
    store.close()


def test_re_issuing_replaces_rather_than_accumulates(tmp_path):
    """sqlite counts two NULLs as distinct in a unique index, which is how
    `setup_sheets` lost sheets before v8. The circuit is stored as the empty
    string when there is none, so the upsert keeps matching."""
    from pitcrew.engineer.shift_points import ShiftPoints
    from pitcrew.store.db import Store

    store = Store(str(tmp_path / "pitcrew.db"))
    for rpm in (8000.0, 8200.0, 8400.0):
        store.save_shift_points(ShiftPoints(car_name="A", performance={6: rpm}))
    assert len(store.list_shift_points("A")) == 1
    assert store.shift_points_for("A").performance == {6: 8400.0}
    store.close()


def test_a_shift_point_no_gt7_car_could_have_is_refused():
    """Refused where it is issued, rather than stored and beeped at."""
    import pytest as _pytest

    from pitcrew.engineer.shift_points import ShiftPoints

    with _pytest.raises(Exception, match="not an upshift rpm"):
        ShiftPoints(car_name="A", performance={3: 250_000.0}).validate()
    with _pytest.raises(Exception, match="keyed by gear number"):
        ShiftPoints(car_name="A", performance={11: 8250.0}).validate()


def test_a_fuel_saving_point_above_its_own_performance_point_is_refused():
    """The two columns swapped. It is silent at the wheel, and it costs fuel
    in the direction the driver was told it saved."""
    import pytest as _pytest

    from pitcrew.engineer.shift_points import ShiftPoints

    with _pytest.raises(Exception, match="not below performance"):
        ShiftPoints(car_name="A", performance={3: 8000.0},
                    fuel_saving={3: 8400.0}).validate()
    # Equal is not a saving either.
    with _pytest.raises(Exception, match="not below performance"):
        ShiftPoints(car_name="A", performance={3: 8000.0},
                    fuel_saving={3: 8000.0}).validate()
    # And a gear performance never named cannot be short-shifted.
    with _pytest.raises(Exception, match="names gears performance does not"):
        ShiftPoints(car_name="A", performance={3: 8000.0},
                    fuel_saving={4: 7000.0}).validate()


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


# ------------------------------ not being cut off by a device list rebuild

def test_the_beep_holds_a_device_rebuild_off_while_it_sounds(monkeypatch):
    """`sd._terminate()` closes every open stream in the process, silently,
    and the transducer watchdog now rebuilds the device list mid-race. Sixty
    milliseconds is worth waiting for and costs a recovery nothing.

    Deliberately NOT re-fired if it is cut, unlike a spoken line: a beep is an
    instruction about the rpm the engine is at right now, and one played late
    tells him to shift in the wrong place.
    """
    import threading

    from pitcrew.engineer import audio_devices

    order: list[str] = []
    # Only this thread's events: a leftover "PitCrewBeep" thread from another
    # test would otherwise interleave its own open into the list.
    mine = threading.get_ident()

    def note(event):
        if threading.get_ident() == mine:
            order.append(event)

    class _Stream:
        def write(self, _samples):
            note("write")

        def stop(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(audio_devices, "open_output",
                        lambda _rate: note("open") or _Stream())
    monkeypatch.setattr(audio_devices, "begin_playback",
                        lambda what: note(f"gate up: {what}")
                        or audio_devices.Playback(what))
    monkeypatch.setattr(audio_devices, "end_playback",
                        lambda p: note("gate down"))

    SB._TonePlayer(ms=1)._render()
    # The gate goes up AFTER the open, never before: the open goes through the
    # enumeration lock and a rebuild waits on the gate from inside it, so the
    # other order is an AB-BA deadlock.
    assert order == ["open", f"gate up: {SB.BEEP}", "write", "gate down"]


def test_a_beep_cut_by_a_rebuild_is_not_fired_again(monkeypatch):
    from pitcrew.engineer import audio_devices

    class _Stream:
        def __init__(self):
            self.writes = 0

        def write(self, _samples):
            self.writes += 1

        def stop(self):
            pass

        def close(self):
            pass

    stream = _Stream()
    monkeypatch.setattr(audio_devices, "open_output", lambda _rate: stream)

    def cut(what):
        playback = audio_devices.Playback(what)
        playback.interrupted = True
        return playback

    monkeypatch.setattr(audio_devices, "begin_playback", cut)
    SB._TonePlayer(ms=1)._render()          # raises nothing, retries nothing
    assert stream.writes == 1


# ---------------------------------------------------------------- top gear
#
# There is no seventh gear in a six-speed. A beep there is an instruction that
# cannot be obeyed, and it lands on the fastest part of the lap.


def test_top_gear_is_silent_and_the_gear_below_it_is_not():
    table = {5: 8000.0, 6: 8000.0}
    beep, played = beeper(per_gear=table, top_gear=6)
    assert not beep.update(Packet(gear=6, rpm=8600.0), 100.0)
    assert played == []
    # Same rpm, one gear down: this one has somewhere to go.
    beep, played = beeper(per_gear=table, top_gear=6)
    assert beep.update(Packet(gear=5, rpm=8600.0), 100.0)
    assert played == [1]


def test_an_unknown_gearbox_beeps_in_every_gear():
    """None is not "no gears" - it is "not read yet", and going quiet on it
    would be a silence nobody could account for."""
    beep, played = beeper(per_gear={8: 8000.0}, top_gear=None)
    assert beep.update(Packet(gear=8, rpm=8600.0), 100.0)
    assert played == [1]


def test_the_top_gear_does_not_re_time_the_beeps_after_it():
    """Suppressing the sound must not disturb the hysteresis.

    The top gear arms `shift_above` exactly as it would have done had it
    beeped, so that the next gear the driver takes behaves identically whether
    or not the lap passed through top. A version that returned early left the
    state stale and made sixth gear silently change when fourth beeped.
    """
    def sequence(top):
        beep, _ = beeper(top_gear=top)
        frames = [Packet(gear=6, rpm=8600.0),      # top: no sound either way
                  Packet(gear=6, rpm=8600.0),
                  Packet(gear=4, rpm=6000.0),      # downshift
                  *[Packet(gear=4, rpm=6000.0)] * 30,   # clear the mute
                  Packet(gear=4, rpm=8600.0)]      # due again
        return run(beep, frames)

    assert [f[1:] for f in sequence(6)] == [f[1:] for f in sequence(None)][1:]


def test_the_gear_count_is_read_off_the_packet():
    beep, played = beeper()
    packet = Packet(gear=6, rpm=8600.0)
    packet.gear_ratios = [2.7, 1.9, 1.5, 1.2, 1.1, 1.0, None, None]
    assert not beep.update(packet, 100.0)
    assert beep.top_gear == 6
    assert played == []


def test_an_empty_ratio_table_keeps_the_gearbox_it_had():
    """The car has not loaded yet. Forgetting the gearbox every time the
    session pauses would let the top gear beep again on the way back in."""
    beep, _ = beeper()
    loaded = Packet(gear=3, rpm=5000.0)
    loaded.gear_ratios = [2.7, 1.9, 1.5, 1.2, 1.1, 1.0, None, None]
    beep.update(loaded, 100.0)
    blank = Packet(gear=3, rpm=5000.0)
    blank.gear_ratios = [None] * 8
    beep.update(blank, 100.1)
    assert beep.top_gear == 6


# --------------------------------------------------------------- priority
#
# The beep and the engineer share one card. Until now the beep WAITED for the
# sentence, which meant a two-second call did not delay the beep so much as
# destroy it: a beep played late names an rpm the engine has already left, and
# it sounds exactly like a beep that arrived on time.


def test_the_beep_asks_for_the_card_while_it_waits():
    """The claim has to be up while the beep is blocked, not after - the voice
    reads it between chunks and would otherwise never see it."""
    import threading

    from pitcrew.engineer import audio_devices

    device = audio_devices.output_device()
    lock = audio_devices.lock_for(device)
    seen = threading.Event()
    released = threading.Event()

    player = SB._TonePlayer()
    player._render_locked = lambda: None

    lock.acquire()
    try:
        worker = threading.Thread(target=player._render, daemon=True)
        worker.start()
        # The voice's inner loop, standing in for a chunk boundary.
        for _ in range(200):
            if audio_devices.priority_wanted(device):
                seen.set()
                break
            time.sleep(0.001)
    finally:
        lock.release()
        released.set()
    worker.join(timeout=2.0)
    assert seen.is_set(), "the beep never asked for the card"
    assert not audio_devices.priority_wanted(device), "the claim outlived it"


def test_a_beep_that_cannot_be_played_on_time_is_dropped_not_queued():
    """`PRIORITY_WAIT_S` is a deadline, and past it the beep is wrong rather
    than late. The count is what makes the trade-off visible."""
    import threading

    from pitcrew.engineer import audio_devices

    lock = audio_devices.lock_for(audio_devices.output_device())
    player = SB._TonePlayer()
    player._render_locked = lambda: pytest.fail("played after the deadline")

    lock.acquire()
    try:
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            player._render()
        waited = time.monotonic() - started
    finally:
        lock.release()
    assert player.dropped == 1
    assert waited < SB.PRIORITY_WAIT_S + 0.5


def test_the_voice_stands_aside_for_a_pending_beep():
    """It marks the line cut rather than dropping it - `LineCut` re-queues it
    with its original timestamp, so staleness decides whether it is still
    true. And it closes its OWN stream: a beep reaching into another thread's
    blocking write is the close-from-send deadlock."""
    from pitcrew.engineer import audio_devices, voice

    class Line:
        interrupted = False

    line = Line()
    assert voice._yield_to_priority(line) is False
    assert line.interrupted is False

    with audio_devices.priority_on(audio_devices.output_device()):
        assert voice._yield_to_priority(line) is True
    assert line.interrupted is True
    assert voice._yield_to_priority(None) is False
