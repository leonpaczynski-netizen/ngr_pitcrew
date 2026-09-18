"""How a rival's tyres will be, modelled from his last stop and OUR wear rate.

The driver, 19 Sep 2026, about Sardegna Rd 9: *"using our tyre model george
should be able to tell me how his tyres will be when he is catching me ...
Rocky is catching but based on his last stop his tyres will be off the cliff
in the last lap so keep fighting. This is critical information."*

He was right that it was computable. Rocky stopped at the end of his lap 14
and ran 15 laps on Racing Medium. Our RM rate at that circuit and multiplier
is 0.068 worn a lap, so the model put him at the cliff around lap 28 of 29 -
and on the final lap he fell from 0.6 s ahead in P3 to 17 s behind in P5.

### What this can and cannot know

**Nothing here is measured, and it never says otherwise** (CLAUDE.md rule 5,
§3.3). GT7 has no tyre-wear channel for any car, least of all someone else's.
Every figure is OUR measured rate applied to HIS laps on the set:

* **Laps on the set** - from the lap the pit wall saw him stop, which is a
  reading. This is the solid half.
* **The rate** - ours, fitted from our gauge at this circuit, for this
  compound, at this race's multiplier. `Knowledge.wear_per_lap` already
  refuses a rate measured at another multiplier (§5.2), and it carries its
  sample count (rule 4). Applying it to his car assumes his car and driving
  wear the set as ours does - a fair assumption in a one-make series, and
  still an assumption.
* **The compound - the weakest link, and said so.** The disc is a single
  letter, and on the one stop where we know the truth (our own, 16 Sep: we
  fitted RH) it read M the whole time - so it appears to show the tyres a car
  ARRIVED on, not the ones it left on. One sample, not proof. So what this
  projects is "if he went back out on the same compound", and the derived
  record says exactly that.

### The cliff, not the stint limit

`WEAR_STINT_LIMIT` (0.85) is OUR planning margin - where we choose to box. A
rival's tyres are going OFF at the cliff, which §5.1 puts at about 90% worn:
traction gone, car undriveable rather than merely slow. That is the moment
the driver needs, so it is what this projects.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# Where a set goes off - CLAUDE.md §5.1, and `strategy.model.PHASE_CLIFF_FROM`.
# Imported rather than restated, so the voice and the planner mean one thing
# by "the cliff" (rule 13).
from pitcrew.strategy.model import PHASE_CLIFF_FROM as CLIFF_WORN

# Dry compound letters the disc can show, and the dry families a letter can
# belong to - Racing, Sports, Comfort. Wet and intermediate are whole codes of
# their own (`IM`, `HW`) and carry no family.
_DRY_LETTERS = ("S", "M", "H")
_DRY_FAMILIES = ("R", "S", "C")


@dataclass(frozen=True)
class RivalTyres:
    """One rival's set, as our model sees it. Every field is derived."""
    driver: str
    compound: str           # full code, e.g. "RM"
    laps_on_set: float      # laps COMPLETED since his stop
    rate: float             # OUR worn fraction a lap for this compound
    samples: int            # the stints behind that rate (rule 4)
    worn_now: float         # rate x laps on the set, modelled
    cliff_key: float        # the completed-lap key where he reaches the cliff

    def cliff_lap(self, screen_offset: int) -> int:
        """The lap on his screen when the set goes off.

        **The catch lap's own conversion**, `CatchProjection.catch_lap`, so
        "on you around lap 25" and "off around lap 28" are the same kind of
        number in one sentence (rule 13).
        """
        return math.floor(self.cliff_key) + int(screen_offset)

    def model(self) -> str:
        """The whole assumption, for `Call.derived` and the audit afterwards."""
        return (f"[DERIVED] {self.driver}'s {self.compound}: "
                f"{self.laps_on_set:.0f} laps on the set since his stop, "
                f"x our {self.compound} rate {self.rate:.3f} worn/lap "
                f"({self.samples} stint{'' if self.samples == 1 else 's'}) = "
                f"{self.worn_now:.0%} now, the cliff ({CLIFF_WORN:.0%}) at "
                f"lap key {self.cliff_key:.1f}. [ASSUMED] his car wears the "
                f"set as ours does; [ASSUMED] he went back out on the "
                f"compound the disc showed at his stop, which on the one stop "
                f"calibrated reads the tyres he ARRIVED on")


def full_code(letter: str | None, our_compound: str | None) -> str | None:
    """`"M"` + the race's family (`"RH"` -> `"R"`) -> `"RM"`, or None.

    The disc is one letter; our wear model is keyed by the whole code. The
    family comes from this race's own tyres, because a field on Racing tyres
    is on Racing tyres. Refused where either half is missing (rule 3).
    """
    if not letter:
        return None
    letter = str(letter).upper()
    if letter not in _DRY_LETTERS:
        return letter if len(letter) == 2 else None
    ours = (our_compound or "").upper()
    # **The FAMILY decides, not the last letter.** `IM` ends in M, so testing
    # only the letter read an intermediate race as a dry family and turned a
    # medium disc into "IM" - an intermediate's wear rate, applied to a
    # slick.
    if (len(ours) != 2 or ours[0] not in _DRY_FAMILIES
            or ours[1] not in _DRY_LETTERS):
        return None
    return f"{ours[0]}{letter}"


def rival_tyres(rival, *, now_key: int | None, our_compound: str | None,
                wear_rate) -> RivalTyres | None:
    """`rival`'s set as our model sees it, or None where it cannot be said.

    `wear_rate(compound) -> (rate, samples)` is `Knowledge.wear_per_lap` with
    the race's multiplier bound in - injected so this stays a pure function
    of what was read, and so the multiplier refusal stays in one place.

    None, not a guess, for every missing input: no stop seen, no compound
    read, no rate on file for that compound here, or a rate of nothing.
    """
    stop = getattr(rival, "stop", None)
    if stop is None or stop.lap is None or now_key is None:
        return None
    code = full_code(getattr(stop, "compound", None), our_compound)
    if code is None:
        return None
    try:
        rate, samples = wear_rate(code)
    except Exception:                                       # noqa: BLE001
        return None
    if not rate or rate <= 0:
        return None
    laps_on_set = float(now_key) - float(stop.lap)
    if laps_on_set < 0:
        # A stop filed ahead of now is a reading in another lap domain, not
        # a set with negative laps on it (rule 9).
        return None
    return RivalTyres(
        driver=str(getattr(rival, "name", None) or "he"),
        compound=code, laps_on_set=laps_on_set, rate=float(rate),
        samples=int(samples or 0),
        worn_now=float(rate) * laps_on_set,
        cliff_key=float(stop.lap) + CLIFF_WORN / float(rate))
