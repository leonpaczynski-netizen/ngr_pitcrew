"""Carry the names typed for the REPLAY board onto the LIVE pit wall's drivers.

    python tools/bridge_driver_names.py --session 143            # dry run
    python tools/bridge_driver_names.py --session 143 --apply    # rename

About 0.5 s a frame (an accurate ffmpeg seek on AV1 plus both readers): the
39-minute Daytona race at the default `--every 3` walks in about 7 minutes.

**Two readers, one screen, and they do not agree on the pixels.** The replay
reader (`tools/read_replay_board.py`) and the live roster
(`telemetry/roster.py`) normalise a name differently - one crops to all ink and
stretches, the other crops to the widest ink group and keeps the length - so a
live exemplar and a replay exemplar of the same driver measure 0.15-0.30 apart
with no gap between nearest and second nearest. Comparing them directly would
put names on cars by coincidence.

What they DO share is the frame. Run both over the same recording and a row
both of them read is the same physical row, whatever each made of its pixels.
So each reader answers only the question it was built for:

* the replay reader says whose name it is, by `label_for` distance against the
  roster the driver labelled by eye - never by cluster index;
* a `Roster` seeded from `drivers` says which `Car #N` the live pit wall would
  have called it, exactly as it will be seeded tomorrow.

Each pairing is a vote. A `Car #N` is renamed only when it has enough of them
and nearly all say one name. **A split vote is a merged cluster** - the live
threshold is wide - and naming it would put one driver's name on another's
car, which is worse than `Car #N`.

Only rows already in `drivers` can be named. A cluster founded during the walk
is not written: nothing seeds from it tomorrow.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import read_replay_board as replay                               # noqa: E402
from pitcrew.telemetry.board import flag_ladder, own_row         # noqa: E402
from pitcrew.telemetry.roster import Roster                      # noqa: E402
from pitcrew.telemetry.roster import read as read_live_rows      # noqa: E402

# **How far apart the two readers' y for one row may be.** Both report a flag's
# centre, but the replay reader finds only the BLUE of the flag and the live
# one any hue, so they differ by a few pixels: live minus replay measured -6
# to 0 over 1,407 pairings on Daytona 143, mostly -1 and -4. Rows are 37-72 px
# apart, so 6 px cannot reach a neighbour; a live row must also be the only
# one in reach.
PAIR_TOL_PX = 6

# **At least this many paired sightings before a name is proposed.** At 90%
# a cluster with fewer than ten votes cannot carry a single dissent, so one
# misread refuses it - the safe direction. Below eight the evidence is a
# couple of laps of one neighbour, which a merged cluster can easily fake.
MIN_PAIRS = 8
# ...and this share of ALL its pairings must be one name. Pairings whose
# replay crop matched no labelled name count against it: a live cluster that
# is half somebody nobody named is a merged cluster all the same.
MIN_SHARE = 0.90

# Where the replay reader's label is refused as a label, not as a name.
UNMATCHED = "(no labelled name)"
AMBIGUOUS = "(two names in reach)"


# --------------------------------------------------------------- the labels

def replay_labels(roster_path: Path) -> list[tuple[np.ndarray, str]]:
    """`[(bits, name)]` off a replay roster, as `label_for` wants them.

    Newer rosters carry the packed `exemplar`. Older ones carry only the 4x
    nearest-neighbour PNG, which is the exemplar exactly - so it is decoded
    and, where the roster has a `fingerprint`, checked against it. An entry
    that fails the check is dropped rather than trusted.
    """
    from PIL import Image

    data = json.loads(roster_path.read_text(encoding="utf-8"))
    out = []
    for entry in data.values():
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name or name == replay.UNREADABLE:
            continue
        if entry.get("exemplar"):
            bits = replay.unpack_bits(entry["exemplar"])
        else:
            png = entry.get("exemplar_do_not_read") or entry.get("bitmap")
            if not png or not (roster_path.parent / png).exists():
                continue
            image = np.asarray(Image.open(roster_path.parent / png).convert("L"))
            step = image.shape[1] // replay.NAME_SHAPE[0]
            bits = image[::step, ::step] > 127
            if bits.shape != replay.NAME_SHAPE[::-1]:
                continue
        mark = entry.get("fingerprint")
        if mark and replay.fingerprint(bits) != mark:
            print(f"  ** {name}: exemplar does not match its fingerprint, "
                  f"dropped")
            continue
        out.append((bits, name))
    return out


def name_of_replay(bits, labels) -> str:
    """The labelled name for one replay crop, or why there is none.

    `label_for` answers with the nearest. **A second, DIFFERENT name also in
    reach refuses**: the threshold sits below the closest different pair ever
    measured, but only just, and a vote cast by a coin toss is not a vote.
    """
    name, _ = replay.label_for(bits, labels)
    if name is None:
        return UNMATCHED
    for other, other_name in labels:
        if (other_name != name and other.shape == bits.shape
                and (other != bits).mean() < replay.SAME_NAME_MAX_DIFF):
            return AMBIGUOUS
    return name


# ------------------------------------------------------------------- pairing

def pair_rows(live_rows, replay_rows, tol: int = PAIR_TOL_PX):
    """`[(live_row, replay_row)]` for the rows both readers read on one frame.

    `live_rows` are `roster.BoardRow`s, `replay_rows` the replay reader's
    `(side, y, bits, crop)`. Paired on y alone - the same frame is the rest of
    the key. A replay row with no live row in reach, or with two, is dropped.
    """
    pairs = []
    for rrow in replay_rows:
        near = [row for row in live_rows
                if row.name is not None and not row.is_own
                and abs(row.y - rrow[1]) <= tol]
        if len(near) == 1:
            pairs.append((near[0], rrow))
    return pairs


def live_read(frame):
    """The pit wall's own path: ladder once, own row, then the names."""
    ladder = flag_ladder(frame)
    if not ladder:
        return []
    board = own_row(frame, ladder=ladder)
    if board is None:
        return []
    return read_live_rows(frame, board, ladder)


def replay_read(frame):
    return replay.read_frame(frame) or []


@dataclass
class Votes:
    """Per live driver (its `drivers.name`), the names its rows were read as."""
    by_driver: dict = field(
        default_factory=lambda: collections.defaultdict(collections.Counter))
    frames: int = 0
    paired: int = 0
    minted: int = 0            # pairings whose live row founded a new cluster
    dy: collections.Counter = field(default_factory=collections.Counter)

    def see(self, frame, roster: Roster, labels, *,
            live=None, rep=None) -> None:
        live, rep = live or live_read, rep or replay_read
        self.frames += 1
        # **Every live row goes through the roster, not only the paired ones.**
        # The running averages move with every sighting, exactly as they do
        # on the wall; feeding it only the paired rows would be a different
        # roster from the one the names are meant for.
        live_rows = live(frame)
        ids = {id(row): roster.see(row.name) for row in live_rows}
        replay_rows = rep(frame) if live_rows else []
        for row, rrow in pair_rows(live_rows, replay_rows):
            self.paired += 1
            self.dy[row.y - rrow[1]] += 1
            driver = roster.name_of(ids[id(row)])
            if not driver:
                self.minted += 1
                continue
            self.by_driver[driver][name_of_replay(rrow[2], labels)] += 1


# ------------------------------------------------------------------ deciding

@dataclass(frozen=True)
class Verdict:
    driver: str
    seen: int
    top: str | None
    share: float
    second: str | None
    second_n: int
    rename: bool
    why: str


def decide(votes: Votes, *, min_pairs: int = MIN_PAIRS,
           min_share: float = MIN_SHARE) -> list[Verdict]:
    """One verdict per live driver that was paired at all, most seen first."""
    out = []
    for driver, names in votes.by_driver.items():
        seen = sum(names.values())
        ranked = names.most_common()
        top, top_n = ranked[0]
        second, second_n = ranked[1] if len(ranked) > 1 else (None, 0)
        share = top_n / seen
        if top in (UNMATCHED, AMBIGUOUS):
            rename, why = False, "most pairings carry no labelled name"
        elif seen < min_pairs:
            rename, why = False, f"only {seen} pairing(s), need {min_pairs}"
        elif share < min_share:
            rename, why = False, (f"split {top_n}/{seen} - a merged cluster, "
                                  f"never named")
        elif not driver.startswith("Car #"):
            rename = False
            why = ("already named" if driver == top
                   else f"already named {driver!r} and the board says {top!r}")
        else:
            rename, why = True, "rename"
        out.append(Verdict(driver, seen, top, share, second, second_n,
                           rename, why))
    out.sort(key=lambda v: -v.seen)
    return out


def renames(verdicts) -> list[tuple[str, str]]:
    """`(old, new)` in the order `--apply` makes them.

    **Most-paired first, because `rename_driver` merges by deleting.** The
    first `Car #N` given a name keeps its row and exemplar; each later one
    given the same name is deleted into it. The best-evidenced cluster is the
    one whose bitmap should seed tomorrow.
    """
    return [(v.driver, v.top) for v in verdicts if v.rename]


# ---------------------------------------------------------------- the video

def frame_at(video: Path, seconds: float):
    """One RGB frame, accurately seeked, or `None` past the end."""
    width, height = replay.CANVAS
    result = subprocess.run(
        [replay._ffmpeg(), "-hide_banner", "-loglevel", "error",
         "-ss", f"{seconds:.3f}", "-i", str(video), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    if len(result.stdout) != width * height * 3:
        return None
    return np.frombuffer(result.stdout, np.uint8).reshape(height, width, 3)


def seed_exemplars(db: Path) -> dict:
    """`Store.driver_exemplars`, read-only.

    `Store()` runs the schema upgrade on open, which is a write. A dry run
    must not be one.
    """
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT name, exemplar, rows, cols FROM drivers "
            "WHERE exemplar IS NOT NULL AND rows IS NOT NULL").fetchall()
    finally:
        conn.close()
    out = {}
    for name, blob, n_rows, n_cols in rows:
        wanted = int(n_rows) * int(n_cols)
        bits = np.unpackbits(np.frombuffer(blob, dtype=np.uint8))[:wanted]
        if bits.size == wanted:
            out[name] = bits.reshape(int(n_rows), int(n_cols)).astype(bool)
    return out


def session_video(db: Path, session_id: int) -> str | None:
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT video_path FROM sessions WHERE id = ?",
                           (session_id,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def backup(db: Path) -> Path:
    """A consistent copy through the sqlite backup API - a file copy misses
    the WAL."""
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    target = db.with_name(f"{db.stem}-before-bridge-names-{stamp}.db")
    src = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    dst = sqlite3.connect(str(target))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return target


def apply(store, pairs) -> int:
    """Every rename through `Store.rename_driver`. Returns stops moved."""
    moved = 0
    for old, new in pairs:
        moved += store.rename_driver(old, new)
    return moved


def report(votes: Votes, verdicts) -> None:
    print(f"\n{votes.frames} frame(s), {votes.paired} row(s) read by both "
          f"readers; {votes.minted} of those were a cluster not in `drivers` "
          f"and are not written")
    if votes.dy:
        print("  live y - replay y:",
              ", ".join(f"{d:+d}:{n}" for d, n in sorted(votes.dy.items())))
    print(f"\n  {'driver':<9} {'pairs':>5}  {'top name':<20} {'share':>6}  "
          f"second")
    for v in verdicts:
        second = f"{v.second} ({v.second_n})" if v.second else "-"
        print(f"  {v.driver:<9} {v.seen:>5}  {v.top or '-':<20} "
              f"{v.share:>6.0%}  {second:<28} {v.why}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--session", type=int, required=True)
    ap.add_argument("--video", help="default: the session's own recording")
    ap.add_argument("--every", type=float, default=3.0)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=None)
    ap.add_argument("--db", default=str(ROOT / "data" / "pitcrew.db"))
    ap.add_argument("--roster", default=None,
                    help="default: _board/roster-session-<id>.json")
    ap.add_argument("--min-pairs", type=int, default=MIN_PAIRS)
    ap.add_argument("--min-share", type=float, default=MIN_SHARE)
    ap.add_argument("--apply", action="store_true",
                    help="rename through Store.rename_driver, after a backup")
    args = ap.parse_args(argv)

    db = Path(args.db)
    video = Path(args.video or session_video(db, args.session) or "")
    if not video.is_file():
        raise SystemExit(f"no such recording: {video}")
    roster_path = Path(args.roster or ROOT / "_board"
                       / f"roster-session-{args.session}.json")
    if not roster_path.exists():
        raise SystemExit(f"no replay roster at {roster_path}")
    labels = replay_labels(roster_path)
    if not labels:
        raise SystemExit(f"{roster_path} has no labelled names")
    seed = seed_exemplars(db)
    print(f"{len(labels)} labelled exemplar(s) for "
          f"{len({n for _, n in labels})} name(s); {len(seed)} driver(s) "
          f"seeded from {db}")

    roster = Roster(seed=seed)
    votes = Votes()
    began, at = time.monotonic(), args.start
    while args.end is None or at <= args.end:
        frame = frame_at(video, at)
        if frame is None:
            break
        votes.see(frame, roster, labels)
        at += args.every
        if votes.frames % 100 == 0:
            print(f"  {at:.0f} s of video, {votes.paired} pairing(s)",
                  flush=True)
    print(f"walked {votes.frames} frame(s) in "
          f"{time.monotonic() - began:.0f} s")

    verdicts = decide(votes, min_pairs=args.min_pairs,
                      min_share=args.min_share)
    report(votes, verdicts)
    planned = renames(verdicts)
    print(f"\n{len(planned)} rename(s) proposed:")
    for old, new in planned:
        print(f"  store.rename_driver({old!r}, {new!r})")
    if not args.apply:
        print("\ndry run - nothing written. --apply to make them.")
        return 0
    if not planned:
        return 0
    from pitcrew.store.db import Store

    print(f"backup: {backup(db)}")
    moved = apply(Store(db), planned)
    print(f"renamed {len(planned)} driver(s), {moved} stop(s) came with them")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
