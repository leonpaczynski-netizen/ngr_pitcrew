"""Read the tyre-wear gauge off an OBS capture and record it against the laps.

    python tools/read_hud_wear.py --session 52 --video "C:/Users/.../race.mp4"
    python tools/read_hud_wear.py --session 52 --video ... --apply

**GT7 broadcasts no tyre wear channel in any packet format.** CLAUDE.md §3.3
calls that the single most consequential fact in the document, and the app's
answer has been to model wear and ask the driver to corroborate it from the
in-game gauge. He reads it once or twice a stint, in a moving car, and on the
Monza race of 18 Aug 2026 he read it zero times - so the race that mattered
most fed the wear model nothing at all.

**The gauge is on the screen for the whole race, and OBS is already recording
it.** This reads the same instrument he reads, from the capture, as often as
the video is sampled. It is not a model and it is not derived: it is the
game's own wear readout, transcribed.

### What the gauge looks like and how it is read

Four vertical bars flank the car icon in the HUD's bottom-left cluster. Each
fills RED from the top as the tyre wears and the remainder stays white, so

    wear = red rows / (red rows + white rows)

and the bar resets to fully white the moment a fresh set goes on - which is
also how a tyre change is detected here, and it is a far better detector than
the temperature convergence the app uses elsewhere.

### What it costs and why the sampling is sparse

A sequential decode of a 53-minute AV1 capture takes about half an hour;
ffmpeg fast seek (`-ss` BEFORE `-i`) takes about two minutes at 30-second
spacing. The gauge is 30 pixels tall - one pixel is 3.3% of tyre life, and a
lap at Monza is 5.6% - so sampling faster than about 15 s buys nothing the
quantisation can express.

### The accuracy this was verified at

Session 52, both stints, fitted through the origin: 0.0558 and 0.0561 per lap
on the worst corner. Two independent sets, 0.5% apart. The app's model for the
same tyre said 0.04412.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import WEAR_HUD_VIDEO, Store          # noqa: E402

# The HUD cluster's position is fixed to the capture, not to the game, so the
# bars are located by geometry once and checked by the fresh-tyre frame. These
# are for a 1720x916 OBS window capture; `--probe` re-finds them on any other.
LAYOUT_1720x916 = {
    "fl": (339, 348, 800, 829),
    "rl": (339, 348, 846, 875),
    "fr": (411, 420, 800, 829),
    "rr": (411, 420, 846, 875),
}

# A bar reads red where the channel separation is unmistakable, and white where
# every channel is high. Anything else - the dark HUD backing, a bloom from the
# scenery behind a translucent panel - is neither, and a bar that cannot show
# at least this many classified rows is not read at all rather than guessed.
MIN_CLASSIFIED_ROWS = 20

# A drop this large between consecutive samples is a fresh set, not wear going
# backwards. Wear is monotonic within a stint; the only thing that resets it is
# a tyre change.
FRESH_SET_DROP = 0.25


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:                                        # noqa: BLE001
        return "ffmpeg"


def _duration_s(video: Path) -> float:
    out = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(video)],
                         capture_output=True, text=True).stderr
    found = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", out)
    if not found:
        raise SystemExit(f"could not read a duration from {video}")
    h, m, s = found.groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def _grab(video: Path, at_s: float, out: Path, layout: dict) -> None:
    xs = [v[0] for v in layout.values()] + [v[1] for v in layout.values()]
    ys = [v[2] for v in layout.values()] + [v[3] for v in layout.values()]
    x0, y0 = min(xs), min(ys)
    w, h = max(xs) - x0 + 1, max(ys) - y0 + 1
    subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error",
         # **Before -i, deliberately.** After it, ffmpeg decodes every frame up
         # to the seek point and a race takes half an hour instead of minutes.
         "-ss", f"{at_s:.3f}", "-i", str(video), "-frames:v", "1",
         "-vf", f"crop={w}:{h}:{x0}:{y0}", "-q:v", "1", str(out), "-y"],
        check=True, capture_output=True)


def _read_bars(path: Path, layout: dict) -> dict:
    import numpy as np
    from PIL import Image

    xs = [v[0] for v in layout.values()]
    ys = [v[2] for v in layout.values()]
    ox, oy = min(xs), min(ys)
    frame = np.array(Image.open(path).convert("RGB")).astype(int)
    out = {}
    for corner, (x0, x1, y0, y1) in layout.items():
        bar = frame[y0 - oy:y1 - oy + 1, x0 - ox:x1 - ox + 1]
        r, g, b = bar[..., 0], bar[..., 1], bar[..., 2]
        red = (r > 110) & (r - g > 55) & (r - b > 55)
        white = (r > 150) & (g > 150) & (b > 150)
        n_red = int((red.mean(axis=1) > 0.5).sum())
        n_white = int((white.mean(axis=1) > 0.5).sum())
        total = n_red + n_white
        out[corner] = n_red / total if total >= MIN_CLASSIFIED_ROWS else None
    return out


def sample(video: Path, *, every_s: float, layout: dict,
           start_s: float = 0.0,
           limit_s: float | None = None) -> list[tuple[float, dict]]:
    """Walk the capture and read the gauge. Returns (video_seconds, wear).

    **Bounded to the race, because a capture is usually longer than one.** The
    18 Aug Monza recording ran 3 h 39 m: 53 minutes of replay and then two and
    a half hours of OBS left running over the GT7 menus. Sweeping all of it is
    four times the work and, worse, a menu frame occasionally lands colours in
    the bars' rectangles that classify as a full red bar - which reads as a
    dead tyre and would be recorded as one.
    """
    end = limit_s if limit_s is not None else _duration_s(video)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        shot = Path(tmp) / "bars.png"
        at = max(0.0, start_s)
        while at < end:
            try:
                _grab(video, at, shot, layout)
                rows.append((at, _read_bars(shot, layout)))
            except subprocess.CalledProcessError:
                pass                     # past the end, or a frame that failed
            at += every_s
    return rows


def fresh_set_times(rows: list[tuple[float, dict]]) -> list[float]:
    """Video seconds at which a fresh set appeared, one per tyre change."""
    times, last = [], None
    for at, wear in rows:
        worst = max((v for v in wear.values() if v is not None), default=None)
        if worst is None:
            continue
        if last is not None and last - worst > FRESH_SET_DROP:
            times.append(at)
        last = worst
    return times


def split_stints(rows: list[tuple[float, dict]]) -> list[list]:
    """Cut the trace where a fresh set goes on.

    The gauge snapping back to white is the tyre change, and it is a cleaner
    detector than anything the telemetry offers: `laps.tyres_changed` was 0 on
    the Monza stop that demonstrably fitted a new set.
    """
    stints: list[list] = [[]]
    last = None
    for at, wear in rows:
        worst = max((v for v in wear.values() if v is not None), default=None)
        if worst is None:
            continue
        if last is not None and last - worst > FRESH_SET_DROP:
            stints.append([])
        stints[-1].append((at, wear))
        last = worst
    return [s for s in stints if len(s) > 1]


def _crossings(store: Store, session_id: int, offset_s: float) -> list:
    """Video seconds at each recorded line crossing.

    `recorded_at` is a real wall clock stamped at each crossing, so the shape
    of the race is exact and only its zero point has to be supplied: `offset_s`
    is where the green flag falls in the capture. The zero is taken as lap 1's
    crossing less lap 1's own time, which ignores the standing start and is
    therefore a few seconds early - smaller than one sample interval, and it
    moves every lap equally rather than accumulating.
    """
    laps = store.list_laps(session_id)
    if not laps:
        raise SystemExit(f"session {session_id} has no laps")
    first = dt.datetime.fromisoformat(laps[0]["recorded_at"])
    start = first - dt.timedelta(milliseconds=laps[0]["lap_time_ms"])
    return [((dt.datetime.fromisoformat(r["recorded_at"]) - start
              ).total_seconds() + offset_s, r) for r in laps]


def attach(rows, crossings, boundaries=()) -> tuple[dict, list]:
    """One reading per lap: the last sample before that lap's crossing.

    The last, not the nearest: the gauge at the line is what that lap left the
    tyre at, and a sample taken after the crossing belongs to the next lap.

    **A lap that spans a tyre change gets no reading**, and that is the whole
    reason `boundaries` is here. On the Monza stop the last sample before the
    lap-16 crossing sat on the FRESH set, so the naive answer was "3% worn
    after 16 laps" - and the wear model divides consumed life by laps run, so
    that one row would have told it the tyre lasts five hundred laps. The
    in-lap and the out-lap describe two different sets and neither is what the
    lap row means, so it is skipped and reported rather than guessed.

    Returns the readings and the laps deliberately left without one.
    """
    per_lap = {}
    for at, wear in rows:
        for cross_at, lap in crossings:
            if at <= cross_at:
                held = per_lap.get(lap["id"])
                if held is None or held[0] < at:
                    per_lap[lap["id"]] = (at, wear, lap)
                break

    skipped = []
    starts = [c[0] for c in crossings]
    for i, (cross_at, lap) in enumerate(crossings):
        opened = starts[i - 1] if i else float("-inf")
        if any(opened < b <= cross_at for b in boundaries):
            if per_lap.pop(lap["id"], None) is not None:
                skipped.append(lap)
    return per_lap, skipped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db")
    ap.add_argument("--session", type=int, required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--every", type=float, default=15.0,
                    help="seconds between samples (default 15)")
    ap.add_argument("--offset", type=float, default=0.0,
                    help="video seconds at the race's first line crossing "
                         "minus the app's own; a replay recorded from partway "
                         "through needs one")
    ap.add_argument("--apply", action="store_true",
                    help="write the readings; without it, report only")
    args = ap.parse_args()

    store = Store(args.db) if args.db else Store()
    video = Path(args.video)
    if not video.exists():
        raise SystemExit(f"no such capture: {video}")

    # The race window first, so the sweep covers the race and not the two and a
    # half hours of menus a capture can carry after it.
    crossings = _crossings(store, args.session, args.offset)
    first_cross, last_cross = crossings[0][0], crossings[-1][0]
    lap_s = (last_cross - first_cross) / max(1, len(crossings) - 1)
    start_s, end_s = max(0.0, first_cross - 2 * lap_s), last_cross + lap_s

    print(f"sampling {video.name} every {args.every:g} s "
          f"over {start_s:.0f}-{end_s:.0f} s (the race) ...")
    rows = sample(video, every_s=args.every, layout=LAYOUT_1720x916,
                  start_s=start_s, limit_s=end_s)
    usable = [r for r in rows if any(v is not None for v in r[1].values())]
    print(f"  {len(rows)} samples, {len(usable)} with a readable gauge")
    if not usable:
        raise SystemExit(
            "no readable gauge - the HUD is not where this layout expects it. "
            "Check the capture resolution against LAYOUT_1720x916.")

    stints = split_stints(usable)
    print(f"  {len(stints)} stint(s) - the gauge resets to white on a fresh set")
    for i, stint in enumerate(stints, 1):
        first, last = stint[0], stint[-1]
        worst = max(v for v in last[1].values() if v is not None)
        print(f"    stint {i}: {first[0]:.0f}-{last[0]:.0f} s, "
              f"ends at {worst:.2f} on its worst corner")

    per_lap, skipped = attach(usable, crossings, fresh_set_times(usable))
    print(f"\n  {len(per_lap)} of {len(crossings)} laps carry a reading")
    for lap in skipped:
        print(f"  lap {lap['lap_num']} spans a tyre change - no reading, "
              f"because the in-lap and the out-lap are different sets")
    print(f"{'lap':>4} {'video_s':>8} {'fl':>6} {'fr':>6} {'rl':>6} {'rr':>6}")
    for lap_id, (at, wear, lap) in sorted(
            per_lap.items(), key=lambda kv: kv[1][2]["lap_num"]):
        cell = lambda k: (f"{wear[k]:6.2f}" if wear[k] is not None else "     -")
        print(f"{lap['lap_num']:>4} {at:>8.0f} "
              f"{cell('fl')} {cell('fr')} {cell('rl')} {cell('rr')}")

    if not args.apply:
        print("\nreport only - pass --apply to record these against the laps")
        return 0

    for lap_id, (_, wear, _) in per_lap.items():
        store.set_lap_wear(lap_id, wear["fl"], wear["fr"], wear["rl"],
                           wear["rr"], source=WEAR_HUD_VIDEO)
    # Read back once, not once per lap: `set_lap_wear` declines to overwrite a
    # reading of his own, and the only way to know which it kept is to look.
    after = {r["id"]: r for r in store.list_laps(args.session)}
    written = sum(1 for lap_id in per_lap
                  if after[lap_id]["wear_source"] == WEAR_HUD_VIDEO)
    held = len(per_lap) - written
    print(f"\nwrote {written} reading(s) as '{WEAR_HUD_VIDEO}'")
    if held:
        print(f"kept {held} of his own - a driver reading is never overwritten "
              f"by a video one; where they disagree the disagreement is the "
              f"finding")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
