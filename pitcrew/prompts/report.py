"""What the driver supplies — and only what the app cannot know.

Every field here is a judgement or an observation. Nothing in it is derivable
from the store or the telemetry stream, and each one that looks as though it
ought to be says why it is not.

Empty is empty: a blank field is omitted from the prompt rather than filled
with a placeholder, a zero, or a cheerful default.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DriverReport:
    """The perception half of a prompt."""

    # --- what the car did. The controlled vocabulary is app data; see
    # catalogs.symptom_groups(). Telemetry can corroborate a symptom but it
    # cannot report one.
    symptoms: tuple[str, ...] = ()
    biggest_limitation: str = ""
    costs_most_where: str = ""

    # --- how it changed over the run. Both are perceptions of balance, and
    # the app has no balance channel: GT7 sends no slip angle and no yaw
    # target, so "migrated to understeer" is the driver's to say.
    balance_drift: str = ""
    tyre_state_at_end: str = ""

    # --- what to do with the revision. The event's own priority is declared
    # on the Event screen; this is the priority for THIS revision, which can
    # differ after a bad session.
    priority: str = ""

    # --- what made the numbers mean less than they look.
    conditions: str = ""
    unrepresentative: str = ""

    # GT7's feed carries no proximity, no closing speed and no opponent
    # positions, so a tow cannot be detected and a clean-air lap cannot be
    # told from one in traffic. This is the only place that fact can enter.
    clean_air: str = ""

    # --- race only.
    # The app records practice and race sessions. It has no qualifying
    # session kind, so a quali lap has never been through the stream.
    best_quali_lap: str = ""
    # Finishing position comes off the stream; this is the rest of the story
    # -- who was ahead, what happened at the start, whether it was a fair run.
    result: str = ""

    notes: str = ""

    # Set by the screen so a report can be told from a blank one without
    # inspecting every field.
    session_kind: str = "practice"

    def stated(self) -> dict[str, str]:
        """Only the fields actually filled in."""
        return {name: value.strip()
                for name, value in vars(self).items()
                if isinstance(value, str) and value.strip()}

    def is_empty(self) -> bool:
        return not self.symptoms and not self.stated().keys() - {"session_kind"}
