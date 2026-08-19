"""The things a race engineer says that are not instructions.

The driver asked for them: *"I wouldn't mind the engineer being more active
during the race. Think about things he could say to keep me engaged and
motivated during the race without overwhelming me."*

Colour calls are the radio a real engineer fills the quiet laps with - a
personal best, a run of consistent laps, how far to the stop. They are not
strategy and they never change what he does. **The whole design problem is the
second half of his sentence**, because this app's worst measured failure was
exactly this: the race of 16 Aug 2026 repeated one box call nine times, and
the fix was a register that speaks only on a material change. Adding a second
mouth to the same race without a budget would undo that.

So the rules here are stricter than the calls are interesting:

* **Nothing that isn't measured.** No gap to the car ahead, ever - there is no
  proximity channel in any packet format, and a gap the app invented is a lie
  told at 200 km/h. No pace verdicts either: his lap-to-lap sigma is wider
  than the whole degradation band, which is why lap time may confirm and never
  trigger.
* **One at a time, and rarely.** At most one colour call per crossing, and not
  within `gap_laps` of the last one. Silence is the default state.
* **Each kind once per stint.** "Five to the stop" is news the first time and
  noise the third.
* **Never on a lap that carries a real call.** The caller ranks: an engineer
  who says "nice lap" over the top of a box call has actively hurt the race.
* **He can turn it down.** `QUIET` is off entirely, and the levels differ only
  in how much silence they keep.

The gauge prompt is the one that pays its way twice. GT7 broadcasts no tyre
wear channel at all, so the in-game gauge is the only ground truth that exists
- and on the Monza race of 18 Aug 2026 he read it zero times, which left the
race that mattered most contributing nothing to the wear model. Asking him for
it on a straight is engagement that is also the app's most valuable
measurement.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Off, and it means off - not "less often".
QUIET = "quiet"
NORMAL = "normal"
CHATTY = "chatty"
LEVELS = (QUIET, NORMAL, CHATTY)

# Laps of silence a level keeps between colour calls. Chatty is still three
# laps apart: at Monza that is five and a half minutes of race per call, which
# is about what a real engineer does when nothing is happening.
GAP_LAPS = {QUIET: None, NORMAL: 6, CHATTY: 3}

# **The run-in speaks every lap, and it is the one exemption from the gap.**
# The driver asked for it in as many words: *"I want each lap updates in the
# last 5 laps to keep me pushing to the end and aware of what is going on."*
#
# It does not undo the budget that stopped the nine-box-calls defect. That
# register exists to stop a call REPEATING when nothing has changed, and in
# the run-in something changes every crossing: the laps left go down by one.
# Each call is new news, which is the same test every other call here passes.
# It still ranks below every real call - the controller only reaches colour on
# a crossing that had nothing else to say - so it cannot talk over a box call.
RUN_IN_LAPS = 5
RUN_IN = "colour-run-in"

BEST_LAP = "colour-best-lap"
CONSISTENCY = "colour-consistency"
STINT_COUNTDOWN = "colour-stint-countdown"
MILESTONE = "colour-milestone"
GAUGE_PROMPT = "colour-gauge"

# **A run of laps inside this many multiples of his own sigma is a good run.**
# Sigma is measured per car and circuit from the race in progress, never
# inherited - see `replan`. One sigma is by construction the ordinary spread,
# so a run that stays inside it is genuinely better than his own average and
# not just a description of noise.
CONSISTENT_SIGMA = 1.0
CONSISTENT_MIN_LAPS = 4

# How near the stop the countdown is worth saying. Further out he cannot act
# on it and it is just arithmetic read aloud.
COUNTDOWN_FROM_LAPS = 5

# Milestones, as laps remaining. Halfway is handled separately because it
# depends on the distance rather than on the run-in.
MILESTONE_LAPS_LEFT = (10, 5)


@dataclass(frozen=True)
class ColourCall:
    """One thing said, and the fact behind it."""
    kind: str
    call: str
    reason: str = ""

    def spoken(self) -> str:
        return f"{self.call} {self.reason}".strip()


@dataclass
class ColourCalls:
    """Decides whether this crossing is worth a word. Usually it is not."""
    level: str = NORMAL
    _said: dict = field(default_factory=dict)
    _last_lap: int | None = None
    _best_ms: int | None = None
    _times: list = field(default_factory=list)
    _stint: int = 0

    def new_stint(self) -> None:
        """A stop has been taken. Every kind is news again."""
        self._stint += 1
        self._said = {k: v for k, v in self._said.items()
                      if v[0] == self._stint}
        self._times.clear()

    def consider(self, *, lap: int, lap_time_ms: int | None,
                 laps_remaining: int | None, laps_total: int | None = None,
                 stint_ends_on_lap: int | None = None,
                 sigma_s: float | None = None,
                 wear_reading_age: int | None = None,
                 position: int | None = None,
                 laps_firm: bool = True) -> ColourCall | None:
        """One crossing. Returns at most one call, and usually None.

        `wear_reading_age` is laps since the tyre gauge was last read, or None
        where it never has been this stint. `sigma_s` is his measured lap-to-
        lap scatter for this car and circuit, or None before enough clean laps
        exist - and then the consistency call stays silent rather than
        inventing a band.

        `laps_firm` is whether the remaining-lap count is resolvable at all.
        In a timed race the distance is an OUTPUT of the plan and the count
        can be inside this car's own lap-time noise, so the run-in hedges to
        "about three to go" rather than quoting a figure it cannot stand
        behind. `position` is GT7's own, off the packet.
        """
        if self.level == QUIET:
            return None
        if lap_time_ms and lap_time_ms > 0:
            self._times.append(lap_time_ms)

        run_in = self._run_in(laps_remaining, lap_time_ms, position,
                              laps_firm)
        if run_in is not None:
            self._record_only(lap_time_ms)
            self._last_lap = lap
            return run_in

        gap = GAP_LAPS[self.level]
        if self._last_lap is not None and lap - self._last_lap < gap:
            self._record_only(lap_time_ms)
            return None

        call = (self._best_lap(lap_time_ms)
                or self._milestone(lap, laps_remaining, laps_total)
                or self._countdown(lap, stint_ends_on_lap)
                or self._gauge(wear_reading_age)
                or self._consistency(sigma_s))
        self._record_only(lap_time_ms)
        if call is None:
            return None
        self._said[call.kind] = (self._stint, lap)
        self._last_lap = lap
        return call

    # ---------------------------------------------------------------- kinds

    def _fresh(self, kind: str) -> bool:
        held = self._said.get(kind)
        return held is None or held[0] != self._stint

    def _record_only(self, lap_time_ms: int | None) -> None:
        if lap_time_ms and lap_time_ms > 0:
            if self._best_ms is None or lap_time_ms < self._best_ms:
                self._best_ms = lap_time_ms

    def _best_lap(self, lap_time_ms: int | None) -> ColourCall | None:
        """**The one kind that may repeat within a stint.** A new personal best
        is a new fact every time it happens, and it is the single most
        motivating thing an engineer says. It is still bounded by the gap.
        """
        if not lap_time_ms or lap_time_ms <= 0 or self._best_ms is None:
            return None
        if lap_time_ms >= self._best_ms or len(self._times) < 3:
            return None
        gained = (self._best_ms - lap_time_ms) / 1000.0
        return ColourCall(BEST_LAP, "That's the best lap of the race.",
                          f"{gained:.1f} up on your own." if gained >= 0.1
                          else "")

    def _run_in(self, laps_remaining: int | None, lap_time_ms: int | None,
                position: int | None, laps_firm: bool) -> ColourCall | None:
        """Every lap of the run-in, counting down.

        **Everything in it is measured.** The lap count is the app's own
        estimate and says so when it cannot be resolved; the position is
        GT7's; the lap time and the best are GT7's own exact figures. No gap
        to the car ahead - there is no proximity channel in any packet format
        - and no pace verdict, because his lap-to-lap sigma is wider than the
        whole degradation band. "Two tenths off your best" is arithmetic on
        two exact numbers, which is a different thing from a judgement.
        """
        if laps_remaining is None or not 1 <= laps_remaining <= RUN_IN_LAPS:
            return None
        if laps_remaining == 1:
            head = "Last lap."
        else:
            about = "" if laps_firm else "about "
            head = f"{about}{laps_remaining} to go."
            head = head[0].upper() + head[1:]
        where = f"P{position}. " if position else ""

        best = self._best_ms
        if lap_time_ms and lap_time_ms > 0:
            if best is None or lap_time_ms <= best:
                return ColourCall(RUN_IN, head,
                                  f"{where}That's your best of the race.")
            off = (lap_time_ms - best) / 1000.0
            # Under a tenth is inside the resolution of anything he can act
            # on, and "0.0 off your best" is a number that means nothing.
            if off < 0.1:
                return ColourCall(RUN_IN, head, f"{where}On your best pace.")
            return ColourCall(RUN_IN, head, f"{where}{off:.1f} off your best.")
        return ColourCall(RUN_IN, head, where.strip())

    def _consistency(self, sigma_s: float | None) -> ColourCall | None:
        if sigma_s is None or not self._fresh(CONSISTENCY):
            return None
        recent = self._times[-CONSISTENT_MIN_LAPS:]
        if len(recent) < CONSISTENT_MIN_LAPS:
            return None
        spread = (max(recent) - min(recent)) / 1000.0
        if spread > CONSISTENT_SIGMA * sigma_s:
            return None
        return ColourCall(
            CONSISTENCY, f"{len(recent)} laps inside {spread:.1f}.",
            "That's the tidiest run of the race.")

    def _countdown(self, lap: int,
                   stint_ends_on_lap: int | None) -> ColourCall | None:
        if stint_ends_on_lap is None or not self._fresh(STINT_COUNTDOWN):
            return None
        to_go = stint_ends_on_lap - lap
        if not 1 <= to_go <= COUNTDOWN_FROM_LAPS:
            return None
        return ColourCall(STINT_COUNTDOWN,
                          f"{to_go} to the stop." if to_go > 1
                          else "Stop next lap.", "")

    def _milestone(self, lap: int, laps_remaining: int | None,
                   laps_total: int | None) -> ColourCall | None:
        if laps_remaining is None or not self._fresh(MILESTONE):
            return None
        if laps_remaining in MILESTONE_LAPS_LEFT:
            return ColourCall(MILESTONE, f"{laps_remaining} to go.", "")
        if laps_total and lap * 2 == laps_total:
            return ColourCall(MILESTONE, "Halfway.", "")
        return None

    def _gauge(self, age: int | None) -> ColourCall | None:
        """Ask for the tyre gauge.

        **The only ground truth for wear that exists.** GT7 broadcasts no wear
        channel in any packet format, so every wear number the app holds is
        either modelled or read off the in-game gauge by the driver - and on
        the Monza race of 18 Aug 2026 he read it zero times. A prompt on a
        straight costs him a glance and is worth more to the model than
        anything else said all race.
        """
        if age is None or age < 5 or not self._fresh(GAUGE_PROMPT):
            return None
        return ColourCall(GAUGE_PROMPT, "Tyre gauge when you get a straight.",
                          "I have nothing measured on this set.")
