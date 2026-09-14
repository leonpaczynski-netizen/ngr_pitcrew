"""Whether the car is somewhere the driver can listen.

*"Agree data should come on straights not corners."* - the driver, 22 Aug.

It is the most consistent piece of real radio discipline there is: engineers
wait for the straight, because a call in a braking zone is a distraction rather
than information.

### Why throttle alone does not work, measured

The obvious test is sustained full throttle. Run over a clean 109-second Monza
race lap - 6,544 frames - **it finds nineteen windows per lap.** The runs are
broken by upshifts rather than by corners, terminating at 180, 213, 238 and 261
km/h, and several of them sit under heavy lateral load:

    4074-4333 m   5.0 s   164->213 km/h   peak 2.78 g
    2858-3015 m   3.7 s   128->180 km/h   peak 1.91 g
    5190-5338 m   3.4 s   136->180 km/h   peak 1.75 g

Speaking at 2.78 g is worse than speaking in a braking zone.

**Adding a lateral gate fixes it.** The same lap, requiring the car to be
straight as well as accelerating, gives **five sensible windows**, the longest
being 10.2 s from the start/finish line down the main straight.

### What this deliberately is not

**No track model.** A distance-based zone table would need a per-circuit map
and would be wrong the first time he raced somewhere new. Throttle and lateral
load are in the packet at 60 Hz and work on day one at any circuit.

**It did not gate the crossing calls, and that assumption was Monza's.** At
Monza the main straight *begins* at the start/finish line; at Bathurst on 14
Sep 2026 the line is a few seconds from Hell Corner, and the heartbeat plus the
data line queued behind it reached the driver in the braking zone. So the voice
now asks `fits` before it starts any line volunteered mid-lap - a place, a
rival's stop, the data line (`Voice.listen_on`). Instructions go unasked, and
so does what the crossing says: it is arbitrated one call per crossing and
saying it at the line is the design.

### How long is this straight? - measured, and what is missing

**Nothing in the app knows.** `corner_models` holds corners for eleven
circuits and not Mount Panorama, and no table anywhere holds straights; the
telemetry thread has no live lap distance to look one up by. So `Window`
carries a `remaining_s` that is None today, and `fits` is written for both:

* **With a model** (`remaining_s` known), a clip starts when it and
  `FIT_MARGIN_S` fit in what is left.
* **Without one**, it cannot know, so it waits for evidence: the straight has
  to have been held `UNMODELLED_HOLD_S`, and a strict (colour) clip has to be
  no longer than `UNMODELLED_CLIP_S`. Measured over the 143 straight windows
  of the Bathurst race (session 176, 19 laps), a 2.8 s clip started at the
  2 s edge finished inside the straight 28% of the time; started at 4 s
  held, 63%, with about two such chances a lap. At 3.0 s that falls to 48%.
  Half of all windows there had 1.5 s or less left at the edge.

What would close the gap, per circuit: the straights as lap-distance windows
with their duration at race pace - `windows()` below, run over stored laps
with `lap_distance_m`, produces exactly that - and a live lap distance on the
telemetry thread to look the current one up by. Then `Straight.window` takes
the remaining time and the hold can drop back to the edge.
"""
from __future__ import annotations

from dataclasses import dataclass

# Full throttle, near enough. Below this he is still working.
THROTTLE_PCT = 90.0
# **The gate that does the real work.** Lateral load this low is a car going
# straight; at Monza the flat-out kinks and the Parabolica exit all clear
# 1.5 g and are excluded by it.
MAX_LATERAL_G = 0.3
# How long it has to have been true. Long enough that a momentary straightening
# mid-corner is not a straight, short enough that the shorter straights still
# qualify.
MIN_HELD_S = 2.0

# **Without a model of the circuit, how long the straight must already have
# lasted before a volunteered clip starts on it.** See the module docstring
# for the Bathurst measurement: 4 s held roughly doubles how often a short
# clip finishes inside the straight, against the 2 s edge.
UNMODELLED_HOLD_S = 4.0
# And the longest strict (colour) clip that may start there. Timed off the
# rendered pack, 14 Sep 2026: "N laps to the stop." is 1.9-2.6 s, a corner's
# wear ("RR 19 percent.") 2.1-3.1 s with a median of 2.66; "Worst tyre N
# percent." 2.5-3.4 s, the gap to his best up to 4.0 s, and the fuel figure
# 4.5-5.2 s. 2.8 s is where the Bathurst fit rate falls off (63% -> 48% at
# 3.0 s), and it keeps the countdown and most corner figures. The fuel figure
# is not read out mid-lap on a circuit with no model - the heartbeat at the
# crossing carries the fuel anyway.
UNMODELLED_CLIP_S = 2.8
# With a model: the clip must end this far before the straight does.
FIT_MARGIN_S = 0.5
# A detector not fed for longer than this is not on a straight - the stream
# stopped, or the game is paused - whatever it last said.
FRESH_S = 0.5


@dataclass(frozen=True)
class Window:
    """Where the car is, as far as speaking goes, at one moment."""
    held_s: float = 0.0
    # Seconds left on this straight, from a per-circuit model. None today:
    # no circuit has one (see the module docstring).
    remaining_s: float | None = None

    @property
    def open(self) -> bool:
        return self.held_s >= MIN_HELD_S


def fits(window: Window | None, clip_s: float | None, *,
         strict: bool = False) -> bool:
    """Whether a clip of `clip_s` may start now.

    Never on a closed window. With a model, the clip has to fit in what is
    left. Without one, the straight has to have proved itself for
    `UNMODELLED_HOLD_S`, and a strict clip has to be short.

    A clip of unknown length is refused when strict and otherwise judged by
    the hold alone.
    """
    if window is None or not window.open:
        return False
    if window.remaining_s is not None:
        if clip_s is None:
            return not strict
        return clip_s + FIT_MARGIN_S <= window.remaining_s
    if window.held_s < UNMODELLED_HOLD_S:
        return False
    if not strict:
        return True
    return clip_s is not None and clip_s <= UNMODELLED_CLIP_S


def lateral_g(speed_ms: float | None, yaw_rate: float | None) -> float | None:
    """Lateral acceleration from the two channels the packet does carry.

    GT7 broadcasts no accelerometer. `v * yaw` is the centripetal term and it
    is what `telemetry/recorder` already derives `lat_g` from, so the live
    figure and the stored one are the same quantity.
    """
    if speed_ms is None or yaw_rate is None:
        return None
    return abs(speed_ms * yaw_rate) / 9.81


class Straight:
    """Is the car straight and accelerating, and has it been for long enough?

    Fed one packet at a time on the telemetry thread. Holds two floats and
    answers in constant time; nothing here allocates or blocks.
    """

    def __init__(self, *, throttle_pct: float = THROTTLE_PCT,
                 max_lateral_g: float = MAX_LATERAL_G,
                 min_held_s: float = MIN_HELD_S) -> None:
        self._throttle = throttle_pct
        self._max_g = max_lateral_g
        self._min_held = min_held_s
        self._since: float | None = None
        self._fed_at: float | None = None
        self.held_s: float = 0.0

    def window(self, now: float, *,
               remaining_s: float | None = None) -> Window:
        """The straight as it stands at `now`, for `fits`.

        Read from another thread (the voice's) while the telemetry thread
        writes: two floats, each read once, and a torn pair costs at worst
        one poll's wrong answer. A detector not fed for `FRESH_S` is closed -
        a paused game must not hold a straight open.
        """
        since, fed = self._since, self._fed_at
        if since is None or fed is None or now - fed > FRESH_S:
            return Window()
        return Window(held_s=max(0.0, now - since), remaining_s=remaining_s)

    def update(self, *, throttle_pct: float | None, speed_ms: float | None,
               yaw_rate: float | None, now: float) -> bool:
        """True once the car has been straight and flat for long enough.

        **Stays true for the rest of the straight**, so a caller that has
        something to say does not have to catch one particular frame.
        """
        self._fed_at = now
        g = lateral_g(speed_ms, yaw_rate)
        ok = (throttle_pct is not None and throttle_pct >= self._throttle
              and g is not None and g <= self._max_g)
        if not ok:
            self._since = None
            self.held_s = 0.0
            return False
        if self._since is None:
            self._since = now
        self.held_s = now - self._since
        return self.held_s >= self._min_held

    def reset(self) -> None:
        """Forget the current run - on a pit entry, a pause, or a new session."""
        self._since = None
        self._fed_at = None
        self.held_s = 0.0


def windows(frames, *, sample_hz: float = 60.0,
            throttle_pct: float = THROTTLE_PCT,
            max_lateral_g: float = MAX_LATERAL_G,
            min_held_s: float = MIN_HELD_S) -> list[tuple[int, int, float]]:
    """Every straight in a recorded lap, as `(start, end, seconds)`.

    The offline twin of `Straight`, so the same rule can be checked against a
    stored lap before it is ever spoken over.
    """
    out: list[tuple[int, int, float]] = []
    start: int | None = None
    for index, frame in enumerate(frames):
        g = frame.get("lat_g")
        throttle = frame.get("throttle_pct")
        ok = (throttle is not None and throttle >= throttle_pct
              and g is not None and abs(g) <= max_lateral_g)
        if ok:
            if start is None:
                start = index
        elif start is not None:
            held = (index - start) / sample_hz
            if held >= min_held_s:
                out.append((start, index, held))
            start = None
    if start is not None:
        held = (len(frames) - start) / sample_hz
        if held >= min_held_s:
            out.append((start, len(frames), held))
    return out
