# Learning Setup Brain — Roadmap

The north-star directive (Leon, 2026-07-28): make the setup brain **personalize and
keep learning — deterministically and explainably.** This brain has **no AI/ML**
(the determinism rebuild removed it); "learning" means **outcome-tracking + driver-
profile evolution + confidence adjustment**, all offline, explainable, and evidence-
cited. Every phase below is bounded by the range clamp, the anti-ratchet movement
reserve, and the Pack-A safety invariants (item 6 is a standing constraint, not a
phase).

Legend: ✅ done · 🟡 partial · ⬜ not started · 🔎 audit needed to confirm current state

---

## Phase 0 — Audit the loop — ✅ DONE → [LEARNING_SETUP_BRAIN_PHASE0_AUDIT.md](LEARNING_SETUP_BRAIN_PHASE0_AUDIT.md)
Findings (2026-07-28, three read-only traces):
- **Everyday apply→record→outcome loop: OPEN.** The rule engine *consumes* outcomes
  and enforces the lockout correctly (already wired in the new shell), but nothing
  *captures* an outcome from an applied change + recorded run — the new shell's
  `confirm_applied_in_game` never writes one, and the classic writer chain is dead
  (`insert_setup_recommendations` has no caller). `RuleOutcomeStore` is in-memory and
  rebuilt empty every analyse.
- **profile_version scoping = no-op:** frozen `"v1.0-hardcoded"`; the DB read doesn't
  even filter on it.
- **Driver profile = 100% static:** `build_driver_profile()` takes no args; coaching/
  debrief are display-only.
- **Consequence for ordering:** item 2 is *one write-path wiring away* from working
  (consume side is done); item 3 is genuine greenfield (with usable signals). So
  **Phase 2 moves ahead of Phase 3.**

---

## Phase 1 — Scope everything (directive item 1) — 🟡
Every recommendation and every stored outcome keyed to **(car, track, layout,
driver-profile version)**; contexts never mixed.
- ✅ `scope_fingerprint` spine exists (engineering context key).
- ✅ **Per-car baseline authoring** — dampers/camber/toe now differ by car +
  objective (`derive_chassis_seeds`, commit `6a60297`). *Was: identical across cars.*
- ⬜ Verify the analyse path (rule engine) and the outcome store use the **same**
  scope key everywhere; close any place that falls back to an empty/global key.

## Phase 2 — Learn from outcomes (directive item 2) — 🟡 / 🔎
After each applied change + recorded run, record improved/worsened; strengthen what
repeatedly helps this scope, lock out what repeatedly hurts.
- ✅ `RuleOutcomeStore` (success rate per car+track+profile_version → confidence
  up/downgrade) and the **closed-loop lockout** exist.
- 🔎 Confirm the **feed is wired in the new shell**: applied recommendation →
  recorded run → outcome written. If the new shell doesn't feed it, this is the
  single highest-value fix (the store learns nothing if nothing writes to it).
- ⬜ Surface "this change has helped you N/M times on this car+track" in the Garage
  so the learning is visible, not hidden in a store.

## Phase 3 — Track style as it changes (directive item 3) — ⬜ **the heart**
Re-derive the driver profile from each **coaching run + debrief**, versioned over
time, so advice reflects how Leon drives **now** — not months ago. *This is the
missing engine.*
- ✅ `DriverProfile` is versioned; a coaching-run review (`build_coaching_review`)
  and the Holistic Brain per-corner/cross-session verdicts exist as inputs.
- ⬜ **Profile re-derivation:** a deterministic pass that reads recent coaching/
  debrief evidence (braking consistency, rotation, throttle habits, best-vs-avg)
  and produces a **new profile version** with updated style tags/biases — scoped so
  a wet-oval habit doesn't rewrite the road-course profile.
- ⬜ **Versioned history + decay:** keep prior versions; weight recent evidence more,
  age out stale traits, and *never* let a single session flip a trait (needs
  corroboration) — mirror the existing "age alone never decays" doctrine.
- ⬜ **Bind to outcomes:** when the profile version changes, the outcome store keys
  roll forward so old-style outcomes don't wrongly gate the new style.

## Phase 4 — Personalize the move (directive item 4) — 🟡
Bias **direction** toward known preferences; scale **magnitude** to how badly the
car is off.
- ✅ **Magnitude** — severity-scaled corrective steps (commit `755d095`): moderate/
  severe size the move toward the operating-band edge, gated by driver rating OR
  telemetry, bounded by clamp + reserve, disclosed in the rationale.
- ✅ **Direction** — `driver_fit` / profile-bias already lean the baseline toward the
  driver's window.
- ⬜ Feed the **evolving** profile (Phase 3) into both, so magnitude/direction track
  the current style, and let outcome confidence (Phase 2) temper an over-aggressive
  severity move automatically.

## Phase 5 — Deterministic, offline, explainable (directive item 5) — ✅ maintain
No AI/cloud; every recommendation cites its car/track/style/outcome evidence.
- ✅ Determinism rebuild complete; rule engine emits full explainability
  (evidence, rationale, provenance, considered-alternatives).
- ⬜ Standing rule: every new learning signal (Phases 2–3) must add a **human-
  readable citation** ("enlarged for severe handling", "seeded from your proven
  setup", "this helped 3/4 times here") — never a silent adjustment.

## Phase 6 — Never regress safety (directive item 6) — ✅ standing constraint
All learning bounded by the range clamp, the movement reserve, and the Pack-A
invariants. Every phase's tests must prove no proposal escapes these.

---

## Recommended order
1. **Phase 0 audit** (cheap, decides everything).
2. **Phase 2 feed** if the audit shows the outcome loop isn't wired in the new shell
   — biggest leverage: without it, nothing actually "learns".
3. **Phase 3 profile evolution** — the feature Leon most wants ("keep learning my
   style as it changes"); largest build, own sub-phases.
4. Fold the evolving profile back into Phase 4, tighten Phase 5 citations throughout.

Done so far: **Phase 1 (per-car authoring)** and **Phase 4 (magnitude)** — the two
UAT observations that kicked this off.
