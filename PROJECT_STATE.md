# GT7 Pit Crew Project State

## Current Mode
Architecture Stabilisation Mode.

Do not add new features until core data flow, persistence, telemetry storage, and AI context are stable.

## Repository / Build Status (2026-07-07 — Group 57 Delivered)

**Group 57 — Approved Reference Path Assets & Live Progress Activation** DELIVERED (2026-07-07). Branch `group57-reference-path-assets-progress-activation` from clean `master` (`4014857`, Group 56 merged). Read-only, advisory-only: discovers + loads approved/reference-path assets so Group 56 live track progress actually activates. **The repo already ships a real calibration-sourced Fuji Full Course reference path** (200 stations, Porsche RSR, confidence 1.0) — Fuji progress now genuinely resolves HIGH near the path. NEW pure `data/reference_path_loader.py` (Qt/DB/AI-free, read-only, never raises; parses the explicit `reference_path_v1` shape + existing Group 17 calibration shape; discovers by scanning `data/track_models/`; validates identity; converts to Group 56 `TrackPathStation`). Optional backward-compatible `reference_path` track-library manifest block + `load_track_reference_path`. Dashboard `_resolve_live_track_progress_context()` rewritten to use canonical `EventContext.track_location_id`/`layout_id` (Group 56 used the display name and missed the file) + surface provenance. Render adds `reference path: loaded (...)` Found line + honest Missing/Warning routing. **Progress NEVER creates a pit event; LOW/UNKNOWN/mismatched progress never lifts pit confidence.** Reuses `ReferencePath`/`build_track_path_stations` read-only — no calibration run, no mutation (real Fuji file byte-identical after load). Road-distance fallback (§6) deferred to Group 58. **No schema migration** (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). **52 new Group 57 tests pass**; regression green (Group 54–57 + track-lib + map/station/calibration + telemetry 1123; Group 48–53 strategy 453; dashboard smoke 13). See `docs/CURRENT_CLAUDE_HANDOFF.md`, `docs/UAT_RACE_STRATEGY.md`, `docs/TRACK_LIBRARY_SCHEMA.md`, `MASTER_TESTING_REGISTER.md`.

## Repository / Build Status (2026-07-07 — Group 56 Delivered)

**Group 56 — Live Position → Track Progress Resolver** DELIVERED (2026-07-07). Branch `group56-live-position-track-progress` from clean `master` (`cc4697f`, Group 55 merged). Read-only, advisory-only: converts live GT7 world position (X/Y/Z) into a normalised lap progress (0.0–1.0) by matching to the nearest station on an approved/reference track path, **unlocking real Group 55 pit-lane corroboration during live telemetry**. NEW pure `data/live_track_progress.py` (Qt/DB/AI/file-write-free; thresholds mirror `track_map_matching`: HIGH ≤5 m / MEDIUM ≤20 m / LOW ≤60 m / else UNKNOWN); read-only tracker `live_world_position` property; `resolve_live_progress_evidence` + `attach_track_progress` in the live adapter; `live_position`/`reference_stations` threaded through the replan runner + render. **MEDIUM/HIGH progress feeds Group 55 pit-lane corroboration; LOW/UNKNOWN never lifts pit confidence.** Progress NEVER creates a pit event (Group 55 owns corroboration, Group 54 owns pit events). Overall live-replan confidence unchanged (still ≤ MEDIUM). Reuses existing geometry (`ReferencePath`, `import_reference_path_json`) read-only — no calibration run, no track-model mutation. **No schema migration** (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). **64 new Group 56 tests pass**; regression green (Group 48–55 strategy + telemetry + track map/station/calibration 996; Group 48–53 strategy 453; dashboard smoke 13). Caveat: no repo currently ships an approved reference-path file, so live progress typically resolves as "approved reference path unavailable" until one exists (exercised via test-only `fuji_reference_path()` fixture). See `docs/CURRENT_CLAUDE_HANDOFF.md`, `docs/UAT_RACE_STRATEGY.md`, `MASTER_TESTING_REGISTER.md`.

## Repository / Build Status (2026-07-07 — Group 55 Delivered)

**Group 55 — Track-Specific Pit-Lane Mapping & Pit Confidence Upgrade** DELIVERED (2026-07-07). Branch `group55-track-pit-lane-mapping` from clean `master` (`7ff7433`, Group 54 merged). Read-only, advisory-only, **evidence-quality only**: if live lap-progress falls inside a track's *known* pit-lane corridor, a detected pit event is corroborated and its confidence can lift (refuel pit MEDIUM→HIGH; speed-only LOW→MEDIUM at most; contradictions warn; low-confidence maps cap at MEDIUM). **Pit-lane mapping corroborates but never CREATES a pit event** — pit count + tyre age still come solely from the Group 54 tracker. Missing mapping degrades to exact Group 54 behaviour. NEW pure `data/pit_lane_resolver.py`; optional backward-compatible `pit_lane` block on the track-library schema (`load_track_pit_lane`); read-only tracker `in_pit` property; corroboration threaded through the Group 53/54 live adapter + replan render. **No schema migration** (SQLite `user_version` 13, `RULE_ENGINE_VERSION` 46.0). Overall live-replan confidence still capped ≤ MEDIUM (never HIGH from proxy tyre/pace). **73 new Group 55 tests pass**; regression green (Group 48–54 strategy 754, telemetry state/tracker/pit 564, track-library 92, dashboard smoke 13). Caveat: GT7 broadcasts no normalised lap-progress yet, so the live corroboration path typically reports "progress unavailable" and falls back to Group 54; wiring a real progress source is Group 56+. See `docs/CURRENT_CLAUDE_HANDOFF.md`, `docs/UAT_RACE_STRATEGY.md`, `docs/TRACK_LIBRARY_SCHEMA.md`, `MASTER_TESTING_REGISTER.md`.

## Repository / Build Status (2026-07-05 — Group 40 Delivered)

**Group 40 — Setup Diagnosis Hardening** DELIVERED (2026-07-05). Pure Python backend sprint on top of Group 39. Key additions: `bottoming_confidence` (band/subtype/confidence), `driver_feel_traction_status`, `aero_rear_healthy` (0.80×hi fraction-of-max threshold). New validation rules: `rh_increment_exceeds_confidence`, `rh_rake_risk`, `lsd_large_change_gated`, `lsd_blocked_driver_feel`. Hardened `lsd_reversal_without_evidence` (delta >= 5 guard). Deterministic fallback (`_build_deterministic_fallback`) for post-retry engineering failures. **Full suite: 5359 pass / 6 skip / 8 fail** (8 pre-existing frozen-allowlist failures, unchanged). Branch: `ofr2-quali-race-disciplines`.

## Repository / Build Status (2026-07-02)

- **Full test suite:** 3984 pass / 6 skip / 0 fail (6 skips require a Qt display).
- **Git:** the two shipped feature branches `feature/setup-diagnosis-engine` and `feature/strategy-outcome-comparison` were combined on `integration/setup-brain-strategy-overhaul` (clean, no conflicts) and **merged to `master`** (merge commit `7254835`, pushed to `origin/master`). Merged after automated tests passed; **runtime UAT still pending**. Remote: **https://github.com/leonpaczynski-netizen/ngr_pitcrew**.
- **Secrets:** `api_key.txt` and `config.json` are gitignored — not tracked, not pushed.
- **Latest work (Setup Brain + Strategy Outcome — documented in MASTER_TESTING_REGISTER.md):**
  - **Setup Brain:** app-side deterministic setup diagnosis BEFORE the AI call (`strategy/setup_diagnosis.py`), driver tuning-model + hard-constraints injected at the top of every setup prompt, post-AI engineering validation with regenerate-once-then-surface, low-confidence track-model guard, structured liked/hated setup-history learning. Bug fixes: springs shown in **Hz** (was N/mm); timed race renders as **"N minutes, Timed Race"** (was "1 laps, Lap Race").
  - **Strategy Outcome:** deterministic total-race-time comparison (`strategy/outcome.py`) — strategies ranked head-to-head with delta-vs-fastest, confidence, and previously-hidden tyre/fuel/undercut/AI-confidence risk fields surfaced on the cards; refuel time uses the actual refuel rate; "pit loss" relabelled "pit time".
- **Detailed session notes** for Groups 17P–25 live in `docs/CURRENT_CLAUDE_HANDOFF.md`.

### Deferred / carried forward (next remediation group)
- **Setup history key omits track layout:** `config_id` hashes track-name+car+length, not `layout_id`. Two layouts of the same track can share history (config_id re-hash risk if changed — deferred to avoid regressing Event Planner/history/strategy).
- **From-scratch "Build Setup with AI":** receives the driver tuning-model + hard-constraints prompt text but NOT the post-AI engineering-validation/regenerate loop (no telemetry exists at build-from-scratch time). Only the "Analyse & Get Setup Fix" flow is fully validated.
- **Strategy finishing-position prediction:** requires rival/opponent telemetry not present in the pipeline today. Remains deferred as genuinely new scope.

## Phase 1 Fix Status (2026-06-21)

| Defect | Title | Status |
|--------|-------|--------|
| DEF-P1-001 | Session opens on first lap completion | Fixed — Awaiting Retest |
| DEF-P1-002 | Outlaps silently discarded after pit exit | Fixed — Awaiting Retest |
| DEF-P2-001 | Practice mode laps recorded as race | Fixed — Awaiting Retest |
| DEF-P2-009 | Fuel burn calculated in three locations | Fixed — Awaiting Retest |
| DEF-P4-003 | Fuel formula uses additive lap safety | Fixed — Awaiting Retest |

All 54 unit tests pass (5 skipped — require Qt display). Batch A complete (2026-06-21).

## Current Priority
Fix foundation issues in this order:

1. Database and persistence
2. Single source of truth
3. Telemetry persistence
4. AI context and debug logging
5. Session/lap integrity
6. Remove superseded UI/features

## Architecture Rules

Event Planner owns:
- Event name
- Track
- Layout
- Race type
- Race length
- Fuel multiplier
- Refuel rate
- Tyre wear multiplier
- BoP status
- Tuning allowed status
- Available tyres
- Required tyres
- Weather/rain risk
- Damage settings

Garage owns:
- Cars
- Active car
- Car setup history
- Car session history

Setup Builder consumes:
- Active Event
- Active Car
- Driver profile
- Event race conditions
- Event tuning permissions

Strategy Builder consumes:
- Active Event
- Active Car
- Selected setup
- Practice telemetry
- Driver feedback

Practice Review consumes:
- Loaded session from History

History owns:
- Session loading
- Session filtering
- Previous session access

Live Race Engineer consumes:
- Active Event
- Selected strategy if manually loaded
- Live telemetry
- Active tyre compound

Settings owns:
- AI settings
- Voice settings
- PTT settings
- Telemetry connection settings
- Driver profile

## Superseded Requirements

Remove or do not rebuild:
- Dashboard tab unless redesigned later
- Session loader in Practice Review
- Car selector in Event Planner
- Car selector in Setup Builder
- Track selector in Setup Builder
- Race detail fields in Strategy Builder
- Fuel burn input in Strategy Builder
- Tyres in BoP tuning permissions

## Current Critical Defects

### P1-001 Telemetry Not Persisted
Per-frame telemetry is captured in memory but discarded after each lap.

Required:
Create TelemetrySample table and persist telemetry samples linked to session/lap.

### P1-002 Events and Setups Stored In config.json
Events and setups live in config.json with no relational integrity.

Required:
Move event, car, setup, session, strategy data into SQLite.

### P1-003 Missing DB Tables
Missing required tables:
- UserProfile
- EventProfile
- Car
- TelemetrySample

Required:
Create schema and migrations.

### P1-004 AI Context Incomplete
Driver feedback and previous AI recommendations are not passed into AI prompts.

Required:
AI calls must include driver feedback, previous recommendations, tuning permissions, event context, car, setup, and telemetry summary.

### P1-005 Session/Lap Integrity
Practice laps missing, duplicate lap risk exists, and practice mode recorded as race laps.

Required:
Fix lap saving, duplicate prevention, session type mapping, and history loading.

## Current High Priority Defects

- PTT button and voice status must be on Live Race Engineer, not only Settings.
- Fuel multiplier must not be treated as litres per lap.
- Pit window must recalculate dynamically.
- Car data exists in multiple locations and must be unified.
- Setup data exists in multiple locations and must be unified.
- Driver feedback form belongs in Practice Review, not Setup Builder.
- History loading must reliably load recent sessions.
- Session summary must recalculate after History loads a session.

## AI Rules

Every AI call must log to Debug and AIInteraction table:

- Feature name
- Timestamp
- Prompt
- Structured payload
- Response
- Model
- Token usage
- Estimated cost
- Duration
- Errors

AI must distinguish:
- Measured data
- Calculated data
- Inferred data
- Driver feedback

AI must not recommend locked setup changes.

If BoP is enabled and aero is not allowed, AI must not recommend aero changes.

## Tyre Rules

Available tyres and required tyres are selected in Event Planner.

Tyres are always changeable, including under BoP.

Tyres are not part of tuning permissions.

Required tyres must be a subset of available tyres.

Sports tyres must be supported everywhere Racing tyres are supported.

## Setup Builder Rules

Setup Builder must show as read-only:

- Active car
- Track
- Layout
- Race conditions
- BoP status
- Tuning permissions

Editable fields depend on Event tuning permissions.

Brake balance increments by 1.

Setup type must be:
- Race Setup
- Qualifying Setup

## Live Race Engineer Rules

Live Race Engineer is the first tab.

On app startup:
- No strategy is loaded by default.

PTT must work in:
- Practice
- Qualifying
- Race

PTT behaviour is already correct:
- Tap once
- Radio click
- Record approx. 2 seconds
- Radio click
- Process speech

Only improve immersion, do not change behaviour.

## Telemetry Priorities

Telemetry must support:

- Rev limiter events
- Gear usage
- Max speed
- World XYZ location
- Road surface if available
- Tyre radius if available
- Raw throttle
- Raw brake
- Brake lock detection
- Wheel spin detection
- Grip loss confidence
- Location-based issue grouping

## Gearbox Engineering Rules

AI gearbox advice must use telemetry evidence:

- Final gear usage on longest straight
- Rev limiter location and duration
- Max speed before braking zone
- Corner exit RPM
- Gear usage by corner
- Qualifying vs race setup type
- Slipstream risk
- Fuel saving requirements

AI must not give generic gearbox advice without telemetry context.

## Development Workflow

Claude must:

1. Read PROJECT_STATE.md.
2. Read MASTER_TESTING_REGISTER.md.
3. Never create duplicate defects.
4. Never remove defects without marking them Fixed.
5. Never add new features while P1 defects exist.
6. Update both documents after every coding task.
7. Reference defect IDs in commits and responses.

## Current Working Instruction For Claude

When working on this project:

1. Read this file first.
2. Read MASTER_TESTING_REGISTER.md second.
3. Only inspect files directly related to the active task.
4. Do not scan the whole repo unless asked.
5. Do not re-analyse architecture unless asked.
6. Provide a short plan before editing.
7. Make the smallest safe change.
8. Run relevant tests.
9. Update this file and MASTER_TESTING_REGISTER.md after changes.
10. Keep final response concise.