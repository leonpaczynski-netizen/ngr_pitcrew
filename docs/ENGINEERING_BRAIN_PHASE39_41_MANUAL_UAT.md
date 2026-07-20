# Engineering Brain — Phases 39–41 Manual UAT Guide

A written guide for executing manual UAT of the closed-loop engineering workflow against a **real**
engineering history. Prefer a Porsche 911 RSR '17 history at Fuji Full Course where available.

> **A written guide is not executed UAT.** The completion report states whether this was actually run.
> As of this slice it has **NOT** been executed in the live GUI (no live app run in this environment);
> the equivalent behaviours are proven by unit / property / runtime tests (see the testing register).

## Preconditions
- A SessionDB with a real Porsche 911 RSR '17 @ Fuji Full Course development history (exact-context
  records) and, ideally, some Daytona (incompatible) records for the same car/driver.
- Launch the app; open **Development History**; scroll to **Closed-Loop Engineering Development**.

## Steps & expected results
1. **Exact context** — the panel's Evidence Readiness card shows the correct driver, car, track,
   layout, event and discipline; the context fingerprint is present.
2. **No cross-track contamination** — with Daytona records present, the evidence scope shows them as
   `excluded` (contamination guard); the Fuji exact-domain summary counts/convergence do **not**
   include Daytona evidence.
3. **Applied & parent setup** — the run-plan card shows the current applied setup and its parent
   correctly.
4. **Existing candidate** — the selected candidate has an id from the Phase-17 portfolio; the card
   states "existing … referenced, never created" and preflight required.
5. **Changed vs held-constant** — the controlled-change section lists exactly the field(s) to change;
   Held Constant lists every other applied field + compound/fuel/tyre-age/weather/assists.
6. **Lap/tyre/fuel/feedback requirements** — run structure shows warm-up/measurement/min-clean/max
   laps, target corners+metrics and required driver feedback.
7. **Mark a run invalid** — supply an observation with a wrong compound or an unplanned field change;
   the Outcome Review shows `CONFOUNDED`/`INVALID` and "does not count for learning".
8. **Expected vs observed** — supply a valid observation; the review compares expected vs observed and
   states the outcome state.
9. **Regression → rollback** — supply an observation with a protected/new regression; the primary next
   action is `roll_back` (or `isolate_field` for a multi-field bundle).
10. **Valid improvement → eligible, not applied** — supply a valid, repeated improvement; promotion is
    `best_known_eligible`; **no setup is applied automatically** (the Apply gate is untouched).
11. **Qualifying vs Race** — repeat with discipline Qualifying; the objective/gearing differ and a
    qualifying result is not assumed for race.
12. **Coherent next action** — exactly one primary next action is shown; secondary actions do not
    conflict.
13. **No runtime file changes from viewing** — before/after opening and viewing the workflow, confirm
    `data/setup_history.json`, `active_setup_state.json` and the track models are byte-unchanged (the
    runtime test `test_db_byte_identical_before_and_after_workflow` proves the DB equivalent).
14. **No AI / auto-apply / auto-create** — confirm no network calls, no experiment created, no outcome
    written, no setup applied merely from using the workflow.

## Recording results
For each step record PASS/FAIL with a note. File any FAIL as a defect; do not describe the branch as
UAT-complete until the steps are actually executed.
