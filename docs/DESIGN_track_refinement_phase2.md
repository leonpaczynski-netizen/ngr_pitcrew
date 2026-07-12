# Design — Continuous Track‑Model Refinement, Phase 2 (plan)

Status: **DRAFT plan for review** (2026‑07‑12). No code written yet.
Builds on Phase 1 (shipped): `data/live_track_path_capture.py`,
`data/track_refinement.py`, the Track‑Modelling "7. Continuous Refinement" panel,
and the `_poll_ui_queue` capture hook. See
[docs/DESIGN_continuous_track_refinement.md](DESIGN_continuous_track_refinement.md).

Phase 1 recap: capture is **manual** (Start in the Track Modelling tab), refinement
builds a **non‑destructive candidate**, promotion is **gated** (`compare_models`:
metric non‑regression + ≥1 improvement) and atomic. Phase 2 makes it **automatic
during events**, **anti‑contamination robust**, and keeps the **AI‑ready model in
sync**.

---

## Prerequisite — 2·0 Persist candidate geometry (foundation)

Several Phase 2 items need the candidate's actual geometry (station coordinates),
which today only lives in RAM during a refine round — the candidate JSON stores
metrics only.

- At candidate‑build time, write a companion `*.candidate_reference_path.json`
  (the `ReferencePath.points`) next to the candidate model, via the existing
  `export_reference_path_json`.
- `promote_candidate` / `compare_models` / segment‑regen then reload it.

This unlocks the geometry‑shift guard (below), reviewed‑segments regen (2C), and
auto‑accept (2F). Small, do first.

**Geometry‑shift guard (harden `compare_models`):** load the accepted reference
path (`data.reference_path_loader.load_reference_path_for_layout`) and the
candidate points; compute **mean per‑station displacement**. Add as a hard
non‑regression block (`> MAX_MEAN_SHIFT_M`, e.g. 3 m ⇒ contamination/different
line, reject) — the core anti‑contamination guard deferred from Phase 1. Tests:
a contaminated/spun/off‑line candidate is gated out even if its scalar metrics
look fine.

---

## 2A — Auto‑capture during live events (headline; the original ask)

The app already resolves live identity: `_build_event_context()` exposes
`track_location_id` / `layout_id` during a session (used by
`_resolve_live_track_progress_context`).

- **Auto‑start:** when a live session is active and the EventContext resolves
  BOTH canonical ids AND `find_accepted_model_path(loc, lay)` exists, lazily
  construct `LiveTrackPathCapture(loc, lay, car)` (the `_poll_ui_queue` hook is
  already wired). Do it from the same per‑frame path, guarded by
  `capture is None and identity resolved and accepted model exists`.
- **Identity change mid‑session:** if `not capture.matches(loc, lay)` (track/car
  changed), drop the capture and start fresh — never mix tracks.
- **Auto‑refine on session end/reset:** call `refine_from_session` on stop
  (hook `_on_reset_clicked` / session‑stop). If an **improving** candidate
  results, surface a **non‑intrusive** notice — a badge on the Track Modelling
  tab + a one‑line Home/Live banner *"Refined model available for <track> —
  review in Track Modelling."* Never auto‑applies (that's 2F).
- **Fallback:** if the event only has a display name (no canonical ids), skip
  silently and leave the Phase‑1 manual flow. Log to the ledger.

Risk: `laps_recorded` as lap number already proven in Phase 1. Verify off‑track /
out‑lap rejection holds on real event laps (the capture's on‑track gate +
`build_reference_path` quality gates already filter these). **Needs live‑app UAT.**

**Decision:** auto‑start ON by default when an accepted model exists, or opt‑in
per track? Recommend **ON by default** (it's the user's ask) but **prompt‑to‑accept**
always (auto‑accept is separately opt‑in in 2F).

---

## 2B — Weighted merge (anti‑overturn anchoring)

Phase 1 builds the candidate from event laps alone; the gate protects against a
bad result, but a handful of event laps shouldn't *define* the geometry of a
well‑calibrated model.

- Reconstruct **anchor laps** from the accepted reference path (points →
  synthetic `CalibrationLap`), and include `K_anchor` copies in the
  `CalibrationSession` alongside the event laps. `build_reference_path` averages
  per progress bucket, so event‑lap weight = `n_event / (n_event + K_anchor)`.
- Cap event influence at ≈30%: `K_anchor = ceil(n_event * 0.7/0.3)`.
- New helper `reference_path_to_calibration_lap(asset)`; `build_candidate_alignment`
  gains an optional anchor. Keep the un‑anchored path for tests/back‑compat.

Risk: anchor laps need plausible timestamps/quality so `assess_session_laps`
keeps them USABLE — synthesize monotonic timestamps and mark quality directly.
Tests: with 1 noisy event lap + anchor, the candidate stays within a small shift
of the accepted model (no overturn); with many consistent event laps, the shift
is allowed to grow (genuine refinement).

---

## 2C — Reviewed‑segments regeneration on promote (keep AI‑ready in sync)

Phase 1 `promote_candidate` updates `accepted_model.json` only; the
`reviewed_segments` file (what makes the model AI‑ready) is left as‑is, so the
AI‑ready model can lag the refined geometry.

- On promote, rebuild the station map from the persisted candidate reference
  path (2·0), run `detect_track_segments` → `create_review_from_detection` →
  confirm segments → `export_review_json` — mirroring `_tm_accept_track_model`.
- Keep it best‑effort and logged; a regen failure must not corrupt the freshly
  promoted accepted model (write order: accepted first, then segments).

Tests: after promote, the reviewed‑segments file exists and matches the new
geometry; resolver reports AI‑ready.

---

## 2D — Pit‑lane refinement from event pit laps

Event stints include real pit entries; calibration often doesn't.

- The station‑map builder already supports `detect_pit_lane_from_pit_laps`.
  Feed event pit laps (flagged during capture) so a promoted model gains/《refines》
  its pit‑lane corridor — which directly helps the race‑strategy pit resolver
  (`data/pit_lane_resolver.py`).
- Capture must retain pit‑lap markers (extend `LiveTrackPathCapture` to flag laps
  where a pit event was detected by the live tracker).

Tests: a session with a pit lap yields a pit‑lane boundary in the candidate; a
session without leaves the existing one untouched (non‑regression).

---

## 2E — Per‑car line audit (Review UX)

`contributing_cars` is already captured. Different cars take different lines.

- In the Review panel, warn when a candidate is built from a **single** car's
  line (*"built from 1 car — may be line‑biased"*), and list contributing cars.
- Optionally overlay candidate‑vs‑accepted station shift as an amber band on the
  existing map widget (reuse `_tm_set_map_highlight`).

Pure‑UI; no gate change. Small.

---

## 2F — Opt‑in strict auto‑accept

For users who trust the pipeline.

- Per‑track setting `auto_accept_refinements` (default **OFF**).
- On auto‑refine (2A), auto‑promote **only** when: `verdict.improves` AND change
  within a tight tolerance — mean station shift `< 1 m`, **no** corner‑count
  change, confidence delta `≥ 0`. Anything larger always falls back to prompting.
- Every auto‑accept is written to the ledger.

Depends on the geometry‑shift metric (2·0). Tests: a small improvement
auto‑promotes; a large (even if improving) shift falls back to prompt.

---

## Recommended order & sizing

1. **2·0** geometry persistence + shift guard — *foundation, small, high‑value* (hardens the gate immediately).
2. **2A** auto‑capture + notify — *the headline; medium; needs live UAT*.
3. **2B** weighted anchoring — *medium; pure + testable*.
4. **2C** reviewed‑segments regen — *medium; pure‑ish + testable*.
5. **2D** pit‑lane — *small–medium*.
6. **2E** per‑car audit UX — *small*.
7. **2F** opt‑in auto‑accept — *small once 2·0 lands*.

Each ships independently with tests. 2·0 → 2A delivers the user's core ask
(automatic refinement during events, safely) end‑to‑end.

## Safety (unchanged from Phase 1, still enforced)

All Phase 1 invariants hold: accepted model changes only via gated
`promote_candidate`; a worse/contaminated candidate can't be promoted (now also
geometry‑shift‑gated); live features read the accepted model only; every round
logged. Auto‑accept (2F) is opt‑in and tolerance‑bounded.

## Open decisions

1. **2A default:** auto‑start ON by default (recommended) vs opt‑in per track?
2. **2A notify surface:** Track Modelling tab badge + Home/Live one‑liner
   (recommended) — anywhere else?
3. **2B cap:** 30% event‑lap weight (recommended) — looser/tighter?
4. **2F ship in this phase**, or hold until 2A has real‑world mileage? (recommend hold/opt‑in).
