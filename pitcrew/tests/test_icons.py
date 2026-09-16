"""The icons: the shortcut's, the taskbar's, and the phone home screen's.

16 Sep 2026. Two defects, one artefact:

* **The desktop shortcut drew a generic icon.** It pointed at `pitcrew.ico`
  all along and the file was fine to look at - the 256 px frame rendered in
  every preview. Every frame in it was PNG-compressed, including 16-48, and
  the Windows shell reads those small frames as BMP; PNG there is a frame it
  skips. So the shell fell back to the host `pythonw.exe`'s own icon.
* **The strip installed as a PWA had no icon**: no `apple-touch-icon` and no
  manifest, so iOS used a screenshot of a page that is mostly black.

Both are held here against the files themselves, because both were invisible
to every test the app had and visible on his desktop.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ICON = ROOT / "pitcrew.ico"
UI = ROOT / "pitcrew" / "ui"


def frames() -> list[tuple[int, str]]:
    """`(side, "BMP" | "PNG")` for every frame in the icon file."""
    raw = ICON.read_bytes()
    count = struct.unpack_from("<H", raw, 4)[0]
    out = []
    for index in range(count):
        side, _h, _c, _r, _p, _bpp, _size, offset = struct.unpack_from(
            "<BBBBHHII", raw, 6 + 16 * index)
        kind = "PNG" if raw[offset:offset + 4] == b"\x89PNG" else "BMP"
        out.append((side or 256, kind))
    return out


def test_the_small_frames_are_bmp_or_the_shell_draws_a_generic_icon():
    small = [(side, kind) for side, kind in frames() if side < 256]
    assert small, "the icon carries no small frames at all"
    assert all(kind == "BMP" for _side, kind in small), small


def test_the_sizes_windows_actually_asks_for_are_all_there():
    """16 the file list, 32 the taskbar and shortcut, 48 the desktop at its
    usual scaling, 256 the preview. The rest are what the shell picks between
    at other DPIs."""
    sides = [side for side, _kind in frames()]
    for wanted in (16, 24, 32, 48, 64, 128, 256):
        assert wanted in sides, (wanted, sides)


def test_the_largest_frame_is_png_because_a_256_bmp_is_a_quarter_megabyte():
    assert dict(frames())[256] == "PNG"


def test_the_small_frames_drop_the_lettering():
    """"PIT CREW" is a grey smudge at 16 px, so the small frames carry the
    headset and the arc alone - `make_icons.mark()`. The two cuts differ,
    which is the whole reason an `.ico` holds art per size."""
    pytest.importorskip("PIL")
    from PIL import Image

    from tools.make_icons import TEXT_FROM_SIZE, lockup, mark

    small, large = Image.open(ICON), Image.open(ICON)
    small.size = (32, 32)
    small.load()
    large.size = (128, 128)
    large.load()

    def close(a, b) -> float:
        a, b = a.convert("RGB").resize((32, 32)), b.convert("RGB").resize((32, 32))
        return sum(abs(x - y) for x, y in zip(a.tobytes(), b.tobytes()))

    assert close(small, mark()) < close(small, lockup())
    assert close(large, lockup()) < close(large, mark())
    assert TEXT_FROM_SIZE == 48


def test_the_phone_gets_an_icon_and_a_manifest():
    from pitcrew.ui.strip_server import PAGE, STATIC

    page = PAGE.read_text(encoding="utf-8")
    assert 'rel="apple-touch-icon" href="/icon-180.png"' in page
    assert 'rel="manifest" href="/manifest.webmanifest"' in page
    for route, (name, _kind) in STATIC.items():
        asset = PAGE.with_name(name)
        assert asset.is_file(), f"{route} has no file ({asset})"
        assert asset.stat().st_size > 0


def test_the_manifest_names_the_app_and_its_icons():
    manifest = json.loads((UI / "strip.webmanifest").read_text(encoding="utf-8"))
    assert manifest["short_name"] == "Pit Crew"
    assert manifest["display"] == "standalone"
    sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes
    for icon in manifest["icons"]:
        assert (UI / icon["src"].lstrip("/")).is_file(), icon


def test_the_server_serves_them(tmp_path):
    """The routes, through the real server - a manifest that 404s is a page
    with no icon, and nothing in the app would have said so."""
    import urllib.request

    from pitcrew.ui.strip_server import StripServer

    server = StripServer(port=0, host="127.0.0.1")
    assert server.start()
    try:
        port = server._httpd.server_address[1]
        for route, kind in (("/manifest.webmanifest", "application/manifest+json"),
                            ("/icon-180.png", "image/png"),
                            ("/icon-512.png", "image/png")):
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}{route}") as answer:
                assert answer.status == 200, route
                assert answer.headers["Content-Type"] == kind
                assert len(answer.read()) > 100, route
    finally:
        server.stop()
