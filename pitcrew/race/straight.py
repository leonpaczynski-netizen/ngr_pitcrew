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

### How long is this straight? - measured, and what closes the gap

`Window` carries a `remaining_s`, and `fits` is written for both cases:

* **With a model** (`remaining_s` known), a clip starts when it and
  `FIT_MARGIN_S` fit in what is left.
* **Without one**, it cannot know, so it waits for evidence: the straight has
  to have been held `UNMODELLED_HOLD_S`, and a strict (colour) clip has to be
  no longer than `UNMODELLED_CLIP_S`. Measured over the 143 straight windows
  of the Bathurst race (session 176, 19 laps), a 2.8 s clip started at the
  2 s edge finished inside the straight 28% of the time; started at 4 s
  held, 63%, with about two such chances a lap. At 3.0 s that falls to 48%.
  Half of all windows there had 1.5 s or less left at the edge.

**The model** (14 Sep 2026) is `StraightsModel`: the circuit's straights as
lap-distance windows, derived from his own clean laps by
`tools/derive_straights.py` (`analysis/straights.py` says how) and stored per
circuit in `straight_models`. `Straight.use_model` hands the detector the
model and the live lap ruler; `Straight.window` then fills `remaining_s`
itself, so both callers of `fits` - the voice's gate and the straight's data
line - read it with no change of their own.

`remaining_s` is the LOWER of two estimates, because each errs long in its
own way: the model's median time from here to the end of the window (his
pace on most laps, not tonight's - traffic, a lift), and the distance left at
the current speed (which ignores that the car is still accelerating, so it is
long on every straight). It is **None, and the held-4 s fallback applies
unchanged,** wherever the lap distance cannot be trusted: no model, no ruler,
a ruler that has lost packets this lap, or a last closed lap that did not
come out the length of the model's axis - the first lap, a lap after a
reset, the out-lap and the lap after it. Unknown is never 0 m.

It is **0.0 where the distance is trusted and the model says the car is not
on one of its straights** - a measured "no room here", not a missing reading.
"""
from __future__ import annotations

from dataclasses import dataclass, field

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
#
# **What it absorbs.** The voice starting a line after the gate said yes (one
# poll of its queue plus the audio device, about a tenth); where the car
# really is against where the integrated distance puts it after the per-lap
# scale (the Mount Panorama window ends spread 5-18 m lap to lap - 0.1-0.3 s
# at 200 km/h); and a lift a little earlier than usual. The window's end is
# already the lower quartile of where the straight ended, so this is not the
# only conservatism. Replayed over the Bathurst race (`tools/derive_straights.py
# --replay 176`, model out of sample): the 2.8 s clip starts on the same 71
# straights and finishes inside 92% of them at any margin from 0 to 0.75 s;
# the 2.0 s clip starts 95 times at 0 s, 80 at 0.5 s and 72 at 0.75 s with
# the finish rate flat at 93-95% - the extra starts at a smaller margin are
# on the short straights, where a tenth of error is the whole margin.
FIT_MARGIN_S = 0.5
# A detector not fed for longer than this is not on a straight - the stream
# stopped, or the game is paused - whatever it last said.
FRESH_S = 0.5
# How far the live ruler's last closed lap may sit from the model's axis and
# still put the car on it. The same 2% `analysis/straights.py` pools laps by.
MODEL_LAP_TOLERANCE = 0.02
# Below this a distance-over-speed estimate means nothing.
MIN_SPEED_MS = 5.0


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
            # Unknown length: never strict, and never where the model says
            # there is no straight left.
            return not strict and window.remaining_s > FIT_MARGIN_S
        return clip_s + FIT_MARGIN_S <= window.remaining_s
    if window.held_s < UNMODELLED_HOLD_S:
        return False
    if not strict:
        return True
    return clip_s is not None and clip_s <= UNMODELLED_CLIP_S


@dataclass(frozen=True)
class ModelStraight:
    """One straight of a circuit model, on the model's lap-distance axis.

    `end_m` may exceed the lap length: a straight that crosses the line.
    `t_left_s` is the median time, over the laps it was derived from, from
    evenly spaced points between `start_m` and `end_m` to `end_m`.
    """
    id: str
    start_m: float
    end_m: float
    laps: int
    median_s: float | None = None
    t_left_s: tuple[float, ...] = ()
    brake_m: float | None = None

    @property
    def limit_m(self) -> float:
        """Where anything started on it has to be finished: its end, or the
        next braking entry if that comes first."""
        if self.brake_m is None:
            return self.end_m
        return min(self.end_m, self.brake_m)

    def time_to_end(self, at_m: float) -> float | None:
        """Median seconds from `at_m` to `end_m`, off the profile."""
        points = self.t_left_s
        span = self.end_m - self.start_m
        if len(points) < 2 or span <= 0:
            return None
        x = (min(max(at_m, self.start_m), self.end_m) - self.start_m) / span
        position = x * (len(points) - 1)
        low = min(int(position), len(points) - 2)
        return points[low] + (points[low + 1] - points[low]) * (position - low)


@dataclass(frozen=True)
class StraightsModel:
    """A circuit's straights, `[DERIVED]` from stored laps.

    See the module docstring for what `remaining_s` returns and when.
    """
    circuit_key: str
    lap_length_m: float
    straights: tuple[ModelStraight, ...]
    laps: int = 0
    session_ids: tuple[int, ...] = ()
    source: str = "derived-laps"
    raw: dict = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_dict(cls, payload: dict) -> "StraightsModel":
        return cls(
            circuit_key=str(payload["circuit_key"]),
            lap_length_m=float(payload["lap_length_m"]),
            straights=tuple(
                ModelStraight(
                    id=str(w["id"]), start_m=float(w["start_m"]),
                    end_m=float(w["end_m"]), laps=int(w["laps"]),
                    median_s=w.get("median_s"),
                    t_left_s=tuple(float(v) for v in w.get("t_left_s") or ()),
                    brake_m=(None if w.get("brake_m") is None
                             else float(w["brake_m"])))
                for w in payload.get("windows") or ()),
            laps=int(payload.get("laps") or 0),
            session_ids=tuple(int(i) for i in payload.get("session_ids") or ()),
            source=str(payload.get("source") or "derived-laps"),
            raw=payload)

    def locate(self, position_m: float) -> tuple[ModelStraight, float] | None:
        """The straight at `position_m` on the model axis and the position
        unwrapped onto it, or None where the model has no straight."""
        for straight in self.straights:
            for shift in (0.0, self.lap_length_m):
                at = position_m + shift
                if straight.start_m <= at < straight.limit_m:
                    return straight, at
        return None

    def remaining_s(self, distance_m: float | None, *,
                    last_lap_m: float | None,
                    speed_ms: float | None) -> float | None:
        """Seconds of straight left, or None where the distance is not trusted.

        `distance_m` is the live ruler's metres round this lap and
        `last_lap_m` what its last closed lap integrated to - the per-lap
        scale that puts tonight's integration on the model's axis, the same
        correction the derivation made to every lap it pooled.
        """
        if distance_m is None or last_lap_m is None:
            return None
        axis = self.lap_length_m
        if (axis <= 0 or last_lap_m <= 0
                or abs(last_lap_m - axis) > MODEL_LAP_TOLERANCE * axis):
            return None
        position = distance_m * axis / last_lap_m
        if position < 0 or position > axis * (1 + MODEL_LAP_TOLERANCE):
            return None
        found = self.locate(position)
        if found is None:
            return 0.0
        straight, at = found
        estimates = []
        to_here = straight.time_to_end(at)
        to_limit = straight.time_to_end(straight.limit_m)
        if to_here is not None and to_limit is not None:
            estimates.append(to_here - to_limit)
        if speed_ms is not None and speed_ms >= MIN_SPEED_MS:
            estimates.append((straight.limit_m - at) / speed_ms)
        if not estimates:
            return None
        # Both terms are non-negative by construction (`at` is before
        # `limit_m`, and the profile falls towards the end), so this is the
        # smaller of two times, not a clamp.
        return min(estimates)


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
        self._speed_ms: float | None = None
        self._model: StraightsModel | None = None
        self._ruler = None
        self.held_s: float = 0.0

    def use_model(self, model: StraightsModel | None, ruler=None) -> None:
        """The circuit's straights, and where to ask how far round the lap.

        `ruler` is a zero-argument callable returning the live `LapRuler` or
        None - a callable because the controller builds its ruler with the
        pit wall, after the race is armed, and rebuilds it per session. None
        for either restores the unmodelled behaviour exactly. Set by whoever
        arms a race, every race, so a model never outlives its circuit
        (rule 11).
        """
        self._model = model
        self._ruler = ruler if model is not None else None

    @property
    def model(self) -> StraightsModel | None:
        return self._model

    def modelled_remaining_s(self) -> float | None:
        """`StraightsModel.remaining_s` against the live ruler, or None.

        Never raises: it is asked on the voice's thread, and a model that
        cannot answer is the fallback, not a silenced engineer.
        """
        model, ruler_of = self._model, self._ruler
        if model is None or ruler_of is None:
            return None
        try:
            ruler = ruler_of()
            if ruler is None:
                return None
            return model.remaining_s(ruler.where(),
                                     last_lap_m=ruler.last_lap_length_m,
                                     speed_ms=self._speed_ms)
        except Exception:                               # noqa: BLE001
            return None

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
        # **With a model, the remaining time is read here**, so neither
        # caller of `fits` has to know a model exists. The same torn-read
        # doctrine: the ruler's distance and last lap are each read once, and
        # a crossing seen late still lands on the wrapped pit straight.
        if remaining_s is None and self._model is not None:
            remaining_s = self.modelled_remaining_s()
        return Window(held_s=max(0.0, now - since), remaining_s=remaining_s)

    def update(self, *, throttle_pct: float | None, speed_ms: float | None,
               yaw_rate: float | None, now: float) -> bool:
        """True once the car has been straight and flat for long enough.

        **Stays true for the rest of the straight**, so a caller that has
        something to say does not have to catch one particular frame.
        """
        self._fed_at = now
        self._speed_ms = speed_ms
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
