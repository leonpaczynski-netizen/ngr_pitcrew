"""Render the same ten calls in every candidate voice, for a blind listen.

    python tools/audition_voices.py              # one folder per voice
    python tools/audition_voices.py --speakers   # a spread of VCTK speakers

Which voice sounds like a race engineer is not a decision this tool makes and
not one it can make: it has no ears. It renders, names the files by voice, and
stops. The owner picks.

Output goes to `_to_delete/voice_audition/`, which is scratch.

Kokoro is not rendered here. It declares Python 3.10-3.13 and this app runs on
3.14, so it needs its own interpreter - see `--kokoro-help`. Because the pack
is pre-rendered, that is only ever a rendering-time dependency: the app plays
the wavs and never imports whatever produced them.
"""
from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pitcrew.engineer.voice import DEFAULT_TUNING, PiperEngine  # noqa: E402

MODELS = REPO / "pitcrew" / "engineer" / "piper_models"
OUT = REPO / "_to_delete" / "voice_audition"

LINES = (
    "Box this lap.",
    "Box in 3 laps.",
    "4.5 laps of fuel.",
    "P4.",
    "Fuel to 48 litres.",
    "Say again.",
    "Copy, staying on the plan.",
    "No stop planned. Running to the flag.",
    "Racing Medium.",
    "12 laps to go.",
)

# Single-speaker candidates. VCTK is handled separately because 109 speakers
# is not something anyone auditions ten lines at a time.
CANDIDATES = (
    "en_GB-alan-medium",                  # what the pack is rendered in today
    "en_GB-cori-high",                    # the only high tier Piper has for en_GB
    "en_GB-northern_english_male-medium",
)

VCTK = "en_GB-vctk-medium"
# A spread across the corpus rather than the first twelve, which are all
# neighbouring recording sessions.
VCTK_SPEAKERS = tuple(range(0, 109, 9))
VCTK_AUDITION_LINE = "Box in 3 laps."

KOKORO_HELP = """\
Kokoro-82M needs its own interpreter (it declares 3.10-3.13; this app is 3.14).
The pack is pre-rendered, so this is a render-time dependency only:

    py -3.12 -m venv _to_delete\\kokoro-venv
    _to_delete\\kokoro-venv\\Scripts\\pip install kokoro-onnx soundfile
    _to_delete\\kokoro-venv\\Scripts\\python tools\\render_kokoro_audition.py

Voices to audition: bf_emma, bm_george.
"""


def _slug(text: str) -> str:
    keep = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    return "-".join(part for part in keep.split("-") if part)[:36]


def write_wav(path: Path, engine: PiperEngine, text: str) -> float:
    frames, rate = [], 22_050
    for samples, chunk_rate in engine.synthesise(text):
        frames.append(samples.tobytes())
        rate = chunk_rate
    body = b"".join(frames)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(body)
    return len(body) / 2 / rate


def _engine(voice_id: str, speaker: int | None = None) -> PiperEngine:
    model = MODELS / f"{voice_id}.onnx"
    if not model.exists():
        raise FileNotFoundError(
            f"no model for {voice_id}. Download it with:\n"
            f"  python -m piper.download_voices {voice_id} "
            f"--data-dir pitcrew/engineer/piper_models")
    tuning = dict(DEFAULT_TUNING)
    engine = PiperEngine(str(model), tuning=tuning)
    if speaker is not None:
        engine.tuning["speaker_id"] = speaker
    engine.warm()
    return engine


def audition_voices() -> None:
    for voice_id in CANDIDATES:
        try:
            engine = _engine(voice_id)
        except Exception as exc:                 # noqa: BLE001
            print(f"{voice_id}: skipped - {type(exc).__name__}: {exc}")
            continue
        total = 0.0
        for index, line in enumerate(LINES, 1):
            path = OUT / voice_id / f"{index:02d}-{_slug(line)}.wav"
            total += write_wav(path, engine, line)
        print(f"{voice_id:<36} {len(LINES)} lines, {total:5.1f}s")


def audition_speakers() -> None:
    """One line across a spread of VCTK speakers, to shortlist by ear."""
    folder = OUT / f"{VCTK}-speakers"
    for speaker in VCTK_SPEAKERS:
        try:
            engine = _engine(VCTK, speaker)
        except Exception as exc:                 # noqa: BLE001
            print(f"{VCTK} speaker {speaker}: {type(exc).__name__}: {exc}")
            return
        path = folder / f"speaker-{speaker:03d}.wav"
        write_wav(path, engine, VCTK_AUDITION_LINE)
    print(f"{VCTK:<36} {len(VCTK_SPEAKERS)} speakers, "
          f"one line: {VCTK_AUDITION_LINE!r}")
    print(f"  shortlist three, then re-run with "
          f"--speaker N to hear all ten lines")


def audition_one_speaker(speaker: int) -> None:
    engine = _engine(VCTK, speaker)
    folder = OUT / f"{VCTK}-speaker-{speaker:03d}"
    total = 0.0
    for index, line in enumerate(LINES, 1):
        total += write_wav(folder / f"{index:02d}-{_slug(line)}.wav",
                           engine, line)
    print(f"{VCTK} speaker {speaker}: {len(LINES)} lines, {total:.1f}s")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speakers", action="store_true",
                        help="render one line across a spread of VCTK speakers")
    parser.add_argument("--speaker", type=int, default=None,
                        help="render all ten lines for one VCTK speaker")
    parser.add_argument("--kokoro-help", action="store_true",
                        help="how to render the Kokoro candidates")
    args = parser.parse_args()

    if args.kokoro_help:
        print(KOKORO_HELP)
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    if args.speaker is not None:
        audition_one_speaker(args.speaker)
    elif args.speakers:
        audition_speakers()
    else:
        audition_voices()
    print(f"\nwritten to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
