# Engineering Brain — Program 2, Phase 24: Cross-Programme Engineering Playbook

**Status:** implemented on branch `eng-brain-phase24-engineering-playbook` (from the Phase-23 tip `4559bed`). Committed locally; **not pushed; no PR; not merged; not live.**
**Schema:** **NO migration / NO persistence** — `DB_VERSION` stays **26**; `RULE_ENGINE_VERSION` unchanged (`46.0`). The playbook is rebuilt deterministically from immutable records.
**Nature:** assembles the reusable engineering knowledge across the driver's complete car stable into a deterministic, offline, read-only engineering **investigation playbook** — *not* a baseline setup.

The purpose is **not** to tell the user which setup values to copy into another car. It answers: which engineering mechanisms repeatedly matter, which behaviours are confirmed-good and must be protected, which knowledge is safely reusable vs. only a weak hypothesis vs. non-transferable, what to investigate first on a new programme, what evidence must be recollected, and what the explicit boundaries of the knowledge are.

It may assemble, rank, classify and explain existing knowledge. It may **not** generate setup values, copy setup fields, recommend a numerical starting setup, apply a setup, create/schedule an experiment, create/update a campaign, optimise, mutate records, persist a playbook, call AI, use randomness or wall-clock time, infer unknown vehicle attributes, create a second knowledge graph, recreate Phase-23 transfer logic, or bypass any authority.

## 1. Authority chain
```
Phase 17-21 established programme intelligence
  -> Phase 22 programme knowledge report + knowledge graph
  -> Phase 23 transfer report + reuse eligibility
  -> Phase 24 cross-programme engineering playbook
```
Phase 24 calls the **highest** existing orchestration authorities. `SessionDB.build_programme_engineering_playbook` composes the Phase-22 programme knowledge report **exactly once** (the only heavy DB reconstruction), derives the Phase-23 transfer report **purely** from that same Phase-22 result (no second Phase-22 build, no call to the Phase-23 SessionDB entry point), then runs the pure Phase-24 assembler. Verified by test: Phase-22 built once, Phase-23 DB entry never called, query count constant vs campaign count (no N+1), and the renderer touches no DB.

## 2. Domain model (pure)
- **`strategy/stable_themes.py` — `StableEngineeringTheme`**: one per ESTABLISHED source domain (Phase-22 maturity ∈ established/mature/complete with supporting campaigns). Fields: stable `theme_id` (sha256 of domain+mechanism+source key), engineering domain, mechanism/principle, source programme, compatible target programmes (targets where Phase-23 transfer is HIGH/SUPPORTED), recurrence count (1 source + reusable targets), evidence count (Phase-22 confirmations), maturity/confidence summaries, transfer-eligibility summary (best/worst level + counts, **reused verbatim from Phase 23** with the explicit "hypothesis only, never copy the setup" meaning), confirmed-good protections, known negative outcomes, applicability boundaries, exclusions (NOT_TRANSFERABLE targets), rationale, source authorities, and visible calculation inputs. A theme is grounded in structured Phase-22/23 records — it never groups by matching words (two domains sharing a mechanism word stay distinct themes).
- **`strategy/investigation_priority.py` — `InvestigationPriority`**: classifies each domain into `PROTECT_FIRST` / `RECOLLECT_EVIDENCE` / `DO_NOT_REUSE` / `VALIDATE_EARLY` / `CONTEXT_SPECIFIC` / `INVESTIGATE`. The category is a deterministic **ladder** (fully explained); the engineering score is a transparent weighted mean of 11 **visible dimensions** (recurrence, maturity, transfer eligibility, remaining uncertainty, masking-risk-of-confirmed-good [weight 1.5], known-negative-outcomes [1.25], context similarity, importance-to-active, evidence gaps, version compatibility, driver relevance [0.5]) with all weights, caps and rationale as visible constants. It contains no setup values or executable actions.
- **`strategy/knowledge_boundary.py` — `KnowledgeBoundary`**: records *why* knowledge cannot be reused / must be revalidated. 16 boundary types (car/manufacturer/drivetrain/category/track/track-layout/discipline/driver/GT7-version/tyre-rule/fuel-rule specific, insufficient/conflicting evidence, unknown vehicle attribute, failed historical outcome, unverified transfer proxy). Derived from Phase-22 evidence + Phase-23 domain class + visible rules. An unknown target attribute becomes an `unknown_vehicle_attribute` boundary — never guessed.
- **`strategy/new_programme_brief.py` — `NewProgrammeBrief`**: one per target programme. States established knowledge, eligible-for-cautious-reuse (as a hypothesis), protect (confirmed-good), needs-early-validation, recollect-evidence, must-not-reuse, negative directions to avoid, unresolved uncertainties and knowledge limits — plus an explicit statement that **no setup values were transferred and all knowledge requires validation** in the target.
- **`strategy/engineering_playbook.py` — `EngineeringPlaybook`**: top-level immutable result (schema/version, programme identity, generated-from authorities, stable themes, investigation priorities, knowledge boundaries, per-target briefs, global stable summary, evidence coverage, limitations, deterministic `content_fingerprint`). Renderer `strategy/engineering_playbook_render.py`.

## 3. Deterministic ranking & tie-breakers
- **Priorities**: `(category priority [PROTECT_FIRST<DO_NOT_REUSE<RECOLLECT_EVIDENCE<VALIDATE_EARLY<CONTEXT_SPECIFIC<INVESTIGATE], -engineering_score, domain-enum index, domain)`.
- **Themes**: `(-recurrence_count, -evidence_count, -maturity_rank, -confidence_rank, domain-enum index, theme_id)`.
- **Boundaries**: `(boundary-type enum index, domain, target_car)`.
- **Briefs**: target order as supplied by Phase 22 (deterministic).
No reliance on dict iteration order, DB row order, timestamps, display-string lexical order or Python object hashes. The content fingerprint uses only structured fields (domains, levels, categories, boundary keys, versions) — **no timestamps**.

## 4. Confirmed-good protection
Confirmed-good is a domain-level proxy: Phase-22 knowledge state ∈ {well_understood, engineering_complete} with confidence ∈ {high, very_high}, ≥1 confirmation, no regression, no conflict. Every relevant theme/brief exposes the confirmed-good behaviour, the programme it was confirmed in, the supporting campaigns, whether the protection is transferable, and the domains that could threaten it. A confirmed-good domain is classified `PROTECT_FIRST`; if it also carries a harmful direction, the priority sets `masking_conflict=true` and records the conflict explicitly — the playbook never silently recommends investigating a direction known to damage a confirmed-good behaviour. The UI renders confirmed-good protections visually distinct (success colour, bold).

## 5. Negative-learning preservation
Historical failed directions and regressions remain visible: a regressed direction becomes a `failed_historical_outcome` boundary and a theme `known_negative_outcome`; conflicting evidence becomes a `conflicting_evidence` boundary and reduces certainty (never averaged into false confidence). A regression on a direction retires it via the Phase-17 authority, so a contradicted domain is **never fabricated as an established/confirmed-good theme** — proven by golden scenario 5 (a clean domain survives while the contradicted domain does not become confirmed-good).

## 6. Transfer semantics & boundaries
Phase-23 transfer decisions are consumed **exactly** (the `TransferLevel` enum is imported, never re-defined or reinterpreted). `SUPPORTED` means the mechanism may be used as a hypothesis / investigation aid in the target — **never** copy the source setup, LSD, suspension, gearbox or numbers. The renderer and briefs state this distinction explicitly. `NOT_TRANSFERABLE` stays non-transferable; gearbox stays car/track-specific; track/fuel do not cross cars; driver technique requires the same driver; a GT7 major-version change caps transfer low. Suspension compatibility across manufacturers is labelled a manufacturer+category **proxy** (`unverified_transfer_proxy` boundary), not confirmed geometry; no geometry/weight/engine-placement/aero/wheelbase is inferred.

## 7. No-persistence decision
The playbook is a pure function of the reconstructed Phase-22/23 products + immutable records. No schema change is required; `DB_VERSION` stays **26** and `PRAGMA user_version` is verified 26 after every build path. Runtime verification took before/after table counts **and** a full DB-file sha256 — both unchanged.

## 8. UI behaviour
`EngineeringPlaybookPanel` (+ pure `ui/engineering_playbook_vm.py`, renderer above) embedded in the **Development History** page beneath the Phase-23 transfer panel. Structured sections (not one dense box): programme-wide themes, confirmed-good behaviours to protect (visually distinct), reusable knowledge + transfer level, investigation priorities, knowledge to recollect, context-specific boundaries, historical failed directions, per-target new-programme briefs, limitations, and a visible "no setup transferred" statement. **No Apply / Create Experiment / Schedule / Optimise / setup-field editor / numerical-setup / import / copy-setup / edit control** (asserted). Loading / empty / unavailable / error states handled; source and target programme identity visible; transfer limitations adjacent to reuse summaries; unknown attributes shown as unknown. The build runs OFF the Qt thread via the reused `MechanismAnnotationWorker(QThread)`; a **stale worker result cannot replace a newer one** (the handler guards on the current worker reference — asserted). All Phase 12/19/20/21/22/23 panels coexist unchanged (asserted).

## 9. Safety boundaries (proven)
No setup / experiment / outcome / campaign / record / registry mutation (runtime path writes nothing; all table counts + the DB-file hash unchanged; `user_version` 26); no Apply / optimiser / scheduler / setup generation / setup copy / import; no second knowledge graph or re-implemented transfer logic (asserted absent); Phase-23 `TransferLevel` reused, never redefined; no AI / network / random / wall-clock (no timestamps in the fingerprint); no setup field values in the playbook data or rendering (regex-asserted); pure modules Qt-free, DB-free, network-free, AI-free; the frozen Apply gate, config identity, fan-out allowlist, `_setup_constants.py` (git-verified byte-identical), `RULE_ENGINE_VERSION` 46.0 and `DB_VERSION` 26 are unchanged; protected runtime files unchanged.

## 10. Test evidence (exact totals)
| Command | Result |
|---|---|
| `test_phase24_domain.py` | 27 passed |
| `test_phase24_transfer_integration.py` | 10 passed |
| `test_phase24_query_shape.py` | 4 passed |
| `test_phase24_golden.py` | 7 passed |
| `test_phase24_safety.py` | 12 passed |
| `test_phase24_ui_construction.py` | 16 passed |
| **Full Phase-24 suite (6 files)** | **76 passed** |
| Phase 17–23 non-UI regression (8 files) | 57 passed |
| `test_session_db.py` + `test_no_ai_architecture.py` | 34 passed |
| Phase 22 + Phase 23 UI construction (per-file) | 7 + 7 passed |
| `test_config_safety_guardrails.py` | 30 passed, 1 warning |
| Apply-gate safety (`test_group41_validation_gate` + `test_setup_apply_checkpoint_ui` + `test_phase3_coherence_gate`) | 95 passed, 1 skipped |

## 11. Runtime verification results
Multi-car programme (Porsche RSR across two tracks + Porsche GT3 Cup + Toyota Gr.3): 2 stable themes, 2 confirmed-good, 2 reusable across programmes; the related Porsche Cup brief is cautiously reusable (2 items) while the unrelated Toyota brief is isolated (0 reusable); boundary types include car-specific, track-specific and unknown-vehicle-attribute; **all table counts unchanged**, **DB-file sha256 unchanged**, `user_version` 26, **restart-identical content fingerprint**, and **no setup-field-value assignments** anywhere in the output.

## 12. Known limitations
- Knowledge is assembled for the current (primary) programme and its transfer to the other compatibility groups — not a full all-pairs stable matrix.
- Confirmed-good is a domain-level proxy from the Phase-22 knowledge state + confidence, not a per-corner driver-confirmed behaviour.
- Suspension compatibility across manufacturers is a manufacturer+category proxy, labelled as such; unknown vehicle attributes are left unknown.
- A regression retires its direction (Phase-17 authority), so a heavily contradicted single-domain programme can collapse to an honest empty playbook.

## 13. Deferred work / recommended Phase 25
**Phase 25 — Stable Knowledge Timeline & Convergence (advisory):** track how each stable theme's maturity/confidence has moved across sessions and whether the programme is converging, plateauing or regressing over time — still read-only, reusing Phases 17–24, no optimiser, no setup generation, no scheduling, dates passed as data. Not started.
