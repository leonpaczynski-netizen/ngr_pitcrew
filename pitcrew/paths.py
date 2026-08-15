"""Where the app's own files live.

Every path here is resolved against this package rather than against the working
directory.  The shortcut that launches Pit Crew runs `pythonw`, and a shortcut
with no "Start in" set inherits whatever directory the shell happened to be in:
with `data/` read relative to that, `catalogs` returned zero tracks, zero cars
and zero slider presets, and `Store` created a fresh empty database beside them.
Nothing raised — `catalogs._read` treats a missing file as an absent section, by
design — so the app came up looking installed and knowing nothing.
"""
from __future__ import annotations

from pathlib import Path

# pitcrew/paths.py -> pitcrew/ -> the checkout.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
