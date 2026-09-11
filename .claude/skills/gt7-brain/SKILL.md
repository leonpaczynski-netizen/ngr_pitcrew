---
name: gt7-brain
description: Leon's GT7 race-engineering knowledge base - driver model, GT7 physics, tuning doctrine, tyre and fuel model, track and car references, and the v1.71 re-measurement protocol. Use when building or refining a setup, planning race or qualifying strategy, interpreting driver feedback, or reading Pit Crew telemetry. Also use before trusting any pre-20-Aug-2026 tuning figure.
---

# GT7 race engineering — Leon's knowledge base

The knowledge base lives in `brain/_inbox/`. **Read what the question needs;
do not load all of it** — it is roughly 1 MB and the reference documents are
large.

> **This skill is the reference. `ludo` is the engineer.** If the ask is a live
> engineering decision — build or refine a setup, plan a race or a qualifying
> run, read driver feedback, debrief a session, decide what to test — use
> **`ludo`**, which owns the procedure, the refusals and the write-back, and
> which calls back into this file for facts. Use this skill on its own for a
> lookup: which document holds a figure, what 1.71 changed, what a rule says.

## The job — stated by the driver, 23 Aug 2026

> *"You are the engineer I am the driver. You look at all the telemetry and ask
> me questions for what I felt and what you need to confirm from the udp and you
> set the car up for success. This is your job and you need to learn and adapt
> and know what I need before I do."*

**This governs every setup in this project, not one event.** In order:

1. **Read the telemetry first — all of it.** `lap_frames` holds 60 Hz per-wheel
   slip, suspension, surface, steering, pedals. **Before asking him to observe
   anything at the wheel, establish whether the stored frames already answer
   it.** The LSD acceleration fork sat open for three revisions while the answer
   was in 17,421 corner-exit frames.
2. **Ask him only for what the feed cannot carry** — feel, symptom phase, what
   the car did that no channel records, **and what is actually in the car.** A
   front-locking finding at Yas was read off telemetry without knowing he had
   dialled in `bb −1`; the diagnosis was built on his own trim.
3. **Set the car up.** Arrive with a decision and its evidence, not a menu.
4. **Anticipate** — the next test, the stale figure, the constraint about to bind.

**This does not demote his report.** Rule 1 below still stands: where the driver
and the telemetry disagree, the disagreement is the finding. This is about not
spending his attention on questions the data has already answered.

**Rank zero, above everything: what is ACTUALLY IN THE CAR.** Ask before reading
any telemetry off it. The setup record has been wrong in five consecutive
sessions, and at Yas a correct telemetry reading produced a wrong diagnosis
because the driver had dialled in `bb −1` that no sheet recorded.

> ⛔ **The one thing the engineer may not say, however much it is asked for:
> per-lap, per-corner input coaching.** Measured over 307 clean laps, a corner
> is **3–4× noisier in relative terms than a whole lap** (corner time 2σ 4–6%
> against lap time's 1.66%). `brake_point_m` 2σ is **14–37 m, worst corner
> 142 m**; `throttle_on_pct` 2σ is **11–51 percentage points**. *"Move your
> marker back 10 m"* cannot be said honestly at any corner on any circuit on
> file. **Only `min_kph` survives, and only as a multi-lap trend.** Whole-lap
> comparisons, pooled car-limitation findings and multi-lap trends are all fair.
> **When the engineer is silent about a corner it must say so** — silence means
> *I cannot see it*, not *nothing is happening*.

**The full standard, the gap analysis against what is actually built, and the
build order:** `docs/RACE-ENGINEER-CHARTER_2026-08-23.md`.

---

## Before anything else

**GT7 v1.71 (20 Aug 2026) is a physics update.** It reworked the tyre slipping
model, per-car steering geometry, damper attenuation, the default settings *and
the adjustment ranges* of suspension, differential and aero, Performance Points
fleet-wide, both driving assists, and the damage model. Polyphony reset every
ranking board.

**Every figure dated before 20 Aug 2026 is pre-patch and must be re-validated
before use — including our own.** `brain/_inbox/17-v1.71-measured-results.md`
is the only document whose numbers are post-patch. Read it first, and read
`16-update-1.71-physics-change.md` for what is now known to be unknown.

**Read `brain/RECONCILIATION.md` before trusting either the knowledge base or
the app on anything app-facing.** The two have drifted and the differences are
catalogued there.

## Which file answers what

| Question | File |
|---|---|
| **What will he refuse outright?** | **`brain/driver.md` — read this first, every time** |
| How does this driver drive? | `01-driver-profile-leon.md`, then `08-playbook-leon.md` |
| What does this slider do, and what fixes this symptom? | `02-gt7-setup-parameters.md` §10 |
| Compounds, wear, fuel maps, multipliers, pit stops | `03-gt7-tyre-and-fuel-model.md` — **worst affected by 1.71** |
| Race setup vs qualifying setup | `04-race-vs-qualifying.md` |
| What matters at this circuit | `05-track-reference.md` |
| Performance Points, builds, ballast, restrictor | `06-car-building-and-pp.md` |
| This car's character and levers | `07-car-profiles.md` |
| How a setup sheet must be laid out | `09-setup-sheet-format.md` |
| What Pit Crew's export means | `10-pit-crew-data-format.md` + `EXPORT-CONTRACT.md` |
| What a car's sliders actually range over | `11-car-slider-ranges.md` — **re-read post-1.71 before issuing any sheet** |
| What the telemetry flags actually measure | `15-pitcrew-detector-audit.md` + `RECONCILIATION.md` §C1 |
| What a previous event concluded, and why | `_inbox/setups/` |

## The one that gets broken most

**Fuel map 1. Always. Never recommend a map change.** `02` §9.6 calls fuel map
"the primary endurance-strategy lever" and it is — for other drivers. He has
tested it: other maps lose more lap time than they save. His fuel levers are
**short-shift → lift-and-coast → slipstream**, in that order. `brain/driver.md`
carries the rest of the standing refusals.

## The rules that outrank convenience

1. **The driver's report is primary evidence; telemetry corroborates.** Where
   they disagree, that disagreement is the finding — never average it.
2. **A telemetry-only flag may not buy a setup change.** It may buy a question
   or a measurement. This was overridden exactly once and cost 5 mm of ride
   height and 2 mm of rake for nothing.
3. **Reason in percent of slider range, not absolute values.** The ranges are
   `range_records`, re-read on v1.71 for all four cars on file (checked 11 Sep
   2026). The LSD's three axes no longer share a scale (0–30 / 0–100 / 0–100),
   so each is its own range - and the rule to express LSD in absolutes is
   retired. After the next physics patch, re-read before any sheet.
4. **One change per run, three clean laps minimum**, recorded with its result.
5. **Every measurement carries its date and its game version.** A number without
   a version cannot be trusted after the next patch, and there is always a next
   patch.
6. **GT7 has no tyre pressure, no caster, no brake pressure and no high/low-speed
   damper split.** Any source mentioning them was pattern-matched from another
   sim and is unreliable throughout. Second tell: post-1.71 content quoting
   confident absolute values — nobody has measured anything yet.
7. **Prefer the distribution to the datapoint**, and **re-run a post-patch
   measurement over pre-patch data before calling it a finding.** The archive
   holds far more distributions than the setup sheets ever wrote down.
