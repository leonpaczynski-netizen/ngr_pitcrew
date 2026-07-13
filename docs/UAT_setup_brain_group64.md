# Group 64 — Manual UAT Guide (Setup Brain discipline authoring & completeness)

Car: **Porsche 911 RSR (991) '17**. Event: an NGR Porsche Cup race round with a real
fuel multiplier and refuel cost. Two profiles: **(A) populated proven history** (a liked
same-car setup exists) and **(B) fresh profile** (no history).

Automated proof of every step below lives in `tests/test_group64_setup_authoring.py`
and `tests/test_group64_uat_integration.py`.

## 1. Base setup (populated history)
1. Garage → select the RSR. Event Planner → the race round. Setup Builder → **Build Baseline**.
2. **Expect:** the response's `discipline_field_plan` shows Base / Qualifying / Race columns
   that **differ** across several fields (camber, toe, brake bias, LSD, aero, ride height).
3. **Expect:** `seeded_from_history` lists the proven LSD triplet (and camber) — proven
   values reached authoring, not just the comparison table. Each seeded field's disposition
   is `PROVEN_HISTORY_SEED`.
4. **Expect:** every adjustable field carries a disposition; front-diff fields on the RR car
   read `NOT_RELEVANT`; event-locked fields read `EVENT_CONSTRAINT`.

## 2. Qualifying setup
1. Build the Qualifying baseline.
2. **Expect:** more front camber, more front toe-out, brake bias forward, freer LSD decel,
   lower ride height than Race — the one-lap trim. The qualifying brief states the one-lap
   objective and the "do not race it" warning.

## 3. Race setup
1. Build the Race baseline.
2. **Expect:** more conservative than Qualifying (more accel-side lock, more rear aero,
   platform margin) — engineered for repeatable pace over the stint, NOT one lap.
3. **Expect:** the Race plan issues **no pit strategy** (that stays with the Strategy Brain).

## 4. Post-practice feedback (the failed-UAT scenario)
Enter feedback: *Corner Entry: understeer / Mid-Corner: pushes wide / Exit: rear loose on
throttle / Rear under braking: steps out / Notes: LSD floaty, not hooking up on apex; sixth
not fully used.* Run **Analyse**.
1. **Expect (RC3):** bottoming shows **one** state — the header and the impact panel agree
   (no "required" + "normal" contradiction). Count-only bottoming with no measured effect is
   `advisory`/`unconfirmed`, never `required`.
2. **Expect (RC4):** wheelspin is **not** `gear_too_short_spin` when location/per-gear
   evidence is weak — it defers to a controlled test.
3. **Expect (RC5):** the result is **not** "approved (complete)". Because confirmed problems
   remain untreated it is a **Partial recommendation** (or the stronger **evidence required**),
   with the untreated problems listed and targeted tests attached. It is never a lone ARB
   change presented as a finished setup.
4. **Expect:** every feedback item receives an explicit disposition; the LSD triplet is
   evaluated with proven values shown; the final drive is never lengthened for an unused sixth.

## 5. Fresh profile (B)
Repeat 1–4 with no saved setups.
1. **Expect:** `seeded_from_history` is empty; no proven value is invented; dispositions fall
   back honestly to driver-profile / authored / insufficient-evidence. Disciplines still
   differ (session bias), and the completeness verdict is still honest.

## 6. App restart & history reload
1. Save and like a Race setup, close the app, reopen.
2. **Expect:** the liked setup reloads (from the DB / config) and again seeds the LSD triplet
   into the next Base authoring (`seeded_from_history` non-empty).

## 7. Strategy Brain handoff
1. Open the Strategy tab for the same event.
2. **Expect:** the Strategy Brain still owns tyre-life/crossover, fuel, pit timing, compound
   choice and total-race-time ranking. The Setup Brain provides the setup + practice evidence;
   it issues no pit command. No authority leaks either way.
