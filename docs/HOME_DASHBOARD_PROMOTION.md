# Home Dashboard Promotion — Move Home to Index 0 and Add Click Navigation

> Author: Home Dashboard Promotion sprint · Date: 2026-07-03
> Branch: `home-dashboard-promotion` (from `tab-navigation-named-lookup` @ `3b7c9c9`)
>
> Companion docs: `docs/TAB_NAVIGATION_REFACTOR.md` (the named-lookup
> infrastructure this sprint builds on), `docs/HOME_DASHBOARD_BUILD.md` (the
> Race Engineer Command Centre itself), `docs/PRODUCT_CONSOLIDATION_AUDIT.md`.

---

## 1. Why Home moved to the first tab

The Home Dashboard (Race Engineer Command Centre, `REQUIREMENTS.md §12.2`,
audit §1.1) is the app's overview surface: it shows the active event, track
data status, latest setup, strategy plan, AI-input safety and the single
suggested next action. It is the natural **landing page** — the first thing a
race engineer should see when the app opens, and the place to return to for a
"where am I / what next" read.

When the Home Dashboard was first built it had to be **appended at index 13**,
because tab navigation was still keyed to raw numeric positions — inserting it
anywhere else would have silently re-targeted every hard-coded index comparison
in `_on_tab_changed`, every `setCurrentIndex(<n>)` jump, and two visibility
guards. Moving it was therefore deliberately deferred until named tab lookup
existed.

## 2. How named tab lookup made the move safe

The **Tab Navigation Refactor** (`ui/tab_registry.py`) replaced every raw index
with a stable key. Dispatch resolves `key = registry.key_at(index)`; navigation
and visibility checks resolve through `get_tab_index` / `current_tab_key` /
`select_tab`. The registry is **positional** — it mirrors the `addTab` creation
order — so the visual order lives in exactly one place (`DEFAULT_TAB_ORDER`).

That reduced this sprint's reorder to an **order-only edit**:

* lead `DEFAULT_TAB_ORDER` with `TAB_HOME` and renumber the comments;
* move the Home `addTab` call to the front of the matching block in
  `ui/dashboard.py` `_setup_ui`.

No dispatch, jump, or visibility code references a raw position, so **nothing
else had to change**. A source-scan test extracts the real `addTab` title
sequence and asserts it still equals `[TAB_BASE_TITLES[k] for k in
DEFAULT_TAB_ORDER]`, and a runtime count check warns on any drift.

## 3. Final tab order

| Index | Key | Base title | Role |
|---:|---|---|---|
| 0 | `TAB_HOME` | Home | workflow (**default landing tab**) |
| 1 | `TAB_LIVE` | Live Race Engineer | workflow |
| 2 | `TAB_EVENT_PLANNER` | Event Planner | workflow |
| 3 | `TAB_GARAGE` | Garage | workflow |
| 4 | `TAB_SETUP_BUILDER` | Setup Builder | workflow |
| 5 | `TAB_PRACTICE_REVIEW` | Practice Review | workflow |
| 6 | `TAB_STRATEGY_BUILDER` | Strategy Builder | workflow |
| 7 | `TAB_TELEMETRY` | Telemetry (⚙) | diagnostic |
| 8 | `TAB_DIAGNOSTICS` | Diagnostics (⚙) | diagnostic |
| 9 | `TAB_GUIDE` | Guide | support |
| 10 | `TAB_SETTINGS` | Settings | support |
| 11 | `TAB_HISTORY` | History | workflow |
| 12 | `TAB_AI_LOG` | AI Log (⚙) | diagnostic |
| 13 | `TAB_TRACK_MODELLING` | Track Modelling (⚙) | diagnostic |

Home leads; **every other tab keeps its previous relative order** (each shifted
down exactly one). The ⚙ tool-tab markers are unchanged.

## 4. Open on Home by default

`_setup_ui` ends with `self.select_tab(TAB_HOME)` — the app opens on Home by
stable key, independent of position. Because Home is index 0 it is already the
current tab, so selecting it emits no `currentChanged` signal; the first render
is therefore triggered once explicitly at the end of `__init__` via the
existing guarded `self._home_refresh()` (by then every context source the
dashboard reads is fully wired). No raw `setCurrentIndex` is used — `select_tab`
remains the only `_tabs.setCurrentIndex` call site.

## 5. Home card navigation mapping

Each Home card offers an **"Open &lt;Tab&gt;"** button that navigates to the
relevant tool tab. The mapping is pure data in `ui/home_dashboard_vm.py`
(`CARD_TAB_KEYS`, resolved via `tab_key_for_card`), keyed by **stable tab keys —
never visible labels** — so the ⚙ decoration can never affect navigation:

| Home card | Opens tab | Key |
|---|---|---|
| Race Setup | Event Planner | `TAB_EVENT_PLANNER` |
| Track Intelligence | Track Modelling | `TAB_TRACK_MODELLING` |
| Setup Brain | Setup Builder | `TAB_SETUP_BUILDER` |
| Strategy Brain | Strategy Builder | `TAB_STRATEGY_BUILDER` |
| AI Input Safety | AI Log | `TAB_AI_LOG` |

The **Next Best Action** banner carries its own "Open &lt;Tab&gt;" button. The
flow summary reports a display **name** ("Setup Builder"); it is mapped to a
stable key with `tab_registry.key_for_title()` (already ⚙-decoration-safe) in
`_home_update_next_action_button`. When the journey is complete or the name
doesn't resolve to a real tab, the button hides.

Button labels come from the **undecorated** `TAB_BASE_TITLES`
(`_home_nav_button_text`), so they never show the ⚙ marker.

## 6. Navigation is low-risk (tab-change only)

`_home_navigate(tab_key)` (and `_home_navigate_next_action`) do exactly one
thing: `select_tab(tab_key)` — a normal tab switch, identical to the user
clicking the tab. They:

* only change tabs;
* never mutate domain state, write `config`, or persist anything;
* never start AI calls, telemetry, calibration, or workers;
* fail safely — an unavailable/unknown target is a no-op (`has_tab` guard +
  `select_tab` returns `False` on unknown keys), and every helper is wrapped so
  it can never raise out to the UI.

Switching to a tab still runs that tab's normal on-activation sync (via the
unchanged `_on_tab_changed` dispatch) — the same behaviour as a manual click,
by design.

## 7. User-facing affordances

Kept deliberately simple and consistent with the existing dark theme:

* an **"Open &lt;Tab&gt;" button** on each mapped card and on the next-action
  banner (a subtle button-like action row, right-aligned);
* a **pointing-hand cursor** on those buttons;
* a **tooltip** ("Open this tool tab") on the card buttons;
* a hover accent on the buttons.

The Home tab was **not** otherwise redesigned — cards, statuses, warnings and
the next-action banner render exactly as the Home Dashboard Build produced them.

## 8. What changed

* **`ui/tab_registry.py`** — `DEFAULT_TAB_ORDER` now leads with `TAB_HOME`
  (comments renumbered 0–13); header docstring updated. No code/API change.
* **`ui/dashboard.py`** — Home `addTab` moved to first; `select_tab(TAB_HOME)`
  at the end of `_setup_ui`; one guarded `_home_refresh()` at the end of
  `__init__`; `_build_home_tab` adds per-card "Open" buttons + a next-action
  button; new helpers `_home_navigate`, `_home_navigate_next_action`,
  `_home_update_next_action_button`, `_home_nav_button_text`, and the shared
  `_HOME_NAV_BTN_QSS` style; `_home_refresh` now updates the next-action
  button; Guide HTML "Home tab (last tab)" → "(first tab, shown when the app
  opens)".
* **`ui/home_dashboard_vm.py`** — `CARD_TAB_KEYS` mapping + `tab_key_for_card()`
  (imports the pure `ui/tab_registry` key constants — still no PyQt6).
* **`ui/product_flow.py`** — the "Home appended at index 13" note updated to
  "first tab (index 0)".
* **Tests** — `tests/test_home_dashboard_promotion.py` (NEW); order-pinning
  updated in `tests/test_tab_navigation_registry.py`,
  `tests/test_home_dashboard_vm.py`, `tests/test_diagnostic_tab_cleanup.py`,
  `tests/test_consolidation_product_flow.py`.

## 9. What was intentionally NOT changed

* **Per-tab activation behaviour** — the `_on_tab_changed` dispatch table is
  untouched; navigating from Home runs the same sync a manual click would.
* **The Home Dashboard view model** — cards, statuses, warnings, next-action
  computation and HTML rendering are unchanged (the mapping table and a
  `tab_key_for_card` helper are the only additions).
* **No new hard-coded tab indices**; `select_tab` remains the only
  `setCurrentIndex` site.
* **Diagnostic/tool tabs** remain available and ⚙-marked.
* **No** setup logic, strategy calculations, track mapping, AI prompt wording
  or input plumbing, AI snapshot behaviour, telemetry, PTT/voice, calibration,
  persistence, or context-layer ownership change.
* **No** `config["strategy"]` fan-out removal (both fan-outs still present,
  pinned by test) — Legacy Fan-Out Removal is a separate, higher-risk sprint.

## 10. Risks

* `DEFAULT_TAB_ORDER` and the `addTab` block must be edited **together**; the
  sequence-comparison test + runtime count warning guard the pairing (as
  before the move).
* The next-action button depends on `product_flow.build_flow_state_summary()`
  continuing to emit tab **display names** that exist in `TAB_BASE_TITLES`; an
  unmapped name simply hides the button (safe), so a future rename there would
  silently drop the shortcut rather than break — worth a glance if journey tab
  names change.
* Navigating to a tab runs its on-activation sync — intended, but it means the
  Home shortcut is exactly as heavy as a manual tab click, no lighter.

## 11. Next sprint recommendation

**Legacy Fan-Out Removal Phase 1** is now the standing higher-risk track: with
the four canonical contexts, the AI snapshot layer, the Home Dashboard, and
named navigation all in place, the `config["strategy"]` event fan-out
(`_on_event_set_active`) is the remaining worst SSOT violation. Phase 1 should
migrate the low-risk read-only consumers off `config["strategy"]` onto
`EventContext`/`StrategyContext` first, keeping the fan-out writer as
compatibility until every reader is migrated.

Alternatively, **SessionContext / TelemetryContext** would let the Home
Dashboard's two documented approximations (`has_valid_laps` = recorded laps
exist; `live_active` = telemetry connected) become owner-backed truth rather
than dashboard-derived guesses.
