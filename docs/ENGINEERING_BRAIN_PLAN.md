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
| 2 | Canonical engineering context | not started |
| 3 | Complete setup synthesis (target model, interaction graph, full-field candidate generator, coupled solver) | partial (engineering + balance + per-corner layers exist; not yet a candidate generator/solver) |
| 4 | Discipline intelligence (independent Base/Quali/Race objectives, soft-tyre quali) | partial (session bias + engineering objective shaping; no objective SCORING model yet) |
| 5 | Per-corner + telemetry calibration | partial (per-corner authoring from reviewed segments; no wheel-slip/speed calibration) |
| 6 | Strategy handoff | mostly exists (Strategy Brain owns total-race-time; setup provides evidence) |
| 7 | Workflow-first UI | partial (discipline table, balance/driver-fit panels) |

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

## Phase 1 — still to do (next increments)

- **Explicit parent→child lineage persistence** (a `parent_setup_id`/`origin_rec_id`
  on the setup/recommendation rows) so per-CHANGE attribution and rollback work on real
  saved setups, not just in-memory experiments. (Needs a small, additive migration.)
- **Structured better/worse-vs-baseline capture** in Practice Review (today only
  Liked/Hated/Neutral + free text; direction is derived).
- **Rollback UI** (revert to parent; branch instead of stacking on a failed child).
- **Contradiction hard-fail** in the canonical diagnosis (bottoming already reconciled;
  extend to wheelspin/gearing).

Then Phase 2 (canonical `SetupEngineeringContext`) and Phase 3 (target handling model +
interaction graph + full-field candidate generator + coupled objective solver).
