# Run plan — `<car>` at `<circuit>`, `<date>` (template)

**Filled by Ludo before every practice session, before the car turns a wheel.**
A run without a purpose is a run that cannot be judged. One file per session,
saved beside the setup docs as `YYYY-MM-DD-<car>-<circuit>-RUNPLAN.md`; the
debrief writes the outcome column at the end of the day and nothing else moves.

The clean-lap definition is **the tool's** (`tools/where_the_change_landed.py`:
no out-lap, no pit lap, no off-track over 1 s, no spin, not excluded) — not the
eye's. Two definitions produced "4 clean laps" and "0 clean laps" for the same
session on 6 Sep 2026.

```
  Session      : <practice | quali | race sim>      Event : <id> / <hub round>
  Car state    : brain/car-state/<car>-<circuit>.md  Rev <X>, SCREEN-confirmed <date>
  League limits: <power_limit_bhp> BHP / <weight_limit_kg> kg / <drivetrain>   [events row]
  Multipliers  : tyre x<n> · fuel x<n> · refuel <n> L/s                          [events row]
  Time on track: <minutes>       Laps available: ~<n>
```

| run | purpose | fuel | tyre | the ONE delta | lap type | laps | instrument + floor | prediction | falsifier | outcome |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | install / baseline | <L> | <compound, new/used> | none | install + 3 clean | 4 | — | — | — | |
| 2 | test: `<key> a → b` | <L> | same set | one slider | push, 3 clean | 4 | `<instrument>`, floor <n> | `<what moves, by how much>` | `<what would kill it>` | |
| 3 | A-B-A return | <L> | same set | back to a | push, 3 clean | 4 | same | matches run 1 within the floor | drifted: it was the driver learning, not the change | |
| 4 | long run (race load) | full | new set | none | long, 8+ | 9 | burn, wear/lap, temps | burn <n> ± <n>, wear <n>/lap | — | |
| 5 | pit-loss run | as is | as is | none | in-lap + out-lap, no fuel | 3 | (in + out) − 2×clean | ~<n> s ex-fuel | — | |

**Rules the table enforces**
- One delta per run, three clean laps minimum, the instrument and its measured floor
  named BEFORE the run. A change judged on lap time is not judged.
- The A-B-A return leg is not optional when the change is a feel change: the driver
  improves about 0.3 s a run on his own.
- Big enough to feel, both directions: a change inside the driver's resolution can
  take the sheet the wrong way.
- The debrief fills `outcome` from the tool's output and the driver's report, in that
  order of arrival (driver first, data second), and closes each prediction in
  `brain/RECONCILIATION.md` or the car-state file.
