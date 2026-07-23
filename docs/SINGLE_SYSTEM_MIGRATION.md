# Removing the classic UI — one system, measured

**Goal (user, 2026-07-23):** *"All wiring inserted into the new UI, no connectivity to the
old system, remove the old system completely. We should only have one proper system."*

Agreed as the destination. This document records what "the old system" actually **is**,
measured rather than assumed, and the order the pieces have to come out in — because the
classic window is not a skin over the app, it currently **contains** a large part of it.

---

## 1. What is actually there

| Module | Lines | What it really holds |
|---|---:|---|
| `ui/dashboard.py` | 9,129 | `MainWindow`, tab host, queue drains, ~14 tab builders |
| `ui/setup_builder_ui.py` | 4,795 | **`SetupBuilderMixin` — the setup engine wiring** |
| `ui/track_modelling_ui.py` | 3,463 | Track modelling workflow |
| `ui/live_ui.py` | 1,007 | Live tab |
| `ui/settings_ui.py` | 647 | Settings tab |
| `ui/event_planner_ui.py` | 622 | **Event CRUD + activation** |
| `ui/race_plan_ui.py` | 580 | Race plan tab |
| **Total** | **~20,243** | |

**The good news, measured:** every backend service is already built in `main.py` and
*injected* into `MainWindow` — tracker, announcer, db, dispatcher, strategy engine,
driving advisor, recorder, UDP listener, bridge, config. `MainWindow` **owns none of
them**. The domain layer (`strategy/`, `data/`, `telemetry/`, `voice/`) is pure and
tested and is not in question.

**The bad news, measured:** the *state* the app operates on lives in Qt widgets. The
authoritative value of every setup field is a `QDoubleSpinBox` on `SetupFormWidget`.
That is the single fact keeping the classic window load-bearing.

## 2. Every remaining dependency of the new shell on the classic window

Extracted from `ui/live_shell_bridge.py` + `ui/new_shell_launch.py` — this is the
complete list, and it is the definition of "done".

| Symbol | Category | Severed by |
|---|---|---|
| `_race_form`, `_qual_form` | **State in widgets** | Stage 1–2 |
| `_setup_result_text` | **A QTextEdit used as an IPC channel** | Stage 2 |
| `_setup_analyse_ai`, `_setup_analyse_ai_for_form` | Logic in a mixin | Stage 2 |
| `_generate_baseline_setup`, `_generate_baseline_setup_both` | Logic in a mixin | Stage 2 |
| `_on_changes_applied_in_game` | Logic in a mixin | Stage 2 |
| `_revert_last_change_for_form`, `_autosave_applied_setup` | Logic in a mixin | Stage 2 |
| `_event_list`, `_on_event_set_active`, `_persist_config` | Event CRUD in a QListWidget | Stage 3 |
| `_tabs`, `get_tab_index`, `select_tab` | Library panel borrowing | Stage 4 |
| `_record_driver_feedback` | Logic in a mixin | Stage 2 |
| `_build_event_context`, `_build_session_context` | Thin adapters over pure builders | Stage 5 (trivial) |
| `_setup_authority` | Already a data-layer object | Stage 5 (inject directly) |
| `_driving_advisor`, `_tracker`, `_dispatcher`, `_announcer` | Already services from `main.py` | Stage 5 (inject directly) |
| `_last_race_plan_result`, `approve_race_plan` | Strategy result cache | Stage 5 |
| `config_path`, `bridge` | Already plumbing | Stage 5 |

Nothing on that list is unbounded. It is ~15 real extractions.

## 3. Order — and why deletion is LAST

The app is in active race-preparation use. Deleting the classic window before its logic
is extracted would not "simplify" anything, it would remove the setup engine. Each stage
below leaves the app fully working, and only the final stage deletes anything.

### Stage 1 — the setup sheet becomes data ✅ DONE
`strategy/setup_sheet.py`: a pure, typed, normalising `SetupSheet` value object whose
fields mirror `_current_setup_dict` exactly, with `merge`/`diff`/`is_authored`. Context
fields (car, track, `captured_at`) are excluded from `diff`, so re-reading a sheet is
correctly *no change*. 24 tests. **No behaviour change yet — this is the keystone the
rest stands on.**

### Stage 2 — a headless setup service (the big one)
Move out of `SetupBuilderMixin`, into a service with no Qt import:
analyse, baseline build, apply, revert, autosave, applied-in-game.
The inputs it needs (car specs, ranges, event context, advisor) are already pure or
already injected. Deliverables: `services/setup_service.py`, the bridge switched onto
it, `_setup_result_text` replaced by a real result object instead of scraping a text box.
*This is the largest single stage and should be its own session.*

### Stage 3 — native event management
An event editor + activation in the new shell over `SessionDB` directly, replacing
`_event_list`/`_on_event_set_active`. Removes the last "opens the classic window" route.

### Stage 4 — native engineering panels
The Library currently *borrows* the classic Development History tab widget. The panels
are already self-contained `QWidget`s fed by view models, so they can be constructed
directly by the shell and fed from the DB.

### Stage 5 — direct service injection
`launch_new_shell(services)` instead of `launch_new_shell(window)`. Mechanical once
1–4 are done.

### Stage 6 — delete
Remove `ui/dashboard.py`, `ui/setup_builder_ui.py`, `ui/setup_form_widget.py`,
`ui/event_planner_ui.py`, `ui/live_ui.py`, `ui/settings_ui.py`, `ui/race_plan_ui.py`,
`ui/tab_registry.py`, the `NGR_CLASSIC_UI` escape hatch and `classic_ui_requested`.
Track modelling is the one open question — it has no new-shell equivalent yet and is
3,463 lines; either it gets a native surface in Stage 4 or it is deliberately retired.

## 4. Honest position

- Stages 1–6 are a **multi-session programme**, not one change. Stage 2 alone is a
  substantial piece of work.
- Until Stage 2 lands, the new shell *must* keep talking to `MainWindow` for setup
  operations. That is not a design choice to be argued with — it is where the code is.
- Nothing has been deleted. Deleting before extracting would break race preparation
  that is happening now.
