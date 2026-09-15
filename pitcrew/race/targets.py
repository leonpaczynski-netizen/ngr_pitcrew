"""Was that lap on the plan's target? The verdict and the words for it.

The driver, 16 Sep 2026, asked for every lap to be judged against what the
approved plan asks of it - a lap time on the compound he is on and a burn -
said by George and shown on the board. The targets themselves are the plan's
(`strategy/targets.py`); this module decides which laps get a verdict, what
the verdict is, and the one sentence each half is said in.

### Why a single lap, when this codebase refused pace verdicts

`calls._fuel_standing` says a pace verdict is a coin flip: lap-to-lap sigma of
0.68-2.04 s against a 0.5-1.5 s/lap degradation band. That argument is about
**inferring the car's pace** from a lap, and it still holds. This is not that:
it reports how one completed lap compared with the number he was asked to
drive, which is a measurement of the lap and not a claim about the car. The
whole-lap comparison is the fair one the race-engineer charter allows; the
multi-lap pace call stays where it was. The number is always said, so a lap in
traffic reads as "Pace 1.4 seconds slow" and he can discount it himself.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.engineer import say

# **Inside this, the lap is on target.** Two tenths: the finest gap the voice
# says in words ("two tenths"), so "on target" never covers a gap that would
# otherwise be spoken as a number. A stated choice, not a measurement (rule 5).
ON_TARGET_S = 0.2
# Inside this, the burn is on target. A tenth of a litre is under 2% of any
# burn on file (4.2-8.6 L/lap) and the finest figure the sentence says.
ON_TARGET_L = 0.1
# **A lap this far off its target is not a lap that tried.** The pace
# estimator's own incident split (`expectations.BURN_OUTLIER_FRACTION`): his
# noise is about 1.7% of a lap and measured incidents run 5-10% over.
OFF_TARGET_FRACTION = 0.04


@dataclass(frozen=True)
class TargetVerdict:
    """One completed lap against its target. Positive deltas are slow / over."""
    lap: int
    lap_ms: int | None
    target_ms: int | None
    lap_delta_s: float | None
    burn_l: float | None
    target_burn_l: float | None
    burn_delta_l: float | None

    @property
    def pace_on_target(self) -> bool | None:
        if self.lap_delta_s is None:
            return None
        return abs(self.lap_delta_s) < ON_TARGET_S

    @property
    def burn_on_target(self) -> bool | None:
        if self.burn_delta_l is None:
            return None
        return abs(self.burn_delta_l) < ON_TARGET_L


def why_no_verdict(lap, *, rolling_start: bool, incident: bool) -> str | None:
    """Why this lap gets no verdict, or None where it does."""
    if lap.lap_num <= 1 and not rolling_start:
        return "lap 1 of a standing start"
    if getattr(lap, "is_pit_lap", False):
        return "a pit lap"
    if getattr(lap, "is_out_lap", False):
        return "an out lap"
    if incident:
        return "an incident lap"
    if not lap.lap_time_ms or lap.lap_time_ms <= 0:
        return "no lap time"
    return None


def judge(lap, target) -> TargetVerdict | None:
    """The verdict on one lap, or None where neither half can be judged.

    **A burn that came out negative is not a burn** (rule 9): `fuel_used` on a
    lap with fuel added reads wrong, and the lap gets no burn verdict rather
    than a clamped one.
    """
    if target is None:
        return None
    lap_ms = int(lap.lap_time_ms)
    lap_delta = None
    if target.lap_ms:
        lap_delta = (lap_ms - target.lap_ms) / 1000.0
        if lap_delta > target.lap_ms / 1000.0 * OFF_TARGET_FRACTION:
            # An off, a spin, a lap in the barrier: the pace half is not a
            # verdict about driving to a target. The burn half still is.
            lap_delta = None
    used = getattr(lap, "fuel_used", None)
    burn = float(used) if used is not None and used > 0 else None
    burn_delta = (round(burn - target.burn_l, 3)
                  if burn is not None and target.burn_l else None)
    if lap_delta is None and burn_delta is None:
        return None
    return TargetVerdict(lap=int(lap.lap_num), lap_ms=lap_ms,
                         target_ms=target.lap_ms, lap_delta_s=lap_delta,
                         burn_l=burn, target_burn_l=target.burn_l,
                         burn_delta_l=burn_delta)


def pace_sentence(delta_s: float | None) -> str:
    """"Pace on target." / "Pace two tenths slow." / "Pace 1.4 seconds quick."

    **Named "Pace", never bare "On target"**, because the burn clause beside
    it is on target or not too, and one phrase for two quantities under a
    helmet is rule 13.
    """
    if delta_s is None:
        return ""
    if abs(delta_s) < ON_TARGET_S:
        return "Pace on target."
    return (f"Pace {say.spoken_gap(delta_s)} "
            f"{'slow' if delta_s > 0 else 'quick'}.")


def burn_sentence(delta_l: float | None) -> str:
    """"Burn on target." / "Burn 0.3 litres over." / "Burn 0.2 litres under."

    **"Burn", not "Fuel"**: the heartbeat's last clause is "Fuel good to the
    stop", which is the tank. This is the lap's consumption against the plan's
    per-lap figure - a different quantity, so a different word (rule 13).
    """
    if delta_l is None:
        return ""
    if abs(delta_l) < ON_TARGET_L:
        return "Burn on target."
    return (f"Burn {abs(delta_l):.1f} litres "
            f"{'over' if delta_l > 0 else 'under'}.")


def board_target_fields(state) -> dict:
    """The `DriverState` fields for the targets, off a `RaceState`.

    A function rather than a controller method so the board's stubbed tests
    need nothing bound to reach it. Every field None where there is nothing:
    no plan targets, the out lap, a lap that got no verdict (rule 3).
    """
    target = getattr(state, "lap_target", None)
    verdict = getattr(state, "target_verdict", None)
    return {
        "target_lap_ms": getattr(target, "lap_ms", None),
        "target_burn_l": getattr(target, "burn_l", None),
        "target_why": (getattr(target, "why_no_lap", None)
                       if target is not None else None),
        "target_saving": getattr(target, "saving", None),
        "last_vs_target_s": getattr(verdict, "lap_delta_s", None),
        "last_burn_vs_target_l": getattr(verdict, "burn_delta_l", None),
    }


def verdict_sentence(verdict: TargetVerdict | None) -> str:
    """Both halves, pace first. Empty where there is no verdict."""
    if verdict is None:
        return ""
    return " ".join(part for part in (pace_sentence(verdict.lap_delta_s),
                                      burn_sentence(verdict.burn_delta_l))
                    if part)
