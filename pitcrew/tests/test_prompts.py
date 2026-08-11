"""The Race Engineer prompts, against the handoff's own acceptance tests.

The HTML tool this replaces is only deletable when these pass, so they are
written as the acceptance list rather than as unit tests of the builder:

1. zero re-entry     2. range single-source     3. round trip
4. honest gaps       5. no advice               6. reproducible
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from pitcrew.export.build import build_event_export
from pitcrew.export.payload import to_json
from pitcrew.prompts import (
    BRIEF,
    KINDS,
    OUTCOME,
    PROMPT_VERSION,
    REFINEMENT,
    DriverReport,
    PromptRefused,
    build_prompt,
    gather,
)
from pitcrew.prompts import context as ctx
from pitcrew.setup.parse import parse_sheet
from pitcrew.setup.sheet import RangeRecord, SetupChange, SetupSheet
from pitcrew.store import catalogs
from pitcrew.telemetry.session_state import Lap

CAR = "Porsche 911 RSR (991) '17"
CIRCUIT = "Fuji International Speedway"
TODAY = "2026-08-12"

SHEET_VALUES = {
    "rh_f": 62, "rh_r": 70, "nf_f": 3.42, "nf_r": 3.68, "arb_f": 6, "arb_r": 4,
    "dc_f": 28, "dc_r": 30, "de_f": 40, "de_r": 38, "cam_f": 1.2, "cam_r": 1.2,
    "toe_f": 0.0, "toe_r": 0.08, "lsd_i": 5, "lsd_a": 15, "lsd_b": 25,
    "df_f": 380, "df_r": 600, "bb": -1, "top": 300, "fg": 3.72,
}
GEARS = [3.10, 2.28, 1.79, 1.46, 1.22, 1.04]


# ------------------------------------------------------------------ fixtures

def make_event(store, **overrides) -> int:
    fields = dict(
        name="Round 4 - Fuji", track=CIRCUIT, car_name=CAR,
        race_type="laps", race_laps=20, weather="dry",
        tyre_wear_mult="4x", fuel_mult="2x", refuel_rate_lps=1.0,
        pit_loss_secs=19.5, mandatory_stops=1,
        available_compounds=["RH", "RM", "RS"], abs_setting="Weak", tcs=1,
        countersteer=0, start_type="Rolling", time_of_day="Fixed day",
        priority="Race pace and tyre life", notes="League bans ballast.")
    fields.update(overrides)
    return store.create_event(**fields)


def make_sheet(store, name: str = "Fuji race v2", **overrides) -> int:
    sheet = SetupSheet(car_name=CAR, sheet_name=name,
                       values=dict(overrides.pop("values", SHEET_VALUES)),
                       gears=list(GEARS),
                       build={"bhp": 525, "weightKg": 1300, "pp": 730.12},
                       performance={"powerRestrictor": 100, "ecuOutput": 100})
    return store.save_setup_sheet(sheet)


def record_laps(store, session_id: int, times, *, pit_last: bool = True):
    fuel = 92.1
    for index, value in enumerate(times, 1):
        lap = Lap(lap_num=index, lap_time_ms=value, best_lap_ms=min(times),
                  delta_ms=0, fuel_start=fuel, fuel_end=fuel - 3.4,
                  fuel_used=3.4, position=3,
                  is_pit_lap=pit_last and index == len(times),
                  is_out_lap=index == 1, compound="RM")
        fuel -= 3.4
        lap_id = store.add_lap(session_id, lap)
        if index == 6:
            store.set_lap_wear(lap_id, 0.55, 0.42)


@pytest.fixture()
def practice_event(store):
    """An event with a sheet, measured ranges and a recorded practice run."""
    store.seed_range_records(catalogs.range_seed_records())
    event_id = make_event(store)
    sheet_id = make_sheet(store)
    session_id = store.start_session(event_id, "practice",
                                     setup_sheet_id=sheet_id)
    store.note_stream_facts(session_id, packet_format="C",
                            car_category="Gr.3", fuel_capacity_l=100.0)
    record_laps(store, session_id,
                [95800, 94100, 93912, 94300, 94480, 94600, 94900, 95100,
                 95400, 95900, 101000])
    store.add_setup_change(session_id, SetupChange(
        from_lap=5, key="arb_r", from_value=4, to_value=3))
    store.end_session(session_id)
    store.set_state("active_event_id", event_id)
    return event_id


REPORT = DriverReport(
    symptoms=("Rear excited / sketchy under braking",
              "Entry understeer under trail braking"),
    biggest_limitation="Rear excited / sketchy under braking",
    costs_most_where="Heavy braking zones",
    balance_drift="Migrated to understeer",
    tyre_state_at_end="Past peak but usable",
    notes="Rear goes light into T1 from lap 6.")


def prompt_for(store, event_id, kind, report=REPORT):
    context = gather(store, event_id=event_id, kind=kind)
    return build_prompt(context, report, kind=kind, today=TODAY)


# --------------------------------------------------- 1. zero re-entry

def test_refinement_carries_every_fact_the_app_already_has(store,
                                                           practice_event):
    """Nothing in the left-hand column of the handoff's table is retyped."""
    text = prompt_for(store, practice_event, REFINEMENT).text

    for fact in (
        CAR, CIRCUIT,                       # identity
        "Fuji race v2",                     # the sheet as run
        "Tyre wear **4x**", "Fuel **2x**",  # multipliers
        "Mandatory stops **1**",
        "RH, RM, RS",                       # compounds
        "Start: Rolling", "Fixed day",
        "ABS **Weak**", "TCS **1**",
        "laps run **11**", "laps counted **9**",
        "compound **RM**",
        "1:33.912",                         # best lap, off the stream
        "3.4 L/lap",                        # fuel burn
        "arb_r",                            # the mid-session change
        "Front-left",                       # circuit reference wear axle
        "Gr.3",                             # car reference
    ):
        assert fact in text, f"{fact!r} was not carried into the prompt"


def test_the_driver_supplies_only_perception(store, practice_event):
    """The report has no field the app could have answered for itself."""
    stated = set(vars(DriverReport()))
    # Everything the app knows is absent from the report by construction.
    for derivable in ("car", "circuit", "laps", "best_lap", "fuel",
                      "compound", "sheet", "ranges", "multipliers",
                      "assists", "pit_loss", "refuel_rate"):
        assert derivable not in stated


def test_the_setup_section_is_state_not_a_paste_box(store, practice_event):
    text = prompt_for(store, practice_event, REFINEMENT).text
    section = text[text.index("## Setup as run"):text.index("## What the car")]
    # Absolute, clicks from minimum and percent of range - all three, per the
    # sheet format the knowledge base reads.
    assert "| Ride height — front | 62 mm | +7 | 28% |" in section
    assert "3.1  2.28  1.79" in section          # the gears, in order
    assert "from lap 5: `arb_r` 4 → 3" in section


def test_driver_changes_are_structured_lines_not_prose(store, practice_event):
    text = prompt_for(store, practice_event, REFINEMENT).text
    assert re.search(r"from lap \d+: `\w+` .+ → .+", text)


def test_the_payload_is_embedded_verbatim(store, practice_event):
    """The same bytes the export produces, not a second rendering of them."""
    text = prompt_for(store, practice_event, REFINEMENT).text
    payload = to_json(build_event_export(store, practice_event,
                                         kind="practice"))
    assert payload in text
    assert "Where the Pit Crew data and my report disagree" in text


# --------------------------------------------- 2. range single-source

def test_ranges_measured_once_reach_all_three_prompts(store):
    event_id = make_event(store)
    make_sheet(store)
    store.save_range_record(RangeRecord(
        car_name=CAR, measured_date="2026-08-11", verified=True,
        ranges={"rh_f": [55, 80], "nf_f": [3, 5], "arb_f": [1, 10]}))

    for kind in KINDS:
        text = prompt_for(store, event_id, kind).text
        assert "| Ride height — front | 55 mm | 80 mm |" in text
        assert "read off" in text, f"{kind} did not say the ranges are measured"
        assert "not verified" not in text


def test_the_export_carries_the_same_ranges_in_the_same_keys(store,
                                                             practice_event):
    payload = build_event_export(store, practice_event, kind="practice")
    record = payload["rangeRecord"]
    assert record["car"] == CAR
    assert record["verified"] is True
    assert record["r"]["rh_f"] == [55, 80]

    context = gather(store, event_id=practice_event, kind=REFINEMENT)
    assert context.ranges.source == ctx.RANGES_RECORD
    assert context.ranges.values["rh_f"] == [55, 80]


def test_an_unmeasured_car_falls_back_to_a_labelled_estimate(store):
    event_id = make_event(store, car_name="Ferrari 296 GT3 '23")
    text = prompt_for(store, event_id, BRIEF).text
    assert "Not verified on this car" in text
    assert "GT7 typical race-car windows" in text


# ------------------------------------------------------- 3. round trip

def test_the_outcome_prompt_asks_for_the_paste_block_the_parser_reads(store,
                                                                      practice_event):
    text = prompt_for(store, practice_event, OUTCOME).text
    assert "`gt7-pitcrew/1.1` paste block" in text
    assert "race block first, then qualifying, one block per sheet" in text


def test_a_returned_block_still_parses_to_the_acceptance_string():
    """The parser is unchanged, so what comes back still lands."""
    block = json.dumps({
        "setup": {
            "sheetName": "Fuji race v3",
            "values": {**SHEET_VALUES, "awd": None},
            "gears": GEARS,
        }
    })
    result = parse_sheet(block)
    assert result.summary().startswith("22 of 23 settings, 6 gears")


# ------------------------------------------------------ 4. honest gaps

@pytest.fixture()
def bare_event(store):
    """No telemetry, no strategy, no measured ranges - the worst case."""
    event_id = make_event(store, car_name="Ferrari 296 GT3 '23")
    store.set_state("active_event_id", event_id)
    return event_id


@pytest.mark.parametrize("kind", KINDS)
def test_every_prompt_is_usable_with_nothing_recorded(store, bare_event, kind):
    prompt = prompt_for(store, bare_event, kind)
    assert prompt.text.strip()
    assert PROMPT_VERSION in prompt.text
    # The absences are stated rather than defaulted.
    assert "Not verified on this car" in prompt.text or \
           "not verified on this car" in prompt.text


@pytest.mark.parametrize("kind", [REFINEMENT, OUTCOME])
def test_absent_telemetry_omits_the_fence_rather_than_emitting_an_empty_one(
        store, bare_event, kind):
    text = prompt_for(store, bare_event, kind).text
    assert "**Not used this session.**" in text
    assert "```json" not in text
    assert "```\n```" not in text


@pytest.mark.parametrize("kind", KINDS)
def test_nothing_unmeasured_is_reported_as_zero(store, bare_event, kind):
    """The failure this whole feature exists to prevent.

    A zero that means "not measured" gets diagnosed as a real value. Nothing
    the app did not measure may render as one.
    """
    text = prompt_for(store, bare_event, kind).text
    for line in text.splitlines():
        if line.startswith("|"):
            continue        # slider ranges legitimately have a minimum of 0
        assert not re.search(r"\*\*0(\.0+)?\s*(ms|L|s|laps|bhp|kg)?\*\*", line), \
            f"a zero stands where nothing was measured: {line!r}"


def test_a_small_assumption_is_not_rounded_away_to_zero(store, practice_event):
    """0.003 s/L/lap printed as **0** is the same bug wearing a decimal point."""
    from pitcrew.prompts.build import _number
    assert _number(0.003) == "0.003"
    assert _number(None) == "not recorded"
    assert _number(0.0) == "0"


def test_an_event_with_no_car_is_refused_rather_than_guessed(store):
    event_id = store.create_event(name="Blank", track=CIRCUIT)
    context = gather(store, event_id=event_id, kind=BRIEF)
    with pytest.raises(PromptRefused, match="no car"):
        build_prompt(context, DriverReport(), kind=BRIEF, today=TODAY)


def test_an_unknown_circuit_says_so_instead_of_borrowing_another(store):
    event_id = make_event(store, track="Somewhere Nobody Modelled")
    text = prompt_for(store, event_id, BRIEF).text
    assert "not in the circuit reference" in text
    assert "wears" not in text.split("## Event")[0].split("## Circuit")[-1]


def test_a_first_run_says_first_run_rather_than_printing_an_empty_heading(
        store):
    event_id = make_event(store)
    text = prompt_for(store, event_id, BRIEF).text
    assert "First run of this combination" in text


def test_history_reports_what_the_last_refinement_actually_changed(store):
    """Deltas come from comparing the two sheets, not from a remembered note."""
    old_id = make_event(store, name="Round 3 - Fuji")
    old_sheet = make_sheet(store, name="Fuji race v1",
                           values={**SHEET_VALUES, "arb_r": 4, "bb": -1})
    session_id = store.start_session(old_id, "practice",
                                     setup_sheet_id=old_sheet)
    record_laps(store, session_id, [94500, 94100, 94300])
    store.end_session(session_id)

    new_id = make_event(store, name="Round 4 - Fuji")
    make_sheet(store, name="Fuji race v2",
               values={**SHEET_VALUES, "arb_r": 3, "bb": -2})

    text = prompt_for(store, new_id, BRIEF).text
    assert "Last run of this combination: **Round 3 - Fuji**" in text
    assert "`arb_r` 4 → 3" in text
    assert "`bb` -1 → -2" in text


def test_a_setting_absent_from_the_old_sheet_is_not_a_change_from_zero(store):
    old = SetupSheet(car_name=CAR, sheet_name="old", values={"arb_f": 6})
    new = SetupSheet(car_name=CAR, sheet_name="new",
                     values={"arb_f": 6, "toe_r": 0.08})
    assert ctx._sheet_deltas(old, new) == []


# -------------------------------------------------------- 5. no advice

APP_SOURCES = (
    Path("pitcrew/prompts/templates.json"),
    Path("pitcrew/prompts/build.py"),
    Path("pitcrew/prompts/context.py"),
    Path("pitcrew/ui/engineer_screen.py"),
    Path("pitcrew/ui/car_screen.py"),
)

# An imperative verb applied to a setting is the app telling the driver what
# to change. That belongs in the knowledge base, never here. The Reference
# screen is exempt by design - it displays the knowledge base's own material
# verbatim and is not in this list.
ADVICE = re.compile(
    r"\b(increase|decrease|stiffen|soften|raise|reduce|trim|"
    r"more|less|higher|lower)\b[^.\n]{0,40}"
    r"\b(camber|toe|arb|anti-roll|damper|spring|ride height|downforce|"
    r"brake balance|lsd|final gear)\b", re.IGNORECASE)


@pytest.mark.parametrize("path", APP_SOURCES, ids=lambda p: p.name)
def test_no_screen_or_template_tells_the_driver_what_to_change(path):
    text = path.read_text(encoding="utf-8")
    found = ADVICE.findall(text)
    assert not found, f"{path} gives setup advice: {found}"


def test_the_reference_material_never_reaches_a_prompt(store, practice_event):
    """The Quick Reference is display-only; nothing composes from it."""
    builder = Path("pitcrew/prompts/build.py").read_text(encoding="utf-8")
    gatherer = Path("pitcrew/prompts/context.py").read_text(encoding="utf-8")
    assert "quick_reference" not in builder
    assert "quick_reference" not in gatherer

    text = prompt_for(store, practice_event, REFINEMENT).text
    for section in catalogs.quick_reference().get("sections") or []:
        assert section["title"] not in text


# ----------------------------------------------------- 6. reproducible

@pytest.mark.parametrize("kind", KINDS)
def test_the_same_session_generates_byte_identical_output(store,
                                                          practice_event, kind):
    first = prompt_for(store, practice_event, kind).text
    second = prompt_for(store, practice_event, kind).text
    assert first == second


def test_the_footer_names_the_template_that_asked(store, practice_event):
    for kind in KINDS:
        text = prompt_for(store, practice_event, kind).text
        assert text.rstrip().endswith("*")
        assert PROMPT_VERSION in text.splitlines()[-1]
        assert TODAY in text.splitlines()[-1]


# ------------------------------------------------ prompt C in particular

@pytest.fixture()
def raced_event(store):
    store.seed_range_records(catalogs.range_seed_records())
    # A distinct name so this can share a store with `practice_event`:
    # events.name is unique.
    event_id = make_event(store, name="Round 5 - Fuji")
    sheet_id = make_sheet(store)
    session_id = store.start_session(event_id, "race",
                                     setup_sheet_id=sheet_id)
    store.note_stream_facts(session_id, packet_format="C",
                            car_category="Gr.3", fuel_capacity_l=100.0)
    fuel = 100.0
    for index in range(1, 21):
        lap = Lap(lap_num=index, lap_time_ms=94000 + index * 60,
                  best_lap_ms=94060, delta_ms=0, fuel_start=fuel,
                  fuel_end=fuel - 3.42, fuel_used=3.42, position=3,
                  is_pit_lap=index == 11, is_out_lap=index == 1,
                  compound="RM")
        fuel = 100.0 if index == 11 else fuel - 3.42
        lap_id = store.add_lap(session_id, lap)
        if index in (6, 11):
            store.set_lap_wear(lap_id, 0.55 if index == 6 else 0.88,
                               0.42 if index == 6 else 0.71)
    store.end_session(session_id)

    plan = {
        "stops": 1, "pit_laps": [11],
        "stints": [{"laps": 11, "compound": "RM", "fuel_l": 100,
                    "start_lap": 1}],
        "export": {
            "plan": {"stops": 1, "stintLaps": [11, 9],
                     "compounds": ["RM", "RM"], "pitLap": 11},
            "bindingConstraint": "fuel",
            "assumptions": {"pitLossS": 19.5,
                            "pitLossSource": "measured-this-track",
                            "fuelPerLapL": 3.42,
                            "fuelWeightSPerLPerLap": 0.003,
                            "fuelWeightSource": "derived-not-measured",
                            "compoundDeltaSPerLap": None}},
    }
    strategy_id = store.save_strategy(event_id, plan, label="One stop")
    store.approve_strategy(strategy_id)
    run_id = store.start_race_run(event_id, strategy_id, session_id)
    store.append_revision(run_id, 4, "Map 3 down the back straight",
                          {"confidence": "high"}, accepted=False)
    store.append_revision(run_id, 9, "Brake balance one click rearward",
                          {"confidence": "medium"}, accepted=True)
    store.finish_race_run(run_id)
    store.set_state("active_event_id", event_id)
    return event_id


def test_the_outcome_prompt_reports_planned_against_actual(store, raced_event):
    text = prompt_for(store, raced_event, OUTCOME).text
    assert "## Strategy — planned vs actual" in text
    assert "stint laps **11 / 9**" in text
    assert "Actually run: **1** stop on lap 11" in text
    assert "Binding constraint" in text and "**fuel**" in text
    assert "`refuelRateLps`: **1**" in text
    assert "`fuelWeightSPerLPerLap`: **0.003**" in text


def test_declined_calls_survive_to_the_prompt(store, raced_event):
    """A plan offered and refused is evidence about the model."""
    text = prompt_for(store, raced_event, OUTCOME).text
    assert "| 4 | Map 3 down the back straight | high | declined |" in text
    assert "| 9 | Brake balance one click rearward | medium | accepted |" in text


def test_wear_is_never_presented_as_measured(store, raced_event):
    text = prompt_for(store, raced_event, OUTCOME).text
    assert "GT7 exposes no tyre wear channel in any packet format" in text
    assert "Driver gauge: lap 6, front 55%, rear 42% [driver-gauge]" in text
    assert "multiplier actually raced" in text


def test_a_converted_stint_is_flagged_as_unproven(store, raced_event):
    context = gather(store, event_id=raced_event, kind=OUTCOME)
    # Recompute the payload as if the wear rate came from another multiplier.
    context.payload = build_event_export(
        store, raced_event, kind="race", calibrated_at_race_multiplier=False)
    text = build_prompt(context, REPORT, kind=OUTCOME, today=TODAY).text
    assert "NOT measured at the multiplier raced" in text
    assert "linearity is assumed" in text


def test_the_outcome_prompt_asks_for_knowledge_base_updates(store,
                                                            raced_event):
    """Item 5 is the reason prompt C exists."""
    text = prompt_for(store, raced_event, OUTCOME).text
    assert "Knowledge-base updates, stated explicitly and separately" in text
    assert "claim in the knowledge base this event contradicts" in text
    assert "measured next session" in text
    assert "Item 5 is why this prompt exists" in text


def test_the_finishing_position_comes_off_the_stream(store, raced_event):
    text = prompt_for(store, raced_event, OUTCOME).text
    assert "Finished **P3**" in text


def test_no_prompt_ever_claims_a_tow(store, raced_event, practice_event):
    """GT7's feed has no proximity or closing speed, so a tow is a fabrication."""
    for event_id, kind in ((raced_event, OUTCOME),
                           (practice_event, REFINEMENT)):
        text = prompt_for(store, event_id, kind).text
        assert not re.search(r"tow(Speed|Kph|\w*)\s*[:=]", text)
        assert "no proximity" in text or "Traffic and tow" not in text


# --------------------------------------------------------- the prompt log

def test_every_prompt_issued_is_logged_with_its_template(store,
                                                         practice_event):
    prompt = prompt_for(store, practice_event, REFINEMENT)
    issue_id = store.log_prompt(
        kind=REFINEMENT, body=prompt.text, prompt_version=prompt.version,
        app_version=prompt.app_version, event_id=practice_event,
        car_name=CAR, circuit=CIRCUIT)
    logged = store.get_prompt(issue_id)
    assert logged["prompt_version"] == PROMPT_VERSION
    assert logged["body"] == prompt.text
    assert logged["reply"] is None

    store.save_prompt_reply(issue_id, "Here is the revised sheet.")
    logged = store.get_prompt(issue_id)
    assert logged["reply"] == "Here is the revised sheet."
    assert logged["replied_at"]
    assert store.list_prompts(practice_event)[0]["id"] == issue_id


# ------------------------------------------------------- reference data

def test_the_symptom_vocabulary_is_data_not_a_hard_coded_list():
    groups = catalogs.symptom_groups()
    assert len(catalogs.symptoms()) == 28
    assert [name for name, _ in groups] == [
        "Braking", "Entry", "Mid", "Exit", "Surface", "Gearing", "Stint",
        "Overall"]
    for source in ("pitcrew/prompts/build.py", "pitcrew/ui/engineer_screen.py"):
        text = Path(source).read_text(encoding="utf-8")
        assert "Rear excited" not in text


def test_the_circuit_reference_never_borrows_a_sibling_layout():
    """Big Willow's wear axle must not attach to Streets of Willow."""
    assert catalogs.circuit_for(
        "Willow Springs International Raceway", "Big Willow").name \
        == "Willow Springs Big Willow"
    assert catalogs.circuit_for(
        "Willow Springs International Raceway",
        "Streets of Willow Springs") is None
    assert catalogs.circuit_for("Willow Springs International Raceway") is None


def test_the_car_reference_carries_the_drivetrain_the_old_file_lacked():
    spec = catalogs.car_spec(CAR)
    assert spec["drivetrain"] == "MR"
    assert spec["category"] == "Gr.3"
    # The scraped file filed every Gr.B rally car under Gr.4.
    assert catalogs.car_spec("Ford Focus Gr.B Rally Car")["category"] == "Gr.B"


def test_seeded_ranges_never_overwrite_a_measured_record(store):
    store.save_range_record(RangeRecord(
        car_name=CAR, measured_date="2026-08-12", verified=True,
        ranges={"rh_f": [40, 90]}))
    assert store.seed_range_records(catalogs.range_seed_records()) == 0
    assert store.get_range_record(CAR).ranges["rh_f"] == [40, 90]
