"""Superseded by `tools/repair_in_out_laps.py` (15 Sep 2026).

    python tools/reaggregate.py --db PATH [--apply]

This tool wrote `is_pit_lap` and `is_out_lap` from the frames, and wrote BOTH
columns on every lap it found, so it cleared the out-lap flag on any in-lap
that also carried one - which is the marker `race.pit_loss` reads to know a
row holds both halves of a stop. The frames reading it used now lives in
`pitcrew/analysis/reaggregate.py` with the in-lap defined by what happened,
and the only writer is the repair tool, which never clears an out-lap. This
name is kept so an old command line still reaches the right code.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.repair_in_out_laps import main   # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
