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

**What the runs can and cannot say (re-derived 4 Sep from `laps` + `lap_frames`, read-only):**

- **Two clean laps in five sessions.** Every per-run channel except wear and temperature is
  contaminated by off-track laps and is NOT comparable run to run. Lap time judges nothing
  (countable medians 104.3–106.1 s, sd 1.8–5.3 s).
- **Wear rate is identical across all five setups at the gauge's resolution** (`hud-video`,
  1 px ≈ 2.8 %): RR **0.0556/lap** in every run, FL 0.0347–0.0370. Replicates the race-stint
  **0.0570** (3 Sep). ⇒ neither ±25 of rear wing nor camber 1.0↔4.0 moved rear wear over 4–5
  laps; a difference would have to exceed ~12 % of the rate to show at this resolution.
- **Front camber 1.0 → 4.0 does not move front surface temperature** (65.1/65.0 vs 65.8/65.0 °C
  median; floor 0.9–1.4 °C). Cam 4.0/4.0 rears read **74.2/75.6** vs baseline 72.3/73.5 — +2 °C,
  at the floor's edge, on countable laps with offs. Not a finding.
- **Terminal:** 285.9 (420/600) · 283.9 (420/650) · 284.8 (410/635) · 285.1 · 285.4. The
  50-click rear-wing spread is **2.0 km/h, inside the 0.56–2.77 km/h terminal floor.** Nothing
  to say about drag from these runs.
- **The GT7 "Measure" readout IS responsive to aero** (high-speed stability −0.45 → −0.36 across
  420/600 → 420/650) **and inert to camber** (−0.43 at both 1.0/1.0 and 4.0/4.0). Refines entry S:
  it is inert to suspension and geometry, not to everything.
- **Not established:** what `bb` was in the car; whether any spin/off was setup-related.
