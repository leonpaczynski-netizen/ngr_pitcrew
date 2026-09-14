"""Contact and water, said out loud as they appear and as they go.

The driver, 15 Sep 2026: *"George needs to verbally alert me to damage
appearing and leaving car and water on track too."* Both are on the HUD panel
the wear gauge already grabs every ~2 s, and neither is in any packet GT7
sends: the car icon's bumper arcs (`telemetry/hud_damage.py`, row 5.20) and
the hygrometer (`telemetry/hygrometer.py`, row 5.13). This module turns the
per-grab reads into at most one onset and one clear per episode.

It never grabs and never reads pixels. It is fed the reads `HudSession`
already keeps, each with the monotonic time it was taken, and whether the car
was on the circuit - so a replay of a recording drives exactly the rules the
race does.

### What the grab rate is, because every window here is sized from it

**Median 2.21 s between readable grabs** (p10 2.10, p90 2.38, 1169 grabs)
over the Sardegna race of 14 Sep 2026 (session 176), read off the log's
`reading accepted/refused` lines - the driver's `hud_sample_interval_s` is 2 s
and a grab of the whole projector adds the rest. When the wear gauge refuses
or holds a reading the sampler grabs again after 0.5 s, so a count of reads
alone is not a time: **every rule below states a span in seconds as well as a
count**, and the count is the one the 2 s grab reaches.

### Contact

What the icon is, measured (memory `reference_gt7_damage_icon_behaviour`):
only the bumper arc of the end that was hit turns red, front or rear, never
left or right; it pulses about twice a second; it clears on its own 90-135 s
later with no stop. **So it is recent contact, never the car's condition** -
nothing here says "damage", and the clear says the WARNING went, not that the
car is whole (rule 5).

* **Onset** - `CONTACT_MIN_LIT` lit reads of one arc inside
  `CONTACT_WINDOW_S`: `HudSession.contact_recent`'s True, from the same
  constants, so the board and the voice cannot disagree about when contact
  began (rule 13). *"Contact, front."* / *"Contact, rear."* only when the
  other arc read 0 px on every read of that window; otherwise *"Contact."*
* **Clear** - `CLEAR_S` of readable grabs with **0 px on both arcs**, at least
  `CLEAR_MIN_READS` of them, none further apart than `RUN_MAX_GAP_S`. Sized
  from the pulse, measured three ways:

  - **at 60 fps on the recording** (session 166, both episodes): a 0.5 s
    cycle, the arc at 8 px or more for 70-71% of it and at 0 px for 21-25%;
  - **replayed at the live grab series** (the 1166 real intervals of session
    176, 400 random starting phases per episode): the longest all-zero run
    inside an episode was **5 grabs, 14.5 s**;
  - **live** (session 176, seven episodes): the longest run of below-threshold
    grabs inside an episode was **3 grabs, 5.9 s**, and the shortest quiet
    stretch between two episodes **34 grabs, 74 s**.

  30 s is twice the worst replayed run and under half the shortest gap. **A
  grab locked to the pulse is the case it guards**: at a fixed 2.00 s or
  2.50 s - whole multiples of the cycle - the recording gives all-zero runs of
  32-58 s, and the live intervals never hold that still (p10 2.10 s, p90
  2.38 s).
* **Again** - while an episode is lit, the OTHER arc reaching the onset rule
  is a second hit at the other end: *"Contact again, rear."* Only after a
  first onset that named its end; a second hit on the same end cannot be told
  from the pulse, so it is not said.
* **Pit lane** - a read taken in the pit or off the circuit counts for
  nothing: the lane's paint shows through the see-through panel and no damage
  frame has ever been seen there. It breaks a clear run and never lights one.
* **Blind** - nothing is said and nothing is cleared on the absence of reads.
  An episode with no lit read for `EPISODE_RETIRE_S` is retired **silently**
  (rule 10: a lit latch that nothing retires would swallow the next hit) -
  by then the icon has cleared on its own by the game's measured behaviour.
  No "Lost the contact icon.": the icon is read off the bars the wear gauge
  found, so an icon blind for want of a panel is a gauge blind, and the gauge
  already says that once in its own words.

### Water

**Water under OUR car, now** - a fill bar that follows the surface within
tenths of a second: 0 dry, 57-81 of 86 px wet, empty for seconds in a tunnel.
Calibrated on the driver's wet video (`2026-09-14 11-46-35.mp4`) and the dry
Suzuka race (session 166).

* **Onset** - `WATER_ON_MIN_WET` wet reads spanning `WATER_ON_SPAN_S` inside
  `WATER_ON_WINDOW_S`, at least `WATER_ON_SHARE` of the readable reads there.
  The window and share are the board's WET light's (`HudSession.wet_now`), so
  George says "Water on track." only when the light reads wet.
* **Dry again** - wet share at most `WATER_DRY_SHARE` (the hygrometer's own
  dry-lap share) over `WATER_DRY_WINDOW_S`, on `WATER_DRY_MIN_READS` reads
  spanning `WATER_DRY_SPAN_S`. The wet video's tunnel read empty for 4.4 s; a
  dry line on a wet track can hold for seconds. 90 s is most of a lap on every
  circuit on file, so one tunnel or one dry line cannot flap it.
* **No "water in places".** One wet video, wet end to end but for a tunnel,
  cannot calibrate a patchy track; the board's "mixed" stays a light.
* **The words.** "Water on track." is the driver's own phrase and true of what
  the bar measures - water on the track where he is - without claiming the
  whole circuit or rain. "Track looks dry again." says "looks": a judgement
  from most of a lap under his car, not a measurement of the circuit.

**Rain does not retire the plan here.** The desk's playbooks carry `rain ->
report_only`, and `handover.CANNOT_SEE` keeps that rule unarmed, so the
coordinator re-costs nothing on water. "Water on track." IS the report; a
sentence saying the dry plan is off would contradict a coordinator still
calling stops against it.

### Said means heard

Every alert is IN FLIGHT from hand-over until the voice answers
(`delivered`), exactly as the race news is: heard, it is booked; not heard,
it is offered again while it is still true; no answer in `ACK_TIMEOUT_S`, it
is released (rule 10). A clear whose onset was never heard is dropped with
it - "cleared" about a contact he was never told of is noise.

Rule 11: `new_session` forgets everything, and the controller calls it where
the HUD session is reset, at every practice start and race arm.
"""
from __future__ import annotations

import itertools
from collections import deque
from dataclasses import dataclass

from pitcrew.diagnostics import log
from pitcrew.race.calls import (CONTACT, CONTACT_CLEAR, HIGH, WATER,
                                WATER_DRY, Call)
from pitcrew.telemetry.hud_session import (DAMAGE_MIN_LIT, DAMAGE_WINDOW_S,
                                           HYGRO_MIN_READS, HYGRO_WINDOW_S)
from pitcrew.telemetry.hygrometer import LAP_DRY_SHARE, WET_LEVEL

# ------------------------------------------------------------------ words
#
# Declared here and imported by `phrase_manifest`, never retyped there.
CONTACT_ONSET = {None: "Contact.", "front": "Contact, front.",
                 "rear": "Contact, rear."}
CONTACT_AGAIN = {"front": "Contact again, front.",
                 "rear": "Contact again, rear."}
# **"warning", not the car.** The icon is a warning that clears itself; the car
# is not repaired and may still be damaged. No "all clear", no "damage".
CONTACT_CLEARED = "Contact warning's cleared."
WATER_ON = "Water on track."
WATER_OFF = "Track looks dry again."


def fixed_lines() -> tuple[str, ...]:
    """Every sentence this module can say, for the phrase pack."""
    return (*CONTACT_ONSET.values(), *CONTACT_AGAIN.values(),
            CONTACT_CLEARED, WATER_ON, WATER_OFF)


# ---------------------------------------------------------------- contact

# Onset: `contact_recent`'s True, from its own constants (rule 13).
CONTACT_WINDOW_S = DAMAGE_WINDOW_S
CONTACT_MIN_LIT = DAMAGE_MIN_LIT
# Clear: 30 s of 0 px on both arcs. See the module docstring for the pulse:
# the longest all-zero run inside an episode was 3 grabs / 5.9 s live and
# 5 grabs / 14.5 s replayed at the live grab series; the shortest quiet
# stretch between two episodes live was 74 s.
CLEAR_S = 30.0
# Ten reads, so the span is read at the driver's 2 s grab rather than
# stitched across gaps from a handful of frames.
CLEAR_MIN_READS = 10
# A clean run with no readable grab for this long starts again: a pit stop or
# a blind stretch is not 20 s of watching the icon. Live, only 2 of 1169
# gaps between readable grabs in session 176 reached 5 s.
RUN_MAX_GAP_S = 10.0
# The icon clears on its own 90-135 s after contact. With no lit read for
# this long the episode cannot still be lit, so it is retired - silently.
EPISODE_RETIRE_S = 135.0

# ----------------------------------------------------------------- water

WATER_ON_WINDOW_S = HYGRO_WINDOW_S
WATER_ON_SHARE = 2 / 3
WATER_ON_MIN_WET = max(3, HYGRO_MIN_READS)
# Three wet grabs at the 2 s grab span 4.4 s; at the 0.5 s re-grab three
# frames are one second, so the span is stated too.
WATER_ON_SPAN_S = 4.0
WATER_DRY_WINDOW_S = 90.0
WATER_DRY_SHARE = LAP_DRY_SHARE
# 90 s at the measured 2.21 s is ~40 grabs; 30 is three quarters of them.
WATER_DRY_MIN_READS = 30
WATER_DRY_SPAN_S = 75.0
# No readable read for this long retires "wet" silently (rule 10), so a
# later onset is said again rather than swallowed by a state nobody can see.
WATER_RETIRE_S = 180.0

# A hand-over the voice never answers is released after this - the voice's
# own staleness limits are 8-15 s, so an answer later than this is not coming.
ACK_TIMEOUT_S = 45.0

FRONT, REAR = "front", "rear"


@dataclass(frozen=True)
class _Owed:
    """One thing to say, and the episode it is about."""
    kind: str
    text: str
    why: str
    episode: int
    # For a clear: the onset that has to have been heard first.
    after: "_Owed | None" = None


class ContactWatch:
    """The car icon's bumper arcs, read into onsets, re-onsets and clears."""

    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self.reset()

    def reset(self) -> None:
        # (at, front px, rear px, front lit, rear lit): readable, on track.
        self._reads: deque = deque()
        self.episode: int | None = None
        self._arcs: set[str] = set()
        self._named: str | None = None
        self._last_lit_at: float | None = None
        self._run_start: float | None = None
        self._run_last: float | None = None
        self._run_n = 0
        self._pit_logged = False
        self._owed: list[_Owed] = []
        self._onset: _Owed | None = None

    # -------------------------------------------------------------- reading

    def feed(self, at: float, front_px, rear_px, front_lit, rear_lit, *,
             on_track: bool) -> None:
        if front_px is None or rear_px is None:
            return                          # unreadable: evidence of nothing
        if not on_track:
            if (front_px or rear_px) and not self._pit_logged:
                self._pit_logged = True
                log("race").info(
                    "contact: red on the icon off the circuit or in the pit "
                    "(%s/%s px) - not counted; the lane shows through the "
                    "panel", front_px, rear_px)
            self._break_run()
            return
        self._pit_logged = False
        self._reads.append((at, int(front_px), int(rear_px), bool(front_lit),
                            bool(rear_lit)))
        horizon = at - max(CONTACT_WINDOW_S, CLEAR_S) - RUN_MAX_GAP_S
        while self._reads and self._reads[0][0] < horizon:
            self._reads.popleft()
        if front_px == 0 and rear_px == 0:
            if self._run_last is None or at - self._run_last > RUN_MAX_GAP_S:
                self._run_start, self._run_n = at, 0
            self._run_last = at
            self._run_n += 1
        else:
            self._break_run()
        if front_lit or rear_lit:
            self._last_lit_at = at if self.episode is not None \
                else self._last_lit_at
        self._judge(at)

    def _break_run(self) -> None:
        self._run_start = self._run_last = None
        self._run_n = 0

    def _window(self, at: float) -> list:
        return [r for r in self._reads if at - r[0] < CONTACT_WINDOW_S]

    def _lit_arcs(self, window) -> set[str]:
        arcs = set()
        if sum(1 for r in window if r[3]) >= CONTACT_MIN_LIT:
            arcs.add(FRONT)
        if sum(1 for r in window if r[4]) >= CONTACT_MIN_LIT:
            arcs.add(REAR)
        return arcs

    def _judge(self, at: float) -> None:
        window = self._window(at)
        lit = self._lit_arcs(window)
        if self.episode is None:
            if lit:
                self._begin(at, window, lit)
            return
        fresh = lit - self._arcs
        if fresh:
            self._arcs |= fresh
            if self._named is not None and len(fresh) == 1:
                arc = next(iter(fresh))
                owed = _Owed(CONTACT, CONTACT_AGAIN[arc],
                             f"HUD car icon: the {arc} arc lit on "
                             f"{self._count(window, arc)} of {len(window)} "
                             f"readable grabs in {CONTACT_WINDOW_S:g} s while "
                             f"the {self._named} arc's episode was still lit - "
                             f"a second hit at the other end [recent contact, "
                             f"not the car's condition]", self.episode)
                self._owed.append(owed)
                log("race").info("contact: again, %s - %s", arc, owed.why)
            else:
                log("race").info(
                    "contact: the %s arc lit inside an episode that named no "
                    "single end - not said again", "/".join(sorted(fresh)))
        if (self._run_n >= CLEAR_MIN_READS and self._run_start is not None
                and at - self._run_start >= CLEAR_S):
            why = (f"HUD car icon: 0 red px on both arcs on {self._run_n} "
                   f"readable grabs over {at - self._run_start:.1f} s "
                   f"[the warning cleared itself; not a repair, not the car's "
                   f"condition]")
            self._owed.append(_Owed(CONTACT_CLEAR, CONTACT_CLEARED, why,
                                    self.episode, after=self._onset))
            log("race").info("contact: cleared (episode %s) - %s",
                             self.episode, why)
            self._end(at)

    @staticmethod
    def _count(window, arc: str) -> int:
        index = 3 if arc == FRONT else 4
        return sum(1 for r in window if r[index])

    def _begin(self, at: float, window, lit: set[str]) -> None:
        self.episode = next(self._ids)
        self._arcs = set(lit)
        self._last_lit_at = at
        named = None
        if len(lit) == 1:
            arc = next(iter(lit))
            other = 2 if arc == FRONT else 1
            if all(r[other] == 0 for r in window):
                named = arc
        self._named = named
        other_note = ("the other arc 0 px on every one" if named else
                      "both arcs lit" if len(lit) == 2 else
                      "red on the other arc too, so no end is named")
        why = (f"HUD car icon: {'/'.join(sorted(lit))} arc lit on "
               f"{max(self._count(window, a) for a in lit)} of {len(window)} "
               f"readable grabs in {CONTACT_WINDOW_S:g} s, {other_note} "
               f"[recent contact, not the car's condition; the icon clears "
               f"itself in 90-135 s]")
        self._onset = _Owed(CONTACT, CONTACT_ONSET[named], why, self.episode)
        self._owed.append(self._onset)
        log("race").info("contact: onset (episode %s) %r - %s", self.episode,
                         CONTACT_ONSET[named], why)

    def _end(self, at: float) -> None:
        self.episode = None
        self._arcs = set()
        self._named = None
        self._last_lit_at = None
        self._onset = None
        # The clean run is the evidence; nothing older may light the next one.
        start = self._run_start if self._run_start is not None else at
        while self._reads and self._reads[0][0] < start:
            self._reads.popleft()

    def tick(self, now: float) -> None:
        """Retire an episode nothing has lit for `EPISODE_RETIRE_S`."""
        if (self.episode is not None and self._last_lit_at is not None
                and now - self._last_lit_at > EPISODE_RETIRE_S):
            log("race").info(
                "contact: episode %s retired unsaid - no lit read for %.0f s "
                "and no clean run seen, so its clearing fell where the icon "
                "could not be read; nothing is said as cleared",
                self.episode, now - self._last_lit_at)
            self._owed = [o for o in self._owed if o.episode != self.episode]
            self._end(now)
            self._reads.clear()

    def still_true(self, owed: _Owed) -> bool:
        if owed.kind == CONTACT:
            return owed.episode == self.episode
        # A clear stands until a newer episode begins.
        return self.episode is None or self.episode <= owed.episode

    def take_owed(self) -> list[_Owed]:
        owed, self._owed = self._owed, []
        return owed


class WaterWatch:
    """The hygrometer, read into "Water on track." and "Track looks dry again." """

    def __init__(self) -> None:
        self._ids = itertools.count(1)
        self.reset()

    def reset(self) -> None:
        self._reads: deque = deque()          # (at, level): readable, on track
        self.episode: int | None = None       # a wet episode said, or None
        self._last_read_at: float | None = None
        self._owed: list[_Owed] = []
        self._onset: _Owed | None = None

    def feed(self, at: float, level, *, on_track: bool) -> None:
        if level is None or not on_track:
            return
        self._last_read_at = at
        self._reads.append((at, float(level)))
        while self._reads and at - self._reads[0][0] > WATER_DRY_WINDOW_S:
            self._reads.popleft()
        if self.episode is None:
            recent = [r for r in self._reads if at - r[0] <= WATER_ON_WINDOW_S]
            wet = [r for r in recent if r[1] >= WET_LEVEL]
            if (len(recent) >= HYGRO_MIN_READS and len(wet) >= WATER_ON_MIN_WET
                    and wet[-1][0] - wet[0][0] >= WATER_ON_SPAN_S
                    and len(wet) / len(recent) >= WATER_ON_SHARE):
                self.episode = next(self._ids)
                why = (f"hygrometer: water under the car on {len(wet)} of "
                       f"{len(recent)} readable grabs in "
                       f"{WATER_ON_WINDOW_S:g} s (fill >= {WET_LEVEL:.0%}) "
                       f"[where he is driving, not the whole circuit; no "
                       f"rain channel exists]")
                self._onset = _Owed(WATER, WATER_ON, why, self.episode)
                self._owed.append(self._onset)
                log("race").info("water: onset (episode %s) - %s",
                                 self.episode, why)
            return
        reads = list(self._reads)
        wet = sum(1 for r in reads if r[1] >= WET_LEVEL)
        span = reads[-1][0] - reads[0][0]
        if (len(reads) >= WATER_DRY_MIN_READS and span >= WATER_DRY_SPAN_S
                and wet / len(reads) <= WATER_DRY_SHARE):
            why = (f"hygrometer: water under the car on {wet} of {len(reads)} "
                   f"readable grabs over {span:.0f} s "
                   f"(dry at <= {WATER_DRY_SHARE:.0%}) [his line, most of a "
                   f"lap - not the circuit measured]")
            self._owed.append(_Owed(WATER_DRY, WATER_OFF, why, self.episode,
                                    after=self._onset))
            log("race").info("water: dry again (episode %s) - %s",
                             self.episode, why)
            self.episode = None
            self._onset = None

    def tick(self, now: float) -> None:
        if (self.episode is not None and self._last_read_at is not None
                and now - self._last_read_at > WATER_RETIRE_S):
            log("race").info(
                "water: wet episode %s retired unsaid - no readable "
                "hygrometer read for %.0f s; nothing is said as dry",
                self.episode, now - self._last_read_at)
            self._owed = [o for o in self._owed if o.episode != self.episode]
            self.episode = None
            self._onset = None
            self._reads.clear()

    def still_true(self, owed: _Owed) -> bool:
        if owed.kind == WATER:
            return owed.episode == self.episode
        return self.episode is None or self.episode <= owed.episode

    def take_owed(self) -> list[_Owed]:
        owed, self._owed = self._owed, []
        return owed


class HudAlerts:
    """Both watches, and what has been handed to the voice and heard.

    Qt thread only: `feed_*`, `poll` and `delivered` are all called there
    (the controller hops the voice's answer back through a signal).
    """

    # Set by the controller, which routes the voice's answer back. A replay
    # or a test has nobody to answer, and books at hand-over.
    acknowledged_delivery = False

    def __init__(self) -> None:
        self.contact = ContactWatch()
        self.water = WaterWatch()
        self.new_session()

    def new_session(self) -> None:
        """Rule 11: nothing about the last session's icon or water."""
        self.contact.reset()
        self.water.reset()
        self._owed: list[_Owed] = []
        self._in_flight: dict[int, tuple[Call, _Owed, float]] = {}
        self._heard: set[_Owed] = set()
        self._fed_damage_at: float | None = None
        self._fed_hygro_at: float | None = None

    # -------------------------------------------------------------- feeding

    def feed_damage(self, at: float, front_px, rear_px, front_lit, rear_lit,
                    *, on_track: bool) -> None:
        self.contact.feed(at, front_px, rear_px, front_lit, rear_lit,
                          on_track=on_track)

    def feed_hygro(self, at: float, level, *, on_track: bool) -> None:
        self.water.feed(at, level, on_track=on_track)

    def feed_history(self, damage, hygro, *, on_track: bool) -> None:
        """New entries from `HudSession`'s histories, oldest first.

        `damage` rows are `(at, front px, rear px, front lit, rear lit)` and
        `hygro` rows `(at, level)`, exactly as the session keeps them.
        """
        for row in damage:
            if self._fed_damage_at is not None and row[0] <= self._fed_damage_at:
                continue
            self._fed_damage_at = row[0]
            self.feed_damage(*row, on_track=on_track)
        for at, level in hygro:
            if self._fed_hygro_at is not None and at <= self._fed_hygro_at:
                continue
            self._fed_hygro_at = at
            self.feed_hygro(at, level, on_track=on_track)

    # ------------------------------------------------------------- speaking

    def _watch(self, owed: _Owed):
        return self.contact if owed.kind in (CONTACT, CONTACT_CLEAR) \
            else self.water

    def poll(self, now: float, *, lap: int, on_track: bool) -> list[Call]:
        """What to hand the voice now. Nothing off the circuit or in the pit."""
        self.contact.tick(now)
        self.water.tick(now)
        self._owed.extend(self.contact.take_owed())
        self._owed.extend(self.water.take_owed())
        for key, (call, owed, at) in list(self._in_flight.items()):
            if now - at > ACK_TIMEOUT_S:
                self._in_flight.pop(key, None)
                log("race").warning("hud alert: no word from the voice %.0f s "
                                    "after %r - offered again", ACK_TIMEOUT_S,
                                    call.call)
                self._owed.append(owed)
        out: list[Call] = []
        keep: list[_Owed] = []
        flying = {owed for _, owed, _ in self._in_flight.values()}
        for owed in self._owed:
            watch = self._watch(owed)
            if not watch.still_true(owed):
                log("race").info("hud alert: %r no longer true - not said",
                                 owed.text)
                continue
            if owed.after is not None and owed.after not in self._heard:
                if owed.after in flying or owed.after in self._owed:
                    keep.append(owed)          # the onset first
                else:
                    log("race").info("hud alert: %r dropped - the onset it "
                                     "clears was never heard", owed.text)
                continue
            if not on_track:
                keep.append(owed)
                continue
            call = Call(kind=owed.kind, lap=int(lap), call=owed.text,
                        reason="", confidence=HIGH, why_spoken=owed.why,
                        tag=f"{owed.kind}-{owed.episode}")
            out.append(call)
            if self.acknowledged_delivery:
                self._in_flight[id(call)] = (call, owed, now)
                flying.add(owed)
            else:
                self._heard.add(owed)
        self._owed = keep
        return out

    def delivered(self, call: Call, played: bool) -> None:
        entry = self._in_flight.pop(id(call), None)
        if entry is None or entry[0] is not call:
            return
        _, owed, _ = entry
        if played:
            self._heard.add(owed)
            log("race").info("hud alert heard: %r", call.call)
        else:
            log("race").info("hud alert not heard, offered again: %r",
                             call.call)
            self._owed.append(owed)

    def awaits_delivery(self, call: Call) -> bool:
        entry = self._in_flight.get(id(call))
        return entry is not None and entry[0] is call
