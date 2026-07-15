# Sprint 0 — Architecture & Dependency Audit

**Status:** COMPLETE (read-only; no production code changed)
**Date:** 2026-07-15
**Baseline:** master @ c98e46e
**Scope:** Full-repository reconnaissance ahead of the Pit Crew determinism rebuild (Requirements 1–5, UAT Defects 1–7).

This report is the factual foundation for Sprints 1–12. Every claim below is anchored to `file:line`. Nothing here changes behaviour.

---

## 0. Baseline captured

| Item | Value |
|---|---|
| Python files | 462 (excl. `.git`, `__pycache__`) |
| Test files | 316 |
| Tests collected | **7,682** in 3.70 s, zero collection/import errors (Python 3.14, Windows) |
| Runtime interpreter | Python 3.14 (`pythoncore-3.14-64`) |
| Runtime-file hash manifest | `scratchpad/sprint0_runtime_baseline_hashes.txt` (33 protected files: `config.json`, `api_key.txt`, `data/setup_history.json`, `data/gt7_sessions.db*`, all `data/track_models/*`, `data/track_library/*`) |

The full suite is **not** run in Sprint 0 (known PyQt segfault risk on Win/Py3.14 — run in halves per project memory). Collection-clean is the Sprint 0 gate; each later sprint runs its focused subset + regression halves.

---

## 1. Generative-AI inventory (Requirement 1)

**Architecture is favourable for removal.** AI is *audit-only* for setup: the deterministic rule engine is the source of truth and runs with no API key (`strategy/driving_advisor.py:1-26, 1801-1802`; `strategy/setup_ai_audit.py:1-6`; invariant test `tests/test_group42_ai_audit_only.py`). There is **no LLM SDK** — the only AI transport is raw `requests` to one endpoint.

### Single choke point
- `strategy/_ai_client.py:20` — `_API_URL = "https://api.anthropic.com/v1/messages"`
- `strategy/_ai_client.py:131-265` — `call_api()`, the only HTTP POST to Claude. **Everything funnels here**; once it is gone, nothing can reach Anthropic.
- Only AI feature toggle: `GT7_AI_DEBUG` env var (`strategy/_ai_client.py:91`). There is no `ai_enabled` config — AI is gated purely by API-key presence, so deterministic paths already stand alone.

### AI call sites (all route through `call_api`)
| Feature | Site |
|---|---|
| Race Strategy Analysis | `strategy/ai_planner.py:355` (`analyse_strategy`) |
| Tyre degradation (AI cliff pass) | `strategy/ai_planner.py:671-774` (`analyse_tyre_degradation`) |
| Practice Analysis | `strategy/ai_planner.py:380-434` (`analyse_practice_session`) |
| Build Car Setup (from scratch) | `strategy/ai_planner.py:546-668` (`build_car_setup`) — **already unreachable**, imports marked `# noqa: F401 unreachable` (`ui/setup_builder_ui.py:1546, 3309`) |
| Setup audit (post rule-engine) | `strategy/driving_advisor.py:2282-2321` |
| Driver coaching / advice | `strategy/driving_advisor.py:1432, 1567, 1636, 3322` |
| Driver profile update | `strategy/profile_updater.py:165` |
| Corner verification (track modelling) | `strategy/corner_verify_ai.py:69` |

### Module classification (drives Sprint 1 cut order)
**(A) AI-ONLY — deletable wholesale once callers are cut:** `strategy/_ai_client.py`, `strategy/corner_verify_ai.py`, `strategy/track_context_prompt.py`, `strategy/setup_ai_audit.py`, `strategy/strategy_orchestrator.py`, `strategy/practice_orchestrator.py`, `data/ai_context_snapshot.py`. Caveat: `strategy/_rec_parser.py` also parses the *rule-first* JSON payload for DB persistence — confirm the non-AI recommendation-persistence path before deleting.

**(B) MIXED — AI interwoven with deterministic logic to PRESERVE:**
- `strategy/ai_planner.py` — **extract `RaceParams`/`StrategyOption`/`StrategyResult` (`:104-187`) first** (used by `feasibility.py`, `outcome.py`, `race_strategy_*`), plus the deterministic degradation merge (`:713-774`); then delete all `_build_*_prompt`, `_parse_*`, `analyse_*`, `build_car_setup`.
- `strategy/driving_advisor.py` — preserve the entire rule engine + `_build_deterministic_fallback` + finalisers; remove the AI audit step + `call_api` sites.
- `strategy/profile_updater.py` — keep `generate_stats_doc`/`save_stats_doc`; remove `propose_profile_update`.
- `ui/dashboard.py` — remove AI Log tab (`:2238-2495`), AI Settings key field (`:5663-5697`), `_run_ai_analysis`/`_run_practice_analysis`/`_run_propose_profile_update`, snapshot builders, AI buttons/labels.
- `ui/setup_builder_ui.py`, `ui/track_modelling_ui.py`, `ui/home_dashboard_vm.py` (`_build_ai_safety_card`), `main.py:430` (log-hook), `config_paths.py:95-97` (`anthropic` default block).

**(C) DETERMINISTIC-with-AI-hook:** `strategy/setup_diagnosis.py` exports `PERSONAL_DRIVER_TUNING_MODEL`/`DRIVER_HARD_CONSTRAINTS` that `ai_planner` imports into prompts — keep the module, drop the import.

### Dependency
- `requirements.txt:7` — `requests>=2.28.0` is the only AI dependency, **but also used by `data/gt7_updater.py`** (dg-edge scraper). Do **not** remove from `requirements.txt` unless the scraper is also removed.
- No `anthropic`/`openai`/`langchain`/`gpt` imports anywhere (grep clean).

### ⚠️ Security (act independently of the rebuild)
A live-looking Anthropic key `sk-ant-…` is on disk in `api_key.txt:1` and `config.json:63-64` (`anthropic.api_key`) + `config.json.bak`. Both are gitignored (not in history) but present locally. Already flagged in `docs/AUDIT_race_engineer_remediation.md:111`. **Recommend rotating/revoking the key**; Sprint 1 deletes the files/fields. Value was not read or reproduced during this audit.

---

## 2. Network / offline proof (Requirement 1)

Only **two external hosts** exist in the entire codebase.

| Category | Where | Verdict |
|---|---|---|
| **GT7 local UDP telemetry** (KEEP) | `telemetry/listener.py:51-66` — `UDPListener`, inbound-only, `bind("0.0.0.0", 33741)`, `recvfrom`. Never sends. Decryption local (`pycryptodome` Salsa20). | Core ingress; fully offline. |
| **External AI API** (REMOVE) | `strategy/_ai_client.py:209` → `api.anthropic.com:443` | Remove (Sprint 1). |
| **Other external** (optional) | `data/gt7_updater.py:43-74` → `www.dg-edge.com:443` — scrapes car/track/BOP reference data. User-triggered only (Settings "Refresh from web", `ui/dashboard.py:6689`). Degrades silently offline; app ships cached JSON. | Not required for core operation. Leave dormant or remove separately. |
| Loopback only | `config_paths.py:58` (`127.0.0.1:33741`) — telemetry endpoint config. Hundreds of `.connect(` in `ui/*` are **Qt signals**, not sockets. `sqlite3.connect` is a local file. | No egress. |

**Core-workflow network dependency today:** 3 of 4 core workflows hard-depend on Anthropic — `analyse_strategy` (`:355`, unconditional), `build_car_setup` (`:642`, unconditional but already unreachable in UI), and the `_run_practice_analysis` gate (`ui/dashboard.py:4214-4219` returns "No Anthropic API key set" before doing anything). Setup adjustment and corner-verify already degrade gracefully. **Sprint 1 must supply deterministic replacements for strategy generation and practice analysis, not just delete them.** The telemetry core is already offline.

---

## 3. Telemetry event creation & aggregation (Requirement 3, UAT Defects 1 & 2)

**Everything feeding the setup brain is whole-lap counts or per-session averages. There is no discrete-episode model with duration/magnitude, and no true cross-lap recurrence logic.**

### Detection
- **`telemetry/recorder.py:124-303`** — per-lap integer counters (lockup, wheelspin, oversteer, kerb, bottoming, snap-throttle). Uses **four-wheel mean speed** (`:95-99`) so wheelspin/lockup are **not per-axle**. Edge-latched (`in_spin`/`in_lock`) so a slide counts once — but **no min-duration, no cooldown, no downshift/kerb-unload/brake-conflict suppression**. A downshift blip or a rear wheel unloading over a kerb registers as a wheelspin/lockup event.
- **`strategy/wheel_slip.py:68-109`** — better: per-frame, per-axle, wheelspin attributed to the **driven** axle only. Still no time/duration/cooldown; pure per-frame ratio test.
- **`strategy/live_corner_aggregator.py:126-172`** — the closest thing to episodes: edge-latched per-segment occurrence with phase + axle breakdowns. **But stores only counts** — `slip_ratio` magnitude is discarded after the latch; no start/end timestamp, no duration. `observed_symptom()` (`:196`) sets severity from **raw event count** (`high if max(spin,lock) >= 5`).

### The two UAT defects, root-caused
- **False wheelspin dominance (Defect 1):** severity and evidence are count-driven (`live_corner_aggregator.py:196-211`); no per-axle discrimination in the recorder path; no cross-lap gate — one or two bad laps dominate. Fix in Sprint 4 (episodes + suppression) + Sprint 5 (recurrence gate).
- **Bottoming ride-height ratchet (Defect 2) — VERIFIED root cause:** `_rh_permitted_increment()` (`strategy/setup_diagnosis.py:1414-1433`) keys **only on confidence**, returning `+2 mm` at medium confidence **regardless of subtype** — a `kerb_strike` classified `NORMAL_OR_EXPECTED`/`performance_relevant=False` (`:335-340`) is **not** zeroed. The only guard (`kerb_strike_rh_over_increment`, `:2826-2842`) blocks only deltas **> 3 mm**, so `+2 mm` slips through every session. Worse, confidence signal #4 (`:1352-1361`) *raises* confidence when it sees a prior ride-height change in history → self-reinforcing 56→58→60→62. The `NORMAL_OR_EXPECTED` verdict is computed and displayed but **never wired to veto the raise**. Fix in Sprint 4.

### Persistence today (DB v17)
- `data/session_db.py:415-442` — `corner_slip_telemetry`, one row per `(car_id, track, layout_id, segment_id, run_id)`, storing per-run **event counts** only. No per-lap rows, no timestamps/durations, no lap-validity, no severity/magnitude.
- Cross-run "recurrence" = a lifetime **SUM** per corner (`merge_corner_slip_rows`, `:256-310`); `sessions>1` only appends a text suffix. **Nothing asks "does corner X slip in N of the last M laps?"** — that engine does not exist. Sprint 5 builds it; DB gets a new additive per-occurrence table.

---

## 4. Domain data flows & duplicated truth (Requirement 2, UAT Defects 4–6)

### Six canonical read-models exist (all immutable, Qt-free)
`EventContext` (`data/event_context.py:131`), `StrategyContext` (`data/strategy_context.py:183`), `SetupContext` (`data/setup_context.py:232`), `TrackContext` (`data/track_context.py:280`), `SessionContext` (`data/session_context.py:106`), `WorkingRaceConfig` (`data/working_race_config.py:74`). Frozen fan-out allowlist enforced at `tests/test_legacy_fanout_phase_5.py:62`.

### Duplicated / split truth still live
- **Track readiness** — ≥3 independent notions (see below). No resolver.
- **Tyre/compound pace** — two shapes: `RaceStrategyEvidence.compound_pace_s()` (median, `strategy/race_strategy_evidence.py:219`) vs the `relative_degradation` + `tyre_degradation_cache` path (`strategy/ai_planner.py:671`).
- **Fuel** — StrategyContext vs telemetry-owned `_computed_fuel_burn_lpl()` override (`ui/dashboard.py:4090`) vs allowlisted `config["strategy"]` fuel keys.
- **`total_laps`** — StrategyContext, but `_run_ai_analysis` writes it back into `config["strategy"]["total_laps"]` (`ui/dashboard.py:4184`), bypassing the model.

### Defect 4 — Strategy authoring setup: **NO DEFECT.**
`strategy/race_strategy_*.py`, `strategy/engine.py`, `ui/race_strategy_*.py` contain zero setup-field authoring; explicitly guarded by `ui/race_strategy_uat.py:452` (`_uat_safety_checks`) and docstrings (`ui/race_strategy_readiness_vm.py:21`, `ui/race_strategy_vm.py:13`). **Requirement already met.** Sprint 8 must preserve this guard, not fix a defect.

### Defect 7 — `_sc` crash: **VERIFIED.**
`ui/dashboard.py:4162` — `_duration_secs = float(_sc.get("race_duration_minutes", 60)) * 60.0` inside the `race_type == "timed"` branch (`:4160`). `_sc` (old `config["strategy"]` local) was deleted by the AI-snapshot migration; the replacement `race_params` (`:4091`) carries `duration_mins`. Only fires on **timed** races → missed by lap-race tests. The enclosing `_run_ai_analysis` is removed in Sprint 1/2; Sprint 2 still adds the exact regression test the spec requires.

### Defect 5 — Practice → Strategy handoff: **NO `PracticeEvidenceBundle`.**
Handoff is an implicit SQLite round-trip keyed only by session id: Practice writes corner issues/recs (`strategy/practice_orchestrator.py:89,146`), Strategy re-queries via `build_strategy_evidence_from_session` (`strategy/race_strategy_from_session.py:57`). If `_strat_practice_sid` is 0 it silently falls back to all car+track history (`ui/dashboard.py:4002-4011`). No freshness/identity guarantee. Sprint 9 formalises an explicit bundle (or promotes `SessionEvidenceResult`, `race_strategy_from_session.py:39`) stamped with session id + car/track identity + change hash.

### Defect 6 — Track readiness / Fuji blocked: **VERIFIED, duplicated.**
No `TrackReadinessResolver`. Three notions: Command Centre card (`ui/home_dashboard_vm.py:442-447`), TrackContext gate (`data/track_context.py:344` `can_attempt_live_mapping`), Strategy race-plan readiness (`ui/race_strategy_readiness_vm.py:298`). **Fuji blocks because `can_attempt_live_mapping` returns `identity.is_complete and availability.station_map_available` (`:347`) — station-map-only.** A layout with valid seed geometry, a loaded reference path (`data/reference_path_loader.py`), reviewed + accepted models still reads BLOCKED if the station map isn't fed into `build_track_context`. Two stores confirmed: reviewed-segments/AI-ready (`data/track_segment_review.py:365`) and track-library (`data/track_library.py`, scanned by `reference_path_loader.py:289`), reconciled only inside `build_track_context`. Sprint 3 builds one resolver consuming station-map OR reference-path OR reviewed/accepted model, and widens the gate.

### Requirement 4 — Tyre curves: real modelling exists, but AI-entangled.
Deterministic per-compound degradation is real, not generic: `strategy/relative_degradation.py:82` (relative-baseline crossover), `strategy/outcome.py:19-89` (piecewise flat-then-linear cliff curve), `strategy/feasibility.py:80-110` (stint gating), `race_strategy_evidence.py:219` (median, not fastest, pace). **Gaps:** (1) `analyse_tyre_degradation` merges an AI cliff-detection pass (`ai_planner.py:671`) — must become fully deterministic; (2) no explicit pairwise RS/RM/RH **crossover-lap** calculator ("RS faster until lap N, RM thereafter"). Sprint 7 composes the existing per-lap degraded-pace + baselines into a deterministic crossover calculator and adds the mandatory RS→RM-after-lap-3 / RM→RH-after-lap-6 acceptance fixture.

---

## 5. UI, state, saved-vs-applied, PTT (Requirement 5, PTT defect)

### Shell & navigation
Flat `QTabWidget`, **13 tabs** (0–12), Home at 0 (project memory said 14 — corrected). Dispatch by stable key (`ui/dashboard.py:7433`), decorated `⚙` for diagnostic tabs (`ui/product_flow.py:131`). **No stepper/wizard exists** — the 12-stage journey lives only as data (`PRODUCT_JOURNEY`, `ui/product_flow.py:69`) rendered as a Home "next action" hint. AI Log is tab index 11 (removed in Sprint 1).

Tab map: 0 Home, 1 Live Race Engineer (+ practice panel), 2 Event Planner, 3 Garage, 4 Setup Builder, 5 Practice Review, 6 Strategy Builder, 7 Telemetry⚙, 8 Diagnostics⚙, 9 Settings, 10 History, 11 AI Log⚙, 12 Track Modelling⚙.

### State ownership
Newer immutable contexts are well-keyed for staleness but **built ad-hoc per call**; the authoritative mutable state is still the legacy `config["strategy"]`/`config["car_setup"]` dicts + tracker + shared single-element lists (`window._live_mode_ref`, `_practice_is_qual_ref`, `_car_id_ref`) mutated under `main._state_lock`. `MainWindow` is the de-facto hub. Contexts explicitly note the legacy stores are "intentionally not deleted this sprint" (`data/setup_context.py:48-50`).

### Saved vs Applied — significant gap (Sprint 10)
- Exists: autosave on apply (`ui/setup_builder_ui.py:3216→3265→2103`), DB "applied recommendation" link tied to a **telemetry session id** (`:3249`), and a latent unused `SetupContext.applied` hook (`data/setup_context.py:260`).
- Missing: **no "Confirmed applied in GT7" checkpoint** (grep for `applied_checkpoint`/`confirm_applied`/`Changes Applied` = zero), **no "Changes Applied in Game" button**, **no 3-state model** (Saved / Changed-since-GT7 / Confirmed-in-GT7). "Applied" in code conflates "written to form + autosaved" with in-game applied — exactly the ambiguity the UAT wants resolved. Staleness plumbing (`SetupContext.change_hash`/`telemetry_diagnosis_hash`) can support a checkpoint, but no "last confirmed-in-GT7 hash" is stored.

### Advice rendering (Sprint 10)
Advisor returns **structured dicts**, which are converted to a **monolithic HTML blob** via string-builder helpers and dumped into one read-only `QTextEdit` (`.setHtml`, `ui/setup_builder_ui.py:2337`). No per-change interactive components. Sprint 10 renders discrete structured components.

### PTT defect — hypotheses corrected (Sprint 11)
PTT is a **global `pynput` OS-level keyboard hook** (`voice/query_listener.py:328-351`), not a Qt key event — so focus-stealing / event-filter hypotheses **do not apply** (the only Qt `keyPressEvent`/`grabKeyboard` is the transient bind-capture dialog; the app `eventFilter` only swallows mouse-wheel). `query_listener.start()` is unconditional (`main.py:692`). Most likely real cause of "dead in Practice": in Practice mode the strategy engine is set inactive (`ui/dashboard.py:1497-1499`) and tracker intents read zeros (`voice/query_listener.py:83-127`), so strategy/tracker-backed PTT queries return "not available" / empty — PTT *appears* dead without a hard failure. Secondary risks: listener left stopped after a re-bind (`ui/dashboard.py:7065-7093` restart silently returns if binding incomplete; default `query_button` is `{}`, `config_paths.py:77`), and mic contention.

**Local-voice violation:** speech **recognition defaults to cloud `recognize_google`** (`voice/query_listener.py:236-245`; default backend `"google"` at `config_paths.py:73` and `ui/dashboard.py:1707-1713`). Offline Sphinx exists but is opt-in. TTS is already local (SAPI5). Sprint 11 makes local recognition the default and removes the cloud path.

---

## 6. Sprint plan impact (deltas from the original brief)

| Sprint | Adjustment from audit findings |
|---|---|
| 1 (AI removal) | Extract `RaceParams`/`StrategyOption`/`StrategyResult` before deleting `ai_planner`. Keep `requests` (used by scraper). Provide deterministic replacements for `analyse_strategy` + practice-analysis gate (they hard-depend on AI today). Rotate + delete the leaked key. |
| 2 (runtime) | `_run_ai_analysis` is deleted in Sprint 1; still add the exact `_sc`/timed-race regression test. |
| 3 (track readiness) | Build `TrackReadinessResolver`; widen `can_attempt_live_mapping` (station-map-only → OR reference-path/reviewed/accepted); ensure loader results reach `build_track_context`. |
| 4 (telemetry) | Wire the `NORMAL_OR_EXPECTED`/`kerb_strike` verdict to **veto** `_rh_permitted_increment`; add cumulative ride-height anti-ratchet; add episode model (duration/axle/phase) + suppression; per-axle wheelspin in the recorder path. |
| 5 (persistence) | Net-new engine + additive per-occurrence DB table; nothing to reuse — current DB stores per-run sums only. |
| 6 (setup integrity) | Rule engine already deterministic-first; focus on evidence precedence, statuses, LSD independence, driver-style→approved-candidate wiring. |
| 7 (tyre curves) | Reuse `relative_degradation.py`/`outcome.py`; de-AI `analyse_tyre_degradation`; add pairwise crossover-lap calculator + acceptance fixture. |
| 8 (strategy) | Defect 4 already clean — preserve the `_uat_safety_checks` guard; make ranking deterministic + exclude untested compounds. |
| 9 (handoff) | Introduce `PracticeEvidenceBundle`; formalise the session-id round-trip + stale detection. |
| 10 (UI) | Render `product_flow` journey as a real stepper; build the 3-state saved/applied model + "Changes Applied in Game" checkpoint; structured advice components; split-out legacy `config` state where practical. |
| 11 (PTT/voice) | Default to local Sphinx + remove Google; fix Practice intent data; harden listener restart. |
| 12 (UAT) | Golden Porsche-at-Fuji, offline, deterministic re-run equality, all release gates. |

---

## Sprint 0 final report

- **Sprint name:** Sprint 0 — Architecture & dependency audit
- **Branch:** master (audit only; no branch cut)
- **Commit:** baseline c98e46e
- **Files changed:** none (production). Added: `docs/SPRINT_0_AUDIT.md`; `scratchpad/sprint0_runtime_baseline_hashes.txt`.
- **Architecture changed:** none.
- **Behaviour changed:** none.
- **AI code removed:** none (inventory only).
- **DB/schema changes:** none.
- **Tests added:** none.
- **Focused test result:** n/a (read-only).
- **Regression result:** 7,682 tests collect clean in 3.70 s; suite imports without error.
- **Runtime files verified untouched:** yes — baseline SHA-256 manifest captured for all 33 protected files.
- **Manual UAT steps:** none.
- **Known limitations:** full suite not executed (deferred to per-sprint halves to avoid the known Win/Py3.14 PyQt segfault); dg-edge scraper disposition (remove vs dormant) deferred to Sprint 1 decision.
- **Recommended next sprint:** Sprint 1 — Complete AI removal, starting from the leaked-key rotation and the (A)-list wholesale deletions, extracting shared dataclasses first.
