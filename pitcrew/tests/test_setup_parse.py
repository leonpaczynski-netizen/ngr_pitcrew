"""Reading a pasted setup sheet."""
from __future__ import annotations

import json

from pitcrew.setup.parse import parse_sheet


def test_empty_paste_reads_nothing():
    assert parse_sheet("").matched_count == 0
    assert parse_sheet("   \n  ").matched_count == 0


# ---------------------------------------------------------------------- json

def test_reads_the_export_contract_shape():
    payload = json.dumps({"setup": {
        "sheetName": "Fuji race v2",
        "values": {"rh_f": 62, "arb_r": 4, "toe_r": 0.08},
        "gears": [3.10, 2.28, 1.79],
    }})
    result = parse_sheet(payload)
    assert result.source == "json"
    assert result.sheet_name == "Fuji race v2"
    assert result.values == {"rh_f": 62.0, "arb_r": 4.0, "toe_r": 0.08}
    assert result.gears == [3.10, 2.28, 1.79]


def test_reads_a_bare_setup_object():
    result = parse_sheet(json.dumps({"values": {"rh_f": 62}}))
    assert result.values == {"rh_f": 62.0}


def test_json_keys_outside_the_vocabulary_are_reported_not_dropped():
    result = parse_sheet(json.dumps({"values": {"rh_f": 62, "tyre_psi": 30}}))
    assert result.values == {"rh_f": 62.0}
    assert any("tyre_psi" in line for line in result.unmatched)


def test_malformed_json_falls_through_to_line_reading():
    result = parse_sheet('{"values": {"rh_f": 62,,,}\nrh_r: 70')
    assert result.source == "text"
    assert result.values.get("rh_r") == 70.0


# --------------------------------------------------------------------- lines

def test_reads_vocabulary_keys():
    result = parse_sheet("rh_f: 62\nrh_r = 70\narb_f 6")
    assert result.values == {"rh_f": 62.0, "rh_r": 70.0, "arb_f": 6.0}


def test_reads_human_labels():
    result = parse_sheet(
        "Ride Height Front: 62\n"
        "Anti-roll bar rear: 4\n"
        "Damper Compression Front: 28\n"
        "Brake Balance: -1")
    assert result.values["rh_f"] == 62.0
    assert result.values["arb_r"] == 4.0
    assert result.values["dc_f"] == 28.0
    assert result.values["bb"] == -1.0


def test_reads_a_markdown_table():
    result = parse_sheet(
        "| Setting | Value |\n"
        "|---|---|\n"
        "| Camber Front | 1.2 |\n"
        "| Camber Rear | 1.4 |")
    assert result.values == {"cam_f": 1.2, "cam_r": 1.4}


def test_negative_and_decimal_values_survive():
    result = parse_sheet("toe_f: -0.05\nfg: 3.720")
    assert result.values["toe_f"] == -0.05
    assert result.values["fg"] == 3.720


def test_units_after_the_value_are_ignored():
    result = parse_sheet("Camber Front: 1.2 deg\nRide height front: 62 mm")
    assert result.values["cam_f"] == 1.2
    assert result.values["rh_f"] == 62.0


def test_reads_a_gear_list():
    result = parse_sheet("Gears: 3.10 2.28 1.79 1.46 1.22 1.04")
    assert result.gears == [3.10, 2.28, 1.79, 1.46, 1.22, 1.04]


def test_reads_gears_stated_one_per_line():
    result = parse_sheet("Gear 1: 3.10\nGear 2: 2.28\nGear 3: 1.79")
    assert result.gears == [3.10, 2.28, 1.79]


def test_unrecognised_lines_come_back_rather_than_vanishing():
    """A value quietly missed is a setup change the driver thinks he made."""
    result = parse_sheet("rh_f: 62\nTyre pressure: 30\nSomething else entirely")
    assert result.values == {"rh_f": 62.0}
    assert len(result.unmatched) == 2


def test_separator_rows_are_not_reported_as_unmatched():
    result = parse_sheet("| Setting | Value |\n|-----|-----|\n| rh_f | 62 |")
    assert result.values == {"rh_f": 62.0}
    assert result.unmatched == ["Setting | Value"]


def test_summary_states_what_was_read():
    result = parse_sheet("rh_f: 62\nGears: 3.1 2.2\nNonsense here")
    summary = result.summary()
    assert "1 of 23 settings" in summary
    assert "2 gears" in summary
    assert "1 lines not recognised" in summary


def test_a_sheet_of_pure_junk_matches_nothing():
    result = parse_sheet("the quick brown fox\njumped over")
    assert result.matched_count == 0
    assert len(result.unmatched) == 2
