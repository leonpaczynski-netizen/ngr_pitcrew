# How Pit Crew works with the AI and the NPU

Written 21 Aug 2026, describing the shape as built. Companion to
`PLAN-brain-and-live-engineer_2026-08-21.md`, which says how it got here.

**The one sentence:** the AI thinks *before and after* the race, the app decides
*during* it, and the NPU — if it is ever used — does sensing, not thinking.

---

## 1. Three clocks, three different rules

The programme has three timescales, and almost every design decision comes from
which one a thing lives on.

| | **Between sessions** | **During a session** | **After a session** |
|---|---|---|---|
| Who decides | **Claude, with you** | **The app, alone** | **Claude, with you** |
| Timescale | minutes to days | 16 ms to one lap | minutes |
| Network | fine | **never** | fine |
| Can it be wrong slowly? | yes — you argue back | **no** | yes |

**The race path never waits on anything it does not own.** No network, no
language model, no other process. Everything that speaks to the driver at
racing speed is deterministic code reading a plan that was certified before the
green.

---

## 2. The shape

```
   BETWEEN SESSIONS                DURING THE RACE              AFTER
   ───────────────────             ───────────────              ─────

   ┌───────────────┐
   │  brain/       │  doctrine, driver model,
   │  (git)        │  car and track reference
   └───────┬───────┘
           │ loaded as a skill
   ┌───────▼───────┐   MCP over stdio    ┌──────────────┐
   │    CLAUDE     │◄───────────────────►│  pitcrew-mcp │
   │  you argue    │  reads open         │  reads: all  │
   │  with it      │  writes PROPOSE     │  writes: 2,  │
   └───────┬───────┘                     │  both gated  │
           │                             └──────┬───────┘
           │ proposes a plan                    │
           ▼                                    ▼
   ┌─────────────────────────────────────────────────────┐
   │  strategy/certify.py     THE GATE                   │
   │  tank · tyre life · the flag · compounds · stops    │
   │  refuse / warn / say-what-could-not-be-checked      │
   └───────────────────────┬─────────────────────────────┘
                           │ only a certified plan arms
                           ▼
   ┌─────────────────────────────────────────────────────┐
   │  race/coordinator.py    THE EXECUTOR                 │
   │  one call per lap · re-plan on deviation · offline   │
   └───────┬─────────────────────────────────┬───────────┘
           │                                 │
    ┌──────▼──────┐                   ┌──────▼──────┐
    │ UDP 60 Hz   │                   │  VOICE out  │
    │ telemetry   │                   │  PTT in     │
    └─────────────┘                   └──────┬──────┘
    ┌─────────────┐                          │
    │ OBS 1/lap   │  tyre gauge              │ every exchange
    │ (vision)    │  → measured wear         │ → radio log
    └─────────────┘                          │
                                             ▼
                              ┌──────────────────────────┐
                              │  DEBRIEF → Claude        │
                              │  laps · wear · calls ·   │
                              │  radio · plan vs run     │
                              │  → writes back to brain/ │
                              └──────────────────────────┘
```

---

## 3. Where the AI actually sits

**It never sits between a measurement and your ear.** Three places, all of them
either side of the race:

### Before — setup and strategy

You talk to Claude. It reads this database directly through
`pitcrew/mcp/server.py` — events, sheets, slider ranges with the version they
were read on, laps, the full export payload, and the strategy evidence with
every figure's provenance attached. No pasting.

**Writes propose and never apply.** A proposed sheet lands in the prompt log for
you to apply on the Event screen. A proposed plan is saved *unapproved*.

> The reason is measured, not cautious. The app's `setup` block was stale three
> sessions out of three, and on the third it would have produced a completely
> coherent diagnosis of a car that was not on the circuit. **Which sheet was in
> the car is the one thing only you know.**

### At the gate — certification

Anything Claude proposes is checked by `strategy/certify.py` against the tank,
the tyre's life, the flag, the compounds the event offers and the ones its rules
require. **An uncertified plan cannot be armed**, and the check runs again at
arming, which is the last moment anything can be stopped.

> Also measured: the 12 Aug audit found the app ranking the most impossible plan
> cheapest and asking for **510 litres into a 100 litre tank**. Prose is a better
> author than an optimiser and a worse arithmetician. It gets to propose; it does
> not get to be trusted.

Three verdicts, deliberately: **refuse** (arithmetic, not negotiable), **warn**
(driveable, worth knowing), and **could not check** — because a plan certified by
a gate that skipped half its tests carries the authority without the arithmetic.

### After — the debrief

The outcome prompt now carries the laps, the measured wear, the plan as run
against as planned, the calls and whether they were taken, and **both sides of
the radio, verbatim.** That last one is new and it is the point: the calls ledger
alone cannot tell a call that was right and ignored from a call that was noise
and ignored. The difference is in your reply.

What comes back is written into `brain/` as a versioned change — so the learning
is a diff somebody can read, not a drift somebody notices later.

---

## 4. Where the NPU sits, and why it is smaller than it sounds

**It does not run the race engineer, and it was never going to.**

This machine is an **Intel Core Ultra 5 125U — NPU 3720, roughly 11 TOPS.**
Copilot+ starts at 40. It will not host a language model that gives better race
calls than `race/calls.py` already does, and a mediocre one talking in your ear
at racing speed is worse than silence.

So the division is **perception, not judgement**:

| | Runs on | Status |
|---|---|---|
| Tyre wear from the OBS capture | **CPU — pixel geometry, no model at all** | built, flat screen proven |
| Speech recognition (push-to-talk) | CPU today, NPU *possible* | **deferred — see below** |
| Race calls, strategy, wear model | **CPU, deterministic, no model** | built |

**The NPU is reachable and the cheap route is not.** OpenVINO 2026.3 ships a
`cp314` wheel and finds it — `NPU: Intel(R) AI Boost`. But the ONNX Runtime
OpenVINO *execution provider* publishes wheels up to 3.13 and none for 3.14, so
moving Moonshine onto it means converting the model and replacing its runtime
rather than setting a flag. **Deferred**, because the plan's own rule was "if the
win is not measurable the work stops", and here the win cannot be measured
without doing the work first.

**Note the shape of the OBS reader**, because it is the thing people expect to
need a neural network and does not. It is four rectangles, a red/white threshold
and a row count — verified to 0.5% against two independent stints. Every frame
costs 537 ms of OBS CPU, which at one per lap is 0.6% of one core.

---

## 5. What runs during a race, in order

1. **UDP at 60 Hz** → parse, record, aggregate. Never blocked.
2. **At each crossing:** the lap is stored, then a gauge reading is *requested*
   — one screenshot, on a worker thread, queue one lap deep. It can be dropped,
   fail, or find a paused frame; the lap is already saved either way.
3. **The coordinator** compares what is happening to the certified plan and
   emits **at most one call**, instruction first, reason second and short.
4. **You answer** on push-to-talk. Both sides go into the radio log with the lap.
5. **Nothing in 1–4 touches the network or a language model.**

---

## 6. The rules that hold the shape together

1. **Missing is `null`, never `0`.** A frame that could not be read is not a
   fresh tyre.
2. **Nothing derived is presented as measured** — and a Claude number is derived.
3. **A language model is never the last thing between a number and your ear.**
   The certification gate is.
4. **Your report is primary evidence.** A video wear reading cannot overwrite one
   you gave; where they disagree, the disagreement stays visible.
5. **A threshold that was measured, or silence.** The shift beep has no fallback:
   a gearbox nobody has measured does not beep.
6. **The race path never depends on the network.**
7. **Silence is never a pass.** Whatever could not be checked is named.
