"""The 16 Aug race, replayed against the engineer that failed it.

Session 44, Yas Marina, 15 laps, a 2-stop plan the race left behind: the
driver ran a feasible zero-stop, never pitted, and finished with 1.79 litres.
The engineer of that night said "Box this lap. RS. Fuel to 27 litres."
verbatim on every lap from 7 to 15 - the ninth voiced on his chequered-flag
crossing - while the one unanswered re-plan offer from minute two gagged
every later assessment, and the correct call (short-shift, 0.4 laps short)
was computed and outranked nine laps running. Not one word about tyre
temperature was structurally possible.

The regression here drives RaceCoordinator, OfferDesk and assess through
that exact shape - the same plan, burns, lap times, positions and (but for
lap one, taken from the measured stone-cold session 43 start so the cold
branch is exercised; the real lap one was grid-warmed) the same temperatures
- and asserts the race the engineer should have called. The unit tests below
it pin each new mechanism on its own.
"""
from __future__ import annotations

import pytest

from pitcrew.race.calls import (
    BOX_NOW,
    BOX_SOON,
    CHEQUER,
    FUEL_LONG,
    HIGH,
    MEDIUM,
    STATUS,
    STAY_OUT,
    TYRE_TEMP,
    RaceState,
    _fuel_instruction,
    next_call,
    stay_out_call,
)
from pitcrew.race.coordinator import PlanContext, RaceCoordinator
from pitcrew.race.replan import (
    RECOMMENDED,
    RESOLVED_EXPIRED,
    RESOLVED_KEPT,
    RESOLVED_SUPERSEDED,
    URGENT,
    OfferDesk,
    Replan,
    assess,
)
from pitcrew.race.temps import lap_axle_means, window_from_samples
from pitcrew.telemetry.session_state import (
    EventKind,
    Lap,
    SessionEvent,
    SessionKind,
    SessionState,
)

from .conftest import make_packet


# ------------------------------------------------------------- tonight's race

# The approved plan: strategy 3, "2 stops", stints 7/3/5, all RS, assumed
# 7.563 L/lap, reference 118.940 s, for a timed 30-minute race.
PLAN = {"stints": [
    {"laps": 7, "compound": "RS", "fuel_l": 52.9, "start_lap": 1},
    {"laps": 3, "compound": "RS", "fuel_l": 27.0, "start_lap": 8},
    {"laps": 5, "compound": "RS", "fuel_l": 41.6, "start_lap": 11},
]}
PLANNED_BURN = 7.563
PLANNED_LAP_MS = 118_940

# lap: (time_ms, position, fuel_end, fuel_used, front_mean, rear_mean).
# Lap 1's temps are session 43's measured stone-cold start (59.3/61.5);
# everything else is session 44 as recorded.
LAPS = {
    1: (121_511, 4, 92.84, 0.00, 59.3, 61.5),
    2: (117_724, 4, 86.09, 6.75, 73.0, 78.3),
    3: (117_318, 4, 79.32, 6.77, 74.9, 79.9),
    4: (126_254, 4, 72.50, 6.82, 74.4, 82.3),
    5: (129_989, 7, 65.61, 6.89, 76.3, 86.0),
    6: (120_073, 6, 58.88, 6.73, 72.0, 81.4),
    7: (119_170, 6, 51.95, 6.93, 72.9, 81.7),
    8: (119_557, 6, 45.10, 6.85, 73.5, 81.6),
    9: (121_826, 5, 38.10, 7.00, 74.0, 83.2),
    10: (124_059, 4, 31.35, 6.75, 73.8, 84.7),
    11: (119_624, 4, 24.68, 6.67, 73.5, 82.9),
    12: (119_729, 4, 18.11, 6.57, 73.5, 82.4),
    13: (130_443, 4, 12.18, 5.93, 74.0, 81.8),
    14: (124_332, 4, 7.74, 4.44, 70.5, 78.8),
    15: (129_675, 5, 1.79, 5.95, 72.4, 79.1),
}

# The measured window for this car at this track: practice sessions 41-43
# ran F 70-77 / R 77-88 steady, up to temperature in about two laps.
WINDOW_FRONT = (70.0, 77.0)
WINDOW_REAR = (77.0, 88.0)


def lap_event(lap_num: int) -> SessionEvent:
    time_ms, position, fuel_end, fuel_used, front, rear = LAPS[lap_num]
    lap = Lap(
        lap_num=lap_num, lap_time_ms=time_ms, best_lap_ms=117_318,
        delta_ms=time_ms - 117_318,
        fuel_start=fuel_end + fuel_used, fuel_end=fuel_end,
        fuel_used=fuel_used, position=position,
        is_pit_lap=False, is_out_lap=False,
        tyre_temp_front_c=front, tyre_temp_rear_c=rear,
    )
    return SessionEvent(EventKind.LAP_COMPLETED, {"lap": lap})


def a_timed_context() -> PlanContext:
    return PlanContext(car="Ford Shelby GT350R '16", track="Yas Marina",
                       layout=None, race_laps=0, race_minutes=30.0)


def tonight() -> RaceCoordinator:
    race = RaceCoordinator(
        PLAN,
        fuel_per_lap_l=PLANNED_BURN,
        wear_per_lap=0.03161,
        fuel_capacity_l=100.0,
        # No measured short-shift trade for the Shelby - the fold call must
        # name the lever without inventing a number.
        short_shift_l_per_1000rpm=None)
    assert race.arm(a_timed_context(), a_timed_context()) is True
    race.state.temp_window_front = WINDOW_FRONT
    race.state.temp_window_rear = WINDOW_REAR
    race.state.temp_laps_to_window = 2
    return race


def replay():
    """Drive the race and the replan loop the way the controller wires them.

    Returns (race, calls, offers, resolutions): every coordinator call made,
    every offer the desk voiced, every offer it resolved without the driver.
    The driver never answers - he is under a helmet, which is the point.
    """
    race = tonight()
    desk = OfferDesk()
    calls, offers, resolutions = [], [], []

    green = race.handle(SessionEvent(EventKind.RACE_STARTED,
                                     {"laps_in_race": 0}))
    if green:
        calls.append(green)

    for lap_num in range(1, 16):
        call = race.handle(lap_event(lap_num))
        if call:
            calls.append(call)
        verdict = assess(
            laps_done=race.state.lap,
            laps_total=race.state.laps_total,
            fuel_l=race.state.fuel_l,
            planned_fuel_per_lap=race.planned_fuel_per_lap_l,
            observed_fuel_per_lap_l=race.observed_fuel_per_lap(),
            lap_time_ms=race.representative_pace_ms(),
            planned_lap_time_ms=PLANNED_LAP_MS,
            current_stops=race.stops_planned(),
            inputs=None,
            fuel_capacity_l=100.0,
        )
        spoken, resolved = desk.consider(verdict, race.state.lap)
        resolutions.extend(resolved)
        if spoken:
            offers.append((race.state.lap, spoken))

    finish = race.handle(SessionEvent(EventKind.RACE_FINISHED,
                                      {"laps": 15, "position": 5}))
    if finish:
        calls.append(finish)
    return race, calls, offers, resolutions


@pytest.fixture(scope="module")
def raced():
    return replay()


def test_no_pace_verdict_is_built_on_the_standing_start(raced):
    """The lap-1 offer of the real night - "lapping 2% slower than planned",
    voiced two minutes in - must not exist. No offer before three
    representative laps do."""
    _, _, offers, _ = raced
    assert all(lap >= 4 for lap, _ in offers)


def test_the_burn_drift_is_offered_once_the_race_has_shown_its_burn(raced):
    _, _, offers, _ = raced
    lap, first = offers[0]
    assert lap == 4
    assert "less fuel" in first.reason
    # And it is the burn, not the standing-start pace, that raised it.
    assert "slower" not in first.reason


def test_the_unanswered_offer_expires_and_stops_gagging(raced):
    """The single root cause of "didn't adjust at all": one unanswered offer
    used to block every later verdict to the flag."""
    _, _, offers, resolutions = raced
    assert any(res.reason == RESOLVED_EXPIRED for res in resolutions)
    expired = next(res for res in resolutions
                   if res.reason == RESOLVED_EXPIRED)
    assert expired.accepted is False          # expiry never adopts anything
    assert expired.lap == 6                   # two laps after the lap-4 offer


def test_box_now_is_said_at_most_twice_before_the_fold(raced):
    _, calls, _, _ = raced
    box_laps = [c.lap for c in calls if c.kind == BOX_NOW]
    assert box_laps == [7, 8]


def test_the_repeated_box_call_is_never_verbatim(raced):
    _, calls, _, _ = raced
    box = [c.spoken() for c in calls if c.kind == BOX_NOW]
    assert len(set(box)) == len(box)
    assert "overdue" in box[1]


def test_the_engineer_folds_to_the_stay_out_with_the_short_shift_lever(raced):
    race, calls, _, _ = raced
    fold = next(c for c in calls if c.kind == STAY_OUT)
    assert fold.lap == 9
    assert "Staying out" in fold.call
    assert "Short-shift" in fold.reason
    # No measured slope for the Shelby: the lever carries no rpm number and
    # the confidence drops instead of a figure being invented.
    assert fold.confidence == MEDIUM
    assert "0.4" in fold.reason
    # The fold adopted the zero-stop shape: no stop left, target is the flag.
    assert race.stops_planned() == 0
    assert race.state.stint_ends_on_lap is None


def test_nothing_after_the_fold_asks_him_to_box(raced):
    _, calls, _, _ = raced
    assert not any(c.kind in (BOX_NOW, BOX_SOON) and c.lap > 9 for c in calls)


def test_fuel_to_27_litres_is_never_said(raced):
    """The physically vacuous fill of the real night - "Fuel to 27 litres"
    with 51.9 aboard - must not survive in any call."""
    _, calls, offers, _ = raced
    everything = [c.spoken() for c in calls] + [o.reason for _, o in offers]
    assert not any("Fuel to 27" in text for text in everything)
    assert not any("27 litres" in text for text in everything)


def test_the_chequered_flag_is_called_with_position_and_a_closing_fact(raced):
    _, calls, _, _ = raced
    assert calls[-1].kind == CHEQUER
    assert "P5" in calls[-1].reason
    assert "1.8 litres" in calls[-1].reason
    assert "zero-stop" in calls[-1].reason


def test_no_box_or_fuel_call_fires_on_the_final_crossing(raced):
    """The ninth box call of the real night was voiced on the chequered-flag
    crossing - LAP_COMPLETED for the last lap arrives before RACE_FINISHED."""
    _, calls, _, _ = raced
    on_lap_15 = [c for c in calls if c.lap == 15]
    assert all(c.kind == CHEQUER for c in on_lap_15)


def test_the_cold_tyre_call_and_its_confirmation(raced):
    _, calls, _, _ = raced
    temps = [c for c in calls if c.kind == TYRE_TEMP]
    assert temps[0].lap == 1
    assert "Tyres cold" in temps[0].call
    assert "2 laps to window" in temps[0].reason
    assert temps[1].lap == 2
    assert "Tyres in window" in temps[1].call


def test_the_normal_rear_hot_offset_never_raises_a_trend_call(raced):
    """Rears ran 8-11 degC hotter than fronts all race - this car's normal
    thermal balance, not a finding."""
    _, calls, _, _ = raced
    assert not any("heating" in c.call for c in calls)


def test_the_push_call_of_the_night_still_exists(raced):
    """Lap 4's "You can push" - right inside the plan's frame - is not this
    pass's target; it must simply not have been broken."""
    _, calls, _, _ = raced
    assert any(c.kind == FUEL_LONG and c.lap == 4 for c in calls)


def test_the_status_call_survives_where_box_now_used_to_drown_it(raced):
    _, calls, _, _ = raced
    status = [c for c in calls if c.kind == STATUS]
    assert any(c.lap == 10 and "P4" in c.call for c in status)


# --------------------------------------------------------------- offer desk

def an_offer(**overrides) -> Replan:
    fields = dict(verdict=RECOMMENDED, reason="burning 10% less",
                  stops=1, stint_laps=(8,), gain_s=12.0)
    fields.update(overrides)
    return Replan(**fields)


def test_an_offer_expires_after_two_unanswered_laps():
    desk = OfferDesk()
    spoken, _ = desk.consider(an_offer(), lap=4)
    assert spoken is not None
    _, resolved = desk.consider(an_offer(), lap=5)
    assert resolved == [] and desk.pending is not None
    _, resolved = desk.consider(an_offer(), lap=6)
    assert len(resolved) == 1
    assert resolved[0].reason == RESOLVED_EXPIRED
    assert resolved[0].accepted is False
    assert desk.pending is None


def test_expiry_does_not_block_a_materially_different_offer():
    desk = OfferDesk()
    desk.consider(an_offer(stops=1), lap=4)
    desk.consider(an_offer(stops=1), lap=6)          # lapses
    spoken, _ = desk.consider(an_offer(stops=0), lap=8)
    assert spoken is not None                        # different stop count
    assert spoken.stops == 0


def test_a_lapsed_offer_is_not_re_voiced_verbatim():
    """Re-asking the identical question every two laps is the box-call
    defect wearing a different hat."""
    desk = OfferDesk()
    desk.consider(an_offer(), lap=4)
    desk.consider(an_offer(), lap=6)                 # lapses
    spoken, _ = desk.consider(an_offer(), lap=7)
    assert spoken is None


def test_an_escalation_to_urgent_replaces_the_pending_offer():
    desk = OfferDesk()
    desk.consider(an_offer(verdict=RECOMMENDED), lap=4)
    spoken, resolved = desk.consider(
        an_offer(verdict=URGENT, confidence="high"), lap=5)
    assert spoken is not None and spoken.verdict == URGENT
    assert resolved[0].reason == RESOLVED_SUPERSEDED


def test_an_oscillating_verdict_does_not_swap_the_offer_every_lap():
    """A race sitting on a stops boundary flips the model's answer lap to
    lap. The first swap is information; swapping straight back is the model
    dithering out loud, and it waits for an answer or the expiry instead."""
    desk = OfferDesk()
    desk.consider(an_offer(stops=1), lap=4)
    spoken, resolved = desk.consider(an_offer(stops=0), lap=5)
    assert spoken is not None                    # the first swap speaks
    assert resolved[0].reason == RESOLVED_SUPERSEDED
    spoken, resolved = desk.consider(an_offer(stops=1), lap=6)
    assert spoken is None and resolved == []     # the swap-back waits
    assert desk.pending is not None and desk.pending.stops == 0


def test_an_urgent_escalation_cuts_through_the_hysteresis():
    desk = OfferDesk()
    desk.consider(an_offer(stops=1), lap=4)
    desk.consider(an_offer(stops=0), lap=5)
    spoken, _ = desk.consider(
        an_offer(stops=1, verdict=URGENT, confidence="high"), lap=6)
    assert spoken is not None and spoken.verdict == URGENT


def test_draining_the_desk_records_the_race_ending_unanswered():
    from pitcrew.race.replan import RESOLVED_RACE_ENDED
    desk = OfferDesk()
    desk.consider(an_offer(), lap=14)
    resolution = desk.drain(lap=15)
    assert resolution.reason == RESOLVED_RACE_ENDED
    assert resolution.accepted is False          # draining adopts nothing
    assert desk.pending is None
    assert OfferDesk().drain(lap=15) is None


def test_the_drivers_answer_still_lands():
    desk = OfferDesk()
    desk.consider(an_offer(), lap=4)
    resolution = desk.resolve(accepted=False, lap=5)
    assert resolution.reason == RESOLVED_KEPT
    assert desk.pending is None


def test_an_answer_with_nothing_pending_is_none():
    assert OfferDesk().resolve(accepted=True, lap=5) is None


# ------------------------------------------------------- representative pace

def pace_race() -> RaceCoordinator:
    race = RaceCoordinator(None, fuel_per_lap_l=3.4)
    race.arm(None, PlanContext(car="c", track="t", layout=None, race_laps=20))
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    return race


def a_lap(lap_num: int, time_ms: int, **overrides) -> SessionEvent:
    fields = dict(lap_num=lap_num, lap_time_ms=time_ms, best_lap_ms=time_ms,
                  delta_ms=0, fuel_start=40.0, fuel_end=36.6, fuel_used=3.4,
                  position=3, is_pit_lap=False, is_out_lap=False)
    fields.update(overrides)
    return SessionEvent(EventKind.LAP_COMPLETED, {"lap": Lap(**fields)})


def test_lap_one_never_enters_the_pace_record():
    race = pace_race()
    race.handle(a_lap(1, 121_511))
    race.handle(a_lap(2, 117_724))
    race.handle(a_lap(3, 117_318))
    assert race.representative_pace_ms() is None     # only two count
    race.handle(a_lap(4, 117_500))
    assert race.representative_pace_ms() == 117_500  # median of 2,3,4


def test_one_incident_lap_does_not_move_the_pace():
    """His lap-to-lap noise sits right at the 2% threshold on a two-minute
    lap - one slow lap must not read as a pace change. A +6.8% lap is an
    incident, dropped before the median; with only two clean laps left the
    honest answer is that the pace is unknown, and it returns once a third
    clean lap lands."""
    race = pace_race()
    for lap_num, ms in ((1, 121_511), (2, 118_000), (3, 118_100),
                        (4, 126_000)):
        race.handle(a_lap(lap_num, ms))
    assert race.representative_pace_ms() is None
    race.handle(a_lap(5, 118_300))
    assert race.representative_pace_ms() == 118_100


def test_adjacent_incident_laps_cannot_carry_the_median():
    """Tonight's real laps 4-5 (+6.1% and +9.3%: a crawl, then the spin
    recovery) once made the three-lap median 126,254 - a +6% pace verdict
    that went unvoiced only because an earlier offer was gagging the loop.
    Incident laps are 5-10% outliers, not noise; they are dropped against
    the race's own best before any median is taken."""
    race = pace_race()
    for lap_num, ms in ((1, 121_511), (2, 117_724), (3, 117_318),
                        (4, 126_254), (5, 129_989)):
        race.handle(a_lap(lap_num, ms))
    assert race.representative_pace_ms() is None    # two clean laps only
    race.handle(a_lap(6, 120_073))
    assert race.representative_pace_ms() == 117_724


def test_pit_and_out_laps_stay_out_of_the_pace():
    race = pace_race()
    race.handle(a_lap(1, 118_000))
    race.handle(a_lap(2, 118_000))
    race.handle(a_lap(3, 140_000, is_pit_lap=True))
    race.handle(a_lap(4, 139_000, is_out_lap=True))
    race.handle(a_lap(5, 118_200))
    race.handle(a_lap(6, 118_400))
    assert race.representative_pace_ms() == 118_200


def test_no_pace_means_no_pace_verdict():
    verdict = assess(laps_done=1, laps_total=20, fuel_l=90.0,
                     planned_fuel_per_lap=7.563, observed_fuel_per_lap_l=None,
                     lap_time_ms=None, planned_lap_time_ms=118_940,
                     current_stops=2, inputs=None)
    assert verdict.offered is False


# ---------------------------------------------------------------- stay out

def a_state(**overrides) -> RaceState:
    fields = dict(lap=9, laps_total=15, fuel_l=38.1, fuel_per_lap_l=6.77,
                  position=5, stint_ends_on_lap=7, laps_since_stop=9,
                  fuel_capacity_l=100.0)
    fields.update(overrides)
    return RaceState(**fields)


def test_the_stay_out_needs_the_fuel_to_nearly_reach():
    """Without a measured short-shift slope the claim stops at half a lap."""
    assert stay_out_call(a_state(fuel_l=38.1)) is not None   # 0.37 short
    assert stay_out_call(a_state(fuel_l=36.0)) is None       # 0.68 short


def test_a_measured_slope_extends_the_stay_out_reach():
    state = a_state(fuel_l=34.0, short_shift_l_per_1000rpm=1.762)
    call = stay_out_call(state)                              # 0.98 short
    assert call is not None
    # "Should", not "can": the claim rests on him executing the saving
    # every remaining lap, and MEDIUM is never voiced - the hedge has to
    # live in the words.
    assert call.call == "Staying out? You should make it."
    assert call.reason.startswith("Short-shift ")
    drop = int(call.reason.split()[1].rstrip(","))
    assert drop % 50 == 0
    assert call.confidence == HIGH


def test_a_lever_that_cannot_close_the_gap_refuses_the_fold():
    """`stay_out_call` used to read only the rpm drop off `short_shift_for`
    and throw away the laps the CAPPED drop still cannot cover - so with a
    measured slope and a 3-lap hole it said "you can make it" and retired a
    stop the driver needed. The fold's gate is the lever's own arithmetic:
    a residue past the epsilon means the box call stands."""
    state = a_state(fuel_l=20.0, short_shift_l_per_1000rpm=1.762)
    assert stay_out_call(state) is None                      # 3.0 laps short


def test_fuel_already_good_says_so_without_a_lever():
    call = stay_out_call(a_state(fuel_l=45.0))
    # The one unhedged form: no saving is being asked of him.
    assert call.call == "Staying out? You can make it."
    assert "good to the flag" in call.reason
    assert "Short-shift" not in call.reason


def test_a_box_call_that_cannot_make_the_flag_escalates_instead():
    """Fold refused, so the repeat carries the new fact - never verbatim,
    and never the old "You will not make the flag": the measured driver
    closed 0.7 laps with lift-and-coast alone, so the escalation states the
    gap in its frame and names his lever, hedged."""
    state = a_state(fuel_l=20.0)                             # 3 laps short
    state.record(next_call(state))                           # overdue 2
    state.lap = 10                                           # overdue 3
    call = next_call(state)
    assert call.kind == BOX_NOW
    assert "3 laps overdue" in call.reason
    assert "short of the flag on current burn" in call.reason
    assert "short-shift and lift" in call.reason
    assert call.confidence == MEDIUM
    assert "will not make" not in call.reason


# ---------------------------------------------------------- the stale fill

def test_a_stale_plan_does_not_size_a_fill_below_the_race():
    """Next stint 3 laps, no stop after it, 8 laps left: the fill must reach
    the flag, not the plan's stale stint length."""
    state = RaceState(lap=7, laps_total=15, fuel_l=5.0, fuel_per_lap_l=6.79,
                      stint_ends_on_lap=7, next_stint_laps=3,
                      further_stop_planned=False, fuel_capacity_l=100.0)
    said = _fuel_instruction(state)
    assert said == "Fuel to 61 litres."                      # (8+1) x 6.79


def test_a_hand_built_state_keeps_the_stints_own_figure():
    """`further_stop_planned` is None where nobody said - missing is not
    False, and the old behaviour stands."""
    state = RaceState(lap=7, laps_total=15, fuel_l=5.0, fuel_per_lap_l=6.79,
                      stint_ends_on_lap=7, next_stint_laps=3,
                      fuel_capacity_l=100.0)
    assert said_litres(_fuel_instruction(state)) == 27


def said_litres(said: str) -> int:
    return int(said.split("Fuel to ")[1].split(" litres")[0])


# ------------------------------------------------------------- the chequer

def test_the_chequer_outranks_a_stale_box_call():
    state = a_state(lap=15, finished=True, position=5, fuel_l=1.79)
    call = next_call(state)
    assert call.kind == CHEQUER
    assert "P5" in call.reason


def test_the_final_crossing_gap_is_silence_not_a_box_call():
    """LAP_COMPLETED for the last lap lands before RACE_FINISHED. In that
    gap the distance is covered and nothing about a stop is actionable."""
    state = a_state(lap=15, finished=False)
    assert next_call(state) is None


def test_the_fold_never_fires_on_the_chequered_crossing():
    """A plan whose last stop sits two laps before the end puts the fold's
    overdue trigger exactly on the final lap - and the fold used to run
    there, voicing "Staying out? You can make it." 200 ms before the
    chequer and recording an accepted stay-out about a race already over."""
    plan = {"stints": [
        {"laps": 13, "compound": "RS", "start_lap": 1},
        {"laps": 2, "compound": "RS", "start_lap": 14},
    ]}
    race = RaceCoordinator(plan, fuel_per_lap_l=PLANNED_BURN,
                           wear_per_lap=0.03161, fuel_capacity_l=100.0)
    assert race.arm(a_timed_context(), a_timed_context()) is True
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 0}))
    calls = []
    for lap_num in range(1, 16):
        call = race.handle(lap_event(lap_num))
        if call:
            calls.append(call)
    finish = race.handle(SessionEvent(EventKind.RACE_FINISHED,
                                      {"laps": 15, "position": 5}))
    assert finish.kind == CHEQUER
    assert not any(c.kind == STAY_OUT for c in calls)
    assert not any(c.lap == 15 for c in calls)


def test_a_timed_race_that_outruns_its_estimate_keeps_the_engineer_talking():
    """A timed race's lap count is the plan's own estimate. When it runs
    out with two minutes still on the packet clock, the driver is genuinely
    going round again - the countdown stretches by one instead of
    `_crossing_the_line` silencing every call on a real racing lap."""
    race = tonight()
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 0}))
    for lap_num in range(1, 15):
        race.handle(lap_event(lap_num))
    event = lap_event(15)
    event.data["remaining_time_ms"] = 120_000
    race.handle(event)
    assert race.state.laps_total == 16
    assert race.state.laps_remaining() == 1
    # And the flag still ends it in the usual way.
    finish = race.handle(SessionEvent(EventKind.RACE_FINISHED,
                                      {"laps": 16, "position": 5}))
    assert finish.kind == CHEQUER


def test_a_final_lap_with_no_clock_left_is_not_extended():
    """The extension needs the clock's word; the plain crossing - no
    meaningful time remaining - stays the quiet gap before the chequer."""
    race = tonight()
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 0}))
    for lap_num in range(1, 15):
        race.handle(lap_event(lap_num))
    event = lap_event(15)
    event.data["remaining_time_ms"] = 0
    assert race.handle(event) is None
    assert race.state.laps_total == 15


# ------------------------------------------------------------- tyre temps

def temp_state(**overrides) -> RaceState:
    fields = dict(lap=1, laps_total=15, position=4,
                  temp_window_front=(70.0, 77.0),
                  temp_window_rear=(77.0, 88.0),
                  temp_laps_to_window=2)
    fields.update(overrides)
    return RaceState(**fields)


def test_cold_at_the_green_needs_a_real_margin_below_the_window():
    cold = temp_state()
    cold.note_temps(1, 59.3, 61.5)
    call = next_call(cold)
    assert call.kind == TYRE_TEMP and "Tyres cold" in call.call
    assert "2 laps to window" in call.reason

    warm = temp_state()
    warm.note_temps(1, 68.1, 71.3)      # the real grid-warmed lap one
    assert next_call(warm) is None


def test_in_window_confirms_only_a_warning_already_given():
    state = temp_state()
    state.note_temps(1, 59.3, 61.5)
    state.record(next_call(state))
    state.lap = 2
    state.note_temps(2, 73.0, 78.3)
    call = next_call(state)
    assert call.kind == TYRE_TEMP and "in window" in call.call

    unwarned = temp_state()
    unwarned.note_temps(1, 68.1, 71.3)  # no cold call was made
    unwarned.lap = 2
    unwarned.note_temps(2, 73.0, 78.3)
    assert next_call(unwarned) is None


def test_each_temperature_occasion_is_said_once_per_stint():
    state = temp_state()
    state.note_temps(1, 59.3, 61.5)
    state.record(next_call(state))
    state.lap = 2
    state.note_temps(2, 62.0, 64.0)     # still cold
    assert next_call(state) is None


def test_the_baseline_offset_between_axles_is_never_a_finding():
    """Rears 8-11 degC hotter than fronts, every lap, is this car's normal."""
    state = temp_state(lap=0)
    for lap_num, (front, rear) in enumerate(
            [(73.0, 81.0), (74.0, 82.0), (73.5, 81.5), (73.8, 82.3),
             (73.2, 81.8), (73.6, 82.0)], start=1):
        state.lap = lap_num
        state.note_temps(lap_num, front, rear)
        call = next_call(state)
        assert call is None or call.kind != TYRE_TEMP


def test_an_axle_departing_its_own_baseline_is_called_once():
    state = temp_state(lap=0)
    steady = [(73.0, 81.0), (73.5, 81.5), (73.2, 81.2), (73.4, 81.4),
              (73.1, 81.3)]
    for lap_num, (front, rear) in enumerate(steady, start=1):
        state.lap = lap_num
        state.note_temps(lap_num, front, rear)
        next_call(state)
    for lap_num, rear in ((6, 87.0), (7, 88.0)):
        state.lap = lap_num
        state.note_temps(lap_num, 73.3, rear)
        call = next_call(state)
    assert call.kind == TYRE_TEMP
    assert "Rears heating" in call.call
    assert "Mind traction" in call.reason
    state.record(call)
    state.lap = 8
    state.note_temps(8, 73.2, 88.5)
    following = next_call(state)
    assert following is None or following.kind != TYRE_TEMP


def test_fronts_going_first_may_move_brake_balance_rearward_only():
    state = temp_state(lap=0)
    steady = [(73.0, 81.0), (73.5, 81.5), (73.2, 81.2), (73.4, 81.4),
              (73.1, 81.3)]
    for lap_num, (front, rear) in enumerate(steady, start=1):
        state.lap = lap_num
        state.note_temps(lap_num, front, rear)
        next_call(state)
    for lap_num, front in ((6, 79.0), (7, 80.0)):
        state.lap = lap_num
        state.note_temps(lap_num, front, 81.3)
        call = next_call(state)
    assert "Fronts heating" in call.call
    assert "rearward" in call.reason
    assert "forward" not in call.spoken()


def test_a_fresh_sets_warm_up_is_not_its_own_baseline():
    """`clear_stint` empties the temp history on a tyre change, and the
    trend baseline used to filter on the ABSOLUTE race lap - so after a
    lap-10 stop every entry qualified, the fresh set's cold laps entered
    its own baseline, and its normal steady temperature read as "heating"
    in every race with a tyre stop. The baseline is positional within the
    set's history: its first laps are its warm-up, excluded."""
    from pitcrew.race.calls import clear_stint
    # A longer race than tonight's, so laps 16-17 are mid-race laps rather
    # than the final-crossing gap, where every candidate stands down anyway.
    state = temp_state(lap=0, laps_total=25)
    for lap_num in range(1, 11):
        state.lap = lap_num
        state.note_temps(lap_num, 73.0, 81.0)
        next_call(state)
    clear_stint(state, tyres_changed=True)
    fresh_set = [(11, 60.5, 64.0), (12, 67.0, 72.0),        # warm-up
                 (13, 73.0, 81.0), (14, 73.2, 81.2), (15, 73.1, 81.1),
                 (16, 73.3, 81.3), (17, 73.2, 81.4)]        # its normal
    for lap_num, front, rear in fresh_set:
        state.lap = lap_num
        state.note_temps(lap_num, front, rear)
        call = next_call(state)
        if call is not None:
            state.record(call)
        assert call is None or "heating" not in call.call, (lap_num, call)


def test_no_window_means_no_absolute_temperature_claim():
    """Missing is null: without a measured window the only allowed form is
    relative - both axles still climbing - at reduced confidence."""
    state = temp_state(temp_window_front=None, temp_window_rear=None,
                       temp_laps_to_window=None)
    state.note_temps(1, 59.3, 61.5)
    assert next_call(state) is None     # one lap proves nothing
    state.lap = 2
    state.note_temps(2, 66.0, 68.0)
    call = next_call(state)
    assert call.kind == TYRE_TEMP
    assert "Tyres cold" in call.call
    assert call.confidence == MEDIUM
    assert "window" not in call.reason  # no measured figure to quote


# --------------------------------------------------------- measured window

def test_the_window_is_measured_from_steady_practice_laps():
    samples = ([(41, 59.3, 61.5), (41, 66.0, 70.0)]      # warm-up, dropped
               + [(41, 72.0, 78.0), (41, 74.0, 82.0), (41, 76.0, 86.0)]
               + [(42, 60.0, 62.0), (42, 68.0, 72.0)]    # warm-up, dropped
               + [(42, 71.0, 77.5), (42, 75.0, 84.0)])
    window = window_from_samples(samples)
    assert window is not None
    assert window.laps_sampled == 5
    assert 71.0 <= window.front[0] < window.front[1] <= 76.0
    assert 77.5 <= window.rear[0] < window.rear[1] <= 86.0
    assert window.laps_to_window == 2


def test_too_few_steady_laps_is_no_window_not_a_thin_one():
    samples = [(41, 59.3, 61.5), (41, 66.0, 70.0), (41, 72.0, 78.0)]
    assert window_from_samples(samples) is None
    assert window_from_samples([]) is None


def test_lap_axle_means_needs_temps_on_the_frames():
    frames = [{"temp_fl": 72.0, "temp_fr": 74.0,
               "temp_rl": 80.0, "temp_rr": 82.0},
              {"temp_fl": 73.0, "temp_fr": 75.0,
               "temp_rl": 81.0, "temp_rr": 83.0}]
    assert lap_axle_means(frames) == (73.5, 81.5)
    assert lap_axle_means([{"temp_fl": None, "temp_fr": None,
                            "temp_rl": None, "temp_rr": None}]) is None


# ----------------------------------------------- the live feed's new facts

def test_a_completed_lap_carries_its_axle_temperature_means():
    state = SessionState(SessionKind.PRACTICE)
    state.update(make_packet(tyre_temp_fl=70.0, tyre_temp_fr=72.0,
                             tyre_temp_rl=80.0, tyre_temp_rr=82.0))
    state.update(make_packet(tyre_temp_fl=72.0, tyre_temp_fr=74.0,
                             tyre_temp_rl=82.0, tyre_temp_rr=84.0))
    events = state.update(make_packet(
        tyre_temp_fl=72.0, tyre_temp_fr=74.0,
        tyre_temp_rl=82.0, tyre_temp_rr=84.0, last_lap_ms=94_000))
    lap = events[0].data["lap"]
    assert lap.tyre_temp_front_c == pytest.approx(72.0, abs=0.5)
    assert lap.tyre_temp_rear_c == pytest.approx(82.0, abs=0.5)


def test_a_timed_race_finishes_when_the_clock_has_run_out():
    """`laps_in_race` is 0 for a timed race, so the lap-count finish can
    never fire - the measured 30-minute race ended with no RACE_FINISHED at
    all and the engineer mid-box-call. The clock is the finish signal."""
    state = SessionState(SessionKind.RACE)
    state.update(make_packet(speed_ms=0.0, remaining_time_ms=1_800_000))
    events = state.update(make_packet(speed_ms=40.0,
                                      remaining_time_ms=1_800_000))
    assert any(e.kind is EventKind.RACE_STARTED for e in events)
    events = state.update(make_packet(speed_ms=40.0, last_lap_ms=121_511,
                                      remaining_time_ms=1_000_000))
    assert [e.kind for e in events] == [EventKind.LAP_COMPLETED]
    # A transient -1 - the "not in race" sentinel, not an expired clock -
    # must not finish the race on the crossing it happens to land on.
    events = state.update(make_packet(speed_ms=40.0, last_lap_ms=120_000,
                                      remaining_time_ms=-1))
    assert [e.kind for e in events] == [EventKind.LAP_COMPLETED]
    events = state.update(make_packet(speed_ms=40.0, last_lap_ms=119_170,
                                      remaining_time_ms=0))
    assert [e.kind for e in events] == [EventKind.LAP_COMPLETED,
                                        EventKind.RACE_FINISHED]


def test_a_lap_race_never_takes_the_timed_finish_branch():
    """GT7 reports -1 for a lap race's clock; it must not read as expired."""
    state = SessionState(SessionKind.RACE)
    state.update(make_packet(speed_ms=0.0, laps_in_race=3,
                             remaining_time_ms=-1))
    state.update(make_packet(speed_ms=40.0, laps_in_race=3,
                             remaining_time_ms=-1))
    events = state.update(make_packet(speed_ms=40.0, laps_in_race=3,
                                      last_lap_ms=94_000,
                                      remaining_time_ms=-1))
    assert [e.kind for e in events] == [EventKind.LAP_COMPLETED]


# ------------------------------------------------------------- the outcome

def test_the_outcome_names_the_fold():
    from pitcrew.analysis.session import LapInput
    from pitcrew.race.outcome import race_outcome
    laps = [LapInput(lap_num=n, lap_time_ms=120_000, fuel_start=90.0,
                     fuel_end=83.0) for n in range(1, 16)]
    text = race_outcome(laps, planned_stops=2, final_position=5,
                        declined_calls=11, stay_out_lap=9)
    assert "No stops" in text
    assert "plan called for 2 stops" in text
    assert "folded to the driver's stay-out on lap 9" in text
    assert "11 calls offered and not taken" in text
