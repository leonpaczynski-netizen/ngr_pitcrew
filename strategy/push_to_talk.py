"""Push-to-Talk Driver Interaction — pure domain (Program 2, Phase 64).

WHY IT EXISTS
  A PSVR2 driver must be able to talk to the race engineer without removing the headset or looking at the
  PC. This module is the deterministic DOMAIN for that: the PTT binding + lifecycle state, a deterministic
  offline COMMAND GRAMMAR (not natural-language understanding), the four command classes, driver-report
  labelling, engineering-feedback DRAFTS, and the read-back / confirmation workflow.

SAFETY DOCTRINE
  Speech is an interface to canonical authorities, never an engineering agent. A spoken utterance:
    • may execute a SAFE OPERATIONAL command immediately (acknowledge/repeat/mute/status/…) — none of
      which alter engineering knowledge;
    • may REQUEST a strategy assessment — which never forces a strategy change;
    • may be a DRIVER REPORT — always labelled driver-reported/unverified until read-back-confirmed or
      telemetry-corroborated; a spoken report never becomes exact telemetry evidence;
    • may be ENGINEERING FEEDBACK — which becomes a DRAFT and never enters canonical learning until
      confirmed through the existing outcome/feedback workflow.
  Ambiguous / low-confidence recognition can never trigger a strategy or evidence change. Raw transcripts
  never enter engineering fingerprints. Pure: no AI, no network, no DB, no Qt, no wall clock; never raises.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

PUSH_TO_TALK_VERSION = "push_to_talk_v1"

# Recognition below this confidence is treated as AMBIGUOUS — it can never trigger a strategy/evidence
# change; the engineer asks the driver to repeat.
_MIN_CONFIDENCE = 0.55


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _fp(payload) -> str:
    return (f"{PUSH_TO_TALK_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


# --------------------------------------------------------------------------- #
# PTT binding + lifecycle
# --------------------------------------------------------------------------- #
class PttInputKind(str, Enum):
    KEYBOARD = "keyboard"
    CONTROLLER_BUTTON = "controller_button"
    WHEEL_BUTTON = "wheel_button"
    UNSET = "unset"


class PttActivationMode(str, Enum):
    PRESS_AND_HOLD = "press_and_hold"   # default: listen only while held
    TOGGLE = "toggle"                   # only when explicitly configured


@dataclass(frozen=True)
class PushToTalkBinding:
    """A hardware-neutral PTT binding. ``input_code`` is operational configuration (excluded from every
    engineering fingerprint). The default binding is UNSET — the mic is not listening by default."""
    kind: PttInputKind = PttInputKind.UNSET
    input_code: str = ""               # e.g. "F13", "js0_btn7" — operational config, not evidence
    activation: PttActivationMode = PttActivationMode.PRESS_AND_HOLD
    label: str = ""

    @property
    def is_bound(self) -> bool:
        return self.kind != PttInputKind.UNSET and bool(self.input_code)

    def to_config(self) -> dict:
        return {"kind": self.kind.value, "input_code": self.input_code,
                "activation": self.activation.value, "label": self.label}

    @classmethod
    def from_config(cls, cfg: Optional[Mapping]) -> "PushToTalkBinding":
        c = cfg if isinstance(cfg, Mapping) else {}
        try:
            kind = PttInputKind(_lc(c.get("kind")) or "unset")
        except ValueError:
            kind = PttInputKind.UNSET
        try:
            act = PttActivationMode(_lc(c.get("activation")) or "press_and_hold")
        except ValueError:
            act = PttActivationMode.PRESS_AND_HOLD
        return cls(kind=kind, input_code=_norm(c.get("input_code")), activation=act,
                   label=_norm(c.get("label")))


class PushToTalkState(str, Enum):
    IDLE = "idle"                       # not listening (default)
    LISTENING = "listening"             # PTT held / toggled on — capturing
    RECOGNISING = "recognising"         # processing the captured utterance
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # read-back issued, awaiting confirm/cancel
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    UNAVAILABLE = "unavailable"         # no input device / recogniser


class PttOperationalReadiness(str, Enum):
    UNBOUND = "unbound"                 # no PTT binding configured
    NO_RECOGNISER = "no_recogniser"     # bound but no offline recogniser available
    READY = "ready"                     # bound + recogniser available


def assess_ptt_readiness(binding: PushToTalkBinding, *, recogniser_available: bool) -> PttOperationalReadiness:
    if not binding.is_bound:
        return PttOperationalReadiness.UNBOUND
    if not recogniser_available:
        return PttOperationalReadiness.NO_RECOGNISER
    return PttOperationalReadiness.READY


# --------------------------------------------------------------------------- #
# Command classes + the deterministic grammar
# --------------------------------------------------------------------------- #
class DriverCommandClass(str, Enum):
    SAFE_OPERATIONAL = "safe_operational"     # execute immediately; never alters engineering knowledge
    STRATEGY_REQUEST = "strategy_request"     # request an assessment; never forces a change
    DRIVER_REPORT = "driver_report"           # labelled driver-reported/unverified
    ENGINEERING_FEEDBACK = "engineering_feedback"  # a draft; not canonical until confirmed
    UNRECOGNISED = "unrecognised"             # not understood / ambiguous


class DriverReportLabel(str, Enum):
    DRIVER_REPORTED = "driver_reported"
    UNVERIFIED = "unverified"
    CONFIRMED_BY_READBACK = "confirmed_by_readback"
    CORROBORATED_BY_TELEMETRY = "corroborated_by_telemetry"
    CONFLICTING_WITH_TELEMETRY = "conflicting_with_telemetry"
    UNAVAILABLE_FOR_VERIFICATION = "unavailable_for_verification"


# canonical action name -> (class, list of recognised phrases). Deterministic; longest/most-specific first.
_GRAMMAR: Tuple[Tuple[str, DriverCommandClass, Tuple[str, ...]], ...] = (
    # --- safe operational --- #
    ("mute_coaching", DriverCommandClass.SAFE_OPERATIONAL, ("mute coaching", "stop coaching", "quiet coaching")),
    ("resume_coaching", DriverCommandClass.SAFE_OPERATIONAL, ("resume coaching", "coaching back on", "unmute coaching")),
    ("return_to_garage", DriverCommandClass.SAFE_OPERATIONAL, ("return to garage", "back to garage", "box this lap and stop", "in the garage after this lap")),
    ("next_pit_window", DriverCommandClass.SAFE_OPERATIONAL, ("next pit window", "when do i pit", "when is my stop")),
    ("current_plan", DriverCommandClass.SAFE_OPERATIONAL, ("current plan", "what's the plan", "what is the plan", "plan status")),
    ("fuel_status", DriverCommandClass.SAFE_OPERATIONAL, ("fuel status", "how's fuel", "how is fuel", "fuel level")),
    ("tyre_status", DriverCommandClass.SAFE_OPERATIONAL, ("tyre status", "tire status", "how are the tyres", "how are the tires")),
    ("acknowledge", DriverCommandClass.SAFE_OPERATIONAL, ("acknowledge", "acknowledged", "copy", "roger", "got it", "understood", "okay engineer")),
    ("repeat", DriverCommandClass.SAFE_OPERATIONAL, ("repeat", "say again", "repeat that", "come again")),
    ("unmute", DriverCommandClass.SAFE_OPERATIONAL, ("unmute", "unmute voice", "voice back on")),
    ("mute", DriverCommandClass.SAFE_OPERATIONAL, ("mute", "mute voice", "silence", "quiet")),
    ("status", DriverCommandClass.SAFE_OPERATIONAL, ("status", "give me status", "status report")),
    ("cancel", DriverCommandClass.SAFE_OPERATIONAL, ("cancel", "never mind", "nevermind", "abort")),
    ("dismiss", DriverCommandClass.SAFE_OPERATIONAL, ("dismiss", "dismiss message", "clear that")),
    # --- strategy requests --- #
    ("strategy_update", DriverCommandClass.STRATEGY_REQUEST, ("strategy update", "give me a strategy update", "update the strategy")),
    ("plan_viable", DriverCommandClass.STRATEGY_REQUEST, ("is the plan still viable", "is the plan viable", "does the plan still work", "are we still on plan")),
    ("what_if_stop_now", DriverCommandClass.STRATEGY_REQUEST, ("what happens if we stop now", "what if we stop now", "what if i pit now")),
    ("can_extend", DriverCommandClass.STRATEGY_REQUEST, ("can we extend", "can i extend", "can we go longer", "extend the stint")),
    ("can_save_fuel", DriverCommandClass.STRATEGY_REQUEST, ("can we save fuel", "do i need to save fuel", "should i save fuel")),
    ("fallback_plan", DriverCommandClass.STRATEGY_REQUEST, ("what is the fallback plan", "what's the fallback", "fallback plan", "plan b")),
    # --- driver reports --- #
    ("front_damage", DriverCommandClass.DRIVER_REPORT, ("front damage", "front end damage", "damaged the front", "front is damaged")),
    ("rear_damage", DriverCommandClass.DRIVER_REPORT, ("rear damage", "rear end damage", "damaged the rear", "rear is damaged")),
    ("car_damaged", DriverCommandClass.DRIVER_REPORT, ("car damaged", "i have damage", "we have damage", "car is damaged", "damage")),
    ("rain_starting", DriverCommandClass.DRIVER_REPORT, ("rain starting", "it's starting to rain", "rain is starting", "starting to rain", "it's raining")),
    ("track_drying", DriverCommandClass.DRIVER_REPORT, ("track drying", "track is drying", "drying out", "track's drying")),
    ("grip_dropping", DriverCommandClass.DRIVER_REPORT, ("tyre grip dropping", "grip is dropping", "losing grip", "grip's going", "tyres are gone")),
    ("fuel_display_differs", DriverCommandClass.DRIVER_REPORT, ("fuel display differs", "fuel reads different", "fuel display is different", "my fuel is different")),
    ("brakes_unstable", DriverCommandClass.DRIVER_REPORT, ("brakes feel unstable", "brakes are unstable", "brake issue", "no brakes")),
    ("traffic_heavy", DriverCommandClass.DRIVER_REPORT, ("traffic is heavy", "heavy traffic", "stuck in traffic", "lots of traffic")),
    # --- engineering feedback (DRAFT) --- #
    ("more_understeer_mid", DriverCommandClass.ENGINEERING_FEEDBACK, ("more understeer mid corner", "understeer mid corner", "understeer increasing", "more understeer")),
    ("rear_unstable_exit", DriverCommandClass.ENGINEERING_FEEDBACK, ("rear unstable on exit", "rear is loose on exit", "loose on exit", "rear unstable")),
    ("rear_loose", DriverCommandClass.ENGINEERING_FEEDBACK, ("rear is loose", "loose rear", "oversteer")),
    ("gearing_long", DriverCommandClass.ENGINEERING_FEEDBACK, ("gearing too long", "gears too long", "gearing is long")),
    ("tyre_deg_increasing", DriverCommandClass.ENGINEERING_FEEDBACK, ("tyre degradation increasing", "tyres degrading", "deg is high", "degradation increasing")),
    ("better_than_previous", DriverCommandClass.ENGINEERING_FEEDBACK, ("better than previous", "better than last", "that's better", "improvement")),
    ("worse_than_previous", DriverCommandClass.ENGINEERING_FEEDBACK, ("worse than previous", "worse than last", "that's worse", "regression")),
    ("no_change", DriverCommandClass.ENGINEERING_FEEDBACK, ("no change", "about the same", "no difference", "same as before")),
)

# reports/feedback whose meaning depends on telemetry that GT7 may not broadcast.
_TELEMETRY_UNVERIFIABLE_REPORTS = {
    "rain_starting", "track_drying", "grip_dropping", "brakes_unstable", "traffic_heavy",
    "fuel_display_differs",
}


def _match_action(text: str) -> Tuple[str, DriverCommandClass, str]:
    """Best deterministic phrase match. Returns (action, class, matched_phrase) or unrecognised."""
    t = " " + re.sub(r"[^a-z0-9' ]+", " ", _lc(text)) + " "
    t = re.sub(r"\s+", " ", t)
    best = ("", DriverCommandClass.UNRECOGNISED, "")
    best_len = 0
    for action, klass, phrases in _GRAMMAR:
        for ph in phrases:
            if f" {ph} " in t and len(ph) > best_len:
                best = (action, klass, ph)
                best_len = len(ph)
    return best


@dataclass(frozen=True)
class DriverUtterance:
    """A recognised (or unrecognised) driver utterance. ``text`` is retained only for the operational
    workflow (read-back) and NEVER enters an engineering fingerprint."""
    text: str
    confidence: float
    ptt_held: bool = True

    @property
    def ambiguous(self) -> bool:
        return (not self.ptt_held) or self.confidence < _MIN_CONFIDENCE


@dataclass(frozen=True)
class DriverCommandIntent:
    """The classified intent of an utterance. The fingerprint excludes the raw transcript."""
    action: str
    command_class: DriverCommandClass
    confidence: float
    ambiguous: bool
    requires_readback: bool
    executes_immediately: bool
    driver_report_label: Optional[str]     # set only for driver reports
    matched_phrase: str = ""
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return {"action": self.action, "command_class": self.command_class.value,
                "confidence": round(float(self.confidence), 3), "ambiguous": bool(self.ambiguous),
                "requires_readback": bool(self.requires_readback),
                "executes_immediately": bool(self.executes_immediately),
                "driver_report_label": self.driver_report_label, "fingerprint": self.fingerprint}


# utterance classes that could affect strategy/evidence/setup/damage/weather → require a read-back.
_READBACK_CLASSES = (DriverCommandClass.DRIVER_REPORT, DriverCommandClass.ENGINEERING_FEEDBACK)
_READBACK_STRATEGY_ACTIONS: Tuple[str, ...] = ()   # strategy REQUESTS are safe (they only ask) — no readback


def recognize_command(utterance: DriverUtterance) -> DriverCommandIntent:
    """Classify an utterance deterministically. An AMBIGUOUS utterance (PTT not held or confidence below
    threshold) is UNRECOGNISED and can trigger nothing. Never raises."""
    try:
        if utterance is None or not _norm(utterance.text):
            return _intent("", DriverCommandClass.UNRECOGNISED, 0.0, True, "")
        action, klass, phrase = _match_action(utterance.text)
        ambiguous = utterance.ambiguous
        if not action:
            return _intent("", DriverCommandClass.UNRECOGNISED, utterance.confidence, ambiguous, "")
        # A low-confidence / no-PTT utterance never classifies as an actionable command.
        if ambiguous:
            return _intent(action, DriverCommandClass.UNRECOGNISED, utterance.confidence, True, phrase,
                           original_class=klass)
        return _intent(action, klass, utterance.confidence, False, phrase)
    except Exception:  # pragma: no cover - defensive
        return _intent("", DriverCommandClass.UNRECOGNISED, 0.0, True, "")


def _intent(action, klass, confidence, ambiguous, phrase, *, original_class=None) -> DriverCommandIntent:
    requires_readback = (klass in _READBACK_CLASSES) and not ambiguous
    executes_immediately = (klass == DriverCommandClass.SAFE_OPERATIONAL) and not ambiguous
    label = None
    src_class = original_class or klass
    if src_class == DriverCommandClass.DRIVER_REPORT:
        # a report starts driver-reported + unverified (never verified telemetry).
        label = DriverReportLabel.UNVERIFIED.value if action in _TELEMETRY_UNVERIFIABLE_REPORTS \
            else DriverReportLabel.DRIVER_REPORTED.value
    fp = _fp({"a": action, "c": klass.value, "amb": bool(ambiguous),
              "rb": bool(requires_readback), "ex": bool(executes_immediately), "lab": label})
    return DriverCommandIntent(action=action, command_class=klass, confidence=float(confidence or 0.0),
                               ambiguous=bool(ambiguous), requires_readback=requires_readback,
                               executes_immediately=executes_immediately, driver_report_label=label,
                               matched_phrase=phrase, fingerprint=fp)


# --------------------------------------------------------------------------- #
# Read-back + confirmation workflow
# --------------------------------------------------------------------------- #
class ReadbackResponse(str, Enum):
    CONFIRM = "confirm"
    CORRECT = "correct"
    CANCEL = "cancel"
    REPEAT = "repeat"
    REVIEW_IN_GARAGE = "review_in_garage"


@dataclass(frozen=True)
class VoiceReadbackDecision:
    """Whether a concise read-back is required before an utterance can affect anything, and its text."""
    required: bool
    readback_text: str
    reason: str
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return {"required": bool(self.required), "readback_text": self.readback_text,
                "reason": self.reason, "fingerprint": self.fingerprint}


_READBACK_TEXT = {
    "rain_starting": "Copy — you're reporting rain starting. Confirm?",
    "track_drying": "Copy — track drying. Confirm?",
    "car_damaged": "Copy — car damage reported. Confirm?",
    "front_damage": "Copy — front damage reported. Confirm?",
    "rear_damage": "Copy — rear damage reported. Confirm?",
    "grip_dropping": "Copy — grip dropping. Confirm?",
    "brakes_unstable": "Copy — brakes unstable. Confirm?",
    "fuel_display_differs": "Copy — fuel reading differs. Confirm?",
    "traffic_heavy": "Copy — heavy traffic. Confirm?",
    "more_understeer_mid": "Copy — more mid-corner understeer. Log as feedback?",
    "rear_unstable_exit": "Copy — rear unstable on exit. Log as feedback?",
    "rear_loose": "Copy — rear loose. Log as feedback?",
    "gearing_long": "Copy — gearing too long. Log as feedback?",
    "tyre_deg_increasing": "Copy — tyre degradation increasing. Log as feedback?",
    "better_than_previous": "Copy — better than the previous run. Log as feedback?",
    "worse_than_previous": "Copy — worse than the previous run. Log as feedback?",
    "no_change": "Copy — no change from the previous run. Log as feedback?",
}


def decide_readback(intent: DriverCommandIntent) -> VoiceReadbackDecision:
    """Decide the read-back for a classified intent. Any utterance that could affect strategy, evidence,
    setup interpretation, damage or weather requires a concise read-back the driver confirms via PTT.
    Never raises."""
    try:
        if intent is None or intent.command_class not in _READBACK_CLASSES or intent.ambiguous:
            return VoiceReadbackDecision(False, "", "no read-back required", _fp({"rb": "none"}))
        text = _READBACK_TEXT.get(intent.action, "Copy — confirm?")
        return VoiceReadbackDecision(True, text, f"read-back required for {intent.command_class.value}",
                                     _fp({"rb": intent.action}))
    except Exception:  # pragma: no cover - defensive
        return VoiceReadbackDecision(False, "", "read-back error", _fp({"rb": "error"}))


@dataclass(frozen=True)
class DriverFeedbackDraft:
    """A DRAFT engineering-feedback record from speech. It is NOT canonical learning until confirmed
    through the existing outcome/feedback workflow. The raw transcript is never stored here."""
    action: str
    summary: str
    confirmed: bool = False
    source: str = "driver_voice"
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return {"action": self.action, "summary": self.summary, "confirmed": bool(self.confirmed),
                "source": self.source, "fingerprint": self.fingerprint}


@dataclass(frozen=True)
class DriverFeedbackConfirmation:
    """The result of a read-back response for a report/feedback utterance."""
    action: str
    command_class: str
    response: str
    confirmed: bool
    driver_report_label: Optional[str]
    creates_draft: bool
    enters_canonical: bool                 # ALWAYS False here — canonical entry uses the existing workflow
    message: str
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return {"action": self.action, "command_class": self.command_class, "response": self.response,
                "confirmed": bool(self.confirmed), "driver_report_label": self.driver_report_label,
                "creates_draft": bool(self.creates_draft),
                "enters_canonical": bool(self.enters_canonical), "message": self.message,
                "fingerprint": self.fingerprint}


_FEEDBACK_SUMMARY = {
    "more_understeer_mid": "Driver reports more mid-corner understeer.",
    "rear_unstable_exit": "Driver reports the rear is unstable on exit.",
    "rear_loose": "Driver reports a loose rear.",
    "gearing_long": "Driver reports gearing is too long.",
    "tyre_deg_increasing": "Driver reports increasing tyre degradation.",
    "better_than_previous": "Driver reports the run felt better than the previous.",
    "worse_than_previous": "Driver reports the run felt worse than the previous.",
    "no_change": "Driver reports no change from the previous run.",
}


def apply_readback_response(intent: DriverCommandIntent, response) -> DriverFeedbackConfirmation:
    """Apply a read-back response to a report/feedback intent. CONFIRM promotes a driver report to
    'confirmed by read-back' (still not telemetry) and a feedback item to a DRAFT (never canonical here).
    CORRECT/CANCEL/REPEAT/REVIEW create nothing. Never raises."""
    try:
        resp = response if isinstance(response, ReadbackResponse) else ReadbackResponse(_lc(response))
    except Exception:
        resp = ReadbackResponse.CANCEL
    action = intent.action if intent else ""
    klass = intent.command_class.value if intent else DriverCommandClass.UNRECOGNISED.value
    confirmed = resp == ReadbackResponse.CONFIRM
    is_feedback = bool(intent) and intent.command_class == DriverCommandClass.ENGINEERING_FEEDBACK
    is_report = bool(intent) and intent.command_class == DriverCommandClass.DRIVER_REPORT

    label = intent.driver_report_label if intent else None
    creates_draft = confirmed and is_feedback
    if confirmed and is_report:
        label = DriverReportLabel.CONFIRMED_BY_READBACK.value
        msg = "Confirmed as a driver report (read-back). Not treated as verified telemetry."
    elif confirmed and is_feedback:
        msg = ("Logged as a feedback DRAFT. It will not enter canonical learning until confirmed "
               "through the debrief/outcome workflow.")
    elif resp == ReadbackResponse.REVIEW_IN_GARAGE:
        msg = "Held for review in the garage."
    elif resp in (ReadbackResponse.CORRECT, ReadbackResponse.REPEAT):
        msg = "Understood — go again."
    else:
        msg = "Cancelled — nothing recorded."

    fp = _fp({"a": action, "c": klass, "r": resp.value, "conf": bool(confirmed),
              "lab": label, "draft": bool(creates_draft)})
    return DriverFeedbackConfirmation(
        action=action, command_class=klass, response=resp.value, confirmed=confirmed,
        driver_report_label=label, creates_draft=creates_draft, enters_canonical=False,
        message=msg, fingerprint=fp)


def build_feedback_draft(intent: DriverCommandIntent) -> Optional[DriverFeedbackDraft]:
    """Build an UNCONFIRMED feedback draft from a confirmed feedback intent (never canonical). Returns
    None for non-feedback intents. Never raises."""
    try:
        if not intent or intent.command_class != DriverCommandClass.ENGINEERING_FEEDBACK or intent.ambiguous:
            return None
        summary = _FEEDBACK_SUMMARY.get(intent.action, "Driver feedback.")
        return DriverFeedbackDraft(action=intent.action, summary=summary, confirmed=False,
                                   fingerprint=_fp({"draft": intent.action}))
    except Exception:  # pragma: no cover - defensive
        return None


def label_driver_report_against_telemetry(intent: DriverCommandIntent, *,
                                          telemetry_available: bool,
                                          telemetry_agrees: Optional[bool]) -> str:
    """Label a driver report given telemetry availability. A report is corroborated ONLY when telemetry
    is available AND agrees; it conflicts when telemetry disagrees; otherwise it stays driver-reported /
    unavailable-for-verification. Never fabricates telemetry. Never raises."""
    try:
        if not intent or intent.command_class != DriverCommandClass.DRIVER_REPORT:
            return DriverReportLabel.UNAVAILABLE_FOR_VERIFICATION.value
        if not telemetry_available:
            return DriverReportLabel.UNAVAILABLE_FOR_VERIFICATION.value
        if telemetry_agrees is True:
            return DriverReportLabel.CORROBORATED_BY_TELEMETRY.value
        if telemetry_agrees is False:
            return DriverReportLabel.CONFLICTING_WITH_TELEMETRY.value
        return DriverReportLabel.DRIVER_REPORTED.value
    except Exception:  # pragma: no cover - defensive
        return DriverReportLabel.UNAVAILABLE_FOR_VERIFICATION.value


# --------------------------------------------------------------------------- #
# Config safety — PTT binding + voice preferences are OPERATIONAL config only.
# These read/write a plain config dict (the caller persists it via the existing atomic save_config). The
# input_code / key code is operational configuration and is EXCLUDED from every engineering fingerprint.
# --------------------------------------------------------------------------- #
_PTT_CONFIG_KEY = "ptt_binding"


def read_ptt_binding(config: Optional[Mapping]) -> PushToTalkBinding:
    """Read the PTT binding from a config mapping (unbound if absent/malformed). Never raises."""
    try:
        c = config if isinstance(config, Mapping) else {}
        return PushToTalkBinding.from_config(c.get(_PTT_CONFIG_KEY))
    except Exception:  # pragma: no cover - defensive
        return PushToTalkBinding()


def write_ptt_binding(config: dict, binding: PushToTalkBinding) -> dict:
    """Write the PTT binding into a config dict IN PLACE (explicit user action only). Returns the same
    dict for chaining. This is operational nav/config state — never an engineering write. Never raises."""
    try:
        if isinstance(config, dict) and isinstance(binding, PushToTalkBinding):
            config[_PTT_CONFIG_KEY] = binding.to_config()
    except Exception:  # pragma: no cover - defensive
        pass
    return config


def push_to_talk_versions() -> dict:
    return {"push_to_talk": PUSH_TO_TALK_VERSION}
