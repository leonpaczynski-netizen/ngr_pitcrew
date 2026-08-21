"""How much fuel to put in for a qualifying run, and what it is worth.

A qualifying lap is the one place where **carrying fuel is pure loss**. There
is no stint to survive and nothing to save it for: every litre in the tank is
mass the car drags round for the only lap that counts.

The app has always known the two numbers this needs - the measured burn per lap
and the fuel-weight coefficient - and has never put them together into the one
sentence he can act on. So it does.

### Two disciplines, both from things already learned the hard way

**Say it in seconds.** *"Any conservatism must be priced in his units and
said."* He will not carry a spare lap of fuel in a lap race because 6.31 L left
at the flag is 6.3 seconds standing still - and the same driver will not accept
"put in 20 litres" without being told what the other 80 were costing.

**Never invent the burn.** A qualifying fuel figure computed from a guessed
consumption is a guess about the one lap of the weekend that cannot be redone.
No measured burn means no number - the call says what is missing instead.

### What the coefficient is, and is not

`FUEL_WEIGHT_S_PER_L_PER_LAP` is **0.003 s per litre per lap, and it is
derived rather than measured** - `CLAUDE.md` §5.3 says so and says to let the
driver overwrite it. So the seconds figure travels as an estimate and says
which it is. The litres do not: those are arithmetic on a measured burn.
"""
from __future__ import annotations

from dataclasses import dataclass

# A qualifying run is out lap, the flyer, and the lap back to the pits. The
# in-lap is included because the tank has to survive it - a car that runs dry
# on the cool-down has still set the time, but it has also stopped on circuit.
OUT_LAP = 1
IN_LAP = 1

# On top of the laps themselves. Not a spare lap - a spare lap is the thing he
# refuses to carry - but enough that a slow formation lap or a lap under
# instruction does not empty it. Two litres is about a third of a lap here.
MARGIN_L = 2.0


@dataclass(frozen=True)
class QualifyingFuel:
    """The load, and what carrying more would have cost."""

    litres: float
    laps_covered: float
    burn_per_lap_l: float
    #: Seconds a lap saved against a full tank. None where the tank's capacity
    #: is unknown, or where the coefficient has been cleared.
    saving_s_per_lap: float | None
    #: True where `saving_s_per_lap` rests on the derived 0.003 figure rather
    #: than on one the driver measured.
    saving_is_derived: bool
    capacity_l: float | None

    def call(self) -> str:
        """One sentence, in the register of `CLAUDE.md` §5.5.

        Instruction first, reason second and short - and the reason is in
        seconds, because that is the unit he decides in.
        """
        litres = f"{self.litres:.0f}" if self.litres >= 10 else f"{self.litres:.1f}"
        head = f"Qualifying fuel: {litres} litres."
        why = (f"{self.laps_covered:g} laps at {self.burn_per_lap_l:.2f} "
               f"a lap, plus {MARGIN_L:g} spare.")
        if self.saving_s_per_lap is None or self.capacity_l is None:
            return f"{head} {why}"
        worth = (f"About {self.saving_s_per_lap:.2f} s a lap against a full "
                 f"tank" + (" - estimated" if self.saving_is_derived else "")
                 + ".")
        return f"{head} {why} {worth}"


def qualifying_fuel(*, fuel_per_lap_l: float | None,
                    flying_laps: int = 1,
                    fuel_capacity_l: float | None = None,
                    fuel_weight_s_per_l_per_lap: float | None = None,
                    weight_is_derived: bool = True) -> QualifyingFuel | None:
    """The load for a qualifying run, or None where the burn is not known.

    **None is the answer, not zero and not a default.** Guessing the burn puts
    a number on the one lap of the weekend that cannot be redone.
    """
    if not fuel_per_lap_l or fuel_per_lap_l <= 0:
        return None
    laps = OUT_LAP + max(1, int(flying_laps)) + IN_LAP
    litres = laps * fuel_per_lap_l + MARGIN_L
    if fuel_capacity_l and litres > fuel_capacity_l:
        # A run that will not fit in the tank is a run that needs fewer flying
        # laps, and saying so beats quietly clipping the figure.
        litres = fuel_capacity_l

    saving = None
    if (fuel_capacity_l and fuel_capacity_l > 0
            and fuel_weight_s_per_l_per_lap):
        saving = (fuel_capacity_l - litres) * fuel_weight_s_per_l_per_lap

    return QualifyingFuel(
        litres=round(litres, 1), laps_covered=laps,
        burn_per_lap_l=fuel_per_lap_l,
        saving_s_per_lap=None if saving is None else round(saving, 2),
        saving_is_derived=weight_is_derived,
        capacity_l=fuel_capacity_l)


def refusal(fuel_per_lap_l: float | None) -> str:
    """What to say when there is no burn to work from.

    Silence would read as "carry what you like". `CLAUDE.md` §5.5 says an
    unconfident call says so inside the call, because "unconfirmed" is a word
    the driver can act on - and here the honest version is that nobody has
    measured the thing the number would come from.
    """
    if fuel_per_lap_l:
        return ""
    return ("No qualifying fuel figure: nothing has measured this car's burn "
            "at this circuit yet. Run three laps at pace on a full tank and "
            "it will have one.")
