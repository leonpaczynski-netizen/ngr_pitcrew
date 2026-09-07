"""What happened after the engineer said something, where the app can tell.

**The log of calls is the point of keeping one**, and it has been half a
record: every call carries what was said, why, and how sure — and nothing
carries what the driver then did. A call he acted on and a call he ignored are
both evidence about the model, and they are the two that most need telling
apart, because this driver has overruled the engineer and been right four
sessions running.

### One kind can be answered, and the rest say so

The app may only report an outcome it can measure:

* **Box calls** — `laps.is_pit_lap` is measured, so "did a stop follow" is a
  fact. The window is the call's own lap and the two after it, because
  *"box this lap or next"* is the instruction and a stop three laps later is
  a different decision rather than a late compliance.

**And short-shift calls were the second one, until they were not — which took
four critic rounds to see.** `laps.short_shift_rpm` looked like the response and is the
INSTRUCTION: `analysis/driving.py` says so in its first line — *"records the
APP's switch and nothing else"* — and the loop is closed end to end. The app
sets the beep when it makes the call (`controller._show_call` →
`bridge.set_short_shift`), every frame of the next lap writes the drop back
onto the lap (`controller:735`), and judging the call on that field asks
whether the app did what the app did. A driver who ignored the instruction
completely and shifted at the limiter all lap read `ACTED`, and after the
disposition was wired to the verdict he read `taken` as well — in the field
the contract tells a consumer to prefer. `expectations.saving_response`
answers the same question from the BURN and could say *"that hasn't saved"*
in the same race: two mechanisms, one question, opposite answers (rule 13).

So a short-shift call is `CANNOT_TELL` too, and its detail says which
instrument would answer it: `laps.upshift_rpm`, measured off the frames,
against the laps before the call. That is not wired here because the
threshold has never been calibrated, and this project has six derived indices
built and discarded for being shipped before they were.

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
# on a kind of its own, so it is recognised by the field being set. It is
# recognised in order to REFUSE it - see the docstring.
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
        # See the module docstring: this was judged on `short_shift_rpm`,
        # which is the app's own switch, so the answer was always the
        # instruction reflected back. Settled, because no further lap
        # changes it - what changes it is a calibrated read of
        # `laps.upshift_rpm`, and there is not one.
        return Outcome(
            CANNOT_TELL,
            "nothing on file reads whether he short-shifted - "
            "`laps.short_shift_rpm` is the app's own switch, and "
            "`laps.upshift_rpm` has no calibrated threshold to judge against")

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
