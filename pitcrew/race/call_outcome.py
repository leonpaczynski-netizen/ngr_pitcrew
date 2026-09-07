"""What happened after the engineer said something, where the app can tell.

**The log of calls is the point of keeping one**, and it has been half a
record: every call carries what was said, why, and how sure — and nothing
carries what the driver then did. A call he acted on and a call he ignored are
both evidence about the model, and they are the two that most need telling
apart, because this driver has overruled the engineer and been right four
sessions running.

### Only two kinds can be answered, and the rest say so

The app may only report an outcome it can measure:

* **Box calls** — `laps.is_pit_lap` is measured, so "did a stop follow" is a
  fact. The window is the call's own lap and the two after it, because
  *"box this lap or next"* is the instruction and a stop three laps later is
  a different decision rather than a late compliance.
* **Short-shift calls** — `laps.short_shift_rpm` records whether the beep was
  actually moved on a lap, so the instruction and the response are both on
  file.

Everything else is `CANNOT_TELL`, **named rather than omitted**. A fuel-map
change, a brake-balance click and a lift-and-coast are not in any packet GT7
sends; reporting those as "not acted on" would turn a missing channel into a
disobedient driver, which is the exact shape of defect this project keeps
finding — a zero standing in for a measurement nobody took.

### It is not a score

Nothing here judges the driver, and the wording is chosen so a reader cannot
mistake it for that. `NOT_ACTED` on a box call is a finding about the CALL as
often as about the driver: at Fuji he ignored two box calls, ran to the flag
and finished P5, and the app's own binding-constraint figure was wrong. The
value of recording it is that the pair — what was said, what was done — can be
argued about afterwards with both halves present.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.race.calls import BOX_NOW, BOX_SOON

ACTED = "acted"
NOT_ACTED = "not-acted"
CANNOT_TELL = "cannot-tell"

# A box call means this lap or the next. A stop on the third lap after it is a
# decision he made later, not the call being obeyed slowly.
BOX_WINDOW_LAPS = 2

BOX_KINDS = frozenset({BOX_NOW, BOX_SOON})
# The short-shift instruction rides on `Call.short_shift_drop_rpm` rather than
# on a kind of its own, so it is recognised by the field being set.
SHORT_SHIFT_FIELD = "short_shift_drop_rpm"


@dataclass(frozen=True)
class Outcome:
    """What followed one call, and how that was established.

    `settled` says whether this is the final word: a `CANNOT_TELL` because
    the laps that answer the call have not been driven yet is provisional
    and is asked again at the next crossing; one because nothing in the
    feed can ever answer this kind of call is final.
    """
    verdict: str
    detail: str
    settled: bool = True

    @property
    def known(self) -> bool:
        return self.verdict != CANNOT_TELL

    def as_export(self) -> dict:
        return {"verdict": self.verdict, "detail": self.detail}


def _laps_after(call_lap: int, laps, window: int):
    return [lap for lap in laps
            if call_lap <= lap.lap_num <= call_lap + window]


def outcome_for(call, laps) -> Outcome:
    """What the driver did after this call, or an honest refusal.

    `laps` are the race's laps in order, each needing `lap_num` and whichever
    field the call's kind is judged on. A lap list that does not reach past
    the call is `CANNOT_TELL` rather than `NOT_ACTED` — the race may simply
    have ended, and "he did not box" about a call made on the last lap is a
    statement about the flag, not the driver.
    """
    laps = list(laps)
    kind = getattr(call, "kind", None)
    lap_num = getattr(call, "lap", None)
    if lap_num is None:
        return Outcome(CANNOT_TELL, "the call carries no lap number")

    if kind in BOX_KINDS:
        window = _laps_after(lap_num, laps, BOX_WINDOW_LAPS)
        if not window:
            return Outcome(CANNOT_TELL,
                           "no lap on file at or after the call - the race "
                           "may have ended on it", settled=False)
        stopped = [lap for lap in window if getattr(lap, "is_pit_lap", False)]
        if stopped:
            return Outcome(
                ACTED, f"pitted on lap {stopped[0].lap_num}, "
                       f"{stopped[0].lap_num - lap_num} lap(s) after the call")
        # Only where the window was actually driven. A truncated window says
        # nothing about a stop that had not come due yet.
        if len(window) <= BOX_WINDOW_LAPS:
            return Outcome(CANNOT_TELL,
                           f"only {len(window)} lap(s) followed the call, so "
                           f"the window it named was never fully driven",
                           settled=False)
        return Outcome(NOT_ACTED,
                       f"no stop on laps {lap_num}-{lap_num + BOX_WINDOW_LAPS}")

    if getattr(call, SHORT_SHIFT_FIELD, None):
        window = _laps_after(lap_num, laps, 1)
        if not window:
            return Outcome(CANNOT_TELL, "no lap on file at or after the call",
                           settled=False)
        if len(window) < 2:
            return Outcome(CANNOT_TELL, "the next lap has not been driven",
                           settled=False)
        moved = [lap for lap in window
                 if (getattr(lap, "short_shift_rpm", None) or 0) > 0]
        if moved:
            return Outcome(ACTED,
                           f"short-shifting recorded on lap {moved[0].lap_num}")
        return Outcome(NOT_ACTED, "no short-shift recorded on the next lap")

    return Outcome(
        CANNOT_TELL,
        f"nothing in the feed can confirm a {kind or 'call'} of this kind - "
        f"GT7 broadcasts no fuel map, brake balance or driving style")


def judge(filed, laps, *, final: bool = False) -> list:
    """`(key, Outcome)` for every filed call that can be settled now.

    `filed` is an iterable of `(key, call)`. A provisional `CANNOT_TELL` -
    the window not yet driven - is left for the next crossing, unless
    `final` (the flag), when it is written as it stands: a call made on the
    last lap is answered by the race ending, and that is recorded rather
    than left blank. **Written as the laps come in, not at the flag**, so
    the driver sees "ACTED - pitted on lap 12" on the Race screen two laps
    after the call, not after the export.
    """
    laps = list(laps)
    out = []
    for key, call in filed:
        outcome = outcome_for(call, laps)
        if outcome.settled or final:
            out.append((key, outcome))
    return out


def summarise(calls, laps) -> dict:
    """Counts by verdict, for the export and the debrief.

    **The unanswerable ones are counted, not dropped.** A summary reading
    "2 acted, 1 not" over nine calls invites the reader to believe the app
    watched all nine.
    """
    tally = {ACTED: 0, NOT_ACTED: 0, CANNOT_TELL: 0}
    for call in calls:
        tally[outcome_for(call, laps).verdict] += 1
    return tally
