# Reconciliation — the knowledge base against the code

**Written 21 Aug 2026**, on importing the "My Driving Style - Tuning" Project into
`brain/_inbox/`. Every claim the knowledge base makes *about the Pit Crew app* has
been checked against the code and the database as they stand today.

**Nothing here was decided unilaterally.** Where the two disagree, both sides are
stated with their evidence and the verdict is marked. Section E carried the four
questions that were the driver's to answer; all four were answered on the day and
the reasoning is recorded there with the outcome.

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
| B1 | `15` §5.4: `fuelMap` null | **Not a code defect.** Laps inherit the event's declared map and do so perfectly: event 3 declares `1` and all 79 of its laps carry it; events 1 and 2 declare nothing and 0 of 254 do. **It has simply never been entered on two events.** See E5 | data entry, not code |
| B2 | `15` §1 fixes 1–3: per-speed-band reference, mean heave reported alongside per-wheel minima, kerb frames excluded | Not implemented. See C1 — the underlying mechanism turned out to be different, but these three remain good ideas independently | medium |
| B3 | `15` §2 fixes 2–3: normalise the yaw deficit for speed; report a continuous magnitude rather than a boolean | The `1/v²` structural bias argument stands and is analytic | medium |
| B4 | `15` §4: the `setup` / `performance` / PP block is stale | **CONFIRMED LIVE, and the cause is upstream of the app.** `Store.sheet_for` correctly returns the newest sheet it holds; the fault is that revisions are issued, typed into GT7, and never filed. `tools/check_setup_sheets.py` now detects it — see E6 | **high** |

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

## E. Ruled on, 21 Aug 2026

**E1. Drivetrain — answered "yes, and it should be derived from known car
details."** `cars.drivetrain` is already seeded from GT7's own car list, so the
catalogue now answers whenever nobody has declared: the RSR resolves to MR and
the Shelby to FR, matching the KB's settled facts. It travels with its source,
because the catalogue describes the car as shipped and cannot know about an
engine swap that open tuning permits — so a declaration on the event still wins.
Commit `41bdf0c`.

**E2. The orphan strategy document — kept, and moved.** Now
`brain/strategy-design-2026-08-12.md` with a provenance header. Kept because it
is the only record of why `pitcrew/strategy/` enumerates rather than solving
(6.7 M DP states against 3,905 candidates scored in 106 ms) and why the tyre
gauge is primary evidence rather than a lap-time fit. Moved out of `_inbox/`
because that directory is the faithful record of what the Project contained, and
this was never in it.

**E3. Version precedence — answered "use it as a guide but new version date
trumps old data."** Implemented as `analysis/version.py` and applied in
`strategy/evidence.build_inputs`, which is the single point where a race plan's
evidence is assembled.

The design decision worth recording: **a patch is a discontinuity, not a decay.**
`analysis/recency` weights old laps down because the driver gets faster and the
setup moves on — that is a decay and a weight expresses it. Laps either side of
1.71 are not weaker and stronger evidence about one car; they are evidence about
two, and no weighting turns the first into the second. So version is a
*precedence tier*: current-version laps are used alone where there are at least
three, older ones are held back rather than blended, and where there are too few
the plan says out loud that it rests on pre-patch evidence.

**This withdrew an exemption `recency.py` states in its own words** — *"a gauge
reading from three weeks ago is exactly as true as one from today."* That was
right, and right for a good reason: a gauge reading measures GT7's own wear model
rather than estimating it, so age cannot erode it. It holds only while the wear
model is the same model, and 1.71 changed it. **The exemption stands within a
version and is void across one.**

Effect on the live database: the Monza plan now builds on the 12 laps recorded
since the patch and holds back 206, and the reference lap moves from 1:49.2 to
1:52.0. A materially different plan, which is the point. Commit `6007ed6`.

**E4. Keeping the two records in step — `pitcrew/tests/test_brain_reconciliation.py`.**
Asked to design it, and the answer is a test rather than a process, because a
process needs somebody to remember and a test does not.

Each claim in sections A and B above is encoded as an assertion. **A failure
there is not necessarily a bug** — it means the code moved and this document is
stale, and the message says which section to amend. It runs in both directions:
section A asserts things the code *does* do, so a regression to a state the KB
already calls a defect fails loudly; section B asserts things the code *does
not yet* do, so when one is fixed the test fails and the news is good — delete
the test and strike the row.

**Asserting that a defect still exists is deliberate.** The alternative is that
a fix lands, nobody updates the knowledge base, and a document goes on telling a
race engineer to work around something that stopped happening. That is precisely
how §C1 came about. Commit `d08fde4`.

**E5. `fuelMap` — the mechanism works; the declaration is missing.** Laps
inherit the event's declared fuel map, and where one is declared every lap
carries it (event 3: 79 of 79). Events 1 and 2 have never had one entered, so
0 of 254 laps do. **This is yours to declare, not the app's to infer** — and
worth noting, the knowledge base does not record your fuel-map discipline
anywhere either. That belongs in the driver file whenever Phase 1 writes one.

**E6. The stale setup block — confirmed, with a detector.** `Store.sheet_for`
is not at fault: it returns the newest sheet it holds, and does. The fault is
that a revision is written, typed into GT7 and **never filed into Pit Crew**,
so the app faithfully reports the newest sheet it has — which is not the newest
that exists. Nothing inside the app could see that, because the missing sheet
is missing.

`brain/` being in the repository makes it visible for the first time.
`tools/check_setup_sheets.py` compares issued setup documents against stored
sheets. On the day it was written it found two:

| Car | Knowledge base | App holds | Gap |
|---|---|---|---|
| Porsche 911 RSR | `2026-08-21-rsr-monza-revC.md` | `Monza race v2`, 14 Aug | **7 days** — sessions 59 and 60 affected, which are the two the v1.71 results were measured from |
| Ford Shelby | `2026-08-16-shelby-yas-marina-revC.md` | `Yas Marina race v2`, 13 Aug | **3 days** — 4 sessions affected **including the race, session 44** |

### E6 amended — the first version of this compared dates and cried wolf

Comparing dates said all three cars were behind. **Comparing values says
something much sharper**, and one of the three alarms was false:

| Car | Verdict |
|---|---|
| **Porsche 911 RSR** | **Identical.** Rev C's own first line says *"UNCHANGED from Rev B"*, and all 22 values match what the app already holds under the older name. **Nothing to file.** |
| **Ford Shelby** | **`rh_f` 80 → 89, `rh_r` 98 → 107.** Everything else matches. 4 sessions affected, **one of them the race.** |
| **Lamborghini Huracán** | **`rh_f` 65 → 68, `rh_r` 72 → 75.** Everything else matches. 5 sessions affected, **one of them the race.** |

**Both real differences are ride height and nothing else** — and the Huracán's
+3/+3 is the raise that `15` §1's `bottoming` flag bought, whose rationale was
withdrawn but which he won the race on. The app has never had it.

`tools/read_setup_document.py` does the extraction. Two things it had to get
right, both found by checking rather than by shipping:

* **The reply parser cannot read these documents.** Handed one it returned three
  values and all three were wrong, because the range table further down the page
  also contains numbers. These are presentation tables with a race column and a
  qualifying column side by side; the reply parser expects a reply.
* **A negative toe is written with U+2212**, not a hyphen. Left alone the number
  regex skipped it and read the Shelby's front toe of −0.05° as **+0.05°** — a
  sign error on a parameter whose sign is the whole setting, arriving silently.


## F. Reversed by the Fuji race, 25 Aug 2026

Full working in `fuji-race-2026-08-24.md`. These are the entries that change a
verdict either record already held.

| # | Finding | Ruling |
|---|---|---|
| F1 | **The Watkins setup-provenance conclusion is REVERSED.** The sheet linked to the Watkins race was created four days after it and disagrees with the sheet its own practices point at by 3 mm of front ride height, which read as a retrospective reconstruction overwriting the real record | `laps.gear_ratios` is decoded from the packet and copied from no sheet. Session 49 reports 6th = 1.055, matching Rev D **to 9.5e-08** and missing the other sheet by 5.0e-03; all three practices agree. Suspension height corroborates — race-versus-practice differs by the same margin as the practice-to-practice control, 6–12× smaller than the 3 mm in dispute. **Rev D was in the car. The PRACTICES are the mis-linked sessions.** The car was never raised |
| F2 | Fresh tyres arrive at a knowable temperature | **Refuted for the third time, with a third value.** 45 °C, exactly 70 °C, and now exactly 60.0 °C, all four corners converging in one frame. Any fixed fresh-tyre constant is fabricated and nothing may be gated on one |
| F3 | Pit loss is a track constant | **The total still is; the decomposition is not.** Fuji: 22.05 s dead time against 7.5 s modelled, and 6.8 s transit against 20 s declared. The two errors nearly cancel here and will not on a splash-and-dash, where there is no fuel time for the dead time to hide in. Fuji's dead time includes a tyre change and Watkins' 6.79 s may not |
| F4 | "No degradation detected" over a long stint | **Must never be reported as "the tyres did not degrade".** The Fuji null bounds *average* degradation below ≈0.03 s/lap, but against the piecewise shape `03` requires, the smallest detectable end-of-stint step is ≈0.8 s/lap — inside the 0.5–1.5 s/lap band it was meant to catch. It does not refute the planned rate, and with no gauge reading in existence nothing can arbitrate |
| F5 | The app's strategy layer is the better record of what constrains a stint | **Not while it reports the wrong constraint.** The plan was capped by the longest stint ever run (6 laps) and reported *fuel*. Fixed in the app and in the export contract (1.6 adds `evidence`), but the KB should read any pre-1.6 `bindingConstraint` of `tyre` or `fuel` as possibly meaning neither |

| F6 | The fitted tyre archive is a trustworthy record of what has been measured | **It was not, and three faults stacked.** (a) Every model was stamped with a game version collected from `events.game_version`, unioned across all events — event 6 is NULL there while its sessions say 1.71, so all 76 models read `1.70`, including four fitted entirely from post-patch laps. (b) `Scope` — "the keys a fit may never cross" — did not include the version, so fits **pooled across the physics patch**: Monza Racing Hard held 95 laps over 8 sessions spanning 20 Aug at confidence `high`, the largest sample in the archive. (c) `tyre_models`' UNIQUE key had no version either, so once the scopes separated the post-patch write **deleted** the pre-patch row, losing 74 laps silently. Fixed in `ec02d4b`, schema v9. Archive now 84 models, 48 pre-patch and 36 post-patch, none straddling. **Any conclusion drawn from a fitted model before 25 Aug 2026 should be re-checked against the version it actually rests on** |
| F7 | The export contract is ahead of the app | **Behind it, and it cost the one verified sheet.** The Fuji sheet is the first read off the car's own settings screen rather than transcribed, and it carries the build block that screen shows. The export refused it on four undeclared keys — `drivetrain`, `weightBalance`, `torqueKgfm`, `displacementCc` — so it could not be exported at all. Declared in contract 1.7 rather than dropped: none is derivable from `values`, and `drivetrain` in particular existed nowhere in the app, so every diagnosis turning on which axle drives was made without it |

**And one thing both records got right.** The driver overrode the engineer twice
and was right both times — the fourth consecutive session in which his judgement
beat the app's. `driver.md`'s fuel-margin refusal is reaffirmed: the 8.3 s of
fuel carried across the line is charged to the app's in-box call, not to him.

---

## What was not checked

Honesty about coverage: this pass read `00`, `10`, `15`, `16` (index and §11–12),
`17`, and the app-facing parts of `12`–`14`. **The four large reference documents —
`02` setup parameters (123 KB), `03` tyres and fuel (89 KB), `04` race vs qualifying
(98 KB), `05` tracks (155 KB), `06` car building (90 KB), `07` car profiles (74 KB)
— were surveyed structurally but not read line by line.** Their 1.71 exposure
banners are the KB's own assessment and have been taken at face value. Contradictions
between those documents and the app's models may exist and have not been looked for.

---

## G. Reversed by the Red Bull Ring Short practice, 27 Aug 2026

Session 93, event 8, Ford Shelby GT350R '16, v1.71, 11 laps.

| # | Finding | Ruling |
|---|---|---|
| G1 | **`top` is the road speed at which top gear reaches the limiter.** Asserted 26 Aug 2026 from Road Atlanta session 77: Vmax 275.7 km/h at 8,092 rpm with `top` 300 and a ~8,805 limiter, giving 275.7/300 = 8092/8805 = 0.919 to three figures | **REFUTED at n=2.** `top` was set to 265 for this session. The box that came out tops 6th at **291.1 km/h**, not 265 — the identity misses by 26 km/h. GT7's Top Speed slider is a **gear-spacing** control that anchors near the top and compresses the bottom: the requested −11.7% moved 1st by **+46.6%** (2.614 → 3.832) and 6th by **+3.0%** (1.019 → 1.050). The Road Atlanta agreement was one point promoted to a law. **`top` cannot be used to bring top gear down; only `fg` or Manual Adjustment can** |
| G2 | `lsd_a` 17 is leaving exit traction on the table at Red Bull Ring, and 17 → 24 is worth a run. Proposed 26 Aug from `05-track-reference.md` §1.10 (*"rewards diff lock more than almost any other circuit"*, 28–35 for FR) | **REFUTED before it was run, from 4,648 corner-exit frames.** Median left-right rear slip gap on power is **0.0000**; when the rear does let go, **both wheels go together in 5.5% of frames against one wheel in 2.6%**, and of the one-wheel frames it is the unloaded inside right 113 times to 6. A rear axle already turning as one is not short of lock — raising `lsd_a` would push it toward the spool that Rev B found on the 992 at Spa. **The exit looseness is a traction limit, not a differential limit** (mean rear slip 1.0422 against front 0.9985 on the same frames) |
| G3 | `bb` 0 will be comfortable on the uphill stops at Red Bull Ring, because uphill braking loads the front for free (`05` §1.10) | **FALSIFIED.** He reported the rear excited under braking, and the in-car MFD photographed on lap 12 reads **−1** — he moved it back himself and the app recorded nothing. Fifth consecutive session in which the driver's judgement beat a derived or doctrinal call. The doctrine is not wrong about the physics; it was wrong about this driver, who trail-brakes deep by design and needs the front axle to take the stop |
| G4 | The circuit reference's wear axle for Red Bull Ring — *"Rear + front-right"* | **Wrong for this car here.** Gauge read off the HUD after 11 laps: **FL 22.2%, RL 19.4%, FR 13.9%, RR 12.5%** — front-LEFT worst and front-RIGHT nearly the least worn. Corroborated by temperature on the same laps (FL 66.6 °C against FR 55.5 °C; RL 76.5 against RR 69.5). The Short Track is right-hand dominant, so the left side is the loaded side. The reference's line is for the **Full** course and has never been checked against the Short |

**One app defect, filed rather than fixed.** `pitcrew.telemetry.hud.read_gauge`
was handed this 3840×2160 still and returned `wear={'fl': 0.0, 'rl': 0.0,
'fr': 0.0, 'rr': 0.0}` with `located=True, rows=19`. The bars in that image are
**72 px tall**, not 19, and all four carry visible red. A reader that cannot
find the gauge must return **null**, not four zeros — CLAUDE.md rule 3 — and had
this been fed to the wear model it would have recorded a set with no wear on it.
The right-hand bars are also partly occluded by the driver's glove in this frame,
which the reader has no test for.

### G — amendment, session 94, same evening

**G2 stands for the dominant failure mode and is qualified for the residual.**
Rev B ran 13 laps (session 94, sheet still recorded as v1 — sixth consecutive
wrong setup record; the gearbox proves Rev B was in the car, matching to 1e-7).
Over 4,505 matched corner-exit frames the **both-rears-together** mode, which was
the basis for refusing `lsd_a`, **halved: 5.5% → 2.7%.** The single-wheel mode
rose 2.6% → 3.8%, and it is the **right rear every time** (RR alone 165 frames,
RL alone 6, unchanged from v1's 113/6) — the unloaded inside wheel of a
right-hand circuit. **Total spin is down (8.1% → 6.5%) but its composition has
inverted**, and single-wheel spin is the case `lsd_a` exists to fix. The refusal
was correct against the evidence that existed; the evidence has moved. It is a
named test now, not a refusal.

**G1's replacement is verified.** The gearing constant `ratio × speed-at-limiter
= K = 305.66` predicted 3rd would top at **173.7 km/h**. Measured on the limiter
in 3rd: **173.2 mean, 41 frames.** 0.3%. Cut gearboxes from K.

---

## H — Spa Round 5, sessions 90–97, Huracán GT3, v1.71, 27–28 Aug 2026

| # | The prior claim | What the data says now |
|---|---|---|
| H1 | *"Spa short-shift trade: 2.79 L per 1000 rpm, scaled from Fuji's 28.0% of lap fuel"* (Ludo, 27 Aug, `project_spa_round5_initial_2026_08_26`) | **REFUTED on magnitude, confirmed on sign.** Measured at Spa on his own laps, A/B/A over 27 clean laps, pooled OLS: **+2.131 L per 1000 rpm, SE 0.152, t +14.02, 95% CI [1.833, 2.429]**. The 2.79 estimate lies outside the interval — the Fuji-percentage scaling over-reads by 24% |
| H2 | *"3 laps at 7,200 in gears 3–5 vs the 4 on file at ~7,930 — a 730 rpm separation, larger than anything ever measured on this car"* would settle the lap-time cost | **REFUTED.** He ran it, at a 700 rpm separation over 27 laps, and lap time is **still unresolvable**: −1.396 s per 1000 rpm, SE 1.181, t −1.18, 95% CI [−3.71, +0.92]. The interval spans zero and spans the break-even. A bigger rpm separation is not the missing ingredient; his 2.77 s lap-to-lap spread is |
| H3 | The Raidillon lift is bottoming, and rh 68/77 → 73/82 will remove it. Instrument: min body height at 1,000–1,150 m must clear 18 mm | **CONFIRMED, on both instruments and completely.** Body-height minimum in the window: 16.30 mm median on 68/77 → 18.36–21.77 mm on 73/82. **Minimum throttle across 1,000–1,250 m is 100% on 25 of 26 clean laps** where the 27 Aug best lap dropped to 43.5%. Counter-check Pouhon min speed 158.7 → 169.7 km/h. It is at the line, not clear of it: 3 of 7 laps in session 97 still dip below 18 mm |
| H4 | Fuel binds stint 1 before tyres do | **CONFIRMED again.** `fuel_limited_laps(100, 8.886) = 10`; RS at 0.06731/lap gives 12.6. Fuel capacity binds, and at full-rpm shifting (9.636 L/lap measured) a 10-lap stint is 96.4 L raw of a 100 L tank with no other feasible one-stop split |
| H5 | Brake bias is what makes his braking inconsistent | **Not on this evidence.** 28,639 braking frames, five sessions, at `bb +3`: front axle below 0.90 slip on 7.19–15.32%, **rear axle on 0.00% in every single session**. Third circuit, second game version, same answer. The rear has never locked on this car |

**The finding of the session, and it is new.** The rear differential is welded
under power and effectively open everywhere else. 89,187 cornering frames above
50 km/h, 26 clean laps, share where the two rear wheels turn at exactly the same
speed: **power ≥60% throttle 87.70%** · maintenance 5–60% **11.86%** · lift
**4.71%** · braking **2.23%**. The open front axle reads 0.00–0.08% in every one
of those regimes, so the instrument discriminates. Four of the six driver
symptoms — will not hold line on maintenance throttle, nervous/darty mid-corner,
loses rear when I lift, braking distance inconsistent — are one problem living in
the three regimes `lsd_a` does not reach. `lsd_i` is the only axis that acts
independently of throttle and brake, and it was at 6 of 30.

**Two app defects, filed rather than fixed.**
1. `strategy.model.binding_limit(inputs, profiles)` returns **`(3, 'evidence')`**
   for this race — capped by the Racing Medium's 3-lap longest measured stint —
   while `recommend()` on the same inputs returns a 10 + 10 plan off
   `fuel_limited_laps`. **The reported constraint comes from a different
   expression than the decision**, which is CLAUDE.md rule 12 and the Fuji defect
   verbatim. It also raises `TypeError` when handed `inputs.compound_profiles`
   directly, because that is a dict and it wants a list; `tyre_limited_laps`
   raises `TypeError` on a `CompoundProfile` because it wants a float.
2. The export's `derived.bottomingRefMm` and `derived.observedMinHeightMm` are
   **byte-identical** (310.35/306.52/330.9/325.92) though the first is documented
   as the *maximum* of the travel channel and the second as its *minimum*. One of
   the two is wrong and there is no way to tell which from the payload.

**One export contamination, not a defect.** The session payload presents 37 laps
under one sheet, but **laps 1–4 are session 90, which ran rh 68/77** — the sheet
before the raise. The green-tyre reference lap, 2:18.015, is lap 4 of that run,
so every degradation figure in the payload is measured against a car that no
longer exists, and run 1's 0.06173/lap wear is pooled into `byCompound.RS`.

### H — amendment, 29 Aug: the seventh wrong setup record, and my own error

**H6.** *"`de_f`/`de_r` are both 36, the lowest-damped values on the sheet at 20%
of the 30–60 range"* (Ludo, 28 Aug, from `setup_sheets` id 38) — **corrected by
the driver: the car reads 50.** Seventh consecutive session in which the record
and the car disagree. At 50 the rebound is **67% of range**, heavily damped, and
the inference built on it reverses: high rear rebound packs the platform down
over successive kerbs and holds the wheel off the road, which explains *"skips or
hops on kerbs"* better than the soft-rebound reading did. **The proposed test
inverts — `de_r` comes down, not up.**

**My error, and it is the shippable kind.** The reply contract states that an
omitted key means *leave it alone* and a repeated key means *I have checked this
and it stays*. I repeated `de_r: 36` — an instruction to enter a value I had no
ground truth for, on a record already known to be unreliable. **Rule: for any of
the twenty-one settings the feed cannot verify, omit. Only `gears`, and now ride
height via the body-height instrument, may be re-asserted.**

**A new instrument, calibrated before use.** Per-wheel suspension extension rate
(the falling edge of `susp_mm`, above 60 km/h), reported as the **rear/front p99
ratio**. Calibrated on a known change — Shelby at Red Bull Ring, `de_r` 30 → 38,
sessions 93 → 94: **1.007 → 0.915, a step of 0.092**. Applied to Spa it is flat
across all four sessions (0.909 / 0.880 / 0.874 / 0.878) spanning two ride
heights and two days, where a 50 → 36 move should read ~0.16. **Damper expansion
did not change during any of the 37 laps on file**, so it cannot explain a
difference between sessions and does not disturb the differential finding. It
does step at the Fuji → Spa boundary (Fuji 1.017 / 1.034 / 1.034 → Spa ~0.885,
a step of 0.143), but that is confounded with the circuit change and is not
cleanly attributable to the sheet.

---

## I — Spa Round 5, session 102, Huracán GT3, v1.71, 31 Aug 2026

| # | The prior claim | What the data says now |
|---|---|---|
| I1 | *"`lsd_a` 18 is refuted"* — asserted 26 Aug from 75,652 exit frames at 89.03% lock, and again 28 Aug from 87.70%. Carried forward twice as though the axis were closed | **⛔ THE VERDICT IS REVERSED IN SIGN, AND THE ERROR IS MINE.** Both tests asked whether **raising** `lsd_a` would add lock, and both correctly answered no. **Lowering it has never been tested on this car.** A rear axle whose two wheels turn at exactly the same speed on **84.5% of 4,759 on-power cornering frames** (session 102; 83.3% and 84.4% in 95 and 97 on the same definition) is not evidence that the axis is settled — it is the argument for coming DOWN. `02` §10.5 #1 names lower `lsd_a` the dominant cause of power understeer and the single most-validated entry in that section, citing **Huracán/Laguna 18 → 14 — this car, this value**. The measurement supporting the change has been on file since 26 August and I read it as a closure three times |
| I2 | `lsd_i` 6 → 12 will act on the three regimes `lsd_a` does not reach — maintenance, lift and braking (Ludo, 28 Aug) | **ONE OF THREE, AND THE ONE IT HIT HAS A COST.** On one definition applied to all three sessions: power 84.4 → 84.5% (nothing), **maintenance 1.5 → 2.1% — the stated primary target, nothing**, lift **4.9 → 18.5%, a 3.8x move** (n = 464). The change reached only the lift regime, which is the regime he rotates in: he rotates on release, and a rear axle locked on release resists that. Plausibly *contributes to* the mid-corner push reported on 31 Aug rather than relieving it |
| I3 | The on-throttle mid-corner push is an aero-balance problem (never asserted, but `02` §10.4 lists front-grip fixes that would mask it) | **Excluded by the speed signature.** Steering degrees per lateral g, on-throttle minus off-throttle: **+12.18 / +13.81 at 100–140 km/h against +5.77 / +7.45 at 140–180** (sessions 95 / 97). The penalty grows as speed falls. Aero balance acts in the opposite direction, so this is mechanical. `02` §10.4's explicit trap — *check the throttle state first, and if it pushes on throttle this is the wrong table* — applies, and the right table is §10.5 |
| I4 | Front suspension travel grew on v3 (37.2 mm p1–p99 against 25–30 mm on v2) | **WITHDRAWN WITHIN THE SAME ANALYSIS — off-track contamination.** Session 102's two counted laps include a 1.7 s excursion and a 0.05 s spin, and the travel percentiles were taken without a surface filter. Tarmac-only the three sessions read **25.2 / 25.2 / 26.8 mm**. The front is not using more travel on v3. Filter surface before comparing suspension travel |
| I5 | A telemetry instrument can size or falsify a front rebound (`de_f`) change on this car | **⛔ REFUTED FOR A THIRD AND FOURTH INSTRUMENT, AND THE AXIS IS NOW CLOSED.** The 29 Aug entry already withdrew the rear/front extension ratio (circuit-confounded) and the front ext/comp index (0.080 same-setup noise against a 0.053 effect). Two more were built and calibrated against the one known damper change on file — Shelby RBR `de_r` 32 → 38, session 93 → 94, `de_f` 40 throughout, with 98/99/101 as same-setup repeats. **(a) Log-decrement damping ratio: moved the WRONG WAY on the known change** (rear 0.1191 → 0.1084) while the unchanged front rose (0.0909 → 0.1079); same-setup rear spread 0.031, about 3x the effect. **(b) p99 extension velocity, rear/front:** 1.1068 → 1.0348 / 0.9933 / **1.3994** / 0.9771, a same-setup spread of **0.42** against a ~0.10 effect. **(c) Kerb-settle range** moved on the FRONT (47.7 → 36.1–41.3 mm p90) for a REAR-only change — not axle-specific. **Four instruments, four failures. A `de_f` change is settled by the driver's report, which the charter makes primary evidence for a feel symptom anyway** — the standing guard remains Raidillon minimum body height ≥ 18 mm, which is a *counter-check that the change costs nothing*, not a measure of the change |

**What survives and is worth keeping.** The suspension-channel sign was re-derived
from this session rather than recalled: heavy braking moves front-left **+6.91 mm**
and rear-left **−6.34 mm**, so **larger `susp_mm` = more compressed**, confirming
the 17 Aug detector audit. And ballast and power restrictor were shown *not* to have
changed between 28 and 31 August — static front suspension at matched fuel reads
251.68 / 252.66 / 253.16 mm across sessions 95 / 97 / 102, and full-throttle
longitudinal acceleration is identical band for band. **The app has never written
`ballastKg`, `ballastPosition` or `powerRestrictor` although the schema carries all
three; the car has run 55 kg at −24 and a 93% restrictor unrecorded throughout.**

---

## J — Spa Round 5, session 104, Huracán GT3, v1.71, 31 Aug 2026 — the differential closes

| # | The prior claim | What the data says now |
|---|---|---|
| J1 | Lowering `lsd_a` is the lever for the on-throttle push, including in the fast corners (Ludo, 31 Aug, entry I1) | **HALF CONFIRMED, AND THE OTHER HALF IS A DEAD END.** `lsd_a` 18 → 14 moved rear lock by gear: 2nd −7.7, 3rd −9.4, **4th −22.6**, 5th −0.3, **6th 0.0**. Monotonic, and it does nothing above 4th. Locking torque is preload plus `lsd_a` × wheel torque, so a tall gear starves `lsd_a` of the torque it acts through. **Spa's fast corners are all 6th** (median gear 6 above 180 km/h in every session), and 6th reads **97.2–98.3% locked at every diff setting ever tried, `lsd_i` 6 included**. ⇒ **The high-speed push is not reachable from either differential axis. Stop proposing diff changes for Raidillon, Blanchimont and Pouhon.** `lsd_a` 14 is kept on the strength of 4th gear |
| J2 | `arb_f` 5 is stiffer than `arb_r` 4 on an understeering car, and a stiff front bar throws the opposite wheel over a one-wheel kerb strike | **REFUTED BY ITS OWN CONTROL, BEFORE IT WAS ISSUED.** Cross-axle transfer, one wheel on kerb and its pair on tarmac, above 80 km/h: **front (bar 5) 55–61%, rear (bar 4) 73–80%**, stable across five sessions. The softer axle transfers *more*, so either the premise is backwards or the measure is dominated by spring rate and motion ratio. Sixth instrument discarded on this car — the first one killed before it reached the driver |
| J3 | The mid-corner and high-speed push might be an aero-balance problem | **EXCLUDED, and measured for the first time rather than argued.** Compression against speed on straights, full throttle, `lat_g` < 0.15, fuel 60–95 L, 125 → 250 km/h: front **+9.90 / 10.60 / 10.50 / 10.69 / 11.10 mm**, rear **+7.73 / 8.94 / 9.36 / 9.25 / 9.32 mm** across sessions 95/97/102/103/104. Converting to load with `k = 4π²f²m` per corner gives **front ≈ 45% of added aero load against 43% static weight** — balanced, mildly front-biased. `df_f` 400 → 450 is not indicated. `[DERIVED]`, and it rests on GT7's natural-frequency convention |
| J4 | The setup changes of 31 Aug were moving the car's front-end grip | **⛔ NOTHING MOVED IT, AND THE CONTROL WAS AVAILABLE ALL ALONG.** Peak lateral g above 180 km/h, p99 per lap, session medians: **2.760 / 2.843 / 2.645 / 2.671 / 2.777** across five sessions and three setup changes. The grip ceiling is flat. What varied was how much steering was spent reaching it. **This is the blunt control that should be run before attributing any handling change to a slider, and running it first would have stopped three changes** |
| J5 | Two-lap samples are enough to read a setup change on this car | **NO, AND THE NUMBER SAYS SO.** High-speed steering per lateral g on one unchanged setup (session 95, `de_f` 36) ranges **14.93 to 20.36 across nine laps**; session 97 ranges 13.33 to 17.45 across eight. Sessions 102, 103 and 104 carried 3, 2 and 2 laps, one of them with 5.4 s off-track and a spin. **Three changes were issued in forty-five minutes off samples that cannot resolve them.** One change, three clean laps, and the rule exists for exactly this |

**The standing procedural change.** `lsd_a` acts through torque and `lsd_i` does not,
so **whole-lap lock share is the wrong summary and hides the answer** — session 104's
whole-lap figure fell 85.6% → 78.5%, which reads as a broad improvement and is in fact
one large move in 4th gear plus nothing above it. **Report differential lock by gear, and
ask which gear the problem corner is in before proposing any differential change.**
Recorded as `reference-gt7-differential-torque-model`.

---

## K — Spa Round 5 race, session 112, Huracán GT3, v1.71, 31 Aug 2026

| # | The prior claim | What the data says now |
|---|---|---|
| K1 | *"Refuel rate 1.0 L/s is declared and unmeasured; the plausible range 0.5–2.0 swings the stop from 158 s to 60 s"* (Ludo, 31 Aug race plan) | **MEASURED AND THE DECLARED VALUE WAS RIGHT: 1.0009 L/s**, lap 11, 19.149 → 82.842 L in 63.63 s off the frames. The stop cost **89.9 s** on the wall clock against a predicted ~93. **Dead time is 5.80 s, not the 7.5 assumed; pit loss ex-fuel is 26.3 s, not the 20.0 declared.** Both should now be written to the event page as `measured` |
| K2 | The lap row's fuel delta gives the fill taken at a stop | **NO — it is 12% light.** The out-lap reads 19.15 → 75.27 = 56.12 L while the tank actually took **63.69 L**; the out-lap's own ~7.6 L of burn nets into the same row. `fuel_added_l` is NULL and is the field that should carry it. The same lap reports **`fuel_used = 0.0` where fuel ROSE** — `CLAUDE.md` rules 3 and 9, twice in one race (lap 1's grid reset too) |
| K3 | Eight setup changes on 31 Aug were moving the car's front-end grip | **⛔ NONE OF THEM DID, AND THE CONTROL WAS AVAILABLE ALL DAY.** Peak lateral g above 180 km/h across nine sessions and eight changes: 2.760 / 2.843 / 2.645 / 2.671 / 2.777 / 2.692 / 2.835 / 2.751 / 2.802. Range 0.198, no trend. **The null control was computable from the first analysis and was not run until change six.** Every mechanism moved as designed — roll fell with the bar, tyre temps moved with camber, diff lock fell 22.6 points in 4th — and the ceiling never moved |
| K4 | *"Did 1.71 cost this car grip"* can be settled from the archive | **UNMEASURABLE — circuit is perfectly confounded with version on this car.** Watkins is all 1.70 (66 laps, p99 lat g 2.337); Fuji (37 laps, 2.279) and Spa (71 laps, 2.514) are all 1.71. No circuit spans the patch. **The FFB question can only be answered by looking at the wheel, and it is now eleven days open** |
| K5 | The Blanchimont crash was a single lap going wrong | **NO — it was the pattern of the whole race.** Four of the five off-track runs were at Blanchimont (6,155–6,259 m). Median minimum speed there was **241.2 km/h in the race against 255.3–258.4 in practice**, with the throttle lifted on **17 of 19 laps** where practice ran it flat at 100%. He was managing that corner from lap 2 |


---

## L - The team mate's sheet, Huracan GT3, Spa, v1.71, 1 Sep 2026

| # | The prior claim | What the data says now |
|---|---|---|
| L1 | *"Raise the ride height to stop the Raidillon bottoming"* (Ludo, 27 Aug: rh 68/77 -> 73/82) | **RIGHT ABOUT THE SYMPTOM, WRONG ABOUT THE LEVER, AND IT SHAPED EVERYTHING SINCE.** A reference car in the same race runs **55/62 - 0% and 7% of the slider range** - on springs of **3.90/4.10 against our 3.55/3.70**, with rear compression damping **34 (70% of range) against our 24 (20%)**. The answer to a platform sinking under load is spring rate; ride height was the symptom-level fix. **`nf_f` and `nf_r` were never changed once on this car in the entire programme.** Being soft is why we had to be high, and being high is what cost the sustained corners |
| L2 | *"`lsd_a` 18 -> 14"*, *"`lsd_i` 12 -> 6"*, *"`cam_f` 2.4 -> 2.0"* (Ludo, 31 Aug) | **ALL THREE MOVED AWAY FROM THE REFERENCE CAR.** His: `lsd_a` **22**, `lsd_i` **18**, `lsd_b` **48** against our 14 / 6 / 28; `cam_f` **2.4**, the value the day started on and that two changes left behind. The diff measurement (84.5% locked on power) was sound; the inference that less lock was wanted was never tested against a car that worked |
| L3 | *"`arb_f` 5 -> 4 is refuted - he felt it and turn-in measured worse"* and *"`toe_f` -0.05 is inconclusive, put it back"* (Ludo, 31 Aug) | **BOTH WERE THE RIGHT DIRECTION AND BOTH WERE REVERTED.** His `arb_f` is **3** with `arb_r` **5** - a rear-biased roll couple against our front-biased 5/4 - and his `toe_f` is **-0.08**. Softening the front bar alone on a soft, high car adds roll and nothing else; it pays only with the rear bar up and the springs stiffer. **One-change-at-a-time cannot find a platform and will actively reject a correct direction that only works as part of a set. The doctrine is right for refining a platform and wrong for choosing one** |
| L4 | Aero was excluded because front share (~45% of added load) matched the 43% weight split | **BALANCE WAS THE WRONG QUESTION - TOTAL WAS.** His downforce is **420/650 against our 400/640**, front at **70% of range against our 50%**, on a car sitting 13-15 mm lower. I measured ~6,000 N of added load 125->250 km/h with **no baseline to compare it against**; the reference car was that baseline all along |
| L5 | Fuel burn per lap is a single number for the race (`RaceInputs.fuel_per_lap_l`, a scalar median) | **BURN IS A FUNCTION OF LOAD, and the driver spotted it before the model did.** Fitted on the race, holding upshift rpm: **+0.00610 L burned per litre aboard, SE 0.00134, t +4.54, CI [+0.0035, +0.0087]** - **0.61 L/lap between a full tank and an empty one.** It is invisible without the rpm term (fit on load alone: t +0.19) because the one lap he did not short-shift sits at the lowest fuel load. Residual sd falls 0.289 -> 0.112 L when rpm is held. **A full-tank stint and a half-tank stint are not the same number, and the plan currently sizes both from one median** |


---

## M - The team mate's sheet, corrected by the driver, 1 Sep 2026

| # | The prior claim | What the driver says now |
|---|---|---|
| M1 | *"MUST ASK BEFORE COPYING: his ballast MASS (we have position −20, not kg)"* (Ludo, 31 Aug) | **NOT A VARIABLE - BALLAST MASS IS FIXED BY RACE REGULATION.** Driver, 1 Sep: *"it's part of the race regs, you know this."* **The record does not know it: `events.notes` is NULL, `events.pp_cap` is NULL, and no regulation field exists in the schema.** `brain/driver.md` carries "ABS Off is a Supercars regulation", so some regs are written down and these are not. Only ballast POSITION differs (his −20 against our −24) |
| M2 | *"Adopt the platform wholesale as a new baseline, then refine from it"* (Ludo, 31 Aug, entry L3) | **⛔ HALF WITHDRAWN. HIS CAR IS TURBOCHARGED AND OURS IS NOT.** Driver, 1 Sep: *"he is running a turbo on his, I'm not, so completely different restrictor and ECU mapping to meet BHP regs."* Same regulation BHP, **completely different torque curve.** The aero and suspension platform - ride height 55/62, `nf` 3.90/4.10, compression 30/34, downforce 420/650 - is about mass, speed and downforce and still transfers. **The differential (18/22/48) and the gearbox (6th 0.900, final 3.500) do NOT: both are matched to a turbo's torque delivery.** ⭐ It also explains the 23% longer top gear I flagged as unexplained - a turbo pulls it and an NA engine would bog |
| M3 | *"Almost every change I made on 31 Aug moved us away from his car"* - listing `lsd_a` 18→14 and `lsd_i` 12→6 as moves in the wrong direction (Ludo, entry L2) | **STANDS for camber and toe; WRONG for the LSD.** His `lsd_a` 22 and `lsd_i` 18 are a turbo car's numbers and are **not evidence about ours.** The diff measurements taken on our own car (84.5% locked on power, and `lsd_a` inert in 5th and 6th) are unaffected and remain the only evidence on that axis |

**The record defect behind all three: the league regulations have no home in the schema.**
Fixed ballast mass, the BHP cap, ABS, and now **aspiration** all bound what may legitimately
be compared between two cars, and `events` has a field for none of them. **Every cross-car
comparison this project makes is currently unguarded.** ⭐ Note the packet's flags bitfield
already carries a **turbo bit** and nothing reads it - aspiration is available from the feed.

---

## N - The KB's Daytona entry against the driver's standing refusals, 1 Sep 2026

**No run on file. This is the KB read against `brain/driver.md` before a wheel is turned**,
recorded because two of its prescriptions are refused and the reasons must survive the weekend.

| # | `05-track-reference.md` §1.15 says | The verdict here |
|---|---|---|
| N1 | *"Ride height must be raised enough that the car does not bottom on the banking at full speed"* | **REFUSED AS THE FIRST LEVER, AND THE KB REFUTES ITS OWN HEADLINE FOUR LINES LATER.** §521: *"Stiff enough springs to resist the banking compression... resolve this with springs stiff and compression damping moderate rather than the reverse."* That is the driver's instruction verbatim (1 Sep: *"increasing ride height should be a last option not a first"*) and entry L1's finding. `[DERIVED]`: 31 degrees at r ~300 m and 280 km/h gives **1.92 g sustained**; the extra 0.92 g costs **18.1 mm front / 16.6 mm rear** at 3.55/3.70 Hz, plus ~13.2/11.3 mm of aero scaled from J3's measured figures - **31.2 / 27.9 mm consumed, ~3x the largest aero-only excursion ever measured on this car.** At 3.90/4.10 Hz it is 26.0 / 22.7 mm. **5.2 mm at each end, bought with springs.** `nf_f`/`nf_r` have still never been changed once |
| N2 | *"Brake bias: one click forward"* | ⛔ **REFUSED OUTRIGHT.** `brain/driver.md`, standing and non-negotiable: front bias locks his fronts and creates understeer. On this car forward is `bb −`, and his own recorded trim is **+2**, one click rearward. Same failure as the Fuji `05` §1.12 doctrine already ruled out for this car |
| N3 | *"Asymmetric setup (if your league permits it) genuinely pays here: more right-side camber, less left"* | **INAPPLICABLE - GT7 HAS NO PER-SIDE SETTING.** `cam_f`/`cam_r` and `toe_f`/`toe_r` are per-AXLE in the range record and in the game. The line was pattern-matched from a sim that has it, the same failure class as tyre pressure and caster in `CLAUDE.md` §4.8 |
| N4 | *"LSD acceleration sensitivity: medium, 22-28"* | **LIVE AND REACHABLE HERE, UNLIKE SPA - BUT NOT TAKEN IN v1.** J1 measured `lsd_a` moving lock −7.7 in 2nd, −9.4 in 3rd, −22.6 in 4th and **0.0 in 6th**; Spa's problem corners were all 6th, which is why that axis died there. Daytona's traction-limited exits are **2nd/3rd**, so `lsd_a` acts. Our 14 was bought at Spa against a push the differential could not reach. Held at 14 in v1 only so the platform change stays readable |
| N5 | *"Right-side tyre life is the strategic constraint, not fuel"* | **CONTRADICTS OUR OWN ARCHIVE, AND THE ARCHIVE HAS NO BANKING.** Re-derived 1 Sep across 144 four-corner readings: worst corner is **rear-left 80, front-left 56, rear-right 7, front-right 1** - **136 of 144 on the left**. Every circuit on file is flat. Our own bracket makes **fuel** the binding limit (fuel stint 13.7-15.9 laps against a tyre stint of 18.4-27.8), but the tyre half is extrapolated from flat tracks and is the soft one. **Logged as open prediction P4: does Daytona flip the worst corner to the right side?** Either answer separates "left-side wear is this car and driver" from "left-side wear is the circuits we happened to run" |

**The measured gearing finding that goes with it.** Off 8 Spa race laps, `ratio x (km/h per
1000 rpm)` = 35.513 / 36.219 / 36.427 / 36.677 / 36.854 / **37.016** - it **drifts up with
speed and is not a constant K** on this car (tyre growth). Limiter median **8,323 rpm** over
893 frames, so **6th at 1.087 tops out at 283.4 km/h**. Highest speed ever recorded on this
car: **279.0 km/h at Fuji**, and there are **zero 6th-gear limiter frames at any circuit on
file**. Daytona is 72% full throttle with GT7's biggest tow. Issued **6th 1.087 -> 1.040**.
⚠️ **Void if Round 6 runs BoP** - which `events` still has no field for (M1's defect, unfixed).

---

## O - The held ride height, caught by the driver, 1 Sep 2026

| # | The prior claim | What the data says now |
|---|---|---|
| O1 | *"`rh` 68/77 held - springs are doing this job, not ride height"* (Ludo, 1 Sep, Daytona v1) | **⛔ THE DRIVER CAUGHT IT AND HE WAS RIGHT: I ARGUED 68/77 EXISTS ONLY BECAUSE THE SPRINGS ARE SOFT, THEN CARRIED IT FORWARD UNCHANGED.** His words: *"my team mate's car was lower than what I ran at Spa and you are suggesting running the same at Daytona."* **The A/B was in the archive and had never been used** - sheets 38/46/54 ran **73/82**, sheet 55 ran **68/77**, `dc` identical at 26/24 across both. Min `body_height_mm` above 150 km/h: **17.94 (n=47) against 16.45 (n=30)**. ⇒ **5 mm of ride-height setting bought 1.49 mm of minimum ground clearance.** The suspension channel moved the full 5 mm - it tracks the setting 1:1 - but the *floor* did not, because at peak compression the car is against its travel limit and the setting has almost no leverage there. **Lowering is ~3x cheaper than it looks.** Fifth session running in which the driver's reading beat the derived one |
| O2 | *"The banking is ~3x the largest excursion ever measured on this car"* (Ludo, 1 Sep, entry N1) | **TRUE ONLY AGAINST THE AERO-ONLY FIGURE, AND MISLEADING AS FRAMED.** Baselined on low-speed straights, 8 laps on 68/77: **max excursion used F 43.29 mm / R 33.00 mm, minimum body height 16.86 mm.** **Spa's Eau Rouge already loads this platform harder than Daytona's banking will** (43 mm measured against 31 mm derived). What Daytona changes is **duration, not peak** - Eau Rouge is one transient per lap, the banking is sustained for ~40% of it. Riding a bumpstop for a moment is not sitting on it at 280 km/h. The concern survives; the arithmetic that justified it did not |
| O3 | Springs and ride height are separable levers, one to be moved while the other is held | **NO - AND THIS IS THE SECOND TIME THE SAME LESSON HAS COST A REVISION** (L3, `reference-setup-platform-before-sliders`). Revised to **`rh` 62/70 WITH `nf` 3.90/4.10 and `dc` 28/30, as one decision.** `[DERIVED]` at the banking's 0.92 g: front −1.80 mm from the ride height, +3.11 from the spring and +2.26 from the reduced aero sink = **net +3.57 mm**; rear −2.10 / +3.10 / +2.09 = **net +3.09 mm**. ⇒ **62/70 on 3.90/4.10 sits HIGHER dynamically on the banking than 68/77 on 3.55/3.70 while being 6 mm lower statically.** First time this project has priced the two levers against each other in the same units. **55/62 is staged, not rejected**: the 0.30 clearance-per-mm ratio is a single 5 mm step, and the Bus Stop kerbs are the one thing lower hurts |
| O4 | *"Should we run turbo or NA, and if turbo medium or high?"* (driver, 1 Sep) | **NA THIS WEEKEND. The cap is BHP (536), so a turbo buys no peak power - only curve shape under the same ceiling.** It would buy fatter top-end pulling a taller 6th, which is Daytona's currency at 72% full throttle and is M2's already-recorded mechanism. **It costs every measured number on this car**: the gearing constants, the 8,323 rpm limiter, the 0.0907-0.1079 L per full-throttle-second the fuel plan rests on, and above all **`lsd_a` 14, which `07` §3.6.1 and `06` §4 say was chosen BECAUSE a restricted NA build delivers proportionally more torque in early corner exit.** The top-speed gain is **already available free** at 6th 1.087 -> 1.040. If taken anyway: **High, not Medium** (`06` §3.2 names this exact circuit family), **Anti-Lag mandatory**, and the issued 6th ratio is void because it is cut off NA data. ⚠️ **Two record gaps block a full answer**: `events.pp_cap` is NULL, and `06` §3.3's exploit - the PP sim under-rates peaky high-RPM turbos because its own driver model cannot use them - is free performance under a PP cap and worthless under a BHP one. And M2's quote *"he is running a turbo on his"* does not distinguish a turbo PART on a Huracán from a turbocharged CAR. **M1's defect again: the league regulations still have no home in the schema** |

---

## P - The turbo verdict, and the build that drifted underneath it, 1 Sep 2026

**Driver, 1 Sep:** *"no pp cap, bhp only. teammates turbo is a part I ran it at brands hatch,
leguna seca and wanted to run it at watkins glen but you advised against it."*

| # | The prior claim | What the record says now |
|---|---|---|
| P1 | *"NA this weekend, and it isn't close"* (Ludo, 1 Sep, entry O4) | **⛔ OVERSTATED, AND IT IS `refutation-carries-a-direction` FOR THE SECOND TIME.** What was refuted on 13 Aug was **medium turbo + restrictor 70 + ECU 99, at Watkins Glen** - and the document's own reason 1 is an argument against **the restrictor**, not the turbo (*"a restrictor cuts exactly the part of the curve you use here"*), reason 2 against the **combination** (*"fattened, then clipped back by a heavy restrictor"*), and its verdict table calls it *"wrong circuit for it. **This is a Laguna package**"*. **The turbo as such was never refuted, and High RPM was never tried at all** |
| P2 | The Watkins turbo decision was settled | **ITS OWN AUTHOR FLAGGED IT AS UNSETTLED AND ASKED A QUESTION THAT WAS NEVER ANSWERED.** Line 571: *"Whether the NA/ECU package felt more progressive than the turbo/restrictor package, in your own words. **This decision was made on reasoning, not measurement.**"* And line 249 **recommended the High-RPM A/B**: *"Worth one A/B if you have spare practice time… a legitimate test."* **Nineteen days open.** ⭐ I independently re-derived *"High, not Medium"* for Daytona on 1 Sep without knowing that document existed - two routes, 19 days apart, to the same untested hypothesis. That convergence should have been the tell |
| P3 | The turbo has been run, so the archive may hold an A/B | **NO - Brands Hatch and Laguna Seca have ZERO sessions in the database.** Every recorded lap on this car is NA. **The only evidence about the turbo on this car is in the driver's head**, and the 13 Aug question is the way to collect it at a cost of zero laps |
| P4 | The build has been stable NA since Watkins Rev A | **⛔ NO. IT DRIFTED TO THE OPPOSITE TRIM PHILOSOPHY AND NOTHING RECORDS IT - SIXTH CONSECUTIVE SESSION IN WHICH THE SETUP RECORD WAS WRONG ABOUT THE CAR.** Rev A prescribed **restrictor 99 / ECU 94** on the explicit logic *"use ECU as the coarse tool and the restrictor as the vernier… a 1% restrictor trim does not reintroduce the curve distortion that restrictor 70 was causing."* Every sheet from Fuji (24 Aug) onward carries **restrictor 93 / ECU 100** - the coarse cut is now the restrictor and the ECU does nothing. No sheet, no document and no `setup_changes` row records the switch, and **`setup_changes` logs only suspension and diff keys, so restrictor and ECU cannot appear in it at all.** Sheet 46's note: *"restrictor 93 recorded for the first time - they have been on the car unrecorded throughout"* |
| P5 | The Daytona gearing call and the current build are compatible | **THEY FIGHT EACH OTHER, AND I DID NOT SEE IT.** `06` §4.1: the restrictor guillotines the top end, the ECU scales the whole curve. **Daytona is 72% full throttle** - Rev A's Watkins argument (70%) but harder - so a **7% bite is being taken out of the top end on the one circuit where the top end sets the lap**, while entry N's gearing call lengthens 6th to 1.040 specifically to chase terminal speed on the banking. `06` §4.1 also has the restrictor **worse for fuel than the ECU at the same hp**, and **fuel is the binding constraint here** (13.7-15.9 lap stint against 20 laps). ⇒ **New R1a/R1b A/B: restrictor 93 / ECU 100 against an ECU-coarse trim walked to the same BHP in the garage, 3 laps each.** Six laps settles terminal speed AND fuel. ⚠️ Rev A's *"576 base, ECU 94 ≈ 541"* arithmetic is **v1.70 and void** - read the garage number |
| P6 | `lsd_a` 14 is a leftover from a build we no longer run | **IT IS COHERENT WITH THE CURRENT BUILD - BY ACCIDENT.** `07` §3.6.1 validated 14 on a **restrictor-70** build because a restrictor preserves low-end torque; we are back on a restrictor-dominant build. Nobody chose that, and D3.1 rule 1 (*"re-test LSD acceleration sensitivity after every restrictor change, and re-gear - treat them as one job"*) was not run when the trim moved 99 -> 93 |

**Ruling for Round 6:** race NA, on **scheduling** grounds and not physics - the platform change is the
bigger unknown, an induction change triggers D3.1's re-test-LSD-and-re-gear as one job (a session, not
three laps), and the top-speed gain is already bought at 6th 1.040. **The turbo A/B is Round 7 prep:
High RPM, Anti-Lag, its own gearing.** It is no longer being argued against.

**Record defect, third naming.** `events.pp_cap` is NULL and the driver has now confirmed **BHP cap
only, no PP cap** - which kills `06` §3.3's PP exploit as a reason to run a peaky turbo. That answers
entry O4's second blocker, and it is the fourth regulation fact (with fixed ballast mass, ABS and
aspiration) that binds this programme and **has no home in the schema** - M1's defect, still unfixed.

---

## Q - Round 6 regulation: 550 BHP / 1,275 kg minimum, 1 Sep 2026

**Driver, 1 Sep:** *"BHP is 550 for this race and min weight is 1275."* Against `07` §3.1's
stock spec for this car - **576 BHP, 1,230 kg** - and the build that raced Spa: 536 bhp,
1,285 kg, restrictor 93 / ECU 100, ballast 55 kg @ −24.

| # | The prior claim | What the regulation says now |
|---|---|---|
| Q1 | Ballast mass is fixed by regulation and only POSITION is a variable (M1, driver, 1 Sep) | **THE MASS IS SET BY THE WEIGHT MINIMUM, WHICH IS PER-ROUND.** 1,230 stock + **45 kg** = 1,275, down from 55 kg. To hold the same longitudinal moment: `55 x 24 / 45` = **position −29** `[ASSUMED]` linear moment scale - so the weight change stays a weight change and not a balance change too. **The lever is weaker**: 45 kg has less authority over balance than 55 |
| Q2 | The trim A/B (restrictor-dominant against ECU-dominant) is worth 4 laps (Ludo, 1 Sep, entry P5) | **WITHDRAWN - THE CAP MOVING HALVED THE STAKE.** 550/576 is a **4.5% cut** against the 6.9% that reached 536, and at 4.5% Rev A's own line governs: *"a 1% restrictor trim removes 1% of a top end you have plenty of."* **Go ECU-coarse from the start** (expect ~ECU 96 / restrictor 99, walked in the garage - Rev A's *"576 base, ECU 94 ≈ 541"* is v1.70 and void). R3's ten-lap stint measures the fuel; the A/B returns only if that comes back tight |
| Q3 | The BoP question blocks the gearbox change (Ludo, entry N) | **EFFECTIVELY ANSWERED BY THE REGULATION'S OWN FORM. A BHP cap plus a minimum weight is the OPEN-TUNING model** - under BoP the game sets power and weight rather than giving a target to build to. Round 3 Enduro's BoP locked the gearbox outright. Proceeding as open tuning, subject to one word of correction |
| Q4 | *"6th at 1.087 tops out at 283.4 km/h and the car has never been past 279"* - measure first, then cut (Ludo, entry N) | **THE PREDICTION HARDENED AND IT BROKE MY OWN PLAN.** Terminal speed scales as P^(1/3): +2.6% power ⇒ **Fuji's measured 279.0 becomes ≈281.4 km/h at 550 bhp**, against a 283.4 limiter - before Daytona's longer full-throttle run, before the 380/600 drag trim, before any tow. ⇒ **P1 is near-certain, and a car on the limiter gives a CENSORED reading**: "terminal ≥ 283.4" and nothing more, from which no gearbox can be cut. **Run 1a therefore carries 6th = 0.980 as an INSTRUMENT** (limiter 314.4 km/h, well clear); the race ratio is then `308.1 / (measured terminal + tow margin)`. ⚠️ If 0.980 will not enter, raise `top` first - it is a gear-SPACING slider - then re-set gears 1-5 before setting 6th |
| Q5 | Fuel bracket 6.3-7.3 L/lap, stint 13.7-15.9 laps (Ludo, entry N) | **REVISED UP: 6.5-7.5 L/lap, 130-150 L over 20 laps, stint 13.3-15.4 laps.** +2.6% power at 72% full throttle, less a little for −10 kg. **Fuel binds harder than it did an hour ago** |
| Q6 | The 10 kg changes the platform arithmetic | **NO - IT IS MASS-INDEPENDENT.** GT7 sets natural frequency in Hz, so spring rate tracks mass and static deflection `g/(2πf)²` carries no mass term. 3.90/4.10 still gives 16.33 / 14.78 mm. `[ASSUMED]` that GT7 recomputes k when ballast is added |

**Record defect, FIFTH naming, and now demonstrably per-round.** `events` has `pp_cap` (NULL)
and no field for a **BHP cap** or a **minimum weight** - and `setup_sheets.build_json` carries
`bhp` and `weightKg` as **achieved** values with no way to mark a **target**, so the app cannot
tell a regulation from a measurement. Five regulation facts now bind this programme - BHP cap,
minimum weight, ballast mass, ABS, aspiration - **and not one has a home in the schema.**

---

## R - Daytona run 1a, sessions 113/114, Huracán GT3, v1.71, 1 Sep 2026

**Ten laps, eight countable, median 106.747 s. Rank zero CLEARS COMPLETELY for the first time
in this programme** - the settings screen read off an OBS fullscreen projector matches every
issued value: 62/70, 3.90/4.10, 28/30, 46/44, cam 2.0/1.2, toe 0.00/0.12, diff 6/14/28,
downforce 380/600, ballast 45 @ −29, ECU 96 / restrictor 99, top 300. ⚠️ **But
`setup_sheet_id` is NULL on both sessions, so the DATABASE still knows nothing** - the record
cleared by screen and by telemetry, not by the app.

| # | The prior claim | What the data says now |
|---|---|---|
| R1 | **P1**: 6th at 1.087 hits the limiter on the banking in a tow | ✅ **CONFIRMED, AND IN CLEAN AIR.** The 0.980 instrument worked: **zero 6th-gear limiter frames in ten laps**, so the reading is uncensored - **terminal 285.8 km/h solo**, against 283.4 for the 1.087 he would have raced. Gearbox verified off the feed: 6th reads **37.856 km/h per 1000 rpm** ⇒ implied ratio 0.978. **K6 = 37.099**, limiter **8,287 rpm** |
| R2 | *"Gears are too long"* (driver, 1 Sep) | ✅ **RIGHT, AND IT IS ONLY 6TH.** Gears 1-5 land at **6,570-6,680 rpm** on a limiter upshift - evenly spaced, just past the 6,500 torque peak. **6th lands at 6,295 and tops out at 7,490 rpm on the banking - 797 below the limiter and 510 below the 8,000 rpm power peak.** ⇒ **race 6th = 1.030**: terminal at ~8,000 rpm, 5→6 at 6,616, **10.5 km/h of limiter headroom for the tow.** Restrictor **99** (a 1% guillotine, not 7%) keeps the power peak at 8,000, which is what makes that ratio valid |
| R3 | **P3**: at 3.90/4.10 the car does not bottom on the banking | ✅ **CONFIRMED WITH LARGE MARGIN, AND I OVER-INSURED.** Front excursion **25.05 mm** against **26.0 predicted** (3.6% out - the derivation was sound); rear 23.61 against 22.7. **Minimum body height 27.22 mm against Spa's 16.86 - 10.4 mm MORE clearance than Spa.** Spa used 43.29 mm of front travel; Daytona uses 25.05. **The banking is far gentler on the platform than Eau Rouge** (entry O2 called this). ⇒ **stiffness can be given back, and 55/62 is live** |
| R4 | *"A little sketchy in the rear under brakes into the Bus Stop, running bb +2"* (driver, 1 Sep) | **NOT LOCK, NOT BRAKE BALANCE, AND `lsd_b` IS NOT THE LEVER - I WOULD HAVE PROPOSED THE WRONG FIX FROM THE REPORT ALONE.** Across **2,565 braking frames** in three zones the rear was **below 0.90 slip 0.0% of the time** and is the more planted axle everywhere (Bus Stop median: front 0.9746, rear 0.9885; for scale the Watkins race put the FRONTS under 0.90 on 20.2%). What did move is mine: **rear downforce 640 → 600 against front 400 → 380** - rear aero −6.25%, front −5.0%, **total −5.8% with the balance moved FORWARD** - at the one corner entered at 270 km/h. At the Bus Stop the **front dives 11.79 mm and the rear lifts 0.64 mm** |
| R5 | *"Isn't turning in the way I would like"* (driver, 1 Sep) | **⛔ I CANNOT MEASURE THIS AND SAID SO.** Steering per lateral g under trail braking reads 18.32°/g (n=8) with **no Daytona baseline - this session IS the baseline** - and J5 measured this class of metric ranging 14.93-20.36 across nine laps on one UNCHANGED setup. Eight laps cannot resolve it. **But GT7's own settings screen corroborates him independently: `Stability  Low Speed −0.46 (Under) · High Speed −0.45 (Under)`** |
| R6 | Fuel 6.5-7.5 L/lap, stint 13.3-15.4 laps (entry Q5) | **MEASURED AT THE TOP OF THE BRACKET: 7.37-7.65, median ~7.45 L/lap.** 20 laps = **149 L**; stint from full = **13.4 laps**. **Fuel still binds.** Full-throttle share **72.8%** against the KB's ~72% doctrine - that one lands exactly |

⭐ **A free instrument nobody in this programme has used.** GT7's own settings screen carries a
**Stability** readout (Low Speed / High Speed, signed, `Under`/`Over`) and **Rotational G** at
60/120/240 km/h. It responds to the build and costs **zero laps**. ⚠️ It is `[DERIVED by GT7]`
from the same simulated driver model `06` §3.3 shows is bad enough to under-rate high-RPM
turbos because it cannot drive them - so **directional only, confirm on track.** Proposed as a
ten-minute garage sweep: baseline against `cam_f` 2.4, `toe_f` −0.08 and `rh_f` 58, reading the
two numbers each time. **If it does not move for suspension, that is a useful answer too.**

**Power, settled:** 547 BHP = 575.5 x 0.96 x 0.99, confirming `07` §3.1's stock 576 independently.
With 1% steps on both tools every reachable product lands at 0.9504-0.9506 and the next rung
(ECU 96 x restrictor 100 = 0.96) gives 552.5 and is illegal - **547 is the ceiling under a 550
cap.** PP now **751.67**, weight **1,275 kg** exactly.

---

## S - The GT7 "Measure" readout is inert to suspension, 1 Sep 2026

| # | The prior claim | What the data says now |
|---|---|---|
| S1 | *"A free instrument nobody in this programme has used: GT7's settings screen carries `Stability` (Low/High Speed) and `Rotational G`. It responds to the build and costs zero laps"* (Ludo, 1 Sep, entry R) | **⛔ REFUTED IN TEN MINUTES BY THE CALIBRATION I ASKED FOR. IT IS INERT TO SUSPENSION.** Measurement history went from **one entry to five**; between them **`rh_f` 62→58, `cam_f` 2.0→2.4, `toe_f` 0.00→−0.08**. **Not one digit moved**: Stability **−0.46 / −0.45** both times, Rotational G **1.49 / 1.56 / 1.85**, 0-400 m **11.24**, 0-1,000 m **20.15**, 100-150 km/h **2.42**, PP **751.67**. Exactly consistent with `06` §1.1's *"suspension settings - zero weight in PP, confirmed"* - **and now known to hold for the whole measurement suite, not just the PP number** |
| S2 | *"GT7's own readout agrees with you about turn-in… an independent corroboration of 'isn't turning in the way I would like'"* (Ludo, 1 Sep, entry R) | **⛔ IT CORROBORATED NOTHING AND I SHOULD NOT HAVE SAID IT DID.** A reading that cannot respond to any suspension change cannot be evidence about a suspension setup. **−0.46 (Under) is a fixed property of the car**, true before and after every change we will ever make to it. The driver's report stands on its own, which is where it started |

**Seventh derived index discarded on this project, and the first one I proposed and killed inside
the same hour.** [[feedback_calibrate_instruments_before_use]] is why it cost ten minutes and zero
laps rather than a race: the calibration against a KNOWN change was built into the proposal. **The
failure was not proposing it - it was letting it corroborate a driver report in the same breath as
proposing it, before the calibration had run.** A new instrument may not be cited as evidence in
the message that introduces it.

**What survives.** The settings screen remains the best `rank zero` instrument this project has -
it read back all 23 values, the ECU/restrictor split, ballast and its position, and settled the
power arithmetic (547 = 575.5 x 0.96 x 0.99). **It is a record of what is in the car, not a
measurement of what the car does.**

---

## T - Daytona run 2, session 115, Huracán GT3, v1.71, 1 Sep 2026

**Six laps, five countable (lap 1 carried 6.4 s off-track and a 0.5 s spin).** Sheet: `rh` 58/70,
`cam_f` 2.4, `toe_f` −0.08, 6th 1.030; everything else as run 1a. ⚠️ `setup_sheet_id` **still NULL**.

| # | The prior claim | What the data says now |
|---|---|---|
| T1 | 6th = 1.030 should read **36.02 km/h per 1000 rpm** in the feed (Ludo, 1 Sep, entry R2) | ✅ **36.016 MEASURED.** The ratio is in the car, and the gearbox-from-telemetry method is now verified end to end: cut from a measured terminal, predicted to 0.01, confirmed on the next run |
| T2 | *"Expect >= 288 km/h; below 285 and the toe is costing more than the gearing gained"* (Ludo, 1 Sep, entry S) | **⛔ MY OWN FALSIFIER TRIPPED: 283.1 km/h, DOWN 2.7 from 285.8.** And the engine had **more** power available - rpm at terminal rose 7,490 -> 7,830, toward the 8,000 peak - so terminal fell *despite* the gearing gain. **The front-end changes cost at least 2.7 km/h of drag** (toe-out scrub, camber scrub, front ride height). On a **73.9% full-throttle** circuit with GT7's biggest tow, that is a real race cost |
| T3 | The three front-end changes improved the car (median lap 106.747 -> **104.719**, −2.03 s; best 105.661 -> **104.306**) | **THE GAIN IS REAL AND I CANNOT ATTRIBUTE IT.** Run 1a was his **first ever laps here**. Like-for-like end-of-run: ~105.8 (105.661, 105.977) against ~104.3 (104.359, 104.306) = **1.5 s** - and he was **still improving inside run 2** (106.0 -> 104.3 across five laps). ⭐ **But terminal speed is the LEARNING-FREE channel and it went DOWN**, so the lap gain is cornering or learning, **not** straight-line |
| T4 | Steering per lateral g can read the front-end change | **⛔ NO - IT IS INSIDE THE NOISE FLOOR AND I SAID SO RATHER THAN QUOTING IT.** 18.32 (n=8) -> 22.84 (n=5) °/g, which reads as *more* understeer; J5 measured this class of metric spanning **14.93-20.36 across nine laps on one UNCHANGED setup**. A 4.5 change on n=5 resolves nothing. **Only the driver can answer whether the front end improved** |
| T5 | *"5 mm of ride height bought 1.49 mm of minimum ground clearance - lowering is ~3x cheaper than it looks"* (Ludo, 1 Sep, entry O1) | **⛔ OVER-GENERALISED. THE 0.30 RATIO WAS A PROPERTY OF BEING ON THE BUMPSTOP, NOT OF THE CAR.** At Daytona `rh_f` 62 -> 58 cost **3.11 mm** of floor - a **0.78 ratio**. Spa used **43.29 mm** of front travel and was against its limit, so the setting had no leverage on the floor; Daytona uses **25.05 mm** and is well short, so ride height translates nearly 1:1. **Clearance still 24.11 mm - the room is real - but each further millimetre now costs a full millimetre** |
| T6 | Fuel 7.45 L/lap, stint 13.4 laps (entry R6) | **WORSE: 7.86-8.11, median 8.03 L/lap (+7.8%)** - shorter 6th means higher rpm on the banking, and [[reference_fuel_burn_vs_load]] has burn rising ~1.9 L per 1000 rpm. ⇒ **160.6 L over 20 laps and a 12.5-lap stint on a 20-lap race.** The trade is still strongly positive - 2.03 s/lap x 20 = 40.6 s gained against 11.6 L = 11.6 s of extra refuelling - but **fuel is now the dominant race constraint and no tyre-wear data exists at this circuit at all** |
| T7 | The Bus Stop rear may get worse from rake and front toe-out (Ludo prediction, entry S) | **NOT VISIBLE IN THE SLIP CHANNEL - 0.0% below 0.90 on BOTH axles across 237 braking frames**, front 0.9746 -> 0.9671, rear 0.9885 -> 0.9833, rear still the planted end. **Driver report outstanding.** If it feels worse it is confidence, not grip |

**Artefact, resolved and dismissed:** three "6th-gear limiter" frames sit at ~8,190 rpm and
**240 km/h**, which is **5th's** ratio - the gear field flips on the 5-6 upshift before the rpm
drops. No real limiter contact in 6th. It does confirm he is shifting 5-6 at the limiter as asked.

**Standing recommendation: stop tuning, run the ten-lap stint.** The remaining setup gain is ~1 km/h
(6th 1.030 -> 1.048 lands terminal exactly on 8,000 rpm at the same tow headroom) and is not worth a
run, while **wear at this circuit is completely unmeasured** and the strategy rests on rates
extrapolated from flat tracks.

---

## U - Daytona Road Course corner priority, Huracán GT3, v1.71, 1 Sep 2026

**First run of [[reference-track-priority-method]] on this circuit.** Braking zones from the data
(25 m bins, mean brake >8%, >=50 m, 13 laps pooled - zones are a TRACK property); apex from the
speed minimum; carry = apex to the next zone's braking point; leverage = `carry/(3.6 v^2)`;
opportunity = leverage x sd of his own minimum speed (run 2, n=5).

| zone | brake @ | apex | v-min | carry | leverage | sd | **opportunity** |
|---|---|---|---|---|---|---|---|
| **5 Bus Stop exit** | 3,650 | 3,875 | 149.0 | **1,325** | 0.2149 | **12.01** | **2.58** |
| **4 infield exit** | 2,050 | 2,125 | 90.5 | **1,525** | **0.6708** | 1.47 | **0.98** |
| 1 infield entry | 225 | 425 | 102.3 | 375 | 0.1289 | 2.90 | 0.37 |
| 3 hairpin | 1,575 | 1,750 | 88.5 | 300 | 0.1379 | 1.34 | 0.18 |
| 2 | 800 | 950 | 83.7 | 625 | 0.3208 | 0.54 | 0.17 |
| 6 banking | 5,200 | 5,200 | 271.8 | 754 | **0.0367** | 2.03 | 0.07 |

**Zone 4 is the highest-leverage exit on the lap by 3x - 0.67 s per km/h, feeding 1,525 m.
Zone 5 has the largest spread on the lap by 8x** (12.01 km/h against 2.90 for the next).
**The banking is LAST at 0.0367** - Daytona's Blanchimont, a risk corner and not a time corner.
Cornering time by speed band: **21.9% <120 · 26.0% 120-180 · 25.2% 180-240 · 26.9% >240** - but
the >240 band is the banking, which is flat out, so **the band that pays is 120-240 at 51.2%.**

| # | The prior claim | What the data says now |
|---|---|---|
| U1 | `05` §1.15: *"LSD acceleration sensitivity: medium, 22-28. The Bus Stop exit onto the banking is high-value and wants lock"* - and Ludo, 1 Sep entry N4, calling `lsd_a` *"a live axis here, reachable unlike Spa"* | **⛔ REFUTED ON OUR OWN CAR, MEASURED. THE DIFFERENTIAL HAS NOTHING TO BITE ON.** Rear wheel-speed SPLIT across **2,727 exit frames at zone 5 and 2,869 at zone 4: median 0.0000, p95 0.024-0.036.** The wheels are already tied. What IS happening is **both rears spinning together** - peak rear slip on exit **1.1697 (17%) at zones 3 and 4, 1.1200 (12%) at zone 5**, gears 2nd and 4th, TCS 0 on an MR car. **That is a mechanical-grip problem, not a lock problem: more `lsd_a` cannot close a split that is already zero** |
| U2 | *"`lsd_a` 14 is coherent with the current build by accident, because we are back on a restrictor-dominant build"* (Ludo, 1 Sep, entry P6) | **STALE - the build moved again.** `07` §3.6.1 validated 14 on **restrictor 70**; the car now runs **restrictor 99 / ECU 96**, an ECU-dominant trim, so that mechanism no longer applies either way. **The conclusion survives on U1's evidence instead, which is stronger** |
| U3 | The exits are traction-limited and the diff is the lever | **MECHANICAL REAR GRIP IS THE LEVER. Proposed: `dc_r` 30 -> 26.** Rear compression damping governs how readily the rear squats on throttle; stiffer resists the squat so load arrives on the driven axle more slowly. **I raised it 24 -> 30 for the banking and the banking measurement says I over-insured** - 23.61 mm of rear excursion against 24.11 mm of clearance. **Predicts** peak rear slip below ~1.14 at zones 3/4 and exit speed up at zone 4 (0.67 s per km/h). **Falsified by** rear slip unchanged, **or** minimum body height on the banking below ~20 mm - softer rear compression means the rear sinks more readily, and that is the cost |

**Where run 2's 2.03 s sat** (100 m bins, `d/v_post - d/v_pre`; reconstructs −1.254 of −2.028, so
it is the DISTRIBUTION and not the total - median-ing per-bin speed loses the correlation):
infield 1 **−0.312**, onto-banking **−0.267**, run-to-back-straight −0.142, infield entry −0.111,
banking −0.110, back straight −0.106, Bus Stop −0.095, **start-finish +0.007 (the only segment
that got SLOWER - the 2.7 km/h terminal loss)**. Broad, and sitting in the 150-250 km/h
acceleration zones - which is what "the car turns so I get on the power earlier" looks like
**and also what track learning looks like.**

**Not recommended: chasing the 2.7 km/h of terminal back.** Over the ~2,100 m of continuous full
throttle it is worth **0.25 s**, against 2 s/lap gained and a driver reporting the car
*"definitely better"*. ⚠️ **The caveat that survives: terminal speed in a TOW is overtaking
capability, not lap time, and the tow has never been measured.**

⛔ **Zone 5's 12.01 km/h spread was NOT converted into a driving instruction.** Spread is a state,
never a loss to be banked. Its honest use is the race rule's: **it is where the car should be most
forgiving** - which is a second argument for the rear-compression change.

---

## V - Daytona run 3, session 116, Huracán GT3, v1.71, 3 Sep 2026

Driver report: *"locking rears into the bus stop and not sure if gears need to be
lengthened."* Three clean laps (674/675/677) of seven; two incidents.

| # | Claim | Verdict |
|---|---|---|
| V1 | *"Locking rears into the bus stop"* (driver, 3 Sep) | **⛔ THE REAR HAS NEVER LOCKED. Rear slip below 0.90 is 0.00% across all 20 Daytona laps, in every brake band, at the Bus Stop and over the whole lap. The FRONT is locking and it is 7.5x worse than run 2 at MATCHED brake input** (70-90% band: 1.21% -> 2.08% -> **15.59%**; 90-100%: 22.54% -> 35.14% -> **57.79%**). The lap-6 off traces cleanly: front-left pins at **0.874** while the front-right holds 0.95-0.96 and **the rear never drops below 0.955**; he turns in, the car will not take it, he releases at 3,788 m, it bites at 2.5-3.2 lat g, **steering swings to −180° full opposite lock**, grass at 3,857 m. ⇒ **front lock -> understeer -> snap on release, not a rear lock.** ⚠️ **Instrument limit stated: `slip_*` sees locking and spinning, not SLIDING** - "the rear is not locking" is proven, "the rear is not sliding" is not. Countersteer >1.0 g at the Bus Stop *fell* (5.70% -> 0.57%) and peak yaw fell (0.743 -> 0.602), which argues against more slide, on n = 3 laps |
| V2 | *"`rh_f` -> 62 first, then toe"* - my own run-2 undo order (Ludo, 1 Sep, entry S) | **⛔ WRONG WAY ROUND, AND THE MEASUREMENT SAYS SO.** `rh_f` 62 -> 58 moves aero balance **forward**, which *adds* front grip under braking at 250 km/h. **Front toe-out −0.08 is what costs braking grip, and the asymmetric front-left lock is its signature.** ⇒ **toe first.** The run-2 risk I logged (*"the Bus Stop rear gets worse"*) fired on schedule - but the mechanism I named for it was wrong, and naming the wrong mechanism would have sent the fix to the wrong axle |
| V3 | *"Not sure if gears need to be lengthened"* (driver, 3 Sep) | **NOT YET - ZERO 6th-gear limiter frames in seven laps - BUT THE MARGIN HAS FALLEN FROM 10.5 km/h TO 5.9.** Gearbox verified unchanged off the feed: 6th reads **36.008** km/h per 1000 rpm against run 2's 36.016 ⇒ **1.030 confirmed**, gears 2-5 within 0.1%. 6th p99 **8,118 rpm**, max 8,137. ⭐ **Limiter re-measured from 4,023 `rev_limiter` frames across all three runs: median 8,284-8,287 rpm, consistent to 3 rpm - NOT the 8,323 carried in entry N.** ⇒ 6th tops out at **298.3 km/h** against a measured **292.4**. **6th 1.030 -> 1.010** puts terminal on the 8,000 rpm power peak and restores ~12 km/h of tow headroom (`K x ratio = 37.10`, measured twice) |
| V4 | *"Different wind conditions I think got the extra speed"* (driver, 3 Sep) | **✅ HE IS RIGHT, THE TEST WAS IN THE DATA, AND I LEFT IT AS AN OPEN QUESTION INSTEAD OF RUNNING IT.** Daytona's two high-speed straights face **347 deg and 144 deg** - near-opposite. Wind moves them in opposite directions; power or drag moves them together. Top speed, full throttle: **150-350 m: 285.8 / 283.1 / 293.2** (R2->R3 **+10.1**) against **3,400-3,650 m: 279.1 / 281.7 / 275.6** (R2->R3 **−6.1**). **Opposite signs.** Mean of the two straights: **282.5 / 282.4 / 284.4 - flat.** ⇒ **the car is unchanged and the +10.9 was wind.** ⚠️ The straights are 203 deg apart, not 180, so the averaging is approximate; the **sign reversal** is the finding and does not depend on it. **Sixth session running in which his read beat my derived one** |
| V5 | *"The front-end changes cost at least 2.7 km/h of drag"* (Ludo, 1 Sep, entry T2) | **⛔ REFUTED BY V4, AND I HAD BANKED A COST THAT DOES NOT EXIST.** T2 read the front straight alone (285.8 -> 283.1). On the **back straight, which faces the other way, R2 was FASTER by 2.6** (279.1 -> 281.7) - the same reversal. **Wind-corrected: R1a 282.5 against R2 282.4.** ⇒ **the toe / camber / front ride-height package cost NOTHING in drag.** Entry U6 re-checked T2 for a part-throttle artefact and cleared it; the actual defect was that **a single-straight terminal is not a drag measurement on a circuit with wind.** Checking the right thing wrongly still passes |
| V6 | The rear is stepping out because it is loose (implied by the driver report, and the natural reading of V1) | **NO - IT IS STORED STEERING CASHED IN AT THE BRAKE RELEASE, AND EVERY REAR-DIRECTED FIX MAKES IT WORSE.** Oversteer index (measured yaw / Ackermann-commanded yaw) through the lap-6 snap **tracks the brake pedal while the steering is being UNWOUND**: brake 39% -> index 0.99, 30% -> 1.13, 20% -> 1.20, 1% -> 1.71, 0% -> 2.14 -> 2.80 -> 6.92, with steering falling +28.8 -> +6.2 deg. Yaw rate holds 0.50-0.78 rad/s while commanded yaw collapses 0.515 -> 0.043. **The suspension agrees: through the release the REAR COMPRESSES (272.9 -> 282.1 mm) while the front extends (274.1 -> 268.2) - the rear is GAINING load.** A rear losing grip goes light; this one goes heavy. And the aggregate is flat: index >1.0 at the Bus Stop is **19.5% / 16.2% / 20.1%** across R1a/R2/R3 - **the rear has not changed, the front lock has (7.5x).** ⇒ **`lsd_b`, softer rear ARB and rearward bias all add rotation to a car already over-rotating at the release.** The lever is `toe_f` −0.08 -> 0.00, which is the same change that stops the front-left locking. ⚠️ **The index is a bare Ackermann model - no compliance, no aero - so its absolute values are meaningless** (the denominator collapses). **The SHAPE is the evidence** |
| V7 | 6th 1.030 -> 1.010 (revised from entry V3 after V4) | **THE HEADROOM FIGURE IN V3 WAS A TAILWIND NUMBER.** Wind-neutral terminal is **284 km/h**; tonight's tailwind alone reached **293.2 with no tow**, against a **298.4** ceiling at 1.030. Event weather is `changeable`. ⚠️ **No tow has ever been measured on this project - `race_knowledge.tow_s_per_lap` is NULL at every circuit** - so the tow is `[UNMEASURED]` and is not given a number here. ⇒ **1.010 (ceiling 304.4 km/h)** keeps him off the limiter in a tailwind AND a tow and no longer depends on which way the wind blew the night it was cut. **The gear did not get short - the wind made it look short one lap and long the next** |
| V8 | `data_health.py`: *"gearbox - every session ran the sheet it is tagged with"* | **⚠️ A VACUOUS PASS, NOT A CLEAN ONE.** `setup_sheet_id` is NULL on sessions 113/114/115/116, so there is no sheet to compare the gearbox against and the check has nothing to fail on. It reports the same words for "verified" and for "nothing to verify". **App defect: the gearbox check must distinguish AGREED from NOT COMPARED**, as `check_setup_sheets.py` already does for the sheet half |
| V9 | Entry T2's terminal comparison was taken off part-throttle frames | **NO - RE-CHECKED AND T2 STANDS.** Re-measured at throttle >=99.5%: R1a max **285.6** (against the 285.8 quoted) and R2 max **282.7** (against 283.1). The 0.2-0.4 km/h difference is immaterial and the −2.7 km/h finding survives. **Recorded because I went looking to overturn my own verdict and it held** |
| V10 | *"What can I do different in my driving to maximise speed through the bus stop"* (driver, 3 Sep) | **⛔ REFUSED, WITH THE NUMBER RE-DERIVED RATHER THAN QUOTED - n=16 clean laps across all three runs. 2sd: brake point 32.6 m · v-min 14.7 km/h · exit speed 22.7 km/h · corner time 0.44 s.** Any instruction I could give is **a third of his own lap-to-lap variation.** ⭐ **And it is worse than the noise argument: v-min at the Bus Stop against lap time is r = −0.30 over 16 laps, which does not clear significance at this n** - so I cannot even assert that more speed through there buys lap time. **What is honestly sayable: the cap is the car. 11.7% of his 90-100% brake frames at the Bus Stop lock a front, at 89.4% median brake pressure - there is no technique that finds speed under a saturated instrument.** `toe_f` 0.00 is the change that unsaturates it |
| V11 | Run 4 sheet, read off the GT7 settings screen (rank zero, 3 Sep) | **`toe_f` −0.08 -> 0.00 CONFIRMED IN THE CAR**, and every other issued value present: `rh` 58/70 · `nf` 3.90/4.10 · `arb` 5/4 · `de` 46/44 · `cam` 2.4/1.2 · `toe_r` 0.12 · diff 6/14/28 · `df` 380/600 · ECU 96 · restrictor 99 · ballast 45 @ −29 · top 300 · RS/RS · **548 BHP** (my arithmetic said 547 - **the garage number is authoritative**), 1,275 kg, PP 751.67 |
| V12 | *"`dc` reads 28/26 against the 28/30 on record - four clicks below what was issued"* (Ludo, 3 Sep, first version of V11) | **⛔ WRONG, AND HE CAUGHT IT: `dc_r` 26 IS WHAT I PROPOSED. Entry U3, 1 Sep: *"Proposed: `dc_r` 30 -> 26."*** I checked the Daytona memory file's *"RUN 2 sheet as built"* line (`dc 28/30`) and **never opened the reconciliation entry that superseded it**. ⭐ **This is precisely the failure the record exists to prevent - one number written in two places, and the second reader takes whichever he opens first.** **Seventh session running his recall beat my derived reading.** ⇒ **the settings screen agrees with the record; there was no discrepancy** |
| V13 | *"You told me to soften the rear compression to help braking into the bus stop as weight was transferring onto the front"* (driver, 3 Sep) | **THE CHANGE IS RIGHT AND STAYS. THE REASON DOES NOT HOLD, AND IF I GAVE HIM THAT REASON I GOT IT WRONG.** The record's stated mechanism for `dc_r` 30 -> 26 is **exit traction** - *"how readily the rear squats on throttle"*, *"exit speed up at zone 4"* - not braking. **And measured tonight at the Bus Stop, the rear is EXTENDING under braking, not compressing**: entry braking F−R **+1.10 mm**, release F−R **−6.93**. **Compression damping has no authority over an axle in extension - that phase belongs to `de_r` (44).** ⚠️ **One route in his favour**: `02` names rear compression for *"rear chatters/skates under combined braking+cornering - this specific oscillation mode is documented in GT7"*. But that is a chatter symptom, and what is measured here is a **front lock followed by a release snap** (V1, V6). **Different symptom, different axle** |
| V14 | Run 4 carries TWO changes (`toe_f` 0.00 AND `dc_r` 26) and is therefore uninterpretable | **NO - THEY ARE SEPARABLE HERE, BECAUSE THEY HAVE DISTINCT NON-OVERLAPPING INSTRUMENTS, AND THAT IS WHAT THE ONE-CHANGE RULE IS ACTUALLY PROTECTING.** `toe_f` reads out as **front slip in the 70-90% brake band** (15.59% in R3); `dc_r` reads out as **rear slip on exit at zones 3/4** (frames >1.05: 18.72% -> 26.13% -> **34.37%** across R1a/R2/R3 - getting worse, and it is what spun him on lap 4 at 2,277 m). **Neither change can move the other's channel.** ⚠️ **But the LAP TIME is confounded and must not be used to judge either.** Judge on channels. ⚠️ **And it is not established that `dc_r` 26 was absent from run 3**: rear squat velocity on throttle-up at zone 4 went **+14.22 -> +10.28 -> +8.53 mm/s** (softer compression should be FASTER, so this argues 30 was still in), but n=98 on R3 and the metric is confounded by how fast he applies throttle. **Ask, do not assume** |

**Two incidents, and they are different problems at different corners.** Lap 6 is the
Bus Stop (3,863 m), front lock, above. **Lap 4 is zone 4 exit (2,277 m) and it is rear
WHEELSPIN, slip 4.4-6.2, not lock at all** - the traction-limited exit the corner-priority
table already names as the second-highest-value zone on the lap.

**Still unmeasured at Daytona after 27 laps: tyre wear.** `wear_*` is NULL on every one of
them, so open prediction **P4** (does the banking flip the worst-wearing corner to the
right side?) remains open, and the tyre half of the binding-constraint `min()` is still
extrapolated from flat circuits. Fuel measured **7.849 L/lap** (n=3) ⇒ 157 L over 20 laps,
**12.7-lap stint. Fuel still binds.**

---

## W - Daytona run 4, session 117, Huracán GT3, v1.71, 3 Sep 2026

`toe_f` −0.08 -> **0.00**, and the driver also moved **`bb` +2 -> 0**. Five laps,
four countable. Driver report: *"I think that's ok now."*

| # | The prediction | What happened |
|---|---|---|
| W1 | **Front slip <0.90 in the 70-90% brake band falls from 15.59% to under 3%. Falsified by staying above 10%** (Ludo, 3 Sep, entry V) | **⛔ NEITHER - IT LANDED AT 9.67%, IN THE DEAD BAND BETWEEN MY OWN PREDICTION AND MY OWN FALSIFIER, 0.33 POINTS SHORT OF BEING FALSIFIED. That is a defect in the test I wrote**, not an ambiguous car: a prediction and its falsifier must partition the outcome space, and these left a 7-point gap. **Score it as NOT MET.** Direction is right (15.59 -> 9.67, roughly halved) and it is confounded - see W3 |
| W2 | **The release snap: falsified if the oversteer index still climbs past 2.0 with the brake off** (Ludo, 3 Sep, entry V6) | **✅ CONFIRMED, AND IT IS THE BEST OF THE THREE RUNS.** Frames above index 2.0 at the Bus Stop release: **6.8% (R2) · 10.3% (R3) · 1.1% (R4)**; p90 **2.05 -> 1.16**. **At the Bus Stop itself front lock below 0.90 went 6.94% -> 0.00%**, and ⭐ **the front left/right split - the toe-out signature - fell from p95 0.0669 to 0.0241, below even R2's 0.0328.** The asymmetric front lock is gone. **Zero spins in the session** against 1.58 s across two laps in R3 |
| W3 | The run is a clean read of the toe change | **NO - TWO CHANGES, AND THE SECOND ONE OPPOSES THE FIRST, WHICH MEANS THE TOE EFFECT IS UNDERSTATED HERE AND NOT OVERSTATED.** On this car **`bb +1` is rearward, so +2 -> 0 is two clicks FORWARD** - more front braking torque, which pushes front lock **up** while `toe_f` 0.00 pushes it **down**. Front lock halved anyway. ⚠️ **Where the forward bias shows: at maximum pedal (90-100%) front lock is 44.47% - better than R3's 57.79% but WORSE than R2's 35.14% - and the 40-70% band is 2.31% against R2's 0.00%.** **GT7 broadcasts no brake balance, so this is recorded and cannot be verified.** His own in-car trim is his to make |
| W4 | Lap time judges the change | **REFUSED, AND I SAID SO BEFORE THE RUN.** R4 median **105.197** against R2's 104.719 - but R2 was 1 Sep in different wind (terminal 282.7 against R4's 291.5, R3's 293.2). **The fair comparison is R3 -> R4 on the same night: 105.528 -> 105.197, −0.33 s, well inside his ~0.9 s lap-to-lap spread.** Two changes plus wind plus learning: the channels are readable, the clock is not |
| W5 | The gearbox is unchanged and the 1.010 call stands | **✅ VERIFIED. K6 = 36.004** against R3's 36.008 and R2's 36.016 ⇒ **6th = 1.030 still in the car.** Terminal **291.5 km/h @ 8,098 rpm**, **zero 6th-gear limiter frames**, 187 rpm short of the measured 8,285 limiter. **Entry V7's 1.010 is unaffected by anything in this run** |
| W6 | *"`dc_r` is 26"* (driver, 3 Sep) - and **WHEN it went in, which the answer alone does not settle** | **⭐ IT WENT INTO RUN 4, NOT RUN 3, AND THE TELEMETRY DISCRIMINATES IT CLEANLY.** Rear squat velocity on throttle-up at zone 4 - softer compression must squat FASTER: **R1a +14.06 · R2 +10.28 · R3 +8.53 · R4 +16.97 mm/s.** R4 squats **99% faster than R3** and faster than either known-30 run. ⇒ **R3 ran 30.** ⚠️ **So run 4 carried THREE changes, not two.** They are still readable because they do not share instruments: `toe_f` and `bb` both land on **front slip in the brake bands** (confounded with each other, W3), `dc_r` lands on **rear squat and rear exit slip** (clean) |
| W7 | **U3**: `dc_r` 30 -> 26 puts peak rear slip below ~1.14 at zones 3/4 and raises zone-4 exit speed. *Falsified by* rear slip unchanged, **or** banking body height below ~20 mm (Ludo, 1 Sep, entry U3) | **THE MECHANISM IS CONFIRMED AND THE OUTCOME IS NOT. The lever moved and the result did not follow.** The damper is demonstrably doing what it was changed to do (squat rate +99%, W6) and **the cost falsifier did not trip - banking clearance 25.91 mm against a 20 mm floor.** But the benefit is ambiguous: against R3, zone-4 frames above 1.05 slip fall **34.37% -> 24.71%**; against **R2, the other dc_r-30 run, they are 26.13% -> 24.71% - essentially unchanged**, and zone 3 goes 16.61% -> 17.40%. Zone-4 exit speed 181.9 -> 182.7 km/h, **inside the 1.47 km/h spread that corner already has.** Peak rear slip at zone 4 is **1.1576, still above the predicted 1.14**; zone 3 at 1.1334 is below it. ⇒ **NOT RESOLVED on 4 laps.** ⭐ **And it points somewhere: if the rear now squats twice as fast and spins as much, squat rate was not the limiter** - consistent with entry U1, where the rear wheels were already tied and both spin together. **Softer compression did not buy mechanical grip.** Comparing to R3 alone would have flattered it; R3 was the worst rear-slip run on file and had two spins |

---

## X - Daytona 10-lap race stint, session 118, Huracán GT3, v1.71, 3 Sep 2026

The first tyre-wear measurement ever taken at this circuit. `[DRIVER REPORT]`
*"right rear burnt up to 50% in 10 laps"*; *"I think I need more aero to help keep the
car planted and pointed at the bus stop and T1 and look after rears"*; and
*"or reduce front camber might work instead of aero changes possibly."*

| # | The claim | What the data says |
|---|---|---|
| X1 | **P4**: the worst-wearing corner flips to the right side at Daytona. *Falsified by* rear-left still worst (Ludo, 1 Sep) | **✅ CONFIRMED.** `[DRIVER REPORT]` right rear **50% in 10 laps**, against an archive whose worst corner was **rear-left in 80 of 144 four-corner readings, 136 of 144 on the left.** **Corroborated over 44,862 frames: RR is the hottest corner in EVERY window on the lap** (75.2-75.8 degC median vs RL 72.0-73.6, FR 65.5, FL 62.1), and **the rear-to-front gap grows monotonically across the stint, +2.90 -> +12.65 degC.** ⚠️ `laps.wear_*` is NULL on all ten laps - the gauge read is the only wear evidence and **it is not in the database** |
| X2 | *"Daytona's banking is a left turn, so it loads the right"* (Ludo, 1 Sep, entry N/P4) | **⛔ WRONG, AND MEASURED WRONG. THE BANKING LOADS BOTH REARS EQUALLY.** Per-wheel suspension across 7 clean laps: **banking peak RR−RL = +0.15 mm, lat g +0.05.** ⭐ **Because it is BANKED - the 1.92 g is normal to the surface, so it is vertical, not lateral.** The right rear is the outside wheel at **T1 (RR−RL +12.09) and T4 (+12.99) only - 5.5% of the lap** - and those two carry its **highest slip on the lap** (\|slip−1\| p95 0.0749 and 0.0728). **Loaded AND sliding: that is where it burns.** On the banking it slides less than anywhere except the Bus Stop |
| X3 | *"More aero to keep the car planted and pointed at the bus stop and T1, and look after rears"* (driver, 3 Sep) | **⛔ IT CANNOT REACH EITHER CORNER HE NAMED, AND IT ADDS LOAD WHERE THE TYRE IS NOT WEARING.** Downforce as a fraction of its banking value (v²): **T1 3.5% at v-min, 15.2% at v-median; Bus Stop 24.9% / 33.9%; T4 9.1%.** ⭐ **At T1's minimum there is 3.5% of the wing available.** And more REAR wing loads the **banking**, where 96-100% of downforce lives, where the rears are already the most compressed on the lap (RR 287.01) - **and at the lowest slip on the lap.** It adds nothing at T1/T4. ⭐ **The one honest argument for it:** terminal is **294.8 km/h @ 8,181 rpm** against the measured **8,285** limiter - **104 rpm of headroom** - and drag would buy that back. **But 6th -> 1.010 buys it for free**, without paying on every straight and in fuel at 73.9% full throttle |
| X4 | *"Or reduce front camber might work instead"* (driver, 3 Sep) | **⛔ I CANNOT MEASURE CAMBER AND SAY SO - GT7 gives ONE surface temperature per wheel, not the inner/outer split that would show camber working.** What is measurable runs against it: **the fronts are the COLD, underworked axle** - FL 62.1 / FR 65.5 against RL 73.3 / RR 75.8, **a 10-12.6 degC gap that WIDENS across the stint.** Reducing front camber takes grip off the axle that is already doing less and moves work onto the one that is overheating, **and it fights his own "pointed" ask** - `cam_f` 2.0 -> 2.4 was made on 1 Sep for turn-in. ⚠️ **No window exists for GT7 tyre temperature, so "cold" here means only cold RELATIVE TO THE REAR ON THE SAME LAP** - a within-car comparison, not a verdict against a target. ⇒ **the camber the data points at is the REAR (1.2 deg, half the front), not the front** - and that too is unmeasurable |
| X5 | **P2**: fuel binds over 20 laps, not tyres. *Falsified by* a gauge rate above ~0.046/lap (Ludo, 1 Sep) | **THE CLAIM SURVIVES AND ITS FALSIFIER WAS WRITTEN AGAINST THE WRONG QUANTITY. Measured 0.050/lap, so the stated threshold trips** - but re-deriving both sides: **tyre stint `0.85/0.050` = 17.0 laps against fuel stint `100/7.690` = 13.0 laps. FUEL STILL BINDS, BY FOUR LAPS.** The 0.046 was `0.85/18.4`, the bottom of my own **tyre-stint bracket**, so it tested whether the bracket held and **not whether tyres bind.** Correct threshold: `w > 0.85/13.0 = 0.0654`. ⭐ **Second badly-written falsifier in two sessions** (entry W1 left a dead band between prediction and falsifier). **A falsifier must be computed from the same expression as the claim it tests** |
| X6 | The 10-lap stint shows degradation | **NO DEGRADATION DETECTED, AND THAT IS NOT "THE TYRES DID NOT DEGRADE."** Clean laps n=7: median **107.470 s**, sd **1.475**. First 3 clean **107.627** against last 3 **107.140** = **−0.487 s - he got FASTER** - against a 50% gauge read. Textbook: **lap time confirms degradation and can never warn of it** |
| X7 | This race needs a tyre answer | **⛔ IT DOES NOT, AND THAT IS THE ANSWER HE DID NOT ASK FOR.** Fuel **7.690 L/lap** (n=7) ⇒ **154 L over 20 laps: one stop, forced by FUEL at ~13 laps**, despite `mandatory_stops = 0`. At 0.050/lap the right rear reaches **~65% by lap 13 - short of the >90% cliff** - and the stop fuel forces **brings fresh tyres with it.** ⇒ **no setup change is bought by this wear finding for THIS race.** It matters for a longer one |
| X8 | *"I have had OBS on the whole time so why aren't you looking at tyre wear"* (driver, 3 Sep) | **OBS WAS FINE AND THE APP SAID SO OUT LOUD AT 22:00:22, FOUR MINUTES INTO THE RACE. I read `laps.wear_*` as NULL and called it a gap without reading the log.** `logs/pitcrew.log` 21:58:33: *"hud-wear: **no OBS projector window is open** - right click the preview in OBS and choose Windowed Projector (Program), then size it to 1720x916"*, 60 failures, sampling stopped. ⭐ **ROOT CAUSE: `hud_source = screen` reads a windowed OBS PROJECTOR, not the OBS RECORDING** - two different things, and only the recording was on. **Two clicks.** Session 117 failed differently and the log names it: *"expected in VR - GT7 draws the HUD on the car's dashboard in 3D, so a fixed rectangle cannot hold it."* **Read the session log before calling a channel missing** |
| X9 | 16 "voice pack miss" lines mean the driver heard nothing all race | **⛔ NO - I ALMOST REPORTED THIS AND IT WOULD HAVE BEEN WRONG.** `engineer/voice.py` falls through to `self._fallback.speak(text)` on a miss and raises `NotSpoken` only when there is no live engine behind it. **Log confirms zero `NotSpoken` and zero playback failures ⇒ all 16 were synthesised live and spoken**, in the fallback voice rather than the rendered one. **The miss log is "the list of lines still to render" - a to-do list for the pack, not a failure.** Checked the code instead of reporting a log line at face value |
| X10 | **X5/X7**: fuel binds by four laps, this race has no tyre problem (Ludo, 3 Sep, one hour earlier) | **⛔ CORRECTED BY THE RECOVERED GAUGE. THEY BIND TOGETHER.** `read_hud_wear.py` recovered **66 readable samples over 9 of 10 laps** from the race capture. **His "50%" was an UNDER-read: RR reached 0.56.** Slopes over laps 2-9 (r 0.978-0.996): **FL 0.0275 · FR 0.0406 · RL 0.0388 · RR 0.0570** - two near-equal additive effects, **rear bias +0.0139/lap and right bias +0.0157/lap**, and the right rear takes both at **2.07x the front-left**. ⇒ **tyre stint 14.16 laps (linear) / 13.36 (through the origin) against a fuel stint of 13.00.** My 4-lap margin came from his coarse 0.050 estimate; measured is 14-27% higher. ⭐ **He arrives at the forced fuel stop with the right rear at ~0.80-0.85 - on the planning line with no margin. His instinct that the rears need looking after was better supported than my answer.** ⚠️ Calling this fuel-limited would be standing rule 12 exactly. **The aero verdict (X3) is unchanged** |
| X11 | `cam_f` is 2.4, per the 3 Sep settings screenshot (Ludo, entry V11) | **⛔ IT IS 2.0** (driver, 3 Sep) - moved after the screenshot. **Eighth session running the record was wrong about the car.** ⚠️ **Unknown whether 2.0 was in for the race stint, and camber has NO telemetry ground truth - unlike `dc_r` (entry W6) it cannot be discriminated. ASKED.** It also revises entry X4: I opposed lowering front camber partly because *"2.0 -> 2.4 was made on 1 Sep for turn-in"* - **he had already reverted it.** The measured half stands and is value-independent: the fronts are the cooler axle by 10-12.6 degC and the gap widens; **and the recovered gauge now puts a number on it - FL is the LEAST worn corner on the car at 0.0275/lap, 1.00x.** If that was measured at `cam_f` 2.0, then 2.0 is what produced the coolest, least-worn corner on the car, **which argues against going lower still** |

## Y - Daytona five-sheet A/B, sessions 120-124, Huracán GT3, v1.71, 4 Sep 2026

Equal-conditions mode; the driver, his adaptation and the sheet were the only variables. Runs and figures in
`brain/car-state/huracan-daytona.md` (the single place the values live). Read-only re-derivation, 4 Sep.

| # | The prior claim | What the data says now |
|---|---|---|
| Y1 | *"Two clean laps in five sessions"* (Ludo, 4 Sep, first version of the car-state note) | **⛔ WRONG, AND THE DRIVER CAUGHT IT.** The filter excluded any lap with 0.05 s of kerb time; the app's own `excluded` rule keeps them. **24 countable full laps, 20 incident-free, two PBs** (103.853 baseline, 103.486 at cam 1.0/1.0, against 104.338 before). Ninth time his read beat mine, and this one was arithmetic, not a missing input |
| Y2 | Camber is a grip/temperature lever only (`02` §10, every sheet) | **CAMBER IS A RIDE-HEIGHT LEVER: ~2.8 mm per degree, measured.** Banking suspension height front 274.6 / 277.2 / 283.1 mm at 1.0 / 2.0 / 4.0; rear 288.5 → 296.6 at 1.2 → 4.0; body height median 43.3 → 36.2, minimum 27 → 15.5 mm at 4.0/4.0. Same-camber other-day run (s119) reproduces the baseline to 0.5 mm. **Every camber change is a platform change**; the 55/62 stage must be costed with camber in force; the 3 Sep "2.4 → 2.0 braked better" report gains a mechanism (front +1.1 mm) |
| Y3 | *"Or reduce front camber might work instead of aero"* (driver, 3 Sep) and entry X4's reply that the fronts are the cold axle | **NOTHING ON THE FRONT MOVES BETWEEN 1.0 AND 4.0** - surface temperature 65.1–65.5 °C, L/R split and lock inside their floors. X4 stands: GT7's single temperature per wheel cannot show camber working. **What DID move with camber is the rear**: at 4.0/4.0 exit rear slip > 1.05 rose 8–10 points at T2, T3, T4 and T5 and the rears warmed +1.3 / +2.3 °C. One run, direction consistent in four zones, `[DERIVED]` |
| Y4 | *"More aero to help keep the car planted at the Bus Stop and T1 and look after the rears"* (driver, 3 Sep); X3 argued it could not reach those corners | **X3 IS NOW MEASURED, AND THE SLIDER IS WEAKER THAN EITHER OF US ASSUMED.** Rear 600 → 650 adds **0.65 mm** of rear compression at 270 km/h against ~10 mm for the whole aero load (J3): **3–6 % of aero for 25–50 clicks.** Wear 0.0556/lap RR in every run; back-straight terminal 275.0–275.5 in every run; rear temperature +1 °C. There is no wing setting in this range that changes what the rears do. GT7's Measure readout tracks total downforce (−0.45 / −0.42 / −0.36), refining entry S: it sees aero, not suspension or geometry |
| Y5 | Lap time can rank five sheets run back-to-back in equal conditions | **NO - LEARNING WAS THE LARGEST EFFECT.** Run bests 104.62 → 104.09 → 103.85 → 103.49 → 103.59, S2 sector 39.97 → 39.34 monotonic but for one run, fastest lap in the last third of every run: **~0.3 s per run on a car that changed by 3–6 % of aero or by camber.** Same size as any setup effect. Cam 4.0/4.0 is the one run that did not improve on its predecessor - consistent with Y3, not proof of it |
| Y6 | The morning's laps are what the archive holds | **SIX OF 24 CARRY A 100 % BRAKE AT EXACTLY 5,200 m ON THE BANKING** (267 → 110–190 km/h, then full throttle, no pit), costing that lap 1–2 s and the next lap's front stretch (254 vs 284 km/h). Also on s119 L10. **ANSWERED, driver 4 Sep: track-limits time penalties, served there.** Not setup. **App gap:** a penalty lap has a clean signature (full brake above 250 km/h at near-zero lateral g, no pit entry) and is flagged by nothing, so it enters every lap-time, sector, terminal and banking comparison as a real lap. And six penalties in 24 laps means the 0.2–0.5 s of kerb time on most laps is what earned them — `off_track_s` is not noise |
| Y7 | `laps.is_out_lap` marks the out-lap | **⛔ LAP 1 OF EVERY DAYTONA SESSION IS THE OUT-LAP AND IS FLAGGED 0** - pit limiter 79.5 km/h visible at 150–350 m, 91.6 s partial or 7–9 s of grass. A best-lap query on this event returns 93.100 s. **FIXED 4 Sep:** one rule (`runs.opening_lap_verdict` - declaration first, `standing_start_ms` corroborates, distance and lap time deliberately unused) on the live path, the rack and `tools/flag_out_laps.py`; backfill set 79 flags across the archive with a backup, 11 of them Daytona. Event 10 best countable lap is now 103.486 s |
| Y8 | Wear will separate the sheets over a stint | **IDENTICAL AT THE GAUGE'S RESOLUTION IN ALL FIVE** (RR 0.0556/lap, FL 0.035–0.037, FR/RL 0.037–0.042), replicating the race stint's 0.0570. Over 4–5 laps a difference would need to exceed ~12 % of the rate to show |

**What the day bought.** One new instrument fact (Y2) that changes how every future sheet is costed, one closed
question (Y4: wing cannot reach the rear-wear problem at any legal setting), one candidate rear-camber cost (Y3), and a
demonstration that the driver's improvement over a morning is larger than any of the five changes - which is Ludo audit
finding #1 in a single session's data.

## Z - The 6th-gear proposal and the cross-day terminal, Huracán GT3, Daytona, v1.71, 4 Sep 2026

Re-derived read-only from `laps` + `lap_frames`, sessions 118-124, 40 out-lap-free countable laps.
No new running. Both entries below correct *my own* earlier work.

| # | The prior claim | What the data says now |
|---|---|---|
| Z1 | **6th -> 1.010 "buys the terminal back for free"** (Ludo, 3 Sep, entry X3; carried in `brain/car-state/huracan-daytona.md` as *"1.010 proposed for the race"*) | **⛔ REFUTED, AND THE INFERENCE WAS BACKWARDS.** `rev_limiter` fires in **gears 1, 2, 3, 4 and 5 - 3,607 frames - and NEVER ONCE in 6th across 79,090 frames in sixth.** Max rpm in 6th is **8,181** (s118 L2, the fastest lap on file) against the measured **8,285** limiter; on 4 Sep it reaches only **7,830-7,914**. ⭐ **104 rpm of headroom means the gear is ALREADY LONG ENOUGH.** Lengthening it moves him *further* below the limiter and *lower* in the rev range at terminal - the opposite of the intent. The measured half of X3 (294.8 km/h @ 8,181) was right; the conclusion drawn from it was not. **Proposal withdrawn.** If any ratio question is open it is **3rd and 4th**, which take 2,384 of the 3,607 limiter frames |
| Z2 | *"Back-straight terminal 275.0-275.5 in every run"* ⇒ the wing costs no measurable drag (Ludo, 4 Sep, entries F4 / Y4) | **TRUE ON THE BACK STRAIGHT, AND THE BACK STRAIGHT IS THE STRAIGHT THAT CANNOT SEE IT.** Peak speed on the two opposed straights (back 3,300-3,800 m, heading 143 deg; front stretch 5,500-5,900 m, heading 343 deg), penalty laps excluded: 3 Sep at df 380/600 **273.8 / 288.3** (s118) and **274.0 / 288.9** (s119); 4 Sep at df 410-420 **275.1-275.6 / 281.3-282.4**. **The front stretch fell 6.5-7.5 km/h while the back straight rose 1.4** - opposite directions, which is the wind signature this circuit established on 3 Sep, not a drag signature. **Within 4 Sep, 50 rear clicks moves the front stretch ~1.1 km/h** (420/600 282.4 vs 420/650 281.3), so the wing cannot account for 6.5 at any setting in range. Same-day replication is tight (s118 vs s119 agree to 0.9 km/h on both straights; the five 4 Sep runs span 1.5). ⇒ **Y4 stands and narrows: no wing setting in range changes terminal. AND: Daytona terminal speed is not comparable across days at all** - any figure spanning 3->4 Sep is void, including a comparison of a race stint on 380/600 against practice on 410/635. GT7 broadcasts no wind; the HUD shows it and the app does not read it |
| Z3 | Fuel, re-derived for the 20-lap race | **7.708 L/lap at race pace** (s118, n=8, sd 0.297) and **7.789 across the five A/B runs** (n=24, sd 0.086). ⇒ tank stint **12.84-12.97 laps**; 20 laps needs **154-156 L**, so **~55 L to be added, ~55 s standing at 1.0 L/s.** Stop window is **laps 8-12** (stint 2 must fit the tank; stint 1 must too). Tyre at RR 0.0570/lap gives 14.9 laps, so a **10/10 split leaves the tyre at ~0.57 with the fuel binding** - X7 and X10 reconciled: **fuel binds, and the split is what removes the tyre problem, not the setup.** ⚠️ The **evidence** ceiling is 10 laps - the longest stint ever run here - so a 10-lap practice stint sits exactly on it |

| Z4 | *"So my experiment with aero proved successful?"* (driver, 4 Sep) — testing the 3 Sep hypothesis *"more aero to keep the car planted and pointed at the Bus Stop and T1 and look after the rears"* | **THE EXPERIMENT SUCCEEDED. THE HYPOTHESIS FAILED — AND IT WAS TESTED AT THE TWO CORNERS HE NAMED, WHICH NOTHING HAD DONE BEFORE.** Corner v-min was never measured across the wing sweep; F4/Y4 only checked load, wear, terminal and temperature. Median v-min per auto-segment zone, penalty laps excluded, against a same-setup floor built by splitting s118 and s119 every balanced way: **the clean single-variable pair is s120 (420/600) vs s121 (420/650) — same front wing, 50 clicks of rear.** Bus Stop zone (3,776–3,951 m) **152.9 → 150.4 km/h, i.e. DOWN 2.5 with more wing** (floor 1.57–5.08); T1 zone (395–497 m) 89.8 → 100.6 but that zone spans **82.3–100.9 across all seven runs with no ordering by downforce whatever** and carries the worst floor on the lap (3.23–5.56); T2 86.0 → 82.7 (down); T3 86.7 → 87.0; T4 83.2 → 83.8. Peak lateral g at the Bus Stop **3.22 / 2.81 / 3.22** at 600 / 650 / 635 — no ordering. ⇒ **more rear wing did not raise minimum speed or lateral g at either corner he named, and where the point estimate moved at the Bus Stop it moved the wrong way.** Consistent with the mechanism already measured (0.65 mm of 10 mm total aero load = 3–6 %) and with X3's geometry (downforce is 24.9–33.9 % of its banking value at the Bus Stop, 3.5 % at T1 v-min). ⚠️ n=3–5 laps per run: this **cannot prove the wing does nothing**, only that no effect is resolvable and the point estimates do not order by downforce. ⭐ **What the morning DID buy is not a tenth: a closed question that had stayed open across three revisions and two of my own recommendations, a new instrument fact (Y2, camber is a ride-height lever), and a refuted direction (Y3, cam 4.0/4.0).** ⛔ **And the two numbers that DID move with the wing are both static:** GT7's Measure high-speed stability (−0.45 → −0.36 "Neutral") and PP (751.67 → 757.88) are computed from the sheet, not driven — **420/650, the sheet that reads "Neutral", is the run with the LOWEST Bus Stop v-min of the morning.** A Measure readout is not evidence a car got faster |

## AA - Daytona 13-lap stint, session 125, Huracán GT3, v1.71, 4 Sep 2026 evening

The run called for that morning: baseline df 410/635, cam 2.0/1.2, bb 0, RS/RS, full tank, 13 laps
(8 clean: 2, 5, 6, 8, 9, 10, 11, 13). `[DRIVER REPORT]` *"still not happy with it, first corner rears are
stepping out and bus stop is still hit and miss."* Sheet confirmed `SCREEN` against the settings shot.

| # | The claim | What the data says |
|---|---|---|
| AA1 | **The three predictions filed that morning** | **✅ ALL THREE HELD.** Fuel **7.680 L/lap** median (n=11) against a predicted 7.6–7.9; **RR 0.0540/lap** (n=8, regression, 0.111→0.694 over laps 2–13) against 0.052–0.062; last three clean laps **−0.136 s** against the first three, against a predicted ±0.5. First time a Ludo prediction set has closed clean. The wear map **replicates 3 Sep independently** — RR 0.0540 / RL 0.0407 / FR 0.0407 / FL 0.0309 against 0.0570 / 0.0388 / 0.0406 / 0.0275 — right-rear worst at **1.75× the front-left**, second measurement, same rank order |
| AA2 | *"First corner rears are stepping out"* | **CORROBORATED IN PHASE AND PLACE, AND THE PHASE IS THE BRAKE, NOT THE THROTTLE.** In the first-corner complex (380–560 m) the rear reaches its lowest slip of the lap **under trail braking**, and lap 8 — the deepest brake release of the eight — carries **12 frames at rear slip 0.894**, the first sub-0.90 rear reading on file at this circuit (the 3 Sep archive had **0.00 %** below 0.90 across 20 laps). Exit rear spin is *inversely* related to the bad laps (3.2–6.3 % on the worst, 21.6 % on the best), so **every throttle-side explanation is refuted**: the event is on the brake |
| AA3 | What actually separates a good first corner from a bad one | **THE BRAKE RELEASE POINT, AND ALMOST NOTHING ELSE.** Across the 8 clean laps, minimum speed spans **62.1–98.4 km/h** and correlates with the release point at **r = −0.947** (released 420–434 m ⇒ 94–98 km/h; released 461–472 m ⇒ 62–68 km/h). The **brake ON point is uncorrelated, r = −0.051** (242–276 m). Peak approach speed spans **239–286 km/h**, r = −0.735 — acting through the release. Steering at v-min r = −0.767 and reaches **130°** on lap 8 at 1.41 g: that is the consequence, not the cause. **Front lock is severe there and constant** (front mean 0.867–0.946, worst 0.827, front-vs-rear gap **+0.054**) and **does not correlate with the outcome, r = −0.098** ⇒ the front always locks at this corner; it is not what varies |
| AA4 | The rear-lock reading can buy a setup change on its own | **⛔ NO — THE INSTRUMENT DISAGREES WITH ITSELF.** Same-setup floor for first-corner rear-slip minimum under trail braking, built by splitting two unchanged sessions every balanced way: **s118 gives 0.0293 (p90 0.0434), s119 gives 0.0062 (p90 0.0151)** — a 5× disagreement. Taking the wider, as the spin-grip retraction requires: the between-session spread (race stint 0.937, morning base 0.955, tonight 0.948 = 0.018) is **inside the floor**. ⇒ I may not claim the rear locks more than it used to. **The change is bought by AA2's driver report, corroborated in phase — not by a telemetry-only flag** |
| AA5 | *"Bus stop is still hit and miss"* | **I CANNOT SEE IT, AND I SAY SO.** Bus Stop v-min spans **145.8–158.3 km/h, sd 4.91** over 8 laps against a same-setup floor of **1.57 (s118) to 5.08 (s119)** — the scatter sits **inside the wider estimate**, so it cannot be separated from what an unchanged car produces anyway. What the zone does say is that it is a **different problem from the first corner**: the front-vs-rear lock gap there is **+0.018–0.031** against **+0.054** at the first corner, and front lock correlates *positively* with v-min (r = +0.645, n=8) ⇒ **if the Bus Stop is a car problem it is a FRONT problem.** Do not fix both at once |
| AA6 | `laps.wear_*` for lap 8 | **⛔ APP DEFECT, RULE 3.** All four corners written as **0.0** between RR 0.361 (lap 7) and 0.472 (lap 9). A gauge frame that failed to read is being stored as zero, not NULL, and a zero that means "not measured" is exactly what gets diagnosed as a real value. It also silently drops out of any regression that filters `> 0` — which is why the AA1 wear slope had to |

## AB - Daytona, session 126, `lsd_b` 28 -> 40, Huracán GT3, v1.71, 4 Sep 2026 21:34

9 laps. `[DRIVER REPORT]` *"first corner felt better, maybe could bring it back to 35 or something to get a
little more rotation on other corners under brakes"* and *"Bus stop is still very tricky."*
`lsd_b` 40 source `driver` (no settings shot this run). Wear not captured this session.

| # | The claim | What the data says |
|---|---|---|
| AB1 | **§AA's prediction: the sub-0.90 rear frames stop appearing, AND the release-point slope flattens from −0.947** | **HALF HELD, AND THE HALF THAT FAILED IS THE INTERESTING ONE.** ✅ Sub-0.90 rear frames at the first corner: **12 → 0** across 8 zone-clean laps each side, and the driver's report agrees. ⛔ **The slope did NOT flatten**: ~0.67 km/h per metre of release at `lsd_b` 28 against ~0.69 at 40 (r −0.934 → −0.885; release spread 418–472 m → 416–453 m). ⇒ **the release point is arrival, not car** — §AA3's reading is strengthened, and a diff change was never going to move it. **State a falsifier on the quantity the change acts on, not on a correlate of it** |
| AB2 | *"Bring it back to 35 for more rotation on other corners under brakes"* (driver, 4 Sep) | **✅ CORROBORATED, AND ON A CALIBRATED INSTRUMENT.** Rotation-under-brakes index (mean \|yaw rate\| per degree of steering, brake ≥20 %, lock >10°, zone-clean laps only), same-setup floors from splitting s118 and s119 every balanced way: **first corner 0.0121 → 0.0121 (floor 0.0033 / 0.0037) — no change; z3 0.0148 → 0.0125 (floor 0.0014 / 0.0002) — beats both; z4 0.0116 → 0.0103 (floor 0.0011) — beats it marginally.** ⭐ **The cost is real, it is located at the later braking zones, and the first corner's gain did NOT come from the rotation axis** — so 35 can be tried without necessarily giving the first corner back. **Approved, but sequenced second: one change per run** |
| AB3 | *"Bus stop is still very tricky"* — §AA5 said *"I cannot see it"* | **⛔ §AA5 IS SUPERSEDED. I WAS LOOKING AT THE WRONG QUANTITY. THE CAR LEAVES THE GROUND OVER THE KERB, EVERY LAP, IN EVERY SESSION ON FILE.** Through 3,790–3,840 m: **body height rises from ~40 mm to a peak of 72.9–77.5 mm and back inside ~15 m at 160 km/h**, all four wheels extend together (susp 294–300 mm compressed → 252–270 extended), and **lateral g collapses by 2.1–2.5 g to a minimum of 0.02–0.11 g** — median across s118, s119, s122, s125, s126, n=4–11 laps each, **40 laps, no exceptions.** 0.08–0.19 s with effectively no lateral grip. **Kerb contact through the Bus Stop on 100 % of laps** (54–110 non-tarmac frames, 0.9–1.8 s, spanning 3,800–4,020 m), and **3 of 19 evening laps ended on the grass there.** §AA5's scatter statistic (v-min sd 4.91 vs a 1.57–5.08 floor) was measuring the *outcome* of a coin-flip; this measures the coin. ⚠️ The launch magnitude does **not** separate the five sheets (30.5–38.9 mm against a floor of 4.42–6.48 median, 7.99–10.83 p90) — none of them changed damping |
| AB4 | The change that follows | **`dc` 28/26 → 20/20** — compression damping to the bottom of its **verified [20, 40]** range (v1.71, measured 24 Aug). One axis, both ends, and deliberately to the stop: the range is only 20 wide, so taking it there **settles whether compression damping is the lever in a single run** rather than titrating through three. Compression damping is what converts a kerb strike into body movement; at 1.92 g sustained on the banking damper velocity is ≈0, so the spring — not the damper — is what holds the platform there, and the 3.90/4.10 spring change made for the banking is untouched `[DERIVED]`. ⚠️ **`dc_r` 18 was proposed and is out of range** — the floor is 20. **Prediction:** body swing at 3,790–3,840 m falls **below 20 mm** (from 30.5) and the lat-g minimum rises above 0.5 g. **Falsified by:** swing still above 20 mm — the bar is set at the worst p90 floor (10.83 mm) below the current median, so anything smaller is not claimable; or the banking body minimum dropping below the 26.5–30 mm the sheet reads there |
| AB5 | Off-track rate | s126 had **5 of 8 laps with >1 s off-track against s125's 4 of 12**, and 2 of the 3 Bus Stop grass excursions are in it. **Not a verdict** — n is tiny, it is a second run late in the evening, and AB3 says the Bus Stop throws a coin on every lap regardless of sheet. Recorded so it can be re-read if it repeats |

## AC - Daytona practice race against AI, pre-flight, Huracán GT3, v1.71, 4 Sep 2026 ~22:10

Settings shot confirms `SCREEN`: **`dc` 20/20 AND `lsd_b` 35** — both changes made, so this run is a
two-change stack and neither is credited or refuted by it (§AB4 issued the damper alone, §AB2 sequenced
the diff behind it). Partial separation is still possible: **body swing over the Bus Stop kerb is readable**
(the diff cannot plausibly move body height over a kerb), **the rotation index is not** (compression damping
moves load transfer under braking too).

| # | The claim | What the data says |
|---|---|---|
| AC1 | The wear gauge will record this race | **⛔ IT WILL NOT UNLESS THE OBS PROJECTOR IS OPENED FIRST, AND IT ALREADY FAILED THIS WAY TONIGHT.** `logs/pitcrew.log` 21:34:09: *"no OBS projector window is open - right click the preview in OBS and choose Windowed Projector (Program), then size it to 1920x1080"*, then 21:34:39: **"60 samples in a row produced no reading, so the gauge is not visible this session and sampling stops here."** ⭐ **The stop is permanent for the session** — opening the projector after the green does nothing. That is why s126 has no wear rows while s125 has eight. ⚠️ The two guidance strings disagree on the target size (21:06 wanted 1720x916, 21:34 says 1920x1080) — app work, not car work |
| AC2 | Which limit binds the 20-lap race | **FUEL, AND IT IS THE LOWEST OF THREE, NOT THE ONLY ONE COMPUTED.** `build_inputs` + `recommend` on event 10: **fuel 12.96 laps · tyre 0.85/0.05556 = 15.3 · evidence (longest stint on file) 13.0** ⇒ `binding_limit` returns **11 laps, reason `fuel`**, from the same `min()` that produced the plan. Best plan **11 + 9, one stop, 2,235 s**; the two-stop is **+49.9 s**. Fuel 7.715 L/lap (weighted, 81 counted laps, sd 0.080), margin on the long stint **1.7 L = 1.7 s in the pit lane**. Model note, unprompted: *"the longest stint ends in the linear phase at 61 % worn - wear is not what limits it"* |
| AC3 | The pit-loss number this race produces can be believed | **⛔ NOT WITHOUT A WALL-CLOCK CROSS-CHECK.** This project has lost a lap inside a pit stop twice (Monza: 319 s wall against a 183.094 s lap-time sum, the app preferring the sum; and the Monza pit-loss "9.9 s" that was really 17.6-19.0). `pit_loss_source` is NULL on event 10 and the 20.0 s on the page is **declared, never measured here** — one pit lap exists in the whole archive (s116 L6) and it carries `fuel_added_l` NULL. ⇒ **the driver's own note of which lap he boxed on is the cross-check**, and the decomposition to run afterwards is standing time (from the fuel curve) versus transit (from the speed trace), because standing time is all fuel |
| AC4 | Rig state going in | ButtKicker endpoint **wedged at 21:52:31** — *"rendered a peak of 0.531 and metered nothing"* — and recovered in place (recovery 1). Self-healed, but a device-level wedge has previously survived process restarts. Wind link healthy (87,301 frames, 0 drops, 0 failures). App process is up; no log line since 21:52:52 |

## AD - Daytona practice race against AI, session 127, Huracán GT3, v1.71, 4 Sep 2026 22:12-22:50

20 laps, `dc` 20/20 + `lsd_b` 35 (two-change stack, §AC). **P12 -> P2.** Wear captured all race.
`[DRIVER REPORT]` *"car is great much better braking still good with a bit more rotation but still safe and
bus stop is fixed can get on throttle now"*; *"engineer started late and had laps wrong"*; *"it never told
me about gaps"*.

| # | The claim | What the data says |
|---|---|---|
| AD1 | **§AB2: `lsd_b` 35 buys rotation back at the later braking zones without giving the first corner back** | **✅ HELD, ON THE CALIBRATED INDEX, AND HIS REPORT SAYS THE SAME.** Rotation index at z4: 0.0116 (lsd_b 28) -> 0.0103 (40) -> **0.0117 (35)**, floor 0.0011 — **fully recovered**. z3 0.0148 -> 0.0125 -> 0.0134 (floor 0.0014/0.0002), partially recovered. First corner 0.0121 -> 0.0121 -> 0.0133, **inside its 0.0033 floor**, and **sub-0.90 rear frames stayed at 0 across 17 race laps.** *"Still good with a bit more rotation but still safe"* is exactly what the numbers say. ⚠️ `dc` 20/20 is confounded into all of it |
| AD2 | **§AB4: `dc` 20/20 drops the Bus Stop body swing below 20 mm** | **⛔ FALSIFIED. COMPRESSION DAMPING IS ELIMINATED — WHICH IS WHAT TAKING IT TO THE STOP WAS FOR.** Body swing at 3,790-3,840 m: **32.3 mm** at dc 20/20 (n=17) against 30.5 at 28/26 — no movement; lat-g minimum 0.037 vs 0.045; frames below 0.5 g **rose** 5.5 -> 15.0. Nor did the exit move: throttle at v-min 72.2 vs 76.3/74.7 (floor 2.8-5.9), metres to full throttle 6.5 vs 4.2/8.4 (floor 0.9-6.1), exit speed 213.2 vs 213.9/213.1. **The car still leaves the ground over that kerb exactly as it did.** |
| AD3 | *"Bus stop is fixed, can get on throttle now"* | **⭐ HIS REPORT AND EVERY INSTRUMENT I HAVE DISAGREE, AND THE DISAGREEMENT IS THE FINDING — I AM NOT AVERAGING IT.** AD2 shows nothing measurable changed at that corner. Candidate explanations, none tested: **(a) the FFB changed** — softening compression damping alters what an 18 Nm base transmits over a kerb, so the car can *communicate* the launch differently without the launch changing, and **rank zero 1b (what is in the wheel) has never been confirmed since 1.71**; (b) something GT7 does not broadcast (no per-wheel load, no damper force); (c) 17 race laps with a reference car ahead is a different task from a solo practice lap. ⇒ **his report stands as the primary record and the car stays as it is** — but the launch is on file as unsolved, and no future claim may say the Bus Stop was fixed by damping |
| AD4 | **First pit stop ever measured at this circuit** | **REFUEL RATE AND DEAD TIME ARE NOW MEASURED, THE REST IS CONTAMINATED.** Frame-level on lap 13: stationary **63.5 s** (t 3.5-67.0); fuel flat for the first **7.0 s** — **dead time measured, against the 7.5 s the model assumed**; then **6.81 -> 62.96 L in 56.0 s = 1.003 L/s**, confirming the declared 1.0 and the 1.001 in `build_inputs`. ⚠️ **Lap 12's blob ends with 21.7 s stationary at a pinned 5,479 m while lap 13 opens at 60 km/h at 0 m — those cannot both be a continuous drive, so one is an artefact and the data cannot say which.** Until that is resolved the **pit-loss track constant is NOT measured**; the 20.0 s on the event page is still `declared`. **ASK HIM: was there a pause, a spin, or a second stop on lap 12?** |
| AD5 | §AC3: the app will swallow a lap in the pit stop, as it has twice before | **✅ IT DID NOT.** Lap-time sum **2,211.00 s** against `race_elapsed_s` **2,212.37** at the flag — **1.37 s apart**, and `laps_completed` runs a **constant +1** offset across all 20 rows. Both measures agree; no lap was lost |
| AD6 | Plan versus actual | Plan was **11 + 9, 2,235.4 s, binding `fuel`**. Actual **12 + 8, 2,212.4 s** — **23.0 s inside the plan** with two incident laps in it (lap 5, 19.1 s off at 1,981-2,045 m; lap 17, 5.2 s off at 1,603-1,678 m). Green-lap fuel **7.795 L/lap** (n=16) against the plan's 7.715. **Flag with 1.444 L = 0.19 laps** — he ran it to the bone, as declared. Fuel was the constraint and fuel is what he raced to |
| AD7 | Wear, race conditions, second measurement | Stint 1 laps 1-11: RR **0.111 -> 0.611**; stint 2 laps 14-19: **0.111 -> 0.389**. ⚠️ **Three rows written as 0.0 on all four corners (laps 9, 12, 20)** — the rule-3 defect again, third occurrence, task already queued. ⚠️ **`laps.fuel_used` on lap 13 is 0.0** where the tank went 6.81 -> 62.96 and ~7 L were burned finishing the out-lap: the subtraction went negative across a refuel and something clamped it. **`max(x, 0.0)` on a measurement — CLAUDE.md rule 9 verbatim, the defect the rule was written for** |
| AD8 | *"The engineer started late"* | **✅ CONFIRMED, AND IT IS THE MONZA DEFECT UNFIXED.** Session opened **22:12:04**; the first call, *"Green, green, green"*, came at **22:16:25 — 4 min 21 s later**, logged as `lap_num` 0, and the very next call one second later says *"Lap 2."* ⇒ **green is detected at the lap-2 crossing, not at the green**, exactly as at Monza on 19 Aug. **Lap 1 received no calls at all** |
| AD9 | *"...and had laps wrong"* | **✅ CONFIRMED. THE APP IS ONE LAP BEHIND THE DRIVER'S SCREEN, ALL RACE.** `laps_completed` = `lap_num` + 1 on all 20 rows, so *"Lap 2. 18 laps to go"* was spoken while GT7 displayed lap 3. The race arithmetic is right; **the number he hears does not match the number he can see**, and under a helmet the screen wins. **`laps.laps_completed` records this and is read by nothing — third time that sentence has been written** |
| AD10 | The fuel calls | **ONE OF THEM WAS NONSENSE AND IT IS RULE 13 AGAIN.** Lap 2, 22:16:52: *"**−7.1 laps** of fuel in hand to the flag"* — a negative, spoken aloud, with 84 L aboard. Twenty-six seconds earlier, same lap: *"1.9 spare **to the stop**."* **Two different references, both called "spare/in hand", inside half a minute** — the exact failure CLAUDE.md rule 13 was written for. ⭐ The late one was excellent: lap 16, *"0.2 laps of fuel in hand to the flag"*, and he took the flag with **1.444 L = 0.19 laps.** So the model is right and the early-race expression is wrong |
| AD11 | *"It never told me about gaps"* and *"did it see other drivers' pit stops, tyres and fuel"* | **NO, AND THE REASON IS ONE MISSING CONFIG LINE, NOT A LIMIT OF THE FEED.** `rival_stops` holds **0 rows**, for this race and for every race ever run. Log 22:12:05: *"pit-wall: watching, **seeded with 0 known drivers**"*, and one second earlier the cause: *"**league: skipped - no driver name is set**, so there is nobody to look up on the hub. `python -m tools.name_drivers --me "<your hub name>"`."* ⇒ the pit wall seeds its watch list from the hub, found nobody, and watched nobody. **Of 56 calls, not one carried a gap** — and the HUD reference (measured off 81 frames) says gap ahead, gap to leader and gap behind are all readable. ⭐ **George did announce the silence** — brief: *"I can't see other cars - position only"* — which is the doctrine working; the capability was switched off by configuration, not absent |
| AD12 | The brief said *"No tyre gauge this race"* | **STALE BY 24 SECONDS.** Brief at 22:12:04; first accepted gauge reading **22:12:28**, and it ran all race — George later spoke *"RR 17"* on laps 3 and 15, matching `wear_rr` 0.167. The brief is composed before the gauge connects and is never revised |
| AD13 | The tow, measured for the first time | Front-stretch peak **287.3 km/h** in the race against **279.8-281.9** in the two solo practice sessions **the same evening on the same sheet** — **+5.4 to +7.5 km/h**, against a terminal floor of 0.56-2.77 median / 5.62 p90. ⭐ **A tow is worth more straight-line speed than the entire tested downforce range (380-420 / 600-650) ever produced** |

## AE - Corrections and fixes from the race debrief, 5 Sep 2026

| # | The prior claim | What it is now |
|---|---|---|
| AE1 | **§AD11: the pit wall saw no rivals "because no driver name is set"** (Ludo, 4 Sep) | **⛔ WRONG, AND I READ TWO ADJACENT LOG LINES AS ONE EVENT.** *"league: skipped - no driver name is set"* belongs to the **championship-points** feature (`_open_the_league`), not the pit wall. **The wall started and watched the whole race**: *"pit-wall: watching, seeded with 0 known drivers"* — and that seed is a **prior** from past races, not a requirement; `Roster` learns names off the screen. **What actually happened is worse and more useful: the wall was handed 843 frames across 20 laps and wrote NOTHING — no board, no driver, no gap, no stop, and no exception either.** So "read the board and nobody pitted" and "never found the board" were the same silence. The capability is fully built — `telemetry/board.py` finds the three gaps, `telemetry/pit_columns.py` reads each rival's pit flag, compound disc and live fuel figure, `telemetry/roster.py` names the rows, `race/gaps.py` computes the rejoin. **It is instrumented, not diagnosed** |
| AE2 | **§AD3: nothing measurable changed at the Bus Stop** | **HIS OWN CLAIM IS MEASURABLY TRUE — I HAD TESTED THE MECHANISM AND NOT THE OUTCOME HE NAMED.** He said *"I don't exceed track limits"*, and the 4 Sep penalty signature (full brake ≥95 % above 250 km/h at \|lat g\| < 0.6 on the banking, no pit) counts: **s119 1 penalty in 9 laps · s125 2 in 12 · s126 0 in 8 · the race 0 in 18.** **Zero in 26 consecutive laps** across the two most recent sheets. AD2 stands — the launch itself (body 40→73 mm, lat g to 0.04) is unchanged — but **the outcome he actually claimed did change and I had not looked.** ⚠️ Confounded: `lsd_b` 40 already gave 0 in 8 before the damper moved, so the diff may own it |
| AE3 | **§AD4: the 21.7 s stationary block on lap 12 might be a pause or a spin** | **ANSWERED — it was the pit stop** (driver, 5 Sep). ⚠️ **The arithmetic still does not close:** 21.5 s (lap 12) + 63.5 s (lap 13) = **85.0 s stationary** against a total pit-lap excess of **77.9 s** over two green laps. One of the two is wrong and the data cannot say which, so **pit loss stays `declared`.** The refuel rate (1.003 L/s) and dead time (7.0 s) are unaffected — both come from the fuel curve alone |
| AE4 | **The root cause behind `fuel_added_l` NULL, `fuel_used` 0.0 on the out-lap, and `tyres_changed` 0** | **ONE BUG, FOUR SYMPTOMS, FIXED.** `session_state` cleared `_pit_lap`, `_tyres_changed_in_stop` and `_fuel_added_in_stop` at **every** lap crossing. GT7 puts the start/finish line **inside the pit lane** at Daytona, Fuji and Monza, so the crossing fires while the car is standing in the box: the ENTRY lands on one lap and the FILL on the next, and the fill — measured correctly seconds later — was discarded. The out-lap's `start − end` then went negative and `_burn` clamped it to a fabricated **0.0**. Session 127 lap 13: 6.81 → 62.96 L in the box, ~7 L burned finishing the lap, filed as zero with `fuel_added_l` NULL. ⇒ `_stop_straddled` carries the stop across the line; regression test `test_a_stop_that_straddles_the_line_keeps_its_fill` reproduces the production row (`fuel_used=0.0, fuel_added_l=None`) without the fix. **CLAUDE.md rule 9, and it is also why the pit-loss arithmetic in AE3 does not close** |

## AF - Why the pit wall saw nothing, measured off the race recording, 5 Sep 2026

The driver supplied the OBS capture of session 127 (`2026-09-04 22-12-04.mp4`, 1920x1080, 2.5 GB).
**Re-run against real frames rather than reasoned about.**

| # | The claim | What the data says |
|---|---|---|
| AF1 | `tools/read_replay_board.py` reads the board off this video, so the board is readable | **TRUE BUT IT PROVES NOTHING ABOUT PRODUCTION - IT IS A SECOND, INDEPENDENT IMPLEMENTATION.** The tool carries its own `flag_rows` / `own_row` / `name_bitmap` against **fixed windows** (`FLAG_X = (245, 290)`, `BOARD_Y = (150, 700)`) and a per-row **fraction** of blue; it does not import `telemetry/board.py` at all. On 37 sampled frames it read **33 names and found his own row on 36**. ⚠️ **Two implementations of one reading, and only the one nothing depends on works** |
| AF2 | The production `PitWall` would have read the same frames | **⛔ NO. FED 73 REAL FRAMES FROM THE RACE, `flag_ladder` FOUND A BOARD ON 3.** `own_row` 3, gaps read **0**, pit columns **0**. That is the wall's whole-race silence, reproduced on the bench |
| AF3 | Where it fails, gate by gate (t=600 s, a frame the tool reads cleanly) | **THE FLAG COLUMN IS FOUND AND THEN THROWN AWAY.** `_flag_mask` + `_marks` locate the column at **x0=244, width 28, 59 flag-coloured rows** - correct, and within 1 px of the tool's window. They knit into **6 blobs**. Then: **`FLAG_SQUAT` (0.40) requires a blob ≥ 11.2 px tall and only 3 of 6 pass** - real GT7 flags are only partly saturated red/blue, measured heights **5, 10, 10, 12, 12, 18**. `_ladder` then reduces 3 centres to **2 rungs**, against `MIN_LADDER_ROWS = 5`. **Rejected.** ⚠️ **And it is not one constant:** the blob pitches read **40, 64, 69** against the HUD reference's measured 34 px row pitch, so rows are being missed as well as squashed; and on 4 of 6 sampled frames the strongest group is not the board at all but **scenery at x0=0, width 40-44** (the track at the left edge) or **x0=1714**. **A generic saturated-run search over a 1920x1080 racing scene is beaten by the scene** |
| AF4 | The existing `test_board.py` passes | **IT DOES - 20 tests, all green - AND THAT IS THE FINDING.** The suite feeds frames whose flags are solid single-colour blocks of consistent width, which is the shape the code assumes and not the shape GT7 draws. **Sixth time in this codebase that both ends were built and the real input was never put through them.** ⇒ any fix must be judged against **frames from this capture**, not against synthetic ones |
| AF5 | My own working method | ⛔ **I USED `git stash` IN A LIVE SHARED TREE AND LOST TWO OF THREE PATCHES.** A commit (`6f6ba12`, 23:27) landed from another process while my changes were stashed; it swept up the regression test I had written and left the fix behind, so the repository briefly held **a failing test I authored against code I had not restored**. Both patches re-applied and re-verified. **Never stash in a tree something else may be committing from** |

## AG - Adversarial review of the 4-5 Sep work, and what it overturned, 5 Sep 2026

A critic was set on tonight's code and on every number in §AD, §AE and §AF. **It overturned more of mine
than it confirmed.** Corrections below; the code fixes that followed are in the same rows.

| # | The prior claim | What it is now |
|---|---|---|
| AG1 | **§AE1/§AE4: the pit wall "is instrumented"** (Ludo, 5 Sep) | **⛔ IT WAS NOT. `health()` HAD NO CALLER, AND I TOLD THE DRIVER IT WAS LOGGED ONCE A LAP.** The controller patch was lost in a `git stash` cycle (§AF5) and I re-applied only two of three files, then read a 56-line `controller.py` diff belonging to somebody else's `_gap_view` feature as though it were mine. **Seventh instance of this codebase building both ends and skipping the caller** — and the first where the missing caller was mine and I announced it as present. ⇒ wired at both sites, and `test_health_has_a_caller_in_the_app` now fails the moment it is deleted again. **A source-level test is weak on purpose: the defect is a missing call, and no behavioural test of `PitWall` can see it, because `PitWall` is correct when nobody asks it anything** |
| AG2 | **§AE4: "one bug, four symptoms, fixed"** | **⛔ FALSE FOR TWO OF THE FOUR, AND THE FIX ADDED A THIRD DEFECT.** (a) **The out-lap was over-counted**: `_fuel_at_pit_entry` is stamped when the car stops, so one `fuel_added` spanned the WHOLE fill and all of it was credited to the out-lap, overstating it by exactly the litres put in before the line — on the critic's fixture, 12.0 L computed against 7.0 L true. (b) **The entry lap still filed a definite `tyres_changed = False`**, read at PIT_ENTRY *before* the swap: s127 L12 says 0 against a set that was changed, so the database would have held **two contradicting rows about one stop**. (c) **`_stop_straddled` could stick True**, fabricating `fuel_added_l = 0.0` and `tyres_changed = False` on ordinary green laps. ⇒ each half of the fill is now charged to the lap it happened on (total burn conserved, 7.00 = 7.00), `tyres_changed` is `None` until PIT_EXIT actually fires, and the straddle **survives exactly one crossing** and says so in the log — CLAUDE.md rule 10, a guard that cannot retire its own reference is a latch |
| AG3 | **My regression test proved the fix** | **ITS KEY ASSERTION WAS `_burn`'S OWN FORMULA CHECKED AGAINST ITSELF** — `used == start − end + added` passes for any value of `added`, including one that counts the fill twice. ✅ The test *did* fail without the fix, with the exact production signature. Replaced with a **conservation** check (10 L aboard + 30 L in − 33 L left = 7 L burned, wherever the line falls), a per-lap split check (5 L before, 25 L after), and `entry_lap.tyres_changed is None` |
| AG4 | **§AE3: the pit arithmetic "does not close", so pit loss stays declared** | **⛔ IT CLOSES, AND I FAILED TO USE MY OWN FINDING TWO ROWS LATER.** Both figures reproduce (21.7 + 63.4 s stationary; 78.5 s excess over the best green lap). **The missing term is that the two pit laps cover 10,573 m against 11,384 m for two green laps — 811 m less** — because the pit lane bypasses part of the circuit, which is the very fact §AE4 is built on. Charging each pit lap a full green lap charges it about 15 s of driving it never did. Restore that term and the identity closes on **roughly 8 s of pit-lane transit**, which is the right order. ⇒ **pit loss at Daytona IS measurable from what is already on disk** |
| AG5 | **§AD13: "a tow is worth +5.4 to +7.5 km/h"** | **⛔ RETRACTED. THE ARITHMETIC REPRODUCES; THE CAUSAL CLAIM DOES NOT.** The in-race gradient runs **backwards**: the first five green laps, mid-pack from P12 with maximum tow available, mean **285.4 km/h**; the last five, running P4 to P2 in clear air, mean **288.3**. And s118/s119 on 3 Sep — one of them solo — peaked **288.6-294.8**, higher than the "towed" race. **My own quoted floor refutes my own low end**: I cited a 5.62 km/h p90 in the same sentence as a +5.4 claim. This channel's known mover at Daytona is **wind** (3 Sep, +10.9 km/h, the two straights moving in opposite directions). The flourish comparing it to the tested downforce range set an uncontrolled between-session difference against a controlled A/B |
| AG6 | **§AD1: rotation at zone 4 "fully recovered"** | **WEAKENED — THE FLOOR WAS THE WRONG KIND.** 0.0011 came from splitting s118 and s119 *internally*; `reference_instrument_noise_floors_2026_09_04` is explicit that within-session splits cancel exactly the variation a between-session comparison carries. **Same-setup, between-session scatter across s118/s119/s125 (all `lsd_b` 28) is 0.0010-0.0018** — as large as the effect claimed. The 40 to 35 difference is **about 1σ** (0.0007 ± 0.00064). And s118 versus s119, same setup, differ by 0.0018 at the first corner — the race/practice confound §AD3 invokes to explain the Bus Stop away, not applied to the same race laps. ⇒ "0.0117 is indistinguishable from 0.0116" survives; "35 restored what 40 took away" does not |
| AG7 | **§AD3/§AE2: the penalty signature and its counts** | **THE COUNTS ARE RIGHT AND THE STATED METHOD IS NOT.** Applied literally (brake at least 95 %, above 250 km/h, lateral g under 0.6, no pit) it gives s119 2, s125 3, s126 0, race 0 — not the published 1/2/0/0. The events split by distance into **about 5,200 m (the banking, the penalty)** and **about 3,660-3,710 m (Bus Stop braking, not a penalty)**. **Restricted to the 5,200 m band the published counts reproduce exactly**, and match the independently recorded list in `brain/car-state/huracan-daytona.md`. **A distance gate was doing essential work and was missing from the write-up.** Two things that strengthen the finding: s118 was also a race and carried **3 penalty brakes in 8 laps**, so "races do not get them" is not the explanation; and at the pooled pre-race rate of 0.231 per lap, **P(0 in 16) is about 0.025**. The s126 confound stands |
| AG8 | **§AF3: `_ladder` reduces 3 centres to 2 rungs, rejected against `MIN_LADDER_ROWS`** | **THE REJECTION IS REAL AND HAPPENS ONE GATE EARLIER** — `if len(centres) < MIN_LADDER_ROWS: continue` fires at 3 < 5 and `_ladder` is never reached. **This changes the fix target: relaxing the rung count would change nothing.** Also: `_ladder`'s own docstring *expects* a 40 px step, so only the 64 and 69 support "rows are being missed"; and §AF2's 73 frames and §AF1's 37 are different samples presented as one comparison |
| AG9 | **§AD6: green-lap fuel 7.795 L/lap (n=16)** | **NO SELECTION GIVES n=16.** Excluding pit, out, excluded and lap 1: **7.774 (n=15)**. Excluding pit and out only: **7.797 (n=18)** — which is the quoted value, and it includes lap 1, a standing start. Rule 4: the count must be the count of the thing quoted |
| AG10 | **My §7 claim that `test_an_oversized_search_narrows_before_it_stands_down` is group-only shared state** | **⛔ IT FAILS ALONE.** It is a **wall-clock assertion** — a 50 ms budget this machine misses even narrowed, in isolation, at 137 ms. Not shared state, not tonight's work, but **a standing red rather than a known-benign flake**, and I recorded it as the latter |
| AG11 | Findings not yet acted on, recorded so they are not lost | `expectations.py:619` carries a **second, independent `max(0.0, ...)` clamp** on the same quantity with no `fuel_added_l` term, contained today only because out-laps are dropped from the green set; `session_state.py:645`'s `fuel_added = max(0.0, ...)` is untouched rule 9; **`pit_racing_ms` is `None` on BOTH laps of a straddled stop**, so the app's own stop-duration channel is structurally blind at every circuit whose line sits in the pit lane; `controller._race_burns` is appended to and **never read**; `_gap_view` says **"steady"** for measured-and-flat, inside-the-noise and not-enough-laps alike; and `TREND_WORTH_SAYING_S` is documented as "measured" where `race/gaps.py` says **simulated** (rule 5) |

## AH - The board reader rebuilt against real frames, 5 Sep 2026

Built on branch `worktree-agent-a05fbbf94439338da`, commit `c99cea1`, on top of `6f6ba12`.
**Not merged.** `tools/board_bench.py` is new and imports the production readers — nothing reimplemented,
which is the defect §AF1 named.

| # | The claim | What the data says |
|---|---|---|
| AH1 | The production board reader can be made to work on real frames | **✅ YES, AND I VERIFIED IT ON A SAMPLE I CHOSE MYSELF.** An independent 25-frame run over 45-2150 s of the race capture: **`flag_ladder` 25/25 · own row 25/25 · gap boxes framed 45 of 50**, against the **3 of 73** I measured before the change. The author's own two samples: 5→73 of 73 (30-2200 s) and, on a **hold-out nothing was tuned against**, 4→119 of 120. Also **24× faster** — 1,991 → 83 ms per 1920x1080 frame, because the mask pass was computed twice and `_own_from_ladder` reduced the whole frame to use 244 columns of it |
| AH2 | **§AF3's diagnosis was the whole story** | **IT WAS ONE OF SIX GATES, AND MINE WAS NOT THE FIRST.** `_flag_mask` demanded **red-or-blue with a channel lead**, which scored Germany, Belgium and Mexico as scenery before the squat filter ever ran; Japan is a red disc on white, 8 px of colour inside an 18 px flag. Then the run-width approach (my gate), replaced by a per-row **fraction** of a probe band. Then: over grass a flag's run merges rightwards past 200 px so **no width bound admits it** — columns are now proposed from where runs *begin*; the **gap readout is right-aligned into the same column** and became rungs until a colour floor separated it (measured 0.00 on every gap row against 0.20-0.99 on every flag); **catch fencing at x=1814 makes an 11-rung ladder** that beats the board on rung count alone, so a dark name band is now required (board 0.04-0.08, fencing 0.63-0.92); and `_ladder` set its pitch **from the first pair**, so where the driver sits second his row is preceded by a gap readout, the pitch came out 68 and **every row above him was lost** on five sampled frames |
| AH3 | Fixing the board fixes the gaps | **⛔ NO, AND THE REFUSAL IS NOW MEASURED RATHER THAN ASSUMED. `read_gaps` returns None on all 50 boxes in my run and all 240 in the author's.** The boxes are framed correctly; the blocker is downstream in `hud_digits._match`, which scores the four pieces of a real `+ 2.344` at **0.690, 0.698, 0.666 and 0.605 against a 0.80 floor**, and its segmentation runs the two `4`s together into one 16 px piece. **The glyph bank was built from pit-lane fuel figures, which are larger.** Extending it to 12 px glyphs needs a labelling pass, not a threshold — a separate job, and forcing it would fabricate a gap the reader cannot see |
| AH4 | The existing `test_board.py` encoded wrong assumptions | **NO — ALL 20 ORIGINAL TESTS PASS UNCHANGED.** *"The fixture was the problem, not the tests."* 24 → 34 tests, the 10 new ones parametrised over **two real crops committed as fixtures** (`daytona-race-board-p13.png`, `-p2.png`, from t=600 s and t=1805 s), including the driver-second layout that broke the old ladder. ⇒ §AF4's charge stands against the *fixtures*, not the assertions, and the synthetic guards are deliberately kept |
| AH5 | Suite state | Four quarters, **all exited 0**, no `0xC0000409`. **13 failures, every one reproduced with `board.py` reverted to HEAD** — `test_setup_doubt` x6, `test_lap_distance_anchor` x3, `test_race_wiring` x2, `test_wear_rates` x1, and `test_session_state`'s straddle test, which fails there only because that branch predates the fix in the main tree. Green in full: `test_board`, `test_pit_columns`, `test_gaps`, `test_roster`, `test_pit_wall`, `test_hud_time`, `test_replay_board_cluster` |

## AI - Why the gap readout does not read, measured off the race capture, 5 Sep 2026

Driver, 5 Sep: *"we need to resolve the gaps that's critical."* §AH3 said the blocker was the glyph bank
and left it there. Taken apart against real frames at t=600, 900, 1200, 1500, 1805 and 2000 s of
`2026-09-04 22-12-04.mp4`. **It is three faults, not one, and the bank is only the third.**

| # | The claim | What the data says |
|---|---|---|
| AI1 | **§AH3: the blocker is `hud_digits`' glyph bank** | **PARTLY - IT IS THE THIRD OF THREE, AND THE FIRST TWO STOP THE READ BEFORE THE BANK IS EVER CONSULTED** |
| AI2 | The gap box is framed correctly | **⛔ IT IS CLIPPED, AND MOSTLY ON THE LEFT - THE BOX'S LEFT EDGE SITS EXACTLY ON THE `+` SIGN.** `hud_time.tokens` refuses any box whose ink touches an edge (`pieces[0][0] <= 0 or pieces[-1][1] >= width-1`) and **that refusal is correct and must stay** — its own docstring records a `1:23.456` swept across the band returning a well-formed WRONG `3.456` at eleven of 121 offsets. Padding **6 px left and 8 px right cleared `cut` on all six boxes tried**; padding right alone did not, which is why the first attempt at this failed. The fix belongs in `gap_lines`, not in the guard |
| AI3 | The sign is handled | **⛔ `+` IS BEING EMITTED AS `:` OR `.`** GT7 draws `+ 2.344`; the sign is shorter than a digit, so it falls through `tokens`' `DIGIT_MIN_HEIGHT` branch and is classified as punctuation, corrupting the token stream before `read_seconds` parses it. Observed on 5 of 6 boxes |
| AI4 | The bank can read this font | **⛔ NO. EVERY GLYPH SCORES BELOW THE 0.80 FLOOR, AND SEVERAL ARE THE WRONG CHARACTER.** Twenty measured scores: 0.526, 0.556, 0.580, 0.592, 0.625, 0.634, 0.650, 0.660, 0.661, 0.668, 0.668, 0.673, 0.682, 0.683, 0.691, 0.697, 0.707, 0.712, 0.722, 0.744. The bank was hand-labelled from **32 pit-lane FUEL figures** in a Spa replay — larger glyphs. Gap digits measure **4-8 px wide, 11-12 px tall**. ⚠️ **`MATCH_FLOOR` must NOT be lowered**: it is what stops a fabricated gap reaching a driver mid-race, and every one of those twenty reads would pass at 0.50 |
| AI5 | Segmentation is sound at this size | **⛔ ADJACENT DIGITS MERGE.** Measured piece widths of **9, 10, 13 and 15 px** where a single digit is 4-8. Confirmed by eye against the crops: t=900 reads `+ 4.89x` and t=1805 `+ 1.06x`, and in both the final two digits arrive as one piece |
| AI6 | Ground truth exists for this | **YES, AND IT IS CHEAP.** The crops are legible when scaled 6x with NEAREST — `+ 4.89x` and `+ 1.06x` were read straight off them. A labelling pass is a labelling pass, not a modelling problem. The physics check that validated the fuel bank applies here too: **a gap to one car evolves smoothly lap to lap**, so a labelled series either holds together or it does not |

## AJ - The three faults the driver named after session 127, fixed and verified, 5 Sep 2026

Merged as `f3d0474`. **Every load-bearing number below I re-derived from `lap_frames` myself before
merging, and I neutered the central fix and watched the tests go red.**

| # | The prior claim | What it is now |
|---|---|---|
| AJ1 | **§AD8: the green is detected at the lap-2 crossing** (Ludo, 4 Sep; and at Monza, 19 Aug) | **THE SYMPTOM WAS RIGHT AND THE CAUSE IS RULE 11 IN THE DATA ITSELF.** Session 127's lap-1 blob **opens with two frames of the PREVIOUS session** — `t=0` and `t=17 ms`, **278.7 km/h, `gt7_laps_completed` 5, `last_lap_ms` 103,795** — before this race appears at frame 2 with the counter at **0**. Verified directly. `_update_phase` seeded `_prev_laps_completed` from that stale **5**, so `crossed_line` demanded a count above 5 and the real lap-1 crossing (counter 2) could not clear it; `_check_lap` then re-seeded to 2 and the lap-**2** crossing finally did. ⭐ **The launch branch was dead for the same reason** — `_grid_low_speed_seen` was seeded False off that 278.7 km/h frame, and Daytona's minimum over the rest of the lap is **58.85 km/h**, verified. ⇒ `_retire_a_foreign_lap_count`: **a counter that DROPS cannot belong to this session, so the drop retires the baseline.** Rule 10 - the guard can now refuse its own reference. Before: green **111.2 s late**, lap 1 silent. After: green at **t=5.87 s**, the frame GT7 says lap one is running, on a fixture in which **no lap completes at all** |
| AJ2 | `standing_start_ms` could have armed the green (my brief to the fixer) | **⛔ IT COULD NOT, AND I SENT THE AGENT AT THE WRONG SIGNAL.** It is **0** on that row — verified — because the app's first frame of lap 1 was already at 80 km/h, and it is computed by the recorder at lap *end*, so it cannot arm anything live. **I proposed a fix from a column name without checking either its value or when it is written** |
| AJ3 | `clock.py`'s *"0.00 s from green to the first crossing"* | **RULE 9, AND IT WAS MEASURING A NUMBER THE BUG HAD MADE ZERO BY CONSTRUCTION.** `max(0.0, app − elapsed_laps_s)` on a difference the 111.2 s back-dating had already flattened. Now unclamped for the drift baseline, and the *reported* lag is **`None`** when `laps_before_clock` is non-zero, with a warning saying why |
| AJ4 | **§AD9: the spoken lap is one behind the screen** | **FIXED, AND NOT WITH A CACHED OFFSET.** `RaceState.screen_lap` carries GT7's own number, re-read from `Lap.laps_completed` at **every** crossing — Road Atlanta measured **+1 on lap 1 and +2 by lap 20**, so a single offset would have drifted. `state.lap` remains the count behind him and stays the basis of all arithmetic; the snapshot carries both. Before *"Lap 2. 18 laps to go."* After *"Lap 3. 18 laps to go."* — the laps-to-go clause was already right and did not move |
| AJ5 | **§AD10: "−7.1 laps of fuel in hand to the flag"** | **REPRODUCED EXACTLY AND FIXED AT THE EXPRESSION.** `fuel_end/burn − laps_to_flag` gives **−7.2, −7.2, −7.1** before the stop and **+0.2, +0.2** after — 5 of 5 spoken calls. The colour line computed supply **against the flag with a stop nine laps away**, and supplied *"to the flag"* from its own literal while the engineer's line took its reference from elsewhere. ⇒ `calls.fuel_in_hand(state)` returns **`(gap, reference)` from one expression** and the colour line takes the reference as a parameter — rules 12 and 13 in one change. The tank is now only ever asked to reach the next place fuel is added, so no fill term is needed. Lap 2 becomes **"1.8 laps of fuel in hand to the stop"** against the engineer's own *"1.9 spare to the stop"* 26 s earlier; lap 16 unchanged at 0.2 to the flag. Both wordings are existing voice-pack clips, so no live-synthesis pause |
| AJ6 | Test quality | **12 new tests off that race's own figures, each proven by revert** — and I checked the central one myself: neutering `_retire_a_foreign_lap_count` fails **both** green tests, restoring it passes all 12. The reverted code emits the production strings **verbatim** (`'Lap 2. 18 laps to go.'`, `'-7.2 laps of fuel in hand to the flag.'`). **No assertion restates an implementation formula** — the fuel test checks the colour line and the engineer line **against each other**, the lap test asserts a spoken string against GT7's own recorded field, and the green test asserts an event on a fixture with no completed lap. ⚠️ **Three existing files carried assertions encoding two of the defects** — `test_orientation.py` (8), `test_timed_race.py` (2), `test_race_tonight.py` (2, one asserting the clamped `0.0` directly). **The suite had locked in two of the three bugs** |
| AJ7 | Still open | **The launch branch remains blind to a standing start whose grid frames the app never saw** — `_grid_low_speed_seen` is only set while the phase is `ON_TRACK`, and here the first on-track frame was the stale one. Whether the 0 km/h grid packets (visible in the haptics log 22:12:08-22:12:38) reached `update()` at all could not be determined from what is on disk, so the detector was left alone rather than widened on an assumption. **And the green still cannot fire before the app's first frame of a session** — true lights-out is a few seconds earlier and is in no capture |

**Supersedes nothing: §AI is the diagnosis, this is the outcome.** Merged after independent verification - see AK9.
## AK - The gap readouts read, 5 Sep 2026

`read_gaps` had never returned a number in its life. Three faults, all diagnosed off
`2026-09-04 22-12-04.mp4` before this branch started, all verified here and all fixed.
**The bank is built by `tools/gap_bank.py`, which owns `pitcrew/telemetry/hud_smallfont.json`
- do not hand-edit that file.**

| # | The claim | What the data says |
|---|---|---|
| AK1 | Fault 1 - the box was clipped, and mostly on the left | **CONFIRMED, AND IT ALONE ACCOUNTED FOR EVERY REFUSAL BEFORE ANY DIGIT WAS MATCHED.** `gap_lines` returned the ink's own bounding box, so its left edge sat on the `+` and `hud_time`'s clipped-box guard - which is correct and stays - fired on every box of every frame. Fixed in `gap_lines` with `GAP_MARGIN_L/R = 6, 8`, horizontally only: the two boxes sit one row either side of the driver's own with about ten pixels between, so vertical margin reaches into the neighbouring row's ink. `test_board` now asserts the outermost columns of the framed box carry no ink, on the ink itself rather than on the constants |
| AK2 | Fault 2 - the sign was read as a colon or a full stop | **CONFIRMED.** `+` and `-` are now characters in the small-font bank. **And the sign turned out to be a correctness guard rather than a nicety:** GT7 right-aligns the field, so a box framed a few pixels too far right loses its leading characters, and `+10.435` stripped of the `+` and the `1` is a well-formed `0.435` - ten seconds wrong, with nothing in the digits to say so. `read_gap` requires a sign; `read_gaps` additionally requires it to match the side. Measured over 169 boxes the sign agreed with the side on **all 165 that carried one**, and the four without one were exactly the four the box was framed too tight on |
| AK3 | Fault 3 - the glyph bank was the wrong size | **CONFIRMED, AND THE SEGMENTATION IS NOT FIXABLE AT THIS SIZE.** Swept across a known `+ 0.435`, six glyphs, the run-based segmentation gives 7 pieces at ink 150, 6 at 140, 6 at 120, 5 at 110 and 4 at 100. Two thresholds hit six and **neither is the right six** - at 140 the pieces are 8, 5, 1, 1, 7 and 15 px, two single-pixel slivers of the stop and one covering the `3` and the `5` together. And the font is **proportional**: measured over 135 aligned boxes the advance is 9 px after most digits, 8 after a `1` or a `2`, 10 after a `+`, 4 after a stop, so a fixed-width split is wrong on nearly every gap. ⇒ `telemetry/smallfont.py` **never segments**: templates are cells carrying their own advance and a dynamic program tiles the box, so a merge is two placements with no blank between them |
| AK4 | **`MATCH_FLOOR` has not moved, and it did not need to** | **0.80, the same number on the same metric as `hud_digits`.** Two further gates were needed and both are measured. Agreement alone lets a mostly-plate template match blank plate: the first run returned `--0..433-` for a known `+0.435` and got **124 of 132 boxes wrong**, nearly all by inventing punctuation on empty bar. Agreement alone also cannot tell round digits apart - on a known `+0.869` it ranked `3` at 0.890, `6` at 0.886, `9` at 0.873 and the true `8` at 0.803. So a placement must also clear **coverage** (the template's ink is under it) and **correlation** (the plate subtracted from both sides). Measured: correct characters score 0.966 / 0.944 / 0.988 at the median against a wrong character's 0.692 / 0.570 / 0.143, and **0 of 6,874 six-column stretches of blank plate pass all three** |
| AK5 | **The templates: how they were built, and the trap in the middle of it** | Labels read off contact sheets at 7x. The first re-fit pass rebuilt the templates from the boxes the reader **already read correctly**, which is a self-selection trap: it converged at 77 of 136 and learned nothing more, because the glyph phases it was failing on never contributed a template. ⇒ replaced by **supervised alignment** - the character sequence is given and only the positions are searched, so every labelled box hands over an instance of every glyph in it. Same corpus, 77 → 136 of 136. Two other things were needed: **several cells per character** (a right-aligned field puts a `0` on four different sub-pixel phases; one averaged template scored 0.970 on the units digit and below the floor on the millisecond one, which read as a `6`), and a **floor under the advance** (trimming a `1` - a bare vertical stroke - to its own ink gave 6 against a measured 7-9, and every one of the 14 boxes still refused contained a `1`) |
| AK6 | **The hold-out, which is the only number worth quoting** | Bank built on **135 boxes from 120 frames at 60 + 17k s**. Read back on **172 boxes from 100 frames at 53.4 + 21.3k s - not one frame in common**, transcribed off sheets carrying no reading before the reader was run on them. **109 right of 147 boxes carrying a value; 2 differ; 36 refused; 0 of 25 value-less boxes read as a value.** Both disagreements are one digit in the *milliseconds* on a glyph the capture's own compression has half eaten, and on neither is it clear the transcription is the right one. ⚠️ **31 of the 36 refusals are `gap_lines` framing scenery into the box, not the reader failing to read one** - 21 boxes wider than 90 px and 10 taller than 16, against a readout's 51-70 by 12. On cleanly framed boxes it is **109 of 116**. That framing is the next piece of work and it costs yield, not correctness |
| AK7 | The physics check | **A DENSE SERIES EVOLVES, IT DOES NOT JUMP.** 61 frames at 5 s over 1500-1800 s: the gap ahead runs 8.730 → 8.369 → 7.857 → 7.697 → 6.781 → 6.511 → 5.693 → 5.666 → 5.794 → 4.885 → 4.510 → 4.413 → 4.141 → 3.732 → 3.707 → 3.478 → 3.071 → 1.090 → 1.062 → 1.060 → 1.079 → 0.974 → 0.196 - a monotone catch from 8.7 s to 0.2 s over 170 s. Median step 0.365 s ahead and 0.388 s behind, on 34 consecutive pairs each. **Every step above 1 s is either across a hole in the data or at an overtake**, and an overtake shows as both channels flipping on the same frame: at t=1705 ahead goes 0.196 → 1.276 (the next car up the road) while behind goes 17.278 → 0.114 (the car just passed). Nothing unexplained |
| AK8 | Suite state | Four quarters, all run, no `0xC0000409`. **12 failures, and they are exactly the declared known-red set** - `test_setup_doubt` x6, `test_lap_distance_anchor` x3, `test_race_wiring` x2, `test_wear_rates` x1. None of those four files imports `smallfont`, `hud_time`, `race/gaps` or `telemetry/board`. Green in full: `test_smallfont` (new, 23), `test_board` (36), `test_gaps` (27), `test_hud_time` (16), `test_hud_digits`, `test_pit_wall`, `test_pit_columns` |
| AK9 | Verified before merging, not taken on report | **I RE-RAN IT ON A SAMPLE I CHOSE MYSELF AND CHECKED THE READINGS BY EYE.** 30 frames at 71-2111 s, none of them the author's: **52 boxes framed, 34 read** against 0 before. Then blind ground truth - crops saved at 7x with the reader's answer printed only afterwards: **`- 6.468` by eye against 6.468 read, `+ 6.511` against 6.511**, sign matching side in both. And one refusal opened: **`gap_lines` had framed the pit wall and the track alongside a `+ 0.288` squeezed into the corner** - an honest refusal, and the residual fault the author names |


---

## AL - Two records that disagree with the driver, found preparing Sardegna, 5 Sep 2026

**Context.** First sheet for the Porsche 911 RSR (991) '17 at Sardegna Road
Track Layout A, `initial` mode, nothing on file at the circuit in any car.

| # | Record says | Against | Verdict |
|---|---|---|---|
| AL1 | `05-track-reference.md` §2.12: at Sardegna, **"ride height 2 clicks up"** | Driver, 31 Aug / 1 Sep 2026: *"don't ever recommend high ride height again in GR3 it must be solved differently with suspension"*; *"increasing ride height should be a last option not a first."* `brain/driver.md` carries it as a non-negotiable | **The driver wins.** Springs took the undulation instead (nf 3.05/3.20 -> 3.40/3.60, 2.5%/10% -> 20%/30% of range); ride height held at 60/68. The Spa lesson is the same shape: being soft is why the car had to be high |
| AL2 | `05-track-reference.md` §2.12: at Sardegna, **"brake bias: one to two clicks forward"** | Driver standing refusal, `brain/driver.md`: front bias locks his fronts and creates understeer. Already recorded as a general trap at `01` §16 and specifically for Fuji at `05` §1.12 | **The driver wins.** Held at `bb 0`; his lever is LSD braking sensitivity, already at 24. **This is the second circuit whose §2 entry carries the forward-bias line** - it is a systematic property of that document, not a one-off, and every future circuit read out of `05` needs the same check |

**AL3 - the Ludo skill points at a module that no longer exists.** The skill's
spine step 4 instructs the engineer to run a question-resolver gate:

```python
from pitcrew.prompts.context import gather
from pitcrew.prompts.questions import resolve
```

`pitcrew/prompts/` is an **empty package** - only `__pycache__` survives. The
prompt screen and its resolvers were removed in `f4e30a0`
*("refactor(engineer): the prompt screen goes - the tune builder is spoken to
directly")*. The skill was not amended. **Verdict: amend the skill** - there
are no resolvers, so every question is asked directly and nothing can be
pre-resolved from the store. Sixth instance of this codebase's
built-both-ends-skipped-the-caller pattern, inverted: here the caller survived
the callee.

**AL4 - `range_records.measured_date` is restamped by any re-save.** The RSR's
record read `2026-08-21` at the start of this session and `2026-09-05` minutes
later; `controller.save_ranges` sets `measured_date=date.today()`
unconditionally, so re-opening the car screen and saving re-dates a
measurement that was not re-taken. The **endpoints** are unchanged and still
reconcile exactly with Rev C §5's percentages, so nothing downstream is wrong
today - but a record whose date moves without its numbers moving cannot
support the rule that every measurement carries its date. **Not fixed; logged.**

---

## AM - Sardegna session 128, RSR, v1.71, 5 Sep 2026

**AM1 - `05-track-reference.md` §2.12's lap-time band is 7+ seconds wrong.**
It gives Sardegna Road Track A as *"Gr.3 ~1:50-1:54"*. The RSR ran **1:42.917**
on lap 15 of its first ever session here, with five laps inside 1:43.4 and the
driver still learning the circuit. §3.2's summary table repeats the same band.

**Consequence, and it is not cosmetic:** the race is 50 minutes, so the band
sets the lap count. At 1:52 it reads 27 laps; at 1:43 it is **29**. Two laps of
fuel is 13 L, which is 13 seconds of standing time — enough to move a stop
decision. Every strategy figure I issued for this round before session 128 used
27 and has been re-derived.

**Verdict: the reference is wrong for this car.** Whether it is wrong for Gr.3
generally, or was written against a slower reference car, is not established
from one session. Amend it with the measurement and its date.

**AM2 - the refusal card's brake-balance sign warning may be over-general.**
The card says *"Signs differ by car - on the Shelby `bb -1` is forward, on the
Huracan `bb +1` is rearward."* Those two instances **do not differ**: both are
consistent with a single convention, **negative = forward, positive = rearward**.
`brain/driver.md` records the same two and no third.

This matters now because Rev B moves the RSR's balance rearward and the sign has
never been established on that car. **Verdict: unresolved, and stated as such to
the driver rather than assumed.** If a third car ever contradicts the convention,
record it here; if none does, the card should say *"confirm the sign per car"*
rather than *"signs differ by car"* - the first is true and the second is a claim
with no instance behind it.

**AM3 - the wear gauge sampled nothing, for the second event running.**
`wear_fl` is null on all 15 laps of session 128. The known cause is on file: the
sampler stops permanently about 30 s in when no OBS windowed projector is open,
which also killed session 126. **This is the second consecutive event where the
one measurement that decides the stop count was not captured.** Not a new defect
and not diagnosed further here - recorded because it has now cost two events, and
because the pre-flight for the next run has to name it.

**AM4 - a self-correction inside one analysis pass, recorded because the
retraction is the finding.** Pooled over 7,326 braking frames the front L/R slip
split read **FL-FR = -0.0135** against a measured floor of 0.003-0.006, which
looks like a standing left-front bias and matches a real signature found at
Daytona. Split by corner direction it **flips sign symmetrically** (-0.0258 one
way, +0.0201 the other): it is the inside front unloading, and the pooled figure
was an artefact of this circuit turning predominantly one way, 10,776 cornering
frames against 6,923. **A pooled left/right asymmetry is uninterpretable on a
circuit that is not left/right balanced** - it must be split by direction before
it means anything. The Daytona finding stands; this one never existed.

---

## AS1 — Shelby `arb_f`: the app's sheet 31 is the wrong record (6 Sep 2026)

| | |
|---|---|
| **App sheet 31** `Road Atlanta race Rev B` | `arb_f` **4** |
| **Sheets 5, 12, 18, 45, 50** and every issued document | `arb_f` **5** |
| **THE CAR, settings screenshot 6 Sep 2026** | **`arb_f` 5** |

**Verdict: 5. Sheet 31 is wrong and has been since 23 Aug 2026.** Flagged by
`tools/check_setup_sheets.py` and carried as an open dispute on the Round 5
sheet for eleven days; closed by a screenshot.

**Consequence, and it is not cosmetic:** the Round 4 race at Road Atlanta
(session 77) was run on `arb_f` **5**, not the 4 its own stored sheet records.
Any reading taken against sheet 31 describes a car that was never on track.
Superseded material kept, not deleted.

## AS2 — Shelby brake balance: every record on file is wrong (6 Sep 2026)

| | |
|---|---|
| Sheets 5, 12, 18, 45, 50 | `bb` **0** |
| Sheet 31 | `bb` **-1** |
| Driver, 23 Aug 2026 | *"I have had to move BB forward"*, one click |
| **THE CAR, screenshot 6 Sep 2026** | **`bb` -2** |

**Verdict: -2, two clicks FORWARD on this car.** This is the driver's own in-car
trim, which is his to make and is recorded rather than corrected — but **no
sheet has ever carried it**, and the trend across the season is one-directional:
0 -> -1 -> -2. With **ABS prohibited** in this series that is 20% of the bias
range, and it is one of three indicators that the front axle is this car's
limit. See `brain/car-state/shelby-deep-forest.md`.

## AS3 — Round 5 (RBR Short) was ended by a hardware fault, not by the car (6 Sep 2026)

Session 101 shows P3 -> P9 with a 1.08 s spin on lap 8, 20.2 s and 10.4 s
off-track on laps 14 and 15, and the capture stopping at 15:04 with 904 s still
to run. **Driver, 6 Sep 2026: the Fanatec wheelbase locked up from a GT7 error
introduced by the 1.71 update, since resolved by a Fanatec firmware update.**

**Nothing after lap 13 of session 101 describes the car, the setup or the
driver.** Laps 1-13 are clean and the race burn figure (3.813 L/lap, sd 0.082,
n = 12) is drawn from them and stands. Any pace or wear reading taken from the
tail of that race must be discarded.

## AS4 — Deep Forest tyre wear: the circuit reference is wrong by ~4x (6 Sep 2026)

| | |
|---|---|
| `05-track-reference.md` §2.4 | *"High and front-biased ... expect **13-16 laps at 1x**"* -> 6.5-8 laps at the 2x raced here |
| `data/gt7_circuits.json` | Deep Forest `wearSeverity` **5**, Red Bull Ring **3** |
| **MEASURED, session 134, 6 Sep 2026, v1.71** | worst wheel (front right) **2.808 %/lap = 0.660 %/km** -> **30.3-lap stint** |

**Verdict: the reference figure is refuted.** Five monotone HUD-gauge readings
across laps 2-6, all four wheels, OBS on. The stint is **~4x** what the
reference implies, and the tyre does not bind on a ~20.5-lap race.

**And `wearSeverity` is anti-predictive on the only two circuits where this car
has a clean measurement.** Deep Forest is graded 5 and measures 0.660 %/km on
its worst wheel; Red Bull Ring Short is graded 3 and measured 0.90-1.35 %/km.
The higher-graded circuit is the gentler one per kilometre. **Do not use
`wearSeverity` to scale a wear rate.** Superseded material kept.

The direction claim in the same entry DID hold: Deep Forest is
direction-balanced (front-right leads front-left by only 1.27x, front/rear split
5.9%) where RBR Short — all heavy corners to the right — ran its front-left at
~1.6x its front-right.

---

## AT1 — Rake: the KB's `[COMMUNITY]` direction gets its first measurement, 8 Sep 2026

| source | says |
|---|---|
| `02-gt7-setup-parameters.md` §Rake | *"positive rake → more rotation / more entry oversteer / more front grip"* · **`[COMMUNITY]`**, no test on file |
| `03-gt7-tyre-and-fuel-model.md` | *"excessive positive rake induces rotation → rear slip → rear wear"* · **`[TESTED]` elsewhere, never here** |
| `04-race-vs-qualifying.md` §2.3 | *"a full tank squats the rear and REDUCES your rake"* |
| **MEASURED, session 144, Huracán GT3 / Daytona, v1.71** | `rh_r` 70 → 64 (rake 12 → 6 mm; rear 33 % → 13 % of range against a front at 12 %). Driver: *"so much better."* Lap 3 = 103.624 s on 84.7 L ⇒ **103.370 fuel-corrected, 2nd fastest of 34 laps on file**, third lap out |

**Verdict: the direction holds on one car and is now `[MEASURED]` for the pace-and-feel half.**
Two riders, both of which matter more than the headline:

1. ⚠️ **The entry-stability half is NOT established.** T1 opposite-lock laps 8-in-31 → 0-in-2;
   **0 of 2 has p ≈ 0.55 under the old rate.** It must not be quoted as a result.
2. ⛔ **`04` §2.3 is REFUTED on this car.** Dynamic rake against fuel: **+0.0060 mm/L, i.e.
   +0.55 mm across a full-to-empty 92 L swing**, over 31 laps. The full tank does not flatten
   this platform. Measure it per car; do not import the mechanism.

**And the reason it was invisible for a week is `mm`.** "58/70" reads as a choice; **12 % and
33 % of range** reads as the rear sitting nearly 3× further off its own floor than the front.
CLAUDE.md rule 6 already required the percentages. Standing rule now in memory:
`reference_rake_percent_of_range`.

## AT2 — The differential IS an exit lever at Daytona. The 1 Sep refutation used a channel that cannot see it.

| source | says |
|---|---|
| 1 Sep 2026, `reference_daytona_corner_priority` ⛔ block | *"rear wheel-speed SPLIT across 2,727 exit frames at zone 5 and 2,869 at zone 4: median 0.0000, p95 0.024–0.036. The wheels are already tied — there is no split for more lock to close"* ⇒ **the differential is REFUTED as the exit lever; the lever is mechanical rear grip** |
| **MEASURED, session 145, 8 Sep 2026** | `lsd_a` 14 → 8. **The split stayed at median 0.0000** (T3 p95 0.0159 → 0.0261, T5 p95 0.0337 → **0.0248, the wrong way**) — while the **on-power rotation index fell 0.00724 → 0.00554 at the T5 exit, a loss of 0.00170 against a noise floor of 0.00104** taken by splitting the 15 clean race laps odd/even. Front scrub rose +0.0082 → +0.0099. Driver, unprompted: *"it felt like it was worse at rotating."* Fuel-corrected lap +2.30 s |

**Verdict: the ⛔ block is RETIRED. Superseded material kept.** The differential moves the car
at these exits; **the rear wheel-speed split cannot resolve it and therefore never refuted it.**
A measure that does not move across a six-click change of the axis it is supposed to be
measuring is not evidence of no effect.

**Two consequences.**

1. **`lsd_a` on this car runs BACKWARDS to the textbook: less lock gives LESS rotation on
   power, measured.** The KB's original `lsd_a` 22–28 ask was pointing the right way and the
   1 Sep refusal of it rests on the retired channel. `lsd_a` 8 → 20 issued for session 146.
2. ⛔ **The engineer's own error, recorded because it will recur.** `feedback_refutation_carries_
   a_direction` says a refutation carries a direction — true, and it was used here to justify
   testing the untested direction of a refuted lever. **The prior question was never asked:
   what instrument did the refuting, and can it resolve this axis at all?** It could not.
   Pair that check with `feedback_calibrate_instruments_before_use` before re-opening any
   refutation.

## AU1 — Fuel does NOT squat the rear on the Porsche RSR. It squats the front, and 1.7× as much. 9 Sep 2026

**The records that disagree**

- `brain/_inbox/04-race-vs-qualifying.md` §2.3: *a full tank squats the rear and
  flattens the platform.* `[COMMUNITY]`, no per-car measurement behind it.
- `reference_rake_percent_of_range` §4, measured on the **Huracán GT3 at
  Daytona**: **+0.0060 mm/L ⇒ +0.55 mm across a 92 L swing. NOT PRESENT.**

**What was measured, 9 Sep 2026, Porsche 911 RSR (991) '17 at Sardegna Road
Track A, GT7 v1.71, sessions 128–132.** Per-lap median of the front and rear
suspension-height channels on the clean main straight (≥250 km/h, full throttle,
|lat g| < 0.5, all four wheels tarmac), regressed on fuel:

```
  front  +0.0337 mm/L   se 0.0061   n = 11 clean laps, session 128 alone
  rear   +0.0165 mm/L   se 0.0040   n = 23 clean laps, s128/129/130 (df_f held at 400)
```

s129 gives +0.0334 and s130 +0.0467 independently. ⇒ **The front moves 1.7× the
rear per litre, so the rake flattens on a full tank and returns as it burns off
— about 3 mm at the nose across a stint.** The direction is the opposite of
§2.3's, and the magnitude is ~5× the Huracán's.

**⛔ The cause is confounded and must not be reported as fuel alone.** Fuel and
tyre wear are perfectly collinear within a run. `tyre_radius_m` is a constant
0.355 in the feed and cannot separate them; the between-session estimate is
+0.0115 ± 0.0443 on n=6, which distinguishes nothing. **What survives: the nose
sits ~3 mm lower at the end of a stint than at the start, on this car.**

**Resolution.** §2.3's line is `[COMMUNITY]` and stands as a mechanism, not as a
per-car figure — it may not be quoted for any car without a measurement. The
Huracán's "NOT PRESENT" is true of the Huracán and was never a fleet result.
**Measure this per car; it is a two-minute regression off frames already on
disk.** Rows: `measurement` 84, 85. Full working in
`brain/car-state/rsr-sardegna-road-track-a.md` §4, 9 Sep 2026.

## AU2 — The Rev A prediction check misdescribed one of the two low-platform zones. 9 Sep 2026

`brain/car-state/rsr-sardegna-road-track-a.md`, session 128 prediction table,
5 Sep 2026: body-height excursions at *"lap distance 100–200 m and 4,500–4,600 m,
i.e. the two ends of the main straight … **Not a kerb strike, not cornering
bottoming**"*, on a median lat g of 0.27 over the sub-25 mm frames.

**Re-derived 9 Sep over all 35 clean laps, binned by distance:** the 100–260 m
zone is exactly as described — 260 km/h, |lat g| < 0.5, four wheels tarmac,
straight-line surface bounce. **The 4,490–4,700 m zone is not.** It carries
sustained **1.2–1.9 lat g** at 210–230 km/h on full throttle, with kerb frames
(`TCTT`/`TCTC`) at 4,570–4,586 m, and it holds the lowest single reading on file
(**6.7 mm**). It is a loaded corner over kerbs, not a straight.

**Resolution.** The 5 Sep *conclusion* is unaffected — no harshness was reported
and nothing is scraping — but the second zone's description is superseded by
§3 of the 9 Sep entry. The sub-25 mm frame filter is what hid it: selecting on
the outcome and then averaging lat g over the survivors reports the character of
whichever zone contributed most frames, not of each zone. **Bin by distance
first, then describe each zone on its own.** Rows: `measurement` 82, 83.

## AU1a — AMENDMENT to AU1: the confound is dead. It is fuel, and the driver said why. 9 Sep 2026

**AU1, written the same day, closed with:** *"⛔ The cause is confounded and must
not be reported as fuel alone. Fuel and tyre wear are perfectly collinear within
a run … What survives: the nose sits ~3 mm lower at the end of a stint."*
**That refusal was wrong, and it was wrong in a checkable way.**

**[DRIVER REPORT], 9 Sep 2026, unprompted:**

> *"the reason the front gets higher on low fuel is the tank for an MR is in the
> front not the back like an FR"*

**Two independent confirmations, both off data already on disk:**

1. **GT7 does not shrink the tyre with wear.** `tyre_radius_m` is a **per-car,
   per-compound constant on every frame**: Huracán GT3 **0.3525** across the
   entire 20-lap Daytona race of 4 Sep — tyres 2.7 % → 39 % worn, a pit stop,
   then 0 → 28 % again — and RSR **0.355** across 33 % of wear at Sardegna.
   **Wear has no channel through which it could move ride height at all.**
2. **The sign is wrong for wear even in principle.** Wear would lower the car
   late in a run; the measurement has the car **rising** late in a run. And on a
   confirmed 46 : 54 rearward car, wear would take the **rear** first, not the
   front — the opposite of the 1.7 : 1 front bias measured.

**Resolution.** AU1's finding stands and strengthens: **front +0.0337 mm/L,
rear +0.0165 mm/L, and the cause is fuel**, because the 911's tank sits in the
nose ahead of the driver rather than behind the axle line as on a front-engined
car. `04-race-vs-qualifying.md` §2.3's *"a full tank squats the rear"* is an
FR statement and is **end-for-end wrong on any 911**; it may not be quoted
without asking where that car's tank is. It also explains the confirmed 46 : 54
balance on a mid-engined car.

**And the process lesson, which is the more expensive half.** I wrote
`unresolvable` where two checks were available in two minutes: *does the rival
cause have a channel*, and *does it have the right sign*. **A confound needs a
mechanism with the right sign and a channel that can carry it — otherwise it is
not a confound, it is a possibility that has not been looked at.** `unresolvable`
is a real verdict and must not become a place to put unchecked work. See
`feedback_never_assume_investigate_or_ask`.

⚠️ **Corollary, and it costs nothing to state:** `tyre_radius_m` is a chassis
constant, **not a wear proxy.** Nothing anywhere may read wear off it.

## AU2a — The Sardegna wear gauge DID sample. "Failed three times" is wrong. 9 Sep 2026

**The record says**, in `brain/car-state/rsr-sardegna-road-track-a.md` at Rev C,
Rev D and Rev E: *"the 12-lap wear stint … Failed to sample on three sessions
now"*, and the Rev A prediction table: *"`wear_fl` is null on all 15 laps — the
gauge sampled nothing."*

**Session 128 is correctly described. Sessions 130, 131 and 132 are not** — all
three carry `wear_source = 'hud-video'` readings on every lap after the out-lap:
13 laps of gauge data in total. Fitted per wheel, Racing Hard, at the race's
**8× multiplier**:

```
  FL 0.0394   FR 0.0458   RL 0.0488   RR 0.0528  per lap, mean of three runs
  worst wheel REAR-RIGHT  ->  L = 0.85 / 0.0528 = 16.1 laps
```

against the standing figure on file of **0.05897–0.06034/lap ⇒ 14.1–14.4 laps**,
which is **pre-1.71 and from Monza** and was flagged VOID TWICE when written.

**Resolution.** The one-stop case is better supported than the file states — but
this is **not** a settled number and does not retire the stint. The HUD gauge
ticks in **36ths**, so a 5-lap span carries **±0.0056/lap**, putting the true
figure between **13.9 and 17.0 laps** — a band that still straddles the 14.5 a
one-stop needs. And all three runs sample only the first 8–39 % of tyre life;
CLAUDE.md §5.1 says degradation is **piecewise**, so an early-life rate is a
lower bound on the late one, never a projection through it.

⇒ **What was actually missing was a stint 12 laps long, not a working gauge.**
Correct the claim, keep the run, and stop describing a 3-to-6-lap run as a failed
12-lap stint. Rows: `measurement` 88–91.

**Also corrected here:** the worst wheel is the **rear-RIGHT** at Sardegna, not
Monza's rear-left. Measured, not inferred — **60 % of the loaded cornering on
this lap is left-hand turns, carrying 1.5× the lateral load of the rights**
(101,641 frames above 0.6 g, sessions 128–132), and a left-hander loads the
right-hand wheels.
