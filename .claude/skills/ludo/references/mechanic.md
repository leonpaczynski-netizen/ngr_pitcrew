# Mechanic — the setup pass

Procedure only. Slider semantics, symptom tables and per-car values live in the
knowledge base — reach them through the `gt7-brain` skill, which routes to the
right file. Nothing here restates a measurement.

---

## Before a slider moves

**The league's limits first.** `events.power_limit_bhp` and
`events.weight_limit_kg` carry the hub's `carRegulations` (Porsche Cup 509 BHP
/ 1,243 kg; Supercars 1,335 kg). A sheet whose ECU, restrictor or ballast puts
the car outside them is not a sheet - the lobby refuses it - so read them off
the event row and say them on the sheet before anything else is priced. Where
the row is NULL the league did not limit it; that is not zero.

**And whether the round runs BoP** (`events.bop_enabled`, from the hub, plan
row 2.7). **Under BoP the sheet refuses, by name, every key the lobby
locks: `top`, `fg`, the six gear ratios, ECU output, the power restrictor
and ballast** - write "locked by BoP" in those rows, never a value. The
shift table survives: one gearbox for the whole event is measured once.
`tuning_allowed` 0 refuses the rest of the sheet too. NULL on either means
the hub did not say; ask him, and do not read it as open.

**Rank zero first, both halves** (SKILL.md step 1). A correct telemetry reading
against a wrong setup record produces a confident wrong answer, and that has
happened in five consecutive sessions.

Then **diagnose by phase and throttle state.** The knowledge base's symptom
tables are cause-ranked and need no baseline — but they fork on one question
that decides which table you are even in: *does the symptom happen on throttle
or off it?* Reading the wrong side of that fork produces a confident answer from
the wrong table.

The four questions worth his attention, when the data cannot settle them:

1. **Where is your right foot when it happens?** (the fork above)
2. **Which corners are fine?** — a symptom everywhere is the platform; a symptom
   in one phase is that phase's lever.
3. **From lap one, or does it develop?** — separates setup from tyre state.
4. **Is it built as written?** — rank zero, asked plainly.

---

## The run plan — before the car turns a wheel

Every practice session has a run plan, filled before the first run:
`brain/_inbox/setups/RUN-PLAN-TEMPLATE.md`, saved as
`YYYY-MM-DD-<car>-<circuit>-RUNPLAN.md`. Per run: purpose, fuel, tyre, the ONE
delta, lap type, the instrument and its measured floor, the prediction and its
falsifier - and an A-B-A return leg when the change is a feel change, because
the driver improves ~0.3 s a run on his own. The debrief fills the outcome
column and closes each prediction. "Clean lap" is the tool's definition
(`where_the_change_landed.py`), never the eye's.

---

## Choosing the lever

The knowledge base carries a ranked change hierarchy — hardware, then brake
stability, front grip, differential, ride height, aero, brake bias. Use it to
choose **among controls that already fit the diagnosis.** It is not a licence to
reach for a higher-ranked control once the symptom has been traced to a specific
one.

**One change per run, three clean laps.** Not suspended for the 1.71 rebuild —
with every baseline unverified, a two-change run is uninterpretable.

**A telemetry-only flag may not buy a change.** It buys a question or a
measurement. This was overridden once and bought nothing for ride height and
rake.

---

## What the app can verify, and what it cannot

- `pitcrew.analysis.gearing.matches_sheet(laps, sheet_gears)` — **the only setup
  value telemetry can verify.** Element-wise, final drive deliberately excluded.
- `pitcrew.analysis.corners.aggregate_corners(...)` — per-corner metrics, each
  mean carrying its own sample count, with flags that fire only when a quarter
  of laps show them. Understeer is deliberately **not** a flag any more; the old
  detector's shape made a neutral car flag more at speed by construction.
- `pitcrew.analysis.corner_findings.analyse(model, laps) -> Report` — the
  post-session debrief that replaced live corner coaching. **`Report.silent`
  names the corners that cannot carry a claim.** Report those as silent; do not
  omit them.
- `tools/where_the_change_landed.py --before <sessions> --after <sessions>`
  — **where on the lap a change landed.** Sector medians with their own spread
  (a delta inside it prints as *inside the scatter*, which is a refusal), and
  with `--bins` a 100 m attribution that sums back to the delta as an
  identity. Bins are labelled from the BEFORE run only, so the classification
  cannot be moved by the change being measured. It refuses when the two runs
  were cut on different sector models and warns when the compound differs.
  **This is the answer to "the lap time cannot show a tune working"** — the
  lap cannot, the parts can.
- `RangeRecord.fraction_of_range(key, value)` — advisory only. Nothing refuses
  on it, so a value outside range still needs your eyes.

Everything else on a sheet — twenty-two of twenty-three values, the gear ratios
being the one — has **no ground truth in the feed.** For those, the record is what he tells you, and the only
defence is provenance and confirmation.

---

## Every instrument, one line each

Plan row 2.10. Ten of these existed and were re-derived by hand because
nothing named them. Run a tool before re-deriving what it answers; read its
own `--help` for the arguments. **Opening `Store()` upgrades the file it opens,
in a write transaction, every time** - so even a reader touches the database it
is pointed at. For work that must not, open sqlite with `mode=ro`, or a copy
that includes the `-wal` file.

**Readers — they answer a question and add no row of their own.** Not the same
"write" as the line above: opening the database writes to it whatever you do,
so a reader here means one that adds nothing, never one that touches nothing.
Two write a file beside their input: `analyse_m0` a `<capture>.m0.json`,
`draw_track_map` a PNG — and `read_replay_board` writes its
`roster-session-<n>.json` and one PNG per cluster **on the dry run**, which is
the point of the dry run: it is the roster you then label by hand.

> ⛔ **The three corner tools do not give you corner names, and one of them
> changes whether you may use them.** Ask the database which, before you say
> anything about a corner: `SELECT circuit_key, source FROM corner_models` on
> a read-only handle. **No count is written here on purpose** — `refusals.md`'s
> own header says a number copied into a refusal becomes a competing answer
> that nobody re-queries. Note also that several circuits he races have **no
> row at all**, which is a stronger refusal than any source value, not a
> weaker one.
>
> While a circuit's model reads `auto-segment`, corner identity is derived
> from speed minima and steering activity: unstable at many corners,
> unavailable at Monza, and *"turn three" is not a name this app may honestly
> use* there.
>
> `tools/build_track_map.py --apply` is what changes that, and **it writes the
> `source` column as well as the corners now** (12 Sep) — it did not, so a
> world-anchored model still exported as `auto-segment`, the one declaration
> `CLAUDE.md` §3.2 requires it to make. **It writes `track-map` only when
> EVERY corner in the model is anchored**, because the export declares one
> source for the whole model and a half-anchored one is not a track map. It is
> a writer: his call, never a step in a diagnosis. **Running it changes what
> may be said about that circuit's corners** — so say that before proposing
> it, not afterwards.

- `tools/data_health.py` — what may honestly be claimed about one car at one circuit, before claiming it.
- `tools/axis_board.py` — what has been measured on this car, and which axes nobody has tried.
- `tools/where_the_change_landed.py` — where on the lap a change landed (above).
- `tools/where_the_time_went.py` — where 1.71's lap time went, by distance bin.
- `tools/debrief.py` — the whole debrief, in the protocol's order (row 2.5): his report, the open ledger rows, the session, where a change landed, how it was driven, the driver as a variable, George's calls, the race against its plan, the radio. `--db` points it at a copy.
- `tools/driving_style.py` — coast share and upshift rpm, per lap and per stint.
- `tools/brake_bias.py` — what brake balance **does**, measured off the wheels. GT7 sends no brake-bias channel, so the bias itself is DECLARED, never measured; this reads its effect. Four lines above is the list of what telemetry can verify, and the bias is not on it.
- `tools/braking_change.py` — whether 1.71 changed braking, and whether later braking pays.
- `tools/shift_points.py` — where to shift, per car and gear, **derived from his own laps** (the table is still issued, never typed). **Not the MCP `shift_points`**, which is the table already ISSUED and in the car: two different things under one word, and quoting the derived one as the issued one is the §1a failure this programme is built around.
- `tools/shift_target.py` — how far to short-shift for a given race, and where it turns against him.
- `tools/shortshift_trade.py` — what short-shifting costs and saves, off laps he drove.
- `tools/find_penalties.py` — which laps served a track-limit penalty, off the frames.
- `tools/replay_race_calls.py` — a recorded race replayed through the engineer: what he would have said.
- `tools/radio_review.py` — what he asked on the radio, and what the engineer could not take.
- `tools/gate_bands.py` — whether the voice vocabulary reaches the questions he asks.
- `tools/geometric_corners.py` — corners as fixed places on the earth, from the track's shape.
- `tools/draw_track_map.py` — the circuit drawn from his telemetry, in GT7's orientation.
- `tools/analyse_m0.py` — the constants an M0 capture supports.
- `pitcrew.analysis.wear_rates` (`fit`, `fit_stint`, `worst_corner`) — wear rates fitted from what the gauge read, per compound. **Not `carry_into_knowledge`**, which is in the same module and writes: see below.
- `pitcrew.analysis.refuel` (`measure_refuel_rate`, `refuel_evidence`) — how fast the car takes fuel, measured.
- `pitcrew.race.temps` (`measured_temp_window`) — the tyre-temperature range from this event's own laps (a range, never an optimum).
- `pitcrew.race.tyre_split` (`SplitHistory`) — which way a tyre's split against its opposite is going, per lap.
- `pitcrew.race.call_outcome` (`judge`, `summarise`) — what happened after the engineer said something, where the app can tell.
- `pitcrew.race.pit_wall` (`PitWall`) — who was in the lane, on what, with how much.

**Over MCP** (`pitcrew/mcp/server.py`, eighteen tools). **This section left the
whole seam out**, so the standing rule below reached fourteen scripts and none
of the seven MCP calls that write — while `SKILL.md` sends you to four of them
by name. Eleven read and seven write, and **which side a call is on is the
whole of what this list is for** — so each gets its own line.

- `list_events` (MCP) — the events on file, with the regulations each carries.
- `slider_ranges` (MCP) — the car's own slider minima and maxima, from `range_records`.
- `event_export` (MCP) — the `gt7-pitcrew` payload for one event, as the tune builder reads it.
- `laps` (MCP) — a session's recorded laps, aggregated, each figure with its sample count.
- `strategy_evidence` (MCP) — what a plan may honestly be built on, and what is missing.
- `car_context` (MCP) — the car as the app holds it, for the event in front of you.
- `shift_points` (MCP) — the upshift tables **issued** for a car, which is the one the beep actually uses. **Not `tools/shift_points.py`**, which derives a table from his laps: the same word for the two halves of rank zero, and they can differ.
- `measurements` (MCP) — the measurement rows on file for a car and circuit.
- `axis_status` (MCP) — where each axis stands: tried, confirmed, refuted, untouched.
- `prompt_log` (MCP) — what was asked of the engineer, and when.
- `engineer_writes` (MCP) — the journal of what was written, and through which door.

**Writers — each changes the database. Run one only with the driver's yes, and
never as a step of a diagnosis.**

- `propose_strategy` (MCP) — **writes.** It saves the strategy it proposes,
  through `store.save_strategy`. The name reads like a proposal; it is not one.
- `write_shift_points` (MCP) — the shift table, per car and circuit. **This is
  the authoritative write of the one setup artefact that reaches him through
  the app**, as a beep at 60 Hz. It also refuses a fuel-saving rpm at or above
  its performance rpm, but that refusal is a property of the write, not a check
  to run during a diagnosis.
- `write_strategy` (MCP) — the race plan, stamped with the context it was approved for.
- `write_race_knowledge` (MCP) — the circuit's knowledge row: pit loss, burn, wear.
- `write_qualifying_plan` (MCP) — the qualifying plan, through `save_qualifying_plan`.
- `write_measurement` (MCP) — a measurement row, through `store.record_measurement`, journalled with `note_engineer_write`.
- `write_verdict` (MCP) — a verdict row, through `store.record_verdict`, journalled the same way.

- `tools/backfill_measurements.py --apply` — numbers written into prose, as measurement and verdict rows.
- `tools/build_track_map.py --apply` — anchors each corner to a place on the earth. **Read the corner refusal above before this is so much as mentioned to him:** it is the one tool here that can make `refusals.md` false, and it cannot do so honestly until it writes `corner_models.source` as well as `corners_json`.
- `tools/derive_grip_observations.py --apply` — grip observations from sessions on disk.
- `tools/fit_tyre_models.py --apply` — clears and refits the tyre models from those observations.
- `tools/flag_out_laps.py --apply` — re-judges each session's opening lap as an out-lap or not.
- `tools/reaggregate.py --apply` — re-reads stored sessions for stops the app missed.
- `tools/repair_dropped_laps.py --apply` — restores laps GT7 counted and the app did not.
- `tools/stamp_game_versions.py --apply` — the GT7 version on sessions recorded before the column.
- `tools/read_hud_wear.py --apply` — the wear gauge read off an OBS capture, against the laps.
- `tools/read_replay_traffic.py --apply` — who was around him, off the replay's radar.
- `tools/read_replay_board.py --apply` — names those cars off the replay's leaderboard.

  Each of those eleven leaves the DATABASE alone without `--apply` — not the
  disk: `read_replay_board` writes its roster JSON and its cluster PNGs on the
  dry run, by design. **Three do not work that way at all:**
- `tools/derive_sectors.py` — **writes by default**; `--dry-run` reports only.
- `tools/series.py` — `--set` writes at once; `--like`/`--car` ask first unless `--yes`.
- `tools/name_drivers.py` — writes as soon as it is given a name (`old new`, `--me`, `--teammate`).
- `pitcrew.analysis.wear_rates.carry_into_knowledge` — writes the fitted rates into `race_knowledge` through `store.save_race_knowledge`, whenever it is called.

**Not instruments for this skill** (the app's own health, voice, rig and
build — and two one-off scripts, which is what `draw_bathurst_map` and
`extract_reference` are): `audition_voices`, `render_voice_pack`, `render_voice_ab`,
`render_kokoro_audition`, `stt_bench`, `haptics_bench`, `rig_levels`,
`wind_bench`, `wind_replay`, `wind_sweep`, `install_shortcut`,
`probe_extended_packet`, `gap_bank`, `board_bench`, `build_race_fixture`,
`extract_reference`, `draw_bathurst_map`, `schema_audit`, `wiring_audit`.

**`draw_bathurst_map` is to be left alone, not merely skipped.** It opens
`Store()` and `data/pitcrew.db` at module scope, with one session number
written into it — so *importing* it is a write to the live database, before
any function of yours runs.

---

## Before anything is issued

**Nothing in the app checks a sheet any more.** `SetupSheet` (removed) and its
validator went with the setup record (`CLAUDE.md` §1a), so the checks it made are yours,
against `range_records`: every value inside its slider's range for this car
(`RangeRecord.fraction_of_range`); a sign only on toe front, toe rear and brake
balance; gears strictly descending, every ratio positive, nine at most. The
shift table is still checked by the app at the moment you ISSUE it —
`write_shift_points` refuses a fuel-saving rpm at or above its performance rpm.
**That refusal lives inside the write, and is not a check you can run first:**
the call that validates the table is the call that stores it, and it is listed
with the writers above, under their rule.

---

## The deliverable

Two artefacts, always both.

**1. The human sheet.** GT7's in-game order exactly, race primary and qualifying
as a delta. Every per-car value given three ways — the absolute, the position in
its range, and the physical meaning — because one alone is unenterable, one
alone is meaningless across cars, and one alone is unverifiable. The format is
specified in the knowledge base; follow it rather than inventing a layout.

Five things travel with it, and a sheet without them is not finished: deviation
notes one per moved value, the gearing derivation, the strategy note, three
things to test first in priority order, and confidence flags.

**2. The car-state file.** `brain/car-state/<car>-<circuit>.md` is updated with
the sheet - the one place a setup value is written (`CLAUDE.md` §1a). The paste
block that used to feed the app is retired with its parser (`09`); nothing in
the app takes a setup now.

---

## Then record it

Every change is an experiment (SKILL.md, *The record*), and it is a row in
`brain/ledger/<car>-<circuit>.md`, written **before the run** (`refine` step
6): key, direction and delta in points of range - never a setting - with the
instrument, its floor, the control, the prediction and the falsifier. Nothing
files it for you: the app's old `setup_changes` table has no writer, and a
change ledger in the database would be the second setup record `CLAUDE.md` §1a
removed. The **prediction is yours**, and it is the part that makes the ledger
learning rather than logging.
