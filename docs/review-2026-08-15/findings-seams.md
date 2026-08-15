# Round 2, seam hunt — defects living BETWEEN subsystems

These are the class no single-subsystem reviewer could see by construction.

- **SM1 · P1 · strategy/evidence.py:104 — the strategy path hydrates only COUNTED laps, so
  the refuel lap's frames are never decoded and the refuel rate can NEVER be measured.**
  `_laps_to_hydrate` was written for the tyre-temperature window and asks only for laps that
  are counted and compound-tagged:
  `counted = not (row["excluded"] or row["is_out_lap"] or row["is_pit_lap"])`.
  `build_inputs` then passes that same set as the ONLY hydration for the whole strategy path,
  and `refuel_evidence(laps, ...)` reads the fuel channel off `lap.frames`. **A refuel happens
  in the pit box, which is by definition a lap flagged `is_pit_lap` — the one lap the
  hydration set excludes.** `analysis/refuel.py` exists solely to measure that rate off the
  stream and is structurally guaranteed to receive no frames on the only lap that carries it.
  Verified end to end: 11 stored practice laps, the 7th containing a 20 s fill at 3.0 L/s.
  `_laps_to_hydrate` returned {5,6,8,9,10,11} — the pit lap is id 7 — and
  `refuel_evidence(...)['source']` came back `'declared'`. The same laps hydrated WITHOUT the
  filter give `{'rateLps': 3.0, 'source': 'measured-from-the-fuel-channel', 'stopsMeasured': 1}`.
  Consequence: "Refuel rate — 1.00 L/s — declared" on the Strategy screen forever, and every
  stop costed at 100 s instead of 33 s — **which decides the stop count.**
  **This explains the standing note that the refuel rate is driver-typed: the measurement
  path is structurally starved, not merely unused.** Also explains why G3's validator
  refusal never fires.

- **SM2 · P1 · export/build.py:416 — `strategy.assumptions.refuelRateLps` is OVERWRITTEN with
  the driver's typed figure, contradicting the measured rate the plan in the same payload was
  costed with.** `Plan.as_export` does not emit `refuelRateLps`, so `_strategy_section` fills
  it from `event["refuel_rate_lps"]`. But `build_inputs` gives the model
  `refuel["rateLps"] or event["refuel_rate_lps"]` — the MEASURED rate whenever one exists —
  and every stop was costed at `litres / inputs.refuel_rate_lps`.
  Verified: `inputs.refuel_rate_lps = 3.0`, evidence row "Refuel rate | 3.00 L/s | measured",
  and `payload['strategy']['assumptions']['refuelRateLps'] = 1.0`. The knowledge base reads a
  1-stop plan and re-derives a 100 s stop for a plan that assumed 33 s.
  Note the verifier's aside: the trigger state (a refuel lap carrying `is_pit_lap = 0`) is
  **the state of every lap in the owner's DB**.

- **SM3 · P1 · ui/practice_screen.py:150 — the rack's `counted` set disagrees with the
  export's in TWO ways, so the rack's Best lap can be a lap that never went round.**
  `LapRow.counted` is `not (excluded or is_out_lap or is_pit_lap)`.
  `LapInput.counted` (session.py:117) is the same **plus `or self.incident`**, and the export
  additionally runs `classify_exclusions`, which strikes fuel-implausible laps.
  The rack applies neither: `_rows_for_event` imports `auto_out_laps` specifically so the two
  paths agree about out-laps, then marks `row.incident = True` **and never uses it**, and
  never calls `fuel_implausible_laps`.
  Verified against a stored 10-lap event (lap 9 a 122 s spin with crawl evidence; lap 10 a
  garage-transition boundary burning 0.16 L against a 3.4 L median):
  rack says "Counted 9/10", **Best 92.100 s**; export says `lapsCounted 7`,
  `bestLapMs 94000`, `lapsExcluded [1, 9, 10]`.
  **The driver reads a session best 1.9 s quicker than the export's** — precisely the defect
  EXPORT-CONTRACT §16.3 row 6 was written to kill, still live on the screen he looks at.
  `RackRow._sync` compounds it: `uncounted = not self.row.counted` is False for an incident
  lap so it is neither dimmed nor struck, while its Strike button is hidden because
  `structural_reason()` returns "incident".
  controller.py:1350-1356's own comment states the requirement: "It must reach the same answer
  as the export or a lap would read as counted on the screen and be excluded in the payload."

- **SM4 · P2 · prompts/build.py:971 — the outcome prompt prints the tyre window as a MEASURED
  finding while the payload in the same document says it was never measured.**
  `analysis/tyre_window.py` retracted the verdict: `qualification()` returns None
  unconditionally, `inWindow` is None, and every window carries `windowMeasured: false` with a
  `windowSource` reading "NOT MEASURED IN GT7 … the band is not a finding."
  `_strategy_section` reads `windowC`, `band`, `lapsInWindow`, `lapsSampled` off that object,
  renders them as a completed comparison, and **drops `windowMeasured` and `windowSource`
  entirely.** Verified: prompt line "…ran at 72.0 C against a 80-105 C window
  [warming, 0/6 laps in it]" over a payload reading `"windowMeasured": false, "inWindow": null`.
  The reader concludes the compound never reached its window — **the exact false finding the
  module was rewritten to stop emitting.**
  (Corroborates the standing note that the tyre windows in `store/tyres.py` were fabricated and
  were exporting a false finding every time — the retraction was applied to the analysis layer
  and the prompt layer still prints it.)

- **SM5 · P2 · race/coordinator.py:125 — ANY pit exit resets the live tyre model, so a
  fuel-only stop silences the tyre warning for a whole further stint.**
  `handle` treats every PIT_EXIT as a tyre change: calls `clear_stint(state)` which sets
  `laps_since_stop = 0`, and **discards the `tyres_changed` flag the event carries.** The live
  call is `consumed = state.laps_since_stop * state.wear_per_lap`, so modelled consumption
  drops to zero at a stop that changed no rubber.
  `analysis/runs.py:131-140` forbids exactly this inference in the offline layer: "**Never
  inferred from the refuel.** GT7 lets you take fuel without taking tyres, and inferring True
  from a stop would turn every fuel stop into a fresh set and halve every wear rate spanning
  one." **The two layers disagree about what a stop means.**
  On a set 60% consumed at the stop, the "tyres are at the end of their window" call (fires at
  85% modelled) cannot fire again until another full stint's laps have run — so it never fires
  at all in the race, and the driver reads silence as "nothing to report", which is what
  `_status` promises.

- **SM6 · P2 · export/build.py:435 — every engineer call is written `accepted=False` and the
  export reads that as "the driver declined it".**
  `controller._on_race_event` records each call with `append_revision(..., accepted=False)`,
  using False to mean "there was nothing to accept". Only `_resolve_replan` ever writes a
  meaningful value. `_outcome` counts `call.get("accepted") is False` as a decline and passes
  it to `race_outcome(declined_calls=…)`.
  Verified: a 6-lap race with three calls exported
  `"6 laps run. No stops. … 3 calls offered and not taken. …"` with `accepted: False` on all
  three. **A race in which the driver obeyed every call exports a sentence saying he obeyed
  none** — evidence about the model that never happened.
  `db.list_revisions` coerces with `bool(item["accepted"])` so the `is False` test matches;
  no path ever updates a call row.
