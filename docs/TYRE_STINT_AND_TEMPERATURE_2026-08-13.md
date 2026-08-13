# Stint length, compound crossover, and racing into the dark

**Research note, 13 Aug 2026.** Written against the Monza 11–12 Aug practice data,
GT7 1.70. Two questions from the driver:

1. Stint length should follow from **when a compound stops being efficient** — when
   a worn Racing Soft is slower than a fresh Racing Medium — not only from when the
   tyre is dead.
2. Races that run through a **time multiplier** end in conditions practice never saw.
   The Monza race is 50 real minutes at ×6, so five hours of game time, afternoon into
   evening. The coming enduro is 2 real hours at ×12 — a full day and night. In the
   last one the Racing Hards never came up to temperature and cost lap time against
   everything practised in daylight.

Both are answerable. Neither is answerable **from the data as it stands**, and the
reasons why are the most important findings here.

---

## 1. Two blockers, found in the data

### 1.1 ⛔ The tyre temperature windows are fabricated

`store/tyres.py` has carried a per-compound window since the rebuild, and since
`1.3` the export has used it to qualify every compound's evidence:

| Compound | App says "optimal" |
|---|---|
| Racing Hard | 75–100 °C |
| Racing Medium | 80–105 °C |
| Racing Soft | 85–110 °C |

**Every tyre temperature in the 11–12 Aug Monza session, on every compound and every
lap, sits between 68 °C and 78 °C.** Not one lap of any compound reaches even the
bottom of the Racing Medium window. Under these thresholds Racing Soft would be
unusable in GT7 — it could never once reach 85 °C.

Two more things say the numbers are wrong rather than the driving:

- **GT7 fits every set at exactly 70.0 °C** (measured yesterday, three runs, RS/RM/RH).
  Under these thresholds a fresh Racing Soft is fitted precisely *at* its cold ceiling,
  and a fresh Racing Hard is fitted five degrees below its own. A game does not ship
  tyres that start cold on purpose for one compound and not another.
- **Nobody has published GT7 windows.** The question was asked on GTPlanet in April
  2025 and went unanswered; no telemetry project documents them. These figures are
  real-world racing slick numbers — which do live at 90–110 °C — imported into a game
  whose surface-temperature channel plainly does not work in that range.

This is not dormant. `windowQualification` has been telling the knowledge base
*"RM never got into its window … its pace deficit is overstated and its stint length is
flattered"* on **every export**, as a measured finding, about a threshold nobody
measured. It is the exact failure `CLAUDE.md` §4 rule 7 warns about: a heuristic
pattern-matched from another context and believed downstream.

**Fix: stop qualifying against invented numbers.** Either measure the windows (§4.3)
or report the temperature and say plainly that no window is known. The second costs
nothing and is true today.

### 1.2 ⛔ The compound pace deltas do not measure the compounds

`compoundProfiles[].paceDeltaSPerLap` is the median lap time on each compound against
the reference. For Monza it says **Racing Medium is 0.92 s/lap faster than Racing
Hard, and Racing Soft only 0.56 s faster** — the medium beating the soft, which is
not a thing tyres do.

It is not a tyre measurement at all. The three compounds ran in three separate
sessions across two evenings, so the median difference between them contains:

| Confound | Size at Monza |
|---|---|
| Fuel load — RS ran 4 laps off a full tank, RH ran 15 to empty | ~0.3 s/lap across a stint |
| Tyre age within the run | up to 1 s/lap by the end |
| Track evolution and driver warm-up across the evening | unquantified, plausibly the largest |
| Struck and incident laps pulling the median | lap 26 alone is +5.5 s |

**A crossover calculation built on this is arithmetic on noise.** Whatever the model
does with stint length, the number that decides *which compound* has to be measured
like-for-like first.

---

## 2. Stint length: what the maths actually says

### 2.1 Two different questions, and only one of them decides a plan

**The crossover lap** — when a worn X is slower than a fresh Y — is the question as
asked, and it has a clean answer. With the app's own degradation curve (flat to 50%
of tyre life, ramping to 1.0 s/lap at 90%, punitive after), a compound `X` at wear
rate `wₓ` per lap loses

```
loss(n) = 0                                    while n·wₓ ≤ 0.50
        = 2.5 · DEG · (n·wₓ − 0.50)            while 0.50 < n·wₓ < 0.90
```

so X falls behind a fresh Y at the lap where `loss_X(n) − loss_Y(n) = δ`, with `δ`
the fresh-tyre pace gap between them. For the measured Monza wear rates:

| | Wear/lap | 50% worn | 90% worn | App's stint cap (0.85/w) |
|---|---|---|---|---|
| RS | 0.1725 | lap 2.9 | lap 5.2 | **4** |
| RM | 0.0764 | lap 6.5 | lap 11.8 | **11** |
| RH | 0.0577 | lap 8.7 | lap 15.6 | **14** |

With a soft 0.5 s/lap quicker than the medium on fresh rubber, the soft is ahead to
about **lap 4** and by lap 5 is 0.4 s/lap *behind* a fresh medium. That is the number
the driver asked for, and it is worth showing — but note it lands almost exactly on the
existing `0.85/w` cap of 4 laps. **At this wear multiplier, "efficient" and "dead" are
the same lap**, which is the driver's own instinct ("closer to the max stint length for
that tyre") and is what a steep degradation curve does.

**The strategic question is different**: a stint should end when *continuing* costs
more than *stopping*, and stopping costs a pit loss amortised over the stint that
follows. That is not a threshold, it is an optimisation, and it is the one the plan
should be built on. The crossover lap is a *report*, not a rule.

### 2.2 The model cannot currently find the efficient stint

`build_plan` gets its stint lengths from `allocate_laps(total, limits)` — an **even
split subject to caps**. It searches over stop counts and over compound assignments,
but never over *how long each stint should be*. So the answer to "when should I stop"
is always "at the even split, or at the cap", and the economics of stopping earlier or
later are never evaluated.

**Recommended: replace the split with an exact optimiser.** Stint cost is a pure
function of `(compound, laps)` — `stint_time_s` already integrates degradation and
fuel weight — so a dynamic program over (laps remaining × stints remaining) finds the
true optimum in milliseconds:

```
f(laps_left, stints_left) = min over l ≤ cap of
      cost(compound, l) + pit_cost(l) + f(laps_left − l, stints_left − 1)
```

This is exact, not heuristic; it needs no new constant; and it answers the driver's
question directly, because the optimum *is* the efficient stint length. It also gets
the end-of-race case right on its own — a stop with too few laps left to amortise it
never wins, so no special case is needed.

### 2.3 …but at Monza the answer is robust anyway

A sensitivity sweep over the unmeasured pace gap, from 0 to 1.5 s/lap of soft
advantage:

| RS faster than RH by | RM faster by | Winning plan |
|---|---|---|
| 0.0 s | 0.0 s | 1 stop, 27 laps, **13 RH / 14 RH** |
| 0.6 s | 0.3 s | 1 stop, 27 laps, **13 RH / 14 RH** |
| 1.5 s | 0.75 s | 1 stop, 27 laps, **13 RH / 14 RH** |

**The Monza plan does not depend on the number we cannot measure.** At 8× wear the
soft lasts four laps, so using it buys pace for a fraction of a stint and costs a whole
stop — and a stop here is expensive: 19 s pit loss + 7.5 s dead time + **73 s of
refuelling**, because the refuel rate is 1.0 L/s and the tank is 100 L. The refuel
rate, not the tyre, is what decides this race. It is a driver-typed number and it has
never been measured.

So: fix the pace measurement because the *general* answer needs it, but race Monza on
Racing Hards with confidence either way.

---

## 3. Racing into the dark

### 3.1 What GT7 actually simulates

GT7 models air temperature, humidity and **road surface temperature**, updating a
temperature field across the track every few seconds; each tyre queries the surface
beneath it to derive friction. Time of day drives it, and a night race genuinely runs
on a colder track. Community accounts of the WTC800 Nürburgring race — which starts at
night and ends at dawn — report the tyres being *better* at the end than the start,
because the track is colder.

That is the two-sided effect the driver hit, and both halves are real:

- **A colder track wears tyres less.** Stint length grows.
- **A colder track makes a hard compound harder to light up.** If it never reaches its
  working range it is slower than it was in the day — which is exactly what happened to
  the Racing Hards last time.

Nothing about this is inferable from a daytime run.

### 3.2 What the app can and cannot see

| Quantity | In the packet? | Notes |
|---|---|---|
| Track surface temperature | **No** | GT7 simulates it per tyre but does not broadcast it. `CLAUDE.md` §5 forbids inventing a proxy |
| Air temperature | **No** | Same |
| Tyre surface temperature | **Yes** | Per corner, 60 Hz. Already captured |
| In-game time of day | **Yes**, and **currently thrown away** | `time_of_day_ms` at 0x80. The recorder read it, used it as a frame clock, and stopped storing it when the clock moved to the packet counter yesterday |

**This is the key realisation: the app does not need track temperature.** The causal
chain is

```
time of day  →  [track temp, unobservable]  →  tyre temp  →  lap time
```

and both ends plus the middle observable are measurable. Correlating **achieved tyre
temperature and lap time against the in-game clock** answers the strategic question
without ever needing the hidden variable.

The one change that unlocks all of it is small: **put `time_of_day_ms` back in the
frame record**, as its own channel. Every lap then knows where in the day it sat.

### 3.3 What to do with it

**Do not model or predict the temperature curve.** GT7 publishes no such curve, it
varies by circuit and weather preset, and a fitted one would be exactly the kind of
invented constant this project exists to avoid.

Do this instead, in order of value:

1. **Record the time of day per lap** and carry it into the export. A lap at 14:00 and
   a lap at 23:00 stop being interchangeable evidence.
2. **Declare the race's time-of-day span.** Start time × multiplier × duration gives
   the in-game window the race covers. For Monza: 5 hours from an afternoon start. For
   the enduro: 24 hours.
3. **Report evidence coverage, and refuse to extrapolate past it.** If practice covers
   13:00–15:00 and the race runs to 23:00, the plan for the closing stints rests on
   nothing. That is a finding the driver can act on — it tells him what to go and drive
   — and it is the same shape as the existing evidence cap on stint length.
4. **Plan the enduro in phases.** A 24-hour race is not one set of conditions. Split it
   at the day/night boundaries the clock crosses, and require evidence per phase.
5. **Once night runs exist**, the compound choice per phase falls out of the same
   optimiser: it is just a different pace and wear profile per phase.

### 3.4 The test protocol this needs

Two runs, and they are the cheapest hour available:

- **A night run at race pace**, same fuel load and same stint length as a day run, on
  the compound the race will use. This is the single highest-value session before the
  enduro — it converts "the hards did not come up to temp" from an anecdote into a
  measured pace and wear rate.
- **A back-to-back compound run**, same time of day, same fuel load, same tyre age
  window — three short runs, one per compound, ideally on a full tank each. This is
  what makes `paceDeltaSPerLap` mean something, and nothing else will.

If the windows in §1.1 are ever to be real, a third: the same corner at several times
of day, recording achieved tyre temperature against lap time. The temperature at which
lap time stops improving *is* the bottom of the window, measured rather than imported.

---

## 4. Recommended order of work

| | Change | Why first |
|---|---|---|
| 1 | **Stop qualifying compounds against invented windows** | It is producing a false finding in every export today, tagged as measurement |
| 2 | **Capture `time_of_day_ms` per frame** | One line. Everything in §3 is blocked without it, including the enduro |
| 3 | **Measure compound pace like-for-like, or refuse to state it** | The crossover cannot mean anything until this is real |
| 4 | **Replace even-split allocation with the stint optimiser** | Answers the stint-length question exactly, and needs no new constants |
| 5 | **Time-of-day evidence coverage, and phase planning for the enduro** | Turns "no evidence for the dark" into a finding rather than a silent guess |
| 6 | **Measure the refuel rate** | It is 73 s a stop at Monza and decides the stop count; it has never been measured |

Items 1 and 2 are unambiguous and land with this note. Items 3–6 are design choices
worth a decision before building.

---

## Sources

Community and official material consulted; none of it yielded a usable GT7 tyre
temperature window, which is itself the finding in §1.1.

- [GT7 Tire Temperature windows — GTPlanet](https://www.gtplanet.net/forum/threads/gt7-tire-temperature-windows.431495/) (Apr 2025, question unanswered)
- [Tyre temperature — GTPlanet](https://www.gtplanet.net/forum/threads/tyre-temperature.406736/)
- [Gran Turismo 7 features detailed dynamic weather — Traxion](https://traxion.gg/gran-turismo-7-features-detailed-dynamic-weather-but-not-at-every-track/)
- [GT7 weather physics overview — Outscal](https://outscal.com/web-story/gran-turismo-7-weather-physics)
- [Conquering GT7 Endurance Races — Accel](https://artisan.accel.com/conquering-gt7-endurance-races-your-winning-guide)
- [Gran Turismo 7 Online Manual, MFD](https://www.gran-turismo.com/gb/gt7/manual/race/04)

The load-bearing evidence is the 11–12 Aug Monza capture: 51 laps, six runs, three
compounds, full-rate telemetry.
