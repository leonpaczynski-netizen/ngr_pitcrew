# Diagnostic Tab Cleanup — Low-Risk UI Dags Removal

> Author: Diagnostic Tab Cleanup sprint · Date: 2026-07-03
> Branch: `diagnostic-tab-cleanup-ui-dags` (from `home-dashboard-command-centre` @ `d96b967`)
>
> Companion docs: `docs/PRODUCT_CONSOLIDATION_AUDIT.md` (§3/§9 — the cleanup
> list this sprint executes), `docs/HOME_DASHBOARD_BUILD.md` §6/§7.

---

## 1. Scope

Low-risk UI cleanup only. **Unchanged by design:** race logic, setup logic,
strategy logic, track mapping, AI prompt wording, AI input plumbing, PTT,
voice, calibration, persistence, tab order, the Home Dashboard position, the
diagnostic tabs themselves, all context layers, and all legacy compatibility
(including both `config["strategy"]` fan-out writers, which are explicitly
out of scope for this sprint).

## 2. Item-by-item audit and actions

### 2.1 The 7 hidden legacy per-segment review buttons — **DELETE (done)**

| | |
|---|---|
| Controls | `Confirm`, `Rename`, `Reject`, `Needs More Laps`, `Split Required`, `Merge Required`, `Save Reviewed Model` buttons + the `Saved: <file>` path label (`_tm_btn_rev_*`, `_tm_lbl_rev_save_path`) |
| File/function | `ui/track_modelling_ui.py` — created (already `.hide()`-den) in the Section-3 builder; referenced by `_tm_refresh_review_buttons()` and the 7 `_tm_review_*` handlers |
| Purpose | The Group 17F per-segment review workflow, replaced by whole-model acceptance in Group 17P |
| Reachability | **Unreachable**: every button was hidden at creation AND none was ever `clicked.connect`-ed — the 7 handler methods could not be invoked from the UI at all |
| Risk | Low — proven dead by source scan; only live references were an enabled-state refresher (cosmetic on hidden widgets) and one hidden-label `setText` |
| Action taken | Deleted: the 8 widget creations, the 4 never-applied `_rev_btn_*` style strings, `_tm_refresh_review_buttons()` + its 2 external call sites, the no-op `_tm_refresh_approval_panel()` + its call site, the 7 unreachable `_tm_review_*` handlers, and the 8 now-unused imports (`get_review_button_states`, `confirm_segment`, `rename_segment`, `reject_segment`, `mark_needs_more_laps`, `mark_split_required`, `mark_merge_required`, `export_review_json`). A comment at the old creation site records what happened |
| Backend | **KEPT** — the pure review-action functions in `data/track_segment_review.py` and `ui/track_modelling_vm.get_review_button_states` remain (they have their own test coverage: `test_group17f_segment_review.py`, `test_group17m_runtime_hardening.py`); an import test proves they still work |
| Tests | `tests/test_diagnostic_tab_cleanup.py` (widgets/methods/imports gone, no string references remain anywhere in the two UI modules); `test_group24_track_modelling_extraction.py` method-count floor updated 54 → 46 with the reason documented in the test |

### 2.2 Duplicate API-key UI — **finding CORRECTED; no duplicate exists — DEFER relocation**

| | |
|---|---|
| Control | "Anthropic API Key" field (`self._ai_api_key`), Strategy Builder tab |
| Audit claim (§2.5/§4) | "Duplicate of the Settings key entry; keep one owner (Settings)" |
| What the code actually shows | **There is no Settings-tab API key field.** The Strategy Builder field is the only editable key entry, and every AI caller reads `self._ai_api_key.text()` (strategy analysis, practice analysis, degradation, setup paths, profile update). The Guide *claimed* the key could be pasted in Settings — that Guide text was the only "duplicate" |
| Action taken | Guide Step 10 corrected to say the key lives in `api_key.txt` or the **Strategy Builder** field (§2.4). Audit §4 corrected in place. Field and all callers untouched |
| Deferred | Moving the key entry to Settings (making Strategy Builder show status only) is a control relocation between tabs — out of scope for a dags-removal sprint; queue with a future Settings pass |

### 2.3 "Race Config ID" — **RENAME (done)**

| | |
|---|---|
| Control | `Race Config ID: <10-char hash> · track / car / length` row, Strategy Builder |
| File/function | `ui/dashboard.py` AI-analysis param form (`self._lbl_config_id`); value written by `_update_race_config()` |
| Purpose | The practice-lap-bank match key — genuinely user-relevant (explains why old sessions do or don't appear), but labelled with an internal identity name |
| Risk | Low — label text only; the value, tooltip mechanics, and `config_id` computation are untouched |
| Action taken | Row label renamed **"Race Config ID:" → "Session Match Key:"**; tooltip reworded to plain English. Consistent with the Home Dashboard's "Plan match key" wording. NOT hidden — the audit offered HIDE or RENAME, and the tooltip shows users do need this concept for the lap bank |

### 2.4 Guide content — **FIX STALE CONTENT (done)**

| | |
|---|---|
| Items | (a) h1 title "GT7 VR Dashboard — User Guide"; (b) Step 8 described a **"Dashboard" tab with quick-link buttons that never existed**; (c) Step 10 said the API key can be pasted "here" (Settings) — wrong tab; (d) no explanation of the ⚙ tool-tab markers added by the Product Consolidation sprint |
| File | `ui/dashboard.py` `_GUIDE_HTML` |
| Risk | Low — read-only HTML |
| Actions taken | (a) title → "Next Gear Racing Pit Crew — User Guide" (product renamed 2026-06-23); (b) Step 8 rewritten to describe the real **Home** tab (Race Engineer Command Centre, last tab, next-step + stale flags — no invented quick-links); (c) API-key bullet now points at `api_key.txt` or the Strategy Builder field; (d) new intro note: "Tool tabs (⚙)… are advanced tools… safe to ignore during a normal race weekend" |

### 2.5 Embedded telemetry byte-format reference — **DELETE dead constant (done)**

| | |
|---|---|
| Item | `_TELEMETRY_REFERENCE_HTML` (~143 lines: "All 72 fields parsed from the GT7 UDP packet (368 bytes, decrypted with IV 0xDEADBEEF)…") |
| File | `ui/dashboard.py:237–380` |
| Audit verdict | "MOVE → Diagnostics/docs" (believed embedded in the Guide) |
| What the code actually shows | The constant was defined but **never rendered anywhere** in the repo — the Guide embedding had already been removed at some point, leaving dead code |
| Risk | None — zero references |
| Action taken | Deleted, with a comment pointing to `telemetry/parser.py` and docs as the packet-format documentation. (Rendering it inside Diagnostics would have been a new feature, out of scope) |

### 2.6 Diagnostics-tab abbreviations — **RENAME (done)**

| | |
|---|---|
| Items | Tracker row "Rem(clk):" vs raw row "rem_ms(raw):" (inconsistent pair); announcer row "Ann queue:" |
| File/function | `ui/dashboard.py` `_build_debug_tab()` + the update sites in the debug refresher |
| Risk | Low — label prefixes only; both the creation defaults and the `setText` format strings updated together |
| Actions taken | "Rem(clk):" → **"Time left:"** (it is the tracker's computed remaining time); "rem_ms(raw):" → **"remaining_time_ms:"** (the actual packet field name, consistent with the neighbouring `cars_in_race`/`laps_in_race` raw-field row); "Ann queue:" → **"Voice queue:"** |

### 2.7 "pip install" tooltip — **REMOVE from tooltip (done)**

| | |
|---|---|
| Item | "Requires: pip install requests beautifulsoup4" line in the Settings → Game Data "Refresh Data from Web" tooltip |
| File | `ui/dashboard.py` `_build_settings_tab()` |
| Risk | None — tooltip text only; failures already surface via the status line/progress callback |
| Action taken | Line replaced with "Needs an internet connection; the status line below reports progress." Developer setup requirement lives here: the scraper needs the optional `requests` + `beautifulsoup4` packages |

### 2.8 Stale product branding — **RENAME (done)**

| | |
|---|---|
| Items | `setWindowTitle("GT7 VR Dashboard")` and the Guide h1 — the only two user-facing sites of the pre-rename product name |
| Risk | Low — no test or automation pins the window title; module docstrings mentioning the old name were left alone (not user-facing) |
| Action taken | Both → "Next Gear Racing Pit Crew" |

### 2.9 Reviewed and explicitly DEFERRED

| Item | Verdict | Why deferred |
|---|---|---|
| Track Modelling jargon glossary ("Seed", "Station Map", "Extra peaks suppressed", "Lap offset", "AI context", "truth source"…) | DEFER | Large wording pass across ~20 labels with test assertions on several; the audit already schedules it with the Sections-4/5/6 merge |
| Telemetry tab raw rows ("Position XYZ", "Road surface Y", "Tyre radius F/R") | KEEP (deferred HIDE) | The tab is ⚙-marked diagnostic and the Guide now says tool tabs are safe to ignore; hiding rows is not needed for clarity |
| Strategy Builder fuel-burn suffixes "(from telemetry)" / "(last session)" | KEEP | The suffixes are accurate per-source labels, not stale |
| API-key entry relocation to Settings | DEFER | §2.2 — control relocation, not dags removal |
| Garage "Session History" vs History tab overlap | KEEP | Audit already accepted it as a car-scoped view |
| `_on_event_set_active` and Track Modelling combo `config["strategy"]` fan-outs | OUT OF SCOPE | Explicitly excluded by the sprint brief; a source-scan test now pins that both still exist |

## 3. Tab-index risk (for the next sprint)

> **Executed (2026-07-03):** the Tab Navigation Refactor sprint ran next —
> hard-coded indices are gone; dispatch and navigation use the named tab
> registry (`ui/tab_registry.py`). See `docs/TAB_NAVIGATION_REFACTOR.md`.

Tab indices 0–12 remain hard-coded in `_on_tab_changed`, and the Home tab is
pinned at appended index 13 via `self._home_tab_index`. This sprint changed no
indices and added none. The standing recommendation is unchanged and now has
two accumulated consumers waiting on it:

**Next sprint: Tab Navigation Refactor — Named Tab Lookup** — replace the
hard-coded indices with lookup-by-title (or per-tab object references), then
**move Home Dashboard to index 0** as the follow-up, and enable the deferred
Home-tab click-to-navigate feature (`docs/HOME_DASHBOARD_BUILD.md` §5).

## 4. Tests

`tests/test_diagnostic_tab_cleanup.py` (NEW, 25 source-scan/import tests):

* all 8 legacy widgets, all 9 deleted methods, and all 8 dead imports are gone
  from both UI modules, with **no string/getattr references left anywhere**;
* the backend review functions and `get_review_button_states` still import
  (UI-only removal proven);
* renames present / stale labels absent (Session Match Key, Time left,
  remaining_time_ms, Voice queue, product name, no "pip install");
* Guide fixed (no phantom "Dashboard" tab, Home step present, API-key bullet
  points at Strategy Builder, tool-tab note present, dead telemetry constant
  gone);
* tab order pinned (all original addTab lines + Home appended at 13),
  `_on_tab_changed` dispatches unchanged, diagnostic tabs still built,
  product_flow diagnostic set unchanged, Home Dashboard wiring intact;
* legacy `config["strategy"]` fan-outs untouched; no strategy writes in the
  touched areas; the single API-key field still exists for the AI callers.

Updated: `tests/test_group24_track_modelling_extraction.py` — `_tm_` method
floor 54 → 46 (the 9 deleted methods enumerated in the test comment).

## 5. Acceptance status

Full suite: see `MASTER_TESTING_REGISTER.md` (Diagnostic Tab Cleanup). No
logic, prompt, mapping, PTT/voice, persistence, tab-order, or fan-out change
anywhere in the diff — the whole sprint is deletions of dead UI, label text,
and Guide HTML.
