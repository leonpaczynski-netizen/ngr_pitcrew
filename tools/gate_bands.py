"""Does the vocabulary reach the questions he actually asks?

`gate.py`'s bands carry an instruction in as many words: **re-measure if the
phrase list or the embedding model changes**, because the numbers there describe
those two things and nothing else. They were set on 22 Aug 2026 against 57
phrases, then the list was rewritten to 230 and the bands were never re-checked.
This is the check, as one command, so that broadening the vocabulary is a
measured change rather than a hopeful one.

**Measured 26 Aug 2026, and the first run said something the driver's own
complaint had not.** At the current band every one of thirty held-out questions
was acted on outright - and NINE of them were answered as the wrong question.
The vocabulary was not too narrow to reach him; it was reaching him and filing
him under the wrong heading, confidently, with no refusal anywhere to signal it.
The worst was "have the rears gone" at 0.124 - closer than any correct match in
the set - which is a question about tyre LIFE recorded as a driver report about
the CAR. Broadening the list to 339 phrases, and adding an intent whose only job
is to refuse by name, took that to 3 of the same 29.

**What it measures, and what it cannot.** Every question below is held out of
`intents.PHRASES` deliberately - a phrase measured against itself scores zero
and proves nothing. So this reports how a *new* way of asking an *old* question
lands, which is the failure the driver reported in his own words: it doesn't
understand what I'm saying.

It reports three things per sensitivity band:

* **reached** - acted on outright, which is the only outcome that costs him
  nothing.
* **confirmed** - answered, but only after "did you mean...?". A syllable and a
  second at racing speed. Not a failure; not free either.
* **refused** - "say again". The one outcome that makes him ask twice with both
  hands on the wheel.

And separately, **wrong** - reached or confirmed against the wrong intent. This
is the number that matters most and the one a distance threshold cannot fix:
measured on the previous vocabulary, being close was almost no guide to being
right (9 of 11 correct at or below 0.34, 4 of 5 above it). A change that raises
`reached` while raising `wrong` has made the engineer more confident and less
correct, which is the worst direction available.

The junk set exists to bound the cost of a wide band, not to be separated from
the questions - there is no gap between them and no threshold makes one. He
pressed a button to talk to his race engineer; he is not asking about milk.

    python tools/gate_bands.py
    python tools/gate_bands.py --show-misses

Read-only. Loads the embedding model, which takes a few seconds.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.engineer import gate, intents  # noqa: E402

# Held out of `PHRASES` on purpose. Each is a way he could ask something the
# app can already answer, phrased as he would say it rather than as the
# vocabulary lists it. Where one of these is later added to `PHRASES`, replace
# it here - measuring against a phrase in the list measures nothing.
HELD_OUT: tuple[tuple[str, str], ...] = (
    ("have i got enough to get to the end", intents.FUEL),
    ("am i going to run out", intents.FUEL),
    ("what am i sitting on for fuel", intents.FUEL),
    ("who have i got in front of me", intents.GAP),
    ("have i moved up at all", intents.POSITION),
    ("how much of this race is left", intents.LAPS_LEFT),
    ("how many more laps of this", intents.LAPS_LEFT),
    ("am i coming in this lap", intents.BOX_WHEN),
    ("how many laps until the stop", intents.BOX_WHEN),
    ("what am i going onto", intents.BOX_WHAT),
    ("what rubber am i getting", intents.BOX_WHAT),
    ("how many litres are going in", intents.BOX_FUEL),
    ("run me through it again", intents.PLAN),
    ("what's the shape of this race", intents.PLAN),
    ("how knackered are the fronts", intents.TYRES),
    ("is there anything left in these", intents.TYRES),
    ("have the rears gone", intents.TYRES),
    ("was that a good lap", intents.PACE),
    ("am i going quick enough", intents.PACE),
    ("am i on top of the fuel", intents.ON_PLAN),
    ("am i burning too much", intents.ON_PLAN),
    ("the front just washes out", intents.REPORT_UNDERSTEER),
    ("it won't turn in", intents.REPORT_UNDERSTEER),
    ("the back stepped out on me", intents.REPORT_OVERSTEER),
    ("that nearly went round on me", intents.REPORT_OVERSTEER),
    ("i've just been off", intents.REPORT_INCIDENT),
    ("someone put me in the gravel", intents.REPORT_INCIDENT),
    ("i'm stuck behind someone", intents.REPORT_TRAFFIC),
    ("there's a train of cars in front", intents.REPORT_TRAFFIC),
    ("say that one again", intents.REPEAT),
    # Unanswerable, and that is the point: the feed carries one car. The right
    # outcome is the named refusal, not a confident answer to a neighbouring
    # question.
    ("how much is he pulling out on me", intents.GAP),
    ("am i reeling him in", intents.GAP),
    ("what's my advantage", intents.GAP),
)

# Things that are not questions for a race engineer. Not a separation test -
# these overlap the real questions and always will - but a cost check: how much
# of this a band would answer, and whether answering it would matter.
JUNK: tuple[str, ...] = (
    "remind me to buy milk",
    "the dog wants to go out",
    "what's the weather doing tomorrow",
    "turn the volume down a bit",
    "i need to reply to that email",
    "what time is dinner",
    "the fridge is making a noise",
    "put the kettle on",
)


def _bands(distance: float | None, sensitivity: str) -> str:
    act, confirm = gate.SENSITIVITIES[sensitivity]
    if distance is None:
        return "reached"          # literal match; no distance was computed
    if distance <= act:
        return "reached"
    if distance <= confirm:
        return "confirmed"
    return "refused"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--show-misses", action="store_true",
                    help="print every question the vocabulary got wrong")
    args = ap.parse_args()

    # **A probe that is in `PHRASES` measures nothing** - it is compared
    # against itself and scores zero, so it lands in the act band by
    # construction and inflates every "reached" count. Three of the original
    # thirty were in the list without anyone noticing. Loud, not silent: a
    # benchmark that quietly grades its own answer key is worse than none.
    listed = {phrase for group in intents.PHRASES.values() for phrase in group}
    circular = [q for q, _intent in HELD_OUT if q in listed]
    if circular:
        print("these probes are in intents.PHRASES and measure nothing:")
        for question in circular:
            print(f"    {question!r}")
        print("replace them with phrasings that are genuinely held out.")
        return 2

    from pitcrew.engineer.ptt import best_semantic_matcher

    matcher = best_semantic_matcher()
    if matcher is None:
        print("no embedding model - nothing to measure")
        return 1

    total_phrases = sum(len(v) for v in intents.PHRASES.values())
    print(f"\n{len(intents.PHRASES)} intents, {total_phrases} phrases")
    print(f"{len(HELD_OUT)} held-out questions, {len(JUNK)} non-questions\n")

    scored = []
    for said, want in HELD_OUT:
        got, distance = matcher.match(said)
        scored.append((said, want, got, distance))
    junk_scored = [(said, matcher.match(said)) for said in JUNK]

    print(f"{'band':10} {'reached':>8} {'confirmed':>10} {'refused':>8} "
          f"{'WRONG':>7} {'junk answered':>14}")
    for sensitivity in ("low", "medium", "high"):
        counts = {"reached": 0, "confirmed": 0, "refused": 0}
        wrong = 0
        for _said, want, got, distance in scored:
            where = _bands(distance, sensitivity)
            counts[where] += 1
            # Only an answered question can be answered wrongly. A refusal is
            # not a wrong answer - it is the engineer declining to guess, which
            # is the behaviour the whole gate exists to produce.
            if where != "refused" and got != want:
                wrong += 1
        answered_junk = sum(
            1 for _said, (_got, distance) in junk_scored
            if _bands(distance, sensitivity) != "refused")
        mark = "  <- current" if sensitivity == gate.DEFAULT_SENSITIVITY else ""
        print(f"{sensitivity:10} {counts['reached']:8} "
              f"{counts['confirmed']:10} {counts['refused']:8} "
              f"{wrong:7} {answered_junk:>10}/{len(JUNK)}{mark}")

    reals = sorted(d for _s, _w, _g, d in scored if d is not None)
    junks = sorted(d for _s, (_g, d) in junk_scored if d is not None)
    if reals and junks:
        print(f"\n  real questions   {reals[0]:.3f} - {reals[-1]:.3f}"
              f"   (median {reals[len(reals) // 2]:.3f})")
        print(f"  non-questions    {junks[0]:.3f} - {junks[-1]:.3f}"
              f"   (median {junks[len(junks) // 2]:.3f})")
        if reals[-1] > junks[0]:
            print("  ** they overlap, as they always have - the band is set "
                  "on the cost of being wrong, not on a separation")

    misses = [(s, w, g, d) for s, w, g, d in scored if g != w]
    print(f"\n  {len(misses)} of {len(scored)} matched the wrong intent")
    if misses and args.show_misses:
        for said, want, got, distance in sorted(
                misses, key=lambda m: m[3] if m[3] is not None else 9):
            near = f"{distance:.3f}" if distance is not None else "literal"
            print(f"    {near:>7}  {said!r}")
            print(f"             wanted {want}, got {got}")
    elif misses:
        print("             --show-misses to see them")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
