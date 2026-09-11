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

Everything else on a sheet — twenty-one of twenty-three values — has **no ground
truth in the feed.** For those, the record is what he tells you, and the only
defence is provenance and confirmation.

---

## Every instrument, one line each

Plan row 2.10. Ten of these existed and were re-derived by hand because
nothing named them. Run a tool before re-deriving what it answers; read its
own `--help` for the arguments. **Opening `Store()` upgrades the file it opens,
in a write transaction, every time** - so even a reader touches the database it
is pointed at. For work that must not, open sqlite with `mode=ro`, or a copy
that includes the `-wal` file.

**Readers — they answer a question and write nothing else.**

- `tools/data_health.py` — what may honestly be claimed about one car at one circuit, before claiming it.
- `tools/axis_board.py` — what has been measured on this car, and which axes nobody has tried.
- `tools/where_the_change_landed.py` — where on the lap a change landed (above).
- `tools/where_the_time_went.py` — where 1.71's lap time went, by distance bin.
- `tools/debrief.py` — the practice debrief for an event, lap by lap.
- `tools/driving_style.py` — coast share and upshift rpm, per lap and per stint.
- `tools/brake_bias.py` — what brake balance does, measured off the wheels.
- `tools/braking_change.py` — whether 1.71 changed braking, and whether later braking pays.
- `tools/shift_points.py` — where to shift, per car and gear, off his own laps (the table is still issued, never typed).
- `tools/shift_target.py` — how far to short-shift for a given race, and where it turns against him.
- `tools/shortshift_trade.py` — what short-shifting costs and saves, off laps he drove.
- `tools/find_penalties.py` — which laps served a track-limit penalty, off the frames.
- `tools/replay_race_calls.py` — a recorded race replayed through the engineer: what he would have said.
- `tools/radio_review.py` — what he asked on the radio, and what the engineer could not take.
- `tools/gate_bands.py` — whether the voice vocabulary reaches the questions he asks.
- `tools/geometric_corners.py` — corners as fixed places on the earth, from the track's shape.
- `tools/draw_track_map.py` — the circuit drawn from his telemetry, in GT7's orientation.
- `tools/analyse_m0.py` — the constants an M0 capture supports.
- `pitcrew.analysis.wear_rates` (`fit`, `fit_stint`, `worst_corner`) — wear rates fitted from what the gauge read, per compound.
- `pitcrew.analysis.refuel` (`measure_refuel_rate`, `refuel_evidence`) — how fast the car takes fuel, measured.
- `pitcrew.race.temps` (`measured_temp_window`) — the tyre-temperature range from this event's own laps (a range, never an optimum).
- `pitcrew.race.tyre_split` (`SplitHistory`) — which way a tyre's split against its opposite is going, per lap.
- `pitcrew.race.call_outcome` (`judge`, `summarise`) — what happened after the engineer said something, where the app can tell.
- `pitcrew.race.pit_wall` (`PitWall`) — who was in the lane, on what, with how much.

**Writers — each changes the database. Run one only with the driver's yes, and
never as a step of a diagnosis.**

- `tools/backfill_measurements.py --apply` — numbers written into prose, as measurement and verdict rows.
- `tools/build_track_map.py --apply` — anchors each corner to a place on the earth.
- `tools/derive_grip_observations.py --apply` — grip observations from sessions on disk.
- `tools/fit_tyre_models.py --apply` — clears and refits the tyre models from those observations.
- `tools/flag_out_laps.py --apply` — re-judges each session's opening lap as an out-lap or not.
- `tools/reaggregate.py --apply` — re-reads stored sessions for stops the app missed.
- `tools/repair_dropped_laps.py --apply` — restores laps GT7 counted and the app did not.
- `tools/stamp_game_versions.py --apply` — the GT7 version on sessions recorded before the column.
- `tools/read_hud_wear.py --apply` — the wear gauge read off an OBS capture, against the laps.
- `tools/read_replay_traffic.py --apply` — who was around him, off the replay's radar.
- `tools/read_replay_board.py --apply` — names those cars off the replay's leaderboard.

  Each of those eleven reports and writes nothing without `--apply`. **Three
  do not work that way:**
- `tools/derive_sectors.py` — **writes by default**; `--dry-run` reports only.
- `tools/series.py` — `--set` writes at once; `--like`/`--car` ask first unless `--yes`.
- `tools/name_drivers.py` — writes as soon as it is given a name (`old new`, `--me`, `--teammate`).

**Not instruments for this skill** (the app's own health, voice, rig and
build): `audition_voices`, `render_voice_pack`, `render_voice_ab`,
`render_kokoro_audition`, `stt_bench`, `haptics_bench`, `rig_levels`,
`wind_bench`, `wind_replay`, `wind_sweep`, `install_shortcut`,
`probe_extended_packet`, `gap_bank`, `board_bench`, `build_race_fixture`,
`extract_reference`, `draw_bathurst_map`, `schema_audit`, `wiring_audit`.

---

## Validation, before anything is filed

`SetupSheet.validate()` refuses: a key outside the shared vocabulary; a
non-numeric value; **a negative on an unsigned key** (only toe front, toe rear
and brake balance take a sign); a shift-rpm entry outside its gear or rpm
bounds; more than nine gears; a non-positive ratio; **gears not strictly
descending**. It does *not* check slider ranges.

---

## The deliverable

Two artefacts, always both.

**1. The human sheet.** GT7's in-game order exactly, race primary and qualifying
as a delta. Every per-car value given three ways — the absolute, the position in
its range, and the physical meaning — because one alone is unenterable, one
alone is meaningless across cars, and one alone is unverifiable. The format is
specified in the knowledge base; follow it rather than inventing a layout.

Six things travel with it, and a sheet without them is not finished: deviation
notes one per moved value, the gearing derivation, the strategy note, three
things to test first in priority order, confidence flags, and the paste block.

**2. The paste block.** The parser reads `sheetName`, `values` and `gears` and
nothing else. Numbers only inside `values`; signs explicit; gears in order.
**Omit a key entirely when it does not apply — never send it as null**, because
a null on a known key is dropped silently and you will not be told.

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
