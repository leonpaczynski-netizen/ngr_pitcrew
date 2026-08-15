# Adjudicated verdicts, part 2

## Verifier 3 — strategy (S) + telemetry (T)

CONFIRMED: S1 P1, S2 P1 (**raise to #1**), S3 P1, S4 P1, S6 P2, S7 P2, S8 P2, S9 P2,
T2 P2, T3 P2, T4 P3
DOWNGRADED: S5 P1→P2, T1 P1→P2, T5 →P3 (driver-facing claim false)

- **S2 — CONFIRMED, verifier asks to make it the #1 item.** Reproduced
  "You can push. 3.9 laps of fuel in hand." at HIGH confidence **with 0.88 laps of fuel
  on board.** `laps_to_stop()` has no floor.
- **S1 CONFIRMED.** Reproduced "Fuel to 71 litres" for a stint needing 37.4 L.
- **S3 CONFIRMED end to end.** `schema.py:59-61` has BOTH `race_laps` and `race_minutes`,
  but **`race_minutes` is never written** — `event_screen.py:1071` saves the MINUTES spin
  box into `race_laps`. `evidence.py:508` compensates on the strategy side;
  `controller.py:1529-1531` does not. A 45-min Monza produced "P3. 40 to go",
  "Fuel to full. Still 17.8 laps short", "You're 16.8 laps short on fuel".
  *Correction:* "no test covers a timed race" was OVERSTATED — `test_timed_race.py` covers
  the strategy model well. But `race_type` is `"laps"` in all five test files that mention
  it, so the live RACE path is genuinely uncovered.
- **S4 CONFIRMED by controlled A/B.** `evidence.py:186-195` produces this profile from real
  evidence and its comment names the case. Two identical profiles, one with
  `wear_per_lap=None`, cost **4.9 s apart** (RH/RH 3159.12 s vs RM/RM 3154.21 s); the
  unmeasured one ranks first. Both knock-ons confirmed.
- **S5 DOWNGRADED→P2.** Real and reproduced, but an omission not a wrong number, and the
  box calls still fire.
- **T1 DOWNGRADED→P2.** Mechanism reproduced exactly; `_check_lap`'s guard does NOT prevent
  it, only delays the lap until the flags are already latched. **But three claimed harms do
  not stand:** `runs.py:300` says a garage return SHOULD be a run boundary;
  `tyres_changed=True` is factually correct there; refuel-rate measurement is safe
  (`m0.py` uses the guarded offline twin, `refuel.py` bounds at 25 L/s). Race-coordinator
  claim near-unreachable (a mid-race garage return is a retirement). What genuinely breaks:
  **`fuelAddedL` exported as a stop's measured fill for something that was not a stop.**
  *Cross-check answered:* NOT the same bug as the 132-lap `is_pit_lap=0` note — the
  OPPOSITE failure mode of the same detector. That was the old 0.05 L/frame gate (false
  negatives); the window fix removed it and opened this false positive.
- **T3 CONFIRMED.** Reproduced WSAECONNRESET 10054 here — `ConnectionResetError`, NOT a
  `socket.timeout`.
- **T5 DOWNGRADED→P3.** Bug real, driver-facing claim FALSE — nothing in the UI ever passes
  a non-default `listen_s`.
- **T2 CONFIRMED.** Reproduced 1600.8 m recorded for 100.8 m driven; `t_ms` 32000 for 2017 ms.
- **T4 CONFIRMED P3** by AST.

### Fix corrections — proposed fixes that would break something else
- **S1:** "read `stints[i]['fuel_l']`" is WRONG. That is the PLANNED burn; adopting it
  discards the race-measured rate installed at `coordinator.py:170`, which exists for a
  documented reason (`test_fuel_calls_switch_to_the_races_own_burn_rate`). Carry the next
  stint's LAP COUNT into `RaceState` and keep multiplying by `state.fuel_per_lap_l`.
  **Three tests ENCODE this bug** — `test_the_shortfall_is_the_call_when_the_clamp_binds`
  spells the fill-to-the-flag arithmetic out in a comment and asserts it. Written for the
  tank-clamp defect, target carried forward unexamined.
- **S2:** flooring at 0 is NOT enough — with target 0 the gap is the whole tank and
  FUEL_LONG still fires. Past the box lap, fall back to `laps_remaining()`.
- **S7:** "refuse like `crossover_lap`" OVER-refuses; a single-compound plan on the
  reference has a genuinely correct 0.0. Return None only when no constituent profile has
  `pace_known`.
- **S8:** the string came from EXPORT-CONTRACT.md's own example payload (line 662) — a fix
  must keep a vocabulary the consuming tool accepts. **The contract may need the
  alternative token added.**
- **T2:** updating `_last_packet_id` on the drop path fixes `lap_distance_m` but NOT `t_ms`
  (computed from `_lap_start_packet`). Needs a separate dropped-span offset.

### NEW defect
- **N5 · P2 · session_state.py:288-305 — the fuel window survives a paused/loading gap, so a
  stop fires with the car ON TRACK throughout.** `update()` returns early on paused/loading
  BEFORE appending to `_fuel_window` (221-223), and `_refuelling`'s trim loop keeps a
  minimum of two entries, so one pre-gap reading always survives. Reproduced
  `PIT_ENTRY {'fuel': 40.0}` on the first packet after a paused race restart with
  `car_on_track` True throughout.
  **Matters for T1's fix: a `car_on_track` guard on `_update_pit` does NOT close this.**
  The window must be invalidated on any stream discontinuity — paused, loading, or a
  packet-id jump.

---

## Round 2, gap sweep C — measurement core (previously ZERO findings)

- **G12 · P1 · analysis/session.py:235 — the race plan's reference lap is the fastest of the
  three OLDEST counted laps, unweighted, while the export DECLARES it recency-weighted.**
  `green_lap_reference_ms` = `min(lap_time_ms)` over `counted_laps(laps)[:3]` — for an
  event-scoped list (ordered `sessions.started_at, sessions.id, laps.lap_num`) always the
  opening counted laps of the OLDEST session. `evidence.py:452` feeds it into
  `RaceInputs(lap_time_ms=...)` and into `laps_from_minutes(race_minutes, reference_ms)` —
  the plan's reference pace and, for a timed race, **the divisor that fixes the race
  distance.** Immediately above, `fuel_per_lap` IS run through `recency.weighted(...)`, and
  `Weighting.as_export()` emits `"appliesTo": ["referenceLapMs","fuelPerLapL"]` — a claim
  the pace figure is weighted, which it is not. Grep: `referenceLapMs` occurs nowhere else.
  `min` of three rather than a median is also systematically optimistic. recency.py's own
  example: pooled Monza median 109.43 s vs latest session 109.06 s — this reference is the
  fastest of three laps older still. **Interacts with S3/S6.**
- **G13 · P2 · analysis/corners.py:89 — the bottoming reference is the observed MINIMUM of
  the same frames the flag is tested against, so the deepest corner flags `bottoming` BY
  CONSTRUCTION.** `export/build.py:340-341` passes the SAME `counted_with_frames` to both.
  The frame producing the minimum satisfies `height == reference`; its neighbour is in the
  3 mm band too (3 mm in one 16.7 ms frame is 180 mm/s, an impact). CLAUDE.md §3.3 fact 3
  specifies TWO quantities — a steady-state reference and excursions toward the observed
  minimum — collapsed into one. The tune builder stiffens springs against a measurement
  never made.
- **G14 · P2 · analysis/corners.py:331 — `wheelspin` is raised from max slip across ALL FOUR
  wheels; the contract defines it on DRIVEN wheels only** (EXPORT-CONTRACT §7.1). GT7 sends
  no drivetrain channel so the contract is not implementable as written, **but the
  substitution is silent** — `thresholds.as_export()` emits `"wheelspinPct": 8` with no
  statement that the detector is all-wheel. `lockup` two lines later uses `min(slips)`,
  which DOES match its wording, so the two are mutually inconsistent. Trigger: a RWD/MR
  Gr.3 car (the league's cars) putting a front wheel light over a kerb on throttle.
- **G15 · P3 · analysis/corner_model.py:203 — the prominence test scans to the ENDS OF THE
  LAP instead of the neighbouring apexes.** `_rises_to` is unbounded, so every minimum is
  satisfied by the main straight. Near no-op; docstring states the opposite intent.
  `test_a_shallow_lift_is_not_a_corner` passes only because its synthetic lap has one
  constant straight speed. Contrast `_corner_bounds` (225-228), which DOES bound its search.
  Consequence: one corner becomes T4 and T5 and every corner after it is renumbered.
- **G16 · P3 · analysis/corners.py:420 — `_bottomed` requires 2 frames where the contract
  requires >50 ms**, because `int(50/16.67)` truncates 2.999→2, giving 16.7 ms. The other
  two windowed detectors truncate in the SAFE direction (`_countersteered` ≈283 ms vs
  "within 300 ms"; `_kerb_struck` ≈83 ms vs "<100 ms"). Compounds G13.
- **G17 · P3 · analysis/reaggregate.py:121 — a lap that is both out-lap and pit lap produces
  TWO findings, and applying them in order writes `is_out_lap = 0` over the first.**
  `LapFinding.changes` always emits BOTH columns; `tools/reaggregate.py:60-61` applies in
  list order. Contradicts the module's own docstring.
