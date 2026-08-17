"""Composing the three prompts.

Prompts A and B are ports of `buildBrief()` and `buildLog()` from
`reference/gt7-race-engineering.html`.  **Their wording is tuned for the
knowledge base that reads them and is not to be improved here** — it lives in
`templates.json`, and what changed in the port is only where the values come
from.  Prompt C is new: by the end of a race the app knows more than at any
other moment, and the post-race case used to be a variant branch that
under-used all of it.

Nothing in this module advises.  It states what happened, with provenance, and
asks.  If a rule about camber ever appears here it is in the wrong repository.

The one discipline everything below obeys: **a section with no data is omitted,
or carries an explicit "not measured" sentence.**  Never a zero, never a dash
standing in for a number nobody took.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

from pitcrew.export.payload import APP_VERSION
from pitcrew.prompts import context as ctx
from pitcrew.prompts.report import DriverReport
from pitcrew.prompts.templates import PROMPT_VERSION, templates
from pitcrew.setup.vocabulary import SETUP_KEY_NAMES, describe
from pitcrew.store import catalogs

BRIEF = "brief"
REFINEMENT = "refinement"
OUTCOME = "outcome"
KINDS = (BRIEF, REFINEMENT, OUTCOME)

SESSION_NAMES = {"practice": "Practice / shakedown", "race": "Race — completed"}

# The prompt each kind is titled after, for the log and the screen.
KIND_LABELS = {
    BRIEF: "Setup Brief",
    REFINEMENT: "Setup Refinement",
    OUTCOME: "Event Outcome",
}


class PromptRefused(ValueError):
    """The prompt would be misleading. Fix the input rather than send it."""


@dataclass
class Prompt:
    kind: str
    text: str
    version: str = PROMPT_VERSION
    app_version: str = APP_VERSION
    # Things the driver should know are absent from what he is about to paste.
    warnings: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind)


# --------------------------------------------------------------- formatting

def lap_time(ms: int | None) -> str | None:
    """Milliseconds as a lap time. None stays None — never "0:00.000"."""
    if not ms:
        return None
    minutes, remainder = divmod(int(ms), 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def _number(value, decimals: int = 6) -> str:
    """A figure for prose, at whatever precision it actually has.

    `None` says so in words rather than printing 0.  And the significant
    digits are never truncated: rounding 0.003 s/L/lap to two places printed
    it as **0**, which is the exact failure this whole feature exists to
    prevent — a number that means "small" read as a number that means "none".
    """
    if value is None:
        return "not recorded"
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    if isinstance(value, float):
        shown = f"{value:.{max(decimals, 6)}g}"
        # %g falls back to scientific notation on extremes; a setup sheet is
        # not the place for 3e-05.
        return f"{value:.10f}".rstrip("0").rstrip(".") if "e" in shown else shown
    return str(value)


def _clicks_and_percent(key: str, value: float,
                        ranges: ctx.Ranges) -> tuple[str, str]:
    """A value as clicks from minimum and percent of slider range.

    The programme reasons in percent of range rather than absolutes, because
    GT7's ranges are per-car: "3.5 Hz" means different things on different
    cars. Both are em-dash when the range does not cover the key — an unknown
    position is not position zero.
    """
    bounds = ranges.values.get(key)
    if not bounds or bounds[0] is None or bounds[1] is None:
        return "—", "—"
    low, high = float(bounds[0]), float(bounds[1])
    step = catalogs.range_step(key)
    clicks = "—"
    if step:
        clicks = f"{round((value - low) / step):+d}"
    percent = "—" if high == low else f"{(value - low) / (high - low):.0%}"
    return clicks, percent


class Lines(list):
    """A prompt under construction. `blank()` never doubles a blank line."""

    def add(self, *lines: str) -> None:
        for line in lines:
            self.append(line)

    def blank(self) -> None:
        if self and self[-1] != "":
            self.append("")

    def render(self) -> str:
        while self and self[-1] == "":
            self.pop()
        return "\n".join(self)


# ------------------------------------------------------------------ blocks

def _range_rows(ranges: ctx.Ranges) -> list[str]:
    rows = []
    for key in SETUP_KEY_NAMES:
        bounds = ranges.values.get(key)
        if not bounds:
            continue
        label = catalogs.range_label(key) or (describe(key).label
                                              if describe(key) else key)
        unit = catalogs.range_unit(key)
        suffix = f" {unit}" if unit else ""
        low = "—" if bounds[0] is None else f"{_number(bounds[0], 3)}{suffix}"
        high = "—" if bounds[1] is None else f"{_number(bounds[1], 3)}{suffix}"
        rows.append(f"| {label} | {low} | {high} |")
    return rows


def _return_contract(lines, *, first_sheet: bool = False,
                     quali_rule: bool = True,
                     extra: str | None = None) -> None:
    """How to send the sheets back so the app can read them.

    Every prompt asked for markdown and nothing else, so every reply came
    back as markdown - and a setup sheet that only exists as prose is one the
    driver retypes by hand, which is where transcription errors come from.
    The reader was already there: `setup/parse.py` has always accepted the
    export contract's own JSON. The prompt simply never asked for it.

    Asked for **in addition to** the readable sheet, never instead of it. He
    reads the prose and argues with it; the app reads the JSON and enters it.
    Replacing one with the other would trade a transcription problem for a
    comprehension one.
    """
    shared = templates()["shared"]
    lines.add("", shared["returnHeading"])
    lines.add(shared["returnLead"])
    if extra:
        lines.add("", extra)
    if quali_rule:
        lines.add("", shared["returnQualiRule"])
    lines.add("")
    # A first sheet and a revision need opposite rules about omission:
    # there is nothing to leave unchanged on a sheet that does not exist
    # yet, and a key left out of one is a value the app cannot enter.
    lines.add(*shared["returnRulesBrief" if first_sheet
                      else "returnRulesRevision"])
    lines.add("")
    lines.add(*shared["returnShape"])
    lines.add("", shared["returnVocabHeading"])
    # The vocabulary itself rather than a pointer to it. A key list the reply
    # has to match exactly is not something to make anybody go and look up,
    # and an invented key is silently dropped on the way back in.
    lines.add("", "`" + "`, `".join(SETUP_KEY_NAMES) + "`")


def _ranges_section(lines: Lines, ranges: ctx.Ranges, *, brief: bool) -> None:
    """The slider ranges, and — the part that matters — how much they are worth.

    Verified against estimated decides whether the returned sheet is enterable
    without clamping, so the provenance sentence is never dropped.
    """
    shared = templates()["shared"]
    rows = _range_rows(ranges)
    if not rows:
        lines.blank()
        lines.add(shared["rangesHeading"], "", shared["rangesNoneOnFile"], "")
        return

    lines.blank()
    lines.add(shared["rangesHeading"])
    if ranges.source == ctx.RANGES_RECORD:
        if ranges.measured_date:
            lines.add(shared["rangesOnFile"].format(date=ranges.measured_date))
        else:
            lines.add(shared["rangesVerified"])
    elif brief:
        kind = "road-car" if ranges.preset_kind == "road" else "race-car"
        lines.add(shared["rangesEstimatedBrief"].format(kind=kind))
        lines.add("")
        lines.add(shared["rangesSendBack"])
    else:
        lines.add(shared["rangesEstimatedLog"])

    lines.add("")
    lines.add(*shared["rangesTableHead"])
    lines.add(*rows)
    lines.add("")
    lines.add(shared["rangesRuleBrief"] if brief else shared["rangesRuleLog"])
    lines.add("")


def _setup_section(lines: Lines, context: ctx.PromptContext) -> None:
    """The sheet as run — real state, not a paste box.

    Every value that has a range is given three ways, absolute plus clicks
    plus percent, so a returned recommendation survives the range being
    different from the one on file.
    """
    template = templates()["refinement"]
    lines.blank()
    lines.add(template["setupHeading"])
    sheet = context.sheet
    if sheet is None:
        lines.add(template["setupNotRecorded"], "")
        return

    lines.add(f"- Sheet in the car: **{sheet.sheet_name}**")
    verified = ("read off the car's own settings screen"
                if context.ranges.source == ctx.RANGES_RECORD
                else "estimated — the ranges below are typical windows, not "
                     "this car's own limits")
    lines.add(f"- Clicks and percent are against ranges that are {verified}.")
    lines.add("")
    lines.add("| Setting | As run | Clicks from min | % of range |",
              "|---|---|---|---|")

    for key in SETUP_KEY_NAMES:
        value = sheet.values.get(key)
        if value is None:
            continue
        spec = describe(key)
        label = catalogs.range_label(key) or (spec.label if spec else key)
        unit = catalogs.range_unit(key) or (spec.unit if spec else "")
        clicks, percent = _clicks_and_percent(key, float(value),
                                              context.ranges)
        shown = _number(value, spec.decimals if spec else 2)
        lines.add(f"| {label} | {shown}{' ' + unit if unit else ''} "
                  f"| {clicks} | {percent} |")

    missing = [k for k in SETUP_KEY_NAMES if sheet.values.get(k) is None]
    if missing:
        lines.add("")
        lines.add(f"- Not recorded on this sheet: {', '.join(missing)}. "
                  f"Not measured, not zero.")
    if sheet.gears:
        lines.add("- Gear ratios, 1st to top: "
                  + "  ".join(f"{ratio:g}" for ratio in sheet.gears))
    if sheet.performance:
        lines.add(f"- Performance: {_kv(sheet.performance)}")
    if sheet.build:
        lines.add(f"- Build: {_kv(sheet.build)}")

    if context.driver_changes:
        lines.add("")
        lines.add("- Driver changes away from it:")
        for change in context.driver_changes:
            lines.add(f"  - from lap {change.from_lap}: `{change.key}` "
                      f"{_number(change.from_value)} → "
                      f"{_number(change.to_value)}")
    else:
        lines.add("- Driver changes away from it: none recorded.")
    lines.add("")


def _kv(payload: dict) -> str:
    return ", ".join(f"{key} {_number(value)}"
                     for key, value in payload.items() if value is not None)


def _event_context(context: ctx.PromptContext) -> list[str]:
    """The event, circuit and car as facts, with nothing invented."""
    event = context.event or {}
    lines: list[str] = []

    length = _race_length(event)
    lines.append(f"- Format: **{_race_format(event)}**"
                 + (f" · Length **{length}**" if length else ""))

    stops = event.get("mandatory_stops")
    lines.append(
        f"- Tyre wear **{event.get('tyre_wear_mult') or 'not set'}** · "
        f"Fuel **{event.get('fuel_mult') or 'not set'}**"
        + (f" · Mandatory stops **{stops}**" if stops is not None else ""))

    compounds = event.get("available_compounds") or []
    if compounds:
        lines.append("- Compounds available: " + ", ".join(compounds))

    conditions = [
        f"Start: {event['start_type']}" if event.get("start_type") else "",
        f"Conditions: {(event.get('weather') or '').title()}"
        if event.get("weather") else "",
        event.get("time_of_day") or "",
    ]
    conditions = [part for part in conditions if part]
    if conditions:
        lines.append("- " + " · ".join(conditions))

    # **What that preset actually does here, measured.** The name on its own
    # is not information: "Afternoon" is a different hour at every circuit and
    # says nothing about whether the light holds. A race that sweeps three
    # hours into the evening cools the track, lengthens a stint and can leave
    # a harder compound below its working range - which is setup information
    # before it is strategy, and the brief had no way to carry it.
    if context.clock_note:
        lines.append("- Time of day, measured off GT7's own clock: "
                     + context.clock_note)

    assists = []
    if event.get("abs_setting"):
        assists.append(f"ABS **{event['abs_setting']}**")
    if event.get("tcs") is not None:
        assists.append(f"TCS **{event['tcs']}**")
    if event.get("countersteer") is not None:
        assists.append(
            f"Countersteer {'On' if event['countersteer'] else 'Off'}")
    if assists:
        lines.append("- " + " · ".join(assists))

    circuit = context.circuit
    if circuit is not None:
        lines.append(
            f"- Circuit reference: downforce **{circuit.downforce}**, "
            f"mechanical grip **{circuit.mechanical_grip}**, tyre wear "
            f"**{circuit.wear_severity}/5** (wears {circuit.wear_axle}), "
            f"braking **{circuit.braking_severity}/5**, pit loss ≈ "
            f"**{circuit.pit_loss_pct_of_lap}%** of a lap")

    car_line = _car_reference_line(context)
    if car_line:
        lines.append(car_line)
    return lines


def _race_format(event: dict) -> str:
    return "Timed race" if event.get("race_type") == "time" else "Laps race"


def _race_length(event: dict) -> str | None:
    length = event.get("race_laps")
    if not length:
        return None
    unit = "minutes" if event.get("race_type") == "time" else "laps"
    return f"{length} {unit}"


def _car_reference_line(context: ctx.PromptContext) -> str | None:
    spec = context.car_spec or {}
    if not spec and not context.sheet:
        return None
    bits = [spec.get("category"), _drivetrain(spec), spec.get("aspiration")]
    bits = [b for b in bits if b]
    head = "- Car reference: " + ", ".join(bits) if bits else "- Car reference:"
    build = (context.sheet.build if context.sheet else {}) or {}
    bhp = build.get("bhp") or spec.get("power_hp")
    weight = build.get("weightKg") or spec.get("weight_kg")
    source = "as raced" if build.get("bhp") or build.get("weightKg") else "stock"
    if bhp and weight:
        head += f" · {source} **{_number(bhp)} bhp / {_number(weight)} kg**"
    pp = build.get("pp") or spec.get("pp_rating")
    if pp:
        head += f" · PP {_number(pp)}"
    return head


def _drivetrain(spec: dict) -> str | None:
    layout = spec.get("drivetrain")
    return f"{layout} layout" if layout else None


# ---------------------------------------------------------------- prompt A

def _build_brief(context: ctx.PromptContext, report: DriverReport,
                 today: str) -> Prompt:
    template = templates()["brief"]
    shared = templates()["shared"]
    warnings: list[str] = []
    lines = Lines()

    lines.add(template["title"], "", template["standing"], "")

    # --- Car
    spec = context.car_spec or {}
    lines.add(template["carHeading"])
    descriptors = [spec.get("category"), spec.get("drivetrain"),
                   spec.get("aspiration")]
    descriptors = [d for d in descriptors if d]
    lines.add(f"- **{context.car}**"
              + (f" — {', '.join(descriptors)}" if descriptors else ""))

    build = (context.sheet.build if context.sheet else {}) or {}
    performance = (context.sheet.performance if context.sheet else {}) or {}
    bhp, weight = build.get("bhp"), build.get("weightKg")
    if bhp and weight:
        raced = f"- As raced: **{_number(bhp)} bhp · {_number(weight)} kg**"
        if build.get("pp"):
            raced += f" · PP {_number(build['pp'])}"
        if (context.event or {}).get("pp_cap"):
            raced += f" · PP cap {_number(context.event['pp_cap'])}"
        lines.add(raced)
        lines.add(f"- Power-to-weight: {weight / bhp:.2f} kg/hp")
    else:
        warnings.append("the as-raced build (bhp, weight, PP) is not on the "
                        "sheet, so the brief carries the stock figures only")

    if spec.get("power_hp") and spec.get("weight_kg"):
        lines.add(f"- Stock reference: {_number(spec['power_hp'])} bhp / "
                  f"{_number(spec['weight_kg'])} kg"
                  + (f" / PP {_number(spec['pp_rating'])}"
                     if spec.get("pp_rating") else ""))
    if performance:
        lines.add(f"- Performance parts: {_kv(performance)}")
    aero = _aero_line(context)
    if aero:
        lines.add(aero)
    lines.add("")

    # --- Circuit
    lines.add(template["circuitHeading"])
    circuit = context.circuit
    if circuit is None:
        lines.add(template["circuitUnknown"].format(
            circuit=context.circuit_name or "unnamed circuit"))
        warnings.append(f"{context.circuit_name!r} is not in the circuit "
                        f"reference, so the brief has no length, corner count "
                        f"or wear severity for it")
    else:
        lines.add(f"- **{circuit.name}** — {circuit.length_km} km, "
                  f"{circuit.corners} corners, Gr.3 reference lap "
                  f"{circuit.gr3_reference_lap}")
        lines.add(f"- Downforce requirement **{circuit.downforce}** · "
                  f"mechanical-grip priority **{circuit.mechanical_grip}**")
        lines.add(f"- Tyre wear severity **{circuit.wear_severity}/5** "
                  f"(wears {circuit.wear_axle}) · braking severity "
                  f"**{circuit.braking_severity}/5**")
        lines.add(f"- Pit loss ≈ **{circuit.pit_loss_pct_of_lap}% of one lap**")
    lines.add("")

    # --- Event
    event = context.event or {}
    lines.add(template["eventHeading"])
    length = _race_length(event)
    lines.add(f"- Format: **{_race_format(event)}**"
              + (f" · Length: **{length}**" if length else ""))
    stops = event.get("mandatory_stops")
    lines.add(f"- Tyre wear **{event.get('tyre_wear_mult') or 'not set'}** · "
              f"Fuel **{event.get('fuel_mult') or 'not set'}**"
              + (f" · Mandatory stops **{stops}**" if stops is not None else ""))
    if event.get("available_compounds"):
        lines.add("- Compounds available: "
                  + ", ".join(event["available_compounds"]))
    conditions = [f"Start: {event['start_type']}" if event.get("start_type")
                  else "",
                  f"Conditions: {(event.get('weather') or '').title()}"
                  if event.get("weather") else "",
                  event.get("time_of_day") or ""]
    conditions = [part for part in conditions if part]
    if conditions:
        lines.add("- " + " · ".join(conditions))
    # The brief needs this as much as the refinement does, and for a setup
    # reason rather than a strategy one: a race that sweeps three hours into
    # the evening cools the track, and a harder compound that never comes up
    # to temperature is a setup problem the sheet has to answer before the
    # first lap is driven.
    if context.clock_note:
        lines.add("- Time of day, measured off GT7's own clock: "
                  + context.clock_note)
    for line in _strategy_inputs(event):
        lines.add(line)
    if event.get("priority"):
        lines.add(f"- Priority this round: **{event['priority']}**")
    lines.add("")

    # --- Ranges
    _ranges_section(lines, context.ranges, brief=True)
    if context.ranges.source != ctx.RANGES_RECORD:
        warnings.append("this car's slider ranges have never been measured, "
                        "so the brief goes out with estimated windows")

    # --- Assists and hardware
    lines.add(template["assistsHeading"])
    assists = []
    if event.get("abs_setting"):
        assists.append(f"ABS **{event['abs_setting']}**")
    if event.get("tcs") is not None:
        assists.append(f"TCS **{event['tcs']}**")
    if event.get("countersteer") is not None:
        assists.append(
            f"Countersteer assist {'On' if event['countersteer'] else 'Off'}")
    if assists:
        lines.add("- " + " · ".join(assists))
    lines.add(shared["rigLine"], "")

    # --- Context, from real history rather than a free-text box
    lines.add(template["contextHeading"])
    history = context.history
    if history is None:
        lines.add(template["contextFirstRun"])
    else:
        head = (f"- Last run of this combination: **{history.event_name}**, "
                f"{history.date}")
        if history.sheet_name:
            head += f" on sheet **{history.sheet_name}**"
        lines.add(head)
        pace = []
        if history.best_ms:
            pace.append(f"best {lap_time(history.best_ms)}")
        if history.median_ms:
            pace.append(f"median {lap_time(history.median_ms)}")
        if pace:
            lines.add(f"- That run: {', '.join(pace)} over "
                      f"{history.laps_counted} counted laps")
        if history.deltas:
            lines.add("- Changed since: " + ", ".join(
                f"`{key}` {_number(was)} → {_number(now)}"
                for key, was, now in history.deltas))
    if event.get("notes"):
        lines.add(f"- Notes: {event['notes']}")
    if report.notes.strip():
        lines.add(f"- Notes: {report.notes.strip()}")
    lines.add("")

    # --- Required output
    lines.add(template["requiredHeading"])
    lines.add(*template["required"])
    if context.ranges:
        lines.add(template["requiredRangeCheck"])
    _return_contract(lines, first_sheet=True)
    lines.add("", "---")
    lines.add(template["footer"].format(
        date=today, baseline=templates()["gt7Baseline"],
        promptVersion=PROMPT_VERSION))
    return Prompt(BRIEF, lines.render(), warnings=warnings)


def _aero_line(context: ctx.PromptContext) -> str | None:
    """What the sheet says about adjustable aero, and nothing more.

    Derived only from downforce values that were actually entered. An unentered
    downforce is not "no wing fitted" — it is a value nobody recorded, and
    saying otherwise would put a fabricated fact in a setup brief.
    """
    sheet = context.sheet
    if sheet is None:
        return None
    front = sheet.values.get("df_f") is not None
    rear = sheet.values.get("df_r") is not None
    if front and rear:
        return "- Adjustable aero: front and rear, both on the sheet"
    if rear:
        return "- Adjustable aero: rear only on the sheet"
    if front:
        return "- Adjustable aero: front only on the sheet"
    return None


def _strategy_inputs(event: dict) -> list[str]:
    """Refuel rate and pit loss, each with its provenance.

    At the current event refuel is 1 L/s against a 2.5 default, and it decides
    the whole race — a brief that omits it gets a strategy note built on the
    wrong number.
    """
    out = []
    for column, label, unit in (("refuel_rate_lps", "Refuel rate", "L/s"),
                                ("pit_loss_secs", "Pit loss", "s")):
        value = event.get(column)
        if value is None:
            continue
        tag, note = ctx.event_provenance(event, column)
        line = f"- {label}: **{_number(value)} {unit}** [{tag}]"
        if note:
            line += f" — {note}"
        out.append(line)
    return out


# ------------------------------------------------------- prompts B and C

def _session_line(context: ctx.PromptContext) -> str:
    totals = context.session_totals or {}
    kind = context.session_kind or "practice"
    parts = [f"- Type: **{SESSION_NAMES.get(kind, kind)}**"]
    if totals.get("lapsRun") is not None:
        parts.append(f"laps run **{totals['lapsRun']}**")
    if totals.get("lapsCounted") is not None:
        parts.append(f"laps counted **{totals['lapsCounted']}**")
    # One compound only where one ran. A session that ran three is not a
    # session with a compound, and the payload attached to this same prompt
    # says so - it omits `meta.compound` and lists `compoundsRun`.
    if context.compound:
        parts.append(f"compound **{context.compound}**")
    elif context.compounds_run:
        parts.append("compounds run **"
                     + " / ".join(context.compounds_run) + "**")
    return " · ".join(parts)


def _exclusion_line(context: ctx.PromptContext) -> str | None:
    dropped = [(lap.lap_num, lap.reason_not_counted())
               for lap in context.laps if not lap.counted]
    if not dropped:
        return None
    return "- Excluded: " + ", ".join(f"lap {num} {reason}"
                                      for num, reason in dropped)


def _pace_lines(context: ctx.PromptContext,
                report: DriverReport) -> list[str]:
    totals = context.session_totals or {}
    lines: list[str] = []

    pace = []
    if totals.get("bestLapMs"):
        pace.append(f"Best lap **{lap_time(totals['bestLapMs'])}**")
    if totals.get("medianLapMs"):
        pace.append(f"median **{lap_time(totals['medianLapMs'])}**")
    if totals.get("lapTimeStdDevMs") is not None:
        pace.append(f"spread **{totals['lapTimeStdDevMs']} ms**")
    if pace:
        lines.append("- " + " · ".join(pace)
                     + f" over {totals.get('lapsCounted', 0)} counted laps")
    if totals.get("greenLapRefMs"):
        lines.append(f"- Green-tyre reference lap: "
                     f"**{lap_time(totals['greenLapRefMs'])}** — every "
                     f"degradation figure below is measured against it")

    fuel = []
    if totals.get("fuelUsedPerLapL") is not None:
        fuel.append(f"used **{_number(totals['fuelUsedPerLapL'], 2)} L/lap** "
                    f"(median)")
    if totals.get("fuelCapacityL") is not None:
        fuel.append(f"tank **{_number(totals['fuelCapacityL'])} L**")
    if fuel:
        lines.append("- Fuel: " + " · ".join(fuel))

    gauge = [lap for lap in context.laps if lap.worst_wear is not None]
    if gauge:
        readings = "; ".join(
            f"lap {lap.lap_num} "
            + " ".join(f"{corner.upper()} {value:.0%}"
                       for corner, value in lap.wear_by_corner.items()
                       if value is not None)
            for lap in gauge)
        lines.append(f"- Tyre gauge, read off the in-game HUD: {readings}")
        worst = gauge[-1]
        if worst.worst_corner:
            lines.append(
                f"- Limiting corner at lap {worst.lap_num}: "
                f"**{worst.worst_corner.upper()} at {worst.worst_wear:.0%}** "
                f"consumed. Stint length is set by this corner, not by an "
                f"axle average.")
        else:
            # All the read corners were equal. Nominating one anyway would
            # hand the knowledge base an asymmetry the driver never saw.
            lines.append(
                f"- Limiting wear at lap {worst.lap_num}: "
                f"**{worst.worst_wear:.0%}** consumed, even across the "
                f"corners he read. Stint length is set by the worst corner, "
                f"not by an axle average.")

    perception = []
    if report.balance_drift:
        perception.append(f"Balance over the run: {report.balance_drift}")
    if report.tyre_state_at_end:
        perception.append(f"tyre state at the end: {report.tyre_state_at_end}")
    if perception:
        lines.append("- " + " · ".join(perception))
    if report.clean_air:
        lines.append(f"- Traffic and tow: {report.clean_air}")
    return lines


def _symptom_lines(report: DriverReport) -> list[str]:
    template = templates()["refinement"]
    lines = ([f"- {symptom}" for symptom in report.symptoms]
             or [template["symptomsNone"]])
    if report.biggest_limitation:
        lines.append(f"- **Biggest single limitation: "
                     f"{report.biggest_limitation}**")
    if report.costs_most_where:
        lines.append(f"- Costs me most: {report.costs_most_where}")
    return lines


def _payload_section(lines: Lines, context: ctx.PromptContext,
                     warnings: list[str]) -> None:
    template = templates()["refinement"]
    lines.blank()
    if context.payload_json:
        lines.add(template["dataHeading"], "", template["dataLead"], "")
        lines.add("```json", context.payload_json, "```", "")
        lines.add(template["dataDisagreement"], "")
        return
    if context.payload_refusal:
        warnings.append(f"the telemetry payload was refused, so it is not "
                        f"attached: {context.payload_refusal}")
    # No fenced block at all rather than an empty one — an empty code fence
    # reads as "here is the data" and there is none.
    lines.add(template["dataHeading"], "", template["dataAbsent"], "")


def _notes_section(lines: Lines, report: DriverReport) -> None:
    template = templates()["refinement"]
    lines.blank()
    lines.add(template["notesHeading"], "")
    lines.add(report.notes.strip() or template["notesNone"], "")


def _build_refinement(context: ctx.PromptContext, report: DriverReport,
                      today: str) -> Prompt:
    template = templates()["refinement"]
    warnings: list[str] = []
    lines = Lines()

    lines.add(template["title"], "")
    lines.add(f"**{context.car} @ {context.circuit_name}** · "
              f"{SESSION_NAMES.get(context.session_kind or 'practice')} · "
              f"{_session_date(context, today)}")
    lines.add("", template["standing"], "")

    lines.add(template["sessionHeading"])
    lines.add(_session_line(context))
    excluded = _exclusion_line(context)
    if excluded:
        lines.add(excluded)
    if report.conditions:
        lines.add(f"- Track conditions: {report.conditions}")
    if report.priority:
        lines.add(f"- Revision priority: **{report.priority}**")
    if report.unrepresentative:
        lines.add(f"- What made this session unrepresentative: "
                  f"{report.unrepresentative}")
    lines.add("")

    lines.add(template["eventContextHeading"])
    lines.add(*_event_context(context))
    lines.add("")

    _setup_section(lines, context)

    lines.blank()
    lines.add(template["symptomsHeading"])
    lines.add(*_symptom_lines(report))
    lines.add("")

    lines.add(template["paceHeading"])
    pace = _pace_lines(context, report)
    if pace:
        lines.add(*pace)
    else:
        lines.add("- No laps were recorded for this session.")
    lines.add("")

    _ranges_section(lines, context.ranges, brief=False)
    _payload_section(lines, context, warnings)
    _notes_section(lines, report)

    lines.add(template["requiredHeading"])
    lines.add(*template["required"])
    _return_contract(lines)
    lines.add("", template["hierarchy"], "", "---")
    lines.add(template["footer"].format(
        date=today, baseline=templates()["gt7Baseline"],
        promptVersion=PROMPT_VERSION))
    if not context.has_telemetry:
        warnings.append("no laps are recorded against this event, so the "
                        "prompt carries the driver report alone")
    return Prompt(REFINEMENT, lines.render(), warnings=warnings)


# ---------------------------------------------------------------- prompt C

def _build_outcome(context: ctx.PromptContext, report: DriverReport,
                   today: str) -> Prompt:
    template = templates()["outcome"]
    refinement = templates()["refinement"]
    warnings: list[str] = []
    lines = Lines()
    payload = context.payload or {}
    gearing = payload.get("gearing") or {}

    lines.add(template["title"], "")
    lines.add(f"**{context.car} @ {context.circuit_name}** · "
              f"{SESSION_NAMES['race']} · {_session_date(context, today)}")
    lines.add("")
    # **A post-mortem with no race in it can only be invented.** The body says
    # "nothing was recorded" honestly enough, but this is the one prompt whose
    # entire job is to explain what happened, and asking that of an empty
    # session is asking for a plausible answer rather than a true one. Said
    # out loud, at the top and in the warnings, so it is a decision to send it
    # rather than an accident.
    if not context.laps:
        lines.add(template["noRace"], "")
        warnings.append(
            "no race laps are recorded against this event, so there is "
            "nothing to write a post-mortem from - send the refinement "
            "prompt instead, or record the race first")
    if gearing.get("matchesSheet") is False:
        # Said once, at the top: it invalidates most of the diagnosis and must
        # not be buried in a JSON blob further down.
        lines.add(template["gearboxMismatch"], "")
        warnings.append("the fitted gearbox does not match the sheet")
    lines.add(template["standing"], "")

    lines.add(refinement["sessionHeading"])
    lines.add(_session_line(context))
    excluded = _exclusion_line(context)
    if excluded:
        lines.add(excluded)
    if report.conditions:
        lines.add(f"- Track conditions: {report.conditions}")
    if report.priority:
        lines.add(f"- Revision priority: **{report.priority}**")
    if report.unrepresentative:
        lines.add(f"- What made this event unrepresentative: "
                  f"{report.unrepresentative}")
    lines.add("")

    lines.add(refinement["eventContextHeading"])
    lines.add(*_event_context(context))
    lines.add("")

    _setup_section(lines, context)

    lines.blank()
    lines.add(template["happenedHeading"])
    lines.add(*_what_happened(context, report))
    lines.add("")

    lines.add(refinement["symptomsHeading"])
    lines.add(*_symptom_lines(report))
    lines.add("")

    lines.add(refinement["paceHeading"])
    pace = _pace_lines(context, report)
    lines.add(*(pace or ["- No laps were recorded for this race."]))
    lines.add("")

    _strategy_section(lines, context, warnings)
    _calls_section(lines, context)
    _wear_section(lines, context)
    _gearing_section(lines, gearing)

    _ranges_section(lines, context.ranges, brief=False)
    _payload_section(lines, context, warnings)
    _notes_section(lines, report)

    lines.add(template["requiredHeading"])
    lines.add(*template["required"])
    lines.add("", template["requiredEmphasis"])
    _return_contract(lines, extra=template["returnLeadExtra"])
    lines.add("", template["hierarchy"], "", "---")
    lines.add(template["footer"].format(
        date=today, baseline=templates()["gt7Baseline"],
        promptVersion=PROMPT_VERSION))
    return Prompt(OUTCOME, lines.render(), warnings=warnings)


def _what_happened(context: ctx.PromptContext,
                   report: DriverReport) -> list[str]:
    totals = context.session_totals or {}
    lines: list[str] = []

    if context.finish_position:
        lines.append(f"- Finished **P{context.finish_position}** — position "
                     f"off the telemetry stream on the last recorded lap")
    if report.result:
        lines.append(f"- Result, in my words: {report.result}")
    if totals.get("lapsRun"):
        lines.append(f"- Laps completed: **{totals['lapsRun']}**")
    if report.best_quali_lap:
        lines.append(f"- Best qualifying lap: **{report.best_quali_lap}** "
                     f"(entered by hand — the app records practice and race "
                     f"only, so no quali lap has been through the stream)")
    if totals.get("bestLapMs"):
        lines.append(f"- Best race lap: **{lap_time(totals['bestLapMs'])}**")
    if totals.get("medianLapMs"):
        lines.append(f"- Median race lap: "
                     f"**{lap_time(totals['medianLapMs'])}**")
    green, median = totals.get("greenLapRefMs"), totals.get("medianLapMs")
    if green and median:
        lines.append(f"- Median was **{median - green:+d} ms** on the "
                     f"green-tyre reference lap")
    stops = [lap.lap_num for lap in context.laps if lap.is_pit_lap]
    if stops:
        lines.append(f"- Pitted on lap{'s' if len(stops) > 1 else ''}: "
                     + ", ".join(str(lap) for lap in stops))
    return lines or ["- Nothing was recorded for this race."]


def _strategy_section(lines: Lines, context: ctx.PromptContext,
                      warnings: list[str]) -> None:
    template = templates()["outcome"]
    strategy = (context.payload or {}).get("strategy")
    lines.blank()
    lines.add(template["strategyHeading"], "")
    if not strategy:
        lines.add(template["strategyAbsent"], "")
        warnings.append("no approved strategy was found, so the prompt has no "
                        "plan to compare the race against")
        return

    plan = strategy.get("plan") or {}
    planned = []
    if plan.get("stops") is not None:
        planned.append(f"stops **{plan['stops']}**")
    if plan.get("stintLaps"):
        planned.append("stint laps **"
                       + " / ".join(str(n) for n in plan["stintLaps"]) + "**")
    if plan.get("compounds"):
        planned.append("compounds **"
                       + " / ".join(str(c) for c in plan["compounds"]) + "**")
    if plan.get("pitLap"):
        planned.append(f"pit lap **{plan['pitLap']}**")
    if planned:
        lines.add("- Planned: " + " · ".join(planned))

    actual_stops = [lap.lap_num for lap in context.laps if lap.is_pit_lap]
    lines.add(f"- Actually run: **{len(actual_stops)}** stop"
              f"{'' if len(actual_stops) == 1 else 's'}"
              + (f" on lap {', '.join(str(n) for n in actual_stops)}"
                 if actual_stops else ""))

    constraint = strategy.get("bindingConstraint")
    if constraint:
        lines.add(f"- Binding constraint, as the model determined it: "
                  f"**{constraint}**. Say whether the race bears that out — "
                  f"it decides whether the next setup chases durability or "
                  f"pace.")

    crossover = strategy.get("compoundCrossover")
    if crossover and crossover.get("verdict"):
        lines.add("", f"- Compound call: {crossover['verdict']}")
        # The comparison's own inputs, so the reasoning can be checked rather
        # than taken on trust - which is the whole point of exporting it.
        alternative = crossover.get("alternative") or {}
        lines.add(
            f"  Compared on total race time: "
            f"{'/'.join(crossover['winner']['compounds'])} against "
            f"{'/'.join(alternative.get('compounds') or [])}, "
            f"{alternative.get('lostBySeconds')} s apart, "
            f"break-even at {crossover.get('breakEvenSPerLap')} s/lap.")

    profiles = strategy.get("compoundProfiles") or []
    measured = [p for p in profiles if p.get("source") == "measured"]
    if profiles:
        lines.add("", "What each compound was costed at:", "")
        for profile in profiles:
            window = profile.get("tyreWindow") or {}
            temperature = ""
            if window.get("meanC") is not None:
                # **The measured half only.** The band and the window beside it
                # were never measured in GT7 - `analysis/tyre_window.py`
                # retracted that verdict and stamps every window
                # `windowMeasured: false` - and printing them as a completed
                # comparison put "0/6 laps in it" over a payload reading
                # `inWindow: null`. The reader concluded the compound never
                # reached its window, which is the exact false finding the
                # module was rewritten to stop emitting.
                temperature = (
                    f", ran at {window['meanC']} C over "
                    f"{window.get('lapsSampled')} laps")
                if window.get("windowMeasured") is not True:
                    temperature += (
                        " (no GT7 working range has been measured for this "
                        "compound, so there is nothing to judge that against)")
            lines.add(
                f"- **{profile['compound']}**: "
                f"{_number(profile.get('paceDeltaSPerLap'), 3)} s/lap against "
                f"the reference, wear "
                f"{'not measured' if profile.get('wearPerLap') is None else _number(profile['wearPerLap'], 4)}"
                f" per lap [{profile.get('source')}, "
                f"{profile.get('lapsMeasured', 0)} laps, "
                f"{profile.get('stintsMeasured', 0)} stints]"
                + temperature)
            # The qualification is its own line, because it does not amend the
            # figures above - it says how far they can be carried.
            if profile.get("windowQualification"):
                lines.add(f"  - {profile['windowQualification']}")
        if len(measured) < 2:
            lines.add(
                "", "Only one compound has a measured wear rate, so the "
                "harder-tyre comparison above is not yet evidence — the "
                "alternatives are planned on the reference's own number. "
                "Tell me whether that is worth the practice time to fix.")

    assumptions = strategy.get("assumptions") or {}
    if assumptions:
        lines.add("", "Every assumption behind that plan:", "")
        for key, value in assumptions.items():
            # The `...Source` entries are provenance for the key before them,
            # not assumptions in their own right.
            if key.endswith("Source"):
                continue
            if value is None:
                lines.add(f"- `{key}`: not known, and not invented")
                continue
            source = assumptions.get(f"{key}Source")
            line = f"- `{key}`: **{_number(value)}**"
            if source:
                line += f" [{source}]"
            lines.add(line)

    measured = _fuel_actual(context)
    planned_fuel = assumptions.get("fuelPerLapL")
    if measured is not None:
        line = f"- Fuel actually used: **{_number(measured, 2)} L/lap**"
        if planned_fuel:
            line += (f", against **{_number(planned_fuel, 2)} L/lap** "
                     f"planned")
        lines.add(line)

    if (context.payload or {}).get("wear", {}).get("modelConfidence") \
            == "converted":
        lines.add("", template["multiplierAssumed"])
    if strategy.get("outcome"):
        lines.add("", f"- Outcome as the app recorded it: "
                      f"{strategy['outcome']}")
    lines.add("")


def _fuel_actual(context: ctx.PromptContext) -> float | None:
    totals = context.session_totals or {}
    return totals.get("fuelUsedPerLapL")


def _calls_section(lines: Lines, context: ctx.PromptContext) -> None:
    """Every call, including the declined ones.

    A plan offered and refused is evidence about the model; dropping it would
    make the model look better than it was.
    """
    template = templates()["outcome"]
    calls = ((context.payload or {}).get("strategy") or {}).get("callsMade")
    lines.blank()
    lines.add(template["callsHeading"], "")
    if not calls:
        lines.add(template["callsAbsent"], "")
        return
    lines.add(template["callsLead"], "")
    lines.add(*template["callsTableHead"])
    for call in calls:
        # **`disposition` first, because `accepted` cannot hold what most
        # calls are.** A statement - "Green, green, green.", "Chequered flag."
        # - was never a question, and rendering it as "declined" told the
        # knowledge base the driver had refused the chequered flag. On the
        # Watkins race that was all fourteen calls, which left the only
        # feedback channel on the strategy engine saying nothing.
        accepted = call.get("accepted")
        outcome = call.get("disposition") or (
            "accepted" if accepted else
            "declined" if accepted is False else "not recorded")
        lines.add(f"| {call.get('lap', '—')} | {call.get('call', '—')} "
                  f"| {call.get('confidence', 'unstated')} | {outcome} |")
    lines.add("")


def _wear_section(lines: Lines, context: ctx.PromptContext) -> None:
    template = templates()["outcome"]
    wear = (context.payload or {}).get("wear")
    if not wear:
        return
    lines.blank()
    lines.add(template["wearHeading"], "", template["wearLead"], "")

    for reading in wear.get("byDriverGauge") or []:
        parts = [f"lap {reading.get('lap')}"]
        for corner in ("fl", "fr", "rl", "rr"):
            if reading.get(corner) is not None:
                parts.append(f"{corner.upper()} {reading[corner]:.0%}")
        if reading.get("worstCorner"):
            parts.append(f"worst {reading['worstCorner'].upper()}")
        lines.add(f"- Driver gauge: {', '.join(parts)} "
                  f"[{reading.get('source', 'driver-gauge')}]")

    by_corner = wear.get("byCorner") or {}
    if by_corner.get("worstCorner"):
        bias = []
        if by_corner.get("frontMinusRear") is not None:
            bias.append(f"front minus rear {by_corner['frontMinusRear']:+.0%}")
        if by_corner.get("leftMinusRight") is not None:
            bias.append(f"left minus right {by_corner['leftMinusRight']:+.0%}")
        lines.add(
            f"- Limiting corner: **{by_corner['worstCorner'].upper()}** at "
            f"{by_corner.get('worst', 0):.0%} consumed by lap "
            f"{by_corner.get('atLap')}"
            + (f" ({', '.join(bias)})" if bias else "")
            + ". GT7 allows no partial tyre change and no split compounds, so "
              "this is a setup and brake-balance finding, not a strategy one.")

    by_time = wear.get("byLapTime") or {}
    if by_time:
        lines.add(f"- Lap-time model: **{by_time.get('degradationMsPerLap')} "
                  f"ms/lap** in the **{by_time.get('phase')}** phase, against "
                  f"a reference lap of "
                  f"{lap_time(by_time.get('refLapMs')) or 'none'} "
                  f"[{by_time.get('source')}, confidence "
                  f"{by_time.get('confidence')}]")
    by_temp = wear.get("byTemp") or {}
    if by_temp:
        lines.add(f"- Temperature trend: **{by_temp.get('trendCPerLap')} "
                  f"°C/lap**, front-to-rear asymmetry "
                  f"**{by_temp.get('frontRearAsymmetryC')} °C** "
                  f"[{by_temp.get('source')}, confidence "
                  f"{by_temp.get('confidence')}]")
    if wear.get("modelledStintLaps") is not None:
        lines.add(f"- Modelled stint: **{wear['modelledStintLaps']} laps** — "
                  f"{wear.get('modelBasis', 'basis not stated')} "
                  f"[{wear.get('modelConfidence', 'unstated')}]")

    # Stated every time, not only when it is bad news. Multiplier linearity
    # is assumed and has never been demonstrated, so a stint number that was
    # scaled from another multiplier must never reach the knowledge base
    # looking measured.
    confidence = wear.get("modelConfidence")
    multiplier = (((context.payload or {}).get("meta") or {})
                  .get("multipliers") or {}).get("tyreWear")
    raced = f" (`{multiplier}`)" if multiplier else ""
    if confidence == "converted":
        lines.add(f"- **Wear was NOT measured at the multiplier raced{raced}.** "
                  f"It was scaled from a run at another one, and multiplier "
                  f"linearity is assumed, never demonstrated. Treat the stint "
                  f"length as unproven.")
    elif confidence == "measured":
        lines.add(f"- Wear was measured at the multiplier actually raced"
                  f"{raced}, from the gauge readings above.")
    elif not (wear.get("byDriverGauge") or []):
        lines.add("- No gauge reading was entered, so the stint length is not "
                  "modelled from measurement at all.")
    else:
        # A reading exists but something had to be assumed to turn it into a
        # rate - almost always that the set went on fresh at the run's first
        # lap, which GT7 broadcasts nothing to confirm. Saying "no reading was
        # entered" here would be false, and saying "measured" would be worse.
        lines.add(f"- Wear was read off the gauge at the multiplier raced"
                  f"{raced}, but the rate rests on an assumption: "
                  f"{wear.get('modelConfidenceBasis', 'see byRun')}. "
                  f"Treat the stint length as modelled, not measured.")
    lines.add("")


def _gearing_section(lines: Lines, gearing: dict) -> None:
    template = templates()["outcome"]
    if not gearing:
        return
    lines.blank()
    lines.add(template["gearingHeading"], "", template["gearingLead"], "")

    if gearing.get("fittedRatios"):
        lines.add("- Fitted ratios: "
                  + "  ".join(f"{r:g}" for r in gearing["fittedRatios"])
                  + f" [{gearing.get('ratioSource', 'unstated')}]")
    if gearing.get("fittedFinalGear") is not None:
        lines.add(f"- Fitted final gear: **{gearing['fittedFinalGear']:g}** "
                  f"[{gearing.get('finalGearSource', 'unstated')}]")
    if gearing.get("matchesSheet") is not None:
        lines.add(f"- Matches the sheet: "
                  f"**{'yes' if gearing['matchesSheet'] else 'no'}**")
    if gearing.get("gearboxChangedMidSession"):
        lines.add("- The gearbox changed mid-session, so any aggregate "
                  "spanning it covers two configurations.")
    if gearing.get("limiterRpm") is not None:
        lines.add(f"- Limiter: **{gearing['limiterRpm']} rpm** "
                  f"[{gearing.get('limiterRpmSource', 'unstated')}]")
    else:
        lines.add("- Limiter: not established — the rev-limiter flag never "
                  "fired, and the highest rpm observed is not the limiter.")
    if gearing.get("gearingConstantK") is not None:
        lines.add(f"- Gearing constant K: **{gearing['gearingConstantK']}** "
                  f"[{gearing.get('gearingConstantSource', 'unstated')}]")
    if gearing.get("samples") is not None:
        lines.add(f"- From **{gearing['samples']}** laps carrying frames.")
    lines.add("")


def _session_date(context: ctx.PromptContext, today: str) -> str:
    payload_meta = (context.payload or {}).get("meta") or {}
    return payload_meta.get("date") or today


# ------------------------------------------------------------------- entry

def build_prompt(context: ctx.PromptContext, report: DriverReport, *,
                 kind: str, today: str | None = None) -> Prompt:
    """Compose one prompt. Raises rather than emitting something misleading."""
    if kind not in KINDS:
        raise PromptRefused(f"{kind!r} is not one of {KINDS}")
    if context.event is None:
        raise PromptRefused(
            "there is no active event — a prompt has to be about something")
    if not context.car:
        raise PromptRefused(
            "the event has no car, so the brief would be about no car in "
            "particular")
    if not context.circuit_name:
        raise PromptRefused("the event has no circuit")

    today = today or datetime.date.today().isoformat()
    if kind == BRIEF:
        return _build_brief(context, report, today)
    if kind == REFINEMENT:
        return _build_refinement(context, report, today)
    return _build_outcome(context, report, today)
