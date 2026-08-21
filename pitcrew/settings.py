"""The two things the driver has to be able to set: the button and the beep.

Both were hard-coded. Push-to-talk listened on F8 with no way to change it, and
the shift beep took its threshold from GT7's own shift-light rpm with no way to
turn it off or to override it. `config.json` still carries a `query_button` of
`b` and a `shift_beep.race_rpm` of 8640 — but that file belonged to the app
this one replaced and nothing reads it any more, so those settings have simply
been ignored.

Settings live in the store's `app_state` rather than in a settings file, so
there is one place the app's state lives and one thing to back up.

Nothing here has a clever default. The beep threshold defaults to GT7's own
shift light because the game already knows the car's power band and the app
does not; the point of the manual override is that the driver may want to
short-shift, which is a decision only he can make.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields

from pitcrew.race import colour

# **The shift beep's thresholds live on the SETUP SHEET, not here.**
# There were three sources: a per-gear table keyed by car, one global rpm the
# driver could type, and GT7's own shift light. The last two sounded at the
# wheel exactly like a measured threshold without being one, and the first was
# keyed to the wrong thing - a shift point belongs to the GEARBOX, so change a
# ratio and it moves, and two sheets for one car want two tables.
#
# On the sheet it travels with the setup, gets versioned alongside it and
# reaches the export. A sheet with no table means the gearbox has not been
# measured, and the beep is silent rather than guessing.

# The prefix every settings key carries in app_state, so they cannot collide
# with `active_event_id` or a custom catalogue.
PREFIX = "setting:"

# Keys pynput reports for the buttons a wheel is usually mapped to. Free text
# is still allowed - a wheel button can be bound to almost anything - but a
# list stops the common case being a typing exercise.
COMMON_KEYS = ("f8", "f9", "f10", "f11", "f12", "f13", "f14", "f15",
               "ctrl_r", "shift_r", "alt_r", "b", "v", "`")

# Which recogniser listens. SAPI's closed grammar was the safe one, but
# Windows Speech Recognition is being retired - the WSR user experience is
# already gone from this machine - so `moonshine` is where this is going and
# `sapi` is what still works today.
SPEECH_SAPI = "sapi"
SPEECH_MOONSHINE = "moonshine"
SPEECH_BACKENDS = (SPEECH_SAPI, SPEECH_MOONSHINE)

# How readily the engineer acts on what he thinks he heard. Named, never
# numeric: the raw cosine distances behind these live in `engineer/gate.py`
# and mean nothing to the person choosing.
SENSITIVITIES = ("low", "medium", "high")

# **Where the packets arrive, and who does the asking.**
#
# `simhub` - SimHub talks to the console and re-broadcasts GT7's raw
# encrypted packets to a local port. This app binds and listens; it sends
# nothing and does not need the console's address to receive.
#
# `ps5` - this app talks to the console itself. GT7 streams to nobody until
# it is asked and stops when the asking stops, so the listener heartbeats it
# on a timer and receives on GT7's own stream port. Decryption is identical
# either way: SimHub relays the encrypted bytes rather than decoding them, so
# `telemetry/packet.py` has always done the Salsa20 work.
FEED_SIMHUB = "simhub"
FEED_PS5 = "ps5"
FEED_SOURCES = (FEED_SIMHUB, FEED_PS5)

# 33741 is SimHub's relay port. GT7's own pair is a heartbeat to 33739 and
# the stream back on 33740, which is what direct mode uses - see
# `telemetry/listener.py`, and CLAUDE.md 3.1 on why the pair is checked by a
# self-test rather than trusted.
DEFAULT_UDP_PORT = 33741

# How much the engineer says on the laps that carry no instruction. Re-exported
# from `race.colour` so a settings screen has one import for the whole choice
# and cannot drift from the module that acts on it.
COLOUR_QUIET = colour.QUIET
COLOUR_NORMAL = colour.NORMAL
COLOUR_CHATTY = colour.CHATTY
COLOUR_LEVELS = colour.LEVELS


@dataclass
class Settings:
    """Everything the driver can set. Small on purpose."""

    # --- where the telemetry arrives
    udp_port: int = DEFAULT_UDP_PORT
    # Accept packets only from this address. Empty means accept from anything,
    # which is the right default on a rig with one console on it. It earns its
    # keep when something else on the network is talking on the same port -
    # without it, a foreign packet reaches the parser, fails to decode, and
    # shows up as a decode-error count rather than as what it is.
    udp_source_ip: str = ""

    # Which of the two above. The address box that was already here is an
    # accept-filter on inbound packets, not a destination - which is why
    # setting it never made a console start streaming. `ps5_ip` is the
    # destination, and it is only read in direct mode.
    feed_source: str = FEED_SIMHUB
    ps5_ip: str = ""

    # **A sign, not a notification.** In PSVR2 he reads this monitor
    # through passthrough from a metre away, which is roughly the worst
    # display conditions there are - and it is exactly then that he needs
    # to know whether the app is recording. On by default; off for anyone
    # who does not want a screen-filling flash between runs.
    banner_enabled: bool = True

    # **The GT7 version every measurement is filed against.** GT7 rewrote its
    # physics, tyre model and geometry in 1.49 and again in 1.55, so a figure
    # without the version it was taken under cannot be compared with the next
    # one - and the export refuses a payload that has no version on it.
    #
    # It lives here rather than on the event, which is where it used to be
    # asked for. One console runs one version; asking per event meant an event
    # created without it produced an export that was refused outright, which
    # is what "the GT7 version just blocks the output" was. An event may still
    # carry its own, for a measurement taken under a version that is no longer
    # the one installed, and that overrides this.
    #
    # **Empty by default, deliberately, and it used to read "1.70".** A
    # hard-coded version is right for exactly as long as it takes the console
    # to patch itself, and then it is silently wrong on every measurement
    # taken afterwards. 1.71 landed on 20 Aug 2026 and reworked the tyre
    # model, so a run recorded on the 21st and stamped 1.70 is not a small
    # error - it files post-patch evidence under the pre-patch physics and
    # nothing downstream can tell. Empty means unset; the export refuses a
    # payload with no version, which is a failure somebody notices.
    game_version: str = ""

    # --- push to talk
    ptt_enabled: bool = True
    ptt_key: str = "f8"
    # PTT is armed during a race because that is when it earns its keep. Arming
    # it in practice too is how you find out whether the button works at all
    # without committing to a race to test it.
    ptt_in_practice: bool = False
    # **Which sound card, by name.** Empty means "whatever Windows calls the
    # default", which is what the app always did - and what put the engineer's
    # calls into a headset that was not connected, silently, because PortAudio
    # resolves the default once at import and a disconnected endpoint accepts
    # audio without complaining. Stored as a name rather than an index because
    # indices are renumbered whenever a device appears or goes.
    audio_output_device: str = ""
    audio_input_device: str = ""

    speech_backend: str = SPEECH_SAPI
    # low  - acts only when sure, asks more often
    # high - acts readily, asks rarely
    speech_sensitivity: str = "medium"

    # --- the rig
    # **Off by default, deliberately.** This drives a 150 W amplifier into a
    # piston under the driver's seat, and an output that starts making itself
    # felt because the app was updated is not a pleasant surprise. He turns it
    # on once.
    haptics_enabled: bool = False
    # The fans. Off by default for the same reason, though the consequence of
    # a surprise here is startling rather than physical.
    wind_enabled: bool = False
    # Empty means the transducer this rig was measured against. A name rather
    # than an index for the same reason as the engineer's card: indices are
    # renumbered whenever a device appears or goes.
    haptics_device: str = ""
    # Master gain over the whole haptic mix, capped at 1.5. The balance
    # between effects is his SimHub tuning and belongs in the effect list.
    #
    # Capped for safety, not taste: the limiter holds the peak but not the
    # duty cycle, and duty cycle is what trips an amplifier. A master of 2 did
    # exactly that. The amp's own knob is at 35 of 50 and is the right place
    # to find more.
    haptics_gain: float = 1.0

    # --- tyre wear off the OBS capture
    #
    # **GT7 broadcasts no tyre wear channel**, and the driver has said he will
    # not record it in the app or by voice - every session has video, and the
    # gauge is in it. One screenshot at each lap crossing costs about 0.6% of
    # one core, which is affordable; anything faster is not.
    #
    # Off by default: it reaches out to another process on a port, and that is
    # not something that should start happening because the app was updated.
    hud_wear_enabled: bool = False
    obs_host: str = "127.0.0.1"
    obs_port: int = 4455
    obs_password: str = ""

    # --- shift beep
    beep_enabled: bool = True
    # How far a short-shift moves every threshold down when the engineer asks
    # for fuel. He prefers this to leaning the fuel map, which costs power
    # everywhere while this costs only the top of each gear - and it drops
    # rear tyre temperature as well.
    #
    # **Not yet measurable on his data, and that is why it is a setting.** The
    # tool can cost a short-shift only where the next gear has been driven at
    # the rpm the early shift lands on, and he has never short-shifted, so
    # those bins are empty. Once a session is run with this on, the tool can
    # price it per gear and this becomes a measured figure.
    beep_short_shift_drop: float = 500.0
    # **What a short-shift is worth in fuel, per car: `{car_id: L/1000rpm}`.**
    #
    # Measured by `tools/shortshift_trade.py` off laps where his own upshift
    # rpm varied - 1.762 on the Porsche at Monza, 95% CI [0.92, 2.60], 69 laps
    # across 5 sessions. It is what turns "you are 1.2 laps short" into a
    # number of rpm rather than into a fuel map he will never use.
    #
    # A car with no entry gets None and the live call names the lever without
    # a figure. That is the honest failure: the lever is his whatever the car,
    # the conversion is not.
    short_shift_litres_per_1000rpm: dict = field(default_factory=dict)

    # --- how the engineer sounds.
    #
    # A race engineer is calm. The defaults below slow the delivery slightly
    # and, more importantly, cut the phoneme-duration jitter that is the main
    # contributor to the nervous, uneven cadence that reads as robotic.
    #
    # These are on the Settings screen rather than in a file because this app
    # reads no config file - the one at the repo root belonged to the app this
    # replaced. They are here so the voice can be tuned at the rig, by ear,
    # without a code change.
    voice_length_scale: float = 1.12       # > 1 is slower
    voice_noise_scale: float = 0.60        # timbre variation
    voice_noise_w_scale: float = 0.55      # duration jitter - the big one

    # **How much the engineer fills the quiet laps.** `quiet` is off and means
    # off, not "less often"; `normal` and `chatty` differ only in how much
    # silence they keep between colour calls. Strategy is unaffected at every
    # level - this governs the radio that is not an instruction. See
    # `race/colour.py` for why the budget matters more than the calls do.
    colour_calls: str = COLOUR_NORMAL

    def validate(self) -> None:
        if self.colour_calls not in COLOUR_LEVELS:
            raise ValueError(
                f"colour_calls is one of {', '.join(COLOUR_LEVELS)}, "
                f"got {self.colour_calls!r}")
        if not 1024 <= self.udp_port <= 65535:
            raise ValueError(
                f"a UDP port of {self.udp_port} is not one this app can bind - "
                f"expected 1024-65535")
        if self.udp_source_ip and not _looks_like_ipv4(self.udp_source_ip):
            raise ValueError(
                f"{self.udp_source_ip!r} is not an IPv4 address. Leave it "
                f"empty to accept telemetry from anything on the network.")
        for name, low, high in (("voice_length_scale", 0.5, 2.0),
                                ("voice_noise_scale", 0.0, 1.5),
                                ("voice_noise_w_scale", 0.0, 1.5)):
            value = getattr(self, name)
            if not low <= value <= high:
                raise ValueError(
                    f"{name} of {value} is outside {low}-{high}, which is the "
                    f"range Piper produces speech in at all")
        if not 0.0 <= self.beep_short_shift_drop <= 4000.0:
            raise ValueError(
                f"a short-shift drop of {self.beep_short_shift_drop} rpm is "
                f"not a saving, it is a different gearbox - expected 0-4000")
        for car, slope in (self.short_shift_litres_per_1000rpm or {}).items():
            # A negative slope would say short-shifting BURNS fuel, and the
            # live call divides by this - a zero would ask for infinite rpm.
            if not 0.0 < float(slope) <= 20.0:
                raise ValueError(
                    f"a short-shift saving of {slope} L per 1000 rpm for "
                    f"{car!r} is not a measurement of a GT7 car - expected "
                    f"a positive figure up to 20")
        if not 1 <= self.obs_port <= 65535:
            raise ValueError(f"{self.obs_port} is not a port")
        if self.ptt_enabled and not self.ptt_key.strip():
            raise ValueError("push to talk needs a button")
        if self.speech_backend not in SPEECH_BACKENDS:
            raise ValueError(
                f"speech_backend must be one of {SPEECH_BACKENDS}, "
                f"got {self.speech_backend!r}")
        if self.speech_sensitivity not in SENSITIVITIES:
            raise ValueError(
                f"speech_sensitivity must be one of {SENSITIVITIES}, "
                f"got {self.speech_sensitivity!r}")

    def voice_tuning(self) -> dict[str, float]:
        """The synthesis parameters, in the names Piper's config uses."""
        return {
            "length_scale": self.voice_length_scale,
            "noise_scale": self.voice_noise_scale,
            "noise_w_scale": self.voice_noise_w_scale,
        }


def load(store) -> Settings:
    """Read the settings, falling back to the defaults for anything unset.

    A stored value that no longer validates is discarded rather than honoured:
    a bad threshold from an older build must not silently disable the beep or
    make it fire every packet.
    """
    settings = Settings()
    for item in fields(Settings):
        raw = store.get_state(PREFIX + item.name)
        if raw is None:
            continue
        setattr(settings, item.name, _coerce(item.type, raw))
    try:
        settings.validate()
    except ValueError:
        return Settings()
    return settings


def save(store, settings: Settings) -> None:
    settings.validate()
    for item in fields(Settings):
        value = getattr(settings, item.name)
        store.set_state(PREFIX + item.name,
                        "1" if value is True else
                        "0" if value is False else
                        # **A table goes as JSON, never as `str(dict)`.** The
                        # repr round-trips only through `eval`, and a settings
                        # loader that evals stored text is a settings loader
                        # that runs whatever is in the database.
                        json.dumps(value) if isinstance(value, dict) else
                        str(value))


def _looks_like_ipv4(text: str) -> bool:
    parts = text.strip().split(".")
    if len(parts) != 4:
        return False
    return all(part.isdigit() and 0 <= int(part) <= 255 for part in parts)


def _coerce(kind, raw: str):
    if kind is dict or kind == "dict":
        # A table that will not parse is dropped to empty rather than allowed
        # to fail the whole settings load: an unreadable shift-point table
        # should cost the per-gear beep, not every other setting with it.
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    if kind is bool or kind == "bool":
        return raw not in ("0", "", "False", "false")
    if kind is float or kind == "float":
        try:
            return float(raw)
        except ValueError:
            return 0.0
    if kind is int or kind == "int":
        try:
            return int(raw)
        except ValueError:
            # Out of range rather than merely odd: `load` discards the whole
            # settings object when validation fails, so a sentinel here means
            # "fall back to the defaults" rather than "bind port zero".
            return -1
    return raw
