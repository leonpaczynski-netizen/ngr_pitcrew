"""The gap, one car at a time (§5.5), in the board's own words (rule 13).

Carried from row 1.10: push-to-talk answered "what's the gap" as a two-row
table - "Ahead: Boxhead, 3.4 seconds, closing 0.8 seconds a lap. Behind: the
car behind, 10.2 seconds, opening 0.3 seconds a lap." Two cars, two rates,
and one word, "closing", meaning opposite driving on the two sides.

And the voice and the board disagreed about the same car. The board says
"steady" under `TREND_WORTH_SAYING_S` (0.8 s a lap) or with fewer than
`MIN_LAPS_FOR_TREND` (5) laps - `race/gaps.py` records that anything under
0.8 is the random walk of the gap itself, and that the looser bar once told
the driver he was catching somebody three times in four when nothing was
happening. The voice said "closing" above 0.1 with no lap count at all.
"""
from __future__ import annotations

import pytest

from pitcrew.engineer.intents import GAP, PHRASES, answer, gap_side

READ = {"wallRunning": True,
        "gapAheadS": 3.4, "gapAheadName": "Boxhead",
        "gapAheadClosingSPerLap": 0.9, "gapAheadTrendLaps": 6,
        "gapBehindS": 1.2, "gapBehindName": "Rocket",
        "gapBehindClosingSPerLap": 0.9, "gapBehindTrendLaps": 6}


def test_a_question_about_the_car_ahead_is_answered_about_him_alone():
    said = answer(GAP, READ, heard="am i catching him").text
    assert said == ("Boxhead is 3.4 seconds ahead - you're catching him "
                    "0.9 seconds a lap.")
    assert "Rocket" not in said


def test_a_question_about_the_car_behind_is_answered_about_him_alone():
    said = answer(GAP, READ, heard="is he catching me").text
    assert said == ("Rocket is 1.2 seconds behind - he's catching you "
                    "0.9 seconds a lap.")
    assert "Boxhead" not in said


def test_a_question_that_names_no_side_gets_the_nearer_car():
    said = answer(GAP, READ, heard="what's the gap").text
    assert said.startswith("Rocket is 1.2 seconds behind")
    assert "Boxhead" not in said


@pytest.mark.parametrize("rate, words", [
    (-0.9, "you're losing 0.9 seconds a lap to him"),
    (0.3, "steady"),
    (-0.3, "steady"),
])
def test_the_car_ahead_in_the_boards_words(rate, words):
    read = {**READ, "gapAheadClosingSPerLap": rate}
    assert answer(GAP, read, heard="how far up the road is he").text.endswith(
        f"- {words}.")


def test_the_car_behind_pulling_away_is_his_problem_not_ours():
    read = {**READ, "gapBehindClosingSPerLap": -0.9}
    assert answer(GAP, read, heard="who's behind me").text.endswith(
        "- you're pulling away 0.9 seconds a lap.")


def test_too_few_laps_is_steady_on_the_board_and_in_the_ear():
    """**The board's decision, not reversed.** `test_too_few_consecutive_laps_
    is_steady_rather_than_a_slope` pins "steady" for a slope through too few
    points: on this app "steady" means *no trend worth saying*, whichever of
    the two reasons. The voice takes the same meaning through the same rule,
    so the ear and the eye cannot disagree about one car (rule 13)."""
    read = {**READ, "gapAheadTrendLaps": 3, "gapAheadClosingSPerLap": 1.5}
    assert answer(GAP, read, heard="am i catching him").text == (
        "Boxhead is 3.4 seconds ahead - steady.")


def test_the_board_and_the_voice_ask_the_same_rule():
    """One expression for both surfaces: the board's note and the spoken
    clause come from `gaps.trend_words`, so a floor changed in one place is
    changed in both."""
    from pitcrew.race.gaps import TREND_WORTH_SAYING_S, trend_words

    assert trend_words("ahead", TREND_WORTH_SAYING_S - 0.01, 6) is None
    assert trend_words("ahead", 1.0, 4) is None
    assert trend_words("ahead", 1.0, 5) is not None
    assert trend_words("ahead", None, 9) is None


def test_the_side_asked_for_is_not_answered_with_the_other_car():
    read = {**READ, "gapBehindS": None}
    reply = answer(GAP, read, heard="who's behind me")
    assert reply.answered is False
    assert "Boxhead" not in reply.text
    assert reply.text.startswith("Nothing read behind yet")


def test_an_unnamed_car_is_named_by_where_it_is():
    read = {**READ, "gapAheadName": None}
    assert answer(GAP, read, heard="gap to the car ahead").text.startswith(
        "The car ahead is 3.4 seconds away")


@pytest.mark.parametrize("phrase, side", [
    ("how far ahead is he", "ahead"), ("how far behind am i", "ahead"),
    ("who am i behind", "ahead"), ("who's in front of me", "ahead"),
    ("am i catching him", "ahead"), ("can i catch him", "ahead"),
    ("gap to the car ahead", "ahead"), ("how far up the road is he", "ahead"),
    ("is he pulling away from me", "ahead"),
    ("what's the gap to the car in front", "ahead"),
    ("how far behind is he", "behind"), ("how far ahead am i", "behind"),
    ("who's behind me", "behind"), ("whos behind me", "behind"),
    ("is he catching me", "behind"), ("how far back is the next car", "behind"),
    ("gap to the car behind", "behind"),
    ("what's the gap", None), ("whats the gap", None),
    ("how close is he", None),
])
def test_every_gap_phrase_is_read_for_its_side(phrase, side):
    """The inverted pairs are the trap: "how far ahead am I" is about the car
    BEHIND, and "how far behind am I" about the car ahead."""
    assert gap_side(phrase) == side


def test_every_gap_phrase_is_classified():
    """A phrase added to the intent without a side is answered as the nearer
    car - a fallback, not a decision - so the table has to cover them all."""
    for phrase in PHRASES[GAP]:
        gap_side(phrase)            # must not raise; None is a real answer
    from pitcrew.engineer.intents import GAP_SIDES
    assert set(GAP_SIDES) == set(PHRASES[GAP])
