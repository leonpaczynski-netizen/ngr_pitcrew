# M0 run card

**One race. Three stops. Thirty-five minutes.**
Print this. Read it before you put the headset on.

---

## Set up

| | |
|---|---|
| **Car** | Porsche 911 RSR (991) '17 |
| **Track** | Monza — Full (with chicanes) |
| **Race** | Custom, **25 laps** |
| **Fuel multiplier** | **3×** |
| **Tyre wear multiplier** | **1×** ← *not* the 8× you race |
| **Tyres** | Racing Medium (RM), start on a fresh set |
| **Fuel at start** | **Full — 100 %** |
| **Weather** | Dry, fixed. No rain, no time progression |
| **Opponents** | None, or as few as the game allows |

**In Pit Crew, before you go out:** Settings → **Record raw session**.
Check it. Leave it. Stop it when you come in.

---

## The three stops

| | Lap | Do this | Arrive at or below |
|---|---|---|---|
| **A** | **5** | **Tyres only.** RM again. **Fuel: 0.** | *anything* |
| **B** | **12** | **Fuel only. Fill to FULL.** **No tyres.** | **35 %** |
| **C** | **20** | **Tyres AND fill to FULL.** | **60 %** |

**Order matters. Do not swap B and C.**

### If you are above the arrival number

Stay out. Run another lap and box the lap after.
One lap ≈ **6 %**. Two laps ≈ 12 %.

That is the whole precondition. **Being too full when you box is the one
mistake that quietly wastes the entire run** — the fill is small, the
measurement cannot separate the two answers, and nobody finds out until the
analysis runs the next day.

---

## Why those numbers

Measured from your own Monza practice, not estimated: **1:46.8 a lap**,
**6.22 L a lap** at 3× fuel. The tank is 100 L, and because GT7's tank is 100 L
the MFD percentage *is* litres — 35 % is 35 L.

| | Arithmetic | |
|---|---|---|
| Burn | 6.22 L/lap on a 100 L tank | **≈ 6 % a lap** |
| Arrive at A, lap 5 | 100 − 5 × 6.2 | **69 %** — no fuel needed |
| Arrive at B, lap 12 | 100 − 12 × 6.2 | **26 %**, so a **74 L** fill |
| Arrive at C, lap 20 | 100 − 8 × 6.2 | **50 %**, so a **50 L** fill |
| Race length | 25 × 1:46.8 | **≈ 45 min**, stops included |

**Stop C is the measurement.** The whole run exists to tell two answers apart:

- **serial** — tyres go on, *then* fuel goes in: stop C ≈ A + fuelling time
- **parallel** — both at once: stop C ≈ dead time + the *longer* of the two

Those two predictions differ by exactly **the shorter of (tyre change, fuelling
time)**. A 50 L fill takes 50 s at 1 L/s or 7 s at 7 L/s — either way, far
longer than the app can confuse with noise. **A 10 L fill would take 1.4 s at
7 L/s, and the run would prove nothing.** Hence the arrival numbers.

### Why 1× tyre wear when you race at 8×

At 8× a set of RM lasts about **five laps**, so the car would be undriveable by
lap 20 and you would be forced into stops the protocol did not ask for. M0
measures the *pit stop* — how fast fuel goes in, how long tyres take, what the
lane costs. None of that depends on how quickly the rubber wears. Fuel stays at
**3×** because it has to draw the tank down far enough to take a big fill.

---

## If it goes wrong

| What happened | Do this |
|---|---|
| Boxed on the wrong lap | **Carry on.** The analysis finds stops from the telemetry, not from the lap numbers here. Note it afterwards |
| Took fuel at stop A by mistake | **The run is void for A.** Finish anyway, then repeat |
| Declined tyres at C by mistake | **The run is void for C.** Finish anyway, then repeat |
| Arrived too full and boxed regardless | Finish, then repeat. Say so — the analysis may call it inconclusive on its own |
| Spun, went off, damage | **Carry on.** None of it touches the measurement |
| Forgot to start the recording | **Stop. Restart the race.** There is nothing to analyse |
| Game crashed mid-race | Whatever was captured before the crash is still readable. Stop the recording, keep the file, repeat the run |

---

## Void — worth repeating

The run is void if **any** of these is true:

1. **Nothing was recorded.** Pit Crew says so when you stop the recording.
2. **Fewer than three stops** are in the file.
3. **The stream dropped during a stop.** A hole means every duration is a
   floor, not a measurement, and the analysis will refuse rather than quote it.
4. **A stop did the wrong thing** — fuel at A, no tyres at C.
5. **The fill at C was too small to separate the two answers.** The analysis
   says *"inconclusive — repeat with a larger fill"* and it means it. Do not
   accept the number it did not give you.
6. **The capture is not format C.** Pit Crew says so on stop. Reconfigure
   SimHub and go again.

Points 1, 3, 5 and 6 are checked for you. **Points 2 and 4 are yours** — they
are the ones only you saw.

---

## When you come in

1. Settings → **Stop recording**. Read what it says. It names the file.
2. Run:

```bash
python tools/analyse_m0.py captures/<the-file>.pcap
```

It prints the constants and writes them next to the capture. It will tell you
plainly if the run was void, and what to change.

**Nothing goes into the strategy model yet.** These are measurements; using
them is a separate decision with its own review.

---

## What this buys

Four numbers the app currently guesses, and one it asserts without evidence:

- **Refuel rate.** Typed in as 1 L/s today, and it decides the stop count on
  its own. Community measurement suggests 3–7 L/s. If it is 7, the fuel-saving
  doctrine this project is built on is **seven times weaker** than assumed.
- **Tyre-change time.** Not in the model at all.
- **Pit-lane delta.** Typed in as 19 s.
- **Serial or parallel.** Not in the model at all, and it changes every
  two-stop calculation.
- **The position field.** Confirms from your own capture that GT7 reports no
  live classification, rather than taking a forum's word for it.

Half an hour in the car.
