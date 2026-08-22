"""Where in the capture a lap happened — without anyone typing an offset.

`tools/read_hud_wear.py` already reads the tyre gauge out of an OBS recording,
and it aligns the video to the race the only way it could: `recorded_at` on
each lap gives the shape of the race exactly, and **the zero point is supplied
by hand** with `--offset`. Its own comment admits what that costs — the zero is
taken as lap 1's crossing less lap 1's time, "which ignores the standing start
and is therefore a few seconds early".

**The app can know the zero exactly instead of guessing at it.** `ObsSource`
has been able to start and stop the recording since the day it was written and
nothing ever called it. If the app starts the recording, then the wall clock at
which video second zero occurred is not a estimate, it is a fact the app wrote
down — and every lap's position in the capture follows by subtraction.

    video_seconds(lap) = lap.recorded_at - session.video_started_at

No vision, no cross-correlation, no offset to type, and it is exact to whatever
the two clocks agree on — which is the same clock, since both stamps are taken
on this machine.

### What this does not do

**It does not find a corner in the video.** It could: a lap's frames carry
`lap_distance_m` and `t_ms`, so a corner's apex is a known number of seconds
into the lap. That is `seconds_into_lap` below and it is exposed. But it rests
on the integrated distance, and the 22 Aug measurement found that unreliable on
8-12% of laps — so a corner seek is offered with the lap's own length beside it
and the caller decides whether to trust it.

**It does not know about a recording the app did not start.** A capture made by
hand has no stored zero, and this says so rather than guessing one. The offline
tool's `--offset` remains the way in for those.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

# A recording that started AFTER the first lap it is supposed to contain is not
# an alignment problem, it is a different recording. Allow a little slack for
# the two stamps being taken microseconds apart, then refuse.
CLOCK_SLACK_S = 2.0


@dataclass(frozen=True)
class VideoIndex:
    """A session's capture, and where each lap sits in it."""

    path: str | None
    started_at: dt.datetime | None
    # {lap_num: seconds into the video at that lap's CROSSING}
    crossings: dict[int, float]

    @property
    def usable(self) -> bool:
        return self.started_at is not None and bool(self.crossings)

    def at_lap(self, lap_num: int) -> float | None:
        """Video seconds at the moment that lap was completed."""
        return self.crossings.get(lap_num)

    def lap_window(self, lap_num: int) -> tuple[float, float] | None:
        """(start, end) of a lap in video seconds.

        The lap's start is the previous crossing. **The first lap has no
        previous crossing**, so it has no start here rather than a start of
        zero - the recording may well have been running while the car sat on
        the grid, and calling that the lap's beginning would put every seek on
        lap 1 minutes early.
        """
        end = self.crossings.get(lap_num)
        start = self.crossings.get(lap_num - 1)
        if end is None or start is None:
            return None
        return start, end

    def timestamp(self, seconds: float) -> str:
        """`H:MM:SS` — what a video player wants to be told."""
        seconds = max(0.0, seconds)
        hours, rest = divmod(int(seconds), 3600)
        minutes, secs = divmod(rest, 60)
        return f"{hours}:{minutes:02d}:{secs:02d}"


def _parse(stamp) -> dt.datetime | None:
    if stamp is None:
        return None
    if isinstance(stamp, dt.datetime):
        return stamp
    try:
        return dt.datetime.fromisoformat(str(stamp))
    except ValueError:
        return None


def build(session: dict, laps: list[dict]) -> VideoIndex:
    """Index one session's laps against its own capture.

    `laps` are store rows, needing `lap_num` and `recorded_at` - the wall clock
    stamped at each crossing, which is what makes the shape of the race exact.
    """
    started = _parse(session.get("video_started_at"))
    path = session.get("video_path")
    if started is None:
        return VideoIndex(path=path, started_at=None, crossings={})

    crossings: dict[int, float] = {}
    for lap in laps:
        at = _parse(lap.get("recorded_at"))
        if at is None or lap.get("lap_num") is None:
            continue
        offset = (at - started).total_seconds()
        if offset < -CLOCK_SLACK_S:
            # **A lap before the recording began.** Not an alignment error to
            # be corrected - the capture simply does not contain it, and
            # placing it at second zero would seek to the wrong lap silently.
            continue
        crossings[int(lap["lap_num"])] = max(0.0, offset)
    return VideoIndex(path=path, started_at=started, crossings=crossings)


def seconds_into_lap(frames: list[dict], distance_m: float) -> float | None:
    """How far into a lap, in seconds, the car reached a lap distance.

    **Rests on the integrated distance**, which the 22 Aug measurement found
    unreliable on 8-12% of laps - so a caller seeking a corner should weigh
    this against the lap's own integrated length. `t_ms` is the frame index at
    the sample rate, which is real elapsed time.
    """
    best = None
    for frame in frames:
        got = frame.get("lap_distance_m")
        stamp = frame.get("t_ms")
        if got is None or stamp is None:
            continue
        if got >= distance_m:
            best = stamp
            break
    if best is None:
        return None
    first = next((f["t_ms"] for f in frames if f.get("t_ms") is not None), None)
    if first is None:
        return None
    return (best - first) / 1000.0
