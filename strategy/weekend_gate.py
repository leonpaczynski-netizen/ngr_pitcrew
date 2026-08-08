"""Race-weekend transition gate (pure, Qt-free) — UAT 2026-08-07 defects C1/C4/C6/C7/C11.

The UAT symptom was "the app ran one practice session and went straight to qualifying,
without working through the tyres or settling the setup". The cause is that no transition
in the weekend was gated by anything. ``_on_begin_qualifying`` contained zero validation;
the only defence was a disabled button whose readiness mapping treated *developing*,
*adequate*, *strong* and *unknown* alike as non-blocking, so only the literal string
"missing" stopped anything. Per-compound tyre coverage was computed correctly and
consumed by a progress label. No "the driver is comfortable" gate existed anywhere.

**Why this is a new module rather than a promotion of an existing one.** The register
proposed promoting ``RaceWeekendPhase`` to the authoritative sequencer. That module is a
ceremonial weekend-experience assembler (arrival, briefings, scrutineering); it is not a
gate engine. The three modules that ARE gate-shaped — ``discipline_workflow``,
``preparation_transitions`` and ``readiness_grade`` — each state in their own docstrings
that they report and never gate autonomously ("viewing or refreshing must NOT advance the
cycle"). That is a deliberate doctrine, not an oversight, and rewriting them into
enforcers would break the guarantee that recomputing a view changes nothing.

So this module keeps the doctrine and fills the actual hole: it COMPOSES what the
reporters already compute into one verdict for one transition, and the action handler is
what refuses. Purity is preserved on both sides — the verdict is a pure function of its
inputs, and enforcement lives where the state change happens.

**It does not forbid driving.** The app is advisory: a driver who wants to qualify on
thin evidence may, but only through an explicit acknowledgement that NAMES what is being
skipped, and the skip is recorded so the resulting laps are never mistaken for a properly
prepared session. A Yes/No dialog that lists nothing is not consent.

Pure: no Qt, no DB, no network, no AI, no wall-clock, no randomness. Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field
from enum import Enum
from typing import Optional, Sequence


class WeekendTransition(str, Enum):
    """The transitions that must be earned rather than merely clicked."""
    BEGIN_QUALIFYING = "begin_qualifying"
    START_RACE = "start_race"


#: Readiness levels that genuinely satisfy a domain. UAT 2026-08-07 defect C4 — the
#: readiness mapping blocked only on the literal string "missing", so "developing" (one
#: sample) and "unknown" (no idea) both read as good enough to go qualifying.
SATISFIED_LEVELS = frozenset({"adequate", "strong", "ready", "complete", "locked", "done"})

#: Levels that are explicitly not enough yet. "unknown" is here on purpose: not knowing
#: is not the same as being ready, and treating it as passable is how an unmeasured
#: domain waved a driver through.
INSUFFICIENT_LEVELS = frozenset({"missing", "none", "developing", "emerging",
                                 "insufficient", "unknown", ""})


@dataclass(frozen=True)
class GateBlocker:
    """One reason a transition has not been earned."""
    key: str
    message: str          # what is missing, in the driver's words
    remedy: str = ""      # the specific next action that clears it

    def as_json(self) -> dict:
        return {"key": self.key, "message": self.message, "remedy": self.remedy}

    def sentence(self) -> str:
        return f"{self.message}{(' — ' + self.remedy) if self.remedy else ''}"


@dataclass(frozen=True)
class WeekendGateVerdict:
    """Whether a transition is earned, and exactly what is missing if not."""
    transition: WeekendTransition
    blockers: tuple = _dc_field(default_factory=tuple)
    warnings: tuple = _dc_field(default_factory=tuple)

    @property
    def allowed(self) -> bool:
        return not self.blockers

    @property
    def headline(self) -> str:
        if self.allowed:
            return "Everything this transition needs is in place."
        n = len(self.blockers)
        return (f"{n} thing{'s' if n != 1 else ''} still missing before "
                f"{self.transition.value.replace('_', ' ')}.")

    def confirmation_prompt(self) -> str:
        """What an override must make the driver read.

        Deliberately enumerates every blocker. The Start Race check was documented as
        "never hard-stop" and proceeded on a bare Yes/No — a dialog that names nothing
        is not informed consent, it is a formality.
        """
        if self.allowed:
            return ""
        lines = [f"  • {b.sentence()}" for b in self.blockers]
        return ("Going ahead without:\n" + "\n".join(lines)
                + "\n\nThe laps you record will be marked as run on incomplete "
                  "preparation, so they are never mistaken for a properly prepared "
                  "session. Continue anyway?")

    def as_json(self) -> dict:
        return {"transition": self.transition.value, "allowed": self.allowed,
                "headline": self.headline,
                "blockers": [b.as_json() for b in self.blockers],
                "warnings": list(self.warnings)}


def _level_of(entry) -> "tuple[str, str, str]":
    """(name, level, note) from a readiness row of any supported shape."""
    try:
        if isinstance(entry, dict):
            return (str(entry.get("name") or ""), str(entry.get("level") or ""),
                    str(entry.get("note") or ""))
        seq = list(entry) + ["", "", ""]
        return (str(seq[0] or ""), str(seq[1] or ""), str(seq[2] or ""))
    except Exception:
        return ("", "", "")


def _is_satisfied(level: str) -> bool:
    lvl = str(level or "").strip().lower()
    if lvl in INSUFFICIENT_LEVELS:
        return False
    return lvl in SATISFIED_LEVELS


def evaluate_weekend_transition(
    transition: WeekendTransition,
    *,
    readiness: Optional[Sequence] = None,
    required_compounds: Optional[Sequence] = None,
    sampled_compounds: Optional[Sequence] = None,
    setup_applied: bool = False,
    setup_label: str = "",
    driver_comfortable: Optional[bool] = None,
    convergence_state: str = "",
    clean_lap_total: int = 0,
    min_clean_laps: int = 0,
) -> WeekendGateVerdict:
    """Decide whether one weekend transition has been earned. Never raises."""
    blockers: list = []
    warnings: list = []

    try:
        # --- the setup that will be driven must actually be on the car ------------
        if not setup_applied:
            blockers.append(GateBlocker(
                "setup_not_applied",
                "The setup for this session has not been confirmed as entered in GT7",
                "build it in the Garage, then press “I've entered this in GT7”"))

        # --- evidence domains (C4) -----------------------------------------------
        for entry in (readiness or ()):
            name, level, note = _level_of(entry)
            if not name:
                continue
            if not _is_satisfied(level):
                lvl = str(level or "").strip().lower() or "unknown"
                blockers.append(GateBlocker(
                    f"readiness:{name}",
                    f"{name.replace('_', ' ').capitalize()} is {lvl}",
                    (note or "run the practice this area asks for")))

        # --- per-compound tyre coverage (C6) -------------------------------------
        # This was computed correctly and consumed by a progress label. It also
        # disabled itself entirely when the event listed no compounds — "no
        # restriction" — which is backwards: not knowing which tyres are allowed is a
        # reason to ask, not a reason to skip the check.
        req = [str(c).strip().upper() for c in (required_compounds or ()) if str(c).strip()]
        samp = {str(c).strip().upper() for c in (sampled_compounds or ()) if str(c).strip()}
        if req:
            missing = [c for c in dict.fromkeys(req) if c not in samp]
            if missing:
                blockers.append(GateBlocker(
                    "tyre_coverage",
                    f"No recorded run on {', '.join(missing)}",
                    "run a stint on each compound the event allows"))
        elif not samp:
            warnings.append(
                "The event lists no allowed compounds, so tyre coverage could not be "
                "checked — confirm which tyres this event permits.")

        # --- the driver's own verdict (C7) ---------------------------------------
        # No "the driver is comfortable with the setup" gate existed anywhere in the
        # app. A setup the engineer is happy with and the driver is not is not ready.
        if driver_comfortable is None:
            blockers.append(GateBlocker(
                "driver_comfort",
                "You have not said whether you are comfortable with this setup",
                "confirm it in the Garage after a practice run"))
        elif driver_comfortable is False:
            blockers.append(GateBlocker(
                "driver_comfort",
                "You said you are NOT comfortable with this setup",
                "note what is wrong in Review and analyse again"))

        # --- a minimum of real laps ----------------------------------------------
        if min_clean_laps > 0 and clean_lap_total < min_clean_laps:
            blockers.append(GateBlocker(
                "clean_laps",
                f"Only {clean_lap_total} clean lap(s) recorded on this setup "
                f"(needs {min_clean_laps})",
                "run more clean laps before committing to it"))

        # --- race-specific: the setup should have settled -------------------------
        if transition is WeekendTransition.START_RACE:
            state = str(convergence_state or "").strip().lower()
            if state and state not in ("converged", "locked", "final"):
                warnings.append(
                    f"The setup has not converged (state: {state}) — the race will run "
                    f"on a setup still being developed.")
    except Exception:
        # A gate that crashes must not silently become an open door.
        return WeekendGateVerdict(
            transition=transition,
            blockers=(GateBlocker(
                "gate_error",
                "The readiness check could not be completed",
                "this is a fault — treat the session as unprepared"),),
            warnings=tuple(warnings))

    return WeekendGateVerdict(transition=transition, blockers=tuple(blockers),
                              warnings=tuple(warnings))
