# Rule-First Setup Brain — Architecture (Group 42 + Group 43 + Group 44)

> Author: Rule-First Setup Brain sprint · Date: 2026-07-05 (Group 42); updated 2026-07-05 (Group 43); updated 2026-07-06 (Group 44 — from-scratch baseline generator)
> Branch: `ofr2-quali-race-disciplines` (built on top of Group 41)
>
> Companion docs: `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 42 changelog),
> `docs/UAT_SETUP_BRAIN.md` (manual UAT), `MASTER_TESTING_REGISTER.md`
> (Rule-First Setup Brain (Group 42)).
>
> This is the architecture doc. It explains *why* the AI is no longer the source
> of truth, how the deterministic rule engine works, and the contracts that keep
> the AI from ever authoring a setup change.

---

## 1. Why AI is no longer the source of truth

Groups 38–41 made the AI's setup output progressively *safer*: a
diagnosis-before-AI layer, a professional race-engineer reasoning pass, and
finally (Group 41) a hard **engineering-validation gate** that blocked unsafe or
malformed AI output before it reached the driver. But in all of those, **the AI
still authored the setup** — it decided *what* to change, and the app only
gated it afterwards.

That leaves two problems the gate cannot solve:

* **Safety by omission.** A gate can only reject what it has a rule for. If the
  AI hallucinates a plausible-looking change the validator has no rule against,
  it passes. The validator is a net with holes; the AI is free to fish through
  them.
* **Consistency.** The same car, track, telemetry, and driver feedback could
  produce different setups on different runs, because an LLM is non-deterministic
  and prompt-sensitive. That undermines trust and makes the between-race learning
  loop (OFR-1) hard to reason about.

**Group 42 inverts the responsibility.** A deterministic **rule engine** now
authors the setup from the diagnosis, the driver profile, and an explicit
catalogue of race-engineering rules. The AI is demoted to an **audit-only**
layer: it can approve, warn, reject, or ask for more data, but it **cannot author
an actionable setup change**. The result:

* **Deterministic** — same inputs, same plan, every time.
* **Driver-aligned** — the driver profile is a first-class input to ranking and
  contraindication, not just prompt flavour text.
* **Explainable** — every proposed change carries its symptom, rule id,
  rationale, evidence, rejected alternatives, risk, confidence, and driver-style
  alignment.
* **Safe by construction** — the AI cannot introduce a change the engine did not
  author, because the audit parser structurally strips any setup field key from
  the AI response.

**The app now has ONE source of truth for actionable setup recommendations: the
deterministic rule engine.**

---

## 2. The flow

The canonical builder is `build_combined_setup_response` (the Setup Builder
"Analyse" path):

```
diagnose (build_setup_diagnosis)
  → build_driver_profile()
  → run_rule_engine()  →  SetupPlan
  → plan_to_raw_data  →  _normalise_changes
  → validate_setup_engineering_structured
  → if blocking:  _build_deterministic_fallback   (NOT the AI)
    else if API key present:  call_api  →  AI AUDIT ONLY
                              → parse_audit_response  (strips canonical setup keys)
                              → map_audit_to_finaliser
  → _finalise_recommendation   (the unchanged single funnel from Group 41)
  → response JSON
```

Two things to notice:

1. **When engineering validation blocks, the fallback is deterministic** —
   `_build_deterministic_fallback`, not another AI round. The AI is never asked
   to "try again" to author a setup.
2. **The AI call is only reached when the plan already validates clean.** The AI
   audits an already-safe deterministic plan; it never rescues an unsafe one.

The final funnel `_finalise_recommendation` is unchanged from Group 41 — the
rule-first work feeds it, it does not replace it.

---

## 3. The setup knowledge base (`strategy/setup_knowledge_base.py`)

The rule catalogue. Public surface: `register_pack`, `get_all_rules`,
`resolve_delta`. Enums: `RulePhase`, `RiskLevel`, `ConfidenceLevel`,
`DrivetrainType`, `CarClass`, `SessionType`. NamedTuples: `SetupRule`,
`SetupEvidence`.

### SetupRule
A `SetupRule` describes, deterministically, when a rule fires and what it
proposes — the phase it belongs to, the symptom/condition it responds to, the
target setup field, the delta to apply, its base risk and confidence levels, and
its driver-style relevance. Delta resolution is a **named-string lookup** into
`_DELTA_RESOLVERS` (not a stored callable), which keeps the catalogue
serialisable and inspectable — a rule is data, not code.

### The 22 rules — three packs
* **Pack A (A1–A8) — safety invariants.** These protect fields and block unsafe
  deltas. Pack A is why the engine can guarantee it will not, for example, cut a
  field a driver protects or exceed a safe delta on a sensitive setting.
  **Group 43 re-keyed A2, A3, A4, A5 to fire on real diagnosis signals** (see §3a).
* **Pack B (B1–B6) — driver-style adaptation.** These rank candidate changes and
  contraindicate against the driver profile (§5).
  **Group 43 re-keyed B5** to fire on real diagnosis signals + real gearbox gate (see §3a).
* **Pack C/D — handling-phase starter set (8 rules):**
  `C1_entry_lsd_decel`, `C2_entry_brake_bias`, `C3_mid_arb_rear`,
  `C4_mid_rear_aero`, `C5_exit_lsd_accel`, `C6_exit_rear_aero`,
  `C7_kerb_arb_rear`, `C8_kerb_rh_rear`. These cover the entry / mid / exit / kerb
  handling phases. **The remaining per-setting Pack C rules are deferred** — the
  catalogue is deliberately **extensible via `register_pack`**, so additional
  packs can be registered without touching the engine.

---

## 3a. Group 43 — re-keyed rules (real diagnosis signals)

Group 42 shipped with A2/A3/A4/A5/B5 wired to fictional `*_evidence` or
`"too_short"` keys that `build_setup_diagnosis` never emits.  Group 43 re-keys
all five to the **actual signals** the diagnosis dict produces.

### A2 — protect `aero_rear`
Preconditions (re-keyed, Group 43): fires when
`driver_feel_flags.rear_loose_on_exit` is True **OR**
`driver_feel_flags.snap_oversteer_exit` is True (via `__any__` list form).
Firing yields a `rejected_candidate` for `aero_rear` — rear downforce
must not be cut under instability.
No distinct high-speed-oversteer diagnosis signal exists in the current output;
that leg is omitted (deferred).

### A3/A4 — conditional protect `ride_height_front` / `ride_height_rear`
Precondition (unchanged): `bottoming_band == "minor"`.
Contraindications (re-keyed, Group 43): suppress the protection when
`bottoming_confidence.band` ∈ `{"consider","required"}` (via
`__in_consider_required__`) **OR** `compliance_priority` is True.
When the protection fires the field is added to `protected_fields`, preventing
any other rule from proposing a ride-height increase.
When a contraindication matches, the protection is suppressed and C8 may
propose the raise.
No real `aero_platform_evidence` key exists; that leg is omitted (deferred).

### A5 — protect `brake_bias`
Preconditions (re-keyed, Group 43): fires when
`driver_feel_flags.braking_instability` is True **OR** `avg_lockups > 0`
(via `__any__` truthiness — 0/0.0 is falsy, so no fire on clean laps).
Firing yields a `rejected_candidate` for `brake_bias` (rearward move blocked).
`driver_feel_flags.braking_instability` is the available proxy for both entry
and rear-brake instability; a distinct entry-oversteer signal is deferred.

### B5 — propose `final_drive` (gear_too_short path)
Preconditions (re-keyed, Group 43): fires when **both** of the following match:
- `gearing_diagnosis_category == "gear_too_short"` (telemetry confirms rev-limiter
  hits in the top gear on straights)
- `gearbox_flag == "may_change"` (engineering gate allows gearbox edits;
  `None` / `"preserve"` / other values do not match this exact precondition)

Delta resolver: `final_drive_down` (returns **−0.05**). Lower final_drive ratio
number = taller/longer gearing = higher top speed. Direction is correct for
`gear_too_short`.

Self-consistency: `gear_too_short` is **not** in the engineering validator's
preserve set `{"insufficient_data", "gear_too_long", "limiter_limited"}`, so
a `final_drive` change on this diagnosis + `gearbox_flag="may_change"` passes
the `gearbox_category_mismatch` validator.

### "Build Setup with AI" button — disabled (Group 43)
The **"Build Setup with AI"** button in the Setup Builder tab is **disabled**
(frontend parallel change). The reason: the ungated AI path — where AI authors
a setup without a rule-first baseline — is pending replacement. Since Group 42,
the AI is **audit-only** and cannot author setup changes. Until the rule-first
baseline is the stable default path for all setup requests, the "Build" button
is disabled to prevent the old AI-authoring flow from being reached accidentally.
The "Analyse" button (rule-first path) remains active.

---

## 3b. Group 44 — the from-scratch baseline generator (a second rule-first authoring path)

Group 43 disabled the ungated **"Build Setup with AI"** path (§3a), and since
Group 42 the AI is audit-only and structurally cannot author a setup. That left a
real gap: for a car with **no telemetry at all**, the app could no longer produce a
complete starting setup. **Group 44 restores that capability — deterministically,
with the AI NEVER called.**

### Why not `run_rule_engine`?
The Analyse path's engine (§4) emits **deltas** off a telemetry diagnosis. With no
telemetry, almost no rules fire, so it cannot author a from-scratch full-field
setup. A separate **absolute-value author** was required. This is a *distinct
authoring path* from the delta/Analyse path — the two do not share the rule engine,
but they share the same finaliser, validator, response shape, UI renderer, and
Apply gate.

### Backend — `strategy/setup_baseline.py` (NEW)
* **`NEUTRAL_SEEDS`** — the single source of truth for neutral physics defaults.
  It matches the form seeds in `ui/setup_form_widget.py` (note: lsd_front_initial /
  accel / decel take the FORM values 10 / 15 / 5, which differ from the `ai_planner`
  parser fallbacks 0 / 0 / 0).
* **`build_baseline_setup(car, ranges, drivetrain, num_gears, profile,
  allowed_tuning, tuning_locked) -> raw_data dict`** (the same `plan_to_raw_data`
  shape the funnel consumes). It authors **all 33 actionable
  `_CANONICAL_SETUP_PARAMS`** (34 minus the display-only
  `transmission_max_speed_kmh`) as **absolute values**, in three stages:
  neutral seed → **driver-profile bias** (`_PROFILE_BIAS_TABLE`) → **clamp** to
  `resolve_ranges(car)`.
* **`_PROFILE_BIAS_TABLE`** (§5 driver profile as data, applied to a from-scratch
  baseline): prefers_rear_stability → arb_rear −1 / toe_rear +.05; dislikes_snap_exit
  → lsd_accel −2; prefers_front_bite → arb_front +1 / toe_front −.02;
  dislikes_floaty_front → aero_front +50; protects_downforce → aero_rear +50;
  race_values_consistency → lsd_decel +2.
* **Gearbox** (`_build_gearbox_changes`): `final_drive` = midpoint of
  `_FINAL_DRIVE_RANGE (2.5, 6.0)`; `gear_1..gear_num_gears` = a strictly-**decreasing
  geometric sequence** inside `_GEAR_RATIO_RANGE (0.5, 4.0)` — **monotonic by
  construction, so the `gearbox_ratio_inversion` validator can never fire** — sized
  to the car's gear count (>6 capped, ≤1 → a single gear@2.0, 0 → none). The gearbox
  ranges are function-local-imported from `setup_diagnosis` (the source of truth),
  with a try/except fallback to local constants.
* **Locked categories** (via `_derive_locked_fields`) are excluded from the
  actionable output and named by human category (e.g. "Suspension, Aero") in the
  analysis text; `tuning_locked=True` → empty changes (and the UI disables the
  button first anyway).
* Every change carries a **source label**: "neutral default" / "range midpoint" /
  "driver-profile biased" / "conservative default, not diagnosed". The last label is
  deliberately honest — camber / toe / dampers / springs / lsd_initial /
  lsd_front_initial have **no engineering authority** here. The baseline is a safe
  **starting point, not an optimum.**

### Orchestrator — `DrivingAdvisor.build_baseline_setup_response(...)`
`build_baseline_setup_response(car_name, ranges, drivetrain, num_gears,
allowed_tuning, tuning_locked, session_type="Race") -> JSON str`:

```
build_driver_profile()
  → build_baseline_setup
  → validate_setup_engineering_structured
       (the neutral baseline is passed as BOTH the `setup` arg AND the proposed
        setup_fields, so increment / comparison rules see zero delta)
  → _filter_baseline_artifact_warnings
  → _finalise_recommendation            (the same Group 41 funnel)
  → response JSON  (identical in shape to build_combined_setup_response)
```

**The no-AI guarantee:** this path reads **no api_key**, calls **no `call_api`**,
and runs **no audit**. A clean neutral baseline returns status `"approved"` with
`validation_warnings == []`.

### The warning-filter (`_filter_baseline_artifact_warnings`)
A full-field baseline where the proposed setup **equals** the current setup trips
two *definitional* validator artifacts: some rules flag a change as "is a no-op",
and the full field count trips "too many changes". These are meaningless for a
from-scratch baseline. `_filter_baseline_artifact_warnings` drops **only**
WARNING-severity failures whose message contains `"is a no-op"` or
`"too many changes"`.

The safety property is structural: the severity guard `if vf.severity ==
"warning"` is the **outer** condition, so the filter is **proven unable to suppress
a blocking failure** — every blocking failure passes through unfiltered and still
forces `validation_failed` / the fallback exactly as on the Analyse path.

### Frontend
A new **`_btn_baseline` "Build Baseline Setup"** button (enabled + visible; added
to `_RACE_ALIASES`) lives in `ui/setup_form_widget.py` + `ui/setup_builder_ui.py`,
**separate from** the still-disabled Group 43 `_btn_build_setup`. Handlers
`_generate_baseline_setup` / `_generate_baseline_setup_for_form` run on a daemon
thread → `_baseline_result_queue` in `ui/dashboard.py` (polled) →
`_display_baseline_result` re-enables the baseline button then **delegates to the
shared `_display_setup_result` renderer + Apply gate** (no duplication). The Group
43 `_btn_build_setup` / `_run_build_setup*` guards are untouched.

### Honest limitations (Group 44)
* `_btn_baseline` is enabled-at-construction with a **runtime car/track guard** (no
  proactive disable) — consistent with `_btn_analyse_setup`; the shared renderer
  also re-enables `_btn_analyse_setup` after a baseline (harmless).
* The symptom label `"no telemetry baseline"` is generic even on the
  driver-profile-biased fields.
* The no-authority fields (camber / toe / dampers / springs / lsd_initial /
  lsd_front_initial) are **conservative defaults, not engineered values.**
* The old `build_car_setup` AI-authoring path remains **dead-in-tree** behind the
  Group 43 guards.

---

## 4. The rule engine (`strategy/setup_rule_engine.py`)

`run_rule_engine(diagnosis, setup, ranges, profile, allowed_tuning=None,
rule_outcome_store=None) -> SetupPlan`.

NamedTuples: `SetupChangeIntent` (one proposed change) and `SetupPlan` (the
authored plan — proposed intents, rejected candidates, protected fields).

The engine:
* fires the catalogue rules against the diagnosis + current setup;
* applies **Pack A** to protect fields (a protected field can never be authored
  as a change);
* runs **conflict resolution** — when two candidates target the same field in
  opposite directions, **both** move to the rejected list with reason
  `conflict:<id>` (the engine refuses to guess);
* excludes **no-ops** (a change that would not move the value);
* applies **gear-count gating** (do not propose gear ratios a car does not have);
* applies the **confidence-downgrade hook** (§6).

It **never raises** — any internal error yields an empty plan, so a setup request
can always be finalised.

### Confidence model
Each rule carries a **base confidence** (`ConfidenceLevel`). The engine can
**downgrade** a rule's confidence by one step when the (optional)
`RuleOutcomeStore` reports that the rule has fired enough times to judge and has
been underperforming:

* `samples >= MIN_OUTCOME_SAMPLES` (`3`) — enough history to judge, AND
* `success_rate < LOW_SUCCESS_RATE` (`0.40`) — the rule has been going badly

→ downgrade this rule's proposed change one confidence step. Below
`MIN_OUTCOME_SAMPLES`, `get_success_rate` returns `None` and no downgrade is
applied (the engine never punishes a rule on thin evidence).

`RuleOutcomeStore` holds fire/success counts keyed by
`rule_id / car / track / driver_profile_version`.

---

## 5. The driver profile as data (`strategy/setup_driver_profile.py`)

`DriverProfile` NamedTuple + `DriverStyleAlignment` enum
(`aligned` / `neutral` / `caution`).

`build_driver_profile()` derives a set of **booleans** from the existing
`PERSONAL_DRIVER_TUNING_MODEL` / `DRIVER_HARD_CONSTRAINTS` constants:

* `prefers_front_bite`
* `dislikes_floaty_front`
* `dislikes_snap_exit`
* `trail_braker`
* `rotation_without_snap`
* `prefers_rear_stability`
* `protects_downforce`
* `race_values_consistency`

It **never raises** — on any error it returns neutral defaults.

The key architectural change: **driver style is now a data structure**, consumed
by the engine for ranking (which safe change to prefer) and **contraindication**
(a change the driver dislikes is downranked or rejected, and tagged
`driver_style_alignment: caution`). Previously the driver style existed only as
prompt text handed to the AI; now it deterministically shapes the plan.

---

## 6. The AI audit role (`strategy/setup_ai_audit.py`)

`AuditStatus` enum: `APPROVED`, `APPROVED_WITH_WARNINGS`, `REJECTED`,
`NEEDS_MORE_DATA`. `AuditResult` NamedTuple.

### Audit-only, by construction
* **`build_audit_prompt`** renders **8 labelled sections**: diagnosis, plan,
  evidence, rules-fired, rejected candidates, protected fields, current setup,
  driver profile — plus the validation result and the audit instructions. The AI
  is asked to *judge* the deterministic plan, not to write one.
* **`parse_audit_response(response_text, canonical_params)`** is the structural
  guarantee. It **strips any key present in `canonical_params`** (the canonical
  setup field names) from the AI's response and logs them as `stripped_fields`.
  An unknown/garbled status maps to `NEEDS_MORE_DATA`. It **never raises.** This
  is *why* the AI cannot author a setup change — even if it tries to emit a setup
  field, that field is removed before anything downstream sees it.

### The four statuses and `map_audit_to_finaliser`
`map_audit_to_finaliser` translates the audit verdict into the Group 41
finalisation lifecycle:

* `APPROVED` / `APPROVED_WITH_WARNINGS` → the deterministic plan proceeds, with
  any AI concerns attached as warnings.
* `REJECTED` / `NEEDS_MORE_DATA` **with no blocking engineering failure** → the
  deterministic plan is still surfaced as an **`approved_with_warnings`
  advisory** (`ai_audit_rejected_advisory`). The AI's objection is shown to the
  driver, but the safe deterministic plan is not thrown away on the AI's say-so.
* **A blocking engineering failure ALWAYS wins.** If engineering validation
  blocked, the audit verdict cannot un-block it — the recommendation is
  `validation_failed` / handled by the deterministic fallback regardless of what
  the AI said.

`AI_AUDIT_REJECTED_ADVISORY = "ai_audit_rejected_advisory"` is deliberately **not**
in `APPROVED_STATUSES`, and its history routes to the `_rejected_` diagnostic
bucket (§9).

---

## 7. The learning model (foundation only)

`RuleOutcomeStore` is the foundation of a rule-level learning loop. The
confidence-downgrade hook (§4) is **implemented and unit-tested**: a rule that
has fired enough times (`>= MIN_OUTCOME_SAMPLES`) with a low success rate
(`< LOW_SUCCESS_RATE`) has its proposed change's confidence downgraded one step.

This is a **deterministic weighted counter — there is no ML.** It counts fires
and successes and applies a threshold. That honesty matters: the app never
pretends to a learned model it does not have.

**What is deferred:** live wiring and cross-session persistence.
`build_combined_setup_response` passes `rule_outcome_store=None` today, so the
store is exercised only in tests. Wiring it to a real per-car/track/profile store
and persisting it across sessions is the next step in this line of work.

---

## 8. The response JSON contract

### Per-change explainability (inside each `changes` item)
Every item in the response `changes` list carries its own explainability keys:

| Key | Meaning |
|-----|---------|
| `symptom` | the diagnosed problem this change addresses |
| `evidence` | list — the telemetry/feedback evidence behind it |
| `rule_id` | the `SetupRule` that authored it |
| `rationale` | the engineering reason |
| `rejected_alternatives` | list — candidate changes the engine considered and rejected |
| `risk_level` | `low` / `med` / `high` |
| `confidence_level` | `low` / `med` / `high` (after any downgrade) |
| `driver_style_alignment` | `aligned` / `neutral` / `caution` |

### New top-level keys
* `ai_audit` — the audit verdict + concerns.
* `deterministic_plan` — `{proposed_count, rejected_candidate_count,
  protected_fields}`.
* `protected_fields` — the fields Pack A protected from change.

These feed the UI directly (§10) and are persisted to the DB v11 columns (§9).

---

## 9. Legacy safety and persistence

### Legacy-safety — closes Group 41's caveat
`data/setup_history.py` adds `is_legacy_unknown`, `normalise_validation_status`,
and the `LEGACY_UNKNOWN` sentinel. A recommendation whose status is
**absent / None / unrecognised** is now treated as **`legacy_unknown` =
DISPLAY-ONLY, NO Apply.**

Previously (through Group 41) an absent status could default to *approved* — an
old cached recommendation with no lifecycle status could therefore expose an
Apply path. That hole is now closed: the display code (`_display_setup_result`)
shows a legacy banner and the Apply button is gated off. The `_rejected_` bucket
routing is preserved (`ai_audit_rejected_advisory` routes there).

### DB v11
`data/session_db.py::_migrate_v11` bumps `user_version` to 11 and adds **8
nullable TEXT columns** to `setup_recommendations`:

`deterministic_plan_json`, `ai_audit_json`, `validation_status`,
`approved_changes_json`, `rejected_changes_json`, `diagnosis_json`,
`driver_profile_version`, `rule_engine_version`.

The existing `recommendation_text` JSON blob is preserved. The new columns are
**populated on insert** via `strategy/_rec_parser.py` +
`insert_setup_recommendations`. Full migration off the blob (making the columns
the primary store) remains deferred.

---

## 10. The voice-path constraint

The voice path (`build_setup_advice_response`) is constrained to
**narration-only** via a new `_strip_actionable_for_voice(data)` that zeroes
`changes=[]` / `setup_fields={}` before normalisation. The voice path can
therefore never surface an actionable setup change to apply — it can describe the
situation, but not hand the driver changes.

A full rule-first rebuild of the voice path (so it, too, is authored by the rule
engine) is **deferred**. Until then, the Setup Builder "Analyse" path is the one
place actionable rule-first recommendations are produced.

---

## 11. The UI

`ui/setup_builder_ui.py::_display_setup_result` + `ui/setup_form_widget.py`
render the response in this section order:

1. **Diagnosis**
2. **"Pit Crew recommendation"** — the approved deterministic changes. Each has a
   collapsed **"Why Pit Crew recommended this"** details block showing symptom /
   rationale / evidence / rejected_alternatives / risk_level / confidence_level /
   driver_style_alignment.
3. **"Protected fields (Pit Crew will not change these)"**
4. **"Rejected candidate changes (not applied)"**
5. **"AI audit"** — the AI verdict + concerns (never actionable changes).
6. **"Rejected AI output — not for use"**

A legacy recommendation shows the banner **"Legacy recommendation — display only,
cannot apply"**. The Apply button is relabelled **"Apply Pit Crew
recommendation"** and is **hidden** unless the status is in `APPROVED_STATUSES`
AND there are approved changes present AND the recommendation is not legacy.

The labelling deliberately separates **"Pit Crew recommendation"** (the
deterministic, applyable plan) from **"AI audit"** (commentary only), so the
driver can always see which is which.

---

## 12. Remaining limitations / deferred

* **`RuleOutcomeStore` live wiring + cross-session persistence.** The learning
  hook is implemented and tested but not wired live
  (`rule_outcome_store=None`) and does not persist across sessions yet.
  `RuleOutcomeStore` live wiring and cross-session persistence are deferred to
  a future sprint.
* **Individual `gear_1..gear_6` proposing rules.** B5 now proposes `final_drive`
  on `gear_too_short`; rules for individual `gear_1..gear_6` slots are
  deferred. The resolver foundation (`final_drive_down` / `final_drive_up`) is
  in place and extensible via `register_pack`.
* **Tyre signals.** `tyre`-compound / tyre-wear / fuel signals are not read by
  any rule (deferred; no dedicated tyre telemetry diagnosis keys exist today).
* **`applies_session` / `applies_drivetrain` scope enforcement.** These fields
  are set on rules but the engine does not yet filter by them at runtime
  (deferred; the fields are ready for the engine to honour once the scope
  enforcement work is scoped).
* **Voice path.** The voice path is constrained to narration-only; a full
  rule-first rebuild of the voice path so it too is authored by the rule engine
  is deferred.
* **Remaining per-setting Pack C rules.** Pack C/D is a handling-phase starter
  set (C1–C8); more per-setting rules are deferred. The catalogue is extensible
  via `register_pack`.
* **Full DB migration off the JSON blob.** The 8 v11 columns are populated, but
  `recommendation_text` is still the primary store.
* **No car-specific / drivetrain-specific rule packs.** Currently all rules
  default to `applies_drivetrain=any` / `applies_car_class=any` (deferred;
  per-car specificity once more data is in).
* **From-scratch baseline no-authority fields (Group 44).** camber / toe / dampers
  / springs / lsd_initial / lsd_front_initial are seeded from conservative neutral
  defaults, not engineered — the baseline is a safe starting point, not an optimum.
  Per-car gearbox ratio bounds (to promote `gearbox_out_of_range` to blocking) and
  track-type biasing of the baseline are deferred.
* **Pre-existing track-modelling failures.** The 8 frozen-allowlist guard tests
  (`ui/track_modelling_ui.py::_tm_restore_last_track`) are unrelated
  track-modelling tech debt and remain for the track-modelling owner.

---

## 13. Tests

136 new tests across `tests/test_group42_rule_first_engine.py`,
`test_group42_ai_audit_only.py`, `test_group42_driver_style.py`,
`test_group42_legacy_storage.py`, `test_group42_handling_phases.py`,
`test_group42_voice_path_safety.py`, `test_group42_ui_gate.py` — plus 17
rewritten tests (`test_group38` TestRegenerateOnceOrchestration, `test_group40`
TestAC9DeterministicFallback, `test_group41` ×2, `test_group27` ×1). All green,
zero new regressions. See `MASTER_TESTING_REGISTER.md` (Rule-First Setup Brain
(Group 42)) for the per-file coverage table.

**Group 43 note:** The B5 re-key changes the precondition from `gearbox_flag="too_short"`
to `gearing_diagnosis_category="gear_too_short" + gearbox_flag="may_change"`.
The Group 42 `TestB5GearingTooShortRule` tests inject the old `gearbox_flag="too_short"` value
and will need updating by the test-verifier to inject both new keys instead.
All Group 42 tests for A2/A3/A4/A5 that relied on the fictional `*_evidence` keys will
now correctly fire (or correctly not fire) on the real diagnosis signals.

**Group 44 note:** The from-scratch baseline generator (§3b) is covered by
`tests/test_group44_baseline_generator.py` (86 backend) +
`tests/test_group44_baseline_ui.py` (64 UI/integration) — full-field output,
the no-AI guarantee (no api_key / no `call_api` / no audit), the gearbox monotonic
guarantee (`gearbox_ratio_inversion` can never fire), transmission_max_speed_kmh
display-only, driver-profile bias, validator/funnel/Apply-gate routing, the Group
43 guard regression (`_btn_build_setup` still disabled), and
`_filter_baseline_artifact_warnings` (drops only the no-op / too-many-changes
WARNING artifacts, never a blocking failure). **406 green together with group41 +
group42 (all) + group43; 0 fail.** See `MASTER_TESTING_REGISTER.md` (Rule-First
Setup Baseline Generator (Group 44)).

**Test-run note (Windows / Python 3.14):** run the suite in halves to avoid a
flaky native PyQt teardown segfault — an environmental test-isolation artifact,
not a product defect.
