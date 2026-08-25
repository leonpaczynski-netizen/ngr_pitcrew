"""What to ask the driver — and, far more importantly, what not to.

`report.py` is a form: thirteen fields, asked every time, decided once at design
time. Its principle is right — *"only what the app cannot know"* — but a static
list cannot notice when the data moves under it, and the data has. Tyre state at
the end of a run is now read off the HUD gauge to 0.5%; where a lap costs most is
derivable from `grip_observations`. Both are still fields on the form.

This module replaces the form's judgement with a gate, and the gate is one rule:

    **A question with a working resolver may never be asked.**

The rule exists because of a specific failure on 23 Aug 2026. The driver was
asked to watch the on-screen tyre indicators at two corners and report whether
one rear wheel was spinning alone or both were going together — the differential
fork, open across three setup revisions. `lap_frames` carries per-wheel slip.
Splitting the rear axle into inside and outside over 17,421 corner-exit frames
answered it in a single query, decisively, and it had been answerable the whole
time. **A driver observation was queued for something already measured
seventeen thousand times over.** He noticed before the app did.

So every question here declares how it could be answered from data, or states
why it cannot be. `unmeasurable_because` is mandatory when there is no resolver
and it is the field that keeps the registry honest: *"GT7 sends no slip angle
and no yaw target"* is a reason, *"nobody wrote the query"* is not, and the
registry test rejects the second by rejecting the empty string.

**What survives the gate is the irreducible half**, and it is not small. Feel,
confidence, workload, whether the air was clean, what the regulations say, and
above all *what is actually in the car* have no channel and never will. The point
is not to stop asking. It is to spend his attention on the things only he can
answer.

**Three rules the output obeys**, inherited from the rest of the package:

* **A question states what is already known before it asks.** A driver
  confirming a reading is doing something far easier and far more reliable than
  a driver recalling a sensation from twenty minutes ago. That is what
  `context_line` is for, and it is why a resolved fact is not merely deleted —
  it is handed to the question next to it.
* **Nothing derived is presented as measured.** A proxy answers with
  `source=DERIVED` and carries its own basis in `evidence`.
* **Missing is missing.** A resolver that cannot answer this time returns
  `None`, the question is asked, and nothing is defaulted into existence. That
  is a different state from having no resolver at all, and the two are not
  collapsed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Callable

from pitcrew.analysis import gearing

# ------------------------------------------------------------------ provenance

MEASURED = "measured"       # read off a channel, or off the gauge
STORED = "stored"           # the driver already told us and it was written down
DERIVED = "derived"         # a proxy. Never presented as measured.

# How many questions a person answers well before the answers stop being worth
# having. Deliberately small: the ranking exists so the cheap questions cannot
# crowd out the decisive one, and a queue of eleven is a queue nobody finishes.
MAX_QUESTIONS = 4

BRIEF = "brief"
REFINEMENT = "refinement"
OUTCOME = "outcome"
RACE_PLAN = "race_plan"
QUALI_PLAN = "quali_plan"
ALL_KINDS = (BRIEF, REFINEMENT, OUTCOME, RACE_PLAN, QUALI_PLAN)


class RegistryError(ValueError):
    """A question that cannot be trusted to gate itself."""


@dataclass(frozen=True)
class Answer:
    """What a resolver found, and what makes it believable."""
    value: str
    source: str
    evidence: str
    samples: int = 0

    def __post_init__(self) -> None:
        if not self.evidence:
            raise RegistryError(
                f"answer {self.value!r} carries no evidence - a resolved fact "
                f"without its basis is indistinguishable from a guess")


@dataclass(frozen=True)
class Question:
    """One thing the engineer might need, and how it gets answered.

    `impact` ranks the queue and is the answer to "how much does the output
    move if he tells me?". It is deliberately coarse — 1 to 10 — because the
    ordering matters and the precision does not.
    """
    key: str
    asks: str
    feeds: tuple[str, ...]
    impact: int
    resolver: Callable | None = None
    unmeasurable_because: str = ""
    # A sentence of what IS known, shown with the question. Returns None when
    # there is nothing to say, which is not the same as an empty string.
    context_line: Callable | None = None
    kinds: tuple[str, ...] = ALL_KINDS

    def __post_init__(self) -> None:
        if self.resolver is None and not self.unmeasurable_because:
            raise RegistryError(
                f"{self.key}: no resolver and no reason. Either write the "
                f"query or say what channel is missing - an unexplained "
                f"question is how the tyre-indicator failure happened")
        if self.resolver is not None and self.unmeasurable_because:
            raise RegistryError(
                f"{self.key}: has a resolver AND claims to be unmeasurable. "
                f"One of the two is wrong")
        if not 1 <= self.impact <= 10:
            raise RegistryError(f"{self.key}: impact {self.impact} outside 1-10")


@dataclass(frozen=True)
class Asked:
    """A question that survived the gate, with what is already known."""
    question: Question
    context_line: str | None = None

    @property
    def key(self) -> str:
        return self.question.key

    @property
    def text(self) -> str:
        if self.context_line:
            return f"{self.context_line} {self.question.asks}"
        return self.question.asks


@dataclass
class Resolution:
    """The outcome of one pass over the registry."""
    answered: dict[str, Answer] = field(default_factory=dict)
    asked: list[Asked] = field(default_factory=list)
    # Keys the gate suppressed, so a debrief can show its working — and so a
    # test can assert that a specific question is no longer reachable.
    suppressed: tuple[str, ...] = ()
    # Resolvers that raised. A broken resolver must ASK rather than silently
    # answer, so these appear in `asked` too; this records that it happened.
    failed: tuple[str, ...] = ()


# ------------------------------------------------------------------ resolvers
#
# Each takes (store, context) and returns an Answer, or None where it could not
# answer THIS TIME. None means "ask him" and is a first-class outcome.

# Corner-exit frames: hard on the throttle, off the brakes, still turning.
_EXIT_THROTTLE_PCT = 70.0
_EXIT_LAT_G = 0.5
_EXIT_STEER_DEG = 15.0
# Wheel surface speed / road speed. 1.02 is the threshold the v1.71 slip work
# used; it was calibrated on the RSR, so the ASYMMETRY below carries the
# argument and this only labels it.
_WHEELSPIN = 1.02
_MIN_EXIT_FRAMES = 400
# A pattern has to be lopsided to be worth acting on. Below these the resolver
# says nothing rather than reporting a coin toss.
_PATTERN_MAJORITY = 0.60


def _frames(context) -> list[dict]:
    out: list[dict] = []
    for lap in context.laps or ():
        if lap.excluded or lap.is_pit_lap:
            continue
        out.extend(lap.frames or ())
    return out


def _num(frame: dict, key: str) -> float | None:
    """A channel's value, or None where it was never measured.

    **`dict.get(key, default)` is wrong here and it cost two resolvers.** The
    default only applies when the key is ABSENT; a key present with an explicit
    null returns None, and None then compares against a float and raises. The
    store is right to write null - the app's own rule is that missing is never
    zero - so the reader has to carry the rule too. 22,365 frames in one event
    hold a null in a channel these resolvers read.
    """
    value = frame.get(key)
    return None if value is None else float(value)


def _at_least(frame: dict, key: str, floor: float) -> bool:
    value = _num(frame, key)
    return value is not None and value >= floor


def _is_zero(frame: dict, key: str) -> bool:
    """True only where the channel was measured AND read zero."""
    value = _num(frame, key)
    return value is not None and value == 0.0


def _inside_is_left_on_positive_steer(frames: list[dict]) -> bool | None:
    """Which rear wheel is the inside one when steering reads positive.

    **Derived per call rather than assumed.** GT7's steering sign is a
    convention and the suspension channel is a measurement, so the load decides
    it: the compressed wheel is the outside one, and larger is more compressed
    on this feed. Hard-coding the sign would put a silent dependency on a
    convention the packet is free to change between versions.
    """
    loaded = [f for f in frames
              if _at_least(f, "steering_deg", _EXIT_STEER_DEG)
              and _at_least(f, "lat_g", 0.8)
              and _num(f, "susp_mm_rl") is not None
              and _num(f, "susp_mm_rr") is not None]
    if len(loaded) < _MIN_EXIT_FRAMES // 4:
        return None
    rl = mean(f["susp_mm_rl"] for f in loaded)
    rr = mean(f["susp_mm_rr"] for f in loaded)
    if abs(rl - rr) < 1.0:          # no discernible roll: refuse to guess
        return None
    return rl < rr


def rear_wheelspin_pattern(store, context) -> Answer | None:
    """Does one rear wheel spin alone, or do both go together?

    **The question that started this module.** The differential's acceleration
    sensitivity moves in opposite directions depending on the answer — up when
    the inside wheel spins alone and torque is escaping through it, down when
    the axle is over-coupled and drags both tyres into slip together. It was
    asked of the driver three revisions running and it was in the frames the
    whole time.

    The load-bearing measurement is the **asymmetry**, not the absolute slip:
    both rear wheels sit on one axle under one torque, so inside-minus-outside
    is self-referencing and carries no dependence on where the wheelspin
    threshold is set.
    """
    frames = _frames(context)
    inside_left = _inside_is_left_on_positive_steer(frames)
    if inside_left is None:
        return None
    exits = [f for f in frames
             if _at_least(f, "throttle_pct", _EXIT_THROTTLE_PCT)
             and _is_zero(f, "brake_pct")
             and _at_least(f, "lat_g", _EXIT_LAT_G)
             and _num(f, "steering_deg") is not None
             and abs(_num(f, "steering_deg")) >= _EXIT_STEER_DEG
             and _num(f, "slip_rl") is not None
             and _num(f, "slip_rr") is not None]
    if len(exits) < _MIN_EXIT_FRAMES:
        return None
    alone = both = 0
    deltas = []
    for f in exits:
        positive = f["steering_deg"] > 0
        left_inside = inside_left if positive else not inside_left
        ins = f["slip_rl"] if left_inside else f["slip_rr"]
        out = f["slip_rr"] if left_inside else f["slip_rl"]
        deltas.append(ins - out)
        if ins > _WHEELSPIN and out > _WHEELSPIN:
            both += 1
        elif ins > _WHEELSPIN:
            alone += 1
    n = len(exits)
    split = mean(deltas)
    if both / n >= _PATTERN_MAJORITY:
        return Answer(
            "both rears together - the axle is over-coupled",
            MEASURED,
            f"{100 * both / n:.1f}% of {n} corner-exit frames have both rears "
            f"above {_WHEELSPIN}, inside alone {100 * alone / n:.1f}%; "
            f"inside-minus-outside slip {split:+.4f}",
            n)
    if alone / n >= _PATTERN_MAJORITY:
        return Answer(
            "the inside rear alone - torque is escaping through it",
            MEASURED,
            f"{100 * alone / n:.1f}% of {n} corner-exit frames have the inside "
            f"rear alone above {_WHEELSPIN}; inside-minus-outside slip "
            f"{split:+.4f}",
            n)
    return None


def tyre_state_at_end(store, context) -> Answer | None:
    """Wear at the end of the run, from the gauge rather than from memory.

    Still a field on the driver's form. `tools/read_hud_wear.py` reads GT7's
    own gauge off the video to 0.5%, and any reading the driver entered by hand
    is already on the lap. Either way it is written down, and asking him to
    recall it invites a worse answer than the one already stored.
    """
    gauged = [lap for lap in (context.laps or ())
              if None not in (lap.wear_fl, lap.wear_fr, lap.wear_rl, lap.wear_rr)]
    if not gauged:
        return None
    last = max(gauged, key=lambda lap: lap.lap_num)
    corners = {"FL": last.wear_fl, "FR": last.wear_fr,
               "RL": last.wear_rl, "RR": last.wear_rr}
    worst, value = max(corners.items(), key=lambda kv: kv[1])
    return Answer(
        f"worst corner {worst} at {100 * value:.0f}% consumed",
        MEASURED,
        "gauge reading on lap %d: %s" % (
            last.lap_num,
            ", ".join(f"{k} {100 * v:.0f}%" for k, v in corners.items())),
        len(gauged))


# Mid-corner frames for the understeer proxy: turning hard, off the brakes.
_MID_LAT_G = 0.6
_MID_STEER_DEG = 20.0
_OFF_THROTTLE_PCT = 10.0
_ON_THROTTLE_PCT = 50.0
_MIN_BAND_FRAMES = 150
# Compare like corners with like: a bucket narrow enough that a slow hairpin
# and a fast sweeper cannot land in the same one.
_SPEED_BUCKET_KPH = 20.0
_MIN_BUCKET_FRAMES = 30
# How far apart the two bands have to be before the difference is a finding.
_THROTTLE_BAND_RATIO = 0.10


def push_throttle_state(store, context) -> Answer | None:
    """Is the mid-corner push there off throttle, on throttle, or both?

    Asked of the driver on 23 Aug and it looked unmeasurable at the time. It is
    not. Steering angle per unit of lateral acceleration is an understeer
    proxy — more lock for the same cornering force means the front is giving
    up — and comparing that proxy **between throttle bands in the same corners**
    needs no absolute baseline, because each band is measured against the other
    rather than against a number somebody chose.

    **This is a proxy and it answers `DERIVED`.** GT7 broadcasts no slip angle,
    so nothing here measures understeer directly; it measures the input the
    driver had to add, which is a different claim and is labelled as one.
    """
    mid = [f for f in _frames(context)
           if _is_zero(f, "brake_pct")
           and _at_least(f, "lat_g", _MID_LAT_G)
           and _num(f, "steering_deg") is not None
           and abs(_num(f, "steering_deg")) >= _MID_STEER_DEG
           and _num(f, "speed_kph") is not None]

    # **Bucketed by speed, because otherwise the two bands are not the same
    # corners.** Off throttle at high lateral g happens in slow and medium
    # corners; on throttle at high lateral g happens in fast ones, where the
    # steering angle is naturally low for the g. Comparing the pooled means
    # would compare corner types and report the answer as a throttle effect.
    buckets: dict[int, dict[str, list[float]]] = {}
    for f in mid:
        proxy = abs(_num(f, "steering_deg")) / _num(f, "lat_g")
        band = int(_num(f, "speed_kph") // _SPEED_BUCKET_KPH)
        throttle = _num(f, "throttle_pct")
        if throttle is None:
            continue
        slot = buckets.setdefault(band, {"off": [], "on": []})
        if throttle <= _OFF_THROTTLE_PCT:
            slot["off"].append(proxy)
        elif throttle >= _ON_THROTTLE_PCT:
            slot["on"].append(proxy)

    paired = {band: slot for band, slot in buckets.items()
              if len(slot["off"]) >= _MIN_BUCKET_FRAMES
              and len(slot["on"]) >= _MIN_BUCKET_FRAMES}
    off_n = sum(len(s["off"]) for s in paired.values())
    on_n = sum(len(s["on"]) for s in paired.values())
    if not paired or off_n < _MIN_BAND_FRAMES or on_n < _MIN_BAND_FRAMES:
        return None

    # Each bucket weighted by the smaller of its two bands, so a speed range
    # with one good band and one thin one cannot carry the verdict.
    ratios, weights = [], []
    for slot in paired.values():
        off_mean, on_mean = mean(slot["off"]), mean(slot["on"])
        if not off_mean:
            continue
        ratios.append(on_mean / off_mean)
        weights.append(min(len(slot["off"]), len(slot["on"])))
    if not ratios:
        return None
    ratio = sum(r * w for r, w in zip(ratios, weights)) / sum(weights)
    basis = (f"steering per lateral g, on throttle vs off, compared within "
             f"{len(paired)} speed buckets of {_SPEED_BUCKET_KPH:.0f} km/h "
             f"(off n={off_n}, on n={on_n}); weighted ratio {ratio:.2f}")
    if ratio > 1.0 + _THROTTLE_BAND_RATIO:
        return Answer("mostly on throttle - it reads as power-on push",
                      DERIVED, basis, off_n + on_n)
    if ratio < 1.0 - _THROTTLE_BAND_RATIO:
        return Answer("mostly off throttle - it is there before the power is",
                      DERIVED, basis, off_n + on_n)
    return Answer("both phases - the proxy barely moves between them",
                  DERIVED, basis, off_n + on_n)


# --------------------------------------------------------------- context lines


def _gearbox_line(store, context) -> str | None:
    """What the one verifiable setup value says, for the question beside it."""
    sheet = getattr(context, "sheet", None)
    if sheet is None or not getattr(sheet, "gears", None) or not context.laps:
        return None
    verdict = gearing.matches_sheet(context.laps, sheet.gears)
    if verdict is True:
        return ("The gearbox in the car matches the sheet, which is the only "
                "setup value the feed can verify.")
    if verdict is False:
        return ("The gearbox in the car does NOT match the sheet - so the "
                "app's record of this car is already wrong somewhere.")
    return None


def _wheelspin_line(store, context) -> str | None:
    answer = rear_wheelspin_pattern(store, context)
    if answer is None:
        return None
    return f"Off the exits I can see {answer.value} ({answer.evidence})."


# ------------------------------------------------------------------- registry


REGISTRY: tuple[Question, ...] = (
    Question(
        key="brake_balance_as_run",
        asks="What brake balance is actually in the car right now?",
        feeds=("every braking diagnosis", "front tyre life", "setup record"),
        impact=10,
        unmeasurable_because=(
            "GT7 broadcasts no brake balance. The gearbox is the only one of "
            "the 23 setup values with ground truth in the feed"),
        context_line=_gearbox_line,
    ),
    Question(
        key="assist_regulation",
        asks="Is the assist setting a series regulation or your choice?",
        feeds=("rear stability plan", "which levers are available"),
        impact=7,
        unmeasurable_because=(
            "a league rule is not in the telemetry, and the event row records "
            "what is set rather than whether it may be changed"),
        kinds=(BRIEF, RACE_PLAN, QUALI_PLAN),
    ),
    Question(
        key="braking_feel",
        asks=("Under braking, does the car let go on the downshift as you "
              "release, or with the brake hard on in a straight line?"),
        feeds=("LSD braking sensitivity", "brake balance", "rear damping"),
        impact=8,
        unmeasurable_because=(
            "no channel carries confidence, hesitation or the moment a driver "
            "stops trusting the rear - and the two causes want opposite fixes"),
        kinds=(REFINEMENT, OUTCOME),
    ),
    Question(
        key="clean_air",
        asks="Were those laps in clean air, or were you in traffic or a tow?",
        feeds=("pace baseline", "fuel burn", "strategy"),
        impact=6,
        unmeasurable_because=(
            "the feed carries no proximity, no closing speed and no opponent "
            "positions, so a tow cannot be detected at all"),
        kinds=(REFINEMENT, OUTCOME, RACE_PLAN),
    ),
    Question(
        key="push_location",
        asks=("Which corners does it push in, and does it match what I am "
              "seeing?"),
        feeds=("mid-corner balance", "ARB", "differential"),
        impact=7,
        unmeasurable_because=(
            "per-corner comparison is below the measured noise floor - a "
            "corner is 3-4x noisier in relative terms than a whole lap"),
        context_line=_wheelspin_line,
        kinds=(REFINEMENT, OUTCOME),
    ),
    Question(
        key="push_throttle_state",
        asks=("Is the push there before you pick up the throttle, or only "
              "once you are on the power?"),
        feeds=("mid-corner table vs power-on table", "LSD acceleration"),
        impact=8,
        resolver=push_throttle_state,
        kinds=(REFINEMENT, OUTCOME),
    ),
    Question(
        key="rear_wheelspin_pattern",
        asks=("On an exit that will not hook up, does one rear wheel light up "
              "alone or do both go together?"),
        feeds=("LSD acceleration sensitivity",),
        impact=8,
        resolver=rear_wheelspin_pattern,
        kinds=(REFINEMENT, OUTCOME),
    ),
    Question(
        key="tyre_state_at_end",
        asks="How worn were the tyres at the end of the run?",
        feeds=("wear rate", "stint length", "strategy"),
        impact=5,
        resolver=tyre_state_at_end,
        kinds=(REFINEMENT, OUTCOME, RACE_PLAN),
    ),
    Question(
        key="representative",
        asks=("Was anything about that run unrepresentative - a mistake, a "
              "different technique, or something you were deliberately "
              "testing?"),
        feeds=("whether these laps may be fitted at all",),
        impact=6,
        unmeasurable_because=(
            "the app can see that a lap was slow and never why it was slow. "
            "A deliberate fuel-saving lap and a bad lap look identical"),
        kinds=(REFINEMENT, OUTCOME),
    ),
)


def _validate(registry: tuple[Question, ...] = REGISTRY) -> None:
    seen = set()
    for question in registry:
        if question.key in seen:
            raise RegistryError(f"duplicate question key {question.key!r}")
        seen.add(question.key)


_validate()


# ---------------------------------------------------------------------- gate


def resolve(store, context, *, kind: str = REFINEMENT,
            limit: int = MAX_QUESTIONS,
            registry: tuple[Question, ...] = REGISTRY) -> Resolution:
    """Run every resolver, then ask only what is left.

    **A resolver that raises does not answer.** It is recorded in `failed` and
    its question is asked, because a broken query producing silence is exactly
    the failure this module exists to prevent — the driver would never learn
    that the app had stopped looking.
    """
    answered: dict[str, Answer] = {}
    suppressed: list[str] = []
    failed: list[str] = []
    survivors: list[Question] = []

    for question in registry:
        if kind not in question.kinds:
            continue
        answer = None
        if question.resolver is not None:
            try:
                answer = question.resolver(store, context)
            except Exception:                      # noqa: BLE001 - see docstring
                failed.append(question.key)
                answer = None
        if answer is not None:
            answered[question.key] = answer
            suppressed.append(question.key)
            continue
        survivors.append(question)

    survivors.sort(key=lambda q: (-q.impact, q.key))
    asked = []
    for question in survivors[:limit]:
        line = None
        if question.context_line is not None:
            try:
                line = question.context_line(store, context)
            except Exception:                      # noqa: BLE001
                line = None
        asked.append(Asked(question, line))

    return Resolution(answered=answered, asked=asked,
                      suppressed=tuple(suppressed), failed=tuple(failed))
