# NGR Pit Crew — Consolidated UAT Runbook

**Version:** 1.1 · **Date:** ___________ · **Build:** master @ `4e35f36` (post determinism rebuild + Sprint 10 UI + voice + codebase-audit hardening)
**Tester:** ___________

This is the **single, ordered UAT script** for the rebuilt app. It supersedes the
fragmented per-sprint checklists for acceptance purposes — use those only as
deep-dive references. One defect scheme throughout: **UAT-NNN** (log at the end).

> **v1.1 note:** the UI test surface is unchanged behaviourally, but `ui/dashboard.py`
> was decomposed into per-tab mixin modules (see **Appendix — Module map**). If you
> log a defect, the module map tells you which file owns that surface.

**Golden fixture used throughout:** Porsche 911 RSR '17 @ **Fuji International Speedway – Full Course**.

The app is fully **local, offline, deterministic** — no API key, no cloud, no
internet required. Everything below runs on your machine.

---

## 0. Pre-flight setup (~15 min — do this first or the session stalls)

| ✔ | Step | Expected |
|---|------|----------|
| ☐ | `pip install -r requirements.txt` | Completes without error |
| ☐ | (Voice queries only) `pip install pocketsphinx` | Installs; if the wheel fails to build on Py3.14, note it and skip Pass B §B4 |
| ☐ | (Optional, better voice path) `pip install pywin32` | Enables SAPI5; app still works without it |
| ☐ | Launch: `python main.py` | Window opens on the **Home** tab; no crash; console prints "SAPI5 ready" and either "Piper neural TTS active" or "Piper unavailable — using SAPI5" |
| ☐ | Settings tab → **Connection** → set **Host** = your PS5's IP, Port `33740` | Saved |
| ☐ | Event Planner → activate the Fuji/Porsche event (see §A4) | "Active event:" shows the event |

> **#1 gotcha:** default host is `127.0.0.1`. With no PS5 IP set, telemetry never
> arrives and the app looks "dead" — this is config, not a bug.

---

## PASS A — Offline (no PS5 required)

Exercises ~70% of the new-UI risk with zero hardware. Do this first.

### A1 · Launch & data safety
| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-A1.1 | Launch the app | Opens to Home; 12 tabs present: Home, Live Race Engineer, Event Planner, Garage, Setup Builder, Practice Review, Strategy Builder, Telemetry, Diagnostics, Settings, History, Track Modelling |
| ☐ | UAT-A1.2 | Close and relaunch | Reopens; your `config.json` and saved data intact (no reset) |

### A2 · Voice (Piper neural TTS + in-app voice management)
| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-A2.1 | Settings → **Test Voice** | Speaks "Radio check. This is your race engineer." in a **natural** (non-robotic) voice |
| ☐ | UAT-A2.2 | Settings → **Voice** dropdown | Lists 🎤 Natural (Piper) voices first (e.g. "Alan — Great Britain, medium"), then System voices |
| ☐ | UAT-A2.3 | Pick a different voice → **Save Settings** → Test Voice | New voice applies **without restart** |
| ☐ | UAT-A2.4 | Settings → **Download voice…** → pick one → wait | Downloads (~30–110 MB), appears in the Voice list and is auto-selected; Event Log shows "installed" |
| ☐ | UAT-A2.5 | Toggle Voice → a System (SAPI5) voice → Save → Test | Falls back to the system voice cleanly |

### A3 · Home — guided workflow stepper (Sprint 10)
| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-A3.1 | Open Home | A row of numbered stage chips (Event & Car → … → Live Race Review), coloured done/current/blocked/pending, with a single **next-action** bar below |
| ☐ | UAT-A3.2 | Press the **"Go to next step"** button | Jumps to the tab for the current stage |
| ☐ | UAT-A3.3 | With no event set, read the stepper | Early stages current/blocked; the next action points to Event Planner |

### A4 · Event Planner
| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-A4.1 | Create/select the Porsche @ Fuji event; set race length, BoP, tuning rules | Fields save |
| ☐ | UAT-A4.2 | **Set as Active** / **Save Event** | "Active event:" reflects it; Home stepper's "Event & Car" stage turns done |
| ☐ | UAT-A4.3 | (If applicable) set an ABS-disallowed event | Downstream setup/strategy respect the no-ABS rule |

### A5 · Setup Builder — advice cards + applied-in-GT7 3-state (Sprint 10 core)
| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-A5.1 | **Build Baseline (Race + Quali)** | Both Race and Qualifying forms populate with a complete safe setup |
| ☐ | UAT-A5.2 | **Save Setup** | Save status shows; the **apply-status label** reads amber "⚠ … change(s) waiting to be applied in GT7" |
| ☐ | UAT-A5.3 | Press **"Changes Applied in Game"** | Label turns green "✓ Setup confirmed applied in GT7"; Home stepper "Apply Setup in GT7" stage turns done |
| ☐ | UAT-A5.4 | Edit any field (e.g. Rear ARB), Save | Label returns to amber "⚠ N change(s) waiting…" listing the pending count |
| ☐ | UAT-A5.5 | Type a handling issue in the feeling box → **Analyse & Get Setup Fix** | Result panel shows **structured cards** at top: a decision banner + Approved changes / Preserved / Rejected tables (colour-toned), above the detailed analysis |
| ☐ | UAT-A5.6 | If a recommendation is approved, **Apply && Save recommendation** | Fields update + auto-save; apply-status returns to amber (pending in GT7 again) |
| ☐ | UAT-A5.7 | **Load Selected** on a saved setup | Fields repopulate; apply-status recomputes vs the last GT7 checkpoint |

### A6 · Strategy Builder — Build Race Plan from This Practice (Sprint 10)
> Uses the Fuji sample session that ships in the repo (no PS5 needed).

| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-A6.1 | Strategy → pick the Fuji session in the selector | Readiness label updates with a diagnostics message |
| ☐ | UAT-A6.2 | **Build Race Strategy** | Ranked candidate table (by total race time) + plan narrative; **no** setup fields are changed anywhere |
| ☐ | UAT-A6.3 | **Build Race Plan from This Practice** | A **bundle banner** appears above the plan: green (ready+confirmed) / amber (caveats) / red (not enough evidence), listing confidence + missing evidence + any staleness |
| ☐ | UAT-A6.4 | If setup was never confirmed in GT7 (skip A5.3), rebuild | Banner warns "Setup NOT confirmed applied in GT7 — press 'Changes Applied in Game'…" |
| ☐ | UAT-A6.5 | Confirm no plan ever fabricates a pit stop or authors a setup | Honest gaps/rejections shown instead |

### A7 · Track readiness (Fuji auto-ready — Sprint 3 defect fix)
| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-A7.1 | With Fuji active, check Home track card / Track Modelling | Fuji reads **READY** from disk **without** opening Track Modelling (the old "blocked on restart" defect is gone) |

### A8 · Persistence & History
| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-A8.1 | History tab | Prior sessions listed for the car/track |
| ☐ | UAT-A8.2 | Relaunch app, revisit Setup Builder | Saved setups + the GT7 apply-checkpoint survive restart |

---

## PASS B — Live (PS5 + GT7 + real driving)

Only these need hardware. Validates what automation cannot.

### B1 · Telemetry connection
| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-B1.1 | Start GT7 on the PS5, enter a session; app Host = PS5 IP | Status bar shows **connected**; packet rate ~ steady (Telemetry tab) |

### B2 · Live Race Engineer (voice cues + beeps)
| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-B2.1 | Drive a lap | Shift beep fires near the shift RPM; lap/fuel/tyre cues spoken in the **Piper** voice |
| ☐ | UAT-B2.2 | Cues interrupt cleanly | A new urgent cue cuts the previous one without artefacts |

### B3 · Practice capture → episodes & persistence (Sprints 4–5)
| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-B3.1 | Run several representative laps with a repeatable issue (e.g. corner-exit wheelspin) | Session saves; per-corner slip recorded |
| ☐ | UAT-B3.2 | Hit a kerb hard | Kerb-strike bottoming does **not** push a ride-height increase (anti-ratchet) |
| ☐ | UAT-B3.3 | 2 poor laps out of many | A one-off does **not** author a setup change; a same-corner issue on ≥ the recurrence threshold **does** become setup-eligible |

### B4 · Push-to-talk voice queries (needs pocketsphinx + a bound key)
| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-B4.1 | Settings → **Detect Button…** → press your PTT key | Binding saved and shown |
| ☐ | UAT-B4.2 | Settings → **Test PTT** | Radio down-click plays; status → TRANSMITTING → PROCESSING → RADIO READY; engineer responds |
| ☐ | UAT-B4.3 | Hold PTT, ask "how was that lap?" / "pit window?" / "strategy?" | Local transcription; a relevant spoken answer |
| ☐ | UAT-B4.4 | Speak nothing / mic muted | "Sorry, I did not catch that." (graceful, no crash) |

### B5 · Practice Review — driver feedback
| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-B5.1 | Rate a run **Better** / **Worse** per area | Captured; Home stepper "Driver Feedback" stage turns done |
| ☐ | UAT-B5.2 | **Analyse Feedback → Setup Fix** | Deterministic recommendation; positive feedback can veto low-confidence telemetry (no contradictory change) |

### B6 · Strategy from real laps
| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-B6.1 | Strategy → select your live session → Build Race Plan from This Practice | Plan reflects **your measured** pace/fuel/tyre wear; confidence rises vs the sample |

### B7 · Live replan (advisory placeholder — expected behaviour)
| ✔ | ID | Step | Expected |
|---|----|------|----------|
| ☐ | UAT-B7.1 | Mid-race, trigger a re-plan | Honest "Live mid-race re-plan is not available in this build" message; **no** pit call, **no** setup change (see Known Limitations) |

---

## Known limitations — DO NOT log these as defects

These are intentional/disclosed. Confirm the behaviour matches, don't file bugs:
- **Mid-race live re-plan** is not implemented — shows a labelled "not yet available" message; makes no pit calls.
- **Live Replan Readiness** panel is read-only/advisory only.
- **Track models** ship for **Fuji** (+ Daytona reference path); other tracks must be modelled in Track Modelling first. GT7 live `road_distance` semantics are formally unconfirmed beyond these.
- **Tyre degradation** is a disclosed lap-time-drift proxy (not tyre-temp telemetry).
- **Pit loss** is a manual field (seeded from the event).
- **Gearbox ratio ranges** use conservative constants (warn, never block).
- **PTT** requires `pocketsphinx` installed **and** a bound key; without either it is silent by design.
- Running the **automated** test suite in one shot may hit a PyQt teardown segfault on Win/Py3.14 — run in chunks. This is a test-harness artefact, not an app fault.

---

## Defect log (single scheme)

| ID | Pass/Step | Severity (Blocker/Major/Minor) | Description | Repro | Status |
|----|-----------|-------------------------------|-------------|-------|--------|
| UAT-001 | | | | | |
| UAT-002 | | | | | |
| UAT-003 | | | | | |

## Sign-off

| Pass | Result (Pass / Pass-with-issues / Fail) | Tester | Date |
|------|------------------------------------------|--------|------|
| A — Offline | | | |
| B — Live | | | |

**Overall UAT verdict:** ___________________________

---

## Appendix — Module map (where each UAT area lives)

`ui/dashboard.py` was decomposed from a ~9.1k-line monolith into a lean
orchestration core (~6.6k lines) plus **six per-tab mixins** that `MainWindow`
composes. Behaviour is unchanged — this map is for **defect triage**: when a step
fails, start in the module that owns that surface.

**MainWindow composition** (`ui/dashboard.py`):
`class MainWindow(TrackModellingMixin, SetupBuilderMixin, SettingsMixin, RacePlanMixin, EventPlannerMixin, LiveMixin, QMainWindow)`

| UAT area | Owning module(s) | Backing engine / data |
|----------|------------------|-----------------------|
| §0 launch, §A1 | `main.py`, `ui/dashboard.py` (MainWindow core), `config_paths.py` (config safety) | — |
| §A2 Voice + in-app voice manager | `ui/settings_ui.py` (`SettingsMixin` — picker/download), `voice/piper_tts.py`, `voice/announcer.py` | `voice/piper_models/*.onnx` |
| §A3 Home guided stepper | `ui/dashboard.py` (`_build_home_tab`), `ui/workflow_stepper_widget.py` | `ui/workflow_stepper.py`, `ui/home_dashboard_vm.py` |
| §A4 Event Planner | `ui/event_planner_ui.py` (`EventPlannerMixin`) — the 4 `config["strategy"]` writers stay in `ui/dashboard.py` (fan-out allowlist) | `data/event_context.py` |
| §A5 Setup Builder (advice cards + apply 3-state) | `ui/setup_builder_ui.py` (`SetupBuilderMixin`), `ui/setup_form_widget.py`, `ui/setup_advice_render.py` | `strategy/setup_diagnosis.py`, `strategy/setup_rule_engine.py`, `data/applied_checkpoint.py` |
| §A6 / §B6 Strategy · Race Plan · Practice→Strategy | `ui/race_plan_ui.py` (`RacePlanMixin`), `ui/race_strategy_vm.py`, `ui/race_strategy_readiness_vm.py` | `strategy/race_strategy_pipeline.py`, `strategy/race_strategy_from_session.py`, `strategy/practice_evidence_bundle.py` |
| §A7 Track readiness | `data/track_readiness.py`, `data/track_readiness_disk.py`, `ui/track_modelling_ui.py` (`TrackModellingMixin`) | `data/track_*` model stores |
| §A8 / §B history & persistence | `ui/dashboard.py` (History tab), `data/session_db.py` (atomic, additive migrations to v19) | `data/gt7_sessions.db` |
| §B1 Telemetry connection | `telemetry/listener.py`, `telemetry/packet.py` (Salsa20 decode), `telemetry/state.py` | — |
| §B2 Live Race Engineer (cues/beeps/panels) | `ui/live_ui.py` (`LiveMixin`), `voice/announcer.py` | `telemetry/state.py` |
| §B3 Practice capture → episodes/recurrence | `telemetry/slip_events.py`, `strategy/cross_lap_persistence.py`¹ | `data/session_db.py` (v18 store) |
| §B4 Push-to-talk voice queries | `voice/query_listener.py` (local PocketSphinx), `ui/settings_ui.py` (Detect/Test PTT) | — |
| §B5 Practice Review — driver feedback | `ui/dashboard.py` (Practice Review tab), `strategy/driving_advisor.py` | `data/session_db.py` (driver_feedback) |
| §B7 Live replan (advisory placeholder) | `ui/dashboard.py` (`_launch_replan_worker`), `strategy/race_strategy_replan.py` | — |

Tabs still living in the `ui/dashboard.py` core (smaller, not yet extracted):
**Garage, Practice Review, Telemetry, Diagnostics, History**.

¹ `strategy/cross_lap_persistence.py`, `strategy/setup_decision.py` (arbitration),
`strategy/tyre_curves.py`, `strategy/feasibility.py`/`outcome.py` are marked
**⚠ EXPERIMENTAL — not wired into the live UI path** (validated by the golden-UAT
gates directly, not by driving the app). A hands-on tester won't exercise them;
see `tests/test_engine_wiring_status.py` for the enforced live-vs-experimental
registry. The live setup path uses `setup_diagnosis`/`setup_rule_engine`.
