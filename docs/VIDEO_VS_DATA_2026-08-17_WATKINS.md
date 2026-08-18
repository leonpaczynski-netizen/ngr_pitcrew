# Race video vs. recorded data — Watkins Glen, 17 Aug 2026

Session 49 (event 3, Lamborghini Huracán GT3 '15, Watkins Glen Long, 20 laps,
RS, 2x wear / 3x fuel). Source: 35:58 PS5 capture, 1280x720, checked frame by
frame against `laps`, `lap_frames`, `strategies` and `logs/pitcrew.log`.

Video and telemetry are synchronised: `video_t = race_t + 2.0 s`, confirmed on
the green-flag call, all 20 lap crossings and the chequered flag.

---

## 1. The tyre-wear gauge, measured

The HUD wear indicator is four bars; wear renders as a red fill growing down
from the top of each bar. Extracted every 2 s for the whole race (1079 samples)
and stored at
`reference/wear/watkins-glen_huracan-gt3_RS_2x_2026-08-17.csv`.

Read resolution is **±4%** — the bar is ~24 px tall at 720p and yuv420 chroma
subsampling halves that again, so values land on multiples of 1/12. Stint-level
rates are far better determined than any single reading.

Per-corner wear at each stint end:

| | FL | FR | RL | RR |
|---|---|---|---|---|
| end of lap 12 (12.0 laps) | 66.4% | 48.0% | **70.0%** | 52.1% |
| end of lap 20 (7.3 laps)  | 41.8% | 31.6% | **43.6%** | 33.6% |

**The wear curve is linear.** Regressing the raw samples on lap distance:

- stint 1: RL = −0.21% + **5.924 %/lap**, R² = 0.9885, n = 631
- stint 2: RL = **5.782 %/lap**, R² = 0.9571, n = 359

Mean residual by third of stint is under 1% in both stints and shows the same
sign pattern, i.e. no measurable curvature. Note this does not contradict
`CLAUDE.md` §5.1: that section describes the *grip and lap-time* response as
piecewise. The *percentage consumed* accumulates linearly. Nothing here tests
the >90% cliff — he never went past 70%.

### 1.1 The planned rate was 11% optimistic

The approved strategy carried `wearPerLap: 0.05193`, `source: "measured"`,
from 29 laps / 5 stints of practice gauge readings.

Measured worst corner: **5.85 %/lap**. The plan was **11% optimistic**.

It shows up directly in the plan's own note — *"longest stint ends in the
'linear' phase at 62% worn"*. 12 laps × 5.193% = 62.3%. The video says **70.0%**.

It did not cost him anything this time: fuel was the binding constraint at 12
laps, and both rates put the wear limit (0.85/w) beyond that — 16.4 laps
planned, 14.5 laps actual. On a longer stint or a fuel-light race that margin
is what gets consumed.

### 1.2 The practice readings that produced it are contradictory

Every gauge reading for this event, RS only, with the implied rate:

| session | lap | RL reading | implied %/lap |
|---|---|---|---|
| 14 | 4 | 0.08 | 2.00 |
| 15 | 5 | 0.35 | 7.00 |
| 16 | 5 | 0.39 | 7.80 |
| 46 | 3 | 0.11 | 3.67 |
| 47 | 12 | 0.60 | 5.00 |

A 2.0–7.8 %/lap spread averaged into a single "measured" number. Two causes:

- **`tyres_fresh` is NULL on all seven readings at this event.** The
  denominator — laps on *this set* — is being inferred from `lap_num`. If
  session 47's set carried over from session 46 the rate is 4.1 %/lap, not 5.0.
- Session 47 is the closest analogue to the race (same day, same setup sheet 16,
  race intent) and gives 5.0 %/lap against the race's 5.85. The race ran
  *cooler* (RL 81.5 °C vs 83.2) and *slower* (107.5 s vs 105.4 mean) yet wore
  **17% faster**. Whatever drives the rate, it is not mean temperature or pace.

**The video is now the best wear evidence that exists for this car and circuit** —
1079 samples across two stints at R² 0.99, versus five single-point readings
that disagree by a factor of four.

### 1.3 Per-corner distribution is stable, and telemetry predicts it

Wear share is almost identical across the two stints:

| | FL | FR | RL | RR |
|---|---|---|---|---|
| stint 1 | 28.1% | 20.3% | 29.6% | 22.0% |
| stint 2 | 27.8% | 21.0% | 29.0% | 22.3% |

RL is the worst corner at every one of the 20 lap-end readings. This matches the
Monza finding (RL worst on all 8 readings, never a front) — a second circuit,
a second car, same answer.

Tested three UDP-derived per-wheel quantities against that share:

- **Slip** (`|slip−1|` integrated): FL 12.3% / FR 13.5% / RL 36.7% / RR 37.2%.
  Useless — dominated by the driven axle on an MR car, not by wear.
- **Suspension height**: four wheels within 1% of each other. No signal.
- **Tyre surface temperature above a reference**, Σ(T − T₀) with T₀ fitted at
  **56 °C**:

  | | FL | FR | RL | RR |
  |---|---|---|---|---|
  | stint 1 predicted | 27.0% | 20.3% | 28.5% | 24.1% |
  | stint 1 measured | 28.1% | 20.3% | 29.6% | 22.0% |
  | stint 2 predicted | 27.9% | 19.3% | 28.8% | 23.9% |
  | stint 2 measured | 27.8% | 21.0% | 29.0% | 22.3% |

  Within 1–2 percentage points on all eight. Raw temperature (no reference
  subtraction) is much flatter and misses RL by 3.5 pp.

This is a **hypothesis from one race**, not a model: 8 points, two stints of one
car at one circuit, and the two stints are not independent. T₀ = 56 °C is fitted
against shares, which constrains it only loosely. But it is worth testing,
because it would turn one driver gauge reading of the worst corner into all four
corners from telemetry the app already stores.

Note the asymmetry the axle means hide: at lap 8 the app said *"Fronts 81, rears
82, settled"* — accurate as axle means (front 80.7, rear 81.5) — while the
individual corners were FL 84.2 / FR 77.2 and RL 83.7 / RR 79.3. A 7 °C split
across the front axle, and the limiting corner 6.5 °C hotter than its pair.
**Wear follows corners; the calls speak axles.**

---

## 2. What the data got right

Checked against the video, all confirmed:

- **Race position, 18 of 20 laps** exact (see §3.1 for the two that aren't).
- **Every live call landed on the correct lap.** All 14, mapped by wall clock:
  "P3. 15 to go." at end of lap 5, "Box in 2 / Box next lap / Box this lap" at
  laps 10 / 11 / 12, "P2. 5 to go." at lap 15, "Last lap" at 19, "Chequered
  flag. P1. Fuel 6.3 litres." — `fuel_end` lap 20 is 6.307 L.
- **"Fuel to 55 litres" was hit exactly.** UDP shows the tank going 27.237 →
  **55.230 L**.
- **Refuel rate 1.001 L/s**, against 1.0 declared on the event page. Dead time
  before flow 6.18 s; stationary 34.75 s.
- **Lap-13 pit delta 50.9 s**, of which 28.0 s is fuel flow and 16.2 s is
  pit-lane transit.

---

## 3. Defects found

### 3.1 Race position is read from the packet that closes the lap

`session_state.py::_check_lap` closes a lap on the first packet carrying a new
`last_lap_ms` and reads `position=p.current_position` from that same packet.
That packet is already **inside the following lap**, so on any lap where
position changes at the line the recorded value belongs to the next lap.

Lap 13 demonstrates it exactly: the video shows P5 for the whole of lap 13 and
P4 from the crossing onward; the database stores 4 for lap 13.

Lap 14 is worse and is *not* explained by this: video shows P4 through lap 14,
P3 from the line, and P2 only ~19 s into lap 15. The database stores 2. There is
a second, larger source of staleness around the stop that I have not isolated.

Both errors are on the pit lap and the lap after it — exactly the laps used to
judge whether the stop gained or lost places.

### 3.2 Lap 1's fuel is fabricated, and 6.4 L of the best evidence is thrown away

`laps` lap 1: `fuel_start` 49.939, `fuel_end` 93.555, `fuel_used` **0.0**.

The frame trace explains it. Lap 1's recording is 198.3 s long for a 110.9 s lap
— it starts 88.0 s before the car moves (`standing_start_ms` = 88083, so the app
already knows this). At **64.0 s into that pre-green period GT7's fuel jumps
49.984 → 100.000**: the 49.9 L is stale from the previous session, and the app
latched `fuel_start` 64 seconds before the tank was filled.

Then:

```python
fuel_used=max(self._fuel_lap_start - p.fuel_level, 0.0)
```

The clamp turns an impossible negative into a **fabricated zero**, in direct
violation of `CLAUDE.md` rule 3. The true lap-1 burn is 100.000 − 93.555 =
**6.445 L**, the highest of the race — standing start on a full tank, which is
precisely the number a fuel plan wants.

Two fixes, both needed: latch `fuel_start` at the green (the app has
`standing_start_ms`), and make a negative delta `None` plus a loud flag rather
than 0.0. A negative fuel delta without a refuel is never a real value.

### 3.3 There is no way to record a wear reading during a race

`set_lap_wear` has exactly one caller — `_on_lap_changed`, driven by
`practice.rows()`. `race_screen.py` mentions wear once, in a comment about ink.

So during 37 minutes with the gauge on screen the whole time, **all 20 race laps
have `wear_fl/fr/rl/rr` NULL**, and the race — the only session run at true race
pace, race fuel and race traffic — contributes nothing to the wear model. The
model is fitted entirely on practice, which §1.2 shows disagreeing with the race
by 17%.

Related: the `wear_predictions` table exists in `pitcrew.db` with one row from a
practice session on 17 Aug, and **no code in the tree references it at all** —
not `schema.py`, not the store. It is orphaned from an earlier version. The
gauge-prompt loop it was built for does not exist in the current package.

### 3.4 The live engineer and the strategy sheet use different fuel numbers

At the end of lap 7 the app said *"Burning 8% under plan."* Measured burn through
lap 7 was 6.114 L/lap. Against the three plan numbers:

| plan figure | where it lives | delta |
|---|---|---|
| 6.214 | `strategies.plan_json` assumptions (costed) | −1.6% |
| 6.665 | live engineer | **−8.3%** |
| 6.732 | allocated | −9.2% |

The call was computed against 6.665 while the approved strategy was costed at
6.214. This is the same three-number split recorded in the 17 Aug detector audit
and it was still live in this race. Race mean was **6.068 L/lap** (sd 0.171,
n=18) against 6.214 costed — 2.4% rich.

### 3.5 The warm-up call is 2–3 laps late

*"Tyres cold. About 3 laps to come up."* at the end of lap 1 — implying lap 4.
*"Tyres are up to temperature"* did not arrive until the **end of lap 8**.

The telemetry plateaus at lap 5–6 (RL: 73.5, 80.5, 82.0, 82.6, 83.1, 83.8, 84.0,
83.7 — within 1 °C of plateau by lap 4). By lap 8 the tyre was already 48% worn.
On a 12-lap stint the "you can push" moment arrived with a third of the stint
left. The forward estimate was better than the confirmation.

### 3.6 Pit loss has no agreed definition

The event declares `pit_loss_secs = 20.0`, source "declared". The video and UDP
give three different true numbers depending on what is meant:

- pit-lane transit only: **16.2 s**
- transit + dead time: **22.4 s**
- total lap-13 delta with a 28 L fill: **50.9 s**

`CLAUDE.md` §5.4 wants pit loss as a track constant with fuel as the only
variable, which makes **22.4 s** the right figure — 2.4 s worse than declared.
Whichever is chosen, the definition should be written next to the field.

---

## 4. UDP capture: the architectural gap

`CLAUDE.md` §6 asks for the raw stream persisted during a session, then
aggregated, so that re-aggregating after a bug fix is one evening rather than
re-running every test.

That is not what happens. All **405** files in `captures/` are exactly 3890
bytes — a 10-packet connection self-test each. **None is a session recording.**
What survives a session is `lap_frames`: a decoded, fixed field set of ~35
channels.

Two consequences:

1. Any `C`-format channel not in that field set is gone forever — clutch, boost,
   suggested gear, energy recovery, filtered pedals, per-wheel torque vectors.
   Adding a channel to the aggregator cannot be applied to any session already
   recorded.
2. **The "is there a hidden wear channel?" question cannot be asked.**
   `CLAUDE.md` §3.3 states flatly that no wear channel exists, and the wear model
   is the app's largest source of error. I now have a 1079-sample ground-truth
   wear curve for this race — the exact thing needed to test unused packet
   offsets for correlation against it — and no raw packets from the race to test
   against. If the raw stream had been kept, that test would be an hour's work.

Recommend persisting the raw decrypted stream per session alongside `lap_frames`,
and re-running this video-derived curve against it at the next race.

---

## 5. Recommended actions, highest return first

1. **Re-anchor the wear model on the video-measured rate**: 5.85 %/lap worst
   corner, RS, 2x, this car and circuit. Label it `measured-from-video-gauge`
   with its ±4% read resolution — it is a different and better source than a
   driver gauge entry and should not be blended silently into one.
2. **Persist the raw decrypted UDP stream per session.** Everything in §4
   depends on it, and it is the cheapest change here.
3. **Fix lap 1's fuel** — latch at the green, null the negative delta, and
   recover the 6.445 L standing-start burn.
4. **Add a wear-gauge entry to the race screen**, or the race will keep
   contributing nothing to the model it most needs to correct.
5. **Reconcile the three fuel-per-lap numbers** to one, at one source.
6. **Read position at the line**, not from the packet that closes the lap; then
   find the second source of staleness around the stop.
7. **Test the temperature-share hypothesis** (§1.3) against the next race's
   video before building anything on it. If it holds on a second car and
   circuit, one gauge reading yields all four corners.
8. **Move the warm-up confirmation onto the plateau**, which the telemetry shows
   2–3 laps before the call currently fires.
