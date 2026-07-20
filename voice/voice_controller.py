"""Advisory Voice Controller (Program 2, Phase 47).

Drives the pure ``VoiceQueue`` and a concrete ``VoiceOutputPort``, applying the opt-in + safety gates
and handling adapter failure. It is the impure boundary (it calls the port) but stays deterministic
given an injected monotonic ``now``. It speaks only advisories that already passed the Phase-44 and
Phase-46 gates, only the EXACT approved message, and only when voice is explicitly enabled and the
live-validation readiness allows it.

Failure behaviour: any port failure disables voice, records an honest adapter-health error, preserves
the advisory visually, and does not retry continuously. It never raises into the caller and never
crashes the dashboard.

Safety: offline only; no cloud/API/LLM; no pit/tyre/fuel/setup commands (those never reach the queue).
Voice is DISABLED by default; construction speaks nothing.
"""
from __future__ import annotations

from typing import Mapping, Optional

from strategy.voice_delivery import VoiceQueue, VoiceQueueDecision
from strategy.shadow_advisory import voice_gate_allows

_DEFAULT_CONFIG = {"enabled": False, "rate": 0, "volume": 100, "max_routine_seconds": 4.0,
                   "repeat_permitted": False, "voice_name": ""}


class AdapterHealth(str):
    DISABLED = "disabled"
    OK = "ok"
    FAILED = "failed"


class VoiceController:
    """Opt-in advisory voice controller. Deterministic given injected ``now``. Never raises."""

    def __init__(self, port=None, config: Optional[Mapping] = None):
        from strategy.voice_delivery import DisabledVoicePort
        self._port = port if port is not None else DisabledVoicePort()
        self._config = dict(_DEFAULT_CONFIG)
        if isinstance(config, Mapping):
            self._config.update({k: config[k] for k in config if k in _DEFAULT_CONFIG})
        self._queue = VoiceQueue()
        self._health = AdapterHealth.DISABLED
        self._last_spoken_message = ""
        self._run_active = False

    # ---- opt-in ---- #
    def enable(self) -> bool:
        """Explicitly enable voice. Initialises the port if it exposes enable(). Never raises."""
        try:
            ok = True
            if hasattr(self._port, "enable"):
                ok = bool(self._port.enable())
            self._config["enabled"] = bool(ok)
            self._health = AdapterHealth.OK if (ok and self._port.is_available()) \
                else AdapterHealth.FAILED if not ok else AdapterHealth.DISABLED
            return bool(self._config["enabled"] and self._port.is_available())
        except Exception:  # pragma: no cover - defensive
            self._config["enabled"] = False
            self._health = AdapterHealth.FAILED
            return False

    def disable(self) -> None:
        self._config["enabled"] = False
        self._health = AdapterHealth.DISABLED
        try:
            self._port.stop()
        except Exception:
            pass
        self._queue.cancel_all("voice disabled")

    @property
    def enabled(self) -> bool:
        return bool(self._config.get("enabled"))

    # ---- run lifecycle ---- #
    def set_run_active(self, active: bool) -> None:
        self._run_active = bool(active)

    def on_context_change(self) -> None:
        self._queue.cancel_all("context / run-plan changed")
        try:
            self._port.stop()
        except Exception:
            pass

    def on_session_end(self) -> None:
        self._queue.cancel_all("session ended")
        try:
            self._port.stop()
        except Exception:
            pass

    # ---- driver acknowledgement / mute ---- #
    def acknowledge(self, key: str) -> None:
        self._queue.acknowledge(key)

    def repeat_once(self, prompt: Optional[Mapping]) -> None:
        # repeat speaks the SAME approved message once; it creates no new recommendation. An explicit
        # repeat bypasses the cooldown for that key.
        if self.enabled and isinstance(prompt, Mapping):
            key = str(prompt.get("suppression_key") or prompt.get("prompt_type") or "")
            if key:
                self._queue.clear_cooldown(key)
            self._queue.submit(prompt)

    def mute_type(self, key: str) -> None:
        self._queue.mute_type(key)

    def mute_coaching_for_lap(self, lap: int) -> None:
        self._queue.mute_coaching_for_lap(lap)

    # ---- submission + tick ---- #
    def submit(self, prompt: Optional[Mapping]) -> None:
        if self.enabled and isinstance(prompt, Mapping) and str(prompt.get("message") or "").strip():
            self._queue.submit(prompt)

    def tick(self, now: float, *, gates_ok: bool = True, readiness: str = "",
             current_lap: Optional[int] = None) -> dict:
        """Poll the queue and speak the selected message if allowed. Returns a status dict. Deterministic
        given ``now``; never raises."""
        try:
            allowed = self.enabled and voice_gate_allows(readiness)
            decision = self._queue.poll(now, voice_enabled=allowed, gates_ok=gates_ok,
                                        current_lap=current_lap)
            spoke = None
            if decision.action in ("speak", "interrupt") and decision.request:
                msg = str(decision.request.get("message") or "")
                if decision.action == "interrupt":
                    try:
                        self._port.stop()
                    except Exception:
                        pass
                ok = False
                try:
                    ok = bool(self._port.speak(msg))
                except Exception:
                    ok = False
                if ok:
                    self._last_spoken_message = msg
                    spoke = msg
                    self._health = AdapterHealth.OK
                else:
                    # adapter failure -> disable voice, keep advisory visual, do not retry.
                    self._health = AdapterHealth.FAILED
                    self._config["enabled"] = False
                    self._queue.on_finished_speaking()
            return {"action": decision.action, "spoke": spoke, "reason": decision.reason,
                    "health": self._health, "enabled": self.enabled,
                    "queue": self._queue.snapshot()}
        except Exception:  # pragma: no cover - defensive
            return {"action": "hold", "spoke": None, "reason": "controller error",
                    "health": AdapterHealth.FAILED, "enabled": False, "queue": {}}

    def notify_finished_speaking(self) -> None:
        self._queue.on_finished_speaking()

    def test_voice(self, message: str = "Race engineer voice check.") -> dict:
        """Speak a test message ONLY when a timed run is NOT active (so it cannot interfere with live
        prompts). Never raises."""
        if self._run_active:
            return {"ok": False, "reason": "a timed run is active - test voice is unavailable now."}
        if not self.enabled:
            return {"ok": False, "reason": "voice is disabled."}
        try:
            ok = bool(self._port.speak(str(message)))
            if not ok:
                self._health = AdapterHealth.FAILED
                self._config["enabled"] = False
            return {"ok": ok, "reason": "spoken" if ok else "adapter failure - voice disabled."}
        except Exception:  # pragma: no cover - defensive
            self._health = AdapterHealth.FAILED
            self._config["enabled"] = False
            return {"ok": False, "reason": "adapter error - voice disabled."}

    def status(self) -> dict:
        return {"enabled": self.enabled, "health": self._health,
                "last_spoken": self._last_spoken_message, "config": dict(self._config),
                "queue": self._queue.snapshot(), "port": getattr(self._port, "name", "unknown")}

    def set_config(self, **kw) -> None:
        for k, v in kw.items():
            if k in _DEFAULT_CONFIG:
                self._config[k] = v
        if hasattr(self._port, "set_rate") and "rate" in kw:
            self._port.set_rate(int(kw["rate"]))
        if hasattr(self._port, "set_volume") and "volume" in kw:
            self._port.set_volume(int(kw["volume"]))
