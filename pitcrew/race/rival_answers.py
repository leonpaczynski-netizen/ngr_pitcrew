"""The six questions the driver asks about a rival, one entry point each.

Every answer is a value, a reason under five words, and a confidence. Nothing
outside this module assembles one from raw fields - that is the whole point of
it. A caller reaching past these into `gap_signal` or `ledger` is a caller that
will eventually phrase one of them differently from the others.

    Are we catching?          `catching`
    Where are we gaining?     `where_we_gain`
    When did he pit?          `his_stop`
    When does he USUALLY?     `his_pit_pattern`
    Do we have to cover?      `must_cover`
    Will he run out of fuel?  `his_fuel`
    Can we undercut?          `can_undercut`

### Blind is a state, not a silence

`RivalView.available` is false when the screen reader has stopped, when the
board cannot be found, or when everything on file has gone stale. **Every
answer checks it and returns "unknown" rather than the last thing it knew.**
Losing the stream mid-race collapses to ego-only strategy with that said out
loud; it does not quietly keep answering from values that stopped being true
minutes ago.

### The sector map, and what it rests on

`where_we_gain` was reported as blocked once and it was not: GT7 broadcasts no
lap-distance channel, but `telemetry/recorder.py` has always integrated one
from speed at 60 Hz and `race/qualifying.py` does it live. `race/lap_ruler.py`
is the same integration on the race path, so every gap reading is now tagged
with where on the road it was taken.

What it inherits is that integration's known fault: about **7% of laps
teleport**, and speed integration cannot see a teleport at all. What it CAN see
is the consequence - a teleported lap does not come out the length of the
circuit - so those laps are thrown away rather than binned somewhere wrong.
"""
from __future__ import annotations

from dataclasses import dataclass

from pitcrew.race.gap_signal import GAP_STALE_S, GapSignal
from pitcrew.race.ledger import Pace, cover_deadline, undercut
from pitcrew.race.rival_fuel import Litres, forced_stop_lap
from pitcrew.race.rival_pace import Attribution, RivalPace, attribute

# Confidence markers. `THIN` is what a caller says out loud as "unconfirmed",
# which is a word this driver can act on.
SURE, THIN, UNKNOWN = "sure", "thin", "unknown"


@dataclass(frozen=True)
class Answer:
    """A value, a short reason, and how much to trust it."""
    value: object = None
    reason: str = ""
    confidence: str = UNKNOWN

    @property
    def known(self) -> bool:
        return self.confidence != UNKNOWN

    def __bool__(self) -> bool:
        return self.known


NOTHING = Answer(reason="blind to rivals", confidence=UNKNOWN)


@dataclass
class RivalView:
    """Everything known about one rival, and whether any of it is current."""
    name: str | None = None
    signal: GapSignal | None = None
    pace: RivalPace | None = None
    ours: Pace | None = None
    theirs: Pace | None = None
    fuel_aboard: Litres | None = None
    burn_per_lap_l: float | None = None
    stop_lap: int | None = None
    fuel_added: Litres | None = None
    pit_loss_s: float | None = None
    lap: int | None = None
    now_s: float = 0.0
    reader_alive: bool = True
    # Where round the lap we gain and lose on him, from `race/sectors.py`.
    sectors: object = None
    # How far into a race he has stopped, one fraction per stop on file.
    stop_history: tuple = ()

    @property
    def available(self) -> bool:
        """Whether anything here may be answered from.

        **Checked by every answer, not once at the top.** A view that was fresh
        when it was built and read three minutes later is exactly the stale
        propagation this exists to prevent.
        """
        if not self.reader_alive or self.signal is None:
            return False
        return self.signal.latest(self.now_s) is not None

    @property
    def blind_because(self) -> str:
        if not self.reader_alive:
            return "the screen reader has stopped"
        if self.signal is None or not self.signal.samples:
            return "no gap has been read"
        if self.signal.latest(self.now_s) is None:
            return f"the last gap is over {GAP_STALE_S:.0f} s old"
        return ""


# --- the six ---------------------------------------------------------------

def catching(view: RivalView) -> Answer:
    """"Are we catching?" - trend, attributed, plus laps to contact."""
    if not view.available:
        return Answer(reason=view.blind_because)
    rate, spread, samples = view.signal.rate_s_per_s(view.now_s)
    if rate is None:
        return Answer(reason="not enough gap history")
    gap = view.signal.latest(view.now_s)
    split: Attribution | None = None
    if view.pace is not None and view.theirs is not None and view.ours is not None:
        split = attribute(rate, view.ours.base_s, view.ours.base_s,
                          view.pace.smoothed_s(view.lap), view.theirs.base_s)
    laps = None
    if rate > 0 and gap and view.ours is not None:
        laps = gap / (rate * view.ours.base_s) if view.ours.base_s else None
    reason = (split.why() if split and split.why() else
              f"{samples} samples")
    return Answer(value=(rate, laps, split), reason=reason,
                  confidence=THIN if spread is None or samples < 12 else SURE)


def his_stop(view: RivalView) -> Answer:
    """"When did he pit and what did he take on?"

    A pit event does not expire - it is a point, not a level - so this is the
    one answer that survives the reader going quiet.
    """
    if view.stop_lap is None:
        return Answer(reason="he has not been seen stopping")
    added = view.fuel_added
    if added is None or not added.known:
        return Answer(value=(view.stop_lap, None),
                      reason=f"lap {view.stop_lap}, fuel unread",
                      confidence=THIN)
    if added.point is not None:
        return Answer(value=(view.stop_lap, added),
                      reason=f"lap {view.stop_lap}, {added.point:.0f} L",
                      confidence=SURE)
    return Answer(value=(view.stop_lap, added),
                  reason=(f"lap {view.stop_lap}, {added.low:.0f}"
                          f"-{added.high:.0f} L"),
                  confidence=THIN)


def his_fuel(view: RivalView) -> Answer:
    """"Will he run out of fuel?" - his forced stop against ours."""
    early, late = forced_stop_lap(view.fuel_aboard, view.burn_per_lap_l,
                                 view.lap)
    if early is None:
        return Answer(reason="his fuel is not known")
    if early == late:
        return Answer(value=(early, late), reason=f"dry on lap {early}",
                      confidence=SURE)
    return Answer(value=(early, late),
                  reason=f"dry between laps {early} and {late}",
                  confidence=THIN)


def must_cover(view: RivalView) -> Answer:
    """"Do we have to cover?" - the deadline lap and the shrinking margin."""
    if not view.available:
        return Answer(reason=view.blind_because)
    if view.ours is None or view.theirs is None:
        return Answer(reason="no pace model for one of us")
    gap = view.signal.latest(view.now_s)
    laps, margin, now = cover_deadline(gap, view.ours, view.theirs,
                                       view.pit_loss_s)
    if laps is None:
        return Answer(reason="the fit is too thin to say")
    if now:
        return Answer(value=(0, margin, True), reason="box now, margin gone",
                      confidence=THIN)
    return Answer(value=(laps, margin, False),
                  reason=f"{laps} laps, {margin:.0f} s in hand",
                  confidence=SURE)


def can_undercut(view: RivalView) -> Answer:
    """"Can we undercut?" - available or not, and if so the lap and margin."""
    if not view.available:
        return Answer(reason=view.blind_because)
    if view.ours is None or view.theirs is None:
        return Answer(reason="no pace model for one of us")
    gap = view.signal.latest(view.now_s)
    forced = None
    if view.fuel_aboard is not None and view.burn_per_lap_l and view.lap:
        early, _ = forced_stop_lap(view.fuel_aboard, view.burn_per_lap_l,
                                   view.lap)
        forced = None if early is None else max(1, early - view.lap)
    lap, margin = undercut(gap, view.ours, view.theirs, view.pit_loss_s,
                           their_forced_stop_in=forced)
    if lap is None:
        return Answer(value=None, reason="not available", confidence=SURE)
    return Answer(value=(lap, margin),
                  reason=f"box in {lap}, out {margin:.0f} s up",
                  confidence=SURE)


def where_we_gain(view: RivalView) -> Answer:
    """"Where are we gaining on him?" - the two strongest sectors.

    Past the standard-error gate only. Below twice its own error a bin is
    noise, and reporting noise is how a driver learns to distrust the tool -
    which costs more than the finding was worth.

    Empty early in a race is the ordinary answer and not a failure: four laps
    is the floor for a standard error to mean anything at all.
    """
    if view.sectors is None:
        return Answer(reason="no sector map for him")
    if view.sectors.laps_used < 1:
        dropped = view.sectors.laps_dropped
        return Answer(reason=(f"{dropped} laps dropped, none binned"
                              if dropped else "no laps binned yet"))
    best = view.sectors.worth_saying(2)
    if not best:
        return Answer(value=[], reason="nothing past the noise",
                      confidence=THIN)
    where = ", ".join(
        f"{b.from_m:.0f}-{b.to_m:.0f} m {b.mean_s:+.2f}" for b in best)
    gaining = sum(1 for b in best if b.gaining)
    return Answer(value=best,
                  reason=f"{gaining} of {len(best)} gaining",
                  confidence=SURE if best[0].laps >= 6 else THIN)


def his_pit_pattern(view: RivalView) -> Answer:
    """"When does he stop?" - his stops on file, as a fraction of the race.

    A map of WHEN rather than where: the lap he came in on, across every race
    he has been watched in, against the field. It is the pre-race half of the
    pit wall and it needs no live reading at all.

    A fraction rather than a lap, so races of different lengths pool - a stop
    on lap 11 means something quite different in a 20-lap race and a 40-lap
    one.
    """
    if not view.stop_history:
        return Answer(reason="never seen stopping")
    fractions = [f for f in view.stop_history if f is not None]
    if not fractions:
        return Answer(reason="his stop laps are not on file")
    mean = sum(fractions) / len(fractions)
    return Answer(value=(mean, len(fractions)),
                  reason=f"{mean:.0%} in, {len(fractions)} stops",
                  confidence=SURE if len(fractions) >= 3 else THIN)


def everything(view: RivalView) -> dict[str, Answer]:
    """All six, for a screen or an export. Each still its own call."""
    return {
        "catching": catching(view),
        "where_we_gain": where_we_gain(view),
        "his_stop": his_stop(view),
        "must_cover": must_cover(view),
        "his_fuel": his_fuel(view),
        "can_undercut": can_undercut(view),
        "his_pit_pattern": his_pit_pattern(view),
    }
