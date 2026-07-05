# Setup Brain — Manual UAT Checklist

> **Scope:** Setup Builder Engineering Validation Gate (Group 41) and the
> underlying setup-diagnosis brain (Groups 38–40).
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

## Notes / known limitations

- Gearbox ratio ranges (`final_drive` 2.5–6.0, gears 0.5–4.0) are conservative
  invented constants, not per-car data — so `gearbox_out_of_range` is a WARNING,
  not a hard block. A legitimate but out-of-band ratio will warn, not block.
- Running the full automated suite in one process on Windows / Python 3.14 can
  hit a flaky native PyQt teardown segfault; this does not affect the app at
  runtime.
- Full technical detail: `docs/SETUP_BRAIN_UPGRADE.md` (§ Group 41),
  `MASTER_TESTING_REGISTER.md` (Setup Builder Engineering Validation Gate).
