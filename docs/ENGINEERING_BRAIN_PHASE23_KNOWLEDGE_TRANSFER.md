# Engineering Brain — Program 2, Phase 23: Knowledge Transfer Eligibility & Cross-Car Engineering Reuse

**Status:** implemented on branch `eng-brain-phase23-knowledge-transfer` (from the Phase-22 tip `0ce6721`). Committed locally; **not pushed; no PR; not merged; not live.**
**Schema:** **NO migration / NO persistence** — `DB_VERSION` stays **26**; `RULE_ENGINE_VERSION` unchanged (`46.0`). Everything reconstructs from immutable records.
**Nature:** a deterministic Engineering Knowledge **Transfer** layer. Its purpose is **NOT to transfer setups** — it determines whether previously established engineering **KNOWLEDGE** (mechanisms, handling behaviour) is likely reusable in another compatible engineering context (e.g. another Porsche Gr.3, a car with similar architecture).

It transfers NO setup values, recommends applying NOTHING, imports NOTHING, and decides NOTHING. Every transfer level is fixed by **visible deterministic rules**; there is no inference beyond them. No AI/ML/optimisation/scheduling/randomness/wall-clock/network. The frozen Apply gate remains the sole setup-mutation route and is byte-for-byte unchanged; campaign completion remains governed by Phase 18.

## 1. Architecture position
```
... Phases 1-22 (engineering knowledge generation, up to the knowledge graph)
    -> KNOWLEDGE TRANSFER ELIGIBILITY + ENGINEERING REUSE (Phase 23)
```
Phase 23 sits above Phase 22: it takes the current programme's **established** domain knowledge (from the Phase-22 knowledge graph) and evaluates, against each other engineering context, whether that knowledge is reusable. It writes nothing.

## 2. Reused authorities (consumed, never recreated)
Established domain knowledge (domain, maturity, confidence, mechanisms, supporting campaigns) = **Phase 22 knowledge graph** (which reuses Phases 17–21); the other compatibility groups (targets) = **Phase 22 multi-event roll-up**; engineering value / cost / confidence flow through Phase 22 unchanged. Phase 23 **recomputes none of them** — it reasons about reuse using visible rules.

## 3. Layer 1 — knowledge transfer (`strategy/knowledge_transfer.py`, pure)
`evaluate_transfer(source_domain, source_ctx, target_ctx) -> KnowledgeTransferCandidate`. Visible enum **`TransferLevel`**: `NOT_TRANSFERABLE`, `VERY_LOW`, `LOW`, `MEDIUM`, `HIGH`, `SUPPORTED`. The candidate exposes `source_context`, `target_context`, `engineering_domain`, `knowledge_area`, `transfer_level`, `reason`, `supporting_evidence`, `supporting_campaigns`, `supporting_mechanisms`, `confidence` (each computed field with reason/source/calculation) and `limitations`. The level is decided ONLY by the deterministic rules (Layer 2) + the domain transferability class:
- **Established-source gate:** knowledge below ESTABLISHED (Phase-22 maturity) → `NOT_TRANSFERABLE` (nothing proven to transfer).
- **Context-bound** domains (track segments/surface, fuel) → `NOT_TRANSFERABLE` (track/event specific).
- **Driver-specific** (driver technique) → transfers only to the **same driver**, else `NOT_TRANSFERABLE`.
- **Car/track-specific** (gearbox / final-drive) → `NOT_TRANSFERABLE` unless **explicitly supported** (shared mechanism + architecturally identical car + compatible version), then at most `LOW`.
- **Version incompatibility** (different GT7 major version) caps everything at `VERY_LOW`/`NOT_TRANSFERABLE`.
- **Architecture-dependent** (springs, ARBs, dampers, differential, aero, brakes, tyres): same manufacturer + drivetrain + category → `HIGH` (+ shared suspension-architecture proxy + mechanism + strong source → `SUPPORTED`); two of the three → `MEDIUM`; one → `LOW`; none → `NOT_TRANSFERABLE`.
- **Handling/drivetrain** (vehicle balance, weight transfer): same drivetrain + layout → `HIGH` (+ manufacturer + mechanism + strong source → `SUPPORTED`); one → `MEDIUM`.

## 4. Layer 2 — transfer rules (`strategy/transfer_rules.py`, pure)
All rules are **VISIBLE CONSTANTS**, each with *why it exists* and *what authority supports it*: `same_manufacturer`, `same_drivetrain`, `same_layout`, `same_race_category`, `same_suspension_architecture` (manufacturer+category proxy), `compatible_gt7_version`, `same_driver`. `evaluate_rules(...)` returns `{rule_id: bool}`; `rule_catalogue()` returns the visible id/why/authority list for display. Car engineering attributes (`manufacturer / drivetrain / layout / category`) are derived **deterministically from the GT7 car name** via visible maps (`CAR_DRIVETRAIN_REGISTRY`, `DRIVETRAIN_KEYWORDS`, `DRIVETRAIN_LAYOUT`, `CATEGORY_KEYWORDS`) — an **unknown attribute stays "unknown"** (never guessed). `DOMAIN_TRANSFER_CLASS` maps each of the 17 domains to a transferability class with a visible reason.

## 5. Layer 3 — engineering reuse (`strategy/engineering_reuse.py`, pure)
`summarise_reuse(candidates) -> ReuseSummary` groups the candidates into **reusable** ("this knowledge is reusable because…"), **needs_more_evidence** ("additional evidence still required…" + what is missing) and **not_reusable** ("this knowledge is not reusable because…"), and detects **isolated targets** (contexts with no reusable knowledge at all). It **NEVER recommends applying** knowledge or a setup — it only reports.

## 6. Layer 4 — programme transfer report (`strategy/programme_transfer_report.py`, pure orchestration)
`build_transfer_report(source_graph, source_context, target_contexts) -> ProgrammeTransferReport` evaluates every established source-domain × every target context (Layer 1), summarises reuse (Layer 3), attaches the visible rule catalogue, and produces transparent totals + a deterministic `content_fingerprint`. Renderer `strategy/programme_transfer_report_render.py` (strings only; no Apply/import/copy-setup/execute wording).

## 7. SessionDB query shape
`SessionDB.build_programme_transfer_report(**ctx, applied_setup=..., now_date=...)` composes the Phase-22 programme knowledge report **once** (its established source domains + the other compatibility groups as targets), then runs the pure Phase-23 evaluation. No additional per-campaign queries. Proven: **within one context the query count is constant regardless of campaign count** (no N+1); the empty path is cheap; the renderer touches no DB. Writes nothing; DB stays v26.

## 8. Threading & UI
`EngineeringTransferPanel` (+ pure `ui/engineering_transfer_vm.py`, renderer above) embedded in the **Development History** page beneath the Phase-22 knowledge-graph panel. It shows the transfer candidates + eligibility, supporting evidence, limitations, reusable engineering concepts, isolated contexts and the visible rule catalogue. **No Apply / Execute / Import / Copy-Setup / edit control** — only the page's existing refresh drives it (asserted). The build runs OFF the Qt thread via the reused `MechanismAnnotationWorker(QThread)`; the renderer performs no DB calls. All prior panels (Phase 12/19/20/21/22) coexist unchanged (asserted).

## 9. Determinism
Identical canonical inputs (+ the same `now_date`) → identical car-attribute derivation, rule evaluation, transfer levels, reuse grouping, order, `to_dict()` and `content_fingerprint`; verified across repeated calls and DB restart. No timestamps / random / row order / object addresses; dict/JSON ordering is stable.

## 10. Safety boundaries (proven)
No setup / experiment / outcome / record / registry mutation (runtime path writes nothing; `user_version` stays 26); **no setup transfer / import / copy / apply** (no `apply`/`import_setup`/`copy_setup`/`transfer_setup`/`recommend` in any Phase-23 module); no execution / schedule / optimisation (no `argmax`/`heapq`/`optimi`); no AI/ML/graph libraries; transfer levels decided only by visible deterministic rules (no inference beyond them); **unlike contexts never transfer** (different manufacturer gearbox → `NOT_TRANSFERABLE`, asserted); the reuse summary never recommends applying; pure domain is Qt-free, DB-free, network-free, AI-free, random-free, wall-clock-free; the frozen Apply gate, config identity, fan-out allowlist, `RULE_ENGINE_VERSION` 46.0 and `DB_VERSION` 26 are unchanged; protected runtime files git-verified byte-identical.

## 11. Persistence decision — NONE
Transfer candidates and the reuse summary are pure functions of the reconstructed Phase-22 knowledge graph + existing immutable records. No schema change is required; `DB_VERSION` stays **26** and `PRAGMA user_version` is verified 26 after every build path.

## 12. Transfer rules & compatibility rules
**Transfer rules** (visible): same_manufacturer, same_drivetrain, same_layout, same_race_category, same_suspension_architecture (proxy), compatible_gt7_version, same_driver — each with why + authority. **Compatibility** is per engineering domain: architecture-dependent domains need shared manufacturer/drivetrain/category; handling domains need shared drivetrain/layout; gearbox is car/track specific (transfers only when explicitly supported); track/fuel domains are context-bound (never transfer across cars); driver-technique transfers only to the same driver; any GT7 major-version change caps transfer low. Car attributes are derived deterministically from the GT7 car name; unknown attributes are never guessed and simply fail the rules that need them (conservative).

## 13. Tests
| File | Cases | Focus |
|---|---|---|
| `tests/test_phase23_transfer_rules.py` | 12 | car-attribute derivation (known/unknown/empty/category), rule evaluation (same/different/version), visible catalogue, domain classes, determinism, garbage-safe |
| `tests/test_phase23_eligibility.py` | 18 | established-source gate, architecture SUPPORTED/LOW, context-bound/gearbox/driver-specific/version handling, handling-on-drivetrain, confidence reuse, reuse grouping + isolation, determinism, garbage-safe |
| `tests/test_phase23_golden.py` | 8 | scenarios A–C + real production path (writes nothing) + restart determinism + empty DB + ASCII render |
| `tests/test_phase23_query_shape.py` | 3 | constant query count vs campaign count (no N+1), cheap empty, renderer-no-DB |
| `tests/test_phase23_safety.py` | 12 | no forbidden imports/wall-clock, no setup-transfer/apply, visible rule constants, unlike-never-transfer, no-write, never-recommends-applying, no-AI scan |
| `tests/test_phase23_ui_construction.py` | 7 | panel/page, no mutation controls, None-safe, prior-phase coexistence, off-thread |

All 62 pass. Phase 20–22 non-UI regression (incl. the touched `session_db` / `dashboard` / `development_history_page`) green; no-AI architecture guard green.

## 14. Golden UAT results
- **A (transfer candidates):** an established Porsche RSR programme yields transfer candidates to the other contexts, with the visible rule catalogue attached.
- **B (cross-car):** knowledge to a different-manufacturer Toyota Gr.3 is capped low / not-reusable (different manufacturer & drivetrain); the Toyota target is reported isolated.
- **C (single context):** with only the source context present, there are no target contexts and no candidates.
- **Synthetic:** Porsche RSR → Porsche 911 GT3 Cup (same manufacturer + category + drivetrain) gives `SUPPORTED` for suspension/differential/balance; gearbox → `LOW`; track segments → `NOT_TRANSFERABLE`; same car across GT7 versions → `VERY_LOW`.

## 15. Known limitations
- Car attributes are derived from the GT7 car-name string via visible maps; cars whose drivetrain/category are not encoded in the name (and not in the small registry) return "unknown", which conservatively fails the rules that need them (no transfer inferred). The registry is intentionally extensible.
- `same_suspension_architecture` is a manufacturer+category **proxy** — there is no explicit geometry catalogue, so architecturally-similar cars from different manufacturers are treated conservatively.
- Transfer is evaluated from the current (primary) programme's knowledge to the other compatibility groups; a full all-pairs matrix across every car is out of scope (bounded, focused output).
- Transfer levels are deterministic rule outputs, not probabilistic estimates (by design — no statistics/ML).

## 16. Manual UAT
Porsche 911 RSR '17: build established knowledge (e.g. confirmed differential/balance across sessions), and seed records for another car and/or discipline; open Development History → Engineering Knowledge Transfer; confirm transfer candidates show the domain, level, reason, evidence and limitations, that same-manufacturer/category targets read HIGH/SUPPORTED while different-manufacturer targets read LOW/NOT_TRANSFERABLE, that gearbox/track-segment knowledge is not transferred, that the visible rule catalogue is shown, and that isolated contexts are listed; confirm no Apply/Import/Copy-Setup control; restart and confirm identical output + fingerprint; confirm no protected runtime file changed, no DB row was written and `user_version` stays 26; confirm the Phase 12/19/20/21/22 panels are still present.

## 17. Deferred work / recommended Phase 24
**Phase 24 — Cross-Programme Engineering Playbook (advisory):** assemble the transferable knowledge across the whole car stable into a read-only engineering "playbook" — which mechanisms/behaviours are established programme-wide, where they reliably recur, and where a new car should start from proven knowledge vs. a blank sheet — still read-only, reusing Phases 17–23, no optimiser, no setup transfer, no scheduling, never inferring beyond the visible rules. Not started.
