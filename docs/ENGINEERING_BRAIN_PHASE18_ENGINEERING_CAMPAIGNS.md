# Engineering Brain — Program 2, Phase 18: Engineering Campaigns & Multi-Session Development Planning

**Status:** implemented on branch `eng-brain-phase18-engineering-campaigns` (from `60a7e48`, the Phase-17 tip). Committed locally; **not pushed; no PR; not merged; not live.**
**Schema:** **NO migration / NO persistence** — `DB_VERSION` stays **25**; `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** a deterministic, READ-ONLY layer that groups a Phase-17 experiment portfolio into coherent, multi-session vehicle-development **campaigns**. A campaign answers: *what engineering objective are we pursuing, what have we learned, what remains uncertain, which experiments belong to this objective, and how close are we to declaring it complete?*

It is NOT a diagnosis / synthesis / experiment-ranking / lifecycle / Apply authority — it ORCHESTRATES the existing ones. It NEVER applies/approves/freezes a setup, creates/updates experiments, alters outcomes, writes engineering records, performs hidden weighting, re-ranks experiments independently of Phase 17, or marks a successful-but-unvalidated objective complete. No AI/network. The frozen Apply gate remains the sole setup-mutation route and is byte-for-byte unchanged.

## 1. Architecture position
```
canonical evidence -> mechanism-annotated diagnoses (P13) -> bounded legal experiments (P15)
-> experiment portfolio ranking (P17) -> ENGINEERING CAMPAIGN (P18) -> existing lifecycle (P16)
-> outcome evaluation + reconciliation + calibration (P1)
```
Phase 18 sits after Phase-17 planning and before experiment execution.

## 2. Reused authorities (consumed, never recreated)
Experiment ranking + dependencies + retirement = **Phase 17** (`ExperimentPortfolio` / `ExperimentValuation`); bounded legal experiments = **Phase 15**; mechanism hypotheses = **Phase 14**; lifecycle / execution = **Phase 16**; outcome / reconciliation / prediction calibration + development records = **Program 1** (read-only projection); canonical applied-setup state + scope = `setup_state_authority` (for stale detection). Phase 18 owns only the campaign grouping + status/stage/progress derivation.

## 3. Campaign domain (`strategy/engineering_campaign.py`, pure)
- **`CampaignIdentity`** — immutable, scoped to the exact context (driver/car/track/layout/discipline/GT7-version + objective family/region + fingerprint). Incompatible contexts are never silently merged.
- **`CampaignObjective`** — bounded, evidence-derived, traceable (title, engineering question, source diagnoses + mechanisms, affected phases, protected-good behaviours, current uncertainty, completion criteria, blockers, rationale). No vague "improve the setup" objectives.
- **`CampaignStatus`** — `NOT_STARTED`, `ACTIVE`, `BLOCKED`, `VALIDATION_REQUIRED`, `READY_TO_FREEZE`, `COMPLETED`, `ABANDONED`, `STALE` (derived from campaign facts, not guessed; read-only).
- **`CampaignStage` / `CampaignStageType`** — `DEFINE`, `DISCRIMINATE`, `INTERVENE`, `REVIEW`, `VALIDATE`, `FREEZE`, `RACE_READY`, each with purpose, candidate ids, completion state, blockers, exit criteria and an advisory next action.
- **`CampaignExperiment` / `CampaignRole`** — references Phase-17 candidates (never copies the ranking); `PRIMARY_DISCRIMINATOR` / `PRIMARY_INTERVENTION` / `SECONDARY_INDEPENDENT_TEST` / `VALIDATION_TEST` / `PROTECTION_CHECK` / `CONTINGENCY` / `RETIRED`; carries execution/outcome/reconciliation/prediction-accuracy state, knowledge gained and remaining question.
- **`CompletionCriterion`** — immutable, explicit, campaign-specific (issue confirmed, mechanism discriminated, intervention confirmed, no protected regression, validated, freeze-eligible) with satisfied flag + blocker + rationale.
- **`CampaignProgress`** — transparent (tallies + criteria satisfied/total + `progress_pct` = satisfied/total, exposed `factors`, maturity label, rationale). No hidden magic numbers.
- **`EngineeringCampaign`** and **`EngineeringCampaignProgramme`** (context summary, campaigns, active/blocked/ready-to-freeze/completed/stale counts, programme blockers, recommended focus, programme roadmap, fingerprint).

## 4. Grouping rules
Deterministic, evidence-based: candidates are grouped by **objective key = (issue family, region)** derived from the canonical `issue_type` (e.g. `(rotation, front)` = "Improve front grip and rotation" — merges entry + mid-corner understeer; `(braking, rear)` = "Reduce rear instability under braking"; `(traction, rear)` = "Improve corner-exit traction"). Not one campaign per candidate, not per setup field, not collapsing unrelated diagnoses. The grouping rationale is exposed.

## 5. Status / progress / completion
Status derives from the multi-session evidence: no history + a legal experiment → `NOT_STARTED`; executed with uncertainty → `ACTIVE`; no legal experiment / all retired → `BLOCKED` (or `ABANDONED` when a prior regression invalidates the direction); a confirmed direction but < 2 confirmations → `VALIDATION_REQUIRED`; all completion criteria satisfied → `READY_TO_FREEZE` (or `COMPLETED` when confirmed across ≥ 2 sessions); active-context mismatch → `STALE`. Progress is `criteria_satisfied / criteria_total` (visible), so only-regressions never look near-complete and a successful-but-unvalidated objective is **never** COMPLETED.

## 6. Multi-session reconstruction & stale-context
The programme is rebuilt deterministically from existing records: `SessionDB._campaign_outcome_history` projects the immutable Phase-8 development records into `{fields, direction, outcome_status, session}` entries, distinguishing not-tested / tested-this-session / confirmed-across-sessions / regressed. Incompatible evidence is excluded (never merged across scopes); where compatibility can't be proven, confidence is downgraded and disclosed. Stale-context is detected by comparing the active applied-setup identity against the campaign scope (car/track/layout/discipline/GT7-version) — the mismatch is visible and no recommendation is treated as executable.

## 7. SessionDB query shape
`SessionDB.build_engineering_campaign_programme(**ctx, applied_setup=..., session_identity=..., session_context=...)` — reuses the Phase-17 `build_experiment_portfolio` aggregate **once** (the outcome history is fed to it so Phase-17 retirement sees prior confirmed/regressed directions), plus one development-record read and one calibration read. Proven: query count is **constant regardless of diagnosis / campaign count** (no N+1), the empty path is cheap, and the renderer touches no DB. Writes nothing; DB stays v25.

## 8. Threading & UI
`EngineeringCampaignPanel` (+ pure `ui/engineering_campaign_vm.py`, renderer `strategy/engineering_campaign_render.py`) embedded in the **Development History** page beneath the Phase-17 panel. Structured sections: programme summary, campaign list (objective/status/progress/maturity/next action/blockers) and per-campaign detail (engineering question, completion criteria, stages, experiments + roles, knowledge gained, remaining uncertainty, advisory roadmap). **No Apply / Approve / Revert / freeze / setup-edit / experiment-create control.** The build runs OFF the Qt thread via the reused `MechanismAnnotationWorker(QThread)`; the renderer performs no DB calls.

## 9. Determinism
Identical canonical inputs → identical grouping, identities, statuses, stages, roles, criteria, progress, programme ordering, recommended focus, roadmap, `to_dict()` and `content_fingerprint`; verified across repeated calls and DB restart. No timestamps / random / row order / object addresses; dict/JSON ordering is stable.

## 10. Safety boundaries (proven)
No setup / experiment / outcome / development-record mutation; no Apply / approve / freeze / execution authority; no AI imports or API-key references; no duplicate ranking (Phase 17) or lifecycle (Phase 16) logic; the runtime path writes nothing (`engineering_development_records` and `setup_experiments` counts unchanged, `user_version` stays 25); pure domain is Qt-free, DB-free, network-free, AI-free, random-free, wall-clock-free; the frozen Apply gate, config identity, fan-out allowlist, `RULE_ENGINE_VERSION` 46.0 and `DB_VERSION` 25 are unchanged; protected runtime files byte-identical.

## 11. Persistence decision — NONE
Campaigns are reconstructed from canonical existing records (portfolio + development records + calibration). No schema change is required; `DB_VERSION` stays **25** and `PRAGMA user_version` is verified 25 after every campaign build path.

## 12. Tests
| File | Cases | Focus |
|---|---|---|
| `tests/test_phase18_campaign_domain.py` | 18 | identity/scoping, grouping, objective, stages, status, progress, criteria, validation-required, ready-to-freeze, completed, stale, retirement visibility, incompatible-context, determinism, rendering |
| `tests/test_phase18_golden.py` | 7 | Scenarios A–D + real SessionDB production path + restart |
| `tests/test_phase18_safety.py` | 8 | no mutation/apply/freeze/execution, no AI, no duplicate ranking/lifecycle, never-complete-unvalidated, versions, read-only |
| `tests/test_phase18_query_shape.py` | 3 | one portfolio build, constant query count (no N+1), cheap empty, renderer-no-DB |
| `tests/test_phase18_ui_construction.py` | 5 | panel/page, no mutation controls, off-thread |

All 41 pass. Phase 12–17 non-UI (451) + setup-experiment/outcome/preflight/postflight/reconciliation (207) + broad non-UI regression (2409) green; every UI construction module passes per-file (12→18). (UI-worker tests run per-file per the documented Windows/Python-3.14 PyQt `app.exec()` isolation rule — each module passes independently; not a product defect.)

## 13. Golden UAT results
- **A (rear braking instability):** one campaign, `VALIDATION_REQUIRED`, successful intervention visible, validation stage open, not completed, no Apply claim.
- **B (exit traction, prior regression):** the failed `lsd_accel` increase is retired/visible, regression shown, progress not inflated, an alternative experiment remains.
- **C (confirmed across 2 sessions):** `READY_TO_FREEZE`/`COMPLETED`; freeze stage points at the existing freeze/lifecycle authority; no automatic freeze write.
- **D (stale):** `STALE`; context mismatch explained; evidence retained; "do not execute" next action.

## 14. Known limitations
- The dashboard passes no explicit `session_context` yet (defaults to unknown → lower session confidence); the pure API accepts it.
- Cross-campaign mutual-exclusion gating uses coarse (field, increase/decrease) direction; magnitude-aware gating is deferred.
- Multi-session compatibility is established from the development-record context (all compatible within one memory-context key); finer cross-context compatibility scoring is deferred.
- Campaigns are reconstructed, not stored — explicit ABANDONED/COMPLETED *records* are out of scope (Phase 18 reports evidence-derived state only).

## 15. Manual UAT
Porsche 911 RSR '17 @ Fuji: create recurring diagnoses across sessions; open the Development History page; confirm the Engineering Campaigns panel groups them into bounded objectives with status/progress/completion criteria/stages/roadmap and no mutation control; confirm a single confirmed improvement shows `VALIDATION_REQUIRED` (not complete); confirm a prior-regressed direction is retired/visible; change the active car/track and confirm campaigns go `STALE` with the mismatch explained; restart and confirm identical output + fingerprint; confirm no protected runtime file and no DB row changed and `user_version` stays 25.

## 16. Deferred work / recommended Phase 19
**Phase 19 — Campaign Persistence, Evidence-Saturation & Cost-of-Knowledge:** durably record campaign identity + explicit ABANDONED/COMPLETED transitions (additive, idempotent), detect evidence saturation / diminishing information gain to recommend stop-testing, and model per-experiment cost (estimated laps/tyres/fuel) so the planner can weigh knowledge against a session budget — still read-only advisory through every existing gate and manual Apply. Not started.
