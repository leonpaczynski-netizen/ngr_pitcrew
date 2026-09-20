"""The in-box refuel watch, driven by the numbers the Monza stop actually had.

Session 52, 18 Aug 2026: arrived at the box on 10.91 L, filled to 73.82 L at
1.002 L/s, fuel started moving 5.3 s after the wheels stopped.
"""
from pitcrew.race.refuel import (
    FILL_RISE_FRAMES,
    RELEASE,
    RefuelWatch,
    SHORT,
    TARGET,
    UNSIZED,
)

RATE_L_PER_S = 1.002
HZ = 60.0
PER_FRAME_L = RATE_L_PER_S / HZ


def a_watch():
    return RefuelWatch()


def drive_in(watch, litres=10.91, laps_worth=3.0):
    """Approach the box: fuel falling, car moving. Nothing should be said."""
    said = []
    fuel = litres + laps_worth
    for _ in range(300):
        fuel -= 0.01
        call = watch.note(fuel, speed_kph=180.0, target_l=61.0)
        if call:
            said.append(call)
    assert said == []
    return fuel


def dead_time(watch, fuel, seconds=5.3, target_l=61.0):
    """Wheels stopped, hose not in yet. Still nothing to say."""
    for _ in range(int(seconds * HZ)):
        assert watch.note(fuel, speed_kph=0.0, target_l=target_l) is None
    return fuel


def fill(watch, fuel, *, to, target_l=61.0, fuel_per_lap_l=5.553):
    said = []
    while fuel < to:
        fuel = min(to, fuel + PER_FRAME_L)
        call = watch.note(fuel, speed_kph=0.0, target_l=target_l,
                          fuel_per_lap_l=fuel_per_lap_l)
        if call:
            said.append((call, fuel))
    return fuel, said


def test_nothing_is_said_until_the_tank_actually_climbs():
    """The watch arms on the fuel rising, not on the car stopping - there are
    5.3 measured seconds between the two and a call in them is a call about a
    tank that is not filling."""
    watch = a_watch()
    fuel = drive_in(watch)
    dead_time(watch, fuel)
    assert watch.filling is False


def test_the_target_is_called_once_the_hose_is_in():
    watch = a_watch()
    fuel = drive_in(watch)
    fuel = dead_time(watch, fuel)
    fuel, said = fill(watch, fuel, to=30.0)
    assert [c.kind for c, _ in said] == [TARGET]
    call, at = said[0]
    assert call.call == "Fuel to 61 litres."
    # Armed a quarter of a litre in, which at 1.002 L/s is a quarter second.
    assert at - watch.started_l < 0.5
    assert "11 laps" in call.reason


def test_the_release_is_called_when_the_tank_reaches_the_target():
    watch = a_watch()
    fuel = drive_in(watch)
    fuel = dead_time(watch, fuel)
    fuel, said = fill(watch, fuel, to=73.82)
    kinds = [c.kind for c, _ in said]
    assert kinds == [TARGET, RELEASE]
    release, at = said[1]
    assert release.call == "Go."
    # At the target, never before it: being early costs fuel he cannot get
    # back, being late costs about a litre - one second in the pit lane.
    assert at >= 61.0 - 0.05
    assert at < 61.5


def test_the_release_is_said_once_and_not_every_frame_after():
    watch = a_watch()
    fuel = drive_in(watch)
    fuel = dead_time(watch, fuel)
    _, said = fill(watch, fuel, to=73.82)
    assert sum(1 for c, _ in said if c.kind == RELEASE) == 1


def test_a_tank_that_already_covers_the_stint_is_released_immediately():
    """The most valuable call in the race: every litre from here is a second
    parked, and the box call's figure was sized before the stop."""
    watch = a_watch()
    fuel = drive_in(watch, litres=64.0)
    fuel = dead_time(watch, fuel, target_l=61.0)
    _, said = fill(watch, fuel, to=70.0, target_l=61.0)
    assert [c.kind for c, _ in said] == [RELEASE]
    assert "already covers it" in said[0][0].reason


def test_no_target_means_no_invented_figure_but_not_silence():
    """He is holding the trigger on a number. One the app guessed is worse
    than none - **and so is nothing at all.**

    This used to assert silence, and silence is what the box sounded like at
    Bathurst on 20 Sep 2026 when the adviser worked perfectly: four calls
    made, four spoken, and nothing in the log, so a stop nobody could size
    and an app that had died were the same event from the cockpit. The rule
    that survives is rule 3 - no litre figure this app invented - and GT7's
    own diamond marker is accurate (§5.4), so it is what an engineer with no
    figure of his own points at. Said once, and carrying no number.
    """
    watch = a_watch()
    fuel = drive_in(watch)
    for _ in range(int(5.3 * HZ)):
        watch.note(fuel, speed_kph=0.0, target_l=None)
    said = []
    for _ in range(600):
        fuel += PER_FRAME_L
        call = watch.note(fuel, speed_kph=0.0, target_l=None)
        if call:
            said.append(call)
    assert watch.filling is True
    assert [c.kind for c in said] == [UNSIZED]
    assert not any(ch.isdigit() for ch in said[0].spoken())


def test_leaving_short_is_a_lift_and_coast_call_at_pit_exit():
    watch = a_watch()
    fuel = drive_in(watch)
    fuel = dead_time(watch, fuel)
    fuel, said = fill(watch, fuel, to=44.0)
    assert [c.kind for c, _ in said] == [TARGET]
    short = watch.left_early(fuel, fuel_per_lap_l=5.553)
    assert short is not None
    assert short.kind == SHORT
    assert short.call == "Save fuel from here."
    assert "3.1 laps" in short.reason


def test_leaving_on_target_says_nothing_at_pit_exit():
    watch = a_watch()
    fuel = drive_in(watch)
    fuel = dead_time(watch, fuel)
    fuel, _ = fill(watch, fuel, to=73.82)
    assert watch.left_early(fuel, fuel_per_lap_l=5.553) is None


def test_a_single_bad_packet_is_not_a_fill():
    """One frame is a glitch; FILL_RISE_FRAMES at 60 Hz is 50 ms of a fill
    that lasts a minute."""
    watch = a_watch()
    fuel = drive_in(watch)
    for _ in range(FILL_RISE_FRAMES - 1):
        fuel += 1.0
        watch.note(fuel, speed_kph=0.0, target_l=61.0)
    fuel -= 2.0
    assert watch.note(fuel, speed_kph=0.0, target_l=61.0) is None
    assert watch.filling is False


def test_a_rise_while_the_car_is_moving_is_not_a_fill():
    watch = a_watch()
    fuel = drive_in(watch)
    said = []
    for _ in range(600):
        fuel += PER_FRAME_L
        call = watch.note(fuel, speed_kph=120.0, target_l=61.0)
        if call:
            said.append(call)
    assert watch.filling is False
    assert said == []


def test_the_target_is_captured_once_and_does_not_wobble_mid_fill():
    """The car is stationary for the whole fill, so nothing that feeds the
    figure can move while the hose is in."""
    watch = a_watch()
    fuel = drive_in(watch)
    fuel = dead_time(watch, fuel)
    fuel, said = fill(watch, fuel, to=30.0, target_l=61.0)
    assert said[0][0].call == "Fuel to 61 litres."
    # The caller now offers a different figure. It must not be adopted: the
    # release still comes at the target he was actually given.
    fuel, more = fill(watch, fuel, to=73.82, target_l=80.0)
    assert [c.kind for c, _ in more] == [RELEASE]
    assert more[0][1] < 61.5
