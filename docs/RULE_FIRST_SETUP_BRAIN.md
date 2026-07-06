# Rule-First Setup Brain — Architecture (Group 42 + Group 43 + Group 44 + Group 45)

> Author: Rule-First Setup Brain sprint · Date: 2026-07-05 (Group 42); updated 2026-07-05 (Group 43); updated 2026-07-06 (Group 44 — from-scratch baseline generator); updated 2026-07-06 (Group 45 — Setup Brain Intelligence Expansion)
> Branch: `ofr2-quali-race-disciplines` (built on top of Group 41)
>
> Companion docs: `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 42 changelog, § Group 45
> intelligence-expansion detail), `docs/UAT_SETUP_BRAIN.md` (manual UAT),
> `MASTER_TESTING_REGISTER.md` (Rule-First Setup Brain (Group 42), Setup Brain
> Intelligence Expansion (Group 45)).
>
> This is the architecture doc. It explains *why* the AI is no longer the source
> of truth, how the deterministic rule engine works, and the contracts that keep
> the AI from ever authoring a setup change.
>
> **Group 45 added context-awareness on top of this architecture — see the
> dedicated section "Setup Brain Intelligence Expansion" (§14) at the end. The
> core inversion (rule-first, AI audit-only, single funnel) is unchanged.**

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

* **`RuleOutcomeStore` live wiring + cross-session persistence.** *(Group 45
  partially advanced this — see §14.)* Production now constructs a live-but-EMPTY
  store (the hook is wired), but it never fires without samples, and cross-session
  persistence + a success-recording feed remain deferred.
* **Individual `gear_1..gear_6` proposing rules.** B5 proposes `final_drive` on
  `gear_too_short`; **Group 45 added B5b** (`final_drive` up on `gear_too_long`).
  Rules for individual `gear_1..gear_6` slots are still deferred — the
  `per_gear_limiter_evidence` diagnosis key exists for future use, but broad
  final-drive-only logic is what ships today.
* **Tyre / fuel signals.** *(Group 45 partially delivered this — see §14.)*
  Tyre-wear is now read and **contraindicates** four tyre-abusing rules at high
  wear; the fuel multiplier is read but only informational (no fuel-specific rule
  yet). Tyre-compound signals remain unused.
* **`applies_session` / `applies_drivetrain` / `applies_car_class` scope
  enforcement.** **DELIVERED in Group 45** (`_scope_matches`, see §14) — the
  engine now filters at runtime; Pack A is exempt; `any`/`None` is
  wildcard-permissive.
* **Voice path.** The voice path is constrained to narration-only; a full
  rule-first rebuild of the voice path so it too is authored by the rule engine
  is deferred.
* **Remaining per-setting Pack C rules.** Pack C/D is a handling-phase starter
  set (C1–C8); more per-setting rules are deferred. The catalogue is extensible
  via `register_pack`.
* **Full DB migration off the JSON blob.** The 8 v11 columns are populated, but
  `recommendation_text` is still the primary store.
* **Car-specific / drivetrain-specific rule packs.** **Group 45 added the first
  car pack (Pack P — Porsche 911 RSR '17, see §14)** and enforces
  drivetrain/car-class scope. Broader per-car packs are still deferred.
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

---

## 14. Setup Brain Intelligence Expansion (Group 45)

> Date: 2026-07-06 · Branch `ofr2-quali-race-disciplines` (on top of Group 44).
> This is the dedicated, honest account of the intelligence added in Group 45.
> Cross-referenced from `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 45, which carries
> the Pack P / B5b / tyre-wear-contraindication changelog detail).
>
> **`RULE_ENGINE_VERSION` is now "45.0"** (was "42.0").

### 14.0 What did NOT change (architecture preserved)
The rule-first inversion is intact. Pit Crew still owns the decision; the AI is
still **audit-only** (`parse_audit_response` strips canonical params;
`map_audit_to_finaliser` never un-blocks; the voice path is narration-only). Both
the Analyse path and the Group 44 Baseline path still run through the **one**
validator → `_finalise_recommendation` funnel → renderer → Apply gate. The old
"Build Setup with AI" path stays disabled. **Everything works with the AI
disabled.** Group 45 is a *context and confidence* layer on top — it does not
change *who* authors setups.

### 14.1 What new intelligence was added
The engine now consumes **session type, tyre-wear, fuel, drivetrain, and
car-class** context. This context genuinely changes:
- **which rules are eligible** (scope filter, §14.3),
- **how confident** an eligible rule is (session bias, §14.5),
- **how candidates are ranked** when they tie (driver-profile active weighting,
  §14.4),
- **which rules are suppressed** at high tyre-wear (contraindication, §14.5),
- **how each change is explained** (explainability fields, §14.9).

**Crucially, delta magnitudes are UNCHANGED.** Context never invents a more
precise number — it filters, ranks, confidence-shifts, contraindicates, and
explains. This is deliberate: the app has no data to justify finer magnitudes, so
it does not fake them.

### 14.2 What inputs are genuinely used
- **Session type** — resolved from the analysed session's `purpose` → `SessionType`
  (quali / race / endurance; endurance = race + `duration_mins>=60`).
- **Tyre-wear** — `EventContext` tyre_wear → `tyre_wear_multiplier`; at
  `>= HIGH_TYRE_WEAR_THRESHOLD (5.0)` sets `diagnosis["tyre_wear_high"]`.
- **Fuel multiplier** — **READ** (`fuel_known` flag) but currently **only
  informational**. No fuel-specific rule fires. Documented honestly.
- **Car class** — `car_specs.json.category` → `CarClass` (available for **579
  cars**).
- **Drivetrain** — **NOT reliably in per-car data.** Resolved by precedence:
  explicit UI combo > `CAR_DRIVETRAIN_OVERRIDES` (in-module dict, currently
  `{"Porsche 911 RSR (991) '17":"rr"}`) > empty DB → `None` (generic). Unknown
  drivetrain → generic logic + an honest "drivetrain unknown — generic logic
  applied" note.

Context is resolved in `strategy/driving_advisor.py`: the Analyse path reads
`_event_ctx` plus the new `purpose` / `car_specs.category` / `drivetrain` params;
the Baseline path receives **scalar** params only (`session_type`,
`tyre_wear_multiplier`, `car_class`) — **no `EventContext` is injected into the
baseline author**. Both UI analyse handlers (`_setup_analyse_ai`,
`_setup_analyse_ai_for_form`) and both baseline callers thread these.

### 14.3 The engine scope filter (`_scope_matches`)
Rules already carried `applies_session` / `applies_drivetrain` /
`applies_car_class` (set since Group 42) but the engine **ignored** them. Group 45
enforces them at runtime:
- `any` / `None` on either the rule or the context = **wildcard-permissive** —
  an unknown context **never** filters a rule out (missing data must not silently
  drop safe advice).
- **Pack A safety rules are EXEMPT** from scope filtering — safety invariants
  always apply.
- If *every* rule is filtered out, the engine returns a **valid empty
  `SetupPlan`** (it never raises).

`applies_drivetrain` ∈ {fr, ff, mr, rr, awd}; `applies_car_class` ∈
{gr1..gr4, road, race}.

### 14.4 How driver style is now active
Driver style became a data structure in Group 42, but only shaped
contraindication text. Group 45 makes it an **active ranking input**: a bounded
**{−1, 0, +1} rank bonus** used as a **conflict-resolution tiebreaker when two
candidates have equal confidence**:
- all `rule.driver_style_tags ⊆ profile.style_tags` → **+1**;
- `dislikes_snap_exit` + a proposed lsd_accel **increase** → **hard block + −1**.

Again, **magnitudes/deltas are unchanged** — the bonus affects ranking /
confidence / explanation only. On the Baseline path, `_PROFILE_BIAS_TABLE`
gained `trail_braker` → brake_bias −0.5 and `rotation_without_snap` → lsd_decel
−2 (absolute-value baseline biases, driver-profile-driven only).

### 14.5 How session type and tyre/fuel settings affect recommendations
**Session type biases confidence** (not magnitude):
- **quali** upgrades the confidence of front-bite / trail-braker-tagged rules;
- **race** upgrades safety-phase / consistency rules;
- **endurance** = race behaviour + `duration_mins>=60`.

**Tyre-wear contraindicates (suppresses) rules that abuse worn tyres.** At
`tyre_wear_multiplier >= 5.0`, `diagnosis["tyre_wear_high"]` is set and these
**four genuinely tyre-abusing** rules are suppressed:
- **B3** — lsd_accel decrease,
- **C1_entry_lsd_decel** — lsd_decel decrease,
- **C3_mid_arb_rear** — rear ARB soften,
- **C7_kerb_arb_rear** — rear ARB soften.

Rules that **increase** lsd lock or rear downforce are deliberately **NOT**
suppressed — they stabilise worn tyres, so suppressing them would be wrong.

**Honesty gate:** when tyre/fuel context is missing, the change carries the
explicit "tyre/fuel context not available — conservative default applied" note
and makes **no** tyre/fuel-aware claim. The **fuel multiplier is read but only
informational** — there is no fuel-specific rule yet.

### 14.6 How car / drivetrain modifiers work
`applies_drivetrain` and `applies_car_class` filters (§14.3) let rules target a
drivetrain or class. Car class is reliable (`car_specs.json.category`, 579 cars);
**drivetrain is not reliably in per-car data** — it comes from the manual UI
combo or `CAR_DRIVETRAIN_OVERRIDES`, and an unknown drivetrain falls back to
generic logic with an honest note. This is why the Porsche pack asserts its
drivetrain via the override map (§14.7) rather than trusting the empty DB column.

### 14.7 What the Porsche 911 RSR '17 pack (Pack P) does
Registered via `register_pack("P", ...)`.
- **Rule P1** — a **cautious lsd_accel increase (traction-first)**, scoped
  `applies_drivetrain=rr` + `applies_car_class=gr3`, precondition snap-throttle
  wheelspin, **contraindicated when `snap_oversteer_exit` is diagnosed**.
- **No P2.** Rear-downforce protection under rear instability is already provided
  by existing **Pack A A2** (unconditional, all cars), so a separate Porsche P2
  was **intentionally omitted** — A2 covers it. Ride-height raise is gated by
  existing A3/A4 (no generic raise). A top-speed deficit under wheelspin is
  handled **traction-first** (P1), not aero-cut-first (A2 blocks the cut).
- **Labelling.** Every change is tagged `source_label` "Porsche-specific rule"
  (pack `P`) or "generic rule".
- **Drivetrain assertion.** The pack asserts RR via `CAR_DRIVETRAIN_OVERRIDES`
  (it does **not** rely on the empty DB drivetrain column); the manual UI combo
  overrides it.

### 14.8 What gearbox logic exists
- **B5** — `gear_too_short` → `final_drive_down`.
- **B5b (NEW)** — `gear_too_long` → `final_drive_up`.
- `limiter_limited` stays a **preserve** category (no proposal).
- **"limiter_before_braking" is NOT a real diagnosis category** — the sprint's
  wording maps it onto the existing `gear_too_short`. Documented, not faked.
- Diagnosis exposes **`per_gear_limiter_evidence`** (an alias of
  `rev_limiter_by_gear`). Individual `gear_N` changes are only ever proposed with
  gear-specific evidence — but **full per-gear rules remain DEFERRED**; today the
  logic is broad, final-drive-only.
- **Monotonic ordering is enforced NON-INCREASING:** equal adjacent ratios are
  **allowed**; only a strict inversion is rejected with reason "monotonic
  ordering violation". The engine AND the `gearbox_ratio_inversion` validator both
  use strict `>` now (in agreement — this is one of the three reconciled tests).

### 14.9 Explainability fields
Each approved change **and** each rejected candidate now carries, in addition to
the pre-existing symptom / evidence / rule_id / rationale / risk_level /
confidence_level / driver_style_alignment:

| Key | Meaning |
|-----|---------|
| `source_label` | e.g. "Porsche-specific rule" / "generic rule" (Analyse); `_LABEL_NEUTRAL` / `_LABEL_BIASED` / `_LABEL_MIDPOINT` / `_LABEL_CONSERV` (Baseline) |
| `session_influence` | how the session type affected this change — or the neutral "not session-tuned" string |
| `car_drivetrain_influence` | how car class / drivetrain affected it — or "drivetrain unknown — generic logic applied" |
| `pack` | the rule pack that authored it (A / B / C / P) |

**Populated honestly:** a positive session/tyre/car claim appears **only** when
that context was received AND used; missing context yields the explicit
neutral / "not available" string. **Baseline changes never claim telemetry
evidence**, and their `session_influence` text records that a session was *noted*
but the baseline is **NOT session-tuned** (session-specific numerical baseline
tuning is deferred; baseline bias is driver-profile-driven only). The renderer
shows a small `source_label` row.

### 14.10 What learning does — and does NOT do
Production now constructs a **live-but-EMPTY `RuleOutcomeStore`** (was `None` in
Group 42). The confidence-downgrade hook (§4) is therefore **wired**, but with no
samples it **never fires** — behaviour is unchanged. The response carries
`_learning_note` "no cross-session learning history available".

Learning **can only** lower a confidence label / affect ranking. It **CANNOT**:
- un-block a blocking safety rule,
- un-reject a rejected change,
- bypass validation,
- make the AI actionable.

**Deferred:** cross-session persistence of the store, and a success-recording
feed (e.g. from OFR-1 `recommendation_scoring` verdicts) to populate it.

### 14.11 Still deferred after Group 45 (honest)
- Cross-session `RuleOutcomeStore` persistence + a success-recording feed (seam in
  place, empty in production — no behaviour change yet).
- Full per-gear individual ratio proposal rules (`per_gear_limiter_evidence` key
  exists for future use; broad final-drive-only logic today).
- Session-specific **numerical** baseline tuning (session context is recorded on
  baseline changes but does not yet change baseline values).
- A fuel-specific rule (the fuel multiplier is read but only informational).
- The two opposing lsd_decel baseline bias entries
  (`race_values_consistency` +2 vs `rotation_without_snap` −2) **net to zero** on
  a driver profile that carries both flags.

### 14.12 Tests
NEW: `tests/test_group45_engine_scope.py`, `test_group45_gear_monotonic.py`,
`test_group45_context_signals.py`, `test_group45_porsche_pack.py`,
`test_group45_explainability.py`, `test_group45_learning.py`,
`test_group45_baseline_context.py`, `test_group45_ui_context.py`. **Three**
existing tests were reconciled for legitimate behaviour changes:
`RULE_ENGINE_VERSION` "42.0"→"45.0"; the baseline lsd_decel bias now nets
differently with `rotation_without_snap`; the gearbox inversion validator now uses
strict `>` (allowing equal ratios). All Group 45 tests pass; the ~18 pre-existing
frozen-allowlist / schema failures are known, unrelated, and untouched. Run the
suite in halves on Win/Py3.14. See `MASTER_TESTING_REGISTER.md` (Setup Brain
Intelligence Expansion (Group 45)) for the per-file coverage table.
