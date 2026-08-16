# FINAL SPECIFICATION — Lap-time-based stint management

**Resolved against the driver's directive, four critic passes, and re-verified against `C:/Projects/VR_Dashboard/data/pitcrew.db` (154 laps, 23 stints). Every figure below was recomputed in this session; where a proposal's number failed to reproduce or was measured on the wrong lap set, the corrected value is used and the original is named.**

---

## 0. The one-line summary the driver needs first

The app can measure that he is slower than he was. It cannot measure why, and it cannot see the cliff coming. The instrument's noise floor is **1.74 s/lap**, which sits *above* the whole of the 0.5–1.5 s/lap phase-2 degradation band. **It is a confirmer, not a warning.** Replayed over all 154 of his recorded laps it would have spoken **zero times**. Silence from this instrument is not tyre health, and the app says so out loud once per race so silence is never misread.

---

## 1. The usable-lap definition

### 1.1 The rule

A lap feeds the pace series only if **all** of the following hold:

1. Not a pit lap, not an out lap, not excluded, and `lap_time_ms > 0` — *(133 of 154 laps are countable)*
2. `off_track_s < 2.0` s
3. `crawl_s < 0.5` s
4. `spin_s < 0.08` s
5. `off_track_s IS NOT NULL` — a null means the packet format carried no surface channel. Per CLAUDE.md §4.3 that is *not measured*, not *never left the road*; the lap is unverifiable and drops out. **If the whole session is packet `A`, the pace series is void and only PACE_UNREADABLE ever speaks.**

### 1.2 Survival, verified

| | laps |
|---|---|
| Recorded | **154** |
| Countable (pit/out/excluded/zero-time removed) | **133** |
| Struck by the filter | **19** |
| **Usable** | **114** (85.7 % of countable, 74.0 % of all recorded) |
| Stints reaching 6 usable laps | **6 of 23** (23, 13, 13, 11, 9, 8) |
| Stints reaching 3 usable laps | 13 of 23 |

### 1.3 Provenance of the 2.0 s cut — and why the 1.25 s alternative is rejected

2.0 s is the knee in the **off-track-seconds vs measured time-loss** relation: at that cut 7 of 10 flagged laps genuinely lost > 3 s (median loss +4.51 s), against 20 % at 1.0 s and 12 % at 0.05 s. Below 1.5 s the flag carries no time information at all (median loss of a flagged lap +0.25 s).

**Label it honestly: this is a selection over ten flagged events, not a measured constant.** The 2.0-vs-2.5 comparison turns on one lap in each direction (9/11 slow laps struck with 2 innocents, vs 8/11 with 1 innocent). 2.0 is chosen because it is the conservative side of the knee — overshooting a stint costs far more than undershooting (CLAUDE.md §5.1).

**Proposal B's 1.25 s cut is rejected.** It was selected by minimising lap-time scatter over six candidate cuts on the same 69 pairs that then set the threshold — the filter was tuned against the noise it is subsequently measured against. Bootstrapped, σ(1.5) − σ(1.25) = 0.151 with 95 % CI [−0.265, +0.356], containing zero; all candidate CIs overlap heavily. σ at a selected minimum is biased low, which biases the trigger threshold low, which fires on noise. **The cut must be chosen from frame evidence and time loss only — never from lap-time scatter.** That is the sole criterion above.

`crawl_s ≥ 0.5` and `spin_s ≥ 0.08` are the detector's own minima in `analysis/incidents.py` and were confirmed trustworthy as-is (13 of 15 crawl laps survive, median loss +5.99 s; all 15 reach 0.0–0.1 km/h mid-lap, and `LAUNCH_KPH` already strips the grid).

### 1.4 Two biases, declared and not corrected

- **Laps carrying up to 2.0 s of off-track are admitted** and carry a median +0.25 s. `R` can be inflated and `d` biased **downward** — conservative for a box call.
- **Fuel burn-off is not corrected out.** The best-fitting fixed correction over his own data is **0.0000 s/L/lap**; applying the derived 0.003 raises pooled residual sd from 0.6248 → 0.6365 and shifts every stint slope ≈ +0.02 s/lap toward false degradation. The coefficient is unmeasurable here — pooled fixed-effects fit +0.00218 ± 0.01321 s/L, a CI ten times the working figure, containing zero and 0.030 alike; making 0.003 significant needs ≈ 1,875 clean laps against 38. `k = 0.003` stays flagged **ASSUMED** per CLAUDE.md §5.3, remains driver-overwritable, and **is never applied to the live pace series.** Because `R` is taken heavy and `P` light, uncorrected fuel makes `d` **under-report** degradation — the safe direction for a call that moves a stop *earlier*, and the reason no call is permitted to move one *later*.

---

## 2. The statistic, and the threshold

### 2.1 Definitions (all from `lap_time_ms`, measured, GT7 packet, integer ms)

```
R      = median of the FIRST 3 usable laps of the current stint, out-lap excluded.
         Frozen once set. Never re-derived from later laps.
P      = median of the LAST 3 usable laps of the current stint (disjoint from R).
d      = P − R,  seconds per lap.  Requires ≥ 6 usable laps in the stint.
```

Raw times. No fuel normalisation. No model, no wear fraction, no multiplier conversion.

**The reference must be causal.** `incidents.find_incidents` judges a lap against the median of its own whole run, which is only knowable afterwards. Live, the reference is this stint's own first-3 median and nothing later. The out-lap is never in `R` or the series — a cold lap poisons `R` upward and would mask a real deficit.

### 2.2 The noise scale — corrected

| quantity | value | how measured |
|---|---|---|
| σ_lap, pooled | **0.918 s** | median successive-usable-lap \|Δ\| = 0.876 s, ÷0.6745 ÷√2, over **93 pairs / 114 usable laps / 21 stints** |
| sd(median of 3) | **0.670 · σ** | Monte-Carlo, 400 000 draws. **Replaces the proposals' √(1.25/3) = 0.6455**, which was 4 % optimistic in the firing direction |
| σ_d (difference of two disjoint 3-lap medians) | **0.870 s** | 0.918 × 0.670 × √2 |
| **CLEAR (fire threshold)** | **1.74 s** | 2 σ_d |

**The handed-over 0.60 / 1.20 floors are dead.** They were computed on the strict-clean subset (38 laps, σ 0.625) and were to be applied to a series built on the 114-lap usable set, which is 47 % noisier. Carried across they would have set the trigger at ≈ 1.4 σ and roughly tripled the false-alarm rate.

### 2.3 Per-stint threshold, floored at pooled

A single pooled σ is the wrong scale: measured per-stint σ_lap across his six long stints is **0.295, 0.628, 0.761, 0.925, 1.126, 1.479** — a 5× spread. Pooled makes the call over-sensitive on the noisy stints and sets an unearned-low bar on a freak-quiet one.

```
σ_stint  = median|Δ| of THIS stint's own usable laps / 0.6745 / √2
σ_used   = max(σ_stint, 0.918)          # the stint's own noise may only RAISE the bar
CLEAR_stint = 2 × σ_used × 0.670 × √2   # = 1.741 s minimum, higher on a scattered stint
```

The one-sided floor is essential. Verified by permutation (shuffle each stint's own usable lap times, 6 000 draws per stint — destroys any trend, preserves the exact lap-time distribution), false-alarm rate **per stint**:

| threshold rule | null fire rate | fires in his 154 laps |
|---|---|---|
| per-stint σ, no floor | 5.5 % | 1 (stint 3, σ 0.295, bar 0.56 s — pure scatter) |
| per-stint σ, floor only when n < 8 | 5.1 % | 1 (same stint 3) |
| fixed pooled 1.741 | 4.4 % | 1 (stint 5, whose own null rate at that bar is **14.9 %**) |
| **per-stint σ, floored at pooled always** | **2.1 %** | **0** |

Measured deficits and their own bars: stint 3 +1.114 (bar 1.74), stint 4 −0.420 (1.75), stint 5 +2.120 (**2.13**), stint 12 +0.915 (2.80), stint 13 −0.695 (1.74), stint 14 +0.931 (1.74).

**Stint 5's d = +2.120 — called "the single genuine degradation event in the dataset" in Proposal A — does not clear its own stint's bar, and fires on 63 % of random shuffles of its own laps under the pooled bar.** It is unlabelled: nothing in the database says its tyres were worn rather than that it was his most scattered stint. It is not evidence and is not used as validation.

### 2.4 Single evaluation, once per stint

`d` is evaluated **exactly once per stint**, at `laps_to_stop() == 3`. Not every lap from 6 onward. Any-lap evaluation is what produced the 5–6 % null rates above; a single deterministic evaluation is what makes 2.1 % the real number. `laps_to_stop == 3` sits outside `_box_soon`'s 1–2 window and `_box_now`'s 0, so nothing higher-ranked competes for that lap.

---

## 3. The final call set

Four kinds go in; one proposed kind is killed outright and stays dead.

### Urgency ladder (replaces `URGENCY` in `calls.py:37`)

```
BOX_NOW > FUEL_SHORT > BOX_SOON > PACE_BOX > INCIDENT_NOTE > FUEL_LONG
        > PACE_UNREADABLE > GREEN > CHEQUER > STATUS
```

`TYRE` is removed from the ladder entirely. Fuel outranks everything pace-related because running dry ends the race and a second a lap does not. Nothing advisory or interrogative outranks an instruction.

---

### 3.1 `PACE_BOX` — measured deficit against the stint's own reference

**Fact.** `d = P − R`, both medians of measured `lap_time_ms`. Seconds per lap. Nothing else. It never asserts a tyre state.

**Trigger.** Once per stint, at the single evaluation lap `laps_to_stop() == 3`, when **all** hold:
- a stop is **already in the plan** (`stint_ends_on_lap is not None`);
- the stint holds **≥ 6 usable laps** (3 for `R`, 3 disjoint for `P`);
- `d ≥ CLEAR_stint` (§2.3, minimum 1.74 s);
- the stint is not being run on a non-modal `fuel_map`, and no lap in `R` or `P` followed a fuel-save or short-shift instruction from the app (see §3.1.1).

**Statistic behind it.** σ_lap 0.918 s (93 pairs, 114 usable laps, 21 stints); sd(median of 3) = 0.670 σ (Monte-Carlo); σ_d 0.870 s; CLEAR 2 σ_d = 1.741 s, raised per stint, never lowered. Permutation null 2.1 % per stint. **Fires zero times across his 154 recorded laps.**

**Spoken.**
> "Box three early if you want it. You're 2.1 off your own first three laps."

Instruction first and the instruction is his to take. The deficit is spoken to one decimal because it is measured. The comparator is named. The word "tyres" never appears — the app measured that he is slower than he was, and that is exactly and only what it says. The usable-lap count goes to the screen and the export, not to the radio.

**Lever.** A direct `RaceCoordinator.move_stop(new_end_lap)` that shifts `stint_ends_on_lap` and recomputes the fill from **measured burn only**. **It must NOT route through `replan.assess` → `strategy.model.recommend()`** — that path lengths every stint through `tyre_limited_laps`, `pace_loss_s` and `STINT_SAFETY_FACTOR 0.85`, which would install the modelled wear curve off a lap-time trigger. That is the banned costume, and it is the single most important implementation constraint in this document.

Offered, never imposed. The move is applied only on an explicit `ACCEPT`. It uses a **separate pending slot** from `_pending_replan` and **auto-expires at the end of the following lap** — an unanswered pace offer must never block `replan`'s URGENT fuel-short-of-the-flag offer (`controller.py:2469` returns early while `_pending_replan` is set). If accepted, `_box_soon`/`_box_now` then speak the box call in their own register on the following lap; PACE_BOX does not also speak an instruction. Only one mouth per lap.

**Adding a stop that is not in the plan: forbidden on the radio.** `d_required = (pit_loss_s + PIT_DEAD_TIME_S + out_lap_penalty) / N` = 28.5 / N on his declared numbers, of which 7.5 s and 1.0 s are **assumed**, not measured. Against CLEAR 1.74 that needs N ≥ 17 laps remaining with zero margin, before the fresh set's own degradation — and the observed `d` is subject to winner's curse: conditional on crossing a 2 σ bar, the expected true deficit is well below the observed one. Compute `d_required`, show it on the pit wall and in the export, and say nothing on air.

**Repeat rule.** Once per stint, one evaluation, no re-issue. There is no `WORSE_BY` entry — a statistic evaluated once cannot deteriorate.

**Pit reset.** `clear_stint()` drops `R`, `P`, the usable-lap buffer, σ_stint and the evaluated flag, unconditionally on every `PIT_EXIT` — including a fuel-only stop, because `R` is a property of the stint, not of the tyre set.

**Side effect.** From the evaluation lap to the end of the stint, `FUEL_LONG` ("You can push") is hard-suppressed **when and only when `d ≥ CLEAR_stint`**. It is *not* suppressed at any "cannot tell" floor — suppressing a call built on measured burn on the strength of a signal explicitly indistinguishable from zero inverts the provenance hierarchy.

**Confidence.** MEDIUM. Carried by the words, not a suffix: the reason names the comparator, and the sentence makes the deficit the claim rather than the cause.

#### 3.1.1 The app must not be able to trigger itself
Nothing currently excludes laps driven under the app's own instruction. CLAUDE.md §5.3 puts short-shifting at ≈ 0.5 s/lap and a fuel-map step at −4 % power. Two or three saving laps entering the `P` window fabricate a deficit of exactly the right magnitude, and the resulting box call would be caused by the previous radio call. **Any lap whose `fuel_map` differs from the stint's modal map, or that falls within 2 laps of a `FUEL_SHORT` map instruction, is excluded from both `R` and `P`, and the exclusion is recorded.** Traffic and an off-day have the same shape and are not separable — see §6.

---

### 3.2 `INCIDENT_NOTE` — clustered incidents, stated as a fact, never as a tyre claim

**Fact.** A count: how many of the last 3 countable laps carry `off_track_s ≥ 2.0` **or** `crawl_s ≥ 0.5` **or** `spin_s ≥ 0.08`. The count is factual; the thresholds are app-derived detector settings and belong under `derived` in the export.

**Trigger.** ≥ 2 of the last 3 countable laps struck, **and** the window does not include the stint's first 2 countable laps, **and** the lap being spoken on is itself not struck (delay one lap — do not speak on the lap of the second incident; if a third lands first, stay silent, he knows). **At most once per race.**

**Statistic behind it — stated plainly, because there isn't one.** Verified this session over all 133 countable laps: 19 strikes (per-lap rate 0.143), 90 three-lap windows, **2-in-3 windows observed = 1 against 5.0 expected under independence** — incidents are if anything anti-clustered. **9 of the 19 strikes fall on the first countable lap of their stint**, and the single observed 2-in-3 window is laps 1–2 of a 3-lap stint, i.e. the coldest tyre in the dataset. With the opening-lap suppression applied the trigger fires **zero times in 133 laps**. Incident rate through a stint also *falls*: 0.750/lap in first halves vs 0.659 in second (z = −0.935), sign test 1 up / 3 down / 3 tied, MDD ±0.191 against an observed −0.091; incident seconds regress at −0.62 ± 0.41 s once stint 14's single 69.62 s crawl is removed.

**This threshold is the driver's, not the app's.** It exists because he asked for it in his own words. It is retained at zero supporting instances, and the app therefore counts and reports — it never concludes.

**Spoken.**
> "Two offs in your last three laps — tell me if anything's changed."

One sentence. **Non-leading:** it does not name tyres. Naming them plants the one hypothesis his own 133 laps contradict, and the app then records his answer as primary evidence — the app manufacturing the evidence that outranks it. If he says tyres, that is his judgement and it is primary; if the app says it first, it is not. The `spoken()` LOW suffix ("Unconfirmed.") is **suppressed for this kind** — it is already a request, and a four-clause hedge stack is unparseable under a helmet.

**Lever.** None taken by the app. It solicits primary evidence. **It requires an answer channel that does not exist today** — see §5. His answer is recorded as a driver-declared observation against the current stint and exported beside whatever the pace series said at that moment; where they disagree, both sides are exported and never averaged (CLAUDE.md §4.1).

**Repeat rule.** Once per race, never repeated. **Pit reset:** none — the once-per-race limit survives every stop.

**Confidence.** LOW internally for the export; spoken without a hedge suffix because the sentence carries no claim to hedge.

---

### 3.3 `PACE_UNREADABLE` — the app says it cannot read the tyres

**Fact.** A count of rows: how many laps in this stint passed the usable filter, and how many it needs. Nothing about tyres is asserted. This is the app's **modal output** — 17 of his 23 stints never reach 6 usable laps.

**Trigger.** At `laps_to_stop() == 3` — the same evaluation lap as PACE_BOX, mutually exclusive with it — in either of two states:

- **(a) too few laps:** fewer than 6 usable laps in the stint.
- **(b) too scattered:** ≥ 6 usable laps but `CLEAR_stint > 2.0 s`, i.e. no deficit inside the 0.5–1.5 s/lap band is resolvable on this stint. Measured: 2 of his 6 long stints qualify (stint 5, bar 2.13; stint 12, bar 2.80).

**Spoken at most ONCE per race,** on the first stop decision:
> (a) "Call the tyres yourself this stop. Four usable laps is not enough for me to read them."
> (b) "Call the tyres yourself this stop. Your lap times are too scattered this stint for me to read them."

Thereafter the count rides in the existing `_status` reason string, on the rhythm he already has: `"P4, 12 to go. Four usable laps this stint."` Once per stint at 74 % of stints is a recurring apology, and a driver learns to tune out the channel that also carries `BOX_NOW`.

**The no-surface-channel case (packet `A` fallback) is a PRE-RACE condition**, spoken once at arming alongside the existing "no plan — fuel calls only" status line, never during the race. It is fixed for the whole session; announcing it per stint is six announcements of one fact.

**Threshold basis.** 6 is **structural, not tuned**: `d` requires two disjoint 3-lap medians, so below 6 the statistic does not exist. (The n=6 slope-power break-even cited in the handover is a *different estimator* on a *different filter* at a *different* σ and is corroboration only — recomputed at σ 0.702 it gives 0.516 s/lap, at the CI's upper edge 0.722 s/lap, i.e. marginal.) Frequency measured, not guessed: at 85.7 % usable yield a stint needs ≈ 7 laps to expect 6 usable; 6 of 23 stints qualify.

**Lever.** None mechanical. It hands the decision to primary evidence. Its function is to stop silence being ambiguous: without it, "the app has nothing to say" and "the app cannot see" sound identical under a helmet — the missing-is-null defect (CLAUDE.md §4.3) one layer up.

**Wording is load-bearing and must never drift.** "Can't read them." Never "nothing showing", never "tyres look OK", never "no problems".

**Repeat rule.** Once per race standalone; thereafter folded into `_status`. **Pit reset:** none for the standalone; the `_status` count resets with the stint.

---

### 3.4 `PACE_EXTEND` / `PACE_FLAT` — **KILLED. Stays dead.**

Both critics who examined it killed it on statistics, and neither misread the data. It is the only proposed call that converts a non-detection into an action, and every known bias points the wrong way:

- **It is very nearly the null hypothesis.** Permutation over trend-free lap orderings: `d < 0.70` at the final evaluation on **83.7 %** of shuffles. It does not detect flatness; it detects his normal state.
- **Power to detect a genuinely degraded car is ~43 % at a true 1.0 s/lap deficit, ~22 % at 1.5, ~9 % at 2.0.** On a car mid-phase-2 it would offer to extend roughly two times in five.
- **The fuel defence inverts.** Uncorrected fuel makes `d` under-report — safe for a call that moves a stop earlier, **unsafe for one that cancels it**, and the proposal did not notice the sign flip. The bound it quotes ("≤0.27 s/lap") uses `k = 0.003`, the very coefficient the same document proves unmeasurable; at the pooled CI's upper edge the masking is up to **+2.0 s/lap**, larger than PACE_BOX's entire threshold.
- **It spends the one lap of margin CLAUDE.md §5.1 mandates**, on absence of evidence. The cost of the lap that enters phase 3 is not bounded — that is the definition of phase 3.
- **Its stated rate guard is inert** on the only instance of the failure his capture set contains (stint 4's d-series 0.323 → 1.114 → 1.194 → 1.114; a single +0.791 step is not caught).
- **It could only be heard by outranking `BOX_SOON`**, i.e. by letting an absence of evidence silence an instruction off the approved plan. That is an argument the call does not fit the ladder.

**What survives:** the null result goes to the pit-wall screen and the export, with its power stated — *"deficit +0.31 s over 7 usable laps; a deficit below 1.7 s/lap is not excluded"* — where the qualifier can be read. It is **never a radio instruction to extend.** If he wants to run longer he asks; the answer is his to make on feel, which is primary evidence, and the app's contribution is the fuel number, which is measured.

---

## 4. What the modelled wear engine may and may not do

### Still allowed — **pre-race and on screen only**

- Building the offline stint plan: `L = 0.85 / w`, the three-phase curve, `tyre_limited_laps`, `pace_loss_s`, `DEG_AT_CLIFF_S`, `STINT_SAFETY_FACTOR`. The plan is his approved artefact and it is built before the green with time to read it.
- The pit-wall screen, where the figure can carry its source in writing.
- The export, under `derived`, with the model, its phase edges and its thresholds stated, and with the multiplier-linearity conversion tagged `[ASSUMED]` and never silently applied down to a race multiplier.
- Post-session debrief.

### Never again — **speaking**

- `_tyre()` is **deleted from `_candidates`** (`calls.py:244-253`) and the `TYRE` kind is removed from `URGENCY` and `WORSE_BY`. "Tyres are at the end of their window. Modelled at 92%." violates his standing order and CLAUDE.md §3.3: GT7 has no tyre wear channel in any packet format, so the percentage is a model output delivered in the grammar of a reading.
- No spoken wear fraction, no spoken laps-of-tyre-left, no spoken "the tyres are done", no spoken multiplier conversion, no spoken phase.
- No modelled quantity may **enter the plan** on a lap-time trigger — the `recommend()` route is closed to PACE_BOX (§3.1).
- `state.wear_per_lap` and `tyre_change_unconfirmed` stay on `RaceState` for the screen and export. They must have no reachable path to `voice.say`.

**Advantage worth recording:** the lap-time rule needs no multiplier conversion at all, so it sidesteps the `[ASSUMED]` linearity problem entirely rather than inheriting it.

---

## 5. The FIRST race — before any fresh-tyre reference exists for this car and track

**`R` needs no history.** It is this stint's own first 3 usable laps, so the instrument is armed from stint 1 of race 1. What *is* transplanted in race 1 is the pooled σ floor of **0.918 s**, measured across mixed cars and circuits — a fleet figure, not a Yas figure. It only ever *raises* the bar above the stint's own estimate, so the transplant is conservative, and it must be recomputed per circuit as laps accumulate.

### What the app says in race 1

**Once, before the green, spoken:**
> "I read your tyres from lap time only, and I need six clean laps in a stint to say anything. If I'm quiet about tyres, it means I can't see them — not that they're fine."

That sentence is the contract. It is said once per race, every race, and it is what makes every subsequent silence honest.

**During race 1, it will most likely say nothing about tyres at all.** The trigger fires zero times across 154 recorded laps, and 17 of 23 of his stints do not reach 6 usable laps. The realistic race-1 output is: `PACE_UNREADABLE` once at the first stop decision, the usable-lap count riding in `_status` every 5 laps, and normal fuel and box calls.

**What it does not do in race 1 (or ever):**
- It does not compare this stint to any previous session, car or circuit. There is no cross-session pace reference and none is being built into the live path.
- It does not report a wear percentage, a phase, or laps of tyre remaining.
- It does not offer to extend a stint.
- It does not add a stop.
- It does not tell him his tyres are fine, and it does not let silence imply it.
- It does not answer "how are my tyres" with a guess — with fewer than 6 usable laps the PTT answer is a refusal: *"Four usable laps this stint, I need six. Can't read them."*

**What it does do in race 1:** everything already working — fuel calls off measured burn, box calls off the approved plan, the fuel replan path — plus the once-per-race unreadable contract, plus `INCIDENT_NOTE` if two of three laps are struck, plus the full pace series written to the export so race 2 has a per-circuit σ to replace the fleet figure.

---

## 6. Genuinely unknowable — say this to the driver so he does not wait for it

1. **Tyre wear itself.** GT7 has no wear channel in any packet format. Nothing in this design measures wear; it measures lap time. Every wear number the app holds is modelled and stays off the radio.
2. **The cause of a deficit.** `d` contains traffic, track evolution, a damp patch, fuel burn-off, a mistake, and an off-day, in addition to the tyre. Lap time cannot separate them, and no threshold can. This is why the app says "you're slower than you were" and never "your tyres are gone".
3. **The cliff, in advance.** CLEAR is ≥ 1.74 s/lap, above the entire 0.5–1.5 s/lap phase-2 band. By the time this instrument proves a deficit, the deficit has already been paid. It confirms; it cannot warn.
4. **The fuel-weight coefficient.** Pooled estimate +0.00218 ± 0.01321 s/L. Making the 0.003 working figure just significant needs ≈ 1,875 clean laps against 38 available — off by a factor of 50, not a "collect a bit more data" gap. It will not be measurable on any realistic timescale. He may overwrite it by hand.
5. **Whether a fresh set returns to `R`.** Assumed. No track evolution is modelled.
6. **Pit loss and dead time.** `pit_loss_s` is declared (spin box, default 20 s); `PIT_DEAD_TIME_S = 7.5` is the midpoint of a 5–10 s band; the cold out-lap penalty 1.0 s is the midpoint of 0.5–1.5. All three are assumptions inside a 28.5 s budget, which is why the add-a-stop arm is off the radio.
7. **Axle asymmetry.** Lap time carries no per-axle information whatsoever. No brake-balance call can be derived from a whole-lap deficit; inventing one would be exactly the cross-sim pattern-matching CLAUDE.md rule 8 warns about.
8. **Multiplier linearity.** Assumed, unproven — and irrelevant to this instrument, which never converts.
9. **Whether incidents rise with wear.** Not proven either way. His data's point estimate is negative in the rate, negative in the seconds, and negative in both regressions, with a minimum detectable difference twice the observed effect. `INCIDENT_NOTE` accumulates the evidence; it does not assume it.

---

## 7. Implementation checklist

### `pitcrew/race/calls.py`

- [ ] **Delete `_tyre()`** and its entry in `_candidates` (lines 409-431, 251). Remove `TYRE` from `URGENCY` (line 37) and from `WORSE_BY` (line 59).
- [ ] Add kinds `PACE_BOX`, `INCIDENT_NOTE`, `PACE_UNREADABLE`; set `URGENCY = (BOX_NOW, FUEL_SHORT, BOX_SOON, PACE_BOX, INCIDENT_NOTE, FUEL_LONG, PACE_UNREADABLE, GREEN, CHEQUER, STATUS)`.
- [ ] No `WORSE_BY` entries for the three new kinds — all are once-per-stint or once-per-race and must not re-issue.
- [ ] **`Call.spoken()` (line 78-85): suppress the `"Unconfirmed."` suffix for `INCIDENT_NOTE`.** It is already a request; four clauses is unparseable.
- [ ] **`RaceState` (line 96) has no lap-time field at all.** Add: `usable_lap_times: list[float]`, `stint_reference_s: float | None` (frozen `R`), `pace_evaluated: bool`, `pace_deficit_s: float | None`, `pace_clear_s: float | None`, `last3_strikes: list[bool]`, `incident_note_said: bool` (race-scoped), `unreadable_said: bool` (race-scoped), `surface_channel: bool | None`, `stint_modal_fuel_map: int | None`, `fuel_save_instructed_on_lap: int | None`.
- [ ] Add `_pace_box`, `_incident_note`, `_pace_unreadable` to `_candidates`. All three gate on `laps_to_stop() == 3` except `INCIDENT_NOTE`.
- [ ] `_fuel()` (line 386): suppress `FUEL_LONG` for the remainder of the stint when `pace_deficit_s >= pace_clear_s`. **Not** at any lower floor.
- [ ] `_status()` (line 434): append the usable-lap count to the reason string once `unreadable_said` is set.
- [ ] **`clear_stint()` (line 450): reset the pace series unconditionally** — `usable_lap_times`, `stint_reference_s`, `pace_evaluated`, `pace_deficit_s`, `pace_clear_s`, `stint_modal_fuel_map` — on **every** `PIT_EXIT`, including fuel-only stops. `R` is a property of the stint, not of the tyre set. Leave `incident_note_said` and `unreadable_said` alone (race-scoped).
- [ ] Pure helpers: `usable(evidence, lap)`, `robust_sigma(times)`, `clear_threshold(times, pooled=0.9183)`, `deficit(times)`. Constants `POOLED_SIGMA_S = 0.9183`, `MEDIAN3_K = 0.6702`, `MIN_USABLE_LAPS = 6`, `UNREADABLE_SCATTER_S = 2.0`, `USABLE_OFF_TRACK_S = 2.0`, `USABLE_CRAWL_S = 0.5`, `USABLE_SPIN_S = 0.08` — each with its provenance in the comment, in the register of the existing file.

### `pitcrew/race/coordinator.py`

- [ ] **`_on_lap` (line 204) stores fuel and position and discards `lap.lap_time_ms` and the lap's evidence.** Both are prerequisites. Extend the signature to accept per-lap evidence and: append to `usable_lap_times` when the lap is usable, freeze `R` at 3 usable laps, track `last3_strikes` over countable laps, record `surface_channel = evidence.off_track_s is not None`.
- [ ] Add **`move_stop(new_end_lap)`** — shifts `state.stint_ends_on_lap` and re-derives the fill from `observed_fuel_per_lap()` only. **Must not import or call `replan.assess` / `strategy.model.recommend`.** Add a unit test asserting `strategy.model` is not on the call path.
- [ ] `_apply_stint` (line 143): reset the pace series on stint change, same fields as `clear_stint`.
- [ ] `snapshot()` (line 272): add `usableLaps`, `paceDeficitS`, `paceClearS`, `stintSigmaS`, `surfaceChannel`, `dRequired` (the add-a-stop break-even, screen-only) — the PTT and pit-wall read from here.

### Per-lap incident data — the supply path

- [ ] **The evidence is already computed live.** `controller.py:1638` calls `read_rows(rows, FRAME_FIELDS, frames.sample_hz)` inside `_on_lap_completed`, and that handler is connected globally (`controller.py:368`), so it runs during a race, not only in practice.
- [ ] **Emission order is favourable and verified:** `bridge.on_packet` emits `lap_completed` (line 249) *before* `session_event` (line 250) for the same lap, and both are queued to the Qt thread in order. So: stash `self._last_lap_evidence = (lap.lap_num, seen)` in `_on_lap_completed` right after line 1638, and read it in `_on_race_event` (line 2353) before calling `self.race.handle(event, evidence=...)`.
- [ ] **Guard the stash by lap number.** If `stashed_lap_num != event lap_num`, pass `None` — treated as *not measured*, so the lap drops out of the series. Never misattribute one lap's evidence to another, and never substitute a zero.
- [ ] Do **not** move `read_rows` into `bridge.on_packet` — that is the UDP thread at 60 Hz and a 6 600-row pass there risks dropped packets.

### `controller.py` — offer plumbing

- [ ] Add `self._pending_pace: PaceOffer | None`, **separate from `_pending_replan`**, and make `_check_replan`'s early return at line 2469 blind to it. An unanswered pace offer must never suppress `replan`'s URGENT fuel-short offer.
- [ ] Auto-expire `_pending_pace` at the end of the following lap.
- [ ] `_show_ptt_answer` (line 2418): route `ACCEPT`/`KEEP` to `_pending_pace` when it is set and `_pending_replan` is not, and call `coordinator.move_stop` on accept.
- [ ] Record every pace call and offer through the existing `store.append_revision` path (line 2374), accepted or not.
- [ ] `_on_race_event` must not let a pace call and a `_check_replan` utterance land on the same lap — gate one behind the other.

### `pitcrew/engineer/intents.py` and `ptt.py`

- [ ] **`INCIDENT_NOTE` asks a question the driver currently cannot answer.** `_YES`/`_NO` in `ptt.py:49-51` only resolve a `pending_confirmation` the recogniser itself raised; with nothing pending, "yes" matches no phrase, returns `UNKNOWN`, and the app replies "Say again." — the worst possible response mid-corner. **Add a driver-report channel** that writes a declared observation onto the race run and marks it PRIMARY against whatever the pace series said at that moment.
- [ ] Add a `TYRE_STATE` intent — phrases `"how are my tyres"`, `"tyre state"`, `"any deg"`, `"am I losing time"` — answered from `snapshot()`: *"Four usable laps this stint, I need six. Can't read them."* or *"Half a second off your first three, seven laps of it."* Refusal, never a guess (the file's own rule).
- [ ] Keep the three-letter minimum on all new phrases.

### Data repair — must run before any threshold is trusted

- [ ] **Backfill `spin_s`.** The v1→v2 `yaw_rate` repair (`telemetry/recorder.py:31-40`) is applied on read but the stored columns were written from unrepaired frames. Recomputing from repaired frames disagrees on 4 of 399 values (stored 0.0 vs recomputed 0.167); recomputed spin fires on 9 laps against 6 stored. Extend the migration at `store/schema.py:558-582` to rewrite the three columns for v1 blobs.
- [ ] **Then recompute and re-commit** σ_lap, σ_d, CLEAR, the usable count and the yield. Every figure in §1 and §2 sits on the pre-backfill set; the shift is well inside the bootstrap CI but it was asserted, not tested.
- [ ] Re-derive the 2.0 s off-track cut after the backfill and re-state it as a selection over ten flagged events.

### Export (`race/outcome.py`, `export/build.py`)

- [ ] Under `derived`: per-stint `usableLaps`, `sigmaS`, `clearS`, `referenceS`, `deficitS`, plus the usable-lap filter's three thresholds and the note that the cut is a ten-event selection.
- [ ] Every pace call, with its `d`, its bar and its usable-lap count. Every `INCIDENT_NOTE` firing **with the contrary evidence attached** — driver-requested gate, no supporting statistic, contrary point estimate — so a later audit sees the app fired his heuristic *against* its own data rather than because of it.
- [ ] Every driver tyre report, beside the pace figure at that moment. Where they disagree, export both. Never average.
- [ ] The strict-vs-usable trade as a table: σ_d 0.59 → 0.87, CLEAR 1.18 → 1.74, stints covered 3 → 6, and the note that only the strict threshold falls inside the phase-2 band.

### Tests (`pitcrew/tests/test_race.py`, `test_incidents.py`)

- [ ] The 23-lap stint (93.9 → 0.5 L) is the fixture. Assert `PACE_BOX` fires **zero times** across all 23 recorded stints under the final thresholds.
- [ ] Assert `PACE_BOX` never reaches `strategy.model`.
- [ ] Assert a null `off_track_s` drops the lap from the series rather than counting as clean.
- [ ] Assert `clear_stint` resets `R` on a fuel-only stop.
- [ ] Assert an unanswered pace offer does not block a subsequent URGENT replan offer.
- [ ] Assert no reachable path from `wear_per_lap` to `voice.say`.
- [ ] Run the suite in quarters (known PyQt segfault on Win/Py3.14).