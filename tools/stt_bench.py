"""Which recogniser George should use, measured rather than assumed.

He runs `TINY_STREAMING` - **the smallest of the six Moonshine models** - and
the driver's complaint is accuracy and range: he wants to say what he means
rather than one of a list of phrases. Model size is the half of that which is a
one-line change, so it is worth knowing what the larger ones actually buy and
what they cost him in waiting.

**The first version of this tool reported word error rates above 100%, which is
not a bad model, it is a broken harness.** Both faults are worth naming, because
either one would silently poison any future measurement:

* **Scale.** `add_audio` takes floats in -1..1 - the app feeds it straight from
  a `float32` capture stream. The bench handed it int16 sample values as floats,
  so every number arrived thousands of times too loud and the model transcribed
  noise.
* **Reading the answer.** A `Transcript` has no `.text`; it has `.lines`, and
  each line's `str()` is a debug repr - `[0.00s]: 'box this lap', metadata:
  [duration=...]`. The bench fell through to stringifying those, so it scored
  the metadata as if he had said it.

Both are now the same three lines the app itself runs, which is the only version
worth measuring: a benchmark that exercises a different code path from the race
answers a question nobody asked.

**Trailing silence is the biggest single lever here, and it is not a model
choice at all.** A streaming recogniser finishes a word when it hears what
follows it; after the last word nothing follows, because the button comes up.
Feeding six tenths of a second of silence before the final pass took the small
model from two exact transcripts in ten to eight and the tiny model from three
to five - larger than the gap between any two models - and cost nothing, since
silence is fed rather than waited for. The app does this now; `--pad 0` shows
what it was losing.

**Two latencies, and the second is the one he feels.** Audio arrives while he
talks, so feeding it is not waiting. What he waits for is the final pass after
he lets go of the button - `finalise`. `total` is the whole clip fed as fast as
the machine can and then finalised; it bounds the work but overstates the wait.

**The audio is synthesised, and that bounds the claim.** Rendering the phrases
through Piper and reading them back measures the models against each other on
identical input, which is the comparison that decides the choice. It does NOT
measure how well any of them handles his voice, a headset mic, or wheel and
engine noise through an open microphone. Treat the ranking as sound and the
absolute error rates as optimistic.

    python tools/stt_bench.py                 # tiny vs small vs medium
    python tools/stt_bench.py --pad 0 --show  # what the truncation costs

Read-only. Downloads a model on first use of each architecture.
"""
from __future__ import annotations

import argparse
import re
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

SAMPLE_RATE = 16_000
BLOCK = 1600                    # 100 ms, the granularity the app captures in


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
    if rate != SAMPLE_RATE:
        want = int(len(audio) * SAMPLE_RATE / rate)
        idx = (np.arange(want) * (len(audio) - 1) / max(1, want - 1))
        audio = np.interp(idx, np.arange(len(audio)), audio).astype("int16")
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(audio.tobytes())
    return True


_PUNCT = re.compile(r"[^a-z0-9' ]+")


def _normalise(text: str) -> list:
    """Case and punctuation are not errors he would hear.

    The models return capitals and full stops; he did not say them. Scoring
    those as substitutions inflates every rate by roughly one error per
    sentence and makes the models look closer together than they are.
    """
    return _PUNCT.sub(" ", text.lower()).split()


def _wer(said: str, heard: str) -> float:
    """Word error rate by edit distance, the standard measure."""
    a, b = _normalise(said), _normalise(heard)
    if not a:
        return 0.0
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, start=1):
        cur = [i]
        for j, y in enumerate(b, start=1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1] / len(a)


def _read(clip: Path):
    """The clip as float32 in -1..1, the way the capture stream delivers it."""
    import numpy as np

    with wave.open(str(clip), "rb") as f:
        raw = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
    return raw.astype(np.float32) / 32768.0


def _transcribe(transcriber, audio, pad_s=0.6):
    """Exactly what `ptt.py` does, and timed the way he experiences it."""
    import numpy as np

    started = time.perf_counter()
    transcriber.start()
    try:
        for at in range(0, len(audio), BLOCK):
            transcriber.add_audio(audio[at:at + BLOCK].tolist(), SAMPLE_RATE)
        # The wait that belongs to him: everything above happens while he is
        # still speaking, this happens after he lets go of the button.
        released = time.perf_counter()
        if pad_s:
            quiet = np.zeros(int(SAMPLE_RATE * pad_s), dtype=np.float32)
            for at in range(0, quiet.size, BLOCK):
                transcriber.add_audio(quiet[at:at + BLOCK].tolist(),
                                      SAMPLE_RATE)
        result = transcriber.update_transcription()
        finalise = (time.perf_counter() - released) * 1000.0
        text = " ".join(line.text for line in
                        getattr(result, "lines", [])).strip()
    finally:
        transcriber.stop()
    return text, finalise, (time.perf_counter() - started) * 1000.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arch", action="append",
                    help="repeatable; defaults to tiny/small/medium streaming")
    ap.add_argument("--show", action="store_true",
                    help="print every mishearing, which is the useful half")
    ap.add_argument("--pad", type=float, default=0.6,
                    help="seconds of trailing silence; --pad 0 to see what "
                         "cutting the audio off at the last syllable costs")
    ap.add_argument("--repeat", type=int, default=3,
                    help="passes over the phrase set; ten phrases is a small "
                         "sample and one pass moves several points run to run")
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

    from moonshine_voice.moonshine_api import ModelArch
    import moonshine_voice as moonshine
    from moonshine_voice.transcriber import Transcriber

    head = ("model", "median WER", "exact", "finalise ms", "worst", "total ms")
    print("{:22} {:>11} {:>7} {:>12} {:>7} {:>9}".format(*head))
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
        errs, waits, totals, misheard = [], [], [], []
        for _ in range(max(1, args.repeat)):
            for text, clip in clips:
                try:
                    heard, finalise, total = _transcribe(
                        transcriber, _read(clip), pad_s=args.pad)
                except Exception as exc:                     # noqa: BLE001
                    print(f"  {name}: transcribe failed: "
                          f"{type(exc).__name__}: {exc}")
                    continue
                err = _wer(text, heard)
                errs.append(err)
                waits.append(finalise)
                totals.append(total)
                if err and (text, heard) not in misheard:
                    misheard.append((text, heard))
        if errs:
            exact = sum(1 for e in errs if e == 0)
            errs.sort()
            waits.sort()
            totals.sort()
            print("{:22} {:>10.1%} {:>4}/{:<2} {:>11.0f} {:>6.0f} "
                  "{:>8.0f}".format(name, errs[len(errs) // 2], exact,
                                    len(errs), waits[len(waits) // 2],
                                    waits[-1], totals[len(totals) // 2]))
            if args.show:
                for said, heard in misheard:
                    print(f"    said  {said!r}")
                    print(f"    heard {heard!r}")
        try:
            transcriber.close()
        except Exception:                                    # noqa: BLE001
            pass

    print("\nSynthesised speech, so the ranking is sound and the absolute "
          "error rates are optimistic - a headset mic in a moving car is "
          "harder than this. `finalise` is what he waits for after releasing "
          "the button; `total` also includes feeding audio he has already "
          "spoken.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
