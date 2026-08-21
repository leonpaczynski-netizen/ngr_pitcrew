> **Provenance note, added 21 Aug 2026.** This document was **not** in the
> Project export. It was loose in `~/Downloads`, and the export's own `06` is
> `06-car-building-and-pp.md` — so its numbering belongs to a different set and
> its origin could not be established.
>
> **Kept, and moved out of `_inbox/`.** Kept because it is the design rationale
> behind `pitcrew/strategy/` and nothing else in the repository records it: the
> v1→v2 amendment table listing six recommendations that "did not survive
> contact with the code", the measurement that settled enumeration against
> dynamic programming (6.7 M DP states versus 3,905 candidates scored in 106 ms),
> and the decision that the tyre gauge is primary evidence and the lap-time fit
> only corroboration. Losing that would mean re-deriving it or, worse,
> re-litigating it.
>
> Moved because `_inbox/` is the faithful record of what the Project actually
> contained, and a file that was never in it does not belong there.
>
> **Written against v1.70.** Its mechanism is version-independent; its numbers
> are not.

---

# Race strategy — how it should be calculated

**NGR Pit Crew · target design and evidence base · 12 August 2026 · v2**

Companion to the Claude Code audit prompt (project doc `07`). That prompt tells Claude Code to establish how strategy is calculated *today*; this document is what it gets compared against.

> **v2, amended 12 August after the code audit** (`docs/STRATEGY_GAP_REGISTER_2026-08-12.md`). v1 was written without access to the repository and six of its recommendations did not survive contact with the code. All six are accepted here:
>
> | § | v1 said | v2 says | Why |
> |---|---|---|---|
> | 3.2 / 3.3 | Fit degradation from lap times, correcting for fuel | **Tyre gauge is primary**; the lap-time fit is corroboration | The app reads the driver's in-game wear gauge, which is anchored to GT7's own wear model. That sidesteps the `d − k_f·b` identification problem entirely and is already correct. Replacing it with a profile-likelihood fit would be a regression. |
> | 5 | Build a CRN scenario table | **Sequenced last.** Parameter uncertainty dominates and is currently total | CRN reduces *scenario* variance. It does nothing about a `wear_per_lap` that rests on one gauge reading from one stint. Sampling around a guess yields a confident interval around a guess. |
> | 3.6 | Dynamic programming as the primary engine | **Enumeration is correct at this size.** DP only for the stochastic extension | Measured: 6.7 M DP states against 3,905 enumerated candidates scored in 106 ms. |
> | 6.1 | `P(win) ∝` a product of three factors | **Lexicographic ordering, no product notation** | The factors are dependent, so the product understates the joint. The ordering was always the shippable part. |
> | 1.4 | "One consumer per console" is a design constraint | **Background only — already mitigated** | SimHub relays; this app never heartbeats the console. |
> | 8.6 | The caution card is the highest-value contingency | **Cut.** No caution card | GT7 exposes no caution signal and a private league has no marshalling system. The card has no trigger and cannot be built. |
>
> §11 item 3 (`k_f`, the fuel-weight coefficient) is demoted from foundation to corroboration as a direct consequence of the first row.

Scope decisions taken with the owner on 12 Aug:

| Decision | Value |
|---|---|
| Rival data | **Own car only.** No opponent positions or gaps exist. Strategy is a single-agent optimal-control problem, not a game. |
| Race conditions in scope | Mandatory pit stop / compound rules · fuel and tyre wear multipliers · dynamic weather · **damage** · **plan divergence (pace or fuel off plan)** |
| "Failsafe" means | (a) choose the plan that is **robust across the uncertainty**, not the one with the best point estimate; (b) **pre-compute contingency branches** so the in-race call is a lookup, not a fresh optimisation |
| Delivery | Audit first. No implementation until the plan is approved. |

---

## 0. The five findings that should drive the whole design

1. **GT7 gives you fuel exactly and tyre wear not at all.** Fuel level and tank capacity are real fields at 60 Hz. There is no tyre-wear, tyre-compound, weather, damage, pit-state or race-position field in *any* packet version (A / B / ~ / C). Everything except fuel is inferred or declared. The evidence bar for a fuel-driven decision and a degradation-driven decision must therefore differ by design, not by accident.

2. **Fuel load and tyre age are exactly collinear inside a stint**, so a regression that fits both recovers only the net slope `d − k_f·b`, never `d`. **This is why the tyre gauge, not a lap-time fit, must stay the primary source of wear state.** The gauge is anchored to GT7's own wear model and is immune to the confounding; a lap-time fit is not, and adopting one as primary would be a regression. The identification result still binds the *corroboration* channel — any lap-time-derived degradation figure must have a fixed fuel coefficient subtracted before it is fitted, or it will disagree with the gauge for reasons that have nothing to do with tyres.

3. **Optimal stint length is the Economic Order Quantity formula**, `n* = √(2·T_pit / d_total)`, and EOQ is famously flat: within ±15 % of `n*` you are within 1 % of optimal. A one-stop and a two-stop plan are routinely separated by well under a second across a full race — less than the uncertainty in the inputs. **An engine that reports only the argmin is close to useless.** It must report the cost curve and the size of the gap relative to parameter uncertainty.

4. **The refuel rate is a property of the event, not the car, and it is not readable.** Community measurement of GT7 pit stops implies roughly 7 L/s at Bathurst and Le Mans, and users report different effective rates per event ("Sardegna x6, Tokyo x3"). The project's existing governing principle — *"a 1 L/s refuel rate makes on-track fuel saving hugely valuable"* — rests on a number that must be **measured on the first stop of each event and cached**, not assumed. If the true NGR rate is 7 L/s rather than 1 L/s, the value of fuel saving falls by a factor of seven and the current strategy doctrine is wrong at the root. **Verifying this is the highest-value single measurement in the whole project.**

5. **Community evidence says a GT7 tyre change and refuel are serial, not parallel** — tyres are selected and fitted, then fuelling begins. If true, a tyre change is never "free" inside a fuel stop, which invalidates the intuition every ACC/iRacing-derived tool is built on.

   **The audit found the code models neither.** There is no tyre-change term at all: pit loss is a single number the driver types, so a tyre change is implicitly free or implicitly already inside that number, and which of the two is recorded nowhere — while the export declares `"pitLossSource": "measured-this-track"` unconditionally. That last part is the same class of provenance failure Phase 1 found in the setup path: a label asserting an evidence tier the value does not have. Decomposing `T_pit` (§3.4) and telling the truth about its provenance matters more than resolving serial-versus-parallel, and both fall out of the same measurement run.

---

## 1. What the telemetry actually gives you

Verified against four independent open-source implementations (Nenkai/PDTools, MacManley/gt7-udp, zetetos/gt-telemetry, snipem/gt7dashboard) and the GTPlanet reverse-engineering threads, August 2026.

### 1.1 Available, and trustworthy

| Quantity | Field | Notes |
|---|---|---|
| **Fuel level** | f32 @ 0x44, **litres** | 60 Hz. Sample at the lap-transition tick, not on a timer. |
| **Tank capacity** | f32 @ 0x48 | 100 L for effectively all cars, 5 L karts, 0 for EVs (guard the divide). |
| Lap count / laps in race | i16 @ 0x74 / 0x76 | `lap_count == 0` before the race starts — use as the reset trigger. |
| Last / best lap time | i32 ms @ 0x7C / 0x78 | **`−1` when unset.** A naive cast poisons every average. |
| **Current lap time** | i32 ms @ 0x15C | **Packet C only.** Before C you had to count ticks. |
| Tyre surface temp ×4 | f32 @ 0x60 | Surface only. No carcass, no inner/mid/outer, no pressure. |
| Wheel rotation ×4, tyre radius ×4 | f32 @ 0xA4 / 0xB4 | Together give slip ratio: `ω·r / v`. |
| Throttle / brake (post-assist) | u8 @ 0x91 / 0x92 | 0–255. |
| **Raw throttle / post-ABS brake** | u8 @ 0x13C / 0x13D | **Packet ~ and above.** Differencing against 0x91/0x92 gives *TCS and ABS intervention magnitude* — see §1.3. |
| Surface type ×4 | char @ 0x158 | **Packet C only.** Material (tarmac/kerb/grass/dirt/sand/snow) — **not wetness.** |
| World XYZ, velocity, quaternion, angular velocity | — | Track progress and pit-lane geometry are derived from these. |
| Flags bitfield | i16 @ 0x8E | on-track, paused, loading, turbo, rev-limiter, handbrake, lights, **ASM**, **TCS**. Bits 12–15 undocumented. |
| Gear ratios, calculated max speed, car code/category | — | Category string (`GR3`, `GR4`…) is packet C. |

### 1.2 Not available at all

Tyre wear · tyre compound fitted · tyre pressure · brake temperature · **weather, rain, track wetness, ambient or track temperature** · **damage state** · **live race position or any opponent data whatsoever** · penalties · pit-lane / pit-limiter state · the fuel-map setting.

Three traps worth naming explicitly, because each has produced a real bug in some public tool:

- **Race position.** The i16 at 0x84 is the *pre-race grid slot* and goes to `−1` at lights-out. At least one public library labels it `race_position`. It is not.
- **Water and oil temperature** are hardcoded constants (85 °C and 110 °C). They are not sensors. Do not let the field names mislead a data pipeline into treating them as observations.
- **Tyre radius is not a wear proxy.** No source documents it varying with tread depth; both libraries that expose it use it purely as a moment arm. It most plausibly varies with load and deflection. If the strategy engine anywhere treats radius drift as wear, that is a defect. (Cheap experiment: regress radius against lap number over a 20-lap stint at constant fuel-corrected pace; if the drift correlates with lateral G rather than lap number, it is load.)

### 1.3 Derivable, with the latency ordering that matters

| Quantity | Derivation | Latency | Trust |
|---|---|---|---|
| Fuel per lap | Δ tank level across the lap boundary | 1 lap | **High — measured** |
| Live burn rate | linear fit over a rolling ~10 s window | seconds | High |
| Slip ratio per corner | `ω·r / v` | sub-second | High |
| **TCS/ABS intervention** | `raw_input − post_assist_output` (packet ~/C) | **sub-second** | High |
| Sliding energy proxy | slip-ratio excursion count × lateral G, per corner, front-biased | per lap | Medium |
| Pit stop occurred | speed ≈ 0 ∧ on-track ∧ (fuel rising ∨ tyre temps collapsing) | seconds | High |
| Refuel rate (L/s) | `Δfuel / Δt` while stationary | first stop | High |
| Tyre change occurred | tyre temps reset cold then climb on the out-lap | out-lap | Medium |
| Rain onset | intervention magnitude ↑, then temps ↓, then fuel-corrected lap delta ↑ | sub-second → 1 lap | Medium |
| Track drying | monotone recovery of the corner-speed ceiling at matched track segment | several laps | Medium |
| Lap distance / track progress | project world XYZ onto the centreline | — | High |

**Design rule from this table:** every derived channel carries its own confidence and its own latency. A recommendation is only as fresh as its slowest load-bearing input.

### 1.4 Transport gotchas that bite in a race

- Heartbeat `C` to UDP 33739, receive on 33740, re-heartbeat every ~10 s (hard deadline ≈ 16 s). **Length-sniff the reply** (296 / 316 / 344 / 368) rather than assuming.
- **The packet format is latched by the first heartbeat the console receives**, so two tools heartbeating the same console means one wins and the other reads garbage. *Background only for this project* — SimHub relays and this app never heartbeats, so the risk is already designed out. Worth knowing if that architecture ever changes.
- Packet B is reported unavailable in Sport Mode and `~` unavailable in replays. **Keep an A-only degraded path** and prove it works before race day.
- Gate on the packet-id counter (accept only strictly increasing). It **resets on reconnect** — a stored id that is never zeroed deadlocks the stream permanently after one dropout.
- RPM is fractional in replays and integral live: a free live-vs-replay discriminator. Never mix replay and live laps in one model — replay brake traces are filtered.

---

## 2. GT7 mechanics the model must encode

| Mechanic | Best evidence | Confidence |
|---|---|---|
| Fuel and tyre multipliers | **Linear.** One measured lap at any multiplier gives every other. | High |
| Fuel map FM1–6 | **−4 % power, −8 % fuel per step.** Three independent tests agree on FM6 ≈ 0.63× FM1 consumption. **Lap-time cost per step is unpublished — learn it per car/track.** | Medium-high on fuel, unknown on lap time |
| Fuel map in telemetry | **Absent.** Follow gt7dashboard: anchor the *current* setting at 0 and present a **relative** ±N table. | Confirmed |
| Lift-and-coast | Optimal window 2–3 s before braking. "3 s L&C at FM1 ≈ no-coasting at FM3." Short-shifting ~10 mph early: −20 % fuel for ~0.5 s/lap. | Medium |
| Fuel weight | **No GT7-era controlled measurement exists.** 100 L ≈ 70–75 kg. Must be measured, not assumed. | **Unknown — measure** |
| Refuel rate | Event property, ~3–7 L/s observed. **Measure per event.** | Medium |
| Pit stop | Auto-driven, no limiter, no speeding penalty. Total pit-lane time ~30–36 s (Bathurst Gr.3), ~36–41 s (La Sarthe Gr.1), with a ~5 s spread driven by fuel volume. | Medium |
| Tyres/fuel serial | Community: **serial** — tyres then fuel. | **Measure** |
| Partial fill | Supported; the fill can be stopped mid-way. Fuel quantity is therefore a **decision variable, not a constant**. | High |
| Pit line penalties | 3–6 s for touching the white line on entry or exit. | High |
| Tyre wear model (post-1.49) | **Cliffs, not linear.** Past ~50 % wear, ≥1 s/lap. Driven by **lateral sliding, front-biased, on corner entry** — not by braking or traction. | High |
| Compound pace deltas | **No published numbers.** Folklore ~0.5–1.0 s/step. **Learn per car/track.** | Unknown |
| Weather | In-game radar only, no forecast, no telemetry exposure. Slicks in rain ≈ +49 s/lap at Spa. Wets vs inters: near-parity in light rain, wets 7–8 s/lap better in real rain. | Medium |
| Damage | Light damage self-repairs after ~60 s or in the pits; heavy needs a stop. GT7-specific pace costs unquantified. | **Low — treat as second-order but visible** |
| League rules | "Required Tyre Type" lists compounds that must *all* be used; combined with the no-mixing rule this forces a 4-tyre stop even with minimum stops = 0. Non-compliance is punished **post-race** (2-minute penalties observed). | High |

**Consequence:** a large fraction of the constants a strategy engine needs do not exist in any public source. The correct engineering response is not to hardcode folklore — it is to make every constant a **measured, provenance-tagged, per-event quantity with an explicit fallback**, exactly as Phase 1 did for setup data. A strategy plan built on a guessed refuel rate and a guessed compound delta is the strategy-side equivalent of the 108/119 mm ride height.

---

## 3. The model

### 3.1 Lap time

```
t_lap(l) = t0                     base pace, this car/track/driver
         + δ_c                    compound offset
         + f_c(a)                 tyre-age term, a = laps on this set
         + k_f · m_fuel(l)        fuel mass effect
         + e(l)                   track evolution
         + π(l)                   in-lap / out-lap penalties
         + w(W(l), c)             wetness term (§7)
         + ε_l                    noise
```

`ε` is **not Gaussian** — lap times have a fat right tail (mistakes, traffic, lifts) and essentially no left tail. Use a skewed-t likelihood, or at minimum a Gaussian core plus an incident mixture. σ_ε ≈ 0.2–0.4 s.

### 3.2 Why the tyre gauge is primary — and what the identification result still binds

Inside a stint, `l = l_stint_start + a` **exactly**. Regressing lap time on both tyre age and lap index with a free stint intercept is rank-deficient: you can identify only `d − k_f·b`. Adding stint fixed effects does not fix it. Every strategy tool that derives degradation from lap times is exposed to this, and most handle it badly.

**This project is not exposed to it, and should stay that way.** The app reads the driver's in-game wear gauge. That reading is anchored to GT7's own wear model — the same model that will actually decide when the tyre falls off — so it is not an estimate of wear at all, it is an observation of it. No fuel correction is required because no regression is involved.

> **Rule: the gauge is the primary source of wear state. Do not replace it with a lap-time fit.**

The identification result now binds one narrower thing: the **corroboration** channel in §3.3. Any degradation figure derived from lap times must have a fixed fuel coefficient subtracted before fitting —

```
t̃(l) = t_lap(l) − k_f · (m_fuel(l) − m_ref)
d̂_c  = RobustSlope(a, t̃)
```

— or it will drift away from the gauge for reasons that have nothing to do with tyres, and the disagreement check in §3.3 will fire on an artefact.

`k_f` is a vehicle property. Port it with the dimensionless form: `κ = k_f · m_total / t_lap ≈ 0.27` (a 1 % mass increase costs ~0.27 % lap time), so `k_f = κ · t_lap / m_total`. Calibrating `κ` for GT7 (§11 item 3) is **corroboration work, not foundation work** — nothing in the primary path waits on it.

### 3.3 Degradation — gauge primary, lap times corroborating

Two different quantities, from two different sources. Conflating them is the mistake to avoid:

| Quantity | Source | Status |
|---|---|---|
| **Wear state** — % worn, per corner, now | The in-game gauge, driver-read | **Observed.** Anchored to GT7's own model. |
| **Wear cost** — seconds per lap at that wear state | Fuel-corrected lap-time fit over the stint | **Estimated**, and subject to §3.2. |

The gauge tells you *where the tyre is*. It does not tell you what that costs in lap time, and the optimiser needs both. So the lap-time fit does not disappear — it is demoted from "the source of degradation" to "the wear-to-seconds mapping, plus a cross-check on the gauge".

**The cliff.** Post-1.49 GT7 degrades hard past ~50 % wear, so the mapping is **linear + cliff**, not linear:

```
f_c(wear) = d_c·wear + d_cliff·(wear − wear*)⁺
```

Fit the breakpoint by profile likelihood — grid it, robust-fit at each, take the minimiser. Never gradient-descend a breakpoint. A purely linear mapping systematically recommends stints that are too long, and that error lands on the expensive side of the 21:1 asymmetry (§6.2).

**Precision limit for the cost channel — put this number in the UI.** For `n` consecutive clean laps:

```
σ_d̂ = σ_ε · √( 12 / (n·(n²−1)) )
```

| n laps | σ_d̂ at σ_ε = 0.3 s |
|---|---|
| 5 | 0.075 s/lap |
| 8 | 0.046 s/lap |
| 12 | 0.025 s/lap |
| 20 | 0.012 s/lap |

Typical degradation is 0.03–0.15 s/lap, so **after 8 clean laps the 1σ uncertainty on the cost is comparable to a hard tyre's entire degradation rate.** Shrink toward the practice prior rather than trusting a short stint:

```
d̂_post = (σ_d̂⁻² · d̂ + σ₀⁻² · μ₀) / (σ_d̂⁻² + σ₀⁻²)
```

At σ₀ = 0.03 the *data* weight is 15 % at n = 6, 42 % at n = 10, 59 % at n = 12. Note this uncertainty attaches to the **cost mapping only** — the wear state itself carries the gauge's own (much smaller, and quite different) error, which is a read-resolution problem rather than a sampling one. Report them separately; they fail in different ways.

**The disagreement check.** When the gauge says the tyre is at 40 % and the fuel-corrected lap-time fit implies something far off the mapping, one of three things is true: the read was wrong, the mapping is wrong for this car/track, or the driver's pace changed for an unrelated reason. Surface it as a query rather than silently preferring either source. This check is also what catches the export defect the audit found — a stale or mislabelled wear figure reaching the export shows up here first.

**GT7-specific enrichment.** Because 1.49 made wear a function of lateral sliding, front-biased, on corner entry, the sliding-energy proxy from §1.3 is a defensible *leading indicator* — it moves before either the gauge is re-read or the lap times reveal anything. Use it as a covariate and to prompt a gauge read, never as a substitute for one, and mark it derived.

### 3.4 Pit loss — decompose it, never a single constant

```
T_pit = Δ_lane                      auto-driven transit, track constant
      + t_tyres                     tyre change  ┐ serial in GT7 (verify)
      + V_added / ṙ                 refuel       ┘
      + Δ_in + Δ_out                in-lap slow-down, out-lap warm-up
      + p_penalty                   white-line risk
```

Three structural points:

- **`V_added` is a decision variable.** Filling to full by default leaves seconds on the table at every stop. The optimiser must choose the litres.
- **Serial vs parallel changes the answer.** If serial, `T_pit` is a *sum*; if parallel, `t_stat = max(t_tyres, V/ṙ)`. Modelling a max as a sum (or vice versa) is a material error. Measure it, then encode which one is true, with provenance.
- **A single typed `pit_loss_secs` cannot carry this.** The audit found pit loss is one driver-entered number with no tyre-change term, exported with `"pitLossSource": "measured-this-track"` regardless of where it came from. Whatever the decomposition ends up being, the provenance label must be derived from the fields that are actually populated — a constant string asserting an evidence tier is the strategy-side version of the Phase 1 provenance lies.

### 3.5 Total race time and stint splitting

```
J(π) = Σ_s [ n_s·(t0 + δ_cs) + Σ_{i<n_s} f_cs(i) ] + Σ_j T_pit(j) + k_f·Σ_l m_fuel(l)
```

Unlike F1, **GT7 refuels, so the fuel term does not drop out** — start load and fill sizes are strategy-dependent and must stay inside the objective.

Analytic seeds (use them to sanity-check the optimiser, not to replace it):

- Single compound, linear degradation, fuel and tyres both binding:
  `n* = √( 2·T_fix / (d + k_f·b) )`
- Multi-compound optimum equalises **marginal** lap time at the end of every stint:
  `t_cs + d_cs·n_s = λ  ∀s`, with `λ = (L + Σ t_cs/d_cs) / Σ 1/d_cs`

**And then the flatness result.** `C(n)/C(n*) = ½(n*/n + n/n*)`. A worked F1-scale case has 1-stop and 2-stop separated by **0.34 s over a full race**. That is smaller than the uncertainty in `d̂` after 8 laps. This is why real strategy calls are knife-edge and why tie-breakers — legality, safety margin, contingency exposure, driver comfort — legitimately dominate.

> **Product requirement, not a nicety: report the cost curve over candidate plans and the paired uncertainty of the differences. If the top two plans are inside the noise, say so and pick on the failsafe criteria, not on the argmin.**

### 3.6 The optimiser: enumeration now, DP only if it earns its place

**v2 correction.** v1 argued for dynamic programming as the primary engine. At this problem size that is over-engineering: the audit measured **6.7 M DP states against 3,905 enumerated candidates scored in 106 ms**. Exhaustive enumeration over the candidate space is exact, trivially inspectable, and already fast enough — and an inspectable engine is worth a great deal when the whole product thesis is explainability.

**Keep enumeration as the engine.** Build the DP below only when the stochastic extension is actually being built — because that is the one thing enumeration genuinely cannot do — and only after saying so explicitly. Do not build it speculatively.

The formulation, for when that day comes. DP is exact, handles cliffs natively with zero extra machinery, and its value function is *exactly* the object needed for closed-loop replanning.

```
stage   l = 1..L
state   x = (compound c, tyre age a, compounds_used bitmask U, fuel level F)
action  u ∈ {stay} ∪ {pit(c', litres v)}
cost    g(x, stay)         = t_lap(x, l)
        g(x, pit(c', v))   = t_lap(x, l) + T_pit(v, c')
terminal V_{L+1}(x) = 0 if legality satisfied (mandatory stops, required compounds,
                                               fuel ≥ reserve throughout)
                      +∞ otherwise
V_l(x) = min_u [ g(x,u) + V_{l+1}(F(x,u)) ]
```

The `+∞` terminal is how the mandatory-compound rule is enforced — cleanly, without a post-hoc filter that can be bypassed. Fuel must be discretised (litre or 2-litre bins is ample).

Stochastic extension: augment with a race-phase flag and a per-lap hazard for rain onset and damage. This turns the output from an open-loop plan into a **closed-loop policy**, which is what correctly values "stay out one more lap because the rain hazard is rising" — something no deterministic optimiser will ever produce. This, and only this, is the case for building the DP at all.

Ignore MILP/MIQP entirely. The cliff model is not naturally MIQP-representable, so you would end up degrading the tyre model to please a solver you do not need — and enumeration already gives you the exact answer plus the full cost curve §3.5 requires, which is the more valuable output.

---

## 4. Legality and survivability gates — above the optimiser, not inside it

No score may override these. They are filters applied to the candidate set *before* anything is ranked.

| Gate | Rule |
|---|---|
| Mandatory stops | `stops ≥ event.min_stops` |
| Required compounds | every compound in `event.required_tyres` appears in some stint (GT7 forbids mixing front/rear, so each entry implies a full 4-tyre stop) |
| Minimum stint length | league rule if configured; otherwise ≥ 1 lap |
| Fuel floor | `fuel(l) ≥ reserve` for **every** lap under the *pessimistic* burn percentile, not the mean |
| Tank ceiling | `fill ≤ capacity − fuel_at_stop` |
| Executability | every stop lap is ≥ the current lap and reachable before its commitment point (§8.4) |
| Compound availability | only compounds the event actually offers |

A candidate that fails any gate is not scored, not shown, and not held in reserve. A plan that "wins on time but runs dry on lap 27 at the 90th-percentile burn rate" is not a plan.

**Reserve sizing is a real decision, not a constant.** Set the reserve from the residual variance of the burn-rate estimate over the remaining laps, plus one lap-equivalent of white-flag uncertainty in timed races. Report it.

---

## 5. Where the uncertainty comes from, and how to carry it

| Parameter | Distribution | Source |
|---|---|---|
| Lap-time noise ε | skewed-t, σ ≈ 0.3 s, right-skewed | practice sessions, per driver |
| Degradation `d_c` | posterior from §3.3 shrinkage | practice + live |
| Cliff onset `a*` | wide; profile-likelihood interval | practice, often unresolved |
| Fuel burn `b` | tight — measured | telemetry |
| Refuel rate `ṙ` | tight once measured, **wide before** | first stop of the event |
| Pit stationary time | log-logistic (right tail) | observed stops |
| Rain onset / intensity | scenario set with weights, or a 2-state Markov chain | driver-declared radar read |
| Damage / incident | per-lap hazard | driver history |
| Timed-race lap count | discrete, ±1 lap | white-flag logic |

### Parameter uncertainty first, scenario sampling later

**v2 correction, and it reorders the whole section.** v1 put a Common Random Numbers scenario table near the front of the build. The audit's objection is correct and decisive: **CRN reduces variance in the *scenario* noise, and does nothing about *parameter* uncertainty — which here is total.** `wear_per_lap` currently rests on a single gauge reading from a single stint. Monte Carlo around that produces a confident-looking interval around a guess, and a confident-looking interval around a guess is worse than an honest point estimate, because it launders the guess into something that looks like it has error bars.

This is the same argument §11 makes about optimisers — a better optimiser fed guessed constants is worth nothing — applied to v1's own §5. **Sequence scenario sampling last, after the §11 measurement programme has given the parameters real distributions.**

What to do in the meantime: report the **range implied by the parameter's own provenance**, not a sampled distribution. One gauge reading from one stint supports "somewhere between these two plans, we cannot separate them" — which is exactly the honest output §3.5's flatness result demands, and it needs no sampling machinery at all.

**When you do build sampling, CRN is not optional.** Given §3.5's flatness, candidate plans differ by less than the scenario noise, so evaluating each on its own draws makes the comparison meaningless.

> Pre-generate the entire scenario table **once**, fixed seed, shape `(N, L, channels)`. Evaluate every candidate against the same table. Analyse the **paired difference** `D = T_A − T_B`. Because the covariance is high, `Var(D)` collapses — often by 10–50×. This delivers variance reduction, determinism and vectorisation in one move, and it is what makes `σ_diff` in the switching rule (§8.4) a meaningful number.

Seed derivation must be content-based (`hash(race_id, lap, scenario_index)`), never a global RNG, or replay determinism is lost.

---

## 6. Failsafe — choosing the plan that maximises the chance of winning

### 6.1 What "probability of winning" can honestly mean here

With no opponent data, `P(win)` is **not computable** and any tool that claims it is fabricating a field model. Say so, and rank on a well-posed surrogate instead.

**v2 correction:** v1 expressed the surrogate as a product of three probabilities. Drop that notation — the factors are dependent (a plan that runs dry is also a plan that finishes late and takes an unplanned stop), so the product understates the joint and invites someone to compute it. The **lexicographic ordering** below was always the shippable part, and it needs no joint distribution at all:

1. **Feasibility probability first** — `P(plan survives all gates in §4 across the scenario set)`. A plan that fails in 8 % of scenarios is not comparable to one that fails in 0.5 %; it is worse, almost regardless of mean time.
2. **Then CVaR of total race time**, not the mean:
   `CVaR_α(T) = mean of the worst (1−α) fraction of scenario outcomes`, α = 0.8–0.9.
   Over a finite candidate set this is: evaluate, sort each plan's outcomes, average the tail. Trivial to implement, and it is the number that corresponds to "don't lose the race".
3. **Then minimax regret** as the tie-breaker when CVaR is inside the noise: `max over scenarios of [T(π,θ) − min_π' T(π',θ)]`. Directly interpretable as "how much could this plan leave on the table in the world where I chose wrong".
4. **Then mean race time**, last.

**Risk posture must be an explicit input.** Leading and defending → minimise CVaR. Behind and needing a result → maximise the *upper* tail, `P(T < T_target)`. A tool that always optimises the mean gives the wrong answer in both cases. Default to CVaR; expose the switch.

### 6.2 The asymmetries that should be hard-coded

These are not tuning parameters. They are structural facts about racing, and encoding them is most of what "failsafe" means.

| Asymmetry | Ratio | Design consequence |
|---|---|---|
| Stopping one lap early vs one lap late on dead tyres | **0.36 s vs 7.74 s ≈ 21:1** (measured, IndyCar) | Require far more evidence to *extend* a stint than to shorten one. `θ_extend >> θ_shorten`. |
| Running dry vs carrying spare fuel | unbounded vs `k_f·V` | The fuel floor is a hard gate; the reserve is sized from the pessimistic percentile. |
| Too late onto wets vs too early | unbounded (spin/crash, +49 s/lap on slicks in rain) vs ~10–30 s | Bias **early** to wets/inters. |
| Too early onto slicks vs too late | crash risk on the out-lap vs ~2–5 s/lap | Bias **late** back to slicks. |
| Missing a mandatory compound | post-race 2-minute penalty | Legality gate, never a scored term. |

### 6.3 Value of information — when to stop collecting practice data

Find the **switching boundary** `d*` at which the optimal plan flips from k to k+1 stops. Then:

- If `|d̂ − d*| > 2·σ_post`, more practice laps **cannot** change the call. Say "decided", stop gathering, and spend the running elsewhere.
- If `|d̂ − d*| < 1σ`, the call is genuinely live and more clean laps on that compound are the single most valuable thing the driver can do.

This is a directly actionable output for the practice programme, and it connects the strategy brain back to the evidence-coverage doctrine the project already has. It answers "why am I doing another run?" with a number.

---

## 7. Weather

GT7 exposes nothing. The design must therefore be:

- **Driver-declared primary.** A one-touch "rain starting / raining / drying / dry" input, and a radar read relayed by voice. The in-game radar at maximum zoom is the only forecast that exists.
- **Telemetry-inferred corroboration**, in latency order: TCS/ABS intervention magnitude (sub-second) → slip-ratio excess at matched throttle → tyre-temperature collapse → fuel-corrected lap-time step (one lap, the slow confirmer). Never let the inferred channel alone trigger a tyre change; it should raise a *query* to the driver.
- **The crossover is an optimal-stopping problem, not a threshold.** The naive rule "switch when the other tyre is faster" ignores pit loss. Correct form, `O(L)` with prefix sums:

```
l* = argmin_l [ Σ_{j≤l} t_current(W(j)) + T_pit + Σ_{j>l} t_new(W(j)) ]
```

evaluated over the *distribution* of wetness trajectories, not a point forecast. On a drying track the optimum is **later** than the instantaneous crossover; on a wetting track, **earlier** — and §6.2's asymmetry then pushes it earlier still on the way in.

- Treated tyres are quadratic in wetness with an interior optimum: they overheat and destroy themselves on a drying line. Model `t_inter(W)` and `t_wet(W)` as quadratics, `t_slick(W)` as super-linear and effectively unbounded.

---

## 8. Live recalculation

### 8.1 Three objects, never one

The single most common architectural failure in amateur strategy tools is one mutable "current strategy" object. It is the root cause of thrash, unexplainability, and audit failure.

| Object | Mutability | Refresh | Purpose |
|---|---|---|---|
| **Committed plan** | Immutable, versioned, content-hashed | Only on an approved change | What the driver has been told. The sole source of truth for radio calls and fuel targets. |
| **Live projection** | Recomputed wholesale | Every lap boundary | "Executing the committed plan from the *measured* state, what happens?" |
| **Candidate set** | Recomputed and discarded | Every lap boundary | Alternatives scored under identical assumptions and **identical random draws**. Never surfaced as a recommendation until it passes the switching gate. |

### 8.2 The clock

- **Ingest** at 60 Hz; aggregate to lap records. Never compute on the telemetry thread.
- **Project and re-estimate** at the **lap boundary** — the natural sample interval, and it makes replay deterministic.
- **Decide only at gates:** approaching a pit window · a confirmed divergence signal · a race-phase transition (rain, damage, driver-declared incident, telemetry loss) · a scheduled review every K laps.
- **Event interrupts** for anything that invalidates the projection between boundaries.

Between gates the recommendation is frozen *by construction*. This removes most thrash for free and is far more robust than filtering a per-lap recommendation stream.

### 8.3 Divergence detection

Four channels, with deliberately different trust:

| Channel | Residual | Trust |
|---|---|---|
| Fuel per lap | `used − planned` | **High — measured. Act soonest.** |
| Lap time vs plan target | `t_lap − target(stint_lap, fuel_mass)` | Medium |
| Degradation vs model | `ν̂_live − ν_planned` | **Low — derived. Widest gate.** |
| Cumulative stint delta | Σ residuals, and projected stint-end delta | Medium; best "is the plan still the plan" |

**Detection stack** (all deterministic, all pure functions of the lap series):

1. **Clean-lap gate first — it matters more than the statistics.** Exclude in-laps, out-laps, first lap of a stint, any lap the driver flagged as compromised, any lap with off-track/contact, and any lap where you yourself commanded a lift. If a lap cannot be classified, it does not feed the detector. Note that with no caution signal, "compromised" is a driver declaration — so the gate is only as good as how easy that declaration is to make at speed.
2. **EWMA (λ ≈ 0.2) for what you report.** Also gives the one-step forecast for free.
3. **CUSUM (k = 0.5, h = 5) for what you act on.** Do the arithmetic: h = 4 gives ~0.3 false alarms per channel per 50-lap race, so with three channels ~0.9 per race — too many. h = 5 gives ~0.1 per channel. Document the chosen ARL₀ in the app.
4. **Directional asymmetry.** Over-consumption is dangerous; under-consumption is a bonus. Different `h` for the two sides.
5. **Reset on signal.** Emit the event, zero the CUSUMs, re-baseline to the post-change level. Otherwise the detector fires every lap for the rest of the stint — a very common, very visible bug. Hard-reset all detectors at pit stops, compound changes, and on leaving `COMPROMISED`.
6. **Never let absence of data read as "no divergence."** Missing input is an explicit `UNKNOWN` that propagates into confidence and suppresses recommendations.

One subtle trap worth naming: **once the engine issues pace or fuel targets, its own instructions confound its own degradation estimate.** Log the commanded target alongside the observed lap and regress against it, or the model learns its own advice.

### 8.4 The switching rule

Change the committed plan only if **all five** hold:

```
1. GAIN         E[T_committed] − E[T_alt] > θ,  θ = θ_base + z·σ_diff + C_switch
2. PERSISTENCE  the same alternative has led for ≥ M consecutive gate evaluations
3. DWELL        ≥ D laps since the last committed change
4. CONFIDENCE   evidence grade of the driving input ≥ the grade required for that trigger
5. FEASIBLE     current lap ≤ the alternative's commitment point
```

- `σ_diff` is the sd of the **paired** difference under CRN (§5) — much smaller than either candidate's own sd, which is the entire point. `z ≈ 1.0–1.6`.
- `C_switch` is a real cost: driver re-briefing, and the option value of information you would have had by waiting. Set it in seconds and expose it.
- **Two thresholds, not one.** Enter a new plan at `θ_in`; revert to the previous only at `θ_out < −θ_in`. Otherwise two near-equal candidates oscillate at the boundary.
- **`θ` is asymmetric** per §6.2: cheap to shorten a stint, expensive to extend one.
- **Recommend a window, commit a lap.** Emit `[earliest, optimal, latest]` plus the **cost curve** across the window. A flat curve means "stop whenever convenient"; a sharp one means "hit the lap". Small re-estimates then move the optimum *within* the window without changing the message to the driver — the window is itself an anti-thrash device.

### 8.5 Commitment points

The most under-implemented concept in amateur strategy tools, and the direct cause of two documented professional failures.

```
commit_deadline = predicted_pit_entry_arrival_time − (radio lead + driver reaction + line-change margin)
feasible("box this lap") ⟺ now < commit_deadline
```

Three consequences:

- **Pre-filter the candidate set by feasibility before optimising.** Never score an action you cannot execute. Otherwise the optimiser confidently returns "you should have stopped on lap 10" on lap 13.
- **Recommendations expire.** They are never allowed to persist past their deadline.
- **Never issue an execute call whose deadline has passed** — suppress it and issue the explicit cancel instead.

The app already models track progress and pit-lane geometry, so this is a lookup, not an estimate. It also directly repairs UAT defect D1: the "box this lap" prompt must be resolved by telemetry-detected pit entry, never by a button the driver cannot press in VR.

### 8.6 Contingency cards — the failsafe's second half

Pre-compute the branches, **refresh them every lap in the background**, and validate at trigger time. A stale card is worse than no card.

```python
@dataclass(frozen=True)
class ContingencyCard:
    trigger: TriggerKey        # ("DAMAGE","front") ("RAIN_ONSET","light")
                               # ("FORCED_STOP",) ("TYRE_CLIFF",) ("FUEL_HIGH",)
                               # ("PACE_OFF_PLAN",) ("TELEMETRY_LOST",)
                               # note: no ("CAUTION",) — GT7 gives no such signal
    valid_from_lap: int
    valid_to_lap: int          # cards are lap-scoped, never race-scoped
    action: PlanDelta          # the diff to apply to the committed plan
    radio_call: str            # pre-written, already short
    expected_gain_s: float
    confidence: Confidence
    computed_at_lap: int
    inputs_hash: str
```

**v2 correction — there is no caution card.** v1 called it the highest-value card, reasoning from F1 where a safety car collapses the pit-loss term. GT7 exposes no caution signal in telemetry, and a private league has no marshalling system to generate one. The card has no trigger and cannot be built. Everything below is driver-declared or telemetry-derived, which is the real constraint on this card set.

| Trigger | Pre-armed response |
|---|---|
| Damage / puncture | forced stop; re-split the remaining race into legal stints; fuel to add — **highest-value card**, because it is the most likely plan-destroying event that the app can actually detect or be told about |
| Forced early stop, any cause | legal re-split, new fuel numbers |
| Rain onset / drying | compound switch lap, wet pace prior, crossover estimate |
| Fuel-per-lap high, confirmed | lift-and-coast corner count vs splash-and-dash |
| Pace off plan, confirmed | revised target; is the plan still legal at this pace? |
| Tyre cliff detected | bring the stop forward to the earliest feasible lap in the window |
| Telemetry loss | freeze the committed plan, suppress new recommendations, **tell the driver** |

At trigger time the runtime does `lookup → validate freshness → validate feasibility → emit`. If validation fails, fall back to a **conservative** default ("stay out, confirm next lap") — **never** to a fresh optimisation under time pressure. The value of pre-computation is not saving CPU; it is converting a comparison task into a recognition task at the moment of highest load.

### 8.7 Fuel management live

```
usable        = fuel_onboard − reserve
required_avg  = usable / laps_to_stint_end
fpl_est       = robust(last k clean laps)      # median + EWMA, never a mean
delta         = fpl_est − required_avg          # > 0 ⇒ saving needed
margin_laps   = usable / fpl_est − laps_to_stint_end
```

Report **`margin_laps` and `delta`**, not raw litres. And convert the instruction into something a driver can execute:

> Calibrate `(litres saved, seconds cost)` per corner from your own paired-lap telemetry, sort by ratio, and emit a **count**: *"Lift three corners: one, six, eleven."* Not *"save 0.4 litres per lap."*

**The break-even.** Saving Δ L/lap at a cost of c s/lap over L remaining laps is worth it iff

```
c · L  <  Δ · L / ṙ     ⟺     c < Δ / ṙ
```

At the project's assumed `ṙ = 1 L/s` this reduces to *"lift if the seconds cost per lap is less than the litres saved per lap"* — a very permissive rule that makes saving almost always correct. **At a measured 7 L/s it becomes seven times harder to justify.** This inequality is the clearest possible demonstration of why §0's finding 4 matters: the entire fuel-saving doctrine hinges on one unmeasured constant. Add the full pit-transit loss to the benefit side when saving eliminates a stop outright.

Also model the finish properly: in timed races the lap count is itself an estimate (white flag = leader's first crossing after the timer, plus one lap), so `laps_remaining` carries uncertainty and the fuel target must be gated by `P(one more lap needed)`.

### 8.8 Talking to the driver

Fixed grammar, because it is what a loaded driver can parse and what a machine can verify:

```
[ATTENTION] [ACTION] [OBJECT/NUMBER] [DEADLINE] (ack)
```

| Good | Bad |
|---|---|
| "Box this lap, box this lap. Fuel to the end." | "Degradation has come in higher than modelled so the optimum has moved forward…" |
| "Fuel target minus point three. Lift three corners: one, six, eleven." | "You're 0.42 litres per lap over the required average of 2.81." |
| "Box in three. Confirm." | "We might box in two or three, we'll let you know." |

Include one action, one number the driver can control, one deadline. Omit reasoning, probabilities, confidence intervals, alternatives — those go to the log and the UI.

**Lead-time ladder:** "Plan B is live" (5+ laps, pre-arming a *pre-briefed* branch) → "Box in three" (crew readiness, driver manages traffic and temps) → "Box next lap" (last cheap abort) → "Box this lap" (must land before the commitment deadline) → "Stay out, stay out" (explicit cancel).

Four rules: **never let silence carry meaning** (every armed call gets an execute or an explicit cancel); rate-limit with a priority queue (SAFETY > EXECUTE > DEADLINE-BEARING > TARGET UPDATE > INFO); **position speech in the lap** using track progress — the longest straight, not a braking zone; suppress unchanged information.

Model acknowledgement as explicit state: `ARMED → SENT → (ACK | NO_ACK) → EXECUTED | CANCELLED | EXPIRED`. On no-ack, re-issue **once**, shorter, then escalate to a non-verbal channel. The list of unacknowledged critical calls is one of the most valuable post-session artefacts you can produce, and it feeds the certification standard's "PTT usable at racing speed" criterion directly.

**And the guardrail that connects to the voice stack (project docs 04/05):** every number spoken to the driver must be traceable to a field in the emitted plan/state object, verified before speech, with a deterministic template fallback. A published system that generated race-strategy language found only **81.9 %** of model-written sentences passed a faithfulness check against engine state, and that richer fine-tuning *increased* fabrication of gaps and compounds when grounding was sparse. Never let a generative layer speak an unverified number to a driver at racing speed.

---

## 9. Architecture

```
model/        laptime.py  tyre.py  fuel.py  pitloss.py  wet.py      # pure, stateless
estimate/     robust.py (Huber, Theil–Sen)  kalman.py  shrink.py
              cleanlap.py  cusum.py  ewma.py
optimise/     dp.py (backward Bellman, vectorised)  analytic.py (closed-form seeds)
              legality.py (§4 gates — applied before scoring)
uncertainty/  scenarios.py (CRN table)  evaluate.py  risk.py (CVaR, regret, EVSI)
race/         ledger.py (event-sourced lap records)  project.py
              replan.py (gates, switching rule, commitment points)
              contingency.py  decisions.py (DecisionRecord log)
```

**Event-sourced lap ledger + pure reducers.** The append-only `LapRecord` stream is the only durable truth; all derivation is a pure function of it.

```
state_n      = reduce(apply_lap, ledger[:n], initial)
projection_n = project(state_n, committed_plan, seed=h(race_id, n))
candidates_n = [score(state_n, c, seed=h(race_id, n, i)) for i, c in enumerate(cands)]
decision_n   = gate(committed_plan, candidates_n, policy, state_n)
```

Invariants to enforce and test:

- **No wall-clock and no global RNG inside logic.** Time is a field on the event; randomness is a seeded, content-derived stream.
- **Replay determinism** — `reduce(ledger)` produces byte-identical state on every run and machine. Assert in CI.
- **Idempotence** — applying a lap twice is a no-op; recomputing lap n yields the same plan content hash.
- **Round at the presentation boundary only**, and compare plans by hash of the *rounded* fields, so float noise cannot manufacture a spurious "plan changed" event.

**Race-phase state machine**, and it must actually gate emission or it will be decorative in exactly the way `RaceWeekendPhase` currently is:

```
PRE_SESSION → GRID → FORMATION → GREEN ⇄ {PIT_APPROACH → PIT_LANE → OUT_LAP}
            → FINAL_LAP → FINISHED
            ⊥ COMPROMISED  (driver-declared: incident ahead, damage, off — not machine-detected)
            ⊥ TELEMETRY_LOST (from any state, with return-to-last-known)
```

v1 had a `CAUTION` state here. There is no caution signal to drive it, so the equivalent is `COMPROMISED` and it is **driver-declared only** — which means it must be one button or one voice token, because anything more elaborate will not be used at racing speed.

Each phase declares which estimators update, which are frozen, which recommendations may be issued, and the default action. Concretely: freeze all estimator updates in `PIT_LANE` and `OUT_LAP`; on entering `COMPROMISED` reset the CUSUMs immediately and stop feeding the lap into any residual series; in `TELEMETRY_LOST` freeze the plan, suppress recommendations, and say so out loud.

**Decision records — log the non-changes.**

```python
@dataclass(frozen=True)
class DecisionRecord:
    lap: int
    gate: GateKind                     # SCHEDULED | DIVERGENCE | PHASE_CHANGE | WINDOW
    trigger_reason: ReasonCode         # enum, NOT free text
    detector_evidence: dict            # CUSUM S±, EWMA level, clean laps used
    from_plan: str;  to_plan: str | None    # None = no change
    candidates_considered: tuple[CandidateScore, ...]
    gain_s: float;  threshold_s: float      # θ itemised into its three parts
    blocked_by: tuple[BlockReason, ...]     # DWELL | PERSISTENCE | CONFIDENCE | INFEASIBLE
    radio_call_issued: str | None;  ack_state: AckState
```

"We considered stopping on lap 17 and rejected it because dwell had not elapsed" is the single most valuable record for debugging thrash, and it is what makes the system explainable to a driver who asks *why didn't you call it?*

**Counterfactual explanation, cheaply.** Perturb one input at a time and re-run the deterministic scorer: *"We would stop on lap 16 instead of 18 if degradation were 0.05 s/lap worse, or if fuel per lap rose by 0.15 L."* No ML required, and it doubles as a sensitivity analysis showing which inputs the recommendation actually rests on.

**Parity gating.** Ship every new estimator in shadow with an explicit `SHADOW | ACTIVE` flag visible in the UI, log both outputs, compare over recorded races, promote only when clean. Given the project's finding that much of the doctrine is unwired from the shell, one visible shadow flag per component is worth more than another thousand tests.

---

## 10. Failure modes, each with its guardrail

| Failure | Documented case | Guardrail |
|---|---|---|
| **Stale offline lookup feeding a live gate** | Mercedes, Australia 2018: an offline tool returned ~15 s for a VSC threshold when the truth was just under 13 s. They believed they were safe. Lost the win. | Any precomputed constant gating a live decision is a first-class **golden-value regression test**, recomputed from the *same code path* as the live model — never a parallel implementation. Add a crude independent cross-check and refuse to call when the two disagree. **Note the shape: 11,000 passing tests do not help if the tested path is not the executed path** — which is precisely this project's own UAT finding. |
| **Stale state at the decision moment** | Mercedes, Monaco 2015: lost accurate track of gaps under safety car; the SC ran slower than its own target so the field closed faster than modelled. | Freshness stamp on **every** input with a per-channel staleness budget. Exceeded budget ⇒ downgrade to "insufficient data — hold". On entering `COMPROMISED`, **invalidate all green-running-derived quantities immediately** — the event changes the generative process, it does not merely add noise. |
| **Degradation extrapolated past validity** | "By lap 13 the model says the optimum was lap 10 — too late." Correct update, infeasible answer. | Constrain the action space to feasible actions *before* optimising (§8.5); cap the linear extrapolation horizon; widen the interval with horizon so far-horizon claims automatically need more evidence. |
| **Over-reacting to one lap** | ubiquitous | Clean-lap gate + CUSUM + m-of-n + dwell + heavy-tailed error model. |
| **Point estimates without uncertainty** | ubiquitous | Every projection carries an interval; every recommendation carries the paired difference distribution; θ contains `z·σ_diff`. |
| **Confounded parameter estimation** | A published engine's raw per-race fitting conflated compound pace with track evolution and fuel burn, inverting the compound order in 18 of 24 races and inflating undercut success to 72.9 % in one case. | Impose physical priors (compound ordering, monotone degradation, non-negative burn) on the **decision** path even at the cost of fit. Note the deeper lesson: *the model with the best-calibrated probabilities is not necessarily the model that gives the best recommendations.* Keep both paths and report both. |
| **Speech layer stating what the model doesn't contain** | 18.1 % of generated strategy sentences failed a faithfulness gate | Claim-check every number against state before speaking; deterministic template fallback. |
| **Silent degradation** | this project's own nine `except: pass` | Every channel has a heartbeat and a last-valid-lap counter. Absence is an explicit `UNKNOWN`, never a silent zero. Add a synthetic canary. |

### Tests that would have caught each of these

1. **Golden-race replay** — recorded sessions, asserted plan/decision sequences; any output change is a reviewed diff.
2. **Thrash regression** — `plan_changes_per_race ≤ N` and `min_laps_between_changes ≥ D` on every golden race. Nobody writes this test. It is the one that keeps §8.4 honest.
3. **False-alarm budget** — synthesise stationary lap series at measured noise; assert the observed false-alarm rate matches the designed ARL₀.
4. **Feasibility invariant** — no emitted recommendation ever has `deadline < issue_time`.
5. **Freshness invariant** — property-test by dropping channels at random laps; assert no recommendation is emitted on stale critical input.
6. **Lookup-table parity** — every precomputed constant equals the live model's output for the same inputs.
7. **Claim verification** — every number in every generated call resolves to a field in the emitted state.
8. **Determinism** — same ledger ⇒ identical plan hashes, across runs and machines.
9. **Analytic oracles** — single compound, linear degradation, no noise ⇒ the DP must reproduce `n* = √(2T_p/d)` to within rounding; multi-compound ⇒ stint lengths must satisfy the equal-marginal-lap-time condition within one lap; σ_ε = 0 and zero hazards ⇒ Monte Carlo must collapse exactly onto the deterministic DP.

---

## 11. The measurement programme — do this before trusting any number

Six quantities dominate the maths and none of them is published. Each is a short, deliberate test.

| # | Quantity | Test | Why it matters |
|---|---|---|---|
| 1 | **Refuel rate ṙ (L/s), per event** | Log `Δfuel/Δt` while stationary on the first stop | The entire fuel-saving doctrine (§8.7 break-even) hinges on it. 1 vs 7 L/s changes the answer sevenfold. |
| 2 | **Serial or parallel** tyres and fuel | Time a tyres-only stop, a fuel-only stop, and a both stop | Sum vs max. Changes every double-stint calculation. |
| 3 | **Fuel weight `k_f`** (s/lap per 10 L) — **corroboration, not foundation** | Identical fresh tyres, full tank vs ~10 L, tyre wear off, same track | Needed only for the fuel-corrected lap-time fit that cross-checks the gauge (§3.2, §3.3). Because the gauge is primary, **nothing in the main path is blocked on this** — v1 wrongly listed it as foundational. Do it when convenient, not first. |
| 4 | **Pit-lane delta per track** | Time entry line → exit line vs equivalent track time | The dominant fixed cost in `n*`. |
| 5 | **Compound pace deltas and degradation slopes, per car/track** | Structured practice long-runs, ≥ 12 clean laps per compound | §3.3 says fewer than ~10 laps is prior-dominated. This is what the practice programme is *for*. |
| 6 | **Lap-time cost per fuel-map step** | Paired laps at FM n and FM n+1 | The fuel/pace exchange rate. Consumption is known (−8 %/step); the time cost is not. |

Every one of these becomes a provenance-tagged, per-event, per-car stored constant with an explicit fallback and a visible marker when the fallback is in use — the same discipline Phase 1 applied to setup data.

---

## 12. What this design deliberately does not do

- **It does not model rivals.** No undercut, no overcut, no traffic, no track-position value. Having no opponent data is a blessing in disguise: it removes an entire class of unverifiable assumptions. Any recommendation that would depend on opponent behaviour is either not offered or is offered clearly labelled as the driver's judgement call. This is a stronger and more honest position than a tool that fabricates a field model.
- **It does not claim a probability of winning.** It reports feasibility probability, a race-time distribution, and CVaR, and it names the surrogate.
- **It does not present an argmin as an answer.** It presents a cost curve, an uncertainty band, and a statement of whether the top plans are separable at all.
- **It does not sample scenarios yet.** Until the §11 measurement programme lands, the parameters have no distribution worth sampling from, and an interval around a guess is worse than an honest point estimate (§5).
- **It does not build a dynamic programme yet.** Enumeration is exact and fast enough at this size; the DP is reserved for the stochastic extension and nothing else (§3.6).
- **It does not use reinforcement learning, cloud inference, or anything non-deterministic.** Every number is reproducible from the ledger and a fixed seed.

---

## Sources

**GT7 telemetry:** [Nenkai/PDTools](https://github.com/Nenkai/PDTools) · [MacManley/gt7-udp](https://github.com/MacManley/gt7-udp) · [zetetos/gt-telemetry](https://github.com/zetetos/gt-telemetry) · [snipem/gt7dashboard](https://github.com/snipem/gt7dashboard) · [PDTools issue #14](https://github.com/Nenkai/PDTools/issues/14) / [#18](https://github.com/Nenkai/PDTools/issues/18) · [GTPlanet — Overview of GT7 Telemetry Software](https://www.gtplanet.net/forum/threads/overview-of-gt7-telemetry-software.418011/) · [GT Race Engineer](https://www.skepller.dev/gtre/)

**GT7 mechanics:** [Test Results: Fuel Mixture Settings](https://www.gtplanet.net/forum/threads/test-results-fuel-mixture-settings-and-other-fuel-saving-techniques.369387/) · [Do cars refuel at different speeds?](https://www.gtplanet.net/forum/threads/do-cars-refuel-at-different-speeds-during-pit-stops.419240/) · [Estimated Pit Stop Duration?](https://www.gtplanet.net/forum/threads/estimated-pit-stop-duration.381486/) · [Pitstops explained?](https://www.gtplanet.net/forum/threads/pitstops-explained.407333/) · [DG-EDGE — 1.49 physics breakdown](https://www.dg-edge.com/articles/guides/gran-turismo-7-physics-update-1-49-breakdown/424) · [Wets vs Intermediate](https://www.gtplanet.net/forum/threads/wets-vs-intermediate.390792/) · [GT7 World Series 2-minute penalty](https://www.gtplanet.net/forum/threads/gt7-world-series-2-minutes-penalty-could-you-explain-it.431072/)

**Strategy optimisation:** [Heilmeier et al., *Monte Carlo methods in race simulation*, Appl. Sci. 10(12):4229](https://www.mdpi.com/2076-3417/10/12/4229) · [Heilmeier et al., *Virtual Strategy Engineer*, Appl. Sci. 10(21):7805](https://www.mdpi.com/2076-3417/10/21/7805) · [TUMFTM/race-simulation](https://github.com/TUMFTM/race-simulation) · [Bujak et al., *Pit stop strategies via dynamic programming*, CEJOR 2022](https://link.springer.com/article/10.1007/s10100-022-00806-4) · [*Optimization of Pit Stop Strategies in F1*, Universidad de Chile](https://repositorio.uchile.cl/bitstream/handle/2250/199664/Optimization-of-pit-stop-strategies-in-Formula-1-racing.pdf) · [*A State-Space Approach to Modeling Tire Degradation*, arXiv:2512.00640](https://arxiv.org/pdf/2512.00640) · [f1chronicle — 2,106 measured pit stops](https://f1chronicle.com/f1-pit-stop-time-loss-data/)

**Live operation:** [*Pitwall*, arXiv:2607.06495](https://arxiv.org/html/2607.06495) · [Raceteq — how teams determine the fastest strategy](https://www.raceteq.com/articles/2024/07/how-formula-1-teams-determine-the-fastest-race-strategy) · [RACER — IndyCar fuel-saving strategies](https://racer.com/2022/12/08/tech-download-indycar-fuel-saving-strategies) · [RaceFans — Mercedes software bug, Australia 2018](https://www.racefans.net/2018/03/28/mercedes-explains-software-bug-confirms-cost-hamilton-win/) · [Motorsport.com — Monaco 2015 pit call](https://www.motorsport.com/f1/news/analysis-where-it-all-went-wrong-with-mercedes-pit-call-in-monaco/3222316/) · [JMP — CUSUM and EWMA control charts](https://www.jmp.com/en/statistics-knowledge-portal/quality-and-reliability-methods/control-charts/cusum-and-ewma-control-charts) · [Coach Dave Academy — lift and coast](https://coachdaveacademy.com/tutorials/mastering-lift-and-coast-how-to-save-fuel-without-sacrificing-speed/) · [SimHub fuel & strategy properties](https://dahl-design.gitbook.io/properties/properties/fuel-and-strategy)
