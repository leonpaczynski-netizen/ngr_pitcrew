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

**It does not gate the crossing calls.** The once-per-lap call the coordinator
emits at the line already lands on the biggest straight there is - at Monza the
main straight *begins* at the start/finish line. This is for anything that
wants to speak in the middle of a lap.
"""
from __future__ import annotations

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
        self.held_s: float = 0.0

    def update(self, *, throttle_pct: float | None, speed_ms: float | None,
               yaw_rate: float | None, now: float) -> bool:
        """True once the car has been straight and flat for long enough.

        **Stays true for the rest of the straight**, so a caller that has
        something to say does not have to catch one particular frame.
        """
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
