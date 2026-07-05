# Setup Brain Upgrade — Professional Race Engineer Diagnosis

> Author: Setup Brain Upgrade sprint · Date: 2026-07-05
> Branch: `ofr2-quali-race-disciplines` (built on top of the OFR-2 work)
>
> Companion docs: `docs/OFR2_SEPARATE_DISCIPLINES.md`,
> `docs/SMART_RACE_ENGINEER_ROADMAP.md`. Backend-only — no UI surface yet.

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
