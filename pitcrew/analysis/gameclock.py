"""What a lobby's time-of-day setting actually does, measured from the stream.

GT7's lobby does not offer a clock. It offers names — *Late Morning*,
*Afternoon*, *Evening* — and what hour each one starts at differs by track and
is documented nowhere reliable. The community lists that do exist are from
2022, cover a subset of the circuits, and map no preset to an hour at all.

**It does not need to be looked up, because it is broadcast.** GT7 sends its own
clock in every packet. Three things fall straight out of it:

* **the hour the session started**, which is what the preset means at this
  circuit;
* **the time multiplier**, as the rate the game clock runs against the real
  one — measured, not typed. Session 9 of the Monza practice reads exactly
  6.00 on eight consecutive laps;
* **where the clock stops**. A circuit without a 24-hour cycle runs its clock
  forward to the end of its range and then holds it there — it does not roll
  into the next morning. Session 9 shows precisely that: ×6 for nine laps,
  then 3.33, then nothing. **A 50-minute race at ×6 does not cover five hours
  of a daytime-only circuit.** No table would have said so; the stream does.

So a preset is not interpreted here, it is **measured**, per circuit, the first
time it is run. Until then the app says it does not know, which is the honest
state and the one that tells the driver what to go and drive.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from pitcrew.analysis.session import LapInput

DAY_MS = 24 * 60 * 60 * 1000

# Below this the game clock is not moving: the lobby is set to a fixed time of
# day, or the circuit's clock has run to the end of its range and stopped.
STOPPED_RATIO = 0.05

# A lap whose frame buffer covers more than the lap itself - the first of a
# session, an out-lap picked up mid-pit - reports a ratio far above the truth.
# The median across laps handles it; this only keeps the obvious nonsense out.
MAX_PLAUSIBLE_MULTIPLIER = 120.0


@dataclass(frozen=True)
class ClockReading:
    """What the game clock did across one session."""
    multiplier: float | None
    start_hour: float | None
    end_hour: float | None
    stopped_at_hour: float | None
    laps_sampled: int
    note: str

    @property
    def measured(self) -> bool:
        return self.multiplier is not None or self.start_hour is not None

    def as_export(self) -> dict:
        return {
            "multiplier": self.multiplier,
            "startHour": self.start_hour,
            "endHour": self.end_hour,
            "stoppedAtHour": self.stopped_at_hour,
            "lapsSampled": self.laps_sampled,
            "source": "measured-from-the-game-clock",
            "note": self.note,
        }


def _stamps(lap: LapInput) -> list[int]:
    return [frame["time_of_day_ms"] for frame in (lap.frames or ())
            if frame.get("time_of_day_ms") is not None]


def _hour(time_of_day_ms: float) -> float:
    return (time_of_day_ms % DAY_MS) / 3_600_000.0


def lap_multiplier(lap: LapInput) -> float | None:
    """How much game time this lap covered, per second of real time."""
    stamps = _stamps(lap)
    if len(stamps) < 2 or lap.lap_time_ms <= 0:
        return None
    game_ms = stamps[-1] - stamps[0]
    if game_ms < 0:                      # the clock wrapped past midnight
        game_ms += DAY_MS
    ratio = game_ms / lap.lap_time_ms
    return ratio if ratio <= MAX_PLAUSIBLE_MULTIPLIER else None


def read_clock(laps: list[LapInput]) -> ClockReading:
    """Everything the game clock says about one session's conditions."""
    ratios = [(lap, lap_multiplier(lap)) for lap in laps]
    ratios = [(lap, ratio) for lap, ratio in ratios if ratio is not None]
    if not ratios:
        return ClockReading(
            None, None, None, None, 0,
            "No lap carries GT7's clock, so what this lobby setting means at "
            "this circuit is unknown. Run one session at it and the app will "
            "read the hour and the multiplier off the stream.")

    moving = [ratio for _, ratio in ratios if ratio > STOPPED_RATIO]
    multiplier = round(median(moving), 2) if moving else 0.0

    stamps = [stamp for lap, _ in ratios for stamp in _stamps(lap)]
    start_hour = round(_hour(stamps[0]), 3) if stamps else None
    end_hour = round(_hour(stamps[-1]), 3) if stamps else None

    stopped = _stopped_at(ratios)
    return ClockReading(
        multiplier=multiplier,
        start_hour=start_hour,
        end_hour=end_hour,
        stopped_at_hour=stopped,
        laps_sampled=len(ratios),
        note=_note(multiplier, start_hour, end_hour, stopped, len(ratios)),
    )


def _stopped_at(ratios: list[tuple[LapInput, float]]) -> float | None:
    """The hour the clock stopped advancing, if it did so mid-session.

    A circuit without a 24-hour cycle holds its clock at the end of its range
    rather than rolling into the next morning, so this is that circuit's
    ceiling - and it is a hard limit on what any race here can cover, however
    long the race or however high the multiplier.
    """
    moved = False
    for lap, ratio in ratios:
        if ratio > STOPPED_RATIO:
            moved = True
            continue
        if moved:
            stamps = _stamps(lap)
            return round(_hour(stamps[0]), 3) if stamps else None
    return None


def _note(multiplier: float | None, start: float | None, end: float | None,
          stopped: float | None, laps: int) -> str:
    if multiplier == 0.0:
        return (f"The clock did not move across {laps} laps, so this setting "
                f"holds a fixed time of day"
                + (f" at {clock(start)}." if start is not None else "."))
    parts = [f"Measured over {laps} laps: the game clock runs at "
             f"x{multiplier:g}"]
    if start is not None:
        parts.append(f"from {clock(start)}")
    if stopped is not None:
        parts.append(
            f"and stops at {clock(stopped)} - this circuit has no 24-hour "
            f"cycle, so its clock holds there rather than running into the "
            f"next morning, and no race here can cover conditions past it")
    elif end is not None:
        parts.append(f"to {clock(end)}")
    return " ".join(parts) + "."


def clock(hour: float | None) -> str:
    if hour is None:
        return "unknown"
    hour = hour % 24.0
    whole = int(hour)
    return f"{whole:02d}:{int(round((hour - whole) * 60)) % 60:02d}"


def race_span(reading: ClockReading | None, minutes: float | None,
              declared_start: float | None = None,
              declared_multiplier: float | None = None
              ) -> tuple[float, float] | None:
    """The game hours a race actually passes through.

    Measured values win over declared ones, and the circuit's own ceiling wins
    over both: a race cannot run into conditions the circuit's clock will not
    reach. That is the difference between planning five hours of an evening
    and planning the ninety minutes the track will actually give.
    """
    start = declared_start
    multiplier = declared_multiplier
    ceiling = None
    if reading is not None:
        if reading.start_hour is not None:
            start = reading.start_hour
        if reading.multiplier is not None:
            multiplier = reading.multiplier
        ceiling = reading.stopped_at_hour

    if start is None or not minutes or multiplier is None:
        return None
    end = start + (minutes * multiplier) / 60.0
    if ceiling is not None:
        # The ceiling is a clock hour; unwrap it onto the same axis as `end`.
        limit = ceiling if ceiling >= start else ceiling + 24.0
        end = min(end, limit)
    return start, end
