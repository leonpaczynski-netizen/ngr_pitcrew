"""Whether it can rain in this race, and what that means for the plan.

Two things decide it, and only one of them is about the circuit:

* **The league's rule.** Fixed weather is a regulation - the V8 rounds run
  sunny whatever the circuit offers, so no circuit's rain matters there.
  Random weather hands the decision to the circuit.
* **The circuit's capability.** GT7 only implements rain where Polyphony
  thought it realistic; most circuits cannot produce it at all.

**This cannot be measured.** GT7 broadcasts no weather channel in any packet
format - no rain flag, no wetness, nothing - so unlike the game clock there is
nothing in the stream to read it off or to check a claim against. The two
community lists that exist agree exactly with each other and are both from
August 2022, four years and many circuits ago. So the app seeds the question
and the **driver answers it**; his answer is what the model uses.

What follows from the answer is deliberately not a prediction:

* **Rain impossible** - wet compounds are irrelevant. Say so once and stop
  carrying them through the plan, the compound list and the driver's attention.
* **Rain possible** - it still cannot be planned for. GT7's weather cannot be
  known before the race, so a stint on Intermediates remains a stint on
  nothing. What changes is that **no wet running on record becomes an evidence
  gap**, the same shape as never having driven the race's time of day: not a
  plan, a thing to go and drive.
"""
from __future__ import annotations

import json
import pathlib

RULE_FIXED = "Fixed"
RULE_RANDOM = "Random"
WEATHER_RULES = (RULE_FIXED, RULE_RANDOM)

_DATA = pathlib.Path(__file__).resolve().parents[2] / "data" / "gt7_track_weather.json"


def _seed() -> dict:
    try:
        return json.loads(_DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def rain_seed(track: str | None) -> bool | None:
    """The community's answer for this circuit, or None where it has none.

    None is not "no rain". Most circuits added since 2022 are simply absent,
    and treating absence as a dry circuit would quietly retire the wet
    contingency at every one of them.
    """
    if not track:
        return None
    listed = _seed().get("rainPossible") or []
    name = track.strip().lower()
    for entry in listed:
        candidate = entry.strip().lower()
        if candidate in name or name in candidate:
            return True
    return None


def seed_source() -> str:
    data = _seed()
    return (f"{data.get('source', 'unknown')} ({data.get('sourceDate', '?')}). "
            f"{data.get('caveat', '')}").strip()


def can_rain(rule: str | None, rain_possible: bool | None) -> bool | None:
    """Can this race produce rain? None when the circuit's answer is unknown."""
    if rule == RULE_FIXED:
        return False
    if rain_possible is None:
        return None
    return bool(rain_possible)


def wet_evidence(rule: str | None, rain_possible: bool | None,
                 wet_laps: int, track: str | None = None) -> dict:
    """What the weather rule means for the plan, and what is missing.

    `wet_laps` is how many laps have ever been run on a wet compound.
    """
    possible = can_rain(rule, rain_possible)
    circuit = track or "this circuit"

    if possible is False:
        return {
            "canRain": False,
            "note": (
                f"Rain cannot happen in this race"
                + (" - the round runs a fixed weather setting"
                   if rule == RULE_FIXED
                   else f" - {circuit} cannot produce it")
                + ". Wet compounds are irrelevant here and are left out of the "
                  "plan entirely."),
        }

    if possible is None:
        hint = rain_seed(track)
        seeded = (
            f" A community list has {circuit} down as rain-capable, but it is "
            f"from 2022 and incomplete by its own admission, so it is a hint "
            f"and not the answer."
            if hint else
            f" {circuit} is not on the 2022 community list of rain-capable "
            f"circuits - which is four years and many circuits old, so its "
            f"silence is not a no.")
        return {
            "canRain": None,
            "seedSaysRain": hint,
            "note": (
                f"Whether {circuit} can produce rain is not declared, and it "
                f"cannot be measured - GT7 broadcasts no weather channel at "
                f"all. Answer it on the event page: under random weather it "
                f"decides whether a wet contingency is worth anything here."
                + seeded),
        }

    if wet_laps > 0:
        return {
            "canRain": True,
            "wetLaps": wet_laps,
            "note": (
                f"Rain is possible at {circuit} under random weather, and "
                f"there are {wet_laps} laps of wet running on record. It still "
                f"cannot be planned for - GT7's weather is not knowable before "
                f"the race - so the wets stay out of the stint plan and stay "
                f"available as a live call."),
        }

    return {
        "canRain": True,
        "wetLaps": 0,
        "note": (
            f"Rain is possible at {circuit} under random weather, and **no wet "
            f"running has ever been recorded**. The plan is unaffected - the "
            f"weather cannot be known in advance, so wets are never planned - "
            f"but if it rains, every call from that point is being made on a "
            f"tyre nobody has driven. One short run on Intermediates closes "
            f"it."),
    }
