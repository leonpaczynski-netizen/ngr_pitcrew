"""Keep the knowledge base and the code from drifting apart silently.

`brain/RECONCILIATION.md` records where the two records of this system agreed
and disagreed on 21 Aug 2026. Six defects the knowledge base still listed as
open were already closed in the code, and one mechanism the knowledge base
believed had been disproved by the telemetry four days earlier. **Neither
record knew, because nothing checked.**

So this file is the check. Each test encodes one claim from that reconciliation
as an executable assertion, and **a failure here is not necessarily a bug** —
it means the code moved and `brain/RECONCILIATION.md` is now out of date. The
failure message says which section to amend.

Two directions, both loud:

* Section A claims are things the code **does** do. If one breaks, the app has
  regressed to a state the knowledge base already describes as a defect.
* Section B claims are things the code **does not yet** do. If one breaks, the
  defect has been fixed and the knowledge base should stop warning about it.

**A test that asserts a defect still exists is deliberate.** The alternative is
that a fix lands, nobody updates the knowledge base, and a document keeps
telling a race engineer to work around something that no longer happens.
"""
from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

from pitcrew.analysis import gearing, thresholds
from pitcrew.export import build, payload
from pitcrew.store import schema

AMEND = "brain/RECONCILIATION.md"


# --------------------------------------------------------------- section A
# Closed in the code. The knowledge base still lists them as open.

def test_a1_drivetrain_is_used_not_merely_stored():
    """`15` §3: "tell Pit Crew this car is MR - outstanding since 14 Aug"."""
    assert thresholds.wheelspin_wheels("MR") == ("rl", "rr"), (
        f"drivetrain no longer narrows the wheelspin test. {AMEND} §A1 says it "
        f"does; if that is deliberate, amend it.")
    assert thresholds.wheelspin_wheels(None) == thresholds.ALL_WHEELS
    # And the catalogue answers when nobody has declared, with its source.
    assert "from the car catalogue" in thresholds.wheelspin_wheels_note(
        "MR", "catalogue")
    assert "declared" in thresholds.wheelspin_wheels_note("MR", "declared")


def test_a2_gearing_constant_prefers_the_sheets_final_drive():
    """`15` §5.1: computed with the derived final gear, not the sheet's.

    The reported 1126.4 against a correct 1092.5 - 3% out, on the number that
    drives gearbox changes.
    """
    source = inspect.getsource(gearing.gearing_constant)
    assert "sheet_final_gear or derived_final_gear" in source, (
        f"gearingConstantK no longer prefers the sheet's final drive. "
        f"{AMEND} §A2 says it does.")


def test_a3_the_calls_ledger_has_more_than_a_boolean():
    """`15` §5.2: `accepted` false on all 14 calls, including "Green, green"."""
    source = inspect.getsource(payload)
    assert '"disposition"' in source, (
        f"the calls ledger lost its disposition field and is a boolean again. "
        f"{AMEND} §A3 says it has one. An informational call cannot be "
        f"'declined'.")


def test_a4_the_packets_wheelbase_is_stored():
    """`15` §2: understeer judged every car against the RSR's 2.516 m."""
    columns = dict(schema.ADDED_COLUMNS["sessions"])
    assert "wheelbase_m" in columns, (
        f"sessions.wheelbase_m is gone. {AMEND} §A4 says the packet's own "
        f"wheelbase is stored; without it every car is judged against "
        f"{thresholds.DEFAULT_WHEELBASE_M} m again.")
    # The fallback may exist, but it must never be silent about being one.
    assumed = thresholds.as_export(wheelbase_m=None)
    assert "assumed" in assumed["understeerWheelbaseSource"].lower()
    measured = thresholds.as_export(wheelbase_m=2.62)
    assert measured["understeerWheelbaseM"] == 2.62


def test_a6_the_export_refuses_a_payload_with_no_game_version():
    """`17` §8 and Standing Rule 10: "gameVersion is missing from the packet".

    It is required, and has been since contract 1.4. What was missing was
    anything *filling* it - a different defect, fixed 21 Aug.
    """
    source = inspect.getsource(payload)
    assert "meta.gameVersion is required" in source, (
        f"the export no longer refuses a versionless payload. {AMEND} §A6 "
        f"says it does, and Standing Rule 10 depends on it.")


def test_d2_an_event_that_straddles_a_patch_still_refuses():
    """`RECONCILIATION.md` §D2. Event 1 spans the 20 Aug patch."""
    def run(sid, when, version):
        return {"id": sid, "started_at": when, "game_version": version,
                "packet_format": "C", "setup_sheet_id": None,
                "practice_intent": None, "practice_mode": None,
                "car_category": "GR3", "fuel_capacity_l": 100.0,
                "identity_status": "ok"}
    try:
        build._merged_session([run(1, "2026-08-19T10:00:00", "1.70"),
                               run(2, "2026-08-21T10:00:00", "1.71")])
    except ValueError:
        return
    raise AssertionError(
        f"an event spanning two GT7 versions exported as one body of evidence. "
        f"{AMEND} §D2 says it refuses.")


# --------------------------------------------------------------- section B
# Open in the code. The knowledge base is right to warn about them.
#
# **These assert that a defect is still present.** When one starts failing the
# news is good: delete the test and strike the row from section B.

def test_b2_the_bottoming_flag_still_has_no_mean_heave_figure():
    """`15` §1 fix 2: report mean heave across the four wheels.

    Roll cancels in the mean and contact does not, which is the cheapest way to
    tell them apart. The polarity error underneath it is fixed (§C1); this
    improvement is not.
    """
    exported = thresholds.as_export()
    assert not any("heave" in str(k).lower() for k in exported), (
        f"a mean-heave figure has appeared in the thresholds block. That closes "
        f"{AMEND} §B2 - delete this test and strike the row.")


# --------------------------------------------------------------- section E
# Doctrine hygiene (plan row 2.8, 11 Sep 2026). What the knowledge base tells a
# race engineer to use must exist, and a rule that has been retired must say
# so where it is written - or the next reader acts on it.

ROOT = Path(__file__).resolve().parents[2]
# Every skill, not only Ludo's: `gt7-brain` loads on every setup question
# and still carried the retired LSD rule after `ludo` had lost it (critic 5).
LIVE_DOCTRINE = (".claude/skills/**/*.md", "brain/_inbox/**/*.md",
                 "brain/car-state/*.md", "brain/RECONCILIATION.md")
# Word-bounded, so "unresolved" is not a retirement; and "met" only as a
# gate met, so "not met" is not one either (critic 5, pass 3).
GONE = re.compile(r"\b(?:removed|deleted|retired|superseded|resolved)\b|"
                  r"\bgate (?:is )?met\b|no longer applies", re.IGNORECASE)
# A table row or a list item is its own block: one retired row must not
# clear every other row of the table it sits in (critic 5, pass 3).
_ITEM = re.compile(r"^\s*(?:\||[-*] |\d+\. )")


def _live_lines():
    for pattern in LIVE_DOCTRINE:
        for path in sorted(ROOT.glob(pattern)):
            text = path.read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), 1):
                yield path, number, line


def _live_paragraphs():
    """Blank-line-separated blocks, whitespace folded - a rule and the note
    that retires it are often a wrapped line apart."""
    for pattern in LIVE_DOCTRINE:
        for path in sorted(ROOT.glob(pattern)):
            block, start = [], None
            lines = path.read_text(encoding="utf-8").splitlines() + [""]
            for number, line in enumerate(lines, 1):
                if line.strip() and block and _ITEM.match(line):
                    # A new row or item closes the one before it; a wrapped
                    # continuation line (no marker) stays with its item.
                    yield path, start, re.sub(r"\s+", " ", " ".join(block))
                    block = []
                if line.strip():
                    if not block:
                        start = number
                    block.append(line)
                elif block:
                    yield path, start, re.sub(r"\s+", " ", " ".join(block))
                    block = []


def test_e1_no_live_doctrine_cites_a_tool_that_is_gone():
    """L16: `log_setup_change.py`, `check_setup_sheets.py` and
    `read_setup_document.py` were cited as working tools after they were
    deleted with the setup record. A citation may stay as history - on a line
    that says the tool is gone."""
    tools = {p.stem for p in (ROOT / "tools").glob("*.py")}
    stale = []
    for path, number, line in _live_lines():
        named = re.findall(r"tools/(\w+)\.py", line) + re.findall(
            r"(?<![\w/])(check_setup_sheets|log_setup_change|read_setup_document)\.py",
            line)
        for name in named:
            if name not in tools and not GONE.search(line):
                stale.append(f"{path.relative_to(ROOT).as_posix()}:{number} {name}.py")
        # And the classes §1a removed with the setup record (critic 5: `13`
        # still called `SetupSheet.gears` "verified end to end").
        if "SetupSheet" in line and not GONE.search(line):
            stale.append(f"{path.relative_to(ROOT).as_posix()}:{number} SetupSheet")
    assert not stale, f"cited as if it still exists: {stale}"


def test_e2_no_live_rule_still_issues_the_lsd_in_absolutes():
    """Retired 11 Sep 2026: all four cars read on v1.71 carry the same three
    LSD scales in `range_records` (0-30 / 0-100 / 0-100)."""
    # The phrasings the rule was actually written in - including the two
    # car-state sheets' "ABSOLUTES, not percentages" header, which the first
    # version of this test did not match and so passed without checking the
    # places sheets are issued from (critic 5 on row 2.8).
    # Every phrasing a sweep of every skill and brain file found the rule
    # written in (11 Sep 2026) - after two passes in which each fix covered
    # only the wordings its critic had named. Read by paragraph, because the
    # retirement note is often the next wrapped line.
    phrasings = ("except the lsd, in absolutes", "issue lsd in absolute values only",
                 "absolutes, not percentages", "register has not been re-read",
                 "lsd in absolutes", "stated in absolutes",
                 "(absolutes — the three axes", "until the register is re-read",
                 "is unverified in full")
    live = [f"{p.relative_to(ROOT).as_posix()}:{n}" for p, n, block in _live_paragraphs()
            if any(words in block.lower() for words in phrasings)
            and not GONE.search(block)]
    assert not live, f"the LSD-absolutes rule is still live at {live}"


def test_e3_the_paste_block_is_retired_with_its_parser():
    """§1a: the app takes no setup. A doctrine that tells Ludo to paste a
    sheet into it describes an input that goes nowhere."""
    assert not (ROOT / "pitcrew" / "setup" / "parse.py").exists()
    sheet = (ROOT / "brain/_inbox/09-setup-sheet-format.md").read_text(encoding="utf-8")
    assert "RETIRED 5 Sep 2026" in sheet
    mechanic = (ROOT / ".claude/skills/ludo/references/mechanic.md").read_text(
        encoding="utf-8")
    assert "SetupSheet.validate()" not in mechanic
    assert "The parser reads" not in mechanic


def test_e4_the_shift_table_example_names_a_table_the_app_would_find():
    """L16: the example issued a table for "Huracán GT3 EVO" at
    "daytona-road-course" - a car not on file and a key the app never builds,
    so a table issued that way beeps nowhere."""
    from pitcrew.controller import circuit_key_for

    skill = (ROOT / ".claude/skills/ludo/SKILL.md").read_text(encoding="utf-8")
    block = skill.split("write_shift_points(", 1)[1].split("```", 1)[0]
    key = re.search(r'circuit_key="([^"]+)"', block).group(1)
    assert key == circuit_key_for({"track": "Daytona International Speedway",
                                   "layout": "Road Course"})
    assert 'car_name="Lamborghini Huracán GT3 \'15"' in block
    assert re.search(r'performance_rpm=\{"1": ', block), "keys arrive as JSON strings"


def test_e5_no_eval_expects_what_was_deleted_and_no_read_car_is_called_stale():
    evals = json.loads((ROOT / ".claude/skills/ludo/evals/evals.json").read_text(
        encoding="utf-8"))["evals"]
    assert not [e["id"] for e in evals if "question gate" in e["expected_output"]]
    register = (ROOT / "brain/_inbox/11-car-slider-ranges.md").read_text(
        encoding="utf-8")
    assert "Stale. Do not issue" not in register


# A claim that stopping early pays, in every wording the doctrine used for it
# - "undercut" or not (critic on 2.8 part 2, B2/M8: "an aggressive early stop
# to get clean air" and "pit first" said the same thing without the word).
UNDERCUT_PAYS = re.compile(
    r"under-?cut(?:ting|s)?\b[^.]{0,100}?\b(?:strong|works?|viable|powerful"
    r"|pays|effective|decisive|worth|the play)\b"
    r"|\bstrong undercut\b|\bpit first\b|\bpit before (?:him|them|the car)\b"
    r"|early stop\b[^.]{0,40}?clean air|\bstop early\b[^.]{0,40}?clean air"
    r"|\bearly stop pays\b|aggressive strategy pays|strongest weapon"
    r"|except where overtaking is (?:near-)?impossible"
    r"|exception: circuits where overtaking", re.IGNORECASE)
# "not re-flagged" is not a flag (critic on 2.8 part 2, pass 2).
FLAGGED = re.compile(r"(?<!not )re-flagged", re.IGNORECASE)


def _sentences(block: str):
    return re.split(r"(?<=[.!?])\s+", block)


def test_e6_every_live_claim_that_the_undercut_pays_is_re_flagged():
    """Row 2.8 part 2: `05` said the undercut was strong at ten circuits, and
    GT7's undercut is weak (`CLAUDE.md` §5.4) - measured in house as a 1.41 s
    fresh-tyre out-lap at Deep Forest. A claim may stay as history, **in a
    sentence that says it is re-flagged** - a flag elsewhere in the paragraph
    cleared every other sentence in it (critic on 2.8 part 2, M8)."""
    live = [f"{p.relative_to(ROOT).as_posix()}:{n}"
            for p, n, block in _live_paragraphs()
            for sentence in _sentences(block)
            if UNDERCUT_PAYS.search(sentence) and not FLAGGED.search(sentence)]
    assert not live, f"the undercut is claimed to pay, unflagged, at {live}"


def test_e6_sees_the_wordings_it_used_to_miss():
    """The critic's list of claims the first regex could not see."""
    for said in ("the undercut pays here", "undercutting works",
                 "undercuts are strong", "a strong undercut",
                 "the undercut is decisive", "pit first",
                 "an aggressive early stop to get clean air is correct",
                 "The overcut beats the undercut - except where overtaking "
                 "is impossible",
                 # Pass 2's list.
                 "stop early for clean air", "an early stop pays",
                 "the undercut is worth two seconds", "the undercut is the play",
                 "pit before him", "the under-cut works",
                 "fresh tyres are the strongest weapon you have"):
        assert UNDERCUT_PAYS.search(said), said
    assert not UNDERCUT_PAYS.search("The undercut is weak in GT7")
    assert not FLAGGED.search("this line was not re-flagged")


DISCOUNT_RULE = re.compile(
    r"discount\b[^.]{0,40}?3\s?[–-]\s?9\s?%|overstates race burn\s?3\s?[–-]\s?9",
    re.IGNORECASE)


def test_e9_no_live_doctrine_discounts_the_practice_burn():
    """Critic on 2.8 part 2, B3 and pass 2: "discount practice burn 3-9 % for
    the race" was a rule from two circuits, and at Deep Forest the last stint
    burned MORE than practice (7.92 against 7.84 L/lap) - the discount would
    have run him about 5 L dry. Fixed in `07` and still live in the Fuji plan
    and the Deep Forest sheet. It may stay as history, re-flagged in its own
    sentence."""
    live = [f"{p.relative_to(ROOT).as_posix()}:{n}"
            for p, n, block in _live_paragraphs()
            for sentence in _sentences(block)
            if DISCOUNT_RULE.search(sentence) and not FLAGGED.search(sentence)]
    assert not live, f"the practice-burn discount is still a rule at {live}"


def test_e8_every_lsd_band_in_the_track_reference_is_flagged():
    """Critic on 2.8 part 2, M1: the banner said every stale line was flagged
    where it stands and not one of the ~38 LSD bands was - Ludo reads the
    per-circuit entries and would issue a v1.70 number on a 0-100 slider."""
    reference = (ROOT / "brain/_inbox/05-track-reference.md").read_text(
        encoding="utf-8")
    # Any band on a line about the diff - "LSD compromise ... 18-25" escaped
    # a match on "LSD acceleration" (pass 2). Exempt only a line that flags
    # the scale or states the v1.71 reading itself, not any line that
    # happens to mention v1.71.
    bare = [n for n, line in enumerate(reference.splitlines(), 1)
            if re.search(r"LSD|acceleration lock", line)
            and re.search(r"\d+[–-]\d+", line)
            and "5–60 scale" not in line and "v1.71 reads" not in line
            and "range_records" not in line]
    assert not bare, f"LSD bands with no scale flag at lines {bare}"


def test_e7_the_register_restates_no_setup_value():
    """§1a: a setup value is written in one place, `brain/car-state/`. `11`
    quoted sheets' diff, rebound, ride height and spring values as absolutes;
    it keeps their percent of range only (row 2.8 part 2)."""
    register = (ROOT / "brain/_inbox/11-car-slider-ranges.md").read_text(
        encoding="utf-8")
    for quoted in ("Rev D runs **LSD", "initial 5 / acceleration 14",
                   "80 / 98 mm", "89 / 107 mm", "3.05 / 3.20 Hz",
                   "40 front / 38 rear", '"+18 mm rake"', '"+8 mm rake"',
                   # **And no position written as a percentage** (the ledger
                   # README; critic on 2.8 part 2, M2): on a 0-100 axis the
                   # percent IS the value, and the rest invert from ranges
                   # printed in the same file.
                   "| `lsd_i` | 2 % |", "Initial torque | 0 % of range",
                   "Rev D's diff sits at", "6 % / 4 % of range",
                   "16.5 % / 14.1 %", "64 % / 63 %", "33 % / 27 %"):
        assert quoted not in register, quoted
    profiles = (ROOT / "brain/_inbox/07-car-profiles.md").read_text(encoding="utf-8")
    assert "3.05 / 3.20 Hz" not in profiles
    for quoted in ("about 64 %", "16.5 % against 14.1 %",
                   "Discount practice burn 3–9 % for the race"):
        assert quoted not in profiles, quoted
    assert "the measured profile, v1.71" in profiles
    reference = (ROOT / "brain/_inbox/02-gt7-setup-parameters.md").read_text(
        encoding="utf-8")
    assert "**Tags (plan row 2.8, 11 Sep 2026).**" in reference
