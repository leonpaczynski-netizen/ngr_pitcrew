"""How hot each compound actually ran - and why that is all this can say.

GT7 gives per-wheel tyre surface temperature at 60 Hz. That figure is real and
is measured here per compound, per lap.

**What was not real is the window it used to be judged against.** `store/tyres`
carried a `cold_max` / `warming_max` / `optimal_max` / `hot_max` band per
compound, and this module compared the measured temperature to it and emitted
a verdict - "RM never got into its window, so its pace deficit is overstated
and its stint length is flattered" - into every export, as a finding, tagged
as measurement.

Those bands were real-world racing-slick figures at 90-110 degC. Across 51
laps of Monza on three compounds **every lap of every compound ran between
68 degC and 78 degC**, and GT7 fits every fresh set at exactly 70.0 degC -
precisely the Racing Soft cold ceiling. Under those bands a Racing Soft could
never once reach its own window, so the verdict fired every time and said
something confident about nothing.

They are now deleted rather than flagged, because a flag did not stop them
being read. The research behind that decision, Aug 2026: **no optimal
tyre-temperature window has ever been published for GT7 by anyone**, and the
only credible sourced figure is a per-compound UPPER WEAR threshold from a
single 2025 test - `store/tyres.WEAR_ONSET_C`, with its provenance and its
caveats beside it. There is no cold side and this module must not invent one.

So this module reports the temperature, says where the wear threshold sits
when the compound has one, and stops. `qualification()` returns None until a
window has been measured. `windowC` goes out as `null`, because there is no
window - missing is null, and a band shipped "for decoration" is a band that
gets read.

Surface temperature is not core temperature. GT7 exposes one float per wheel,
and parser authors - not Polyphony - are the ones who called it "surface". It
responds fast, so a mean over a lap is a reasonable read of the working range
while a single frame is not. Everything here is averaged over whole laps for
that reason.
"""
from __future__ import annotations

from statistics import mean

from pitcrew.analysis.session import LapInput, counted_laps
from pitcrew.store.tyres import (
    WEAR_ONSET_CAVEATS,
    WEAR_ONSET_GAME_VERSION,
    WEAR_ONSET_SOURCE,
    get_by_code,
)

CORNERS = ("fl", "fr", "rl", "rr")

# **The five bands are gone.** `cold` / `warming` / `optimal` / `hot` /
# `overheating` described a four-zone window with a cold side, and no evidence
# for such a shape exists in GT7. What is left is the one question the evidence
# can answer: is this compound above the temperature at which its wear starts
# to climb?
BAND_ABOVE_WEAR_ONSET = "above wear onset"


def above_wear_onset(compound_code: str | None,
                     temp_c: float) -> bool | None:
    """Whether this temperature is past the compound's wear-onset threshold.

    None where the compound is unknown or has never been tested, which is
    every compound except the three Racing ones. None is "nobody has measured
    this", not "the tyre is fine", and the two must never look alike.
    """
    compound = get_by_code(compound_code) if compound_code else None
    if compound is None or compound.wear_onset_c is None:
        return None
    return temp_c >= compound.wear_onset_c


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
        onset = compound.wear_onset_c
        hot_laps = (None if onset is None
                    else sum(1 for value in lap_means if value >= onset))

        out[code] = {
            "meanC": round(overall, 1),
            "perCornerC": per_corner,
            "lapsSampled": len(lap_means),
            "hottestCorner": max(per_corner, key=per_corner.__getitem__),
            "source": "tyre-surface-temp",
            # **No band, and no window.** Both used to be emitted here off
            # figures that were never GT7's. `null` is the honest value: a
            # reader has to be able to tell "nobody has measured a window for
            # this game" from "the tyre was fine".
            "band": (BAND_ABOVE_WEAR_ONSET
                     if onset is not None and overall >= onset else None),
            "windowC": None,
            "windowMeasured": False,
            "windowSource": _window_source(code, onset),
            # Laps at or above the wear-onset threshold, where one exists. Not
            # "in window" - there is no window - but it is the key the contract
            # gives us, carrying the only count the evidence supports.
            "lapsInWindow": hot_laps,
            "inWindow": None,
        }
    return out


def _window_source(code: str, onset: float | None) -> str:
    """What is and is not known about this compound's temperature, in one line."""
    if onset is None:
        return (
            f"NO GT7 FIGURE EXISTS for {code}. No optimal window has ever been "
            "published for GT7 by Polyphony or by anyone else, and the one "
            "community wear test covered only the three Racing compounds. The "
            "temperature above is measured; there is nothing to judge it "
            "against.")
    return (
        f"No GT7 window exists - none has ever been published. The only "
        f"sourced figure is an UPPER wear-onset threshold of {onset:.0f} °C "
        f"({WEAR_ONSET_SOURCE}, tested on {WEAR_ONSET_GAME_VERSION}), above "
        f"which wear climbs disproportionately. It is not a window and there is "
        f"no cold-side figure. Caveats: " + "; ".join(WEAR_ONSET_CAVEATS))


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
