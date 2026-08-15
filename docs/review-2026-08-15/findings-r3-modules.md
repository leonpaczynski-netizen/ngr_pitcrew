# Round 3, F5 — the 19 previously unswept modules

All 19 read in full with callers traced. **This is trustworthy silence: each clean module is
listed with what was actually checked.**

## Findings
- **P1 · incidents.py:198 — spin detection reads the roll-rate channel.** FOURTH independent
  confirmation of the yaw defect, by yet another route. Axis proof from the DB: over one lap
  `pos_x` spans 1256.3 m and `pos_z` spans 2164.6 m while `pos_y` spans 12.8 m ⇒ Y is vertical
  ⇒ yaw is `angvel_y`. Correlation of stored `yaw_rate` against actual heading-change rate over
  laps 1-4: **0.027, 0.029, 0.012, 0.021**; sd(angvel_z) 0.071 vs sd(heading rate) 0.614 rad/s.
  Across all 132 laps `spin_s` reaches the 0.08 s minimum on **exactly one** lap, and that lap is
  already caught by CRAWL. **Every incident the detector actually reports is signalled by `crawl`
  or `off-track` — never by `spin`.**
  **Fix note the other agents missed:** the on-disk format is append-only, so add a NEW
  `yaw_rate_y` field to `FRAME_FIELDS` rather than reusing the slot, or stored laps stop decoding.
  Also re-check `SPIN_YAW_RAD_S = 1.2` against a real yaw channel — smoothed heading rate peaks at
  ~0.86 rad/s on a clean lap, so 1.2 is plausible but unverified.

- **P2 · incidents.py:190 — `off_track_s` is 0.0 rather than null when the surface channel is
  unavailable (packet A/B).** `wheels_off` is 0 on every frame when `surf_*` is null, so
  `off_track_s` computes as 0.0 and is stored and exported as a measurement.
  `evidence_of` cannot rescue it — its null test is `all(value is None ...)` and
  `crawl_s`/`spin_s` are always non-null.
  Trigger: `listener.py:229-240` switches to `HEARTBEAT_A` after `FORMAT_PATIENCE_S` of no decode
  under `C`. Every lap of that session then gets 0.0. Breaks CLAUDE.md §3.1's explicit purpose for
  `meta.packet` — absent channels must read as *not available*, not *not measured*.

- **P2 · race/outcome.py:46 — a correctly executed multi-stop plan is reported as a DEVIATION.**
  `race_outcome` compares `planned_pit_laps[:len(stops)] != stops`, but its only production caller
  passes at most ONE lap (`[plan["pitLap"]]`), and `Plan.as_export` writes only
  `self.pit_laps[0]`. So any 2+-stop plan driven exactly to plan trips the elif.
  Verified: a two-stop race planned for laps 15 and 30, driven exactly, exports
  *"45 laps run. Stopped lap 15, lap 30. Stopped on lap 15, lap 30 against a planned lap 15."*
  The tune builder reads that as evidence the plan was not followed — corrupting the §5.5 audit.

- **P2 · session_state.py:303 — the live refuel gate accepts an INSTANTANEOUS garage tank reset;
  the offline twin correctly does not.** **This answers the pit_detect twin question.**
  `_refuelling` has a floor (0.30 L over 2 s below 120 km/h) but **no ceiling and no rate check**,
  so a one-frame tank reset satisfies it. `pit_detect.find_stops` does not fire because it
  requires a stationary window and takes `fuel_before` from the first sample INSIDE it.
  Reproduced on the real DB, session 16 lap 1: `fuel_l` steps **96.192 → 100.000 in a single
  frame** at 0.00 km/h — **228 L/s**, where GT7 fills at ~1 L/s. `find_stops` reports that window
  with signals `('speed',)` only and `serviced=False`.
  Currently invisible only because the OLD frame-to-frame gate never fired at all — but with the
  new windowed gate in place a 113.5 s lap the driver actually drove is marked `is_pit_lap=1` with
  `fuel_added_l=3.47`, leaves `counted_laps`, drops the NEXT lap as an out-lap, and
  `race_outcome`/`prompts/build.py:903` report a stop that never happened.
  Fix: reuse `analysis/refuel.MAX_PLAUSIBLE_LPS` (25.0 L/s) as a ceiling, and require the car
  stationary (`TYRE_SWAP_MAX_SPEED_KPH`) rather than merely below 120 km/h.
  Note: `pit_detect`'s own `on_track` requirement is INERT on the offline path —
  `reaggregate.py:93` hardcodes `on_track=True` — so the real difference is the stationary window
  plus the fuel-rise measurement point.

- **P2 · recency.py:108 — `appliesTo: ["referenceLapMs", ...]` is FALSE, and the block carrying
  the claim is NEVER EMITTED.** Sharpens G12 considerably. `recency.weighted` is called exactly
  once in production, for FUEL only; the reference pace comes from unweighted
  `green_lap_reference_ms`. `referenceLapMs` appears nowhere else in the repo or the contract.
  **The false claim survived because `Weighting.as_export()` is never called outside tests** —
  `RaceInputs.weighting` is set at evidence.py:514 and read nowhere — so the weighting block
  never reaches `derived` at all, contradicting recency.py:52-54.
  The docstring's own worked example (0.37 s/lap faster than the pooled median, "about ten seconds
  over a 50-minute race... it moves the stop lap too") is the case for weighting the PACE — and
  the pace is the one figure not weighted.

- **P2 · thresholds.py:106 — TWELVE live thresholds never restated**, against the module's own
  docstring ("Every one of these is restated in `derived.thresholds` on each export"). Larger list
  than the other agents found: adds `FRESH_TYRE_COOLING_C`, `FRESH_TYRE_MAX_SPEED_KPH`,
  `CORNER_MIN_SEPARATION_M`, `SPEED_SMOOTHING_MS`, `ON_TRACK_SURFACES` to the seven already known.
  Recommends bumping `DETECTOR_VERSION` to 3 so exports before and after are not silently compared.

- **P3 · pit_state.py — THE WHOLE MODULE IS DEAD.** 215 lines, **zero importers** anywhere in the
  repo. Its docstring describes itself as the state machine `RaceStateTracker` feeds — and no
  `RaceStateTracker` exists in `pitcrew/`. `pit_detect.py:29-31` already says it is superseded and
  "detects nothing", but the file was left in place.
  **Worse than dead: its `classify_pit_confidence` encodes a confidence model (refuel = MEDIUM,
  speed-only = LOW) that directly CONTRADICTS the live one in `pit_detect.Stop.confidence`
  (fuel+swap = high, either = medium, speed-only = low)** — so a maintainer who finds it first
  gets the wrong model. Delete it.

- **P3 · capture.py:87 — the oversize-datagram refusal cannot fire, and the failure it guards
  against happens silently.** The only production caller receives from `sock.recvfrom(4096)`,
  which truncates at exactly `MAX_DATAGRAM`, so `len(data) > 4096` is unreachable. A genuinely
  oversize datagram is written to the capture file **silently truncated** — precisely the
  "plausible garbage" the guard was written to refuse. Fix: `recvfrom(MAX_DATAGRAM + 1)`.

## OPERATIONAL NOTE FOR UAT — not a code defect
Because `is_pit_lap` is still 0 on all 132 laps in `data\pitcrew.db`,
`incidents.find_incidents` currently reports the real **69.6-second pit stop** (session 19,
lap 14) as an incident — *"Came to a stop, +73.3 s"* — and `race_outcome` would report
**"No stops."**
`tools/reaggregate.py --apply` fixes both, and **nothing in the app runs it automatically.**

## MODULES READ AND FOUND CLEAN, with what was checked
- **pit_detect.py** — window open/close, `RESUME_S` excursion handling, gap accounting,
  `_swapped`, `refuel_span`, `serviced`/`confidence`. Correct on the real capture set; it is the
  RIGHT half of the disagreement with the live detector. Cosmetic non-defect:
  `reaggregate.samples_from` passes `lap=frame_index` so `Stop.lap` is a frame index there —
  harmless because `read_session` uses the DB's own `lap_num`.
- **gearing.py** — ran `gearing_export` against sessions 9, 11, 19 of the real DB; ratios, final
  drive orientation, limiter rpm/gear, K extrapolation and `matchesSheet` all behave as
  documented. One wobble not reported: `gearing_constant`'s docstring bullet reads as absolute
  while the code falls back to the derived figure — but it labels the fallback
  "derived, and high by the unloaded-radius bias", so nothing is presented as measured.
- **gate.py** — re-derived the calibration arithmetic in the docstring: real questions
  0.028-0.244, unrelated 0.416-0.473, gap 0.172; `medium` (0.30, 0.40) sits inside it.
  Stage ordering matches the stated reasoning.
- **resolve.py** — supersession on lap-length mismatch, version bump, `return stored` fallbacks
  all consistent; `None` correctly means "omit `corners`" rather than invent identities.
- **weather.py** — ran `rain_seed` over all 84 layouts in `gt7_tracks.json` against that file's
  authoritative per-layout `rain` field: **0 mismatches.** The bidirectional substring `_matches`
  does not misfire on any real name, including the Tokyo Expressway and Dragon Trail cases the
  data file calls out.
- **shift_beep.py** — hysteresis and downshift-mute state machine walked by hand across
  arm/re-arm/blip sequences.
- **phrase_manifest.py** — `number_word` over 0-99, `_FUEL_LINE` against the actual format string
  at `intents.py:116`, `segments_for` bounds, `plan_single_part_lines` comma filter.
- **sheet.py / vocabulary.py** — null-vs-zero handling, gear descent check, range
  inversion/empty-bound checks, `fraction_of_range` zero-width guard.
- **reference_screen.py** — filter, plate construction, column stretch. `numbered = all(...)`
  would IndexError on an empty row but `gt7_quick_reference.json` has none — not reachable.
- **banner.py** — verified every `theme.*` name it touches actually EXISTS (`WARNING`, `STENCIL`,
  `RUBBER_DEEP`, `STENCIL_DIM`, `STENCIL_CONDENSED`) — the `band_ink_for` class of defect
  specifically hunted for and not found here.
- **report.py / templates.py** — `is_empty`'s `session_kind` subtraction correct; `block()` raises
  rather than blanking.
