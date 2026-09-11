"""`tools/debrief.py` runs the whole list (plan row 2.5) - its pure parts.

The sections that read the store are thin wrappers over expressions tested
where they live (`audit_line_from_laps`, `pit_loss.measure`, `session_trend`,
`radio_review.report`); what is new here is the matching, the ledger read and
the tallies, and those are pinned.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from pitcrew.race.call_outcome import ACTED, CANNOT_TELL, NOT_ACTED  # noqa: E402
from tools.debrief import (call_tally, ledger_for, open_rows,  # noqa: E402
                           stint_lengths)

HEADER = ("date,session_ids,key,direction,delta_pct_range,instrument,"
          "measured_floor,control,prediction,falsifier,outcome,source,"
          "car_state_rev")


def _ledger(directory: Path, name: str, pair: str, rows: list[str]) -> Path:
    path = directory / name
    body = "\n".join([HEADER, *rows])
    path.write_text(f"# Experiment ledger — {pair}\n\nprose\n\n```csv\n{body}\n```\n",
                    encoding="utf-8")
    return path


def test_the_ledger_is_found_by_its_own_words_inside_the_events(tmp_path):
    """The car-state file's names are not the event's: "Huracán GT3 '15"
    inside "Lamborghini Huracán GT3 '15", "Daytona Road Course" inside a
    track and a layout."""
    mine = _ledger(tmp_path, "huracan-daytona.md",
                   "Huracán GT3 '15 × Daytona Road Course", [])
    _ledger(tmp_path, "huracan-mount-panorama.md",
            "Huracán GT3 '15 × Mount Panorama", [])
    _ledger(tmp_path, "rsr-daytona.md", "Porsche 911 RSR '17 × Daytona Road Course", [])
    (tmp_path / "README.md").write_text("# The experiment ledger\n", encoding="utf-8")
    event = {"car_name": "Lamborghini Huracán GT3 '15",
             "track": "Daytona International Speedway", "layout": "Road Course"}
    assert ledger_for(event, tmp_path) == [mine]


def test_another_layout_of_the_same_circuit_is_not_this_ledger(tmp_path):
    _ledger(tmp_path, "huracan-daytona.md",
            "Huracán GT3 '15 × Daytona Road Course", [])
    oval = {"car_name": "Lamborghini Huracán GT3 '15",
            "track": "Daytona International Speedway", "layout": "Tri-Oval"}
    assert ledger_for(oval, tmp_path) == []


def test_only_open_rows_come_back_and_a_quoted_comma_stays_in_its_cell(tmp_path):
    path = _ledger(tmp_path, "x.md", "Car × Track", [
        '2026-09-01,s1,arb_r,stiffer,+11.1,lap,n/a,s0,"faster, at S2",slower,open,src,A',
        "2026-09-02,s2,df_f,up,+20.0,lap,n/a,s1,faster,slower,confirmed,src,A",
        "2026-09-03,s3,bb,rearward,+10.0,lap,n/a,s2,stable,unstable,unresolvable,src,A",
    ])
    rows = open_rows(path)
    assert [row["key"] for row in rows] == ["arb_r"]
    assert rows[0]["prediction"] == "faster, at S2"


def test_a_pit_lap_closes_the_stint_it_ends():
    rows = [{"lap_num": n, "is_pit_lap": n in (10, 18)} for n in range(1, 26)]
    assert stint_lengths(rows) == [10, 8, 7]
    assert stint_lengths([]) == []


def _stop(*, fuel):
    from pitcrew.race.pit_loss import PitLoss

    return PitLoss(total_s=75.6, ex_fuel_s=40.6 if fuel else 75.6,
                   in_lap_ms=123_200, out_lap_ms=162_100, clean_lap_ms=104_800.0,
                   clean_laps=15, fuel_added_l=70.0 if fuel else None,
                   refuel_rate_lps=2.0 if fuel else None, stop_lap=12)


def test_a_measured_figure_is_never_called_declared():
    """Rule 13, off the Daytona smoke run: "72.3 s against 72.28 s declared
    (measured)" - one word saying typed, the source saying measured."""
    from tools.debrief import pit_loss_line

    said = pit_loss_line(_stop(fuel=True), 72.28, "measured")
    assert "declared" not in said
    assert "the event's 72.28 s (measured)" in said
    assert "40.6 s ex-fuel" in said
    assert "no source" in pit_loss_line(_stop(fuel=True), 20.0, None)


def test_a_stop_with_no_fill_is_a_ceiling_not_an_ex_fuel_figure():
    from tools.debrief import pit_loss_line

    said = pit_loss_line(_stop(fuel=False), 72.28, "measured")
    assert "ex-fuel figure" in said and "ceiling" in said
    assert "75.6 s in all" in said
    assert "75.6 s ex-fuel" not in said


def test_a_missing_verdict_is_counted_and_never_read_as_acted():
    revisions = [
        {"lap_num": 8, "reason": "Box in 2 laps.", "verdict": ACTED, "plan": {}},
        {"lap_num": 10, "reason": "Box this lap.", "verdict": NOT_ACTED,
         "verdict_detail": "did not pit on lap 10", "plan": {"kind": "box-now"}},
        {"lap_num": 11, "reason": "Push now.", "verdict": CANNOT_TELL, "plan": {}},
        {"lap_num": 12, "reason": "Old call.", "verdict": None, "plan": {}},
        {"lap_num": 13, "reason": "3 laps to the stop.", "verdict": None,
         "plan": {"informational": True}},
    ]
    tally, ignored = call_tally(revisions)
    assert tally[ACTED] == 1 and tally[NOT_ACTED] == 1 and tally[CANNOT_TELL] == 1
    assert tally["no verdict on file"] == 1
    assert tally["said, not an instruction"] == 1
    assert [r["lap_num"] for r in ignored] == [10]
