"""Loading the prompt prose.

The wording lives in `templates.json` next to this module, not in the builder,
so it can be edited without touching application logic — and so that a change
to it is a data change with a version, rather than a code change nobody can
trace from a returned setup sheet.
"""
from __future__ import annotations

import functools
import json
from pathlib import Path

TEMPLATES_FILE = Path(__file__).resolve().parent / "templates.json"


@functools.lru_cache(maxsize=1)
def templates() -> dict:
    with TEMPLATES_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


@functools.lru_cache(maxsize=1)
def _version() -> str:
    return templates().get("version") or "pitcrew-prompts/unversioned"


# Read once at import so the constant is importable, but the loader stays the
# single place the file is read.
PROMPT_VERSION = _version()


def block(*path: str) -> str:
    """One template string, by path. Raises rather than returning a blank.

    A missing block would otherwise print as an empty line in the middle of a
    prompt and be read as "nothing to say about this", which is a different
    claim from "the template is broken".
    """
    node: object = templates()
    for step in path:
        if not isinstance(node, dict) or step not in node:
            raise KeyError(
                f"prompt template has no block {'.'.join(path)!r} — "
                f"templates.json and the builder are out of step")
        node = node[step]
    if not isinstance(node, (str, list)):
        raise KeyError(f"prompt block {'.'.join(path)!r} is not text")
    return node
