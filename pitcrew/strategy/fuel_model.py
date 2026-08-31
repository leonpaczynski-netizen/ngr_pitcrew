"""Fuel burn as a function of what is in the tank, not a single number.

**A full-tank lap and a half-tank lap are not the same lap, and the plan has
always costed them as though they were.** `RaceInputs.fuel_per_lap_l` is one
scalar median; so is George's `expected_fuel_per_lap_l`. Sizing a fill off it
over-fuels a stint that starts light and under-fuels one that starts heavy, and
at the measured 1.0009 L/s every surplus litre is a second standing still.

### The measurement

Spa race, 31 Aug 2026, session 112, Huracan GT3, v1.71, 17 green laps:

    burn = base + LOAD_SLOPE_L_PER_L * (litres aboard)

    fuel aboard   +0.00610 L per litre   SE 0.00134   t +4.54   CI [0.0035, 0.0087]
    upshift rpm   +1.9406 L per 1000 rpm SE 0.2099    t +9.25

Residual scatter falls from 0.289 L to 0.112 L once rpm is in the fit. **Over a
100 L range that is 0.61 L/lap between a full tank and an empty one** - and on a
ten-lap stint it is several litres, which is several seconds in the pit lane.

**⚠️ It is invisible unless upshift rpm is held.** Fitted on load alone the
slope is +0.00058, t +0.19 - nothing - because the one lap of that race he did
not short-shift sits at the lowest fuel load and cancels the effect exactly.
Anyone re-fitting this must hold rpm or they will conclude there is no effect.
The driver reported it from the seat before any model showed it.

### What this module does NOT do

**It does not predict burn from scratch.** A first solver built directly on the
fit above demanded 80.3 L for a stint the driver actually completed on 75.27 L;
it over-predicts at low load by about 0.18 L/lap. The fit is good for the
*difference* between two loads and not for the absolute level, so everything
here works by **correcting a measured base burn to a different load**, never by
generating one. `base_l` always comes from observed laps.

That is also why the slope defaults to zero at every call site: with no measured
base and no reference load, this module returns exactly what the old scalar
arithmetic returned.
"""
from __future__ import annotations

# Measured; see the module docstring for the fit and its confidence interval.
# Spa, Huracan GT3, v1.71, 31 Aug 2026, 17 green laps.
LOAD_SLOPE_L_PER_L = 0.00610

# The buffer a fill is sized to leave at the flag. **One litre, not one lap.**
# `brain/driver.md`: he will not carry a spare lap in a lap race, and at
# 1.0009 L/s (measured, same race) a litre is a second standing still. The Spa
# race finished on 2.91 L, which was 2.8 L more than it needed once the
# un-short-shifted last lap is accounted for - 2.8 seconds.
DEFAULT_BUFFER_L = 1.0


def burn_at_load_l(base_l: float, aboard_l: float, *,
                   reference_load_l: float | None,
                   slope: float = LOAD_SLOPE_L_PER_L) -> float:
    """`base_l` corrected from the load it was measured at to `aboard_l`.

    **`reference_load_l` is the mean fuel aboard across the laps that produced
    `base_l`.** Without it the correction has no origin and would double-count:
    a median burn already contains whatever load its own laps were carrying.
    None means "unknown", and then the base is returned untouched - which is
    the old behaviour, exactly.
    """
    if reference_load_l is None or not slope:
        return base_l
    return base_l + slope * (aboard_l - reference_load_l)


def stint_burn_l(base_l: float, laps: int, start_load_l: float | None, *,
                 reference_load_l: float | None,
                 slope: float = LOAD_SLOPE_L_PER_L) -> float:
    """Litres burned over `laps`, starting the stint with `start_load_l` aboard.

    Integrated lap by lap because the car lightens as it goes: each lap is
    costed at the load it actually carries, taken at the **middle** of the lap
    rather than the start, which is where the mean load of that lap sits.

    Falls back to `laps * base_l` when the load is unknown or the slope is off.
    """
    if start_load_l is None or reference_load_l is None or not slope:
        return laps * base_l
    aboard = float(start_load_l)
    total = 0.0
    for _ in range(int(laps)):
        # One pass to find the lap's own mean load, then cost it there.
        rough = burn_at_load_l(base_l, aboard, reference_load_l=reference_load_l,
                               slope=slope)
        used = burn_at_load_l(base_l, aboard - rough / 2.0,
                              reference_load_l=reference_load_l, slope=slope)
        total += used
        aboard -= used
    return total


def fill_for_l(base_l: float, laps: int, *, reference_load_l: float | None,
               buffer_l: float = DEFAULT_BUFFER_L,
               slope: float = LOAD_SLOPE_L_PER_L,
               capacity_l: float | None = None) -> float:
    """The fill that runs `laps` and leaves `buffer_l` at the end.

    **Self-referential, and that is the whole point**: the fuel you take is its
    own weight, so taking less makes the stint burn less and lets you take less
    again. Solved by bisection rather than algebra because `stint_burn_l`
    integrates lap by lap.

    **Not clamped to the tank.** `capacity_l` is accepted only so the search can
    be bounded sensibly; a requirement larger than the tank is returned honestly
    so the caller can refuse the plan. Clamping once made an impossible plan
    look cheap - see `model.build_plan`.
    """
    flat = laps * base_l + buffer_l
    if reference_load_l is None or not slope:
        return flat
    lo, hi = 0.0, max(flat * 2.0, (capacity_l or 0.0) * 2.0, 1.0)
    for _ in range(80):
        mid = (lo + hi) / 2.0
        left = mid - stint_burn_l(base_l, laps, mid,
                                  reference_load_l=reference_load_l, slope=slope)
        if left > buffer_l:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


def fit_load_slope(samples):
    """Least squares of burn on (fuel aboard, upshift rpm). Offline use.

    `samples` is an iterable of `(fuel_used_l, mean_aboard_l, upshift_rpm)`.
    Returns `(slope_per_litre, per_1000_rpm, base, n)` or None below four
    samples - two predictors and an intercept need more than three points to
    say anything at all.

    **The rpm term is not optional.** It is here because leaving it out is what
    makes the load effect vanish: on the race this was fitted from, load alone
    returns t +0.19 and load-with-rpm returns t +4.54 on the same 17 laps.
    """
    rows = [(float(u), float(a), float(r) / 1000.0)
            for u, a, r in samples if u and a is not None and r]
    n = len(rows)
    if n < 4:
        return None
    # Normal equations for y = b0 + b1*aboard + b2*krpm, solved by elimination.
    design = [[1.0, a, k] for _, a, k in rows]
    y = [u for u, _, _ in rows]
    size = 3
    ata = [[sum(design[i][a] * design[i][b] for i in range(n))
            for b in range(size)] for a in range(size)]
    aty = [sum(design[i][a] * y[i] for i in range(n)) for a in range(size)]
    matrix = [ata[i][:] + [aty[i]] for i in range(size)]
    for col in range(size):
        pivot = max(range(col, size), key=lambda r_: abs(matrix[r_][col]))
        matrix[col], matrix[pivot] = matrix[pivot], matrix[col]
        if not matrix[col][col]:
            return None
        for row in range(size):
            if row != col:
                factor = matrix[row][col] / matrix[col][col]
                for c in range(col, size + 1):
                    matrix[row][c] -= factor * matrix[col][c]
    beta = [matrix[i][size] / matrix[i][i] for i in range(size)]
    return beta[1], beta[2], beta[0], n
