"""Which sound card the engineer speaks into, and which one hears the driver.

PortAudio enumerates the machine's devices **once**, when it is first
imported, and resolves "the default device" against that snapshot. Nothing in
this app ever asked it to look again. The driver puts the PSVR2 on after the
app is already running, so as far as the process is concerned that headset
does not exist.

That would be survivable if it failed. It does not: measured on this machine,
writing 1.00 s of tone to the **disconnected** default output completed in
2.53 s and raised nothing at all. The engineer speaks, the hit counter goes up,
the call is written to the race screen and the revision log, and the man in the
headset hears silence with every indicator green.

So two things happen here that did not before:

* **The device is named and resolved at every stream open**, not once at
  import. A device chosen at the rig is honoured, and a default that has moved
  since launch is picked up on the next call rather than at the next restart.
* **A `PortAudioError` re-enumerates and retries once.** `_terminate()` /
  `_initialize()` is the only way to make PortAudio look at Windows again, and
  a device that has genuinely gone is exactly the case where the first open
  fails and the second finds the one the driver just put on.

Neither of those can make silence impossible - a device that has gone can
still accept audio without complaining - so `voice.Voice` counts the calls that
produced no sound. This module is the half that can be fixed; the counter is
the half that can only be reported.
"""
from __future__ import annotations

import threading

from pitcrew.diagnostics import log

# What the driver chose, or None for "whatever Windows calls the default".
# An int is a PortAudio device index; a str is matched against device names.
# Held here rather than in `Settings` because the streams are opened deep in
# two engines that must not know what a settings object is; the controller
# pushes the chosen value in at start-up. See HANDOFF in the fix report.
_OUTPUT: object | None = None
_INPUT: object | None = None

# `_terminate()`/`_initialize()` tears down every PortAudio handle in the
# process, so it must not run while another thread is opening a stream.
_ENUMERATE_LOCK = threading.RLock()


def set_output_device(device: object | None) -> None:
    """Where the engineer speaks. Name fragment, index, or None for default."""
    global _OUTPUT
    _OUTPUT = device or None
    log("audio").info("engineer speaks into %s", describe(_OUTPUT))


def set_input_device(device: object | None) -> None:
    """Where push-to-talk listens. Name fragment, index, or None for default."""
    global _INPUT
    _INPUT = device or None
    log("audio").info("push-to-talk listens on %s", describe(_INPUT))


def output_device() -> object | None:
    return _OUTPUT


def input_device() -> object | None:
    return _INPUT


def describe(device: object | None) -> str:
    return "the system default" if device is None else repr(device)


def devices(kind: str) -> list[tuple[int, str]]:
    """(index, name) for every device that can do `kind` - "output"|"input".

    Enumerated fresh on each call, for the settings screen: the list the driver
    picks from has to include the headset he plugged in a moment ago.
    """
    import sounddevice as sd

    field = f"max_{kind}_channels"
    with _ENUMERATE_LOCK:
        _reinitialise(sd)
        found = []
        for index, info in enumerate(sd.query_devices()):
            if info.get(field, 0) > 0:
                found.append((index, str(info.get("name", index))))
    return found


def _resolve(sd, device: object | None, kind: str):
    """A device argument sounddevice will take, resolved against the machine
    as it is right now.

    None stays None - that is PortAudio's own default, which is re-resolved
    because the enumeration behind it was just refreshed. A name that no longer
    matches anything falls back to the default with a warning rather than
    raising: the driver would rather hear the call out of the wrong speaker
    than not hear it.
    """
    if device is None or isinstance(device, int):
        return device
    wanted = str(device).lower()
    field = f"max_{kind}_channels"
    for index, info in enumerate(sd.query_devices()):
        name = str(info.get("name", ""))
        if wanted in name.lower() and info.get(field, 0) > 0:
            return index
    log("audio").warning(
        "no %s device matching %r on this machine - using the default",
        kind, device)
    return None


def _reinitialise(sd) -> None:
    """Make PortAudio look at Windows again.

    The device list is built at import and never refreshed, so a headset
    connected after launch does not exist as far as the process is concerned.
    This is the only way to rebuild it.
    """
    try:
        sd._terminate()
        sd._initialize()
    except Exception as exc:                    # noqa: BLE001
        # Re-enumeration is a repair attempt, not a requirement: failing it
        # leaves the old device list, which is what we already had.
        log("audio").warning("could not re-enumerate audio devices: %s: %s",
                             type(exc).__name__, exc)


def open_output(samplerate: int, *, channels: int = 1, dtype: str = "int16"):
    """A started output stream on the chosen device, retried once."""
    import sounddevice as sd

    def attempt():
        stream = sd.OutputStream(
            samplerate=samplerate, channels=channels, dtype=dtype,
            device=_resolve(sd, _OUTPUT, "output"))
        stream.start()
        return stream

    return _retry_once(sd, attempt, "output")


def open_input(samplerate: int, *, channels: int = 1, dtype: str = "float32",
               blocksize: int = 0, callback=None):
    """A started input stream on the chosen device, retried once."""
    import sounddevice as sd

    def attempt():
        stream = sd.InputStream(
            samplerate=samplerate, channels=channels, dtype=dtype,
            blocksize=blocksize, callback=callback,
            device=_resolve(sd, _INPUT, "input"))
        stream.start()
        return stream

    return _retry_once(sd, attempt, "input")


def _retry_once(sd, attempt, kind: str):
    """Open, and on a PortAudio failure re-enumerate and try exactly once more.

    Once, not repeatedly: the driver is mid-corner and a retry loop on the
    voice thread is a stall he can hear. If the second attempt fails the caller
    raises, which is what makes the silence visible instead of logged.
    """
    with _ENUMERATE_LOCK:
        try:
            return attempt()
        except sd.PortAudioError as exc:
            log("audio").warning(
                "%s device failed to open (%s) - re-enumerating and trying "
                "once more", kind, exc)
            _reinitialise(sd)
            return attempt()
