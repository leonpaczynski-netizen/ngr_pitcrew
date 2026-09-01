"""Knowing when to shut up.

*"In the last V8 race I came off track and was frustrated, and then George
kept telling me every time someone passed me, which made me more angry. Better
for him to keep quiet and then encourage when I am back on track."*

That is a driver report about the engineer, and CLAUDE.md standing rule 1 makes
it primary evidence. It is also, read plainly, a correctness bug: the app said
several true things at the one moment they could do nothing but harm.

### Why this is separate from `incident_watch`

`IncidentWatch` answers *"is this lap out of the count"* and its whole detector
is a crawl - the car at or near a standstill mid-lap, which is what every
genuine incident in the capture set ends with. **Running wide at speed and
rejoining never trips it**, and that is exactly the case being reported here.

The two questions also want opposite error costs, which is the argument for
two detectors rather than one threshold:

* Striking a lap wrongly **loses a measurement** nobody knows is gone, so
  `IncidentWatch` is deliberately conservative.
* Staying quiet wrongly costs a position call the driver could have had, for a
  few seconds, once. Against a driver who is already angry the other error is
  far worse. **So this one fires easily and on purpose.**

### What goes quiet, and what never does

Only the **`FACT` register** - which today is `POSITION` and `STATUS`. Those
are volunteered observations about what is happening around him, and they are
what he named.

**A `DECISION` is never suppressed.** If he needs to box, or he is short on
fuel, that is the same whether he has just been off or not, and withholding it
to protect his mood would be the app deciding he cannot handle information he
needs to finish the race. Same for an `EVENT`: the chequer, the green, and the
incident record itself all still go out.

### And then say something

Silence alone is not the request - *"encourage when I am back on track"* is
half of it. The encouragement here is deliberately a **fact**, not
cheerleading: what it actually cost, and where he still is. An engineer saying
"you're fine" to a driver who just lost four seconds is a driver who stops
believing the engineer.
"""
from __future__ import annotations

from dataclasses import dataclass

# Surface characters that are not the racing surface. `C` (kerb) is
# deliberately absent: he rides kerbs by design and a kerb is not a moment.
OFF_SURFACE = frozenset("DGSs")

# **How long off the road before the engineer stops volunteering.** Two wheels
# brushing grass at a track limit is not a moment; a third of a second of it
# is. Set low on purpose - see the error costs above.
OFF_MIN_S = 0.35

# How long after rejoining before he is treated as racing again. Long enough to
# cover the re-gather and the corner after it, short enough that a race is not
# run in silence.
SETTLE_S = 12.0

# A moment that cost less than this is not worth a word on the way back. He
# knows he brushed the grass; being congratulated for surviving it is worse
# than silence.
WORTH_SAYING_S = 1.5


@dataclass
class Composure:
    """Per-frame, on the telemetry thread. Never raises, never speaks.

    It answers two questions - may the engineer volunteer a fact, and is there
    a word owed on the way back - and the caller decides what that is worth.
    """

    off_for_s: float = 0.0
    settling_for_s: float = 0.0
    _was_off: bool = False
    # Seconds owed as an account of the moment: how long the car spent off.
    # None once it has been said, so it is said once and not every frame.
    _owed_s: float | None = None

    @property
    def off(self) -> bool:
        return self.off_for_s >= OFF_MIN_S

    @property
    def composed(self) -> bool:
        """True when the engineer may volunteer a fact again."""
        return not self.off and self.settling_for_s >= SETTLE_S

    def reset(self) -> None:
        """Between sessions. State that outlives one is read as belonging to
        it — CLAUDE.md rule 11, and this one would open a race mid-recovery."""
        self.off_for_s = 0.0
        self.settling_for_s = SETTLE_S
        self._was_off = False
        self._owed_s = None

    def update(self, surfaces, dt: float) -> None:
        """One frame of surface characters, and how long it lasted.

        `surfaces` absent is not "on track": packet formats `A` and `B` carry
        no surface channel at all, and treating missing as clean would make
        this silently inert on a fallback format. With nothing to read it
        holds whatever it last knew rather than asserting composure.
        """
        if not surfaces:
            return
        if dt <= 0:
            return
        off_now = any(char in OFF_SURFACE for char in surfaces)
        if off_now:
            self.off_for_s += dt
            self.settling_for_s = 0.0
            self._was_off = True
            return
        if self._was_off and self.off:
            # Just rejoined after a real moment. Bank what it cost him so the
            # word on the way back carries a number rather than a sentiment.
            self._owed_s = self.off_for_s
        if self._was_off:
            self._was_off = False
            self.off_for_s = 0.0
        self.settling_for_s += dt

    def may_volunteer(self, register: str) -> bool:
        """Whether a call of this register may go out unasked right now.

        Registers other than `FACT` are always allowed. A decision he needs to
        act on does not become less true because he is angry, and an engineer
        that withholds one is deciding for him what he can cope with.
        """
        from pitcrew.race.calls import FACT

        return register != FACT or self.composed

    def owed(self) -> float | None:
        """Seconds off the road, once, when he is settled — or None.

        Cleared as it is handed over, so this is a word on the way back and
        not a thing repeated every frame for twelve seconds, which is the
        defect being fixed rather than a second copy of it.
        """
        if self._owed_s is None or not self.composed:
            return None
        owed, self._owed_s = self._owed_s, None
        return owed if owed >= WORTH_SAYING_S else None
