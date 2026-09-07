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

1. **A pit lap, an out lap, or the session's opening lap.** This is the big
   one, and neither critic found it. Counted over the whole archive, of 270
   flags: **141 are lap one of a practice session** - four of them on one
   Monza lap (session 83: 600, 1,800, 3,600 and 4,800 m), five on one Spa lap
   (session 91). Nobody serves four penalties on one lap. They are a car
   leaving the box, braking to a crawl to check something, or joining the
   circuit. Sessions 83, 91 and 102 carry `is_out_lap = 1` on that lap;
   session 88's is not flagged and is 9% slower than lap 2, which is the
   opening-lap defect `flag_opening_lap` exists for. A further 16 are pit
   laps, and three or four at a time - a car in the lane, not a driver
   serving four penalties on one lap either.

   **What it costs, counted rather than asserted:** 11 race flags on lap one
   are given up. None of them has been confirmed to be a penalty and none was
   examined one by one, so this is a real loss and not a demonstrated
   nothing. **Out laps cost nothing at all** - there is not one out-lap flag
   in the archive, in a race or in practice; every race flag the gate removes
   is on a pit lap.
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
4. **A corner missing from the model, which is real and is common.** Every
   corner model on file is `auto-segment` and several are sparse: Yas Marina
   has six corners with a 1.6 km gap between T4 and T5, and Spa's 24 h layout
   six for 7 km. The driver brakes in those gaps on every lap, and it reads
   as a penalty on every lap. `RoadNotPenalty` below is the test.

   **The question that separates them is not how OFTEN a place is flagged.
   It is whether the other laps brake there at all.** Two dead ends were
   tried first and both are on the record, because both looked right:

   * *"Two consecutive laps is the road"* deletes a real pair - session 114,
     Daytona, laps 5 and 6.
   * *"Four consecutive laps is the road"* rested on the claim that no place
     on file is flagged on every lap and that the longest run is two. **Both
     were false**, from a sweep that silently began at session 82: Yas
     Marina's 3,470 m is flagged on 10 of the 15 laps of the session 44 RACE
     with a run of NINE, and it is beyond doubt a corner - all fifteen laps
     brake there at 83-100%, 250 km/h down to about 105. Any run threshold
     long enough to spare it catches nothing at all.

   Counting brakes rather than flags separates the two populations cleanly,
   because a corner is braked on every lap and a penalty is not:

   | place | flagged | braked | laps | share |
   |---|---|---|---|---|
   | Yas 3,470 m (s44, race) | 10 | 13 | 14 | 93% - corner |
   | Yas 3,486 m (s11) | 4 | 6 | 6 | 100% - corner |
   | Spa 24h 2,281 and 6,582 m (s65) | 5 | 6 | 6 | 100% - corner |
   | Daytona 5,215 m (s118, race) | 5 | 5 | 9 | 56% - penalty |
   | Red Bull Ring 1,386 m (s101, race) | 3 | 3 | 15 | 20% - penalty |
   | Daytona 5,200 m (s125) | 2 | 2 | 12 | 17% - penalty |
   | Monza 4,461 m (s10) | 2 | 2 | 14 | 14% - penalty |

   Nothing on file falls between 56% and 93%, which is where
   `BRAKED_SHARE` over `BRAKED_LAPS_NEEDED` laps sits. The verdict is
   **recomputed from the counts on every lap and never latched**, so a place
   whose share falls back below the bar becomes readable again without a
   separate un-retirement rule that would need its own threshold - CLAUDE.md
   rule 10 by construction rather than by a second guard.

   Refusing every `auto-segment` model instead - critic 6's suggestion -
   would refuse all nine models on file and delete the feature outright.

   Every decision is reported to the caller to be logged, the accepts too and
   not only the refusals. And a withdrawal names **the count that stands on
   the lap afterwards** rather than zeroing it: a lap can carry a penalty at
   one place and a missing corner at another, and session 65's laps 2, 3 and
   4 each do exactly that.
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
# Two brakes this far apart round the lap are the same stretch of road. The
# eighteen on file at Daytona's banking exit span 5,194-5,277 m - 83 m -
# because the brake is picked up wherever the car happens to be, so anything
# under about 90 m would split one place into two.
#
# **It is WIDER than the gap between some pairs of corners on file** - Road
# Atlanta's closest pair is 91.7 m apart, Red Bull Ring short's 99.2 m, and
# Spa's 109.4 m. That is a real cost and it is the acceptable direction: the
# only thing this constant groups is places to withdraw, so two adjacent
# corners the model is missing are withdrawn together, which is the right
# answer for both of them.
SAME_PLACE_M = 150.0
# Looked-at laps before a place may be judged the road at all, and the share
# of them that must carry a brake there. Both off the archive - see the
# module docstring's table. The separation is wide: the missing corners run
# 93-100% of laps braked and the penalties 14-56%, so 80% over four laps sits
# in the gap rather than on either population.
BRAKED_LAPS_NEEDED = 4
BRAKED_SHARE = 0.8
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
class Withdrawal:
    """A lap whose penalty count has been changed after the fact.

    **The count that stands NOW, not zero.** A lap can carry a penalty at one
    place and a brake at a missing corner at another, and session 65's laps
    2, 3 and 4 each do - a 2,281 m flag and a 6,582 m flag apiece. Zeroing
    the lap when one place is withdrawn writes "looked at and clean" over a
    reading that still stands, which is CLAUDE.md rule 3 and is what the
    schema note beside `penalties_served` forbids in as many words.
    """
    lap: int
    served: int
    lost_s: float | None


@dataclass(frozen=True)
class Verdict:
    """One lap's verdict from `RoadNotPenalty`: what to keep and what to say.

    `give_back` are `Withdrawal`s against laps a PREVIOUS call kept - write
    each back to its row, and hand the lap back to the race only where the
    count has fallen to zero. `notes` is every decision this lap in words,
    accepts included, for the log: CLAUDE.md rule 10, whose ratchet at Fuji
    was invisible for a whole race because only the refusals were written
    down.
    """
    kept: tuple
    give_back: tuple
    notes: tuple[str, ...]


def braked_at(frames, *, sample_hz: float = SAMPLE_HZ) -> list[float]:
    """Where on the lap the car braked hard, whatever the reason.

    Every run of `BRAKE_PCT` or more lasting `MIN_BRAKE_S` or more, by the
    metre it began at. **No speed bound, no lateral-g bound and no corner
    window** - this is the question "is this stretch of road braked for",
    which is what tells a corner the model is missing from a penalty served,
    and every one of those filters would answer a different question.
    """
    rows = [f for f in (frames or ())
            if f.get("lap_distance_m") is not None]
    dt = 1.0 / sample_hz
    out: list[float] = []
    i, n = 0, len(rows)
    while i < n:
        if (rows[i].get("brake_pct") or 0.0) < BRAKE_PCT:
            i += 1
            continue
        j = i
        while j < n and (rows[j].get("brake_pct") or 0.0) >= BRAKE_PCT:
            j += 1
        if (j - i) * dt >= MIN_BRAKE_S:
            out.append(float(rows[i]["lap_distance_m"]))
        i = j
    return out


def braked_columns(rows, field_names, *,
                   sample_hz: float = SAMPLE_HZ) -> list[float] | None:
    """`braked_at` from the recorder's column-array rows."""
    index = {name: position for position, name in enumerate(field_names)}
    wanted = ("lap_distance_m", "brake_pct")
    if any(name not in index for name in wanted):
        return None
    return braked_at([{name: row[index[name]] for name in wanted}
                      for row in rows], sample_hz=sample_hz)


class RoadNotPenalty:
    """Which flagged places are a corner the model is missing. One session.

    Item 4 of the module docstring, and its table. **A corner is braked on
    every lap and a penalty is not**, so the test is the share of the
    session's looked-at laps that carry a brake at the place - not the share
    that were flagged there, and not a run of consecutive laps, both of which
    were tried and are recorded there as the dead ends they are.

    A place is the road once `BRAKED_LAPS_NEEDED` laps have been looked at
    and `BRAKED_SHARE` of them braked there. The verdict is **recomputed from
    the counts on every lap**, so nothing latches: a place whose share falls
    back below the bar is readable again, and CLAUDE.md rule 10's "a rule
    that refuses a reading must be able to refuse its own baseline" is
    satisfied by construction rather than by a second guard.

    **What it costs, stated.** Flags at a missing corner before the fourth
    looked-at lap are kept and spoken, at LOW with "Unconfirmed." on the end,
    and then withdrawn. At Yas Marina's session 44 that is one call; where
    the place is flagged on the very first laps it can be two or three. There
    is no way to tell the shape from one lap - a real penalty arrives exactly
    once too - and refusing every first sighting refuses every real one.

    **`filter` must be called for EVERY lap the detector looked at**,
    including laps it found nothing on: those are what the share is counted
    against. `None` for `found` is a lap it could NOT look at, and is not
    counted at all.

    **CLAUDE.md rule 11.** One instance per session; the controller keys it
    on the session id beside `_corner_windows_cache` for the same reason.
    """

    def __init__(self, same_place_m: float = SAME_PLACE_M,
                 laps_needed: int = BRAKED_LAPS_NEEDED,
                 share: float = BRAKED_SHARE) -> None:
        self._same_place_m = float(same_place_m)
        self._laps_needed = int(laps_needed)
        self._share = float(share)
        self._laps_seen = 0
        # place -> how many looked-at laps carried a brake there
        self._braked: dict[float, int] = {}
        # lap -> the (place, Penalty) pairs this ledger has kept on it
        self._kept: dict[int, list[tuple[float, object]]] = {}
        # Places a flag has ever been raised at. Most places braked on every
        # lap are corners the model DOES contain - `APPROACH_M` covers them
        # and they never flag - and naming those as "missing" in the log is
        # noise that buries the one that matters.
        self._flagged: set[float] = set()

    def _place(self, at_m: float) -> float:
        """The book's own name for this stretch of road, adding it if new."""
        for place in self._braked:
            if abs(place - at_m) <= self._same_place_m:
                return place
        self._braked[at_m] = 0
        return at_m

    def _is_road(self, place: float) -> bool:
        if self._laps_seen < self._laps_needed:
            return False
        return self._braked.get(place, 0) >= self._share * self._laps_seen

    def retired(self) -> tuple[float, ...]:
        """The places a flag was raised at and this session calls corners.

        For the log and for `tools/find_penalties.py`: these are the corners
        the model is missing, and each one is worth adding to it.
        """
        return tuple(sorted(p for p in self._flagged if self._is_road(p)))

    def filter(self, lap_num: int, found, braked=()) -> Verdict:
        """One lap's verdict.

        `found` is the lap's `Penalty` list - `None` where the detector could
        not look at the lap. `braked` is `braked_at(frames)` for the same
        lap: every hard brake on it, flagged or not, which is what the share
        is counted from. Passing nothing for `braked` counts only the flags,
        which is the measure this class exists to replace - callers that can
        read the frames must pass it.
        """
        lap_num = int(lap_num)
        if found is None:
            return Verdict((), (), ())
        self._laps_seen += 1
        for at_m in dict.fromkeys(self._place(float(at)) for at in braked):
            self._braked[at_m] = self._braked.get(at_m, 0) + 1

        kept, notes = [], []
        for penalty in found:
            place = self._place(float(penalty.at_m))
            self._flagged.add(place)
            if self._is_road(place):
                notes.append(
                    f"lap {lap_num}: the brake at {penalty.at_m:.0f} m is at a "
                    f"place braked on {self._braked[place]} of "
                    f"{self._laps_seen} laps - that is a corner the model is "
                    f"missing, not a penalty")
                continue
            kept.append(penalty)
            self._kept.setdefault(lap_num, []).append((place, penalty))
            notes.append(
                f"lap {lap_num}: penalty at {penalty.at_m:.0f} m kept - braked "
                f"on {self._braked[place]} of {self._laps_seen} laps, "
                f"{self._share:.0%} of {self._laps_needed} would be a corner")

        # A place that has JUST become the road takes its earlier flags with
        # it, and each of those laps is recounted rather than zeroed.
        withdrawn = {}
        for lap, entries in list(self._kept.items()):
            if lap == lap_num:
                continue
            standing = [(place, p) for place, p in entries
                        if not self._is_road(place)]
            if len(standing) == len(entries):
                continue
            gone = [p for place, p in entries if self._is_road(place)]
            self._kept[lap] = standing
            lost = sum(p.lost_s for _, p in standing) if standing else None
            withdrawn[lap] = Withdrawal(lap=lap, served=len(standing),
                                        lost_s=lost)
            notes.append(
                f"lap {lap}: {len(gone)} reading(s) withdrawn at "
                f"{', '.join(f'{p.at_m:.0f} m' for p in gone)} - the place is "
                f"a corner. {len(standing)} penalt"
                f"{'y' if len(standing) == 1 else 'ies'} still stand(s) on "
                f"that lap")
        return Verdict(tuple(kept),
                       tuple(withdrawn[lap] for lap in sorted(withdrawn)),
                       tuple(notes))
