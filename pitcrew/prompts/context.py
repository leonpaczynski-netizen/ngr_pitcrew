"""Everything the app already knows, gathered once.

This is the half of a prompt the driver never types. It reads the store, the
reference catalogues and the export builder, and hands the builder a bundle of
facts with their provenance attached.

Two rules run through all of it:

* **Missing is absent, never zero.** A field the app does not have is `None`
  here and is omitted from the prompt there. Nothing is defaulted into
  existence to make a template look complete.
* **Nothing derived is presented as measured.** Slider ranges that came from a
  preset are marked estimated; a pit-loss figure that is still the app's own
  default says so; modelled wear travels with its model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from pitcrew.analysis.session import LapInput, counted_laps, session_export
from pitcrew.analysis.runs import classify_exclusions
from pitcrew.export.build import (
    build_event_export,
    event_lap_inputs,
    mark_incidents,
)
from pitcrew.export.payload import ExportRefused, to_json
from pitcrew.setup.sheet import RangeRecord, SetupChange, SetupSheet
from pitcrew.setup.vocabulary import RANGE_KEY_NAMES
from pitcrew.store import catalogs
from pitcrew.strategy.evidence import ASSUMED, DECLARED, MEASURED, MISSING

# The event columns whose value is still whatever the schema put there. Equal
# to the default is not proof the driver never looked at it, so this only ever
# adds "still the app default - confirm it", never downgrades the provenance.
EVENT_DEFAULTS = {"refuel_rate_lps": 2.5, "pit_loss_secs": 20.0}

RANGES_RECORD = "record"        # read off this car's own settings screen
RANGES_PRESET = "preset"        # GT7 typical windows, estimated
RANGES_NONE = "none"


@dataclass
class Ranges:
    """The slider limits a prompt will quote, and how much they are worth."""
    values: dict[str, list]
    source: str
    verified: bool = False
    measured_date: str | None = None
    preset_kind: str | None = None      # 'race' | 'road'

    def __bool__(self) -> bool:
        return bool(self.values)


@dataclass
class History:
    """The last time this car ran at this circuit."""
    event_name: str
    date: str
    sheet_name: str | None = None
    best_ms: int | None = None
    median_ms: int | None = None
    laps_counted: int = 0
    # (key, from, to) for every setting the current sheet moved. This is what
    # the last refinement actually changed, read from the two sheets rather
    # than from a note somebody remembered to write.
    deltas: list[tuple[str, float | None, float | None]] = field(
        default_factory=list)


@dataclass
class PromptContext:
    """The app's half of a prompt."""
    event: dict | None = None
    car: str | None = None
    car_spec: dict | None = None
    circuit_name: str | None = None
    circuit: catalogs.Circuit | None = None
    sheet: SetupSheet | None = None
    driver_changes: list[SetupChange] = field(default_factory=list)
    ranges: Ranges = field(default_factory=lambda: Ranges({}, RANGES_NONE))
    history: History | None = None

    # Present for refinement and outcome only.
    session_kind: str | None = None
    session_id: int | None = None
    laps: list[LapInput] = field(default_factory=list)
    session_totals: dict | None = None
    payload: dict | None = None
    payload_json: str | None = None
    # What the lobby's time-of-day preset actually does at this circuit,
    # measured off GT7's own clock. A sentence, or None where this preset
    # has never been run here. The brief needs it as much as the
    # refinement does and had no way to get it: "Afternoon" is a name, and
    # a race that sweeps three hours into the evening cools the track,
    # lengthens a stint and can leave a harder compound below its working
    # range - all of which is setup information before it is strategy.
    clock_note: str | None = None
    # **Both sides of the radio, for the debrief only.**
    #
    # The calls ledger says what the engineer said and whether it was taken. It
    # cannot say whether a call HELPED: a call that was right and ignored and a
    # call that was noise and ignored look identical in it, and the difference
    # is almost always in what the driver said back. Learning to be a better
    # engineer needs the reply.
    radio: list[dict] = field(default_factory=list)
    payload_refusal: str | None = None
    # Set only where exactly one compound ran, so the prose can say what the
    # payload says. `compounds_run` carries the rest, in order.
    compound: str | None = None
    compounds_run: list[str] = field(default_factory=list)
    # Off the stream, on the last recorded race lap. None when the race was
    # not recorded or the stream never reported a position.
    finish_position: int | None = None

    @property
    def has_telemetry(self) -> bool:
        return bool(self.laps)

    def missing(self) -> list[str]:
        """What a prompt built from this will have to leave out."""
        gaps = []
        if self.event is None:
            gaps.append("an event")
        if not self.car:
            gaps.append("a car")
        if self.circuit is None and self.circuit_name:
            gaps.append("this circuit's reference data")
        if self.sheet is None:
            gaps.append("the sheet as run")
        if self.ranges.source != RANGES_RECORD:
            gaps.append("measured slider ranges")
        return gaps


# ------------------------------------------------------------------ ranges

def resolve_ranges(store, car: str | None, spec: dict | None) -> Ranges:
    """The car's own limits if they were measured, a typical window if not.

    The difference is load-bearing: it decides whether the returned sheet can
    be entered without clamping, so it is carried through to the prompt rather
    than flattened into a table of numbers.
    """
    record: RangeRecord | None = store.get_range_record(car) if car else None
    if record is not None and record.ranges:
        return Ranges(
            values={k: list(v) for k, v in record.ranges.items()},
            source=RANGES_RECORD,
            verified=record.verified,
            measured_date=record.measured_date or None,
        )

    category = (spec or {}).get("category") or ""
    kind = "road" if category in ("", "Road Car") else "race"
    preset = catalogs.range_preset(kind)
    if not preset:
        return Ranges({}, RANGES_NONE)
    return Ranges(values=preset, source=RANGES_PRESET, verified=False,
                  preset_kind=kind)


# ----------------------------------------------------------------- history

def _event_all_laps(store, event_id: int) -> list[LapInput]:
    return (event_lap_inputs(store, event_id, "practice")
            + event_lap_inputs(store, event_id, "race"))


def _fitted_sheet(store, event_id: int) -> SetupSheet | None:
    for session in sorted(store.list_sessions(event_id),
                          key=lambda s: s["started_at"]):
        if session["setup_sheet_id"]:
            sheet = store.get_setup_sheet(session["setup_sheet_id"])
            if sheet is not None:
                return sheet
    return None


def combination_history(store, event: dict | None,
                        current: SetupSheet | None) -> History | None:
    """The most recent previous running of this car at this circuit.

    Prompt A's Context section used to be a free-text box. The app has every
    prior sheet, session and lap for the combination, so it fills it in — and
    where there is nothing, the prompt says "first run" rather than printing
    an empty heading.
    """
    if event is None or not event.get("car_name") or not event.get("track"):
        return None

    candidates = [
        other for other in store.list_events()
        if other["id"] != event["id"]
        and other["car_name"] == event["car_name"]
        and other["track"] == event["track"]
        and other["layout"] == event["layout"]
    ]
    for other in sorted(candidates, key=lambda e: e["created_at"], reverse=True):
        laps = _event_all_laps(store, other["id"])
        counted = counted_laps(laps)
        if not counted:
            continue
        times = [lap.lap_time_ms for lap in counted]
        previous = _fitted_sheet(store, other["id"])
        return History(
            event_name=other["name"],
            date=(other["created_at"] or "")[:10],
            sheet_name=previous.sheet_name if previous else None,
            best_ms=min(times),
            median_ms=round(median(times)),
            laps_counted=len(counted),
            deltas=_sheet_deltas(previous, current),
        )
    return None


def _sheet_deltas(previous: SetupSheet | None,
                  current: SetupSheet | None) -> list[tuple]:
    """Settings the current sheet moved away from the previous one.

    Only keys present in both are compared. A key that appears for the first
    time is not a change from zero — it is a value that was not recorded, and
    reporting it as `0 -> 3` would be a fabrication.
    """
    if previous is None or current is None:
        return []
    deltas = []
    for key, was in previous.values.items():
        now = current.values.get(key)
        if was is None or now is None or was == now:
            continue
        deltas.append((key, was, now))
    return deltas


def _clock_note(store, event) -> str | None:
    """What this lobby setting has been measured to do at this circuit.

    Read from the per-circuit record rather than recomputed: it is
    measured once per preset per circuit and reused, which is the whole
    point of storing it. None where it has never been run, which reads as
    "not known" rather than as "no day/night change".
    """
    from pitcrew.analysis.gameclock import ClockReading
    from pitcrew.analysis.resolve import circuit_key

    stored = store.get_track_clock(
        circuit_key(event["track"], event["layout"]),
        event["time_of_day"] or "")
    if not stored:
        return None
    reading = ClockReading(
        multiplier=stored["multiplier"], start_hour=stored["start_hour"],
        end_hour=None, stopped_at_hour=stored["stops_at_hour"],
        laps_sampled=stored["laps_sampled"], note="")
    from pitcrew.analysis.gameclock import _note
    return _note(reading.multiplier, reading.start_hour, None,
                 reading.stopped_at_hour, reading.laps_sampled)


# ------------------------------------------------------------------ gather

def gather(store, *, event_id: int | None = None, kind: str = "brief",
           session_id: int | None = None,
           game_version: str | None = None) -> PromptContext:
    """Assemble everything the app knows for one prompt.

    `kind` is the prompt: 'brief' needs no telemetry at all, 'refinement'
    reads the event's practice running, 'outcome' reads its race.

    `game_version` is the app-wide setting, used where the event does not
    carry one of its own. **The payload is refused without a version**,
    and a refused payload is a refinement prompt sent with no telemetry
    in it at all - which is the failure it exists to avoid, and which it
    was doing silently for every event created without the field filled
    in.
    """
    event = store.get_event(event_id) if event_id else None
    context = PromptContext(event=event)
    if event is None:
        return context

    context.car = event["car_name"] or None
    context.car_spec = catalogs.car_spec(context.car)
    context.circuit_name = _circuit_name(event)
    context.circuit = catalogs.circuit_for(event["track"], event["layout"])
    context.sheet = _fitted_sheet(store, event["id"]) or _latest_sheet(
        store, context.car)
    context.ranges = resolve_ranges(store, context.car, context.car_spec)
    context.history = combination_history(store, event, context.sheet)
    context.clock_note = _clock_note(store, event)
    if kind == "outcome":
        # Read only for the debrief. A refinement is about the car; this is
        # about how the engineer spoke and whether it landed.
        try:
            context.radio = store.event_radio(event["id"])
        except Exception:                                    # noqa: BLE001
            context.radio = []

    if kind == "brief":
        return context

    session_kind = "race" if kind == "outcome" else "practice"
    context.session_kind = session_kind
    # **Read once and used twice.** `build_event_export` below wants the same
    # laps, and used to read them again from scratch - the whole event
    # decompressed and JSON-parsed a second time, 3.2 s on one event. They
    # are handed over raw, because that function classifies them itself and
    # neither classifier mutates.
    raw_laps = event_lap_inputs(store, event["id"], session_kind)
    if not raw_laps:
        return context
    laps = raw_laps

    # **Classified before anything is counted off it**, exactly as the export
    # does and for the same reason: out-laps, incidents and laps whose fuel
    # burn says they never went round have to leave the set before a best or
    # a median is taken from it.
    #
    # This was missing, and the prompt disagreed with the payload attached to
    # it. On the 14 Aug Monza data the prose read "best lap 1:44.912 over 79
    # counted laps" and the payload underneath it read 1:46.828 over 73 - the
    # 1:44.9 being a lap that burned 0.16 L against a 6.4 L median, which is
    # a lap boundary landing inside a pit transition rather than a lap of the
    # circuit. The knowledge base would have read it as the car's potential
    # and built a sheet to reach it.
    capacity = _fuel_capacity(store, event["id"], session_kind)
    laps, _ = mark_incidents(laps)
    context.laps = classify_exclusions(laps, capacity)

    context.session_totals = session_export(
        context.laps, fuel_capacity_l=capacity)
    context.compound = _single_compound(context.laps)
    context.compounds_run = compounds_run(context.laps)

    if session_kind == "race":
        context.finish_position = _finish_position(store, event["id"])

    sessions = store.list_sessions(event["id"], session_kind)
    if sessions:
        context.session_id = sorted(
            sessions, key=lambda s: s["started_at"])[-1]["id"]
        context.driver_changes = store.list_setup_changes(context.session_id)

    try:
        context.payload = build_event_export(
            store, event["id"], kind=session_kind,
            game_version=game_version, laps=raw_laps)
        context.payload_json = to_json(context.payload)
    except ExportRefused as exc:
        # Refusing to emit is the designed behaviour: the consumer is a
        # reader, so a malformed payload is misread rather than rejected. The
        # prompt goes out without it and says why.
        context.payload = None
        context.payload_refusal = " · ".join(
            line.strip(" -") for line in str(exc).splitlines()[1:]) or str(exc)
    except ValueError as exc:
        context.payload = None
        context.payload_refusal = str(exc)
    return context


def _latest_sheet(store, car: str | None) -> SetupSheet | None:
    if not car:
        return None
    sheets = store.list_setup_sheets(car)
    return sheets[0] if sheets else None


def _fuel_capacity(store, event_id: int, kind: str) -> float | None:
    """The first **plausible** tank, matching `export/build.py`.

    A stored 0 is not an electric declaration - GT7 reports 0 both for a car
    with no tank and for a packet that arrived before the car loaded, and
    taking the first non-None handed the second one to `classify_exclusions`,
    which skips the fuel-plausibility gate on a capacity of 0. The prompt and
    the payload have to count the same laps or the prose contradicts the JSON
    beneath it.
    """
    sessions = list(store.list_sessions(event_id, kind))
    for session in sessions:
        if session["fuel_capacity_l"] is not None \
                and session["fuel_capacity_l"] > 0:
            return session["fuel_capacity_l"]
    return None


def _finish_position(store, event_id: int) -> int | None:
    """Position on the last recorded race lap.

    Zero is the stream's "not reported", not first place, so it reads as
    absent - which is the whole missing-is-null rule in one field.
    """
    rows = store.list_event_laps(event_id, "race")
    for row in reversed(rows):
        position = row.get("position")
        if position:
            return int(position)
    return None


def compounds_run(laps: list[LapInput]) -> list[str]:
    """Every compound the counted laps ran, in the order they ran them.

    **Never a vote.** This is the export's own rule (`export/build.py`), which
    was applied there and missed here: the prompt printed
    `compound **RM**` by majority over a payload in the same document that
    correctly omitted `meta.compound` and listed both. Prose and JSON stated
    mutually exclusive things about which rubber ran, and the prose is what
    gets read.

    The vote was also non-deterministic. `max(set(tags), key=tags.count)`
    iterates a set of strings, so `PYTHONHASHSEED` decided a tie - six fresh
    processes over five RM and five RS laps returned RM RS RM RS RS RS - and
    a tie is the normal shape of a comparison test.
    """
    seen: list[str] = []
    for lap in counted_laps(laps):
        if lap.compound and lap.compound not in seen:
            seen.append(lap.compound)
    return seen


def _single_compound(laps: list[LapInput]) -> str | None:
    """The compound, only where the session ran exactly one."""
    codes = compounds_run(laps)
    return codes[0] if len(codes) == 1 else None


def _circuit_name(event: dict) -> str:
    track = event["track"] or ""
    layout = event["layout"]
    return f"{track} ({layout})" if layout else track


# ------------------------------------------------------------- provenance

def event_provenance(event: dict, column: str) -> tuple[str, str]:
    """(tag, note) for an event figure the strategy rests on.

    The tags are `strategy/evidence.py`'s vocabulary, so a prompt and a plan
    describe the same number the same way.
    """
    value = event.get(column)
    if value is None:
        return MISSING, "not set"
    default = EVENT_DEFAULTS.get(column)
    if default is not None and value == default:
        return DECLARED, "still the app default — confirm it"
    return DECLARED, ""


__all__ = [
    "ASSUMED", "DECLARED", "History", "MEASURED", "MISSING",
    "PromptContext", "RANGES_NONE", "RANGES_PRESET", "RANGES_RECORD",
    "Ranges", "RANGE_KEY_NAMES", "combination_history", "event_provenance",
    "gather", "resolve_ranges",
]
