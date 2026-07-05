# Setup Brain — Manual UAT Checklist

> **Scope:** Rule-First Setup Brain (Group 42), the Setup Builder Engineering
> Validation Gate (Group 41), and the underlying setup-diagnosis brain
> (Groups 38–40).
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

## Notes / known limitations

- Gearbox ratio ranges (`final_drive` 2.5–6.0, gears 0.5–4.0) are conservative
  invented constants, not per-car data — so `gearbox_out_of_range` is a WARNING,
  not a hard block. A legitimate but out-of-band ratio will warn, not block.
- Running the full automated suite in one process on Windows / Python 3.14 can
  hit a flaky native PyQt teardown segfault; this does not affect the app at
  runtime.
- **Group 42 deferrals:** the rule-engine learning loop (`RuleOutcomeStore`) is a
  foundation only — it is not wired live and does not persist across sessions
  yet, so recommendations will not yet self-tune from outcomes. The handling-phase
  rule pack (C/D) is a starter set — the remaining per-setting Pack C rules are
  deferred. The voice path is narration-only pending a full rule-first rebuild.
- Full technical detail: `docs/RULE_FIRST_SETUP_BRAIN.md` (architecture),
  `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 42 and § Group 41),
  `MASTER_TESTING_REGISTER.md` (Rule-First Setup Brain (Group 42)).
