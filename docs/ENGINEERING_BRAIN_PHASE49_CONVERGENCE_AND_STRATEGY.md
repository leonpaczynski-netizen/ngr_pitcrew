# Engineering Brain — Phase 49: Convergence, Setup Lock-In & Strategy Maturation

Program 2, Phase 49. Read-only, deterministic, offline, no AI. Turns cumulative Practice evidence into a
controlled final engineering decision before the official race. Authors no setup value, applies nothing.

## Setup convergence — `strategy/setup_convergence.py`

`SetupConvergenceState` (11): `insufficient_evidence`, `exploring`, `diverging`, `improving`,
`stable_with_uncertainty`, `provisional`, `ready_for_confirmation`, `lock_ready`, `locked`, `reopened`,
`rollback_recommended`. `assess_convergence_state` is a deterministic ladder:

- A validated regression dominates → `rollback_recommended` (if a rollback target exists) else `reopened`.
- `lock_ready` requires **≥3 valid confirming runs + an explicit final-confirmation run + no outstanding
  experiments** — one quick lap is never lock-ready.
- A single noisy/inconclusive lap never auto-reopens a stable setup.
- A locked setup stays locked until a validated regression.
- Base / Qualifying / Race converge independently and need not match.

`SetupCandidateComparison` / `build_setup_comparison`: order-independent side-by-side across a fixed
13-dimension set; missing dimensions are `unknown` (never fabricated); surfaces protected-strengths and
unresolved-risks unions; declares no absolute winner — a human selects.

## Setup lock & restriction — `strategy/setup_lock.py`

`build_lock_decision` locks **only** when `confirmed=True` AND convergence permits (`lock_ready` /
`ready_for_confirmation` / `stable_with_uncertainty`-with-warning). A repeated call with
`confirmed=False` never locks → a dashboard refresh cannot lock/unlock. The lock is a **provenance
decision, not an Apply bypass**: it does not import or call `ActiveSetupAuthority.mark_applied`, which
remains the sole setup-mutation route. NGR-neutral `SetupRestrictionState`
(open/advisory/locked/post-qualifying/restricted-after-lock), `AllowedPostLockChange`, `SetupLockPolicy`;
parc fermé is one configurable state, never assumed. `post_lock_change_allowed` enforces the restriction.

## Tyre / fuel / strategy maturation — `strategy/strategy_maturity.py`

`StrategyMaturity` ladder: `no_evidence` → `early_model` → `partial` → `developing` →
`validation_required` → `provisional` → `finalisation_ready` → `finalised`, with `replan_required` on a
changed dependency. `FINALISATION_READY` requires a validated long-run + fuel evidence with race
duration and multipliers known. `TyreFuelMaturity` reads the cumulative evidence domains: 4 exact long
runs → `MATURE` tyre; an unknown fuel multiplier → `CAPPED` fuel. `missing_evidence` is always exposed.

## Strategy finalisation & deadline-aware risk — `strategy/strategy_finalisation.py`

`build_strategy_finalisation` finalises **only** on explicit confirmation. If not `FINALISATION_READY`
it finalises only when the driver explicitly accepts a low-confidence plan (assumptions/missing evidence
stay visible); otherwise it stays un-finalised and states what is missing. Presents primary + alternative
`StrategyPlan` (race-time/fuel/tyre/stints/pit windows/pit loss/triggers/weather/deps).

`assess_deadline_risk` becomes conservative as the race nears: a high-interaction coupled experiment
within ~3 days is `BLOCK_UNLESS_OVERRIDDEN`; with an explicit override it proceeds as
`PROTECT_BEST_KNOWN` with a visible warning. Race week → `PREFER_CONFIRMATION`; early → `EXPLORATORY_OK`.
The countdown feeds this advisory output only, never the cycle-identity fingerprint.

## Tests

`test_phase49_convergence.py` (13), `test_phase49_setup_lock.py` (8),
`test_phase49_strategy_maturity.py` (8), `test_phase49_finalisation_risk.py` (11).
