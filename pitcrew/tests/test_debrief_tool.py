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


def _daytona_stop():
    from pitcrew.race.pit_loss import PitLoss

    return PitLoss(total_s=72.28, ex_fuel_s=23.19, in_lap_ms=124_471,
                   out_lap_ms=156_160, clean_lap_ms=104_200.0, clean_laps=15,
                   fuel_added_l=49.09, refuel_rate_lps=1.0, stop_lap=12)


def test_a_figure_that_is_this_stops_ex_fuel_says_so():
    """The path every correctly stored figure will take (critic 6, P4)."""
    from tools.debrief import pit_loss_line

    said = pit_loss_line(_daytona_stop(), 23.19, "measured", this_session=143)
    assert "measured at this stop, ex-fuel, so this compares it with itself" in said


def test_another_sessions_stop_is_never_this_one():
    """Critic 6, P8: "compares it with itself" is for this stop only."""
    from tools.debrief import pit_loss_line

    said = pit_loss_line(_stop(fuel=True), 23.19, "measured",
                         others=[(143, _daytona_stop())], this_session=127)
    assert "measured at the session 143 stop, ex-fuel" in said
    assert "itself" not in said


def test_a_filter_does_not_hide_where_the_figure_came_from(capsys):
    """Critic 6, pass 3 (MAJOR): `--sessions 127` dropped the s143 run, and
    the 72 s figure - its total, fill inside - was called "measured"."""
    from tools.debrief import against_the_plan

    def _rows(pit_ms, out_ms, fill):
        rows = [{"lap_num": n, "lap_time_ms": 104_000, "is_pit_lap": False,
                 "is_out_lap": False} for n in range(2, 12)]
        rows.append({"lap_num": 12, "lap_time_ms": pit_ms, "is_pit_lap": True,
                     "is_out_lap": False, "fuel_added_l": 0.0 if fill else None})
        rows.append({"lap_num": 13, "lap_time_ms": out_ms, "is_pit_lap": False,
                     "is_out_lap": True, "fuel_added_l": fill})
        return rows

    laps = {143: _rows(124_471, 156_160, 49.09), 127: _rows(123_200, 162_100, None)}

    class Store:
        def list_strategies(self, event_id):
            return [{"id": 1, "label": "plan",
                     "plan": {"stints": [{"laps": 12}, {"laps": 8, "tyres": True}]}}]

        def list_event_laps(self, event_id, kind):
            return []

        def list_laps(self, session_id):
            return laps[session_id]

    event = {"id": 10, "pit_loss_secs": 72.63, "pit_loss_source": "measured",
             "refuel_rate_lps": 1.0, "race_type": "laps", "race_laps": 20,
             "race_minutes": None, "car_name": "Car",
             "track": "Daytona International Speedway", "layout": "Road Course"}
    every = [{"id": 14, "strategy_id": 1, "session_id": 127},
             {"id": 17, "strategy_id": 1, "session_id": 143}]
    against_the_plan(Store(), event, every[:1], all_runs=every)
    out = capsys.readouterr().out
    assert "the session 143 stop's total with its 49.1 L fill inside" in out
    assert "run 17" not in out, "only the filtered run is printed"


def test_main_scores_a_filtered_run_against_every_run(monkeypatch):
    """Critic 6, pass 4 (minor): the pass-3 fix rides on one line in `main`
    that nothing ran - passing no `all_runs`, or the filtered runs as
    `all_runs`, brought the defect back silently."""
    import tools.debrief as debrief

    every = [{"id": 14, "session_id": 127}, {"id": 17, "session_id": 143}]
    got = {}

    class Store:
        def __init__(self, *args):
            pass

        def get_event(self, event_id):
            return {"id": event_id, "start_type": None}

        def list_sessions(self, event_id):
            return []

        def list_race_runs(self, event_id):
            return list(every)

        def close(self):
            pass

    def against_the_plan(store, event, runs, all_runs=None):
        got["runs"], got["all_runs"] = runs, all_runs

    monkeypatch.setattr(debrief, "Store", Store)
    monkeypatch.setattr(debrief, "against_the_plan", against_the_plan)
    for name in ("driver_first", "open_predictions", "render", "change_landed",
                 "how_driven", "by_compound", "driver_variable", "calls_against_outcome",
                 "radio", "close", "_head"):
        monkeypatch.setattr(debrief, name, lambda *a, **k: None)
    monkeypatch.setattr(debrief, "from_store", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["debrief.py", "10", "--sessions", "127"])
    assert debrief.main() == 0
    assert got["runs"] == every[:1]
    assert got["all_runs"] == every


def test_his_words_go_on_his_row():
    from tools.debrief import split_notes

    under, below = split_notes([
        'lap 2 struck by hand, in his words: "crash" - not in the incident count',
        "no lap-one cost: a practice lap one is driven out of the pits"])
    assert under == ['lap 2 struck by hand, in his words: "crash" - not in the incident count']
    assert below == ["no lap-one cost: a practice lap one is driven out of the pits"]


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


def _contact(**kw) -> dict:
    """A radar contact, as `record_traffic` takes them."""
    base = dict(lap_id=None, lap_num=3, video_s=120.0, side="behind",
                ribbon_px=7.0, near_m=23.8, rival_position=6,
                source="replay-radar")
    base.update(kw)
    return base

# ------------------------------------------- who he raced, read off the board

def _named_race(store):
    """A race session with board readings on file."""
    event = store.create_event(name="e", track="Fuji Speedway",
                               layout="Full Course")
    session = store.start_session(event, "race")
    rows = []
    for lap in range(1, 12):
        rows.append({"lap_num": lap, "video_s": float(lap) * 10, "side": "ahead",
                     "driver": "CruisingChaos", "source": "replay-board"})
        rows.append({"lap_num": lap, "video_s": float(lap) * 10 + 2,
                     "side": "behind", "driver": "K.Graebs",
                     "source": "replay-board"})
    store.record_board_sightings(session, rows)
    return event, session


def test_the_debrief_names_who_he_raced(store, capsys):
    """**The step that was missing, not the data.** `analysis/rivals` has had
    `tendencies` for weeks and the wiring audit listed the module under *no
    production code imports* — a board pass filed its readings and they
    stopped there."""
    from tools.debrief import who_he_raced

    _event, session = _named_race(store)
    who_he_raced(store, [dict(store.get_session(session))])
    printed = capsys.readouterr().out
    assert "WHO HE RACED" in printed
    assert "CruisingChaos" in printed and "K.Graebs" in printed
    assert "1094" not in printed
    assert "22 board reading(s)" in printed


def test_a_race_with_nothing_on_file_says_so_rather_than_nothing(store, capsys):
    """Silence would read as "he raced nobody", which is a different claim
    from "neither instrument was read"."""
    from tools.debrief import who_he_raced

    event = store.create_event(name="e", track="Fuji Speedway",
                               layout="Full Course")
    session = store.start_session(event, "race")
    who_he_raced(store, [dict(store.get_session(session))])
    printed = capsys.readouterr().out
    assert "nothing on file" in printed


def test_a_race_named_from_the_radar_still_reports_its_rivals(store, capsys):
    """**It printed "no board pass" and threw the answer away.** Sessions 88
    and 112 carry 334 and 499 named `traffic` rows and no board rows at all,
    so the only sessions named the old way reported nothing — the same mistake
    as the chain that was never wired, one layer further out."""
    from tools.debrief import who_he_raced

    event = store.create_event(name="e", track="Fuji Speedway",
                               layout="Full Course")
    session = store.start_session(event, "race")
    store.record_traffic(session, [
        _contact(lap_num=lap, side="behind") for lap in range(1, 9)])
    for row in store.list_traffic(session):
        store.name_traffic(row["id"], "TommyTbone")
    who_he_raced(store, [dict(store.get_session(session))])
    printed = capsys.readouterr().out
    assert "TommyTbone" in printed, "the radar's answer was suppressed"
    assert "radar" in printed, "and it must say which instrument said so"


def test_an_all_unreadable_board_pass_falls_through_to_the_radar(store, capsys):
    """Rows with a NULL driver are the board saying it could not be read.

    Counting them as "the board answered" reported *nobody was beside him*
    over a radar pass that had named eight laps — CLAUDE.md rule 3, with the
    two answers collapsed into one.
    """
    from tools.debrief import who_he_raced

    event = store.create_event(name="e", track="Fuji Speedway",
                               layout="Full Course")
    session = store.start_session(event, "race")
    store.record_traffic(session, [
        _contact(lap_num=lap, side="behind") for lap in range(1, 9)])
    for row in store.list_traffic(session):
        store.name_traffic(row["id"], "PUNISHED")
    store.record_board_sightings(session, [
        {"lap_num": lap, "video_s": float(lap), "side": "ahead",
         "driver": None, "source": "replay-board"} for lap in (1, 2, 3)])
    who_he_raced(store, [dict(store.get_session(session))])
    printed = capsys.readouterr().out
    assert "PUNISHED" in printed, (
        "an unreadable board pass reported 'nobody' over eight named laps")


def test_an_unreadable_cluster_is_counted_in_the_debrief(store, capsys):
    """Filed with no driver, and said out loud — the operator marked it
    unknowable and the debrief must not quietly drop it."""
    from tools.debrief import who_he_raced

    event = store.create_event(name="e", track="Fuji Speedway",
                               layout="Full Course")
    session = store.start_session(event, "race")
    store.record_board_sightings(session, [
        {"lap_num": 1, "video_s": 4.0, "side": "ahead", "driver": None,
         "source": "replay-board"}])
    who_he_raced(store, [dict(store.get_session(session))])
    printed = capsys.readouterr().out
    assert "nobody could read" in printed


def test_one_overtake_is_not_a_tendency(store, capsys):
    """Below the floor the debrief says why it is quiet, rather than listing
    a driver who was alongside for a corner."""
    from tools.debrief import who_he_raced

    event = store.create_event(name="e", track="Fuji Speedway",
                               layout="Full Course")
    session = store.start_session(event, "race")
    store.record_board_sightings(session, [
        {"lap_num": 1, "video_s": 4.0, "side": "ahead", "driver": "Rocky",
         "source": "replay-board"}])
    who_he_raced(store, [dict(store.get_session(session))])
    printed = capsys.readouterr().out
    assert "not a tendency" in printed
    assert "Rocky" not in printed


def test_main_asks_who_he_raced_about_the_sessions_it_found(monkeypatch):
    """**The wiring, not the function.** The existing `main` test stubs
    `list_sessions` to `[]`, so the call this whole change exists for was
    unpinned — removing it from `main()` passed everything."""
    import tools.debrief as debrief

    sessions = [{"id": 143, "kind": "race", "rehearsal": 0,
                 "started_at": "2026-09-07T20:17:57"}]
    asked = {}

    class Store:
        def __init__(self, *args):
            pass

        def get_event(self, event_id):
            return {"id": event_id, "start_type": None}

        def list_sessions(self, event_id):
            return list(sessions)

        def list_race_runs(self, event_id):
            return []

        def close(self):
            pass

    monkeypatch.setattr(debrief, "Store", Store)
    monkeypatch.setattr(debrief, "who_he_raced",
                        lambda store, given: asked.setdefault("given", given))
    for name in ("driver_first", "open_predictions", "render", "change_landed",
                 "how_driven", "by_compound", "driver_variable", "calls_against_outcome",
                 "against_the_plan", "radio", "close", "_head"):
        monkeypatch.setattr(debrief, name, lambda *a, **k: None)
    monkeypatch.setattr(debrief, "from_store", lambda *a, **k: None)
    monkeypatch.setattr(sys, "argv", ["debrief.py", "10"])
    assert debrief.main() == 0
    assert [s["id"] for s in asked.get("given", [])] == [143], (
        "main() did not ask who he raced about the sessions it found")


def test_the_debrief_says_which_instrument_named_them(store, capsys):
    """A board line and a radar line are different claims (rule 13): the board
    reads the running order whatever the gap, the radar sees about a second
    each way and only while that page is up."""
    from tools.debrief import who_he_raced

    _event, session = _named_race(store)
    who_he_raced(store, [dict(store.get_session(session))])
    printed = capsys.readouterr().out
    assert "[board]" in printed
    assert "[radar]" not in printed
