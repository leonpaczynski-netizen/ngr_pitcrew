"""GT7 telemetry packet parser.

GT7 on PS5 sends Salsa20-encrypted UDP packets.  SimHub re-broadcasts those
raw encrypted bytes to 127.0.0.1:33741.  We decrypt here before parsing.

Decryption (from Nenkai's PDTools / granturismo package):
  Key   : b'Simulator Interface Packet GT7 v'  (32 bytes)
  IV    : read bytes [64:68] of the ENCRYPTED packet as LE uint32 → iv1
          iv2 = iv1 ^ 0xDEADBEAF
          nonce = pack('<II', iv2, iv1)  (8 bytes)
  Cipher: Salsa20 XOR over the full 296-byte buffer

Magic check (after decryption):
  bytes 0-3 in the decrypted packet are the LE-stored int32 0x47375330.
  That means the actual bytes are b'0S7G' (= b'G7S0'[::-1]).

All field offsets are verified against the granturismo open-source packet model:
  https://github.com/snipem/gt7dashboard / granturismo PyPI package
"""
from __future__ import annotations
import struct
from dataclasses import dataclass
from Crypto.Cipher import Salsa20

PACKET_SIZE     = 296   # minimum bytes we parse (original GT7 struct size)
PACKET_SIZE_NEW = 368   # GT7 v1.3+ extended packet; same field layout, 72 extra bytes

# Decrypted bytes 0-3 are 0x30,0x53,0x37,0x47 (= LE int32 0x47375330 = 'G7S0')
VALID_MAGIC: set[bytes] = {b'0S7G', b'1S7G'}

_SALSA_KEY = b'Simulator Interface Packet GT7 v'   # 32 bytes
# GT7 changed the IV mask from 0xDEADBEAF to 0xDEADBEEF in a 2024 update.
# The extended-packet format (368 bytes) uses the new mask exclusively.
_IV_MASK_NEW = 0xDEADBEEF   # current
_IV_MASK_OLD = 0xDEADBEAF   # pre-2024 (kept for fallback)


def _decrypt(data: bytes) -> bytes:
    """Apply Salsa20 decryption to raw GT7 packet bytes.

    Tries the current mask (0xDEADBEEF) first; falls back to the legacy mask
    (0xDEADBEAF) so both the original 296-byte and new 368-byte formats work.
    """
    # The nonce is stored PLAINTEXT at offset 64 in the encrypted packet.
    iv1 = struct.unpack_from('<I', data, 64)[0]

    # Try new mask first (GT7 v1.3+ / 368-byte extended format)
    iv2 = iv1 ^ _IV_MASK_NEW
    nonce = struct.pack('<II', iv2, iv1)
    dec = Salsa20.new(key=_SALSA_KEY, nonce=nonce).decrypt(data)
    if dec[0:4] in VALID_MAGIC:
        return dec

    # Fallback: original mask for pre-2024 / 296-byte format
    iv2 = iv1 ^ _IV_MASK_OLD
    nonce = struct.pack('<II', iv2, iv1)
    return Salsa20.new(key=_SALSA_KEY, nonce=nonce).decrypt(data)


# Struct covering all parsed fields.  Offsets verified from granturismo source.
#
# Running byte offset:
# 0x00=0    magic            4s
# 0x04=4    pos xyz          3f  (12)
# 0x10=16   vel xyz          3f  (12)
# 0x1C=28   rot p/y/r        3f  (12)
# 0x28=40   orientation      f   (4)
# 0x2C=44   angvel xyz       3f  (12)
# 0x38=56   body_height      f   (4)
# 0x3C=60   engine_rpm       f   (4)
# 0x40=64   [nonce – skip]   4x
# 0x44=68   fuel_level       f   (4)
# 0x48=72   fuel_capacity    f   (4)
# 0x4C=76   speed_ms         f   (4)
# 0x50=80   turbo_boost      f   (4)
# 0x54=84   oil_pressure     f   (4)
# 0x58=88   water_temp       f   (4)
# 0x5C=92   oil_temp         f   (4)
# 0x60=96   tyre_temp 4f     (16)
# 0x70=112  packet_id        I   (4)
# 0x74=116  laps_completed   h   (2) signed; NOT reliable lap count — do not use for race finish
# 0x76=118  laps_in_race     h   (2) signed; -1 = timed, 0 = unlimited, N = N-lap race
# 0x78=120  best_lap_ms      i   (4) signed; -1 = no time set
# 0x7C=124  last_lap_ms      i   (4) signed; -1 = no time set
# 0x80=128  time_of_day_ms   I   (4) unsigned ms
# 0x84=132  start_pos_cars   I   (4) byte0=live_pos, byte1=0, byte2=total_cars, byte3=0
# 0x88=136  rpm_alert_min    H   (2)
# 0x8A=138  rpm_alert_max    H   (2)
# 0x8C=140  car_max_speed_r  H   (2)
# 0x8E=142  flags_raw        H   (2) 16-bit flags
# 0x90=144  gear_raw         B   (1)
# 0x91=145  throttle_raw     B   (1)
# 0x92=146  brake_raw        B   (1)
# 0x93=147  [skip]           x
# 0x94=148  road_plane xyz   3f  (12)
# 0xA0=160  road_distance    f   (4)
# 0xA4=164  wheel_rps 4f     (16)
# 0xB4=180  tyre_radius 4f   (16)
# 0xC4=196  suspension 4f    (16)
# 0xD4=212  unused_0xD4      i   (4) possibly race position
# 0xD8=216  [skip]           2x
# 0xDA=218  remaining_time_ms i  (4) signed; -1 for lap races / not in race
# 0xDE=222  [skip]           22x
# 0xF4=244  clutch           f   (4)
# 0xF8=248  clutch_engage    f   (4)
# 0xFC=252  clutch_gbx_rpm   f   (4)
# 0x100=256 trans_max_spd    f   (4)
# 0x104=260 gear_ratios      8f  (32)
# 0x124=292 car_id           i   (4)
# = 296 bytes total
_FMT = struct.Struct(
    '<'
    '4s'    # [0]     magic
    '3f'    # [1-3]   pos xyz
    '3f'    # [4-6]   vel xyz
    '3f'    # [7-9]   rot pitch/yaw/roll
    'f'     # [10]    orientation
    '3f'    # [11-13] angvel xyz
    'f'     # [14]    body_height
    'f'     # [15]    engine_rpm
    '4x'    # nonce at 0x40 – skip
    'f'     # [16]    fuel_level
    'f'     # [17]    fuel_capacity
    'f'     # [18]    speed_ms
    'f'     # [19]    turbo_boost
    'f'     # [20]    oil_pressure
    'f'     # [21]    water_temp
    'f'     # [22]    oil_temp
    '4f'    # [23-26] tyre_temp FL/FR/RL/RR
    'I'     # [27]    packet_id
    'h'     # [28]    laps_completed (signed; NOT reliable for race finish — see offset comment)
    'h'     # [29]    laps_in_race   (signed; -1 = timed, 0 = unlimited, N = N-lap race)
    'i'     # [30]    best_lap_ms    (signed; -1 = no time set)
    'i'     # [31]    last_lap_ms    (signed; -1 = no time set)
    'I'     # [32]    time_of_day_ms
    'I'     # [33]    start_pos_and_cars
    'H'     # [34]    rpm_alert_min
    'H'     # [35]    rpm_alert_max
    'H'     # [36]    car_max_speed_raw
    'H'     # [37]    flags_raw (16-bit)
    'B'     # [38]    gear_raw
    'B'     # [39]    throttle_raw
    'B'     # [40]    brake_raw
    'x'     # unused_0x93 – skip
    '3f'    # [41-43] road_plane xyz
    'f'     # [44]    road_distance
    '4f'    # [45-48] wheel_rps FL/FR/RL/RR
    '4f'    # [49-52] tyre_radius FL/FR/RL/RR
    '4f'    # [53-56] suspension FL/FR/RL/RR
    'i'     # [57]    unused_0xD4 (possible race position)
    '2x'    # skip 0xD8-0xD9
    'i'     # [58]    remaining_time_ms at 0xDA (signed; -1 for lap races)
    '22x'   # skip 0xDE-0xF3
    'f'     # [59]    clutch
    'f'     # [60]    clutch_engagement
    'f'     # [61]    clutch_gearbox_rpm
    'f'     # [62]    transmission_max_speed
    '8f'    # [63-70] gear_ratios
    'i'     # [71]    car_id
)

assert _FMT.size == PACKET_SIZE, f"Struct size {_FMT.size} != {PACKET_SIZE}"


@dataclass(frozen=True)
class GT7Packet:
    magic: bytes
    pos_x: float;       pos_y: float;       pos_z: float
    vel_x: float;       vel_y: float;       vel_z: float
    rot_pitch: float;   rot_yaw: float;     rot_roll: float
    orientation: float
    angvel_x: float;    angvel_y: float;    angvel_z: float
    body_height: float
    engine_rpm: float
    fuel_level: float
    fuel_capacity: float
    speed_ms: float
    turbo_boost: float
    oil_pressure: float
    water_temp: float
    oil_temp: float
    tyre_temp_fl: float; tyre_temp_fr: float
    tyre_temp_rl: float; tyre_temp_rr: float
    packet_id: int
    laps_completed: int      # signed int16; NOT reliable for race finish (GT7 field at 0x74)
    laps_in_race: int        # signed int16; -1 = timed/unlimited; 0 = unlimited; N = lap count
    best_lap_ms: int         # signed int32; -1 = none set
    last_lap_ms: int         # signed int32; -1 = none
    time_of_day_ms: int
    start_pos_and_cars: int  # bits[31:4] = start_pos, bits[7:0] = cars_in_race
    rpm_alert_min: int
    rpm_alert_max: int
    car_max_speed_raw: int
    flags_raw: int           # 16-bit; bit0=on_track, bit1=paused, bit2=loading
    gear_raw: int            # nibble low=current, nibble high=suggested
    throttle_raw: int        # 0-255
    brake_raw: int           # 0-255
    road_plane_x: float;  road_plane_y: float;  road_plane_z: float
    road_distance: float
    wheel_rps_fl: float;  wheel_rps_fr: float
    wheel_rps_rl: float;  wheel_rps_rr: float
    tyre_radius_fl: float; tyre_radius_fr: float
    tyre_radius_rl: float; tyre_radius_rr: float
    suspension_fl: float; suspension_fr: float
    suspension_rl: float; suspension_rr: float
    unused_0xD4: int              # may contain current race position
    remaining_time_ms: int        # GT7 race timer (ms); -1 for lap races / when not in race
    clutch: float
    clutch_engagement: float
    clutch_gearbox_rpm: float
    transmission_max_speed: float
    gear_ratio_1: float; gear_ratio_2: float; gear_ratio_3: float
    gear_ratio_4: float; gear_ratio_5: float; gear_ratio_6: float
    gear_ratio_7: float; gear_ratio_8: float
    car_id: int

    # ---------------------------------------------------------------- computed

    @property
    def speed_kmh(self) -> float:
        return self.speed_ms * 3.6

    @property
    def car_on_track(self) -> bool:
        return bool(self.flags_raw & 0x0001)

    @property
    def paused(self) -> bool:
        return bool(self.flags_raw & 0x0002)

    @property
    def loading(self) -> bool:
        return bool(self.flags_raw & 0x0004)

    @property
    def in_gear(self) -> bool:
        return bool(self.flags_raw & 0x0008)

    @property
    def rev_limiter_active(self) -> bool:
        return bool(self.flags_raw & 0x0020)

    @property
    def current_gear(self) -> int:
        return self.gear_raw & 0x0F

    @property
    def suggested_gear(self) -> int:
        g = (self.gear_raw >> 4) & 0x0F
        return 0 if g == 0x0F else g

    @property
    def tyre_temps(self) -> tuple[float, float, float, float]:
        return (self.tyre_temp_fl, self.tyre_temp_fr,
                self.tyre_temp_rl, self.tyre_temp_rr)

    @property
    def cars_in_race(self) -> int:
        # byte 2 (bits[23:16]) = total cars in race
        v = (self.start_pos_and_cars >> 16) & 0xFF
        return 0 if v == 255 else v

    @property
    def total_cars(self) -> int:
        """Alias used by state.py."""
        return self.cars_in_race

    @property
    def current_position(self) -> int:
        """Live race position (1-based).

        GT7 encodes four bytes at offset 0x84:
          byte 0 (bits[7:0])   = current race position (updates live)
          byte 1 (bits[15:8])  = 0 (unused / padding)
          byte 2 (bits[23:16]) = total cars in race
          byte 3 (bits[31:24]) = 0 (unused)
        """
        pos = self.start_pos_and_cars & 0xFF
        return pos if 1 <= pos <= 100 else 0

    @property
    def throttle(self) -> float:
        return self.throttle_raw / 255.0

    @property
    def brake(self) -> float:
        return self.brake_raw / 255.0

    @property
    def wheel_rps(self) -> tuple[float, float, float, float]:
        return (self.wheel_rps_fl, self.wheel_rps_fr,
                self.wheel_rps_rl, self.wheel_rps_rr)

    @property
    def tyre_radius(self) -> tuple[float, float, float, float]:
        return (self.tyre_radius_fl, self.tyre_radius_fr,
                self.tyre_radius_rl, self.tyre_radius_rr)

    @property
    def suspension(self) -> tuple[float, float, float, float]:
        return (self.suspension_fl, self.suspension_fr,
                self.suspension_rl, self.suspension_rr)

    @property
    def gear_ratios(self) -> list[float | None]:
        raw = [self.gear_ratio_1, self.gear_ratio_2, self.gear_ratio_3,
               self.gear_ratio_4, self.gear_ratio_5, self.gear_ratio_6,
               self.gear_ratio_7, self.gear_ratio_8]
        return [r if r > 0.0 else None for r in raw]

    @property
    def transmission_max_speed_kmh(self) -> float:
        return self.transmission_max_speed * 3.6


def parse_packet(data: bytes) -> GT7Packet | None:
    """Decrypt (if needed) and parse raw GT7 UDP bytes into a GT7Packet.

    Accepts both the original 296-byte format and the extended 368-byte
    format introduced in GT7 v1.3+.  Only the first 296 bytes are parsed;
    the extra bytes in the new format are safely ignored.
    """
    if len(data) < PACKET_SIZE:
        return None

    # Try decryption (normal path via SimHub raw relay).
    # If magic is already valid the bytes arrived pre-decrypted (rare).
    if data[0:4] not in VALID_MAGIC:
        try:
            data = _decrypt(data)
        except Exception:
            return None

    if data[0:4] not in VALID_MAGIC:
        return None   # still bad after decryption

    try:
        fields = _FMT.unpack(data[:PACKET_SIZE])
    except struct.error:
        return None
    return GT7Packet(*fields)


# ---------------------------------------------------------------------------
# Voice / display formatting helpers
# ---------------------------------------------------------------------------

def format_laptime_voice(ms: int) -> str:
    """Return ms as spoken lap time, e.g. '1 minute 12 seconds'."""
    if ms <= 0:
        return "no time"
    total_sec = ms // 1000
    minutes, seconds = divmod(total_sec, 60)
    if minutes == 0:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    return (f"{minutes} minute{'s' if minutes != 1 else ''} "
            f"{seconds} second{'s' if seconds != 1 else ''}")


def format_delta_voice(ms: int) -> str:
    """Return a delta in ms as spoken text, e.g. 'plus 1 point 8 seconds'."""
    sign = "plus" if ms >= 0 else "minus"
    abs_ms = abs(ms)
    seconds = abs_ms // 1000
    tenths  = (abs_ms % 1000) // 100
    if tenths == 0:
        return f"{sign} {seconds} second{'s' if seconds != 1 else ''}"
    return f"{sign} {seconds} point {tenths} seconds"


def format_remaining_time_voice(ms: int) -> str:
    """Return remaining time in ms as speech, e.g. '14 minutes 30 seconds'."""
    total_sec = max(ms // 1000, 0)
    minutes, seconds = divmod(total_sec, 60)
    if minutes > 0 and seconds > 0:
        return (f"{minutes} minute{'s' if minutes != 1 else ''} "
                f"{seconds} second{'s' if seconds != 1 else ''}")
    if minutes > 0:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    return f"{seconds} second{'s' if seconds != 1 else ''}"


def format_laptime_display(ms: int) -> str:
    """Return ms as M:SS.mmm for UI display."""
    if ms <= 0:
        return "--:--.---"
    minutes, remainder = divmod(ms, 60000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"
