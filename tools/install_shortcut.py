"""Put Pit Crew on the taskbar.

Builds an icon from the logo and creates a shortcut you can pin. Run once:

    python tools/install_shortcut.py

Then right-click the new Desktop shortcut and choose "Pin to taskbar".

The icon is built size-adaptive on purpose. The logo is a wide banner, and any
single crop of it that reads at 256 px is an unreadable smudge at 16 px, which
is the size the taskbar and Alt-Tab actually draw. A .ico can carry a different
image per size, so the small sizes get a tight crop of the chequered flag - a
bold two-tone shape that survives - and the large sizes get the whole headset.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOGO = REPO / "logo.png"
ICON = REPO / "pitcrew.ico"
NAME = "Next Gear Racing Pit Crew"
# Must match pitcrew.app.APP_ID or Windows treats the pinned
# shortcut and the running window as two different applications.
APP_ID = "NextGearRacing.PitCrew"

# Crops from logo.png, chosen by looking at them rendered at real sizes.
FLAG_CROP = (1105, 675, 1275, 845)      # legible down to 16 px
CUP_CROP = (1035, 600, 1300, 865)       # the headset, for 48 px and up
SMALL_SIZES = (16, 20, 24, 32)
LARGE_SIZES = (48, 64, 128, 256)


def build_icon() -> Path:
    from PIL import Image

    if not LOGO.exists():
        raise SystemExit(f"no logo at {LOGO}")

    logo = Image.open(LOGO).convert("RGBA")
    flag = logo.crop(FLAG_CROP)
    cup = logo.crop(CUP_CROP)

    frames = [flag.resize((size, size), Image.LANCZOS) for size in SMALL_SIZES]
    frames += [cup.resize((size, size), Image.LANCZOS) for size in LARGE_SIZES]

    # Pillow writes every appended image as its own frame, so each size keeps
    # the crop chosen for it rather than being downscaled from one source.
    frames[-1].save(ICON, format="ICO",
                    sizes=[(f.width, f.height) for f in frames],
                    append_images=frames[:-1])
    return ICON


def _pythonw() -> str:
    """The windowed interpreter, so launching does not open a console."""
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate if candidate.exists() else sys.executable)


def make_shortcut(folder: Path, icon: Path, *, force: bool = False) -> Path:
    import win32com.client

    folder.mkdir(parents=True, exist_ok=True)
    name = f"{NAME} (force start)" if force else NAME
    path = folder / f"{name}.lnk"
    shell = win32com.client.Dispatch("WScript.Shell")
    link = shell.CreateShortCut(str(path))
    link.TargetPath = _pythonw()
    link.Arguments = "-m pitcrew.app --force" if force else "-m pitcrew.app"
    # Without this the app writes data/pitcrew.db and exports/ wherever the
    # shortcut happened to be launched from.
    link.WorkingDirectory = str(REPO)
    link.IconLocation = str(icon)
    link.Description = (
        "Start even if another copy holds the rig claim"
        if force else "GT7 race engineering companion")
    link.save()
    if not force:
        # **Only the ordinary shortcut is tagged.** The app id is what groups
        # a pinned shortcut with the running window; giving both the same id
        # would make the recovery shortcut disappear into the normal one on
        # the taskbar, which is the one place it needs to be findable.
        _tag_app_id(path)
    return path


def _tag_app_id(path: Path) -> None:
    """Stamp System.AppUserModel.ID on the shortcut.

    Without it the pinned shortcut and the running window are two taskbar
    buttons. Best effort: the app sets the same id on itself, so pinning the
    running window works even if this fails.
    """
    try:
        import pythoncom
        from win32com.propsys import propsys, pscon

        store = propsys.SHGetPropertyStoreFromParsingName(
            str(path), None, 3, propsys.IID_IPropertyStore)  # GPS_READWRITE
        store.SetValue(pscon.PKEY_AppUserModel_ID,
                       propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR))
        store.Commit()
    except Exception as exc:                     # noqa: BLE001
        print(f"  (could not tag app id: {type(exc).__name__}: {exc})")


def main() -> int:
    icon = build_icon()
    print(f"icon:      {icon}")

    made = []
    desktop = Path(os.path.expanduser("~")) / "Desktop"
    made.append(make_shortcut(desktop, icon))
    # **The way back in when the guard says no.** A copy of Pit Crew wedged in
    # a driver call cannot be killed and holds its claim for ever; this starts
    # anyway. Measured 24 Aug 2026: four refused launches, and the only
    # recovery anyone had was rebooting the machine.
    made.append(make_shortcut(desktop, icon, force=True))

    start = (Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows"
             / "Start Menu" / "Programs")
    if start.parent.exists():
        made.append(make_shortcut(start, icon))

    for path in made:
        print(f"shortcut:  {path}")
    print()
    print("Right-click the Desktop shortcut and choose 'Pin to taskbar'.")
    print("It launches without a console window; if something goes wrong,")
    print("run 'python -m pitcrew.app' in a terminal to see the error.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
