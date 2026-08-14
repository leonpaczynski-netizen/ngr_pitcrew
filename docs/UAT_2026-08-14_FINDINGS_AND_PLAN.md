# Pit Crew — UAT 14 Aug 2026: findings and implementation plan

Written against the DB as it stood at 14:26 on 14 Aug 2026: 3 events, 19 practice
sessions, 132 laps with full 60 Hz frames. Every number below is measured out of
that data, not estimated. Where I could not measure something I say so.

The headline: **six of your sixteen items are one bug**, and I can point at the
line. The rest split into four genuinely new features and a handful of small
corrections.

---

## Part 1 — What the data says

### 1.1 The pit stop the app cannot see (your items 1, 4, 13, and half of 3)

You have exactly one pit stop in the database: session 19, lap 14, at Monza on
14 Aug. It is unmistakable — the lap took 182.4 s against a 108.5 s median, the
tank went from 20.7 L to 71.9 L, and all four tyres were changed. The app
recorded `is_pit_lap = 0` and `is_out_lap = 0`.

So does every other lap in the database. **All 132 of them.** No lap has ever
been flagged as a pit lap or an out lap, in any session, at any event.

The cause is one line, `pitcrew/telemetry/session_state.py:242`:

```python
refuelling = (
    p.fuel_level > self._prev.fuel_level + 0.05
    and p.speed_kmh < PIT_MAX_SPEED_KMH
)
```

That compares **one frame to the previous frame**. GT7 fills the tank at about
1 L/s and the stream runs at 60 Hz, so the tank rises by roughly **0.0167 L per
frame**. I decoded all 17,998 frames of that lap: 3,790 consecutive frames show
fuel rising, the largest single-frame step is **0.0170 L**, and the number of
frames clearing the 0.05 L gate is **zero**.

The gate is about three times higher than the signal. It cannot fire, has never
fired, and never will. Everything downstream inherits it:

| Depends on `is_pit_lap` | What it does today |
|---|---|
| `analysis/runs.py::starts_run` | never starts a new run at a stop |
| `analysis/runs.py::auto_out_laps` | never marks an out-lap |
| `ui/practice_screen.py::stint_end_ids` | never offers the end-of-stint gauge |
| `prompts/build.py` | tells the knowledge base the race had no stops |
| `race/outcome.py::pit_laps` | returns empty |

Your item 13 — "the first lap of every stint will always be an out lap, I don't
want to strike it every time" — is already written (`runs.auto_out_laps`). It has
simply never had a run boundary to fire on.

There are two more defects sitting behind that one:

**The stop is split in two.** The offline detector `telemetry/pit_detect.py`
does use a windowed fuel comparison and would work — except it ends a stationary
window on any frame above 2 km/h, and the trace carries a 51 km/h blip in the
middle of the box stop. It sees two stops of 9.8 s and 68.7 s instead of one.

**A tyres-only stop has no detector at all.** Not a threshold problem — there is
no code path. `_update_pit` is reached only through `refuelling`.

### 1.2 The tyre change is visible, and cleanly (your item 2)

You asked for a tyre change detected from a temperature drop below 10 km/h. The
signal is better than that. Here is the stop, one reading per 3 s:

```
   t_s   spd   fuel     FL    FR    RL    RR
 121.3   0.0  14.65   73.8  67.6  82.9  79.8
 124.3   0.0  14.65   60.0  60.0  60.0  60.0   <- one frame
 127.3   0.0  17.22   59.8  59.8  59.8  59.8   <- fuel starts, 3 s later
```

GT7 does not cool the tyres down. It **replaces all four with one identical
value in a single frame** — mean 75.8 °C to 60.0 °C, all four corners landing
within 0.5 °C of each other.

I ran that signature across all 132 laps: *all four corners drop ≥5 °C in one
frame and converge to within 0.5 °C*. It fires **once** — on the one real tyre
change. Zero false positives across every session in the database.

That also corrects a stored constant. `analysis/thresholds.py` has:

```python
FRESH_TYRE_TEMP_C = 70.0   # "GT7 fits every set at the same temperature"
```

It does not. Fitting temperatures observed across the database run from **60.0 to
70.0 °C** — s2 opened at 66.8, s6 at 66.0, s15 at 69.5, s16 at 68.6, and this
stop fitted at 60.0. It tracks time of day (this stop was at 18:50 game time
against a 15:56 session start). The absolute value is not usable; the
*convergence* is. As written, `fresh_by_temperature` returns `None` for the one
genuine tyre change in the database — which is exactly your complaint that the
app does not notice new cold tyres.

This is the same class of defect as the fabricated tyre windows in `store/tyres.py`
that we found on 13 Aug: a plausible constant, documented as measured, that the
data does not support.

### 1.3 The game clock is measured, then thrown away — and the cached copy is wrong (your item 6)

You said practice has not updated start hour or time multiplier in event
settings. Correct, and it is worse than not updating.

The clock **is** measured. `analysis/gameclock.py` reads GT7's own clock out of
the frames, and it works — session 18 gives a clean ×6.00:

```
  s18 lap 2: 16.122h -> 16.307h   game 663.1s / real 110.5s  = x6.00
  s18 lap 3: 16.307h -> 16.490h   game 659.6s / real 110.0s  = x6.00
```

Two things then go wrong.

**It is never written back.** `strategy/evidence.py:447` saves the reading into
the `track_clock` table. Nothing ever copies it to `events.start_hour` or
`events.time_multiplier`. All three events still hold `NULL` for both.

**The cached reading is wrong.** This is the serious one. Here is the row that is
now on file for Monza:

```
circuit_key: autodromo-nazionale-monza
preset:      Day to night transition
start_hour:  18.833      multiplier: 0.0      laps_sampled: 6
```

It says the Monza night lobby holds a **fixed** time of day at 18:50. It does
not — it starts at 15:56 and runs at ×6 until the clock stops at 18:50.

The cause is `strategy/evidence.py::_laps_to_hydrate`, which decodes frames for
only the **last 6 counted laps per compound** (`WINDOW_SAMPLE_LAPS = 6`). At
Monza those 6 laps are s19's final laps — the ones *after* the pit stop, where
GT7's clock had already run to its ceiling and frozen:

```
  s19 lap13: 18.155h -> 18.335h  span= 649.1s     <- moving, x6
  s19 lap14: 18.335h -> 18.833h  span=1792.5s     <- the pit stop
  s19 lap15: 18.833h -> 18.833h  span=   0.0s     <- frozen
  ... laps 16-26 all 18.833h, span 0.0s
```

The clock reader saw six frozen laps, concluded `multiplier = 0.0`, and cached
it. Strategy is now planning a Monza night race against "fixed at 18:50", and
`practice_clock_warning` will tell you your practice was frozen when in fact it
was the only session that swept the whole span correctly.

**That row must be deleted, not just recomputed.**

### 1.4 Why the screens are clipped (your item 8)

Not a stylesheet problem. Your displays:

```
DISPLAY2  2560x1440   working 2560x1392   (primary)
DISPLAY3  2560x1080   working 2560x1032
DISPLAY1  1280x800    working 1280x752    <- panel is physically 1920x1200, so 150% scaling
```

`app.py:37` sets `WINDOW = (1600, 1000)` and `app.py:234` does `self.resize(*WINDOW)`
with no clamp to available geometry. On DISPLAY1 the window is wider than the
screen by 320 px and taller by 248 px.

The practice rack then makes it unrecoverable. Its columns are fixed pixel
widths summing to ~984 px of content, and the code says so explicitly
(`practice_screen.py:483`):

> *"The rack's columns are fixed width and set the window's own minimum, so it
> can never be given less than it needs anyway."*

— while the horizontal scrollbar is set to `ScrollBarAlwaysOff` on the line
below. When the assumption fails, there is no scrollbar to recover with. Content
is simply cut off. That is the horizontal corruption, and it will appear on
every screen with a fixed-width row, not just Practice.

### 1.5 GT7 version does not block anything (your item 5)

I traced every reference. `events.game_version` is written into the export
payload and the setup-sheet payload and read nowhere else. The event form
requires only name, track and car (`event_screen.py:964`). Nothing in the
telemetry path reads it.

So it is not blocking telemetry — but a field that looks mandatory and isn't is
still a defect. It belongs in app settings once, not on every event.

### 1.6 The app cannot talk to the PS5 (your item 9)

Half-built, and the hard half is done. `telemetry/packet.py` already implements
the full Salsa20 decryption — key, the 0xDEADBEEF IV mask, the `G7S0` magic
check, and a fallback to the legacy 0xDEADBEAF mask. It decrypts real GT7
packets today.

What is missing is the **heartbeat**. `telemetry/listener.py` only binds a port
and waits. The console will not stream to an address that has not sent it a
heartbeat byte. The "Only accept from" IP box in Settings is an accept-filter on
inbound packets, not a destination — which is why setting it does nothing.

Direct mode is: send `C` to `<PS5 IP>:33739` on a timer, listen on 33740, decrypt
with code that already exists.

### 1.7 Spins and offs are detectable, but not with one threshold (your item 14)

The per-wheel surface channel works. The clear incidents:

| Session/lap | Lap time | Off-tarmac | Evidence |
|---|---|---|---|
| s9 L12 | 137.9 s (+28) | 17.6 s | long excursion |
| s17 L11 | 121.5 s (+15) | 11.3 s | long excursion |
| s10 L14 | 126.7 s (+18) | 8.1 s | excursion, yaw 1.69 |
| s9 L6 | 123.3 s (+14) | 0.2 s | 20 frames of yaw >1.2 rad/s at low speed |

But a naive threshold is useless: **1–3 s off tarmac-and-kerb is normal on a
clean Monza lap** — it is the astroturf at the exits. Around 70 of 132 laps
would flag. It needs two signals: excess over the stint's clean median **and** a
corroborating incident (a sustained excursion, or a yaw/slip event).

Note s9 L6 has almost no off-track time — a spin that stayed on the road. Yaw
rate is the only thing that catches it, so both signals are needed.

### 1.8 Recency weighting is worth having, and I can size it (your item 15)

Event 1 clean-lap medians, oldest to newest:

```
  s1  108.92s (n=3)     s9  109.44s (n=12)    s18 109.95s (n=13)
  s6  109.42s (n=3)     s10 109.48s (n=13)    s19 109.06s (n=23)
  s7  108.56s (n=9)
```

Pooled unweighted: **109.43 s**. Latest session alone: **109.06 s**. A 0.37 s/lap
difference. Over ~27 laps of a 50-minute Monza race that is about **10 s of
cumulative plan error**, and because stint length is set by where degradation
crosses a threshold, a biased reference pace moves the stop lap too.

Worth doing — and worth being honest that 0.37 s is not a huge signal on this
data set. It will matter more as the setup actually changes between sessions.

### 1.9 Two things you did not report

**The first recorded lap of a session is often not a lap you drove.** Lap 1's
frame buffer always runs longer than its reported lap time, because the recorder
starts buffering the moment the app connects, in the garage:

```
  s16 L1:  113.5 s reported,  294.2 s of frames   (+180.7)
  s15 L1:  100.4 s reported,  177.7 s of frames   (+77.2)
  s14 L1:   99.2 s reported,  154.2 s of frames   (+55.0)
```

And in 8 of 13 sessions lap 1 is *faster* than the session median — s12's lap 1
by 13.8 s. GT7's `last_lap_ms` still holds a value from before the app was
watching, and the app records it as lap 1. So your "first lap is always an out
lap" is right in spirit, but the app needs to tell an out-lap from a **phantom
lap that was never driven in this session**. Striking it as an out-lap would
launder a fabricated lap time into the evidence.

**The measured out-lap penalty.** s19 lap 15 (the real post-stop out-lap) ran
110.85 s against a stint-2 median of 108.69 s: **+2.17 s**. That is consistent
with CLAUDE.md §5.4's 0.5–1.5 s cold out-lap plus the pit-exit portion, and it
is a number the strategy model should use rather than assume.

---

## Part 2 — The plan

Ordered by return per hour. Phases 1 and 2 are corrections to things that are
actively producing wrong output; everything after is new capability.

### Phase 1 — Stop the wrong answers (highest priority)

**1.1 Fix pit detection.** Replace the per-frame fuel gate in
`session_state._update_pit` with a windowed one: fuel rising by ≥0.3 L across a
rolling ~2 s window while speed is under the pit-lane threshold. Measured signal
is 1 L/s, so 0.3 L in 2 s has 6× margin and still clears float noise.

**1.2 Add the tyre-change detector.** New signal, live and offline: all four
corners drop ≥5 °C in one frame and land within 0.5 °C of each other. Fires a
stop on its own, so a tyres-only stop is seen. Zero false positives on the 132
laps we have. This is what makes your item 2 work.

**1.3 Fix the stationary-window split** in `pit_detect.find_stops` — allow brief
excursions above the stopped threshold inside a window (hysteresis, ~1 s)
instead of ending it.

**1.4 Correct the fresh-tyre threshold.** Drop `FRESH_TYRE_TEMP_C = 70.0` as an
absolute test. Keep the spread test, add the convergence-step test, and record
the *observed* fitting temperature per stop rather than asserting a constant.
Bump `DETECTOR_VERSION`.

**1.5 Delete the poisoned `track_clock` row** and fix `_laps_to_hydrate` so the
clock is read from a lap set chosen for the clock, not from the last 6 laps of
whatever compound. Reading the clock needs only the first and last
`time_of_day_ms` of each lap — that can be stored per-lap at capture time and
never needs a frame decode at all.

**1.6 Clamp the window to the screen** and make the rack survive being narrow:
`resize(min(WINDOW, availableGeometry))`, move the column heads inside the
scroll area, set the horizontal policy to `AsNeeded`, and convert the fixed
column widths to minimums with a priority order for what collapses first.

*After 1.1–1.5, every session in the database should be re-aggregated. The frames
are all still on disk, which is exactly the case CLAUDE.md §6 kept them for.*

### Phase 2 — The things you have to redo by hand every session

**2.1 Stint headers.** A `StintHeader` row above each stint in the rack: best,
median, average fuel per lap, lap count, compound, and — free, because
`time_of_day_ms` is already captured — **game clock start and end** (your item
16). Same three statistics as the session total so they read as comparable.

**2.2 Compound carries forward.** Tag the compound once at the stint's first lap
and fill forward to the stint end or the next detected tyre change. Keep a
per-lap override. Requires 1.1/1.2 for the boundaries to exist.

**2.3 Out-laps handled automatically.** With run boundaries working,
`auto_out_laps` fires. Two changes: include the session's first lap (it is
currently excluded by `run.first_lap != laps[0].lap_num`), and show out-laps
**in the rack with an OUT tag rather than struck through** — you said you want to
see them, and they carry real information about tyre warm-up.

**2.4 Phantom first laps.** Where lap 1's frame buffer materially exceeds its
reported lap time and the lap is faster than the session median, mark it
`not-driven-in-this-session` and exclude it from everything. This is a new
exclusion reason, not an out-lap.

**2.5 Incident detection.** Two-signal rule per §1.7. Adds the `incident`
exclusion reason (already in the `EXCLUSION_REASONS` vocabulary) with the
evidence attached — "3.2 s off-track at T4, +18.1 s". Strategy drops these; setup
analysis keeps them, which is your item 14 exactly. Export declares both
thresholds under `derived`.

**2.6 Write the measured clock back to the event.** Start hour and multiplier
land in the event form marked as measured, and can be overridden by hand — the
existing measured/declared/assumed ink already covers the distinction.

**2.7 Move GT7 version out of the event form** into app settings. One value, set
once, travels into every export as it does now.

### Phase 3 — New capability

**3.1 Direct PS5 connection.** A source mode in Settings — *SimHub relay* or
*PS5 direct* — with a PS5 IP field. Direct mode sends the `C` heartbeat to
33739 on a ~1 s timer and listens on 33740. Decryption is already written.

CLAUDE.md §3.1 flags the port pair as verify-before-building, so this ships with
a connection self-test that reports **which format decoded and at what rate**,
and fails loudly rather than degrading to zeros. Worth doing early because it
removes SimHub from the chain entirely.

**3.2 The VR session banner.** Full-screen, high-contrast, very large type, on a
timer, for practice start / stop / lap complete / box-this-lap. Designed to be
read through passthrough at a glance — one number or three words, nothing else.
This is the same constraint as §5.5's live calls, applied to the screen.

**3.3 Quali and race setups as separate objects.** A `purpose` column on
`setup_sheets` (`race` | `qualifying`), both loadable per event, and a session
intent so **Quali practice** and **Race practice** are distinct modes:

- *Quali practice* — one-lap peak, best sector composite, tyre state at the
  peak lap, low fuel. Degradation is noise here.
- *Race practice* — stint consistency, degradation, fuel burn, out-lap cost.
  A single fast lap is noise here.

Same rack, different aggregates and a different export emphasis.

**3.4 Full race practice against AI.** `sessions.kind` already supports `race`
and `controller.start_race()` exists. What is needed is a **rehearsal** flag so a
practice race is evidence without being the league race, and so its stints,
stops and out-laps feed the strategy model as the highest-quality evidence
available — it is the only source that produces a real stop under race
conditions. This is the single best answer to "prove race strat and get
consistency", and it becomes possible only once Phase 1 can see a pit stop.

**3.5 Recency weighting.** Exponential decay on the reference pace and
degradation rate, keyed on session order and on setup revision — a lap run on a
superseded sheet should weigh less than one on the current sheet, which matters
more than age. The weighting and its half-life go in the export under `derived`
so a plan can be audited. Sized at ~0.37 s/lap on today's data (§1.8).

### Phase 4 — Prompts

**4.1 Add a return contract.** All three prompts (`brief`, `refinement`,
`outcome`) currently ask for markdown — "side by side", "manually enterable".
There is no schema. `setup/parse.py` can already read the export contract's own
JSON, so the reader exists and the prompt simply never asks for it.

Add a `returnContract` block to `templates.json` specifying an exact JSON
envelope: the setup keys from `setup/vocabulary.py`, gears as an array, a
per-value `why`, and each value as absolute + clicks-from-min + percent-of-range
as the prompts already require in prose. Ask for the JSON **and** the readable
sheet — you need to read it, the app needs to parse it.

**4.2 Tighten the wording** and bump to `pitcrew-prompts/1.1`. The version
already travels in every footer and is stored on every issued prompt, so old
replies stay traceable.

---

## Sequencing

Phase 1 first and as one piece — 1.1 through 1.5 are the same bug seen from five
angles, and re-aggregating the stored sessions once at the end of it is worth
more than any of them individually. 1.6 is independent and can go in parallel.

Phase 2 depends on Phase 1 for its boundaries. Phase 3.1 is independent of
everything and can be done whenever. Phase 3.4 depends on Phase 1. Phase 4 is
independent of all of it.

## What I have not resolved

- **Whether GT7's fitting temperature tracks track temperature or time of day.**
  Two data points (60.0 at 18:50, 70.0 at various session starts) is a pattern,
  not a model. The convergence detector does not need it, so nothing is blocked —
  but do not let a constant get written down for it.
- **The 51 km/h blip mid-stop.** It is one frame region in a stationary car. It
  could be a decode artefact or a genuine GT7 quirk. The hysteresis in 1.3 makes
  it harmless either way, but it is worth a look before trusting any per-frame
  speed gate.
- **The direct-connection port pair**, per CLAUDE.md §3.1. To be confirmed
  against hardware, not documentation.
