"""Cut the bootloader region out of a full-flash Intel hex, for restoring.

**The defect this fixes, found 6 Sep 2026 with the board on the bench.**
`wind-reflash.sh` takes its backup with `avrdude -U flash:r:...` which reads
the WHOLE 32 KB, bootloader included. Restoring that image through the
`arduino` programmer then asks the bootloader to overwrite itself, and it
will not:

    stk500_paged_write(): (a) protocol error, expect=0x14, resp=0x62
    stk500_paged_load(): (a) protocol error, expect=0x14, resp=0x10

The board survived - a bootloader refusing to erase itself is correct
behaviour, and the application region had already been written - but the
restore reported failure, could not verify, and left the board unreachable
by avrdude until it was power-cycled. A rollback that looks like it failed
is not a rollback anyone will trust at 11pm before a race.

So the image is trimmed to the application region before it is written.

**The boundary.** An Uno's optiboot lives in the top 512 bytes, so the
application region ends at 0x7E00. That is set by the BOOTSZ fuses rather
than by anything readable here, and 512 bytes is the Uno default; a board
with a larger bootloader would need a lower figure. Trimming too LOW is
safe (it just leaves some of the old application in place, which the next
write replaces); trimming too HIGH is what causes the error above.
"""
from __future__ import annotations

import sys

# Optiboot on an Uno: 512 bytes at the top of 32 KB.
APPLICATION_END = 0x7E00

EOF_RECORD = ":00000001FF"


def trim(lines, *, end: int = APPLICATION_END):
    """Records below `end`, then a fresh EOF. Anything else is dropped.

    Extended-address records (type 02/04) are dropped rather than tracked:
    an ATmega328P is 32 KB, so a full-flash read never needs them, and a hex
    that carries one is not the file this was written for.
    """
    kept, dropped = [], 0
    for line in lines:
        line = line.strip()
        if not line.startswith(":"):
            continue
        record_type = line[7:9]
        if record_type == "01":          # EOF, re-emitted below
            continue
        if record_type != "00":          # not a data record
            dropped += 1
            continue
        address = int(line[3:7], 16)
        if address >= end:
            dropped += 1
            continue
        kept.append(line)
    return kept, dropped


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: trim_bootloader.py <in.hex> <out.hex>", file=sys.stderr)
        return 2
    source, target = argv[1], argv[2]
    with open(source, encoding="ascii") as handle:
        kept, dropped = trim(handle)
    if not kept:
        print(f"{source} has no application-region data - refusing to write "
              f"an empty image", file=sys.stderr)
        return 1
    with open(target, "w", encoding="ascii", newline="\n") as handle:
        for line in kept:
            handle.write(line + "\n")
        handle.write(EOF_RECORD + "\n")
    print(f"kept {len(kept)} records below {APPLICATION_END:#06x}, "
          f"dropped {dropped}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
