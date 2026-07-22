# NGR Pit Crew — UI Architecture & Design System (Stage 1)

**Status:** Design & architecture specification for the UI rebuild. No code written yet — implementation is gated on user approval.
**Date:** 2026-07-22
**Companion docs:** [`NGR_PIT_CREW_UI_AUDIT.md`](NGR_PIT_CREW_UI_AUDIT.md) (current-state audit), `NGR_PIT_CREW_UI_REBUILD_PLAN.md` (decomposition + migration + test plan), `NGR_PIT_CREW_UI_REBUILD_UAT.md` (manual UAT).
**Design method:** UI/UX Pro Max design-system pass (OLED-dark operations-console pattern) adapted to PyQt6/QSS, brand-locked to the existing NGR identity.

---

## 1. Product Philosophy

NGR Pit Crew is a **professional virtual race-engineering environment** for GT7, not a game menu. The engineering brains (setup, strategy, telemetry, learning, live race state) are the machinery beneath the floor; **the UI is the pit crew standing beside the driver** — handing them the right tool at the right time and explaining what happens next.

**The one principle — "follow the bouncing ball".** On every page the driver can answer, in seconds:

1. **Where am I?** (event header + progress rail)
2. **What does Pit Crew know?** (engineer-guidance card: evidence summary + confidence)
3. **What's blocking progress?** (guided-action area: blockers)
4. **What do I do next?** (ONE dominant primary action)
5. **Why does it matter?** (guidance "why" line)
6. **What result is expected?** (guidance "expected outcome")
7. **What happens after?** (progress rail advances; next stage unlocks)

**Design values:** intuitive · guided · immersive · professional · motorsport-focused · evidence-led · calm under pressure · readable at a glance in PSVR2 · usable by a driver who understands racing but not setup engineering.

**Non-negotiables the UI must never do** (enforced by safety tests): invent certainty, hide missing evidence, upgrade confidence without evidence, silently apply a setup / pit call / strategy change, present a low-confidence fallback as a high-confidence result, or show five equal actions when one is the recommended next step.

---

## 2. Visual Design System (NGR brand-locked, extends `ui/ngr_theme.py`)

**Style direction:** *Dark Mode (OLED) operations console* — deep carbon surfaces, restrained neon-green accent, status-driven colour, spacious information hierarchy, telemetry-grade numerals. **Dark only** (no light mode). The UI/UX engine's default blue/amber palette and Orbitron/JetBrains fonts are **rejected** in favour of the established NGR brand.

### 2.1 Colour tokens (existing — reuse verbatim from `ngr_theme.py`)

| Token | Hex | Use |
|---|---|---|
| `INK_BLACK` | `#0C0E10` | App background / VR-safe void |
| `CARBON` | `#141619` | Base surface |
| `CARBON_RAISED` | `#1D2024` | Cards, panels |
| `CARBON_HI` | `#262A2F` | Hover / raised card |
| hairline | `#333941` / `#2A2F35` | Borders, dividers |
| `TEXT_HI` / `TEXT` / `TEXT_DIM` / `TEXT_MUTE` | — | 4-level type hierarchy |
| `NGR_GREEN` (+HI/DIM/INK) | `#2EE86E` | Brand accent, primary action, active nav, "current" state |
| `INFO / SUCCESS / WARN / DANGER / NEUTRAL` | — | Semantic status |
| `STATUS_TONES` | — | (fill, text, border) per semantic key — **status is never colour-only** |

### 2.2 Tokens to ADD (extend, don't replace)

```
# Progress-rail / stage states (colour + always paired with an icon + label)
STAGE_COMPLETE   = SUCCESS      + "✓" glyph
STAGE_CURRENT    = NGR_GREEN    + "▶" glyph   (pulsing 1.2s, reduced-motion → static)
STAGE_AVAILABLE  = TEXT         + "○" glyph
STAGE_BLOCKED    = TEXT_MUTE    + "🔒" glyph   (WARN border if action needed)
STAGE_NOT_REQ    = TEXT_MUTE    + "–" glyph   (dashed hairline)

# Confidence ladder (colour + label + fill bar — never colour alone)
CONF_HIGH        = SUCCESS   "High"      (bar 100%)
CONF_MEDIUM      = INFO      "Medium"    (bar 66%)
CONF_LOW         = WARN      "Low"       (bar 33%)
CONF_UNKNOWN     = NEUTRAL   "No evidence" (bar 0%, hatched)

# Setup-change direction / outcome
DELTA_UP / DELTA_DOWN     = NEUTRAL glyph "▲/▼" (direction is glyph, magnitude is number)
OUTCOME_IMPROVED = SUCCESS "Improved"
OUTCOME_WORSE    = DANGER  "Worse"    (prominent — negative feedback is authoritative)
OUTCOME_UNCHANGED= NEUTRAL "Unchanged"
OUTCOME_INCONCL  = WARN    "Inconclusive"

# Data freshness (live)
FRESH_LIVE   = SUCCESS "LIVE"      (age < 1s)
FRESH_RECENT = INFO    "0.0s"      (1–3s)
FRESH_STALE  = WARN    "STALE"     (>3s)
FRESH_NONE   = NEUTRAL "NO SIGNAL"

# Map-match trust (live track map — must look different per tier)
MATCH_APPROVED  = SUCCESS  solid green dot   "Reference path"
MATCH_FALLBACK  = WARN     hollow amber dot  "Road-distance estimate"
MATCH_LOW       = WARN     grey dot + ?      "Low confidence"
MATCH_NONE      = NEUTRAL  no dot            "Position unavailable"
```

### 2.3 Typography (keep Segoe UI; add tabular figures)

- **Family:** `Segoe UI` (existing `FONT_FAMILY`). Reject Orbitron/JetBrains — NGR brand voice is clean, not cyberpunk.
- **Scale (existing `FS_*`):** CAPTION 11 · BODY 13 · LABEL 14 (medium) · TITLE 16 · HEADLINE 20 · DISPLAY 28. **Minimum body 13px** (no tiny text; the brief bans it) — larger baselines at 4K via display-scale awareness.
- **Weight hierarchy:** headings 600–700, body 400, labels 500.
- **Tabular numerals everywhere data aligns** — lap times, deltas, fuel, tyre temps, setup values, timers. Qt: `QFont.setStyleStrategy` / `font-feature-settings: "tnum"` via a `.numeric` object-name class. Prevents column jitter as values change.
- **Line-height** 1.4–1.5 for explanation prose; keep prose ≤ ~75 chars per line inside guidance cards.

### 2.4 Spacing, radius, elevation

- 8pt scale (`SPACE_XS..XL` = 4/8/12/16/24). Density dial = **high** (dashboard) for data regions; **generous** for guidance cards (calm).
- Radius `SM/MD/LG` = 4/8/12. Cards `MD`; primary CTA `MD`; pills/badges `LG`.
- Elevation via surface step (`CARBON` → `CARBON_RAISED` → `CARBON_HI`) + 1px hairline, **not** heavy shadows. One consistent elevation scale; no random shadow values.
- Effects: minimal green glow only on the single primary CTA and the "current" stage marker (`text-shadow: 0 0 10px NGR_GREEN` equivalent). No decorative glow.

---

## 3. Information Architecture

### 3.1 Top-level navigation (persistent LEFT rail)

Icon **+ text label** (never icon-only), active item highlighted with NGR_GREEN left-border + text. Rail is keyboard-navigable and always reachable.

| # | Nav item | Primary question it answers | Backed by |
|---|---|---|---|
| 1 | **Home** | "What should I do?" | `build_event_command_centre_view` |
| 2 | **Active Event** | "What does this event require?" (expands to stage list) | `event_preparation_cycle` + `event_command_centre` |
| 3 | **Garage** | "Which setup should I run?" | `driving_advisor` + setup brain |
| 4 | **Practice** | "What are we testing / did it work?" | run card + experiment/outcome brain |
| 5 | **Qualifying** | "Am I ready?" | `setup_strategy_readiness` |
| 6 | **Race Strategy** | "What is the plan?" | `race_strategy_pipeline` |
| 7 | **Live Pit Wall** | "What do I need to do now?" | `canonical_live_race_state` |
| 8 | **Debrief** | "What did we learn?" | `binding_debrief_workflow` + `build_cross_session_memory` |
| 9 | **Engineering Library** | "Show me the evidence / advanced" | `development_history_page` reframed |
| 10 | **Settings** | configuration | `settings_ui` |

**Rail states:** each item is `available` / `current` / `blocked` / `not-required`. A **blocked** destination is *shown with the reason on hover/click* ("Complete a practice run first"), never silently hidden. Diagnostic surfaces (Telemetry, Diagnostics, Track Modelling, Event Planner) move **into Engineering Library / Settings** — off the primary path but reachable.

### 3.2 Persistent chrome (present on every page)

```
┌─ EVENT HEADER (persistent) ───────────────────────────────────────────────┐
│ [logo]  SERIES · EVENT · CAR · TRACK/LAYOUT   │  SESSION · STAGE  │ ●CONN  │
│                                                │  Active setup: … │ ●PitCrew│
├─ PROGRESS RAIL (persistent) ──────────────────────────────────────────────┤
│  Briefing ─ Garage ─ Practice ─ Review ─ Qualifying ─ Strategy ─ Race ─ Debrief │
│    ✓         ✓        ▶ current    ○         🔒          🔒        🔒      –      │
├─ NAV │ PAGE BODY ─────────────────────────────┬─ GUIDED ACTION AREA ───────┤
│ RAIL │  (one primary purpose per page)        │  Objective                 │
│      │                                        │  Why it matters            │
│      │                                        │  Blockers (if any)         │
│      │                                        │  ┌──────────────────────┐  │
│      │                                        │  │  ▶ PRIMARY ACTION    │  │
│      │                                        │  └──────────────────────┘  │
│      │                                        │  secondary action (subtle) │
└──────┴────────────────────────────────────────┴────────────────────────────┘
```

The **guided-action area** is a right-hand column (or docked panel) that hosts the **Pit Crew Engineer guidance card**. Exactly **one** dominant primary action per page.

---

## 4. Component Patterns (Qt-implementable)

Each is a reusable `QWidget` bound to a **pure view-model** (no engineering logic in the widget). Notes give the Qt approach.

### 4.1 `NavRail`
Left `QFrame`, vertical `QToolButton`s (checkable, exclusive `QButtonGroup`). Active = NGR_GREEN 3px left border + `TEXT_HI`. Blocked = `TEXT_MUTE` + lock glyph + tooltip reason. Emits `navigate(stage_key)`. Focus ring on `:focus` (2px NGR_GREEN). "Active Event" expands to a sub-list of stages (the progress rail mirrored vertically).

### 4.2 `EventHeaderBar`
Fixed-height `QFrame`. Left: logo pixmap (via `ngr_theme.logo_pixmap`, unchanged) + series/event/car/track. Right: session · stage · **connection dot** (green LIVE / amber stale / grey none) · **Pit Crew status** · active-setup label. All labels bound to the app-state model; updated by signal, never rebuilt.

### 4.3 `ProgressRail`
Horizontal stepper of stages. Each node = glyph + label + state colour (§2.2). Current node pulses (reduced-motion → static ring). Clicking an available/complete node navigates; blocked node shows reason. Pure VM: `build_workflow_state` (reuse `ui/workflow_stepper.py` logic, re-skinned) fed by the app-state model.

### 4.4 `EngineerGuidanceCard` — the heart of the product
```
┌───────────────────────────────────────────────┐
│ ◈ PIT CREW ENGINEER                    [🔊]     │  ← read-aloud hook (voice port)
│ "<one-paragraph engineer message>"             │  ← ≤ ~3 lines, plain language
│ ─────────────────────────────────────────────  │
│ Objective:  <what we're doing>                 │
│ Evidence:   <n runs · n corners>   Conf: ▮▮▯ Med│  ← confidence = bar+label
│ ⚠ <warning / missing evidence>                 │  ← only if present, never hidden
│ ┌───────────────────────────┐                  │
│ │  ▶ RECOMMENDED ACTION      │  secondary…      │
│ └───────────────────────────┘                  │
│ ▸ Why this / show reasoning  (expander)        │  ← progressive disclosure
└───────────────────────────────────────────────┘
```
- **Deterministic input only.** VM built from `event_command_centre._primary_next_action` (operational) and/or `race_engineer_team_brief` (deep). The card **renders** domain state; it computes nothing.
- Confidence + evidence come straight from domain; if evidence is missing, the card says so.
- `[🔊]` calls the existing voice/announcer port (opt-in, off by default). Never auto-speaks.
- Expander reveals the rule/evidence detail (from the same payload) — kept out of the primary view.

### 4.5 `SetupWorkspace` (Garage) — replaces the two-scroll maze
Single focused workspace, **one** scroll region:
```
[ Discipline selector:  ( Base | Qualifying | Race ) ]   Active setup: "Quali v3" ●applied
┌ Setup status ─────────────────────────────────────────────────────────┐
│ Saved ✓ · Applied in GT7 ✓ · Validated ○      (applied_checkpoint 3-state)│
├ Setup lineage (tree/timeline) ────────────────────────────────────────┤
│  Base → v1 → v2(worse✗) → v3(current) ▶            [Revert to v2]        │
├ Changed fields (vs parent) ───────────────────────────────────────────┤
│  Rear ARB   5 → 4  ▼   "reduce mid-corner understeer"   expected: +rotation│
├ Engineering explanation (guidance) ───────────────────────────────────┤
├ Full setup values  ▸ (expander)  │  Compare ▸  │  RPM / Gearbox ▸       │
└ Save · Apply recommendation  (immediate refresh; shown == applied) ─────┘
```
- **Discipline selector** (segmented control) swaps the *focused* discipline — no side-by-side panels.
- **Lineage** is a first-class visual tree (nodes coloured by outcome; worse = DANGER). Reuses `setup_lineage` + DB experiments; **not** buried in a log.
- **Comparison** view (current↔parent, base↔quali, quali↔race, recommended↔active, best-proven↔current) highlights changed value · direction · magnitude · reason · expected effect · outcome · proven range.
- **Apply/Save correctness:** unify on **one** recommendation representation so *shown == applied* (fixes the audit's renderer-vs-plan divergence). After apply: visible values, active-setup badge, lineage, and changed-fields all refresh immediately from the authority.
- **RPM/Gearbox** expander shows discipline-specific objectives (quali = one-lap pace/top speed; race = consistency/fuel/drive-out) from `gearbox_evidence`/`gearbox_format`; never silently identical across disciplines without explanation.

### 4.6 `RunCard` (Practice)
A persistent (dockable) card visible during the run: objective · setup under test · exact changes · expected effect · corners/behaviours to monitor · fuel load · tyre compound · target laps · push level · run purpose (pace/consistency/deg/fuel/gearing/diagnosis) · invalidation conditions. Primary action **Start Practice Run**. Stays accessible mid-session.

### 4.7 `StructuredFeedbackForm` (Practice Review)
Dropdowns / segmented controls / 1–5 scales / corner selector — **not** free-text-first:
- Overall vs previous: Better / Worse / Unchanged (prominent).
- Balance: entry / mid / exit (understeer↔oversteer scale).
- Braking confidence · traction · rotation · kerb behaviour · bottoming · gear choice · drive-out · straight-line · fuel · tyre · confidence.
- Corner/segment selector (from track model) to localise feedback.
- Free-text **supplements**, never replaces.
Then shows telemetry findings · driver feedback · agreements · contradictions · confidence · what changed vs previous run · experiment verdict (succeeded/failed/inconclusive). Primary action **adapts** to verdict: Keep / Revert / Refine / Gather more / Build next / → Qualifying prep. Reuses `setup_diagnosis.build_feedback_dispositions` + `detect_diagnosis_contradictions`.

### 4.8 `QualifyingReadiness`
Checklist with colour+icon+label status per item: quali setup selected · **Soft tyres confirmed** · fuel target · gearbox objective · track limits reviewed · out-lap plan · tyre-prep plan · push-lap plan · traffic plan · risk corners · driver confidence · remaining blockers. Engineer explains what changed from practice, why it gives one-lap pace, what to protect, and the compromised-first-lap fallback. Primary **Begin Qualifying**. Soft-tyre requirement is a visible rule (unless event rules forbid).

### 4.9 `StrategyPlanView`
Recommended plan + alternatives as cards (not a raw table): total race time / expected laps (time-certain) · stint plan · tyre sequence · fuel targets · pit windows · refuelling targets · traffic/deg/fuel risk · confidence · **measured-vs-assumed** inputs (source tag per input, from `race_strategy_vm._classify_source`) · replan triggers. **No setup Apply controls anywhere on this surface** (safety). Primary **Approve Race Plan**.

### 4.10 `LivePitWall` — audio-first, low-distraction
Large-type, few elements, glanceable (PSVR2):
- Big KPIs: current lap · position · stint · fuel state · tyre state · pit window · gap-to-plan.
- **Current engineer instruction** prominent; next decision point.
- Live **track map** with car position **only when trustworthy** — match tier shown by colour+label (§2.2: approved / fallback / low / none). Never make a fallback look like a high-confidence match.
- **Data freshness + confidence** always visible (LIVE / 0.0s / STALE / NO SIGNAL).
- Streaming values as large text KPIs (per data-viz guidance); respect reduced-motion (freeze pulse). Pause-safe.
- **No dense tables. No silent commands** — every pit/fuel/strategy suggestion is advisory; the driver acts. Voice/PTT hooks integrated (off by default, gated).
- Perf: incremental per-packet updates (mutate labels/dot only), throttled/coalesced worker refresh — **never a worker-per-packet**; heavy geometry stays off the packet path.

### 4.11 `DebriefView`
After every session: what happened · learned · improved · regressed · predictions right/wrong · new evidence · contradictions · setup outcome · strategy outcome · driver findings · track/corner findings · knowledge-maturity changes. Failed experiments remain visible; proven working windows shown. Primary action reflects programme state (Continue development / Prepare quali / Prepare race / Close event / Post-event review). Reuses `binding_debrief_workflow` + `postflight_review_vm` + `development_history_vm`.

### 4.12 `EngineeringLibrary`
Progressive-disclosure home for advanced depth (the reframed `development_history_page`): evidence provenance, rule traces, knowledge graph, confidence calculations, assurance/priority, certification, bench/manual UAT, season/campaign knowledge. **Off the primary workflow**; the driver-facing answer always comes first elsewhere.

### 4.13 Shared states (every data component)
`empty` (helpful message + action, never blank) · `loading` (skeleton/shimmer > 300ms, not a bare spinner) · `ready` · `blocked` (reason + what unblocks it) · `error` (cause + recovery path). Explicit VM state enum; stale-result guards on all background work.

---

## 5. Application State Model

One canonical, observable app-state object (assembled by a **controller**, not the QMainWindow) that the shell/nav/header/rail/guidance all read:

```
AppState
 ├ active_event        ← resolve_active_cycle / event_context      (identity + timeline + format)
 ├ programme_stage     ← event_command_centre + workflow_state     (current stage + per-stage status)
 ├ active_setup        ← ActiveSetupAuthority                      (saved/applied/validated)
 ├ session             ← RaceStateTracker / session_context        (live/practice/quali/race + freshness)
 ├ guidance            ← _primary_next_action / race_engineer_team_brief
 ├ connection          ← UDP listener status
 └ readiness           ← setup_strategy_readiness                  (lock/finalisation per discipline)
```
- Built by relocating the existing `_build_*_context()` adapters out of `MainWindow` into a `PitCrewController`.
- Emits granular change signals; components subscribe and update incrementally (no full-page rebuild on telemetry).
- **Single source of truth** — no second truth system for setup values, symptoms, recommendations, applied changes, event identity, session state, strategy state, track identity, confidence, readiness, or lineage.

---

## 6. View-Model Boundaries & Domain Integration

- **Layers:** (1) canonical domain/services `strategy/` `data/` — unchanged; (2) application orchestration `PitCrewController` + `AppState`; (3) pure Qt-free view-models `*_vm.py`; (4) UI components; (5) page composition; (6) navigation/workflow state; (7) theme/design tokens `ngr_theme`; (8) runtime adapters (telemetry/voice).
- **Rules:** view-models Qt-free & deterministic; formatting out of page classes; **no engineering logic in UI classes**; typed models; explicit empty/loading/ready/blocked/error; stale-result guards; never block the UI thread; incremental live updates; reusable components; one canonical app-state; no circular imports; decompose the `dashboard.py` monolith; retire old paths once proven.
- **Hidden logic to extract first** (from audit §5): learning-outcome loop, feedback/verify helpers, setup-field taxonomy, weather→condition map, schema-default coercion, `apply_ai_fields` key/gear remap, decision-status derivation, `_ensure_active_preparation_cycle` cycle-provisioning, qualifying sector math, car-dot recompute, auto-confirm review policy → move into `strategy/`/`data/` with their own unit tests **before** re-homing each surface.

---

## 7. Setup Workflow (correctness spine)

1. Analyse (`driving_advisor.build_combined_setup_response`) → **one** canonical recommendation VM (`setup_recommendation_vm`) that is the single source for both what's shown and what's applied.
2. Apply → clamp via `setup_ranges` (apply gate) → write via authority → **immediate** visible refresh of values + active-setup badge + lineage + changed-fields.
3. Confirm-applied-in-GT7 → `applied_checkpoint` three-state → `setup_state_authority.mark_applied` → experiment link.
4. Review outcome → verdict/evidence/keep-revert-refine → lineage outcome + `learning_outcomes`.
5. Lineage & blocked directions surfaced visually; a failed direction the brain won't repeat is shown as an explicit, authoritative warning.

**Dual-store integrity:** save writes both `config.json` and the DB — keep them in sync (single save path).

---

## 8. Live Workflow

`UDPListener → RaceStateTracker → canonical_live_race_state → LiveStrategyState → live_audio_strategy_build / live_pit_wall_build`, rendered by `LivePitWall`. Advisory replan via `race_strategy_live_replan` (manual/triggered, "ADVISORY ONLY · NO PIT COMMAND"). Track position via `track_map_matching` with explicit trust tiers. Voice/PTT via existing announcer + `query_listener` (off by default, gated). **Wired per-frame with throttle/coalesce**, fixing the audit finding that these panels currently refresh only on tab activation.

---

## 9. Safety Boundaries (must remain provable)

The new UI must be unable to: bypass setup Apply gates · silently apply setups / make pit calls / execute strategy changes · hide missing evidence · upgrade confidence without evidence · recommend illegal strategies · use fallback progress to corroborate pits · rewrite canonical diagnoses · create contradictory field states · mark incomplete experiments as complete setups · repeat failed directions without justified stronger evidence · write to setup history from read-only views · require an API key for deterministic functionality. Each gets an explicit safety test (see plan doc). Strategy surface exposes **no** setup Apply control. Every outward/irreversible action is user-initiated with confirmation.

---

## 10. Migration & Cutover Approach

Staged, parity-checked, no big-bang:
1. **Audit & architecture** (this doc + plan). ✅ read-only.
2. **Shell + event workflow** — new shell, nav rail, event header, guided-action area, progress rail, engineer-guidance card, Home + Active Event. New shell runs **alongside** the old tabs behind a launch flag.
3. **Garage/setup** — SetupWorkspace over the existing setup brain.
4. **Practice + experiment** — run cards, structured feedback, outcome flow.
5. **Qualifying + strategy** — readiness + strategy meeting (deterministic boundaries preserved).
6. **Live Pit Wall** — canonical live state, voice/PTT, trusted position.
7. **Debrief + Engineering Library** — debrief surface + advanced disclosure.
8. **Cutover** — parity + workflow UAT, remove obsolete navigation/dead panels/duplicate renderers, app **opens into the new experience**, keep migration notes. Old dashboard retired as the primary surface; not left as a second competing production UI.

Each stage: independently testable, focused commits, full inherited regression stays green, golden fixtures never edited to hide failures, runtime data files untouched, `DB_VERSION`=28 and `RULE_ENGINE_VERSION`="46.0" unchanged (this is UI-only; no schema/rule change expected).

---

## 11. Accessibility & Interaction

- **Keyboard-first:** full keyboard operation; tab order matches visual order; no traps. A "skip to page body" affordance past the nav rail. Global shortcuts for stage nav.
- **Focus:** visible 2px NGR_GREEN focus ring on every interactive element (`:focus` QSS) — never removed without replacement.
- **Status is colour + icon + text**, never colour alone (confidence, outcome, freshness, match trust, stage state all carry a glyph/label).
- **Contrast:** body text ≥ 4.5:1, large/secondary ≥ 3:1 on carbon surfaces (OLED dark grades AAA in the engine).
- **Scalable text:** respect Windows display scaling at 1080p/1440p/4K; wrap rather than truncate; tooltip/expand for any unavoidable truncation.
- **Motion:** 200–300ms, ease-out enter / faster exit; motion conveys meaning (stage advance, apply confirm); **reduced-motion freezes** the current-stage pulse and live streaming animation; data readable without motion.
- **One primary action per screen**; secondary actions visually subordinate; destructive actions use DANGER colour, separated, with confirm + undo/rollback where possible.
- **Plain language:** driver-facing text avoids engineering jargon; advanced terminology lives behind expanders / the Library.

---

## 12. Consistent Terminology (single label per concept)

Active setup · Parent setup · Previous setup · Recommended setup · Applied setup · Setup experiment · Run · Session · Event · Programme · Confidence · Readiness · Blocker · Warning · Missing evidence. No synonyms for the same concept anywhere in the UI.

---

*Approval gate: on sign-off of this spec + the rebuild plan, Stage 2 begins on a fresh branch cut from master `d79a5eb`. Second NGR logo file still required from user before branding is finalised.*
