"""Gearbox authoring from evidence, or not at all (pure, Qt-free) — UAT 2026-08-07 A4.

``_build_gearbox_changes`` used to produce the SAME geometric spread for every car in
the game — 3.800/2.558/1.722/1.159/0.780/0.525 and a final drive of 4.25 — from two
global constants, with no reference to the engine, the redline or the track. A gearbox
is the one part of a setup a driver cannot diagnose by feel from the sheet, so a
plausible-looking wrong answer there is worse than no answer.

Phase 0 stopped the orphan case (a final drive authored with no ratios attached,
because ``num_gears`` is read from ``car_specs.json``, which carries that key for no
car). This module builds the positive case, and its central decision is to author
NOTHING far more often than the old code did:

  * a **proven** gearbox for this car at this track is used verbatim;
  * otherwise, gearing needs the car's redline, its stock ratios and the track's
    longest straight. None of those exist for any car until a GT7 capture supplies
    them, so the honest answer today is "keep the stock gearing" plus a specific list
    of what would be needed to do better. That is a better answer than a confident
    geometric spread, and it tells the driver exactly which capture unlocks it.

The one thing that CAN be said without a capture is a direction: a long-straight track
wants longer gearing, a corner-dense one wants shorter. That already exists as
``final_drive_lean`` from the engineering-intents layer, and it is reported as a
direction, never converted into a ratio it cannot justify.

Pure: no Qt, no DB, no network, no AI, no wall-clock, no randomness. Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from typing import Optional

#: What a from-evidence gearbox derivation needs, and why.
REQUIREMENTS = {
    "redline_rpm": "the car's redline — sets where each ratio has to land",
    "stock_ratios": "the car's stock ratios — the shape to adjust, not replace",
    "longest_straight_m": "the track's longest straight — sets the top-speed target",
}


@dataclass(frozen=True)
class GearboxPlan:
    """Either a gearbox authored from evidence, or an explicit refusal to author one."""
    authored: bool
    final_drive: Optional[float] = None
    ratios: dict = _dc_field(default_factory=dict)      # "gear_1" -> ratio
    source: str = ""
    advice: str = ""
    missing: tuple = ()
    reasons: tuple = ()

    @property
    def gear_count(self) -> int:
        return len(self.ratios)

    def as_json(self) -> dict:
        return {"authored": self.authored, "final_drive": self.final_drive,
                "ratios": dict(self.ratios), "source": self.source,
                "advice": self.advice, "missing": list(self.missing),
                "reasons": list(self.reasons)}


#: The sentence the Garage shows when nothing can be authored. Deliberately an
#: instruction the driver can act on, not an apology.
KEEP_STOCK_ADVICE = (
    "Keep the car's stock gearing. Nothing here knows this car's redline or stock "
    "ratios, and a gearbox invented without them is the one part of a setup you "
    "cannot judge by feel.")


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def derive_gearbox(
    *,
    car_model=None,
    track_profile=None,
    proven_gearbox: Optional[dict] = None,
    final_drive_lean: float = 0.0,
) -> GearboxPlan:
    """Decide what, if anything, to author for the gearbox. Never raises.

    ``car_model`` is a ``data.car_parameter_model.CarParameterModel``; the redline and
    stock ratios come from a GT7 capture on it.
    """
    reasons: list = []
    # The lean arrives from the engineering layer and is only ever read as a direction;
    # normalise it once so a junk value degrades to "no lean" rather than raising.
    final_drive_lean = _num(final_drive_lean) or 0.0

    # 1. A proven gearbox is the strongest evidence there is — use it verbatim.
    pg = proven_gearbox or {}
    ratios = {}
    for i in range(1, 7):
        v = _num(pg.get(f"gear_{i}"))
        if v is not None:
            ratios[f"gear_{i}"] = v
    fd = _num(pg.get("final_drive"))
    if ratios:
        reasons.append(
            f"a vetted {len(ratios)}-speed gear set exists for this car at this track")
        if fd is not None:
            reasons.append(f"with its proven final drive of {fd:g}")
        return GearboxPlan(authored=True, final_drive=fd, ratios=ratios,
                           source="proven-setup library", reasons=tuple(reasons))

    # A proven FINAL DRIVE with no ratios is still evidence, but it is not a gearbox.
    # Phase 0 established that authoring it alone silently mismatches the car's stock
    # ratios in the one direction the driver cannot diagnose from the sheet.
    if fd is not None:
        return GearboxPlan(
            authored=True, final_drive=fd, ratios={},
            source="proven-setup library (final drive only)",
            advice="Set the final drive and leave the individual ratios stock.",
            reasons=("a proven final drive exists for this car at this track, but no "
                     "proven ratios — the stock ratios stay",))

    # 2. From-evidence derivation. Establish what we actually have.
    missing: list = []
    redline = _num(getattr(car_model, "redline_rpm", None))
    if redline is None:
        missing.append("redline_rpm")
    stock = {}
    try:
        for i in range(1, 7):
            v = _num((getattr(car_model, "stock_ratios", None) or {}).get(f"gear_{i}"))
            if v is not None:
                stock[f"gear_{i}"] = v
    except Exception:
        stock = {}
    if not stock:
        missing.append("stock_ratios")
    straight = _num(getattr(track_profile, "longest_straight_m", None))
    if straight is None or not getattr(track_profile, "measured", False):
        missing.append("longest_straight_m")

    if missing:
        # 3. Author nothing — but say precisely what is missing and what would fix it,
        # and report the one thing that IS known: the direction the track wants.
        if final_drive_lean:
            direction = "longer" if final_drive_lean < 0 else "shorter"
            reasons.append(
                f"the track wants {direction} gearing, but a direction is not a ratio")
        return GearboxPlan(
            authored=False, missing=tuple(missing),
            advice=KEEP_STOCK_ADVICE + " Capture " + ", ".join(
                REQUIREMENTS[m].split(" — ")[0] for m in missing) + " to change that.",
            reasons=tuple(reasons))

    # 4. Everything is present: adjust the STOCK ratios rather than replacing them.
    # The shape of a manufacturer's gearbox encodes far more about the engine than
    # anything derivable here; the only defensible move is to scale it to the straight.
    target = _target_top_speed(straight)
    scale = _final_drive_scale(final_drive_lean)
    reasons.append(f"stock ratios kept, scaled for a {straight:.0f} m straight")
    reasons.append(f"top-speed target {target:.0f} km/h at {redline:.0f} rpm")
    return GearboxPlan(
        authored=True,
        final_drive=(round(fd * scale, 3) if fd is not None else None),
        ratios=dict(stock), source="stock ratios scaled to the track",
        reasons=tuple(reasons))


def _target_top_speed(longest_straight_m: float) -> float:
    """A top-speed target from the longest straight.

    Deliberately coarse: this exists so the scale factor has a stated basis, not to
    pretend to a precision no input here supports.
    """
    if longest_straight_m >= 1200:
        return 320.0
    if longest_straight_m >= 900:
        return 300.0
    if longest_straight_m >= 600:
        return 280.0
    return 260.0


def _final_drive_scale(lean: float) -> float:
    """Convert the engineering layer's final-drive lean into a bounded scale factor.

    Bounded to +/-6% so a track shaping signal can never restructure the gearbox.
    """
    try:
        lean = float(lean or 0.0)
    except (TypeError, ValueError):
        lean = 0.0
    return max(0.94, min(1.06, 1.0 + lean * 0.02))
