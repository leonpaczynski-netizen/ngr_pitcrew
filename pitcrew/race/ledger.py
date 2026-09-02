"""One ledger. Undercut, overcut and the cover deadline are the same sum.

All three ask what happens to a gap over the laps following a stop by one
party. They differ only in who stopped and what the answer is compared against,
so there is one function and three readings of it - not three implementations
that can drift apart and disagree about the same race.

    dG(n) = sum over i=1..n of [ t_stayed_out(i) - t_pitted(i) ] - pit_loss

`t_pitted(i)` is fresh-tyre, low-fuel pace INCLUDING the out-lap warm-up
penalty, which is measured from our own stops rather than assumed - at 1.2 s on
this driver's archive it is most of what an undercut has to overcome.
`t_stayed_out(i)` is degraded, heavier pace from the deg model.

### It refuses rather than running on a thin fit

A rival's degradation is inferred from lap times derived from gaps, and those
carry about a quarter-second of quantisation each. A two-lap fit of that is not
a deg rate, it is a slope through noise, and a ledger built on it produces a
confident lap number for a decision worth a place. Below `MIN_DEG_LAPS` every
answer here is `None`, and the caller is expected to say "unknown" rather than
find something else to say.

### Why the cover deadline is the one the driver actually asks

He has pitted; we lead by `g_behind` and are losing it every lap because his
tyres are new and ours are not. The deadline is the last lap on which stopping
still keeps us ahead, and it shrinks on its own. When the margin falls inside
the standard error of the deg fit the model can no longer tell the two
alternatives apart, and at that point the honest call is to stop now - not
because it is better but because waiting is no longer a decision anybody can
support.
"""
from __future__ import annotations

from dataclasses import dataclass

# Laps of rival evidence before a ledger is worth computing. Fewer than this
# and the deg rate is a slope through the 2 Hz quantisation noise.
MIN_DEG_LAPS = 5

# The margin below which the ledger cannot separate stopping now from waiting.
# Expressed in seconds, and compared against the deg fit's own standard error
# where one is supplied.
DEFAULT_MODEL_ERROR_S = 1.0

# How far ahead the ledger will look. Longer than any stint this driver runs.
MAX_HORIZON_LAPS = 40


@dataclass(frozen=True)
class Pace:
    """How a car's lap time evolves over the laps after a reference point.

    `base_s` is its pace at the reference; `deg_s_per_lap` is what each further
    lap costs on the tyre it is on; `warmup_s` is the one-off cost of the first
    lap out of the pits. `laps_of_evidence` is what the deg rate rests on and
    is the only thing that decides whether this may be used at all.
    """
    base_s: float
    deg_s_per_lap: float = 0.0
    warmup_s: float = 0.0
    laps_of_evidence: int = 0
    error_s: float = DEFAULT_MODEL_ERROR_S
    stint_lap: int = 0

    def lap_time_s(self, i: int) -> float:
        """Lap time on the i-th lap from the reference, 1-based."""
        cost = self.base_s + self.deg_s_per_lap * (self.stint_lap + i - 1)
        if i == 1:
            cost += self.warmup_s
        return cost

    @property
    def trustworthy(self) -> bool:
        return self.laps_of_evidence >= MIN_DEG_LAPS


@dataclass(frozen=True)
class Swing:
    """What a stretch of laps does to a gap, and what it rests on.

    `seconds` is always **from our point of view and positive is good for us**.
    One convention across all three readings, because the whole reason there is
    one ledger is that three of them drift apart.
    """
    laps: int
    seconds: float
    model_error_s: float
    pit_loss_counted: bool

    @property
    def inside_the_noise(self) -> bool:
        return abs(self.seconds) <= self.model_error_s


def pace_swing(n: int, slower: Pace, faster: Pace) -> float | None:
    """Seconds the faster car takes out of the slower one over `n` laps.

    Pace only. **The pit loss is deliberately not in here**, because whether it
    belongs depends on who has already paid it, and that is a property of the
    question rather than of the arithmetic - see `swing`.
    """
    if n <= 0 or n > MAX_HORIZON_LAPS:
        return None
    if not (slower.trustworthy and faster.trustworthy):
        return None
    return sum(slower.lap_time_s(i) - faster.lap_time_s(i)
               for i in range(1, n + 1))


def swing(n: int, ours: Pace, theirs: Pace, pit_loss_s: float | None, *,
          we_still_owe_a_stop: bool) -> Swing | None:
    """What `n` laps do to the gap, from our side.

    **`we_still_owe_a_stop` is the whole modelling decision and it must be
    passed deliberately.** A pit loss is paid once by each car, so it cancels
    out of any comparison made after BOTH have stopped - which is the undercut,
    where he stops later and pays the same toll we just paid. It does not
    cancel while only he has stopped and we have not, which is the cover: there
    the toll is still ahead of us and it is by far the largest term.

    A first cut had it always subtracted. That made an undercut require
    recovering the entire pit loss on pace alone - eighty seconds at Spa - so
    it never returned one, correctly by its own arithmetic and wrongly about
    racing.
    """
    if pit_loss_s is None:
        return None
    gained = pace_swing(n, theirs, ours)
    if gained is None:
        return None
    if we_still_owe_a_stop:
        gained -= pit_loss_s
    return Swing(laps=n, seconds=gained,
                 model_error_s=max(ours.error_s, theirs.error_s),
                 pit_loss_counted=we_still_owe_a_stop)


def undercut(gap_ahead_s: float | None, ours_fresh: Pace, theirs_old: Pace,
             pit_loss_s: float | None, *,
             their_forced_stop_in: int | None = None
             ) -> tuple[int | None, float | None]:
    """`(lap it first works, margin)` for stopping while he stays out.

    We stop now and he stops later, so **both pay the pit loss and it cancels**;
    what is left is the pace we take out of him while he is on old tyres and we
    are on new ones, against the gap we started behind.

    `(None, None)` where it never works inside his remaining fuel - a real
    answer, and it should be reported as unavailable rather than offered with a
    low probability.
    """
    if gap_ahead_s is None or gap_ahead_s < 0:
        return None, None
    horizon = min(MAX_HORIZON_LAPS, their_forced_stop_in or MAX_HORIZON_LAPS)
    for n in range(1, horizon + 1):
        answer = swing(n, ours_fresh, theirs_old, pit_loss_s,
                       we_still_owe_a_stop=False)
        if answer is None:
            return None, None
        if answer.seconds > gap_ahead_s:
            return n, answer.seconds - gap_ahead_s
    return None, None


def cover_deadline(gap_behind_s: float | None, ours_old: Pace,
                   theirs_fresh: Pace, pit_loss_s: float | None
                   ) -> tuple[int | None, float | None, bool]:
    """`(last lap we can still stop and stay ahead, margin, pit now)`.

    The question the driver actually asks, and the overcut is the same sum read
    the other way: he has stopped, we have not, we lead by `gap_behind_s` and
    are giving it back every lap to his new tyres. **We still owe the stop**,
    so the pit loss is in the ledger here.

    `pit now` goes true when the margin falls inside the deg fit's own error:
    at that point the model cannot tell waiting from stopping, and a lap number
    quoted past it is invented precision.
    """
    if gap_behind_s is None or gap_behind_s < 0 or pit_loss_s is None:
        return None, None, False
    if not (ours_old.trustworthy and theirs_fresh.trustworthy):
        return None, None, False
    error = max(ours_old.error_s, theirs_fresh.error_s)
    last, margin = None, None
    for n in range(0, MAX_HORIZON_LAPS + 1):
        if n == 0:
            standing = gap_behind_s - pit_loss_s
        else:
            answer = swing(n, ours_old, theirs_fresh, pit_loss_s,
                           we_still_owe_a_stop=True)
            if answer is None:
                break
            standing = gap_behind_s + answer.seconds
        if standing <= 0:
            break
        last, margin = n, standing
    if last is None:
        # Even stopping this instant loses the place: the deadline is past.
        return 0, gap_behind_s - pit_loss_s, True
    return last, margin, margin is not None and margin <= error


def overcut(gap_behind_s: float | None, ours_old: Pace, theirs_fresh: Pace,
            pit_loss_s: float | None) -> tuple[int | None, float | None]:
    """`(laps we can stay out and still hold him, margin)`.

    The cover deadline, read as the question "how long can I keep going" rather
    than "when must I stop". Same ledger, deliberately - two implementations of
    one sum is two answers about one race.
    """
    laps, margin, _ = cover_deadline(gap_behind_s, ours_old, theirs_fresh,
                                     pit_loss_s)
    return laps, margin
