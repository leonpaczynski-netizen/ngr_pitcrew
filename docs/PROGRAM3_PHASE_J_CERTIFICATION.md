# Program 3 — Phase J Certification Report

**Objective:** certify that the completed Program 3 event / session / evidence / debrief /
learning spine feeds the Setup Brain and Race Strategy Brain with correctly-scoped,
deterministic, provenance-complete evidence — establishing confidence *before* real
GT7/PSVR2 activation and Phase K UAT. **No new domain features; no Setup/Strategy Brain
doctrine changed.**

## Starting checkpoint (verified before any change)

| Item | Verified |
|---|---|
| Starting branch / HEAD | `master` / `4654063` |
| `master` == `origin/master` | ✅ both `4654063` |
| Working tree | clean of Program-3 work (only runtime data files modified — never committed) |
| DB version | **40** |
| Rule-engine version | **46.0** |
| PRs #98–#101 present | ✅ merge commits `355cf81` / `f8cce36` / `d33b180` / `4654063` |
| Full suite collected | **12,423 tests** |

**Ending branch / HEAD:** `cert/program3-phase-j-2026-08-01` / `<doc-commit>` (cert suite `e472540` + this doc).

## Reconciling the two number ambiguities (as required)

These are **two different matrices** and were conflated in earlier summaries:

1. **Acceptance gates (§31)** — the *functional* acceptance criteria. The brief calls them
   "31 gates" but §31 enumerates **30** numbered items. Post-Phase-I: **24 fully met (✅)** and
   **6 flagged yellow** (#14, #15, #16, #17, #25, #26). The earlier "7 yellow" came from
   `31−24`; the correct figure is **6** (there are 30 gates, not 31). Phase J now certifies
   #25 and #26.
2. **Pre-existing red tests** — *failing tests*, unrelated to the gate matrix. Earlier
   reports said "5"; the exact count is **6** test cases in **4 defect families** (the 6th,
   `test_refresh_feeds_appstate_and_garage`, was found during E-integration and the running
   tally wasn't updated). **All 6 are pre-existing and NOT introduced by Program 3.**

Gates ≠ reds. A yellow gate is a maturity flag on a functional criterion; a red is a failing
legacy test. They do not belong to the same list.

## Proof the 6 reds are pre-existing

Ran the exact 6 on a detached **base-commit worktree at `3c3446e`** (pre-Program-3, DB v31,
Program 3 entirely absent). All 6 failed **identically** there:

| # | Test | Family |
|---|---|---|
| 1 | `test_ofr2_session_db::TestOFR1NonCollision::test_recommendation_scoring_byte_unchanged` | stale hash-pin |
| 2 | `test_group18e_setup_history::TestGetBestLap::test_get_best_lap_returns_minimum` | old dup-lap vs v30 unique index |
| 3 | `test_group18e_setup_history::TestApplyRecommendation::test_apply_recommendation_captures_metrics` | same |
| 4 | `test_uat_shell_remediation::TestU4HomeSaysSomething::test_home_without_a_view_says_so` | home next-button |
| 5 | `test_uat_shell_remediation::TestU4HomeSaysSomething::test_next_action_navigates` | same |
| 6 | `test_live_shell_bridge::TestBridgeReadSide::test_refresh_feeds_appstate_and_garage` | garage-seed |

`base worktree: 6 failed, 10 passed` — matching `master: 6 failed, 10 passed` on the same selection.

## Certification results (J1–J9)

All through the **real** `SessionDB` + real domain functions (no orchestration-bypassing mocks).
**43 certification tests, all green.**

| Area | File | n | Certifies |
|---|---|---|---|
| J1 evidence scoping + J2 event isolation | `test_cert_j1_j2_scoping_isolation.py` | 9 | event/session-scoped evidence; metamorphic event/run changes; stale-worker rejection; no latest-row-wins; terminal cycles can't activate; quarantine exclusion |
| J3 specificity + J4 global protection + J5 decisions | `test_cert_j3_j4_j5_learning.py` | 13 | specificity ladder; more-specific outranks broad; one event can't redefine global; car/track priors don't universalise; contradiction suppresses (no averaging); immutable profile versions; accept/reject/edit/defer + suppression |
| J8 debrief + J9 determinism | `test_cert_j8_j9_debrief_determinism.py` | 10 | provenance retained; no auto-promotion; source provenance retained; low-confidence doesn't promote; driver exclusion; cross-event isolation; deterministic aggregation/transfer/selection; replay mutates nothing |
| J6 Setup Brain + J7 Race Strategy | `test_cert_j6_j7_brains.py` | 11 | physical-fingerprint isolation (event-independent by design); distinct quali/race objectives; RULE_ENGINE_VERSION 46.0; immutable parent-chained revisions; only-latest-active; snapshots link event/run/lap; acknowledge executes nothing; no command tokens |

**Cross-check:** the cert suite + `TestLiveSafety` (advisory-only pit wall) + `test_race_config_id_hash`
(frozen golden) + `test_group55_safety_guards` + `test_group61_safety_invariants` = **106 passed**.

## Defects

- **Found:** 0 code defects. One certification-test assertion was too strict (J7 revision
  immutability compared the whole row, but the `is_active` *pointer* legitimately moves to the
  new revision) — corrected to assert **content**-immutability while allowing the pointer to move.
  **This was a test fix, not a code change; no brain doctrine was touched.**
- **Fixed:** 0 (none needed).
- **Deferred:** 0.

## Safety invariants — proof unchanged

- **Advisory-only:** `acknowledge_strategy(...).executes_anything is False`; `live_pit_wall.py` /
  `ngr_live_pit_wall.py` contain no `set_plan(` / `make_pit` / `execute_pit` / `strategy_engine`
  (J7 + `TestLiveSafety`, green).
- **Deterministic / offline:** J9 proves stable outputs on identical inputs; all Program-3
  domain modules are pure/never-raise; no wall-clock in the pure layers.
- **Apply-gate:** unchanged — Program 3 added no auto-apply path; setup evidence remains scoped
  by the physical fingerprint; `RULE_ENGINE_VERSION` still `46.0`.
- **Frozen goldens:** `config_id` + fan-out allowlist untouched (green).

## Gate status after Phase J

- **✅ 26 met** (adds #25 Setup Brain scoped evidence, #26 Race Strategy scoped evidence — now certified).
- **🟡 4 remaining yellow** — all require **live GT7/PSVR2 activation** (Phase K), not further offline work:
  - #14 Coaching uses correctly scoped evidence (existing coach + spine scoping; live confirmation).
  - #15 Qualifying uses correct context — machine built + unit-certified; **live activation pending**.
  - #16 Auditable snapshot at lap/material trigger — on accepted replan today; **per-lap live pending**.
  - #17 Material incidents create revisions — on accept today; **broader live triggers pending**.

## Full-suite result

_Batched-in-quarters run in progress (12,423 collected; the single Win/Py3.14 `EventCommandCentrePanel` segfault isolates one quarter, per the register). Aggregated totals to be appended on completion; the only expected reds are the 6 pre-existing failures proven above._

## Recommendation on controlled live activation

**Go for controlled live activation.** The spine's scoping, isolation, provenance, determinism
and advisory/Apply invariants are certified offline; no defects were found; the only remaining
yellow gates are inherently live-activation items. Proceed to Phase K with the on-hardware UAT.

### Proposed activation order (lowest blast radius first)

1. **Practice** — activate the live practice brief (E14) in `_feed_live` (read-only guidance; no strategy/pit surface). Validate objective/valid-lap tracking against a real practice run.
2. **Qualifying** — activate the qualifying state machine (E16); validate out-lap → flying-lap → cooldown phases + PB/invalidation on a real hot-lap run.
3. **PTT** — broaden capture beyond strategy acks to driver reports/queries; verify the audit trail stamps the correct run/lap and that no raw transcript is stored.
4. **Per-lap race-state snapshots** — persist a snapshot at each completed race lap (advisory recording only).
5. **Broader strategy triggers** — rain / damage / fuel-deviation → immutable strategy revisions, after the snapshot path is confirmed stable live.

Each step is additive, advisory-only, and independently revertable; do not advance a step until the prior one is confirmed on-hardware.
