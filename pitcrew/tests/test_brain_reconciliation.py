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

import ast
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
# **The house style comes out before anything is matched** (the critic on 2.8
# part 2, pass 10, and it is both of that pass's majors at once). These files
# bold mid-sentence and end sentences with `.**`: **29.6% of the sentence
# ends in e10's own scope are `.**`, `.)` or `."` rather than `. `**, and
# `**front** accel` is how the two `02` §10.5 lines the FWD exclusion exists
# for are actually written. Every pattern here was fragile to that, and a
# guard held up by a formatting choice nobody knows is load-bearing is not a
# guard. Taken out once, here, rather than guessed at in six patterns.
# Underscores are left alone: `lsd_a` is a slider's name.
# **Asterisks only.** Backticks were here too and earned nothing - a mutant
# dropping them changed no outcome, because every pattern already matches
# through a backtick (`` drop `lsd_a` `` matches either way: the backtick is
# inside `[^.|]` and `lsd_a\b` closes on it). Underscores are left in, because
# `lsd_a` is a slider's name.
_MARKUP = re.compile(r"\*+")
_SPACES = re.compile(r"[^\S\n]{2,}")
# A full stop that ends a sentence, through whatever closes the quote or the
# bracket after it. **`]` and `}` included** (pass 11 review): every stamp in
# this corpus closes `]*`, and without them "…LESS rotation on power.]* Lower
# the accel and the push goes" read as one sentence. Rarer than the `.**` form
# that was the major - 16 sentence ends against 13,137 - and one character.
_SENTENCE_END = re.compile(r"\.[)\]}\"'”]*\s")


def _plain(line: str) -> str:
    """The line with the emphasis markup taken out, and its spacing evened.

    For judging text, never for offsets into the original: the length changes.

    **The spacing matters** (pass 11 review): e11 excludes the front axis with
    fixed-width lookbehinds, which one double space defeats - while e10's
    `[\\s-]*` handles it. Evening the spacing once fixes that for every
    pattern instead of teaching each one to count spaces.
    """
    return _SPACES.sub(" ", _MARKUP.sub("", line))


def _axis_name(text: str) -> str:
    """A matched axis as the plain slider name it is.

    `front-accel`, `front's accel` and `front accel` are one axis, and the
    exclusion compares by name - so without this the two hyphenated forms
    walked straight through the guard written to stop them.

    **This one does flatten underscores**, unlike `_plain`: `lsd_a` becomes
    `lsd a` here. Harmless, because the result is only ever compared by
    `startswith` against `_OTHER_AXIS` and `_GENERIC`, neither of which
    contains an underscore - but `_plain`'s note about leaving underscores
    alone is about `_plain`, not about this.
    """
    return re.sub(r"[^a-z0-9]+", " ",
                  re.sub(r"['’]s\b", "", text.lower())).strip()


# **`low` is NOT a lowering word here** (pass 10 review). It was added on the
# guess that e10 might reach "run it LOW" - which e11 does properly - and the
# corpus comparison shows it gained no line at all, while it made "With
# initial torque low, the diff still pushes on turn-in" read as this claim.
# **A mutant putting it back survives**, and that is worth saying rather than
# leaving to be found: the back-reference rule below fixes that sentence on
# its own terms, so `low` is out because it earns nothing, not because
# anything now depends on its absence.
_LESS = (r"(?:lower|reduc\w*|drop\w*|down|decreas\w*|soften\w*|open\w*|freer"
         r"|less|unlock\w*|back\b[^.|]{0,20}?\boff\b)")
# **`\block\b`, not `lock`** (pass 9): "unlocks" is a LOWERING word, and
# reading the "lock" inside it as an axis being lowered was one of the two
# reasons "Braking sensitivity down unlocks the diff and the car turns in
# better" was flagged. **It does not fix that line, and this comment used to
# claim it did**: the scan rejects `braking sensitivity`, then finds
# `down ... diff ... turns` as a fresh claim on the generic word. That false
# positive stands - see `lower_accel_axis`.
_ACCEL = (r"(?:front(?:['’]s)?[\s-]*accel\w*|braking sensitivity"
          r"|initial torque|accel\w*|lsd_a\b|diff\w*|\block\b)")
# The sliders this claim is NOT about. A match on one of these is somebody
# else's axis; `diff` and `lock` name no particular one and settle nothing.
_OTHER_AXIS = ("front accel", "braking sensitivity", "initial torque")
# Words that name no particular slider, and so cannot carry a claim on their
# own once the sentence has already named one.
_GENERIC = ("diff", "lock")
# The whole word, so the matched span carries it: the refutation says "gives
# LESS rotation", and a span ending at "rotat" hid that from the exclusion
# (the critic on 2.8 part 2, pass 7). "turn" and "point" are the same
# symptom in his words (pass 8, minor 1).
_CURE = r"(?:push\w*|understeer\w*|rotat\w*|turn\w*|point\w*)"
# The lowering word and the axis close together, in either order, and the
# thing it is offered to cure. The mechanism wordings count (pass 6): "a
# freer diff frees rotation", "less lock under power", "back the accel off".
def _near(tag: str) -> str:
    """That shape, with the axis CAPTURED rather than looked for afterwards.

    **The axis is read off the match** (the critic on 2.8 part 2, pass 9).
    Scanning the span counted every axis word in it, so a claim was decided
    by whichever slider happened to stand next to the one being lowered:
    "Braking sensitivity down unlocks the diff" was judged on `diff`, and
    "open the diff - braking sensitivity aside - to cure the push" on
    `braking sensitivity`. Both wrong, in opposite directions, and the span
    rule could not tell them apart because it never knew which word the
    lowering verb belonged to.

    Pass 8 wanted precisely this and could not have it: one `(?P<axis>...)`
    used for all three occurrences is `re.PatternError: redefinition of group
    name`. Hence a tag per occurrence - and a tag per copy, because the whole
    shape appears twice in the pattern below.
    """
    return (rf"(?P<n{tag}>"
            rf"{_LESS}\b[^.|]{{0,30}}?(?P<a{tag}>{_ACCEL})"
            rf"|(?P<b{tag}>{_ACCEL})[^.|]{{0,30}}?{_LESS}\b"
            # The axis INSIDE the lowering phrase: "back the accel off",
            # "take accel out of the diff" - neither ordering above can see
            # it, because the phrase swallows the word it is about.
            rf"|back\b[^.|]{{0,20}}?(?P<c{tag}>{_ACCEL})[^.|]{{0,10}}?\boff\b"
            rf"|out of the (?P<d{tag}>diff))")
# The windows carry a clause between the change and the symptom - his
# rationales run long ("soften the accel (leave braking sensitivity high)
# and the understeer goes"), so 200 rather than 120 (pass 8, minor 1).
LOWER_ACCEL_FOR_PUSH = re.compile(
    rf"{_near('1')}[^.|]{{0,200}}?{_CURE}"
    rf"|{_CURE}\w*[^.|]{{0,200}}?{_near('2')}", re.IGNORECASE)
# The refutation's own sentence, in both car-state wordings.
_REFUTATION = re.compile(r"less rotation on power", re.IGNORECASE)
# A claim about the OVERRUN diff - the braking axis - which claims a
# rotation source rather than a cure for a power-on push.
_OVERRUN = re.compile(r"overrun|off-throttle|on the brakes", re.IGNORECASE)
# **"push" and "understeer" are NOT on-power words** (pass 9, minor). They
# are the two commonest symptoms there are, so listing them here killed the
# overrun exemption for every ordinary wording of it: "an open diff on the
# overrun stops the entry understeer" - the braking axis, which §4.1 calls a
# larger rotation source than anything the accel axis does - read as this
# claim and would have been stamped as the refuted one.
_ON_POWER = re.compile(r"on power|on throttle|under throttle|power-on",
                       re.IGNORECASE)
# **Not this claim.** s145 tested the ACCELERATION axis on an MR car and
# found lowering it cost rotation. These are other claims, and stamping them
# would be a false record: the overrun/braking axis, initial torque, a FWD
# front diff, raising it - and the refutation itself, which says the words
# in the opposite order ("less lock, LESS rotation").
def claims_lower_accel(line: str) -> bool:
    """Whether this line offers lowering the ACCELERATION axis as the cure.

    **The axis is the one the lowering word belongs to** - captured by the
    pattern, not looked for in the span afterwards (`_near`, and the critic
    on 2.8 part 2, pass 9). Three passes reached for this and each stopped
    one step short: pass 7 judged the exclusions on the line, pass 8 on the
    span, pass 9 on every axis word inside the span. All three decide a claim
    by words standing NEAR it rather than by what it is about.

    Three things are not this claim, and each is decided on its own terms:
    the matched axis being the braking, initial-torque or front/FWD one; the
    refutation's own sentence ("gives LESS rotation on power", both
    car-state wordings); and a claim about the OVERRUN diff that offers a
    rotation source rather than a cure for a power-on push. The last two are
    judged on the sentence the match sits in - see `_sentence`.

    **"freer differential" is still not excluded** (pass 7, and pass 10
    checked): §4.1's Initial Torque bullet and the live claim say it in the
    same words. Reading the axis off the match rejects that bullet's opening
    clause and then meets the same wording standing on its own, which is how
    the live claim reads. That bullet carries a hand stamp.

    **What it still cannot see, stated rather than half-covered:** a standing
    rule that names no symptom at all ("run acceleration sensitivity LOW and
    prove you need more", `08`:146). This check is shaped "lowered AS THE
    CURE FOR a push"; a rule with no symptom in it satisfies no such shape.
    Those carry hand stamps, and e11 catches the ones whose line names a
    rotation symptom somewhere.
    """
    return lower_accel_axis(line) is not None


def _sentence(line: str, start: int, end: int) -> str:
    """The sentence, or table cell, the match sits in.

    **Bounded by `|` and `. ` - the boundaries the claim pattern itself
    refuses to cross** (the critic on 2.8 part 2, pass 9, MAJOR). Judging the
    wording exemptions on the whole LINE was pass 7's major put straight back
    for one phrase: e10 iterates lines, a markdown row is one line of many
    cells, and a refutation quoted inside a stamp therefore cleared the live
    claim standing beside it. It is not hypothetical - it fails open on
    `07-car-profiles.md`:609, the line pass 6 named as one of the two most
    canonical places, where the claim and the quote refuting it share a row.
    Judging them on the SPAN fails the other way, because the span stops at
    the first symptom word and cuts "less rotation on power" at "rotation".
    The sentence is the unit both exemptions were always about, and it is
    what they are both judged on now - `_OVERRUN` included, which had no
    reason to differ.
    """
    left = 0
    for ends in _SENTENCE_END.finditer(line, 0, start):
        left = ends.end()
    left = max(left, line.rfind("|", 0, start) + 1)
    after = _SENTENCE_END.search(line, end)
    right = after.start() + 1 if after else len(line)
    bar = line.find("|", end)
    return line[left:min(right, bar) if bar != -1 else right]


def lower_accel_axis(line: str) -> str | None:
    """Which axis this line offers lowering as the cure, or `None` for none.

    The axis comes from the matched group, so it is the slider the lowering
    word actually belongs to - see `_near`.
    """
    line = _plain(line)
    named: set[str] = set()
    at = 0
    while (hit := LOWER_ACCEL_FOR_PUSH.search(line, at)) is not None:
        found = {name: text for name, text in hit.groupdict().items() if text}
        axis = _axis_name(next((text for name, text in found.items()
                                if not name.startswith("n")), ""))
        # **Resume just past the rejected AXIS.** `finditer` is
        # non-overlapping and a match runs on to the symptom, so a rejected
        # claim swallowed the live one starting inside it: "with initial
        # torque already low, drop the acceleration sensitivity to cure the
        # push" was thrown out on `initial torque`, and "keep braking
        # sensitivity high and lower accel to free rotation" on `braking
        # sensitivity`. Past the axis and no further, because the lowering
        # word after it belongs to the next claim, not this one - and a
        # lowering word BEFORE it is already out of reach, `search(line, at)`
        # requiring the whole match to start at `at` or later. That is what
        # keeps "FWD: open the front accel diff to stop the exit push"
        # rejected: "open" is behind us, so the bare "diff" has nothing to
        # pair with.
        axis_at = next((name for name, text in found.items()
                        if text and not name.startswith("n")), None)
        at = max(hit.end(axis_at) if axis_at else hit.end(), hit.start() + 1)
        sentence = _sentence(line, hit.start(), hit.end())
        if axis.startswith(_OTHER_AXIS):
            named.add(sentence)
            continue
        # **A generic word after a named axis is a BACK-REFERENCE to it, not
        # a fresh claim** (pass 10 review). "diff" and "lock" name no
        # particular slider, so once a sentence has named one and had it
        # thrown out, the bare word is that same slider being described
        # again: "Braking sensitivity down unlocks the diff and the car turns
        # in better" and "FWD: open the front accel diff to reduce the exit
        # push" both read as this claim on the word "diff" alone. A SPECIFIC
        # axis later in the sentence is a second claim and still counts -
        # "keep braking sensitivity high and lower accel to free rotation".
        # The cost is a sentence that names the other axis first and then
        # makes this claim generically; §4.1's Initial Torque bullet is that
        # shape, and it carries a hand stamp.
        if axis.startswith(_GENERIC) and sentence in named:
            continue
        if _REFUTATION.search(sentence):
            continue
        if _OVERRUN.search(sentence) and not _ON_POWER.search(sentence):
            continue
        return axis or "diff"
    return None


# **Everywhere Ludo reasons from, and the SAME everywhere for every check**
# (pass 10 review): e11 was scanning 18 files fewer than e10, with no reason
# given, and among them the ledger that e10's own comment had just argued in.
# `brain/ledger/` is here because `SKILL.md`'s reference table has `refine`,
# `race plan` and
# `debrief` open it FIRST, so it is as much a source as the dossiers are. **It
# flags nothing today and a mutant removing it survives** - said plainly
# rather than left to be discovered: the five files hold one band and that
# band corrects itself. A door closed on the way in, not a defect caught.
DOCTRINE_SCOPE = (".claude/skills/**/*.md", "brain/_inbox/0*.md",
                  "brain/_inbox/1[0-7]-*.md", "brain/car-state/*.md",
                  "brain/ledger/*.md")


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
    scope = DOCTRINE_SCOPE
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
                  "`lsd_a` down gives LESS rotation on power on this car",
                  # **The overrun claim in its ordinary wording** (pass 9,
                  # minor). "push" and "understeer" used to count as on-power
                  # words, so the exemption died for every sentence that used
                  # the two commonest symptoms there are - and this is the
                  # braking axis, which §4.1 calls a larger rotation source
                  # than anything the acceleration axis does.
                  "an open diff on the overrun stops the entry understeer",
                  "a freer diff on the brakes will kill the entry push",
                  # **Excluded by the axis itself**, and nothing asserted
                  # that until now: every other exclusion above is decided by
                  # the refutation or the overrun rule, so the axis rule -
                  # the whole of what passes 8, 9 and 10 were arguing about -
                  # could be deleted with every probe still green.
                  "lower the braking sensitivity to cure the entry push",
                  "drop the initial torque and the mid-corner push goes",
                  # The FWD front diff: the critic's pass-9 false positive,
                  # which the span rule flagged on the word "diff" standing
                  # beside the axis actually being opened.
                  "FWD: open the front accel diff to stop the exit push",
                  # **The three spellings this corpus actually uses** (pass 10
                  # review): the exclusion wanted the literal string
                  # "front ", so the bold form - which is how `02` §10.5's
                  # own AWD and FWD lines are written - walked through the
                  # guard added to stop it.
                  "FWD: open the **front** accel diff to cure the exit push",
                  "AWD: lower the front's accel sensitivity to kill the "
                  "exit understeer",
                  "FWD: open the front-accel diff to stop the exit push",
                  # And with a second lowering verb, which is what the old
                  # "'open' is behind us" reasoning did not survive.
                  "FWD: open the front accel diff to reduce the exit push",
                  # The back-reference: one named axis, then the generic word.
                  "Braking sensitivity down unlocks the diff and the car "
                  "turns in better",
                  # **Both claims in the SECOND sentence of a two-sentence
                  # line.** The only shape that can tell `named.add(sentence)`
                  # from `named.add(line)`: with the line stored and the
                  # sentence looked up the two never match, so the rule goes
                  # inert rather than line-scoped, and on a single-sentence
                  # line the two are identical. Every other probe here is one
                  # sentence, or expects a flag, so none of them could see it.
                  "Entry is fine on this car. Lower the braking sensitivity "
                  "and open the diff and the push goes away"):
        assert not claims_lower_accel(other), other
    # **The refutation quoted beside the claim it refutes** (the critic on
    # 2.8 part 2, pass 9, MAJOR): this is `07-car-profiles.md`:609's shape,
    # and judging the exemption on the LINE cleared the live claim standing
    # in front of the quote. Strip that line's stamps and e10 saw nothing at
    # all - on the file pass 6 was written to protect.
    assert claims_lower_accel(
        "the setting that makes it rotate is also the setting that makes the "
        "tyres last, because less acceleration lock means less rear scrub. "
        "The rotation half is disputed: on this car LESS acceleration lock "
        "gives LESS rotation on power")
    # **The same line, ended the way this corpus ends its sentences** (pass 10
    # review). `.**` closes 29.6% of the sentence ends in e10's own scope and
    # appears 173 times in `07-car-profiles.md` alone; a splitter that cannot
    # see it degrades silently back to the line, which IS the defect.
    assert claims_lower_accel(
        "the setting that makes it rotate is also the setting that makes the "
        "tyres last, because less acceleration lock means less rear scrub.** "
        "The rotation half is disputed: on this car LESS acceleration lock "
        "gives LESS rotation on power")
    # The overrun exemption leaked across the same boundary: an overrun
    # sentence clearing a live claim in the one after it.
    assert claims_lower_accel(
        "An open diff on the overrun is the bigger rotation source.** Lower "
        "the accel and the mid-corner push goes")
    # **The cell boundary, which is the other half of the same rule**: a
    # table row is one line, so a refutation quoted in a neighbouring cell
    # must not clear the claim standing in this one.
    assert claims_lower_accel(
        "| less accel lock cures the push | on this car LESS acceleration "
        "lock gives LESS rotation on power |")
    # **And the boundary on the other side of the claim**, which the probe
    # above cannot reach: the refutation in the cell BEFORE this one.
    assert claims_lower_accel(
        "| on this car LESS acceleration lock gives LESS rotation on power "
        "| less accel lock cures the push |")
    # A quoted sentence end. `_plain` takes out emphasis, so `.**` is already
    # a plain full stop by the time the splitter sees it - but a quote is not
    # emphasis and stays, which is what the splitter's own pattern is for.
    assert claims_lower_accel(
        'The bigger rotation source is an open diff on the overrun." Lower '
        'the accel and the mid-corner push goes')
    # **The back-reference rule is held to the SENTENCE** (pass 11 review):
    # `named.add(line)` in place of `named.add(sentence)` failed no test, and
    # it would let a rejected axis in one sentence - or one table cell - clear
    # a live claim in the next, which is the fail-open shape this row has
    # fought since pass 7.
    assert claims_lower_accel(
        "Lower the braking sensitivity for entry. Now open the diff and the "
        "mid-corner push goes away")
    assert claims_lower_accel(
        "| Lower the braking sensitivity for entry | open the diff and the "
        "mid-corner push goes away |")
    # **The stamp's own closing bracket.** Every stamp in this corpus ends
    # `]*`, and without `]` in the splitter the refutation quoted inside one
    # sits in the same sentence as the claim after it.
    assert claims_lower_accel(
        "[CONTESTED: on this car LESS acceleration lock gives LESS rotation "
        "on power.]* Lower the accel and the mid-corner push goes")
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
    #
    # **The back-reference rule settles it** (pass 10 review). This sentence
    # names Initial Torque, so the bare "differential" after it is that same
    # slider being described again, not a second claim. Pass 7's hand stamp
    # stays - the assertion below still reads the file for it - but the check
    # no longer rests on it. The same wording with NO other axis named is
    # still this claim and still flags, which is the line after this one.
    assert not claims_lower_accel(
        "Initial Torque decrease → freer differential, more rotation")
    assert claims_lower_accel("a freer differential gives more rotation")
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
                 "a freer differential on power will cure the mid-corner push",
                 # **The window itself** (pass 9, minor): 200 was taken on
                 # trust, and the wording the change was justified with fits
                 # inside 120. This one does not - 160 characters of clause
                 # between the change and the symptom, which is how a
                 # rationale that pauses to say what it is NOT touching
                 # actually reads.
                 "open the diff a click on corner exit, leaving braking "
                 "sensitivity exactly where it is because that is set for "
                 "the entry phase and we have not tested it here, and the "
                 "mid-corner push goes away"):
        assert claims_lower_accel(both), both


# A standing instruction to run the axis low, with no symptom in it.
# **The ACCELERATION axis only.** `_ACCEL` is the claim-shape vocabulary and
# takes in every neighbouring slider on purpose; here the axis IS the
# question, and a line-level check on the loose one flagged four lines that
# are about somebody else's slider entirely - braking sensitivity at
# `02`:477, initial torque at `02`:888, the AWD front diff at `02`:914.
# The front forms are excluded in each spelling this corpus uses, because a
# lookbehind must be a fixed width and so cannot be written once (pass 10
# review: `**front** accel` normalises to `front accel`, but `front-accel`
# and `front's accel` are still their own spellings).
_ACCEL_ONLY = (r"(?:(?<!front )(?<!front-)(?<!ront's )(?<!ront’s )"
               r"accel\w*|lsd_a\b)")
# One alternative, not two: a `run|keep|set ... low` arm was here and was
# dead, because the axis-then-low arm already matches every wording of it
# ("Run acceleration sensitivity LOW", "keep accel sensitivity low"). A
# mutant deleting it changed no outcome, which is how it was found.
_RUN_LOW = re.compile(
    rf"{_ACCEL_ONLY}[^.|]{{0,40}}?\b(?:low|lower)\b", re.IGNORECASE)
# **Narrower than `_CURE`** (pass 10 review). e11 asks only whether a symptom
# is somewhere on the line, with no proximity bound at all - so `turn\w*` and
# `point\w*`, which are fine inside e10's 200-character window, turned "out
# of every turn" and "Turn 4 is the reference corner" into evidence of the
# refuted claim. The traction levers are meant to be out of reach BECAUSE
# they name no rotation symptom; with `turn` in the set they were out of
# reach only by an accident of how they happen to be worded.
# **"turn in" is his word and stays; a bare "turn" is a place** (pass 11
# review). Narrowing this to the rotation family lost "the car will not turn
# in", which is exactly how he reports it - while `turn\w*` had made "out of
# every turn" and "Turn 4 is the reference corner" into evidence of the
# refuted claim. The distinction is the phrase, not the distance: e11 has no
# proximity bound to tighten.
# **A leading `\b` too.** Without it the phrase matches inside "return in"
# and "returns in" - two live in the corpus today, neither on a line that also
# carries the instruction, so it flagged nothing wrongly and would have
# eventually demanded a CONTESTED stamp for a line naming no symptom at all.
_ROTATION = re.compile(r"push\w*|understeer\w*|rotat\w*|\bturns?[-\s]in\b",
                       re.IGNORECASE)


def _standing_rule_unstamped(line: str) -> bool:
    """A "run the accel axis low" rule, with a rotation symptom, unstamped.

    **One expression, used by the corpus check and by the probes** (pass 11
    review): `_ROTATION` was pinned as a pattern while e11's call site could
    revert to `_CURE` with no test failing, which is the whole of what keeps
    the traction levers out of reach.
    """
    said = _plain(line)
    return bool(_RUN_LOW.search(said) and _ROTATION.search(said)
                and not any(mark in line for mark in ("CONTESTED", "§10.5")))


def test_e11_a_standing_rule_to_run_accel_low_carries_the_contest():
    """**The check e10 is not shaped to make** (the critic on 2.8 part 2,
    pass 9, MAJOR 3).

    e10 asks whether lowering the acceleration axis is offered as the CURE
    for a push. A standing rule names no symptom - `08`'s A5 heading, "Run
    acceleration sensitivity LOW", and its "Rule for you: run acceleration
    sensitivity LOW and prove you need more" - so no cure-shaped check can
    see it, and both sat unstamped while every worded claim around them
    carried a pointer. The heading is what a reader scans, and A5 is what
    Ludo opens when asked about a push on throttle: the call it produced,
    *"accel sensitivity down two clicks"*, is the step the axis register
    records as REFUTED and `02` §10.5 prices at 2.30 s of lap time.

    **Only where a rotation symptom is somewhere on the line.** `05`'s
    circuit levers tell him to run the axis low for TRACTION - "more lock
    produces more wheelspin, not more drive" - which is a different claim
    and was not refuted. Stamping those CONTESTED would be the false record
    this file exists to prevent, so they are deliberately out of reach.
    """
    bare = []
    for pattern in DOCTRINE_SCOPE:
        for path in sorted(ROOT.glob(pattern)):
            for number, line in enumerate(
                    path.read_text(encoding="utf-8").splitlines(), 1):
                if _standing_rule_unstamped(line):
                    bare.append(f"{path.relative_to(ROOT).as_posix()}:{number}")
    assert not bare, f"'run accel low' with a push on the line, uncontested, at {bare}"


def test_e11_sees_the_standing_rule_and_not_the_traction_one():
    for rule in ("Run acceleration sensitivity LOW.",
                 "Rule for you: run acceleration sensitivity LOW and prove "
                 "you need more",
                 "keep accel sensitivity low on this car",
                 "acceleration sensitivity: LOW, 12-20"):
        assert _RUN_LOW.search(rule), rule
    # The traction wording is the SAME instruction and a different claim, so
    # e11 leans on the symptom, not on the instruction.
    traction = ("**LSD acceleration sensitivity: LOW, 12-20.** More lock "
                "produces more wheelspin, not more drive.")
    assert _RUN_LOW.search(traction)
    assert not re.search(_CURE, traction, re.IGNORECASE), traction
    # And the rotation wording, which is the refuted one.
    rotation = ("A heavily locked diff breaks away as a unit - and it also "
                "pushes. Run acceleration sensitivity LOW.")
    assert _RUN_LOW.search(rotation) and _ROTATION.search(rotation)
    # **Somebody else's axis, in this corpus's spellings** (pass 10 review):
    # the front/FWD diff is not this claim, and `**front**` is how `02`
    # §10.5's own lines are written.
    for front in ("FWD: front-accel sensitivity low will not cure the push",
                  "FWD: keep the front's accel sensitivity low for the push",
                  "FWD: **front** accel sensitivity low for the exit push",
                  # A double space, which the fixed-width lookbehinds cannot
                  # see and `_plain`'s evened spacing hands them anyway.
                  "FWD: keep the front  accel sensitivity low for the push"):
        assert not _RUN_LOW.search(_plain(front)), front
    # **"turn" and "point" are not symptoms for THIS check** - it has no
    # proximity bound, so they made a reference corner into evidence.
    assert not _ROTATION.search(
        "Keep accel sensitivity low here; Turn 4 is the reference corner")
    # **Through the one expression the corpus check uses**, so the call site
    # is pinned and not only the patterns it is built from.
    assert _standing_rule_unstamped(rotation)
    assert not _standing_rule_unstamped(traction)
    assert not _standing_rule_unstamped(
        "LSD acceleration sensitivity: LOW, 12-18 - more lock produces "
        "wheelspin out of every turn")
    assert not _standing_rule_unstamped(
        "Keep accel sensitivity low here; Turn 4 is the reference corner")
    # **His own word for it**, which the narrowing had lost.
    assert _standing_rule_unstamped(
        "Run acceleration sensitivity LOW or the car will not turn in")
    # **"return in" is not "turn in".** The leak was a common English word,
    # not a circuit name - `Turn 4`, "out of every turn" and "the turn-in
    # point at T4" all behaved, while "the losses return in the last stint"
    # made a line with no rotation symptom at all look like this claim.
    assert not _standing_rule_unstamped(
        "Rule: run acceleration sensitivity LOW; the losses return in the "
        "last stint")
    assert not _ROTATION.search("the wheel returns in a controlled way")
    # A stamp clears it, which is the whole point of the check.
    assert not _standing_rule_unstamped(
        "Run acceleration sensitivity LOW, and it pushes. [CONTESTED on v1.71]")


def _terminates(statement) -> bool:
    """Does this statement end its scope outright?

    **The guard's body must END in one** (row 2.10 pass 6 review), not merely
    contain one somewhere. Walking the whole `If` for any `return` or `raise`
    blessed four shapes that all leave the tool writing without the flag: a
    terminator behind a further condition, one inside a nested `def` that is
    never called, one caught and swallowed by a `try`, and - worst - one in
    the guard's own `else:`, which returns when `--apply` IS set and falls
    through to the write when it is not. An inverted guard reading as a guard.

    Checked against every negated guard on disk: seven of the eight end in
    `return`, and the eighth never relied on this rule - its writes sit inside
    `if args.apply:` and are caught by the positive shape.
    """
    if isinstance(statement, (ast.Return, ast.Raise)):
        return True
    # **A block terminates when every way out of it does** (pass 7 review).
    # Without this, `try: return 0 finally: print(...)` was reported as an
    # unguarded write - correct code, and the message said something untrue
    # about the tool. Loops are deliberately left out: a `for` over a possibly
    # empty iterable cannot be shown to terminate.
    if isinstance(statement, ast.Try):
        return (bool(statement.body) and _terminates(statement.body[-1])
                and all(handler.body and _terminates(handler.body[-1])
                        for handler in statement.handlers))
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        return bool(statement.body) and _terminates(statement.body[-1])
    if isinstance(statement, ast.If):
        return (bool(statement.body) and _terminates(statement.body[-1])
                and bool(statement.orelse) and _terminates(statement.orelse[-1]))
    # **The dotted form only.** A local `def exit(message): print(message)`
    # called as the guard's last statement is not a terminator, and matching
    # on the last segment of the name accepted it.
    return (isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Call)
            and _render(statement.value.func) in ("sys.exit", "os._exit",
                                                  "os.abort"))


def _apply_guard_problems(path) -> dict[str, str]:
    """Writes in an `--apply` tool that are not reached only under the flag.

    **Reachability, not "the scope mentions the flag"** (row 2.10 pass 5
    review). Asking whether the enclosing function contained ANY apply-branch
    was wrong in both directions: `if args.apply: print("applying")` blessed
    every write after it, and moving a write into a helper called only from
    under the guard turned the suite red while naming a tool that was
    behaving correctly - the same misdirection as the docstring defect, one
    layer along.

    **Two shapes, because the eleven are split.** Eight bail early -
    `if not args.apply: return` - where the write is a SIBLING after a
    terminating guard rather than a descendant of one, so ancestry alone
    cannot see it. Three write inside `if args.apply:`, where ancestry is
    exactly right. **And a helper is guarded when every one of its call sites
    is**, which needs the call graph and not the tree.
    """
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    handles = _store_handles(tree)
    # **Imported writers only, not the module's own functions.** A call to a
    # local function is not a write site here: its writes are recorded in its
    # own scope and carried by the call graph below. Counting the call too
    # made every tool's `main()` a write at module level, under the
    # `if __name__` line, where no flag can reach.
    known = _imported_writers(tree)
    writes: list[tuple[str, str, bool]] = []
    calls: list[tuple[str, str, bool]] = []
    compound = (ast.For, ast.AsyncFor, ast.While, ast.With, ast.AsyncWith,
                ast.Try)

    def about_the_flag(test) -> tuple[bool, bool]:
        said = ast.unparse(test)
        if "apply" not in said or re.search(r"\b(?:True|False)\b", said):
            return False, False
        return True, bool(re.match(r"\s*not\b", said))

    def scan(node, guarded: bool, scope: str) -> None:
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            if (why := _writes_in(sub, handles, known)):
                writes.append((scope, why, guarded))
            if (name := _render(sub.func).split(".")[-1]):
                calls.append((scope, name, guarded))

    def visit(body, guarded: bool, scope: str) -> None:
        for statement in body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                visit(statement.body, False, statement.name)
            elif isinstance(statement, ast.ClassDef):
                visit(statement.body, guarded, scope)
            elif isinstance(statement, ast.If):
                scan(statement.test, guarded, scope)
                mentions, negated = about_the_flag(statement.test)
                visit(statement.body, guarded or (mentions and not negated),
                      scope)
                visit(statement.orelse, guarded or (mentions and negated),
                      scope)
                if (mentions and negated and statement.body
                        and _terminates(statement.body[-1])):
                    guarded = True          # everything after it is covered
            elif isinstance(statement, compound):
                for field in ("test", "iter", "items"):
                    part = getattr(statement, field, None)
                    for piece in (part if isinstance(part, list) else [part]):
                        if isinstance(piece, ast.AST):
                            scan(piece, guarded, scope)
                for field in ("body", "orelse", "finalbody"):
                    block = getattr(statement, field, None)
                    if isinstance(block, list):
                        visit(block, guarded, scope)
                for handler in getattr(statement, "handlers", []) or []:
                    visit(handler.body, guarded, scope)
            else:
                scan(statement, guarded, scope)

    visit(tree.body, False, "")
    functions = {node.name for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    sites: dict[str, list[tuple[str, bool]]] = {}
    for scope, callee, guarded in calls:
        if callee in functions:
            sites.setdefault(callee, []).append((scope, guarded))
    # A function is reached only under the flag when every call of it is -
    # to a fixpoint, because a helper may call a helper.
    always = dict.fromkeys(functions, False)
    moved = True
    while moved:
        moved = False
        for name in functions:
            here = sites.get(name, [])
            covered = bool(here) and all(guarded or always.get(caller, False)
                                         for caller, guarded in here)
            if covered != always[name]:
                always[name] = covered
                moved = True
    return {scope: why for scope, why, guarded in writes
            if not guarded and not always.get(scope, False)}


_MECHANIC = ".claude/skills/ludo/references/mechanic.md"
# A tool's own LINE - the path, a dash, and something after it. **Not merely
# its name somewhere in the file** (the critic on row 2.10): the old check was
# satisfied by any backticked identifier, so a `tools/fit.py` or a
# `tools/judge.py` would have passed undocumented on the strength of `fit` and
# `judge` being callables named in a different list.
# **At column zero**, so a bullet indented under something else, or sitting
# inside a fence, is not a tool's listing (row 2.10, pass 2 review).
_INSTRUMENT_LINE = re.compile(r"^- `tools/(\w+)\.py[^`]*`\s*[—-]\s*\S",
                              re.MULTILINE)
_MCP_LINE = re.compile(r"^- `(\w+)` \(MCP\)\s*[—-]\s*\S", re.MULTILINE)
_BACKTICKED = re.compile(r"`([A-Za-z_]\w*)`")
# The three passages the section turns on. Each was deletable, or could be
# paraphrased into its opposite, with every assertion green.
_WRITERS_RULE = re.compile(
    r"\*\*Writers\b[^*]*?each changes the database[^*]*?"
    r"never as a step of a diagnosis\.\*\*", re.DOTALL)
_APPLY_RULE = re.compile(
    r"leaves the DATABASE alone without `--apply`[^.]*?not the\s+disk",
    re.DOTALL)
# **The corner refusal**, which is the finding here that reaches the driver.
# Pinned by what it must keep saying, not by a substring: it was deletable,
# and "nine of nine" could be changed to "three of nine", untested.
_CORNER_REFUSAL = re.compile(
    r"⛔[^⛔]*?corner_models[^⛔]*?auto-segment[^⛔]*?"
    r"build_track_map\.py --apply[^⛔]*?never a step in a diagnosis",
    re.DOTALL)


def _mechanic() -> tuple[str, str]:
    """The instrument list and the exclusion block, as separate text.

    **Read apart, because reading the whole file cannot tell an instrument
    from a tool that is explicitly not one** (row 2.10 review): a mutant
    moving `debrief` from one list to the other left every assertion green.

    Fenced blocks and HTML comments come out first - a line that reads like a
    bullet inside one is an example or a note, not a listing, and both passed
    as a tool's line.
    """
    text = (ROOT / _MECHANIC).read_text(encoding="utf-8")
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    marks, at = [], 0
    for mark in ("## Every instrument, one line each",
                 "**Not instruments for this skill**"):
        assert mark in text[at:], f"mechanic.md no longer has: {mark}"
        at = text.index(mark, at)
        marks.append(at)
    end = text.find("\n---", marks[1])
    assert end != -1, "the exclusion block runs to the end of the file"
    return text[marks[0]:marks[1]], text[marks[1]:end]


# **One verb set, shared by the tool check and the MCP check** (row 2.10 pass
# 3 review): the MCP side knew three of these, so a call whose only write was
# `store.set_teammate(...)` read as a reader - and `Store.set_driver_name`,
# `set_lap_flags`, `set_lap_wear` and `approve_strategy` are all real writes.
_WRITE_VERB = re.compile(
    r"^(?:save|record|link|note|update|create|delete|set|write|approve)_"
    r"|^_write$")
_DML = re.compile(r"INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM",
                  re.IGNORECASE)


def _render(node) -> str:
    """The dotted name a node spells - `store`, `self.store`, `a.b.c`."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{base}.{node.attr}" if (base := _render(node.value)) else ""
    return ""


def _without_docstrings(text: str, tree) -> str:
    """The source with its docstrings removed.

    Every check below reads prose otherwise, so a docstring quoting a SQL
    statement or naming another method reclassifies its own function as a
    writer - and then everything that calls it. Defined here because two of
    them run at import.
    """
    for node in ast.walk(tree):
        if (isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef))
                and node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            text = text.replace(node.body[0].value.value, "")
    return text


def _store_handles(tree) -> set[str]:
    """Every expression in this module that holds a `Store`.

    **Bare names were all the first version bound** (row 2.10 pass 3 review),
    which lost `self.store = Store()` - a regression on the regex it replaced
    - and with it `with Store() as db`, the walrus, and a tuple target. A
    parameter called `store` or annotated `Store` counts, and so does a local
    factory returning one, which is how `server.py`'s own `_store()` is
    followed.

    **Seeded with `"store"`**, so a handle this cannot trace still counts.
    That is a naming convention standing in for a binding, deliberately, and
    it errs towards calling something a writer.
    """
    factories = {node.name for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and any(isinstance(step, ast.Return)
                         and isinstance(step.value, ast.Call)
                         and _render(step.value.func).split(".")[-1] == "Store"
                         for step in ast.walk(node))}

    def binds(value) -> bool:
        if not isinstance(value, ast.Call):
            return False
        spelled = _render(value.func)
        return spelled.split(".")[-1] == "Store" or spelled in factories

    handles = {"store"}

    def keep(target) -> None:
        for leaf in (target.elts if isinstance(target, (ast.Tuple, ast.List))
                     else [target]):
            if (spelled := _render(leaf)):
                handles.add(spelled)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and binds(node.value):
            for target in node.targets:
                keep(target)
        elif isinstance(node, ast.Assign):
            # `db, _ = Store(), None` - the VALUE is a tuple, not a call, so
            # the test above never fires. Paired element-wise instead.
            for target in node.targets:
                if (isinstance(target, (ast.Tuple, ast.List))
                        and isinstance(node.value, (ast.Tuple, ast.List))):
                    for leaf, value in zip(target.elts, node.value.elts):
                        if binds(value):
                            keep(leaf)
        elif (isinstance(node, (ast.AnnAssign, ast.NamedExpr))
                and binds(node.value)):
            keep(node.target)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None and binds(item.context_expr):
                    keep(item.optional_vars)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in (*node.args.posonlyargs, *node.args.args,
                        *node.args.kwonlyargs):
                named = (_render(arg.annotation).split(".")[-1]
                         if arg.annotation is not None else "")
                if arg.arg == "store" or named == "Store":
                    handles.add(arg.arg)
    return handles


def _store_write_methods() -> set[str]:
    """The `Store` methods that change the database, read off `store/db.py`.

    **Keyed on the METHOD, not the receiver** (row 2.10 pass 4). A `Store`
    handed into a function under any other name - `def main(handle)` - binds
    to nothing this file can see, and `handle.save_strategy(...)` was
    invisible however far the binding rules were widened. The method names
    are knowable and they are distinctive: no argument parser or serial port
    has a `save_strategy`.
    """
    tree = ast.parse((ROOT / "pitcrew/store/db.py").read_text(encoding="utf-8"))
    store = next((node for node in ast.walk(tree)
                  if isinstance(node, ast.ClassDef) and node.name == "Store"),
                 None)
    if store is None:                      # pragma: no cover - the class moved
        return set()
    # **Docstrings out first** (row 2.10 pass 4 review). Both tests below read
    # the unparsed body, so ONE SENTENCE in a reader's docstring naming
    # `self.save_race_knowledge(` put that reader into this set - and the
    # any-receiver rule then flagged the fourteen tools that call it, with a
    # failure message pointing at `mechanic.md`, which had not changed. A
    # guard that fails loudly at the wrong file is how this programme spent
    # months calling a product defect an environment fault.
    bodies = {}
    for node in store.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            source = ast.unparse(node)
            bodies[node.name] = _without_docstrings(source, ast.parse(source))
    writers: set[str] = set()
    moved = True
    while moved:
        moved = False
        for name, body in bodies.items():
            if name in writers:
                continue
            if (_DML.search(body) or "self._write(" in body
                    or any(f"self.{other}(" in body for other in writers)):
                writers.add(name)
                moved = True
    return writers


_STORE_METHODS = _store_write_methods()


def _writes_in(node, handles: set[str], writers: set[str]) -> str:
    """Why this subtree writes the database, or ""."""
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        if (isinstance(call.func, ast.Attribute)
                and call.func.attr in _STORE_METHODS):
            return f"{call.func.attr}(), a Store write"
        if (isinstance(call.func, ast.Attribute)
                and _render(call.func.value) in handles
                and _WRITE_VERB.search(call.func.attr)):
            return f"{_render(call.func.value)}.{call.func.attr}()"
        spelled = _render(call.func)
        if spelled and spelled.split(".")[-1] in writers:
            # **A call that switches the write off is not a write.**
            # `build_inputs` saves the measured track clock by default, and
            # the two doors documented as read-only pass `remember=False` -
            # which this cannot see from the name alone. Only an explicit
            # literal counts; a variable could be anything.
            declared = _MODULE_WRITERS.get(spelled.split(".")[-1],
                                           {}).get("params", set())
            if "remember" in declared and any(
                    keyword.arg == "remember"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is False
                    for keyword in call.keywords):
                continue
            return f"{spelled}()"
    return ""


def _module_writers() -> dict[str, set[str]]:
    """Module-level callables in `pitcrew/` that write, and where they live.

    **Derived, not listed** (row 2.10 pass 4 review). Naming
    `carry_into_knowledge` closed one instance and left `resolve_corner_model`,
    `handover.accept` and `rival_book.record` open - each of which a tool could
    reasonably call, and `resolve_corner_model` is the canonical way to get a
    corner model at all.

    **Keyed by module, because the names are ordinary.** `record` and `accept`
    are words a tool may well use for something of its own, so a caller only
    counts when it has imported the name from the module that defines it.
    """
    found: dict[str, dict] = {}
    for path in sorted((ROOT / "pitcrew").rglob("*.py")):
        if "tests" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:                    # pragma: no cover
            continue
        handles = _store_handles(tree)
        dotted = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        # **The whole tree, not `tree.body`** (pass 5 review): a writer
        # defined inside a `try:`, or as a method on an ordinary class, was
        # invisible - and a class method that writes is a perfectly normal way
        # for one of these modules to grow.
        # Which class owns each WRITING method, so one imported through its
        # class can be followed. **Resolved per node, not by name** (pass 7
        # review): a dict keyed on the bare method name recorded whichever
        # class was walked last, so two classes with a method of the same name
        # both hid the writer and accused the reader - one line producing a
        # false negative and a false positive at once.
        parent = {child: node for node in ast.walk(tree)
                  for child in ast.iter_child_nodes(node)}

        def owning_class(node) -> str | None:
            step = parent.get(node)
            while step is not None:
                if isinstance(step, ast.ClassDef):
                    return step.name
                step = parent.get(step)
            return None
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            source = ast.unparse(node)
            plain = _without_docstrings(source, ast.parse(source))
            if _DML.search(plain) or _writes_in(node, handles, set()):
                entry = found.setdefault(node.name, {"modules": set(),
                                                     "params": set(),
                                                     "owners": set()})
                entry["modules"].add(dotted)
                if (owner := owning_class(node)) is not None:
                    entry["owners"].add(owner)
                # **What the callee actually declares** (pass 5 review): the
                # `remember=False` exemption was honoured on spelling alone,
                # so a call could silence the check with a keyword the callee
                # has never heard of.
                entry["params"] |= {arg.arg for arg in
                                    (*node.args.posonlyargs, *node.args.args,
                                     *node.args.kwonlyargs)}
    return found


_MODULE_WRITERS = _module_writers()


def _imported_writers(tree) -> set[str]:
    """Which of those a module has actually imported, under whatever name."""
    names: set[str] = set()

    def from_module(dotted: str) -> None:
        for writer, entry in _MODULE_WRITERS.items():
            if dotted in entry["modules"]:
                names.add(writer)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
                "pitcrew"):
            for alias in node.names:
                homes = _MODULE_WRITERS.get(alias.name, {}).get("modules", set())
                if node.module in homes:
                    names.add(alias.asname or alias.name)
                # **A writer reached through the class that owns it** (pass 6
                # review): `from X import Filer`, then `Filer.file_it(...)`.
                # The derivation saw the method; the lookup did not.
                for writer, entry in _MODULE_WRITERS.items():
                    if (node.module in entry["modules"]
                            and alias.name in entry.get("owners", set())):
                        names.add(writer)
                from_module(f"{node.module}.{alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("pitcrew"):
                    from_module(alias.name)
    return names


def _writing_functions(tree, handles: set[str]) -> set[str]:
    """Which functions in this module write, directly or through each other.

    To a fixpoint, because a helper may call a helper. **The first version
    split the server on `@mcp.tool()` and threw the module head away** - which
    is where helpers live - so a tool whose whole body was `_persist(plan)`
    read as a reader, and a helper sitting BETWEEN two tools made the check
    fail while naming the innocent tool before it.
    """
    writers = _imported_writers(tree)
    functions = [node for node in ast.walk(tree)
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    moved = True
    while moved:
        moved = False
        for function in functions:
            if function.name in writers:
                continue
            if _writes_in(function, handles, writers):
                writers.add(function.name)
                moved = True
    return writers


def _writes_the_database(path) -> str:
    """Why this tool is a writer, or "" - by structure, not by name.

    A regex cannot tell `store.set_lap_flags(...)` from
    `parser.set_defaults(...)` or a serial port's `_write(...)`, and reads
    `write_text` and `write_wav` as database writes. Raw DML counts wherever
    it appears, which is how `build_track_map`, `repair_dropped_laps` and
    `stamp_game_versions` are caught - none of them calls a store method.
    """
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    if (dml := _DML.search(_without_docstrings(text, tree))):
        return f"raw DML: {dml.group(0)}"
    handles = _store_handles(tree)
    return _writes_in(tree, handles, _writing_functions(tree, handles))


def test_e12_every_tool_is_named_or_excluded_by_the_mechanic():
    """Plan row 2.10: name every tool the skill may use, one line each.

    `mechanic.md` does, in two lists - the instruments, and the ones that
    belong to the app's own health, voice, rig and build. **Nothing kept it
    that way.** Ten tools existed and were re-derived by hand because nothing
    named them, which is the finding the row comes from, and a tool added
    without a line puts the file back into that state silently: a name that
    is missing reads exactly like a tool that was never written.

    **Both directions**, because the file has failed both ways. A tool with
    no line is work done twice; a line for a tool that no longer exists sends
    the skill to run something that is not there, which is the stale-citation
    defect row 2.8 had to clear by hand.
    """
    instruments, excluded_block = _mechanic()
    rule = _WRITERS_RULE.search(instruments)
    assert rule, "the writers' standing rule is gone, or no longer says it"
    readers, writers = instruments[:rule.start()], instruments[rule.end():]
    assert _APPLY_RULE.search(instruments), "the --apply sentence is gone"
    assert _CORNER_REFUSAL.search(instruments), (
        "the corner refusal is gone, or no longer refuses - it is the one "
        "thing in this file that stops a tool making refusals.md false")

    tools = {path.stem for path in (ROOT / "tools").glob("*.py")}
    lined = set(_INSTRUMENT_LINE.findall(instruments))
    excluded = set(_BACKTICKED.findall(excluded_block))

    assert not lined & excluded, f"both an instrument and not: {lined & excluded}"
    assert not tools - (lined | excluded), (
        f"tools with no line and no exclusion: {sorted(tools - (lined | excluded))}")
    assert not lined - tools, (
        f"instrument lines for tools that do not exist: {sorted(lined - tools)}")
    assert not excluded - tools, (
        f"excluded names that are not tools: {sorted(excluded - tools)}")

    # **A tool that writes belongs under the writers' rule**, not in a bare
    # exclusion list where the rule cannot reach it.
    writing = {path.stem: why
               for path in sorted((ROOT / "tools").glob("*.py"))
               if (why := _writes_the_database(path))}
    under_the_rule = set(_INSTRUMENT_LINE.findall(writers))
    astray = {name: why for name, why in writing.items()
              if name not in under_the_rule}
    assert not astray, f"tools that write and are not with the writers: {astray}"

    # **The MCP surface, and which SIDE of the rule each call is on** (row
    # 2.10 pass 2). Naming them was not enough: all seven writers could be
    # relabelled read-only with the suite green - the roster check this row
    # had just replaced for `tools/`, left standing on the higher-stakes half,
    # where one of the writes is the shift table that beeps in his ear.
    server = ast.parse(
        (ROOT / "pitcrew/mcp/server.py").read_text(encoding="utf-8"))
    handles = _store_handles(server)
    helpers = _writing_functions(server, handles)
    lined_mcp = set(_MCP_LINE.findall(instruments))
    for node in ast.walk(server):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(_render(mark).endswith("mcp.tool")
                   or (isinstance(mark, ast.Call)
                       and _render(mark.func).endswith("mcp.tool"))
                   for mark in node.decorator_list):
            continue
        assert node.name in lined_mcp, (
            f"MCP tool with no line of its own: {node.name}")
        why = _writes_in(node, handles, helpers - {node.name})
        side, verdict = (writers, why) if why else (readers, "only reads")
        assert f"`{node.name}` (MCP)" in side, (
            f"`{node.name}` is on the wrong side of the writers' rule: "
            f"{verdict}")

    # **Pin the property, not the prose** (row 2.10 pass 3 review, and it is
    # the review's own diagnosis): `_WRITERS_RULE`, `_APPLY_RULE` and
    # `_CORNER_REFUSAL` each assert that a word sequence is PRESENT, and a
    # word sequence cannot be true or false. That is why a contradiction
    # placed beside the sentence and a rewrite around it both got through -
    # the refusal was re-hosted in prose that inverted every clause while
    # keeping every anchor phrase, in order.
    # **Driven from the TOOLS, not from the line** (pass 4 review): the loop
    # read ` --apply` out of the very document it polices, so editing the line
    # skipped the check entirely and the tool could then drop the flag. And
    # two substring tests are a word sequence again - `if False and not
    # args.apply:` satisfied both while writing unconditionally.
    unguarded = {}
    for tool in sorted((ROOT / "tools").glob("*.py")):
        source = tool.read_text(encoding="utf-8", errors="replace")
        if '"--apply"' not in source and "'--apply'" not in source:
            continue
        for scope, why in _apply_guard_problems(tool).items():
            unguarded[f"{tool.stem}:{scope or 'module level'}"] = why
    assert not unguarded, (
        f"tools that take `--apply` and write where the flag does not reach: "
        f"{unguarded}")

    # **The corner refusal's own claim, asserted against the code - and it
    # retires itself.** This fails the day `build_track_map` writes `source`,
    # which is exactly the day the refusal stops being true and the block has
    # to be rewritten. No pattern over the prose can do that.
    mapper = (ROOT / "tools/build_track_map.py").read_text(encoding="utf-8")
    # **Every such statement, not the first** (pass 4 review): the fix the
    # driver has authorised may land as a second UPDATE rather than as a
    # column added to this one, and a `search` would not see it - so the
    # refusal would not be forced into rewriting, which is the whole point.
    updates = list(re.finditer(r"UPDATE\s+corner_models\s+SET\s+(.*?)\s+WHERE",
                               mapper, re.IGNORECASE | re.DOTALL))
    assert updates, "build_track_map no longer updates corner_models"
    columns = {part.split("=")[0].strip().strip("\"'`")
               for update in updates for part in update.group(1).split(",")}
    # **The gate opened on 12 Sep and this assertion turned over with it.**
    # It used to say `source` must NOT be among the columns - true while the
    # tool wrote `corners_json` alone, and written to fail on the day that
    # changed, because that is the day the refusal stopped being true. It did,
    # the block was rewritten in the same commit, and the check now holds the
    # tool to the declaration instead.
    # **Both directions, and ONE assertion, so neither latches.** Eval 17 told
    # Ludo the tool "cannot honestly be run at all" because it never wrote
    # `source` - true when written, false two commits later, so a Ludo
    # answering CORRECTLY failed its own eval. The first fix for that was an
    # unconditional deny-list sitting under an eager `assert "source" in
    # columns`, which is rule 10's defect with the working example three lines
    # above it: in the direction the guard exists for - the code losing the
    # declaration again - the assert above fired first and the eval's
    # staleness was never reached, and there was no green state in which the
    # tool lacked `source` and an eval truthfully said so. Collected and
    # asserted once, it turns over the way the `source` check itself did.
    declares = "source" in columns
    evals = (ROOT / ".claude/skills/ludo/evals/evals.json").read_text(
        encoding="utf-8")
    problems = []
    if not declares:
        problems.append(
            "build_track_map no longer writes corner_models.source - a "
            "world-anchored model would export as `auto-segment`, which is "
            "the one declaration CLAUDE.md 3.2 requires it to make")
    for dead in ("never `corner_models.source`", "cannot honestly be run"):
        if declares and dead in evals:
            problems.append(
                f"an eval still asserts a defect the code has fixed: {dead!r}")
    # **No arm requires an eval to DOCUMENT the defect.** The obvious
    # symmetry - "the tool stopped declaring and no eval says so" - would
    # make a broken tool green as soon as an eval described it, and would
    # oblige the evals to carry a defect's obituary. Losing the declaration
    # is a fault in its own right (§3.2), so it is reported whatever the
    # evals say; what the evals may not do is contradict a tool that is
    # behaving. The two are reported together rather than one short-
    # circuiting the other, which is the part that was wrong.
    assert not problems, problems

    # **A backstop, and only that.** A deny-list cannot referee contradiction
    # in general - but absolution is the one class of edit that has now been
    # observed twice: a sentence appended beside the `--apply` rule saying
    # none of it matters, and a rewrite of the corner refusal saying the
    # caution has lapsed and running the writer first is routine. Both kept
    # every anchor phrase, in order. These strings are here because those
    # edits happened, not because the list is a principle.
    for absolution in ("run them freely", "safe to run unattended",
                       "none of this matters", "no longer applies",
                       "caution has lapsed", "may use freely",
                       "is now routine", "without asking"):
        assert absolution not in instruments.lower(), (
            f"the instrument list absolves its own rules: {absolution!r}")

    # **A tool the skill sends itself to is an instrument**, whatever else it
    # is - so one cannot be quietly reclassified out of the safety rules.
    for page in sorted((ROOT / ".claude/skills/ludo").rglob("*.md")):
        text = page.read_text(encoding="utf-8")
        if page.name == "mechanic.md":
            text = text.replace(excluded_block, "")
        for cited in set(re.findall(r"tools/(\w+)\.py", text)):
            assert cited not in excluded, (
                f"{page.name} sends the skill to `{cited}`, which "
                f"mechanic.md lists as not an instrument")


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
