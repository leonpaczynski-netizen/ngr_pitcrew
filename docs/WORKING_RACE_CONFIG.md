# Working Race Config Read Model — Retirement-Map Item 3 (Readers)

> Author: Working Race Config Read Model sprint · Date: 2026-07-04
> Branch: `working-race-config` (from `master` @ `7f4a95a`)
>
> Companion docs: `docs/LEGACY_FANOUT_PHASE_5.md` §4 (retirement map),
> `docs/LEGACY_FANOUT_PHASE_6B.md` (the analysis this implements).

---

## 1. Scope decision

Item 3 ("restore-writer redesign") was scoped by explicit product decision to
its **reader half**: introduce the named read model and migrate the remaining
working-config readers through it. The **writer half** (writers write a typed
first-class object; the dict becomes derived) is deliberately deferred — it
rewires activation/restore/garage flows and persistence in one step and belongs
with item 4 (a durable working-config home).

## 2. The model — `data/working_race_config.py` (NEW, pure)

`WorkingRaceConfig` (frozen): `track`, `car`, `race_type` (raw token — only
exactly `"timed"` is timed), `total_laps` (default **25**), `race_duration_minutes`
(default **60** — the hash's own absent-key defaults, deliberately distinct from
EventContext's 0 defaults), `config_id` (the stored match key).

* `from_strategy()` — verbatim legacy reads; never raises. One intentional
  hardening (documented + tested): non-numeric lengths coerce to the field
  default instead of propagating `ValueError` out of the hash.
* **It now owns the match-key algorithm**: `length_key` (`t<min>`/`l<laps>`),
  `hash_raw` (`f"{track}|{car}|{length_key}"`), `compute_config_id()`
  (`sha256[:10]`) — all frozen by the Phase 6b golden vectors, which still
  exercise the REAL dashboard method end-to-end through the new delegation.
* `length_text()` — the Strategy tab's `"30 min"` / `"12 laps"` display detail.

Semantics (per the 6b analysis): the working config *usually* mirrors the
active event (post-Phase-4, never silently drifts), but during a lap-bank
restore it deliberately holds a historical session's race config so the match
key follows the restored session — the reason this concept exists separately
from EventContext.

## 3. Migrated readers (`ui/dashboard.py`)

New `_working_race_config()` builder — the **single bridge read** of the legacy
dict for this concept. Then:

| Consumer | Before | After |
|---|---|---|
| `_compute_race_config_id` | inline dict reads + inline hash | delegates to `wrc.compute_config_id()` (golden vectors green through the full path) |
| `_update_race_config` | dict reads for the label + `race_configs` snapshot | `wrc` fields + `wrc.length_text()`; the `config_id` **write** (setdefault) stays — it's the writer |
| `_sync_strategy_from_event` no-event checks | `sc.get("track")` / `sc.get("car")` | `wrc.track` / `wrc.car` (identical falsiness) |
| `_save_session_to_db` session tagging | `strat.get("car"/"track"/"config_id")` | `wrc.car` / `wrc.track` / `wrc.config_id` (a saved session must be tagged with what it actually ran under — incl. a restored config) |

**Allowlist movement** (`FROZEN_ALLOWLIST`, consciously updated):
`_compute_race_config_id` (1) / `_sync_strategy_from_event` (1) /
`_save_session_to_db` (1) removed; `_update_race_config` 2→1 (write only);
`_working_race_config` (1, bridge) added. Net −3 direct readers.

## 4. What was intentionally NOT changed

* All working-config **writers** (`_fanout_event_to_strategy`,
  `_load_session_config`, garage car select, `_update_race_config`'s
  `config_id`/`race_configs` writes) and the plan-state writers — the second
  half of item 3, with item 4.
* The match-key **values** — byte-identical (golden vectors); the 6b
  source-level pins moved with the algorithm to the model (same invariant, new
  home).
* No behaviour change anywhere: labels, snapshots, session tagging, and the
  no-event checks produce identical output.

## 5. Tests

`tests/test_working_race_config.py` (25) — `from_strategy` verbatim + the 25/60
absent-key defaults + None-safety + the documented garbage-coercion hardening +
immutability; `length_key`/`hash_raw`/`compute_config_id` against the golden
vectors directly on the model; unknown race-type hashes as lap; `length_text`;
schema/purity; source-scans for all four migrated consumers (incl. the
config_id write remaining in `_update_race_config`); writers-untouched pins;
allowlist/Home-first/guardrail invariants. `tests/test_race_config_id_hash.py`
updated in place — the `_bind` stub binds the real builder too (vectors exercise
the full delegated path), and the source-level algorithm pin points at the
model (same invariant, new home). `FROZEN_ALLOWLIST` reshaped in the same
commit.

## 6. Next sprint recommendation

* **Item 3 writer-half + item 4** — writers write the typed `WorkingRaceConfig`
  (or a successor store), the dict's event-rule fields become derived
  compatibility, and plan-state gets a durable home — the actual fan-out
  deletion, now guarded end-to-end by golden vectors + the frozen allowlist.
* Or **product work** (deferred OFR-1 between-race learning loop) — the reader
  side of the entire consolidation is now complete.
