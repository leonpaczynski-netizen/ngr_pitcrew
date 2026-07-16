"""Atomic JSON file writes (shared helper).

Several modules persist JSON that the running UI reads back — accepted track
models, station maps, scraped car/BoP data. A plain ``open(...,'w')`` +
``json.dump`` that is interrupted mid-flush (app close, crash, disk full) leaves
a truncated, unparseable file. This helper writes to a temp sibling, fsyncs, and
``os.replace``s it into place (atomic on the same filesystem), keeping a ``.bak``
snapshot of the prior good file — the same discipline as ``config_paths.save_config``.
"""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


def atomic_write_json(path, obj, *, indent: int = 2, ensure_ascii: bool = True) -> Path:
    """Serialise ``obj`` to ``path`` as JSON atomically. Returns the path.

    Copies any existing file to ``<name>.bak`` first (so the target is never
    momentarily absent), writes ``<name>.tmp`` + fsync, then ``os.replace``.
    On failure the temp file is cleaned up and the original is left intact.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, indent=indent, ensure_ascii=ensure_ascii)
    if p.exists():
        try:
            shutil.copy2(p, p.with_name(p.name + ".bak"))
        except Exception:
            pass
    tmp = p.with_name(p.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        raise
    return p
