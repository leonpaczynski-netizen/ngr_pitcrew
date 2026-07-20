# Engineering Brain — Phases 60–62 Pre-Phase Audits & Corrections

Performed at `eng-brain-phase57-59-live-gt7-event-certification @ fd66f74` before Phase 60. Additive — no
earlier commit amended.

## Checkpoint (verified)

Branch `…phase57-59… @ fd66f74`; master `3d7c6af`; not pushed / no PR / not merged. `DB_VERSION == 28`,
`RULE_ENGINE_VERSION == "46.0"`. All 10 Phase 57–59 commits present; 90 targeted tests pass; the existing
daemon `UDPListener` + `RaceStateTracker` remain the sole GT7 pipeline; no visual/live/voice certification
awarded (`live_event_certification()` = `NOT_TESTED`); Apply + voice gates unchanged.

## Audit A — Phase 57–59 modified-file list (correction)

`git diff --name-status 00111b4..fd66f74`: **21 A / 6 M / 0 D = 27 files, +2129/-3**.

- **Added (21):** 5 strategy (`gt7_live_adapter`, `live_runtime_cache`, `live_runtime_authority`,
  `ngr_live_pit_wall`, `live_pit_wall_integration`), 2 UI (`ngr_live_pit_wall_panel`,
  `ngr_live_pit_wall_vm`), 9 tests, 5 docs.
- **Modified (6) = 2 SOURCE + 4 DOCS:** source = `strategy/event_programme_certification.py` (Phase-59
  extension), `ui/development_history_page.py` (hosts the panels); docs = `MASTER_TESTING_REGISTER.md`,
  `docs/CURRENT_CLAUDE_HANDOFF.md`, `docs/ENGINEERING_BRAIN_PHASE56_OPERATIONAL_CERTIFICATION.md`,
  `docs/PROJECT_STATE.md`.
- The contradictory "3 source + 3 docs" description was WRONG: `strategy/ngr_live_pit_wall.py` is
  **Added**, not modified (its `pit_wall_to_dict` append landed in the same commit that created it). The
  authoritative count is **2 source + 4 docs**. Corrected the handoff.

## Audit B — real-tracker match limitations

The live classifier yields `MATCH_WITH_LIMITATIONS` for a real tracker because the engineering context
digest, tyre compound and run-plan cannot be verified from telemetry alone. Field classification:

| Field | Source | Availability |
| --- | --- | --- |
| car | GT7 telemetry via `RaceStateTracker` | **tracker-provided** |
| track | GT7 telemetry via tracker | **tracker-provided** |
| layout | resolved via map-match / track model | **resolved / can be unreliable** (GT7 does not cleanly label the layout) |
| event identity | Event Preparation state (selected cycle) | **resolved through Event Preparation** |
| setup discipline | selected activity | **resolved through selected activity** |
| expected setup fingerprint | Event Preparation + active setup authority | **resolved (canonical)** |
| **active applied setup fingerprint** | local `ActiveSetupAuthority.active_setup().setup_hash` | **resolved through active setup authority — a PROXY**: GT7 does NOT broadcast the applied setup, so if the driver changes the setup in-game without recording it via the Apply gate, this is **unreliable/unknown** |
| tyre compound | GT7 telemetry (partial) | **tracker-provided when running; may be unknown pre-lap** |
| fuel state | GT7 telemetry | **tracker-provided** |
| run-plan identity | selected activity | **resolved through selected activity** |
| selected activity | Event Preparation state | **resolved** |
| telemetry freshness | injected monotonic clock | **derived** |
| session purpose | selected activity (never telemetry) | **resolved** |
| map-match confidence | existing segment resolver / tracker | **tracker-provided** |

**Is an exact match possible through legitimate composition?** YES — an EXACT match is achievable WITHOUT
fabricating telemetry: the live *context* digest can be COMPOSED LOCALLY from the resolved canonical live
state (car+track+layout+discipline) into the same digest form as the immutable event-context digest
(Phase 60 `RuntimeContextResolution`). When that composed digest matches, the applied-setup fingerprint
(from `ActiveSetupAuthority`) equals the expected one, and compound + run-plan are known, the classifier
reaches `EXACT_ACTIVITY_MATCH`.

**Honest limitations (preserved, not disguised):**
- The applied-setup fingerprint is a **local proxy** (GT7 does not broadcast it). An unrecorded in-game
  setup change is undetectable → caps **setup attribution** confidence (not Practice pace/consistency).
- Layout can be **unreliable** when the map-match is low-confidence → keeps the match limited/unverifiable
  rather than exact.
- These block **exact setup identity** and thus setup-attribution/tyre-model/strategy-confidence that
  depend on it; they do NOT block Practice pace/consistency evidence.

## Audit C — runtime threading claim (correction)

At `fd66f74` the Phase 57–59 live modules are **pure domain** (immutable snapshots; no threads). The
production Live-tab **off-thread worker does NOT exist yet** — it is Phase 60. The Phase-58 panel
docstring wrongly implied an existing off-thread live worker; corrected to say the feeding worker is
implemented in Phase 60. Thread model of record (to be implemented + tested in Phase 60):

| Stage | Thread |
| --- | --- |
| telemetry listener (`UDPListener`) | existing daemon thread |
| tracker update (`RaceStateTracker`) | existing daemon thread |
| normalised snapshot + adapter + match | **Phase 60 live worker (off the UI thread)** |
| advisory evaluation | Phase 60 worker (bounded cadence) |
| UI refresh | Phase 60 handler on the UI thread |
| rendering | UI thread |
| stale-result protection | Phase 60 stale guard (per active event + activity) |
| shutdown/cleanup | Phase 60 controller shutdown |

Until Phase 60 implements and tests that path, no claim of a production off-thread Live tab is made.

## Audit D — production navigation ownership

- **Command Centre action opening Live:** the pit-wall / Command Centre next-action + the `live`
  quick-action surface → `TAB_LIVE`.
- **Selected event activity authority:** the Event Preparation Cycle's next/selected activity (Phase 48).
- **Production Live tab:** the existing `TAB_LIVE` ("running") tab in `ui/dashboard.py` — EXTENDED, not
  replaced.
- **Existing live telemetry panels / track map:** the Live tab content + `ui/track_map_vm.TrackMapDrawData`
  / `live_track_progress` (the canonical moving-dot authority — reused, not duplicated).
- **Session-binding / debrief surfaces:** the Command Centre binding action + the Development History
  eng-brain debrief panels.
- **Return path:** back to `TAB_HOME` (the Event Command Centre).

Phase 60 EXTENDS the existing Live tab and reuses the existing track map; it creates no new Live page,
listener, tracker, or moving-dot authority.

## Event-selection persistence (confirmed)

`config["active_cycle_id"]` via `config_paths.save_config` (atomic + backup): written only on explicit
selection, restored after restart, never on refresh, safe on missing/deleted, test-isolated by
`conftest._guard_real_config`, excluded from engineering fingerprints. No second store added.

## Runtime-file integrity (recorded)

`active_setup_state.json` (e84aeb9a…), `data/setup_history.json` (91ed583e…),
`.claude/settings.local.json` (a71b52a7…) recorded and left unstaged; re-verified untouched at the end.
Tests use `SessionDB(":memory:")` / `tmp_path` and the config-safety fixtures.
