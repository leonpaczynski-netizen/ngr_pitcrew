# Engineering Brain — Phase 65: Adaptive Live Race Strategy Brain

Program 2, Phase 65. Read-only, deterministic, offline, no AI. Continuously compares the pre-race plan with
trustworthy real-time race evidence and RECOMMENDS a revised strategy when the current plan is no longer
optimal. Advisory only — it makes no pit call, changes no GT7 control, applies no setup, and never
finalises a strategy. `strategy/adaptive_live_strategy.py` (pure; reuses the `race_strategy_replan`
fuel-viability authority + pre-race scored candidates).

## Two objectives (the core distinction)

- **Lap-count race** (`StrategyObjective.LAP_COUNT`): minimise expected total race time to complete the
  required laps. `project_lap_count(...)` → total race time = laps × lap-time + stops × pit-loss.
- **Time-certain race** (`TIME_CERTAIN`): maximise expected COMPLETED LAPS before the clock expires.
  `project_time_certain(...)` → `floor((time − stops·pit_loss) / lap_time)`. An extra stop that is faster
  per stint but costs a completed lap is **rejected**; one that yields an extra completed lap **may** be
  recommended (with explicit assumptions + confidence). **Minimum theoretical stint time alone is never
  used for a time-certain event** — `rank_candidates` orders time-certain candidates by expected completed
  laps first, so a lap-losing extra stop can never rank above keeping the plan.

## Live evidence + divergence triggers

`LiveStrategyState` carries only trustworthy evidence; unknown stays unknown. `detect_divergence_triggers`
fires fuel-burn-high/low, pace-slower/faster, tyre-deg-early/late, pit-loss-changed, damage, rain/drying,
penalty, consistency-drop — each with a **material threshold** (5% fuel, 1% pace, 15% tyre) so small noise
never replans. **Unsupported triggers are returned `available=False` (explicitly unavailable, never
silently absent).** Rain / damage / penalties are **never fabricated** — they fire only from telemetry OR a
confirmed driver report (`driver_reported` labelled, never auto-verified).

## Plan comparison, candidates & decision

`generate_replan_candidates` produces LEGAL, deterministic candidates (keep-the-plan, conservation, extra-
stop-for-pace/tyres) with projected total time / expected completed laps, fuel/tyre notes, and surfaced
ASSUMPTIONS; `rank_candidates` drops illegal candidates and orders by the objective. `decide_replan(state,
context_ok, rules_verified)` → `StrategyRecommendation`: PLAN_STILL_OPTIMAL / PLAN_VIABLE / MONITOR /
CONSERVATION_REQUIRED / PACE_INCREASE_AVAILABLE / REPLAN_RECOMMENDED / REPLAN_URGENT / INSUFFICIENT_EVIDENCE
/ CONTEXT_MISMATCH / RULES_UNVERIFIED. **Telemetry loss / insufficient inputs → INSUFFICIENT_EVIDENCE and
never a high-confidence replan.** Driver-reported-only divergence or unknown tyre age caps confidence to
LOW; unverified required rules hold a replan (RULES_UNVERIFIED). Context mismatch is surfaced, not hidden.

## Driver communication + acknowledgement + monitoring

`build_strategy_driver_message` → an audio-first `StrategyDriverMessage`: a concise HEADLINE first (what
changed → revised plan → expected gain → confidence → next review), with the detailed candidate comparison
DEFERRED (garage / on PTT request). `acknowledge_strategy` records receipt / an operational preference and
**executes nothing** — no pit stop, no GT7 control, no setup/fuel-map change, no accepted outcome, no
strategy finalisation. `StrategyMonitor` is a deterministic continued-monitoring guard: it suppresses a
repeat message unless the decision fingerprint materially changed OR the injected-time cooldown elapsed
(no per-lap spam). The decision records the active advisory plan, reason, confidence, next-review trigger
and the evidence that would invalidate it.

## Production integration

`strategy/live_audio_strategy_build.py` (`build_live_audio_strategy_view`) composes the Phase-63 audio
state + the Phase-65 decision + the concise message + the speech-window decision into ONE immutable,
**DB-FREE** view for the Live tab and the Phase-47 voice controller. `RaceStateTracker → immutable live
race snapshot → canonical strategy comparison → replan decision → workload gate → approved verbal message →
visual strategy card`. Bounded cadence; no DB query per packet; the off-thread worker + stale guard live in
the dashboard. Detailed candidate tables belong in the garage/strategy-review — VR operation never depends
on reading the table.

## Tests

`tests/test_phase65_adaptive_strategy.py` (24) + integration (`tests/test_phase63_65_integration.py`, 8) +
metamorphic proofs in `tests/test_phase63_65_safety.py`.
