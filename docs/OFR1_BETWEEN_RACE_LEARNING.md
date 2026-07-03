# OFR-1 — Between-Race Learning Loop (Loop 1: Setup Self-Scoring)

> Author: OFR-1 feature-factory run · Date: 2026-07-04
> Branch: `ofr1-between-race-learning` (from `master` @ `f0a23aa`)
>
> Companion docs: `docs/SMART_RACE_ENGINEER_ROADMAP.md` (OFR-1 spec §11–42,
> §5 Loop 1, §6.4, Phase 3-B), `docs/WORKING_RACE_CONFIG.md`,
> `docs/LEGACY_FANOUT_PHASE_5.md` (the frozen allowlist this feature extends).

---

## 1. What it does

After each session, the app **scores the AI's own setup recommendations against
measured telemetry** and feeds the results back into future setup prompts — so
over many races the engineer calibrates to Leon rather than staying a generic
model. Scope (explicit product decision): roadmap **Loop 1 only** — no
prediction_log / compound_profiles / driver_weaknesses (Loops 2–3 stay deferred).

**The loop:** recommendation applied → next session driven → on the following
session-open, the just-finished session is compared to the recommendation's
creation session → verdict (`improved` / `worsened` / `neutral` /
`insufficient_data`) + confidence (0.0–1.0) persisted write-once → the next
setup prompt for that car+track opens with a plain-English
**"Performance of Previous Recommendations"** block (roadmap §6.4) → the Home
journey's step 13 ("Save learning…") finally lights up from DB truth.

## 2. How it was built (feature-factory)

Seven-agent factory run with human approval gates: researcher → story
(approved) → technical brief (approved **with one design correction**: the
"after" session is resolved via `get_previous_session_id` — the just-finished
session — NOT `rec['outcome_session_id']`, which nothing populates; recs
created in the after-session are skipped) → backend-builder →
frontend-builder → test-verifier (43 acceptance tests, all 11 ACs + 4 edge
cases PASS) → implementation-validator → fix round → re-verified. Builder
output was checkpoint-committed before each verifier stage (house rule).

## 3. The pieces

### `data/recommendation_scoring.py` (NEW, pure — no PyQt/sqlite/IO, never raises)
- `LapWindow` / `ScoringResult` frozen dataclasses; `aggregate_lap_window()`
  (clean-lap filtering: non-pit, non-out; per-lap handling-event rates;
  majority compound).
- `classify_why_text()` — handling-targeted vs laptime-targeted from the
  recommendation's why-text (understeer/oversteer/wheelspin/traction/…).
- `compute_verdict_and_confidence()` — honesty gates FIRST (missing
  `before_metrics` or <3 clean laps either side → `insufficient_data`,
  confidence 0.0); Δt best-clean-lap delta; handling directional agreement
  across lock-ups / wheelspin / oversteer (+on-throttle) / bottoming / brake
  consistency; verdict thresholds (improved: Δt<−200 ms or agreement≥0.6 with
  Δt≤+100; worsened: Δt>+300 ms or agreement<0.3 with Δt>0; **mixed-signal
  override**: Δt clearly improved but agreement<0.3 → neutral); confidence =
  evidence quality (−0.1 per clean lap below 6 each side, −0.15 mixed signals,
  +0.1 driver feedback, ×1/N attribution split across simultaneous recs,
  clamped). **No tyre-radius signal anywhere** (unvalidated proxy, roadmap §2.3).
- `format_performance_block()` — the §6.4 plain-English block; only recs with
  confidence ≥0.5 and a real verdict; `''` when nothing qualifies.

### `data/session_db.py` — migration v9 + six methods
`score_confidence REAL DEFAULT -1.0` (unscored sentinel) / `score_verdict TEXT
DEFAULT ''` / `score_details TEXT DEFAULT '{}'` (lap-time delta, per-event
deltas, clean-lap counts, compounds both sides, before-source note). Methods:
`get_applied_unverified_recs` (car+track, **cross-layout guard** — differing
non-empty layout_id never compared), `get_laps_for_scoring`,
`get_previous_session_id`, `persist_score` (**write-once**),
`has_learning_for_car_track`, `get_scored_recs_for_prompt` (≥0.5, LIMIT 5).
The pre-existing `after_metrics` write-once contract is untouched.

### `ui/dashboard.py` — the trigger + the gate
`_trigger_scoring_pass(car_id, track, layout_id, new_session_id)` — never
raises, never blocks a session opening, zero `config["strategy"]` reads;
resolves the after-session, skips own-session recs, splits attribution,
queries driver feedback once (`get_recent_feedback`) for the confidence bonus,
persists, refreshes Home on ≥1 real verdict. Called after session-open in
`_on_live_mode_changed` (ev_ctx) and `_save_session_to_db` (wrc). And
`_build_home_dashboard_state` now derives **`learning_saved` from
`has_learning_for_car_track`** — journey step 13 is live, DB-derived, restart-proof.

### `strategy/driving_advisor.py` — the feedback-to-AI path
`_get_previous_ai_context` tries the scored block first
(`get_scored_recs_for_prompt` + `format_performance_block`); when non-empty it
**replaces** the free-text recommendation history (never both); defensive
fallback preserves the pre-feature behaviour exactly. No prompt wording changed
elsewhere; no new `config["strategy"]` read (layout key is the literal `''`,
matching how recommendations are stored).

## 4. Validator findings → fixes (all resolved, re-verified)

| Finding | Resolution |
|---|---|
| C1: mixed-signal override was dead code (impossible guard) | Restructured — the override now genuinely fires (Δt improved + agreement<0.3 → neutral); covered by test |
| I1: `has_driver_feedback` hardcoded False (bonus never activated) | Wired to `get_recent_feedback(car_id, track)`, once per run |
| I2: a new `config["strategy"]["layout_id"]` read in the advisor (story violation, invisible to the allowlist) | Removed (literal `''`); **and the allowlist scan extended to `strategy/driving_advisor.py`** with its 15 pre-existing legacy-bridge entries frozen — the gap is closed for good |
| m1/m2 minors | Stale test name fixed; oversteer-on-throttle delta added to the prompt block |

## 5. Honesty properties (tested)

- Thin data never fabricates: missing `before_metrics` or <3 clean laps →
  `insufficient_data` (confidence 0.0) — verified end-to-end through the trigger.
- Handling-targeted recommendations cannot be judged by lap time alone (two
  scenarios differing only in handling metrics flip the verdict — tested).
- Write-once: a second scoring run never rewrites a verdict.
- `applied`-but-never-executed recommendations resolve toward
  `insufficient_data`, never a confident verdict.
- The before-window is the recommendation's creation session (documented in
  `score_details.before_source` — it may pre-date application by design).

## 6. Tests

171 new tests across four files: `test_recommendation_scoring.py` (57 — verdict
matrix incl. the now-reachable mixed-signal branch, gates, split, bonus, block
rendering, purity), `test_recommendation_scoring_db.py` (45 — migration,
round-trip, write-once, layout guard, prompt-query filters),
`test_ofr1_trigger_wiring.py` (26 — source-scans + behavioural stubs incl.
feedback wiring), `test_ofr1_acceptance.py` (43 — one end-to-end test per AC +
edge cases). Schema-pin tests bumped 8→9; allowlist extended (+15 frozen
driving_advisor entries). **Full suite: 4948 pass / 6 skip / 0 fail**
(pre-feature baseline 4777).

## 7. Deferred / future

- **OFR-2** (race vs qualifying telemetry disciplines) — separate story.
- Loops 2–3 tables (prediction_log / compound_profiles / driver_weaknesses).
- A "was actually followed in GT7" detector (comparing in-game setup evidence);
  today `status='applied'` + honest gates carry that risk.
- Corner-level attribution (linking scores to corner_issues confidence).
- Any UI display of confidence/scoring history (data correctness was the
  deliverable; a Home/History surface can come later).

## 8. Next recommendation

Drive some sessions and let scores accumulate — the prompt block appears
naturally once the first ≥0.5-confidence verdicts exist. Next build candidates:
**OFR-2**, or a small History-tab surface for the scored recommendations.
