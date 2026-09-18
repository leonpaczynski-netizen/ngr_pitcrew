"""The box call that carries a decision, played from the pack (11 Sep 2026).

**Every box call carrying a tyre decision missed the pack.** Measured before
this change over 36 box-call shapes: 15 misses. "Box this lap. RS on. On the
plan." asked for a clip called "RS on. On the plan."; "Box this lap. No
tyres. ..." the same; and every overdue call - "2 laps overdue." - asked for
a tail nothing declared. The one the driver most needs without a pause, the
overdue box call with a tyre word, was not even counted as a miss: the peel
failed on "RS on.", the rest landed as one clause holding two numbers, and
`uncovered_reason` filed it as a DECLARED gap - a decision nobody made.

The tyre word arrived with the Phase 0.2 decision (plan §6), and the pack's
states were never extended to it, so since then every stop with a `tyres`
field has been a live synthesis on the call he acts on.
"""
from __future__ import annotations

import pytest

from pitcrew.engineer import phrase_manifest as manifest
from pitcrew.engineer.intents import GAP, answer
from pitcrew.race.calls import RaceState, next_call


def _plays(line: str) -> bool:
    clips = set(manifest.clips())
    segments = manifest.segments_for(line)
    return bool(segments) and all(name in clips for name in segments)


@pytest.mark.parametrize("tyres", [True, False, None])
@pytest.mark.parametrize("compound", ["RS", "RM", "IM", None])
@pytest.mark.parametrize("lap, end", [(6, 6), (6, 7), (6, 8), (7, 6), (9, 6)])
def test_every_box_call_plays_from_the_pack(tyres, compound, lap, end):
    call = next_call(RaceState(lap=lap, laps_total=20, stint_ends_on_lap=end,
                               next_compound=compound, next_tyres=tyres))
    if call is None:
        return
    spoken = call.spoken()
    # **Not a declared gap either.** The overdue call with a tyre word was
    # filed as one, which is how it hid from the coverage test.
    assert manifest.uncovered_reason(spoken) is None, spoken
    assert _plays(spoken), (spoken, manifest.segments_for(spoken))


def test_an_overdue_call_short_of_the_flag_plays():
    """The FUEL_SHORT register inside the overdue call: "You're 3.0 laps
    short of the flag on current burn - short-shift and lift if you stay
    out." Its tail was declared nowhere."""
    call = next_call(RaceState(lap=9, laps_total=20, stint_ends_on_lap=6,
                               fuel_l=8.0, fuel_per_lap_l=1.0,
                               fuel_capacity_l=100.0, next_compound="RS",
                               next_tyres=True))
    assert "short of the flag" in call.spoken()
    assert _plays(call.spoken()), manifest.segments_for(call.spoken())


def test_an_overdue_call_with_fuel_to_spare_plays():
    call = next_call(RaceState(lap=8, laps_total=20, stint_ends_on_lap=6,
                               fuel_l=60.0, fuel_per_lap_l=3.4,
                               fuel_capacity_l=100.0))
    assert _plays(call.spoken()), manifest.segments_for(call.spoken())


def test_no_gap_read_yet_plays():
    """Said at the moment he has just failed to get an answer - the exchange
    that has already gone wrong, and the worst place for a pause."""
    line = answer(GAP, {"wallRunning": True}).text
    assert line.startswith("No gap read yet")
    assert _plays(line), line


def test_the_pack_stays_within_budget_with_the_decisions_in_it():
    # 880 since 18 Sep 2026 - see `test_voice_pack.test_the_pack_stays_within_budget`.
    assert len(manifest.clips()) < 880
