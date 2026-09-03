"""Record a setup change and, above all, WHY it was made.

`setup_changes` is written automatically at session open by
`Store.note_sheet_change`, which diffs this session's sheet against the last
one on the same car and circuit. That catches *what* moved and can never catch
*why* — a sheet diff has no access to intent — so until 3 Sep 2026 the ledger
held 202 rows and not one reason.

The why is the half that makes the ledger a learning loop rather than a log.
`dc_r 30 -> 26` scores differently depending on whether it was made for exit
traction or for braking stability: the same outcome confirms one and refutes
the other, and without the stated intent neither verdict is available.

    # attach a reason to rows this session already filed
    python tools/log_setup_change.py --session 116 --list
    python tools/log_setup_change.py --reason 7 "exit traction at zone 4"

    # file a change the sheet diff could not see
    python tools/log_setup_change.py --session 116 --from-lap 1 \
        --key dc_r --from 30 --to 26 --source issued \
        --reason "rear mechanical grip off the apex; zone 4 exit"

**Sources** say how the value was learned, and a request is not a reading:
`screen` (GT7's settings screen — ground truth), `feed` (telemetry; only the
gearbox can be), `issued` (what the engineer asked for), `sheet-diff`
(derived), `driver` (he said so).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pitcrew.setup.sheet import SetupChange, SetupError
from pitcrew.setup.vocabulary import CHANGE_KEY_NAMES, CHANGE_SOURCES, describe
from pitcrew.store.db import Store


def _show(store: Store, session_id: int) -> int:
    rows = store._query(                                   # noqa: SLF001
        "SELECT id, from_lap, key, from_value, to_value, reason, source "
        "FROM setup_changes WHERE session_id = ? ORDER BY from_lap, id",
        (session_id,))
    if not rows:
        print(f"session {session_id}: no changes on file")
        return 0
    print(f"session {session_id}: {len(rows)} change(s)")
    for r in rows:
        key = describe(r["key"])
        label = key.label if key else r["key"]
        print(f"  [{r['id']:>4}] lap {r['from_lap']}  {label} "
              f"({r['key']}): {r['from_value']} -> {r['to_value']}"
              f"   source={r['source'] or '?'}")
        print(f"         why: {r['reason'] or '** NOT RECORDED **'}")
    missing = sum(1 for r in rows if not r["reason"])
    if missing:
        print(f"\n  {missing} of {len(rows)} carry no reason. "
              f"A change without an intent cannot be scored against one.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--session", type=int, help="session id")
    p.add_argument("--list", action="store_true",
                   help="show this session's changes and which lack a reason")
    p.add_argument("--reason", nargs=2, metavar=("CHANGE_ID", "TEXT"),
                   help="attach a reason to an existing change row")
    p.add_argument("--key", help=f"one of: {', '.join(CHANGE_KEY_NAMES)}")
    p.add_argument("--from", dest="from_value", type=float)
    p.add_argument("--to", dest="to_value", type=float)
    p.add_argument("--from-lap", type=int, default=1)
    p.add_argument("--source", choices=CHANGE_SOURCES)
    p.add_argument("--why", help="why the change was made (with --key)")
    args = p.parse_args(argv)

    store = Store()

    if args.reason:
        change_id, text = int(args.reason[0]), args.reason[1]
        if store.set_setup_change_reason(change_id, text):
            print(f"change {change_id}: reason recorded")
            return 0
        print(f"no change with id {change_id}", file=sys.stderr)
        return 1

    if args.list:
        if args.session is None:
            p.error("--list needs --session")
        return _show(store, args.session)

    if args.key:
        if args.session is None:
            p.error("--key needs --session")
        # **A change filed by hand must say why.** The automatic path is
        # allowed a null reason because a sheet diff genuinely does not know
        # one; a human at a keyboard does, and a ledger that lets the why be
        # skipped is the ledger we already had.
        if not args.why:
            p.error("--key needs --why: a change with no stated intent cannot "
                    "be scored against one")
        try:
            change = SetupChange(from_lap=args.from_lap, key=args.key,
                                 from_value=args.from_value,
                                 to_value=args.to_value,
                                 reason=args.why,
                                 source=args.source or "issued")
            new_id = store.add_setup_change(args.session, change)
        except SetupError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 1
        print(f"change {new_id} filed on session {args.session}: "
              f"{args.key} {args.from_value} -> {args.to_value}")
        return 0

    p.error("nothing to do - try --list, --reason or --key")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
