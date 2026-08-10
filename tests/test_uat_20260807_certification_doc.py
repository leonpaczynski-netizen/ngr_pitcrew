"""The certification script must not drift from the app — UAT 2026-08-07 defect E3.

The three root-level UAT scripts became unrunnable silently: the shell grew eleven nav
destinations, the tab bar went away and the AI path was removed, and nothing failed when
the documents stopped describing the app. 79 steps sat there navigating to a UI that no
longer existed, with every Pass/Fail cell empty.

A document nobody can verify rots exactly that way, so the parts of the certification
script that ARE checkable are checked here: the destinations it tells the driver to
navigate to, the numbers it tells them to expect, and the fact that the superseded
scripts say so. Prose is left to prose — this only pins the facts.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_DOC = _ROOT / "docs" / "UAT_2026-08-07_REMEDIATION_CERTIFICATION.md"
_SUPERSEDED = ("SETUP_BUILDER_UAT.md", "LIVE_RACE_ENGINEER_UAT.md",
               "STRATEGY_BUILDER_UAT.md")


@pytest.fixture(scope="module")
def doc() -> str:
    return _DOC.read_text(encoding="utf-8")


def test_the_certification_script_exists(doc):
    assert doc.strip()


# ---------------------------------------------------------------------------
# Navigation — the thing the old scripts got wrong
# ---------------------------------------------------------------------------
def test_every_nav_destination_is_named(doc):
    """If a destination is added or renamed, the script must be updated with it."""
    from ui.components.nav_rail import NAV_LABELS
    from ui.app_state import NAV_DESTINATIONS
    missing = [NAV_LABELS[d] for d in NAV_DESTINATIONS if NAV_LABELS[d] not in doc]
    assert not missing, f"the script never mentions: {missing}"


def test_the_script_names_no_destination_that_does_not_exist(doc):
    """The old scripts sent the driver to a "Setup Builder tab" that is gone."""
    from ui.components.nav_rail import NAV_LABELS
    from ui.app_state import NAV_DESTINATIONS
    real = {NAV_LABELS[d] for d in NAV_DESTINATIONS}
    # The rail block lists the destinations separated by "·".
    block = re.search(r"`Home`(.+?)\n\n", doc, re.S)
    assert block, "the nav rail block is missing from the script"
    listed = {m.strip() for m in re.findall(r"`([^`]+)`", "`Home`" + block.group(1))}
    assert listed == real, f"script lists {listed - real} which do not exist"


def test_the_destination_count_is_stated_correctly(doc):
    from ui.app_state import NAV_DESTINATIONS
    assert len(NAV_DESTINATIONS) == 11
    assert "eleven nav destinations" in doc or "eleven" in doc


def test_it_says_there_are_no_tabs(doc):
    """The single most important navigation fact for anyone who ran the old scripts."""
    assert "no tab bar" in doc or "no tabs" in doc


# ---------------------------------------------------------------------------
# The numbers the driver is told to expect
# ---------------------------------------------------------------------------
def test_the_gr3_sanity_anchor_matches_the_vetted_setup(doc):
    """The script tells the driver a Gr.3 should land near the vetted Porsche RSR
    values. If the proven library changes, this must change with it."""
    setups = json.loads(
        (_ROOT / "data" / "proven_setups.json").read_text(encoding="utf-8"))["setups"]
    race = [s for s in setups if s["discipline"] == "race" and "Monza" in s["track"]][0]
    f = race["fields"]
    anchor = re.search(r"a Gr\.3 should land near \*\*(.+?)\*\*", doc, re.S)
    assert anchor, "the sanity anchor is missing from the script"
    text = anchor.group(1)
    for value in (f["ride_height_front"], f["ride_height_rear"],
                  f["camber_front"], f["camber_rear"],
                  f["aero_front"], f["aero_rear"]):
        assert str(value) in text, f"{value} is not in the stated anchor"


def test_the_spring_band_matches_the_gr3_archetype(doc):
    from data.car_parameter_model import resolve_parameter_model
    spec = resolve_parameter_model("AMG Mercedes-AMG GT3 '20").spec("springs_front")
    band = re.search(r"Gr\.3 ≈ \*\*([\d.]+)–([\d.]+) Hz\*\*", doc)
    assert band, "the spring band is missing from the script"
    assert float(band.group(1)) == pytest.approx(spec.window_low)
    assert float(band.group(2)) == pytest.approx(spec.window_high)


def test_the_ride_height_band_is_the_one_the_golden_test_asserts(doc):
    """The script and the automated golden test must not disagree about what sane is."""
    assert "50–80 mm" in doc or "50-80 mm" in doc


def test_the_clean_lap_expectation_matches_the_evidence_floor(doc):
    from data.session_db import MIN_EVIDENCE_CLEAN_LAPS
    assert f"{MIN_EVIDENCE_CLEAN_LAPS + 1} clean laps" in doc or \
        f"at least **{MIN_EVIDENCE_CLEAN_LAPS + 1} clean laps**" in doc


# ---------------------------------------------------------------------------
# Honesty about its own scope
# ---------------------------------------------------------------------------
def test_it_states_that_offline_evidence_cannot_certify(doc):
    """The register's central finding: 11,000 passing tests coexisted with basics being
    broken, because the suite exercised modules the live path never called."""
    # Normalise wrapping — the assertion is about the claim, not the line breaks.
    flat = " ".join(doc.lower().split())
    assert "not tested" in flat
    assert "no automated evidence" in flat or "can never promote" in flat


def test_every_step_starts_as_not_tested(doc):
    """A pre-ticked checklist is not a checklist."""
    assert "☑ NOT TESTED" not in doc
    assert doc.count("☐ NOT TESTED") > 40


def test_the_known_gaps_are_declared(doc):
    """A certification that hides what it does not cover is worse than none."""
    for gap in ("B11", "B12", "E3", "Gr.2"):
        assert gap in doc, f"the known-gaps section never mentions {gap}"


def test_it_covers_all_four_reported_symptoms(doc):
    for symptom in ("symptom 1", "symptom 2", "symptom 3", "symptom 4"):
        assert symptom in doc


def test_it_has_a_defect_register_and_a_run_record(doc):
    assert "## 8. Defect register" in doc
    assert "## 9. Run record" in doc


def test_the_must_not_happen_checks_are_unticked(doc):
    section = doc.split("## 7. Must NOT happen")[1].split("## 8.")[0]
    # The sentence "Any ☑ here is a FAIL" is the instruction, not a ticked box; only
    # the table rows are checked.
    rows = [l for l in section.splitlines() if l.strip().startswith("| 7.")]
    assert rows, "the must-not-happen table is empty"
    assert not any("☑" in r for r in rows), "a regression check is pre-ticked"
    assert len(rows) >= 10


# ---------------------------------------------------------------------------
# The superseded scripts say so
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", _SUPERSEDED)
def test_the_old_scripts_are_marked_superseded(name):
    """They mis-navigate from step 1.1. Leaving them unmarked is how someone runs one."""
    text = (_ROOT / name).read_text(encoding="utf-8")
    head = text[:1200]
    assert "SUPERSEDED" in head
    assert "DO NOT RUN" in head
    assert "UAT_2026-08-07_REMEDIATION_CERTIFICATION" in head


@pytest.mark.parametrize("name", _SUPERSEDED)
def test_the_supersession_says_why(name):
    text = (_ROOT / name).read_text(encoding="utf-8")[:1200]
    assert "tab" in text.lower(), "the reason (tab navigation) is not stated"


# ---------------------------------------------------------------------------
# E3's other half — the project docs that also describe a UI that is gone
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["PROJECT_STATE.md", "REQUIREMENTS.md"])
def test_the_stale_project_docs_carry_an_accuracy_note(name):
    """They describe the classic tab layout the driver no longer sees. Rewriting either
    wholesale is out of proportion to the value; leaving them unmarked is how someone
    acts on stale content, which is exactly how the UAT scripts rotted."""
    head = (_ROOT / name).read_text(encoding="utf-8")[:1600]
    assert "ACCURACY NOTE" in head
    assert "no tab bar" in head
    assert "UAT_2026-08-07" in head
