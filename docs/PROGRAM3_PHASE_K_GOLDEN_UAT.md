# Program 3 — Phase K: Golden End-to-End UAT + Live Activation Plan

Phase K has two halves. The **automated golden scenarios** (§30) run deterministically
through the assembled stack and are **complete** here. The **live on-hardware GT7/PSVR2
UAT** can only be run by the driver and is the remaining step; this document is its plan.

**Branch:** `cert/program3-phase-k-2026-08-01` (off the Phase-J work; review gate, not merged).

## Automated golden scenarios — COMPLETE (`tests/test_golden_k_end_to_end.py`, 8 tests)

Deterministic, offline, real `SessionDB` + real domain functions — **no live seam activated**.

| # | Scenario | Journey certified |
|---|---|---|
| 1 | Track modelling | event → draft + approved track-model version → **restart** → linkage + scope survive |
| 2 | Practice & setup | baseline/A/B runs bound to one plan; **no cross-event mix**; exact lineage |
| 3 | Coaching | practice evidence is **car/track-scoped**; a practice brief won't let one anomaly dominate |
| 4 | Qualifying | out-lap (build temp) → flying ("commit", minimal) → **PB report** → cooldown; tracks its OWN best, not a race-fuel lap |
| 5 | Race + replan | immutable parent-chained revisions v1→v2→v3, per-lap snapshots, only-latest-active, **v1 history preserved** |
| 6 | Debrief | provenance-tagged findings → propose → **accept/reject/defer** (only accepted becomes a prior) |
| 7 | Cross-event transfer | new track + different car: global style applies **as a prior**; exact-car + exact-track do **NOT** transfer; rejected inactive; a new more-specific prior overrides |
| + | Restart/recovery | run identity, revision, laps survive a restart; DB elects no auto-active |

**Refinement found by scenario 7:** the Phase-I transfer only checked context *presence*, so an
exact-car learning would wrongly apply to a *different* car. Added value-matching + the
`EXCLUDED_CONTEXT_MISMATCH` verdict (a prior naming its exact context must MATCH the target; omitting
it falls back to presence — back-compat, all prior J tests green). This is a refinement of the
Program-3 learning model, not a brain-doctrine change.

## Live on-hardware UAT — the driver's step (NOT done here)

The domain layers are built + unit/golden-certified; these live activations were deliberately **not**
landed because they can only be validated against real GT7/PSVR2 telemetry. Activate **in this order**,
one at a time, confirming each on-hardware before the next (each is additive, advisory-only, and
independently revertable):

1. **Practice brief in `_feed_live`** — wire `EngineerContext.practice_brief` so the practice engineer
   tracks objective/valid-lap progress live. Verify: objective stated pre-run; valid-lap count matches
   the Review; one off-lap doesn't derail the read; session conclusion.
2. **Qualifying state machine in `_feed_live`** — feed a `QualifyingState`, advancing it on the
   pit-exit / lap-completed edges. Verify: out-lap tyre-prep cue; **minimal** flying-lap chatter; PB and
   deleted-lap reports; cooldown; a race-fuel lap is never the comparison.
3. **Broader PTT capture** — persist driver reports/queries (not just strategy acks) via
   `_record_ptt_interaction`, stamped with the live run/lap. Verify: correct run/lap on the record; **no
   raw transcript stored**; a wrong response is diagnosable from the audit row.
4. **Per-lap race-state snapshots** — persist a `race_state_snapshot` at each completed race lap
   (advisory recording). Verify: one snapshot per lap, linked to event/run/lap; no duplicate.
5. **Broader strategy-revision triggers** — rain / damage / fuel-deviation → an immutable
   `strategy_revision` (as the PTT-accept path already does). Verify: a material event appends a new
   revision (never rewrites history); only the latest is active; the driver hears only material changes.

### The seven §30 golden scenarios re-run live
After each activation, re-run the matching golden scenario against real telemetry (scenarios 1–7 above)
plus a full event journey and a mid-event restart, to confirm the deterministic backbone holds on
hardware.

## Gate impact
The four remaining yellow gates (#14 coaching, #15 qualifying, #16 lap/material snapshots, #17 material
triggers) each close as their live activation above is confirmed on-hardware. No further offline work is
required to reach them.

## Status
Automated Phase-K golden UAT: **COMPLETE (8/8 green)**. Live on-hardware UAT: **pending the driver**.
Program 3 Phases **A–K** are now implemented and certified to the limit of what is provable offline;
the only remaining work is the driver's controlled live activation + hardware UAT.
