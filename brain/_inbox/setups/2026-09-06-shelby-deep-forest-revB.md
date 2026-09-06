═══════════════════════════════════════════════════════════════════
  FORD SHELBY GT350R '16  ·  DEEP FOREST RACEWAY — FULL COURSE
  **ROUND 6 SUPERCARS — Rev B · GEARBOX ONLY**
  After session 133 · 5 laps · 6 Sep 2026 · v1.71
  Values: `brain/car-state/shelby-deep-forest.md` — nothing restated here
═══════════════════════════════════════════════════════════════════

# 1. What you said, and what the data says about it

> *"Car feels pretty good — just some gears are between corners, so changing
> some ratios would be good."*

**You are right, and the telemetry says it harder than you did.** This is not a
case of one badly placed crossover. **The entire top of the box is a wall.**

Across 4 clean laps and 21,780 frames, every gear-stint in 3rd, 4th, 5th and
6th ended at the gear's own ceiling rather than anywhere you chose:

| gear | tops at | stints/lap | peak actually reached |
|---|---:|---:|---:|
| 3 | 173.1 | 6.8 | — |
| 4 | 203.1 | 6.8 | **199.3** median · 11 of 27 peaked 199-203 |
| 5 | 230.8 | 4.0 | **230.1** median |
| 6 | 261.5 | 1.8 | **261.1** median · **Vmax 265.2** |

**The upshift scatter is the proof.** Where you have a choice, your shifts
spread out — up 1→2 spans **32.0 km/h**, up 2→3 spans **20.3 km/h**. Where the
box decides, they do not:

```
   up 3->4   164.2 - 168.3 km/h     span 4.1 km/h
   up 4->5   198.7 - 202.8 km/h     span 4.1 km/h
   up 5->6   228.6 - 233.1 km/h     span 4.5 km/h
```

A four-kilometre-an-hour window over four laps is not a driving decision. **The
limiter is choosing your shift points, and some of them land between corners.**

And 6th does not even reach the end of the straight: **998 rev-limiter frames**,
which is **4.6% of the lap spent pinned against the limiter producing no
acceleration at all.**

---

# 2. The change — one component, one verdict

```
   OLD   3.400 / 2.410 / 1.760 / 1.500 / 1.320 / 1.165     fg 3.600
   NEW   3.400 / 2.330 / 1.600 / 1.360 / 1.205 / 1.085     fg 3.600
```

**K = 304.6 km/h**, re-derived from this session — limiter median 8,798 rpm,
constant 0.03463 across all six gears with 3.6% spread. **[MEASURED]**, and it
is the **third circuit** to return 304 after Road Atlanta and Red Bull Ring.

| gear | old top | **new top** | |
|---|---:|---:|---|
| 1 | 89.6 | **89.6** | unchanged |
| 2 | 126.4 | **130.7** | lengthened only to protect the drop into 3rd |
| 3 | 173.1 | **190.4** | ← **this is the change** |
| 4 | 203.1 | **224.0** | forced by 3rd |
| 5 | 230.8 | **252.8** | forced by 4th |
| 6 | 261.5 | **280.8** | 15.6 km/h of headroom over today's Vmax |

## 2.1 Why 3rd, and how much it is worth — **[MEASURED]**

Of **27 fourth-gear stints** across the four clean laps, **9 never exceeded
190.4 km/h.** They were short hops between linked corners — 0.5 s to 6.0 s long,
entered at 149-166 and peaking at 177-186. Every one of them is an up-and-down
you did not need:

```
   164.7 -> 186.0    155.0 -> 185.4    165.8 -> 184.0
   149.4 -> 182.5    166.2 -> 181.1    164.4 -> 178.6
   165.3 -> 178.4    164.8 -> 177.9    164.8 -> 177.6
```

**A 3rd topping at 190.4 absorbs all nine — about 4.5 gearchanges per lap
removed.** That is your report, measured.

## 2.2 The cascade is forced, not a preference

I am not re-cutting four gears because I feel like it. **Lengthen 3rd to 190 and
4th at 203 becomes a 13 km/h gear. Move 4th to 224 and 5th at 231 becomes a
6 km/h gear.** Gears 3 to 6 move together or not at all. 1st and 2nd stay where
they are, and 2nd moves only 4 km/h to keep the 2→3 drop honest.

## 2.3 Every landing rpm sits on measured ground

The one risk in a longer 3rd is falling off the torque curve on the 2→3 shift.
It does not, and the archive says so:

| shift | lands at | what the accel table measured |
|---|---:|---|
| 1→2 | 6,033 rpm | landing at 5,843 gave **6.63 m/s²** against 6.29 for staying — *stronger after the shift* |
| 2→3 | 6,041 rpm | landing at 6,038 gave **4.67 m/s²** |
| 3→4 | 7,478 rpm | old ratio step 0.852, **new step 0.850** — unmoved |
| 4→5 | 7,795 rpm | old 0.880, new 0.886 |
| 5→6 | 7,922 rpm | old 0.883, new 0.900 |

---

# 3. The shift beep — re-issued for this box

```
   performance    1: 8500     2: 8500     3: 8250
   fuel saving    1: 8000     2: 8000     3: 7750
   gears 4, 5, 6  SILENT
```

- **3→4 = 8250 is [MEASURED] and transfers exactly.** The 3/4 ratio step is
  preserved to **0.2%**, so the crossover does not move — the archive's 6,932
  frames still describe it. *A spacing-preserving re-cut carries its shift point
  with it.*
- **1→2 = 8500 [MEASURED].**
- **2→3 = 8500 is [DERIVED, not measured on this box].** The step fell from
  0.730 to 0.686, and a bigger drop moves the optimum later.
- **4, 5 and 6 stay silent.** The archive holds 76 and 14 frames at those
  points and the re-cut did not change that. Fewer gears beats softer numbers.

**Re-measure with `tools/shift_points.py` after the next run.**

---

# 4. What OBS cost you, and what it did not

**Telemetry was fine** — 21,780 frames, all five laps, the gearbox read straight
out of the packet. Capture and the HUD gauge are independent.

**The tyre gauge got nothing.** `wear_fl` is null on all five laps. So **the one
question that decides one stop or two is exactly as open as it was this
morning**, and it is the most valuable eight laps you could drive today.

---

# 5. Fuel — I was wrong, and by a lot

**Predicted 6.5-7.0 L/lap. Measured 8.196 L/lap** (sd 0.088, n=4). **I missed by
18-21%.**

Both of my scalings failed the same way:

| | Road Atlanta | RBR Short | **Deep Forest** |
|---|---:|---:|---:|
| practice, per km | 1.586 | 1.798 | **1.927** |
| practice, per second | 0.0795 | 0.0830 | **0.0910** |

**Higher than any circuit on file on either axis.** The reason is structural and
I should have seen it: burn tracks *work done*, and **18 corners is 18
accelerations.** A corner-dense lap beats both distance and time scaling.

**What it does to the race** — race burn at the measured 3-9% practice discount
is **7.46-7.95 L/lap**, so the tank covers **12.6-13.4 laps** against a ~20.5-lap
race:

- **One stop, fuel-bound, and the window is lap 12-13** — earlier than the
  14-15 I gave you this morning.
- Two stops costs about **26 s more**, because the total fuel is the same and
  you pay a second transit and a second dead time for nothing.
- The stop is long: ~58 L at 2.0 L/s is **~29 s standing**, plus dead time,
  plus transit. **The fuelling is longer than the pit lane.**

---

# 6. One of my own proposals is closed by your report

*"Car feels pretty good"* is primary evidence, and it beats GT7's static
high-speed-understeer readout of −0.50 that I built the `df_r` 260 → 235 case
on this morning. **The aero test drops behind the gearbox and I am not asking
for it today.**

---

# 7. Runs

### Run 2 — the Rev B box · 3+ clean laps · **OBS ON**
The verdict is **your report and the shift count**, not the stopwatch — see §8.

### Run 3 — race-pace stint, full tank · 8+ laps · **OBS ON, and read the gauge**
Still the most valuable run available. It is the only thing that can close the
one-stop/two-stop question, and it also gives me the burn on the new box.

---

# 8. ⚠️ The next run cannot be judged on lap time

You went **94.093 → 90.232 → 89.948 → 89.100** across four laps on a circuit you
had never seen. That is nearly 5 seconds of learning in four laps, on a car
whose whole-lap noise floor is 0.918 s. **Learning here is far larger than any
gearbox effect, and it is one-directional — so the next run will be faster and
I will not be able to tell you how much of that was the box.**

What I *can* read is the shift count and where the shifts land. That, and what
you feel, is the verdict.

---

# 9. Predictions on the record

| Prediction | Falsified by |
|---|---|
| Gearchanges drop by ~4.5/lap; the linked sweeper sequence runs in one gear | you still report shifting between corners, or 4th-gear stints under 190 km/h persist in the frames |
| The 998 rev-limiter frames in 6th go to ~0, and Vmax rises above 265.2 | still hitting the limiter in 6th |
| The 2→3 shift does **not** feel flat despite landing 400 rpm lower | the car feels bogged out of the slow corners — if so, 2nd goes back toward 2.410 and 3rd to ~1.660 |
| Race burn lands **7.46-7.95 L/lap**; the stop window is lap 12-13 | a race burn outside that band |
| Lap time is **not** a usable verdict on this change | — this one is a refusal, not a prediction |
