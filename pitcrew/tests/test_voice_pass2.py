"""Critic 3's minors on the voice batch, and two defects found while fixing
its majors (11 Sep 2026).

* **"one hundred" could not be said.** `number_word(100)` indexed past
  `TENS_WORDS` and `_split_on_number` refused anything over 99, so "Fuel to
  100 litres" - a full tank, the one figure most likely at a long-stint stop -
  could never be played from the pack.
* **"1 laps after the box."** `_laps_the_fill_covers` built its basis as
  `f"{remaining} {frame}"`, so a last-lap stop said it in the plural.
* **"steady" from no trend at all.** A single reading, or a rate with no lap
  count, was said "steady" - a rate of about zero asserted from nothing
  (rule 3). The board's "steady" for too few laps stays: that is a pinned
  decision about a slope, and this is the case where there is no slope.
* **"what's the gap behind"** reached GAP through the literal matcher, named
  no phrase in `GAP_SIDES`, and was answered with the car ahead.
* **A gap of 0.0** was spoken "0.0 seconds ahead" and chosen as the nearer
  car; `_chase` treats a gap of zero or less as no reading.
"""
from __future__ import annotations

import pytest

from pitcrew.engineer import phrase_manifest as manifest
from pitcrew.engineer.intents import GAP, answer, gap_side
from pitcrew.race.calls import RaceState, fuel_target_basis


def _plays(line: str) -> bool:
    clips = set(manifest.clips())
    segments = manifest.segments_for(line)
    return bool(segments) and all(name in clips for name in segments)


def test_one_hundred_is_a_number_the_pack_can_say():
    assert manifest.number_word(100) == "one hundred"
    assert _plays("Box this lap. Fuel to 100 litres - 16 laps after the box.")


def test_a_last_lap_stop_is_one_lap_not_one_laps():
    state = RaceState(lap=18, laps_total=20, stint_ends_on_lap=18,
                      fuel_l=2.0, fuel_per_lap_l=3.0, fuel_capacity_l=100.0,
                      next_stint_laps=2, further_stop_planned=False)
    state.lap = 19
    basis = fuel_target_basis(state)
    assert basis is not None
    assert "1 laps" not in basis


@pytest.mark.parametrize("snapshot", [
    {"wallRunning": True, "gapAheadS": 1.5, "gapAheadClosingSPerLap": None,
     "gapAheadTrendLaps": None},
    {"wallRunning": True, "gapAheadS": 1.5, "gapAheadClosingSPerLap": 1.2,
     "gapAheadTrendLaps": None},
])
def test_no_trend_at_all_is_not_called_steady(snapshot):
    said = answer(GAP, snapshot, heard="am i catching him").text
    assert said == "The car ahead is 1.5 seconds away."


def test_too_few_laps_of_a_real_slope_is_still_steady_like_the_board():
    said = answer(GAP, {"wallRunning": True, "gapAheadS": 1.5,
                        "gapAheadClosingSPerLap": 1.2,
                        "gapAheadTrendLaps": 3}, heard="am i catching him").text
    assert said.endswith("- steady.")


@pytest.mark.parametrize("heard, side", [
    ("what's the gap behind", "behind"),
    ("what's the gap ahead", "ahead"),
    ("what's the gap to the guy behind", "behind"),
    ("how close is he behind me", "behind"),
    ("how far is the guy in front", "ahead"),
])
def test_a_side_named_in_other_words_is_still_read(heard, side):
    assert gap_side(heard) == side


def test_a_question_naming_both_sides_names_neither():
    """Critic 3, pass 2: "behind" was checked first, so this was read as the
    car behind. Both named is no side - the nearer car answers, and says
    which it is."""
    assert gap_side("how far behind is the car ahead") is None


def test_back_to_the_car_in_front_is_the_car_in_front():
    """The same pass: "back" was a side word, so this was the car behind. It
    is not a side, and the question is about the car in front."""
    assert gap_side("what's the gap back to the car in front") == "ahead"


def test_back_is_not_a_side():
    assert gap_side("is he coming back to me") is None


@pytest.mark.parametrize("crossed, frame", [
    (False, "1 lap after the box."), (True, "1 lap to the flag.")])
def test_a_one_lap_fill_plays_from_the_pack(crossed, frame):
    """Critic 3, pass 2: the singular this batch introduced was never in the
    pack, so a late splash filed its whole box call as a declared gap."""
    from pitcrew.race.calls import next_call

    # Not yet across the line in the box, the fill covers the laps AFTER the
    # box lap - so one of them needs a 14-lap race from lap 12; across the
    # line, the lap in progress is the one it covers.
    state = RaceState(lap=12, laps_total=13 if crossed else 14,
                      stint_ends_on_lap=12, fuel_l=1.0, fuel_per_lap_l=3.0,
                      fuel_capacity_l=100.0, next_compound="RS",
                      next_tyres=True, crossed_in_box=crossed)
    spoken = next_call(state).spoken()
    assert frame in spoken, spoken
    assert manifest.uncovered_reason(spoken) is None, spoken
    assert _plays(spoken), manifest.segments_for(spoken)


def test_a_sentence_of_numbers_alone_is_not_split():
    assert manifest._split_on_numbers("3 7.") is None


def test_the_inverted_pairs_still_win_over_the_word_fallback():
    assert gap_side("how far ahead am i") == "behind"
    assert gap_side("how far behind am i") == "ahead"


def test_a_gap_of_nothing_is_not_a_reading_or_the_nearer_car():
    snapshot = {"wallRunning": True, "gapAheadS": 0.0, "gapAheadName": "Boxhead",
                "gapBehindS": 2.0, "gapBehindName": "Rocket"}
    said = answer(GAP, snapshot, heard="what's the gap").text
    assert "0.0" not in said
    assert said.startswith("Rocket is 2.0 seconds behind")
