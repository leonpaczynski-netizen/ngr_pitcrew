"""Offline Windows SAPI command-grammar recognition for the live PTT path (UAT-8).

Why this exists
---------------
The live push-to-talk recogniser (``voice/query_listener.py``) transcribes a recorded
clip with PocketSphinx keyword-spotting. For a small, FIXED command set that recogniser
is the wrong tool: ~72% of the vocabulary sits at PocketSphinx's strictest spotting
thresholds and is effectively un-spottable, so the driver hears "Say again" almost
every time. SAPI's command-and-control **grammar** recognition is built for exactly this
job — a closed set of phrases — and is far more reliable per phrase.

This module recognises the SAME recorded WAV clip QueryListener already captures against
a command grammar built from the app's own command phrases, and returns the recognised
phrase for the existing intent matcher to classify. It is wired as the PRIMARY recogniser
with PocketSphinx kept as the fallback (see ``query_listener._recognise``), so a machine
where SAPI is unavailable is never worse off than before.

Properties: fully offline (in-process SAPI, no network, no cloud); persists no raw audio
beyond a short-lived temp WAV it deletes; lazy ``win32com`` import so importing on a
non-Windows box never fails; broad try/except so a COM hiccup returns ``None`` and the
caller falls back rather than crashing the radio.

HONEST LIMITATION: SAPI recognition reliability varies by machine and installed language
pack, and this path has not been validated on the physical PSVR2/GT7 microphone rig — it
must be confirmed there. It is never presented as certified.
"""

from __future__ import annotations

import os
import tempfile
import threading
import wave
from typing import List, Optional


# SAPI SpFileStream open mode: read.
_SSFM_OPEN_FOR_READ = 0
# Grammar rule attributes: TopLevel (0x1) | Dynamic (0x20).
_SPRAF_TOP_LEVEL = 0x1
_SPRAF_DYNAMIC = 0x20
_RULE_NAME = "ngr_ptt_commands"

# One recogniser + grammar per process, built lazily on the calling (PTT) thread.
_LOCK = threading.Lock()
_STATE: dict = {"built": False, "failed": False, "recognizer": None,
                "context": None, "grammar": None, "handler": None, "com_ready": False}


def _command_phrases() -> List[str]:
    """The phrases the grammar recognises — the app's own command vocabulary.

    Uses ``candidate_phrases`` (NOT ``keyword_entries``): the PocketSphinx pronunciation
    dictionary gate does not apply to SAPI, so British spellings and short forms SAPI can
    say ("tyres", "litre") are kept. The recognised text feeds the same
    ``match_intent_with_confidence`` matcher, so any phrase here maps to an intent.
    """
    try:
        from voice.command_vocabulary import candidate_phrases
        from voice.query_listener import _INTENT_KEYWORDS
        phrases = [p for p in candidate_phrases(_INTENT_KEYWORDS) if p and p.strip()]
        # De-dup preserving order.
        seen, uniq = set(), []
        for p in phrases:
            if p not in seen:
                seen.add(p)
                uniq.append(p)
        return uniq
    except Exception:
        return []


class _RecoEvents:
    """COM event sink for the reco context: captures the recognised phrase text.

    win32com instantiates this via ``WithEvents``; the recognised text is read back off
    the live instance after the message pump drains.
    """

    def __init__(self):
        self.text: Optional[str] = None

    # SAPI ISpeechRecoContext event — a full recognition.
    def OnRecognition(self, StreamNumber, StreamPosition, RecognitionType, Result):  # noqa: N802,N803
        try:
            import win32com.client
            result = win32com.client.Dispatch(Result)
            self.text = str(result.PhraseInfo.GetText()).strip().lower()
        except Exception:
            self.text = None


def _ensure_built() -> bool:
    """Build (once) the in-process recogniser + command grammar. False if unavailable."""
    if _STATE["failed"]:
        return False
    if _STATE["built"]:
        return True
    try:
        import pythoncom
        import win32com.client

        # COM must be initialised on this (PTT) thread. Idempotent — S_FALSE if already.
        if not _STATE["com_ready"]:
            pythoncom.CoInitialize()
            _STATE["com_ready"] = True

        phrases = _command_phrases()
        if not phrases:
            _STATE["failed"] = True
            return False

        recognizer = win32com.client.Dispatch("SAPI.SpInprocRecognizer")
        context = recognizer.CreateRecoContext()
        handler = win32com.client.WithEvents(context, _RecoEvents)
        grammar = context.CreateGrammar()
        rule = grammar.Rules.Add(_RULE_NAME, _SPRAF_TOP_LEVEL | _SPRAF_DYNAMIC)
        for phrase in phrases:
            rule.InitialState.AddWordTransition(None, phrase)
        grammar.Rules.Commit()
        grammar.CmdSetRuleState(_RULE_NAME, 0)  # inactive until a clip is fed

        _STATE.update({"recognizer": recognizer, "context": context,
                       "grammar": grammar, "handler": handler, "built": True})
        return True
    except Exception:
        _STATE.update({"failed": True, "built": False, "recognizer": None,
                       "context": None, "grammar": None, "handler": None})
        return False


def is_available() -> bool:
    """Whether SAPI grammar recognition can be used on this machine."""
    with _LOCK:
        return _ensure_built()


def recognize_wav_bytes(audio_bytes: bytes, sample_rate: int,
                        sample_width: int = 2, timeout_s: float = 3.0) -> Optional[str]:
    """Recognise a 16-bit PCM mono clip against the command grammar. None on any failure.

    The clip is the exact audio QueryListener already recorded. Returns the recognised
    command phrase (lower-cased) or None so the caller can fall back to PocketSphinx.
    """
    if not audio_bytes:
        return None
    with _LOCK:
        if not _ensure_built():
            return None
        recognizer = _STATE["recognizer"]
        grammar = _STATE["grammar"]
        handler = _STATE["handler"]
        wav_path = ""
        try:
            import pythoncom
            import win32com.client

            # Write the clip to a short-lived WAV SAPI can open as a file stream.
            fd, wav_path = tempfile.mkstemp(suffix=".wav", prefix="ngr_ptt_")
            os.close(fd)
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(int(sample_width))
                wf.setframerate(int(sample_rate))
                wf.writeframes(audio_bytes)

            handler.text = None
            stream = win32com.client.Dispatch("SAPI.SpFileStream")
            stream.Open(wav_path, _SSFM_OPEN_FOR_READ)
            recognizer.AudioInputStream = stream
            grammar.CmdSetRuleState(_RULE_NAME, 1)  # active

            # Pump COM messages so the recognition event fires, until we have a result or
            # the timeout elapses. A monotonic-free loop with a bounded iteration count
            # keeps this deterministic and avoids Date/time calls.
            import time as _time
            deadline = _time.monotonic() + max(0.5, float(timeout_s))
            while handler.text is None and _time.monotonic() < deadline:
                pythoncom.PumpWaitingMessages()
                _time.sleep(0.01)

            grammar.CmdSetRuleState(_RULE_NAME, 0)  # inactive
            try:
                stream.Close()
            except Exception:
                pass
            recognizer.AudioInputStream = None
            return handler.text or None
        except Exception:
            # A recognition-time COM failure must not permanently disable the path — the
            # next press retries; but never raise into the radio thread.
            return None
        finally:
            if wav_path:
                try:
                    os.remove(wav_path)
                except Exception:
                    pass
