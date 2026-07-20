"""Prompt Timing & Message-Duration Budget (Program 2, Phase 46).

Deterministic estimation of a prompt's spoken duration and whether it fits safely inside the available
delivery window - used BEFORE voice exists to reject prompts that cannot fit (e.g. a detailed
explanation during a short straight). Timing is based on word count + a configured speaking-rate band +
the prompt class; it never reads wall-clock (available time is supplied).

Purity: Qt-free, DB-free, UI-free, network-free, AI-free; no random, no wall-clock; deterministic;
never raises.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Optional

PROMPT_TIMING_VERSION = "prompt_timing_v1"

# configured speaking-rate band (words per minute). Deterministic; conservative default.
SPEAKING_RATE_WPM = 150.0
_WORDS_PER_SECOND = SPEAKING_RATE_WPM / 60.0

# per prompt-priority maximum spoken duration (seconds) a routine delivery may occupy.
_MAX_DURATION = {
    1: 3.0,   # stop-critical: immediate + concise
    2: 4.0,   # context/setup mismatch
    3: 4.0,   # run-plan stop condition
    4: 4.0,   # measurement-lap instruction
    5: 2.5,   # target-corner coaching cue: very short
    6: 4.0,   # evidence collection
    7: 5.0,   # informational progress
    8: 6.0,   # strategy awareness (usually visual/pit)
}


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _fp(payload) -> str:
    return (f"{PROMPT_TIMING_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        default=str).encode()).hexdigest()[:24])


class TimingVerdict(str, Enum):
    FITS = "fits"
    TOO_LONG_FOR_WINDOW = "too_long_for_window"
    TOO_LONG_FOR_CLASS = "too_long_for_class"
    IMMEDIATE = "immediate"        # stop-critical: deliver now regardless of window


def estimate_spoken_seconds(message: str) -> float:
    """Deterministic estimated spoken duration (seconds) from word count + the speaking-rate band."""
    words = len([w for w in _norm(message).split() if w])
    if words == 0:
        return 0.0
    return round(words / _WORDS_PER_SECOND, 3)


@dataclass(frozen=True)
class PromptTimingAssessment:
    verdict: str
    estimated_seconds: float
    available_seconds: float
    class_max_seconds: float
    fits: bool
    reason: str
    content_fingerprint: str

    def to_dict(self) -> dict:
        return {"verdict": self.verdict, "estimated_seconds": self.estimated_seconds,
                "available_seconds": self.available_seconds, "class_max_seconds": self.class_max_seconds,
                "fits": self.fits, "reason": self.reason,
                "content_fingerprint": self.content_fingerprint}


def assess_prompt_timing(prompt: Optional[Mapping], available_seconds: float) -> PromptTimingAssessment:
    """Assess whether ``prompt`` can be spoken within ``available_seconds`` before the next high-workload
    segment. Stop-critical prompts are IMMEDIATE (delivered now, still bounded by the class max).
    Deterministic; never raises."""
    try:
        p = prompt if isinstance(prompt, Mapping) else {}
        priority = int(p.get("priority") or 7)
        cls = _norm(p.get("prompt_class"))
        est = estimate_spoken_seconds(p.get("message"))
        class_max = float(_MAX_DURATION.get(priority, 5.0))
        avail = float(available_seconds if available_seconds is not None else 0.0)

        if cls == "stop_critical":
            # immediate; only rejected if it exceeds the (generous) stop-critical class cap.
            if est > class_max:
                verdict, fits, reason = (TimingVerdict.TOO_LONG_FOR_CLASS, False,
                                         "stop-critical message too long - shorten it.")
            else:
                verdict, fits, reason = (TimingVerdict.IMMEDIATE, True,
                                         "stop-critical: deliver immediately and concisely.")
        elif est > class_max:
            verdict, fits, reason = (TimingVerdict.TOO_LONG_FOR_CLASS, False,
                                     f"estimated {est:.1f}s exceeds the {class_max:.1f}s budget for this "
                                     f"prompt class - defer detail to the pits/post-session.")
        elif est > avail:
            verdict, fits, reason = (TimingVerdict.TOO_LONG_FOR_WINDOW, False,
                                     f"estimated {est:.1f}s does not fit the {avail:.1f}s window before "
                                     f"the next high-workload segment.")
        else:
            verdict, fits, reason = (TimingVerdict.FITS, True,
                                     f"estimated {est:.1f}s fits within {avail:.1f}s.")
        return PromptTimingAssessment(
            verdict=verdict.value, estimated_seconds=est, available_seconds=round(avail, 3),
            class_max_seconds=class_max, fits=fits, reason=reason,
            content_fingerprint=_fp({"prio": priority, "cls": cls, "est": est, "avail": round(avail, 1),
                                     "verdict": verdict.value}))
    except Exception:  # pragma: no cover - defensive
        return PromptTimingAssessment(verdict=TimingVerdict.TOO_LONG_FOR_WINDOW.value,
                                      estimated_seconds=0.0, available_seconds=0.0, class_max_seconds=0.0,
                                      fits=False, reason="unavailable.", content_fingerprint=_fp({"e": 1}))


def prompt_timing_versions() -> dict:
    return {"prompt_timing": PROMPT_TIMING_VERSION, "speaking_rate_wpm": SPEAKING_RATE_WPM}
