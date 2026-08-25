"""Which recogniser George should use, measured rather than assumed.

He runs `TINY_STREAMING` - **the smallest of the six Moonshine models** - and
the driver's complaint is accuracy and range: he wants to say what he means
rather than one of a list of phrases. Model size is the half of that which is a
one-line change, so it is worth knowing what the larger ones actually buy and
what they cost in latency.

**Latency is not a footnote here, it is the constraint.** A recogniser that is
right more often but answers a second later may still be the wrong choice under
a helmet - he used push-to-talk zero times in fifty-three minutes at Fuji, and a
tool nobody reaches for is worth nothing however accurate it is.

**The audio is synthesised, and that bounds the claim.** Rendering the phrases
through Piper and reading them back measures the models against each other on
identical input, which is the comparison that decides the choice. It does NOT
measure how well any of them handles his voice, a headset mic, or wheel and
engine noise through an open microphone. Treat the ranking as sound and the
absolute error rates as optimistic.

    python tools/stt_bench.py                 # tiny vs base vs small
    python tools/stt_bench.py --arch MEDIUM_STREAMING

Read-only. Downloads a model on first use of each architecture.
"""
from __future__ import annotations

import argparse
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# What he actually says on the radio, plus the shapes that are hardest: a
# number, a compound code, and a free sentence outside the intent list.
PHRASES = (
    "how many laps left",
    "what's my fuel looking like",
    "when am I boxing",
    "box this lap",
    "the rear is loose on entry",
    "I'm getting understeer in the middle of the corner",
    "there's traffic ahead of me",
    "what tyres am I on",
    "I had a moment at turn one and lost about three seconds",
    "can I make it to the end on this set",
)

# `BASE_STREAMING` is not published for English - the library offers TINY,
# BASE, TINY_STREAMING, SMALL_STREAMING and MEDIUM_STREAMING, and **MEDIUM is
# its default**. The app asks for the smallest of them by name.
DEFAULT_ARCHES = ("TINY_STREAMING", "SMALL_STREAMING", "MEDIUM_STREAMING")


def _render(text: str, path: Path) -> bool:
    """One phrase as a 16 kHz wav, through the voice George already uses."""
    try:
        from pitcrew.engineer.voice import PiperEngine
    except Exception:                                        # noqa: BLE001
        return False
    try:
        engine = PiperEngine()
        chunks = list(engine.synthesise(text))
    except Exception as exc:                                 # noqa: BLE001
        print(f"  could not synthesise {text!r}: {exc}")
        return False
    if not chunks:
        return False
    import numpy as np

    rate = chunks[0][1]
    audio = np.concatenate([c[0] for c in chunks])
    # Moonshine wants 16 kHz mono. Linear resample is plenty for a benchmark
    # whose question is which model reads the words, not audio quality.
    if rate != 16_000:
        want = int(len(audio) * 16_000 / rate)
        idx = (np.arange(want) * (len(audio) - 1) / max(1, want - 1))
        audio = np.interp(idx, np.arange(len(audio)), audio).astype("int16")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16_000)
        out.writeframes(audio.tobytes())
    return True


def _wer(said: str, heard: str) -> float:
    """Word error rate by edit distance, the standard measure."""
    a, b = said.lower().split(), heard.lower().split()
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, start=1):
        cur = [i]
        for j, y in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1] / max(1, len(a))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arch", action="append",
                    help="repeatable; defaults to tiny/base/small streaming")
    args = ap.parse_args()
    arches = args.arch or list(DEFAULT_ARCHES)

    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="stt_bench_"))
    print(f"rendering {len(PHRASES)} phrases through Piper...")
    clips = []
    for n, text in enumerate(PHRASES):
        path = tmp / f"{n}.wav"
        if _render(text, path):
            clips.append((text, path))
    if not clips:
        print("nothing rendered - Piper unavailable, cannot benchmark")
        return 1
    print(f"  {len(clips)} clips\n")

    import numpy as np
    from moonshine_voice.moonshine_api import ModelArch
    import moonshine_voice as moonshine
    from moonshine_voice.transcriber import Transcriber

    print(f"{'model':22} {'median WER':>11} {'mean WER':>9} "
          f"{'median ms':>10} {'worst ms':>9}")
    for name in arches:
        arch = getattr(ModelArch, name, None)
        if arch is None:
            print(f"  {name}: no such architecture")
            continue
        try:
            path, resolved = moonshine.get_model_for_language("en", arch)
            transcriber = Transcriber(path, resolved)
        except Exception as exc:                             # noqa: BLE001
            print(f"{name:22} unavailable: {type(exc).__name__}: {exc}")
            continue
        errs, times = [], []
        for text, clip in clips:
            with wave.open(str(clip), "rb") as f:
                audio = np.frombuffer(f.readframes(f.getnframes()),
                                      dtype=np.int16)
            # The same call the app's own capture path uses: feed the audio
            # in and read the transcription back, rather than a one-shot API
            # that would measure a different code path from the one raced.
            started = time.perf_counter()
            heard = ""
            try:
                transcriber.start()
                transcriber.add_audio(audio.tolist(), 16_000)
                result = transcriber.update_transcription()
                transcriber.stop()
                heard = getattr(result, "text", None) or (
                    result if isinstance(result, str) else "")
                if not heard and result is not None:
                    for attr in ("transcription", "line", "lines", "segments"):
                        got = getattr(result, attr, None)
                        if got:
                            heard = (" ".join(str(g) for g in got)
                                     if isinstance(got, (list, tuple))
                                     else str(got))
                            break
            except Exception as exc:                         # noqa: BLE001
                print(f"  {name}: transcribe failed: "
                      f"{type(exc).__name__}: {exc}")
            times.append((time.perf_counter() - started) * 1000.0)
            errs.append(_wer(text, str(heard or "")))
        errs.sort()
        times.sort()
        print(f"{name:22} {errs[len(errs) // 2]:10.1%} "
              f"{sum(errs) / len(errs):8.1%} "
              f"{times[len(times) // 2]:10.0f} {times[-1]:9.0f}")

    print("\nSynthesised speech, so the ranking is sound and the absolute "
          "error rates are optimistic - a headset mic in a moving car is "
          "harder than this.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
