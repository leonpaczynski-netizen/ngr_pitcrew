# Monza post-patch test plan — RSR, 24 Aug 2026

**Porsche 911 RSR (991) '17 · Autodromo Nazionale Monza, Full Course · GT7 v1.71 ·
8× tyre / 3× fuel · ABS Weak · TCS 0 · fuel map 1 · sheet 3 "Monza race v2".**

Written before driving, from `data/pitcrew.db` and `brain/_inbox/17-v1.71-measured-results.md`.
Every figure carries its version. Nothing pre-20-Aug is treated as current.

---

## 1. Where the app actually stands

`build_inputs(store, 1)` this morning. This is the app's own account, not mine:

| Input | Value | Source | Note |
|---|---|---|---|
| Evidence version | 1.71 | measured | **12 laps.** 206 laps on 1.70 held back — a physics update makes them history |
| Reference lap | 1:51.988 | measured | recency-weighted over 11 counted laps, one session |
| Fuel per lap | 5.28 L | measured | but flagged **two populations**: 9 laps at 5.28, 2 at 6.74 |
| Fuel capacity | 100 L | measured | from the stream |
| **Tyre wear** | **—** | **MISSING** | *"no compound has a measured wear rate"* |
| **Compounds compared** | **—** | **MISSING** | RM and RS are unplannable — untested compounds are excluded, not down-weighted |
| Refuel rate | 1.00 L/s | **declared** | never measured at this circuit |
| Pit loss | 19.0 s | **declared** | KB estimates 20–22 s; Watkins measured 15.7 against 20 declared |
| Pit dead time | 7.5 s | **assumed** | |
| Time of day | 15:56–20:56 | **MISSING** | race sweeps 5 h of game time at ×6. Practice has only ever covered 16:13–18:31 |
| Fuel weight | 0.003 s/L/lap | assumed | derived, never measured |

`recommend()` returns three feasible plans, all **fuel-bound**, because `wear_per_lap` is
`None` — the tyre constraint is switched off entirely. The 11-lap first stint it picks is
not a decision about tyres; it is the absence of one.

**One number — `w`, wear per lap on RH at 8× — is worth more than everything else on this page.**

---

## 2. Answered already. Do not spend a stint on these.

Read off stored frames this morning. Standing Rule 13 applied throughout: every post-patch
query was re-run over pre-patch sessions before it was called a finding.

### 2.1 LSD acceleration — the axle is already locked

Corner-exit frames (throttle ≥ 80 %, |steering| ≥ 5°, ≤ 200 km/h), inside-minus-outside rear slip:

| Session | n frames | p25 | p50 | p75 | p95 |
|---|---:|---:|---:|---:|---:|
| 58 — pre-patch race | 25,982 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| 60 — **v1.71** | 16,209 | 0.0000 | 0.0000 | 0.0000 | 0.0010 |

The **front** axle, open, over the same frames reads a median gap of 0.0093. That is the
control that proves the channel resolves per-wheel differences. The rear's zero is real.

**At `lsd_a 14` the rear axle is fully locked at corner exit, pre and post patch.** Raising
acceleration lock cannot buy exit traction, because there is no differential slip left to
remove. What slip exists is the *whole axle* spinning together — median 1.0233 post-patch,
down from 1.0506, consistent with `17` §1.

This overrides `17` §9's *"re-test upward from 14 — highest-value single-slider test."*
That was sound from the slip headline alone; the per-wheel split refines it. What it does
**not** settle is the KB's Monza-specific stability argument for keeping accel low (15–22:
*a locked diff snaps on the kerb strike*). That is a feel question — §6, not a stint.

### 2.2 Brake balance — the front is the limiting axle here, not the rear

Braking frames (brake ≥ 50 %, ≥ 60 km/h), worst wheel on each axle:

| Session | Front median | Front < 0.90 | Rear median | Rear < 0.90 |
|---|---:|---:|---:|---:|
| 52 — pre-patch race | 0.9000 | 49.9 % | 0.9250 | 2.2 % |
| 58 — pre-patch race | 0.8901 | 54.8 % | 0.9221 | 2.1 % |
| 60 — **v1.71** | 0.9119 | 42.9 % | 0.9552 | **0.00 %** |

**The RSR at Monza on ABS Weak locks its fronts, not its rears** — on both versions, by a
wide margin. Post-patch the rear does not reach 0.90 in a single braking frame out of 5,726.

This matters because `brain/driver.md` records you running **`bb −1`** — one click forward —
for a rear-lock complaint. That complaint is from **Road Atlanta, in the Shelby, with ABS
Off.** Different car, different assist regime, opposite axle. **Do not carry `bb −1` into
the RSR on the strength of it.**

By the same measurement, `lsd_b 24` is not solving a problem at Monza either.

⚠️ Both readings assume the sheet is what is in the car. See §3.1.

### 2.3 The wear geometry — and the knowledge base has it backwards

Session 52 (18 Aug, 1.70 race), gauge read off the recording, both stints fitted independently:

| Corner | Stint 1, 15 laps | Stint 2, 10 laps | r² |
|---|---:|---:|---:|
| **RL** | **0.0577 /lap** | **0.0602 /lap** | 0.997 |
| FL | 0.0517 | 0.0555 | 0.996 |
| RR | 0.0482 | 0.0495 | 0.994 |
| FR | 0.0346 | 0.0371 | 0.978 |

Two independent sets, four corners, agreeing to 4 %, r² ≥ 0.978 on every fit. **This is the
best instrument the app has, and it is the one that has produced nothing for five sessions.**

- Worst corner **rear-left**, 0.0590 /lap → **0.85 / w = 14.4 laps** at 8×.
- Left-to-right spread: front **1.49×**, rear **1.21×**.
- `05-track-reference.md` §1.5 says *"front-right takes more than front-left (Lesmos and
  Parabolica are rights)"*, and its summary table repeats it. **Your own gauge refutes it:
  FL 0.0536 against FR 0.0359, a 49 % gap the other way.** Right-handers load the left
  tyres; the KB has the sign backwards. Its *"rear-biased"* claim is confirmed.

**All of this is 1.70 and is void as a number.** It stands as the shape to compare against,
and as proof the measurement is worth taking.

### 2.4 Already measured on 1.71 — no work needed

From `17`: driven-wheel slip −52 to −62 % by gear · Vmax 274.9 km/h, below the floor of
twenty pre-patch sessions · short-shift saving −21.6 % · rev limiter unchanged at ~8,600 ·
slider ranges re-read and verified (LSD initial 0–30, accel 0–100, braking 0–99; damper
expansion ceiling 50→60; everything else unchanged).

---

## 3. Rank zero — fifteen minutes, no driving

### 3.1 What is actually in the car

The setup record has been wrong in five consecutive sessions. **Read the four garage pages
and tell me what they say** — do not read them off the app. In particular:

- **Brake balance.** The sheet says `0`. You have been running `−1` elsewhere.
- Camber F/R — sheet says 1.0 / 1.0
- Toe F/R — sheet says 0.00 / +0.08
- LSD — sheet says 5 / 14 / 24
- Downforce — sheet says 370 / 540

A correct telemetry reading against a wrong setup record produces a confident wrong answer.
Everything in §2 is conditional on this.

### 3.2 Flat screen or PSVR2? — this decides whether the morning works

In VR, GT7 draws the HUD **on the car's dashboard in 3D**, so the wear gauge moves with your
head and leaves the calibrated rectangle whenever you look into a corner. The sampler knows
this and says so; it cannot fix it.

- **Flat screen** → the gauge is readable at fixed geometry. Proceed as planned.
- **PSVR2** → drop `hud_sample_interval_s` from 10 s to **2 s**, so the free-running sampler
  catches the frames where you are looking forward, and treat the OBS recording as the
  primary source rather than the backstop.

### 3.3 The gauge pre-flight — three laps, and it is not optional

The live sampler answered **6 laps of 21** at Road Atlanta on 23 Aug, and the six it did
answer were not monotonic:

```
session 77, laps 8–11    FL 0.333 0.333 0.444 0.429     RL 0.300 0.353 0.350 0.368
                         FR 0.200 0.286 0.250 0.211     RR 0.250 0.444 0.200 0.200
```

Wear is monotonic. **The left pair climbs cleanly; the right pair does not** — same pattern
in session 71. Session 52's readings, taken from the *recording* through
`tools/read_hud_wear.py`, are monotonic on all four to r² 0.99.

So: **run three laps and check all four readings climb.** If the right pair jitters, the
live path is not fit to measure `w`, and the video is the measurement rather than the backstop.

> **Record in OBS for every stint, and tell me the file path.** The 0.5 %-agreement
> measurement in §2.3 came off a recording. Live sampling is a convenience; the file is the
> evidence.

### 3.4 App switches

- `active_event_id` is **5 (Road Atlanta)**. Switch it to **1 (Round 8 Porsche Cup)**.
- Confirm `game_version` reads **1.71**. It does in `app_state`; event 1's own field is still
  NULL — cosmetic, sessions stamp correctly, I will fix it.
- `hud_wear_enabled` on, `hud_source` obs, interval per §3.2.
- Test suite is green this morning, including the uncommitted engineer work.

---

## 4. The stints

Total ≈ 2 h 05. **If there is time for one only, it is Stint A.**

### Stint A — the 50-minute rehearsal · ~55 min · THE ONE THAT MATTERS

Arm it on the race screen as a **rehearsal**, at last week's exact lobby settings: 50 min,
8× / 3×, rolling start, ABS Weak, TCS 0, changeable/Random, RH, full tank, map 1.

A rehearsal records laps *and* runs the engineer, and rehearsal laps carry **double weight**
in the evidence model. It is the only session kind that tests both halves at once.

**Laps 1–15 — race pace, short-shifting throughout. No mode changes.** Keep it one clean
population. Run to the gauge showing ~85 % on the worst corner; that was lap 14–15 on 1.70.

**Then box, and make the stop deliberately awkward:**

- Take a number you will remember — **fill to 62 L**, not "fill it".
- Fresh RH.
- Do not touch brake balance during the stop.

That one stop measures the refuel rate, the dead time and the pit loss, all three of which
are typed-in guesses today. At 1 L/s a 60 L splash is a minute of the race; a 15 % error in
the rate is nine seconds of plan.

**Laps 17 to the flag — alternate short-shift and full RPM, lap about lap.** Five clean
full-RPM laps at map 1 is exactly what `17` §3 asked for to settle fuel, and interleaving
them is exactly what §7 asked for to settle pace. Both close in one stint.

**Delivers:** `w` per corner post-patch · wear asymmetry against the §2.3 shape · both fuel
populations · refuel rate, dead time and pit loss measured · pace with modes interleaved ·
clock coverage into the dusk hours nobody has driven · the engineer, PTT, haptics and box
logic under a full race duration.

> The engineer will stand down on tyre calls for this whole stint, because it has no wear
> model. **That is correct, and I want to hear it say so.** If it goes quiet instead of
> saying *"I cannot see them"*, that is a defect and I want to know.

### Stint B — Racing Medium · ~22 min · 10 laps

Fresh RM, full-ish tank, race pace, short-shifting. Gauge reading at the end.

**Why it earns 22 minutes:** the app plans only tested compounds. RM and RS are not risky
options tonight, they are *absent* ones. Ten laps makes RM plannable. At 27 race laps with
RH binding near 14, whether a second compound exists changes the shape of the race, not a
tenth of a lap.

### Stint C — one setup change · ~25 min · 12 laps

**Choose it from Stint A's asymmetry, not from this page.** The rule:

| What Stint A shows | The change | The channel that resolves it |
|---|---|---|
| Rear/front ratio **> 1.30** (rear-limited) | `toe_r` 0.08 → **0.25** | rear `w`, and Vmax in 6th |
| Front/rear ratio **> 1.15** (front-limited) | `cam_f` 1.0 → **3.0** | front `w` |
| Left/right front **> 1.6** | `cam_f` 1.0 → **3.0** | FL-to-FR ratio |
| Shape close to §2.3, nothing limiting | `df_r` 540 → **500** | **Vmax in 6th** |

One change. Twelve laps. Same fuel load and same shift discipline as Stint A's first stint,
so the comparison is like-for-like.

### Stint D — optional, if time remains · ~20 min

Downforce is the one lever at Monza whose effect is *large* and whose channel is *precise*.
Vmax in 6th resolved a 3.9 km/h change against a 6.5 km/h historical spread in `17` §2 —
lap time cannot come close. `df_r` 540 → 500 is 20 % of the range, at the circuit where the
KB says run minimum wing and where you sit at 20 %.

---

## 5. What each stint can and cannot resolve

**Read this before deciding a change "worked".**

Your lap-to-lap σ at Monza is **≈ 0.7 s**. Comparing two setups with *n* clean laps each,
the 95 % interval on the difference is **1.94 / √n seconds**:

| Laps each | Smallest lap-time difference that is real |
|---:|---|
| 5 | ±0.87 s |
| 8 | ±0.69 s |
| 12 | ±0.56 s |
| 20 | ±0.43 s |

**A camber click is worth a tenth or two. It is invisible to the stopwatch in any stint you
can drive this morning, and it stays invisible if you drive all day.** Same for a toe click
and an ARB click.

What *can* resolve a small change:

| Channel | Precision | Resolves |
|---|---|---|
| **Gauge wear rate** | ~4 %, r² 0.99 over a 15-lap stint | camber, toe, brake balance — anything moving load distribution |
| **Vmax in 6th** | ~0.3 % across 20 sessions | downforce, toe, gearing, drag |
| **Per-wheel slip** | per-frame, tens of thousands of samples | LSD, traction, lock-up — and already on disk |
| Corner `min_kph` | multi-lap trend only | grip changes, coarsely |
| Lap time | ±0.6 s at best | nothing you will change this morning |

And what cannot be resolved at all: **camber by tyre temperature.** GT7 reports one surface
temperature per wheel — no inner/mid/outer split — so the standard camber validation does
not exist in this game. Anyone claiming otherwise is quoting a different simulator.

⛔ No per-corner input coaching comes out of this, from me or the app. Brake-point 2σ is
14–37 m and throttle-on 2σ is 11–51 points on your own 307 clean laps. *"Brake ten metres
later at Ascari"* is not a sentence the data supports.

---

## 6. The assumption ledger

Everything you named, plus what I would add. **A** = measurable this morning · **F** = already
answered from frames · **N** = not resolvable today, don't try.

| Assumption | Currently | Status |
|---|---|---|
| **Camber 1.0 / 1.0** | 17 % of range, unchanged since pre-patch | **A** — gauge asymmetry only, big step only, and only if Stint C's rule points at it |
| **Toe 0.00 / +0.08** | rear toe is dead centre | **A** — rear `w` and Vmax both resolve it |
| **Brake balance 0 (sheet)** | you may be running −1 | **F** — front is the limiting axle here; §3.1 first |
| **LSD 5 / 14 / 24** | accel 14 | **F** — axle already locked; not a stint |
| Wear `w` on RH at 8× | **none, any compound** | **A** — Stint A. The morning's reason for existing |
| Wear on RM | none | **A** — Stint B |
| Refuel rate 1.00 L/s | declared, never measured | **A** — Stint A's stop |
| Pit loss 19.0 s | declared; KB says 20–22; Watkins ran 4.3 s optimistic | **A** — Stint A's stop |
| Pit dead time 7.5 s | assumed | **A** — Stint A's stop |
| Fuel 6.74 L/lap full-RPM | provisional, n = 2 | **A** — Stint A's interleaved laps |
| Pace on 1.71 | unmeasured; modes confounded with familiarity | **A** — Stint A's interleaved laps |
| Dusk grip and clock | race runs to 20:56; never driven past 18:31 | **A** — Stint A, clock at ×6 from 15:56 |
| Short-shift seconds cost | unmeasured; moves the optimum 400↔2800 rpm | **N** today — needs a 1500 rpm separation and its own session |
| Fuel weight 0.003 s/L/lap | assumed | **N** today |
| Multiplier linearity | assumed, never demonstrated | **N** ever, from one multiplier |
| Corner model | auto-segment, 6 corners, 5746.9 m against 5793 m real | **N** — and `lap_distance_m` is unreliable on 8–12 % of Monza laps, so those laps' corner aggregates describe the wrong road |

**What no channel carries** — answer these into the app or over PTT as you go. They are the
half only you have:

1. What is actually in the car (§3.1).
2. Does the car snap on the kerb exits at Rettifilo and Roggia? That is the open half of the
   LSD question and §2.1 cannot see it.
3. Did the *wheel* feel different after the patch, separately from the car? On an 18 Nm base
   an FFB change reads exactly like a grip change. (Auto Setup was confirmed untouched on
   21 Aug, so this is about feel, not settings.)
4. Was the air clean? Monza is the tow track; a lap in traffic is not a lap.

---

## 7. Engineer and PTT — the pre-race check

PTT is enabled in practice (`ptt_in_practice`), backend **moonshine**, key **b**, tap to
toggle. The engineer's calls only run when a race or rehearsal is armed — which is why
Stint A is armed as a rehearsal rather than run as practice.

**Say one from each group during Stint A.** Eighteen intents, 230 phrases; these carry a decision:

- `fuel` · `laps left` · `what's the plan` · `are we on the plan`
- `when do i box` · `what tyres` · `how much fuel do i take`
- `accept` / `keep` — the offer round-trip, and it must not repeat itself
- **`how are my tyres`** — the one I most want tested. It should answer *"I cannot see them"*
  today, not a compound name. It answered with the stop's compound as recently as 22 Aug.
- **`what's my pace`** — also new
- `understeer` / `oversteer` / `i went off` / `traffic` — the report side
- `say again`

Log what it *mishears*, not only what fails. Below 0.34 confidence it is 82 % correct and
above it 80 % — distance barely predicts correctness, so the interesting failures are the
confident wrong ones.

---

## 8. Afterwards — mine, not yours

`grip_observations` stops at **session 52**. Nothing has been derived since 18 Aug, so every
1.71 session — Spa, Road Atlanta, and the post-patch Monza run — has contributed **nothing**
to any tyre model. Every model in the database was fitted on 1.70 data on 18 Aug.

When you are done:

1. `python tools/read_hud_wear.py --session <id> --video <path>` per stint, `--apply` once
   the readings look monotonic.
2. `python tools/derive_grip_observations.py --event 1 --apply`
3. `python tools/fit_tyre_models.py --apply` — and read the *"not yet"* half of the report,
   which is the half that says what tonight's engineer still may not say.
4. Re-run `build_inputs` and `recommend()`. If `w` lands near 0.059 the one-stop stands and
   the stop window is laps 13–15. If it has moved, the plan moves with it.
5. Write the results into `brain/_inbox/17-v1.71-measured-results.md`. §8's *"tyre gauge
   readings — none, fifth session running"* is the line this morning exists to delete.

---

*Written 24 Aug 2026 · GT7 v1.71 · against `data/pitcrew.db` sessions 52, 58 and 60,
`brain/_inbox/17-v1.71-measured-results.md`, `brain/driver.md` and
`brain/_inbox/05-track-reference.md` §1.5*
