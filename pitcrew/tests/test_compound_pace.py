"""Plan row 5.22 - bests per compound, and gaps between compounds on the lap and
each sector, off like-for-like laps only."""
from __future__ import annotations

import ast
import inspect
import textwrap
from types import SimpleNamespace

import pytest

from pitcrew.analysis.compound_pace import (
    SITTING_GAP_H,
    compound_pace,
    reference_by_hardness,
    may_set_a_best,
    sitting_line,
    sittings,
)
from pitcrew.analysis.session import LapInput
from pitcrew.strategy.evidence import (
    PACE_MIN_LAPS,
    comparable_groups,
    comparable_pace,
    comparable_pools,
)

MODEL = "sardegna:thirds:1704/3409"


def lap(n, ms, *, code="RH", session=1, fuel=None, sectors=None, model=MODEL,
        version="1.71", **flags):
    """A lap whose sectors add to its time unless told otherwise."""
    if sectors is None:
        third = ms // 3
        sectors = (third, third, ms - 2 * third)
    return LapInput(lap_num=n, lap_time_ms=ms,
                    fuel_start=100.0 - 7 * n if fuel is None else fuel,
                    fuel_end=93.0 - 7 * n if fuel is None else fuel - 7,
                    compound=code, session_id=session, game_version=version,
                    sector1_ms=sectors[0], sector2_ms=sectors[1],
                    sector3_ms=sectors[2], sector_model=model, **flags)


def run(session, code, times, *, start=1, fuel_offset=0.0, **kwargs):
    """An out-lap then `times`, from a full tank less `fuel_offset`, in one
    session."""
    full = 100.0 - fuel_offset
    laps = [lap(start, 120_000, code=code, session=session, is_out_lap=True,
                fuel=full, **kwargs)]
    for age, ms in enumerate(times, start=1):
        laps.append(lap(start + age, ms, code=code, session=session,
                        fuel=full - 7 * age, **kwargs))
    return laps


# ------------------------------------------------------- the lap's sectors

def test_a_non_positive_sector_is_not_measured():
    got = lap(1, 90_000, sectors=(30_000, 0, None))
    assert got.sectors_ms == (30_000, None, None)


def test_the_export_carries_the_sectors_off_the_row():
    from pitcrew.export.build import _rows_to_laps

    row = {"id": 1, "lap_num": 1, "lap_time_ms": 90_000, "fuel_start": 50.0,
           "fuel_end": 43.0, "compound": "RM", "fuel_map": None,
           "is_pit_lap": 0, "is_out_lap": 0, "excluded": 0,
           "exclusion_reason": None, "wear_fl": None, "wear_fr": None,
           "wear_rl": None, "wear_rr": None, "session_id": 3,
           "sector1_ms": 30_100, "sector2_ms": 29_900, "sector3_ms": 30_000,
           "sector_model": MODEL}

    class _Row(dict):
        def keys(self):
            return super().keys()

    got = _rows_to_laps(SimpleNamespace(get_lap_frames=lambda i: None),
                        [_Row(row)], hydrate=set())[0]
    assert got.sectors_ms == (30_100, 29_900, 30_000)
    assert got.sector_model == MODEL


# ------------------------------------------------- one expression of comparable

def test_strategy_still_compares_inside_one_session_and_picks_the_widest():
    laps = (run(1, "RH", [100_000] * 4) + run(1, "RM", [99_000] * 4, start=6)
            + run(2, "RH", [101_000] * 4) + run(2, "RM", [100_500] * 4, start=6)
            + run(2, "RS", [99_500] * 4, start=11))
    groups = comparable_groups(laps, "RH")
    assert set(groups) == {1, 2}
    assert set(comparable_pools(laps, "RH")) == {"RH", "RM", "RS"}
    pace = comparable_pace(laps, "RH")
    assert pace["RM"]["deltaS"] == pytest.approx(-0.5)
    assert pace["RS"]["deltaS"] == pytest.approx(-1.5)
    assert pace["RH"]["deltaS"] == 0.0


def test_a_lap_whose_sector_was_refused_still_ages_the_set():
    """Tyre age is the age on the road: a refused S2 on lap 2 must not let
    lap 6 in as the fifth lap of the set."""
    laps = run(1, "RH", [100_000] * 5)                  # laps 2-6, ages 1-5
    laps[1] = lap(2, 100_000, fuel=93.0, sectors=(33_000, None, 34_000))
    from pitcrew.analysis.compound_pace import _timing

    s2 = _timing("S2", MODEL)
    groups = comparable_groups(laps + run(1, "RM", [99_000] * 4, start=8),
                               "RH", s2)
    rh = {one.lap_num for one in groups[1]["RH"]}
    # Lap 2 has no S2; lap 6 is the fifth lap of the set and out of the window
    # - dropping lap 2 before counting would have let it in as the fourth.
    assert rh == {3, 4, 5}


def test_a_sector_cut_at_other_lines_is_not_a_sector_here():
    from pitcrew.analysis.compound_pace import _timing

    other = lap(1, 90_000, model="sardegna:landmark:1780/3409")
    assert _timing("S1", MODEL)(other) is None
    assert _timing("lap", MODEL)(other) is None
    assert _timing("S1", MODEL)(lap(1, 90_000)) == 30_000


# ------------------------------------------------------------------ bests

def test_a_best_is_the_fastest_counted_lap_driven_line_to_line():
    laps = run(1, "RM", [101_000, 100_400, 100_900])
    laps.append(lap(5, 95_000, code="RM", incident=True))          # a cut
    laps.append(lap(6, 96_000, code="RM", excluded=True))
    laps.append(lap(7, 97_000, code="RM", sectors=(32_000, None, 33_000)))
    pace = compound_pace(laps)
    (best,) = pace.bests
    assert best.compound == "RM" and best.lap_ms == 100_400
    assert best.laps == 3 and best.lap_num == 3
    assert pace.without_sectors == 1


def test_best_sectors_come_from_any_lap_and_the_theoretical_adds_them():
    laps = [lap(1, 100_000, code="RS", sectors=(33_000, 34_000, 33_000)),
            lap(2, 100_500, code="RS", sectors=(34_000, 33_500, 33_000)),
            lap(3, 100_200, code="RS", sectors=(33_500, 34_000, 32_700))]
    (best,) = compound_pace(laps).bests
    assert best.sectors_ms == (33_000, 33_500, 32_700)
    assert best.theoretical_ms == 99_200


def test_bests_are_kept_per_tyre_per_version_and_untagged_laps_join_none():
    laps = ([lap(1, 100_000, code="RH"), lap(2, 99_000, code="RM"),
             lap(3, 98_000, code="RM", version="1.70"), lap(4, 97_000, code=None)])
    pace = compound_pace(laps)
    got = {(b.game_version, b.compound): b.lap_ms for b in pace.bests}
    assert got == {("1.71", "RH"): 100_000, ("1.71", "RM"): 99_000,
                   ("1.70", "RM"): 98_000}
    assert pace.untagged == 1


def test_may_set_a_best_refuses_a_lap_with_no_lines():
    assert not may_set_a_best(lap(1, 90_000, model=None))
    assert not may_set_a_best(lap(1, 90_000, is_pit_lap=True))
    assert may_set_a_best(lap(1, 90_000))


# ------------------------------------------------------------------- gaps

def _sweep():
    """His Sardegna shape: one compound per session, back to back."""
    return (run(153, "RH", [102_700, 102_600, 102_800, 103_000])
            + run(154, "RM", [101_700, 101_600, 101_800, 101_000])
            + run(155, "RS", [100_200, 100_500, 101_000, 100_700]))


def test_one_compound_per_session_is_refused_under_the_session_rule():
    pace = compound_pace(_sweep())
    assert pace.gaps == ()
    # One line, not one per compound as well (critic pass 4, Q1).
    assert pace.refusals == (f"1.71, {MODEL}: no sitting holds two compounds - a gap "
                             f"across sittings would compare the days, not the tyres",)


def test_one_evening_of_back_to_back_runs_is_compared_and_labelled():
    evening = {153: "runs from 2026-09-09 20:09", 154: "runs from 2026-09-09 20:09",
               155: "runs from 2026-09-09 20:09"}
    pace = compound_pace(_sweep(), sitting_of=evening)
    lap_gaps = {g.compound: g for g in pace.gaps if g.timing == "lap"}
    # Medians: RH 102,750; RM 101,650; RS 100,600.
    assert lap_gaps["RM"].delta_s == pytest.approx(-1.10)
    assert lap_gaps["RS"].delta_s == pytest.approx(-2.15)
    assert lap_gaps["RM"].n == 4 and lap_gaps["RM"].reference_n == 4
    assert lap_gaps["RM"].sessions == (153, 154)
    assert lap_gaps["RM"].sitting == "runs from 2026-09-09 20:09"
    assert lap_gaps["RM"].floor_s is None and lap_gaps["RM"].inside_floor is None
    assert {g.timing for g in pace.gaps} == {"lap", "S1", "S2", "S3"}
    # IQR, inclusive: RM 101,000 101,600 101,700 101,800 -> 101,450..101,725
    assert lap_gaps["RM"].spread_s == pytest.approx(0.275)
    # A sitting that has all its gaps refuses nothing - not even the reference
    # against itself (P2).
    assert pace.refusals == ()


def test_an_explicit_reference_is_honoured():
    evening = dict.fromkeys((153, 154, 155), "evening")
    pace = compound_pace(_sweep(), "RM", sitting_of=evening)
    assert {g.reference for g in pace.gaps} == {"RM"}
    assert {g.compound for g in pace.gaps} == {"RH", "RS"}


def test_a_tyre_run_twice_in_the_evening_gives_the_floor():
    laps = (_sweep() + run(156, "RH", [103_600, 103_700, 103_500, 103_800]))
    evening = dict.fromkeys((153, 154, 155, 156), "evening")
    pace = compound_pace(laps, sitting_of=evening)
    rm = next(g for g in pace.gaps if g.compound == "RM" and g.timing == "lap")
    # RH 153 median 102,750, RH 156 median 103,650: moved 0.90 s.
    assert rm.floor_s == pytest.approx(0.90)
    # The reference now pools both RH runs: median 103,250 -> RM -1.60 s.
    assert rm.delta_s == pytest.approx(-1.60)
    assert rm.inside_floor is False
    assert "the same tyre's lap moved 0.90 s" in sitting_line(pace.gaps, "RM", "evening")


def test_two_evenings_are_reported_apart_and_never_pooled():
    laps = (run(1, "RH", [102_000] * 4) + run(2, "RM", [101_000] * 4)
            + run(3, "RH", [104_000] * 4) + run(4, "RM", [101_500] * 4))
    evenings = {1: "a", 2: "a", 3: "b", 4: "b"}
    pace = compound_pace(laps, sitting_of=evenings)
    deltas = sorted(g.delta_s for g in pace.gaps if g.timing == "lap")
    assert deltas == [pytest.approx(-2.5), pytest.approx(-1.0)]
    (line,) = pace.across_sittings()
    assert "1.50 s apart" in line and "something other than the tyre" in line


def test_too_few_laps_on_a_side_is_no_gap():
    laps = run(1, "RH", [102_000] * 4) + run(2, "RM", [101_000] * (PACE_MIN_LAPS - 1))
    pace = compound_pace(laps, sitting_of={1: "a", 2: "a"})
    assert pace.gaps == ()


# ---------------------------------------------------------------- evenings

def test_back_to_back_sessions_chain_and_a_long_break_starts_a_sitting():
    got = sittings([
        {"id": 3, "started_at": "2026-09-10T19:11:36", "ended_at": "2026-09-10T19:45:00"},
        {"id": 1, "started_at": "2026-09-09T20:09:25", "ended_at": "2026-09-09T23:00:00"},
        {"id": 2, "started_at": "2026-09-09T23:50:00", "ended_at": "2026-09-10T00:30:00"},
        {"id": 6, "started_at": "2026-09-10T00:40:00"},        # after midnight
        {"id": 7, "started_at": "2026-09-11T15:00:00", "ended_at": "2026-09-11T15:40:00"},
        {"id": 8, "started_at": "2026-09-11T18:30:00", "ended_at": "2026-09-11T19:00:00"},
        {"id": 9, "started_at": "2026-09-11T22:00:00"},
        {"id": 4, "started_at": None},
        {"id": 5, "started_at": "not a time"},
    ])
    assert got[1] == got[2] == got[6] == "runs from 2026-09-09 20:09"
    assert got[3] == "runs from 2026-09-10 19:11"
    # Chained end to start, never start to start: 15:00, 18:30, 22:00 are three.
    assert len({got[7], got[8], got[9]}) == 3
    assert 4 not in got and 5 not in got


def test_the_sitting_gap_is_measured_from_the_last_end_at_its_boundary():
    """N5."""
    gap = int(SITTING_GAP_H * 60)
    base = {"id": 1, "started_at": "2026-09-09T10:00:00", "ended_at": "2026-09-09T11:00:00"}
    on = sittings([base, {"id": 2, "started_at": f"2026-09-09T{11 + gap // 60:02d}:{gap % 60:02d}:00"}])
    past = sittings([base, {"id": 2, "started_at": f"2026-09-09T{11 + gap // 60:02d}:{gap % 60 + 1:02d}:00"}])
    assert on[1] == on[2] and past[1] != past[2]


def test_a_race_session_does_not_bridge_two_practice_blocks():
    got = sittings([
        {"id": 1, "kind": "practice", "started_at": "2026-09-09T12:00:00", "ended_at": "2026-09-09T12:30:00"},
        {"id": 2, "kind": "race", "started_at": "2026-09-09T13:30:00", "ended_at": "2026-09-09T15:30:00"},
        {"id": 3, "kind": "practice", "started_at": "2026-09-09T16:00:00"},
    ])
    assert 2 not in got and got[1] != got[3]


# ------------------------------------------------------------ the tool and wiring

def test_the_tool_refuses_two_cars():
    from tools.compound_pace import load

    events = {1: {"car_name": "RSR", "track": "Sardegna", "layout": "A"},
              2: {"car_name": "GT3", "track": "Sardegna", "layout": "A"}}
    store = SimpleNamespace(get_event=events.get, list_event_laps=lambda *a: [],
                            list_sessions=lambda e: [])
    laps, evenings, refused = load(store, [1, 2])
    assert laps == [] and "one car at one circuit" in refused


def _method(name):
    from pitcrew.controller import PitCrewController

    source = textwrap.dedent(inspect.getsource(getattr(PitCrewController, name)))
    return ast.parse(source)


def _calls(tree, attr):
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call)
            and getattr(node.func, "attr", "") == attr]


def test_the_screen_is_refreshed_after_a_mark_is_written_not_before():
    tree = _method("_on_lap_changed")
    body = tree.body[0].body
    order = [getattr(getattr(stmt, "value", None), "func", None) for stmt in body]
    names = [getattr(func, "attr", "") for func in order]
    assert "_refresh_compound_pace" in names
    assert names.index("_refresh_compound_pace") > names.index("exclude_lap")


def test_every_rack_load_refreshes_the_plate():
    for name in ("load_active_event", "_on_lap_completed"):
        assert _calls(_method(name), "_refresh_compound_pace"), name


def test_a_failed_read_empties_the_plate_and_never_raises():
    from pitcrew.controller import PitCrewController

    shown = []
    stub = SimpleNamespace(
        practice=SimpleNamespace(show_compound_pace=shown.append),
        store=SimpleNamespace(list_event_laps=lambda *a: 1 / 0,
                              list_sessions=lambda e: []))
    PitCrewController._refresh_compound_pace(stub, 11)
    PitCrewController._refresh_compound_pace(stub, None)
    assert shown == [None, None]


@pytest.fixture(scope="module")
def qt_app():
    import os

    pytest.importorskip("PyQt6.QtWidgets")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _texts(widget):
    from PyQt6.QtWidgets import QLabel

    return [label.text() for label in widget.findChildren(QLabel)
            if label.isVisibleTo(widget) or not widget.isVisible()]


def test_the_plate_shows_bests_the_theoretical_and_the_gap_in_words(qt_app):
    from pitcrew.ui.practice_screen import CompoundPaceView

    view = CompoundPaceView()
    evening = dict.fromkeys((153, 154, 155), "runs from 2026-09-09 20:09")
    view.show_pace(compound_pace(_sweep(), sitting_of=evening))
    texts = " | ".join(_texts(view))
    assert "1:40.200" in texts                       # RS best
    assert "RM on RH, runs from 2026-09-09 20:09: lap -1.10 s" in texts
    assert "BEST S1" in texts and "race plan does not use it" in texts
    # The sector columns are the best sectors, not the lap time (M22).
    rs = next(b for b in view.pace.bests if b.compound == "RS")
    assert f"{rs.sectors_ms[0] / 1000:.3f}" in texts
    view.show_pace(None)
    assert view.empty.isVisibleTo(view) or not view.isVisible()
    assert view.pace is None


def test_the_debrief_prints_the_section(capsys, monkeypatch):
    import tools.debrief as debrief

    store = SimpleNamespace(
        get_event=lambda e: {"car_name": "RSR", "track": "S", "layout": "A"},
        list_event_laps=lambda *a: [], list_sessions=lambda e: [])
    debrief.by_compound(store, 11)
    out = capsys.readouterr().out
    assert "BY COMPOUND" in out and "not in any row" in out


# ------------------------------------------------ critic pass 1: what survived

def test_strategy_takes_no_comparison_from_a_session_with_one_compound():
    """M7: a group holding only the reference must not become `{ref: 0.0}`."""
    laps = run(1, "RH", [100_000] * 4) + run(1, "RM", [99_000] * 2, start=6)
    assert comparable_groups(laps, "RH") == {}
    assert comparable_pace(laps, "RH") == {}


def test_strategy_keeps_the_first_widest_session_on_a_tie():
    """M6: `>` not `>=` - two sessions each comparing two compounds, the first
    met wins."""
    laps = (run(1, "RH", [100_000] * 4) + run(1, "RM", [99_000] * 4, start=6)
            + run(2, "RH", [100_000] * 4) + run(2, "RM", [98_000] * 4, start=6))
    assert comparable_pace(laps, "RH")["RM"]["deltaS"] == pytest.approx(-1.0)


def test_an_out_lap_without_sectors_still_ages_the_run():
    """M2: filtering to the sector model before `split_runs` counts age would
    make lap 6 - the fifth of the run - the fourth."""
    laps = run(1, "RH", [100_000, 100_000, 100_000, 100_000, 90_000])
    laps[0] = lap(1, 120_000, fuel=100.0, model=None, sectors=(None, None, None),
                  is_out_lap=True)
    laps += run(2, "RM", [99_000] * 4)
    pace = compound_pace(laps, sitting_of={1: "a", 2: "a"})
    gap = next(g for g in pace.gaps if g.timing == "lap")
    assert gap.reference_n == 4                   # the 90 s lap 6 is not in


def test_the_floor_needs_the_minimum_on_both_sessions_and_takes_the_widest():
    """M3/M4/M5: an under-sized session is not a floor even when its move is
    the biggest; of two qualifying moves the wider is the floor; a gap exactly
    on the floor is inside it."""
    laps = (run(1, "RH", [102_000] * 4) + run(2, "RM", [101_000] * 4)
            + run(3, "RH", [104_000] * 2)          # moved 2.0 s, too few laps
            + run(4, "RM", [101_600] * 4)          # RM moved 0.6 s
            + run(5, "RH", [102_300] * 4))         # RH moved 0.3 s
    names = dict.fromkeys(range(1, 6), "a")
    pace = compound_pace(laps, sitting_of=names)
    gap = next(g for g in pace.gaps if g.timing == "lap")
    assert gap.floor_s == pytest.approx(0.6)
    assert replace_gap(gap, delta_s=-0.6).inside_floor is True
    assert replace_gap(gap, delta_s=-0.61).inside_floor is False


def replace_gap(gap, **kw):
    from dataclasses import replace

    return replace(gap, **kw)


def test_the_line_says_when_the_lap_gap_is_inside_the_floor():
    """M20."""
    laps = (run(1, "RH", [102_000] * 4) + run(2, "RM", [101_800] * 4)
            + run(3, "RM", [101_000] * 4))
    pace = compound_pace(laps, sitting_of=dict.fromkeys((1, 2, 3), "a"))
    line = sitting_line(pace.gaps, "RM", "a")
    assert "the lap gap is inside that" in line
    assert "the same tyre's lap moved 0.80 s between sessions" in line


def test_the_reference_is_the_hardest_and_does_not_change_with_counts():
    assert reference_by_hardness({"RS", "RM", "RH"}) == "RH"
    assert reference_by_hardness({"RS", "RM"}) == "RM"
    assert reference_by_hardness(set()) is None
    few_rh = (run(1, "RH", [102_000] * 3) + run(2, "RM", [101_000] * 9))
    pace = compound_pace(few_rh, sitting_of={1: "a", 2: "a"})
    assert {g.reference for g in pace.gaps} == {"RH"}


def test_a_sitting_without_the_reference_is_said_not_dropped():
    """Critic major 4."""
    laps = (run(1, "RH", [102_000] * 4) + run(2, "RM", [101_000] * 4)
            + run(3, "RM", [101_000] * 4) + run(4, "RS", [100_000] * 4))
    pace = compound_pace(laps, sitting_of={1: "a", 2: "a", 3: "b", 4: "b"})
    assert {g.sitting for g in pace.gaps} == {"a"}
    assert pace.refusals == (f"1.71, {MODEL}, b: no RH run to measure RM, RS against",)


def test_a_compound_without_a_gap_beside_one_that_has_one_is_said():
    """Critic pass 2, major 2: too few laps, or outside the fuel band."""
    laps = (run(1, "RH", [102_000] * 4) + run(2, "RM", [101_000] * 4)
            + run(3, "RS", [100_000] * 2)
            + run(4, "IM", [105_000] * 4, fuel_offset=40))
    pace = compound_pace(laps, sitting_of=dict.fromkeys((1, 2, 3, 4), "a"))
    assert {g.compound for g in pace.gaps if g.timing == "lap"} == {"RM"}
    need = ("it needs 3+ laps on it and on RH within the first 4 laps of a run, "
            "inside a 15 L fuel band of the RH laps")
    # Exactly these: a compound named here is not ALSO "never shared a
    # sitting" (critic pass 4, Q6).
    assert pace.refusals == (f"1.71, {MODEL}, a: no gap for IM - {need}",
                             f"1.71, {MODEL}, a: no gap for RS - {need}")


def test_uncatalogued_codes_are_refused_by_name():
    laps = run(1, "X1", [100_000] * 4) + run(2, "X2", [99_000] * 4)
    pace = compound_pace(laps, sitting_of={1: "a", 2: "a"})
    assert pace.gaps == ()
    assert pace.refusals == (f"1.71, {MODEL}: none of X1, X2 is a compound in "
                             f"GT7's catalogue, so there is nothing to measure against",)
    assert "None" not in pace.refusals[0]


def test_bests_and_references_do_not_cross_versions_or_lines():
    """M8/M9: each version and set of lines picks its own reference and bests."""
    laps = (run(1, "RS", [100_000] * 4) + run(2, "RM", [101_000] * 4)
            + run(3, "RH", [95_000] * 4, version="1.70")
            + run(4, "RH", [96_000] * 4, model="other:lines"))
    pace = compound_pace(laps, sitting_of=dict.fromkeys((1, 2, 3, 4), "a"))
    main = [b for b in pace.bests if b.game_version == "1.71" and b.sector_model == MODEL]
    assert {b.compound for b in main} == {"RS", "RM"}
    gaps = [g for g in pace.gaps if g.timing == "lap"]
    assert {(g.reference, g.compound) for g in gaps} == {("RM", "RS")}
    assert all(g.game_version == "1.71" and g.sector_model == MODEL for g in pace.gaps)


def test_a_zero_lap_time_is_not_a_best():
    """M10."""
    assert not may_set_a_best(lap(1, 0, sectors=(30_000, 30_000, 30_000)))


def test_the_counts_and_the_one_compound_refusal():
    """M14/M15: untagged counts COUNTED laps only."""
    laps = (run(1, "RH", [102_000] * 4) + [lap(9, 90_000, code=None)]
            + [lap(10, 120_000, code=None, is_out_lap=True)])
    pace = compound_pace(laps)
    assert pace.untagged == 1
    assert pace.refusals == (f"1.71, {MODEL}: 1 compound with full laps - nothing to compare",)


def test_two_sittings_inside_their_spread_are_said_to_agree():
    """M19: the widest spread decides - here only one side is wide enough."""
    laps = (run(1, "RH", [101_000, 102_000, 103_000, 104_000])     # IQR 1.5 s
            + run(2, "RM", [101_000] * 4)
            + run(3, "RH", [102_500] * 4)
            + run(4, "RM", [100_500] * 4))
    pace = compound_pace(laps, sitting_of={1: "a", 2: "a", 3: "b", 4: "b"})
    (line,) = pace.across_sittings()
    assert "0.50 s apart" in line and "inside the sittings' own spread" in line


def test_both_no_event_paths_empty_the_plate():
    """M16/M17 - rule 11: nothing of the last event stays on the plate."""
    for name in ("switch_event", "_switch_to_round"):
        calls = _calls(_method(name), "_refresh_compound_pace")
        assert calls and any(isinstance(call.args[0], ast.Constant)
                             and call.args[0].value is None for call in calls), name


def test_a_drawing_failure_is_contained():
    from pitcrew.controller import PitCrewController

    def boom(pace):
        raise RuntimeError("paint")

    stub = SimpleNamespace(practice=SimpleNamespace(show_compound_pace=boom),
                           store=SimpleNamespace())
    PitCrewController._refresh_compound_pace(stub, None)


def test_strategy_names_the_weaker_practice_figure_it_does_not_use():
    from pitcrew.strategy.evidence import comparable_pace_gap

    said = comparable_pace_gap(_sweep(), "RH", "RM")
    assert "By tyre panel" in said and "not used here" in said


def test_the_per_timing_detail_carries_no_floor_wording_of_its_own():
    """Critic pass 2, blocker: `describe` printed the retired sentence."""
    laps = run(1, "RH", [102_000] * 4) + run(2, "RM", [101_000] * 4)
    pace = compound_pace(laps, sitting_of={1: "a", 2: "a"})
    for gap in pace.gaps:
        said = gap.describe()
        assert "ran twice" not in said and "floor" not in said
        assert said.startswith(f"RM -1.00 s on RH over the {gap.timing}") or gap.timing != "lap"
    line = sitting_line(pace.gaps, "RM", "a")
    assert "Sector gaps do not add up to the lap gap." in line       # N14
    assert "no tyre has 3+ comparable laps in two of these sessions" in line


def test_a_practice_mode_change_refreshes_the_plate():
    """N8."""
    assert _calls(_method("_on_practice_mode"), "_refresh_compound_pace")


def test_the_strategy_note_says_may_on_both_branches():
    from pitcrew.strategy.evidence import PRACTICE_PANEL_NOTE, comparable_pace_gap

    assert "may show" in PRACTICE_PANEL_NOTE
    assert comparable_pace_gap(_sweep(), "RH", "RH").endswith(PRACTICE_PANEL_NOTE)


def test_a_compound_only_ever_run_in_a_sitting_of_its_own_is_named():
    """Critic pass 3 (Spa's RS): a best with no gap and no word is not allowed."""
    laps = (run(1, "RH", [102_000] * 4) + run(2, "RM", [101_000] * 4)
            + run(3, "RS", [100_000] * 4))
    pace = compound_pace(laps, sitting_of={1: "a", 2: "a", 3: "b"})
    assert {b.compound for b in pace.bests} == {"RH", "RM", "RS"}
    assert {g.compound for g in pace.gaps} == {"RM"}
    assert pace.refusals == (
        f"1.71, {MODEL}: no gap for RS - it never shared a sitting with RH (a "
        f"sitting ends when the next practice session starts more than "
        f"{SITTING_GAP_H:g} h after the last one ended)",)


def test_a_named_reference_with_no_laps_says_so():
    """Critic pass 4, note: not "never shared a sitting with RX" for every tyre."""
    laps = run(1, "RH", [102_000] * 4) + run(2, "RM", [101_000] * 4)
    pace = compound_pace(laps, "RS", sitting_of={1: "a", 2: "a"})
    assert pace.gaps == ()
    assert pace.refusals == (f"1.71, {MODEL}: no RS laps with all three sectors "
                             f"on file to measure against",)


def test_the_tool_prints_sectors_as_seconds_like_the_plate(capsys):
    """Critic pass 3/4, R1: a 64 s sector as 1:04.126 ran into its neighbour."""
    from tools.compound_pace import render

    laps = [lap(2, 142_059, code="RS", sectors=(40_261, 64_126, 37_672))]
    render(compound_pace(laps))
    out = capsys.readouterr().out
    assert "   40.261   64.126   37.672" in out and "1:04.126" not in out
