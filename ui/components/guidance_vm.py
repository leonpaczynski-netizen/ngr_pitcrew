"""EngineerGuidanceVM — pure view-model for the Pit Crew Engineer guidance card.

Maps the canonical Event Command Centre view dict (produced by
``SessionDB.build_event_command_centre_view`` →
``strategy.event_command_centre.command_centre_to_dict``) into the fields the
guidance card renders. It invents nothing: the recommended action, objective,
evidence, confidence and warnings all come from deterministic domain state. When
evidence is missing it stays 'unknown' rather than fabricating certainty.

Pure/Qt-free/never-raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Tuple

from ui import ngr_theme as _t


def _norm(v) -> str:
    return "" if v is None else str(v).strip()


#: Setup-convergence states (what the command centre actually puts in setup_confidence)
#: mapped to the confidence ladder. Without this a lock-ready setup showed "No
#: evidence" on the guidance card because none of these words is "high"/"developing".
_CONVERGENCE_CONFIDENCE = {
    "locked": "high", "lock_ready": "high", "ready_for_confirmation": "high",
    "accepted": "high",
    "provisional": "medium", "improving": "medium", "stable_with_uncertainty": "medium",
    "exploring": "low", "diverging": "low", "insufficient_evidence": "low",
    "rollback_recommended": "low", "reopened": "low",
}


def _confidence_key(raw: str) -> str:
    """Map a free-text confidence/maturity/convergence string to a ladder key. Never raises."""
    s = (raw or "").strip().lower()
    if not s:
        return "unknown"
    if s in _CONVERGENCE_CONFIDENCE:
        return _CONVERGENCE_CONFIDENCE[s]
    if "high" in s or "strong" in s or "mature" in s:
        return "high"
    if "med" in s or "moderate" in s or "developing" in s:
        return "medium"
    if "low" in s or "weak" in s or "thin" in s or "early" in s:
        return "low"
    return "unknown"


def _tone_key(raw: str) -> str:
    s = (raw or "").strip().lower()
    return s if s in _t.STATUS_TONES else "info"


#: An evidence objective names a DOMAIN ("Build setup_base evidence"). The domain routes
#: it to the surface where that domain's work STARTS — the Garage for setup domains. Once a
#: setup is actually applied that becomes a dead end: the driver is standing in the Garage
#: being told to go to the Garage. Evidence for a setup domain is only ever produced by
#: DRIVING the setup and recording the run, so the presentation layer re-routes to Practice
#: and says so in words. The domain's payload is untouched (its shape is fingerprinted).
_EVIDENCE_RUN: dict[str, tuple[str, str]] = {
    "setup_base": ("baseline run", "Start a baseline run"),
    "setup_race": ("long race run", "Start a race run"),
    "setup_qualifying": ("qualifying simulation", "Start a qualifying run"),
    "working_window": ("setup experiment", "Start a setup experiment"),
    "driver_coaching": ("coaching run", "Start a coaching run"),
    "tyre_model": ("tyre test", "Start a tyre test"),
    "fuel_model": ("fuel test", "Start a fuel test"),
    "race_pace": ("long race run", "Start a race run"),
    "consistency": ("practice run", "Start a practice run"),
    "strategy": ("strategy validation run", "Start a strategy run"),
}


def evidence_domain_in(headline: str) -> str:
    """The evidence domain named by an objective headline, or "" if it isn't one."""
    h = (headline or "").strip().lower()
    if "evidence" not in h:
        return ""
    for domain in sorted(_EVIDENCE_RUN, key=len, reverse=True):
        if domain in h:
            return domain
    return ""


def _plain_attention(message: str) -> str:
    """Restate a domain attention line in the driver's terms.

    "Base Setup has no evidence yet" reads as "the app hasn't accepted my base setup",
    which is not what it means — it means no RUN has been recorded for that domain.
    """
    m = (message or "").strip()
    if m.endswith("has no evidence yet."):
        return m[: -len("has no evidence yet.")].strip() + " — no recorded runs yet."
    return m


def _evidence_summary(progress: Mapping) -> str:
    """One-line evidence summary from the progress payload (non-zero parts only)."""
    if not isinstance(progress, Mapping):
        return ""
    parts = []
    pairs = [
        ("practice_sessions", "practice session", "practice sessions"),
        ("valid_laps", "valid lap", "valid laps"),
        ("setup_experiments", "setup experiment", "setup experiments"),
        ("tyre_samples", "tyre sample", "tyre samples"),
        ("fuel_samples", "fuel sample", "fuel samples"),
        ("race_simulations", "race sim", "race sims"),
    ]
    for key, singular, plural in pairs:
        try:
            n = int(progress.get(key, 0) or 0)
        except (TypeError, ValueError):
            n = 0
        if n > 0:
            parts.append(f"{n} {singular if n == 1 else plural}")
    return " · ".join(parts)


@dataclass(frozen=True)
class EngineerGuidanceVM:
    message: str = ""                 # the engineer's explanatory line (rationale)
    objective: str = ""               # what we're doing now (imperative headline)
    tone: str = "info"                # semantic tone key
    primary_action_label: str = ""    # the single dominant CTA text
    primary_action_surface: str = ""  # nav destination the CTA routes to
    secondary_action_label: str = ""
    secondary_action_surface: str = ""
    evidence_summary: str = ""
    confidence_level: str = "unknown"
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    explanation: str = ""             # expandable detail
    read_aloud_text: str = ""
    active_setup: str = ""            # what is on the car right now (or "")

    @classmethod
    def empty(cls) -> "EngineerGuidanceVM":
        return cls(
            message="No active event yet.",
            objective="Create or select an NGR event to begin.",
            tone="info",
            primary_action_label="Go to Active Event",
            primary_action_surface="active_event",
        )

    @classmethod
    def from_command_centre(cls, view: Optional[Mapping], *,
                            active_setup_label: str = "",
                            active_setup_applied: bool = False) -> "EngineerGuidanceVM":
        """Build from the Event Command Centre view dict. Never raises.

        ``active_setup_*`` describe what is actually on the car. They change nothing the
        domain decided — they let the card acknowledge the driver's applied setup and
        route an evidence objective to the run that would produce the evidence, instead
        of back to the surface the driver is already standing on.
        """
        try:
            if not view or not isinstance(view, Mapping) or not view.get("ok", True):
                return cls.empty()
            na = view.get("next_action") or {}
            headline = _norm(na.get("headline"))
            detail = _norm(na.get("detail"))
            surface = _norm(na.get("target_surface"))
            tone = _tone_key(na.get("tone"))

            progress = view.get("progress") or {}
            evidence = _evidence_summary(progress)
            confidence = _confidence_key(_norm(progress.get("setup_confidence")))

            # Warnings come from attention items with a warn/danger tone.
            warnings = []
            for item in (view.get("attention") or []):
                if not isinstance(item, Mapping):
                    continue
                if _norm(item.get("tone")).lower() in ("warn", "danger"):
                    msg = _plain_attention(_norm(item.get("message")))
                    if msg:
                        warnings.append(msg)

            # A quiet secondary route: the first quick action that isn't the primary.
            secondary_label = secondary_surface = ""
            for qa in (view.get("quick_actions") or []):
                if not isinstance(qa, Mapping):
                    continue
                s = _norm(qa.get("target_surface"))
                if s and s != surface:
                    secondary_label = _norm(qa.get("label"))
                    secondary_surface = s
                    break

            objective = headline
            message = detail or headline
            explanation = detail if detail and detail != message else ""

            # An evidence objective is only ever satisfied by DRIVING and recording a run.
            # Say that plainly, and send the driver to the run card rather than back to the
            # surface the domain nominates for starting that domain's work.
            setup_label = _norm(active_setup_label)
            domain = evidence_domain_in(headline)
            primary_label, primary_surface = headline, surface
            if domain:
                run_name, cta = _EVIDENCE_RUN[domain]
                primary_label, primary_surface = cta, "practice"
                if setup_label and active_setup_applied:
                    message = (f"{setup_label} is on the car, but no {run_name} has been "
                               f"recorded for it yet. Drive one and press “End run & record” — "
                               f"that is what builds the evidence.")
                else:
                    message = (f"No {run_name} has been recorded yet. Apply a setup, drive a "
                               f"{run_name}, then record it — that is what builds the evidence.")
                explanation = detail or explanation

            return cls(
                message=message,
                objective=objective,
                tone=tone,
                primary_action_label=primary_label,
                primary_action_surface=primary_surface,
                active_setup=f"{setup_label}{' (applied)' if active_setup_applied else ''}"
                             if setup_label else "",
                secondary_action_label=secondary_label,
                secondary_action_surface=secondary_surface,
                evidence_summary=evidence,
                confidence_level=confidence,
                warnings=tuple(warnings),
                explanation=explanation,
                read_aloud_text=f"{objective}. {message}".strip(),
            )
        except Exception:
            return cls.empty()
