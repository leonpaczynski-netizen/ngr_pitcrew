# Live Activation 3 — Preflight Audit (2026-08-02)

Race activation + race-day certification foundation. Branch
`live-activation-3-race-certification` off clean `master @ 607fdc6`.

## Verified starting position

| Check | Expected | Verified |
|-------|----------|----------|
| Branch / base commit | `master @ 607fdc6` | ✓ `607fdc6` (PR #106 merge) |
| `DB_VERSION` | 40 | ✓ `strategy/_setup_constants.py:160` |
| `RULE_ENGINE_VERSION` | "46.0" | ✓ `strategy/_setup_constants.py:79` |
| Live Activation 1 (Practice) | present (PR #105) | ✓ `decec1a` + modules present |
| Live Activation 2 (Qualifying) | present (PR #106) | ✓ `0557bb7`/`d64dc21`/`0a0602a` + modules present |
| Canonical event/session/run spine | present | ✓ `data/engineering_context_key.py`, session-run wiring |
| Working tree | clean bar local runtime | `.claude/settings.local.json` (local), untracked `after.txt` (stray dump — left untouched) |

No migration is introduced in this phase (additive files only; `DB_VERSION`/`RULE_ENGINE_VERSION`
unchanged).

## Audit finding — what exists vs what Activation 3 adds

Practice and Qualifying each have a **coordinator + activation gate + domain phase machine + DB
port + bridge driver + diagnostics**. **Race had no recording coordinator** — only the *advisory*
strategy/pit-wall surface (`canonical_live_race_state` → adaptive strategy → replan →
`ngr_live_pit_wall`), which lights up when `_live_session_mode == "race"` but never opens an
authoritative `session_run`, never gates identity, and never persists laps against a run.

Activation 3 therefore **extends, not rebuilds**:

- **Reused unchanged:** the generic recording FSM (`LiveRunState` in
  `strategy/live_practice_activation.py`), the lap guard (`evaluate_live_lap`), reconnect
  (`resolve_reconnect`), event-switch guard, the session-type-agnostic DB port
  (`ui/live_practice_db_port.py`), the canonical race-state pipeline (`RacePhase`,
  `canonical_live_race_state`, `PitPhase`, `RaceType`), the deterministic replan pipeline
  (`race_strategy_replan` / `race_strategy_live_replan`, advisory-only), the pit wall
  (`ngr_live_pit_wall`), and the voice/PTT stack.
- **Added (new modules):**
  - `strategy/live_practice_activation.py` — `RACE` constant, `resolve_live_race_activation`
    wrapper, and `validate_race_plan_context` (race-plan/identity coherence guard).
  - `strategy/race_engineer_state_machine.py` — the race engineer phase machine (waiting →
    race-start → racing → pit-entry/in-pit/pit-exit → finished) + cue, driven from the EXISTING
    `RacePhase`/`PitPhase` vocabulary via `events_from_race_signals` (no second physical machine).
  - `strategy/live_race_runtime.py` — `LiveRaceCoordinator` (clone of the qualifying coordinator).
  - Bridge race driver, race diagnostics, post-session integrity audit, race voice/PTT, and the
    guided certification workflow + report export (subsequent commits).

## Architectural invariants preserved

Deterministic, offline, advisory-only. No live AI/network in the decision path. No auto pit call,
no auto tyre/fuel/setup change, no setup Apply on Live Race. Unknown evidence is never treated as
safe (the replan pipeline already returns `INSUFFICIENT_EVIDENCE`; the race-plan guard treats
unknown-live-vs-known-plan as a MISMATCH). PTT stays a bounded vocabulary. Tests use isolated
temp paths and never mutate user runtime data.
