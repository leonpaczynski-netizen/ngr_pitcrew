# Engineering Brain — Phases 51–53 Pre-Phase Audits (A–D)

Read-only audits performed at `eng-brain-phase48-50-event-preparation-cycle @ ef49d6c` before Phase 51
implementation. No earlier commit is amended.

## Starting checkpoint (verified)

- Branch `eng-brain-phase48-50-event-preparation-cycle`, HEAD `ef49d6c`; master `3d7c6af`; not pushed / no
  PR / not merged. `DB_VERSION == 28`, `RULE_ENGINE_VERSION == "46.0"`.
- 145 Phase 48–50 targeted tests pass; Phase 45–47 targeted suite (64) green; Qt-worker UI tests (15) green.
- Runtime/app-state files (`data/`, `active_setup_state.json`, `.claude/settings.local.json`) left untouched.

### Exact Phase 48–50 Git classification (`git diff --name-status 0447375 ef49d6c`)

| Class | Count |
| --- | --- |
| Added (A) | 31 |
| Modified (M) | 71 |
| Deleted (D) | 0 |
| **Total files** | **102** |
| Insertions | 6,179 |
| Deletions | 115 |

## Audit A — the nine existing regression failures

All nine reproduced at `ef49d6c`. Classification and repair (this slice, commit 1):

| # | Test | Class | Repair |
| --- | --- | --- | --- |
| 1–7 | `test_group55…61_safety_guards.py::TestNoSchemaMigration::test_no_new_migration_hook` | **stale test / invalid historical invariant** | Asserted `"_migrate_v26" not in src`; v26/v27/v28 are legitimate later migrations (Phase 19/45/48). Repaired to guard the real invariant: `f"_migrate_v{DB_VERSION+1}" not in src` (no accidental migration beyond the current declared version). |
| 8 | `test_phase6_golden_uat.py::test_no_migration_needed` | **stale test** | Same `"_migrate_v26" not in src`; same repair. |
| 9 | `test_phase33_35_safety.py::test_no_schema_migration_added_by_slice` | **invalid historical invariant** | Diffed `4b485be..HEAD` (a *moving* HEAD) — breaks on any later legitimate migration. Repaired to pin the endpoint to the P33-35 slice tip `9f64ce7`; `4b485be..9f64ce7 -- _setup_constants.py` is empty, so it now tests the true historical fact (the P33-35 slice changed no setup constants). |

None were genuine product defects, test-isolation defects, or environment-specific defects. No
architecture, migration, Apply-gate or safety protection was weakened; each repair preserves the real
intent (catch an *accidental* new migration) while allowing the legitimate v26→v28 chain. After repair,
all nine pass and no failure is knowingly retained.

## Audit B — `strategy/_setup_constants.py` (0447375 → ef49d6c)

Exact diff: `DB_VERSION: int = 27` → `28`, plus six documentation-comment lines recording the v27
(Phase 45) and v28 (Phase 48) migrations. Changed by commit `639da14` (Phase 48-50 11/12).

- **What/why:** the v28 preparation-tables migration legitimately requires a `DB_VERSION` bump — exactly
  as Phase 19 (25→26) and Phase 45 (26→27) did.
- **Setup-authoring behaviour:** unaffected. `DB_VERSION` is a schema version, not a setup value or rule.
  `RULE_ENGINE_VERSION` is unchanged at `46.0`; `APPROVED_STATUSES` and all setup constants unchanged.
- **Location:** correct — `_setup_constants.py` is the canonical home of the version constants (where
  every prior DB bump lived); the content does not belong in another authority.
- **Byte-stable protection:** the file was guarded by prior-slice byte/diff tests; those are precisely the
  Audit-A failures, which forbade *any* later legitimate bump. Repaired in Audit A, not by moving the
  constant.
- **Frozen invariant:** none violated — no setup value, rule, or status changed.

Conclusion: the modification is necessary, correctly located, and violates no frozen setup invariant.
No corrective relocation is required.

## Audit C — setup convergence invalidation

`strategy/setup_convergence.py::assess_convergence_state` today: a `LOCKED` / `LOCK_READY` setup resists
noise — `regression_detected` is documented as a *validated* worse outcome (not a noisy lap), and a single
noisy/inconclusive latest lap never reopens a stable setup. **Gap:** every reopening trigger collapses
into one `regression_detected` bool; it does not distinguish one noisy lap · one subjective complaint ·
repeated corroborated regression · critical safety instability · setup fingerprint mismatch · materially
changed event context · GT7 physics/rule-version change · new independent experiment evidence.

**Remediation (Phase 53):** a `strategy/setup_lock_reopen.py` reason authority classifies these eight
triggers into an explicit `SetupLockReopenDecision` — a mature setup resists noise (one lap / subjective
complaint alone → not eligible) but reopens on a corroborated critical regression, an event-context
revision, a fingerprint mismatch, a rules/physics-version change, independently corroborated evidence, or
an explicit driver override with visible consequence.

## Audit D — active-cycle resolution

Today `SessionDB.list_preparation_cycles()` returns all cycles and `get_preparation_cycle(id)` fetches
one; there is **no** active-cycle resolver and nothing yet chooses an active cycle at all (so nothing
silently picks the newest row — because no active concept exists). **Gap:** the eight resolution cases
(none / one / several / paused / completed / upcoming / context-changed / manually-selected) are
unhandled.

**Remediation (Phase 51):** `strategy/active_cycle_resolution.py::resolve_active_cycle` produces one of
`NO_ACTIVE_EVENT` / `ONE_ACTIVE_EVENT` / `MULTIPLE_ACTIVE_EVENTS` / `UPCOMING_EVENT` / `PAUSED_EVENT` /
`EVENT_REQUIRES_SELECTION` / `EVENT_CONTEXT_CHANGED` / `EVENT_BLOCKED`; when several cycles qualify it
requires **explicit selection** and never silently chooses by insertion order or newest timestamp. The
selected cycle is **operational navigation state** (an explicit selection id), separate from semantic
engineering evidence — selecting a cycle never alters an engineering fingerprint or historical evidence.
