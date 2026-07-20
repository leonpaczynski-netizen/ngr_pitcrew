# Engineering Brain — Program 2, Phase 12: Deterministic Vehicle Dynamics Knowledge Engine

**Status:** implemented on branch `eng-brain-phase12-vehicle-dynamics` (from `master` @ Phase 11 `0923f5c`).
**Schema:** **NO migration / NO persistence** — `DB_VERSION` stays **25**; `RULE_ENGINE_VERSION` unchanged (`46.0`).
**Nature:** the first phase of **Program 2**. A NEW read-only authority — Vehicle Dynamics
Knowledge — that explains the PHYSICAL MECHANISM behind each setup element ("what physical
mechanism is creating this behaviour?"). It is NOT a replacement for Program 1 (the
deterministic engineering workflow of Phases 1–11); it is an additional explanatory authority.

It NEVER creates experiments, ranks candidates, overrides evidence, or modifies outcomes,
memory or working windows. It only explains deterministic engineering relationships. No ML,
no statistics, no natural-language reasoning, no black-box scoring.

## 1. Problem solved

Program 1 answers "what happened previously?". Program 2 answers "what physical mechanism is
creating this behaviour?" — a curated, deterministic vehicle-dynamics knowledge base that
explains *why* a setup change produces an engineering outcome, with the primary mechanism,
secondary interactions and known GT7 limitations for every element.

## 2. Starting checkpoint

`eng-brain-phase12-vehicle-dynamics` from `master` @ Phase 11 `0923f5c` (Phases 2–11 stacked;
master at Phase 1). Golden `config_id`, frozen fan-out allowlist, Apply-gate predicate and
engine-wiring-status all unchanged.

## 3. Existing authorities reused (no overlap)

| Concern | Reused authority |
|---|---|
| Directional sign graph (field → axis → ±1) | Program 1 `setup_synthesis.PARAMETER_INTERACTIONS` (CONSUMED, never duplicated) |
| Canonical handling axes | the 9 axes owned by that graph |

Program 2 defines **no** new sign data — it reads the Program-1 graph as the single source of
truth for directions and layers mechanism + GT7 knowledge on top. It owns no DB, no session
state, and no decision logic.

## 4. New modules (all pure: Qt-free, DB-free, UI-free, network-free, AI-free, never raise, no clock/random, no decisions)

- **`strategy/vehicle_dynamics.py`** — the knowledge authority. `Component` (25 tunable elements)
  + `ComponentGroup` (suspension / differential / aero / tyres / brakes / transmission /
  weight-transfer / alignment) + `EngineeringExplanation` (primary mechanism, secondary
  interactions, GT7 limitations, raise/lower effect, axis effects from the Program-1 graph).
  `explain_component`, `explain_change(component, direction)` (direction flips the axis signs),
  `build_knowledge_report`, and the combined `build_engineering_knowledge`.
- **`strategy/load_transfer.py`** — `TransferMode` (longitudinal / lateral / combined / pitch /
  roll / yaw / platform) + `LoadTransferRelation` (mechanism, increased-by, decreased-by,
  balance effect, GT7 note). `explain_transfer`, `build_load_transfer_report`.
- **`strategy/handling_balance.py`** — `HandlingPhase` (corner entry / trail braking / initial
  rotation / mid-corner / exit traction / power-on rotation / straight-line / high-speed
  stability) + `PhaseExplanation` (dominant mechanism, key components, load-transfer modes,
  understeer-if, oversteer-if, GT7 note). Composes the component + load-transfer knowledge.
- **`strategy/setup_interactions.py`** — `ComponentInteraction` (spring↔damper, damper↔ARB,
  ride-height↔aero, camber↔tyre, toe↔stability, differential↔suspension) + `InteractionType`
  (reinforcing / opposing / enabling / limiting) + the detailed LSD model (initial / accel /
  decel) and aero model (front / rear balance, ride-height sensitivity, platform dependence,
  high-speed behaviour). `explain_interaction`, `interactions_for`, `lsd_model`, `aero_model`.

## 5. Vehicle model coverage

Springs, dampers (bump/rebound × front/rear), ARBs, ride height, camber, toe, brake balance,
LSD (initial/accel/decel), ballast, weight distribution, fuel load, aero (front/rear),
transmission and tyres — 25 components across the 8 groups, each with a primary mechanism,
secondary interactions and GT7-specific limitations.

## 6. GT7-specific knowledge

Modelled separately from generic race-car theory, as GT7 limitations per component and a GT7
note per load-transfer mode / handling phase / interaction — e.g. bottoming/ride-height
sensitivity, LSD decel curing lift-off snap, tyre-wear drivers, aero ride-height gating, and
the platform sensitivity that makes GT7 setups distinctive.

## 7. Output

Every explanation identifies the **primary mechanism**, the **secondary interactions** and the
**known GT7 limitations**; `explain_change` additionally returns the directional effect and the
affected axes (sign-flipped for raise vs lower). All outputs are deterministic dicts.

## 8. UI — the Engineering Knowledge panel

- `ui/engineering_knowledge_vm.py` — pure Qt-free view-model over `build_engineering_knowledge`,
  grouped by Suspension / Differential / Aero / Tyres / Brakes / Transmission / Weight transfer,
  plus load-transfer, handling-phase, interaction, LSD and aero rows.
- `ui/engineering_knowledge_panel.py` — `EngineeringKnowledgePanel`, a self-contained read-only
  reference panel (13 grouped tables). **No Apply controls** (asserted).
- Surfaced in the existing **Development History** page (static reference; renders on
  construction). No new tab, no registry change, no DB call.

## 9. Determinism & purity verification

- All 4 modules verified free of random/wall-clock/sqlite/Qt/network AND of any
  setup-authoring / experiment-selection call (asserted).
- Every report is restart-deterministic (identical `content_fingerprint` on rebuild).
- Metamorphic: `explain_change` raise vs lower flips every axis sign.
- Consistency: every component's axis effects exactly match the Program-1 sign graph (no
  duplication, no contradiction) and use only canonical axes.

## 10. Schema / contract changes

**None.** No migration, no persistence, no new tab. `DB_VERSION` 25, `RULE_ENGINE_VERSION` 46.0.
Golden `config_id`, frozen fan-out allowlist, Apply-gate predicate and engine-wiring-status
untouched.

## 11. Tests

`tests/test_phase12_{vehicle_dynamics,models,view_model}.py` (36 non-UI) +
`tests/test_phase12_ui_construction.py` (3 UI — run individually). Property (every component
fully explained), metamorphic (raise/lower sign flip), consistency (axes match Program 1),
determinism/restart, golden knowledge assertions, and safety (no decisions/mutation).

## 12. Known limitations / deferred

- The knowledge base is curated GT7-focused race-engineering knowledge; it is qualitative
  (directional mechanisms), not a numeric tyre/aero simulator.
- The panel is surfaced in the Development History page; a dedicated "Engineering Knowledge" tab
  is deferred (the panel is self-contained and tab-ready).
- Program 3 could connect this explanatory authority to Program 1's diagnosis so a residual
  issue is annotated with its physical mechanism — deferred.

## 13. Recommended Phase 13

**Mechanism-annotated diagnosis** — deterministically attach the Vehicle-Dynamics mechanism
explanation to a Program-1 residual issue / proposed change (e.g. "this exit wheelspin is an
LSD-accel / rear-load mechanism"), joining the "why" authority to the "what happened" workflow,
still a pure observer that changes no Program-1 authority.
