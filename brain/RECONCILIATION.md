# Reconciliation — the knowledge base against the code

**Written 21 Aug 2026**, on importing the "My Driving Style - Tuning" Project into
`brain/_inbox/`. Every claim the knowledge base makes *about the Pit Crew app* has
been checked against the code and the database as they stand today.

**Nothing here has been decided unilaterally.** Where the two disagree, both sides
are stated with their evidence and the verdict is marked. Section D is the part
that needs your ruling.

`CLAUDE.md` §4.1: *where the driver's report and the telemetry disagree, that
disagreement is the finding.* The same applies to two written records of the same
system.

---

## A. The knowledge base is out of date — the app already fixed it

These are recorded in the KB as open defects. They are closed in the code. **The
KB should be amended**; no app work follows.

| # | KB says | The code says | Where |
|---|---|---|---|
| A1 | `15` §3: *"tell Pit Crew this car is MR / rear-wheel drive. Outstanding since Rev B (14 Aug)"* | The field exists and is used — `events.drivetrain`, consumed by `thresholds.wheelspin_wheels(drivetrain)` | `analysis/corners.py:474` |
| A2 | `15` §5.1: `gearingConstantK` *"computed with the derived final gear, not the sheet's"* | Fixed, and documented as such: *"It uses the final drive off the sheet, not the derived one."* `final = sheet_final_gear or derived_final_gear`, with `gearingConstantFinalGear` and its source both exported | `analysis/gearing.py:224` |
| A3 | `15` §5.2: *"`callsMade[].accepted` is false on all 14 calls… needs `informational` / `offered` / `taken` / `declined`"* | A `disposition` field now travels beside `accepted` in the calls ledger | `export/payload.py:1107` |
| A4 | `15` §2: `understeerWheelbaseM: 2.516` *"assumed — the recorder does not store the packet's wheelbase"* | `sessions.wheelbase_m` is stored from the packet and used; the constant survives only as a fallback for sessions predating the column, and the export declares which was used | `store/schema.py:830`, `analysis/thresholds.py:289` |
| A5 | `15` §5.5: `runs[].compound` *"null on both runs"* | 296 of 333 laps now carry a compound | `laps.compound` |
| A6 | `17` §8 and Standing Rule 10: *"`meta.gameVersion` is missing from the packet. Priority-one fix"* | **Required since contract 1.4 — the export refuses a payload without it.** See D1: the KB was right that nothing was *filling* it, which is a different defect and is now fixed | `export/payload.py:267` |

---

## B. The knowledge base is right — still open in the app

| # | Defect | Evidence today | Severity |
|---|---|---|---|
| B1 | `15` §5.4: `fuelMap` null | **79 of 333 laps populated (24%).** The whole fuel model is expressed per map, and `04`/`03` reason in map steps throughout | high — cheapest field on the sheet |
| B2 | `15` §1 fixes 1–3: per-speed-band reference, mean heave reported alongside per-wheel minima, kerb frames excluded | Not implemented. See C1 — the underlying mechanism turned out to be different, but these three remain good ideas independently | medium |
| B3 | `15` §2 fixes 2–3: normalise the yaw deficit for speed; report a continuous magnitude rather than a boolean | The `1/v²` structural bias argument stands and is analytic | medium |
| B4 | `15` §4: the `setup` / `performance` / PP block is stale | Not re-checked in this pass — needs a session to confirm against | **high if still live** |

---

## C. Both records found the same fault by different routes — and the app's mechanism is the better one

### C1. `bottoming` — the KB has the right verdict and the wrong mechanism

**Both agree the flag was invalid and that the Rev C ride-height raise is withdrawn.**
They disagree on *why*, and the difference changes the fix.

**The KB (`15` §1)** says the reference is taken at maximum aero load, so every
corner sits higher and the flag catches the loaded wheel of any car that rolls.
Supporting evidence: T4, T7 and T8 flag 17/17 while mean heave is 5–8 mm *higher*
than reference; all three are right-handers.

**The code (`analysis/corners.py:139`)** says something more fundamental:

> `susp_mm_*` **is COMPRESSION, not height** … `body_height_mm` falls to 50.5 mm as
> downforce builds, while every `susp_mm_*` **rises**, 257 → 269 front and 279 → 289
> rear. Two channels, the same frames, opposite signs. So the bottoming end of the
> trace is the **maximum**, and taking `min` took the most **extended** the wheel ever
> got.

**The app's account explains strictly more of the evidence.** It predicts the
same-handed inside-wheel pattern the KB observed *and* it explains the KB's own
falsification test — raising the car 5 mm made the reported depth double, which the
roll hypothesis does not account for and an inverted-polarity reading does exactly.

**Recommendation: the KB adopts the code's mechanism.** `15` §1 keeps its evidence
and its verdict; its "The fix Pit Crew needs" list is superseded by the polarity
correction, with items 1–3 demoted from fixes to improvements (they remain B2).

*This is the clearest case in the set for why the brain has to live in version
control: the KB has been carrying a plausible, well-argued mechanism that the
telemetry had already disproved.*

### C2. Things both records independently confirm

Worth recording, because agreement from two directions is stronger than either alone:

- **The Rev C ride-height raise was bought by a flag that could not measure what it
  was named for.** KB Standing Rule 8 prices it at *"5 mm of ride height and 2 mm of
  rake, changed for no reason."*
- **Monza's front wear side is LEFT** (FL 0.79 vs FR 0.63). `05-track-reference.md`
  still has it backwards, outstanding since 12 Aug.
- **Rear-left is the worst-wearing corner.** Eight prior gauge readings, never once a
  front — and the live OBS sampler proved on 21 Aug made it nine.
- **Refuel is ~1.0 s per litre against ~0.07 s per lap of stop delay — a 14× ratio.
  Optimise litres, not lap.**

---

## D. Decided today, during this pass

| # | Finding | Action taken |
|---|---|---|
| D1 | `game_version` was NULL on every session, on the Monza event, and on all three slider registers. The KB called this its highest-priority app defect and was right about the *effect*, wrong about the *cause* — the field was required, but nothing filled it | Sessions now stamp at recording; the register takes the installed version rather than the event's; 58 sessions backfilled to 1.70, 2 to 1.71, three registers stamped. Commits `50f06eb`, `6bd9dcb` |
| D2 | An event export flattened every session into one payload under one version. Event 1 holds 44 sessions spanning the 20 Aug patch | The export now **refuses** an event that straddles two versions, naming the sessions on each side. Commit `50f06eb` |
| D3 | The slider register held the RSR's v1.71 endpoints beside the Shelby's and Huracán's v1.70 ones with nothing marking the difference — and 1.71 moved the LSD axes off a shared 5–60 onto 0–30, 0–100 and 0–99 | Stamped. **`17` §6's warning now holds in the app as well as on paper: express LSD in absolutes until the whole register is re-read** |

---

## E. Needs your ruling

**E1. Two cars have no drivetrain declared.** `events.drivetrain` is `MR` for the
Huracán and **NULL for the RSR and the Shelby**. The KB's own settled facts say the
911 RSR '17 is MR; the Shelby GT350R is front-engine rear-drive (FR). Setting both
closes the contaminated `wheelspin` channel on two more cars — but they are *your*
declarations to make, and the app is explicit that drivetrain is declared or
unknown, never guessed. **Shall I set RSR = MR and Shelby = FR?**

**E2. `06-race-strategy-design-research-2026-08-12.md` is not in the Project
export.** It was loose in Downloads, and the export's own `06` is
`06-car-building-and-pp.md`. It is a 61 KB strategy-design document whose provenance
I cannot establish. **Keep it in the brain, or set it aside?**

**E3. Pre-1.71 data — archive or leave live?** 58 of 60 sessions and two of three
slider registers are pre-patch. The KB says they are a control group, not values to
tune from. The app now refuses to export event 1 whole, which enforces that at the
boundary — but the aggregates, compound profiles and wear models still read every
lap regardless of version. **Should the analysis layer filter by game version too,
or is the export refusal enough for now?**

**E4. Which record is authoritative when they drift again?** This pass found six
places where the KB was stale and one where the code was. Nothing keeps them in
step. Options: regenerate the KB's app-facing sections from the code, have the
debrief write back into `brain/`, or accept drift and re-reconcile per patch.

---

## What was not checked

Honesty about coverage: this pass read `00`, `10`, `15`, `16` (index and §11–12),
`17`, and the app-facing parts of `12`–`14`. **The four large reference documents —
`02` setup parameters (123 KB), `03` tyres and fuel (89 KB), `04` race vs qualifying
(98 KB), `05` tracks (155 KB), `06` car building (90 KB), `07` car profiles (74 KB)
— were surveyed structurally but not read line by line.** Their 1.71 exposure
banners are the KB's own assessment and have been taken at face value. Contradictions
between those documents and the app's models may exist and have not been looked for.
