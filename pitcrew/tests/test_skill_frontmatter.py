"""Every skill's frontmatter parses, and its description survives.

**This failure is silent, which is the whole reason for the test.** A colon in
an unquoted YAML scalar makes the block unparseable - and a skill whose
frontmatter will not parse does not error. It loads with no description, falls
back to its heading, and simply stops being triggered by the phrases it was
written to catch. Nothing anywhere says so.

Caught live on 26 Aug 2026: `description: ... the driver or the plan: building
or refining a setup sheet ...` took Ludo's description from a paragraph of
trigger contexts to the four words of its `# ` heading.

The description is also the only surface the driver reads to remember what a
skill does, so an empty one costs twice.
"""
from __future__ import annotations

from pathlib import Path

import pytest

SKILLS = Path(__file__).resolve().parents[2] / ".claude" / "skills"


def _skill_files() -> list[Path]:
    return sorted(SKILLS.glob("*/SKILL.md")) if SKILLS.is_dir() else []


def _frontmatter(text: str) -> str:
    """The block between the first two `---` fences."""
    assert text.startswith("---\n"), "no frontmatter fence at the top"
    return text.split("---\n")[1]


@pytest.mark.parametrize("path", _skill_files(), ids=lambda p: p.parent.name)
def test_the_frontmatter_parses_and_carries_a_description(path: Path):
    yaml = pytest.importorskip("yaml")

    meta = yaml.safe_load(_frontmatter(path.read_text(encoding="utf-8")))
    assert isinstance(meta, dict), f"{path.parent.name}: frontmatter is not a map"
    assert meta.get("name"), f"{path.parent.name}: no name"

    description = meta.get("description") or ""
    # Short enough to be a stub rather than a trigger. The description is the
    # entire triggering mechanism - there is no other signal - so a one-liner
    # means the skill fires on almost nothing.
    assert len(description) > 80, (
        f"{path.parent.name}: description is {len(description)} chars, which is "
        f"too short to trigger on anything: {description!r}")


@pytest.mark.parametrize("path", _skill_files(), ids=lambda p: p.parent.name)
def test_no_unquoted_colon_can_break_the_block_later(path: Path):
    """The specific shape that broke it, caught before it is committed.

    `key: value with: a colon` is legal-looking and fatal. It parses today only
    because the *first* colon wins and the rest lands inside the scalar - until
    a line happens to put one where YAML reads it as a nested key. Rather than
    reason about which colons are safe, require that a value containing one is
    quoted, which is unconditionally safe.
    """
    for line in _frontmatter(path.read_text(encoding="utf-8")).splitlines():
        if not line or line.startswith((" ", "\t", "#")) or ":" not in line:
            continue
        _key, _, value = line.partition(":")
        value = value.strip()
        if value.startswith(("'", '"', "|", ">", "[", "{")):
            continue
        assert ": " not in value, (
            f"{path.parent.name}: {_key.strip()!r} holds an unquoted colon and "
            f"will break the block. Quote the value or use a dash: {value[:70]!r}")
