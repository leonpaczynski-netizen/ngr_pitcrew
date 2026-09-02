"""A rival's lap times, his degradation, and who is responsible for a gap.

### His lap time is our lap time plus what the gap did

Sampled at the same point of the lap each time - start/finish - the identity is
exact:

    t_ahead(L)  = t_us(L) + [ g_ahead(L)  - g_ahead(L-1)  ]
    t_behind(L) = t_us(L) - [ g_behind(L) - g_behind(L-1) ]

**Sampled at the same POINT, not at whatever reading was nearest the lap
trigger.** A gap read 200 ms after the line is a gap over a different stretch
of track, and the error goes straight into the lap time. The two 2 Hz samples
straddling the crossing are interpolated instead.

What survives is about a quarter of a second of quantisation error per lap,
uncorrelated lap to lap, so a three-lap mean brings it near 0.15 s. **That is
accurate enough to decide strategy and not accurate enough to read out.** A
derived rival lap time is never surfaced as his lap time; only the trend is.

### Attribution, because a closing gap has two causes

They demand opposite instructions and the aggregate hides which one it is:

    our contribution   = our reference pace  - our actual pace
    their contribution = their actual pace   - their reference pace

"Catching at 0.4 a lap, 0.3 of it his tyres" means hold station and save fuel.
"Catching at 0.4, all of it you in sector 3" means keep pushing. Reporting only
the 0.4 is the most common way a strategy tool hands a driver a correct number
and the wrong idea, so nothing here returns a trend without one.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from pitcrew.analysis.wear import trend_slope
from pitcrew.race.ledger import MIN_DEG_LAPS, Pace

# Quantisation on one derived lap time, from sampling a gap at 2 Hz at each end
# of the lap. Two samples, each good to about half a sample interval.
LAP_TIME_ERROR_S = 0.25

# Laps pooled before a rival lap time is worth anything. Three brings the
# quantisation to about 0.15 s.
SMOOTH_LAPS = 3


@dataclass
class RivalPace:
    """One rival's derived lap times, and the deg fit over them.

    Keyed by lap and cleared whenever the slot changes hands, because a series
    across two cars describes neither. `excluded` records the laps thrown out
    and why, so a thin fit can say what it lost rather than just being thin.
    """
    subject: object = None
    lap_times_s: dict[int, float] = field(default_factory=dict)
    excluded: dict[int, str] = field(default_factory=dict)
    stint_started_on: int | None = None

    def new_session(self) -> None:
        """CLAUDE.md rule 11."""
        self.subject = None
        self.lap_times_s = {}
        self.excluded = {}
        self.stint_started_on = None

    def note_lap(self, lap: int | None, ours_s: float | None,
                 gap_now_s: float | None, gap_last_s: float | None, *,
                 ahead: bool = True, subject: object = None,
                 exclude: str | None = None) -> float | None:
        """File one derived lap time, or record why it was excluded.

        `exclude` is the caller's reason - a pit event, a slot change or a
        rejected gap sample anywhere inside the lap. A lap containing any of
        those is not a lap of his pace and must not reach the fit.
        """
        if subject is not None and subject != self.subject:
            if self.subject is not None:
                self.lap_times_s = {}
                self.excluded = {}
                self.stint_started_on = None
            self.subject = subject
        if lap is None:
            return None
        if exclude:
            self.excluded[int(lap)] = exclude
            return None
        if ours_s is None or gap_now_s is None or gap_last_s is None:
            self.excluded[int(lap)] = "a gap or our own lap time was not read"
            return None
        moved = gap_now_s - gap_last_s
        theirs = ours_s + moved if ahead else ours_s - moved
        if theirs <= 0:
            self.excluded[int(lap)] = "the arithmetic gave a negative lap time"
            return None
        self.lap_times_s[int(lap)] = theirs
        return theirs

    def note_stop(self, lap: int | None) -> None:
        """He pitted: the stint restarts and the deg fit begins again."""
        if lap is None:
            return
        self.excluded[int(lap)] = "he pitted on this lap"
        self.stint_started_on = int(lap)

    # --- reading it back --------------------------------------------------

    def stint_lap(self, lap: int | None) -> int | None:
        """How deep into his current set he is on this lap."""
        if lap is None or self.stint_started_on is None:
            return None
        return max(0, int(lap) - self.stint_started_on)

    def smoothed_s(self, lap: int | None,
                   over: int = SMOOTH_LAPS) -> float | None:
        """His lap time, pooled over the last few laps.

        **Internal.** A rival lap time carries about 0.25 s of quantisation and
        pooling three brings it to 0.15; neither is good enough to read out as
        his lap time, and nothing here should be surfaced as one.
        """
        laps = [k for k in sorted(self.lap_times_s) if lap is None or k <= lap]
        laps = laps[-over:]
        if not laps:
            return None
        return sum(self.lap_times_s[k] for k in laps) / len(laps)

    def deg_s_per_lap(self) -> tuple[float | None, int]:
        """`(seconds a lap he is losing, laps behind it)`, over this stint.

        Theil-Sen, like every other slope in this app: one bad derived lap
        would take a least-squares fit and its sign with it, and derived laps
        are exactly where a bad one comes from.
        """
        laps = sorted(k for k in self.lap_times_s
                      if self.stint_started_on is None
                      or k >= self.stint_started_on)
        if len(laps) < 3:
            return None, len(laps)
        points = [(k, int(self.lap_times_s[k] * 1000)) for k in laps]
        slope = trend_slope(points)
        if slope is None:
            return None, len(laps)
        return slope / 1000.0, len(laps)

    def as_pace(self, lap: int | None = None,
                warmup_s: float = 0.0) -> Pace | None:
        """A `ledger.Pace` for this rival, or `None` if the fit is too thin.

        The gate is `ledger.MIN_DEG_LAPS`, and it is deliberately the same
        number: a ledger that refuses a thin fit and a pace model that hands
        one over would be two rules about one question.
        """
        base = self.smoothed_s(lap)
        rate, laps = self.deg_s_per_lap()
        if base is None or rate is None or laps < MIN_DEG_LAPS:
            return None
        return Pace(base_s=base, deg_s_per_lap=rate, warmup_s=warmup_s,
                    laps_of_evidence=laps,
                    error_s=LAP_TIME_ERROR_S / max(1, SMOOTH_LAPS) ** 0.5,
                    stint_lap=self.stint_lap(lap) or 0)


@dataclass(frozen=True)
class Attribution:
    """Who is responsible for a gap moving, in seconds a lap each.

    `ours` positive means we are quicker than our own reference; `theirs`
    positive means they are slower than theirs. They sum to the trend, and the
    trend is never reported without them.
    """
    total_s_per_lap: float
    ours_s_per_lap: float | None
    theirs_s_per_lap: float | None

    @property
    def known(self) -> bool:
        return self.ours_s_per_lap is not None and self.theirs_s_per_lap is not None

    @property
    def mostly_theirs(self) -> bool:
        if not self.known:
            return False
        return abs(self.theirs_s_per_lap) > abs(self.ours_s_per_lap)

    def why(self) -> str:
        """One clause the driver can act on, or an empty string."""
        if not self.known:
            return ""
        if self.mostly_theirs:
            return f"{abs(self.theirs_s_per_lap):.1f} of it is his tyres"
        return f"{abs(self.ours_s_per_lap):.1f} of it is you"


def attribute(total_s_per_lap: float | None,
              ours_now_s: float | None, ours_reference_s: float | None,
              theirs_now_s: float | None, theirs_reference_s: float | None
              ) -> Attribution | None:
    """Split a closing rate into our part and theirs.

    `None` where there is no trend at all. Where a reference is missing the
    `Attribution` still comes back, with that side unknown - so a caller can
    tell "we do not know who is responsible" from "it is evenly split", which
    are very different things to say under a helmet.
    """
    if total_s_per_lap is None:
        return None
    ours = (None if ours_now_s is None or ours_reference_s is None
            else ours_reference_s - ours_now_s)
    theirs = (None if theirs_now_s is None or theirs_reference_s is None
              else theirs_now_s - theirs_reference_s)
    return Attribution(total_s_per_lap=total_s_per_lap,
                       ours_s_per_lap=ours, theirs_s_per_lap=theirs)
