"""Sector times — where the lap is cut, and what each piece took.

**GT7 sends no sectors.** Not a sector time, not a sector line, not a marker
that a sector line was crossed, in any of the four packet formats — the layout
in `telemetry/packet.py` is fully accounted for and there is no such field.
The race HUD does not draw them either, measured off 81 recorded frames. So
there is nothing to align to, and a sector here is the app's own claim in
exactly the way a corner is: it has to declare where the line is and where
that came from, or `S2` means a different piece of road next week.

### The lines, and their three provenances

Every entry in `SECTOR_LINES` carries a `source`, and the three are different
claims about how much to trust the boundary:

* **`timing-line`** — a published figure for the real circuit's own timing
  loop, in metres against a numbered corner.
* **`landmark`** — placed at a named corner because that is where the racing
  world's sector boundary sits, but without a published metre figure behind
  it. Good enough that `S1` means roughly what a timing sheet means by it; not
  a measurement, and it says so.
* **`thirds`** — no entry, so the lap is cut in three equal distances and each
  cut is then moved to the nearest edge of the stored corner model. Snapping
  costs nothing and buys the one thing equal thirds get wrong: a boundary
  landing mid-corner puts a corner's entry in one sector and its exit in the
  next, so the two sectors move in opposite directions every time he changes
  his line through it. With no corner model the cut stays where it fell.

A circuit gets a real line by adding two numbers to `SECTOR_LINES` below.
Nothing else has to change, and a lap already stored is re-derived because the
model it was measured against is stamped beside the times.

### The distance axis is integrated, and about 7% of laps cannot use it

`lap_distance_m` is integrated from speed — see `analysis/distance.py`. A lap
whose path teleported, or whose integrated length does not look like the
circuit, is **refused whole**: all three sectors come back `None`. Rule 3, and
rule 9 in particular — a sector time computed against boundaries that are
somewhere else on the road is not an imprecise number, it is a number about a
different piece of track, and it would be indistinguishable from a good one.

### The three sum to GT7's lap time exactly

`t_ms` is measured from the lap's first captured frame, which is the first
packet after the crossing rather than the crossing itself. So S1 carries that
offset (at most one frame, 16.6 ms at 60 Hz) and S3 is taken as
`lap_time_ms - t(S2)` rather than as the frames' own span. The three then
reconcile with the only authoritative time in the system, which is the one on
the rack beside them.

### ...which is why the two clocks have to be shown to share an origin first

That last step mixes the frame clock with GT7's, and on an **out-lap they do
not describe the same thing at all**. The frames start when the car is still
sitting in the box; GT7's lap time starts at the line. Measured across the
archive, an out-lap's frames span a median 1.34x its stated lap time and up to
8.8x, while the distance channel still integrates to within the circuit's
tolerance - so every length check passes and `lap_time_ms - t(S2)` returns a
confidently wrong S3. It read 5.58 s on a 95 s lap.

So the span is checked against the stated time before anything is cut, and the
gate is placed in **measured gaps rather than between populations**. Over the
733 stored laps the clean cluster is 0.990-1.005 - 563 of them - and above it
there is nothing at all until 1.050. Below it the laps thin out rather than
stop: 0.9895, 0.9838, 0.9793, 0.9655, then a real gap down to 0.5593.

**Why the lower bound is 1% and not the 5% the distribution would allow.**
`marks` starts at 0, so it assumes the first captured frame IS the crossing.
Where frames are missing from the START of a lap that assumption is wrong by
the whole missing interval, every crossing is read early, and **the entire
deficit lands inside S1** - understated by the offset, with S3 absorbing it
back so the three still sum to the lap time and nothing looks wrong. At 0.95
that is up to 5.5 s of a 110 s lap, roughly 15% of a sector, and it is
indistinguishable from driving.

A mid-lap dropout is harmless by contrast: `t_ms` comes off the packet counter
and stays a true clock across a gap, so the crossings are still read at the
right moments. It is specifically the missing PREFIX that corrupts a sector,
and the span ratio is the only thing that sees it.

The cost of the tighter bound is small and known: seven of the 555 laps in the
archive sat between 0.9655 and 0.9895 and now carry no sectors instead of a
silently wrong S1. Two of them differ by 1.9 s in S1 while agreeing to 60 ms
in S2, which is the signature of exactly this fault.

It refuses 87 of 91 out-laps, and the four it admits are ones whose clocks
genuinely do agree - which is the point, because the gate is about the clocks
and not about the flag.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.analysis.distance import CIRCUIT_TOLERANCE, teleports

SOURCE_TIMING_LINE = "timing-line"
SOURCE_LANDMARK = "landmark"
SOURCE_THIRDS = "thirds"

# How each provenance reads on a screen. The words matter: "thirds" has to say
# plainly that nobody measured this boundary, or a driver reads a sector split
# as if it were the one on a timing sheet. One table for the rack and the
# driver board, so the two cannot describe the same lines differently.
CUT_WORDS = {
    SOURCE_TIMING_LINE: "at the circuit's timing lines",
    SOURCE_LANDMARK: "at the circuit's landmarks",
    SOURCE_THIRDS: "thirds of the lap - not GT7's",
}


def cut_words(stamp: str | None) -> str | None:
    """`<circuit>:<source>:<lines>` (see `SectorModel.stamp`) as words."""
    if not stamp:
        return None
    parts = stamp.split(":")
    source = parts[1] if len(parts) > 2 else ""
    return CUT_WORDS.get(source, source or None)

# Three, everywhere. A 90-140 s lap gives 30-45 s a sector, which is coarse but
# sits far clear of the corner noise floor that put per-corner coaching out of
# reach: a corner is 3-4x noisier in relative terms than a whole lap on this
# driver's own 307-lap sample, and a third of a lap is much nearer a whole lap
# than a corner.
SECTORS = 3

# How far a snapped third may travel to reach a corner edge, as a fraction of
# the lap. Beyond this the nearest corner is not near, and the honest boundary
# is the arithmetic one where it fell.
SNAP_REACH = 0.04

# How far the frames' own span may sit from GT7's lap time before the two are
# not measuring the same lap.
#
# **A principled bound, not a fitted one**, and it was 0.95 first. The frames
# have to cover the lap: 1% is a lap time's worth of rounding either way, and
# anything further means a stretch of the lap was never observed. The first
# version chose 0.95 because that number sat in an empty band of the observed
# distribution - true, but the wrong question. A lap missing 4% of its frames
# is not admissible merely because no other lap missed 3%.
SPAN_RATIO = (0.99, 1.01)


@dataclass(frozen=True)
class SectorModel:
    """Where this circuit's sector lines are, and where they came from."""
    circuit_key: str
    source: str
    lap_length_m: float
    # Distance from the start line, metres, one per boundary. Two of them for
    # three sectors.
    lines_m: tuple[float, ...]
    note: str | None = None

    @property
    def fractions(self) -> tuple[float, ...]:
        """The lines as fractions of the lap.

        Everything downstream works in fractions rather than metres, because a
        lap's own integrated distance is what the frames carry and it is a few
        tenths of a percent short of the circuit. Multiplying the fraction by
        the lap's own length is the same correction `distance.anchor` applies,
        without needing the scale factor in hand.
        """
        return tuple(line / self.lap_length_m for line in self.lines_m)

    def as_meta(self) -> dict:
        """What the export has to declare, mirroring `meta.cornerModel`."""
        return {
            "source": self.source,
            "circuit": self.circuit_key,
            "sectors": len(self.lines_m) + 1,
            "linesM": [round(line, 1) for line in self.lines_m],
            "note": self.note,
        }

    @property
    def stamp(self) -> str:
        """What gets stored beside a lap's sector times.

        A lap measured against boundaries that have since moved is stale, and
        the only way to know is to keep what it was measured against. Short,
        because it goes in a column on every lap.
        """
        lines = "/".join(f"{line:.0f}" for line in self.lines_m)
        return f"{self.circuit_key}:{self.source}:{lines}"


# **The catalogue.** Keyed by the same slug `analysis/resolve.circuit_key`
# builds, so this is a lookup and not a match. Metres from the start line, on
# the circuit's own length as `track_layouts` holds it.
#
# A circuit that is not here is not a gap in the data — it is a circuit whose
# real sector lines nobody has established, and it gets snapped thirds and says
# so on the screen. That is deliberately not the same claim, and the screen
# does not let them look alike.
SECTOR_LINES: dict[str, dict] = {
    # S1 is published: the boundary between sectors 1 and 2 sits 145 m before
    # Turn 5 (Les Combes). Our corner model opens the Les Combes braking zone
    # at 2,405 m, so the line is 2,260.
    #
    # S2 is published as 48 m before Turn 15 (Paul Frere), but Paul Frere is
    # not one of the eight speed minima the segmenter finds here — it takes
    # Stavelot (T14, our T7, ending 5,021 m) and then nothing until the Bus
    # Stop. So this one is placed just past Stavelot's exit rather than
    # measured off the published figure, and the pair is labelled `landmark`,
    # because a model is worth the weaker of its two boundaries.
    "circuit-de-spa-francorchamps-full-course": {
        "lines_m": (2260.0, 5100.0),
        "source": SOURCE_LANDMARK,
        "note": ("S1 from the published timing line, 145 m before Les Combes "
                 "(T5). S2 placed just past Stavelot's exit, near the "
                 "published 48 m before Paul Frere (T15) - a placement, not a "
                 "measured line."),
    },
    # Same road, same length in `track_layouts` (7,044 m); GT7's 24h layout
    # differs in the pits and the scenery, not in the lap.
    "circuit-de-spa-francorchamps-24h-layout": {
        "lines_m": (2260.0, 5100.0),
        "source": SOURCE_LANDMARK,
        "note": "As the full course - the 24h layout is the same road.",
    },
    # The racing sectors here are well established even without a metre
    # figure: S1 runs to the braking zone for the Variante della Roggia, S2
    # covers the Lesmos and ends at the exit of Ascari, S3 is Parabolica and
    # the pit straight. Our corner model opens Roggia at 2,097 m and closes
    # Ascari at 3,978 m.
    #
    # **Keyed by the layout slug**, which is what `resolve.circuit_key` returns
    # for an event - not by the corner model's `model_id`, which at Monza is
    # the bare `autodromo-nazionale-monza` and would never match.
    "autodromo-nazionale-monza-full-course": {
        "lines_m": (2097.0, 3978.0),
        "source": SOURCE_LANDMARK,
        "note": ("S1 ends on the brakes for Variante della Roggia, S2 at the "
                 "exit of Ascari - the corner model's own edges for the two, "
                 "rather than a rounded figure. Placed from the racing "
                 "sectors, not from a published timing line."),
    },
}


def _snapped(cut_m: float, corners, lap_length_m: float) -> float:
    """Move an arithmetic cut to the nearest corner edge, if one is near.

    Edges rather than apexes: a sector boundary belongs between corners, and
    the two places a corner is least busy are the metre before it starts and
    the metre after it ends.
    """
    if not corners:
        return cut_m
    reach = lap_length_m * SNAP_REACH
    edges = [edge for corner in corners
             for edge in (corner.start_m, corner.end_m)]
    nearest = min(edges, key=lambda edge: abs(edge - cut_m))
    return nearest if abs(nearest - cut_m) <= reach else cut_m


def model_for(circuit_key: str | None, lap_length_m: float | None,
              corner_model=None) -> SectorModel | None:
    """This circuit's sector model, or None where the lap cannot be cut.

    None when the circuit length is unknown: without it there is no axis to
    put a boundary on, and a boundary in the wrong place is worse than no
    sector times at all.
    """
    if not circuit_key or not lap_length_m or lap_length_m <= 0:
        return None

    entry = SECTOR_LINES.get(circuit_key)
    if entry is not None:
        return SectorModel(circuit_key=circuit_key,
                           source=entry["source"],
                           lap_length_m=lap_length_m,
                           lines_m=tuple(entry["lines_m"]),
                           note=entry.get("note"))

    corners = tuple(getattr(corner_model, "corners", ()) or ()) if corner_model \
        else ()
    even = tuple(lap_length_m * index / SECTORS for index in range(1, SECTORS))
    cuts = tuple(_snapped(cut, corners, lap_length_m) for cut in even)
    # A model whose boundaries do not increase is not a model.
    #
    # **This cannot fire at the current constants, and it stays anyway.** The
    # cuts start a third of a lap apart and each may move at most 4% of one, so
    # the most two can close on each other is 8% against a 33% gap. It becomes
    # reachable the moment either constant moves - more sectors, or a longer
    # reach - and the failure it would produce is a negative sector time
    # reaching the rack, which is precisely the class of well-formed wrong
    # answer this file exists to refuse. "Not reachable today" is not a
    # property anyone can keep.
    if cuts[0] <= 0 or any(b <= a for a, b in zip(cuts, cuts[1:])):
        cuts, note = even, "Equal thirds - the snapped cuts did not stay in order."
    elif corners:
        note = ("Equal thirds, each moved to the nearest edge of the corner "
                "model so a boundary does not fall inside a corner.")
    else:
        note = "Equal thirds - no corner model for this circuit to snap to."
    return SectorModel(circuit_key=circuit_key, source=SOURCE_THIRDS,
                       lap_length_m=lap_length_m, lines_m=cuts, note=note)


def _crossings(distances: list, times: list, targets: list) -> list | None:
    """The frame clock at each target distance, or None if any is unreachable.

    Linear between the two frames either side, which at 60 Hz is a step of
    1.4 m at 300 km/h - so the interpolation is doing very little, and doing it
    costs nothing against reading the nearer frame.
    """
    found: list[int] = []
    index = 0
    for target in targets:
        while index < len(distances) - 1:
            here, ahead = distances[index], distances[index + 1]
            if here is None or ahead is None or ahead < target:
                index += 1
                continue
            break
        else:
            return None
        here, ahead = distances[index], distances[index + 1]
        t_here, t_ahead = times[index], times[index + 1]
        if None in (here, ahead, t_here, t_ahead):
            return None
        span = ahead - here
        fraction = 0.0 if span <= 0 else (target - here) / span
        found.append(int(round(t_here + fraction * (t_ahead - t_here))))
    return found


@dataclass(frozen=True)
class Sectors:
    """One lap cut into three, or the reason it was not."""
    times_ms: tuple = (None,) * SECTORS
    stamp: str | None = None
    refused: str | None = None
    # **The number that admitted this lap**, so the accept can log it. Rule 10
    # is explicit that logging only the refusals is what made the tyre-gauge
    # ratchet invisible for a whole race: the bar has to appear in the log on
    # the laps it lets through, not only on the ones it turns away.
    span_ratio: float | None = None

    @property
    def measured(self) -> bool:
        return all(value is not None for value in self.times_ms)


def _refused(reason: str) -> Sectors:
    return Sectors(refused=reason)


def read(frames, lap_time_ms: int, model: SectorModel | None) -> Sectors:
    """Cut one lap into sectors, or refuse it and say why.

    `frames` are decoded frames in order; `lap_time_ms` is GT7's own time for
    the lap, which is what S3 is taken back from.
    """
    if model is None:
        return _refused("no sector model for this circuit")
    if not frames:
        return _refused("no frames captured for this lap")
    if lap_time_ms <= 0:
        return _refused("the lap carries no time")

    jumped = teleports(frames)
    if jumped.happened:
        return _refused(jumped.describe())

    # **Before anything is cut, show that the two clocks share an origin.**
    # An out-lap's frames begin in the pit box and GT7's lap time begins at
    # the line, so `lap_time_ms - t(S2)` would be a difference between two
    # different zeros. The whole lap is refused rather than S3 alone: if the
    # origins differ then S1 is measured from the wrong end too.
    span_ms = frames[-1].get("t_ms")
    if span_ms is None:
        return _refused("this lap has no frame clock")
    ratio = span_ms / lap_time_ms
    if not SPAN_RATIO[0] <= ratio <= SPAN_RATIO[1]:
        return _refused(
            f"{span_ms / 1000:.1f} s of frames against a {lap_time_ms / 1000:.1f} s "
            "lap - the frame clock and GT7's do not start in the same place")

    distances = [frame.get("lap_distance_m") for frame in frames]
    measured = [value for value in distances if value is not None]
    if not measured:
        return _refused("this lap has no distance channel")
    length = max(measured)
    if abs(length - model.lap_length_m) > model.lap_length_m * CIRCUIT_TOLERANCE:
        return _refused(
            f"integrated to {length:.0f} m against a "
            f"{model.lap_length_m:.0f} m circuit, so the lines are elsewhere")

    # Against the lap's own length, not the circuit's: the same correction
    # `distance.anchor` makes, expressed as a fraction so no scale factor has
    # to be carried around.
    targets = [fraction * length for fraction in model.fractions]
    times = [frame.get("t_ms") for frame in frames]
    crossed = _crossings(distances, times, targets)
    if crossed is None:
        return _refused("the distance channel does not reach every line")

    marks = [0, *crossed, lap_time_ms]
    times_ms = tuple(after - before for before, after in zip(marks, marks[1:]))
    if any(value <= 0 for value in times_ms):
        # A sector of zero or negative length is a clock and a distance axis
        # disagreeing. Rule 9: that is a reading whose reference is wrong, not
        # a sector that took no time.
        return _refused("the lap clock and the distance axis disagree")
    return Sectors(times_ms=times_ms, stamp=model.stamp, span_ratio=ratio)


def read_rows(rows, field_names, lap_time_ms: int,
              model: SectorModel | None) -> Sectors:
    """`read`, from the recorder's column-array rows.

    Taken at the crossing while the rows are still uncompressed, for the same
    reason `incidents.read_rows` is: the rack asks this question of every lap
    on every redraw, and the answer must not cost a 400 KB decode a row.
    """
    if not rows:
        return _refused("no frames captured for this lap")
    index = {name: position for position, name in enumerate(field_names)}
    wanted = ("t_ms", "lap_distance_m", "pos_x", "pos_y", "pos_z")
    return read(
        [{name: row[index[name]] for name in wanted if name in index}
         for row in rows],
        lap_time_ms, model)
