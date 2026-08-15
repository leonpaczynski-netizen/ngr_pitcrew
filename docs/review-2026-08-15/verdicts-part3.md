# Adjudicated verdicts, part 3 — engineer (E) + UI (U)

CONFIRMED: E1 P1, E2 P1, E3 P1, E4 P2, E6 P2, E8 P2, E9 P3, E10 P3,
U1 P1 (mechanism corrected), U2 P2, U3 P2, U4 P3, U5 P3
DOWNGRADED: E7 P2→P3
REJECTED: E5

## The correction that matters most

**U1 — CONFIRMED, but the WRITE-UP'S MECHANISM IS WRONG. Stays P1 on different grounds.**
PyQt6 calls `qFatal()` only when `sys.excepthook` is still `sys.__excepthook__`.
`app.main()` calls `diagnostics.install()` as its **first statement** (app.py:378), which
installs a non-default hook. Measured both ways:

| configuration | Practice, one tagged lap | Event, scrolled to chips |
|---|---|---|
| no excepthook (bare PyQt6 default) | **exit 127 (abort)** | exit 0 — chips below the fold, never painted |
| `diagnostics.install()` — **the shipped path** | **exit 0, survives** | **exit 0, survives** |

**The shipped app does NOT crash. UAT can start.** Independently re-confirmed by the
orchestrator: with `diagnostics.install()` the paint raises and returns exit 0.
What it actually does: every paint of every coded band raises, so **the two-letter code is
never drawn on any band or chip anywhere in the app**, and each paint writes a full
`CRITICAL … AttributeError` traceback to the log. One Event screen scrolled to the rack
emitted five in a single render pass; eleven chips plus one band per lap row, repainted on
every hover, scroll, resize and compound change, fills the log CLAUDE.md §7 depends on —
on the GUI thread. Breaks DESIGN.md verbatim: "**Colour is never the only channel.**
Every band carries its two-letter code."
*Origin confirmed:* `git log -L 344,358:pitcrew/ui/widgets.py` shows two commits —
`7d8e56d` created it with the working `theme.band_ink(self._code)`, and **`cbe19fe`**
replaced it with `band_ink_for(over)` plus a nine-line comment justifying a function never
written. Fresh regression, four commits back from HEAD.
*Fix:* the intended function must be WRITTEN — `band_ink_for(QColor) -> QColor` picking by
WCAG relative luminance against the colour actually painted (DESIGN.md:98-99), which is
what `band_ink(code)` already does one step earlier in the chain.

## Engineer

- **E1 CONFIRMED P1.** Standalone script, real event loop on main thread, daemon thread
  standing in for pynput's: `QTimer.singleShot(0, lambda)` posted from the worker **never
  fired**; the identical call from the Qt thread fired on MainThread. Call really is on
  pynput's thread (`_process` runs on its own daemon thread; `_reply` calls `_on_answer`
  inline). Downstream: `_show_ptt_answer` never runs → `_resolve_replan` never runs from
  speech → `_pending_replan` stays set → `_check_replan` (controller.py:1697) is gated
  `if not verdict.offered or self._pending_replan is not None: return`, so **no further
  re-plan is ever offered for the rest of the race.** Meanwhile `_answer` (ptt.py:181-182)
  has already cleared `ptt.pending_replan` and spoken "Copy, changing the plan."
  *Fix check:* the obvious patch does NOT work — PyQt6 has no `singleShot(msec, context,
  slot)` overload (TypeError). Verified the correct fix empirically: a `pyqtSignal` on the
  controller, connected in `__init__`, emitted from the hook thread, dispatches on MainThread.
- **E2 CONFIRMED P1, verified live on this machine.** `settings.load(store)` on the real DB
  returns `speech_backend='sapi'`. `best_recogniser_for('sapi')` logs
  `SapiGrammarRecogniser unavailable: TimeoutError … did not come up within 5s` and returns
  a **MoonshineRecogniser** (9.3 s). A direct `SapiGrammarRecogniser(None)` hung past 120 s.
  But controller.py:242-244 picks `matcher` from the SETTING, so `matcher=None`, and
  `gate.judge` short-circuits to `Verdict(ACT, …)`. `best_semantic_matcher()` DOES return a
  working matcher here — **the gate is available and simply not wired.**
  *Fix:* one line — both classes carry `name` (`"sapi-grammar"` ptt.py:201, `"moonshine"`
  :310), so build the recogniser first and select the matcher from it.
- **E3 CONFIRMED P1.** Ran it: `'the front is pushing on entry'` → **position**;
  `'i have no grip at the rear'` → **keep**; `'not yet'` → **keep**;
  `'blah blah nonsense'` → **keep** (no**n**sense). Existing test passes by luck.
  **Compounding:** `gate.judge` tests `intent == UNKNOWN` BEFORE the `distance is None`
  short-circuit, so UNKNOWN is the only rejection path left once E2 removes the matcher —
  and E3 makes UNKNOWN nearly unreachable. E2+E3 together: free-dictated speech answered
  confidently with essentially no gate, and an OOV utterance while a re-plan is pending
  **silently declines it** (`KEEP` → `_resolve_replan(accepted=False)`).
- **E4 CONFIRMED P2.** Read the installed pynput source: `_emitter.inner` catches, logs,
  queues `exc_info`, calls `self.stop()` and re-raises, which `ListenerMixin._run` swallows
  in a bare `except:`. Listener stops permanently, surfaced only via `join()`, which nothing
  calls. `has_listener` only tests `is not None`.
- **E5 REJECTED — unreachable.** `begin`/`end` have exactly one caller, and pynput's win32
  listener delivers events on a single thread (`SystemHook._handler` posts `_WM_PROCESS` to
  that thread's own message loop; `_run` calls `_process` inline from the pump). Press and
  release are serialised, so a second `end()` cannot overlap and the `_busy` early-return
  cannot be entered in production. Would become live only if a second input source were
  wired to the same `PushToTalk`.
- **E6 CONFIRMED P2.** Two states genuinely indistinguishable at the snapshot. Arming with
  no plan is explicitly supported (controller.py:1570-1571 prints "no plan - fuel calls
  only"). *Correcting the reviewer:* this is NOT the only non-refusal None branch — BOX_WHAT
  does the same (:127-128) and `_plan_summary` appends "Running to the flag" (:150-151).
  LAPS_LEFT/FUEL/BOX_FUEL are all correctly `answered=False`.
  **A passing test encodes the bug:** `test_no_stop_planned_is_said_plainly`
  (test_ptt_and_replan.py:109-112) asserts `answered is True` for `lapsToStop=None`.
  Fix belongs at the SNAPSHOT (carry "is there a plan at all"), not at the answer.
- **E7 DOWNGRADED P2→P3.** Defect real, but reachability narrow: the common order is
  rebind-then-start-session, which calls `start()` and works. Only bites when the key is
  rebound DURING a live session.
- **E8 CONFIRMED P2.** Lifetime claim confirmed: `_button_probe` is cleared only at
  controller.py:833-835 (toggling LISTEN off) and 1764-1766 (shutdown) — nothing stops it on
  leaving Settings or on starting a race, so a forgotten probe mutates widgets off-thread
  throughout the race.
- **E9 CONFIRMED P3.** `last_reason` set at ptt.py:335, 344, 387, 406 and read **nowhere**;
  the race_screen.py hits are an unrelated `BodyLabel` of the same name.
- **E10 CONFIRMED P3.** Nothing truncates a capture; `check_audio` is applied after the
  stream is already closed, and TOO_LONG discards the ENTIRE transcript. The line-39 comment
  describes behaviour that does not exist.

## UI

- **U2 CONFIRMED P2, re-measured.** All seven combos paint their sentinel **(163,230,53)** =
  CRAYON `#A3E635`; a control combo built identically WITH `mark_unset` painted
  **(128,120,112)** = STRUCK `#807870`. No `color:` rule on QComboBox in the stylesheet, so
  `QPalette.ButtonText` (CRAYON, theme.py:438) wins. Reviewer's subtlety confirmed:
  `_refresh_worst` does clear/addItem/setCurrentIndex entirely inside `blockSignals(True)`,
  so `mark_unset`'s sync will not fire — the fix must call `sync` explicitly at the end.
- **U3 CONFIRMED P2, re-measured on a live RaceScreen.** `Fuel "8.3 laps"` renders
  **(232,228,220)** = STENCIL, class `Measured`; `Box in "3"` renders **(176,139,216)** =
  Derived. `Then "RM"` is also Measured. `lapsOfFuel` is the planned burn until 3 laps are
  in and the median of observed burns after — a model output either way.
- **U4 CONFIRMED P3, numbers exact.** First (offscreen) measurement gave nonsense — the
  offscreen platform failed to resolve Bahnschrift. Re-measured on the REAL Windows
  platform: `combo.width()` 118, edit-field rect **74px**,
  `horizontalAdvance('Carried over')` **84px**, `elidedText` → **'Carried o…'**,
  `sizeHint()` 128px. `CONTROLS_WIDTH` 474, row `sizeHint` 988 at 1280 wide, so raising to
  128 costs 10px and cannot overflow.
- **U5 CONFIRMED P3.** Dev harness, not a shipped surface — but it is the harness that would
  have caught U1.

## New defects
- **N6 · P3 · DESIGN.md:41 — the register table's Struck swatch is STALE.** DESIGN.md gives
  Struck as `#6B6459`; `theme.STRUCK` is `#807870` and theme.py:84 documents the lift. The
  spec the whole register review is measured against names the pre-fix colour, so anyone
  verifying U2-class findings against DESIGN.md compares pixels to the wrong value.
- **N7 · P3 · test_ptt_and_replan.py:109-112 — a passing test encodes E6** (see above).
- **N8 · P2, UNPROVEN — the whole recognition pass runs inside pynput's message-pump thread,
  which also owns the `WH_KEYBOARD_LL` hook.** `end()` → `_transcriber.update_transcription()`
  runs synchronously inside `ListenerMixin._run`'s message loop, so for the duration of
  transcription that thread is not pumping and cannot service its own low-level keyboard
  hook. Windows' `LowLevelHooksTimeout` (default 300 ms) silently removes hooks that do not
  return in time. If it fires, the PTT button goes dead mid-race with no exception and
  `has_listener` still True — the same end state as E4 by a different route, and reachable
  **without any error condition.**
  Could not prove without a microphone and a real key press. **Test:** time `end()` here
  (Moonshine tiny at 0.46x real time on a ~3 s capture is ~1.4 s, well past 300 ms), then
  check whether a second press is still detected. **This is a UAT item.**
- **N9 · P3 · ptt.py:530-553 — `build_within` abandons a thread that never dies.** When SAPI
  times out the probe thread is left running (still alive past 120 s), holding a
  half-initialised SAPI/COM object for the life of the process. Happens on **every** app
  start under the shipped default.
