"""Small results worked out from a lap's stored frames, remembered by content.

**Why it exists.** Arming the qualifying coach decodes the event's recent lap
blobs twice over - fifteen for the temperature window, one or more for the
reference curve - at ~50 ms a blob, on the Practice button: 0.5 s for a
176-lap event, every start, to reach the same two answers from the same
bytes. The race arm reads the same temperature window. A lap's frames are
written once and are only ever replaced wholesale by an offline tool, so the
answer for a given lap is a pure function of the bytes stored for it.

**Keyed on the bytes, not on the lap id.** The key is the lap id, the CRC-32
and length of the stored blob, its sample rate and frame count, and the name
of the derivation. A lap rewritten by `tools/reaggregate.py` (or anything
else) has different bytes, misses, and is worked out again - there is nothing
to invalidate and no way for a stale answer to be served, which is also why
this cannot carry state from one session into the next (CLAUDE.md rule 11):
nothing session-shaped is in the key or the value. Reading the blob to hash it
costs a few milliseconds; decoding it is what costs fifty.

**Only immutable results go in.** A tuple of floats, a frozen dataclass. The
decoded frames themselves are NOT kept - a lap is ~6,000 dicts, ~20 MB of
Python objects - only what was worked out from them.

`prefetch` is the other half: the same derivations run on a background thread
while the app idles, so the button finds them already done.
"""
from __future__ import annotations

import threading
import zlib
from collections import OrderedDict

from pitcrew.diagnostics import log

# Enough for every lap of the largest event on file several times over; each
# entry is a few hundred bytes (a reference curve is two tuples of ~6,000
# floats, ~100 KB - there is one per event, not one per lap).
MAX_ENTRIES = 2048

# What `derived` returns for a lap that has no frames stored at all, which is
# not the same answer as a derivation that ran and found nothing (None).
NO_FRAMES = object()

_MEMO: OrderedDict = OrderedDict()
_LOCK = threading.Lock()
_STATS = {"hits": 0, "misses": 0}


def derived(store, lap_id: int, name, compute):
    """`compute(stored)` for this lap's stored frames, or `NO_FRAMES`.

    `stored` is exactly what `Store.get_lap_frames` returns. `name` must say
    everything about `compute` that its result depends on beyond the bytes -
    it is part of the key. Never serves an answer for different bytes.
    """
    row_of = getattr(store, "lap_frames_row", None)
    if row_of is None:
        # A store double without the raw accessor: no memory, same answer.
        stored = store.get_lap_frames(lap_id)
        return NO_FRAMES if not stored else compute(stored)
    row = row_of(lap_id)
    if row is None:
        return NO_FRAMES
    blob = row["blob"]
    key = (int(lap_id), zlib.crc32(blob), len(blob), row["sample_hz"],
           row["frame_count"], name)
    with _LOCK:
        if key in _MEMO:
            _MEMO.move_to_end(key)
            _STATS["hits"] += 1
            return _MEMO[key]
    _STATS["misses"] += 1
    value = compute(store.decode_lap_frames_row(row))
    with _LOCK:
        _MEMO[key] = value
        _MEMO.move_to_end(key)
        while len(_MEMO) > MAX_ENTRIES:
            _MEMO.popitem(last=False)
    return value


def stats() -> dict:
    """Hit and miss counts since the process started. For tests and logs."""
    with _LOCK:
        return dict(_STATS, entries=len(_MEMO))


def clear() -> None:
    with _LOCK:
        _MEMO.clear()
        _STATS["hits"] = _STATS["misses"] = 0


def prefetch(work, *, name: str) -> threading.Thread:
    """Run `work()` on a daemon thread to fill the memo; log, never raise.

    The results are thrown away - the point is the entries `derived` leaves
    behind, which the Qt thread then finds instead of decoding.
    """
    def run() -> None:
        try:
            work()
        except Exception:                                    # noqa: BLE001
            log("pitcrew").warning("prefetch %s failed - the button will "
                                   "work it out itself", name, exc_info=True)

    thread = threading.Thread(target=run, name=f"prefetch-{name}",
                              daemon=True)
    thread.start()
    return thread
