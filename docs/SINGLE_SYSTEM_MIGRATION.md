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
| ~~`_event_list`, `_on_event_set_active`~~ | Event CRUD in a QListWidget | ✅ **severed (Stage 3)** |
| `_persist_config` | Config write — a service, injected | Stage 5 |
| `_tabs`, `get_tab_index`, `select_tab` | Library panel borrowing | Stage 4 |
| `_record_driver_feedback` | Logic in a mixin | Stage 2 |
| `_build_event_context`, `_build_session_context` | Thin adapters over pure builders | Stage 5 (trivial) |
| `_setup_authority` | Already a data-layer object | Stage 5 (inject directly) |
| `_driving_advisor`, `_tracker`, `_dispatcher`, `_announcer` | Already services from `main.py` | Stage 5 (inject directly) |
| `_last_race_plan_result`, `approve_race_plan` | Strategy result cache | Stage 5 |
| `config_path`, `bridge` | Already plumbing | Stage 5 |

Nothing on that list is unbounded. It is ~15 real extractions.

## 2b. What earns its place — keep / redesign / scrap

**Direction (user, 2026-07-23):** *"I don't want you to replicate the old program. I want
the new program to be the clean, user-friendly version it should be. We can scrap what's
no longer needed."*

So this is **not a port**. The domain layer is the asset and is reused wholesale; the
classic *views* are evidence of what the app does, not a specification of how it should
look. Each classic tab has to justify itself against the guided race-weekend flow.

| # | Classic tab | Verdict | Why |
|---|---|---|---|
| 0 | Home | **SCRAP** | The new Home is the Command Centre; the old one is a weaker duplicate |
| 1 | Live Race Engineer | **SCRAP** | Live Pit Wall replaces it |
| 2 | Event Planner | **REDESIGN** | Capability needed (create/edit/activate). 18 fields dumped in one form becomes a short guided event setup — most fields have sane defaults and only matter for some events |
| 3 | Garage (car browser) | **FOLD** | Browsing cars/specs/BOP is part of choosing the event's car, not a destination |
| 4 | Setup Builder | **ENGINE KEPT, VIEW SCRAPPED** | The engine becomes the Stage-2 service; the new Garage is already the better surface |
| 5 | Practice Review | **SCRAP** | Native Practice → Review is live and confirmed working |
| 6 | Strategy Builder | **REDESIGN** | Race Strategy exists but still needs a native "build the plan" trigger |
| 7 | Telemetry | **SCRAP** | Developer diagnostic; the driver never needs a packet view |
| 8 | Diagnostics | **SCRAP** | Same |
| 9 | Settings | **SCRAP** | Native Settings exists |
| 10 | History | **FOLD** | Past sessions belong in Debrief / Engineering Library, not a filtered table |
| 12 | Track Modelling | **REDESIGN** | Capability needed — see Stage 4b. Rebuilt as a guided flow over the existing coordinator, NOT as the 14-section tab |
| 13 | Development History | **FOLD** | Already reached through the Engineering Library |

Net: of thirteen classic tabs, **two capabilities need a new native surface** (event
setup, track modelling), one needs a trigger (build plan), one engine moves behind a
service, and the rest are duplicates or developer tooling that go.

**The test for "no longer needed" is not "unused code" — it is "no longer part of the
job".** Nothing that is still the only way to do something gets scrapped; the fold rows
above mean the capability survives somewhere better, not that it disappears.

## 3. Order — and why deletion is LAST

The app is in active race-preparation use. Deleting the classic window before its logic
is extracted would not "simplify" anything, it would remove the setup engine. Each stage
below leaves the app fully working, and only the final stage deletes anything.

### Stage 1 — state out of the widget tree ✅ DONE (both keystones)

The same defect appears twice: the working state of a job lives in Qt widgets, so the
job cannot run without the old UI. Both are now plain data.

**1a — the setup sheet**
`strategy/setup_sheet.py`: a pure, typed, normalising `SetupSheet` value object whose
fields mirror `_current_setup_dict` exactly, with `merge`/`diff`/`is_authored`. Context
fields (car, track, `captured_at`) are excluded from `diff`, so re-reading a sheet is
correctly *no change*. 24 tests.

**1b — the track modelling session**
`data/track_modelling_session.py`: the modelling job's working state as a value —
selection, capture flags, artefacts, error — deriving `TrackModellingInputs` for the
existing pure coordinator. Replaces `_tm_build_coordinator_inputs`, which read combo
boxes and mixin attributes. Changing track clears the previous job's artefacts, so a
station map can never be carried onto the wrong layout. 27 tests.

**No behaviour change yet — these are the keystones the rest stands on.**

### Stage 2a — the setup engine, headless ✅ DONE
`services/setup_store.py` answers "who owns the setup values" with a file instead of a
`QDoubleSpinBox`: one working sheet per discipline per scope (car + track + **layout**),
atomic writes, corrupt file degrades to empty, both sheets persisted in one write.
Not a second source of truth for what is *applied* — `ActiveSetupAuthority` owns that.

`services/setup_service.py` is the same engine with the widgets removed, reusing the
baseline generator, the advisor, `analysis_inputs` and the authority unchanged. Every
operation returns a **result object**, which is the real fix for the reported hang:
`analyse` distinguishes ok-with-changes, ok-with-**no** changes (a success that says so),
unreadable reply, and failure — four states the scraped text box collapsed into one.
`build_initial_setup` reports each sheet individually, so a Qualifying sheet that did not
build is never implied to have built. 46 tests.

### Stage 2b — headless inputs ✅ / bridge switch ⏳
`services/setup_inputs.py` is **done**: it rebuilds the generators' input snapshot from
the DB and config, replacing `_build_setup_inputs`, `_load_car_specs_for_current` and
`_build_track_tune_profile_for_current`. The drivetrain and gear-count combo reads now
come from the car's own specs — where the classic form's autofill got them anyway.
Unresolvable inputs stay *unknown* rather than guessed; an unrated historical setup is
carried without a rating rather than assumed good. 12 tests.

**The bridge switch itself is not done.** It was prototyped and reverted rather than
half-landed. What it needs, in order:

1. `_feed_garage` reads the store, not `form.current_setup_dict()`; a defaults-only
   sheet must render as *no setup*, never as numbers nobody authored.
2. `_on_analyse` / `_on_build_baseline` call the service on a worker and report the
   returned result object. Spawning must be **injectable** — a real thread emitting a
   signal into a QObject the tests are tearing down segfaults, and the engine is
   synchronous precisely so the caller can choose.
3. `_on_apply` / `_on_revert` / `_on_applied_in_game` / `_on_tyre_change` → service.
4. **Seed the store from the classic sheets once per scope**, only where the store has
   nothing authored, so an in-progress setup is not lost on the switch.
5. A transitional write-through to the classic form while that window still exists, so
   it can never display numbers that disagree with the real sheet. Deleted in stage 6.
6. Realign the shell tests that currently assert the classic routing
   (`test_apply_routes_to_form_apply`, `test_revert_routes_to_window`, the V15 analyse
   settling tests, and the `_Win` fakes' `_setup_result_text`).

Item 6 is the bulk of it and is why this is its own pass: those tests encode the old
contract, and rewriting them carelessly would lose the regressions they protect.

### Stage 2 — reference: what is being extracted
Move the setup ENGINE out of `SetupBuilderMixin` into a service with no Qt import:
analyse, baseline build, apply, revert, autosave, applied-in-game. The classic Setup
Builder *view* is not reproduced — the new Garage already replaced it.
The inputs the service needs (car specs, ranges, event context, advisor) are already
pure or already injected. Deliverables: `services/setup_service.py`, the bridge switched
onto it, and `_setup_result_text` replaced by a real result object instead of the
text-box scraping currently used to detect that an analysis finished.
*Largest single stage; its own session.*

### Stage 3 — native event setup ✅ DONE (redesigned, not ported)
The classic Event Planner puts 18 fields in one form. Most have sane defaults and only
matter for some events, so the native version is a short guided setup — identity (name,
car, track, layout), then format (race type, laps/duration), with regulations
(tyre wear, fuel multiplier, mandatory stops, BOP, tuning, ABS, weather, damage, refuel
rate, allowed compounds) behind progressive disclosure and pre-filled. Writes through
`SessionDB` directly, replacing `_event_list`/`_on_event_set_active`.

**Delivered as four steps — identity → format → rules → confirm.** What makes it not the
old form:

* **Three fields can block you**, and only because nothing can guess them: name, car,
  track. Every regulation has a standard default and *cannot* stop you creating an event.
* **Format is a choice, not a form.** Pick "set number of laps" or "fixed length of
  time"; the field you do not need disappears. One number, not two.
* **Rules are folded away** behind one line — "Standard rules — nothing unusual about
  this event" — and open only if this event actually differs. An event that does differ
  opens them automatically and states what differs.
* **Confirm reads it back as a sentence:** *"A 120-minute race at Watkins Glen
  International in the Porsche Cayman GT4. Tyres wear at 4x. 1 mandatory pit stop."*
  That is the "did I get this right" check eighteen widgets could never give.
* **Switching to an event you already made is the same screen**, on step 1 — it is the
  same job, so it is not a different place.

`services/event_setup.py` performs it headlessly: validate → save → fan out the working
config → ensure exactly one preparation cycle (an event without one is invisible to the
Command Centre) → activate → persist. A completed or abandoned cycle is never silently
reopened, and rules are deliberately NOT duplicated into the config — every consumer
reads them DB-first, and a second copy is a second thing to go stale.

`_event_list`, `_on_event_set_active` and the Event Planner route are no longer used by
the shell. **The last "opens the classic window" route is gone.**

### Stage 4 — native engineering panels
The Library currently *borrows* the classic Development History tab widget. The panels
are already self-contained `QWidget`s fed by view models, so they can be constructed
directly by the shell and fed from the DB.

### Stage 4b — native Track Modelling — **CONFIRMED PORT, NOT RETIRE**
Decided by the user (2026-07-23): *"needs to be brought across, as not all tracks are
modelled yet."* It stays, so the new shell needs a real modelling surface.

**The raw 3,463 lines badly overstate this job.** Measured, the modelling stack is
already almost entirely extracted:

| Layer | Lines | State |
|---|---:|---|
| `data/track_*.py` (calibration, detection, review, resolver, truth, intelligence) | 7,738 | pure domain ✅ |
| `data/track_modelling_coordinator.py` | 315 | pure state machine (`derive_state`, 10 states, legal-action table) ✅ |
| `ui/track_modelling_vm.py` | 1,398 | **explicitly Qt-free** — every label, badge, button-state and error string ✅ |
| `data/track_modelling_session.py` | *new* | working state, headless ✅ **DONE** |
| `ui/track_modelling_ui.py` | 3,463 | ~890 widget construction + ~2,450 handlers gluing the above to widgets ❌ |

So the port is **rebuilding one view over a spine that already exists**, not
reimplementing track modelling. The only genuine logic in the mixin was
`_tm_build_coordinator_inputs`, which assembled coordinator inputs out of combo-box
reads and mixin attributes — now replaced by `TrackModellingSession.to_inputs()`.

Remaining for 4b: a `TrackModelling` page in the new shell, built as **one guided flow —
pick track → drive calibration laps → build → review corners → accept** — driven by the
coordinator's own state machine, not as a rebuild of the classic tab's fourteen
simultaneously-visible sections. Every string, badge and button state already comes from
the existing Qt-free VM, and the underlying calls (capture start/stop, build path,
detect segments, review actions, alignment, accept, refine, lap offset) are unchanged.
This is view work over a finished spine, not engineering work.

### Stage 5 — direct service injection
`launch_new_shell(services)` instead of `launch_new_shell(window)`. Mechanical once
1–4 are done.

### Stage 6 — delete
Remove `ui/dashboard.py`, `ui/setup_builder_ui.py`, `ui/setup_form_widget.py`,
`ui/event_planner_ui.py`, `ui/live_ui.py`, `ui/settings_ui.py`, `ui/race_plan_ui.py`,
`ui/tab_registry.py`, `ui/track_modelling_ui.py`, the `NGR_CLASSIC_UI` escape hatch and
`classic_ui_requested`. Everything the classic modules own must have a native equivalent
first — Stage 6 deletes nothing that is still the only way to do a job.

## 4. What "clean" means here, concretely

Rules this migration is held to, so "user-friendly" is a standard rather than a hope:

1. **One surface per job.** No screen exists because the old app had a tab for it.
2. **Progressive disclosure over field dumps.** An 18-field event form becomes identity +
   format, with regulations pre-filled and folded away.
3. **No developer tooling in the driver's product.** Telemetry and Diagnostics go.
4. **Every state says what to do next.** An empty or blocked surface explains the cause
   and the next action — the rule the UAT rounds kept proving.
5. **Nothing is deleted while it is the only way to do a job.**

## 5. Honest position

- Stages 1–6 are a **multi-session programme**, not one change. Stage 2 alone is a
  substantial piece of work.
- Until Stage 2 lands, the new shell *must* keep talking to `MainWindow` for setup
  operations. That is not a design choice to be argued with — it is where the code is.
- Nothing has been deleted. Deleting before extracting would break race preparation
  that is happening now.
- This is a **redesign that reuses a domain layer**, not a port. The two surfaces being
  rebuilt (event setup, track modelling) are being designed for the guided flow, and the
  classic versions are reference material for *what the app does*, not for how it looks.
