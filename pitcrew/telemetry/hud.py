"""Reading GT7's tyre-wear gauge off the OBS capture, live, once a lap.

**GT7 broadcasts no tyre wear channel in any packet format.** `CLAUDE.md` §3.3
calls that the single most consequential fact in the document, and the app's
answer has been to model wear and ask the driver to corroborate it from the
in-game gauge. He reads it once or twice a stint at best - across five sessions
running, including the two that mattered most, he read it zero times.

**The gauge is on screen for the whole race and OBS is already pointed at it.**
`tools/read_hud_wear.py` proved the transcription against a recorded file and
was verified to 0.5% across two independent stints. This is the same reading,
taken at each lap crossing instead of afterwards.

### What was measured before this was written

On 21 Aug 2026, against the live capture:

* **Round trip 520 ms, and about 537 ms of OBS CPU per screenshot.** At one per
  90-second lap that is **0.6% of one core**, which is affordable. At one per
  second it is 51% of a core, which is not - so this samples on the crossing and
  nowhere else.
* **The canvas is 1720x916, exactly the geometry `LAYOUT_1720x916` was
  calibrated on.** Screenshot the SCENE, not the `PS5` source: the scene renders
  at canvas resolution, the source at the card's own, and every calibrated
  constant would need re-probing.
* **A 1720x916 PNG is about 2 MB and `websockets` caps frames at 1 MB.** Left at
  the default it does not truncate, it closes the socket with a 1009 - which
  mid-race reads as "OBS went away" rather than "the frame was large".
* **A paused frame is dimmed and desaturated by about 45%**: every bar peaks at
  137 where the reader needs 150 for white and 110 for red, so all four read
  null. That is the correct refusal, and the rule it gives is
  **detect the dim and skip the frame - never relax the thresholds to meet it.**
  Relaxing them lets a dimmed frame produce a number, and a wrong wear figure is
  far worse than a missing one.

### What this deliberately is not

**It never touches the race path.** Every grab happens on a worker thread, the
queue is one deep, and any failure at all - OBS shut, socket closed, canvas the
wrong size, gauge unreadable - produces a logged reason and nothing else. A
perception layer that can stall a lap handler is worse than no perception layer.

**In VR it does not work yet, and it says so rather than guessing.** GT7 draws
its HUD on the car's dashboard in 3D there, so the gauge moves with head
position - measured at roughly 200 px of drift - and a fixed rectangle tracks
nothing. The flat-screen path is proven; the VR locator is separate work.

**Measured in VR, 23 Aug 2026:** 22 crossings, 6 readings, and the 16 refusals
all peaked at exactly 81 in blocks - which is the driver looking away, not a
broken capture. `locate_gauge` is tried on every dim frame from `ObsSource` and
found nothing on those 16. The lever that actually helps here is
**`hud_sample_interval_s`**: at one grab every two seconds a 40-minute race
offers about 1,200 chances instead of 22, and only a handful need to land while
he is looking forward. **Note the interaction** - `ScreenSource` returns a
`CropFrame`, and `read_gauge` skips the locator on a crop because a crop is a
bet that the gauge did not move. So the cheap capture path and the VR locator
are mutually exclusive as things stand, and in VR the OBS source is the one
that can still find a moved gauge.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import queue
import threading
import time
from dataclasses import dataclass

from pitcrew.diagnostics import log
from pitcrew.race.brief import (
    GAUGE_NOT_IN_FRAME,
    GAUGE_UNREADABLE,
    blind_note,
)

# **`log` RETURNS a logger; it does not take a message.** Every diagnostic
# in this module used to call `log(f"hud-wear: ...")`, which built a logger
# NAMED after the message and emitted nothing - so the sampler could fail on
# every sample of every lap and say so eight different ways, in silence.
# That is the failure mode CLAUDE.md 7 exists to forbid: a capture that
# degrades quietly instead of loudly. Bind it once, here.
_log = log("hud")

# The calibrated gauge, in canvas pixels. Four vertical bars flanking the car
# icon in the HUD's bottom-left cluster; each fills red from the top as the
# tyre wears and the remainder stays white.
LAYOUT_1720x916 = {
    "fl": (339, 348, 800, 829),
    "rl": (339, 348, 846, 875),
    "fr": (411, 420, 800, 829),
    "rr": (411, 420, 846, 875),
}
CANVAS = (1720, 916)

# **What `snap_projector` sizes the projector TO, and it is deliberately not
# `CANVAS`.** `CANVAS` is the geometry `LAYOUT_1720x916` was calibrated for and
# it is still the fast path in `read_gauge`. It is the wrong thing to SIZE a
# projector to, for two reasons measured on this driver's own captures:
#
# * **The PS5 outputs 1080p.** He asked in August why the capture had to be
#   1720x916 when the console outputs 1080p and `55aa96e` agreed with him -
#   *"he is right that it should not"* - so the reader gained the locator and
#   has read 1920x1080 ever since. Snapping the projector to 1720x916 forces
#   OBS to scale a 1920x1080 canvas down into it, and a scaled canvas moves
#   every calibrated pixel: the fast path is then wrong AND the locator is
#   working on a downscaled image.
# * **1920x1080 is the BETTER instrument, not a fallback.** The bars there are
#   36 px against 30 on the calibrated flat HUD, so one pixel is 2.8% of tyre
#   life rather than 3.3%.
#
# On 3 Sep 2026 the driver had the projector open all night and sized it from
# the app; the race read nothing and the offline pass over the same capture
# read 64 of 64. Sizing it to the calibrated canvas was the difference.
SNAP_CANVAS = (1920, 1080)

# A bar reads red where the channel separation is unmistakable and white where
# every channel is high. Anything else - the dark HUD backing, bloom from
# scenery behind a translucent panel - is neither.
RED_MIN, RED_SEPARATION, WHITE_MIN = 110, 55, 150
# A bar that cannot show at least this many classified rows is not read at all
# rather than guessed. The bar is 30 px tall.
MIN_CLASSIFIED_ROWS = 20
# Below this peak the frame is dimmed - a pause menu, a transition, a replay
# overlay - and no threshold in it means what it usually means. Measured: a
# paused frame peaks at 137, a live one at 255.
LIVE_PEAK = 165

# Frames larger than the library's default cap; see the module docstring.
MAX_FRAME_BYTES = 16 * 1024 * 1024
CONNECT_TIMEOUT_S = 4.0
# Consecutive failures before the sampler stands down for the session. It says
# so once and stops trying: an error repeated every lap is noise, and by then
# something needs a human anyway.
MAX_CONSECUTIVE_FAILURES = 5
# **Consecutive unreadable crossings before the driver is told.** He raced
# 22 laps at Road Atlanta on 23 Aug 2026 and the gauge answered six of them;
# nothing said so at the time, and the wear plan ran the whole race on a
# practice figure while the instrument that was meant to replace it sat blind.
# CLAUDE.md's rule for the engineer is that silence must announce itself -
# "I cannot see them" is a thing he can act on, and no message is not.
BLIND_CROSSINGS_BEFORE_SAYING = 3
# How many identical dim peaks in a row mean the rectangle is not looking at
# the game at all. A dimmed game frame varies between grabs - a pause menu
# behind a moving scene, a transition part-way through. **Sixteen refusals in
# that race reported a peak of exactly 81, every one of them**, in two blocks
# either side of readable stretches. Identical to the unit over forty minutes
# is not a dim frame, it is the same pixels.
IDENTICAL_PEAKS_MEAN_STATIC = 3
# **How many samples in a row may produce NOTHING before the reader accepts
# that it cannot see the gauge this session.**
#
# `MAX_CONSECUTIVE_FAILURES` covers the source dying - OBS shut, the projector
# closed - and nothing covered the case where the source is perfectly healthy
# and the gauge simply is not in what it returns. That is the VR case, and it
# is now the normal case: he races in VR, where GT7 draws the HUD on the car's
# dashboard in 3D. At Fuji the reader made **553 attempts after the green and
# accepted none**, writing a warning for almost every one - half a thousand log
# lines saying the same thing, and a driver who had been told in the brief that
# the gauge was being watched.
#
# **Any accepted reading resets it, and that distinction is the whole design.**
# In VR the gauge is intermittent rather than absent - at Road Atlanta it
# answered 6 crossings of 22, because a sample only needs the driver to be
# looking forward. Standing down on a count that a partial success could not
# clear would throw those six away. Zero accepts across this many attempts is a
# different claim: the gauge is not coming.
#
# Sixty, against the 2-10 s intervals raced, is ten minutes and several laps -
# far past any occlusion a long left-hander or a menu can produce.
BLIND_SAMPLES_BEFORE_STANDING_DOWN = 60
# A drop this large between readings is a fresh set, not wear going
# backwards. Wear is monotonic within a stint and the only thing that
# resets it is a tyre change - the gauge snapping back to white is a
# cleaner detector than anything the telemetry offers.
FRESH_SET_DROP = 0.25
# **Wear is monotonic on EVERY corner, not just the worst one, and that is
# what says whether a reading is of the gauge at all.**
#
# 24 Aug 2026, Monza: the driver reported that GT7 moves the tyre gauge to
# the bottom-left of the screen while he is in the pits. The calibrated
# rectangle then reads whatever the HUD put in its place, and the numbers
# that come back are plausible one at a time - the pit lap filed
# FL 45 / FR 45 / RL 32 / RR 50 against a previous FL 63 / FR 37 / RL 68 /
# RR 55. Three corners fell and one rose. **No tyre does that**, and the
# old worst-corner test could not see it: it read a 75%-to-42% drop on the
# worst corner, called a fresh set, and threw the stint's series away. It
# did so three times in one session.
#
# So a reading is compared corner by corner and accepted only if it is
# physically possible: every shared corner steady or rising, or every one
# of them dropping onto a set that reads near zero. Anything else is not a
# reading of the gauge and is refused rather than filed.
#
# `GAUGE_SLACK` is two gauge rows. The bar is 30 px, so one row is 3.3% of
# tyre life and quantisation alone can put a corner a row either side of
# where it truly sits; twice that is comfortably past the noise and still
# far short of a lap's wear at any multiplier raced.
GAUGE_SLACK = 0.05
# A set that has just gone on reads near zero on every corner. This is the
# other half of the fresh-set test, and it is what separates a tyre change
# from a misread that happens to have dropped everything: the crash lap of
# the same session dropped all four and landed at 42% worst, which is not a
# new tyre and is not four laps of wear either.
FRESH_SET_MAX = 0.15
# How far apart the four corners of a just-fitted set may read, in pixels of
# whatever bar is being read. Three, because a set that has run an out-lap has
# genuinely worn a little and unevenly, and because the quantisation itself is
# one pixel at each end. Measured: 0 points of spread at the Fuji change on a
# 36 px bar, 3.3 at Monza's on a 31 px bar - against 16.8 across session 77's
# refused step.
FRESH_SET_SPREAD_SLACKS = 3.0
# **The ceiling on how far a reading may climb in one sample, and it exists
# because the refusal rule above only ever looks downward.**
#
# `_coherent` refuses two shapes - corners moving both ways, and every corner
# dropping onto a set too worn to be new - and silently accepts everything
# else, including a reading that rose forty points in ten seconds. Since a
# refusal deliberately does not become the new baseline, and an accept
# silently does, the baseline can only ever ratchet UPWARD: one bad
# all-rising read raises the bar, and every honest reading below it is then
# refused, loudly, for the rest of the session.
#
# Fuji, 24 Aug 2026, is that mechanism running to completion. The sampler was
# rebuilt with an empty series at 20:03:47 and was already refusing a 32%
# reading by 20:07:28 - which requires an unlogged accept above 37% inside
# those four minutes - and later refusals name figures as high as 76%. Across
# the race it refused 432 readings and accepted none. The driver was told "I
# have the tyre gauge this race" in the brief and "No tyre gauge" three and a
# half minutes later.
#
# A lap at the multipliers this league races is a few percent of tyre life,
# and samples are seconds apart. Fifteen points between two consecutive
# readings is not a tyre wearing, it is a misread - so it is refused in the
# rising direction exactly as an impossible fall already is.
GAUGE_MAX_RISE = 0.15
# **How many refusals in a row mean the BASELINE is the wrong reading.**
#
# The rule that a refusal must not become the baseline is right, and on its own
# it makes the comparison a latch: once a bad reading is filed, every honest
# one after it is refused, and because refusals never replace the baseline
# nothing can ever clear it. There is no path back. Fuji refused 432 readings
# in a row on exactly that mechanism and accepted none.
#
# The asymmetry to fix is that one accepted reading outranks any number of
# rejected ones, forever. It should not. A handful of consecutive refusals is
# a gauge that has moved or a frame that is being misread; a sustained run of
# them, all judged against one reading, is evidence about that reading. So the
# baseline is dropped and the next reading re-seeds the series.
#
# Deliberately not small. Three or four refusals in a row is ordinary - the
# driver looks away in VR, the pit-lane HUD relocates the gauge for a few
# seconds - and re-seeding then would hand the series to the pit-lane misread
# that `_coherent` exists to reject. Twelve consecutive, at the sample rates
# raced, is tens of seconds of nothing but disagreement.
REFUSALS_BEFORE_RESEED = 12
# How far past its own interval a held reading may be and still be the
# lap reading. Wider than one interval so a single missed tick does not
# force a grab on the crossing, and far short of a lap so a stale number
# can never be filed as a fresh one.
STALE_MARGIN_S = 3.0
# How long the worker waits on the queue before looking round. Short
# enough that stop() is prompt; the free-run interval is enforced against
# the clock, so this does not set the sample rate.
QUEUE_WAIT_S = 0.5
# How long `stop` waits for the reader to come out of its current grab.
# An OBS grab measures about 2050 ms, so this is regularly not enough -
# which is why a timed-out join is reported rather than assumed away.
STOP_JOIN_S = 2.0
# Free-run failures are logged no more often than this.
FREE_RUN_LOG_SPACING_S = 30.0
# Sentinel: no crossing asked, take a free-running sample.
_FREE_RUN = object()


@dataclass(frozen=True)
class Reading:
    """A gauge reading, or an honest account of why there is not one."""

    wear: dict[str, float | None] | None
    reason: str | None = None
    # **The brightest pixel in the gauge rectangle, when there was one.**
    # Carried so a caller can tell two different failures apart: a frame that
    # is genuinely dim varies from grab to grab, and one that reads the SAME
    # peak every time is not a game frame at all - it is the same pixels, which
    # means the rectangle is not on the gauge. None where no peak was taken.
    peak: int | None = None
    # **The height of the shortest bar that was read, in pixels.** Carried
    # because it IS the reading's resolution and nothing downstream can
    # recover it: one pixel of a 30 px bar is 3.3% of tyre life and one pixel
    # of an 18 px bar is 5.6%, and the two numbers look identical once they
    # are floats in a column. None where no bar was read.
    rows: int | None = None
    # **Whether the gauge was FOUND rather than read from the calibrated
    # rectangle.** The 0.5% verification of this transcription was taken on
    # the fixed layout at 1720x916; a located read uses looser thresholds on
    # whatever the locator found, and the two should not be confused when a
    # run is being judged. The canvas size does not answer this - a dim frame
    # on the calibrated canvas is located too.
    located: bool = False
    # **Where the four bars were, in the frame's own pixels**, when a gauge
    # was read. Appended with a default: the hygrometer sits beside the bars
    # and is anchored off them (`telemetry/hygrometer.py`), so a reading that
    # found them passes the geometry on rather than making the reader search
    # the frame a second time. None where no bars were read.
    bars: dict | None = None

    @property
    def ok(self) -> bool:
        return self.wear is not None and any(
            v is not None for v in self.wear.values())


def coherent(previous: dict | None, wear: dict, *,
             slack: float = GAUGE_SLACK,
             max_rise: float = GAUGE_MAX_RISE,
             fresh_max: float = FRESH_SET_MAX) -> tuple[bool, bool, str]:
    """Can this reading follow the one before it on a real set of tyres?

    Returns `(accept, fresh_set, why_not)`. `previous` is the last reading
    that was believed, or None to seed a series.

    **One rule, two callers.** `LiveWearSampler` applies it to the race path
    and `tools/read_hud_wear.py` applies it to a recorded capture, and they
    have to mean the same thing: the offline tool wrote readings into sessions
    71 and 77 that this rule refuses, while the live path was refusing the
    identical shape of misread in the same week.

    `slack` is how far a corner may move the wrong way and still be
    quantisation rather than a misread. It is a parameter because the gauge is
    not always the same size - the calibrated HUD bar is 30 px, a located one
    at 1920x1080 is 36, and one on a VR dashboard is 8-20, so a pixel is worth
    2.8% of tyre life in one case and 12.5% in another.
    """
    if not previous:
        return True, False, ""
    shared = [k for k, v in wear.items()
              if v is not None and previous.get(k) is not None]
    if not shared:
        return True, False, ""
    moved = {k: wear[k] - previous[k] for k in shared}
    fell = [k for k in shared if moved[k] < -slack]
    rose = [k for k in shared if moved[k] > slack]
    if fell and rose:
        return False, False, (
            "wear moved both ways at once ("
            + ", ".join(f"{k.upper()} {moved[k] * 100:+.0f}"
                        for k in sorted(shared))
            + ") - no tyre does that, so this is not the gauge")
    # **A fresh set is identified by where the corners ARE, not by how far
    # they fell.** This used to require every shared corner to have dropped,
    # and a corner that was barely worn cannot drop: at the Fuji stop the
    # front-right stood at 8% against a 2.8-point pixel, so it "held" while
    # the other three fell, the step was refused as incoherent, and the honest
    # tyre change the tool had already detected as a second stint was thrown
    # away.
    #
    # What a set that has just gone on actually looks like is all four corners
    # LOW and CLOSE TOGETHER - they started level and have run the same laps.
    # A misread is neither: session 77 reads 37/22/35/20 across its step, a
    # spread of six pixels, and stays refused.
    if fell and not rose:
        worst = max(wear[k] for k in shared)
        spread = worst - min(wear[k] for k in shared)
        if worst <= fresh_max and spread <= FRESH_SET_SPREAD_SLACKS * slack:
            return True, True, ""
        # Not a fresh set. **Refused only where EVERY corner fell.** A lone
        # corner falling while the rest hold is the race path's deliberate
        # tolerance - it is tuned to keep sampling and the batch form
        # reports that shape itself, so refusing it here would make
        # `coherent` reject what `wear_faults` exists to name.
        if len(fell) == len(shared):
            return False, False, (
                f"every corner dropped but the set still reads "
                f"{worst * 100:.0f}% worst against a {fresh_max * 100:.0f}% "
                f"ceiling, and they span {spread * 100:.0f} points - too "
                f"worn to be a set that has just gone on, and too low to "
                f"follow the last one")
    leapt = [k for k in rose if moved[k] > max_rise]
    if leapt:
        # The other direction of the same impossibility. See
        # `GAUGE_MAX_RISE` for why this one had to be added.
        return False, False, (
            "wear jumped "
            + ", ".join(f"{k.upper()} +{moved[k] * 100:.0f}"
                        for k in sorted(leapt))
            + f" points since the last reading - more than a tyre wears "
              f"between samples, so this is not the gauge")
    return True, False, ""


@dataclass(frozen=True)
class WearFault:
    """One step in a series of readings that no tyre could have produced."""

    # Whatever identifies the two readings to the operator - lap numbers for
    # a series about to be written, video seconds for one being swept.
    before: object
    after: object
    corners: tuple[str, ...]
    moved: dict[str, float]
    why: str

    def __str__(self) -> str:
        return (f"{self.before} -> {self.after}: "
                + ", ".join(f"{k.upper()} {self.moved[k] * 100:+.1f}"
                            for k in self.corners)
                + f" - {self.why}")


def wear_faults(series, *, slack: float = GAUGE_SLACK,
                max_rise: float = GAUGE_MAX_RISE,
                fresh_max: float = FRESH_SET_MAX, span=None) -> list[WearFault]:
    """Every step in a series of readings that a real tyre cannot have made.

    `series` is `[(key, {corner: wear|None}), ...]` in order. The keys are
    only carried through to the faults and to `span`, so they can be lap
    numbers, video seconds or anything else the caller can print.

    **`max_rise` is per step, and `span` says how big a step was.** The live
    ceiling is 15 points between readings taken seconds apart, and applying
    that to a series a LAP apart refuses honest data: measured across the
    archive, a lap on RS routinely puts 12-17 points on a corner, and the
    ceiling would split that population - refusing 16.7 and 15.0 in two
    sessions while accepting 14.1 in a third that was recorded the same way.
    So a caller whose readings are laps apart passes `span=lambda a, b: b - a`
    and a per-lap ceiling, and a step over nine laps is allowed nine laps of
    wear.

    **This is the batch form of `coherent`, and it is stricter in one place.**
    `coherent` lets a single corner fall while the others hold, because on the
    race path a refusal costs a lap of gauge and the next sample is two
    seconds away - it is tuned to keep sampling. A batch write is the opposite
    trade: nothing is lost by refusing, the whole series is on the table at
    once, and **wear is monotonic on every corner** - so a corner that goes
    backwards by more than the quantisation is reported here rather than
    filed.

    **Every step is judged against the one before it, and the baseline always
    advances** - deliberately unlike the live path. There, a refusal must not
    become the baseline or one misread poisons the comparison for the rest of
    the session. Here the point is to name each bad step exactly once, and a
    frozen baseline would report every later reading as a fault of the first.
    """
    faults: list[WearFault] = []
    for (before, was), (after, now) in zip(series, series[1:]):
        laps = max(1.0, span(before, after)) if span else 1.0
        ceiling = max_rise * laps
        # **The fresh-set ceiling is spanned too, and it was not.** `max_rise`
        # was scaled here and `FRESH_SET_MAX` was left at its live-path value,
        # which asks a set fitted in the pits to read under 15% on the NEXT
        # SAMPLE - and the next sample is a lap later, or two. A new set that
        # has run an out-lap and a flying lap has genuinely worn: at the RS
        # rates measured in this very archive (14.1%/lap in session 83,
        # 16.7% in session 81) it reads 25-30%, every corner has correctly
        # fallen, and the batch gate refuses the step - which discards the
        # WHOLE RACE, because the gate is all-or-nothing.
        #
        # Allowed the same physical budget the rise test already allows: what
        # the set could have consumed since it went on. Anything above that is
        # not a fresh set and is still refused.
        fresh_ceiling = fresh_max + max_rise * laps
        accept, fresh, why = coherent(was, now, slack=slack, max_rise=ceiling,
                                      fresh_max=fresh_ceiling)
        if fresh:
            continue
        shared = [k for k, v in now.items()
                  if v is not None and was.get(k) is not None]
        moved = {k: now[k] - was[k] for k in shared}
        wrong = tuple(sorted(k for k in shared
                             if moved[k] < -slack or moved[k] > ceiling))
        if accept and not wrong:
            continue
        if accept:
            why = ("wear went backwards on "
                   + ", ".join(k.upper() for k in wrong)
                   + " while the other corners held - a tyre does not recover, "
                     "so one of the two readings is not of the gauge")
        faults.append(WearFault(before, after, wrong, moved, why))
    return faults


def flat_series_fault(series, *, slack: float = GAUGE_SLACK) -> str | None:
    """Why a whole run cannot be a reading of tyres, or None. **Tyres wear.**

    Every other rule here asks whether one STEP is possible, and all of them
    pass trivially on a series that never moves - which is exactly what a
    misplaced rectangle produces. Rendered at 2560x1440 the locator returned a
    quad of 16 px fragments reading 0.000 on all four corners in 57 of 60
    frames, with zero faults from `wear_faults`, and a batch write would have
    filed a whole race of zeros under a source that says they were measured.
    That is CLAUDE.md rule 3: a zero meaning "not measured" is indistinguish-
    able downstream from a zero that was.

    `bar_height_bounds` now scales with the canvas so the real gauge cannot be
    excluded from candidacy, which is what created that particular false quad.
    This is the backstop for the general case, because no locator is proof
    against a frame that does not contain the gauge at all.

    A run of one is not a run and returns None: a single reading has nothing
    to be flat against, and refusing it would refuse the honest case of one
    crossing answered in a whole session.
    """
    worst = [max((v for v in wear.values() if v is not None), default=None)
             for _, wear in series]
    seen = [v for v in worst if v is not None]
    if len(seen) < 2:
        return None
    moved = max(seen) - min(seen)
    if moved > slack:
        return None
    if max(seen) <= 0.0:
        return (f"all four corners read 0.00 on every one of {len(seen)} "
                f"readings - tyres wear, so this is not the gauge")
    return (f"the worst corner moved {moved * 100:.1f} points across "
            f"{len(seen)} readings - tyres wear, so this is not the gauge")


def read_gauge(png, layout: dict | None = None, *,
               near: dict | None = None) -> Reading:
    """Transcribe the four bars from a canvas screenshot.

    Pure: bytes in, a reading out. Everything that can go wrong returns a
    `Reading` with a reason rather than raising, because the caller is a lap
    handler and the lap matters more than the gauge.

    `near` is where a previous frame found the gauge (`Reading.bars`). Where
    the gauge has to be located, the search looks there first and falls back
    to the whole frame - see `locate_gauge_near`.
    """
    layout = layout or LAYOUT_1720x916

    whole = None
    if isinstance(png, CropFrame) and _is_whole_canvas(png):
        # **A "crop" of the entire canvas is not a crop.** The refusal below
        # exists because a crop is a bet that the gauge did not move, so there
        # is nowhere to search. A full canvas is the opposite: it is exactly
        # what `locate_gauge` needs, and refusing it would be refusing the one
        # frame that can answer the question. `ScreenSource` sends this shape
        # deliberately when the driver's window is not the calibrated canvas.
        #
        # **Read from the pixels, not through a PNG.** This used to encode the
        # frame to PNG and decode it straight back so it took the bytes path
        # below. PNG is lossless, so the array is the same; the round trip was
        # about 180 ms of a 1080p frame, and "once a lap" became every grab
        # when the sampler started free-running (measured 17 Sep 2026 on the
        # Rd 9 recording: 322 ms per gauge read, of a 460 ms cycle).
        import numpy as np

        whole = np.asarray(png.pixels).astype(int)

    if isinstance(png, CropFrame) and whole is None:
        # **A crop, whose geometry was verified where it was cut.** The source
        # measured the canvas it took this from; if that was not the calibrated
        # one the crop is of the wrong rectangle and the refusal is the same
        # refusal, made one step earlier.
        if tuple(png.canvas) != CANVAS:
            return Reading(None, f"canvas is {png.canvas[0]}x{png.canvas[1]}, "
                                 f"not {CANVAS[0]}x{CANVAS[1]} - the gauge "
                                 f"layout is calibrated to that geometry and "
                                 f"cannot be scaled")
        import numpy as np

        frame = np.asarray(png.pixels).astype(int)
        ox, oy = png.origin
        layout = {corner: (x0 - ox, x1 - ox, y0 - oy, y1 - oy)
                  for corner, (x0, x1, y0, y1) in layout.items()}
        bx0, by0, bx1, by1 = layout_bounds(layout)
        if (bx0 < 0 or by0 < 0
                or by1 >= frame.shape[0] or bx1 >= frame.shape[1]):
            # The crop does not contain the gauge. Never read partially: a bar
            # clipped at the edge reads as a bar that is short of white.
            return Reading(None, f"crop at {png.origin} is "
                                 f"{frame.shape[1]}x{frame.shape[0]} and does "
                                 f"not contain the gauge")
    elif whole is not None:
        frame = whole
    else:
        try:
            import io

            import numpy as np
            from PIL import Image

            frame = np.array(
                Image.open(io.BytesIO(png)).convert("RGB")).astype(int)
        except Exception as exc:                             # noqa: BLE001
            return Reading(None, f"frame could not be decoded: {exc}")

    searchable = whole is not None or not isinstance(png, CropFrame)
    if searchable:
        height, width = frame.shape[0], frame.shape[1]
        if (width, height) != CANVAS:
            # **Not the calibrated canvas, so the layout is not used - the
            # gauge is FOUND instead.** The constants are pixel positions and
            # still may not be scaled onto another geometry; what changed is
            # that refusing outright was the wrong answer to that.
            #
            # 1720x916 is not a property of the game. It is an OBS canvas
            # someone chose, and it is not even 16:9 (1.878 against 1.778), so
            # it is a window size rather than a scale of the PS5's own output.
            # Forcing it costs twice: the 1080p source is downscaled before it
            # is read, which makes the bar SHORTER - 30 px instead of about 35,
            # so 3.3% of tyre life per pixel instead of 2.9% - and it puts the
            # capture at odds with the resolution the driver broadcasts at.
            #
            # `locate_gauge` already exists for exactly this shape of problem:
            # it finds four bars in a 2x2 by their own red-over-white
            # signature, at whatever size and wherever they sit. It was written
            # for VR, where the HUD is drawn on the dashboard in 3D, and a
            # different canvas is a strictly easier case - the gauge is in
            # screen space, it is simply not where 1720x916 put it.
            #
            # **A located read is honest about being one.** It classifies on
            # the looser thresholds the locator found the bars with and carries
            # `quantisation_note`, so it is never confused with the fixed-layout
            # read that the 0.5% verification was taken on.
            located = locate_gauge_near(frame, near)
            if located is not None:
                return _read_bars(frame, located, quantisation_note=True)
            return Reading(None, f"canvas is {width}x{height}, not "
                                 f"{CANVAS[0]}x{CANVAS[1]}, and the four bars "
                                 f"could not be found in it - so there is no "
                                 f"calibrated rectangle to read and nothing "
                                 f"that looks like the gauge either")

    peak = max(int(frame[y0:y1 + 1, x0:x1 + 1].max())
               for (x0, x1, y0, y1) in layout.values())
    if peak <= LIVE_PEAK:
        # **Before calling it dimmed, check whether the gauge simply is not
        # there.** In VR it is drawn on the dashboard and moves with head
        # position, so the calibrated rectangle is looking at trim. A located
        # gauge is read; a genuinely dark frame still says so.
        # **Only a full canvas can be searched.** The locator exists because
        # the gauge moves; a crop is a bet that it did not, so on a crop there
        # is nowhere to look and the dim verdict stands.
        moved = locate_gauge_near(frame, near) if searchable else None
        if moved is not None:
            return _read_bars(frame, moved, quantisation_note=True)
        return Reading(None, f"frame is dimmed (gauge peaks at {peak}) - paused, "
                             f"in a menu, or the HUD is drawn in 3D and the "
                             f"gauge is not where the flat layout expects it",
                       peak=peak)

    return _read_bars(frame, layout)


def _read_bars(frame, layout: dict, *,
               quantisation_note: bool = False) -> Reading:
    """Red rows over classified rows, per bar. The transcription itself."""
    out: dict[str, float | None] = {}
    shortest = None
    for corner, (x0, x1, y0, y1) in layout.items():
        bar = frame[y0:y1 + 1, x0:x1 + 1]
        rows = bar.shape[0]
        shortest = rows if shortest is None else min(shortest, rows)
        r, g, b = bar[..., 0], bar[..., 1], bar[..., 2]
        # A located gauge is dimmer and smaller, so it is classified on the
        # looser thresholds it was found with. The fixed layout keeps the
        # strict ones, which is what the 0.5% verification was taken on.
        if quantisation_note:
            red = ((r > VR_RED_MIN) & (r - g > VR_RED_SEPARATION)
                   & (r - b > VR_RED_SEPARATION))
            white = ((r > VR_WHITE_MIN) & (g > VR_WHITE_MIN)
                     & (b > VR_WHITE_MIN))
            floor = max(4, rows // 2)
        else:
            red = ((r > RED_MIN) & (r - g > RED_SEPARATION)
                   & (r - b > RED_SEPARATION))
            white = (r > WHITE_MIN) & (g > WHITE_MIN) & (b > WHITE_MIN)
            floor = MIN_CLASSIFIED_ROWS
        n_red = int((red.mean(axis=1) > 0.5).sum())
        n_white = int((white.mean(axis=1) > 0.5).sum())
        total = n_red + n_white
        out[corner] = n_red / total if total >= floor else None

    if all(v is None for v in out.values()):
        return Reading(out, "no bar showed enough classified rows to read",
                       rows=shortest, located=quantisation_note, bars=layout)
    if quantisation_note and shortest:
        # **Said, because it changes what the number is worth.** One pixel of
        # an 18 px bar is 5.6% of tyre life - about a lap at Monza - against
        # 3.3% on the flat HUD's 30 px.
        #
        # **"Found" rather than "moving".** This path is taken by the VR HUD,
        # which does move, and equally by a flat capture at a canvas nobody
        # calibrated - 1920x1080, which is what the driver broadcasts at. The
        # bars there are 36 px and perfectly still; calling them a moving HUD
        # misdescribes the reading in the one field that explains it.
        return Reading(out, f"gauge found rather than calibrated; bars are "
                            f"{shortest} px, so one pixel is "
                            f"{100 / shortest:.1f}% of tyre life - fit a slope "
                            f"across the stint rather than trusting one "
                            f"reading", rows=shortest, located=True,
                       bars=layout)
    return Reading(out, rows=shortest, located=quantisation_note, bars=layout)


# --- finding the gauge when it will not hold still -------------------------
#
# **In VR the HUD is drawn on the car's dashboard in 3D**, so it translates and
# skews with head position: measured across one 48-second recording, the
# cluster moved about 200 px horizontally and 95 px vertically during ordinary
# driving. A fixed rectangle tracks nothing there.
#
# It is also smaller. The bars are 18-20 px tall against 30 on the flat HUD, so
# one pixel is about 5.6% of tyre life - roughly a whole lap at Monza, against
# 3.3% flat. **That quantisation is fundamental and the locator cannot improve
# it**; what makes it survivable is the same discipline the offline tool
# already uses, fitting a slope across a stint rather than trusting any single
# reading.

# A bar is a short vertical strip: red at the top, white below it. These bound
# what counts as one, and they are deliberately loose on position and tight on
# shape - position is the thing that moves.
VR_BAR_MIN_H, VR_BAR_MAX_H = 8, 40
# **...and both scale with the canvas, because those two are pixel counts on a
# 916-row frame and the gauge is a FRACTION of the screen, not a size.**
#
# GT7 draws the flat bar at exactly `canvas_height / 30`: 30-31 px on the
# calibrated 916 canvas, 36 px measured on the 25 Aug 1080p replay. So at
# 1440p the real bar is 48 px, a fixed cap of 40 EXCLUDES IT FROM CANDIDACY,
# and the locator is left to pick the best of whatever else is on screen. It
# does: at 2560x1440 it returns a quad of 16 px fragments in 57 of 60 frames,
# every one reading 0.000 on all four corners, with the coherence gate seeing
# nothing wrong because a flat series of zeros is perfectly monotonic. That is
# CLAUDE.md rule 3 written to the archive under the highest-trust source tag,
# and **the driver's monitor is 2560x1440** - one click in OBS away.
#
# Scaled, not replaced: the VR gauge is painted on the dashboard in 3D and is
# both smaller and variable with head position (8-20 px against 30 flat), so a
# strict `canvas_height / 30` rule would refuse every VR capture on file. The
# ratios below are the existing constants divided by the calibrated 30.5, so
# the 916 canvas keeps exactly the bounds it has today.
FLAT_BAR_ROWS = 30
VR_BAR_MIN_RATIO, VR_BAR_MAX_RATIO = VR_BAR_MIN_H / 30.5, VR_BAR_MAX_H / 30.5


def bar_height_bounds(canvas_height: int) -> tuple[int, int]:
    """The tallest and shortest thing that can be a gauge bar on this canvas.

    Returns pixel counts, never a fraction, because the caller is comparing
    against a run length. Floors at the calibrated bounds so a small window
    cannot narrow the search below what already works.
    """
    flat = canvas_height / FLAT_BAR_ROWS
    return (min(VR_BAR_MIN_H, max(1, int(flat * VR_BAR_MIN_RATIO))),
            max(VR_BAR_MAX_H, int(round(flat * VR_BAR_MAX_RATIO))))
VR_BAR_MIN_W, VR_BAR_MAX_W = 3, 16
# The four bars sit either side of a small car icon. Two x positions, two y
# bands, all within this of each other.
VR_CLUSTER_W, VR_CLUSTER_H = 130, 90
# Looser than the flat thresholds, because the dashboard is dim and the panel
# is lit by the scene rather than composited over it.
VR_RED_MIN, VR_RED_SEPARATION, VR_WHITE_MIN = 95, 40, 135

# **What makes four bars THE gauge is that they form a 2x2 grid**, and the
# constants below are that grid's tolerances.
#
# Measured 26 Aug 2026 on the driver's own 1920x1080 capture, mid-race: the
# four real bars were found exactly - x346-357 and x430-441, y960-995 and
# y1014-1049, 36 px tall - and `locate_gauge` returned four fragments of the
# track map at x1745-1753, y339-406 instead, which then read 0.000 wear on all
# four corners. It did that because the only test applied to a candidate four
# was "closest together wins", and a stack of fragments in one column has a
# spread of 8 px where the real instrument, which has the car icon between its
# two columns, has 95. Nothing anywhere checked that the four bars were in two
# columns and two rows at all.
#
# A wrong wear number is far worse than a missing one, so the grid is now
# tested rather than assumed: two columns of two, separated by the icon,
# aligned in x within a column and in y across them, and all four the same
# size because they are the same instrument drawn four times.

# Two bars are in one column if their x extents overlap by this much of the
# narrower one. Not equality: in VR the panel is skewed by perspective and a
# bar's own edges step sideways down its height.
VR_COLUMN_OVERLAP = 0.5
# **The two columns sit either side of the car icon, and how far apart they
# are RELATIVE TO THE BAR HEIGHT is this instrument's signature.** Measured
# 2.33 at 1920x1080 (84 px between column centres, 36 px bars) and 2.40 on the
# calibrated canvas (72 px, 30 px bars) - the same gauge at two scales.
#
# Relative to height rather than to width, because width is where this went
# wrong twice. A 3 px wide fragment satisfies "two bar-widths apart" at 6 px
# of separation, and two such quads - track-map fragments on the 25 Aug
# replay, leaderboard flags on the 26 Aug capture - beat the real gauge on
# that test. Their height ratios are 1.17 and 0.23, nowhere near 2.3.
#
# The band is wide because in VR the panel is seen at an angle, which
# foreshortens the horizontal separation while leaving the bars their height.
VR_COLUMNS_APART_MIN, VR_COLUMNS_APART_MAX = 1.2, 4.0
# How far the two columns may sit apart vertically, as a fraction of bar
# height. Zero on a flat capture; non-zero in VR, where the dashboard is seen
# at an angle.
VR_ROW_SKEW = 0.6
# **What is BETWEEN the two columns is a car icon, and that is the last thing
# that separates the gauge from four bright shapes in the right arrangement.**
#
# The icon is grey line-work: neither red enough nor white enough to classify,
# so the space between the columns is almost entirely unclassified. A patch of
# sky, a white kerb or a scoreboard is not. Measured 26 Aug 2026 over the
# fraction of that space which classifies as red or white:
#
#   real gauge, 1920x1080 race capture      2.1%
#   real gauge, 1080p chase-view replay     3.0%
#   real gauge, VR dashboard, fresh set     9.4% and 10.5%
#   FALSE - VR HUD's sky and lap counter   90.3%
#   FALSE - flat HUD over a white kerb     27.2%
#
# The false one at 90.3% is the one that matters: it read 0% wear on all four
# corners at lap 5 of a stint, and no monotonicity check can catch that,
# because a run of zeros is perfectly consistent with a run of zeros. Rule 3
# of CLAUDE.md is precisely this - a zero that means "not measured" is
# diagnosed as a real value - and here it would have told the wear model that
# five laps consumed nothing.
VR_ICON_MAX_SOLID = 0.20
# How much the four bars may differ in height, as a fraction of the shortest.
# They are one instrument drawn four times; anything wildly mismatched is four
# unrelated things that happen to be near each other.
VR_HEIGHT_MISMATCH = 0.5


def _vr_masks(frame):
    import numpy as np

    r, g, b = frame[..., 0], frame[..., 1], frame[..., 2]
    red = (r > VR_RED_MIN) & (r - g > VR_RED_SEPARATION) &           (r - b > VR_RED_SEPARATION)
    white = ((r > VR_WHITE_MIN) & (g > VR_WHITE_MIN) & (b > VR_WHITE_MIN)
             & (abs(r - g) < 45) & (abs(g - b) < 45))
    return red, white, np.asarray(red | white)


def _looks_like_a_bar(red, white, x: int, y0: int, y1: int) -> bool:
    """Could this column of solid pixels be one tyre bar?

    **A bar is red from the top and white below, and either part may be the
    whole of it.** The test used to demand both at once - top third red AND
    bottom third white - which finds a half-worn tyre and nothing else. A
    FRESH set is white all the way down and a dead one is red all the way
    down, so the locator could not see either: the two readings that matter
    most, since one anchors a stint and the other ends it.

    Measured on synthetic canvases at 1920x1080: a 0% set and a 90% set both
    failed to locate under the old test and both read correctly under this
    one.

    The relaxation is safe because **finding is not validating.** What
    disambiguates the gauge from brake lights and kerbs is the 2x2 geometry
    below - four bars, two columns, two rows, inside a tight cluster, taking
    the tightest spread. This test only has to admit what a bar can look like
    and reject a column that is not red-over-white at all.
    """
    import numpy as np

    r = red[y0:y1 + 1, x]
    w = white[y0:y1 + 1, x]
    rows = len(r)
    if rows == 0:
        return False
    # The run is solid by construction, so nearly every row should be one or
    # the other. A column that is largely neither is not this instrument.
    if (r | w).mean() < 0.9:
        return False
    red_rows, white_rows = np.where(r)[0], np.where(w)[0]
    if len(red_rows) == 0 and len(white_rows) == 0:
        return False
    # **Red above white, and either may be empty.** That single statement is
    # what a tyre bar is at every wear level - it fills red from the top as
    # the tyre wears - and it covers the fresh set (no red), the spent set (no
    # white) and everything between, which three separate thresholds did not.
    # One row of overlap is allowed for the boundary pixel, which is a blend
    # of both and can classify either way.
    if len(red_rows) and len(white_rows):
        if int(red_rows.max()) > int(white_rows.min()) + 1:
            return False
    return True


def locate_gauge_near(frame, near: dict | None) -> dict | None:
    """`locate_gauge`, searching round where the gauge last was before the frame.

    **The whole-frame search is most of what a free-running grab costs** -
    about 230 ms of a 1080p frame, every grab, to find an instrument that on a
    flat capture has not moved since the last one. So the same search runs
    first on a window round `near`, and only a miss there searches everything.

    **Finding is not relaxed, only narrowed.** The window is searched by
    `locate_gauge` itself, with the bar-height bounds of the FULL canvas, so a
    gauge found here passed the same 2x2 grid and car-icon tests as one found
    anywhere. Two guards keep the window honest:

    * the window is padded by more than the tallest possible bar, and
    * a gauge found within one bar-height of a cut edge is refused and the
      whole frame searched instead - a run the cut truncated could otherwise
      pass for a bar of the right height.

    `near` is only a starting point. It never stands in for a reading: a miss
    falls through to the full search, whose answer (or None) is returned.
    """
    if near:
        height, width = frame.shape[0], frame.shape[1]
        _, max_h = bar_height_bounds(height)
        pad = max(VR_CLUSTER_W, 3 * max_h)
        margin = max_h + 2
        x0, y0, x1, y1 = layout_bounds(near)
        wx0, wy0 = max(0, x0 - pad), max(0, y0 - pad)
        wx1, wy1 = min(width, x1 + pad + 1), min(height, y1 + pad + 1)
        found = locate_gauge(frame[wy0:wy1, wx0:wx1], canvas_height=height)
        if found is not None:
            fx0, fy0, fx1, fy1 = layout_bounds(found)
            inside = ((wx0 == 0 or fx0 >= margin)
                      and (wy0 == 0 or fy0 >= margin)
                      and (wx1 == width or fx1 < (wx1 - wx0) - margin)
                      and (wy1 == height or fy1 < (wy1 - wy0) - margin))
            if inside:
                return {corner: (bx0 + wx0, bx1 + wx0, by0 + wy0, by1 + wy0)
                        for corner, (bx0, bx1, by0, by1) in found.items()}
    return locate_gauge(frame)


def locate_gauge(frame, *, canvas_height: int | None = None) -> dict | None:
    """Find the four bars in a frame that will not hold them still.

    Returns a layout in the same shape as `LAYOUT_1720x916` - `{corner:
    (x0, x1, y0, y1)}` - or None where four bars in a 2x2 could not be found.

    **None is the expected answer much of the time** and is not a failure: the
    panel is often edge-on, out of frame, or behind the wheel. Sampling more
    often costs nothing but a screenshot, and a stint's slope survives gaps.

    `canvas_height` is for a window cut from a larger canvas: the bar sizes
    scale with the screen, not with the window.
    """
    import numpy as np

    red, white, solid = _vr_masks(frame)
    height, width = solid.shape
    min_h, max_h = bar_height_bounds(canvas_height or height)
    found = []
    for x in range(width):
        column = solid[:, x]
        if not column.any():
            continue
        idx = np.where(column)[0]
        # **A run may bridge one unclassified row, because the boundary
        # between the red and the white IS one.** Measured on the 25 Aug
        # 1080p replay, rear-left bar: red runs y1014-1030, white y1032-1049,
        # and y1031 is the blend of the two - about (230,190,190) - which is
        # neither red enough nor white enough at some columns and both at
        # others. Split there, one bar becomes two runs of 17 and 18 rows, the
        # grouping below mixes full-height columns with half-height ones, and
        # the bar's median extent comes out 26 px instead of 36. That is not a
        # missed reading, it is a WRONG one: the same 17 red rows over a
        # denominator of 26 read 65% worn where the truth is 47%.
        #
        # `_looks_like_a_bar` already allows the two to overlap by a row for
        # the same reason, and its solidity test is a 90% mean, so one bridged
        # row cannot admit a column that is not otherwise a bar.
        for run in np.split(idx, np.where(np.diff(idx) > 2)[0] + 1):
            if not (min_h <= len(run) <= max_h):
                continue
            y0, y1 = int(run[0]), int(run[-1])
            if _looks_like_a_bar(red, white, x, y0, y1):
                found.append((x, y0, y1))
    if len(found) < VR_BAR_MIN_W * 4:
        return None

    # Adjacent columns of similar extent are one bar.
    #
    # **Several bars are open at once, and that is the whole difficulty.** A
    # single linear scan cannot do this. Sorting by column interleaves the top
    # and bottom bar of the same column, which share an x; sorting by row
    # breaks a bar apart the moment perspective drifts its rows across its own
    # width, which is exactly what a HUD painted on a dashboard does. Measured
    # both ways on one real recording: column-first read a fifth of the frames,
    # row-first read a fourteenth.
    #
    # So every open bar is kept and each run joins the one it continues.
    open_bars: list[list] = []
    for item in sorted(found, key=lambda c: (c[0], c[1])):
        for bar in open_bars:
            last = bar[-1]
            if item[0] - last[0] <= 1 and abs(item[1] - last[1]) <= 4:
                bar.append(item)
                break
        else:
            open_bars.append([item])

    shaped = []
    for group in open_bars:
        if not VR_BAR_MIN_W <= len(group) <= VR_BAR_MAX_W:
            continue
        xs = [c[0] for c in group]
        shaped.append((min(xs), max(xs),
                       int(np.median([c[1] for c in group])),
                       int(np.median([c[2] for c in group]))))
    if len(shaped) < 4:
        return None

    # Two bars stacked at the same x are one side of the car.
    columns = []
    for index, first in enumerate(shaped):
        for second in shaped[index + 1:]:
            top, bottom = sorted((first, second), key=lambda bar: bar[2])
            if bottom[2] - top[2] > VR_CLUSTER_H:
                continue
            if _one_column(top, bottom):
                columns.append((top, bottom))

    # Two columns either side of the car icon are the gauge. **Scored on size
    # first** - not on how close together the four are, which is what chose
    # the track map, and not on how well they match each other either.
    #
    # Measured on the 25 Aug 1080p replay: the real gauge's rear-left bar is
    # split by a seam in its white section, so that quad is 36/26/36/36 while
    # a quad of track-map fragments is 9/9/9/10 - and any score that ranks
    # regularity above size prefers the fragments. Bar height IS the reading's
    # resolution (36 px is 2.8% of tyre life per pixel, 9 px is 11.1%), so
    # where two candidates both satisfy the grid, the bigger one is both the
    # more likely instrument and the better reading. Regularity breaks ties.
    best = None
    for index, first in enumerate(columns):
        for second in columns[index + 1:]:
            left, right = sorted((first, second), key=lambda pair: pair[0][0])
            if not _one_gauge(left, right, solid):
                continue
            heights = [bar[3] - bar[2] + 1 for pair in (left, right)
                       for bar in pair]
            score = (-min(heights), max(heights) - min(heights))
            if best is None or score < best[0]:
                # Left column is the near side, top of each column is the
                # front axle - the same arrangement the flat HUD uses.
                best = (score, {"fl": left[0], "rl": left[1],
                                "fr": right[0], "rr": right[1]})
    return best[1] if best else None


def _heights_match(bars) -> bool:
    """One instrument drawn four times, or four unrelated things?"""
    heights = [bar[3] - bar[2] + 1 for bar in bars]
    return (max(heights) - min(heights)
            <= max(2, VR_HEIGHT_MISMATCH * min(heights)))


def _one_column(top, bottom) -> bool:
    """Are these two bars the front and rear of one side of the car?"""
    if top[3] >= bottom[2]:
        # Overlapping vertically. Two axles do not share rows, and a bar that
        # overlaps another is a fragment of the same thing.
        return False
    overlap = min(top[1], bottom[1]) - max(top[0], bottom[0]) + 1
    narrower = min(top[1] - top[0], bottom[1] - bottom[0]) + 1
    if overlap < VR_COLUMN_OVERLAP * narrower:
        return False
    return _heights_match((top, bottom))


def _one_gauge(left, right, solid) -> bool:
    """Are these two columns the same instrument, with the icon between them?"""
    bars = (left[0], left[1], right[0], right[1])
    if not _heights_match(bars):
        return False
    height = max(bar[3] - bar[2] + 1 for bar in bars)
    apart = abs((right[0][0] + right[0][1]) - (left[0][0] + left[0][1])) / 2
    if not (VR_COLUMNS_APART_MIN * height <= apart
            <= min(VR_COLUMNS_APART_MAX * height, VR_CLUSTER_W)):
        return False
    if max(abs(left[0][2] - right[0][2]),
           abs(left[1][2] - right[1][2])) > VR_ROW_SKEW * height:
        return False
    # The front row is entirely above the rear row, across both columns.
    if max(left[0][3], right[0][3]) >= min(left[1][2], right[1][2]):
        return False
    # And the car icon sits between the columns. See `VR_ICON_MAX_SOLID`.
    top = min(left[0][2], right[0][2])
    bottom = max(left[1][3], right[1][3])
    between = solid[top:bottom + 1,
                    max(left[0][1], left[1][1]) + 1:
                    min(right[0][0], right[1][0])]
    return not between.size or between.mean() <= VR_ICON_MAX_SOLID


@dataclass(frozen=True)
class CropFrame:
    """A gauge-sized crop of the canvas, with the origin it was cut from.

    **The point of this type is that the geometry was checked at the source
    rather than by counting pixels here.** `read_gauge` refuses a PNG whose
    canvas is not 1720x916 because the layout constants are pixel positions on
    that canvas and mean nothing on another. A crop cannot be checked that way
    - it is 82x76 by construction - so the source that cut it carries the
    canvas it measured, and it is that figure which is verified.

    `pixels` is RGB, `origin` is the crop's top-left in canvas coordinates.
    """

    pixels: object
    origin: tuple[int, int]
    canvas: tuple[int, int]


def _is_whole_canvas(crop: CropFrame) -> bool:
    """Whether this `CropFrame` is actually the entire canvas."""
    try:
        height, width = crop.pixels.shape[0], crop.pixels.shape[1]
    except AttributeError:
        return False
    return (tuple(crop.origin) == (0, 0)
            and (width, height) == tuple(crop.canvas))


def whole_frame(grabbed):
    """A grab as a whole-screen RGB array, or `None` if it is not one.

    **A grab is not an image, and a crop is not a screen.** `ScreenSource`
    returns a `CropFrame` and `ObsSource` returns PNG bytes; `read_gauge` knows
    how to unwrap both and nothing else did. A passenger handed the raw result
    got an object with no `ndim`, every reader refused it as "not a frame", and
    three layers of exception handling turned a dead feature into silence.

    The second half matters as much as the first. When the projector IS the
    calibrated 1720x916 canvas the sampler grabs only the gauge rectangle -
    82x76 - and there is no leaderboard anywhere in it. Handing that on would
    let a board reader search a picture of a tyre gauge and report, honestly
    and uselessly, that it could not find a board. `None` says the difference.
    """
    import numpy as np

    if isinstance(grabbed, CropFrame):
        if not _is_whole_canvas(grabbed):
            return None
        return np.asarray(grabbed.pixels)
    if isinstance(grabbed, (bytes, bytearray)):
        # `io` is imported inside `read_gauge`, not at module level - and a
        # bare `io.BytesIO` here raised NameError into a broad `except`, which
        # is how a decode that works perfectly in isolation returns None
        # forever. Import it where it is used.
        import io as _io

        from PIL import Image
        try:
            return np.asarray(
                Image.open(_io.BytesIO(bytes(grabbed))).convert("RGB")
            ).astype(int)
        except (OSError, ValueError):
            return None
    if getattr(grabbed, "ndim", 0) == 3:
        return np.asarray(grabbed)
    return None


def layout_bounds(layout: dict) -> tuple[int, int, int, int]:
    """The bounding box of a layout, as (x0, y0, x1, y1) inclusive."""
    xs = [v[0] for v in layout.values()] + [v[1] for v in layout.values()]
    ys = [v[2] for v in layout.values()] + [v[3] for v in layout.values()]
    return min(xs), min(ys), max(xs), max(ys)


class ObsSource:
    """One canvas screenshot per call, over obs-websocket 5.x.

    Opened and closed per grab. A long-lived socket would be cheaper and would
    also be one more thing holding state across a session that already has a
    telemetry stream, a haptics engine and a serial port to keep alive.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 4455,
                 password: str = "") -> None:
        self.host, self.port, self.password = host, port, password

    def _connected(self, work):
        """Open, authenticate, run `work(request)`, close. Never raises."""
        try:
            from websockets.sync.client import connect
        except ImportError:
            return None, "the websockets package is not installed"
        try:
            with connect(f"ws://{self.host}:{self.port}",
                         open_timeout=CONNECT_TIMEOUT_S,
                         close_timeout=CONNECT_TIMEOUT_S,
                         max_size=MAX_FRAME_BYTES) as ws:
                self._identify(ws, json.loads(ws.recv(timeout=CONNECT_TIMEOUT_S)))
                return work(lambda kind, data=None: self._request(ws, kind, data)), None
        except Exception as exc:                             # noqa: BLE001
            return None, f"{type(exc).__name__}: {exc}"

    def grab(self) -> tuple[bytes | None, str | None]:
        def work(request):
            scene = request("GetCurrentProgramScene")
            name = (scene.get("sceneName")
                    or scene.get("currentProgramSceneName"))
            if not name:
                raise RuntimeError("OBS did not name a program scene")
            shot = request("GetSourceScreenshot", {
                "sourceName": name, "imageFormat": "png",
                "imageWidth": CANVAS[0], "imageHeight": CANVAS[1]})
            data = shot.get("imageData") or ""
            if "," not in data:
                raise RuntimeError("OBS returned no image data")
            return base64.b64decode(data.split(",", 1)[1])

        return self._connected(work)

    def recording(self) -> tuple[bool | None, str | None]:
        got, why = self._connected(lambda request: request("GetRecordStatus"))
        if got is None:
            return None, why
        return bool(got.get("outputActive")), None

    def start_recording(self) -> tuple[bool | None, str | None]:
        """Begin recording, unless OBS is already doing so.

        **Returns False when it was already running**, which is not a failure
        and is the signal the caller needs: a recording this app did not start
        is not a recording this app may stop.
        """
        def work(request):
            if bool(request("GetRecordStatus").get("outputActive")):
                return False
            request("StartRecord")
            return True

        return self._connected(work)

    def stop_recording(self) -> tuple[str | None, str | None]:
        """Stop, and return the file OBS wrote."""
        def work(request):
            if not bool(request("GetRecordStatus").get("outputActive")):
                return None
            return (request("StopRecord") or {}).get("outputPath")

        return self._connected(work)

    def _identify(self, ws, hello: dict) -> None:
        payload = {"rpcVersion": 1}
        auth = (hello.get("d") or {}).get("authentication")
        if auth:
            secret = base64.b64encode(hashlib.sha256(
                (self.password + auth["salt"]).encode()).digest()).decode()
            payload["authentication"] = base64.b64encode(hashlib.sha256(
                (secret + auth["challenge"]).encode()).digest()).decode()
        ws.send(json.dumps({"op": 1, "d": payload}))
        got = json.loads(ws.recv(timeout=CONNECT_TIMEOUT_S))
        if got.get("op") != 2:
            raise RuntimeError(f"OBS refused the connection: {got}")

    def _request(self, ws, kind: str, data: dict | None = None) -> dict:
        ws.send(json.dumps({"op": 6, "d": {
            "requestType": kind, "requestId": kind, "requestData": data or {}}}))
        while True:
            got = json.loads(ws.recv(timeout=CONNECT_TIMEOUT_S))
            if got.get("op") == 7 and got["d"].get("requestId") == kind:
                status = got["d"]["requestStatus"]
                if not status.get("result"):
                    raise RuntimeError(f"{kind} failed: {status}")
                return got["d"].get("responseData") or {}


# --- the local screen, at a five-hundredth of the cost --------------------
#
# **Measured 22 Aug 2026, on this PC (Core Ultra 5 125U, 2560x1440):**
#
#   mss grab of the 82x76 gauge region     wall 16.68 ms   CPU  0.21 ms
#   mss grab of the full 2560x1440 screen  wall 33.14 ms   CPU 12.50 ms
#   PIL ImageGrab, same 82x76 bbox         wall 50.07 ms   CPU 23.05 ms
#   transcribing the four bars                             CPU  0.10 ms
#
# against `ObsSource`'s measured **537 ms of OBS CPU per screenshot**. The
# whole difference is what is being asked for: OBS renders, PNG-encodes and
# base64s a 1720x916 canvas over a socket, where this copies 6,232 pixels.
#
# Three things that are not obvious in those numbers:
#
# * **The 16.68 ms wall time is vsync, not work.** It is 1/60 s to three
#   decimals - the grab blocks on the compositor - and the CPU actually burned
#   is 0.21 ms. It therefore belongs on the worker thread, which is where the
#   sampler already puts it.
# * **Crop at capture, never after.** Grabbing the screen and slicing in numpy
#   costs 12.50 ms against 0.21; PIL costs 23.05 ms for the identical 82x76
#   output because it copies the whole screen regardless of the bbox. The
#   cheap path is the one that asks the OS for the rectangle.
# * **The cost is flat in area** - 600x200 measured 0.52 ms against 82x76's
#   0.21 - so it is the round trip that is paid for, not the pixels.
#
# **What it costs to be right: the pixels have to be on screen.** The socket
# does not care whether OBS is visible, minimised or behind the app; this
# reads what the monitor shows. That is the trade, and it is why `ObsSource`
# stays and stays the default.

# OBS's projector windows, whose client area IS the canvas - which is what
# makes this self-locating rather than a rectangle he has to calibrate.
#
# **Matched on the word alone, because OBS renamed them.** The tuple below is
# what OBS 30 called these windows; **OBS 32.2.2 titles the same window
# `Projector - Preview`**, which matches none of them. Measured 22 Aug 2026
# with a projector open and the reader insisting none was - the message even
# told him to open the thing that was already open.
#
# So the test is the word "projector" and the client area, not a title
# format that changes between releases. The size check is what actually
# guards against reading the wrong window, and it is exact.
PROJECTOR_WORD = "projector"
# Kept only to prefer the program feed where both are open - it is the real
# output, and a preview projector can be showing a different scene.
PROJECTOR_PREFERRED = ("program",)
PROJECTOR_TITLES = ("windowed projector (program)",
                    "windowed projector (preview)",
                    "fullscreen projector (program)")


def find_projector(title_hint: str = ""):
    """(hwnd, title) of the OBS projector, or (None, reason).

    **One matcher, used by both the reader and the sizer.** Two copies of
    "which window is the projector" would drift the first time OBS renamed
    them again - which it has already done once, between OBS 30 and 32.
    """
    try:
        import win32gui
    except ImportError:
        return None, "pywin32 is not installed"
    hint = (title_hint or "").strip().lower()
    hits = []
    # **Windows that ARE projectors but are not visible, kept separately.**
    # `IsWindowVisible` is false for a minimised window, one on another
    # virtual desktop, and one behind an exclusive-fullscreen app - all three
    # of which happen in VR. Reporting those as "no projector is open" sent
    # the driver to reopen a window he already had open: on 3 Sep 2026 he had
    # it up all night and the log told him to create it.
    hidden = []

    def visit(hwnd, _):
        title = win32gui.GetWindowText(hwnd) or ""
        low = title.lower()
        if PROJECTOR_WORD not in low:
            return
        if hint and hint not in low:
            return
        if not win32gui.IsWindowVisible(hwnd):
            hidden.append((hwnd, title))
            return
        hits.append((hwnd, title))

    try:
        win32gui.EnumWindows(visit, None)
    except Exception as exc:                                 # noqa: BLE001
        return None, f"could not enumerate windows: {type(exc).__name__}"
    if not hits and hidden:
        # The window exists. Saying "open one" here is a wrong instruction,
        # and it is the one that wasted a whole race night.
        return None, (
            f"the projector {hidden[0][1]!r} is open but NOT VISIBLE to the "
            f"screen reader - it is minimised, on another virtual desktop, or "
            f"behind a fullscreen app (VR does this). Bring it to the front on "
            f"the monitor the app is on; it does not need focus.")
    if not hits:
        return None, ("no OBS projector window is open - right click the "
                      "preview in OBS and choose Windowed Projector "
                      f"(Program), then size it to "
                      f"{SNAP_CANVAS[0]}x{SNAP_CANVAS[1]}")
    # **The first, and it is said when there are others.** Two projectors
    # showing different scenes would otherwise be chosen between silently.
    # The program feed first where both are open: it is the real output,
    # and a preview projector can be showing a different scene entirely.
    hits.sort(key=lambda hit: 0 if any(
        word in hit[1].lower() for word in PROJECTOR_PREFERRED) else 1)
    if len(hits) > 1:
        _log.info(f"hud-wear: {len(hits)} projector windows open, using "
                  f"{hits[0][1]!r}")
    return hits[0], None


def snap_projector(title_hint: str = "") -> tuple[bool, str]:
    """Size the projector so its client area is exactly the canvas.

    Returns `(ok, what happened)`, both fit to be shown to the driver.

    **Because the size has to be exact and a mouse cannot do exact.**
    `ScreenSource` takes the calibrated crop only when the projector IS
    `CANVAS` to the pixel and hands the whole frame to the locator otherwise -
    correctly, since a scaled canvas moves every calibrated pixel and a crop
    from one would be a plausible wrong wear number rather than an error.
    **The size wanted is `SNAP_CANVAS`, the console's own 1080p**, not the
    calibrated canvas: see its comment. That leaves
    the driver dragging a window edge against a figure he cannot see, before
    every session, because a projector does not survive a restart. This does
    the arithmetic instead: the chrome is whatever the window rect has over
    the client rect, so the outer size wanted is the canvas plus that.

    **The position is preserved, deliberately.** Which monitor the projector
    sits on is the driver's business - his second screen has the app on it -
    and the reader re-reads the window's position on every grab, so moving it
    afterwards costs nothing. Only the size is ours to set.
    """
    found, why = find_projector(title_hint)
    if found is None:
        # **Logged, not only returned.** This ran from a button all night on
        # 3 Sep 2026 and left no trace in the log at all, so the morning after
        # there was no way to tell whether it had been pressed, what it found,
        # or what size it set. A sizer that reports only to a dialog reports
        # to nobody an hour later.
        _log.warning("hud-wear: snap_projector found nothing: %s", why)
        return False, why
    hwnd, title = found
    try:
        import win32con
        import win32gui

        _, _, was_w, was_h = win32gui.GetClientRect(hwnd)
        if (was_w, was_h) == SNAP_CANVAS:
            # **Still raised, because being the right size is not the whole
            # job.** The stint that went dark had a correctly sized projector
            # the entire time; it was simply underneath something.
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                                  win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
                                  | win32con.SWP_NOACTIVATE)
            return True, (f"{title!r} is already "
                          f"{SNAP_CANVAS[0]}x{SNAP_CANVAS[1]}, and "
                          f"is now kept in front so nothing can cover the "
                          f"gauge.")
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        chrome_w = (right - left) - was_w
        chrome_h = (bottom - top) - was_h
        # **Topmost, and it is not a convenience.** This source reads what the
        # MONITOR shows, not what the window holds, so anything composited
        # over the gauge is read as tyre wear. Measured 24 Aug 2026: a stint
        # sampled every two seconds for six minutes and every single grab came
        # back dark, because the projector was sitting behind another window -
        # the capture was of that window, and the log said only "the frame is
        # dimmed". Sizing it correctly and leaving it buried is no better than
        # not opening it, so the two are done together.
        win32gui.SetWindowPos(
            hwnd, win32con.HWND_TOPMOST, left, top,
            SNAP_CANVAS[0] + chrome_w, SNAP_CANVAS[1] + chrome_h,
            win32con.SWP_NOACTIVATE)
        _, _, now_w, now_h = win32gui.GetClientRect(hwnd)
        _log.info("hud-wear: snap_projector %r %sx%s -> %sx%s (wanted %sx%s)",
                  title, was_w, was_h, now_w, now_h,
                  SNAP_CANVAS[0], SNAP_CANVAS[1])
    except Exception as exc:                                 # noqa: BLE001
        _log.warning("hud-wear: snap_projector %r failed: %s: %s",
                     title, type(exc).__name__, exc)
        return False, f"{title!r}: {type(exc).__name__}: {exc}"
    if (now_w, now_h) != SNAP_CANVAS:
        # A projector pinned by the window manager - fullscreen, snapped to
        # half a monitor, or on a display too small to hold the canvas.
        return False, (f"{title!r} would not resize: asked for "
                       f"{SNAP_CANVAS[0]}x{SNAP_CANVAS[1]}, got "
                       f"{now_w}x{now_h}. If it "
                       f"is a fullscreen projector, close it and open a "
                       f"Windowed Projector (Program) instead.")
    return True, (f"{title!r} resized from {was_w}x{was_h} to "
                  f"{SNAP_CANVAS[0]}x{SNAP_CANVAS[1]}, left where it "
                  f"was, and kept in "
                  f"front so nothing can cover the gauge.")


class ScreenSource:
    """The gauge region, read straight off the desktop.

    Point OBS at a **Windowed Projector (Program)** and size it 1:1 - right
    click the preview, Windowed Projector, then size the window until its
    client area is the canvas. This finds that window by title, so nothing has
    to be calibrated and moving it costs nothing.

    Returns a `CropFrame`, never PNG bytes: there is no encode step here and
    adding one would put back most of what this exists to remove.
    """

    def __init__(self, title_hint: str = "") -> None:
        # A hint narrows the search where several projectors are open. Empty
        # means "any program projector", which is the normal case.
        self.title_hint = title_hint.strip().lower()
        # **Whole window rather than the gauge rectangle.** Set when something
        # else needs the screen - the pit wall needs the leaderboard, which is
        # nowhere near the gauge. Costed before offering it: a full 2560x1440
        # grab is 33.14 ms wall against 16.68 for the gauge rectangle, and at
        # the one-to-two-hertz this runs at that is nothing.
        self.whole = False

    def _window(self):
        """(hwnd, title) of the projector, or (None, reason)."""
        return find_projector(self.title_hint)

    def grab(self):
        """(CropFrame, None) or (None, reason). Never raises."""
        found, why = self._window()
        if found is None:
            return None, why
        hwnd, title = found
        try:
            import win32gui

            left, top, right, bottom = win32gui.GetClientRect(hwnd)
            ox, oy = win32gui.ClientToScreen(hwnd, (left, top))
        except Exception as exc:                             # noqa: BLE001
            return None, f"{title!r}: {type(exc).__name__}: {exc}"

        try:
            import mss
            import numpy as np
        except ImportError as exc:
            return None, f"{exc.name} is not installed"

        width, height = right - left, bottom - top
        if width <= 0 or height <= 0:
            return None, f"{title!r} has no client area"
        if self.whole or (width, height) != CANVAS:
            # **The whole window, so the locator can find the gauge in it.**
            #
            # This used to refuse outright, and the reason it gave was sound
            # when it was written: the layout constants are pixel positions on
            # a 1720x916 canvas and a scaled projector moves every one of them.
            # But `read_gauge` grew a locate path for exactly this - it finds
            # the four bars by their own red-over-white signature at whatever
            # size, and `bar_height_bounds` scales with the canvas so a 1440p
            # bar (48 px against the calibrated 30.5) is inside candidacy.
            #
            # **So the refusal outlived the problem.** The driver moved to
            # 2560x1440 and the live sampler went silent - not wrong, which
            # would have been worse, but silent, and a wear channel that
            # returns a reason every lap looks identical to one nobody
            # checked.
            #
            # Costed before choosing it. Measured in this file: a full
            # 2560x1440 grab is 33.14 ms wall and 12.50 ms CPU against 16.68
            # and 0.21 for the gauge rectangle. Sixty times the CPU, once a
            # lap, on a worker thread - which is nothing against a lap of 105
            # seconds, and the alternative is no reading at all.
            try:
                with mss.mss() as sct:
                    shot = sct.grab({"left": ox, "top": oy,
                                     "width": width, "height": height})
                pixels = np.asarray(shot)[..., 2::-1]
            except Exception as exc:                         # noqa: BLE001
                return None, f"screen grab failed: {type(exc).__name__}: {exc}"
            return CropFrame(pixels=pixels, origin=(0, 0),
                             canvas=(width, height)), None

        gx0, gy0, gx1, gy1 = layout_bounds(LAYOUT_1720x916)
        try:
            with mss.mss() as sct:
                shot = sct.grab({"left": ox + gx0, "top": oy + gy0,
                                 "width": gx1 - gx0 + 1,
                                 "height": gy1 - gy0 + 1})
            # mss hands back BGRA; the reader wants RGB.
            pixels = np.asarray(shot)[..., 2::-1]
        except Exception as exc:                             # noqa: BLE001
            return None, f"screen grab failed: {type(exc).__name__}: {exc}"
        return CropFrame(pixels=pixels, origin=(gx0, gy0), canvas=CANVAS), None


class LiveWearSampler:
    """Gauge readings off the race path, filed one per lap.

    `request` is called from the lap handler and returns immediately. The grab,
    the decode and the write all happen on a worker thread, and the queue holds
    **one** lap: if a reading is still in flight when the next crossing lands,
    the older request is dropped. A wear figure filed against the wrong lap is
    worse than a gap, and a queue that grows is a queue that is already wrong.

    ### Free-running, where the frames are cheap enough for it

    With `interval_s` set the worker also samples on its own between crossings,
    and a crossing then files **the last good reading taken before it** rather
    than grabbing afresh. That is not a new rule - it is the one
    `tools/read_hud_wear.py::attach` already applies to a recorded race, for
    the same reason: the gauge at the line is what that lap left the tyre at,
    and a sample taken after the crossing belongs to the next lap.

    Two things it buys, and one it does not:

    * **A paused or dimmed frame at the crossing no longer costs the lap.** The
      reading from a few seconds earlier stands in, and on a quantised gauge
      those are usually the same number anyway.
    * **A stint gets a series instead of a point.** The advice above for a
      30 px bar is to fit a slope across the stint rather than trust any single
      reading; at one sample every two seconds there are hundreds to fit rather
      than the twenty-odd a race has laps.
    * **It does not make a single reading finer.** One pixel is 3.3% of tyre
      life whatever the rate. Sampling faster pins the step transitions, which
      tightens the slope; it does not subdivide a step.

    `interval_s = 0` keeps the original behaviour exactly: nothing is sampled
    until a crossing asks for it.

    **Only a crossing failure counts toward standing down.** A free-run grab
    failing every two seconds would exhaust the budget in ten and take the
    whole session gauge with it - and a projector window shut for a minute is
    not the same event as the gauge being unreadable at the line.
    """

    def __init__(self, source, write, *, on_status=None,
                 interval_s: float = 0.0, on_frame=None,
                 on_hygro=None, on_compound=None, on_damage=None) -> None:
        self._source = source
        # **The hygrometer rides the same grab** (plan row 5.21), for the reason
        # `on_frame` does: a second grab would halve the gauge's rate. Handed a
        # `HygroReading` every grab - "cannot see" included - and swallowed.
        self._on_hygro = on_hygro
        # And the compound label beside the same bars (`hud_compound`).
        self._on_compound = on_compound
        # And the car icon between them (`hud_damage`, plan row 5.20).
        self._on_damage = on_damage
        self._write = write
        self._status = on_status
        # **Anyone else who needs this frame gets THIS frame.** Measured on
        # this machine `mss` costs about 16.6 ms for a grab of any size - that
        # is the vsync, not the copy - and it does not compose: four regions is
        # four grabs and 15 Hz. A second sampler with its own grab would halve
        # the gauge's rate to read a leaderboard that changes once a lap. So
        # the frame is handed on, and every failure in the handler is swallowed
        # here: nothing riding along may cost the gauge a reading.
        self._on_frame = on_frame
        # Said once when the grab turns out to be a crop with no board in it.
        self._said_crop_only = False
        self._interval_s = max(0.0, float(interval_s))
        self._queue: queue.Queue = queue.Queue(maxsize=1)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._failures = 0
        self.stood_down = False
        # Crossings in a row that produced no reading, and the dim peaks they
        # reported. Both exist to turn a silent instrument into a spoken one -
        # see `BLIND_CROSSINGS_BEFORE_SAYING`.
        self._blind = 0
        # What was last said about the blindness, so it can be said again when
        # the diagnosis sharpens but not when it merely repeats. None = nothing
        # said yet, which is not the same as "said nothing was wrong".
        self._said_blind: str | None = None
        self._said_stuck = False
        self._dim_peaks: list[int] = []
        # Consecutive samples that produced no accepted reading, for any
        # reason. Reset by any accept. See BLIND_SAMPLES_BEFORE_STANDING_DOWN.
        self._nothing_seen = 0
        # The most recent good reading and when it was taken. Written and read
        # on the worker thread only.
        self._latest: tuple[float, Reading] | None = None
        # Every good reading this stint, for the slope fit. Cleared on a fresh
        # set, the same way the offline tool splits stints.
        self.series: list[tuple[float, dict]] = []
        # Consecutive refusals against the current baseline. See
        # `REFUSALS_BEFORE_RESEED`.
        self._refused_running = 0
        self._last_free_log = 0.0
        # **A fresh-set reading, held until a second agrees.** A drop to zero
        # on all four corners was accepted instantly while a rise was refused
        # twelve times - and an all-four-corners 0.000 is a documented
        # failure of the locator, so the series was cut on a misread nine
        # times in one race (Deep Forest, 6 Sep 2026). Symmetric now: the cut
        # waits for the next accepted reading to agree.
        self._pending_fresh: tuple[float, Reading] | None = None
        # Whether the last `_keep` HELD its reading rather than refusing it.
        # The callers count a refusal as a blind sample; a held reading is a
        # good reading awaiting its second, and must not.
        self._held_last = False
        # **Where the last good reading found the gauge**, so the next grab
        # searches there before searching the whole frame (`locate_gauge_near`).
        # A search hint, never a reading. Dropped whenever a grab finds no
        # gauge or a reading is refused, so a wrong place cannot outlive the
        # frame that disagrees with it - rule 10.
        self._gauge_near: dict | None = None

    def new_session(self) -> None:
        """Forget what has already been said about the gauge being blind.

        **The sampler outlives the session.** It is cached on the controller
        and built once, so without this a practice run that went blind spends
        the one-shot announcement and the race that follows says nothing at
        all - which is precisely the Road Atlanta failure, moved one session
        later. Cheap enough to call whenever a session opens.
        """
        self._blind = 0
        self._said_blind = None
        self._said_stuck = False
        self._dim_peaks.clear()
        self._nothing_seen = 0
        self.stood_down = False
        # **The comparison baseline is session state and it never was.** The
        # series and the held reading outlived the session along with the
        # sampler, so a race opened judging its fresh set against whatever
        # practice left behind - and the seed guard added above would be
        # defeated by a stale series it never gets to re-seed. A stint that
        # ended is not evidence about the one starting.
        self.series = []
        self._refused_running = 0
        self._latest = None
        self._pending_fresh = None
        self._gauge_near = None

    def start(self) -> None:
        """Start the reader. A no-op while one is already running.

        **Each thread owns its stop event rather than sharing the sampler's.**
        The old pair could resurrect the thread it had just been asked to kill:
        `stop` set the shared flag, joined for two seconds and cleared
        `_thread` whether or not the join had succeeded - and an OBS grab
        measures about 2050 ms, so it usually had not. `start` then saw `None`,
        called `_stop.clear()`, and the flag the surviving thread was about to
        read on its next pass was gone. One live thread became two, both
        driving the same unlocked `series` and `_latest`.

        That is the 30 Aug practice crash arriving one session boundary at a
        time instead of one lap at a time - `HudSession.sampler` had the
        per-lap version of it, and 13 threads took the process down with an
        access violation. Until that fix this path was unreachable, because
        `HudSession.stop` never found a sampler to stop.

        With an event per thread nothing `start` does can reach a departing
        thread: its flag stays set and it leaves when its grab returns.
        """
        if self._thread is not None and self._thread.is_alive():
            return
        stop = self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(stop,),
                                        name="hud-wear", daemon=True)
        self._thread.start()

    def stop(self) -> bool:
        """Ask the reader to stop. True if it had actually stopped.

        **A timed-out join is no longer silent, and no longer a leak.** The
        thread is released either way - a fresh one may now start safely
        alongside it, since it cannot be resurrected and writes nothing
        further - but a caller that wanted the gauge quiet is told that it is
        not, rather than left to assume it.

        No sentinel is queued any more. The loop wakes every `QUEUE_WAIT_S`
        regardless, and a `None` left behind by a thread that had already gone
        would be drawn by the *next* thread and stop it dead on its first pass
        - a sampler that is silently not running at all.
        """
        thread, self._thread = self._thread, None
        self._stop.set()
        if thread is None:
            return True
        thread.join(timeout=STOP_JOIN_S)
        if thread.is_alive():
            _log.warning(
                "hud-wear: the reader was still mid-grab after %.1fs. It has "
                "been released and will exit when that grab returns; it files "
                "nothing further.", STOP_JOIN_S)
            return False
        return True

    def request(self, lap_id: int) -> None:
        """Ask for a reading. Never blocks, never raises, may be dropped."""
        if self.stood_down or self._thread is None:
            return
        try:
            self._queue.put_nowait(lap_id)
        except queue.Full:
            # The previous lap's reading has not finished. Drop the older one:
            # the newer crossing is the one whose wear is still true.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(lap_id)
            except (queue.Empty, queue.Full):
                pass

    def _run(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                lap_id = self._queue.get(timeout=QUEUE_WAIT_S)
            except queue.Empty:
                # Nothing asked. Free-running turns the idle wait into a
                # sample; without it the loop simply goes round again.
                lap_id = _FREE_RUN
            if lap_id is None or stop.is_set():
                return
            try:
                if lap_id is _FREE_RUN:
                    self._free_run(stop)
                else:
                    self._sample(lap_id, stop)
            except Exception as exc:                         # noqa: BLE001
                # Nothing here may reach the caller. The lap is recorded
                # whatever the gauge does.
                _log.warning(f"hud-wear: unhandled {type(exc).__name__}: {exc}")

    def _free_run(self, stop: threading.Event | None = None) -> None:
        """One un-asked-for sample, kept but never filed against a lap."""
        if not self._interval_s or self.stood_down:
            return
        now = time.monotonic()
        if self._latest is not None and now - self._latest[0] < self._interval_s:
            return
        reading, _ = self._read()
        if stop is not None and stop.is_set():
            # **A grab that outlived its session may not be filed.** `_read`
            # blocks for about two seconds on OBS, so a thread asked to stop
            # part way through still comes back holding a frame - of the
            # session that has just ended. Keeping it seeds the next session's
            # comparison series with the last one's tyres, which is the
            # stale-state failure of CLAUDE.md rule 11 and the reason
            # `new_session` exists.
            return
        if reading.ok:
            if not self._keep(now, reading) and not self._held_last:
                self._saw_nothing()
            return
        self._saw_nothing()
        if now - self._last_free_log > FREE_RUN_LOG_SPACING_S:
            # Sparse, deliberately. A shut projector is one fact, not one fact
            # every two seconds.
            self._last_free_log = now
            _log.warning(f"hud-wear: no free-run reading: {reading.reason}")

    def _read(self) -> tuple[Reading, bool]:
        """Grab and transcribe. Returns (reading, the source itself failed).

        **The two failures are not the same failure and must not be counted
        together.** A source that cannot produce a frame is a connection
        problem - OBS shut, the projector closed - and it is what standing down
        exists for. A frame that arrives and cannot be read is a paused game or
        a menu, which is a normal thing that happens several times a session.
        """
        frame, why = self._source.grab()
        if frame is None:
            return Reading(None, why), True
        # Decoded once for everyone riding along (critic pass 1: the pit wall
        # and the panel readers each decoded the same grab).
        whole = (whole_frame(frame)
                 if self._on_frame is not None or self._on_hygro is not None
                 or self._on_compound is not None
                 or self._on_damage is not None else None)
        if self._on_frame is not None:
            if whole is None:
                # **Said once, not swallowed.** A passenger that wants the
                # board and is being handed a gauge crop will find no board on
                # every frame forever, which is indistinguishable from a race
                # in which nobody pitted.
                if not self._said_crop_only:
                    self._said_crop_only = True
                    _log.warning(
                        "hud-wear: the grab is a gauge crop, not the screen, "
                        "so nothing riding along can see the leaderboard. Ask "
                        "the source for whole frames if you need it.")
            else:
                try:
                    self._on_frame(whole)
                except Exception:
                    _log.exception("hud-wear: frame passenger failed")
        reading = read_gauge(frame, near=self._gauge_near)
        self._note_gauge_at(reading)
        if (self._on_hygro is not None or self._on_compound is not None
                or self._on_damage is not None):
            self._pass_hygro(frame, reading, whole=whole)
        return reading, False

    def _note_gauge_at(self, reading: Reading) -> None:
        """Remember where a located gauge read, or forget it."""
        seen = (reading.located and reading.bars is not None
                and reading.wear is not None
                and any(v is not None for v in reading.wear.values()))
        was = self._gauge_near
        self._gauge_near = reading.bars if seen else None
        if seen and was is None:
            # Logged when set, not only when lost: the hint decides where the
            # next search looks, so the log has to show what it is.
            _log.info("hud-wear: gauge found at %s - searching there first",
                      layout_bounds(reading.bars))

    def _pass_hygro(self, frame, reading: Reading, *, whole=None) -> None:
        """Read the hygrometer beside the bars this grab found, and hand it on.

        **Only on a whole frame.** At the calibrated canvas the source grabs the
        gauge rectangle alone, and the hygrometer is outside it - that is
        "cannot see", said as such, never a dry reading.
        """
        from pitcrew.telemetry.hud_compound import CompoundRead, read_compound
        from pitcrew.telemetry.hud_damage import DamageRead, read_damage
        from pitcrew.telemetry.hygrometer import HygroReading, read_hygrometer

        if whole is None and reading.bars is not None:
            whole = whole_frame(frame)
        if reading.bars is None:
            whole = None
        why = (reading.reason or "gauge not found" if reading.bars is None
               else "grab is a gauge crop" if whole is None else "")
        if self._on_hygro is not None:
            try:
                self._on_hygro(HygroReading(None, None, why) if why
                               else read_hygrometer(whole, reading.bars))
            except Exception:
                _log.exception("hud-wear: hygrometer passenger failed")
        if self._on_compound is not None:
            try:
                self._on_compound(CompoundRead(None, why=why) if why
                                  else read_compound(whole, reading.bars))
            except Exception:
                _log.exception("hud-wear: compound label passenger failed")
        if self._on_damage is not None:
            try:
                self._on_damage(DamageRead(None, None, why=why) if why
                                else read_damage(whole, reading.bars))
            except Exception:
                _log.exception("hud-wear: damage icon passenger failed")

    def _coherent(self, wear: dict) -> tuple[bool, bool, str]:
        """Can this reading follow the last one on a real set of tyres?

        Returns `(accept, fresh_set, why_not)`. See `GAUGE_SLACK` for the
        account of the pit-lane gauge that made this necessary.

        **The comparison is against the last ACCEPTED reading**, which is why
        a refusal must not become `_latest`: one relocated gauge would
        otherwise become the baseline every later reading is judged against,
        and the whole stint after it would read as incoherent.

        **The rule itself is `coherent`**, module level and shared with
        `tools/read_hud_wear.py`. Two copies of "can a tyre do that" is two
        answers to the same question, and the offline tool has already
        recorded readings this one would have refused.
        """
        return coherent(self.series[-1][1] if self.series else None, wear)


    def _keep(self, at: float, reading: Reading) -> bool:
        """Hold a good reading, and cut the series where a fresh set went on.

        Returns whether it was kept. A reading the gauge cannot physically
        have produced is refused here rather than filed - see `_coherent`.
        """
        self._held_last = False
        accept, fresh, why = self._coherent(reading.wear)
        if not accept:
            # The place may be what is wrong. Search the whole next frame.
            self._gauge_near = None
            self._refused_running += 1
            _log.warning("hud-wear: reading refused - %s", why)
            if self._refused_running >= REFUSALS_BEFORE_RESEED:
                # **The baseline is the reading that is wrong.** See
                # `REFUSALS_BEFORE_RESEED`. Said loudly rather than quietly:
                # the series is being thrown away, so any wear slope built on
                # it is gone too, and the driver's gauge figures restart from
                # here.
                _log.warning(
                    "hud-wear: %d readings in a row refused against one "
                    "baseline (%s) - so the baseline is what is wrong, not "
                    "the gauge. Dropping it and re-seeding from the next "
                    "reading; the wear series so far is discarded.",
                    self._refused_running,
                    ", ".join(f"{k.upper()} {v * 100:.0f}%"
                              for k, v in sorted(self.series[-1][1].items())
                              if v is not None) if self.series else "none")
                self.series = []
                self._latest = None
                self._refused_running = 0
            return False
        self._refused_running = 0
        self._nothing_seen = 0
        if fresh:
            pending = self._pending_fresh
            if pending is None:
                # The first reading that looks like a new set: held, not
                # believed. The series and the held reading stay the old
                # set's until the next reading says the same.
                self._pending_fresh = (at, reading)
                self._held_last = True
                _log.info("hud-wear: a fresh-set reading (worst %.0f%%) is "
                          "held until the next reading agrees",
                          max(v for v in reading.wear.values()
                              if v is not None) * 100)
                return False
            self._pending_fresh = None
            _log.info("hud-wear: fresh set - every corner back to "
                      "%.0f%% or less, on two readings",
                      max(v for v in reading.wear.values() if v is not None)
                      * 100)
            self.series = [(pending[0], dict(pending[1].wear))]
        else:
            # A reading that follows the OLD series: whatever was held as a
            # fresh set was the locator, not the tyres.
            if self._pending_fresh is not None:
                _log.info("hud-wear: the held fresh-set reading did not repeat "
                          "- discarded")
            self._pending_fresh = None
        self._latest = (at, reading)
        self.series.append((at, dict(reading.wear)))
        # **Refusals were logged and accepts were not, which is why the
        # ratchet was invisible.** The Fuji log carries 432 refusals naming
        # figures from 19% to 76% and not one line saying what they were being
        # judged against - so a baseline climbing on unlogged accepts looked
        # exactly like a gauge that had simply stopped working. The number that
        # sets the bar has to be as visible as the ones it rejects.
        #
        # Guarded rather than left to the logger to discard: the join and the
        # sort run whichever way the level is set, and this is the sampler's
        # own loop. At the 2-10 s intervals raced that is nothing, but it is
        # on a path that can be driven as fast as the source will answer.
        if _log.isEnabledFor(logging.INFO):
            _log.info("hud-wear: reading accepted - %s (worst %.0f%%)",
                      ", ".join(f"{k.upper()} {v * 100:.0f}%"
                                for k, v in sorted(reading.wear.items())
                                if v is not None),
                      max((v for v in reading.wear.values() if v is not None),
                          default=0.0) * 100)
        return True

    def latest(self) -> Reading | None:
        """The most recent good reading, or None."""
        return self._latest[1] if self._latest else None

    def _sample(self, lap_id: int,
                stop: threading.Event | None = None) -> None:
        now = time.monotonic()
        held = self._latest
        if (self._interval_s
                and held is not None
                and now - held[0] <= self._interval_s + STALE_MARGIN_S):
            # **The last sample before the crossing is this lap reading**, the
            # same rule the offline tool applies to a recorded race. Nothing is
            # grabbed on the crossing at all.
            reading = held[1]
        else:
            reading, source_failed = self._read()
            if stop is not None and stop.is_set():
                return      # see `_free_run`: a grab that outlived its session
            if source_failed:
                self._failed(f"lap {lap_id}: {reading.reason}")
                return
            if reading.ok and not self._keep(now, reading):
                if self._held_last:
                    # A fresh-set reading held for its second. Not blind, not
                    # refused, and not this lap's figure either: the price of
                    # not cutting the series on one all-zero misread is one
                    # lap's point after a real change, in per-lap sampling.
                    _log.info("hud-wear: lap %s: fresh-set reading held for "
                              "the next to agree", lap_id)
                    return
                # Readable, and not of the gauge. **Not blind and not a source
                # failure**: the source is fine and the next grab may well be
                # good, so this does not tell the driver the gauge has gone
                # dark. `_keep` has already said what was wrong with it. It
                # does count toward `BLIND_SAMPLES_BEFORE_STANDING_DOWN`,
                # because a sample that produced no reading produced no
                # reading whatever the reason.
                self._saw_nothing()
                return
        if not reading.ok:
            # A dimmed or unreadable frame is not a connection failure - it is
            # a normal thing that happens when the game is paused - so it does
            # not count toward standing down.
            _log.warning(f"hud-wear: lap {lap_id}: {reading.reason}")
            self._saw_nothing()
            self._note_blind(reading)
            return
        self._blind = 0
        self._said_blind = None
        self._said_stuck = False
        self._dim_peaks.clear()
        self._failures = 0
        self._write(lap_id, reading.wear)
        worst = max((v for v in reading.wear.values() if v is not None),
                    default=None)
        _log.info(f"hud-wear: lap {lap_id}: "
            + ", ".join(f"{k.upper()} "
                        + ("--" if v is None else f"{v * 100:.0f}%")
                        for k, v in sorted(reading.wear.items()))
            + (f" (worst {worst * 100:.0f}%)" if worst is not None else ""))
        if self._status:
            self._status(reading)

    def _note_blind(self, reading: Reading) -> None:
        """A crossing produced no reading. Decide whether to say so, and why.

        **Two different faults wear the same message today.** A genuinely
        dimmed frame - paused, mid-transition - varies from grab to grab. A
        rectangle that is not on the gauge at all reports the *same* peak every
        time, because it is the same pixels. Measured at Road Atlanta on
        23 Aug 2026: sixteen refusals, every one of them "peaks at 81", in two
        blocks either side of stretches that read perfectly.

        **And it says so out loud.** He raced the whole thing believing the
        instrument was watching. Silence from a perception layer reads as
        "nothing to report"; CLAUDE.md's standard is that it has to read as
        "I cannot see it", because only one of those is actionable.

        **The diagnosis is hedged, because it is an inference over three
        samples.** A constant peak also comes from a black frame during a
        capture-card dropout, and from `ScreenSource` grabbing a window parked
        over the projector - where the rectangle is right and the remedy is to
        move the window. CLAUDE.md rule 5 covers a derived diagnosis as much as
        a derived number, so this offers the likely cause rather than asserting
        it.

        **Worker thread.** `on_status` is called from here, so a consumer must
        not touch Qt directly - see `PitCrewController._hud_status`.
        """
        self._blind += 1
        if reading.peak is not None:
            self._dim_peaks.append(reading.peak)
            del self._dim_peaks[:-IDENTICAL_PEAKS_MEAN_STATIC]
        stuck = (len(self._dim_peaks) >= IDENTICAL_PEAKS_MEAN_STATIC
                 and len(set(self._dim_peaks)) == 1)
        if stuck and not self._said_stuck:
            self._said_stuck = True
            _log.warning(
                "hud-wear: the last %s refusals all peaked at exactly %s. A "
                "dimmed game frame varies; an identical peak is the same "
                "pixels every time, so the gauge is not in the rectangle. "
                "**In VR that is expected and is not a fault** - GT7 draws the "
                "HUD on the car's dashboard in 3D, so it leaves the calibrated "
                "rectangle whenever the driver looks away, and a left-hander "
                "can hide it completely. The answer there is free-running "
                "(`hud_sample_interval_s`), not a capture fix: a sample every "
                "two seconds only needs the few where he is looking forward. "
                "On a flat screen, check nothing is parked over the projector "
                "window and that the capture region is right.",
                IDENTICAL_PEAKS_MEAN_STATIC, self._dim_peaks[-1])
        if self._blind < BLIND_CROSSINGS_BEFORE_SAYING:
            return
        # **Said once, and again only if the diagnosis improves.** Repeating
        # one message every lap is the nine-box-calls defect with a second
        # mouth. But the first announcement can land before enough peaks exist
        # to tell the two faults apart - a single refusal with no peak at all,
        # a canvas-size refusal, is enough to delay it - and a driver told
        # "unreadable" when the answer is "something is over your projector"
        # has been given the wrong job.
        # **Careful what this blames.** In VR the gauge moves with head
        # position, so "the capture is wrong" is actively misleading - the
        # capture is fine and the gauge is simply not being looked at. The
        # message names the symptom and leaves the cause to the log, which has
        # the room to separate the VR case from the flat-screen one.
        note = GAUGE_NOT_IN_FRAME if stuck else (
            reading.reason or GAUGE_UNREADABLE)
        if self._said_blind == note:
            return
        self._said_blind = note
        if self._status:
            # **A Reading with no wear IS the "I cannot see it" message.**
            # `wear=None` rather than zeros, so nothing downstream can read a
            # refusal as a measurement.
            self._status(Reading(None, blind_note(note),
                                 peak=reading.peak))

    def _saw_nothing(self) -> None:
        """One more sample that produced no reading. Stand down at the cap.

        **Said once, with the route to the number rather than only its
        absence.** The gauge is the only ground truth for tyre wear that exists
        - GT7 broadcasts no wear channel in any packet format - so "I cannot
        see it" is not the end of the sentence. In VR it can be read afterwards
        off a chase-view replay, where the HUD is back in screen space, and
        that is a thing the driver can act on.
        """
        self._nothing_seen += 1
        if (self.stood_down
                or self._nothing_seen < BLIND_SAMPLES_BEFORE_STANDING_DOWN):
            return
        self.stood_down = True
        _log.warning(
            "hud-wear: %s samples in a row produced no reading, so the gauge "
            "is not visible this session and sampling stops here. **This is "
            "expected in VR** - GT7 draws the HUD on the car's dashboard in "
            "3D, so a fixed rectangle cannot hold it. Nothing is lost that "
            "was not already lost: read it off a chase-view replay afterwards "
            "with `tools/read_hud_wear.py --session <id> --video <file>`, "
            "where the HUD is in screen space and the whole race is "
            "available. Until then this session contributes no measured wear.",
            self._nothing_seen)
        if self._status:
            self._status(Reading(None, "no tyre gauge this session - it will "
                                       "have to come from the replay"))

    def _failed(self, message: str) -> None:
        self._failures += 1
        _log.warning(f"hud-wear: {message}")
        if self._failures >= MAX_CONSECUTIVE_FAILURES:
            self.stood_down = True
            _log.warning(f"hud-wear: stood down after {self._failures} consecutive "
                f"failures - it will not be retried this session")
