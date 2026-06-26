"""Push-to-talk voice query system for GT7 VR Dashboard.

Press a configured button → hear a 440 Hz "listening" beep → speak a query
word → hear the answer announced via VoiceAnnouncer.

Supports keyboard buttons (via pynput) and optionally joystick buttons (via
pygame if installed). Audio is recorded with sounddevice and recognised via
the SpeechRecognition library (Google backend by default).
"""
from __future__ import annotations

import math
import queue
import threading
import time
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from telemetry.state import RaceStateTracker
    from voice.announcer import VoiceAnnouncer

from telemetry.packet import format_laptime_voice, format_remaining_time_voice
from telemetry.state import Priority, RaceType, TyreState

try:
    import sounddevice as _sd
    import numpy as _np
    _SOUNDDEVICE_OK = True
except ImportError:
    _SOUNDDEVICE_OK = False

try:
    import speech_recognition as _sr
    _SR_OK = True
except ImportError:
    _SR_OK = False


# ---------------------------------------------------------------------------
# Intent matching
# ---------------------------------------------------------------------------

_INTENT_KEYWORDS: list[tuple[str, list[str]]] = [
    ("fuel",       ["fuel", "litre", "liter", "petrol", "gas", "tank"]),
    ("position",   ["position", "where", "place", "standing", "rank"]),
    ("laps",       ["laps", "how many"]),
    ("time",       ["time", "remaining", "how long", "minutes", "clock"]),
    ("best",       ["best", "fastest", "record"]),
    ("pit",        ["pit window", "when pit", "when should i pit", "pit now", "when do i pit", "pit stop"]),
    ("strategy",   ["strategy", "plan", "next stop", "stint"]),
    ("pace",       ["how am i", "pace", "going", "performance", "consistent", "falling"]),
    ("tyre_state", ["tyre", "tire", "rubber", "tires", "tyres"]),
    ("rain",       ["rain", "raining", "wet", "weather", "slippery", "damp"]),
    ("damage",     ["crash", "damage", "accident", "hit the wall", "bent", "spin",
                    "minor", "major incident"]),
    ("fuel_check",   ["fuel check", "fuel target", "fuel strategy", "burning", "spare fuel"]),
    ("lap_analysis", ["last lap", "how was", "analyze", "analyse", "lap review"]),
    ("coaching",     ["improve", "go faster", "coaching", "tips", "technique", "sector"]),
    ("setup_advice", ["setup", "car setup", "setup advice", "tuning", "tune"]),
]


def _match_intent(text: str) -> str:
    lower = text.lower()
    for intent, keywords in _INTENT_KEYWORDS:
        if any(kw in lower for kw in keywords):
            return intent
    return ""


def _build_response(intent: str, tracker: "RaceStateTracker") -> str:
    if intent == "fuel":
        fuel = tracker.last_fuel
        if fuel < 0.5:
            return "The tank is empty."
        avg = tracker.avg_fuel_per_lap
        if avg > 0:
            laps = fuel / avg
            lap_word = "lap" if laps < 1.5 else "laps"
            return f"You have {fuel:.1f} liters, about {laps:.1f} {lap_word} remaining."
        return f"You have {fuel:.1f} liters remaining."

    if intent == "position":
        pos   = tracker.last_position
        total = tracker.last_total_cars
        if pos > 0 and total > 0:
            return f"You are P{pos} of {total} cars."
        return "Position is not available."

    if intent == "time":
        rem_ms = tracker.computed_remaining_ms()
        if rem_ms > 0:
            time_str = format_remaining_time_voice(rem_ms)
            best_ms  = tracker.best_lap_ms
            if best_ms > 0:
                est = max(1, math.ceil(rem_ms / best_ms))
                word = "lap" if est == 1 else "laps"
                return (f"You have {time_str} remaining, "
                        f"approximately {est} {word} at your best pace.")
            return f"You have {time_str} remaining."
        if tracker.race_type == RaceType.TIMED:
            return "The timer has expired."
        # Lap race fallback: estimate time from laps remaining × best lap
        if tracker.race_type == RaceType.LAP and tracker.laps_remaining > 0:
            best_ms = tracker.best_lap_ms
            if best_ms > 0:
                est_ms = tracker.laps_remaining * best_ms
                time_str = format_remaining_time_voice(est_ms)
                n = tracker.laps_remaining
                word = "lap" if n == 1 else "laps"
                return (f"Approximately {time_str} remaining "
                        f"based on {n} {word} at your best pace.")
        return "Race time is not available."

    if intent == "laps":
        if tracker.race_type == RaceType.LAP and tracker.laps_in_race > 0:
            n = tracker.laps_remaining
            word = "lap" if n == 1 else "laps"
            return f"You have {n} {word} remaining."
        # Timed race: estimate laps from remaining time / best lap
        rem_ms  = tracker.computed_remaining_ms()
        best_ms = tracker.best_lap_ms
        if rem_ms > 0 and best_ms > 0:
            est = max(1, math.ceil(rem_ms / best_ms))
            word = "lap" if est == 1 else "laps"
            return f"Approximately {est} {word} remaining at your best pace."
        return "Lap count is not available."

    if intent == "best":
        ms = tracker.best_lap_ms
        if ms > 0:
            return f"Your best lap is {format_laptime_voice(ms)}."
        return "No best lap set yet."

    if intent == "tyre_state":
        states = tracker.tyre_states  # dict[str, TyreState]: fl/fr/rl/rr
        if not any(s != TyreState.COLD for s in states.values()):
            return "Tyres are cold. Build temperature before pushing."
        _label = {"fl": "front left", "fr": "front right", "rl": "rear left", "rr": "rear right"}
        _word  = {
            TyreState.COLD:        "cold",
            TyreState.WARMING:     "warming",
            TyreState.OPTIMAL:     "optimal",
            TyreState.HOT:         "hot",
            TyreState.OVERHEATING: "overheating",
        }
        parts = [f"{_label[k]} {_word.get(v, v.value)}" for k, v in states.items()]
        critical = [_label[k] for k, v in states.items() if v == TyreState.OVERHEATING]
        if critical:
            return f"Tyres: {', '.join(parts)}. Watch the {', '.join(critical)}."
        return f"Tyres: {', '.join(parts)}."

    return "Sorry, I did not understand that."


# ---------------------------------------------------------------------------
# Audio capture (sounddevice)
# ---------------------------------------------------------------------------

_RECORD_SAMPLE_RATE = 16000  # fixed rate — works for all common headset mics
# BT HFP takes ~300ms to activate after the stream opens. We record this many
# extra seconds so the warmup is included in the clip; Google finds speech
# wherever it appears rather than us discarding early frames.
_HFP_WARMUP_SECS = 0.35


def _record_audio(duration_secs: float,
                  mic_index: Optional[int],
                  warmup_secs: float = _HFP_WARMUP_SECS) -> Optional[tuple[bytes, int, float]]:
    """Record audio and return (raw_pcm_bytes, sample_rate), or None on error.

    Uses sounddevice.InputStream (streaming) instead of sd.rec() so the BT
    HFP device stays open continuously.  sd.rec() closes and reopens the device
    on every call; reopening HFP takes 300-800 ms during which the buffer is
    silence and the user's first words are lost.  Keeping the stream open
    lets HFP activate during the clip; the warmup frames are passed to the
    recogniser intact — Google finds speech wherever it appears.
    """
    if not _SOUNDDEVICE_OK:
        print("[QueryListener] sounddevice not installed — cannot record audio")
        return None

    try:
        dev_idx  = mic_index if mic_index is not None else int(_sd.default.device[0])  # type: ignore[index]
        dev_info = _sd.query_devices(dev_idx)
        dev_name  = dev_info.get("name", "?")
        max_in_ch = int(dev_info.get("max_input_channels", 0))
    except Exception as e:
        print(f"[QueryListener] device query error: {e}")
        dev_name, max_in_ch = "?", 1

    if max_in_ch == 0:
        print(f"[QueryListener] device [{dev_idx}] '{dev_name}' has no input channels")
        return None
    print(f"[QueryListener] recording via [{dev_idx}] '{dev_name}'")

    sr          = _RECORD_SAMPLE_RATE
    total_secs  = duration_secs + warmup_secs
    target_frames = int(total_secs * sr)
    chunks: list = []
    n_captured  = 0

    def _cb(indata, frames, time_info, status):  # type: ignore[override]
        chunks.append(indata.copy())

    try:
        with _sd.InputStream(samplerate=sr, channels=1, dtype="int16",
                             device=dev_idx, callback=_cb):
            # Block until we have enough frames (stream fills chunks via callback).
            deadline = time.time() + total_secs + 1.0  # +1 s safety margin
            while n_captured < target_frames and time.time() < deadline:
                time.sleep(0.05)
                n_captured = sum(len(c) for c in chunks)
    except Exception as e:
        print(f"[QueryListener] audio record error: {e}")
        return None

    if not chunks:
        print("[QueryListener] no audio captured")
        return None

    flat = _np.concatenate(chunks, axis=0).flatten()
    rms  = float(_np.sqrt(_np.mean(flat.astype(_np.float32) ** 2)))
    print(f"[QueryListener] RMS={rms:.0f} ({total_secs:.1f}s captured)")

    return flat.tobytes(), sr, rms


# ---------------------------------------------------------------------------
# Speech recognition
# ---------------------------------------------------------------------------

_recogniser: Optional["_sr.Recognizer"] = _sr.Recognizer() if _SR_OK else None  # type: ignore[assignment]


def _recognise(audio_bytes: bytes, sample_rate: int, backend: str) -> Optional[str]:
    if not _SR_OK or _recogniser is None:
        print("[QueryListener] SpeechRecognition not installed")
        return None
    audio = _sr.AudioData(audio_bytes, sample_rate=sample_rate, sample_width=2)
    try:
        if backend == "sphinx":
            result = _recogniser.recognize_sphinx(audio).lower()  # type: ignore[attr-defined]
        else:
            result = _recogniser.recognize_google(audio).lower()
        print(f"[QueryListener] recognised text: {result!r}")
        return result
    except _sr.UnknownValueError:
        print("[QueryListener] recognition: Google could not understand audio "
              "(speak clearly into mic, check volume)")
        return None
    except _sr.RequestError as e:
        print(f"[QueryListener] recognition: API error — {e} "
              "(check internet connection; free API key has rate limits)")
        return None
    except Exception as e:
        print(f"[QueryListener] recognition: unexpected error — {e}")
        return None


# ---------------------------------------------------------------------------
# QueryListener thread
# ---------------------------------------------------------------------------

class QueryListener(threading.Thread):
    """Listens for a configured button press and answers spoken queries."""

    def __init__(
        self,
        tracker: "RaceStateTracker",
        announcer: "VoiceAnnouncer",
        config: dict,
        strategy_engine=None,
        driving_advisor=None,
        bridge=None,
    ) -> None:
        super().__init__(daemon=True, name="QueryListener")
        self._tracker          = tracker
        self._announcer        = announcer
        self._config           = config
        self._strategy_engine  = strategy_engine
        self._driving_advisor  = driving_advisor
        self._bridge           = bridge
        self._trigger_queue: queue.Queue = queue.Queue(maxsize=1)
        self._stop_event = threading.Event()
        self._pynput_listener = None
        self._car_specs_ref: dict = {}
        self._active_setup_getter = None
        self._last_live_position = None

    def update_car_specs(self, specs: dict) -> None:
        """Called from dashboard when the active car changes."""
        self._car_specs_ref = specs or {}

    def set_active_setup_getter(self, getter) -> None:
        """Pass a callable that returns the current live setup dict."""
        self._active_setup_getter = getter

    def update_live_position(self, pos) -> None:
        self._last_live_position = pos

    # ------------------------------------------------------------------
    def run(self) -> None:
        self._setup_keyboard_listener()
        self._setup_joystick_poller()
        while not self._stop_event.is_set():
            try:
                item = self._trigger_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if item is None:
                break
            self._handle_trigger()

    def stop(self) -> None:
        self._stop_event.set()
        if self._pynput_listener is not None:
            try:
                self._pynput_listener.stop()
            except Exception:
                pass
        try:
            self._trigger_queue.put_nowait(None)
        except queue.Full:
            pass

    # ------------------------------------------------------------------
    def _setup_keyboard_listener(self) -> None:
        qb = self._config.get("query_button", {})
        if qb.get("type") != "keyboard":
            return
        key_str = qb.get("key", "")
        if not key_str:
            return
        try:
            from pynput import keyboard as _kb

            def on_press(key):
                try:
                    k = key.char if (hasattr(key, "char") and key.char) else key.name
                except Exception:
                    k = str(key)
                if k == key_str:
                    try:
                        self._trigger_queue.put_nowait(True)
                    except queue.Full:
                        pass  # already pending

            self._pynput_listener = _kb.Listener(on_press=on_press)
            self._pynput_listener.start()
            print(f"[QueryListener] keyboard listener active — key: {key_str!r}")
        except ImportError:
            print("[QueryListener] pynput not installed — keyboard detection unavailable")

    def _setup_joystick_poller(self) -> None:
        qb = self._config.get("query_button", {})
        if qb.get("type") != "joystick":
            return
        btn_idx = int(qb.get("button_index", 0))

        def _poll() -> None:
            try:
                import pygame
                pygame.init()
                pygame.joystick.init()
                if pygame.joystick.get_count() == 0:
                    print("[QueryListener] No joystick found")
                    return
                joy = pygame.joystick.Joystick(0)
                joy.init()
                prev_pressed = False
                while not self._stop_event.is_set():
                    pygame.event.pump()
                    pressed = bool(joy.get_button(btn_idx))
                    if pressed and not prev_pressed:
                        try:
                            self._trigger_queue.put_nowait(True)
                        except queue.Full:
                            pass
                    prev_pressed = pressed
                    time.sleep(0.02)
            except ImportError:
                print("[QueryListener] pygame not installed — joystick detection unavailable")
            except Exception as e:
                print(f"[QueryListener] joystick poll error: {e}")

        t = threading.Thread(target=_poll, daemon=True, name="JoystickPoller")
        t.start()

    def _emit_ptt_status(self, status: str) -> None:
        if self._bridge is not None:
            try:
                self._bridge.ptt_status.emit(status)
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _handle_trigger(self) -> None:
        try:
            self._handle_trigger_inner()
        except Exception as _e:
            import traceback
            traceback.print_exc()
            self._emit_ptt_status(f"PTT ERROR: {_e}")
            self._announcer.announce(
                "Radio fault. Please try again.", Priority.HIGH, "query", 0.0, interrupt=True
            )

    def _handle_trigger_inner(self) -> None:
        qc       = self._config.get("query", {})
        duration = float(qc.get("record_secs", 3.0))
        backend  = qc.get("speech_backend", "google")
        mic_idx  = qc.get("mic_index", None)
        bt_mode  = self._config.get("voice", {}).get("bt_mode", False)
        hfp_warmup = _HFP_WARMUP_SECS if bt_mode else 0.0

        # 1. Radio key-down click → UI shows TRANSMITTING.
        self._emit_ptt_status("TRANSMITTING")
        self._announcer.play_click_sync("down")

        # 2. Stop TTS and lock the mute window.
        self._announcer.silence()
        total_mute = duration + hfp_warmup + 1.0
        self._announcer.mute_for(total_mute)
        time.sleep(0.05)  # let purge sentinel execute in announcer thread

        # 3. BT only: suppress keepalive so A2DP can relinquish and HFP can open.
        if bt_mode:
            self._announcer.pause_keepalive(duration + hfp_warmup + 2.0)
            time.sleep(0.15)  # gap while A2DP releases and HFP mic stream opens

        print(f"[QueryListener] recording {duration}s ...")
        result = _record_audio(duration, mic_idx, warmup_secs=hfp_warmup)

        # 4. Radio key-up click → UI shows PROCESSING.
        self._announcer.clear_mute()
        self._announcer.play_click_sync("up")
        self._emit_ptt_status("PROCESSING")

        if result is None:
            self._emit_ptt_status("RADIO READY")
            self._announcer.announce(
                "Microphone error.", Priority.HIGH, "query", 0.0, interrupt=True
            )
            return

        audio_bytes, sample_rate, rms = result
        if rms < 100:
            print("[QueryListener] RMS too low — mic silent, skipping recognition")
            self._emit_ptt_status("RADIO READY")
            return

        text = _recognise(audio_bytes, sample_rate, backend)

        if text is None:
            self._emit_ptt_status("RADIO READY")
            self._announcer.announce(
                "Sorry, I did not catch that.", Priority.HIGH, "query", 0.0, interrupt=True
            )
            return

        # 5. Engineer is about to respond → brief radio carrier click + status update.
        self._emit_ptt_status("ENGINEER RESPONDING")
        self._announcer.play_beep(wav_path="pit_radio.wav", interrupt=False,
                                  mute_bypass=True, priority=0)

        intent = _match_intent(text)
        se = self._strategy_engine
        da = self._driving_advisor
        tr = self._tracker
        if intent == "pit" and se is not None:
            response = se.build_pit_window_response(
                tr.laps_recorded if tr is not None else 0
            )
        elif intent == "pit" and se is None:
            response = "No strategy loaded. Pit when you judge."
        elif intent == "strategy" and se is not None:
            response = se.build_strategy_response()
        elif intent == "pace" and se is not None:
            response = se.build_pace_response()
        elif intent == "rain" and se is not None:
            response = se.handle_rain_report()
        elif intent == "damage" and se is not None:
            response = se.handle_damage_report(text)
        elif intent == "fuel_check" and se is not None:
            response = se.build_fuel_check_response()
        elif intent == "lap_analysis" and da is not None:
            response = da.build_last_lap_response()
        elif intent == "coaching" and da is not None:
            self._announcer.announce(
                "Analysing your data, stand by.",
                Priority.HIGH, "query_coaching_pending", 0.0, interrupt=True)
            _sc = self._config.get("strategy", {})
            _allowed = _sc.get("allowed_tuning_categories", []) or None
            _locked  = not bool(_sc.get("tuning", True))
            _car_name_ql = _sc.get("car", "")
            _car_specs_ql = self._car_specs_ref or {}
            _compound_ql = _sc.get("mandatory_compounds", "") or ""
            response = da.build_coaching_response(
                allowed_tuning=_allowed, tuning_locked=_locked,
                car_name=_car_name_ql, car_specs=_car_specs_ql,
                compound=_compound_ql,
                live_position=self._last_live_position)
        elif intent == "setup_advice" and da is not None:
            self._announcer.announce(
                "Checking your setup, stand by.",
                Priority.HIGH, "query_setup_pending", 0.0, interrupt=True)
            if self._active_setup_getter is not None:
                try:
                    _live_setup = self._active_setup_getter()
                except Exception:
                    _live_setup = {}
            else:
                _fallback_setups = self._config.get("car_setup", {}).get("setups", [{}])
                _live_setup = _fallback_setups[0] if _fallback_setups else {}
            _sc = self._config.get("strategy", {})
            _allowed = _sc.get("allowed_tuning_categories", []) or None
            _locked  = not bool(_sc.get("tuning", True))
            _car_name_ql = _sc.get("car", "")
            _car_specs_ql = self._car_specs_ref or {}
            _compound_ql = _sc.get("mandatory_compounds", "") or ""
            response = da.build_setup_advice_response(
                _live_setup,
                allowed_tuning=_allowed, tuning_locked=_locked,
                car_name=_car_name_ql, car_specs=_car_specs_ql,
                compound=_compound_ql)
        else:
            response = _build_response(intent, self._tracker)
        self._announcer.announce(response, Priority.HIGH, "query", 0.0, interrupt=True)
        self._emit_ptt_status("RADIO READY")
        print(f"[QueryListener] PTT cycle complete — RADIO READY")

    # ------------------------------------------------------------------
    @staticmethod
    def list_microphones() -> list[tuple[int, str]]:
        """Return list of (index, name) for available input devices."""
        try:
            devices = _sd.query_devices()
            return [
                (i, d["name"])
                for i, d in enumerate(devices)
                if d.get("max_input_channels", 0) > 0
            ]
        except Exception:
            return []
