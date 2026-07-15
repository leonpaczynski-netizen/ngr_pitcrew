# Sprints 4 & 5 — Telemetry Event Correctness + Cross-Lap Persistence

**Status:** COMPLETE (domain engines + storage; decision-gating wired in Sprint 6)
**Branch:** milestone-3-telemetry-persistence (off master)
**UAT Defects addressed:** 1 (false wheelspin dominance), 2 (bottoming ride-height ratchet), and Requirement 3 (recurrence over raw counts).

## Sprint 4 — telemetry events are now discrete episodes

**`telemetry/slip_events.py`** — turns a lap's frames into a small set of discrete `SlipEpisode`s instead of counting packets/samples:
- Per-frame, per-axle classification via `strategy.wheel_slip.classify_wheel_slip`, so **brake-side rear slip is a LOCKUP, never acceleration wheelspin** (Fixture D).
- **Hysteresis + merging + min-duration + cooldown** so one continuous slide is **one episode, not 40 events** (Fixture C).
- **Suppression with a visible `exclusion_reason`** for shift/downshift transients, kerb-unloading (big suspension travel), airborne/unloaded wheels (road-normal collapse), and noise — suppressed episodes are returned but marked inadmissible (`is_evidence=False`).
- Each episode carries start/end, duration, peak & mean slip, axle, subtype (`power_wheelspin`/`inside_wheel_spin`/`both_wheel_power_oversteer`/`front_lockup`/`rear_lockup`/`downshift_transient`), throttle/brake/speed/gear, yaw, segment/phase (via optional resolver), confidence, provenance. All thresholds live in one tested `EpisodeConfig`.

**Bottoming anti-ratchet (Defect 2)** — `strategy/setup_diagnosis._rh_permitted_increment` keyed only on confidence, returning +2 mm at medium confidence **regardless of subtype**, so a `kerb_strike` (→ NORMAL_OR_EXPECTED) authorised a raise every session (56→58→60→62). Fixed: a ride-height raise is now authorised **only** for genuine `floor_contact` (or high-confidence `suspension_compression`); kerb strikes, throttle squat, and insufficient data return **0**. The `NORMAL_OR_EXPECTED` verdict now actually vetoes the raise.

## Sprint 5 — cross-lap persistence engine

**`strategy/cross_lap_persistence.py`** — the pure engine that decides whether an issue is isolated or a real pattern, so **one or two poor laps can never author a setup change**:
- `IssueOccurrence`, `CornerIssueSignature`, `LapMeta`, `IssuePersistenceResult`, `RecurrenceThresholds` (one tested config object).
- **Representative-lap classification** with visible exclusions (out/in/formation/incident/spin/off-track/pit/yellow/wet-mixed/invalid/corrupt).
- Occurrences group by signature (track, layout, **setup checkpoint**, corner/segment, phase, issue type, axle, compatible subtype family). Only admissible occurrences on representative laps count toward recurrence.
- Classifications: `ISOLATED_ANOMALY`, `LOW_SAMPLE`, `EMERGING_PATTERN`, `RECURRING_PATTERN`, `PERSISTENT_PATTERN`, `CROSS_SESSION_CONFIRMED`, `INCONSISTENT`. Only `PERSISTENT_PATTERN` and `CROSS_SESSION_CONFIRMED` are **setup-eligible** (and still gated by Sprint 6 arbitration).
- `render_persistence_debug` surfaces recurrence %, thresholds, and excluded laps (never hidden).

**Additive DB v18** — `corner_issue_occurrences` table (`data/session_db.py`, `_migrate_v18`, `DB_VERSION`→18) with `save_issue_occurrences`/`get_issue_occurrences`, so per-episode occurrences persist and **cross-session confirmation** works from stored data. Standalone `CREATE IF NOT EXISTS`; touches no existing table.

**Bridge:** `occurrence_from_episode` + `extract_slip_episodes` + `analyse_cross_lap` compose end-to-end (frames → episodes → occurrences → DB → persistence).

## Spec fixtures (all verified)
- **A** — two bad laps at different corners → `ISOLATED_ANOMALY`, not eligible.
- **B** — same-corner wheelspin on 6/8 laps → `PERSISTENT_PATTERN`, eligible.
- **C** — one continuous slide (many packets) → 1 episode.
- **D** — rear slip under braking → lockup, not wheelspin.
- **F** — same issue across two sessions → `CROSS_SESSION_CONFIRMED`.

## Verification
- 42 new domain/pipeline tests (episodes 11, bottoming anti-ratchet 15, persistence 12, integration 4) — all pass.
- Full suite (run in chunks to avoid the intermittent Win/Py3.14 Qt teardown segfault at large batch sizes): **~6800 passed, 0 failed.**
- 8 schema-version canaries updated for the intentional additive v18 bump (no real coverage weakened).
- **gt7_sessions.db and all protected runtime files unchanged** (tests use `:memory:`); the user's v17 DB upgrades to v18 additively on next app launch.

## Milestone 3 final report
- **Files:** +`telemetry/slip_events.py`, +`strategy/cross_lap_persistence.py`, +5 test files; modified `strategy/setup_diagnosis.py`, `data/session_db.py`, `strategy/_setup_constants.py`, 11 canary/version test files.
- **Architecture:** telemetry evidence is now episodes + cross-lap persistence, not raw counts; ride-height raises are subtype-vetoed.
- **DB/schema:** additive v18 `corner_issue_occurrences` (idempotent).
- **Behaviour:** bottoming ratchet stopped now (wired); episode/persistence engines built + stored; the persistence **gate into the setup decision** is wired in Sprint 6 (arbitration/evidence precedence), where it belongs.
- **Known limitations:** live recorder still emits legacy per-lap counters in parallel (kept for existing surfaces); replacing them with the episode pipeline in the live path + consuming persistence in the setup decision is Sprint 6/10 wiring.
- **Recommended next:** Milestone 4 — Sprints 6 (setup integrity: evidence precedence + arbitration consuming persistence), 7 (tyre curves), 8 (deterministic strategy).
