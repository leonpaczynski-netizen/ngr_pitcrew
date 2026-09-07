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
* **It prices the tow** (the driver's second half, 7 Sep: *"I was saving
  fuel sitting behind Boxhead but I was also losing lap time to first - was
  the fuel saving worth the lost lap time or not?"*): the litres not burned
  in his wake are worth their standing time at Deep Forest's 2 L/s pump -
  about 0.3 s a lap - against the second a lap given away. Not worth it, and
  the undercut says so. Where the tow DOES pay, there is no undercut.

**What the pinned lap rests on, said plainly (critic pass 5).** The
constant-burn form below never measures a burn scatter, so the fill carries
the model's whole-lap fallback margin and the tank first holds the flag at
lap 7. Driven on the session's real per-lap burn the scatter measures at
about 0.15 L, the margin shrinks to about two litres, and it is lap 6 - the
second test below holds that, and it is the number the driver would have
been given. Two premises remain the reconstruction's: the race is run as a
20-lap lap race (session 138 was timed, 30 minutes, where the margin is a
lap while the count is soft), and P2 is one car all race (he was P2 himself
on laps 5 and 12, and a subject change wipes the trend and the map).
"""
from __future__ import annotations

from pitcrew.race.calls import (SECTOR_SPLIT, TOW_TRADE, UNDERCUT,
                                fuel_target_basis, fuel_target_l)
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
        {"laps": 11, "compound": "RS", "fuel_l": 85.0, "start_lap": 1},
        {"laps": 9, "compound": "RS", "fuel_l": 70.0, "start_lap": 12,
         "tyres": True},
    ],
    "stops": 1, "pit_laps": [11], "laps": 20,
    "binding_constraint": "fuel",
}


def _context(**over) -> PlanContext:
    fields = dict(car="Ford Mustang Gr.3", track="Deep Forest Raceway",
                  layout="Full Course", race_laps=20)
    fields.update(over)
    return PlanContext(**fields)


def _lap_event(lap, ms, fuel_end, position, pit, *,
               fuel_used: float = BURN_L) -> SessionEvent:
    fuel_start = fuel_end + fuel_used if not pit else fuel_end
    return SessionEvent(EventKind.LAP_COMPLETED, {"lap": Lap(
        lap_num=lap, lap_time_ms=ms, best_lap_ms=86996, delta_ms=0,
        fuel_start=fuel_start, fuel_end=fuel_end, fuel_used=fuel_used,
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


def _race(*, planned_burn: float = 8.0, planned_ms: int = 87_000,
          refuel_lps: float | None = 2.0):
    """Strategy 27's expectations were a clear-air 87.0 s at 8.0 L a lap
    (the plan's burn, measured in practice); the pump at Deep Forest is the
    hub's 2 L/s. Behind P2 he lapped about 88.2 s on about 7.4 L."""
    race = RaceCoordinator(PLAN, fuel_per_lap_l=BURN_L, fuel_capacity_l=100.0,
                           planned_fuel_per_lap_l=planned_burn,
                           planned_lap_time_ms=planned_ms, mandatory_stops=0,
                           refuel_rate_lps=refuel_lps)
    assert race.arm(_context(), _context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    race.note_circuit(CIRCUIT_M, sector_cuts_m=CUTS_M)
    # The briefed wear rate this compound measured here (3.7 %/lap).
    race.state.briefed_wear_per_lap = 0.037
    race.state.briefed_wear_samples = 1
    return race


def _drive(race, upto: int, *, gaps_from: int = 2, real_burn: bool = False):
    """Feed the race to lap `upto`, held up behind P2 from `gaps_from`.

    `real_burn` feeds each lap the litres the session actually burned (the
    fuel at the line less the last), so the burn scatter is measured as it
    was live; otherwise every lap burns the round 7.4 L.

    **The trend is keyed the way the wall keys it** (critic pass 6): the pit
    wall files a reading under `lap_now()` - laps COMPLETED - so a gap read
    while lap N is being driven carries N-1, and the figure kept for the lap
    is the LAST read, because the live trend overwrites within the lap.
    `tools/replay_race_calls.py` feeds the stored reads back the same way.
    Keyed on the lap itself with the FIRST read this drove a convention no
    race has ever produced, and the off-by-one it was hiding lived in
    `_weigh_the_tow` for a whole batch.

    Returns every call the engineer made, keyed by the lap it landed on.
    """
    trend = GapTrend(side="ahead")
    calls = {}
    last_fuel = 99.1
    for lap, ms, fuel_end, position, pit in RACE:
        if lap > upto:
            break
        if lap >= gaps_from:
            samples = _held_up_lap(1.0)
            trend.note(lap - 1, samples[-1][1], subject=P2)
            race.note_gaps(ahead=trend, ahead_name=P2, ahead_samples=samples)
        used = (last_fuel - fuel_end) if real_burn and not pit else BURN_L
        last_fuel = fuel_end
        call = race.handle(_lap_event(lap, ms, fuel_end, position, pit,
                                      fuel_used=used))
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
    found = re.search(r"Over (\d+) laps: ([\d.]+) seconds a lap through "
                      r"1 and 2, ([\d.]+) seconds a lap back in 3\.",
                      said.reason)
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
    assert call.call == "Box this lap. RS on. Fuel to the flag."
    assert call.reason.startswith(
        f"Undercut on {P2}: you're held up, and faster through 1 and 2. "
        "The fill costs the same now as on lap 11.")
    assert call.confidence == "medium", "the tyre life to the flag was checked"


def test_on_the_real_burn_scatter_it_is_lap_six():
    """The session's own per-lap burn: the scatter measures, the margin is
    two litres rather than a lap, and the tank holds the flag a lap earlier.
    This is the lap he would have been given."""
    race = _race()
    calls = _drive(race, upto=8, real_burn=True)
    assert _kinds(calls, UNDERCUT) == [6]


def test_a_fuel_only_stop_keeps_the_set_it_has():
    """Ludo's Deep Forest instruction was fuel only. At 5 %/lap the set he
    keeps would be at 95 % at the flag: no undercut. At 3.7 % it reaches,
    and the call says "No tyres." like every other box call (rule 13)."""
    import copy

    plan = copy.deepcopy(PLAN)
    plan["stints"][1]["tyres"] = False
    race = RaceCoordinator(plan, fuel_per_lap_l=BURN_L, fuel_capacity_l=100.0,
                           planned_fuel_per_lap_l=BURN_L,
                           planned_lap_time_ms=88_000, mandatory_stops=0)
    assert race.arm(_context(), _context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    race.note_circuit(CIRCUIT_M, sector_cuts_m=CUTS_M)
    race.state.briefed_wear_per_lap = 0.05
    assert _kinds(_drive(race, upto=9), UNDERCUT) == []

    race = RaceCoordinator(plan, fuel_per_lap_l=BURN_L, fuel_capacity_l=100.0,
                           planned_fuel_per_lap_l=BURN_L,
                           planned_lap_time_ms=88_000, mandatory_stops=0)
    assert race.arm(_context(), _context())
    race.handle(SessionEvent(EventKind.RACE_STARTED, {"laps_in_race": 20}))
    race.note_circuit(CIRCUIT_M, sector_cuts_m=CUTS_M)
    race.state.briefed_wear_per_lap = 0.037
    calls = _drive(race, upto=7)
    call = next(c for c in calls[7] if c.kind == UNDERCUT)
    assert call.call == "Box this lap. No tyres. Fuel to the flag."


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
            trend.note(lap - 1, 1.0, subject=P2)
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


# ---------------------------------------------- the second half: the tow

def test_a_trade_with_nothing_on_either_side_is_not_a_finding():
    """Critic pass 7, fifth round. Both figures inside `WASH_S` is a trade
    with no terms in it, and it reached him as "The tow saves you 0.0 litres
    a lap - 0.0 seconds a lap at the stop. About a wash." A REAL wash - a
    second of saving against a second of loss - still speaks, because that
    one he can act on by choosing."""
    from dataclasses import replace as dc_replace

    from pitcrew.race.rival_calls import tow_trade_call

    race = _race()
    _drive(race, upto=7)
    race.state.said_tags = set()
    race.state.tow_trade = dc_replace(race.state.tow_trade,
                                      saving_l_per_lap=0.04,
                                      saving_s_per_lap=0.02,
                                      losing_s_per_lap=0.05)
    assert tow_trade_call(race.state) is None
    race.state.tow_trade = dc_replace(race.state.tow_trade,
                                      saving_l_per_lap=2.0,
                                      saving_s_per_lap=1.0,
                                      losing_s_per_lap=0.9)
    said = tow_trade_call(race.state)
    assert said is not None and said.call.endswith("About a wash.")


def test_the_tow_is_priced_at_the_pump_and_found_not_worth_it():
    race = _race()
    calls = _drive(race, upto=7)
    laps = _kinds(calls, TOW_TRADE)
    assert laps and laps[0] <= 6, "three laps behind him and it is sayable"
    said = next(c for c in calls[laps[0]] if c.kind == TOW_TRADE)
    # **"a lap" on BOTH seconds figures** (critic pass 7, fifth round): the
    # standing time and the lap time are two quantities the driver has to
    # compare, and only one of them used to say what it was per.
    assert said.call.startswith("The tow saves you 0.6 litres a lap - "
                                "0.3 seconds a lap at the pump.")
    # **Not "losing N seconds a lap to Boxhead"** - `closing_call` owns that
    # sentence for the GAP growing, and this is his lap time in the wake
    # against clear air. Rule 13, found by critic pass 7.
    assert "Behind Boxhead you're 1." in said.call
    assert "seconds a lap slower." in said.call
    assert said.call.endswith("Not worth it.")
    assert said.reason.endswith("against the plan.")
    trade = race.state.tow_trade
    assert trade is not None and trade.worth_it is False
    undercut = next(c for c in calls[7] if c.kind == UNDERCUT)
    # Row 1.10: both halves said "seconds a lap" for two quantities -
    # standing time saved at the pump per towed lap, against lap time given
    # away on the road. The driver asked for this trade by name, so the
    # figures stay; each one says which clock it is on.
    # The critic on row 1.10: "costs 1.4 seconds of lap time" reads as a
    # total, and it is per lap - over a ten-lap tow that is 1.4 s against 14,
    # understating in the direction that makes the tow look free. Both keep
    # the rate, and "at the pump" / "on the road" is `tow.sentence`'s own
    # vocabulary, so one pair of numbers has one pair of words.
    assert ("The tow's 0.3 seconds a lap at the pump against 1.4 seconds a "
            "lap on the road.") in undercut.reason


def test_a_tow_that_pays_means_no_undercut():
    """Saving 2.6 L a lap at 2 L/s is 1.3 s at the stop against two tenths
    given away: stay in it, and the stop is the plan's."""
    race = _race(planned_burn=10.0, planned_ms=88_000)
    calls = _drive(race, upto=9)
    said = next(c for made in calls.values() for c in made
                if c.kind == TOW_TRADE)
    assert said.call.endswith("Worth it - stay in it.")
    assert race.state.tow_trade.worth_it is True
    assert _kinds(calls, UNDERCUT) == []


def test_no_refuel_rate_means_the_saving_is_not_priced():
    race = _race(refuel_lps=None)
    calls = _drive(race, upto=7)
    said = next(c for made in calls.values() for c in made
                if c.kind == TOW_TRADE)
    assert "no refuel rate on file to price it" in said.call
    assert race.state.tow_trade.worth_it is None
    assert _kinds(calls, UNDERCUT) == [7], "unpriced is not 'worth it'"


def test_the_trade_prefers_this_races_clear_air_laps():
    from pitcrew.race.tow import BY_CLEAR_LAPS, trade

    gaps = {2: 8.0, 3: 8.5, 4: 1.0, 5: 1.1, 6: 0.9}
    laps = {2: (87_000, 8.0), 3: (87_200, 8.1), 4: (88_300, 7.4),
            5: (88_100, 7.5), 6: (88_400, 7.3)}
    made = trade(gaps, laps, refuel_rate_lps=2.0,
                 planned_fuel_per_lap_l=9.0, planned_lap_time_ms=90_000)
    assert made.reference == BY_CLEAR_LAPS
    assert round(made.saving_l_per_lap, 2) == 0.65
    assert round(made.losing_s_per_lap, 1) == 1.2
    assert made.worth_it is False


def test_a_tow_that_saves_nothing_says_so():
    from pitcrew.race.tow import trade

    gaps = {2: 1.0, 3: 1.1, 4: 0.9}
    laps = {2: (88_000, 8.2), 3: (88_100, 8.3), 4: (88_000, 8.1)}
    made = trade(gaps, laps, refuel_rate_lps=2.0,
                 planned_fuel_per_lap_l=8.0, planned_lap_time_ms=87_000)
    call, _ = made.sentence("him")
    assert call.startswith("No fuel saving in the tow.")
    assert made.worth_it is False


def test_a_tow_that_costs_fuel_is_priced_as_a_cost():
    """Critic pass 7: `worth_it` clamped the saving at zero, so a tow
    costing 0.4 s of fuel and 0.2 s of lap time came out inside `WASH_S` and
    was spoken "About a wash". CLAUDE.md rule 9 - and the sentence said "No
    fuel saving in the tow", which is what a tow that saves NOTHING gets, so
    a measured negative was rendered as an absence in both halves."""
    from pitcrew.race.tow import TowTrade

    made = TowTrade(laps_held=3, saving_l_per_lap=-0.8,
                    saving_s_per_lap=-0.4, losing_s_per_lap=0.2,
                    reference="the plan")
    assert made.worth_it is False
    call, _ = made.sentence("Boxhead")
    assert call == ("The tow costs you 0.8 litres a lap - 0.4 seconds a lap "
                    "at the pump. Behind Boxhead you're 0.2 seconds a lap "
                    "slower. Not worth it.")


def test_a_tow_that_costs_fuel_and_no_time_still_says_get_out():
    """Critic pass 7's fourth round. Two special cases were each wrong once
    around one comparison: `losing <= 0 -> True` called this "worth it", and
    its replacement called it "nothing in it either way". The arithmetic has
    an answer - `gain > losing` is False - and it is get out."""
    from pitcrew.race.tow import TowTrade

    made = TowTrade(laps_held=3, saving_l_per_lap=-0.8,
                    saving_s_per_lap=-0.4, losing_s_per_lap=-0.1,
                    reference="the plan")
    assert made.worth_it is False
    assert made.sentence("Boxhead")[0] == (
        "The tow costs you 0.8 litres a lap - 0.4 seconds a lap at the pump. "
        "Behind Boxhead you're no slower. Not worth it.")


def test_a_free_tow_worth_saying_is_worth_it_and_a_nil_one_is_a_wash():
    """Critic pass 7, fifth round. The last special case bypassed `WASH_S`,
    so a saving of 0.02 L a lap behind a car he was no slower than produced
    "The tow saves you 0.0 litres a lap - 0.0 seconds a lap at the stop.
    Worth it - stay in it." Two zeros and an order. The general comparison
    reaches every case the special one was there for."""
    from pitcrew.race.tow import TowTrade

    def made(saving_s, losing_s):
        return TowTrade(laps_held=3, saving_l_per_lap=saving_s * 2,
                        saving_s_per_lap=saving_s, losing_s_per_lap=losing_s,
                        reference="the plan")

    assert made(0.5, -0.5).worth_it is True, "a free tow worth naming"
    assert made(0.01, -0.1).worth_it is None, "and one that is not"


def test_a_saving_inside_the_reading_error_is_not_called_a_cost():
    """Two tank readings are worth about a litre between them, so a tenth of
    a litre "against" him is the reference disagreeing with itself."""
    from pitcrew.race.tow import TowTrade

    made = TowTrade(laps_held=3, saving_l_per_lap=-0.05,
                    saving_s_per_lap=-0.02, losing_s_per_lap=0.0,
                    reference="the plan")
    assert made.sentence("Boxhead")[0].startswith("No fuel saving in the tow.")


def test_the_tow_call_does_not_borrow_the_closing_calls_sentence():
    """Rule 13, critic pass 7. `closing_call` says "You are losing N seconds
    a lap to X" and means the GAP is growing, read off the board. The tow
    means his LAP TIME against clear air, while the gap is by construction
    not growing. Same words, same rival, minutes apart."""
    from pitcrew.race.tow import TowTrade

    made = TowTrade(laps_held=3, saving_l_per_lap=0.6, saving_s_per_lap=0.3,
                    losing_s_per_lap=1.4, reference="the plan")
    call, _ = made.sentence("Boxhead")
    assert "losing" not in call
    assert "Behind Boxhead you're 1.4 seconds a lap slower." in call


def test_a_wash_is_said_as_one():
    from pitcrew.race.tow import TowTrade

    made = TowTrade(laps_held=3, saving_l_per_lap=1.0, saving_s_per_lap=1.0,
                    losing_s_per_lap=0.9, reference="the plan")
    assert made.worth_it is None
    assert made.sentence()[0].endswith("About a wash.")


def test_the_gap_is_paired_with_the_lap_it_was_read_on():
    """Critic pass 6, and it was wrong live rather than here.

    The wall files a reading under `lap_now()` - laps COMPLETED - so a gap
    read while lap N is being driven carries N-1, while `laps_by_number()`
    keys lap N's own time and litres under N. Taken at face value the trade
    weighed this lap's gap against the PREVIOUS lap's burn, which is the one
    pairing the whole calculation is.

    Driven so the two answers differ: held up on laps 2, 3 and 4 and clear
    from 5. Re-keyed the wall's way that is three held laps and a trade.
    Face value, it is laps 1, 2 and 3 - and lap 1 is not evidence after a
    standing start, so two laps, below `MIN_HELD_LAPS`, and no trade at all.
    """
    race = _race()
    trend = GapTrend(side="ahead")
    for lap, ms, fuel_end, position, pit in RACE[:6]:
        trend.note(lap - 1, 1.0 if lap <= 4 else 9.0, subject=P2)
        race.note_gaps(ahead=trend, ahead_name=P2)
        race.handle(_lap_event(lap, ms, fuel_end, position, pit))
    assert race._lap_of_read_key == {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6}
    trade = race.state.tow_trade
    assert trade is not None, "the wall's own keys read as two held laps"
    assert trade.laps_held == 3


def _through_the_stop(race, upto=16):
    """Drive the race past the lap-13 stop, held up behind P2 throughout."""
    trend = GapTrend(side="ahead")
    made = {}
    for lap, ms, fuel_end, position, pit in RACE[:upto]:
        trend.note(lap - 1, 1.0, subject=P2)
        race.note_gaps(ahead=trend, ahead_name=P2)
        if pit:
            race.handle(SessionEvent(EventKind.PIT_ENTRY, {"fuel": fuel_end}))
        call = race.handle(_lap_event(lap, ms, fuel_end, position, pit))
        if pit:
            race.handle(SessionEvent(EventKind.PIT_EXIT, {
                "fuel_added": 70.0, "tyres_changed": True}))
        if call is not None:
            race.state.record(call)
            made.setdefault(lap, []).append(call)
    return made


def test_the_tow_verdict_is_not_repeated_once_the_last_fill_is_in():
    """Critic pass 6: *"Worth it - stay in it"* about a saving already spent.

    The lap-13 stop is the last one, and `race/tow.py` says a litre saved
    after it is worth nothing at all - the fill is in. `clear_stint` empties
    `said` at PIT_EXIT, so the first crossing out of the box was free to say
    the trade again about whoever is ahead now, with a verdict computed
    entirely from the half of the argument that has stopped existing.

    What he hears instead is the thing that CHANGED (critic pass 7): the
    reason he was given for sitting there is gone. Once, with no verdict.
    """
    from pitcrew.race.rival_calls import tow_trade_call

    race = _race(planned_burn=10.0, planned_ms=88_000)   # a tow that "pays"
    made = _through_the_stop(race)
    assert race.state.stint_ends_on_lap is None, "the last stint is running"
    assert race.state.tow_trade is not None, "the trade is still computable"
    assert race.state.tow_trade.worth_it is True, "and it still says stay in"
    assert race.state.tow_said_worth_it is True, "and he was told so"

    after = [c for laps, calls in made.items() if laps >= 13 for c in calls
             if c.kind == TOW_TRADE]
    assert len(after) == 1, "once, not once a lap"
    assert after[0].tag == "tow-spent"
    assert after[0].call.startswith("No fuel left to save in the tow - "
                                    "the fill's in.")
    assert "Worth it" not in after[0].call and "worth it" not in after[0].call
    # And it does not come round again on the next crossing.
    assert tow_trade_call(race.state) is None


def test_a_driver_told_the_tow_was_not_worth_it_is_not_told_again():
    """He already got out, or chose not to. Saying it a second time after
    the stop is the same words for a different claim - rule 13."""
    race = _race()                       # Deep Forest: not worth it
    made = _through_the_stop(race)
    before = [c for laps, calls in made.items() if laps < 13 for c in calls
              if c.kind == TOW_TRADE]
    assert before and before[0].call.endswith("Not worth it.")
    assert race.state.tow_said_worth_it is False
    assert not [c for laps, calls in made.items() if laps >= 13
                for c in calls if c.kind == TOW_TRADE]


def test_a_tow_never_spoken_about_is_not_summed_up_after_the_stop():
    """Nothing was ever said about the tow, so there is nothing that has
    stopped being true."""
    from pitcrew.race.rival_calls import tow_trade_call

    race = _race(planned_burn=10.0, planned_ms=88_000)
    _through_the_stop(race)
    race.state.said_tags = set()
    race.state.tow_said = False
    race.state.tow_said_worth_it = None
    assert tow_trade_call(race.state) is None


def test_an_unpriced_tow_is_not_summed_up_as_if_it_had_a_price():
    """Critic pass 7. `worth_it` is also None with no refuel rate on file -
    the app said "no refuel rate on file to price it". Gated on "not False"
    it then said "The saving was worth its standing time at the pump",
    asserting the price it had just refused to name."""
    from pitcrew.race.rival_calls import tow_trade_call

    race = _race(refuel_lps=None)
    made = _through_the_stop(race)
    before = [c for laps, calls in made.items() if laps < 13 for c in calls
              if c.kind == TOW_TRADE]
    assert before and "no refuel rate on file to price it" in before[0].call
    assert race.state.tow_said_worth_it is None
    assert tow_trade_call(race.state) is None
    assert not [c for laps, calls in made.items() if laps >= 13
                for c in calls if c.kind == TOW_TRADE]


def test_the_withdrawal_is_only_about_the_car_he_was_told_about():
    """Critic pass 7. Told to stay behind Boxhead, he stops and comes out
    behind Rocket: the withdrawal of an instruction never given about Rocket
    would be spoken about Rocket. The figure would be right - `GapTrend`
    clears on a subject change - and the premise invented."""
    from pitcrew.race.rival_calls import tow_trade_call

    race = _race(planned_burn=10.0, planned_ms=88_000)
    _through_the_stop(race)
    assert race.state.tow_said_about == P2
    race.state.said_tags = set()
    race.state.gap_ahead_name = "Rocket"
    assert tow_trade_call(race.state) is None
    race.state.gap_ahead_name = P2
    assert tow_trade_call(race.state) is not None
    # **And a verdict given about a car the board could not name says
    # nothing about any car** (critic pass 7, third round). `gap_ahead_name`
    # is None whenever the top-8 truncation hides the car ahead, and the
    # first version of this guard let a None subject match every rival -
    # which is the failure it was written to close.
    race.state.said_tags = set()
    race.state.tow_said_about = None
    assert tow_trade_call(race.state) is None


def test_the_fill_is_only_called_in_where_a_stop_was_taken():
    """Critic pass 7, fourth round. `_a_fill_is_still_to_come` also refuses
    on `stop_still_needed`, which goes false with NO stop taken the moment
    `_stops_off` fires - so a driver who had just heard "You're fuelled to
    the flag" was told "the fill's in" about a stop he never made. Under a
    helmet that reads as the app believing he has pitted."""
    from pitcrew.race.rival_calls import tow_trade_call

    race = _race(planned_burn=10.0, planned_ms=88_000)
    _through_the_stop(race)
    race.state.said_tags = set()
    said = tow_trade_call(race.state)
    assert said is not None and "the fill's in" in said.call
    assert "there is no pump left" in said.reason

    # The same state, but the stop was dropped rather than taken.
    race.state.said_tags = set()
    race.state.last_stop_lap = None
    said = tow_trade_call(race.state)
    assert said is not None
    assert "there's no stop to save it for" in said.call
    assert "the fill's in" not in said.call
    assert "you are not stopping" in said.reason


def test_a_tenth_is_the_floor_on_the_lap_time_it_names():
    """`worth_it is True` needs the loss to sit `WASH_S` under the saving,
    so a loss of 0.04 s a lap is exactly the reachable case - and `:.1f`
    renders it "0.0", a measurement spoken as nothing (rule 9's shape)."""
    from dataclasses import replace as dc_replace

    from pitcrew.race.rival_calls import tow_trade_call

    race = _race(planned_burn=10.0, planned_ms=88_000)
    _through_the_stop(race)
    race.state.said_tags = set()
    race.state.tow_trade = dc_replace(race.state.tow_trade,
                                      losing_s_per_lap=0.04)
    assert tow_trade_call(race.state) is None
    race.state.tow_trade = dc_replace(race.state.tow_trade,
                                      losing_s_per_lap=0.14)
    said = tow_trade_call(race.state)
    assert said is not None and "0.1 seconds a lap slower" in said.call


def test_a_tyre_that_will_not_reach_the_flag_refuses():
    race = _race()
    race.state.briefed_wear_per_lap = 0.09      # 12 laps x 9% = 108%
    calls = _drive(race, upto=8)
    assert _kinds(calls, UNDERCUT) == []
