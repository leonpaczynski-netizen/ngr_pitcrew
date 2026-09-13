"""Asked for laps, he is answered in laps.

Suzuka, 13 Sep 2026 (session 166), a timed race:

    act 'Laps left.' as laps-left (distance 0.089)
    radio table: heard 'Laps left.', said '16 minutes left.'

The count was not firm yet, so the lap figure was withheld entirely and the
clock was quoted in its place. Rule 13: an answer in a different unit from the
question is a different answer, and under a helmet he cannot ask which one he
got. When the count is soft he gets the hedged pair - the same words and the
same renderer as the heartbeat (`calls.laps_to_go`) - and the clock after it.
"""
from __future__ import annotations

import pytest

from pitcrew.engineer import phrase_manifest as manifest
from pitcrew.engineer.intents import LAPS_LEFT, NO_LAP_COUNT, answer

TIMED = {"raceMinutes": 30.0, "remainingS": 16 * 60 + 5.0,
         "lapsRemaining": 9}


def said(snapshot, heard="Laps left."):
    return answer(LAPS_LEFT, snapshot, heard=heard)


def test_the_race_that_answered_in_minutes():
    """The exact snapshot shape from the race: timed, count not yet firm."""
    reply = said({**TIMED, "lapsEstimateFirm": False})
    assert reply.text == "8 or 9 laps to go. 16 minutes left."
    assert reply.answered is True


def test_a_firm_count_is_said_flat_and_first():
    reply = said({**TIMED, "lapsEstimateFirm": True})
    assert reply.text == "9 laps to go. 16 minutes left."


def test_a_firm_count_the_heartbeat_hedges_is_hedged_here_too():
    """`laps_count_hedged` turns the heartbeat's figure into a pair. The same
    figure asked for must not come back flat (rule 13)."""
    reply = said({**TIMED, "lapsEstimateFirm": True,
                  "lapsCountHedged": True})
    assert reply.text == "8 or 9 laps to go. 16 minutes left."


def test_one_lap_is_never_a_pair_with_zero():
    reply = said({**TIMED, "remainingS": 80.0, "lapsRemaining": 1,
                  "lapsEstimateFirm": False})
    assert reply.text == "1 lap to go. 80 seconds left."


def test_no_count_at_all_says_so_before_the_clock():
    reply = said({**TIMED, "lapsRemaining": None})
    assert reply.text == f"{NO_LAP_COUNT} 16 minutes left."
    assert reply.answered is False


def test_a_count_that_has_run_out_is_not_spoken_as_zero():
    reply = said({**TIMED, "remainingS": 45.0, "lapsRemaining": 0,
                  "lapsEstimateFirm": True})
    assert reply.text == f"{NO_LAP_COUNT} 45 seconds left."


@pytest.mark.parametrize("heard", ["how long", "time left",
                                   "how much longer", "how many minutes"])
def test_a_question_about_time_is_answered_with_the_clock_first(heard):
    reply = said({**TIMED, "lapsEstimateFirm": True}, heard=heard)
    assert reply.text == "16 minutes left. 9 laps to go."


def test_a_time_question_still_hedges_a_soft_count():
    reply = said({**TIMED, "lapsEstimateFirm": False}, heard="how long")
    assert reply.text == "16 minutes left. 8 or 9 laps to go."


def test_no_clock_still_leads_with_the_laps():
    reply = said({**TIMED, "remainingS": None, "lapsEstimateFirm": False})
    assert reply.text.startswith("No clock.")
    assert "laps to go" in reply.text


@pytest.mark.parametrize("heard", ["Laps left.", "how many laps to go",
                                   None])
def test_the_lap_race_is_unchanged(heard):
    """Tomorrow is a 20-lap race: the count is a regulation, said alone."""
    reply = said({"raceMinutes": None, "lapsRemaining": 12}, heard=heard)
    assert reply.text == "12 laps to go."


@pytest.mark.parametrize("snapshot", [
    {**TIMED, "lapsEstimateFirm": False},
    {**TIMED, "lapsEstimateFirm": True},
    {**TIMED, "lapsRemaining": None},
])
def test_every_timed_answer_plays_from_the_pack(snapshot):
    """A pause before the answer lands on the exchange he started."""
    clips = set(manifest.clips())
    text = said(snapshot).text
    segments = manifest.segments_for(text)
    assert segments is not None, text
    assert [s for s in segments if s not in clips] == [], text


def test_the_coordinator_snapshot_carries_the_hedge():
    """The answer can only hedge on what the snapshot hands it."""
    from pitcrew.race.coordinator import RaceCoordinator

    race = RaceCoordinator(None)
    assert race.snapshot()["lapsCountHedged"] is False
    race.state.laps_count_hedged = True
    assert race.snapshot()["lapsCountHedged"] is True
