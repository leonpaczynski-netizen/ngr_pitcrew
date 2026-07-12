# Race Engineer Brain Remediation — Phase 1 Root-Cause Audit

Branch: `race-engineer-track-specific-tunes-quali-discipline` (from master `cab54b1`).
Status: **audit in progress** — this is the mandatory Phase-1 deliverable; implementation
follows per the phased plan at the end. Setup is deterministic, rule-first, AI-audit-only;
no safety/Apply-gate boundary is weakened by anything proposed here.

> Scope note: the sprint prompt is a multi-week, 16-phase programme. This document is the
> audit + roadmap. Foundational safety phases (2 setup-snapshot integrity, 3 dominant-problem
> coherence gate, 4 feedback disposition) are implemented first; the large tune-architecture
> phases (5 track-specific base tunes, 7 qualifying engine, 9 historical intelligence,
> 10–14 arbitration/subtypes/sequencing) are staged behind them.

---

## A. Confirmed root causes

### DEFECT — Dominant "bottoming (required)" declared from thin/low-confidence data, untreated, yet approved
The single most serious defect: the plan's dominant *required* problem got no change **and** the
plan was still `approved_with_warnings`.

- **Fabricated "required" from thin data.** `avg_bottoming = sum(bottoming_count)/len(laps)` has
  **no min-lap or confidence guard** (`setup_diagnosis.py:1263`); `_bottoming_band` escalates on
  `avg > 2.0 → "required"` (`:214-229`) on threshold alone. `_derive_dominant_problem`
  (`:297-298`) appends "bottoming" at `issues[0]` = **dominant** reading the **band only** — it
  never consults `bottoming_confidence.confidence` (computed `low`, `:784-789`) or
  `location_evidence_usable` (computed `False`, `:1257`). Result: an internally incoherent
  diagnosis (dominant+required simultaneously low-confidence and location-unusable).
- **No rule can treat it.** The only ride-height *raising* rule is `C8_kerb_rh_rear`
  (`setup_knowledge_base.py:1044-1065`) which needs `compliance_priority` AND the confidence band.
  A3/A4 are *protection* rules for `minor` bottoming and are suppressed once band is `required`.
  The deterministic fallback is dead too: `_rh_permitted_increment` returns 0 when confidence is
  `low` (`:840-841`). So telemetry-only "required" bottoming with no compliance signal matches no
  proposing rule — dominant problem is structurally untreatable in that state.
- **The funnel never checks coherence.** `_finalise_recommendation` (`driving_advisor.py:471-654`)
  sets status purely from validation failures + `fallback_used` + warnings (`:630-641`); it never
  compares `dominant_problem` against the fields in `approved_changes`. So an untreated
  dominant-required plan returns `approved_with_warnings` ∈ APPROVED_STATUSES → shown as applyable.

**Fix (Phase 3):** (a) upstream — demote "required→consider" (or don't make it *dominant*) when
`bottoming_confidence.confidence == low` AND `location_evidence_usable is False`; (b) backstop —
a coherence gate in `_finalise_recommendation` (thread the `diagnosis` dict through the 3 call
sites `:1654/:2134/:2362`) that, when the dominant *required* problem is unaddressed, returns
`EVIDENCE_REQUIRED` (new, NON-approved) or `PARTIAL_RECOMMENDATION` (new, surfaced-but-flagged).
Add both statuses in `_setup_constants.py:47-56`; only `PARTIAL_RECOMMENDATION` joins APPROVED_STATUSES.

### DEFECT — Base tune pins front aero to MAX (race and quali identical, drag/fuel penalty)
`build_baseline_setup` seeds `aero_front = 400` (mid of RSR range 350–450), but the driver-profile
bias table applies `dislikes_floaty_front → aero_front +50` (`setup_baseline.py:117`). The driver's
profile has `dislikes_floaty_front=True`, so baseline `aero_front = 450 = MAX` for **both** race and
quali (quali's +25 clamps at max too). On a long-straight, ×3-fuel circuit, max front wing is a
direct drag/fuel/top-speed penalty. This is also *not track-aware*: the same max-aero base is
produced regardless of circuit. **Fix:** Phase 5 (track-specific base tune) + cap/soften the profile
aero bias so it cannot pin a field to its range extreme without track evidence.

### DEFECT — Qualifying tune is race trim on camber/toe
`_SESSION_BIAS_TABLE["qualifying"]` touches no camber/toe, so quali camber/toe == race
(camber 1.0/1.5, toe 0.00/0.05). A one-lap tune wants more negative camber for peak grip. The base
camber itself (1.0/1.5) is far below the driver's proven Watkins values (2.5/2.1) — the generic base
tune ignores car/driver/track. **Fix:** Phase 7 qualifying engine (camber/toe/aggression deltas) +
Phase 5/9 (track- and history-shaped base camber).

### DEFECT — High fuel use routed entirely out of setup reasoning
The current fuel note (added last sprint) says fuel is "not these setup levers." With
`fuel_multiplier` available in event context (`ai_context_snapshot.py:595`) and a long-straight,
×3-fuel, 1 L/s-refuel circuit, aero drag and gearing **do** affect fuel-per-lap and total race
time. The note is contextually too absolute. **Fix:** Phase 8 — make the fuel note context-aware
(high fuel-multiplier + drag-sensitive track ⇒ recommend an aero/gearing comparison run;
`additional_refuel_time_s = additional_fuel_l` at 1 L/s), never fabricating a saving.

### DEFECT — No historical successful-setup intelligence
There is no retrieval/comparison of actual successful setup **values** (e.g. Watkins LSD 22/8/33,
aero 400/600, ARB 7/7, camber 2.5/2.1). `RuleOutcomeStore` tracks per-rule outcomes, not setup
phenotypes; rule rationales ("driver prefers progressive throttle") are generic, not evidence from
a known-good setup. **Fix:** Phase 9 — scoped historical retrieval + explicit current/historical/
recommended/deviation-reason comparison, as a weighted prior (never overrides validators).

### DEFECT — `aero_front_near_min=True` on a max-aero car  *(agent tracing — section pending)*

### DEFECT — Track model needs re-approval every app open  *(agent tracing — section pending)*

### DEFECT — Strategy Builder pit loss = 0 despite track data  *(agent tracing — section pending)*

---

## B. Phased implementation roadmap
1. **Phase 2** — setup-snapshot integrity (aero-position facts; max-aero can never read near-min; stale/mismatched snapshot blocks with `SETUP_SNAPSHOT_MISMATCH`).
2. **Phase 3** — dominant-problem coherence gate (+ EVIDENCE_REQUIRED / PARTIAL_RECOMMENDATION) + bottoming-from-thin-data demotion.
3. **Phase 4** — every feedback item gets an explicit disposition.
4. **Clean bugs** — track re-approval persistence; Strategy Builder pit-loss wiring.
5. **Phase 11/12** — wheelspin-subtype gating of LSD; rear lock-up disposition.
6. **Phase 5** — track-specific base tune builder (track-model-shaped, evidence-honest).
7. **Phase 7** — qualifying-tune engine (distinct one-lap discipline).
8. **Phase 9** — historical successful-setup intelligence (Watkins prior).
9. **Phase 8** — race-time aero/fuel reasoning.
10. **Phase 10/13/14** — cross-symptom arbitration, controlled test sequencing, candidate comparison.
11. **Phase 15** — additive UI/explanation quality.

Each phase ships behind the existing safety/Apply gates with its own tests; nothing auto-applies.
