# Product Consolidation Audit — NGR Pit Crew (GT7 Pit Crew)

> Author: Product Consolidation Sprint · Date: 2026-07-03
> Scope: architecture clarity, UI flow, stale controls, duplicate workflows,
> single-source-of-truth. **No new features. No backend capability removed.**
>
> Companion docs: `docs/CURRENT_CLAUDE_HANDOFF.md`, `docs/PROJECT_STATE.md`,
> `MASTER_TESTING_REGISTER.md`, `REQUIREMENTS.md` (§12 UI spec).

---

## 0. How to read this document

The app is a mature, working product (~4,100 passing tests, 40+ feature groups).
It is **not** broken — it is **crowded**. Thirteen top-level tabs, built across
dozens of "Group 17x/2x/3x" iterations, mix the core race-engineer workflow with
developer/diagnostic tooling and accumulated jargon. This audit says what each
surface is, whether it should stay/move/rename/merge/hide/delete, where state
ownership is unclear, and proposes a target module structure. Section 8 lists
what this sprint actually changed (deliberately small and low-risk).

Verdict legend: **KEEP** · **MOVE** · **RENAME** · **MERGE** · **DELETE** ·
**HIDE_UNTIL_READY**.

---

## 1. Current top-level product areas

The dashboard exposes **13 tabs** (`ui/dashboard.py:536–548`), in this order:

| # | Tab | Builder | Role | Verdict |
|---|-----|---------|------|---------|
| 0 | Live Race Engineer | `_build_live_tab` (dashboard.py:554) | Workflow (live) | KEEP |
| 1 | Event Planner | `_build_event_planner_tab` (6587) | Workflow (setup) | KEEP |
| 2 | Garage | `_build_garage_tab` (7104) | Workflow (setup) | KEEP |
| 3 | Setup Builder | `_build_setup_builder_tab` (setup_builder_ui.py:1722) | Workflow (setup) | KEEP |
| 4 | Practice Review | `_build_practice_review_tab` (6059) | Workflow (analysis) | KEEP |
| 5 | Strategy Builder | `_build_strategy_builder_tab` (6040) | Workflow (strategy) | KEEP |
| 6 | Telemetry | `_build_telemetry_tab` (1272) | Diagnostic | RENAME/MARK (tool) |
| 7 | Debug → **Diagnostics** | `_build_debug_tab` (1487) | Diagnostic | RENAME (done) |
| 8 | Guide | `_build_guide_tab` (1472) | Support/help | KEEP + split content |
| 9 | Settings | `_build_settings_tab` (997) | Support/config | KEEP |
| 10 | History | `_build_history_tab` (6313) | Workflow (learning) | KEEP |
| 11 | AI Log | `_build_ai_log_tab` (1605) | Diagnostic | MARK (tool) |
| 12 | Track Modelling | `_build_track_modelling_tab` (track_modelling_ui.py:121) | Diagnostic/advanced | RENAME + MERGE internally |

### 1.1 The biggest structural gap: no "home / next action" surface

> **RESOLVED (2026-07-03, Home Dashboard Build sprint).** The Race Engineer
> Command Centre now exists: a **Home tab appended at index 13** rendering
> `ui/home_dashboard_vm.py` (event / track intelligence / setup / strategy /
> AI-input-safety cards + the suggested next action from
> `build_flow_state_summary`), built from the four canonical contexts.
> Display-only; tab indices 0–12 unchanged. Residual: the tab sits at the END
> of the tab bar until the index-by-lookup refactor lands (§9 risk note), and
> the telemetry-owned flags are approximations — see
> `docs/HOME_DASHBOARD_BUILD.md` §3/§6.

`REQUIREMENTS.md §12.1` specifies **9** tabs, the first being a **Dashboard**
home showing *"Next saved race, Active car, Active setup, Active strategy, Recent
sessions, **Suggested next action**"* (§12.2). **That home tab was never built.**
Instead the app grew **five** extra tabs that are largely tools — Telemetry,
Debug, Guide, AI Log, Track Modelling. So the product opens on the Live tab with
no overview of "where am I in the workflow / what should I do next," and the
normal 13-step journey (below) is not represented anywhere as a flow.

This sprint adds the *logic* for that surface (`ui/product_flow.py`
`build_flow_state_summary`) so a future home panel is a rendering job, not a
design job. See §7 and §8.

### 1.2 Intended user journey vs. where it lives today

| Step | Intended action | Primary tab today | Flow clear? |
|------|-----------------|-------------------|-------------|
| 1 | Select/create event | Event Planner | ✔ |
| 2 | Select car, track, layout, rules | Event Planner (+ Garage for car) | ⚠ car lives in Garage, track/layout also editable in Track Modelling |
| 3 | Confirm tuning legality & allowed changes | Event Planner → Setup Builder (read-only mirror) | ✔ |
| 4 | Capture practice telemetry | Live Race Engineer (Practice) | ✔ |
| 5 | Validate session/lap data quality | Practice Review | ⚠ quality diagnostics split with Track Modelling |
| 6 | Identify repeated issues by corner | Practice Review + Track Modelling | ⚠ split |
| 7 | Recommend driver-tailored setup | Setup Builder | ✔ |
| 8 | Validate setup improvement | Practice Review / Setup Builder | ⚠ manual |
| 9 | Build qualifying setup | Setup Builder | ✔ |
| 10 | Build race setup | Setup Builder | ✔ |
| 11 | Build race strategy | Strategy Builder | ✔ |
| 12 | Live pit-crew support | Live Race Engineer | ✔ |
| 13 | Save learning to history | History (+ DB) | ⚠ driver profile never aggregated (see §6, item 13) |

---

## 2. Per-tab UI inventory and verdicts

Only notable items are listed. Line numbers are `ui/dashboard.py` unless noted.

### 2.0 Live Race Engineer (tab 0) — KEEP
Panels: Tyres (649), Lap Times (653), Fuel (683), Shift Beep (692); mode-specific
Race/Practice/Qualifying sub-panels (749/830/873).

| Item | Verdict | Note |
|------|---------|------|
| Mode selector Race/Practice/Qualifying (588) | KEEP | Core |
| "Reset Session" button (610) | KEEP | Tooltip already clarifies history is preserved |
| Race panel status "No plan applied — run Race Strategy Analysis, then select and apply a strategy." (780) | KEEP wording, treat as empty-state | Correct guidance; consider muted styling |
| "Strategy Status: No plan loaded" (790) | KEEP | Accurate default |
| Shift-Beep RPM spinboxes (692) | KEEP | Also mirrored read-only in Setup Builder by design (Group 31) |

Group A already removed the dead live map widget and the auto-syncing session
combo — Live is one of the cleaner tabs.

### 2.1 Event Planner (tab 1) — KEEP
`_build_event_planner_tab` (6587). Event list + editor form; "Save Event" (6787),
"Set as Active" (6793).

| Item | Verdict | Note |
|------|---------|------|
| Full event editor | KEEP | This is the correct single owner of race rules |
| Nested "Tuning Permissions" group (6698) | KEEP | Correct home for allowed-tuning |
| "Set as Active" copies event → `config["strategy"]` | RENAME concept / see §5 SSOT-1 | The copy is the #1 state-duplication risk |

### 2.2 Garage (tab 2) — KEEP
Car list + specs, "Load to Event ↩" (7150), Setups table (7159), Track Setup
History (7174), Session History (7193).

| Item | Verdict | Note |
|------|---------|------|
| "No spec data available" (specs label) | KEEP | Legit empty-state |
| Session History table (7193) | MERGE candidate | Duplicates History tab content for the selected car; acceptable as a car-scoped view, but note the overlap |
| Setups table | KEEP | But setups have dual residence (config + DB) — see §5 SSOT-3 |

### 2.3 Setup Builder (tab 3) — KEEP
`setup_builder_ui.py`. Race-conditions mirror (1735), full car-setup form (89),
Analyse/Build/Apply AI actions, driver-feedback rating, shift-RPM (read-only).

| Item | Verdict | Note |
|------|---------|------|
| "Race Conditions (from Event Planner)" read-only group (1735) | KEEP | Good pattern: read-only mirror of the event owner |
| Warning "No active event — go to Event Planner and click 'Set as Active' first." (1730) | KEEP wording | Correct; hide when an event is active (minor) |
| Shift-RPM group "Shift RPM (auto-set by AI Build Setup)" read-only | KEEP | Owned by Live tab per Group 31 |
| "Build Setup with AI" vs "Analyse & Get Setup Fix" | KEEP | Two genuinely different actions (from-scratch vs telemetry-fix) — label wording is good |

### 2.4 Practice Review (tab 4) — KEEP
Session Summary (6067), Lap Data table (6094) with 15 columns incl. `Compound ✎`
/ `Setup ✎`, Practice AI Analysis (6167), Driver Feedback — After Stint (6207).

| Item | Verdict | Note |
|------|---------|------|
| Lap Data table + compound tagging | KEEP | Core |
| "Full Practice Analysis" button (6173) | KEEP | Tooltip is strong |
| Driver Feedback form (6207) | KEEP | Feeds AI; but see §6 item 13 (never aggregated into profile) |
| Session loader | (already removed) | Group 23-era: historical loading moved to History tab — good precedent for this sprint |

### 2.5 Strategy Builder (tab 5) — KEEP
Workflow guide (collapsible, 4072), AI Race Analysis (4157), Stint Plan (4264),
Tyre Reference Paces (4450).

| Item | Verdict | Note |
|------|---------|------|
| Collapsible "Show workflow guide" (4079) | KEEP | Good pattern — hides complexity by default |
| "Anthropic API Key" field (4194) | MERGE → Settings | Duplicate of the Settings key entry; keep one owner (Settings) and show status only here |
| "Race Config ID: <hash>" (4206) | HIDE_UNTIL_READY / RENAME | Internal 10-char hash surfaced to the user; move behind Diagnostics or relabel "Session match key" |
| Outlier-filter per-compound spinboxes (4502) | KEEP | Powerful; wording ("spin laps", "end-of-life worn laps") is jargon-ish but tooltip explains |
| "Fuel Burn (auto): … (last session)" (4173/4179) | RENAME | "(last session)" reads as stale; clarify source consistently (see §5 duplicate fuel) |

### 2.6 Telemetry (tab 6) — MARK AS TOOL (done), partial HIDE
Connection, Session, Live Packet Data (10 Hz), Lap Times, "Lap Events (last
completed lap)".

| Item | Verdict | Note |
|------|---------|------|
| Whole tab | MARK diagnostic (done — ⚙ prefix) | Raw packet inspector; useful but not a workflow step |
| "Position XYZ", "Road surface Y", "Tyre radius F/R" (1339–1341) | HIDE_UNTIL_READY | Raw field names; developer-facing |
| "Errors: N", "UDP listener: Starting…" (1302/1306) | KEEP under Diagnostics | Fine for a tool tab |
| Session/Car/Track/Setup rows (1313) | KEEP | Read-only mirror; harmless |

### 2.7 Debug → Diagnostics (tab 7) — RENAME (done), KEEP as tool
Connection counters, Tracker State, Raw Packet Fields, Announcer State, Gearbox
Analysis (last lap), Event log.

| Item | Verdict | Note |
|------|---------|------|
| Tab title "Debug" | RENAME → "Diagnostics" (**done**) | "Debug" is developer language |
| Raw fields "cars_in_race", "laps_in_race", "rem_ms(raw)", "on_track", "loading" (1525–1530) | KEEP under Diagnostics | Correct home for raw values |
| "Rem(clk)" vs "rem_ms(raw)" (1515/1527) | RENAME (later) | Inconsistent abbreviation pair |
| "Ann queue" (1540) | RENAME (later) | "Ann" = Announcer; spell out "Voice queue" |

### 2.8 Guide (tab 8) — KEEP, split content
Read-only HTML (`_GUIDE_HTML`, 76–235).

| Item | Verdict | Note |
|------|---------|------|
| 10-step workflow, PTT commands, compound tags, setup-field glossary | KEEP | Genuinely useful onboarding |
| Embedded telemetry reference ("72 fields… 368 bytes… IV 0xDEADBEEF") | MOVE → Diagnostics/docs | Developer reference inside a user guide |

### 2.9 Settings (tab 9) — KEEP
Game Data, Connection, Voice Alerts, Fuel, Voice Queries (PTT), Driver Profile,
**Developer** group (1242).

| Item | Verdict | Note |
|------|---------|------|
| "Developer" mode toggle (1242) | KEEP | Good — a gate already exists; AI-Log detail respects it |
| Tooltip "pip install requests beautifulsoup4" (1021) | MOVE | Dev setup instruction in a user tooltip |
| Driver Profile group | KEEP | But profile is never auto-updated — see §6 item 13 |
| API key entry | KEEP (canonical owner) | Strategy Builder's copy should defer to this |

### 2.10 History (tab 10) — KEEP
Filters (Car/Track/Type), sessions table, Session Detail, "Load into Practice
Review" (6376). Clean; the correct owner of historical session loading.

### 2.11 AI Log (tab 11) — MARK AS TOOL (done), gate DRY-RUN
List + Prompt/Payload/Response/Details sub-tabs; token/cost/status fields.

| Item | Verdict | Note |
|------|---------|------|
| Whole tab | MARK diagnostic (done) | Prompt/response audit — a tool |
| "DRY-RUN" status + "structured_payload" + validation warnings | KEEP but Developer-gated | Already partly gated by Developer Mode (1249) |
| Token/cost fields | KEEP | Standard for AI apps |

### 2.12 Track Modelling (tab 12) — RENAME + MERGE internally, HIDE legacy
The single largest consolidation target. Six numbered sections in
`track_modelling_ui.py`: 1. Seed Data, 2. Calibration, 3. Segment Detection,
4. Segment Review, 5. Seed Geometry (renamed this sprint), 6. Track Truth /
Mapping.

| Item | Verdict | Note |
|------|---------|------|
| Whole tab | MARK advanced (done — ⚙ prefix) | Calibration/geometry authoring; not a normal race step |
| Section 5 title "Track Model Alignment" (misleading — only builds seed geometry) | RENAME → "5. Seed Geometry" (**done**) | Alignment metrics actually live in Section 4 |
| "Resolver Status" panel (632) | RENAME → "Track Model Status" (**done**) | "Resolver" is an internal module name |
| 7 hidden legacy per-segment buttons — Confirm/Rename/Reject/Needs More Laps/Split Required/Merge Required/Save Reviewed Model (517–524) | DELETE (deferred — see §9) | Already `.hide()`; replaced by whole-model acceptance. Kept for now because handlers still `getattr` them; safe removal needs handler cleanup |
| Jargon: "Seed", "Station Map", "Extra peaks suppressed", "Lap offset", "AI context", "Complex metadata", "truth source" | RENAME (later) | Heavy internal vocabulary; needs a glossary pass (deferred, higher-risk) |
| Sections 4/5/6 overlap (alignment/geometry/truth all read the same model) | MERGE (later) | Candidate to collapse from 6 panels to ~3 |

---

## 3. Legacy / confusing UI elements (consolidated)

1. **Hidden legacy per-segment review buttons** (`track_modelling_ui.py:517–524`)
   — dead workflow replaced by whole-model acceptance; still instantiated.
2. **"Debug" tab name** — developer word in the top-level nav (**fixed** →
   Diagnostics).
3. **Section 5 "Track Model Alignment"** mislabelled — it builds seed geometry,
   not alignment (**fixed** → "5. Seed Geometry").
4. **"Resolver Status"** — internal term (**fixed** → "Track Model Status").
5. **"Race Config ID" hash** in Strategy Builder (4206) — internal identity leaked.
6. **Embedded 368-byte/IV-0xDEADBEEF telemetry reference** inside the user Guide.
7. **Inconsistent abbreviations** on the Diagnostics tab ("Rem(clk)" vs
   "rem_ms(raw)", "Ann queue").
8. **Track Modelling jargon wall** — Seed / Station Map / peaks / lap offset /
   truth source with no in-UI glossary.

---

## 4. Duplicate workflows / duplicate visible controls

| Duplicate | Where | Recommendation |
|-----------|-------|----------------|
| **Fuel burn per lap** | Telemetry "Fuel burn avg" (1335); Practice Review "Avg Fuel/Lap" (6083); Strategy Builder "Fuel Burn (auto)" (4173) | One owner (telemetry/recorder) → all three are read-only views. Standardise the source suffix wording; don't show "(last session)" next to a live value |
| **Anthropic API key entry** | Settings (canonical); Strategy Builder field (4194) | Settings owns it; Strategy Builder should show status ("key loaded ✓"), not a second editable field |
| **Compound tagging** | Practice Review lap table; History detail table | Acceptable (edit vs read) — document, don't merge |
| **Session history listing** | History tab; Garage "Session History" (7193) | Acceptable car-scoped view; note overlap |
| **Track/layout selection** | Event Planner (track name) **and** Track Modelling combos (`_tm_location_combo`/`_tm_layout_combo`) **and** `config["strategy"]` IDs | Real SSOT problem — see §5 SSOT-2 |
| **Car selection** | Garage list; `config["strategy"]["car"]`; setup form; dispatcher `car_id_ref` | Real SSOT problem — see §5 SSOT-4 |

---

## 5. Single source of truth — state ownership

For each state item: current owner, files/keys, whether duplicated, and the
recommended future owner (target context — see §7).

| # | State | Current owner(s) | Files / keys | Duplicated? | Recommended owner |
|---|-------|------------------|--------------|-------------|-------------------|
| 1 | Selected event | `config["active_event_id"]` **and** a copy fanned into `config["strategy"]` | dashboard.py:7032–7102; events table (session_db) | **YES (worst)** | **EventContext** — store only `active_event_id`; read fields from the DB event record |
| 2 | Selected track/layout | `config["strategy"]["track"]` (name) + `track_location_id`/`layout_id`; TM combos | dashboard.py:7041; track_modelling_ui.py:177–190, 923–924 | **YES** | **TrackContext** — one `{location_id, layout_id, display_name}` object; combos read/write it |
| 3 | Selected car | `config["strategy"]["car"]`; Garage list; setup form; dispatcher `car_id_ref` | dashboard.py:7396; setup_builder_ui.py:720–776; driving_advisor.py:711 | **YES** | **EventContext** (active car for the event); numeric id derived, not stored |
| 4 | Tuning rules (BoP + allowed) | `config["strategy"]["bop"/"tuning"/"allowed_tuning_categories"]`; Event checkboxes; events table | dashboard.py:7063–7067, 6708–6713 | Partial (widget vs config) | **EventContext** |
| 5 | Current session | Dispatcher `_session_id` (clean) | dashboard.py:968–972; session_db | Mostly clean; mode/tracker coupling loose | **SessionContext** |
| 6 | Lap validity (pit/out/outlier) | DB `is_pit_lap`/`is_out_lap`; outliers computed at analysis time | session_db.py:75–76; practice_analysis.py | Clean | **SessionContext** (DB-backed) |
| 7 | Reference path | Filesystem `<loc>__<lay>.reference_path.json`; loaded on demand | track_calibration_runtime.py; live_segment_resolver.py | Clean | **TrackContext** |
| 8 | Station map | Filesystem `*.station_map.json`; derived | track_station_map.py | Clean | **TrackContext** |
| 9 | Corner/segment model | Filesystem reviewed/accepted model; resolver picks best | track_segment_review.py; track_model_resolver.py | Clean | **TrackContext** |
| 10 | Setup diagnosis | Computed on demand, displayed, **never persisted** | setup_diagnosis.py; dashboard.py ~3500 | Transient (lost on close) | **SetupContext** (cache per car/track w/ timestamp) |
| 11 | AI setup prompt context | Assembled at call time from 6 sources, no freeze | driving_advisor.py:1272–1371 | Scattered | **SetupContext** builds a frozen snapshot per call |
| 12 | Strategy prompt context | `config["strategy"]` + live telemetry + DB history | ai_planner.py; config.json:43–104 | Scattered; can desync on event switch | **StrategyContext** frozen snapshot per call |
| 13 | Driver style profile | `user_profile` DB table — exists but **no UI writer, never aggregated** | session_db.py:193–200 | Under-used | **LearningContext** |
| 14 | Saved learning history | DB (sessions/laps/ai_interactions/setups); setups **also** in config | session_db; config["car_setup"]["setups"] | **YES (setups dual-resident)** | **LearningContext**; setups → DB only |

### 5.1 Worst SSOT violations (ranked)

1. **Event fan-out into `config["strategy"]`** — "Set as Active" copies event
   fields into a `strategy` blob that downstream code reads; edits to the event
   afterward don't propagate. *Highest impact, highest fix effort.*
2. **Track/layout split three ways** — name vs seed IDs vs TM combos; no
   guaranteed sync.
3. **Setups dual-resident** (config.json + DB) with migrate-on-init but no
   cleanup — can diverge.
4. **Car selection multi-writer** — Garage / config / setup form / dispatcher.
5. **Session mode ↔ tracker coupling** — mode combo change must call
   `set_session_type_override()`; not enforced by signal.
6. **Setup diagnosis transient** — recomputed every launch; no cache.
7. **Prompt context assembled live from 6 sources** with no consistency freeze.

> `config.json` currently behaves as a "god object." Target: config holds only
> immutable app settings (API key, voice, UDP, UI) + transient UI state (current
> tab, live mode); the **DB is the source of truth** for events, setups, profile,
> and history; the **contexts** (§7) mediate reads so tabs never reach into
> `config["strategy"]` directly.

---

## 6. Diagnostic / developer controls exposed in the normal flow

| Control | Location | Verdict |
|---------|----------|---------|
| Telemetry raw packet view (XYZ, road-Y, tyre radius, error counts) | Telemetry tab | MARK tool (done) + HIDE raw fields |
| Debug tab (tracker state, raw packet fields, gearbox debug, event log) | Debug tab | RENAME→Diagnostics (done), MARK tool (done) |
| AI Log DRY-RUN / structured_payload / validation warnings | AI Log tab | Developer-gate (partly done via Settings toggle) |
| "Race Config ID" hash | Strategy Builder | HIDE/RENAME |
| "pip install …" tooltip | Settings | MOVE to logs/docs |
| 368-byte / IV-0xDEADBEEF telemetry reference | Guide | MOVE to Diagnostics/docs |
| Track Modelling calibration/alignment authoring | Track Modelling tab | MARK advanced (done) |

This sprint's approach: **mark the four tool tabs** (Telemetry, Diagnostics, AI
Log, Track Modelling) with a ⚙ prefix driven by `ui/product_flow.py`, so the six
workflow tabs read as the product and the tools are visibly separate — without
reordering tabs (indices are hard-coded in `_on_tab_changed`).

---

## 7. Proposed target architecture (9 contexts)

Practical, incremental — **thin owner objects that wrap existing modules**, not a
rewrite. Each context is a plain Python class (no Qt) that owns state and exposes
read methods; tabs read from contexts instead of reaching into `config["strategy"]`
or the DB directly. `ui/product_flow.py` (added this sprint) is the first concrete
step toward the missing Dashboard/home surface.

| Context | Owns | Must NOT own | Existing files that belong to it | UI panels that read it |
|---------|------|--------------|----------------------------------|------------------------|
| **EventContext** | active event id, car, track name, race rules, BoP/tuning/allowed categories | telemetry, setups, geometry | session_db (events), Event Planner handlers | Event Planner (writer); Setup/Strategy/Live (read-only mirrors) |
| **TrackContext** | location_id/layout_id, reference path, station map, corner/segment model, seed geometry, track-truth model | event rules, car | track_intelligence, track_calibration*, track_station_map, track_model_resolver, track_truth* | Track Modelling (writer); Setup/Strategy/Live (read AI-corner context) |
| **SessionContext** | current session id + type, lap validity, live mode | AI prompt assembly | session_db (sessions/laps), dispatcher, telemetry/state | Live, Practice Review, History |
| **TelemetryContext** | live packet stream, per-lap stats, derived events | persistence policy | telemetry/recorder, telemetry/state | Telemetry, Live, Debug |
| **SetupContext** | current setup, setup diagnosis (cached), AI setup snapshot | strategy, event rules | setup_diagnosis, driving_advisor (setup paths), setup_history | Setup Builder |
| **StrategyContext** | stint plan, tyre refs, feasibility, strategy prompt snapshot | setup fields | ai_planner, feasibility, outcome, strategy_orchestrator, engine | Strategy Builder, Live (race panel) |
| **LearningContext** | driver profile, saved plans/setups, per-rec outcomes | live telemetry | session_db (user_profile, setups, ai_interactions), profile_updater | Settings (profile), Practice Review (feedback), History |
| **LiveRaceContext** | active strategy, pit window, live coaching/announcer state, mid-race replan | model authoring | engine, live_segment_coaching, voice/announcer | Live Race Engineer |
| **DiagnosticsContext** | packet counters, AI log entries, debug snapshots, dev-mode flag | any workflow state | _ai_client (log), track_modelling_runtime_check | Telemetry, Diagnostics, AI Log |

Migration order (low → high risk): (a) **DiagnosticsContext** + `product_flow`
(navigation/tools) — *this sprint starts here*; (b) **EventContext** to kill the
`config["strategy"]` fan-out (SSOT-1); (c) **TrackContext** to unify track/layout
(SSOT-2); (d) freeze **SetupContext/StrategyContext** prompt snapshots (SSOT-7);
(e) **LearningContext** to make the driver profile live.

---

## 8. What this sprint changed (safe first pass)

Deliberately small, display-only or additive, fully test-covered. **No backend
capability removed. No feature added. No tab reordered.**

1. **New `ui/product_flow.py`** — pure, no-Qt single source of truth for: tab
   roles (workflow/support/diagnostic), the canonical 13-step journey, tab-title
   decoration, and `build_flow_state_summary()` (the logic behind the missing
   "suggested next action" home surface).
2. **`ui/dashboard.py`** — renamed tab 7 **"Debug" → "Diagnostics"**; added
   `_apply_product_flow_tab_markers()` which prefixes the four tool tabs
   (Telemetry, Diagnostics, AI Log, Track Modelling) with a ⚙ marker from
   `product_flow`. Idempotent, display-only, indices unchanged.
3. **`ui/track_modelling_ui.py`** — renamed misleading **"5. Track Model
   Alignment" → "5. Seed Geometry"**; renamed **"Resolver Status" → "Track Model
   Status"**.
4. **Tests** — `tests/test_consolidation_product_flow.py` (36 tests: roles,
   decoration idempotency, 13-step journey integrity, flow-state gate logic,
   plus source-scans of the dashboard/track-modelling renames). Updated
   `tests/test_group23b_ui_cleanup.py` for the Section-5 rename.

### Intentionally NOT changed (and why)
- **Tab order** — indices are hard-coded in `_on_tab_changed` (dashboard.py:5917).
- **Hidden legacy per-segment buttons** — still `getattr`-referenced by handlers;
  safe deletion needs handler cleanup (deferred, §9).
- **`config["strategy"]` fan-out / track-layout split / setups dual-residence** —
  real SSOT fixes but higher-risk refactors; documented in §5, scheduled in §7.
- **Track Modelling jargon glossary** — large wording pass; deferred to avoid
  churn and test breakage.

---

## 9. Remaining clean-up, risks, and next sprint

### Remaining clean-up (recommended order)
1. Delete the 7 hidden legacy per-segment buttons + their `getattr` handlers
   (`track_modelling_ui.py:517–524` and the review-action map).
2. Make Strategy Builder's API-key field defer to Settings (status only).
3. HIDE/RENAME "Race Config ID"; move the Guide's telemetry reference to
   Diagnostics/docs; move the "pip install" tooltip.
4. Diagnostics-tab wording pass ("Rem(clk)", "Ann queue", raw field labels).
5. Track Modelling jargon glossary + merge Sections 4/5/6 into ~3 panels.
6. ~~Build the actual **home/overview panel** rendering `build_flow_state_summary`.~~
   **DONE (2026-07-03)** — Home Dashboard Build sprint; see §1.1 and
   `docs/HOME_DASHBOARD_BUILD.md`.

### Risks
- **Index-coupled tabs** — any future reorder must update `_on_tab_changed`
  (indices 3/4/5/6/10/11/12). Recommend switching to index-by-lookup.
- **`config["strategy"]` god object** — the EventContext refactor touches many
  read sites; do it behind a compatibility shim and one tab at a time.
- **No-Qt test convention** — UI tests are source-scans; renames that a test
  asserts (e.g. section titles in `test_group23b`) must update the test too.

### Recommended next sprint
**"State Consolidation 1: EventContext"** — introduce `EventContext`, remove the
`config["strategy"]` event fan-out (SSOT-1), and route Setup/Strategy/Live reads
through it. Ship with the home/overview panel (item 6) as the visible payoff.
