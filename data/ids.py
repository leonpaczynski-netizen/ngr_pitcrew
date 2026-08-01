"""Canonical identity primitives for the NGR Pit Crew data spine (Program 3).

Program 3 introduces one authoritative identity that flows through the database,
UI, telemetry, Engineer, strategy, setup history and learning systems. That
identity is a **UUIDv7** (RFC 9562) — time-ordered, so a natural ``ORDER BY uuid``
reproduces chronological order (the property that lets us later repoint the ~50
legacy ``ORDER BY id`` / ``MAX(id)`` "latest row" queries onto the uuid without
changing their meaning).

This module is deliberately tiny, pure and dependency-free so every layer can
mint or reason about an id without importing the DB. Two entry points:

* ``new_id()``      — a fresh v7 stamped with the current time (for new rows).
* ``backfill_id()`` — a v7 with an explicit millisecond timestamp, used ONLY by
  the v32 migration to give pre-existing rows a uuid whose sort order matches
  their original chronology.
"""

from __future__ import annotations

import os
import uuid

__all__ = ["new_id", "backfill_id"]


def new_id() -> str:
    """Return a fresh canonical UUIDv7 (time-ordered) as a 36-char string."""
    return str(uuid.uuid7())


def backfill_id(unix_ms: int) -> str:
    """Build a UUIDv7 carrying an explicit 48-bit millisecond timestamp.

    Used only to backfill rows that pre-date the identity spine. The migration
    passes a **strictly increasing** ``unix_ms`` per table batch, so the 48-bit
    time field alone determines ``ORDER BY uuid`` and reproduces the rows'
    original ``(date, id)`` order; the remaining bits are random purely for
    uniqueness. Layout follows RFC 9562 §5.7 (unix_ts_ms | ver=7 | rand_a |
    var | rand_b).
    """
    ts = int(unix_ms) & ((1 << 48) - 1)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF          # 12 bits
    rand_b = int.from_bytes(os.urandom(8), "big") & ((1 << 62) - 1)  # 62 bits
    value = (
        (ts << 80)
        | (0x7 << 76)      # version 7
        | (rand_a << 64)
        | (0b10 << 62)     # variant (RFC 4122)
        | rand_b
    )
    return str(uuid.UUID(int=value))
