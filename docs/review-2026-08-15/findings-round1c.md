# Round 1 findings, part 3 — UI

## AREA: UI (pitcrew/ui/*)

**U1 · P1 · ui/widgets.py:353 — `theme.band_ink_for` DOES NOT EXIST. Painting any coded compound band aborts the process.**

**ALREADY VERIFIED BY THE ORCHESTRATOR — do not spend effort re-proving it, but do
assess its blast radius, which is the part still open.** Verification performed:
- `grep -rn "band_ink_for" pitcrew/` → one hit, the call site at widgets.py:353. No definition.
- `python -c "from pitcrew.ui import theme; print([n for n in dir(theme) if 'band' in n])"`
  → `['band_colour', 'band_ink']`.
- Headless paint of `widgets.CompoundBand("RM")` with an excepthook installed:
  `AttributeError: module 'pitcrew.ui.theme' has no attribute 'band_ink_for'` at widgets.py:353.
- Same paint with default PyQt6 behaviour: **process exit 127 (abort).**
- `pitcrew/diagnostics.py:13-15, 106-115` documents this exact path: PyQt calls
  `sys.excepthook`, the app logs the traceback, "PyQt aborts the process after this returns".

Reviewer's claim of origin: `git log -L 344,358:pitcrew/ui/widgets.py` shows commit
**cbe19fe** ("fix(ui): the rest of what the critique and the audit found") replaced a
working `ink = theme.band_ink(self._code)` with a call to a function that was never
written. **Confirm that origin claim** — it decides whether this is a fresh regression or
long-standing.

Blast radius to establish: `RackRow.__init__` (practice_screen.py:403) builds one band per
lap row and `_on_compound` (:511) calls `setCode`; `CompoundChip` (event_screen.py:101) is
built eleven times in `_compounds_plate` (:633). Reviewer claims `PracticeScreen` with two
tagged laps and `EventScreen` scrolled to the chips both exit 0xC0000409.
The suite passes because test_registers.py:307/321 call `theme.band_ink` directly and
**nothing in the suite ever paints a CompoundBand.**

**U2 · P2 · ui/engineer_screen.py:310 — all seven Race Engineer perception combos paint their unanswered "—" in CRAYON, so unanswered looks identical to answered.**
`_choices` builds each combo with a leading `"—"` carrying `None` and never calls
`widgets.mark_unset`. With no `color` rule on QComboBox in the stylesheet the text takes
`QPalette.ButtonText`, which `theme.apply` (theme.py:438) sets to CRAYON — the register
meaning "the driver entered this". Same for `self.worst`, whose sentinel is the
instruction "— tick symptoms above first —".
`mark_unset` (widgets.py:601-627) exists precisely for this and its own docstring names
the problem; it was applied to `rain_possible` on Event and both rack pickers on Practice.
The one screen whose entire left column IS the driver's report was missed.
Claimed rendered-pixel check: all seven return (163, 230, 53) = CRAYON `#A3E635`;
STRUCK is `#807870`. Consumed by `report()` (:465-482) via `.currentData() or ""`.
Rule: CLAUDE.md §4.3, §4.1; DESIGN.md "Placeholders are struck, never crayon."
Reviewer's fix notes a subtlety: `_refresh_worst` rebuilds inside `blockSignals(True)` so
`mark_unset`'s signal-driven sync never fires — **check that claim.**

**U3 · P2 · ui/race_screen.py:346 — the pit wall shows "Fuel N laps" in the MEASURED register, but it is a model output.**
`show_snapshot` adds Fuel with no `derived=`, so `SpecLine.add` builds a `Measured` and
paints STENCIL — the ink meaning "came off the telemetry stream". `lapsOfFuel` is
`RaceState.laps_of_fuel()` = `fuel_l / fuel_per_lap_l`, where `fuel_per_lap_l` is the
*planned* burn until three laps are in, then the median of observed burns
(coordinator.py:158-162, `BURN_LAPS_NEEDED` 3). "Box in" directly below was given
`derived=True` for exactly this reason, so one line carries a derived and a measured figure
in one ink. "Then <compound>" (:354) has the same problem — it is the plan's next stint.
Claimed rendered check: Fuel `color: #E8E4DC` (STENCIL) vs Box in `#B08BD8` (Derived).
Rule: CLAUDE.md §4.5. **Note this is the live race surface, so weigh it accordingly.**

**U4 · P3 · ui/practice_screen.py:74 — the FRESH SET picker is 10px too narrow, so "Carried over" renders "Carried o…" — the exact truncation its own comment claims it prevents.**
`W_SET_ON = 118`; `RackRow` calls `setFixedWidth(W_SET_ON)` (:464). Claimed measurement on
the real widget with the theme applied: edit-field rect 74px,
`horizontalAdvance('Carried over')` 84px, `elidedText` → 'Carried o…'; combo's own
`sizeHint()` is 128px. The control decides whether the wear rate is measured or assumed.
`CONTROLS_WIDTH` (:80) derives from it and the head cap uses the same constant (:758), so
a widened constant keeps heads aligned. **Re-measure rather than trusting the numbers.**

**U5 · P3 · ui/preview.py:84 — `NavRail.select` reads `self.stack`, never assigned.**
**ALREADY VERIFIED BY THE ORCHESTRATOR:** `sed -n '55,58p;80,90p' pitcrew/ui/preview.py`
shows `self._stack = stack` at :57, `self.select(0)` at :81, and
`if not 0 <= index < self.stack.count():` at :84. `PreviewWindow` names its own attribute
`self.stack` (:109), which is where the typo came from; app.py:227-231 has the correct
equivalent. So `python -m pitcrew.ui.preview` — documented in the module docstring as the
way to inspect screens without a PS5 — cannot start, in either interactive or `--shot` mode.
Consider the compounding effect: **this is the harness that would have caught U1.**
