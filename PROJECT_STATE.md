# GT7 Pit Crew Project State

## Current Mode
Architecture Stabilisation Mode.

Do not add new features until core data flow, persistence, telemetry storage, and AI context are stable.

## Repository / Build Status (2026-07-02)

- **Full test suite:** 3813 pass / 6 skip / 0 fail (6 skips require a Qt display).
- **Git:** branch `feature/car-setup-ranges-engineer-prompt` merged (fast-forward) into `master` and pushed to the remote **https://github.com/leonpaczynski-netizen/ngr_pitcrew** (`origin/master`). Latest commit `1dea1e3` (Groups 37/37b/38).
- **Secrets:** `api_key.txt` and `config.json` are gitignored — not tracked, not pushed.
- **Recent work (documented in MASTER_TESTING_REGISTER.md):** Groups 26–38 + lettered Groups A/B/C/D/E + Qualifying Mode — setup-advice overhaul, per-car range enforcement, shift-beep, feasibility-gated race strategy, mid-race AI re-plan + qualifying engineer, and relative-compound tyre degradation.
- **Detailed session notes** for Groups 17P–25 live in `docs/CURRENT_CLAUDE_HANDOFF.md`.

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