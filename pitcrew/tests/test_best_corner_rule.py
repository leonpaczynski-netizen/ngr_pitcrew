"""The best-corner amendment of 14 Sep 2026, pinned where it has to stay true.

The driver said yes to plan row 5.B0: a per-lap per-corner instruction stays
refused, and a best corner built from many laps is allowed - but only in the
refusal card's exact form. Two ways this can go wrong, and each has happened to a
rule in this repo before (row 2.8's retired LSD rule survived in four files):

1. **The old blanket refusal survives somewhere a reader scans**, so Ludo is told a
   rule the driver lifted.
2. **The guards fall out of the card**, so a subagent - which sees only the card -
   reads "a best corner is allowed" without "one input at a time" or "never off
   the fastest laps", and builds exactly the outcome-selected recipe nine critic
   passes removed.

Judged per file on the text with emphasis and line wrapping removed, because a
bolded or rewrapped phrase is the same claim (row 2.8 pass 10).
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CLAUDE = "CLAUDE.md"
CARD = ".claude/skills/ludo/references/refusals.md"
BRAIN = ".claude/skills/gt7-brain/SKILL.md"
CHARTER = "docs/RACE-ENGINEER-CHARTER_2026-08-23.md"


def _flat(text: str) -> str:
    """One line, no markdown emphasis, no blockquote markers, single spaces."""
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", text)


def _read(rel: str) -> str:
    return _flat((ROOT / rel).read_text(encoding="utf-8"))


# --- what must stay refused ------------------------------------------------

_PER_LAP = r"per-lap,? per-corner (?:input coaching|instruction)"
_REFUSING = r"(?:⛔|\bNo\b|may not|not say|refused)"


def still_refuses_per_lap(text: str) -> bool:
    """The per-lap phrase with a refusing word inside the same sentence, either
    side - the contract says "... may not ship", the card "No ...", the charter
    "⛔ ..."."""
    return bool(re.search(
        rf"{_REFUSING}[^.]{{0,120}}?{_PER_LAP}|{_PER_LAP}[^.]{{0,40}}?{_REFUSING}",
        text, flags=re.IGNORECASE))


def blanket_refusal_survives(text: str) -> list[str]:
    """Phrasings of the pre-amendment rule that refuse the pooled form too."""
    patterns = [
        # CLAUDE.md header, before: '"brake 10 m later at T4" is not, at any corner'
        r"brake 10 m later at T4\"? is not, at any corner",
        # refusal card gate 1, before: 'labelled, testable, and forbidden.'
        r"labelled, testable, and forbidden\.",
        # refusal card gate 4, before: 'Never propose: per-corner input coaching'
        r"Never propose: per-corner input coaching",
        # gt7-brain, before: 'cannot be said honestly at any corner on any circuit on file.'
        r"cannot be said honestly at any corner on any circuit on file\.",
    ]
    return [p for p in patterns if re.search(p, text)]


# --- what the card must carry beside the permission ------------------------

CARD_GUARDS = {
    "one input at a time": r"one input at a time",
    "held on both sides": r"held on both the input and the result",
    "never off the best laps": r"never read off the laps with the best result",
    "credit only with matched laps": r"credited alone only when enough matched laps",
    "multiplicity": r"corrected for how many were tried",
    "unknown setup excluded": r"laps on an unknown setup are not used",
    "brake inputs not pooled across brake changes":
        r"never brake-phase inputs across a brake-tagged change",
    "derived with lap count": r"\[DERIVED\] and carries its lap count",
    "sized before he drives": r"sized from that corner's measured floor before he drives",
    "judged with his report": r"against its floor and his report",
    "practice only": r"never calls markers in a race",
}


def missing_guards(text: str) -> list[str]:
    return [name for name, pat in CARD_GUARDS.items() if not re.search(pat, text)]


# --- the tests -------------------------------------------------------------

def test_per_lap_instruction_is_still_refused_everywhere_it_was():
    for rel in (CLAUDE, CARD, BRAIN, CHARTER):
        assert still_refuses_per_lap(_read(rel)), (
            f"{rel} no longer refuses a per-lap per-corner instruction - the "
            "amendment lifted the pooled form only")


def test_the_blanket_refusal_is_gone_from_every_live_statement():
    for rel in (CLAUDE, CARD, BRAIN):
        left = blanket_refusal_survives(_read(rel))
        assert not left, (
            f"{rel} still refuses the pooled best corner the driver allowed on "
            f"14 Sep (RECONCILIATION AV): {left}")


def test_the_card_carries_every_guard_beside_the_permission():
    missing = missing_guards(_read(CARD))
    assert not missing, (
        "the refusal card allows a best corner without its guards - a subagent "
        f"sees only the card: {missing}")


def test_the_contract_and_the_brain_point_at_the_card():
    assert "ludo/references/refusals.md" in _read(CLAUDE)
    assert "ludo/references/refusals.md" in _read(BRAIN)
