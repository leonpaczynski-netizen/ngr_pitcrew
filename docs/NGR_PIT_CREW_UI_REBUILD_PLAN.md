# NGR Pit Crew — UI Rebuild Plan (Feature Factory Decomposition + Migration + Test Plan)

**Status:** Stage-1 planning deliverable. Implementation gated on user approval.
**Date:** 2026-07-22
**Companions:** [`NGR_PIT_CREW_UI_AUDIT.md`](NGR_PIT_CREW_UI_AUDIT.md) · [`NGR_PIT_CREW_UI_ARCHITECTURE.md`](NGR_PIT_CREW_UI_ARCHITECTURE.md) · `NGR_PIT_CREW_UI_REBUILD_UAT.md`

---

## 1. Decomposition Method (Feature Factory)

The overhaul is decomposed into **10 feature epics** (F0–F9) mapped to the 8 migration stages. Each epic breaks into **slices** small enough for a focused commit, each with explicit acceptance criteria and a dependency order. This prevents an uncontrolled rewrite: the domain layer is the frozen contract; slices re-home presentation and extract hidden logic incrementally, with the new shell running alongside the old behind a launch flag until cutover.

**Traceability:** every slice cites the canonical services it consumes (never duplicates) and the audit component(s) it reuses/wraps/retires/extracts.

---

## 2. User Journey Map (the "bouncing ball")

| Stage | Page | Driver question | Primary action | Unblocks |
|---|---|---|---|---|
| Event Arrival | Active Event | What am I preparing for? | Begin Event Briefing | Briefing |
| Briefing | Active Event | What does this event demand? | Approve Practice Programme | Garage |
| Garage Prep | Garage | Which setup do I run? | Load Setup & Begin Run | Practice |
| Practice Run | Practice | What are we testing? | Start Practice Run | Review |
| Practice Review | Practice | Did it work? | (adaptive) Keep/Revert/Refine/Build next | Experiment / Quali |
| Experiment/Learning | Garage/Practice | Is the car better? | Build next setup | (loop) / Quali |
| Qualifying Prep | Qualifying | Am I ready? | Begin Qualifying | Strategy |
| Race Strategy | Race Strategy | What's the plan? | Approve Race Plan | Race |
| Live Pit Wall | Live Pit Wall | What do I do now? | (advisory only) | Debrief |
| Debrief | Debrief | What did we learn? | (state-based) Continue/Quali/Race/Close | next stage |
| Event Completion | Active Event | What carries forward? | Complete Event Programme | next event |

Each transition is gated: a stage is `blocked` until its precondition is met, and the reason is always shown (never a silent skip).

---

## 3. Feature Epics & Slices

### F0 — Foundations (Stage 2 pre-work)  ·  *no user-visible change*
Extract hidden logic + build the app-state spine before any surface moves.
| Slice | Acceptance criteria | Consumes / touches |
|---|---|---|
| F0.1 Extract setup-domain helpers | `_combine_driver_feedback_text`, `_verify_change_outcome`, `_TUNING_CATEGORIES/_SETUP_TUNING_GROUPS`, weather→condition, schema defaults, `apply_ai_fields` remap, decision-status derivation moved to `strategy/`/`data/` with unit tests; `dashboard.py`/`setup_form_widget.py` import them; behaviour identical (regression green). | audit §5 EXTRACT list |
| F0.2 Extract event/live/track logic | `_ensure_active_preparation_cycle` → `strategy/` cycle-provisioning service; qualifying sector math → live VM; car-dot recompute removed (use `track_map_vm`); auto-confirm review policy → domain. Tests added. | `event_planner_ui`, `live_ui`, `track_modelling_ui` |
| F0.3 `PitCrewController` + `AppState` | Canonical observable app-state assembled from relocated `_build_*_context` adapters; granular change signals; unit-tested; QMainWindow no longer owns context assembly. | `event_context`, `strategy_context`, `session_context`, authorities |
| F0.4 Theme token extension | New tokens (§2.2 of architecture) added to `ngr_theme.py` with pure QSS builders + tests; existing tokens unchanged. | `ngr_theme` |
| F0.5 Design-token adoption seam | Shared component base classes (Card, Badge, GuidanceCard, StatusPill, PrimaryAction) in a new `ui/components/` package, Qt widgets over pure VMs. | new package |

### F1 — Application Shell & Navigation (Stage 2)
| Slice | Acceptance criteria | Reuses |
|---|---|---|
| F1.1 Shell window + launch flag | New `PitCrewShell(QMainWindow)` constructed by `main.py` behind a config/env flag; old dashboard still default until cutover; app boots both. | `main.py` backend graph, `tab_registry` |
| F1.2 NavRail | Left rail, 10 items, icon+label, active highlight, blocked-with-reason, keyboard nav + focus ring; emits `navigate`. | `product_flow`, `tab_registry` |
| F1.3 EventHeaderBar | Persistent header bound to AppState; logo via `logo_pixmap` unchanged; connection + pit-crew + active-setup live. | `ngr_theme.logo_pixmap` |
| F1.4 ProgressRail | 8-stage rail with complete/current/available/blocked/not-required; navigates; reduced-motion aware. | `workflow_stepper` logic |
| F1.5 GuidedActionArea + EngineerGuidanceCard | Renders `_primary_next_action`/team-brief VM: message/objective/evidence/confidence/warnings/one primary + secondary + expander + read-aloud hook; empty/loading/blocked states. | `event_command_centre`, `race_engineer_team_brief` |
| F1.6 Home + Active Event pages | Home answers "what should I do?"; Active Event shows arrival + briefing (event/series/track/car/format/timeline/sessions/restrictions/weather/multipliers/pit reqs/known intel) + stage list. | `build_event_command_centre_view`, `event_preparation_cycle` |

### F2 — Garage / Setup Workspace (Stage 3)
| Slice | Acceptance criteria | Reuses |
|---|---|---|
| F2.1 SetupWorkspace + discipline selector | Single scroll region; segmented Base/Qual/Race swaps focused discipline; **no** side-by-side scroll panels; active-setup badge. | `setup_form_widget` (re-hosted) |
| F2.2 Unified recommendation representation | One VM drives both shown and applied; **shown == applied** proven by test; clamp via `setup_ranges`. | `setup_recommendation_vm`, `driving_advisor`, `setup_ranges` |
| F2.3 Apply/Save immediate refresh | After apply/save: values + badge + lineage + changed-fields refresh instantly; dual-store (config+DB) single path; 3-state applied checkpoint. | `applied_checkpoint`, `setup_state_authority`, `session_db` |
| F2.4 Setup lineage tree | Visual tree/timeline; nodes coloured by outcome (worse=DANGER); revert control; blocked-direction warning. | `setup_lineage`, DB experiments |
| F2.5 Setup comparison | current↔parent, base↔quali, quali↔race, recommended↔active, best↔current; changed value/direction/magnitude/reason/expected/outcome/proven-range/working-window. | `setup_recommendation_vm`, history |
| F2.6 RPM/Gearbox discipline objectives | Quali vs race objectives shown; not silently identical without explanation. | `gearbox_evidence`, `gearbox_format`, `shift_rpm_recommendation` |

### F3 — Practice & Experiment (Stage 4)
| Slice | Acceptance criteria | Reuses |
|---|---|---|
| F3.1 RunCard | Objective/setup/changes/expected/monitor/fuel/tyre/laps/push/purpose/invalidation; persists during run; Start Practice Run. | run inputs, setup context |
| F3.2 StructuredFeedbackForm | Dropdowns/segmented/scales/corner-selector; better/worse/unchanged prominent; free-text supplements only. | `setup_diagnosis.build_feedback_dispositions` |
| F3.3 Telemetry review + reconciliation | Findings/feedback/agreements/contradictions/confidence/what-changed/verdict. | `detect_diagnosis_contradictions`, practice evidence |
| F3.4 Adaptive outcome action | Primary action adapts to verdict (Keep/Revert/Refine/Gather/Build/→Quali); revert executes; failed direction blocked & warned. | `setup_lineage`, `learning_outcomes` |

### F4 — Qualifying (Stage 5a)
| Slice | Acceptance criteria | Reuses |
|---|---|---|
| F4.1 QualifyingReadiness checklist | All items with colour+icon+label; **Soft tyres** requirement visible; blockers listed. | `setup_strategy_readiness` |
| F4.2 Quali engineer explanation | What changed vs practice / why one-lap pace / what to protect / compromised-lap fallback; Begin Qualifying. | team brief, readiness |

### F5 — Race Strategy (Stage 5b)
| Slice | Acceptance criteria | Reuses |
|---|---|---|
| F5.1 StrategyPlanView | Recommended + alternatives; total time/laps; stint/tyre/fuel/pit windows; risks; confidence; measured-vs-assumed; replan triggers. | `race_strategy_pipeline`, `race_strategy_vm` |
| F5.2 No-Apply guarantee + approve | Zero setup-Apply controls on surface (safety test); Approve Race Plan. | `race_strategy_readiness_vm` |

### F6 — Live Pit Wall (Stage 6)
| Slice | Acceptance criteria | Reuses |
|---|---|---|
| F6.1 Glanceable KPI layout | Lap/pos/stint/fuel/tyre/pit-window/gap-to-plan as large KPIs; engineer instruction prominent; freshness+confidence always shown. | `canonical_live_race_state`, `live_pit_wall_build` |
| F6.2 Live track map trust tiers | Car position only when trustworthy; approved/fallback/low/none visibly distinct. | `track_map_vm`, `track_map_matching` |
| F6.3 Per-frame wiring (perf) | Incremental updates; throttled/coalesced worker; **no worker-per-packet**; heavy geometry off packet path; disconnect/stale/session-change handled. | tracker, workers |
| F6.4 Voice/PTT + advisory-only | Voice off-by-default, gated; replan advisory ("NO PIT COMMAND"); no silent command (safety test). | announcer, `query_listener`, `race_strategy_live_replan` |

### F7 — Debrief & Learning (Stage 7a)
| Slice | Acceptance criteria | Reuses |
|---|---|---|
| F7.1 DebriefView | happened/learned/improved/regressed/predictions/new-evidence/contradictions/setup+strategy outcomes/driver+track/corner findings/maturity; failed experiments visible. | `binding_debrief_workflow`, `postflight_review_vm`, `development_history_vm` |
| F7.2 State-based next action + event completion | Continue/Quali/Race/Close/Post-review; event summary + knowledge carry-forward. | `build_cross_session_memory`, programme reports |

### F8 — Engineering Library (Stage 7b)
| Slice | Acceptance criteria | Reuses |
|---|---|---|
| F8.1 Library shell (progressive disclosure) | Reframed `development_history_page`; advanced evidence/rule-trace/knowledge-graph/audit/assurance/UAT behind it; driver-facing answer first elsewhere. | `development_history_page` panels |
| F8.2 Relocate diagnostic surfaces | Telemetry/Diagnostics/Track Modelling/Event Planner moved off primary path into Library/Settings; still reachable. | those mixins |

### F9 — Cutover (Stage 8)
| Slice | Acceptance criteria |
|---|---|
| F9.1 Parity audit | Every old capability reachable in new UI or consciously retired (documented). |
| F9.2 Flip default surface | App opens into new shell; old dashboard no longer primary. |
| F9.3 Remove dead paths | Retire stepper + dead Home plumbing + duplicate renderers + two-scroll setup layout; migration notes kept. |
| F9.4 Final regression + safety + parity audit + completion report | Full inherited regression green; all safety tests pass; report produced. |

---

## 4. Dependency Order

```
F0 (foundations) → F1 (shell) → F2 (garage) → F3 (practice) → F4 (quali) ─┐
                                                    F5 (strategy) ─────────┤
                                                    F6 (live) ────────────┤→ F7 (debrief) → F8 (library) → F9 (cutover)
```
F4/F5 can proceed in parallel after F2/F3; F6 depends on F1 (shell) + live services; F9 requires all prior epics parity-complete.

---

## 5. Test Plan

### 5.1 Pure view-model / state tests (per epic)
Event-programme state · stage transitions · blocked transitions · recommended next action · engineer guidance · setup comparison · setup lineage · run-card formatting · feedback reconciliation · readiness state · empty states · confidence presentation · status presentation · live-state reduction · debrief VMs · navigation permissions · event-scoped setup filtering.

### 5.2 Safety tests (must all pass at cutover)
UI cannot: bypass setup Apply gates · silently apply setup changes · silently make pit calls · silently execute strategy changes · hide missing evidence · upgrade confidence without evidence · recommend illegal strategies · use fallback progress to corroborate pits · rewrite canonical diagnoses · create contradictory field states · mark incomplete experiments as complete setups · repeat failed directions without justified stronger evidence · write to setup history from read-only views · require an API key for deterministic functionality. (Extends existing `race_strategy_uat` no-apply-token assertions to every new surface.)

### 5.3 UI construction tests
Every new page constructs · navigation works · pages survive empty data / missing event context / no active session / low confidence / runtime error without crashing · controls enable/disable correctly · no nested-scroll chaos · primary actions remain visible · official NGR logo loads from the approved asset.

### 5.4 Regression (unchanged suites, kept green)
Full inherited regression (10k+) · UI-specific · strategy · setup brain · SessionDB · telemetry · track modelling · live strategy · safety & certification. **Golden fixtures never edited to hide failures** — every behavioural change investigated.

---

## 6. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Renderer-vs-plan setup divergence | F2.2 unifies representation; test asserts shown == applied. |
| Worker-per-packet perf regression on Live | F6.3 throttle/coalesce; heavy geometry off packet path; explicit perf note. |
| Two competing production UIs lingering | Launch flag + hard cutover in F9; old surface retired, not left. |
| Extracting `_on_event_set_active` breaks frozen fan-out allowlist | F0.2 extracts *around* the governance-pinned writers; regression + safety tests guard. |
| Runtime data / config clobber during dev | Never touch runtime files; use temp-config fixtures (existing guardrail). |
| Second NGR logo missing | Design accepts either mark; branding finalised when user supplies file. |
| PSVR2/live/voice/PTT not physically testable here | Labelled NOT TESTED in UAT; certification stays honest. |

---

## 7. Deliverables Checklist (Stage 1)

- [x] Current-state UI audit (`NGR_PIT_CREW_UI_AUDIT.md`)
- [x] Feature Factory decomposition (this doc §3)
- [x] UI/UX Pro Max design output (`NGR_PIT_CREW_UI_ARCHITECTURE.md` §2–4)
- [x] Information architecture (`…ARCHITECTURE.md` §3)
- [x] Navigation architecture (`…ARCHITECTURE.md` §3.1)
- [x] User journey map (this doc §2)
- [x] Design system & theme tokens (`…ARCHITECTURE.md` §2)
- [x] Component inventory (audit §5 + `…ARCHITECTURE.md` §4)
- [x] Migration plan (`…ARCHITECTURE.md` §10 + this doc §4)
- [x] Test plan (this doc §5)
- [ ] Manual UAT document (`NGR_PIT_CREW_UI_REBUILD_UAT.md`)
- [ ] **User approval to begin Stage 2 implementation**

---

*On approval: fast-forward local `master` to `d79a5eb`, cut branch `ui-rebuild-ngr-pit-crew`, begin F0. No implementation starts before sign-off.*
