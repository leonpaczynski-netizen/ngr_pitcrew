"""Is the tow worth it? The fuel a slipstream saves is priced at the pump.

The driver's second half of the Deep Forest question, 7 Sep 2026: *"I was
saving fuel sitting behind Boxhead but I was also losing lap time to first -
was the fuel saving worth the lost lap time or not? That's what George needs
to calculate in real time."*

### The arithmetic, and why it is this simple

The fill at the last stop is sized to the flag: the laps after the box times
the burn, less what is aboard. Every litre NOT burned before the stop is a
litre already aboard at the box and a litre less to pump - so a litre saved in
the tow is worth exactly its standing time, `1 / refuel_rate` seconds, and
nothing else. (After the stop a saved litre is worth nothing at all: the fill
is already in.) Against that, the lap time given away sitting in his wake is
lost every lap and never comes back.

    worth it  <=>  saving_l_per_lap / refuel_rate_lps  >  losing_s_per_lap

Deep Forest, 6 Sep 2026: about 0.6 L a lap saved behind P2 at a 2 L/s pump is
0.3 s a lap at the stop, against about a second a lap given away. Not worth it
- which is the argument for the traffic undercut in `rival_calls`.

### Every term is read, and the reference names itself

The held-up laps are the ones the wall read inside `HELD_UP_GAP_S`. The
reference - what he burns and laps in clear air - is this race's own laps with
nothing within `CLEAR_GAP_S` where there are enough of them, and the plan's
burn and lap time where there are not; the sentence says which (CLAUDE.md
4.5). Inside `WASH_S` the two sides cannot be told apart and the verdict is
"about a wash", never a coin toss dressed as a finding.

CLAUDE.md 5.3 says fuel-saving in a slipstream is "nearly free". Nearly: it
is free of DRIVING cost, and this is the whole of the cost it is not free of.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

# Held up: the car ahead inside this many seconds. Shared with the undercut,
# which imports it from here so the two agree about what "held up" is.
HELD_UP_GAP_S = 1.5
# Clear air: nothing within this many seconds. Beyond a tow's reach.
CLEAR_GAP_S = 3.0
MIN_HELD_LAPS = 3
MIN_CLEAR_LAPS = 2
# Inside this the saving and the loss cannot be told apart.
WASH_S = 0.3

BY_CLEAR_LAPS = "your clear-air laps"
BY_THE_PLAN = "the plan"


@dataclass(frozen=True)
class TowTrade:
    """What the tow is worth against what it costs, per lap, and on what."""
    laps_held: int
    # Litres a lap NOT burned behind him against the reference. Signed: a
    # negative figure is a real finding (no tow benefit), not a bad reference.
    saving_l_per_lap: float
    # The same, priced at the pump. None where no refuel rate is on file.
    saving_s_per_lap: float | None
    # Seconds a lap slower behind him than the reference. Signed likewise.
    losing_s_per_lap: float
    reference: str

    @property
    def worth_it(self) -> bool | None:
        """True to stay in it, False to get out, None where it cannot say.

        **`max(self.saving_s_per_lap, 0.0)` stood here and was CLAUDE.md
        rule 9** (critic pass 7). A negative saving is the tow COSTING him
        fuel - a real finding - and clamping it to zero made a tow that cost
        0.4 s of fuel and 0.2 s of lap time come out inside `WASH_S` and be
        spoken as *"About a wash"*, in a sentence that had already said there
        was no fuel saving and that he was losing time. Unclamped it is 0.6
        apart and it is "Not worth it", which is the answer.
        """
        if self.saving_s_per_lap is None:
            return None
        gain = self.saving_s_per_lap
        if gain <= 0 and self.losing_s_per_lap <= 0:
            # It costs fuel and costs no time. Neither side is a gain and
            # neither is a loss he can act on: say so rather than pick one.
            return None
        if self.losing_s_per_lap <= 0:
            return True                 # a free tow: nothing given away
        if abs(gain - self.losing_s_per_lap) < WASH_S:
            return None
        return gain > self.losing_s_per_lap

    def sentence(self, them: str = "him") -> tuple[str, str]:
        """`(call, reason)`. Units named on both sides - litres and seconds
        both go "a lap", and rule 13 forbids one phrase for two quantities.

        **And this side had to be reworded to keep that promise** (critic
        pass 7). It said *"You're losing 1.4 seconds a lap to Boxhead"*,
        which is the sentence `rival_calls.closing_call` already owns for a
        different quantity - there it means the GAP is growing at 1.4 s a
        lap, read off the board. Here it means his LAP TIME in the wake
        against his own clear-air reference, while the gap is by
        construction not growing at all. Two calls, the same words, the same
        rival, minutes apart. "Behind him you're N a lap slower" cannot be
        heard as a gap, and the reason names what it is slower THAN - which
        is the plan on some laps and his own clear-air laps on others, so it
        belongs there and not in the sentence (rule 12).
        """
        lost = (f"Behind {them} you're {self.losing_s_per_lap:.1f} seconds a "
                f"lap slower." if self.losing_s_per_lap > 0
                else f"Behind {them} you're no slower.")
        if self.saving_l_per_lap <= 0:
            call = f"No fuel saving in the tow. {lost}"
        elif self.saving_s_per_lap is None:
            call = (f"The tow saves you {self.saving_l_per_lap:.1f} litres a "
                    f"lap - no refuel rate on file to price it. {lost}")
        else:
            call = (f"The tow saves you {self.saving_l_per_lap:.1f} litres a "
                    f"lap - {self.saving_s_per_lap:.1f} seconds at the stop. "
                    f"{lost}")
        verdict = self.worth_it
        if verdict is True:
            call += " Worth it - stay in it."
        elif verdict is False:
            call += " Not worth it."
        elif self.saving_s_per_lap is not None:
            call += " About a wash."
        return call, f"Over {self.laps_held} laps, against {self.reference}."


def trade(gaps_by_lap: dict, laps: dict, *,
          refuel_rate_lps: float | None,
          planned_fuel_per_lap_l: float | None,
          planned_lap_time_ms: int | None) -> TowTrade | None:
    """The trade on this race's own laps, or None where it cannot be made.

    `gaps_by_lap` is lap -> gap ahead in seconds (the trend's `seen`);
    `laps` is lap -> `(lap_time_ms, fuel_used_l)` for the laps that are
    evidence (no incident, no saving instruction).
    """
    held = [laps[lap] for lap, gap in gaps_by_lap.items()
            if gap is not None and 0 < gap <= HELD_UP_GAP_S and lap in laps]
    if len(held) < MIN_HELD_LAPS:
        return None
    clear = [laps[lap] for lap, gap in gaps_by_lap.items()
             if gap is not None and gap >= CLEAR_GAP_S and lap in laps]
    if len(clear) >= MIN_CLEAR_LAPS:
        ref_ms = median(ms for ms, _ in clear)
        ref_l = median(fuel for _, fuel in clear)
        reference = BY_CLEAR_LAPS
    elif planned_fuel_per_lap_l and planned_lap_time_ms:
        ref_ms, ref_l, reference = (float(planned_lap_time_ms),
                                    float(planned_fuel_per_lap_l), BY_THE_PLAN)
    else:
        return None
    held_ms = median(ms for ms, _ in held)
    held_l = median(fuel for _, fuel in held)
    saving_l = ref_l - held_l
    saving_s = (saving_l / refuel_rate_lps
                if refuel_rate_lps and refuel_rate_lps > 0 else None)
    return TowTrade(laps_held=len(held), saving_l_per_lap=saving_l,
                    saving_s_per_lap=saving_s,
                    losing_s_per_lap=(held_ms - ref_ms) / 1000.0,
                    reference=reference)
