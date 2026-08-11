"""Running the race: arm, wait for green, follow the plan, adapt.

Two rules from the brief shape this:

* **Nothing fires until the race actually starts.** Start Race arms the
  coordinator; the plan does not begin until the car is on track and the
  start/finish line has been crossed. Arming is not starting.
* **The plan is refused if it was built for a different race.** A stint plan
  from another car, track or race length is worse than no plan, because the
  driver would act on it.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass

from pitcrew.race.calls import Call, RaceState, clear_stint, next_call
from pitcrew.telemetry.session_state import EventKind, Phase


class RacePhase(enum.Enum):
    IDLE = "idle"          # not armed
    ARMED = "armed"        # waiting for the car to go green
    RUNNING = "running"
    FINISHED = "finished"


@dataclass(frozen=True)
class PlanContext:
    """What the approved plan was built for."""
    car: str
    track: str
    layout: str | None
    race_laps: int

    def matches(self, other: "PlanContext") -> tuple[bool, str]:
        if self.car != other.car:
            return False, f"plan was built for {self.car}, car is {other.car}"
        if self.track != other.track:
            return False, f"plan was built for {self.track}, track is {other.track}"
        if self.layout != other.layout:
            return False, (f"plan was built for the {self.layout} layout, "
                           f"this is {other.layout}")
        if self.race_laps != other.race_laps:
            return False, (f"plan was built for {self.race_laps} laps, "
                           f"this race is {other.race_laps}")
        return True, ""


class RaceCoordinator:
    """Turns telemetry events into engineer calls against an approved plan."""

    def __init__(self, plan: dict | None = None,
                 fuel_per_lap_l: float | None = None,
                 wear_per_lap: float | None = None) -> None:
        self.phase = RacePhase.IDLE
        self.plan = plan or {}
        self.state = RaceState(
            fuel_per_lap_l=fuel_per_lap_l, wear_per_lap=wear_per_lap)
        self.refusal: str | None = None
        self.planned_fuel_per_lap_l = fuel_per_lap_l
        self._burns: list[float] = []
        self._stints = list(self.plan.get("stints") or ())
        self._apply_stint(0)

    # ------------------------------------------------------------------ arming

    def arm(self, planned: PlanContext | None,
            actual: PlanContext | None) -> bool:
        """Ready the race. Returns False, with a reason, if the plan does not fit."""
        self.refusal = None
        if planned is not None and actual is not None:
            ok, why = planned.matches(actual)
            if not ok:
                self.refusal = why
                return False
        if actual is not None:
            self.state.laps_total = actual.race_laps
        self.phase = RacePhase.ARMED
        return True

    def disarm(self) -> None:
        self.phase = RacePhase.IDLE

    @property
    def armed(self) -> bool:
        return self.phase is RacePhase.ARMED

    @property
    def running(self) -> bool:
        return self.phase is RacePhase.RUNNING

    # ------------------------------------------------------------------ laps

    def _apply_stint(self, index: int) -> None:
        self.state.stint_index = index
        if index >= len(self._stints):
            self.state.stint_ends_on_lap = None
            self.state.next_compound = None
            return
        stint = self._stints[index]
        start = stint.get("start_lap") or 1
        self.state.stint_ends_on_lap = start + stint.get("laps", 0) - 1
        following = self._stints[index + 1] if index + 1 < len(self._stints) else None
        self.state.next_compound = following.get("compound") if following else None
        # The last stint runs to the flag; there is no stop at the end of it.
        if following is None:
            self.state.stint_ends_on_lap = None

    def handle(self, event, packet=None) -> Call | None:
        """Feed one telemetry event. Returns the call to make, if any."""
        if event.kind is EventKind.RACE_STARTED:
            return self._on_green(event)
        if self.phase is not RacePhase.RUNNING:
            return None
        if event.kind is EventKind.LAP_COMPLETED:
            return self._on_lap(event, packet)
        if event.kind is EventKind.PIT_ENTRY:
            self.state.in_pit = True
            return None
        if event.kind is EventKind.PIT_EXIT:
            self.state.in_pit = False
            clear_stint(self.state)
            self._apply_stint(self.state.stint_index + 1)
            return None
        if event.kind is EventKind.RACE_FINISHED:
            return self._on_finish(event)
        return None

    def _on_green(self, event) -> Call | None:
        if self.phase is not RacePhase.ARMED:
            # Arming is not starting, and a race that started without being
            # armed is not this app's race.
            return None
        self.phase = RacePhase.RUNNING
        if event.data.get("laps_in_race"):
            self.state.laps_total = event.data["laps_in_race"]
        return self._emit()

    # Below this the race has not shown enough of its own burn to trust it
    # over the practice figure.
    BURN_LAPS_NEEDED = 3

    def _on_lap(self, event, packet) -> Call | None:
        lap = event.data["lap"]
        self.state.lap = lap.lap_num
        self.state.laps_since_stop += 1
        self.state.fuel_l = lap.fuel_end
        if lap.position:
            self.state.position = lap.position

        # Fuel calls must use what this race is actually burning, not what
        # practice suggested. Told he could push while burning 35% more than
        # planned, the driver would run dry - and the number that produced
        # that advice would have looked perfectly reasonable.
        if lap.fuel_used > 0:
            self._burns.append(lap.fuel_used)
        if len(self._burns) >= self.BURN_LAPS_NEEDED:
            ordered = sorted(self._burns)
            self.state.fuel_per_lap_l = ordered[len(ordered) // 2]

        return self._emit()

    def observed_fuel_per_lap(self) -> float | None:
        if len(self._burns) < self.BURN_LAPS_NEEDED:
            return None
        ordered = sorted(self._burns)
        return ordered[len(ordered) // 2]

    def _on_finish(self, event) -> Call | None:
        self.phase = RacePhase.FINISHED
        self.state.finished = True
        if event.data.get("position"):
            self.state.position = event.data["position"]
        return self._emit()

    def _emit(self) -> Call | None:
        call = next_call(self.state)
        if call is not None:
            self.state.said.append(call.kind)
        return call

    def stops_planned(self) -> int:
        """Stops still in the plan from here, for the re-plan comparison."""
        return max(0, len(self._stints) - 1 - self.state.stint_index)

    def adopt(self, stint_laps) -> None:
        """Take on a re-plan the driver accepted.

        The stints already completed are left alone: what changes is the
        shape of the race from here, not a rewrite of what already happened.
        The stint currently running is replaced, not kept - keeping it would
        leave the stop at the end of it in the plan, which is exactly the stop
        the driver just cancelled.
        """
        done = self._stints[:self.state.stint_index]
        start = self.state.lap + 1
        fresh = []
        for laps in stint_laps:
            fresh.append({"laps": laps, "compound": None, "fuel_l": None,
                          "start_lap": start})
            start += laps
        self._stints = done + fresh
        self._apply_stint(self.state.stint_index)

    # ---------------------------------------------------------------- answers

    def snapshot(self) -> dict:
        """What the pit wall shows, and what the PTT answers from."""
        return {
            "phase": self.phase.value,
            "lap": self.state.lap,
            "lapsTotal": self.state.laps_total,
            "lapsRemaining": self.state.laps_remaining(),
            "position": self.state.position,
            "fuelL": self.state.fuel_l,
            "lapsOfFuel": self.state.laps_of_fuel(),
            "lapsToStop": self.state.laps_to_stop(),
            "nextCompound": self.state.next_compound,
            "inPit": self.state.in_pit,
        }


def context_from_event(event: dict, plan: dict | None = None) -> PlanContext:
    return PlanContext(
        car=event.get("car_name") or "",
        track=event.get("track") or "",
        layout=event.get("layout"),
        race_laps=int(event.get("race_laps") or 0),
    )


def phase_from_session(phase: Phase) -> RacePhase:
    """Map the telemetry phase onto the engineer's, for display only."""
    if phase is Phase.RACING:
        return RacePhase.RUNNING
    if phase is Phase.FINISHED:
        return RacePhase.FINISHED
    return RacePhase.ARMED
