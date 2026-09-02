"""What a rival has aboard, from three estimators that check each other.

### The premise this section had to be rebuilt on

The spec's input contract lists **opponent fuel level at 2 Hz**. It is not
available, and the measurement is unambiguous: GT7 draws the pit columns - the
flag, the compound disc and the fuel figure - only for a car that is standing
in the pit lane at that instant. Of 94 clean frames after CruisingChaos filled
from 10 L to 89, exactly one carried columns, and it belonged to A.Maidment,
who was in the box at that moment. A driver who stopped five minutes ago looks
identical on screen to one who has never stopped.

So there is no per-lap fuel series for a rival, and Estimator A as written -
EWMA of `F(L-1) - F(L)` over laps - has no input. What exists instead is fuel
at the ENTRY and EXIT of each stop, which supports three estimators of its own:

* **A. Burn between two observed stops.** He left stop `k` with `x` and arrived
  at stop `k+1` with `y`, `n` laps later: that is `(x - y) / n`, and it needs no
  assumption at all. The strongest of the three and it needs two stops.
* **A'. Burn over the first stint**, from what he is assumed to have started
  with. One stop is enough, and the assumption is stored with the observation
  rather than applied and forgotten - see `race/profile.py`.
* **B. Fuel added at the stop**, straight from the two readings.

**C. Stationary time as a proxy** is the one that survives when the fuel OCR
fails but the entry and exit events land. Refuelling and tyres run concurrently,
so the stop is as long as whichever is longer - and that is why it yields a
BOUND rather than a figure whenever the stop was tyre-limited.

### Corroboration, concretely

A pit event, a fuel reading and a standing time that agree are truth. Two of
three are a hypothesis. Where they disagree by more than the calibration
uncertainty this **widens the window** rather than picking a winner, because
picking a winner is how a tool with three instruments reports the confidence of
one.
"""
from __future__ import annotations

from dataclasses import dataclass

# What a fill can be known to. Below this the estimators are agreeing.
AGREEMENT_L = 4.0

# A stop this close to the tyre-only time took no meaningful fuel that can be
# separated from the tyre change - see `Calibration.tyres_only_s`.
TYRE_LIMITED_SLACK_S = 3.0

POINT, LOWER_BOUND, UNKNOWN = "point", "lower-bound", "unknown"


@dataclass(frozen=True)
class Calibration:
    """The two constants a stop is priced with, from our OWN stops.

    Ours are fully observed - the tank telemetry gives litres to the decilitre
    and the clock gives the standing time - so they are measured here and
    applied to rivals, rather than assumed for both. Per track and car, because
    the pit lane is a track constant and the fill rate is not obviously one.
    """
    refuel_rate_lps: float | None = None
    tyres_only_s: float | None = None
    stops_behind_it: int = 0
    source: str = "none"

    @property
    def known(self) -> bool:
        return bool(self.refuel_rate_lps and self.tyres_only_s is not None)


@dataclass(frozen=True)
class Litres:
    """A fuel quantity that knows how well it is known.

    `kind` is `point`, `lower-bound` or `unknown`. A tyre-limited stop produces
    a lower bound and must never be flattened into a number: the fill was
    shorter than the tyre change, so all that is known is that it was at most
    what the tyre change covered.
    """
    low: float | None = None
    high: float | None = None
    kind: str = UNKNOWN
    why: str = ""

    @property
    def known(self) -> bool:
        return self.kind != UNKNOWN

    @property
    def point(self) -> float | None:
        """The single number, or `None` where there is not one."""
        if self.kind != POINT or self.low is None or self.high is None:
            return None
        return (self.low + self.high) / 2.0

    @property
    def width(self) -> float | None:
        if self.low is None or self.high is None:
            return None
        return self.high - self.low


def calibrate(stops) -> Calibration:
    """`r` and `t_tyres` from our own observed stops.

    `stops` is an iterable of `(litres_taken, standing_s, tyres_changed)`.
    Needs at least one fuel-and-tyres stop for the rate; `t_tyres` comes from a
    tyres-only stop where one exists, and otherwise from the intercept.
    """
    fuelled = [(litres, standing) for litres, standing, _ in stops
               if litres and litres > 0 and standing and standing > 0]
    tyres_only = [standing for litres, standing, changed in stops
                  if changed and (not litres or litres <= 0)
                  and standing and standing > 0]
    if not fuelled:
        return Calibration(source="no fuelled stop observed")
    tyre_time = (sum(tyres_only) / len(tyres_only)) if tyres_only else None
    if tyre_time is None and len(fuelled) >= 2:
        # Two stops of different fills give the line: the intercept is the part
        # of the stop that is not the hose.
        (l1, s1), (l2, s2) = fuelled[0], fuelled[-1]
        if abs(l2 - l1) > 1e-6:
            rate = (l2 - l1) / (s2 - s1) if s2 != s1 else None
            if rate and rate > 0:
                return Calibration(refuel_rate_lps=rate,
                                   tyres_only_s=max(0.0, s1 - l1 / rate),
                                   stops_behind_it=len(fuelled),
                                   source="two fills, rate and intercept")
    if tyre_time is None:
        return Calibration(source="one fill only, cannot separate the hose "
                                  "from the tyre change")
    rates = [litres / (standing - tyre_time) for litres, standing in fuelled
             if standing - tyre_time > 0]
    if not rates:
        return Calibration(source="every fill was shorter than a tyre change")
    return Calibration(refuel_rate_lps=sum(rates) / len(rates),
                       tyres_only_s=tyre_time,
                       stops_behind_it=len(fuelled),
                       source="measured against a tyres-only stop")


# --- the estimators --------------------------------------------------------

def burn_between_stops(left_with_l: float | None, arrived_with_l: float | None,
                       laps_between: int | None) -> float | None:
    """Litres a lap between two observed stops. No assumption at all.

    `None` where a reading is missing or the arithmetic goes backwards - a car
    that arrived with more than it left with is a misread, not a car that made
    fuel. CLAUDE.md rule 9.
    """
    if (left_with_l is None or arrived_with_l is None
            or not laps_between or laps_between <= 0):
        return None
    used = left_with_l - arrived_with_l
    if used <= 0:
        return None
    return used / laps_between


def fill_from_readings(entry_l: float | None,
                       exit_l: float | None) -> Litres:
    """Estimator B: what the two fuel figures say was added."""
    if entry_l is None or exit_l is None:
        return Litres(why="a fuel figure was not read")
    added = exit_l - entry_l
    if added < 0:
        return Litres(why="the exit reading was lower than the entry one")
    return Litres(low=added, high=added, kind=POINT, why="read off the screen")


def fill_from_standing(standing_s: float | None,
                       cal: Calibration) -> Litres:
    """Estimator C: what the stop's LENGTH says was added.

    Refuelling and the tyre change run concurrently, so the stop is as long as
    whichever takes longer. When the standing time is no longer than a tyre
    change the stop was tyre-limited and the fill is unbounded below: all that
    is known is a ceiling, so a LOWER BOUND of zero with that ceiling is
    returned rather than a fabricated point.
    """
    if standing_s is None or not cal.known:
        return Litres(why="no standing time, or the pit lane is not calibrated")
    over = standing_s - cal.tyres_only_s
    ceiling = max(0.0, over) * cal.refuel_rate_lps
    if over <= TYRE_LIMITED_SLACK_S:
        return Litres(low=0.0,
                      high=max(0.0, TYRE_LIMITED_SLACK_S
                               * cal.refuel_rate_lps),
                      kind=LOWER_BOUND,
                      why="the stop was no longer than a tyre change, so the "
                          "fill is bounded rather than measured")
    return Litres(low=ceiling, high=ceiling, kind=POINT,
                  why="from the standing time at the measured fill rate")


def reconcile(*estimates: Litres) -> Litres:
    """Combine estimators, WIDENING where they disagree.

    Two that agree inside `AGREEMENT_L` are one answer with the tighter bound.
    Two that do not are a hypothesis, and the honest output is the span of
    both - not the one that happens to be listed first.
    """
    known = [e for e in estimates if e.known and e.low is not None]
    if not known:
        reasons = "; ".join(e.why for e in estimates if e.why)
        return Litres(why=reasons or "nothing was observed")
    if len(known) == 1:
        return known[0]
    points = [e.point for e in known if e.point is not None]
    low = min(e.low for e in known)
    high = max(e.high for e in known if e.high is not None)
    if len(points) >= 2 and max(points) - min(points) > AGREEMENT_L:
        return Litres(low=low, high=high, kind=LOWER_BOUND,
                      why=(f"the estimators disagree by "
                           f"{max(points) - min(points):.0f} L, so the window "
                           f"is widened rather than one of them chosen"))
    if any(e.kind == LOWER_BOUND for e in known) and not points:
        return Litres(low=low, high=high, kind=LOWER_BOUND,
                      why="every estimate was a bound")
    return Litres(low=low, high=high,
                  kind=POINT if low == high else LOWER_BOUND,
                  why="the estimators agree")


def forced_stop_lap(aboard_l: Litres | float | None,
                    burn_per_lap_l: float | None,
                    lap_now: int | None) -> tuple[int | None, int | None]:
    """`(earliest, latest)` lap he must stop by, or `(None, None)`.

    A range, because what he has aboard is a range. The earliest comes from the
    bottom of the fuel window and the latest from the top, and a caller that
    wants one number should be told it does not have one.
    """
    if burn_per_lap_l is None or burn_per_lap_l <= 0 or lap_now is None:
        return None, None
    if isinstance(aboard_l, Litres):
        if not aboard_l.known:
            return None, None
        low, high = aboard_l.low, aboard_l.high
    else:
        if aboard_l is None:
            return None, None
        low = high = float(aboard_l)
    if low is None or high is None:
        return None, None
    return (lap_now + int(low / burn_per_lap_l),
            lap_now + int(high / burn_per_lap_l))
