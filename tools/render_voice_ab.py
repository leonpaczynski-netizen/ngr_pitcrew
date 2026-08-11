"""Render the same lines under two tunings, so they can be compared by ear.

    python tools/render_voice_ab.py

Voice quality is not something a test can assert. The only way to settle
whether the engineer sounds calm is to listen to him say the things he
actually says, back to back, with nothing else changed.

Writes to `_to_delete/voice_ab/`, which is scratch: it is not committed, and
deleting it costs nothing.
"""
from __future__ import annotations

import sys
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pitcrew.engineer.voice import DEFAULT_TUNING, PiperEngine  # noqa: E402

OUT = REPO / "_to_delete" / "voice_ab"

# What the engineer actually says. Short calls, a number, a compound, a
# refusal and a confirmation - the shapes that expose bad prosody.
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

# The tuning in the tree before this change, and the one after it.
TUNINGS = {
    "before": {"length_scale": 1.0, "noise_scale": 0.667,
               "noise_w_scale": 0.8},
    "after": dict(DEFAULT_TUNING),
}


def _slug(text: str) -> str:
    keep = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    return "-".join(part for part in keep.split("-") if part)[:40]


def render(engine: PiperEngine, text: str, path: Path) -> float:
    """Write one line to a wav. Returns its duration in seconds."""
    frames, rate = [], 22_050
    for samples, chunk_rate in engine.synthesise(text):
        frames.append(samples.tobytes())
        rate = chunk_rate
    body = b"".join(frames)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(body)
    return len(body) / 2 / rate


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        engine = PiperEngine()
    except Exception as exc:                     # noqa: BLE001
        print(f"no Piper on this machine: {type(exc).__name__}: {exc}")
        return 1
    engine.warm()

    for label, tuning in TUNINGS.items():
        engine.tune(**tuning)
        total = 0.0
        for index, line in enumerate(LINES, 1):
            path = OUT / f"{index:02d}-{_slug(line)}.{label}.wav"
            total += render(engine, line, path)
        print(f"{label:<7} {tuning}")
        print(f"        {len(LINES)} lines, {total:.1f}s of audio")

    print(f"\nwritten to {OUT}")
    print("Play each pair back to back - the filenames sort so the two "
          "tunings of a line sit next to each other.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
