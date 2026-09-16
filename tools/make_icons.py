"""Cut every icon size Windows and the phone need, from one piece of artwork.

    python tools/make_icons.py --sheet out.png    # how it reads at real sizes
    python tools/make_icons.py --write            # the .ico and the PWA PNGs

The artwork is `icon-src.png` at the repo root: the Pit Crew headset with the
chequered earcup, the rev arc, and "PIT CREW" under it (the driver, 16 Sep
2026). Two rules turn it into icons, and both exist because an icon is looked
at, not read:

* **The text is dropped below 48 px.** "PIT CREW" is four hundred pixels wide
  in the art and a grey smudge at 16; the small frames carry the headset and
  the arc alone, enlarged into the room the text had. An `.ico` holding
  different art per size is what the format is for.
* **The small frames are BMP, not PNG.** Every frame of the old `pitcrew.ico`
  was PNG-compressed - Explorer drew the 256 and fell back to a generic icon
  for the shortcut and the taskbar. Pillow writes BMP under 256 and PNG at
  256, which is what the shell reads.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "icon-src.png"
ICON = ROOT / "pitcrew.ico"
PWA_DIR = ROOT / "pitcrew" / "ui"

# The ground the art was drawn on, and the board's own black behind anything
# transparent - so a rounded phone icon and a Windows tile show one colour.
GROUND = (5, 6, 10)
# The artwork's own green, for the small-size silhouette.
LIME = "#8BE33C"

# Where the lettering starts, as a fraction of the artwork's height. The
# headset and the arc live above it; the bar and "PIT CREW" below.
TEXT_FROM = 0.70
# Frames that carry the whole lockup, and the ones that carry the mark alone.
ICO_SIZES = (16, 20, 24, 32, 48, 64, 128, 256)
TEXT_FROM_SIZE = 48
PWA_SIZES = (180, 192, 512)


def _square(art: Image.Image) -> Image.Image:
    """The artwork centred on a square of its own ground."""
    side = max(art.size)
    card = Image.new("RGB", (side, side), GROUND)
    if art.mode == "RGBA":
        card.paste(art, ((side - art.width) // 2, (side - art.height) // 2),
                   art)
    else:
        card.paste(art.convert("RGB"),
                   ((side - art.width) // 2, (side - art.height) // 2))
    return card


def lockup(source: Path = SOURCE) -> Image.Image:
    """The whole thing: headset, arc, and the words."""
    return _square(Image.open(source))


def silhouette() -> Image.Image:
    """The headset as a solid shape, for the frames Windows draws small.

    **A photograph is not an icon at 24 px.** Cropping the artwork to the
    headset was tried first and the taskbar showed a dark smudge: the chrome,
    the arc's gradient and the flag's checks all fall below a pixel. A
    silhouette keeps the one thing that is legible at that size - the
    outline - in the artwork's own lime on its own black.

    Drawn rather than traced so it stays crisp at every size, and so the
    boom mic survives: without it the shape reads as music headphones.
    """
    from PIL import ImageDraw

    side = 512
    card = Image.new("RGB", (side, side), GROUND)
    draw = ImageDraw.Draw(card)
    band = int(side * 0.115)
    draw.arc((int(side * 0.17), int(side * 0.14), int(side * 0.83),
              int(side * 0.80)), 200, 340, fill=LIME, width=band)
    cup_w, cup_h, top = int(side * 0.20), int(side * 0.34), int(side * 0.40)
    draw.rounded_rectangle((int(side * 0.13), top, int(side * 0.13) + cup_w,
                            top + cup_h), radius=int(cup_w * 0.42), fill=LIME)
    draw.rounded_rectangle((int(side * 0.87) - cup_w, top, int(side * 0.87),
                            top + cup_h), radius=int(cup_w * 0.42), fill=LIME)
    draw.line([(int(side * 0.19), int(side * 0.72)),
               (int(side * 0.30), int(side * 0.86)),
               (int(side * 0.46), int(side * 0.86))], fill=LIME,
              width=int(side * 0.055), joint="curve")
    return card


def mark(source: Path = SOURCE) -> Image.Image:
    """The headset and the arc, without the lettering, filling the square.

    **Trimmed to what is actually drawn**, not to the artwork's own margins:
    the lockup leaves room under the headset for the words, and a small frame
    that keeps that room spends a quarter of sixteen pixels on ground.
    """
    art = Image.open(source)
    top = art.crop((0, 0, art.width, int(art.height * TEXT_FROM)))
    grey = top.convert("RGB").convert("L")
    # Everything brighter than the ground, with a margin for the arc's glow.
    box = grey.point(lambda v: 255 if v > 24 else 0).getbbox()
    if box is not None:
        edge = int(max(top.size) * 0.04)
        box = (max(0, box[0] - edge), max(0, box[1] - edge),
               min(top.width, box[2] + edge), min(top.height, box[3] + edge))
        top = top.crop(box)
    return _square(top)


def _frame(size: int) -> Image.Image:
    art = lockup() if size >= TEXT_FROM_SIZE else silhouette()
    return art.resize((size, size), Image.LANCZOS)


def sheet(path: Path) -> None:
    """Both cuts at every size, so the swap-over can be judged rather than
    assumed."""
    sizes = (16, 24, 32, 48, 64, 128, 180)
    gap, pad = 28, 24
    page = Image.new("RGB", (pad + sum(s + gap for s in sizes),
                             3 * (180 + gap) + pad), (18, 18, 18))
    rows = (lockup(), mark(), None)        # whole, mark, and what ships
    for row, art in enumerate(rows):
        x, y = pad, pad + row * (180 + gap)
        for size in sizes:
            drawn = _frame(size) if art is None else art.resize(
                (size, size), Image.LANCZOS)
            page.paste(drawn, (x, y + (180 - size) // 2))
            x += size + gap
    page = page.resize((page.width * 2, page.height * 2), Image.NEAREST)
    page.save(path)
    print(f"wrote {path}")


def _dib(frame: Image.Image) -> bytes:
    """One frame as a 32-bit DIB, the shape an `.ico` has always held.

    `BITMAPINFOHEADER` with double the height (the format's own convention:
    colour rows then the AND mask), BGRA bottom-up, and an all-zero mask
    because the alpha channel carries the shape.
    """
    import struct

    rgba = frame.convert("RGBA")
    width, height = rgba.size
    rows = []
    for y in range(height - 1, -1, -1):
        row = bytearray()
        for x in range(width):
            r, g, b, a = rgba.getpixel((x, y))
            row += bytes((b, g, r, a))
        rows.append(bytes(row))
    mask_row = b"\x00" * (((width + 31) // 32) * 4)
    header = struct.pack("<IiiHHIIiiII", 40, width, height * 2, 1, 32, 0,
                         0, 0, 0, 0, 0)
    return header + b"".join(rows) + mask_row * height


def _ico(frames: list[Image.Image]) -> bytes:
    """The whole file: BMP under 256, PNG at 256.

    **Written here rather than by Pillow**, for both of this module's rules:
    Pillow's ICO writer PNG-compresses every frame (which is the defect on
    the shortcut) and resizes one image for all of them (which would put the
    lettering back into the 16 px frame).
    """
    import struct

    payloads = []
    for frame in frames:
        if frame.width >= 256:
            from io import BytesIO

            buffer = BytesIO()
            frame.convert("RGBA").save(buffer, format="PNG")
            payloads.append(buffer.getvalue())
        else:
            payloads.append(_dib(frame))
    out = bytearray(struct.pack("<HHH", 0, 1, len(frames)))
    offset = 6 + 16 * len(frames)
    for frame, payload in zip(frames, payloads):
        side = 0 if frame.width >= 256 else frame.width
        out += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32,
                           len(payload), offset)
        offset += len(payload)
    for payload in payloads:
        out += payload
    return bytes(out)


def write() -> None:
    """The `.ico` Windows reads and the PNGs a phone's home screen reads."""
    ICON.write_bytes(_ico([_frame(size) for size in ICO_SIZES]))
    print(f"wrote {ICON}")
    for size in PWA_SIZES:
        out = PWA_DIR / f"icon-{size}.png"
        lockup().resize((size, size), Image.LANCZOS).save(out)
        print(f"wrote {out}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sheet", type=Path, help="write a comparison sheet")
    ap.add_argument("--write", action="store_true",
                    help="write the .ico and the PWA icons")
    args = ap.parse_args(argv)
    if not SOURCE.is_file():
        ap.error(f"no artwork at {SOURCE}")
    if args.sheet:
        sheet(args.sheet)
    if args.write:
        write()
    if not args.sheet and not args.write:
        ap.error("nothing to do: pass --sheet or --write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
