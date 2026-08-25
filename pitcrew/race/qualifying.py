"""The qualifying coach: warm the set on the out lap, then chase the reference.

The driver asked for a session "that gets my tyres up to temp on out lap and
pushes and coaches me through a flying lap based on my best lap in practice."
He is under a helmet, often in a headset, so the whole product here is the
voice - CLAUDE.md §5.5's register, one thing at a time, the instruction first
and the reason short. The screen shows only that the coach is armed and what
it was armed with.

Two halves, armed separately and honestly:

* **Temperature.** The target is the window measured from this event's own
  practice laps (`race/temps.py`), never the strategy layer's fabricated band.
  No measured window means the out-lap coach speaks relative trend only
  ("Tyres still coming up.") or stays quiet - it never invents a target
  number.
* **Delta.** The reference is the best counted practice lap's own frames,
  read through the Store so the distance and clock repairs apply. No
  reference lap means the delta half stands down and says so once - that is
  a statement of what practice measured, not a failure.

**Sign convention, used everywhere in this module: "up" means faster -
ahead of the reference - and "down" means slower.** The delta is
`reference elapsed at this distance minus live elapsed`, so positive is up.

The live position on the flying lap is lap distance integrated from speed
against the packet counter, exactly as the recorder does it. Integration
drifts, so the mid-lap calls say "about" until a completed flyer has shown
the drift is inside `NOISE_OK_S` - and the line call never relies on it at
all, because GT7's own lap time is exact. Tenths, never hundredths.

Threading: `update()` runs on the UDP thread, fed from `on_packet` beside the
shift beep. It returns nothing and speaks through a callable that is a queue
put (`Voice.say`), so nothing here waits on a sound card or touches Qt.
"""
from __future__ import annotations

import enum
from bisect import bisect_right
from dataclasses import dataclass

from pitcrew.diagnostics import log
from pitcrew.engineer import say
from pitcrew.race.temps import TempWindow
from pitcrew.telemetry.recorder import SAMPLE_HZ
from pitcrew.telemetry.session_state import EventKind

# The car has set off on its out lap. The same figure the race start uses for
# "still on the grid" - below it he is rolling out of the box, not driving.
SET_OFF_KMH = 30.0

# No temperature call within this many seconds of the previous call. Temps
# move a degree or two in that time; anything said sooner is chatter.
TEMP_CALL_SPACING_S = 15.0

# What counts as meaningful warm-up progress since the out lap began. Less
# than this and the mid-lap progress call has nothing to report.
PROGRESS_RISE_C = 5.0

# An axle this far below its measured floor at the line is worth stating
# plainly. Below it the deficit rounds to nothing a driver can act on.
COLD_AT_LINE_C = 2.0

# Where on the flying lap the two delta calls live, as fractions of the
# reference lap's distance. A third in confirms the lap has started well or
# not; two thirds in is the last point where a number still helps.
EARLY_FRACTION = 1.0 / 3.0
MID_FRACTION = 2.0 / 3.0

# Behind the reference by this much, the lap is not a flying lap any more -
# a spin, a cut, a bailed run. The coach drops back to the out lap quietly;
# nothing it could say about a lap this dead is worth a word.
ABANDON_BEHIND_S = 10.0

# ...and no abandon verdict before this much of the lap exists. On the
# crossing frame itself, whether GT7 has already reset the lap clock when
# `last_lap_ms` changes is UNVERIFIED against a live stream (CLAUDE.md:
# verify before building) - if the clock still holds the outgoing lap's
# time for a frame or two, the delta reads instantly ten seconds behind and
# a naive check killed every flyer at birth, silently. Two hundred metres
# is seconds past any plausible stale-field window and far before the first
# delta call at a third of the lap.
ABANDON_MIN_DISTANCE_M = 200.0

# A reference candidate's claimed time has to describe its own frames.
# Session 42's fastest "lap" claims 104.431 s over frames spanning 123.3 s -
# the documented lobby-join phantom, a lap he never drove wearing a time it
# never set - and chasing it put every delta call 8-15 s out on the real
# replay. Genuine laps at the same event agree within 0.1%; two per cent
# absorbs stream gaps without admitting a phantom.
REFERENCE_SPAN_TOLERANCE = 0.02

# The out-lap judgments compare against floors built from LAP MEANS
# (`race/temps.py` takes percentiles of per-lap means), so the live figure
# has to be a mean too: the start/finish straight reads coolest, and judged
# frame-by-frame a car at working temperature heard "still 7 cold" at the
# worst possible moment. A rolling mean over the last half minute, sampled
# once a second, is the like-for-like figure.
ROLLING_WINDOW_S = 30.0
ROLLING_SAMPLE_S = 1.0

# Mid-lap deltas rest on integrated distance. Until a completed flyer has
# shown the integration lands inside this of the reference, the wording
# widens to "about" - a claim of precision the arithmetic cannot support is
# exactly what CLAUDE.md's derived-versus-measured rule forbids.
NOISE_OK_S = 0.2

# Inside this of level, the delta is level. A tenth is the resolution of
# every call here, so half of one is the dead band.
LEVEL_BAND_S = 0.05

def _tenths_words(seconds: float) -> str:
    """Say a gap the way an engineer would: tenths, then plain seconds.

    **Kept as a name, moved as an implementation.** It used to drop the unit
    above a second - "one point three down" - which is a number with no
    dimension in the middle of a sentence. `say.spoken_gap` attaches it.
    """
    return say.spoken_gap(seconds)


def _axle_means(packet) -> tuple[float, float]:
    temps = packet.tyre_temps
    return (temps[0] + temps[1]) / 2.0, (temps[2] + temps[3]) / 2.0


@dataclass(frozen=True)
class ReferenceLap:
    """The best practice lap as a distance-to-elapsed curve, plus its time.

    The curve is strictly monotonic in distance - duplicate and regressive
    samples (a car briefly stationary, a repaired old blob) are dropped on
    build, because interpolation over a non-monotonic curve answers a
    different question at every lookup.
    """
    lap_id: int
    lap_time_ms: int
    distances: tuple[float, ...]
    elapsed_ms: tuple[float, ...]

    @classmethod
    def from_frames(cls, frames: list[dict], *, lap_id: int,
                    lap_time_ms: int) -> "ReferenceLap | None":
        distances: list[float] = []
        elapsed: list[float] = []
        for frame in frames:
            d, t = frame.get("lap_distance_m"), frame.get("t_ms")
            if d is None or t is None:
                continue
            if distances and (d <= distances[-1] or t < elapsed[-1]):
                continue
            distances.append(float(d))
            elapsed.append(float(t))
        if len(distances) < 2 or lap_time_ms <= 0:
            return None
        return cls(lap_id=lap_id, lap_time_ms=lap_time_ms,
                   distances=tuple(distances), elapsed_ms=tuple(elapsed))

    @property
    def total_m(self) -> float:
        return self.distances[-1]

    def elapsed_at(self, distance_m: float) -> float:
        """Reference elapsed ms at a lap distance, clamped at the ends."""
        if distance_m <= self.distances[0]:
            return self.elapsed_ms[0]
        if distance_m >= self.distances[-1]:
            return self.elapsed_ms[-1]
        i = bisect_right(self.distances, distance_m)
        d0, d1 = self.distances[i - 1], self.distances[i]
        t0, t1 = self.elapsed_ms[i - 1], self.elapsed_ms[i]
        return t0 + (t1 - t0) * (distance_m - d0) / (d1 - d0)


def reference_lap(store, event_id: int) -> ReferenceLap | None:
    """The best counted practice lap at this event, as a reference curve.

    Counted means what it means everywhere else: not excluded, not an
    out-lap, not a pit lap, and carrying a real time. None where practice
    recorded nothing usable - the coach then says so and coaches temperature
    only, which is the honest half it can still do.
    """
    rows = [row for row in store.list_event_laps(event_id, "practice")
            if not row.get("excluded")
            and not row.get("is_out_lap") and not row.get("is_pit_lap")
            and (row.get("lap_time_ms") or 0) > 0]
    # Fastest first, falling back down the order: a curve needs frames, and
    # a lap recorded without them (stream started late) cannot be one however
    # fast it was. The fallback is the best lap that can actually be chased.
    #
    # Known blindness, accepted for now: neither this nor the temperature
    # window is compound- or weather-aware - the reference is simply the
    # event's best counted lap, whatever set and sky it was driven under.
    # A follow-up, not this change.
    for row in sorted(rows, key=lambda row: row["lap_time_ms"]):
        stored = store.get_lap_frames(row["id"])
        if not stored:
            continue
        # The claimed time has to describe the frames - see
        # REFERENCE_SPAN_TOLERANCE for the phantom this gate exists to stop.
        span_ms = (stored["frame_count"]
                   / (stored["sample_hz"] or SAMPLE_HZ) * 1000.0)
        if (abs(span_ms - row["lap_time_ms"])
                > row["lap_time_ms"] * REFERENCE_SPAN_TOLERANCE):
            log("quali").info(
                "reference candidate lap %s rejected: claims %d ms, frames "
                "span %.0f ms - a time its own recording contradicts",
                row["id"], row["lap_time_ms"], span_ms)
            continue
        reference = ReferenceLap.from_frames(
            stored["frames"], lap_id=row["id"],
            lap_time_ms=int(row["lap_time_ms"]))
        if reference is not None:
            return reference
    return None


class _Phase(enum.Enum):
    ARMED = "armed"        # session open, car not yet away
    WAITING = "waiting"    # armed mid-lap; silent until the next crossing
    OUT_LAP = "out_lap"    # warming the set
    FLYING = "flying"      # on a timed run against the reference


class QualifyingCoach:
    """Per-frame consumer for a qualifying session. Speaks; never blocks.

    The machine is ARMED -> OUT_LAP -> FLYING and back: every line crossing
    from the out lap starts a flyer, every completed flyer rolls straight
    into the next one, a pit entry or a dead lap drops quietly back a state.
    Session stop is simply the controller letting go of the object.

    `mid_lap=True` starts in WAITING instead: the coach was armed with the
    car already circulating - an intent flip mid-session - and announcing
    "Out lap" into the middle of a flying lap would be wrong about the one
    thing it claims. WAITING says nothing and joins in at the next line
    crossing, choosing out lap or flyer by whether the set is in its window.
    """

    def __init__(self, *, window: TempWindow | None,
                 reference: ReferenceLap | None,
                 speak=None, mid_lap: bool = False) -> None:
        self.window = window
        self.reference = reference
        self._speak = speak
        # Everything said, spoken or not - the auditable record, mirrored
        # into log("quali") line by line.
        self.said: list[str] = []
        self.phase = _Phase.WAITING if mid_lap else _Phase.ARMED
        # (time, front, rear) samples over the last ROLLING_WINDOW_S - the
        # like-for-like figure every window comparison uses. See the
        # constant for why frame-by-frame reads must not be judged.
        self._temp_samples: list[tuple[float, float, float]] = []
        # The time the line call is judged against: the reference to start
        # with, then the best of what he actually sets tonight, so "Purple"
        # is never claimed twice for the same pace.
        self._best_ms = reference.lap_time_ms if reference else None
        self._last_call_at: float | None = None
        # Out-lap state, reset each time one begins.
        self._out_start: tuple[float, float] | None = None
        self._out_progress_said = False
        self._out_window_said = False
        # Flying-lap state.
        self._distance_m = 0.0
        self._elapsed_ms = 0.0
        self._last_packet_id: int | None = None
        self._early_said = False
        self._mid_said = False
        self._clean_flyer = False
        self._flyer_started_in_window = False
        # Measured on each completed clean flyer: what the integrated
        # distance missed the reference's total by, expressed in seconds of
        # lap time. None until measured, and "about" until it is small.
        self._noise_s: float | None = None
        if reference is None:
            # The delta half stands down; the line call stays - GT7's lap
            # time is exact and it is the one number he wants at the line.
            self._say("No reference lap from practice - "
                      "temperatures and lap times only.", None)

    def set_speak(self, speak) -> None:
        """Follow the Speaks/Silent toggle live, like the race engineer.
        One reference assignment, safe against the UDP thread's reads."""
        self._speak = speak

    # ------------------------------------------------------------------ input

    def update(self, packet, events, now: float) -> None:
        """One frame, on the UDP thread. `events` are this frame's session
        events, already produced by `SessionState.update` upstream."""
        for event in events:
            self._on_event(event, packet, now)
        if packet.paused or packet.loading:
            # **The distance must not survive the gap.** GT7's packet
            # counter keeps running while paused, and an integrator that
            # left its last id behind would charge the resume frame with the
            # whole excursion - 30 s paused at 500 m read as 2,000 m and a
            # spurious "Up about 30". The recorder documents and closes this
            # exact hole (`recorder.record_frame`); this is the coach's half.
            self._last_packet_id = packet.packet_id
            return
        if not packet.car_on_track:
            # Back to the garage mid-session. Whatever was being coached is
            # over; the next time he sets off it is an out lap again.
            if self.phase is not _Phase.ARMED:
                self.phase = _Phase.ARMED
                self._reset_out_lap()
            self._last_packet_id = None
            return

        self._sample_temps(packet, now)
        if self.phase is _Phase.WAITING:
            return
        if self.phase is _Phase.ARMED:
            if packet.speed_kmh > SET_OFF_KMH:
                self._begin_out_lap(packet, now)
        elif self.phase is _Phase.OUT_LAP:
            self._coach_temps(packet, now)
        else:
            self._advance(packet)
            self._coach_delta(packet, now)

    # ----------------------------------------------------------------- events

    def _on_event(self, event, packet, now: float) -> None:
        if event.kind is EventKind.PIT_ENTRY:
            # An abandoned run. Quietly: he knows he pitted.
            self.phase = _Phase.ARMED
            self._reset_out_lap()
            self._clean_flyer = False
        elif event.kind is EventKind.LAP_COMPLETED:
            self._on_crossing(event.data["lap"], packet, now)

    def _on_crossing(self, lap, packet, now: float) -> None:
        if self.phase is _Phase.WAITING:
            # Armed mid-lap; this crossing is where the coaching joins in.
            # Cold set and a measured window: it is an out lap, said so.
            # Otherwise a flyer - he flipped the intent to qualify, and with
            # nothing measured to call the set cold, the push lap is the
            # honest default.
            front, rear = self._rolling_means(packet)
            if (self.window is not None
                    and (front < self.window.front[0]
                         or rear < self.window.rear[0])):
                self._begin_out_lap(packet, now)
            else:
                self._begin_flyer(packet)
        elif self.phase is _Phase.OUT_LAP:
            self._cold_at_line(packet, now)
            self._begin_flyer(packet)
        elif self.phase is _Phase.FLYING:
            if self._clean_flyer and not lap.is_pit_lap and lap.lap_time_ms > 0:
                self._measure_noise()
                self._line_call(lap, now)
            # The next lap is another run either way - tyres are warm, the
            # only question is whether he takes it.
            self._begin_flyer(packet)

    # ------------------------------------------------------------ temperature

    def _sample_temps(self, packet, now: float) -> None:
        """One (front, rear) sample a second, kept for ROLLING_WINDOW_S.

        Every judgment against the window reads the mean of these, never a
        single frame - the floors are percentiles of LAP MEANS and a lap has
        straights in it, so a frame read at the line is systematically the
        coolest reading the lap produces.
        """
        if self._temp_samples and now - self._temp_samples[-1][0] < ROLLING_SAMPLE_S:
            return
        front, rear = _axle_means(packet)
        self._temp_samples.append((now, front, rear))
        cutoff = now - ROLLING_WINDOW_S
        while len(self._temp_samples) > 1 and self._temp_samples[0][0] < cutoff:
            self._temp_samples.pop(0)

    def _rolling_means(self, packet) -> tuple[float, float]:
        """The rolling per-axle mean, or this frame's own where no sample
        has landed yet - one frame of history is one frame of mean."""
        if not self._temp_samples:
            return _axle_means(packet)
        fronts = [front for _, front, _ in self._temp_samples]
        rears = [rear for _, _, rear in self._temp_samples]
        return sum(fronts) / len(fronts), sum(rears) / len(rears)

    # ---------------------------------------------------------------- out lap

    def _reset_out_lap(self) -> None:
        self._out_start = None
        self._out_progress_said = False
        self._out_window_said = False

    def _begin_out_lap(self, packet, now: float) -> None:
        self.phase = _Phase.OUT_LAP
        self._reset_out_lap()
        # The opening call reads the gauges as they stand - a statement of
        # now, not a window judgment - but the warm-up baseline is the
        # rolling figure, the same construction every later comparison uses.
        front, rear = _axle_means(packet)
        self._out_start = self._rolling_means(packet)
        if self.window is not None:
            self._say(f"Out lap. Fronts {front:.0f}, rears {rear:.0f} - "
                      f"need {self.window.front[0]:.0f} "
                      f"and {self.window.rear[0]:.0f}.", now)
        else:
            # Measured temperatures only. No window on file means no target
            # number exists to speak.
            self._say(f"Out lap. Fronts {front:.0f}, rears {rear:.0f}.", now)

    def _coach_temps(self, packet, now: float) -> None:
        front, rear = self._rolling_means(packet)
        if self._out_start is None:
            # Reached without a set-off call - an abandoned flyer dropped
            # back here. The baseline is wherever the temps are now.
            self._out_start = (front, rear)
        if self.window is not None:
            floor_f, floor_r = self.window.front[0], self.window.rear[0]
            if front >= floor_f and rear >= floor_r:
                if not self._out_window_said and self._say(
                        "Tyres in window. Push when you cross the line.",
                        now, temp_call=True):
                    self._out_window_said = True
                return
            if not self._out_progress_said:
                start_f, start_r = self._out_start
                if (front - start_f >= PROGRESS_RISE_C
                        or rear - start_r >= PROGRESS_RISE_C):
                    # Name the axle further from its own floor - that is the
                    # one deciding when he can push. The judgment is the
                    # rolling mean, but the number spoken is the gauge as it
                    # reads now: the opening call spoke the gauge, and a
                    # rolling figure still carrying pit-exit cold would have
                    # this call say a LOWER number than the one before it -
                    # "rears 69" then "coming - 64" - which under a helmet
                    # reads as the set cooling.
                    gauge_f, gauge_r = _axle_means(packet)
                    axle, temp = (("Fronts", gauge_f)
                                  if floor_f - front >= floor_r - rear
                                  else ("Rears", gauge_r))
                    if self._say(f"{axle} coming - {temp:.0f}.",
                                 now, temp_call=True):
                        self._out_progress_said = True
            return
        # No measured window: trend only, or silence.
        if not self._out_progress_said:
            start_f, start_r = self._out_start
            if (front - start_f >= PROGRESS_RISE_C
                    or rear - start_r >= PROGRESS_RISE_C):
                if self._say("Tyres still coming up.", now, temp_call=True):
                    self._out_progress_said = True

    def _cold_at_line(self, packet, now: float) -> None:
        """Crossing the line to start the flyer with the set still cold.

        Stated plainly and left with him - the app informs, the driver
        decides. Nothing without a measured window: "cold" is a claim about
        a floor, and there is no floor to claim. Judged on the rolling mean,
        so a set at working temperature that happens to read cool on the
        straight is not called cold at the worst possible moment.
        """
        if self.window is None:
            return
        front, rear = self._rolling_means(packet)
        deficit_f = self.window.front[0] - front
        deficit_r = self.window.rear[0] - rear
        axle, deficit = (("Fronts", deficit_f)
                         if deficit_f >= deficit_r else ("Rears", deficit_r))
        if deficit >= COLD_AT_LINE_C:
            self._say(f"{axle} still {deficit:.0f} cold - your call.", now)

    # ------------------------------------------------------------- flying lap

    def _begin_flyer(self, packet) -> None:
        self.phase = _Phase.FLYING
        self._distance_m = 0.0
        self._elapsed_ms = 0.0
        self._last_packet_id = packet.packet_id
        self._early_said = False
        self._mid_said = False
        self._clean_flyer = True
        front, rear = self._rolling_means(packet)
        self._flyer_started_in_window = (
            self.window is not None
            and front >= self.window.front[0]
            and rear >= self.window.rear[0])

    def _advance(self, packet) -> None:
        """Integrate distance and time exactly as the recorder does: stepped
        by the packet counter, so a dropped packet costs its own distance."""
        if self._last_packet_id is None:
            step = 1
        else:
            step = packet.packet_id - self._last_packet_id
            if step <= 0:
                return
        self._last_packet_id = packet.packet_id
        self._distance_m += packet.speed_ms * step / SAMPLE_HZ
        self._elapsed_ms += step * 1000.0 / SAMPLE_HZ

    def _live_ms(self, packet) -> float:
        """Time on this lap: GT7's own channel where the C format carries it,
        the integrated clock otherwise. The channel is exact; the fallback
        drifts with the distance and shares its "about"."""
        lap_ms = packet.current_lap_time_ms
        if lap_ms is not None and lap_ms > 0:
            return float(lap_ms)
        return self._elapsed_ms

    def _coach_delta(self, packet, now: float) -> None:
        if self.reference is None:
            return
        # Positive = ahead of the reference = "up". See the module docstring.
        delta_s = (self.reference.elapsed_at(self._distance_m)
                   - self._live_ms(packet)) / 1000.0
        if (delta_s < -ABANDON_BEHIND_S
                and self._distance_m >= ABANDON_MIN_DISTANCE_M):
            # The lap is dead and he knows it better than the app does.
            # Quietly back to the out-lap state: both out-lap calls are
            # marked said, so nothing speaks until the next line crossing
            # starts the next run.
            self.phase = _Phase.OUT_LAP
            self._clean_flyer = False
            self._out_progress_said = True
            self._out_window_said = True
            self._out_start = None
            return
        fraction = self._distance_m / self.reference.total_m
        if not self._early_said and fraction >= EARLY_FRACTION:
            self._early_said = True
            self._say(self._delta_call(delta_s, early=True), now)
        elif not self._mid_said and fraction >= MID_FRACTION:
            self._mid_said = True
            self._say(self._delta_call(delta_s, early=False), now)

    def _delta_call(self, delta_s: float, *, early: bool) -> str:
        about = ("about " if self._noise_s is None
                 or self._noise_s > NOISE_OK_S else "")
        if abs(delta_s) < LEVEL_BAND_S:
            return "Level."
        words = _tenths_words(delta_s)
        if delta_s > 0:
            text = f"Up {about}{words}."
            return f"On it. {text}" if early else text
        if early:
            return f"Down {about}{words}."
        return f"Down {about}{words} - tidy the last sector."

    def _measure_noise(self) -> None:
        """What the integrated distance missed the reference total by, in
        seconds of lap time. This is what earns - or keeps - the "about"."""
        if self.reference is None or self.reference.total_m <= 0:
            return
        error = abs(self._distance_m - self.reference.total_m)
        self._noise_s = (error / self.reference.total_m
                         * self.reference.lap_time_ms / 1000.0)

    def _line_call(self, lap, now: float) -> None:
        """The lap is set. Judged against GT7's own times - exact, no
        integration in it - so this call never says "about"."""
        # **Spoken as a lap time, not as a count of seconds.** GT7's own exact
        # figure goes to the log through `_say`; what he hears is the form
        # every timing screen uses.
        spoken = say.spoken_lap_time(lap.lap_time_ms)
        if self._best_ms is None:
            # Temperature-only mode's first flyer: nothing measured to
            # compare against, so the exact time is the whole call. Purple
            # claims start once tonight has a best of its own.
            self._say(f"{spoken}.", now, exact_ms=lap.lap_time_ms)
            self._best_ms = lap.lap_time_ms
            return
        gap_s = (self._best_ms - lap.lap_time_ms) / 1000.0
        if abs(gap_s) < LEVEL_BAND_S:
            text = f"{spoken} - level with your best."
        elif gap_s > 0:
            text = (f"Purple. {spoken} - "
                    f"{_tenths_words(gap_s)} under your best.")
        else:
            text = f"{spoken} - {_tenths_words(gap_s)} down."
            if self._flyer_started_in_window:
                # The one diagnostic worth a second sentence: the set was
                # not the problem, so another run is worth taking.
                text += " Tyres were ready - grip should hold for another run."
        self._say(text, now, exact_ms=lap.lap_time_ms)
        self._best_ms = min(self._best_ms, lap.lap_time_ms)

    # ------------------------------------------------------------------ voice

    def _say(self, text: str, now: float | None, *,
             temp_call: bool = False, exact_ms: int | None = None) -> bool:
        """Record and speak one line. Temperature calls respect the spacing
        limiter - temps move slowly and a second call inside it is chatter.
        Structural calls (out-lap start, line calls) are events, not
        readings, and always go out. Returns whether it was said."""
        if (temp_call and now is not None and self._last_call_at is not None
                and now - self._last_call_at < TEMP_CALL_SPACING_S):
            return False
        self.said.append(text)
        # **The spoken form loses the thousandth on purpose; the log keeps
        # it.** He cannot act on a thousandth between two corners, but he can
        # read one back afterwards, and two of his laps are separated by it.
        if exact_ms:
            log("quali").info("said: %s  [%s]", text, say.lap_time(exact_ms))
        else:
            log("quali").info("said: %s", text)
        if now is not None:
            self._last_call_at = now
        if self._speak is not None:
            self._speak(text)
        return True
