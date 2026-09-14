"""Print the debrief for an event - the whole list, in the protocol's order.

    python tools/debrief.py 10
    python tools/debrief.py 10 --report his-report.md
    python tools/debrief.py 10 --before 129 130 --after 132
    python tools/debrief.py 10 --sessions 113 114 115
    python tools/debrief.py 10 --walk

Plan row 2.5. The order is the protocol's (`references/modes.md`, *debrief*): **his
account first, free and unprompted, before he is shown any of this** -
because numbers shown first lead him and his account is primary evidence
(CLAUDE.md rule 1). It asks him nothing: the questions come after the
telemetry is read, four at most (the spine's steps 3 and 4). The row's
per-corner grid is open for the driver - see `references/modes.md`. Then the open predictions the ledger holds for this car at
this circuit; the practice session; where a named change landed; how it was
driven; the bests and gaps by compound (row 5.22); the driver as a variable (row 2.11 - here and nowhere else); George's
calls against what followed them; the race against its plan; the radio. Every
section says what it could not see rather than going quiet.

Reads only - apart from the schema upgrade every `Store()` makes when it opens
a file (`references/mechanic.md`). After it the debrief closes each open
prediction in `brain/ledger/` and commits `brain/`: one commit per debrief.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import io
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import median

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# Windows consoles default to cp1252 and this prints em dashes and arrows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pitcrew.analysis.debrief import (  # noqa: E402
    CLEAN_OFF_TRACK_S,
    MIN_GEAR_ARM,
    from_store,
)
from pitcrew.store.db import Store  # noqa: E402

RULE = "-" * 72
LEDGER_DIR = REPO / "brain" / "ledger"


def _ms(value) -> str:
    if value is None:
        return "—"
    return f"{value / 1000.0:.3f} s"


def _head(text: str) -> None:
    print(f"\n{text}\n{RULE}")


def _tool(name: str):
    """A sibling tool, imported by path - its functions, not its `main`."""
    spec = importlib.util.spec_from_file_location(
        f"_debrief_{name}", REPO / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ------------------------------------------------------------ his report first

def driver_first(report_path) -> None:
    _head("HIS REPORT FIRST — before he is shown anything below")
    if report_path is None:
        print("  none given. Take his account now - free, unprompted, in his "
              "words. It is")
        print("  primary evidence and everything below corroborates it "
              "(CLAUDE.md rule 1).")
        print("  It asks him nothing: any question comes after the telemetry, "
              "four at most.")
        print("  `--report FILE` prints it here.")
        return
    for line in Path(report_path).read_text(encoding="utf-8").splitlines():
        print(f"  {line}")


# ------------------------------------------------------- the open predictions

def _tokens(text) -> set[str]:
    from pitcrew.store.tyres import slugify

    return {part for part in slugify(text or "").split("-") if part}


def ledger_for(event, directory: Path = LEDGER_DIR) -> list[Path]:
    """The ledger files for this car at this circuit.

    A ledger's first line names its pair as `... — <car> × <circuit>`, in the
    words the car-state file uses, which are not the event's: "Huracán GT3
    '15" against "Lamborghini Huracán GT3 '15", "Daytona Road Course" against
    a track and a layout. So every word of the ledger's car must be in the
    event's car, and every word of its circuit in the track and layout -
    through `slugify`, the one slug rule.
    """
    car = _tokens(event.get("car_name"))
    circuit = _tokens(f"{event.get('track') or ''} {event.get('layout') or ''}")
    found = []
    for path in sorted(directory.glob("*.md")):
        lines = path.read_text(encoding="utf-8").splitlines()
        head = lines[0] if lines else ""
        if "—" not in head or "×" not in head:
            continue
        car_part, _, circuit_part = head.split("—", 1)[1].partition("×")
        wanted_car, wanted_circuit = _tokens(car_part), _tokens(circuit_part)
        if (wanted_car and wanted_circuit and wanted_car <= car
                and wanted_circuit <= circuit):
            found.append(path)
    return found


def open_rows(path: Path) -> list[dict]:
    """Every ledger row whose outcome is still `open`, from its csv blocks."""
    text = path.read_text(encoding="utf-8")
    rows = []
    for block in re.findall(r"```csv\n(.*?)```", text, re.S):
        rows.extend(row for row in csv.DictReader(io.StringIO(block))
                    if (row.get("outcome") or "").strip() == "open")
    return rows


def open_predictions(event, directory: Path = LEDGER_DIR) -> None:
    _head("OPEN PREDICTIONS — the loop closes here, before the data")
    paths = ledger_for(event, directory)
    if not paths:
        print(f"  no ledger in brain/ledger/ for {event.get('car_name')} at "
              f"{event.get('track')}, so nothing is open on file.")
        return
    for path in paths:
        rows = open_rows(path)
        print(f"  {path.name}: {len(rows)} open")
        for row in rows:
            print(f"    {row.get('date')}  {row.get('key')} — "
                  f"{row.get('direction')} ({row.get('delta_pct_range')})")
            print(f"      predicts:     {row.get('prediction')}")
            print(f"      falsified by: {row.get('falsifier')}")
    print("\n  Each is closed in its ledger row after this debrief: confirmed, "
          "refuted with\n  its direction, or unresolvable — which is not "
          "refuted.")


# ------------------------------------------------------ the practice session

def render(debrief) -> None:
    _head("SESSION")
    print(f"  {debrief.census.describe()}")

    pace, burn = debrief.pace, debrief.burn
    print(f"  pace     median {_ms(pace.median_ms)}   best {_ms(pace.best_ms)}"
          f"   sd {_ms(pace.sd_ms)}   (n={pace.n})")
    if burn.median_l is not None:
        spread = f"± {burn.sd_l:.2f}" if burn.sd_l is not None else "spread —"
        print(f"  fuel     {burn.median_l:.2f} L/lap {spread}   (n={burn.n})")
    else:
        print("  fuel     — no lap burned a measurable amount")

    _head("CONSISTENCY — where you are least repeatable")
    if not debrief.scatter:
        print("  no corner was reached on enough laps to say.")
    for row in debrief.scatter:
        sd = f"{row.sd_kph:5.1f}" if row.sd_kph is not None else "    —"
        cov = f"{row.cov_pct:5.2f}%" if row.cov_pct is not None else "     —"
        print(f"  {row.corner_id:<4} {row.corner_name:<12} "
              f"min {row.mean_kph:6.1f} km/h   sd {sd} km/h  {cov}"
              f"   carries {row.carry_m:5.0f} m   (n={row.n})")
    worst = debrief.least_repeatable
    if worst is not None and worst.sd_kph is not None:
        print(f"\n  → {worst.corner_name} is your least repeatable corner "
              f"({worst.sd_kph:.1f} km/h). It carries {worst.carry_m:.0f} m.")
        print("    This needs no reference lap and no teammate: do the same "
              "thing there twice.")

    _head("GEAR — the A/Bs you have already run")
    if not debrief.gears:
        print("  you took every corner in the same gear on every lap. "
              "Nothing to compare.")
    for split in debrief.gears:
        best = split.quickest
        print(f"  {split.corner_id:<4} {split.corner_name}")
        for arm in split.arms:
            mark = " <-" if best is not None and arm.gear == best.gear else "  "
            print(f"      G{arm.gear}  n={arm.n:<3} "
                  f"min {arm.mean_min_kph:6.1f} km/h   "
                  f"lap {_ms(arm.mean_lap_ms)}{mark}")
        if split.balanced:
            print(f"      balanced — both arms have {MIN_GEAR_ARM}+ laps. "
                  "Worth acting on.")
        else:
            print("      UNBALANCED — a hypothesis to test, not a finding.")
    if debrief.gears:
        print("\n  Apex gear is partly an EFFECT of entry speed: arrive slowly "
              "and you\n  end up a gear lower, so the gear did not cause the "
              "slow lap. To break\n  that, choose the gear deliberately — five "
              "laps each way, same intent.")

    _head("CORNERS THAT PREDICT THE LAP")
    spoken = debrief.spoken
    if not spoken:
        print("  none clears significance. See SILENCES.")
    for found in spoken:
        way = "quicker when faster" if found.r < 0 else "quicker when slower"
        print(f"  {found.corner_id:<4} {found.corner_name:<12} "
              f"r={found.r:+.2f}  p={found.p:.3f}  n={found.n}   {way} here")

    if debrief.video:
        _head("VIDEO — where to look")
        # Grouped by file. An event spans several sessions and each has its own
        # capture, so a flat list under one filename sends you to the right
        # timecode in the wrong recording.
        by_file: dict[str, list] = {}
        for cue in debrief.video:
            by_file.setdefault(cue.path, []).append(cue)
        for path, cues in by_file.items():
            print(f"  {Path(path).name}")
            for cue in cues[:6]:
                mins, secs = divmod(max(0.0, cue.second), 60)
                print(f"    lap {cue.lap_num:<3} {cue.corner_id}   "
                      f"{int(mins):02d}:{secs:05.2f}")
            if len(cues) > 6:
                print(f"    … and {len(cues) - 6} more")
        print("\n  Good to about a metre. The speed-integrated and "
              "position-measured axes\n  place a corner within half a metre of "
              "each other, and every lap above\n  has passed the teleport "
              "check. What moves is where you actually apexed.")

    _head("SILENCES — what I could not see")
    if not debrief.silences:
        print("  nothing was withheld.")
    for line in debrief.silences:
        print(f"  - {line}")
    for note in debrief.notes:
        print(f"\n  {note}")


# ---------------------------------------------------- where a change landed

def change_landed(store, before, after) -> None:
    _head("WHERE THE CHANGE LANDED — sectors, not the lap time")
    if not before or not after:
        print("  no change named. `--before SESSION... --after SESSION...` "
              "runs")
        print("  tools/where_the_change_landed.py's sector table here "
              "(add --bins there for distance).")
        return
    tool = _tool("where_the_change_landed")
    was, now = tool.laps_for(store, before), tool.laps_for(store, after)
    print(f"  before: sessions {before}, {len(was)} clean laps")
    print(f"  after : sessions {after}, {len(now)} clean laps")
    # Whose "clean": a count that differs from another file's is the finding
    # (`references/modes.md`, refine step 5 - a baseline counted by the tool's
    # definition), and it cannot be seen without the definition.
    print("  (clean by this tool's own test - counted, and no excursion, crawl "
          "or spin.\n   A different count elsewhere for the same laps is a "
          "finding, not a rounding.)")
    if len(was) < tool.MIN_LAPS_PER_SIDE or len(now) < tool.MIN_LAPS_PER_SIDE:
        print(f"  not enough clean laps - {tool.MIN_LAPS_PER_SIDE} a side is "
              "the floor. Nothing is said about the change.")
        return
    note = tool.compound_note(was, now)
    if note:
        print(f"  ** {note}")
    tool.sector_table(was, now)


# ------------------------------------------------------------ how it was driven

def how_driven(store, sessions) -> None:
    """Coast share and upshift rpm per session - `driving_style`'s reader and
    its filter (lap one, pit and out laps left out)."""
    from pitcrew.analysis.driving import read_frames

    _head("HOW IT WAS DRIVEN — coast share and upshift rpm, per session")
    if not sessions:
        print("  no session to read.")
    for session in sessions:
        reads = []
        for row in store.list_laps(session["id"]):
            if (row.get("is_pit_lap") or row.get("is_out_lap")
                    or (row.get("lap_num") or 0) <= 1):
                continue
            frames = store.get_lap_frames(row["id"])
            read = read_frames((frames or {}).get("frames") or [])
            if read.coast_pct is not None:
                reads.append(read)
        if not reads:
            print(f"  s{session['id']:<4} {session.get('kind') or '':<8} "
                  "no lap with frames to read")
            continue
        ups = [r.upshift_rpm for r in reads if r.upshift_rpm is not None]
        upshift = f"{median(ups):.0f} rpm" if ups else "—"
        print(f"  s{session['id']:<4} {session.get('kind') or '':<8} "
              f"coast {median(r.coast_pct for r in reads):4.1f}%   "
              f"flat {median(r.full_throttle_pct for r in reads):4.1f}%   "
              f"upshift {upshift}   (n={len(reads)})")


# ------------------------------------------------------------ by compound

def by_compound(store, event_id: int) -> None:
    """Plan row 5.22: the best lap and sectors on each tyre, and the gaps
    between tyres off like-for-like laps only - `tools/compound_pace.py`."""
    tool = _tool("compound_pace")
    # The whole event, whatever `--sessions` says: a best on a tyre is a best
    # over every lap on file (critic pass 1).
    _head("BY COMPOUND — bests per tyre, and gaps on like-for-like laps "
          "(whole event, not --sessions)")
    laps, evenings, refused = tool.load(store, [event_id])
    if refused:
        print(f"  {refused}")
        return
    from pitcrew.analysis.compound_pace import compound_pace

    tool.render(compound_pace(laps, sitting_of=evenings))


# ---------------------------------------------------- the driver as a variable

def split_notes(silences) -> tuple[list[str], list[str]]:
    """(under his session's row, gathered below the table). His own words
    belong on his session's row, not in a pile at the bottom (critic 6)."""
    under = [line for line in silences if "struck by hand, in his words" in line]
    return under, [line for line in silences if line not in under]


def trend_line(trend, label: str) -> str:
    """One session's three numbers, each with its n, "—" where unknown."""
    if trend.incidents is None:
        incidents = "—"
    else:
        incidents = (f"{trend.incidents} in {trend.judged_laps} judged laps "
                     f"({trend.incident_rate:.0%})")
    if trend.lap_one_cost_s is None:
        lap_one = "—"
    else:
        start = (f"start: {trend.start_type}" if trend.start_type
                 else "start type not on the event")
        lap_one = (f"{trend.lap_one_cost_s:+.1f} s vs lap 5 on "
                   f"(n={trend.lap_one_reference_n}; {start})")
    spread = ("—" if trend.consistency_sd_s is None
              else f"sd {trend.consistency_sd_s:.3f} s")
    return (f"  s{str(trend.session_id):<4} {label:<16} incidents {incidents}   "
            f"lap one {lap_one}   consistency {spread} (n={trend.consistency_n})")


def driver_variable(store, event_id: int, sessions, *, start_type=None) -> None:
    """Plan row 2.11 - here, and in no brief, plan or live call."""
    from pitcrew.analysis.driver_trends import session_trend
    from pitcrew.export.build import event_lap_inputs

    _head("THE DRIVER AS A VARIABLE — debrief only")
    # Not "never in a brief" for all three: whether lap one's cost belongs
    # in the pre-race brief is open (race-planner.md against row 2.11), and
    # the tool may not settle what both skill files leave to the driver.
    print("  Described, never forecast: incidents are memoryless, so none of "
          "this is a\n  warning, a live call or an allowance in a plan. "
          "Incidents and scatter never go in a\n  brief; whether lap one's "
          "cost does is open for the driver. Scatter is a state, not a loss.")
    wanted = {session["id"] for session in sessions}
    by_kind: dict[str, list] = {}
    for kind in sorted({session.get("kind") for session in sessions
                        if session.get("kind")}):
        by_kind[kind] = event_lap_inputs(store, event_id, kind)
    notes: dict[str, list[int]] = {}
    for session in sessions:
        laps = [lap for lap in by_kind.get(session.get("kind"), [])
                if lap.session_id == session["id"] and lap.session_id in wanted]
        if not laps:
            continue
        kind = session.get("kind")
        trend = session_trend(laps, session_id=session["id"], kind=kind,
                              start_type=start_type if kind == "race" else None)
        print(trend_line(trend, session_label(kind, session.get("rehearsal"))))
        under_row, footnotes = split_notes(trend.silences)
        for line in under_row:
            print(f"        - {line}")
        for line in footnotes:
            notes.setdefault(line, []).append(session["id"])
    for line, ids in notes.items():
        print(f"  - {line} (s{', s'.join(str(i) for i in ids)})")


def who_he_raced(store, sessions) -> None:
    """Plan row 3.2 - the named cars either side of him, per race session.

    **This is the step that was missing, not the data.** `analysis/rivals`
    had `tendencies` and `carry_into_knowledge` for weeks and `wiring_audit`
    listed the module under *no production code imports* - the chain from a
    read name to anything a person sees was never closed, so a board pass
    filed its readings and they stopped there. This call is what removed it
    from that list.

    **`carry_into_knowledge` is still on it**, and deliberately: writing the
    tendencies into `race_knowledge` changes what the next brief says, so it
    is a separate act and not a side effect of reading a debrief.
    """
    from pitcrew.analysis.rivals import MIN_LAPS_TOGETHER, tendencies

    races = [s for s in sessions if s.get("kind") == "race"]
    if not races:
        return
    _head("WHO HE RACED")
    said = False
    for session in races:
        found = tendencies(store, session["id"])
        sightings = store.list_board_sightings(session["id"])
        label = session_label(session.get("kind"), session.get("rehearsal"))
        named = sum(1 for row in sightings if row["driver"])
        # **A missing board pass is not a missing answer.** This printed
        # "no board pass on file" and dropped `found` on the floor, so
        # sessions named the old way - 334 and 499 rows on s88 and s112 -
        # reported nothing at all. The radar's answer is thinner and it is
        # still an answer; what it must not do is arrive unlabelled.
        if not sightings:
            if found:
                said = True
                print(f"  {label} s{session['id']}: no board pass — from the "
                      f"radar only, which sees about a second each way:")
                _rival_lines(found)
            else:
                print(f"  {label} s{session['id']}: nothing on file — run "
                      f"tools/read_replay_board.py")
            continue
        said = True
        unreadable = len(sightings) - named
        print(f"  {label} s{session['id']}: {len(sightings)} board reading(s)"
              + (f", {unreadable} from a cluster nobody could read"
                 if unreadable else ""))
        if not found:
            print(f"    nobody was beside him for {MIN_LAPS_TOGETHER}+ laps — "
                  f"one overtake is not a tendency")
            continue
        _rival_lines(found)
    if said:
        print("  Time spent beside him, and nothing more: not a gap, not a "
              "closing rate,\n  and not a prediction of anyone's stop — none "
              "of those are in a reading of the order.")


def _rival_lines(found) -> None:
    for one in found:
        print(f"    {one.name:<18} {one.laps_together:>2} lap(s) together,"
              f" mostly {one.mostly}"
              f"  (ahead {one.laps_ahead}, behind {one.laps_behind})"
              f"  [{one.source}]")


# --------------------------------------------------------- George's calls

def call_tally(revisions) -> tuple[Counter, list]:
    """Counts by what followed each filed call, and the ones he did not act on.

    **A missing verdict is counted, never read as acted** - it is a call
    recorded before verdicts were kept, or one never settled. Informational
    lines (the colour tier, the refuel watch) were said and not asked, and
    are counted as that rather than as instructions declined.
    """
    from pitcrew.race.call_outcome import NOT_ACTED

    tally: Counter = Counter()
    ignored = []
    for revision in revisions:
        payload = revision.get("plan") or {}
        if isinstance(payload, dict) and payload.get("informational"):
            tally["said, not an instruction"] += 1
            continue
        verdict = revision.get("verdict")
        if not verdict:
            tally["no verdict on file"] += 1
            continue
        tally[verdict] += 1
        if verdict == NOT_ACTED:
            ignored.append(revision)
    return tally, ignored


def calls_against_outcome(store, runs) -> None:
    _head("GEORGE'S CALLS — and what followed each")
    if not runs:
        print("  no race run on file for this event.")
        return
    for run in runs:
        revisions = store.list_revisions(run["id"])
        tally, ignored = call_tally(revisions)
        print(f"  run {run['id']} (session {run.get('session_id')}): "
              f"{len(revisions)} filed   "
              + "   ".join(f"{name} {n}" for name, n in tally.most_common()))
        for revision in ignored:
            print(f"    L{revision.get('lap_num'):<3} "
                  f"{revision.get('reason')!r} — "
                  f"{revision.get('verdict_detail') or ''}")


# ---------------------------------------------------- the race against its plan

def stint_lengths(rows) -> list[int]:
    """Laps per stint as run: the pit lap that opens a stop closes the stint.

    **A stop filed on two pit rows is one stop, and it closes on the first**
    (critic 6, passes 1 and 2). At Fuji lap 5 is the in-lap and lap 6 carries
    the pit flag, the out-lap flag and the fill - so lap 6 opens stint 2, as
    Daytona's out-lap does. "[5, 1, 14]" invented a stop; "[6, 14]" then
    had him box a lap later than he did.
    """
    lengths, current, previous_pit = [], 0, False
    for row in sorted(rows, key=lambda r: r.get("lap_num") or 0):
        current += 1
        pit = bool(row.get("is_pit_lap"))
        if pit and not previous_pit:
            lengths.append(current)
            current = 0
        previous_pit = pit
    if current:
        lengths.append(current)
    return lengths


def _whose_figure(stop, figure: float, others, this_session) -> str:
    """Which measured stop the event's figure came from, and what it holds.

    **The flag stores a race's own stop onto the event** (`_record_pit_loss`),
    and until 11 Sep it stored a stop's TOTAL - fill inside - as the ex-fuel
    figure. So the figure is matched against every race session's stops, and
    a total with a fill in it is called what it is (critic 6, pass 2).
    """
    candidates = [(this_session, stop)] + [(sid, s) for sid, s in others
                                           if s is not stop]
    for session_id, origin in candidates:
        mine = origin is stop
        where = "this stop" if mine else f"the session {session_id} stop"
        itself = ", so this compares it with itself" if mine else ""
        if (origin.fuel_added_l is not None
                and abs(figure - origin.ex_fuel_s) < 0.05):
            return f"measured at {where}, ex-fuel{itself}"
        if abs(figure - origin.total_s) < 0.05:
            if origin.fuel_added_l is not None:
                return (f"stored as measured, but it is {where}'s total with "
                        f"its {origin.fuel_added_l:.1f} L fill inside - about "
                        f"{origin.total_s - origin.ex_fuel_s:.0f} s high; the "
                        f"correction waits for the driver's yes")
            return (f"measured at {where}, a ceiling - no fill could be taken "
                    f"off{itself}")
    return "measured"


def pit_loss_line(stop, figure, source, *, others=(), this_session=None) -> str:
    """One measured stop against the event's own figure, in words that say
    which each is (rule 13).

    **The event's figure is named by its source, never called "declared"** -
    at Daytona it IS a measurement, and "72.3 against 72.28 declared" said a
    measured number was typed. **And a stop with no fill on file is a
    ceiling**: nothing was taken off, so the lane and the standing time are
    not separated (`pit_loss.best`), and printing its total as "ex-fuel"
    claimed a split nobody made.
    """
    if figure is None:
        against = "no figure on the event"
    else:
        if source == "measured":
            said = _whose_figure(stop, float(figure), others, this_session)
        elif source == "declared":
            # `pit_loss_source` says `declared` whether he typed it or the
            # row was created with the app's 20 s default (store docstring) -
            # which only a figure of 20 can be (critic 6, pass 2).
            said = ("declared - typed, or the app's 20 s default; the record "
                    "cannot tell which" if abs(float(figure) - 20.0) < 0.05
                    else "declared")
        else:
            said = "no source recorded"
        against = f"the event's {figure} s ({said})"
    if stop.fuel_added_l is None:
        return (f"stop on lap {stop.stop_lap}: {stop.total_s:.1f} s in all - "
                f"the fuel could not be taken off, so a ceiling and not the "
                f"ex-fuel figure; against {against}; {stop.method}")
    return (f"stop on lap {stop.stop_lap}: {stop.ex_fuel_s:.1f} s ex-fuel "
            f"against {against}; {stop.method}")


def race_length(context) -> str:
    """What a full race is: laps, or minutes for a timed one."""
    laps = getattr(context, "race_laps", None)
    minutes = getattr(context, "race_minutes", None)
    if laps:
        return f"{laps} laps"
    if minutes:
        return f"{minutes:g} minutes"
    return "not on the event"


def strip_fixed_wear(line: str) -> tuple[str, bool]:
    """**Not a fixed sentence presented as this race's finding** (critic 6):
    the audit ends its wear clause with `WEAR_CONTRADICTION`, three particular
    gauge readings, word for word at every event. (line, whether it was cut)"""
    from pitcrew.race.expectations import WEAR_CONTRADICTION

    fixed = f"; {WEAR_CONTRADICTION}."
    if fixed in line:
        return line.replace(fixed, "."), True
    return line, False


def session_label(kind, rehearsal) -> str:
    """A rehearsal is not the league race, and says so (critic 6)."""
    return f"{kind} (rehearsal)" if kind == "race" and rehearsal else (kind or "")


def against_the_plan(store, event, runs, all_runs=None) -> None:
    """From the data, never from the plan - through the export's own
    expressions: `audit_line_from_laps` for burn, lap time and wear against
    `expects`, and `race.pit_loss.measure` for each stop."""
    from pitcrew.export.build import event_lap_inputs
    from pitcrew.race import pit_loss
    from pitcrew.race.coordinator import context_from_event
    from pitcrew.race.expectations import audit_line_from_laps

    _head("THE RACE AGAINST ITS PLAN — from the data, never from the plan")
    if not runs:
        print("  no race run on file for this event.")
        return
    strategies = {row["id"]: row for row in store.list_strategies(event["id"])}
    race_laps = event_lap_inputs(store, event["id"], "race")
    figure = event.get("pit_loss_secs")
    source = event.get("pit_loss_source")
    # What a full race is, so a short recording reads as short (critic 6):
    # "run [16]" of a thirty-minute race is sixteen laps ON FILE.
    length = race_length(context_from_event(event))
    # Every run's stops first: the event's one measured figure came from one
    # of them, and the line for each stop has to say which.
    # **Every race run on the event, filtered or not** (critic 6, pass 3):
    # built from the `--sessions`-filtered runs, a debrief of the earlier
    # Daytona race called a figure with 49 L of fill inside it "measured",
    # because the run it came from had been filtered out.
    every_run = list(all_runs) if all_runs is not None else list(runs)
    every_run += [run for run in runs if run not in every_run]
    measured: dict = {}
    for run in every_run:
        rows = store.list_laps(run["session_id"]) if run.get("session_id") else []
        measured[run["id"]] = (rows, pit_loss.measure(
            rows, refuel_rate_lps=event.get("refuel_rate_lps")))
    everywhere = [(run.get("session_id"), stop) for run in every_run
                  for stop in measured[run["id"]][1]]
    dropped_wear = False
    for run in runs:
        row = strategies.get(run.get("strategy_id"))
        if row is None:
            print(f"  run {run['id']}: raced with no plan on file - nothing to "
                  "score against.")
            continue
        plan = row.get("plan") if isinstance(row.get("plan"), dict) else {}
        laps = [lap for lap in race_laps if lap.session_id == run.get("session_id")]
        print(f"  run {run['id']} against strategy {row['id']} "
              f"({row.get('label') or 'unlabelled'}):")
        line, dropped = strip_fixed_wear(
            audit_line_from_laps(plan.get("expects"), laps))
        dropped_wear = dropped_wear or dropped
        print(f"    {line or 'the plan carried no expectation to score against'}")
        rows, stops = measured[run["id"]]
        planned = [s.get("laps") for s in plan.get("stints") or []
                   if isinstance(s, dict)]
        print(f"    stints planned {planned or '—'}   run "
              f"{stint_lengths(rows) or '—'}   ({len(rows)} laps on file; the "
              f"race is {length})")
        if not stops:
            print("    pit loss: no stop these rows can resolve (an in-lap, its "
                  "out-lap and three clean laps)")
        for stop in stops:
            print(f"    {pit_loss_line(stop, figure, source, others=everywhere, this_session=run.get('session_id'))}")
    if dropped_wear:
        print("  (the audit's fixed sentence about three old gauge readings is "
              "left out - it is\n   not this race's finding; the export still "
              "carries it, as its own open task)")


# ------------------------------------------------------------------ the radio

def radio(store, event_id: int, session_ids=None) -> None:
    _head("THE RADIO — what he asked, and what the engineer could not take")
    tool = _tool("radio_review")
    if session_ids:
        # `--sessions` filters every section (critic 6): unfiltered, s143's
        # debrief printed four exchanges from sessions 118, 119 and 125.
        marks = ",".join("?" * len(session_ids))
        rows = tool._rows(
            store, f"WHERE sessions.event_id = ? AND radio.session_id IN ({marks})",
            (event_id, *session_ids))
    else:
        rows = tool._rows(store, "WHERE sessions.event_id = ?", (event_id,))
    for line in tool.report(rows, misses_only=True):
        print(line)


def close() -> None:
    _head("THEN")
    print("  Close every open prediction above in its brain/ledger/ row, update "
          "the\n  car-state file if what is in the car changed, and commit "
          "brain/ -\n  one commit per debrief.\n")


# ------------------------------------------------------------------ one lap

def _gear(value) -> str:
    """Gears are said as words in the copy, not as column headings."""
    names = {1: "first", 2: "second", 3: "third", 4: "fourth",
             5: "fifth", 6: "sixth", 7: "seventh", 8: "eighth"}
    return names.get(value, f"gear {value}")


def _clock(second: float | None) -> str:
    if second is None:
        return "  --:--  "
    mins, secs = divmod(max(0.0, second), 60)
    return f"{int(mins):02d}:{secs:05.2f}"


def walk_through(store, event_id: int, lap_num: int | None) -> int:
    from pitcrew.analysis.walkthrough import NOTABLE_SIGMA, from_store as walk

    result = walk(store, event_id, lap_num=lap_num)
    if result is None:
        print(f"No lap to talk through for event {event_id}.")
        return 1

    _head(f"LAP {result.lap_num} — {_ms(result.lap_time_ms)}")
    if result.reference_ms is not None:
        gap = result.delta_ms / 1000.0
        print(f"  against the median of your other {result.reference_laps} "
              f"clean laps ({_ms(result.reference_ms)}): {gap:+.3f} s")
    else:
        print("  no other clean lap to compare against — described, not judged")

    _head("CORNER BY CORNER")
    print("  %-4s %-12s %8s %8s %7s %6s %6s %s"
          % ("", "corner", "time", "vs med", "sigma", "min", "gear", "video"))
    for seg in result.segments:
        delta = f"{seg.delta:+.3f}" if seg.delta is not None else "     —"
        sigma = f"{seg.sigma:+.1f}" if seg.sigma is not None else "    —"
        mark = "*" if seg.notable else " "
        gear = f"G{seg.gear}" if seg.gear else " —"
        if seg.gear_differs:
            gear += f"({seg.usual_gear})"
        print("  %-4s %-12s %7.3fs %8s %7s %6.1f %6s %s"
              % (mark, seg.corner_name, seg.seconds, delta, sigma,
                 seg.min_kph, gear, _clock(seg.video_second)))

    if result.unaccounted_s is not None:
        _head("WHERE THE TIME WENT")
        print(f"  corners      {result.accounted_s:+.3f} s")
        print(f"  everything else {result.unaccounted_s:+.3f} s   "
              "— straights and transitions, which no corner window covers")
        print(f"  lap          {result.delta_ms / 1000.0:+.3f} s")

    _head("WHAT STANDS OUT")
    if not result.notable:
        print(f"  Nothing. Every corner on this lap sits inside "
              f"{NOTABLE_SIGMA:.0f} standard deviation of")
        print("  your own normal there — which is what an ordinary lap looks "
              "like, and it")
        print("  is why the lap time came from somewhere else.")
    for seg in result.notable:
        way = "quicker" if seg.delta < 0 else "slower"
        print(f"  {seg.corner_name}: {abs(seg.delta):.3f} s {way} than usual, "
              f"{abs(seg.sigma):.1f} sigma.")
        if seg.gear_differs:
            print(f"      and in {_gear(seg.gear)} where you normally use "
                  f"{_gear(seg.usual_gear)}.")
        print(f"      watch it at {_clock(seg.video_second)}")
    if result.video_path:
        print(f"\n  {Path(result.video_path).name}")

    if result.silences:
        _head("SILENCES")
        for line in result.silences:
            print(f"  - {line}")
    print("\n  Corner times are measured on both sides. Whether a difference "
          "REPEATS is a")
    print("  separate question this cannot answer from one lap.\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("event_id", type=int)
    parser.add_argument("--sessions", type=int, nargs="*", default=None,
                        help="limit to these session ids")
    parser.add_argument("--report", default=None, metavar="FILE",
                        help="his report, printed first")
    parser.add_argument("--before", type=int, nargs="+", default=None,
                        metavar="SESSION", help="sessions before a change")
    parser.add_argument("--after", type=int, nargs="+", default=None,
                        metavar="SESSION", help="sessions after it")
    parser.add_argument("--lap", type=int, default=None,
                        help="talk through this lap instead of the debrief")
    parser.add_argument("--walk", action="store_true",
                        help="talk through the quickest clean lap")
    parser.add_argument("--db", default=None,
                        help="a different archive - a copy, for trying it "
                             "without opening the live file")
    args = parser.parse_args()

    def _store() -> Store:
        return Store(args.db) if args.db else Store()

    if args.walk or args.lap is not None:
        return walk_through(_store(), args.event_id, args.lap)

    store = _store()
    try:
        event = store.get_event(args.event_id)
        if event is None:
            print(f"No event {args.event_id}.")
            return 1
        driver_first(args.report)
        open_predictions(event)
        debrief = from_store(store, args.event_id, session_ids=args.sessions)
        if debrief is None:
            _head("SESSION")
            print("  no practice debrief: no corner model for the circuit, or "
                  "no practice laps.\n  A model is built from your own laps — "
                  "see pitcrew/analysis/resolve.py.")
        else:
            render(debrief)
        change_landed(store, args.before, args.after)
        sessions = sorted(store.list_sessions(args.event_id),
                          key=lambda s: s.get("started_at") or "")
        if args.sessions:
            sessions = [s for s in sessions if s["id"] in set(args.sessions)]
        how_driven(store, sessions)
        by_compound(store, args.event_id)
        driver_variable(store, args.event_id, sessions,
                        start_type=event.get("start_type"))
        who_he_raced(store, sessions)
        all_runs = store.list_race_runs(args.event_id)
        runs = all_runs
        if args.sessions:
            runs = [r for r in all_runs if r.get("session_id") in set(args.sessions)]
        calls_against_outcome(store, runs)
        against_the_plan(store, event, runs, all_runs=all_runs)
        radio(store, args.event_id, args.sessions)
        close()
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
