"""The app's own race clock, started at the green flag.

**GT7's race clock is not accurate.** The driver measured it and said so, and
the engineer used to lean on it: `remaining_time_ms` off the packet gated the
timed-race finish, stretched the lap count when the plan's estimated distance
ran out early, and was logged once a lap because nothing had certified what
the field does after expiry. All of that rested on a channel the driver does
not trust.

What replaces it is arithmetic on two measures the app owns:

* **The app timer** - a monotonic clock started when `session_state` raises
  RACE_STARTED, which is gated on real green-flag conditions. The duration is
  the event's own declared minutes (`events.race_laps` holds MINUTES when
  `race_type` is `time` - the documented column overload).
* **The sum of completed lap times** - GT7's own per-lap figures, which are
  exact. Independent of the first, and the two should reconcile.

The difference between them is not noise, it is a quantity with a meaning: it
absorbs the standing start (the time between the green and the first line
crossing) plus any paused time the frame watcher missed. Measured once at the
first crossing, it should then stay put. **A difference that grows lap on lap
means the app timer is running through something the laps are not** - a pause
nobody saw, or a timer started at the wrong moment - and the honest response
is to prefer the lap-time sum, which is built out of exact figures, and to say
that the estimate now rests on it.

Missing is None throughout. No duration means no remaining time and no
expiry - not a race that has just run out.

Threading: `note_frame` is called on the telemetry thread (60 Hz, arithmetic
on three floats and nothing else); everything else is read on the Qt thread.
The only shared mutable state is a handful of floats, each written by one
thread and read by the other, which CPython assignment makes atomic. Nothing
here takes a lock, because a lock on the packet path is a cost paid sixty
times a second for a race that pauses once.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from pitcrew.diagnostics import log

# How far the two measures may drift apart before the app timer stops being
# the reference. The offset itself - the standing start - is measured and
# subtracted, so this is the drift ON TOP of it. Three seconds is far more
# than the frame-quantisation between the two (one packet, 17 ms) and far less
# than any real pause or a dropped lap, so it separates the two populations
# with room on both sides.
RECONCILE_MARGIN_S = 3.0

# A lap whose app-clock span exceeds its own recorded time by this fraction,
# on a lap that was not a pit lap, is very likely a LAP_COMPLETED that never
# arrived: two laps of wall clock against one lap of recorded time. Worth one
# warning, because every distance estimate downstream counts laps.
DROPPED_LAP_FRACTION = 0.6


@dataclass(frozen=True)
class Reconciliation:
    """The two measures of elapsed race time, and what they say about each other."""
    app_s: float
    laps_s: float
    # App minus laps, minus the offset measured at the first crossing. Zero is
    # perfect agreement; positive means the app timer has run through
    # something the laps did not.
    drift_s: float
    # Whether the two still agree inside `RECONCILE_MARGIN_S`. None before a
    # second lap has landed, because one lap only establishes the offset and
    # cannot corroborate anything.
    corroborated: bool | None
    # Whether this lap's span looks like two laps of racing - a dropped
    # LAP_COMPLETED, which makes the lap count itself wrong.
    dropped_lap: bool = False


class RaceClock:
    """Elapsed and remaining race time, from the app's own timer and the laps.

    `duration_s` is None for a race run to a lap count: the clock still
    measures elapsed time (which the reconciliation and the export both want)
    but `remaining_s` and `expired` stay None and False. A lap race ends on
    its lap count and nothing here should pretend otherwise.
    """

    def __init__(self, duration_s: float | None = None, *,
                 now=time.monotonic) -> None:
        self.duration_s = duration_s
        self._now = now
        self._started_at: float | None = None
        # Paused time, accumulated by the frame watcher. GT7 can be paused
        # mid-race in a single-player lobby, and the recorder already gates on
        # the same two flags - a race clock that ran through a pause would
        # report a race shorter than it is and call the last lap early.
        self._paused_total_s = 0.0
        self._paused_since: float | None = None
        # The lap-time sum, and the offset between the two measures.
        self._laps_ms = 0
        self._laps_counted = 0
        self._offset_s: float | None = None
        self._drift_s = 0.0
        self._corroborated: bool | None = None
        self._app_at_last_lap: float | None = None
        self._discrepancy_logged = False
        self._dropped_logged = False
        # How many LAP_COMPLETED events look to have been missed. Surfaced on
        # the snapshot rather than only logged: every distance estimate
        # downstream counts laps, so a dropped one is a fact the pit wall has
        # to be able to show.
        self.laps_dropped = 0

    # ---------------------------------------------------------------- timing

    @property
    def running(self) -> bool:
        return self._started_at is not None

    def start(self) -> None:
        """The green flag. Idempotent - a second green does not restart it."""
        if self._started_at is None:
            self._started_at = self._now()

    def note_frame(self, now: float, *, paused: bool) -> None:
        """One packet, on the telemetry thread. Accrues paused time only.

        Called for every frame including the paused ones, which is the point:
        `SessionState.update` returns early on a pause and produces no events
        at all, so nothing else downstream can see that the race stopped.
        """
        if self._started_at is None:
            return
        if paused:
            if self._paused_since is None:
                self._paused_since = now
            return
        since = self._paused_since
        if since is not None:
            self._paused_total_s += max(0.0, now - since)
            self._paused_since = None

    @property
    def elapsed_app_s(self) -> float:
        """Wall time since the green, less anything spent paused."""
        if self._started_at is None:
            return 0.0
        now = self._now()
        # **Total first, then the pause in progress.** Both are written by the
        # frame watcher on the telemetry thread and read here on the Qt one.
        # Reading `_paused_since` first and the total second double-counts a
        # pause that ends between the two reads - the elapsed pause lands in
        # the total AND is added again from the stale `since`. This order can
        # only ever undercount by one pause for one frame, which self-corrects
        # on the next read; the other order overstates elapsed race time, and
        # elapsed race time is what ends the race.
        total = self._paused_total_s
        since = self._paused_since
        paused = total + (max(0.0, now - since) if since is not None else 0.0)
        return max(0.0, now - self._started_at - paused)

    @property
    def elapsed_laps_s(self) -> float:
        """Racing time as the laps themselves report it."""
        return self._laps_ms / 1000.0

    @property
    def corroborated(self) -> bool | None:
        """Whether the lap times still agree with the app timer.

        None until a second lap has landed: one lap measures the offset and
        corroborates nothing.
        """
        return self._corroborated

    @property
    def elapsed_s(self) -> float:
        """The measure the remaining-time arithmetic actually rests on.

        The app timer while the two agree. **Once they disagree past
        `RECONCILE_MARGIN_S` the lap-time sum wins**, because it is built out
        of GT7's own exact per-lap figures and the app timer is the one that
        can silently run through a pause. The measured offset - the standing
        start - is carried back on, because the lap sum starts at the first
        crossing and the race started before it.
        """
        if self._corroborated is False and self._offset_s is not None:
            return self.elapsed_laps_s + self._offset_s
        return self.elapsed_app_s

    @property
    def remaining_s(self) -> float | None:
        if self.duration_s is None or self._started_at is None:
            return None
        return self.duration_s - self.elapsed_s

    @property
    def expired(self) -> bool:
        remaining = self.remaining_s
        return remaining is not None and remaining <= 0.0

    # -------------------------------------------------------- reconciliation

    def note_lap(self, lap_time_ms: int, *, is_pit_lap: bool = False
                 ) -> Reconciliation | None:
        """One completed lap, with GT7's own figure for it.

        Returns the reconciliation, or None before the clock has started or
        for a lap with no usable time. The first lap only measures the offset:
        the standing start, the formation portion, whatever sits between the
        green and the first line crossing. Every lap after it is checked
        against that offset.
        """
        if self._started_at is None or lap_time_ms <= 0:
            return None
        app_before = self._app_at_last_lap
        app = self.elapsed_app_s
        self._laps_ms += int(lap_time_ms)
        self._laps_counted += 1
        self._app_at_last_lap = app

        if self._offset_s is None:
            # The first crossing. Everything between the green and here is
            # the offset, and it is a measurement, not an error.
            self._offset_s = max(0.0, app - self.elapsed_laps_s)
            # **Logged every race, because the zero point is not the flag.**
            # `RACE_STARTED` fires when the car is seen under 30 km/h and then
            # over 80, which is some seconds AFTER lights out, while the
            # duration counted down is the full declared minutes. So the
            # remaining time is systematically long by that delta, and the
            # finish, "two to go" and "last lap" all rest on it.
            #
            # The reconciliation cannot catch it: a constant start error looks
            # exactly like the standing start it is folded into. What can
            # catch it is this number set beside `laps.standing_start_ms` for
            # the same lap - GT7's own figure for the grid period - and the
            # difference between the two IS the detection lag. One line a
            # race is enough to measure it and correct the zero point next
            # session; until then the countdown runs long by an unmeasured
            # amount and no call may imply otherwise.
            log("race").info(
                "app clock: %.2f s from green to the first crossing. Compare "
                "against this lap's standing_start_ms - the difference is how "
                "late the launch detector fired, and the countdown is long by "
                "exactly that much.", self._offset_s)
            return Reconciliation(app, self.elapsed_laps_s, 0.0, None)

        if self.duration_s is None:
            # **A lap race is not reconciled.** The reconciliation exists to
            # protect one thing - how much racing time is left - and a race
            # run to a lap count has none: its finish is a number the game
            # reports and the app counts down. Running the check anyway would
            # produce a warning about a discrepancy that decides nothing.
            return Reconciliation(app, self.elapsed_laps_s, 0.0, None)

        self._drift_s = app - self.elapsed_laps_s - self._offset_s
        self._corroborated = abs(self._drift_s) <= RECONCILE_MARGIN_S
        if not self._corroborated and not self._discrepancy_logged:
            # **Once, not per lap.** A discrepancy that persists is one fact
            # about the race, and a line a lap would bury it.
            self._discrepancy_logged = True
            log("race").warning(
                "race clock disagreement: app timer %.1f s against %.1f s of "
                "lap times plus a %.1f s standing start (%.1f s apart). The "
                "lap-time sum is now the reference - it is built from GT7's "
                "own exact lap figures.",
                app, self.elapsed_laps_s, self._offset_s, self._drift_s)

        dropped = False
        if (app_before is not None and not is_pit_lap
                and app - app_before
                > lap_time_ms / 1000.0 * (1.0 + DROPPED_LAP_FRACTION)):
            dropped = True
            self.laps_dropped += 1
            if not self._dropped_logged:
                self._dropped_logged = True
                log("race").warning(
                    "a lap took %.1f s of clock against a recorded %.1f s - a "
                    "LAP_COMPLETED was probably missed, so the lap count and "
                    "every distance estimate built on it are one lap light.",
                    app - app_before, lap_time_ms / 1000.0)
        return Reconciliation(app, self.elapsed_laps_s, self._drift_s,
                              self._corroborated, dropped)

    # ------------------------------------------------------------- estimates

    def laps_left(self, lap_time_ms: int | None) -> int | None:
        """How many more laps fit in the time left. **An estimate, always.**

        GT7 drops the flag at the first line crossing after the clock expires,
        so any time at all remaining means one more lap: the answer is a
        ceiling, never a rounding. None where there is no clock or no lap time
        to divide by - missing is None, and a distance guessed from nothing
        would be read as a count.
        """
        remaining = self.remaining_s
        if remaining is None or not lap_time_ms or lap_time_ms <= 0:
            return None
        if remaining <= 0:
            return 0
        return max(1, math.ceil(remaining / (lap_time_ms / 1000.0)))

    def laps_left_margin_s(self, lap_time_ms: int | None) -> float | None:
        """How wrong the median may be, in seconds, before `laps_left` flips.

        The estimate is a ceiling over `remaining / lap`, so it changes when
        that ratio crosses an integer. This returns the distance to the nearer
        crossing, expressed as an error in the lap time itself, which is the
        quantity that can be compared against the driver's own measured
        lap-to-lap spread.

        **It exists because the comparison matters.** Simulated across a real
        30-minute race, the first four crossings had 0.12-0.66 s of margin
        against a measured spread of 2.04 s - the answer there is not
        uncertain, it is unresolvable, and quoting a lap count would be
        inventing precision. From the fifth crossing the margin is 0.9 s and
        climbing, and by two laps out it is over thirteen seconds.
        """
        remaining = self.remaining_s
        if remaining is None or not lap_time_ms or lap_time_ms <= 0:
            return None
        lap_s = lap_time_ms / 1000.0
        left = self.laps_left(lap_time_ms)
        if not left:
            return None
        # A slower lap than this and one fewer fits; a quicker one than that
        # and one more does. Either bound can be unreachable, which is what
        # the guards are for - at one lap to go there is no lower bound.
        slower = remaining / (left - 1) if left > 1 else None
        quicker = remaining / left
        margins = [value for value in
                   ((slower - lap_s) if slower is not None else None,
                    lap_s - quicker)
                   if value is not None and value >= 0]
        return min(margins) if margins else 0.0

    def as_snapshot(self) -> dict:
        """What the pit wall and the export can say about the clock."""
        remaining = self.remaining_s
        return {
            "clockRunning": self.running,
            "elapsedS": round(self.elapsed_s, 1) if self.running else None,
            "remainingS": round(remaining, 1) if remaining is not None else None,
            "elapsedAppS": round(self.elapsed_app_s, 1) if self.running else None,
            "elapsedLapsS": (round(self.elapsed_laps_s, 1)
                             if self._laps_counted else None),
            "lapsCounted": self._laps_counted,
            # None until a second lap can corroborate the first.
            "clockCorroborated": self._corroborated,
            "clockDriftS": (round(self._drift_s, 1)
                            if self._corroborated is not None else None),
            # Non-zero means the lap count - and every distance built on it -
            # is light by that many.
            "lapsDropped": self.laps_dropped,
            # How late the launch detector fired relative to the first
            # crossing. None before that crossing. It is not the flag drop,
            # and the countdown is long by the part of it that is detection
            # lag rather than standing start - see `note_lap`.
            "greenToFirstCrossingS": (round(self._offset_s, 1)
                                      if self._offset_s is not None else None),
        }
