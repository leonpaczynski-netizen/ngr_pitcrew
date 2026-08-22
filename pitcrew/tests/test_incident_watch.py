"""P6 - noticing an off while it is still happening, and resetting what it made stale.

`analysis/incidents.py` finds incidents afterwards and finds them well. The
handover named the gap: *after a spin or an off, the plan's assumptions are
stale and nothing notices* - and `coordinator.py` carried the same fact as a
comment beside the pace record, "incidents cannot be flagged live".

The tests that matter are the refusals. A detector that strikes a clean lap is
worse than one that misses an incident: the aggregate quietly loses a
measurement nobody knows is gone.
"""
from __future__ import annotations

import pytest

from pitcrew.analysis.incidents import CRAWL_KPH, CRAWL_MIN_S, LAUNCH_KPH
from pitcrew.race.calls import (
    HIGH,
    INCIDENT,
    INCIDENT_WORTH_SAYING_MS,
    RaceState,
    _incident,
    clear_stint,
    next_call,
)
from pitcrew.race.incident_watch import IncidentWatch


class P:
    """A frame. Only the four channels the watch reads."""

    def __init__(self, speed_kmh, *, paused=False, loading=False,
                 on_track=True):
        self.speed_kmh = speed_kmh
        self.paused = paused
        self.loading = loading
        self.car_on_track = on_track


def drive(watch, frames, *, start=0.0, step=1 / 60.0, in_pit=False):
    """Feed frames at 60 Hz. Returns the times an incident was reported."""
    fired = []
    now = start
    for packet in frames:
        if watch.update(packet, now, in_pit=in_pit):
            fired.append(now)
        now += step
    return fired


def under_way(watch, now=0.0, step=1 / 60.0):
    """Get the car moving, so the launch guard is satisfied."""
    drive(watch, [P(LAUNCH_KPH + 20)] * 10, start=now, step=step)
    return now + 10 * step


# ------------------------------------------------------------- it does fire

def test_a_car_that_stops_mid_lap_is_an_incident():
    watch = IncidentWatch()
    at = under_way(watch)
    fired = drive(watch, [P(0.0)] * 120, start=at)
    assert len(fired) == 1


def test_a_crawl_is_enough_and_a_standstill_is_not_required():
    """`CRAWL_KPH` sits in the empty band between the slowest corner anyone
    drives and a car that has stopped - so a car limping is caught too."""
    watch = IncidentWatch()
    at = under_way(watch)
    assert drive(watch, [P(CRAWL_KPH - 1)] * 120, start=at)


def test_one_incident_per_lap_however_long_the_car_sits_there():
    """A car in the gravel for twenty seconds is one event, not twelve
    hundred."""
    watch = IncidentWatch()
    at = under_way(watch)
    assert len(drive(watch, [P(0.0)] * 1200, start=at)) == 1


def test_the_next_lap_can_have_its_own():
    watch = IncidentWatch()
    at = under_way(watch)
    drive(watch, [P(0.0)] * 120, start=at)
    watch.new_lap()
    at = under_way(watch, now=at + 3.0)
    assert drive(watch, [P(0.0)] * 120, start=at)


# ------------------------------------------------------- it refuses to fire

def test_the_grid_is_not_an_incident():
    """**The trap `analysis/incidents.py` documents.** Without the launch
    guard the box, the grid and a session joined stationary are all incidents.
    """
    watch = IncidentWatch()
    assert not drive(watch, [P(0.0)] * 600)


def test_a_slow_corner_is_not_an_incident():
    """The slowest corner on any circuit in the capture set is around
    60 km/h, against a threshold of 15."""
    watch = IncidentWatch()
    at = under_way(watch)
    assert not drive(watch, [P(55.0)] * 600, start=at)


def test_a_brief_dip_is_not_an_incident():
    watch = IncidentWatch()
    at = under_way(watch)
    frames = int(CRAWL_MIN_S * 60) - 5
    assert not drive(watch, [P(2.0)] * frames, start=at)


def test_a_pause_is_not_a_thirty_second_crawl():
    """**GT7 keeps sending while paused and the car reads 0 km/h throughout.**
    A clock that ran across one would make every pause an incident."""
    watch = IncidentWatch()
    at = under_way(watch)
    assert not drive(watch, [P(0.0, paused=True)] * 1800, start=at)


def test_loading_and_being_off_track_are_the_same_refusal():
    for kwargs in ({"loading": True}, {"on_track": False}):
        watch = IncidentWatch()
        at = under_way(watch)
        assert not drive(watch, [P(0.0, **kwargs)] * 600, start=at)


def test_a_pit_stop_is_a_car_stationary_by_design():
    """The pit lap is already excluded on its own account."""
    watch = IncidentWatch()
    at = under_way(watch)
    assert not drive(watch, [P(0.0)] * 600, start=at, in_pit=True)


def test_a_pause_in_the_middle_of_a_crawl_starts_the_clock_again():
    """Otherwise a pause taken while stopped would confirm the incident the
    frames either side of it had not earned."""
    watch = IncidentWatch()
    at = under_way(watch)
    half = int(CRAWL_MIN_S * 60 / 2)
    frames = ([P(0.0)] * half + [P(0.0, paused=True)] * 60
              + [P(0.0)] * (half - 2))
    assert not drive(watch, frames, start=at)


def test_a_reset_forgets_that_the_car_ever_moved():
    watch = IncidentWatch()
    at = under_way(watch)
    watch.reset()
    assert not drive(watch, [P(0.0)] * 600, start=at)


def test_no_packet_is_not_a_crash():
    assert IncidentWatch().update(None, 0.0) is False


# ---------------------------------------------------------------- the call

def test_it_names_the_lap_and_what_it_cost():
    state = RaceState(lap=12, incident_lap=12, incident_cost_ms=14200)
    call = _incident(state)
    assert call.kind == INCIDENT and call.confidence == HIGH
    assert "Lap 12 is out" in call.call
    assert "14 seconds" in call.reason


def test_with_no_pace_reference_it_reports_without_a_figure():
    """A number the race has not earned must not be spoken beside a lap that
    is out either way - the exclusion is not in the driver's gift."""
    call = _incident(RaceState(lap=12, incident_lap=12, incident_cost_ms=None))
    assert "Lap 12 is out" in call.call
    assert not any(ch.isdigit() for ch in call.reason)


def test_a_loss_inside_his_own_noise_carries_no_figure():
    """sd 0.918 s lap to lap, so under three seconds is inside the spread of
    laps he drives without noticing."""
    call = _incident(RaceState(lap=9, incident_lap=9,
                               incident_cost_ms=INCIDENT_WORTH_SAYING_MS - 1))
    assert not any(ch.isdigit() for ch in call.reason)


def test_the_app_does_not_announce_what_he_told_it():
    """He said "I went off" and was answered then. Saying it again is the
    engineer talking to himself."""
    state = RaceState(lap=12, incident_lap=12, incident_cost_ms=14200,
                      incident_reported=True)
    assert _incident(state) is None
    # Nothing will be spoken, so nothing will be recorded, so this is the one
    # branch that must still clear the state itself.
    assert state.incident_lap is None


def test_it_is_true_exactly_once_and_only_once_it_is_SAID():
    """**The defect this replaced.** It used to clear the state while the call
    was being BUILT - and `next_call` builds every candidate and then ranks -
    so an incident that lost one crossing to a box call was lost outright.
    Only the call actually made may record that it was made."""
    state = RaceState(lap=12, incident_lap=12, incident_cost_ms=9000)
    first = _incident(state)
    assert first is not None
    # Not spoken: still true, still offered on the next crossing.
    assert _incident(state) is not None
    state.record(first)
    assert _incident(state) is None


def test_a_stop_drops_an_incident_nobody_got_round_to_saying():
    """"Lap 12 is out" said on the way out of the pits is news about a lap two
    minutes gone."""
    state = RaceState(lap=12, incident_lap=12, incident_cost_ms=9000)
    clear_stint(state, tyres_changed=True)
    assert state.incident_lap is None
    assert _incident(state) is None


def test_it_reaches_the_ranking():
    state = RaceState(lap=12, laps_total=30, incident_lap=12,
                      incident_cost_ms=9000, fuel_l=70.0,
                      fuel_per_lap_l=3.0)
    call = next_call(state)
    assert call is not None and call.kind == INCIDENT


def test_nothing_is_said_in_the_pits_or_after_the_flag():
    for field in ("in_pit", "finished"):
        state = RaceState(lap=12, incident_lap=12, incident_cost_ms=9000)
        setattr(state, field, True)
        assert _incident(state) is None


# ------------------------------------------------ what the coordinator does
#
# The reset half of P6. An incident lap must not enter the pace record, must
# be costed against the pace that excludes it, and must re-arm the temperature
# occasions - a trip through the grass leaves the set at a temperature the
# stint's earlier calls were not about.

from pitcrew.race.coordinator import RaceCoordinator, RacePhase       # noqa: E402
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent  # noqa: E402


def a_plan() -> dict:
    return {"stints": [
        {"laps": 10, "compound": "RM", "fuel_l": 37.4, "start_lap": 1},
        {"laps": 10, "compound": "RS", "fuel_l": 37.4, "start_lap": 11},
    ]}


def lap_event(lap_num: int, lap_time_ms: int = 94_000) -> SessionEvent:
    return SessionEvent(EventKind.LAP_COMPLETED, {"lap": Lap(
        lap_num=lap_num, lap_time_ms=lap_time_ms, best_lap_ms=94_000,
        delta_ms=0, fuel_start=40.0, fuel_end=36.6, fuel_used=3.4,
        position=3, is_pit_lap=False, is_out_lap=False)})


def a_running_race() -> RaceCoordinator:
    from pitcrew.race.coordinator import PlanContext

    context = PlanContext(car="RSR", track="Monza", layout=None,
                          race_laps=20)
    race = RaceCoordinator(a_plan(), fuel_per_lap_l=3.4)
    race.arm(context, context)
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    assert race.phase is RacePhase.RUNNING or race.running
    return race


def clean_laps(race, count, first=2):
    for lap in range(first, first + count):
        race.handle(lap_event(lap))


def test_the_incident_lap_stays_out_of_the_pace_record():
    """**The comment this change came from.** The pace median had to absorb
    incidents as outliers because nothing could flag one live."""
    race = a_running_race()
    clean_laps(race, 6)
    before = race.representative_pace_ms()
    race.note_incident()
    race.handle(lap_event(8, lap_time_ms=112_000))
    assert race.representative_pace_ms() == before


def test_a_clean_lap_still_enters_it():
    race = a_running_race()
    clean_laps(race, 6)
    race.handle(lap_event(8, lap_time_ms=94_500))
    assert race.representative_pace_ms() is not None


def test_the_cost_is_measured_against_the_pace_that_excludes_it():
    race = a_running_race()
    clean_laps(race, 6)
    pace = race.representative_pace_ms()
    race.note_incident()
    race.handle(lap_event(8, lap_time_ms=pace + 15_000))
    # Read off the state BEFORE anything records the call - `record` clears it,
    # and on a lap where a box call outranks it nothing records it at all.
    assert race.state.incident_lap == 8
    assert race.state.incident_cost_ms == pytest.approx(15_000, abs=600)


def test_a_lap_that_lost_nothing_is_costed_at_nothing():
    """It is still out - the detector saw the car stop - but there is no
    figure to put on it."""
    race = a_running_race()
    clean_laps(race, 6)
    race.note_incident()
    race.handle(lap_event(8, lap_time_ms=93_000))
    assert race.state.incident_lap == 8
    assert race.state.incident_cost_ms is None


def test_the_temperature_occasions_are_armed_again():
    """A spell in the gravel leaves the set at a temperature the stint's
    earlier calls were not about. The HISTORY is kept - it is the same
    rubber - but every occasion may be spoken again."""
    race = a_running_race()
    clean_laps(race, 6)
    race.state.temp_said = {"cold", "up-to-temp"}
    race.state.temp_conserve_lap = 5
    race.state.temp_history = [(3, 80.0, 88.0), (4, 81.0, 89.0)]
    race.note_incident()
    race.handle(lap_event(8, lap_time_ms=110_000))
    assert race.state.temp_said == set()
    assert race.state.temp_conserve_lap is None
    assert len(race.state.temp_history) >= 2


@pytest.mark.parametrize("order", [(False, True), (True, False)])
def test_being_told_beats_being_detected_whichever_lands_first(order):
    """His word is the primary record and he has already been answered, so the
    engineer must not announce it back at him - whichever way round the
    detector and the driver got there.

    Asserted on the state being cleared rather than on a flag: the reported
    branch is the one that speaks nothing, so nothing records it, so clearing
    itself is the only evidence it ran."""
    race = a_running_race()
    for reported in order:
        race.note_incident(reported=reported)
    call = race.handle(lap_event(3, lap_time_ms=110_000))
    assert call is None or call.kind != INCIDENT
    assert race.state.incident_lap is None


def test_a_lap_with_no_incident_leaves_the_state_alone():
    race = a_running_race()
    race.handle(lap_event(3))
    assert race.state.incident_lap is None
