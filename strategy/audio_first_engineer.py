"""PSVR2 Audio-First Race Engineer — pure decision layer (Program 2, Phase 63).

WHY IT EXISTS
  The driver may be wearing a PSVR2 headset and unable to see the PC screen while driving. During
  Practice, Qualifying and Race, essential information must therefore reach the driver as concise SPOKEN
  race-engineer messages, delivered in low-workload windows, prioritised so a lower-priority message never
  interrupts a higher-priority one. This module is the deterministic DECISION layer over that experience.

WHAT THIS MODULE IS / IS NOT
  • It DECIDES: the single message priority order, the driver-workload estimate from trustworthy live
    context, whether a message may be spoken now (the speech window), the concise duration budget, and the
    composite audio operational readiness + voice/listening state.
  • It is NOT a voice engine, a second advisory engine, or a telemetry listener. It never speaks, never
    queues (the Phase-47 ``VoiceQueue``/``VoiceController`` own delivery), never reads telemetry directly,
    never changes an engineering conclusion, and never alters an evidence fingerprint.
  • Voice/PTT are INTERFACES to canonical authorities, not independent agents. This module carries no AI,
    no network, no DB, no Qt, no wall clock (runtime timing is injected), and never raises.

DETERMINISM
  Every semantic decision has a version-prefixed fingerprint over sorted-key ASCII JSON that EXCLUDES
  volatile operational/display state (device identity, selected Windows voice, volume, PTT key code, raw
  audio, filesystem paths, UI tab, wall-clock render time).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Optional, Sequence, Tuple

AUDIO_FIRST_ENGINEER_VERSION = "audio_first_engineer_v1"


def _norm(v) -> str:
    return str(v if v is not None else "").strip()


def _lc(v) -> str:
    return _norm(v).lower()


def _fp(payload) -> str:
    return (f"{AUDIO_FIRST_ENGINEER_VERSION}:"
            + hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=True, default=str).encode()).hexdigest()[:24])


def _num(x) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# VR runtime mode
# --------------------------------------------------------------------------- #
class VrRuntimeMode(str, Enum):
    """How the live experience is being consumed. Audio-first mode makes the verbal channel primary
    but never alters engineering conclusions and never bypasses voice eligibility."""
    DESKTOP = "desktop"           # normal on-screen use (non-VR); voice optional
    AUDIO_FIRST = "audio_first"   # PSVR2 / no-screen: verbal delivery is the primary live channel


# --------------------------------------------------------------------------- #
# Message intent + the single deterministic priority authority
# --------------------------------------------------------------------------- #
class EngineerMessageIntent(str, Enum):
    """What a live message is FOR (its operational meaning). Priority is derived from this, once."""
    SAFETY_CRITICAL = "safety_critical"        # immediate safety / critical mismatch
    CAR_CONDITION_WARNING = "car_condition_warning"  # severe telemetry / car-condition warning
    STRATEGY_CHANGE = "strategy_change"        # material strategy change
    PIT_FUEL_UPDATE = "pit_fuel_update"        # pit-window / fuel-critical update
    SESSION_TRANSITION = "session_transition"  # session / activity transition
    SETUP_TEST_INSTRUCTION = "setup_test_instruction"  # important setup-test instruction
    LAP_STINT_STATUS = "lap_stint_status"      # lap / stint status
    DRIVER_COACHING = "driver_coaching"        # coaching
    INFORMATIONAL = "informational"            # informational detail


class EngineerMessagePriority(int, Enum):
    """Lower value = higher priority. A lower-priority message never interrupts a higher-priority one."""
    SAFETY = 1
    CAR_CONDITION = 2
    STRATEGY = 3
    PIT_FUEL = 4
    TRANSITION = 5
    SETUP_TEST = 6
    LAP_STINT = 7
    COACHING = 8
    INFO = 9


_INTENT_PRIORITY = {
    EngineerMessageIntent.SAFETY_CRITICAL: EngineerMessagePriority.SAFETY,
    EngineerMessageIntent.CAR_CONDITION_WARNING: EngineerMessagePriority.CAR_CONDITION,
    EngineerMessageIntent.STRATEGY_CHANGE: EngineerMessagePriority.STRATEGY,
    EngineerMessageIntent.PIT_FUEL_UPDATE: EngineerMessagePriority.PIT_FUEL,
    EngineerMessageIntent.SESSION_TRANSITION: EngineerMessagePriority.TRANSITION,
    EngineerMessageIntent.SETUP_TEST_INSTRUCTION: EngineerMessagePriority.SETUP_TEST,
    EngineerMessageIntent.LAP_STINT_STATUS: EngineerMessagePriority.LAP_STINT,
    EngineerMessageIntent.DRIVER_COACHING: EngineerMessagePriority.COACHING,
    EngineerMessageIntent.INFORMATIONAL: EngineerMessagePriority.INFO,
}

# The two most urgent intents may override the normal low-workload window (safety / strategy-critical).
_WINDOW_OVERRIDE_PRIORITIES = (EngineerMessagePriority.SAFETY, EngineerMessagePriority.CAR_CONDITION,
                               EngineerMessagePriority.STRATEGY, EngineerMessagePriority.PIT_FUEL)
# Stop-critical (interrupts an active routine message via the Phase-47 queue).
_STOP_CRITICAL_PRIORITIES = (EngineerMessagePriority.SAFETY, EngineerMessagePriority.CAR_CONDITION)


def classify_message_priority(intent) -> EngineerMessagePriority:
    """The single priority authority: map a message intent to its deterministic priority. Unknown intents
    are treated as INFORMATIONAL (lowest), never as urgent. Never raises."""
    try:
        if isinstance(intent, EngineerMessagePriority):
            return intent
        if not isinstance(intent, EngineerMessageIntent):
            try:
                intent = EngineerMessageIntent(_lc(intent))
            except ValueError:
                return EngineerMessagePriority.INFO
        return _INTENT_PRIORITY.get(intent, EngineerMessagePriority.INFO)
    except Exception:  # pragma: no cover - defensive
        return EngineerMessagePriority.INFO


# --------------------------------------------------------------------------- #
# Driver workload (from trustworthy live context only)
# --------------------------------------------------------------------------- #
class DriverWorkloadState(str, Enum):
    LOW = "low"                 # straight / pit lane / stopped — safe to speak routine messages
    MODERATE = "moderate"       # light steering / partial throttle
    HIGH = "high"               # braking / corner entry / apex / heavy steering — defer routine
    UNKNOWN = "unknown"         # workload cannot be trusted — treat conservatively (as if not-low)


@dataclass(frozen=True)
class DriverWorkloadEstimate:
    state: DriverWorkloadState
    reason: str
    inputs_available: bool                 # False when no trustworthy workload signal was present
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return {"state": self.state.value, "reason": self.reason,
                "inputs_available": bool(self.inputs_available)}


# track-segment phases that indicate a high-workload moment.
_HIGH_SEGMENTS = ("braking", "corner_entry", "entry", "apex", "corner", "turn", "corner_exit", "chicane")
_LOW_SEGMENTS = ("straight", "start_finish_straight", "pit_lane", "pitlane", "pit", "grid", "stopped")


def assess_driver_workload(context: Optional[Mapping]) -> DriverWorkloadEstimate:
    """Estimate driver workload from TRUSTWORTHY live context only. Unknown workload is conservative
    (never LOW), so routine messages are not delivered into an unknown moment. Never raises.

    Recognised (all optional): ``segment``/``segment_phase`` (str), ``braking`` (bool/0..1),
    ``throttle`` (0..1), ``steering`` (-1..1 or 0..1 magnitude), ``speed_kmh`` (float),
    ``in_pit_lane`` (bool), ``stopped`` (bool), ``telemetry_fresh`` (bool).
    """
    try:
        c = context if isinstance(context, Mapping) else {}
        if not c:
            return DriverWorkloadEstimate(DriverWorkloadState.UNKNOWN,
                                          "no live workload signal — treated conservatively", False,
                                          _fp({"w": "unknown-empty"}))
        fresh = c.get("telemetry_fresh", True)
        if fresh is False:
            return DriverWorkloadEstimate(DriverWorkloadState.UNKNOWN,
                                          "telemetry stale — workload not trusted", False,
                                          _fp({"w": "unknown-stale"}))

        seg = _lc(c.get("segment") or c.get("segment_phase"))
        braking = c.get("braking")
        throttle = _num(c.get("throttle"))
        steer = _num(c.get("steering"))
        speed = _num(c.get("speed_kmh"))
        in_pit = bool(c.get("in_pit_lane"))
        stopped = bool(c.get("stopped")) or (speed is not None and speed <= 1.0)

        have_signal = any(v is not None for v in (throttle, steer, speed)) or bool(seg) \
            or braking is not None or in_pit or stopped

        # Unambiguous LOW states first.
        if in_pit:
            return DriverWorkloadEstimate(DriverWorkloadState.LOW, "in pit lane", True,
                                          _fp({"w": "low-pit"}))
        if stopped:
            return DriverWorkloadEstimate(DriverWorkloadState.LOW, "stopped", True,
                                          _fp({"w": "low-stopped"}))

        # HIGH signals: braking, a corner segment, or heavy steering.
        braking_on = (braking is True) or (isinstance(braking, (int, float))
                                           and not isinstance(braking, bool) and float(braking) > 0.15)
        steer_mag = abs(steer) if steer is not None else None
        if braking_on:
            return DriverWorkloadEstimate(DriverWorkloadState.HIGH, "braking", True, _fp({"w": "high-brake"}))
        if seg and any(k in seg for k in _HIGH_SEGMENTS) and not any(k in seg for k in ("straight",)):
            return DriverWorkloadEstimate(DriverWorkloadState.HIGH, f"cornering ({seg})", True,
                                          _fp({"w": "high-seg", "seg": seg}))
        if steer_mag is not None and steer_mag >= 0.35:
            return DriverWorkloadEstimate(DriverWorkloadState.HIGH, "heavy steering input", True,
                                          _fp({"w": "high-steer"}))

        # LOW: on a straight, or light steering + near-full throttle.
        on_straight = bool(seg) and any(k in seg for k in _LOW_SEGMENTS)
        light_steer = steer_mag is not None and steer_mag < 0.12
        high_throttle = throttle is not None and throttle >= 0.9
        if on_straight or (light_steer and high_throttle):
            return DriverWorkloadEstimate(DriverWorkloadState.LOW, "straight / low control activity", True,
                                          _fp({"w": "low-straight"}))

        if not have_signal:
            return DriverWorkloadEstimate(DriverWorkloadState.UNKNOWN,
                                          "insufficient workload signal — conservative", False,
                                          _fp({"w": "unknown-nosignal"}))
        # Something is happening but not clearly low or high.
        return DriverWorkloadEstimate(DriverWorkloadState.MODERATE, "moderate control activity", True,
                                      _fp({"w": "moderate"}))
    except Exception:  # pragma: no cover - defensive
        return DriverWorkloadEstimate(DriverWorkloadState.UNKNOWN, "workload error — conservative", False,
                                      _fp({"w": "unknown-error"}))


# --------------------------------------------------------------------------- #
# Speech window decision
# --------------------------------------------------------------------------- #
class SpeechWindowVerdict(str, Enum):
    SPEAK_NOW = "speak_now"           # deliver in this window
    DEFER = "defer"                   # hold until a lower-workload window
    OVERRIDE = "override"             # urgent: override the workload gate and deliver now


@dataclass(frozen=True)
class SpeechWindowDecision:
    verdict: SpeechWindowVerdict
    priority: int
    workload: str
    reason: str
    fingerprint: str = ""

    @property
    def may_speak(self) -> bool:
        return self.verdict in (SpeechWindowVerdict.SPEAK_NOW, SpeechWindowVerdict.OVERRIDE)

    def to_dict(self) -> dict:
        return {"verdict": self.verdict.value, "priority": int(self.priority),
                "workload": self.workload, "reason": self.reason}


def decide_speech_window(priority, workload) -> SpeechWindowDecision:
    """Decide whether a message of the given priority may be spoken in the current workload window.

    Rules (deterministic):
      • Urgent priorities (safety/car-condition/strategy/pit-fuel) OVERRIDE any workload — delivered now.
      • Routine priorities are delivered only in a LOW-workload window.
      • MODERATE, HIGH or UNKNOWN workload DEFERS a routine message (unknown is treated conservatively).
    Never raises.
    """
    try:
        pr = priority if isinstance(priority, EngineerMessagePriority) else \
            EngineerMessagePriority(int(priority))
        w = workload if isinstance(workload, DriverWorkloadState) else DriverWorkloadState(_lc(workload))
    except Exception:
        pr = EngineerMessagePriority.INFO
        w = DriverWorkloadState.UNKNOWN
    if pr in _WINDOW_OVERRIDE_PRIORITIES:
        return SpeechWindowDecision(SpeechWindowVerdict.OVERRIDE, int(pr), w.value,
                                    "urgent priority overrides the workload window",
                                    _fp({"win": "override", "p": int(pr)}))
    if w == DriverWorkloadState.LOW:
        return SpeechWindowDecision(SpeechWindowVerdict.SPEAK_NOW, int(pr), w.value,
                                    "routine message delivered in a low-workload window",
                                    _fp({"win": "speak", "p": int(pr)}))
    return SpeechWindowDecision(SpeechWindowVerdict.DEFER, int(pr), w.value,
                                f"routine message deferred ({w.value} workload)",
                                _fp({"win": "defer", "p": int(pr), "w": w.value}))


# --------------------------------------------------------------------------- #
# Message duration budget (concise — no paragraph-length radio while driving)
# --------------------------------------------------------------------------- #
# seconds; headline budgets. Detailed engineering explanation is deferred to garage/debrief (0 = defer).
_DURATION_BUDGET = {
    EngineerMessagePriority.SAFETY: 1.5,
    EngineerMessagePriority.CAR_CONDITION: 2.0,
    EngineerMessagePriority.STRATEGY: 3.0,       # concise headline first; detail on request/in garage
    EngineerMessagePriority.PIT_FUEL: 2.5,
    EngineerMessagePriority.TRANSITION: 2.5,
    EngineerMessagePriority.SETUP_TEST: 3.0,
    EngineerMessagePriority.LAP_STINT: 2.5,
    EngineerMessagePriority.COACHING: 2.5,
    EngineerMessagePriority.INFO: 2.5,
}
_MAX_ROUTINE_SECONDS = 2.5


def message_duration_budget(priority) -> float:
    """The concise spoken-duration budget (seconds) for a message of the given priority. Never raises."""
    try:
        pr = priority if isinstance(priority, EngineerMessagePriority) else \
            EngineerMessagePriority(int(priority))
    except Exception:
        pr = EngineerMessagePriority.INFO
    return float(_DURATION_BUDGET.get(pr, _MAX_ROUTINE_SECONDS))


# --------------------------------------------------------------------------- #
# Voice / listening state + audio operational readiness
# --------------------------------------------------------------------------- #
class AudioFirstEngineerState(str, Enum):
    """The composite voice + listening state the driver hears/sees. One at a time."""
    VISUAL_ONLY = "visual_only"                 # not in audio-first mode
    VOICE_DISABLED = "voice_disabled"           # voice off (default)
    VOICE_GATED = "voice_gated"                 # enabled but live-validation gate not satisfied
    VOICE_READY = "voice_ready"                 # eligible, idle
    VOICE_ACTIVE = "voice_active"               # currently speaking
    PTT_ACTIVE = "ptt_active"                   # driver holding PTT / listening
    MUTED = "muted"                             # muted by the driver
    RECOGNITION_UNAVAILABLE = "recognition_unavailable"  # no working mic/recogniser (TTS may still work)
    TTS_UNAVAILABLE = "tts_unavailable"         # no working TTS
    ADAPTER_FAILURE = "adapter_failure"         # a voice/PTT adapter failed
    TELEMETRY_STALE = "telemetry_stale"         # telemetry lost — routine advisories suppressed
    CRITICAL_ONLY = "critical_only"             # only safety/critical messages will be spoken


class AudioOperationalReadiness(str, Enum):
    """Whether audio-first operation is genuinely usable right now."""
    NOT_AUDIO_FIRST = "not_audio_first"         # desktop mode
    READY = "ready"                             # voice ready (TTS available), PTT optional
    DEGRADED = "degraded"                       # partial (e.g. TTS but no mic, or critical-only)
    UNAVAILABLE = "unavailable"                 # voice cannot operate — visual fallback only


@dataclass(frozen=True)
class LiveEngineerAudioSnapshot:
    """Immutable composite of the audio-first live state for the UI + voice controller. Display-only
    counters are excluded from the fingerprint."""
    vr_mode: VrRuntimeMode
    state: AudioFirstEngineerState
    readiness: AudioOperationalReadiness
    voice_enabled: bool
    tts_available: bool
    recognition_available: bool
    ptt_available: bool
    telemetry_fresh: bool
    critical_only: bool
    status_line: str                            # concise driver-facing status
    notes: Tuple[str, ...] = ()
    fingerprint: str = ""

    def as_stable_payload(self) -> dict:
        return {"vr_mode": self.vr_mode.value, "state": self.state.value,
                "readiness": self.readiness.value, "voice_enabled": bool(self.voice_enabled),
                "tts_available": bool(self.tts_available),
                "recognition_available": bool(self.recognition_available),
                "ptt_available": bool(self.ptt_available), "telemetry_fresh": bool(self.telemetry_fresh),
                "critical_only": bool(self.critical_only)}

    def to_dict(self) -> dict:
        d = self.as_stable_payload()
        d.update({"status_line": self.status_line, "notes": list(self.notes),
                  "fingerprint": self.fingerprint})
        return d


_STATE_LABEL = {
    AudioFirstEngineerState.VISUAL_ONLY: "Visual only — voice not active.",
    AudioFirstEngineerState.VOICE_DISABLED: "Voice off. Enable the race-engineer voice to hear updates.",
    AudioFirstEngineerState.VOICE_GATED: "Voice ready but gated — live validation not yet confirmed.",
    AudioFirstEngineerState.VOICE_READY: "Race-engineer voice ready.",
    AudioFirstEngineerState.VOICE_ACTIVE: "Race engineer speaking…",
    AudioFirstEngineerState.PTT_ACTIVE: "Listening — hold to talk.",
    AudioFirstEngineerState.MUTED: "Muted.",
    AudioFirstEngineerState.RECOGNITION_UNAVAILABLE: "Voice out only — no microphone / recogniser.",
    AudioFirstEngineerState.TTS_UNAVAILABLE: "Voice unavailable — visual pit wall only.",
    AudioFirstEngineerState.ADAPTER_FAILURE: "Voice adapter failed — visual pit wall preserved.",
    AudioFirstEngineerState.TELEMETRY_STALE: "Telemetry stale — routine radio paused.",
    AudioFirstEngineerState.CRITICAL_ONLY: "Critical messages only.",
}


def resolve_audio_engineer_state(
    *,
    vr_mode=VrRuntimeMode.DESKTOP,
    voice_enabled: bool = False,
    gate_allows: bool = False,
    speaking: bool = False,
    ptt_active: bool = False,
    muted: bool = False,
    tts_available: bool = True,
    recognition_available: bool = False,
    ptt_available: bool = False,
    telemetry_fresh: bool = True,
    adapter_failed: bool = False,
    critical_only: bool = False,
) -> LiveEngineerAudioSnapshot:
    """Resolve the ONE composite audio-first state + operational readiness deterministically.

    Precedence (highest first): adapter failure → TTS unavailable → visual-only (desktop) → voice
    disabled → PTT active → speaking → muted → telemetry stale → critical-only → gated → recognition
    unavailable (voice-out ready) → ready. Voice can never be manufactured ELIGIBLE here — ``gate_allows``
    is supplied by the canonical voice gate. Never raises.
    """
    try:
        mode = vr_mode if isinstance(vr_mode, VrRuntimeMode) else VrRuntimeMode(_lc(vr_mode))
    except Exception:
        mode = VrRuntimeMode.DESKTOP

    # readiness (independent of the transient state)
    if mode != VrRuntimeMode.AUDIO_FIRST:
        readiness = AudioOperationalReadiness.NOT_AUDIO_FIRST
    elif adapter_failed or not tts_available:
        readiness = AudioOperationalReadiness.UNAVAILABLE
    elif critical_only or not recognition_available:
        readiness = AudioOperationalReadiness.DEGRADED
    else:
        readiness = AudioOperationalReadiness.READY

    # transient state (one at a time, by precedence)
    if adapter_failed:
        state = AudioFirstEngineerState.ADAPTER_FAILURE
    elif not tts_available:
        state = AudioFirstEngineerState.TTS_UNAVAILABLE
    elif mode != VrRuntimeMode.AUDIO_FIRST and not voice_enabled:
        state = AudioFirstEngineerState.VISUAL_ONLY
    elif not voice_enabled:
        state = AudioFirstEngineerState.VOICE_DISABLED
    elif ptt_active:
        state = AudioFirstEngineerState.PTT_ACTIVE
    elif speaking:
        state = AudioFirstEngineerState.VOICE_ACTIVE
    elif muted:
        state = AudioFirstEngineerState.MUTED
    elif not telemetry_fresh:
        state = AudioFirstEngineerState.TELEMETRY_STALE
    elif critical_only:
        state = AudioFirstEngineerState.CRITICAL_ONLY
    elif not gate_allows:
        state = AudioFirstEngineerState.VOICE_GATED
    elif not recognition_available:
        state = AudioFirstEngineerState.RECOGNITION_UNAVAILABLE
    else:
        state = AudioFirstEngineerState.VOICE_READY

    notes = []
    if mode == VrRuntimeMode.AUDIO_FIRST:
        notes.append("Audio-first (PSVR2): essential information is spoken; the screen is a fallback.")
    if state in (AudioFirstEngineerState.ADAPTER_FAILURE, AudioFirstEngineerState.TTS_UNAVAILABLE):
        notes.append("Visual pit wall preserved; no retry loop; engineering conclusions unchanged.")

    snap = LiveEngineerAudioSnapshot(
        vr_mode=mode, state=state, readiness=readiness, voice_enabled=bool(voice_enabled),
        tts_available=bool(tts_available), recognition_available=bool(recognition_available),
        ptt_available=bool(ptt_available), telemetry_fresh=bool(telemetry_fresh),
        critical_only=bool(critical_only), status_line=_STATE_LABEL.get(state, ""), notes=tuple(notes))
    return _with_fp(snap)


def _with_fp(snap: LiveEngineerAudioSnapshot) -> LiveEngineerAudioSnapshot:
    return LiveEngineerAudioSnapshot(
        vr_mode=snap.vr_mode, state=snap.state, readiness=snap.readiness,
        voice_enabled=snap.voice_enabled, tts_available=snap.tts_available,
        recognition_available=snap.recognition_available, ptt_available=snap.ptt_available,
        telemetry_fresh=snap.telemetry_fresh, critical_only=snap.critical_only,
        status_line=snap.status_line, notes=snap.notes, fingerprint=_fp(snap.as_stable_payload()))


# --------------------------------------------------------------------------- #
# The engineer speech decision (composes priority + workload + window + budget)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class EngineerSpeechDecision:
    """The complete decision for ONE candidate live message: whether/when to speak it, its priority, its
    concise budget, and whether it is stop-critical (may interrupt a routine active message)."""
    intent: str
    priority: int
    window: SpeechWindowDecision
    duration_budget_seconds: float
    stop_critical: bool
    speak: bool
    reason: str
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return {"intent": self.intent, "priority": int(self.priority),
                "window": self.window.to_dict(),
                "duration_budget_seconds": round(float(self.duration_budget_seconds), 3),
                "stop_critical": bool(self.stop_critical), "speak": bool(self.speak),
                "reason": self.reason, "fingerprint": self.fingerprint}


def decide_engineer_speech(
    intent,
    *,
    workload=DriverWorkloadState.UNKNOWN,
    audio: Optional[LiveEngineerAudioSnapshot] = None,
) -> EngineerSpeechDecision:
    """Decide whether a message of the given intent should be spoken now, given driver workload and the
    current audio state. In CRITICAL_ONLY / telemetry-stale states only stop-critical messages pass.
    Never raises. This DECIDES only — the Phase-47 controller/queue performs the actual delivery."""
    try:
        it = intent if isinstance(intent, EngineerMessageIntent) else EngineerMessageIntent(_lc(intent))
    except Exception:
        it = EngineerMessageIntent.INFORMATIONAL
    priority = classify_message_priority(it)
    window = decide_speech_window(priority, workload)
    budget = message_duration_budget(priority)
    stop_critical = priority in _STOP_CRITICAL_PRIORITIES

    speak = window.may_speak
    reason = window.reason
    if audio is not None:
        # audio-state gating: only stop-critical messages survive stale/critical-only; nothing survives
        # when voice is not deliverable.
        if audio.state in (AudioFirstEngineerState.TELEMETRY_STALE, AudioFirstEngineerState.CRITICAL_ONLY):
            if not stop_critical:
                speak = False
                reason = f"suppressed: {audio.state.value} allows only critical messages"
        if audio.state in (AudioFirstEngineerState.VOICE_DISABLED, AudioFirstEngineerState.TTS_UNAVAILABLE,
                           AudioFirstEngineerState.ADAPTER_FAILURE, AudioFirstEngineerState.VISUAL_ONLY,
                           AudioFirstEngineerState.VOICE_GATED):
            speak = False
            reason = f"not deliverable: {audio.state.value}"

    payload = {"intent": it.value, "priority": int(priority), "window": window.to_dict(),
               "stop_critical": bool(stop_critical), "speak": bool(speak),
               "audio_state": audio.state.value if audio is not None else ""}
    return EngineerSpeechDecision(intent=it.value, priority=int(priority), window=window,
                                  duration_budget_seconds=budget, stop_critical=stop_critical,
                                  speak=speak, reason=reason, fingerprint=_fp(payload))


def audio_first_engineer_versions() -> dict:
    return {"audio_first_engineer": AUDIO_FIRST_ENGINEER_VERSION}
