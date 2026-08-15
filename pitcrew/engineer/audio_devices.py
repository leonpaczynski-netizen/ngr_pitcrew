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

So three things happen here that did not before:

* **The device is named and resolved at every stream open**, not once at
  import. A device chosen at the rig is honoured, and a default that has moved
  since launch is picked up on the next call rather than at the next restart.
* **A `PortAudioError` re-enumerates and retries once.** `_terminate()` /
  `_initialize()` is the only way to make PortAudio look at Windows again, and
  a device that has genuinely gone is exactly the case where the first open
  fails and the second finds the one the driver just put on.
* **One card is one entry, and opening it tries every route to it.** See
  `devices` and `_candidates` - the fix for a picker that offered the same
  headset four times and could not actually select between them.

None of those can make silence impossible - a device that has gone can still
accept audio without complaining - so `voice.Voice` counts the calls that
produced no sound and `endpoint_meter` asks Windows whether the audio ever
arrived. This module is the half that can be fixed; those two are the half
that can only be reported.
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

# "No device argument was given", which is not the same as `None` - `None` is
# a real choice meaning PortAudio's own default. Without a distinct sentinel
# a caller could not ask for the system default on a card other than the
# engineer's, and `device=None` would silently mean "the engineer's".
_DEFAULT = object()

# `_terminate()`/`_initialize()` tears down every PortAudio handle in the
# process, so it must not run while another thread is opening a stream.
_ENUMERATE_LOCK = threading.RLock()

# **One lock per card, not one across the process.**
#
# It began as a single global, on the belief that overlapping PortAudio
# streams crash the host rather than mixing. That is true of two streams on
# **the same device** - PortAudio's own documentation says a device may be
# used by at most one stream - and it was the right fix for the two sources of
# sound that existed then, the engineer's voice and the shift beep, which
# share one output and can fire on different threads in the same corner.
#
# It is not true across devices. Measured on this machine, 15 Aug 2026: two
# concurrent WASAPI streams on two different cards ran for two seconds and
# delivered 205 and 132 callbacks with no status flags between them.
#
# The distinction matters now because the tactile transducer is a second card
# that has to hold a stream open while the engineer is talking into the first.
# A process-wide lock would have made the two mutually exclusive, so the
# haptics would have stopped dead every time a call was made - during exactly
# the moments the driver most wants both.
_DEVICE_LOCKS: dict[str, threading.Lock] = {}
_DEVICE_LOCKS_GUARD = threading.Lock()


def lock_for(device: object | None) -> threading.Lock:
    """The lock covering one card. Two names for one card share one lock."""
    key = endpoint_key(device) if isinstance(device, str) else repr(device)
    with _DEVICE_LOCKS_GUARD:
        return _DEVICE_LOCKS.setdefault(key, threading.Lock())


# Streams that outlive the sound they are making. A spoken line opens a stream
# and closes it a second later, so re-enumerating between lines costs nothing;
# a transducer holds one open for the whole session, and re-enumerating under
# it is a silent stop. Anything registered here is suspended and resumed
# around a rebuild - see `_reinitialise`.
_SUSTAINED: list = []
_SUSTAINED_GUARD = threading.Lock()


def register_sustained(holder) -> None:
    """Declare a stream that must survive the device list being rebuilt.

    `holder` needs `suspend()` and `resume()`. It is on the holder to reopen
    against whatever the machine looks like afterwards, because the card it
    was using may be the one that just went away.
    """
    with _SUSTAINED_GUARD:
        if holder not in _SUSTAINED:
            _SUSTAINED.append(holder)


def unregister_sustained(holder) -> None:
    with _SUSTAINED_GUARD:
        if holder in _SUSTAINED:
            _SUSTAINED.remove(holder)

# Which route to a card to try first. A headset is reachable through several
# host APIs and they are **not** equivalent. Measured on this machine against
# the endpoint's own peak meter, 15 Aug 2026, one second of full-scale tone to
# a card known to be working:
#
# | host API    | result                                           |
# |-------------|--------------------------------------------------|
# | WASAPI      | refuses the open: "Invalid sample rate"           |
# | DirectSound | opens, accepts all of it, **meters 0.0000**       |
# | MME         | opens, meters 0.733                               |
#
# * **WASAPI** is the modern one and the lowest latency, but shared mode only
#   accepts the endpoint's own mix rate, and 22050 Hz - what the Piper models
#   render at - is not it. It fails loudly and cheaply, which is why it is
#   still first: when it does open it is the best route there is.
# * **DirectSound** is the trap. The write returns in 0.08 s for 1.06 s of
#   audio because it only buffers, and PortAudio's `stop()` discards that
#   buffer instead of draining it. It reports complete success and makes no
#   sound whatsoever - the exact failure this whole module exists to prevent -
#   so it sits below MME despite the better latency.
# * **MME** resamples, so it takes whatever the synthesiser produces, and its
#   blocking write really does block until the audio has played. Its latency
#   is the worst of the three - measured, 1.5 s to open - but a call that
#   arrives is worth more than one that does not.
# * **WDM-KS** cannot do blocking writes at all: "Blocking API not supported
#   yet". Every write path in this app is blocking, so it is last, and it is
#   never offered in the picker.
#
# `_open_first_that_works` walks down this order, so a rate WASAPI refuses
# costs one failed open and lands on MME rather than costing the driver the
# call.
_HOST_API_ORDER = ("Windows WASAPI", "MME", "Windows DirectSound",
                   "Windows WDM-KS")

# Host APIs and names that are routing pseudo-devices or per-pin exports
# rather than the card the driver would recognise. Offering these is how a
# picker ends up with four near-identical rows for one headset.
_HIDE_FROM_PICKER = ("Windows WDM-KS",)
_HIDE_NAMES = ("microsoft sound mapper", "primary sound driver",
               "primary sound capture driver")

# MME truncates device names to 31 characters, so one endpoint is
# 'Headphones (JBL Endurance Run 3' under MME and
# 'Headphones (JBL Endurance Run 3C)' under DirectSound and WASAPI. Comparing
# on the truncated form is what lets one stored name find every route to one
# card.
_MME_NAME_LIMIT = 31

# The route that last worked, per (name, kind). Cleared whenever the device
# list is rebuilt. Without it every beep pays for WASAPI refusing 22050 Hz
# again before falling to DirectSound.
_WORKING: dict[tuple, int] = {}


def set_output_device(device: object | None) -> None:
    """Where the engineer speaks. Name fragment, index, or None for default."""
    global _OUTPUT
    _OUTPUT = device or None
    _WORKING.clear()
    log("audio").info("engineer speaks into %s", describe(_OUTPUT))


def set_input_device(device: object | None) -> None:
    """Where push-to-talk listens. Name fragment, index, or None for default."""
    global _INPUT
    _INPUT = device or None
    _WORKING.clear()
    log("audio").info("push-to-talk listens on %s", describe(_INPUT))


def output_device() -> object | None:
    return _OUTPUT


def input_device() -> object | None:
    return _INPUT


def describe(device: object | None) -> str:
    return "the system default" if device is None else repr(device)


def endpoint_key(name: str) -> str:
    """The identity of a sound card, independent of the route taken to it.

    Two rows in PortAudio's list are the same piece of hardware when this
    matches - which is how the picker shows one headset once, and how a name
    stored from any host API still finds the others.
    """
    return str(name).strip().lower()[:_MME_NAME_LIMIT].rstrip()


def devices(kind: str) -> list[tuple[int, str]]:
    """(index, name) for every card that can do `kind` - "output"|"input".

    **One row per card, not one per route to it.** PortAudio lists the same
    headset under every host API it can be reached through, which on this
    machine meant four near-identical rows: an MME one truncated to 31
    characters, a DirectSound one, a WASAPI one, and two WDM-KS pin exports.
    The driver could not tell them apart, and picking the wrong one was
    silent - WASAPI refuses the synthesiser's sample rate, WDM-KS refuses
    blocking writes at all, and the old name match returned whichever came
    first regardless of which row was clicked.

    So the routes are collapsed and the fullest spelling of the name is shown.
    Which route is actually taken is `_candidates`' business, decided at open
    time against the machine as it is then.

    Enumerated fresh on each call, for the settings screen: the list the driver
    picks from has to include the headset he plugged in a moment ago.
    """
    import sounddevice as sd

    field = f"max_{kind}_channels"
    with _ENUMERATE_LOCK:
        _reinitialise(sd)
        apis = _host_api_names(sd)
        seen: dict[str, tuple[int, str]] = {}
        for index, info in enumerate(sd.query_devices()):
            if info.get(field, 0) <= 0:
                continue
            name = str(info.get("name", index))
            if apis.get(info.get("hostapi")) in _HIDE_FROM_PICKER:
                continue
            if any(hidden in name.lower() for hidden in _HIDE_NAMES):
                continue
            key = endpoint_key(name)
            previous = seen.get(key)
            # Keep the fullest spelling: MME's is cut at 31 characters and is
            # the one least worth showing him.
            if previous is None:
                seen[key] = (index, name)
            elif len(name) > len(previous[1]):
                seen[key] = (previous[0], name)
    return list(seen.values())


def _host_api_names(sd) -> dict[int, str]:
    return {i: str(api.get("name", ""))
            for i, api in enumerate(sd.query_hostapis())}


def _candidates(sd, device: object | None, kind: str) -> list:
    """Every route to the chosen card, best first.

    None stays None - that is PortAudio's own default, which is re-resolved
    because the enumeration behind it was just refreshed. An int is taken as
    given. A name matches on the truncated form, so a name stored under any
    host API finds all of them, and the list comes back in `_HOST_API_ORDER`
    so the caller can walk down it.

    A name that no longer matches anything falls back to the default with a
    warning rather than raising: the driver would rather hear the call out of
    the wrong speaker than not hear it.
    """
    if device is None or isinstance(device, int):
        return [device]

    wanted = endpoint_key(device)
    field = f"max_{kind}_channels"
    apis = _host_api_names(sd)
    found = []
    for index, info in enumerate(sd.query_devices()):
        if info.get(field, 0) <= 0:
            continue
        if endpoint_key(info.get("name", "")) != wanted:
            continue
        api = apis.get(info.get("hostapi"), "")
        rank = (_HOST_API_ORDER.index(api) if api in _HOST_API_ORDER
                else len(_HOST_API_ORDER))
        found.append((rank, index))
    if not found:
        log("audio").warning(
            "no %s device matching %r on this machine - using the default",
            kind, device)
        return [None]
    found.sort()
    ordered = [index for _rank, index in found]
    # Whatever worked last time goes first: the ranking is a guess about the
    # machine, and one successful open is a measurement of it.
    remembered = _WORKING.get((wanted, kind))
    if remembered in ordered:
        ordered.remove(remembered)
        ordered.insert(0, remembered)
    return ordered


def _resolve(sd, device: object | None, kind: str):
    """The single best route to the chosen card, for callers that want one
    device argument rather than the ordered list `_candidates` returns."""
    return _candidates(sd, device, kind)[0]


def _reinitialise(sd) -> None:
    """Make PortAudio look at Windows again, without killing what is playing.

    The device list is built at import and never refreshed, so a headset
    connected after launch does not exist as far as the process is concerned.
    `_terminate()`/`_initialize()` is the only way to rebuild it.

    **And it closes every open stream in the process while doing so.**
    PortAudio says as much - "the final matching call to Pa_Terminate() will
    automatically close any PortAudio streams that are still open" - and it
    was measured here on 15 Aug 2026: two streams open, terminate, re-init,
    and both went to **zero callbacks with nothing raised**. Reading `.active`
    afterwards gave `PortAudioError -9988, invalid stream pointer`, which is
    the first moment anything says a word about it.

    That was survivable while every stream in the app lived for the length of
    one spoken line. It is not survivable for a tactile transducer, which
    holds one stream open for the whole session: the driver would open the
    settings screen, the picker would enumerate, and the haptics would stop
    for the rest of the race with nothing logged and no exception raised.

    So sustained streams are suspended around the rebuild and resumed after,
    rather than silently destroyed by it. Everything short-lived is unchanged.
    """
    _WORKING.clear()
    with _SUSTAINED_GUARD:
        holders = list(_SUSTAINED)
    for holder in holders:
        try:
            holder.suspend()
        except Exception as exc:                # noqa: BLE001
            log("audio").warning("could not suspend %s before re-enumerating: "
                                 "%s", holder, exc)
    try:
        sd._terminate()
        sd._initialize()
    except Exception as exc:                    # noqa: BLE001
        # Re-enumeration is a repair attempt, not a requirement: failing it
        # leaves the old device list, which is what we already had.
        log("audio").warning("could not re-enumerate audio devices: %s: %s",
                             type(exc).__name__, exc)
    finally:
        # In a `finally` on purpose. A rebuild that raised half-way would
        # otherwise leave the transducer suspended for the rest of the
        # session - the exact silent-stop this whole mechanism exists to
        # prevent, arrived at by a different route.
        for holder in holders:
            try:
                holder.resume()
            except Exception as exc:            # noqa: BLE001
                log("audio").error(
                    "%s did not come back after re-enumerating audio devices: "
                    "%s. It is stopped until it is restarted.", holder, exc)


def open_output(samplerate: int, *, channels: int = 1, dtype: str = "int16",
                device: object | None = _DEFAULT, blocksize: int = 0,
                callback=None, finished_callback=None,
                extra_settings=None):
    """A started output stream, retried once.

    `device` names a card explicitly; omitting it uses the one the driver
    chose for the engineer. That distinction is the whole point of the
    parameter: this module used to read a single module-level global and had
    no way to express "the other card", so the transducer and the engineer's
    voice could not both be open. They are different hardware doing different
    jobs and neither should wait for the other.

    `callback` opens a stream PortAudio pulls from on its own thread rather
    than one written to by the caller - which is how a continuous signal is
    generated without a Python thread trying to keep up with the card.
    """
    import sounddevice as sd

    chosen = _OUTPUT if device is _DEFAULT else device

    def attempt():
        return _open_first_that_works(
            sd, chosen, "output",
            lambda resolved: sd.OutputStream(
                samplerate=samplerate, channels=channels, dtype=dtype,
                device=resolved, blocksize=blocksize, callback=callback,
                finished_callback=finished_callback,
                extra_settings=extra_settings))

    return _retry_once(sd, attempt, "output")


def open_input(samplerate: int, *, channels: int = 1, dtype: str = "float32",
               blocksize: int = 0, callback=None):
    """A started input stream on the chosen device, retried once."""
    import sounddevice as sd

    def attempt():
        return _open_first_that_works(
            sd, _INPUT, "input",
            lambda device: sd.InputStream(
                samplerate=samplerate, channels=channels, dtype=dtype,
                blocksize=blocksize, callback=callback, device=device))

    return _retry_once(sd, attempt, "input")


def _open_first_that_works(sd, chosen, kind: str, build):
    """Walk the routes to the chosen card and start the first that opens.

    The last route's failure is re-raised rather than swallowed, so a card
    that cannot be opened at all is still loud. Anything that opens is
    remembered, because the next beep should not re-discover that WASAPI will
    not take 22050 Hz.
    """
    routes = _candidates(sd, chosen, kind)
    for position, device in enumerate(routes):
        try:
            stream = build(device)
            stream.start()
        except sd.PortAudioError as exc:
            if position == len(routes) - 1:
                raise
            log("audio").info(
                "%s device %r would not open (%s) - trying the next route",
                kind, device, exc)
            continue
        if isinstance(chosen, str):
            _WORKING[(endpoint_key(chosen), kind)] = device
        return stream
    # `_candidates` returns [None] rather than [], so this is unreachable
    # unless it is changed to return nothing.
    raise RuntimeError(f"no {kind} route to {describe(chosen)}")


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
