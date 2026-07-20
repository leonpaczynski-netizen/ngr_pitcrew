# Engineering Brain — Phases 54–56 Pre-Phase Audits & Report Corrections

Performed at `eng-brain-phase51-53-event-command-centre @ da9d6db` before Phase 54. No earlier commit is
amended; these are additive corrections.

## Starting checkpoint (verified)

Branch `…phase51-53… @ da9d6db`; master `3d7c6af`; not pushed / no PR / not merged. `DB_VERSION == 28`,
`RULE_ENGINE_VERSION == "46.0"`. All 10 Phase 51–53 commits present; 117 Phase 51–53 targeted tests pass;
broad regression green (3,835 passed / 12 skipped / 0 failed). No live or operational certification granted
(recorded `AUTOMATED_ONLY`). Runtime/app-state files untouched.

## Correction 1 — Phase 51–53 file-count reconciliation

The Phase 51–53 completion report stated **20 A / 11 M / 0 D = 31 files, +2975/-25**. That figure was
measured mid-slice (before commit 10's files were committed) and is **wrong**. The authoritative
`git diff --name-status ef49d6c..da9d6db`:

| Class | Count |
| --- | --- |
| Added (A) | **26** |
| Modified (M) | **15** |
| Deleted (D) | **0** |
| **Total** | **41** |
| Insertions | **+3,489** |
| Deletions | **−26** |

This now reconciles with the narrative (9 new `strategy/` modules + 2 new `ui/` modules + 10 new test
files + **5** new docs = 26 added; `dashboard.py` + `session_db.py` + 9 repaired test files + 4
doc/register files = 15 modified).

- **Added strategy (9):** active_cycle_resolution, activity_binding, event_command_centre,
  event_revision_impact, live_activity, live_activity_modes, operational_certification, programme_resume,
  setup_lock_reopen.
- **Added UI (2):** event_command_centre_panel, event_command_centre_vm.
- **Added tests (10):** phase51_command_centre, phase51_command_centre_ui, phase51_dashboard_integration,
  phase52_live_activity, phase52_live_modes, phase52_binding_debrief, phase53_resume,
  phase53_revision_reopen_cert, phase51_53_golden, phase51_53_safety.
- **Added docs (5):** PHASE51_53_PREPHASE_AUDITS, PHASE51_EVENT_COMMAND_CENTRE,
  PHASE52_LIVE_ACTIVITY_ORCHESTRATION, PHASE53_OPERATIONAL_CERTIFICATION, UAT_ENGINEERING_BRAIN_PHASE51_53.
- **Modified (15):** dashboard.py, session_db.py; docs CURRENT_CLAUDE_HANDOFF, NGR_EVENT_PREPARATION_
  ARCHITECTURE, PROJECT_STATE, MASTER_TESTING_REGISTER; and 9 repaired test files (group55–61 [7],
  phase33_35_safety, phase6_golden_uat).

## Correction 2 — Phase 51–53 test-count reconciliation

`pytest --collect-only` over the 10 Phase 51–53 test files collects **exactly 117 tests**, and all 117
pass. The headline "117" was correct; the **per-file list drifted**: it listed `golden[20]` but
`test_phase51_53_golden.py` collects **19** (not 20). Correct per-file counts:

`command_centre[17] · command_centre_ui[6] · dashboard_integration[7] · live_activity[17] · live_modes[6]
· binding_debrief[8] · resume[11] · revision_reopen_cert[17] · golden[19] · safety[9]` = **117**. No
parametrised case is counted differently; the "118" sum was arithmetic drift from the wrong golden entry.

## Correction 3 — UAT terminology

The Phase 51–53 report marked automated results as "Stage … PASS". Automated tests are **not** manual UAT.
The corrected categories (used henceforth) are: **unit tests · property/metamorphic tests · runtime DB
tests · offscreen UI tests · replay tests · manual visual UAT · live GT7 UAT**. In Phase 51–53, the only
proof was the first four categories; **manual visual UAT and live GT7 UAT were NOT run** (headless). The
`UAT_ENGINEERING_BRAIN_PHASE51_53.md` staged table is corrected to say "proven by automated tests" rather
than "PASS (manual UAT)".

## Correction 4 — Operational-configuration boundary

`config["active_cycle_id"]` audit at `da9d6db`:

- **Written only on explicit action:** `MainWindow._cc_select_active_cycle` (dashboard.py:859) sets it on
  an explicit "Select" click; **in-memory only** (no disk write on selection at `da9d6db`). Config
  persistence goes exclusively through `config_paths.save_config` (atomic temp-file + `os.replace`,
  with backup), never called from selection or refresh.
- **Home refresh performs no write:** `_refresh_event_command_centre` (dashboard.py:873) only *reads*
  `active_cycle_id`; `build_event_command_centre_view` is SELECT-only.
- **Test isolation:** `tests/conftest.py` installs a session-autouse `_guard_real_config` fixture that
  fails the whole run if any test mutates the real `config.json`; `test_config_safety_smoke.py` proves the
  real config is SHA-256-identical after MainWindow construction. Headless tests cannot touch the real
  user config.
- **Operational vs semantic:** selection changes navigation only — the candidate-membership fingerprint is
  identical whether or not one is selected (proven in `test_phase51_command_centre`).
- **Missing/corrupt selected reference → safe:** `resolve_active_cycle` only honours a selection that
  matches a *non-terminal* candidate; a stale/missing id falls through to normal resolution
  (multiple active → `EVENT_REQUIRES_SELECTION`; single → resolves it; none → `NO_ACTIVE_EVENT`). No
  silent bad state; verified. Phase 54 adds an explicit test for this.

The existing Config Safety Guardrails are preserved. Phase 54 persists the selection durably only through
the safe `save_config` path on **explicit** selection (Home refresh still never writes config).

## Source-of-truth map (Phase 54 target)

The report identified four **currently defaulted** Command Centre inputs — `pending_binding`,
`pending_debrief`, `strategy_final_ready`, and `lock_ready_disciplines` — all passed as `False`/`()` at
`da9d6db`. Phase 54 replaces every defaulted input with canonical persisted or deterministically derived
state. Full field map:

| Field | Canonical source | Persisted / Derived | Unknown behaviour |
| --- | --- | --- | --- |
| active cycle | `active_cycle_resolution` over persisted cycles + `config.active_cycle_id` | selection = persisted (explicit); resolution = derived | `NO_ACTIVE_EVENT` / `EVENT_REQUIRES_SELECTION` |
| current phase | `EventPreparationCycle.current_phase` | derived from activities | first included phase |
| current activity | next actionable / explicitly-started activity | derived + persisted state | none |
| activity state | `event_preparation_activities.state` | **persisted** (explicit) | `PLANNED` |
| pending binding | activity ran + candidate sessions exist + no binding row + type requires telemetry + not abandoned/invalid | **derived** | not pending |
| pending driver feedback / debrief | binding exists + no canonical outcome + requires debrief + not invalid/abandoned | **derived** | not pending |
| Base/Qualifying/Race setup readiness | `setup_convergence` over cumulative evidence | **derived** | `insufficient_evidence` |
| setup-lock eligibility | `setup_lock.lock_permitted(convergence)` | **derived** | not eligible |
| setup-lock state | `event_preparation_cycles.setup_lock_json` (v28) | **persisted** (explicit) | unlocked |
| setup-reopen state | `setup_lock_reopen` over triggers | **derived** | not eligible |
| tyre / fuel maturity | `strategy_maturity.TyreFuelMaturity` over evidence | **derived** | `none` |
| strategy maturity | `strategy_maturity` | **derived** | `no_evidence` |
| strategy-finalisation eligibility | `maturity == FINALISATION_READY` | **derived** | not eligible |
| strategy-finalised state | `event_preparation_cycles.strategy_final_json` (v28) | **persisted** (explicit) | not finalised |
| event revision state | `event_revision_impact` over context snapshots | **derived** | none |
| official session readiness | preparation readiness | **derived** | not ready |
| interrupted activity | `event_preparation_activities.state` + `programme_resume` | persisted + derived | none |
| telemetry-loss recovery | `programme_resume.resolve_telemetry_dropout` (runtime) | **derived** (runtime only) | live |
| voice readiness | `shadow_advisory.voice_gate_allows` | **derived** | disabled |
| operational certification | `operational_certification` | **derived** | `NOT_TESTED` |

**Persistence conclusion:** all durable explicit decisions are representable in **existing v28 structures**
(`event_preparation_activities.state`, `event_preparation_activity_sessions`,
`event_preparation_cycles.setup_lock_json` / `strategy_final_json`) plus existing canonical outcome tables.
**No v29 migration is required.** Viewing / Home refresh creates no activity records.
