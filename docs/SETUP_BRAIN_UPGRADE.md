# Setup Brain Upgrade — Professional Race Engineer Diagnosis

> Author: Setup Brain Upgrade sprint · Date: 2026-07-05
> Branch: `ofr2-quali-race-disciplines` (built on top of the OFR-2 work)
>
> Companion docs: `docs/OFR2_SEPARATE_DISCIPLINES.md`,
> `docs/SMART_RACE_ENGINEER_ROADMAP.md`. Backend-only — no UI surface yet.
>
> **This file is now multi-sprint.** The original Group 39 upgrade is below,
> followed by Group 41, Group 42, Group 45, and — added most recently — **Group 46
> (Setup Brain Learning & Race Context)**. The full, honest architecture accounts
> live in `docs/RULE_FIRST_SETUP_BRAIN.md` § 14 (Group 45 — Intelligence
> Expansion) and § 15 (Group 46 — Learning & Race Context); the sections below are
> the changelog-level detail.

---

## Group 46 — Setup Brain Learning & Race Context (changelog)

> Date: 2026-07-06 · Branch `ofr2-quali-race-disciplines` (on top of Group 45).
> **Full architecture + honesty account: `docs/RULE_FIRST_SETUP_BRAIN.md` § 15
> ("Setup Brain Learning & Race Context").** This section is the changelog-level
> highlight. `RULE_ENGINE_VERSION` is now **"46.0"**; the DB `user_version` is now
> **12**.

The rule-first Setup Brain now **learns across sessions** and its **Analyse**
recommendations are shaped by **fuel load** and by **fuller per-gear telemetry**;
the from-scratch **Baseline** is now **numerically biased by session type**; and
the Porsche pack inherits the new confidence layers. The architecture is
preserved: telemetry + feedback + setup + car/track/session context + learning
history → deterministic diagnosis → deterministic rule recommendation →
validation → AI audit-only → approved-only display/apply. The AI still cannot
author setup values / add approved fields / un-block / un-reject / author per-gear
values; both paths work with the AI disabled; the Apply gate is unchanged.

### Cross-session learning persistence + feed
* **NEW SQLite table `learning_outcomes`** (`data/session_db.py::_migrate_v12`;
  PRAGMA `user_version` 11→12; additive `CREATE TABLE IF NOT EXISTS`, idempotent).
  Columns: id, ts, car_id, track, layout_id, session_id, session_type, rule_id,
  source_path, verdict, confidence, driver_profile_version, rule_engine_version +
  an index on (car_id, track, layout_id).
* **DELIBERATELY NOT persisted to `data/setup_history.json`** — that file is a
  user-local artifact owned by `setup_history.py`; learning lives entirely in the
  gitignored DB (single owner, no user-file churn, no accidental commit of local
  state).
* `record_learning_outcome(...)` (INSERT, never raises) is written from the OFR-1
  scoring pass (`ui/dashboard.py::_trigger_scoring_pass`) after `persist_score`,
  per approved rule_id, skipping `insufficient_data`;
  `get_learning_outcomes(car_id, track, layout_id)` returns `[]` on any error.
* **Feed:** `build_combined_setup_response` loads the scoped rows into a real
  `RuleOutcomeStore` before `run_rule_engine` (improved → fire+success;
  worsened/neutral → fire; insufficient_data → skip). The hook now runs **both
  directions**, capped at one step, validator-gated: **UPGRADE** (`>= 3` samples
  AND success_rate `>= HIGH_SUCCESS_RATE (0.60)` → +1) / **DOWNGRADE**
  (`< LOW_SUCCESS_RATE (0.40)` → −1). `learning_influence` is set **only when a
  step actually happened**. Learning **cannot** un-block / un-reject / bypass
  validation / make the AI actionable.
* **Honest limitations:** the Baseline path does **not** consume rule-confidence
  learning (empty `learning_influence`); `source_path="Baseline"` is
  schema-supported but **not yet written** (only `"Analyse"` in production today);
  `session_type` is stored as `""` on learning rows (scope = car_id + track +
  layout_id; a JOIN/column is deferred).

### Fuel-multiplier influence (Analyse)
`diagnosis["fuel_multiplier"]` (value) + `diagnosis["fuel_high"]`
(`>= HIGH_FUEL_MULTIPLIER_THRESHOLD (5.0)`; unknown → False) are injected
(previously only a `fuel_known` bool). `_process_rule` **upgrades the confidence**
of traction/stability fields (`_FUEL_TRACTION_STABILITY_FIELDS` = lsd_accel,
lsd_initial, arb_rear, aero_rear, ride_height_rear; delta > 0) and is
**note-only** for rotation/aero-cut (`_FUEL_ROTATION_FIELDS`; delta < 0, no
downgrade). **No new deltas** — ranking/confidence only. `fuel_influence` is set
only when the effect occurred and is appended to the change's `evidence` list so
it renders in the existing UI. Fuel = 1.0 / absent → no bias, no claim.

### Session-specific NUMERICAL baseline tuning
`setup_baseline._SESSION_BIAS_TABLE` (qualifying/sprint/endurance/practice/unknown
→ {field: delta}) accumulates into the **same** bias dict as the driver-profile
table, so the existing clamp/round/validator apply unchanged.
`_normalise_session_for_bias(session_type, duration_mins)`: qualifying / sprint
(race & duration < 60 or unknown) / **endurance** (race & duration_mins >= 60) /
practice / unknown; `duration <= 0` is NOT endurance. `build_baseline_setup` +
`build_baseline_setup_response` gained a `duration_mins` param. A per-field
`session_changed` flag compares clamped/rounded output with vs without the bias, so
`session_influence` claims a session tune **only for fields that actually moved**
(else "session noted — no numerical change for this field"; unknown session → "").

### Fuller per-gear intelligence (REAL telemetry detection)
`setup_diagnosis` genuinely detects `wheelspin_by_gear` (throttle > 0.7,
speed > 2 m/s, rear-wheel-speed > 1.3× vehicle speed, bucketed by the gear active
per frame, normalized PER-LAP). `bog_by_gear` and `lockups_by_gear` are honestly
`None` (no reliable 10 Hz signal). `setup_rule_engine._emit_per_gear_changes`
proposes `gear_N` **only** on a real indexed signal — rev-limiter-in-gear
(`per_gear_limiter_evidence[N] > 0` with `gearing_diagnosis_category ==
"gear_too_short"`) or per-gear wheelspin (`wheelspin_by_gear[N] >=
_PER_GEAR_WHEELSPIN_THRESHOLD (2.0)`). Conservative ±0.03 delta; gated on
`gearbox_flag == "may_change"`; same clamp + strict-`>` monotonic + validator;
rule_id `"PG_{N}"`, `source_label` "per-gear rule". `final_drive` (B5/B5b) is
untouched as the broad lever. `diagnosis["per_gear_explanation"]` records
proposed(+evidence) / not-proposed(+reason) for every gear; "top speed low" alone
with no indexed evidence → no gear change + an explanation why.

### Porsche 911 RSR '17 extension
The existing Pack P (P1 traction-first lsd_accel, rr + gr3) auto-benefits from the
new fuel/tyre/learning confidence layers — no new authored rule. Rear-downforce
protection under instability stays with existing Pack A A2. Benchmark **AC37**
(RSR / Fuji / 50 min / high tyre + fuel / rear-loose + mid-push + floaty-front /
snap-throttle wheelspin + top-speed-low + entry-stable + possible-bottoming)
verifies traction-first before/instead of aero-cut, no rear-downforce reduction,
no rearward brake bias, no generic ride-height raise without bottoming confidence,
no top-speed gear-lengthening as the primary wheelspin fix, no AI-authored values,
and passes the Apply gate.

### Constants
`RULE_ENGINE_VERSION` "45.0" → **"46.0"**; DB `user_version` 11 → **12**
(`DB_VERSION=12`); `HIGH_FUEL_MULTIPLIER_THRESHOLD=5.0`; `HIGH_SUCCESS_RATE=0.60`.

### Tests
6 new `tests/test_group46_{learning_persistence, fuel_influence,
baseline_session_modifiers, per_gear, porsche_pack, ui_explainability}.py`
(**122 tests**, incl. the AC37 RSR/Fuji integrated regression, a
fuel-renders-into-evidence test, and an AC16 single-winner-per-field
learning-safety assertion). Reconciled version/schema tests: `RULE_ENGINE_VERSION`
→ 46.0 (`test_group42_rule_first_engine`); DB version → 12
(`test_group42_legacy_storage`, `test_group18b_rec_persistence`, `test_session_db`,
`test_group18e_setup_history`). All Group 46 tests pass; the ~7–20 pre-existing
frozen-allowlist / OFR failures are known, unrelated, and untouched. Run the suite
in halves on Win/Py3.14.

### Deferred (honest)
Baseline rule-confidence learning consumption; `source_path="Baseline"` recording
wiring; `learning_outcomes.session_type` population (needs a JOIN/column);
`bog_by_gear` + `lockups_by_gear` per-gear detection (no genuine telemetry
signal); a fuel-specific *delta* rule. See `docs/RULE_FIRST_SETUP_BRAIN.md` § 15.7.

---

## Group 45 — Setup Brain Intelligence Expansion (changelog)

> Date: 2026-07-06 · Branch `ofr2-quali-race-disciplines` (on top of Group 44).
> **Full architecture + honesty account: `docs/RULE_FIRST_SETUP_BRAIN.md` § 14
> ("Setup Brain Intelligence Expansion").** This section is the changelog-level
> highlight of the three most product-visible pieces. `RULE_ENGINE_VERSION` is
> now **"45.0"**.

The rule-first Setup Brain became **context-aware** — session type, tyre-wear,
drivetrain, and car-class now genuinely shape which rules fire and how
confident/ranked they are — **without inventing precision** (delta magnitudes
are unchanged; context affects filtering, confidence, ranking, contraindication,
and explanation only). The architecture is preserved: Pit Crew owns the decision,
the AI stays audit-only, both Analyse and Baseline run through the one validator →
funnel → renderer → Apply gate, and everything works with the AI disabled. The
engine scope filter (`_scope_matches`, Pack A exempt, `any`/`None`
wildcard-permissive), driver-profile active weighting, session/tyre confidence
bias, and the learning seam (live-but-empty `RuleOutcomeStore`) are all detailed
in § 14 of the architecture doc.

### Pack P — Porsche 911 RSR '17 (the first car pack)
Registered via `register_pack("P", ...)`.
* **Rule P1** — a cautious **lsd_accel increase (traction-first)**, scoped
  `applies_drivetrain=rr` + `applies_car_class=gr3`, precondition snap-throttle
  wheelspin, **contraindicated when `snap_oversteer_exit` is diagnosed**.
* **No P2 (intentional).** Rear-downforce protection under rear instability is
  already handled by existing **Pack A A2** (unconditional, all cars); a separate
  Porsche P2 would duplicate it, so it was omitted. Ride-height raise stays gated
  by A3/A4 (no generic raise). A top-speed deficit under wheelspin is handled
  traction-first (P1), not aero-cut-first (A2 blocks the cut).
* **Labelling** — every change is tagged `source_label` "Porsche-specific rule"
  (pack `P`) or "generic rule".
* **Drivetrain assertion** — the pack asserts RR via `CAR_DRIVETRAIN_OVERRIDES`
  (`{"Porsche 911 RSR (991) '17":"rr"}`), **not** the empty DB drivetrain column;
  the manual UI combo overrides it.

### Gearbox B5b
* **B5** — `gear_too_short` → `final_drive_down` (Group 43).
* **B5b (NEW)** — `gear_too_long` → `final_drive_up`.
* `limiter_limited` stays a **preserve** category (no proposal). The sprint's
  "limiter_before_braking" is **not a real diagnosis category** — it maps to the
  existing `gear_too_short` (documented, not faked). `per_gear_limiter_evidence`
  (alias of `rev_limiter_by_gear`) is exposed for future per-gear rules, which
  remain deferred (final-drive-only broad logic today). Monotonic ordering is now
  enforced **non-increasing** — equal adjacent ratios are allowed; only a strict
  inversion is rejected (engine and the `gearbox_ratio_inversion` validator both
  use strict `>`).

### Tyre-wear contraindications
At `tyre_wear_multiplier >= HIGH_TYRE_WEAR_THRESHOLD (5.0)`,
`diagnosis["tyre_wear_high"]` suppresses **four genuinely tyre-abusing** rules:
**B3** (lsd_accel decrease), **C1_entry_lsd_decel** (lsd_decel decrease),
**C3_mid_arb_rear** (rear ARB soften), **C7_kerb_arb_rear** (rear ARB soften).
Rules that **increase** lsd lock or rear downforce are deliberately **not**
suppressed (they stabilise worn tyres). Missing tyre/fuel context → the honest
"tyre/fuel context not available — conservative default applied" note; the fuel
multiplier is read (`fuel_known`) but **only informational** (no fuel rule yet).

### Tests
NEW `tests/test_group45_engine_scope.py`, `test_group45_gear_monotonic.py`,
`test_group45_context_signals.py`, `test_group45_porsche_pack.py`,
`test_group45_explainability.py`, `test_group45_learning.py`,
`test_group45_baseline_context.py`, `test_group45_ui_context.py`; 3 existing tests
reconciled (`RULE_ENGINE_VERSION` "42.0"→"45.0"; baseline lsd_decel bias nets
differently with `rotation_without_snap`; the inversion validator now strict-`>`).
All Group 45 tests pass; the ~18 pre-existing frozen-allowlist / schema failures
are known, unrelated, and untouched. Run the suite in halves on Win/Py3.14.

### Deferred (honest)
Cross-session `RuleOutcomeStore` persistence + a success-recording feed (seam in
place, empty in production); full per-gear ratio rules; session-specific numerical
baseline tuning; a fuel-specific rule; the two opposing lsd_decel baseline bias
entries net to zero on a profile with both flags. See
`docs/RULE_FIRST_SETUP_BRAIN.md` § 14.11.

---

## 1. What it does

The setup-diagnosis brain (`strategy/setup_diagnosis.py`, the diagnosis-before-AI
+ engineering-validation layer) now reasons like a race engineer about **why** a
symptom appears before it lets the AI touch a setup. The sprint adds four new
diagnostic outputs, replaces a flawed gearing rule, hardens the LSD anti-flip
guard, re-orders feedback by recency, and fixes an `issue_classification`
schema gap. Two production files changed: `strategy/setup_diagnosis.py` and
`strategy/driving_advisor.py`. All new diagnosis keys appear in **both** the
normal and the conservative/error-path diagnosis dicts.

## 2. The pieces

### Gearing diagnosis (app-side, replaces the old blanket rule)
* **`_classify_gearing(...)` → `gearing_diagnosis_category`** ∈
  `gear_too_short` / `gear_too_long` / `top_gear_power_band_limited` /
  `traction_limited_acceleration` / `drag_or_power_limited` / `limiter_limited` /
  `insufficient_data`. Priority decision table: top-gear limiter + below-target →
  `gear_too_short`; top-gear limiter at/above target → `limiter_limited`;
  below-target + severe wheelspin + no top-gear limiter →
  `traction_limited_acceleration`; below-target + early-peak-power + accel-fade →
  `top_gear_power_band_limited`; else `drag_or_power_limited` / `gear_too_long` /
  `insufficient_data`.
* **`_derive_top_gear_frame_signals(frames, top_gear)` (NEW, pure)** — derives
  `accel_fade_detected` and `peak_power_early` over the retained ~10 Hz
  `LapStats.frames`; degrades to `insufficient_data` when frames are absent.
  Tunable module constants: accel-fade throttle %, min samples, peak-power RPM
  fraction, speed-drop %, kerb-proximity window.
* **Removed the flawed rule.** The `gear_note` "Do NOT recommend lengthening
  gears" block in `_build_combined_prompt`, the old
  `DRIVER_HARD_CONSTRAINTS` constraint #8 (now **8** constraints), and the
  `gearbox_edit_when_preserve` validator rule are gone. Replaced with
  **`gearbox_category_mismatch`**, which only blocks gear changes for
  `insufficient_data` / `gear_too_long` / `limiter_limited` (or when the driver
  flags the gearbox as good) — so the Fuji RSR power-band case now **ALLOWS** a
  gearbox change.

### Wheelspin subtype
* **`_classify_wheelspin_subtype(...)` → `wheelspin_subtype`** ∈
  `both_rear_spin` / `snap_throttle_induced` / `kerb_unload_spin` /
  `gear_too_short_spin` / `aero_instability` / `mixed` / `insufficient_data`.
* **Honest deferrals:** `inside_wheel_spin` is **NEVER** emitted (the GT7 packet
  has no per-wheel slip ratio); `rear_platform_stiffness` folds into `mixed`
  (needs a spring/damper baseline the app lacks); `kerb_unload_spin` uses
  `kerb_count > 0` as a proximity proxy (there is no kerb-position channel).

### Compliance priority (unprompted)
* **`_detect_compliance_priority(feeling, avg_kerb)` → `compliance_priority`
  (bool)** — when the driver reports stiffness / kerb-upset / undulation terms
  AND kerb events/lap > 2, natural frequency / damping is raised to first-or-
  second in `_derive_tuning_priority` **without the driver asking**, and
  `format_diagnosis_for_prompt` emits an explicit compliance instruction.

### Dominant-problem re-ordering
* **`_derive_dominant_problem`** — severe/major wheelspin now outranks a
  "consider"-band bottoming call unless the driver's feel explicitly cites
  bottoming (new `"bottoming"` entry in `_FEEL_VOCABULARY`).

### LSD anti-oscillation
* **`validate_setup_engineering`** gains a `rec_history` param + the rule
  **`lsd_reversal_without_evidence`** — fires on an unevidenced LSD-accel
  direction reversal; skips when a `worsened` verdict backs it, when there is no
  prior / first rec, or when history is unavailable. The reversal reason carries
  the prior value, new value, both directions, and a `reversal_reason`.
  `rec_history` is resolved by the **CALLER**
  (`build_setup_advice_response`, `build_combined_setup_response`) from
  STRUCTURED `data/setup_history.json` changes + the DB `worsened` verdict — no
  new `config["strategy"]` read (config_id sourced from `_event_ctx`).

### Feedback chronology
* **`_get_driver_feedback_context`** now splits "Latest feedback (weight
  highest)" (newest) vs "Earlier feedback", with per-field trend tags
  `current` / `improving` / `worsening` / `resolved` via
  **`DrivingAdvisor._feedback_trend_tag`** (newest-first; keyword-based
  "improving" detection). Latest feedback now dominates old feedback.

### Schema fix
* Added `not-present` to the allowed `issue_classification` values in **both**
  prompt builders and `_race_engineer_directives`; removed the invalid
  `"not currently an issue"` example.

## 3. Honesty properties (tested)

`inside_wheel_spin` is never emitted (no per-wheel slip); `rear_platform_stiffness`
degrades to `mixed` (no damper baseline); `kerb_unload_spin` is a count-proxy,
not true spatial proximity; missing frames → gearing `insufficient_data`; the LSD
rule refuses to reverse without either a `worsened` verdict or prior history; the
new keys are present on the conservative/error path too.

## 4. Tests

~72 new tests in `tests/test_group39_setup_brain_upgrade.py`:
AC1 Fuji RSR gearing, AC2 traction-limited, AC3 categories + error-path keys,
AC4 compliance, AC5 wheelspin subtype (incl. never-inside-wheel-spin),
AC6 LSD anti-oscillation, AC7 feedback trend + latest-wins (Scenario 5),
AC8 dominant-precedence, AC9 not-present schema, plus frame-signal unit tests.
4 re-pointed tests in `tests/test_group38_setup_diagnosis.py` (constraint count
9→8, rule rename `gearbox_edit_when_preserve` → `gearbox_category_mismatch`).
This sprint added ~72 green tests with **zero regressions**.

**Full suite after sprint: 5356 pass / 6 skip / 8 fail.** The 8 failures are
ALL pre-existing frozen-allowlist guard tests caused by the already-committed
`ui/track_modelling_ui.py::_tm_restore_last_track` `config["strategy"]` consumer
(unrelated track-modelling tech debt — NOT this sprint), left to the
track-modelling owner.

## 5. Deferred / limitations

* `inside_wheel_spin` and `rear_platform_stiffness` wheelspin subtypes are
  deferred (no per-wheel-slip signal / no damper baseline).
* `kerb_unload_spin` uses a kerb-count proxy, not true spatial proximity.
* The LSD `worsened`-verdict join matches the DB `recommendation_text` blob for
  `"lsd_accel"` — functional, but the one fragile join; a candidate for a
  structured follow-up.
* No UI surface for the new diagnosis keys yet (backend-only; a UI readout is a
  follow-on story).
* The 8 pre-existing track-modelling allowlist failures are not this sprint's
  and remain for the track-modelling owner.

---

# Group 41 — Setup Builder Engineering Validation Gate

> Date: 2026-07-05 · Branch `ofr2-quali-race-disciplines` (on top of Group 40)
> Backend **+ UI** this time — a display-safety gate in the Setup Builder.
> Production files: `strategy/setup_diagnosis.py`, `strategy/driving_advisor.py`,
> `strategy/_setup_constants.py` (NEW), `strategy/_rec_parser.py`,
> `data/setup_history.py`, `ui/setup_builder_ui.py`.

## 6. What it does

A hard gate between the AI's raw setup output and what the driver can see or
apply. Unsafe or malformed recommendations are blocked before they reach the
"CHANGES TO MAKE IN CAR SETUP" section and the Apply button; only
validator-approved changes ever get an apply path.

### Recommendation lifecycle
Explicit statuses: `generated`, `validation_failed`, `retry_requested`,
`retry_failed`, `approved`, `approved_with_warnings`, `fallback_generated`,
`blocked_no_safe_recommendation`. `APPROVED_STATUSES = {approved,
approved_with_warnings, fallback_generated}` in `strategy/_setup_constants.py`.

### Single finalisation funnel
`_finalise_recommendation` in `driving_advisor.py` — both AI paths
(`build_setup_advice_response`, `build_combined_setup_response`) route through
it, producing a frozen `SetupRecommendationResult` dataclass (status,
approved_changes, approved_fields, rejected_changes, analysis, primary_issue,
engineering_errors, validation_warnings, fallback_used, raw_json). The fields
are embedded into the returned JSON (keys: `recommendation_status`, `changes`,
`setup_fields`, `rejected_changes`, `engineering_validation_errors`,
`validation_warnings`, `fallback_used`).

### Display safety (`ui/setup_builder_ui.py::_display_setup_result`)
* "CHANGES TO MAKE IN CAR SETUP" renders ONLY when status ∈ `APPROVED_STATUSES`
  and `approved_changes` is non-empty, iterating `approved_changes` only.
* The Apply button is **HIDDEN** (not just disabled) unless approved-ish with a
  non-empty `approved_fields`, and applies `approved_fields` only (routed
  through `SetupFormWidget.apply_ai_fields`).
* Rejected AI output appears only in a collapsed "Rejected AI output — not for
  use" section (shown for `validation_failed`, `retry_failed`,
  `blocked_no_safe_recommendation`), visually distinct, with no apply path.

### Validator severity
`strategy/setup_diagnosis.py` adds `ValidationFailure(code, message, severity)`
and `validate_setup_engineering_structured()`; the legacy
`validate_setup_engineering` still returns byte-identical prefixed strings. ANY
blocking-severity failure (safety-prefix OR structural such as
`malformed_schema` / `invalid_units` / locked-field) forces status
`validation_failed` (`retry_failed` if retried) and `approved_changes=[]`.
**out-of-range is a WARNING** because the clamping mechanism forces the applied
value back into range — the clamped in-range value is what lands in approved
output.

### New rules
* **Blocking:** `snap_throttle_lsd_accel_gate` (snap_throttle_induced wheelspin +
  lsd_accel increase > 4); `kerb_strike_rh_over_increment` (kerb_strike
  bottoming + rear ride-height increase > 3mm); `gearbox_fake_field`
  (transmission_max_speed_kmh used as an actionable field);
  `gearbox_ratio_inversion` (a gear ratio not strictly lower than the gear
  below it).
* **Warning:** `gearbox_out_of_range` (final_drive outside 2.5–6.0 or any gear
  outside 0.5–4.0 — conservative **invented** constants pending per-car range
  data).

### Real gearbox fields
`final_drive` and `gear_1..gear_6` are now actionable setup fields (added to
`_CANONICAL_SETUP_PARAMS` and `_CAT_FIELDS["transmission"]`; `_normalise_changes`
expands a `gear_ratios:[...]` list into individual `gear_N` keys; surfaced /
applied via `SetupFormWidget`). `transmission_max_speed_kmh` is DEMOTED to
display-only (in `_DISPLAY_ONLY_FIELDS`): still readable for diagnosis /
top-speed-target classification, but stripped from `approved_changes` /
`approved_fields` and never emitted as an actionable change.
`gearbox_category_mismatch` now also blocks `final_drive` / `gear_1..6` changes
when the gearing diagnosis is a preserve category.

### Strict retry contract
`_build_retry_prompt` lists each blocking failure code + max allowed delta +
forbidden fields and forbids repeating rejected changes. A retry that still has
any blocking failure becomes `retry_failed` (never approved). The old UI banner
wording "survived a correction attempt" is removed; the reworded banner reads
"AI recommendation rejected after retry".

### Deterministic fallback engine
`_build_deterministic_fallback` now emits 1–3 real conservative changes that
pass the same validator (respecting ride-height increment / LSD subtype / rake
gates); if nothing safe can be produced the status is
`blocked_no_safe_recommendation` with a "run more laps" message.

### Persistence respects validation state
`data/setup_history.py::save_entry` takes `validation_status` and routes
non-approved statuses to a `_rejected_<config_id>` diagnostic bucket instead of
the primary/current bucket; the DB `setup_recommendations` row now carries the
final lifecycle status (`strategy/_rec_parser.py` extracts
`recommendation_status` from the JSON) instead of the default `'proposed'`.

### Wording / logic fixes
* kerb_strike bottoming is described distinctly from true floor contact and no
  longer forces ride-height as "required".
* snap_throttle_induced wheelspin no longer asserts "inside rear spins" (no
  inside-wheel telemetry exists) and is classified as mixed setup/driver.
* The old "top speed below target ⇒ no gearing change" leakage is removed so
  gearing can change on power-band / driver evidence (with a display-only caveat
  on `transmission_max_speed_kmh`).

### Dedup
`_ENG_SAFETY_PREFIXES` deduplicated to a single shared constant
`ENG_SAFETY_PREFIXES` in `strategy/_setup_constants.py`, imported by both
`driving_advisor` and `setup_diagnosis`.

### Amendment B — UI real-estate cleanup
The redundant read-only "Race Conditions (from Event Planner)" group box was
removed from the Setup Builder header (it duplicated Event Planner + the Home
Race Setup card, all sourced from the same `EventContext`). The 320px header cap
was lifted so the space flows to the setup view. `_sync_setup_builder_from_event`
retains all functional side effects (BoP toggle, setup permissions, spinbox
rebind, RE-brief load, prefill, qual-form sync).

### Amendment C
The Home "Race Setup" card now shows a Damage line (the one race-condition field
that had only been on the removed Setup Builder block), sourced from
`EventContext.damage`.

## 7. Tests

New suite `tests/test_group41_validation_gate.py` (AC0–AC14) covering the
lifecycle statuses, the finalisation funnel + embedded JSON keys, display-safety
gating, validator severity, the four new blocking rules + the out-of-range
warning, real gearbox fields + the transmission_max_speed_kmh demotion, the
strict retry contract, the deterministic fallback / blocked_no_safe_recommendation
path, persistence bucket routing + DB lifecycle status, the wording/logic fixes,
and Amendments B & C.

**Full suite: 5505 passed / 8 pre-existing frozen-allowlist failures / 6
skipped.** The 8 failures are the SAME
`ui/track_modelling_ui.py::_tm_restore_last_track` guards (unrelated
track-modelling tech debt, NOT this sprint), zero new regressions.

**Test-run note (Windows / Python 3.14):** running the ENTIRE suite in one
process can hit a flaky native PyQt teardown segfault; running in two halves (or
by group) completes clean at 5505 passed / 8 pre-existing failures. This is an
environmental test-isolation artifact, not a product defect.

Manual UAT: `docs/UAT_SETUP_BRAIN.md` (Porsche 911 RSR '17 at Fuji).

## 8. Deferred / limitations

* Gearbox ratio ranges (final_drive 2.5–6.0, gears 0.5–4.0) are invented
  constants, not per-car data; `gearbox_out_of_range` is therefore a WARNING,
  not a hard block, to avoid false-blocking legitimate setups. Tighten to
  per-car ranges + blocking once range data exists.
* The DB `_rec_parser` stores the full JSON blob as `recommendation_text` for
  structured setup responses (pre-existing behaviour, not human-readable in the
  DB).
* Flaky full-suite PyQt segfault on Windows/Py3.14 (see above).

---

# Group 42 — Rule-First Setup Brain

> Date: 2026-07-05 · Branch `ofr2-quali-race-disciplines` (on top of Group 41)
> Backend **+ UI + DB**. Companion architecture doc:
> `docs/RULE_FIRST_SETUP_BRAIN.md`. Manual UAT: `docs/UAT_SETUP_BRAIN.md`
> (Rule-First Setup Brain UAT).
> New production files (all `strategy/`, pure Python):
> `setup_knowledge_base.py`, `setup_driver_profile.py`, `setup_rule_engine.py`,
> `setup_plan.py`, `setup_ai_audit.py`. Changed: `strategy/_setup_constants.py`,
> `strategy/driving_advisor.py`, `strategy/_rec_parser.py`,
> `data/setup_history.py`, `data/session_db.py` (v11), `ui/setup_builder_ui.py`,
> `ui/setup_form_widget.py`.

## 9. The rule-first inversion

Groups 38–41 made the AI's setup output *safe* (diagnosis-before-AI +
engineering-validation gate). Group 42 changes **who authors the setup**. The
setup is no longer written by the AI and merely gated — it is written by a
deterministic **rule engine**, and the AI is demoted to an **audit-only** layer
that can approve / warn / reject / request-more-data but **cannot author
actionable setup changes**. The app now has **ONE source of truth for actionable
setup recommendations: the deterministic rule engine.**

The new flow in `build_combined_setup_response` (the Setup Builder "Analyse"
path, the canonical builder):

```
diagnose (build_setup_diagnosis)
  → build_driver_profile()
  → run_rule_engine()  →  SetupPlan
  → plan_to_raw_data  →  _normalise_changes
  → validate_setup_engineering_structured
  → if blocking:  _build_deterministic_fallback   (NOT the AI)
    else if API key:  call_api  →  AI AUDIT ONLY
                      → parse_audit_response  (strips canonical setup keys)
                      → map_audit_to_finaliser
  → _finalise_recommendation   (the unchanged single funnel from Group 41)
  → response JSON
```

## 10. The pieces

### Rule packs (`setup_knowledge_base.py`)
The rule catalogue with `register_pack` / `get_all_rules` / `resolve_delta`;
enums `RulePhase` / `RiskLevel` / `ConfidenceLevel` / `DrivetrainType` /
`CarClass` / `SessionType`; NamedTuples `SetupRule`, `SetupEvidence`. **22 rules**:

* **Pack A (A1–A8) — safety invariants.** Protect fields / block unsafe deltas.
* **Pack B (B1–B6) — driver-style adaptation.** Rank + contraindicate against
  the driver profile.
* **Pack C/D — handling-phase starter set:** `C1_entry_lsd_decel`,
  `C2_entry_brake_bias`, `C3_mid_arb_rear`, `C4_mid_rear_aero`,
  `C5_exit_lsd_accel`, `C6_exit_rear_aero`, `C7_kerb_arb_rear`,
  `C8_kerb_rh_rear`. The remaining per-setting Pack C rules are **deferred** —
  the catalogue is **extensible via `register_pack`**. Delta resolvers are
  **named-string lookups** in `_DELTA_RESOLVERS` (no stored callables — so the
  catalogue stays serialisable/inspectable).

### Driver profile as data (`setup_driver_profile.py`)
`DriverProfile` NamedTuple + `DriverStyleAlignment` enum. `build_driver_profile()`
derives booleans (prefers_front_bite, dislikes_floaty_front, dislikes_snap_exit,
trail_braker, rotation_without_snap, prefers_rear_stability, protects_downforce,
race_values_consistency) from the existing `PERSONAL_DRIVER_TUNING_MODEL` /
`DRIVER_HARD_CONSTRAINTS` constants; **never raises** (neutral defaults on
error). Driver style is now a **DATA STRUCTURE** the engine consumes for ranking
+ contraindications — not just prompt text.

### Rule engine (`setup_rule_engine.py`)
`SetupChangeIntent`, `SetupPlan` NamedTuples;
`run_rule_engine(diagnosis, setup, ranges, profile, allowed_tuning=None,
rule_outcome_store=None) -> SetupPlan`. Pack A protects fields; conflict
resolution moves both same-field opposite candidates to rejected with
`conflict:<id>`; no-op exclusion; gear-count gating; a confidence-downgrade hook.
`RuleOutcomeStore` holds fire/success counts keyed by
rule_id / car / track / driver_profile_version; `get_success_rate` returns `None`
below `MIN_OUTCOME_SAMPLES`. **Never raises** → empty plan on error.

### Plan → funnel (`setup_plan.py`)
`plan_to_raw_data` emits the raw_data dict the existing Group 41 funnel consumes
(including confidence + validation_targets so the engineering validator's schema
check passes); `rejected_to_json`.

### AI audit only (`setup_ai_audit.py`)
`AuditStatus` enum (APPROVED / APPROVED_WITH_WARNINGS / REJECTED /
NEEDS_MORE_DATA), `AuditResult` NamedTuple. `build_audit_prompt` renders 8
labelled sections (diagnosis, plan, evidence, rules-fired, rejected candidates,
protected fields, current setup, driver profile + validation result + audit
instructions). `parse_audit_response(response_text, canonical_params)` **strips
any key in canonical_params** (logs stripped_fields), maps an unknown status →
NEEDS_MORE_DATA, and never raises — this is the structural guarantee that the AI
**cannot author a setup field**. `map_audit_to_finaliser`: REJECTED /
NEEDS_MORE_DATA with no blocking engineering failure → `approved_with_warnings`
advisory (`ai_audit_rejected_advisory`); **a blocking engineering failure ALWAYS
wins.**

### Constants (`strategy/_setup_constants.py`)
`RULE_ENGINE_VERSION="42.0"`, `MIN_OUTCOME_SAMPLES=3`, `LOW_SUCCESS_RATE=0.40`,
`AI_AUDIT_REJECTED_ADVISORY="ai_audit_rejected_advisory"` (**NOT** in
APPROVED_STATUSES). `APPROVED_STATUSES` unchanged = {approved,
approved_with_warnings, fallback_generated}.

### Voice path constraint (`build_setup_advice_response`)
Constrained to **NARRATION-ONLY** via new `_strip_actionable_for_voice(data)`,
which zeroes `changes=[]` / `setup_fields={}` before normalisation — the voice
path can never surface AI-authored actionable setup changes. A full rule-first
rebuild of the voice path is **DEFERRED**.

### DB v11 (`data/session_db.py`)
`_migrate_v11` bumps user_version to 11 and adds 8 nullable TEXT columns to
`setup_recommendations`: deterministic_plan_json, ai_audit_json,
validation_status, approved_changes_json, rejected_changes_json, diagnosis_json,
driver_profile_version, rule_engine_version. The recommendation_text JSON blob is
preserved. These columns are now **POPULATED on insert** (via
`strategy/_rec_parser.py` + `insert_setup_recommendations`). Full migration off
the JSON blob remains deferred.

### Legacy safety — closes Group 41's caveat (`data/setup_history.py`)
Adds `is_legacy_unknown` / `normalise_validation_status` / `LEGACY_UNKNOWN`. A
recommendation whose status is absent / None / unrecognised is now treated as
**legacy_unknown = DISPLAY-ONLY, NO Apply** — previously an absent status could
default to approved. That hole is closed, enforced in `_display_setup_result` and
gated at the Apply button. The `_rejected_` bucket routing is preserved
(`ai_audit_rejected_advisory` routes there).

### Learning foundation (`RuleOutcomeStore`)
**FOUNDATION ONLY.** The confidence-downgrade hook (samples ≥
MIN_OUTCOME_SAMPLES and success_rate < LOW_SUCCESS_RATE → downgrade one
confidence step) is implemented and unit-tested, but **live wiring +
cross-session persistence is DEFERRED** — `build_combined_setup_response` passes
`rule_outcome_store=None` today. No fake ML: a deterministic weighted counter.

### UI (`ui/setup_builder_ui.py::_display_setup_result` + `ui/setup_form_widget.py`)
Section order: diagnosis → **"Pit Crew recommendation"** (approved changes, each
with a collapsed **"Why Pit Crew recommended this"** details block showing
symptom / rationale / evidence / rejected_alternatives / risk_level /
confidence_level / driver_style_alignment) → **"Protected fields (Pit Crew will
not change these)"** → **"Rejected candidate changes (not applied)"** → **"AI
audit"** (verdict + concerns) → **"Rejected AI output — not for use"**. Legacy
banner: "Legacy recommendation — display only, cannot apply". The Apply button is
relabelled **"Apply Pit Crew recommendation"** and hidden unless status ∈
APPROVED_STATUSES AND approved changes present AND not legacy.

### Response JSON contract
Per-change explainability keys live **inside each item** of the `changes` list:
symptom, evidence (list), rule_id, rationale, rejected_alternatives (list),
risk_level (low/med/high), confidence_level (low/med/high), driver_style_alignment
(aligned/neutral/caution). New top-level keys: `ai_audit`, `deterministic_plan`
{proposed_count, rejected_candidate_count, protected_fields}, `protected_fields`.

## 11. Tests

136 new tests across `tests/test_group42_rule_first_engine.py`,
`test_group42_ai_audit_only.py`, `test_group42_driver_style.py`,
`test_group42_legacy_storage.py`, `test_group42_handling_phases.py`,
`test_group42_voice_path_safety.py`, `test_group42_ui_gate.py` — plus 17
rewritten tests in `test_group38_setup_diagnosis.py`
(TestRegenerateOnceOrchestration), `test_group40_diagnosis_hardening.py`
(TestAC9DeterministicFallback), `test_group41_validation_gate.py` (2 tests),
`test_group27_setup_overhaul2.py` (1 test). All green.

The 8 pre-existing frozen-allowlist track-modelling failures are unrelated and
untouched, zero new regressions. **Test-run note (Windows / Python 3.14):** run
the suite in halves to avoid a flaky native PyQt teardown segfault — an
environmental test-isolation artifact, not a product defect.

## 12. Deferred / limitations

* `RuleOutcomeStore` live wiring + cross-session persistence — foundation only
  today (`rule_outcome_store=None`).
* The remaining per-setting Pack C rules — C/D is a handling-phase starter set,
  extensible via `register_pack`.
* Full DB migration off the recommendation_text JSON blob (the 8 v11 columns are
  populated, but the blob is still the primary store).
* Full rule-first rebuild of the voice path — constrained to narration-only for
  now.
* The 8 pre-existing track-modelling allowlist failures remain for the
  track-modelling owner.
