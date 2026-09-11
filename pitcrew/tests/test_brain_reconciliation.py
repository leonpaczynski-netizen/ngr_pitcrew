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


_PCT = r"\d+(?:\.\d+)?\s?(?:[–-]\s?\d+(?:\.\d+)?\s?)?%"
# Every form the rule took (pass 3: the number before the word, "take X %
# off", and the number-less "overstates race burn ... on every circuit").
DISCOUNT_RULE = re.compile(
    rf"discount\b[^.]{{0,40}}?{_PCT}"
    rf"|{_PCT}[^.]{{0,20}}?discount"
    rf"|\b(?:take|knock|shave|cut)\b[^.]{{0,15}}?{_PCT}\s?off\b[^.]{{0,25}}?practice"
    rf"|race burn runs\b[^.]{{0,15}}?{_PCT}\s?(?:under|below)\b[^.]{{0,10}}?practice"
    r"|overstates race burn\b[^.]{0,60}?(?:every circuit|always|\d)",
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


def test_e9_sees_every_form_of_the_discount():
    """The critic's pass-3 probes, and the observation that is NOT a rule."""
    for said in ("race burn at the measured 3-9% practice discount",
                 "race burn runs 3-9 % under practice",
                 "take 5 % off the practice burn", "knock 9% off practice burn",
                 "Practice burn overstates race burn on this car, on every "
                 "circuit, in the same direction",
                 "discount practice burn 3-9 % for the race"):
        assert DISCOUNT_RULE.search(said), said
    assert not DISCOUNT_RULE.search(
        "Practice burn ran above race burn at Road Atlanta (−3.5 %) and Red "
        "Bull Ring (−9.2 %)")


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


def test_e8_no_live_lsd_band_anywhere_is_left_on_the_old_scale():
    """Critic on 2.8 part 2, pass 4: `02` §11 step 5 still gave "accel
    15-25, brake 10-20" unflagged - e8 read only `05`. Every live doctrine
    line giving an LSD band or step carries its version, a scale flag, or
    the v1.71 reading itself."""
    # Where Ludo reasons from: the skills, the knowledge base (00-10) and the
    # car-state files. Left out, each for a reason: `11`, `16` and `17` exist
    # to state the v1.71 ranges; the dated setup sheets are v1.70 history
    # under `setups/00-PRE-1.71-NOTICE.md`; RECONCILIATION is a log.
    scope = (".claude/skills/**/*.md", "brain/_inbox/0*.md",
             "brain/_inbox/10-*.md", "brain/car-state/*.md")
    # A band shortly after the diff is named - a table cell away counts, so
    # a car-state row comparing a value against a v1.70 band is seen. The
    # slider keys too: `\bLSD\b` cannot match `lsd_a` (the underscore is a
    # word character), and that is how the Mount Panorama row was written.
    # A slider's own name counts, with no "LSD" on the line: §4.1 defines
    # them one per heading, and its "Initial Torque (5-60)" kept the v1.70
    # range while the sibling above it was stamped (pass 6).
    near = re.compile(
        r"(?:\bLSD\b|\blsd_[iab]\b|acceleration lock|initial torque"
        r"|braking sensitivity|acceleration sensitivity"
        r"|\baccel(?:eration)?\b[^.|]{0,20}\bsensitivity)[^\n]{0,120}?"
        r"(?<![\d.])\d{1,2}\s?[–-]\s?\d{1,2}(?![\d.])",
        re.IGNORECASE)
    # Pass 5: the band before the word ("20-28 accel"), and value forms - a
    # triple after the diff, or "initial torque 5, acceleration 25". A triple
    # in a car-state file is that car's setting, where §1a puts it.
    before = re.compile(r"(?<![\d.])\d{1,2}\s?[–-]\s?\d{1,2}(?![\d.])\s?"
                        r"(?:\w+\s){0,1}accel", re.IGNORECASE)
    values = re.compile(
        r"(?:\bLSD\b|\blsd\b)[^\n]{0,60}?(?<![\d.])\d{1,2}\s?/\s?\d{1,2}\s?/"
        r"\s?\d{1,2}(?![\d.])|initial torque \d+, acceleration \d+",
        re.IGNORECASE)
    stamped = ("v1.70", "5–60 scale", "v1.71 reads", "on v1.71",
               "range_records", "0–30 / 0–100")
    bare = []
    for pattern in scope:
        for path in sorted(ROOT.glob(pattern)):
            text = path.read_text(encoding="utf-8")
            kb = "car-state" not in path.as_posix()
            for number, line in enumerate(text.splitlines(), 1):
                hit = (near.search(line) or before.search(line)
                       or (kb and values.search(line)))
                if hit and not any(s in line for s in stamped):
                    bare.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
    assert not bare, f"LSD bands with no version or scale flag at {bare}"


# "Lower the accel" offered as the cure for a push, understeer or lost
# rotation - the claim the v1.71 Huracán test refuted (s145). Arrow forms
# ("18 → 14") are pinned by hand; these are the worded ones.
_LESS = (r"(?:lower|reduc\w*|drop\w*|down|decreas\w*|soften\w*|open\w*|freer"
         r"|less|unlock\w*|back\b[^.|]{0,20}?\boff\b)")
_ACCEL = (r"(?:front accel\w*|braking sensitivity|initial torque"
          r"|accel\w*|lsd_a\b|diff\w*|lock)")
# **Which axes the match actually names** (the critic on 2.8 part 2, pass
# 8). Scanning the span for a disqualifying token cleared any live claim
# that named a second slider while making it - "lower the accel AND the
# initial torque, and the push goes away". Longest alternative first, so
# "front accel" and "braking sensitivity" win over the bare words.
_AXIS_WORD = re.compile(
    r"front accel\w*|braking sensitivity|initial torque"
    r"|accel\w*|lsd_a\b|diff\w*|lock", re.IGNORECASE)
_OTHER_AXIS = ("front accel", "braking sensitivity", "initial torque")
# The whole word, so the matched span carries it: the refutation says "gives
# LESS rotation", and a span ending at "rotat" hid that from the exclusion
# (the critic on 2.8 part 2, pass 7). "turn" and "point" are the same
# symptom in his words (pass 8, minor 1).
_CURE = r"(?:push\w*|understeer\w*|rotat\w*|turn\w*|point\w*)"
# The lowering word and the axis close together, in either order, and the
# thing it is offered to cure. The mechanism wordings count (pass 6): "a
# freer diff frees rotation", "less lock under power", "back the accel off".
_NEAR = (rf"(?:{_LESS}\b[^.|]{{0,30}}?{_ACCEL}"
         rf"|{_ACCEL}[^.|]{{0,30}}?{_LESS}\b"
         # The axis INSIDE the lowering phrase: "back the accel off",
         # "take accel out of the diff" - neither ordering above can see it,
         # because the phrase swallows the word it is about.
         rf"|back\b[^.|]{{0,20}}?{_ACCEL}[^.|]{{0,10}}?\boff\b"
         rf"|out of the diff)")
# The windows carry a clause between the change and the symptom - his
# rationales run long ("soften the accel (leave braking sensitivity high)
# and the understeer goes"), so 200 rather than 120 (pass 8, minor 1).
LOWER_ACCEL_FOR_PUSH = re.compile(
    rf"{_NEAR}[^.|]{{0,200}}?{_CURE}|{_CURE}\w*[^.|]{{0,200}}?{_NEAR}",
    re.IGNORECASE)
# The refutation's own sentence, in both car-state wordings.
_REFUTATION = re.compile(r"less rotation on power", re.IGNORECASE)
# A claim about the OVERRUN diff - the braking axis - which claims a
# rotation source rather than a cure for a power-on push.
_OVERRUN = re.compile(r"overrun|off-throttle|on the brakes", re.IGNORECASE)
_ON_POWER = re.compile(r"on power|on throttle|under throttle|power-on"
                       r"|push|understeer", re.IGNORECASE)
# **Not this claim.** s145 tested the ACCELERATION axis on an MR car and
# found lowering it cost rotation. These are other claims, and stamping them
# would be a false record: the overrun/braking axis, initial torque, a FWD
# front diff, raising it - and the refutation itself, which says the words
# in the opposite order ("less lock, LESS rotation").
def claims_lower_accel(line: str) -> bool:
    """Whether this line offers lowering the ACCELERATION axis as the cure.

    **Judged on the axis that matched, not on words near it** (the critic on
    2.8 part 2, pass 8, MAJOR). Scanning the span for a disqualifying token
    cleared the claim whenever a real rationale named a second slider while
    making it - "lower the accel AND the initial torque, and the push goes
    away". Pass 7's span rule only moved that failure inside the match.

    Three things are not this claim, and each is decided on its own terms:
    the matched axis being the braking, initial-torque or front/FWD one; the
    refutation's own sentence ("gives LESS rotation on power", both
    car-state wordings); and a claim about the OVERRUN diff that offers a
    rotation source rather than a cure for a power-on push.

    **"freer differential" is not excluded** (pass 7): §4.1's Initial Torque
    bullet and the live claim say it in the same words, so no pattern can
    tell them apart. That bullet carries a hand stamp instead.
    """
    for hit in LOWER_ACCEL_FOR_PUSH.finditer(line):
        span = hit.group(0)
        axes = [word.group(0).lower()
                for word in _AXIS_WORD.finditer(span)]
        # Every axis it names is somebody else's: not this claim. One
        # generic axis among them and it is.
        if axes and all(axis.startswith(_OTHER_AXIS) for axis in axes):
            continue
        # **Against the whole line, not the span** (pass 8): the span ends at
        # the first symptom word, so "gives LESS rotation on power" is cut at
        # "rotation" and the refutation reads as the claim - pass 7's
        # mid-word trap one step along. It is a statement about the
        # sentence, so the sentence is what it is judged on.
        if _REFUTATION.search(line):
            continue
        if _OVERRUN.search(span) and not _ON_POWER.search(span):
            continue
        return True
    return False


def test_e10_lower_accel_for_a_push_always_says_it_is_contested():
    """Critic on 2.8 part 2, passes 4 and 5: each pass pointed four more
    places at "lower the accel" as the cure for a power-on push, after the
    v1.71 Huracán test refuted lowering it (s145). Every such line, anywhere
    Ludo reasons from, carries the pointer, the word, or its v1.70 stamp.

    **Two limits, stamped by hand instead.** A bullet that takes its axis
    from the heading above it names nothing a line-level check can read -
    §4.1's "Decrease -> more rotation on throttle" under Acceleration
    Sensitivity, and its "freer differential" sibling under Initial Torque.
    And the arrow forms ("18 -> 14", "25->20") carry no lowering word at all.
    So `02`:440, `08`:530, `01` §11, `01`:163 and `08`:274 are pointed by
    hand, and `NOT_THIS_CLAIM` keeps the other axes out.
    """
    scope = (".claude/skills/**/*.md", "brain/_inbox/0*.md",
             "brain/_inbox/1[0-7]-*.md", "brain/car-state/*.md")
    marked = ("CONTESTED", "§10.5", "v1.70")
    bare = []
    for pattern in scope:
        for path in sorted(ROOT.glob(pattern)):
            text = path.read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), 1):
                if claims_lower_accel(line) \
                        and not any(m in line for m in marked):
                    bare.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
    assert not bare, f"'lower accel for a push' with no pointer at {bare}"


def test_e10_sees_the_claim_and_not_its_neighbours():
    for said in ("if it pushes on throttle, bring accel down from 25",
                 "Reduce accel LSD slightly to free rotation",
                 "LSD accel down → frees rotation under power",
                 "Power-on mid-corner understeer, resolved by dropping LSD "
                 "accel from 18 to 14",
                 # Pass 6's list - the mechanism, not the instruction.
                 "decrease acceleration sensitivity for more rotation",
                 "open the diff on power and it will rotate",
                 "a freer diff frees rotation",
                 "less lock under power will bring the rotation back",
                 "back the accel off and the push goes",
                 "soften acceleration sensitivity to cure the understeer",
                 "take accel out of the diff, it will rotate"):
        assert LOWER_ACCEL_FOR_PUSH.search(said), said
    # A different claim: lower accel for the two-wheel snap or for wear.
    assert not LOWER_ACCEL_FOR_PUSH.search(
        "Car snaps suddenly on power | Lower acceleration sensitivity")
    # And the claims that are somebody else's axis, or the refutation itself.
    for other in ("an open diff on the overrun is a larger rotation source",
                  "an open diff on the overrun would be a larger rotation "
                  "source than anything in A4 or C1",
                  "FWD: raise front accel sensitivity for exit understeer",
                  "On this car LESS acceleration lock gives LESS rotation "
                  "on power",
                  "`lsd_a` down gives LESS rotation on power on this car"):
        assert not claims_lower_accel(other), other
    # **The second axis INSIDE the claim** (pass 8): a rationale names one
    # while making the other, and that must not clear it.
    for both in ("lower the accel and the initial torque, and the push goes away",
                 "less lock on the overrun and on power the push goes away",
                 "open the diff - braking sensitivity aside - to cure the push",
                 "drop accel, not initial torque, to fix the push",
                 "accel down, initial torque unchanged, cures the mid-corner push",
                 "less accel lock gives less rotation on entry but more on "
                 "power, so lower it for the push",
                 "soften the accel (leave braking sensitivity high) and the "
                 "understeer goes",
                 "unlike the FWD case, lower accel here for the push",
                 "open the diff and it will turn better"):
        assert claims_lower_accel(both), both
    # **"Freer differential" is the live claim's own wording**, so §4.1's
    # Initial Torque bullet cannot be told from it by pattern - it carries a
    # hand stamp instead, and the check is left free to flag the wording.
    assert claims_lower_accel(
        "Initial Torque decrease → freer differential, more rotation")
    bullet = [line for line in (ROOT / "brain/_inbox/02-gt7-setup-parameters.md")
              .read_text(encoding="utf-8").splitlines()
              if "freer differential, more rotation" in line]
    assert bullet and all("v1.70" in line for line in bullet), bullet
    # **A second axis in the same sentence does not clear the claim** (pass
    # 7): the exclusion is judged on the span that matched, not the line.
    for both in ("with initial torque already low, drop the acceleration "
                 "sensitivity to cure the push",
                 "keep braking sensitivity high and lower accel to free rotation",
                 "leave it on the overrun; on power, less accel lock gives "
                 "more rotation",
                 "on an FWD car raise front accel, but on this MR car lower "
                 "accel for the push",
                 "initial torque stays, accel comes down, and the push goes away",
                 "a freer differential on power will cure the mid-corner push"):
        assert claims_lower_accel(both), both


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
