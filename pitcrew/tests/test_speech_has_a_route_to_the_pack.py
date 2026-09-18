"""Every module that SPEAKS is a module the manifest can reach.

**This test exists because five families were found in one sweep on 18 Sep
2026, and every one of them had been green all along.** The coverage tests
check that what is DECLARED is rendered. Nothing checked that what is SAID is
declarable - so speech written where `phrase_manifest` has no way to call it
was rendered nowhere, synthesised live, and heard as a pause before the
engineer. The tablet's three levers, the whole beep-column family,
`Replan.call()`, the gauge's blind note and the entire qualifying coach.

The rule this pins is structural, not a list of sentences: **a sentence the
driver hears lives in a module the manifest imports.** Moving one there costs
nothing; leaving it inline costs a pause at racing speed.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "engineer" / "phrase_manifest.py"

# Modules that speak and that the manifest is NOT expected to reach, each with
# the reason it is affordable. The test is not asking for every line in the app
# to be rendered - it is asking for the decision to be made and written down.
SPEAKS_BUT_LIVE = {
    # The controller passes text it was handed; it must not AUTHOR any. That
    # is the whole finding - every sentence it authored was unreachable - so
    # it is allowed here only as a relay, and `test_the_controller_authors_no
    # _speech` below is what actually holds it to that.
    "controller.py": "relays text built elsewhere; authors none of it",
}

# Said in the garage or on the grid rather than at racing speed, so a pause
# in front of them is affordable. They reach the voice THROUGH the controller,
# which is why they are not in the map above: nothing in them calls `say`.
#   analysis/debrief.py  - the practice debrief, between sessions
#   the grid brief's league line - names and points, and combinatorial


def _module_of(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _speaking_modules() -> dict[str, list[int]]:
    """Every module with a `.say(` call in it, and the lines it is on."""
    found: dict[str, list[int]] = {}
    for path in sorted(ROOT.rglob("*.py")):
        rel = _module_of(path)
        if rel.startswith("tests/"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                                  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr in ("say", "_say")):
                found.setdefault(rel, []).append(node.lineno)
    return found


def _manifest_imports() -> set[str]:
    """Modules `phrase_manifest` imports, at module scope or inside a family."""
    tree = ast.parse(MANIFEST.read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("pitcrew."):
                modules.add(node.module[len("pitcrew."):].replace(".", "/")
                            + ".py")
    return modules


def test_every_speaking_module_is_one_the_manifest_can_reach():
    """A new module that speaks must be declared or explicitly excused."""
    reachable = _manifest_imports()
    unreachable = []
    for module, lines in _speaking_modules().items():
        if module in SPEAKS_BUT_LIVE or module in reachable:
            continue
        # The voice machinery itself speaks nothing of its own.
        if module.startswith("engineer/voice") or module.startswith("engineer/say"):
            continue
        unreachable.append(f"{module} (lines {lines[:4]})")
    assert not unreachable, (
        "these modules speak to the driver but `phrase_manifest` imports "
        "nothing from them, so nothing they say can be declared, so none of "
        "it is rendered and all of it is synthesised live at racing speed. "
        "Either declare a family for it, or add it to SPEAKS_BUT_LIVE with "
        "the reason a pause there is affordable: " + "; ".join(unreachable))


def test_the_controller_authors_no_speech():
    """`voice.say("...")` with a literal in the controller is the defect.

    The controller cannot be reached by the manifest and never will be - it
    imports half the app. So a sentence written there is unreachable by
    construction, which is exactly how the tablet's three buttons, the
    re-planning notice and the rig's two lines came to be live. Text it is
    HANDED is fine; text it writes is not.
    """
    tree = ast.parse((ROOT / "controller.py").read_text(encoding="utf-8"))
    authored = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "say"):
            continue
        for arg in node.args[:1]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                authored.append((node.lineno, arg.value[:60]))
            elif isinstance(arg, ast.JoinedStr):
                # An f-string of only named pieces is a join, not an author.
                if any(isinstance(part, ast.Constant)
                       and part.value.strip() not in ("", " ")
                       for part in arg.values):
                    authored.append((node.lineno, "f-string with wording"))
    assert not authored, (
        "the controller authors these, where the manifest cannot reach them "
        f"- move the wording to the module that owns it: {authored}")
