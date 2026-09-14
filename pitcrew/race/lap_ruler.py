"""Where round the lap we are, live, integrated from speed.

**GT7 broadcasts no lap-distance channel.** `telemetry/recorder.py` integrates
one from speed at 60 Hz for the archive and `race/qualifying.py` does the same
thing live for a hot lap; this is the same integration for the race path, so
that a screen reading can be tagged with where on the road it was taken.

It exists because a gap with no track position attached cannot be binned into
sectors afterwards, and the position cannot be recovered later - the frame is
gone and so is the packet.

### It says when it does not know

About **7% of laps teleport** - the car is moved without travelling - and
speed integration cannot see that at all: the integrator keeps adding speed
times time while the car is somewhere else. What it CAN see is the consequence,
because a teleported lap does not come out the length of the circuit. So the
ruler reports its own confidence by comparing the finished lap against the
circuit, and a caller binning by distance is expected to throw those laps away
rather than bin them somewhere wrong.

Nothing here corrects a teleport. `analysis/distance.py` holds the offline
detector and its account of why 7% is the figure; this is the live half, and
live it can only refuse.
"""
from __future__ import annotations

from dataclasses import dataclass

# A finished lap this far from the circuit's own length did not measure the
# road. Same tolerance `race/sectors.py` applies, and for the same reason.
LENGTH_TOLERANCE = 0.08

# GT7 streams at 60 Hz. A packet id gap larger than this is a dropout, and the
# distance across it is guessed rather than integrated.
MAX_PACKET_STEP = 30
SAMPLE_HZ = 60.0


@dataclass
class LapRuler:
    """Metres travelled on this lap, and how much to trust the figure.

    Fed every packet; asked at any moment for the current distance. One per
    session and reset between them - CLAUDE.md rule 11, and a ruler carrying
    the last race's lap into this one puts every sector boundary in the wrong
    place.
    """
    circuit_length_m: float | None = None
    distance_m: float = 0.0
    lap: int | None = None
    dropped_packets: int = 0
    last_lap_length_m: float | None = None
    _last_packet_id: int | None = None

    def new_session(self) -> None:
        self.distance_m = 0.0
        self.lap = None
        self.dropped_packets = 0
        self.last_lap_length_m = None
        self._last_packet_id = None

    def note_packet(self, packet) -> None:
        """One 60 Hz packet. Never raises: the race matters more than the map."""
        try:
            raw_id = getattr(packet, "packet_id", None)
            if raw_id is None:
                # **Not a packet.** Counted as one with id 0 and speed 0, it
                # marked the ruler as fed and `where()` answered 0.0 m.
                return
            packet_id = int(raw_id)
            speed = float(getattr(packet, "speed_ms", 0.0) or 0.0)
        except (TypeError, ValueError):
            return
        if self._last_packet_id is None:
            step = 1
        else:
            step = packet_id - self._last_packet_id
            if step <= 0:
                return
            if step > MAX_PACKET_STEP:
                # A dropout. The distance across it is unknown, and adding
                # `speed * step` would assert the car held this speed through
                # a gap nobody saw.
                self.dropped_packets += 1
                self._last_packet_id = packet_id
                return
        self._last_packet_id = packet_id
        self.distance_m += speed * step / SAMPLE_HZ

    def crossed_line(self, lap: int | None = None) -> float | None:
        """Close the lap and start the next. Returns the finished lap's length."""
        finished = self.distance_m
        self.last_lap_length_m = finished
        self.distance_m = 0.0
        self.dropped_packets = 0
        self.lap = lap
        return finished

    # --- what it is worth -------------------------------------------------

    @property
    def believable(self) -> bool:
        """Whether the last finished lap measured the road.

        `False` where it came out the wrong length, which is what a teleport
        looks like from inside the integrator, and what a long dropout looks
        like too. Both mean the same thing to a caller: do not bin this lap.
        """
        if not self.circuit_length_m or self.last_lap_length_m is None:
            return False
        off = abs(self.last_lap_length_m - self.circuit_length_m)
        return off <= LENGTH_TOLERANCE * self.circuit_length_m

    def where(self) -> float | None:
        """Metres round the current lap, or `None` if it cannot be trusted.

        `None` once the integration has already lost packets on THIS lap -
        the figure would be short by an unknown amount, and a sector boundary
        placed with it is somewhere else on the road.

        **And `None` from a ruler that has never been fed a packet** (14 Sep
        2026). The controller built the ruler and the telemetry bridge was
        the one asked to feed it - on its own attribute, which nothing ever
        set - so `distance_m` sat at its starting 0.0 for five races and
        every one of 3,583 `gap_reads` rows, sessions 143-176, was filed at
        `track_m = 0.0`: the start line, for a reading nobody placed.
        CLAUDE.md rule 3. Zero metres is a place; "never fed" is not one.
        """
        if self._last_packet_id is None:
            return None
        if self.dropped_packets:
            return None
        if self.circuit_length_m and self.distance_m > (
                self.circuit_length_m * (1 + LENGTH_TOLERANCE)):
            return None                  # past the line without a crossing
        return self.distance_m
