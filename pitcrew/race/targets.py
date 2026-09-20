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
from pitcrew.strategy.targets import BURN_BASIS_PLAN, BURN_BASIS_RACE

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

# **The two references, in the one word a tile has room for.** The voice says
# `strategy.targets.BURN_BASIS_PLAN` ("the plan") and `BURN_BASIS_RACE` ("this
# race's burn"); a caption on the phone strip is fourteen characters wide and
# a rack row's note column is narrower than that, so neither sentence fits
# where the number is.
#
# **Each word is the head noun of the sentence he hears, and nothing else.**
# "vs race" is what "Against this race's burn." shortens to and could not be
# mistaken for "Against the plan."; the two stay a glance apart. An
# abbreviation of the spoken reference is the same vocabulary as the spoken
# reference - a third word for either of them, chosen for a screen, would be
# rule 13 with extra steps.
#
# Keyed off the constants themselves rather than off a string typed here, and
# **unknown is None, not a guess**: a basis added to `strategy.targets` later
# arrives with no word and the surfaces draw no qualifier, which is a gap
# somebody notices, where inheriting whichever word was nearest is the defect
# this exists to close (rule 3).
BURN_WORDS = {BURN_BASIS_PLAN: "plan", BURN_BASIS_RACE: "race"}


def burn_source_word(source: str | None) -> str | None:
    """"plan" or "race" for a screen, or None where nothing was said."""
    return BURN_WORDS.get(source) if source else None


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
    # **Which burn `target_burn_l` is** - `strategy.targets.BURN_BASIS_PLAN`
    # or `BURN_BASIS_RACE` - and the green laps behind it where it is this
    # race's own. Rule 4 and rule 13: the delta is meaningless without its
    # reference, and the reference changed mid-race at Bathurst Rd 8.
    burn_source: str | None = None
    burn_laps: int | None = None
    # What the plan asked for, whatever was actually used. Kept so the audit
    # can read both halves off one row.
    planned_burn_l: float | None = None

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
                         burn_delta_l=burn_delta,
                         # **From the same target the delta was taken off**
                         # (rule 12): a reference read from anywhere else
                         # could name a burn this delta was not measured
                         # against.
                         burn_source=(getattr(target, "burn_source", None)
                                      if burn_delta is not None else None),
                         burn_laps=(getattr(target, "burn_laps", None)
                                    if burn_delta is not None else None),
                         planned_burn_l=getattr(target, "planned_burn_l",
                                                None))


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


def burn_sentence(delta_l: float | None, against: str | None = None) -> str:
    """"Burn on target. Against the plan." / "Burn 0.3 litres over. ..."

    **"Burn", not "Fuel"**: the heartbeat's last clause is "Fuel good to the
    stop", which is the tank. This is the lap's consumption against a per-lap
    figure - a different quantity, so a different word (rule 13).

    **And the reference is a sentence of its own, every time.** Until 20 Sep
    2026 this said "Burn 2.2 litres under" whether the figure behind it was
    the plan's or this race's own, and at Bathurst Rd 8 it was the plan's for
    all 28 laps of a race run 22% under it. Two calls in the same words
    meaning two things is rule 13, and under a helmet he cannot ask which one
    he just heard.

    A separate sentence rather than a longer clause, for a mechanical reason
    as well as a spoken one: `phrase_manifest._pieces` can only render a
    sentence carrying ONE number, so "Burn 0.3 litres under this race's burn
    over 19 laps" would be a line the voice pack cannot hold and every
    decisive burn call would fall to live synthesis. The reference sentence
    carries no number at all, so it is one clip for the race.

    `against` is `strategy.targets.BURN_BASIS_PLAN` or `BURN_BASIS_RACE`.
    None names nothing rather than guessing - the caller did not say.
    """
    if delta_l is None:
        return ""
    if abs(delta_l) < ON_TARGET_L:
        said = "Burn on target."
    else:
        said = (f"Burn {abs(delta_l):.1f} litres "
                f"{'over' if delta_l > 0 else 'under'}.")
    return f"{said} Against {against}." if against else said


def stint_burn(state) -> tuple[float | None, int, bool | None]:
    """`(mean litres over target a lap, laps behind it, saving?)` this stint.

    **Only the laps on the column the last judged lap was driven on.** The two
    beep columns are two burns ~30% apart, and pooling a stint that switched
    lands near the practice figure - right-looking and wrong (Sardegna
    session 183). Every figure carries its lap count (rule 4); `None` with no
    judged lap on that column, never a zero.
    """
    burns = list(getattr(state, "stint_burns", None) or [])
    if not burns:
        return None, 0, None
    column = burns[-1][0]
    mine = [delta for saving, delta in burns if saving == column]
    return round(sum(mine) / len(mine), 3), len(mine), column


def board_target_fields(state) -> dict:
    """The `DriverState` fields for the targets, off a `RaceState`.

    A function rather than a controller method so the board's stubbed tests
    need nothing bound to reach it. Every field None where there is nothing:
    no plan targets, the out lap, a lap that got no verdict (rule 3).

    **The burn target's reference travels with it, and so does its lap
    count.** `target_burn_l` steps from the plan's figure to this race's the
    moment one is installed - 10.625 to 8.47 around lap 7 at Bathurst Rd 8,
    a drop of 2.2 L - and until 21 Sep 2026 nothing on any screen said so.
    The voice names it and the log names it; the tile drew a number that
    changed what it meant with no mark on it, which is rule 13 on the surface
    he actually looks at. `target_burn_laps` is rule 4 beside it: the plan's
    figure has no lap count and this race's does, so the count appearing IS
    the figure turning from a plan into a measurement.

    **`last_burn_source` is the verdict's, not the target's, and they are two
    references for one lap.** `target_verdict` is the lap just finished and
    `lap_target` is the lap now being driven, so on the lap the reference
    changes the delta was judged against the old one while the target beside
    it is the new one. They are carried apart rather than pooled so the
    surfaces can mark that lap instead of quietly wording it as either
    (rule 12: the reference shown comes off the same object the figure did).
    """
    target = getattr(state, "lap_target", None)
    verdict = getattr(state, "target_verdict", None)
    stint_delta, stint_laps, stint_saving = stint_burn(state)
    return {
        "stint_burn_vs_target_l": stint_delta,
        "stint_burn_laps": stint_laps,
        "stint_burn_saving": stint_saving,
        "target_lap_ms": getattr(target, "lap_ms", None),
        "target_burn_l": getattr(target, "burn_l", None),
        "target_burn_source": getattr(target, "burn_source", None),
        "target_burn_laps": getattr(target, "burn_laps", None),
        "target_why": (getattr(target, "why_no_lap", None)
                       if target is not None else None),
        "target_saving": getattr(target, "saving", None),
        "last_vs_target_s": getattr(verdict, "lap_delta_s", None),
        "last_burn_vs_target_l": getattr(verdict, "burn_delta_l", None),
        "last_burn_source": getattr(verdict, "burn_source", None),
    }


def verdict_sentence(verdict: TargetVerdict | None) -> str:
    """Both halves, pace first. Empty where there is no verdict."""
    if verdict is None:
        return ""
    return " ".join(part for part in (
        pace_sentence(verdict.lap_delta_s),
        burn_sentence(verdict.burn_delta_l, verdict.burn_source)) if part)
