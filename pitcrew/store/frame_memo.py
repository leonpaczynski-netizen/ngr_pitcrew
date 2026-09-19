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

**One decode per key, however many threads ask.** A prefetch started by a
stop or an event switch can still be running when the next Start or race arm
asks for the same laps. Without care both would decode the same blob at once
and fight for the interpreter: the second asker of a key that is being worked
out WAITS for that answer (`IN_FLIGHT_WAIT_S`, then works it out itself if the
first asker failed or stalled). And a prefetch can be stood down
(`Prefetch.cancel`) - the session start does, first thing, so a prefetch never
decodes beside a live session: it finishes the one blob it is on and stops.
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

# How long a second asker waits for a key another thread is working out. One
# blob decodes in ~50 ms; this is a backstop for a worker that stalled, after
# which the asker decodes it itself rather than hang the button.
IN_FLIGHT_WAIT_S = 5.0

_MEMO: OrderedDict = OrderedDict()
_LOCK = threading.Lock()
# key -> Event set when the thread working that key out is done with it.
_IN_FLIGHT: dict = {}
_STATS = {"hits": 0, "misses": 0, "waits": 0}
# The prefetch a thread is running, if it is a prefetch thread - so
# `derived` can tell a stood-down prefetch to stop before its next decode.
_THREAD = threading.local()


class PrefetchCancelled(Exception):
    """Raised inside a stood-down prefetch before it decodes anything more."""


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
    mine = None
    with _LOCK:
        if key in _MEMO:
            _MEMO.move_to_end(key)
            _STATS["hits"] += 1
            return _MEMO[key]
        _stop_if_stood_down()
        pending = _IN_FLIGHT.get(key)
        if pending is None:
            mine = _IN_FLIGHT[key] = threading.Event()
    if mine is None:
        # Another thread is decoding these very bytes: wait for its answer
        # rather than decode them beside it.
        _STATS["waits"] += 1
        pending.wait(IN_FLIGHT_WAIT_S)
        with _LOCK:
            if key in _MEMO:
                _MEMO.move_to_end(key)
                return _MEMO[key]
            _stop_if_stood_down()
        # It failed, or stalled past the backstop: work it out here.
        return _compute(store, row, key, compute)
    try:
        return _compute(store, row, key, compute)
    finally:
        with _LOCK:
            _IN_FLIGHT.pop(key, None)
        mine.set()


def _compute(store, row, key, compute):
    _STATS["misses"] += 1
    frames = store.decode_lap_frames_row(row)
    # And again between the decode and the derivation: a stood-down prefetch
    # does not go on to work out an answer nobody is waiting for. Measured
    # 0.8 s after a stop on event 1, it was still in `lap_axle_means` 220 ms
    # after the Start. Whoever waits on this key works it out itself.
    _stop_if_stood_down()
    value = compute(frames)
    with _LOCK:
        _MEMO[key] = value
        _MEMO.move_to_end(key)
        while len(_MEMO) > MAX_ENTRIES:
            _MEMO.popitem(last=False)
    return value


def _stop_if_stood_down() -> None:
    """Raise `PrefetchCancelled` on a prefetch thread that has been stood
    down. Checked before every decode, never in the middle of one."""
    running = getattr(_THREAD, "prefetch", None)     # thread-local: unset
    if running is not None and running.cancelled:    # on non-prefetch threads
        raise PrefetchCancelled(running.name)


def stats() -> dict:
    """Hit and miss counts since the process started. For tests and logs."""
    with _LOCK:
        return dict(_STATS, entries=len(_MEMO))


def clear() -> None:
    with _LOCK:
        _MEMO.clear()
        _STATS["hits"] = _STATS["misses"] = _STATS["waits"] = 0


class Prefetch(threading.Thread):
    """A daemon thread filling the memo, which can be stood down."""

    def __init__(self, work, name: str) -> None:
        super().__init__(name=f"prefetch-{name}", daemon=True)
        self._work = work
        self.cancelled = False

    def cancel(self) -> None:
        """Stop before the next decode. Does not wait: the blob in hand
        (~50 ms) is finished and filed, and anyone waiting on it gets it."""
        self.cancelled = True

    def run(self) -> None:
        _THREAD.prefetch = self
        try:
            self._work()
        except PrefetchCancelled:
            log("pitcrew").info("%s stood down for a session start",
                                self.name)
        except Exception:                                    # noqa: BLE001
            log("pitcrew").warning("%s failed - the button will work it out "
                                   "itself", self.name, exc_info=True)
        finally:
            _THREAD.prefetch = None


def prefetch(work, *, name: str) -> Prefetch:
    """Run `work()` on a daemon thread to fill the memo; log, never raise.

    The results are thrown away - the point is the entries `derived` leaves
    behind, which the Qt thread then finds instead of decoding.
    """
    thread = Prefetch(work, name)
    thread.start()
    return thread
