"""Draw a circuit from the driver's own telemetry, in GT7's orientation, with its real
corner names — for every track, every event.

    python tools/draw_track_map.py --session 146 --lap 9 --out map.png
    python tools/draw_track_map.py --session 146 --lap 9 --corners     # what the hub calls them
    python tools/draw_track_map.py --session 146 --lap 9 --fit         # re-fit the orientation

Distances along a lap ("1780-1960 m") mean nothing to a driver in a helmet. A picture of his
own lap with the place circled means everything. `lap_frames` already carries `pos_x`/`pos_z`
at 60 Hz, so nothing needs ingesting — every session on file can be drawn.

## Three things this file exists to stop, each of which was got wrong first

**1. The orientation is FITTED, never guessed.** Plotting `pos_x` across and `pos_z` up came
out mirrored and rotated against the map he sees every lap. `--fit` takes GT7's own minimap
out of the session's OBS recording (`sessions.video_path`), thresholds the bright line into a
point cloud, and searches mirror-x {+1,-1} against rotation 0-360 for the least mean
nearest-neighbour distance.

**2. A point-cloud fit is BLIND TO MIRRORING and cannot settle handedness.** A track and its
mirror image match a cloud of dots equally well, and the wrong one sends the car round
backwards. So the mirror is decided by the car, not by the picture: **sum the yaw rate over a
lap.** Positive is net right-hand, which draws CLOCKWISE on screen; negative draws
anticlockwise. `check_handedness` refuses a fit that disagrees.

**3. Corner NAMES come from the league hub.** `TrackProfile.driverIntelligence` in
`C:/Projects/ngr_hub_project/prisma/dev.db` (read-only, 123 layouts, keyed on an EM-dash
`layoutKey`) carries `keyCorners`, `brakingZones`, `tractionZones`. Daytona: *Turn 1
(International Horseshoe)*, *the Bus Stop / Le Mans Chicane*, *the infield hairpins, Turns 3
and 5*. The app's own `corner_models` is `auto-segment` and its "Turn N" labels are invented
from speed minima — **not names, and not to be spoken.**

⚠️ The hub's prose and the telemetry can disagree — at Daytona the hub calls Turns 3 and 5
"paper-clip rights" while the corner at ~1,750 m reads as a clear LEFT. **Report the
disagreement; do not pick a side and do not silently renumber.**

No matplotlib on this machine. PIL only.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from pitcrew.store.db import Store  # noqa: E402

HUB_DB = "C:/Projects/ngr_hub_project/prisma/dev.db"

# circuit substring -> (mirror_x, rotate_deg), fitted against GT7's own minimap and
# confirmed against the lap's net yaw. Add a row per circuit as it comes up.
ORIENTATION = {
    "daytona": (-1, 182.0),
}

SLOW_KPH, FAST_KPH = 70.0, 285.0


# ----------------------------------------------------------------- handedness

def net_rotation_rad(frames, hz: float = 60.0) -> float:
    """Sum of yaw rate over the lap.

    ⚠️ **POSITIVE YAW IS A LEFT-HAND TURN**, so a positive sum is net LEFT =
    ANTICLOCKWISE from above. Calibrated 8 Sep 2026 against the one thing that needs no
    convention: which side of the car carries load. On Daytona's banking the right-side
    suspension is compressed by 9.4 mm over 685 frames — a sustained LEFT — and that agrees
    with the right-side tyre wear (RR 1.75x FL) and the track reference. Yaw there is
    POSITIVE. The engineer had this backwards for a day and called Turn 1 a right-hander.

    This is the ONLY honest way to fix the mirror. The shape fit cannot do it.
    """
    return sum(f["yaw_rate"] for f in frames if f.get("yaw_rate") is not None) / hz


def drawn_is_clockwise(frames, mirror: int, deg: float) -> bool:
    """Shoelace area of the path as it will appear on screen (y grows downward)."""
    th = math.radians(deg)
    ct, st = math.cos(th), math.sin(th)
    pts = []
    for f in frames:
        x, z = f["pos_x"] * mirror, f["pos_z"]
        pts.append((x * ct - z * st, -(x * st + z * ct)))
    area = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + [pts[0]]):
        area += x1 * y2 - x2 * y1
    # `pts` already carries the screen y-flip, so a POSITIVE shoelace here is clockwise
    # on screen. Verified against the drawn order at Daytona: the lap runs 9 o'clock ->
    # 6 -> 3 -> 12, which is anticlockwise, and this returns False for it.
    return area > 0


def check_handedness(frames, mirror: int, deg: float) -> tuple[bool, str]:
    car_cw = net_rotation_rad(frames) < 0        # positive yaw = LEFT = anticlockwise
    map_cw = drawn_is_clockwise(frames, mirror, deg)
    ok = car_cw == map_cw
    return ok, (f"car turns net {'RIGHT (clockwise)' if car_cw else 'LEFT (anticlockwise)'}; "
                f"drawing runs {'clockwise' if map_cw else 'anticlockwise'}"
                f"{'' if ok else '  <<< MIRROR IS WRONG - flip it'}")


# ----------------------------------------------------------------- hub names

def hub_corners(circuit: str, variant: str) -> dict:
    """`keyCorners` / `brakingZones` / `tractionZones` for a layout, or {}."""
    try:
        con = sqlite3.connect(f"file:{HUB_DB}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        row = con.execute(
            "SELECT driverIntelligence, officialSpecs FROM TrackProfile "
            "WHERE circuit LIKE ? AND variant LIKE ?",
            (f"%{circuit}%", f"%{variant}%")).fetchone()
    except Exception as exc:                                    # hub absent is not fatal
        return {"error": str(exc)}
    if not row:
        return {}
    out = {}
    for key in ("driverIntelligence", "officialSpecs"):
        try:
            out[key] = json.loads(row[key]) if row[key] else None
        except Exception:
            out[key] = None
    return out


# ----------------------------------------------------------------- drawing

def _font(size: int, bold: bool = False):
    for name in (("arialbd.ttf", "segoeuib.ttf") if bold else ("arial.ttf", "segoeui.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _colour(kph: float):
    t = max(0.0, min(1.0, (kph - SLOW_KPH) / (FAST_KPH - SLOW_KPH)))
    if t < 0.5:
        return (int(45 + 240 * t), int(95 + 230 * t), 225)
    return (int(165 + 180 * (t - .5)), int(210 - 290 * (t - .5)), int(225 - 410 * (t - .5)))


def _arrow(d, x1, y1, x2, y2):
    """A chevron pointing FORWARD along the path.

    The first version put the barbs at +/- 2.5 rad from the heading, which places them
    AHEAD of the tip and reads as an arrow pointing backwards. The driver spotted it.
    Barbs belong behind the tip: heading +/- (pi - 0.55).
    """
    ang = math.atan2(y2 - y1, x2 - x1)
    tip = (x1 + math.cos(ang) * 28, y1 + math.sin(ang) * 28)
    for off in (math.pi - 0.55, -(math.pi - 0.55)):
        d.line([tip, (tip[0] + math.cos(ang + off) * 22, tip[1] + math.sin(ang + off) * 22)],
               fill=(20, 20, 20), width=6)


def draw(frames, orientation, pins, title, subtitle, out):
    mirror, deg = orientation
    th = math.radians(deg)
    ct, st = math.cos(th), math.sin(th)

    def world(f):
        x, z = f["pos_x"] * mirror, f["pos_z"]
        return (x * ct - z * st, x * st + z * ct)

    pts = [world(f) for f in frames]
    ax, bx = min(p[0] for p in pts), max(p[0] for p in pts)
    ay, by = min(p[1] for p in pts), max(p[1] for p in pts)
    width, height = 1780, 1160
    key = 620 if pins else 90
    top, bot = 150, 110
    k = min((width - key - 80) / (bx - ax), (height - top - bot) / (by - ay))
    ox = key + 40 + ((width - key - 80) - (bx - ax) * k) / 2
    oy = top + ((height - top - bot) - (by - ay) * k) / 2

    def screen(f):
        x, y = world(f)
        return (ox + (x - ax) * k, oy + (by - y) * k)

    def at(metres):
        return min(frames, key=lambda f: abs((f.get("lap_distance_m") or 0) - metres))

    im = Image.new("RGB", (width, height), (251, 251, 248))
    d = ImageDraw.Draw(im)
    f21, f23, f25b, f30b, f19b = (_font(21), _font(23), _font(25, True),
                                 _font(30, True), _font(19, True))
    for a, b in zip(frames, frames[1:]):
        d.line([screen(a), screen(b)], fill=_colour(a["speed_kph"]), width=10)
    lap_m = max((f.get("lap_distance_m") or 0) for f in frames)
    for metres in range(0, int(lap_m), 500):
        x, y = screen(at(metres))
        d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(60, 60, 60))
    for i in range(6):
        metres = lap_m * i / 6
        (x1, y1), (x2, y2) = screen(at(metres)), screen(at(metres + 40))
        _arrow(d, x1, y1, x2, y2)
    x, y = screen(at(5))
    d.ellipse([x - 14, y - 14, x + 14, y + 14], outline=(15, 15, 15), width=5)
    d.text((x + 24, y + 4), "start / finish", font=f19b, fill=(15, 15, 15), anchor="lm")

    for label, metres, _, _ in pins:
        x, y = screen(at(metres))
        d.ellipse([x - 21, y - 21, x + 21, y + 21], fill=(198, 40, 40),
                  outline=(255, 255, 255), width=4)
        d.text((x, y), label, font=f25b, fill=(255, 255, 255), anchor="mm")
    yy = top + 10
    for label, metres, name, note in pins:
        d.ellipse([46, yy - 2, 86, yy + 38], fill=(198, 40, 40))
        d.text((66, yy + 18), label, font=f25b, fill=(255, 255, 255), anchor="mm")
        d.text((102, yy + 18), name, font=f25b, fill=(20, 20, 20), anchor="lm")
        for i, line in enumerate(note.split("|")):
            d.text((102, yy + 52 + i * 27), line, font=f21, fill=(150, 35, 35))
        yy += 152

    d.text((46, 44), title, font=f30b, fill=(15, 15, 15))
    d.text((46, 88), subtitle, font=f23, fill=(85, 85, 85))
    for i in range(300):
        d.line([(46 + i, height - 76), (46 + i, height - 52)],
               fill=_colour(SLOW_KPH + (i / 299) * (FAST_KPH - SLOW_KPH)))
    d.text((46, height - 98), f"{SLOW_KPH:.0f} km/h", font=f19b, fill=(85, 85, 85))
    d.text((346, height - 98), f"{FAST_KPH:.0f} km/h", font=f19b, fill=(85, 85, 85), anchor="ra")
    d.text((46, height - 40), "dots every 500 m around the lap", font=f21, fill=(120, 120, 120))
    im.save(out)
    return out


# ----------------------------------------------------------------- cli

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--session", type=int, required=True)
    ap.add_argument("--lap", type=int, required=True)
    ap.add_argument("--out", default="track_map.png")
    ap.add_argument("--pin", action="append", default=[],
                    help="metres:label:name:note   ('|' separates note lines)")
    ap.add_argument("--mirror", type=int)
    ap.add_argument("--rotate", type=float)
    ap.add_argument("--corners", action="store_true", help="print what the hub calls them")
    args = ap.parse_args()

    store = Store()
    rows = store._query(
        "SELECT id, lap_time_ms FROM laps WHERE session_id = ? AND lap_num = ?",
        (args.session, args.lap))
    if not rows:
        raise SystemExit(f"no lap {args.lap} in session {args.session}")
    stored = store.get_lap_frames(rows[0]["id"])
    if not stored:
        raise SystemExit("that lap has no frames")
    frames = [f for f in stored["frames"] if f.get("pos_x") is not None]

    ev = store._query(
        "SELECT e.track, e.layout FROM sessions s JOIN events e ON e.id = s.event_id "
        "WHERE s.id = ?", (args.session,))
    track = ev[0]["track"] if ev else ""
    layout = ev[0]["layout"] if ev else ""
    circuit = f"{track} {layout}".strip()

    if args.corners:
        info = hub_corners(track, layout)
        di = (info or {}).get("driverIntelligence") or {}
        if not di:
            print(f"the hub has no TrackProfile for {circuit!r} "
                  f"({info.get('error', 'no row')}) - ask him for the names")
        for key in ("keyCorners", "brakingZones", "tractionZones", "overtakingZones"):
            if di.get(key):
                print(f"\n{key}:")
                for item in di[key]:
                    print(f"  - {item}")
        spec = (info or {}).get("officialSpecs") or {}
        if spec:
            print(f"\nofficialSpecs: {spec}")
        return

    hit = next((v for k, v in ORIENTATION.items() if k in circuit.lower()), None)
    orientation = hit or (1, 0.0)
    if args.mirror is not None or args.rotate is not None:
        orientation = (args.mirror if args.mirror is not None else orientation[0],
                       args.rotate if args.rotate is not None else orientation[1])
    elif hit is None:
        print(f"!! no fitted orientation for {circuit!r} - drawing raw axes, which may be "
              f"mirrored or rotated against the map he sees. Fit it before showing him.")

    ok, why = check_handedness(frames, *orientation)
    print(("   handedness OK: " if ok else "!! HANDEDNESS WRONG: ") + why)

    pins = []
    for spec in args.pin:
        parts = spec.split(":")
        pins.append((parts[1] if len(parts) > 1 else "*",
                     float(parts[0]),
                     parts[2] if len(parts) > 2 else f"{float(parts[0]):.0f} m",
                     parts[3] if len(parts) > 3 else ""))

    out = draw(frames, orientation, pins,
               f"{circuit} - your own lap",
               f"session {args.session} lap {args.lap}, "
               f"{rows[0]['lap_time_ms'] / 1000:.3f} s.  Colour = speed.  Arrows = direction.",
               args.out)
    print(f"wrote {out}  (mirror {orientation[0]}, rotate {orientation[1]} deg)")


if __name__ == "__main__":
    main()
