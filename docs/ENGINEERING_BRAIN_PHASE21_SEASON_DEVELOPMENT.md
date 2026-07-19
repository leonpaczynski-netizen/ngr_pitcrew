# Engineering Brain — Program 2, Phase 21: Season Development Plan & Cross-Campaign Knowledge Map

**Status:** implemented on branch `eng-brain-phase21-season-development` (from the Phase-20 tip `dd0f1ea`). Committed locally; **not pushed; no PR; not merged; not live.**
**Schema:** **NO migration / NO persistence** — `DB_VERSION` stays **26**; `RULE_ENGINE_VERSION` unchanged (`46.0`). Everything reconstructs from existing records.
**Nature:** a deterministic, READ-ONLY *season-level* engineering-planning layer — the Engineering Director's dashboard. Where Phases 1–20 understand individual experiments and campaigns, Phase 21 understands the programme **as a whole**: what has been learned, where the largest knowledge gaps are, which vehicle systems are understood, where campaigns overlap / duplicate / support / contradict / depend / sit isolated.

It **only explains** the current state of engineering. It MUST NOT (and does not) make decisions, optimise, reprioritise, schedule, complete, apply, or create anything. No AI/ML/statistics/Bayesian/graph-optimisation/network/clustering/scheduling. The frozen Apply gate remains the sole setup-mutation route and is byte-for-byte unchanged; campaign completion remains governed by Phase 18.

## 1. Architecture position
```
... engineering campaigns (P18) -> saturation/persistence/cost (P19)
    -> knowledge confidence / development ROI / campaign opportunity (P20)
    -> SEASON DEVELOPMENT PLAN + CROSS-CAMPAIGN KNOWLEDGE MAP (P21)
```
Phase 21 sits above Phase 20: it composes the Phase-18 programme once, derives the Phase-19 efficiency and Phase-20 knowledge-quality views purely from it (+ one registry read + one calibration read), joins them into one normalised record per campaign, and runs the three Phase-21 aggregators. It writes nothing.

## 2. Reused authorities (consumed, never recreated)
Campaign identity (objective family/region), objective mechanisms and experiment fields = **Phase 18**; per-campaign saturation signals + cost = **Phase 19**; confidence / ROI / opportunity = **Phase 20**; engineering value = **Phase 17** (via Phase 19, verbatim); prediction accuracy = **Phase 11** (via Phase 20). Phase 21 **recomputes none of them** — it only joins and aggregates.

## 3. Layer 1 — season development (`strategy/season_development.py`, pure)
`summarize_season(records, knowledge_states) -> SeasonDevelopment` — a programme-wide roll-up. Every metric is a `SeasonMetric` carrying **value + reason + source + calculation** (no hidden maths): `campaign_count`, `active_campaigns`, `completed_campaigns`, `campaigns_needing_confirmation`, `campaigns_plateaued`, `high_confidence_campaigns`, `low_confidence_campaigns`, `total_engineering_value` (sum of Phase-17 value), `total_remaining_value`, `estimated_remaining_cost` (Phase-19 laps/tyres/minutes), `knowledge_completion` (fraction of campaigns whose Phase-21 knowledge state is complete/well-understood), plus a plain-language `engineering_summary`.

## 4. Layer 2 — cross-campaign map (`strategy/cross_campaign_map.py`, pure)
`build_cross_campaign_map(campaigns) -> CrossCampaignMap` — deterministic **O(n²) pairwise** detection of *engineering* relationships (not execution dependencies, not a scheduler). Visible enum **`CampaignRelationship`**: `NONE`, `RELATED`, `OVERLAPS`, `SUPPORTS`, `DEPENDS_ON`, `DUPLICATES`, `CONTRADICTS`, `BLOCKED_BY`, `ISOLATED`. Every edge carries a **reason**, **supporting_evidence** and the **authority** it came from — nothing is inferred: if no rule's concrete evidence is present, the pair has no relationship.

**Relationship rules (priority order, each evidence-grounded):**
1. **DUPLICATES** — same objective (family+region) *and* the identical target field(s), both testable → duplicated effort.
2. **CONTRADICTS** — same family, one confident + the other contradictory → conflicting conclusions in one system.
3. **DEPENDS_ON / SUPPORTS** — a shared physical mechanism (Phase-18 `source_mechanisms`) with a confidence asymmetry: a campaign that still needs a mechanism the other has validated → DEPENDS_ON; a confident campaign whose mechanism supports another still building confidence → SUPPORTS (both directional).
4. **OVERLAPS** — same objective (family+region), concurrent but not identical.
5. **BLOCKED_BY** — same family (different region), the related campaign has unresolved conflicting evidence and this one needs progress (directional).
6. **RELATED** — same vehicle system (family), different region.
7. **RELATED** — a shared physical mechanism with no confidence asymmetry.
8. **OVERLAPS** — different systems, but the same setup field is being changed (may interact).
9. **ISOLATED** — a campaign that ends up in no relationship with any other.

This is plain deterministic aggregation — **not** graph search, clustering, ML or network optimisation.

## 5. Layer 3 — season knowledge map (`strategy/season_knowledge_map.py`, pure)
`classify_campaign_knowledge(record) -> CampaignKnowledgeState` — a deterministic ladder over Phase-18 status + Phase-19 saturation + Phase-20 confidence/opportunity producing one visible state: `ENGINEERING_COMPLETE`, `WELL_UNDERSTOOD`, `EMERGING_CONFIDENCE`, `NEEDS_CONFIRMATION`, `CONTRADICTORY`, `LITTLE_EVIDENCE`, `NO_USEFUL_EXPERIMENTS`, `KNOWLEDGE_PLATEAU`, `UNKNOWN`. Each state carries a `reason`, the `source` authority and a visible `factors` block.

## 6. Layer 4 — season engineering report (`strategy/season_engineering_report.py`, pure orchestration)
`build_season_report(programme, efficiency, quality) -> SeasonEngineeringReport` joins the three per-campaign views by `campaign_id` into one normalised record each (identity/fields/mechanisms + saturation signals + Phase-17 value + Phase-20 confidence/opportunity), then runs Layers 1–3. It **preserves the incoming campaign order** (no re-sort), assembles a context summary + development summary + relationships + knowledge map + the traceable normalised campaigns, and a deterministic `content_fingerprint`. Renderer `strategy/season_engineering_report_render.py` (strings only; no Apply/freeze/complete/schedule wording).

## 7. SessionDB query shape
`SessionDB.build_season_engineering_report(**ctx, applied_setup=..., now_date=...)` composes the Phase-18 `build_engineering_campaign_programme` aggregate **once**, derives the Phase-19 efficiency and Phase-20 quality views **purely** from it (+ one registry read + one calibration read — no double programme build), then runs the pure Phase-21 aggregators. Proven: query count is **constant regardless of campaign count** (no N+1), the empty path is cheap, and the renderer touches no DB. Writes nothing; DB stays v26.

## 8. Threading & UI
`EngineeringSeasonPanel` (+ pure `ui/engineering_season_vm.py`, renderer above) embedded in the **Development History** page beneath the Phase-20 confidence panel. It shows the season overview (with each metric's source/calculation), the cross-campaign relationship map (every edge explained) and the per-campaign knowledge map. **No Apply / Approve / Freeze / Complete / Execute / edit / schedule control** — only the page's existing refresh drives it (asserted). The build runs OFF the Qt thread via the reused `MechanismAnnotationWorker(QThread)`; the renderer performs no DB calls. All prior panels (Phase 12/19/20) coexist unchanged (asserted).

## 9. Determinism
Identical canonical inputs (+ the same `now_date`) → identical summary metrics, relationship edges, knowledge states, order, `to_dict()` and `content_fingerprint`; verified across repeated calls, large campaign counts and DB restart. No timestamps / random / row order / object addresses; dict/JSON ordering is stable.

## 10. Safety boundaries (proven)
No setup / experiment / outcome / record / registry mutation (runtime path writes nothing; `user_version` stays 26); no Apply / approve / freeze / complete / execute / **schedule** authority; **completion stays Phase-18-governed** (the knowledge map reads status, never sets it); every measure reused, nothing recomputed; **no optimiser / graph search / clustering / ML / statistics** (no `optimi`/`argmax`/`heapq`/`rank`/`dijkstra`/`kmeans`/`sklearn`/`numpy`/`networkx` in any Phase-21 module); every relationship carries supporting evidence + an authority (no inference); pure domain is Qt-free, DB-free, network-free, AI-free, random-free, wall-clock-free; the frozen Apply gate, config identity, fan-out allowlist, `RULE_ENGINE_VERSION` 46.0 and `DB_VERSION` 26 are unchanged; protected runtime files git-verified byte-identical.

## 11. Persistence decision — NONE
The season summary, relationships and knowledge map are pure functions of the reconstructed campaign programme + existing immutable records. No schema change is required; `DB_VERSION` stays **26** and `PRAGMA user_version` is verified 26 after every build path.

## 12. Tests
| File | Cases | Focus |
|---|---|---|
| `tests/test_phase21_knowledge_map.py` | 15 | every state reachable + explained + sourced, determinism, garbage-safe |
| `tests/test_phase21_relationships.py` | 16 | every relationship type reachable + evidence-grounded, isolated detection, large-count, duplicate-id, determinism, no graph-optimisation |
| `tests/test_phase21_development.py` | 10 | metric counts/totals with reason/source/calculation, report assembly (all 3 layers), order preserved, empty, garbage-safe |
| `tests/test_phase21_golden.py` | 6 | scenarios A–B + real production path (writes nothing) + restart determinism + empty DB |
| `tests/test_phase21_query_shape.py` | 3 | one build, constant query count (no N+1), cheap empty, renderer-no-DB |
| `tests/test_phase21_safety.py` | 12 | no forbidden imports/wall-clock, no scheduling/execution, no optimiser/graph-search, evidence-grounded edges, no-write, completion-stays-Phase-18, no-AI scan |
| `tests/test_phase21_ui_construction.py` | 7 | panel/page, no mutation controls, None-safe, prior-phase coexistence, off-thread |

All 72 pass. Phase 18–20 non-UI regression (incl. the touched `session_db` / `dashboard` / `development_history_page`) green; no-AI architecture guard green.

## 13. Golden UAT results
- **A (single campaign):** a knowledge map entry + a season summary appear; relationships object present.
- **B (two vehicle systems):** both campaigns mapped; relationships computed (possibly isolated) from the concrete shared/distinct attributes.
- **Relationship examples (synthetic):** two same-objective campaigns changing the same field → DUPLICATES; a low-confidence traction campaign needing a mechanism another rotation campaign has validated → DEPENDS_ON; a braking campaign sharing nothing → ISOLATED.

## 14. Known limitations
- Relationships are grounded in the coarse attributes the upstream authorities expose (objective family/region, `source_mechanisms`, target fields, confidence/opportunity) — subtler couplings not represented in those attributes are deliberately not inferred.
- `knowledge_completion` counts campaigns in the "understood/complete" states; it is a transparent ratio, not a weighted progress model.
- The season view is per-context (car/track/discipline); a true multi-event/season roll-up across contexts is deferred (would require iterating contexts, out of scope here).
- Detection is O(n²) pairwise; fine for realistic campaign counts (tens) and proven deterministic for 40 campaigns, but not intended for thousands.

## 15. Manual UAT
Porsche 911 RSR '17 @ Fuji: build several recurring diagnoses across sessions and systems; open Development History → Season Development Plan; confirm the season overview shows counts/values/knowledge-completion each with a visible source/calculation, the relationship map lists every edge with a reason + evidence + authority (or marks a campaign isolated), and the knowledge map classifies each campaign with a reason; confirm no mutation control and no schedule/complete button; confirm a Phase-18 COMPLETED campaign reads ENGINEERING_COMPLETE; restart and confirm identical output + fingerprint; confirm no protected runtime file changed, no DB row was written and `user_version` stays 26; confirm the Phase 12/19/20 panels are still present.

## 16. Deferred work / recommended Phase 22
**Phase 22 — Multi-Event Season Roll-Up & Engineering Narrative (advisory):** aggregate the per-context season reports across events/tracks into a single programme-level knowledge narrative (which systems are understood across the whole car, where cross-event transfer is proven, where the biggest programme-wide questions remain) — still read-only, still reusing Phases 17–21, no optimiser, no scheduling, no auto-completion. Not started.
