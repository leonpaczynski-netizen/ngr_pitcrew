"""PTT interaction audit record (Program 3 Phase F / §19).

One immutable record per push-to-talk interaction, stamped with the exact context in
force plus the recognised intent, resolved action and response — so a wrong response
can be traced to speech recognition, intent resolution, the active context, stale
telemetry/strategy, the wrong engineer mode, or response construction.

Deliberately has NO raw-transcript field. The push-to-talk domain's invariant
(``strategy.push_to_talk``) is that raw transcripts never persist and never enter a
fingerprint; this record honours that — it captures the recognised *intent*
(action / class / confidence / ambiguous), never the words. Pure, frozen, never
raises.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PttInteractionRecord:
    # --- context in force at the moment of the interaction ---
    event_id: int = 0
    cycle_id: str = ""
    session_run_id: str = ""
    stint_id: str = ""
    lap_number: int = 0
    car_id: int = 0
    setup_snapshot_id: str = ""
    strategy_revision_id: str = ""
    session_type: str = ""

    # --- recognised intent (NEVER the raw transcript) ---
    recognised_action: str = ""
    command_class: str = ""
    intent_confidence: float = 0.0
    ambiguous: bool = False

    # --- resolution ---
    resolved_action: str = ""
    response: str = ""
    response_priority: str = ""
    fallback_state: str = ""

    created_at: str = ""

    def as_dict(self) -> dict:
        try:
            return asdict(self)
        except Exception:
            return {}


# The fields a record must NEVER carry — asserted by the tests and by any future
# call site, so the transcript invariant can't be reintroduced by accident.
FORBIDDEN_FIELDS = ("transcript", "raw_text", "utterance", "text", "words")
