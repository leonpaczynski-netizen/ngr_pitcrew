# Engineering Brain — Phase 51: NGR Event Command Centre

Program 2, Phase 51. Read-only, deterministic, offline, no AI. Makes the active Event Preparation Cycle
the **primary application Home and navigation spine**.

## Active-cycle resolution (Audit D remediation)

`strategy/active_cycle_resolution.py::resolve_active_cycle` → one of eight states: `NO_ACTIVE_EVENT`,
`ONE_ACTIVE_EVENT`, `MULTIPLE_ACTIVE_EVENTS`, `UPCOMING_EVENT`, `PAUSED_EVENT`, `EVENT_REQUIRES_SELECTION`,
`EVENT_CONTEXT_CHANGED`, `EVENT_BLOCKED`. Rules (in order): an explicit `selected_cycle_id` matching a
non-terminal candidate wins; no candidates / only terminal → `NO_ACTIVE_EVENT`; exactly one non-terminal
→ its state (blocked > context-changed > paused > upcoming > active); **more than one → `EVENT_REQUIRES_
SELECTION`** (never silently picks the newest row / latest timestamp). A user-selected cycle is
**operational navigation state** — the candidate-membership fingerprint is identical whether or not one is
selected, so selecting a cycle never alters an engineering fingerprint or historical evidence. `now_date`
classifies `UPCOMING` but is excluded from the fingerprint.

## Event Command Centre

`strategy/event_command_centre.py::build_event_command_centre` — orchestration over the resolution +
`SessionDB.build_event_preparation_report`; writes nothing. Produces:

- **ONE primary next action** by deterministic priority: create-event / select-event / resolve-blocker /
  review-revision → bind-session → complete-debrief → finalise-strategy → lock-setup → the cumulative
  objective. Never several contradictory primaries.
- Attention items (event revision, pending binding, pending debrief, missing required setup).
- Per-dimension readiness, cumulative progress, 11 quick-action navigation surfaces, preparation timeline.
- `command_centre_to_dict` serialises to the immutable view dict (countdown + resolution state are
  display, not in the fingerprint).

## Home integration (post `/ui-ux-pro-max` gate)

`ui/event_command_centre_vm.py` (Qt-free) + `ui/event_command_centre_panel.py` render the status hero,
prominent primary action, explicit event selector (only when several cycles are open), readiness grid,
cumulative-learning card, timeline strip and quick-action navigation. The panel is the **first widget in
the Home tab**. `ui/dashboard.py` rebuilds it **off the Qt thread** (`_refresh_event_command_centre` +
`MechanismAnnotationWorker` + a stale-result guard `_on_event_command_centre_ready`), showing a loading
state while building. `_cc_navigate` maps a surface to a specialist tab; `_cc_select_active_cycle` persists
`config["active_cycle_id"]` (operational only) and refreshes. `SessionDB.build_event_command_centre_view`
resolves candidates once + the selected report once (constant query count, no N+1); a Home refresh writes
nothing.

## Design decisions (`/ui-ux-pro-max`)

Adopted: Real-Time/Operations IA (status hero + one primary CTA + key metrics + timeline + navigation);
loading-state feedback for the async refresh; explicit event selector (never auto-pick); NGR status tones;
tag-not-colour. Rejected/deferred: the engine's Fira/blue-amber palette and marketing hero/CTA framing
(kept the NGR brand and a status hero).

## Tests

`test_phase51_command_centre.py` (17), `test_phase51_command_centre_ui.py` (6),
`test_phase51_dashboard_integration.py` (7).
