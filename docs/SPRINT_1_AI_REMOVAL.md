# Sprint 1 — Complete AI Removal

**Status:** COMPLETE (verified green)
**Branch:** milestone-1-ai-removal (off sprint-0-audit)
**Requirement:** Non-Negotiable Requirement 1 — remove ALL generative-AI functionality; Pit Crew operates fully in-house, deterministic, offline, private.

## What was removed

**8 AI-only production modules deleted:**
`strategy/_ai_client.py` (the single Anthropic HTTP client), `strategy/ai_planner.py`, `strategy/corner_verify_ai.py`, `strategy/setup_ai_audit.py`, `strategy/strategy_orchestrator.py`, `strategy/practice_orchestrator.py`, `strategy/track_context_prompt.py`, `strategy/_rec_parser.py`.

**AI removed from mixed modules (deterministic logic preserved):**
- `strategy/driving_advisor.py` — deleted the AI audit step, all `call_api` sites, and the four `_build_*_prompt` builders. The deterministic rule engine is now the sole path. `build_coaching_response`, `build_setup_advice_response`, and `build_driver_feeling_response` are now deterministic (aggregate telemetry / delegate to the rule engine); `build_last_lap_response` unchanged.
- `ui/dashboard.py` — removed the AI Log tab (+ signal/hook/wiring), the Anthropic API-key settings field + `api_key.txt` auto-load, the "Propose Profile Update" AI button/handler, the legacy "Race Strategy Analysis" AI button + `_run_ai_analysis` (**this deletes the `_sc` NameError crash surface — UAT Defect 7**), the "Full Practice Analysis" AI button + `_run_practice_analysis`, and AI help text. `_run_analyse_degradation` repointed to the deterministic tyre engine. Mid-race replan no longer calls AI (posts a graceful "deterministic re-plan pending Sprint 8" status).
- `ui/setup_builder_ui.py` — gutted the dead from-scratch `build_car_setup` paths; repointed the tuning-compliance validator; neutralized AI button labels. The deterministic "Build Baseline Setup" (Group 44) remains the from-scratch path.
- `ui/track_modelling_ui.py` — removed the AI corner-verify import/call; corners use the deterministic greedy seed-matcher. Button hidden/relabelled.
- `ui/home_dashboard_vm.py` — removed the "AI Input Safety" card.
- `ui/tab_registry.py` / `ui/product_flow.py` — removed the AI Log tab (13 → 12 tabs).
- `config_paths.py` — removed the `anthropic` default config block.
- `main.py` — removed the AI log-hook registration.
- `strategy/profile_updater.py` — removed the AI `propose_profile_update`; kept the deterministic stats/profile functions.

## Deterministic code extracted to neutral homes (no AI import)
- `strategy/race_params.py` — `RaceParams`, `StrategyOption`, `StrategyResult` (were trapped in `ai_planner`; consumed by `outcome.py`, `feasibility.py`, `race_strategy_*`).
- `strategy/tyre_degradation.py` — deterministic `analyse_tyre_degradation` (relative-baseline + life-ordering; AI cliff pass dropped, Sprint 7 restores a deterministic crossover calculator).
- `strategy/gearbox_format.py` — `format_gearbox_summary` (was `format_gearbox_for_prompt`; used by the diagnostic gearbox view).
- `strategy/setup_compliance.py` — `validate_setup_tuning_compliance` (was `validate_ai_setup_response`; pure tuning-lock check).

## Security
The leaked Anthropic key was removed locally: `api_key.txt` deleted; the `anthropic` block cleared from `config.json`/`config.json.bak` (all three are gitignored, so this is a local-runtime cleanup, not a committed change). **The user is rotating/revoking the key at the Anthropic console.**

## Architecture enforcement
New `tests/test_no_ai_architecture.py` (7 tests) is the standing gate: deleted AI modules are absent and non-importable; no production source contains a generative-AI marker (`openai`/`anthropic` import, `api.anthropic.com`, `call_api`, `x-api-key`, `sk-ant-`, deleted-module imports, `config['anthropic']`); `requirements.txt` has no LLM SDK; default config has no `anthropic` block; shared dataclasses live in a neutral module; deterministic tyre degradation is import-clean and repeatable (identical inputs → identical output).

## Offline operation
The only remaining external host in the codebase is `dg-edge.com` (optional, user-triggered reference-data scraper in `data/gt7_updater.py`). No core workflow requires any network call. GT7 telemetry (inbound UDP :33741) is local. `requests` stays in `requirements.txt` (used only by the optional scraper).

## Deferred (tracked)
- Cosmetic rename `data/ai_context_snapshot.py` → `data/analysis_inputs.py` (deterministic input-plumbing; no generative AI). Kept under its legacy name this sprint to avoid bundling a rename into the removal; scheduled before Milestone 1 review.

## Verification
- Collection: **0 errors, 6764 tests collect clean.**
- Full suite (run in halves per the known Win/Py3.14 PyQt segfault): **6737 passed, 0 failed, 27 skipped.**
- `test_no_ai_architecture.py`: **7/7 pass.**
- Production forbidden-marker scan: **CLEAN.**
- All four large Qt modules import cleanly.
- Test suite repair: 14 AI-only test files deleted, 79 repointed/pruned (deterministic coverage preserved — tyre RS/RM/RH crossover & life-ordering, feasibility gating, StrategyResult shims, setup_diagnosis, rule-first engine, home-dashboard VM). No deterministic coverage weakened.

## Sprint 1 final report
- **Files changed:** +4 neutral strategy modules, +1 arch test; −8 AI modules, −14 AI test files; ~90 modified (production + tests).
- **Architecture changed:** single AI choke point removed; deterministic rule engine is the sole setup path; shared dataclasses rehomed.
- **Behaviour changed:** AI strategy/practice/coaching/setup-audit surfaces removed; coaching/advice now deterministic; degradation deterministic; mid-race AI replan → graceful pending status.
- **AI code removed:** all of it (per arch test).
- **DB/schema changes:** none.
- **Tests added:** `test_no_ai_architecture.py` (7).
- **Regression result:** 6737 passed / 0 failed.
- **Runtime files verified untouched:** 27 protected files unchanged vs Sprint-0 baseline; only the 3 authorized key files changed (all gitignored).
- **Known limitations:** deterministic mid-race replan not yet wired (Sprint 8); `ai_context_snapshot` rename deferred; deep deterministic coaching templates deferred (Sprint 6).
- **Recommended next:** Sprint 2 — runtime stability (exact `_sc` crash regression test + exception containment).
