"""What the engineer says while the tank is filling.

The driver asked for this in as many words: *"It also needs to pick up when
fuel is going up and read out again what fuel volume (calculated from current
race) what litres I need to leave the pits with."*

The box call already names a figure - "Box this lap. RH. Fuel to 74 litres" -
but it is said a lap and a half before the fuel starts moving, and it is sized
by the plan's picture of the race rather than by the race. **This one is said
with the hose in the car**, off the burn this race has actually shown and the
laps that are actually left, and it is followed by the only call that removes
the gauge from the job entirely: when to go.

### Why a second call here does not break the one-thing-at-a-time rule

CLAUDE.md §5.5 is about calls made at racing speed under a helmet. In the box
the car is stationary, the driver is doing nothing, and the thing he is
otherwise doing is reading a number off a gauge and waiting for it. A release
call is not a second instruction competing with the first - it is the end of
the first one.

### The three measurements this rests on

All from the Monza race of 18 Aug 2026, session 52, the only stop of the race:

* **The fuel channel never rises while driving.** Zero frame-to-frame rises in
  5999 green-flag frames. So a rise is a fill and nothing else, and the
  detector does not need a wide gate to be safe - the last one was three times
  the signal it was looking for and reported `is_pit_lap` 0 on all 132 laps.
* **The fill runs at 1.002 L/s**, which agrees with the 1.001 L/s measured at
  Watkins the day before. One litre is one second and sixty frames, so a
  release call has about a second of resolution and cannot be late by a
  rounding error.
* **Fuel starts moving 5.3 s after the wheels stop.** The dead time is real
  and it is why the watch arms on the fuel rising rather than on the car
  stopping: arming on the stop would spend its first five seconds looking at a
  tank that is not filling yet.
"""
from __future__ import annotations

from dataclasses import dataclass

# **A rise this big is a fill.** Sized against a channel that produced no
# spurious rise at all across 5999 driving frames, so this is not a noise
# gate - it is the smallest move that cannot be a single bad packet, and at
# the measured 1.002 L/s it arms a quarter of a second into the fill.
FILL_RISE_L = 0.25

# Consecutive rising frames before the watch believes it. One frame is a
# glitch, three at 60 Hz is 50 ms of a fill that lasts a minute.
FILL_RISE_FRAMES = 3

# Above this the car is not in a pit box. The stop itself sits at 0 km/h and
# the crawl detector elsewhere uses 15 km/h; this is deliberately looser than
# both, because the only thing it has to exclude is a fuel reading that rises
# while the car is going somewhere - which has never been observed.
FILL_MAX_KPH = 15.0

# How much the tank may sit under target and still be called done. The target
# already carries its own margin and GT7's pump is continuous, so this only
# exists to stop a release call hanging on the last hundredth of a litre.
RELEASE_EPSILON_L = 0.05

# **Short of target by less than this and it is not worth a word.** The same
# epsilon the fuel call uses before it bothers reporting what a short-shift
# leaves uncovered.
SHORT_EPSILON_L = 0.5
# How much bigger the to-the-flag fill has to be before it is worth naming as
# an alternative in the box. Under a couple of litres the two plans are the
# same stop and a second number is noise at the one moment he cannot afford
# any. Two litres is also two seconds on the measured 1.001 L/s rig.
TO_FLAG_EPSILON_L = 2.0

TARGET = "refuel-target"
RELEASE = "refuel-release"
SHORT = "refuel-short"


@dataclass(frozen=True)
class RefuelCall:
    """One thing to say in the box."""
    kind: str
    call: str
    reason: str = ""

    def spoken(self) -> str:
        return f"{self.call} {self.reason}".strip()


class RefuelWatch:
    """Watches one stop: arms on the fill, calls the target, calls the release.

    Pure arithmetic on floats. `note` is called from the telemetry thread at
    60 Hz and does nothing at all until the tank starts climbing, which is
    once a race.

    The caller owns the target, and owns it deliberately: sizing a fill is the
    strategy layer's job and it already does it from the race's own burn. This
    class only decides *when* the number is worth saying and when the tank has
    reached it.
    """

    def __init__(self) -> None:
        self._rising = 0
        self._low_l: float | None = None
        self._prev_l: float | None = None
        self._filling = False
        self._target_l: float | None = None
        self._said_target = False
        self._said_release = False
        self._said_short = False
        # The tank at the moment the fill was first seen, so the stop's own
        # figures can be reported afterwards without re-deriving them.
        self.started_l: float | None = None
        self.peak_l: float | None = None

    @property
    def filling(self) -> bool:
        return self._filling

    def reset(self) -> None:
        """A new stop. Called on pit exit - never mid-fill."""
        self.__init__()

    def note(self, fuel_l: float | None, *, speed_kph: float | None,
             target_l: float | None,
             fuel_per_lap_l: float | None = None,
             to_flag_l: float | None = None,
             basis: str | None = None) -> RefuelCall | None:
        """One frame. Returns what to say, or None - which is almost always.

        `target_l` is what the tank should read at pit exit, recomputed by the
        caller from the race in progress. It is **captured once**, when the
        fill is first seen: the car is stationary for the whole of it, so
        nothing that feeds the figure can move while the hose is in, and a
        target that wobbled mid-fill would be chatter rather than news.
        """
        if fuel_l is None:
            return None
        if speed_kph is not None and speed_kph > FILL_MAX_KPH:
            # Driving. Track the tank down so the next stop measures its rise
            # from where the car actually arrived.
            self._rising = 0
            self._low_l = fuel_l
            self._prev_l = fuel_l
            return None

        prev = self._prev_l
        self._prev_l = fuel_l
        if self._low_l is None or fuel_l < self._low_l:
            self._low_l = fuel_l
        if self.peak_l is None or fuel_l > self.peak_l:
            self.peak_l = fuel_l

        if not self._filling:
            if prev is not None and fuel_l > prev:
                self._rising += 1
            else:
                self._rising = 0
            if (self._rising < FILL_RISE_FRAMES
                    or self._low_l is None
                    or fuel_l - self._low_l < FILL_RISE_L):
                return None
            self._filling = True
            self.started_l = self._low_l
            self._target_l = target_l

        target = self._target_l
        if target is None:
            # Filling, but nothing sized the stop - no burn measured, or no
            # idea how many laps are left. **Silence is the right answer and
            # a guessed litre figure is not**: he is holding the trigger on a
            # number, and one the app invented is worse than none.
            return None

        if not self._said_target:
            self._said_target = True
            if fuel_l >= target - RELEASE_EPSILON_L:
                # Already covered before the fill got going. The most valuable
                # call in the race: every litre from here is a second parked.
                self._said_release = True
                return RefuelCall(
                    RELEASE, "Go.",
                    f"{fuel_l:.0f} litres aboard - that already covers it."
                    + _to_flag_clause(to_flag_l, target))
            # **The bound, not just the count.** "10 laps at this race's
            # burn" was said at Deep Forest with 7 to go - the count was the
            # plan's stint and nothing said so. The basis names which bound
            # produced the figure; the lap count is derived from it and is
            # kept for the case where no basis was handed over.
            return RefuelCall(TARGET, f"Fuel to {_ceil_l(target)} litres.",
                              (f"{basis[0].upper() + basis[1:]}, at this "
                               f"race's burn." if basis
                               else _laps_reason(target, fuel_per_lap_l))
                              + _to_flag_clause(to_flag_l, target))

        if not self._said_release and fuel_l >= target - RELEASE_EPSILON_L:
            self._said_release = True
            # **Called AT the target, not before it.** His reaction time times
            # the measured 1.002 L/s is the overshoot, so being late costs
            # about a litre - one second in the pit lane. Being early costs
            # fuel he cannot get back, and this app does not run him dry to
            # save a second. Same direction as the fill call's "round up,
            # never to nearest".
            return RefuelCall(RELEASE, "Go.", f"{fuel_l:.0f} litres aboard.")
        return None

    def left_early(self, fuel_l: float | None, *,
                   fuel_per_lap_l: float | None = None
                   ) -> RefuelCall | None:
        """Pit exit. Says how short he is, if he is short and it matters.

        Called by the coordinator on PIT_EXIT rather than from the frame path,
        because "he has left" is an event and not a fuel reading. Short by
        less than `SHORT_EPSILON_L` is not worth a word; short by more is a
        lift-and-coast he can start on the next straight, which is the whole
        reason to say it at pit exit rather than three laps later when the
        estimate finally crosses a threshold.
        """
        target = self._target_l
        if (not self._filling or self._said_short or self._said_release
                or target is None or fuel_l is None):
            return None
        self._said_short = True
        short = target - fuel_l
        if short < SHORT_EPSILON_L:
            return None
        laps = (short / fuel_per_lap_l) if fuel_per_lap_l else None
        reason = (f"{short:.0f} litres light - about {laps:.1f} laps."
                  if laps is not None else f"{short:.0f} litres light.")
        return RefuelCall(SHORT, "Save fuel from here.", reason)


class RefuelAdviser:
    """A watch, where its numbers come from, and where its words go.

    The 60 Hz frame path lives on `TelemetryBridge` and the race lives on the
    controller, so something has to carry the target across. Same shape as the
    qualifying coach: the controller builds it with a `speak` callable and
    hands it over, and the frame path calls one method and knows nothing else.

    `context` returns `(target_l, fuel_per_lap_l, to_flag_l, basis)` for the
    race right now - `basis` being the bound that sized the target, in words -
    or None where nothing can size a stop. It is called **only when the car is
    slow enough to be in a pit box**, because it re-derives the fill from the
    race's own burn and that is not free sixty times a second for an hour.
    """

    def __init__(self, *, context, speak) -> None:
        self.watch = RefuelWatch()
        self._context = context
        self._speak = speak

    @property
    def filling(self) -> bool:
        return self.watch.filling

    def note_frame(self, fuel_l: float | None,
                   speed_kph: float | None) -> None:
        target = fuel_per_lap = to_flag = basis = None
        if speed_kph is not None and speed_kph <= FILL_MAX_KPH:
            found = self._context()
            if found is not None:
                # Three values from an older context, four from the
                # controller's: the fourth is the bound behind the figure.
                target, fuel_per_lap, to_flag = found[:3]
                basis = found[3] if len(found) > 3 else None
        call = self.watch.note(fuel_l, speed_kph=speed_kph, target_l=target,
                               fuel_per_lap_l=fuel_per_lap,
                               to_flag_l=to_flag, basis=basis)
        if call is not None:
            self._speak(call)

    def note_pit_exit(self, fuel_l: float | None) -> None:
        """Pit exit: say how short he left, then a clean watch for the next
        stop. Both, in that order - resetting first would throw away the
        target the shortfall is measured against."""
        found = self._context()
        call = self.watch.left_early(
            fuel_l, fuel_per_lap_l=found[1] if found else None)
        if call is not None:
            self._speak(call)
        self.watch.reset()


def _to_flag_clause(to_flag_l: float | None, target_l: float | None) -> str:
    """" Nn to the flag if you stay out.", or nothing.

    Only where staying out is a live alternative: a figure that is already
    covered by the planned fill is not a choice, and one the tank cannot hold
    is not an option. See `calls.fuel_to_flag_l` for why it is said at all.
    """
    if to_flag_l is None or target_l is None:
        return ""
    if to_flag_l <= target_l + TO_FLAG_EPSILON_L:
        return ""
    # **Litres, and it is the one place "N to the flag" is not laps** (row
    # 1.10): every other site says "1.4 laps short of the flag". Adjacency
    # rescues a big number; "9 to the flag" beside "9 laps after the box"
    # does not.
    return f" {_ceil_l(to_flag_l)} litres to the flag if you stay out."


def _ceil_l(litres: float) -> int:
    """Round up, never to nearest - the spoken figure is what he dials in."""
    return int(litres) if litres == int(litres) else int(litres) + 1


def _laps_reason(target: float, fuel_per_lap_l: float | None) -> str:
    if not fuel_per_lap_l:
        return ""
    return f"{target / fuel_per_lap_l:.0f} laps at this race's burn."
