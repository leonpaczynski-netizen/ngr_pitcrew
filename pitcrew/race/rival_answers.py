"""The six questions the driver asks about a rival, one entry point each.

Every answer is a value, a reason under five words, and a confidence. Nothing
outside this module assembles one from raw fields - that is the whole point of
it. A caller reaching past these into `gap_signal` or `ledger` is a caller that
will eventually phrase one of them differently from the others.

    Are we catching?          `catching`
    Where are we gaining?     `where_we_gain`     (not built - see below)
    When did he pit?          `his_stop`
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

### One of the six is deliberately not here

`where_we_gain` - the per-sector attribution of §4 - needs the ego track
distance interpolated onto every 2 Hz gap sample, and that join does not exist
yet: `GapSample.track_s` is carried for it and nothing fills it in. Building
the binning on top of an unfilled field would produce a confident map of a lap
from no positional information at all. It is left out rather than stubbed.
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
    """"Where are we gaining on him?" - NOT BUILT, and it says so.

    The per-sector split needs the ego track distance interpolated onto every
    2 Hz gap sample. `GapSample.track_s` is carried for it and nothing fills it
    in yet, so binning would divide a lap using no positional information at
    all and return a confident map of nothing.
    """
    return Answer(reason="track position not joined to gaps yet")


def everything(view: RivalView) -> dict[str, Answer]:
    """All six, for a screen or an export. Each still its own call."""
    return {
        "catching": catching(view),
        "where_we_gain": where_we_gain(view),
        "his_stop": his_stop(view),
        "must_cover": must_cover(view),
        "his_fuel": his_fuel(view),
        "can_undercut": can_undercut(view),
    }
