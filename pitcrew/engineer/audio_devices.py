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

import contextlib
import dataclasses
import threading
import time

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


def enumeration_lock():
    """The lock that serialises device-list rebuilds against stream opens.

    Public for exactly one reason: lock ORDER. `devices` takes this lock and
    then calls `suspend` on every sustained holder - the holder's own lock -
    while a holder that opens a stream from inside its own lock arrives here
    needing this one. Same two locks, opposite order, two threads: the app
    stops for good, and the likeliest collision is the driver opening the
    settings screen in the same seconds a wedge recovery is reopening the
    transducer. So any holder that will open while holding its own lock must
    take this lock FIRST; it is re-entrant, so the nested acquisitions inside
    `open_output` on the same thread cost nothing.
    """
    return _ENUMERATE_LOCK

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


# **The beep goes first, and the line it cuts is said again.**
#
# The voice and the beep share one card, so they share one `lock_for` - which
# until now meant a beep arriving mid-sentence WAITED for the sentence. That
# is the wrong way round twice over. A spoken call is a paragraph the driver
# can hear a second late and still act on; the beep is an instruction about
# the rpm the engine is at *right now*, and `shift_beep`'s own rule is that a
# beep played late names a shift point that has already gone past. So a
# two-second line did not delay the beep, it destroyed it - and the driver
# heard nothing wrong, because a beep that arrives at the wrong rpm sounds
# exactly like a beep.
#
# So the beep raises a flag on the card it wants, the voice reads that flag
# BETWEEN writes, and a voice that sees it closes its own stream and gets out
# of the way. **Only the thread that opened a stream ever closes it** - the
# beep never reaches into the voice's stream, because a close landing inside
# another thread's blocking `write` is the SimHub close-from-send deadlock
# this codebase has already paid for once.
#
# The cut line is not lost: it is marked `interrupted`, which raises
# `voice.LineCut`, which re-queues it with its ORIGINAL timestamp - so the
# staleness rule decides whether it is still worth saying, exactly as it does
# for a line cut by a device rebuild. The cost of a pre-empted call is
# therefore one clip of silence and a repeat, and the cost of not pre-empting
# is a shift point.
_PRIORITY: dict[str, int] = {}
_PRIORITY_GUARD = threading.Lock()


@contextlib.contextmanager
def priority_on(device: object | None):
    """Ask whoever holds `device` to finish early. Released on the way out.

    A counter rather than a flag because two beeps a corner apart can overlap
    with a long line, and the first one to leave must not clear the second
    one's claim.
    """
    key = endpoint_key(device) if isinstance(device, str) else repr(device)
    with _PRIORITY_GUARD:
        _PRIORITY[key] = _PRIORITY.get(key, 0) + 1
    try:
        yield
    finally:
        with _PRIORITY_GUARD:
            remaining = _PRIORITY.get(key, 0) - 1
            if remaining > 0:
                _PRIORITY[key] = remaining
            else:
                _PRIORITY.pop(key, None)


def priority_wanted(device: object | None) -> bool:
    """True when something more urgent is waiting for `device`.

    Read by a long write loop between chunks. Cheap on purpose: it is on the
    voice's inner loop and must not cost more than the check is worth.
    """
    key = endpoint_key(device) if isinstance(device, str) else repr(device)
    with _PRIORITY_GUARD:
        return _PRIORITY.get(key, 0) > 0


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


# Streams that ARE the sound they are making - the other half of `_SUSTAINED`.
#
# The comment above says a spoken line opens a stream and closes it a second
# later, so re-enumerating between lines costs nothing. True, and it was the
# whole justification for leaving the voice off the sustained register. What it
# does not cover is a re-enumeration landing DURING a line: `_terminate()`
# closes that stream mid-sentence, the engineer stops in the middle of a word,
# and nothing is raised and nothing is logged.
#
# **The path that does it is the settings screen, and it is the shipped app.**
# `ui/settings_screen.py::_audio_plate` fills its two device pickers by calling
# `devices("output")` and `devices("input")` while `_build` runs, and `devices`
# re-enumerates on every call - deliberately, so that the list offered includes
# the headset the driver plugged in a moment ago. So opening the settings
# screen mid-session runs `_reinitialise` twice, and `_reinitialise` measured
# its own consequence on 15 Aug 2026: two streams open, terminate, re-init,
# and both went to zero callbacks with nothing raised, `.active` afterwards
# giving `PortAudioError -9988`. That docstring drew the conclusion for the
# transducer and registered it as sustained. **It missed the voice**, which is
# not registered, and which is the only channel the driver has under a helmet.
#
# `TransducerWatchdog` (881e213) is a second way in - `recover()` and
# `rebuild()` both reach `open_output`, and a failed open re-enumerates - and
# it is written here as the possibility it is rather than as a sighting.
# **The engineer talking over the driver on 17 Aug 2026 was not either of
# them.** That was the test suite on his real output device, and it is fixed
# in `pitcrew/tests/conftest.py` at 81ab637; the diagnosis that blamed the
# watchdog for it is withdrawn. The hazard outlived the withdrawal because the
# settings-screen path has a measured mechanism and a human who reaches for it
# mid-session, which is a stronger case than the one that was retracted.
#
# So a rebuild now WAITS for the sound in flight to finish before tearing
# PortAudio down. **Nothing that arrives here is urgent enough to refuse.** A
# picker being populated is a screen the driver is already reading; a haptics
# recovery has had the transducer silent for its whole conviction window
# before it ever got this far. Another two seconds costs neither of them
# anything, and it is the difference between a call heard and half a call. If
# the wait runs out the rebuild goes ahead and marks what it is about to cut,
# so the caller can say it again - see `voice.LineCut`.
#
# Suspend/resume, the mechanism `_SUSTAINED` uses, is deliberately NOT what
# this is. A tactile bed resumed a moment later is continuous; a sentence
# resumed mid-word is not obviously better than one cut, the write is a
# blocking call on the voice thread that another thread closing under it is
# the SimHub close-from-send deadlock in a new costume, and the resume would
# need a lock the recovery thread already holds. Deferral and re-speak instead.
_PLAYING: list = []
_PLAYING_STATE = threading.Condition(threading.Lock())

# How long a rebuild will hold off for. A spoken race call is two to four
# seconds; this is a couple beyond the longest plausible one, so a line that is
# still going at the cap is a stuck engine rather than a long sentence, and
# waiting further would starve whatever wanted the rebuild - a driver watching
# an empty device picker, or a transducer recovery. It is deliberately under
# `voice.STALE_AFTER_S` (8 s): a line cut at the cap must still be able to come
# back as fresh, or the deferral would guarantee the re-speak is always too
# late to be worth saying.
DEFER_CAP_S = 6.0


class Playback:
    """One short-lived stream that is open and being written to right now."""

    __slots__ = ("what", "thread", "interrupted")

    def __init__(self, what: str) -> None:
        self.what = what
        self.thread = threading.get_ident()
        # Set when the stream was ended before its sound finished - either a
        # rebuild ran out of patience and tore it down, or the caller stood
        # aside for something more urgent on the same card (`priority_on`).
        # Read by the caller after its write loop: the voice re-speaks the
        # line if it is still true, the shift beep does not - a beep said late
        # is a wrong shift point, and the next one is a corner away.
        self.interrupted = False


def begin_playback(what: str) -> Playback:
    """Declare that a stream is open and mid-write. `what` names it in the log.

    **Call this AFTER the open, holding `enumeration_lock()` across both, and
    open nothing else before `end_playback`.** Every clause is load-bearing,
    and the first two pull against each other.

    *After the open*, because `_reinitialise` waits on this gate while holding
    the enumeration lock, and the enumeration lock is what every open goes
    through. A caller that declared itself first and opened second would be
    holding the gate against a rebuild that holds the lock its open needs:
    the same two locks in the opposite order, which is the AB-BA that
    `enumeration_lock` exists to document, reopened from a new direction.

    *Across both*, because "after the open" on its own leaves a gap between
    the stream starting and the gate going up, and a rebuild landing in that
    gap closes a stream it never saw. That is this module's own silent
    truncation narrowed to microseconds rather than removed - and it is the
    worse shape of it, because `interrupted` stays False afterwards, so the
    line is lost without even being said again. Holding the enumeration lock
    over the pair makes them atomic against the only thing in the process that
    calls `_terminate()`. It adds no lock order that is not already there:
    this gate is a leaf, taken under that lock by the rebuild too, and the
    lock is re-entrant so a nested open costs nothing.
    """
    playback = Playback(what)
    with _PLAYING_STATE:
        _PLAYING.append(playback)
    return playback


def end_playback(playback: Playback) -> None:
    """The stream is closed. Release any rebuild that was holding off."""
    with _PLAYING_STATE:
        if playback in _PLAYING:
            _PLAYING.remove(playback)
        _PLAYING_STATE.notify_all()


def open_and_declare(what: str, open_stream):
    """Start a stream and raise its gate as one step. `(stream, playback)`.

    The only correct way to do the pair, so that no caller has to re-derive
    the lock order in `begin_playback` and none of them can get it subtly
    wrong in a different way. `open_stream` is a no-argument callable that
    returns a started stream - a callable rather than the arguments to
    `open_output`, because the three callers want three different opens and
    the rate is not known until the first chunk of synthesis comes back.

    Holding the enumeration lock across the two is not extra caution, it is
    the point: see `begin_playback`. It costs nothing, because `open_output`
    already holds that lock for the whole of its own attempt.
    """
    with _ENUMERATE_LOCK:
        stream = open_stream()
        return stream, begin_playback(what)


def _wait_for_playback(cap: float | None = None) -> list:
    """Hold a device-list rebuild until the sound in flight has finished.

    Returns the playbacks still in flight at the cap - empty when the wait
    came out clean. **The caller must not re-enumerate over a non-empty
    return**; see `_reinitialise`.

    Bounded, always. A wait that could not time out would let a stuck engine
    hold off the settings picker, or a transducer recovery, for the rest of
    the race - which in the second case is trading one silent output for
    another. At the cap it proceeds and marks every stream it is about to
    close, so nothing is cut without something knowing.

    A playback on the CALLING thread is never waited for - it would be waiting
    on itself - but it is still marked, because `_terminate()` is going to
    close it just the same.
    """
    # Read here rather than defaulted in the signature, so that raising or
    # lowering the cap at runtime - which the tests do, and which a settings
    # screen could - actually reaches this.
    cap = DEFER_CAP_S if cap is None else cap
    mine = threading.get_ident()
    started = time.monotonic()
    with _PLAYING_STATE:
        if not _PLAYING:
            return []
        others = [p for p in _PLAYING if p.thread != mine]
        labels = ", ".join(sorted({p.what for p in _PLAYING}))
        while others:
            left = cap - (time.monotonic() - started)
            if left <= 0:
                break
            _PLAYING_STATE.wait(left)
            others = [p for p in _PLAYING if p.thread != mine]
        waited = time.monotonic() - started
        cut = list(_PLAYING)
        for playback in cut:
            playback.interrupted = True
    # Outside the lock, and only when something actually happened: this fires
    # once per rebuild that collided with a sound, not once per attempt.
    if cut:
        log("audio").warning(
            "%s was still playing after %.1fs, so the audio devices were "
            "rebuilt underneath it and it was cut off. Whatever was speaking "
            "will say it again if it is still true.",
            ", ".join(sorted({p.what for p in cut})), waited)
    else:
        log("audio").info(
            "held the audio device rebuild %.1fs for %s to finish. Nothing "
            "that re-enumerates is more urgent than that: a device picker is "
            "a screen he is reading, and a sentence he only half hears cannot "
            "be got back.", waited, labels)
    return cut


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


def open_exclusive_output(device: object, samplerate: int, *,
                          channels: int = 2, dtype: str = "float32",
                          blocksize: int = 0, callback=None):
    """A stream that owns its card outright, or a refusal. No middle ground.

    **Measured not to work on the ButtKicker PRO, 15 Aug 2026. Do not reach
    for this on that rig without checking it again first.** It opens, reports
    21.3 ms and a sensible rate and channel count, and then renders nothing:
    the endpoint metered 0.0000 for the whole call and the driver in the seat
    felt nothing, while the identical tone through a shared stream metered
    0.125 and was felt. Repeatedly opening and closing it also degrades the
    endpoint until further opens fail outright with -9996; a fresh process
    opens cleanly again.

    That is exactly the fault this module exists to catch - a card accepting
    audio and playing none of it - arrived at from the inside, by an API that
    reports success. Which is why the transducer runs shared, and why the
    endpoint meter is not optional on that path: it is the only thing that
    would have caught this.

    Kept rather than deleted because it is correct for devices where WASAPI
    exclusive genuinely works, and because the reasons to want it are real -
    they are below. But a caller must verify that sound actually arrives,
    and cannot verify it with the endpoint meter, which does not see past the
    audio engine that exclusive mode bypasses. A human, or nothing.

    For the tactile transducer, where "isolated from everything else the PC is
    doing" is a requirement rather than a preference. Three things follow from
    exclusive mode and all three are the point:

    * **Nothing else can open the endpoint while this is held.** A stray
      notification cannot arrive through the driver's seat.
    * **The Windows audio engine is bypassed**, and with it every APO. Bass
      Management redirects everything below its crossover, Loudness
      Equalization compresses the dynamics, and both would quietly ruin a
      signal whose whole content is 25-120 Hz.
    * **The endpoint's volume slider stops applying**, which removes one of
      the two gain stages between the app and the piston.

    **It will not fall back to another host API, deliberately.** Exclusive
    mode exists only under WASAPI. `_open_first_that_works` walks down to MME
    on a refusal, which for the voice is right - a call out of the wrong
    speaker beats no call - but here it would silently hand back a *shared*
    stream on the very endpoint the caller asked to have to itself. Every
    Windows sound would then arrive through the transducer, which is the exact
    thing this function is for. So a refusal is raised.
    """
    import sounddevice as sd

    if device is None:
        # "The default device" is the one thing this must not accept. The
        # default is wherever Windows is sending everything else, and taking
        # exclusive ownership of it would mute the machine.
        raise ValueError(
            "a transducer has to be named. Opening the system default "
            "exclusively would take the card everything else is playing "
            "through.")

    with _ENUMERATE_LOCK:
        routes = _candidates(sd, device, "output", host_api="Windows WASAPI")
        if not routes:
            raise RuntimeError(
                f"{describe(device)} has no WASAPI endpoint on this machine, "
                f"so it cannot be opened exclusively. Sharing it would let "
                f"every other sound on the PC through it.")
        stream = sd.OutputStream(
            samplerate=samplerate, channels=channels, dtype=dtype,
            device=routes[0], blocksize=blocksize, callback=callback,
            extra_settings=sd.WasapiSettings(exclusive=True))
        stream.start()
        return stream


def _matching_indices(sd, name: str, kind: str) -> list[int]:
    """Every device index whose card is `name`. Empty means it is not here.

    Separate from `_candidates` because that one deliberately answers "the
    default" when nothing matches, which is the right answer for the voice and
    the wrong one for a device-specific stream.
    """
    wanted = endpoint_key(name)
    field = f"max_{kind}_channels"
    return [index for index, info in enumerate(sd.query_devices())
            if info.get(field, 0) > 0
            and endpoint_key(info.get("name", "")) == wanted]


def _candidates(sd, device: object | None, kind: str,
                host_api: str | None = None, strict: bool = False) -> list:
    """Every route to the chosen card, best first.

    None stays None - that is PortAudio's own default, which is re-resolved
    because the enumeration behind it was just refreshed. An int is taken as
    given. A name matches on the truncated form, so a name stored under any
    host API finds all of them, and the list comes back in `_HOST_API_ORDER`
    so the caller can walk down it.

    A name that no longer matches anything falls back to the default with a
    warning rather than raising: the driver would rather hear the call out of
    the wrong speaker than not hear it.

    **Unless `strict`, where that trade is exactly backwards.** The transducer
    is a 150 W amplifier under the seat and its band is 25-160 Hz: routed to
    the default it puts a road-rumble bed into whatever Windows currently
    calls default, which on this machine has been a monitor over HDMI and a
    pair of headphones. `open_output` checks the name exists before it starts,
    but that check and this resolution are separate moments and the device
    list is rebuilt between them often enough to matter - the list was rebuilt
    three times in one practice session on 22 Aug. A strict caller gets the
    card it named or nothing.
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
        # A caller that needs one specific route - exclusive mode exists only
        # under WASAPI - gets that route or nothing. Falling through to
        # another host API would quietly give it a stream with different
        # properties from the ones it asked for.
        if host_api is not None and api != host_api:
            continue
        rank = (_HOST_API_ORDER.index(api) if api in _HOST_API_ORDER
                else len(_HOST_API_ORDER))
        found.append((rank, index))
    if host_api is not None:
        return [index for _rank, index in sorted(found)]
    if not found:
        if strict:
            raise RuntimeError(
                f"no {kind} device named {device!r} on this machine at the "
                f"moment of opening. Refusing to fall back to the default - "
                f"this sound is meant for one specific card.")
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
    rather than silently destroyed by it.

    **And it was never survivable for the short-lived ones either - that
    paragraph reasoned about the gaps between lines and forgot the lines.**
    One spoken line is a stream open for two to four seconds, and the caller
    that reaches this most often is the settings screen: `_audio_plate` calls
    `devices("output")` and `devices("input")` while it builds its pickers, so
    the driver opening settings mid-session lands here twice, and either one
    can close the stream the engineer is talking through. He hears half a
    sentence, `sd` raises nothing, and this function logs nothing.

    `_wait_for_playback` holds the rebuild until the sound in flight has
    finished, up to `DEFER_CAP_S`, and marks what it cuts if it runs out of
    patience. It runs FIRST, before the sustained holders are suspended:
    suspending the transducer for the length of the wait would mute the
    haptics in order to protect the voice, which is paying for the fix with
    the thing the fix is for.
    """
    # **`Pa_Terminate` over an open stream does not raise. It takes the
    # process down.** Measured 22 Aug 2026, twice, from this exact call:
    #
    #     the engineer's line was still playing after 6.0s, so the audio
    #     devices were rebuilt underneath it and it was cut off
    #     PortAudioError: Unanticipated host error [PaErrorCode -9999]
    #     Windows fatal exception: access violation
    #       sounddevice.py:2952 in _terminate
    #       audio_devices.py in _reinitialise
    #
    # `_wait_for_playback` is bounded on purpose - a wait that could not time
    # out would let a stuck engine hold off a transducer recovery for the
    # rest of a race - but reaching the cap and then re-enumerating anyway
    # trades a cut sentence for a dead app, and the driver loses the whole
    # session rather than one line of it.
    #
    # So the cap now ends the REBUILD, not the wait. A stale device list is
    # exactly what we already had and is survivable; the caller's strict
    # check will refuse on its own if the card it wants is genuinely gone.
    still_playing = _wait_for_playback()
    if still_playing:
        log("audio").error(
            "not re-enumerating the audio devices: %s is still playing after "
            "the wait, and terminating PortAudio over an open stream kills "
            "the process rather than raising. The device list stays as it "
            "was.", ", ".join(sorted({p.what for p in still_playing})))
        return
    _WORKING.clear()
    with _SUSTAINED_GUARD:
        holders = list(_SUSTAINED)
    unsuspended = []
    for holder in holders:
        try:
            holder.suspend()
        except Exception as exc:                # noqa: BLE001
            unsuspended.append(holder)
            log("audio").warning("could not suspend %s before re-enumerating: "
                                 "%s", holder, exc)
    if unsuspended:
        # Same rule, same reason: a sustained holder that would not let go
        # still has its stream open, and that is the one condition under
        # which terminating is fatal rather than merely unhelpful.
        log("audio").error(
            "not re-enumerating the audio devices: %d sustained stream(s) "
            "would not suspend, and terminating over an open stream kills "
            "the process.", len(unsuspended))
        for holder in holders:
            try:
                holder.resume()
            except Exception as exc:            # noqa: BLE001
                log("audio").error("%s did not come back: %s", holder, exc)
        return
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
                extra_settings=None, strict: bool = False):
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

    `strict` refuses rather than falling back to the default when the named
    card is not there. **The default is right for the voice and wrong for the
    transducer**, and the difference is not a detail: a call out of the wrong
    speaker still reaches the driver, whereas a road-rumble bed routed to his
    headphones because the ButtKicker was switched off puts 40 Hz in his ears
    for a whole race. Silence is the correct output for a transducer that is
    not connected.
    """
    import sounddevice as sd

    chosen = _OUTPUT if device is _DEFAULT else device
    if strict and isinstance(chosen, str):
        with _ENUMERATE_LOCK:
            # **Look before rebuilding, and it used to rebuild first.**
            #
            # `_reinitialise` is `Pa_Terminate` + `Pa_Initialize` - it tears
            # down the whole of PortAudio and enumerates every device on the
            # machine. Measured on this rig at about 1.9 s, and it ran on
            # EVERY strict open whether or not anything was wrong. 58 of 82
            # transducer opens in the log are on the Qt thread, because
            # `start_practice` opens the haptics inline, so that 1.9 s was a
            # frozen window on every practice and race start.
            #
            # It is also the call that takes the process down when a stream
            # is open - see `_reinitialise` - so not making it is worth more
            # than the time it saves.
            #
            # The rebuild was there to be sure a name that appears absent
            # really is, rather than merely stale. That is still true, and
            # still done: it is just now the fallback rather than the
            # opening move. Only the genuinely-missing case pays for it.
            if not _matching_indices(sd, chosen, "output"):
                _reinitialise(sd)
                if not _matching_indices(sd, chosen, "output"):
                    raise RuntimeError(
                        f"no output device named {chosen!r} on this machine. "
                        f"Refusing to fall back to the default - this sound "
                        f"is meant for one specific card.")

    def attempt():
        return _open_first_that_works(
            sd, chosen, "output", strict=strict,
            build=lambda resolved: sd.OutputStream(
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


def _open_first_that_works(sd, chosen, kind: str, build, strict: bool = False):
    """Walk the routes to the chosen card and start the first that opens.

    The last route's failure is re-raised rather than swallowed, so a card
    that cannot be opened at all is still loud. Anything that opens is
    remembered, because the next beep should not re-discover that WASAPI will
    not take 22050 Hz.
    """
    routes = _candidates(sd, chosen, kind, strict=strict)
    for position, device in enumerate(routes):
        try:
            stream = build(device)
            stream.start()
        except sd.PortAudioError as exc:
            if position == len(routes) - 1:
                raise
            log("audio").info(
                "%s device %s would not open (%s) - trying the next route",
                kind, _name_of(sd, device), exc)
            continue
        if isinstance(chosen, str):
            _WORKING[(endpoint_key(chosen), kind)] = device
        return stream
    # `_candidates` returns [None] rather than [], so this is unreachable
    # unless it is changed to return nothing.
    raise RuntimeError(f"no {kind} route to {describe(chosen)}")


def _name_of(sd, device) -> str:
    """`3 'Speakers (Thing)' via MME`, for a log line about one route.

    **The index alone is not an identity and must never be read as one.** It
    is a position in a list this process rebuilt at every `_reinitialise`, so
    the same number means a different card in a later process - or in the same
    process ten minutes on. On 18 Aug 2026 a "device 25 would not open" line
    from the beep was read against a fresh enumeration in which 25 was the
    transducer, and became a diagnosis that the shift beep had been playing
    into the ButtKicker. It had not: 25 was the headset's WASAPI route, and
    the line is the routine discovery that WASAPI will not take 44100. The
    name is what settles it, so the name is what gets logged.
    """
    if device is None:
        return "the system default"
    try:
        info = sd.query_devices(device)
        api = _host_api_names(sd).get(info.get("hostapi"), "?")
        return f"{device} {info.get('name', '?')!r} via {api}"
    except Exception:                                       # noqa: BLE001
        # Never let a log line be the thing that raises.
        return repr(device)


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


# ----------------------------- what the stream actually turned out to be
#
# **The gap this closes cost a whole session to find and was still not
# settled at the end of it.** On 17 Aug 2026 the transducer's endpoint meter
# read silent for thirteen minutes, the app said so out loud, and the driver
# felt the seat working - badly, but working. Those two cannot both be true of
# the same stream on the same endpoint, and nothing in the record could
# separate them, because the only thing written down at every open was
# `"transducer running on Speakers (ButtKicker PRO)"` - the name that was
# ASKED for. Not the route taken to it, not the index, not the rate that came
# back, not the block size PortAudio chose. A stream that opened on a
# different host API, or at a rate the synthesiser is not generating for, is
# indistinguishable in that line from the one that was working a second
# earlier.
#
# So every open now records what it got and compares it to what it wanted.
# Two different questions, and they are answered separately:
#
# * **`mismatches`** - the stream is not what was asked for. A rate that came
#   back different means every tone is transposed by that ratio, and this
#   amp passes 25-160 Hz, so a modest shift walks the road bed out of the
#   band entirely. That is a failed open, not a working one.
# * **`differences`** - the stream is not what was working before. Same
#   format, different route, is not a fault on its own; it is also not a
#   recovery, because the route decides whether the audio is audible
#   (DirectSound buffers and discards) and whether the endpoint meter can
#   even see it.

# The fields that make two opens the same stream. The index is deliberately
# not among them - PortAudio renumbers between enumerations and the whole
# reason the device is named rather than indexed is that the number moves.
# Nor is the block size: `BLOCKSIZE = 0` asks PortAudio to choose, so a
# different choice is its business, and it is reported rather than judged.
IDENTITY_FIELDS = ("samplerate", "channels", "dtype", "host_api", "endpoint")

# How far the negotiated rate may sit from the requested one before the
# stream is a different stream. Rates come back as floats; anything past this
# is a real renegotiation rather than a representation wobble.
RATE_TOLERANCE_HZ = 1.0


@dataclasses.dataclass(frozen=True)
class StreamFacts:
    """What an open stream IS, beside what it was asked to be.

    Every field is optional because this must never be able to fail an open
    that succeeded: a stream object that does not answer a question leaves
    that question `None`, which reads as *not known* rather than as a
    mismatch. Missing is null, never zero, here as everywhere.
    """

    samplerate: float | None = None
    blocksize: int | None = None
    channels: int | None = None
    dtype: str | None = None
    latency: float | None = None
    index: int | None = None
    host_api: str | None = None
    name: str | None = None

    asked_samplerate: float | None = None
    asked_blocksize: int | None = None
    asked_channels: int | None = None
    asked_dtype: str | None = None
    asked_name: str | None = None

    @property
    def endpoint(self) -> str | None:
        """The card, independent of the route - the same key `_candidates`
        matches on, so two routes to one piece of hardware compare equal."""
        return None if self.name is None else endpoint_key(self.name)

    def describe(self) -> str:
        """One line naming the whole negotiation, for the log."""
        parts = [
            f"{self.samplerate:.0f} Hz" if self.samplerate is not None
            else "rate unknown",
            f"block {self.blocksize}" if self.blocksize is not None
            else "block unknown",
            f"{self.channels}ch" if self.channels is not None
            else "channels unknown",
            str(self.dtype) if self.dtype is not None else "dtype unknown",
            self.host_api or "host API unknown",
            f"index {self.index}" if self.index is not None
            else "index unknown",
        ]
        if self.latency is not None:
            parts.append(f"{self.latency * 1000:.1f} ms")
        if self.name:
            parts.append(repr(self.name))
        return " · ".join(parts)

    def mismatches(self) -> list[str]:
        """Where the stream differs from what was requested.

        The block size is never in here: zero means "PortAudio chooses", so
        whatever it chose is the right answer by construction.
        """
        wrong: list[str] = []
        if (self.samplerate is not None and self.asked_samplerate is not None
                and abs(self.samplerate - self.asked_samplerate)
                > RATE_TOLERANCE_HZ):
            wrong.append(
                f"asked for {self.asked_samplerate:.0f} Hz and got "
                f"{self.samplerate:.0f} Hz")
        if (self.channels is not None and self.asked_channels is not None
                and self.channels != self.asked_channels):
            wrong.append(f"asked for {self.asked_channels} channels and got "
                         f"{self.channels}")
        if (self.dtype is not None and self.asked_dtype is not None
                and str(self.dtype) != str(self.asked_dtype)):
            wrong.append(f"asked for {self.asked_dtype} samples and got "
                         f"{self.dtype}")
        if (self.endpoint is not None and self.asked_name
                and self.endpoint != endpoint_key(self.asked_name)):
            wrong.append(f"asked for {self.asked_name!r} and landed on "
                         f"{self.name!r}")
        return wrong

    def differences(self, other: "StreamFacts | None") -> list[str]:
        """Where this stream differs from one that was previously working.

        `None` on either side of a field is *not known*, and an unknown is
        never reported as a change: inventing a difference out of a stream
        that would not answer the question would escalate a recovery that
        was fine.
        """
        if other is None:
            return []
        changed: list[str] = []
        for field in IDENTITY_FIELDS:
            was, now = getattr(other, field), getattr(self, field)
            if was is None or now is None:
                continue
            if field == "samplerate":
                if abs(float(now) - float(was)) <= RATE_TOLERANCE_HZ:
                    continue
            elif str(now) == str(was):
                continue
            changed.append(f"{field} was {was} and is now {now}")
        return changed


def describe_stream(stream, *, samplerate=None, blocksize=None, channels=None,
                    dtype=None, device=None) -> StreamFacts:
    """Read back what PortAudio actually gave us. Never raises.

    Called immediately after an open, with the arguments the open was made
    with, so the comparison is against the request rather than against a
    remembered constant that may have drifted from it.
    """
    def attr(name):
        try:
            value = getattr(stream, name)
        except Exception:                       # noqa: BLE001
            return None
        return value

    index = attr("device")
    if not isinstance(index, int):
        # A `device=None` stream reports PortAudio's own default, which may
        # come back as a pair. Neither is a route we can name.
        index = None
    host_api = name = None
    if index is not None:
        try:
            import sounddevice as sd

            with _ENUMERATE_LOCK:
                info = sd.query_devices(index)
                name = str(info["name"])
                host_api = _host_api_names(sd).get(info.get("hostapi"))
        except Exception as exc:                # noqa: BLE001
            # Reading the device list back is a convenience, not the open.
            log("audio").debug("could not name stream route %r: %s: %s",
                               index, type(exc).__name__, exc)

    def number(value):
        try:
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    def whole(value):
        try:
            return None if value is None else int(value)
        except (TypeError, ValueError):
            return None

    latency = attr("latency")
    if isinstance(latency, (tuple, list)):
        latency = latency[-1] if latency else None

    asked_dtype = None if dtype is None else str(dtype)
    got_dtype = attr("dtype")
    return StreamFacts(
        samplerate=number(attr("samplerate")),
        blocksize=whole(attr("blocksize")),
        channels=whole(attr("channels")),
        dtype=None if got_dtype is None else str(got_dtype),
        latency=number(latency),
        index=index,
        host_api=host_api,
        name=name,
        asked_samplerate=number(samplerate),
        asked_blocksize=whole(blocksize),
        asked_channels=whole(channels),
        asked_dtype=asked_dtype,
        asked_name=device if isinstance(device, str) else None)
