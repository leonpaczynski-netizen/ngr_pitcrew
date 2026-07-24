"""Constrained PTT command vocabulary for the offline recogniser (UAT-4).

PocketSphinx was being asked to transcribe FREE-FORM speech against a general
language model and the result was then keyword-matched. That is close to the worst
possible use of it: a general LM will happily return "for the little liter" for "how
much fuel", the keyword never lands, and the driver hears "Sorry, I did not catch
that" every time.

The app only ever needs to distinguish a small, fixed set of pit-radio commands, and
PocketSphinx has a mode built exactly for that — keyword spotting, where recognition
is constrained to a supplied phrase list. This module builds that phrase list.

The one trap is out-of-vocabulary words: PocketSphinx errors out if ANY word in a
keyword phrase is missing from the pronunciation dictionary, which would take the
whole pass down. Several of the app's own phrases are OOV in the shipped US
dictionary ("tyres", "litre", "analyse", "wheelspin"), so every phrase is validated
against the real dictionary and unusable ones are dropped rather than risking the
recogniser. Pure, offline, cached, and never raises.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, List, Sequence, Set, Tuple

#: Extra phrasings drivers actually say on the radio, mapped onto the same intents the
#: keyword matcher already understands. Keyword spotting rewards LONGER phrases (more
#: acoustic evidence, far fewer false positives), so full questions are worth listing.
EXTRA_PHRASES: Tuple[str, ...] = (
    "how much fuel", "fuel left", "fuel remaining", "how much fuel left",
    "what position", "what position am i", "where am i",
    "how many laps", "how many laps left", "laps remaining",
    "how much time", "time remaining", "how long left",
    "what is my best lap", "best lap", "fastest lap",
    "when should i pit", "when do i pit", "pit window", "should i pit",
    "what is the strategy", "strategy update", "next stop",
    "how am i doing", "how is my pace", "am i consistent",
    "how are my tyres", "tyre temperatures", "how is the rubber",
    "is it raining", "what is the weather",
    "i have damage", "i hit the wall", "i spun",
    "how was my last lap", "review my last lap",
    "how do i go faster", "coaching tips",
    "setup advice", "what should i change",
    # Strategy acknowledgement — accept or decline the live replan recommendation.
    # All words here are US-English and in the CMU pronunciation dictionary.
    "accept the plan", "accept plan",
    "keep the plan", "keep plan", "stay out",
)

#: Phrases below this many characters are too acoustically thin to spot reliably —
#: they fire on almost anything. Dropped from the keyword pass (free-form fallback
#: can still catch them).
_MIN_PHRASE_LEN = 4

_WORD_RE = re.compile(r"[a-z']+")


def _dictionary_path() -> str:
    """Path to the pronunciation dictionary shipped with SpeechRecognition."""
    try:
        import inspect

        import speech_recognition as _sr
        return os.path.join(
            os.path.dirname(inspect.getfile(_sr)), "pocketsphinx-data", "en-US",
            "pronounciation-dictionary.dict")
    except Exception:
        return ""


_DICT_CACHE: Set[str] | None = None


def dictionary_words() -> Set[str]:
    """Every word the offline recogniser can pronounce. Empty set if unavailable."""
    global _DICT_CACHE
    if _DICT_CACHE is not None:
        return _DICT_CACHE
    words: Set[str] = set()
    path = _dictionary_path()
    try:
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    head = line.split("\t", 1)[0].split(" ", 1)[0].strip().lower()
                    if head:
                        # "word(2)" is an alternate pronunciation of "word".
                        words.add(head.split("(", 1)[0])
    except Exception:
        words = set()
    _DICT_CACHE = words
    return words


def phrase_is_pronounceable(phrase: str, words: Set[str]) -> bool:
    """Whether every word of ``phrase`` is in the dictionary.

    With no dictionary available we cannot verify anything, so nothing is claimed
    pronounceable — the caller falls back to free-form rather than handing
    PocketSphinx a phrase list that might abort the whole pass.
    """
    if not words:
        return False
    tokens = _WORD_RE.findall(str(phrase or "").lower())
    return bool(tokens) and all(t in words for t in tokens)


def sensitivity_for(phrase: str) -> float:
    """The detection threshold for one phrase, scaled by how much evidence it carries.

    SpeechRecognition turns this into PocketSphinx's keyword threshold as
    ``1e(100*s - 110)``, and for keyword spotting a SMALLER threshold means MORE
    detections. So a higher value here is STRICTER, and Sphinx's own recommended band
    of 1e-50…1e-5 corresponds to roughly 0.6…1.05 — outside it, short words fire on
    engine noise continuously (measured: at 0.35 a second of noise "spotted" 35 words).

    A single short word therefore has to clear a high bar; a four-word question can be
    matched loosely because noise will not accidentally produce it.
    """
    n = len(_WORD_RE.findall(str(phrase or "").lower()))
    if n >= 4:
        return 0.70    # 1e-40
    if n == 3:
        return 0.80    # 1e-30
    if n == 2:
        return 0.95    # 1e-15
    # 1e-10. SpeechRecognition validates sensitivity into [0, 1], so this is the
    # strictest available — a lone word needs a clean match.
    return 1.00


def candidate_phrases(intent_keywords: Sequence[Tuple[str, Sequence[str]]] = ()) -> List[str]:
    """Every phrase worth spotting, longest first, de-duplicated.

    Longest-first matters: the matcher takes the first intent whose keyword appears,
    so spotting "fuel check" before "fuel" keeps the more specific intent.
    """
    seen: Set[str] = set()
    out: List[str] = []
    for group in (EXTRA_PHRASES, _flatten(intent_keywords)):
        for phrase in group:
            p = " ".join(_WORD_RE.findall(str(phrase or "").lower()))
            if len(p) >= _MIN_PHRASE_LEN and p not in seen:
                seen.add(p)
                out.append(p)
    out.sort(key=lambda p: (-len(p.split()), -len(p)))
    return out


def _flatten(intent_keywords: Iterable[Tuple[str, Sequence[str]]]) -> List[str]:
    flat: List[str] = []
    for entry in intent_keywords or ():
        try:
            _intent, keywords = entry
        except (TypeError, ValueError):
            continue
        flat.extend(str(k) for k in (keywords or ()))
    return flat


def keyword_entries(intent_keywords: Sequence[Tuple[str, Sequence[str]]] = ()) -> List[Tuple[str, float]]:
    """The ``(phrase, sensitivity)`` list to hand PocketSphinx keyword spotting.

    Empty when the dictionary cannot be read — the caller must then use free-form
    recognition rather than risk aborting on an unpronounceable phrase.
    """
    words = dictionary_words()
    if not words:
        return []
    return [(p, sensitivity_for(p)) for p in candidate_phrases(intent_keywords)
            if phrase_is_pronounceable(p, words)]
