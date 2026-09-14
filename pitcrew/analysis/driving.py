"""How the lap was driven - lift-and-coast and upshift rpm, off the frames.

`laps.short_shift_rpm` records the APP's switch and nothing else. It read `0.0`
on all twenty laps of the Deep Forest race while the driver short-shifted by
hand for twelve of them and lift-and-coasted for the same twelve, and the
debrief read that zero as evidence and invented a cause for the burn step.
Measured afterwards off the frames it decomposed exactly: coasting stopped at
the stop (+0.47 L/lap, shift rpm identical), short-shifting stopped on lap 17
(+0.23 L/lap, coast identical). Both were in the 60 Hz archive the whole time.

Two numbers per lap, taken at the crossing from the rows in hand, the way
`analysis/incidents.read_rows` takes its three:

* **coast share** - the fraction of the lap's frames spent off both pedals
  above walking pace. A lift-and-coast is a lift with no brake; a corner is a
  lift with a brake somewhere near it, and the speed floor keeps the pit lane
  and the grid out.
* **upshift rpm** - the median rpm at which he took his upshifts, under power.
  **The throttle is read LOOKBACK frames before the change, not at it**: the
  frame before a shift reads 16-58% because he lifts to shift, so gating on
  the shift frame rejects every real upshift (`tools/shortshift_trade.py`,
  trap 1; memory, 6 Sep 2026).

* **full-throttle share** and **braking share** - the fraction of frames at
  or above `FULL_THROTTLE_PCT` throttle, and at or above `BRAKING_PCT` brake.
  Plan row 5.7: Campbell-Brennan (Racecar Engineering, 2021) uses the first as a
  rear-degradation and traction instrument; neither is quoted as one until it
  has passed `analysis/instrument_gate`.

All are None where the lap cannot carry them - too few frames, no upshift
under power - never zero. **A frame with no pedal reading is left out of that
share's count, not read as a released pedal** (rule 3): `brake_pct or 0.0`
used to count a missing brake frame as coasting.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

# Off both pedals: below this on each, in percent.
PEDAL_OFF_PCT = 5.0
# Above this the car is on the circuit; below it, in the lane or on the grid.
COAST_MIN_KPH = 60.0
# Frames before an upshift over which the throttle must have been open for
# the shift to count as one taken under power.
LOOKBACK = 15
FULL_THROTTLE_PCT = 90.0
# Real pressure, not a foot resting on the pedal - the same threshold
# `tools/braking_change.py` finds braking events with.
BRAKING_PCT = 20.0
# A lap needs this many frames before a share is a share (~10 s at 60 Hz).
MIN_FRAMES = 600


@dataclass(frozen=True)
class DrivingRead:
    coast_pct: float | None          # % of frames off both pedals above 60 km/h
    full_throttle_pct: float | None  # % of frames at >= 90% throttle
    upshift_rpm: float | None        # median upshift rpm under power
    upshifts: int                    # how many upshifts under power were seen
    frames: int
    # Appended with a default: `DrivingRead` is built positionally.
    braking_pct: float | None = None  # % of frames at >= 20% brake


def read_rows(rows: list[list], field_names) -> DrivingRead:
    """From the recorder's column-array rows, while they are still in hand."""
    index = {name: position for position, name in enumerate(field_names)}
    wanted = ("speed_kph", "throttle_pct", "brake_pct", "gear", "rpm")
    if any(name not in index for name in wanted):
        return DrivingRead(None, None, None, 0, len(rows))
    frames = [{name: row[index[name]] for name in wanted} for row in rows]
    return read_frames(frames)


def read_frames(frames: list[dict]) -> DrivingRead:
    """From decoded frames (`store.get_lap_frames(...)["frames"]`)."""
    count = len(frames)
    if count < MIN_FRAMES:
        return DrivingRead(None, None, None, 0, count)
    coasting = flat = braking = 0
    coast_seen = throttle_seen = brake_seen = 0
    for f in frames:
        throttle = f.get("throttle_pct")
        brake = f.get("brake_pct")
        speed = f.get("speed_kph")
        if throttle is not None:
            throttle_seen += 1
            if throttle >= FULL_THROTTLE_PCT:
                flat += 1
        if brake is not None:
            brake_seen += 1
            if brake >= BRAKING_PCT:
                braking += 1
        if throttle is not None and brake is not None and speed is not None:
            coast_seen += 1
            if (throttle < PEDAL_OFF_PCT and brake < PEDAL_OFF_PCT
                    and speed >= COAST_MIN_KPH):
                coasting += 1

    def share(hits: int, seen: int) -> float | None:
        return round(100.0 * hits / seen, 2) if seen >= MIN_FRAMES else None
    shifts: list[float] = []
    for i in range(LOOKBACK, count):
        gear, before = int(frames[i].get("gear") or 0), int(frames[i - 1].get("gear") or 0)
        if not (gear == before + 1 and before >= 1):
            continue
        window = [frames[j].get("throttle_pct") or 0.0
                  for j in range(i - LOOKBACK, i)]
        if max(window) < FULL_THROTTLE_PCT:
            continue
        rpm = frames[i - 1].get("rpm")
        if rpm:
            shifts.append(float(rpm))
    return DrivingRead(
        coast_pct=share(coasting, coast_seen),
        full_throttle_pct=share(flat, throttle_seen),
        upshift_rpm=(round(median(shifts)) if shifts else None),
        upshifts=len(shifts),
        frames=count,
        braking_pct=share(braking, brake_seen))


# --- the step, lap over lap -----------------------------------------------------

# A coast share falling by this many points, or an upshift rpm rising by this
# many, held for two laps against the stint's earlier median, is the driver
# having stopped saving. Deep Forest: coast 8.3 -> 6.1 % at the stop, upshift
# 8298 -> 8694 on lap 17.
COAST_STEP_PCT = 2.0
UPSHIFT_STEP_RPM = 250.0
# Laps on each side of the step before it is believed.
STEP_LAPS = 2


@dataclass(frozen=True)
class SavingChange:
    lap: int                      # the first lap on the new behaviour
    what: str                     # "lift-and-coast" | "short-shift"
    before: float
    after: float


def _sd(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def saving_change(history: list[tuple[int, DrivingRead]]) -> SavingChange | None:
    """The lap the driver stopped saving, if the last two laps say so.

    `history` is this stint's (lap, read) pairs in order. The last `STEP_LAPS`
    are compared with the median of everything before them; a change needs
    at least `STEP_LAPS` on each side. Coast is tested first because it is
    the bigger lever; upshift rpm second. None where nothing moved, or where
    the stint is too short to say.
    """
    if len(history) < 2 * STEP_LAPS:
        return None
    earlier, recent = history[:-STEP_LAPS], history[-STEP_LAPS:]

    def values(rows, key):
        return [getattr(read, key) for _lap, read in rows
                if getattr(read, key) is not None]

    for key, what, step, up in (("coast_pct", "lift-and-coast", COAST_STEP_PCT, False),
                                ("upshift_rpm", "short-shift", UPSHIFT_STEP_RPM, True)):
        old, new = values(earlier, key), values(recent, key)
        if len(old) < STEP_LAPS or len(new) < STEP_LAPS:
            continue
        before, after = median(old), median(new)
        # **Sized on the stint's own scatter where there is enough of it.** A
        # coast share varies lap to lap by a couple of points on a clean
        # stint (Deep Forest stint 2: sd ~1.7), so a fixed 2-point step would
        # fire on about one pair in a hundred. Two of the stint's own sd, or
        # the fixed step, whichever is larger.
        if len(old) >= 3:
            step = max(step, 2.0 * _sd(old))
        moved = (after - before) if up else (before - after)
        # Every recent lap has to sit past the step, not just their median -
        # one saving lap and one flat-out lap average to nothing.
        each = all(((v - before) if up else (before - v)) >= step for v in new)
        if moved >= step and each:
            return SavingChange(lap=recent[0][0], what=what,
                                before=round(before, 1), after=round(after, 1))
    return None
