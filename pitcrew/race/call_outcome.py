"""What happened after the engineer said something, where the app can tell.

**The log of calls is the point of keeping one**, and it has been half a
record: every call carries what was said, why, and how sure — and nothing
carries what the driver then did. A call he acted on and a call he ignored are
both evidence about the model, and they are the two that most need telling
apart, because this driver has overruled the engineer and been right four
sessions running.

### One instrument can answer a call, and it answers two questions

`laps.is_pit_lap` is measured, so whether a stop followed is a fact:

* **Box calls** — did a stop follow, and on which lap against the one the
  call named and the plan's. The window opens on the lap AFTER the call's
  own - a call is said on the crossing that closes `call.lap`, so that lap is
  already driven - and runs to the lap after the one it named, because
  *"box this lap or next"* is the instruction and a stop later than that is a
  different decision rather than a late compliance. A stop inside the window
  but after the named lap is still `ACTED`, and says how late (14 Sep 2026,
  Bathurst: every race on file boxed one lap after the plan's lap and every
  one of those box calls read "acted", judged from a window that started on
  a lap already completed and never compared against the plan).
* **The stay-out fold** — the same reading, inverted. *"Staying out? You
  should make it."* asks him not to stop, and no stop in the same window is
  the answer to the question the call actually asked.

**And short-shift calls looked like a second instrument, until they were not
— which took four critic rounds to see.** `laps.short_shift_rpm` looked like the response and is the
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

So a short-shift call is `CANNOT_TELL` too — **and the first version of that
refusal gave a reason the app itself contradicts out loud.** It said
`laps.upshift_rpm` had "no calibrated threshold to judge against".
`analysis/driving.saving_change` has one: `UPSHIFT_STEP_RPM`, 250 rpm or two
of the stint's own standard deviations, whichever is larger, over two laps
each side. The coordinator runs it every lap and George says the result in
the driver's ear — *"You've stopped short-shifting since lap 15 - upshifts at
8298 before, 8694 now."* One race, one question, two mechanisms, opposite
claims: rule 13, in the commit that cited rule 13 as its reason.

The reason that actually binds is a DIRECTION. `saving_change` finds a step
within a stint by comparing the last two laps with the median of everything
before, and it has only ever been calibrated on a step UPWARD - he stopped
saving, Deep Forest 8298 to 8694. A fall as compliance with one particular
call is a different measurement, over a window that starts where the call was
made rather than where the stint did, and nobody has calibrated it. Memory
`feedback-refutation-carries-a-direction` is this shape exactly.

### Three reports the laps can hold to account

A report is not an instruction, so it is not `ACTED` or `NOT_ACTED`; it is
`BORNE_OUT` or `NOT_BORNE_OUT` by the record (13 Sep 2026, Suzuka race run 20,
where every call was refused with a reason about the fuel map):

* **A place** — against `laps.position`, read at the crossing that closed the
  lap the place was called in.
* **"Two to go" / "Last lap"** — against the lap the flag fell on, and only
  where the flag was seen.
* **Fuel short to the flag** — against the tank at the flag, where no stop
  came between.

Everything else is `CANNOT_TELL`, **named rather than omitted, with the reason
that binds for its own kind**. A brake-balance click is not in any packet GT7
sends; reporting it as "not acted on" would turn a missing channel into a
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

from pitcrew.race.calls import (BOX_NOW, BOX_SOON, CHASE, FUEL_SHORT, GREEN,
                                 INCIDENT, LAPS_TO_GO, POSITION, RIVAL_BOXED,
                                 STATUS, STAY_OUT, TO_THE_FLAG, TO_THE_STOP,
                                 TYRE_TEMP)

ACTED = "acted"
NOT_ACTED = "not-acted"
CANNOT_TELL = "cannot-tell"
# **A report is not an instruction, and "acted" means nothing about it.**
# A place, a lap count and a fuel shortfall are claims about the race, and
# the laps on file can hold three of them to what happened. These two say
# whether the record bears the claim out - never that the driver did
# anything, and `not-borne-out` never that the call was false: the detail
# says what the laps show and, where they cannot separate two readings,
# says that too (rule 5).
BORNE_OUT = "borne-out"
NOT_BORNE_OUT = "not-borne-out"

# A box call means the lap it names or the next. A stop after that is a
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
    # **For a box call answered by a stop: laps after the plan's in-lap**
    # (after the lap the call named where the plan's is not on the call).
    # 0 is on plan, 1 is a lap late, negative is early; None where no stop
    # answered it. Not a score - the detail says the same in words.
    laps_late: int | None = None

    @property
    def known(self) -> bool:
        return self.verdict != CANNOT_TELL

    def as_export(self) -> dict:
        return {"verdict": self.verdict, "detail": self.detail}


def _laps_after(call_lap: int, laps, window: int):
    return [lap for lap in laps
            if call_lap <= lap.lap_num <= call_lap + window]


def outcome_for(call, laps, *, final: bool = False,
                flagged: bool = False) -> Outcome:
    """What the driver did after this call, or an honest refusal.

    `laps` are the race's laps in order, each needing `lap_num` and whichever
    field the call's kind is judged on. A lap list that does not reach past
    the call is `CANNOT_TELL` rather than `NOT_ACTED` — the race may simply
    have ended, and "he did not box" about a call made on the last lap is a
    statement about the flag, not the driver.

    `final` says the race is over and no more laps are coming; `flagged`
    says it ended at the flag, so the last lap on file is the finishing lap.
    A race ended with the Stop button is final and not flagged, and a claim
    about the flag is refused there rather than held to the wrong lap.
    """
    laps = list(laps)
    kind = getattr(call, "kind", None)
    lap_num = getattr(call, "lap", None)
    if lap_num is None:
        return Outcome(CANNOT_TELL, "the call carries no lap number")

    if kind in BOX_KINDS:
        return _box(call, lap_num, laps)

    if kind == STAY_OUT:
        # **The same reading as a box call, inverted** (critic pass 8, fifth
        # round). A stay-out fold carries `short_shift_drop_rpm`, so it used
        # to fall into the branch below and be refused for not knowing
        # whether he short-shifted - answering a question the call did not
        # ask. What it asked was whether he stayed out, and `is_pit_lap`
        # says so. Rule 12: the reported reason has to come from the
        # constraint that bound the answer.
        window = _laps_after(lap_num, laps, BOX_WINDOW_LAPS)
        stopped = [lap for lap in window if getattr(lap, "is_pit_lap", False)]
        if stopped:
            return Outcome(NOT_ACTED,
                           f"boxed on lap {stopped[0].lap_num} after all")
        if len(window) <= BOX_WINDOW_LAPS:
            return Outcome(CANNOT_TELL,
                           f"only {len(window)} lap(s) followed the call, so "
                           f"the window it named was never fully driven",
                           settled=False)
        return Outcome(ACTED,
                       f"stayed out through laps "
                       f"{lap_num}-{lap_num + BOX_WINDOW_LAPS}")

    if getattr(call, SHORT_SHIFT_FIELD, None):
        # See the module docstring: this was judged on `short_shift_rpm`,
        # which is the app's own switch, so the answer was always the
        # instruction reflected back. Settled, because no further lap
        # changes it.
        #
        # **Plain words, and true ones.** The detail is read aloud off the
        # Race screen beside "pitted on lap 11"; column names and backticks
        # belong in the log. And the reason is the DIRECTION, not a missing
        # instrument - `saving_change` measures a rise off `upshift_rpm`
        # every lap and George speaks it.
        return Outcome(
            CANNOT_TELL,
            "whether he short-shifted after this call is not measured - the "
            "app can see him STOP saving, not start")

    if kind == POSITION:
        return _position(call, lap_num, laps)
    if kind == LAPS_TO_GO:
        return _laps_to_go(call, lap_num, laps, final=final, flagged=flagged)
    if kind == FUEL_SHORT:
        return _fuel_short(call, lap_num, laps, final=final, flagged=flagged)

    return Outcome(CANNOT_TELL, _why_unanswerable(call, kind))


def _laps_word(n: int) -> str:
    return "one lap" if n == 1 else f"{n} laps"


def _box(call, lap_num: int, laps) -> Outcome:
    """A box instruction, held to the pit lap, the lap it named and the plan.

    **The lap it named, not the lap it was said on.** "Box this lap." said on
    the crossing that closed lap 10 names lap 11, the in-lap - `Call.box_lap`
    carries it, and a call from before the field existed names `lap + 1`,
    which is what "this lap" always meant. The window is the laps after the
    call up to one past the named lap: lap 10 itself is already driven and
    can hold no answer to a call made at its end.

    **And the plan's in-lap beside it** (`Call.plan_box_lap`), because a call
    that was itself a lap late can be obeyed to the letter by a stop that is
    a lap late - which is exactly what happened in every race on file.
    """
    named = getattr(call, "box_lap", None) or lap_num + 1
    planned = getattr(call, "plan_box_lap", None)
    last = max(named, lap_num + 1) + BOX_WINDOW_LAPS - 1
    driven = last - lap_num
    window = [lap for lap in laps if lap_num < lap.lap_num <= last]
    stopped = [lap for lap in window if getattr(lap, "is_pit_lap", False)]
    if stopped:
        pit = stopped[0].lap_num
        off = pit - named
        detail = f"pitted on lap {pit}, " + (
            "the lap the call named" if off == 0 else
            f"{_laps_word(abs(off))} {'after' if off > 0 else 'before'} "
            f"lap {named}, the lap the call named")
        late = off
        if planned is not None:
            late = pit - planned
            detail += ("; on the plan's lap" if late == 0 else
                       f"; {_laps_word(abs(late))} "
                       f"{'late' if late > 0 else 'early'} against the "
                       f"plan's lap {planned}")
        return Outcome(ACTED, detail, laps_late=late)
    if not window:
        return Outcome(CANNOT_TELL,
                       "no lap on file after the call - the race may have "
                       "ended on it", settled=False)
    # Only where the window was actually driven. A truncated window says
    # nothing about a stop that had not come due yet.
    if len(window) < driven:
        return Outcome(CANNOT_TELL,
                       f"only {len(window)} lap(s) followed the call, so "
                       f"the window it named was never fully driven",
                       settled=False)
    return Outcome(NOT_ACTED, f"no stop on laps {lap_num + 1}-{last}")


def _why_unanswerable(call, kind) -> str:
    """The reason this call cannot be held to anything on file - ITS reason.

    **One sentence served every kind, and it was true of almost none**
    (Suzuka, 13 Sep 2026, race run 20). "GT7 broadcasts no fuel map and no
    brake balance" was written under the green, a place, an incident, a
    chase, a rival's stop and "two to go"; no call the engineer makes names
    a fuel map at all, and only two carry a brake-balance click. A refusal
    whose reason is false is rule 12 in the audit trail: a reader who
    believes it stops asking whether the call could have been checked, and
    three of those could.

    **Not "driving style"** (critic pass 8, fifth round): the app measures it
    off the frames and speaks it.
    """
    spoken = f"{getattr(call, 'call', '')} {getattr(call, 'reason', '')}"
    if "brake balance" in spoken.lower():
        # The one channel the old sentence was right about - and only here.
        return ("GT7 broadcasts no brake balance, so whether he made the "
                "click is not on file")
    reason = _UNANSWERABLE.get(kind)
    if reason:
        return reason
    return (f"nothing on file answers a {kind} call"
            if kind else "the call carries no kind to judge it by")


# Each is the reason that binds for THAT kind, in words the driver reads off
# the Race screen. Most say the same shape of thing - the only record is the
# reading the call was made from, so holding the call to it would ask whether
# the app agrees with itself, which is the short-shift loop above again.
_UNANSWERABLE = {
    GREEN: ("the green is read off the same stream the laps are cut from - "
            "there is no second clock on file to hold it to"),
    INCIDENT: ("the lap was struck on the same evidence the call was made "
               "from, so its exclusion cannot confirm the call"),
    STATUS: ("a status line reads several running figures aloud at once; a "
             "place and a fuel shortfall are each judged where they are a "
             "call of their own"),
    TYRE_TEMP: ("read off the same tyre temperatures the laps are summarised "
                "from - no second instrument on file"),
    CHASE: ("the gap is the timing board as the app read it, and nothing on "
            "file times the other car independently"),
    RIVAL_BOXED: ("a rival's stop is seen only by the pit wall's own read of "
                  "the board - no record of his laps to confirm it"),
}


def _row_for(lap_num: int, laps):
    return next((lap for lap in laps if lap.lap_num == lap_num), None)


def _position(call, lap_num: int, laps) -> Outcome:
    """A place called, held to the place at the line that closed its lap.

    `laps.position` is read off the crossing packet, and a POSITION call is
    made mid-lap on a place held for eight seconds with `state.lap` counting
    the laps behind him - so a call on lap 8 is about the row for lap 9.

    **`not-borne-out` is what the record says, not that the call was false.**
    A place can be his for eight seconds and gone before the line; the laps
    cannot tell that from a place that was never his (a pit sequence
    renumbering the field reads the same), and the detail says so.
    """
    called = getattr(call, "position_called", None)
    if not called:
        return Outcome(CANNOT_TELL,
                       "this call states no place to hold to the line - it is "
                       "the time off the road, read off the wheels")
    closing = lap_num + 1
    row = _row_for(closing, laps)
    if row is None:
        return Outcome(CANNOT_TELL,
                       f"lap {closing}, the lap P{called} was called in, is "
                       f"not on file", settled=False)
    at_line = getattr(row, "position", None)
    if not at_line:
        # Rule 3: the column defaults to 0 and 0 is nobody's place.
        return Outcome(CANNOT_TELL,
                       f"lap {closing} closed with no place read at the line")
    if at_line == called:
        return Outcome(BORNE_OUT,
                       f"lap {closing} closed at P{at_line}, as called")
    return Outcome(NOT_BORNE_OUT,
                   f"called P{called}, lap {closing} closed at P{at_line} - "
                   f"lost before the line or never his; the laps cannot say "
                   f"which")


def _finishing_lap(laps):
    numbers = [lap.lap_num for lap in laps if lap.lap_num is not None]
    return max(numbers) if numbers else None


def _awaiting_flag(final: bool, flagged: bool, what: str) -> Outcome | None:
    """None where the flag has fallen and the last lap on file is the last."""
    if not final:
        return Outcome(CANNOT_TELL, f"{what} is answered at the flag",
                       settled=False)
    if not flagged:
        return Outcome(CANNOT_TELL,
                       f"the flag was never seen, so the last lap on file is "
                       f"not known to be the finishing lap and {what} cannot "
                       f"be held to it")
    return None


def _laps_to_go(call, lap_num: int, laps, *, final: bool,
                flagged: bool) -> Outcome:
    """"Two to go" at the crossing that closed lap N claims the flag at the end
    of lap N+2. Read off the call's tag, which `calls._laps_to_go` sets from
    the same count it spoke - never parsed back out of the sentence."""
    tag = getattr(call, "tag", None) or ""
    try:
        to_go = int(tag.rsplit("-", 1)[1]) if tag.startswith("to-go-") else None
    except (IndexError, ValueError):
        to_go = None
    if not to_go:
        return Outcome(CANNOT_TELL,
                       "the call does not record how many laps it counted")
    waiting = _awaiting_flag(final, flagged, "a lap count")
    if waiting is not None:
        return waiting
    if any(getattr(lap, "laps_dropped", None) for lap in laps):
        return Outcome(CANNOT_TELL,
                       "the clock counted a crossing as missed, so the lap "
                       "numbers on file are short of the race's own")
    finish = _finishing_lap(laps)
    if finish is None:
        return Outcome(CANNOT_TELL, "no lap on file to find the flag on")
    expected = lap_num + to_go
    if finish == expected:
        return Outcome(BORNE_OUT, f"the flag fell at the end of lap {finish}, "
                                  f"as counted")
    off = expected - finish
    words = {1: "one lap", 2: "two laps"}.get(abs(off), f"{abs(off)} laps")
    return Outcome(NOT_BORNE_OUT,
                   f"the flag fell at the end of lap {finish}, {words} "
                   f"{'sooner' if off > 0 else 'later'} than counted")


def _fuel_short(call, lap_num: int, laps, *, final: bool,
                flagged: bool) -> Outcome:
    """Short to the flag, held to the tank at the flag.

    **Not a verdict on the driver, and not quite one on the projection.**
    The call is a forecast on the burn at the time AND an instruction to
    save, so a car that reaches the flag with fuel aboard is either a
    projection that was wrong or a driver who did what he was told - and the
    laps do not separate the two. `not-borne-out` says the shortfall did not
    arrive, and the detail says it cannot say why.
    """
    frame = getattr(call, "fuel_frame", None)
    if frame == TO_THE_STOP:
        return Outcome(CANNOT_TELL,
                       "short to the stop the plan named - the laps record "
                       "whether he boxed, not whether the tank would have "
                       "reached that lap")
    if frame != TO_THE_FLAG:
        return Outcome(CANNOT_TELL,
                       "the call does not record whether it was short to the "
                       "stop or to the flag")
    waiting = _awaiting_flag(final, flagged, "a fuel shortfall")
    if waiting is not None:
        return waiting
    after = [lap for lap in laps if lap.lap_num > lap_num]
    stopped = [lap for lap in after if getattr(lap, "is_pit_lap", False)]
    if stopped:
        return Outcome(CANNOT_TELL,
                       f"boxed on lap {stopped[0].lap_num}, so the fuel aboard "
                       f"at the call never had to reach the flag")
    finish = _finishing_lap(laps)
    last = _row_for(finish, laps) if finish is not None else None
    if last is None:
        return Outcome(CANNOT_TELL, "no lap on file to read the flag's fuel off")
    left = getattr(last, "fuel_end", None)
    start = getattr(last, "fuel_start", None)
    if left is not None and left > 0:
        return Outcome(NOT_BORNE_OUT,
                       f"no stop, and the flag fell on lap {finish} with "
                       f"{left:.1f} L aboard - a projection that was wrong or "
                       f"fuel he saved; the laps cannot say which")
    if left is not None and start is not None and start > 0:
        # A lap that STARTED with a measured tank and ended at zero burned it
        # dry. A zero with no measured start is a default (rule 3).
        return Outcome(BORNE_OUT,
                       f"no stop, and the tank was dry at the flag on lap "
                       f"{finish}")
    return Outcome(CANNOT_TELL,
                   f"no fuel reading at the flag on lap {finish}")


def judge(filed, laps, *, final: bool = False, flagged: bool = False) -> list:
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
        outcome = outcome_for(call, laps, final=final, flagged=flagged)
        if outcome.settled or final:
            out.append((key, outcome))
    return out


def summarise(calls, laps) -> dict:
    """Counts by verdict, for the export and the debrief.

    **The unanswerable ones are counted, not dropped.** A summary reading
    "2 acted, 1 not" over nine calls invites the reader to believe the app
    watched all nine.
    """
    tally = {ACTED: 0, NOT_ACTED: 0, BORNE_OUT: 0, NOT_BORNE_OUT: 0,
             CANNOT_TELL: 0}
    for call in calls:
        tally[outcome_for(call, laps).verdict] += 1
    return tally
