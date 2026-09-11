# The experiment ledger

Plan row 2.1 (`docs/ENGINEERS-ASSESSMENT-AND-PLAN_2026-09-06.md` §6). One file
per car × circuit, beside its car-state file. **Every setup change tested
against a control is a row here, and so is every open prediction.** `refine`,
`race plan` and `debrief` open it first (`.claude/skills/ludo/SKILL.md`).

**It never holds a setting.** `brain/car-state/<car>-<circuit>.md` is the only
place a setup value is written (`CLAUDE.md` §1a). A row holds the key, the
direction and the delta in percentage points of the car's slider range - never
a `from` or `to`, and never a position written as a percentage. A change
ledger in the database was the second setup record §1a removed; `setup_changes`
is a writer-less archive now.

**The app writes nothing here.** These are brain files, written by the tune
builder and reviewed like any other.

## Columns

`date, session_ids, key, direction, delta_pct_range, instrument,
measured_floor, control, prediction, falsifier, outcome, source,
car_state_rev` - one fenced `csv` block per file (Sardegna has two, one per
week), parseable by any CSV reader.

## Conventions

- **No `from` / `to` setup value appears in any CSV row** (CLAUDE.md §1a; plan "Ledger rule",
  pass-1 fix 3). A row holds the key, the direction, and the delta in percentage points (pp) of
  the car's slider range. Where a file's prediction would name a setting, the row
  says "one click" / "−11.1 pp" instead. The notes show each delta as *step ÷ span*. The step
  size is a difference, not a setting, and no note restates a from/to pair.
- **Ranges used.** Huracán GT3 '15, v1.71, `verified`, read 24 Aug 2026. This is
  `brain/_inbox/11-car-slider-ranges.md` §0.2: five moved endpoints plus "every other endpoint
  unchanged from v1.70". The Daytona file (§7 Sep rake table; lines 217, 222, 267) and the
  Bathurst file (sheet header) corroborate it: rh_f [55,80], rh_r [60,90], nf [3,5], arb [1,10],
  dc [20,40], de [30,60], cam [0,6], toe [−1,1], lsd_i [0,30], lsd_a [0,100], lsd_b [0,100],
  df_f [350,450], df_r [500,700], bb [−5,5], top [200,800], fg [2,5].
  Porsche 911 RSR '17, v1.71, `verified`, 21 Aug 2026 (`11-car-slider-ranges.md`, RSR v1.71
  block; the Sardegna header says its endpoints reconcile with Rev C §5). Same endpoints as the
  Huracán except lsd_b [0,99].
  Shelby GT350R '16, v1.71, `verified`, 23 Aug 2026 (`pitcrew.db` `range_records`, read read-only
  11 Sep). Same endpoints as the Huracán except rh_f [75,160], rh_r [95,180], nf [2,4],
  df_f [50,150], df_r [150,300]. The range register still carries a stale v1.70 reading: the
  Shelby file's (b)-S1.
- **Gear ratios, shift tables, ECU, restrictor and ballast have no slider range** in any range
  record (`pitcrew/setup/vocabulary.py` `RANGE_KEY_NAMES`; `ranges.py`). Those rows read
  "range unknown" and are also listed in (a).
- **Outcome.** `confirmed` / `refuted` / `unresolvable` / `open`. `unresolvable` means the
  instrument could not see the change. It is not `refuted`. Every `refuted` row carries its
  direction in `direction`, and only that direction is refuted. Where a file never re-scored a
  prediction but later reports the exact quantity the falsifier names, under the stated
  conditions, the row is scored and marked **"scored from the file's figures"**. Where the
  conditions do not match, the row stays `open` and is flagged in (b).
- **Floor.** Quoted exactly as the file gives it. "not established" where it gives none.
  Never 0.
- **Keys and directions.** Coupled keys are joined with `;`. Direction words: up/down, stiffer/
  softer, forward/rearward (bb: + is rearward on both the Huracán and the RSR), longer/shorter
  (gearing).
- Non-setup predictions (fuel, wear, strategy, measurements to take) are included because
  plan 2.1's done-when says "every open item above has a row". Their `key` is `n/a (…)`.

## How a row is added

`refine` step 6 writes it **before the run**: key, direction, delta, the
instrument and its measured floor, a no-change control, the prediction and a
complementary falsifier. Step 7 closes it on the same instrument, against the
control's drift - `confirmed`, `refuted` (with its direction), or
`unresolvable`. **`unresolvable` is not `refuted`.**

Seeded 11 Sep 2026 from the four car-state files by a read-only extraction,
reviewed before writing; positions stated as percentages in the extraction's
prose were removed.
