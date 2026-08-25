"""What he asked on the radio, and which of it the engineer could not take.

**The vocabulary cannot be designed from a desk.** Every phrase in
`intents.PHRASES` is somebody's guess at how a driver would say a thing, and
the two measurements that exist both say guessing is the weak part: the phrase
list was written for a SAPI grammar and then reused as the reference points a
semantic matcher measures natural speech against, and when it was finally
tested on held-out phrasing it missed three questions in sixteen - including
"how are my tyres", which is the question this whole application is about.

So this reads the ledger back the other way round. Not "did the app answer" but
**"what did he say, and what happened to it"**, ordered so that the presses
nobody could answer come first. Those are the additions.

Three things it separates, because they need different fixes:

* **Refused** - nothing close enough in meaning, or no question heard at all.
  A refusal with words in it is a phrase to add. A refusal with no words is a
  microphone or a button problem and belongs in the log, not the vocabulary.
* **Confirmed** - the engineer had to ask "did you mean...?". He got his
  answer, but it cost him a syllable and a second at racing speed. A phrasing
  that repeatedly lands here is a phrase to add to the intent it kept meaning.
* **Acted** - answered outright. Worth reading anyway: the intent recorded here
  is the one that actually replied, so an answer to the wrong question shows up
  as a sensible-looking row saying something he did not ask about.

**A refused press and an unrecorded press look identical from here.** The
ledger held nothing at all before 26 Aug 2026 - the handler returned early on
an empty transcript, which is exactly what a refusal looks like - so an empty
result for an old session means the rows were never written, not that every
press succeeded. It says so rather than reporting silence as success.

    python tools/radio_review.py                    # everything, newest first
    python tools/radio_review.py --session 84
    python tools/radio_review.py --event 6 --misses  # just what to add

Read-only. Nothing here writes.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.store.db import Store  # noqa: E402

# The ledger started recording the gate's own verdict at this schema version.
# Rows older than it carry a re-derived intent and no action at all, and saying
# so matters more than showing them: an `action` of null is "not recorded",
# never "acted".
VERDICTS_FROM = 10


def _rows(store, where: str, params) -> list:
    return [dict(r) for r in store._query(
        "SELECT radio.*, sessions.kind AS session_kind, "
        "sessions.event_id AS event_id FROM radio "
        "LEFT JOIN sessions ON sessions.id = radio.session_id "
        f"{where} ORDER BY radio.id DESC", params)]


def _bucket(row: dict) -> str:
    action = (row.get("action") or "").lower()
    if action in ("act", "confirm", "reject"):
        return action
    # Pre-verdict rows. An intent of `unknown` is the only signal they carry,
    # and it is a weak one - it was re-derived by the literal matcher, which
    # never saw the decision the driver heard.
    return "unrecorded"


def report(rows: list, *, misses_only: bool) -> list:
    out: list = []
    if not rows:
        out.append("  no exchanges recorded.")
        out.append("  ** the ledger dropped every refused press before "
                   "26 Aug 2026, so this is not evidence that none were "
                   "refused - it is evidence that none were written down.")
        return out

    buckets = Counter(_bucket(r) for r in rows)
    total = len(rows)
    out.append(f"  {total} exchanges   "
               + "   ".join(f"{name} {n}" for name, n in buckets.most_common()))
    if buckets.get("unrecorded"):
        n = buckets["unrecorded"]
        out.append(f"  ** {n} row{'s' if n != 1 else ''} predate the verdict "
                   f"columns (schema v{VERDICTS_FROM}) - their intent was "
                   f"re-derived afterwards and is not what the driver heard")

    for name, title in (("reject", "REFUSED - these are the additions"),
                        ("confirm", "CONFIRMED - cost him a syllable"),
                        ("act", "ANSWERED")):
        if misses_only and name == "act":
            continue
        picked = [r for r in rows if _bucket(r) == name]
        if not picked:
            continue
        out.append("")
        out.append(f"  {title}   ({len(picked)})")
        for row in picked:
            heard = (row.get("heard") or "").strip()
            if not heard:
                # No words at all: a brushed button or a microphone that never
                # opened. Nothing here is a phrase, so it is counted and named
                # rather than offered as vocabulary.
                why = row.get("reason") or "no reason recorded"
                out.append(f"    (no words)  {why}")
                continue
            where = f"s{row.get('session_id')}"
            if row.get("lap_num"):
                where += f" L{row['lap_num']}"
            near = (f"  ~{row['distance']:.3f}"
                    if row.get("distance") is not None else "")
            out.append(f"    {where:<10} {heard!r}{near}")
            if name != "reject" and row.get("intent"):
                out.append(f"    {'':<10}   answered as {row['intent']}: "
                           f"{(row.get('said') or '')[:60]!r}")
    return out


def suggestions(rows: list) -> list:
    """The refusals, deduplicated, in the shape `intents.PHRASES` wants.

    Deliberately not a proposed intent for each one. Deciding which intent a
    question belongs to - or that it belongs to a new one, or to none because
    the feed cannot answer it - is the judgement this tool exists to hand
    someone, and pre-filling it would be a guess wearing the clothes of a
    finding.
    """
    said = [(r.get("heard") or "").strip().lower()
            for r in rows if _bucket(r) in ("reject", "confirm")]
    counts = Counter(s for s in said if s)
    if not counts:
        return []
    out = ["", "  candidates, most-repeated first - each needs an intent "
           "deciding, or a refusal that names itself:"]
    for phrase, n in counts.most_common(30):
        out.append(f'    {n:>2}x  "{phrase}"')
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--session", type=int)
    ap.add_argument("--event", type=int)
    ap.add_argument("--misses", action="store_true",
                    help="only what the engineer could not take outright")
    args = ap.parse_args()

    store = Store()
    try:
        if args.session:
            rows = _rows(store, "WHERE radio.session_id = ?", (args.session,))
            scope = f"session {args.session}"
        elif args.event:
            rows = _rows(store, "WHERE sessions.event_id = ?", (args.event,))
            scope = f"event {args.event}"
        else:
            rows = _rows(store, "", ())
            scope = "every session"

        print(f"\nradio ledger - {scope}\n")
        for line in report(rows, misses_only=args.misses):
            print(line)
        for line in suggestions(rows):
            print(line)
        print()
        return 0
    finally:
        store.close()


if __name__ == "__main__":
    raise SystemExit(main())
