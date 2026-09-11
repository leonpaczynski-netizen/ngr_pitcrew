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


def test_a_stop_filed_on_two_rows_is_one_stop_and_closes_on_the_first():
    """Critic 6, passes 1 and 2: Fuji's in-lap is lap 5; lap 6 carries the
    pit flag, the out-lap flag and the fill. "[5, 1, 14]" invented a stop and
    "[6, 14]" boxed him a lap late - he boxed on lap 5."""
    fuji = [{"lap_num": n, "is_pit_lap": n in (5, 6), "is_out_lap": n == 6}
            for n in range(1, 21)]
    assert stint_lengths(fuji) == [5, 15]
    daytona = [{"lap_num": n, "is_pit_lap": n == 12, "is_out_lap": n == 13}
               for n in range(1, 21)]
    assert stint_lengths(daytona) == [12, 8]


def test_the_radio_is_filtered_to_the_sessions_asked_for():
    """Critic 6: `--sessions 143` printed four exchanges from 118, 119, 125."""
    from tools.debrief import radio

    class Store:
        def __init__(self):
            self.asked = []

        def _query(self, sql, params):
            self.asked.append((sql, params))
            return []

    store = Store()
    radio(store, 10, [143])
    sql, params = store.asked[-1]
    assert "radio.session_id IN (?)" in sql and params == (10, 143)
    radio(store, 10)
    assert store.asked[-1][1] == (10,)


def test_the_small_helpers_say_what_they_should():
    from types import SimpleNamespace

    from pitcrew.race.expectations import WEAR_CONTRADICTION
    from tools.debrief import race_length, session_label, strip_fixed_wear

    assert session_label("race", 1) == "race (rehearsal)"
    assert session_label("race", 0) == "race"
    assert session_label("practice", 1) == "practice"
    line = f"Wear stayed the plan's assumption; {WEAR_CONTRADICTION}."
    assert strip_fixed_wear(line) == ("Wear stayed the plan's assumption.", True)
    assert strip_fixed_wear("Planned on 7.7 L/lap.") == ("Planned on 7.7 L/lap.", False)
    assert race_length(SimpleNamespace(race_laps=20, race_minutes=None)) == "20 laps"
    assert race_length(SimpleNamespace(race_laps=None, race_minutes=30.0)) == "30 minutes"
    assert race_length(SimpleNamespace(race_laps=None, race_minutes=None)) == "not on the event"


def test_a_ledger_header_with_an_empty_side_matches_nothing(tmp_path):
    _ledger(tmp_path, "blank.md", " × ", [])
    event = {"car_name": "Lamborghini Huracán GT3 '15",
             "track": "Daytona International Speedway", "layout": "Road Course"}
    assert ledger_for(event, tmp_path) == []


def test_the_trend_line_says_what_it_does_not_know():
    from pitcrew.analysis.driver_trends import SessionTrend
    from tools.debrief import trend_line

    blank = SessionTrend(session_id=113, kind="practice", judged_laps=0,
                         incidents=None, lap_one_cost_s=None,
                         lap_one_reference_n=0, consistency_sd_s=None,
                         consistency_n=1)
    said = trend_line(blank, "practice")
    assert "incidents —" in said and "lap one —" in said
    assert "consistency — (n=1)" in said
    raced = SessionTrend(session_id=143, kind="race", judged_laps=15,
                         incidents=2, lap_one_cost_s=11.7,
                         lap_one_reference_n=12, consistency_sd_s=1.6,
                         consistency_n=13, start_type="Standing")
    said = trend_line(raced, "race")
    assert "2 in 15 judged laps (13%)" in said
    assert "+11.7 s vs lap 5 on (n=12; start: Standing)" in said


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


def test_a_stop_compared_with_itself_says_so():
    """Critic 6: the flag stored this stop's own total as the event's
    measured figure, and the line reported the agreement."""
    from tools.debrief import pit_loss_line

    said = pit_loss_line(_stop(fuel=False), 75.6, "measured")
    assert "measured at this stop, a ceiling" in said
    assert "compares it with itself" in said


def test_a_stored_total_with_the_fill_inside_is_called_what_it_is():
    """Critic 6, pass 2: Daytona's 72.28 s is the s143 stop's TOTAL, with the
    49 L fill inside, stored as the ex-fuel figure - "measured, compares it
    with itself" told him nothing about which number to believe."""
    from pitcrew.race.pit_loss import PitLoss
    from tools.debrief import pit_loss_line

    daytona = PitLoss(total_s=72.28, ex_fuel_s=23.19, in_lap_ms=124_471,
                      out_lap_ms=156_160, clean_lap_ms=104_200.0, clean_laps=15,
                      fuel_added_l=49.09, refuel_rate_lps=1.0, stop_lap=12)
    said = pit_loss_line(daytona, 72.28, "measured", this_session=143)
    assert "this stop's total with its 49.1 L fill inside" in said
    assert "about 49 s high" in said and "driver's yes" in said
    # The earlier race at the same circuit is scored against the same
    # figure - and is told where it came from.
    earlier = _stop(fuel=False)
    said = pit_loss_line(earlier, 72.28, "measured", others=[(143, daytona)],
                         this_session=127)
    assert "the session 143 stop's total with its 49.1 L fill inside" in said


def test_declared_says_it_may_be_the_default_only_when_it_could_be():
    from tools.debrief import pit_loss_line

    said = pit_loss_line(_stop(fuel=True), 20.0, "declared")
    assert "the app's 20 s default" in said and "cannot tell which" in said
    said = pit_loss_line(_stop(fuel=True), 19.0, "declared")
    assert "default" not in said and "(declared)" in said


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
