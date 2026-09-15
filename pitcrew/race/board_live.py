"""What the driver board reads off every packet: the lap delta, LOCK and TCS.

Plan row 5.21, asked for by the driver on 14 Sep 2026 - *"current lap delta
against best lap"*, and indicator boxes that light up. Three things, all cheap
enough for the telemetry thread. **The Qt thread only ever reads one tuple this
thread publishes whole** (`_shown`), so a compound switched between two reads
can never pair one tyre's delta with another tyre's best - critic pass 1 found
`session_reference` read twice per packet and the second read going None.

### The delta

Live lap time minus the reference lap's time **at the same distance round the
lap**, so negative is ahead and positive behind. Two references, both named on
the board:

* **this session's best lap on the compound fitted** - built from the frames
  the recorder hands over at the crossing, the moment a counted lap beats it;
* **the best lap on file** for this car, circuit, game version **and compound**
  - another day, perhaps another setup, which is why it is the second figure.

**Every reference is locked to a compound** (the driver, 14 Sep 2026: *"all
best times should be locked to compound"*). An RM lap chased against an RS best
is half a second of tyre dressed as driving. With no compound known there is no
delta at all, and the board says "compound not set".

Distance is integrated from speed against the packet counter **exactly as the
recorder writes `lap_distance_m`** (`TelemetryRecorder.record_frame`): a packet
off track, paused or loading adds nothing but still closes its own gap in the
counter - otherwise the first packet after 30 s paused carries 1,800 packets of
distance, which critic pass 1 reproduced here (500 m became 2,000 m). The
crossing packet belongs to the lap it completes, as the recorder files it. A lap
abandoned without a crossing - GT7's lap clock going backwards on a restart, the
garage, a return to the pits - stops being timed until the next crossing.
That rule only acts on a newer packet, more than `BACKWARDS_AFTER_MS` into the
lap, on a drop larger than `BACKWARDS_BY_MS`: no capture on file shows whether
GT7's lap clock resets on the crossing packet or a packet after it, and an
out-of-order datagram must not end a lap either (critic pass 2).

### LOCK - derived, and the board says so

GT7 sends no ABS signal, and "ABS is working" cannot be derived: with ABS off,
heavy braking sits in the same slip band ABS holds (13-24% of heavy-braking
frames on the Shelby against 13-44% with ABS Weak, 14 Sep 2026). **What ABS
removes is most of the lock tail** - 2-6% of heavy-braking frames below 0.80
front slip with ABS off, about none with it on. The light's gate is any brake,
so it does still fire with ABS Weak: critic pass 1 counted it on 5 of 31
Bathurst laps and 9 of 151 Daytona laps on 1.71. It reports a lock, never a
verdict on ABS.

### TCS - measured

`flags_raw` bit 11, calibrated on the driver's TCS-on lap of 14 Sep 2026: set
on 22% of that lap's frames against 0.01% of the same car and circuit with TCS
off, and on 82% of the hard-throttle wheelspin frames.

Both lights are held for a moment after they drop, and **everything reverts to
"no reading" once packets stop arriving** (rule 3: a lamp left lit by the last
packet of a dead stream is not a reading).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

# The recorder's own sample rate, so distance is stepped exactly as it is there.
SAMPLE_HZ = 60.0

# Front slip below this under braking is a locking wheel (see module docstring).
LOCK_SLIP = 0.80
LOCK_MIN_BRAKE = 0.05
LOCK_MIN_SPEED_MS = 40.0 / 3.6
LOCK_HOLD_S = 0.6

TCS_BIT = 0x0800
TCS_HOLD_S = 0.3

# Packets older than this and nothing on the panel or the lights is live.
STALE_S = 1.5

# The lap clock going backwards ends the timing only this far into a lap, and
# only by this much - see the module docstring.
BACKWARDS_AFTER_MS = 2000.0
BACKWARDS_BY_MS = 1000.0

# Why the delta is a dash, in the board's words.
NO_BEST_YET = "no best lap yet on this tyre"
NOT_ON_A_LAP = "waiting for the line"
NO_COMPOUND = "compound not set"
NO_TELEMETRY = "no telemetry"

_NOTHING_SHOWN = (None, None, None, None, None, None, None, None, None)

# Why the sectors are dashes, in the board's words.
NO_LAP_YET = "no lap completed yet"
NO_SECTOR_TIMES = "no sector times for that lap"


@dataclass(frozen=True)
class SectorsView:
    """The last completed lap cut into three, against this session's best of
    each sector on the same tyre and the same sector lines.

    Asked for on 15 Sep 2026 for the ultrawide ("last lap S1/S2/S3 vs best").
    **GT7 sends no sectors** - these are `analysis/lap_sectors.py`'s cut, so
    `cut` names where the lines came from and the board prints it. A best is
    only ever a counted lap's: not an out-lap, not a pit lap, not a struck lap,
    and never a sector cut on other lines (a sector at 1,780 m is not the same
    piece of road as one at 2,097).
    """
    times_ms: tuple | None = None           # the last lap's three, or None
    best_ms: tuple = (None, None, None)     # the session bests they are against
    set_best: tuple = (False, False, False)  # this lap IS that best
    why: str | None = None                  # why `times_ms` is None
    cut: str | None = None                  # the lines' provenance, in words
    compound: str | None = None


def _front_slip(packet) -> float | None:
    """The lower front wheel's surface speed over car speed, or None."""
    speed = getattr(packet, "speed_ms", None)
    if not speed or speed < LOCK_MIN_SPEED_MS:
        return None
    try:
        fl = abs(packet.wheel_rps_fl) * packet.tyre_radius_fl / speed
        fr = abs(packet.wheel_rps_fr) * packet.tyre_radius_fr / speed
    except (AttributeError, TypeError):
        return None
    if not (math.isfinite(fl) and math.isfinite(fr)):
        return None
    return min(fl, fr)


class BoardLive:
    """Per-packet state for the board. One per session; `new_session` resets."""

    def __init__(self, *, file_reference_for=None) -> None:
        """`file_reference_for(compound)` returns the best lap on file for that
        compound as a `ReferenceLap`, or None. Called on the Qt thread when the
        compound is set, never on the telemetry thread."""
        self._file_reference_for = file_reference_for
        self._file_refs: dict = {}
        self.new_session()

    # ------------------------------------------------------------ Qt thread

    def new_session(self) -> None:
        """Rule 11: nothing measured in the last session is this session's.
        The on-file references are kept - they belong to the archive - but the
        session bests and the fitted compound are not."""
        self.compound: str | None = None
        self._session_refs: dict = {}
        self._distance_m = 0.0
        self._elapsed_ms = 0.0
        self._last_packet_id = None
        self._last_lap_ms = None
        self._on_lap = False
        self._lock_until = -1.0
        self._tcs_until = -1.0
        self._last_seen: float | None = None
        # The sector panel - Qt thread only, set at the crossing.
        # `(lap_id, (s1, s2, s3), stamp, compound)` for every counted lap
        # with all three sectors, so a struck lap can be retired and the next
        # best found without going back to the store.
        self._sector_laps: list = []
        self._last_sectors: tuple | None = None   # (lap_id, times, stamp, code, why)
        # (code, session ref, file ref, lap ms, delta, delta on file,
        #  predicted, lock, tcs) - published whole, read whole.
        self._shown = _NOTHING_SHOWN

    def set_compound(self, compound: str | None) -> None:
        """The tyre now fitted; loads its best on file once."""
        code = compound.upper() if compound else None
        if code and code not in self._file_refs:
            loader = self._file_reference_for
            try:
                found = loader(code) if loader else None
            except Exception:                               # noqa: BLE001
                found = None
            refs = dict(self._file_refs)
            refs[code] = found
            self._file_refs = refs            # swapped whole, never mutated
        self.compound = code

    def note_lap(self, lap, rows, field_names, compound: str | None,
                 *, lap_id: int | None = None) -> bool:
        """At the crossing. Returns whether that compound's session best moved.

        Only a counted lap on a KNOWN compound may become a reference: not an
        out-lap, not a pit lap, a real time, and frames that span that time. The
        caller refuses excluded laps; `drop_lap` retires one struck or re-tagged
        afterwards, which is why the reference carries the lap's stored id."""
        from pitcrew.race.qualifying import REFERENCE_SPAN_TOLERANCE, ReferenceLap

        lap_ms = getattr(lap, "lap_time_ms", None) or 0
        code = compound.upper() if compound else None
        if (not code or lap_ms <= 0 or getattr(lap, "is_out_lap", False)
                or getattr(lap, "is_pit_lap", False) or not rows):
            return False
        best = self._session_refs.get(code)
        if best is not None and lap_ms >= best.lap_time_ms:
            return False
        index = {name: i for i, name in enumerate(field_names)}
        if "lap_distance_m" not in index or "t_ms" not in index:
            return False
        span_ms = len(rows) / SAMPLE_HZ * 1000.0
        if abs(span_ms - lap_ms) > lap_ms * REFERENCE_SPAN_TOLERANCE:
            return False
        d, t = index["lap_distance_m"], index["t_ms"]
        frames = [{"lap_distance_m": row[d], "t_ms": row[t]} for row in rows]
        reference = ReferenceLap.from_frames(
            frames, lap_id=lap_id if lap_id is not None else -1,
            lap_time_ms=int(lap_ms))
        if reference is None:
            return False
        refs = dict(self._session_refs)
        refs[code] = reference
        self._session_refs = refs             # swapped whole, never mutated
        return True

    def drop_lap(self, lap_id: int) -> None:
        """A lap struck by hand or re-tagged to another tyre is no longer a best
        on the tyre it was filed under. That compound has no session best until
        the next counted lap on it - a gap, never the wrong reference."""
        refs = {code: ref for code, ref in self._session_refs.items()
                if ref.lap_id != lap_id}
        if len(refs) != len(self._session_refs):
            self._session_refs = refs
        # Its sectors stop being bests too; the next best is whatever the
        # remaining counted laps hold.
        self._sector_laps = [entry for entry in self._sector_laps
                             if entry[0] != lap_id]

    # ------------------------------------------------------------ sectors

    def note_sectors(self, *, lap_id: int | None, times_ms, stamp: str | None,
                     compound: str | None, counted: bool,
                     refused: str | None = None) -> None:
        """At the crossing, on the Qt thread: the lap just completed, cut.

        Every lap becomes the LAST lap - the panel shows what he has just
        driven, dashes and a reason included. Only a counted lap with all
        three sectors, on a known tyre, can become a best.
        """
        code = compound.upper() if compound else None
        whole = (times_ms is not None and len(times_ms) == 3
                 and all(value is not None and value > 0 for value in times_ms))
        times = tuple(int(value) for value in times_ms) if whole else None
        why = None if whole else (refused or NO_SECTOR_TIMES)
        if whole and counted and code and stamp:
            self._sector_laps = [*self._sector_laps,
                                 (lap_id, times, stamp, code)]
        self._last_sectors = (lap_id, times, stamp, code, why)

    def sectors_view(self, cut_words=None) -> SectorsView:
        """The panel. `cut_words(stamp)` turns the lines' stamp into words."""
        last = self._last_sectors
        if last is None:
            return SectorsView(why=NO_LAP_YET, compound=self.compound)
        lap_id, times, stamp, code, why = last
        cut = cut_words(stamp) if (cut_words and stamp) else None
        if times is None:
            return SectorsView(why=why, cut=cut, compound=code)
        # **Same tyre, same lines** - the two locks every best on this board
        # carries (rule 13: a best that does not say what it is against is
        # two numbers pretending to be one).
        pool = [entry for entry in self._sector_laps
                if entry[2] == stamp and entry[3] == code]
        best, mine = [], []
        for index in range(3):
            if not pool:
                best.append(None)
                mine.append(False)
                continue
            holder = min(pool, key=lambda entry: entry[1][index])
            best.append(holder[1][index])
            # Ties go to the lap that set it first: `min` keeps the earliest,
            # so a later lap equalling a best does not claim it.
            mine.append(lap_id is not None and holder[0] == lap_id)
        return SectorsView(times_ms=times, best_ms=tuple(best),
                           set_best=tuple(mine), cut=cut, compound=code)

    # ------------------------------------------------------------ telemetry thread

    def note_packet(self, packet, now: float, *, crossed: bool = False) -> None:
        """`crossed` is true on the packet a lap completed."""
        # **One read of everything the Qt thread may change**, used for the
        # whole packet and published with the answer it produced.
        code = self.compound
        session_ref = self._session_refs.get(code) if code else None
        file_ref = self._file_refs.get(code) if code else None
        self._last_seen = now

        flags = getattr(packet, "flags_raw", None)
        tcs = None
        if flags is not None:
            if flags & TCS_BIT:
                self._tcs_until = now + TCS_HOLD_S
            tcs = now <= self._tcs_until
        brake = getattr(packet, "brake", None) or 0.0
        slip = _front_slip(packet)
        if brake >= LOCK_MIN_BRAKE and slip is not None and slip < LOCK_SLIP:
            self._lock_until = now + LOCK_HOLD_S
        lock = now <= self._lock_until

        moving = (getattr(packet, "car_on_track", True)
                  and not getattr(packet, "paused", False)
                  and not getattr(packet, "loading", False))
        packet_id = getattr(packet, "packet_id", None)
        step = 1
        if packet_id is not None:
            last = self._last_packet_id
            step = 1 if last is None else packet_id - last
            if step > 0:
                self._last_packet_id = packet_id
                # The crossing packet is recorded in the lap it completes, so
                # it is not the new lap's distance either.
                if moving and not crossed:
                    self._distance_m += (packet.speed_ms or 0.0) * step / SAMPLE_HZ
                    self._elapsed_ms += step * 1000.0 / SAMPLE_HZ

        lap_ms = getattr(packet, "current_lap_time_ms", None)
        if crossed:
            self._distance_m = 0.0
            self._elapsed_ms = 0.0
            self._on_lap = True
        elif (self._on_lap and step > 0 and lap_ms is not None
              and self._last_lap_ms is not None
              and self._elapsed_ms > BACKWARDS_AFTER_MS
              and lap_ms < self._last_lap_ms - BACKWARDS_BY_MS):
            # GT7's lap clock went backwards with no crossing: a restart, the
            # garage, a return to the pits. That lap is not being driven.
            self._on_lap = False
        if lap_ms is not None and step > 0:
            self._last_lap_ms = lap_ms

        if not self._on_lap:
            self._shown = (code, session_ref, file_ref, None, None, None, None,
                           lock, tcs)
            return
        live_ms = float(lap_ms) if lap_ms is not None else self._elapsed_ms
        delta = self._delta(session_ref, live_ms)
        delta_file = self._delta(file_ref, live_ms)
        predicted = (None if delta is None
                     else int(round(session_ref.lap_time_ms + delta * 1000.0)))
        self._shown = (code, session_ref, file_ref, int(live_ms), delta,
                       delta_file, predicted, lock, tcs)

    def _delta(self, reference, live_ms: float) -> float | None:
        if reference is None:
            return None
        return (live_ms - reference.elapsed_at(self._distance_m)) / 1000.0

    # ------------------------------------------------------------ for the board

    def board_fields(self, now: float | None = None) -> dict:
        """The `DriverState` fields this object owns, from one publication, so
        the tyre named is the tyre the delta was measured against (rule 13)."""
        now = time.monotonic() if now is None else now
        (code, session_ref, file_ref, lap_ms, delta, delta_file, predicted,
         lock, tcs) = self._shown
        if self._last_seen is None:
            code, session_ref, file_ref = (self.compound,
                                           self._session_refs.get(self.compound),
                                           self._file_refs.get(self.compound))
        stale = self._last_seen is None or now - self._last_seen > STALE_S
        if stale:
            lap_ms = delta = delta_file = predicted = None
            lock = tcs = None
        if delta is not None:
            why = None
        elif not code:
            why = NO_COMPOUND
        elif stale:
            why = NO_TELEMETRY
        elif lap_ms is None:
            why = NOT_ON_A_LAP
        else:
            why = NO_BEST_YET
        return {
            "reference_compound": code,
            "lap_time_ms": lap_ms,
            "delta_s": delta,
            "session_best_ms": None if session_ref is None else session_ref.lap_time_ms,
            "predicted_ms": predicted,
            "delta_file_s": delta_file,
            "file_best_ms": None if file_ref is None else file_ref.lap_time_ms,
            "delta_why": why,
            "front_lock": lock,
            "tcs_active": tcs,
        }


def best_lap_on_file(store, car_name: str | None, track: str | None,
                     layout: str | None, game_version: str | None,
                     compound: str | None):
    """The fastest counted lap with frames for this car, circuit, game version
    and compound, as a `ReferenceLap`, or None.

    **The game version is a filter, not a preference**: a patch is a
    discontinuity (1.71 rewrote the physics), so a faster lap on another
    version is not a reference for this one. Practice and race laps both count;
    the frames have to span the claimed time, the gate `reference_lap` uses."""
    from pitcrew.race.qualifying import REFERENCE_SPAN_TOLERANCE, ReferenceLap

    if not car_name or not track or not game_version or not compound:
        return None
    rows = store._query(
        "SELECT l.id, l.lap_time_ms FROM laps l "
        "JOIN sessions s ON s.id = l.session_id "
        "JOIN events e ON e.id = s.event_id "
        "WHERE e.car_name = ? AND e.track = ? AND COALESCE(e.layout, '') = ? "
        "AND s.game_version = ? AND COALESCE(l.excluded, 0) = 0 "
        "AND COALESCE(l.is_out_lap, 0) = 0 AND COALESCE(l.is_pit_lap, 0) = 0 "
        "AND l.lap_time_ms > 0 AND UPPER(l.compound) = ? "
        "ORDER BY l.lap_time_ms LIMIT 12",
        (car_name, track, layout or "", game_version, compound.upper()))
    for row in rows:
        stored = store.get_lap_frames(row["id"])
        if not stored:
            continue
        span_ms = stored["frame_count"] / (stored["sample_hz"] or SAMPLE_HZ) * 1000.0
        if abs(span_ms - row["lap_time_ms"]) > row["lap_time_ms"] * REFERENCE_SPAN_TOLERANCE:
            continue
        reference = ReferenceLap.from_frames(
            stored["frames"], lap_id=row["id"], lap_time_ms=int(row["lap_time_ms"]))
        if reference is not None:
            return reference
    return None
