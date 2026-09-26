"""Compound bests on the practice tablet — Story 3, 25 Sep 2026.

`compound_bests_for_session` filters to counted laps only and groups by
compound.  `compose_practice` carries the result in a "compound_bests" key.
"""
from __future__ import annotations

from pitcrew.race.compound_bests import compound_bests_for_session
from pitcrew.ui.driver_view import DriverState
from pitcrew.ui.tablet import compose_practice


# ----------------------------------------- helpers: duck-type LapRow


class _Row:
    """Minimal duck-type for a LapRow with the fields we need."""
    def __init__(self, ms, compound, *,
                 excluded=False, is_out_lap=False, is_pit_lap=False,
                 incident=False):
        self.lap_time_ms = ms
        self.compound = compound
        self.excluded = excluded
        self.is_out_lap = is_out_lap
        self.is_pit_lap = is_pit_lap
        self.incident = incident

    @property
    def counted(self):
        return not (self.excluded or self.is_out_lap or self.is_pit_lap
                    or self.incident)


# ----------------------------------------- unit: compound_bests_for_session


def test_compound_bests_excludes_out_laps():
    """An out-lap with a fast time must not appear in the best or count."""
    rows = [
        _Row(90_000, "RS"),        # counted, best
        _Row(80_000, "RS", is_out_lap=True),  # NOT counted
        _Row(92_000, "RS"),        # counted
    ]
    result = compound_bests_for_session(rows)
    assert len(result) == 1
    assert result[0]["best_ms"] == 90_000
    assert result[0]["lap_count"] == 2


def test_compound_bests_null_time_excluded():
    rows = [
        _Row(None, "RS"),          # null time: excluded
        _Row(100_000, "RS"),
        _Row(99_000, "RS"),
    ]
    result = compound_bests_for_session(rows)
    assert len(result) == 1
    assert result[0]["lap_count"] == 2
    assert result[0]["best_ms"] == 99_000


def test_compound_bests_two_compounds():
    """Two compounds → two entries, each correct, ordered by best_ms."""
    rows = [
        _Row(95_000, "RS"),
        _Row(93_000, "RS"),
        _Row(100_000, "RM"),
        _Row(98_000, "RM"),
    ]
    result = compound_bests_for_session(rows)
    assert len(result) == 2
    # RS best is 93 000, RM best is 98 000 → RS first
    assert result[0]["compound"] == "RS"
    assert result[0]["best_ms"] == 93_000
    assert result[1]["compound"] == "RM"
    assert result[1]["best_ms"] == 98_000


def test_compound_bests_empty_returns_empty_list():
    assert compound_bests_for_session([]) == []
    assert compound_bests_for_session(None) == []


def test_compound_bests_all_uncounted_returns_empty():
    rows = [_Row(90_000, "RS", is_out_lap=True)]
    assert compound_bests_for_session(rows) == []


# ----------------------------------------- integration: compose_practice


def _practising(**over) -> DriverState:
    base = dict(session_kind="practice", lap_number=5,
                last_lap_ms=100_000, compound="RS")
    base.update(over)
    return DriverState(**base)


def test_compose_practice_compound_bests_key_present():
    """compound_bests on DriverState → key present with correct entries."""
    state = _practising(compound_bests=[
        {"compound": "RS", "best_ms": 93_000, "lap_count": 5},
        {"compound": "RM", "best_ms": 98_000, "lap_count": 3},
    ])
    body = compose_practice(state)
    assert "compound_bests" in body
    assert len(body["compound_bests"]) == 2
    assert body["compound_bests"][0]["compound"] == "RS"
    assert body["compound_bests"][0]["best_ms"] == 93_000
    assert body["compound_bests"][0]["lap_count"] == 5


def test_compose_practice_compound_bests_absent_when_none():
    """compound_bests=None → key absent (not computed, not empty)."""
    state = _practising(compound_bests=None)
    body = compose_practice(state)
    assert "compound_bests" not in body


def test_compose_practice_compound_bests_empty_list_when_no_compounds():
    """compound_bests=[] → key present with empty list (laps but no disc reads)."""
    state = _practising(compound_bests=[])
    body = compose_practice(state)
    assert "compound_bests" in body
    assert body["compound_bests"] == []
