"""What would change the race plan - flip points for one event, plan row 5.1.

    python tools/flip_points.py 11
    python tools/flip_points.py 11 --burn 7.05 --lap-ms 101600
    python tools/flip_points.py 11 --save-cost 0.53      # s a litre, from a lever he measured
    python tools/flip_points.py 11 --inputs fuel_per_lap_l pit_loss_s   # quicker
    python tools/flip_points.py 11 --db copy.db

**Slow on purpose**: every step re-runs the optimiser. All four inputs took 6.5
minutes on Sardegna's 50-minute race (14 Sep); `--inputs` searches fewer.

Builds the event's inputs exactly as the plan does (`strategy.evidence.build_inputs`,
`remember=False`, so it is a reader - apart from the schema upgrade every
`Store()` makes when it opens a file), then re-runs the optimiser across one
input at a time (`strategy.flip`). **A sensitivity, not a simulation**: one input
moves and the rest hold, except that in a timed race burn and lap time are
flipped together.

`--burn`, `--lap-ms` and `--wear-scale` replace the practice figure with another
one - a stored plan's own number, or a race-pace read - and the output says the
figure was supplied. `--save-cost` prices the fuel save in seconds a litre; it
must come from a lever he drove (`tools/shortshift_trade.py`, an A/B), and
without it every saving sentence says the cost was not priced.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pitcrew.store.db import Store  # noqa: E402
from pitcrew.strategy import flip  # noqa: E402
from pitcrew.strategy.evidence import build_inputs  # noqa: E402


def overridden(inputs, *, burn=None, lap_ms=None, wear_scale=None):
    """The inputs with any supplied figure in place, and the words for each."""
    said = []
    if burn is not None:
        said.append(f"burn {burn:.3f} L/lap supplied (practice "
                    f"{inputs.fuel_per_lap_l if inputs.fuel_per_lap_l is not None else '-'})")
        inputs = replace(inputs, fuel_per_lap_l=burn)
    if lap_ms is not None:
        said.append(f"lap {lap_ms / 1000:.3f} s supplied (practice "
                    f"{inputs.lap_time_ms / 1000:.3f})")
        inputs = replace(inputs, lap_time_ms=int(lap_ms))
    if wear_scale is not None:
        before = inputs.wear_per_lap
        inputs = flip._scale_wear(inputs, wear_scale)
        said.append(f"wear x{wear_scale:g} supplied ("
                    + (f"{before:.4f} -> {inputs.wear_per_lap:.4f} a lap"
                       if before is not None else "no event wear figure")
                    + "; every compound's rate scaled; the flips below are "
                      "in percent of THIS rate)")
    return inputs, said


def report(inputs, *, save_cost=None, names=None, burn_supplied=False) -> list[str]:
    found = (flip.flip_points(inputs, names=tuple(names)) if names
             else flip.flip_points(inputs))
    if found.base.impossible is not None:
        # `decide` catches the optimiser's refusal, so this is where it shows.
        return [f"No plan to flip: {found.base.impossible}"]
    spread = {}
    if inputs.fuel_sd_l and not burn_supplied:
        spread["fuel_per_lap_l"] = (inputs.fuel_sd_l, "lap-to-lap burn scatter")
    lines = flip.describe(found, spread=spread)
    if burn_supplied:
        lines.append("  (The burn was supplied, so no sigma is quoted: practice's "
                     "scatter belongs to practice's figure.)")
    saving = flip.flip_on_saving(inputs, cost_s_per_l=save_cost)
    if saving is not None:
        lines.append(f"Fuel save: {saving.words()}.")
    lines.extend(burn_flip_save_lines(inputs, found))
    lines.append("Playbook: " + playbook_words(inputs, found))
    return lines


def _moves_with_pace(inputs, found) -> bool:
    return inputs.is_timed and any(one.at is not None
                                   for _, flips in found.joint for one in flips)


def burn_flip_save_lines(inputs, found) -> list[str]:
    """The litres a lap that cross a burn flip which REMOVES a stop.

    **Only there** (critic pass 1): a lower-burn flip that only changes the
    tyres is not a save that drops a stop, and in a timed race whose burn flip
    moves with lap time one figure "at the plan's distance" is the number the
    playbook line refuses to give. Unpriced, and said so - the priced figure is
    the Fuel save line above, and two save numbers must not read as one.
    """
    if _moves_with_pace(inputs, found):
        return []
    lines = []
    for one in found.for_input("fuel_per_lap_l"):
        need = flip.saving_to_flip(inputs, one)
        if (need is None or one.becomes is None or one.becomes.stops is None
                or found.base.stops is None or one.becomes.stops >= found.base.stops):
            continue
        lines.append(f"  Burn flip: {need:.2f} L a lap under the plan's burn at "
                     f"the plan's own pace drops a stop - unpriced, the lap "
                     f"time held.")
    return lines


def playbook_words(inputs, found) -> str:
    """The grant `playbook_hint` makes, or which of its refusals applied - the
    same branches, in the same order (rule 12)."""
    hint = flip.playbook_hint(inputs, found)
    if hint:
        return f"{hint['trigger']} -> {hint['action']}, when {hint['when']}"
    if found.base.impossible is not None:
        return "no grant - there is no runnable plan"
    if found.base.stops in (None, 0):
        return "no grant - the plan has no stop to drop"
    if _moves_with_pace(inputs, found):
        return ("no grant - in a timed race the burn that removes a stop moves "
                "with lap time, so one figure would be wrong at another pace")
    down = [one for one in found.for_input("fuel_per_lap_l")
            if one.direction == "down"]
    if not down:
        return "no grant - fuel burn was not searched"
    first = down[0]
    if first.at is None:
        return "no grant - no lower burn inside the search changes the plan"
    return ("no grant - the first lower-burn flip does not drop a stop, and "
            "the search stops at the first change, so a lower burn that does "
            "was not looked for")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("event_id", type=int)
    parser.add_argument("--burn", type=float, default=None, help="L a lap")
    parser.add_argument("--lap-ms", type=int, default=None, help="lap time, ms")
    parser.add_argument("--wear-scale", type=float, default=None,
                        help="multiply every wear rate by this")
    parser.add_argument("--save-cost", type=float, default=None,
                        help="seconds a litre saved, from a lever he measured")
    parser.add_argument("--inputs", nargs="+", default=None,
                        choices=sorted(flip.TOLERANCE),
                        help="search only these inputs")
    parser.add_argument("--db", default=None, help="a different archive")
    args = parser.parse_args()
    if args.db and not Path(args.db).is_file():
        # `Store()` on a path that is not there creates and migrates an empty
        # archive, and every figure would then be "no laps".
        print(f"No archive at {args.db}.")
        return 1
    store = Store(args.db) if args.db else Store()
    try:
        try:
            inputs, _ = build_inputs(store, args.event_id, remember=False)
        except ValueError as refused:
            print(refused)
            return 1
        inputs, said = overridden(inputs, burn=args.burn, lap_ms=args.lap_ms,
                                  wear_scale=args.wear_scale)
        minutes = (f"{inputs.race_minutes:g} min" if inputs.is_timed
                   else f"{inputs.race_laps} laps")
        print(f"Event {args.event_id}: {minutes}, lap "
              f"{inputs.lap_time_ms / 1000:.3f} s, burn "
              f"{inputs.fuel_per_lap_l if inputs.fuel_per_lap_l is not None else '-'} L/lap, "
              f"pit loss {inputs.pit_loss_s if inputs.pit_loss_s is not None else '-'} s")
        for line in said:
            print(f"  ({line})")
        for line in report(inputs, save_cost=args.save_cost, names=args.inputs,
                           burn_supplied=args.burn is not None):
            print(line)
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
