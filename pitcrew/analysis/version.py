"""Which laps still describe the car you are about to race.

`analysis/recency` weights laps down as they age, because the driver gets
faster and the setup moves on. **A physics update is not that.** It is not a
gradual loss of relevance that a weight can express — it is a discontinuity.
Laps recorded on either side of one are not weaker and stronger evidence about
the same car; they are evidence about two different cars.

GT7 v1.71, 20 Aug 2026, reworked the tyre slipping model, per-car steering
geometry, damper attenuation, and the adjustment ranges of suspension,
differential and aero. Polyphony reset every ranking board, which is their own
statement that old lap times no longer compare to new ones.

So version is a **precedence tier, not a weight**:

* where the current version has evidence, it is used **alone**;
* where it does not, older evidence is used and **the result says so**;
* the two are **never blended**, because an average across a patch describes
  nothing that was ever driven.

*"Use it as a guide, but the new version date trumps old data"* — the driver,
21 Aug 2026.

## The exemption this withdraws

`analysis/recency` carves out degradation explicitly:

> **Not degradation.** … a gauge reading from three weeks ago is exactly as
> true as one from today.

That was right, and 1.71 made it false. The reasoning was that a gauge reading
is a measurement of GT7's own wear model rather than an estimate, so age cannot
erode it — but that holds only while the wear model is the same model. **1.71
changed it.** A gauge reading from three weeks ago is exactly as true as one
from today *about the game it was taken on*, and that game no longer exists.

The exemption stands **within** a version and is void **across** one.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Selection:
    """The laps to reason from, and an honest account of what was set aside."""

    laps: list
    #: The version everything in `laps` was recorded under. None when no lap
    #: carries a version at all — which is not the same as being current.
    version: str | None
    #: True when `laps` is not from the version being planned for.
    stale: bool
    #: One sentence for the export and for the prompt. Never empty when
    #: anything was held back or when the evidence is pre-patch.
    note: str | None

    def __bool__(self) -> bool:
        return bool(self.laps)


def versions_present(laps) -> list[str]:
    """Every distinct version among these laps, oldest string first."""
    return sorted({lap.game_version for lap in laps if lap.game_version})


def prefer_current(laps, current: str | None, *, minimum: int = 1) -> Selection:
    """Laps from `current` if there are enough of them, else all of them, said.

    `minimum` is the caller's own floor — the point below which its estimate
    would be refused anyway. Falling back is better than returning three laps
    and letting a downstream sample-count check turn them into silence with no
    explanation.

    **Never blends.** The fallback is every lap, not the current ones topped up
    with older ones, because a mixed set has no version to declare and the
    export has to declare one.
    """
    laps = list(laps)
    if not laps:
        return Selection([], None, False, None)

    present = versions_present(laps)
    if not present:
        return Selection(
            laps, None, False,
            "no lap carries a game version, so none of this evidence can be "
            "placed either side of a physics update")

    if current is None:
        return Selection(
            laps, present[-1] if len(present) == 1 else None, False,
            "the installed GT7 version is not set, so evidence from "
            + " and ".join(present) + " could not be told apart")

    matching = [lap for lap in laps if lap.game_version == current]
    older = len(laps) - len(matching)

    if len(matching) >= minimum:
        note = None
        if older:
            note = (f"{len(matching)} lap{'' if len(matching) == 1 else 's'} on "
                    f"GT7 {current}; {older} recorded on "
                    + " and ".join(v for v in present if v != current)
                    + " held back - a physics update makes them evidence about "
                      "a different car, not weaker evidence about this one")
        return Selection(matching, current, False, note)

    return Selection(
        laps, None if len(present) > 1 else present[0], True,
        f"no usable evidence on GT7 {current} - "
        f"{len(matching)} lap{'' if len(matching) == 1 else 's'} recorded, "
        f"{minimum} needed - so this rests on "
        + " and ".join(present) +
        f", recorded before the physics changed. Treat it as a starting point "
        f"and re-measure on {current}.")
