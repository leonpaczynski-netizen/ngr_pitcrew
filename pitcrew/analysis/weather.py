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


def _matches(candidate: str, name: str) -> bool:
    candidate, name = candidate.strip().lower(), name.strip().lower()
    return candidate in name or name in candidate


def rain_seed(track: str | None,
              layout: str | None = None) -> tuple[bool | None, str]:
    """Can this circuit rain, and on whose authority.

    Three tiers, strongest first:

    * **confirmed** - checked in the game by the driver. Nothing outranks it;
    * **listed** - the wiki's per-layout table, which is complete for the
      circuits it covers, so a circuit in it with no rain layout genuinely
      cannot rain;
    * **unknown** - a circuit added since the table was read. Not "dry":
      treating absence as a dry circuit would quietly retire the wet
      contingency at every new one.

    Rain is a property of the **layout**, not the track. Dragon Trail Gardens
    rains and Seaside does not; Tokyo Expressway Central and East rain and
    South does not. The older community lists missed that entirely.
    """
    if not track:
        return None, "no circuit named"
    data = _seed()

    for name, entry in (data.get("confirmed") or {}).items():
        if _matches(name, track):
            return bool(entry.get("rain")), (
                f"confirmed in game by the driver, {entry.get('date', 'undated')}")

    for name, layouts in (data.get("rainByTrack") or {}).items():
        if not _matches(name, track):
            continue
        if layout and not any(_matches(one, layout) for one in layouts):
            return False, (
                f"{track} can rain, but not on the {layout} layout - the "
                f"wiki's table is per layout")
        return True, "the GT Wiki track list, read 2026-08-13"

    for name in data.get("noRain") or []:
        if _matches(name, track):
            return False, "the GT Wiki track list, read 2026-08-13"

    return None, (
        "not on the GT Wiki track list read 2026-08-13 - a circuit added "
        "since, so unknown rather than dry")


def can_rain(rule: str | None, rain_possible: bool | None,
             track: str | None = None,
             layout: str | None = None) -> tuple[bool | None, str]:
    """Can this race produce rain, and on whose authority.

    The league's rule comes first and can settle it on its own: a round run to
    a fixed weather setting cannot rain whatever the circuit offers.
    """
    if rule == RULE_FIXED:
        return False, "the round runs a fixed weather setting"
    if rain_possible is not None:
        return bool(rain_possible), "declared on the event page"
    return rain_seed(track, layout)


def wet_evidence(rule: str | None, rain_possible: bool | None,
                 wet_laps: int, track: str | None = None,
                 layout: str | None = None) -> dict:
    """What the weather rule means for the plan, and what is missing.

    `wet_laps` is how many laps have ever been run on a wet compound.
    """
    possible, authority = can_rain(rule, rain_possible, track, layout)
    circuit = track or "this circuit"

    if possible is False:
        return {
            "canRain": False,
            "source": authority,
            "note": (
                f"Rain cannot happen in this race - {authority}. Wet compounds "
                f"are irrelevant here and are left out of the plan entirely."),
        }

    if possible is None:
        return {
            "canRain": None,
            "source": authority,
            "note": (
                f"Whether {circuit} can produce rain is unknown - {authority} - "
                f"and it cannot be measured, because GT7 broadcasts no weather "
                f"channel at all. Answer it on the event page: under random "
                f"weather it decides whether a wet contingency is worth "
                f"anything here."),
        }

    if wet_laps > 0:
        return {
            "canRain": True,
            "source": authority,
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
        "source": authority,
        "wetLaps": 0,
        "note": (
            f"Rain is possible at {circuit} under random weather, and **no wet "
            f"running has ever been recorded**. The plan is unaffected - the "
            f"weather cannot be known in advance, so wets are never planned - "
            f"but if it rains, every call from that point is being made on a "
            f"tyre nobody has driven. One short run on Intermediates closes "
            f"it."),
    }
