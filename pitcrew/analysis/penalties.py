"""Track-limit penalties served, read off the frames.

GT7 serves a time penalty by making the driver slow to a crawl inside a
marked zone - so a served penalty is a hard brake at speed on a stretch of
road where nothing is braked for. Six laps of the Daytona A/B runs of 4 Sep
2026 carry one at about 5,200 m on the banking - full brake from 270 km/h to
about 190, lateral g near zero, no pit lane - and the app flagged none of
them, so those laps went into the pace population as driven, and the next
lap's front stretch with them.

### What is read, and what is not

* **Read:** a brake run - `BRAKE_PCT` or more, for `MIN_BRAKE_S` or longer -
  that starts above `MIN_SPEED_KPH` with the car going straight
  (`MAX_LAT_G`), and starts outside every corner's braking approach in the
  circuit's corner model. The Bus Stop brake at 3,700 m on the same laps
  starts 80-120 m before T5's `start_m` and is excluded by `APPROACH_M`.
* **Not read:** the penalty indicator on the HUD. No captured frame of one
  exists to calibrate a reader against, and a reader with no calibration
  frame is the fabricated-zero defect in a new shape (plan §9a).
* **Derived:** `lost_s`, the time given away from the brake until the car
  is back to the speed it braked from - `sum(dt * (v_entry - v) / v_entry)`
  - is a model of the penalty's cost, not a reading, and is exported under
  that heading.

A lap with no frames on file gets `None`, never zero (CLAUDE.md rule 3).

### What this shape is NOT, and what is done about each

The shape above is a *hard brake at speed where the model says nothing is
braked for*. Four other things make that shape, and none of them is a
penalty. Left alone, each one reached the driver as **"Penalty served. About
0.3 seconds."** - a flat assertion, at medium confidence, under a helmet -
and each one reached the lap row as a `1` that nothing downstream could tell
from a reading.

**Every claim below is counted off the archive**, and
`tools/find_penalties.py --session N` reproduces any line of it. Critic
passes 6 and 7 both reasoned about this detector from what its shape COULD
do; the numbers here are what it has actually done.

1. **An out-lap, or the session's opening lap.** This is the big one, and
   neither critic found it: **more than twenty of the flags on file are on
   lap 1 of a practice session** - four of them on one Monza lap (session 83:
   600, 1,800, 3,600 and 4,800 m), five on one Spa lap (session 91). Nobody
   serves four penalties on one lap. They are a car leaving the box, braking
   to a crawl to check something, or joining the circuit. Sessions 83, 91 and
   102 carry `is_out_lap = 1` on that lap; session 88's is not flagged and is
   9% slower than lap 2, which is the opening-lap defect `flag_opening_lap`
   exists for. So the controller does not read a pit lap, an out lap, or lap
   one. **The cost, stated:** a penalty served on lap one of a race is
   missed. There is no instance of one on file, and the alternative is four
   fabricated calls off an installation lap.
2. **An avoidance stab** - lifting hard behind a spinning car on a straight.
   Nothing in the feed distinguishes it, and nothing here pretends to: the
   call says "Possible penalty served", goes out LOW, and `Call.spoken()`
   ends it "Unconfirmed." Every caller that speaks it must keep it that way.
   The *lap* still leaves the pace and burn populations, and that half needs
   no hedge - whatever caused it, a lap with a full-brake-to-a-crawl in it is
   not evidence of pace.
3. **A wet brake taken early** for a corner the model does contain, beginning
   further back than `APPROACH_M`. Every frame this detector was calibrated
   against is dry, and the app cannot read that it is raining - the
   hygrometer reader was struck for exactly that reason. The controller
   stands the detector down where the event's record **declares** wet
   conditions. It does NOT stand down where rain is merely *possible*: seven
   of the eleven events on file are `changeable`/`Random`, **including event
   10, which is where all eight verified penalties came from**, so refusing
   on the possibility would delete the feature at every circuit where it has
   ever been shown to work. A possibility is not a reading, and turning one
   into a silence is the fabricated value with the sign flipped.
4. **A corner missing from the model.** Every corner model on file is
   `auto-segment`, so this is the one that would repeat: the same brake, at
   the same place, on every lap. `RoadNotPenalty` below is the test, and its
   threshold comes off the archive rather than off intuition:

   * **No place on file is flagged on every lap.** The highest rate anywhere
     is 5 of 10 (session 118, Daytona, laps 2/4/6/8/10) and the frames say
     plainly it is not a corner - laps 1, 3, 5, 7 and 9 carry **no brake at
     all** through 5,100-5,400 m at a flat 269 km/h, and all twenty laps of
     the race that followed (session 127) carry none. A corner is braked
     every lap; this is braked every other lap.
   * **The longest run of consecutive laps at one place is TWO** - session
     114, laps 5 and 6 at Daytona, both real. So "two in a row is the road",
     which is what this file said first, deletes a real pair. Four in a row
     deletes nothing on the archive and still catches a corner braked on
     every lap by its fourth lap.
   * Refusing every `auto-segment` model instead - critic 6's suggestion -
     would refuse all nine models on file and delete the feature outright.

   And the retirement can itself be retired (CLAUDE.md rule 10): a place that
   then runs `ROAD_RUN_LAPS` laps WITHOUT a flag is not braked every lap
   after all, so it goes back. Every decision is reported to the caller to be
   logged - the accepts too, not only the refusals.
"""
from __future__ import annotations

from dataclasses import dataclass

BRAKE_PCT = 80.0
MIN_SPEED_KPH = 180.0
# Daytona's banking loads the car to about 0.3 g laterally while it is going
# straight (memory: the banking is vertical load, 1.92 g sustained, with
# lateral g near 0.05-0.3); the 4 Sep session 121 lap-3 penalty peaked at
# 0.312 and was missed at 0.30. Half a g is still well inside "not
# cornering" - the Bus Stop brake, in a straight line, peaks at 0.25, and it
# is the corner window that excludes it, not this.
MAX_LAT_G = 0.50
MIN_BRAKE_S = 0.5
# How far before a corner's `start_m` its braking zone may begin.
APPROACH_M = 250.0
# Recovery is judged over at most this long after the brake began.
MAX_RECOVERY_S = 25.0
SAMPLE_HZ = 60.0
# Two flags this far apart round the lap are the same stretch of road. The
# nineteen on file at Daytona's banking exit span 5,194-5,310 m - 116 m -
# because the brake is picked up wherever the car happens to be, so anything
# under about 120 m would split one place into two and never see a run.
#
# **It is WIDER than the gap between some pairs of corners on file** - Road
# Atlanta's closest pair is 91.7 m apart, Red Bull Ring short's 99.2 m, and
# Spa's 109.4 m. That is a real cost and it is the acceptable direction: the
# only thing this constant groups is places to RETIRE, so two adjacent
# corners the model is missing would be retired together, which is the right
# answer for both of them.
SAME_PLACE_M = 150.0
# Consecutive laps flagged at one place before it is called a corner rather
# than a penalty - and the clean run that puts it back. Four, off the
# archive: the longest real run on file is two (session 114, Daytona, laps 5
# and 6), so four deletes nothing that has ever happened and still catches a
# corner braked on every lap within four laps of the green.
ROAD_RUN_LAPS = 4
# Words in an event's `weather` that DECLARE the session wet, so the detector
# stands down (item 3 of the docstring). `changeable` is deliberately not one
# of them: it is a possibility, and seven of the eleven events on file carry
# it, including the one every verified penalty came from.
WET_WORDS = ("wet", "rain", "damp", "storm")


@dataclass(frozen=True)
class Penalty:
    """One served penalty, where and what it cost."""
    at_m: float
    brake_s: float
    speed_from_kph: float
    speed_to_kph: float
    lost_s: float           # derived - see the module docstring


def _windows(corners) -> list[tuple[float, float]]:
    out = []
    for corner in corners or ():
        start = corner.get("start_m") if isinstance(corner, dict) else \
            getattr(corner, "start_m", None)
        end = corner.get("end_m") if isinstance(corner, dict) else \
            getattr(corner, "end_m", None)
        if start is None or end is None:
            continue
        out.append((float(start) - APPROACH_M, float(end)))
    return out


def _in_a_corner(at_m: float, windows) -> bool:
    return any(lo <= at_m <= hi for lo, hi in windows)


def read_columns(rows, field_names, corners, *,
                 sample_hz: float = SAMPLE_HZ) -> list[Penalty] | None:
    """From the recorder's column-array rows, while they are still in hand."""
    index = {name: position for position, name in enumerate(field_names)}
    wanted = ("lap_distance_m", "speed_kph", "brake_pct", "lat_g")
    if any(name not in index for name in wanted):
        return None
    frames = [{name: row[index[name]] for name in wanted} for row in rows]
    return read_rows(frames, corners, sample_hz=sample_hz)


def read_rows(frames, corners, *, sample_hz: float = SAMPLE_HZ
              ) -> list[Penalty] | None:
    """Every penalty served on one lap's frames, or None without frames.

    `frames` are dicts with `lap_distance_m`, `speed_kph`, `brake_pct` and
    `lat_g`; `corners` are the corner model's entries (`start_m`, `end_m`).
    An empty list is a lap with frames and no penalty; `None` is a lap the
    detector could not look at.
    """
    rows = [f for f in (frames or ())
            if f.get("lap_distance_m") is not None
            and f.get("speed_kph") is not None]
    if not rows:
        return None
    windows = _windows(corners)
    dt = 1.0 / sample_hz
    out: list[Penalty] = []
    i, n = 0, len(rows)
    while i < n:
        f = rows[i]
        if (f.get("brake_pct") or 0.0) < BRAKE_PCT:
            i += 1
            continue
        j = i
        while j < n and (rows[j].get("brake_pct") or 0.0) >= BRAKE_PCT:
            j += 1
        run = rows[i:j]
        entry = run[0]
        brake_s = len(run) * dt
        straight = all(abs(r.get("lat_g") or 0.0) <= MAX_LAT_G for r in run)
        if (brake_s >= MIN_BRAKE_S and entry["speed_kph"] >= MIN_SPEED_KPH
                and straight
                and not _in_a_corner(float(entry["lap_distance_m"]), windows)):
            v_entry = float(entry["speed_kph"])
            lost = 0.0
            k = i
            limit = i + int(MAX_RECOVERY_S * sample_hz)
            while k < n and k < limit:
                v = float(rows[k]["speed_kph"])
                if k > j and v >= v_entry:
                    break
                lost += dt * max(0.0, v_entry - v) / v_entry
                k += 1
            out.append(Penalty(at_m=float(entry["lap_distance_m"]),
                               brake_s=brake_s, speed_from_kph=v_entry,
                               speed_to_kph=float(run[-1]["speed_kph"]),
                               lost_s=lost))
        i = j
    return out


@dataclass(frozen=True)
class Verdict:
    """One lap's verdict from `RoadNotPenalty`: what to keep and what to say.

    `give_back` are laps a PREVIOUS call kept and this one withdraws - pass
    each to `RaceCoordinator.forget_penalty` and correct its stored row.
    `notes` is every decision this lap in words, accepts included, for the
    log. CLAUDE.md rule 10: the ratchet at Fuji was invisible for a whole
    race because only the refusals were written down.
    """
    kept: tuple
    give_back: tuple[int, ...]
    notes: tuple[str, ...]


class RoadNotPenalty:
    """Which flagged places are a corner the model is missing. One session.

    Item 4 of the module docstring, and its numbers. A served penalty happens
    on a lap; a corner is there on every lap. So a place flagged on
    `ROAD_RUN_LAPS` CONSECUTIVE laps is the road: it is retired, and every
    lap of the run is handed back, because each was struck on a reading this
    has just withdrawn.

    **And the retirement retires** (CLAUDE.md rule 10, which is about exactly
    this: "a rule that refuses a reading must be able to refuse its own
    baseline"). A retired place that then runs `ROAD_RUN_LAPS` laps with no
    flag is not braked every lap, so it was not a corner; it goes back and
    the next flag there is a penalty again. Without that this class is a
    one-way latch that swallows every real penalty at Daytona's banking exit
    for the rest of a race, and writes `penalties_served = 0` - a positive
    claim of "looked at and clean" - on every lap of it.

    **What it costs, stated.** The first `ROAD_RUN_LAPS - 1` laps of a
    missing corner are still flagged and still spoken, at LOW with
    "Unconfirmed." on the end. There is no way to tell the shape from one
    lap: a real penalty arrives exactly once too, and refusing every first
    sighting refuses all nineteen on file. Three hedged sentences at the
    start of a race is the price of not deleting a real pair on lap 5 and 6
    the way "two in a row" did.

    **`note_lap` must be called for EVERY lap the detector looked at**,
    including the ones with nothing on them - that is what a run is counted
    against. `filter` does it for you.

    **CLAUDE.md rule 11.** One instance per session; the controller keys it
    on the session id beside `_corner_windows_cache` for the same reason.
    """

    def __init__(self, same_place_m: float = SAME_PLACE_M,
                 run_laps: int = ROAD_RUN_LAPS) -> None:
        self._same_place_m = float(same_place_m)
        self._run_laps = int(run_laps)
        # place -> the consecutive laps flagged there, newest last
        self._run: dict[float, list[int]] = {}
        # place -> laps run since it was retired with nothing flagged there
        self._retired: dict[float, int] = {}

    def _near(self, places, at_m: float):
        for place in places:
            if abs(place - at_m) <= self._same_place_m:
                return place
        return None

    def retired(self) -> tuple[float, ...]:
        """The places this session currently calls corners, for the log."""
        return tuple(sorted(self._retired))

    def filter(self, lap_num: int, found) -> Verdict:
        """One lap's verdict. `found` is that lap's `Penalty` list.

        An empty list is a lap the detector looked at and found nothing on,
        which is evidence about every place. `None` is a lap it could not
        look at - no frames, a pit lap, a session it stood down on - and is
        not evidence either way, so it BREAKS a run rather than extending
        it: the same argument `GapTrend._window` makes about fitting a line
        through a hole in the readings, and the safe direction, because a
        hole can then only delay a retirement and never cause one.
        """
        lap_num = int(lap_num)
        if found is None:
            return Verdict((), (), ())
        kept, give_back, notes = [], [], []
        flagged_here = set()

        for penalty in found:
            at_m = float(penalty.at_m)
            place = self._near(self._retired, at_m)
            if place is not None:
                self._retired[place] = 0        # flagged again: the run breaks
                flagged_here.add(place)
                notes.append(
                    f"lap {lap_num}: the brake at {at_m:.0f} m is inside a "
                    f"place already read as a corner ({place:.0f} m) - not "
                    f"counted as a penalty")
                continue
            place = self._near(self._run, at_m)
            if place is None:
                place = at_m
                self._run[place] = []
            run = self._run[place]
            if run and run[-1] != lap_num - 1 and run[-1] != lap_num:
                run.clear()                     # the run was broken
            if not run or run[-1] != lap_num:
                run.append(lap_num)
            flagged_here.add(place)
            if len(run) >= self._run_laps:
                # Braked every lap for a run: that is the road, not a
                # penalty served four times running.
                self._retired[place] = 0
                give_back.extend(l for l in run if l != lap_num)
                notes.append(
                    f"lap {lap_num}: {place:.0f} m has been flagged on "
                    f"{len(run)} consecutive laps {run} - a penalty is served "
                    f"on a lap and a corner is there on all of them, so this "
                    f"is a corner the model is missing. Laps "
                    f"{[l for l in run if l != lap_num]} go back into the pace")
                self._run.pop(place, None)
                continue
            notes.append(
                f"lap {lap_num}: penalty at {at_m:.0f} m kept - "
                f"{len(run)} consecutive lap(s) at this place, "
                f"{self._run_laps} would be a corner")
            kept.append(penalty)

        # The laps that did NOT flag a place are what retires a retirement
        # and what breaks a run.
        for place in list(self._run):
            if place not in flagged_here:
                self._run[place] = []
        for place in list(self._retired):
            if place in flagged_here:
                continue
            self._retired[place] += 1
            if self._retired[place] >= self._run_laps:
                self._retired.pop(place)
                notes.append(
                    f"lap {lap_num}: {place:.0f} m has run {self._run_laps} "
                    f"laps with no brake flagged - it is not braked every lap, "
                    f"so it is not a corner and it goes back to being readable")
        return Verdict(tuple(kept), tuple(dict.fromkeys(give_back)),
                       tuple(notes))
