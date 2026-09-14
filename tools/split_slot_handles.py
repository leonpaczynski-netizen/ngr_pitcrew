"""Split a gap-reads handle that named a board SLOT back into the cars in it.

    python tools/split_slot_handles.py --session 176 --handles 78 80 82
    python tools/split_slot_handles.py --session 176 --handles 78 80 82 \
        --apply --db "<a copy of pitcrew.db>"
    python tools/split_slot_handles.py --session 176 --all    # every subject

`--cache DIR` keeps the rows read off the recording, 600 s of video per file,
and `--fill-chunk START_S` fills one file and stops, so a whole race can be
read one short command at a time (about two minutes a file here) and a dry
run and its apply read the same rows.

### What went wrong, and why the database alone cannot undo it

Until 15 Sep 2026 `PitWall._neighbour` named the car beside us by looking up
which roster cluster had LAST been seen on the row next to ours - a sticky
table that kept every cluster's last row for the rest of the race. GT7's
board is a window around the player, so our own row sits still while the
field passes through the row above it, and the first cluster ever parked
there answered for everybody after it. At Bathurst (session 176) the handle
"78" filed 329 gap readings; the recording shows nine different drivers on
that row at those moments.

Nothing in `gap_reads` says who was really there: a subject, a gap, a row
index and a clock. **A split made from those columns would be a guess by
position, which is the defect itself.** So this reads the recording: for each
filed reading it takes the frame at that moment and one second either side,
reads the name on the row next to ours with the live reader, and resolves it
with a `Roster` seeded from `drivers` - exactly as tomorrow's race will. A
session with no recording on file is listed and left alone.

### What a reading becomes

* **A named driver** where the roster resolves the row to one (a seeded name,
  `Car #N` handles included - they are the names the live wall uses).
* **`<handle>.<k>`** for a car the archive has no name for; the same `k` is
  the same car wherever it appears in the session, so "78.3" and "82.3" are
  one driver seen on both sides.
* **NULL** where the three frames do not agree, or the row did not read on
  two of them: the owner of that gap is unknown, and unknown is null
  (CLAUDE.md rule 3). A reading is never given the car of a neighbouring
  second on its own.

Nothing is deleted. Every changed row gets an `identity_repairs` row holding
the old subject, the new one, and the evidence (video second, frames read,
the name on each).

`board_positions` is listed too. It files only NAMED drivers
(`PitWall.positions`), so an unnamed slot handle never reaches it; the rows
there are sticky last-seen rows by design and are not rewritten here.

`--apply` needs `--db` and refuses a path that does not exist, so a typo
cannot create an empty database and report success against it. Run it on a
copy first; the live command is printed at the end of a dry run.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from extract_race_comms_fixture import monotonic_offset         # noqa: E402
from pitcrew.telemetry.board import flag_ladder, own_row         # noqa: E402
from pitcrew.telemetry.roster import Roster                      # noqa: E402
from pitcrew.telemetry.roster import read as read_rows           # noqa: E402

DB = ROOT / "data" / "pitcrew.db"
RESOLVED_BY = "slot-split 2026-09-15 (recording)"
W, H = 1920, 1080

# **Frames either side of the reading that must agree.** The reading's moment
# is known to about a third of a second (`monotonic_offset` bounds it from
# both sides on every lap) and the frames are a second apart, so the car in
# the row at the reading is the car on the frames around it - unless a pass
# happened inside those two seconds, which is the case this refuses.
AGREE_SPAN_S = 1
MIN_AGREEING = 2


def _clock(stamp: str) -> float:
    moment = dt.datetime.fromisoformat(stamp)
    return moment.hour * 3600 + moment.minute * 60 + moment.second


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:                                   # pragma: no cover
        return "ffmpeg"


def frames(video: Path, start_s: float, duration_s: float, *, fps: int = 1,
           decoder: str | None = "av1_qsv"):
    """`(second, frame)` at `fps` from `start_s`, whole seconds of the video.

    Hardware AV1 first - measured 8.7x real time against libaom's 2x on this
    machine - and the software decoder where the hardware one yields nothing.
    """
    cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "error"]
    if decoder:
        cmd += ["-c:v", decoder]
    cmd += ["-ss", f"{start_s:.3f}", "-t", f"{duration_s:.3f}", "-i", str(video),
            "-vf", f"fps={fps}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, bufsize=10 ** 8)
    count = 0
    try:
        while True:
            buf = proc.stdout.read(W * H * 3)
            if len(buf) < W * H * 3:
                break
            yield (int(round(start_s + count / fps)),
                   np.frombuffer(buf, dtype=np.uint8).reshape(H, W, 3))
            count += 1
    finally:
        proc.stdout.close()
        proc.wait()
    if count == 0 and decoder:
        yield from frames(video, start_s, duration_s, fps=fps, decoder=None)


def seeds(db) -> dict:
    out = {}
    for name, blob, rows, cols in db.execute(
            "SELECT name, exemplar, rows, cols FROM drivers "
            "WHERE exemplar IS NOT NULL AND rows IS NOT NULL ORDER BY id"):
        wanted = int(rows) * int(cols)
        bits = np.unpackbits(np.frombuffer(blob, dtype=np.uint8))[:wanted]
        if bits.size == wanted:
            out[name] = bits.reshape(int(rows), int(cols)).astype(bool)
    return out


@dataclass
class Board:
    """What one frame said: our row's index and the id on every row."""
    own: int | None
    ids: list


# Seconds of video read per cache chunk. About four minutes of wall time on
# this machine (8.7x hardware decode plus the reader), so each chunk can be
# filled by one command that finishes.
CHUNK_S = 600


def read_chunk(video: Path, start_s: int, duration_s: int) -> dict:
    """`second -> (own row index or None, [bitmap or None per row])`."""
    out: dict[int, tuple] = {}
    for second, frame in frames(video, float(start_s), float(duration_s)):
        ladder = flag_ladder(frame)
        board = own_row(frame, ladder=ladder) if ladder else None
        rows = read_rows(frame, board, ladder) if board is not None else []
        own = next((i for i, row in enumerate(rows) if row.is_own), None)
        out[second] = (own, [row.name for row in rows])
    return out


def _chunk_path(cache: Path, video: Path, start_s: int) -> Path:
    return cache / f"rows-{video.stem.replace(' ', '_')}-{start_s:05d}.npz"


def save_chunk(path: Path, chunk: dict) -> None:
    seconds, owns, counts, bits, readable = [], [], [], [], []
    for second, (own, names) in sorted(chunk.items()):
        seconds.append(second)
        owns.append(-1 if own is None else own)
        counts.append(len(names))
        for name in names:
            readable.append(name is not None)
            bits.append(np.zeros((16, 64), bool) if name is None else name)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, second=np.array(seconds, np.int32),
                        own=np.array(owns, np.int16),
                        count=np.array(counts, np.int16),
                        bits=np.packbits(np.array(bits, bool).reshape(
                            len(bits), -1), axis=1) if bits
                        else np.zeros((0, 128), np.uint8),
                        readable=np.array(readable, bool))


def load_chunk(path: Path) -> dict:
    data = np.load(path)
    out, k = {}, 0
    for second, own, count in zip(data["second"], data["own"], data["count"]):
        names = []
        for _ in range(int(count)):
            names.append(np.unpackbits(data["bits"][k])[:1024]
                         .reshape(16, 64).astype(bool)
                         if data["readable"][k] else None)
            k += 1
        out[int(second)] = (None if own < 0 else int(own), names)
    return out


def rows_of(video: Path, end_s: float, cache: Path | None) -> dict:
    """Every whole second from the start of the capture to `end_s`."""
    out: dict[int, tuple] = {}
    for start in range(0, int(end_s) + 1, CHUNK_S):
        path = _chunk_path(cache, video, start) if cache else None
        if path is not None and path.exists():
            chunk = load_chunk(path)
        else:
            chunk = read_chunk(video, start, CHUNK_S)
            if path is not None:
                save_chunk(path, chunk)
        out.update(chunk)
    return out


def walk(video: Path, start_s: float, end_s: float, roster: Roster,
         cache: Path | None = None) -> dict:
    """Every whole second up to `end_s`, resolved in order through `roster`."""
    boards: dict[int, Board] = {}
    for second, (own, names) in sorted(rows_of(video, end_s, cache).items()):
        if second < start_s:
            continue
        if not names:
            boards[second] = Board(None, [])
            continue
        boards[second] = Board(own, roster.see_frame(names))
    return boards


@dataclass
class Verdict:
    read_id: int
    old: str
    new: str | None
    reason: str
    lap: int | None = None
    video_s: float = 0.0


@dataclass
class SessionPlan:
    session: int
    handles: list
    verdicts: list = field(default_factory=list)
    skipped: str | None = None
    board_positions: int = 0


def resolve(read, boards: dict, roster: Roster, labels: dict,
            handle_of: dict) -> tuple[str | None, str]:
    """The car on the row beside ours around this reading, or `None` and why."""
    rid, handle, side, video_s = read
    step = -1 if side == "ahead" else 1
    centre = int(round(video_s))
    seen = []
    for second in range(centre - AGREE_SPAN_S, centre + AGREE_SPAN_S + 1):
        board = boards.get(second)
        if board is None or board.own is None:
            seen.append((second, None))
            continue
        j = board.own + step
        who = board.ids[j] if 0 <= j < len(board.ids) else None
        # **Through the merges made since.** A board stores the id its frame
        # resolved to; two clusters of one driver folded together later are
        # the same car, and comparing the raw ids called that a pass.
        seen.append((second, None if who is None else roster._resolve(who)))
    ids = [who for _, who in seen if who is not None]
    if len(set(ids)) > 1:
        return None, ("the row beside ours changed within "
                      f"{AGREE_SPAN_S} s of the reading: "
                      + ", ".join(f"{s}s={_named(w, roster)}" for s, w in seen))
    if len(ids) < MIN_AGREEING:
        return None, (f"the row beside ours read on {len(ids)} of "
                      f"{len(seen)} frames around the reading")
    name = _label(ids[0], roster, labels, handle, handle_of)
    return name, (f"video {video_s:.1f} s, row {side} of ours read as {name} "
                  f"on {len(ids)} of {len(seen)} frames")


def _named(driver, roster) -> str:
    """For a reason string only: never assigns a `<handle>.<k>` label."""
    if driver is None:
        return "unread"
    return roster.name_of(driver) or f"cluster {driver}"


def _label(driver, roster, labels, handle, handle_of):
    if driver is None:
        return "unread"
    name = roster.name_of(driver)
    if name:
        return name
    if driver not in labels:
        labels[driver] = len(labels) + 1
        handle_of[driver] = handle
    return f"{handle_of[driver]}.{labels[driver]}"


def plan_session(db, sid: int, handles: list | None, video: Path | None,
                 cache: Path | None = None) -> SessionPlan:
    if handles is None:
        # `--all`: every subject filed for the session, commonest first. The
        # sticky lookup was not particular to unnamed clusters - a NAMED
        # driver's readings went through it too.
        handles = [row[0] for row in db.execute(
            "SELECT subject FROM gap_reads WHERE session_id = ? AND subject "
            "IS NOT NULL GROUP BY subject ORDER BY COUNT(*) DESC, subject",
            (sid,))]
        if not handles:
            return SessionPlan(session=sid, handles=[],
                               skipped="no gap readings with a subject")
    plan = SessionPlan(session=sid, handles=list(handles))
    marks = ",".join("?" * len(handles))
    plan.board_positions = db.execute(
        f"SELECT COUNT(*) FROM board_positions WHERE session_id = ? "
        f"AND driver IN ({marks})", (sid, *handles)).fetchone()[0]
    reads = db.execute(
        f"SELECT id, subject, side, at_s, lap FROM gap_reads "
        f"WHERE session_id = ? AND subject IN ({marks}) ORDER BY at_s",
        (sid, *handles)).fetchall()
    if not reads:
        plan.skipped = "no gap readings under these handles"
        return plan
    row = db.execute("SELECT video_path, video_started_at FROM sessions "
                     "WHERE id = ?", (sid,)).fetchone()
    path = video or (Path(row[0]) if row and row[0] else None)
    if path is None or not path.exists() or not (row and row[1]):
        plan.skipped = (f"no recording on file ({path}) - {len(reads)} "
                        f"readings left as they are; the database alone "
                        f"cannot say whose they were")
        return plan
    offset = monotonic_offset(db, sid)[0]
    zero = _clock(row[1])
    placed = [(rid, subject, side, at_s + offset - zero, lap)
              for rid, subject, side, at_s, lap in reads]
    last = max(p[3] for p in placed) + AGREE_SPAN_S + 2
    roster = Roster(seed=seeds(db))
    # **From the start of the capture**, not from the first reading: the
    # roster founds its clusters in the order the race showed them, which is
    # what the live wall did.
    boards = walk(path, 0.0, last, roster, cache)
    labels: dict = {}
    handle_of: dict = {}
    for rid, subject, side, video_s, lap in placed:
        new, reason = resolve((rid, subject, side, video_s), boards, roster,
                              labels, handle_of)
        plan.verdicts.append(Verdict(rid, subject, new, reason, lap, video_s))
    return plan


def _ranges(ids: list) -> str:
    ids = sorted(ids)
    out, start, prev = [], None, None
    for i in ids:
        if start is None:
            start = prev = i
        elif i == prev + 1:
            prev = i
        else:
            out.append(f"{start}-{prev}" if prev != start else str(start))
            start = prev = i
    if start is not None:
        out.append(f"{start}-{prev}" if prev != start else str(start))
    return ",".join(out)


def report(plan: SessionPlan) -> None:
    print(f"session {plan.session}, handles {' '.join(plan.handles)}")
    print(f"  board_positions rows under these handles: {plan.board_positions}"
          " (none move)")
    if plan.skipped:
        print(f"  skipped: {plan.skipped}")
        return
    by_handle = collections.defaultdict(list)
    for v in plan.verdicts:
        by_handle[v.old].append(v)
    for handle in plan.handles:
        vs = by_handle.get(handle, [])
        if not vs:
            continue
        kept = sum(1 for v in vs if v.new == v.old)
        groups = collections.defaultdict(list)
        for v in vs:
            groups[v.new].append(v)
        print(f"  '{handle}': {len(vs)} gap readings -> "
              f"{len([k for k in groups if k is not None])} cars, "
              f"{len(groups.get(None, []))} unknown, {kept} unchanged")
        for new, items in sorted(groups.items(),
                                 key=lambda kv: -len(kv[1])):
            laps = sorted({v.lap for v in items if v.lap is not None})
            span = (f"laps {laps[0]}-{laps[-1]}" if laps else "no lap")
            print(f"    {str(new) if new is not None else 'NULL (unknown)':22s}"
                  f" {len(items):4d}  {span}, video "
                  f"{min(v.video_s for v in items):.0f}-"
                  f"{max(v.video_s for v in items):.0f} s  gap_reads ids "
                  f"{_ranges([v.read_id for v in items])}")


def apply(db_path: Path, plans: list) -> int:
    """Rewrite the subjects and log each one. One transaction; all or none."""
    db = sqlite3.connect(str(db_path))
    now = dt.datetime.now().isoformat(timespec="seconds")
    changed = 0
    try:
        with db:
            for plan in plans:
                for v in plan.verdicts:
                    if v.new == v.old:
                        continue
                    cur = db.execute(
                        "UPDATE gap_reads SET subject = ? WHERE id = ? "
                        "AND session_id = ? AND subject = ?",
                        (v.new, v.read_id, plan.session, v.old))
                    if cur.rowcount != 1:
                        raise RuntimeError(
                            f"gap_reads {v.read_id} is no longer '{v.old}' - "
                            f"the database moved since the dry run; nothing "
                            f"was written")
                    db.execute(
                        "INSERT INTO identity_repairs (table_name, row_id, "
                        "field, old_value, new_value, reason, resolved_by, "
                        "resolved_at) VALUES ('gap_reads', ?, 'subject', ?, "
                        "?, ?, ?, ?)",
                        (str(v.read_id), v.old, v.new,
                         f"session {plan.session}: '{v.old}' named a board "
                         f"slot, not a car (sticky-row neighbour lookup). "
                         + v.reason, RESOLVED_BY, now))
                    changed += 1
    finally:
        db.close()
    return changed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--session", type=int, action="append", required=True)
    which = parser.add_mutually_exclusive_group(required=True)
    which.add_argument("--handles", nargs="+")
    which.add_argument("--all", action="store_true",
                       help="every subject filed for the session")
    parser.add_argument("--video", type=Path,
                        help="override the session's recording (one session)")
    parser.add_argument("--db", type=Path,
                        help="database to read, and with --apply to write")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--cache", type=Path,
                        help="keep the board rows read off the recording here, "
                             f"{CHUNK_S} s of video per file, and reuse them")
    parser.add_argument("--fill-chunk", type=int, metavar="START_S",
                        help="with --cache and one --session: read the chunk "
                             "starting at this video second into the cache "
                             "and stop")
    args = parser.parse_args(argv)

    if args.apply and args.db is None:
        print("--apply needs --db PATH: name the database it will write")
        return 2
    db_path = args.db or DB
    if not db_path.exists():
        print(f"no database at {db_path} - refusing rather than creating one")
        return 2
    if args.video is not None and len(args.session) != 1:
        print("--video names one recording; give one --session with it")
        return 2

    db = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    if args.fill_chunk is not None:
        if args.cache is None or len(args.session) != 1:
            print("--fill-chunk needs --cache and one --session")
            return 2
        row = db.execute("SELECT video_path FROM sessions WHERE id = ?",
                         (args.session[0],)).fetchone()
        db.close()
        video = args.video or (Path(row[0]) if row and row[0] else None)
        if video is None or not video.exists():
            print(f"no recording on file ({video})")
            return 2
        start = args.fill_chunk - args.fill_chunk % CHUNK_S
        path = _chunk_path(args.cache, video, start)
        chunk = read_chunk(video, start, CHUNK_S)
        save_chunk(path, chunk)
        print(f"{path}: {len(chunk)} frames, "
              f"{sum(1 for own, _ in chunk.values() if own is not None)} "
              f"with our row")
        return 0
    try:
        plans = [plan_session(db, sid, None if args.all else args.handles,
                              args.video, args.cache)
                 for sid in args.session]
    finally:
        db.close()
    for plan in plans:
        report(plan)

    if not args.apply:
        sessions = " ".join(f"--session {s}" for s in args.session)
        print("\ndry run - nothing written. To apply:")
        chosen = ("--all" if args.all else "--handles " + " ".join(
            f'"{h}"' if " " in h or "#" in h else h for h in args.handles))
        print(f'  python tools/split_slot_handles.py {sessions} {chosen} '
              f'--apply --db "{db_path}"')
        return 0
    changed = apply(db_path, plans)
    print(f"\napplied: {changed} gap_reads subjects rewritten in {db_path}, "
          f"each logged in identity_repairs as '{RESOLVED_BY}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
