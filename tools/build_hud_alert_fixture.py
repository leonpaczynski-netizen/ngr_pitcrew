"""Build `pitcrew/tests/fixtures/hud_alert_reads.npz` from real captures and a real log.

    python tools/build_hud_alert_fixture.py decode   # ~25 min: ffmpeg + the readers
    python tools/build_hud_alert_fixture.py pack     # the npz, from the decoded reads

The HUD alerts (`race/hud_alerts.py`) are replayed in the tests against what the
REAL readers made of REAL frames, sampled at the REAL grab cadence. Full crops
of a 31-minute race at the live rate would be tens of megabytes; the readers'
own outputs are a few kilobytes, and the readers themselves are pinned on real
crops in `test_hud_damage.py` and `test_hygrometer.py`.

**What is decoded**, every frame through `hud.locate_gauge`, `read_damage` and
`read_hygrometer` on the 220x140 wear-panel crop at x 280, y 930 of the flat
1080p HUD:

* session 166, Suzuka race, dry, 13 Sep 2026 - every 0.25 s, plus both contact
  episodes at 60 fps (rear 280-390 s, front 1255-1410 s) so the 2 Hz pulse is
  sampled as a grab would see it;
* session 176, Bathurst race, dry, 14 Sep 2026 - every 0.25 s (the pit stop's
  frames are in it);
* the driver's wet video, 14 Sep 2026 - every 0.1 s.

**And from the log** (`logs/pitcrew.log`): session 176's 1166 real intervals
between readable grabs, and its LIVE icon reads, rebuilt from the grabs and the
`hud-damage: ... lit/dim` transitions `HudSession._note_damage` wrote. A grab
between two transitions carries the last state; its px is the lit count when
lit and 0 when dim - the log keeps no sub-threshold px between transitions.

Decoded with `-hwaccel d3d11va`; checked against the software-decoded survey
frames (`front_22px_166_t1295` and its neighbours read the same counts).
"""
from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

VIDEOS = Path("C:/Users/leons/Videos/InstantReplays")
LOG = REPO / "logs" / "pitcrew.log"
CACHE = REPO / "logs" / "hud_alert_reads"
OUT = REPO / "pitcrew" / "tests" / "fixtures" / "hud_alert_reads.npz"
X0, Y0, W, H = 280, 930, 220, 140

SOURCES = {
    # name: (video, start s, duration s or None, fps)
    "s166_4fps": ("2026-09-13 20-23-32.mp4", 0.0, None, 4),
    "s166_rear60": ("2026-09-13 20-23-32.mp4", 280.0, 110.0, 60),
    "s166_front60": ("2026-09-13 20-23-32.mp4", 1255.0, 155.0, 60),
    "s176_4fps": ("2026-09-14 20-19-14.mp4", 0.0, None, 4),
    "wet10": ("2026-09-14 11-46-35.mp4", 0.0, 162.0, 10),
}
S176_START = "2026-09-14T20:19:14"
S176_END = "2026-09-14T21:03:47"


def _ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def decode(name: str) -> list:
    from pitcrew.telemetry.hud import locate_gauge
    from pitcrew.telemetry.hud_damage import read_damage
    from pitcrew.telemetry.hygrometer import read_hygrometer

    video, start, duration, fps = SOURCES[name]
    cmd = [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-hwaccel", "d3d11va"]
    if start:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", str(VIDEOS / video)]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vf", f"fps={fps},crop={W}:{H}:{X0}:{Y0}", "-pix_fmt", "rgb24",
            "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    rows, i = [], 0
    while True:
        buf = proc.stdout.read(W * H * 3)
        if len(buf) < W * H * 3:
            break
        frame = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
        t = round(start + i / fps, 3)
        i += 1
        bars = locate_gauge(frame.astype(int))
        if not bars:
            rows.append([t, None, None, None, None, None, "gauge not found"])
            continue
        hygro, damage = read_hygrometer(frame, bars), read_damage(frame, bars)
        rows.append([t, hygro.level, damage.front_px, damage.rear_px,
                     damage.front, damage.rear, hygro.why + "|" + damage.why])
    proc.wait()
    return rows


def _stamp(line: str) -> datetime.datetime:
    return datetime.datetime.strptime(line[:23], "%Y-%m-%d %H:%M:%S,%f")


def live_s176() -> tuple[list[float], list[list]]:
    """The live grab intervals and the live icon reads of session 176."""
    start = datetime.datetime.fromisoformat(S176_START)
    end = datetime.datetime.fromisoformat(S176_END)
    state = {"front": False, "rear": False}
    px = {"front": 0, "rear": 0}
    grabs: list[list] = []
    for line in LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("2026") or " hud-wear " not in line[24:50]:
            continue
        at = _stamp(line)
        if not start <= at <= end:
            continue
        found = re.search(r"hud-damage: (front|rear) arc (lit|dim) \((\d+) px\)",
                          line)
        if found:
            arc, lit = found.group(1), found.group(2) == "lit"
            state[arc], px[arc] = lit, int(found.group(3)) if lit else 0
            continue
        if ("reading accepted" in line or "reading refused" in line
                or "held until" in line):
            grabs.append([(at - start).total_seconds(),
                          px["front"] if state["front"] else 0,
                          px["rear"] if state["rear"] else 0])
    times = [g[0] for g in grabs]
    intervals = [b - a for a, b in zip(times, times[1:]) if b - a < 5.0]
    return intervals, grabs


def _px(rows, index) -> np.ndarray:
    return np.array([-1 if r[index] is None else r[index] for r in rows],
                    dtype=np.int16)


def _level(rows) -> np.ndarray:
    return np.array([np.nan if r[1] is None else r[1] for r in rows],
                    dtype=np.float32)


def pack() -> None:
    arrays: dict[str, np.ndarray] = {}
    for name, (_, start, _, fps) in SOURCES.items():
        rows = json.loads((CACHE / f"{name}.json").read_text())
        arrays[f"{name}__t0"] = np.array([start, fps], dtype=np.float64)
        arrays[f"{name}__level"] = _level(rows)
        arrays[f"{name}__front_px"] = _px(rows, 2)
        arrays[f"{name}__rear_px"] = _px(rows, 3)
    intervals, grabs = live_s176()
    arrays["s176_live__intervals"] = np.array(intervals, dtype=np.float32)
    arrays["s176_live__grabs"] = np.array(grabs, dtype=np.float32)
    np.savez_compressed(OUT, **arrays)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


def main() -> int:
    global LOG, CACHE
    if len(sys.argv) < 2 or sys.argv[1] not in ("decode", "pack"):
        print(__doc__)
        return 2
    # `--log` and `--cache` for a worktree, whose `logs/` is not the app's.
    for flag in ("--log", "--cache"):
        if flag in sys.argv:
            value = Path(sys.argv[sys.argv.index(flag) + 1])
            if flag == "--log":
                LOG = value
            else:
                CACHE = value
    if sys.argv[1] == "decode":
        CACHE.mkdir(parents=True, exist_ok=True)
        for name in SOURCES:
            rows = decode(name)
            (CACHE / f"{name}.json").write_text(json.dumps(rows))
            print(f"{name}: {len(rows)} frames")
        return 0
    pack()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
