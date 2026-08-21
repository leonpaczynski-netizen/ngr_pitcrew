# v1.71 — where the lap time went, and what happened to braking

**Measured 21 Aug 2026** from `data/pitcrew.db`, event 1 (Porsche 911 RSR '17,
Monza Full, Racing Hard). Addendum to `_inbox/17-v1.71-measured-results.md`,
which recorded pace as `[UNMEASURED]` and asked for a session with the run modes
interleaved. **This does not measure pace either.** It decomposes the lap-time
delta by *where on the lap it occurs*, which is a different and answerable
question — and it settles two driver hypotheses.

**Method.** The lap is cut into 100 m distance bins. Each lap's speed trace is
read into them and the per-bin time difference computed as `d/v_post − d/v_pre`;
summed it reconstructs the lap-time delta, separated it says which hypothesis
owns it. **Bins are classified by what the car was doing using the pre-patch
laps only**, so the label cannot be moved by the change being measured.

14 clean pre-patch practice laps against 11 post-patch, same car, same circuit,
same compound.

---

## 1. ✅ The loss is on the straights, not in the corners

Reconstructed lap-time delta **+2.72 s**, against a measured median gap of
109.48 → 111.86 s.

| What the car was doing | Distance | Time lost | Share |
|---|---|---|---|
| **Flat out, straight** (>95% throttle, <5° steering) | 3.60 km | **+1.86 s** | **68.3%** |
| Flat out, turning (>95% throttle, ≥5°) | 0.90 km | +0.67 s | 24.7% |
| Part throttle or braking | 1.30 km | +0.19 s | 7.0% |

| Speed band | Time lost | Share |
|---|---|---|
| **Above 220 km/h** | **+1.43 s** | **52.6%** |
| 140–220 km/h | +0.80 s | 29.4% |
| Below 140 km/h | +0.49 s | 17.9% |

**93% of the loss is at full throttle and only 7% under braking or part
throttle.** A grip loss would land in the braking and turning bins. It does not.
This is the signature of increased resistance, and it corroborates `17` §2's
top-speed result — 274.9 km/h against a pre-patch range of 275.6–282.1 — through
an independent route.

> ⚠️ **One part this does not explain.** Speeds are down in the slow corners too:
> 70.3 → 67.5 km/h in the 900 m bin, about 4%. **Aerodynamic drag cannot do
> that** — it scales with v². Rolling resistance can, and so can a driver still
> adapting. The ~18% of the loss below 140 km/h is a separate component and this
> run cannot attribute it.

**Driver hypothesis — *"the slower laps come from the increase in rolling
resistance and lower top speed"* — supported**, for the 82% of the loss above
140 km/h.

---

## 2. ✅ He braked 27 m later, and the tyre holds better under braking

Two questions that must not be answered with one number: **what he did**, which
was his own experiment, and **what the tyre did**, which is the game.

Braking events found as contiguous runs of >20% brake pressure, matched across
laps by where on the lap they start. Six zones had enough laps on both sides.

| Zone | Brake → apex (m) | Apex km/h | Trail-brake % | **Min slip under brake** |
|---|---|---|---|---|
| 750 | 208 → 165 **(−43)** | 65.1 → 61.8 | 30.5 → 33.8 | 0.8469 → 0.8614 **(+0.0145)** |
| 1750 | 166 → 136 **(−29)** | 92.5 → 87.8 | 25.5 → 25.1 | 0.8448 → 0.8664 **(+0.0215)** |
| 2250 | 456 → 430 **(−26)** | 128.8 → 126.7 | 51.6 → 57.0 | 0.9378 → 0.9690 **(+0.0312)** |
| 2750 | 105 → 85 **(−21)** | 128.8 → 128.2 | 48.1 → 48.4 | 0.9264 → 0.9565 **(+0.0300)** |
| 3750 | 153 → 138 **(−15)** | 131.9 → 120.7 | 29.2 → 40.6 | 0.8465 → 0.8751 **(+0.0286)** |
| 4750 | 196 → 167 **(−28)** | 131.7 → 124.0 | 33.1 → 40.8 | 0.8681 → 0.8860 **(+0.0178)** |

**Brake point: median −27 m.** The driver reported *"about 20 m or so closer to
the apex"* before this was run. Measured, it is 27, in every zone.
*This is his experiment, not the patch. Recorded as a driver input.*

**Minimum slip under brake: 0.8575 → 0.8805, and it rose in all six zones.**
`slip_*` is wheel surface speed over car speed, so under brake the minimum is
how far below rolling the wheels get. **They slide less.** This is the braking
side of `17` §1, which found driven-wheel slip under power down 40–60%: the same
change, the same direction, the other axis of the friction circle.

### The confound, checked and closed

A softer brake would raise slip for reasons that have nothing to do with the
patch. **Peak brake pressure is unchanged: median 98.9% → 100.0%.**

**Four of six zones are at 100% brake on both sides**, and the slip rose in every
one of them:

| Zone at 100% brake both sides | Min slip |
|---|---|
| 750 | 0.8469 → 0.8614 |
| 1750 | 0.8448 → 0.8664 |
| 3750 | 0.8465 → 0.8751 |

**At identical, maximal brake input the wheels slide less.** That is a property
of the game, not of the driver.

**Driver hypothesis — *"the new model will reward later braking with more trail
braking"* — supported.** Trail braking rose in four of six zones, most at 3750 m
(29.2 → 40.6%) and 4750 m (33.1 → 40.8%).

> ⚠️ **The reward has not arrived yet.** Apex speed is **down in all six zones**,
> −0.6 to −11.3 km/h. Braking later has not so far produced more apex speed.
> Partly confounded: lower entry speed from §1 feeds straight into apex speed, so
> some of this is the straight-line loss arriving at the corner rather than a
> braking result. **3750 m is the one to look at** — the largest trail-brake
> increase and the largest apex-speed loss, which is what overdoing it looks
> like.

---

## 3. What this does not establish

- **Not pace.** `17` §7 still stands: pace on v1.71 needs a session run after
  the physics stop feeling new. This says where a delta sits, not what the car
  is capable of.
- **Not cornering grip.** Both findings are longitudinal. Lateral grip is
  untouched by either measurement.
- **Not rolling resistance versus drag.** Both act on terminal speed and neither
  is directly observable here — `17` §2 says the same.
- **The sub-140 km/h losses are unattributed.** See the caveat in §1.

## 4. Driver evidence recorded alongside

- *"Wheel felt heaps more realistic."* 1.71 adjusted force feedback, understeer
  vibration and Fanatec Auto Setup, and `08`, `07` and `04` all warn that on an
  18 Nm base an FFB change reads exactly like a grip change. **It was felt, and
  felt as an improvement — so it is not masking a grip loss, and it is not
  settings drift.** Job 7a can be closed on the driver's report.
- *"I don't believe I was off track that much."* **Correct, and the app agrees.**
  `ON_TRACK_SURFACES` already counts kerb (`C`) as on-track; what registers is
  grass, in small amounts. By the app's own threshold — 2.5 s with two or more
  wheels off — only **1 of 11** post-patch laps is flagged, and 5 of 190
  pre-patch. An earlier pass excluded any lap with *any* grass contact, which was
  far stricter than the app's rule and threw away 9 of 11 laps. **That was an
  analysis error, not a detector error.**

---

*Tools: `tools/where_the_time_went.py`, `tools/braking_change.py`. Both take the
version pair as their comparison and will re-run against the next patch.*
