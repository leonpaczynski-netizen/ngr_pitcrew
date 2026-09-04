# The interaction interface — minimum prompt, targeted questions

**Written 23 Aug 2026**, from the driver's requirement of the same date:

> *"Something that allows me a minimum prompt and you prompt me to clarify what
> you can't get from udp or video footage specifically."*

Covers **setups, setup refinement, race plans and qualifying plans** in one
interaction. Companion to `RACE-ENGINEER-CHARTER_2026-08-23.md` §6 and
`ENGINEER-BRAIN-IMPLEMENTATION_2026-08-23.md`.

---

## 1. What is wrong today

`pitcrew/ui/engineer_screen.py` presents a **blank form with thirteen fields**
(`prompts/report.py::DriverReport`): symptoms, biggest limitation, costs most
where, balance drift, tyre state at end, priority, conditions, unrepresentative,
clean air, best quali lap, result, notes. He picks a kind and fills it in.

**That is a maximum prompt, not a minimum one.** Three specific problems:

1. **It asks everything, every time**, regardless of what the data already knows.
2. **It is a static list.** `report.py`'s docstring is the right principle —
   *"only what the app cannot know"* — but it was decided once, at design time.
   **Some of those fields have since become measurable and the form cannot
   tell.** `tyre_state_at_end` is now read off the HUD gauge to 0.5% by
   `tools/read_hud_wear.py`; `costs_most_where` is derivable from
   `grip_observations` and `tools/where_the_time_went.py`.
3. **It asks in the wrong direction.** A blank field asks him to *recall*. A
   question that shows what the data already says asks him to *confirm* — which
   is a far easier and far more reliable act, and it is what a real engineer does
   over the radio.

**The prompt kinds are also incomplete.** `prompts/build.py` has `BRIEF`,
`REFINEMENT` and `OUTCOME` — all setup. **Race and qualifying plans are not
prompt kinds at all**; strategy lives separately on `strategy_screen.py`.

---

## 2. The minimum prompt — four verbs

Everything else comes from the event row, the session history and the store.

```
  tune            build me a setup for the event that is loaded
  refine          revise the fitted sheet against what just happened
  race plan       stint, fuel and stop plan for this event
  quali plan      one-lap configuration and an execution plan
```

**Nothing else is required of him.** Car, circuit, format, multipliers, assists,
compounds, regulations and the fitted sheet are already in `events` and
`setup_sheets`. Pace, burn, wear, consistency and incidents are already in
`laps`, `lap_frames`, `grip_observations` and `tyre_models`.

**Optional free text is still accepted and outranks everything** — *"rears lock
under braking"* should short-circuit straight to the relevant question set. A
minimum prompt is a floor, not a ceiling.

---

## 3. The evidence-gap engine, and the gate that defines it

**The whole design is one rule:**

> ⛔ **A question with a working resolver may never be asked.**

Today's session is the reason it exists. I asked him to watch the on-screen tyre
indicators at T7 and T12 to settle whether one rear wheel was spinning alone or
both together. **`lap_frames` carries per-wheel slip; splitting the rear axle
into inside and outside over 17,421 corner-exit frames answered it in one
query — both together, 100% of frames at slow-exit speeds.** A driver
observation was queued for something already measured seventeen thousand times.

### The shape

Each question is a record, not a form field:

```python
@dataclass(frozen=True)
class Question:
    key: str                      # "brake_balance_as_run"
    asks: str                     # the words, with the data already in them
    feeds: tuple[str, ...]        # which decisions change with the answer
    resolver: Callable | None     # tries to answer from UDP / DB / video
    unmeasurable_because: str     # REQUIRED when resolver is None
    impact: int                   # how much the output moves. Ranks the queue.
```

**`unmeasurable_because` is mandatory when there is no resolver**, and it is the
field that keeps the registry honest. *"GT7 sends no slip angle and no yaw
target"* is a reason. *"We never wrote the query"* is not, and fails review.

### The pass

```
  1. assemble      event + fitted sheet + laps + frames + grip_observations
                   + tyre_models + setup history + KB
  2. resolve       run EVERY resolver. Record what it answered and from what.
  3. gate          drop every question the resolvers answered
  4. rank          by impact x how much the answer would change the output
  5. ask           the top N, ONE AT A TIME, each showing what the data says
  6. record        answer -> prompt_issues / setup_changes / driver_preferences
  7. produce       the sheet or the plan, with the answers folded in
```

**N is small — three, four at most.** Nobody answers eleven questions well, and
the ranking exists so the cheap ones do not crowd out the decisive one.

---

## 4. The registry, seeded from today

**Every question asked today, classified. This is the acceptance test for the
gate** — the last row must never be asked again.

| Question | Resolver | Verdict |
|---|---|---|
| **What brake balance is actually in the car?** | none — GT7 broadcasts no brake balance | ✅ **ASK. Standing, pre-session.** Rank zero: a correct telemetry reading against a wrong setup record gives a confident wrong answer |
| **Is ABS Off your choice or the regulations?** | none — a league rule is not in the feed | ✅ **ASK once per series**, then store it on the event |
| **Which sheet is actually fitted?** | partly — `matchesSheet` covers the gearbox only | 🟡 **ASK until the circuit key lands** (implementation plan §0.1), then resolve |
| **Does the push happen on or off throttle?** | **candidate** — correlate steering demand against yaw response, split by `throttle_pct`, over `lap_frames` | 🟡 **BUILD THE RESOLVER.** It looked unmeasurable and probably is not |
| **How did the car feel under braking?** | none — no channel carries confidence or hesitation | ✅ **ASK.** This is the irreducible core |
| **Was that lap representative / clean air?** | none — no proximity or closing-speed channel | ✅ **ASK.** `report.py` already states why |
| **Tyre state at the end of the run** | **yes** — `tools/read_hud_wear.py`, 0.5% | ⛔ **STOP ASKING.** Still a form field today |
| **Where does it cost you most?** | **yes** — `grip_observations`, `where_the_time_went.py` | ⛔ **STOP ASKING as an open question.** Show the answer, ask him to confirm it matches what he felt |
| **Watch the tyre indicators: one rear wheel or both?** | **yes** — inside-vs-outside rear slip asymmetry | ⛔ **NEVER ASK.** Measured, 17,421 frames |

**Four of nine are resolvable and three of those are currently asked.**

### How a gated question should read

Not *"how did the car feel mid-corner?"* but:

> *"Both rear wheels are going together at T7 and T12 — inside and outside
> within 0.5% of each other across 17,421 frames, so the diff is over-coupled
> rather than open. I am taking `lsd_a` from 17 to 14. **What I cannot see is
> whether that push is there before you pick up the throttle** — off throttle
> too, or only on power?"*

**It states what is known, names precisely what is not, and asks one thing.**

---

## 5. Delivery — screen and voice

**Between runs, on screen.** One question at a time on `EngineerScreen`, with
the supporting data beside it. The thirteen-field form becomes the fallback for
free-text, not the primary path.

**In the car, by voice.** Piper/SAPI TTS and Moonshine PTT already exist, and in
VR he cannot read anything. A gated question is short enough to speak. **Two
existing constraints bound this:** the audio card contention that already dropped
the shift beep seven times in one evening, and the rule that a question asked at
racing speed must be answerable with one word.

**The precedent already exists in the schema.** `wear_predictions` carries
`trigger`, `asked_where`, `asked_at`, `answered_at`, `answer_kind`,
`answer_route` — a predict → ask → record loop, already built, for one question.
**Generalise that table's shape rather than inventing one.**

---

## 6. Race and qualifying plans become prompt kinds

`prompts/build.py` gains `RACE_PLAN` and `QUALI_PLAN` beside `BRIEF`,
`REFINEMENT` and `OUTCOME`, so all four verbs run through one interaction and one
log.

**Race plan** already has its engine — `strategy/model.py::recommend()` with
measured `CompoundProfile`s. What it lacks is the question set:

- *the regulations that are not in the feed* — refuel rate, mandatory stops,
  ABS. **Tonight's refuel rate was declared 2.0 L/s against four measurements of
  1.00 L/s at a different multiplier, and it inverted the short-shift call.**
- *whether the lap count is firm enough to drop the spare lap of fuel* — a
  decision taken at the stop, not before it.

**Quali plan is the genuinely missing one.** The app has no qualifying session
kind, so no quali lap has ever been through the stream — `report.py` says so.
Beyond the sheet it needs an execution plan: tyre preparation, out-lap targets,
where to attack, where not to overdrive, and the fuel load for exactly one lap.

---

## 7. Build phases

| # | Work | Done when |
|---|---|---|
| 1 | `Question` registry + the gate, with the nine rows above | the tyre-indicator question **cannot** be asked — a test asserts the gate suppresses it |
| 2 | Resolvers for the three currently-asked-but-resolvable rows | the form loses three fields and the prompt gains three measured values |
| 3 | Four-verb entry point on `EngineerScreen` | `tune` produces a sheet having asked ≤4 questions |
| 4 | `RACE_PLAN` and `QUALI_PLAN` kinds | a race plan is produced from `recommend()` through the same interaction |
| 5 | Voice delivery over PTT/TTS, with the contention guard | a question is asked and answered without touching the keyboard |
| 6 | Throttle-state resolver (§4 row 4) | a question that was asked today is never asked again |

**Phase 1 is the whole idea.** Everything else is filling the registry.

---

## 8. What this must not become

- **It must not ask a question it can answer.** That is the entire point.
- **It must not stop asking the irreducible ones.** Feel, confidence, workload,
  clean air, regulations and what is actually in the car have no channel and
  never will. The charter's §7 stands: **his report is evidence, not an
  instruction, and where it disagrees with telemetry the disagreement is the
  finding.**
- **It must not hide what it did not know.** A plan built without an answer says
  which question went unanswered and what it assumed.

---

*Written 23 Aug 2026 · GT7 v1.71*
*One rule: a question with a working resolver may never be asked.*
*Four of the nine questions asked today were resolvable; three are still on the form.*
*The thirteen-field form was right when it was written and the data has moved under it.*
