"""Diff the schema the code declares against the database that actually exists.

    python tools/schema_audit.py                 # data/pitcrew.db
    python tools/schema_audit.py --db other.db

`CREATE TABLE IF NOT EXISTS` is a no-op on a table that already exists, so a
column added to the DDL without an `ADDED_COLUMNS` entry reaches every fresh
database and no real one. The suite builds fresh databases, so it cannot see
this; the live file is the only place the defect shows, and it shows as an
`OperationalError` swallowed by a try/except - `rival_stops` held zero rows for
every race ever run while its tests asserted `compound_reads == 3`.

Exit 1 when any declared column is missing from the file. The file is opened
read-only; nothing here migrates anything.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pitcrew.store.schema import DDL  # noqa: E402

_TABLE = re.compile(
    r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\);", re.S | re.I)
_LINE_COMMENT = re.compile(r"--[^\n]*")


def declared_columns(ddl: str = DDL) -> dict[str, list[str]]:
    """Every table in the DDL with its column names, in declaration order.

    A line that starts with a constraint keyword is not a column. Comments are
    stripped first because a `--` remark can contain a comma.
    """
    tables: dict[str, list[str]] = {}
    for name, body in _TABLE.findall(_LINE_COMMENT.sub("", ddl)):
        columns: list[str] = []
        depth = 0
        piece = ""
        for ch in body:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            if ch == "," and depth == 0:
                columns.append(piece)
                piece = ""
            else:
                piece += ch
        columns.append(piece)
        for raw in columns:
            words = raw.split()
            if not words:
                continue
            head = re.split(r"[(\s]", words[0].upper(), maxsplit=1)[0]
            if head in {"PRIMARY", "UNIQUE", "FOREIGN", "CHECK", "CONSTRAINT"}:
                continue
            tables[name] = tables.get(name, []) + [words[0]]
    return tables


def drift(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Declared columns the connected database does not have, per table.

    A table absent from the file is reported with every column missing; the
    DDL would create it on the next open, so that is drift of a harmless kind,
    but it is still a table nothing has ever written.
    """
    missing: dict[str, list[str]] = {}
    for table, columns in declared_columns().items():
        have = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        gone = [c for c in columns if c not in have]
        if gone:
            missing[table] = gone
    return missing


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--db", default=str(ROOT / "data" / "pitcrew.db"))
    args = parser.parse_args(argv)

    path = Path(args.db)
    if not path.exists():
        print(f"no database at {path}")
        return 2
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        missing = drift(conn)
    finally:
        conn.close()
    print(f"{path}: user_version {version}")
    if not missing:
        print("no drift: every declared column exists in the file.")
        return 0
    for table, columns in missing.items():
        print(f"  {table}: missing {', '.join(columns)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
