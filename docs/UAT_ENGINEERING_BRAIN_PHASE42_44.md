# UAT — Engineering Brain Phases 42–44 (Assisted Runtime Activation)

Preferred setup: Porsche 911 RSR '17, Fuji Full Course, one Base/Race setup experiment, a known applied
+ parent setup, at least one valid telemetry session.

## Execution status (honest)

This environment is **headless (offscreen Qt, no display) with no live GT7 telemetry feed**, so the
full interactive **live-GUI UAT with real telemetry could not be executed**. What WAS executed here is
an **offscreen end-to-end verification** that constructs the real `DevelopmentHistoryPage` + panels and
drives the real `SessionDB` read-only orchestration against a seeded DB. A written guide is not the same
as executed live UAT; the interactive steps below are marked **NOT RUN (needs live GUI + telemetry)**.

| # | Step | Result |
| --- | --- | --- |
| 1 | Exact current context shown | **PARTIAL (offscreen)** — context resolved + fingerprinted; visual layout not viewed live |
| 2 | Missing context fields shown honestly / legacy not silently exact | **PASS (offscreen)** — legacy tyre/fuel/gearing exact-count = 0; driver-technique/working-window exact |
| 3 | Legacy records not silently exact | **PASS (offscreen)** |
| 4 | Correct active setup fingerprint | **PASS (offscreen)** — `verify_setup` MATCH on equal fingerprints |
| 5 | Wrong setup blocks run readiness | **PASS (offscreen)** — expected_setup mismatch => state != READY_TO_RUN |
| 6 | Changed vs held-constant fields readable | **PASS (offscreen)** — run-plan renders both |
| 7 | Run-plan instructions practical | **PARTIAL (offscreen)** — content present; not read live |
| 8 | Correct live session selected | **NOT RUN (needs live telemetry)** — ranking logic PASS in unit tests |
| 9 | No automatic session binding | **PASS (offscreen)** — `auto_bind_forbidden` always true |
| 10 | Clean-lap progress updates | **NOT RUN (needs live telemetry)** — evidence_progress wired |
| 11 | Wrong compound/context invalidates run | **PASS (offscreen)** — confounded => not counted |
| 12 | Coaching prompt only in safe windows | **PASS (offscreen)** — high-workload delivers only stop/none |
| 13 | Duplicate prompts suppressed | **PASS (offscreen)** — cooldown/per-lap suppression (unit + injected clock) |
| 14 | Stale telemetry suppresses prompts | **PASS (offscreen)** — all suppressed with "stale" reason |
| 15 | Stop condition supersedes coaching | **PASS (offscreen)** — priority arbitration |
| 16 | Outcome review uses the intended session | **NOT RUN (needs live GUI)** — bound-session review PASS in unit tests |
| 17 | No outcome written without explicit confirmation | **PASS (offscreen)** — READY_TO_RECORD only on explicit confirm |
| 18 | Canonical outcome workflow receives the confirmed result | **NOT RUN (needs live GUI)** — write path referenced, not exercised live |
| 19 | No setup automatically applied | **PASS (offscreen)** — no Apply path; DB byte-identical after viewing |
| 20 | No voice/pit/autonomous strategy | **PASS (source + offscreen)** — no TTS/pit/strategy code paths |

Offscreen end-to-end evidence captured this session: legacy tyre/fuel/gearing exact-count = 0; wrong
`expected_setup` blocks `READY_TO_RUN`; high-workload telemetry delivers only stop-critical/none; the
`DevelopmentHistoryPage` builds the assisted-runtime panel (3 cards); DB SHA-256 **byte-identical**
before/after viewing; `user_version` stays 26.

## To run the remaining steps in the live app

1. Launch NGR Pit Crew, load the Porsche 911 RSR '17 @ Fuji Full Course event with a real practice
   session and a known applied + parent setup.
2. Open **Development History → Assisted Runtime**. Confirm the current context banner (step 1) and the
   changed-vs-held-constant table (step 6/7).
3. Apply the wrong setup and confirm the panel blocks READY_TO_RUN (step 5); restore the correct one.
4. Run a practice stint; confirm clean-lap progress updates (step 10), coaching prompts appear only on
   straights/pit/low-workload (step 12), and stale-telemetry/cooldown suppression (steps 13/14).
5. After the run, confirm two candidate sessions are both presented (no auto-bind, step 8/9), select
   the intended one (step 16), review the outcome, and confirm it is NOT written until you explicitly
   confirm through the existing experiment-outcome workflow (steps 17/18).
6. Confirm no setup is applied, no experiment is auto-created, and no voice/pit/strategy command occurs
   (steps 19/20). Record PASS/FAIL per step.
