"""Noticing an off or a spin while it is still happening.

`analysis/incidents.py` finds them beautifully and finds them **afterwards**:
it needs a whole lap of frames, because two of its three signals are spells
measured across one and its first test is time lost against the run's own
median. `coordinator.py` says the consequence out loud in a comment beside the
pace record - *"incidents cannot be flagged live, which is one more reason the
pace is a median and never a single lap"* - and the handover calls the same
thing P6: after a spin or an off, the plan's assumptions are stale and nothing
notices.

This is the live half. It is deliberately **one signal, not three**, and it is
the one the offline module's own measurement says is decisive:

    Every genuine incident in the capture set ends with the car at or near a
    standstill in the middle of a lap. Fourteen laps touch zero mid-lap and
    every one of them is an incident, a pit stop or an opening lap out of the
    box. The other hundred and eighteen have a tenth-percentile minimum of
    30 km/h, against a slowest corner around 60.

So `crawl` is the whole detector here, and the three exclusions in that
sentence - the pit stop, the lap out of the box, the grid - are what the
guards below are for. **The thresholds are imported, never restated**: a
detector that disagrees with the one that judges the same lap afterwards
produces two records of one race.

### What it deliberately does not do

**It does not try to catch a spin that kept moving.** The offline module needs
a reconstructed yaw channel and a whole lap to do that, and the measurement
behind `SPIN_YAW_RAD_S` shows how narrow the band is. A live detector that
guessed at it would strike clean laps, and striking a clean lap is worse than
missing an incident: the aggregate quietly loses a measurement nobody knows is
gone. The lap is still judged properly afterwards, by the module that can.

**It never speaks and never writes.** It answers one question - has the car
stopped mid-lap - and the caller decides what that is worth.
"""
from __future__ import annotations

from pitcrew.analysis.incidents import CRAWL_KPH, CRAWL_MIN_S, LAUNCH_KPH
from pitcrew.diagnostics import log


class IncidentWatch:
    """Per-frame, on the telemetry thread. Cheap, and it never raises.

    `update` returns True on the single frame an incident is confirmed, and
    False every other time - including every later frame of the same
    incident, so a car sitting in the gravel for twenty seconds is one event
    and not twelve hundred.
    """

    def __init__(self) -> None:
        self._crawling_for_s = 0.0
        self._last_at: float | None = None
        # **The car has to have gone somewhere first.** Without this the grid,
        # the box and a session joined stationary are all incidents - which is
        # the same trap `analysis/incidents.py` documents, and the reason
        # `LAUNCH_KPH` exists there.
        self._under_way = False
        self._fired_this_lap = False

    # ------------------------------------------------------------- lifecycle

    def new_lap(self) -> None:
        """A crossing. At most one incident is reported per lap."""
        self._fired_this_lap = False
        self._crawling_for_s = 0.0

    def reset(self) -> None:
        """Back to the box, or a session that has not started. Everything
        about where the car has been stops being true."""
        self._crawling_for_s = 0.0
        self._last_at = None
        self._under_way = False
        self._fired_this_lap = False

    # ----------------------------------------------------------------- input

    def update(self, packet, now: float, *, in_pit: bool = False) -> bool:
        """One frame. True exactly once per incident."""
        if packet is None:
            return False
        last, self._last_at = self._last_at, now
        if packet.paused or packet.loading or not packet.car_on_track:
            # **The clock must not run across a pause.** GT7 keeps sending
            # while paused and the car reads 0 km/h throughout, so a thirty
            # second pause is a thirty second crawl and every pause becomes an
            # incident. The quali coach documents the same hole from the
            # distance side.
            self._crawling_for_s = 0.0
            return False
        if in_pit:
            # A stop is a car stationary mid-lap by design. The pit lap is
            # already excluded on its own account.
            self._crawling_for_s = 0.0
            return False

        speed = packet.speed_kmh
        if speed > LAUNCH_KPH:
            self._under_way = True
        if not self._under_way or speed > CRAWL_KPH:
            self._crawling_for_s = 0.0
            return False

        # Elapsed between consecutive live frames, not a frame count: the feed
        # is nominally 60 Hz and measured at 59.88, and a dropped run of
        # packets would otherwise shorten a real crawl.
        if last is not None and now > last:
            self._crawling_for_s += now - last
        if self._crawling_for_s < CRAWL_MIN_S or self._fired_this_lap:
            return False

        self._fired_this_lap = True
        log("race").info(
            "incident: the car has been under %.0f km/h for %.1f s mid-lap",
            CRAWL_KPH, self._crawling_for_s)
        return True
