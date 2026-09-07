"""What is built and wired to nothing: empty tables, and modules nobody imports.

    python tools/wiring_audit.py            # data/pitcrew.db, read-only
    python tools/wiring_audit.py --db x.db

This codebase has built both ends of a mechanism and skipped the caller at
least eight times on record - `setup_changes` (0 rows / 88 sessions),
`prompts/questions.py` (500 lines, no caller), `video_index.build` (test file
only), `rival_answers`/`rival_pace`/`teammate`/`ledger` (no production
importer), `carry_into_knowledge` (no caller), `lost_the_gauge` (imported,
never called), `rival_stops` (0 rows for every race - a column never reached
the live file). Each looked complete from either end.

Two lists, both cheap, both read-only:

1. **Tables with no rows in the live database.** A table with rows is
   evidence; one without is a gap, a fossil, or a design never built, and the
   report cannot tell which - only that somebody should.
2. **Modules under `pitcrew/` that no other module outside `tests/` imports.**
   Entry points (`app.py`, `controller.py`, `mcp/server.py`, `bench.py`) are
   exempt by name; everything else with no importer is a seam with one end.

Exit 0 always: this is a report, not a gate. Run it in CI and read it.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "pitcrew"

ENTRY_POINTS = {"pitcrew.app", "pitcrew.controller", "pitcrew.mcp.server",
                "pitcrew.bench", "pitcrew.diagnostics", "pitcrew.paths",
                "pitcrew.settings"}
# Tables that are legitimately empty on a machine that has never done the
# thing: named so the report can say "expected" rather than "unwired".
EXPECTED_EMPTY = {"series_teammates": "written by nothing yet (assessment S3)",
                  "gap_reads": "filled by the pit wall from the next race "
                               "(added 7 Sep 2026)",
                  "board_positions": "filled by the pit wall from the next "
                                     "race (added 8 Sep 2026)"}

# The names group must not run across lines: `[\w\s,()]+` swallowed every
# import that followed the first one in a file and reported half the package
# as unimported on the tool's first run.
_IMPORT = re.compile(r"^\s*(?:from\s+(pitcrew(?:\.\w+)*)\s+import\s+"
                     r"(\([^)]*\)|[^\r\n]*)"
                     r"|import\s+(pitcrew(?:\.\w+)*))", re.M)


def empty_tables(db: Path) -> list[tuple[str, str]]:
    conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        names = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        out = []
        for name in names:
            count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            if count == 0:
                out.append((name, EXPECTED_EMPTY.get(name, "no rows - unwired, "
                                                          "a fossil, or unused")))
        return out
    finally:
        conn.close()


def modules() -> dict[str, Path]:
    found = {}
    for path in PKG.rglob("*.py"):
        if "tests" in path.parts or path.name == "__init__.py":
            continue
        dotted = ".".join(path.relative_to(ROOT).with_suffix("").parts)
        found[dotted] = path
    return found


def importers(mods: dict[str, Path]) -> dict[str, set[str]]:
    """module -> set of modules (outside tests) that import it."""
    who: dict[str, set[str]] = {m: set() for m in mods}
    scan = list(mods.items()) + [
        (".".join(p.relative_to(ROOT).with_suffix("").parts), p)
        for p in (ROOT / "tools").glob("*.py")]
    for name, path in scan:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in _IMPORT.finditer(text):
            base = m.group(1) or m.group(3)
            if base is None:
                continue
            targets = {base}
            if m.group(1) and m.group(2):
                for piece in m.group(2).replace("(", "").replace(")", "").split(","):
                    piece = piece.strip().split(" as ")[0].strip()
                    if piece:
                        targets.add(f"{base}.{piece}")
            for target in targets:
                if target in who and target != name:
                    who[target].add(name)
    return who


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(ROOT / "data" / "pitcrew.db"))
    args = ap.parse_args(argv)

    db = Path(args.db)
    print("== tables with no rows ==")
    if db.exists():
        rows = empty_tables(db)
        for name, why in rows:
            print(f"  {name:24s} {why}")
        if not rows:
            print("  none")
    else:
        print(f"  no database at {db}")

    print("== modules no production code imports ==")
    mods = modules()
    who = importers(mods)
    lonely = sorted(m for m, users in who.items()
                    if not users and m not in ENTRY_POINTS
                    and not m.startswith("pitcrew.ui.")
                    and not m.startswith("pitcrew.tests"))
    for m in lonely:
        print(f"  {m}")
    if not lonely:
        print("  none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
