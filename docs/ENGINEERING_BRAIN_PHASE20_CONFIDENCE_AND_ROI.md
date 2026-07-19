# Engineering Brain — Program 2, Phase 20: Confidence-Weighted Evidence & Development ROI

**Status:** implemented on branch `eng-brain-phase20-confidence-and-roi` (from the Phase-19 tip `f95345e`). Committed locally; **not pushed; no PR; not merged; not live.**
**Schema:** **NO migration / NO persistence** — `DB_VERSION` stays **26**; `RULE_ENGINE_VERSION` unchanged (`46.0`). Everything reconstructs from existing records.
**Nature:** three deterministic, ADVISORY-ONLY analysis layers built *above* Phase 19. They answer: *how trustworthy are the conclusions we've drawn, and where is the greatest engineering return still available?* They **measure**; they decide nothing.

It is NOT a diagnosis / synthesis / ranking / lifecycle / campaign-completion / Apply authority — it OBSERVES the existing ones. It NEVER completes/freezes/abandons a campaign, applies/approves a setup, creates/updates experiments, alters outcomes, re-ranks experiments, recomputes the Phase-17 engineering value or the Phase-19 cost, or auto-prioritises anything. No AI/ML/stats/optimiser/Bayesian/network. The frozen Apply gate remains the sole setup-mutation route and is byte-for-byte unchanged; campaign completion remains governed by Phase 18.

## 1. Architecture position
```
... experiment portfolio valuation (P17) -> engineering campaigns (P18)
    -> evidence saturation + campaign persistence + cost model (P19)
    -> CONFIDENCE-WEIGHTED KNOWLEDGE QUALITY + DEVELOPMENT ROI + CAMPAIGN OPPORTUNITY (P20)
```
Phase 20 sits above Phase 19: it reads the Phase-19 Engineering Efficiency view (which itself reuses the Phase-18 programme once) + the Phase-11 prediction calibration, and layers confidence / ROI / opportunity. It writes nothing.

## 2. Reused authorities (consumed, never recreated)
Campaign evidence signals (confirmed/regressed/no-change/executed/conflicting/unresolved-mechanisms/remaining-*) = **Phase 18 progress** via **Phase 19 saturation.signals**; information gain remaining = **Phase 19 saturation**; per-campaign remaining cost (laps/tyres/minutes) = **Phase 19 cost model** (reused verbatim); prediction accuracy + contradiction counts = **Phase 11 calibration**; experiment engineering value = **Phase 17** (never re-derived). Phase 20 owns only: the confidence combination, the ROI arithmetic, and the opportunity classification.

## 3. Layer 1 — knowledge confidence (`strategy/knowledge_confidence.py`, pure)
- **`ConfidenceLevel`** — `UNKNOWN`, `VERY_LOW`, `LOW`, `MEDIUM`, `HIGH`, `VERY_HIGH`.
- **`assess_campaign_confidence(campaign_efficiency, calibration) -> KnowledgeConfidence`** — seven components, each a `ConfidenceComponent` carrying `score` (0..1 or None), `label`, `included_in_overall`, and a **reason / source / calculation** triple (no hidden maths): `confirmation_strength`, `repeatability`, `contradiction_level`, `mechanism_support`, `outcome_consistency`, `prediction_accuracy` (context-level; **excluded when uncalibrated** so it neither inflates nor deflates), `remaining_uncertainty` (informational; excluded — completeness ≠ correctness).
- **Overall** = the equal-weighted mean of the *included* components (weight 1.0 each, stated), banded by named constants (`CONF_BAND_VERY_HIGH/HIGH/MEDIUM/LOW`), then **visibly capped**: no evidence → `UNKNOWN`; unresolved conflicting evidence → `LOW`; a regression with zero confirmations → `VERY_LOW`; `< MIN_REPEATABILITY` confirmations → `MEDIUM` (a single, unrepeated confirmation cannot be HIGH — mirroring the Phase-18 VALIDATION_REQUIRED doctrine).
- Every threshold is a **named constant** (`MIN_CONFIRMATIONS_HIGH`, `MIN_REPEATABILITY`, `MAX_ALLOWED_CONTRADICTIONS`, `CONTRADICTION_FULL_PENALTY`, `MECHANISM_FULL_PENALTY`, `MIN_PREDICTION_ACCURACY_HIGH`, bands) and surfaced in `thresholds`.

## 4. Layer 2 — development ROI (`strategy/development_roi.py`, pure)
- **`estimate_campaign_roi(campaign_efficiency, confidence, calibration) -> DevelopmentROI`** — about engineering **knowledge**, never lap time. Fields: `expected_information_gain` (from Phase-19 saturation via `INFO_GAIN_SCALE`, not recomputed), `expected_confidence_gain` (the knowledge gap that a remaining legal experiment could realistically close — full for a discriminating test, half for a plain validation, zero when nothing is testable), `knowledge_gap` (`1 - overall confidence`), `estimated_session_value` (information a further session could yield, gated by testability), `cost_to_close_gap` (Phase-19 laps/tyres/minutes verbatim), `remaining_risk` (none/low/moderate/high from regressions + conflicts + elevated-risk history), `engineering_priority_reason` (an **explanation, not a ranking**), and a fully-visible `inputs` block.
- **Not an optimiser:** it computes per-campaign facts and **sorts / ranks / prioritises nothing**.

## 5. Layer 3 — campaign opportunity (`strategy/campaign_opportunity.py`, pure)
- **`classify_campaign_opportunity(campaign_efficiency, confidence, roi) -> CampaignOpportunityResult`** — a deterministic ladder over existing measures producing one of: `COMPLETE`, `NEARLY_COMPLETE`, `WORTH_ANOTHER_CONFIRMATION`, `WORTH_CONTRADICTION_TESTING`, `WORTH_MECHANISM_ISOLATION`, `NOT_WORTH_FURTHER_WORK`, `EVIDENCE_EXHAUSTED`, `KNOWLEDGE_PLATEAU`, `UNKNOWN`. Every branch carries a `reason`, a visible `factors` block and an advisory `recommended_focus` (a *kind* of test, not an instruction).
- **Completion authority is read, never overridden:** a Phase-18 `COMPLETED`/`READY_TO_FREEZE` campaign is reported COMPLETE/NEARLY_COMPLETE irrespective of remaining signals.

## 6. Assembly (`strategy/knowledge_quality.py`, pure)
`build_knowledge_quality(efficiency, calibration) -> EngineeringKnowledgeQuality` composes the three layers per campaign, **preserving the Phase-19 campaign order** (no re-sort), and produces a context summary, per-campaign `{confidence, roi, opportunity}`, transparent totals (confidence-level counts, opportunity counts, worthwhile count, context prediction accuracy) and a deterministic `content_fingerprint`. Renderer `strategy/engineering_knowledge_quality_render.py` (strings only; no Apply/freeze/complete wording).

## 7. SessionDB query shape
`SessionDB.build_engineering_knowledge_quality(**ctx, applied_setup=..., now_date=...)` reuses the Phase-19 `build_engineering_efficiency` aggregate **once** (read-only — no `register_session_id`, so it triggers no registry write; efficiency itself reuses the Phase-18 programme once) plus one `build_prediction_calibration` read. Proven: query count is **constant regardless of campaign count** (no N+1), the empty path is cheap, and the renderer touches no DB. Writes nothing; DB stays v26.

## 8. Threading & UI
`EngineeringConfidencePanel` (+ pure `ui/engineering_confidence_vm.py`, renderer above) embedded in the **Development History** page beneath the Phase-19 efficiency panel. Per campaign: overall confidence + the fully-explained component breakdown, development ROI (gains, gap, cost, risk) and campaign opportunity. **No Apply / Approve / Freeze / Complete / Execute / edit control** (asserted; only the page's existing refresh drives it). The build runs OFF the Qt thread via the reused `MechanismAnnotationWorker(QThread)`; the renderer performs no DB calls.

**Naming:** the panel is `EngineeringConfidencePanel`, **not** `EngineeringKnowledgePanel` — the latter is already owned by the Phase-12 vehicle-dynamics knowledge panel on the same page. A test asserts both panels coexist. (The brief's suggested name would have collided with Phase 12; the collision-free name preserves Phase 12 unchanged.)

## 9. Determinism
Identical canonical inputs (+ the same `now_date`) → identical component scores, confidence levels, ROI, opportunity, totals, `to_dict()` and `content_fingerprint`; verified across repeated calls and DB restart. No timestamps / random / row order / object addresses; dict/JSON ordering is stable.

## 10. Safety boundaries (proven)
No setup / experiment / outcome / development-record / registry mutation (runtime path writes nothing; `user_version` stays 26); no Apply / approve / freeze / complete / execute authority; **completion stays Phase-18-governed** (opportunity reads status, never sets it); **value reused from Phase 17 and cost from Phase 19, never recomputed**; **not an optimiser** — no sort/rank/prioritise/argmax/heapq in the ROI/opportunity/assembly modules; no AI imports or API-key references; pure domain is Qt-free, DB-free, network-free, AI-free, random-free, wall-clock-free; the frozen Apply gate, config identity, fan-out allowlist, `RULE_ENGINE_VERSION` 46.0 and `DB_VERSION` 26 are unchanged; protected runtime files git-verified byte-identical.

## 11. Persistence decision — NONE
Confidence, ROI and opportunity are pure functions of existing immutable records (development records + reconciliation records + the reconstructed campaign programme). No schema change is required; `DB_VERSION` stays **26** and `PRAGMA user_version` is verified 26 after every build path.

## 12. Tests
| File | Cases | Focus |
|---|---|---|
| `tests/test_phase20_confidence.py` | 16 | every level reachable, repeatability/conflicting/regression caps, component monotonicity, calibration inclusion/exclusion, equal-weighted mean, thresholds visible, determinism, garbage-safe |
| `tests/test_phase20_roi.py` | 12 | info gain + cost reused verbatim, no-testable→0, gap = 1−confidence, discriminating closes more, risk levels, not-lap-time, disclaims ranking, determinism, garbage-safe |
| `tests/test_phase20_opportunity.py` | 13 | all outcomes reachable, never overrides Phase-18 completion, factors visible, determinism, garbage-safe |
| `tests/test_phase20_golden.py` | 6 | scenarios A–C + real production path (writes nothing) + restart determinism + empty DB |
| `tests/test_phase20_query_shape.py` | 3 | one build, constant query count (no N+1), cheap empty, renderer-no-DB |
| `tests/test_phase20_safety.py` | 12 | no forbidden imports/wall-clock, no completion/execution, not-an-optimiser, value/cost-not-recomputed, thresholds named, no-write, completion-stays-Phase-18, no-AI scan |
| `tests/test_phase20_ui_construction.py` | 7 | panel/page, no mutation controls, None-safe, Phase-12 panel coexists, off-thread |

All 74 pass. Phase 12–19 non-UI regression (incl. the touched `session_db` / `dashboard` / `development_history_page`) green; no-AI architecture guard green.

## 13. Golden UAT results
- **A (single confirmation):** confidence `MEDIUM` (capped — not yet repeated), positive knowledge gap, opportunity worth another confirmation / mechanism isolation.
- **B (confirmed across two sessions):** confidence lifts above the single-confirmation cap; opportunity moves toward not-worth-more / nearly-complete.
- **C (a regression):** low/very-low confidence, elevated remaining risk.

## 14. Known limitations
- `prediction_accuracy` is context-level (from calibration), not per-campaign — it is applied uniformly and clearly labelled; per-campaign calibration is deferred.
- Confidence bands + component scores are deterministic rule-based estimates, not a probabilistic model (by design — no statistics/Bayesian engine).
- The opportunity ladder is coarse-grained (evidence tallies), matching the granularity of the upstream saturation signals.
- ROI is a per-campaign magnitude, deliberately **not** a cross-campaign ranking; the user reads the reasons and chooses.

## 15. Manual UAT
Porsche 911 RSR '17 @ Fuji: build recurring diagnoses across sessions; open Development History → Engineering Knowledge Quality; confirm each campaign shows overall confidence with a fully-explained component breakdown, development ROI (gains/gap/cost/risk) and an opportunity classification with reasons, and no mutation control; confirm a single confirmation reads MEDIUM (not HIGH); confirm a COMPLETED campaign reads COMPLETE regardless of remaining signals; restart and confirm identical output + fingerprint; confirm no protected runtime file changed, no DB row was written and `user_version` stays 26; confirm the Phase-12 vehicle-dynamics knowledge panel is still present.

## 16. Deferred work / recommended Phase 21
**Phase 21 — Season Development Plan & Cross-Campaign Knowledge Map (advisory):** assemble the per-campaign confidence/ROI/opportunity into a read-only season-level knowledge map (which objectives are trustworthy, which are open, where the biggest unexplored engineering questions lie) and a suggested multi-event development narrative — still read-only, still reusing Phase-17 value / Phase-18 completion / Phase-19 cost / Phase-20 confidence, no optimiser, no auto-prioritisation, no auto-completion. Not started.
