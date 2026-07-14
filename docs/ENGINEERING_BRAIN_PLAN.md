# Setup Brain → Engineering Brain — Plan of Attack (status tracker)

The Setup Brain has many good components (deterministic rules, vehicle/track/driver
reasoning, proven-history, balance solver, per-corner context, safety validation, AI
audit, discipline labels) but they must operate as ONE engineering system. The target
is Mode A (Complete Setup Synthesis) + Mode B (Closed-Loop Development), authored from
one canonical context toward a target handling model, scored per objective, and
learned from run to run. Full plan: the "Engineering Intelligence Plan of Attack".

## Build order & status

| Phase | Goal | Status |
|-------|------|--------|
| **1** | **Stop harmful behaviour (closed loop)** | **In progress** — lineage/attribution/lockout/rollback core done + rule-level lockout wired |
| 2 | Canonical engineering context | **done** — `SetupEngineeringContext` + working windows + capability confidence |
| 3 | Complete setup synthesis (target model, interaction graph, full-field candidate generator, coupled solver) | **core done** — `setup_synthesis.py` (surfaced additively; not yet the primary authoring path) |
| 4 | Discipline intelligence (independent Base/Quali/Race objectives, soft-tyre quali) | **done** — `discipline_objectives.py` (soft-tyre quali + RPM/shift targets + scoring priorities) |
| 5 | Per-corner + telemetry calibration | **core done** — `corner_diagnosis.py` (corner resolution + phase-separated causes + precise-test-on-missing-telemetry) |
| 6 | Strategy handoff | **done** — `setup_strategy_handoff.py` (clean evidence handoff + boundary guard) |
| 7 | Workflow-first UI | **surfacing done** — engineering-brain panels shipped; full editor/tablet overhaul deferred for visual review |

## Phase 1 — delivered so far

**NEW `strategy/setup_lineage.py` (pure)** — the deterministic memory an engineer keeps:
- `FieldChange` / `SetupExperiment` (parent + changes + the symptoms each change was
  EXPECTED to improve) / `ExperimentOutcome` (better/worse/unchanged + per-symptom +
  new problems).
- `attribute_change_outcomes` → per-change verdict EFFECTIVE / INEFFECTIVE / HARMFUL /
  UNKNOWN. Harm is attributed only via a targeted-symptom-worse OR a DIRECT known side
  effect, so an ineffective change is not falsely blamed for another change's damage
  (matches the plan: ARB reduction = ineffective, LSD-accel increase = harmful).
- `failed_directions` → harmful `DirectionKey`s scoped to car+track+objective+field+
  direction (a Fuji failure never becomes a global ban — plan §5.5).
- `apply_direction_lockout` → filters proposed changes that repeat a failed direction,
  overturnable by explicit stronger new evidence.
- `rollback_target` / `rollback_advice` → revert to the parent when an experiment made
  the car worse.
- `blocked_rules_from_outcomes` → builds a rule-level lockout from the persisted
  `learning_outcomes` (block a rule that worsened the car ≥2× and never improved it;
  a later `improved` verdict lifts the block).

**Rule-engine lockout (wired):** `run_rule_engine(..., blocked_rule_ids=…)` — a locked
rule is surfaced as a REJECTED candidate with the reason, never proposed. Pack-A safety
protection still runs first. `build_combined_setup_response` builds the lockout from the
`learning_outcomes` it already loads (scoped to car+track+layout) and surfaces
`closed_loop_lockouts`. **No schema migration** — it consumes data already captured by
`_trigger_scoring_pass`.

**Field-level lockout across ALL authors (wired):** `_rule_field_directions` maps each
rule to the (field, direction) it authors (from the delta_fn names); `failed_directions_
from_learning_outcomes` turns worsened outcomes into field-direction `DirectionKey`s, and
`apply_direction_lockout` filters the **balance solver + driver-fit** changes on the
telemetry path — so a harmful direction is not re-introduced by an author that doesn't
consult outcomes itself. Blocked moves are surfaced (and merged, not overwritten) in
`closed_loop_lockouts`.

**Tests:** `tests/test_setup_lineage.py` (15). Full suite green (~7373 passed, 0 failed).

## Phase 1 — lineage persistence, contradiction hard-fail, rollback (DELIVERED)

**Lineage persistence (additive DB migration v15):** a standalone `setup_lineage` table
(touches no existing table; `DB_VERSION` 14→15) recording each applied setup as a node
derived from a PARENT node by a set of changes, with the measured outcome once scored.
`SessionDB.record_lineage` (auto-resolves the parent as the latest node at this
car+track+layout scope), `record_lineage_outcome_by_rec`, `get_lineage`. Wired:
`apply_recommendation_for_car_track` records a node from the rec's applied changes; the
scoring pass (`_trigger_scoring_pass`) stamps each node's verdict.

**Contradiction hard-fail:** `detect_diagnosis_contradictions(diagnosis)` — a central
coherence check (gearing conflicting, wheelspin conflicting, bottoming incoherent). Any
authored change on a contradicted field is withheld (→ a controlled test) and surfaced
as `diagnosis_contradictions`, so a setup is never authored over conflicting evidence.

**Rollback advisory:** `rollback_from_lineage(rows)` — if the driver's last SCORED setup
tested worse, recommend reverting its changes to the parent; surfaced as `rollback` on
the analyse response.

**Tests:** `tests/test_setup_lineage.py` (20) + `test_session_db` schema. Full suite green
(~7377 passed, 0 failed). 7 stale "no new migration" guards (Groups 55–61, read-only
sprints) updated to allow the legitimate v15 and guard v16.

## Phase 1 — still to do

- **Structured better/worse-vs-baseline UI** in Practice Review (today the direction is
  DERIVED from telemetry scoring + feedback classification, which now feeds lineage — an
  explicit combo would strengthen the signal). Low incremental value; UI-only.
- **Rollback UI button** (the advisory + revert set now exist on the backend).

## Phase 2 — canonical engineering context (DELIVERED)

**NEW `strategy/setup_engineering_context.py`** — one immutable `SetupEngineeringContext`
that bundles Driver + Car (vehicle model) + Track (tune profile + per-corner) + Event +
current evidence (setup, diagnosis, proven history), built ONCE, and derives:
- **Working windows** — `build_working_windows`: every adjustable field gets a WINDOW
  (`low..high` + `preferred` + `sources` + `confidence`) assembled through the documented
  `EVIDENCE_PRECEDENCE`. A strong proven value narrows the window toward what worked
  (high/medium confidence); no proven value → the full legal range at low confidence; a
  locked field collapses to its current value. It is a *range with evidence*, not a
  forced value — the substrate the Phase-3 solver will select from.
- **Confidence separated by capability** — `track_confidence_by_capability`
  (setup_shaping / corner_detail / geometry), not a single flag.
- **Current-vs-historical feedback state** — `feedback_state` distinguishes what the
  driver reports NOW from their proven historical preferences.
- Honest `missing_evidence`.

Surfaced on the baseline/discipline response as `engineering_context` (`as_json`).
`tests/test_engineering_context.py` (11). Full suite green (~7369 passed, 0 failed).

## Phase 3 — complete setup synthesis (CORE DELIVERED)

**NEW `strategy/setup_synthesis.py`** — the deterministic engineer that builds a whole
car toward a goal:
- **Target handling model** (`build_target_handling_model`): the desired car behaviour
  across 10 handling axes (entry rotation, apex front support, exit traction, power-
  oversteer resistance, trail-braking stability, high-speed stability, kerb compliance,
  tyre preservation, fuel efficiency, consistency), from driver × car × track ×
  objective × current diagnosis.
- **Parameter interaction graph** (`PARAMETER_INTERACTIONS`): how raising each field
  moves each handling axis — reason in systems, not sliders.
- **Full-field candidate generator** (`generate_candidates`): several complete
  candidates (balance / driver-history / aggressive lenses), each field chosen within
  its Phase-2 working window toward the target-desired direction.
- **Coupled objective solver** (`score_candidate` + `synthesize_setup`): objective-
  weighted match between predicted and target handling minus a coherence penalty, then
  select the best — with per-field provenance and honest confidence.

Surfaced as `setup_synthesis`. Qualifying vs Race select materially different complete
setups from the same evidence. `tests/test_setup_synthesis.py` (8). Full suite green
(~7366 passed, 0 failed).

**Not yet:** making synthesis the PRIMARY authoring path (currently an additive,
validated surface beside the existing authoring); richer per-axis magnitudes.

## Phase 4 — discipline intelligence (DELIVERED)

**NEW `strategy/discipline_objectives.py`** — Base/Qualifying/Race as independent
products:
- **Soft-tyre qualifying enforcement** — `softest_dry_compound` / `qualifying_tyre_plan`:
  qualifying runs the softest legal dry compound (peak one-lap grip; tyre life ignored),
  honest when only wet compounds exist, and respects a required-compound constraint.
- **Objective RPM/shift targets** — `objective_rpm_target`: qualifying revs each gear out
  over one lap; race short-shifts and leaves headroom for traction/fuel; base balanced.
- **Scoring priorities** — `objective_priorities`: the readable factor weighting each
  discipline optimises (quali = one-lap pace/rotation/peak grip; race = tyre deg / lap-
  time variance / traction / fuel).
- `discipline_objective_summary` surfaced as `discipline_objective` on the response.

`tests/test_discipline_objectives.py` (9). Full suite green (~7367 passed, 0 failed).

## Phase 5 — per-corner + telemetry calibration (CORE DELIVERED)

**NEW `strategy/corner_diagnosis.py`** — a corner-scoped complaint is turned into precise
engineering:
- **Corner resolution** — `parse_corner_number` + `resolve_corner_reference`: "Corner 2"
  / "T2" / "turn 2" resolves against the reviewed track segments to the real apex
  (progress + direction), honestly low-confidence when it cannot be matched.
- **Phase-separated causes** — `diagnose_corner_feedback`: buckets the complaint by phase
  (entry/apex/exit/braking) and lists the candidate causes (front-grip limit vs LSD
  preload vs excessive accel-lock vs insufficient rear support vs wrong gear vs
  compliance), each with the fields + handling targets involved.
- **Precise test on missing evidence** — when the speed/wheel-slip telemetry to pick
  between causes is unavailable, confidence is reduced and a concrete controlled test is
  prescribed (capture X, Y, Z over 3 clean laps) — never a guessed single cause.
- `diagnose_from_feeling` wires it to free-text feedback; surfaced as `corner_diagnosis`
  on the analyse response.

`tests/test_corner_diagnosis.py` (8). Full suite green (~7366 passed, 0 failed).

**Not yet:** live per-corner telemetry aggregation + wheel-slip classification from real
captures (the causes + tests are ready to consume it); structured per-corner feedback UI.

## Phase 6 — Strategy handoff (DELIVERED)

**NEW `strategy/setup_strategy_handoff.py`** — the clean boundary between the two brains:
- `build_setup_strategy_handoff(context, synthesis)` packages the race setup's
  strategy-relevant CHARACTERISTICS (tyre preservation, traction stability, fuel/drag
  efficiency, consistency — from the target handling model) as EVIDENCE for the Strategy
  Brain, with readable strengths/weaknesses. Only meaningful for a race setup.
- `STRATEGY_OWNED` names what the Strategy Brain owns (degradation curve, crossover lap,
  fuel-per-lap, refuel/pit loss, legal candidates, compound + pit timing, total-race-time)
  and the Setup Brain must not author.
- `handoff_respects_boundary` — a guard (asserted in tests + callable by callers): the
  handoff carries the `setup_provides_evidence_only` marker and NO strategy-authoring
  keys (pit_lap/compound/stint/total_race_time/…). Surfaced as `setup_strategy_handoff`.

`tests/test_setup_strategy_handoff.py` (6). Full suite green (~7364 passed, 0 failed).

## Phase 7 — workflow-first UI (SURFACING DELIVERED)

The engineering brain's reasoning is now shown to the driver in the Setup Builder result
via self-guarding, Qt-free, module-level render panels (`_engineering_brain_html` +
the earlier `_closed_loop_html` / `_balance_solution_html` / `_driver_fit_html` /
`_discipline_field_plan_html`):
- **Discipline objective** — what this setup optimises + the enforced qualifying tyre +
  the RPM/shift intent.
- **Complete-setup synthesis** — the target handling drivers + the best candidate lens +
  candidate scores.
- **Per-corner diagnosis** — the resolved corner, phase, candidate causes and the precise
  test when evidence is missing.
- **Setup → Strategy handoff** — the race setup's tyre/fuel/consistency evidence "for the
  Strategy tab", with the boundary stated.

`tests/test_engineering_brain_ui.py` (3) + UI smoke + phase15 green. Full suite green.

**Deferred (needs interactive visual review):** the full layout overhaul — one-setup-
editor segmented switch, a dedicated Base/Quali/Race comparison workspace, a setup
lineage/development timeline with rollback buttons, structured Practice Review controls,
and tablet/mobile responsiveness. These are visual-design changes on the large PyQt files
that cannot be verified in the headless (segfault-prone) test environment; they should be
done with the app running in front of a reviewer.

## Status: Phases 1–6 complete + merged to master; Phase 7 surfacing done, layout overhaul deferred.
