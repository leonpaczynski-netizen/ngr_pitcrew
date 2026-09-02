"""Where he is in the field, said as it changes.

`packet.current_position` and `cars_in_race` were decoded correctly from the
first version of the parser and read by nothing in `pitcrew/race/` - so every
race the engineer has run was run as though the driver were alone on the
circuit. These are the tests for the wiring that fixed that, and for the one
documented exception to the two registers: **position is a fact, and it is
volunteered anyway.**
"""
from __future__ import annotations

import pytest

from pitcrew.race.calls import (
    BOX_NOW,
    DECISION,
    EVENT,
    FACT,
    POSITION,
    POSITION_HOLD_FRAMES,
    POSITION_MAX_STEP,
    REGISTER,
    STATUS,
    URGENCY,
    RaceState,
    position_change,
    register_of,
)


def a_state(**overrides) -> RaceState:
    fields = dict(lap=5, laps_total=20, position=6, field_size=12,
                  position_said=6)
    fields.update(overrides)
    return RaceState(**fields)


def settle(state: RaceState, position: int):
    """Feed the same new position until the hold is served. Returns the call."""
    state.position = position
    call = None
    for _ in range(POSITION_HOLD_FRAMES):
        call = position_change(state)
        if call is not None:
            return call
    return call


# --- the hold --------------------------------------------------------------

def test_a_place_is_not_said_until_it_holds():
    """A side-by-side swaps the byte for a few frames and swaps it back.

    Three sentences about nothing is worse than silence, and at 60 Hz the
    hold is a third of a second of the new position actually standing.
    """
    state = a_state()
    state.position = 7
    for _ in range(POSITION_HOLD_FRAMES - 1):
        assert position_change(state) is None


def test_a_place_that_holds_is_said_once():
    state = a_state()
    call = settle(state, 7)
    assert call is not None
    assert call.kind is POSITION or call.kind == POSITION
    # ...and not again on the next frame, or the one after that.
    assert position_change(state) is None
    assert position_change(state) is None


def test_a_swap_that_reverses_inside_the_hold_says_nothing():
    state = a_state()
    for _ in range(POSITION_HOLD_FRAMES - 1):
        state.position = 7
        assert position_change(state) is None
    state.position = 6
    assert position_change(state) is None
    # And the pending count has been cleared, not merely paused: the next
    # genuine change must serve a full hold of its own.
    state.position = 7
    for _ in range(POSITION_HOLD_FRAMES - 1):
        assert position_change(state) is None


def test_the_first_reading_is_a_baseline_and_not_news():
    """He knows where he started. What he cannot see is the next change."""
    state = a_state(position_said=None, position=6)
    assert position_change(state) is None
    assert state.position_said == 6


# --- what it says ----------------------------------------------------------

def test_a_place_gained_says_so_with_the_field_size():
    """**The position is the call and the direction is the reason.** BLUF, and
    it is also what keeps the voice pack affordable - see
    `phrase_manifest.position_fragments`."""
    state = a_state(position=6, position_said=7, field_size=12)
    call = settle(state, 6)
    assert call.call == "P6 of 12."
    assert call.reason == "You've made a place."
    assert call.spoken() == "P6 of 12. You've made a place."


def test_a_place_lost_says_so():
    state = a_state(position_said=6)
    call = settle(state, 7)
    assert call.call == "P7 of 12."
    assert call.reason == "You've lost a place."


def test_more_than_one_place_is_counted():
    state = a_state(position_said=6)
    call = settle(state, 9)
    assert call.reason == "You've lost 3 places."


def test_the_position_call_plays_from_the_pack():
    """It arrives mid-corner and cannot be asked for again, so a fall to live
    synthesis here is a pause on the one call he cannot repeat."""
    from pitcrew.engineer import phrase_manifest

    state = a_state(position_said=6)
    call = settle(state, 7)
    for part in (call.call, call.reason):
        assert phrase_manifest.segments_for(part) is not None, part


def test_the_field_size_is_omitted_when_it_is_not_known():
    """`cars_in_race` returns 0 for the 255 sentinel, and 0 is not a field."""
    state = a_state(position_said=6, field_size=None)
    call = settle(state, 7)
    assert call.call == "P7."


def test_a_jump_larger_than_anyone_overtook_is_not_counted():
    """A restart or a re-grid moves the byte by more than a place change.

    The position is still real and still worth saying; the count would be a
    fiction, so it is not offered.
    """
    state = a_state(position_said=3)
    call = settle(state, 3 + POSITION_MAX_STEP + 1)
    assert call.reason == ""
    assert call.call.startswith("P")


# --- when it stays quiet ---------------------------------------------------

@pytest.mark.parametrize("overrides", [
    {"in_pit": True},
    {"finished": True},
    {"lap": 0},
    {"position": 0},
])
def test_silent_where_a_position_is_not_a_place_on_the_road(overrides):
    """Positions during a stop are arithmetic about cars still circulating.

    Every one of them reverses on exit and none is a place he won or lost.
    """
    state = a_state(position_said=6, **overrides)
    for _ in range(POSITION_HOLD_FRAMES + 2):
        assert position_change(state) is None


# --- the registers ---------------------------------------------------------

def test_every_ranked_kind_declares_a_register():
    """A kind that can be spoken and has no register is the defect this split
    exists to prevent: a new instruction quietly treated as a fact."""
    for kind in URGENCY:
        assert register_of(kind) in (DECISION, EVENT, FACT), kind


def test_an_unclassified_kind_raises_rather_than_defaulting():
    with pytest.raises(KeyError):
        register_of("something-nobody-classified")


def test_position_and_the_heartbeat_are_the_only_volunteered_facts():
    """Both are there for one reason: he races with GT7's race HUD off.

    If a third joins them, someone has to have decided that he cannot obtain
    it himself either - so this test exists to make that a decision rather
    than a drift.
    """
    facts = {kind for kind, reg in REGISTER.items() if reg == FACT}
    assert facts == {POSITION, STATUS}


def test_the_box_call_is_an_instruction():
    assert register_of(BOX_NOW) == DECISION


def test_position_ranks_below_every_ranked_instruction():
    """It is a fact. It never actually contends - it is emitted mid-lap - but
    a fact that could outrank an instruction is a register that does not mean
    anything."""
    for kind in URGENCY:
        if register_of(kind) == DECISION:
            assert URGENCY.index(kind) < URGENCY.index(POSITION), kind


def test_the_kinds_outside_the_ranking_are_the_known_six():
    """`URGENCY` ranks what `_candidates` offers. Six kinds reach the driver
    by another road and are classified here anyway, because the register is
    about whether a thing may be said unasked and that question does not care
    which function composed it.

    `TYRE` is the retired modelled warning - kept classified so an old record
    can still be read, not because anything emits it.

    **The three rival kinds are unranked on purpose, and this test is the
    reason the choice got made rather than defaulted.** They are composed in
    `race/rival_calls.py` and nothing offers them to `_candidates` yet, so a
    rank here would be an ordering against contention that no test exercises.
    `next_call` sorts on `URGENCY.index`, so the day one of them IS wired it
    raises on the race path - loudly, at the point the ordering question is
    real - which is exactly what `WEAR` did until a test asked for it. The
    decision itself is written down in `rival_calls.py` so it need not be
    re-derived: a rival's stop ranks BELOW every call about our own fuel,
    because a car about to run dry outranks news about somebody else.
    """
    from pitcrew.race.calls import SAVING_RESPONSE, STAY_OUT, TYRE
    from pitcrew.race.rival_calls import (
        RIVAL_BOXED, RIVAL_COMMITTED, STAY_OUT_FUEL,
    )

    assert set(REGISTER) - set(URGENCY) == {
        STAY_OUT, SAVING_RESPONSE, TYRE,
        RIVAL_BOXED, RIVAL_COMMITTED, STAY_OUT_FUEL,
    }
