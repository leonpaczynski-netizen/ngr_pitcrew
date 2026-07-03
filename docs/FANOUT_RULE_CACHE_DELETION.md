# Fan-Out Rule-Cache Deletion — the Event-Rule Cache Is Gone

> Author: Fan-Out Rule-Cache Deletion sprint · Date: 2026-07-04
> Branch: `fanout-rule-cache-deletion` (from `master` @ `8d7c500`)
>
> Companion docs: `docs/WORKING_RACE_CONFIG.md` (the reader half),
> `docs/LEGACY_FANOUT_PHASE_5.md` §4 (retirement map — items 3½/4),
> `docs/PRODUCT_CONSOLIDATION_AUDIT.md` (the original SSOT-1 finding).

---

## 1. What was deleted, and why it is invisible

The Product Consolidation audit's worst SSOT violation was "Set as Active"
fanning the event's RULES into `config["strategy"]` — a cache that could drift
from the DB. After Phases 1–6 made every consumer DB-first and Phase 4 made
drift impossible, the cache had **no remaining reader that fires in practice**.
This sprint deletes it (scoped by explicit product decision: "delete the rule
cache"; the full schema migration was declined as the highest-risk option).

`_fanout_event_to_strategy` no longer writes the **12 event-rule fields**:
`tyre_wear_multiplier`, `fuel_mult`, `mandatory_stops`, `weather`, `damage`,
`refuel_speed_lps`, `required_tyres`, `mandatory_compounds`, `avail_tyres`,
`bop`, `tuning`, `allowed_tuning_categories`.

**Why nothing changes (the invisibility proofs, all tested):**

* `EventContext` resolves every rule field **DB-event-first, per field**; the
  strategy fallback fires only when the event record's field is `None`. The DB
  record (and the `config["events"]` mirror that `_active_event()` falls back
  to without a DB) carries all rule fields — so EventContext's rules are
  **identical** whether the strategy dict holds fresh rules, stale rules, or
  none (proven field-by-field).
* The AI snapshots' CONTEXTS source takes everything from the contexts; the
  LEGACY_ONLY fallback fires only with **no active event** — a state in which
  the fan-out never ran, so the rule keys were absent before this change too
  (proven: identical frozen `race_params` with/without the legacy rule keys).
* The match-key hash reads only the **working-config core** (untouched;
  golden vectors green).
* Existing user configs keep their old rule keys as harmless, unread leftovers
  — the helper neither refreshes nor removes them (pinned).

## 2. What the fan-out now is

The helper writes only the **legitimate working-config core**: `track`,
`race_type`, `laps`/`total_laps`, `race_duration_minutes` (the match-key hash +
lap-bank restore inputs) and `event_id` (session tagging). With that, "the
fan-out" as the audit's SSOT violation **no longer exists** — what remains is
the working-race-config writer (named + typed by `data/working_race_config.py`)
plus plan-state persistence.

## 3. Touch-ups included

* **`_on_event_set_active`'s writer-internal permission call deleted** — it was
  redundant since Phase 3: `_sync_setup_builder_from_event()` (called at
  activation) applies permissions from the just-saved DB event via EventContext
  with identical values, and the call's cached bop/tuning/categories inputs no
  longer exist.
* **Driving-advisor fallback hardened** — `set_event_context(_evt_full or
  self._active_event() or strat)`: the no-DB path now goes through the
  `config["events"]` mirror (full rules) instead of the rules-less strategy
  dict.

## 4. Residual edge (documented, accepted at scoping)

A DB event row from a very old schema whose rule columns are `NULL` would make
EventContext fall back to the (now frozen-stale) leftover strategy keys instead
of freshly-cached ones. Mitigation: `_on_event_save` always writes full
records, so **any edit/re-save of the event heals the row**; and rows created
by any recent version carry all fields.

## 5. Tests

`tests/test_fanout_rule_cache_deletion.py` (16) — the shrunk helper on a widget
stub (core-only writes; plan state never touched; stale leftovers left alone);
the invisibility proofs (EventContext rules identical core-vs-stale-cache and
sourced from the DB event; the `config["events"]` mirror covers the no-DB
fallback; AI snapshot CONTEXTS `race_params` identical with/without legacy rule
keys; the match key unaffected); source-scans (no rule writes; the redundant
permission call gone; the advisor fallback hardened; activation side effects
intact); allowlist/golden-vector/Home/guardrail invariants.

**12 legacy pins updated in place** — the invariant evolved from "the fan-out
writes the rules (so downstream sees them)" to "the rules are NOT cached
(DB-only via EventContext); the working-config core IS written":
`test_group7_event_persistence` ×6 (+1 new core pin),
`test_group12a_bop_tuning_propagation` ×2, `test_group4_fixes` ×1,
`test_legacy_fanout_phase_1` writer pin, `test_legacy_fanout_phase_3` gating
pin (redundant-call deletion), `test_legacy_fanout_phase_4` helper stub test.

## 6. What remains on `config["strategy"]` (all legitimate, all allowlisted)

* The working-config core writer (+ the Track Modelling combo id writer).
* Plan-state persistence (`stops`, fuel, tolerances, `config_id`) — its durable
  home (retirement-map item 4's remainder) is the only piece left of the
  original map, and it is a schema-migration decision, not a correctness one.
* The context/AI **bridge inputs** (by design, last to change).
* Cosmetic car reads.

## 7. Next sprint recommendation

**Return to product work** — recommended: the consolidation series has reached
its goal (the audit's SSOT violation is deleted; everything else is guarded by
the allowlist + golden vectors). The deferred **OFR-1 between-race learning
loop** is the standing product item. The optional architectural tail is the
plan-state schema migration (item 4 remainder), best done only if/when a
feature needs it.
