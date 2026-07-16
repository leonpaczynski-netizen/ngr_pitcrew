# Sprints 9, 10 & 11 — Practice→Strategy handoff, guided-UI backbone, local voice

**Status:** COMPLETE (domain + backbone + local voice; Qt widget rendering is the remaining visual layer)
**Branch:** milestone-5-handoff-ui-voice (off master)
**Addresses:** UAT Defect 5 (practice→strategy handoff), Requirement 5 (guided UI, saved-vs-applied), PTT/local-voice requirement.

## Sprint 9 — PracticeEvidenceBundle (`strategy/practice_evidence_bundle.py`)
One explicit object Practice writes and Strategy reads automatically — no manual re-entry:
- Carries event/car/track/layout identity, race rules, fuel/tyre multipliers, refuel rate, mandatory stops, required compounds, **approved-setup id + applied-in-GT7 checkpoint id**, the measured `RaceStrategyEvidence`, tyre curves + crossovers, cross-lap patterns, driver feedback, confidence, missing evidence, provenance (session ids, timestamp), and a deterministic change hash.
- `bundle.strategy_evidence` is the exact object Strategy consumes (`recommend_strategy`).
- `detect_bundle_staleness` flags when the setup, checkpoint, multipliers, track, layout, duration, or refuel rate moved on — or the setup was never confirmed in GT7, or newer practice exists.

## Sprint 10 — guided-UI backbone (three pure, tested modules)
- **`ui/workflow_stepper.py`** — the 12-stage "follow the bouncing ball" state. From the canonical inputs it computes each stage's status (DONE / CURRENT / BLOCKED / PENDING), blocker text, and the single next action + next tab. The first not-done stage is CURRENT (or BLOCKED); a saved-but-not-applied setup surfaces the pending-change blocker.
- **`data/applied_checkpoint.py`** — the honest **saved-vs-applied-in-GT7** three-state model: `NOT_SAVED`, `CHANGED_SINCE_GT7` (with the exact pending field list), `CONFIRMED_IN_GT7`. `make_checkpoint` records what the "Changes Applied in Game" button confirms; a setup hash drives pending-field detection so autosave never masquerades as "applied".
- **`ui/setup_advice_render.py`** — structured advice rendering: turns the Sprint 6 `SetupDecision` + Sprint 5 persistence + Sprint 7 crossovers into an ordered list of typed `AdviceCard`s (decision banner, approved-changes table, preserved list, evidence-conflict card, controlled-test card, rejected list, cross-lap evidence table, tyre-crossover table). **No free-form prose blob.** Status is unambiguous — an engineering failure never renders an "approved" card.

## Sprint 11 — local-only voice (`voice/query_listener.py`)
- `_recognise` now uses **CMU PocketSphinx locally only**; the cloud `recognize_google` path was removed — speech never leaves the machine, no network required.
- Config default `speech_backend` → `sphinx`; the Settings combo offers only the local engine (cloud option removed).
- PTT remains a global OS-level hook (works across tabs/focus, unconditional start).

## Verification
- 46 new tests (bundle 13, UI backbone 15, local voice 5, plus earlier) — all pass.
- Full suite in chunks: **6811 passed, 0 failures.**
- All protected runtime files unchanged.

## Milestone 5 final report
- **Files:** +`strategy/practice_evidence_bundle.py`, +`ui/workflow_stepper.py`, +`data/applied_checkpoint.py`, +`ui/setup_advice_render.py`, +3 test files; modified `voice/query_listener.py`, `config_paths.py`, `ui/dashboard.py` (Settings combo).
- **Architecture:** explicit Practice→Strategy bundle; deterministic guided-flow, apply-state, and advice-rendering models; local-only speech.
- **DB/schema:** none.
- **Behaviour:** voice is now local-only; the handoff/stepper/apply-state/advice models are built and consumed by tests.
- **Known limitations (the remaining Qt visual layer):** the workflow stepper, structured advice cards, and the "Changes Applied in Game" button + applied-checkpoint persistence are modelled and tested but **not yet wired into the Qt widgets / rendered on screen**, and the practice→strategy "Build Race Plan from This Practice" action is not yet bolted to the Strategy tab. That wiring needs the running app for visual iteration and is the natural content of the release-hardening pass (Sprint 12) or a dedicated UI session. The deterministic logic every widget renders is complete and locked by tests.
- **Recommended next:** Milestone 6 — Sprint 12 (golden UAT: end-to-end Porsche-at-Fuji, offline, deterministic, all release gates) + wiring the Sprint 10 backbone into the Qt widgets with the app running.
