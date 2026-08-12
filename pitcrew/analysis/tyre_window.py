"""Where each compound actually ran, against the window it wants.

GT7 gives per-wheel tyre **surface** temperature at 60 Hz, and `store/tyres.py`
has carried a per-compound window since the rebuild — `cold_max`,
`warming_max`, `optimal_max`, `hot_max`. Until now nothing read them, so the
strategy model compared compounds on pace and wear without ever asking whether
those figures were gathered on a tyre that was working.

That question changes what the numbers mean:

* **A compound below its window is slower than it is, and wears less than it
  will.** Harder compounds need more energy to light up. Measure a Racing Hard
  on a cool track behind traffic and its pace deficit is partly the
  temperature, not the tyre — and the long stint it appears to promise is a
  cold-tyre wear rate that will not survive a race at proper pace.
* **A compound above its window wears faster than it will.** An overheating
  stint measures a rate that a cooler race would not reproduce.

**Nothing here corrects a measurement.** It would be easy, and wrong, to scale
a cold compound's pace by some recovery factor — GT7 publishes no such curve
and inventing one would put a fabricated number where a measured one belongs.
This module qualifies the evidence and says so in words; the arithmetic stays
exactly as measured.

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
            "band": band_for(code, overall),
            "lapsSampled": len(lap_means),
            "lapsInWindow": in_window,
            "inWindow": in_window >= len(lap_means) * IN_WINDOW_FRACTION,
            "windowC": [compound.warming_max, compound.optimal_max],
            "hottestCorner": max(per_corner, key=per_corner.__getitem__),
            "source": "tyre-surface-temp",
        }
    return out


def qualification(code: str, window: dict | None) -> str | None:
    """What this compound's window does to the evidence gathered on it.

    None when the evidence needs no qualification — the tyre was working, so
    the pace and wear measured on it describe the compound rather than the
    conditions.
    """
    if not window or window.get("inWindow"):
        return None

    band = window.get("band")
    low, high = window.get("windowC", (None, None))
    ran = window.get("meanC")
    sampled = window.get("lapsSampled", 0)
    inside = window.get("lapsInWindow", 0)
    outside = sampled - inside

    where = (f"{ran} °C mean against a {low}–{high} °C window, "
             f"{outside} of {sampled} laps outside it")

    if band in BANDS_BELOW:
        return (
            f"{code} never got into its window ({where}). A cold tyre is "
            f"slower than the compound is and wears less than it will, so its "
            f"pace deficit is overstated and its stint length is flattered. "
            f"Neither figure describes a race run at temperature.")
    if band in BANDS_ABOVE:
        return (
            f"{code} ran hot ({where}). An overheating tyre wears faster than "
            f"it will in a cooler race, so the stint length measured on it is "
            f"pessimistic - and the wear itself may be a setup problem rather "
            f"than a property of the compound.")
    # In one of the working bands on average, but not consistently enough.
    return (
        f"{code} was only in its window for {inside} of {sampled} laps "
        f"({where}). The pace and wear measured on it are a mixture of "
        f"conditions rather than one.")
