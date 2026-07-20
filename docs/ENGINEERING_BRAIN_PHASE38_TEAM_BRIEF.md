# Engineering Brain — Program 2, Phase 38: Integrated Race-Engineer Team Brief

Read-only, offline, deterministic, advisory-only. Part of the combined **Phases 36-38 Race-Engineer
Activation** slice. DB stays **v26**; rule engine **46.0**; no migration; no DB write; no setup values.

## Purpose

Layers 7-8. Assemble the Phase-36 activation and the Phase-37 learning into **one** coordinated
race-engineer plan for the current event, and expose it read-only in the UI. **The driver receives one
coherent plan, not several disconnected reports** (the Phase 38 invariant).

## Authority ownership

| Module | Owns |
| --- | --- |
| `strategy/race_engineer_team_brief.py` | The coordinated crew brief, contradiction resolution, the ordered plan. |
| `strategy/race_engineer_team_brief_render.py` | Deterministic role-labelled renderer. |
| `ui/race_engineer_team_vm.py` / `ui/race_engineer_team_panel.py` | Pure VM + read-only panel. |

It composes the already-built Phase-36/37 products (dicts) — it recomputes no authority and duplicates
no engine.

## Coordinated crew architecture (crew-role boundaries)

Five role-specific but **non-duplicated** sections, each a VIEW over the shared canonical evidence (not
five independent authorities or AI personas):

- **Chief Engineer** — objective, context readiness, highest-priority problem, conflicts, ordered next
  actions, stop/defer conditions.
- **Setup Engineer** — current best-**proven** setup (explicitly *not* an ultimate setup), confirmed-good
  to protect, working windows, latest outcome, the next existing canonical bounded experiment
  (referenced, never created), rollback plan, success/failure criteria.
- **Performance/Data Engineer** — repeatable findings, corner losses/strengths, gear & drive-out
  findings, confidence, missing evidence, recommended collection.
- **Driver Coach** — one or two priorities with technique focus, target corners and measurable
  verification.
- **Strategy Engineer** — race-plan implications, tyre/fuel/stint evidence, whether an experiment
  risks race prep, and the evidence still required before trusting a race plan.

## Contradiction resolution

The brief never recommends mutually opposing setup or driving actions at once. Detected conflicts are
resolved by **sequencing** with an explicit hold-constant and surfaced as alternative controlled
hypotheses:

- `coaching_vs_setup_experiment` — a coaching test needs the setup held constant while a setup
  experiment would change it → run them in separate sessions.
- `explore_vs_rollback` — a field looks worth exploring but the current state is a regression → resolve
  the regression first, then explore from a stable base.

The result is one ordered `ordered_development_plan` (numbered steps with rationale and hold-constant).

## Authority reuse & non-duplication proof

`subordinate_fingerprints` records the `content_fingerprint` of each consumed layer (activation,
outcome_learning, working_windows, driver_development, coaching_plan). The brief hashes these plus the
plan/context — it never rebuilds a lower layer. The SessionDB entry builds the Phase-22 chain exactly
once (see below).

## Read-only SessionDB entry & query shape

`SessionDB.build_race_engineer_team_brief(...)` → `{ok, brief, context_fingerprint, completeness,
exact_evidence_count, plan_step_count, content_fingerprint}`. It resolves the current context ONCE
(Phase-22 primary key + the current session's track/layout/compound), reuses `_build_knowledge_chain`
**once** (the single bounded evidence read), computes Phases 36-38 purely in memory, **never calls the
lower public SessionDB builders**, performs no extra DB reads (constant query count for small and large
histories; no N+1), writes nothing, and creates no experiment. An empty programme returns a truthful
collection-plan brief. No migration.

## UI placement

`RaceEngineerTeamPanel` sits in **Development History**, beneath the Phase-33-35 Assurance Review Pack
panel. It has NO Apply / setup-mutation / experiment / campaign / scheduler / editable-grade /
editable-priority / AI / auto-export control; it renders only the finished immutable dict. The heavy
build runs OFF the Qt thread via the reused `MechanismAnnotationWorker`, and
`_on_race_engineer_team_brief_ready` guards on the current worker so a stale result cannot replace a
newer one.

## Deterministic fingerprint hierarchy

subordinate layer fingerprints → brief `content_fingerprint` (over context fingerprint + completeness +
subordinate fingerprints + ordered plan + highest-priority + contradiction kinds). Canonical ordering
is material where it is part of the plan's meaning; runtime/object identity, machine identity,
destinations and wall-clock are excluded. Restart-, `now_date`- and shuffle-stable.

## Safety invariants & deferred work

Pure domain module (no Qt/DB/network/AI/clock/random); never raises; authors no setup value; creates no
experiment; the brief is **not a certification and never claims a final or "ultimate" setup**; newer is
never treated as better merely because it is newer.

**Deferred (not started):** a recommended next grouped slice is Phase 39+ — live in-session coaching
delivery (voice/telemetry-timed prompts), automated experiment-candidate linkage from the Phase-17
portfolio, and race-strategy integration with the live progress resolver. The previously-deferred
release-assurance features (signed manifest, multi-snapshot assurance timeline, reviewer-annotation
import) remain deferred.
