"""The tablet page: what everyone is doing, as words and figures to draw.

The tablet left of the wheel (17 Sep 2026) leads with the timing tower and
carries, per car, the lap he pitted, his fuel in and out, and whether his fuel
says one stop or two. `race/field.py` works that out; this module words it;
`tablet.html` only draws it - the same division the phone strip is built on,
so a page cannot word a car two ways (rule 13).

**Every figure says how much it is worth.** A board read that is a moment
behind says its age. An exit fuel that is only a lower bound is drawn "≥50",
never "50". A prediction inside the reading error ends in "?". A prediction
made on OUR burn because his was never measured says so. A gap the reader
has lost draws "--" rather than the last figure it had. None of those is a
decoration: each is the difference between a fact and an assumption, and the
driver acts differently on the two (rules 3 and 5).

**And a second face, for practice** (his ask, 20 Sep 2026). There is no field
in practice - `field.py` needs a race - so this page was a cover and three
inert buttons while the app's only practice instrument sat on the monitor,
which now carries the lap rack instead. `compose_practice` words the practice
board for it; `compose` above is untouched and still owns the race.
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

# **What a car the app cannot name is called here.** Not a name, not a
# number, and deliberately not plausible as either - the store's own
# `identity.unknown_car_name` mints "Unknown car #N" for exactly this
# reason: *"the one thing it must never do is get mistaken for an
# identification"*.
UNNAMED = "NOT NAMED"


def driver_words(car) -> tuple[str, bool]:
    """The Driver column's words for one car, and whether they name a person.

    **A minted handle is not a name, and it was drawn as one.** `Car #164` is
    `Store.provisional_driver_name`'s global counter - not the car's race
    number, not anything on his screen - and this column printed it in the
    same ink, the same case and the same column as `PUNISHED`. On the 20 Sep
    race that was 25 of 27 rows, and he asked where the numbers came from.

    Every other channel already tells these apart: `news.a_person` is the gate
    the voice uses and returns `None` for a minted handle *or a bare numeric
    subject*, and `news` states the doctrine - a handle "is said as *the car
    ahead* or *the car behind*: it is not a person." This is that same gate,
    on the one surface that never consulted it (rules 3 and 13).

    **The row stays.** A car whose row was read is on the board whether or not
    the app can name him, and his place, his stop and his fuel are all facts
    about him - dropping the row would lose those to a naming failure. Only
    the word changes, and the flag lets the page ink it as the absence it is.
    """
    from pitcrew.race.news import a_person

    if car.us:
        return "YOU", True
    person = a_person(car.name)
    if person is not None:
        return person, True
    return UNNAMED, False


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
        # **"on the limit", not "no fuel to push"** (critic, 19 Sep). A spare
        # inside the reading error is one we cannot resolve - the true figure
        # could be up to twice the error - so "no fuel" asserted a zero the
        # instrument cannot see (rule 3). "On the limit" is what the point
        # estimate says, and it is Rocky at Sardegna exactly: 2.2 L over 15
        # laps, holding his rate.
        if prediction.spare_readable and prediction.spare_l is not None:
            reach = f"{prediction.spare_l:.0f} L to push"
        else:
            reach = "on the limit"
        return (f"{_stops(prediction.total_stops)}{maybe}",
                f"{reach}{burn}", "reaches")
    if prediction.words == SHORT_SAVES:
        # The voice's own hedge, not a stop count: "he lifts or he stops
        # again" is what the app can stand behind, and `total_stops` is None
        # here for that reason. "LIFTS?" reads as the question it is.
        # Shortened to fit: "short - lifts or stops again · his burn, 2
        # stops" was 47 characters in a 38-character column, and the half it
        # lost was the evidence count (rule 4). The headline already says he
        # is short; the detail says what that means.
        return (f"{_stops(prediction.stops_seen)} SO FAR",
                f"lifts or stops{burn}", "plain")
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


# The sessions that get the practice face. A race has a field to draw and
# takes `compose` above; anything else has no field at all (`field.py` needs
# a race), which is why the tablet was a cover and three inert buttons.
PRACTICE_KINDS = ("practice", "qualifying")


def _figure(caption: str, block) -> dict:
    """One captioned figure, in the strip's own shape - so the two pages draw
    a register the same way and neither decides what a number IS."""
    return {"caption": caption, "value": block.value, "sub": block.sub,
            "tone": block.tone, "register": block.register}


def compose_practice(state) -> dict:
    """The practice board, for the tablet. `None` is no such session.

    His ask, 20 Sep 2026: *"in practice board on monitor should move to
    tablet as it has nothing on it"*. Outside a race the tablet drew a cover
    saying "no race running" while the monitor carried the only practice
    instrument in the app - and the monitor is now the lap rack.

    **What is on it, and why those and not others.** This is the monitor's
    practice board, worded here instead of drawn there:

    * **The four corners.** His own first request for this display, and the
      one reading GT7 does not show him anywhere.
    * **The three sectors.** The one thing that leaves the monitor entirely
      when it turns to the rack - the rack keeps the corners, the phone keeps
      the lap face, nothing else keeps these. GT7 sends no sectors, so the
      line under them names whose cut they are.
    * **The lap face** - last lap, the best on file, the live delta to it -
      and the three lamps. These are on the phone too, and deliberately: they
      come from the same three expressions, so the two surfaces cannot word
      one lap two ways (rule 13).

    **Nothing else, because there is nothing else.** There is no field, no
    plan, no target lap and no target burn in practice, and a payload that
    invented any of them would be rule 3 at the top of the screen. The rack
    itself is not here either - it is on the monitor, which is what he asked
    for, and two racks are two places to read one thing.

    **Python decides the words; `tablet.html` only draws them** - the same
    division `strip.py` is built on. `classify` and `pair_gap` stay here and
    the page gets their answer, so no temperature rule is re-derived in
    JavaScript against a threshold nobody re-checked.
    """
    if state is None or state.session_kind not in PRACTICE_KINDS:
        return {"v": PAYLOAD_VERSION, "idle": True}
    from pitcrew.ui.driver_view import (
        CORNERS, PAIRS, abs_light, classify, face_best_block,
        face_delta_block, face_lap_block, face_last_block, pair_gap,
        sector_blocks, tcs_light, tyre_caption_words, wet_light)
    # The phone's own list, not a second copy of it: the two pages draw the
    # same three lamps and a lamp "unread" on one and dark on the other is
    # the same instrument saying two things (rule 13). Imported here rather
    # than at module scope so this module still costs no Qt to import.
    from pitcrew.ui.strip import UNREAD_LIGHT

    temps = state.temps_c or {}
    rates = state.split_rates or {}
    tyres = []
    for corner in CORNERS:
        reading, lopsided = classify(corner, temps, state.compound)
        gap = pair_gap(corner, temps)
        # **Only where it is a finding**, exactly as `_Tyre` has it: a gap
        # under the threshold would be a small figure he has to decide about
        # at 200 km/h, and the direction is silent where the laps do not say
        # it yet - no rate is not a rate of zero.
        rate = rates.get(corner)
        if not lopsided or gap is None:
            words, tone = "", "plain"
        else:
            trend = ("" if rate is None else
                     "  WIDENING" if rate > 0 else "  SETTLING")
            words = f"+{gap:.0f} vs {PAIRS[corner].upper()}{trend}"
            tone = "good" if rate is not None and rate <= 0 else "near"
        value = temps.get(corner)
        tyres.append({"corner": corner.upper(),
                      # A dash, never a zero: a corner with no reading is an
                      # instrument that cannot see it (rule 3).
                      "value": "--" if value is None else f"{value:.0f}",
                      "state": reading, "gap": words, "gap_tone": tone})

    sectors, sector_note = sector_blocks(state)
    best_caption, best = face_best_block(state)
    delta_caption, delta = face_delta_block(state)
    lights = [wet_light(state.wet),
              abs_light(state.abs_setting, state.front_lock),
              tcs_light(state.tcs_active)]
    return {
        "v": PAYLOAD_VERSION,
        "idle": False,
        "kind": "practice",
        # Which session this is, in his own words: a qualifying run and a
        # practice run are not the same session and the delta on the face
        # below is against the same reference in both.
        "session": state.session_kind.upper(),
        "lap": f"LAP {face_lap_block(state).value}",
        "faces": [_figure("LAST LAP", face_last_block(state)),
                  _figure(best_caption, best),
                  _figure(delta_caption, delta)],
        "tyres": tyres,
        "tyre_caption": tyre_caption_words(state),
        "sectors": [{"value": block.value, "sub": block.sub,
                     "tone": block.tone} for block in sectors],
        "sector_note": sector_note,
        # `unread` is the lamp helpers' own distinction: "no reading" and "no
        # signal" are the instrument saying it cannot see, where "no lock"
        # and "" are measured negatives (rule 3). The page cannot tell them
        # apart from the word alone - `strip.py` carries the same flag.
        "lights": [{"word": word.upper(), "sub": sub, "ink": ink,
                    "unread": sub in UNREAD_LIGHT}
                   for word, sub, ink in lights],
        # Per-compound best laps (Story 3, 25 Sep 2026).  The fastest compound
        # seen today sits at index 0; the page draws one row per entry.  The
        # key is absent rather than `[]` when `compound_bests` is None (no
        # board state to read from) so the page can tell "nothing computed"
        # from "computed and empty" - the latter is a session with laps but no
        # compound reads, which is itself a finding (rule 3).
        **({"compound_bests": [
            {"compound": e["compound"],
             "best_ms": e["best_ms"],
             "lap_count": e["lap_count"]}
            for e in (getattr(state, "compound_bests", None) or [])
        ]} if getattr(state, "compound_bests", None) is not None else {}),
    }


def _laps_block(state, view) -> "dict | None":
    """Laps figure for the own-car block: to the stop or to the flag.

    When a stop is still to come (`state.laps_to_box` is not None and the
    plan is running), the value and tone come VERBATIM from `box_block(state)`
    — the same Block that fills ``own.box`` in `compose()`.  One expression
    for the stop countdown (rule 13): the board may not re-derive a second
    tone threshold or produce a different string for the same lap count.  On
    the in-lap `box_block` returns ``"NOW"``; this block carries that too, so
    ``own.laps.value`` is never ``"0"`` (rule 3).

    When the plan has no further stop (`laps_to_box` is None but `has_plan`
    is True), the figure is the laps remaining to the flag from
    `view.own_laps_remaining` with label ``"to the flag"``.  None in all
    other cases (no plan, no state, finished).

    **The race-finished guard (I-B, 25 Sep 2026).** When `state.finished` is
    True, `laps_remaining()` returns 0 and this function would emit
    ``{"value": "0", "label": "to the flag"}`` — a zero that looks like a
    measurement (rule 3) and hides the "FLAG" word `box_block` already
    provides.  Return None instead; the page falls back to `own.box`, which
    `box_block` has worded for the finish.  The same guard catches the short
    window at the final crossing where `laps_remaining()==0` and
    `finished==False` — that state is also one `box_block` already names.

    `view.own_laps_remaining` is `state.laps_remaining()` filed by
    `field_view()` — the same call the voice makes; the board may not
    derive a second one (rule 13).
    """
    if state is None:
        return None
    # Finished race: box_block says "FLAG"; this block would say "0 to the
    # flag" — a zero that is not a count (rule 3).  Return None.
    if getattr(state, "finished", False):
        return None
    has_plan = bool(getattr(state, "has_plan", False))
    laps_to_box = getattr(state, "laps_to_box", None)
    if not has_plan:
        return None
    if laps_to_box is not None:
        # Stop still to come (including the in-lap where laps_to_box == 0.0):
        # take value and tone VERBATIM from box_block — the one expression for
        # the stop countdown.  On the in-lap box_block returns "NOW"; this
        # block carries that too, so own.laps.value is never "0" (rule 3).
        # `box_block` is imported here, not at module scope, to avoid a Qt
        # import cost (same pattern as `compose`).
        from pitcrew.ui.driver_view import box_block
        bb = box_block(state)
        return {"value": bb.value, "label": "to the stop", "tone": bb.tone}
    # No further stop: how many laps to the flag.
    own_laps_remaining = getattr(view, "own_laps_remaining", None)
    if own_laps_remaining is None:
        return None
    # Guard zero: at the final crossing `laps_remaining()` becomes 0 before
    # `finished` is set.  "0 to the flag" is not a useful instruction and
    # would hide box_block's own last-lap word (rule 3 and rule 13).
    if own_laps_remaining <= 0:
        return None
    return {"value": str(own_laps_remaining), "label": "to the flag",
            "tone": "plain"}


def _gap_block(own_gap) -> dict | None:
    """One side of the own-car gap, as the payload shape the brief specifies.

    Returns None when the argument is None (P1 has no car ahead; last has
    none behind).  The page renders null as "not applicable" rather than as
    a dash that would look like a missed reading.

    `name` is the resolved display name of the neighbouring car (None at
    P1/last or when the board has not yet been read).
    """
    if own_gap is None:
        return None
    return {
        "gap_s": own_gap.gap_s,
        "unread": own_gap.unread,
        "trend": own_gap.trend,
        "rate_s_per_lap": own_gap.rate_s_per_lap,
        "name": getattr(own_gap, "name", None),
    }


def compose(view: "FieldView | None", state=None) -> dict:
    """The whole payload. `None` is no session - the page says so (rule 11).

    `state` is the `DriverState` built in the same tick, passed from the
    controller.  It is used for the own-car block: `temps_c` (comes off the
    packet, not off the race-state) and `box_block` (needs `laps_to_box`,
    `has_plan`, `finished`).  Without it the "own" key is omitted so the page
    can tell "no block built" from "block has no data" (rule 3).

    **One DriverState, passed in, not re-derived here.**  Building it a
    second time would mean the tyre temps on the tablet could differ from the
    ones on the phone, which is exactly the defect the comment at line 7683
    of controller.py was written to prevent (rules 12 and 13).
    """
    if view is None:
        return {"v": PAYLOAD_VERSION, "idle": True}
    rows, left_off = _window(list(view.rows), view.position)
    drawn = []
    for car in rows:
        headline, detail, tone = prediction_words(car.prediction)
        name, named = driver_words(car)
        gap_unread = bool(getattr(car, "gap_unread", False)) and car.gap_s is None
        drawn.append({
            "place": "" if car.place is None else f"P{car.place}",
            "name": name,
            # Presentation only: `field.py` still keys every row by
            # `car.name`, and the stop, the fuel and the prediction on this
            # row are all still his.
            "named": named,
            "us": car.us,
            # **A dash, never a stale number** (rule 3, and `field.py`'s
            # `gap_still_stands`). The gap is the one figure on this page he
            # acts on at racing speed: a figure read before the crossing, or
            # left behind by a board reader that has gone quiet, describes
            # the car he has already passed. So past the bound it is not
            # dimmed, it is withdrawn - and the cell says which of the two
            # silences it is, because an empty cell is also what a car with
            # no interval box draws and those are opposite claims.
            "gap": ("--" if gap_unread
                    else "" if car.gap_s is None else f"{car.gap_s:.1f}"),
            "gap_unread": gap_unread,
            "lane": car.in_lane,
            "stop": "" if car.last_stop_lap is None else f"L{car.last_stop_lap}",
            "fuel": _fuel(car),
            "prediction": headline,
            "detail": detail,
            "tone": tone,
        })
    age = view.board_age_s

    # ---- own-car block (Story 1, 25 Sep 2026) --------------------------------
    # Built only when a DriverState is passed in, so the test that builds just
    # a FieldView still gets a well-formed payload (rule 3: absent ≠ null ≠ 0).
    own = None
    if state is not None:
        from pitcrew.ui.driver_view import box_block
        from pitcrew.ui.driver_view import history_rows, fuel_in_hand_parts

        bb = box_block(state)
        temps = getattr(state, "temps_c", None)

        # **History rack: one expression for race laps (rule 13).** The same
        # `history_rows(kind="race")` the monitor uses, so the two surfaces
        # cannot show different lap times for the same lap.  The tablet renders
        # a compact version (time, delta, burn) below the big gap cards.
        hist_rows = history_rows(getattr(state, "history", None), kind="race")
        history_payload = [
            {
                "lap": r.lap,
                "time": r.time,
                "delta": r.delta,
                "burn": r.burn,
                "note": r.note,
                "delta_tone": r.delta_tone,
                "burn_tone": r.burn_tone,
            }
            for r in hist_rows
        ]

        # **Fuel-in-hand: one expression (rule 13).** The monitor uses
        # `fuel_in_hand_parts(state)` in the rack; we use exactly the same
        # call so the tablet and monitor cannot disagree.  Each item is
        # [words, ink] — the HTML page inks each part separately.
        fuel_parts = fuel_in_hand_parts(state)
        fuel_in_hand_payload = [
            {"words": words, "ink": ink}
            for words, ink in fuel_parts
        ]

        # George's last call text (one line for the header, spoken anyway).
        last_call_obj = getattr(state, "last_call", None)
        last_call_text = (
            getattr(last_call_obj, "text", None)
            if last_call_obj is not None else None
        )

        own = {
            # The gap to each immediate neighbour.  `_gap_block` returns None
            # at P1 / last place, which is the correct word for "no car there"
            # as opposed to "gap exists and is expired".
            "gap_ahead": _gap_block(getattr(view, "own_gap_ahead", None)),
            "gap_behind": _gap_block(getattr(view, "own_gap_behind", None)),
            # Tyre temps from the packet, not from the race state - same object
            # the phone draws from, so the two surfaces cannot disagree (rule 13).
            "temps_c": (None if temps is None
                        else {"fl": temps.get("fl"), "fr": temps.get("fr"),
                              "rl": temps.get("rl"), "rr": temps.get("rr")}),
            # Mean lap-delta and burn-delta over the current stint, DERIVED.
            # None when fewer than 2 qualifying laps - the count says so (rule 4).
            "stint_lap_delta_ms": getattr(view, "own_stint_lap_delta_ms", None),
            "stint_lap_laps": getattr(view, "own_stint_lap_laps", None),
            "stint_burn_delta_l": getattr(view, "own_stint_burn_delta_l", None),
            "stint_burn_laps": getattr(view, "own_stint_burn_laps", None),
            # The box countdown, verbatim from `box_block` - "NOW" on the
            # in-lap, never "0" (`box_block` is the one expression for it,
            # and rule 13 says the board and the page must agree).
            "box": {"value": bb.value, "sub": bb.sub, "tone": bb.tone},
            # **Laps figure: to the stop when one is still to come; to the
            # flag otherwise** (C1, 25 Sep 2026).  `laps_to_box` is the one
            # expression for "laps to the next stop" (rule 13); the flag
            # figure comes from `view.own_laps_remaining` which was filed by
            # `field_view()` from `state.laps_remaining()` - the same
            # expression the voice uses, so the board and the voice cannot
            # give two different numbers for laps left (rule 13).
            #
            # None when neither a stop nor a plan exists (no plan running),
            # never a zero or a dash (rule 3).
            "laps": _laps_block(state, view),
            # Race rack: my last laps with time, delta and burn, from the same
            # history_rows(kind="race") the monitor draws.
            "history": history_payload,
            # Fuel-in-hand: [[words, ink], ...] from fuel_in_hand_parts, the
            # same expression the monitor uses (rule 13).
            "fuel_in_hand": fuel_in_hand_payload,
            # George's last call, one line for the tablet header (spoken anyway).
            "last_call_text": last_call_text,
        }

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
        **({"own": own} if own is not None else {}),
    }
