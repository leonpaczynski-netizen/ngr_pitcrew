"""Where round the lap we gain and lose on a rival.

At 2 Hz over a 90-140 s lap the gap is read 180-280 times. That is ample for
sector resolution and marginal for corner resolution, so this bins the lap into
twelve and says nothing about corners. **The corner claim is refused on
measured grounds, not caution**: a corner is 3-4x noisier in relative terms
than a whole lap on this driver's own 307-lap sample, which is why per-corner
input coaching is already off the table in CLAUDE.md.

### Ego track distance is integrated, not broadcast

GT7 has no lap-distance channel; `telemetry/recorder.py` integrates one from
speed at 60 Hz, and `race/qualifying.py` does the same thing live. So binning
by distance is available - it was never blocked - but it inherits that
integration's known fault: **about 7% of laps teleport**, and speed integration
cannot see a teleport at all. A lap whose integrated length disagrees with the
circuit is therefore thrown out rather than binned, because its bin boundaries
are somewhere else on the road.

### The gap you read is not where they were

The interval at your position describes their pace roughly one gap-length of
track EARLIER. Under about two seconds that is a fraction of a bin and can be
ignored at this resolution. Above `OFFSET_FROM_S` the samples are attributed
backwards by `g * v / bin_length` bins, and above `MAX_USEFUL_GAP_S` the whole
feature switches off - at half a lap of separation the correction is larger
than the thing being corrected.

### Nothing reaches the driver inside the noise

A bin is only surfaced when its mean exceeds twice its own standard error.
Below that it is noise, and reporting noise is how a driver learns to distrust
the tool - which costs more than the finding was worth.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

# Twelve bins puts roughly 8-12 s of track in each at this driver's lap times.
DEFAULT_BINS = 12

# A lap whose integrated distance is this far from the circuit's own length did
# not measure the road. See `analysis/distance.py` - 7% of laps teleport and
# the integrator cannot see it.
LAP_LENGTH_TOLERANCE = 0.08

# Below this the offset between "where he is" and "where the gap describes" is
# a fraction of a bin. Above the ceiling the correction exceeds the signal.
OFFSET_FROM_S, MAX_USEFUL_GAP_S = 2.0, 25.0

# Laps of evidence before a bin is worth a standard error at all.
MIN_LAPS = 4


@dataclass(frozen=True)
class Bin:
    """One stretch of track, and what the gap did across it."""
    index: int
    from_m: float
    to_m: float
    mean_s: float
    standard_error_s: float
    laps: int

    @property
    def worth_saying(self) -> bool:
        """Twice its own standard error, or it is noise."""
        return (self.laps >= MIN_LAPS
                and abs(self.mean_s) > 2 * self.standard_error_s)

    @property
    def gaining(self) -> bool:
        """A shrinking gap is a gain. Same convention as everywhere else."""
        return self.mean_s < 0


@dataclass
class SectorMap:
    """Gap change per stretch of track, accumulated over laps.

    One instance per rival. `subject` clears it, for the same reason it clears
    everything else here: a stretch of track measured against two different
    cars describes neither.
    """
    circuit_length_m: float
    bins: int = DEFAULT_BINS
    subject: object = None
    # bin index -> the per-lap deltas seen in it
    seen: dict[int, list[float]] = field(default_factory=dict)
    # One dict per lap kept, bin index -> that lap's delta in it. `seen`
    # loses the lap alignment across bins (a bin with no sample on a lap is
    # simply absent), and the roll-up into sectors needs each lap whole.
    lap_sums: list[dict[int, float]] = field(default_factory=list)
    laps_used: int = 0
    laps_dropped: int = 0

    @property
    def bin_length_m(self) -> float:
        return self.circuit_length_m / self.bins

    def new_session(self) -> None:
        """CLAUDE.md rule 11."""
        self.seen = {}
        self.lap_sums = []
        self.subject = None
        self.laps_used = self.laps_dropped = 0

    def note_lap(self, samples, *, subject=None,
                 speed_ms: float | None = None) -> bool:
        """Fold one lap of `(track_m, gap_s)` readings in. Returns whether kept.

        `samples` must be one lap's worth in order. The lap is dropped whole
        when its span does not look like the circuit - a teleport moves the
        integrator without moving the car, and every bin boundary after it is
        in the wrong place.
        """
        if subject is not None and subject != self.subject:
            if self.subject is not None:
                self.seen = {}
                self.lap_sums = []
                self.laps_used = self.laps_dropped = 0
            self.subject = subject
        usable = [(m, g) for m, g in samples
                  if m is not None and g is not None]
        if len(usable) < self.bins:
            self.laps_dropped += 1
            return False
        span = usable[-1][0] - usable[0][0]
        if abs(span - self.circuit_length_m) > (
                LAP_LENGTH_TOLERANCE * self.circuit_length_m):
            # The integrator says this lap was not the length of the lap.
            self.laps_dropped += 1
            return False
        if usable[0][1] > MAX_USEFUL_GAP_S:
            self.laps_dropped += 1
            return False

        shift = self._offset_bins(usable[0][1], speed_ms)
        per_bin: dict[int, list[float]] = {}
        origin = usable[0][0]
        for (m0, g0), (m1, g1) in zip(usable, usable[1:]):
            # **A delta that straddles a bin line is shared by distance.**
            # Credited whole to the bin it started in, a 200 m reading
            # interval put up to 200 m of one sector's gain into its
            # neighbour - a third of a lap read a tenth low at Deep Forest
            # on the reconstruction of 7 Sep 2026.
            delta = g1 - g0
            span = m1 - m0
            if span <= 0:
                index = int((m0 - origin) / self.bin_length_m)
                index = max(0, min(self.bins - 1, index - shift))
                per_bin.setdefault(index, []).append(delta)
                continue
            first = int((m0 - origin) / self.bin_length_m)
            last = int((m1 - origin) / self.bin_length_m)
            for raw in range(first, last + 1):
                lo = max(m0, origin + raw * self.bin_length_m)
                hi = min(m1, origin + (raw + 1) * self.bin_length_m)
                if hi <= lo:
                    continue
                index = max(0, min(self.bins - 1, raw - shift))
                per_bin.setdefault(index, []).append(delta * (hi - lo) / span)
        sums = {index: sum(deltas) for index, deltas in per_bin.items()}
        for index, total in sums.items():
            self.seen.setdefault(index, []).append(total)
        self.lap_sums.append(sums)
        self.laps_used += 1
        return True

    def _offset_bins(self, gap_s: float, speed_ms: float | None) -> int:
        """How many bins back the reading actually describes.

        Zero under `OFFSET_FROM_S`, where it is a fraction of a bin anyway.
        """
        if gap_s < OFFSET_FROM_S or not speed_ms or speed_ms <= 0:
            return 0
        return int(round(gap_s * speed_ms / self.bin_length_m))

    # --- reading it back --------------------------------------------------

    def bin_at(self, index: int) -> Bin | None:
        deltas = self.seen.get(index)
        if not deltas:
            return None
        mean = sum(deltas) / len(deltas)
        spread = statistics.stdev(deltas) if len(deltas) > 1 else 0.0
        error = spread / (len(deltas) ** 0.5) if deltas else 0.0
        return Bin(index=index,
                   from_m=index * self.bin_length_m,
                   to_m=(index + 1) * self.bin_length_m,
                   mean_s=mean, standard_error_s=error, laps=len(deltas))

    def all_bins(self) -> list[Bin]:
        return [b for b in (self.bin_at(i) for i in range(self.bins))
                if b is not None]

    def sectors(self, cuts_m) -> list[Bin]:
        """The bins rolled up into the circuit's own sectors.

        `cuts_m` are the sector lines from the start, metres - the same two
        numbers the lap rows' sector times were cut at, so "faster through
        1 and 2" means the sectors the driver already sees on his rack. A
        bin belongs to the sector its centre falls in. Each sector's mean
        and standard error come from its per-lap sums, so a sector is
        judged on the same footing as a bin: `worth_saying` is twice its
        own standard error, over `MIN_LAPS` laps.
        """
        lines = [float(c) for c in (cuts_m or ())]
        edges = [0.0] + lines + [self.circuit_length_m]
        out = []
        for number in range(len(edges) - 1):
            lo, hi = edges[number], edges[number + 1]
            members = [i for i in range(self.bins)
                       if lo <= (i + 0.5) * self.bin_length_m < hi]
            per_lap = [sum(lap.get(i, 0.0) for i in members)
                       for lap in self.lap_sums
                       if any(i in lap for i in members)]
            if not per_lap:
                continue
            mean = sum(per_lap) / len(per_lap)
            spread = statistics.stdev(per_lap) if len(per_lap) > 1 else 0.0
            error = spread / (len(per_lap) ** 0.5)
            out.append(Bin(index=number, from_m=lo, to_m=hi, mean_s=mean,
                           standard_error_s=error, laps=len(per_lap)))
        return out

    def worth_saying(self, most: int = 2) -> list[Bin]:
        """The strongest bins past the standard-error gate, biggest first.

        Empty is the ordinary answer early in a race and is not a failure: four
        laps is the floor for a standard error to mean anything.
        """
        past = [b for b in self.all_bins() if b.worth_saying]
        past.sort(key=lambda b: -abs(b.mean_s))
        return past[:most]
