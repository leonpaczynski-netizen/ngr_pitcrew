"""Championship points, mirrored from the hub's own `src/lib/points.ts`.

Every rule here is transcribed rather than invented, so every test is really
asking one question: does Pit Crew agree with the league about the league. Two
places computing a championship differently is worse than one place computing
it at all, because the driver has no way to tell which is right.
"""
from __future__ import annotations

from pitcrew.hub.standings import (
    POINTS_TABLE,
    Standing,
    effective_position,
    normalise_for_races,
    points_for_position,
    points_for_result,
    resolve_scheme,
    standings,
    title_math,
)


# --- the table -------------------------------------------------------------

def test_the_default_table_is_the_leagues():
    """P1 = 22, and nothing from P17."""
    assert POINTS_TABLE[0] == 22
    assert points_for_position(1) == 22
    assert points_for_position(16) == 1
    assert points_for_position(17) == 0


def test_a_league_with_its_own_scheme_uses_it():
    """`resolveScheme` on the hub: a configured table wins, an empty one falls
    back. Keeping that boundary means the day a league is configured, Pit Crew
    follows without being changed."""
    assert resolve_scheme((44, 36, 30)) == (44, 36, 30)
    assert resolve_scheme([]) == POINTS_TABLE
    assert resolve_scheme(None) == POINTS_TABLE


def test_a_position_off_the_end_of_the_table_scores_nothing():
    assert points_for_position(0) == 0
    assert points_for_position(-1) == 0
    assert points_for_position(None) == 0


# --- statuses --------------------------------------------------------------

def test_a_non_starter_and_a_disqualification_score_nothing():
    """Position is ignored for both - it is not a finish."""
    assert points_for_result("DNS", 1) == 0
    assert points_for_result("DSQ", 1) == 0


def test_a_retirement_scores_from_its_position_like_a_finish():
    """FINISHED and DNF score identically: the admin places a DNF after the
    classified finishers and the calculation does not distinguish them."""
    assert points_for_result("DNF", 5) == points_for_result("FINISHED", 5)


# --- penalties -------------------------------------------------------------

def test_a_place_drop_is_applied_at_read_time():
    """The stored position is always the physical finishing order and is never
    mutated - a drop moves a driver down here and nowhere else."""
    assert effective_position("FINISHED", 1, [("POSITION_DROP", 4)]) == 5
    assert points_for_result("FINISHED", 1, [("POSITION_DROP", 4)]) == 12


def test_a_drop_past_the_end_of_the_table_scores_nothing():
    assert points_for_result("FINISHED", 14, [("POSITION_DROP", 10)]) == 0


def test_a_points_deduction_comes_off_the_base_and_floors_at_zero():
    """A penalty cannot put a driver into negative points."""
    assert points_for_result("FINISHED", 1, [("POINTS_DEDUCTION", 5)]) == 17
    assert points_for_result("FINISHED", 16, [("POINTS_DEDUCTION", 5)]) == 0


def test_no_penalties_is_exactly_the_unpenalised_result():
    assert points_for_result("FINISHED", 3, []) == points_for_result(
        "FINISHED", 3)


def test_a_drop_on_an_unclassified_result_changes_nothing():
    assert effective_position("DSQ", 1, [("POSITION_DROP", 4)]) is None


# --- multi-race rounds -----------------------------------------------------

def test_a_multi_race_round_divides_the_scheme_and_the_total_drifts():
    """22 becomes 7+7+7 = 21 over three races. The drift is the league's
    accepted behaviour and is reproduced rather than corrected."""
    per_race = normalise_for_races(POINTS_TABLE, 3)
    assert per_race[0] == 7
    assert per_race[0] * 3 == 21


def test_a_single_race_round_is_untouched():
    assert normalise_for_races(POINTS_TABLE, 1) == POINTS_TABLE


def test_an_absent_scheme_stays_absent_rather_than_becoming_the_default():
    """For the overall table absence means "use the default"; for a class
    table it means "award no class points at all". Resolving one here awarded
    class points to leagues that had configured none."""
    assert normalise_for_races([], 3) == []
    assert normalise_for_races(None, 3) is None


# --- the table -------------------------------------------------------------

def a_result(name, position, **kw):
    row = {"driverName": name, "position": position, "status": "FINISHED",
           "penalties": []}
    row.update(kw)
    return row


def test_the_bonuses_are_added_at_full_value_every_race():
    """Pole and fastest lap do NOT divide by the race count, and the hub says
    so in as many words."""
    table = standings([a_result("Rocky", 1, pole=True, fastestLap=True)],
                      pole_points=2, fastest_lap_points=1)
    assert table[0].points == 22 + 2 + 1


def test_the_table_is_ordered_by_points_then_by_best_finish():
    table = standings([a_result("A", 2), a_result("B", 3), a_result("B", 4)])
    assert [s.driver for s in table] == ["B", "A"]     # 15+13 beats 18


def test_every_standing_carries_the_races_behind_it():
    """CLAUDE.md rule 4."""
    table = standings([a_result("A", 2), a_result("A", 3)])
    assert table[0].races == 2


# --- what secures it -------------------------------------------------------

def a_table(*pairs):
    return [Standing(driver=name, points=points, races=1)
            for name, points in pairs]


def test_the_position_that_secures_it_assumes_every_rival_wins_out():
    """The pessimistic case. A position that only works if somebody else has a
    bad day is not a plan, and it is not what a driver should be told."""
    # One round left. We lead by 15; the rival can still take 22, reaching
    # 107, so we need 8 - which is P9 on the league table.
    math = title_math(a_table(("Beeni", 100), ("Rocky", 85)),
                      ours="Beeni", rounds_left=1)
    assert math.live_rivals == ["Rocky"]
    assert math.secures_position == 9
    assert "P9 today secures it" in math.to_say()


def test_a_lead_bigger_than_what_is_left_is_already_secured():
    """100 against 70 with 22 available is not a position to aim at - it is
    done, and offering a position would imply a risk that is not there."""
    math = title_math(a_table(("Beeni", 100), ("Rocky", 70)),
                      ours="Beeni", rounds_left=1)
    assert math.already_secured and math.live_rivals == []


def test_an_unassailable_lead_is_said_plainly():
    math = title_math(a_table(("Beeni", 100), ("Rocky", 40)),
                      ours="Beeni", rounds_left=1)
    assert math.already_secured
    assert "already yours" in math.to_say()


def test_a_championship_out_of_reach_says_so_rather_than_offering_a_position():
    math = title_math(a_table(("Rocky", 100), ("Beeni", 40)),
                      ours="Beeni", rounds_left=1)
    assert math.out_of_reach
    assert "gone" in math.to_say()


def test_nothing_settling_it_today_is_the_ordinary_answer_not_a_gap():
    """With three rounds left and seventy-five points available, no single
    finish secures anything - and that must not read as a missing value."""
    math = title_math(a_table(("Magical daddy", 95), ("Beeni", 68)),
                      ours="Beeni", rounds_left=3)
    assert math.secures_position is None
    assert "Nothing settles it today" in math.to_say()
    assert "27 behind" in math.to_say()


def test_the_margin_is_signed_and_named_for_what_it_is():
    """It was called `lead_over_next` and went negative whenever we were not
    first, which is a field whose name contradicts its value."""
    behind = title_math(a_table(("Rocky", 95), ("Beeni", 68)), ours="Beeni",
                        rounds_left=3)
    ahead = title_math(a_table(("Beeni", 95), ("Rocky", 68)), ours="Beeni",
                       rounds_left=3)
    assert behind.margin_to_leader == -27 and not behind.leading
    assert ahead.margin_to_leader == 0 and ahead.leading


def test_only_drivers_who_can_still_win_are_title_rivals():
    """Everyone else is a place, not a championship - and defending against
    them costs the race actually being driven."""
    math = title_math(a_table(("Beeni", 100), ("Rocky", 90), ("Slow", 10)),
                      ours="Beeni", rounds_left=1)
    assert "Rocky" in math.live_rivals
    assert "Slow" not in math.live_rivals


def test_the_rivals_who_matter_are_the_ones_in_this_race():
    math = title_math(a_table(("Beeni", 100), ("Rocky", 90),
                              ("Absent", 95)), ours="Beeni", rounds_left=1)
    assert set(math.matters_here(["Rocky", "PUNISHED"])) == {"Rocky"}


def test_a_driver_not_in_the_table_gets_an_empty_answer():
    math = title_math(a_table(("Rocky", 90)), ours="Beeni", rounds_left=1)
    assert math.our_points == 0 and math.live_rivals == []
