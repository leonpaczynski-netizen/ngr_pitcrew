# Engineering Brain — Program 2, Phase 22: Engineering Knowledge Graph & Multi-Event Knowledge Roll-Up

**Status:** implemented on branch `eng-brain-phase22-knowledge-graph` (from the Phase-21 tip `30df17e`). Committed locally; **not pushed; no PR; not merged; not live.**
**Schema:** **NO migration / NO persistence** — `DB_VERSION` stays **26**; `RULE_ENGINE_VERSION` unchanged (`46.0`). Everything reconstructs from immutable records.
**Nature:** the first programme-level **Engineering Knowledge Graph** — a deterministic, explainable map of *what the Engineering Brain currently knows, how well it knows it, what evidence supports that knowledge, and what remains unknown*, organised by ENGINEERING DOMAIN and rolled up across compatible events.

This is **NOT** an AI graph, NOT graph theory, NOT ML, NOT optimisation, NOT scheduling — it is deterministic aggregation of existing authorities. It NEVER decides / optimises / prioritises / schedules / completes / applies / creates anything, and it NEVER mutates engineering state. No AI/ML/graph libraries/Bayesian/network/wall-clock/randomness. The frozen Apply gate remains the sole setup-mutation route and is byte-for-byte unchanged; campaign completion remains governed by Phase 18.

## 1. Architecture position
```
... engineering campaigns (P18) -> saturation/persistence/cost (P19)
    -> confidence/ROI/opportunity (P20) -> season development + cross-campaign map (P21)
    -> ENGINEERING KNOWLEDGE GRAPH + MULTI-EVENT ROLL-UP (P22)
```
Phase 22 sits above Phase 21: it enumerates the distinct event contexts in the immutable development records, builds the Phase-21 season report **once per compatible event**, enriches each campaign with its Phase-21 knowledge state, rolls up compatible events, and organises the knowledge by engineering domain. It writes nothing.

## 2. Reused authorities (consumed, never recreated)
Per-campaign identity (family / region / setup fields) + objective mechanisms = **Phase 18**; saturation signals + cost = **Phase 19**; confidence / ROI = **Phase 20**; per-campaign knowledge state + normalised records = **Phase 21 season report**; engineering value = **Phase 17** (via P19). Phase 22 **recomputes none of them** — it maps campaigns to domains and aggregates.

## 3. Layer 1 — engineering knowledge graph (`strategy/engineering_knowledge_graph.py`, pure)
`build_knowledge_graph(campaigns) -> KnowledgeGraph`. Visible enum **`KnowledgeDomain`** (17): Differential, Suspension, Ride Height, Springs, Anti-roll Bars, Dampers, Alignment, Brake Balance, Aerodynamics, Tyres, Fuel, Gearbox, Track Surface, Track Segments, Vehicle Balance, Weight Transfer, Driver Technique. Each campaign is mapped to the domains it touches via **FULLY VISIBLE keyword maps** — `FIELD_DOMAIN_KEYWORDS` (setup fields → mechanical domains), `FAMILY_DOMAIN_KEYWORDS` (issue family → handling domains), `MECHANISM_DOMAIN_KEYWORDS` (Phase-18 `source_mechanisms` → domains). **No inference: an unmapped field/family/mechanism contributes to no domain.**

Each `DomainKnowledge` exposes, with **reason / source / calculation** on every computed field: `knowledge_state` (dominant Phase-21 state), `confidence` (best-known Phase-20 level), `maturity` (Phase-22 Layer 3), `remaining_uncertainty` (highest Phase-19 information-gain), `supporting_campaigns`, `supporting_experiments` (fields), `supporting_mechanisms`, `supporting_evidence` (confirmation/regression/executed counts) and `known_limitations` (contradictions, unresolved mechanisms, sub-trustworthy confidence, multi-track span). The graph enumerates **all** domains — those with no contributing campaign are reported as **missing** ("knowledge still missing").

## 4. Layer 2 — multi-event roll-up (`strategy/multi_event_rollup.py`, pure)
`build_rollup(events, primary_context) -> EventRollup`. Groups per-event knowledge by the **compatibility key = (car, discipline, gt7_version, driver)** — track and layout MAY differ (that is the point of multi-event). It **NEVER merges unlike contexts**: a difference in car / discipline / version / driver keeps events in separate groups, and every exclusion states the differing field(s) explicitly. Every merge exposes *why it merged* (shared key + tracks) and every non-primary group exposes *why it did not*. It merges (and dedupes) campaign records only; it computes no new knowledge.

## 5. Layer 3 — knowledge maturity (`strategy/knowledge_maturity.py`, pure)
`classify_maturity(signals) -> MaturityResult`. Visible enum **`KnowledgeMaturity`**: `UNKNOWN`, `EMERGING`, `DEVELOPING`, `ESTABLISHED`, `MATURE`, `COMPLETE`, `PLATEAUED`. A deterministic ladder over the domain's aggregated Phase-19/20/21 measures (executed count, confirmations, conflicts, unresolved mechanisms, best confidence, knowledge states) — **no invented weighting**: no evidence → UNKNOWN; complete state or very-high confidence with nothing left → COMPLETE; plateau state with nothing left → PLATEAUED; high/very-high confidence → MATURE; medium + a confirmation → ESTABLISHED; ≥2 executions → DEVELOPING; 1 execution → EMERGING. Every level carries a reason + the authorities it came from.

## 6. Layer 4 — programme knowledge report (`strategy/programme_knowledge_report.py`, pure orchestration)
`build_programme_knowledge(events, primary_context) -> ProgrammeKnowledgeReport` rolls up the events (Layer 2) and builds the domain knowledge graph (Layer 1 + Layer 3) for the **primary compatibility group**, listing the other groups + their exclusion reasons. It assembles a context summary, compatibility block, knowledge graph, transparent totals (known/missing domain counts, maturity distribution, events merged) and a deterministic `content_fingerprint`. Renderer `strategy/programme_knowledge_report_render.py` (strings only; no Apply/freeze/complete/schedule wording).

## 7. SessionDB query shape
`SessionDB.build_programme_knowledge_report(**ctx, applied_setup=..., now_date=...)`:
1. one `SELECT DISTINCT` over `engineering_development_records` → the distinct event contexts (bounded by number of **events**, not campaigns);
2. for each event **compatible** with the current context (same car/discipline/version/driver), build the Phase-21 season report **once** and enrich its campaigns with their knowledge state (a join, not a recomputation);
3. incompatible events are passed with no campaigns (surfaced as separate groups);
4. run the pure Phase-22 aggregators.

Proven: **within one event context the query count is constant regardless of campaign count** (no N+1); the total scales with the number of distinct *events* (inherent to multi-event, bounded and small); the empty path is cheap; the renderer touches no DB. Writes nothing; DB stays v26.

## 8. Threading & UI
`EngineeringKnowledgeGraphPanel` (+ pure `ui/engineering_knowledge_graph_vm.py`, renderer above) embedded in the **Development History** page beneath the Phase-21 season panel. It shows the programme/compatibility summary, per-domain knowledge (maturity / confidence / evidence / uncertainty / supporting campaigns-experiments-mechanisms / limitations) and the domains where knowledge is still missing. **No Apply / Approve / Freeze / Complete / Execute / edit / schedule control** — only the page's existing refresh drives it (asserted). The build runs OFF the Qt thread via the reused `MechanismAnnotationWorker(QThread)`; the renderer performs no DB calls. All prior panels (Phase 12/19/20/21) coexist unchanged (asserted).

## 9. Determinism
Identical canonical inputs (+ the same `now_date`) → identical domain aggregation, maturity, roll-up grouping, order, `to_dict()` and `content_fingerprint`; verified across repeated calls, large graphs (60 campaigns) and DB restart. No timestamps / random / row order / object addresses; fixed domain order; dict/JSON ordering is stable.

## 10. Safety boundaries (proven)
No setup / experiment / outcome / record / registry mutation (runtime path writes nothing; `user_version` stays 26); no Apply / approve / freeze / complete / execute / **schedule** authority; **completion stays Phase-18-governed** (the graph reads the Phase-21 knowledge state, never sets it); every measure reused, nothing recomputed; **no AI / ML / graph or network libraries / optimisation** (no `sklearn`/`numpy`/`networkx`/`igraph`/`scipy`/`argmax`/`heapq`/`dijkstra`/`kmeans`/`optimi` in any Phase-22 module); domain maps are visible constants (no inference); **unlike contexts are never merged**; pure domain is Qt-free, DB-free, network-free, AI-free, random-free, wall-clock-free; the frozen Apply gate, config identity, fan-out allowlist, `RULE_ENGINE_VERSION` 46.0 and `DB_VERSION` 26 are unchanged; protected runtime files git-verified byte-identical.

## 11. Persistence decision — NONE
The knowledge graph, roll-up and maturity are pure functions of the reconstructed per-event season reports + existing immutable records. No schema change is required; `DB_VERSION` stays **26** and `PRAGMA user_version` is verified 26 after every build path.

## 12. Compatibility rules (multi-event)
Two events roll together **iff** they share **car AND discipline AND gt7_version AND driver**. Track/layout may differ. Any difference in the four key fields keeps events apart, and the exclusion names the differing field(s). This protects against merging unlike knowledge (e.g. a Qualifying event's knowledge is never merged into a Race programme; a different car's knowledge is never merged in). Track-specific domains (Track Segments/Surface) within a merged group carry a `known_limitation` noting the tracks spanned.

## 13. Knowledge maturity model
UNKNOWN (no evidence) → EMERGING (1 execution) → DEVELOPING (≥2 executions, still low confidence) → ESTABLISHED (medium confidence + a confirmation) → MATURE (high/very-high confidence, refinement remaining) → COMPLETE (confirmed, trustworthy, nothing useful remaining). PLATEAUED is a distinct end-state (nothing left to test yet unresolved). Determined only from Phase-19/20/21 measures; no invented weighting.

## 14. Tests
| File | Cases | Focus |
|---|---|---|
| `tests/test_phase22_maturity.py` | 13 | every level reachable + explained + sourced, best-confidence, determinism, garbage-safe |
| `tests/test_phase22_knowledge_graph.py` | 15 | field/family/mechanism→domain mapping visible + non-inferred, aggregation, dominant state/best confidence, missing domains, multi-track & conflict limitations, large graph, empty, no graph libs |
| `tests/test_phase22_rollup.py` | 15 | compatible merge, incompatible-not-merged (+reason), dedup, merge/exclude reasons, report assembly, determinism, empty, garbage-safe |
| `tests/test_phase22_golden.py` | 6 | scenarios A–C + real production path (writes nothing) + restart determinism + empty DB |
| `tests/test_phase22_query_shape.py` | 3 | constant query count vs campaign count (no N+1), cheap empty, renderer-no-DB |
| `tests/test_phase22_safety.py` | 12 | no forbidden imports/wall-clock, no scheduling/execution/optimisation, visible domain maps, unlike-never-merged, no-write, completion-stays-Phase-18, no-AI scan |
| `tests/test_phase22_ui_construction.py` | 7 | panel/page, no mutation controls, None-safe, prior-phase coexistence, off-thread |

All 71 pass. Phase 19–21 non-UI regression (incl. the touched `session_db` / `dashboard` / `development_history_page`) green; no-AI architecture guard green.

## 15. Golden UAT results
- **A (single event):** knowledge organised by domain; all 17 domains enumerated; some reported missing.
- **B (two compatible events, Fuji + Spa Race):** merged into one programme (2 events, both tracks); differential (from lsd) + ARB (from arb_front) known.
- **C (incompatible Qualifying event):** NOT merged; excluded with reason "differs in discipline".

## 16. Known limitations
- Domain mapping uses visible keyword maps over the attributes upstream authorities expose (setup fields, issue family, `source_mechanisms`); attributes not present there map to no domain (Track Segments/Surface/Driver Technique are mostly "missing" unless mechanisms reference them — honest).
- The knowledge graph is built for the **primary** compatibility group; other groups are listed with their keys/tracks but not fully graphed (bounded output; each group's own graph is available by switching context).
- Multi-event cost = one season build per compatible event; bounded by number of distinct events (small), not campaigns.
- Maturity/confidence are deterministic rule-based aggregates, not probabilistic models (by design — no statistics/graph theory).

## 17. Manual UAT
Porsche 911 RSR '17: build recurring diagnoses across two tracks (Fuji + Spa, Race) and one Qualifying event; open Development History → Engineering Knowledge Graph; confirm knowledge is organised by domain with maturity/confidence/evidence/limitations each carrying a source, that Fuji+Spa merged into one programme while Qualifying is listed separately with the reason, and that missing domains are surfaced; confirm no mutation control and no schedule/complete button; restart and confirm identical output + fingerprint; confirm no protected runtime file changed, no DB row was written and `user_version` stays 26; confirm the Phase 12/19/20/21 panels are still present.

## 18. Deferred work / recommended Phase 23
**Phase 23 — Knowledge Transfer & Cross-Car Generalisation (advisory):** identify which domain knowledge established for one car/discipline plausibly transfers to a compatible one (shared platform / class), with a fully-visible transfer-eligibility rule and every transfer grounded in evidence — still read-only, reusing Phases 17–22, no optimiser, no scheduling, no auto-completion, never merging unlike contexts silently. Not started.
