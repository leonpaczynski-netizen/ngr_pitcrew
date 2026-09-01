"""Lap distance, anchored to the circuit rather than integrated blind.

**`lap_distance_m` is not in the packet.** GT7 broadcasts no lap-distance
channel at all, so `telemetry/recorder.py` integrates one from speed at 60 Hz.
Corner identity is a window of lap distance, so every corner aggregate in every
export rests on that integration - and Ludo is now the only author of setups,
which makes corner aggregates the thing he reads to build one.

### What it is worth today, measured

Against each circuit's own length from `track_layouts`:

| circuit | true | median | min | max | sd |
|---|---|---|---|---|---|
| Monza full | 5,793 | 5,748 | 203 | 11,187 | 1,187 |
| Watkins Glen long | 5,423 | 5,412 | 5,163 | 8,278 | 503 |
| Red Bull Ring short | 2,336 | 2,314 | 2,065 | 3,354 | 216 |

Two separate faults, and they need opposite treatments:

1. **A systematic shortfall of 0.2-0.9%**, in the same direction on all three.
   That is an integration bias, it accrues smoothly across the lap, and it is
   *correctable* - the true length is known and the lap ran exactly one of
   them, so the scale factor is not a guess.
2. **Laps at twice the length and laps at a third of it.** A lap that swallowed
   a missed crossing integrates to roughly two laps; a fragment to a few
   hundred metres. Those are not imprecise about their corners, they are
   measuring a different piece of road, and no scale factor rescues them.

So: **anchor what can be anchored, null what cannot.** Rule 3 - a lap whose
distance channel cannot be trusted carries `None`, not a number nobody
measured.

### Why a linear rescale is the right model, and where it would not be

The surviving laps' error is the smooth kind: it accrues in proportion to
distance travelled, because it comes from integrating a speed that is slightly
off. A single dropped packet is a *step*, not a slope, and a linear rescale
would smear it across the whole lap - which is why the laps carrying steps are
nulled first rather than scaled. The gate is what makes the rescale honest.

**`length_gate` is not replaced.** It compares each lap against the session's
own median and it is kept, because it catches a lap that disagrees with its
neighbours even where the circuit length is unknown. What it could never catch
is a whole session biased the same way - the median moves with it - and that is
exactly the 0.2-0.9% this corrects.

### A third fault, found 1 Sep 2026, that neither of the above catches

`pos_x/y/z` gives a second and completely independent distance: the sum of the
straight lines between consecutive samples. At 60 Hz and 300 km/h a real step
is 1.4 m, so chord-versus-arc error is beneath notice. Comparing the two axes
across 672 stored laps settled two things.

**The integration is better than it was thought to be.** On the 224 good Monza
laps the two axes place a corner's minimum-speed point within half a metre of
each other (sd 17.6 m against 17.4 at T1, 19.8 against 19.7 at T2, and so on
through all six). Two independent instruments agreeing that closely are both
right, and the residual ~20 m is the DRIVER apexing in a different place - the
same fact the corner noise floor reports. Nothing done to the distance axis can
move it. They disagree by more than 2% on 1.6% of laps, not on 8-12%.

**But 7% of laps contain a teleport** - one frame in which the car moves
hundreds of metres. A track reset, a garage return, a session restart. Speed
integration cannot see it, because the speed channel reads zero through it, so
such a lap's integrated length is perfectly plausible and it sails through both
the tolerance above and `length_gate`. Every corner window after the jump is
then indexed against a lap driven partly somewhere else.

They are unmistakable: sampled over 220 laps the same 15 flag at a 10 m
threshold as at a 25 m one, and the smallest jump observed is 302 m against a
real per-frame step of 1.4 m. Two orders of magnitude of margin on either side,
so this cannot be confused with a run of dropped packets, which is legitimate
motion and stays.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

# How far a lap's own integrated length may sit from the circuit's true length
# and still be a lap of that circuit.
#
# **Wider than `thresholds.LAP_LENGTH_TOLERANCE` (2%), deliberately, and they
# answer different questions.** That one asks whether a lap agrees with its
# neighbours, where 2% is a tight and useful bar. This one asks whether the lap
# is a lap AT ALL, and refusing at 2% against the circuit would null the good
# laps of a session whose integration bias happens to be 3% - throwing away
# every corner in it to avoid a scale factor that was measured, not guessed.
#
# 10% is chosen against what the faults actually look like: the smooth bias is
# under 1% on all three circuits on file, and the broken laps are out by 40% to
# 100%. Nothing observed sits between.
CIRCUIT_TOLERANCE = 0.10

# **A step no car made.** 300 km/h at 60 Hz is 1.4 m between samples; the
# smallest teleport in the archive is 302 m. This sits clear of both rather
# than tuned between them - the lap count it produces is identical at 10 m and
# at 25 m - so a run of dropped packets, which is real motion, is never mistaken
# for a reset.
TELEPORT_STEP_M = 25.0

_POSITION = ("pos_x", "pos_y", "pos_z")


@dataclass(frozen=True)
class Teleport:
    """Whether the car was moved rather than driven, and by how far."""
    count: int = 0
    longest_m: float = 0.0

    @property
    def happened(self) -> bool:
        return self.count > 0

    def describe(self) -> str:
        return (f"the car jumped {self.longest_m:.0f} m in one frame "
                f"({self.count}x) - a reset or a garage return, so every "
                "distance after it is against a different axis")


def teleports(frames) -> Teleport:
    """Find the discontinuities in one lap's path.

    Read off position, which is the only channel that can see them: speed
    reads zero through a reset, so the integrated distance comes out plausible
    and no length check can catch it.
    """
    count, longest, previous = 0, 0.0, None
    for frame in frames or ():
        point = tuple(frame.get(key) for key in _POSITION)
        if any(value is None for value in point):
            # Absent is missing, not stationary - and emphatically not a jump.
            previous = None
            continue
        if previous is not None:
            step = math.dist(point, previous)
            if step > TELEPORT_STEP_M:
                count += 1
                longest = max(longest, step)
        previous = point
    return Teleport(count=count, longest_m=longest)


@dataclass(frozen=True)
class Anchored:
    """Laps with a trustworthy distance channel, and what was refused.

    `scale` is per lap and is exported, because a corrected number that does
    not say it was corrected is a derived figure wearing a measured one's
    clothes - CLAUDE.md rule 5.
    """
    laps: list
    refused: list[tuple[object, float]]
    circuit_length_m: float | None = None
    ran: bool = False
    # Laps whose path jumped. Kept apart from `refused` because the reason is
    # different and a caller reporting "could not be anchored" would otherwise
    # tell the driver his lap was the wrong length when it was the right
    # length driven in two places.
    teleported: list[tuple[object, "Teleport"]] = field(default_factory=list)

    def as_export(self) -> dict:
        """What the payload has to say about it. Never a bare corrected number."""
        return {
            "ran": self.ran,
            "circuitLengthM": self.circuit_length_m,
            "tolerance": CIRCUIT_TOLERANCE,
            "lapsRefused": len(self.refused),
            "lapsTeleported": len(self.teleported),
            "teleportedLaps": [{"lap": getattr(lap, "lap_num", None),
                                "jumpM": round(found.longest_m, 1)}
                               for lap, found in self.teleported] or None,
            "refusedLaps": [{"lap": getattr(lap, "lap_num", None),
                             "integratedM": round(length, 1)}
                            for lap, length in self.refused] or None,
        }


def integrated_length(lap) -> float | None:
    """How far this lap's own frames say it went. None with no channel."""
    distances = [frame.get("lap_distance_m") for frame in (lap.frames or ())
                 if frame.get("lap_distance_m") is not None]
    return max(distances) if distances else None


def anchor(laps: list, circuit_length_m: float | None) -> Anchored:
    """Scale each lap's distance onto the circuit, or refuse the lap.

    **`ran=False` when the circuit length is unknown**, and the laps come back
    untouched. Every circuit in `track_layouts` has one, but a layout the
    catalogue has never heard of is a real state and silently skipping would
    make an uncorrected export indistinguishable from a corrected one.
    """
    if not circuit_length_m or circuit_length_m <= 0:
        return Anchored(list(laps), [], None, ran=False)

    limit = circuit_length_m * CIRCUIT_TOLERANCE
    kept, refused, jumped = [], [], []
    for lap in laps:
        # **The teleport is checked first, and against position.** A lap that
        # jumped is not the wrong length - the speed channel reads zero through
        # a reset, so its integrated length is plausible and it would otherwise
        # be scaled and used. The scale is the wrong treatment twice over: the
        # error is a step and a linear rescale smears it across the whole lap.
        found = teleports(lap.frames)
        if found.happened:
            jumped.append((lap, found))
            kept.append(_without_distance(lap))
            continue
        length = integrated_length(lap)
        if length is None:
            # **No channel is not a bad channel.** The lap contributes no
            # corner windows either way, and refusing it would report an
            # exclusion that changed no number.
            kept.append(lap)
            continue
        if length <= 0 or abs(length - circuit_length_m) > limit:
            refused.append((lap, length))
            kept.append(_without_distance(lap))
            continue
        kept.append(_rescaled(lap, circuit_length_m / length))
    return Anchored(kept, refused, circuit_length_m, ran=True,
                    teleported=jumped)


def _rescaled(lap, scale: float):
    """Every frame's distance multiplied onto the circuit's true length.

    Returns the lap unchanged where the scale is already 1.0 - not an
    optimisation, but so that a lap needing no correction is bit-identical to
    the one that was recorded, and a diff between two exports shows only what
    actually moved.
    """
    if scale == 1.0 or not lap.frames:
        return lap
    frames = []
    for frame in lap.frames:
        distance = frame.get("lap_distance_m")
        if distance is None:
            frames.append(frame)
        else:
            frames.append({**frame,
                           "lap_distance_m": round(distance * scale, 2)})
    return replace(lap, frames=frames)


def _without_distance(lap):
    """The lap with its distance channel nulled, and everything else kept.

    **Nulled rather than dropped.** The lap's fuel, its time and its
    temperatures were all measured properly; only the distance is untrustworthy.
    Dropping the whole lap to be rid of one channel would take four good
    measurements out of the session to remove one bad one.
    """
    if not lap.frames:
        return lap
    return replace(lap, frames=[{**frame, "lap_distance_m": None}
                                for frame in lap.frames])


def circuit_length(store, event: dict) -> float | None:
    """The circuit's own length in metres, from the shipped catalogue.

    Keyed by the same slug `analysis/resolve.circuit_key` builds, which is what
    `track_layouts.slug` holds - so this is a lookup and not a match.
    """
    from pitcrew.analysis.resolve import circuit_key

    track = event.get("track")
    if not track:
        return None
    rows = store.layout_length_m(circuit_key(track, event.get("layout")))
    return float(rows) if rows else None
