"""Deterministic review of a recorded practice run (UAT-4).

After recording a run the driver had nowhere to see what actually happened — no lap
times, no fuel per lap — and submitting feedback landed on an empty Outcome screen,
because nothing ever built an outcome from the run.

This module turns the lap rows the app already stores (``SessionDB.get_session_laps``)
into two things:

  * a **lap-by-lap review** with a clean-lap summary (best, average, consistency, fuel
    per lap, projected stint), and
  * a **run outcome** reconciling what the telemetry measured against what the driver
    said, versus the previous recorded run.

Pure, offline, deterministic; it judges nothing it cannot measure. With no previous
run to compare against, the verdict is INCONCLUSIVE and says so — it never dresses a
first run up as an improvement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import List, Mapping, Optional, Sequence, Tuple

#: A lap this far off the best is treated as compromised (traffic, off, cool-down) and
#: excluded from the clean-lap summary. Generous enough to keep honest slow laps.
CLEAN_LAP_TOLERANCE = 1.07

#: The FIRST lap is treated as an unflagged flying out lap when it is faster than this
#: fraction of the NEXT-FASTEST real lap. 0.97 = more than 3% quicker than every other
#: lap — a gap no consistent driver opens up within a single run, but exactly what a
#: rolling-start out lap (which covers less than a full lap) looks like.
FLYING_OUTLAP_FLOOR = 0.97

#: Below this many clean laps nothing can be said about consistency or pace with
#: any confidence — the outcome reports "gather more" rather than a verdict.
MIN_LAPS_FOR_VERDICT = 3


def _f(v, default=0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _i(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def format_lap_time(ms) -> str:
    """m:ss.mmm, or an em dash when there is no time."""
    n = _i(ms)
    if n <= 0:
        return "—"
    minutes, rem = divmod(n, 60000)
    seconds, millis = divmod(rem, 1000)
    return f"{minutes}:{seconds:02d}.{millis:03d}"


def format_delta(ms) -> str:
    n = _i(ms)
    if n == 0:
        return "—"
    return f"{'+' if n > 0 else '-'}{abs(n) / 1000:.3f}"


@dataclass(frozen=True)
class LapRow:
    lap: int
    time_ms: int
    delta_to_best_ms: int
    fuel_used: float
    compound: str
    clean: bool
    excluded_reason: str = ""
    lock_ups: int = 0
    wheelspin: int = 0

    @property
    def time_text(self) -> str:
        return format_lap_time(self.time_ms)

    @property
    def delta_text(self) -> str:
        return format_delta(self.delta_to_best_ms)

    @property
    def fuel_text(self) -> str:
        return f"{self.fuel_used:.2f} L" if self.fuel_used > 0 else "—"


@dataclass(frozen=True)
class RunReview:
    """Everything measured about one recorded run. Empty when there are no laps."""
    laps: Tuple[LapRow, ...] = field(default_factory=tuple)
    clean_laps: int = 0
    best_ms: int = 0
    average_clean_ms: int = 0
    consistency_ms: int = 0            # std-dev of clean laps
    fuel_per_lap: float = 0.0
    total_fuel: float = 0.0
    laps_of_fuel: float = 0.0          # projected from 100 L, 0 when unknown
    compounds: Tuple[str, ...] = field(default_factory=tuple)
    lock_ups: int = 0
    wheelspin: int = 0

    @property
    def has_laps(self) -> bool:
        return bool(self.laps)

    @property
    def summary_line(self) -> str:
        if not self.has_laps:
            return ""
        bits = [f"Best {format_lap_time(self.best_ms)}"]
        if self.average_clean_ms:
            bits.append(f"clean average {format_lap_time(self.average_clean_ms)}")
        if self.consistency_ms:
            bits.append(f"±{self.consistency_ms / 1000:.3f}s")
        if self.fuel_per_lap:
            bits.append(f"{self.fuel_per_lap:.2f} L/lap")
        if self.laps_of_fuel:
            bits.append(f"~{self.laps_of_fuel:.1f} laps per tank")
        return "   ·   ".join(bits)


def build_run_review(lap_rows: Sequence[Mapping]) -> RunReview:
    """Summarise a run from ``get_session_laps`` rows. Never raises."""
    try:
        return _build_run_review(lap_rows)
    except Exception:  # pragma: no cover - defensive
        return RunReview()


def _build_run_review(lap_rows: Sequence[Mapping]) -> RunReview:
    rows = [r for r in (lap_rows or ()) if isinstance(r, Mapping) and _i(r.get("lap_time_ms")) > 0]
    if not rows:
        return RunReview()

    ordered = sorted(rows, key=lambda x: _i(x.get("lap_num")))

    def _flagged_in_or_out(r: Mapping) -> bool:
        return bool(r.get("is_pit_lap")) or bool(r.get("is_out_lap"))

    # A rolling-start out lap covers less than a full lap, so it is anomalously FAST.
    # GT7's telemetry does not always flag it, and older recorded runs pre-date the
    # flag entirely — so a run whose only "best" was that short first lap kept
    # contaminating the advice (best lap 1:52 against honest 1:57s). The FIRST lap is
    # treated as an out lap when it is implausibly faster than the rest of the field —
    # a margin no consistent driver improves by within one run — even without a flag.
    first_id = _i(ordered[0].get("lap_num")) if ordered else None
    rest_times = [_i(r.get("lap_time_ms")) for r in ordered[1:]
                  if not _flagged_in_or_out(r) and _i(r.get("lap_time_ms")) > 0]
    # Judge the first lap against the NEXT-FASTEST real lap, not the average: an out lap
    # is quicker than EVERY honest lap, whereas a merely-good first lap is only a hair
    # under the next one. Using the field minimum keeps a single slow lap from dragging
    # the reference up and falsely condemning a normal first lap.
    flying_outlap_ceiling = (min(rest_times) * FLYING_OUTLAP_FLOOR) if len(rest_times) >= 2 else 0

    def _in_or_out(r: Mapping) -> bool:
        if _flagged_in_or_out(r):
            return True
        # Unflagged flying out lap: the first lap, quicker than the next-fastest by a
        # margin no consistent driver opens up within one run.
        return (flying_outlap_ceiling > 0
                and _i(r.get("lap_num")) == first_id
                and _i(r.get("lap_time_ms")) < flying_outlap_ceiling)

    # The reference pace can only come from laps that were actually RACED. An in/out
    # lap is fast or slow for reasons that have nothing to do with the car, so letting
    # one set "best" both reports a lap the driver never really drove as the result and
    # measures every honest lap against it. Fall back to the raw minimum only when the
    # whole run is in/out laps, so a one-lap run still shows something.
    raced = [_i(r.get("lap_time_ms")) for r in ordered if not _in_or_out(r)]
    reference = min(raced) if raced else min(_i(r.get("lap_time_ms")) for r in ordered)

    # Pass 1: classify. "Off the pace" is judged against the raced reference.
    classified: List[Tuple[Mapping, int, bool, str]] = []
    clean_times: List[int] = []
    for r in ordered:
        t = _i(r.get("lap_time_ms"))
        pit_or_out = _in_or_out(r)
        slow = (not pit_or_out) and t > reference * CLEAN_LAP_TOLERANCE
        reason = ("in/out lap" if pit_or_out
                  else ("off the pace" if slow else ""))
        clean = not (pit_or_out or slow)
        if clean:
            clean_times.append(t)
        classified.append((r, t, clean, reason))

    # The run's best is the best CLEAN lap; deltas are measured against it.
    best = min(clean_times) if clean_times else reference

    # Pass 2: build the rows now that the real best is known.
    laps: List[LapRow] = []
    fuels: List[float] = []
    compounds: List[str] = []
    lock_ups = wheelspin = 0

    for r, t, clean, reason in classified:
        fuel = _f(r.get("fuel_used"))
        comp = str(r.get("compound") or "").strip()
        lu, ws = _i(r.get("lock_up_count")), _i(r.get("wheelspin_count"))
        lock_ups += lu
        wheelspin += ws
        if clean and fuel > 0:
            fuels.append(fuel)
        if comp and comp not in compounds:
            compounds.append(comp)
        laps.append(LapRow(
            lap=_i(r.get("lap_num")), time_ms=t, delta_to_best_ms=t - best,
            fuel_used=fuel, compound=comp, clean=clean, excluded_reason=reason,
            lock_ups=lu, wheelspin=ws))

    fuel_per_lap = round(mean(fuels), 3) if fuels else 0.0
    return RunReview(
        laps=tuple(laps),
        clean_laps=len(clean_times),
        best_ms=best,
        average_clean_ms=int(round(mean(clean_times))) if clean_times else 0,
        consistency_ms=int(round(pstdev(clean_times))) if len(clean_times) > 1 else 0,
        fuel_per_lap=fuel_per_lap,
        total_fuel=round(sum(_f(r.get("fuel_used")) for r in rows), 2),
        # GT7's tank is always 100 units (see the fuel-units reference).
        laps_of_fuel=round(100.0 / fuel_per_lap, 1) if fuel_per_lap > 0 else 0.0,
        compounds=tuple(compounds),
        lock_ups=lock_ups, wheelspin=wheelspin)


# --------------------------------------------------------------------------- outcome
#: Driver verdict from the structured feedback form.
_DRIVER_VERDICT = {"better": "improved", "worse": "worse", "unchanged": "unchanged"}

#: A pace change smaller than this is noise, not a result.
MEANINGFUL_DELTA_MS = 100


@dataclass(frozen=True)
class RunOutcome:
    verdict: str = ""                  # improved|worse|unchanged|inconclusive
    summary: str = ""
    telemetry_findings: Tuple[str, ...] = field(default_factory=tuple)
    feedback_summary: str = ""
    agreements: Tuple[str, ...] = field(default_factory=tuple)
    contradictions: Tuple[str, ...] = field(default_factory=tuple)
    changed_vs_previous: Tuple[str, ...] = field(default_factory=tuple)
    confidence: str = "unknown"
    primary_action_label: str = ""
    primary_action_key: str = ""
    secondary_action_label: str = ""
    secondary_action_key: str = ""


def _feedback_verdict(feedback: Optional[Mapping]) -> str:
    fb = feedback if isinstance(feedback, Mapping) else {}
    return _DRIVER_VERDICT.get(str(fb.get("overall") or "").strip().lower(), "")


def _feedback_summary(feedback: Optional[Mapping]) -> str:
    """One line of what the driver actually reported (non-neutral answers only)."""
    fb = feedback if isinstance(feedback, Mapping) else {}
    skip = {"", "neutral", "none", "ok", "n/a"}
    bits = []
    for key, value in fb.items():
        if key in ("overall", "notes", "corners"):
            continue
        v = str(value or "").strip()
        if v.lower() not in skip:
            bits.append(f"{str(key).replace('_', ' ')}: {v}")
    notes = str(fb.get("notes") or "").strip()
    if notes:
        bits.append(notes)
    return "   ·   ".join(bits)


def build_run_outcome(
    review: RunReview,
    *,
    feedback: Optional[Mapping] = None,
    previous: Optional[RunReview] = None,
) -> RunOutcome:
    """Reconcile the measured run against the driver's feedback. Never raises."""
    try:
        return _build_run_outcome(review, feedback=feedback, previous=previous)
    except Exception:  # pragma: no cover - defensive
        return RunOutcome()


def _build_run_outcome(review, *, feedback, previous) -> RunOutcome:
    if not isinstance(review, RunReview) or not review.has_laps:
        return RunOutcome(
            verdict="inconclusive",
            summary="No laps were recorded for this run, so there is nothing to judge.",
            confidence="unknown",
            primary_action_label="Gather more data", primary_action_key="gather")

    findings = [f"Best lap {format_lap_time(review.best_ms)}",
                f"{review.clean_laps} clean lap{'s' if review.clean_laps != 1 else ''} "
                f"of {len(review.laps)}"]
    if review.consistency_ms:
        findings.append(f"Consistency ±{review.consistency_ms / 1000:.3f}s")
    if review.fuel_per_lap:
        findings.append(f"{review.fuel_per_lap:.2f} L/lap")
    if review.lock_ups:
        findings.append(f"{review.lock_ups} lock-up{'s' if review.lock_ups != 1 else ''}")
    if review.wheelspin:
        findings.append(f"{review.wheelspin} wheelspin event"
                        f"{'s' if review.wheelspin != 1 else ''}")

    driver = _feedback_verdict(feedback)
    fb_summary = _feedback_summary(feedback)

    # Telemetry verdict needs something to compare against.
    changed: List[str] = []
    measured = ""
    if isinstance(previous, RunReview) and previous.has_laps and previous.best_ms:
        delta = review.best_ms - previous.best_ms
        changed.append(f"Best lap {format_delta(delta)}s vs the previous run")
        if previous.average_clean_ms and review.average_clean_ms:
            changed.append("Clean average "
                           f"{format_delta(review.average_clean_ms - previous.average_clean_ms)}s")
        if previous.fuel_per_lap and review.fuel_per_lap:
            changed.append(f"Fuel {review.fuel_per_lap - previous.fuel_per_lap:+.2f} L/lap")
        if abs(delta) < MEANINGFUL_DELTA_MS:
            measured = "unchanged"
        else:
            measured = "improved" if delta < 0 else "worse"

    if review.clean_laps < MIN_LAPS_FOR_VERDICT:
        return RunOutcome(
            verdict="inconclusive",
            summary=(f"Only {review.clean_laps} clean lap"
                     f"{'s' if review.clean_laps != 1 else ''} — too few to judge the "
                     f"setup. Run at least {MIN_LAPS_FOR_VERDICT} representative laps."),
            telemetry_findings=tuple(findings), feedback_summary=fb_summary,
            changed_vs_previous=tuple(changed), confidence="low",
            primary_action_label="Gather more data", primary_action_key="gather",
            secondary_action_label="Build the next change", secondary_action_key="build_next")

    if not measured:
        return RunOutcome(
            verdict="inconclusive",
            summary=("This is the first recorded run for this setup, so there is nothing "
                     "to compare it against yet. Record another run to get a verdict."),
            telemetry_findings=tuple(findings), feedback_summary=fb_summary,
            confidence="low",
            primary_action_label="Gather more data", primary_action_key="gather",
            secondary_action_label="Build the next change", secondary_action_key="build_next")

    agreements: List[str] = []
    contradictions: List[str] = []
    if driver:
        line = f"telemetry says {measured}, you said {driver}"
        (agreements if driver == measured else contradictions).append(line)

    # A contradiction is never resolved by outvoting the driver — it lowers confidence
    # and asks for another run instead of promoting a result nobody agrees on.
    if contradictions:
        confidence = "low"
        action = ("Gather more data", "gather")
    elif agreements:
        confidence = "medium"
        action = (("Keep this change", "keep") if measured == "improved"
                  else ("Revert this change", "revert") if measured == "worse"
                  else ("Refine the change", "refine"))
    else:
        confidence = "low"
        action = (("Keep this change", "keep") if measured == "improved"
                  else ("Revert this change", "revert") if measured == "worse"
                  else ("Refine the change", "refine"))

    summaries = {
        "improved": f"Faster: best lap {format_delta(review.best_ms - previous.best_ms)}s.",
        "worse": f"Slower: best lap {format_delta(review.best_ms - previous.best_ms)}s.",
        "unchanged": "No meaningful pace change versus the previous run.",
    }
    return RunOutcome(
        verdict=measured, summary=summaries[measured],
        telemetry_findings=tuple(findings), feedback_summary=fb_summary,
        agreements=tuple(agreements), contradictions=tuple(contradictions),
        changed_vs_previous=tuple(changed), confidence=confidence,
        primary_action_label=action[0], primary_action_key=action[1],
        secondary_action_label="Gather more data", secondary_action_key="gather")


# --------------------------------------------------------------------------- coaching
#: A coaching run is about the DRIVER, not the setup. Its review reads the same lap data
#: as any run, but asks a different question: where is the driver leaving time, and is
#: the limit the car or the lap being driven? Built purely from the RunReview so no new
#: telemetry pipeline is needed.

@dataclass(frozen=True)
class CoachingReview:
    """Driver-focused read of a run: pace left on the table, consistency, mistakes."""
    headline: str = ""
    lines: Tuple[str, ...] = field(default_factory=tuple)
    limited_by: str = ""          # "the lap you are driving" | "the car" | ""

    @property
    def has_content(self) -> bool:
        return bool(self.headline or self.lines)


def build_coaching_review(review: Optional["RunReview"]) -> CoachingReview:
    """Coach a driver from a recorded run. Never raises."""
    try:
        return _build_coaching_review(review)
    except Exception:  # pragma: no cover - defensive
        return CoachingReview()


def _build_coaching_review(review: Optional["RunReview"]) -> CoachingReview:
    if not isinstance(review, RunReview) or not review.has_laps:
        return CoachingReview()
    if review.clean_laps < MIN_LAPS_FOR_VERDICT:
        return CoachingReview(
            headline="Not enough clean laps to coach yet — put in a few repeatable laps.")

    lines: List[str] = []
    gap_ms = max(0, review.average_clean_ms - review.best_ms)
    gap_s = gap_ms / 1000.0
    # How much the driver leaves per lap by not repeating their best.
    if gap_ms > 0:
        lines.append(
            f"Your best clean lap is {format_lap_time(review.best_ms)}, but your average "
            f"is {format_lap_time(review.average_clean_ms)} — you are leaving about "
            f"{gap_s:.1f}s a lap by not repeating your best.")
    else:
        lines.append(
            f"Your laps are right on your best of {format_lap_time(review.best_ms)} — "
            f"very little left in the driving.")

    # Consistency read.
    cons_s = review.consistency_ms / 1000.0
    if review.consistency_ms:
        band = ("tight — you repeat the lap well" if cons_s <= 0.3
                else "loose — the lap is not repeating" if cons_s >= 0.7
                else "workable, with room to tighten")
        lines.append(f"Consistency ±{cons_s:.3f}s: {band}.")

    # Mistakes.
    if review.lock_ups or review.wheelspin:
        bits = []
        if review.lock_ups:
            bits.append(f"{review.lock_ups} lock-up{'s' if review.lock_ups != 1 else ''}")
        if review.wheelspin:
            bits.append(f"{review.wheelspin} wheelspin event{'s' if review.wheelspin != 1 else ''}")
        lines.append(" and ".join(bits) + " — smoothing these out is free lap time.")
    else:
        lines.append("Clean run — no lock-ups or wheelspin flagged.")

    # The coaching verdict: is the driver or the car the limit?
    # A tight, repeatable run near its own best is car-limited; a loose or off-best run
    # has time in the driving.
    driver_limited = gap_s >= 0.5 or cons_s >= 0.7 or review.lock_ups or review.wheelspin
    limited_by = "the lap you are driving" if driver_limited else "the car"
    headline = ("There is time in your driving to find."
                if driver_limited else
                "You are getting the most out of this car — look to the setup for more.")
    return CoachingReview(headline=headline, lines=tuple(lines), limited_by=limited_by)
