"""The rollback has to be writable, and for one evening it was not.

`wind-reflash.sh` backs the board up with `avrdude -U flash:r:...`, which
reads the whole 32 KB - bootloader included. Restoring that through the
`arduino` programmer asks the bootloader to overwrite itself. It refuses,
correctly, and avrdude reports:

    stk500_paged_write(): (a) protocol error, expect=0x14, resp=0x62

**Measured 6 Sep 2026 on the real board.** Nothing was damaged - the
application region had already been written and a bootloader that will not
erase itself is doing its job - but the restore reported failure, could not
verify, and left the board not answering avrdude until it was power-cycled.
A rollback that looks like it failed is not one anybody trusts before a race,
which is the entire reason it exists.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.trim_bootloader import APPLICATION_END, EOF_RECORD, trim

BACKUP = Path("reference/simhub-baseline/redion-flash-backup-20260906-124639.hex")


def record(address: int, payload: str = "00" * 32) -> str:
    """One data record. The checksum is not computed - nothing here reads it,
    and a wrong one would be caught by avrdude rather than by this."""
    length = len(payload) // 2
    return f":{length:02X}{address:04X}00{payload}FF"


def test_records_below_the_boundary_are_kept():
    kept, dropped = trim([record(0x0000), record(0x1000), record(0x7DE0)])
    assert len(kept) == 3
    assert dropped == 0


def test_records_at_and_above_the_boundary_are_dropped():
    """0x7E00 is the first byte of an Uno's optiboot, so it is the first
    byte that must not be written."""
    kept, dropped = trim([record(0x7E00), record(0x7FE0)])
    assert kept == []
    assert dropped == 2


def test_the_boundary_itself_is_excluded_not_included():
    kept, _ = trim([record(APPLICATION_END - 0x20), record(APPLICATION_END)])
    assert len(kept) == 1, "the boundary record was kept, which is the defect"


def test_the_old_eof_is_dropped_because_a_fresh_one_is_written():
    """Left in place it would sit in the middle of the trimmed file, and
    everything after it is ignored by anything reading the hex."""
    kept, _ = trim([record(0x0000), EOF_RECORD, record(0x1000)])
    assert all(line[7:9] == "00" for line in kept)
    assert len(kept) == 2


def test_extended_address_records_are_dropped_and_counted():
    """An ATmega328P is 32 KB, so a full-flash read never needs one. A hex
    that carries one is not the file this was written for, and silently
    keeping it would make every following address wrong."""
    kept, dropped = trim([":02000004FFFFFC", record(0x0100)])
    assert len(kept) == 1
    assert dropped == 1


def test_junk_between_records_is_ignored():
    kept, _ = trim(["", "  ", "# a comment", record(0x0000), "\n"])
    assert len(kept) == 1


@pytest.mark.skipif(not BACKUP.exists(), reason="the board backup is not here")
def test_the_real_backup_loses_exactly_the_bootloader():
    """**The rollback actually on disk**, which is the one that matters.

    512 bytes of optiboot at 32 bytes a record is 16 records, and what is
    left must end just below the boundary.
    """
    kept, dropped = trim(BACKUP.read_text(encoding="ascii").splitlines())
    assert dropped == 16, f"dropped {dropped} records, expected 16 (512 bytes)"
    assert len(kept) == 1008

    last = int(kept[-1][3:7], 16)
    assert last == APPLICATION_END - 0x20, (
        f"the last kept record starts at {last:#06x}; the application region "
        f"should run right up to {APPLICATION_END:#06x}")
