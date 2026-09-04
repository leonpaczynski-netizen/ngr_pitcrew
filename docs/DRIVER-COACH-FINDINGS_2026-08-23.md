# The driver coach — what can be built honestly, and what cannot

**Written 23 Aug 2026** from a 13-agent adversarial design pass: three ground-truth
readers, three independent coach designs, and critics on each. **Eleven of thirteen
agents finished**; the evidence critic on the practice-loop design and the synthesis
agent both died on a usage limit, so the practice-loop design carries one critic
instead of two and this synthesis is written by hand.

**The headline: the coach that survives is much smaller than the one that was
designed, and the most valuable thing the exercise produced is the refusal list.**
Every critic, independently, named the refusals as the strongest part of the design
they were attacking.

---

## 1. The premise I gave the agents was wrong, and they refuted it

I seeded the exercise with the post-incident step-down — *"32.6 s of spins plus ~21 s
of permanent step-down, about 53 seconds in one race, entirely driver-side"* — and
told the loss analyst to verify rather than assume. **It does not survive.**

| Test | Result |
|---|---|
| Pooled within-session regression, n=135 | step **+0.430 s/lap, t = +1.84** — not significant |
| Same regression, Yas removed | **+0.093 s/lap, t = +0.40 — zero** |
| Bidirectional event study (the decisive one) | pace in the 6 laps **before** an incident vs the 6 **after**: difference **+0.11%, t = +0.52** |
| The Yas case against its own control | the "baseline" 117.52 was **1.51 s faster than his own Yas practice median** — a two-lap peak never held for more than two laps anywhere on file |

**Pace before an incident and after it are the same.** The only offset that moves is
+1: one cautious lap immediately after, +0.66 s, which is rational rather than a lost
session. The honest Yas number is ~16 s below *sustainable* pace, not 21 s below an
achieved level, and it rests on **n=2 pre-incident laps in one race**.

> **This corroborates the car-affinity finding from the same day** — the step-down is
> one car at one circuit, not a driver trait. See
> `ENGINEER-BRAIN-IMPLEMENTATION_2026-08-23.md` §2.1.

**A second standing claim also fell.** Two permutation tests over 100k shuffles:
adjacent-pair p = 0.47, gap-dispersion p = 0.82. **Incidents are indistinguishable
from a memoryless Poisson process at ~8.8% per lap.** The "incidents are
anti-clustered" note is withdrawn — and the design consequence is severe: **you cannot
predict the next incident from the last one.**

---

## 2. The corrected loss ranking

Reference **R25** = the 25th percentile of that race's own clean laps — a pace he
demonstrably held on a quarter of the laps in that very race.

| Rank | Bucket | s/race | Range | Coachable? |
|---|---|---:|---|---|
| 1 | **Inconsistency** (clean-lap scatter) | 12.3 | 9.2 – 17.9 | ⚠️ **Largely an artefact — see below** |
| 2 | **Incidents** | **10.8** | **0 – 37.7** | ✅ **Yes — 12× the noise floor** |
| 3 | Race lap 1 | 3.6 | 0 – 7.0 | Partly; a pre-race brief, never a live call |
| 4 | Run warm-up (laps 2–4) | ~1.5 | — | Marginal |
| — | Post-incident step-down | **not established** | — | ❌ §1 |
| — | Minor off-tracks < 1.5 s | **0.0** | — | ❌ costs nothing |
| — | Race-day nerves | **0.0** | — | ❌ does not exist |

```
  s44 Yas/Shelby   incidents 37.7  scatter 10.7  lap1 1.8  = 50.2 s
  s53 Monza/RSR    incidents  6.8  scatter 17.9  lap1 7.0  = 31.7 s
  s52 Monza/RSR    incidents  9.3  scatter 13.8  lap1 0.0  = 23.1 s
  s49 Watkins/Hur  incidents  0.0  scatter  9.2  lap1 6.4  = 15.6 s   (won it)
  s58 Monza/RSR    incidents  0.0  scatter 10.1  lap1 2.8  = 12.9 s   (won it)
```

**The two clean races are the two he won, and 100% of the gap between his worst race
and his best is incidents.**

> ⚠️ **The evidence critic killed the scatter bucket as recoverable time, and it is
> right.** Summing positive deviations from a p25 of a noisy sample produces a large
> number **even for a driver with zero real inconsistency** — simulated at his own σ it
> reproduces most of the bucket. Scatter is a *state*, not a pot of recoverable
> seconds. Report it; never bank it.

**Three further findings that constrain any consistency work:**

- **It is not race pressure.** Median σ: race 0.951 s, practice 0.799 s. Race pace vs
  practice pace is +0.06 s at Monza and **−0.89 s at Watkins**.
- **It is not knowable early.** Scatter of the first 5 clean laps vs the rest,
  r = **−0.246**. **This kills "today is a scrappy day, dial it back" outright.**
- **It is not the same state as incidents.** Correlation between a session's 2σ% and
  its incident rate: **r = +0.030**. Consistency and crashes are two separate problems.
- **Only 21.8% of lap-time variance is explained by any whole-lap channel** — minimum
  speed carry, the surviving channel. Brake time adds 7.3%. **78% is unexplained**, and
  top speed, throttle application and steering activity are all non-significant, which
  rules out both drag and "he is over-driving the wheel."

---

## 3. The speakable set — everything that survived both critics

| Output | Where | Floor |
|---|---|---|
| **Incident ledger** — count, cost, signal, per session and pooled | post-session | **~12×**. Median 12.7 s against a ~1.0 s lap σ. No corner indexing, so immune to `lap_distance_m`; no per-corner comparison, so immune to the noise floor |
| **One incident described** — arc position, min speed, yaw, brake, gear, per-wheel surface at the moment | post-session | transcription of a single event; no floor to clear. Locator error median **6.6 m** |
| **Lap-1 cost, pooled across races** | pre-race brief | +9.3 / +7.0 / +6.4 / +2.8 / +1.8 s, mean **5.5 s**, every race without exception |
| **Warm-up cost** — laps 2/3/4 at +0.54% / +0.59% / +0.25% | pre-run note | pooled over 21 runs; gone by lap 5 |
| **Session scatter as a state**, against his own 0.28–1.84 range | post-session | reported, never banked as recoverable |
| **Top-speed / power-loss check** | **post-session only** | 10σ on a single lap. **The only output that takes blame off him** |

**That is the coach.** It is a post-session document plus one pre-race brief. There is
no live corner coaching in it because none of it clears the floor.

---

## 4. The refusal list — the most valuable artefact of the exercise

**Every item is backed by a measurement the agents took themselves.**

| Never say | The measurement that forbids it |
|---|---|
| "Brake ten metres later at Turn 4" | `brake_point_m` 2σ = 14–37 m, worst corner 142 m |
| "You lost a tenth in sector X" | smallest honestly speakable sector delta **0.155–0.197 s** |
| "Sector X is your recurring weak spot" | cross-session residual sector correlation **r = −0.091** |
| "Ease off, you're on the edge" | **no incident precursor exists** — n=32 incident laps with a clean lap before, best precursor **z = +0.35, AUC ≈ 0.60**, at both lap and 150 m scale |
| "Your consistency improved this week" | the consistency statistic has **38% error on itself** between two 10-lap blocks |
| "That incident put you off your pace — here's how to reset" | §1. Pace before and after differ by +0.11%, t = +0.52 |
| "Today is a scrappy day, dial it back" | **r = −0.246** — it is not knowable early |
| "Tidy up your track limits" | **256 of 382 laps** carry non-zero off-track; clean laps at 0–1.5 s off-track cost **+0.10 to +0.16%**, i.e. nothing |
| "Your line through the esses is costing you" | a lap **0.41 s off** the reference deviates **1.04 m** — inside the 1.55–2.34 m lateral 2σ |
| "Your minimum speed at turn three is down four" | ⛔ **the smuggled per-corner call.** Below its own floor on the app's own certified rows — and `corner_models` has no track map, so "turn three" is not a name the app can honestly use |
| "Rear-left again — a front has never been worst" | ⛔ **refuted by the table.** Over 54 laps with wear: RL worst 37, **FL worst 14**, RR 3. FL is worst on all three Yas readings |

---

## 5. ⭐ The exercise found live defects in the shipped app

**This is the part I did not expect, and it is worth more than the coach.**

| Defect | Evidence |
|---|---|
| 🔴 **The app ships per-corner coaching that is below the floor right now.** `pitcrew/race/qualifying.py:530–548` emits mid-lap delta calls quoting tenths against a **1.3–2.6 s sector noise floor**. Both evidence critics independently said withdraw it | two critics, agreeing |
| 🔴 **The shift beep's root cause is identified.** `voice.py:538` checks `_yield_to_priority` only **between segments**, after a blocking `stream.write`. All 525 clips in the voice pack exceed the beep's `PRIORITY_WAIT_S = 0.4 s` deadline — **median clip 1.88 s** — so the beep's deadline expires inside a clip roughly **79%** of the time | this is the 7 drops in one evening seen in today's log |
| 🟡 **The duplicated final-lap `lap_time_ms` is confirmed independently.** Sessions 32, 38, 39, 40 all end in a 181–266 frame tail fragment carrying the previous lap's time — and those phantoms nearly triggered a false power-loss call | matches the task already raised today |
| 🟡 **`wear_source` is incoherent.** 10 laps with `wear_source='driver'` have **NULL wear values**; 20 laps carry real wear with **NULL source** | a source with no number, and a number with no source |
| 🟡 **`corner_models` cannot name a corner.** All 5 rows are `source='auto-segment'`; Monza's `model_id` disagrees with its `circuit_key` | no track map exists |
| 🟡 **`radio` has 0 rows.** Nothing the app has ever said to him is on record, so no coaching output can be audited against what happened next | all three critics flagged it |
| 🟡 **The short-shift drill already exists as a setting** — `settings.py: beep_short_shift_drop = 500.0` — and the practice-loop design proposed building it | |
| 🟡 **`tools/where_the_time_went.py` does not do what its name says.** It is a v1.70→v1.71 physics-delta tool with `EVENT = 1` hard-coded; it cannot see incidents, scatter or sessions | |

---

## 6. Build order

| # | Work | Why first |
|---|---|---|
| 1 | **Withdraw the quali mid-lap delta calls** (`qualifying.py:530–548`) | a shipped output that is below the floor. Deleting it is the highest-value line of code in this document |
| 2 | **Write every call into `radio`** via the existing `store.log_radio` | the table and writer exist; only the caller is missing. Without it nothing is auditable |
| 3 | **The incident ledger**, post-session | the one bucket that clears every constraint |
| 4 | **The spatial arc spine** — a distance axis from `pos_x`/`pos_z` | retires the `lap_distance_m` defect at zero capture cost, and the export's corner aggregates want it anyway |
| 5 | **Incident description** — one located event with its channels | transcription, no floor to clear |
| 6 | **Lap-1 and warm-up notes** in the pre-race brief | pooled, cheap, real |
| 7 | **Power-loss check, offline only** | takes blame off him. **Not live** — §7 |

**Reconcile the incident count before shipping 3.** The loss analyst reports 33 laps
/ 520 s; the evidence critic re-derived **30 laps / 479.4 s** using the repo's own
`incidents.py`, and attributes the gap to lap-1 laps passing the rule for structural
reasons (grid crawl). **Exclude lap 1 and re-count.**

---

## 7. What was rejected, and why

- **A live coach, almost entirely.** The live design scored 4 and 5. Its power-loss
  call fires four times rather than once with no session latch, its sole true positive
  is measured on two spin laps, it has no tow discriminator against a running-maximum
  reference, and *"Armed. Nothing to report"* converts structural muteness into an
  affirmative all-clear — the exact failure the frozen haptics meter taught. **What
  survives live is what already ships**: the incident call at `race/calls.py:1236`.
- **Every video output.** `video_path` is NULL on **51 of 51 sessions**. One video
  exists on the machine — 48 seconds, in VR. The wear reader is pinned to a single
  flat-screen OBS geometry; in PSVR2 the gauge bars are 18–20 px and one pixel is
  **5.6% of tyre life**. Video is not a second telemetry system yet; it is one
  calibrated instrument with no material.
- **Cross-session incident clustering as a headline.** p = 0.020/0.035 against a
  correct null, locator error up to 38.5 m against a ±50 m window, and it accrues
  ~1.2 located incidents per race — **a season to settle**.
- **The A/B practice drill as designed.** Its sizing assumed 6 clean laps per arm; his
  **median practice session is 3 clean laps total**, and only 12 of 44 reach 6. It can
  measure a fuel effect in 3 laps each way and can **never** measure an incident-rate
  effect — halving 8.8% needs 495 laps per arm.
- **Consistency coaching in any form.** §2.

---

*Written 23 Aug 2026 · 13 agents, 11 completed, 1.6M subagent tokens, 320 tool calls*
*My seeding premise was refuted by the agents I gave it to, which is the system working.*
*The coach that survives is a post-session document. The refusal list is the deliverable.*
*And the exercise found a live below-the-floor output shipping in the app today.*
