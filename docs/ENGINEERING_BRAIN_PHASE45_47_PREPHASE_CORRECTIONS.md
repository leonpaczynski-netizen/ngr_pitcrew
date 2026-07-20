# Engineering Brain — Phases 45–47 Pre-Phase Corrections (A & B)

Read-only audit + corrections applied before the Phase 45–47 work. No earlier commit is amended.

## Correction A — Stale Phase 6 regression test

**Root cause.** `tests/test_phase6_wiring.py::test_no_migration_no_new_telemetry_table` asserted
`"_DDL_V26" not in src and "_migrate_v26" not in src`. That was true when written (before Phase 19), but
Phase 19 legitimately introduced database version 26 (`_DDL_V26` / `_migrate_v26`), so the test forbade
the entire legitimate migration chain rather than the actual Phase-6 invariant. It failed identically at
every recent checkpoint (unrelated to the intervening slices).

**Correction.** The test now proves the real Phase-6 invariant against a freshly-created database:
`PRAGMA user_version == DB_VERSION` (schema coherent with the *legitimate* migration chain, including
v26 and the new v27); no residual/telemetry persistence table exists (Phase 6 residual detection is
pure); and no telemetry table exists beyond the canonical base stores
(`{lap_telemetry, corner_slip_telemetry}`). It does not weaken migration safety generally. Verified
against: the v26 checkpoint (passes), the new Phase-45 v27 schema (passes), a fresh DB and a migrated
legacy DB (migration tests in the Phase-45 suite).

## Correction B — Mechanism-level context sensitivity

**Root cause.** The Phase-42 coarse `DOMAIN_REQUIRED` map let some legacy records stay *exact* for
`setup_working_windows` / `driver_technique` / `vehicle_dynamics` even when the material *setup* or
*event* conditions a specific mechanism depends on were unknown.

**Correction.** Added a finer `MECHANISM_REQUIRED` map + `field_to_mechanism` + a field-level
`build_field_working_window_trust`, so a specific setup field caps to `PARTIAL_CONTEXT` when its
mechanism's material conditions are unknown:

| Mechanism | Required (must be a known match for exact) |
| --- | --- |
| gearing_acceleration | car, track, layout, BoP, power, weight, discipline, gt7, applied-setup, compound |
| aero | car, track, layout, BoP, power, weight, discipline, gt7, applied-setup |
| suspension_ride_height | car, track, layout, discipline, compound, applied-setup |
| lsd_traction | car, discipline, compound, applied-setup |
| driver_technique | driver, car, track (broad transfer; limitations retained) |

Legacy records carry only the memory key (driver/car/track/layout/discipline/compound/gt7) — they lack
BoP/restrictions/applied-setup identity — so gearing/aero/suspension/LSD legacy evidence is now
correctly capped to `PARTIAL_CONTEXT`, while driver_technique stays exact. Full-context evidence (with
applied-setup identity + restrictions known) is exact. Every eligibility decision still exposes required
/ known / missing / inferred fields, the confidence cap and the reason. The coarse `DOMAIN_REQUIRED`
map is retained for backward compatibility; `build_material_context_trust` accepts either a domain or a
mechanism key.

## Phase 42–44 documentation caveats (stated per the task)

1. The Phase-6 regression test was **stale** and is corrected as above.
2. The Phase 42–44 **offscreen UAT did not prove live GT7 prompt usability** — only that the code paths
   construct and behave deterministically headlessly.
3. A **semantic fingerprint without persisted snapshot content was insufficient** for permanent
   historical reconstruction — Phase 45 persists immutable snapshot **content** (a v27 table), not just
   a fingerprint or a reference to a mutable event.
4. The broad domain-level context requirements **required mechanism-level refinement** (Correction B).
