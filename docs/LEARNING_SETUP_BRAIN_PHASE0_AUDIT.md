# Phase 0 Audit — What the Setup Brain Actually Learns Today

Read-only trace (2026-07-28), three independent investigations. Bottom line up front:

> **In the everyday loop — apply a setup change, drive, record a run — the brain learns NOTHING today.** The machinery to *use* learning is fully wired; the machinery to *capture* it is not. The one narrow exception is the separate setup-**experiment** subsystem. The driver profile is 100% static.

This is good news, not bad: the expensive half (consume) exists and is correct. The gap is a well-defined write-side wiring job, not a redesign.

---

## The three questions

### Q1 — Does an applied change + recorded run teach the brain? **NO — write side broken.**

- **Consume side is fully wired** in the new-shell analyse path (`strategy/driving_advisor.py:1710-1776`): it builds a `RuleOutcomeStore`, seeds it from `SessionDB.get_learning_outcomes(...)`, passes it into `run_rule_engine(rule_outcome_store=…)`, and computes the closed-loop `blocked_rule_ids` lockout — all correct and enforced (`setup_rule_engine.py:786, 973-980`).
- **Write side is broken at two independent points:**
  1. The new shell's "I've entered this in GT7" (`_on_applied_in_game` → `SetupService.confirm_applied_in_game`, `services/setup_service.py:400`) writes **only** to the setup-state authority + revision history. It never calls the outcome writer `SessionDB.record_learning_outcome`.
  2. Even the *classic* writer chain is dead: `_trigger_scoring_pass` (`ui/dashboard.py:987`) → `record_learning_outcome` depends on `setup_recommendations` rows created by `insert_setup_recommendations` — which has **no production caller anywhere in the repo**. So the classic path records nothing either.
- **The store doesn't persist:** `RuleOutcomeStore` is in-memory only (its own docstring says persistence is "deferred"), and it's re-created fresh on **every** analyse call (`driving_advisor.py:1721`) — so even in-session nothing accumulates, and nothing survives a restart.
- **Net:** `learning_outcomes` is only ever populated by the separate experiment/campaign subsystem (`learn_from_experiment_outcome`, `_record_failed_direction_learning`), never by the ordinary apply→record loop. The everyday loop is open.

### Q2 — Is profile-version scoping real? **NO — a constant placeholder.**

- `profile_version` is the hardcoded literal `"v1.0-hardcoded"` (`strategy/setup_driver_profile.py:135, 151`), never changed at runtime — only by editing the source.
- It **is** threaded end-to-end (into `run_rule_engine`, the in-memory store key, and the DB `learning_outcomes.driver_profile_version` column), so the plumbing is real — but because the value never varies, "per profile version" distinguishes nothing.
- Extra dead weight: the DB read `get_learning_outcomes` (`session_db.py:6855`) filters only on `car_id, track, layout_id` — it **ignores** `driver_profile_version` entirely. Even a varying version wouldn't scope the DB read today.

### Q3 — Does the profile learn from coaching/debrief over time? **NO — 100% static.**

- `build_driver_profile()` takes **zero arguments**. All flags/tags are substring-matched from two fixed prose constants (`PERSONAL_DRIVER_TUNING_MODEL` / `DRIVER_HARD_CONSTRAINTS` in `setup_diagnosis.py`). Same inputs → identical profile forever; rebuilt fresh on every analyse.
- `build_coaching_review`, the debrief (`_feed_debrief`), and the Group-76 Holistic Brain verdicts are all **computed-fresh-then-displayed-and-discarded** — none writes back to a profile.
- **Greenfield, but with real scaffolding to leverage:** the per-run observed-driving signals already exist and are thrown away — `RunReview` (best-vs-avg gap, consistency, lock-ups, wheelspin, `practice_run_review.py:99-234`), `CoachingReview.limited_by` (car-vs-driver limit), and structured driver feedback. A persistence spine (setup-experiment tables + the `driver_profile_version` provenance column) is present. What's missing is (a) a writer that derives profile deltas from observed runs, (b) a profile store keyed by driver, and (c) `build_driver_profile` accepting observed evidence as input (today it accepts none).

---

## What learns today vs. what's a stub

| Capability | Status | Why |
|---|---|---|
| Rule-engine *consumes* outcomes (confidence up/down, lockout) | ✅ wired & correct | `driving_advisor.py:1721-1776`, `setup_rule_engine.py:973-980` |
| Everyday apply→record→outcome *capture* | ❌ not wired | `confirm_applied_in_game` never writes outcomes; classic chain dead |
| Outcome persistence across sessions | ❌ none | `RuleOutcomeStore` in-memory, rebuilt per call; DB has the table but the loop doesn't fill it |
| Experiment/campaign outcome learning | 🟡 exists (narrow) | separate subsystem writes `learning_outcomes` on confirmed regressions only |
| Per-(car,track) scoping | 🟡 partial | car/track flow through; but DB read ignores profile_version |
| Per-profile-version scoping | ❌ no-op | `profile_version` is a frozen constant; DB read doesn't filter on it |
| Driver profile evolving from coaching/debrief | ❌ static | `build_driver_profile()` takes no args; coaching/debrief display-only |

## Dead code found (worth cleaning up regardless)
- `SessionDB.insert_setup_recommendations` (`session_db.py:7349`) — no production caller → the classic scoring pass can never find rows to score.
- `learning_outcomes.driver_profile_version` — written but never read/filtered (`get_learning_outcomes` ignores it).

---

## Revised priorities (this audit updates the roadmap)

1. **Phase 2 write-side wiring is THE unlock, and it's small.** The consume side already works; wire the new shell's apply→record path to `record_learning_outcome` (an applied revision + a subsequent recorded run on the same scope → an improved/worsened outcome), and either persist `RuleOutcomeStore` or lean on the DB (already persistent) instead of rebuilding it empty each call. Do this first — it makes everything already-built come alive.
2. **Make `get_learning_outcomes` honour scope** (and decide whether profile_version should filter) once a real version exists.
3. **Phase 3 (profile evolution)** is greenfield but has the signals (`RunReview`/`CoachingReview`) and a persistence spine ready to consume — build the writer + profile store + let `build_driver_profile` take observed evidence.

Given the consume side is done, **item 2 (learn from outcomes) is far closer to working than item 3** — one write-path wiring away — whereas item 3 is a genuine build.
