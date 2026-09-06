"""The driver's own acceptance test for the engineer, 7 Sep 2026.

    "One true test will be, after these updates are all finished, if having
    that Deep Forest Supercars race over again George would notice I was
    losing time to a car in front that I was faster than through sector 1
    and 2 but that he was faster in sector 3, and pit me as soon as I could
    take enough fuel on board to finish the race and perform an undercut."

**The race is real; the gaps are reconstructed.** The twenty lap rows below
are session 138 as recorded - lap times, fuel at the line, position, the
lap-13 stop - and the plan is strategy 27 (one stop, box lap 11, fuel-bound).
The wall read the gap to P2 on 154 frames that night and persisted none of
them (assessment S8, closed by `gap_reads` in this same change), so the gap
samples here are built to the driver's account: a second behind P2 at the
line, taking two tenths out of him through each of sectors 1 and 2, giving
four back in sector 3. The next race replays its own reads off the store.

What the test holds the engineer to:

* **It notices where.** `SECTOR_SPLIT` names sectors 1 and 2 as ours and
  sector 3 as his, on the sector lines his rack uses, once the map has four
  laps outside its own noise.
* **It boxes him on the first lap the tank holds fuel to the flag**, and
  not one lap earlier: 12 laps after the box at 7.4 L is 96 L, which fits at
  the lap-7 crossing and does not at lap 6 (13 laps, 103 L).
* **The fill it then asks for is to the flag**, on the same expression the
  box already uses.
"""
from __future__ import annotations

from pitcrew.race.calls import (SECTOR_SPLIT, UNDERCUT, fuel_target_basis,
                                fuel_target_l)
from pitcrew.race.coordinator import PlanContext, RaceCoordinator
from pitcrew.race.gaps import GapTrend
from pitcrew.telemetry.session_state import EventKind, Lap, SessionEvent

# Session 138, Deep Forest Raceway, 6 Sep 2026: (lap, lap_time_ms, fuel_end,
# position, is_pit_lap). Fuel at the green was 99.1 L; burn about 7.4 L a lap.
RACE = [
    (1, 95901, 91.74, 4, 0), (2, 88454, 84.20, 3, 0), (3, 87700, 76.53, 3, 0),
    (4, 89021, 69.20, 3, 0), (5, 88327, 61.76, 2, 0), (6, 89433, 54.08, 3, 0),
    (7, 87897, 46.73, 3, 0), (8, 87879, 39.65, 3, 0), (9, 87992, 32.65, 3, 0),
    (10, 88237, 25.85, 3, 0), (11, 88582, 18.68, 3, 0), (12, 88011, 11.27, 2, 0),
    (13, 140153, 75.15, 3, 1), (14, 88649, 67.31, 3, 0), (15, 87135, 59.47, 3, 0),
    (16, 88115, 51.79, 3, 0), (17, 87704, 43.86, 3, 0), (18, 86996, 35.82, 3, 0),
    (19, 87036, 27.83, 3, 0), (20, 87341, 19.73, 3, 0),
]
CIRCUIT_M = 4253.0
CUTS_M = (1418.0, 2835.0)          # laps.sector_model 'thirds:1418/2835'
BURN_L = 7.4
P2 = "Boxhead"

PLAN = {
    "stints": [
        {"laps": 11, "compound": "RH", "fuel_l": 85.0, "start_lap": 1},
        {"laps": 9, "compound": "RH", "fuel_l": 70.0, "start_lap": 12},
    ],
    "stops": 1, "pit_laps": [11], "laps": 20,
    "binding_constraint": "fuel",
}


def _context(**over) -> PlanContext:
    fields = dict(car="Ford Mustang Gr.3", track="Deep Forest Raceway",
                  layout="Full Course", race_laps=20)
    fields.update(over)
    return PlanContext(**fields)


def _lap_event(lap, ms, fuel_end, position, pit) -> SessionEvent:
    fuel_start = fuel_end + BURN_L if not pit else fuel_end
    return SessionEvent(EventKind.LAP_COMPLETED, {"lap": Lap(
        lap_num=lap, lap_time_ms=ms, best_lap_ms=86996, delta_ms=0,
        fuel_start=fuel_start, fuel_end=fuel_end, fuel_used=BURN_L,
        position=position, is_pit_lap=bool(pit), is_out_lap=False)})


def _held_up_lap(gap_at_line: float, *, s12_gain: float = 0.2,
                 s3_loss: float = 0.4, every_m: float = 200.0):
    """One lap of (track_m, gap_s) behind P2, to the driver's account.

    Through sectors 1 and 2 the gap shrinks by `s12_gain` each; through
    sector 3 it grows back by `s3_loss`. Sampled every 200 m, which is the
    wall's real rate that night (about 21 reads a lap).
    """
    out = []
    m = 0.0
    gap = gap_at_line
    while m < CIRCUIT_M:
        if m < CUTS_M[0]:
            gap = gap_at_line - s12_gain * (m / CUTS_M[0])
        elif m < CUTS_M[1]:
            gap = (gap_at_line - s12_gain
                   - s12_gain * ((m - CUTS_M[0]) / (CUTS_M[1] - CUTS_M[0])))
        else:
            gap = (gap_at_line - 2 * s12_gain
                   + s3_loss * ((m - CUTS_M[1]) / (CIRCUIT_M - CUTS_M[1])))
        out.append((m, round(gap, 2)))
        m += every_m
    return out


def _race():
    race = RaceCoordinator(PLAN, fuel_per_lap_l=BURN_L, fuel_capacity_l=100.0,
                           planned_fuel_per_lap_l=BURN_L,
                           planned_lap_time_ms=88_000, mandatory_stops=0)
    assert race.arm(_context(), _context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    race.note_circuit(CIRCUIT_M, sector_cuts_m=CUTS_M)
    # The briefed wear rate this compound measured here (3.7 %/lap).
    race.state.briefed_wear_per_lap = 0.037
    race.state.briefed_wear_samples = 1
    return race


def _drive(race, upto: int, *, gaps_from: int = 2):
    """Feed the race to lap `upto`, held up behind P2 from `gaps_from`.

    Returns every call the engineer made, keyed by the lap it landed on.
    """
    trend = GapTrend(side="ahead")
    calls = {}
    for lap, ms, fuel_end, position, pit in RACE:
        if lap > upto:
            break
        if lap >= gaps_from:
            samples = _held_up_lap(1.0)
            trend.note(lap, samples[0][1], subject=P2)
            race.note_gaps(ahead=trend, ahead_name=P2, ahead_samples=samples)
        call = race.handle(_lap_event(lap, ms, fuel_end, position, pit))
        if call is not None:
            race.state.record(call)
            calls.setdefault(lap, []).append(call)
    return calls


def _kinds(calls, kind):
    return sorted(lap for lap, made in calls.items()
                  if any(c.kind == kind for c in made))


def test_the_engineer_notices_where_he_has_us():
    race = _race()
    calls = _drive(race, upto=7)
    laps = _kinds(calls, SECTOR_SPLIT)
    assert laps, "seven laps behind P2 and not a word about where"
    said = next(c for c in calls[laps[0]] if c.kind == SECTOR_SPLIT)
    assert said.call == f"Faster than {P2} through 1 and 2. He has you in 3."
    # The magnitudes are read off 200 m samples whose last stretch of the
    # lap is not chained to the next, so they come in a touch under the
    # 0.4 built in; the sentence and the sign are what the driver hears.
    import re
    found = re.search(r"Over (\d+) laps: ([\d.]+) a lap through 1 and 2, "
                      r"([\d.]+) back in 3\.", said.reason)
    assert found, said.reason
    assert abs(float(found.group(2)) - 0.4) < 0.15
    assert abs(float(found.group(3)) - 0.4) < 0.15
    # Gaps from lap 2; four laps of them is lap 5, and not before.
    assert laps[0] == 5, "four laps of gaps before a sector is a finding"


def test_he_is_boxed_on_the_first_lap_the_tank_holds_the_flag():
    """Lap 7: 12 laps after the box at 7.4 L is 96 L. Lap 6 wanted 103."""
    race = _race()
    calls = _drive(race, upto=7)
    assert _kinds(calls, UNDERCUT) == [7]
    call = next(c for c in calls[7] if c.kind == UNDERCUT)
    assert call.call == "Box this lap. Fuel to the flag."
    assert call.reason.startswith(
        f"Undercut on {P2}: you're held up, and faster through 1 and 2. "
        "The fill costs the same now as on lap 11.")
    assert call.confidence == "medium", "the tyre life to the flag was checked"


def test_the_fill_it_asks_for_is_to_the_flag():
    race = _race()
    _drive(race, upto=7)
    state = race.state
    assert fuel_target_basis(state) == "12 laps after the box"
    # 12 laps at 7.4 L less the load correction the fill model applies,
    # plus its margin: the box's own expression, not a second one.
    assert 92.0 < fuel_target_l(state) < 98.0


def test_not_a_lap_earlier_and_not_twice():
    race = _race()
    calls = _drive(race, upto=12)
    assert _kinds(calls, UNDERCUT) == [7]


def test_without_a_sector_where_we_gain_there_is_no_undercut():
    """Held up, and no slower than him anywhere we can measure: the stop is
    the plan's, on the plan's lap."""
    race = _race()
    trend = GapTrend(side="ahead")
    for lap, ms, fuel_end, position, pit in RACE[:8]:
        if lap >= 2:
            samples = _held_up_lap(1.0, s12_gain=0.0, s3_loss=0.0)
            trend.note(lap, 1.0, subject=P2)
            race.note_gaps(ahead=trend, ahead_name=P2, ahead_samples=samples)
        call = race.handle(_lap_event(lap, ms, fuel_end, position, pit))
        assert call is None or call.kind != UNDERCUT


def test_a_rival_who_has_stopped_is_not_undercut():
    from pitcrew.race.rival_calls import Rival
    from pitcrew.race.rivals import Stop

    race = _race()
    race.state.rivals[P2] = Rival(name=P2, pitted=True, stop=Stop(lap=4))
    calls = _drive(race, upto=8)
    assert _kinds(calls, UNDERCUT) == []


def test_an_unbriefed_tyre_is_said_to_be_unchecked():
    race = _race()
    race.state.briefed_wear_per_lap = None
    calls = _drive(race, upto=7)
    call = next(c for c in calls[7] if c.kind == UNDERCUT)
    assert call.confidence == "low"
    assert call.reason.endswith("Tyre life to the flag unchecked.")
    assert call.spoken().endswith("Unconfirmed.")


def test_a_tyre_that_will_not_reach_the_flag_refuses():
    race = _race()
    race.state.briefed_wear_per_lap = 0.09      # 12 laps x 9% = 108%
    calls = _drive(race, upto=8)
    assert _kinds(calls, UNDERCUT) == []
