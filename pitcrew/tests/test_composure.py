"""The engineer knowing when to shut up.

*"I came off track and was frustrated and then George kept telling me every
time someone passed me which made me more angry. Better for him to keep quiet
and then encourage when I am back on track."*

A driver report about the engineer, which CLAUDE.md rule 1 makes primary
evidence — and read plainly, a correctness bug: several true things said at the
one moment they could only do harm.
"""
from __future__ import annotations

import pytest

from pitcrew.race.calls import DECISION, EVENT, FACT
from pitcrew.race.composure import (
    OFF_MIN_S,
    SETTLE_S,
    WORTH_SAYING_S,
    Composure,
)

STEP = 1.0 / 60.0


def _run(comp: Composure, surfaces: str, seconds: float) -> None:
    for _ in range(int(seconds / STEP)):
        comp.update(tuple(surfaces), STEP)


def _fresh() -> Composure:
    comp = Composure()
    comp.reset()
    return comp


def test_a_settled_driver_hears_everything():
    comp = _fresh()
    _run(comp, "TTTT", 5.0)
    assert comp.composed
    assert comp.may_volunteer(FACT)


def test_going_off_stops_the_engineer_volunteering_facts():
    comp = _fresh()
    _run(comp, "GGTT", OFF_MIN_S + 0.2)
    assert comp.off
    assert not comp.may_volunteer(FACT)


def test_a_decision_is_never_withheld_however_angry_he_is():
    """If he needs to box, that is the same whether he has just been off or
    not. Withholding it would be the app deciding what he can cope with."""
    comp = _fresh()
    _run(comp, "GGGG", 4.0)
    assert not comp.may_volunteer(FACT)
    assert comp.may_volunteer(DECISION)
    assert comp.may_volunteer(EVENT)


def test_the_quiet_lasts_past_the_rejoin():
    """He is not composed the instant four wheels touch tarmac again."""
    comp = _fresh()
    _run(comp, "GGGG", 3.0)
    _run(comp, "TTTT", SETTLE_S / 2)
    assert not comp.off
    assert not comp.composed
    assert not comp.may_volunteer(FACT)


def test_and_then_it_ends():
    comp = _fresh()
    _run(comp, "GGGG", 3.0)
    _run(comp, "TTTT", SETTLE_S + 1.0)
    assert comp.composed
    assert comp.may_volunteer(FACT)


def test_clipping_a_kerb_is_not_a_moment():
    """He rides kerbs by design. `C` is deliberately not an off-surface."""
    comp = _fresh()
    _run(comp, "TTCC", 3.0)
    assert not comp.off
    assert comp.may_volunteer(FACT)


def test_brushing_the_grass_at_a_track_limit_is_not_a_moment_either():
    comp = _fresh()
    _run(comp, "TTGT", OFF_MIN_S / 2)
    _run(comp, "TTTT", SETTLE_S)
    assert comp.composed
    assert comp.owed() is None


# ------------------------------------------------------------ the way back

def test_the_word_on_the_way_back_carries_what_it_cost():
    comp = _fresh()
    _run(comp, "GGGG", 4.0)
    _run(comp, "TTTT", SETTLE_S + 0.5)
    owed = comp.owed()
    assert owed is not None
    assert owed == pytest.approx(4.0, abs=0.2)


def test_it_is_said_once_and_not_every_frame():
    """Saying it repeatedly is the defect being fixed, not a second copy."""
    comp = _fresh()
    _run(comp, "GGGG", 4.0)
    _run(comp, "TTTT", SETTLE_S + 0.5)
    assert comp.owed() is not None
    assert comp.owed() is None
    _run(comp, "TTTT", 5.0)
    assert comp.owed() is None


def test_nothing_is_owed_until_he_is_actually_back():
    comp = _fresh()
    _run(comp, "GGGG", 4.0)
    assert comp.owed() is None
    _run(comp, "TTTT", SETTLE_S / 3)
    assert comp.owed() is None


def test_a_moment_too_small_to_mention_is_not_mentioned():
    """He knows he brushed the grass. Being congratulated for surviving it is
    worse than silence."""
    comp = _fresh()
    _run(comp, "GGTT", OFF_MIN_S + 0.1)
    assert comp.off
    _run(comp, "TTTT", SETTLE_S + 0.5)
    assert WORTH_SAYING_S > OFF_MIN_S + 0.1
    assert comp.owed() is None


# --------------------------------------------------------------- soundness

def test_a_packet_with_no_surface_channel_does_not_assert_composure():
    """Formats A and B carry no surface characters. Treating missing as clean
    would make this silently inert on a fallback format."""
    comp = _fresh()
    _run(comp, "GGGG", 3.0)
    for _ in range(600):
        comp.update(None, STEP)
    assert not comp.composed, "absent is missing, not on-track"


def test_reset_clears_a_recovery_so_a_race_does_not_open_mid_silence():
    """CLAUDE.md rule 11 — state that outlives a session is read as belonging
    to it."""
    comp = _fresh()
    _run(comp, "GGGG", 4.0)
    assert not comp.composed
    comp.reset()
    assert comp.composed
    assert comp.owed() is None
