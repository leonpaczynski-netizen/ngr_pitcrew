# Engineering Brain — Phases 57–59 Pre-Phase Audits & Corrections

Performed at `eng-brain-phase54-56-live-operational-certification @ 00111b4` before Phase 57. Additive —
no earlier commit amended.

## Checkpoint (verified)

Branch `…phase54-56… @ 00111b4`; master `3d7c6af`; not pushed / no PR / not merged. `DB_VERSION == 28`,
`RULE_ENGINE_VERSION == "46.0"`. All 11 Phase 54–56 commits present; 112 targeted tests pass; broad
regression green; certification below visual/live/operational (`current_slice_certification()` =
`NOT_TESTED`); Apply + voice gates unchanged.

## Audit A — Phase 54–56 file counts (correction)

`git diff --name-status da9d6db..00111b4` is authoritative:

| Class | Count |
| --- | --- |
| Added (A) | **24** |
| Modified (M) | **6** |
| Deleted (D) | **0** |
| **Total** | **30** |
| Insertions | **+2,761** |
| Deletions | **−10** |

The headline (24/6/0) was correct; the completion-report **narrative was wrong** — it said "9 strategy +
2 UI + 11 tests + 4 docs = 26". The correct added breakdown is **6 strategy + 2 UI + 11 tests + 5 docs =
24**:

- **Strategy (6):** `canonical_activity_state.py`, `setup_strategy_readiness.py` (P54);
  `live_activity_bridge.py`, `live_bridge_views.py`, `live_session_detection.py` (P55);
  `event_programme_certification.py` (P56). *(Not 9.)*
- **UI (2):** `certification_panel.py`, `certification_vm.py`.
- **Tests (11):** phase54_canonical_truth, phase54_truth_db, phase54_lock_strategy_readiness,
  phase54_next_action_truth, phase55_bridge_match, phase55_bridge_views, phase55_session_end,
  phase56_certification, phase56_certification_ui, phase54_56_golden, phase54_56_safety.
- **Docs (5):** PHASE54_56_PREPHASE_AUDITS, PHASE54_CANONICAL_ACTIVITY_TRUTH,
  PHASE55_LIVE_GT7_ACTIVITY_BRIDGE, PHASE56_OPERATIONAL_CERTIFICATION, UAT_ENGINEERING_BRAIN_PHASE54_56.
  *(Not 4.)*
- **Modified (6):** `data/session_db.py`, `ui/development_history_page.py` (2 source);
  `MASTER_TESTING_REGISTER.md`, `docs/CURRENT_CLAUDE_HANDOFF.md`, `docs/PROJECT_STATE.md`,
  `docs/UAT_ENGINEERING_BRAIN_PHASE51_53.md` (4 doc/register).

The handoff + register are corrected accordingly.

## Audit B — Active-event selection ownership (authoritative design)

**Decision:** the active-event selection is **operational navigation state persisted through the existing
safe operational-settings authority** (`config_paths.save_config` — atomic `<name>.tmp` + `os.replace`,
with backup), keyed `config["active_cycle_id"]`. It is NOT a new semantic event authority.

- **Storage owner:** the operational `config.json` (`active_cycle_id`), written only via
  `config_paths.save_config`.
- **Lifetime:** persists across application restart (predictable for a multi-week preparation cycle).
- **Restart behaviour:** on startup the stored id is read and passed to `resolve_active_cycle`; it is
  honoured only if it matches a *non-terminal* candidate, else the resolver falls through safely.
- **Write boundary:** written ONLY on explicit user selection (`_cc_select_active_cycle`); NEVER on Home
  refresh, live UI refresh, or a telemetry packet.
- **Fallback:** a deleted / completed / paused / missing selected cycle → the resolver returns
  `EVENT_REQUIRES_SELECTION` (several active), `ONE_ACTIVE_EVENT` (one), or `NO_ACTIVE_EVENT` (none) — no
  silent bad state.
- **Semantic isolation:** the selection never enters an engineering fingerprint (candidate-membership
  fingerprint is identical whether or not one is selected).
- **Test isolation:** tests use an isolated temp config path; the session-autouse `_guard_real_config`
  fixture fails the run on any real-config mutation; the real config SHA-256 is asserted unchanged.

Phase 57 wires explicit selection to persist through `save_config` (previously in-memory only).

## Audit C — Evidence-category wording (correction)

The Phase 54–56 docs described the live-bridge tests as "replay-via-snapshots". This is **incorrect**:
those tests construct a **static `LiveActivityRuntimeSnapshot` directly** and never pass through the
`strategy/telemetry_replay.py` timeline. The categories are now used strictly and distinctly:

- **static runtime-snapshot test** — a `LiveActivityRuntimeSnapshot` (or `TrackerRuntimeSnapshot`)
  constructed directly and classified. Awards at most `AUTOMATED_ONLY`.
- **deterministic telemetry replay** — evidence produced by driving frames through
  `strategy/telemetry_replay.py`. Awards at most `REPLAY_VALIDATED`. (Phase 57 adds real replay-through-
  the-timeline tests for the runtime adapter to legitimately claim this.)
- **offscreen Qt test** — `QT_QPA_PLATFORM=offscreen` panel construction. Awards at most
  `OFFSCREEN_VALIDATED`; never visual.
- **manual visual UAT** — a human viewing the rendered UI. Awards `VISUAL_UAT_*`.
- **live GT7 telemetry UAT** — a real GT7 feed driving the runtime. Awards `LIVE_GT7_*`.
- **physical audio / voice UAT** — a human hearing spoken advisories through the SAPI5 adapter.

The Phase 54–56 certification (`current_slice_certification`) claimed no REPLAY evidence — it used
AUTOMATED for domain and OFFSCREEN for UI. Corrected the one doc table that mislabelled it.

## Audit D — Runtime-file integrity

Runtime/app-state files present at the checkpoint, recorded (SHA-256 prefix) and left **unstaged /
uncommitted**; the slice must not modify them:

| File | Status at checkpoint | SHA-256 (prefix) |
| --- | --- | --- |
| `active_setup_state.json` | untracked | `e84aeb9a35d875af` |
| `data/setup_history.json` | modified (pre-existing) | `91ed583eb5b7c5ea` |
| `.claude/settings.local.json` | modified (pre-existing) | `a71b52a73a890a48` |
| `data/track_models/…full_course.accepted_model.json` | modified (pre-existing) | (tracked) |
| `data/track_library/…`, `data/track_models/_refine_pending/`, candidate/ledger files | untracked | (runtime) |

These reflect prior GT7 usage, not this slice. Re-verified untouched in the completion report. Tests use
`SessionDB(":memory:")` / `tmp_path` and the config-safety fixtures — no real runtime/config file is
written.
