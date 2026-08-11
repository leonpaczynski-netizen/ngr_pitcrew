"""Render the phrase pack: every line the engineer can say, as a wav.

    python tools/render_voice_pack.py                    # the default voice
    python tools/render_voice_pack.py --voice en_GB-cori-high
    python tools/render_voice_pack.py --sample           # the ten A/B lines only

Idempotent. A clip is re-rendered only when its text is new or the tuning that
produced it changed, so re-running after adding one phrase costs one clip
rather than four hundred.

The backend is pluggable because the whole point of pre-rendering is that the
runtime never has to import whatever produced the audio. Piper ships first
because the app already has it; a Kokoro backend can render the same manifest
from a different interpreter entirely, and the app will play the result without
knowing or caring.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pitcrew.engineer import phrase_manifest as manifest  # noqa: E402
from pitcrew.engineer.voice import (  # noqa: E402
    DEFAULT_TUNING,
    PACK_ROOT,
    PACK_MANIFEST,
    PiperEngine,
    clip_filename,
)

# The ten lines from the A/B set, for auditioning a voice before committing to
# rendering four hundred clips in it.
SAMPLE_LINES = (
    "Box this lap.", "Box in 3 laps.", "4.5 laps of fuel.", "P4.",
    "Fuel to 48 litres.", "Say again.", "Copy, staying on the plan.",
    "No stop planned. Running to the flag.", "Racing Medium.",
    "12 laps to go.",
)

SAMPLE_RATE = 22_050


class PiperBackend:
    """Renders through the same engine the app falls back to."""

    def __init__(self, voice_id: str | None, tuning: dict) -> None:
        model = None
        if voice_id:
            found = sorted((REPO / "pitcrew" / "engineer" / "piper_models")
                           .glob(f"{voice_id}*.onnx"))
            if not found:
                raise FileNotFoundError(
                    f"no model for {voice_id!r}. Download it with:\n"
                    f"  python -m piper.download_voices {voice_id} "
                    f"pitcrew/engineer/piper_models")
            model = str(found[0])
        self._engine = PiperEngine(model, tuning=tuning)
        self._engine.warm()
        self.voice_id = voice_id or Path(self._engine._path).stem
        self.tuning = dict(self._engine.tuning)

    def render(self, text: str) -> tuple[bytes, int]:
        frames, rate = [], SAMPLE_RATE
        for samples, chunk_rate in self._engine.synthesise(text):
            frames.append(samples.tobytes())
            rate = chunk_rate
        return b"".join(frames), rate


def write_wav(path: Path, body: bytes, rate: int) -> str:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(body)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_existing(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", default=None,
                        help="model id under pitcrew/engineer/piper_models")
    parser.add_argument("--sample", action="store_true",
                        help="render only the ten audition lines")
    parser.add_argument("--force", action="store_true",
                        help="re-render every clip even if unchanged")
    args = parser.parse_args()

    try:
        backend = PiperBackend(args.voice, dict(DEFAULT_TUNING))
    except Exception as exc:                     # noqa: BLE001
        print(f"cannot render: {type(exc).__name__}: {exc}")
        return 1

    lines = SAMPLE_LINES if args.sample else manifest.clips()
    out = PACK_ROOT / backend.voice_id
    out.mkdir(parents=True, exist_ok=True)
    index_path = out / PACK_MANIFEST

    previous = load_existing(index_path)
    unchanged = previous.get("tuning") == backend.tuning and not args.force
    known = previous.get("clips", {}) if unchanged else {}

    clips, rendered, kept, seconds = {}, 0, 0, 0.0
    for text in lines:
        name = clip_filename(text)
        path = out / name
        entry = known.get(text)
        if entry and path.exists() and entry.get("file") == name:
            clips[text] = entry
            kept += 1
            continue
        body, rate = backend.render(text)
        clips[text] = {"file": name,
                       "sha256": write_wav(path, body, rate),
                       "samples": len(body) // 2}
        seconds += len(body) / 2 / rate
        rendered += 1
        if rendered % 25 == 0:
            print(f"  {rendered} rendered...")

    index_path.write_text(json.dumps({
        "voice": backend.voice_id,
        "tuning": backend.tuning,
        "sampleRate": SAMPLE_RATE,
        "clips": clips,
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    # Anything in the folder that is no longer in the manifest is a clip from
    # an older run. Named, not deleted - deleting files the tool did not write
    # in this run is how a typo in --voice wipes a pack.
    live = {entry["file"] for entry in clips.values()}
    stray = [p.name for p in out.glob("*.wav") if p.name not in live]

    print(f"\nvoice:     {backend.voice_id}")
    print(f"tuning:    {backend.tuning}")
    print(f"rendered:  {rendered} ({seconds:.0f}s of audio)")
    print(f"unchanged: {kept}")
    print(f"total:     {len(clips)} clips in {out}")
    if stray:
        print(f"stray:     {len(stray)} wav(s) not in the manifest, "
              f"e.g. {stray[:3]} - delete by hand if that is what you meant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
