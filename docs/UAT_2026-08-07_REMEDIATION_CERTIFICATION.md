# UAT 2026-08-07 Remediation — On-Hardware Certification (GT7 + PSVR2)

Branch `fix/phase0-uat-20260807`. Certifies the remediation of the 6 August 2026 hardware
UAT: **43 of the 47 defects** in [the register](UAT_2026-08-07_DEFECT_REGISTER.md),
across Phases 0–4.

**Everything below is `NOT TESTED` until you complete it on real hardware.** That is not
a formality. The register's central finding was that 11,000 passing offline tests
coexisted with basics being broken on track, because the suite exercised modules the
live path never called. Phases 0–4 added ~330 more tests to that same suite. **No
automated evidence in this repository can promote a single line below to PASS.**

## Why the old scripts could not do this

`SETUP_BUILDER_UAT.md`, `LIVE_RACE_ENGINEER_UAT.md` and `STRATEGY_BUILDER_UAT.md` hold 79
steps between them with **every Pass/Fail cell empty**, and they navigate by clicking
"the **Setup Builder** tab" and "the **AI Log** tab" — the classic shell that is being
retired, plus an AI path the determinism rebuild removed. Running them would mis-navigate
from step 1.1. They are superseded by this document.

## The eleven nav destinations

This app has no tabs. The rail on the left is:

`Home` · `Programme` · `Garage` · `Practice` · `Qualifying` · `Race Strategy` ·
`Live Pit Wall` · `Debrief` · `Track Model` · `Engineering Library` · `Settings`

Every step below names the destination it starts from.

## How to run this

One controlled event, one car, one track. **Practice, then qualifying, then race, one at
a time.** Do not skip ahead to see if something later works — the ordering is the test:
several defects were only visible because a later stage inherited a broken earlier one.

Record what you actually saw, not what you expected. A step that half-works is a FAIL
with a note. If you have to work around something to continue, that is a defect even if
the next step then passes.

**Sections 1–4 must be done in order.** 5 onward can only follow them.

---

## 0. Preparation

| # | From | Step | Expected | Result |
|---|------|------|----------|--------|
| 0.1 | Settings | Confirm the app opened in the new shell (nav rail on the left, no tab bar) | Eleven destinations listed above | ☐ NOT TESTED |
| 0.2 | Home | Create or activate ONE event: one car, one track, one layout | Event + car + track shown in the header | ☐ NOT TESTED |
| 0.3 | Settings | Start GT7 telemetry (PS5 → app) | Telemetry reads connected | ☐ NOT TESTED |
| 0.4 | — | Note the app version / commit and the DB schema version | Recorded below in §9 | ☐ NOT TESTED |

---

## 1. Track model and pit lane — symptom 4 (Phase 4)

> *"During track modelling it told you to box, then after you came out it still asked me
> to drive the pit lane."* The cause: "box" meant **press the Stop recording button**,
> which is unreachable in VR, so the flow could not advance.

Do this section **first**. A measured track model is what unlocks the setup shaping in §2,
and doing it first is also how you find out whether §2's gating is honest.

| # | From | Step | Expected | Result |
|---|------|------|----------|--------|
| 1.1 | Track Model | Select the track and layout | Rail shows IDENTIFY → CAPTURE | ☐ NOT TESTED |
| 1.2 | Track Model | Start capture and drive clean laps | Per-lap coaching after each lap; clean-lap count rises | ☐ NOT TESTED |
| 1.3 | Track Model | Keep lapping until the engineer says the data is complete | Message says **"just box … nothing to press"** — it must NOT tell you to press a button | ☐ NOT TESTED |
| 1.4 | — | **Drive into the pit lane.** Touch nothing. | The model finishes **by itself** within a few seconds of pit-lane speed | ☐ NOT TESTED |
| 1.5 | Track Model | Observe the rail | Moves to the pit-lane step; message asks for one lap through the lane | ☐ NOT TESTED |
| 1.6 | — | Drive one lap through the pit lane — in at the entry, down the lane, back out. **Do not stop.** | The lane maps; status says the model is complete | ☐ NOT TESTED |
| 1.7 | Track Model | Watch the UI during 1.6 | **No freeze or stutter** while the lane is being computed | ☐ NOT TESTED |
| 1.8 | — | Close the app completely. Reopen it. | The track still reads as complete **including** the pit lane — not "approved" with the lane outstanding | ☐ NOT TESTED |
| 1.9 | — | On disk, open `data/track_models/<layout>.station_map.json` | `pit_lane` is populated, not `null` | ☐ NOT TESTED |
| 1.10 | — | On disk, check `data/track_library/tracks/<id>/layouts/<id>/pit_lane.json` exists | Present, `"available": true`, with segments | ☐ NOT TESTED |

**Falsifies:** D1 (box unwired), D4 (pit lane not a step / lost on restart), D7 (mapping
written where the live engineer never reads it), D8 (instruction the detector cannot
satisfy), D9 (12M computations on the UI thread).

**Fail it if:** you had to press anything to finish the model · the pit callout repeated
after you came out · the UI froze · after restart the track claimed to be finished with
`pit_lane: null`.

---

## 2. Base setup — symptom 1 (Phase 1)

> *"Setups are still wrong."* Verified before the fix on a Gr.3 at Monza: 108/119 mm ride
> height, 13.4/14.9 Hz springs, **more camber on the rear than the front**, status
> `approved` with zero warnings.

| # | From | Step | Expected | Result |
|---|------|------|----------|--------|
| 2.1 | Garage | Observe the discipline tabs | **Base · Qualifying · Race** — Base exists | ☐ NOT TESTED |
| 2.2 | Garage | Select **Base**. Check the live session type is unaffected | Selecting a tab does **not** put the app into qualifying or race | ☐ NOT TESTED |
| 2.3 | Garage | Press **Build initial setup** | All three sheets author; the headline names all three | ☐ NOT TESTED |
| 2.4 | Garage | Read the ride height | **50–80 mm**, front lower than rear | ☐ NOT TESTED |
| 2.5 | Garage | Read the spring rates | Inside the class band (Gr.3 ≈ **3.0–5.0 Hz** on GT7's scale) | ☐ NOT TESTED |
| 2.6 | Garage | Read the camber | **Front ≥ rear** | ☐ NOT TESTED |
| 2.7 | Garage | Read the aero | Not pinned to either end of the slider | ☐ NOT TESTED |
| 2.8 | Garage | Read the gearbox | Either a full ratio set, **or** "keep the stock gearing" naming what to capture — never a final drive with no ratios | ☐ NOT TESTED |
| 2.9 | Garage | Read the top-of-sheet provenance line | Says plainly if this is running on **class defaults** for an uncaptured car | ☐ NOT TESTED |
| 2.10 | Garage | Read the per-field tiers | Each field shows where its value came from; only ENGINEERED-and-above claim "engineered for car + track" | ☐ NOT TESTED |
| 2.11 | Garage | Read the degradations panel | Names any layer that had no data (history, proven library, corner segments) — or is absent if all ran | ☐ NOT TESTED |
| 2.12 | Garage | Read the status banner | A low-confidence baseline says so; it must not read `approved` with no warnings | ☐ NOT TESTED |
| 2.13 | Garage | Compare the Base/Quali/Race columns against the applied sheet | The comparison table and the sheet **agree on every field** | ☐ NOT TESTED |
| 2.14 | Garage | Read what Qualifying and Race changed from Base | Each names the fields it moved, or says it is identical | ☐ NOT TESTED |

**Sanity anchor:** a Gr.3 should land near **55/63 mm, 3.4/3.35 Hz, 2.4°/2.0° camber,
390/595 aero** — the vetted Porsche RSR values. Anything far from that shape is a FAIL
even if it is inside the bands above.

**Falsifies:** A1 (midpoint walk), A6 (three authors disagreeing), A8 (low confidence
laundered into approved), A9 (provenance lies), A10 (silent degradation), A4 (orphan
final drive).

---

### 2b. Car data capture (Phase 1, chunk 9)

| # | From | Step | Expected | Result |
|---|------|------|----------|--------|
| 2b.1 | Garage | Press **Record this car's GT7 data…** | Capture page opens for the active car | ☐ NOT TESTED |
| 2b.2 | Garage | Open the car's tuning screen in GT7. Enter **only** the gear count and redline | Saves; the rest stays on class defaults | ☐ NOT TESTED |
| 2b.3 | Garage | Rebuild the setup | The gearbox advice changes — it now knows more than it did | ☐ NOT TESTED |
| 2b.4 | Garage | Reopen the capture page | Shows what you captured and what is still a class default, per field | ☐ NOT TESTED |

**Fail it if:** a partly-filled car became unusable · a blank field was saved as 0.

---

## 3. Practice and driver feedback — symptom 2 (Phase 2)

> *"Driver feedback was ignored."* Every submission in the new shell died with the
> process; two classic fields were destroyed on every write; the acknowledgement existed
> but could not reach this shell.

| # | From | Step | Expected | Result |
|---|------|------|----------|--------|
| 3.1 | Practice | Start a run, drive **at least 6 clean laps**, end and record it | Run recorded; laps visible in Review | ☐ NOT TESTED |
| 3.2 | Practice | Fill in **all fourteen** feedback dropdowns. **Do not press Submit.** | — | ☐ NOT TESTED |
| 3.3 | Garage | Press **Analyse** | The analysis reflects what you typed — it must not report missing evidence | ☐ NOT TESTED |
| 3.4 | Garage | Read the acknowledgement panel | **"What I did with what you told me"**, one line per item you reported | ☐ NOT TESTED |
| 3.5 | Garage | Check every item you reported appears | Each is Acted on / Heard, not changed / Strategy / Left alone — **nothing missing** | ☐ NOT TESTED |
| 3.6 | Practice | Report **mid-corner oversteer** specifically, and analyse | It comes back explicitly as heard-but-deferred, not silently dropped | ☐ NOT TESTED |
| 3.7 | Practice | Press Submit feedback, then start a **new run** | The form clears; the previous verdict is not carried over | ☐ NOT TESTED |
| 3.8 | Garage | Analyse again on the new run | The old verdict is **not** reused | ☐ NOT TESTED |
| 3.9 | Debrief | Confirm the feedback survived | Your answers are still there after an app restart | ☐ NOT TESTED |
| 3.10 | Garage | Read the recommendation's test plan | Ordered stages with a success criterion and a rollback each — not a bare numbered list | ☐ NOT TESTED |

**Falsifies:** B1, B2 (analyse read a stale copy), B3 (error → all-clear), B5 (fields
destroyed), B6 (acknowledgement unreachable), B7 (vocabulary gaps), B8 (stale verdict),
C8 (test planner never ran).

**Fail it if:** anything you reported vanished without comment · "no change recommended"
appeared with no explanation · the new run opened with the last run's answers.

---

## 4. Progression gates — symptom 3 (Phase 3)

> *"It ran one practice session and went straight to qualifying, without working through
> the tyres or settling the setup."*

| # | From | Step | Expected | Result |
|---|------|------|----------|--------|
| 4.1 | Programme | After the ONE run from §3, read the objective | Still on the **same domain** — it must not have moved on after one run | ☐ NOT TESTED |
| 4.2 | Programme | Compare the objective to the programme map's target | Both say the same number of runs | ☐ NOT TESTED |
| 4.3 | Qualifying | Press **Begin Qualifying** now | **Refused**, with a list naming what is missing and how to clear each | ☐ NOT TESTED |
| 4.4 | Qualifying | Read the list | Names base setup / qualifying setup / tyre coverage / your comfort — **not** fuel or strategy | ☐ NOT TESTED |
| 4.5 | Practice | Drive a run on **each** compound the event allows | Tyre coverage rises per compound | ☐ NOT TESTED |
| 4.6 | Practice | Drive an out-lap only (1–2 laps) and record it | It does **not** count as a complete evidence sample | ☐ NOT TESTED |
| 4.7 | Programme | Try to record one telemetry session against a second activity | Refused — one run is one piece of evidence | ☐ NOT TESTED |
| 4.8 | Practice | Say you are **not** comfortable with the setup | Begin Qualifying stays blocked and says so | ☐ NOT TESTED |
| 4.9 | — | Complete the work the gate asked for | Begin Qualifying becomes available | ☐ NOT TESTED |
| 4.10 | Qualifying | Press it now | Proceeds; the app switches to the qualifying setup and RPM | ☐ NOT TESTED |

**Falsifies:** C1/C4 (no gate), C2/C9 (domain retired after one run), C3 (one lap = one
sample; one session counted three times), C5 (tab converts the session), C6 (tyre
coverage gated nothing), C7 (no comfort gate), C11 (consent that named nothing).

**Fail it if:** the gate let you through with the work undone · the override dialog
listed nothing · a 1-lap run satisfied a domain.

---

## 5. Qualifying

| # | From | Step | Expected | Result |
|---|------|------|----------|--------|
| 5.1 | Qualifying | Confirm the compound | Softest allowed dry (or rain if wet) | ☐ NOT TESTED |
| 5.2 | — | Drive a qualifying run | Shift beep at the **qualifying** RPM, not the race one | ☐ NOT TESTED |
| 5.3 | Live Pit Wall | Check the session type | Reads Qualifying end to end | ☐ NOT TESTED |
| 5.4 | Debrief | Record the result | Lap and evidence attributed to qualifying, not practice | ☐ NOT TESTED |

---

## 6. Race

| # | From | Step | Expected | Result |
|---|------|------|----------|--------|
| 6.1 | Race Strategy | Approve a race plan | Plan shown as approved | ☐ NOT TESTED |
| 6.2 | Live Pit Wall | Press **Start Race** before the race work is done | Refused, naming exactly what is missing | ☐ NOT TESTED |
| 6.3 | — | Read the override prompt | Enumerates every blocker **and its remedy** — not stage names | ☐ NOT TESTED |
| 6.4 | — | Override deliberately | A message records that the race started on incomplete preparation | ☐ NOT TESTED |
| 6.5 | — | Drive the race | Race setup + race RPM + the approved plan are the ones in use | ☐ NOT TESTED |
| 6.6 | Debrief | Read the post-race debrief | Reflects this race, not a previous session | ☐ NOT TESTED |

---

## 7. Must NOT happen

Regression checks. Any ☑ here is a FAIL.

| # | Must not happen | Seen? |
|---|-----------------|-------|
| 7.1 | A setup arrives `approved` with no warnings on a car with no captured data | ☐ |
| 7.2 | Rear camber exceeds front on a race car | ☐ |
| 7.3 | A final drive is authored with no gear ratios | ☐ |
| 7.4 | Selecting a Garage tab changes the live session type | ☐ |
| 7.5 | Feedback you entered is not reflected in the next analysis | ☐ |
| 7.6 | A pit callout repeats after you have driven the pit lane | ☐ |
| 7.7 | The UI freezes during pit-lane mapping | ☐ |
| 7.8 | A single lap satisfies an evidence domain | ☐ |
| 7.9 | Begin Qualifying or Start Race proceeds with no list of what is missing | ☐ |
| 7.10 | The app claims a proven setup was used but the values differ from `data/proven_setups.json` | ☐ |
| 7.11 | Any screen shows the flashing/focus-stealing box | ☐ |

---

## 8. Defect register

Record what you actually saw. One row per problem.

| # | Where (destination + step) | What happened | What you expected | Severity |
|---|---------------------------|---------------|-------------------|----------|
| | | | | |

Severity: **P1** blocks a trustworthy race weekend · **P2** degrades quality or hides
failure · **P3** correctness debt.

---

## 9. Run record

| Field | Value |
|---|---|
| Date | |
| App version / commit | |
| DB schema version | |
| Car | |
| Track + layout | |
| Sections completed | |
| Overall verdict | ☐ NOT TESTED |

**A verdict of PASS requires every section 1–6 completed on hardware with no P1 in §8 and
no ☑ in §7.** Nothing else can produce it — not the test suite, not a simulated run, and
not a partial pass with the rest inferred.

---

## Known gaps — not covered by this script

Stated so the certification is honest about its own scope:

* **B11** — when telemetry and the driver disagree on the same axis, nothing arbitrates.
  The structured arbiter is dormant by decision, not by accident.
* **B12** — there is no voice capture for driver feedback. If you speak it, nothing
  receives it.
* **E3/E4** — `PROJECT_STATE.md` and `REQUIREMENTS.md` still describe the classic tab
  layout; setup history `config_id` hashes track name rather than `layout_id`, so two
  layouts of one track share history.
* **Gr.2 and Gr.B archetypes** are interpolated from no supporting data at all. If you
  race either, the numbers in §2 need your review before they mean anything.
