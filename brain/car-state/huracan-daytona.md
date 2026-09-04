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
| 6th gear | **0.980** (instrument) | **1.030** | **1.030** `FEED` | **1.030** `FEED` (K6 36.004) — **1.010 proposed for the race** |
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
2. **There is no Daytona `setup_sheets` row at all** for this car. `check_setup_sheets.py`
   lists Spa, Fuji and Watkins Glen and simply does not mention Daytona.
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
- **`tools/log_setup_change.py`** files a change with its reason, or attaches one to a
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
`bb` is not on that page and was not asked: **`?`**. Gearbox not on that page: `FEED` says 6th
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
partial 91.6 s or 7–9 s on the grass) and `is_out_lap` is 0 on all of them — fix in progress.

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

**Not established:** `bb` in the car for any of the five.
