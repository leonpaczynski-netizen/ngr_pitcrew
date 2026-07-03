# Legacy Fan-Out Removal Phase 3 — Functional Gating / Validation Migration

> Author: Legacy Fan-Out Removal Phase 3 sprint · Date: 2026-07-03
> Branch: `legacy-fanout-removal-phase-3` (from `master` @ `4e6721b`)
>
> Companion docs: `docs/LEGACY_FANOUT_PHASE_1.md`, `docs/LEGACY_FANOUT_PHASE_2.md`,
> `docs/EVENT_CONTEXT_MIGRATION.md`, `docs/AI_SNAPSHOT_MIGRATION.md`.

---

## 1. Scope decision (product sign-off)

Phase 2 migrated the **display labels** to DB-first `EventContext` and left the
functional paths on the `config["strategy"]` fan-out pending sign-off. Phase 3
was scoped by an explicit product decision — **"flip reads only"**:

* **Migrated:** the two remaining functional fan-out consumers (setup-permission
  gating; DEF-P3-012 tuning validation) now read DB-first `EventContext`.
* **NOT done (deferred to Phase 4):** making `_on_event_save` re-sync (or
  retiring) the fan-out writer. Both fan-out writers remain, pinned by tests.

## 2. What was migrated

| Site | Before (fan-out) | After (EventContext) |
|---|---|---|
| `setup_builder._sync_setup_builder_from_event` gating inputs | `bool(sc.get("bop", evt.get("bop", False)))` / `bool(sc.get("tuning", evt.get("tuning", True)))` / `sc.get("allowed_tuning_categories", [])` | `ev_ctx.bop_enabled` / `ev_ctx.tuning_allowed` / `list(ev_ctx.allowed_tuning_categories)` → fed to the unchanged `_on_bop_toggled` + `_apply_setup_permissions` |
| `dashboard` DEF-P3-012 strategy-options validation | `not bool(_sc_strat.get("tuning", True))` / `_sc_strat.get("allowed_tuning_categories") or []` | `_ev_ctx.tuning_locked` / `list(_ev_ctx.allowed_tuning_categories)` → fed to the unchanged `validate_ai_setup_response` |

**Deliberately NOT migrated:** `_on_event_set_active`'s own
`_apply_setup_permissions(strat.get(...))` call — it sits *inside the writer*,
immediately after the fan-out is written from the UI widgets, so `strat` is
fresh by construction. Migrating it would change nothing; it stays with the
writer (pinned by test).

## 3. Behaviour

* **In-sync (normal) case** — right after "Set as Active", the DB event and the
  fan-out agree, so the gating/validation inputs are **byte-identical** to the
  old raw reads (tested field-by-field across unrestricted / BoP-on / fully
  locked / partially restricted combinations).
* **Diverged case** (event edited + Saved but **not** re-activated) — the
  signed-off behaviour change: **which setup fields are editable, and the
  tuning-rule validation, now follow the fresh DB truth** — consistent with the
  AI inputs (DB-first since the AI Snapshot Migration) and the Phase 2 labels.
  Before this sprint the labels said one thing while the lock state and
  validation enforced another; that inconsistency is what Phase 3 removes.

This completes **reader consistency**: AI inputs, display labels, functional
gating, and validation all resolve event truth the same way (DB-first
EventContext). The fan-out now exists only for its writers, the remaining
minor label fallbacks (refuel/req/avail on the setup tab), the car spinbox
rebind, `_get_mandatory_compounds`, the no-active-event branch, and the
context-builders' own legacy-bridge inputs.

## 4. What was intentionally NOT changed

* `_apply_setup_permissions` / `_on_bop_toggled` / `validate_ai_setup_response`
  **logic** — only their inputs moved.
* Both fan-out writers (`_on_event_set_active`; the Track Modelling combo) and
  `config["strategy"]` itself.
* No setup-recommendation logic, strategy calculation, track mapping, AI prompt
  wording, telemetry, PTT, voice, or tab order.

## 5. Tests

`tests/test_legacy_fanout_phase_3.py` (20) — in-sync byte-identity of the
gating trio and validation inputs vs the verbatim old expressions
(parametrized across lock/restriction combinations + empty-state defaults);
DB-first divergence (edited-not-reactivated flips gating and unlock state);
source-scans that the gating inputs and DEF-P3-012 read EventContext with no raw
`sc.get("bop"/"tuning"/"allowed_tuning_categories")` left in either site, that
the gating calls/logic are unchanged (`_apply_setup_permissions` body pinned),
and that the writer-internal permission call still reads the fresh `strat`;
writers + Home-first + config-guardrail invariants. Two Phase 2 pins updated in
place (`test_legacy_fanout_phase_2.py`) — the "gating still reads fan-out"
assertions became "gating calls intact" (the invariant that evolved with the
sign-off).

## 6. Next sprint recommendation

> **Executed (2026-07-03):** Phase 4 ran next — Save now re-syncs the fan-out
> for the active event (divergence eliminated), the last named readers were
> migrated, and writer retirement was investigated and deferred to Phase 5 with
> a concrete dependency list. See `docs/LEGACY_FANOUT_PHASE_4.md`.

**Legacy Fan-Out Removal Phase 4 — retire the divergence, then the fan-out:**

1. Make `_on_event_save` re-sync the fan-out when the saved event is the active
   event (config-only — no tracker/advisor side effects), so DB and
   `config["strategy"]` can no longer diverge; then
2. migrate the last minor readers (refuel/req/avail label fallbacks,
   `_get_mandatory_compounds`, car rebind), and
3. retire the Set-as-Active fan-out writer (keeping `config["strategy"]` only as
   the context-builders' input until a schema migration removes it).

Alternative smaller job: **wire the real UDP-listener connection signal into
`SessionContext`** so Home's `live_active` reflects the actual connection.
