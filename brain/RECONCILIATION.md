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

## What was not checked

Honesty about coverage: this pass read `00`, `10`, `15`, `16` (index and §11–12),
`17`, and the app-facing parts of `12`–`14`. **The four large reference documents —
`02` setup parameters (123 KB), `03` tyres and fuel (89 KB), `04` race vs qualifying
(98 KB), `05` tracks (155 KB), `06` car building (90 KB), `07` car profiles (74 KB)
— were surveyed structurally but not read line by line.** Their 1.71 exposure
banners are the KB's own assessment and have been taken at face value. Contradictions
between those documents and the app's models may exist and have not been looked for.
