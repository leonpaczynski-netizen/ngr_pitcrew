# Engineering Brain — Program 2, Phase 19: Campaign Persistence, Evidence Saturation & Cost of Knowledge

**Status:** implemented on branch `eng-brain-phase19-campaign-persistence` (from the Phase-18 tip). Committed locally; **not pushed; no PR; not merged; not live.**
**Schema:** **additive, idempotent migration** — `DB_VERSION` **25 → 26** (new standalone `engineering_campaign_registry` table); `RULE_ENGINE_VERSION` unchanged (`46.0`). No existing table/column/query altered.
**Nature:** three deterministic, ADVISORY-ONLY layers built on a Phase-18 campaign programme. They answer, for each engineering campaign: *how old is this line of investigation, how saturated is its evidence (is more testing still worth it), and what does the remaining testing cost against a session budget?* They **measure**; they decide nothing.

It is NOT a diagnosis / synthesis / ranking / lifecycle / completion / Apply authority — it OBSERVES the existing ones. It NEVER completes/freezes/abandons a campaign, applies/approves a setup, creates/updates experiments, alters outcomes, re-ranks experiments, or recomputes engineering value. Saturation is **independent of campaign status**; **completion remains governed by Phase 18**. No AI/network. The frozen Apply gate remains the sole setup-mutation route and is byte-for-byte unchanged.

## 1. Architecture position
```
... -> experiment portfolio ranking (P17) -> engineering campaigns (P18)
       -> ENGINEERING EFFICIENCY (P19): registry age + evidence saturation + cost of knowledge
```
Phase 19 sits **above** Phase 18: it reads a built campaign programme and layers age / saturation / cost. It adds the program's first new write since Phase 11 — an additive, metadata-only campaign registry — and nothing else.

## 2. Reused authorities (consumed, never recreated)
Campaign grouping / status / stages / progress / completion = **Phase 18** (`build_engineering_campaign_programme`, read once); experiment engineering **value** = **Phase 17** (`ExperimentValuation.engineering_value`, reused verbatim — never recomputed); bounded legal experiments = **Phase 15**; multi-session outcome history + development records = **Program 1** (read-only). Phase 19 owns only: the registry metadata, the evidence-saturation status, and the cost/budget estimates.

## 3. Pure domain

### 3.1 `strategy/evidence_saturation.py`
- **`EvidenceSaturation`** — `NOT_STARTED`, `EARLY`, `BUILDING`, `STRONG`, `SATURATED`, `OVERTESTED`. Derived only from the campaign's existing progress tallies + experiment states.
- **`assess_saturation(campaign) -> SaturationResult`** — every count is exposed in `signals`; every decision number is a **named, visible constant** (`CONFIRMATIONS_FOR_STRONG=1`, `CONFIRMATIONS_FOR_SATURATED=2`, `OVERTESTED_REPEATS=3`, `EXECUTED_FOR_BUILDING=2`) surfaced in `thresholds`; every status carries `reasons`. `information_gain_remaining` ∈ `high/moderate/low/none`. **Saturation never reads or depends on campaign status** — identical evidence yields identical saturation whether the campaign is ACTIVE or READY_TO_FREEZE.

### 3.2 `strategy/engineering_cost_model.py`
- **`estimate_experiment_cost(experiment) -> ExperimentCostEstimate`** — an A/B/A effort estimate: `laps = warmup(1) + baseline(4) + test(4, +4 if coupled pair) + revert(4)`, plus `time_minutes`, `fuel_laps`, `tyre_sets`, `estimated_confidence_gain`, `value_per_lap`, `value_per_minute`, `info_gain_per_tyre_set`. The `engineering_value` is taken **verbatim from Phase 17**; the ratios are pure divisions of that value. All cost constants are exposed on every estimate (`cost_constants`).
- **`EngineeringBudget` / `plan_budget(estimates, session_budget)`** — a **deterministic greedy fit in the given Phase-17 rank order** over still-testable experiments: which fit a session's time / tyres / fuel, which are deferred, with utilisation. It is explicitly **NOT an optimiser or scheduler** and selects/executes/mutates nothing. When no budget is supplied, `budget_known=False` and all experiments are deferred (nothing is invented).

### 3.3 `strategy/campaign_persistence.py`
- **`CampaignRegistryEntry`** — metadata only: stable `campaign_id` (from car/track/layout/discipline/objective-family/region/GT7-version — set by Phase 18), creation session, first/last seen, last updated, user notes, manual archive flag, completion state (mirrored, not authored), abandonment reason, and links to the informing development records / experiments / outcomes. It owns **no engineering logic**.
- **`campaign_age_days(first_seen, now_date)`** — dates are **data** (passed in; no wall-clock).
- **`build_engineering_efficiency(programme, *, registry, session_budget, now_date)`** — composes Phase-18 campaigns + registry age + saturation + per-experiment cost + programme-level budget fit into one read-only view with a deterministic `content_fingerprint`. Never raises.

## 4. Persistence — the only new write
`engineering_campaign_registry` (DB v26, additive standalone table): `campaign_id` PK + identity columns + `creation_session` / `first_seen` / `last_seen` / `last_updated` + `notes` / `manual_archive_flag` / `completion_state` / `abandonment_reason` + `linked_*` JSON. Metadata only — it stores **no setup, no experiment, no outcome**.

`SessionDB.record_engineering_campaigns(programme, *, session_id, recorded_at)` is idempotent: `INSERT OR IGNORE` preserves `first_seen` / `creation_session` on re-record; a follow-up `UPDATE` refreshes only `last_seen` / `last_updated` / `completion_state` / `linked_experiments`. User-owned `notes` and `manual_archive_flag` (set via `set_campaign_note`) are **never** clobbered by a re-record. `recorded_at` is supplied, never read from the clock.

The write is **opt-in**: `SessionDB.build_engineering_efficiency(...)` writes **nothing** by default (the read-only / test path). Only when the caller passes a non-empty `register_session_id` does it perform the single best-effort registry capture before reading the registry back — so a freshly observed campaign's first-seen provenance and age are available. A capture failure never breaks the advisory. The write never governs completion and never affects the advisory beyond the age/first-seen provenance it records.

## 5. SessionDB query shape
`SessionDB.build_engineering_efficiency(**ctx, applied_setup=..., session_budget=..., now_date=..., register_session_id=..., recorded_at=...)` reuses the Phase-18 `build_engineering_campaign_programme` aggregate **once** (which itself reuses Phase-17 once), plus one registry read. Proven: query count is **constant regardless of campaign count** (no N+1), the empty path is cheap, and the renderer touches no DB.

## 6. Threading & UI
`EngineeringEfficiencyPanel` (+ pure `ui/engineering_efficiency_vm.py`, renderer `strategy/engineering_efficiency_render.py`) embedded in the **Development History** page beneath the Phase-18 campaigns panel, as a read-only **Engineering Efficiency** section. Per campaign: age (from the registry), evidence saturation with its visible reasons and signals, cost of knowledge (laps / time / tyres, value reused from Phase 17), remaining information gain, and a session-budget fit advisory. **No Apply / Approve / Freeze / Complete / Execute / setup-edit / experiment-create control.** The build runs OFF the Qt thread via the reused `MechanismAnnotationWorker(QThread)`; the dashboard supplies the current session id + today's date so the off-thread build performs the additive registry capture; the renderer performs no DB calls.

## 7. Determinism
Identical canonical inputs (+ the same `now_date` / `session_budget`) → identical saturation, cost estimates, budget fit, registry-derived age, `to_dict()` and `content_fingerprint`; verified across repeated calls and DB restart. No timestamps / random / row order / object addresses in the pure layer; dates are data; dict/JSON ordering is stable.

## 8. Safety boundaries (proven)
No setup / experiment / outcome / development-record mutation; no Apply / approve / freeze / complete / execute authority; **saturation independent of status**; **value reused from Phase 17, never recomputed**; no re-ranking; no AI imports or API-key references; the read-only build writes nothing (registry / development-record / experiment counts unchanged, `user_version` stays 26) and the opt-in capture touches **only** the registry; pure domain is Qt-free, DB-free, network-free, AI-free, random-free, wall-clock-free; the frozen Apply gate, config identity, fan-out allowlist and `RULE_ENGINE_VERSION` 46.0 are unchanged; protected runtime files byte-identical; the migration is additive + idempotent (`IF NOT EXISTS`, re-runnable).

## 9. Persistence decision — ADDITIVE (justified)
Unlike Phases 12–18, campaign **identity provenance** (creation session, first-seen date → age) and **user-authored notebook metadata** (notes, archive flag) are genuinely non-reconstructable from canonical records — they must survive across sessions. This warrants the program's first migration since Phase 11: one additive, idempotent, standalone table. All *engineering* facts (status, progress, saturation, cost) remain reconstructed, not stored; the registry stores only metadata.

## 10. Tests
| File | Cases | Focus |
|---|---|---|
| `tests/test_phase19_saturation.py` | 13 | every status reachable + explained, thresholds/signals visible, saturation independent of status, never-raises, determinism, no hidden numbers |
| `tests/test_phase19_cost.py` | 16 | A/B/A lap budget, coupled cost, value reused (not recomputed), confidence share, tyre/fuel derivation, greedy budget fit in rank order, tyre/time constraints, no optimiser, only-testable planned |
| `tests/test_phase19_persistence.py` | 13 | registry entry / row round-trip, age (dates as data), efficiency assembly, idempotent write preserves provenance, notes/archive preserved on rewrite, restart survival, migration idempotency, opt-in capture |
| `tests/test_phase19_golden.py` | 6 | Scenarios A–C + real SessionDB production path (writes only registry) + restart determinism + empty DB |
| `tests/test_phase19_query_shape.py` | 3 | one efficiency build, constant query count (no N+1), cheap empty, renderer-no-DB |
| `tests/test_phase19_safety.py` | 9 | no forbidden imports / wall-clock, no completion/execution, value-not-recomputed, thresholds named, versions, read-only build, capture-touches-only-registry, no-AI scan |
| `tests/test_phase19_ui_construction.py` | 6 | panel/page, no mutation controls, None-safe, off-thread |

All 66 pass. Phase 8–18 version-affected suites (260) re-green after the `DB_VERSION` bump (test assertions updated 25 → 26); no-AI architecture + config-safety guards green.

## 11. Golden UAT results
- **A (early campaign, one confirmed):** saturation `early/building`, positive remaining information gain, non-zero remaining testing cost.
- **B (opt-in capture):** first observation records `first_seen`; a later observation preserves it and computes a 10-day age (`week(s)` label); creation session preserved.
- **C (budget fit):** with a session budget the fit is `budget_known` and the rationale states **no optimisation** — advisory only.

## 12. Known limitations
- Saturation uses coarse outcome tallies (confirmed / regressed / no-change counts) — it does not yet weight by per-outcome confidence or effect size.
- Cost estimates use conservative fixed constants (laps/tyre-set, minutes/lap default); real per-car/tyre wear curves are not consulted (they are exposed for a future refinement).
- The budget fit is a single greedy pass in Phase-17 rank order; it deliberately does not search alternative subsets (that would be an optimiser — out of scope).
- Explicit user-driven ABANDONED/COMPLETED *transitions* are storable (columns exist) but authored only via `set_campaign_note`; automatic completion remains forbidden and Phase-18-governed.

## 13. Manual UAT
Porsche 911 RSR '17 @ Fuji: build recurring diagnoses across sessions; open Development History → Engineering Efficiency; confirm each campaign shows age, saturation (with reasons + visible thresholds), cost of knowledge and remaining information gain, and no mutation control; confirm a heavily saturated campaign is **not** marked complete (status still Phase-18-governed); supply a session budget and confirm the fit says "no optimisation"; re-open on a later date and confirm the age grows while first-seen/creation are preserved; restart and confirm identical output + fingerprint; confirm no protected runtime file changed, only the registry row was written, and `user_version` stays 26.

## 14. Deferred work / recommended Phase 20
**Phase 20 — Confidence-Weighted Evidence & Development ROI:** fold per-outcome **confidence / effect-size** into saturation (so a low-confidence confirmation counts less than a strong one) and into a **development ROI** view that ranks *campaigns* (not experiments) by expected knowledge-gain per unit cost against the season's open objectives — still read-only advisory through every existing gate and manual Apply, still reusing Phase-17 value and Phase-18 completion, no optimiser, no auto-prioritisation. Not started.
