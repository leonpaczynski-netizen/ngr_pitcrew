# Design — Continuous Track‑Model Refinement (UAT #6)

Status: **DRAFT for review** (2026‑07‑12). No code written yet.
Author: Pit Crew dev session. Supersedes nothing; extends the existing track‑modelling pipeline.

Related: [[project_track_modelling_stores]], `data/track_geometry_builder.py`,
`data/track_station_map.py`, `data/track_model_alignment.py`,
`data/track_segment_review.py`, `ui/track_modelling_ui.py`, `data/live_road_distance_capture.py`.

---

## 1. Problem & goal

Today a track model is built **once**, manually, in the Track Modelling tab: the driver
runs a dedicated *calibration* session (2–3 clean laps), the app builds a 1 m station map,
detects/aligns corners against seed data, and the user **accepts** it → writes
`<loc>__<lay>.accepted_model.json` + the reviewed‑segments file (AI‑ready).

UAT complaint: *"after the initial model is approved and I'm doing an event, the app knows
what track I'm at — why doesn't it keep adding track data and refine the mapping?"*

**Goal:** while driving real event laps at a track that already has an accepted model,
opportunistically accumulate fresh lap geometry and use it to **refine** the model —
tightening the reference path, lap‑length estimate, corner positions, and confidence —
**without ever silently degrading or mutating the model that live features are relying on.**

---

## 2. Current pipeline (grounded)

```
select track/layout (seed: corners_expected, lap_length_m)
  → start_session (dedicated calibration; packets → _tm_controller)
  → build_reference_path   (filter_full_laps → build_seed_geometry)   [track_geometry_builder.py]
  → _build_station_map     (1 m stations; ~4441 for Fuji)             [track_station_map.py]
  → detect_segments        (corner detection)                         [track_segment_review.py]
  → run_alignment          (detected vs seed corners → match_status)  [track_model_alignment.py]
  → ACCEPT → export_accepted_model_json  +  export_review_json
```

`accepted_track_model_v1` fields already carried (see the Fuji file): `match_status`,
`accepted`, `accepted_at`, `seed_corners_expected`, `model_corners_found`,
`lap_length_m_model`, `lap_length_m_seed`, `lap_length_delta_pct`, `station_count`,
`confidence`, `blockers`, `warnings`.

Two stores (unchanged): **accepted_model** (station map + alignment, used by live progress /
race strategy) and **reviewed_segments** (AI‑ready). The **model is built from per‑lap XYZ
paths.**

---

## 3. Hard constraints discovered

| # | Constraint | Consequence for design |
|---|------------|------------------------|
| C1 | Event laps in `SessionDB.write_lap` store **summary stats + event markers only** — NOT the full XYZ path. | Refinement can't replay history from the DB. Need a **live path accumulator** during events (reuse the `live_road_distance_capture` pattern: keep `pos_x/y/z` per sample, lap markers). |
| C2 | The accepted model is **actively read** by live progress + race strategy during a session. | **Never mutate the in‑use model mid‑session.** Refine into a candidate; promote only between sessions. |
| C3 | Event laps are dirty: off‑tracks, spins, contact, different cars/lines, damage, weather. | Strict lap‑quality gating before a lap is allowed to contribute. |
| C4 | A refined model can be **worse** than the accepted one. | Promotion is gated on **non‑regression + improvement**; a worse candidate is discarded, never promoted. |
| C5 | Project philosophy = **honest, no silent mutation** (Engineer Brain safety spine, no runtime mutation). | Default is **refine → propose → user accepts**. Auto‑accept only under a strict, opt‑in improvement gate. |
| C6 | Different cars take different lines; the model is a spatial corridor for progress matching, not a racing line. | Keep the existing centreline‑ish build; more laps tighten the corridor. Don't over‑fit to one car's line (track contributing car(s)). |

---

## 4. Design overview

Three decoupled parts:

```
(A) LIVE CAPTURE            (B) CANDIDATE REFINEMENT           (C) PROMOTION
event packets ─▶ path       accumulated clean laps ─▶ rebuild  candidate vs accepted
accumulator (in RAM,        via existing builder ─▶ align ─▶   ─▶ improvement gate
per event lap, XYZ+lap)     candidate_model (on disk, NON‑     ─▶ prompt user (default)
  ▲ only when an accepted    destructive) + refinement ledger    or strict auto‑accept
    model exists for the                                         ─▶ on accept: atomic
    current track/layout                                            replace accepted_model
```

- **(A)** runs during normal Live driving — no dedicated calibration session.
- **(B)** runs off the hot path (session end, or idle), produces a *candidate* only.
- **(C)** never happens automatically unless the strict gate + opt‑in are both satisfied;
  otherwise the user sees "Refined model available — review & accept" in the Track
  Modelling tab.

---

## 5. Data model (new, additive — no migration to existing files)

New sibling files next to the accepted model (same `data/track_models/` dir):

- `**<loc>__<lay>.candidate_model.json**` — schema `candidate_track_model_v1`.
  Superset of `accepted_track_model_v1` plus:
  - `base_accepted_at` — the `accepted_at` of the model this candidate was refined from
    (detects a stale candidate after a manual re‑accept).
  - `contributing_laps` — count of clean event laps merged in.
  - `contributing_cars` — sorted list of car names that contributed (line‑variance audit).
  - `source_sessions` — session ids that contributed.
  - `delta_vs_accepted` — `{corner_match_delta, lap_length_delta_pct_change, confidence_delta,
    mean_station_shift_m}`.
  - `improves` (bool) + `improvement_reasons[]` / `regression_reasons[]`.
- `**<loc>__<lay>.refinement_ledger.jsonl**` — append‑only audit: one line per refinement
  round `{ts, session_id, cars, laps_seen, laps_accepted, laps_rejected+reasons, candidate
  metrics, decision}`. Honest record of what was ingested and why laps were dropped
  (mirrors the "no silent caps — log what was dropped" principle).

The **accepted_model + reviewed_segments files are only ever replaced atomically on
promotion** (write `.tmp` → `os.replace`), exactly like today's export.

---

## 6. Components (new modules, pure where possible)

1. `data/live_track_path_capture.py` (pure, RAM) — **(A)**.
   - `LiveTrackPathCapture(track_location_id, layout_id, car_name)`; `add_packet(packet)`
     stores `(pos_x,y,z, lap_number, on_track_flags)`; emits per‑lap `LapPath` objects on
     lap rollover. Rejects non‑finite coords. Mirrors `live_road_distance_capture` design
     (read‑only, diagnostic, never writes the model).
   - Gated on: an accepted model exists for the *current* track/layout **and** the driver is
     actually on this track/layout (identity check), matching the app's known track.

2. `data/track_refinement.py` (pure) — **(B)** + **(C) gate**.
   - `assess_lap_quality(lap_path, accepted_model, seed) -> LapQualityVerdict`
     (ACCEPT / REJECT+reason). Reuses `classify_lap_delta` + `filter_full_laps` semantics:
     full lap, crosses S/F cleanly, lap length within tolerance of accepted, no large
     off‑corridor excursion vs the accepted station map, not a pit/out lap.
   - `build_candidate_model(accepted_model, prior_contributing_paths, new_clean_paths, seed)
     -> CandidateModel` — merge paths → existing `build_seed_geometry` → `_build_station_map`
     → `detect_segments` → `run_alignment`. **Weights the existing accepted geometry** so a
     handful of event laps nudge, not overturn, a well‑established model (e.g. EWMA / capped
     new‑lap weight).
   - `compare_models(accepted, candidate) -> ImprovementVerdict` — the **non‑regression +
     improvement gate** (§7).
   - `promote_candidate(...)` — atomic replace of accepted_model + reviewed_segments;
     appends to the ledger; clears the candidate.

3. Wiring in `ui/track_modelling_ui.py` + the live packet path:
   - Attach `LiveTrackPathCapture` where live packets are dispatched (same seam the
     race‑strategy live capture uses), constructed only when an accepted model exists.
   - On **session stop** (or Track Modelling tab shown): run refinement round → write
     candidate + ledger → refresh a new "Refinement" panel.

---

## 7. Improvement / non‑regression gate (`compare_models`)

A candidate may be promoted **only if it does not regress and improves ≥1 axis**:

- **Never regress (hard blocks):**
  - `model_corners_found` must not drop below accepted.
  - `match_status` must not fall below accepted (GOOD_MATCH ▸ PARTIAL ▸ …).
  - `confidence` must not drop by more than a tiny epsilon.
  - mean per‑station shift vs accepted must be < `MAX_MEAN_SHIFT_M` (e.g. 3 m) — a large
    shift means contamination or a different line, not a refinement.
- **Improves (≥1 required):**
  - `lap_length_delta_pct` moves closer to seed, **or**
  - `model_corners_found` increases (a corner the calibration missed), **or**
  - `confidence` increases, **or**
  - `contributing_laps` increases materially with metrics stable (tighter corridor / more
    evidence) — this yields at most a small confidence bump, never a geometry overturn.
- Contributing‑car diversity is surfaced (not a gate): a candidate built from 1 car's line is
  flagged so the user knows it may be line‑biased.

If the gate fails → candidate is kept on disk for visibility but marked `improves:false` with
`regression_reasons`, and is **never** auto‑promoted.

---

## 8. Promotion policy (the decision you flagged)

Default, matching project philosophy (C5): **refine → propose → user accepts.**
Track Modelling tab shows: *"Refined model available for <track>: +1 corner, lap‑length
2.68% → 1.1%, confidence 1.00 (from 4 event laps across 2 cars). [Review] [Accept] [Discard]."*
Review overlays candidate vs accepted on the existing map widget (reuse highlight bands).

Optional, **opt‑in** per‑track setting `auto_accept_refinements` (default OFF): auto‑promote a
candidate **only** when the gate reports improvement **and** the change is within a
conservative tolerance (e.g. mean shift < 1 m, no corner count change, confidence delta ≥ 0).
Anything larger always falls back to prompting. Every auto‑accept is written to the ledger.

> Recommendation: ship prompt‑only first (Phase 1). Add opt‑in auto‑accept in Phase 3 once the
> gate has proven itself on real event data.

---

## 9. Safety invariants (must hold)

- **S1** Never write the accepted_model/reviewed_segments except via `promote_candidate`
  (atomic, gated, logged). No mid‑session mutation.
- **S2** A worse or equal candidate is never promoted. Regression is impossible by the gate.
- **S3** Live progress / race strategy read the **accepted** model only; the candidate is
  invisible to them until promoted.
- **S4** Every ingested/rejected lap is logged with a reason (no silent contamination, no
  silent truncation).
- **S5** A candidate whose `base_accepted_at` ≠ the current accepted model's `accepted_at`
  is stale → discarded and rebuilt (handles a manual re‑accept in between).
- **S6** Capture only runs when the driven track/layout identity matches the accepted model.

---

## 10. UI additions (Track Modelling tab)

- A **"Continuous Refinement"** group: status line (*"Capturing… N clean laps this session"* /
  *"Refined model available"* / *"Model up to date"*), `contributing_laps`, `contributing_cars`,
  and **Review / Accept / Discard** buttons.
- Reuse the existing map widget + highlight bands to show candidate‑vs‑accepted differences
  (shifted stations / new corner).
- Per‑track `auto_accept_refinements` checkbox (Phase 3).

---

## 11. Phasing

- **Phase 1 (MVP):** live path capture (A) + candidate build (B) + gate (C) + ledger +
  prompt‑only UI. Refinement runs on session stop / tab open. Metrics: lap length, corner
  count/match, confidence, mean shift. *Delivers the user's ask end‑to‑end, safely.*
- **Phase 2:** corridor tightening (weighted merge tuning), pit‑lane refinement from event
  pit laps, per‑car line audit surfaced in Review.
- **Phase 3:** opt‑in strict auto‑accept; refinement history view from the ledger.

---

## 12. Testing

- Pure unit tests (no Qt) for `assess_lap_quality`, `build_candidate_model`,
  `compare_models` (regression cases: contaminated lap, spun lap, different‑line lap all
  either rejected or gated out), `promote_candidate` atomicity + stale‑base handling.
- Golden: feeding the accepted model's own laps back yields `improves:false`/no‑op (idempotent).
- Contamination: an off‑track lap must be rejected (S4 logged) and must not shift stations.
- Headless UI smoke: capture status + Review/Accept/Discard wiring, accepted file only
  changes via Accept.

---

## 13. Open decisions for you

1. **Auto vs prompt** — recommend prompt‑only in Phase 1 (default OFF auto‑accept). Confirm?
2. **Trigger timing** — refine on **session stop** (clean, off hot path) vs also on Track
   Modelling tab open. Recommend both; refine‑on‑stop is primary.
3. **New‑lap weight** — how strongly event laps nudge an established model. Recommend a capped
   EWMA (e.g. event laps never exceed ~30% aggregate weight) so one bad session can't overturn
   a calibrated model. Tune in Phase 2.
4. **Scope of refinement** — geometry + lap length + corners + confidence (recommended).
   Include pit‑lane in Phase 2. Racing line stays out (it's not what the model represents).
```
