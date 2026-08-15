"""How hot each compound actually ran — and why that is all this can say.

GT7 gives per-wheel tyre **surface** temperature at 60 Hz. That figure is real
and is measured here per compound, per lap.

**What is not real is the window it used to be judged against.** `store/tyres.py`
carries a `cold_max` / `warming_max` / `optimal_max` / `hot_max` band per
compound, and this module used to compare the measured temperature to it and
emit a verdict — "RM never got into its window, so its pace deficit is
overstated and its stint length is flattered" — into every export, as a
finding, tagged as measurement.

The bands were never measured in GT7 and are not GT7's numbers. They are
real-world racing-slick figures, which live at 90–110 °C. Across 51 laps of
Monza on three compounds, **every lap of every compound ran between 68 °C and
78 °C**, and GT7 fits every fresh set at exactly 70.0 °C. Under those bands a
Racing Soft could never once reach its own window, so the verdict fired every
time and said something confident about nothing. Nobody has published GT7
windows: the question was asked on GTPlanet in April 2025 and went unanswered.

So this module now reports the temperature and stops there. `qualification()`
returns None until a window has been measured, and the band travels with
`windowMeasured: false` so nothing downstream mistakes decoration for a
finding.

**Measuring one is a driving job, not a coding job**: the same corner at
several times of day, achieved tyre temperature against lap time, and the
temperature at which lap time stops improving is the bottom of the window.

Surface temperature is not core temperature. GT7 exposes only the surface, and
it responds far faster than the carcass, so a mean over a lap is a reasonable
read of the working range while a single frame is not. Everything here is
averaged over whole laps for that reason.
"""
from __future__ import annotations

from statistics import mean

from pitcrew.analysis.session import LapInput, counted_laps
from pitcrew.store.tyres import get_by_code

CORNERS = ("fl", "fr", "rl", "rr")

BAND_COLD = "cold"
BAND_WARMING = "warming"
BAND_OPTIMAL = "optimal"
BAND_HOT = "hot"
BAND_OVERHEATING = "overheating"

# The bands that mean the tyre is not delivering what the compound can do.
BANDS_BELOW = (BAND_COLD, BAND_WARMING)
BANDS_ABOVE = (BAND_HOT, BAND_OVERHEATING)

# A compound is treated as having run in its window when at least this much of
# the lap-by-lap evidence sat in the optimal band. Two thirds rather than a
# majority: a tyre in window for half the run is a tyre that spent half the run
# somewhere else, and the whole point of this module is to stop that passing as
# clean evidence.
IN_WINDOW_FRACTION = 2 / 3


def band_for(compound_code: str, temp_c: float) -> str | None:
    """Which band a temperature falls in for this compound.

    None when the compound is unknown, because a band from the wrong
    compound's thresholds is worse than no band at all - Racing Hard's optimal
    range starts where Comfort Soft is already overheating.
    """
    compound = get_by_code(compound_code) if compound_code else None
    if compound is None:
        return None
    if temp_c < compound.cold_max:
        return BAND_COLD
    if temp_c < compound.warming_max:
        return BAND_WARMING
    if temp_c < compound.optimal_max:
        return BAND_OPTIMAL
    if temp_c < compound.hot_max:
        return BAND_HOT
    return BAND_OVERHEATING


def _lap_mean_temps(lap: LapInput) -> dict[str, float] | None:
    """Mean surface temperature per corner across one lap's frames."""
    if not lap.frames:
        return None
    per_corner: dict[str, float] = {}
    for corner in CORNERS:
        values = [frame[f"temp_{corner}"] for frame in lap.frames
                  if frame.get(f"temp_{corner}") is not None]
        if values:
            per_corner[corner] = mean(values)
    return per_corner or None


def window_by_compound(laps: list[LapInput]) -> dict[str, dict]:
    """How each compound's laps sat against that compound's own window.

    Keyed by compound code. A compound with no captured frames gets no entry
    at all rather than an entry full of nulls: "no temperature was recorded"
    and "the temperature was fine" must not look alike.
    """
    by_compound: dict[str, list[dict[str, float]]] = {}
    for lap in counted_laps(laps):
        if not lap.compound:
            continue
        temps = _lap_mean_temps(lap)
        if temps:
            by_compound.setdefault(lap.compound, []).append(temps)

    out: dict[str, dict] = {}
    for code, lap_temps in by_compound.items():
        compound = get_by_code(code)
        if compound is None:
            continue

        per_corner = {
            corner: round(mean([t[corner] for t in lap_temps if corner in t]), 1)
            for corner in CORNERS
            if any(corner in t for t in lap_temps)
        }
        if not per_corner:
            continue

        # One figure per lap - the mean across its corners - so a single
        # overheating corner does not read as an overheating car, and so the
        # in-window fraction counts laps rather than frames.
        lap_means = [mean(t.values()) for t in lap_temps]
        overall = mean(lap_means)
        bands = [band_for(code, value) for value in lap_means]
        in_window = sum(1 for band in bands if band == BAND_OPTIMAL)

        out[code] = {
            "meanC": round(overall, 1),
            "perCornerC": per_corner,
            "lapsSampled": len(lap_means),
            "hottestCorner": max(per_corner, key=per_corner.__getitem__),
            "source": "tyre-surface-temp",
            # The band and the window it is read against were never measured
            # in GT7 - see `store/tyres.py`. They travel with the temperature
            # so a reader can see the shape of the guess, flagged so nothing
            # downstream treats them as a finding.
            "band": band_for(code, overall),
            "windowC": [compound.warming_max, compound.optimal_max],
            "windowMeasured": False,
            "windowSource": (
                "NOT MEASURED IN GT7 - real-world slick figures carried over "
                "from the rebuild. Every compound in the 11 Aug Monza session "
                "ran 68-78 °C, so these bands do not describe this game. The "
                "temperature above is measured; the band is not a finding."),
            "lapsInWindow": in_window,
            "inWindow": None,
        }
    return out


def qualification(code: str, window: dict | None) -> str | None:
    """What this compound's temperature does to the evidence gathered on it.

    **Returns None, always, until a window has been measured in GT7.**

    It used to return a verdict - "RM never got into its window, so its pace
    deficit is overstated and its stint length is flattered" - and that verdict
    went into every export as a finding. The thresholds behind it were never
    measured in GT7 and are not GT7's numbers: across 51 laps of Monza every
    lap of every compound ran between 68 °C and 78 °C, while the thresholds put
    Racing Soft's window at 85-110 °C, where it could never once arrive. The
    qualification was therefore fired on every compound, every session, saying
    something confident about nothing.

    The temperature itself is real and stays in the payload, with
    `windowMeasured: false` beside it so a reader knows the band is decoration
    and not a finding. What replaces this is a measurement: the same corner at
    several times of day, achieved tyre temperature against lap time, and the
    temperature at which lap time stops improving is the bottom of the window.
    Until then, silence is the honest output.
    """
    return None
