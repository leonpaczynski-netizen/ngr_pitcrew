"""No name may be defined twice in one class or one module.

**22 Aug 2026: `PitCrewController._event_fuel_capacity` was defined twice.**
One took the event dict, the other its id; they disagreed about whether a
stored `0.0` capacity means "electric car" or "session opened before the car
loaded". Python keeps the later definition, so the newer method was dead on
arrival - and the newer CALLER, the qualifying plan, handed a dict to
`list_sessions`:

    ProgrammingError: Error binding parameter 1: type 'dict' is not supported

The qualifying-plan button raised every time it was pressed, in a Qt slot
with no `try` around it. Nothing caught it: not the type checker, not the
2352-test suite, not review - because a 4,763-line class is exactly where two
definitions 343 lines apart are invisible.

This is a whole-package structural check rather than a test of that one
method, because the next one will be somewhere else. It costs a few
milliseconds and it cannot be fooled by the shadowed copy being plausible.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

# `@property` + `@x.setter` is a legitimate repeat, and so is
# `@typing.overload` and a `@functools.singledispatch` register. Everything
# else that repeats is a mistake.
ALLOWED_REPEAT_DECORATORS = {"setter", "getter", "deleter", "overload",
                             "register"}


def _decorator_names(node) -> set[str]:
    names = set()
    for dec in getattr(node, "decorator_list", []):
        target = dec.func if isinstance(dec, ast.Call) else dec
        while isinstance(target, ast.Attribute):
            names.add(target.attr)
            target = target.value
        if isinstance(target, ast.Name):
            names.add(target.id)
    return names


def _duplicates(body, where: str) -> list[str]:
    """Every name bound more than once directly in this body."""
    seen: dict[str, int] = {}
    found: list[str] = []
    for node in body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
            continue
        if _decorator_names(node) & ALLOWED_REPEAT_DECORATORS:
            continue
        first = seen.get(node.name)
        if first is not None:
            found.append(
                f"{where}: {node.name!r} defined at line {first} and again at "
                f"line {node.lineno} - the first is dead")
        else:
            seen[node.name] = node.lineno
    return found


def _sources() -> list[pathlib.Path]:
    return sorted(
        p for p in ROOT.rglob("*.py")
        if "tests" not in p.parts and "__pycache__" not in p.parts)


@pytest.mark.parametrize(
    "path", _sources(), ids=lambda p: str(p.relative_to(ROOT)))
def test_nothing_is_defined_twice(path: pathlib.Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rel = path.relative_to(ROOT)

    problems = _duplicates(tree.body, f"{rel} (module level)")
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            problems += _duplicates(node.body, f"{rel}::{node.name}")

    assert not problems, (
        "a definition is shadowed by a later one of the same name, so the "
        "first is unreachable:\n  " + "\n  ".join(problems))
