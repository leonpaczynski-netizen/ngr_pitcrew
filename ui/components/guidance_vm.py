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


def _confidence_key(raw: str) -> str:
    """Map a free-text confidence/maturity string to a ladder key. Never raises."""
    s = (raw or "").strip().lower()
    if not s:
        return "unknown"
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
    def from_command_centre(cls, view: Optional[Mapping]) -> "EngineerGuidanceVM":
        """Build from the Event Command Centre view dict. Never raises."""
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
                    msg = _norm(item.get("message"))
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

            return cls(
                message=message,
                objective=objective,
                tone=tone,
                primary_action_label=headline,
                primary_action_surface=surface,
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
