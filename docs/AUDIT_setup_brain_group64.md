# Setup Brain — Group 64 Root-Cause Report & Architecture

**Scenario:** the manual UAT after Group 63 still produced effectively identical Base,
Qualifying and Race setups, returned a lone `ARB Front 6.0 → 5.0` labelled "Setup
approved with notes / AI audit APPROVED_WITH_WARNINGS", showed contradictory bottoming
states (`required` in the header vs `NORMAL_OR_EXPECTED` in the impact panel), classified
weak wheelspin as `gear_too_short_spin`, and left proven same-car values decorating the
comparison table without reaching authoring.

This report is grounded in a four-thread production code trace (discipline propagation,
proven-history integration, recommendation-status/coherence, canonical diagnosis vs UI
render). File:line references are to `master` at the start of Group 64. Verdicts
(REAL / PARTIAL) are recorded per root cause.

---

## Cross-cutting theme

Group 63 repaired the *evidence pipeline* on the **incremental analyse path** (feedback
parsing, gearbox state, bottoming impact, LSD triplet, coherence-for-handling-dominants).
But two structural gaps survived, and both are what the UAT actually hit:

1. **There is no single deterministic authoring path that builds a COMPLETE,
   objective-specific, full-field setup.** The objective (base/quali/race) reaches the
   *incremental* path only as a rule-scope/label modifier; it changes no authored value,
   so when the plan collapses to one generic field the three disciplines render identical.
2. **Several "one canonical truth" and "safe ≠ complete" guarantees are enforced in the
   diagnosis layer but re-derived (or ignored) at the render / status layer.**

---

## RC1 — Discipline objective does not reach analyse-path authoring
`strategy/driving_advisor.py` (`build_combined_setup_response`), `strategy/setup_rule_engine.py`.

* The baseline path DOES diverge by discipline — `setup_baseline._SESSION_BIAS_TABLE`
  shifts up to 9 fields for qualifying (camber/toe/brake/lsd/aero/ride-height). **VERDICT:
  works.**
* The analyse path passes `session_type` into `run_rule_engine`, but it only gates rule
  *scope* (`_scope_matches`) and *confidence* (`_upgrade_confidence`) + label text — it
  changes **no numeric delta**. The candidate comparison (`driving_advisor.py:2358-2371`)
  projects the base/quali/race columns onto `_focus` = approved-fields ∪ history-prior
  fields, so when the only approved field is `final_drive`/`arb_front`, all disciplines
  collapse to that single value ("look identical", the RC-F.3 finding). **VERDICT: REAL.**
* There was **no** `SetupObjective` type, no single authoring context, and no full-field
  objective-specific plan. **VERDICT: REAL (architecture gap).**

## RC2 — Proven history reaches authoring only for camber/toe (baseline only)
`strategy/setup_history_intelligence.py`, `strategy/lsd_reasoning.py`.

* `build_baseline_seed_overrides` lifted only `BASELINE_LIFT_FIELDS = {camber_front/rear,
  toe_front/rear}` at tier ≤ 2 — the **LSD triplet was explicitly excluded** and never
  seeded any authored value. **VERDICT: REAL.**
* The LSD prior in `lsd_reasoning.build_lsd_triplet_assessment` is advisory-only (direction
  + controlled test), never merged into `setup_fields`. **VERDICT: REAL (by design, but the
  base never got a proven LSD start).**
* Analyse-path `compare_to_history` is reactive — it flags a field only when a recommended
  value already exists, so unflagged proven values are discarded. **VERDICT: REAL.**

## RC3 — Bottoming renders two contradictory states
`strategy/setup_diagnosis.py`, `ui/setup_builder_ui.py`.

* The UI "App diagnosis" header printed the raw count-based `bottoming_band` (`> 2.0/lap ⇒
  "required"`) at `setup_builder_ui.py:1691`, while Section 15 printed the consequence-graded
  `bottoming_impact.impact` (e.g. `NORMAL_OR_EXPECTED`) — **never reconciled**. Group 63
  fixed the dominance *gating* but left the header band raw. **VERDICT: REAL.**

## RC4 — Weak/unlocated wheelspin becomes `gear_too_short_spin`
`strategy/setup_diagnosis.py` (`_classify_wheelspin_subtype`).

* `_classify_wheelspin_subtype` (a **separate** function from the Group-63-fixed
  `_classify_gearing`) returned `gear_too_short_spin` on **any** lower-gear limiter hit with
  severe-ish wheelspin — **no location-confidence or per-gear gate**. A single intermediate-
  gear tap was enough, and the label then deferred all LSD-accel reasoning downstream.
  **VERDICT: REAL.**

## RC5 — "Safe" is treated as "complete"; gate holes
`strategy/driving_advisor.py` (`_finalise_recommendation`), `strategy/setup_diagnosis.py`,
`strategy/_setup_constants.py`.

* The coherence gate only checks the **single dominant** — confirmed **secondary** problems
  can be wholly untreated while status is `"approved"`. A bare `arb_front` satisfies the
  understeer-dominant addressing set → `"approved"` as the only change. **VERDICT: REAL.**
* `wheelspin` (a valid dominant key) never armed the gate. **VERDICT: REAL.**
* `partial_recommendation` is inside `APPROVED_STATUSES`; an AI `REJECTED` with no blocking
  constraint maps to `approved_with_warnings`; the AI can only upgrade, never veto
  completeness; there is no change-budget requiring completeness. **VERDICT: REAL.**

---

## Architecture implemented (Group 64)

| RC | Repair | Primary files |
|----|--------|---------------|
| — | **Canonical `SetupObjective` (BASE/QUALIFYING/RACE), immutable `SetupAuthoringContext`, documented `EVIDENCE_PRECEDENCE`, `FieldDisposition` (11 states), full-field `author_full_field_plan` + `author_discipline_setups`, objective-specific per-field justification** | **NEW `strategy/setup_authoring.py`** |
| RC1 | Discipline field-plan surface on the baseline response: authors Base/Quali/Race as separate full-field setups from ONE context, exposes per-field base/quali/race values + `differing_fields` + a disposition for every field | `driving_advisor.py`, `setup_authoring.py` |
| RC2 | `build_baseline_seed_overrides` now lifts the **LSD triplet** (personal-fit lever) — geometry at tier ≤ 2, LSD at tier ≤ 3 (transfers cross-track as a *starting window*); marked `PROVEN_HISTORY_SEED` | `setup_history_intelligence.py`, `setup_baseline.py` |
| RC3 | `_bottoming_display_state` reconciles band + impact into ONE canonical state (consequence governs); UI header reads it — "required" only when the impact is performance-relevant | `setup_diagnosis.py`, `ui/setup_builder_ui.py` |
| RC4 | `_classify_wheelspin_subtype` requires location-trustworthy, non-contradicted evidence before `gear_too_short_spin`; else `unknown` (→ controlled test) or `conflicting_evidence` | `setup_diagnosis.py` |
| RC5 | `RECO_*` recommendation-state vocabulary + `assess_recommendation_completeness`: a plan is complete only when EVERY active confirmed problem (incl. telemetry wheelspin + secondaries) is addressed by a change or covered by a targeted test; else downgraded to `partial_recommendation`. `wheelspin` now arms the finaliser gate. UI shows the completeness verdict + untreated list | `setup_diagnosis.py`, `driving_advisor.py`, `ui/setup_builder_ui.py` |

**Invariants preserved:** deterministic rule-first authoring; AI audit-only (never authors,
never validates invalid evidence, never bypasses Apply); no auto-Apply; no fabricated
telemetry/fuel/history; honest UNKNOWN; disabled AI-build stays disabled; Strategy-Brain
authority untouched; no schema migration (`RULE_ENGINE_VERSION` unchanged, `user_version`
14); runtime data files untouched (tests use fixtures).
