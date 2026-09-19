"""The tablet page: what everyone is doing, as words and figures to draw.

The tablet left of the wheel (17 Sep 2026) leads with the timing tower and
carries, per car, the lap he pitted, his fuel in and out, and whether his fuel
says one stop or two. `race/field.py` works that out; this module words it;
`tablet.html` only draws it - the same division the phone strip is built on,
so a page cannot word a car two ways (rule 13).

**Every figure says how much it is worth.** A board read that is a moment
behind says its age. An exit fuel that is only a lower bound is drawn "≥50",
never "50". A prediction inside the reading error ends in "?". A prediction
made on OUR burn because his was never measured says so. None of those is a
decoration: each is the difference between a fact and an assumption, and the
driver acts differently on the two (rules 3 and 5).
"""
from __future__ import annotations

from pitcrew.race.field import (
    BOARD_FRESH_S, NO_STOP_SEEN, REACHES_FLAG, SHORT_SAVES, STOPS_AGAIN,
    FieldView)

PAYLOAD_VERSION = 1

# **How many rows the tablet draws.** Past this it is a table to read, and he
# is driving: the rows nearest his place are kept, the rest dropped from the
# far end, and the page says how many were left off rather than scrolling.
MAX_ROWS = 12


def _stops(count: int | None) -> str:
    if count is None:
        return ""
    return f"{count} STOP" + ("" if count == 1 else "S")


def prediction_words(prediction) -> tuple[str, str, str]:
    """`(headline, detail, tone)` for one car's stop picture.

    The tone is what it means FOR US, in the only two readings that matter -
    a car that must stop again ("stops") and one that will not ("reaches") -
    and plain for everything the app cannot say.
    """
    if prediction is None:
        return "", "", "plain"
    maybe = "?" if prediction.unconfirmed else ""
    # **Both burns are named, and his carries its count** (rule 4). Only ours
    # was marked, so "his burn" was the unmarked default - the reassuring
    # case, resting on the weakest evidence, and the one figure on the row
    # with nothing saying how much of it there was. One stop is one stint's
    # worth of evidence about a driver who may have been saving.
    if prediction.burn_of == "ours":
        burn = " · our burn"
    elif prediction.burn_of == "his":
        stops = prediction.burn_stops
        burn = (f" · his burn, {stops} stop{'' if stops == 1 else 's'}"
                if stops else " · his burn")
    else:
        burn = ""
    if prediction.words == STOPS_AGAIN:
        return (f"{_stops(prediction.total_stops)}{maybe}",
                f"in by L{prediction.reaches_lap}{burn}", "stops")
    if prediction.words == REACHES_FLAG:
        # **Whether he can push, not only whether he gets there.** A car with
        # the fuel to go harder and a car holding his rate to the last litre
        # both "reach the flag", and they are opposite answers to "can he come
        # after me?". The spare is said as fuel to push only where it is
        # bigger than the reading error - otherwise it is "just enough", which
        # is the honest word for a margin we cannot resolve.
        # Sized to the column: the longest of these with its burn suffix is
        # 38 characters, which is what the opinion column holds unclipped.
        if prediction.spare_readable and prediction.spare_l is not None:
            reach = f"{prediction.spare_l:.0f} L to push"
        else:
            reach = "no fuel to push"
        return (f"{_stops(prediction.total_stops)}{maybe}",
                f"{reach}{burn}", "reaches")
    if prediction.words == SHORT_SAVES:
        # The voice's own hedge, not a stop count: "he lifts or he stops
        # again" is what the app can stand behind, and `total_stops` is None
        # here for that reason. "LIFTS?" reads as the question it is.
        return (f"{_stops(prediction.stops_seen)} SO FAR",
                f"short - lifts or stops again{burn}", "plain")
    if prediction.words == NO_STOP_SEEN:
        # About the instrument, not the car: the board may simply not have
        # been read while he was in the lane.
        return "NONE SEEN", "no stop read", "plain"
    return "CAN'T TELL", prediction.why or "", "plain"


def _fuel(car) -> str:
    """`8 → 50`, `8 → ≥30` for a bound, or what was read of it."""
    if car.fuel_in_l is None and car.fuel_out_l is None:
        return ""
    # `<=` on the entry for the same reason `>=` marks the exit: a figure
    # read after the fill started bounds what he arrived with, it does not
    # measure it (rule 5, and `boxed_call` refuses to SAY it at all).
    inward = "≤" if getattr(car, "in_is_bound", False) else ""
    fuel_in = ("?" if car.fuel_in_l is None
               else f"{inward}{car.fuel_in_l:.0f}")
    if car.fuel_out_l is None:
        return f"{fuel_in} → ?"
    bound = "≥" if car.out_is_bound else ""
    return f"{fuel_in} → {bound}{car.fuel_out_l:.0f}"


def _window(rows, ours: int | None) -> tuple[list, int]:
    """The rows nearest his place, and how many were left off."""
    placed = [row for row in rows if row.place is not None]
    unplaced = [row for row in rows if row.place is None]
    if ours and len(placed) > MAX_ROWS:
        placed.sort(key=lambda row: (abs(row.place - int(ours)), row.place))
        placed = sorted(placed[:MAX_ROWS], key=lambda row: row.place)
    kept = (placed + unplaced)[:MAX_ROWS]
    return kept, len(rows) - len(kept)


def compose(view: FieldView | None) -> dict:
    """The whole payload. `None` is no session - the page says so (rule 11)."""
    if view is None:
        return {"v": PAYLOAD_VERSION, "idle": True}
    rows, left_off = _window(list(view.rows), view.position)
    drawn = []
    for car in rows:
        headline, detail, tone = prediction_words(car.prediction)
        drawn.append({
            "place": "" if car.place is None else f"P{car.place}",
            "name": "YOU" if car.us else (car.name or "-"),
            "us": car.us,
            "gap": "" if car.gap_s is None else f"{car.gap_s:.1f}",
            "lane": car.in_lane,
            "stop": "" if car.last_stop_lap is None else f"L{car.last_stop_lap}",
            "fuel": _fuel(car),
            "prediction": headline,
            "detail": detail,
            "tone": tone,
        })
    age = view.board_age_s
    return {
        "v": PAYLOAD_VERSION,
        "idle": False,
        "kind": "race",
        # "/ ~30" where the distance is the plan's estimate: the tilde is
        # the hedge the voice says as "about", and it is the number every
        # prediction below is divided by.
        "lap": ("" if view.lap is None else
                f"LAP {view.lap}" + (
                    f" / {'~' if view.laps_total_hedged else ''}"
                    f"{view.laps_total}" if view.laps_total else "")),
        "position": ("" if view.position is None else
                     f"P{view.position}" + (f" of {view.field_size}"
                                            if view.field_size else "")),
        "board": ("board not read yet" if age is None
                  else f"board read {age:.0f} s ago"),
        "board_stale": age is None or age > BOARD_FRESH_S,
        # The seconds themselves, not only the sentence: the page walks the
        # heads' ink toward struck across them, so a read going cold is
        # visible before it is refused. None is "no read", which is the far
        # end of that walk rather than the near one.
        "board_age_s": age,
        "rows": drawn,
        "left_off": left_off,
        "why": view.why or ("" if drawn else "no other car read yet"),
    }
