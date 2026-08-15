# Pre-UAT code review — 15 Aug 2026

Full review of `pitcrew/` (~26k lines, 66 modules) run immediately before manual UAT.
Three rounds: 7 subsystem reviewers → 4 adversarial verifiers → 3 gap sweeps + 1 seam hunt
→ a critic that returned INSUFFICIENT with 5 assignments → round 3 → **STRONG**.

Every module has been read. Findings were verified from source and, where a number was
claimed, reproduced by running code against the real `data/pitcrew.db` (read-only copies).
4 findings were rejected, 5 downgraded, and 10 proposed fixes corrected because they would
have broken something else. Baseline: the full test suite passes at exit 0, so everything
here is something the 52 test files currently miss.

## Fix these three first — they are the measurement channel, and every corner diagnostic is downstream

**1. `recorder.py:171` — slip ratios are 2π too large.** GT7's per-wheel channel is rad/s;
the code multiplies by 2π again. Verified: median `slip_fl` on straight-line coasting frames
is **6.2832** where a rolling wheel must read 1.0. Consequence: `wheelspin` fires on **99.7%**
of throttle-on frames and `lockup` on **0.2%**. The shipped export carries wheelspin on all
nine Watkins Glen corners and no lockup anywhere.
**Land it together with** returning `None` below `_MIN_SPEED_FOR_SLIP_MS` instead of the
synthetic `1.0` — the 2π bug is currently the only thing making that fabrication detectable.

**2. `recorder.py:308,325` — the channel stored as `yaw_rate` is `angvel_z` (roll), not yaw.**
Yaw is `angvel_y`, proved three ways from the stored data (`road_plane_y` ≈ 1.0 ⇒ world-up is
+Y; `angvel_z` correlates +0.62…+0.76 with the derivative of suspension roll asymmetry; stored
yaw integrates to −1.6°/lap where true yaw integrates to −360°). Correlation with true yaw:
**0.027**. `lat_g` peaks at **8.46 g** on a car that pulls 2–3.
**Repair, do not re-capture** — the 132 stored laps are recoverable from `pos_x`/`pos_z`
(reconstruction error 2–4% of the cornering signal). Append a NEW field; do not reuse the slot
(`decode_frames` maps by the blob's own stored `fields` list). Return `None` on frames with no
displacement — heading is undefined when stationary.
Then run `tools/reaggregate.py --apply`: the v5 back-fill is gated on `crawl_s IS NULL` and
will not re-run itself, so spin detection stays dead until you trigger it.

**3. `export/build.py:270` — `fuelCapacityL` takes the first non-None, so a `0.0` wins.**
Event 3's earliest session opened before the car loaded and holds 0.0; four later sessions hold
100.0. Contract §5 makes 0 a real value meaning electric. It **switches off the lap-validity
check for the whole event** (`fuel_implausible_laps` returns `set()` on `<= 0`) *and* removes
the fuel constraint from every race plan (`bindingConstraint` can never be `fuel`), with
nothing in the payload saying so.

## Then, before you trust an export

4. **`wear.py:342` — `modelledStintLaps` is `rates[-1]`**, the last run's rate, with no compound
   named. Real data: exports **26** off a Racing Hard rate while Racing Soft is ≈4 laps. A
   driver planning 26 laps who fits softs runs 5–6x past the cliff, and §5.1 says overshooting
   is the expensive direction.
5. **`RunWear.confidence`** grants `measured` to a temperature-inferred fresh set, and
   suppresses `assumesFreshAtLap` with it. Four of six Monza runs carry `confidence: measured`
   on an app-side heuristic; that promotes the whole payload to `modelConfidence: "measured"`.
   (`FRESH_TYRE_TEMP_C = 70.0` is fabricated — real range 60–70.)
6. **The audio device.** `sounddevice` resolves the default input and output once at import and
   never re-enumerates. Set the Windows defaults to the device you will actually race on
   *before* launching.

## The live-race calls (`race/calls.py`) — fix before racing, not necessarily before UAT

- `laps_to_stop()` has no floor, so overdue laps count as fuel *in hand*: reproduced
  **"You can push. 2.9 laps of fuel in hand"** with **0.88 laps aboard**, at high confidence.
  Flooring at 0 is not enough — past the box lap, fall back to `laps_remaining()`.
- `_fuel_instruction` fuels to the flag, not to the next stop (multi-stop races).
  Carry the next stint's *lap count*; do **not** adopt `stints[i]['fuel_l']`, which is the
  planned burn and would discard the race-measured rate. Three tests encode this bug.
- A timed race's **minutes** are loaded into `laps_total` (`events.race_laps` holds minutes when
  `race_type='time'`, and `race_minutes` is never written).

## Safe to defer past UAT
Every P3; `pit_state.py` (215 lines, zero importers, and a pit-confidence model that
contradicts the live one — delete it); `capture.py`'s unreachable oversize guard;
`race/outcome.py`'s multi-stop deviation text; `derived.steerRotationDeg`; `meta.carCategory`
vocabulary; the validator's 37 unenforced constraints (that is how the *next* bug ships, not
this one); `schema.py`'s migration ladder (no migration runs at v5→v5).

## UAT steps that are pointless until a fix lands
- **Any judgement of `corners[].flags`** until fixes 1 and 2. `wheelspin` on 9/9 corners and
  `lockup` on none are both artefacts.
- **`understeer-mid`** until fix 2 — but **do not delete it**. An earlier claim that correcting
  the channel does not help was not reproducible; re-measured, reconstruction *cuts* firing from
  33% to 18% (the steering term alone fires on 74%, so it does need a magnitude threshold).
- **"Test engineer voice" proves nothing at any time** — it reports success before synthesis is
  attempted. Instead press "Test beep" *and* "Test voice" with the headset on: `winsound.Beep`
  re-resolves the default device each call and `sounddevice` does not, so **hearing the beep but
  not the voice confirms the stale-device diagnosis outright.**
- **Push-to-talk cannot be tested at all** until the input device is changed. The current
  default is a disconnected Bluetooth earbud that opens without error and delivers zero frames,
  which the app reports as "no speech in the capture" → "Say again."

## Status: all findings remediated — see `git log` on `fix/pre-uat-review-2026-08-15`

Fixed and verified on the real database: the yaw axis and the 2*pi slip error (with the 132
stored laps repaired on read rather than re-captured), the corner detectors, the live fuel
calls, timed races, the export payload and validator (contract now 1.5), the PTT thread hop,
the semantic gate selection, `band_ink_for`, the sheet-purpose retag, plans following the
driver to the wrong event, CWD-relative data paths, the pit-loss/refuel provenance, the audio
device selection, and the rack/export divergence.

`pitcrew/tests/fixtures/watkins_glen_lap.bin` is now the real recorded lap CLAUDE.md §7 asks
for, and `test_real_capture_fixture.py` asserts physics against it rather than golden values.

## Remaining, and they are not code
- **`captures/` is still synthetic.** 245 files, one distinct payload. It is gitignored and
  untracked, so it was left alone rather than deleted. The *aggregation* fixture now exists
  (above), but the **raw UDP datagram path** still has no real sample — take one live capture
  during UAT and check it in, rather than fabricating packets from decoded frames.
- **`is_pit_lap` is 0 on all 132 laps**, so a real 69.6 s pit stop reports as an incident
  ("Came to a stop, +73.3 s") and `race_outcome` says "No stops." `tools/reaggregate.py --apply`
  fixes it; nothing runs it automatically.
- **`catalogs.py:16` / `db.py:24` are CWD-relative.** Launching from a shortcut with "Start in"
  unset gives a fully-working app with zero tracks, zero cars, zero presets and a fresh empty
  database — silently. Resolve against `Path(__file__).resolve().parents[2]` as `app.py:61`
  already does.

## Files
- `BRIEF.md`, `CRITIC.md` — the standards reviewers and the critic were held to
- `findings-round1*.md` — subsystem sweeps (strategy, engineer, telemetry, analysis, export,
  store/controller, UI)
- `findings-seams.md` — defects living between subsystems
- `verdicts*.md` — adjudications: rejections, downgrades, corrected fixes
- `findings-r3-channels.md` — the yaw axis and the 2π slip error, with before/after flag rates
- `findings-r3-export.md` — payload audited field by field; 37 unenforced validator constraints
- `findings-r3-audio.md` — the engineer's audio path, and the physical UAT checks
- `findings-r3-modules.md` — the last 19 modules, with what was checked in each clean one
