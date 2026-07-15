# Sprints 6, 7 & 8 — Setup Integrity, Tyre Curves, Deterministic Strategy

**Status:** COMPLETE (deterministic decision engines + fixtures; live-path wiring in Sprint 10)
**Branch:** milestone-4-setup-tyre-strategy (off master)
**Addresses:** Requirement 2 (one engineering truth model / decision statuses), Requirement 4 (measured RS/RM/RH curves), UAT Defects 3 (setup preservation / LSD) and the strategy correctness rules.

## Sprint 6 — setup engineering integrity (`strategy/setup_decision.py`)
One accountable arbitration that returns **exactly one** decision status and puts every proposed change into exactly one state (approved / preserved / rejected / deferred-test / insufficient):
- **Decision statuses:** `APPROVED_WITH_CHANGES`, `APPROVED_NO_CHANGE`, `CONTROLLED_TEST_REQUIRED`, `EVIDENCE_CONFLICT`, `INSUFFICIENT_EVIDENCE`, `REJECTED_UNSAFE`, `ENGINEERING_FAILURE`.
- **Never "approved" + "validation failed" together** — a failed recommendation returns `ENGINEERING_FAILURE`, not approved; the setup is preserved.
- **Evidence precedence** (`EvidenceTier`) with the rule that a single noisy lap / low-confidence telemetry cannot override explicit positive driver feedback → `EVIDENCE_CONFLICT`, setup preserved, controlled test prescribed (**Fixture E**). Only Sprint 5 `PERSISTENT_PATTERN` / `CROSS_SESSION_CONFIRMED` telemetry is eligible to author a change.
- **LSD independence** — `lsd_initial` / `lsd_accel` / `lsd_decel` are arbitrated on their own axes (good traction preserves accel-lock even while a persistent rear lockup approves decel-lock).
- **Driver feedback is IN the pipeline** (per-area sentiment drives each field's outcome), not a separate display.

## Sprint 7 — measured tyre curves + crossovers (`strategy/tyre_curves.py`)
Race strategy is built from **measured** per-compound tyre-age performance, not generic assumptions or one fastest lap:
- `CompoundPerformanceCurve` (pace-by-age, degradation onset/slope, cliff, usable stint), `UsableStintWindow`, `TyreEvidenceQuality`, `TyreCrossover`.
- **Pairwise crossover-lap calculator** — "RS is fastest until lap N; after that RM is the better tyre."
- **Untested compounds** produce a curve flagged `tested=False` / confidence `none` and are excluded from crossovers.
- **Mandatory acceptance fixture verified:** RS(1–3 @1:38, 4+ @1:40), RM(1–6 @1:39, 7+ @1:41.5), RH(1–12 @1:40, 13+ @1:41.8) → **RS→RM crossover after lap 3, RM→RH after lap 6.**

## Sprint 8 — deterministic race strategy (verification + one fix)
The deterministic total-race-time engine already existed (`generate_candidates` / `score_candidates` / `recommend_strategy`, ranked by `estimated_total_race_time`). This sprint locks in the guarantees and closes one gap:
- **Determinism** — identical inputs → identical candidate order, times, and recommendation (test).
- **Ranked by total race time** ascending (test).
- **Untested-compound exclusion fix:** `_second_compound` now only returns a compound with **measured pace**, so an untested compound can never enter a recommended/legal compound-switch candidate (it may only appear as an unvalidated alternative). `_fastest_compound` already excluded untested compounds.
- **No setup authoring in strategy** — already clean (Sprint 0), guarded by `ui/race_strategy_uat.py`.

## Fixtures (all verified)
E → EVIDENCE_CONFLICT (no LSD change); tyre RS→RM after lap 3 / RM→RH after lap 6; strategy determinism + untested exclusion.

## Verification
- 24 new tests (setup decision 9, tyre curves 10, strategy 5) — all pass.
- Strategy regression (363 tests) green after the `_second_compound` change.
- Full suite in chunks: **~6900 passed, 0 real failures** (the only crash is the intermittent Win/Py3.14 Qt teardown segfault at large batch sizes — every file passes individually).
- All protected runtime files unchanged.

## Milestone 4 final report
- **Files:** +`strategy/setup_decision.py`, +`strategy/tyre_curves.py`, +3 test files; modified `strategy/race_strategy_candidates.py` (untested-second-compound fix).
- **Architecture:** deterministic setup-decision arbitration (consumes Sprint 5 persistence), measured tyre-curve/crossover engine, and verified deterministic strategy ranking.
- **DB/schema:** none.
- **Behaviour:** strategy candidate generation now excludes untested compounds; the setup-decision arbitration and tyre-curve engines are built + fixture-covered.
- **Known limitations:** the setup-decision arbitration and tyre-curve crossover are not yet routed through the live `driving_advisor.build_combined_setup_response` output or the strategy explanation UI — that wiring, plus surfacing the decision statuses and crossover chart, is Sprint 10 (guided UI overhaul, which redesigns advice/strategy rendering). The engines and their guarantees are complete and locked by fixtures.
- **Recommended next:** Milestone 5 — Sprints 9 (PracticeEvidenceBundle handoff), 10 (guided UI overhaul — where these engines surface), 11 (PTT + local voice).
