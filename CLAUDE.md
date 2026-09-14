# Pit Crew — project instructions

**Read this before writing any code.** It is the whole brief: what the app is for,
what the game will and will not give you, and the rules the output has to obey.
This file is the contract with the wider programme; `EXPORT-CONTRACT.md` is the
contract with the tool that consumes our output.

Written 11 Aug 2026 · GT7 v1.70 · rebuild of an existing codebase.

> **23 Aug 2026 — the app has a fifth job, and it is the one the other four
> serve: be the driver's race engineer.** The standard, the gap analysis against
> what is actually built, and the build order are in
> `docs/RACE-ENGINEER-CHARTER_2026-08-23.md`. Nothing in it overrides this file,
> `EXPORT-CONTRACT.md`, or §3's facts about the feed — **it is bounded by them,
> and the charter's §6 says where.** Two things from it belong here because they
> change what the app may claim:
>
> - **Rank zero of every diagnosis is "what is actually in the car."** The setup
>   record has been wrong in five consecutive sessions. A correct telemetry
>   reading against a wrong setup record produces a confident wrong answer.
>   **On 5 Sep 2026 the app stopped keeping that record at all** — see §1a. The
>   question is unchanged and it is now answered entirely outside this app.
> - **Per-lap, per-corner input coaching may not ship; a best corner built from
>   many laps may.** Measured over 307 clean laps, a corner is 3–4× noisier in
>   relative terms than a whole lap, so no single lap — and no handful — can carry
>   *"brake 10 m later at T4"*. Multi-lap trends, whole-lap comparisons and pooled
>   findings are fair. **Amended 14 Sep 2026 with the driver's yes**
>   (`brain/RECONCILIATION.md` AV, plan row 5.B0): the engineer may build a best
>   corner from his own laps — entry, middle and exit together — and say which
>   input paid, **one input at a time, with arriving speed, fuel and the session
>   held on both the input and the result, never read off the laps with the best
>   result.** An input is credited alone only when enough matched laps separate it
>   from what moves with it; every marker is `[DERIVED]` and carries its lap
>   count; a corner without enough laps says "can't tell yet"; a marker becomes
>   the reference only after a sized try–back–again run on which the time down the
>   next straight and the driver's report agree. In practice George may guide a
>   best lap from markers Ludo issued — never in a race, never a marker or a
>   verdict from one lap. The full guard list is the refusal card,
>   `.claude/skills/ludo/references/refusals.md`.

---

## 1. What this app is

Pit Crew is a **local race-engineering companion for Gran Turismo 7**, run on a PC
alongside a PS5. One driver, one league. It does four jobs, in this order of
maturity:

1. **Capture.** Read GT7's UDP telemetry stream and record it.
2. **Record practice sessions.** Persist runs, aggregate them per lap and per
   corner.
3. **Export what was measured.** Emit a `gt7-pitcrew` JSON payload the tune
   builder reads — directly, over MCP, or pasted. **`EXPORT-CONTRACT.md` defines
   this payload exactly. It is the app's most important output — treat the schema
   as an API.**
4. **Race strategy.** Compute a stint and fuel plan before the race, then talk the
   driver through it live and adapt it as the race actually unfolds.

Jobs 1–3 are the loop that makes the car faster. Job 4 is the one used under
pressure, so it has the strictest correctness bar.

## 1a. What the app does NOT hold — the setup

**5 Sep 2026. The app no longer records what is in the car, and this is not a
gap to be filled in.** No setup sheet, no per-slider values, no gear ratios, no
mid-session change ledger, and no UI to enter any of it. Do not rebuild one.

The reason is the failure it caused. The setup record was wrong in five
consecutive sessions — a Yas Marina sheet at Road Atlanta, a v1 sheet against a
Rev B car, `bb -1` in the car against `0` on every sheet on file — and every one
was caught by the driver mentioning it in passing, never by the app. Two copies
of a setup existed, so there were two setups. Better checking does not fix that;
having one copy does.

**Where it lives now.** The tune builder (the `ludo` skill) holds the car and the
gearbox and issues changes directly. `brain/car-state/<car>-<circuit>.md` is the
only place a setup value may be written; everything else links to it and restates
nothing. The driver confirms what is actually in the car with a screenshot of
GT7's own settings screen, which is the ground truth and the only one left.

**Four things stayed, and each for a stated reason:**

- **The range record and the Car screen.** A range record is not a setup — it is
  the car's own slider min and max, read off its settings screen once and never
  re-entered. It is what lets the whole programme reason in percent of slider
  range rather than absolute values (§4 rule 6), and it outlives every sheet ever
  run on the car.
- **The shift table** (`engineer/shift_points.py`). This is the one part of a
  setup that has to reach the driver *through the app* — it is a beep in his ear
  at 60 Hz, not something he can read off a screen mid-corner. It is **issued by
  the tune builder, never typed in**, keyed by car AND circuit because a gearbox
  is cut for the circuit, and it carries two absolute per-gear tables: one for lap
  time and one for a fuel-bound stint. A gear with no issued point does not beep.
- **The `setup_sheets` table, as archive.** 96 sessions of laps reference it and
  `lap_frames` cascades off `laps`. It is read by `archived_setup_sheet` for the
  offline tools and written by nothing.
- **The `setup_changes` table, as archive — and read by nothing either.**
  206 rows to session 119, the last written 4 Sep 2026, each carrying a
  `from_value` and a `to_value`: absolutes, the second setup record this
  section removed. Nothing in the app writes it or reads it (checked 11 Sep:
  the schema and one migration are its only code). **The experiment ledger that
  replaces it lives in `brain/ledger/<car>-<circuit>.md`, not here** — key,
  direction and delta in percent of slider range, never a from/to value (plan
  row 2.1). A change ledger in the database is this section's defect again,
  whatever its columns.

## 2. Who it is for

A single driver on a Fanatec DD Extreme (18 Nm), ClubSport V3 pedals with a load-cell
brake, PS5, sometimes PSVR2. He races a custom league with **no BoP and open garage
tuning**, mixed sprint and multi-stop formats. He trail-brakes deep by design and
runs low or no assists. This matters for job 4: during a race he is wearing a wheel
and possibly a headset, so **live strategy output must be usable without reading a
screen** — audio, or a single large number, not a dashboard.

---

## 3. Hard facts about the GT7 telemetry feed

These bound what is buildable. Do not design around channels that do not exist.

### 3.1 Transport

- **Encrypted UDP, Salsa20.** The key is a fixed ASCII string used by every public
  parser; the IV comes from the packet.
- **60 Hz.** A 12-lap run is roughly half a million samples.
- **Heartbeat-driven.** The console only streams to an address that has sent it a
  heartbeat byte, and it stops when heartbeats stop. Re-send on a timer.
- **Four packet formats,** selected by which heartbeat character you send:

  | Heartbeat | Size | Adds |
  |---|---|---|
  | `A` | 296 B | base set |
  | `B` | 316 B | wheel rotation, sway, heave, surge |
  | `~` | 344 B | per-wheel surface type, steering angles, wheelbase, filtered pedals, torque vectors, energy recovery |
  | `C` | 368 B | current-lap time in ms, car category |

  **Request `C`.** It is a superset and it is the only format that carries
  **current-lap time in milliseconds**, which live strategy needs. Fall back to `A`
  only if `C` fails to decode, and record which format was used — the export has to
  declare it (`meta.packet`) so that absent channels read as *not available* rather
  than *not measured*.
- **⚠️ VERIFY BEFORE BUILDING:** the send/receive port pair. The widely used pair is
  **send heartbeat to PS5 UDP 33739, receive on 33740**, but port assignment for the
  extended formats is not consistently documented across parsers. Confirm against
  whichever reference parser you vendor, and write a connection self-test that fails
  loudly rather than silently returning zeros. Same for heartbeat interval —
  published implementations range from every 100 packets (~1.7 s) to every 1000
  (~16 s). Treat >1 s of stream silence as a dropped connection and re-heartbeat.

### 3.2 What the feed gives you

Position, world velocity, rotation, angular velocity, body height, engine RPM, fuel
level and capacity, speed, boost, oil pressure, oil and water temperature, per-wheel
tyre surface temperature, wheel RPS, tyre radius, per-wheel suspension height, gear
and suggested gear, throttle, brake, clutch, gear ratios, lap count, best and last
lap time, day progression — and in the extended packets, per-wheel surface type,
steering angle, sway/heave/surge, per-wheel torque vectors, filtered throttle and
brake, energy recovery, current lap time.

### 3.3 What the feed does NOT give you — the four that shape the architecture

**1. There is no tyre wear channel. None. In any packet format.**
This is the single most consequential fact in this document. Job 4 exists to plan
around tyre life, and the game will not tell you what the tyre life is. Wear must be
**modelled and corroborated**, from three sources:
  - the driver reading the in-game HUD gauge and entering it (most reliable, coarse);
  - lap-time degradation against a fresh-tyre reference;
  - tyre surface temperature trend and front/rear asymmetry.

Never present modelled wear as measured. Every wear number the app displays carries
its source. See §5.

**2. There is no track ID.** The feed does not say which circuit you are on.
Circuit is **driver-selected**, and corner identification comes from the app's own
track model, not from the game. Two viable approaches, and the export must say which
was used:
  - **`track-map`** — a stored per-circuit corner definition (lap-distance windows,
    or world-coordinate gates). Stable corner IDs across sessions. Preferred.
  - **`auto-segment`** — derive corners from speed minima and steering activity,
    numbered in order around the lap. Works day one, but corner IDs are only
    comparable within a session unless you anchor them.

Corner aggregates are worthless if `T3` means a different corner next week. Whatever
you choose, **corner identity must be stable and the export must declare its source.**

**3. Suspension is reported as height in metres, not travel remaining.**
The v1.0 spec asked for "travel remaining, zero means bottomed." That is not
directly measurable. You get an absolute per-wheel height. Bottoming must be
inferred: capture a static/steady-state reference per car per setup, then flag
sustained excursions toward the observed minimum. Export the raw minimum height
**and** the reference used, never a bare "travel remaining" that implies a
measurement you did not make.

**4. Oil temperature is pinned at ~110 °C and water at ~85 °C.** They are constants.
They carry no information. Do not capture, store, display, or export them.

### 3.4 Units — convert once, at the parser boundary

| Channel | Feed gives | Store and export as |
|---|---|---|
| Speed | m/s | km/h |
| Throttle, brake | 0–255 | percent, 0–100 |
| Steering (`wheelRotation`, `wheelSteeringAngle`) | radians | degrees, and also keep normalised −1…1 |
| Suspension height, body height | metres | millimetres |
| Wheel rotation rate | RPS / rad·s⁻¹ | keep native; use with tyre radius for slip |
| Lap and sector times | milliseconds | milliseconds, integer — never a formatted string |
| Fuel | litres | litres |
| Tyre temperature | °C | °C |

Fuel capacity is **100 L for almost every car, 5 L for karts, 0 L for electric**.
A capacity of 0 is a real value, not an error — guard the divide.

Surface type is a character per wheel: `T` tarmac, `C` kerb, `D` dirt, `G` grass,
`S` sand, `s` snow. Richer than a boolean off-track; keep the distinction.

---

## 4. Standing rules inherited from the race-engineering programme

These are not style preferences. They come from the knowledge base this app feeds,
and output that violates them will be discarded on arrival.

1. **The driver's report is primary evidence. Telemetry is corroboration.** Never
   structure output so that data appears to overrule what the driver felt. Where the
   two disagree, that disagreement is the finding — surface it, do not average it.
2. **Aggregates, not raw samples.** Raw 60 Hz traces stay in the app. The export is
   per-lap and per-corner summary only.
3. **Missing is `null`, never `0`.** A zero that means "not measured" gets diagnosed
   as a real value. This rule is absolute and applies at every layer.
4. **Every aggregate carries its sample count.** A corner metric from two laps and
   one from eleven are not the same claim.
5. **Nothing derived is presented as measured.** Anything the app computes — slip
   ratio, understeer index, countersteer events, wear, bottoming — goes under a
   `derived` heading with its threshold or model stated.
6. **Reason in percent of slider range, not absolute values.** GT7's tuning ranges
   are per-car and derived from chassis data. "3.5 Hz" is meaningless across cars.
   Wherever the app stores or shows a setup value, store the car's slider min/max
   with it.
7. **Any GT7 tuning logic published before August 2024 is void; before February 2025
   is suspect.** Update 1.49 rewrote the physics, tyre wear and geometry model; 1.55
   did a second pass. If you find yourself importing a heuristic from a guide, check
   its date first.
8. **GT7 has no tyre pressure, no caster, no brake pressure, and no high/low-speed
   damper split.** If any of these appear in the UI, the model, or a comment, the
   logic was pattern-matched from another sim and is wrong throughout.

9. **`max(x, 0.0)` on a measurement is rule 3 in disguise, and it is the most
   repeated defect in this codebase.** A quantity that came out negative is not
   a quantity of zero — it is a reading whose *reference* is wrong, and clamping
   it converts "I cannot tell you" into a confident, well-formed, wrong answer
   that no downstream consumer can distinguish from a real one. Three instances
   found in one race: `fuel_used` clamped on two laps that plainly burned fuel,
   and the launch-detector offset clamped so a −2 s green read as `0.00 s`
   against a log line whose entire stated purpose was to report that sign.
   Where the arithmetic can go negative, return `None` and say why.

10. **A rule that refuses a reading must be able to refuse its own baseline.**
    Any check of the form *"is this new value consistent with the last good
    one?"* is a latch unless something can retire the reference. The tyre gauge
    accepted one bad frame, then refused 432 consecutive honest readings against
    it and accepted nothing for a whole race, because a refusal — correctly —
    never becomes the baseline, and nothing else could clear it either. Two
    guards, and both are needed: bound how far a reading may move *in each
    direction*, and drop the reference after a sustained run of refusals,
    because a reference that disagrees with everything is the thing that is
    wrong. **And log the accepts, not only the refusals** — the ratchet was
    invisible for a whole race precisely because the number setting the bar
    never appeared in the log.

11. **State that outlives a session will be read as if it belongs to this one.**
    The sampler, its comparison series, and the controller's lap-id map are all
    built once and torn down at app exit, so a race opened judging its fresh
    tyres against practice's worn ones, and a practice gauge reading was spoken
    aloud as a measured race number two laps in. Anything cached across a
    session boundary needs an explicit reset at the start of the next one, and
    that reset needs a caller — `LiveWearSampler.new_session()` existed,
    documented why it was needed, and was called only from a test file.

12. **Report the constraint that actually bound the answer, not one from the
    same family.** The strategy layer laid plans out against the lowest of three
    ceilings and reported a constraint computed from only two of them, so a plan
    capped by *"nobody has run a stint this long"* told the driver it was
    fuel-limited. Those two readings demand opposite driving. Where a decision
    is a `min()` over several limits, the reported reason must come from the
    same expression that produced the decision.

13. **Two calls that use the same words must mean the same thing.** "Laps in
    hand" was spoken twice in two minutes meaning laps-to-the-stop and
    laps-to-the-flag — figures ten laps apart, neither naming its reference.
    Under a helmet the driver cannot ask which one he just heard.

---

## 5. Job 4 — the race strategy engine

The hardest part of the app, and the part most likely to be built on sand. Build it
as an explicit model with stated assumptions, not as a pile of heuristics.

### 5.1 The wear model is piecewise, not linear

GT7's post-1.49 degradation has three phases:

- **0 → ~50% worn:** near-flat. Losses in tenths. Do not pit here.
- **~50 → ~90%:** progressive, roughly 0.5–1.5 s/lap cumulative. **Balance shifts
  before the stopwatch does** — front-limited entry understeer appears first on most
  Gr.3 cars.
- **>~90%:** cliff. Traction effectively gone, car undriveable rather than merely slow.

**Do not fit a linear model.** The optimisation is not "integrate pace over the
stint," it is **"how long can I run without entering phase 3."** Because onset is
sharp, overshooting costs far more than undershooting — build one lap of margin into
every recommendation and say that you did.

### 5.2 Stint length

    L = 0.85 / w        where w = wear fraction consumed per lap

Use 0.85, not 1.0, so the stint ends before the cliff. `w` must be **measured at the
multiplier actually being raced**, from a run at genuine race pace from a full tank.

**Multiplier linearity is ASSUMED, not proven.** The common claim is that multipliers
are pure linear rate scalars, so a stint measured at one converts exactly to another.
The evidence is two informal forum statements plus a calibration method that assumes
linearity rather than demonstrating it. The app may offer a conversion, but it must
label the result `[ASSUMED]` and prompt for a calibration at the target multiplier.
**Never silently convert from a high multiplier down to a race multiplier.**

### 5.3 Fuel

- Six-level fuel map on the MFD. **Level 1 = richest, most power, most consumption.
  Level 6 = leanest.** Third-party sources that say 1–5, or that invert the
  direction, are wrong.
- Roughly **−4% power and −8% consumption per step**, except step 6, which is
  anomalous: about **50% consumption for about 80% power**. Model step 6 separately.
- Fuel weight: a full 100 L tank is ~73 kg. Working figure ~0.003 s/L/lap on a
  ~90 s circuit. **This is derived, not measured** — flag it, and let the driver
  overwrite it with a measured value.
- **Fuel-saving in a slipstream is nearly free** and is the highest-value live call
  the app can make. If it can detect a tow (closing speed plus proximity is not in
  the feed — this may need driver input or a manual toggle), prompt for map 5–6.
- Short-shifting saves ~20% fuel for ~0.5 s/lap **and** reduces rear tyre wear.

### 5.4 Pit stops

- Pit time loss is a **track constant**, not a car variable. Measure once per circuit
  and store it. The only meaningful variable is fuel taken, at roughly
  **0.5–1.0 s per 10% of tank**.
- There is a 5–10 s dead time at the start of every stop before refuelling begins.
- **No partial tyre changes. No split compounds front/rear.** Axle-asymmetric wear
  cannot be solved with strategy — only with brake balance (adjustable mid-race via
  the MFD) and setup.
- **The undercut is weak in GT7** — cold out-lap penalty of 0.5–1.5 s plus a long pit
  delta. The overcut is comparatively strong. Do not import F1 instincts.
- Take fuel only to the in-game diamond marker plus one lap of margin. The diamond is
  accurate.

### 5.5 What a live call must look like

Under a helmet, at racing speed. One thing at a time, stated as an instruction, with
the reason second and short:

    "Box this lap or next. Fuel is the constraint — you're 1.2 laps short."
    "Map 3 down the back straight. You're a lap light on fuel."
    "Brake balance one click rearward. Fronts are going first."

Not a table. Not three options. If the app is not confident, it says so in the call
itself — "unconfirmed" is a word the driver can act on. Every live call must be
derived from a stated model with a stated confidence, and the post-session export
must contain the calls it made and the assumptions behind them, so they can be
audited afterwards against what actually happened.

---

## 6. Architecture notes

- **Capture, aggregation, strategy and UI are four separable layers.** The parser
  must be swappable; packet formats have changed across GT7 versions and will again.
- **Persist the raw stream to disk during a session,** then aggregate. Re-aggregating
  a stored session after fixing a corner-detection bug is the difference between one
  evening of work and re-running every test.
- **The setup as run is not app state, and not the app's business.** It was, and
  it is the removal described in §1a. Do not reintroduce it: a value kept here as
  well as in the tune builder's car-state file is two values, which is the defect,
  not a redundancy.
- **Slider ranges are measured once per car and never re-entered.** Store them
  keyed by car in the vocabulary given in `EXPORT-CONTRACT.md` §6 — the consuming
  tool uses those exact keys, so a range record round-trips with no translation.
- Recommended build order, highest return per hour first:
  1. `rangeRecord` — pure app state, no telemetry needed
  2. `corners` with min speed, consistency and flags — the diagnostic core
  3. `laps` with tyre temperatures and fuel — feeds strategy and wear
  4. `session` aggregates — cheap once the rest exists
  5. `strategy` — the plan and its assumptions
  6. `derived` — last, and only after the thresholds have been sanity-checked
     against a session where the driver's account is already known to be right

## 7. Testing

- **A recorded session file is the test fixture.** Capture one real practice run
  early and check it in. Every aggregation change gets re-run against it.
- **The connection must fail loudly.** A decrypt failure, a wrong port, or a stopped
  heartbeat must not degrade into a stream of zeros. Zeros are the one failure mode
  that survives all the way into a setup recommendation.
- **Validate the export against `EXPORT-CONTRACT.md` before writing it out.** A
  malformed payload is pasted into a prompt and silently misread. Schema-validate,
  and refuse to export rather than export something wrong.
- Round-trip test: export → parse → confirm every non-null field has a unit and a
  sample count, and every null is genuinely unmeasured rather than defaulted.
- **The full suite runs in one command, as of 6 Sep 2026.** `python -m pytest
  pitcrew/tests` — green, exit 0, verified twice.

  It did not, for months, and the reason was one line. `ui/widgets.py` built its
  wheel guard at module scope: `_WHEEL_GUARD = _WheelGuard()`, a QObject
  constructed before any QApplication exists and held by a Python reference for
  the life of the process. When one test file tore its QApplication down, Qt
  deleted the C++ object underneath, and every later file died in *setup* on
  `RuntimeError: wrapped C/C++ object of type _WheelGuard has been deleted` —
  so a whole quarter of the suite errored, and the `0xC0000409` in PyQt teardown
  came from the same orphan. It is built on demand now, and rebuilt if Qt takes
  it away.

  **This was diagnosed as an environment fault for months and it was a product
  defect**, in the widest-used helper in the UI. The instruction here used to be
  to run in quarters and treat a crashing quarter as the machine's fault, which
  is exactly the reading that kept it alive: a rule that tells you to expect a
  failure stops anyone asking what causes it. Quarters still work and are still
  quicker to bisect with, but a green "all tests pass" is now available and
  should be the thing you check.
- **A test that passes in a group and fails alone — or the reverse — is telling
  you about shared state, not about the change in front of you.** Before
  attributing a failure to your own work, reproduce it with your change reverted.
  Two of the failures found while fixing the Fuji race predated it entirely, and
  one timing assertion only fails under full-suite load.

## 8. Out of scope

Do not build: raw trace export, GPS position arrays, engine RPM series, oil and water
temperature anything, boost logging, replay-derived data, live leaderboards, or
anything that reads or writes GT7 game state. The app observes and advises. It never
drives.
