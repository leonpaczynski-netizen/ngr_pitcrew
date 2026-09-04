"""Full-rate per-lap telemetry capture.

GT7 sends at 60 Hz.  The old recorder kept every sixth packet (~10 Hz) because
its consumers were summary statistics.  The consumer now is an analysis pass in
Claude, so the requirement is "the best frequency of refresh possible" — this
records every packet.

A lap is roughly 7,200 frames.  Frames are serialised column-header + row-array
rather than a list of objects (no key repetition), rounded to the precision the
channel actually carries, then zlib-compressed: ~150-400 KB per lap on disk.

Threading: `record_frame()` runs on the UDP thread, `take_lap()` on whichever
thread handles lap completion.  Both take the lock; nothing else touches the
buffer.
"""
from __future__ import annotations

import array
import json
import sys
import math
import threading
import zlib
from dataclasses import dataclass

from pitcrew.telemetry.packet import GT7Packet

SAMPLE_HZ = 60.0
MS_PER_PACKET = 1000.0 / SAMPLE_HZ
BLOB_FORMAT = "pitcrew.frames.v1"

# **What the numbers mean**, versioned separately from where they sit.
# `decode_frames` maps values by the blob's own stored `fields` list, so the
# column layout is already safe against change; what it could not express was a
# channel whose *values* were wrong at the source. Two were:
#
#   v1 - `yaw_rate` held the roll rate (`angvel_z`), and the four slip channels
#        were 2pi too large.
#   v2 - `yaw_rate` is the yaw rate (`angvel_y`), slip is a true ratio, and the
#        slip channels are null rather than a synthetic 1.0 below walking pace.
#
# A blob with no version stamp is v1 and is upgraded on read by
# `repair_frames`, so the laps already on disk are repaired rather than lost.
FRAME_SCHEMA_VERSION = 2

# Where `decode_frames` hands the blob's version to `repair_frames`, which
# strips it again. Nothing downstream of the repair ever sees this key.
_VERSION_KEY = "_v"

# Column order is part of the on-disk format.  Append only — never reorder, or
# previously stored laps decode into the wrong channels.
#
# Units are converted here, at the parser boundary, once.  Everything
# downstream works in the export's units so no layer has to remember which
# convention it is holding.  Missing channels are null, never zero.
#
# Deliberately absent: oil and water temperature.  GT7 pins them at ~110 C and
# ~85 C regardless of what the car is doing, so they carry no information.
FRAME_FIELDS: tuple[str, ...] = (
    "t_ms",              # ms since the lap's first frame, from the packet counter
    # GT7 0xA0. This is the road plane's fourth coefficient, NOT distance
    # around the lap: it reads about -80 to -250 m and covers 125 m over a
    # whole lap of Monza. It was named `road_distance_m` and fed to corner
    # detection, which is why no session ever produced a corner model and why
    # `corners` - the section the contract calls the one to build if only one
    # gets built - has never once been exported. Kept because the on-disk
    # format is append-only, named for what it is so it cannot be mistaken
    # again. Nothing reads it.
    "road_plane_d",
    "speed_kph",
    "throttle_pct",      # 0-100
    "brake_pct",         # 0-100
    "steering_deg",      # degrees, null until the tail offset is verified
    "steering_norm",     # -1..1 fraction of full lock, null likewise
    "gear",
    "rpm",               # captured for short-shift analysis; never exported
    # Rotation about the **vertical** axis, rad/s, from `angvel_y`.
    # **Not `angvel_z`**, which is what this column held in every v1 blob:
    # `road_plane_y` - the road normal's Y component - runs 0.987 to 1.0 across
    # all 918,673 captured frames, so up is world +Y and yaw is rotation about
    # Y. `angvel_z` correlates +0.62 with the derivative of suspension roll
    # asymmetry and -0.04 with ground-track yaw, and integrates to -1.6 deg
    # over a closed lap where yaw must integrate to -360. It is the roll rate,
    # and spin detection had never once fired on it.
    "yaw_rate",
    # speed * yaw rate / g. The expression was always right; the rate it was
    # handed was not, which is what put a peak of 8.46 g on a Gr.3 car.
    "lat_g",
    "pos_x", "pos_y", "pos_z",
    "slip_fl", "slip_fr", "slip_rl", "slip_rr",   # wheel surface speed / car speed
    "susp_mm_fl", "susp_mm_fr", "susp_mm_rl", "susp_mm_rr",  # absolute height, mm
    "temp_fl", "temp_fr", "temp_rl", "temp_rr",   # tyre surface, degrees C
    "body_height_mm",
    "surf_fl", "surf_fr", "surf_rl", "surf_rr",   # T/C/D/G/S/s, null before '~'
    "road_plane_y",      # off-track proxy for formats without surface type
    "rev_limiter",
    # Needed to derive the final drive from engine speed against wheel speed.
    # Appended, so laps recorded before this still decode - the blob carries
    # its own field list.
    "tyre_radius_m",
    # **Distance around the lap, metres from the line.** GT7 broadcasts no
    # such channel, so it is integrated here from speed against the packet
    # clock. Everything about corner identity depends on it: a corner is a
    # window of lap distance, and without one there are no corners.
    "lap_distance_m",
    # **GT7's in-game clock**, ms through the game day. Useless as a frame
    # clock - it is frozen in a fixed-time event and runs at the event's time
    # multiplier otherwise, which is what made it wrong for `t_ms`. That same
    # property is exactly what makes it worth recording: it says **where in the
    # day this lap was driven**. A race at x12 covers a day and a night, the
    # track cools, and a compound that never reaches temperature costs lap time
    # against everything practised in daylight. GT7 broadcasts neither track
    # nor air temperature, so this is the only channel that says which
    # conditions a measurement belongs to.
    "time_of_day_ms",
    # **Fuel in the tank, litres.** Per-lap start and end have always been
    # stored, but a stop happens inside a lap and the rate it fills at is the
    # largest term in a pit stop - 73 s of a 100 s stop at Monza. GT7 marks no
    # pit stop in any packet format, so the tank climbing is both the detector
    # and the measurement. See `analysis/refuel.py`.
    "fuel_l",
    # **World velocity, and the reason it is being kept at last.**
    #
    # The haptic layer derives sideslip - the angle between where the car is
    # pointing and where it is going - from the velocity vector against the
    # yaw rate. Both are in the base packet, so the live model has what it
    # needs; the difficulty is proving it, because until now the only route to
    # a path heading offline was differencing `pos_x`/`pos_z`, which are
    # stored to the centimetre. That puts the reconstructed residual's noise
    # floor at 0.06 deg against 0.18 deg of real sideslip at the limit, which
    # is why the rotation cue is capped at MEDIUM confidence and attenuated.
    #
    # These three columns are what lift that cap. They are floats at 60 Hz and
    # need no differencing at all, so one recorded lap re-run through
    # `tools/rig_levels.py` settles whether the model is worth trusting - and
    # if it is not, says so, which is equally worth having.
    #
    # Appended, so laps recorded before this still decode: the blob carries
    # its own field list.
    "vel_x", "vel_y", "vel_z",
    # **Where the front wheels are actually pointing, radians.** GT7 offsets
    # 352 and 356, averaged - not `steering_deg`, which is the in-game rim at
    # 296 and saturates at +-pi regardless of the driver's rotation setting.
    #
    # Kept because the front-saturation question cannot be answered without
    # it. The obvious model - measured yaw against the yaw a neutral-steer car
    # would do - needs a road-wheel angle, and fed the rim instead it becomes
    # a steering meter: measured, the implied steer gain falls by a factor of
    # 2.5 from small angles to large, and there is no way to tell how much of
    # that is tyre saturation and how much is the steering rack. With this
    # column it is separable. Without it, no front cue should be built at all.
    "road_wheel_rad",
    # **The three channels that decide which lap this is, and none of them was
    # being kept.** Thirty-odd columns per frame and not one of them could say
    # why a crossing went missing: `laps_completed` is GT7's own lap counter,
    # `last_lap_ms` is the edge the detector actually triggers on, and
    # `flags_raw` bit 0 is `car_on_track`, which GT7 clears through the pit
    # sequence and which used to gate lap filing.
    #
    # Session 88 filed 19 rows for a 20-lap race and the archive could not be
    # asked which of those two dropped it - the fault had to be read off a
    # video replay of the race instead. Appended, so every lap already on disk
    # still decodes: the blob carries its own field list.
    "gt7_laps_completed",
    "last_lap_ms",
    "flags_raw",
)

# The driver's physical wheel rotation setting (Fanatec DD Extreme).  Reported
# in `derived.steerRotationDeg` so a reader can relate the captured angle to
# what his hands did — it is NOT used to normalise, because the channel we
# capture is the in-game wheel, which saturates at +-pi whatever the rim is set
# to.  Normalisation lives in GT7Packet.steering_norm.
DEFAULT_STEER_ROTATION_DEG = 1080.0

_TWO_PI = 2.0 * math.pi
# Below this the wheel-speed ratio is numerically meaningless (standing start,
# stopped in the pit box) and would report enormous slip.
_MIN_SPEED_FOR_SLIP_MS = 2.0

_SLIP_FIELDS = ("slip_fl", "slip_fr", "slip_rl", "slip_rr")

# Half-width of the stencil the yaw repair takes a heading over, in seconds.
# `pos_x`/`pos_z` are stored at 1 cm and the car covers ~1.3 m per frame at
# racing speed, so a heading measured across +-0.1 s spans ~16 m and carries
# about 0.6 mrad of rounding noise. Differencing two of those over the same
# span keeps the reconstructed rate inside 0.01 rad/s - 2-4% of the cornering
# signal, against corner windows that are seconds long and keyed on lap
# distance rather than on this.
_YAW_STENCIL_S = 0.1


# Index of `time_of_day_ms` in a frame row, so the clock span can be lifted
# out of the rows without decoding them again.
_TOD_INDEX = FRAME_FIELDS.index("time_of_day_ms")
_SPEED_INDEX = FRAME_FIELDS.index("speed_kph")

# Below this the car has not set off. Not zero: the release from a standstill
# passes through fractions of a km/h and a hard zero would call the first
# creep "moving".
_MOVING_KPH = 5.0


@dataclass(frozen=True)
class LapFrames:
    """One lap's captured telemetry, ready to store."""
    frame_count: int
    sample_hz: float
    blob: bytes
    # **GT7's own clock at the first and last frame of the lap.** Stored on
    # the lap rather than left inside the blob because everything that reads
    # the clock - what hour the lobby's time-of-day preset actually means at
    # this circuit, what multiplier it runs at, where it stops - needs every
    # lap of a session and needs none of the other 36 channels.
    #
    # Leaving it in the blob meant the clock could only be read from whichever
    # laps something else had decided to decode, and something else was
    # decoding the last six laps per compound. At Monza those were the laps
    # after the pit stop, where GT7's clock had already run to its ceiling and
    # frozen - so the app measured "multiplier 0, fixed at 18:50" for a lobby
    # that starts at 15:56 and runs at six times real speed, and cached it.
    tod_start_ms: int | None = None
    tod_end_ms: int | None = None
    # **How long the car sat before it set off**, on this lap. Only the first
    # lap of a session has anything to say with it, and what it says is which
    # kind of session this was: out of the pit box in a lobby, or already on
    # the track ahead of the line in a time trial. Measured across the capture
    # set the two do not overlap - 0 to 4.6 s against 43 to 80 s, with nothing
    # in between. It corroborates the driver's declaration; it never overrules
    # it.
    standing_start_ms: int | None = None
    # Set by the caller from `analysis.incidents.read_rows` while the rows are
    # still uncompressed. Not computed here: the recorder is the bottom of the
    # stack and the analysis layer sits above it.
    crawl_s: float | None = None
    off_track_s: float | None = None
    spin_s: float | None = None
    # **The fastest frame of the lap, taken here rather than read back out.**
    # `Store._note_top_speed` used to `decode_frames(blob)` - a full
    # `zlib.decompress` plus `json.loads` of the lap that had just been
    # encoded three lines earlier - to take one maximum. Measured at 40.2 ms,
    # about 30 ms of it `json.loads` holding the GIL uninterruptibly, on the
    # Qt thread, at every lap crossing, immediately after `encode_frames` had
    # done the same thing in the other direction. The same answer off the
    # rows in hand is 0.369 ms.
    top_kph: float | None = None
    # **The lap cut in three, and the lines it was cut against.** Set by the
    # caller from `analysis.lap_sectors.read_rows` while the rows are still
    # uncompressed - not computed here, for the same reason the incident
    # evidence above is not: the recorder is the bottom of the stack and the
    # analysis layer sits above it.
    #
    # All four stay None where the lap was refused. A refusal must not be
    # stored as a settled answer, because the commonest reason for one is a
    # circuit whose sector lines have not been established yet.
    sector1_ms: int | None = None
    sector2_ms: int | None = None
    sector3_ms: int | None = None
    sector_model: str | None = None

    @property
    def size_bytes(self) -> int:
        return len(self.blob)


def _round(value: float | None, places: int) -> float | None:
    """Round, but leave `None` alone. Missing is null, never zero."""
    return None if value is None else round(value, places)


def _slip_ratios(p: GT7Packet) -> tuple[float | None, ...]:
    """Wheel surface speed / car speed per corner.

    1.0 = rolling true, > 1.0 = spinning up, < 1.0 = locking.  This is the only
    way to get slip out of GT7, which sends wheel rotation and tyre radius but
    no slip channel.

    **The per-wheel channel is rad/s, not rev/s**, so surface speed is
    `omega * radius` and nothing more.  Multiplying by 2pi as well made every
    reading 6.2832 times too large, and the flags built on it were noise:
    `wheelspin` true on 99.7% of throttle-on frames, `lockup` on 0.2% of
    braking ones - so a driver whose whole technique is trail-braking deep had
    never once been shown a lockup.  The declared 8% wheelspin trip was really
    17.2% and the declared 15% lockup was really an 86.5% lock.  Sanity check
    on the observed top speed: 282.66 km/h on a 0.355 m tyre is 221 rad/s,
    which is 2,110 rpm; rev/s would make it 13,300.

    Below `_MIN_SPEED_FOR_SLIP_MS` the ratio is arithmetic on a divisor that
    means nothing, so it is `None`.  It used to be a hard 1.0, which is this
    channel's zero - exactly "rolling true", the most benign real reading it
    has, written with nothing to mark it unmeasured.
    """
    if p.speed_ms < _MIN_SPEED_FOR_SLIP_MS:
        return (None, None, None, None)
    rps = (p.wheel_rps_fl, p.wheel_rps_fr, p.wheel_rps_rl, p.wheel_rps_rr)
    radius = (p.tyre_radius_fl, p.tyre_radius_fr, p.tyre_radius_rl, p.tyre_radius_rr)
    out = []
    for i in range(4):
        surface_ms = abs(rps[i]) * radius[i]
        out.append(surface_ms / p.speed_ms)
    return (out[0], out[1], out[2], out[3])


# How many rows are serialised per `json.dumps` call.
#
# **`json` does not release the GIL, and `zlib` does.** Measured 22 Aug 2026
# against a 100 Hz probe standing in for the audio callback, with
# `sys.setswitchinterval(0.0005)` already in force:
#
#     work on another thread   ms/call   worst callback lateness   blocks lost
#     pure-Python loop            19.6                    0.6 ms         0/12
#     zlib.compress                2.2                    0.5 ms          0/3
#     zlib.decompress              0.7                    0.3 ms          0/2
#     json.dumps                  29.3                   28.9 ms        12/19
#     json.loads                  23.8                   22.5 ms         9/16
#
# The switch interval only takes effect at bytecode boundaries, so it cannot
# pre-empt one long C call. A whole lap through `json.dumps` is ~30 ms of
# uninterruptible GIL - three audio blocks - at every lap crossing, about
# twenty-six times a race. That underfeed is what degrades the transducer's
# endpoint until the machine is rebooted, so this is a hardware fault with a
# software cause, not a latency nicety.
#
# Measured on a real 17,998-row lap, worst callback lateness against the same
# 100 Hz probe:
#
#     one dumps   144.5 ms/call    91.4 ms late   32 blocks lost
#     chunk  250  180.0 ms/call     0.9 ms late    0
#     chunk  500  179.3 ms/call     0.6 ms late    0
#     chunk 2000  178.3 ms/call     0.6 ms late    0
#
# The chunk size barely matters, which is the tell: the win comes from many
# SHORT `dumps` calls, each of which ends at a bytecode boundary the audio
# thread can be scheduled at, not from the slicing itself. 500 is picked for
# doing fewer joins than 250 with the same result.
#
# **It costs about 35 ms of wall time and is still a net saving**, because
# `_note_top_speed` used to decode the blob straight back - 99 ms - to take
# one maximum. The lap crossing goes from ~245 ms with 91 ms uninterruptible
# to ~181 ms with 0.6 ms.
ENCODE_CHUNK_ROWS = 500


# **The columnar blob, and why the row-of-JSON one had to go.**
#
# A lap is 41 channels x up to 26,000 frames of numbers, and it was stored as
# JSON rows. Measured on the longest lap on file:
#
#     zlib.decompress      4.9 ms
#     json.loads          43.7 ms   <- 69% of the decode
#     building the dicts  ~15   ms
#
# `json` also does not release the GIL, so every one of those decodes is tens
# of milliseconds in which the audio callback cannot run - the fault that
# degrades the transducer's endpoint. The encode side is worse: one lap
# through `json.dumps` held the GIL for 85 ms at every lap crossing.
#
# Columns rather than rows, packed as machine numbers rather than decimal
# text. The channels are strongly typed and strongly regular - 33 floats, 4
# integers, 4 single-character surface codes, and nulls in the four slip
# channels only - so each column packs into one `array` and compresses far
# better beside its own kind than interleaved with 40 others.
#
# `array('d')` is IEEE double, which is exactly what a Python float already
# is, and `array('q')` holds every integer these channels carry. So the round
# trip is EXACT rather than close, which matters: these numbers are the
# evidence every setup recommendation is built on, and a lap that changed in
# the fourth decimal on being re-read would be undetectable and wrong.
COLUMNAR_FORMAT = "pitcrew.frames.v2"

_KIND_FLOAT = "f"          # array('d')
_KIND_INT = "i"            # array('q')
_KIND_CHAR = "c"           # one byte per row
_KIND_NULL = "n"           # the column is entirely null; no data follows


def _scan_column(values) -> tuple[str | None, bytes, list]:
    """One pass: the column's kind, its null bitmap, and its present values.

    **One pass and not four.** The first version asked `_column_kind`, then
    `_pack_nulls`, then filtered out the Nones - three walks over every value
    on top of a pure-Python transpose, and the encode came out slower than
    the JSON it replaced. There are 2.6 million frames of 41 channels in this
    database; a redundant pass is 107 million operations.
    """
    kind = None
    mask = None
    present = []
    for index, value in enumerate(values):
        if value is None:
            if mask is None:
                mask = bytearray((len(values) + 7) // 8)
            mask[index >> 3] |= 1 << (index & 7)
            continue
        if isinstance(value, bool):
            return None, b"", []             # bool is an int subclass; refuse
        if isinstance(value, float):
            here = _KIND_FLOAT
        elif isinstance(value, int):
            here = _KIND_INT
        elif isinstance(value, str) and len(value) == 1 and value.isascii():
            here = _KIND_CHAR
        else:
            return None, b"", []
        if kind is None:
            kind = here
        elif kind != here:
            return None, b"", []             # mixed: int and float are not
        present.append(value)
    return (kind or _KIND_NULL), (bytes(mask) if mask else b""), present


def _column_kind(values: list) -> str | None:
    """How this column packs, or None if it does not.

    **Returning None is a supported answer and the whole safety story.** A
    column that mixes types, or carries something these three kinds cannot
    hold, sends the entire blob back to the JSON format rather than being
    coerced - because coercion here is silent data loss in the one table that
    cannot be regenerated. A lap recorded during a format change is worth more
    than the bytes it would save.
    """
    kind = None
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            return None                      # bool is an int subclass; refuse
        if isinstance(value, int):
            here = _KIND_INT
        elif isinstance(value, float):
            here = _KIND_FLOAT
        elif isinstance(value, str) and len(value) == 1 and value.isascii():
            here = _KIND_CHAR
        else:
            return None
        if kind is None:
            kind = here
        elif kind != here:
            return None                      # mixed: int and float are not
    return kind or _KIND_NULL


def _pack_nulls(values: list) -> bytes:
    """One bit per row, set where the value is null. Empty when none are."""
    if not any(value is None for value in values):
        return b""
    mask = bytearray((len(values) + 7) // 8)
    for index, value in enumerate(values):
        if value is None:
            mask[index >> 3] |= 1 << (index & 7)
    return bytes(mask)


def _encode_columnar(rows: list[list], version: int) -> bytes | None:
    """The columnar blob, or None if these rows cannot be held exactly."""
    count = len(rows)
    if not rows or len(rows[0]) != len(FRAME_FIELDS):
        return None
    # `zip(*rows)` transposes in C. Done as a comprehension it was the single
    # largest cost in the encode.
    columns = zip(*rows)

    meta, chunks = [], []
    for name, values in zip(FRAME_FIELDS, columns):
        kind, nulls, present = _scan_column(values)
        if kind is None:
            return None
        meta.append({"n": name, "k": kind, "z": len(nulls)})
        chunks.append(nulls)
        if kind == _KIND_NULL:
            continue
        if kind == _KIND_CHAR:
            chunks.append("".join(present).encode("ascii"))
        else:
            packed = array.array("d" if kind == _KIND_FLOAT else "q", present)
            # Little-endian on the wire, whatever the machine is, so a blob
            # written on one box reads on another.
            if sys.byteorder != "little":
                packed.byteswap()
            chunks.append(packed.tobytes())

    header = json.dumps({"format": COLUMNAR_FORMAT, "v": version,
                         "fields": list(FRAME_FIELDS), "count": count,
                         "cols": meta}, separators=(",", ":")).encode("utf-8")
    body = b"".join(chunks)
    return zlib.compress(len(header).to_bytes(4, "little") + header + body, 6)


def _decode_columnar(raw: bytes) -> list[dict] | None:
    """Rows back out of a v2 blob, or None if this is not one."""
    if len(raw) < 4:
        return None
    size = int.from_bytes(raw[:4], "little")
    if size <= 0 or size + 4 > len(raw):
        return None
    try:
        header = json.loads(raw[4:4 + size].decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if header.get("format") != COLUMNAR_FORMAT:
        return None

    fields = header["fields"]
    count = int(header["count"])
    version = int(header.get("v", 1))
    at = 4 + size
    columns: list[list] = []
    for column in header["cols"]:
        kind, nulls_len = column["k"], int(column["z"])
        mask = raw[at:at + nulls_len]
        at += nulls_len
        missing = [bool(mask[i >> 3] & (1 << (i & 7))) for i in range(count)]             if nulls_len else None
        if kind == _KIND_NULL:
            columns.append([None] * count)
            continue
        present_count = count - (sum(missing) if missing else 0)
        if kind == _KIND_CHAR:
            values = list(raw[at:at + present_count].decode("ascii"))
            at += present_count
        else:
            code = "d" if kind == _KIND_FLOAT else "q"
            packed = array.array(code)
            width = packed.itemsize * present_count
            packed.frombytes(raw[at:at + width])
            if sys.byteorder != "little":
                packed.byteswap()
            values = packed.tolist()
            at += width
        if missing is None:
            columns.append(values)
        else:
            out, source = [], iter(values)
            for gone in missing:
                out.append(None if gone else next(source))
            columns.append(out)

    return [dict(zip(fields, row), **{_VERSION_KEY: version})
            for row in zip(*columns)] if columns else []


def encode_frames(rows: list[list], *,
                  version: int = FRAME_SCHEMA_VERSION) -> bytes:
    """The lap's rows, as the stored blob.

    **`version` is the blob's own schema stamp and is a parameter for one
    reason: anything that RE-ENCODES an existing lap must carry the original
    across.** It decides how the analysis reads the lap - `grip.yaw_source_for`
    takes yaw from the stored path below version 2 and off the packet at 2 and
    above, and the two differ by 3-4% at the top of the acceleration
    distribution, which is the same size as the compound step the tyre model
    exists to detect.

    Proved the hard way, 23 Aug 2026, on a throwaway migration script that
    re-encoded the database columnar without preserving it: every v1 lap came
    back stamped 2, the analysis switched yaw source underneath it, and one
    event's export moved `yawDeficitPct` from 0.2 to 42.0 and changed the
    wheelspin flag counts on nearly every corner. Nothing raised. That is
    exactly the failure the stamp exists to prevent, arriving through the one
    door nobody had thought to close.

    The live path never re-encodes - `LapRecorder.encode` is the only caller
    and it has a fresh lap - so the default is right for everything that
    exists today, and a future migration has to say what it means.

    Serialised in slices and fed straight into a streaming deflate rather
    than built as one string. `json.dumps(list, separators=(",", ":"))` is
    exactly `"[" + ",".join(dumps(row)) + "]"`, so the JSON is byte-identical
    to the single-call form; only the compressed framing differs, and the
    contract on disk is "zlib of this JSON", not one particular deflate
    stream. See `ENCODE_CHUNK_ROWS`.
    """
    columnar = _encode_columnar(rows, version)
    if columnar is not None:
        return columnar

    # **The fallback, and it is not dead code.** `_encode_columnar` returns
    # None for anything it cannot hold exactly - a column that mixes integers
    # and floats, a channel carrying something new - and the answer to that is
    # to store the lap the old way, not to coerce it. The chunking below is
    # still what keeps `json.dumps` from holding the GIL for 85 ms when this
    # path is taken.
    dumps = json.dumps
    tight = {"separators": (",", ":")}
    # Tight separators in the head too, or the field list comes out as
    # `["t_ms", "road_plane_d"]` against the single-call form's
    # `["t_ms","road_plane_d"]` - which decodes the same but is not the
    # byte-identical blob this docstring claims. Checked: identical.
    head = ('{"format":%s,"v":%s,"fields":%s,"rows":['
            % (dumps(BLOB_FORMAT, **tight),
               dumps(version, **tight),
               dumps(list(FRAME_FIELDS), **tight)))
    packer = zlib.compressobj(6)
    out = [packer.compress(head.encode("utf-8"))]
    first = True
    for start in range(0, len(rows), ENCODE_CHUNK_ROWS):
        chunk = ",".join(dumps(row, **tight)
                         for row in rows[start:start + ENCODE_CHUNK_ROWS])
        out.append(packer.compress((chunk if first else "," + chunk)
                                   .encode("utf-8")))
        first = False
    out.append(packer.compress(b"]}"))
    out.append(packer.flush())
    return b"".join(out)


# 500 km/h is the sanity bound, and the reason is in `Store`: the speed
# channel drops to exactly 0.0 for runs of frames mid-straight, which a
# maximum is immune to, but a spike upward is not - and one bad frame would
# move a divisor for every future session at this circuit.
MAX_PLAUSIBLE_KPH = 500.0
_SPEED_INDEX = FRAME_FIELDS.index("speed_kph")


def top_speed_kph(rows: list[list]) -> float | None:
    """The fastest plausible frame of the lap, off the uncompressed rows.

    None when nothing plausible was seen - missing is null, never zero, and a
    zero here would ratchet an event's reference speed down to nothing.
    """
    best = None
    for row in rows:
        value = row[_SPEED_INDEX]
        if value is None or not 0.0 < value < MAX_PLAUSIBLE_KPH:
            continue
        if best is None or value > best:
            best = value
    return None if best is None else round(best, 1)


def clock_span(rows: list[list]) -> tuple[int | None, int | None]:
    """GT7's clock at the first and last frame that carried it.

    First and last *present*, not first and last row: the channel is absent
    from packet formats below `~`, and a lap that starts before the stream
    settles can open on nulls without the rest of it being unreadable.
    """
    stamps = [row[_TOD_INDEX] for row in rows
              if len(row) > _TOD_INDEX and row[_TOD_INDEX] is not None]
    return (stamps[0], stamps[-1]) if stamps else (None, None)


def standing_start_ms(rows: list[list], sample_hz: float = SAMPLE_HZ) -> int | None:
    """Milliseconds from the first recorded frame until the car set off.

    `None` where the speed channel is absent. `0` is a real answer and means
    the car was already moving when the recording picked it up.
    """
    rate = sample_hz or SAMPLE_HZ
    for index, row in enumerate(rows):
        if len(row) <= _SPEED_INDEX or row[_SPEED_INDEX] is None:
            continue
        if row[_SPEED_INDEX] > _MOVING_KPH:
            return int(round(index * 1000.0 / rate))
    return None


def decode_frames(blob: bytes) -> list[dict]:
    """Inverse of `encode_frames`, as a list of per-frame dicts.

    Each frame carries the blob's schema version under `_VERSION_KEY`, which is
    how `repair_frames` tells a lap recorded before the yaw and slip fixes from
    one recorded after. It strips the key again, so nothing downstream of the
    repair sees it.
    """
    raw = zlib.decompress(blob)
    # **Every lap already on disk is v1 and stays readable.** 366 of them, and
    # the raw stream is the one thing in this database that cannot be
    # regenerated - so the reader knows both formats for good, rather than the
    # blobs being migrated. A migration that goes wrong here loses the
    # evidence every setup recommendation is built on.
    columnar = _decode_columnar(raw)
    if columnar is not None:
        return columnar

    payload = json.loads(raw.decode("utf-8"))
    fields = payload["fields"]
    version = int(payload.get("v", 1))
    return [dict(zip(fields, row), **{_VERSION_KEY: version})
            for row in payload["rows"]]


def _repair_distance_and_clock(frames: list[dict], rate: float) -> list[dict]:
    """Integrate a lap distance and re-derive `t_ms` from the frame index.

    * **`lap_distance_m` did not exist.** What was recorded as distance was the
      road plane's fourth coefficient. Speed integrated at the known sample
      rate lands within a percent or two of the circuit's published length and
      does so consistently lap to lap, which is what corner windows need.
    * **`t_ms` was GT7's in-game clock.** Frozen in a fixed-time event and
      running at many times real speed in a day-to-night one, so laps came out
      spanning 0 s or 970 s where the lap took 110 s. Every corner metric timed
      against it - trail-brake duration, time loss, consistency - was scaled by
      whatever the event's time multiplier happened to be. The frame index at
      the sample rate is the real elapsed time.

    A lap already carrying `lap_distance_m` was recorded after the fix and is
    left exactly as it is. A lap with no speed channel is left alone too: the
    distance stays absent and the corner model reports no corners, which is
    honest.
    """
    if frames[0].get("lap_distance_m") is not None:
        return frames
    if all(frame.get("speed_kph") is None for frame in frames):
        return frames
    distance = 0.0
    out = []
    for index, frame in enumerate(frames):
        speed = frame.get("speed_kph")
        if speed is not None:
            distance += speed / 3.6 / rate
        out.append({**frame,
                    "lap_distance_m": round(distance, 2),
                    "t_ms": int(round(index * 1000.0 / rate))})
    return out


def ground_track_yaw(frames: list[dict], rate: float = SAMPLE_HZ) -> list[float | None]:
    """Yaw rate reconstructed from the stored path, rad/s, one per frame.

    **This is ground-track yaw, not body yaw.** The two differ by the rate of
    change of chassis sideslip: second order for corner metrics and the
    understeer flag, and emphatically not second order for a sideslip channel.
    Nothing that needs body attitude may be built on a column repaired from
    this.

    **Sign.** This is the *y component of angular velocity*, which in a
    right-handed frame is the negative of the heading rate: for planar motion
    `r x v` has j-component `-R^2 * dtheta/dt` where `theta = atan2(z, x)`.
    That is also what the capture set demands - it integrates to -360.3 deg per
    lap here, and all three circuits in it are clockwise.

    Whether GT7's own `angvel_y` carries the same sign is **not yet verified**:
    thirty seconds of live capture settles it, and until then a v1 lap repaired
    here and a v2 lap recorded from the packet agree in magnitude but only
    presumptively in sign. Every consumer today takes `abs()`.

    **Heading is undefined when the car is not moving.** Below the displacement
    a car at `_MOVING_KPH` covers over the stencil, the direction of travel is
    1 cm of position rounding and the honest answer is `None` - never a
    carried-forward heading and never 0.0, which reads downstream as "not
    rotating any harder" and quietly satisfies the understeer detector.
    """
    half = max(1, int(round(_YAW_STENCIL_S * rate)))
    # The displacement a car at walking pace covers over the full stencil. At
    # the ends of the lap the stencil narrows and this floor is stricter than
    # it needs to be, which is the safe direction to be wrong in.
    floor_m = (_MOVING_KPH / 3.6) * (2 * half / rate)
    count = len(frames)
    xs = [frame.get("pos_x") for frame in frames]
    zs = [frame.get("pos_z") for frame in frames]

    headings: list[float | None] = []
    for index in range(count):
        first, last = max(0, index - half), min(count - 1, index + half)
        x0, z0, x1, z1 = xs[first], zs[first], xs[last], zs[last]
        if x0 is None or z0 is None or x1 is None or z1 is None:
            headings.append(None)
            continue
        dx, dz = x1 - x0, z1 - z0
        headings.append(math.atan2(dz, dx)
                        if math.hypot(dx, dz) >= floor_m else None)

    out: list[float | None] = []
    for index in range(count):
        first, last = max(0, index - half), min(count - 1, index + half)
        before, after = headings[first], headings[last]
        if before is None or after is None or last == first:
            out.append(None)
            continue
        turned = (after - before + math.pi) % _TWO_PI - math.pi
        out.append(-turned / ((last - first) / rate))
    return out


def _repair_rotation_and_slip(frames: list[dict], rate: float) -> list[dict]:
    """Put yaw, lateral g and slip back on a v1 lap.

    Yaw and `lat_g` are recovered from the path rather than re-captured - see
    `ground_track_yaw` for what that costs and what it cannot be used for.
    Slip is recovered arithmetically, by dividing out the 2pi that should never
    have been there, so no information is lost at all.

    The slip channels below `_MIN_SPEED_FOR_SLIP_MS` become `None`. v1 wrote a
    synthetic 1.0 there, and the 2pi error was the only thing making that
    fabrication detectable - a genuine rolling-true reading stored as 6.283, so
    an exact 1.0 could only be the placeholder. Dividing by 2pi without also
    nulling the floor would hide it for good.
    """
    yaw_rates = ground_track_yaw(frames, rate)
    out = []
    for frame, yaw_rate in zip(frames, yaw_rates):
        speed = frame.get("speed_kph")
        repaired = {
            **frame,
            "yaw_rate": _round(yaw_rate, 4),
            "lat_g": (None if yaw_rate is None or speed is None else
                      round(abs(speed / 3.6 * yaw_rate) / 9.81, 3)),
        }
        unmeasurable = speed is not None and speed / 3.6 < _MIN_SPEED_FOR_SLIP_MS
        for corner in _SLIP_FIELDS:
            value = frame.get(corner)
            repaired[corner] = (None if unmeasurable or value is None
                                else round(value / _TWO_PI, 4))
        out.append(repaired)
    return out


def repair_frames(frames: list[dict],
                  sample_hz: float = SAMPLE_HZ) -> list[dict]:
    """Bring a stored lap up to the current schema, on read.

    Four channels were wrong in laps captured before now, and every one of them
    is recoverable from what *was* stored - which is why 132 recorded laps are
    repaired here rather than thrown away and re-driven. `lap_distance_m` and
    `t_ms` are rebuilt for any lap that lacks a distance channel; `yaw_rate`,
    `lat_g` and the four slip channels are rebuilt for any blob stamped below
    `FRAME_SCHEMA_VERSION`.

    Frames that did not come out of `decode_frames` carry no version stamp and
    are assumed current: a caller holding hand-built frames is holding
    already-correct ones, and dividing their slip by 2pi would invent a defect.
    """
    if not frames:
        return frames
    rate = sample_hz or SAMPLE_HZ
    version = frames[0].get(_VERSION_KEY, FRAME_SCHEMA_VERSION)
    frames = _repair_distance_and_clock(frames, rate)
    if version < FRAME_SCHEMA_VERSION:
        frames = _repair_rotation_and_slip(frames, rate)
    for frame in frames:
        frame.pop(_VERSION_KEY, None)
    return frames


class LapRecorder:
    """Buffers frames for the lap in progress and hands them over on completion."""

    def __init__(self, sample_every: int = 1) -> None:
        # sample_every=1 is full rate.  Exposed only so a test can thin the
        # stream; the app should never raise it.
        self._sample_every = max(1, sample_every)
        self._lock = threading.Lock()
        self._counter = 0
        self._rows: list[list] = []
        self._lap_start_packet: int | None = None
        self._last_packet_id: int | None = None
        self._distance_m = 0.0
        self._dropped_off_track = 0
        # Packets seen but not recorded, in packet-counter units. Subtracted
        # from `elapsed` so a lap's clock measures time on track rather than
        # time since the lap's first frame.
        self._dropped_packets = 0
        # Packets the stream never delivered, counted from breaks in GT7's
        # own packet id. Session-cumulative and deliberately NOT reset per
        # lap: this is a health measure of the feed, not a property of a lap.
        self._stream_gaps = 0
        self._lost_packets = 0

    @property
    def frame_count(self) -> int:
        with self._lock:
            return len(self._rows)

    @property
    def stream_gaps(self) -> int:
        """How many breaks appeared in GT7's packet id this session."""
        with self._lock:
            return self._stream_gaps

    @property
    def lost_packets(self) -> int:
        """How many packets those breaks account for."""
        with self._lock:
            return self._lost_packets

    def record_frame(self, packet: GT7Packet) -> None:
        """Called from the UDP thread for every packet."""
        with self._lock:
            self._counter += 1
            if self._counter % self._sample_every != 0:
                return
            if not packet.car_on_track or packet.paused or packet.loading:
                self._dropped_off_track += 1
                # **The excursion is charged to neither counter.** Both are
                # measured against the packet id, so a frame that is dropped
                # still has to close its own gap or the next recorded frame
                # pays for the whole thing: 30 s paused mid-lap integrated the
                # resume speed across 1,800 packets and recorded 1,600 m of
                # lap distance for 100 m driven, and reported `t_ms` 32,000
                # for 2,000 ms of driving. Corner windows are keyed on lap
                # distance, so one such lap renumbers every corner at that
                # circuit.
                if self._last_packet_id is not None:
                    self._dropped_packets += max(
                        0, packet.packet_id - self._last_packet_id)
                self._last_packet_id = packet.packet_id
                return

            # The clock is the packet counter, not GT7's time of day.
            # `time_of_day_ms` is the *in-game* clock: it is frozen at a fixed
            # time of day and runs at many times real speed in a day-to-night
            # event, so laps recorded through one came out spanning 0 s and
            # laps through the other 970 s - for a 110 s lap. Everything timed
            # off it was wrong by whatever multiplier the event happened to
            # use. The counter ticks once per packet at a known 60 Hz.
            if self._lap_start_packet is None:
                self._lap_start_packet = packet.packet_id
                # Anything dropped before the lap's first recorded frame is
                # not part of this lap's clock at all.
                self._dropped_packets = 0
            elapsed = max(0, int(round(
                (packet.packet_id - self._lap_start_packet
                 - self._dropped_packets) * MS_PER_PACKET)))

            # Distance around the lap, integrated from speed. GT7 broadcasts
            # no lap-distance channel at all, and corner identity is a window
            # of lap distance, so this is what makes corners possible. Stepped
            # by the gap since the previous packet so a dropped packet costs
            # its own distance rather than shifting everything after it.
            step = 1 if self._last_packet_id is None else max(
                1, packet.packet_id - self._last_packet_id)
            # **A gap here is the stream losing packets, and it is counted.**
            # The arithmetic above absorbs it correctly, which is exactly the
            # problem: distance is integrated across the gap at the speed on
            # the far side of it, and the result is a lap that looks clean.
            # CLAUDE.md 7 wants the connection to fail loudly, so the loss is
            # recorded rather than silently smoothed over. Not counted for
            # the first frame of a session, where there is nothing to compare
            # against, nor for the deliberate skips above, which are the
            # driver being in the menus rather than the network dropping.
            if step > 1:
                self._stream_gaps += 1
                self._lost_packets += step - 1
            self._last_packet_id = packet.packet_id
            self._distance_m += packet.speed_ms * step / SAMPLE_HZ

            slip = _slip_ratios(packet)
            # Yaw is rotation about the vertical axis, and up is world +Y.
            # See the `yaw_rate` entry in FRAME_FIELDS for the three proofs.
            yaw_rate = packet.angvel_y
            lat_g = abs(packet.speed_ms * yaw_rate) / 9.81
            steer_rad = packet.steering
            steer_deg = None if steer_rad is None else round(math.degrees(steer_rad), 2)
            steer_norm = packet.steering_norm
            steer_norm = None if steer_norm is None else round(steer_norm, 4)
            surface = packet.surface_types or (None, None, None, None)

            self._rows.append([
                elapsed,
                round(packet.road_distance, 2),
                round(packet.speed_kmh, 2),
                round(packet.throttle * 100.0, 1),
                round(packet.brake * 100.0, 1),
                steer_deg,
                steer_norm,
                packet.current_gear,
                round(packet.engine_rpm, 0),
                round(yaw_rate, 4),
                round(lat_g, 3),
                round(packet.pos_x, 2), round(packet.pos_y, 2), round(packet.pos_z, 2),
                _round(slip[0], 4), _round(slip[1], 4),
                _round(slip[2], 4), _round(slip[3], 4),
                round(packet.suspension_fl * 1000.0, 2),
                round(packet.suspension_fr * 1000.0, 2),
                round(packet.suspension_rl * 1000.0, 2),
                round(packet.suspension_rr * 1000.0, 2),
                round(packet.tyre_temp_fl, 1), round(packet.tyre_temp_fr, 1),
                round(packet.tyre_temp_rl, 1), round(packet.tyre_temp_rr, 1),
                round(packet.body_height * 1000.0, 2),
                surface[0], surface[1], surface[2], surface[3],
                round(packet.road_plane_y, 4),
                1 if packet.rev_limiter_active else 0,
                round(packet.tyre_radius_rl, 4),
                round(self._distance_m, 2),
                packet.time_of_day_ms,
                round(packet.fuel_level, 3),
                round(packet.vel_x, 3), round(packet.vel_y, 3),
                round(packet.vel_z, 3),
                _round(packet.road_wheel_angle, 5),
                packet.laps_completed if packet.laps_completed >= 0 else None,
                packet.last_lap_ms if packet.last_lap_ms > 0 else None,
                packet.flags_raw,
            ])

    def take_rows(self) -> list[list]:
        """Detach the lap in progress, without compressing it.

        This must run on the telemetry thread the instant a lap completes: any
        frame recorded after the lap boundary but before the swap belongs to
        the next lap, and compressing ~7,200 rows takes long enough to drop
        packets if it happens inline. The caller compresses afterwards, off the
        socket loop.
        """
        with self._lock:
            rows = self._rows
            self._rows = []
            self._lap_start_packet = None
            self._last_packet_id = None
            self._distance_m = 0.0
            self._dropped_off_track = 0
            self._dropped_packets = 0
        return rows

    def encode(self, rows: list[list]) -> LapFrames | None:
        """Compress detached rows. Safe to call from any thread."""
        if not rows:
            return None
        start, end = clock_span(rows)
        rate = SAMPLE_HZ / self._sample_every
        return LapFrames(
            frame_count=len(rows),
            sample_hz=rate,
            blob=encode_frames(rows),
            tod_start_ms=start,
            tod_end_ms=end,
            standing_start_ms=standing_start_ms(rows, rate),
            top_kph=top_speed_kph(rows),
        )

    def take_lap(self) -> LapFrames | None:
        """Detach and compress in one step. Convenient off the hot path."""
        return self.encode(self.take_rows())

    def discard(self) -> None:
        with self._lock:
            self._rows = []
            self._lap_start_packet = None
            self._last_packet_id = None
            self._distance_m = 0.0
            self._dropped_packets = 0
