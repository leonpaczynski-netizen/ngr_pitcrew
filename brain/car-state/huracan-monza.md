# What is in the car — Huracán GT3 '15 · Autodromo Nazionale Monza, Full Course

**Round 8 (season finale), NGR GR3 Season 1 · race 21 Sep 2026 10:30 UTC · GT7 v1.71**

**This file is the ONLY place a setup value for this car+circuit may be written down.**
Car-level direction verdicts: `huracan-gt3-AXIS-REGISTER.md`. Experiments:
`brain/ledger/huracan-monza.md`.

| source | what it is worth |
|---|---|
| `SCREEN` | read off the GT7 settings screen. Ground truth for 23 of 24 values. |
| `FEED` | verified from telemetry. Only the gearbox can be. |
| `ISSUED` | what Ludo asked for. **A request, not a reading.** |
| `DRIVER REPORT` | what he says is in the car. |

---

## Rank zero — what is in the car today

`DRIVER REPORT`, 15 Sep: *"setup hasn't changed"* — the Bathurst sheet, `SCREEN`-confirmed 8 Sep
(`huracan-mount-panorama.md` §Rank zero). **Every Monza value below is issued against that car.**
Nothing here is `SCREEN` until the Monza settings screenshot arrives.

## The round, from the league hub (read-only, 15 Sep)

| | | source |
|---|---|---|
| format | 20 laps, standing start, 1 mandatory stop | hub `upcoming()` |
| tyre wear / fuel | 2× / 3×, refuel rate 1 (measured 1.00 L/s at Bathurst — re-measure in this lobby) | hub |
| **power / weight** | **550 bhp / 1,275 kg** | `RoundCarOverride` for Rd8 — the Huracán row |
| BoP | off, tuning open | hub `carRegulations` |
| compounds | RS · RM · RH · IM · HW | hub |
| TCS | lobby 0; **his in-car level is his** (he ran 1→3 at Bathurst) | event / driver |

⚠️ Rd8 **overrides back to 550 / 1,275** (Bathurst inherited 540 / 1,285). The Daytona race car read
**548 BHP / 1,275 kg at ECU 96, restrictor 99, ballast 45 at −29** `SCREEN` (Rd6, same limits) — that
is the regulation answer here, not a judgement call. ECU 97 would be ~554 `DERIVED`, over.

---

## The sheet as issued — 15 Sep 2026 (run A, the Monza baseline)

Percent of the car's own slider range in brackets (`range_records`, verified, v1.71, 24 Aug 2026).

| | in the car now (Bathurst) | **Monza run A, issued** | moved | why |
|---|---|---|---|---|
| tyres | RS / RS | **RS / RS** | — | race compound is a race-plan question |
| body height | 64 / 70 (36 % / 33 %) | **64 / 70** | — | Monza wants the car **up** for kerbs (`05` §1.5, `02` §10.9 #1) and this is already +6 over Daytona. Rear ride height was **null** on the kerb instrument at Daytona (15 Sep) |
| anti-roll bar | 5 / 6 (44 % / 56 %) | **5 / 6** | — | ⭐ `arb_r` is **run B's** experiment — held here so run B has a baseline |
| damping compression | 20 / 20 (0 % / 0 %) | **20 / 20** | — | on the slider floor; and compression damping was **null** on the kerb instrument at Daytona (28/26 → 20/20, 48 v 46 laps) |
| damping expansion | 50 / 44 (67 % / 47 %) | **50 / 44** | — | untested on kerbs with the circuit held; `de_r` up is REFUTED on this car (balance). Held |
| natural frequency | 3.70 / 3.90 (35 % / 45 %) | **3.70 / 3.90** | — | already the softest this car has run. Never tested with the circuit held. Held |
| negative camber | 2.0 / 1.2 | **2.0 / 1.2** | — | camber is a ride-height lever on this car (2.8 mm/deg) |
| toe | 0.00 / +0.12 | **0.00 / +0.12** | — | the `toe_f` braking fix is holding |
| diff initial / accel / braking | 6 / 18 / 35 | **6 / 18 / 35** | — | `05` says medium-low accel for kerb exits; **`lsd_a` down is REFUTED on this car** (less rotation, not more). Held |
| downforce | 410 / 635 (60 % / 68 %) | **350 / 500 (0 % / 0 %)** | ⬇ **both to minimum** | Monza is the lowest-drag circuit (`05` §1.5); on this car the whole wing range is 3–6 % of aero load and moved **no** handling instrument (4 Sep); `02` §10.9 #7 — aero preload eats bump travel. Top speed is what it buys |
| ECU output | 94 | **96** | ⬆ | regulation: 550 bhp limit → 548 `SCREEN` at Daytona |
| power restrictor | 99 | **99** | — | |
| ballast / position | 55 / −29 | **45 / −29** | ⬇ −10 kg | regulation: 1,275 kg limit |
| transmission | 3.022 / 2.450 / 1.972 / 1.598 / 1.285 / 1.030 `FEED`, top speed 300 | **unchanged** | — | see gearbox, below |
| brake balance (MFD) | 0 | **0** | — | `05` §1.5 says one-two forward — **refused** (fronts already lock past the ABS point; standing rule). `bb +1` is rearward on this car. His trim is his |

## The gearbox — held, `[ASSUMED]` until run A

6th tops out ~311 km/h on this box (`huracan-mount-panorama.md` §gearbox, `FEED`). With minimum wing and
548 bhp, Monza's main straight may bring 6th closer to the limiter than Daytona did — `05` asks for 6th
to top out **with a tow** at the Rettifilo board. **Run A checks it:** limiter frames in 6th without a
tow ⇒ 6th is too short; far short with a tow ⇒ too long. 2nd must cover the chicanes without an upshift
between apexes — **unmeasured** on this box at Monza.

**Shift table:** the box is unchanged, so the Bathurst table (`shift_points` id 5: performance
8,600 in 1/2/3, fuel 7,450 in 1/2/3, gears 4–6 silent) is the candidate for Monza — **not yet written
for `autodromo-nazionale-monza-full-course`; awaiting his yes** (it changes the beep).

---

## Why the kerbs are the brief — measured 15 Sep, GT7 1.71

`[DRIVER REPORT]` 15 Sep: *"when the car hits a kerb it loses the "planted feel" to the road and it's
hard for me to keep control, compared to the porsche RSR which is a much more balanced car."*

**The instrument agrees with him** `[DERIVED]` (kerb-strike response, excursion-free strikes ≥80 km/h;
"upset" = a yaw jolt, steering jolt or opposite lock within 1 s):

| big strikes (15–30 mm at the wheel, >140 km/h) | upset share |
|---|---|
| Huracán, Daytona | 0.48 of 91 |
| Huracán, Bathurst | 0.42 of 52 |
| RSR, Sardegna | 0.00 of 106 |

On power the Huracán's rear slips after a strike about five times as often as the RSR's (0.10 against
0.02). The wheel that ends up most extended after a strike is a front on 72–77 % of Huracán strikes.
⚠️ Different car (RR), different circuits, spring-dependent severity — a hint, not a transfer.

**What the setups on file say, with the circuit held (Daytona):** compression damping — null; rear ride
height — null; **`arb_r` 4 → 6 — more rear slip and more catches after a strike, inside the floor** (a
hint only, 15 v 9 laps). TCS 1→3 at Bathurst did not change the upset rate. **Never tested on this car
with the circuit held: springs, front rebound, front ride height, ballast position.**

**Monza's kerbs** (off RSR laps s78–83, 24 Aug, 1.71, map only): the Roggia takes the most hits (~10 a
lap) and the largest upset share; Lesmo 2 is next and has the highest share of strikes followed by
leaving the road; Ascari exit is struck on power at ~170 km/h. The Rettifilo is struck below the
instrument's speed gate. Map: `brain/car-state/monza-kerbs-2026-09-15.png`.

---

## Run plan — Monza practice, before 21 Sep

**0.** Settings-screen screenshot after setting run A. Wheel settings unchanged since 1.71 (rank zero, half 2).
Race fuel for at least one run (burn at 3× is **unmeasured** for this car at Monza).

| run | sheet | laps | what it answers |
|---|---|---|---|
| **A** | as above | 8 clean | baseline: kerb upset share, rear slip after strikes on power, top speed at the Rettifilo board, 6th-gear limiter, 2nd through the chicanes, burn per lap |
| **B** | A with **rear anti-roll bar 6 → 4** | 8 clean | does the car stay planted after a kerb — **his report first** |
| **A again** | back to 6 | 8 clean | the return leg — separates the change from him learning Monza |

~30 laps, about 55 minutes. **What 8 laps a block can see:** a change in upset share of about 0.10–0.14,
or rear slip after strikes of about 0.10–0.13. The Daytona hint was +0.09, so the telemetry will most
likely say *"can't tell"* — **his report decides B**, and the time down the next straight (Roggia exit →
Lesmo 1, Ascari exit → Parabolica) says what it costs. ~20 clean laps a block would be needed to see a
change the size of the hint.

**The price of B, stated before he drives:** `arb_r` 4 → 6 was the best change of 8 Sep — the drive out
of Daytona's infield (sector 2) — so B may give some exit drive back.
