"""Pure helpers for structured car-setup naming (Group D).

Saved setups are named '<Q|R> <event name> <number>', e.g. "Q NGR Enduro Rd1 3"
(the 3rd qualifying setup tried for event "NGR Enduro Rd1"). These functions are
pure (no Qt, no I/O) so the naming/numbering logic is unit-testable on its own.
"""
from __future__ import annotations

import re


def setup_display_label(s: dict) -> str:
    """Return the user-facing name for a saved setup.

    The user's setup name is stored in ``setup_label`` (e.g. "R NGR Porsche
    Cup Rd7 2"); the legacy ``name`` field actually holds the *car* name. Any
    place that shows a setup to the user must prefer ``setup_label`` so the
    displayed name matches what was typed in the Setup Builder. Falls back to
    ``name`` (then empty) for pre-label records.
    """
    if not isinstance(s, dict):
        return ""
    return (s.get("setup_label") or s.get("name") or "").strip()


def build_setup_name(prefix: str, event_name: str, n: int) -> str:
    """Build the structured setup name, e.g. 'Q NGR Enduro Rd1 3'."""
    return f"{prefix} {event_name} {n}"


def is_structured_name(label: str, event_name: str) -> bool:
    """True if ``label`` is a system-generated structured name for ``event_name``.

    Matches '<Q|R> <event_name> <digits>' exactly (either prefix). Used to decide
    whether a label is system-managed (and should advance to the next number on
    save) versus a manual/freeform name the user typed (kept as-is).
    """
    if not event_name:
        return False
    return bool(re.fullmatch(rf"[QR] {re.escape(event_name)} \d+", (label or "").strip()))


def resolve_save_name(
    current_label: str,
    prefix: str,
    event_name: str,
    saved_setups: list[dict],
) -> str:
    """Resolve the label to store when saving a setup (D-RESAVE).

    A structured auto-name (or an empty field) becomes the NEXT numbered attempt for
    the current prefix+event, so saving a freshly-prefilled or previously-loaded
    structured setup always creates a new numbered entry instead of overwriting.
    A manual/freeform name is preserved exactly as the user typed it.
    """
    cur = (current_label or "").strip()
    if event_name and (cur == "" or is_structured_name(cur, event_name)):
        return build_setup_name(
            prefix, event_name, next_setup_number(saved_setups, prefix, event_name)
        )
    return cur


def next_setup_number(saved_setups: list[dict], prefix: str, event_name: str) -> int:
    """Return the next sequence number for setups named '<prefix> <event_name> <n>'.

    Counts only the loadable saved setups whose ``setup_label`` EXACTLY matches the
    pattern (so "NGR Enduro Rd1" and "NGR Enduro Rd10" never cross-count, and old
    freeform labels are ignored). Returns max matched number + 1, or 1 if none match
    or the event name is blank.
    """
    if not event_name:
        return 1
    pat = re.compile(rf"^{re.escape(prefix)} {re.escape(event_name)} (\d+)$")
    best = 0
    for s in saved_setups or []:
        if not isinstance(s, dict):
            continue
        label = (s.get("setup_label") or "").strip()
        m = pat.match(label)
        if m:
            best = max(best, int(m.group(1)))
    return best + 1
