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

**And the fourth rule, learned on 17 Aug 2026: it says WHICH endpoint it
read.** That session ended with the meter reporting silence on
`Speakers (ButtKicker PRO)` for thirteen minutes while the driver felt the
seat working. Both cannot be true of one endpoint, and the record could not
say whether they were one endpoint, because a device is resolved here by its
**friendly name** and Windows does not promise that a friendly name is
unique. Two instances of one card, or a card that re-enumerated onto a
different USB port while the old endpoint had not yet left the ACTIVE list,
give two endpoints spelling themselves identically - and this module took the
first match while PortAudio, walking its own list in its own order, may have
opened the other. The verdict "it played nothing" would then be a true
statement about an endpoint nobody was feeding.

So every match is counted, every endpoint ID is named in the log when there
is more than one, and the reading carries the identity of the endpoint it
came from. A single match is the ordinary case and reads exactly as before;
more than one is an admission that the answer is not safe to act on.
"""
from __future__ import annotations

import dataclasses
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


@dataclasses.dataclass(frozen=True)
class Reading:
    """One look at an endpoint, and everything needed to weigh it.

    `peak is None` means **could not measure**, which is the distinction this
    module was written to defend and which `poll_briefly` used to throw away
    by answering `0.0` for both. That collapse is not cosmetic: the caller
    treats a zero as "the card accepted the audio and played none of it",
    says so to the driver in a headset, and runs a recovery ladder against a
    device that may be working perfectly. A meter that cannot be opened is
    evidence about the meter and none at all about the transducer.
    """

    peak: float | None = None
    endpoint: str | None = None
    matches: int = 0
    detail: str = ""

    @property
    def measured(self) -> bool:
        return self.peak is not None

    @property
    def ambiguous(self) -> bool:
        """More than one active endpoint answers to the name asked for, so
        the stream may be feeding one of the others."""
        return self.matches > 1

    @classmethod
    def of(cls, value) -> "Reading":
        """A `Reading` from either a reading or a bare peak.

        Callers that have only a number - the settings screen's own probe,
        and the tests that drive the ladder without a sound card - hand one
        in, and it means the ordinary case: measured, one endpoint, no doubt
        about which.
        """
        if isinstance(value, cls):
            return value
        if value is None:
            return cls(peak=None, detail="not measured")
        return cls(peak=float(value), matches=1)


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

    def __init__(self, meters, uninitialise, endpoint: str | None = None,
                 matches: int = 1) -> None:
        # **Every endpoint of the name, not the first of them.**
        #
        # Windows does not promise friendly names are unique and on this rig
        # they are not: three PortAudio devices and, after a re-enumeration,
        # more than one ACTIVE MMDevice answer to `Speakers (ButtKicker PRO)`.
        # This walked the MMDevice list in Windows' order and metered
        # `found[0]`; PortAudio resolves the stream over its own list in its
        # own order, and PortAudio does not report back which MMDevice it
        # landed on - `StreamFacts` carries a name, not an endpoint id - so
        # there is no way to make the two agree by construction.
        #
        # The way out is not to need them to agree. A peak from ANY endpoint
        # of that name means the audio is reaching the hardware; silence from
        # ALL of them means it is reaching none. Both claims hold whichever
        # instance PortAudio picked, so the ambiguity stops mattering instead
        # of being warned about.
        #
        # This is the last of the three "two endpoints, two resolvers" doubts
        # from 17 Aug 2026, where the app told the driver his haptics were
        # dead while he could feel them working.
        self._meters = list(meters)
        self._uninitialise = uninitialise
        # Which endpoint gave the loudest reading, and how many carried the
        # name. Both travel out with the reading.
        self.endpoint = endpoint
        self.matches = matches
        self._ids = [None] * len(self._meters)

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
        ALL_STATES = 0x0F
        STATE_NAMES = {0x01: "active", 0x02: "disabled",
                       0x04: "not present", 0x08: "unplugged"}

        flow = RENDER if kind == "output" else CAPTURE

        def named(collection, wanted):
            """Every endpoint in `collection` whose friendly name matches."""
            found = []
            for index in range(collection.GetCount()):
                candidate = collection.Item(index)
                try:
                    value = candidate.OpenPropertyStore(0).GetValue(
                        byref(FRIENDLY_NAME))
                    name = cast(value.pwszVal, c_wchar_p).value or ""
                except Exception:               # noqa: BLE001
                    # An endpoint that will not name itself cannot be the
                    # one that was asked for by name.
                    continue
                if endpoint_key(name) != wanted:
                    continue
                try:
                    identity = str(candidate.GetId())
                except Exception:               # noqa: BLE001
                    identity = None
                try:
                    state = int(candidate.GetState())
                except Exception:               # noqa: BLE001
                    state = None
                found.append((candidate, identity, state))
            return found

        comtypes.CoInitialize()
        uninitialise = comtypes.CoUninitialize
        try:
            enumerator = CoCreateInstance(
                GUID("{BCDE0395-E52F-467C-8E3D-C4579291692E}"),
                IMMDeviceEnumerator, CLSCTX_ALL)

            endpoint = None
            identity = None
            matches = 1
            if device:
                wanted = endpoint_key(device)
                found = named(enumerator.EnumAudioEndpoints(flow, ACTIVE),
                              wanted)
                matches = len(found)
                if not found:
                    # **Say why, not just that.** A name that matches nothing
                    # active is a different fault from a name that matches a
                    # disabled or unplugged endpoint, and the second one is
                    # the driver switching the amp off at the wall.
                    others = named(
                        enumerator.EnumAudioEndpoints(flow, ALL_STATES),
                        wanted)
                    where = ", ".join(
                        STATE_NAMES.get(state, f"state {state}")
                        for _c, _i, state in others) or "not present at all"
                    log("audio").info(
                        "no active endpoint named %r to meter - %d endpoint(s"
                        ") of that name on this machine: %s",
                        device, len(others), where)
                    uninitialise()
                    return None
                endpoint, identity, _state = found[0]
                if matches > 1:
                    # **All of them, not the first of them.** The stream is
                    # resolved by PortAudio walking its own list in its own
                    # order; this walks the MMDevice list in Windows'. They
                    # can disagree, and PortAudio does not say which MMDevice
                    # it opened - so instead of metering one and hedging the
                    # verdict, meter every one. A peak from any of them means
                    # the audio is reaching the hardware; silence from all of
                    # them means it is reaching none. Both hold whichever
                    # instance the stream picked.
                    log("audio").info(
                        "%d active %s endpoints answer to the name %r: %s. "
                        "Metering all of them, so a silent reading is about "
                        "the device rather than about which instance was "
                        "picked.",
                        matches, kind, device,
                        "; ".join(str(i) for _c, i, _s in found))
                candidates = [(c, i) for c, i, _s in found]
            else:
                endpoint = enumerator.GetDefaultAudioEndpoint(flow, MULTIMEDIA)
                try:
                    identity = str(endpoint.GetId())
                except Exception:               # noqa: BLE001
                    identity = None
                candidates = [(endpoint, identity)]

            meters, ids = [], []
            for candidate, candidate_id in candidates:
                try:
                    meters.append(candidate.Activate(
                        byref(IAudioMeterInformation._iid_), CLSCTX_ALL,
                        None).QueryInterface(IAudioMeterInformation))
                    ids.append(candidate_id)
                except Exception as exc:        # noqa: BLE001
                    # One endpoint of several refusing a meter is not a
                    # failure of the whole reading - it is one fewer witness.
                    log("audio").debug(
                        "no meter on endpoint %s: %s", candidate_id, exc)
            if not meters:
                raise OSError(
                    f"no endpoint of the name {device!r} would open a meter")
        except Exception:
            uninitialise()
            raise
        watcher = cls(meters, uninitialise, endpoint=identity, matches=matches)
        watcher._ids = ids
        return watcher

    def read(self) -> float:
        """The loudest of every endpoint answering to the name.

        A meter that stops answering mid-call is not evidence of silence, so
        it reads as "nothing seen this tick" and the caller decides on the
        whole run.
        """
        best = 0.0
        for position, meter in enumerate(self._meters):
            try:
                value = float(meter.GetPeakValue())
            except Exception:                   # noqa: BLE001
                continue
            if value > best:
                best = value
                if self._ids[position] is not None:
                    # Name the one actually rendering, so a log line about a
                    # working seat says which instance is carrying it.
                    self.endpoint = self._ids[position]
        return best

    def close(self) -> None:
        self._meters = []
        try:
            self._uninitialise()
        except Exception:                       # noqa: BLE001
            pass


def poll_briefly(device: str | None, seconds: float = 0.4) -> Reading:
    """The highest peak seen on a card over a short window.

    For a caller that wants to know whether anything at all is coming out of a
    device without making a sound itself.

    **It used to answer `0.0` when the meter could not be opened at all**, and
    that one line is the difference between "the card played nothing" and "I
    could not look". The transducer's health check reads a zero as the first,
    writes an ERROR the driver cannot see, runs three device rebuilds and
    then tells him through the headset that the haptics are gone. Every one of
    those steps is wrong if the meter simply was not there - and the meter not
    being there is the ordinary case on a machine without `comtypes`, on a
    non-Windows box, and on the exact device event this whole module is
    watching for. `peak is None` now says so.
    """
    watcher = _Meter.open(device, "output")
    if watcher is None:
        return Reading(peak=None, detail="no peak meter for this device")
    deadline = time.monotonic() + seconds
    peak = 0.0
    try:
        while time.monotonic() < deadline:
            peak = max(peak, watcher.read())
            time.sleep(POLL_S)
    finally:
        watcher.close()
    return Reading(peak=peak, endpoint=watcher.endpoint,
                   matches=watcher.matches)
