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
