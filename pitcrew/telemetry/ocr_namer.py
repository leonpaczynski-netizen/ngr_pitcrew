"""Name a roster cluster by running Windows.Media.Ocr on its board crops.

### Why OCR, and why now

The roster matches bitmaps against hand-labelled exemplars.  That works for
returning drivers but leaves every new rival anonymous.  s213 (Monza, 21 Sep
2026) had five new rivals and zero of 868 board rows named: every stop was
filed under a phantom `Car #N` handle, and none could be traced to a person.

Windows.Media.Ocr is built into Windows 10/11 and needs no model download.
Measured against s213 and s188 groundtruth (the `winocr.ps1` run in the
groundtruth folder), it reads 90–94% of board rows correctly when matched
against the hub's closed vocabulary with difflib ratio ≥ 0.6.

### What it is and what it is not

**A tie-breaker between cluster and name, not a replacement for the bitmap
match.**  OCR is run on at most a few crops per cluster and its result is
voted on.  A cluster with a clear OCR winner gets that name; one where OCR
is split or silent stays anonymous until a person labels it.

**Off the capture thread.**  `note_crop()` buffers the native pixel crop per
cluster.  OCR is run in a `concurrent.futures.ThreadPoolExecutor` and the
result is applied via a callback.  The capture thread never blocks on I/O.

**Graceful degradation.**  If the winrt packages are unavailable (non-Windows
machine, incomplete install), this module logs one line and `OcrNamer.ready`
is `False`.  Nothing in the pit wall crashes; it falls back to exemplar
matching only.

### Cluster merge by OCR name

When two clusters are given the same OCR name they are the same driver.
`OcrNamer` calls back with the pair, and `PitWall` merges them the same way
`_merge_converged` does for bitmap drift — one identity for one car.

### Retroactive rename of phantom handles

When OCR resolves a cluster that was already given a `Car #N` handle, stops
filed under that handle in THIS session are renamed.  Past sessions' rows are
untouched.  The callback `on_rename(old_name, new_name)` carries that.
"""
from __future__ import annotations

import asyncio
import collections
import concurrent.futures
import difflib
import io
import logging
import re
import threading
from typing import Callable

import numpy as np

_log = logging.getLogger("pitcrew.telemetry.ocr_namer")

# A ratio below this is not a match.
FUZZY_MIN = 0.6
# The winner must lead the runner-up by at least this much, or the result is
# ambiguous and refused.  Keeps "Rocky" and "TommyTbone" from competing.
FUZZY_MARGIN = 0.05
# Vote N ≥ this many crops before accepting a name.
MIN_VOTES = 3
# Buffer at most this many crops per cluster.  After that, stop saving new
# ones — the vote is settled.
MAX_CROPS = 8
# Scale factor before OCR.  3× is what the groundtruth analysis used.
OCR_SCALE = 3

# Normalise a name or an OCR result to a key for fuzzy matching.
def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _engine():
    """The English OCR engine, or `None` if the winrt stack is unavailable."""
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.media.ocr import OcrEngine
        lang = Language("en-US")
        return OcrEngine.try_create_from_language(lang)
    except Exception as exc:
        _log.warning("pit-wall: OCR unavailable (%s) — falling back to "
                     "exemplar matching only", exc)
        return None


async def _ocr_bytes(engine, png_bytes: bytes) -> str:
    """Run OCR on a PNG image and return the text, or '' on failure."""
    try:
        from winrt.windows.graphics.imaging import BitmapDecoder
        from winrt.windows.storage.streams import DataWriter, InMemoryRandomAccessStream
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(png_bytes)
        await writer.store_async()
        stream.seek(0)
        dec = await BitmapDecoder.create_async(stream)
        sb = await dec.get_software_bitmap_async()
        result = await engine.recognize_async(sb)
        return (result.text or "").strip()
    except Exception as exc:
        _log.debug("pit-wall: OCR frame failed: %s", exc)
        return ""


def _crop_to_png(crop: np.ndarray) -> bytes:
    """Upscale a native pixel crop (H×W×3) by OCR_SCALE and encode as PNG."""
    from PIL import Image
    img = Image.fromarray(crop.astype("uint8"), mode="RGB")
    w, h = img.size
    img3 = img.resize((max(1, w * OCR_SCALE), max(1, h * OCR_SCALE)),
                      Image.BICUBIC)
    buf = io.BytesIO()
    img3.save(buf, format="PNG")
    return buf.getvalue()


def _fuzzy_match(text: str,
                 vocab: dict[str, str]) -> tuple[str | None, float]:
    """Best vocabulary match for `text`, or (None, 0.0) if below threshold.

    `vocab` maps normalised key → canonical name.  Returns the canonical name
    and its ratio.  Where the winner's margin over the runner-up is below
    `FUZZY_MARGIN` the result is refused — two names that look equally likely
    from one crop should not arbitrarily be awarded.
    """
    n = _norm(text)
    if not n or not vocab:
        return None, 0.0
    scores: list[tuple[float, str]] = []
    for key, name in vocab.items():
        ratio = difflib.SequenceMatcher(None, n, key).ratio()
        scores.append((ratio, name))
    scores.sort(key=lambda x: -x[0])
    best_r, best_n = scores[0]
    if best_r < FUZZY_MIN:
        return None, 0.0
    if len(scores) > 1:
        second_r = scores[1][0]
        if best_r - second_r < FUZZY_MARGIN:
            return None, 0.0
    return best_n, best_r


class OcrNamer:
    """Accumulate native crops per cluster, run OCR, vote, and name.

    Thread-safe: `note_crop` is called from the capture worker; callbacks are
    dispatched on a background thread from the ThreadPoolExecutor.

    Parameters
    ----------
    vocabulary:
        Every canonical name the OCR result may match against.  Should be the
        league's full driver-name list (hub.drivers().driver_name/psn_name).
    on_named:
        Called when a cluster has been named by OCR.
        `on_named(cluster_id, name, source, score, votes)`.
        `source` is always `'ocr'` from this class.
    on_merge:
        Called when two clusters share the same OCR name and should be merged.
        `on_merge(keep_id, drop_id, name)`.
    on_rename:
        Called when OCR resolves a cluster that already has a `Car #N` handle.
        `on_rename(old_name, new_name)` — the caller updates filed stops.
    own_cluster:
        The cluster id of the driver's own row.  Crops for this cluster are
        never OCR'd — the white own-plate reads inverted ("Seeni" for "Beeni").
    """

    def __init__(
        self,
        vocabulary: list[str],
        *,
        on_named: Callable | None = None,
        on_merge: Callable | None = None,
        on_rename: Callable | None = None,
        own_cluster: int | None = None,
    ) -> None:
        self._vocab: dict[str, str] = {}
        for name in vocabulary:
            if name:
                key = _norm(name)
                if key:
                    # **First seen wins.** When the archive has "K.Graebs" and
                    # the hub has "K_Graebs" they share the same normalised key.
                    # Keeping the first-seen (archive) spelling prevents OCR from
                    # relabelling a seeded driver with the hub's variant and
                    # splitting his archived rows from this session's.
                    # (Issue 4, 26 Sep 2026 coordinator replay review.)
                    if key not in self._vocab:
                        self._vocab[key] = name
        # Callbacks may be set after construction via these public attributes.
        self.on_named = on_named
        self.on_merge = on_merge
        self.on_rename = on_rename
        # **A separate resolution hook for the DB writer.** PitWall sets
        # `on_named`, `on_merge`, `on_rename` for its own roster updates.
        # The controller sets `on_resolution` to log every naming event to
        # `name_resolutions` without interfering with the wall's path.
        # Signature: on_resolution(cluster_id, name, source, score, votes).
        self.on_resolution: Callable | None = None
        self._own = own_cluster
        self._lock = threading.Lock()
        # cluster_id -> list of PNG bytes (up to MAX_CROPS)
        self._crops: dict[int, list[bytes]] = {}
        # cluster_id -> resolved name
        self._resolved: dict[int, str] = {}
        # OCR-name -> first cluster_id that claimed it (for merge detection)
        self._name_to_cluster: dict[str, int] = {}
        # cluster_id -> current roster name at the time of resolution
        self._prior_name: dict[int, str | None] = {}
        # **Session token — incremented by new_session().** Captured when a
        # task is submitted; checked at the start of _run_ocr before any
        # callback is fired.  An in-flight OCR task whose token differs from
        # the current one was queued for a session that is already over, and
        # its results must not flow into the new race (rule 11).
        self._session_token: int = 0
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="ocr-namer")
        self._engine = None
        self._engine_tried = False
        self.ready = False
        # Start engine init off the calling thread — the first OCR call will
        # wait for it, but the constructor never blocks.
        self._executor.submit(self._init_engine)

    def _init_engine(self) -> None:
        """Initialise the OCR engine once, in the worker thread."""
        self._engine = _engine()
        self.ready = self._engine is not None
        self._engine_tried = True
        if self.ready:
            _log.info("pit-wall: OCR engine ready (en-US)")

    # -- Public API ---------------------------------------------------------

    def add_vocabulary(self, names: list[str]) -> None:
        """Extend the vocabulary after construction (e.g. from the drivers DB)."""
        with self._lock:
            for name in names:
                if name:
                    key = _norm(name)
                    if key and key not in self._vocab:
                        self._vocab[key] = name

    def set_own_cluster(self, cluster_id: int | None) -> None:
        """Update the own-driver cluster id (may change during a race)."""
        with self._lock:
            self._own = cluster_id

    def note_crop(self, cluster_id: int, crop: np.ndarray,
                  roster_name: str | None = None) -> None:
        """Buffer one native pixel crop for this cluster.

        Called from the capture thread.  Buffers up to MAX_CROPS crops, then
        schedules an OCR run once MIN_VOTES are buffered.  After the vote is
        settled this becomes a no-op.  `crop` is H×W×3 uint8 from the frame.
        """
        token = None
        with self._lock:
            if cluster_id == self._own:
                return                          # own plate reads inverted
            if cluster_id in self._resolved:
                return                          # already named
            crops = self._crops.setdefault(cluster_id, [])
            if len(crops) >= MAX_CROPS:
                return
            if crop is None or crop.ndim != 3 or crop.size == 0:
                return
            # **Copy the array rather than encoding here** (issue 10, 26 Sep
            # 2026).  PNG encoding can take 85 ms and blocks the capture thread
            # while it holds the lock.  Store a compact uint8 copy; the worker
            # encodes it before calling OCR.
            try:
                raw = crop.astype("uint8", copy=True)
            except Exception:
                return
            crops.append(raw)
            self._prior_name[cluster_id] = roster_name
            # **Retry at 6 and 8 crops if still unresolved** (issue 8,
            # 26 Sep 2026).  Running once at MIN_VOTES=3 fails 31/145 in s213
            # and 11/151 in s188; more crops give more OCR material.  The first
            # try is at MIN_VOTES; retries at the next two thresholds.  Once
            # resolved, note_crop is a no-op (line above).
            RETRY_AT = (MIN_VOTES, 6, 8)
            n = len(crops)
            if n in RETRY_AT and cluster_id not in self._resolved:
                snapshot = list(crops)
                prior = roster_name
                token = self._session_token
        if token is not None:
            self._executor.submit(
                self._run_ocr, cluster_id, snapshot, prior, token)

    def resolved_name(self, cluster_id: int) -> str | None:
        """The OCR-resolved name, or `None` if not yet settled."""
        with self._lock:
            return self._resolved.get(cluster_id)

    def new_session(self) -> None:
        """Forget everything.  Called when a new race starts."""
        with self._lock:
            # **Increment before clearing** so any in-flight task that
            # checks the token under the lock after we release it sees the
            # new value and drops its result (rule 11).
            self._session_token += 1
            self._crops.clear()
            self._resolved.clear()
            self._name_to_cluster.clear()
            self._prior_name.clear()

    def shutdown(self) -> None:
        """Shut the executor down, bounded at 500 ms.

        ThreadPoolExecutor.shutdown has no timeout parameter, so we cancel
        pending work first (cancel_futures=True) then join the running future
        by waiting up to 0.5 s in a daemon thread before falling back to
        wait=False.  `wait=False` is safe here: the session token was already
        incremented by new_session, so any in-flight callback that fires after
        shutdown will see a stale token and discard its result.
        """
        import threading

        def _wait_bounded():
            # Give the one running OCR call ~500 ms to finish, then give up.
            # ThreadPoolExecutor has no timeout on shutdown; we join a daemon
            # thread that blocks so the main thread is never held up.
            self._executor.shutdown(wait=True, cancel_futures=True)

        t = threading.Thread(target=_wait_bounded, daemon=True, name="ocr-shutdown")
        t.start()
        t.join(timeout=0.5)
        if t.is_alive():
            _log.warning("ocr_namer: shutdown timed out, continuing without wait")
            self._executor.shutdown(wait=False)

    # -- Worker thread -------------------------------------------------------

    def _run_ocr(self, cluster_id: int, crops: list[bytes],
                 prior_name: str | None, token: int) -> None:
        """Run OCR on the buffered crops and apply the vote.

        Called in the ThreadPoolExecutor.  Never raises.

        `token` is the session token at the time this task was submitted.
        If `new_session()` has been called since, the token will not match
        and the results are discarded — an in-flight crop from the previous
        race must not name a cluster in the new one (rule 11).
        """
        # **Guard under the lock** so we do not race with new_session().
        with self._lock:
            if self._session_token != token:
                _log.debug(
                    "pit-wall: OCR cluster %d result dropped — session "
                    "changed (token %d → %d)", cluster_id, token,
                    self._session_token)
                return
        if not self.ready or self._engine is None:
            return
        try:
            # **Encode to PNG on the worker thread** (issue 10, 26 Sep 2026).
            # `note_crop` now stores raw uint8 numpy arrays; encode here so
            # the 85 ms encoding cost is off the 60 Hz capture thread.
            pngs: list[bytes] = []
            for raw in crops:
                try:
                    pngs.append(_crop_to_png(raw))
                except Exception as exc:
                    _log.debug("pit-wall: PNG encode failed for cluster %d: %s",
                               cluster_id, exc)
            if not pngs:
                return
            loop = asyncio.new_event_loop()
            try:
                results = loop.run_until_complete(
                    self._ocr_all(pngs))
            finally:
                loop.close()
        except Exception as exc:
            _log.debug("pit-wall: OCR run failed for cluster %d: %s",
                       cluster_id, exc)
            return
        self._apply_vote(cluster_id, results, prior_name)

    async def _ocr_all(self, crops: list[bytes]) -> list[str]:
        """Run OCR on each PNG-encoded crop and return the text results."""
        out = []
        for png in crops:
            text = await _ocr_bytes(self._engine, png)
            out.append(text)
        return out

    def _apply_vote(self, cluster_id: int, texts: list[str],
                    prior_name: str | None) -> None:
        """Tally OCR results and, if a winner is clear, name the cluster.

        A winner is the most-voted canonical name with a clear majority (more
        votes than any other candidate).  A tie refuses — two crops reading
        two different names is not one reading (rule 3).
        """
        candidates: dict[str, int] = collections.Counter()
        for text in texts:
            name, score = _fuzzy_match(text, self._vocab)
            if name:
                candidates[name] += 1
        if not candidates:
            _log.debug("pit-wall: OCR cluster %d — %d crops, no vocabulary "
                       "match in any", cluster_id, len(texts))
            return
        ranked = sorted(candidates.items(), key=lambda kv: -kv[1])
        winner_name, winner_votes = ranked[0]
        # **Require ≥ 2 agreeing non-blank votes** — a single crop match is not
        # a vote, it is a guess.  Cluster 26 in s188 was named on 1 match out of
        # 3 crops ('', '', 'Boxhead'); with min_votes=3 it felt like a majority
        # but it was 1/3. Two is the smallest number that says a second crop
        # agreed. (Issue 2b, 26 Sep 2026 coordinator replay review.)
        if winner_votes < 2:
            _log.debug("pit-wall: OCR cluster %d — winner %r has only %d "
                       "vote(s), need ≥ 2; refusing", cluster_id,
                       winner_name, winner_votes)
            return
        # **Refuse a tie or a split with two credible names.**
        # When a cluster was formed by a wrong bitmap merge of two different
        # drivers, the OCR crops will vote for both names.  A second candidate
        # with ≥ 2 votes is a sign the cluster holds two people; naming it
        # would assign the wrong identity to one of them.  Refuse and log so
        # the split can be tracked.  (Issue 3, 26 Sep 2026 coordinator review.)
        #
        # P3-3 analysis (26 Sep 2026): this branch IS reachable and must stay.
        # Proof: texts = ["Rocky", "Rocky", "TT", "TT"] gives candidates
        # {"Rocky": 2, "TT": 2}; winner_votes=2 passes the `< 2` guard above;
        # ranked[1][1]=2 ≥ 2 → this branch fires.  `test_tied_vote_is_refused`
        # in test_names_stops.py exercises this path.  The `len(ranked) > 1`
        # guard is also necessary: a sole winner with no runner-up short-circuits
        # rather than indexing ranked[1] out of bounds.
        if len(ranked) > 1 and ranked[1][1] >= 2:
            _log.info("pit-wall: OCR cluster %d — conflict: %r (%d) vs %r "
                      "(%d); cluster may hold two drivers; refusing",
                      cluster_id, winner_name, winner_votes,
                      ranked[1][0], ranked[1][1])
            return
        winner_score = max(
            difflib.SequenceMatcher(None, _norm(t), _norm(winner_name)).ratio()
            for t in texts if t)
        with self._lock:
            if cluster_id in self._resolved:
                return                          # another thread beat us
            self._resolved[cluster_id] = winner_name
            other = self._name_to_cluster.get(winner_name)
            self._name_to_cluster[winner_name] = cluster_id
        _log.info("pit-wall: OCR cluster %d -> %r (%d/%d votes, score %.2f)%s",
                  cluster_id, winner_name, winner_votes, len(texts),
                  winner_score,
                  f" (was {prior_name!r})" if prior_name else "")
        if self.on_named is not None:
            try:
                self.on_named(cluster_id, winner_name, "ocr",
                              winner_score, winner_votes)
            except Exception:
                _log.exception("pit-wall: OCR on_named callback raised")
        if self.on_resolution is not None:
            try:
                self.on_resolution(cluster_id, winner_name, "ocr",
                                   winner_score, winner_votes)
            except Exception:
                _log.exception("pit-wall: OCR on_resolution callback raised")
        if other is not None and other != cluster_id:
            _log.info("pit-wall: OCR merge — cluster %d and %d both read as "
                      "%r; merging", other, cluster_id, winner_name)
            if self.on_merge is not None:
                try:
                    self.on_merge(other, cluster_id, winner_name)
                except Exception:
                    _log.exception("pit-wall: OCR on_merge callback raised")
            # **Record the merge in name_resolutions** (issue 9, 26 Sep 2026).
            # The controller docstring promised named/merge/rename; only named
            # was written.
            if self.on_resolution is not None:
                try:
                    self.on_resolution(other, winner_name, "ocr-merge",
                                       winner_score, winner_votes)
                except Exception:
                    _log.exception("pit-wall: OCR on_resolution (merge) raised")
        # **Retroactive rename of phantom handles.** A `Car #N` handle is one
        # this app minted because the exemplar bank had no match.  When OCR
        # resolves it to a real name, any stops filed under the old handle in
        # this session should carry the corrected name.  The callback carries
        # both names; the coordinator renames the DB rows.
        if (prior_name and prior_name != winner_name
                and _is_phantom(prior_name)):
            _log.info("pit-wall: renaming phantom %r -> %r for cluster %d",
                      prior_name, winner_name, cluster_id)
            if self.on_rename is not None:
                try:
                    self.on_rename(prior_name, winner_name)
                except Exception:
                    _log.exception("pit-wall: OCR on_rename callback raised")
            # **Record the rename in name_resolutions** (issue 9).
            if self.on_resolution is not None:
                try:
                    self.on_resolution(cluster_id, winner_name, "ocr-rename",
                                       winner_score, winner_votes)
                except Exception:
                    _log.exception("pit-wall: OCR on_resolution (rename) raised")


def _is_phantom(name: str) -> bool:
    """True for a handle minted by the app, e.g. 'Car #3' or 'F#7'."""
    return bool(re.match(r"^(Car #|F#)\d+$", name))
