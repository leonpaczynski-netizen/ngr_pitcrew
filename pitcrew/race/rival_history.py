"""Rival race history: normalise, store, clean up, and profile.

Written by the cleanup gate before `board_reads` and `name_resolutions` are
deleted.  One row per rival per race session in `rival_race_history`.

### What "due for cleanup" means

A race session is due when it has ended (sessions.ended_at IS NOT NULL), it
is not a rehearsal, AND the session ended at least `_CLEANUP_MIN_AGE_MINUTES`
minutes ago (guards against trailing board_reads writes from the sampler
thread), AND EITHER:

* `sessions.debriefed_at` is set (the race engineer ran the debrief), OR
* more than 14 days have elapsed since `sessions.ended_at`.

A session that is still running (ended_at NULL) is never due.  A rehearsal
(`sessions.rehearsal = 1`) never qualifies.

### Safety — RH-I1

Normalisation, verification and deletion happen in **one transaction**.
`_collect_all_rows` builds every history row dict in memory without writing.
`_run_cleanup_for_session` then opens a single `store._write()` block and
performs all three steps inside it.  If any step raises, the whole
transaction rolls back and nothing is deleted.  `history_compacted_at` is
set only after the transaction commits successfully — it is the idempotency
guard.

### Board_reads names — RH-I2

Drivers seen ONLY in `board_reads` (never in `board_positions` or
`rival_stops`) are included in both the normalise driver set and the verify
count.  A driver with board_reads evidence but no stop or position data
receives a history row with NULL position/stop fields but a non-NULL
`board_reads_n`, so their evidence is preserved before the board_reads rows
are deleted.

### Rule compliance

* Missing is NULL, never 0 (rule 3).
* No clamping (rule 9).
* Every aggregate carries its count (rule 4).
* Derived figures are [DERIVED] in code comments and in the schema (rule 5).
* Two calls using the same words use the same expression (rule 13):
  burn via `fill_verdict.derive_stop_burn`; gap slope via `GapTrend`.
"""
from __future__ import annotations

import datetime
import json
import logging
import re
import sqlite3
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pitcrew.store.db import Store

_CLEANUP_DAYS = 14          # fallback if never debriefed
# RH-I5: guard against trailing board_reads writes from the sampler thread.
# A session must have ended at least this many minutes ago before cleanup runs.
_CLEANUP_MIN_AGE_MINUTES = 10
# RH-I5: single-flight guard — only one cleanup pass at a time.
_CLEANUP_LOCK = threading.Lock()

_LOG = logging.getLogger("rival_history")


# Minimum consecutive laps for a gap trend to count (mirrors GapTrend).
# Imported from gaps.py to avoid duplicating the constant (rule 13).
def _min_laps_for_trend() -> int:
    try:
        from pitcrew.race.gaps import MIN_LAPS_FOR_TREND
        return MIN_LAPS_FOR_TREND
    except Exception:
        return 5


def _is_phantom(name: str) -> bool:
    """True for app-minted phantom handles such as 'Car #3' or 'F#7'."""
    return bool(re.match(r"^(Car #|F#)\d+$", name))


# ---------------------------------------------------------------------------
# Due-for-cleanup predicate
# ---------------------------------------------------------------------------

def is_race_session_due(session: dict, race_runs: list[dict],
                        now: datetime.datetime) -> tuple[bool, str | None]:
    """Is this session due for cleanup?  Returns (due, reason_or_None).

    `session` is a `sessions` row dict.  `race_runs` is the list of
    `race_runs` rows for the session (may be empty).  `now` is timezone-naive
    UTC.

    A session is due when ALL of:
    * kind == 'race'
    * rehearsal is falsy
    * it has ended (ended_at is not NULL)
    * it ended at least _CLEANUP_MIN_AGE_MINUTES ago (RH-I5)
    * it has not already been compacted (history_compacted_at is NULL)
    AND either:
    * debriefed_at is set, OR
    * more than _CLEANUP_DAYS days have elapsed since ended_at.
    """
    if session.get("kind") != "race":
        return False, None
    if session.get("rehearsal"):
        return False, None
    if not session.get("ended_at"):
        return False, None
    if session.get("history_compacted_at"):
        return False, None      # already done

    ended_at_str = session["ended_at"]
    try:
        ended_at = datetime.datetime.fromisoformat(
            ended_at_str.replace("Z", "+00:00")
        ).replace(tzinfo=None)
    except (ValueError, AttributeError):
        # Malformed timestamp — cannot decide; skip rather than guess.
        return False, None

    # RH-I5: session must have ended at least _CLEANUP_MIN_AGE_MINUTES ago.
    # This prevents a cleanup from racing the sampler thread's last board_reads
    # write, which can land a few seconds after stop_race is called.
    age_total = now - ended_at
    if age_total.total_seconds() < _CLEANUP_MIN_AGE_MINUTES * 60:
        return False, None

    if session.get("debriefed_at"):
        return True, "debriefed"

    if age_total.days >= _CLEANUP_DAYS:
        return True, f"{age_total.days} days since ended (fallback)"

    return False, None


# ---------------------------------------------------------------------------
# Gap slope helper
# ---------------------------------------------------------------------------

def _gap_slope_for_driver(gap_reads: list[dict], driver: str
                          ) -> tuple[float | None, int | None]:
    """[DERIVED] Gap trend slope (s/lap) and lap count for one driver.

    Replays `gap_reads` rows attributed to `driver` into a GapTrend and asks
    for the closing rate.  Returns (slope, n) where slope is positive if we
    were closing, or (None, n_observed) where the noise gate refuses.

    The 'subject' column carries driver names for newer sessions; for older
    ones it may be a bare integer roster id.  We match only on the exact
    string — an integer string never equals a name, so old rows are silently
    skipped.
    """
    from pitcrew.race.gaps import GapTrend  # import here; gaps imports calls

    trend = GapTrend(side="ahead")   # side only affects the caller's sentence
    for row in gap_reads:
        if str(row.get("subject") or "") != driver:
            continue
        trend.note(row.get("lap"), row.get("gap_s"), subject=driver)

    rate, n = trend.closing_s_per_lap()
    if rate is None or n < _min_laps_for_trend():
        # n is always an int from closing_s_per_lap; use None only for truly
        # empty (0 laps, no evidence at all).
        return None, (n if n > 0 else None)
    return rate, n


# ---------------------------------------------------------------------------
# Pit-window counter (from board_reads pit_columns)
# ---------------------------------------------------------------------------

def _count_pit_windows(board_rows: list[dict],
                       gap_s: float = 60.0) -> int | None:
    """[DERIVED] Count distinct pit visit windows in board_reads rows.

    A new window starts whenever pit_columns transitions from 0 to 1, or when
    more than `gap_s` seconds have elapsed since the previous pit row.  Returns
    None when board_rows is empty (not 0, which would claim "we looked and saw
    nothing").
    """
    if not board_rows:
        return None
    windows = 0
    in_pit = False
    last_pit_s: float | None = None
    for row in board_rows:
        at_s = row.get("at_s")
        pit = bool(row.get("pit_columns"))
        if pit:
            new_window = (
                not in_pit
                or last_pit_s is None
                or (at_s is not None and at_s - last_pit_s > gap_s)
            )
            if new_window:
                windows += 1
            in_pit = True
            last_pit_s = at_s
        else:
            in_pit = False
    return windows if windows > 0 else None


# ---------------------------------------------------------------------------
# Seconds-in-view helper — RH-I3
# ---------------------------------------------------------------------------

def _secs_in_view_from_reads(board_rows: list[dict]) -> float | None:
    """[DERIVED] Seconds driver was visible, from board_reads at_s timestamps.

    Sums the gaps between consecutive at_s readings while the driver was
    present on the board.  Each interval is capped at 2× the median interval
    so that a view gap (board hidden, driver off screen) does not inflate the
    total.  The model is: driver was continuously in view for each inter-read
    interval up to the cap; larger gaps mean the board was away.

    Returns None when fewer than two timestamped rows exist (rule 3).
    """
    timestamps = sorted(
        r["at_s"] for r in board_rows if r.get("at_s") is not None
    )
    if len(timestamps) < 2:
        return None
    intervals = [timestamps[i + 1] - timestamps[i]
                 for i in range(len(timestamps) - 1)]
    si = sorted(intervals)
    n = len(si)
    if n % 2 == 1:
        median_iv = si[n // 2]
    else:
        median_iv = (si[n // 2 - 1] + si[n // 2]) / 2.0
    cap = 2.0 * median_iv if median_iv > 0 else 2.0
    total = sum(min(iv, cap) for iv in intervals)
    return total if total > 0 else None


# ---------------------------------------------------------------------------
# Row collection — pure computation, no writes
# ---------------------------------------------------------------------------

def _collect_all_rows(store: "Store", session_id: int
                      ) -> tuple[list[tuple[str, dict]], dict]:
    """Build all `rival_race_history` row dicts for this session.

    Returns (rows, context) where:
    * rows  — list of (driver, row_dict) pairs, one per rival
    * context — the race-level metadata dict (series, circuit_key, …) that
      the caller appends to each row

    Does **no writes**.  All store._query() calls happen here so that the
    caller can enter a single _write() transaction to insert everything.

    Raises on any unrecoverable error so the caller can abort the transaction
    before deleting anything.
    """
    session = store.get_session(session_id)
    if session is None:
        return [], {}

    # Pull the event for race context.
    events = store._query(                        # type: ignore[attr-defined]
        "SELECT e.* "
        "FROM events e "
        "JOIN sessions s ON s.event_id = e.id "
        "WHERE s.id = ?", (session_id,))
    if not events:
        return [], {}
    event = dict(events[0])

    # Circuit key.
    circuit_key: str | None = None
    try:
        from pitcrew.analysis.resolve import circuit_key as _ck  # noqa: PLC0415
        track = event.get("track") or ""
        layout = event.get("layout")
        circuit_key = _ck(track, layout) if track else None
    except Exception:
        circuit_key = None

    race_laps: int | None = event.get("race_laps")
    is_timed: int = 1 if event.get("race_type") == "time" else 0
    race_date: str | None = (
        str(session["started_at"])[:10] if session.get("started_at") else None)
    series: str | None = event.get("series")
    car_name: str | None = event.get("car_name")
    fuel_capacity_l: float | None = session.get("fuel_capacity_l")

    # [DERIVED] Actual laps run — the leader's lap count as a lower bound.
    # For a timed race, `race_laps` is the lap CAP (e.g. 50) not what ran
    # (e.g. 29).  MAX(lap_num) in our own laps table is a sound lower bound
    # since the leader may have run one more lap than we did.
    race_laps_run: int | None = None
    try:
        rows = store._query(                      # type: ignore[attr-defined]
            "SELECT MAX(lap_num) as m FROM laps WHERE session_id = ?",
            (session_id,))
        if rows and rows[0]["m"] is not None:
            race_laps_run = int(rows[0]["m"])
    except Exception:
        pass

    # For lap-count races, scheduled == run (unless the race was cut short,
    # in which case race_laps_run < race_laps and is still correct to use).
    # Use race_laps_run when available; otherwise fall back to race_laps.
    effective_race_laps: int | None = race_laps_run or race_laps

    # Load raw source tables.
    board_pos = store.board_positions(session_id)
    gap_reads_rows = store.gap_reads(session_id)
    stops_rows = store.rival_stops(session_id=session_id)

    # --- Driver discovery ----------------------------------------
    # RH-I2: include names from ALL sources, including board_reads.
    drivers: set[str] = set()
    for r in board_pos:
        if r.get("driver"):
            drivers.add(str(r["driver"]))
    for r in stops_rows:
        if r.get("driver"):
            drivers.add(str(r["driver"]))
    # gap_reads subjects that look like names (not bare integers).
    for r in gap_reads_rows:
        subj = r.get("subject")
        if subj and not str(subj).lstrip("-").isdigit():
            drivers.add(str(subj))
    # RH-I2: board_reads names — non-null, non-phantom.
    # These drivers may have no stops or board_positions data; without this
    # step their board_reads rows would be deleted with no history preserved.
    try:
        br_name_rows = store._query(              # type: ignore[attr-defined]
            "SELECT DISTINCT name FROM board_reads "
            "WHERE session_id = ? AND name IS NOT NULL",
            (session_id,))
        for r in br_name_rows:
            name = r["name"] if hasattr(r, "keys") else r[0]
            if name and not _is_phantom(str(name)):
                drivers.add(str(name))
    except Exception:
        pass  # board_reads absent in very old schemas

    context = dict(
        series=series,
        circuit_key=circuit_key,
        car_name=car_name,
        race_laps=race_laps,
        race_laps_run=race_laps_run,
        is_timed=is_timed,
        race_date=race_date,
    )

    result: list[tuple[str, dict]] = []
    for driver in sorted(drivers):
        row = _build_history_row(
            driver=driver,
            session_id=session_id,
            board_pos=board_pos,
            gap_reads_rows=gap_reads_rows,
            stops_rows=stops_rows,
            store=store,
            effective_race_laps=effective_race_laps,
            fuel_capacity_l=fuel_capacity_l,
        )
        row.update(context)
        result.append((driver, row))

    return result, context


def _build_history_row(*, driver: str, session_id: int,
                       board_pos: list[dict],
                       gap_reads_rows: list[dict],
                       stops_rows: list[dict],
                       store: "Store",
                       effective_race_laps: int | None,
                       fuel_capacity_l: float | None) -> dict:
    """Build one history row dict (without context/audit fields)."""
    from pitcrew.race.fill_verdict import (   # noqa: PLC0415
        _rival_verdict,
        derive_stop_burn,
    )

    # ------ positions from board_positions ------
    driver_laps = sorted(
        {r["lap"]: r["position"]
         for r in board_pos
         if r.get("driver") == driver and r.get("lap") is not None}.items()
    )
    positions = [pos for _lap, pos in driver_laps]

    start_position: int | None = None
    finish_position: int | None = None
    best_position: int | None = None
    worst_position: int | None = None
    places_gained: int | None = None
    places_gained_n: int | None = None
    # RH-M2: laps_observed = distinct laps this driver appeared at a
    # crossing (where board_positions are recorded), not total board reads.
    laps_seen_at_crossings: int | None = len(driver_laps) if driver_laps else None

    if positions:
        start_position = driver_laps[0][1]
        finish_position = driver_laps[-1][1]
        # Best = lowest position number (P1 is best).
        best_position = min(positions)
        # Worst = highest position number (last place is worst).
        worst_position = max(positions)
        # places_gained: positive = net gain (moved forward in the field).
        # start P8 → finish P6: gained 2 → 8 - 6 = +2.
        places_gained = start_position - finish_position
        places_gained_n = len(positions)

    # ------ gap trend from gap_reads ------
    gap_slope, gap_n = _gap_slope_for_driver(gap_reads_rows, driver)

    # ------ stops from rival_stops ------
    driver_stops = [r for r in stops_rows if r.get("driver") == driver]
    driver_stops.sort(key=lambda r: (r.get("lap") or 0, r.get("id") or 0))

    stops_json_list = []
    for i, stop in enumerate(driver_stops):
        lap = stop.get("lap")
        lap_fraction: float | None = (
            float(lap) / effective_race_laps
            if lap is not None and effective_race_laps and effective_race_laps > 0
            else None
        )
        fuel_in = stop.get("fuel_in_l")
        fuel_out = stop.get("fuel_out_l")
        litres_added: float | None = None
        if fuel_out is not None and fuel_in is not None:
            # rule 9: a negative litres_added is returned as-is, not clamped
            litres_added = fuel_out - fuel_in

        # [DERIVED] burn per lap — rule 13: one expression via derive_stop_burn.
        prev = driver_stops[i - 1] if i > 0 else None
        burn, burn_assumed, start_basis = derive_stop_burn(
            stop, prev, capacity_l=fuel_capacity_l
        )

        # [DERIVED] stint_laps: our lap count from previous stop to this one.
        if i == 0:
            stint_laps = lap  # from race start (our lap 0)
        else:
            prev_lap = driver_stops[i - 1].get("lap")
            stint_laps = (
                (lap - prev_lap)
                if (lap is not None and prev_lap is not None)
                else None
            )
        burn_n = stint_laps   # sample count = laps in the stint

        # [DERIVED] fill verdict — same function as the monitor (rule 13).
        verdict_obj = _rival_verdict(
            fuel_out,
            burn,
            lap,
            effective_race_laps,
            partial=bool(stop.get("partial")),
            exit_is_a_bound=bool(stop.get("exit_is_a_bound", False)),
        )
        stops_json_list.append({
            "lap": lap,
            "lap_fraction": lap_fraction,
            "fuel_in_l": fuel_in,
            "fuel_out_l": fuel_out,
            "litres_added": litres_added,
            "fill_verdict": verdict_obj.verdict,
            "fill_bound": verdict_obj.bound,
            "burn_per_lap_l": burn,
            "burn_assumed": burn_assumed,           # rule 5: flag the assumption
            "start_basis": start_basis,             # rule 5: name the source
            "burn_n": burn_n,
            "stint_laps": stint_laps,
            "tyre_in": stop.get("compound_in"),
            "tyre_out": stop.get("compound"),
            "partial": bool(stop.get("partial")),
            "left_view": bool(stop.get("left_view", False)),
        })

    # ------ board_reads evidence ------
    board_rows: list[dict] = []
    try:
        board_rows = store.board_reads_for_driver(session_id, driver)
    except Exception:
        pass  # table absent in older DBs
    board_reads_n: int | None = len(board_rows) if board_rows else None
    # RH-I3: [DERIVED] seconds in view from timestamps, not a 1-s-per-read
    # approximation.  Sums inter-read intervals capped at 2× the median so
    # a view gap (board hidden) is excluded.  NULL when < 2 timestamped reads.
    board_secs_in_view: float | None = _secs_in_view_from_reads(board_rows)

    # ------ [DERIVED] pit visits seen by board but not filed ------
    pit_windows = _count_pit_windows(board_rows)
    pit_stops_board_unseen: int | None = (
        (pit_windows - len(driver_stops))
        if pit_windows is not None
        else None
        # Not clamped — a negative value is informative (rule 9).
    )

    # RH-M3: stop_count is NULL (not 0) when there is no board evidence for
    # this driver (no board_positions rows and no board_reads rows).  A 0
    # when we have board coverage means "we watched and saw no stops";
    # NULL means "we have no board data for this driver at all" (rule 3).
    has_board_evidence = (
        any(r.get("driver") == driver for r in board_pos)
        or bool(board_rows)
    )
    stop_count: int | None = len(driver_stops) if has_board_evidence else None

    return {
        "start_position": start_position,
        "finish_position": finish_position,
        "best_position": best_position,
        "worst_position": worst_position,
        "places_gained": places_gained,
        "places_gained_n": places_gained_n,
        "laps_observed": laps_seen_at_crossings,
        "gap_slope_s_per_lap": gap_slope,
        "gap_slope_n": gap_n,
        "stops_json": json.dumps(stops_json_list) if stops_json_list else None,
        "stop_count": stop_count,
        "pit_stops_board_unseen": pit_stops_board_unseen,
        "board_reads_n": board_reads_n,
        "board_secs_in_view": board_secs_in_view,
    }


# ---------------------------------------------------------------------------
# Normalise one session — public entry point
# ---------------------------------------------------------------------------

def normalise_session(store: "Store", session_id: int) -> int:
    """Write `rival_race_history` rows for every rival in this session.

    Reads board_positions, gap_reads, rival_stops, and board_reads (where
    available).  Returns the number of rows written.

    **Idempotent**: runs for a session that already has history rows and
    simply replaces them.  Safe to call multiple times.

    Raises on unrecoverable error (caller decides whether to abort cleanup).
    """
    all_rows, _ctx = _collect_all_rows(store, session_id)
    for driver, row in all_rows:
        store.upsert_rival_race_history(session_id, driver, row)
    return len(all_rows)


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup_due_sessions(store: "Store",
                         now: datetime.datetime | None = None) -> None:
    """Normalise and clean up all due race sessions.

    For each due session, in **one transaction** (RH-I1):
      (a) write rival_race_history rows,
      (b) verify the row count,
      (c) DELETE board_reads and name_resolutions for that session,
      (d) set history_compacted_at.

    Never runs while any race is currently active.  Never raises: logs all
    errors so the caller (app start, session end) is unaffected.

    RH-I5: exactly one cleanup pass runs at a time (module-level lock).

    **No VACUUM** — SQLite reuses freed pages; callers must not VACUUM the
    live DB (cost and lock).
    """
    if not _CLEANUP_LOCK.acquire(blocking=False):
        _LOG.debug("cleanup skipped: another cleanup pass is already running")
        return
    try:
        _cleanup_due_sessions_inner(store, now)
    finally:
        _CLEANUP_LOCK.release()


def _cleanup_due_sessions_inner(store: "Store",
                                now: datetime.datetime | None) -> None:
    if now is None:
        now = datetime.datetime.utcnow()

    # Abort if any race session is still open (ended_at IS NULL, kind=race).
    try:
        open_races = store._query(                    # type: ignore[attr-defined]
            "SELECT id FROM sessions "
            "WHERE kind = 'race' AND ended_at IS NULL "
            "AND (rehearsal IS NULL OR rehearsal = 0)",
            [])
        if open_races:
            _LOG.debug("cleanup skipped: %d race session(s) still open",
                       len(open_races))
            return
    except Exception as exc:
        _LOG.warning("cleanup aborted: could not check open races: %s", exc)
        return

    # Find all race sessions that are candidates.
    try:
        candidates = store._query(                    # type: ignore[attr-defined]
            "SELECT id, kind, ended_at, rehearsal, debriefed_at, "
            "history_compacted_at, started_at "
            "FROM sessions "
            "WHERE kind = 'race' "
            "AND (rehearsal IS NULL OR rehearsal = 0) "
            "AND ended_at IS NOT NULL "
            "AND history_compacted_at IS NULL",
            [])
    except Exception as exc:
        _LOG.warning("cleanup aborted: could not load candidates: %s", exc)
        return

    for raw in candidates:
        sess = dict(raw)
        session_id = sess["id"]
        due, reason = is_race_session_due(sess, [], now)
        if not due:
            continue
        _run_cleanup_for_session(store, session_id, reason)


def _upsert_row_conn(conn: "sqlite3.Connection", session_id: int,
                     driver: str, row: dict) -> None:
    """INSERT OR REPLACE one rival_race_history row using an existing conn."""
    now = _now_str()
    fields = {k: v for k, v in row.items()
              if k not in ("id", "session_id", "driver", "derived_at")}
    fields["session_id"] = session_id
    fields["driver"] = driver
    fields["derived_at"] = now
    cols = ", ".join(fields)
    placeholders = ", ".join("?" * len(fields))
    conn.execute(
        f"INSERT OR REPLACE INTO rival_race_history ({cols}) "
        f"VALUES ({placeholders})",
        list(fields.values()))


def _run_cleanup_for_session(store: "Store", session_id: int,
                              reason: str | None) -> None:
    """Normalise + verify + delete — all in ONE transaction (RH-I1).

    Step order inside the transaction:
      1. Build all row dicts in memory (no writes yet).
      2. INSERT OR REPLACE every row.
      3. Verify the count.
      4. DELETE board_reads and name_resolutions.
      5. SET history_compacted_at.

    If any step raises, the whole transaction rolls back and nothing is lost.
    """
    # Step 1: collect all row dicts (pure computation, no writes).
    try:
        all_rows, _ctx = _collect_all_rows(store, session_id)
    except Exception as exc:
        _LOG.error(
            "cleanup of session %d aborted: row collection failed: %s",
            session_id, exc, exc_info=True)
        return

    expected_n = len(all_rows)
    br_deleted = 0
    nr_deleted = 0

    try:
        with store._write() as conn:             # type: ignore[attr-defined]
            # Step 2: upsert all rows.
            for driver, row in all_rows:
                _upsert_row_conn(conn, session_id, driver, row)

            # Step 3: verify — must have at least expected_n rows for this
            # session.  INSERT OR REPLACE may have also preserved pre-existing
            # rows from a previous normalise call.
            cur = conn.execute(
                "SELECT COUNT(*) FROM rival_race_history WHERE session_id = ?",
                (session_id,))
            actual_n = cur.fetchone()[0]
            if actual_n < expected_n:
                raise RuntimeError(
                    f"verify failed: wrote {expected_n} rows for session "
                    f"{session_id} but SELECT counts only {actual_n}"
                )

            # Step 4: delete bulk tables.
            res = conn.execute(
                "DELETE FROM board_reads WHERE session_id = ?",
                (session_id,))
            br_deleted = res.rowcount
            try:
                res2 = conn.execute(
                    "DELETE FROM name_resolutions WHERE session_id = ?",
                    (session_id,))
                nr_deleted = res2.rowcount
            except sqlite3.OperationalError:
                # name_resolutions absent in very old schema — skip.
                pass

            # Step 5: set marker (commits with the rest of the transaction).
            conn.execute(
                "UPDATE sessions SET history_compacted_at = ? WHERE id = ?",
                (_now_str(), session_id))

    except Exception as exc:
        _LOG.error(
            "cleanup of session %d aborted: transaction failed: %s",
            session_id, exc, exc_info=True)
        return

    _LOG.info(
        "session %d cleaned up (%s): %d history rows written, "
        "%d board_reads deleted, %d name_resolutions deleted",
        session_id, reason or "unknown", expected_n,
        br_deleted, nr_deleted)


def _now_str() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")


# ---------------------------------------------------------------------------
# Profile aggregation across races
# ---------------------------------------------------------------------------

def history_profile(store: "Store", driver: str,
                    car: str | None = None,
                    circuit: str | None = None) -> dict:
    """Aggregate rival_race_history across races into how he likes to race.

    Returns a dict with:
    * races_n            — number of races in the sample
    * stop_lap_frac      — median stop-lap fraction (from race_laps_run, or
                           race_laps when run is absent), across all stops
    * stop_lap_frac_n
    * fill_habits        — shares of each fill verdict: {"spare": 0.4, ...}
    * fill_habits_n      — verdicts with known outcomes (excludes "can't tell")
    * burn_per_lap_l     — weighted mean burn (via profile_of, rule 13);
                           excludes assumed-start burns when measured burns
                           are available — reports them separately
    * burn_n             — count of stints (first stops) behind burn_per_lap_l
    * burn_assumed_n     — count of assumed-start burns excluded from the mean
    * stint_laps_median
    * stint_laps_n
    * places_gained_mean — mean places gained (positive = moved forward)
    * places_gained_n
    * gap_slope_mean_s_per_lap
    * gap_slope_races_n  — count of races that contributed a slope (RH-I4).
                           Distinct from gap_slope_n in rival_race_history rows
                           (which is consecutive laps behind the slope).

    Every figure carries its count.  None where the sample is empty (rule 3,
    rule 4).

    **Burn reuses profile_of** rather than re-deriving it (rule 13).  The
    history rows store per-stop burns for auditing; the aggregated figure
    comes from rival_book.profile_of, which reads rival_stops directly and
    is what the live race voice uses.
    """
    from pitcrew.race.rival_book import profile_of  # noqa: PLC0415

    history = store.rival_race_history(driver=driver)
    if car is not None:
        history = [r for r in history if r.get("car_name") == car]
    if circuit is not None:
        history = [r for r in history if r.get("circuit_key") == circuit]

    if not history:
        return _empty_profile(driver)

    races_n = len(history)

    # Collect stop-level data from stops_json in each history row.
    all_stops: list[dict] = []
    for row in history:
        raw = row.get("stops_json")
        if raw:
            try:
                all_stops.extend(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                pass

    # Stop lap fractions — use the race_laps_run-based fractions stored in
    # stops_json (already computed against effective_race_laps in normalise).
    fracs = [s["lap_fraction"] for s in all_stops
             if s.get("lap_fraction") is not None]
    stop_lap_frac = _median(fracs)
    stop_lap_frac_n = len(fracs)

    # Fill habits.
    verdicts = [s["fill_verdict"] for s in all_stops
                if s.get("fill_verdict") and s["fill_verdict"] != "can't tell"]
    fill_habits: dict[str, float] | None = None
    if verdicts:
        counts: dict[str, int] = {}
        for v in verdicts:
            counts[v] = counts.get(v, 0) + 1
        total = len(verdicts)
        fill_habits = {k: round(v / total, 3) for k, v in counts.items()}
    fill_habits_n = len(verdicts)

    # Stint lengths.
    stint_laps_list = [s["stint_laps"] for s in all_stops
                       if s.get("stint_laps") is not None and s["stint_laps"] > 0]
    stint_laps_median = _median(stint_laps_list)
    stint_laps_n = len(stint_laps_list)

    # Burn — use profile_of (rule 13: one burn expression).
    # profile_of reads rival_stops directly, the same source as the live voice.
    profile = profile_of(store, driver, series=None)
    raw_burn, burn_count = profile.burn_per_lap_l(car, circuit)
    burn_per_lap_l: float | None = raw_burn
    burn_n: int | None = burn_count if burn_count else None

    # Report how many assumed-start burns are in the history for this scope.
    # These are excluded from profile_of's mean (which uses first-stop
    # derivation with assumed_start_l from the row, not the 100 L fallback).
    # Counting them here surfaces the evidence quality.
    burn_assumed_n = sum(
        1 for s in all_stops if s.get("burn_assumed")
    )

    # Places gained — positive means moved forward (rule: start - finish).
    pg_list = [r["places_gained"] for r in history
               if r.get("places_gained") is not None]
    places_gained_mean = (
        sum(pg_list) / len(pg_list) if pg_list else None
    )
    places_gained_n = len(pg_list)

    # Pace against us.  Build (slope, n) pairs together so the filter is
    # consistent — every race that contributed a slope also contributes its n.
    # RH-I4: gap_slope_races_n = count of RACES that contributed a slope.
    # This is distinct from gap_slope_n on each history row, which is the
    # consecutive lap count behind that race's slope (rule 13, rule 4).
    slope_pairs = [
        (r["gap_slope_s_per_lap"], r.get("gap_slope_n"))
        for r in history
        if r.get("gap_slope_s_per_lap") is not None
    ]
    gap_slope_mean = (
        sum(s for s, _ in slope_pairs) / len(slope_pairs)
        if slope_pairs else None
    )
    # gap_slope_races_n = count of races that contributed a slope (rule 4).
    gap_slope_races_n: int | None = len(slope_pairs) if slope_pairs else None

    return {
        "driver": driver,
        "races_n": races_n,
        "stop_lap_frac": stop_lap_frac,
        "stop_lap_frac_n": stop_lap_frac_n,
        "fill_habits": fill_habits,
        "fill_habits_n": fill_habits_n,
        "burn_per_lap_l": burn_per_lap_l,
        "burn_n": burn_n,
        "burn_assumed_n": burn_assumed_n,
        "stint_laps_median": stint_laps_median,
        "stint_laps_n": stint_laps_n,
        "places_gained_mean": places_gained_mean,
        "places_gained_n": places_gained_n,
        "gap_slope_mean_s_per_lap": gap_slope_mean,
        "gap_slope_races_n": gap_slope_races_n,   # RH-I4: races, not laps
    }


def _empty_profile(driver: str) -> dict:
    return {
        "driver": driver,
        "races_n": 0,
        "stop_lap_frac": None,
        "stop_lap_frac_n": 0,
        "fill_habits": None,
        "fill_habits_n": 0,
        "burn_per_lap_l": None,
        "burn_n": None,
        "burn_assumed_n": 0,
        "stint_laps_median": None,
        "stint_laps_n": 0,
        "places_gained_mean": None,
        "places_gained_n": 0,
        "gap_slope_mean_s_per_lap": None,
        "gap_slope_races_n": None,   # RH-I4
    }


def _median(xs: list) -> float | None:
    """Median of a non-empty list, or None."""
    if not xs:
        return None
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    if n % 2 == 0:
        return (s[mid - 1] + s[mid]) / 2.0
    return float(s[mid])
