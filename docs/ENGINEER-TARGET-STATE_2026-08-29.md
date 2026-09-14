# The target state — where Pit Crew is going

**Written 29 Aug 2026**, from a full design interview with the driver on the
same date. Companion to `RACE-ENGINEER-CHARTER_2026-08-23.md`, which it does
not replace: the charter set the standard and found the gaps, and this decides
what the app becomes. Where the two differ, this is the later record.

Nothing here overrides `CLAUDE.md` or `EXPORT-CONTRACT.md`. Two decisions
below **do** change doctrine that is currently written into the code, and both
are marked ⚠ where they appear.

---

## 0. The architecture, in one sentence

**Ludo authors, the app instruments, and George executes — free within the
plan's shape, bounded at its structure, and briefed by a record Ludo writes
into the database before the flag.**

Everything below follows from that sentence. It resolves the tension the
charter left open: `PRODUCT.md` says the app deliberately does not author
setups, and the charter says the app's fifth job is to be the race engineer.
Both are true, because they are about different clocks. **Ludo owns everything
with a human in the loop and time to think. George owns what happens inside a
lap with a helmet on.**

---

## 1. The decisions

| # | Decision |
|---|---|
| D1 | **The app is the instrument; Ludo is the engineer.** Every judgement — setup, plan, diagnosis — is authored outside and handed in. |
| D2 | **George decides freely during a race** and the driver overrides on the radio. |
| D3 | **The rail gates four calls only** — add a stop, remove a stop, change compound, abandon the plan. Everything that changes only *when* within the plan's shape is free. |
| D4 | **George sees live race position** and the size of the field. |
| D5 | **Rivals are read after the race, not during it.** Live rival vision in VR is refused on evidence, not on effort. |
| D6 | **No model runs in the live loop.** George stays deterministic. Everything smart is precomputed. |
| D7 | **Two registers: George volunteers decisions and answers facts on request.** Position is the single documented exception — it is a fact and he volunteers it anyway. **Amended 14 Sep 2026 by the driver after Bathurst Rd7 ("want more comms from him about what is going on in the race"):** George also volunteers the gap ahead and behind with names, rival stops and what they mean for us (on the road versus after the stops), championship rivals' running positions, and pace against the car ahead or behind. There is no per-lap talk cap ("talk whenever it matters"). **Amended again 15 Sep 2026 by the driver: "George can speak at anytime."** Nothing is withheld for want of a straight: on the Bathurst replay the straight gate (14 Sep) left 28 of 52 mid-lap lines stale, because Mountain to Conrod is about a minute and news is stale in 12-20 s. The only ordering is the radio's own: instructions first, then the crossing's calls, then news, then the data line, each waiting only behind other speech and dropped (and returned to the race, which composes it again) once it is too late to still be true. Every volunteered figure still carries its source and hedge (CLAUDE.md §4 rules 4, 5, 13). |
| D8 | **Free dictation through the existing gate**, not a closed phrase list. |
| D9 | **A per-event knowledge record** carries race-specific numbers Ludo writes and George's rules consume. |
| D10 | **Wear is measured off the replay and carried forward**; the live gauge corrects the measured baseline rather than being the baseline. |
| D11 | **The database is the single source of truth** for both the app and Ludo. |
| D12 | ⚠ **Ludo writes setup sheets directly.** Plans are written directly too, but cannot arm unless `certify.py` passes. |
| D13 | **Setup doubt is detected, and a doubtful export is refused** — the capture is never refused. |
| D14 | **`lap_distance_m` gets repaired properly**, and laps that still cannot be trusted are nulled rather than exported. |
| D15 | **The app computes trends; Ludo interprets them.** |
| D16 | ⚠ **The paste path retires.** The driver report is rebuilt to ask him to confirm, not to recall. |
| D17 | **Qualifying uses the same machinery** — plan, knowledge record, certificate — in a quali mode. |
| D18 | **The rig is frozen.** Bug fixes only. |
| D19 | **`controller.py` is extracted as we go**, enforced: no item in this plan lands without taking its concern out. |
| D20 | **A full race session is checked in as the fixture**, telemetry and the replay video reference together. |

---

## 2. Baseline against target

Measured against the code and the database as they stand on 29 Aug 2026.

| | Today | Target |
|---|---|---|
| **Who authors setups** | Ludo, via a payload pasted out of the app | Ludo, reading the DB over MCP and writing the sheet back into it |
| **Who authors plans** | `recommend()` ranks; `handover.py` accepts one from the desk | Ludo authors; `recommend()` prices and `certify()` gates |
| **George's autonomy** | A playbook gates whatever it names; **no playbook at all means no bounds** | Free everywhere; four structural calls gated |
| **What George says** | ~15 call types, most of them status, all volunteered | Decisions volunteered, facts answered, position volunteered |
| **What George can see** | His own car. Nothing else. | His own car, plus live position and field size |
| **Rival data** | 626 rows, one race, hand-driven replay pass | Every race, unattended, feeding the next race's briefing |
| **Wear** | Modelled. Gauge reads **6 of 22 crossings in VR** | Measured off the replay to **0.5%**, carried forward as a rate |
| **Race-specific knowledge** | None. George is generic on every circuit | A knowledge record per event, six fields, Ludo-written |
| **Setup record** | Circuit key fixed; **nothing checks** | Two detectors; a doubtful export refused; correction lands in the DB |
| **`lap_distance_m`** | Integrated from speed. sd **620 m within a run**, over 10% of a lap | Crossing-anchored; untrustworthy laps nulled |
| **Driver model / trends** | Prose in `brain/`, 3,961 `grip_observations` unread | App computes the slopes; Ludo reads the output |
| **Prompts** | ~3,000 lines building a paste payload; 13 blank fields | Paste path retired; targeted confirm-not-recall questions |
| **Qualifying** | Partly built, on its own track | Same plan / knowledge / certificate machinery |
| **`controller.py`** | 5,299 lines, and every wiring bug lives in it | Shrinks with every item below |
| **Fixture** | One real lap (`watkins_glen_lap.bin`) | One full race, telemetry and video |

### What is already there and needed no decision

- **Live race position is already decoded and already correct.** `laps.position`
  reads P3→P1 across session 49 — the Watkins race that was won from P3 — and
  P10→P5 at Fuji. It is stored at every crossing and **read by nothing in
  `pitcrew/race/`.** D4 is wiring, not capture.
- **The MCP seam exists** — nine tools, `pitcrew/mcp/server.py`.
- **The gate exists** — six stages over free dictation, three outcomes, and
  stages 0–4 are pure numeric functions specifically so a fabricated answer
  cannot reach the driver's ear. D8 is an extension, not a build.
- **The PTT second-tap defect is fixed.** Root cause was the opening burst
  overrunning Windows' 300 ms low-level-hook timeout, dropping every key-up.
  Fixed in code; **not yet verified in a live session.**
- **`note_sheet_change` exists** and writes `setup_changes` from the
  between-session diff. The table still holds zero rows.
- **`tyre_models`** is already keyed `car_key × circuit_key × compound` with
  provenance. The measured wear rate of D10 has a home already.

---

## 3. Why live rival vision is refused

D5 is the only capability in this document turned down, and it is turned down
on measurement rather than on cost.

**In VR, GT7 draws its HUD on the car's dashboard in 3D.** It translates and
rotates with head position — measured at roughly 200 px of drift — so a fixed
rectangle tracks nothing. Measured in VR on 23 Aug: **22 crossings, 6 readings**,
and that is the *wear gauge*, which is large, high-contrast and fixed in the
car. The proximity radar is smaller, translucent, and drawn over moving
scenery. The leaderboard's gap rows, in the driver's own words on 26 Aug, are
**never visible in VR at all**.

**And the two problems are not the same shape.** Wear changes slowly, so
occasional samples suffice — the documented lever is sampling every two seconds
to get ~1,200 chances instead of 22. **Rival proximity changes in a second.**
Occasional samples of a fast-moving quantity are not a degraded signal; they
are no signal.

So rival knowledge moves from perception to memory: read it off the replay
after the race, and hand it to George as a briefing before the next one.

---

## 4. The work

Nine workstreams. Dependencies are stated; the sequence in §5 follows them.

### A — What George says *(no dependencies)*

The driver's own answer to "what do you wish the app had done": **George
reports where he should advise.** Reading `calls.py`, most of his vocabulary is
status — `_status`, `orientation`, `_fuel_standing`, `_gauge_ask`,
`minutes_left`, `laps_to_go`, `fuel_reference`.

- **A1.** Split the call inventory into two registers. Decisions are volunteered
  as instructions with the reason second and short, per `CLAUDE.md` §5.5. Status
  is not volunteered at all.
- **A2.** Wire `packet.current_position` and `cars_in_race` into `RaceState`,
  read live in `note_packet` rather than only at the crossing. Position is
  volunteered on every change (D7's exception).
- **A3.** Extend the answerable set to the three groups chosen: **fuel and
  stops** (fuel to the flag, laps to the stop, what the plan says next),
  **position and rivals** (where he is, who is near, who has pitted), **tyres
  and pace** (tyre state, last lap, gap to plan, time remaining).
- **A4.** Narrow the rail to the four structural calls of D3. Remove the
  "no playbook means no bounds" branch — the bound is now in code, not in a
  document that may be absent.
- **A5.** Verify PTT end to end in a live session. The fix is in; the proof is not.

> **The driver did not take "why" into the askable set.** Rule 12 therefore has
> to be honoured *inside* the call: every box call names the constraint that
> actually bound it, in the same sentence, because it can no longer be asked for
> afterwards.

### B — Setup record integrity *(no dependencies)*

Rank zero of the charter's hierarchy, wrong in five consecutive sessions, and
caught by the driver in passing every single time.

- **B1.** Two detectors, both ground truth and both already computed:
  `gearing.matchesSheet == false`, and a revision present in `brain/` that is
  absent from `setup_sheets` (`tools/check_setup_sheets.py` already finds this,
  and it is the confirmed live cause of charter B4).
- **B2.** On doubt, prompt for a photograph of the setup and gear screens.
- **B3.** ⚠ **Block the export, never the capture.** A session not recorded is a
  session lost, and the sheet can be corrected afterwards. What must not happen
  is an export reaching Ludo carrying a sheet the app has reason to doubt —
  that is how a wrong premise becomes permanent learning.
- **B4.** Backfill `setup_changes`. Both ends built, zero rows after 88 sessions.

### C — Ludo's channel *(depends on B for the doubt signal)*

- **C1.** ⚠ `propose_setup_sheet` becomes an authoritative write: the sheet lands
  in `setup_sheets` and the session re-binds. **This reverses the doctrine
  currently written into `mcp/server.py`** — *"Reads are open. Writes propose;
  they never apply"* — whose stated reason is that the app was wrong about which
  sheet was in the car three sessions out of three. The decision is the
  driver's and it is taken. It ships with a **change log and an undo**, and the
  docstring is rewritten so the code does not carry a doctrine it no longer
  follows.
- **C2.** `propose_strategy` writes an approved plan directly, but **`certify.py`
  must pass or it cannot arm.** A sheet describes something that already exists;
  a plan is an instruction that will be executed under a helmet, and the failure
  on record is a plan priced 50 s slower than its own alternative.
- **C3.** Expose computed trends over `grip_observations` as an MCP tool (D15).
- **C4.** Retire the paste path. Rebuild the driver report as targeted questions
  that show what the data already says and ask him to **confirm rather than
  recall** — the interaction-design doc's own principle, applied.

### D — The knowledge record *(depends on nothing; blocks E and F)*

A new record per event, written by Ludo, read by George's rules. Six fields:

1. **Pit loss ex-fuel, measured**, and the measured refuel rate
2. **Undercut / overcut value at this circuit**
3. **The binding constraint Ludo expects**, and what would change it
4. **Rival tendencies** from the last race here *(filled by F)*
5. **Tow value on this circuit's straights**
6. **Calls Ludo does not want made here, and why** — the rail expressed as
   knowledge rather than as a veto

Absent or stale, George falls back to the generic model **and says so once at
the green**: *"no notes for this circuit — I'm running on the model."* Silent
fallback is the defect pattern that made the gauge ratchet invisible for a
whole race.

### E — Wear, measured *(depends on D and on H2)*

The highest-value item in this document. The replay reader is verified to
**0.5%** against a model that was **~21% low** — a 21% error sitting underneath
every stint length raced so far.

- **E1.** Routine post-race replay wear pass, unattended.
- **E2.** The measured rate lands in the knowledge record, keyed car × circuit ×
  compound × multiplier.
- **E3.** George runs the measured rate as his baseline. Any live gauge reading
  that lands corrects it rather than replacing it.
- **E4.** Close the `wear_predictions` loop — predicted against answered, one row today.

### F — Rivals, after the race *(depends on H2; feeds D)*

- **F1.** The traffic pass runs unattended — sides and presence are positional
  and need no human.
- **F2.** A **league roster of name bitmaps, labelled once**, not once per race.
  GT7 renders each name as the same bitmap every time, so a labelled cluster
  carries forward and every subsequent race matches against it automatically.
  This is what makes "routine" achievable.
- **F3.** Rival tendencies and time-lost-in-traffic feed the knowledge record.

### G — Qualifying *(depends on A, C, D)*

Same machinery in a quali mode: Ludo writes a quali plan into the DB, it
certifies, George runs the out-lap, the tyre preparation, the flying lap and
the fuel load. No second plan format, no second knowledge record shape.

### H — Foundations *(H1 blocks nothing; H2 blocks E and F)*

- **H1.** Repair `lap_distance_m`: anchor on crossings rather than integrating
  blind, and null the laps that still cannot be trusted rather than exporting
  them. Under D1 the app's entire job is being a good instrument, and a 10%
  distance error is an instrument fault — corner aggregates are what Ludo builds
  setups from.
- **H2.** Check in one full race session: telemetry **and** the replay video
  reference. Every wear, rival and distance change is re-run against it. It is
  the only way to know a change to the wear model is an improvement.
- **H3.** `controller.py` extraction, enforced per item (D19).
- **H4.** Fix the contradiction in `packet.py`: the dataclass comment at line 274
  says `bits[31:4] = start_pos, bits[7:0] = cars_in_race`; the property at 476
  says byte 0 is position and byte 2 is total cars. **The data proves the
  property right and the comment wrong**, and A2 is about to depend on it.

---

## 5. Sequence

The driver's instruction was *"just do it all"*, so this orders by dependency
and by value per hour, not by preference.

| Order | Workstream | Why here |
|---|---|---|
| 1 | **A — what George says** | Smallest, no dependencies, and it is the thing he actually named. Changes every race regardless of circuit, car or plan. |
| 2 | **B — setup record integrity** | Small, mostly built, and it protects everything downstream from a wrong premise. |
| 3 | **H1, H2, H4 — foundations** | H2 blocks E and F. H4 blocks A2. H1 is the instrument fault. |
| 4 | **D — the knowledge record** | The spine. E, F and G all write into it or read from it. |
| 5 | **E — wear** | Highest value in the document; needs H2 and D first. |
| 6 | **F — rivals** | Needs H2; feeds D. |
| 7 | **C — Ludo's channel** | Larger, and the paste path still works while it waits. |
| 8 | **G — qualifying** | Last, and cheapest last, because it reuses everything above. |

H3 is not a row: it runs through every one of them.

---

## 5a. What shipped, 29 Aug 2026

**All eight workstreams are in**, on `feat/direct-feed-and-endpoint-verification`,
nine commits from `df19d04` to `992e111`. Four test quarters green, exit 0 on
every one, after every workstream.

| # | Workstream | State | What it turned out to be |
|---|---|---|---|
| 1 | **A** what George says | ✅ | Position was decoded correctly all along and read by nothing. Two registers, enforced. Rail narrowed to the structural four. "How long left" answered a timed race in laps while the measured clock sat unquoted beside it. |
| 2 | **B** setup integrity | ✅ | Two detectors; the export refuses and the capture never does. **Three of eight events refuse today**, all on a gearbox that disagrees with its sheet. `setup_changes` backfilled to 142 rows from zero. |
| 3 | **H** foundations | ✅ | Monza sd 1,187 m → 0.00. 18 of 176 laps refused. Full race fixture checked in (session 49, 9.9 MB). |
| 4 | **D** knowledge record | ✅ | `race_knowledge`, six fields plus wear rates. Absent is announced at the green. |
| 5 | **E** wear | ✅ | Fitted per stint, per compound. **Reproduces the 0.0493/lap Monza figure measured by hand.** Six of eight circuits now carry a rate. George can speak about tyres in VR with no gauge reading at all. |
| 6 | **F** rivals | ✅ | The `--offset` is derived; `video_index.build` had no caller. Fuji tendencies written. |
| 7 | **C** Ludo's channel | ✅ | ⚠ Writes apply, with an audit trail and an undo. `prompts/questions.py` — 500 lines — had no caller anywhere in the app. |
| 8 | **G** qualifying | ✅ | One briefing, one plan door. Qualifying was the last place the app still authored. |

### D19 — owed, then paid

The eight workstreams left `controller.py` at **5,464** lines against the
5,299 they started from: every new *concern* landed in a module of its own,
but nothing was extracted, and D19 asked for extraction as a precondition of
landing. Three cuts followed.

| Cut | Lines | Why it was safe, and what it hides |
|---|---|---|
| `rig/supervisor.py` | 597 | Fourteen methods calling **one** controller method between them, and state nothing else touched. D18 freezes the rig, so nothing moves under it. Hides the watchdog, the endpoint note and the recovery ladder. |
| `telemetry/hud_session.py` | 183 | The gauge session around `telemetry/hud.py`'s instrument. Its interface is the **four loose attributes** the controller actually read — from three different places, written on a worker thread. |
| `bench.py` | 343 | The Settings screen's hardware checks and the health line. **None of it runs during a session.** Hides the three-valued audio verdict. |

**5,464 → 4,373. Down 20%, and 18% below where the week started.**

**Three collaborators, and all three take readers rather than objects.** The
controller rebinds `settings` on every save, `listener` on every session, and
the tests rebind `_confirm_audio` after construction. A module holding what it
was built with reads the world as it was when the app opened — the driver
turns the haptics off and the rig carries on. The bench's first draft did
exactly that and two tests caught it, three lines below a docstring describing
the trap.

**Two tests got better rather than merely moved**, and that is the argument
for the cuts. The wind tests built a hand-made rack and borrowed three methods
onto it; they build the real `RigSupervisor` now, because it takes exactly
what the rack was faking. The stale-wear test grepped its own source for
`_wear_now = None` because there was nothing to construct; it drives a real
`HudSession` now — a good reading, then a refusal, then what the radio would
be handed.

What is left in `controller.py` is what the class is for: `start_race` (274),
`__init__` (182), and the two event handlers (159, 146). The next cut worth
making is the re-planner, and it is not as clean — it calls out to nothing,
but it touches thirteen pieces of race state.

### Five things that were built and wired to nothing

Found while doing the above, and worth recording as a pattern rather than five
incidents:

* `packet.current_position` — decoded correctly, read by no module in `race/`.
* `video_index.build` — the exact-offset derivation, called only from its own
  test file, while both replay tools went on asking for `--offset` by hand.
* `prompts/questions.py` — the whole confirm-not-recall design, no caller.
* `setup_changes` — both ends built, zero rows after 88 sessions.
* `SetupSheet.updated_at` — read by the first draft of the doubt detector and
  **it does not exist**, so `getattr` returned None on every sheet and the
  detector was silent on all eight events while looking entirely correct.

The last one is the shape to watch: it is not a missing caller, it is a caller
reading a field nobody has. Both fail the same way — correct-looking and dead.

### One defect this work introduced and caught

The event-level knowledge record **shadowed the circuit's measured wear rates**
for about an hour. "The event's record wins" has to mean field by field, not
row by row; row by row, the first traffic pass to write rivals took every wear
rate on that circuit out of George's view and he went quietly back to
modelling. There is a test named after it.

---

## 6. Risks, stated rather than discovered later

1. **The replay offset is hand-found.** `--offset` is required for every replay
   pass and is currently a number the operator reads off the video. F1's
   "unattended" degrades to "one manual number per race" unless it can be
   derived. **This is the main threat to F, and it should be settled before F
   is scheduled.**
2. **⚠ C1 makes MCP writes authoritative**, reversing a doctrine the code
   currently states and justifies. The audit log and undo are not optional
   extras; they are what makes the decision safe.
3. **The suite cannot be run in one command** — `0xC0000409` in PyQt teardown on
   Windows / Python 3.14. Every change in this plan lands without a single green
   signal. Run in quarters, check exit codes, and re-run a crashing quarter
   file-by-file before believing a failure is yours.
4. **PTT is fixed but unproven live.** A3 assumes the driver can ask a question.
   A5 exists because that assumption is untested in a race.
5. **`recommend()` is not retired.** D1 removes its *authority*, not its code —
   it still prices plans, still ranks them, and `replan.py` still calls it live
   at 1.4 ms. Anything that reads it as "the app's recommendation" in the UI is
   now mislabelled and needs re-registering as derived, not declared.

---

## 7. What does not change

- `EXPORT-CONTRACT.md` and the export vocabulary.
- `CLAUDE.md` §3 — the four facts about the feed. **No tyre wear channel, no
  track ID**, still. E does not measure wear from the stream; it measures it
  from a picture of the game's own gauge and carries the number forward.
- **Lap time confirms degradation and can never warn of it.** σ 0.918 s puts the
  floor at 1.74 s/lap, above the entire 0.5–1.5 s/lap band.
- **Fuel map 1, always.** His levers are short-shift → lift-and-coast →
  slipstream, and even that reverses when refuelling is fast.
- **The driver's report is primary evidence.** D15 gives the app the arithmetic
  and leaves the meaning where it belongs.
- The rig: haptics, ButtKicker, wind, shift beep, transducer. Frozen, bug fixes
  only.

---

*Written 29 Aug 2026 · GT7 v1.71 · from a design interview with the driver.*
*Twenty decisions, nine workstreams, two doctrine changes, one capability refused on evidence.*
