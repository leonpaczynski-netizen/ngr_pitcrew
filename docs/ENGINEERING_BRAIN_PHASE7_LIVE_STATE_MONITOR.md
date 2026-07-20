# Engineering Brain — Phase 7: Live Engineering State Monitor & Session Development Ledger

**Status:** implemented on branch `eng-brain-phase7-live-state-monitor` (from `master` @ Phase 6 `abfa14b`).
**Schema:** **NO migration** — `DB_VERSION` stays **23**, `RULE_ENGINE_VERSION` stays `46.0`.
**Nature:** a READ-ONLY OBSERVER over the Phase 1–6 spine. It answers *"what is happening
to the car right now?"* — NOT *"what experiment should I run?"*. No generative AI, no
network, no auto-apply/revert, no setup authoring, no whole-app redesign, no new authority.

## 1. Problem solved

Phases 3–6 evaluate an experiment **after** a Review & Learn step. Between reviews the
driver has no continuously-updating picture of how each engineering issue is evolving lap
to lap. Phase 7 adds a live, deterministic **Engineering State Monitor**: per-issue
identity, confidence, recurrence, last-observed lap/corner, **trend** and **status**,
updated every comparable lap — plus an append-only **Session Development Ledger** that
records the deterministic timeline of engineering events (detected / status-changed /
trend-changed / resolved / regressed / protected-damaged / health-band-changed).

It **decides nothing**: it selects no experiment, scores no evidence, evaluates no lap,
authors no setup value, modifies no working window and changes no candidate ordering. It
consumes canonical outputs and classifies what they already show.

## 2. Starting checkpoint

`eng-brain-phase7-live-state-monitor` from `master` @ Phase 6 `abfa14b` (Phases 2–6
stacked; master remains at Phase 1). `DB_VERSION 23`, `RULE_ENGINE_VERSION 46.0`,
golden `config_id` vectors + frozen fan-out allowlist + Apply-gate predicate +
engine-wiring-status all unchanged.

## 3. Existing authorities reused (no duplication)

| Concern | Reused authority |
|---|---|
| Per-corner observation shape | Phase 4 `corner_evidence.CornerObservationRecord` / `from_issue_occurrence_row` |
| Recurrence classification | Phase 4 `corner_evidence.classify_recurrence` → `practice_pattern_analysis.RecurrenceThresholds` (the SINGLE recurrence authority — Phase 7 invents no second rule) |
| Comparable-lap window | Phase 4 `engineering_lap_validity.evaluate_session_laps` (`LapPurpose.PRACTICE_PATTERN`) — the observer trusts this, it never re-judges laps |
| Issue identity (display-text-free) | Phase 6 `engineering_issue.EngineeringIssueIdentity` / `issue_family_for` |
| Persisted evidence store | existing `corner_issue_occurrences` (session-keyed, per-lap) — **read only** |

Phase 7 adds **no** competing telemetry table and **no** second recurrence/identity model.

## 4. New modules (all pure: Qt-free, DB-free, UI-free, network-free, AI-free, never raise, no clock/random)

- **`strategy/state_transitions.py`** — the documented Trend + IssueStatus rules.
  - `Trend`: `IMPROVING / UNCHANGED / WORSENING / FLUCTUATING / INSUFFICIENT_EVIDENCE`.
  - `IssueStatus`: `UNKNOWN / NEW / ACTIVE / RECOVERING / STABLE / RESOLVED / PROTECTED / DAMAGED`.
  - `detect_trend(affected)` — window-fraction comparison over **valid laps only**, with a
    minimum-lap gate, a jitter (FLUCTUATING) gate, and a **≥2-lap support rule** so a single
    exceptional lap can never flip a trend (IMPROVING needs ≥2 recent *clear* laps; WORSENING
    needs ≥2 recent *affected* laps).
  - `next_status(...)` — deterministic recovery path `UNKNOWN→NEW→ACTIVE→RECOVERING→STABLE→RESOLVED`,
    regression path (re-appearance → ACTIVE/NEW), protected path `PROTECTED→DAMAGED→ACTIVE`.
- **`strategy/live_engineering_state.py`** — the live fold.
  - `LiveIssueState` (identity, status, trend, recurrence class, confidence, present-now,
    first/last observed lap, last observed corner, affected-lap numbers, `ConsistencyMeasures`, severity).
  - `ConsistencyMeasures` — **engineering** repeatability numbers (recurrence ratio, lap-to-lap
    repeatability), explicitly NOT driver ratings.
  - `SessionHealth` + `SessionHealthBand` (`NOMINAL / SETTLING / DEVELOPING / DEGRADING / UNKNOWN`).
  - `LiveEngineeringState` with a time-independent `content_fingerprint`.
  - `update_live_state(records, valid_lap_numbers, …)` — a pure deterministic fold; excluded
    (kerb/airborne/noise) events and non-comparable laps never count; **order-independent**.
- **`strategy/session_development.py`** — the append-only ledger.
  - `LedgerEvent` (positional `sequence_no`, never a timestamp), `LedgerEventType`,
    `SessionDevelopmentLedger` (immutable; `append_snapshot` returns a NEW ledger, never mutates).
  - `build_session_ledger(snapshots)` folds a `(lap, LiveEngineeringState)` sequence and is
    **byte-for-byte equal** to appending snapshots one at a time — the append-only + determinism contract.

## 5. Orchestrator (SessionDB, read-only, no persistence)

`SessionDB.build_live_engineering_state(session_id, *, car_id, track, layout_id,
scope_fingerprint, discipline, protected_keys)`:

1. Resolve physical scope (car/track) from the session when not supplied.
2. Read `corner_issue_occurrences` for the scope, restricted to this session (**read only**).
3. Compute the comparable-lap window via the Phase-4 lap-validity authority.
4. Fold the current `LiveEngineeringState` over the full window.
5. Build the `SessionDevelopmentLedger` by folding one snapshot per growing valid-lap prefix
   (a lap only ever appends events).

It **writes nothing** and is **regenerable**: the live state and ledger are a pure function
of already-persisted rows, so a restart rebuild yields identical `content_fingerprint`s.
This is exactly why **no migration is required**.

## 6. UI (read-only visualisation — NO Apply / setup-authoring controls)

- `ui/live_engineering_vm.py` — pure Qt-free view-model: health-banner rows, active/resolved/
  protected issue tables, a per-lap **trend sparkline** (`▇` present / `·` clear), and the
  development-timeline rows.
- `ui/live_engineering_monitor.py` — self-contained `LiveEngineeringMonitor` widget rendering
  the VM. It has a health banner, Session Health grid, Active Issues (with sparkline), Resolved,
  Protected Behaviour and an append-only Development Timeline. There are **no Apply / Save /
  Revert buttons** — asserted by test. `dashboard.py` (the god-file) is left untouched.

## 7. Determinism & purity verification

- `state_transitions`, `live_engineering_state`, `session_development`, `live_engineering_vm`
  are all pure (no `random`, no wall-clock, no sqlite/Qt/network imports — asserted by tests).
- Live recompute == from-scratch restart: identical live-state and ledger fingerprints
  (`test_phase7_orchestrator.test_restart_determinism`).
- Append == rebuild for the ledger (`test_phase7_ledger.test_append_equals_rebuild`).
- Order-independence: reordering records / occurrence-insertion order does not change the
  state (`test_metamorphic_insertion_order_invariant`, `test_order_independent_fingerprint`).
- Single-lap guarantee: one exceptional lap never flips a trend, both directions.

## 8. Schema / contract changes

**None.** No migration. `DB_VERSION 23`, `RULE_ENGINE_VERSION 46.0`. No new table (asserted:
no `live_engineering*` / `development_ledger*` table; the corner-telemetry table set is
unchanged). Golden `config_id`, frozen fan-out allowlist, Apply-gate predicate and
engine-wiring-status untouched.

## 9. Tests

`tests/test_phase7_state_transitions.py`, `tests/test_phase7_live_state.py`,
`tests/test_phase7_ledger.py`, `tests/test_phase7_orchestrator.py`,
`tests/test_phase7_view_model.py` (55 non-UI) + `tests/test_phase7_ui_construction.py`
(3 UI — run individually per the Windows/PyQt teardown-segfault caveat).

## 10. Known limitations / deferred

- **Protected-behaviour seeding**: `protected_keys` is an accepted input but is not yet
  auto-derived from accepted-checkpoint protected behaviours; callers pass it explicitly.
  Deferred to a Phase-6/7 bridge.
- **Live wiring into a running Practice session**: the monitor + orchestrator are complete and
  tested; hooking `LiveEngineeringMonitor.update_result` to the live-session per-lap tick inside
  `dashboard.py` is deliberately left as a small, separate integration step (the god-file is
  untouched here to avoid the known teardown-segfault surface).
- **Trend thresholds** (`MIN_TREND_LAPS=3`, `TREND_DELTA=0.20`, `RESOLVE_CLEAR_LAPS=3`) are
  fixed constants; per-discipline tuning is deferred.

## 11. Recommended Phase 8

**Live in-session wiring + cross-session development history**: drive `update_live_state`
from the live per-lap tick (off-thread, mirroring the Phase-6 review worker), persist an
append-only development-ledger snapshot per session for cross-session comparison, and derive
`protected_keys` from accepted-checkpoint protected behaviours — still a pure observer, still
no auto-apply.
