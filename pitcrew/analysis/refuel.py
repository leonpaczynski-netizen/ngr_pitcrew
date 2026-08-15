"""How fast the car actually takes fuel, measured rather than typed.

**This is the number that decides the Monza race.** The tank holds 100 L and
the rate on the event page is 1.0 L/s, so a full stop is 73 seconds of standing
still — against 19 s of pit loss and 7.5 s of dead time. The refuel dominates
the stop, the stop dominates the stop count, and the stop count is the plan.

It has never been measured. It is a figure the driver typed into a form, and
`build_inputs` has been handing it to the model as though it came off the car.

It is measurable, and only from the stream: GT7 broadcasts the fuel level at
60 Hz, so a stop is a window where the level climbs. Nothing else in the feed
marks a pit stop — there is no stop event, no pit-lane flag that survives
every packet format — so the rise in the tank is both the detector and the
measurement.

**It needs a stop to have happened with the app recording.** Refuelling in the
garage between sessions does not count and cannot be seen: the recorder is
stopped, and the tank simply reads full again next time. So the honest output
where there is no stop on record is a refusal that says what to drive, not a
figure carried over from the form.
"""
from __future__ import annotations

from statistics import median

from pitcrew.analysis.session import LapInput

# Below this the tank did not move enough to time. Float noise on a channel in
# litres is a few hundredths; a splash worth measuring is litres.
MIN_FUEL_TAKEN_L = 5.0

# A rise separated by more than this is a second stop, not the same one.
MAX_GAP_MS = 2_000.0

# Sanity bounds. GT7's slowest refuelling is a little under 1 L/s and its
# fastest a little over 10; anything outside this is a channel glitch or a
# lap boundary landing inside a stop, and a plan built on it would be absurd.
MIN_PLAUSIBLE_LPS = 0.2
MAX_PLAUSIBLE_LPS = 25.0


def refuel_windows(lap: LapInput) -> list[dict]:
    """Every window inside one lap where the tank was filling.

    A window is contiguous in time: the level climbs, frame after frame, and a
    break longer than `MAX_GAP_MS` starts a new one.
    """
    frames = [frame for frame in (lap.frames or ())
              if frame.get("fuel_l") is not None and frame.get("t_ms") is not None]
    if len(frames) < 2:
        return []

    windows: list[dict] = []
    current: dict | None = None
    for previous, frame in zip(frames, frames[1:]):
        rising = frame["fuel_l"] > previous["fuel_l"]
        gap = frame["t_ms"] - previous["t_ms"]
        if rising and gap <= MAX_GAP_MS:
            if current is None:
                current = {"startMs": previous["t_ms"],
                           "startL": previous["fuel_l"]}
            current["endMs"] = frame["t_ms"]
            current["endL"] = frame["fuel_l"]
        elif current is not None:
            windows.append(current)
            current = None
    if current is not None:
        windows.append(current)

    out = []
    for window in windows:
        litres = window["endL"] - window["startL"]
        seconds = (window["endMs"] - window["startMs"]) / 1000.0
        if litres < MIN_FUEL_TAKEN_L or seconds <= 0:
            continue
        rate = litres / seconds
        if not MIN_PLAUSIBLE_LPS <= rate <= MAX_PLAUSIBLE_LPS:
            continue
        out.append({
            "lap": lap.lap_num,
            "litres": round(litres, 2),
            "seconds": round(seconds, 2),
            "rateLps": round(rate, 3),
        })
    return out


def measure_refuel_rate(laps: list[LapInput]) -> dict | None:
    """Litres per second, from every stop on record. None when there are none.

    Median across stops rather than mean: one stop cut short by a lap boundary
    should not move the figure the whole race is planned on.
    """
    stops = [window for lap in laps for window in refuel_windows(lap)]
    if not stops:
        return None
    return {
        "rateLps": round(median([stop["rateLps"] for stop in stops]), 3),
        "stopsMeasured": len(stops),
        "stops": stops,
        "source": "measured-from-the-fuel-channel",
    }


def refuel_evidence(laps: list[LapInput], declared_lps: float | None) -> dict:
    """The rate to plan with, and where it came from.

    The driver's typed figure is used when nothing has been measured, because
    a plan still has to be built — but it is labelled `declared`, and where the
    two disagree the disagreement is reported rather than resolved. His figure
    is a claim about the car; the stream is a record of it.
    """
    measured = measure_refuel_rate(laps)
    if measured is None:
        return {
            "rateLps": declared_lps,
            "source": "declared",
            "note": (
                "The refuel rate has never been measured. It is the number "
                "typed on the event page, and at 100 L it sets a full stop at "
                f"{(100.0 / declared_lps):.0f} s if it is right - which is "
                "most of the stop and therefore most of the plan. To measure "
                "it: make one pit stop in practice, taking fuel, with the app "
                "recording."
                if declared_lps else
                "The refuel rate has never been measured and none is declared, "
                "so no stop can be costed."),
        }

    payload = {
        "rateLps": measured["rateLps"],
        "source": measured["source"],
        "stopsMeasured": measured["stopsMeasured"],
    }
    if declared_lps and abs(measured["rateLps"] - declared_lps) > 0.1:
        payload["note"] = (
            f"Measured {measured['rateLps']:.2f} L/s across "
            f"{measured['stopsMeasured']} stop"
            f"{'' if measured['stopsMeasured'] == 1 else 's'}, against "
            f"{declared_lps:.2f} L/s declared on the event page. The measured "
            f"figure is used. On a 100 L tank the two differ by "
            f"{abs(100.0 / measured['rateLps'] - 100.0 / declared_lps):.0f} s "
            f"a stop.")
    return payload
