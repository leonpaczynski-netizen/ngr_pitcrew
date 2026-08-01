"""Live Activation 1 — Practice Engineer message choreography (§7).

The engineer must say the RIGHT thing at the right moment and then be quiet — a pre-run brief,
a recording-started confirmation, occasional progress, specific invalid-lap feedback, a
"that's enough" notice, and a concise conclusion — never constant commentary.

This module is the deterministic choreographer: given the previous and current phase snapshots
(the authoritative recording state + valid/invalid-lap counters + the brief), it returns AT MOST
ONE message, only on a material transition, and ``None`` when nothing has changed. Anti-chatter is
structural — a message fires on a state edge, not on a clock tick. Pure, offline, never raises,
advisory only. The caller (bridge) owns the "speak once per new lap" timing on top of this.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from strategy.run_brief import lap_progress_note


class EngineerCue(str, Enum):
    NONE = "none"
    BRIEF = "brief"                        # pre-run objective + target
    RECORDING_CONFIRMED = "recording_confirmed"
    PROGRESS = "progress"                  # a valid lap was banked
    INVALID_LAP = "invalid_lap"            # an anomalous lap, with the reason
    SUFFICIENT = "sufficient"              # target valid-lap count reached
    CONCLUSION = "conclusion"              # run finished


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class EngineerMessage:
    cue: EngineerCue
    text: str
    priority: Priority = Priority.MEDIUM


@dataclass(frozen=True)
class EngineerPhase:
    """A snapshot of everything the engineer reasons over. Immutable + comparable."""
    run_state: str = "not_started"         # LiveRunState value
    valid_laps: int = 0
    invalid_laps: int = 0
    invalid_reason: str = ""               # reason of the MOST RECENT invalid lap
    target_min: int = 0
    target_laps: str = ""                  # the brief's target string, for the progress note
    objective: str = ""

    @property
    def is_complete(self) -> bool:
        return self.target_min > 0 and self.valid_laps >= self.target_min


_ACTIVE = frozenset({"starting", "recording", "paused", "disconnected"})
_TERMINAL = frozenset({"completed", "abandoned"})

#: invalid-lap reason → driver-facing phrase.
_REASON_PHRASE = {
    "pit_lap": "that was a pit lap",
    "out_lap": "that was an out lap",
    "incomplete_telemetry": "the telemetry dropped mid-lap",
    "off_track": "you ran wide",
    "cut": "a corner was cut",
}


def _reason_phrase(reason: str) -> str:
    r = (reason or "").strip().lower()
    return _REASON_PHRASE.get(r, "it didn't meet the clean-lap criteria")


def _brief_text(p: EngineerPhase) -> str:
    obj = (p.objective or "this run").strip()
    if p.target_min > 0:
        tgt = p.target_laps or str(p.target_min)
        return f"{obj}. Aim for {tgt} clean laps — I'll track them; drive it like you mean it."
    return f"{obj}. Bank some clean laps and note how the balance feels."


def _conclusion_text(p: EngineerPhase) -> str:
    if p.run_state == "abandoned":
        return "Run abandoned — nothing banked against the event."
    banked = p.valid_laps
    extra = (f" ({p.invalid_laps} didn't count)" if p.invalid_laps else "")
    obj = (p.objective or "the objective").strip()
    return (f"Run complete — {banked} clean lap{'' if banked == 1 else 's'}{extra}. "
            f"That's a read on {obj}. Bring it in and tell me how it felt.")


def choreograph_engineer(prev: EngineerPhase, curr: EngineerPhase) -> Optional[EngineerMessage]:
    """Return the single message the engineer should say on the prev→curr transition, or None.

    Exactly-once by construction: each cue fires only on its own edge, and highest-priority
    wins when several could fire at once (a completed run concludes; it does not also nag).
    """
    try:
        if prev == curr:
            return None

        # 1. Conclusion — the run just finished (terminal), whatever else changed.
        if curr.run_state in _TERMINAL and prev.run_state not in _TERMINAL:
            return EngineerMessage(EngineerCue.CONCLUSION, _conclusion_text(curr), Priority.HIGH)

        # 2. Pre-run brief — the run just opened (activation), before recording.
        if prev.run_state == "not_started" and curr.run_state == "starting":
            return EngineerMessage(EngineerCue.BRIEF, _brief_text(curr), Priority.HIGH)

        # 3. Recording confirmed — telemetry live, recording actually began.
        if prev.run_state in ("starting", "disconnected") and curr.run_state == "recording":
            verb = "Recording" if prev.run_state == "starting" else "Back on — recording"
            return EngineerMessage(EngineerCue.RECORDING_CONFIRMED,
                                   f"{verb}. Go when you're ready.", Priority.HIGH)

        # 4. Invalid lap — an anomaly was recorded (name the reason).
        if curr.invalid_laps > prev.invalid_laps:
            return EngineerMessage(
                EngineerCue.INVALID_LAP,
                f"That lap won't count — {_reason_phrase(curr.invalid_reason)}. "
                f"Shake it off, next clean lap.", Priority.MEDIUM)

        # 5. Sufficient — the target valid-lap count was just reached (once).
        if curr.is_complete and not prev.is_complete:
            banked = curr.valid_laps
            return EngineerMessage(
                EngineerCue.SUFFICIENT,
                f"That's enough for a read — {banked} clean lap{'' if banked == 1 else 's'}. "
                f"Bring it in when you're ready, or keep going if you want more.", Priority.HIGH)

        # 6. Progress — a valid lap was banked (still short of target). Materially useful: the
        #    count changed. The caller throttles to once-per-lap, so this never chatters per tick.
        if curr.valid_laps > prev.valid_laps and curr.run_state == "recording":
            return EngineerMessage(
                EngineerCue.PROGRESS,
                lap_progress_note(curr.target_laps, curr.valid_laps), Priority.LOW)

        return None
    except Exception:
        return None


class PracticeEngineerVoice:
    """Thin stateful wrapper: remembers the last phase and yields the next message (or None).
    The bridge calls ``observe(phase)`` each refresh; anti-chatter is inherited from the pure
    choreographer (no edge → no message)."""

    def __init__(self):
        self._prev = EngineerPhase()

    def observe(self, phase: EngineerPhase) -> Optional[EngineerMessage]:
        msg = choreograph_engineer(self._prev, phase)
        self._prev = phase
        return msg

    def reset(self) -> None:
        self._prev = EngineerPhase()
