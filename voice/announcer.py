"""Voice announcement engine with a priority queue and per-type cooldowns.

Uses Windows SAPI5 directly via win32com (pywin32) for TTS and audio cues.
pyttsx3's SAPI5 wrapper has a known silent-failure bug on Windows 10/11
where runAndWait() returns without audio after a few calls; win32com with
pythoncom.CoInitialize() in the VoiceAnnouncer thread avoids this entirely.

The SpVoice object MUST live in the VoiceAnnouncer thread — COM STA objects
are not thread-safe.  All beeps are played via sp.Speak() with the SVSFIsXML
<audio src=""> element so they share SAPI5's own audio session, guaranteeing
audibility regardless of the Windows Volume Mixer state of Python.exe.
"""
from __future__ import annotations
import enum
import io
import itertools
import math
import random
import queue
import struct
import tempfile
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from telemetry.packet import (
    format_laptime_voice,
    format_delta_voice,
    format_remaining_time_voice,
)
from telemetry.state import EventType, Priority, RaceType, TelemetryEvent, TyreState

try:
    import sounddevice as _sd
    import numpy as _np
    _SD_OK = True
except ImportError:
    _SD_OK = False

try:
    import winsound as _winsound
    _WINSOUND_OK = True
except ImportError:
    _WINSOUND_OK = False

_beep_wav_cache: dict = {}         # (freq_hz, dur_ms) -> temp WAV file path
_beep_sample_cache: dict = {}      # (freq_hz, dur_ms) -> (float32 stereo ndarray, samplerate)
_wav_sample_cache: dict = {}       # source path -> (float32 stereo ndarray, samplerate)
_wav_prewarm_file_cache: dict = {} # source path -> temp WAV file path (prewarm + audio)
_keepalive_wav_path: str = ""      # path to the near-silent BT keepalive tone
_click_down_wav_path: str = ""     # path to the PTT key-down click WAV for winsound
_click_up_wav_path: str = ""       # path to the PTT key-up click WAV for winsound
_keepalive_paused_until: float = 0.0  # wall-clock time; keepalive skips plays before this
_sapi5_wav_cache: dict = {}        # source path -> SAPI5-compatible temp WAV path
# Single lock for all winsound.PlaySound calls — not thread-safe to call concurrently.
_winsound_lock = threading.Lock()
# Single lock for all _sd.play() calls.
# sounddevice's play() closes any previous stream then starts a new one using
# module-level global state — calling it from two threads simultaneously (e.g.
# the VoiceAnnouncer mid-beep and the QueryListener click cue) is not thread-safe
# and causes a PortAudio SIGSEGV that kills the whole process.  This lock
# serialises every play() call; blocking plays hold it for their full duration
# so the arriving thread simply waits rather than racing.
_sd_play_lock = threading.Lock()

# Set to True if using a Bluetooth headset — enables A2DP prewarm silence,
# BTKeepAlive pulse, and HFP/A2DP contention workarounds.
# False (default) = wired headset: all BT workarounds disabled, direct audio.
_bt_mode: bool = False


def _get_beep_wav(freq_hz: int, dur_ms: int) -> str:
    """Return path to a cached temp WAV file containing a pure-tone beep."""
    key = (freq_hz, dur_ms)
    if key not in _beep_wav_cache:
        sr = 16000
        n = int(sr * dur_ms / 1000)
        buf = bytearray(n * 2)
        for i in range(n):
            v = int(29000 * math.sin(2 * math.pi * freq_hz * i / sr))
            struct.pack_into('<h', buf, i * 2, v)
        wave_buf = io.BytesIO()
        with wave.open(wave_buf, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(bytes(buf))
        tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
        tmp.write(wave_buf.getvalue())
        tmp.close()
        _beep_wav_cache[key] = tmp.name
    return _beep_wav_cache[key]


_BT_PREWARM_MS = 200  # silent frames before the tone to wake Bluetooth A2DP


def _make_keepalive_wav() -> str:
    """Return a cached temp WAV containing a 50ms near-silent 440 Hz tone.

    Played every 1.5 s by the BTKeepAlive thread to prevent BT A2DP from
    entering its power-save sleep state.  At ~-40 dB the tone is inaudible.
    """
    global _keepalive_wav_path
    if _keepalive_wav_path:
        return _keepalive_wav_path
    sr, dur_ms = 44100, 50
    n = int(sr * dur_ms / 1000)
    buf = bytearray(n * 2)
    for i in range(n):
        v = int(3 * math.sin(2 * math.pi * 440 * i / sr))    # 440 Hz, ≈-80 dB (inaudible)
        struct.pack_into('<h', buf, i * 2, v)
    wave_buf = io.BytesIO()
    with wave.open(wave_buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(buf))
    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    tmp.write(wave_buf.getvalue())
    tmp.close()
    _keepalive_wav_path = tmp.name
    return tmp.name


def _make_click_wav(variant: str = "down") -> str:
    """Return cached path to a radio-style PTT click WAV for winsound.

    variant="down" generates a key-down (transmit start) click with pop + static hiss.
    variant="up" generates a shorter key-up (transmit end) click.
    winsound routes via the Windows Audio Session (WASAPI shared mode) —
    same warm path as SAPI5 TTS, no A2DP re-negotiation delay.
    """
    global _click_down_wav_path, _click_up_wav_path
    cached = _click_down_wav_path if variant == "down" else _click_up_wav_path
    if cached:
        return cached
    import random as _rnd
    sr   = 44100
    pre_n = int(sr * 0.03) if _bt_mode else 0  # 30ms pre-silence for BT A2DP session open
    rng  = _rnd.Random(41 if variant == "down" else 43)

    if variant == "down":
        # Radio key-down: sharp broadband pop → brief static hiss → carrier
        n = int(sr * 0.085)  # 85 ms
        buf = bytearray((pre_n + n) * 2)
        for i in range(n):
            t = i / sr
            # Pop: fast-decaying high-freq transient
            pop_env   = math.exp(-t * 90)
            pop       = 0.55 * math.sin(2 * math.pi * 2200 * t) * pop_env
            pop      += 0.25 * math.sin(2 * math.pi * 1100 * t) * pop_env
            # Static burst: bandlimited noise with ADSR (very fast attack, medium decay)
            noise_env = math.exp(-t * 30) * (1 - math.exp(-t * 400))
            noise     = 0.30 * (rng.random() * 2 - 1) * noise_env
            # Carrier tail: low-level tone suggesting open mic
            tail_env  = math.exp(-t * 8) * (1 - math.exp(-t * 200))
            tail      = 0.08 * math.sin(2 * math.pi * 800 * t) * tail_env
            val = int(32767 * max(-1.0, min(1.0, pop + noise + tail)))
            struct.pack_into('<h', buf, (pre_n + i) * 2, val)
    else:
        # Radio key-up: shorter, slightly higher pitch, no carrier tail
        n = int(sr * 0.055)  # 55 ms
        buf = bytearray((pre_n + n) * 2)
        for i in range(n):
            t = i / sr
            pop_env  = math.exp(-t * 130)
            pop      = 0.50 * math.sin(2 * math.pi * 2600 * t) * pop_env
            pop     += 0.20 * math.sin(2 * math.pi * 1300 * t) * pop_env
            noise_env = math.exp(-t * 60) * (1 - math.exp(-t * 600))
            noise     = 0.22 * (rng.random() * 2 - 1) * noise_env
            val = int(32767 * max(-1.0, min(1.0, pop + noise)))
            struct.pack_into('<h', buf, (pre_n + i) * 2, val)

    wave_buf = io.BytesIO()
    with wave.open(wave_buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(bytes(buf))
    tmp = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
    tmp.write(wave_buf.getvalue())
    tmp.close()
    if variant == "down":
        _click_down_wav_path = tmp.name
    else:
        _click_up_wav_path = tmp.name
    return tmp.name


def _get_sapi5_wav(path: str) -> str:
    """Return a SAPI5-compatible temp WAV for the given file path.

    SAPI5 SVSFIsFilename only handles PCM WAV with ≤16-bit depth.
    Converts 24-bit→16-bit and stereo→mono if needed, caches the result.
    Falls back to the original resolved path on error.
    """
    if path in _sapi5_wav_cache:
        return _sapi5_wav_cache[path]
    try:
        with wave.open(path, "rb") as wf:
            params = wf.getparams()
            raw = wf.readframes(wf.getnframes())
        sr, n_ch, sw, nf = params.framerate, params.nchannels, params.sampwidth, params.nframes

        # Convert sample width to 16-bit if needed
        if sw == 3:  # 24-bit PCM → 16-bit
            out = bytearray(nf * n_ch * 2)
            for i in range(nf * n_ch):
                v = int.from_bytes(raw[i*3:i*3+3], "little", signed=True)
                struct.pack_into("<h", out, i*2, max(-32768, min(32767, v >> 8)))
            raw, sw = bytes(out), 2
        elif sw == 1:  # 8-bit unsigned PCM → 16-bit signed
            out = bytearray(nf * n_ch * 2)
            for i in range(nf * n_ch):
                struct.pack_into("<h", out, i*2, (raw[i] - 128) << 8)
            raw, sw = bytes(out), 2

        # Convert stereo → mono (mix L+R) — simplifies SAPI5 format negotiation
        if n_ch == 2:
            n_frames = len(raw) // 4  # 2 bytes × 2 channels
            out = bytearray(n_frames * 2)
            for i in range(n_frames):
                L = struct.unpack_from("<h", raw, i * 4)[0]
                R = struct.unpack_from("<h", raw, i * 4 + 2)[0]
                struct.pack_into("<h", out, i * 2, (L + R) // 2)
            raw, n_ch = bytes(out), 1

        if sw == 2 and n_ch == 1 and path == str(Path(path).resolve()):
            # Already compatible and is an absolute path — no temp file needed
            _sapi5_wav_cache[path] = path
            return path

        wave_buf = io.BytesIO()
        with wave.open(wave_buf, "wb") as wf:
            wf.setnchannels(n_ch)
            wf.setsampwidth(sw)
            wf.setframerate(sr)
            wf.writeframes(raw)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.write(wave_buf.getvalue())
        tmp.close()
        _sapi5_wav_cache[path] = tmp.name
        dur_ms = nf / sr * 1000
        print(f"[VoiceAnnouncer] SAPI5 WAV ready: {path!r} ({dur_ms:.0f}ms, {sr}Hz 16-bit mono)")
        return tmp.name
    except Exception as e:
        print(f"[VoiceAnnouncer] SAPI5 WAV convert error {path!r}: {e} — using original")
        fallback = str(Path(path).resolve())
        _sapi5_wav_cache[path] = fallback
        return fallback


def _load_wav_samples(path: str) -> "tuple[_np.ndarray, int]":
    """Load a WAV file and return (stereo float32 ndarray with BT prewarm, 48000).

    Always resamples to 48000 Hz so it is compatible with WASAPI exclusive-mode
    devices (which require an exact rate match) and matches _get_beep_samples().
    Returns a fallback silent buffer on error.
    """
    if path in _wav_sample_cache:
        return _wav_sample_cache[path]
    sr_out = 48000
    try:
        with wave.open(path, 'rb') as wf:
            sr_in = wf.getframerate()
            n_ch  = wf.getnchannels()
            sw    = wf.getsampwidth()
            raw   = wf.readframes(wf.getnframes())
        if sw == 1:
            pcm = _np.frombuffer(raw, dtype=_np.uint8).astype(_np.float32) / 128.0 - 1.0
        elif sw == 2:
            pcm = _np.frombuffer(raw, dtype=_np.int16).astype(_np.float32) / 32768.0
        else:
            pcm = _np.frombuffer(raw, dtype=_np.int32).astype(_np.float32) / 2147483648.0
        mono = pcm.reshape(-1, n_ch).mean(axis=1) if n_ch > 1 else pcm
        if sr_in != sr_out:
            n_out = int(len(mono) * sr_out / sr_in)
            mono  = _np.interp(
                _np.linspace(0, len(mono) - 1, n_out),
                _np.arange(len(mono)),
                mono,
            ).astype(_np.float32)
        pre_n = int(sr_out * _BT_PREWARM_MS / 1000) if _bt_mode else 0
        buf   = _np.zeros((pre_n + len(mono), 2), dtype=_np.float32)
        buf[pre_n:, 0] = mono
        buf[pre_n:, 1] = mono
        _wav_sample_cache[path] = (buf, sr_out)
        dur_ms = len(mono) / sr_out * 1000
        print(f"[VoiceAnnouncer] loaded WAV {path!r}: {dur_ms:.0f}ms @ {sr_out}Hz (src {sr_in}Hz)")
        return buf, sr_out
    except Exception as e:
        print(f"[VoiceAnnouncer] WAV load error {path!r}: {e}")
        buf = _np.zeros((int(sr_out * 0.3), 2), dtype=_np.float32)
        return buf, sr_out


def _get_wav_prewarm_file(path: str) -> str:
    """Return a temp WAV file with BT prewarm silence prepended (bt_mode only).

    In wired mode (_bt_mode=False) returns the original file path directly —
    no prewarm silence needed since there is no A2DP wake-up delay.
    Keeps the original sample rate / channels / bit-depth so WinMM treats
    it identically to the source file.
    Falls back to the original file path on error.
    """
    if path in _wav_prewarm_file_cache:
        return _wav_prewarm_file_cache[path]
    if not _bt_mode:
        resolved = str(Path(path).resolve())
        _wav_prewarm_file_cache[path] = resolved
        return resolved
    try:
        with wave.open(path, "rb") as wf:
            params = wf.getparams()
            raw    = wf.readframes(wf.getnframes())
        sr, n_ch, sw = params.framerate, params.nchannels, params.sampwidth
        pre_frames = int(sr * _BT_PREWARM_MS / 1000)
        pre_bytes  = bytes(pre_frames * n_ch * sw)   # silence = zeroed bytes
        wave_buf = io.BytesIO()
        with wave.open(wave_buf, "wb") as wf:
            wf.setparams(params)
            wf.writeframes(pre_bytes + raw)
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.write(wave_buf.getvalue())
        tmp.close()
        _wav_prewarm_file_cache[path] = tmp.name
        total_ms = (pre_frames + params.nframes) / sr * 1000
        print(f"[VoiceAnnouncer] prewarm WAV cached: {path!r} -> {tmp.name} ({total_ms:.0f}ms total)")
        return tmp.name
    except Exception as e:
        print(f"[VoiceAnnouncer] prewarm WAV error {path!r}: {e} — using original")
        fallback = str(Path(path).resolve())
        _wav_prewarm_file_cache[path] = fallback
        return fallback


def _run_bt_keepalive(stop_event: threading.Event, interval_secs: float = 1.5) -> None:
    """Play a near-silent 50ms tone every interval_secs to keep BT A2DP from sleeping.

    Without this, BT A2DP enters power-save ~500ms after the last audible output.
    When it wakes the first ~200ms of audio is dropped; the prewarm WAV covers most
    of that, but a warm device is more reliable.  At -40 dB the tone is inaudible.

    Skips playing when _keepalive_paused_until is in the future — PTT recording
    suspends the keepalive so the winsound A2DP pulse does not block HFP mic
    activation (A2DP and HFP are mutually exclusive on most BT headsets).
    """
    path = _make_keepalive_wav()
    while not stop_event.is_set():
        if _WINSOUND_OK and time.time() >= _keepalive_paused_until:
            try:
                with _winsound_lock:
                    _winsound.PlaySound(
                        path,
                        _winsound.SND_FILENAME | _winsound.SND_ASYNC | _winsound.SND_NODEFAULT,
                    )
            except Exception:
                pass
        stop_event.wait(interval_secs)


def _get_beep_samples(freq_hz: int, dur_ms: int) -> "tuple[_np.ndarray, int]":
    """Return cached (float32 stereo ndarray, sample_rate) for a beep.

    In bt_mode, prefixed with _BT_PREWARM_MS of silence so Bluetooth A2DP
    has time to re-activate before the audible tone starts.
    In wired mode, no prewarm — tone plays immediately.
    """
    key = (freq_hz, dur_ms)
    if key not in _beep_sample_cache:
        sr = 48000
        pre_n  = int(sr * _BT_PREWARM_MS / 1000) if _bt_mode else 0
        tone_n = int(sr * dur_ms / 1000)
        buf = _np.zeros((pre_n + tone_n, 2), dtype=_np.float32)
        t    = _np.linspace(0, dur_ms / 1000, tone_n, endpoint=False)
        tone = (0.85 * _np.sin(2 * _np.pi * freq_hz * t)).astype(_np.float32)
        buf[pre_n:, 0] = tone
        buf[pre_n:, 1] = tone
        _beep_sample_cache[key] = (buf, sr)
    return _beep_sample_cache[key]


def _get_click_samples(variant: str = "down") -> "tuple[_np.ndarray, int]":
    """Return cached radio-style click sound for the sounddevice path.

    variant="down": key-down click (pop + static hiss, ~85ms)
    variant="up":   key-up click (shorter pop, ~55ms)
    In bt_mode, prefixed with 300ms prewarm silence for A2DP codec establishment.
    """
    key = f"__click_{variant}__"
    if key not in _beep_sample_cache:
        sr     = 48000
        pre_n  = int(sr * 0.30) if _bt_mode else 0
        rng    = _np.random.default_rng(41 if variant == "down" else 43)

        if variant == "down":
            dur_s  = 0.085
            tone_n = int(sr * dur_s)
            t      = _np.linspace(0, dur_s, tone_n, endpoint=False)
            pop_env   = _np.exp(-t * 90).astype(_np.float32)
            pop       = (0.55 * _np.sin(2 * _np.pi * 2200 * t) * pop_env
                       + 0.25 * _np.sin(2 * _np.pi * 1100 * t) * pop_env).astype(_np.float32)
            noise_env = (_np.exp(-t * 30) * (1 - _np.exp(-t * 400))).astype(_np.float32)
            noise     = (0.30 * (rng.random(tone_n).astype(_np.float32) * 2 - 1) * noise_env)
            tail_env  = (_np.exp(-t * 8) * (1 - _np.exp(-t * 200))).astype(_np.float32)
            tail      = (0.08 * _np.sin(2 * _np.pi * 800 * t) * tail_env).astype(_np.float32)
            mono      = _np.clip(pop + noise + tail, -1.0, 1.0)
        else:
            dur_s  = 0.055
            tone_n = int(sr * dur_s)
            t      = _np.linspace(0, dur_s, tone_n, endpoint=False)
            pop_env   = _np.exp(-t * 130).astype(_np.float32)
            pop       = (0.50 * _np.sin(2 * _np.pi * 2600 * t) * pop_env
                       + 0.20 * _np.sin(2 * _np.pi * 1300 * t) * pop_env).astype(_np.float32)
            noise_env = (_np.exp(-t * 60) * (1 - _np.exp(-t * 600))).astype(_np.float32)
            noise     = (0.22 * (rng.random(tone_n).astype(_np.float32) * 2 - 1) * noise_env)
            mono      = _np.clip(pop + noise, -1.0, 1.0)

        buf = _np.zeros((pre_n + tone_n, 2), dtype=_np.float32)
        buf[pre_n:, 0] = mono
        buf[pre_n:, 1] = mono
        _beep_sample_cache[key] = (buf, sr)
    return _beep_sample_cache[key]


@dataclass(order=False)
class Announcement:
    priority: int
    seq: int
    text: str
    cooldown_key: str
    cooldown_secs: float
    interrupt: bool = False
    # If version_key is set, only speak if _versions[version_key] still equals
    # version_num at speak time — newer announcements for the same key supersede this one.
    version_key: str = ""
    version_num: int = 0
    # Beep-only announcement — plays a WAV tone via SAPI5 <audio> XML element.
    is_beep: bool = False
    # mute_bypass=True lets this item through during a PTT recording mute window.
    # Only PTT control signals should set this; shift beeps leave it False.
    mute_bypass: bool = False
    beep_freq: int = 880
    beep_dur_ms: int = 150
    beep_click: bool = False  # if True, play click sound (ignores beep_freq/beep_dur_ms)
    wav_path: str = ""      # if set, play this WAV file instead of synthesising a tone
    queued_at: float = 0.0  # time.time() when queued; >0 enables staleness check
    max_age_secs: float = 0.0  # discard beep if (now - queued_at) > this; 0 = no limit

    def __lt__(self, other: "Announcement") -> bool:
        return (self.priority, self.seq) < (other.priority, other.seq)


class VoiceAnnouncer(threading.Thread):
    """Daemon thread that owns the SAPI5 engine and speaks announcements."""

    def __init__(self, voice_config: dict) -> None:
        super().__init__(daemon=True, name="VoiceAnnouncer")
        self._cfg = voice_config
        global _bt_mode
        _bt_mode = bool(voice_config.get("bt_mode", False))
        print(f"[VoiceAnnouncer] audio mode: {'Bluetooth' if _bt_mode else 'wired'}")
        self._queue: queue.PriorityQueue[tuple[int, int, Announcement]] = queue.PriorityQueue()
        self._cooldowns: dict[str, float] = {}
        self._versions: dict[str, int] = {}
        self._seq = itertools.count()
        self._stop_event = threading.Event()
        self._wake = threading.Event()
        self._muted_until: float = 0.0
        self._engine = None
        self._beep_dev_eff: Optional[int] = None
        self._session_mode: str = "race"
        self._qualifying_target_ms: int = 0

    # ------------------------------------------------------------------ public

    def announce(self, text: str, priority: Priority, cooldown_key: str,
                 cooldown_secs: float = 0.0, interrupt: bool = False,
                 version_key: str = "") -> None:
        if not self._cfg.get("enabled", True):
            return
        version_num = 0
        if version_key:
            version_num = self._versions.get(version_key, 0) + 1
            self._versions[version_key] = version_num
        n = next(self._seq)
        ann = Announcement(priority.value, n, text, cooldown_key, cooldown_secs,
                           interrupt, version_key, version_num)
        self._queue.put((priority.value, n, ann))

    def get_beep_device(self) -> Optional[int]:
        """Return the effective sounddevice output index for beeps."""
        return self._beep_dev_eff

    def update_config(self, cfg: dict) -> None:
        self._cfg = cfg
        # Re-apply the explicit beep_device setting.  None means "Auto" —
        # clear _beep_dev_eff so subsequent beeps use the sounddevice default.
        cfg_dev = cfg.get("beep_device", None)
        self._beep_dev_eff = int(cfg_dev) if cfg_dev is not None else None

    def test_voice(self) -> None:
        self.announce("Voice test OK.", Priority.INFO, "test", 0.0)

    def play_beep(self, freq_hz: int = 880, duration_ms: int = 150,
                  interrupt: bool = False, mute_bypass: bool = False,
                  wav_path: str = "", priority: int = 0,
                  max_age_secs: float = 0.0, click: bool = False) -> None:
        """Queue a tone through the SAPI5 thread.

        If wav_path is set, plays that WAV file.
        If click=True, plays a short exponentially-decaying click sound.
        Otherwise synthesises a sine-wave tone at freq_hz / duration_ms.
        interrupt=True   — purge current TTS and play immediately.
        mute_bypass=True — play even during a PTT recording mute window.
        priority         — queue priority (0=immediate, use Priority.X values).
        max_age_secs     — discard beep if it waits longer than this in the queue.
        """
        n = next(self._seq)
        ann = Announcement(
            priority=priority, seq=n, text="", cooldown_key="__beep__",
            cooldown_secs=0.0, interrupt=interrupt,
            is_beep=True, mute_bypass=mute_bypass,
            beep_freq=freq_hz, beep_dur_ms=duration_ms,
            beep_click=click,
            wav_path=wav_path,
            queued_at=time.time(),
            max_age_secs=max_age_secs,
        )
        self._queue.put((priority, n, ann))
        self._wake.set()

    def silence(self) -> None:
        """Stop any current speech and clear pending announcements."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        n = next(self._seq)
        ann = Announcement(
            priority=0, seq=n, text="", cooldown_key="__silence__",
            cooldown_secs=0.0, interrupt=True,
            is_beep=True, mute_bypass=True,
            beep_freq=0, beep_dur_ms=0,
        )
        self._queue.put((0, n, ann))
        self._wake.set()

    def set_session_mode(self, mode: str) -> None:
        """Set the current session mode so event handlers can suppress mode-inappropriate alerts."""
        self._session_mode = mode.lower()
        if mode.lower() != "qualifying" and hasattr(self, "_handler"):
            self._handler._qualifying_lap_count = 0

    def set_qualifying_target_ms(self, ms: int) -> None:
        self._qualifying_target_ms = max(0, int(ms))

    def mute_for(self, secs: float) -> None:
        """Hold all non-bypass queued items for `secs` seconds (PTT recording window)."""
        self._muted_until = time.time() + secs

    def clear_mute(self) -> None:
        """End the recording mute immediately."""
        self._muted_until = 0.0
        self._wake.set()

    def play_click_sync(self, variant: str = "down") -> None:
        """Play the PTT radio click via winsound — thread-safe, zero WASAPI re-init cost.

        variant="down" plays the key-down (transmit start) click.
        variant="up"   plays the key-up (transmit end) click.
        winsound routes through the Windows Audio Session (WASAPI shared mode),
        the same always-warm path used by SAPI5 TTS.  Unlike sounddevice, it does
        not open a new exclusive WASAPI stream, so there is no A2DP codec
        re-negotiation delay.  Safe to call from any thread (guarded by _winsound_lock).
        Falls back to sounddevice if winsound is unavailable (non-Windows).
        """
        if _WINSOUND_OK:
            t0 = time.monotonic()
            wav = _make_click_wav(variant)
            with _winsound_lock:
                _winsound.PlaySound(wav, _winsound.SND_FILENAME)
            print(f"[VoiceAnnouncer] click({variant}) via winsound ({(time.monotonic() - t0) * 1000:.0f} ms)")
        elif _SD_OK:
            samples, sr = _get_click_samples(variant)
            t0 = time.monotonic()
            with _sd_play_lock:
                try:
                    _sd.play(samples, sr, blocking=True)
                except Exception as e:
                    print(f"[VoiceAnnouncer] click sd error: {e}")
            print(f"[VoiceAnnouncer] click via sd ({(time.monotonic() - t0) * 1000:.0f} ms)")

    def play_beep_direct(self) -> bool:
        """Play rpm.wav immediately via winsound async — bypasses the SAPI5 queue."""
        if not _WINSOUND_OK:
            print("[ShiftBeep] play_beep_direct: winsound not available")
            return False
        wav = _get_wav_prewarm_file("rpm.wav")
        if not wav or not Path(wav).exists():
            print(f"[ShiftBeep] play_beep_direct: wav not found ({wav!r})")
            return False
        try:
            with _winsound_lock:
                _winsound.PlaySound(
                    wav,
                    _winsound.SND_FILENAME | _winsound.SND_ASYNC | _winsound.SND_NODEFAULT,
                )
            print(f"[ShiftBeep] winsound ok ({Path(wav).name})")
        except Exception as e:
            print(f"[VoiceAnnouncer] play_beep_direct error: {e}")
            return False
        return True

    def pause_keepalive(self, secs: float) -> None:
        """Suppress the BT A2DP keepalive for `secs` seconds.

        Called by QueryListener before PTT recording so the winsound keepalive
        pulse does not keep A2DP active while the HFP mic InputStream is open.
        A2DP and HFP are mutually exclusive on most BT headsets; an A2DP pulse
        during HFP activation causes the mic to capture silence (RMS=0).
        """
        global _keepalive_paused_until
        _keepalive_paused_until = time.time() + secs

    @property
    def queue_depth(self) -> int:
        """Approximate number of pending announcements (for debug display)."""
        return self._queue.qsize()

    @property
    def muted_until(self) -> float:
        """Monotonic time until which non-bypass announcements are held; 0 = not muted."""
        return self._muted_until

    def stop(self) -> None:
        self._stop_event.set()
        try:
            self._queue.put_nowait((0, -1, None))  # type: ignore[arg-type]
        except Exception:
            pass

    def list_voices(self) -> list[tuple[str, str]]:
        """Return list of (id, name) for available SAPI5 voices."""
        try:
            import win32com.client, pythoncom
            pythoncom.CoInitialize()
            sp = win32com.client.Dispatch("SAPI.SpVoice")
            vlist = sp.GetVoices()
            result = [(vlist.Item(i).Id, vlist.Item(i).GetDescription())
                      for i in range(vlist.Count)]
            pythoncom.CoUninitialize()
            return result
        except Exception:
            pass
        try:
            import pyttsx3
            eng = pyttsx3.init()
            voices = eng.getProperty("voices")
            result = [(v.id, v.name) for v in voices]
            eng.stop()
            return result
        except Exception:
            return []

    # -------------------------------------------------------------------- run

    def run(self) -> None:
        try:
            import win32com.client
            import pythoncom
        except ImportError:
            self._run_pyttsx3()
            return

        pythoncom.CoInitialize()
        try:
            self._run_sapi5(win32com.client)
        finally:
            pythoncom.CoUninitialize()

    def _apply_sapi5_cfg(self, sp, cfg: dict) -> None:
        wpm = int(cfg.get("rate", 175))
        sp.Rate   = max(-10, min(10, round((wpm - 200) / 20)))
        sp.Volume = int(float(cfg.get("volume", 1.0)) * 100)
        vid = cfg.get("voice_id", "")
        if vid:
            try:
                vlist = sp.GetVoices()
                for i in range(vlist.Count):
                    v = vlist.Item(i)
                    if vid in v.Id or v.Id in vid:
                        sp.Voice = v
                        break
            except Exception:
                pass

    def _run_sapi5(self, win32com_client) -> None:
        try:
            sp = win32com_client.Dispatch("SAPI.SpVoice")
        except Exception as e:
            print(f"[VoiceAnnouncer] SAPI5 init failed: {e} — trying pyttsx3")
            self._run_pyttsx3()
            return

        self._apply_sapi5_cfg(sp, self._cfg)
        self._engine = sp

        # Pre-generate/load audio so first trigger has no I/O delay.
        _get_beep_wav(440, 300)
        _get_beep_wav(550, 150)
        for _wname in ("rpm.wav", "pit_radio.wav"):
            _get_wav_prewarm_file(_wname)  # pre-generate 200ms-silence prewarm WAV for winsound
        _get_beep_wav(440, 100)
        if _SD_OK:
            _get_click_samples("down")
            _get_click_samples("up")
        if _WINSOUND_OK:
            _make_click_wav("down")
            _make_click_wav("up")
        if _WINSOUND_OK and _bt_mode:
            _make_keepalive_wav()
            _make_click_wav()
            _ka_stop = threading.Event()
            threading.Thread(
                target=_run_bt_keepalive, args=(_ka_stop,),
                daemon=True, name="BTKeepAlive",
            ).start()
            print("[VoiceAnnouncer] BT A2DP keepalive started (1.5 s interval)")
        elif _WINSOUND_OK:
            _make_click_wav()   # pre-generate PTT click WAV so first press has no I/O delay
            _ka_stop = None
            print("[VoiceAnnouncer] wired mode — BT keepalive disabled")
        else:
            _ka_stop = None

        print("[VoiceAnnouncer] SAPI5 ready")

        if _SD_OK:
            try:
                all_devs = _sd.query_devices()
                default_out = _sd.default.device[1]
                print("[VoiceAnnouncer] sounddevice output devices:")
                for i, d in enumerate(all_devs):
                    if d.get("max_output_channels", 0) > 0:
                        marker = " *" if i == default_out else ""
                        print(f"  [{i}] {d['name']}{marker}")
            except Exception as e:
                print(f"[VoiceAnnouncer] sounddevice device list error: {e}")

        # Determine the effective beep output device without persisting it to config.
        # config "beep_device" is an explicit user override; if unset, auto-detect the
        # WASAPI default so beeps match the SAPI5 TTS audio path on BT headsets.
        # We intentionally do NOT write the auto-detected index back to self._cfg —
        # device indices are ephemeral and would become stale if the device list changes.
        cfg_dev = self._cfg.get("beep_device", None)
        if cfg_dev is not None:
            self._beep_dev_eff = int(cfg_dev)
            print(f"[VoiceAnnouncer] beep_device override: {cfg_dev}")
        elif _SD_OK:
            try:
                apis = _sd.query_hostapis()
                wasapi = next((a for a in apis if "WASAPI" in a.get("name", "")), None)
                if wasapi and wasapi.get("default_output_device", -1) >= 0:
                    dev_idx  = int(wasapi["default_output_device"])
                    dev_name = _sd.query_devices(dev_idx).get("name", "?")
                    self._beep_dev_eff = dev_idx
                    print(f"[VoiceAnnouncer] WASAPI auto-select: [{dev_idx}] '{dev_name}'")
            except Exception as e:
                print(f"[VoiceAnnouncer] WASAPI auto-select error: {e}")

        try:
            print("[VoiceAnnouncer] startup greeting speaking...")
            sp.Speak("Welcome to Next Gear Racing Pit Crew.", 1)  # SVSFlagsAsync=1
            # Wait on _stop_event (not _wake) so queued telemetry events cannot
            # wake us early and purge the greeting via interrupt=True.
            self._stop_event.wait(timeout=2.8)
        except Exception as e:
            print(f"[VoiceAnnouncer] startup message failed: {e}")

        # SVSFlagsAsync=1: fire-and-forget. SVSFPurgeBeforeSpeak=2: cancel current speech.
        # WaitUntilDone is avoided — in a COM STA thread with no message pump it can
        # deadlock waiting for a completion callback that never drains.  Instead we
        # sleep for an estimated duration; _wake lets shift beeps interrupt early.
        _ASYNC = 1
        _PURGE = 2
        # Items queued during PTT recording are held here; flushed when mute expires.
        _pending: list[tuple[int, int, Announcement]] = []

        while not self._stop_event.is_set():
            if _pending and time.time() >= self._muted_until:
                for item in _pending:
                    _, _, a = item
                    if not a.is_beep:  # discard stale shift beeps — they're time-critical and now stale
                        self._queue.put(item)
                _pending.clear()

            try:
                _, _, ann = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue

            if ann is None:
                break

            if time.time() < self._muted_until and not ann.mute_bypass:
                label = ann.wav_path or (f"beep {ann.beep_freq}Hz" if ann.is_beep else ann.text[:40])
                print(f"[VoiceAnnouncer] held (mute {self._muted_until - time.time():.1f}s): {label!r}")
                _pending.append((ann.priority, ann.seq, ann))
                continue

            if ann.is_beep:
                try:
                    if (ann.max_age_secs > 0
                            and ann.queued_at > 0
                            and time.time() - ann.queued_at > ann.max_age_secs):
                        print(f"[VoiceAnnouncer] beep discarded (stale by "
                              f"{time.time() - ann.queued_at:.2f}s): {ann.wav_path or ann.beep_freq}Hz")
                        continue
                    has_audio = ann.wav_path or ann.beep_click or (ann.beep_freq > 0 and ann.beep_dur_ms > 0)
                    if has_audio:
                        if ann.wav_path:
                            # is_async=True for RPM beeps (interrupt+no mute_bypass);
                            # is_async=False for PTT cues (interrupt+mute_bypass).
                            is_async = ann.interrupt and not ann.mute_bypass
                            beep_dev = self._beep_dev_eff

                            # For sync (PTT cue): purge TTS before the blocking play so the
                            # cue replaces speech cleanly.  For async (RPM beep): defer the
                            # purge until AFTER a successful play — if the device is missing
                            # and play fails, the purge must NOT fire or it silently kills the
                            # current TTS (e.g. lap-delta mid-sentence) with nothing to replace it.
                            if ann.interrupt and not is_async:
                                sp.Speak("", _PURGE | _ASYNC)

                            play_ok = False
                            via = "unavailable"
                            if _SD_OK:
                                samples, sr = _load_wav_samples(ann.wav_path)
                                # Try configured device first; fall back to sounddevice default
                                # when the headset is disconnected or the device index shifted.
                                devs = [beep_dev, None] if beep_dev is not None else [None]
                                with _sd_play_lock:
                                    for _dev in devs:
                                        try:
                                            _sd.play(samples, sr, device=_dev,
                                                     blocking=not is_async)
                                            play_ok = True
                                            via = f"sd[{_dev}]"
                                            if _dev != beep_dev:
                                                print(f"[VoiceAnnouncer] beep_device {beep_dev} "
                                                      f"unavailable — using default")
                                            break
                                        except Exception as _e:
                                            if _dev is devs[-1]:
                                                print(f"[VoiceAnnouncer] beep error: {_e}")
                            elif _WINSOUND_OK:
                                prewarm_wav = _get_wav_prewarm_file(ann.wav_path)
                                wflags = _winsound.SND_FILENAME | (
                                    _winsound.SND_ASYNC if is_async else 0
                                )
                                with _winsound_lock:
                                    _winsound.PlaySound(prewarm_wav, wflags)
                                play_ok = True
                                via = "winsound"

                            # For async beeps: purge TTS now that we know audio is playing.
                            # If play failed, skip the purge so TTS continues uninterrupted.
                            if ann.interrupt and is_async and play_ok:
                                sp.Speak("", _PURGE | _ASYNC)

                            if play_ok:
                                print(f"[VoiceAnnouncer] WAV {ann.wav_path!r} via {via} async={is_async}")
                        else:
                            if ann.interrupt:
                                sp.Speak("", _PURGE | _ASYNC)  # stop current TTS
                            if self._cfg.get("beep_use_tts", False):
                                if ann.beep_click:
                                    word = "click"
                                else:
                                    word = {
                                        (440, 300): "go",
                                        (550, 150): "done",
                                    }.get((ann.beep_freq, ann.beep_dur_ms), "shift")
                                sp.Speak(word, _ASYNC)
                                dur = 0.08 if ann.beep_click else ann.beep_dur_ms / 1000.0
                                time.sleep(dur + 0.15)
                                print(f"[VoiceAnnouncer] beep TTS {'click' if ann.beep_click else f'{ann.beep_freq}Hz {ann.beep_dur_ms}ms'}")
                            elif _SD_OK:
                                if ann.beep_click:
                                    samples, sr = _get_click_samples()
                                else:
                                    samples, sr = _get_beep_samples(ann.beep_freq, ann.beep_dur_ms)
                                beep_dev = self._beep_dev_eff
                                devs = [beep_dev, None] if beep_dev is not None else [None]
                                t0 = time.monotonic()
                                with _sd_play_lock:
                                    for _dev in devs:
                                        try:
                                            _sd.play(samples, sr, device=_dev, blocking=True)
                                            if _dev != beep_dev:
                                                print(f"[VoiceAnnouncer] beep_device {beep_dev} "
                                                      f"unavailable — using default")
                                            break
                                        except Exception as _e:
                                            if _dev is devs[-1]:
                                                print(f"[VoiceAnnouncer] beep error: {_e}")
                                elapsed_ms = (time.monotonic() - t0) * 1000
                                expected_ms = (400 if ann.beep_click else ann.beep_dur_ms + _BT_PREWARM_MS)
                                if elapsed_ms < expected_ms * 0.5:
                                    print(f"[VoiceAnnouncer] sounddevice returned in {elapsed_ms:.0f}ms "
                                          f"(expected ~{expected_ms}ms) — "
                                          f"check Python.exe volume in Windows Volume Mixer")
                                label = "click" if ann.beep_click else f"{ann.beep_freq}Hz {ann.beep_dur_ms}ms"
                                print(f"[VoiceAnnouncer] beep {label} ({elapsed_ms:.0f}ms)")
                            else:
                                sp.Speak(_get_beep_wav(ann.beep_freq, ann.beep_dur_ms), 4)
                                print(f"[VoiceAnnouncer] beep {ann.beep_freq}Hz {ann.beep_dur_ms}ms")
                    elif ann.interrupt:
                        sp.Speak("", _PURGE | _ASYNC)  # silence sentinel: purge TTS
                        # Do NOT call _sd.stop() here.  Stopping the sounddevice
                        # WASAPI stream forces BT A2DP to re-negotiate its codec
                        # connection (~200-400 ms), which swallows the click cue's
                        # prewarm silence and makes the tone inaudible.  Async shift
                        # beeps are only 160 ms and are cancelled automatically by the
                        # next _sd.play() call; explicit stop is not needed.
                        if _WINSOUND_OK:  # cancel any async winsound keepalive pulse
                            with _winsound_lock:
                                _winsound.PlaySound(None, _winsound.SND_PURGE)
                except Exception as e:
                    print(f"[VoiceAnnouncer] beep error: {e}")
                continue

            if not self._cfg.get("enabled", True):
                continue

            if self._is_stale(ann):
                print(f"[VoiceAnnouncer] stale  key={ann.version_key!r}: {ann.text[:50]!r}")
                continue
            if self._on_cooldown(ann.cooldown_key):
                remaining = self._cooldowns.get(ann.cooldown_key, 0) - time.monotonic()
                print(f"[VoiceAnnouncer] cooldown '{ann.cooldown_key}' ({remaining:.0f}s left): {ann.text[:50]!r}")
                continue

            try:
                self._apply_sapi5_cfg(sp, self._cfg)
                purge_flag = _PURGE if ann.interrupt else 0
                print(f"[VoiceAnnouncer] speak  key={ann.cooldown_key!r} interrupt={ann.interrupt}: {ann.text!r}")
                sp.Speak(ann.text, purge_flag | _ASYNC)
                rate_wpm = max(int(self._cfg.get("rate", 175)), 50)
                words    = len(ann.text.split())
                est_secs = min((words / rate_wpm) * 60.0 + 0.3, 12.0)
                self._wake.wait(timeout=est_secs)
                self._wake.clear()
            except Exception as e:
                print(f"[VoiceAnnouncer] speak error: {e}")

            if ann.cooldown_secs > 0:
                self._cooldowns[ann.cooldown_key] = time.monotonic() + ann.cooldown_secs

        if _ka_stop is not None:
            _ka_stop.set()
        print("[VoiceAnnouncer] SAPI5 loop exited")

    def _run_pyttsx3(self) -> None:
        try:
            import pyttsx3
        except ImportError:
            print("[VoiceAnnouncer] pyttsx3 not installed and win32com unavailable — voice disabled")
            return

        try:
            eng = pyttsx3.init()
        except Exception as e:
            print(f"[VoiceAnnouncer] pyttsx3 init failed: {e}")
            return

        self._engine = eng
        eng.setProperty("rate", int(self._cfg.get("rate", 175)))
        eng.setProperty("volume", float(self._cfg.get("volume", 1.0)))
        vid = self._cfg.get("voice_id", "")
        if vid:
            try:
                eng.setProperty("voice", vid)
            except Exception:
                pass

        print("[VoiceAnnouncer] pyttsx3 ready")
        try:
            eng.say("Welcome to Next Gear Racing Pit Crew.")
            eng.runAndWait()
        except Exception as e:
            print(f"[VoiceAnnouncer] startup message failed: {e}")

        while not self._stop_event.is_set():
            try:
                _, _, ann = self._queue.get(timeout=0.3)
            except queue.Empty:
                continue

            if ann is None:
                break

            if not self._cfg.get("enabled", True):
                continue

            if self._is_stale(ann) or self._on_cooldown(ann.cooldown_key):
                continue

            if ann.interrupt:
                try:
                    eng.stop()
                except Exception:
                    pass

            try:
                eng.say(ann.text)
                eng.runAndWait()
            except Exception as e:
                print(f"[VoiceAnnouncer] speak error: {e}")

            if ann.cooldown_secs > 0:
                self._cooldowns[ann.cooldown_key] = time.monotonic() + ann.cooldown_secs

        try:
            eng.stop()
        except Exception:
            pass

    def _on_cooldown(self, key: str) -> bool:
        expiry = self._cooldowns.get(key, 0.0)
        return time.monotonic() < expiry

    def _is_stale(self, ann: "Announcement") -> bool:
        if not ann.version_key:
            return False
        return self._versions.get(ann.version_key, 0) > ann.version_num


# ---------------------------------------------------------------------------
# Event handler — translates TelemetryEvents into Announcements
# ---------------------------------------------------------------------------

class AnnouncerEventHandler:
    """Converts TelemetryEvent objects into voice announcements."""

    def __init__(self, announcer: VoiceAnnouncer) -> None:
        self._a = announcer
        self._qualifying_lap_count: int = 0

    def _is_flying_lap(self) -> bool:
        return self._a._session_mode == "qualifying" and self._qualifying_lap_count >= 1

    def handle(self, event: TelemetryEvent) -> None:
        cfg = self._a._cfg
        t = event.type

        if t == EventType.LAP_COMPLETED and cfg.get("lap_alerts", True):
            self._on_lap(event.data)

        elif t == EventType.POSITION_CHANGED and cfg.get("position_alerts", True):
            self._on_position(event.data)

        elif t == EventType.TYRE_STATE and cfg.get("tyre_alerts", True):
            self._on_tyre(event.data)

        elif t == EventType.PIT_ENTRY and cfg.get("fuel_alerts", True):
            self._on_pit(event.data)

        elif t == EventType.FUEL_LOW and cfg.get("fuel_alerts", True):
            self._on_fuel_low(event.data)

        elif t == EventType.RACE_STARTED:
            self._on_race_start(event.data)

        elif t == EventType.PIT_EXIT and event.data.get("session_type") == "qualifying":
            self._on_qualifying_outlap()

        elif t == EventType.RACE_FINISHED:
            self._on_race_finish(event.data)

    # --- lap ---

    def _on_lap(self, data: dict) -> None:
        record   = data["record"]
        lap_n    = record.lap_num
        has_best = data["has_best"]

        if not has_best:
            text = "Personal best."
        elif record.delta_ms != 0:
            text = format_delta_voice(record.delta_ms) + " from best."
        else:
            text = "Matched best lap."

        self._a.announce(text, Priority.LOW, f"lap_{lap_n}", 0.0)

        if self._a._session_mode == "qualifying":
            self._qualifying_lap_count += 1
            record = data.get("record")
            lap_ms = getattr(record, "lap_time_ms", 0) if record else 0
            target_ms = self._a._qualifying_target_ms

            if lap_ms > 0 and target_ms > 0:
                # AC4: manual target takes precedence — no lap-count gate, fires every lap.
                delta_ms = lap_ms - target_ms
                abs_sec = abs(delta_ms) / 1000.0
                delta_str = f"{abs_sec:.3f}s"
                if delta_ms < 0:
                    phrase = f"Lap complete. {delta_str} under target."
                elif delta_ms > 0:
                    phrase = f"Lap complete. {delta_str} over target."
                else:
                    phrase = "Lap complete. On target."
                self._a.announce(phrase, Priority.LOW, "qual_lap_delta", 0.0)

            elif lap_ms > 0 and self._qualifying_lap_count >= 3:
                # AC3: no manual target — use best lap of the current session as reference.
                # Lap 1 (out-lap) and lap 2 (first timed lap, no prior reference) are silent.
                # DECISION B5: first spoken delta is lap 3+.
                best_ms = data.get("best_lap_ms", 0)
                # AC6: if no valid best lap is available, say nothing.
                if best_ms and best_ms > 0:
                    delta_ms = lap_ms - best_ms
                    abs_sec = abs(delta_ms) / 1000.0
                    delta_str = f"{abs_sec:.3f}s"
                    if delta_ms < 0:
                        phrase = f"Lap complete. {delta_str} under target."
                    elif delta_ms > 0:
                        phrase = f"Lap complete. {delta_str} over target."
                    else:
                        phrase = "Lap complete. On target."
                    self._a.announce(phrase, Priority.LOW, "qual_lap_delta", 0.0)

        laps_rem = data.get("laps_remaining", 0)
        if laps_rem == 1:
            self._a.announce("Last lap.", Priority.LOW, "last_lap", 0.0)

        if self._a._cfg.get("countdown_alerts", True):
            laps_rem = data.get("laps_remaining", 0)
            rem_ms   = data.get("remaining_time_ms", -1)

            if laps_rem > 0:
                lap_word = "lap" if laps_rem == 1 else "laps"
                countdown = f"{laps_rem} {lap_word} remaining."
                self._a.announce(countdown, Priority.LOW, "countdown", 2.0)
            elif rem_ms > 0:
                best_ms_val = data.get("best_lap_ms", 0)
                if best_ms_val > 0:
                    laps_left = max(1, math.ceil(rem_ms / best_ms_val))
                    lap_word  = "lap" if laps_left == 1 else "laps"
                    countdown = f"About {laps_left} {lap_word} remaining."
                else:
                    countdown = format_remaining_time_voice(rem_ms) + " remaining."
                self._a.announce(countdown, Priority.LOW, "countdown", 2.0)

    # --- position ---

    def _on_position(self, data: dict) -> None:
        pos    = data["position"]
        gained = data["gained"]
        verb   = "gained a position" if gained else "lost a position"
        text   = f"P{pos}, {verb}."
        key    = "pos_gain" if gained else "pos_lost"
        self._a.announce(text, Priority.HIGH, key, 5.0, version_key="position")

    # --- tyres ---

    _STATE_WORDS: dict[TyreState, str] = {
        TyreState.COLD:        "cold",
        TyreState.WARMING:     "warming up",
        TyreState.OPTIMAL:     "optimal",
        TyreState.HOT:         "getting hot",
        TyreState.OVERHEATING: "overheating",
    }

    def _on_tyre(self, data: dict) -> None:
        if self._is_flying_lap():
            return
        label     = data["label"]
        new_state = data["new_state"]
        word      = self._STATE_WORDS.get(new_state, new_state.value)
        text = f"{label.capitalize()} {word}."

        if new_state in (TyreState.HOT, TyreState.OVERHEATING):
            # Single shared key: prevents four individual "X tyre getting hot" calls
            # in a braking zone; only the first one announces within the cooldown.
            cooldown_key = "tyre_hot_urgent"
            cooldown     = 90.0
        else:
            group_slug   = label.replace(" ", "_")
            cooldown_key = f"tyre_{group_slug}_optimal"
            cooldown     = 120.0

        self._a.announce(text, Priority.MEDIUM, cooldown_key, cooldown,
                         version_key="tyre_status")

    # --- pit ---

    def _on_pit(self, data: dict) -> None:
        if getattr(self._a, "_session_mode", "race") in ("practice", "qualifying"):
            return  # no pit fuel instructions outside race sessions
        target   = data.get("fuel_target", 0.0)
        at_entry = data.get("fuel_at_entry", 0.0)

        if target > at_entry:
            # GT7 pit UI expects the total target level, not how much to add.
            text = f"Fuel to {math.ceil(target)} liters."
        elif target > 0:
            text = "Fuel OK, no refuel needed."
        else:
            text = "Pit stop."
        self._a.announce(text, Priority.CRITICAL, "pit_fuel", 30.0, interrupt=True)

    # --- fuel low ---

    def _on_fuel_low(self, data: dict) -> None:
        if getattr(self._a, "_session_mode", "race") in ("practice", "qualifying"):
            return  # fuel burn is informational outside race sessions; don't speak pit advice
        laps_rem = data.get("laps_remaining", 0)
        if laps_rem > 0 and laps_rem <= 2:
            return  # lap race almost over — skip fuel warning
        fuel_laps = data["fuel_laps"]
        tenths = round(fuel_laps * 10) / 10
        word = "lap" if tenths < 1.5 else "laps"
        text = f"{tenths:.1f} {word} of fuel remaining. Consider pitting."
        self._a.announce(text, Priority.LOW, "fuel_low", 0.0)

    # --- race finish ---

    def _on_race_finish(self, data: dict) -> None:
        if getattr(self._a, "_session_mode", "race") != "race":
            return  # race-finished announcement only fires in Race mode
        pos = data.get("position", 0)
        if pos == 1:
            text = "Race finished. First place! Congratulations, you won!"
        elif pos == 2:
            text = "Race finished. Second place — great podium result!"
        elif pos == 3:
            text = "Race finished. Third place — you made the podium!"
        elif 4 <= pos <= 6:
            pos_words = {4: "fourth", 5: "fifth", 6: "sixth"}
            text = f"Race finished. {pos_words[pos].capitalize()} place — so close, better luck next time."
        elif pos >= 7:
            text = f"Race finished. P{pos}. Keep practicing, you'll get there."
        else:
            text = "Race finished."
        self._a.announce(text, Priority.HIGH, "race_finished", 0.0)

    # --- qualifying out-lap ---

    _OUTLAP_PHRASES = [
        "Breathe. Build tyre temperature. No need to rush this out lap.",
        "Take it easy. Let the tyres come in. Smooth is fast here.",
        "Relax. Focus on clean exits. The lap starts when the tyres are ready.",
    ]

    def _on_qualifying_outlap(self) -> None:
        text = random.choice(self._OUTLAP_PHRASES)
        self._a.announce(text, Priority.LOW, "qual_outlap", 0.0)

    # --- race start ---

    def _on_race_start(self, data: dict) -> None:
        # In qualifying the engine already fires "Qualifying session started." —
        # suppress this handler's "Race started." so the driver does not hear both.
        # Matches the guard pattern used by _on_pit, _on_fuel_low, and _on_race_finish.
        # Practice mode is intentionally left unchanged (driver hears "Race started.").
        if getattr(self._a, "_session_mode", "race") == "qualifying":
            return
        race_type = data.get("race_type", RaceType.UNKNOWN)
        laps      = data.get("laps_in_race", 0)
        rem_ms    = data.get("remaining_time_ms", -1)

        if race_type == RaceType.LAP and laps > 0:
            text = f"Race started. {laps} lap{'s' if laps != 1 else ''}."
        elif race_type == RaceType.TIMED and rem_ms > 0:
            text = f"Race started. {format_remaining_time_voice(rem_ms)}."
        else:
            text = "Race started."
        self._a.announce(text, Priority.HIGH, "race_started", 0.0)
