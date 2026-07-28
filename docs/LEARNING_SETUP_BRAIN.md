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

## Phase 0 — Audit the loop (🔎 do first)
Before building more "learning," confirm what actually closes today, end to end in
the **new shell**:
- Is a `RuleOutcomeStore` outcome genuinely recorded when an applied change is
  followed by a recorded run? (store + closed-loop lockout exist — is the *feed*
  wired in the new shell, or only the classic one?)
- Is the `DriverProfile` version stamped onto outcomes and recommendations so scope
  keys are real?
- Does any path re-derive the profile from coaching/debrief today, or is it static?

Output: a one-page "what learns today vs. what's a stub" so phases 2–3 target real
gaps, not assumed ones.

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
