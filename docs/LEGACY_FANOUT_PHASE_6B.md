# Legacy Fan-Out Removal Phase 6b — config_id Hash Byte-Stability Proof

> Author: Legacy Fan-Out Removal Phase 6b sprint · Date: 2026-07-04
> Branch: `legacy-fanout-phase-6b-hash-proof` (from `master` @ `8e9fcb6`)
>
> Companion docs: `docs/LEGACY_FANOUT_PHASE_5.md` §4 (retirement map — this is
> item 2), `docs/LEGACY_FANOUT_PHASE_6A.md`.

---

## 1. Goal and outcome

`_compute_race_config_id` derives the 10-char **session match key** every
lap-bank entry, setup-history entry, and DB session row is keyed by. Silently
changing its algorithm *or its input source* would re-key all of that history.

Retirement-map item 2 asked for a byte-stability proof and, if possible, a
migration of the hash inputs to the canonical contexts. **Outcome: the proof
and pins are delivered; the migration is provably blocked and folds into
retirement-map items 3/4.** No production code changed this sprint — it is
tests + documentation.

## 2. The blocker discovered — restore-divergence

`_load_session_config` (the lap-bank "load historical session" feature)
**deliberately** writes a historical session's track/car + race params into the
working `config["strategy"]` *without changing the active event*, then calls
`_update_race_config()` to recompute the id — the whole point is that the id
follows the **restored session**, so its laps/history light up.

`EventContext.track`/race-rules are **DB-event-first**. An EventContext-sourced
hash would therefore pin the id to the *active event* during a restore — a
different id — silently breaking the lap-bank restore feature. (Post-Phase-4
the working config and the DB event are otherwise always in sync, so outside a
restore the two sources are provably identical — tested.)

`car` alone is always-safe (strategy-first in EventContext, even mid-restore),
but hash inputs must move **together**: piecemeal sourcing would make the id
depend on two stores at once.

**Corrected retirement map:** item 2's migration half merges into item 3
(restore-writer redesign) / item 4 (a proper "working race config" home). When
the working config gets a canonical model, the hash reads move with it — under
the golden vectors added here, which make any accidental re-keying impossible
to miss.

## 3. What was delivered

`tests/test_race_config_id_hash.py` (17):

* **Golden vectors** — five literal (inputs → id) pairs computed from the
  shipped algorithm and frozen, exercised through the REAL
  `_compute_race_config_id` bound to a widget-free stub. Includes the
  empty/default working config `'||l25' → 05e6d2f288` — a real id observed in
  the field (it appeared in the restored user config on 2026-07-03). The test
  header forbids regenerating vectors on failure: a mismatch means history
  re-keying and the *code* must be fixed.
* **`DEFAULT_CONFIG` pin** — a freshly-loaded config hashes to the empty
  vector.
* **Shape/stability/sensitivity** — 10-char lowercase hex; deterministic; each
  input (track, car, race type, length) independently changes the id; the
  algorithm's own `l25`/`t60` defaults pinned (distinct from EventContext's 0
  defaults); unknown race-type tokens hash as lap races.
* **Source-level algorithm pin** — the raw-string format
  (`f"{track}|{car}|{length_key}"`), `sha256(...)[:10]`, the 25/60 defaults,
  and the working-config input source are asserted verbatim in the function
  body.
* **Equivalence + divergence proofs** — an in-sync active event would hash
  identically from EventContext (so the future migration is safe *outside*
  restores); the restore case produces a different EventContext-sourced raw
  string (the blocker, demonstrated); `car`'s strategy-first safety shown.
* **Invariants** — the Phase 5 frozen allowlist is untouched (no reads
  migrated); Home-first; config-safety guardrail.

## 4. What was intentionally NOT changed

Everything. This sprint is purely additive tests + docs: no hash change, no
reader migration, no writer change, no behaviour change of any kind.

## 5. Next sprint recommendation

* **Retirement-map item 3 — restore-writer redesign**: give the lap-bank
  restore a first-class "working race config" flow (and home, item 4) so the
  hash inputs, the restore writers, and the plan-state persistence can migrate
  together — now guarded by the golden vectors.
* Or **return to product work** (deferred OFR-1 between-race learning loop) —
  the state architecture is consolidated, Home is truthful, and the match-key
  is now tamper-evident.
