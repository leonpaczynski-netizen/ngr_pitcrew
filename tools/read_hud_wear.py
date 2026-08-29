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

### It is the app's reader, not a second one

**Every part of the transcription lives in `pitcrew/telemetry/hud.py`** - the
calibrated layout, the colour thresholds, the locator that finds the gauge on
a canvas nobody calibrated, and `coherent`, the rule for whether one reading
can follow another on a real set of tyres. This file supplies frames and laps
and nothing else.

That was not true until 26 Aug 2026 and the divergence cost real data. This
tool carried its own copy of a layout calibrated for a 1720x916 OBS canvas,
with no fall-through to the locator that `hud.py` had gained in `55aa96e`, and
its own bar classifier. On the 1920x1080 canvas the driver now broadcasts at,
the copy cropped a rectangle that is not the gauge and reported "no readable
gauge" - and it had no plausibility check at all, so where it did read
something it filed it whatever the numbers said.

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
spacing. Measured 26 Aug 2026, per sample: 0.25-0.45 s to seek and decode one
frame, plus 0.1-0.3 s to find and read the gauge in it.

**The bar's height in pixels is the reading's resolution and the tool now
reports it.** A 30 px bar quantises tyre life at 3.3% a pixel and a 36 px one
at 2.8%, so sampling faster than about 15 s buys nothing the quantisation can
express - a lap at Monza is 5.6%.

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
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import WEAR_HUD_VIDEO, Store          # noqa: E402
from pitcrew.telemetry.hud import (                         # noqa: E402
    CANVAS,
    FRESH_SET_MAX,
    GAUGE_SLACK,
    Reading,
    coherent,
    flat_series_fault,
    read_gauge,
    wear_faults,
)


# **How much of one tyre a single LAP may consume before the reading is a
# misread rather than a lap of wear.**
#
# `hud.GAUGE_MAX_RISE` is 15 points and it is right for the live path, where
# readings are seconds apart. The series written here is a lap apart, and a
# lap is not a small step: measured across every `hud-video` reading in the
# archive on 26 Aug 2026, the largest honest per-lap rises are 16.7, 15.4,
# 15.0 and 14.1 points, all on RS, and all in sessions whose series never goes
# backwards. The live ceiling cuts straight through that population.
#
# The physical bound agrees: the shortest stint ever measured on file is
# 4.9 laps on RS, and `L = 0.85 / w` puts that at 17.3 points of tyre a lap.
# 25 is above everything measured and everything the model allows, and still
# refuses a corner that jumps a quarter of its bar in a lap.
LAP_MAX_RISE = 0.25

# How far a sample's bar height may sit from the run's modal height and still
# be the same instrument. See `one_instrument`.
BAR_HEIGHT_TOLERANCE = 0.25


def _ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:                                        # noqa: BLE001
        return "ffmpeg"


def probe(video: Path) -> tuple[float, tuple[int, int] | None]:
    """(duration in seconds, (width, height)) of a capture."""
    out = subprocess.run([_ffmpeg(), "-hide_banner", "-i", str(video)],
                         capture_output=True, text=True).stderr
    found = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", out)
    if not found:
        raise SystemExit(f"could not read a duration from {video}")
    h, m, s = found.groups()
    size = re.search(r"Video:.*?, (\d{2,5})x(\d{2,5})", out)
    return (int(h) * 3600 + int(m) * 60 + float(s),
            (int(size.group(1)), int(size.group(2))) if size else None)


def _grab(video: Path, at_s: float, out: Path) -> None:
    """One whole frame, because the gauge is not always where it was.

    **The whole canvas, not a crop of it.** The crop this used to take was the
    calibrated rectangle for a 1720x916 canvas, which is not where the gauge
    is on any other - and a crop cannot be searched, so cropping first threw
    away the only thing that could have recovered the reading. A full frame
    costs about 0.1 s more per sample and `read_gauge` still takes the
    calibrated path when the canvas is the calibrated one.
    """
    subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error",
         # **Before -i, deliberately.** After it, ffmpeg decodes every frame up
         # to the seek point and a race takes half an hour instead of minutes.
         "-ss", f"{at_s:.3f}", "-i", str(video), "-frames:v", "1",
         "-q:v", "1", str(out), "-y"],
        check=True, capture_output=True)


def sample(video: Path, *, every_s: float, start_s: float = 0.0,
           limit_s: float | None = None) -> list[tuple[float, Reading]]:
    """Walk the capture and read the gauge. Returns (video_seconds, reading).

    **Bounded to the race, because a capture is usually longer than one.** The
    18 Aug Monza recording ran 3 h 39 m: 53 minutes of replay and then two and
    a half hours of OBS left running over the GT7 menus. Sweeping all of it is
    four times the work and, worse, a menu frame occasionally lands colours in
    the bars' rectangles that classify as a full red bar - which reads as a
    dead tyre and would be recorded as one.
    """
    end = limit_s if limit_s is not None else probe(video)[0]
    rows: list[tuple[float, Reading]] = []
    with tempfile.TemporaryDirectory() as tmp:
        shot = Path(tmp) / "frame.png"
        at = max(0.0, start_s)
        while at < end:
            try:
                _grab(video, at, shot)
                rows.append((at, read_gauge(shot.read_bytes())))
            except subprocess.CalledProcessError:
                pass                     # past the end, or a frame that failed
            at += every_s
    return rows


def series_of(rows: list[tuple[float, Reading]]) -> list[tuple[float, dict]]:
    """The readable samples, as (video seconds, wear)."""
    return [(at, reading.wear) for at, reading in rows if reading.ok]


def one_instrument(rows: list[tuple[float, Reading]], *,
                   tolerance: float = BAR_HEIGHT_TOLERANCE):
    """Keep the samples that read a bar the same size as the rest.

    Returns `(kept, odd, modal height)`.

    **The gauge does not change size, so a reading taken off a bar of another
    size is not a reading of the gauge.** Measured 26 Aug 2026 on the driver's
    own capture, sweeping 7 minutes at 30 s: twelve samples found a 36 px bar
    and one a 35 px one - the seam between the red and the white, a pixel
    either way - while two frames found something else entirely. One was a
    16 px pair of shapes that read RL and RR as 100% worn, and one a 20 px
    pair that read every corner as 0%.

    Both come from the same thing and it is worth naming, because it is the
    residual weakness of finding the gauge rather than knowing where it is:
    **GT7's HUD is translucent.** With the car on a white kerb the panel
    floods, the car icon between the bars classifies as white, and shapes that
    are not bars pass a test that only knows what a bar looks like. Neither
    frame was a missing reading - both produced confident, well-formed,
    completely wrong numbers, and the all-zero one would have been filed as a
    fresh set and cut the stint in two.

    A quarter of the modal height is far wider than the seam (one pixel) and
    far narrower than either misread (44% and 56% out).
    """
    heights = Counter(reading.rows for _, reading in rows
                      if reading.ok and reading.rows)
    if not heights:
        return [], [], None
    modal = heights.most_common(1)[0][0]
    kept, odd = [], []
    for at, reading in rows:
        if not reading.ok:
            continue
        if reading.rows and abs(reading.rows - modal) <= tolerance * modal:
            kept.append((at, reading))
        else:
            odd.append((at, reading))
    return kept, odd, modal


def fresh_set_times(series: list[tuple[float, dict]]) -> list[float]:
    """Video seconds at which a fresh set appeared, one per tyre change.

    **`coherent`'s test, not a worst-corner drop.** A drop on the worst corner
    alone is what the live sampler used to use, and `hud.py` records what it
    cost: a relocated pit-lane gauge read 75% down to 42% on the worst corner,
    was called a fresh set, and threw the stint's series away - three times in
    one session. A tyre change puts EVERY corner back to near zero.
    """
    times = []
    last = None
    for at, wear in series:
        _, fresh, _ = coherent(last, wear)
        if fresh:
            times.append(at)
        last = wear
    return times


def split_stints(series: list[tuple[float, dict]]) -> list[list]:
    """Cut the trace where a fresh set goes on.

    The gauge snapping back to white is the tyre change, and it is a cleaner
    detector than anything the telemetry offers: `laps.tyres_changed` was 0 on
    the Monza stop that demonstrably fitted a new set.
    """
    stints: list[list] = [[]]
    last = None
    for at, wear in series:
        _, fresh, _ = coherent(last, wear)
        if fresh:
            stints.append([])
        stints[-1].append((at, wear))
        last = wear
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


def attach(series, crossings, boundaries=()) -> tuple[dict, list]:
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
    for at, wear in series:
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
        why = None
        if any(opened < b <= cross_at for b in boundaries):
            why = "spans a tyre change"
        elif spans_two_laps(crossings, i):
            why = "is two GT7 laps in one row"
        if why and per_lap.pop(lap["id"], None) is not None:
            lap = dict(lap)
            lap["_skip_why"] = why
            skipped.append(lap)
    return per_lap, skipped


def spans_two_laps(crossings, index: int) -> bool:
    """Did GT7 count more crossings across this row than the app did?

    **A row is not always a lap.** GT7 takes the car over at pit entry and
    the crossing inside that sequence never reaches the app, so a pit row
    covers two of the game's laps: session 88 filed 19 rows for 20 laps,
    its row 5 spanning 256.2 s of a 141.3 s "lap", and `laps_completed`
    stepping 5 -> 7 across it where every other row steps by one.

    The reading attached to such a row is the gauge at the END of the LAST
    of those laps, and the row says it is the end of the first. Filing it
    dates the reading a lap early and, worse, hands the wear model a set
    age short by one - which is the denominator of every rate it computes.

    **GT7's own counter is the witness and it is already in the row.** It is
    recorded on every lap and read by nothing; this is the first thing to
    ask it a question. Silent where the column is null, because a session
    recorded before it existed is unknown, not clean.
    """
    _, lap = crossings[index]
    now = lap.get("laps_completed")
    if now is None:
        return False
    if index == 0:
        return False
    before = crossings[index - 1][1].get("laps_completed")
    if before is None:
        return False
    return now - before > 1


def quantisation(rows: list[tuple[float, Reading]]) -> tuple[int | None, float]:
    """The coarsest bar height read, and the slack that follows from it.

    **The bar height IS the reading's resolution**, and it is not constant:
    30 px on the calibrated canvas, 36 on the 1920x1080 one the driver
    broadcasts at, 8-20 on a VR dashboard. One pixel is 3.3%, 2.8% and up to
    12.5% of tyre life respectively, and the three look identical once they
    are floats in a column.

    The COARSEST is taken, so the plausibility gate below allows a pixel of
    the worst bar in the series rather than of the best one. A gate that
    refuses honest quantisation is worse than no gate: it throws away the
    only measured wear the app has.
    """
    heights = [r.rows for _, r in rows if r.ok and r.rows]
    if not heights:
        return None, GAUGE_SLACK
    return min(heights), 1.0 / min(heights)


def resolve_offset(store, session_id: int, given):
    """The video offset: what was typed, or what the app already wrote down.

    **`--offset` was the thing standing between "run this after every race"
    and "run it when somebody has ten minutes."** The app records the wall
    clock at video second zero when it starts the recording, and every lap
    carries the wall clock at its crossing, so the number is a subtraction -
    exact, rather than the few-seconds-early estimate this used to take.

    An explicit `--offset` still wins: a capture made by hand, or a replay
    recorded from partway through, has no stored zero and the operator is the
    only one who knows it.
    """
    if given is not None:
        return float(given), "given on the command line"
    from pitcrew.race.video_index import offset_for

    derived = offset_for(store, session_id)
    if derived is not None:
        return derived, "derived from the recording the app started"
    # **Zero, and SAID.** A capture made by hand has no stored zero, and zero
    # is the right assumption for a replay trimmed to the race - it is what
    # this defaulted to silently before any of it was derivable. What is new
    # is that it says so: a plausible default standing in for "nobody knows"
    # is this codebase's most repeated defect, and the fix is not to refuse,
    # it is to make the assumption audible.
    return 0.0, ("ASSUMED zero - the app did not start this recording, so "
                 "there is no stored video zero. Pass --offset if the "
                 "capture does not begin at the first crossing")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db")
    ap.add_argument("--session", type=int, required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--every", type=float, default=15.0,
                    help="seconds between samples (default 15)")
    ap.add_argument("--offset", type=float, default=None,
                    help="video seconds at the race's first line crossing. "
                         "**Derived when the app started the recording** - it "
                         "wrote down the wall clock at video second zero, so "
                         "the offset is a subtraction rather than the "
                         "few-seconds-early estimate this used to take. Pass "
                         "it only for a capture made by hand, or a replay "
                         "recorded from partway through")
    ap.add_argument("--apply", action="store_true",
                    help="write the readings; without it, report only")
    args = ap.parse_args()

    store = Store(args.db) if args.db else Store()
    video = Path(args.video)
    if not video.exists():
        raise SystemExit(f"no such capture: {video}")

    # The race window first, so the sweep covers the race and not the two and a
    # half hours of menus a capture can carry after it.
    offset, how = resolve_offset(store, args.session, args.offset)
    print(f"video offset {offset:.2f} s, {how}")
    crossings = _crossings(store, args.session, offset)
    first_cross, last_cross = crossings[0][0], crossings[-1][0]
    lap_s = (last_cross - first_cross) / max(1, len(crossings) - 1)
    start_s, end_s = max(0.0, first_cross - 2 * lap_s), last_cross + lap_s

    _, size = probe(video)
    if size == CANVAS:
        print(f"{video.name} is {size[0]}x{size[1]}, the calibrated canvas")
    elif size:
        print(f"{video.name} is {size[0]}x{size[1]}, not the calibrated "
              f"{CANVAS[0]}x{CANVAS[1]} - the four bars are found in each "
              f"frame instead")
    print(f"sampling every {args.every:g} s "
          f"over {start_s:.0f}-{end_s:.0f} s (the race) ...")
    rows = sample(video, every_s=args.every, start_s=start_s, limit_s=end_s)
    readable = sum(1 for _, r in rows if r.ok)
    print(f"  {len(rows)} samples, {readable} with a readable gauge")
    if not readable:
        why = Counter(r.reason for _, r in rows if r.reason)
        raise SystemExit(
            "no readable gauge in any sample. The reasons given were:\n  "
            + "\n  ".join(f"{n}x {reason}" for reason, n in why.most_common(5)))

    kept, odd, modal = one_instrument(rows)
    for at, reading in odd:
        print(f"  {at:.0f} s: found a {reading.rows} px bar where the run "
              f"reads {modal} px - not the same instrument, so it is not read")
    series = series_of(kept)
    if not series:
        raise SystemExit(
            f"no sample read a bar of a consistent height, so nothing here is "
            f"reliably the gauge (heights seen: "
            + ", ".join(f"{h} px" for h in sorted(
                {r.rows for _, r in rows if r.ok and r.rows})) + ")")

    bar_px, slack = quantisation(kept)
    if bar_px:
        # **Printed before anything is applied, because it is what the numbers
        # below are worth.** A stint's slope over a 36 px bar and the same
        # slope over an 8 px one are not the same claim.
        heights = Counter(r.rows for _, r in kept if r.rows)
        spread = (" (heights read: "
                  + ", ".join(f"{h} px x{n}" for h, n in heights.most_common(4))
                  + ")") if len(heights) > 1 else ""
        print(f"  bar is {bar_px} px at its shortest, so one pixel is "
              f"{100 / bar_px:.1f}% of tyre life{spread}")
    located = sum(1 for _, r in kept if r.located)
    if located:
        # **Said, because it is a different instrument from the one the 0.5%
        # verification was taken on.** A capture on the calibrated canvas can
        # still be located frame by frame - every VR frame is dim, and a dim
        # frame is searched rather than refused - so the canvas size does not
        # answer this and the readings have to.
        print(f"  {located} of {len(kept)} reading(s) came from a gauge that "
              f"was FOUND in the frame, not from the calibrated rectangle - "
              f"looser thresholds, and the bar height above is what they are "
              f"worth")

    stints = split_stints(series)
    print(f"  {len(stints)} stint(s) - the gauge resets to white on a fresh set")
    for i, stint in enumerate(stints, 1):
        first, last = stint[0], stint[-1]
        worst = max(v for v in last[1].values() if v is not None)
        print(f"    stint {i}: {first[0]:.0f}-{last[0]:.0f} s, "
              f"ends at {worst:.2f} on its worst corner")

    per_lap, skipped = attach(series, crossings, fresh_set_times(series))
    print(f"\n  {len(per_lap)} of {len(crossings)} laps carry a reading")
    for lap in skipped:
        print(f"  lap {lap['lap_num']} "
              f"{lap.get('_skip_why', 'is unreadable')}"
              f" - no reading, because the reading and the row would "
              f"not be about the same lap")
    print(f"{'lap':>4} {'video_s':>8} {'fl':>6} {'fr':>6} {'rl':>6} {'rr':>6}")
    ordered = sorted(per_lap.items(), key=lambda kv: kv[1][2]["lap_num"])
    for lap_id, (at, wear, lap) in ordered:
        cell = lambda k: (f"{wear[k]:6.2f}" if wear[k] is not None else "     -")
        print(f"{lap['lap_num']:>4} {at:>8.0f} "
              f"{cell('fl')} {cell('fr')} {cell('rl')} {cell('rr')}")

    # **The gate, and it runs on exactly what would be written.** Not on the
    # sweep - a sample that never becomes a lap reading cannot poison the wear
    # model, and one that does is the whole risk. See `hud.wear_faults`.
    faults = wear_faults([(lap["lap_num"], wear)
                          for _, (_, wear, lap) in ordered],
                         slack=slack, max_rise=LAP_MAX_RISE,
                         span=lambda before, after: after - before)
    # **The ceiling is printed whether or not anything hit it.** CLAUDE.md
    # rule 10: the number setting the bar was invisible for a whole race
    # precisely because it only ever appeared beside a refusal.
    print("")
    print(f"gate: {slack * 100:.1f} points of slack (one pixel of a "
          f"{bar_px or '?'} px bar), {LAP_MAX_RISE * 100:.0f} points of "
          f"wear allowed per lap, and a fresh set allowed "
          f"{FRESH_SET_MAX * 100:.0f} points plus a lap's wear for every "
          f"lap skipped")
    if faults:
        print(f"{len(faults)} step(s) that no tyre could have made:")
        for fault in faults:
            print(f"  lap {fault}")

    # **A series that never moves is not a reading of a tyre.**
    #
    # Every check above asks whether one STEP is possible, and all of them
    # pass trivially on a series that is flat - which is exactly what a
    # false quad produces. Rendered at 2560x1440 the locator returned a set
    # of 16 px fragments reading 0.000 on all four corners in 57 of 60
    # frames, with zero faults, and `--apply` would have filed a whole race
    # of zeros under a source that says they were measured. The bar-height
    # bounds now scale with the canvas so the real gauge can no longer be
    # excluded from candidacy - but **the driver's monitor is 2560x1440**,
    # and no locator is proof against a frame that does not contain the
    # gauge at all.
    #
    # Rule 3, and the cheapest possible test of it: tyres wear. A run whose
    # worst corner ends where it started did not measure one.
    flat = flat_series_fault([(lap["lap_num"], wear)
                              for _, (_, wear, lap) in ordered], slack=slack)
    if flat is not None:
        faults.append(f"whole run: {flat}. Check the capture size on the "
                      f"first line above - the bar should be about one "
                      f"thirtieth of the canvas height.")
        print(f"  {faults[-1]}")

    if not args.apply:
        print("\nreport only - pass --apply to record these against the laps")
        return 0
    if faults:
        # **Refused rather than filed, and CLAUDE.md rule 3 is why.** These
        # readings go into the `laps` table beside the driver's own, under a
        # source that says they were measured. A wear figure that is wrong is
        # indistinguishable downstream from one that is right, and the wear
        # model divides consumed life by laps run - so one impossible step
        # becomes a stint length the strategy engine will plan a race around.
        print("\nrefusing to write: the readings above are not a possible "
              "series on one set of tyres, so at least one of them is not of "
              "the gauge. Nothing has been written. Re-sample with a shorter "
              "--every, check the offset lines the laps up, or check what the "
              "capture is showing at the laps named.")
        return 2

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
