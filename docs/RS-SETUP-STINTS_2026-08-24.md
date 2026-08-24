# The four RS stints — Monza, 24 Aug 2026

**Porsche 911 RSR (991) '17 · Autodromo Nazionale Monza, Full Course · GT7 v1.71 ·
8× tyre / 3× fuel · fuel map 1 · Racing Soft · four stints of four laps, 14:04–14:40.**

App stints **26–29** = database sessions **80, 81, 82, 83**. Written against
`data/pitcrew.db` sessions 78–83 and `logs/pitcrew.log`, adversarially re-derived,
and reconciled against the driver's own account of the four runs.

> **The driver's report is primary evidence and the telemetry is corroboration**
> (`CLAUDE.md` §4.1). It corroborates three of his four statements from channels
> that know nothing about them. The fourth disagreement is §2.4, and it is left as
> a disagreement.

---

## 1. The four stints were four independent single changes

| Stint | Session | Started | Change | Laps | Clean |
|---|---|---|---|---:|---:|
| 26 | 80 | 14:04 | original — sheet 3 | 4 | 3 |
| 27 | 81 | 14:13 | `cam_f` 1.0 → **3.0** | 4 | 2 |
| 28 | 82 | 14:23 | `toe_r` 0.08 → **0.25** | 4 | 2 |
| 29 | 83 | 14:31 | `df_r` 540 → **500** | 4 | 2 |

**That they were independent rather than cumulative is measured, not assumed.**
Fitting `susp_mm = a + b·(v/100)²` over ~8,000 straight-line frames per stint
separates static geometry (the intercept) from aero load (the slope). The front
static intercept reads 265.03 in stint 26, **270.40 in stint 27**, and **265.03
again in stint 28** — back to baseline to two decimal places. Something front-only
and static moved for stint 27 and was put back for stint 28, exactly as you
described. `body_height_mm` drops 2.7 mm across the same stint, half of 5.4, which
is what a front-only change does to a whole-car average.

⚠️ **It is not proof the front change was camber.** 1.0° → 3.0° on a 355 mm tyre
moves the wheel centre by 0.43 mm — an order of magnitude short of 5.4 mm — and
GT7's camber-slider-to-strut mapping has never been calibrated on this car. A
front ride-height change would look identical. **Worth one bench check**: set
camber alone on a stationary car and read `susp_mm_fl`. Until then the honest
statement is *front axle only, static, reverted afterwards*.

Stint 29's signature is aerodynamic and unambiguous: the rear's share of
suspension compression falls **2.9 points** (38.1 % → 35.2 %), rear aero slope
down 7.8 %, front up 4.3 %, static intercepts unchanged. That is a rear wing
coming off, with the rake increase that follows.

> **The sign convention is measured.** Under hard braking the front channels rise
> (+6.8, +30.8 mm) and the rears fall (−21.3 mm). Larger is more compressed.
>
> **"Compression share" is not "load share."** Converting needs the axle rates;
> at the sheet's 3.05/3.20 Hz and a 42/58 split the rear's *load* share is 48.3 %
> → 45.2 %, a −3.1 point move. The direction is the same; the level is not.

---

## 2. Your report against the telemetry

### 2.1 `cam_f 3` — "turns in way more, holds through the corner way better" ✅ CONFIRMED

Minimum speed through each corner, clean laps only (offs and spins dropped):

| Corner | orig | **cam_f 3** | toe_r .25 | df_r 500 |
|---|---:|---:|---:|---:|
| T1 Rettifilo | 65.5 | 65.4 | 66.6 | 61.0 |
| T4 Roggia | 92.1 | 93.1 | 93.6 | 91.1 |
| **T6 Lesmo 1** | 135.3 | **140.3 (+5.0)** | 138.3 | 138.2 |
| T7 Lesmo 2 | 132.5 | 133.4 | 133.7 | 134.7 |
| T8 Ascari | 130.2 | 131.3 | 135.5 | 128.5 |
| **T11 Parabolica** | 133.1 | **136.9 (+3.9)** | 135.4 | 137.0 |

**The gains land where you said they land** — the long, fast, sustained corners.
Lesmo 1 +5.0 km/h and Parabolica +3.9 km/h are the two largest single-corner
numbers of the morning, and mid-corner lateral g at Lesmo 1 rises from 1.988 to
2.192 (+10 %). The two slow corners gain nothing. That is a front-grip change, not
a driver having a good run.

### 2.2 `cam_f 3` — "rears became loose due to imbalance" ✅ CONFIRMED

Countersteer — frames where steering is applied against the yaw the car is
already generating, as a fraction of frames above 1.0 g:

| Stint | L1 | L2 | L3 | L4 |
|---|---:|---:|---:|---:|
| 26 orig | 0.00 % | 0.00 % | 0.24 % | 0.00 % |
| **27 cam_f 3** | **9.29 %** | 0.00 % | 0.37 % | 0.00 % |
| 28 toe_r .25 | 0.18 % | 0.13 % | 0.00 % | 0.13 % |
| **29 df_r 500** | 0.50 % | 0.00 % | 0.44 % | **7.16 %** |

**You lost it on lap 1 of the camber stint** — 9.29 % countersteer, 13.7 s
off-track, 0.95 s of spin. And the rears ran hottest of the three thermally
comparable stints: rear-axle lap means 67.2 / 65.9 / 65.7 °C against 65.0–65.3 for
the toe stint and 64.2–64.6 for the wing stint. **More front grip, more rear work,
hotter and looser rear.** Your diagnosis, from three channels.

### 2.3 `toe_r 0.25` — "getting on throttle much safer" ✅ CONFIRMED, and it is the strongest single result of the morning

Understeer factor — steering angle divided by the neutral-steer angle
(`L·yaw/v`) the car is actually achieving. Higher means more lock for less
rotation:

| Stint | entry / mid, off throttle | **on throttle > 50 %** |
|---|---:|---:|
| 26 orig | 19.08 | 29.86 |
| 27 cam_f 3 | 20.57 | 29.67 |
| **28 toe_r .25** | 22.47 | **36.66 (+23 %)** |
| 29 df_r 500 | 19.70 | 29.49 |

**On throttle the car needs 23 % more lock for the same rotation.** That is the
rear refusing to come round — precisely "safer on throttle" expressed as a
number, and it is the only stint of the four where the on-throttle figure moves at
all. Four laps, zero rear moments, countersteer 0.00–0.18 %.

The cost shows in heat, not in the stopwatch. Rear left-to-right temperature
spread widens from **+1.8 °C to +4.0 °C** and the front from +5.9 to +7.8 °C
(lap-matched). Rear toe-in scrubs, and Monza's right-handers load the left tyres,
so the scrub lands asymmetrically.

### 2.4 `df_r 500` — "rear looser" ✅ CONFIRMED · "wore rears faster" ❌ DISAGREES

Looser is not in doubt. On the two clean laps the countersteer rate is
**0.44 % and 0.50 %** — the highest of any incident-free lap all morning, against
0.00–0.24 % on the original — and lap 4 was a spin at 7.16 %. It also loses
minimum speed at Rettifilo (−4.4), Roggia (−1.0) and Ascari (−1.7) while gaining
at Parabolica: a car that will not settle on entry.

**The wear reading disagrees with you.** The gauge puts stint 29's rear-left at
**0.1375 /lap — the lowest of the four**, where you expected the highest. Two
things are true at once and both matter:

- The gauge cannot resolve a difference this small over four laps (§4), so it is
  not evidence *against* you, it is an absence of evidence.
- What you were feeling is visible in a different channel. Rear temperatures on
  the spin lap are the hottest of the day (RL lap-mean 71.8 °C, peak 102.6 °C
  against 64–67 °C everywhere else), and rear corner-exit slip is the highest of
  the four stints. **Rear temperature and slip, not consumed tread.** On a soft
  tyre those lead wear rather than record it, so over a longer stint you would
  probably have been right — this one was too short to show it.

**Surfaced, not averaged.** A twelve-lap stint on the wing setting would settle it,
and it is not worth twelve laps given §3.

---

## 3. What goes on the car

**`toe_r` 0.08 → 0.25: keep it.** It is the only change with a confirmed,
mechanism-backed driver benefit and no established cost. I had it down as a reject
on a straight-line number that has since failed to replicate (§5); that verdict is
withdrawn.

**`cam_f` 1.0 → 3.0: keep it, but not alone.** It is worth 3.9–5.0 km/h in the two
corners that matter most at Monza, and it took the rear away from you. Camber gave
the front; toe gives the rear back.

**⭐ The untested combination is the highest-value stint you have not run.**
`cam_f 3.0` **and** `toe_r 0.25` together. You tested them separately, and
separately each has one good half and one bad half. There is a specific reason to
believe they cancel: the camber stint's problem is on-throttle rear security, and
the toe stint's measured effect is +23 % of exactly that. Twelve laps, on **RH**,
back to back with a control.

**`df_r` 540 → 500: put it back.** It made the car looser in the direction you
already had a problem with, cost entry speed in three corners, and the top-speed
gain that justified it is at most 0.2 km/h and does not replicate on the main
straight (§5). At Monza the knowledge base says run minimum wing; **on this car,
on this evidence, the last 40 counts of it are not free.**

---

## 4. Wear — what the gauge can and cannot say

Gauge readings, `wear_source = hud-video`.

| Compound | worst corner (RL) | FL | RR | FR | stint at `0.85/w` |
|---|---:|---:|---:|---:|---:|
| **RH** (s78, 7 readings over 14 laps, r² 0.98) | **0.0493 ± 0.0031** | 0.0415 | 0.0418 | 0.0233 | **17.2 laps** |
| **RS** (s80–83, 4 stints of 4 laps) | **0.142** | 0.124 | 0.118 | 0.080 | **4.9 – 7.0 laps** |

**RS wears about 2.9× as fast as RH at 8×**, and that ratio is the one number here
worth carrying.

⚠️ **The six-lap headline needs its error bar.** The RH regression pins where in a
lap a reading is taken to only **±0.68 laps** (intercept se 0.033). On a fourteen-
lap stint that is noise; on a **four-lap** stint it is ±17 % of the rate, which
propagates to **4.9–7.0 laps** — the difference between a four-stop and a
five-stop race. Note also that the two compounds were fitted by different methods:
RH by seven-point regression, RS by a single point through the origin. Using both
RS gauge points instead gives per-stint slopes of 0.167 / 0.150 / 0.141 — a **17 %
spread between stints of the same tyre**.

**Which is the point.** The spread *between setups* is smaller than the spread
*between stints*, so **no setup effect on wear is resolvable from these stints, in
either direction.** That is an absence of measurement, not a null result.

And the instrument itself misreads. Inside the RH anchor stint alone the log
records three false fresh-set detections mid-stint (`gauge dropped 75 % to 42 %`,
`62 % to 27 %`, `68 % to 41 %`) with no tyre change, and fifteen afternoon readings
were refused for moving both ways at once by up to 25 points. A misread biased the
same way on all four corners passes the monotonicity filter and is accepted.

**The wear shape survives the patch, and `05-track-reference.md` §1.5 is still
backwards.** Left worse than right on both axles, on both compounds, worst corner
rear-left every time: RS front L/R 1.54, rear L/R 1.20; RH (computed the same way)
1.47 and 1.21. The KB's "front-right takes more than front-left" is wrong by
~50 % the other way on two compounds and two game versions. Its *rear-biased*
claim is confirmed again.

---

## 5. The straight-line instrument — claim withdrawn

I reported that rear toe cost 19 ms on the main straight and that the downforce
change bought nothing. **Neither survives replication and both are withdrawn.**

Monza has four full-throttle sixth-gear stretches. Measured over fixed distance
windows with entry speed regressed out — speed gained, km/h, against the original:

| Stint | str 1 (600 m) | str 2 (175 m) | str 3 (240 m) | str 4 (270 m) |
|---|---:|---:|---:|---:|
| 27 cam_f 3 | −0.19 | +0.04 | −0.08 | −0.06 |
| 28 toe_r .25 | **−0.61** | +0.01 | −0.00 | +0.01 |
| 29 df_r 500 | −0.15 | **+0.22** | **+0.17** | **+0.20** |

**Straight 1 contradicts straights 2–4 for both changes.** The toe deficit appears
only on the main straight and is dead zero on the other three; the downforce gain
appears on the other three and is negative on the main straight. Within-stint
scatter is 0.03–0.35 km/h, so this is a real disagreement between windows and not
noise.

Two further problems with my original figure: session 79 is the **same original
setup** as stint 26 and differs from it by +32 ms on the same fixed-distance metric
— larger than the toe effect I was reporting — and `t(100→765 m)` regresses on
entry speed at ~21 ms per km/h, so one km/h of Parabolica exit swamps everything
quoted. My "constant offset, therefore scrub not drag" inference had no power
either: v² varies only 24 % across the window.

**What survives:** on three independent straights, less rear wing is worth
+0.17 to +0.22 km/h — the physically expected direction, replicated 3/3, tight
scatter. It is a fifth of a km/h, and §3 spends it.

---

## 6. Three things confounded with stint order

**6.1 Stint 26 ran on cold tyres.** First frame, all four wheels: sessions 79 and
80 start at **45.0 and 48.2 °C**; sessions 78, 81, 82 and 83 all start at
**exactly 70.0 °C**. The gap is 17–20 °C on lap 1, still 3.5–5.2 °C by lap 4, and
stint 26 never reaches the ~62 °C the others settle at. Its lateral-g p95 is 1.732
against 1.816–1.864 for the variants — but session 79, same setup, reads 1.811, so
that is commitment, not grip.

**I do not know what selects 45 °C over 70 °C.** Session 78 also followed a long
break and got 70, so my "cold soak" explanation is wrong. Until it is understood,
**treat the first stint after any gap as thermally suspect.**

**6.2 The game clock.** 16.35 → 17.29 → 18.26 h, then frozen at 18.8333 — and the
freeze starts inside stint 28's lap 4, not at stint 29. Monza's stored
`track_clock` says start 16.213, ×6, ceiling 18.833, and I measure exactly 6.00×.
Every variant ran later in a dimming game day than the control.

**6.3 Driver warm-up.** Stint means fall monotonically 109.44 → 109.08 → 108.69 →
108.77 s. That is ~0.7 s of improvement perfectly collinear with setup order.

**6.4 And the fans died inside stint 26.** 14:07:20, 27 s into lap 2. Stint 26 is
the only stint that ran any laps with airflow.

Between them these are the same size as everything §2 reports. **What makes §2
stand is that the driver's account was given independently and the channels agree
with it corner by corner** — a warm-up drift does not put +5.0 km/h into Lesmo 1
and nothing into Rettifilo, and it does not put 23 % of on-throttle understeer into
one stint only.

---

## 7. Two numbers the morning fixed that had nothing to do with the setup

**7.1 Racing Soft is about 2.7 s a lap quicker than Racing Hard — as a direction
only.** RS 109.088 s (n = 8, sd 0.457) against RH 111.806 s (n = 7, sd 0.326); the
app's own medians over all 1.71 laps agree at 2.68 s. **But `compound_profiles`
reports `pace_known: False` and refuses to state a delta**, correctly: no shared
session, four hours apart, two tyre-temperature regimes, and no RS set older than
four laps. The fix is its own prescription — six laps of each, back to back, one
session, same fuel load.

**7.2 Short-shifting costs about three times what the plan assumes.** Session 78
laps 16–17 ran at a median upshift of **8,397 rpm** against **7,360** on all
thirty-four other laps — a clean 1,037 rpm separation with no overlap.

| | short-shift | full RPM | Δ |
|---|---:|---:|---:|
| Fuel | 5.248 L/lap (n = 16) | 6.944 L/lap (n = 2) | **−24.4 %** |
| Lap time | 111.806 s (n = 7) | 110.195 s (n = 2) | **+1.61 s** |

Corrected for 10.5 L of fuel weight, **1.58 s/lap = 1.52 s per 1000 rpm**. The app
assumes 0.5 s/lap. At 1.64 L saved per 1000 rpm and 1.0 L/s refuel, break-even
goes from a threefold win to **1.64 against 1.52** — eight per cent, and a refuel
rate above ~1.08 L/s inverts it. **n = 2, so do not re-plan on it; do stop quoting
0.5 s.**

---

## 8. The race

Fifty minutes. **Distance is an output of the plan, not an input** — a stop costs
laps — so the "27 laps × 2.7 s" arithmetic I first wrote is the wrong model.
Re-solving for distance including refuel time, both compounds complete **26 laps**
at every pit loss tested, and neither reaches 27:

| | stops | total | spare |
|---|---:|---:|---:|
| RH @ 19 s declared | 1 | 2962.9 s | 37.1 s |
| RS @ 19 s | 4 | 2954.2 s | 45.8 s |
| RH @ 15.7 s (Watkins-measured) | 1 | 2959.6 s | 40.4 s |
| RS @ 15.7 s | 4 | 2941.0 s | 59.0 s |
| RH @ 22 s | 1 | 2965.9 s | 34.1 s |
| RS @ 22 s | 4 | 2966.2 s | 33.8 s |

The compound choice is worth about **9 s of margin, not 16**, and it inverts at a
22 s pit loss — which has never been measured here. Three cold out-laps at
0.5–1.5 s each are enough on their own to flip it. **RH one-stop stands, and RM —
the option that would give two stops — is still the highest-value stint on the
board.**

---

## 9. Defects

1. **The database says all four stints ran the original setup.** Sessions 78–83
   all carry `setup_sheet_id = 3`; `setup_changes` has **zero rows in the entire
   database**; and no sheet anywhere contains `cam_f 3.0`, `toe_r 0.25` or
   `df_r 500`. The only record of what was in the car for three of four stints is
   your spoken account. **Repair before anything is derived from today.**
2. **The reference lap is now a Racing Soft number and the race is on Racing
   Hard.** `build_inputs` returns **1:49.911** with `evidence_compound = 'RH'`.
   `reference_pace_ms` weights by recency with **no compound filter**, and the four
   newest sessions are all soft; the RH median over the same population is
   **111.992**, so the plan is costed **2.1 s/lap optimistic.** Recency weighting
   exists because the newest laps are the most representative — when the newest
   laps are a different tyre they are the least representative. `compound_profiles`
   guards the compound *delta* properly; the top-level reference bypasses the
   guard. It will not change tonight's plan shape, but **the live engineer will
   tell you you are two seconds off the plan on every lap.** Design call: restrict
   the reference to the evidence compound, or to the first stint's compound.
3. **Nothing was recorded and the app never said so.** `_start_video` never ran —
   neither of its two failure lines appears — despite `obs_record_sessions = 1`.
   Separately, `video_path` can never be non-NULL by construction, since
   `_start_video` calls `set_session_video(path=None, ...)`; the field that should
   be checked is `video_started_at`, also NULL for every session ever recorded. In
   VR the recording *is* the wear instrument.
4. **The live sampler answered 16 readings out of 268 attempts across the day**,
   and **only 14 of the 16 were stored** — laps 432 and 436 were logged and not
   persisted. Stint 26's single reading is not a late start: laps 2 and 3 were
   inside the sampling window and were *refused* on the peak-81 VR signature.
5. **`grip_observations` still stops at session 52** — 2,201 rows, nothing since
   18 Aug. (The gauge path is separate and has picked today up.)
6. **The 8× tyre multiplier is not verifiable from the feed at all.** Fuel burn
   being consistent across 78–83 (5.23 RH / 5.31 RS) supports an unchanged *fuel*
   multiplier; nothing in any packet format corroborates the wear multiplier, so a
   lobby change between stints would be invisible and would look exactly like a
   compound effect. Any output quoting the 2.9× ratio should say so.
7. **The fans.** §10.

---

## 10. The fans — diagnosed and fixed (`56a9f83`)

    14:04:40  wind simulator ready on COM5
    14:07:20  Lost the wind simulator on COM5: Write timeout      (2 min 40 s in)
    14:07:21  closing COM5 did not return within 1.0s
    14:07:22  COM5 cannot be reopened because this app is still holding it

COM5 was not released until the app exited at 14:54:36. Seven losses since 22 Aug,
six of them write timeouts; only two ever reopened. **Ruled out**: USB selective
suspend is disabled, AC and DC; the PC had rebooted 62 minutes earlier. The
`93e8c10` cancel-before-close fix was running and did not get the port back.

**So the fix is to stop entering that path.** A fan value is idempotent and resent
every 250 ms against a 1000 ms firmware deadman; a single write the driver would
not take is worth nothing and was costing whole sessions.

- `WindLink.send` catches `SerialTimeoutException` specifically, purges, cancels
  the stuck write, counts it and **sends the next frame**. The link is given up
  only after 20 in a row — five seconds.
- A non-timeout `SerialException` is still fatal, unchanged.
- `_close_handle` calls `reset_output_buffer` (`PurgeComm(PURGE_TXABORT |
  PURGE_TXCLEAR)`) **before** the cancels, which only reach this process's own I/O.
- The health line carries `timeouts N` beside `failures N`.

Five tests added; full suite green. **Why the write times out at all is still
unexplained** — the new counter is what answers it next session.

---

## 11. What the setup brain needs

For `brain/_inbox/17-v1.71-measured-results.md` (§8 "Not captured" is what this
deletes) and the files named:

| Fact | Goes in |
|---|---|
| RS wear 0.142/lap worst corner at 8×, stint 4.9–7.0 laps; **RS/RH ≈ 2.9×** | `03` tyre model, `17` |
| RH wear 0.0493/lap confirmed post-patch, r² 0.98 over 14 laps | `03`, `17` |
| Wear is **left-biased on both axles, both compounds** — `05` §1.5 has the front sign backwards | `05` §1.5 correction |
| `toe_r` +0.17 in ⇒ **+23 % on-throttle understeer**, throttle security, rear L/R temp spread +2.2 °C | `02` toe, `08` playbook |
| `cam_f` +2.0° ⇒ **+5.0 km/h Lesmo 1, +3.9 Parabolica**, rears 1–2 °C hotter and loose | `02` camber, `07` RSR profile |
| `df_r` −40 (20 % of range) ⇒ **+0.2 km/h only**, rear instability; not a top-speed lever here | `05` Monza, `07` RSR |
| **Countersteer % above 1.0 g is a usable looseness index** — 0.0–0.2 % settled, 0.4–0.5 % loose, >7 % is an incident | `10`/`15` instruments |
| Short-shift **1.52 s per 1000 rpm** (provisional, n=2) against 0.5 s assumed | `03` fuel, `13` strategy |
| Fresh sets arrive at **45 °C or exactly 70 °C** and nobody knows which or why | `03`, and a protocol note |
| **Protocol: never run the control first after a gap; interleave, and repeat the baseline last** | `08` playbook |
| GT7 gives one temperature per wheel, so **camber still cannot be validated thermally** — it is validated by corner speed | `02` camber |

Say go and I will write these in.

---

## 12. Next, in order

1. **Fix the reference lap** (§9.2) — the only item that touches a race being
   driven rather than a measurement being taken.
2. **`cam_f 3.0` + `toe_r 0.25` together, twelve laps on RH, control run last.**
   The one stint most likely to produce a faster race car.
3. **Repair the setup record** for stints 27–29.
4. **Six laps RH and six laps RS back to back**, one session, same fuel load —
   turns §7.1 into a number the app will certify.
5. **Ten laps on RM.**
6. Get the recording working, or accept a ~6 % gauge hit rate in VR.
7. Settle the short-shift seconds cost — five and five, interleaved.

---

*Written 24 Aug 2026 · GT7 v1.71 · against `data/pitcrew.db` sessions 78–83 and
`logs/pitcrew.log`, with the driver's account of stints 26–29 and an adversarial
re-derivation of every figure. Companion to
`docs/MONZA-POST-PATCH-TEST-PLAN_2026-08-24.md`.*
