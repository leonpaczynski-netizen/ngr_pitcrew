"""Render the Kokoro candidates. Runs under its own interpreter, not the app's.

    py -3.12 -m venv _to_delete\\kokoro-venv
    _to_delete\\kokoro-venv\\Scripts\\pip install kokoro-onnx soundfile
    _to_delete\\kokoro-venv\\Scripts\\python tools\\render_kokoro_audition.py

Kokoro-82M declares Python 3.10-3.13 and this app runs on 3.14, so it can
never be a runtime dependency here. It does not have to be: the phrase pack is
pre-rendered, and the app plays wavs without knowing what produced them. If
Kokoro wins the listening test, `tools/render_voice_pack.py` gains a Kokoro
backend that is run from this venv, and the app itself gains nothing at all.

This script deliberately imports nothing from `pitcrew` - it runs under a
different interpreter, and the ten lines are duplicated here rather than
imported for that reason.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "_to_delete" / "voice_audition"

# The same ten calls as tools/audition_voices.py. Duplicated on purpose: see
# the module docstring.
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

# The two best-trained British voices in the model: bf_emma is the highest
# graded female, bm_george the RP male.
VOICES = ("bf_emma", "bm_george")


def _slug(text: str) -> str:
    keep = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    return "-".join(part for part in keep.split("-") if part)[:36]


def main() -> int:
    try:
        import soundfile as sf
        from kokoro_onnx import Kokoro
    except ImportError as exc:
        print(f"missing dependency: {exc}")
        print(__doc__)
        return 1

    model = REPO / "_to_delete" / "kokoro-v1.0.onnx"
    voices = REPO / "_to_delete" / "voices-v1.0.bin"
    if not model.exists() or not voices.exists():
        print("Kokoro needs its model files. Download them into _to_delete/:")
        print("  https://github.com/thewh1teagle/kokoro-onnx/releases"
              "/download/model-files-v1.0/kokoro-v1.0.onnx")
        print("  https://github.com/thewh1teagle/kokoro-onnx/releases"
              "/download/model-files-v1.0/voices-v1.0.bin")
        return 1

    kokoro = Kokoro(str(model), str(voices))
    for voice in VOICES:
        folder = OUT / f"kokoro-{voice}"
        folder.mkdir(parents=True, exist_ok=True)
        seconds = 0.0
        for index, line in enumerate(LINES, 1):
            samples, rate = kokoro.create(line, voice=voice, speed=1.0,
                                          lang="en-gb")
            sf.write(str(folder / f"{index:02d}-{_slug(line)}.wav"),
                     samples, rate)
            seconds += len(samples) / rate
        print(f"kokoro-{voice:<28} {len(LINES)} lines, {seconds:5.1f}s")

    print(f"\nwritten to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
