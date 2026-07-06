# Setup Brain — Manual UAT Checklist

> **Scope:** Setup Brain Learning & Race Context (Group 46), Setup Brain
> Intelligence Expansion (Group 45), Rule-First Setup Brain (Group 42), the Setup
> Builder Engineering Validation Gate (Group 41), and the underlying
> setup-diagnosis brain (Groups 38–40).
> **Branch:** `ofr2-quali-race-disciplines`
> **Test car / track:** Porsche 911 RSR '17 at Fuji International Speedway
> **Environment:** GT7 on PS5, dashboard on PC via UDP, `GT7_AI_DEBUG=1` set in
> the shell so every AI prompt/response prints to the console and the AI Log.
> **Tester:** Leon Paczynski

---

## How to enable AI debug logging

```
set GT7_AI_DEBUG=1
python main.py
```

Every AI prompt and response prints to the console and appears in the AI Log.
Watch the AI Log to confirm the validation gate and the lifecycle status.

---

## Validation Gate checklist (Porsche 911 RSR '17 at Fuji)

Run these in order after a stint with real telemetry.

1. **Generate** a setup recommendation from current telemetry.
2. **Unsafe blocked.** Confirm unsafe AI recommendations are blocked — no
   actionable changes shown.
3. **Rejected hidden.** Confirm rejected recommendations are NOT shown under
   "CHANGES TO MAKE" and the Apply button is hidden (not merely disabled).
4. **Safe fallback.** Confirm a safe fallback appears if the AI retry fails —
   or a clear "no safe recommendation — run more laps" message.
5. **No fake gearbox field.** Confirm no `transmission_max_speed_kmh` change
   appears as an actionable setup change.
6. **Real gearbox advice.** Confirm a gearbox issue appears as either real
   gear-ratio / final-drive changes or manual gearbox advice — never a fake
   top-speed target change.
7. **LSD accel gate.** Confirm LSD accel changes are limited for
   `snap_throttle_induced` wheelspin (max +4).
8. **Ride-height / rake gate.** Confirm rear ride-height changes are limited for
   `kerb_strike` bottoming and rear-only rake risk is blocked.
9. **Safe, small, actionable.** Confirm the final displayed recommendation is
   safe, small (1–3 changes), and actionable.
10. **Apply approved only.** Apply only the approved changes.
11. **Validation laps.** Run validation laps.
12. **No resurrected rejects.** Confirm the next recommendation compares
    before/after and does not resurrect previously-rejected changes.
13. **UI real-estate (Amendments B & C).** Confirm the Setup Builder tab no
    longer shows the "Race Conditions (from Event Planner)" block and has more
    room for the setup view; confirm Damage now appears on the Home Race Setup
    card.

---

## Rule-First Setup Brain UAT (Group 42)

> **What changed:** the Setup Brain is now RULE-FIRST. The deterministic rule
> engine authors the setup changes; the AI is an AUDIT-ONLY layer that can
> approve / warn / reject / request-more-data but **cannot author actionable
> setup changes**. Confirm below that the deterministic engine drives the
> recommendation and the AI can only comment on it.
>
> Debug: keep `GT7_AI_DEBUG=1` set (see "How to enable AI debug logging" above).
> The AI Log now shows the audit prompt (8 labelled sections) and the audit
> response — NOT a setup-authoring prompt.

### Primary scenario — Porsche 911 RSR '17 at Fuji Full Course

Set-up: driver reports **rear loose on throttle**, **snap wheelspin**,
**mid-corner push**, and that they **hate a floaty front**; telemetry shows
**snap-throttle wheelspin / traction loss**. Run a stint, enter that driver
feedback, then **Analyse** in the Setup Builder.

1. **No generic ride-height raise.** Confirm the app does **NOT** recommend a
   generic ride-height raise as a fix for the traction complaint.
2. **Downforce not cut first.** Confirm the app does **NOT** reduce downforce as
   the first fix if traction (not drag) is the true top-speed limiter — the
   deterministic engine should protect downforce for a driver who protects it.
3. **Driver-aligned mechanical traction / LSD.** Confirm the recommendation is
   safe, small (1–3 changes), and consists of driver-aligned **mechanical
   traction** and/or **LSD** changes (e.g. LSD accel within the safe gate,
   rear-ARB / rear-aero within the handling-phase rules) — not a floaty-front
   change the driver dislikes.
4. **"Pit Crew recommendation" vs "AI audit" labelling.** Confirm the approved
   changes appear under **"Pit Crew recommendation"** (the deterministic plan),
   and the AI's verdict appears separately under **"AI audit"**. The AI audit may
   warn or approve, but it must **never add or change** an actionable setup
   field. If the AI rejects, the recommendation is surfaced as an
   `approved_with_warnings` advisory (unless a blocking engineering failure
   applies — which always wins), and any AI-authored setup keys are stripped.
5. **"Why Pit Crew recommended this" explainability.** Expand a change's
   collapsed **"Why Pit Crew recommended this"** block and confirm it shows
   symptom, rationale, evidence, rejected_alternatives, risk_level,
   confidence_level, and driver_style_alignment.
6. **Protected + rejected sections.** Confirm **"Protected fields (Pit Crew will
   not change these)"** lists the safety-protected fields and **"Rejected
   candidate changes (not applied)"** lists candidate changes the engine
   rejected (e.g. conflicting or contraindicated ones).
7. **Apply is deterministic-only.** Confirm the Apply button reads **"Apply Pit
   Crew recommendation"** and, when clicked, applies only the deterministic
   approved changes — never an AI-authored field.

### legacy_unknown — an old cached recommendation is display-only

8. **No status → display only.** Load an old cached recommendation that predates
   the lifecycle status (absent / unknown status). Confirm it shows the banner
   **"Legacy recommendation — display only, cannot apply"** and that the Apply
   button is **hidden** — the old default-to-approved behaviour is gone.

### Voice path is narration-only

9. **Voice cannot surface actionable changes.** Trigger a setup query via the
   voice path (`build_setup_advice_response`). Confirm the spoken/narrated
   response describes the situation but does **NOT** surface actionable
   setup-field changes to apply — the voice path is constrained to
   narration-only.

---

## Setup Brain Intelligence Expansion UAT (Group 45)

> **What changed:** the rule-first engine is now **context-aware** — session
> type, tyre-wear, drivetrain, and car-class shape *which* rules fire and *how
> confident / ranked* they are, without changing any delta magnitude. Every
> approved and rejected change now carries honest explainability fields
> (`source_label`, `session_influence`, `car_drivetrain_influence`, `pack`). The
> Porsche 911 RSR '17 gets its own rule pack (Pack P). Full detail:
> `docs/RULE_FIRST_SETUP_BRAIN.md` § 14.
>
> Debug: keep `GT7_AI_DEBUG=1` set. Nothing here requires the AI — everything
> works with the AI disabled; the AI (if enabled) is still audit-only.

### Session-aware recommendations (Porsche 911 RSR '17 at Fuji)

Run the **same** stint/feedback twice, changing only the Event Planner session
purpose.

1. **Quali vs Race differ.** Analyse once with the session set to **Qualifying**
   and once to **Race**. Confirm the recommendations differ in **which changes
   are surfaced / their ordering / their confidence** — quali should favour
   front-bite / trail-braker-tagged changes, race should favour
   safety-phase / consistency changes. **The delta magnitudes should NOT change**
   (this is deliberate — context shifts confidence/ranking, not the numbers).
2. **Endurance.** Confirm a Race session with a duration **>= 60 min** is treated
   as endurance (race behaviour + the endurance flag).
3. **`session_influence` is honest.** Expand a change and confirm `session_influence`
   describes how the session affected it — or, if session context was missing,
   reads the explicit neutral / "not session-tuned" string rather than claiming a
   session tune.

### Tyre-wear-aware recommendations

4. **High tyre-wear suppresses tyre-abusing rules.** Set a high tyre-wear
   multiplier (`>= 5.0`) in the Event Planner and Analyse. Confirm the four
   tyre-abusing rules are **suppressed** — no lsd_accel *decrease* (B3), no
   lsd_decel *decrease* (C1), no rear-ARB *soften* (C3 / C7).
5. **Stabilising rules survive.** Confirm rules that **increase** lsd lock or rear
   downforce are **NOT** suppressed at high wear (they stabilise worn tyres).
6. **Missing tyre/fuel context is honest.** With no tyre/fuel context available,
   confirm the change reads "tyre/fuel context not available — conservative
   default applied" and makes no tyre/fuel-aware claim. (Fuel is read but only
   informational — there is no fuel-specific change yet.)

### Car / drivetrain-aware recommendations + the Porsche pack

7. **Porsche pack fires.** On the RSR (RR, Gr.3), confirm a snap-throttle
   wheelspin complaint yields the cautious traction-first **lsd_accel increase**
   (Pack P / rule P1), labelled `source_label` **"Porsche-specific rule"**, and
   that it is **contraindicated** (not proposed) when `snap_oversteer_exit` is
   diagnosed.
8. **No generic ride-height raise / no downforce cut first.** Confirm (as in the
   Group 42 primary scenario) there is still no generic ride-height raise and no
   downforce cut as the first fix — A2/A3/A4 still cover these unconditionally
   (Pack P deliberately has no P2).
9. **`car_drivetrain_influence` is honest.** Expand a change and confirm
   `car_drivetrain_influence` describes the car-class / drivetrain effect — or, if
   the drivetrain is unknown, reads "drivetrain unknown — generic logic applied".
   The RSR's RR drivetrain comes from the override map / the manual combo, not the
   (empty) DB column.

### Gearbox

10. **B5b lengthens gearing.** Confirm a `gear_too_long` diagnosis proposes a
    `final_drive` **up** change (B5b); a `gear_too_short` still proposes
    `final_drive` **down** (B5); `limiter_limited` proposes **no** gearbox change.
11. **Equal ratios allowed.** Confirm a setup with two equal adjacent gear ratios
    is **NOT** rejected as an inversion (monotonic ordering is now non-increasing;
    only a strict inversion is rejected).

### Explainability + learning

12. **Source label row.** Confirm each change shows a small `source_label` row
    ("Porsche-specific rule" / "generic rule"; baseline changes show
    neutral / biased / midpoint / conservative labels and never claim telemetry
    evidence).
13. **Learning is inert but present.** Confirm the response carries a learning
    note "no cross-session learning history available" — the learning seam is
    wired but empty, so recommendations do **not** yet self-tune from outcomes.
    Learning can never un-block a safety rule, un-reject a change, or make the AI
    actionable.

---

## Setup Brain Learning & Race Context UAT (Group 46)

> **What changed:** the rule-first engine now **learns across sessions** (a real
> SQLite `learning_outcomes` feed), and its **Analyse** recommendations are shaped
> by **fuel load** and by **fuller per-gear telemetry**; the from-scratch
> **Baseline** is now **numerically biased by session type**; the Porsche pack
> inherits the new confidence layers. Full detail:
> `docs/RULE_FIRST_SETUP_BRAIN.md` § 15.
>
> Debug: keep `GT7_AI_DEBUG=1` set. Nothing here requires the AI — everything works
> with the AI disabled; the AI (if enabled) is still audit-only. Learning shows up
> **only after repeated matching sessions** have been scored.

### Cross-session learning (Porsche 911 RSR '17 at Fuji)

1. **Learning is silent until there is history.** On a fresh DB (or a new
   car+track+layout), Analyse and confirm the recommendation carries **no**
   learning-influence claim — a rule with no history makes no learning statement.
2. **Learning influence appears only for repeated matching contexts.** Drive and
   score the **same** car+track+layout across **at least 3 sessions** so outcomes
   accumulate, then Analyse again. Confirm a `learning_influence` note appears
   **only** on a rule whose confidence actually stepped — a rule that had history
   but stayed between the thresholds shows **no** learning claim (honesty).
3. **Upgrade vs downgrade.** Confirm a rule with a **good** track record
   (success_rate `>= 0.60` over `>= 3` samples) reads as an **upgraded** confidence
   step, and a rule going **badly** (`< 0.40`) reads as a **downgraded** step — one
   step either way, never more.
4. **Learning cannot break safety.** Confirm learning never un-blocks a blocked
   safety rule, never un-rejects a rejected change, and never makes the AI author a
   change — it only shifts a confidence label / ranking.
5. **No user-file churn.** Confirm `data/setup_history.json` is **not** touched by
   learning (learning lives only in the gitignored session DB). *(Observable: the
   file's mtime/contents do not change when a scored session records outcomes.)*

### Fuel-aware recommendations (Analyse)

6. **High fuel prioritises traction / stability.** Set a high fuel multiplier
   (`>= 5.0`) in the Event Planner and Analyse a traction complaint. Confirm the
   traction / stability changes (lsd_accel, arb_rear, aero_rear, etc.) are ranked /
   confidence-boosted, and that the change's evidence line mentions the fuel
   effect. **The delta magnitudes must NOT change** — fuel affects
   ranking/confidence only.
7. **Fuel honesty.** With fuel = 1.0 or no fuel context, confirm there is **no**
   fuel claim on any change (no false "high fuel" statement).

### Session-biased baseline (Build Baseline Setup)

8. **Session-specific baselines differ numerically.** Build a baseline for the
   same car three times, changing only the session: **Qualifying**, a short
   **Sprint** race, and an **Endurance** race (duration `>= 60 min`). Confirm the
   resulting baseline **values differ numerically** between sessions (this is the
   Group 46 change — Group 45's baseline only *noted* the session).
9. **Baseline session honesty.** Confirm a field the session bias **did not** move
   reads "session noted — no numerical change for this field", and an **unknown**
   session makes no session claim. No false "session bias applied".

### Per-gear intelligence

10. **Per-gear only on real evidence.** Confirm an individual `gear_N` change is
    proposed **only** when there is real indexed evidence for gear N (rev-limiter
    in that gear on a `gear_too_short` diagnosis, or detected per-gear wheelspin).
    A change carries the `source_label` **"per-gear rule"**.
11. **"Top speed low" alone changes nothing.** Confirm a top-speed-low symptom with
    **no** indexed per-gear evidence yields **no** gear change — and the
    per-gear explanation says why. `final_drive` (B5/B5b) remains the broad lever.

### Porsche benchmark (AC37)

12. **RSR / Fuji integrated check.** On the RSR at Fuji with high tyre + high fuel
    and the *rear-loose + mid-push + floaty-front* / snap-throttle-wheelspin +
    top-speed-low scenario, confirm the recommendation is **traction-first**
    (before/instead of an aero cut), with **no** rear-downforce reduction, **no**
    rearward brake bias, **no** generic ride-height raise without bottoming
    confidence, and **no** top-speed gear-lengthening as the primary wheelspin fix
    — and it applies cleanly through the Apply gate.

---

## Notes / known limitations

- Gearbox ratio ranges (`final_drive` 2.5–6.0, gears 0.5–4.0) are conservative
  invented constants, not per-car data — so `gearbox_out_of_range` is a WARNING,
  not a hard block. A legitimate but out-of-band ratio will warn, not block.
- Running the full automated suite in one process on Windows / Python 3.14 can
  hit a flaky native PyQt teardown segfault; this does not affect the app at
  runtime.
- **Group 42 deferrals:** the handling-phase rule pack (C/D) is a starter set —
  the remaining per-setting Pack C rules are deferred. The voice path is
  narration-only pending a full rule-first rebuild.
- **Group 45 deferrals (now partly superseded by Group 46):** what Group 45 left
  open — the empty learning seam, informational-only fuel, and session context
  merely *recorded* on the baseline — was **delivered in Group 46** (see below).
  Still standing from Group 45: on a driver profile that carries **both**
  `race_values_consistency` and `rotation_without_snap`, the two opposing baseline
  lsd_decel biases (+2 / −2) net to zero.
- **Group 46 deferrals:** the **Baseline path does NOT consume rule-confidence
  learning** (it does not run the rule engine — learning shapes the **Analyse**
  path only). `source_path="Baseline"` is schema-supported but **not yet written**
  (only `"Analyse"` is recorded in production today). `learning_outcomes.session_type`
  is stored as `""` (scope is car_id + track + layout_id; a JOIN/column is
  deferred). **`bog_by_gear` and `lockups_by_gear` are honestly `None`** — GT7's
  10 Hz telemetry has no reliable signal for them, so per-gear evidence today is
  limiter + wheelspin only. Fuel affects confidence/ranking only — there is no
  fuel-specific *delta* rule.
- Full technical detail: `docs/RULE_FIRST_SETUP_BRAIN.md` (architecture, incl.
  § 14 "Setup Brain Intelligence Expansion" and § 15 "Setup Brain Learning & Race
  Context"), `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 46, § Group 45, § Group 42 and
  § Group 41), `MASTER_TESTING_REGISTER.md` (Setup Brain Learning & Race Context
  (Group 46), Setup Brain Intelligence Expansion (Group 45), Rule-First Setup Brain
  (Group 42)).
