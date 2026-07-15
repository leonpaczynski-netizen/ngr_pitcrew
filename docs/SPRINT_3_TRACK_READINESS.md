# Sprint 3 — Track Readiness Resolver + Fuji auto-load

**Status:** COMPLETE (verified green)
**Branch:** sprint-3-track-readiness (off master)
**UAT Defect 6:** Fuji blocked in Command Centre despite valid assets; user forced to open Track Modelling and re-save seed geometry first.

## Root cause (verified)
Track readiness was decided in ≥3 places with different rules. The Command Centre keyed off `TrackContext.can_attempt_live_mapping`, which is `identity.is_complete AND station_map_available` — **station-map only**. And `_build_track_context` only audited disk when the Track-Modelling combos were already populated (they are empty on a fresh restart because that tab hasn't run), so on startup every availability flag was False. Worse, `audit_track_model_files` never checked `accepted_model.json` or `station_map.json` and looked for a non-timestamped `reviewed_segments.json` while the real files are timestamped. Net: Fuji read BLOCKED even though an approved reference path (200 pts), accepted model, station map, reviewed segments, and seed geometry were all on disk.

## What was built
- **`data/track_readiness.py`** — the single deterministic resolver (pure: no Qt/IO/network). `TrackReadiness` enum (READY_APPROVED, READY_SEED_GEOMETRY, PARTIAL, MISSING_ASSET, IDENTITY_MISMATCH, INVALID_ASSET) + `TrackReadinessResult` (state, ids, confidence, provenance, assets, blockers, next_action, `is_ready`/`is_approved`). `resolve_track_readiness(track_context)` applies a fixed precedence over the availability signals.
- **`data/track_readiness_disk.py`** — disk-first companion. `resolve_track_readiness_from_disk(loc, lay)` audits the flat `track_models/` store directly via the existing helpers (`reference_path_asset_summary`, `find_accepted_model_path`, `find_station_map_path`, `find_reviewed_models_for_layout` glob, `audit_layout_seed.has_seed_centreline`) and feeds the pure resolver — **no Track Modelling, no in-memory state required.** This is the one function every screen calls.
- **Command Centre wired**: `ui/home_dashboard_vm._build_track_card` now takes a `readiness` verdict (computed disk-first in the Qt layer, `ui/dashboard._build_home_dashboard_state`, and passed in to keep the VM pure). Status is driven by the verdict: READY_APPROVED/READY_SEED_GEOMETRY → READY, MISSING_ASSET → MISSING, INVALID_ASSET → BLOCKED, PARTIAL/IDENTITY_MISMATCH → ATTENTION. The station-map-only gate remains only as a fallback when no verdict is supplied.
- **`audit_track_model_files` extended (additive)**: new `accepted_exists` / `station_map_exists` fields; reviewed detection now globs the timestamped `…__reviewed_segments__*.json` (with legacy fallback). `build_track_context` now ORs these disk flags into `accepted_model_available` / `station_map_available`, so the shared `TrackContext.availability` that Setup Builder and Track Modelling read is also disk-correct on a fresh restart.

## Acceptance (verified against real committed Fuji assets)
- `resolve_track_readiness_from_disk("fuji…","fuji…__full_course")` → **READY_APPROVED** (all assets detected: reference path 200 pts, accepted model, station map, reviewed segments via glob, seed geometry) with **no Track Modelling opened**.
- The Command Centre "Track Intelligence" card renders **READY, not BLOCKED**, for an approved verdict — even with `station_map_available=False` (proving readiness no longer requires the station map).
- Unknown track → MISSING_ASSET.

## `can_attempt_live_mapping`
Left unchanged — it is semantically the gate for the *live station-map matcher* specifically, which legitimately needs a station map. It is simply no longer (mis)used as the general readiness signal.

## Sprint 3 final report
- **Files changed:** +`data/track_readiness.py`, +`data/track_readiness_disk.py`, +`tests/test_track_readiness.py`, +`docs/SPRINT_3_TRACK_READINESS.md`; modified `ui/home_dashboard_vm.py`, `ui/dashboard.py`, `data/track_context.py`, `data/track_calibration.py`.
- **Architecture changed:** one shared `TrackReadinessResolver` (disk-first) replaces three ad-hoc readiness notions for track-model readiness.
- **Behaviour changed:** Command Centre (and any screen calling the resolver) now reflects on-disk assets without opening Track Modelling; Fuji is READY on a clean restart. No valid asset is rewritten on load (resolver is read-only).
- **DB/schema changes:** none.
- **Tests added:** 19 (pure resolver states, real-disk Fuji READY_APPROVED, Command Centre card READY-not-BLOCKED, determinism).
- **Regression result:** full suite in halves = **6761 passed / 0 failed / 27 skipped.**
- **Runtime files verified untouched:** 27 protected files unchanged vs the Sprint-0 baseline (resolver only reads).
- **Known limitations:** per-screen readiness *display* on Setup/Practice/Strategy/Live is deferred to the Sprint 10 guided-UI overhaul; the shared resolver they must call already exists. `IDENTITY_MISMATCH` currently fires on incomplete identity; richer alias-mismatch detection can be added when the alias map is wired.
- **Recommended next:** Milestone 3 — Sprint 4 (telemetry event correctness) + Sprint 5 (cross-lap persistence).
