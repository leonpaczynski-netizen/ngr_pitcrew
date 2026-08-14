"""A compound tagged once carries to the end of its stint.

*"When I enter a tyre compound at the start of the stint replicate that
compound until either the end of the stint or until you detect a tyre change
due to temp drop while being < 10 kmh."*

The tyre change he describes is what opens a run, so the run boundary is
already the answer: it is set by a refuel, by a detected stop, or by going
back to the garage, and every one of those is a point where the set could
have come off.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.analysis.runs import carry_compound


@dataclass
class Row:
    """The fields `split_runs` and the fill need. Mutable, like the rack's."""
    lap_id: int
    lap_num: int
    fuel_start: float
    fuel_end: float
    compound: str | None = None
    is_pit_lap: bool = False
    tyres_changed: bool | None = None
    session_id: int | None = 1
    practice_mode: str | None = "time-trial"


def a_stint(first_lap: int, count: int, *, tank: float = 100.0,
            session_id: int = 1) -> list[Row]:
    return [Row(lap_id=first_lap + n, lap_num=first_lap + n,
                fuel_start=tank - 6.0 * n, fuel_end=tank - 6.0 * (n + 1),
                session_id=session_id)
            for n in range(count)]


def test_tagging_the_first_lap_tags_the_whole_stint():
    rows = a_stint(1, 6)
    rows[0].compound = "RM"
    changed = carry_compound(rows, lap_id=1)
    assert [row.compound for row in rows] == ["RM"] * 6
    assert {row.lap_id for row in changed} == {1, 2, 3, 4, 5, 6}


def test_it_stops_at_the_stop_and_does_not_reach_the_next_set():
    """A refuel opens a new run, which is where the tyres could have changed.
    Running past it would claim a compound for a set nobody has tagged."""
    rows = a_stint(1, 4) + a_stint(5, 4)
    rows[0].compound = "RH"
    carry_compound(rows, lap_id=1)
    assert [row.compound for row in rows] == ["RH"] * 4 + [None] * 4


def test_a_detected_tyre_change_ends_the_fill_with_no_refuel_at_all():
    """The case he described: the set came off and no fuel went in."""
    rows = a_stint(1, 6)
    rows[2].is_pit_lap = True
    rows[2].tyres_changed = True
    rows[0].compound = "RS"
    carry_compound(rows, lap_id=1)
    assert [row.compound for row in rows] == ["RS", "RS", "RS", None, None, None]


def test_tagging_mid_stint_does_not_reach_backwards():
    """Tagging lap 4 says what lap 4 ran on. Filling backwards would overwrite
    a tag he had already made on an earlier lap and disagreed with."""
    rows = a_stint(1, 6)
    rows[0].compound = "RM"
    rows[3].compound = "RH"
    carry_compound(rows, lap_id=4)
    assert [row.compound for row in rows] == [
        "RM", None, None, "RH", "RH", "RH"]


def test_clearing_a_tag_clears_only_that_lap():
    """Untagging is not a claim about the rest of the stint."""
    rows = a_stint(1, 4)
    rows[0].compound = "RM"
    carry_compound(rows, lap_id=1)
    rows[1].compound = None
    changed = carry_compound(rows, lap_id=2)
    assert [row.compound for row in rows] == ["RM", None, "RM", "RM"]
    assert [row.lap_id for row in changed] == [2]


def test_going_back_to_the_garage_ends_the_stint():
    rows = a_stint(1, 3) + a_stint(4, 3, session_id=2)
    rows[0].compound = "RH"
    carry_compound(rows, lap_id=1)
    assert [row.compound for row in rows] == ["RH"] * 3 + [None] * 3
