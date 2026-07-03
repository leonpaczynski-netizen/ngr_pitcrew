# Legacy Fan-Out Removal Phase 4 — Divergence Elimination + Last Readers

> Author: Legacy Fan-Out Removal Phase 4 sprint · Date: 2026-07-03
> Branch: `legacy-fanout-removal-phase-4` (from `master` @ `e356879`)
>
> Companion docs: `docs/LEGACY_FANOUT_PHASE_1.md` / `_2.md` / `_3.md`,
> `docs/EVENT_CONTEXT_MIGRATION.md`.

---

## 1. Goal

Phases 1–3 made every event-truth **reader** DB-first (AI inputs, display
labels, functional gating, validation). What remained was the **divergence
itself**: `_on_event_save` writes event edits to the DB but not to the
`config["strategy"]` fan-out, so the fan-out went stale until the next
"Set as Active". Phase 4:

1. **eliminates the divergence** — Save now re-syncs the fan-out when the saved
   event is the active event;
2. **migrates the last minor readers** named by Phase 3
   (refuel/req/avail labels, car rebind, `_get_mandatory_compounds`);
3. **documents why writer retirement is deferred** (§5) rather than forcing it.

## 2. Re-sync on Save (`ui/dashboard.py`)

* **`_fanout_event_to_strategy(evt_name)` (NEW)** — the Set-as-Active fan-out
  block, extracted **verbatim**. Writes the event-RULE fields (track, race
  type/length, wear/fuel multipliers, stops, weather, damage, refuel rate,
  required/available tyres + the `mandatory_compounds` names string, BoP,
  tuning, allowed categories, event_id) from the Event Planner widgets into
  `config["strategy"]` and returns it. **Config-dict only**: no tracker /
  driving-advisor / query-listener / UI-sync side effects and no persist
  (callers own those). Strategy-PLAN fields (`car`, `config_id`, `stops`,
  fuel/tolerances) are never touched.
* **`_on_event_set_active`** — unchanged behaviour: calls `_on_event_save()`,
  then the helper, then all its activation side effects (tracker race config,
  advisor context, permission apply, tab syncs, persist, …) exactly as before.
* **`_on_event_save`** — after upserting the DB record and mirroring
  `config["events"]`, and **only when the saved event IS the active event**
  (`name == config["active_event_id"]`), it calls the helper before its
  existing `_persist_config()`. Saving a non-active event changes nothing.

**Result:** the DB event record and the fan-out can no longer diverge. The
DB-first readers (Phases 2–3) are unaffected; the *remaining* fan-out readers
(live-session open, BoP/degradation checks, `_compute_race_config_id` inputs)
now also see fresh values after a Save. The derived `config_id` still refreshes
on the next strategy-tab sync (`_update_race_config`) — same timing as before.

**Deliberate limitation (documented):** the re-sync is config-only. The
tracker's race type/duration and the driving-advisor context still update only
on "Set as Active" — unchanged from previous behaviour, where a Save updated
them never.

## 3. Last readers migrated

| Site | Before | After |
|---|---|---|
| `dashboard._get_mandatory_compounds` | parse `config["strategy"]["mandatory_compounds"]` (a names string) | map `EventContext.required_tyres` codes → display names via `data.tyres.get_by_code` — the **same mapping the fan-out writer used to build that string**, so byte-identical in sync |
| `setup_builder` refuel label | `f"{sc.get('refuel_speed_lps', 10)} L/s"` | `f"{int(ev_ctx.refuel_rate_lps)} L/s"` (int keeps the QSpinBox formatting) |
| `setup_builder` required/available tyre labels | `", ".join(sc.get(...))` (+ names-string fallback) | `", ".join(ev_ctx.required_tyres / .available_tyres)` (same codes) |
| `setup_builder` car spinbox rebind | `sc.get("car", "") or ""` | `ev_ctx.car or ""` (byte-identical — Phase 1 proof) |

With these, **`_sync_setup_builder_from_event` no longer reads
`config["strategy"]` at all** (the dead `sc` variable was removed).

## 4. Behaviour summary

* **In-sync case:** everything byte-identical (helper extracted verbatim;
  reader migrations proven field-by-field and via the shared name mapping).
* **Edit-active-event + Save (no re-activate):** previously the fan-out stayed
  stale; now it mirrors the DB immediately. All readers — DB-first *and*
  legacy — agree from the moment of Save.

## 5. Writer retirement — investigated and deferred (Phase 5)

Retiring the Set-as-Active fan-out writer now would **break the app**:

* `car`, `config_id`, and the stint plan (`stops`) live **only** in
  `config["strategy"]` — the events table stores none of them; the canonical
  contexts read them *from* the fan-out as their input source.
* ~25 readers still consume fan-out fields directly (live-session open in
  `_on_live_mode_changed`, BoP checks (~L5400), degradation params (~L5525),
  `_compute_race_config_id` (hash — must stay byte-stable), race-config
  restore paths, garage/practice car reads, AI-snapshot legacy bridges).

With re-sync in place the fan-out **can no longer go stale**, so the writer is
now harmless plumbing. Retirement becomes a mechanical Phase 5: give `car` /
`config_id` / plan state a durable home (DB or the contexts), migrate the
remaining ~25 reads, then delete the writer and the compatibility dict.

## 6. What was intentionally NOT changed

* Activation side effects (tracker push, advisor context, syncs) stay exclusive
  to "Set as Active".
* The Track Modelling combo writer, `_compute_race_config_id`, all strategy-plan
  writers/readers, and the context-builders' bridge inputs.
* No setup logic, strategy calculation, track mapping, AI prompt, telemetry,
  PTT, voice, or tab-order change.

## 7. Tests

`tests/test_legacy_fanout_phase_4.py` (18) — the real `_fanout_event_to_strategy`
bound to a widget stub (writes all rule fields incl. the compounds names string;
never touches car/config_id/stops/fuel; returns the live config dict; no
persist/sync side effects; race-type normalisation both ways); save-path
source-scans (guarded call before persist; save stays config-only — no
tracker/advisor/listener/sync calls; Set-as-Active keeps its side effects; no
inline fan-out left in Set-as-Active); reader migrations (mandatory compounds
byte-identity vs the old string-parse via the shared name mapping; refuel/req/
avail/car label equivalence; `_sync_setup_builder_from_event` reads no
`config["strategy"]`); Track-Modelling writer + Home-first + config-guardrail
invariants. **11 legacy pins updated in place** (same invariants, new home:
`test_group7_event_persistence` ×7, `test_group12a_bop_tuning_propagation` ×3,
`test_group4_fixes` ×1, plus the Phase 1/2/3 writer pins).

## 8. Next sprint recommendation

**Legacy Fan-Out Removal Phase 5 — retire the writer** (per §5: re-home
`car`/`config_id`/plan state, migrate the remaining ~25 reads, delete the
fan-out), or the standing smaller job: **wire the real UDP-listener connection
signal into `SessionContext`** so Home's `live_active` reflects the actual
connection.
