"""Phase 7 — qualifying-discipline output surface (pure, Qt-free).

The qualifying camber/toe/diff bias already lives in setup_baseline's
_SESSION_BIAS_TABLE["qualifying"] (the UAT fix that stopped quali being race trim).
This module SURFACES that discipline honestly: what a qualifying tune is FOR
(one flying lap), what it buys (sharper turn-in, more rotation, more peak grip),
what it trades away (tyre life over a stint, stability, a more demanding car), and
a plain one-lap warning that it is not a race setup.

It describes only the deltas actually applied — a field not shifted for qualifying
produces no claim. It authors no setup values and applies nothing.
"""
from __future__ import annotations

from dataclasses import dataclass, field as _dc_field

# Per-field (benefit, cost) for the qualifying bias. Direction is implied by the
# qualifying table (all these fields move toward one-lap aggression).
_QUALI_FIELD_NOTES = {
    "camber_front": ("more front camber for peak cornering grip",
                     "the extra camber wears and overheats the front tyre over a stint"),
    "camber_rear": ("more rear camber for peak grip",
                    "tyre-life cost over a stint"),
    "toe_front": ("more front toe-out for sharper turn-in",
                  "can feel darty and scrubs a little speed on long runs"),
    "lsd_decel": ("a freer decel diff for more corner-entry rotation",
                  "less entry stability lap after lap"),
    "lsd_accel": ("a freer accel diff for more corner-exit rotation",
                  "less exit traction — easier to light up the rears when tyres go off"),
    "brake_bias": ("more front brake bias for turn-in bite",
                   "more front-locking risk if you overdrive the entry"),
    "aero_front": ("more front downforce for sharper turn-in",
                   "subject to the track's drag profile — costs a little top speed"),
    "ride_height_front": ("a lower front platform for more aero",
                          "bottoming risk over bumps and kerbs"),
    "ride_height_rear": ("a lower rear platform for more aero",
                         "bottoming risk over bumps and kerbs"),
}

_ONE_LAP_WARNING = (
    "This is a qualifying tune — built for a single flying lap on low fuel and "
    "fresh tyres. Do not race it: the aggressive camber and freer diff trade away "
    "tyre durability and stability over a stint. Use your race setup for the race."
)
_OBJECTIVE = ("Outright one-lap pace — extract the peak this lap, not the stint "
              "average.")


@dataclass(frozen=True)
class QualifyingBrief:
    is_qualifying: bool
    objective: str
    strengths: list = _dc_field(default_factory=list)
    compromises: list = _dc_field(default_factory=list)
    one_lap_warning: str = ""

    def as_note(self) -> str:
        if not self.is_qualifying:
            return ""
        parts = [f"Qualifying discipline — {self.objective}"]
        if self.strengths:
            parts.append("It buys " + "; ".join(self.strengths) + ".")
        if self.compromises:
            parts.append("It trades away " + "; ".join(self.compromises) + ".")
        parts.append(self.one_lap_warning)
        return " ".join(parts)


def build_qualifying_brief(session_category: str,
                           applied_deltas: "dict | None" = None) -> QualifyingBrief:
    """Return a QualifyingBrief when the session is qualifying, else an empty one.

    ``session_category`` is the normalised bias key (e.g. "qualifying") or a raw
    purpose/session string containing "qual". ``applied_deltas`` is the field→delta
    map actually applied for qualifying; only those fields generate claims."""
    cat = str(session_category or "").lower()
    if "qual" not in cat:
        return QualifyingBrief(False, "", [], [], "")

    strengths, compromises = [], []
    for field, delta in (applied_deltas or {}).items():
        try:
            if float(delta) == 0:
                continue
        except (TypeError, ValueError):
            continue
        note = _QUALI_FIELD_NOTES.get(field)
        if note:
            strengths.append(note[0])
            compromises.append(note[1])

    # Always carry the overarching stint cost, even with no per-field detail.
    if "tyre durability over a stint" not in compromises:
        compromises.append("consistency and tyre durability over a full stint")

    return QualifyingBrief(
        is_qualifying=True, objective=_OBJECTIVE,
        strengths=strengths, compromises=compromises,
        one_lap_warning=_ONE_LAP_WARNING,
    )


def qualifying_brief_to_json(brief: QualifyingBrief) -> dict:
    return {
        "is_qualifying": brief.is_qualifying,
        "objective": brief.objective,
        "strengths": list(brief.strengths),
        "compromises": list(brief.compromises),
        "one_lap_warning": brief.one_lap_warning,
    }
