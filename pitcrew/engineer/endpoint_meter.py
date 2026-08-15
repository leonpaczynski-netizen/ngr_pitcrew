"""Whether the sound the app just made actually reached the sound card.

Everything else in this app can only report what it was told. `open_output`
returns a started stream, `stream.write` returns without complaint, the voice
engine returns from `speak`, and every one of those is true of a card that is
discarding the audio. Measured on this machine, 15 Aug 2026: a USB headset
that Windows reported ACTIVE, default, both channels at 97% and unmuted, with
the USB device present and problem code 0, accepted three seconds of
full-scale tone through MME, DirectSound and WASAPI alike and played none of
it - Windows re-routed the stream to the fallback speakers. Its microphone
captured 0.00 s in the same state. The Settings screen said "Said it through
voice-pack" in green and the man in the headset heard nothing.

There is exactly one instrument on Windows that can tell the difference, and
it is not in the audio API the app plays through: `IAudioMeterInformation`
reports the peak sample the **endpoint** is rendering. During that same test
the dead endpoint metered 0.0000 across 28 samples while a working one metered
0.89 across 15 of 22. That gap is what this module reads.

Three rules it follows, all of them because the answer is shown to a driver
who is about to go racing on it:

* **"Cannot measure" is not "failed".** Anything other than Windows, a missing
  `comtypes`, a COM error, an endpoint that offers no meter - all return
  `None`, which callers must report as unverified rather than as silence.
* **It never plays anything itself.** The caller supplies the sound, so what
  is measured is the real path - the real engine, the real device setting,
  the real stream - and not a probe that could succeed where the app fails.
* **It meters the endpoint the app aimed at**, not the one that made a noise.
  When Windows re-routes a stream off a dead endpoint the audio is audible
  somewhere, and reporting that as success is how this went unnoticed. The
  question is whether the chosen card played it.
"""
from __future__ import annotations

import threading
import time

from pitcrew.diagnostics import log

# Anything at or below this is silence. Endpoint meters read exactly 0.0 when
# nothing is rendering; the margin is for a card whose mixer idles just above.
SILENT_PEAK = 0.001

# How often to read the meter while the sound plays. The meter reports the
# peak since the last read, so this only has to be fast enough not to miss a
# short beep - 60 ms of square wave at 20 Hz is sampled three times.
POLL_S = 0.05


def confirm_reached_endpoint(play, *, device: str | None,
                             kind: str = "output") -> tuple[bool | None, str]:
    """Run `play()` and report whether audio reached the chosen card.

    Returns `(heard, detail)`:

    * `(True, "")` - the endpoint metered signal. The card played it.
    * `(False, why)` - the endpoint metered nothing for the whole call. It
      accepted the audio and dropped it, which is the failure that looks
      identical to success everywhere else in the app.
    * `(None, why)` - it could not be measured. **Not a failure**; say
      "unverified", never "silent".

    `play` is run on a worker thread and this samples the meter meanwhile, so
    the sound being measured is the app's own, made the way it normally is.
    Whatever `play` raises is re-raised here, because a call that never played
    is the caller's news to break, not this module's.
    """
    watcher = _Meter.open(device, kind)
    if watcher is None:
        # `_Meter.open` has already logged why.
        return None, "no peak meter for this device on this machine"

    failure: list[BaseException] = []
    done = threading.Event()

    def run() -> None:
        try:
            play()
        except BaseException as exc:            # noqa: BLE001 - re-raised
            failure.append(exc)
        finally:
            done.set()

    worker = threading.Thread(target=run, name="PitCrewAudioProbe",
                              daemon=True)
    peak = 0.0
    try:
        worker.start()
        while not done.wait(POLL_S):
            peak = max(peak, watcher.read())
        # One more read: a short sound can finish inside the last interval.
        peak = max(peak, watcher.read())
    finally:
        watcher.close()

    if failure:
        raise failure[0]

    if peak > SILENT_PEAK:
        return True, f"peaked at {peak:.3f} on the endpoint"
    return False, (
        f"the endpoint metered {peak:.4f} for the whole call - it accepted "
        f"the audio and played none of it")


class _Meter:
    """A live `IAudioMeterInformation` on one render or capture endpoint."""

    def __init__(self, meter, uninitialise) -> None:
        self._meter = meter
        self._uninitialise = uninitialise

    @classmethod
    def open(cls, device: str | None, kind: str) -> "_Meter | None":
        """The meter for the named card, or None if there is not one.

        A name is matched the way `audio_devices` matches one - on the first
        31 characters, because MME truncates there and the stored name may
        have come from either spelling. An empty name means the Windows
        default, which is the endpoint the app would play to.
        """
        try:
            import comtypes                     # noqa: F401
        except ImportError:
            log("audio").info(
                "comtypes is not installed, so playback cannot be verified")
            return None
        try:
            return cls._open_windows(device, kind)
        except Exception as exc:                # noqa: BLE001
            # Every failure here is "cannot measure", which is reported as
            # unverified. It must never be mistaken for "played nothing".
            log("audio").info("no endpoint meter for %r: %s: %s",
                              device or "the system default",
                              type(exc).__name__, exc)
            return None

    @classmethod
    def _open_windows(cls, device: str | None, kind: str) -> "_Meter | None":
        from ctypes import byref, cast, c_float, c_ulong, c_ushort, c_void_p
        from ctypes import POINTER, Structure, c_uint32, c_wchar_p
        from ctypes.wintypes import DWORD, LPCWSTR

        import comtypes
        from comtypes import (CLSCTX_ALL, COMMETHOD, GUID, HRESULT, IUnknown,
                              CoCreateInstance)

        from pitcrew.engineer.audio_devices import endpoint_key

        class IAudioMeterInformation(IUnknown):
            _iid_ = GUID("{C02216F6-8C67-4B5B-9D00-D008E73E0064}")
            _methods_ = (
                COMMETHOD([], HRESULT, "GetPeakValue",
                          (["out"], POINTER(c_float), "peak")),
            )

        class PROPERTYKEY(Structure):
            _fields_ = [("fmtid", GUID), ("pid", DWORD)]

        class PROPVARIANT(Structure):
            _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort),
                        ("r3", c_ushort), ("pwszVal", c_void_p),
                        ("pad", c_ulong * 3)]

        class IPropertyStore(IUnknown):
            _iid_ = GUID("{886d8eeb-8cf2-4446-8d02-cdba1dbdcf99}")
            _methods_ = (
                COMMETHOD([], HRESULT, "GetCount",
                          (["out"], POINTER(DWORD), "n")),
                COMMETHOD([], HRESULT, "GetAt", (["in"], DWORD, "i"),
                          (["out"], POINTER(PROPERTYKEY), "key")),
                COMMETHOD([], HRESULT, "GetValue",
                          (["in"], POINTER(PROPERTYKEY), "key"),
                          (["out"], POINTER(PROPVARIANT), "value")),
            )

        class IMMDevice(IUnknown):
            _iid_ = GUID("{D666063F-1587-4E43-81F1-B948E807363F}")
            _methods_ = (
                COMMETHOD([], HRESULT, "Activate",
                          (["in"], POINTER(GUID), "iid"),
                          (["in"], DWORD, "ctx"), (["in"], c_void_p, "params"),
                          (["out"], POINTER(POINTER(IUnknown)), "iface")),
                COMMETHOD([], HRESULT, "OpenPropertyStore",
                          (["in"], DWORD, "access"),
                          (["out"], POINTER(POINTER(IPropertyStore)), "store")),
                COMMETHOD([], HRESULT, "GetId",
                          (["out"], POINTER(LPCWSTR), "id")),
                COMMETHOD([], HRESULT, "GetState",
                          (["out"], POINTER(DWORD), "state")),
            )

        class IMMDeviceCollection(IUnknown):
            _iid_ = GUID("{0BD7A1BE-7A1A-44DB-8397-CC5392387B5E}")
            _methods_ = (
                COMMETHOD([], HRESULT, "GetCount",
                          (["out"], POINTER(c_uint32), "n")),
                COMMETHOD([], HRESULT, "Item", (["in"], c_uint32, "i"),
                          (["out"], POINTER(POINTER(IMMDevice)), "device")),
            )

        class IMMDeviceEnumerator(IUnknown):
            _iid_ = GUID("{A95664D2-9614-4F35-A746-DE8DB63617E6}")
            _methods_ = (
                COMMETHOD([], HRESULT, "EnumAudioEndpoints",
                          (["in"], DWORD, "flow"), (["in"], DWORD, "mask"),
                          (["out"], POINTER(POINTER(IMMDeviceCollection)), "c")),
                COMMETHOD([], HRESULT, "GetDefaultAudioEndpoint",
                          (["in"], DWORD, "flow"), (["in"], DWORD, "role"),
                          (["out"], POINTER(POINTER(IMMDevice)), "device")),
            )

        FRIENDLY_NAME = PROPERTYKEY(
            GUID("{a45c254e-df1c-4efd-8020-67d146a850e0}"), 14)
        RENDER, CAPTURE = 0, 1
        MULTIMEDIA = 1
        ACTIVE = 0x01

        flow = RENDER if kind == "output" else CAPTURE

        comtypes.CoInitialize()
        uninitialise = comtypes.CoUninitialize
        try:
            enumerator = CoCreateInstance(
                GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}"),
                IMMDeviceEnumerator, CLSCTX_ALL)

            endpoint = None
            if device:
                wanted = endpoint_key(device)
                collection = enumerator.EnumAudioEndpoints(flow, ACTIVE)
                for index in range(collection.GetCount()):
                    candidate = collection.Item(index)
                    try:
                        value = candidate.OpenPropertyStore(0).GetValue(
                            byref(FRIENDLY_NAME))
                        name = cast(value.pwszVal, c_wchar_p).value or ""
                    except Exception:           # noqa: BLE001
                        # An endpoint that will not name itself cannot be the
                        # one that was asked for by name.
                        continue
                    if endpoint_key(name) == wanted:
                        endpoint = candidate
                        break
                if endpoint is None:
                    log("audio").info(
                        "no active endpoint named %r to meter", device)
                    uninitialise()
                    return None
            else:
                endpoint = enumerator.GetDefaultAudioEndpoint(flow, MULTIMEDIA)

            meter = endpoint.Activate(
                byref(IAudioMeterInformation._iid_), CLSCTX_ALL,
                None).QueryInterface(IAudioMeterInformation)
        except Exception:
            uninitialise()
            raise
        return cls(meter, uninitialise)

    def read(self) -> float:
        try:
            return float(self._meter.GetPeakValue())
        except Exception:                       # noqa: BLE001
            # A meter that stops answering mid-call is not evidence of
            # silence, so read as "nothing seen this tick" and let the caller
            # decide on the whole run.
            return 0.0

    def close(self) -> None:
        self._meter = None
        try:
            self._uninitialise()
        except Exception:                       # noqa: BLE001
            pass


def poll_briefly(device: str | None, seconds: float = 0.4) -> float:
    """The highest peak seen on a card over a short window, or 0.0.

    For a caller that wants to know whether anything at all is coming out of a
    device without making a sound itself.
    """
    watcher = _Meter.open(device, "output")
    if watcher is None:
        return 0.0
    deadline = time.monotonic() + seconds
    peak = 0.0
    try:
        while time.monotonic() < deadline:
            peak = max(peak, watcher.read())
            time.sleep(POLL_S)
    finally:
        watcher.close()
    return peak
