# NGR Pit Crew — Current-State UI Audit (Stage 1, UI Rebuild)

**Status:** Read-only audit. No code, runtime data, or branches were changed to produce this.
**Date:** 2026-07-22
**Author:** UI Rebuild — Stage 1 (audit)
**Method:** Four parallel read-only code-audit passes over the shell, setup/garage, live+strategy+track, and event+debrief+library surfaces, cross-referenced against `strategy/`, `data/`, `telemetry/`, `voice/`.

---

## 0. Start-State Verification

| Item | Value |
|---|---|
| Working branch (at audit start) | `uat-defect-073-navigation-and-home-state` @ `ec486eb` |
| This branch vs remote | **Already merged** — `ec486eb` is an ancestor of `origin/master` |
| True `origin/master` (freshly fetched) | `d79a5eb` (PR #80 tip; includes `c87c484` / PR #78) |
| Local `master` | `ecf922c` — **33 commits stale**, fast-forwardable to `d79a5eb` |
| `DB_VERSION` (`strategy/_setup_constants.py:132`) | **28** |
| `RULE_ENGINE_VERSION` (`strategy/_setup_constants.py:79`) | **"46.0"** |
| Runtime files (17 M/??) | All `data/*`, `active_setup_state.json`, `.claude/settings.local.json` — user race-prep, **left untouched** |
| Branding assets in repo | **Only `logo.png`** (brief references *two* official logos — second is missing, see §9) |

**Branch plan:** the fresh rebuild branch must be cut from **`d79a5eb`** (the real current master), after fast-forwarding local `master`. Not from `ec486eb` and not from any historical phase hash.

---

## 1. UI Inventory (scale of the surface)

- **115 Python files** under `ui/`, **~39,440 LOC**.
- Dominated by a few monoliths:

| File | LOC | Role |
|---|---|---|
| `ui/dashboard.py` | 9,187 | `MainWindow` shell + Home + Telemetry + Diagnostics + History + Practice Review + Strategy Builder + Garage + Dev-History + all context builders |
| `ui/setup_builder_ui.py` | 4,783 | Setup Builder mixin (the two-panel setup maze) |
| `ui/track_modelling_ui.py` | 3,463 | Track Modelling mixin |
| `ui/setup_form_widget.py` | 1,066 | Reusable setup form (per discipline) |
| `ui/live_ui.py` | 1,007 | Live mixin |
| plus ~110 smaller VMs/panels | — | Mostly clean, pure, Qt-free view-models |

`MainWindow` is a 7-way multiple-inheritance composite:
`class MainWindow(TrackModellingMixin, SetupBuilderMixin, SettingsMixin, RacePlanMixin, EventPlannerMixin, LiveMixin, QMainWindow)` — `ui/dashboard.py:184`.

---

## 2. Current Navigation & Shell

- **Boot:** `main.py:main()` constructs the entire backend graph (queues, `RaceStateTracker`, `SessionDB`, `RaceStrategyEngine`, `DrivingAdvisor`, `UDPListener`, dispatcher) **before** the window, then `MainWindow(...)` at `main.py:613` with ~14 injected collaborators. A 200 ms `QTimer` drives connection status; a 100 ms `QTimer` (`ui.refresh_ms`) drains the UI queue.
- **Navigation model:** a single flat `QTabWidget` (`self._tabs`, `dashboard.py:415`). **No router, no stacked-page model, no side-nav, no breadcrumb.** Movement = tab click → `_on_tab_changed` (`:5205`) runs that tab's refresh.
- **Stable-key dispatch (a strength):** `ui/tab_registry.py` maps stable keys ↔ indices; programmatic nav is centralized in `select_tab(tab_key)` (`:499`, the only sanctioned `setCurrentIndex`). A persistent "⌂ Command Centre" corner button returns Home from any tab.
- **13 top-level tabs today:**

| Idx | Key | Title | Renderer |
|----|-----|-------|----------|
| 0 | `home` | Home (Command Centre) | `_build_home_tab` `dashboard.py:567` |
| 1 | `live` | Live Race Engineer | `LiveMixin._build_live_tab` `live_ui.py:46` |
| 2 | `event_planner` | Event Planner | `event_planner_ui.py` |
| 3 | `garage` | Garage | `_build_garage_tab` `dashboard.py:8852` |
| 4 | `setup_builder` | Setup Builder | `setup_builder_ui.py:4291` |
| 5 | `practice_review` | Practice Review | `dashboard.py:5468` |
| 6 | `strategy_builder` | Strategy Builder | `dashboard.py:5448` → `race_plan_ui.py` |
| 7 | `telemetry` | ⚙ Telemetry | `dashboard.py:1217` |
| 8 | `diagnostics` | ⚙ Diagnostics | `dashboard.py:1478` |
| 9 | `settings` | Settings | `settings_ui.py` |
| 10 | `history` | History | `dashboard.py:6469` |
| 11 | `track_modelling` | ⚙ Track Modelling | `track_modelling_ui.py` |
| 12 | `development_history` | Development History | `dashboard.py:6795` → `development_history_page.py` (45 panels / 5 subtabs) |

---

## 3. Architectural Strength to Preserve (the stable contract)

The **domain layer is clean, pure, deterministic and well-tested.** The dominant pattern is strict:

> **panel (Qt) → `*_vm.py` (pure, Qt-free) → `SessionDB.build_*` orchestration → `strategy/*` pure domain**

VMs hold no Qt and never raise; `SessionDB.build_*` methods are constant-query, read-only orchestrators. This separation is the rebuild's single biggest asset — **the new UI consumes these unchanged.** Canonical spines already exist for every workflow stage:

- **Event Programme:** `strategy/active_cycle_resolution.resolve_active_cycle` (deterministic active-event resolver; `EVENT_REQUIRES_SELECTION` when >1, never auto-picks) → `strategy/event_preparation_cycle.py` (lifecycle/phase/activity/readiness/progress/timeline) → `strategy/event_command_centre.build_event_command_centre` (picks the **one** primary next action) → `SessionDB.build_event_command_centre_view` (`data/session_db.py:6466`).
- **Guidance / next-action:** `event_command_centre._primary_next_action` (operational) + `strategy/race_engineer_team_brief.py` (deep development plan) via `SessionDB.build_race_engineer_team_brief`.
- **Setup brain:** `strategy/driving_advisor.build_combined_setup_response` (single entry) over `setup_baseline`, `setup_synthesis`, `setup_diagnosis`, `setup_ranges` (apply-gate clamp), `setup_decision`/`setup_decision_status`, `setup_lineage`, `setup_compliance`, `data/applied_checkpoint.py`, `data/setup_state_authority.py`.
- **Readiness gate:** `strategy/setup_strategy_readiness.build_setup_strategy_readiness` (LOCK_READY≠LOCKED; FINALISATION_READY≠FINALISED) over `setup_convergence` + `setup_lock` + `strategy_maturity`.
- **Strategy:** `strategy/race_strategy_pipeline.recommend_strategy_from_session` + `ui/race_strategy_vm.py` / `ui/race_strategy_readiness_vm.py` (measured-vs-assumed source tagging, confidence).
- **Live:** `strategy/canonical_live_race_state.build_canonical_live_race_state` → `adaptive_live_strategy.LiveStrategyState` → `live_audio_strategy_build` / `live_pit_wall_build`; `gt7_live_adapter`; `race_strategy_live_replan` (advisory).
- **Track model:** `ui/track_map_vm.py` (pure geometry + projection cache), `track_model_alignment_vm.py`, `data/track_map_matching.match_position_to_map` (HIGH/MEDIUM/LOW/UNKNOWN confidence), two model stores (reviewed-segments = AI-ready; track-library = seed/pit-lane).
- **Debrief / learning:** `strategy/binding_debrief_workflow.py` + `activity_binding.py`; `engineering_development_records` ledger; `strategy/engineering_knowledge_graph.py` + `programme_*` reports; `SessionDB.build_cross_session_memory`.

---

## 4. Problems Identified (why the UI is the product blocker)

1. **No guided journey / navigation shell.** Flat 13-tab bar; the intended "follow the bouncing ball" journey exists only as *unrendered* data (`ui/product_flow.py`, `ui/workflow_stepper.py`). The user must know which tab to click.
2. **State is fragmented** across `config.json`, `active_setup_state.json`, `gt7_sessions.db`, and transient `MainWindow` attributes — reconciled only by four `_build_*_context()` adapter methods on the QMainWindow. No single canonical application-state object for "active event + workflow stage + active setup."
3. **Setup two-panel maze.** `_build_car_setup_group` (`setup_builder_ui.py:887`) renders Race + Qualifying `SetupFormWidget`s **each in its own `QScrollArea`** inside a horizontal splitter; "Base" only appears inside HTML comparison blobs. Exactly the layout the rebuild must remove.
4. **Renderer-vs-plan divergence risk (correctness).** The recommendation *table* renders from `data["changes"]`, but *Apply* writes from `data["setup_fields"]` (`approved_fields`, numeric-only filtered). A third representation drives the compact field table. If these diverge, the driver **sees one change set but a different one is written.** Unifying on one source is the #1 correctness item.
5. **Live panels not truly live.** The "production" NGR pit-wall + VR-audio panels refresh **only on Live-tab activation** (`dashboard.py:5214`), *not per telemetry packet*. Per-packet updates today are the legacy label/tyre/fuel chrome + qualifying sector math. The rebuild must wire canonical live state to a throttled/coalesced per-frame feed (never a worker-per-packet).
6. **Two overlapping Home surfaces.** The live Event Command Centre vs a retained-but-unrendered legacy `home_dashboard_vm` + `workflow_stepper` stack. One canonical Home must be chosen (Command Centre wins).
7. **Guidance is buried & duplicated.** The deepest guidance (`race_engineer_team_brief`) is a *sub-panel of Development History*. The "bouncing ball" stepper is retained but dead. No first-class Pit Crew Engineer guidance surface.
8. **Debrief loop is UI-orphaned.** `binding_debrief_workflow` is canonical, but the Command Centre `debrief` action routes to Development History → "Overview & Records" (a catch-all). No dedicated Debrief surface.
9. **Engineering Library overload.** `development_history_page.py` already hosts **45 panels across 5 subtabs** — a de-facto library, but mixing primary-workflow guidance with developer/assurance depth.
10. **Theme applied inconsistently.** `ui/ngr_theme.py` is a clean token system, but much of `dashboard.py`, `widgets.py`, `guide_content.py` still use hard-coded hexes (`#0D1B2A`, `#2EA043`) instead of tokens.
11. **Dead plumbing.** `_build_home_dashboard_state`/`_home_*` (`dashboard.py:643-720`) and `home_dashboard_vm.py` feed only the retired stepper.

---

## 5. Component Classification (consolidated)

Legend: **REUSE** (consume as-is) · **WRAP** (keep logic/VM, re-skin/re-host presentation) · **RETIRE** · **EXTRACT** (hidden domain logic to move out of UI).

### Reuse — the stable domain/VM contract
`ui/ngr_theme.py`, `ui/tab_registry.py`, `ui/product_flow.py`, all pure VMs (`event_command_centre_vm`, `event_preparation_vm`, `development_history_vm`, `preflight_review_vm`, `postflight_review_vm`, `race_engineer_team_vm`, `assisted_runtime_vm`, `uat_runtime_vm`, `setup_recommendation_vm`, `setup_transcribe_view`, `race_strategy_vm`, `race_strategy_readiness_vm`, `live_engineering_vm`, `track_map_vm`, `track_model_alignment_vm`, `track_modelling_vm`), `ui/track_map_widget.py`, `ui/ngr_live_pit_wall_panel.py`, `ui/live_engineering_monitor.py`, `ui/race_strategy_uat.py`, `ui/car_ranges_dialog.py`. All `strategy/*` + `data/session_db.py build_*` + `data/*` domain modules named in §3.

### Wrap — re-skin / re-home, keep the VM contract
`main.py` (keep backend graph + threading; re-point window construction), `MainWindow` nav core (`_setup_ui`/`select_tab`/`_on_tab_changed`), `event_command_centre_panel`, `event_preparation_panel`, `preflight_review_panel`, `postflight_review_panel`, `race_engineer_team_panel`, `assisted_runtime_panel`, `setup_recommendation_view`, `race_plan_ui` (RacePlanMixin), `widgets.py` (tokenize), `guide_content.py` (keep content, drop bespoke styling), `development_history_page.py` (reframe as the Engineering Library shell).

### Retire
`ui/workflow_stepper.py` + `workflow_stepper_widget.py` (legacy bouncing ball, already un-rendered), `dashboard.py` `_build_home_dashboard_state` + `_home_*` stubs (`:643-720`), `ui/home_dashboard_vm.py` (confirm no other consumer first), the setup two-scroll `_build_car_setup_group` layout, legacy Home render (`:567-757`).

### Extract — hidden business logic to move into `strategy/`/`data/`
| Location | What to extract |
|---|---|
| `dashboard.py:1083-1181` | Learning-outcome verdict/evidence/persistence loop (owns the loop + `source_path='Analyse'` rule + DB writes) |
| `dashboard.py:70-127` | `_combine_driver_feedback_text`, `_verify_change_outcome` (+ `_FEEDBACK_TEXT_FIELDS`) — domain evidence helpers misfiled in UI |
| `dashboard.py:186-224` | `_TUNING_CATEGORIES` / `_SETUP_TUNING_GROUPS` — setup-field taxonomy (domain knowledge) as class attrs |
| `setup_form_widget.py:811` | Weather→Dry/Wet/Damp classification dict |
| `setup_form_widget.py:877,892` | Schema defaults / `_as_int` coercion (duplicates `setup_baseline` defaults) |
| `setup_form_widget.py:965` | `apply_ai_fields` rec-key→save-key remap + `gear_N`→`gear_ratios` mapping + `brake_bias`→`brake_bias_front` |
| `setup_builder_ui.py:2836` | `_build_setup_advice_cards` re-derives `DecisionStatus` in UI |
| `event_planner_ui.py:489-559` | `_ensure_active_preparation_cycle` — cycle-id slug + car-authority + terminal-preservation (Layer A↔B bridge) |
| `event_planner_ui.py:561-603` | `_on_event_set_active` activation side-effects (carefully — governance fan-out is a frozen allowlist) |
| `live_ui.py:707-773` | Qualifying sector/lap-projection math |
| `track_modelling_ui.py:1610-1620` | Car-dot world-XY recompute (duplicates `track_map_vm`) |
| `track_modelling_ui.py:2574` | Auto-promote UNREVIEWED→CONFIRMED review policy embedded in a button handler |

---

## 6. Safety Boundaries — confirmed intact today (must remain)

- Race Plan + Live Replan are **read-only, advisory**, manual-refresh, tagged "ADVISORY ONLY · NO PIT COMMAND"; the UAT harness (`race_strategy_uat.py:452`) asserts no setup-apply tokens.
- The NGR pit-wall + VR-audio panels issue **no** pit/tyre/fuel/setup command; voice off-by-default and gated; acknowledgement executes nothing.
- Live-progress stabiliser is display-only and "never touches pit corroboration, pit count, setup, or commands."
- The **only** UI paths that mutate strategy state are user-initiated Apply buttons (`_strategy_apply_plan` writes `config["strategy"]`; `_live_apply_strategy`). No silent pit call or setup apply exists.
- Apply gates: `setup_ranges` clamp on apply; `APPROVED_STATUSES`/`is_legacy_unknown` visibility gate; `applied_checkpoint` three-state (not saved / pending in GT7 / confirmed applied); `setup_state_authority` owns the active/applied identity.

The rebuild must **preserve every one of these** and add safety tests proving the new UI cannot bypass them.

---

## 7. Performance Notes (carry into rebuild)

- Per-packet path is currently light: `_update_live` is cache-deduped; 100 ms timer drains ≤5 packets/tick; track-map live update mutates only the car dot (projection cache avoids full reprojection). **Good — preserve.**
- `_poll_ui_queue` calls `_refresh_strategy_fuel_column` / `_refresh_gear_ratios` / `_update_telemetry_labels` every tick — verify these stay O(1) (not re-inspected; flag).
- Off-thread workers (`_refresh_live_pit_wall`, `_refresh_audio_engineer`, `_refresh_uat_runtime`) each spawn a `QThread`, currently tab-show only. **If the rebuild wires them per-frame they must be throttled/coalesced** — a worker-per-packet is the primary performance risk.
- `build_track_map_draw_data` is O(stations) (thousands of points at 1 m spacing); keep it off the telemetry path (rebuild-only).

---

## 8. State Ownership Map (fragmentation to consolidate)

| Concept | Current owner(s) |
|---|---|
| Active event profile | `config["active_event_id"]`, DB-first via `_active_event()` (`dashboard.py:6782`) |
| Active preparation cycle | `config["active_cycle_id"]` → `resolve_active_cycle` |
| Active / applied setup | `data/setup_state_authority.ActiveSetupAuthority` ← `active_setup_state.json` |
| "Setup running this stint" | `self._live_running_setup` (str) |
| Strategy plan | `config["strategy"]` → `build_strategy_context` |
| Live/session state | `RaceStateTracker` (volatile) → `build_session_context`; scattered `_live_*` attrs |
| Stage / journey position | Computed on demand (`workflow_stepper`, `product_flow`); **not stored** |

**Rebuild target:** one canonical application-state model (active event + preparation stage + active setup + session) that the shell, nav, event header, progress rail, and guidance all read from — assembled by a controller, not the QMainWindow.

---

## 9. Branding Gap

- Repo contains **one** logo: `logo.png` (1.7 MB, read-only via `ngr_theme.logo_path()` / `logo_pixmap()`; text fallback "NEXT GEAR RACING" when headless).
- The brief mandates using "one of the **two** official saved NGR logo files." The second (the "NEXT GEAR RACING // PIT CREW" mark) is **not in the repo** — it was pasted inline this session and cannot be used as a file.
- **Action required from user:** drop the second logo into the repo (suggested `assets/logo_pit_crew.png`). The design system will accept either mark, used unchanged (no recolour/crop/distort/redraw).

---

## 10. Rebuild Seams (where the new UI plugs in)

1. **Keep** `main.py`'s backend graph + threading; construct a new shell window instead of the mixin monolith.
2. **Keep** `tab_registry` key-based nav as the primitive; add a proper nav shell (left rail + event header + guided action area + progress rail) above it.
3. **Introduce** one canonical app-state controller consuming the existing `_build_*_context` adapters (relocated out of `MainWindow`).
4. **Consume** `SessionDB.build_*` + `strategy/*` unchanged; add **no** engineering logic to UI.
5. **Extract** the ~12 hidden-logic sites (§5) into `strategy/`/`data/` *before or alongside* re-homing each surface.
6. **Unify** the setup recommendation representation (one source for shown == applied) — the top correctness fix.
7. **Re-home** panels into a coherent IA: Home / Active Event (Programme) / Garage / Practice / Qualifying / Race Strategy / Live Pit Wall / Debrief / Engineering Library / Settings.
8. **Wire** canonical live state to a throttled per-frame feed; keep heavy geometry off the packet path.
9. **Promote** `race_engineer_team_brief` to the primary guidance surface; **retire** the stepper + dead Home plumbing.
10. **Reframe** `development_history_page` as the Engineering Library (progressive disclosure for assurance/UAT/knowledge depth).

---

*Next Stage-1 deliverables: Feature Factory decomposition (features/slices + acceptance criteria + dependency plan), UI/UX Pro Max design output (IA, navigation, journey map, design system/tokens, component hierarchy, interaction & accessibility), and `docs/NGR_PIT_CREW_UI_ARCHITECTURE.md`. Implementation is gated on user approval of this plan.*
