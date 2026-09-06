# Daytona Road Course — GR3 Season 1 Round 6 — race brief, 7 Sep 2026

**Written 6 Sep 2026, late, by Ludo. This is the driver's written brief.** The
car-state file is `brain/car-state/huracan-daytona.md` and restates nothing here;
the plan is strategy **28** (approved, with a playbook); the knowledge row is
event 10's. Everything below is either measured with its source, or labelled.

```
  20 LAPS · 1 mandatory stop · fuel ×3 · tyre ×2 · refuel 1.0 L/s
  STANDING start · grid by FASTEST LAP · weather RANDOM (inters and wets allowed)
  damage HEAVY · ABS Weak · Huracán GT3 '15 · hub sign-in CONFIRMED
```

---

## 1. The plan — 11 + 9 on RS, box on lap 11, tyres YES

| | |
|---|---|
| Stint 1 | 11 laps, 100 L → ~14.6 L at the box, burn ~7.8 L/lap `[MEASURED s127, 4 Sep race]` |
| **Box** | **at the crossing that completes lap 11 — George calls it; the in-lap is lap 12 on the HUD** |
| Fill | ~55 L at 1.0 L/s `[MEASURED 1.003, 4 Sep]` + 7 s dead time `[MEASURED]` ≈ 62 s standing |
| Tyres | **YES, RS.** RR wear 0.0570/lap `[MEASURED s118 laps 2–9, ×2]`: a set reaches lap 14.9 at the 0.85 ceiling. One set cannot do 20. George will say "RS" at the box call, which is right. |
| Stint 2 | 9 laps on 69.4 L |

**The stop lap is free inside the tank.** The litres added are the same whichever
lap you stop on, and the hose is the slow part, so **stop early rather than late**
if traffic or a gap makes an earlier stop attractive — anywhere from lap 9 on
still fits the tank for the run home.

### The one rule that overrides George's number

> **If you box when George calls it, or earlier, his litres are right. If you box
> late — lap 12 done or later — take laps left × this stint's burn plus the margin
> and ignore his number.**

Why: George's fill logic can *raise* the plan's 9-lap stint to the laps actually
left but cannot *lower* it (`race/calls.py:1467`). It cost P2 at Deep Forest last
night — a 10-lap fill with 7 to go, 19.7 L over the line, 9.9 s parked. Fix is
in this week's work; not in the car tomorrow. On a 1 L/s hose every litre you
do not need is one second standing still.

### Playbook George is running (strategy 28)

| trigger | action | when |
|---|---|---|
| fuel short | **short-shift** (his call: "Short-shift and lift") | tank misses the stop or flag by > 0.5 lap |
| fuel long | report only | > 1.5 laps in hand |
| stop missed | re-cost to the flag, name the new lap **once** | lap 12 completed without a stop |
| incident | report only | > 8 s lost |
| rain | report only — **you tell him**; George cannot see rain | any wet reading |
| safety car | *unhandled on purpose* | no channel, no lobby setting |

Never a fuel-map call. Map 1, always.

---

## 2. What the car will and will not say

- **Tyre gauge: armed.** The brief will say so from tomorrow (the line that said
  "No tyre gauge" was reading a name that did not exist — fixed tonight).
- **Other cars:** George still opens with "I can't see other cars — position
  only" and that line is wrong; the pit wall reads gaps and rival stops. Ignore
  the sentence, not the calls.
- **Shift beep — gears 1, 2, 3 only, at 8600 rpm** (the limiter is the fastest
  upshift in all three, measured off s127, hard cut ~8660). **Gears 4, 5, 6 are
  silent on purpose**: the next gear was never driven low enough to compare, so
  nothing honest can be issued. Short-shift table 7450 in 1–3 `[in-house v1.71
  measurement, ~1200 rpm below the limiter, −21.6% fuel]`.
- **Rain:** George cannot see it. Say "rain" on the radio and the plan is void.
- **Damage:** on the HUD car icon; George cannot read it yet. Say it.

---

## 3. Rivals — the GR3 field, from the hub (1 day old)

Sign-ins tomorrow: **Magical daddy** (GT-R), **CruisingChaos** (296), **Boxhead**
(Huracán), **PUNISHED** (296), TommyTbone (992), K_Graebs (AMG), Corn_flake (992).
Not signed in yet: Rocky, Pooy01.

Your GR3 season: **Q4, Q4, Q5, Q7, Q7 — won Round 3 at Watkins from Q5.**
Quali gap to pole by round: 1.60 / 1.60 / 1.13 / 2.35 / 3.53 s. Race-lap gap to
the fastest lap: 1.15 / 1.19 / **0.18 (you set P1 pace)** / 1.91 / 4.82 s. The
qualifying gap is the bigger number at every round but Watkins.

**The two to cover:** Magical daddy (pole 3 of 5, never off the podium) and
CruisingChaos (fastest lap 3 of 5, P2/P3/P5/P3/P2 — quicker in the race than on
the grid). Boxhead is in the same car as you and has qualified P2/—/P1/—/P5;
his race pace has faded relative to quali this season (Rd5 P5 from Q5, best lap
1.7 s off). PUNISHED is P4 at three of five rounds and will be around you on the
grid.

Nothing here reads any rival's stop habits — the rival book has never held a row
(the column defect is Phase 0 work). What George *will* say: who has boxed and on
how much fuel, and "box now and X comes out in front".

---

## 4. Pit loss — measure it tomorrow in practice

**Declared 20 s on the event; never measured here.** Provisional from the 4 Sep
race lap rows: pit lap 123.2 s + out-lap 162.1 s − 2 × ~104.5 s clean = ~76 s,
of which ~49 L at 1 L/s ≈ 49 s and dead time ≈ 7 s, leaving **~20 s ex-fuel** —
straddle-affected (the refuel sat inside the "out-lap" row), so it is a
corroboration of the declared figure, not a measurement.

**Recipe for tomorrow, one run:** drive in, stop, take *no fuel* (or note the
litres), drive out. Pit loss = (in-lap + out-lap) − 2 × your clean lap. Say the
three numbers on the radio; they go into the knowledge row as `pit_loss_s` with
this recipe as the source. The event row stays "declared" until the app has a
writer for a measured value.

---

## 5. What is open on the car

From `brain/car-state/huracan-daytona.md`: the issued-never-run
`dc 28/26 → 20/20` and `lsd_b 40 → 35` are **not** for a race day. Race the
baseline (410/635, cam 2.0/1.2) you raced on 4 Sep. Rank zero: a settings
screenshot before the first run tomorrow, and brake balance by voice.

---

## 6. Before you go out — the checklist

1. Settings screenshot → confirm against `huracan-daytona.md`. Brake balance said aloud.
2. Strategy screen: **strategy 28 approved** — confirm it shows the playbook.
   (Strategy 17 is demoted to candidate.)
3. OBS projector open; the pre-flight now *asks* on a timeout instead of blocking.
4. Practice: the pit-loss run (§4), then a 3-lap clean run for the burn at race load.
5. On the grid: George opens with "20 laps, 1 stop". Tyres YES at the stop.
   Box when called or earlier; if late, the rule in §1.
