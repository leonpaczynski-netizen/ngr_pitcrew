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

1. **Is there anything in the Project that cannot be exported to files** —
   uploaded documents, artifacts, chat history you rely on? Blocks Phase 1 only.

---

## 8. Spike S3 — run 21 Aug 2026

### Transport: works, and it is cheap enough

obs-websocket 5.7.4 on OBS 32.2.2, port 4455. Measured against a control
window, so the figure is the screenshot's cost and not OBS's own render load:

| | |
|---|---|
| OBS alone, rendering and capturing as usual | 16.1% of one core |
| OBS + one screenshot per second | 67.4% of one core |
| Cost attributable to one screenshot | ~537 ms CPU, 520 ms round-trip |
| **At one screenshot per 90-second lap** | **0.60% of one core, sustained** |

Two things production must inherit:

- **A 1720x916 PNG is ~2 MB and `websockets` caps frames at 1 MB by default.**
  It does not truncate — it closes the socket with a 1009. Mid-race that reads
  as "OBS went away" rather than "the frame was large". Set `max_size`.
- Screenshot **the scene, not the `PS5` source.** The scene renders at the
  canvas resolution; the source returns the card's own, and every calibrated
  constant would need re-probing.

### Flat screen: the calibrated geometry still lands

The canvas is **1720x916 — exactly** what `LAYOUT_1720x916` was derived from,
and the four bars sit on the calibrated rectangles. No re-probing needed.

**The pause menu dims and desaturates by ~45%**: every bar peaks at
`(137,137,137)` where production needs `>150` for white and `r>110` for red, so
all four read `None`. That is the correct refusal, and it gives the live sampler
a firm rule: **detect the dim and skip the frame — never relax the thresholds to
compensate.** Relaxing them lets a dimmed frame produce a number, and a wrong
wear figure is far worse than a missing one.

**Proven end to end.** Ten consecutive live reads over ~27 s of driving, through
OBS → websocket → the calibrated layout → `read_hud_wear._read_bars` unmodified.
No re-probing, no code change, `peak = 255` on every frame:

| | start | end | over 27 s |
|---|---|---|---|
| FL | 40.0% | 46.7% | +6.7 |
| FR | 23.3% | 26.7% | +3.4 |
| **RL** | **50.0%** | **60.0%** | **+10.0** |
| RR | 36.7% | 46.7% | +10.0 |

**Zero reversals across all forty readings**, and every step is either nothing or
exactly one quantum (3.3–3.4 points = the gauge's 1/30 pixel). Wear is monotonic
and the reader never once produced a value that went backwards — which is the
strongest available evidence that it is reading the instrument and not noise.

The dim detector also did its job: **10 live frames, 9 dim/paused polls**, cleanly
separated with no dimmed frame producing a number.

Two observations that are findings in their own right:

- **The car is rear-limited and RL is the worst corner** — matching all eight of
  the driver's previous gauge readings, where a front has never once been worst.
- **The rate is very fast** — ~10 points in 27 s on both rears. That implies a
  wear multiplier well above race settings in this session. Worth confirming
  rather than assuming, but it is exactly the kind of thing the live sampler
  will make visible from now on.

### VR: the gauge IS there — and it moves

**An earlier reading of this was wrong and is withdrawn.** The gauge box was
empty in VR and no HUD was visible in the frames to hand, so it was recorded as
"GT7 draws no HUD in VR". The 48-second recording
`C:\Users\leons\Videos\2026-08-21 16-50-36.mp4` shows otherwise:

- **In VR the HUD is drawn on the car's dashboard in 3D**, not as a screen-space
  overlay. It is present, complete with the four-bar tyre cluster.
- **So it translates and skews with head position.** Located across the drive,
  the cluster moved roughly **x 1240 → 1453, y 360 → 455** — about 200 px
  horizontally — during ordinary driving. *A fixed rectangle tracks nothing.*
- **It is much smaller: bars are 18–20 px tall against 30 px flat.** One pixel is
  therefore **~5.6% of tyre life, which at Monza is about one full lap** —
  against 3.3% flat.
- A first-cut locator (find a short vertical strip that is red over white, then
  demand a 2×2 cluster) found it on **2 frames in 15**. That number is about the
  detector, not the ceiling. **The quantisation floor is the fundamental part.**

Consequence for Phase 3: **live wear reading is materially harder in VR than on
a flat screen, but it is not out of reach.** It needs

1. a **per-frame locator** rather than fixed geometry — anchor on the car icon;
2. **many samples per lap**, since the hit rate will never be 100%;
3. **fitting a slope across a stint rather than trusting any single reading** —
   which is exactly how the offline tool already reaches 0.5% accuracy from a
   gauge quantised at 3.3%. That discipline is what makes the coarser VR gauge
   survivable, and it is already the design.

**S3 verdict: flat screen is proven and ready to build; VR is possible but
needs a per-frame locator.** Phase 3 therefore ships in two stages - the flat-screen
sampler first, since it works today with the constants already in the repo, and
the VR locator second as its own piece of work with its own accuracy target.

---

## 9. Spike S1 — run 21 Aug 2026

### The finding that reframes the question

**The transport is already solved, and it has been all along.**

`%APPDATA%\Claude\claude_desktop_config.json` on this machine has **no
`mcpServers` key at all**. What it has instead is `coworkUserFilesPath`,
`ccdScheduledTasksEnabled`, and a `remoteSessionFolderGrants` block granting
three sessions access to `C:\Projects\VR_Dashboard`. This is the Claude Code
Desktop build, and it is already wired to the repo.

So Claude — in a session exactly like the one that wrote this document — already
has the repository, the SQLite database, `CLAUDE.md`, `EXPORT-CONTRACT.md`, and
memory that persists between sessions. It can run arbitrary analysis against
`Store`, which is **strictly more capable than any fixed MCP tool surface**.

**What is missing is not a pipe. It is the brain**, which lives in a claude.ai
Project that a Claude Code session cannot see. That was Phase 1's job already,
and S1 raises it from "load-bearing" to "very nearly the whole of seamless".

### The MCP server is still proven, and still worth having

Built a throwaway read-only server over the real `Store` and drove it over stdio
end to end:

```
connected: pitcrew-spike (protocol 2025-11-25)
tools: ['list_events', 'cars_with_range_records', 'setup_sheet']
cars_with_range_records -> Ford Shelby GT350R '16,
                           Lamborghini Huracan GT3 '15,
                           Porsche 911 RSR (991) '17
```

Real database, real rows. Notes for Phase 2:

- **`mcp` 2.0.0 supports Python 3.14** and installs clean. No version risk.
- **The 2.x API moved.** `mcp.server.fastmcp.FastMCP` is gone; it is
  `mcp.server.mcpserver.MCPServer`, and result fields are snake_case
  (`server_info`, not `serverInfo`). Any 1.x example found online needs porting.
- Open the store per call, or with a read-only URI. **The server must never hold
  a lock the app needs during a session.**

Where the MCP server earns its place is **bounded** access — the claude.ai
Project reaching the data through a connector, and gated write actions — not
the analysis conversation, which Claude Code already does better.

### Revised recommendation

1. **Phase 1 (brain into the repo) becomes the whole of the near-term work.**
   With Claude Code Desktop already on the race machine, extracting the brain to
   `brain/` and shipping it as a skill closes the loop with no new plumbing.
   A skills directory already exists and works.
2. **Phase 2 (MCP) drops in priority** and is re-scoped to the Project/connector
   case and to safe writes.
3. The trade to be aware of: **Claude Code is tied to this machine; the claude.ai
   Project is reachable from anywhere.** If setup work away from the rig matters,
   the Project stays and the MCP connector matters more than this suggests.

### What is actually in the Project

Answered: **the Project's knowledge is essentially all markdown**, so nothing is
trapped in a format that will not come out. Four of the files are already on disk
in `~/Downloads`, and their names show the shape of the whole set:

| File | What it is |
|---|---|
| `06-race-strategy-design-research-2026-08-12.md` (61 KB) | **Doctrine** — how strategy *should* be calculated, with a v1→v2 amendment table recording six recommendations that "did not survive contact with the code" |
| `15-pitcrew-detector-audit.md` | **Doctrine about this app** — what the detector flags actually measure |
| `2026-08-11-rsr-monza.md` (35 KB) | **An event output** — the sheet, the reasoning per value, the gearing derivation, the fuel arithmetic, the tests to run |
| `2026-08-10_Huracan_LagunaSeca.md` | Same, for a different event |

Two categories, and they belong in different places:

- **Numbered doctrine files (at least 01–15)** → `brain/`, versioned, loaded as a
  skill. This is the reusable knowledge.
- **Dated event documents** → alongside the sheets they produced. **These carry
  far more than `setup_sheets_v8` stores** — the *why* behind every value, which
  is exactly what makes the next revision good, and today it exists only in
  Downloads and the Project. This is the other half of the provenance gap.

### Phase 1 is a merge, not a copy

Two things make a straight import wrong:

1. **Some of the doctrine is already superseded.** The detector audit's
   `bottoming` finding, for instance, has since been withdrawn — the flag fires
   on the most *extended* wheel because GT7's suspension channel reads
   larger-is-more-compressed, and the rationale it bought for a ride-height raise
   went with it. Importing that as-is would re-import a known-wrong rule.
   **Corrections learned since have accumulated in session memory, not in the
   Project documents.**
2. **Volume.** One doctrine file is 61 KB. Fifteen of them cannot all be
   always-loaded context. Phase 1 needs a triage into a small always-loaded core,
   an on-demand reference tier, and an archive of what has been superseded —
   with the supersessions *recorded* rather than deleted, the same way §8 keeps
   the withdrawn VR conclusion visible.

