# Sprint 2 — Runtime Stability

**Status:** COMPLETE (core crash fixed & regression-locked; broader hardening scoped to Sprint 8)
**Branch:** milestone-1-ai-removal
**UAT Defect 7:** `NameError: name '_sc' is not defined` in `_run_ai_analysis`, timed-race branch.

## What was fixed
- **`_run_ai_analysis` removed** (Sprint 1) — this deletes the crash site entirely. The orphaned `_sc` (a leftover from the AI-snapshot migration) only fired for `race_type == "timed"`, which is why lap-race tests never caught it.
- **Mid-race replan no longer calls AI** and runs off the Qt UI thread — the worker posts a graceful `("replan_error", "Deterministic mid-race re-plan is not yet available (pending Sprint 8).")` instead of raising.
- **Duplicate-click surfaces removed** — the AI "Race Strategy Analysis" / "Full Practice Analysis" buttons that could double-fire long work are gone.

## Regression test (the exact `_sc` condition)
`tests/test_sprint2_runtime_stability.py` (5 tests):
1. `MainWindow` has no `_run_ai_analysis` (crash handler stays gone).
2. The exact orphaned expression `_sc.get("race_duration_minutes"...)` is absent from source.
3. **General guard:** every function in `dashboard.py` that *reads* a bare `_sc` must also *assign* `_sc` locally — catches any future reintroduction of the same class of bug, not just the one line.
4. The deterministic replacement (timed-race lap estimate via `RaceParams` + `strategy.feasibility.estimate_race_laps`) is deterministic and repeatable: `ceil(3600/100) == 36`.
5. `estimate_race_laps` guards a zero/unknown lap time (returns 0, no division crash).

## Scoped forward
- Exception boundaries around the remaining long-running calculations now live in the **deterministic strategy engine** (Strategy Builder), which Sprint 8 rebuilds — that is where "never terminate the app because one analysis failed" and cancellation belong. Sprint 2's acute crash is resolved and locked.

## Sprint 2 final report
- **Files changed:** +`tests/test_sprint2_runtime_stability.py`; +`docs/SPRINT_2_RUNTIME.md`. (Production crash fix landed in Sprint 1.)
- **Behaviour changed:** none beyond Sprint 1; this sprint adds regression coverage.
- **DB/schema changes:** none.
- **Tests added:** 5.
- **Focused test result:** 5/5 pass.
- **Runtime files verified untouched:** yes (test-only + doc).
- **Known limitations:** deterministic strategy-engine exception containment / cancellation deferred to Sprint 8 (that is where the long calcs now live).
- **Recommended next:** Milestone 2 — Sprint 3 (TrackReadinessResolver + Fuji auto-load).
