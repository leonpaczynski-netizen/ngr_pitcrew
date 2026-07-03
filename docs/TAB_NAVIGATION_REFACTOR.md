# Tab Navigation Refactor — Named Tab Lookup

> Author: Tab Navigation Refactor sprint · Date: 2026-07-03
> Branch: `tab-navigation-named-lookup` (from `diagnostic-tab-cleanup-ui-dags` @ `c4eafdf`)
>
> Companion docs: `docs/PRODUCT_CONSOLIDATION_AUDIT.md` (§9 risk note — the
> index-coupled-tabs risk this sprint retires), `docs/HOME_DASHBOARD_BUILD.md`
> §6, `docs/DIAGNOSTIC_TAB_CLEANUP.md` §3.

---

## 1. The problem with hard-coded indices

Tab navigation was keyed to **raw numeric positions**:

* `_on_tab_changed` compared the incoming index against hard-coded `10 / 3 /
  5 / 4 / 6 / 11 / 12` (plus the Home tab via a stored `_home_tab_index`);
* three navigation jumps called `self._tabs.setCurrentIndex(4 / 3 / 1)`
  (History → Practice Review, Garage setup load → Setup Builder, Garage
  "Load to Event" → Event Planner);
* two visibility guards compared `currentIndex()` against a raw number
  (`!= 11` in `_flush_ai_log_pending_select`, `!= _home_tab_index` in
  `_home_refresh_if_visible`).

Consequences, accumulated over three sprints: the Home Dashboard had to be
**appended at index 13** instead of leading the tab bar; every reorder or
insertion risked silently re-targeting a comparison; and Home click-to-navigate
was deferred because jumping by number was too brittle to extend.

## 2. The named tab registry

**`ui/tab_registry.py` (NEW, pure Python — no PyQt6, no config access, tested
importable without a QApplication).**

* One stable key constant per existing tab (no invented tabs):

| Index | Key | Base title |
|---:|---|---|
| 0 | `TAB_LIVE` | Live Race Engineer |
| 1 | `TAB_EVENT_PLANNER` | Event Planner |
| 2 | `TAB_GARAGE` | Garage |
| 3 | `TAB_SETUP_BUILDER` | Setup Builder |
| 4 | `TAB_PRACTICE_REVIEW` | Practice Review |
| 5 | `TAB_STRATEGY_BUILDER` | Strategy Builder |
| 6 | `TAB_TELEMETRY` | Telemetry (⚙) |
| 7 | `TAB_DIAGNOSTICS` | Diagnostics (⚙) |
| 8 | `TAB_GUIDE` | Guide |
| 9 | `TAB_SETTINGS` | Settings |
| 10 | `TAB_HISTORY` | History |
| 11 | `TAB_AI_LOG` | AI Log (⚙) |
| 12 | `TAB_TRACK_MODELLING` | Track Modelling (⚙) |
| 13 | `TAB_HOME` | Home |

* **`DEFAULT_TAB_ORDER`** — the current visual order in one place. It must
  mirror the `addTab` calls exactly; a source-scan test extracts the `addTab`
  titles from `dashboard.py` and compares them sequence-to-sequence against
  the order, and a runtime count check logs a warning on mismatch.
* **`TabRegistry`** — ordered key↔index mapping mirroring creation order:
  `register(key)` (duplicate = safe no-op returning the existing index),
  `register_all`, `index_of(key)` (-1 when unknown), `key_at(index)` (None
  when out of range or not an int), `has(key)`, `count`, `keys()`. **Nothing
  raises on bad input.**
* **`TAB_BASE_TITLES`** — canonical undecorated titles, cross-checked by test
  against `product_flow.TAB_ROLES` so the two tables can't drift.
* **`key_for_title(title)`** — reverse lookup that strips the ⚙ decoration
  first. Lookup is **positional, never label-based**, so the decoration can
  never break it; this function exists for reverse mapping and tests.

## 3. What was changed (`ui/dashboard.py`)

* `_setup_ui` builds `self._tab_registry = build_default_registry()` right
  after the (unchanged) `addTab` block, with a defensive registry-vs-tab-bar
  count check. `self._home_tab_index` is retired (superseded by `TAB_HOME`).
* **`_on_tab_changed` dispatches by key**: resolve `key = registry.key_at(index)`
  then dispatch — the same 8 per-tab activation behaviours as before
  (`TAB_HISTORY → _refresh_history`, `TAB_SETUP_BUILDER →
  _sync_setup_builder_from_event`, `TAB_STRATEGY_BUILDER →
  _sync_strategy_from_event`, `TAB_PRACTICE_REVIEW → _sync_practice_from_event`,
  `TAB_TELEMETRY → _refresh_telemetry_context`, `TAB_AI_LOG →
  _flush_ai_log_pending_select`, `TAB_TRACK_MODELLING → _tm_on_tab_shown`,
  `TAB_HOME → _home_refresh`). No behaviour added, removed, or reordered.
* **Navigation helpers** (all safe on unknown keys — no-op/-1/None, never
  raise): `get_tab_index(tab_key)`, `has_tab(tab_key)`, `current_tab_key()`,
  `select_tab(tab_key)`. `select_tab` contains the **only**
  `_tabs.setCurrentIndex` call site left in the file.
* **Jump sites migrated**: `setCurrentIndex(4)` →
  `select_tab(TAB_PRACTICE_REVIEW)`; `setCurrentIndex(3)` →
  `select_tab(TAB_SETUP_BUILDER)`; `setCurrentIndex(1)` →
  `select_tab(TAB_EVENT_PLANNER)`.
* **Visibility guards migrated**: `_flush_ai_log_pending_select` checks
  `current_tab_key() != TAB_AI_LOG` (was `currentIndex() != 11`);
  `_home_refresh_if_visible` checks `current_tab_key() != TAB_HOME` (was the
  stored `_home_tab_index`).

The mixins (`track_modelling_ui.py`, `setup_builder_ui.py`) never touched
`self._tabs` and needed no changes.

## 4. What was intentionally NOT changed

* **Tab order** — every `addTab` line is byte-identical (pinned by tests in
  three suites); Home stays appended at index 13 this sprint.
* **Per-tab activation behaviour** — the dispatch table is a 1:1 translation
  of the old index comparisons.
* The ⚙ tool-tab markers, all diagnostic tabs, the Home Dashboard, all
  context layers, both `config["strategy"]` fan-outs (pinned still-present by
  test), and all setup/strategy/AI/track/telemetry/PTT/voice/persistence
  logic.

## 5. Proof tab order is preserved

* Source-scan pins all 14 `addTab` lines verbatim, including the appended
  Home line, and that Home's `addTab` still appears after Track Modelling's.
* `test_default_order_matches_addtab_calls_in_dashboard` extracts the actual
  `addTab` title sequence from the source and asserts it equals
  `[TAB_BASE_TITLES[k] for k in DEFAULT_TAB_ORDER]` — so the registry cannot
  claim an order the tab bar doesn't have.
* The runtime count check warns if the registry and tab bar ever disagree.

## 6. How this enables the Home Dashboard move

Moving Home to index 0 (next sprint) is now a **two-line-locality change**:
move its `addTab` call to the front and move `TAB_HOME` to the front of
`DEFAULT_TAB_ORDER`. Nothing else references positions: dispatch, the
visibility guards, and every jump resolve through the registry. Click-to-
navigate from the Home cards becomes `self.select_tab(TAB_SETUP_BUILDER)`
etc. — the helpers are already in place and safe on unknown keys.

## 7. Remaining risks

* `DEFAULT_TAB_ORDER` and the `addTab` block must be edited **together**; the
  pairing is guarded by the sequence-comparison test (fails the suite) and
  the runtime count warning (catches it in dev runs), but a same-count
  reorder edited in only one place would mis-dispatch until the test runs —
  keep the source-scan test green before committing any reorder.
* `product_flow.build_flow_state_summary()` returns **tab display names**
  ("Setup Builder") for the next-action target, not registry keys. When
  click-to-navigate lands, map via `tab_registry.key_for_title()` (already
  decoration-safe) or extend product_flow to emit keys.
* Two `QTabWidget`s exist (`self._tabs` and the AI-Log detail sub-tabs); the
  registry deliberately covers only the top-level one.

## 8. Tests

`tests/test_tab_navigation_registry.py` (NEW, 27):

* registry: every current tab keyed (14, unique), titles cross-checked
  against `product_flow.TAB_ROLES`, visual order preserved incl. Home last,
  **DEFAULT_TAB_ORDER mirrors the real addTab sequence**, key↔index round
  trip, missing key → -1 / out-of-range → None / garbage-safe, duplicate
  registration no-op, empty registry safe;
* decoration: every ⚙-decorated title resolves to its key; unknown titles →
  None; lookup proven positional; module purity (no PyQt6, no config);
* dashboard: `_on_tab_changed` has **no `index == <n>` comparisons** and
  carries all 8 key→handler pairs; the only `_tabs.setCurrentIndex` call site
  is inside `select_tab`; no `currentIndex() != <n>` checks; `_home_tab_index`
  retired; the three jump sites use `select_tab(TAB_*)`; visibility guards
  use keys; helpers defined + safe + write no state; registry built at setup
  with the count guard; jump-target key→index mapping proven;
* unchanged: all 14 addTab lines pinned, Home appended after Track Modelling,
  diagnostic tabs built + ⚙ markers applied, product_flow diagnostic set
  unchanged, legacy fan-out untouched.

Updated in place (same invariants, key-based home): `test_group12c_ai_log_display`
(AI-Log flush dispatch — `TAB_AI_LOG` instead of index 11),
`test_diagnostic_tab_cleanup` and `test_home_dashboard_vm` (`_on_tab_changed`
dispatch fragments — key names + handler names instead of `index == N`).

## 9. Next sprint recommendation

**Home Dashboard Promotion — Move Home to index 0 and add click-to-navigate**:
move the Home `addTab` call and `TAB_HOME` to the front together (update the
order-pinning tests), make the app open on Home, and wire the Home cards /
next-action banner to `select_tab(...)` using the registry keys (mapping the
flow summary's tab names via `key_for_title`). After that, the standing
higher-risk track remains **Legacy Fan-Out Removal Phase 1**.
