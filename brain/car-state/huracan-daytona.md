# What is in the car — Huracán GT3 '15 · Daytona Road Course

**This file is the ONLY place a setup value for this car+circuit may be written down.**
Everything else — memory files, `RECONCILIATION.md`, session notes — **links here and
restates nothing.** A number written in two places becomes two numbers; that has now
happened twice on this car (`dc_r` on 3 Sep, and the worst-wearing corner before it).

**Writing rule.** A row is only written from one of three sources, and the source is
recorded per run:

| source | what it is worth |
|---|---|
| `SCREEN` | read off the GT7 settings screen. **Ground truth for 23 of 24 values, costs zero laps.** The best rank-zero instrument this project has. |
| `FEED` | verified from telemetry. **Only the gearbox can be** — `analysis/gearing`, K = km/h per 1000 rpm. |
| `ISSUED` | what Ludo asked for. **A request, not a reading.** Never promote to `SCREEN` without a screenshot. |

**Anything with no source is `?` and must be asked, never inferred.**

---

| | Run 1a<br>s113/114, 1 Sep | Run 2<br>s115, 1 Sep | Run 3<br>s116, 3 Sep | **Run 4**<br>s117, 3 Sep |
|---|---|---|---|---|
| **source** | SCREEN (per 1 Sep note) | ISSUED | **? — never read** | **SCREEN** ✅ |
| brake balance `bb` | ? | ? | ? | **0** — moved from +2 by the driver, `driver`. ⚠️ **`bb +1` is rearward on this car, so this is two clicks FORWARD.** GT7 broadcasts no brake balance: recorded, unverifiable |
| ride height `rh` | 62 / 70 | 58 / 70 | ? | **58 / 70** |
| natural freq `nf` | 3.90 / 4.10 | 3.90 / 4.10 | ? | **3.90 / 4.10** |
| anti-roll `arb` | 5 / 4 | 5 / 4 | ? | **5 / 4** |
| damping compression `dc` | 28 / 30 | 28 / 30 | **28 / 30** `FEED` (note 1) | **28 / 26** ✅ |
| damping expansion `de` | 46 / 44 | 46 / 44 | ? | **46 / 44** |
| camber `cam` | 2.0 / 1.2 | 2.4 / 1.2 | ? | **2.0** / 1.2 `driver` (was 2.4 on the 3 Sep screen) — moved AFTER the screenshot. ⭐ **`[DRIVER REPORT]` 3 Sep: *"braking was better and the turn in improved"* — BACKWARDS from textbook.** ⚠️ **Still unknown whether 2.0 was in for the race stint (s118); camber has NO telemetry ground truth, so unlike `dc_r` it cannot be discriminated.** |
| toe | 0.00 / 0.12 | **−0.08** / 0.12 | ? | **0.00** / 0.12 ✅ |
| diff `lsd` i/a/b | 6 / 14 / 28 | 6 / 14 / 28 | ? | **6 / 14 / 28** |
| downforce `df` | 380 / 600 | 380 / 600 | ? | **380 / 600** |
| 6th gear | **0.980** (instrument) | **1.030** | **1.030** `FEED` | **1.030** `FEED` (K6 36.004). ⛔ **The 1.010 proposal is WITHDRAWN, 4 Sep** — the rev limiter fires in gears 1–5 and never once in 6th across 79,090 frames; 6th is already long enough (`RECONCILIATION.md` §Z1) |
| top speed slider | 300 | 300 | ? | **300** |
| ECU / restrictor | 96 / 99 | 96 / 99 | ? | **96 / 99** |
| ballast / position | 45 / −29 | 45 / −29 | ? | **45 / −29** |
| compound | RS | RS `FEED` | RS `FEED` | **RS / RS** |
| — race stint s118, 3 Sep | | | | as run 4. **Wear RECOVERED from the recording**: RR 0.0570/lap, FL 0.0275 |
| — s119, 3 Sep 22:27 | | | | as run 4 **but `cam_f` 2.0** `driver` — that run ONLY. Resolves nothing: front temps and the rear−front gap both unchanged |
| — | | | | 548 BHP · 1,275 kg · PP 751.67 |

**Note 1 — CLOSED, 3 Sep.** Driver confirmed `dc_r` is 26, and the telemetry says **when**:
rear squat velocity on throttle-up at zone 4 went **+14.06 (R1a, 30) · +10.28 (R2, 30) ·
+8.53 (R3) · +16.97 mm/s (R4)**. Softer compression squats faster, and **R4 is 99% faster
than R3** ⇒ **R3 ran 30 and the change went into run 4.**

---

## Why this file exists — the three defects it works around

1. **`sessions.setup_sheet_id` is NULL on all four Daytona sessions**, so the database
   knows nothing about what was in the car for any of them. `data_health.py` reports
   *"every session ran the sheet it is tagged with"* — **a vacuous pass, not a clean one**:
   there is no sheet to compare against, and the check says the same words for
   "verified" and "nothing to verify."
2. **There is no Daytona `setup_sheets` row at all** for this car.
   `check_setup_sheets.py` (since removed with the setup record, §1a) listed Spa, Fuji and Watkins Glen and simply does not mention Daytona.
3. **`setup_changes` logs only suspension and diff keys**, so restrictor, ECU, ballast and
   gearing **cannot appear in it at any time** — which is how the build drifted from
   restrictor 99 / ECU 94 to 93 / 100 with no row anywhere recording it.

⇒ **App work — done 3 Sep 2026, DB schema v14:**

- **`setup_changes` now holds performance and gearing keys.** `SetupChange.validate`
  checked the 23 export-contract sliders, and `note_sheet_change` only ever iterated
  `sheet.values` — so a sheet's `performance` and `gears` were invisible to the ledger
  **by construction**. `vocabulary.CHANGE_KEY_NAMES` is now a deliberate superset
  (23 sliders + `powerRestrictor` / `ecuOutput` / `ballastKg` / `ballastPosition` +
  `gear1`..`gear9`), and `export/build.py` filters back to contract keys on the way out,
  so the payload cannot widen. **The restrictor drift now has a home.**
- **`setup_changes` has `reason` and `source`.** A row saying `dc_r 30 → 26` records
  that something moved but not what it was *for*, and **the same outcome confirms an
  exit-traction intent and refutes a braking one.** `source` is `screen` / `feed` /
  `issued` / `sheet-diff` / `driver` — because **a request is not a reading**, which is
  the distinction that failed on this very value. All 202 existing rows keep NULL in
  both: back-filling them would be inventing intent nobody stated.
- **`tools/log_setup_change.py`** *(since removed: `setup_changes` has no writer, and `brain/ledger/` replaced it)* filed a change with its reason, or attaches one to a
  row already written. **A hand-filed change without `--why` is refused** — the
  automatic path may have a null reason because a sheet diff genuinely has none; a
  human at a keyboard does not get that excuse.
- **`data_health.py` no longer passes vacuously.** Its gearbox query filtered on
  `sh.circuit_key = ?` after a LEFT JOIN, which **drops every session whose
  `setup_sheet_id` is NULL** — so this car at this circuit examined nothing, found no
  mismatch, and reported *"every session ran the sheet it is tagged with."* It now
  counts what it compared and names what it could not, scoping untagged sessions by
  their **event's** circuit (they have no sheet, so they have no circuit of their own
  and were being reported under every circuit the car had ever visited).

⚠️ **Defect 2 above is NOT a code bug and was not "fixed".** `controller` deliberately
records **no** sheet rather than the wrong one, and says so on the Practice status line.
`setup_sheet_id` is NULL here because **there is no Daytona sheet in `setup_sheets` at
all** — that is data entry, and this file is standing in for it until there is one.

---

## 4 Sep 2026 — five A/B runs, sessions 120–124, each with a settings-screen shot

**Source: `SCREEN` for every value below** — screenshots `20260904_1.png` … `_5.png` in
`C:\Users\leons\Downloads` (11:20, 11:39, 11:52, 12:03, 12:16; the file number is the run order).
`bb` is not on that page; **asked and answered 4 Sep — `0` all day, `driver`**, unchanged since run 4 on 3 Sep. Gearbox not on that page: `FEED` says 6th
still **1.030** (K6 unchanged, see run 4). ⚠️ **None of the five sessions has a `setup_sheets` row,
a `sessions.setup_sheet_id`, or a `setup_changes` row** — the defect this file exists to work
around, reproduced five times in one morning while the audit was being written.

Common to all five: rh 58/70 · arb 5/4 · dc 28/26 · de 46/44 · nf 3.90/4.10 · toe 0.00/0.12 ·
lsd 6/14/28 · top 300 · ECU 96 · restrictor 99 · ballast 45 @ −29 · RS/RS · 548 BHP · 1,275 kg.

| run | session | start | **changed** | GT7 Measure: PP · stability lo/hi | laps · countable · clean (DB) |
|---|---|---|---|---|---|
| 5 | 120 | 11:25 | **df 420/600** | 751.67 · −0.46 / **−0.45** Under | 6 · 6 · 1 |
| 6 | 121 | 11:39 | **df 420/650** | 757.88 · −0.46 / **−0.36 Neutral** | 6 · 6 · 0 |
| 7 | 122 | 11:52 | **df 410/635, cam 2.0/1.2** (baseline) | 752.56 · −0.46 / −0.42 | 5 · 5 · 0 |
| 8 | 123 | 12:04 | **cam 1.0/1.0** (df 410/635) | 752.54 · −0.46 / −0.43 | 6 · 6 · 1 |
| 9 | 124 | 12:17 | **cam 4.0/4.0** (df 410/635) | 752.54 · −0.46 / −0.43 | 6 · 6 · 0 |

**What the runs say — final, re-derived 4 Sep from `laps` + `lap_frames` (read-only). Countable = `excluded 0`,
lap > 1, off-track < 1 s, no spin: 24 laps, 20 incident-free. Straight-line and banking figures additionally exclude
the six laps carrying the banking-brake event (F6) and the lap after each.**

⚠️ First version of this note said "two clean laps in five sessions" — wrong, the driver caught it: the filter excluded
any lap with 0.05 s of kerb time. ⚠️ Lap 1 of every session is the out-lap (pit limiter 79.5 km/h visible at 150–350 m;
partial 91.6 s or 7–9 s on the grass) and `is_out_lap` was 0 on all of them — **fixed and backfilled 4 Sep** (`tools/flag_out_laps.py`).

| run | change | laps (clean-banking) | best | median | S2 sector | T4 exit spin | RR temp | bank susp F / R | body min (bank) |
|---|---|---|---|---|---|---|---|---|---|
| 5 (s120) | df 420/600 | 4 (4) | 104.618 | 105.40 | 39.97 | 14.3 % | 73.9 | 277.8 / 288.0 | 26.5 |
| 6 (s121) | df 420/650 | 4 (1) | 104.086 | 105.72 | 39.69 | 15.0 % | 74.8 | 277.3 / 288.7 | 28.9 |
| 7 (s122) | base 410/635, cam 2.0/1.2 | 3 (2) | **103.853 PB** | 104.48 | 39.42 | 22.3 % | 74.6 | 277.2 / 288.6 | 27.2 |
| 8 (s123) | cam 1.0/1.0 | 5 (3) | **103.486 PB** | 104.45 | 39.58 | 21.1 % | 74.5 | **274.6** / 288.2 | 30.0 |
| 9 (s124) | cam 4.0/4.0 | 4 (1) | 103.594 | 105.01 | **39.34** | **31.3 %** | **76.9** | **283.1 / 296.6** | **15.5** |
| ref s119 (3 Sep) | df 380/600 | 7 | 104.169 | 106.41 | 39.88 | 17.3 % | 73.5 | 276.7 / 288.2 | 26.9 |

**F1 — Camber is a ride-height lever in GT7: ~2.8 mm per degree, measured.** Suspension height on the banking at full
throttle: front **274.6 → 277.2 → 283.1 mm** at camber 1.0 / 2.0 / 4.0; rear **288.5 → 296.6** at 1.2 / 4.0. Body height
on the banking at 4.0/4.0: median **43.3 → 36.2 mm**, minimum **27 → 15.5 mm**. s119 (same camber as the baseline, other
day) reads 276.7 / 288.2 — the channel is the setup, not the day. ⇒ **every camber change is also a platform change**, the
55/62 ride-height stage must be costed with the camber in force, and the 3 Sep *"2.4 → 2.0 braked better and turned in
better — backwards from textbook"* now has a candidate mechanism: the front rose ~1.1 mm. `[MEASURED]`, one instrument.

**F2 — Rear camber 4.0 costs exit traction at every traction zone.** Rear slip > 1.05 on exit: T2 **23.6 %** (baseline
13.6), T3 **30.3** (22.1), T4 **31.3** (22.3), T5 **25.3** (15.4); rears +1.3 / +2.3 °C. Direction consistent in four
zones on one run of four laps; the 3 Sep unchanged-rear band for the whole-lap figure was 18.7–34.4 %, so this is
`[DERIVED]`, suggestive, not proven. Lap time does not show it — S2 was R5's fastest sector because T3 / T4 v-min were the
highest of the morning (88.3 / 91.2): more speed carried, less exit drive.

**F3 — Front camber 1.0 ↔ 4.0: nothing measurable on the front.** Front surface temperature 65.1–65.5 °C across the
sweep (floor 0.9–1.4); front L/R slip split and lock inside their floors. GT7 gives one surface temperature per wheel,
so camber's effect on the contact patch is invisible here — the front camber the data can justify is whatever the driver
reports, and he set the PB on 1.0/1.0.

**F4 — The downforce slider moves very little load.** Rear 600 → 650: +0.65 mm rear compression, −0.5 front at 270 km/h;
380/600 → 410/635: +0.5 / +0.3 mm. J3 measured the whole aero load at ~10 mm from 125 → 250 km/h, so **±25–50 clicks is
3–6 % of the aero load** — invisible on lap time, wear (RR 0.0556/lap in every run), terminal (back straight 275.0–275.5,
front stretch 283.7–284.6, floor 0.56–2.77) and rear temperature (+1 °C). *"More aero to look after the rears"* (3 Sep)
cannot work at this magnitude; entry X3 stands and is now measured rather than argued. GT7's Measure readout does see
it — high-speed stability −0.45 / −0.42 / −0.36 tracks total downforce 1,020 / 1,045 / 1,070.

**F5 — Learning was the largest effect in the morning.** Run bests 104.62 → 104.09 → 103.85 → 103.49 → 103.59; S2
sector 39.97 → 39.69 → 39.42 → 39.58 → 39.34; the fastest lap came in the last third of every run. ~0.3 s per run on a
car that changed by 3–6 % of aero load or by camber — the same size as any setup effect. **Lap time cannot rank these
five sheets**; camber 4.0/4.0 is the one run that did not improve on its predecessor.

**F6 — The 5,200 m brake is a track-limits time penalty, served on the banking. ANSWERED by the driver, 4 Sep.**
On six of 24 laps (s121 L3, L6; s122 L5; s123 L4; s124 L2, L6; also s119 L10) the brake goes to 100 % at exactly
5,200 m, 267 → 110–190 km/h, then full throttle without pitting: GT7 making him serve a penalty for exceeding track
limits earlier in the lap. Not setup. It costs that lap ~1–2 s and the **next** lap's front stretch (254 instead of
284 km/h). ⇒ **Penalty laps have a signature the app can detect** — full brake above 250 km/h at near-zero lateral g,
no pit entry — and should be flagged like an incident so they and the following lap's straight drop out of
comparisons automatically. Until then, banking and straight-line figures here exclude them by hand. **Also:** six
penalties in 24 laps says the kerb time in `off_track_s` (0.2–0.5 s on most laps) is not cosmetic — it is what earned
them. `[DRIVER REPORT]` for the cause, `[MEASURED]` for the cost.

**F7 — Wear.** Identical at the gauge's resolution in all five runs: RR 0.0556/lap, RL 0.037–0.042, FR 0.037–0.042,
FL 0.035–0.037. Replicates the race stint's 0.0570. Neither wing nor camber moved it over 4–5 laps.

**`bb` = 0 for all five** (`driver`, asked 4 Sep) — and therefore identical to the 3 Sep race stint s118 and to
s119, so front-lock and wear comparisons across 3–4 Sep are clean on that axis. ⚠️ **0 is two clicks FORWARD of
the +2 he ran before 3 Sep**, and the RR 0.0570/lap wear map was measured there. **The toe fix is holding at
it:** front L/R slip split under braking (>60 %, >80 km/h) is −0.0035 to −0.0073 in every run and −0.0035 in the
race stint, against a measured floor of 0.003–0.006 — **inside the floor, i.e. no resolvable front asymmetry**,
an order of magnitude below the 0.0428 that the toe change removed on 3 Sep. cam 4.0/4.0 flips the sign
(+0.0029) on three laps; that too is inside the floor and is not a claim.

**Not established:** nothing on this sheet is now unsourced.

## 4 Sep 2026 evening — session 125, the 13-lap race stint

**Source: `SCREEN`** (settings shot, 4 Sep evening) — **identical to the 4 Sep baseline**: df 410/635 ·
cam 2.0/1.2 · rh 58/70 · arb 5/4 · dc 28/26 · de 46/44 · nf 3.90/4.10 · toe 0.00/0.12 · lsd 6/14/28 ·
top 300 · ECU 96 · restrictor 99 · ballast 45 @ −29 · RS/RS · PP 752.54. **`bb` 0** (`driver`, 4 Sep).
6th still 1.030 `FEED`.

13 laps, 8 clean. **Wear captured (`hud-video`) — the OBS projector fix held.**
Verdicts in `RECONCILIATION.md` §AA.

| measured | value | note |
|---|---|---|
| fuel | **7.680 L/lap** (n=11) | ⇒ tank stint **13.02 laps** |
| wear RR / RL / FR / FL | **0.0540 / 0.0407 / 0.0407 / 0.0309** per lap (n=8) | replicates 3 Sep; RR worst at **1.75× FL**; ⇒ tyre stint 15.7 laps ⇒ **fuel still binds** |
| clean lap median / best / sd | 105.858 / **105.084** / 0.818 s | first 3 vs last 3: **−0.136 s** |
| first corner v-min | **62.1–98.4 km/h** | **r = −0.947 with the brake RELEASE point**; brake ON point uncorrelated (r = −0.051) |
| first corner rear slip min | **0.894** on lap 8 | first sub-0.90 rear reading on file here; 3 Sep archive was 0.00 % below 0.90 in 20 laps |
| Bus Stop v-min | 145.8–158.3, sd 4.91 | **inside the same-setup floor (1.57–5.08) — no claim** |

⛔ **Lap 8's `wear_*` row is 0.0 on all four corners** — a failed gauge frame stored as zero, not NULL. Rule 3.

**`lsd_b` 28 → 40 — RUN, session 126, 4 Sep 21:34, source `driver`** (no settings shot). Verdicts in §AB.
Sub-0.90 rear frames at the first corner **12 → 0**; rotation-under-brakes **unchanged at the first corner
(0.0121, floor 0.0033)** but **down at z3 (0.0148 → 0.0125, floor 0.0014) and z4 (0.0116 → 0.0103, floor
0.0011)** — the driver's *"more rotation on other corners under brakes"* is measured. Fuel 7.693 L/lap (n=8).

**⇒ NEXT CHANGE, ISSUED (not yet run): `dc` 28/26 → 20/20** — compression damping to the bottom of its
verified [20, 40] range. One axis, both ends. Bought by §AB3: **the car leaves the ground over the Bus Stop
kerb on every lap of all five sessions** (body 40 → 73–78 mm, lateral g to 0.02–0.11 g, 0.08–0.19 s with no
grip at 160 km/h; kerb contact on 100 % of laps; 3 of 19 evening laps ended on the grass there).
⚠️ **`dc_r` 18 is OUT OF RANGE — the floor is 20.**

**⇒ THEN: `lsd_b` 40 → 35**, the driver's own ask, already justified by §AB2 and only sequenced behind the
damper by the one-change rule.

**(superseded) `lsd_b` 28 → 40 was issued as:** (range 0–100, `verified` v1.71, measured 24 Aug).
One change. Bought by the driver's report corroborated in phase (§AA2), **not** by telemetry (§AA4 — the
rear-lock instrument's floor disagrees with itself 5×). ⚠️ **It will cost rotation on release, which he
does by design** — that is the trade, and it is the falsifier.

## 7 Sep 2026 — Round 6, sessions 139–143. Source: `SCREEN` (settings shot, 8 Sep)

**Identical to the s127 sheet, confirmed value by value off the GT7 settings screen.**
RS/RS · rh **58 / 70** · arb 5 / 4 · dc **20 / 20** · de 46 / 44 · nf 3.90 / 4.10 ·
cam 2.0 / 1.2 · toe 0.00 / 0.12 · lsd **6 / 14 / 35** · df 410 / 635 · ECU 96 ·
restrictor 99 · ballast 45 @ −29 · top 300 · **PP 752.54 · 548 BHP · 1,275 kg · 43:57**.
GT7 Measure: stability −0.46 (Under) low / −0.43 (Under) high; rotational g 1.49 / 1.57 / 1.86.
**`bb` = 0** (`driver`, 8 Sep — "exact settings as they were run in race").
Gearbox **`FEED`**: 3.022 / 2.450 / 1.972 / 1.598 / 1.285 / **1.030** on all 38 laps of the weekend.

⇒ **Nothing has moved since session 127 (4 Sep).** Every 1–7 Sep figure is on one sheet.

### Rake, in percent of range for the first time — range record 24 Aug, `verified`, v1.71

| | value | range | **% of range** |
|---|---|---|---|
| `rh_f` | 58 | [55, 80] | **12 %** (3 mm off the floor) |
| `rh_r` | 70 | [60, 90] | **33 %** (10 mm off the floor) |

**Rake = 12 mm.** Other drivers in the league run 5 mm (driver report, 8 Sep) — which on this
car is both sliders at or near minimum, since the minimums themselves differ by 5 mm.
**The rear is nearly 3× further off its own floor than the front is off its.** `rh_f` has never
been moved from 58 since 1 Sep and **no ride-height A/B exists anywhere in this car's archive.**

**Measured 7 Sep, so the change can be priced:**
- Dynamic rake (rear − front suspension height, full throttle before the banking) median
  **10.51 mm**, range 8.98–12.81 over 31 laps. **Fuel moves it +0.0060 mm/L ⇒ +0.55 mm across a
  full-to-empty 92 L swing.** The "a full tank squats the rear and kills your rake" mechanism
  from `04-race-vs-qualifying.md` §2.3 is **NOT PRESENT on this car** — measured, not argued.
- **Bottoming is not the constraint.** Body clearance at the banking's worst point: median
  41.5 mm, minimum 38.6 over 31 laps. Rear wheel compresses to ~285 mm there against ~272 at
  its most compressed anywhere. Taking the rear down 6 mm does not reach anything.

**⇒ ISSUED, one change, session 144: `rh_r` 70 → 64.** Rake 12 → 6 mm; rear 33 % → 13 % of
range, matching the front's 12 %. Front untouched at 58 so the 4 Sep front A/Bs stay comparable.
Basis, prediction and falsifier in the 7 Sep debrief memory.

⚠️ **`de` 46/44 is the untried axis and it is the one aimed at the Bus Stop.** The launch is an
**extension** event — the RR wheel rises to 300 mm median, 314.4 mm max, at 3,815–3,852 m,
**on tarmac, before the car reaches the grass** — and compression damping cannot govern
extension, which is why `dc` 20/20 was falsified there on 4 Sep. `de_r` 44 is 47 % of [30, 60].
Queued behind the rake change by the one-change rule.

## 8 Sep 2026 — session 144, `rh_r` 70 → 64 RUN. Source `driver`, **corroborated `FEED`**

⭐ **Ride height is the SECOND setup value this feed can verify, and it verifies.** The rear
suspension-height channel moved **+6.1 mm** (banking, full throttle: rear 285.0 → 291.1 mm
median) while **the front did not move** (273.4 → 272.6). The rake proxy went 10.51 → **16.6**.
The channel's sign is inverted relative to the ride-height slider — a *lower* slider reads
*higher* here — so quote the magnitude and the front/rear asymmetry, never the absolute.
⇒ **`rh_f` and `rh_r` can be checked from the packet from now on, like the gearbox.**

**3 laps (1 out-lap). Lap 3 = 103.624 s on 84.7 L.** Fuel-corrected at 0.003 s/L/lap `[DERIVED]`
that is **103.370 — the second-fastest lap in the whole six-session Daytona archive**, 0.026 s
off s140L4 and ahead of every race lap. Third lap out, full tank.

| prediction (7 Sep) | result | verdict |
|---|---|---|
| T1 opposite-lock laps 8/31 → ≤2/12 | **0 frames on both laps**, at v@250 285.6/287.7 (race median 281.6, so not slower) | **holding, NOT YET EVIDENCE** — 0/2 has p≈0.55 under the old 26 % rate. Needs ~10 laps |
| T5-exit rear-slip peak < 1.15 | 1.082 / 1.104 (median was 1.090, max 1.264) | holding, n=2 |
| RR wear < 0.054/lap | not measurable in 3 laps | open |
| **stated cost: less rotation** | **`[DRIVER REPORT]` — and he located it more precisely than I did: it landed on ACCELERATION, not on release under brakes** | ⭐ I predicted the cost on the `lsd_b` axis; it arrived on the `lsd_a` one |

⚠️ **Banking body clearance is now at its lowest observed: 38.6 / 38.8 mm** (previous minimum
38.6 over 31 laps, median 41.5). Not bottoming, but there is no more rear to give.

⛔ **Lap 2 spun at 1,881 m — the T3 exit, for the FOURTH time** (s139 L6, s141 L3, s144 L2, plus
3 of 27 clean laps on the grass there). `spin_s` 1.17. Identical signature every time: full
throttle out of the hairpin on tarmac with the car stable (rear slip 1.00–1.01, yaw −0.32),
**runs out of road on the left at ~1,840 m, lifts (throttle 78 → 13 %), kerb at 1,843, grass at
1,858, gone.** **The rake change neither caused nor cured it** — it is not a balance event.

**⇒ NEXT CHANGE, ISSUED, session 145: `lsd_a` 14 → 8.** His ask, and the axis
`01-driver-profile-leon.md` names for on-power rotation. **The 1 Sep refutation only ever
tested RAISING it** ([[feedback_refutation_carries_a_direction]]) and its own measurement —
rear slip-ratio split at the exits, **median 0.0000, p95 0.02–0.03 over 31 laps** — is the
evidence FOR lowering: the two rear tyres are held to the same slip ratio, which is what a
locking diff does and the opposite of what rotation on power needs. `lsd_a` has measured
authority in 2nd and 3rd, which is both exits that matter.
**PREDICTS** the exit split p95 opens above 0.03 at T3 and T5, and he reports rotation back.
**FALSIFIED BY** an unchanged split AND no driver report of change.
**HYPOTHESIS, stated so it can be wrong:** a car that will not rotate on power runs wide on
exit, and the T3-exit kerb contact (16/27 laps) is downstream of that. If the kerb contact
rate falls, that is the mechanism; if it does not, the kerb problem is separate and `de_r` is
next.

⚠️ `de` 46/44 still queued — the Bus Stop launch is an extension event and nothing has been
aimed at it yet.

**⭐ 8 Sep, driver correction on s144 L2 — the hypothesis is corroborated before the test ran.**
*"My off on lap 2 was getting on the throttle early and not getting the rotation and running
wide."* `[DRIVER REPORT]` The frames say exactly that: full throttle from 1,763 m, car stable,
arrives at the road edge at 1,840 m and lifts. ⇒ **the T3-exit kerb contact (16/27 laps) is
downstream of on-power rotation, not a separate problem**, and `lsd_a` 14 → 8 is now aimed at
both. The falsifier is unchanged: the exit split must open above p95 0.03, or it is refuted.

## 8 Sep — session 145, `lsd_a` 14 → 8. **REFUTED. I had the direction backwards.**

`[DRIVER REPORT]` *"it felt like it was worse at rotating."* **The telemetry agrees, on a
calibrated index.**

**ON-POWER ROTATION INDEX** — median |yaw rate| per degree of lock, throttle >60 %, >60 km/h,
lock >10°, all four on tarmac. **Noise floor measured by splitting the 15 clean race laps
odd/even, same car, same day: T3 |0.00058| (lap sd 0.00128), T5 |0.00104| (lap sd 0.00082).**

| config | T3 exit | T5 exit | front scrub (T5) | rear spin (T5) |
|---|---:|---:|---:|---:|
| A · rh 70 / lsd_a 14 — race, n=15 | 0.00672 | **0.00788** | +0.0079 | +0.0264 |
| B · rh 64 / lsd_a 14 — n=2 | 0.00559 | 0.00724 | +0.0082 | +0.0340 |
| C · rh 64 / **lsd_a 8** — n=3 | 0.00555 | **0.00554** | **+0.0099** | +0.0304 |

- **A→B (the rake change) cost 0.00064 at T5 — INSIDE the 0.00104 floor. Not resolvable.**
  At T3 it cost 0.00113, about at the floor. So the rake change is not what he felt most.
- ⭐ **B→C (`lsd_a` down) cost 0.00170 at T5 — 1.6× the odd/even split and 2.1× the lap-to-lap
  sd. RESOLVABLE, and it is a LOSS.** Front scrub rose with it (+0.0082 → +0.0099): the nose
  washed out further. **On this car LESS acceleration lock gives LESS rotation on power** —
  the opposite of the textbook and the opposite of what I predicted.
- Lap time agrees: fuel-corrected best 103.370 (B) → **105.674 (C, +2.30 s)**.
- The split falsifier also failed on its own terms: T3 p95 0.0159 → 0.0261 (never cleared the
  0.03 bar), **T5 p95 0.0337 → 0.0248, i.e. it went the wrong way.**

⛔⛔ **AND THE SPLIT WAS THE WRONG INSTRUMENT ALL ALONG.** The 1 Sep refutation
(*"rear wheel-speed split median 0.0000, the wheels are already tied, there is no split for
more lock to close ⇒ the differential is REFUTED as the exit lever"*) rests on a channel that
**stayed at 0.0000 across a 6-click diff change while the rotation index moved twice its noise
floor.** A measure that cannot see the change cannot refute the lever. ⇒ **the differential IS
an exit lever here, `reference_daytona_corner_priority`'s ⛔ block is retired, and the KB's
original `lsd_a` 22-28 (v1.70 scale) ask was pointing the right way** *(a direction only -
the band is not on this car's v1.71 0–100 slider)*.

⛔ **s145 L3 also went off at the T3 exit — the FIFTH time at that spot** (8.13 s off-track,
`spin_s` 0.23, S2 50.0 s and S3 61.2 s, so two separate incidents on one lap).

**⇒ NEXT CHANGE, ISSUED, session 146: `lsd_a` 8 → 20.** A symmetric step the other way
(+6 from the 14 baseline, matching the −6 that measurably cost 0.00170) on the instrument that
just proved it can resolve it, and toward the KB's 22-28.
**PREDICTS** the T5 rotation index rises above 0.0089 — i.e. past the race baseline's 0.00788
by more than the floor — and front scrub falls back below +0.0082.
**FALSIFIED BY** an index at or below 0.00788, in which case 14 is the optimum and it stops there.
⚠️ `lsd_a` is inert in tall gears, so nothing on the banking is at risk.

## 8 Sep — session 146, `lsd_a` 20, 11 laps. Two of my falsifiers FAILED. Values below.

`[DRIVER REPORT]` *"definitely rotates more on acceleration, I needed to adjust my throttle
application to be smoother and a little more gradual to avoid spinning, but there are a few
spins in that session."*

### ⛔ FALSIFIER 1 FAILED — `lsd_a` 20 buys nothing measurable over 14

Stated: *"the T5 rotation index rises above 0.0089. FALSIFIED BY an index at or below
0.00788."* **Result: 0.00748 (n=10). Falsified.**

| config | T3 exit | T5 exit | n |
|---|---:|---:|---:|
| rh 70 · `lsd_a` 14 (race) | 0.00672 | 0.00788 | 15 |
| rh 64 · `lsd_a` **8** | 0.00555 | 0.00554 | 3 |
| rh 64 · `lsd_a` 14 | 0.00559 | 0.00724 | 2 |
| rh 64 · `lsd_a` **20** | **0.00672** | **0.00748** | 10 |

**The AXIS is confirmed — 8 → 20 is +0.00194 at T5 and +0.00117 at T3, both ~2× their floors
(0.00104 / 0.00058), and monotonic. But 14 → 20 is +0.00024, INSIDE the floor.** All of the
gain lives between 8 and 14. ⇒ **The instrument cannot separate 14 from 20. The driver can and
prefers 20, so 20 stands as HIS call, recorded as such** (`CLAUDE.md` rule 1).
**Cost on the record: 2 spins at the T5 exit in 10 laps** (2,221 m and 2,226 m, on tarmac,
laps 6 and 7) against **0 in 24 laps** at every other config. Both came while he was learning
the throttle; laps 8-11 had none.

### ⛔ FALSIFIER 2 FAILED — the rake change did NOT fix the T1 entry

Stated 8 Sep: *"T1 opposite-lock laps fall from 8/31 to ≤2/12."*
**Result at rh 58/64: 5 laps of 15** (s146 L5 2 frames, L6 3, **L7 37**, **L10 14**), against
**8 of 31** at rh 58/70. 33 % vs 26 % — **no improvement, and 15 laps is enough to rule out the
large drop I predicted.** Worse, **rear brake lock is still live: L7 carries 19 sub-0.90 rear
frames and L10 carries 34** — the same signature as race lap 8 (19 frames), which spun him out
of P2. ⇒ **The rake change stands on pace and on his report; its entry-stability rationale is
refuted.** Said plainly rather than quietly dropped.

### Pace — the two fastest laps ever recorded on this car here

L5 **103.329 s** at 69.1 L and L9 **103.245 s** at 37.1 L ⇒ fuel-corrected (0.003 s/L/lap,
`[DERIVED]`) **103.122 and 103.134**, against a previous archive best of 103.303 (s140 L4) and
103.370 at rh 64 / `lsd_a` 14. **But the clean-lap median is 104.42 against the race's 104.173**
— faster at the top, not in the middle. That is the trade he described.

### ⛔ The T3 exit bit for the SIXTH time and nothing I have changed touches it

s146 L2 at **1,869 m**: identical trace to the other five. Full throttle out of the hairpin,
car stable (rear slip 1.03-1.04, yaw −0.4), **backs off at 1,822 m (100 → 80 → 29 %), kerb at
1,827, grass at 1,841, gone.** Six events at 1,830-1,970 m across five sessions, plus 3 of 27
clean race laps on the grass there. **It is a placement problem at a kerb the car cannot
survive — the same class as the Bus Stop launch, and the same lever.**

**⇒ NEXT CHANGE, ISSUED, session 147: `lsd_b` 35 → 40.** Aimed at the T1 rear brake lock, which
is the failure that actually cost the race. **Measured lever:** 4 Sep, `lsd_b` 28 → 40 took
sub-0.90 rear frames at the first corner **12 → 0** ([[project_daytona_lsdb40_2026_09_04]]).
`lsd_a` stays at 20 — his call, and the change is one axis.
**PREDICTS** laps carrying sub-0.90 rear frames at T1 fall from 2-in-15 to 0, and T1
opposite-lock laps fall below 2-in-12.
**FALSIFIED BY** either rate unchanged over 12 laps.
⚠️ **THE COST, and it is the one he bought 35 for:** `lsd_b` 40 measurably reduced rotation on
release under brakes at z3 and z4 on 4 Sep. He now has extra rotation on power from `lsd_a` 20,
so the trade is not the same one he refused in September — but if the car will not rotate into
the corner, this is the change that did it.

**⇒ THEN: `de_r` 44 → higher.** The T3 exit and the Bus Stop are both **extension** events —
a kerb throwing the wheel up — which is why `dc` 20/20 was falsified at the Bus Stop and why
nothing tried so far has touched either. `de_r` 44 is 47 % of [30, 60] and is untried.

## 8 Sep — session 147 as RUN: `lsd_b` 35 → 40 (issued) **and** `lsd_a` 20 → 18 (`driver`)

**Two changes in one run, allowed deliberately and the reasoning recorded** so this is not read
later as the one-change rule being dropped.

**They act on opposite throttle states and each has its own instrument, in a different distance
window, on a different channel:**

| change | acts | instrument | window |
|---|---|---|---|
| `lsd_b` 35 → 40 | **under braking only** | sub-0.90 rear frames · opposite-lock laps | T1, 240-425 m |
| `lsd_a` 20 → 18 | **on throttle only** | on-power rotation index | T3 1780-1960 m · T5 2140-2400 m |

`lsd_a` cannot act under braking and `lsd_b` cannot act on throttle, so **neither primary
reading can be moved by the other change.** ⚠️ **What IS confounded and must not be attributed:
lap time, and any whole-car feel report.** Lap time cannot resolve either change anyway
(σ 0.918 s).

⚠️ **`lsd_a` 20 → 18 is BELOW THE INSTRUMENT'S RESOLUTION and is not a test.** 14 → 20 moved
the T5 index +0.00024 against a 0.00104 floor; 20 → 18 is a fraction of that. It is a feel
adjustment, it is his, and it is recorded as his. **No prediction is attached to it and none
should be read into the result.**

**12 laps requested, and the number is arithmetic not habit.** T1 opposite-lock baseline at
`lsd_b` 35 is **5 laps in 15 (33 %)**. If the true rate were unchanged, seeing zero in N laps
has probability 0.667^N: **N=8 → p 0.039 · N=10 → 0.017 · N=12 → 0.008.** Twelve settles the
falsifier. The rear-lock half (2-in-15, 13 %) would need ~22 laps to prove absent on its own,
so **opposite-lock is the sensitive reading and rear lock is the corroborator.**
⚠️ **12 laps is 93.1 L of a 100 L tank — one stint, no refuel, no confound.** But RS at 2x puts
the right rear at **~66 % worn by lap 12** (0.055/lap measured), so **laps 1-9 are the clean
comparison** and anything after is read with the tyre state beside it.

## 8 Sep — session 147, `lsd_b` 35 → 40 + `lsd_a` 20 → 18. **HE IS RIGHT. `lsd_b` 40 OUT.**

`[DRIVER REPORT]` *"lsd_b is too high and actually made the rear slide more into T1... we are
still lacking mid corner rotation, I don't want lsd_a more than 18."*

**What `lsd_b` 40 did to the thing it was aimed at — it WORKED:** rear brake lock at T1
**0 laps in 5**, against 2 in 15 at `lsd_b` 35. Catches at T1 are still there (2 of 5 laps) but
tiny — biggest correction **−7.0°** against **−27.9°** and **−18.6°** at 35. And he arrived
**5-7 km/h faster** at the 250 m mark on every lap.

**⛔ AND WHAT IT COST, which is far larger.** Entry rotation at T1 (|yaw| per degree of lock,
brake ≥20 %): **0.01197 → 0.00485, a 60 % cut.** Front scrub through T1 mid-corner nearly
doubled, +0.0182 → **+0.0374**. ⇒ **the car will not turn into Turn 1**, he has to carry more
lock, and it runs wide on the front. **He described that as the rear sliding; I read it as the
front. The disagreement is recorded, not averaged** — what is not in doubt is that something
at T1 got much worse and he felt it on the first lap.

### ⭐⭐ MID-CORNER IS FRONT-LIMITED, AT EVERY CORNER, IN EVERY CONFIG — measured

Off both pedals (throttle <20 %, brake <20 %, >60 km/h, lock >10°, all tarmac). **Noise floors
by odd/even split of the 15 clean race laps: T1 0.00086 · hairpin 0.00027 · T5 0.00026.**

| config | T1 | right hairpin | your T5 | front slipping | rear slipping |
|---|---:|---:|---:|---:|---:|
| A · rh70 `lsd_a`14 `lsd_b`35 (race) | 0.00856 | 0.00806 | 0.00776 | +0.021 to +0.025 | +0.013 to +0.016 |
| C · rh64 `lsd_a`20 `lsd_b`35 | **0.00917** | 0.00746 | 0.00733 | +0.018 to +0.029 | +0.012 to +0.018 |
| D · rh64 `lsd_a`18 **`lsd_b`40** | 0.00693 | 0.00710 | 0.00694 | **+0.028 to +0.037** | +0.015 to +0.022 |

- **D loses mid-corner rotation at all three corners by 2-3.6× the floor.** Not marginal.
- ⭐ **The FRONT slips about TWICE what the rear does mid-corner, everywhere, in every config.**
  That is the answer to *"how else do we get mid-corner rotation?"* — **it is a front-grip
  problem, not a differential one.** The diff cannot fix it and `lsd_a` is not the lever.

**Pace is not the problem: s147 L5 = 103.250 s on 68.6 L ⇒ 103.044 fuel-corrected, the fastest
lap on file here**, ahead of s146 L5 (103.122) and s146 L9 (103.134).

**⇒ NEXT, session 148 — TWO changes, and he has authorised more than one when the car is not
working:**
1. **`lsd_b` 40 → 35, a REVERT.** His call and the measurement agrees. Not an experiment.
2. **`arb_f` 5 → 3** — the change. 44 % → 22 % of [1, 10]. **The front bar is the mid-corner
   lever that adds FRONT grip rather than taking rear grip away**, and it is the tool
   `01-inbox/01-driver-profile-leon.md` names first for mid-corner balance without sacrificing
   the rear. Camber is refused (4 Sep: front 1.0↔4.0 produced nothing measurable and it is a
   ride-height lever at 2.8 mm/deg, which would disturb the rake he has just settled); front
   wing is refused (F4: ±25-50 clicks is 3-6 % of aero load, invisible); front toe-out is held
   back because 3 Sep took `toe_f` −0.08 → 0.00 to remove a front L/R asymmetry and that fix
   is holding.
**PREDICTS** mid-corner rotation clears the best on file at every corner — above 0.00917 at
T1, 0.00806 at the hairpin, 0.00776 at T5 — and front slipping mid-corner falls below +0.020.
**FALSIFIED BY** mid-corner rotation unchanged, or the front scrub not falling.
⚠️ **THE CAUTION, stated because it has failed once:** `arb_f` toward softer was tried at Spa
on 31 Aug and reverted for feeling worse alone. `reference_setup_platform_before_sliders` says
why — *softening a front bar on a soft, high car just adds roll; it pays only with the rear bar
up and the springs stiffer.* **This car is now stiffer (nf 3.90/4.10) and lower (rh 58/64) than
the Spa car was**, which is the condition that note named. A reason to expect a different
answer, not a guarantee.

**⇒ THEN: `de_r` 44 → ~52.** `lsd_b` 40 was papering over the T1 rear brake lock at the price of
all the rotation. **Rear rebound is the lever that keeps the rear down under braking WITHOUT
touching rotation, and it is the same lever aimed at the Bus Stop kerb launch** — both are
extension events. One change, two problems.

## 8 Sep — session 148, `arb_f` 5 → 3 (+ `lsd_b` back to 35). **REFUTED. His report holds.**

`[DRIVER REPORT]` *"car feels less pointed at the front, more slidy and not as responsive."*
**This is the Spa failure mode reproducing, and I flagged it as the risk before the run.**

**Mid-corner rotation** (off both pedals; floors T1 0.00086 · hairpin 0.00027 · T5 0.00026):

| config | T1 | right hairpin | your T5 | front slipping | rear slipping |
|---|---:|---:|---:|---:|---:|
| A · race, `arb_f` 5 | 0.00856 | **0.00806** | **0.00776** | +0.021 to +0.025 | +0.013 to +0.016 |
| C · `arb_f` 5 `lsd_a` 20 | **0.00917** | 0.00746 | 0.00733 | +0.018 to +0.029 | +0.012 to +0.018 |
| D · `arb_f` 5 `lsd_b` 40 | 0.00693 | 0.00710 | 0.00694 | +0.028 to +0.037 | +0.015 to +0.022 |
| **E · `arb_f` 3** | 0.00883 | **0.00751** | **0.00723** | +0.013 to +0.028 | +0.010 to +0.017 |

**E loses rotation at BOTH hairpins by 2× their floors** (−0.00055 and −0.00053 against A).
T1 is unresolved. Best lap 103.678 at 77.0 L ⇒ **103.447 fuel-corrected, against 103.044 the
run before.**

### ⭐⭐ WHY, and it is the discriminator I should have measured first — ROLL

Front L/R suspension split through the corners, i.e. how far the car rolls:

| config | T1 front / rear | hairpin front / rear | T5 front / rear |
|---|---|---|---|
| A · `arb_f` 5 | 16.51 / 13.04 | 20.22 / 14.04 | 19.69 / 14.87 |
| **E · `arb_f` 3** | **20.07 / 15.22** | **22.27 / 16.67** | **21.14 / 16.03** |

⭐ **Softening the front bar added 1.5-3.6 mm of roll at BOTH ends and barely moved the
front/rear ratio** (1.27→1.32, 1.44→1.34, 1.32→1.32). It did not shift the balance — **it just
let the whole car roll more**, and the front lost the camber that roll costs it.
⇒ **`reference_setup_platform_before_sliders` reproduced exactly:** *softening a front bar on a
soft car just adds roll.* Refuted twice now, Spa 31 Aug and here. **`arb_f` softer is closed.**

⇒ **`arb_f` 3 → 5, a REVERT.** And the direction for front bite on this car is **LESS roll, not
more** — which the driver has now told me twice in different words.

**⇒ NEXT, session 149, one real change: `arb_r` 4 → 6** (33 % → 56 % of [1, 10]).
It does both things the evidence asks for: **more total roll stiffness (less roll, which is the
direction that just tested well) AND it moves roll stiffness rearward, which is the way to
rotation that does not need the front to find grip it has not got.** ⚠️ **It buys rotation by
taking rear grip, and that is affordable HERE and only here:** mid-corner the rear slips
+0.010 to +0.017 against the front's +0.021 to +0.029 — **the rear has grip in hand exactly
where he wants the rotation**, and `arb_r` acts in ROLL, so it does not touch the braking zone
where the rear lock lives.
**PREDICTS** mid-corner rotation clears the best on file at every corner — 0.00917 T1,
0.00806 hairpin, 0.00776 T5 — and total roll falls back under the config-A figures.
**FALSIFIED BY** rotation unchanged, OR rear slipping mid-corner rising above the front's.
⚠️ **THE RISK, named before the run: the Bus Stop.** A stiffer rear bar over a big kerb can
make the launch worse, and that kerb already throws the car every lap. If it is worse there,
that is the trade and **`de_r` 44 → ~52 is next** — still the one lever aimed at both the T1
rear lock and the kerb.

## 8 Sep — session 149, `arb_f` back to 5 + `arb_r` 4 → 6. **THE BEST THE CAR HAS BEEN.**

`[DRIVER REPORT]` *"that felt the best it has... did manage fastest 2nd sector ever but just
couldn't quite get it all together."*

### ⭐⭐ HE IS RIGHT AND MY INSTRUMENT MISSED IT. Record that, do not bury it.

**Sector 2 — both hairpins and his T5, exactly where `arb_r` acts:**

| config | n | S2 median | S2 best | spread |
|---|---:|---:|---:|---:|
| A · arb 5/4, the race | 15 | 36.233 | 35.786 | 3.364 |
| C · arb 5/4 `lsd_a` 20 | 7 | 36.060 | 35.904 | 13.803 |
| D · arb 5/4 `lsd_b` 40 | 3 | 36.123 | 35.890 | 0.424 |
| E · **arb 3**/4 | 4 | 36.008 | 35.882 | 0.170 |
| **F · arb 5/6** | **7** | **35.784** | **35.608** | 0.748 |

**S2 median −0.449 s on the race config and −0.224 on the next best, and the two fastest S2s in
the whole archive are laps 5 and 6 of this session** (35.608, 35.632; previous best 35.701).
**The controls hold:** S1 median 37.810 → 37.884 and S3 30.263 → 30.096, both unmoved. **The
gain sits in the one sector the change acts on.**

⛔ **And the mid-corner rotation index cannot see it.** T1 0.00856 → 0.00852, hairpin 0.00806 →
0.00820, T5 0.00776 → 0.00749 — every one inside or at its floor. **Two independent
witnesses (the driver and the sector clock) found something my index could not.** The index
measures yaw per degree of lock at an instant; it does not measure whether he can get the car
turned and driving. ⇒ **Do not let a null on a derived index outvote a driver report plus an
outcome measure.** [[feedback_calibrate_instruments_before_use]] cuts both ways.

**Where the time is NOT coming from: apex speed.** Hairpin v-min 88.1 → 88.2 km/h, T5 91.2 →
90.9. Unchanged. So it is the drive out and the transition between the two, not more speed in.

**⚠️ The risk I named did NOT happen. The Bus Stop is no worse:** on the grass **3 of 9 laps**
against **9 of 17** at arb 5/4, body lift 83.7 mm median against 82.9. A stiffer rear bar over
that kerb was the stated danger and it did not materialise.

**Roll came back down** where it matters: hairpin total 34.26 (A) → 38.94 (E) → **32.40** (F);
T5 34.56 → 37.17 → **33.09**. T1 alone is up (29.55 → 32.24).

⚠️ **`is_out_lap` = 1 on lap 7 is a MISDETECTION.** `[DRIVER REPORT]`: *"the issue the app
called a second out lap was me going off track too far and resetting back on track."* **GT7's
track reset looks like a pit exit to the detector**, and an out-lap is silently dropped from
every aggregate. Laps 7-9 (S3 of 41.7 and 42.4 s, crawl 3.6 and 3.4) are that reset and its
aftermath, not car behaviour. **App work; flagged, not fixed here.**

**⇒ NEXT, one change, and the last one before the race: `de_r` 44 → 52** (47 % → 73 % of
[30, 60]). Everything else stands. Two things are still open and this is the one lever aimed at
both: **the rear brake lock at Turn 1** — the failure that actually cost the race, and which
`lsd_b` 40 could only fix by taking all the rotation away — **and the Bus Stop kerb**, still
one lap in three on the grass. Both are EXTENSION events: the rear wheel rising. Rear rebound
damping holds it down, and unlike `lsd_b` it does not touch rotation.
**PREDICTS** laps carrying rear brake lock at T1 stay at zero and opposite-lock laps fall below
2-in-12; Bus Stop grass rate falls below 3-in-9; S2 median holds at or under 35.9.
**FALSIFIED BY** the Bus Stop rate unchanged, or S2 going backwards.
⚠️ **If it does nothing, race the arb 5/6 sheet.** It is the best the car has been on his report
and on the only outcome measure that has ever separated these sheets.

## 8 Sep — session 150, `de_r` 44 → 52. **REFUTED after 2 laps. Reverted.**

`[DRIVER REPORT]` *"lost rotation on throttle, no change in T1."* **He did two laps and came
in — that is a verdict.** Neither lap was clean (L2 2.0 s off, L3 2.8 s crawl and S1 44.8 s),
so there is no clean sector to compare, and I am not going to build a claim on two spoiled laps.

**Against the prediction:** T1 rear brake lock was to stay at zero — **1 of 2 laps carried it**,
against **0 of 9** at `de_r` 44. Bus Stop grass 0 of 2 (n far too small). S2 unmeasurable.
⇒ **Falsified on the half that could be read, and it cost throttle rotation that was not
predicted. `de_r` back to 44.**

⇒ **THE RACE SHEET IS THE arb 5/6 CONFIG, EXACTLY AS SESSION 149 RAN IT**, as promised before
that run: rh **58 / 64** · arb **5 / 6** · dc 20 / 20 · de **46 / 44** · nf 3.90 / 4.10 ·
cam 2.0 / 1.2 · toe 0.00 / +0.12 · lsd **6 / 18 / 35** · df 410 / 635 · ECU 96 · restrictor 99 ·
ballast 45 @ −29 · top 300 · RS/RS · `bb` 0. Beep 8,600 in 1/2/3, 4-6 silent.
**Best on his report and on the only outcome measure that has ever separated these sheets:
S2 median 36.233 → 35.784, with S1 and S3 unmoved.**

## ⚠️⚠️ 8 Sep — WHAT THIS SHEET IS ACTUALLY FOR. Read the calendar before the next session.

**NGR GR3 Season 1, from the league hub:**

| | | |
|---|---|---|
| Rd6 | **7 Sep** | Daytona Road Course — **RACED. Last night.** |
| **Rd7** | **14 Sep** | **Mount Panorama Circuit** |
| Rd8 | 21 Sep | Autodromo Nazionale Monza |

⇒ **A full day was spent perfecting a Daytona sheet for a race that has already been run.**
He asked for a more consistent car and that is what was delivered — but **the circuit half of
it expires now**, and nobody checked the calendar until the end of the day. **Put the calendar
in front of him at the START of a setup session, not the end.**

**What transfers to Bathurst — car facts, not circuit facts:**
- ⭐ **Less rake is the right direction there too, independently.** `05-track-reference.md`
  §Mount Panorama: *"avoid aggressive rake; pitch sensitivity over Skyline is dangerous."*
  Same conclusion from a different argument. See [[reference_rake_percent_of_range]].
- **This car wants LESS roll.** `arb_f` softer is closed — refuted at Spa and again here.
- **`arb_r` stiffer buys rotation** and did not hurt the kerbs.
- **`lsd_a` down gives LESS rotation on power** on this car — backwards to the textbook.
  **`lsd_b` up destroys entry rotation** (T1 entry index halved at 40).
- **Mid-corner is FRONT-limited** — the front slips about twice the rear, in every config tested.

**What does NOT transfer:** ride heights (Bathurst is bumpy with big crests and will want more
clearance, in tension with the rake finding — that is the first thing to settle there), the
gearbox, the shift table, and every corner-specific figure on this page.
