"""What a rival's stop costs him, and whether that is more than ours costs us.

*"If we know when a rival pits and the fuel they come in on, we know if we have
a fuel advantage or not, and what they leave with, and how long they spent in
the pits compared to what we will spend."* — the driver, 2 Sep 2026, and he is
right that this stands on its own.

**This is arithmetic on observed quantities, and that is the point.** It needs
no degradation model, no tyre-age lever and no theory about undercuts. Litres
taken divided by a measured refuel rate is seconds standing still; the
difference between his and ours is the swing across the stop cycle. Every term
is either read off the screen or measured from our own tank.

### Why that is the whole game in GT7

GT7 has no partial tyre change and no split compounds, so the only part of a
stop that VARIES between two cars is fuel. Measured on this driver's own
archive: at Monza he stood for 48-63 s taking 48-63 L at a measured 1.001 L/s,
against a pit transit of the order of ten seconds. A rival taking twenty litres
where he takes fifty is thirty seconds cheaper in the box, and no tyre
advantage on this driver's wear multipliers comes close to paying that back.

### What this deliberately does NOT do

**It does not recommend an undercut**, and the reason is measured rather than
stylistic. At the 2x wear he actually races, his stints end at 0.44-0.56 worst
corner — CLAUDE.md §5.1 phase 1, "losses in tenths" — so there is no old-tyre
pace loss to gain against. Any undercut model would be multiplying by a number
never observed at his multiplier, which is rule 5.

**It does not assume the pit delta cancels.** It does not, and believing it did
was the central error of the first design: two cars pitting on different laps
take different fuel loads, and for a driver who fuels to the flag, deferring a
stop by one lap makes his own stop SHORTER by a lap's burn. That term is
carried explicitly in `deferring_saves_s`.

**It does not speak.** It answers what a stop costs; the caller decides whether
that is worth saying.
"""
from __future__ import annotations

from dataclasses import dataclass

# **Measured, and it is not the figure the strategy model uses.** Time from pit
# entry to the first rise in the tank, measured off the frames at all three
# Monza stops as 16.93 s and identical between them to 0.01 s. CLAUDE.md §5.4
# says 5-10 s and understates it; `strategy/model.py` uses 7.5.
#
# It is carried here as an ADDITIVE term only where the caller supplies a
# transit that excludes it. Where a circuit's stored `pit_loss_secs` already
# describes the whole non-fuel cost - which is what the measured 17.6-19.0 s at
# Monza against a declared 19.0 says it does - adding this again double-counts
# by eight seconds, and that defect is live in the strategy model today.
DEAD_TIME_S = 16.9
DEAD_TIME_SOURCE = "measured: 3 Monza stops, 16.93 s, identical to 0.01 s"


@dataclass(frozen=True)
class Stop:
    """One stop, as observed. Every field may be `None` — it was not seen.

    Nullable throughout and deliberately so: these come from reading a screen,
    and a reader that returns 0.0 for "could not see it" writes a rival's fuel
    down as an empty tank. CLAUDE.md rule 3.
    """
    lap: int | None = None
    fuel_in_l: float | None = None
    fuel_out_l: float | None = None
    tyres_changed: bool | None = None
    compound: str | None = None

    @property
    def litres(self) -> float | None:
        """Fuel taken, or None. Never negative and never clamped to zero.

        A negative result means one of the two readings is wrong, not that no
        fuel was taken — clamping it would turn "I misread" into a confident
        "he took nothing", which is CLAUDE.md rule 9.
        """
        if self.fuel_in_l is None or self.fuel_out_l is None:
            return None
        taken = self.fuel_out_l - self.fuel_in_l
        return taken if taken >= 0 else None

    def standing_s(self, refuel_rate_lps: float | None) -> float | None:
        """Seconds stationary: the fill, plus the dead time before it starts."""
        litres = self.litres
        if litres is None or not refuel_rate_lps or refuel_rate_lps <= 0:
            return None
        return litres / refuel_rate_lps + DEAD_TIME_S


@dataclass(frozen=True)
class Swing:
    """What a stop cycle is worth against a rival's, and why.

    `seconds` is positive when WE come out ahead of where we would have been.
    `reason` names the term that produced it, because a figure whose reason
    comes from a different expression is CLAUDE.md rule 12 — and that rule
    exists because this app has already reported a plan capped by evidence as
    though it were capped by fuel.
    """
    seconds: float | None
    reason: str
    ours_standing_s: float | None = None
    theirs_standing_s: float | None = None

    @property
    def known(self) -> bool:
        return self.seconds is not None


def fuel_swing(ours: Stop, theirs: Stop,
               refuel_rate_lps: float | None) -> Swing:
    """How much longer their stop is than ours, in seconds.

    **The one number the screen makes available that nothing else does.** Both
    cars pay the same pit transit at the same circuit, so it cancels here and
    only here — what does not cancel is what each of them stands still for, and
    on this driver's archive that is 48-63 s against a transit of ten.
    """
    mine = ours.standing_s(refuel_rate_lps)
    yours = theirs.standing_s(refuel_rate_lps)
    if mine is None or yours is None:
        missing = []
        if mine is None:
            missing.append("ours")
        if yours is None:
            missing.append("theirs")
        return Swing(None,
                     f"not known: {' and '.join(missing)} fuel was not read",
                     ours_standing_s=mine, theirs_standing_s=yours)
    swing = yours - mine
    litres = (theirs.litres or 0.0) - (ours.litres or 0.0)
    return Swing(
        swing,
        (f"he takes {litres:+.0f} L on you, which is {swing:+.0f} s "
         f"standing still"),
        ours_standing_s=mine, theirs_standing_s=yours)


def deferring_saves_s(burn_per_lap_l: float | None,
                      refuel_rate_lps: float | None) -> float | None:
    """Seconds of our own standing time saved by staying out one more lap.

    **The term the first design dropped, and it is the largest one.** A driver
    who fuels to the flag and carries no spare — which this one does, and has
    said so — takes one lap less fuel for every lap he defers. Measured across
    his circuits that is 3.2 s a lap at Road Atlanta and 8.0 at Spa, against an
    out-lap penalty measured at about 1.2 s. Staying out is worth several times
    what the fresh tyres are.
    """
    if not burn_per_lap_l or not refuel_rate_lps or refuel_rate_lps <= 0:
        return None
    return burn_per_lap_l / refuel_rate_lps


def earliest_stop_lap(laps_total: int | None, lap_now: int | None,
                      burn_per_lap_l: float | None,
                      capacity_l: float | None) -> int | None:
    """The first lap on which a stop can still reach the flag, or None.

    **A hard floor under every stop call, and the design had none.** Stopping
    earlier than this does not merely waste time — the tank cannot hold enough
    fuel to finish, so it forces a second stop worth the better part of a
    minute. This app has already put nine wrong box calls into one race; a box
    call that cannot reach the end is a worse failure than a late one.
    """
    if not laps_total or not lap_now or not burn_per_lap_l or not capacity_l:
        return None
    if burn_per_lap_l <= 0 or capacity_l <= 0:
        return None
    reach = capacity_l / burn_per_lap_l
    earliest = laps_total - reach
    return max(lap_now, int(earliest) + 1 if earliest > int(earliest)
               else int(earliest))


def forced_stop_lap(stop: Stop, burn_per_lap_l: float | None) -> int | None:
    """The last lap a rival can reach on the fuel he left the pits with.

    Their constraint, which changes what we do with ours: a car that must stop
    by lap 22 cannot overcut us to 25. `None` where their fuel was not read —
    an unread tank is not a full one.
    """
    if stop.lap is None or stop.fuel_out_l is None:
        return None
    if not burn_per_lap_l or burn_per_lap_l <= 0:
        return None
    return stop.lap + int(stop.fuel_out_l / burn_per_lap_l)
