# Legacy Fan-Out Removal Phase 5 — Functional Readers + Frozen Allowlist Guard

> Author: Legacy Fan-Out Removal Phase 5 sprint · Date: 2026-07-03
> Branch: `legacy-fanout-removal-phase-5` (from `master` @ `b58545e`)
>
> Companion docs: `docs/LEGACY_FANOUT_PHASE_1.md` … `_4.md`,
> `docs/EVENT_CONTEXT_MIGRATION.md`.

---

## 1. Scope decision

The Phase 4 plan's step 3 ("retire the Set-as-Active writer") was re-audited at
the start of this sprint and found **blocked** (§4 below). The product decision
for Phase 5 was **"Functional + guard"**:

* migrate the remaining **functional** event-rule readers to the canonical
  contexts (no product decision reads the legacy dict any more);
* add a **frozen allowlist** source-scan test pinning every remaining
  `config["strategy"]` access site, so no new consumer can creep in and no site
  can be removed without a conscious allowlist update;
* write the definitive **Phase 6 retirement map** (§4).

Cosmetic label/car reads and the blocked core stay put. Since Phase 4's re-sync
the fan-out can never go stale, so the remaining reads are always fresh — the
value of migrating them is architecture hygiene, and the risk/benefit was judged
against each site.

## 2. Functional readers migrated (byte-identical in sync, tested)

| Site | Before (fan-out) | After (canonical) |
|---|---|---|
| `dashboard._on_live_mode_changed` — live-session open tagging | `strat.get("track"/"car"/"config_id")`, `int(strat.get("event_id", 0))` | `EventContext.track/.car`, `_active_config_id()` (StrategyContext), `int(ev_ctx.event_id or 0)` |
| `dashboard` degradation params | `float(sc.get("tyre_wear_multiplier", 1.0))`, `int(sc.get("degradation_consecutive_laps", 2))` | `EventContext.tyre_wear_multiplier`, `StrategyContext.degradation_consecutive_laps` (read on the UI thread before the worker spawns, as before) |
| `dashboard._get_bop_data_for_car` + the reload-BoP gate | `sc.get("bop")`, `sc.get("car")` | `EventContext.bop_enabled` / `.car` |
| `setup_builder._current_setup_dict` — event-identity fields | `sc.get("car"/"track"/"weather"/"bop")` | one `_ev_ctx = self._build_event_context()` (car with the `or "Unknown Car"` fallback preserved; weather feeding the same condition map; `bop_enabled`) |
| `setup_builder` setup-save `event_id` | `int(sc.get("event_id", 0))` | `int(self._build_event_context().event_id or 0)` |

Thread-safety note: `_current_setup_dict` is also the voice query listener's
setup getter (may run off the UI thread). Building an EventContext there does a
`SessionDB.get_event` read — safe: the connection is `check_same_thread=False`
with an internal lock, and voice queries are seconds-scale, not per-packet.

## 3. The frozen allowlist

`tests/test_legacy_fanout_phase_5.py::FROZEN_ALLOWLIST` pins all **41 remaining
access sites** across 40 `(file, method)` entries (dashboard 29, setup_builder
14 across 9 methods, track_modelling 3, main.py 2). The scan maps every
`get("strategy"` / `setdefault("strategy"` occurrence to its enclosing method
and requires **exact equality**: a new consumer fails loudly with a pointer to
the contexts; a silent removal fails too (shrink the allowlist in the same
commit). Classifications (writer / bridge / hash / plan state / restore /
cosmetic / telemetry-path) are annotated inline on each entry.

## 4. Phase 6 retirement map — why the writer stays (for now)

Deleting the Set-as-Active fan-out writer requires all of the following first:

1. **Telemetry-path reads** (`main.py` `_dispatch`, 2 sites) — per-lap DB
   tagging (`event_id`) and the fallback race-session open (track / car /
   config_id / event_id). These run in the telemetry event pipeline on the
   dispatcher (not MainWindow); an EventContext build there means a DB query per
   lap event. Fix: push a frozen "session tag" snapshot into the dispatcher at
   activation/session-open time instead of it reading config.
2. **`_compute_race_config_id`** — the session-match-key **hash** reads
   track/car/race-type/length from the dict with specific defaults (25/60);
   any source change risks silently re-keying every lap bank / history entry.
   Fix: byte-stability proof against EventContext (post-Phase-4 the inputs are
   always in sync) plus pinned hash-vector tests.
   **Phase 6b (2026-07-04): proof + golden vectors delivered
   (`tests/test_race_config_id_hash.py`); the MIGRATION half is blocked by the
   restore-divergence (`_load_session_config` deliberately desyncs the working
   config so the id follows the restored session) and folds into items 3/4.
   See `docs/LEGACY_FANOUT_PHASE_6B.md`.**
3. **Restore writers** — **reader half done (2026-07-04, Working Race Config
   Read Model):** the concept is now named/typed (`data/working_race_config.py`,
   owning the match-key algorithm under the golden vectors) and the remaining
   working-config readers migrated. The WRITER half below stays, deferred with
   item 4 — see `docs/WORKING_RACE_CONFIG.md`.
   **Writer half resolved (2026-07-04, Fan-Out Rule-Cache Deletion):** the
   event-RULE cache writes were DELETED from `_fanout_event_to_strategy`
   (proven invisible — all consumers DB-first); the remaining writes are the
   legitimate working-config core. The audit's SSOT violation no longer
   exists. See `docs/FANOUT_RULE_CACHE_DELETION.md`. Item 4's remainder
   (a durable home for plan state) is a schema decision, not a correctness
   one.
   (`_load_session_config` ×3, `_strategy_apply_plan`,
   `_save_race_params`, `_update_race_config`, garage car writer) — they WRITE
   track/car/laps/config_id into the dict; the restore design must move to the
   contexts/DB before the event-rule fields can disappear.
4. **Plan-state persistence** — `stops`, `fuel_burn_per_lap`, `pit_loss_secs`,
   tolerances, `config_id` legitimately persist in `config["strategy"]` (no DB
   home). Either they get a DB/table home or the dict survives as a
   plan-only store (renamed/reshaped in a schema migration).
5. **Context-builder bridges** — Event/Strategy/Track/Session context builders
   and the AI-snapshot fallbacks read the dict *by design*; they are the last
   to change, when the dict itself is reshaped.

With Phase 4's re-sync the fan-out can never go stale, so none of this is a
correctness risk — it is a mechanical (if large) cleanup, best done as
targeted follow-ups (1 → 2 → 3) rather than one sprint.

## 5. What was intentionally NOT changed

* The fan-out writer + save re-sync (Phase 4), the Track Modelling combo
  writer, the hash, all restore/plan writers, the bridges, and every cosmetic
  read in the allowlist.
* No setup logic, strategy calculation, track mapping, AI prompt, telemetry,
  PTT, voice, or tab-order change.

## 6. Tests

`tests/test_legacy_fanout_phase_5.py` (15) — frozen-allowlist exact match + the
no-new/no-silently-removed guard; byte-identity for every migrated read
(session-tagging fields incl. empty defaults, degradation params incl. 1.0/2
defaults, BoP gate + car, setup-dict identity fields incl. the "Unknown Car"
fallback); source-scans that the five migrated methods read the contexts with no
raw reads left; fan-out writer + save re-sync + Home-first + config-guardrail
invariants. **2 legacy pins updated in place** (`test_group4_fixes`
`TestBoPSourceOfTruth` ×2 — the invariant was "BoP from event state, never a
widget"; the event-state source is now EventContext).

## 7. Next sprint recommendation

> **Executed (2026-07-04):** Phase 6a ran next — retirement-map item 1 is done.
> The dispatcher's telemetry-path reads were replaced by a frozen `SessionTag`
> pushed from the UI, and the allowlist was consciously shrunk
> (`("main.py","_dispatch"):2` → `("main.py","__init__"):1`). See
> `docs/LEGACY_FANOUT_PHASE_6A.md`.

The fan-out series has reached its natural pause: staleness is impossible
(Phase 4), no functional decision reads the dict (Phases 3+5), and the guard
prevents regression. Recommended next:

* **Wire the real UDP-listener connection signal into `SessionContext`** (the
  standing one-place change) so Home's `live_active` reflects the actual
  connection — small, user-visible; or
* **Phase 6a** — the dispatcher session-tag snapshot (retirement map item 1),
  the first concrete step toward deleting the writer; or
* return to **product work** (e.g. the deferred OFR-1 between-race learning
  loop) now that the state architecture is consolidated.
