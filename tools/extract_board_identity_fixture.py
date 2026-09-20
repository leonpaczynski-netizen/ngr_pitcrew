"""Pour one race's board rows, with WHO each row really was, into a fixture.

    python tools/extract_board_identity_fixture.py --session 176 \
        --parts <dir> --chunk 0          # then 600, 1200, ... one per command
    python tools/extract_board_identity_fixture.py --session 176 \
        --parts <dir> --merge --drop-seed "Car #76" ... "Car #83"

Writes `pitcrew/tests/fixtures/board_identity_s<session>.npz`: every row the
live reader (`telemetry/roster.read`) finds on the race recording at the live
pit wall's grab rate (one frame every 2 s), as the 64x16 bitmap the roster
compares, with our own row marked - and a TRUE name per row.

### Where the true name comes from, and why not from the roster

A test of the roster scored against the roster's own clusters would pass
whatever the roster did. The truth here is read at NATIVE resolution, where a
name is legible (see the memory note on labelling from the native crop): each
row's ink is taken from a 40 px band - wide enough that a flag centre
jittering by 4 px never cuts a glyph, which the reader's own narrower band
does - cropped to the name, and matched with a +/-2 px shift search against
eight references per driver. The references are
`fixtures/board_identity_s<session>_refs.npz`: native ink crops, each with the
video second and row it came from, picked from clusters whose crops were read
by eye. A row is labelled only where one driver is under 0.35 and the next is
more than 0.15 further off.
Everything else is `-1`, unlabelled: menus, cars mid-reorder, a crew in the
way.

On session 176 that labels 7,939 of 10,597 rows (1,308 frames, one every
2 s) across the 13 cars in the race; twelve random crops per name were
checked by eye and all were the name given.

`--drop-seed` removes drivers minted DURING this race from the seed set, so
the fixture's seeds are the drivers the live wall was seeded with at the
green (the log line at 20:19:15 on 14 Sep 2026: "seeded with 72 known
drivers"). Their bitmaps are as saved at the end of that race, which is the
nearest copy on file.

Read-only against the database. Needs the recording. Each `--chunk` reads
600 s of video at the live grab rate and labels it (about four minutes), so
every command finishes; `--merge` joins the parts in order.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from split_slot_handles import frames, seeds                     # noqa: E402
from pitcrew.telemetry import roster as R                         # noqa: E402
from pitcrew.telemetry.board import flag_ladder, own_row          # noqa: E402

OUT = ROOT / "pitcrew" / "tests" / "fixtures"
BAND = 20
ACCEPT, MARGIN = 0.35, 0.15


def native_name(frame, y: int, name_x: int, right: int, is_own: bool):
    """The name's ink at native resolution from a band wide enough to hold it."""
    strip = frame[max(0, y - BAND):y + BAND, max(0, name_x - 4):right].astype(int)
    ink = R._ink(strip, is_own)
    if ink.sum() < R.NAME_MIN_INK:
        return None
    groups = R._merged(ink.any(axis=0))
    if not groups:
        return None
    x0, x1 = max(groups, key=lambda g: g[1] - g[0])
    if x1 - x0 < 4:
        return None
    body = ink[:, x0:x1 + 1]
    on = np.where(body.any(axis=1))[0]
    if len(on) < 4:
        return None
    return body[on.min():on.max() + 1]


def native_distance(a, b, shift: int = 2) -> float:
    """One minus the best IoU over +/-`shift` px; far-apart widths are 1.0."""
    if abs(a.shape[1] - b.shape[1]) > 8:
        return 1.0
    height = max(a.shape[0], b.shape[0]) + 2 * shift
    width = max(a.shape[1], b.shape[1]) + 2 * shift
    base = np.zeros((height, width), bool)
    base[shift:shift + a.shape[0], shift:shift + a.shape[1]] = a
    best = 0.0
    for dy in range(-shift, shift + 1):
        for dx in range(-shift, shift + 1):
            moved = np.zeros((height, width), bool)
            moved[shift + dy:shift + dy + b.shape[0],
                  shift + dx:shift + dx + b.shape[1]] = b
            union = (base | moved).sum()
            if union:
                best = max(best, (base & moved).sum() / union)
    return 1.0 - best


def read_frame(frame):
    """`[(bits, is_own, native)]` for every row, as the live reader sees it."""
    ladder = flag_ladder(frame)
    board = own_row(frame, ladder=ladder) if ladder else None
    if board is None:
        return []
    rows = R.read(frame, board, ladder)
    if not rows:
        return []
    flag_x0, flag_x1, ys = ladder
    right = max(0, flag_x0 - (flag_x1 - flag_x0 + 1))
    name_x = R.name_column(frame, board, ys, right)
    return [(row.name, row.is_own,
             native_name(frame, row.y, name_x, right, row.is_own))
            for row in rows]


CHUNK_S = 600


def load_refs(path: Path) -> dict:
    data = np.load(path)
    refs: dict[str, list] = {}
    for name, height, width, ink in zip(data["name"], data["height"],
                                        data["width"], data["ink"]):
        size = int(height) * int(width)
        crop = np.unpackbits(ink)[:size].reshape(int(height), int(width))
        refs.setdefault(str(name), []).append(crop.astype(bool))
    return refs


def label_row(native, refs: dict, names: list) -> int:
    if native is None:
        return -1
    scores = sorted((min(native_distance(native, r) for r in refs[n]), k)
                    for k, n in enumerate(names))
    if scores[0][0] < ACCEPT and (
            len(scores) == 1 or scores[1][0] - scores[0][0] > MARGIN):
        return scores[0][1]
    return -1


def chunk(video: Path, start: int, every: int, refs: dict, names: list,
          out: Path) -> int:
    seconds, place, own, bits, label = [], [], [], [], []
    for second, frame in frames(video, float(start), float(CHUNK_S)):
        if second % every:
            continue
        for index, (row_bits, is_own, native) in enumerate(read_frame(frame)):
            seconds.append(second)
            place.append(index + 1)
            own.append(bool(is_own))
            if row_bits is None:
                bits.append(np.zeros(R.NAME_SHAPE[0] * R.NAME_SHAPE[1] // 8,
                                     np.uint8))
                label.append(-2)
            else:
                bits.append(np.packbits(row_bits.ravel()))
                label.append(label_row(native, refs, names))
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, second=np.array(seconds, np.int32),
                        place=np.array(place, np.int8),
                        own=np.array(own, bool),
                        bits=np.array(bits, np.uint8).reshape(len(bits), -1),
                        label=np.array(label, np.int8))
    return len(seconds)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--session", type=int, required=True)
    parser.add_argument("--parts", type=Path, required=True)
    parser.add_argument("--chunk", type=int, metavar="START_S")
    parser.add_argument("--merge", action="store_true")
    parser.add_argument("--drop-seed", nargs="*", default=[])
    parser.add_argument("--db", type=Path, default=ROOT / "data" / "pitcrew.db")
    parser.add_argument("--every", type=int, default=2)
    args = parser.parse_args()
    if (args.chunk is None) == (not args.merge):
        print("give exactly one of --chunk START_S or --merge")
        return 2
    if not args.db.exists():
        print(f"no database at {args.db}")
        return 2

    refs_path = OUT / f"board_identity_s{args.session}_refs.npz"
    refs = load_refs(refs_path)
    names = sorted(refs)
    db = sqlite3.connect(f"file:{args.db.as_posix()}?mode=ro", uri=True)
    try:
        video = Path(db.execute("SELECT video_path FROM sessions WHERE id = ?",
                                (args.session,)).fetchone()[0])
        seed = {k: v for k, v in seeds(db).items()
                if k not in set(args.drop_seed)}
    finally:
        db.close()

    if args.chunk is not None:
        start = args.chunk - args.chunk % CHUNK_S
        part = args.parts / f"part-{args.session}-{start:05d}.npz"
        rows = chunk(video, start, args.every, refs, names, part)
        print(f"{part}: {rows} rows")
        return 0

    parts = sorted(args.parts.glob(f"part-{args.session}-*.npz"))
    if not parts:
        print(f"no parts in {args.parts}")
        return 2
    starts = [int(p.stem.rsplit("-", 1)[1]) for p in parts]
    if starts != list(range(0, CHUNK_S * len(parts), CHUNK_S)):
        print(f"parts are not contiguous from 0: {starts}")
        return 2
    loaded = [np.load(p) for p in parts]
    joined = {key: np.concatenate([d[key] for d in loaded])
              for key in ("second", "place", "own", "bits", "label")}
    path = OUT / f"board_identity_s{args.session}.npz"
    np.savez_compressed(
        path, **joined, names=np.array(names),
        seed_names=np.array(list(seed)),
        seed_bits=np.array([np.packbits(b.ravel()) for b in seed.values()],
                           np.uint8))
    frames_n = len(set(joined["second"].tolist()))
    print(f"{path}: {frames_n} frames, {len(joined['second'])} rows, "
          f"{int((joined['label'] >= 0).sum())} labelled, {len(seed)} seeds")
    return 0


if __name__ == "__main__":
    sys.exit(main())
