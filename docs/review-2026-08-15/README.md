# Pre-UAT code review and remediation — 15 Aug 2026

Full review of `pitcrew/` (~26k lines, 66 modules), then the fixes.
Three review rounds: 7 subsystem reviewers → 4 adversarial verifiers → 3 gap sweeps + 1 seam
hunt → a critic that returned INSUFFICIENT with 5 assignments → round 3 → **STRONG**.

Every module was read. Findings were verified from source and, where a number was claimed,
reproduced by running code against the real `data/pitcrew.db` (read-only copies). **4 findings
were rejected, 5 downgraded, and 10 proposed fixes corrected** because they would have broken
something else. The suite passed at exit 0 throughout the review, so every finding here is
something the tests could not see.

Remediation is on `fix/pre-uat-review-2026-08-15`. **1316 tests pass**; first-run smoke on an
empty database builds all eight screens.

---

## The two that mattered most

Both were in the measurement channel, and neither was visible from the code: each channel
decoded, converted and stored cleanly, and simply was not the quantity its name claimed.

**`yaw_rate` held `angvel_z` — the roll rate.** Yaw is `angvel_y`, proved three ways from the
owner's own frames: `road_plane_y` sits at 0.987–1.0 across all 918,673 samples so world-up is
+Y; `angvel_z` correlates +0.62…+0.76 with the derivative of suspension roll asymmetry; and the
stored channel integrated to −1.6° over a closed lap where a real one integrates to −360°.
`lat_g` is `speed × yaw` and its formula was right all along, which is why it read **8.46 g** on
a car that pulls 2–3.

**Slip was 2π too large.** GT7 broadcasts wheel speed in rad/s and the parser multiplied by 2π
again, so a wheel rolling true read **6.2832**. `wheelspin` fired on 99.7% of throttle frames
and `lockup` on 0.2% — a driver who trail-brakes deep by design had never once been shown a
lockup. The test fixture synthesised rev/s, so it asserted 1.0 against its own assumption.

**Repaired, not re-captured.** The blob is versioned; v1 laps have yaw reconstructed from
`pos_x`/`pos_z`, `lat_g` recomputed and slip divided out. Verified across the 132 stored laps:
slip 1.0000, `lat_g` 2.20 g, yaw integral **−359.9°** median over 123 single-lap captures.
Yaw is `None` where the car is stationary — never `0.0`, which would satisfy "not rotating any
harder" and corrupt the understeer detector.

### What that did to the corner flags

| flag | as built | after |
|---|---|---|
| wheelspin | 99.7% | 34.4% |
| lockup | 0.3% | 8.8% |
| understeer-mid | 54.2% | 7.8% |
| trail-brake-instability | 31.2% | 0.0% |
| countersteer | 36.3% | 3.3% |
| kerb-strike | 48.5% | 38.4% |
| off-track | 9.3% | 6.8% |

---

## Also fixed

**Live race** — `laps_to_stop()` counted overdue laps as fuel *in hand* ("You can push, 2.9 laps
in hand" with 0.88 aboard, at high confidence); the fill at each stop was computed to the flag
rather than to the next stop; a timed race's **minutes** were used as a lap count all race; any
pit exit reset the tyre model even when no tyres changed; each call kind was said at most once
per stint however far a shortfall grew; the fuel-saving call was a fixed "Map 3" whatever the
gap.

**Engineer** — the PTT answer was posted with `QTimer.singleShot` from pynput's hook thread,
which has no event loop, so it never fired; the semantic gate was selected from the configured
backend rather than the recogniser actually built, so a SAPI failure ran free dictation ungated;
`match_intent` matched substrings with `"p"` and `"no"` in the vocabulary; the voice self-test
reported success before synthesis was attempted; there was no way to choose a sound device.

**Export** — `fuelCapacityL` took the first non-null so a `0.0` disabled lap validity for a
whole event; `meta.packet` fell back to a literal `"A"`; `modelledStintLaps` was the last run's
rate with no compound named; a temperature-inferred fresh set was labelled `measured`; the
prompt declared one compound by a non-deterministic majority vote. Contract is now **1.5** with
a §16.4 change table.

**App** — `theme.band_ink_for` was called and never written, so no compound band had drawn its
code since `cbe19fe`; a qualifying sheet loaded under the Race label and one Save retagged it;
switching events left the previous event's plans loaded and Approve filed them against the new
one; `data/` and the database were resolved against the working directory.

---

## Before you start UAT

1. **Set your Windows default input and output**, or pick them explicitly on Settings →
   Sound devices. PortAudio resolves the default once at import, so a headset connected after
   launch is not found. This is now selectable, but the choice still has to be made.
2. **Run `tools/reaggregate.py --apply` against your database.** `is_pit_lap` is 0 on all 132
   laps, so a real 69.6 s stop currently reports as an incident and `race_outcome` says
   "No stops". Nothing runs it automatically, and it was left for you rather than run against
   your data unasked.
3. **Take one live raw capture and check it in.** The aggregation fixture now exists
   (`pitcrew/tests/fixtures/watkins_glen_lap.bin`, a real recorded lap), but all 245 files in
   `captures/` are byte-identical copies of one synthetic packet, so the **raw UDP datagram
   path** still has no real sample. Fabricating packets from decoded frames would defeat the
   purpose. `captures/` is gitignored and untracked, so it was left alone rather than deleted.

## Known-thin coverage

All seven remediation agents hit a session limit mid-task, each while writing tests. Their
source edits landed and the suite is green, but their own verification was cut short. The
channel, corner, controller, store and audio work was measured directly against the real
database; **the analysis, export and engineer changes carry the agents' own tests and no
independent check.** Worth a closer look during UAT than the pass count alone suggests.

---

## Files
- `BRIEF.md`, `CRITIC.md` — the standards reviewers and the critic were held to
- `findings-round1*.md` — subsystem sweeps
- `findings-seams.md` — defects living between subsystems
- `verdicts*.md` — adjudications: rejections, downgrades, corrected fixes
- `findings-r3-channels.md` — the yaw axis and the 2π slip error, with before/after flag rates
- `findings-r3-export.md` — payload audited field by field; 37 unenforced validator constraints
- `findings-r3-audio.md` — the engineer's audio path, and the physical UAT checks
- `findings-r3-modules.md` — the last 19 modules, with what was checked in each clean one
