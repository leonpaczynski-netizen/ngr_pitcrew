# Current Claude Handoff

## Current Objective
**Group 47 — Setup Brain Outcome Verification & Learning Loop 2 — COMPLETE (2026-07-06).** Built on top of Group 46 (merged to master at `249410e`). Branch `group47-setup-brain-outcome-learning`. **The Setup Brain can now verify whether an approved, applied setup change actually helped after the next session — classifying the outcome as IMPROVED / UNCHANGED / WORSE / MIXED / INSUFFICIENT_EVIDENCE from before/after telemetry and (safely) driver feedback — and turn that into a one-step confidence/ranking nudge plus an honest explanation.** It remains rule-first, validator-gated, and AI-audit-only. **All Group 43–46 guarantees are intact:** Analyse and Baseline work AI-disabled; AI audit is explanation-only; the old AI Build path stays disabled; the Apply-gate predicate is UNCHANGED; only approved changes render/apply; rejected / blocked / low-confidence / unvalidated changes stay non-actionable. Learning affects **confidence/ranking/explanation only** — it authors no values, creates no fields, un-blocks nothing, overrides no validation, and never writes to `data/setup_history.json`.

**What shipped (Group 47):**

1. **Outcome verification model** — NEW **pure** module `strategy/setup_outcome_verification.py` (no PyQt / sqlite3 / AI / file I/O; never raises). `OutcomeVerdict` enum + `MetricSnapshot` (typed before/after per-lap telemetry) + `OutcomeVerificationResult` (`rule_id`, `car_id`, `track`, `layout_id`, `target_issue`, `before_metric`, `after_metric`, `driver_feedback`, `outcome`, `confidence`, `evidence_summary`, `safety_notes`). Deterministic per-issue checks for **exit-traction/wheelspin**, **bottoming/platform**, and **brake-stability**; **rotation** via oversteer proxy; **understeer/front-bite → INSUFFICIENT_EVIDENCE** (no steering-angle/rival metrics invented). `classify_driver_feedback` (better/worse/no_change/mixed/unknown). Telemetry-first, safety-first: positive feedback strengthens an upgrade only when telemetry agrees, **never** overrides a telemetry safety regression, and never manufactures IMPROVED on flat telemetry; negative feedback on flat telemetry downgrades; contradictory feedback → MIXED. `outcome_to_learning_verdict()` bridges to the Group 46 vocabulary (MIXED → neutral, INSUFFICIENT_EVIDENCE → skipped).

2. **Persistence (SQLite only)** — `_migrate_v13` (additive, idempotent; duplicate-column guard) adds 5 `TEXT NOT NULL DEFAULT ''` columns to `learning_outcomes`: `target_issue`, `evidence_summary`, `driver_feedback`, `safety_notes`, `outcome_kind`. `record_learning_outcome(...)` gained matching **keyword-only** params (defaults `''`) — every Group 46 caller keeps working. `DB_VERSION` → **13**. Old v12 DBs upgrade without data loss; learning never touches `data/setup_history.json`.

3. **Integration (additive, non-regressive)** — `ui/dashboard.py::_trigger_scoring_pass` derives the Group 47 verification per approved change (`_verify_change_outcome`) and stores the richer evidence alongside the record. **The confidence-feed `verdict` remains the telemetry OFR-1 verdict** (deliberately non-regressive). `driving_advisor` populates the `_learning_outcome_explanation` payload key via `format_learning_outcome_explanation()`.

4. **Explainability** — `ui/setup_builder_ui.py::_display_setup_result` renders a subdued outcome-verification block after the analysis card, gated on a non-empty backend string, always ending with the disclaimer that it adjusts confidence/ranking/explanation only and does not author values or bypass validation.

**Constants:** `DB_VERSION` 12 → **13**; `RULE_ENGINE_VERSION` stays **46.0** (Group 47 changes no rule proposals).

**Tests:** 4 new `tests/test_group47_{outcome_verification, feedback_learning, learning_persistence, ui_explainability}.py` (**73 tests**). Reconciled DB-version tests → 13 (`test_session_db`, `test_group18b_rec_persistence`, `test_group18e_setup_history`, `test_group42_legacy_storage`, `test_group46_learning_persistence`). Regression: Group 46 (106 non-UI + 16 UI isolated), Groups 38–45 non-UI (694), UI files individually — all green; AC37 RSR/Fuji benchmark green. Run UI files individually on Win/Py3.14 (known PyQt segfault); the pre-existing frozen-allowlist / OFR failures (incl. `test_recommendation_scoring_db::test_v9_schema_version`, which asserts the stale v10) are KNOWN, unrelated, and untouched.

**Deferred after Group 47 (honest):** the **live confidence feed still consumes the telemetry OFR-1 verdict**, not the feedback-aware Group 47 verdict (routing the model's verdict into the feed is a scoped follow-up, kept out to guarantee non-regression); understeer/front-bite/rotation-feel verification (no signal); `source_path="Baseline"` recording + `learning_outcomes.session_type` population (carried from Group 46); feedback negation handling. No new feature work was done in this task.

**Recommended manual UAT:** Porsche 911 RSR '17 at Fuji Full Course, high tyre + high fuel; run a session, Apply the approved traction-first change, drive another session, submit driver feedback (e.g. "fixed exit traction" or "rear still loose"), then re-Analyse and confirm the outcome-verification explanation appears and honestly reflects the before/after exit-traction telemetry + feedback.

**Docs:** `docs/RULE_FIRST_SETUP_BRAIN.md` (NEW § 16), `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 47), `docs/UAT_SETUP_BRAIN.md` (§ Group 47), `docs/PROJECT_STATE.md`, `MASTER_TESTING_REGISTER.md`.

---

## Prior Objective (historical)
**Group 46 — Setup Brain Learning & Race Context Intelligence — COMPLETE (2026-07-06).** Built on top of Group 45. Branch `ofr2-quali-race-disciplines`. **The rule-first Setup Brain now learns across sessions (a real SQLite-backed rule-outcome feed), and its ANALYSE recommendations are shaped by fuel load and by fuller per-gear telemetry; session type now numerically biases the from-scratch baseline; the Porsche pack inherits the new fuel/tyre/learning confidence layers.** The architecture is unchanged and preserved: telemetry + feedback + setup + car/track/session context + learning history → deterministic diagnosis → deterministic rule recommendation → validation → AI audit-only → approved-only display/apply. The AI still cannot author setup values, add approved fields, un-block, un-reject, or author per-gear values; Baseline and Analyse both work AI-disabled; the old AI Build path stays disabled; the Apply-gate predicate is UNCHANGED.

**What shipped (Group 46):**

1. **Cross-session learning persistence + feed** — a NEW SQLite table `learning_outcomes` (`data/session_db.py::_migrate_v12`; PRAGMA `user_version` 11→12; additive `CREATE TABLE IF NOT EXISTS`, idempotent). Columns: id, ts, car_id, track, layout_id, session_id, session_type, rule_id, source_path, verdict, confidence, driver_profile_version, rule_engine_version + an index on (car_id, track, layout_id). **DELIBERATELY NOT persisted to `data/setup_history.json`** — that file is a *user-local artifact* owned by `setup_history.py`; learning lives entirely in the gitignored DB (single owner, no user file churn, no accidental commit of local state). Methods: `record_learning_outcome(...)` (INSERT, never raises) written from the OFR-1 scoring pass in `ui/dashboard.py::_trigger_scoring_pass` after `persist_score`, per approved rule_id, skipping `insufficient_data`; `get_learning_outcomes(car_id, track, layout_id)` (returns `[]` on any error → safe fallback). **FEED:** `driving_advisor.build_combined_setup_response` loads the scoped rows into a real `RuleOutcomeStore` before `run_rule_engine` (improved → fire+success; worsened/neutral → fire; insufficient_data → skip). `_process_rule` threads car/track/profile_version with a key-aware lookup + empty-key fallback. **UPGRADE** (`>= MIN_OUTCOME_SAMPLES=3` samples AND success_rate `>= HIGH_SUCCESS_RATE=0.60` → +1 confidence step) and **DOWNGRADE** (`< LOW_SUCCESS_RATE=0.40` → −1), between = no change; both capped at one step, both validator-gated, both structurally unable to un-block / un-reject / author values. The `learning_influence` explainability string is set **only when a step actually happened** (honesty); `_learning_note` reflects the real loaded history.

2. **Fuel-multiplier influence (Analyse)** — `driving_advisor` injects `diagnosis["fuel_multiplier"]` (the value) + `diagnosis["fuel_high"]` (`>= HIGH_FUEL_MULTIPLIER_THRESHOLD=5.0`; unknown → False, never a false claim); previously only a `fuel_known` bool existed. `_process_rule` fuel layer: high fuel **UPGRADES** the confidence of traction/stability fields (`_FUEL_TRACTION_STABILITY_FIELDS` = lsd_accel, lsd_initial, arb_rear, aero_rear, ride_height_rear, with delta > 0); for rotation / aero-cut (`_FUEL_ROTATION_FIELDS`, delta < 0) it is **NOTE-ONLY** (no downgrade). **No new deltas** — ranking / confidence only. The `fuel_influence` string is set only when the effect occurred and is appended to the change's `evidence` list so it renders in the existing UI (keeps the at-most-2-new-rows constraint). Honesty: fuel = 1.0 or absent → no bias, no claim.

3. **Session-specific NUMERICAL baseline tuning** — `setup_baseline._SESSION_BIAS_TABLE` keyed qualifying / sprint / endurance / practice / unknown → `{field: delta}`, accumulated into the **same** bias dict as the driver-profile table so the existing clamp / round / validator apply unchanged. `_normalise_session_for_bias(session_type, duration_mins)`: qualifying / sprint (race & duration < 60 or unknown) / **endurance (race & duration_mins >= 60)** / practice / unknown; `duration <= 0` is NOT endurance. `build_baseline_setup` + `build_baseline_setup_response` gained a `duration_mins` param (threaded from the UI's `_ai_snap.duration_mins` / `EventContext.race_duration_minutes`). **Honesty:** a per-field `session_changed` flag compares the clamped/rounded output with vs without the session bias; the `session_influence` text claims a session bias **only for fields whose value actually moved** — known-session-but-unchanged → "session noted — no numerical change for this field"; unknown session → "". No false "session bias applied".

4. **Fuller per-gear intelligence (with REAL telemetry detection)** — `setup_diagnosis` now **genuinely detects** `wheelspin_by_gear` by bucketing per-frame wheelspin (throttle > 0.7, speed > 2 m/s, rear-wheel-speed > 1.3× vehicle speed) by the gear active at each frame, **normalized PER-LAP** (mirroring `rev_limiter_by_gear`). `bog_by_gear` is **honestly deferred = None** — GT7's 10 Hz telemetry lacks a reliable longitudinal-acceleration signal to detect bogging; `lockups_by_gear` also None. `setup_rule_engine._emit_per_gear_changes` proposes `gear_N` **only when a REAL indexed signal exists for gear N**: rev-limiter-in-gear (`per_gear_limiter_evidence[N] > 0` with `gearing_diagnosis_category == "gear_too_short"`) OR per-gear wheelspin (`wheelspin_by_gear[N] >= _PER_GEAR_WHEELSPIN_THRESHOLD=2.0` frames/lap). Conservative delta (±0.03, smaller than final_drive's ±0.05); gated on `gearbox_flag == "may_change"`; SAME clamp + strict-`>` monotonic (reject "monotonic ordering violation") + validator machinery; rule_id `"PG_{N}"`, `source_label` "per-gear rule". `final_drive` (B5/B5b) UNTOUCHED as the broad lever. `diagnosis["per_gear_explanation"]` records, for EVERY gear, proposed (+evidence) or not-proposed (+reason). "Top speed low" alone with no indexed evidence → NO gear change + an explanation saying why.

5. **Porsche 911 RSR '17 extension** — the existing Pack P (P1 traction-first lsd_accel, rr + gr3 scoped via `CAR_DRIVETRAIN_OVERRIDES`) **auto-benefits** from the new fuel / tyre / learning confidence layers (no new authored rule needed). Rear-downforce protection under instability is still provided by existing Pack A A2. **Benchmark AC37** (RSR / Fuji / 50 min / high tyre + high fuel / rear-loose + mid-push + floaty-front / snap-throttle wheelspin + top-speed-low + entry-stable + possible-bottoming) verified: **traction-first before/instead of aero-cut; no rear-downforce reduction; no rearward brake bias; no generic ride-height raise without bottoming confidence; no top-speed gear-lengthening as the primary wheelspin fix; no AI-authored values; passes the Apply gate.** `source_label` distinguishes Porsche-specific vs generic.

**Constants:** `RULE_ENGINE_VERSION` "45.0" → **"46.0"**; DB `user_version` 11 → 12 (`DB_VERSION=12`); `HIGH_FUEL_MULTIPLIER_THRESHOLD=5.0`; `HIGH_SUCCESS_RATE=0.60`.

**Tests:** 6 new `tests/test_group46_{learning_persistence, fuel_influence, baseline_session_modifiers, per_gear, porsche_pack, ui_explainability}.py` (**122 tests**, incl. the AC37 RSR/Fuji integrated regression, a fuel-renders-into-evidence test, and an AC16 single-winner-per-field learning-safety assertion). Reconciled version/schema tests: `RULE_ENGINE_VERSION` → 46.0 (`test_group42_rule_first_engine`); DB version → 12 (`test_group42_legacy_storage`, `test_group18b_rec_persistence`, `test_session_db`, `test_group18e_setup_history`). Run the suite **IN HALVES** (Win/Py3.14 PyQt segfault); the ~7–20 pre-existing frozen-allowlist / OFR failures are KNOWN, unrelated, and untouched.

**Docs:** `docs/RULE_FIRST_SETUP_BRAIN.md` (NEW § 15 "Setup Brain Learning & Race Context (Group 46)"), `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 46 changelog, cross-referencing § 15), `docs/UAT_SETUP_BRAIN.md` (§ Group 46 UAT), `docs/PROJECT_STATE.md`, `MASTER_TESTING_REGISTER.md` (Setup Brain Learning & Race Context (Group 46)).

**Deferred / limitations (honest, state clearly):**
- The **Baseline path does NOT consume rule-confidence learning** — it does not run the rule engine, so baseline change dicts carry an honest EMPTY `learning_influence`; learning shapes the ANALYSE path only.
- **`source_path` is effectively always "Analyse" in production today** — the baseline path does not insert a scored `setup_recommendations` row, so `source_path="Baseline"` is supported by the schema/method but not yet written; wiring baseline recording is DEFERRED.
- **`session_type` is stored as `""` on `learning_outcomes`** because `setup_recommendations` has no `session_type` column (scope is enforced by car_id + track + layout_id); a JOIN / column is deferred.
- **`bog_by_gear` + `lockups_by_gear` per-gear detection** deferred — no genuine telemetry signal (10 Hz, no reliable longitudinal-accel channel); per-gear evidence today is limiter + wheelspin only.
- A fuel-specific *delta* rule (fuel is confidence/ranking-only, not a new change); the old `build_car_setup` AI-authoring path remains dead-in-tree behind the Group 43 guards; the pre-existing frozen-allowlist / OFR failures remain for their owners.

**Next:** drive the RSR at Fuji across repeated matching sessions and confirm (a) the learning note/influence appears only once ≥3 matching-context outcomes exist and a step actually fires; (b) quali vs sprint vs endurance baselines differ numerically; (c) high fuel prioritises traction/stability changes in the ordering; (d) per-gear changes appear only on real indexed evidence. Build candidates: wire baseline rule-confidence learning + `source_path="Baseline"` recording; add a `session_type` column/JOIN to populate learning scope; genuine per-gear bog/lockup detection if a signal appears; a fuel-specific delta rule.

---

## Prior Objective (historical)
**Group 45 — Setup Brain Intelligence Expansion — COMPLETE (2026-07-06).** Built on top of Group 44. Branch `ofr2-quali-race-disciplines`. **The rule-first Setup Brain is now context-aware: session type, tyre-wear, drivetrain, and car-class genuinely shape which rules fire and how confident/ranked they are — WITHOUT inventing precision (delta magnitudes are unchanged; context affects filtering, confidence, ranking, contraindication, and explanation only).** The architecture is unchanged and preserved: Pit Crew owns the decision, the AI stays audit-only (`parse_audit_response` strips canonical params; `map_audit_to_finaliser` never un-blocks; voice narration-only); both Analyse and Baseline still run through one validator → finalisation funnel → renderer → Apply gate; the old AI build path stays disabled; everything works with AI disabled.

**What shipped (Group 45):**

1. **Engine scope filter** (`strategy/setup_rule_engine.py::_scope_matches`) — rules already carried `applies_session` / `applies_drivetrain` / `applies_car_class` but the engine ignored them; now enforced at runtime. `any` / `None` context = **wildcard-permissive** (unknown never filters). **Pack A safety rules are EXEMPT** from scope filtering. All-rules-filtered-out returns a **valid empty `SetupPlan`** (no raise). Closes the Group 42/43 "scope fields set but not honoured" deferral.

2. **Context resolution** (`strategy/driving_advisor.py`) — Analyse reads `_event_ctx` (tyre_wear → tyre_wear_multiplier, fuel_multiplier, duration_mins for endurance) and new params `purpose` → `SessionType`, `car_specs.category` → `CarClass`, `drivetrain`. **Drivetrain precedence:** explicit UI combo > `CAR_DRIVETRAIN_OVERRIDES` (in-module dict, currently `{"Porsche 911 RSR (991) '17":"rr"}`) > empty DB → `None` (generic). Baseline receives **scalar** params only (`session_type`, `tyre_wear_multiplier`, `car_class`) — **NO EventContext injected**. Both UI analyse handlers (`_setup_analyse_ai`, `_setup_analyse_ai_for_form`) and both baseline callers thread these.

3. **Driver-profile active weighting** (`setup_rule_engine.py`) — a bounded {−1, 0, +1} rank bonus used as a **conflict-resolution tiebreaker when confidence is equal** (all `rule.driver_style_tags ⊆ profile.style_tags` → +1; `dislikes_snap_exit` + lsd_accel increase → hard block + −1). **Magnitudes/deltas are UNCHANGED** (no fake precision) — driver style affects ranking / confidence / explanation only. Baseline `_PROFILE_BIAS_TABLE` gained `trail_braker` → brake_bias −0.5 and `rotation_without_snap` → lsd_decel −2.

4. **Session / tyre / fuel intelligence** — session type **biases confidence** (quali upgrades front-bite / trail-braker-tagged rules; race upgrades safety-phase / consistency rules; endurance = race + `duration_mins>=60`). `HIGH_TYRE_WEAR_THRESHOLD=5.0` → `tyre_wear_multiplier>=5.0` sets `diagnosis["tyre_wear_high"]`, which **CONTRAINDICATES (suppresses) 4 genuinely tyre-abusing rules**: B3 (lsd_accel decrease), C1_entry_lsd_decel (lsd_decel decrease), C3_mid_arb_rear (rear ARB soften), C7_kerb_arb_rear (rear ARB soften). Rules that **increase** lsd lock or rear downforce are deliberately **NOT** suppressed (they stabilise worn tyres). Missing tyre/fuel context → honest "tyre/fuel context not available — conservative default applied", **NO** tyre/fuel-aware claim. Fuel multiplier is **READ** (`fuel_known` flag) but currently **only informational** — no fuel-specific rule yet.

5. **Drivetrain / car-class modifiers** — `applies_drivetrain` (fr/ff/mr/rr/awd) and `applies_car_class` (gr1..gr4/road/race) filters enforced. Car class comes from `car_specs.json.category` (available for **579 cars**). Drivetrain is **NOT** reliably in per-car data — it comes from the manual UI combo or `CAR_DRIVETRAIN_OVERRIDES`; unknown drivetrain → generic logic + honest "drivetrain unknown — generic logic applied".

6. **Porsche 911 RSR '17 pack (Pack P)** — `register_pack("P",...)`. **Rule P1**: cautious lsd_accel increase (traction-first), scoped `applies_drivetrain=rr` + `applies_car_class=gr3`, precondition snap-throttle wheelspin, **contraindicated** when `snap_oversteer_exit` is diagnosed. Rear-downforce protection under rear instability is already provided by existing **Pack A A2** (unconditional, all cars), so a separate Porsche P2 was **intentionally OMITTED** (A2 covers it). Ride-height raise is gated by existing A3/A4 (no generic raise). Top-speed deficit under wheelspin is handled **traction-first** (P1), not aero-cut-first (A2 blocks the cut). Every change is labelled `source_label` "Porsche-specific rule" (pack P) or "generic rule". The pack **asserts RR via `CAR_DRIVETRAIN_OVERRIDES`** (the empty DB drivetrain column is NOT relied on); the manual UI combo overrides it.

7. **Gearbox intelligence** — B5 (gear_too_short → final_drive_down) plus **new B5b** (gear_too_long → final_drive_up). `limiter_limited` stays a preserve category (no proposal). **NOTE:** the sprint's "limiter_before_braking" is **NOT** a real diagnosis category — it maps to the existing `gear_too_short` (documented, not faked). Per-gear evidence: diagnosis now exposes `per_gear_limiter_evidence` (alias of `rev_limiter_by_gear`); individual `gear_N` changes are only ever proposed with gear-specific evidence — **full per-gear rules remain DEFERRED** (final-drive-only broad logic today). Monotonic ordering is enforced **NON-INCREASING**: equal adjacent ratios are **ALLOWED**; only a strict inversion is rejected with reason "monotonic ordering violation" (engine AND the `gearbox_ratio_inversion` validator both use strict `>` now, in agreement).

8. **Learning seam** — production now constructs a live-but-**EMPTY** `RuleOutcomeStore` (was `None`); the confidence-downgrade hook is wired but **never fires without samples**, so behaviour is unchanged. Response carries `_learning_note` "no cross-session learning history available". Cross-session persistence + a success-recording feed (e.g. from OFR-1 `recommendation_scoring` verdicts) remain **DEFERRED**. Learning can only lower a confidence label / affect ranking — it **CANNOT** un-block a blocking safety rule, un-reject a rejected change, bypass validation, or make the AI actionable.

9. **Explainability** — each approved change and each rejected candidate now carries `source_label`, `session_influence`, `car_drivetrain_influence`, `pack` (plus the pre-existing symptom/evidence/rule_id/rationale/risk_level/confidence_level/driver_style_alignment). Populated **HONESTLY** — a positive session/tyre/car claim appears only when that context was received AND used; missing context yields the explicit neutral/"not available" string. Baseline changes carry `_LABEL_NEUTRAL`/`_LABEL_BIASED`/`_LABEL_MIDPOINT`/`_LABEL_CONSERV` and never claim telemetry evidence. The renderer shows a small `source_label` row. Baseline `session_influence` text is honest: it records that a session was noted but that the baseline is **NOT session-tuned** (no session-specific baseline bias is applied — deferred); baseline bias is **driver-profile-driven only**.

**Constants:** `RULE_ENGINE_VERSION` is now **"45.0"** (was "42.0"); `HIGH_TYRE_WEAR_THRESHOLD=5.0`.

**Tests:** NEW `tests/test_group45_engine_scope.py`, `test_group45_gear_monotonic.py`, `test_group45_context_signals.py`, `test_group45_porsche_pack.py`, `test_group45_explainability.py`, `test_group45_learning.py`, `test_group45_baseline_context.py`, `test_group45_ui_context.py`. Reconciled **3 existing tests** for legitimate behaviour changes (`RULE_ENGINE_VERSION` "42.0"→"45.0"; baseline lsd_decel bias now nets differently with `rotation_without_snap`; the gearbox inversion validator now strict-`>` allowing equal ratios). **All Group 45 tests pass**; the ~18 pre-existing frozen-allowlist / schema failures are KNOWN, unrelated, and untouched. Run the suite **IN HALVES** on Win/Py3.14 (flaky PyQt teardown segfault).

**Docs:** `docs/RULE_FIRST_SETUP_BRAIN.md` (§ Group 45 + the dedicated **"Setup Brain Intelligence Expansion"** section), `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 45 — Pack P / B5b / tyre-wear contraindications, cross-referencing the dedicated section), `docs/UAT_SETUP_BRAIN.md` (§ Group 45 UAT), `docs/PROJECT_STATE.md`, `MASTER_TESTING_REGISTER.md` (Setup Brain Intelligence Expansion (Group 45)).

**Deferred / limitations (honest, state clearly):**
- Cross-session `RuleOutcomeStore` persistence + a success-recording feed (seam in place, EMPTY in production — no behaviour change yet).
- Full per-gear individual ratio proposal rules (final-drive-only broad logic today; `per_gear_limiter_evidence` key exists for future use).
- Session-specific **NUMERICAL** baseline tuning (session context is recorded on baseline changes but does not yet change baseline values).
- Fuel multiplier is read but only informational (no fuel-specific rule yet).
- The two opposing lsd_decel baseline bias entries (`race_values_consistency` +2 vs `rotation_without_snap` −2) net to zero on a driver profile that has both flags.
- The old `build_car_setup` AI-authoring path remains dead-in-tree behind the Group 43 guards; the ~18 pre-existing frozen-allowlist / schema failures remain for their owners.

**Next:** drive quali vs race sessions on the RSR at Fuji and confirm the recommendations differ by session/tyre-wear and carry honest `source_label` / `session_influence` / `car_drivetrain_influence` fields (`docs/UAT_SETUP_BRAIN.md` § Group 45). Build candidates: wire a real cross-session `RuleOutcomeStore` feed from OFR-1 `recommendation_scoring` verdicts + persist it; full per-gear ratio rules using `per_gear_limiter_evidence`; session-specific numerical baseline tuning; a fuel-specific rule; more car packs.

---

## Prior Objective (historical)
**Group 44 — Rule-First From-Scratch Setup Baseline Generator — COMPLETE (2026-07-06).** Built on top of Group 43. Branch `ofr2-quali-race-disciplines`. Delivered via the feature-factory chain. **Restores the capability lost when Group 43 disabled "Build Setup with AI" — the app can now author a COMPLETE safe starting setup for a car with NO telemetry, deterministically, with the AI NEVER called.** A new **"Build Baseline Setup"** button (`_btn_baseline`) sits separate from the still-disabled `_btn_build_setup` (Group 43 guards untouched).

**Why a new module (not `run_rule_engine`):** `run_rule_engine` emits DELTAS off a telemetry diagnosis; with no telemetry almost no rules fire, so it cannot author a from-scratch full-field setup. A separate ABSOLUTE-VALUE author was required.

**Backend — `strategy/setup_baseline.py` (NEW):**
- `NEUTRAL_SEEDS` — single source of truth for neutral physics defaults (matches the form seeds in `ui/setup_form_widget.py`; note: lsd_front_initial/accel/decel take the FORM values 10/15/5, which differ from `ai_planner` parser fallbacks 0/0/0).
- `build_baseline_setup(car, ranges, drivetrain, num_gears, profile, allowed_tuning, tuning_locked) -> raw_data dict` (plan_to_raw_data shape). Authors ALL 33 actionable `_CANONICAL_SETUP_PARAMS` (34 minus display-only transmission_max_speed_kmh) as ABSOLUTE values: neutral seed → driver-profile bias (`_PROFILE_BIAS_TABLE`: prefers_rear_stability→arb_rear−1/toe_rear+.05; dislikes_snap_exit→lsd_accel−2; prefers_front_bite→arb_front+1/toe_front−.02; dislikes_floaty_front→aero_front+50; protects_downforce→aero_rear+50; race_values_consistency→lsd_decel+2) → clamp to `resolve_ranges(car)`.
- **Gearbox** (`_build_gearbox_changes`): final_drive = midpoint of `_FINAL_DRIVE_RANGE (2.5,6.0)`; gear_1..gear_num_gears = a strictly-DECREASING geometric sequence inside `_GEAR_RATIO_RANGE (0.5,4.0)` (monotonic by construction, so `gearbox_ratio_inversion` can never fire), sized to the car's gear count (>6 capped, ≤1 → single gear@2.0, 0 → none). Gearbox ranges are function-local-imported from `setup_diagnosis` (source of truth, try/except fallback to local constants).
- **Locked categories** (via `_derive_locked_fields`) are excluded from actionable output and named by human category (e.g. "Suspension, Aero") in the analysis text; tuning_locked=True → empty changes (UI disables the button first).
- Every change carries a **source label**: "neutral default" / "range midpoint" / "driver-profile biased" / "conservative default, not diagnosed". The last is honest: camber/toe/dampers/springs/lsd_initial/lsd_front_initial have NO engineering authority — the baseline is a safe STARTING POINT, not an optimum.

**Orchestrator — `DrivingAdvisor.build_baseline_setup_response(car_name, ranges, drivetrain, num_gears, allowed_tuning, tuning_locked, session_type="Race") -> JSON str`:** `build_driver_profile()` → `build_baseline_setup` → `validate_setup_engineering_structured` (neutral baseline passed as BOTH the `setup` arg AND the proposed setup_fields so increment/comparison rules see zero delta) → `_filter_baseline_artifact_warnings` (drops ONLY WARNING-severity failures whose message contains "is a no-op" or "too many changes" — definitional artifacts of a full-field from==to baseline; ALL blocking failures pass through unfiltered — the severity guard `if vf.severity == "warning"` is the outer condition, proven unable to suppress a blocking failure) → `_finalise_recommendation` → JSON identical in shape to `build_combined_setup_response`. **NO api_key read, NO call_api, NO audit.** A clean neutral baseline returns status "approved" with validation_warnings == [].

**Frontend:** new `_btn_baseline` "Build Baseline Setup" (enabled+visible; added to `_RACE_ALIASES`) in `ui/setup_form_widget.py` + `ui/setup_builder_ui.py` handlers `_generate_baseline_setup` / `_generate_baseline_setup_for_form` (daemon thread → `_baseline_result_queue` in `ui/dashboard.py`, polled) → `_display_baseline_result` re-enables the baseline button then DELEGATES to the shared `_display_setup_result` renderer + Apply gate (no duplication). Advisor accessor `self._driving_advisor`. Group 43 `_btn_build_setup` / `_run_build_setup*` guards untouched.

**Tests:** `tests/test_group44_baseline_generator.py` (86 backend) + `tests/test_group44_baseline_ui.py` (64 UI/integration). Final: **406 green** together with group41 + group42 (all) + group43; 0 fail. The 8 pre-existing frozen-allowlist track-modelling failures are unrelated and untouched. Run the suite in halves on Windows/Py3.14 to avoid the flaky PyQt teardown segfault.

**Docs:** `docs/RULE_FIRST_SETUP_BRAIN.md` (§ Group 44 — the baseline generator as an additional rule-first authoring path), `docs/PROJECT_STATE.md`, `MASTER_TESTING_REGISTER.md` (Rule-First Setup Baseline Generator (Group 44)).

**Deferred / limitations (honest):** `_btn_baseline` is enabled-at-construction with a runtime car/track guard (no proactive disable) — consistent with `_btn_analyse_setup`; the shared renderer also re-enables `_btn_analyse_setup` after a baseline (harmless); the symptom label "no telemetry baseline" is generic even on driver-profile-biased fields; the no-authority fields are conservative defaults, not engineered; the old `build_car_setup` AI-authoring path remains dead-in-tree behind the Group 43 guards.

**Next:** run a manual baseline for a fresh car and confirm every category fills with safe values and Apply pushes them into the form. Build candidates: wire `RuleOutcomeStore` live-learning + persistence; per-car gearbox ratio bounds (promote `gearbox_out_of_range` to blocking); track-type biasing of the baseline.

---

## Prior Objective (historical)
**Group 42 — Rule-First Setup Brain — COMPLETE (2026-07-05).** Built on top of Group 41. Branch `ofr2-quali-race-disciplines`. **The Setup Brain is inverted from AI-first to RULE-FIRST.** Deterministic race-engineering rules are now the PRIMARY source of setup recommendations; the AI is demoted to an **audit-only** layer that can approve / warn / reject / request-more-data but **CANNOT author actionable setup changes**. The app now has ONE source of truth for actionable setup recommendations: the deterministic rule engine. **Backend + UI + DB.** All Group 42 tests green (136 new + 17 rewritten).

**Why it matters:** previously the AI authored the setup and the validator only gated it — an AI hallucination could still shape *what* changed. Now the rule engine authors a plan from diagnosis + driver profile + engineering rules; the AI can only comment on it. This makes recommendations deterministic, driver-aligned, and consistent between runs. **This closes the previous sprint's caveat** where a recommendation with an absent/unknown status could default to approved — such a recommendation is now `legacy_unknown` = DISPLAY-ONLY, no Apply.

**The new flow** (`build_combined_setup_response`, the canonical Setup Builder "Analyse" path): diagnose (`build_setup_diagnosis`) → `build_driver_profile()` → `run_rule_engine()` → `SetupPlan` → `plan_to_raw_data` → `_normalise_changes` → `validate_setup_engineering_structured` → **if blocking: `_build_deterministic_fallback` (NOT AI)** → else if API key present: `call_api` for **AI AUDIT ONLY** → `parse_audit_response` (strips any canonical setup field keys) → `map_audit_to_finaliser` → `_finalise_recommendation` (the unchanged single funnel) → response JSON.

**New backend modules (all `strategy/`, pure Python):**
- **`setup_knowledge_base.py`** — the rule catalogue. `register_pack`/`get_all_rules`/`resolve_delta`; enums `RulePhase`/`RiskLevel`/`ConfidenceLevel`/`DrivetrainType`/`CarClass`/`SessionType`; NamedTuples `SetupRule`, `SetupEvidence`. **22 rules**: Pack A (A1–A8, safety invariants), Pack B (B1–B6, driver-style adaptation), Pack C/D (C1_entry_lsd_decel, C2_entry_brake_bias, C3_mid_arb_rear, C4_mid_rear_aero, C5_exit_lsd_accel, C6_exit_rear_aero, C7_kerb_arb_rear, C8_kerb_rh_rear — the handling-phase starter set, extensible via `register_pack`; the remaining per-setting Pack C rules are deferred). Delta resolvers are named-string lookups in `_DELTA_RESOLVERS` (no stored callables).
- **`setup_driver_profile.py`** — `DriverProfile` NamedTuple + `DriverStyleAlignment` enum; `build_driver_profile()` derives booleans (prefers_front_bite, dislikes_floaty_front, dislikes_snap_exit, trail_braker, rotation_without_snap, prefers_rear_stability, protects_downforce, race_values_consistency) from the existing `PERSONAL_DRIVER_TUNING_MODEL` / `DRIVER_HARD_CONSTRAINTS` constants; **never raises** (neutral defaults on error). Driver style is now a **DATA STRUCTURE** consumed by the engine for ranking + contraindications, not just prompt text.
- **`setup_rule_engine.py`** — `SetupChangeIntent`, `SetupPlan` NamedTuples; `run_rule_engine(diagnosis, setup, ranges, profile, allowed_tuning=None, rule_outcome_store=None) -> SetupPlan` (Pack A protects fields; conflict resolution moves both same-field opposite candidates to rejected with `conflict:<id>`; no-op exclusion; gear-count gating; confidence-downgrade hook); `RuleOutcomeStore` (fire/success counts keyed by rule_id/car/track/driver_profile_version; `get_success_rate` returns None below `MIN_OUTCOME_SAMPLES`). **Never raises** → empty plan on error.
- **`setup_plan.py`** — `plan_to_raw_data` (emits the raw_data dict the existing funnel consumes, including confidence + validation_targets so the engineering validator's schema check passes), `rejected_to_json`.
- **`setup_ai_audit.py`** — `AuditStatus` enum (APPROVED / APPROVED_WITH_WARNINGS / REJECTED / NEEDS_MORE_DATA), `AuditResult` NamedTuple; `build_audit_prompt` (8 labelled sections: diagnosis, plan, evidence, rules-fired, rejected candidates, protected fields, current setup, driver profile + validation result + audit instructions); `parse_audit_response(response_text, canonical_params)` **strips any key in canonical_params** (logs stripped_fields), unknown status → NEEDS_MORE_DATA, never raises; `map_audit_to_finaliser` (REJECTED / NEEDS_MORE_DATA + no blocking → approved_with_warnings advisory; **a blocking engineering failure ALWAYS wins**).

**Constants** added to `strategy/_setup_constants.py`: `RULE_ENGINE_VERSION="42.0"`, `MIN_OUTCOME_SAMPLES=3`, `LOW_SUCCESS_RATE=0.40`, `AI_AUDIT_REJECTED_ADVISORY="ai_audit_rejected_advisory"` (NOT in APPROVED_STATUSES). `APPROVED_STATUSES` unchanged = {approved, approved_with_warnings, fallback_generated}.

**Voice path** (`build_setup_advice_response`): constrained to NARRATION-ONLY via new `_strip_actionable_for_voice(data)` which zeroes `changes=[]` / `setup_fields={}` before normalisation — the voice path can never surface AI-authored actionable setup changes. A full rule-first rebuild of the voice path is DEFERRED.

**DB (v11):** `data/session_db.py::_migrate_v11` bumps user_version to 11 and adds 8 nullable TEXT columns to `setup_recommendations` (deterministic_plan_json, ai_audit_json, validation_status, approved_changes_json, rejected_changes_json, diagnosis_json, driver_profile_version, rule_engine_version); the recommendation_text JSON blob is preserved. These are now POPULATED on insert (via `strategy/_rec_parser.py` + `insert_setup_recommendations`). Full migration off the JSON blob remains deferred.

**Legacy safety (closes Group 41's caveat):** `data/setup_history.py` adds `is_legacy_unknown` / `normalise_validation_status` / `LEGACY_UNKNOWN`. A recommendation whose status is absent/None/unrecognised is now treated as **legacy_unknown = DISPLAY-ONLY, NO Apply** (previously an absent status could default to approved — that hole is closed, enforced in `_display_setup_result` and gated at the Apply button). The `_rejected_` bucket routing is preserved (`ai_audit_rejected_advisory` routes there).

**Learning layer:** `RuleOutcomeStore` is **FOUNDATION ONLY** — the confidence-downgrade hook (samples ≥ MIN_OUTCOME_SAMPLES and success_rate < LOW_SUCCESS_RATE → downgrade one confidence step) is implemented and unit-tested, but **live wiring + cross-session persistence is DEFERRED** (`build_combined_setup_response` passes `rule_outcome_store=None` today). No fake ML — a deterministic weighted counter only.

**UI** (`ui/setup_builder_ui.py::_display_setup_result` + `ui/setup_form_widget.py`): section order diagnosis → **"Pit Crew recommendation"** (approved changes, each with a collapsed **"Why Pit Crew recommended this"** details block showing symptom / rationale / evidence / rejected_alternatives / risk_level / confidence_level / driver_style_alignment) → **"Protected fields (Pit Crew will not change these)"** → **"Rejected candidate changes (not applied)"** → **"AI audit"** (verdict + concerns) → **"Rejected AI output — not for use"**. Legacy banner "Legacy recommendation — display only, cannot apply". The Apply button is relabelled **"Apply Pit Crew recommendation"**, hidden unless status ∈ APPROVED_STATUSES AND approved changes present AND not legacy.

**Response JSON contract:** per-change explainability keys live INSIDE each item of the `changes` list — symptom, evidence (list), rule_id, rationale, rejected_alternatives (list), risk_level (low/med/high), confidence_level (low/med/high), driver_style_alignment (aligned/neutral/caution). New top-level keys: `ai_audit`, `deterministic_plan` {proposed_count, rejected_candidate_count, protected_fields}, `protected_fields`.

**Tests:** 136 new across `tests/test_group42_rule_first_engine.py`, `test_group42_ai_audit_only.py`, `test_group42_driver_style.py`, `test_group42_legacy_storage.py`, `test_group42_handling_phases.py`, `test_group42_voice_path_safety.py`, `test_group42_ui_gate.py` — plus 17 rewritten (test_group38 TestRegenerateOnceOrchestration, test_group40 TestAC9DeterministicFallback, test_group41 ×2, test_group27 ×1). All green. The 8 pre-existing frozen-allowlist track-modelling failures are unrelated and untouched. Run tests in halves on Win/Py3.14 to avoid the flaky PyQt teardown segfault.

**Docs:** `docs/RULE_FIRST_SETUP_BRAIN.md` (NEW — the architecture doc), `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 42), `docs/UAT_SETUP_BRAIN.md` (Rule-First Setup Brain UAT section), `MASTER_TESTING_REGISTER.md` (Rule-First Setup Brain (Group 42)), `docs/PROJECT_STATE.md`.

**Deferred / limitations:** `RuleOutcomeStore` live wiring + cross-session persistence (foundation only today); the remaining per-setting Pack C rules (C/D is a handling-phase starter set); full DB migration off the recommendation_text JSON blob; full rule-first rebuild of the voice path (constrained to narration-only for now); the 8 pre-existing track-modelling allowlist failures remain for the track-modelling owner.

**Next:** run the Rule-First manual UAT (Porsche 911 RSR '17 at Fuji — `docs/UAT_SETUP_BRAIN.md`) to confirm the rule engine authors safe driver-aligned traction/LSD changes and the AI audit cannot author changes; build candidates: wire + persist `RuleOutcomeStore` (live learning loop); the remaining Pack C per-setting rules; a human-readable DB rec store; return to OFR strategy telemetry (Phase 2-B/2-C).

---

## Prior Objective (historical)
**Group 41 — Setup Builder Engineering Validation Gate — COMPLETE (2026-07-05).** Built on top of Group 40. Branch `ofr2-quali-race-disciplines`. Full suite: **5505 pass / 8 fail / 6 skip** — the 8 failures are the SAME pre-existing frozen-allowlist guard tests (`ui/track_modelling_ui.py::_tm_restore_last_track`, track-modelling tech debt, NOT this sprint), zero new regressions. **Backend + UI** (this sprint DOES have a UI surface — the display-safety gate in the Setup Builder). Test-run note: running the ENTIRE suite in one process can hit a flaky native PyQt teardown segfault on Windows/Python 3.14; running in two halves (or by group) completes clean at 5505 pass / 8 pre-existing fail — an environmental test-isolation artifact, not a product defect.

**What it does:** a hard gate between the AI's raw setup output and what the driver can see or apply. NEW RECOMMENDATION LIFECYCLE with explicit statuses (generated, validation_failed, retry_requested, retry_failed, approved, approved_with_warnings, fallback_generated, blocked_no_safe_recommendation; `APPROVED_STATUSES = {approved, approved_with_warnings, fallback_generated}` in the new `strategy/_setup_constants.py`). SINGLE FINALISATION FUNNEL `_finalise_recommendation` (driving_advisor.py) — both AI paths (`build_setup_advice_response`, `build_combined_setup_response`) route through it, producing a frozen `SetupRecommendationResult` dataclass (status/approved_changes/approved_fields/rejected_changes/analysis/primary_issue/engineering_errors/validation_warnings/fallback_used/raw_json), embedded into the returned JSON (recommendation_status, changes, setup_fields, rejected_changes, engineering_validation_errors, validation_warnings, fallback_used). DISPLAY SAFETY (`ui/setup_builder_ui.py::_display_setup_result`): "CHANGES TO MAKE IN CAR SETUP" renders ONLY when status ∈ APPROVED_STATUSES and approved_changes non-empty (iterates approved_changes only); Apply button HIDDEN (not disabled) unless approved-ish with non-empty approved_fields, applies approved_fields only via `SetupFormWidget.apply_ai_fields`; rejected output only in a collapsed "Rejected AI output — not for use" section (validation_failed/retry_failed/blocked_no_safe_recommendation), no apply path. VALIDATOR SEVERITY: `ValidationFailure(code, message, severity)` + `validate_setup_engineering_structured()` (legacy `validate_setup_engineering` still byte-identical prefixed strings); ANY blocking-severity failure (safety-prefix OR structural — malformed_schema/invalid_units/locked-field) forces validation_failed (retry_failed if retried) + approved_changes=[]; out-of-range is a WARNING because clamping forces the applied value back into range. NEW BLOCKING RULES: `snap_throttle_lsd_accel_gate` (snap_throttle_induced + lsd_accel > 4), `kerb_strike_rh_over_increment` (kerb_strike bottoming + rear RH increase > 3mm), `gearbox_fake_field` (transmission_max_speed_kmh as actionable), `gearbox_ratio_inversion` (a gear ratio not strictly lower than the gear below). NEW WARNING: `gearbox_out_of_range` (final_drive outside 2.5–6.0 or gear outside 0.5–4.0 — invented constants pending per-car data). REAL GEARBOX FIELDS: final_drive + gear_1..gear_6 now actionable (in `_CANONICAL_SETUP_PARAMS` + `_CAT_FIELDS["transmission"]`; `_normalise_changes` expands `gear_ratios:[...]` into gear_N keys; via SetupFormWidget); transmission_max_speed_kmh DEMOTED to display-only (`_DISPLAY_ONLY_FIELDS`) — readable for diagnosis/top-speed classification, stripped from approved output, never actionable; `gearbox_category_mismatch` now also blocks final_drive/gear_1..6 on a preserve gearing category. STRICT RETRY CONTRACT: `_build_retry_prompt` lists each blocking failure code + max delta + forbidden fields + forbids repeating rejected changes; retry with any blocking failure → retry_failed (never approved); banner reworded "AI recommendation rejected after retry" (was "survived a correction attempt"). DETERMINISTIC FALLBACK ENGINE (`_build_deterministic_fallback`) now emits 1–3 real conservative changes passing the same validator (RH-increment/LSD-subtype/rake gates); nothing safe → blocked_no_safe_recommendation + "run more laps". PERSISTENCE: `data/setup_history.py::save_entry` takes `validation_status`, routing non-approved to a `_rejected_<config_id>` diagnostic bucket; DB `setup_recommendations` row carries the final lifecycle status (`strategy/_rec_parser.py` extracts recommendation_status, was default 'proposed'). WORDING/LOGIC FIXES: kerb_strike bottoming distinct from true floor contact (no longer forces RH "required"); snap_throttle_induced no longer asserts "inside rear spins" (no telemetry), classified mixed setup/driver; old "top speed below target ⇒ no gearing change" leakage removed. DEDUP: `_ENG_SAFETY_PREFIXES` → shared `ENG_SAFETY_PREFIXES` in `_setup_constants.py`. AMENDMENT B: redundant read-only "Race Conditions (from Event Planner)" group box removed from the Setup Builder header (duplicated Event Planner + Home Race Setup card, same EventContext); 320px header cap lifted; `_sync_setup_builder_from_event` retains all functional side effects (BoP toggle, permissions, spinbox rebind, RE-brief load, prefill, qual-form sync). AMENDMENT C: Home "Race Setup" card now shows a Damage line (`EventContext.damage`).

**Tests:** `tests/test_group41_validation_gate.py` (NEW, AC0–AC14). Full detail: `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 41), `docs/UAT_SETUP_BRAIN.md` (manual checklist), `MASTER_TESTING_REGISTER.md` (Setup Builder Engineering Validation Gate).

**Deferred / limitations:** gearbox ratio ranges (final_drive 2.5–6.0, gears 0.5–4.0) are invented constants, not per-car data → `gearbox_out_of_range` is a WARNING not a hard block (tighten to per-car ranges + blocking once range data exists); the DB `_rec_parser` stores the full JSON blob as recommendation_text for structured setup responses (pre-existing, not human-readable in the DB); flaky full-suite PyQt segfault on Windows/Py3.14 (run in halves); UI readout for the Group 39/40 diagnosis keys still a follow-on; the 8 pre-existing track-modelling allowlist failures remain for the track-modelling owner.

**Next:** run the manual UAT (Porsche 911 RSR '17 at Fuji — `docs/UAT_SETUP_BRAIN.md`) to confirm the gate blocks unsafe recommendations and hides the Apply button; build candidates: per-car gearbox ranges to promote `gearbox_out_of_range` to blocking; a human-readable DB rec store; return to OFR strategy telemetry (Phase 2-B/2-C).

---

## Prior Objective (historical)
**Group 40 — Setup Diagnosis Hardening — COMPLETE (2026-07-05).** Built on top of Group 39 (Setup Brain Upgrade). Branch `ofr2-quali-race-disciplines`. Full suite: **5359 pass / 6 skip / 8 fail** — the 8 failures are ALL pre-existing frozen-allowlist guard tests (track-modelling tech debt, unchanged from before this sprint), zero new regressions. **Backend-only; no UI surface.**

**What it does:** Three new deterministic keys added to every diagnosis path (normal, conservative, and format-for-prompt): `bottoming_confidence` (band/subtype/confidence dict via `_classify_bottoming_confidence`), `driver_feel_traction_status` (string via `_derive_driver_feel_traction_status`), `aero_rear_healthy` (bool: `aero_rear_value >= 0.80 × hi`, fraction-of-max, with generic-range guard for no-aero cars). Four new engineering-validation rules: `rh_increment_exceeds_confidence` (cap RH delta to what `_rh_permitted_increment` permits for the bottoming band), `rh_rake_risk` (rear RH raised >= 4 mm with no front change — fires in both `validate_setup_engineering` and the structural `_validate_setup_response` in driving_advisor.py), `lsd_large_change_gated` (subtype-gated delta cap on LSD accel changes), `lsd_blocked_driver_feel` (blocks LSD accel increase when traction_status=="good"). `lsd_reversal_without_evidence` hardened: delta >= 5 guard added + `delta=N` appended to reason string. `_derive_dominant_problem` and `_derive_tuning_priority` now respect `aero_rear_healthy` — when True, the rear-traction-aero path is suppressed and mechanical wheelspin prioritised instead. Deterministic fallback (`_build_deterministic_fallback`) invoked in `build_setup_advice_response` and `build_combined_setup_response` when engineering retry fails — annotates `_retry_data` with `engineering_validation_failed=True`, `engineering_validation_errors`, `fallback_used=True` while preserving the pre-existing changes list (required to not regress test_group27 and test_group38).

**Key helpers added to `strategy/setup_diagnosis.py`:** `_classify_bottoming_confidence(laps, avg_bottoming, b_band, driver_feel_flags, all_frames, setup_history_entries) -> dict`, `_rh_permitted_increment(bottoming_confidence, loc_usable) -> int`, `_derive_driver_feel_traction_status(feeling_history) -> str`, `_build_deterministic_fallback(diagnosis) -> dict`. `strategy/driving_advisor.py`: `_build_deterministic_fallback` and `_build_setup_diagnosis_conservative` added to import; `rh_rake_risk` structural check in `_validate_setup_response`; fallback annotation in both retry blocks.

**AC5 verification (no code change):** `top_gear_power_band_limited` is NOT in `_PRESERVE_GEARBOX_CATEGORIES`, so `gearbox_flag = "may_change"` — transmission changes are allowed for the Fuji power-band scenario. Confirmed by code inspection.

**Tests:** `tests/test_group40.py` to be written by the test-verifier agent (S1–S10 + AC9 fallback + key-parity). No regressions in existing suite.

**Deferred / limitations:** UI surface for new keys (follow-on story); inside_wheel_spin/rear_platform_stiffness subtypes still deferred; fragile LSD-verdict blob join unchanged; the 8 pre-existing track-modelling allowlist failures remain for the track-modelling owner.

**Next:** test-verifier writes `tests/test_group40.py`; then drive setups and read the AI Log to confirm the new validation rules fire correctly; build candidates: UI readout for bottoming_confidence + aero_rear_healthy; structured LSD-history join; return to OFR strategy telemetry (Phase 2-B/2-C).

---

## Prior Objective (historical)
**Setup Brain Upgrade — Professional Race Engineer Diagnosis — COMPLETE (2026-07-05).** Branch `ofr2-quali-race-disciplines` (built on top of the OFR-2 work). Full suite: **5356 pass / 6 skip / 8 fail** — the 8 failures are ALL pre-existing frozen-allowlist guard tests from the already-committed `ui/track_modelling_ui.py::_tm_restore_last_track` `config["strategy"]` consumer (unrelated track-modelling tech debt, NOT this sprint), left to the track-modelling owner; ~72 new tests all green, zero regressions. **Backend-only; no UI surface.**

**What it does:** the setup-diagnosis brain (`strategy/setup_diagnosis.py`) now reasons like a race engineer about WHY a symptom appears before the AI touches a setup. NEW app-side GEARING DIAGNOSIS — `_classify_gearing(...)` → `gearing_diagnosis_category` ∈ {gear_too_short, gear_too_long, top_gear_power_band_limited, traction_limited_acceleration, drag_or_power_limited, limiter_limited, insufficient_data} via a priority decision table (top-gear limiter below/at target → gear_too_short/limiter_limited; below-target + severe wheelspin → traction_limited; below-target + early-peak-power + accel-fade → power-band-limited; else drag/long/insufficient), fed by the new pure `_derive_top_gear_frame_signals(frames, top_gear)` (accel_fade_detected, peak_power_early over the ~10Hz `LapStats.frames`; degrades to insufficient_data when absent; tunable module constants). The flawed rule is REMOVED — the `gear_note` "Do NOT recommend lengthening gears" block, old `DRIVER_HARD_CONSTRAINTS` constraint #8 (now 8), and the `gearbox_edit_when_preserve` validator rule gone; replaced by `gearbox_category_mismatch` that only blocks changes for insufficient_data/gear_too_long/limiter_limited (or driver-flagged-good) — the Fuji RSR power-band case now ALLOWS a gearbox change. NEW WHEELSPIN SUBTYPE `_classify_wheelspin_subtype(...)` → {both_rear_spin, snap_throttle_induced, kerb_unload_spin, gear_too_short_spin, aero_instability, mixed, insufficient_data} with honest deferrals (`inside_wheel_spin` NEVER emitted — no per-wheel slip; `rear_platform_stiffness` folds into mixed — no damper baseline; kerb_unload_spin is a kerb-count proxy). NEW `compliance_priority` (bool) via `_detect_compliance_priority` raises natural-freq/damping to first-or-second in `_derive_tuning_priority` UNPROMPTED when stiffness/kerb-upset terms + kerb events/lap > 2, and emits an explicit compliance instruction. DOMINANT re-order: severe/major wheelspin now outranks "consider"-band bottoming unless driver feel cites bottoming (new `bottoming` in `_FEEL_VOCABULARY`). LSD ANTI-OSCILLATION: `validate_setup_engineering` gains `rec_history` + rule `lsd_reversal_without_evidence` (fires on an unevidenced LSD-accel direction reversal; skips when a `worsened` verdict backs it / no prior / no history); rec_history resolved by the CALLER from STRUCTURED `data/setup_history.json` + the DB `worsened` verdict — no new `config["strategy"]` read. FEEDBACK CHRONOLOGY: `_get_driver_feedback_context` splits "Latest feedback (weight highest)" vs "Earlier feedback" with per-field trend tags current/improving/worsening/resolved via `DrivingAdvisor._feedback_trend_tag` — latest now dominates old. SCHEMA FIX: `not-present` added to allowed `issue_classification` values in both prompt builders + `_race_engineer_directives`; invalid `"not currently an issue"` example removed. All new keys (gearing_diagnosis_category, wheelspin_subtype, compliance_priority) appear in BOTH the normal and the conservative/error-path diagnosis dicts.

**Pieces:** `strategy/setup_diagnosis.py` (`_classify_gearing`, `_derive_top_gear_frame_signals`, `_classify_wheelspin_subtype`, `_detect_compliance_priority`, `_derive_tuning_priority`/`_derive_dominant_problem` re-order, `validate_setup_engineering`+`rec_history`/`lsd_reversal_without_evidence`, `format_diagnosis_for_prompt`, `_build_combined_prompt`/`_race_engineer_directives`/`DRIVER_HARD_CONSTRAINTS` edits, new `_FEEL_VOCABULARY` bottoming entry + tunable module constants); `strategy/driving_advisor.py` (`_get_driver_feedback_context` chronology split, `_feedback_trend_tag`, caller `rec_history` resolution in `build_setup_advice_response`/`build_combined_setup_response`). No UI, no config["strategy"] read added.

**Tests:** `tests/test_group39_setup_brain_upgrade.py` (~72 — AC1 Fuji RSR gearing, AC2 traction-limited, AC3 categories + error-path keys, AC4 compliance, AC5 wheelspin subtype incl. never-inside-wheel-spin, AC6 LSD anti-oscillation, AC7 feedback trend + Scenario 5 latest-wins, AC8 dominant precedence, AC9 not-present schema, frame-signal units); 4 re-pointed tests in `tests/test_group38_setup_diagnosis.py` (constraint count 9→8, rule rename). Full detail: `docs/SETUP_BRAIN_UPGRADE.md`, `MASTER_TESTING_REGISTER.md` (Setup Brain Upgrade).

**Deferred / limitations (honest):** inside_wheel_spin & rear_platform_stiffness subtypes deferred (no per-wheel-slip / no damper baseline); kerb_unload_spin is a count-proxy; the LSD `worsened`-verdict join matches the DB `recommendation_text` blob for "lsd_accel" (the one fragile join — a structured follow-up candidate); no UI surface for the new keys yet (a follow-on story); the 8 pre-existing track-modelling allowlist failures are for the track-modelling owner.

**Next:** drive setups and read the AI Log to confirm the gearing/wheelspin/compliance reasoning; build candidates: a UI readout for the new diagnosis keys; a structured LSD-history join; return to OFR strategy telemetry (Phase 2-B/2-C).

---

## Prior Objective (historical)
**OFR-2 — Separate Race vs Qualifying Telemetry Disciplines (Core split) — COMPLETE (2026-07-04).** Branch `ofr2-quali-race-disciplines` (from `master` @ `82ca7c3`). Full suite: **5217 pass / 6 skip / 0 fail** (269 new tests; pre-feature baseline 4948). **Feature-factory run** (story + brief approved — the brief with TWO corrections I flagged: RF1 single-source discipline via the analysed session's stored type, RF2 real recent laps wired into the setup path instead of the brief's inert empty list) → backend → UI → 114-test acceptance (all 11 ACs PASS) → validator → fix round → re-verified; checkpoints before every verifier stage.

**What it does:** the setup-BUILD and practice-analysis prompts now feed discipline-aware telemetry. QUALIFYING = peak metrics (best lap, peak lateral G [estimated]+derivation, lock-ups, brake consistency, oversteer rotation split) + an explicit "steering corrections and rival traffic/dirty-air are not measured" line. RACE = consistency/efficiency (fuel/lap, lock-up/wheelspin/snap-throttle rates, lap-time std-dev with "N/A (1 lap)", per-corner tyre temps with "— not recorded"). **Unknown/practice/test purposes keep today's generic block BYTE-FOR-BYTE** (the None-sentinel contract). Objective text, all other sections, and ALL strategy prompts byte-identical; OFR-1 untouched; no tyre-radius; no new config["strategy"] reads; scoped-out-honestly: steering (no packet signal), rival data (none exists), per-corner exits (Phase 7-A), strategy telemetry (Phase 2-B/C deferred).

**Pieces:** `strategy/telemetry_disciplines.py` (NEW pure; None sentinel for every non-quali/race purpose); `ai_planner` param threading + `{_telem_section}` byte-identity injection; `practice_orchestrator` self-resolves via new `db.get_session_type` (RF1); `session_db.get_session_laps` +2 columns + `latest: bool = False` (True = last N laps ascending — the validator caught that limit=5 returned full-fuel OPENING laps); snapshots gain defensive `discipline` (Setup+Practice only, hash-excluded); `ui/setup_builder_ui._resolve_recent_laps` (UI-thread fetch, latest=True) + session_type→snapshot. **Validator findings fixed:** C1 practice/test fell through to the RACE block (free-practice sessions are stored as "practice"!) → sentinel; I1 earliest-laps ordering → latest semantics; +coverage/polish. Full detail: `docs/OFR2_SEPARATE_DISCIPLINES.md`, `MASTER_TESTING_REGISTER.md` (OFR-2).

**Next:** drive quali + race sessions and compare the advice. Build candidates: History-tab surface for OFR-1's scored recommendations; Phase 2-B/2-C strategy telemetry; plan-state schema migration.

---

## Prior Objective (historical)
**OFR-1 — Between-Race Learning Loop (Loop 1: setup self-scoring) — COMPLETE (2026-07-04).** Branch `ofr1-between-race-learning` (from `master` @ `f0a23aa`). Full suite: **4948 pass / 6 skip / 0 fail** (171 new tests; pre-feature baseline 4777). **Built via the /feature-factory chain** (researcher → story approved → brief approved with one design correction → backend → UI → 43-test acceptance verification (all 11 ACs PASS) → validator → fix round → re-verified; builder output checkpoint-committed before each verifier stage per the standing rule).

**What it does:** after each session, the app self-scores the AI's applied setup recommendations against measured before/after telemetry (verdict improved/worsened/neutral/insufficient_data + confidence 0.0–1.0, write-once), and the next setup prompt for that car+track opens with the roadmap-§6.4 plain-English "Performance of Previous Recommendations" block (≥0.5 confidence only, REPLACING the free-text history — never both). Home journey step 13 (`learning_saved`) is finally live, DB-derived via `has_learning_for_car_track`.

**Key design points:** the "after" session is the just-finished session resolved via `get_previous_session_id` (approved correction — `outcome_session_id` is never populated); recs created in the after-session are skipped; cross-layout guard (differing non-empty layout_id never compared); attribution split ×1/N for simultaneous recs; honesty gates (missing before_metrics or <3 clean laps either side → insufficient_data, conf 0.0 — never fabricate); handling-targeted recs judged by handling-event rates, not lap time alone; mixed-signal override (Δt improved but handling agreement <0.3 → neutral); driver-feedback bonus wired via `get_recent_feedback`; NO tyre-radius signal; NO new `config["strategy"]` reads — and the frozen-allowlist scan was EXTENDED to `strategy/driving_advisor.py` (15 pre-existing bridge entries frozen) after the validator caught exactly such a read sneaking in (fixed).

**Pieces:** `data/recommendation_scoring.py` (NEW pure module — the whole algorithm + §6.4 formatter); `data/session_db.py` migration v9 (`score_confidence`/-1.0 sentinel, `score_verdict`, `score_details`) + 6 methods; `ui/dashboard.py` `_trigger_scoring_pass` (never-raises; called after session-open in `_on_live_mode_changed` + `_save_session_to_db`) + the `learning_saved` derivation; `strategy/driving_advisor.py` scored-block-first injection with exact-fallback. Full detail: `docs/OFR1_BETWEEN_RACE_LEARNING.md`, `MASTER_TESTING_REGISTER.md` (OFR-1).

**Next:** drive sessions to accumulate scores (the prompt block appears once ≥0.5-confidence verdicts exist). Build candidates: **OFR-2** (race vs quali telemetry disciplines), or a small History-tab surface for scored recommendations.

---

## Prior Objective (historical)
**Fan-Out Rule-Cache Deletion — COMPLETE (2026-07-04).** Branch `fanout-rule-cache-deletion` (from `master` @ `8d7c500`). Full suite: **4777 pass / 6 skip / 0 fail** (16 new tests; 12 legacy pins updated in place). **THE AUDIT'S ORIGINAL SSOT VIOLATION IS DELETED** (scoped by explicit product decision: "delete the rule cache"; full schema migration declined as highest-risk).

**What was deleted:** `_fanout_event_to_strategy` no longer writes the 12 event-RULE fields (`tyre_wear_multiplier`, `fuel_mult`, `mandatory_stops`, `weather`, `damage`, `refuel_speed_lps`, `required_tyres`, `mandatory_compounds`, `avail_tyres`, `bop`, `tuning`, `allowed_tuning_categories`). The helper now writes only the legitimate **working-config core** (track, race_type, laps/total_laps, race_duration_minutes — the match-key/restore inputs — and event_id for session tagging). Existing configs keep old rule keys as harmless unread leftovers (neither refreshed nor removed — pinned).

**Why it's invisible (proofs, all tested):** EventContext resolves rules DB-event-first per field (fallback fires only on `None` fields; the DB record and the `config["events"]` mirror carry all rules) → rules identical whether the strategy dict has fresh/stale/no rules, field-by-field. AI snapshots' CONTEXTS source ignores the legacy rule keys (identical frozen race_params proven); LEGACY_ONLY fires only with no event — a state where the fan-out never ran anyway. Match-key hash reads core fields only (golden vectors green).

**Touch-ups:** `_on_event_set_active`'s writer-internal permission call DELETED (redundant since Phase 3 — the sync applies permissions from the just-saved DB event with identical values, and its cached inputs no longer exist); driving-advisor fallback hardened (`_evt_full or self._active_event() or strat` — no-DB path gets full rules via the events mirror). **Residual edge (accepted at scoping):** ancient DB rows with NULL rule columns would fall back to frozen-stale leftovers; any event re-save heals the row.

**Tests:** `tests/test_fanout_rule_cache_deletion.py` (16 — shrunk helper on a stub: core-only/plan-untouched/stale-leftovers-left-alone; the invisibility proofs incl. EventContext field-by-field + events-mirror fallback + AI CONTEXTS race_params identity + match-key unaffected; source-scans: no rule writes, redundant call gone, advisor hardened, activation side effects intact; allowlist/golden-vector/Home/guardrail invariants). **12 pins updated in place** (invariant evolved: "fan-out writes the rules" → "rules are NOT cached, DB-only; core IS written"): group7 ×6 (+1 new core pin), group12a ×2, group4 ×1, phase_1 writer pin, phase_3 gating pin, phase_4 helper stub.

**What remains on `config["strategy"]` (all legitimate, allowlisted):** the working-config core writer + TM combo ids; plan-state persistence (stops/fuel/tolerances/config_id — item 4's remainder, a schema-migration decision, not a correctness one); the context/AI bridge inputs (by design); cosmetic car reads.

**Next sprint: RETURN TO PRODUCT WORK (recommended)** — the consolidation series has reached its goal. Standing item: **OFR-1 between-race learning loop** (deferred; see `project_outstanding_features` memory + roadmap). Optional architectural tail: the plan-state schema migration, only if/when a feature needs it. Full detail: `docs/FANOUT_RULE_CACHE_DELETION.md`, `MASTER_TESTING_REGISTER.md` (Fan-Out Rule-Cache Deletion).

---

## Prior Objective (historical)
**Working Race Config Read Model — COMPLETE (2026-07-04).** Branch `working-race-config` (from `master` @ `7f4a95a`). Full suite: **4760 pass / 6 skip / 0 fail** (25 new tests; hash-vector suite updated in place; allowlist consciously reshaped). **Retirement-map item 3, reader half (explicit product decision: "read model + readers"; the writer half is deferred with item 4). The reader side of the entire consolidation is now complete.**

**The model — `data/working_race_config.py` (NEW, pure):** `WorkingRaceConfig` (frozen — track, car, raw race_type token, total_laps default **25**, race_duration_minutes default **60** (the hash's own absent-key defaults, distinct from EventContext's 0), stored config_id). `from_strategy()` verbatim (one documented hardening: garbage lengths coerce to defaults instead of raising). **It now owns the match-key algorithm** — `length_key`/`hash_raw`/`compute_config_id()` (`sha256[:10]`) — still frozen by the 6b golden vectors, which exercise the REAL dashboard method through the new delegation. `length_text()` for the Strategy-tab detail. Semantics per 6b: usually mirrors the active event; deliberately holds a restored historical session's config during a lap-bank restore (why it exists apart from EventContext).

**Migrated readers (byte-identical, via new `_working_race_config()` builder — the single bridge read):** `_compute_race_config_id` (delegates to the model); `_update_race_config` label + `race_configs` snapshot values (`wrc` + `length_text()`; the config_id WRITE stays — it's the writer); `_sync_strategy_from_event` no-event checks (`wrc.track/car` falsiness); `_save_session_to_db` session tagging (`wrc.car/track/config_id`). **Allowlist net −3 direct readers**: `_compute_race_config_id`/`_sync_strategy_from_event`/`_save_session_to_db` removed, `_update_race_config` 2→1 (write only), `_working_race_config` +1 (bridge).

**Tests:** `tests/test_working_race_config.py` (25 — from_strategy verbatim + 25/60 defaults + None-safety + garbage-coercion hardening + immutability; the golden vectors asserted directly on the model; unknown race-type→lap; length_text; purity; the four consumer source-scans incl. the remaining config_id write; writers-untouched pins; allowlist/Home/guardrail invariants). `tests/test_race_config_id_hash.py` updated in place (the `_bind` stub binds the real builder → vectors run the full delegated path; the source-level algorithm pin moved to the model — same invariant, new home).

**Next sprint:** **item 3 writer-half + item 4** (writers write the typed model / a durable store; the dict's event-rule fields become derived compatibility; plan-state gets a home — the actual fan-out deletion, now guarded end-to-end), or **product work** (deferred OFR-1 between-race learning loop). Full detail: `docs/WORKING_RACE_CONFIG.md`, `MASTER_TESTING_REGISTER.md` (Working Race Config Read Model).

---

## Prior Objective (historical)
**Legacy Fan-Out Removal Phase 6b — config_id Hash Byte-Stability Proof — COMPLETE (2026-07-04).** Branch `legacy-fanout-phase-6b-hash-proof` (from `master` @ `8e9fcb6`). Full suite: **4738 pass / 6 skip / 0 fail** (17 new tests). **Purely additive — tests + docs; no production code changed. Retirement-map item 2 delivered as proof + pins; the migration half is provably BLOCKED and folds into items 3/4.**

**The blocker discovered (restore-divergence):** `_load_session_config` (lap-bank "load historical session") deliberately writes a historical session's track/car + race params into the working `config["strategy"]` WITHOUT changing the active event, then recomputes the id — the id must follow the RESTORED session. `EventContext.track`/rules are DB-first → an EventContext-sourced hash would pin the id to the active event mid-restore, silently breaking the feature. Outside restores the two sources are provably identical (post-Phase-4 always in sync — tested). `car` alone is always-safe (strategy-first) but hash inputs move together. **Corrected map:** item 2's migration merges into item 3 (restore redesign) / item 4 (working-race-config home).

**Delivered — `tests/test_race_config_id_hash.py` (17):**
- **Golden vectors** (5 literal inputs→id pairs, frozen; exercised through the REAL `_compute_race_config_id` on a widget-free stub; incl. `'||l25' → 05e6d2f288`, a real id observed in the field). Test header forbids regenerating vectors on failure — a mismatch means history re-keying; fix the CODE.
- `DEFAULT_CONFIG` → empty-vector pin; shape/stability/sensitivity (each input independently changes the id); the algorithm's own `l25`/`t60` defaults pinned; unknown race-type tokens hash as lap.
- **Source-level algorithm pin** (raw-string format, `sha256[:10]`, 25/60 defaults, working-config input source — verbatim body fragments).
- **Equivalence + divergence proofs** — in-sync EventContext would hash identically (future migration safe outside restores); the restore case demonstrably diverges (the blocker); car's strategy-first safety.
- Invariants: Phase 5 frozen allowlist untouched; Home-first; config guardrail.

**Next sprint:** **retirement-map item 3 — restore-writer redesign** (a first-class "working race config" flow + home, so the hash inputs, restore writers, and plan-state persistence migrate together under the golden vectors), or **product work** (deferred OFR-1 between-race learning loop). Full detail: `docs/LEGACY_FANOUT_PHASE_6B.md`, `MASTER_TESTING_REGISTER.md` (Legacy Fan-Out Removal Phase 6b).

---

## Prior Objective (historical)
**SessionContext Real Connection Signal — COMPLETE (2026-07-04).** Branch `session-context-real-connection` (from `master` @ `ebbaed4`). Full suite: **4721 pass / 6 skip / 0 fail** (18 new tests). **The one-place change promised by the SessionContext sprint, delivered: Home's `live_active`, the flow gates, and the telemetry labels now reflect the REAL UDP-listener state (packet-timeout based), instead of an always-False phantom tracker attribute.**

**What was wired:**
- **`MainWindow(udp_listener=...)` (NEW param)** — duck-typed (`.connected`/`.total_received`/`.parse_errors`/`.packet_rate`, all real `UDPListener` properties; `connected` = True on packet receive, False after 3 s silence). `main()` passes the listener (created before the window). Listener attrs are plain bool/int/float — GIL-atomic cross-thread reads, no locks added.
- **`_build_session_context`** — sources `connected` + `packet_count` from the listener when wired; the legacy tracker-getattr fallbacks are retained verbatim (byte-identical to the old always-False/0 behaviour for tests/legacy constructions — the existing 25 SessionContext tests pass unchanged). Home `live_active` / journey step-12 gate / `_refresh_telemetry_context` labels become real automatically through the existing context plumbing.
- **`_update_telemetry_labels` (diagnostics panel) — wider latent bug found+fixed:** it read FOUR phantom tracker attrs (`_connected`/`_packet_count`/`_error_count`/`_packet_rate_hz` — none ever existed), so the panel was frozen at "Disconnected / 0 / — Hz / Not started". Now reads the listener's four real stats (old fallbacks preserved when no listener).

**Intended behaviour change (the point):** with SimHub streaming, Home's Live signals and the Telemetry tab show Connected + live packet counts; 3 s of silence → Disconnected. Everything else byte-identical.

**Tests:** `tests/test_session_connection_signal.py` (18 — real `_build_session_context` on widget-free stubs: connected→live ctx+flow_flags, packet totals, disconnected, listener-beats-tracker, missing-attr listener safe; no-listener fallbacks reproduce the old frozen state; real `_update_telemetry_labels` on stubs (lit vs frozen); wiring scans (ctor param, `main()` pass-through, prefers-listener-with-fallback, panel stats); `UDPListener` property contract pinned; Phase 5 allowlist still exact; Home-first + guardrail invariants). Docs: `SESSION_CONTEXT_MIGRATION.md` §5a (the sprint's home), HOME_DASHBOARD_BUILD + PHASE_6A cross-refs.

**Next sprint:** **Phase 6b — `_compute_race_config_id` hash byte-stability proof** (retirement-map item 2: pin hash vectors → prove EventContext inputs identical in-sync → migrate), or **product work** (deferred OFR-1 between-race learning loop) — the state architecture is consolidated and Home is now fully truthful. Full detail: `docs/SESSION_CONTEXT_MIGRATION.md` §5a, `MASTER_TESTING_REGISTER.md` (SessionContext Real Connection Signal).

---

## Prior Objective (historical)
**Legacy Fan-Out Removal Phase 6a — Dispatcher SessionTag Snapshot — COMPLETE (2026-07-04).** Branch `legacy-fanout-phase-6a-dispatcher-tag` (from `master` @ `b010882`). Full suite: **4703 pass / 6 skip / 0 fail** (21 new tests; Phase 5 allowlist consciously shrunk — the guard held). **Retirement-map item 1 done: the telemetry pipeline no longer touches `config["strategy"]` at runtime.**

**The mechanism:**
- **`data/session_context.SessionTag` (NEW, pure)** — frozen dataclass (track/car/config_id/event_id); `from_strategy()` reproduces the dispatcher's original reads verbatim; coercing `build_session_tag()`. Immutable → attribute swap is atomic under the GIL (no lock between UI writer thread and dispatcher reader thread).
- **`EventDispatcher` (main.py)** — seeds the tag at construction from the config it receives (one-time, pre-thread — the single remaining main.py bridge read, allowlisted as `("main.py","__init__"): 1`, replacing `("main.py","_dispatch"): 2`); `set_session_tag()` None-safe swap; `_dispatch` reads only the tag at both sites (per-lap `write_lap` event_id; fallback race-session open track/car/config_id/event_id). **`self._config` removed entirely.**
- **`MainWindow._push_session_tag()` (NEW)** — builds from EventContext + `_active_config_id()` (byte-identical, Phase 5 proofs) and pushes. Sites: end of `_update_race_config` (Set-as-Active, garage car select, and session-config restore ALL funnel through it), `_on_event_save`'s active-event re-sync branch (after the fan-out write, ordering pinned), and end of `__init__` (belt-and-braces before `dispatcher.start()`).

**Behaviour notes:** byte-identical in-sync (always, post-Phase-4). The old fallback-open `strat.get("track", "Unknown")` default was DEAD CODE (DEFAULT_CONFIG has always materialised `strategy.track = ""`) — real behaviour (empty string) preserved and pinned by test.

**Tests:** `tests/test_legacy_fanout_phase_6a.py` (21 — SessionTag verbatim/from_strategy/defaults/coercion/immutability + the dead-"Unknown" pin; context-tag == strategy-tag; the REAL EventDispatcher exercised without starting its thread: construction seed, None-safe swap, RACE_STARTED opens the session with exactly the tag fields, LAP_COMPLETED writes event_id from the tag, updated tag used by the next event; source-scans: `_dispatch` config-free, config attr gone, push helper + all sites wired; writer/re-sync/Home-first/guardrail invariants). `tests/test_legacy_fanout_phase_5.py` FROZEN_ALLOWLIST updated in the same commit (main.py `_dispatch`×2 → `__init__`×1).

**Next sprint:** retirement-map item 2 — **`_compute_race_config_id` hash byte-stability proof** (pin hash vectors → prove EventContext inputs identical → migrate) — or **wire the real UDP connection signal into SessionContext** (Home `live_active` becomes real), or **product work** (OFR-1). Full detail: `docs/LEGACY_FANOUT_PHASE_6A.md`, `MASTER_TESTING_REGISTER.md` (Legacy Fan-Out Removal Phase 6a).

---

## Prior Objective (historical)
**Legacy Fan-Out Removal Phase 5 — Functional Readers + Frozen Allowlist Guard — COMPLETE (2026-07-03).** Branch `legacy-fanout-removal-phase-5` (from `master` @ `b58545e`). Full suite: **4682 pass / 6 skip / 0 fail** (15 new tests; 2 legacy pins updated in place). **Scope (explicit product decision: "Functional + guard") — full writer retirement was re-audited and found BLOCKED (telemetry-path dispatcher reads, the config_id hash, restore writers, plan-state persistence, bridges); instead: no product decision reads the legacy dict any more, and a frozen allowlist prevents any new consumer.**

**Functional readers migrated (byte-identical in-sync, tested):**
- **Live-session open tagging** (`_on_live_mode_changed`) — track/car/event_id from EventContext + config_id from StrategyContext (was 4 raw strat reads).
- **Degradation params** — `tyre_wear_multiplier` (EventContext) + `degradation_consecutive_laps` (StrategyContext); still read on the UI thread before the worker spawns.
- **BoP checks** — `_get_bop_data_for_car` + the reload-BoP gate → `EventContext.bop_enabled`/`.car`.
- **`_current_setup_dict`** event-identity fields (car with the `or "Unknown Car"` fallback, track, weather→condition map, bop) → one `_ev_ctx`; safe off the UI thread (voice-query getter) — SessionDB is `check_same_thread=False` + locked.
- **Setup-save `event_id`** → `int(_build_event_context().event_id or 0)`.

**Frozen allowlist guard:** `tests/test_legacy_fanout_phase_5.py::FROZEN_ALLOWLIST` pins all **41 remaining `config["strategy"]` access sites** across 40 `(file, method)` entries (each annotated: writer/bridge/hash/plan/restore/cosmetic/telemetry-path). Exact-equality scan — a NEW consumer fails with a pointer to the contexts; a silent removal fails too (shrink the list in the same commit).

**Phase 6 retirement map (docs §4):** (1) dispatcher session-tag snapshot instead of the `main.py` `_dispatch` telemetry-path reads; (2) `_compute_race_config_id` hash byte-stability proof + pinned vectors; (3) restore-writer redesign (`_load_session_config` etc.); (4) a home for plan-state persistence (stops/fuel/tolerances/config_id); (5) reshape the bridges last. None is a correctness risk post-Phase-4 (staleness impossible) — mechanical follow-ups, best 1→2→3.

**Deliverables:** `docs/LEGACY_FANOUT_PHASE_5.md` (NEW); `ui/dashboard.py` + `ui/setup_builder_ui.py` (the five migrations); `tests/test_legacy_fanout_phase_5.py` (15 — allowlist exact-match + creep/removal guard; byte-identity for every migrated read incl. empty defaults + the "Unknown Car" fallback; source-scans; writer/re-sync/Home-first/guardrail invariants); `test_group4_fixes` `TestBoPSourceOfTruth` ×2 updated in place (invariant "BoP from event state, never a widget" — source now EventContext).

**Next sprint (the fan-out series is at its natural pause):** **wire the real UDP connection signal into SessionContext** (one-place change, user-visible), or **Phase 6a** (dispatcher session-tag snapshot — first concrete writer-retirement step), or **return to product work** (e.g. deferred OFR-1 between-race learning loop) now that the state architecture is consolidated. Full detail: `docs/LEGACY_FANOUT_PHASE_5.md`, `MASTER_TESTING_REGISTER.md` (Legacy Fan-Out Removal Phase 5).

---

## Prior Objective (historical)
**Legacy Fan-Out Removal Phase 4 — Divergence Elimination + Last Readers — COMPLETE (2026-07-03).** Branch `legacy-fanout-removal-phase-4` (from `master` @ `e356879`). Full suite: **4667 pass / 6 skip / 0 fail** (18 new tests; 11 legacy pins updated in place). **The DB event record and the `config["strategy"]` fan-out can no longer diverge, and `_sync_setup_builder_from_event` no longer reads `config["strategy"]` at all. Writer retirement investigated and explicitly deferred to Phase 5 (would break the app today — see below).**

**Deliverables:**
- **`dashboard._fanout_event_to_strategy(evt_name)` (NEW)** — the Set-as-Active fan-out block extracted **verbatim** (event-RULE fields only; never touches `car`/`config_id`/`stops`/fuel). **Config-dict only** — no tracker/advisor/query-listener/sync/persist side effects (callers own those). `_on_event_set_active` behaviour unchanged (calls save → helper → all its activation side effects).
- **Re-sync on Save** — `_on_event_save` calls the helper **only when the saved event IS the active event** (`name == active_event_id`), before its existing `_persist_config()`. Saving a non-active event changes nothing; activation side effects (tracker race config, advisor context) remain exclusive to "Set as Active" (unchanged from before, where Save updated them never). Result: after an edit+Save, ALL readers — DB-first and legacy — agree immediately.
- **Last readers migrated (byte-identical in-sync):** `_get_mandatory_compounds` (→ `EventContext.required_tyres` codes mapped to display names via `data.tyres.get_by_code` — the same mapping the fan-out writer used to build its `mandatory_compounds` string); setup tab refuel label (`int(ev_ctx.refuel_rate_lps)` keeps QSpinBox formatting), required/available tyre labels (same codes), car spinbox rebind (`ev_ctx.car`). Dead `sc` variable removed — the setup sync method is fully off the fan-out.
- **`docs/LEGACY_FANOUT_PHASE_4.md` (NEW)** — incl. §5's writer-retirement analysis: retiring the writer NOW would break the app (`car`/`config_id`/stint plan live ONLY in the fan-out; ~25 readers remain: live-session open, BoP ~L5400, degradation ~L5525, `_compute_race_config_id` hash, restore paths, AI-snapshot bridges). With re-sync the fan-out can't go stale, so retirement is a mechanical Phase 5 (re-home car/config_id/plan → migrate ~25 reads → delete writer).

**Tests:** `tests/test_legacy_fanout_phase_4.py` (18 — the real helper bound to a widget stub: writes all rule fields incl. compounds names, preserves plan fields, returns the live dict, no persist/sync side effects, race-type normalisation; save-path scans: guarded call before persist, save stays config-only, Set-as-Active keeps side effects + no inline fan-out left; reader byte-identity + `_sync_setup_builder_from_event` reads no config["strategy"]; TM writer/Home-first/guardrail invariants). **11 legacy pins updated in place** (same invariants, new home — the strat writes moved to the helper): `test_group7_event_persistence` ×7, `test_group12a_bop_tuning_propagation` ×3, `test_group4_fixes` ×1, plus the Phase 1/2/3 writer pins.

**Next sprint: Legacy Fan-Out Removal Phase 5 — retire the writer** (re-home `car`/`config_id`/plan state, migrate the remaining ~25 reads, delete the fan-out + compatibility dict), or the standing smaller job: **wire the real UDP connection signal into SessionContext**. Full detail: `docs/LEGACY_FANOUT_PHASE_4.md`, `MASTER_TESTING_REGISTER.md` (Legacy Fan-Out Removal Phase 4).

---

## Prior Objective (historical)
**Legacy Fan-Out Removal Phase 3 — Functional Gating / Validation Migration — COMPLETE (2026-07-03).** Branch `legacy-fanout-removal-phase-3` (from `master` @ `4e6721b`). Full suite: **4649 pass / 6 skip / 0 fail** (20 new tests; 2 Phase 2 pins updated in place). **Scope (explicit product sign-off: "flip reads only"): the two remaining FUNCTIONAL `config["strategy"]` consumers now read DB-first EventContext; the fan-out writers are untouched (Phase 4's job).**

**What was migrated:**
- **Setup-permission gating** — `_sync_setup_builder_from_event` now feeds `_on_bop_toggled` + `_apply_setup_permissions` from `ev_ctx.bop_enabled` / `.tuning_allowed` / `list(.allowed_tuning_categories)` (was `bool(sc.get("bop"/"tuning", …))` / `sc.get("allowed_tuning_categories", [])`). Gating LOGIC unchanged — only inputs moved.
- **DEF-P3-012 strategy-options tuning validation** — `_strat_locked`/`_strat_allowed` from `_build_event_context()` (`tuning_locked` / `allowed_tuning_categories`) instead of `_sc_strat` raw reads; `validate_ai_setup_response` call unchanged.
- **Deliberately NOT migrated:** `_on_event_set_active`'s own `_apply_setup_permissions(strat.get(...))` call — inside the writer, `strat` fresh by construction (pinned by test).

**Behaviour:** byte-identical in-sync (tested field-by-field across unrestricted/BoP-on/locked/partially-restricted + empty-state defaults). In the diverged case (event edited + Saved, not re-activated) the signed-off change: **which setup fields are editable, and the tuning validation, now follow the fresh DB truth** — removing the Phase 2 inconsistency where the labels showed DB truth but the lock state enforced the stale fan-out. **Reader consistency is now complete**: AI inputs, labels, gating, validation all resolve event truth DB-first. The fan-out remains only for: its two writers, refuel/req/avail label fallbacks, car spinbox rebind, `_get_mandatory_compounds`, the no-event branch, and the context-builders' legacy-bridge inputs.

**Deliverables:** `docs/LEGACY_FANOUT_PHASE_3.md` (NEW); `ui/setup_builder_ui.py` + `ui/dashboard.py` (the two flips); `tests/test_legacy_fanout_phase_3.py` (20 — in-sync byte-identity vs verbatim old expressions; DB-first divergence; source-scans: gating/validation read EventContext, zero raw `sc.get("bop"/"tuning"/"allowed_tuning_categories")` left at either site, gating calls + `_apply_setup_permissions` body unchanged, writer-internal call still reads fresh `strat`; writers + Home-first + config-guardrail invariants); `tests/test_legacy_fanout_phase_2.py` (2 pins updated in place — "gating still reads fan-out" → "gating calls intact", the invariant that evolved with the sign-off).

**Next sprint: Legacy Fan-Out Removal Phase 4 — retire the divergence, then the fan-out:** (1) `_on_event_save` re-syncs the fan-out when the saved event is active (config-only, no tracker/advisor side effects) so DB/config can't diverge; (2) migrate the last minor readers (refuel/req/avail fallbacks, `_get_mandatory_compounds`, car rebind); (3) retire the Set-as-Active fan-out writer (keep `config["strategy"]` only as the context-builders' input). Alternative smaller job: wire the real UDP connection signal into SessionContext. Full detail: `docs/LEGACY_FANOUT_PHASE_3.md`, `MASTER_TESTING_REGISTER.md` (Legacy Fan-Out Removal Phase 3).

---

## Prior Objective (historical)
**Legacy Fan-Out Removal Phase 2 — Event-Rule Display-Label Migration — COMPLETE (2026-07-03).** Branch `legacy-fanout-removal-phase-2` (from `master` @ `0ae591d`). Full suite: **4629 pass / 6 skip / 0 fail** (15 new tests). **Scope (user-chosen): DISPLAY LABELS ONLY — the Strategy/Setup event-context readout labels now reflect DB-first EventContext (consistent with the AI inputs); functional paths (setup-permission gating, BoP toggle, spinbox rebind) still read `config["strategy"]`, so which fields are editable is unchanged. Byte-identical when the DB event and the fan-out are in sync.**

**Why it exists:** `_on_event_save` writes event edits to the DB (+`config["events"]`) but NOT `config["strategy"]` — only `_on_event_set_active` writes the fan-out. So after editing an event and Saving without re-activating, DB is fresh and the fan-out is stale. The strategy/setup AI already reads DB-first (EventContext, since AI Snapshot Migration), so the labels *describing those inputs* were showing stale fan-out values. Phase 2 makes the labels consistent with the AI.

**Scope decision:** I surfaced (via a scoping question) that `_sync_setup_builder_from_event` isn't purely display — it also feeds `_apply_setup_permissions`/`_on_bop_toggled` (which fields are editable). User chose **display labels only**, leaving those functional inputs on the fan-out.

**Migrated (byte-identical in-sync, DB-first when diverged):**
- **`dashboard._sync_strategy_from_event`** — the `_lbl_strategy_event_ctx` context line (track/car/length/Wear/Fuel/Refuel, int-wrapped) + `_lbl_fuel_mult_display`, via one `ev_ctx = self._build_event_context()`. `_update_race_config()` writer + `_get_mandatory_compounds()` + the no-event fallback branch left unchanged.
- **`setup_builder._sync_setup_builder_from_event`** — `_lbl_setup_event_ctx` (track/car) + the `_lbl_rc_*` readouts (race_type/length/fuel/wear/mand_pits/weather/damage + bop/tuning **labels**). Left on the fan-out: refuel/req_tyre/avail_tyres labels (complex fallbacks) and the **functional** `_bop`/`_tuning`/`_cats` → `_apply_setup_permissions`/`_on_bop_toggled` + `_rebound_setup_spinboxes`.

**Byte-identity mechanism:** all event multipliers/counts are `QSpinBox` **integers**, so the migrated labels wrap `int()` around EventContext floats (`"2×"` stays `"2×"`, not `"2.0×"`). `race_type` is safe because EventContext normalises the DB combo text (`"Timed Race"`) and the fan-out token (`"timed"`) to the same value. Verified the full rendered Strategy line + Setup labels byte-identical for an in-sync pair.

**Deliverables:** `docs/LEGACY_FANOUT_PHASE_2.md` (NEW — scope decision, why DB-first, byte-identity, the migrated-vs-left table, the documented behaviour change, next sprint); `ui/dashboard.py` + `ui/setup_builder_ui.py` (the two sync methods); `tests/test_legacy_fanout_phase_2.py` (15 — in-sync byte-identity of label values + int-format guard; DB-first divergence (edited-not-reactivated shows DB truth); source-scans that display labels read EventContext while functional gating still reads `config["strategy"]` and is fed sc-derived `_bop`/`_tuning`/`_cats`; writer + Home-first + config-guardrail invariants).

**Next sprint: Phase 3 — functional gating (needs product sign-off)** — migrate the setup permission/BoP inputs + the tuning/BoP AI-response validation to DB-first EventContext (changes which fields are editable in the diverged case); ideally first make `_on_event_save` re-sync (or drop) the fan-out so DB/config can't diverge, enabling the Set-as-Active fan-out to finally be retired. Alternative: wire the real UDP connection signal into SessionContext. Full detail: `docs/LEGACY_FANOUT_PHASE_2.md`, `MASTER_TESTING_REGISTER.md` (Legacy Fan-Out Removal Phase 2).

---

## Prior Objective (historical)
**SessionContext / TelemetryContext — COMPLETE (2026-07-03).** Branch `session-telemetry-context` (from `master` @ `c94e4ad`). Full suite: **4614 pass / 6 skip / 0 fail** (25 new tests). **Additive read-model + byte-identical consumer migration — no telemetry/PTT/voice/live-race/setup/strategy/track/AI/tab-order change; `config["strategy"]` + both fan-out writers preserved.**

**Why it exists:** live-session status ("connected / recording / laps / fuel burn / live?") was read from **volatile tracker attributes** (`tracker._connected`, `._packet_count`, `.avg_fuel_per_lap`, `_active_session_id`, `_loaded_session_avg_fuel`) plus a `config["strategy"]["fuel_burn_per_lap"]` fallback, and the Home Dashboard's `live_active`/`has_practice_laps` were documented approximations built the same way. This adds the telemetry-layer canonical read model (peer of Event/Strategy/Setup/Track contexts).

**Deliverables:**
- **`data/session_context.py` (NEW, pure Python — no PyQt6/DB/I/O)** — `SessionContext` (frozen): `connected`, `packet_count`, `laps_recorded`, `active_session_id`, `is_recording`, `live_active` (= connected), `live_mode`, `telemetry_avg_fuel_per_lap`, `fuel_burn_per_lap` + `fuel_burn_source` (LOADED_SESSION/TELEMETRY/CONFIG_FALLBACK), `has_practice_laps`, `has_valid_laps`, `source` (EMPTY/LIVE); helpers `connection_text()`/`recording_text()`/`is_live`/`to_dict()`/`flow_flags()`. `build_session_context(...)` never raises. **Byte-identity:** `fuel_burn_per_lap` reproduces `_computed_fuel_burn_lpl`'s 3-tier fallback exactly; `connected` reproduces `tracker is not None and getattr(tracker,"_connected",False)` (still False today — a real connection signal can later be wired in one place).
- **`ui/dashboard.py`** — new `_build_session_context()` helper (reads the tracker via safe getters + the fuel fallback from `config["strategy"]` as the single legacy bridge + `config["live"]["mode"]`). Migrated: **`_computed_fuel_burn_lpl`** → `self._build_session_context().fuel_burn_per_lap` (the flagship — its `config["strategy"]` read now lives only in the builder); **`_build_home_dashboard_state`** → `session_ctx.live_active`/`.has_practice_laps`/`.has_valid_laps`; **`_refresh_telemetry_context`** → `sctx.connection_text()`/`.packet_count`/`.recording_text()`/`.telemetry_avg_fuel_per_lap`.
- **`docs/SESSION_CONTEXT_MIGRATION.md` (NEW)** — the ad-hoc-reads table, the model, byte-identity guarantees, migrated consumers, deferred (real connection state; true lap-validity owner), next sprint.

**Tests:** `tests/test_session_context.py` (25 — fuel 3-tier byte-identity vs verbatim legacy + source classification; connection/live/recording semantics; coercion; live-mode default; source EMPTY/LIVE; garbage safety; ownership boundary (no event/strategy/setup/track fields); `flow_flags`; `to_dict`; purity; source-scans that the three consumers read the context and no longer touch tracker internals / inline fallback / config writes; Home-first + config-guardrail invariants).

**Preserved / deferred:** `_home_has_practice_laps` still owns the DB query (SessionContext just carries the flag); `has_valid_laps` still approximated; `config["strategy"]` + both fan-out writers untouched; live-render tracker reads (tyre labels, fuel bar, countdown, per-packet UI) left alone.

**Next sprint: Legacy Fan-Out Removal Phase 2** (migrate the DB-first-precedence event-rule display/validation consumers to EventContext, accepting + testing the behaviour change, then begin retiring the Set-as-Active fan-out) — or **wire real connection state into SessionContext** (now a one-place change). Full detail: `docs/SESSION_CONTEXT_MIGRATION.md`, `MASTER_TESTING_REGISTER.md` (SessionContext / TelemetryContext).

---

## Prior Objective (historical)
**Legacy Fan-Out Removal Phase 1 — Read-Only Consumer Migration — COMPLETE (2026-07-03).** Branch `legacy-fanout-removal-phase-1` (from `config-safety-guardrails` @ `d206be2`). Full suite: **4589 pass / 6 skip / 0 fail** (22 new tests). **Consumer-migration only — every migrated read is byte-identical to the expression it replaces (proven by test); no behaviour change, `config["strategy"]` and both fan-out writers preserved.**

**Why it exists:** reduce dependence on the legacy `config["strategy"]` fan-out cache by moving low-risk read-only consumers onto the canonical read models. This is NOT the sprint that removes the fan-out — writers stay.

**Migrated (byte-identical, tested):**
- **`config_id` → `StrategyContext.config_id`** via a new `dashboard._active_config_id()` accessor. Sites: `setup_builder._refresh_setup_history_combo` + `_on_setup_history_selected` (read-only history lookups), `_display_setup_result` + `_run_build_setup` (history-save keys). Zero raw `config_id` reads remain in `ui/setup_builder_ui.py`. (`_refresh_lap_bank` already used StrategyContext.config_id — precedent.)
- **`car` → `EventContext.car`** in `dashboard._sync_practice_from_event` (practice-bank combo sync). Car resolves strategy-first in EventContext and the events table never stores a car, so it's byte-identical.

**Why only these:** the canonical builders are **DB-event-first** for race-rule fields (`track`, `tyre_wear`, `fuel_mult`, `tuning`, `bop`, race length) — reading those from EventContext would (correctly) differ from the strategy-first raw read when a DB edit post-dates "Set as Active", i.e. NOT byte-identical. Those are documented + **deferred** to Phase 2. `config_id` (strategy-owned) and `car` (strategy-first) are the fields that are provably identical today.

**Preserved (pinned by tests):** the Event Planner "Set as Active" fan-out (`_on_event_set_active`) and the Track Modelling combo writer (`track_location_id`/`layout_id`); `config["strategy"]` itself; all AI-input snapshot reads (already migrated); the config_id **hash** (`_compute_race_config_id`) and telemetry-owned `_computed_fuel_burn_lpl` (both LEGACY_REQUIRED, byte-stable/owned elsewhere).

**Deliverables:** `docs/LEGACY_FANOUT_PHASE_1.md` (NEW — full classification of every remaining `config["strategy"]` reader: EVENT_CONFIG / STRATEGY_PLAN / TRACK_IDENTITY / SETUP_STATE / AI_INPUT / LEGACY_REQUIRED / WRITER, with the precedence caveat table, migrated list, and deferred list with reasons); `ui/dashboard.py` (`_active_config_id`, `_sync_practice_from_event`); `ui/setup_builder_ui.py` (4 `config_id` sites → helper); `tests/test_legacy_fanout_phase_1.py` (22 — byte-identity for `config_id`/`car` incl. DB-event-without-car; source-scans that migrated consumers use the contexts and no longer read raw; both writers intact; migrated methods write no `config["strategy"]`; Track Modelling's only strategy writes are the two combo ids; tab order Home-first + config guardrail still active).

**Next sprint: SessionContext / TelemetryContext** (additive, low-risk — give the telemetry/session layer a canonical read model so `_computed_fuel_burn_lpl` / `has_valid_laps` / `live_active` / live-session identity stop reading `config["strategy"]`/volatile attrs; unblocks Home's two approximations), then **Legacy Fan-Out Removal Phase 2** (migrate the DB-first-precedence event-rule display/validation consumers, accepting + testing the behaviour change). Full detail: `docs/LEGACY_FANOUT_PHASE_1.md`, `MASTER_TESTING_REGISTER.md` (Legacy Fan-Out Removal Phase 1).

---

## Prior Objective (historical)
**Config Safety Guardrails — COMPLETE (2026-07-03).** Branch `config-safety-guardrails` (from `home-dashboard-promotion` @ `69289ba`). Full suite: **4567 pass / 6 skip / 0 fail** (34 new tests). **Safety + test-isolation only: no setup/strategy/track-mapping/AI-prompt/AI-input/telemetry/PTT/voice/calibration/workflow change; `config["strategy"]` + both fan-outs untouched; the only config-schema change is materialising the already-effective `strategy.degradation_consecutive_laps: 2` default (tested).**

**Why it exists:** the app rewrites `config.json` during normal use *and during `MainWindow` construction* (api-key auto-load + `config_id` derivation → `_persist_config`). Last sprint an ad-hoc headless smoke run built `MainWindow` against the real `config.json` and clobbered the user's settings; the file is gitignored so there was no git recovery copy. This sprint makes that class of accident impossible.

**Deliverables:**
- **`config_paths.py` (NEW, pure Python — no PyQt6, no app imports)** — the single owner of config path resolution + IO + the guardrail. `DEFAULT_CONFIG` (moved from `main.py`, re-exported there; now materialises `strategy.degradation_consecutive_laps: 2`); `resolve_config_path(explicit)` (precedence: `--config` → `NGR_CONFIG_PATH` → `config.json`); `is_test_environment()` (pytest in `sys.modules` / `PYTEST_CURRENT_TEST` / `NGR_TEST_MODE=1`); `is_real_config_path()` / `real_config_access_blocked()` (test env + real path + not `NGR_ALLOW_REAL_CONFIG=1`); **`load_config()`** (deep-merge over defaults, never raises; refuses to READ the real config under tests → returns defaults, no secret exposure); **`save_config(path, cfg, *, backup=True)`** (refuses to WRITE the real config under tests → raises `ConfigSafetyError`; serialise-first so no partial writes; `.bak` backup; atomic `tmp`+`os.replace`); `write_default_config()`.
- **`main.py`** — `DEFAULT_CONFIG`/`load_config` imported from `config_paths` (re-exported); `main()` uses `resolve_config_path(explicit)`.
- **`ui/dashboard.py _persist_config()`** — delegates to `save_config(..., backup=True)`; catches `ConfigSafetyError` (logs "BLOCKED real-config write under tests", never crashes). Normal runs write the real config exactly as before, now atomic + `.bak`. All ~22 call sites unchanged.
- **`.gitignore`** — also ignores `config.json.bak` / `config.json.tmp`.
- **`tests/conftest.py` (NEW)** — `temp_config_path` fixture (isolated `config.json` from `DEFAULT_CONFIG` in `tmp_path`; its dir has no `api_key.txt` so no key auto-loads) + **`_guard_real_config`** session-autouse net (SHA-256 of the real config before/after the whole run; fails the suite if any test mutated it).
- **`docs/CONFIG_SAFETY_GUARDRAILS.md` (NEW)** — full audit (load/save sites, construction-time save paths, what constructs MainWindow), the mechanism, the safe-smoke pattern, risks, next sprint.

**Tests (34):** `tests/test_config_safety_guardrails.py` (pure — path precedence; test-env + real-path predicates; opt-out hatch; `load_config` merge/missing/corrupt/real-under-test-returns-defaults/doesn't-mutate-DEFAULT; `save_config` temp-only/refuses-real/atomic-no-tmp-leftover/backup-holds-previous/no-partial-on-non-serialisable/non-dict-rejected; `write_default_config`; `DEFAULT_CONFIG` deg=2 + empty api_key + main re-export; **no real `sk-ant-api…` key value anywhere in sources**; `.gitignore` protects config + .bak/.tmp; config.json not git-tracked; `main` uses `resolve_config_path`; `_persist_config` uses the guarded saver, no raw `open`/`json.dump`). `tests/test_config_safety_smoke.py` (Qt, `importorskip` + offscreen — constructs `MainWindow` against a temp config, real config byte-identical before/after, no api-key leak; persist-to-temp writes only temp; a window wired to the real path is blocked, not crashed). config.json restored/intact (`degradation_consecutive_laps=2`), untouched by the full run.

**Next sprint: Legacy Fan-Out Removal Phase 1** — migrate the low-risk read-only `config["strategy"]` consumers onto EventContext/StrategyContext, keeping the `_on_event_set_active` fan-out writer as compatibility until every reader is migrated. Full detail: `docs/CONFIG_SAFETY_GUARDRAILS.md`, `MASTER_TESTING_REGISTER.md` (Config Safety Guardrails).

---

## Prior Objective (historical)
**Home Dashboard Promotion — Move Home to Index 0 and Add Click Navigation — COMPLETE (2026-07-03).** Branch `home-dashboard-promotion` (from `tab-navigation-named-lookup` @ `3b7c9c9`). Full suite: **4533 pass / 6 skip / 0 fail** (new `tests/test_home_dashboard_promotion.py`; order-pinning updated in place across 4 suites). **UI navigation only: no setup/strategy/track-mapping/AI-prompt/AI-snapshot/telemetry/PTT/voice/calibration/persistence/context-ownership change; no `config["strategy"]` fan-out removed; no new hard-coded index; `select_tab` still the only `setCurrentIndex` site (pinned by source-scans).**

**Why it exists:** the Home Dashboard (Race Engineer Command Centre) is the app's overview/landing surface but had to be *appended at index 13* while tabs were index-coupled. The Tab Navigation Refactor made the reorder an order-only edit, so this sprint promotes Home to the first tab + default landing page and lights up the click-to-navigate that was deferred with it.

**Deliverables:**
- **`ui/tab_registry.py`** — `DEFAULT_TAB_ORDER` now **leads with `TAB_HOME`** (comments renumbered 0–13); every non-Home tab keeps its previous relative order (each shifted down one). Header docstring updated. No code/API change — the positional registry re-derives every index.
- **`ui/dashboard.py`** — Home `addTab` moved to first (`# 0`); **`select_tab(TAB_HOME)`** at the end of `_setup_ui` (open on Home by key); one guarded **`_home_refresh()`** at the end of `__init__` (first render — selecting an already-current index emits no signal); `_build_home_tab` now adds a per-card **"Open <Tab>" button** + a next-action button; new helpers **`_home_navigate`** / **`_home_navigate_next_action`** / **`_home_update_next_action_button`** / **`_home_nav_button_text`** + shared `_HOME_NAV_BTN_QSS`; `_home_refresh` updates the next-action button; Guide HTML "Home tab (last tab)" → "(first tab, shown when the app opens)". Navigation is **tab-change only** (`select_tab`), guarded by `has_tab`, never raises.
- **`ui/home_dashboard_vm.py`** — `CARD_TAB_KEYS` mapping + **`tab_key_for_card()`** (imports the pure `ui/tab_registry` key constants — still no PyQt6). Card→tab: Race Setup→Event Planner, Track Intelligence→Track Modelling, Setup Brain→Setup Builder, Strategy Brain→Strategy Builder, AI Input Safety→AI Log. **Stable keys only — never labels** (⚙-decoration-safe).
- **`ui/product_flow.py`** — "Home appended at index 13" note → "first tab (index 0)".
- **`docs/HOME_DASHBOARD_PROMOTION.md` (NEW)** — why/how, final order, card mapping, tab-change-only proof, risks, next sprint.

**Tests:** `tests/test_home_dashboard_promotion.py` (NEW — Home leads default order + is first addTab in source; app selects Home via `select_tab(TAB_HOME)`; `_home_refresh()` at startup; `DEFAULT_TAB_ORDER` still mirrors the addTab sequence; card→tab mapping exact + covers every card + values are real registry keys + unknown card → None; `_home_navigate` uses `select_tab`+`has_tab`; nav methods change tab only — no config/persist/AI/telemetry/worker; next-action button maps name via `key_for_title`; button text from undecorated `TAB_BASE_TITLES`; no new raw `setCurrentIndex`; diagnostics preserved). Updated in place (order renumbered, same invariants): `test_tab_navigation_registry` (Home-first order/index/pin, jump-target indices +1, positional key_at(7)=Telemetry), `test_home_dashboard_vm` (Home leads before Track Modelling), `test_diagnostic_tab_cleanup` + `test_consolidation_product_flow` (tab-order pins). Headless smoke run confirmed: 14 tabs, tab 0 = Home, opens on Home, card + next-action navigation work, unknown target is a safe no-op.

**Next sprint: Legacy Fan-Out Removal Phase 1** (migrate the low-risk read-only `config["strategy"]` consumers onto EventContext/StrategyContext, keep the fan-out writer as compatibility) — the standing higher-risk track. Alternative: **SessionContext / TelemetryContext** (turn Home's `has_valid_laps`/`live_active` approximations into owner-backed truth). Full detail: `docs/HOME_DASHBOARD_PROMOTION.md`, `MASTER_TESTING_REGISTER.md` (Home Dashboard Promotion).

---

## Prior Objective (historical)
**Tab Navigation Refactor — Named Tab Lookup — COMPLETE (2026-07-03).** Branch `tab-navigation-named-lookup` (from `diagnostic-tab-cleanup-ui-dags` @ `c4eafdf`). Full suite: **4512 pass / 6 skip / 0 fail** (33 new tests; 6 legacy tests updated in place to key-based homes). **Navigation infrastructure only: tab order byte-identical, Home stays appended at index 13, per-tab activation behaviour a 1:1 translation of the old index dispatch, no logic/prompt/mapping/PTT/voice/persistence/fan-out change (pinned by source-scans).**

**Why it exists:** tab navigation was keyed to raw numeric positions — `_on_tab_changed` compared hard-coded `10/3/5/4/6/11/12` (+ `_home_tab_index`), three jumps called `setCurrentIndex(4/3/1)`, and two visibility guards compared `currentIndex()` to raw numbers. That forced the Home Dashboard to be appended at 13 and blocked click-to-navigate. This sprint retires the risk the audit flagged as "index-coupled tabs".

**Deliverables:**
- **`ui/tab_registry.py` (NEW, pure Python — no PyQt6, no config)** — one stable key per existing tab (`TAB_LIVE`, `TAB_EVENT_PLANNER`, `TAB_GARAGE`, `TAB_SETUP_BUILDER`, `TAB_PRACTICE_REVIEW`, `TAB_STRATEGY_BUILDER`, `TAB_TELEMETRY`, `TAB_DIAGNOSTICS`, `TAB_GUIDE`, `TAB_SETTINGS`, `TAB_HISTORY`, `TAB_AI_LOG`, `TAB_TRACK_MODELLING`, `TAB_HOME`); `DEFAULT_TAB_ORDER` = the current visual order 0–13 **in one place** (a test extracts the real addTab title sequence from dashboard source and compares 1:1; a runtime count check warns on drift); `TabRegistry` ordered key↔index mapping that never raises (`index_of` → -1, `key_at` → None, duplicate `register` = safe no-op); `key_for_title()` ⚙-decoration-safe reverse lookup — the registry itself is **positional**, so decorated labels can never break lookup; `TAB_BASE_TITLES` cross-checked against `product_flow.TAB_ROLES` by test.
- **`ui/dashboard.py`** — registry built in `_setup_ui` right after the unchanged addTab block; **`_on_tab_changed` dispatches by stable key** (same 8 behaviours: history refresh, setup/strategy/practice syncs, telemetry context, AI-Log flush, TM tab-shown, Home refresh); navigation helpers **`get_tab_index` / `has_tab` / `current_tab_key` / `select_tab`** (all safe on unknown keys; `select_tab` holds the only remaining `_tabs.setCurrentIndex` call site); jumps migrated to `select_tab(TAB_PRACTICE_REVIEW/TAB_SETUP_BUILDER/TAB_EVENT_PLANNER)`; guards migrated to `current_tab_key() != TAB_AI_LOG/TAB_HOME`; `_home_tab_index` retired. Mixins never touched `self._tabs` — unchanged.
- **`docs/TAB_NAVIGATION_REFACTOR.md` (NEW)** — the index problem, the registry, the key table, changed/not-changed, tab-order proof, how the Home move becomes an addTab+`DEFAULT_TAB_ORDER`-only change, remaining risks (order/addTab must be edited together — test-guarded; `build_flow_state_summary` returns display names → map via `key_for_title` when click-to-navigate lands).

**Tests:** `tests/test_tab_navigation_registry.py` (NEW, 33 — registry keys/order/round-trip/garbage safety; decorated-title resolution; positional-lookup proof; module purity; `_on_tab_changed` zero raw index comparisons + all 8 key→handler pairs; only `select_tab` calls `setCurrentIndex`; `_home_tab_index` retired; jump sites + guards keyed; helpers safe/stateless; registry count guard; jump-target mapping proven; all 14 addTab lines pinned; Home after Track Modelling; diagnostics + ⚙ markers; fan-out untouched). Updated in place: `test_group12c` (AI-Log dispatch), `test_group14` DEF-P2-033 flush guard ×2, `test_group3` (history jump), `test_diagnostic_tab_cleanup` + `test_home_dashboard_vm` dispatch scans — same invariants, key-based homes.

**Next sprint: Home Dashboard Promotion — Move Home to index 0 and add click-to-navigate** using the registry (`select_tab`; map the flow summary's tab display names via `key_for_title`). Move the Home addTab call + `TAB_HOME` to the front of `DEFAULT_TAB_ORDER` together and update the order-pinning tests. Alternative higher-risk track: **Legacy Fan-Out Removal Phase 1**.

Full detail: `docs/TAB_NAVIGATION_REFACTOR.md`, `MASTER_TESTING_REGISTER.md` (Tab Navigation Refactor).

---

## Prior Objective (historical)
**Diagnostic Tab Cleanup — Low-Risk UI Dags Removal — COMPLETE (2026-07-03).** Branch `diagnostic-tab-cleanup-ui-dags` (from `home-dashboard-command-centre` @ `d96b967`). Full suite: **4479 pass / 6 skip / 0 fail** (25 new tests). The whole diff is deletions of dead UI, label text and Guide HTML — **no logic, prompt, mapping, PTT/voice, persistence, tab-order, Home-Dashboard, or fan-out change** (all pinned by source-scans).

**Why it exists:** executes the Product Consolidation Audit's remaining low-risk cleanup items (§9 1/3/4) now that the Home Dashboard exists to carry the user-facing overview.

**Deliverables:**
- **7 legacy per-segment review buttons DELETED** (`ui/track_modelling_ui.py`) — Confirm/Rename/Reject/Needs More Laps/Split Required/Merge Required/Save Reviewed Model were hidden at creation AND never `clicked.connect`-ed, so the 7 `_tm_review_*` handlers were unreachable. Also deleted: the save-path label, 4 never-applied `_rev_btn_*` style strings, `_tm_refresh_review_buttons` (+2 call sites), the no-op `_tm_refresh_approval_panel` (+1 call site), and 8 dead imports. **Retained:** the pure review-action functions in `data/track_segment_review.py` and `ui/track_modelling_vm.get_review_button_states` (own coverage; import test proves intact). `test_group24` `_tm_` method floor 54→46 (deleted methods enumerated in the test comment).
- **Dead `_TELEMETRY_REFERENCE_HTML` DELETED** (`ui/dashboard.py`, ~143 lines) — the audit thought the 72-field packet reference was embedded in the Guide; it was actually dead code, defined but never rendered anywhere.
- **Renames:** "Race Config ID:" → **"Session Match Key:"** (plain-English tooltip; the `config_id` value/mechanics and lap-bank behaviour untouched); Diagnostics tab "Rem(clk):" → "Time left:", "rem_ms(raw):" → "remaining_time_ms:" (real packet-field name, consistent with the raw row), "Ann queue:" → "Voice queue:" — creation defaults and `setText` sites updated together; window title + Guide h1 "GT7 VR Dashboard" → **"Next Gear Racing Pit Crew"** (the only two user-facing old-brand sites).
- **Guide fixes (`_GUIDE_HTML`):** Step 8 described a **"Dashboard" tab with quick-link buttons that never existed** — rewritten to describe the real Home tab (Race Engineer Command Centre); the API-key bullet said the key could be pasted in Settings — **corrected finding: no Settings key field exists**, the Strategy Builder `self._ai_api_key` field is the single editable entry every AI caller reads (audit §4 corrected; relocation to Settings deferred); new intro note "Tool tabs (⚙) … are advanced tools … safe to ignore during a normal race weekend"; "pip install requests beautifulsoup4" removed from the web-refresh tooltip.
- **`docs/DIAGNOSTIC_TAB_CLEANUP.md` (NEW)** — per-item audit tables (control, file, purpose, reachability, verdict, risk, action), the corrected API-key/telemetry-reference findings, and the deferred list (TM jargon glossary, Telemetry raw-row hiding, API-key relocation, both `config["strategy"]` fan-outs — the fan-outs are pinned-still-present by test).

**Tests (`tests/test_diagnostic_tab_cleanup.py`, 25):** deleted widgets/methods/imports gone with zero string/getattr references remaining in either UI module; backend review functions importable; renames present + stale labels absent; Guide fixed; tab order pinned (incl. Home appended at 13); `_on_tab_changed` dispatches unchanged; diagnostic tabs still built; product_flow diagnostic set unchanged; Home Dashboard wiring intact; both legacy fan-outs untouched; no strategy writes in touched areas; the API-key field still exists.

**Next sprint: Tab Navigation Refactor — Named Tab Lookup** — replace the hard-coded indices in `_on_tab_changed` with lookup-by-title/object so tabs can be reordered safely; then **move Home Dashboard to index 0** and enable its deferred click-to-navigate. Alternative higher-risk track: **Legacy Fan-Out Removal Phase 1**.

Full detail: `docs/DIAGNOSTIC_TAB_CLEANUP.md`, `MASTER_TESTING_REGISTER.md` (Diagnostic Tab Cleanup).

---

## Prior Objective (historical)
**Home Dashboard Build — Race Engineer Command Centre — COMPLETE (2026-07-03).** Branch `home-dashboard-command-centre` (from `ai-snapshot-migration-context-freeze` @ `f8e9a9d`). Full suite: **4454 pass / 6 skip / 0 fail** (52 new tests). **Display-only: no race/setup/strategy/track-mapping/calibration/AI-prompt/PTT/voice change, no tab reordered/renamed/removed, no legacy store touched, no polling/workers added.**

**Why it exists:** `REQUIREMENTS.md §12.2` specified a Dashboard/home tab ("Suggested next action") that was never built (audit §1.1). The five prior sprints delivered everything it needs — the four canonical read models, the AI snapshot layer, and `build_flow_state_summary()` — so this sprint is the rendering job those sprints deferred, including surfacing the staleness indicators that until now only appeared in GT7_AI_DEBUG stdout.

**Deliverables:**
- **`ui/home_dashboard_vm.py` (NEW, pure Python — no PyQt6/AI/DB/network/file-I/O, source-scanned)** — `build_home_dashboard_state()` (never raises; each section defensive; garbage in any slot degrades to a missing/"Status unavailable" card) → `HomeDashboardState` with five `HomeDashboardCard`s (`READY`/`ATTENTION`/`MISSING`/`BLOCKED`, plain-English lines + `HomeDashboardWarning`s) + `HomeDashboardNextAction`. Cards: **Race Setup** (EventContext + its validator), **Track Intelligence** (TrackContext availability/geometry/alignment + live-mapping blockers + track-vs-event mismatch), **Setup Brain** (`_last_setup_context`: purpose/source/changes/applied + stale-vs-event + stale-vs-strategy via a derived `StrategyPromptSnapshot`), **Strategy Brain** (StrategyContext plan/fuel + stale-vs-event via `event_change_hash`), **AI Input Safety** (AI snapshot core: CONTEXTS = "frozen snapshot" / LEGACY_ONLY = legacy-fallback warning / stale warnings). `build_flow_flags()` bridges contexts → `build_flow_state_summary()` gates (`has_strategy` requires a stint plan, not just a config; telemetry flags caller-supplied). `format_card_html`/`format_next_action_html` pure renderers with HTML escaping.
- **`ui/dashboard.py`** — **Home tab APPENDED at index 13** (`_build_home_tab`; indices 0–12 and all `_on_tab_changed` dispatches unchanged — the only zero-risk placement while indices stay hard-coded; `self._home_tab_index` captured at creation). `_build_home_dashboard_state()` reads `_build_event_context()` / `_build_strategy_context()` / `_build_track_context()` / `_last_setup_context` / `_build_strategy_ai_snapshot()` (pure computation — no AI call) + `_home_has_practice_laps()` (read-only DB query for saved sessions with laps for the active car/track). `_home_refresh()` renders; `_home_refresh_if_visible()` is the guarded hook (no-op unless Home is the current tab). Refresh triggers: tab-shown, Refresh button, end of `_on_event_set_active`, end of `_update_race_config`.
- **`ui/setup_builder_ui.py` / `ui/track_modelling_ui.py`** — one hasattr-guarded `_home_refresh_if_visible()` call each at the end of `_display_setup_result` / `_tm_refresh_track_truth_panel`.
- **`ui/product_flow.py`** — "Home" registered `ROLE_WORKFLOW` (diagnostic set unchanged).
- **`docs/HOME_DASHBOARD_BUILD.md` (NEW)** — sections, context sources, refresh triggers, display-only proof, documented approximations (`has_valid_laps` = recorded laps exist; `live_active` = telemetry connected), deferred items, cleanup risks, next sprint.

**Tests (`tests/test_home_dashboard_vm.py`, 52):** empty/event-only/incomplete-event; fresh + stale strategy vs event, plan-less, uncalibrated fuel; fresh setup matching current event, stale vs event, stale vs strategy snapshot, missing identity; track ready / missing identity / seed-without-geometry / station-map-missing → live mapping BLOCKED / event mismatch; AI snapshot clean/legacy/stale/bare-core/missing; next-action ordering across the whole journey + progress partition; no-jargon display-string scan; spec-exact stale wording; never-raises (garbage + attribute-raising objects in every slot); HTML escaping; source-scans (tab order pinned, diagnostic tabs present, home reads contexts, home methods write nothing — no config["strategy"]/persist/DB/file writes, hooks guarded, no QTimer/QThread/workers, VM import purity).

**Intentionally deferred:** setup-card persistence across restarts (needs an "active setup" record), click-to-navigate (do with the index-by-lookup refactor), per-panel stale badges on the Strategy/Setup tabs themselves, SessionContext/TelemetryContext-owned `has_valid_laps`/`live_active`, AI-call-time snapshot capture (Home shows what a call made *now* would use — the migrated AI methods were not touched). **Next sprint: Diagnostic Tab Cleanup** (audit §9 items 1–4) or **Legacy Fan-Out Removal Phase 1** — see `docs/HOME_DASHBOARD_BUILD.md` §7.

Full detail: `docs/HOME_DASHBOARD_BUILD.md`, `MASTER_TESTING_REGISTER.md` (Home Dashboard Build).

---

## Prior Objective (historical)
**AI Snapshot Migration — Frozen Context Inputs — COMPLETE (2026-07-03).** Branch `ai-snapshot-migration-context-freeze` (from `state-consolidation-4-track-context` @ `45b48d5`). Full suite: **4402 pass / 6 skip / 0 fail** (41 new tests; 20 legacy source-scan tests updated in place — same invariants, new home). **No prompt wording changed, no setup/strategy intelligence changed, no PTT/voice change, no tab reordered, no legacy store removed.**

**Why it exists:** every AI-input path assembled its inputs live from `config["strategy"]` at prompt time (SSOT-7/12) — prompts could mix stale fan-out copies with fresh UI state, and the Build-Setup worker re-read config mid-flight. This sprint threads **frozen, owner-documented snapshots** of the four canonical contexts into the AI-input assembly, byte-identical wherever the stores are in sync.

**Deliverables:**
- **`data/ai_context_snapshot.py` (NEW, pure Python)** — `AIContextSnapshot` core (combined `snapshot_id` + the four component change markers + `source` CONTEXTS/LEGACY_ONLY/EMPTY + build `warnings` + `stale_warnings`); use-case snapshots `StrategyAISnapshot` / `PracticeAnalysisSnapshot` (frozen `race_params` → `RaceParams(**…)`; two types because the practice path's DEF-P1-005 safe default — unknown tuning → LOCKED — differs from the strategy paths' unlocked default, both preserved exactly) and `SetupAISnapshot` (17 event/track fields with the build-setup 0.0 refuel/pit-loss defaults preserved); staleness detection at build time (strategy-vs-event, setup-vs-event, track-vs-event mismatch); `validate_ai_context_snapshot()`; LEGACY_ONLY fallback evaluates the **exact legacy expressions** with a warning — never silent.
- **`docs/AI_SNAPSHOT_MIGRATION.md` (NEW)** — all 11 AI prompt/input paths with per-input owners, migrated vs deferred, the byte-identity proof list, the 4 documented intentional differences, updated legacy tests, remaining legacy dependencies, next sprint.
- **`ui/dashboard.py`** — `_build_strategy_ai_snapshot()` / `_build_practice_ai_snapshot()` helpers; **migrated**: `_assemble_strategy_inputs` (also serving the mid-race re-plan), `_run_ai_analysis` (incl. `config_id` from the snapshot), `_run_practice_analysis` (GT7_AI_DEBUG line now prints snapshot id/source + stale warnings — debug stdout only).
- **`ui/setup_builder_ui.py`** — `_build_setup_ai_snapshot()` helper (threads EventContext + StrategyContext + TrackContext + the captured `_last_setup_context` as a SetupPromptSnapshot); **migrated**: `_run_build_setup` (16 scattered event reads → one frozen snapshot; worker-thread rec metadata now uses the frozen track/layout — mid-flight config re-read removed), `_setup_analyse_ai` (allowed/locked/mandatory-compounds).

**Byte-identity proof (`tests/test_ai_context_snapshot.py`, 41):** verbatim-captured legacy expressions vs snapshot output — identical for synced state, fuel-burn override, lap race, BoP+locked, no-DB-event, absent-key defaults (25/10.0/23.0/2.0), present-zero preservation, both tuning-default regimes, setup-path defaults; plus **`test_prompt_text_byte_identical`** on the real `_build_race_prompt`. **Intentional differences (each tested):** (1) fresh DB event supersedes a stale fan-out copy — the point of the migration; (2) practice tuning-absent-but-DB-present uses DB truth instead of the blind locked default; (3) GT7_AI_DEBUG stdout format; (4) build-setup `race_laps` always int. Snapshot semantics: id stable/changing per each of the four contexts, frozen after legacy mutation, staleness detection, garbage safety, legacy fallback, source-scans (migrated methods contain no direct event-field config reads).

**Intentionally NOT changed:** prompt builders' internals (`_build_race_prompt`/`_build_practice_prompt`/driving_advisor prompts), `_launch_replan_worker` race_situation, `_computed_fuel_burn_lpl()` (telemetry-owned), DEF-P2-007 display validation, PTT paths, degradation worker, all legacy stores. Stale indicators surface in GT7_AI_DEBUG only — UI labels deferred to the Home Dashboard sprint. **Next sprint: Home Dashboard Build** (render `build_flow_state_summary` from the four contexts' flow flags + surface staleness) — see migration doc §9.

Full detail: `docs/AI_SNAPSHOT_MIGRATION.md`, `MASTER_TESTING_REGISTER.md` (AI Snapshot Migration).

---

## Prior Objective (historical)
**State Consolidation 4 — TrackContext — COMPLETE (2026-07-03).** Branch `state-consolidation-4-track-context` (from `state-consolidation-3-setup-context` @ `d9c6231`). Full suite: **4361 pass / 6 skip / 0 fail** (68 new tests). No feature added, no track mapping feature started, no UI rebuilt, no tab reordered, no PTT/voice change, no Daytona accuracy claims. All legacy track files/loaders/resolver/calibration code retained unchanged.

**Why it exists:** track state is the worst-scattered state in the app (audit SSOT-2): the display name lives in `config["strategy"]["track"]` (written by Event Planner), the canonical ids in `config["strategy"]["track_location_id"/"layout_id"]` (written by the *Track Modelling combos*, track_modelling_ui.py:928-929), the model artefacts in six per-layout file formats under `data/track_models/` + the track library, and the live state in volatile dashboard attributes (`_tm_station_map`, `_tm_alignment_result`, `_tm_offset_calibration`). Nothing answers "what track is selected, what model data exists, is any of it stale?" in one place. This sprint adds a canonical **TrackContext** read model owning identity + availability + status, keyed to `EventContext.change_hash`.

**Deliverables:**
- **`data/track_context.py` (NEW, pure Python — no PyQt6/DB/AI/file-I/O)** — `TrackIdentity` (ids + display names + `combined_id` matching the `<loc>__<lay>` file conventions), `TrackMapAvailability` (seed metadata/corner-windows/geometry, reference path, calibration laps, station map, reviewed/accepted model, lap offset — every flag echoes the existing audits, never invents accuracy), `TrackGeometryStatus` (modelling status resolver-first, ai_ready, resolver outcome, track-truth gates echoed **tri-state**), `TrackAlignmentStatus`, `TrackContextSource` (EMPTY/TRACK_MODELLING_UI/EVENT_CONTEXT/LEGACY_STRATEGY/SEED_LIBRARY — identity priority: combos → EventContext → config ids → seed), `TrackContextValidationResult` (identity vs availability vs staleness warnings kept separate); staleness/mismatch helpers `matches_event` (tri-state), `mismatches_event`, `is_stale_for_event`, `can_attempt_live_mapping`, `live_mapping_blockers()`; `build_track_context()` takes duck-typed results the existing loaders already produce (`SeedAuditResult`, `TrackModelFileAudit`, `TrackModelResolverResult`, `TrackModelAlignmentResult`, `LapStartOffsetCalibration`, `TrackTruthValidationResult`), never raises; `compute_change_hash()` over identity+availability+status only; splat-safe `flow_flags()` bridge composable with `event_context.flow_flags`.
- **`docs/TRACK_CONTEXT_MIGRATION.md` (NEW)** — full SSOT audit of all 16 track state items (owner, files:lines, duplication verdict, future owner), every file format, what was migrated, deferred consumers (live map dot, AI id reads, the Group 17H combo fan-out writer), stale-model/alignment/library risks, next-sprint plan.
- **`ui/track_modelling_ui.py`** — `_build_track_context()` helper (assembles from combo ids + loaded seed + the same `audit_layout_seed`/`audit_track_model_files` audits the tab already runs + the volatile `_tm_*` objects + `_build_event_context()`; never raises); **migrated**: `_tm_refresh_track_truth_panel()` reads track/layout identity through TrackContext (combo-sourced only — strictly behaviour-preserving; empty selection keeps the empty state) and captures `self._last_track_context`.

**Tests:** `tests/test_track_context.py` (NEW, 68 — identity resolution priority + all four sources; availability for seed/geometry/ref-path/calibration-laps/station-map(flag+object)/reviewed/accepted; geometry status incl. resolver-wins + tri-state truth gates (Daytona-style echoed False); alignment status incl. garbage-not-available; lap offset not_loaded/provisional_zero/calibrated/on_disk_not_loaded; change-hash on identity/availability/alignment change + **hash ignores event change** (tracked via `event_change_hash`); staleness/mismatch (tri-state matches_event, display-name fallback, live-mapping gate + blockers); ownership boundary (no event/strategy/setup fields); garbage-input safety; validation separation incl. **missing-geometry honesty even when accepted**; serialisation/immutability; splat-safe flow_flags into `build_flow_state_summary`; track_modelling source-scans incl. the intentionally-unchanged legacy combo fan-out).

**Intentionally NOT changed:** the live map dot identity read, the AI id reads (`track_context_prompt`, `_run_practice_analysis`, `_assemble_strategy_inputs`), the `_tm_on_layout_changed` config fan-out writer, all calibration/detection/review/accept workflows, all persistence formats. `_last_track_context` is captured but not yet surfaced. **Next sprint: AI Snapshot Migration** (thread frozen Event/Strategy/Setup/Track state into the AI-input paths, prove prompts byte-identical) or **Home Dashboard Build** (render `build_flow_state_summary` from the four contexts' flow flags) — see migration doc §8.

Full detail: `docs/TRACK_CONTEXT_MIGRATION.md`, `MASTER_TESTING_REGISTER.md` (State Consolidation 4 — TrackContext).

---

## Prior Objective (historical)
**State Consolidation 3 — SetupContext — COMPLETE (2026-07-03).** Branch `state-consolidation-3-setup-context`. Full suite: **4293 pass / 6 skip / 0 fail** (67 new tests). No feature added, no backend capability removed, no UI rebuilt, no tab reordered, no live PTT/voice change. Legacy setup config/DB storage retained as compatibility.

**Why it exists:** setup state is scattered across four stores (the current form setup, `config["car_setup"]["setups"]`, the `setups`/`setup_recommendations` DB tables, and the AI response payload), and **none records which event/strategy assumptions a setup was built against** — so a setup can silently go stale when the event or strategy changes. This sprint adds a canonical **SetupContext** read model that owns *only* setup-recommendation state and is **keyed** to `EventContext.change_hash` and `StrategyPromptSnapshot.snapshot_id` so stale setups become detectable.

**Deliverables:**
- **`data/setup_context.py` (NEW, pure Python, no PyQt6/DB/AI)** — `SetupContext` (immutable; owns setup_id/config_id/label, purpose, source, adjustments, changed fields, frozen baseline+target setups, reason/primary_issue/confidence, validation warnings, applied state, `change_hash` + `event_change_hash`/`strategy_snapshot_id`/`telemetry_diagnosis_hash`); `SetupChangeEntry` (round-trips the AI `changes` shape); `SetupContextSource` (EMPTY/AI/GENERATED/MANUAL/SAVED_DB/LEGACY_CONFIG); `SetupPurpose` (QUALIFYING/RACE/PRACTICE/TEST/UNKNOWN) + `normalise_purpose()`; `SetupContextValidationResult` (keeps setup-input vs staleness warnings separate); `SetupPromptSnapshot` + `build_setup_prompt_snapshot()` (value-copied freeze of setup + event/strategy keys, stable under later config mutation); keying helpers `matches_event`/`is_stale_for_event`/`is_stale_for_strategy`/`is_missing_identity`/`matches_purpose`; `build_setup_context(...)` never raises; `compute_change_hash()` over setup fields only.
- **`docs/SETUP_CONTEXT_MIGRATION.md` (NEW)** — every setup store (config/DB/AI-response/diagnosis/history) with writers/readers, ownership boundary, what was migrated, deferred consumers, stale/prompt/validation risks, next-sprint plan.
- **`ui/setup_builder_ui.py`** — `_build_setup_context()` helper (current setup + EventContext + StrategyPromptSnapshot → SetupContext, defensive); **migrated**: `_setup_type_prefix()` derives purpose via `normalise_purpose`; `_display_setup_result()` captures the canonical `SetupContext` into `self._last_setup_context` (read-only/additive — no display change).

**Tests:** `tests/test_setup_context.py` (NEW, 67 — normalise_purpose; build sources; setup fields preserved; ownership boundary (no event/strategy fields); qualifying-vs-race distinguishable; staleness on event/strategy hash change; setup hash ignores event/strategy; diagnosis hash; malformed-input safety; validation setup-vs-staleness separation; frozen prompt snapshot stable under later mutation; serialisation/immutability; legacy setup-dict compat; setup_builder source-scans).

**Intentionally NOT changed:** the AI setup-**prompt** paths (`build_setup_advice_response`/`build_combined_setup_response`/`build_car_setup`) and the apply/save writers still read the legacy stores — deferred until a frozen `SetupPromptSnapshot` can be threaded with byte-identical-prompt tests (migration doc §6). All writers unchanged. `_last_setup_context` is captured but not yet surfaced. **Next sprint: TrackContext** (unify track/layout SSOT-2) or migrate the deferred AI-input consumers to frozen snapshots (migration doc §9).

**Git:** the three prior consolidation sprints were committed on `fix/def-17u-uat007-timetrial-calibration` (commit `1dca4a5`) before this sprint branched to `state-consolidation-3-setup-context`.

Full detail: `docs/SETUP_CONTEXT_MIGRATION.md`, `docs/STRATEGY_CONTEXT_MIGRATION.md`, `docs/EVENT_CONTEXT_MIGRATION.md`, `MASTER_TESTING_REGISTER.md` (State Consolidation 3 — SetupContext).

---

## Prior Objective (historical)
**State Consolidation 2 — StrategyContext — COMPLETE (2026-07-03).** Full suite: **4226 pass / 6 skip / 0 fail** (53 new tests). No feature added, no backend capability removed, no UI rebuilt, no tab reordered. `config["strategy"]` retained as legacy compatibility.

**Why it exists:** `config["strategy"]` mixes event/race configuration (now owned by EventContext) with strategy-plan state (stint plan, planned stops, fuel burn per lap, the derived `config_id`, degradation assumptions, analysis tolerances). This sprint adds a canonical **StrategyContext** read model that owns *only* the strategy-plan half and **reads event/race rules from EventContext** so the two can't drift.

**Deliverables:**
- **`data/strategy_context.py` (NEW, pure Python, no PyQt6/DB)** — `StrategyContext` (immutable, normalised), `StintPlanEntry` (round-trips to the legacy `stops` dict shape), `StrategyContextSource` (EMPTY/LEGACY_STRATEGY/GENERATED), `StrategyContextValidationResult` (keeps `strategy_*` warnings separate from `event_*` warnings), `StrategyPromptSnapshot` + `build_strategy_prompt_snapshot()` (value-copied freeze of a consistent EventContext race config + StrategyContext plan, stable even if `config["strategy"]` mutates later; `snapshot_id` = hash of event+strategy change markers); `build_strategy_context(strategy, event_context, tyre_degradation, source)` (never raises; ignores event fields in the strategy dict), `validate_strategy_context()`, `compute_change_hash()` (strategy fields only — event tracked via `event_change_hash`).
- **`docs/STRATEGY_CONTEXT_MIGRATION.md` (NEW)** — ownership boundary table (rate-vs-number split: `mandatory_stops`/`refuel_rate_lps` stay EventContext; *planned* stops + pit laps are StrategyContext), every strategy-specific `config["strategy"]` field with writer/readers, what was migrated, deferred consumers, risks, and the SetupContext next-step plan.
- **`ui/dashboard.py`** — `_build_strategy_context()` helper (config["strategy"] + `_build_event_context()` + `_tyre_degradation_cache` → StrategyContext, defensive); **one low-risk consumer migrated**: `_refresh_lap_bank()` reads the active `config_id` from StrategyContext for the practice-lap-bank ★ marker.

**Tests:** `tests/test_strategy_context.py` (NEW, 53 — build sources, strategy fields preserved, ownership boundary (no event fields), stint-plan parse + planned-stops/pit-laps derivation, degradation fields, change markers (strategy hash ignores event fields; event hash changes independently), malformed-input safety, validation strategy-vs-event separation, frozen prompt snapshot stability under later config mutation, serialisation/immutability, legacy round-trip, dashboard source-scans).

**Intentionally NOT changed:** the AI-input path (`_assemble_strategy_inputs`, `_run_ai_analysis`, `_launch_replan_worker`) still reads `config["strategy"]` — highest-risk, migrate as a unit with a frozen `StrategyPromptSnapshot` per call (see migration doc §6). All writers unchanged. **Next sprint: SetupContext** keyed on `EventContext.change_hash` + `StrategyPromptSnapshot.snapshot_id` (migration doc §9).

Full detail: `docs/STRATEGY_CONTEXT_MIGRATION.md`, `docs/EVENT_CONTEXT_MIGRATION.md`, `MASTER_TESTING_REGISTER.md` (State Consolidation 2 — StrategyContext).

---

## Prior Objective (historical)
**State Consolidation 1 — EventContext — COMPLETE (2026-07-03).** Full suite: **4173 pass / 6 skip / 0 fail** (38 new tests). No feature added, no backend capability removed, no UI rebuilt, no tab reordered. `config["strategy"]` retained as legacy compatibility.

**Why it exists:** the audit found the worst single-source-of-truth violation is `_on_event_set_active()` fanning the active event into `config["strategy"]` — a god-object snapshot that can drift from the durable DB event record (which even uses different field names: `tyre_wear`/`duration_mins`/`refuel_rate_lps` vs `tyre_wear_multiplier`/`race_duration_minutes`/`refuel_speed_lps`). This sprint adds a canonical **EventContext** read model without changing behaviour.

**Deliverables:**
- **`data/event_context.py` (NEW, pure Python, no PyQt6/DB)** — `EventContext` (immutable, normalised), `EventContextSource` (EMPTY/DB_EVENT/LEGACY_STRATEGY/MERGED), `EventContextValidationResult`; `build_event_context(event, strategy, active_event_id)` (DB-event-first resolution, overlays car + track ids from strategy, falls back to strategy; never raises); `validate_event_context()` (warnings not crashes); `compute_change_hash()` (stable 12-char change marker); `flow_flags()` bridge to `ui/product_flow.py`; `to_dict`/`summary_line`/`to_summary_lines`.
- **`docs/EVENT_CONTEXT_MIGRATION.md` (NEW)** — every `config["strategy"]` read site (~35) with enclosing method, fields, risk, and EVENT-CONFIG vs NON-EVENT classification; the single fan-out writer (`_on_event_set_active`); the migration plan and the StrategyContext/SetupContext next-step plan.
- **`ui/dashboard.py`** — `_build_event_context()` helper (DB event + `config["strategy"]` + `active_event_id` → EventContext, defensive); **one low-risk consumer migrated**: `_refresh_telemetry_context()` reads event/car/track from EventContext (DEF-P1-011 fuel-burn behaviour preserved).

**Tests:** `tests/test_event_context.py` (NEW, 38 — build sources, field-name normalisation both schemas, timed-stays-timed / lap-stays-lap, BoP + tuning + multipliers + refuel preserved, DB-first beats stale strategy, change-hash detects edits, validation warnings without crashes, garbage-input safety, legacy strategy-only build, `flow_flags`→`product_flow` interop, immutability, dashboard source-scan).

**Intentionally NOT changed:** `config["strategy"]` still written by `_on_event_set_active` and still read by the other ~34 sites (compatibility). `driving_advisor.set_event_context()`/`_event_ctx` left as-is (AI prompt behaviour untouched). **Next sprints: StrategyContext then SetupContext** (see migration doc §6–§7), then remove the fan-out and migrate the low-risk read-only consumers; also build the home/overview panel from `build_flow_state_summary(**flow_flags(ctx))`.

Full detail: `docs/EVENT_CONTEXT_MIGRATION.md`, `docs/PRODUCT_CONSOLIDATION_AUDIT.md` (§5/§7), `MASTER_TESTING_REGISTER.md` (State Consolidation 1 — EventContext).

---

## Prior Objective (historical)
**Product Consolidation Sprint — audit + safe first-pass UI clean-up — COMPLETE (2026-07-03).** Full suite: **4135 pass / 6 skip / 0 fail** (27 new tests). No feature added, no backend capability removed, no tab reordered.

**Why it exists:** the app reached 13 top-level tabs built patch-on-patch, mixing the core race-engineer workflow (6 tabs) with developer/diagnostic tooling (Telemetry, Debug, AI Log, Track Modelling) and accumulated jargon. `REQUIREMENTS.md §12` specified a **Dashboard/home** tab ("suggested next action") that was never built. This sprint audited the whole product against the intended 13-step journey and implemented only low-risk clean-up.

**Deliverables:**
- **`docs/PRODUCT_CONSOLIDATION_AUDIT.md` (NEW)** — the specific audit: per-tab KEEP/MOVE/RENAME/MERGE/DELETE/HIDE_UNTIL_READY verdicts (with `ui/dashboard.py` line refs), duplicate workflows, stale labels, diagnostic-controls-in-normal-flow, the 14-item single-source-of-truth ownership table + ranked violations, a 9-context target architecture (EventContext…DiagnosticsContext), what changed, and next-sprint plan.
- **`ui/product_flow.py` (NEW, pure Python, no PyQt6)** — single source of truth for tab roles (workflow/support/diagnostic), the canonical 13-step journey, tab-title decoration, and `build_flow_state_summary()` (the logic behind the missing "suggested next action" home surface).

**Safe UI changes implemented (display-only / additive):**
- `ui/dashboard.py`: tab 7 renamed **"Debug" → "Diagnostics"**; new `_apply_product_flow_tab_markers()` prefixes the four tool tabs (Telemetry, Diagnostics, AI Log, Track Modelling) with a ⚙ marker sourced from `product_flow`. Idempotent, indices unchanged (tab order is hard-coded in `_on_tab_changed`).
- `ui/track_modelling_ui.py`: misleading **"5. Track Model Alignment" → "5. Seed Geometry"** (that section only builds seed geometry; alignment metrics live in Section 4); **"Resolver Status" → "Track Model Status"**.

**Tests:** `tests/test_consolidation_product_flow.py` (NEW, 27 tests — roles, decoration idempotency, 13-step journey integrity, flow-state gate logic, source-scans of the renames). Updated `tests/test_group23b_ui_cleanup.py` Section-5 assertion.

**Intentionally NOT changed (higher-risk, documented in the audit §5/§8/§9):** the `config["strategy"]` event fan-out (worst SSOT violation), track/layout split three ways, setups dual-resident in config+DB, the 7 hidden legacy per-segment buttons (`track_modelling_ui.py:517–524`, still `getattr`-referenced), and the Track Modelling jargon glossary. **Recommended next sprint: "State Consolidation 1 — EventContext"** + build the home/overview panel from `build_flow_state_summary`.

Full detail: `docs/PRODUCT_CONSOLIDATION_AUDIT.md`, `MASTER_TESTING_REGISTER.md` (Product Consolidation Sprint).

---

## Prior Objective (historical)
**DEF-17U-UAT-007 — Time Trial calibration laps falsely classified as pit-in / unusable — FIXED (2026-07-03).** Branch `feature/group-18a-track-truth-foundation`.

**Symptom (Post-Group-17U UAT):** In GT7 Time Trial the user drove 5 clean laps and never pitted. Building the reference path failed with *"Not enough usable laps to build reference path (0 usable, need 2)"*. Diagnostics wrongly reported 7 captured laps, rejected lap 1 as an outlier (18.1s / 749m vs session median 128.7s / 6171m), detected laps 2–6 as "pit-in laps", rejected lap 7 (40 samples < 50), and concluded *"All calibration laps appear to be pit-in laps."*

**Root cause:**
1. GT7 Custom UDP telemetry has **no reliable per-sample pit-lane flag** (`TelemetrySample.is_in_pit_lane` is always `None`). Pit-in was inferred by `detect_pit_lap_raw()` purely from XZ-centroid geometry (a contiguous run > 60 m from lap centroid for > 10 s), which **false-positives on normal Time Trial laps**.
2. Short partial first/last laps (captured when Start/Stop is pressed mid-lap) poisoned the session median and were mislabelled as generic outliers.

**The fix (`data/track_calibration.py`, `ui/track_modelling_vm.py`, `ui/track_modelling_ui.py`, `data/track_segment_detection.py`):**
- **Pit-in detection is DISABLED BY DEFAULT.** `build_reference_path(session, *, pit_detection_enabled=False)`. `detect_pit_lap_raw()` is not called and no "pit-in" wording is emitted unless a caller explicitly opts in. The "All calibration laps appear to be pit-in laps / Drive a clean lap first" message only appears when pit detection actually ran.
- **New `CalibrationLapQuality` values `PARTIAL_START` / `PARTIAL_STOP`.** The first/last lap of a session is classified as a partial start/stop lap when its path length is below `PARTIAL_LAP_PATH_FRACTION` (0.5) of the interior (complete-lap) median AND it has ≥ `MIN_CALIBRATION_SAMPLES` (50). Guarded to sessions with > 2 laps. Partial laps carry exactly one reason ("partial start lap" / "partial stop lap"), are excluded from the build, and are **NOT** counted in `rejected_lap_count`.
- **Session median duration/path is computed from complete (non-partial) laps only**, so partials can't drag full laps into "outlier" rejection.
- `CalibrationBuildResult` gained `partial_start_count`, `partial_stop_count`, `rejected_too_few_samples`, `rejected_path_length`, `pit_detection_enabled`. `diagnose_calibration_session()` surfaces `partial_start_count` / `partial_stop_count` / `pit_detection_enabled` and per-lap `"partial_start"` / `"partial_stop"` quality strings.
- **UI:** `format_no_usable_laps()` gives a count-based failure message ("Pit detection: off", complete-candidate count, partial / too-few-samples / path-length breakdown) and never says "pit-in" or "Drive a clean lap first" when complete candidates existed but were rejected. `format_build_failure_diagnostics()` shows the new breakdown, filters pit warnings when pit detection is off, and only recommends "Avoid pit stops" when pit detection ran. `_CAL_LAP_QUALITY_LABELS` maps `partial_start`→"Partial (start)", `partial_stop`→"Partial (stop)". The Track Modelling build handler only shows the prominent pit warning label when `result.pit_detection_enabled` is True.
- **Segment-detection** no-usable-laps summary now also reports an "N partial" count so the numbers reconcile with the total captured.

**Tests:**
- New: `tests/test_def17u_uat007_calibration_build.py` (data/build layer, ~35 tests incl. the exact UAT 7-lap regression) and `tests/test_def17u_uat007_partial_laps.py` (UI formatters/labels, 44 tests).
- Updated: `tests/test_group21b_missing_coverage.py` — 2 opt-in pit tests now pass `pit_detection_enabled=True`.
- Full suite: 4200+ passed. The only failing test (`test_group28_analyse_prompt_ranges`) is a **pre-existing** failure in unrelated in-progress "setup ranges" work (`strategy/driving_advisor.py`) and is **not** part of this fix.

**Acceptance criteria met:** a clean Time Trial 5-lap (captured as 7 slices) session builds a reference path; clean laps are never marked pit-in; first/last partial laps no longer block the valid middle laps; build diagnostics are accurate and count-based; no unrelated features changed.

Full detail: `docs/TRACK_MODELLING_RUNTIME_UAT.md` (DEF-17U-UAT-007), `MASTER_TESTING_REGISTER.md` (DEF-17U-UAT-007 remediation).

---

## Prior Objective (historical)
**Group 18A — Track Truth Library, Calibration Wizard, and Station-Based Map Matching Foundation — COMPLETE.** Full suite: **4053 pass / 6 skip / 0 fail** (45 new tests). No automated-test blockers.

**Why it exists:** the app was still treating **curvature-only detected corners** as authoritative track truth. Group 18A lays the foundation for a proper Track Truth system. Product principle: **no mapped-corner confidence ⇒ no high-confidence setup/strategy recommendation.** **Foundation only** — the Setup Brain, Strategy Brain, and Live Race Engineer are NOT yet rewired to consume it.

**New modules (pure-Python, no PyQt6):**
- `data/track_truth.py` — Track Truth data model + validation + AI guard. Enums `TrackTruthStatus` / `TrackTruthConfidence` / `TrackTruthSource` / `TrackTruthValidationIssue`; dataclasses `TrackStation`, `CornerWindow`, `CornerComplex`, `SectorMarker`, `PitLaneDefinition`, `TrackTruthManifest`, `TrackTruthModel`, `TrackTruthValidationResult`; `resolve_track_truth_model(track_id, layout_id, base_dir=None)`, `validate_track_truth_model(model)`, `can_use_track_truth_for_ai_corner_context(result)`. `track_truth_model_from_dict` returns None on schema mismatch (never raises).
- `data/track_truth_matcher.py` — station-based live map-matching foundation. `match_track_truth_position(inp, model, validation=None)` — weighted `_score_candidate` (spatial + heading + monotonic-progress + lap-wrap + max-plausible-movement + pit), a scaffold to be swapped for HMM/Viterbi later. Confidence bands mirror `track_map_matching.py` (≤5m HIGH / ≤20m MED / ≤60m LOW). Never raises.
- `data/track_truth_calibration.py` — calibration wizard. `TrackTruthWizardStage` (NOT_STARTED → CAPTURE_CENTRELINE → CAPTURE_LEFT_EDGE → CAPTURE_RIGHT_EDGE → OPTIONAL_HOT_LAP → BUILD_PROPOSED → VALIDATE → ACCEPT) + `TrackTruthCalibrationWizard`. Illegal transitions = no-ops that set `state.error`. Geometry DELEGATED to `data/track_geometry_builder.build_seed_geometry` (defensive wrapper, no duplicate algorithm); `accept()` is the only route to ACCEPT and persists via `save_seed_geometry_to_library`; `abandon()` resets, writes no file.

**UI (additive, headless-VM tests only — needs manual UAT):** `ui/track_modelling_vm.py` `format_track_truth_status()` (20-key display dict); `ui/track_modelling_ui.py` "Track Truth / Mapping" panel + `_tm_refresh_track_truth_panel()`.

**New schema:** `track_truth_model_v1` (envelope, nested `track_truth_manifest_v1`). **Runtime-built** from the existing library manifest + semantic_model — NO new JSON file in the library. Full field list in `docs/TRACK_LIBRARY_SCHEMA.md`.

**Validation gates (the spine):**
- `is_accepted` = no blockers. Blockers: non-monotonic stations, progress out of 0–100, `lap_length ≤ 0`, apex outside window, complex → missing corner, sector out of range, `corners_expected > 0` with no windows, and `NO_COORDINATE_GEOMETRY` ("Coordinate geometry unavailable — high-confidence corner mapping is blocked").
- `is_usable_for_live_mapping` = accepted AND stations present AND `manifest.corners_are_seed_verified` (default False).
- `is_usable_for_ai_corner_context` = live-mapping-usable AND `manifest.seed_geometry_available`.
- AI guard True only when accepted AND AI-context-usable; None → False. Single-member complex is a warning, not a blocker.

**Daytona status — BLOCKED (by design):** Daytona truth is built at runtime from its existing manifest + semantic model (12 corners T1–T12, sectors S1–S3, complexes BusStop=T1+T2 and Horseshoe/T10T11=T10+T11). It has no `geometry.seed_map.json`, so the model has zero stations → `NO_COORDINATE_GEOMETRY` → `is_accepted=False` → AI corner context BLOCKED. Curvature peaks are never presented as verified truth. `availability.seed_geometry` stays `false`.

**Tests:** `tests/test_group18a_track_truth.py` (26), `tests/test_group18a_track_truth_matcher.py` (9), `tests/test_group18a_track_truth_calibration.py` (10). Baseline moved 4008 → **4053** pass / 6 skip / 0 fail.

**Natural next step / deferred:** wire `TrackTruthModel` into the Setup Brain / Strategy Brain / Live Race Engineer (so recs respect the no-mapped-corner principle), and/or produce a real Daytona `geometry.seed_map.json` (acceptance stays blocked until it exists). Also deferred: full HMM/Viterbi matcher, non-Daytona tracks, automated boundary generation, deep AI prompt integration, automatic track ID. UI panel needs manual UAT.

Full detail: `docs/TRACK_INTELLIGENCE_STARTER_MODEL.md` (Group 18A), `docs/TRACK_LIBRARY_SCHEMA.md` (Track Truth Model Schema), `MASTER_TESTING_REGISTER.md` (Group 18A — Track Truth Foundation).

---

## Prior Objective (historical)
**Integration: Setup Brain + Strategy Outcome — merged to `master`.** `integration/setup-brain-strategy-overhaul` combined `feature/setup-diagnosis-engine` + `feature/strategy-outcome-comparison` (clean, no conflicts) and was **merged to `master`** (merge commit `7254835`, pushed). **Full combined suite: 3984 pass / 6 skip / 0 fail.** Merged after automated tests passed; **runtime UAT still pending** (SETUP_BUILDER_UAT.md + STRATEGY_BUILDER_UAT.md) — run it against `master` and log results.

Delivered (see MASTER_TESTING_REGISTER.md "Integration — Setup Brain + Strategy Outcome"):
- **Setup Brain:** deterministic app-side diagnosis before the AI call (`strategy/setup_diagnosis.py`), driver tuning-model + hard-constraints at the top of every setup prompt, post-AI engineering validation with regenerate-once-then-surface, low-confidence track-model guard, structured liked/hated setup-history learning. Bug fixes: springs in **Hz** (was N/mm); timed race renders "N minutes, Timed Race" (was "1 laps, Lap Race"). Proven on the Porsche RSR '17 / Fuji regression: ride-height blocked, aero prioritised, gearbox preserved. Tests: `tests/test_group38_setup_diagnosis.py` (74).
- **Strategy Outcome:** deterministic total-race-time comparison (`strategy/outcome.py`) — head-to-head ranking, delta-vs-fastest, confidence, refuel-rate-based pit time, and previously-hidden risk fields on the cards; "pit loss" → "pit time". Tests: `tests/test_group39_strategy_outcome.py` (53) + `tests/test_group40_strategy_card_rendering.py` (44).

**Deferred (carried forward):** setup history key omits track layout (config_id re-hash risk); from-scratch "Build Setup with AI" lacks the post-AI validation loop (no telemetry at build time); strategy finishing-position prediction needs rival telemetry.

**Remaining step:** runtime UAT (against `master`) not yet executed. No automated-test blockers.

---

## Prior Objective (historical)
Group 31 complete. Race-Engineer Prompt Directives, Validation, and Bottoming Classifier. 3426 pass / 6 skip / 0 fail. 144 tests in `tests/test_group31_race_engineer.py`. Both entry points (`build_setup_advice_response` and `build_combined_setup_response`) now normalise, validate, and strip locked fields from the AI response before returning. The UI renders validation errors as a banner. Defects C1/C2/C3/I1/I5 resolved.

## Group 31 — Session Notes (2026-06-29)

**Problem solved:** The setup advisor's AI responses had no server-side validation, could recommend locked fields, allowed no-ops to pass through, used a 1200-token response cap, and had no race-engineer discipline in the prompt.

**What was added / fixed:**

- **`telemetry/recorder.py`:** `LapStats.bottoming_positions: list` field added; `_compute_stats` captures rising-edge XYZ on bottoming events (mirrors snap_throttle_positions pattern).

- **`strategy/driving_advisor.py`:**
  - `_normalise_changes`: no-op stripping — when `from == to_clamped` the change is dropped before it reaches the AI context or the Apply button.
  - `_derive_locked_fields(allowed_tuning) -> set[str]`: maps allowed-tuning category strings to canonical setup param names; has inline comments explaining `steering` and `nitrous` have no canonical params yet.
  - `_validate_setup_response(parsed, car_name, allowed_tuning, locked_fields, setup) -> dict`: 7 checks (unresolvable field, out-of-range, locked, no-op, string-not-number, >4 changes warning, setup_fields mismatch); appends `validation_errors` list; never drops changes.
  - `_classify_bottoming_location(positions, loc_id, lay_id) -> str`: delegates to `enrich_telemetry_issues`; votes on `matched_segment_type`; returns a category string or "unknown".
  - `_race_engineer_directives(...)`: generates AC1–AC13 directive block for injection into both prompts; includes I1 fix — when `setup` is passed and ride height is at the per-car max AND bottoming > 0, emits explicit "do NOT recommend raising it" with field names; when below max, emits "IS permissible".
  - `_get_previous_ai_context(feature, prior_outcomes=None)`: renders structured block with do-not-repeat instruction when `prior_outcomes` is a non-empty list.
  - `build_setup_advice_response`: max_tokens 1000→1500; post-call normalise+validate+C3a locked-strip.
  - `build_combined_setup_response`: max_tokens 1200→1500 (C2); C1 setup_fields rebuild after normalise; C3a locked-field strip from both `changes` and `setup_fields`; normalise+validate; passes `prior_outcomes`.
  - `_build_setup_prompt` and `_build_combined_prompt`: inject `_race_engineer_directives` block + extended JSON schema (AC8 keys: `primary_issue`, `issue_classification`, `validation_targets`, `do_not_change_reasoning`, `confidence`, `expected_validation`).

- **`ui/setup_builder_ui.py`:**
  - `_format_validation_errors_banner(validation_errors: list) -> str`: pure module-level helper — returns HTML orange-banner string; returns "" for empty list.
  - `_display_setup_result`: reads `validation_errors` from parsed JSON; calls `_format_validation_errors_banner`; injects banner before the changes list.

**Defects resolved in this session:**
- C1/I3: `build_combined_setup_response` now rebuilds `setup_fields` from surviving normalised changes — stale no-op keys never reach the validator or Apply button.
- C2: `build_combined_setup_response` max_tokens corrected to 1500.
- C3a: Locked-field changes stripped from both `changes` and `setup_fields` after validation in both entry points.
- C3b: `validation_errors` rendered as orange warning banner in `_display_setup_result`.
- I1/AC3: `_race_engineer_directives` explicitly names ride-height fields at their per-car max and states they must not be raised.
- I5: `_derive_locked_fields` has inline comments for unmapped categories.

**Files added / modified:**
- `telemetry/recorder.py`: `bottoming_positions` field + population logic
- `strategy/driving_advisor.py`: all changes listed above
- `ui/setup_builder_ui.py`: `_format_validation_errors_banner` helper + `_display_setup_result` banner injection
- `tests/test_group31_race_engineer.py` (NEW): 144 tests covering AC1–AC14 + defect-fix targeted tests

**Full suite result after Group 31: 3426 pass / 6 skip / 0 fail**

---

## Group 17U — Session Notes (2026-06-26)

**Problem solved:** After Group 17T, track seed/coordinate files were discovered ad hoc from the flat `data/track_seed_maps/` directory with no schema versioning, no per-layout metadata, no semantic model separation, and no availability summary. As the track library grows, this becomes unmanageable. Group 17U replaces ad hoc file discovery with a structured, versioned track-library registry.

**What was added / fixed:**

- **New `data/track_library.py` module:** Dataclass hierarchy — `TrackLibraryIndex`, `TrackMetadata`, `TrackLibraryAvailability`, `TrackLayoutManifest`, `TrackSemanticModel`, `ValidationAcceptance`, `ValidationWarningThresholds`, `ValidationRules`, `SourceManifest`, `TrackLibraryAuditResult`. All load functions accept optional `base_dir` for testability. `resolve_seed_coordinate_map(track_id, layout_id)` returns `(SeedCoordinateMap|None, source_label)` with library-first, legacy-fallback, then none resolution. `audit_track_library_layout()` returns full availability picture.

- **New `data/track_library/` directory structure:** JSON-based (not YAML) for consistency with seed map files. `index.json` → track index. Per-track `track.json` with layout list. Per-layout directory named `<layout_id>/` containing `manifest.json`, `semantic_model.json`, `validation_rules.json`, `source_manifest.json`, `geometry.seed_map.json` (when available), `accepted_models/`, `calibration_runs/`.

- **Daytona Road Course library skeleton:** All files present except `geometry.seed_map.json`. `manifest.json` sets `availability.seed_geometry = false`. 12 corners T1–T12, 3 sectors S1–S3, 2 complexes (BusStop=T1+T2, T10T11=T10+T11). Source manifest documents T1 apex at 8.2% as verified from UAT telemetry; all other corner windows estimated.

- **`SeedAuditResult` extended:** New fields `seed_source` (`"track_library"/"legacy_fallback"/"none"`), `library_manifest_loaded` (bool), `validation_rules_loaded` (bool). All default to safe values so existing callers see no change.

- **`audit_layout_seed()` updated:** Calls `audit_track_library_layout()` and `resolve_seed_coordinate_map()` when track/layout IDs given. Falls back to legacy-only path if `data.track_library` import fails. Missing centreline message now references the library path.

- **`format_alignment_summary()` updated:** `"seed_source"` key added to the returned dict with display-friendly values ("Track library", "Legacy fallback", "Unavailable", "—").

- **`ui/dashboard.py` updated:** "Seed source" panel row added before "Seed truth source". `_tm_refresh_alignment_panel()` uses `resolve_seed_coordinate_map()` from `data.track_library` (library-first).

**Daytona acceptance status:** BLOCKED. No geometry file. `audit_layout_seed()` returns `seed_source="none"`, `has_seed_centreline=False`. Full geometry match cannot be verified. To unblock: place coordinate data in `data/track_library/tracks/daytona_international_speedway/layouts/daytona_international_speedway__road_course/geometry.seed_map.json` and set `availability.seed_geometry = true` in `manifest.json`.

**New test file:** `tests/test_group17u_track_library_schema.py` — 83 tests covering all 13 categories.

**Files added / modified:**
- `data/track_library.py` (NEW): Full dataclass hierarchy + resolver/loader/audit functions
- `data/track_library/index.json` (NEW): Track library index, schema `track_library_index_v1`
- `data/track_library/tracks/daytona_international_speedway/track.json` (NEW): Track metadata
- `data/track_library/tracks/.../layouts/daytona_international_speedway__road_course/manifest.json` (NEW)
- `data/track_library/tracks/.../layouts/.../semantic_model.json` (NEW): 12 corners, 3 sectors, 2 complexes
- `data/track_library/tracks/.../layouts/.../validation_rules.json` (NEW): acceptance + warning thresholds
- `data/track_library/tracks/.../layouts/.../source_manifest.json` (NEW): data provenance
- `data/track_intelligence.py`: `SeedAuditResult` extended; `audit_layout_seed()` library-first
- `ui/track_model_alignment_vm.py`: `format_alignment_summary()` returns `"seed_source"` key
- `ui/dashboard.py`: "Seed source" row; `_tm_refresh_alignment_panel()` uses library resolver
- `tests/test_group17u_track_library_schema.py` (NEW): 83 tests
- `docs/TRACK_LIBRARY_SCHEMA.md` (NEW): Full schema reference

**Schema versions introduced in 17U:**
- `track_library_index_v1`, `track_metadata_v1`, `track_layout_manifest_v1`
- `track_semantic_model_v1`, `validation_rules_v1`, `source_manifest_v1`

**Next step to create Daytona seed geometry:**
1. Run accepted calibration laps in GT7 and export telemetry x/y per station.
2. Create `geometry.seed_map.json` using `export_seed_coordinate_map_json()` from `data/track_seed_coordinate_map.py`.
3. Place file in `data/track_library/tracks/daytona_international_speedway/layouts/daytona_international_speedway__road_course/geometry.seed_map.json`.
4. Set `"seed_geometry": true` in `manifest.json` availability.

## Group 17T — Session Notes (2026-06-26)

**Problem solved:** After Group 17S, runtime UAT showed the modelled lap (5393 m) vs seed (5729 m) delta was correctly blocked, but the app had no way to explain WHY the map was short or verify coordinate geometry. Accept was blocked correctly, but the user had no coordinate-level evidence.

**What was added / fixed:**

- **DEF-17T-001 (Seed centreline/coordinate map unavailable blocks true matching):**
  New `data/track_seed_coordinate_map.py` — `SeedMapStation`, `SeedCoordinateMap` dataclasses, `find_seed_coordinate_map_path()`, `load_seed_coordinate_map()`, `export_seed_coordinate_map_json()`, `import_seed_coordinate_map_json()`, `resample_seed_map()`. File convention: `data/track_seed_maps/<track_id>__<layout_id>.seed_map.json`. `audit_layout_seed()` updated to accept `track_location_id` and `layout_id_str` and check for seed coordinate map file, setting `has_seed_centreline` and `centreline_point_count` accordingly.

- **DEF-17T-002 (Compare seed map vs modelled telemetry map):**
  New `data/track_map_geometry_alignment.py` — `MapMismatchRange`, `CornerCoordinateMatch`, `SectorCoordinateMatch`, `CoordinateTransform`, `TrackMapGeometryAlignmentResult` dataclasses. `align_maps_geometry(station_map, seed_map, seed_layout)` main entry point. Falls back to length-only when seed map absent. Reports `has_coordinate_comparison`, `mean_coord_error_m`, `max_coord_error_m`, `missing_section_ranges`, `corner_matches`, `sector_matches`, `coordinate_transform`, `blockers`, `warnings`.

- **DEF-17T-003 (Detect and explain missing track sections):**
  `_detect_missing_sections()` in `track_map_geometry_alignment.py`: when coordinates exist, scans for large inter-station jumps (> 10× expected step). Fallback: assumes missing section is at lap boundary (estimated start %–100%). Blocker text includes "Rebuild from complete clean laps crossing S/F line."

- **DEF-17T-004 (Stop using 200-point reference path for serious alignment):**
  `align_maps_geometry()` reads `station_map.stations` directly (full-resolution, 1 m spacing). `model_stations_count` in result reports the full count. Result is independent of any 200-pt reference path.

- **DEF-17T-005 (Handle coordinate transform between seed map and GT7 telemetry map):**
  `estimate_coordinate_transform()`: centroid alignment → translation; RMS-radius ratio → scale; rotation scan (15° coarse + 1° fine) minimising mean nearest-neighbour error; returns `CoordinateTransform` with `quality` 0–1. `_apply_transform()` applies translation + rotation + scale. Scale mismatch > 5% → warning.

- **DEF-17T-006 (Corner and sector matching use coordinate/progress truth):**
  `_match_corners()` uses seed map `has_corner_markers` station `corner_id` fields, matched to model corners by progress proximity (± 3% threshold). `_match_sectors()` reads `has_sector_markers` station `sector_id` fields. Progress-window fallback (Group 17S) remains active when no seed coordinate map.

- **DEF-17T-007 (UI overlay must show seed vs modelled map):**
  `TrackMapDrawData.seed_centreline: List[MapPoint]` added (defaulted field). `build_track_map_draw_data()` accepts optional `seed_coordinate_map` parameter and populates `seed_centreline` from `SeedCoordinateMap.stations` using `(x, y)` coordinates. `project_to_screen()` projects `seed_centreline`. `seed_overlay_note` cleared when seed map is present.

- **DEF-17T-008 (Recalibration must guide user toward fixing full-lap mismatch):**
  `_tm_rebuild_model()` dialog updated: now lists 4 explicit steps including "Start Calibration mode before leaving pits", "Drive 2–3 full clean laps crossing S/F line", "Avoid pit-lane entries and lap-start offsets", and a note about checking correct layout selection.

**New schema (Group 17T):**
- `SeedMapStation`: station_m, progress_pct, x, y, z, width_left_m, width_right_m, corner_id, sector_id
- `SeedCoordinateMap`: track_location_id, layout_id, source, confidence, lap_length_m, start_finish_station_m, stations, has_z_coordinates, has_corner_markers, has_sector_markers, has_width_corridor, notes
- `MapMismatchRange`, `CornerCoordinateMatch`, `SectorCoordinateMatch`, `CoordinateTransform`, `TrackMapGeometryAlignmentResult`
- File convention: `data/track_seed_maps/<track_id>__<layout_id>.seed_map.json`, schema: `seed_coordinate_map_v1`

**Daytona status:** No seed coordinate map file exists yet. Daytona full geometry match remains blocked. To enable: create `data/track_seed_maps/daytona_international_speedway__daytona_international_speedway__road_course.seed_map.json` with GT7 coordinate data from accepted telemetry runs.

**New test file:** `tests/test_group17t_seed_coordinate_map.py` — 55 tests covering all 8 defects.

**Files modified:**
- `data/track_seed_coordinate_map.py` (NEW): SeedCoordinateMap model, file I/O, resample
- `data/track_map_geometry_alignment.py` (NEW): geometry alignment engine, transform estimator
- `data/track_seed_maps/` (NEW directory): empty, awaiting seed map files
- `data/track_intelligence.py`: `audit_layout_seed()` now accepts track/layout IDs, checks for seed coordinate map file, sets `has_seed_centreline` + `centreline_point_count`
- `ui/track_map_vm.py`: `TrackMapDrawData.seed_centreline` field (defaulted); `build_track_map_draw_data()` accepts `seed_coordinate_map`; `project_to_screen()` projects seed_centreline
- `ui/track_model_alignment_vm.py`: `format_geometry_alignment_summary()`; `format_alignment_summary()` accepts `geo_result` + returns `"geometry_match"` key
- `ui/dashboard.py`: "Geometry match" alignment panel row; `_tm_refresh_alignment_panel()` computes geometry result via `align_maps_geometry()`; recalibration dialog with 4-step guidance
- `tests/test_group17t_seed_coordinate_map.py`: 55 new tests

## Group 17S — Session Notes (2026-06-26)

**Problem solved:** Six runtime defects observed after Group 17R UAT. The Daytona seed had no corner windows, sectors, or complex definitions — the alignment system was operating entirely on curvature peaks and integer counts. Turn assignment was wrong (Straight 0–7.3% assigned T2). Lap delta 5.1% was only a warning, not a blocker.

**What was added / fixed:**

- **DEF-17S-001 (Daytona seed lacks corner window truth):**
  Added 12 corner definitions (T1–T12) to Daytona Road Course in `track_modelling_seed.yaml`. All source: "estimated", confidence: "low". T1 apex at 8.2% confirmed from UAT telemetry. Other windows approximated from track layout knowledge.

- **DEF-17S-002 (Corner complexes not represented):**
  Added `CornerComplexDefinition` dataclass to `data/track_intelligence.py`. Added `corner_complexes` field to `TrackLayoutSeed`. Daytona has 2 complexes: BusStop (T1+T2) and T10T11 (T10+T11, coaching name "Horseshoe"). `_parse_complex_def()` parses from YAML.

- **DEF-17S-003 (Lap delta 5.1% must be a blocker):**
  In `data/track_model_alignment.py`, the `delta_pct > _MAX_LAP_DELTA_GOOD_PCT` branch is now a BLOCKER (not a warning). Daytona's 5.1% delta will now appear in the Blockers row with an explicit explanation of possible causes.

- **DEF-17S-004 (Turn assignment uses curvature rank, not seed windows):**
  `_tm_refresh_seg_table()` in `ui/dashboard.py` now resolves `SeedCornerDefinition` list for the selected layout. Segment midpoint is checked against each corner window: if it falls inside a window, that corner_id is assigned. A segment at 3.65% (pre-T1 straight) receives no assignment. A segment at 8.2% correctly receives T1. Falls back to nearest-station-map-corner proximity only when no seed windows are present.

- **DEF-17S-005 (Legacy warnings still leak after station map loads):**
  New `_tm_refresh_seg_diagnostics_labels()` method in `dashboard.py`. Called at end of `_tm_try_load_station_map_from_disk()` and `_tm_try_build_station_map()`. Re-filters "Corner count mismatch" and "corners vs expected" warnings and updates `_tm_lbl_seg_status`. The existing inline filter in `_tm_detect_segments_safe()` is still there as the first filter pass.

- **DEF-17S-006 (No seed audit diagnostics):**
  Added `SeedAuditResult` dataclass and `audit_layout_seed()` function to `data/track_intelligence.py`. Added `format_seed_audit_summary()` to `ui/track_model_alignment_vm.py`. `format_alignment_summary()` now accepts optional `layout_seed` and includes `"seed_audit"` key. New "Seed data available" row in alignment panel shows: lap length, N sectors, N corner windows, N complexes, centreline status.

- **New schema fields:**
  - `SeedSectorDefinition` dataclass (sector_id, display_name, start/end_progress_pct, source, confidence)
  - `CornerComplexDefinition` dataclass (complex_id, display_name, member_corner_ids, start/end_progress_pct, sector_id, coaching_name, notes, source, confidence)
  - `SeedAuditResult` dataclass (all availability flags + counts + max_match_status)
  - `TrackLayoutSeed.sector_definitions: list[SeedSectorDefinition]`
  - `TrackLayoutSeed.corner_complexes: list[CornerComplexDefinition]`

**New test file:** `tests/test_group17s_seed_definition_authoring.py` — 36 tests covering all defects.

**Files modified:**
- `data/track_intelligence.py`: 3 new dataclasses, 2 new parse helpers, audit_layout_seed(), updated _parse_layout(), updated TrackLayoutSeed
- `docs/track_modelling_seed/track_modelling_seed.yaml`: Daytona Road Course enriched with corners:, sector_definitions:, corner_complexes:
- `data/track_model_alignment.py`: lap delta > 5% is now a blocker, not a warning
- `ui/track_model_alignment_vm.py`: format_seed_audit_summary(), format_alignment_summary() has optional layout_seed param + seed_audit key
- `ui/dashboard.py`: "Seed data available" alignment row, _tm_refresh_alignment_panel() passes layout_seed, seed-window-based turn assignment in _tm_refresh_seg_table(), _tm_refresh_seg_diagnostics_labels() method
- `tests/test_group17s_seed_definition_authoring.py`: 36 new tests

## Group 17R — Session Notes (2026-06-26)

**Problem solved:** Six runtime defects observed during Daytona Road Course UAT after Group 17Q.

**What was added / fixed:**

- **DEF-17R-001 (Corner labels are curvature peaks, not verified positions):**
  `format_alignment_summary()` in `ui/track_model_alignment_vm.py` now returns explicit `seed_position_status` text: *"Unavailable — corner labels are curvature peaks, not verified positions"* when `seed_corner_positions_available=False`. Makes clear that T1-T12 labels in the current Daytona model are unverified curvature rankings, not positionally matched to the real Daytona corners.

- **DEF-17R-002 (No seed overlay note in TrackMapDrawData):**
  `build_track_map_draw_data()` in `ui/track_map_vm.py` now sets `seed_overlay_note` from `station_map.seed_corner_positions_available`. When unavailable: *"Seed centreline not available — showing telemetry-derived model only. Corner labels are curvature peaks, not verified seed positions."*. `project_to_screen()` passes the note through to the projected result.

- **DEF-17R-003 (Seed map source not explicit):**
  New `"seed_truth_source"` key in `format_alignment_summary()` and new "Seed truth source" row in the alignment panel. Shows either *"Metadata only — no coordinate or window data"* or *"Seed corner windows (N defs)"* depending on whether corner definitions are present in the seed YAML.

- **DEF-17R-004 (Old detection warnings leaking):**
  In `dashboard._tm_detect_segments_safe()`, "Corner count mismatch" and "corners vs expected" warnings from `detect_track_segments()` are now suppressed when a station map with seeded corners is authoritative. The old telemetry-based corner count is irrelevant when the station map owns the corner geometry.

- **DEF-17R-005 (Rebuild/Recalibrate button was a no-op):**
  `_tm_rebuild_model()` now: clears `self._tm_station_map = None`, clears `self._tm_alignment_result = None`, pushes empty draw data to both map widgets, resets the alignment panel to "Not built", and shows a dialog: *"Station map cleared. Start Calibration and drive clean laps to rebuild the track model."*. Updated button tooltip to explain what it does.

- **DEF-17R-006 (Lap offset not explained):**
  The `_off_note` QLabel in the Lap Offset Calibration group now explains: what lap offset calibration does, and what the three status states mean (Not loaded / Zero offset provisional / Calibrated).

**New test file:** `tests/test_group17r_seed_overlay_alignment.py` — 38 tests covering DEF-17R-001 through DEF-17R-006.

**Files modified:**
- `ui/track_model_alignment_vm.py`: `format_alignment_summary()` — new `seed_truth_source` key, updated `seed_position_status` text
- `ui/track_map_vm.py`: `build_track_map_draw_data()` — sets `seed_overlay_note`; `project_to_screen()` — passes note through
- `ui/dashboard.py`: new alignment panel row, `_tm_refresh_alignment_panel()` wiring, `_tm_rebuild_model()` fix, warning suppression in `_tm_detect_segments_safe()`, tooltip and lap offset note updates
- `tests/test_group17r_seed_overlay_alignment.py`: 38 new tests

## Group 17Q — Session Notes (2026-06-26)

**Problem solved:** Group 17P only capped corners at corners_expected=12. It chose the top-12 strongest curvature peaks without verifying they were at the correct Daytona T1–T12 positions. Accept Track Model could reach ACCEPTABLE_MATCH based on count alone.

**What was added:**
- `data/seed_corner_matching.py` (NEW): `CornerMatchStatus` enum, `CornerCandidateMatch` dataclass, `match_peaks_to_seed_windows()` greedy algorithm.
- `data/track_intelligence.py`: `SeedCornerDefinition` dataclass (per-corner progress window: corner_id, apex_progress_pct, start/end_progress_pct, direction, sector_id, source, confidence). `TrackLayoutSeed.corner_definitions` list field (empty by default — backward compatible). `_parse_corner_def()` + YAML `corners:` key support.
- `data/track_station_map.py`: `TrackStationMap.seed_corner_positions_available` bool field. `build_track_station_map()` branches: if `corner_definitions` present → calls `_find_curvature_peaks()` + `match_peaks_to_seed_windows()` to select official corners by window; else → existing top-N cap. JSON I/O updated.
- `data/track_model_alignment.py`: Four new fields on `TrackModelAlignmentResult`: `seed_corner_positions_available`, `corner_position_match`, `corners_matched`, `corner_candidate_matches`. `align_track_model()` now: (a) if seed has no corner defs → warns, marks all as SEED_POSITION_UNAVAILABLE, caps match status at GOOD_MATCH; (b) if seed has defs → checks each official corner against its expected window, computes PASS/PARTIAL/FAIL. ACCEPTABLE_MATCH only reachable when `corner_defs` present + no blockers + lap delta < 2%.
- `ui/track_model_alignment_vm.py`: `format_alignment_summary()` returns 4 new keys: `seed_position_status`, `corners_matched`, `corner_position_match`, `corner_position_color`.
- `ui/dashboard.py`: 3 new label rows in alignment panel (Seed corner positions, Corners matched, Corner pos match). Wired in `_tm_refresh_alignment_panel()`.
- `tests/test_group17q_seed_corner_matching.py`: 29 tests, all passing.

**Key acceptance rule change:** ACCEPTABLE_MATCH (and therefore Accept Track Model button enabled) now REQUIRES `corner_defs` in the layout seed. Without seed corner position data, the system is honest: max status = GOOD_MATCH, Accept disabled, UI says "Unavailable — count only".

## Source of Truth
- docs/PROJECT_STATE.md
- docs/MASTER_TESTING_REGISTER.md
- docs/AI_ENGINEERING_VALIDATION_REPORT.md, only when the scoped task requires it

## Architecture Boundaries
- Event Planner owns race/event settings.
- Garage owns cars.
- Setup Builder consumes Event + Car.
- Strategy Builder consumes Event + Car + Practice Data.
- History owns session loading.
- Live Race Engineer consumes Event + Strategy + Telemetry.

## Do Not Touch
- No unrelated refactors.
- No duplicate race/event/session state.
- No duplicate strategy fuel sources.
- No fake telemetry assumptions.
- No silent fallback logic that hides broken data flow.
- No broad UI rewrites unless explicitly scoped.

## Required Validation
- Update or add tests where practical.
- Update docs/MASTER_TESTING_REGISTER.md.
- Provide manual UAT steps.
- Confirm no unrelated behaviour changed.

## End Of Session Notes

### Session: Group 17P — Seed-to-Telemetry Track Model Alignment (2026-06-25)

**Root cause fixed (DEF-17P-UAT-001/005):** `_detect_corners()` in `data/track_station_map.py` kept ALL curvature peaks above threshold without capping at `corners_expected`. Daytona with 36 curvature peaks and `corners_expected=12` would create T1-T36 as official corners. Fixed by: when `detected > corners_expected`, take the top N by curvature magnitude; excess peaks stored as `extra_curvature_peaks` with XP1..XPn IDs (never official turns).

**New modules:**
- `data/track_model_alignment.py` — `TrackModelAlignmentResult`, `align_track_model()`, accepted model JSON persistence
- `ui/track_model_alignment_vm.py` — `format_alignment_summary()`, `get_acceptance_button_states()`, `format_mismatch_reasons()`

**`data/track_station_map.py` changes:**
- `_detect_corners()` returns `(official, extras)` tuple; caps to `corners_expected` when detected > expected
- `TrackStationMap` gains `extra_curvature_peaks: List[SeededCorner]` field
- JSON export/import updated to include `extra_curvature_peaks`

**`ui/track_map_vm.py` changes:**
- `TrackMapDrawData` gains `seed_overlay_note: str` (shown when seed centreline unavailable)

**`ui/dashboard.py` changes:**
- Segment Review renamed → Segment Diagnostics; 6 per-segment manual-approval buttons hidden (attrs preserved to avoid AttributeError in legacy handler methods)
- Review Approval panel replaced → Track Model Alignment panel with alignment metrics, Accept Track Model button (green, disabled until ACCEPTABLE_MATCH), Rebuild/Recalibrate button
- New methods: `_tm_run_alignment()`, `_tm_refresh_alignment_panel()`, `_tm_accept_track_model()`, `_tm_rebuild_model()`, `_tm_try_load_accepted_model()`
- `_tm_on_layout_changed()`: now calls `_tm_try_load_accepted_model()` in addition to station map load
- `_tm_try_build_station_map()`: calls `_tm_run_alignment()` after every successful build
- `_tm_try_load_station_map_from_disk()`: calls `_tm_run_alignment()` after loading

**New imports in `ui/dashboard.py`:**
- `data.track_model_alignment`: `align_track_model`, `export_accepted_model_json`, `find_accepted_model_path`, `import_accepted_model_json`
- `ui.track_model_alignment_vm`: `format_alignment_summary`, `get_acceptance_button_states`, `format_mismatch_reasons`

**New test file:** `tests/test_group17p_alignment.py` — 34 tests covering all 6 DEFs

**Test result: 2088 pass / 5 skip / 0 fail** (+34 vs Group 17O Round 2)

---

### Session: Group 17O UAT Remediation Round 2 — DEF-17O-UAT-004 through 008 (2026-06-25)

**Root cause fixed (CRITICAL):** `_tm_try_build_station_map()` at line 2770 iterated `self._tm_seed_result.layouts` — `TrackSeedLoadResult` has `.track_locations` not `.layouts`. This AttributeError was silently caught, causing the station map never to build, the track map never to display, and Daytona to show only 5 curvature-detected corners instead of the seeded 12.

**`ui/dashboard.py` changes:**
- `_tm_try_build_station_map()`: replaced broken `for layout in self._tm_seed_result.layouts:` with `get_selected_layout(self._tm_seed_result, loc_id, lay_id)` (already imported); also reads `loc_id` from location combo (was missing); after build, calls `_export_station_map()` to persist JSON; updates `_tm_lbl_build_info` to show `"Path: N pts | Conf: X | Map: N stations / N corners"`
- `_tm_on_layout_changed()`: calls `_tm_try_load_station_map_from_disk(loc_id, lay_id)` — new method that loads saved station map JSON when layout is selected, populating both map widgets immediately
- `_tm_refresh_seg_table()`: matches each segment's `lap_progress_mid` to nearest `SeededCorner` (< 15% threshold) to populate Turn column for non-apex segments
- `_TELEMETRY_OVERLAY_SEG_TYPES`: added `BRAKING_ZONE` and `TRACTION_ZONE` — both tagged with Porsche RSR car-specific warnings, not universal track geometry
- New imports: `export_station_map_json`, `import_station_map_json`, `find_station_map_path` from `data.track_station_map`

**`tests/test_group17o_uat_defects.py` changes:**
- 40 tests total (was 23); added `TestDef17OUAT004StationMapCountDisplay` (3), `TestDef17OUAT005SeedLookupFix` (5), `TestDef17OUAT007MapDisplayFix` (2), `TestDef17OUAT008StationMapPersistence` (6)
- Updated `TestDef17OUAT002OverlayFiltering`: added `test_braking_and_traction_zones_are_overlay`; updated `test_geometry_types_not_in_overlay_set` (removed BRAKING/TRACTION from geometry list); updated `test_review_segment_filtering_preserves_geometry` (uses APEX_ZONE as geometry proxy)

**Test result: 2054 pass / 5 skip / 0 fail**

---

### Session: Group 17M — Runtime UAT and Calibration Workflow Hardening (2026-06-24)

**New module:** `data/track_modelling_runtime_check.py` (pure Python, no PyQt6)

**New doc:** `docs/TRACK_MODELLING_RUNTIME_UAT.md` — 15-section manual UAT checklist

**`ui/track_modelling_vm.py` additions (all pure Python, testable without QApplication):**
- `_WORKFLOW_ERROR_MESSAGES` — 11-key error string dict
- `get_workflow_error_message(error_key)` — safe lookup with unknown-key fallback
- `get_calibration_button_states(ctrl_state, has_track, has_completed_laps, has_ref_path, has_review_model, selected_segment_id=None, has_track_length=False)` → 15-key bool dict
- `format_calibration_status_extended(status_summary, last_packet_age_s=None)` → 7-key dict
- `format_lap_offset_status(offset_calibration=None, track_length_m=None)` → 7-key dict
- `format_live_resolver_status_summary(loc_id, lay_id, ...)` → newline-separated string

**`data/track_modelling_runtime_check.py`:**
- `RuntimeCheckResult` — 14-field dataclass with `summary_text()` → compact display string
- `run_track_modelling_runtime_check()` — never raises; duck-typed; aggregates resolver/offset/live_position/live_segment

**`data/lap_distance_mapper.py` change:**
- `create_offset_zero()` default `source` changed from `"manual"` to `"zero_offset"` to match spec; `ValueError` raised on non-positive `track_length_m`

**`ui/dashboard.py` additions:**
- `_tm_lbl_packet_age` label with green/amber/red colour feedback
- `_tm_last_packet_time: Optional[float]` and `_tm_offset_calibration` instance vars
- Lap Offset Calibration QGroupBox with Create Zero Offset / Load Offset / Save Offset buttons and status/detail/warning labels
- `_tm_get_track_length_m()`, `_tm_update_packet_age_label()`, `_tm_update_offset_status()`
- `_tm_create_zero_offset()`, `_tm_load_offset()`, `_tm_save_offset()` handlers
- `_tm_update_cal_buttons()` extended for offset buttons (create_zero = needs track+length; load = needs track; save = needs offset)
- Signal connections in `_connect_signals()` for the three new offset buttons

**Button state rules implemented:**
- `create_zero_offset`: has_track AND has_track_length
- `load_offset`: has_track
- `save_offset`: has_offset_calibration

**Provisional vs validated offset:**
- Provisional: source == "zero_offset" OR confidence in (low, unknown)
- Validated: confidence in (high, medium) AND source != "zero_offset"

**Files changed:**
- `data/track_modelling_runtime_check.py` — new file
- `ui/track_modelling_vm.py` — 5 new functions appended after `get_review_button_states()`
- `data/lap_distance_mapper.py` — `create_offset_zero()` updated
- `ui/dashboard.py` — packet age label, offset group, new methods, signal connections
- `tests/test_group17m_runtime_hardening.py` — 94 new tests (all pass)
- `docs/TRACK_MODELLING_RUNTIME_UAT.md` — new file
- `docs/PROJECT_STATE.md` — build stats updated; Group 17M row added
- `MASTER_TESTING_REGISTER.md` — Group 17M section added
- `docs/TRACK_INTELLIGENCE_STARTER_MODEL.md` — Group 17M section added
- `docs/CURRENT_CLAUDE_HANDOFF.md` — this file updated

**Tests run:**
- `tests/test_group17m_runtime_hardening.py`: 94/94 pass
- Full suite: 1815 pass / 5 skip / 0 fail (1820 collected)

---

### Session: Group 17M UAT Defect Remediation (2026-06-25)

**Defects fixed:**

**DEF-17M-UAT-001 — Lap Count Mismatch Display**
- Root cause: `lap_count = len(session.laps)` counts ALL closed segments; quality data only available after Build
- Fix: `format_lap_count_info(status_summary) -> dict` added to `track_modelling_vm.py` — returns `captured_text`, `quality_text`, `explanation`; `_tm_update_cal_status()` uses it; tooltip shows explanation when gap exists

**DEF-17M-UAT-002 — Detect Segments Crash**
- Root cause: `seed_result.layouts` (line 2607) — `TrackSeedLoadResult` has no `.layouts` attribute; `AttributeError` in Qt slot crashes app
- Fix: `_tm_detect_segments()` split into outer try/except catcher + `_tm_detect_segments_safe()` inner; crash shows QMessageBox.critical; `seed_result.layouts` replaced with `get_selected_layout(seed_result, loc_id, lay_id)`

**DEF-17M-UAT-003 — Saved File Not Discoverable After Restart**
- Root cause: `ctrl._saved_path` is None after restart (new controller); UI never audited disk
- Fix: `audit_track_model_files(loc_id, lay_id, search_dir=None) -> TrackModelFileAudit` added to `track_calibration.py`; `_tm_on_layout_changed()` calls `_tm_audit_and_show_saved_files()`; `TrackModelFileAudit` dataclass + `reference_path_filename()` + `format_file_audit_status()` vm helper

**Files changed (UAT remediation):**
- `data/track_calibration.py` — `reference_path_filename()`, `TrackModelFileAudit` dataclass, `audit_track_model_files()` appended
- `ui/track_modelling_vm.py` — `format_lap_count_info()`, `format_file_audit_status()` appended
- `ui/dashboard.py` — new imports, `_tm_update_cal_status()` updated, `_tm_detect_segments()` refactored + `_tm_detect_segments_safe()` added, `_tm_on_layout_changed()` updated, `_tm_audit_and_show_saved_files()` added
- `tests/test_group17m_uat_defects.py` — new file, 49 tests (all pass)
- `docs/TRACK_MODELLING_RUNTIME_UAT.md` — UAT Defect Register section appended
- `docs/PROJECT_STATE.md` — build stats + Group 17M UAT row added
- `MASTER_TESTING_REGISTER.md` — Group 17M UAT Remediation section added

**Tests run:**
- `tests/test_group17m_uat_defects.py`: 49/49 pass
- Full suite: 1864 pass / 5 skip / 0 fail (1869 collected)

---

### Session: Group 17N UAT Defect Remediation (2026-06-25)

**Defect fixed:**

**DEF-17N-UAT-004 — Detect Segments Requires Live Session Despite Saved Reference Path**
- Root cause: `detect_track_segments()` needs raw `CalibrationLap.samples` (per-sample TelemetrySample arrays). `save_reference_path()` only saved the 200-point aggregated ReferencePath JSON — raw lap data was discarded on every restart.
- Fix: Three-layer change:
  1. **`data/track_calibration.py`** — Added `calibration_laps_filename()`, `export_calibration_laps_json()` (USABLE laps + all TelemetrySample fields serialised), `import_calibration_laps_json()` (reconstructs CalibrationSession from disk). Extended `TrackModelFileAudit` with `calibration_laps_exists`, `calibration_laps_usable_count`, `can_detect_segments` property (True when both files present and loadable), `is_legacy_ref_path_only` property (True when ref path exists but no laps file). `audit_track_model_files()` now checks for laps file. `summary_line()` includes laps count.
  2. **`data/track_calibration_runtime.py`** — `save_reference_path()` now writes BOTH files per save: `<loc>__<lay>.reference_path.json` and `<loc>__<lay>.calibration_laps.json`. Laps write is best-effort (ref path save succeeds independently).
  3. **`ui/dashboard.py`** — `_tm_detect_segments_safe()` rewritten with three-path logic: (A) active session with usable laps → run immediately; (B) laps file found on disk → load via `import_calibration_laps_json()`, reconstruct CalibrationSession, run detection; (C) legacy ref path only → informational dialog explaining pre-17N format and what to do. `_tm_audit_and_show_saved_files()` updated: Detect Segments enabled when `ctrl_has_ref OR disk_can_detect OR disk_legacy`; save-path label includes laps count.
  4. **`ui/track_modelling_vm.py`** — `format_file_audit_status()` updated: `detail_text` includes `"{N} laps persisted"` when laps file present, or `"no lap data saved"` for legacy. `load_status` distinguishes "Detect Segments ready — lap data available from disk" vs "Pre-17N format — re-run calibration once".

**Files changed:**
- `data/track_calibration.py` — calibration_laps_filename, export/import_calibration_laps_json, TrackModelFileAudit extensions, audit + summary_line updated
- `data/track_calibration_runtime.py` — save_reference_path() writes both files
- `ui/dashboard.py` — _tm_detect_segments_safe() three-path logic, _tm_audit_and_show_saved_files() laps-aware
- `ui/track_modelling_vm.py` — format_file_audit_status() laps-aware
- `tests/test_group17m_uat_defects.py` — test_file_found_load_ok_saved_text updated; test_file_found_legacy_no_laps_shows_preformat_message added
- `tests/test_group17n_uat_defects.py` — new file, 41 tests (all pass)
- `docs/TRACK_MODELLING_RUNTIME_UAT.md` — DEF-17N-UAT-004 appended to defect register
- `docs/PROJECT_STATE.md` — build stats + Group 17N UAT row added
- `MASTER_TESTING_REGISTER.md` — Group 17N UAT Remediation section added, header updated

**Saved file format:** `<loc>__<lay>.calibration_laps.json` alongside `<loc>__<lay>.reference_path.json`
**Legacy path:** is_legacy_ref_path_only=True → informational dialog; user must run one new calibration session and re-save.

**Tests run:**
- `tests/test_group17n_uat_defects.py`: 41/41 pass
- Full suite: 1906 pass / 5 skip / 0 fail (1911 collected)

---

### Session: Group 17N UAT-005 Defect Remediation (2026-06-25)

**Defect fixed:**

**DEF-17N-UAT-005 — No Usable Calibration Laps Message Lacks Actionable Diagnostics**
- Root cause 1: `CalibrationLap.quality` defaults to `REJECTED` and `build_reference_path()` never wrote quality assessment results back to the lap objects. `detect_track_segments()` filtered by `quality == USABLE` → found none → generic error even after a successful Build.
- Root cause 2: `_tm_build_path()` only showed `result.errors`, discarding per-lap rejection reasons in `result.warnings`.
- Fix:
  1. **`data/track_calibration.py`** — `build_reference_path()` now mutates `CalibrationLap.quality` and `quality_reasons` immediately after `assess_session_laps()` runs (both success and failure paths). Added `diagnose_calibration_session(session) -> dict` — structured diagnostic snapshot with `total_laps`, `usable/rejected/low_confidence_count`, `total_samples`, `per_lap` list, `all_reasons`, `most_common_reason`, `car_id`, `has_any_laps`. Never raises.
  2. **`data/track_segment_detection.py`** — Added `assess_session_laps` to import. Added `_build_no_usable_laps_errors(session) -> list[str]` helper that re-assesses quality and returns per-lap diagnostic lines + context-specific recommended action. `detect_track_segments()` calls this instead of the hardcoded "record more laps with the Porsche 911 RSR".
  3. **`ui/track_modelling_vm.py`** — Added `format_build_failure_diagnostics(result, session=None) -> str` — multi-line dialog string with primary error, lap quality counts (usable/rejected/low-conf), per-lap reasons from `result.warnings`, car ID, and a context-specific recommended action (too-few-samples → UDP advice; zero-xyz → on-track advice; off-track → 30% limit explanation; outlier → consistent laps advice). Added `_min_samples()` helper.
  4. **`ui/dashboard.py`** — Added `format_build_failure_diagnostics as _format_build_diag` to import. `_tm_build_path()` now calls `_format_build_diag(result, session)` instead of generic `"\n".join(result.errors)`.

**Files changed:**
- `data/track_calibration.py` — quality mutation in build_reference_path, diagnose_calibration_session added
- `data/track_segment_detection.py` — assess_session_laps import, _build_no_usable_laps_errors helper
- `ui/track_modelling_vm.py` — format_build_failure_diagnostics, _min_samples added
- `ui/dashboard.py` — _format_build_diag import, _tm_build_path updated
- `tests/test_group17n_uat_defects.py` — test_daytona_ref_path_is_legacy_until_resaved updated for three-way state
- `tests/test_group17n_uat005_defects.py` — new file, 32 tests (all pass)
- `docs/TRACK_MODELLING_RUNTIME_UAT.md` — DEF-17N-UAT-005 appended
- `docs/PROJECT_STATE.md` — build stats + Group 17N UAT-005 row added
- `MASTER_TESTING_REGISTER.md` — Group 17N UAT-005 section added, header updated

**Post-fix behavior:**
- Build success: all session laps now have `quality = USABLE`; Detect Segments immediately works on active session.
- Build failure: dialog shows "Lap 1 rejected: Too few telemetry samples (10 < 50)" style detail plus recommended action.
- Detect with no usable laps: error includes lap counts, per-lap rejection reasons, car ID, and action (e.g., "Confirm GT7 Custom UDP Output is enabled").

**Tests run:**
- `tests/test_group17n_uat005_defects.py`: 32/32 pass
- Full suite: 1938 pass / 5 skip / 0 fail (1943 collected)

---

### Session: Group 17O — Seeded 1m Track Map, Width Corridor, Map Matching, and Visual Verification (2026-06-25)

**Root cause of old segment weirdness:** Group 17E segment detection used telemetry behaviour (speed minima, brake, throttle, gear, RPM) to detect track anatomy. This produced non-geometry items (limiter approaches, kerb candidates, gear zones, fuel-saving candidates) instead of true corner boundaries.

**New three-layer architecture:**
- Layer 1 — Track Model: stable circuit truth from X/Y/Z geometry only. No brake/gear/throttle.
- Layer 2 — Driver Reference Path: car-specific driving line (existing ReferencePath)
- Layer 3 — Telemetry Overlay: behaviour events attached to known stations (NOT geometry)

**New files:**

`data/track_station_map.py`:
- `StationPoint` — one station (station_m, progress_pct, x, y, z, heading_rad, curvature, gradient, widths, corner_id, corner_phase, confidence)
- `SeededCorner` — T1..Tn from seed + placeholder filling
- `TrackStationMap` — container with `station_count()`, `get_station_at()`
- `resample_path_to_uniform_spacing(xyz_points, spacing_m=1.0)` — arc-length resampling
- `build_track_station_map(ref_path, layout_seed, spacing_m=1.0)` — main builder
- Corner detection: `_find_curvature_peaks()` iterative peak suppression + placeholder filling for `corners_expected` guarantee
- `export_station_map_json()` / `import_station_map_json()` — JSON I/O (schema `track_station_map_v1`)

`data/track_map_matching.py`:
- `MapMatchConfidence` — HIGH (≤5m), MEDIUM (≤20m), LOW (≤60m), UNKNOWN (>60m)
- `MapMatchResult` — station_m, progress_pct, lateral_offset_m, edge distances, confidence, is_pit_likely
- `find_nearest_station_idx()`, `match_position_to_map()`, `is_likely_outlap()`, `map_match_samples()`
- Pit detection: speed < 8 kph OR dist > 60m from centreline → `is_pit_likely=True`

`data/track_width_model.py`:
- `WidthObservation`, `WidthEstimate` dataclasses
- `collect_lateral_offsets()`, `build_width_estimates()`, `apply_width_estimates_to_map()`
- `is_near_left_edge()`, `is_near_right_edge()`, `unused_track_width_pct()`

`ui/track_map_vm.py` (pure Python, NO PyQt6):
- `MapPoint`, `CornerLabel`, `CarDot`, `TrackMapDrawData` dataclasses
- `build_track_map_draw_data(station_map, match_result, telemetry_trace)` — world-space primitives
- `project_to_screen(draw_data, canvas_w, canvas_h, margin)` — pixel projection with Y-flip

**Dashboard changes (`ui/dashboard.py`):**
- `TrackMapWidget(QWidget)` — new QPainter-based canvas class before MainWindow
- Track Modelling tab: "Station Map" QGroupBox with `TrackMapWidget` (min height 300px) added after Calibration Session group
- Live tab: logo replaced with `self._live_map_widget = TrackMapWidget()` in mid_row
- `_tm_try_build_station_map()` — builds station map from ref path after successful Build Reference Path, updates both map widgets
- `_tm_update_live_map_dot(packet)` — called from `_tm_on_calibration_packet()`, matches packet XYZ to station map and refreshes both widgets
- New state: `self._tm_station_map = None` (Group 17O)

**Tests:** `tests/test_group17o_track_station_map.py` — 76 tests across 14 categories (all pass):
1. Creating 1m station model from reference data
2. Resampling path to 1m stations
3. Mapping X/Y/Z to nearest station
4. Calculating station_m and progress_pct
5. Calculating lateral_offset_m
6. Calculating left/right edge distance
7. Handling missing/unknown width safely
8. Ignoring pit/out-lap fragments
9. Keeping seeded 12-corner Daytona structure
10. Separating telemetry overlays from track geometry
11. Producing drawing primitives without PyQt
12. Producing live car-dot from mapped telemetry
13. Low-confidence map matching state
14. Legacy low-resolution (200-point) reference path handling

**Files changed:**
- `data/track_station_map.py` — new file
- `data/track_map_matching.py` — new file
- `data/track_width_model.py` — new file
- `ui/track_map_vm.py` — new file
- `ui/dashboard.py` — TrackMapWidget class, map widget on both tabs, _tm_try_build_station_map, _tm_update_live_map_dot, new imports
- `tests/test_group17o_track_station_map.py` — new file, 76 tests

**Tests run:**
- `tests/test_group17o_track_station_map.py`: 76/76 pass
- Full suite: 2014 pass / 5 skip / 0 fail (2019 collected)

---

### Session: Group 17L — Lap-Start Offset Calibration and Road-Distance Mapping (2026-06-24)

**New module:** `data/lap_distance_mapper.py` (pure Python, no PyQt6)

**Enums:** `LapDistanceMappingStatus` (6 values: mapped / mapped_with_wrap / no_distance_data / no_track_length / invalid_offset / error), `LapDistanceMappingConfidence` (high / medium / low / unknown)

**Dataclasses:** `LapStartOffsetCalibration` (stores offset between GT7 road_distance and model distance_along_lap_m; JSON-persistable to `data/track_models/<loc>__<lay>__lap_offset.json`), `LapDistanceMappingResult` (full error-status return from any mapping call), `LapDistanceMapperConfig` (min_track_length_m=100, clamp_progress=True)

**Core conversion formula:** `model_distance = (road_distance - offset_m) % track_length_m`
  - `offset_m = normalise_distance(gt7_start_distance_m - model_start_distance_m, track_length_m)`
  - `normalise_distance` uses Python modulo (handles negatives safely)
  - Wrap-around detection: `raw < 0 or raw >= track_length_m` → status = MAPPED_WITH_WRAP + warning

**Functions:** `normalise_distance()`, `calculate_lap_start_offset()`, `map_road_distance_to_lap_distance()`, `map_road_distance_to_lap_progress()`, `create_offset_zero()`, `create_offset_from_reference_path()`, `export_offset_calibration_json()`, `import_offset_calibration_json()`, `load_offset_calibration_for_track()`

**`data/live_segment_resolver.py` updates:**
- `LivePosition.road_distance_m: Optional[float] = None` — raw GT7 field (populated, not converted)
- `packet_to_live_position()` — populates `road_distance_m` from `packet.road_distance`; `distance_along_lap_m` still NOT set (requires calibration)
- `enrich_position_with_road_distance(position, offset_calibration) -> LivePosition` — standalone helper; returns new instance with `distance_along_lap_m` set; no-op on missing data
- `resolve_live_segment(…, offset_calibration=None)` — new Priority 3: road_distance_m + calibration → distance_along_lap_m; confidence downgraded when calibration is LOW/UNKNOWN

**Matching priority (updated):** segment_id → lap_progress → road_distance+offset → distance_along_lap_m → XYZ nearest → nearest midpoint → unresolved

**Explicitly deferred:** track auto-detection, PTT marker capture, voice announcements, lap progress from weak evidence only, seed-only as trusted coaching truth, Porsche calibration as universal truth, live engineer rewrite

**69 tests, all passing.** Full suite: 1721 pass / 5 skip / 0 fail.

---

### Session: Group 17K — Segment-Aware Live Coaching Rules (2026-06-24)

**New module:** `data/live_segment_coaching.py` (pure Python, no PyQt6)

**Enums:** `LiveCoachingCueType` (13 incl. no_call), `LiveCoachingPriority` (low/medium/high/urgent), `LiveCoachingSuppressionReason` (12 values)

**Dataclasses:** `LiveCoachingCue` (cue_type, priority, text, basis fields, repetition count, lap/progress context), `LiveCoachingDecision` (suppressed, cue, suppression_reason, all_candidates, debug_info), `LiveCoachingConfig` (9 tuneable fields; fuel-save and tyre-management cues opt-in disabled by default)

**Core function:** `build_live_coaching_decision(live_segment_result, enriched_issues, current_sample, config, previous_cues, current_lap, current_progress) -> LiveCoachingDecision`

**Gate sequence:** seed_only → rejected_segment → needs_more_laps → low_confidence → no issues → build candidates (filter by segment_id/type, count repetitions, apply rules) → sort by priority → cooldown → max_cues_per_lap → return cue

**25-entry cue template table:** covers brake_lock / wheelspin / oversteer / understeer / poor_exit_drive / wrong_gear / limiter_hit / fuel_saving_opportunity / tyre_wear_hotspot × relevant segment types with exact+fallback matching

**Helpers:** `format_live_coaching_for_prompt()` (returns "" when suppressed, block with basis when cue fires); `get_live_coaching_debug_metadata()` (4 debug fields); `_format_cue_text()` (inserts or gracefully removes {segment} placeholder without inventing names); `_downgrade_priority()`, `_cooldown_suppressed()`, `_confidence_is_usable()`

**`DrivingAdvisor` wiring:** `_get_live_coaching_context(live_position, laps) -> str`; injected into coaching prompt `extra_sections` after `live_segment_block`

**78 tests, 19 test classes** in `tests/test_group17k_live_segment_coaching.py`

**Deferred:** TTS/voice delivery, track auto-detection, multi-cue display, tyre management cues (noisy), fuel-save cues (require strategy context)

---

### Session: Group 17J — Live Current Segment Resolver (2026-06-24)

**New module:** `data/live_segment_resolver.py` (pure Python, no PyQt6)

**Enums:** `LiveSegmentResolutionConfidence` (HIGH/MEDIUM/LOW/UNKNOWN), `LiveSegmentResolutionStatus` (matched/matched_nearest/no_reviewed_model/no_position_data/no_segment_bounds/error)

**Dataclasses:** `LivePosition`, `LiveSegmentMatch`, `LiveSegmentResolverResult`, `LiveSegmentResolverConfig`

**Core function:** `resolve_live_segment(loc_id, lay_id, position, base_dir, config)` — never raises; matching priority: segment_id exact → lap_progress range → distance_along_lap_m via ref path → XYZ nearest via ref path → nearest midpoint → unresolved

**GT7 limitations (documented, not worked around):**
- No native lap_progress in packet — `packet_to_live_position()` never populates it
- `road_distance` is absolute (not lap-relative) — not used as `distance_along_lap_m`
- XYZ→reference path→lap_progress is the primary position path

**Adapters:** `packet_to_live_position(packet)` (duck-typed, guards paused/loading/off-track/zero-xyz, never raises); `format_live_segment_for_engineer(result)` (compact text, no invented names); `get_live_segment_context_for_prompt()` (AI block, "" for no_reviewed_model)

**`strategy/driving_advisor.py` changes:**
- `_get_live_segment_context(live_position=None) -> str` — new method; returns "" when no position or no IDs; never raises
- `_build_coaching_prompt()`, `_build_setup_prompt()`, `_build_combined_prompt()` — each gets optional `live_position=None` parameter; live_segment_block injected into `extra_sections` after track_intel_block

**Test file:** `tests/test_group17j_live_segment_resolver.py` — 78 tests, 17 test classes

**Full suite: 1574 pass / 5 skip / 0 fail**

**Deferred (documented in TRACK_INTELLIGENCE_STARTER_MODEL.md):**
- Lap-start distance offset calibration (for road_distance → distance_along_lap_m conversion)
- Voice position announcements using live resolver
- Track auto-detection from telemetry

---

### Session: Group 17H — Track Intelligence AI Prompt Integration (2026-06-24)

**New module:** `strategy/track_context_prompt.py` (pure Python, no PyQt6, no state)

**Public function:** `get_track_context_for_ai(track_location_id, layout_id) -> str`
- Missing/empty IDs: returns compact `"Track Intelligence unavailable: no selected track/layout was provided."` warning; never raises
- Present: delegates to `build_resolved_track_context_for_prompt()` from `data.track_model_resolver` (lazy import inside try block)
- Resolver exception: returns safe error note with exception class and message; never raises or propagates

**`strategy/ai_planner.py` changes:**
- `RaceParams.track_location_id: str = ""` and `RaceParams.layout_id: str = ""` — new optional dataclass fields
- `_build_race_prompt(track_context="")` — track context section injected before `## Practice lap times`
- `_build_practice_prompt(track_context="")` — same injection point
- `_build_setup_from_scratch_prompt(track_context="")` — section injected after race conditions block
- `build_car_setup(track_location_id="", layout_id="")` — calls `get_track_context_for_ai()`; passes to prompt builder; adds `track_context_included`, `track_location_id`, `layout_id` to `structured_payload`
- `analyse_strategy()` — resolves context from `params.track_location_id/layout_id`; payload updated; "Track Intelligence unavailable" added to `_warnings` when IDs missing
- `analyse_practice_session()` — same

**`strategy/driving_advisor.py` changes:**
- `DrivingAdvisor._get_track_intelligence_context()` — new method; reads `config["strategy"]["track_location_id"/"layout_id"]`; calls `get_track_context_for_ai()`; never raises
- `_build_coaching_prompt()` — `track_intel_block` prepended to `extra_sections`
- `_build_setup_prompt()` — same
- `_build_combined_prompt()` — same
- `_build_feeling_prompt()` — intentionally NOT updated (car-specific, not track-specific)

**`ui/dashboard.py` changes:**
- `_tm_on_layout_changed()` — stores `loc_id`/`lay_id` to `config["strategy"]["track_location_id"/"layout_id"]` when Track Modelling layout selected
- `_run_ai_analysis()` — passes `track_location_id`/`layout_id` from config into `RaceParams` dict
- `_run_practice_analysis()` — same; debug print updated with track context presence info
- `_run_build_setup()` — reads IDs from config; passes to `build_car_setup()`

**Source of truth for track/layout IDs:**
- Set when user selects location/layout in Track Modelling tab (NOT from event planner or telemetry)
- Stored in `config["strategy"]["track_location_id"]` / `["layout_id"]`
- If not set → all AI prompts receive "Track Intelligence unavailable" warning section

**Tests:** 56 new tests in `tests/test_group17h_track_context_prompt.py` — 16 test classes. Full suite: **1420/1425 green** (5 skipped unchanged).

**Key design decisions:**
- Thin helper module: zero state, zero PyQt6, zero direct model file parsing
- Resolver is the single boundary — `get_track_context_for_ai` never touches track model files directly
- Missing IDs → warning in every prompt (not a crash, not silent omission)
- Seed-only/not-AI-ready/missing each return their own distinct warning block (from resolver, unchanged)
- Porsche boundary note carried through from resolver on all contexts

**Deferred:**
- Live current-segment lookup
- Telemetry-to-segment issue enrichment
- Wiring `layout_id` from Event Planner (currently only Track Modelling tab selection)
- `_build_feeling_prompt` track context injection
- Track auto-detection from telemetry

**Recommended next task:** Group 17J — live current-segment lookup (which segment is the car currently in during practice/qualifying).

---

### Session: Group 17I — Telemetry Issue to Segment Enrichment (2026-06-24)

**New module:** `data/track_issue_enrichment.py` (pure Python, no PyQt6)

**Enums:** `TrackIssueType` (10 values), `TrackIssuePhase` (7 values), `TrackIssueEnrichmentConfidence` (4 values)

**Dataclasses:** `RawTelemetryIssue`, `EnrichedTelemetryIssue`, `TrackIssueEnrichmentResult`

**Core enrichment:** `enrich_telemetry_issues(raw_issues, loc_id, lay_id, base_dir) -> TrackIssueEnrichmentResult`
- Resolves reviewed track model via `resolve_best_track_model()`
- Loads reference path (`<loc>__<layout>.reference_path.json`) for XYZ→lap_progress conversion
- Matching priority: segment_id exact → lap_progress range → distance_along_lap_m → XYZ nearest → nearest midpoint → unresolved
- Never raises; all exceptions captured as result.warnings

**Confidence rules:**
- Engineer_validated/AI_ready model → HIGH base; reviewed → MEDIUM; seed_only → LOW; missing → UNRESOLVED
- REJECTED segment → UNRESOLVED; NEEDS_MORE_LAPS → LOW; UNREVIEWED → capped MEDIUM
- `nearest` match method → base confidence downgraded one level

**Implication mapping:** Deterministic dict keyed `(issue_type, segment_type)` covering:
- brake_lock+braking_zone → brake_bias, LSD braking, front damping; driver: brake release, trail braking
- wheelspin+corner_exit/traction → LSD accel, rear damping, rear ARB; driver: throttle pickup, short shift
- limiter_hit+straight/gear_zone → top gear ratio, final drive; driver: upshift timing
- poor_exit_drive+corner_exit → LSD accel, exit gear, rear grip; driver: apex speed, throttle timing
- oversteer+exit/apex → rear ARB soften, rear toe, rear downforce; driver: earlier throttle
- understeer+entry/apex → front springs/ARB, front downforce; driver: corner entry speed

**Adapters:**
- `issues_from_lap_stats(laps) -> list[RawTelemetryIssue]` — from lock_up/wheelspin/oversteer/snap_throttle/over_braking position lists
- `issues_from_corner_issues(corner_issues) -> list[RawTelemetryIssue]` — decodes `CornerIssue.corner_id` ("P500_-200") to approximate XYZ

**Prompt helper:** `summarise_enriched_issues_for_prompt(enriched_issues) -> str`
- Groups by (segment_display_name, issue_type)
- Lists unique lap numbers; limits to 8 per group with "… (N total)"
- Unresolved section: never invents corner names; includes "do not invent corner names" instruction

**`strategy/driving_advisor.py` changes:**
- `_get_enriched_issue_context(laps) -> str` — new method; reads track/layout IDs from config; calls enrichment pipeline; returns summary or ""; never raises
- `_build_coaching_prompt()`, `_build_setup_prompt()`, `_build_combined_prompt()` — include `enriched_issues_block or corner_issues_summary` in extra_sections (enriched takes precedence when non-empty)

**`strategy/ai_planner.py`:** No code changes needed — `corner_issues_summary` parameter already flows through all prompt builders.

**Tests:** 76 new tests in `tests/test_group17i_track_issue_enrichment.py` — 15 test classes. Full suite: **1496/1501 green** (5 skipped unchanged).

**Key design decisions:**
- Never invent corner names for unresolved issues
- Enriched block takes precedence over legacy `corner_issues_summary` when non-empty
- XYZ → lap_progress via reference path (not raw distance); falls back gracefully when path missing
- All matching is silent — no exceptions propagate to callers

**Deferred:**
- Live current-segment lookup
- Track auto-detection from telemetry
- PTT marker capture
- Graphical split/merge segment editing

---

### Session: Group 17G — Approved Track Model Resolver and Modelling Status Promotion (2026-06-24)

**New module:** `data/track_model_resolver.py` (pure Python, no PyQt6)

**Enums:** `TrackModelSourceType` (6), `TrackModelResolutionStatus` (6) — both `str, Enum`

**Dataclasses:** `ResolvedTrackModel` (full model snapshot with counts/blockers/warnings), `TrackModelResolverResult` (resolution outcome with all_candidate_paths + errors)

**Core resolver:** `resolve_best_track_model(loc, layout, base_dir)` — maturity priority: engineer_validated > ai_ready > reviewed > seed_only > missing; ties resolved by created_at (newest wins); malformed files silently skipped

**Prompt context builder:** `build_resolved_track_context_for_prompt(loc, layout, base_dir)` — not yet wired to AI prompts; includes seed warning / reviewed segments / Porsche boundary note / blockers

**Schema extension (`data/track_segment_review.py`):**
- `TrackModelReviewResult.modelling_status: Optional[str] = None` (backward-compatible)
- `export_review_json()` computes and writes `modelling_status` (engineer_grade / user_reviewed / segment_detected)
- `import_review_json()` reads it; old files get `None`

**`ui/track_modelling_vm.py`:** `format_resolver_summary(resolver_result)` → 8-key dict for UI display

**`ui/dashboard.py`:**
- Import: `resolve_best_track_model as _resolve_track_model`, `format_resolver_summary as _format_resolver_summary`
- `_tm_resolver_result` instance var
- "Resolver Status" QGroupBox: 5 labels + blockers + warnings; updates on layout select + after save
- `_tm_refresh_resolver()` method — resolves model, formats, updates labels

**Tests:** 68 new tests in `tests/test_group17g_track_model_resolver.py` — 13 test classes. Full suite: **1364/1369 green** (5 skipped unchanged).

**Key design decisions:**
- Seed YAML is never mutated — modelling_status is persisted in reviewed JSON only
- Seed-only fallback always shows warnings — no silent downgrade to unqualified seed data
- Porsche boundary note always in prompt context (braking/gear/traction not universal truth)
- `build_resolved_track_context_for_prompt` is ready for wiring; NOT yet integrated into any AI caller

**Deferred:**
- Wiring prompt context into Setup Builder / Strategy Builder / Practice Analysis / Live Race Engineer (Group 17H)
- Graphical split/merge editing
- Track auto-detection from telemetry

**Recommended next task:** Group 17H — wire `build_resolved_track_context_for_prompt()` into AI prompt builders (`driving_advisor.py`, `ai_planner.py`); promote modelling status display in Practice Review and Setup Builder context labels.

---

### Session: Group 17F — Segment Review and Track Model Approval (2026-06-24)

**New module:** `data/track_segment_review.py` (pure Python, no PyQt6)

**Enums:** `SegmentReviewStatus` (8 values), `SegmentReviewAction` (7 values)

**Dataclasses:** `ReviewedTrackSegment` (original detection fields + review state; `display_name` property; `is_reviewed` property), `TrackModelReviewResult` (detection metadata + segment list)

**Action functions (7):** `confirm_segment`, `rename_segment` (blank ignored), `reject_segment`, `mark_needs_more_laps`, `mark_split_required`, `mark_merge_required`, `promote_engineer_validated` (CONFIRMED only)

**Aggregate helpers:** `review_completion_pct(review) → float`, `is_ai_ready(review) → (bool, list[str])` with 5-blocker rule set

**JSON I/O:** schema `track_model_review_result_v1`; filename `<loc>__<layout>__reviewed_segments__<session_id>.json` in `data/track_models/`

**`ui/track_modelling_vm.py` additions:** `format_segment_row`, `format_review_summary`, `get_review_button_states`

**`ui/dashboard.py` changes:**
- Import: 9 functions from `track_segment_review` + 3 vm helpers
- `_tm_detect_segments()` auto-creates review and populates table on detection success
- "Segment Review" QGroupBox: 8-col read-only QTableWidget, 6 action buttons, "Save Reviewed Model" button
- "Review Approval" QGroupBox: 7 stat labels (detected/reviewed/confirmed/rejected/needs-laps/completion%/ai-ready/blockers)
- 11 new methods + 8 new signal connections

**Tests:** 122 new tests in `tests/test_group17f_segment_review.py` — 14 test classes. Full suite: **1296/1301 green** (5 skipped unchanged).

**Deferred:**
- Graphical split/merge editing (currently flags only)
- Reviewed segment integration into AI prompts (Group 17G+)
- `modelling_status` promotion after review save

**Recommended next task:** Group 17G — integrate reviewed segments into `build_seed_track_context_for_prompt()` and/or promote `modelling_status` to `segment_detected` after saving a reviewed model.

---

### Session: Group 17E — Automatic Track Segment Detection (2026-06-24)

**New module:** `data/track_segment_detection.py` (pure Python, no PyQt6)

**Enums:** `TrackSegmentType` (12 values), `TrackSegmentDirection`, `TrackSegmentDetectionConfidence`

**Dataclasses:** `SegmentDetectionConfig`, `DetectedTrackSegment`, `SegmentDetectionResult`

**Detection:**
- `detect_segments_from_lap(lap, config, ...)` — single-lap: speed minima → apex candidates; walk back/forward for braking + exit; emits `braking_zone`, `corner_entry`, `apex_zone`, `corner_exit`, `traction_zone` per corner; fills gaps with `straight` / `fuel_saving_candidate`
- `detect_track_segments(session, reference_path, layout_seed, config)` — multi-lap: clusters apex candidates by lap_progress across laps; confirmed corners from ≥ 2 laps; auxiliary: gear zones, limiter zones, kerb candidates, fuel-save candidates
- `assign_corner_numbers(segments, expected_corner_count)` — assigns T1/T2… by progress; mismatch warning; never invents corners
- `export_segment_detection_json()` / `import_segment_detection_json()` — schema `segment_detection_result_v1`

**Key design choices:**
- No steering angle (not in GT7) → heading from XZ position delta; direction = `UNKNOWN` when no movement
- Car-specific segments (braking/traction/limiter/gear/fuel-save) tagged with `calibration_car_id`; track-geometry (apex/straight/kerb) not tagged
- `layout_seed.corners_expected` → warning only; detection count never inflated
- Rejected laps excluded before detection

**`ui/dashboard.py` changes:**
- Import `detect_track_segments as _detect_track_segments`
- "Detect Segments" button (enabled when `ctrl.can_save`)
- 3 new status labels: `_tm_lbl_seg_summary`, `_tm_lbl_seg_expected`, `_tm_lbl_seg_status`
- `_tm_detect_segments()` method + `_connect_signals()` wiring

**Tests:** 99 new tests in `tests/test_group17e_track_segment_detection.py` — 22 test classes. All 1174 pass.

**Recommended next task:** Group 17F — wire `build_seed_track_context_for_prompt()` into AI practice/coaching prompts; or Group 17G — promote `modelling_status` to `reference_path_built` / `segment_detected` after successful calibration steps.

---

### Session: Group 16 — Phase 2 Per-Lap Telemetry (2026-06-23)

#### Phase 2-D: Schema Migration v3 + TelemetryFrame/LapStats tyre temps
- `telemetry/recorder.py` — `TelemetryFrame` gains `tyre_temp_fl/fr/rl/rr: float = 0.0`; `LapStats` gains `tyre_temp_fl/fr/rl/rr_avg: float = 0.0`; `_compute_stats()` averages per-corner temps from frames (skips 0.0 frames); `record_frame()` injects tyre temps from packet
- `data/session_db.py` — DDL adds 4 `tyre_temp_*_avg REAL NOT NULL DEFAULT 0.0` cols to `lap_records`; `_V3_ALTER_COLUMNS`, `_migrate_v3()`, PRAGMA user_version=3; `write_lap()` persists all 4 via `getattr(stats, ...)` fallback

#### Phase 2-A/B/C: DB query methods + AI prompt wiring
- `data/session_db.py` — `get_session_laps()` gains `exclude_pit`, `exclude_out`, `limit` params + expanded SELECT including 9 telemetry columns; `get_recent_fuel_sequence(car_id, track, limit=15)` returns chronological fuel consumption (pit/out/zero excluded); `get_compound_lap_sequences(car_id, track, session_id=0, limit_per_compound=25)` returns per-compound lap-time sequences
- `strategy/ai_planner.py` — `_build_per_lap_telemetry_block()` formats per-lap table (Phase 2-A); `_build_fuel_trend_block()` formats avg/std-dev/95th-pct with `[measured]` tag (Phase 2-B); `_build_compound_sequence_block()` formats per-compound sequences with linear-regression deg rate (Phase 2-C); `analyse_practice_session()` + `_build_practice_prompt()` gain `per_lap_telemetry: list | None = None`; `analyse_strategy()` + `_build_race_prompt()` gain `fuel_sequence` + `compound_sequences`
- `ui/dashboard.py` — `_run_practice_analysis()` captures `_hist_session_id` before thread; worker calls `get_session_laps(_hist_session_id, exclude_pit=True, exclude_out=True, limit=5)` in try/except; passes `per_lap_telemetry=_per_lap_telem`; `_run_ai_analysis()` queries fuel_sequence + compound_sequences before thread; passes both to `analyse_strategy()`

#### Tests
- `tests/test_group16_per_lap_telemetry.py` — 74 new tests (all pass)
- `MASTER_TESTING_REGISTER.md` — Group 16 section added
- `docs/PROJECT_STATE.md` — Group 16 row added; build stats updated (643/648 pass)

### Tests Run
- `tests/test_group16_per_lap_telemetry.py`: 74/74 pass
- Full suite: 643 pass / 5 skip / 0 fail (648 collected)

---

### Session: Group 15A — DEF-P3-013 Fix (2026-06-23)

### Files Changed
- `strategy/_ai_client.py` — `AILogEntry` gains `car_id: int = 0` and `track: str = ""` fields; `call_api()` gains matching kwargs; all three `AILogEntry` construction sites (debug/success/exception) pass them through
- `strategy/ai_planner.py` — `analyse_strategy()`, `analyse_practice_session()`, `build_car_setup()` gain `car_id: int = 0`; thread to `call_api()` with `track=params.track` or `track=track`
- `strategy/driving_advisor.py` — all four `call_api()` sites (`build_coaching_response`, `build_setup_advice_response`, `build_combined_setup_response`, `build_driver_feeling_response`) pass `car_id=self._car_id_ref[0], track=_track_da`
- `ui/dashboard.py` — `_run_ai_analysis()` resolves `_car_id_strat` before worker; `_run_practice_analysis()` passes `car_id=_car_id_hist`; `_run_build_setup()` resolves `_car_id_build` before worker; `_on_ai_log_entry_dict()` passes `car_id`/`track` when reconstructing AILogEntry from DB rows
- `tests/test_group15a_ai_log_car_track.py` — 56 new tests (all pass)
- `MASTER_TESTING_REGISTER.md` — DEF-P3-013 closed; AWR-063/068 closed; Group 15A section added
- `docs/PROJECT_STATE.md` — Group 15A row added; build stats updated (569/574 pass)
- `docs/CURRENT_CLAUDE_HANDOFF.md` — this file updated

### Tests Run
- `tests/test_group15a_ai_log_car_track.py`: 56/56 pass
- Full suite: 569 pass / 5 skip / 0 fail (574 collected)

### AWR Summary (All Closed)

| AWR | Area | Result |
|-----|------|--------|
| AWR-058 | Strategy race_params (race_type/tuning/bop/avail_tyres) | CLOSED |
| AWR-059 | Practice worker car_id resolution | CLOSED |
| AWR-060 | Practice race_params bop | CLOSED |
| AWR-061 | avail_tyres throughout | CLOSED |
| AWR-062 | Driver feedback in practice AI | CLOSED |
| AWR-063 | Prev AI recs in practice prompt | CLOSED (DEF-P3-013 fixed Group 15A) |
| AWR-064 | PTT coaching car context | CLOSED |
| AWR-065 | PTT setup_advice live setup | CLOSED |
| AWR-066 | Timed race in race prompt | CLOSED |
| AWR-067 | build_car_setup race context | CLOSED |
| AWR-068 | _DATA_QUALITY_NOTE in ai_planner | CLOSED |
| AWR-069 | Strategy validation + warning banner | CLOSED |

### Open Defects Remaining (not Group 15 scope)

| ID | Priority | Title |
|----|----------|-------|
| DEF-P2-018 | P2 | Outlap row has no visual identification in Practice Review |
| DEF-P3-005 | P3 | Pit window is static, not recalculated on deviation |
| DEF-P3-007 | P3 | Disabled race type field not visually dimmed |
| DEF-P3-008 | P3 | Top speed target never populated from valid practice telemetry |

### Manual UAT Still Required
- AWR-063: Run Practice Analysis twice for same car+track. Second call's prompt (via GT7_AI_DEBUG=1) should contain "Previous AI Recommendations" section with the first response text.
- AWR-062: Submit driver feedback, run Practice Analysis → "Recent Driver Feedback" section appears in prompt.
- All other AWRs unchanged from prior session.

### Session: Group 17 (user: Group 16) — Corner-Level Telemetry Learning (2026-06-23)

#### New module: `data/corner_learning.py`
- `CornerIssue` dataclass: car_id, track, corner_id, lap_count, total_laps, issue_type, phase, severity, confidence, evidence, session_id, detected_at
- `ISSUE_TYPES` frozenset, `SETUP_ADVICE_MAP` dict (all major issue types → list[str])
- `_corner_id_from_xyz(x, z, bucket_m=100)` → XZ world-position bucket string
- PATH A: `detect_issues_from_lap_records(laps, car_id, track, session_id)` — from event_positions_json in lap_records; thresholds: ≥3 laps OR ≥30% of valid laps
- PATH B helpers: `detect_corner_events_from_frames(frames)` + `detect_issues_from_frame_data(per_lap_events, ...)`
- `merge_issues(path_a, path_b)` — PATH B overwrites PATH A for same corner+type
- `verify_fix(previous_issues, current_issues)` → dict of "corner_id:issue_type" → FIX_STATUS_*
- `build_corner_summary_for_prompt(issues, verifications, max_issues=6)` → concise AI prompt block
- `get_setup_advice(issue_type)` → list[str] from SETUP_ADVICE_MAP

#### `data/session_db.py` — schema v4
- `_DDL_V4` string: `corner_issues` table + index
- `_DDL` updated to include `_DDL_V4`
- `_migrate_v4()` — CREATE TABLE IF NOT EXISTS corner_issues + index
- `_migrate()` updated: `if version < 4:` block
- `get_session_laps()` SELECT now includes `event_positions_json` (needed for PATH A in worker)
- New methods: `save_corner_issues(issues)`, `get_corner_issues(car_id, track, session_id=0)`, `get_previous_corner_issues(car_id, track, exclude_session_id)`

#### `strategy/ai_planner.py`
- `_build_practice_prompt()` + `analyse_practice_session()` gain `corner_issues_summary: str = ""`; injected after per_lap_section
- `_build_race_prompt()` + `analyse_strategy()` gain `corner_issues_summary: str = ""`; injected after _fuel_trend_block

#### `strategy/driving_advisor.py`
- `build_coaching_response()`, `_build_coaching_prompt()` gain `corner_issues_summary`; added to `extra_sections`
- `build_setup_advice_response()`, `_build_setup_prompt()` gain `corner_issues_summary`; added to `extra_sections`
- `_build_combined_prompt()` gains `corner_issues_summary`; added to `extra_sections`

#### `ui/dashboard.py`
- `_run_practice_analysis()` worker: after `_per_lap_telem` query, calls `detect_issues_from_lap_records`, saves via `save_corner_issues`, loads previous via `get_previous_corner_issues`, runs `verify_fix`, builds `_corner_summary`, passes `corner_issues_summary=_corner_summary` to `analyse_practice_session()`
- `_run_ai_analysis()`: reads saved corner issues from DB before thread, reconstructs CornerIssue objects, builds `_strat_corner_summary`, passes to `analyse_strategy()`

#### Tests
- NEW: `tests/test_group17_corner_learning.py` — 64 tests (all pass)
- `tests/test_group16_per_lap_telemetry.py` — `test_user_version_is_3` updated to `>= 3`
- `MASTER_TESTING_REGISTER.md` — Group 17 section added
- `docs/PROJECT_STATE.md` — Group 17 row added; build stats updated (707/712 pass)

### Tests Run
- `tests/test_group17_corner_learning.py`: 64/64 pass
- Full suite: 707 pass / 5 skip / 0 fail (712 collected)

---

### Session: Group 18 — DEF-P3-014 Startup State Leak (2026-06-23)

**Defect:** `python main.py` with a previously used event printed:
```
[Strategy] plan set: 2 stints
[StateTracker] race config: timed, duration=40.0 min
[StateTracker] race config: timed, duration=40.0 min
```

**Root causes found and fixed:**

1. `main.py` lines 361–365 (removed): `strategy_engine.set_plan()` called at startup with `config["strategy"]["stops"]` — activated Live Race Engineer without user action
2. `main.py` lines 509–527 (removed): `tracker.set_race_config()` called from `config["race"]` / `config["strategy"]["race_type"]` before window created — first StateTracker print
3. `ui/dashboard.py` `_update_race_config()` (removed block): called `tracker.set_race_config()` during `_build_strategy_builder_tab()` on every startup — second StateTracker print
4. `ui/dashboard.py` `_on_event_set_active()` line 7801 (fixed): `from telemetry.tracker import RaceType` → `from telemetry.state import RaceType` (module `telemetry.tracker` does not exist — import silently caught by try/except, meaning `set_race_config()` never actually fired from the explicit activation path either)

**Architecture boundary**: `_on_event_set_active()` is now the ONLY path that calls `tracker.set_race_config()`.

**Tests:** `tests/test_group18_startup_no_plan.py` — 21 tests, all pass
**Full suite:** 728 pass / 5 skip / 0 fail (733 collected)

**Acceptance criteria met:**
- `python main.py` does NOT print `[Strategy] plan set` unless user activates a plan
- `python main.py` does NOT print `[StateTracker] race config` on startup
- Saved stops remain visible in Strategy Builder UI (populated in `dashboard.__init__` lines 482–487)
- Opening app after previously using a 40-min 2-stint plan does NOT reactivate it
- Duplicate StateTracker print eliminated (was 2, now 0 at startup)

### Session: Group 17A — Track Intelligence Seed Loader (2026-06-24)

#### New module: `data/track_intelligence.py`

- `TrackModellingStatus` enum — 9 values (`not_modelled`, `seed_only`, `telemetry_sampled`, `reference_path_built`, `segment_detected`, `user_reviewed`, `practice_refined`, `race_validated`, `engineer_grade`); helper methods: `is_ready_for_calibration()`, `is_ready_for_ai()`, `missing_calibration_requirements()`
- Dataclasses: `TrackSeedMetadata`, `CalibrationCarProfile`, `TrackLayoutSeed`, `TrackLocationSeed`, `TrackSeedLoadResult`
- `load_track_seed(yaml_path, force_reload)` — validates file exists, metadata, calibration cars, tracks, unknown statuses preserved, duplicates detected; caches on success from default path
- `get_track_locations()`, `get_track_layouts()`, `resolve_track_layout()`, `search_track_layouts()` — query helpers
- `build_seed_track_context_for_prompt(track_location_id, layout_id)` — AI prompt context block with seed data caveat for unmodelled layouts and calibration car boundary note
- Architecture boundary: Track Intelligence owns seed facts and modelling status only; no event/car/strategy state

#### New test file: `tests/test_group17a_track_intelligence.py`
- 63 tests, all pass (791/796 full suite)

#### New doc: `docs/TRACK_INTELLIGENCE_STARTER_MODEL.md`
- Architecture boundary, dataclass overview, enum maturity table, all 5 public functions, seed coverage table (18 layouts with full facts), calibration car facts, validation checks, next steps

#### Tests Run
- `tests/test_group17a_track_intelligence.py`: 63/63 pass
- Full suite: 791 pass / 5 skip / 0 fail (796 collected)

---

### Session: Group 17B — Track Modelling UI Foundation (2026-06-24)

#### New module: `ui/track_modelling_vm.py`
- Pure Python view model, no PyQt6 dependency — testable without QApplication
- `format_layout_facts(layout, loc)` — 27-row `(label, value)` list; None → "Unknown / needs calibration"
- `format_readiness(layout)` — readiness status rows with missing-step drill-down
- `format_calibration_car(car)` — Porsche 911 RSR key facts
- `get_seed_warning_text(layout)` — amber banner text for seed/partial layouts; empty for calibrated
- `is_seed_only(layout)` — True if `not_modelled` or `seed_only`
- `build_location_display_items(seed_result)` — sorted location combo items
- `build_layout_display_items(seed_result, loc_id)` — cascaded layout combo items
- `get_selected_location(seed_result, loc_id)` — resolve or None
- `get_selected_layout(seed_result, loc_id, lay_id)` — resolve or None
- `build_prompt_preview(seed_result, loc_id, lay_id)` — full AI prompt preview string
- `describe_seed_load_status(seed_result)` — one-line status summary
- `CALIBRATION_CAR_BOUNDARY_NOTE`, `SEED_WARNING_TEXT` constants

#### Modified: `ui/dashboard.py`
- Imports: `load_track_seed`, `search_track_layouts`, all `track_modelling_vm` helpers
- Tab 12 added: `self._tabs.addTab(self._build_track_modelling_tab(), "Track Modelling")`
- `_on_tab_changed(12)` → `self._tm_on_tab_shown()`
- `_build_track_modelling_tab()` — QSplitter with left selection panel + right detail panel
  - Left: search (QLineEdit + button → results QListWidget), location QComboBox → layout QComboBox, seed status label
  - Right: amber warning QGroupBox, layout facts QFormLayout (27 rows), readiness QFormLayout, calibration car QFormLayout + boundary note, AI prompt QPlainTextEdit (read-only)
- `_tm_on_tab_shown()` — lazy seed load on first tab visit; populates combos + car panel
- `_tm_populate_location_combo()`, `_tm_on_location_changed()`, `_tm_on_layout_changed()`
- `_tm_clear_detail_panels()`, `_tm_refresh_details(loc_id, lay_id)`
- `_tm_populate_calibration_car()`, `_tm_do_search()`, `_tm_on_search_result_selected()`
- `_tm_` prefix on all widgets to avoid namespace conflicts

#### New test file: `tests/test_group17b_track_modelling_ui.py`
- 101 tests, all pass
- 13 test classes covering all view model functions
- No PyQt6 widgets tested — pure view model layer only

#### Tests Run
- `tests/test_group17b_track_modelling_ui.py`: 101/101 pass
- Full suite: 892 pass / 5 skip / 0 fail (897 collected)

---

### Session: Group 17C — Calibration Lap Capture and Reference Path Builder (2026-06-24)

#### New module: `data/track_calibration.py`
Pure Python — no PyQt6 dependency.

**Data models:**
- `TelemetrySample` — one GT7 telemetry snapshot; `from_frame()` factory accepts duck-typed `TelemetryFrame`; `steering=None` (GT7 does not expose steering angle); `is_off_track` inferred from `road_plane_y < 0.5 AND speed > 20 kph`; `is_in_pit_lane=None` per sample
- `LapQualityResult` — `quality`, `reasons`, `sample_count`, `path_length_m`, `duration_ms`; `.is_usable` property
- `CalibrationLap` — lap_number, lap_time_ms, samples, quality, quality_reasons, path_length_m
- `CalibrationSession` — session_id, track_location_id, layout_id, calibration_car_id (default `porsche_911_rsr_991_2017`), started_at, source, laps, notes, modelling_status
- `ReferencePathPoint` — lap_progress, distance_along_lap_m, x, y, z, speed_kph_avg, source_lap_count
- `ReferencePath` — track/layout/car IDs, source_lap_count, points, confidence 0–1, built_at, warnings
- `CalibrationBuildResult` — success, reference_path, usable/rejected/low_confidence counts, errors, warnings
- `CalibrationLapQuality` enum: `USABLE`, `LOW_CONFIDENCE`, `REJECTED`
- `CalibrationSource` enum: `GT7_TELEMETRY_LIVE`, `IMPORTED_JSON`, `SYNTHETIC_TEST`

**Quality rules (reject):** too few samples (<50), all-zero xyz, coordinate jump >100 m, pit lane >10%, off-track >30%, duration outlier (>2× or <0.5× session median), path length outlier

**Distance / progress helpers:** `point_distance_3d`, `estimate_path_length`, `detect_coordinate_jumps`, `cumulative_distances`, `normalize_to_lap_progress`, `resample_to_buckets`

**Reference path builder:** `build_reference_path(session)` — 200 progress buckets, averaged per bucket across usable laps, cumulative distances, confidence = fill_rate × min(1, lap_count/5); requires ≥ 2 usable laps

**File I/O:** `export_reference_path_json`, `import_reference_path_json` — JSON under `data/track_models/`

**Constants:** `MIN_CALIBRATION_SAMPLES=50`, `MAX_JUMP_THRESHOLD_M=100`, `MAX_PIT_FRACTION=0.10`, `MAX_OFF_TRACK_FRACTION=0.30`, `N_PROGRESS_BUCKETS=200`, `MIN_USABLE_LAPS_FOR_PATH=2`, `PRIMARY_CALIBRATION_CAR_ID="porsche_911_rsr_991_2017"`

#### Modified: `ui/dashboard.py`
Added disabled placeholder calibration controls to Track Modelling tab right panel:
- "Start Calibration Session" button (disabled, tooltip explains deferral)
- "Stop Calibration Session" button (disabled)
- "Build Reference Path" button (disabled, tooltip: requires ≥ 2 usable laps)
- "No calibration session active" status label
Live telemetry wiring deferred — no existing dashboard architecture changed.

#### New test file: `tests/test_group17c_track_calibration.py`
- 102 tests, all pass
- 14 test classes covering all models, helpers, quality evaluator, path builder, file I/O, regression checks
- No PyQt6 dependency — fully headless

#### Decisions Made
- No DB migration — in-memory model + JSON file export sufficient for this group
- No corner/segment detection — deferred to Group 17D
- No live telemetry plumbing — deferred; existing architecture makes this safe when ready
- `steering` field always `None` — GT7 does not expose steering angle
- `is_in_pit_lane` always `None` per sample — no per-sample pit flag in GT7 packet

#### Tests Run
- `tests/test_group17c_track_calibration.py`: 102/102 pass
- Full suite: 994 pass / 5 skip / 0 fail (999 collected)

---

### Session: Group 17D — Live Telemetry Calibration Session Wiring (2026-06-24)

#### New module: `data/track_calibration_runtime.py`
Pure Python — no PyQt6 dependency.  Depends only on `data.track_calibration`.

**Adapter helpers:**
- `can_capture_calibration_sample(packet)` — duck-typed guard; returns False for paused/loading/off-track or any exception
- `infer_lap_number(packet, fallback=None)` — `laps_completed + 1` when ≥ 0; returns `fallback` when -1 (practice/qualifying with no lap count)
- `packet_to_calibration_sample(packet, lap_number)` — full GT7Packet → TelemetrySample mapping; `steering=None`, `is_in_pit_lane=None`; `is_off_track` from `road_plane_y < 0.5 AND speed > 20`; returns None on invalid/exception

**State enum:** `CalibrationCaptureState` — `INACTIVE` / `RECORDING` / `STOPPED` / `BUILT` / `ERROR`

**Controller:** `TrackCalibrationCaptureController`
- `start_session(track_location_id, layout_id, calibration_car_id)` — fails (ERROR) if IDs blank; resets all state
- `add_sample_from_packet(packet)` — RECORDING only; detects lap boundary from `laps_completed` change; calls `_close_current_lap()` at boundary; groups `TelemetrySample` objects into `CalibrationLap` objects
- `stop_session()` — flushes partial lap; transitions to STOPPED
- `evaluate_laps()` → `assess_session_laps(session)`
- `build_reference_path()` → `build_reference_path(session)`; transitions to BUILT
- `save_reference_path(output_dir)` → `export_reference_path_json(reference_path, output_dir)`
- `get_status_summary()` — 15-key dict for UI label refresh
- Properties: `can_start`, `can_stop`, `can_build`, `can_save`, `is_recording`
- Internal: `_close_current_lap()` — computes `lap_time_ms = t_end - t_start`, appends `CalibrationLap` to session

#### Modified: `ui/dashboard.py`
- `SignalBridge` gains `calibration_packet = pyqtSignal(object)` (after `ptt_status`)
- Import `TrackCalibrationCaptureController` from `data.track_calibration_runtime`
- Calibration group rebuilt: 4 live buttons (Start/Stop/Build/Save) with green hover style; 5 status labels (`_tm_lbl_sample_count`, `_tm_lbl_lap_info`, `_tm_lbl_build_info`, `_tm_lbl_cal_status`, `_tm_lbl_save_path`)
- `self._tm_controller = TrackCalibrationCaptureController()` stored on window after `self._tm_seed_result = None`
- `_tm_on_layout_changed()` calls `self._tm_update_cal_buttons()` after refresh
- `_tm_clear_detail_panels()` calls `self._tm_update_cal_buttons()`
- New methods: `_tm_update_cal_buttons()`, `_tm_update_cal_status()`, `_tm_on_calibration_packet()`, `_tm_start_session()`, `_tm_stop_session()`, `_tm_build_path()` (shows QMessageBox on fail), `_tm_save_path()` (shows QMessageBox on fail)
- `_connect_signals()` adds: `calibration_packet → _tm_on_calibration_packet`, 4 button click connections

#### Modified: `main.py`
- `_cal_pkt_counter = [0]` added as closure variable before `on_packet` definition
- In `on_packet()` after `recorder.record_frame()`: `if _cal_pkt_counter[0] % 6 == 0: bridge.calibration_packet.emit(packet)`; counter incremented mod 1000000
- Effective rate: 60 Hz / 6 = 10 Hz — same subsampling as `LapTelemetryRecorder`

#### New test file: `tests/test_group17d_calibration_runtime.py`
- 81 tests, all pass
- 10 test classes covering all helpers, state machine lifecycle, lap grouping, save/load, status summary, button properties, regression imports
- No PyQt6 dependency — fully headless

#### Decisions Made
- Controller is pure Python; `GT7Packet` accepted via duck-typing to avoid circular imports
- `steering` always `None` — GT7 protocol; `is_in_pit_lane` always `None` — no per-sample flag
- `laps_completed = -1` (practice mode) uses `fallback` parameter — controller defaults fallback to current lap number or 1
- `can_build` is a pre-filter (≥ 2 closed laps); the actual build can still fail quality evaluation
- QMessageBox shown on build/save failure so the user sees a clear error without leaving the tab

#### Tests Run
- `tests/test_group17d_calibration_runtime.py`: 81/81 pass
- Full suite: 1075 pass / 5 skip / 0 fail (1080 collected)

---

### Recommended Next Task
Group 17E — Wire `build_seed_track_context_for_prompt()` from `data/track_intelligence.py` into AI practice/coaching prompts (`strategy/driving_advisor.py` and `strategy/ai_planner.py`) so the AI receives track facts (sector count, elevation, corner types, known overtaking points) from the Track Modelling seed. Requires Track Modelling tab's selected layout to be passed through to the driving advisor call site.

---

### Session: Group 17O UAT Remediation (2026-06-25)

**Defects fixed:** DEF-17O-UAT-001, DEF-17O-UAT-002, DEF-17O-UAT-003

**DEF-17O-UAT-001 — Station Map panel shows "No track map loaded" after successful build**
- Root cause: `_tm_try_build_station_map()` read `ctrl._ref_path` (line 2737) but `TrackCalibrationCaptureController` has no `_ref_path` attribute. The reference path is stored at `ctrl._last_build_result.reference_path`.
- Fix: Changed `_tm_try_build_station_map(self)` to `_tm_try_build_station_map(self, ref_path=None)`. When `ref_path` is None, reads `ctrl._last_build_result.reference_path` (the correct attribute). Added a disk-load path in `_tm_detect_segments_safe()`: when loading calibration session from disk and station map is None, loads the saved reference path JSON and calls `_tm_try_build_station_map(ref_path=_ref)`.
- Imports added: `import_reference_path_json as _import_ref_path` from `data.track_calibration`.

**DEF-17O-UAT-002 — Segment Review still displays telemetry behaviour as track geometry**
- Root cause: `_create_seg_review(result)` at line 2917 was called with the full `SegmentDetectionResult` including `GEAR_ZONE`, `LIMITER_ZONE`, `FUEL_SAVING_CANDIDATE`, `KERB_OR_BUMP_CANDIDATE` — telemetry overlays that are not permanent track geometry.
- Fix: Added `_TELEMETRY_OVERLAY_SEG_TYPES` frozenset constant near imports; also imported `TrackSegmentType` as `_TrackSegmentType`. After `_create_seg_review(result)`, filters `self._tm_review_result.segments` to remove overlay types. Segment count label now shows geometry-only count with a note like "+3 telemetry overlays hidden".

**DEF-17O-UAT-003 — Daytona runtime still reports 5 corners despite seeded expected 12**
- Root cause: Corner count labels used `result.detected_corner_count` (old Group 17E telemetry detection, 5 corners for Daytona) instead of the station map seeded corner count (12, guaranteed by placeholder filling).
- Fix: In `_tm_detect_segments_safe()`, after detection succeeds, checks if `_tm_station_map` is available. If so, shows station map corner counts instead: `"{n_seeded} seeded corners | {n_detected_geo} curvature-detected | {n_placeholder} estimated"`. Falls back to old detection labels only if no station map is available.

**New test file:** `tests/test_group17o_uat_defects.py` — 23 tests across 3 defect classes
- `TestDef17OUAT001RefPathAttribute` (6 tests): verifies controller has no `_ref_path`, correct attribute chain works, station map builds from ref path, has_map=True produced, None/empty path → no_map
- `TestDef17OUAT002OverlayFiltering` (9 tests): overlay frozenset defined, all 4 overlay types in set, all geometry types NOT in set, filtering removes overlays, geometry preserved, review result filtering, overlay count calculation
- `TestDef17OUAT003DaytonaCornerCount` (8 tests): seed=12 → 12 seeded corners, station map is authoritative, placeholders fill gap, draw data has 12 labels, no-seed doesn't guarantee 12, status text includes count, detection result can differ from station map

**Files changed:**
- `ui/dashboard.py` — import fixes, `_TELEMETRY_OVERLAY_SEG_TYPES` constant, `_tm_try_build_station_map()` ref_path fix + optional param, disk-load station map build in `_tm_detect_segments_safe()`, overlay filtering, station map corner labels

**Full suite result: 2037 pass / 5 skip / 0 fail**

**Manual Daytona UAT steps after remediation:**
1. Start calibration at Daytona Road Course → drive 3+ clean laps → Stop → Build Reference Path.
2. Station Map panel must now render (no longer says "No track map loaded").
3. Save Reference Path → confirm map still shown.
4. Click Detect Segments → Segment Review table must NOT contain "Limiter approach", "Kerb/bump candidate", or "Gear zone" rows.
5. Summary label must read e.g. "12 seeded corners | 5 curvature-detected | 7 estimated" (not "Expected corners: 12 ≠ detected: 5").
6. Restart app, load Daytona → click Detect Segments → map builds from saved ref path, same corner summary shown.
