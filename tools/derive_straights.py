"""Derive each circuit's straights from stored laps, so George speaks where a clip fits.

    python tools/derive_straights.py --all                  # every circuit, dry run
    python tools/derive_straights.py --circuit mount-panorama-circuit-full-course
    python tools/derive_straights.py --circuit KEY --replay 176
    python tools/derive_straights.py --circuit KEY --json model.json
    python tools/derive_straights.py --all --apply --db data/pitcrew.db
    python tools/derive_straights.py --circuit KEY --apply --replace --db PATH

**A dry run by default, and it reads the database read-only** - a `mode=ro`
URI, never a copy (a plain copy of a WAL file misses the WAL). `--apply` writes
into `straight_models` of the file named by `--db`, which has to be given
explicitly and has to exist.

Every circuit with events on file is derived (no --circuit is the same as
--all). What is stored passes the gates in `pitcrew/analysis/straights.py`;
a window that fails them is printed and left out. `--apply` never replaces a
stored model with a worse one (`pitcrew/analysis/straight_refresh.compare`)
unless `--replace` says to. The app re-derives on its own when a session
closes (`straight_refresh.plan`); this is for all circuits at once, a replay,
or an override.

How a straight is found and pooled is `pitcrew/analysis/straights.py`; how the
live gate uses the model is `pitcrew/race/straight.py`.

`--replay SESSION` runs that session's stored frames, in order, through the live
detector and `straight.fits` - with the model (derived WITHOUT that session, so
the figure is out of sample, unless `--in-sample`) and without it - and reports,
for a clip started at the first moment the gate allows on each straight, how
often it finished inside the straight.
"""
from __future__ import annotations

import argparse
import datetime
import json
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pitcrew.analysis import straight_refresh as refresher    # noqa: E402
from pitcrew.analysis import straights as derivation          # noqa: E402
from pitcrew.analysis.resolve import circuit_key              # noqa: E402
from pitcrew.race import straight as live                     # noqa: E402
from pitcrew.store.db import DEFAULT_DB_PATH                  # noqa: E402
from pitcrew.telemetry.recorder import decode_frames          # noqa: E402

# What the replay reads - it runs the live detector, which wants yaw rate.
_KEEP = ("throttle_pct", "brake_pct", "lat_g", "speed_kph", "yaw_rate",
         "lap_distance_m", "pos_x", "pos_y", "pos_z")

REPLAY_CLIPS_S = (2.0, 2.8)


def _read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)


def _slim(frames: list[dict]) -> list[dict]:
    return [{key: frame.get(key) for key in _KEEP} for frame in frames]


def circuits(conn: sqlite3.Connection) -> dict[str, list[int]]:
    """Every circuit with events on file, and the events at it."""
    return refresher.circuits(refresher.read_only_query(conn))


def clean_laps(conn: sqlite3.Connection, event_ids: list[int], *,
               exclude_sessions: set[int] = frozenset(),
               max_laps: int = refresher.LOAD_LIMIT,
               ) -> list[derivation.LapInput]:
    """The most recent clean laps, in the order driven - the same selection
    the app refreshes from (`straight_refresh.load_laps`)."""
    return refresher.load_laps(refresher.read_only_query(conn), event_ids,
                               limit=max_laps,
                               exclude_sessions=sorted(exclude_sessions))


def session_laps(conn: sqlite3.Connection,
                 session_id: int) -> list[derivation.LapInput]:
    """Every lap of one session in order, struck or not - a replay is the race
    as it was driven, pit lap and all."""
    rows = conn.execute(
        "SELECT l.session_id, l.lap_num, l.lap_time_ms, f.blob, f.sample_hz "
        "FROM laps l JOIN lap_frames f ON f.lap_id = l.id "
        "WHERE l.session_id = ? ORDER BY l.lap_num", (session_id,)).fetchall()
    return [derivation.LapInput(s, n, ms, _slim(decode_frames(b)),
                                hz or derivation.SAMPLE_HZ)
            for s, n, ms, b, hz in rows]


def session_circuit(conn: sqlite3.Connection, session_id: int) -> str | None:
    row = conn.execute(
        "SELECT e.track, e.layout FROM sessions s JOIN events e "
        "ON e.id = s.event_id WHERE s.id = ?", (session_id,)).fetchone()
    return circuit_key(row[0], row[1]) if row and row[0] else None


# ----------------------------------------------------------------- replay

@dataclass
class _Ruler:
    """The live ruler's two answers, set frame by frame from stored laps."""
    distance_m: float | None = None
    last_lap_length_m: float | None = None

    def where(self) -> float | None:
        return self.distance_m


@dataclass
class ReplayResult:
    clip_s: float
    laps: int
    straights: int            # detector windows (held at least 2 s)
    started: int              # clips the gate let start
    inside: int               # finished before the detector's window closed
    before_brake: int         # no brake application while it played
    on_straight: int          # finished inside the bridged straight
    modelled_starts: int      # of `started`, how many the model decided

    def fraction(self, count: int) -> float | None:
        return None if not self.started else count / self.started

    def describe(self) -> str:
        def pct(count):
            value = self.fraction(count)
            return "n/a" if value is None else f"{value:.0%}"
        return (f"{self.clip_s:.1f} s clip: {self.started} started on "
                f"{self.straights} straights over {self.laps} laps "
                f"({self.started / max(1, self.laps):.1f}/lap, "
                f"{self.modelled_starts} by the model); finished inside the "
                f"detector window {pct(self.inside)}, before any brake "
                f"{pct(self.before_brake)}, inside the straight "
                f"{pct(self.on_straight)}")


def replay(laps: list[derivation.LapInput],
           model: live.StraightsModel | None, clip_s: float, *,
           margin_s: float | None = None) -> ReplayResult:
    """One session's frames through the live detector and gate, in order."""
    hz = laps[0].sample_hz if laps else derivation.SAMPLE_HZ
    frames, distances, last_lengths = [], [], []
    previous = None
    for lap in laps:
        length = max((f.get("lap_distance_m") or 0.0) for f in lap.frames) \
            if lap.frames else None
        for frame in lap.frames:
            frames.append(frame)
            distances.append(frame.get("lap_distance_m"))
            last_lengths.append(previous)
        previous = length
    bridged = derivation.bridged_listenable(frames, hz)

    ruler = _Ruler()
    detector = live.Straight()
    detector.use_model(model, ruler=lambda: ruler)
    saved_margin = live.FIT_MARGIN_S
    if margin_s is not None:
        live.FIT_MARGIN_S = margin_s
    try:
        windows = []          # [open_index, close_index, start_index, modelled]
        current = None
        for index, frame in enumerate(frames):
            now = index / hz
            ruler.distance_m = distances[index]
            ruler.last_lap_length_m = last_lengths[index]
            speed = frame.get("speed_kph")
            detector.update(
                throttle_pct=frame.get("throttle_pct"),
                speed_ms=None if speed is None else speed / 3.6,
                yaw_rate=frame.get("yaw_rate"), now=now)
            window = detector.window(now)
            if not window.open:
                if current is not None and detector._since is None:
                    current[1] = index
                    windows.append(current)
                    current = None
                continue
            if current is None:
                current = [index, None, None, False]
            if current[2] is None and live.fits(window, clip_s, strict=True):
                current[2] = index
                current[3] = window.remaining_s is not None
        if current is not None:
            current[1] = len(frames)
            windows.append(current)
    finally:
        live.FIT_MARGIN_S = saved_margin

    span = int(round(clip_s * hz))
    started = inside = before_brake = on_straight = modelled = 0
    for _open, close, start, by_model in windows:
        if start is None:
            continue
        started += 1
        modelled += int(by_model)
        end = start + span
        if end <= close:
            inside += 1
        played = frames[start:min(end, len(frames))]
        if end <= len(frames) and all((f.get("brake_pct") or 0.0)
                                      <= derivation.MAX_BRAKE_PCT
                                      for f in played):
            before_brake += 1
        if end <= len(frames) and all(bridged[start:end]):
            on_straight += 1
    return ReplayResult(clip_s, len(laps), len(windows), started, inside,
                        before_brake, on_straight, modelled)


# ------------------------------------------------------------------ report

def describe(result: derivation.Derived) -> str:
    lines = [f"{result.circuit_key}: {result.laps_used} clean laps pooled"
             + (f"; refused {result.refused}" if result.refused else "")]
    for window in result.dropped:
        lines.append("  LEFT OUT " + derivation.describe_dropped(window))
    if result.model is None:
        lines.append(f"  no model - {result.reason}")
        return "\n".join(lines)
    model = result.model
    lines.append(f"  [DERIVED] axis {model['lap_length_m']} m (integrated), "
                 f"{model.get('laps_available', '?')} clean laps on file, "
                 f"sessions {model['session_ids']}")
    lines.append("  id   start_m    end_m  brake_m  laps  median_s  "
                 "p25-p75 s  end spread m  end km/h")
    for w in model["windows"]:
        lines.append(
            f"  {w['id']:<3} {w['start_m']:>8.1f} {w['end_m']:>8.1f} "
            f"{(w['brake_m'] if w['brake_m'] is not None else float('nan')):>8.1f} "
            f"{w['laps']:>3}/{w['laps_pooled']:<3} {w['median_s']:>6.2f}  "
            f"{w['p25_s']:>5.2f}-{w['p75_s']:<5.2f} {w['end_spread_m']:>9.1f}  "
            f"{w['end_kph'] if w['end_kph'] is not None else 'n/a':>8}")
    lines.append("  braking entries: " + ", ".join(
        f"{z['id']} {z['start_m']:.0f} m ({z['laps']} laps)"
        for z in model["braking"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", help="database to read (and, with --apply, "
                        f"write); default {DEFAULT_DB_PATH}, read-only")
    parser.add_argument("--circuit", help="one circuit key")
    parser.add_argument("--all", action="store_true",
                        help="every circuit with events on file (the default "
                             "without --circuit)")
    parser.add_argument("--exclude-session", type=int, action="append",
                        default=[], help="leave a session out of the pool")
    parser.add_argument("--json", help="write the derived model to this file")
    parser.add_argument("--replay", type=int, metavar="SESSION",
                        help="replay a session through the gate")
    parser.add_argument("--in-sample", action="store_true",
                        help="keep the replayed session in the pool")
    parser.add_argument("--apply", action="store_true",
                        help="write the models into --db (with --circuit or "
                             "--all)")
    parser.add_argument("--replace", action="store_true",
                        help="with --apply: store even where the stored model "
                             "would be replaced by a worse one")
    args = parser.parse_args(argv)

    if args.circuit and args.all:
        parser.error("--circuit and --all: pick one")
    if args.apply and not args.db:
        parser.error("--apply writes a database: name it with --db PATH")
    if args.apply and not (args.circuit or args.all):
        parser.error("--apply needs --circuit KEY or --all")
    if args.replace and not args.apply:
        parser.error("--replace only means something with --apply")
    path = Path(args.db) if args.db else DEFAULT_DB_PATH
    if not path.is_file():
        # **Refused, not created.** `Store(path)` would build an empty
        # database at a mistyped path and report the model written.
        print(f"no database at {path} - refusing", file=sys.stderr)
        return 2

    store = None
    if args.apply:
        from pitcrew.store.db import Store
        store = Store(path)
    try:
        return _run(args, path, store)
    finally:
        if store is not None:
            store.close()


def _run(args, path: Path, store) -> int:
    today = datetime.date.today().isoformat()
    conn = _read_only(path)
    outcomes: dict[str, refresher.Outcome] = {}
    try:
        query = refresher.read_only_query(conn)
        known = refresher.circuits(query)
        wanted = [args.circuit] if args.circuit else sorted(known)
        exclude = set(args.exclude_session)
        if args.replay is not None and not args.in_sample:
            exclude.add(args.replay)

        for key in wanted:
            if key not in known:
                print(f"{key}: no events at this circuit")
                continue
            # Decided as a dry run; written here, and only under the flag.
            outcome = refresher.refresh(
                query, key, known[key], always=True, replace=args.replace,
                today=today, exclude_sessions=sorted(exclude))
            if args.apply and outcome.action == "would-store":
                model = outcome.derived.model
                model["tool"] = "tools/derive_straights.py"
                store.save_straight_model(key, model)
                outcome.action = "stored"
            outcomes[key] = outcome
            if outcome.derived is not None:
                print(describe(outcome.derived))
            verdict = {"stored": "STORED", "would-store": "would store",
                       "refused": "REFUSED"}.get(outcome.action,
                                                 outcome.action)
            print(f"  -> {verdict}"
                  + ("" if outcome.action in ("stored", "would-store")
                     else f": {outcome.reason}")
                  + ("" if outcome.seconds is None
                     else f" [{outcome.seconds:.1f} s]"))
        results = {key: o.derived for key, o in outcomes.items()
                   if o.derived is not None}
        replayed = (session_laps(conn, args.replay)
                    if args.replay is not None else None)
        replay_key = (session_circuit(conn, args.replay)
                      if args.replay is not None else None)
    finally:
        conn.close()

    if replayed is not None:
        result = results.get(replay_key)
        model = (live.StraightsModel.from_dict(result.model)
                 if result is not None and result.model is not None else None)
        print(f"\nreplay of session {args.replay} ({replay_key}), model "
              f"{'out of sample' if not args.in_sample else 'in sample'}"
              f"{'' if model else ' - NONE derived'}:")
        for clip in REPLAY_CLIPS_S:
            print("  fallback  " + replay(replayed, None, clip).describe())
            if model is not None:
                print("  model     " + replay(replayed, model, clip).describe())

    if args.json:
        if not args.circuit or results.get(args.circuit) is None \
                or results[args.circuit].model is None:
            print("--json needs one circuit with a model", file=sys.stderr)
            return 1
        Path(args.json).write_text(
            json.dumps(results[args.circuit].model, indent=1) + "\n",
            encoding="utf-8", newline="\n")
        print(f"wrote {args.json}")

    if store is None:
        print("\ndry run - nothing written")
        return 0
    print()
    for key, outcome in outcomes.items():
        if outcome.action != "stored":
            print(f"not applied: {key} - {outcome.reason}")
            continue
        back = store.straight_model(key)
        print(f"applied: {key}, {len(back.straights)} straights, "
              f"{back.laps} laps, sessions {list(back.session_ids)} -> {path}")
    if args.circuit and args.circuit in outcomes \
            and outcomes[args.circuit].action != "stored":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
