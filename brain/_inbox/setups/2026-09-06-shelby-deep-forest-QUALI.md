═══════════════════════════════════════════════════════════════════
  FORD SHELBY GT350R '16  ·  DEEP FOREST RACEWAY — FULL COURSE
  **ROUND 6 SUPERCARS — QUALIFYING**
  10 minutes · 50 L fixed · wear & fuel at RACE rate (2×) · SLIPSTREAM OFF
  Grid ordered by the fastest lap set in this session
  Issued 6 Sep 2026 · v1.71 · car = Rev B, FEED-verified in session 134
═══════════════════════════════════════════════════════════════════

# 0. A correction first

Two turns ago I wrote *"grid is set by fastest lap, not a qualifying session."*
**That was wrong.** The hub reads `qualifyingEnabled: true`,
`qualifyingDurationMinutes: 10`, and `gridOrderMethod: FASTEST_LAP` — meaning
**there is a ten-minute qualifying session and the grid is ordered by the
fastest lap set inside it.** I conflated the ordering method with the absence of
a session. The plan below is what I should have given you then.

---

# 1. The regulations, read from the hub — not assumed

```
  qualifyingEnabled              true
  qualifyingDurationMinutes      10          -> 600 s
  qualifyingInitialFuelLitres    50          <- FIXED. Not your decision.
  qualifyingTyreWearRate         SAME_AS_RACE  (2x)
  qualifyingFuelConsumptionRate  SAME_AS_RACE  (2x)
  qualifyingContinuationTime     180 s       -> a lap begun before the flag counts
  qualifyingSlipstreamStrength   DISABLED    <- no tow. Traffic is pure downside.
  gridOrderMethod                FASTEST_LAP
```

**Nothing here is a setup lever.** Three of these decide the session and none
of them is on the settings screen.

---

# 2. Fuel — the app's own planner is right and it does not apply

`race.quali_fuel.qualifying_fuel()` on the measured burn of **7.842 L/lap**:

| flying laps | it wants | worth vs a full tank |
|---:|---:|---:|
| 1 | 24.7 L | 0.23 s/lap **[DERIVED]** |
| 3 | 40.0 L | 0.18 s/lap **[DERIVED]** |
| 5 | 55.6 L | 0.13 s/lap **[DERIVED]** |

**And you cannot use any of it, because the lobby fixes qualifying fuel at
50 L.** The planner's central output is "fuel to N litres" and that is not a
decision this series gives you. Worth knowing anyway: **50 L sits between its
3-lap and 5-lap answers**, so the fixed load happens to suit a 4-flying-lap
session almost exactly.

## 2.1 What 50 L actually buys — **the session is FUEL-capped, not clock-capped**

Measured today: the out-lap burned **8.000 L**, flying laps **7.842 L**.

```
   out-lap  8.000
   + 5 flying laps  x 7.842  =  39.21
   ------------------------------------
   total  47.2 L  of 50      ->  2.8 L spare
   a SIXTH flying lap needs 55.1 L  ->  IT DOES NOT FIT
```

Against the clock: `92.2 + 5 x 87.9 = 531.7 s` of a 600 s session, so **you
finish with ~68 s of clock and no fuel.**

> **The session is out-lap + FIVE flying laps. That is all of it.**

---

# 3. The out-lap — **[MEASURED], and the answer is that it is already done**

This mode's first priority, and for once the data answers it cleanly.

**Tyre temperature across the out-lap** (session 134, 4-wheel mean):

```
   first third  68.5 degC     mid third  70.8 degC     last third  71.8 degC
```

**And then it stops moving.** Lap-to-lap 4-wheel mean, with the per-corner
temperature noise floor on file at **0.9-1.4 °C**:

| lap | 1 (out) | 2 | 3 | 4 | 5 | 6 |
|---|---:|---:|---:|---:|---:|---:|
| mean °C | 70.8 | 71.9 | 72.2 | 72.0 | 73.2 | 72.8 |
| delta | — | +1.12 | +0.27 | −0.17 | +1.22 | −0.42 |

**Every one of those deltas is at or inside the noise floor.** So the set has
**plateaued by the end of the out-lap and there is no measurable warm-up ramp
after it.**

> **Push from the first flying lap. You do not owe the tyres a build-up lap.**

⚠️ **This is a plateau call, not a window call.** No optimal tyre window has ever
been published for GT7, by anyone. I am telling you the temperature has stopped
changing, **not** that it has arrived somewhere good. The set opened around
68-70 °C on the out-lap and why it opens there is unexplained.

---

# 4. What the temperatures DO say — the right-hand side does the work here

Per-wheel, and both gaps are **monotone across all five laps**:

| | out-lap | lap 6 | climb |
|---|---:|---:|---:|
| Front right − front left | +0.6 | **+6.2** | +5.6 °C |
| Rear right − rear left | +0.1 | **+4.0** | +3.9 °C |

The front-left actually **cools** (68.0 → 65.9) while the front-right climbs
(68.6 → 72.1).

**This corroborates the wear map from an independent instrument.** Measured wear
today: front-right **1.27×** front-left, rear-right **1.41×** rear-left. The
temperature gap and the gauge agree on which corner of the car is loaded, which
is the standing method — *gaps* are the usable temperature signal, never raw
temperature.

**Deep Forest is left-turn dominant for this car.** That is a finding about the
race more than about one lap, and it is new today.

---

# 5. Pace build-up — the number that actually decides your grid slot

Gap to that session's best, by flying lap:

| | flying 1 | 2 | 3 | 4 | 5 |
|---|---:|---:|---:|---:|---:|
| session 133 | +4.993 | +1.132 | +0.848 | **0.000** | — |
| session 134 | +1.637 | +1.217 | +0.180 | **0.000** | +0.179 |

**Your best lap came on the fourth flying lap in both sessions.** n = 2, so it
is a pattern and not a law — but it is the largest effect in this whole document.
The build-up is worth **1.2-1.6 s** on flying lap 1, which is **ten times** the
0.114 s that burning the tank down is worth.

> **Do not judge yourself on the first flying lap and do not bail after two.**
> Five flying laps fit in the fuel. Use all five.

**And the fuel arithmetic agrees with your own habit** — the tank runs out one
lap after the lap you have historically been quickest on.

---

# 6. Fuel weight — [DERIVED], small, and I cannot measure it

Burning 50 L down to ~12 L is 38 L = **27.7 kg**, worth **0.114 s** at the
doctrine figure of 0.003 s/L/lap on a ~90 s lap.

**[DERIVED, per CLAUDE.md §5.3 — never measured on this car.]** And I tried:
your last three laps today (87.912 / 87.732 / 87.911) are flat while ~15.6 L
burned off, which predicts 0.047 s. That is far inside your own lap scatter.
**Unmeasurable here.** It stays derived, and it is an order of magnitude smaller
than the build-up in §5.

---

# 7. The tyre does not limit this session

Worst wheel **2.808 %/lap** measured today. Six laps of quali = **16.8% worn** —
inside the near-flat first phase, where CLAUDE.md §5.1 puts losses in tenths.

**So the tyre is not a reason to go early.** It is, mildly, a reason not to
expect flying lap 5 to beat flying lap 4.

---

# 8. Setup — **nothing changes, and here is why that is the answer**

This mode's own rule is that a quali setup may spend its whole range on one lap,
because tyre life and fuel saving are race concerns. I have taken that seriously
and I am still not changing anything:

1. **The car is validated over 11 laps** across two sessions on Rev B, and your
   own report is *"car feels pretty good"* — **[DRIVER REPORT]**, primary
   evidence.
2. **The gearbox already suits a light car.** 6th tops at **280.8** against
   today's Vmax of **272.8** — 8 km/h of headroom, so a lighter, faster quali lap
   still does not run out of gear. No change needed and none made.
3. **Every quali variable that matters is already measured and none is a
   slider** — the fuel cap, the build-up, the plateau.
4. **The one candidate I have is unpriced, and the race follows immediately.**
   See §9.

---

# 9. The one thing I would test, and not today

> **[HYPOTHESIS]** `df_r` **260 → 300** (73.3% → 100.0% of range) is worth more
> in the sweepers than it costs on the straight, on a circuit that is
> Medium-High downforce with ~55% full throttle and 18 corners in 4.25 km.
>
> **[BASIS]** **[DOCTRINE]** — `05-track-reference.md` §2.4 names aero level as
> lever #2, *"set in the linked sweepers"*, and says run high. **[MEASURED]**
> — 25.4% of the lap sits in the 140-179 km/h band. Against it: `df_f` is
> already **100.0% of range**, so this moves aero balance **rearward**, and
> GT7's own readout says the car is already high-speed understeering at −0.50.
>
> **[TEST]** 3 clean laps at 300, 3 at 260, back to back, same session.
>
> **[COST]** 6 laps — and it must not be today.
>
> **[FALSIFIED BY]** the car running wide on entry to the linked sweepers, or
> terminal speed dropping more than **2.77 km/h** (the measured straight-speed
> noise floor on file).
>
> ⛔ **Why not today:** it is unpriced, it is race day, and **if you cannot
> revert it between qualifying and the race you would race an untested car** on
> a narrow circuit where the reference says overtaking is genuinely hard.

---

# 10. Predictions on the record

| Prediction | Falsified by |
|---|---|
| The session ends on fuel, not the clock — 5 flying laps, not 6 | you complete a sixth flying lap |
| Your best comes on flying lap 3, 4 or 5, not 1 or 2 | your best is flying lap 1 or 2 |
| No warm-up lap is needed — flying lap 1 is on temperature | the car feels short of grip on flying lap 1 in a way it does not on lap 3 |
| Your quali best beats 87.732 | it does not |
| The FR−FL temperature gap keeps climbing through the session | it flattens or reverses |
