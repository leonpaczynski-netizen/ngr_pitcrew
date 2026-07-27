"""Capture convergence — "has the track model stopped changing yet?"

The guided flow used to make the driver guess when they had recorded enough laps,
then manually build / review / validate / activate. The engineering objective is
simpler: keep driving until the model is stable, then approve it automatically.

This module is the deterministic judge of "stable". The reference path is the
aggregate of the usable calibration laps, so once those laps are geometrically
*repeatable* — the driver is putting the car through the same line lap after lap —
adding more laps no longer moves the model. We measure that repeatability from the
per-lap path length, which the calibration layer already computes and already trusts
(it uses the median path length to reject outlier laps).

Pure and deterministic: no Qt, no I/O, no AI, no timestamps. Never raises. The live
layer calls this once per completed lap and speaks the verdict to the driver.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import List, Sequence

#: A model needs at least this many usable laps before it can be called complete —
#: two build a reference path at all, a third confirms the line is repeatable rather
#: than a lucky pair.
MIN_USABLE_LAPS: int = 3

#: How many of the most-recent usable laps must agree for the model to be "stable".
STABILITY_WINDOW: int = 3

#: Maximum spread (percent of median path length) across the window for the laps to
#: count as repeatable. Real laps of one layout driven cleanly vary well under this;
#: a wider spread means the line is still moving (or a lap wandered).
MAX_SPREAD_PCT: float = 0.6


@dataclass(frozen=True)
class ConvergenceResult:
    """Whether the captured laps have stabilised into a usable track model."""
    converged: bool = False
    usable_laps: int = 0
    spread_pct: float = 0.0           # path-length spread across the window, % of median
    reason: str = ""                  # why not converged (empty when converged)

    @property
    def laps_remaining_hint(self) -> int:
        """Rough number of extra clean laps still wanted (0 once converged)."""
        if self.converged:
            return 0
        return max(0, MIN_USABLE_LAPS - self.usable_laps)


def _usable_path_lengths(laps: Sequence) -> List[float]:
    """Path lengths of usable, non-pit calibration laps, in order. Duck-typed."""
    out: List[float] = []
    for lap in laps or []:
        try:
            if getattr(lap, "is_pit_lap", False):
                continue
            quality = getattr(lap, "quality", None)
            qname = str(getattr(quality, "value", "") or getattr(quality, "name", "") or quality).lower()
            if qname and qname != "usable":
                continue
            length = float(getattr(lap, "path_length_m", 0.0) or 0.0)
            if length > 0.0:
                out.append(length)
        except Exception:  # pragma: no cover - defensive
            continue
    return out


def assess_capture_convergence(
    laps: Sequence,
    *,
    min_laps: int = MIN_USABLE_LAPS,
    window: int = STABILITY_WINDOW,
    max_spread_pct: float = MAX_SPREAD_PCT,
) -> ConvergenceResult:
    """Judge whether the captured laps form a stable (complete) track model.

    Converged when there are at least ``min_laps`` usable laps AND the most recent
    ``window`` of them agree on path length to within ``max_spread_pct`` — i.e. the
    driver is repeating the same line, so the aggregated model has stopped moving.
    """
    lengths = _usable_path_lengths(laps)
    n = len(lengths)
    if n < min_laps:
        return ConvergenceResult(
            converged=False, usable_laps=n, spread_pct=0.0,
            reason=f"{n} clean lap{'s' if n != 1 else ''} so far — need at least {min_laps}.")

    recent = lengths[-window:]
    med = median(recent)
    if med <= 0:
        return ConvergenceResult(converged=False, usable_laps=n, reason="No valid lap geometry yet.")
    spread_pct = (max(recent) - min(recent)) / med * 100.0
    if spread_pct > max_spread_pct:
        return ConvergenceResult(
            converged=False, usable_laps=n, spread_pct=spread_pct,
            reason=(f"Your last {len(recent)} laps still vary by {spread_pct:.1f}% — "
                    f"the line is still settling. Keep driving clean, consistent laps."))
    return ConvergenceResult(converged=True, usable_laps=n, spread_pct=spread_pct, reason="")


def convergence_coach_message(result: ConvergenceResult) -> str:
    """What the engineer says to the driver about capture progress."""
    if not isinstance(result, ConvergenceResult):
        return ""
    if result.converged:
        return ("Track data is complete and consistent — box this lap and I'll approve "
                "the model, then bring it round the pit lane once to map it.")
    if result.usable_laps < MIN_USABLE_LAPS:
        need = MIN_USABLE_LAPS - result.usable_laps
        return (f"{result.usable_laps} clean lap{'s' if result.usable_laps != 1 else ''} "
                f"logged — keep going, {need} more to go.")
    return "Lines still settling — keep lapping cleanly and I'll tell you when it's done."
