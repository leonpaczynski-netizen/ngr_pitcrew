# Legacy Fan-Out Removal Phase 2 — Event-Rule Display-Label Migration

> Author: Legacy Fan-Out Removal Phase 2 sprint · Date: 2026-07-03
> Branch: `legacy-fanout-removal-phase-2` (from `master` @ `0ae591d`)
>
> **Phase 3 update (2026-07-03):** the functional gating + DEF-P3-012 validation
> described as "left on the fan-out" below were subsequently migrated to
> DB-first EventContext with product sign-off — see `docs/LEGACY_FANOUT_PHASE_3.md`.
>
> Companion docs: `docs/LEGACY_FANOUT_PHASE_1.md`,
> `docs/EVENT_CONTEXT_MIGRATION.md`, `docs/AI_SNAPSHOT_MIGRATION.md`,
> `docs/SESSION_CONTEXT_MIGRATION.md`.

---

## 1. Scope decision

Phase 1 deferred the event-rule display/validation consumers because reading
them from `EventContext` flips the precedence from **strategy-first**
(`config["strategy"]` fan-out) to **DB-event-first** — not byte-identical when
the two diverge. Phase 2 was scoped by an explicit product decision to
**display labels only**:

* **Migrated:** the on-screen event-context READOUT labels on the Strategy tab
  (`_sync_strategy_from_event`) and the Setup tab (`_sync_setup_builder_from_event`).
* **NOT migrated (left on `config["strategy"]`):** the functional paths —
  setup-permission gating (`_apply_setup_permissions`), the BoP toggle
  (`_on_bop_toggled`), and the spinbox rebind. So **which setup fields are
  editable is unchanged** by this sprint.

## 2. Why DB-first is the right source for these labels

`_on_event_save` writes event edits to the **DB** (and `config["events"]`) but
**not** to `config["strategy"]`; only `_on_event_set_active` writes the fan-out.
So after *editing an event and Saving without re-activating*, the DB event is
fresh and the fan-out is stale.

Crucially, the **strategy/setup AI already reads DB-first** (via `EventContext`,
since the AI Snapshot Migration — that's its documented "intentional
difference"). So before this sprint the AI used fresh DB values while the labels
*describing those inputs* showed stale fan-out values. Phase 2 makes the labels
**consistent with the AI inputs**. In the normal case (right after "Set as
Active", when DB and fan-out agree) the labels are unchanged.

## 3. Byte-identity guarantee (in-sync case)

All event multipliers/counts come from **`QSpinBox`** widgets → they are
**integers**. The migrated labels wrap `int()` around the `EventContext` float
fields so an in-sync `"2×"` stays `"2×"` (not `"2.0×"`). The Strategy tab's full
context line and the Setup tab's readout labels were verified byte-identical to
the previous output for an in-sync event/fan-out pair (see
`tests/test_legacy_fanout_phase_2.py`). `race_type` is safe because the DB stores
the combo text (`"Timed Race"`) and the fan-out the token (`"timed"`), and
`EventContext` normalises both to `"timed"`.

## 4. What changed

| Consumer | Migrated label reads | Left on `config["strategy"]` |
|---|---|---|
| `dashboard._sync_strategy_from_event` | `_lbl_strategy_event_ctx` context line: track, car, race length, `Wear`, `Fuel`, `Refuel` (int-wrapped); `_lbl_fuel_mult_display` | `_update_race_config()` (writer); `_get_mandatory_compounds()`; the no-active-event fallback branch |
| `setup_builder._sync_setup_builder_from_event` | `_lbl_setup_event_ctx` (track/car); `_lbl_rc_race_type` / `_race_length` / `_fuel_mult` / `_tyre_wear` / `_mand_pits` / `_weather` / `_damage`; `_lbl_rc_bop` / `_lbl_rc_tuning` (**labels**) | `_lbl_rc_refuel_rate`, `_lbl_rc_req_tyre`, `_lbl_rc_avail_tyres` (complex fallbacks); **functional** `_bop`/`_tuning`/`_cats` → `_on_bop_toggled` + `_apply_setup_permissions`; `_rebound_setup_spinboxes` |

Both methods now build one `ev_ctx = self._build_event_context()` and read the
migrated labels from it.

## 5. Behaviour change (documented + tested)

* **Normal case (in sync):** no visible change — labels byte-identical.
* **Edited-but-not-reactivated case:** the Strategy/Setup readout **labels** now
  show the fresh DB event values (matching the AI), instead of the stale fan-out
  values. The **editable fields / BoP gating do not change** (still fan-out).

This is the intended direction of the consolidation architecture (EventContext =
DB-first durable truth; `config["strategy"]` = legacy fan-out cache).

## 6. What was intentionally NOT changed

* No functional setup-permission / BoP / spinbox behaviour (the chosen scope).
* No setup-recommendation logic, strategy calculation, track mapping, AI prompt
  wording, telemetry, PTT, voice, or tab order.
* `config["strategy"]` and both fan-out writers (`_on_event_set_active`; Track
  Modelling combo) remain and are pinned by tests.
* The tuning/BoP AI-setup-response **validation** reads (`dashboard` ~L3970) were
  left on the fan-out — validation is functional, not display, so it stays out
  of the "display labels only" scope.

## 7. Tests

`tests/test_legacy_fanout_phase_2.py` (15) — in-sync byte-identity of the
migrated label VALUES (numeric int-preserved, string, bool, normalised
race_type) + integer-formatting guard (`"2×"` not `"2.0×"`); DB-first divergence
(edited-not-reactivated shows DB truth; car/track ids stay strategy-sourced);
source-scans that both sync methods build `EventContext` and read the labels from
it, that the **functional** gating still reads `config["strategy"]` and is fed
the sc-derived `_bop`/`_tuning`/`_cats`, that the writer is still called, and that
no raw wear/fuel strategy reads remain in the strategy label; plus the
Set-as-Active writer, Home-first, and config-guardrail invariants.

## 8. Next sprint recommendation

* **Phase 3 — functional gating (needs product sign-off):** migrate the setup
  permission/BoP inputs and the tuning/BoP AI-response validation to DB-first
  EventContext, explicitly accepting that it changes which fields are editable in
  the edited-not-reactivated case. Consider first making `_on_event_save`
  re-sync the fan-out (or dropping the fan-out) so DB and config can't diverge —
  which would also let the Set-as-Active fan-out finally be retired.
* Alternatively, **wire the real UDP-listener connection signal into
  `SessionContext`** (now a one-place change) so Home's `live_active` reflects
  the actual connection.
