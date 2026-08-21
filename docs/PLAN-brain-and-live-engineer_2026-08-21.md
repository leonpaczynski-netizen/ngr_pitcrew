# Plan — connecting the tuning brain, the app, and a live race engineer

Written 21 Aug 2026. Nothing has been built. This is the plan you asked for
before we do anything.

Three asks, restated:

1. The **"My Driving Style - Tuning"** Claude Project builds and refines setups,
   fed continuously by the UDP feed and by your own feedback.
2. The laptop's **NPU** runs a live in-race engineer, optionally reading tyre
   wear off an **OBS** capture.
3. **Race and qualifying strategy comes from Claude**, discussed with you until
   optimal, loaded into the app, and then assessed and improved live.

---

## 1. What already exists (so we build the gap, not the whole thing)

Surveyed the tree before planning. More of this is already standing than the
brief assumes.

| Capability | State | Where |
|---|---|---|
| Three Claude prompts — brief, refinement, outcome | **Built** | `pitcrew/prompts/build.py` |
| Parsing Claude's reply back into a setup sheet, race + quali, nothing silently dropped | **Built** | `pitcrew/setup/parse.py` |
| Every prompt and reply logged with a version | **Built** | `Store.log_prompt` / `save_prompt_reply` |
| Setup sheet as run, slider ranges per car | **Built** | `Store.save_setup_sheet`, `save_range_record` |
| **Reading the tyre-wear gauge off an OBS capture** | **Built, offline** | `tools/read_hud_wear.py` — verified to 0.5% on session 52 |
| Deterministic strategy: stints, fuel, compound crossover, feasibility | **Built** | `pitcrew/strategy/model.py` |
| Live race execution, one call per lap, re-plan on deviation | **Built** | `pitcrew/race/coordinator.py`, `calls.py`, `replan.py` |
| Push-to-talk, offline ASR + semantic gate, bounded vocabulary | **Built** | `pitcrew/engineer/ptt.py`, `intents.py` |
| Qualifying protocol | **Partial** | `pitcrew/race/qualifying.py` |
| Any network or AI call from the app | **Deliberately absent** | zero `anthropic`/`http` imports in `pitcrew/` |

The seam to Claude therefore already exists and is a **manual copy-paste**. The
work is to close that loop, not to open it.

---

## 2. Three corrections to the brief

These change what gets built. Taking them in order of how much they change it.

### 2.1 The NPU cannot host the race engineer

This laptop is an **Intel Core Ultra 5 125U** — Meteor Lake, NPU 3720, roughly
**11 TOPS**. Copilot+ class starts at 40. It will run small fixed-function
vision and speech models well. It will not run a language model that is a
better race engineer than the deterministic code already in `race/calls.py`,
and a mediocre one talking in your ear at racing speed is worse than silence.

**Reframe: intelligence is compiled *before* the race; the NPU does perception.**

- Claude authors the plan and a **playbook** of pre-authorised responses to
  named contingencies, before the race.
- The app executes it deterministically, at feed rate, offline, with the
  latency and auditability a race demands.
- The NPU's jobs are *senses*, not judgement: speech in (Moonshine ASR and the
  embedding gate, currently on CPU), and vision in (below).

This is not a downgrade of the ambition. It is where the ambition can actually
be delivered on this hardware.

### 2.2 Reading tyre wear off OBS needs no NPU, and is already 80% done

`tools/read_hud_wear.py` already transcribes GT7's own four-bar wear gauge from
a capture: red rows over total rows, per corner. Verified at 0.5% across two
independent stints. It is pixel geometry and a colour threshold — deterministic,
cheap, and it does not want a neural network anywhere near it.

What is missing is that it runs **after** the race on a video file. Making it
run **at each lap crossing, live** is the single highest-value item in this
entire plan, because it converts `CLAUDE.md` §3.3's biggest hole — *"there is no
tyre wear channel, none"* — from a model into a measurement, every lap.

Concretely: OBS on this machine already has obs-websocket at port 4455 with a
password set, but **`server_enabled` is `false`**. One screenshot request per
lap boundary is all this needs.

### 2.3 The deterministic strategy engine must not be replaced — it must be promoted

You want the plan to come from Claude. Agreed. But the engine stops being the
*author* and becomes the **feasibility gate**, and that role is load-bearing.

The precedent is in your own history: the strategy audit found the app ranking
*the most impossible plan cheapest*, and proposing **"Fuel to 510 litres"** into
a 100 litre tank. A language model will produce that class of error more often,
not less, and more fluently. So:

> **Claude proposes. The engine certifies. The coordinator executes.**
> No plan reaches the car without passing tank capacity, stint limit, compound
> evidence and clock checks. An uncertified plan cannot be armed.

`CLAUDE.md` §4.5 already says nothing derived may be presented as measured. A
Claude-authored number is *derived*. It carries its source like every other.

---

## 3. Target architecture

```
                 +------------------------------------------+
                 |  BRAIN  (versioned in this repo)         |
                 |  GT7 physics · your driving model ·      |
                 |  tuning doctrine · call preferences      |
                 +---------------+--------------------------+
                                 |  loaded as Project knowledge
                                 |  AND as a Claude skill
     +---------------------------v---------------------------+
     |  CLAUDE  — setups, race strategy, quali strategy,      |
     |            debrief.  Conversational, you in the loop.  |
     +-----------+-------------------------------+-----------+
         MCP tools|  (read data, file results)    | certified plan
     +-----------v-------------------------------v-----------+
     |  PIT CREW APP                                          |
     |  +-------------+   +--------------+   +--------------+ |
     |  | UDP capture |   | FEASIBILITY  |   | COORDINATOR  | |
     |  |   60 Hz     |-->|    GATE      |-->| one call/lap | |
     |  +-------------+   | (strategy/)  |   +------+-------+ |
     |  +-------------+   +--------------+          |         |
     |  | OBS frame   |---- wear per corner --------+         |
     |  | each lap    |     (measured, not modelled)|         |
     |  +-------------+                             v         |
     |  +-------------+                     +--------------+  |
     |  | NPU: ASR +  |<---- push to talk --|    VOICE     |  |
     |  | semantic    |                     +--------------+  |
     |  +-------------+                                       |
     +--------------------------------------------------------+
```

---

## 4. Phase 0 — spikes, before any building

Four questions whose answers change the design. Each is a day or less. None of
them commits us to anything.

**S1 — Where does the brain live and how does Claude reach it?**
Can Claude Desktop hold the *"My Driving Style - Tuning"* Project knowledge and
talk to a **local MCP server** in the same conversation? If yes, that is the
seam: no API key, no per-token cost, the Project intact, and live tool access to
the database. If no, the fallback is the app calling the Anthropic API directly
with the brain shipped as a skill. **Verify, do not assume.**

**S2 — Does the NPU actually help?**
`onnxruntime` 1.27 is already installed on this Python 3.14. Confirm an Intel NPU
execution path exists for 3.14 (OpenVINO EP or DirectML), then measure Moonshine
push-to-talk latency and CPU load, CPU versus NPU, *while the race stack is
running*. If the win is not measurable, the NPU work stops here and we lose
nothing.

**S3 — Can OBS deliver a frame live?**
Enable obs-websocket, request one source screenshot, measure round-trip and CPU.
Then the question that decides it: **when you are in PSVR2, is the HUD wear
gauge present in what OBS captures?** If the mirrored VR view drops or distorts
the HUD, live wear reading only works on flat-screen races.

**S4 — Is Claude in the loop *during* a race viable?**
Measure API round-trip on your network at race time. A lap is ~90 s, so 3–5 s is
affordable for a once-per-lap consultation. The requirement is not speed, it is
**failure behaviour**: hard timeout, deterministic fallback, and the driver told
which mode he is in.

---

## 5. Phases

Ordered by value per hour, with the dependencies honoured.

### Phase 1 — Get the brain out of the Project and into the repo
*No AI calls. This is the load-bearing step for everything else.*

A brain that lives only in a Project cannot be diffed, tested, versioned, or
reached by anything but you typing into a chat box. Extract it to `brain/`:

- `brain/physics.md` — GT7 post-1.49 model, the §4 standing rules, what GT7
  does not have (no pressure, no caster, no brake pressure, no damper split).
- `brain/driver.md` — **your model, and today it exists nowhere the app can see
  it.** Fuel map 1 only, and never recommend a change. Never move brake bias
  forward. Trail-brakes deep by design. Will not carry a spare lap of fuel in a
  lap race. Lap-to-lap noise σ ≈ 0.9 s, so lap time confirms degradation and
  never warns of it.
- `brain/doctrine.md` — how a setup change is justified, what evidence promotes
  a sheet, what never transfers between tracks.
- `brain/calls.md` — how you like to be spoken to, and when.

Then close the provenance gap: `setup_sheets_v8` records no link to the prompt
reply that produced it. Add one, so *"which Claude conversation produced this
sheet, from which laps"* is a query and not an archaeology exercise.

**Done when:** the Project's knowledge is a set of files under version control,
the Project is re-seeded from them, and every stored sheet points at its origin.

### Phase 2 — The MCP seam
Build `pitcrew-mcp`, a local server over the existing `Store`.

- **Read tools first, and only read:** event, car, sheet, ranges, laps, corners,
  wear, compound profiles, strategy history, prompt log.
- Then **narrow write actions**, each one gated by your confirmation in the app,
  never by the model's say-so: file a setup sheet, save a candidate strategy.
- The export contract stays exactly as it is — it is the payload shape and it
  already works. MCP replaces the *clipboard*, not the *contract*.

**Done when:** you can ask Claude "what did the last three Monza practice runs
say about the rear" and it answers from the database, unpasted.

### Phase 3 — Live tyre wear from OBS *(can run in parallel with 1–2)*
Promote `read_hud_wear.py` from an offline tool to a live sampler: one frame per
lap crossing, four corners, written through `Store.set_lap_wear`.

Guardrails that matter:

- A frame that cannot be read is **null**, never zero, and never last lap's value.
- Measured wear is tagged as measured and **outranks the model** — but the model
  keeps running alongside it, and when the two disagree that disagreement is a
  finding, not something to average away.
- The gauge resetting to white is a far better tyre-change detector than the
  temperature convergence currently used. Switch to it.
- It must be impossible for OBS being shut, wrong-sized, or slow to affect the
  race calls. Perception degrades; the race does not.

**Done when:** a race produces a per-corner wear curve measured every lap, and
the stint-length model can be scored against the truth for the first time.

### Phase 4 — Invert strategy authorship

- Define a **Race Plan artifact**: stints, compounds, fuel, the contingencies,
  and every assumption named. Versioned, stored, diffable.
- Claude authors candidates in conversation with you, using MCP to read the real
  evidence. You argue with it. That conversation is the deliverable.
- The engine **certifies** the chosen plan — capacity, stint limits, clock,
  compound evidence — and refuses to arm what it cannot certify, with the reason
  in words.
- The coordinator executes it unchanged. Live deviation triggers the existing
  re-plan path.

Only after that works: optional Claude-in-the-loop once per lap, behind S4's
timeout and fallback.

### Phase 5 — Qualifying
Extend the same shape to quali: Claude issues the quali sheet and the session
protocol — out-lap or flying lap, fuel load and therefore weight, tyre
temperature build. The app runs it and reports back what the tyres actually did.

### Phase 6 — The engineer that learns to be an engineer

- Move ASR and the semantic gate onto the NPU, **if S2 showed a real win**.
- Widen push-to-talk beyond the fixed vocabulary — carefully. The current
  bounded vocabulary exists because a confident mishearing at speed is worse
  than a refusal. Anything wider must keep the refusal.
- Log every call made, whether you acted on it, and what you said back. That log
  is what Claude reads at debrief to learn which calls help and which are noise —
  the app never self-tunes its own voice from it.

### Phase 7 — Debrief
The `outcome` prompt already exists and is the right shape. Give it the new
evidence — measured wear, the plan as run versus as planned, the calls and your
responses — and let the debrief write back into `brain/` as a versioned change.
That is the learning loop closed, and it is auditable because it is a diff.

---

## 6. Rules this plan does not get to break

Carried from `CLAUDE.md` and from things already learned the hard way.

1. **Missing is `null`, never `0`.** A failed frame read is not a fresh tyre.
2. **Nothing derived is presented as measured** — and a Claude number is derived.
3. **A language model is never the last thing between a number and your ear.**
   The feasibility gate is.
4. **Your report stays primary evidence.** Where you and the data disagree, that
   is the finding.
5. **One call per lap, instruction first, reason second and short.**
6. **The race path never depends on the network.** Claude may improve the plan
   before the race and may consult during it; it may never be required for the
   app to run one.
7. **The deterministic engine is not deleted.** It is the thing that makes an
   AI-authored plan safe to arm.

---

## 7. Decisions taken, 21 Aug 2026

- **OBS captures the PS5 through a capture card.** So the game's own HUD is in
  frame at known geometry, and live wear reading has a real source. Phase 3 is
  viable as written.
- **MCP first, API later.** A local MCP server against `Store`, driven from
  Claude Desktop, with the Project's knowledge intact. No API key, no per-token
  cost, and you stay in the conversation. The Anthropic API is a later addition
  for unattended work (debrief, refinement), not a prerequisite. This also keeps
  rule 6 below true by construction: the race path never touches the network.
- **Build order: Phase 3 first** — live wear from OBS. It is independent of the
  AI work, it is the highest value per hour, and it means the next race is run
  with measured wear rather than modelled wear. Phase 1 (brain extraction) runs
  behind it, then Phase 2 (MCP).
- **This laptop is the race machine.** COM5 — the wind simulator's Arduino —
  answers here, so the NPU, OBS and the race stack are all on one box.

### Still open

1. **In PSVR2, does the capture still show the HUD wear gauge?** Answered by
   spike S3. If the mirrored VR view drops or distorts it, live wear reading
   works on flat-screen races only — and that is worth knowing before the plan
   leans on it.
2. **Is there anything in the Project that cannot be exported to files** —
   uploaded documents, artifacts, chat history you rely on? Blocks Phase 1 only.
