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

from pitcrew.diagnostics import log
from pitcrew.race.expectations import FUEL_BASES_HEDGED

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

# **How much has to go in before the app admits it cannot size the stop.**
# At the measured 1.002 L/s that is five seconds into a fill - early enough
# that he can still act on it, and far past any single-frame jump. It is
# deliberately a fuel figure and not a clock: `note` has no clock, and the
# quantity that matters is how much of the stop is already spent.
UNSIZED_RISE_L = 5.0

TARGET = "refuel-target"
RELEASE = "refuel-release"
SHORT = "refuel-short"
# **Nothing could size this fill, and saying so beats saying nothing.**
# Silence in the box is indistinguishable from an app that has died - which
# is exactly the night this call was written on, when four calls WERE made
# and nobody could tell from the log. The instruction carries no litre figure
# the app invented (rule 3): GT7's own diamond marker is accurate (§5.4) and
# it is the one number in the box that does not come from here.
UNSIZED = "refuel-unsized"

# **The caller did not say whose burn sized the target.** Distinct from None,
# which is a statement - no race burn installed, so the figure is practice's
# (`RaceState.fuel_burn_basis`). A watch that is not told names no burn at all
# rather than guess one: "at this race's burn" said over a practice figure is
# the defect this exists to stop (Sardegna, 15 Sep 2026, session 179).
BURN_UNSTATED = object()


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

    **Pure arithmetic, and one log line per decision.** The logging is not
    instrumentation bolted on - it is the only record that this class ran at
    all, because nothing it says leaves a mark anywhere else (CLAUDE.md rule
    10, and see `note`).
    """

    def __init__(self) -> None:
        self._rising = 0
        self._low_l: float | None = None
        self._prev_l: float | None = None
        self._filling = False
        self._target_l: float | None = None
        self._burn_basis = BURN_UNSTATED
        self._burn_laps: int | None = None
        self._said_target = False
        self._said_release = False
        self._said_short = False
        self._said_unsized = False
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
             basis: str | None = None,
             burn_basis=BURN_UNSTATED,
             burn_laps: int | None = None) -> RefuelCall | None:
        """One frame. See `_decide`; this only writes down what came out.

        **Every call this watch makes is logged here** (rule 10, second
        half). Four were made at Bathurst on 20 Sep 2026 - two fill targets,
        a release and a shortfall, all filed in `race_revisions` and all
        spoken - and not one of them left a mark in `pitcrew.log`, because
        `voice.say` logs a line only when the caller passes an `on_done` and
        this one did not. The record therefore could not tell "the adviser
        spoke" from "the adviser has never run", which is a whole class of
        question this one line closes.
        """
        call = self._decide(fuel_l, speed_kph=speed_kph, target_l=target_l,
                            fuel_per_lap_l=fuel_per_lap_l,
                            to_flag_l=to_flag_l, basis=basis,
                            burn_basis=burn_basis, burn_laps=burn_laps)
        if call is not None:
            log("race").info("refuel: %s [%s]", call.spoken(), call.kind)
        return call

    def _decide(self, fuel_l: float | None, *, speed_kph: float | None,
                target_l: float | None,
                fuel_per_lap_l: float | None = None,
                to_flag_l: float | None = None,
                basis: str | None = None,
                burn_basis=BURN_UNSTATED,
                burn_laps: int | None = None) -> RefuelCall | None:
        """One frame. Returns what to say, or None - which is almost always.

        `target_l` is what the tank should read at pit exit, recomputed by the
        caller from the race in progress. It is **captured once**, when the
        fill is first seen: the car is stationary for the whole of it, so
        nothing that feeds the figure can move while the hose is in, and a
        target that wobbled mid-fill would be chatter rather than news.

        **`None` is the one thing that is not captured** (rule 10). It is not
        a figure that might wobble - it is "I have not been told" - and
        holding it for the stop is a refusal that becomes its own baseline,
        with nothing able to retire it. So the watch keeps asking until a
        real figure turns up, and the first real one wins. If none ever does,
        `_unsized` says the one instruction that needs no figure from here.

        `burn_basis` is `RaceState.fuel_burn_basis` beside that target: one of
        `expectations.FUEL_BASIS_*` where this race's burn is installed, None
        where the burn is still practice's. Captured with the target, because
        the words have to name the burn that sized the number (rules 5, 12).

        `burn_laps` is `RaceState.fuel_burn_laps` beside both - how many green
        laps stand behind that burn (rule 4). Captured with them for the same
        reason: a count that arrived later would belong to a different figure.
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
            self._capture(target_l, burn_basis, burn_laps)
            # **The accept, not only the refusals** (rule 10). The number
            # setting the bar for everything this stop says never appeared in
            # a log, so four calls made at Bathurst on 20 Sep 2026 were
            # indistinguishable in the record from an adviser that had never
            # run at all - and a night went into asking which it was.
            log("race").info(
                "refuel: the hose is in at %.1f L. Target %s; bound %s; "
                "burn %s; laps behind it %s.",
                self.started_l,
                "NOT SIZED" if target_l is None else f"{target_l:.1f} L",
                basis or "not named", _burn_words(burn_basis) or "not said",
                burn_laps if burn_laps else "not said")
        elif self._target_l is None:
            # **A stop nothing could size is not a decision to hold** (rule
            # 10). The target is captured once so it cannot wobble mid-fill,
            # but a `None` is not a figure that could wobble - it is "I have
            # not been told", and capturing it once latches the whole stop
            # into silence with nothing able to retire it. So a real figure
            # arriving later is taken; a real figure already captured is not
            # replaced.
            if target_l is not None:
                self._capture(target_l, burn_basis, burn_laps)
                log("race").info(
                    "refuel: sized late, %.1f L into the fill - target "
                    "%.1f L, bound %s, burn %s.",
                    fuel_l - (self.started_l or fuel_l), target_l,
                    basis or "not named",
                    _burn_words(burn_basis) or "not said")

        target = self._target_l
        if target is None:
            # Filling, but nothing sized the stop - no burn measured, or no
            # idea how many laps are left. **A guessed litre figure is not
            # the answer**: he is holding the trigger on a number, and one
            # the app invented is worse than none (rule 3).
            #
            # **Silence is not the answer either.** It is what the box
            # sounded like when the adviser worked perfectly, so the driver
            # cannot tell a stop nobody could size from an app that has
            # stopped. `_unsized` says the one instruction that needs no
            # figure from here.
            return self._unsized(fuel_l, fuel_per_lap_l)

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
            # **And the burn it was sized on, by name.** Sardegna, session
            # 179: "17 laps after the box, at this race's burn." over the
            # practice 5.586 L/lap, because every lap ran the plan's
            # short-shift and no race burn was ever installed.
            burn = _burn_words(self._burn_basis)
            bound = (basis[0].upper() + basis[1:]) if basis else None
            return RefuelCall(
                TARGET, f"Fuel to {_ceil_l(target)} litres.",
                (f"{bound}{f', at {burn}' if burn else ''}." if bound
                 else _laps_reason(target, fuel_per_lap_l, burn))
                # **Directly after the burn it qualifies**, and before the
                # stay-out alternative, so the count cannot be heard as
                # belonging to that other figure (rule 13).
                + _burn_evidence(self._burn_basis, self._burn_laps)
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

    def _capture(self, target_l: float | None, burn_basis,
                 burn_laps: int | None) -> None:
        """The figure, and the words that qualify it, taken together.

        Never separately. A count or a basis picked up from a later context
        than the litres would have the sentence name the burn that did NOT
        size the number (rules 12 and 13) - which is the whole reason the
        three travel in one tuple from the controller in the first place.
        """
        self._target_l = target_l
        self._burn_basis = burn_basis
        self._burn_laps = burn_laps

    def _unsized(self, fuel_l: float,
                 fuel_per_lap_l: float | None) -> RefuelCall | None:
        """The hose is in and nothing here can size the stop. Say so, once.

        **Not a litre figure, and not silence.** GT7's own diamond marker is
        accurate (CLAUDE.md §5.4) and it is the one number in the box that
        does not come from this app, so it is what an engineer with no figure
        of his own points at. "Plus a lap" is §5.4's margin, said in the
        words the rest of the app uses for it.

        Held until `UNSIZED_RISE_L` is aboard so it cannot fire on a jump
        that was never a pit stop, and said once per stop: he is holding the
        refuelling trigger, not listening to a conversation.

        **And the refusal is logged with the reason that produced it** (rule
        10). "No target" has two quite different causes - nothing reached the
        watch at all, or a burn arrived with no lap count to spend it on -
        and they are fixed in different places.
        """
        if self._said_unsized or self.started_l is None:
            return None
        if fuel_l - self.started_l < UNSIZED_RISE_L:
            return None
        # **A figure may still arrive after this, and if it does it wins.**
        # Retiring the None-target latch made a target reachable mid-fill, so
        # "I can't size this one" can be followed by "Fuel to 55 litres" a
        # second later (measured: unsized at 10.0 L, target at 11.0 L).
        #
        # That is NOT fixed by holding this line back until a target can be
        # ruled out. Tried and reverted: waiting a second rise delays the
        # diamond instruction in the case that never resolves - the one where
        # nothing reaches the watch at all - to spare a contradiction in the
        # case that does. He is holding the trigger; late advice on a stop
        # nothing can size costs more than a refinement he can obviously act
        # on. The instruction here survives the figure anyway - filling to
        # the diamond plus a lap is not wrong, it is only less precise - so
        # the second call refines the first rather than reversing it.
        #
        # What this DOES require is that he knows the figure wins, which is
        # a briefing line, not a code branch.
        self._said_unsized = True
        log("race").warning(
            "refuel: %.1f L aboard and nothing sized this stop - %s. Saying "
            "the diamond rather than a litre figure: a number this app "
            "invented would be worse than none (rule 3).",
            fuel_l,
            f"a burn of {fuel_per_lap_l:.2f} L/lap arrived, but no lap count "
            f"to spend it on" if fuel_per_lap_l else
            "no figure reached the watch at all - the race is not running, "
            "or no burn is installed yet")
        return RefuelCall(UNSIZED, "Fill to the diamond, plus a lap.",
                          "I can't size this one.")

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

        **Every exit is written down, whether it says anything or not** (rule
        10). "He left and I said nothing" has four quite different causes
        here and the log used to record none of them.
        """
        target = self._target_l
        if (not self._filling or self._said_short or self._said_release
                or target is None or fuel_l is None):
            log("race").info(
                "refuel: out of the box with nothing to say - %s.",
                "no fill was seen this stop" if not self._filling else
                "the shortfall was already said" if self._said_short else
                "he was released at the target" if self._said_release else
                "nothing sized this stop" if target is None else
                "no fuel reading at the exit")
            return None
        self._said_short = True
        short = target - fuel_l
        if short < SHORT_EPSILON_L:
            log("race").info(
                "refuel: out of the box on %.1f L against a %.1f L target - "
                "%.2f L short, inside the %.1f L that is worth a word.",
                fuel_l, target, short, SHORT_EPSILON_L)
            return None
        laps = (short / fuel_per_lap_l) if fuel_per_lap_l else None
        reason = (f"{short:.0f} litres light - about {laps:.1f} laps."
                  if laps is not None else f"{short:.0f} litres light.")
        call = RefuelCall(SHORT, "Save fuel from here.", reason)
        log("race").info("refuel: %s [%s]", call.spoken(), call.kind)
        return call


class RefuelAdviser:
    """A watch, where its numbers come from, and where its words go.

    The 60 Hz frame path lives on `TelemetryBridge` and the race lives on the
    controller, so something has to carry the target across. Same shape as the
    qualifying coach: the controller builds it with a `speak` callable and
    hands it over, and the frame path calls one method and knows nothing else.

    `context` returns `(target_l, fuel_per_lap_l, to_flag_l, basis,
    burn_basis, burn_laps)` for the race right now - `basis` being the bound
    that sized the target, in words, `burn_basis` whose burn did and
    `burn_laps` how many laps stand behind it (see `RefuelWatch.note`) - or
    None where nothing can size a stop. It is called **only when the car is
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
        target = fuel_per_lap = to_flag = basis = burn_laps = None
        burn_basis = BURN_UNSTATED
        if speed_kph is not None and speed_kph <= FILL_MAX_KPH:
            found = self._context()
            if found is not None:
                # Three values from an older context, six from the
                # controller's: the fourth is the bound behind the figure, the
                # fifth whose burn, the sixth how many laps stand behind it.
                # A context too old to carry the fifth has not said, and the
                # watch then names no burn at all; one too old to carry the
                # sixth names the burn without its count, which is where this
                # was before 20 Sep 2026 and is honest rather than invented.
                target, fuel_per_lap, to_flag = found[:3]
                basis = found[3] if len(found) > 3 else None
                if len(found) > 4:
                    burn_basis = found[4]
                if len(found) > 5:
                    burn_laps = found[5]
        call = self.watch.note(fuel_l, speed_kph=speed_kph, target_l=target,
                               fuel_per_lap_l=fuel_per_lap,
                               to_flag_l=to_flag, basis=basis,
                               burn_basis=burn_basis, burn_laps=burn_laps)
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


def _burn_words(burn_basis) -> str | None:
    """"this race's burn", "the practice burn", or None where not told.

    Any installed basis - the race, this stint, or the higher of the two - is
    this race's laps; None is `build_inputs`' practice figure, which is what
    `RaceState.fuel_per_lap_l` holds until a race burn replaces it. Not told
    names nothing, never a guess.

    **The five bases deliberately collapse to four words, and that is why
    `_burn_evidence` exists.** "At this race's burn" meant nineteen laps of
    evidence on lap 25 of Bathurst Rd 8 and three laps on lap 26, in an
    identical sentence - rule 13, and rule 4's sample count never reaching
    the ear at all. Naming the basis itself would not fix it: "the higher of
    the race and this stint so far" is not a sentence to say to a man holding
    the refuelling trigger. The count is the part he can act on.
    """
    if burn_basis is BURN_UNSTATED:
        return None
    if burn_basis is None:
        return "the practice burn"
    return "this race's burn"


def _burn_evidence(burn_basis, burn_laps: int | None) -> str:
    """" Measured over 19 laps.", " Unconfirmed.", or nothing where nobody said.

    **Its own sentence, and it carries the only number in it.** The voice
    pack's manifest can render a sentence with ONE number in it
    (`phrase_manifest._pieces`), so folding this into "17 laps after the box,
    at this race's burn over 19 laps" would put the whole line beyond the
    pack and send every fill call of every race to live synthesis.

    Only on this race's own burn. The practice figure's sample count is the
    plan's and is not a count of laps run today; quoting it here would be two
    different things behind one form of words, which is the defect above.

    **And a derived basis is hedged, never counted** (rule 5). Every basis in
    `expectations.FUEL_BASES_HEDGED` is a hedge rather than a reading - the
    beep column's laps converted at the plan's ratio, or the higher of two
    populations picked because the lower one is the direction that runs him
    dry. "Measured over 19 laps" over a conversion off laps he did not drive
    on this column states a claim the evidence does not support, and it
    states it in the most confident form of words the call has. So the
    hedged bases say the one word §5.5 says the driver can act on, and say
    no number at all: a count is what makes a figure sound measured.

    `FUEL_BASES_HEDGED` rather than a list of names here, deliberately - the
    tuple exists so a basis split or added later hedges at every consumer by
    construction, and this module was the one consumer not reading it.
    """
    if burn_basis is BURN_UNSTATED or burn_basis is None:
        return ""
    if burn_basis in FUEL_BASES_HEDGED:
        # **Already in the pack.** `calls`' LOW-confidence mark is the same
        # word in the same one-word sentence (`phrase_manifest`), so this
        # costs no clip and it is a hedge he has heard before (rule 13).
        return " Unconfirmed."
    if not burn_laps or burn_laps <= 0:
        return ""
    laps = int(burn_laps)
    return f" Measured over {laps} lap{'' if laps == 1 else 's'}."


def _laps_reason(target: float, fuel_per_lap_l: float | None,
                 burn: str | None = None) -> str:
    if not fuel_per_lap_l:
        return ""
    laps = f"{target / fuel_per_lap_l:.0f} laps"
    return f"{laps} at {burn}." if burn else f"{laps}."
