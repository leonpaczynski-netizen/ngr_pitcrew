"""Practice rack sector columns — Story 4, 25 Sep 2026.

`history_rows(kind="practice")` now computes per-sector stint/session bests and
paints them with `rank_ink`.  `practice_history` passes `compound` and
`sectors_ms` from each `LapRow`.  These tests hold the ranking rule, the
out-lap guard, and the import path.
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pitcrew.ui import theme  # noqa: E402
from pitcrew.ui.driver_view import HistoryRow, history_rows, practice_history  # noqa: E402


# ----------------------------------------- smoke: rank_ink import


def test_rank_ink_import_not_copy():
    """rank_ink is importable from practice_screen with no AttributeError."""
    from pitcrew.ui.practice_screen import rank_ink  # noqa: F401


# ----------------------------------------- practice_history


class _LapRow:
    """Minimal duck-type matching practice_screen.LapRow fields we need."""
    def __init__(self, num, ms, *, out=False, pit=False, excluded=False,
                 incident=False, compound="RS",
                 sectors=(40_000, 36_000, 25_000), fuel=3.0):
        self.lap_num = num
        self.lap_time_ms = ms
        self.fuel_used = fuel
        self.is_out_lap = out
        self.is_pit_lap = pit
        self.excluded = excluded
        self.incident = incident
        self.compound = compound
        self._sectors = sectors
        self.exclusion_reason = None

    @property
    def counted(self):
        return not (self.excluded or self.is_out_lap or self.is_pit_lap
                    or self.incident)

    @property
    def sectors_ms(self):
        return self._sectors


def test_practice_history_includes_compound_and_sectors():
    row = _LapRow(1, 101_000, compound="RM",
                  sectors=(40_000, 36_000, 25_000))
    result = practice_history([row])
    assert len(result) == 1
    d = result[0]
    assert d["compound"] == "RM"
    assert d["sectors_ms"] == (40_000, 36_000, 25_000)


def test_practice_history_out_lap_compound_present():
    """Out-lap keeps its compound field but carries no delta."""
    row = _LapRow(1, 80_000, out=True, compound="RS")
    result = practice_history([row])
    assert result[0]["compound"] == "RS"
    assert result[0]["lap_delta_s"] is None


def test_practice_history_missing_sectors_defaults_to_none_triple():
    """A LapRow without sectors_ms defaults to (None, None, None), no raise."""
    class _Plain:
        lap_num = 1
        lap_time_ms = 100_000
        fuel_used = 3.0
        is_out_lap = False
        is_pit_lap = False
        excluded = False
        incident = False
        compound = "RS"
        exclusion_reason = None

        @property
        def counted(self):
            return True

    result = practice_history([_Plain()])
    assert result[0]["sectors_ms"] == (None, None, None)


# ----------------------------------------- history_rows sector ranking


def _lap(n, ms, sectors, *, out=False, pit=False, compound="RS"):
    """A history dict as practice_history produces."""
    return {
        "lap": n,
        "lap_ms": ms,
        "lap_delta_s": None if (out or pit) else (ms - 100_000) / 1000.0,
        "burn_l": 3.0,
        "burn_delta_l": None,
        "saving": None,
        "why": None,
        "pit": pit,
        "out": out,
        "counted": not (out or pit),
        "compound": compound,
        "sectors_ms": sectors,
    }


def test_history_rows_sector_rank_purple_for_session_best():
    """The fastest sector time in the session earns BEST_EVER."""
    history = [
        _lap(1, 100_000, (40_000, 36_000, 24_000)),   # s3 = session best
        _lap(2, 101_000, (40_000, 36_000, 25_000)),
    ]
    rows = history_rows(history, kind="practice")
    assert len(rows) == 2
    # lap 1 has the best s3 in the session
    assert rows[0].sector_tones[2] == theme.BEST_EVER


def test_history_rows_sector_rank_green_for_stint_best():
    """A sector best of its own stint (not session) earns BEST_STINT."""
    history = [
        _lap(1, 100_000, (40_000, 36_000, 24_000)),   # stint best session best
        {"lap": 2, "lap_ms": None, "lap_delta_s": None, "burn_l": None,
         "burn_delta_l": None, "saving": None, "why": None,
         "pit": True, "out": False, "counted": False,
         "compound": None, "sectors_ms": (None, None, None)},
        _lap(3, 101_000, (39_000, 36_000, 25_000)),   # s1 best of new stint
        _lap(4, 102_000, (40_000, 36_000, 26_000)),
    ]
    rows = history_rows(history, kind="practice")
    # Row index 2 (lap 3) should have s1 as BEST_STINT but s1=39_000 > session
    # best of 40_000 from lap 1... wait, 39 < 40 so it IS the session best too.
    # Let's check s3: lap 3 s3=25_000, session best s3=24_000. Not session best.
    # lap 3's s3 should be BEST_STINT (best of second stint) = BEST_STINT.
    # row index 2 is lap 3 (after the pit row)
    s3_tone = rows[2].sector_tones[2]
    assert s3_tone == theme.BEST_STINT


def test_history_rows_sector_rank_null_for_out_lap():
    """An out-lap cannot hold a mark regardless of time (rank_ink rule)."""
    history = [_lap(1, 80_000, (35_000, 30_000, 20_000), out=True)]
    rows = history_rows(history, kind="practice")
    assert all(t is None for t in rows[0].sector_tones)


def test_history_rows_null_sector_no_rank():
    """A sector of None stays None, never ranked."""
    history = [
        _lap(1, 100_000, (40_000, None, 25_000)),
        _lap(2, 101_000, (40_000, None, 26_000)),
    ]
    rows = history_rows(history, kind="practice")
    # s2 is None for both: no rank possible
    assert rows[0].sectors[1] is None
    assert rows[0].sector_tones[1] is None


def test_history_rows_compound_carried():
    """Compound on each history row is passed through."""
    history = [_lap(1, 100_000, (40_000, 36_000, 25_000), compound="RM")]
    rows = history_rows(history, kind="practice")
    assert rows[0].compound == "RM"


def test_history_rows_race_mode_no_sector_tones():
    """In race mode all sector tones are None (no rank_ink called)."""
    history = [
        {"lap": 1, "lap_ms": 100_000, "lap_delta_s": 0.5,
         "burn_l": 5.0, "burn_delta_l": 0.1, "saving": False,
         "why": None, "pit": False, "out": False,
         "compound": "RS", "sectors_ms": (40_000, 36_000, 25_000)},
    ]
    rows = history_rows(history, kind="race")
    assert all(t is None for t in rows[0].sector_tones)
    # time_tone also None in race mode
    assert rows[0].time_tone is None
