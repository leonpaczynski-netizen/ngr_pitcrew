"""Adaptive Per-Gear Shift Strategy — source-inspection safety tests.

Mirrors tests/test_phase69_71_safety.py idiom: the _code_only helper strips
all comments and string/docstring literals so assertions inspect actual CODE
(imports, calls, attribute names) rather than prose in docstrings.

WHAT IS CHECKED
  * No PyQt / PySide import in any new module (including ui/shift_strategy_vm.py
    which must stay Qt-free so it is importable in the test suite without a
    running Qt app).
  * No sqlite3 / INSERT / UPDATE / DB writes.
  * No socket / UDP / network access.
  * No AI / API key / requests.
  * No setup-authoring calls (apply_setup, write_setup, SetupApply, setup_history).
  * No shift-beep-RPM WRITE (the shift-rpm setting is a separate concern).
  * No game commands (keyboard, joystick, pyautogui, press_button, execute_pit).
"""
from __future__ import annotations

import io
import tokenize
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent

_NEW_MODULES = [
    "strategy/shift_strategy_constants.py",
    "strategy/shift_strategy_inputs.py",
    "strategy/shift_strategy_engine.py",
    "services/shift_strategy_store.py",
    "ui/shift_strategy_vm.py",
]

# The view file may import Qt (it is a widget), so it is tested SEPARATELY
# below rather than being included in _NEW_MODULES (which asserts no Qt).
_VIEW_MODULE = "ui/components/shift_strategy_view.py"


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _code_only(rel: str) -> str:
    """Source with all comments and string/docstring contents removed.

    Inspects actual CODE tokens (imports, calls, identifiers) rather than
    prose descriptions of what a module deliberately does NOT do.
    """
    src = _src(rel)
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type in (tokenize.COMMENT, tokenize.STRING):
                continue
            out.append(tok.string)
    except tokenize.TokenError:
        return src
    return " ".join(out)


# ---------------------------------------------------------------------------
# Qt-free
# ---------------------------------------------------------------------------

def test_no_qt_import_in_any_new_module():
    """ALL new modules must be importable without a Qt runtime."""
    for rel in _NEW_MODULES:
        code = _code_only(rel)
        assert "PyQt" not in code, f"{rel} must not import PyQt"
        assert "PySide" not in code, f"{rel} must not import PySide"
        assert "QApplication" not in code, f"{rel} must not reference QApplication"
        assert "QWidget" not in code, f"{rel} must not reference QWidget"


def test_vm_has_no_qt_import():
    """ui/shift_strategy_vm.py specifically: zero Qt references in code."""
    code = _code_only("ui/shift_strategy_vm.py")
    for banned in ("PyQt6", "PyQt5", "PySide6", "PySide2", "QtWidgets", "QtCore"):
        assert banned not in code, (
            f"ui/shift_strategy_vm.py must not reference {banned!r} — "
            "it must stay Qt-free so tests run without a display"
        )


# ---------------------------------------------------------------------------
# No DB writes
# ---------------------------------------------------------------------------

def test_no_sqlite_or_db_write_in_new_modules():
    for rel in _NEW_MODULES:
        code = _code_only(rel)
        assert "sqlite3" not in code, f"{rel} must not use sqlite3"
        assert "INSERT" not in code, f"{rel} must not issue INSERT"
        assert "UPDATE" not in code, f"{rel} must not issue UPDATE"


# ---------------------------------------------------------------------------
# No network / socket
# ---------------------------------------------------------------------------

def test_no_socket_or_udp_in_new_modules():
    for rel in _NEW_MODULES:
        src = _src(rel)   # full source so bind/SOCK appear anywhere
        assert "socket.socket" not in src, f"{rel} must not open a socket"
        assert "SOCK_DGRAM" not in src, f"{rel} must not use UDP"
        assert "UDPListener" not in src, f"{rel} must not reference UDPListener"
        assert ".bind(" not in src, f"{rel} must not call .bind("


# ---------------------------------------------------------------------------
# No AI / external API
# ---------------------------------------------------------------------------

def test_no_ai_or_api_key_in_new_modules():
    for rel in _NEW_MODULES:
        code = _code_only(rel)
        assert "openai" not in code, f"{rel} must not import openai"
        assert "api_key" not in code, f"{rel} must not reference api_key"
        assert "requests" not in code, f"{rel} must not import requests"


# ---------------------------------------------------------------------------
# No setup-authoring
# ---------------------------------------------------------------------------

def test_no_setup_authoring_in_new_modules():
    """The strategy module must not write setups or setup history."""
    banned_tokens = (
        "apply_setup", "SetupApply", "write_setup", "setup_history",
        "save_setup_history",
    )
    for rel in _NEW_MODULES:
        code = _code_only(rel).lower()
        for b in banned_tokens:
            assert b.lower() not in code, (
                f"{rel} must not reference {b!r} in code (setup authoring is forbidden)"
            )


# ---------------------------------------------------------------------------
# No shift-beep-RPM write (separate concern from shift strategy)
# ---------------------------------------------------------------------------

def test_no_shift_rpm_write_in_new_modules():
    """Shift strategy computes optimal RPMs — it must not SET the shift-beep knob."""
    for rel in _NEW_MODULES:
        code = _code_only(rel)
        # The shift-rpm recommendation module is a SIBLING; we must not call its
        # write path.  The constants file is allowed to reference shift_rpm in names.
        # We specifically ban calling set_shift_rpm / write_shift_rpm.
        assert "set_shift_rpm" not in code, f"{rel} must not call set_shift_rpm"
        assert "write_shift_rpm" not in code, f"{rel} must not call write_shift_rpm"


# ---------------------------------------------------------------------------
# No game commands
# ---------------------------------------------------------------------------

def test_no_game_commands_in_new_modules():
    banned = (
        "keyboard", "joystick", "sendkey", "pyautogui",
        "press_button", "execute_pit",
    )
    for rel in _NEW_MODULES:
        code = _code_only(rel).lower()
        for b in banned:
            assert b not in code, (
                f"{rel} must not issue device/game commands ({b!r})"
            )


# ---------------------------------------------------------------------------
# Parseable and have module docstrings
# ---------------------------------------------------------------------------

def test_all_new_modules_parse_and_have_docstrings():
    import ast
    for rel in _NEW_MODULES:
        src = _src(rel)
        tree = ast.parse(src)
        assert ast.get_docstring(tree), f"{rel} must have a module docstring"


# ---------------------------------------------------------------------------
# View module — setup-apply / game-command safety
# ---------------------------------------------------------------------------

def test_view_has_no_setup_apply_controls():
    """The shift strategy view must contain no setup-apply, fuel-map or game controls.

    These tokens would indicate that the advisory-only surface is trying to write a
    setup or issue a game command — both are forbidden. Checked in CODE tokens so
    comments and docstrings do not produce false positives.
    """
    code = _code_only(_VIEW_MODULE)
    code_lower = code.lower()
    forbidden = (
        "set_plan(",
        "fuel_map",
        "execute_pit",
        "press_button",
    )
    for token in forbidden:
        assert token not in code_lower, (
            f"{_VIEW_MODULE} must not reference {token!r} "
            "(advisory-only surface; no setup-apply or game commands allowed)")

    # "apply" is checked separately with a tighter scope: we forbid
    # apply_requested / apply_setup / _on_apply but NOT words like "applicable"
    # that are acceptable in prose-like identifiers.
    apply_variants = ("apply_requested", "apply_setup", "_on_apply", "applysetup")
    for token in apply_variants:
        assert token not in code_lower, (
            f"{_VIEW_MODULE} must not reference {token!r}")


def test_view_has_no_gearbox_command():
    """The view must not issue a gearbox command (only display advisory data)."""
    code = _code_only(_VIEW_MODULE)
    # "gearbox" as a gearbox command or control import is forbidden.
    # "gearbox_objectives" is in setup_workspace.py, not the view.
    assert "gearbox_command" not in code.lower(), (
        f"{_VIEW_MODULE} must not reference gearbox_command")
    assert "execute_pit" not in code.lower(), (
        f"{_VIEW_MODULE} must not reference execute_pit")


def test_view_has_module_docstring():
    import ast
    src = _src(_VIEW_MODULE)
    tree = ast.parse(src)
    assert ast.get_docstring(tree), f"{_VIEW_MODULE} must have a module docstring"


def test_view_parses():
    import ast
    src = _src(_VIEW_MODULE)
    ast.parse(src)   # raises SyntaxError if malformed


# ---------------------------------------------------------------------------
# No new telemetry listener
# ---------------------------------------------------------------------------

def test_no_telemetry_listener_in_new_modules():
    for rel in _NEW_MODULES:
        src = _src(rel)
        assert "recvfrom" not in src, f"{rel} must not call recvfrom"
        assert "GT7Packet" not in src, f"{rel} must not reference GT7Packet"
        assert "UDPListener" not in src, f"{rel} must not reference UDPListener"
