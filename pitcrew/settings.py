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

from dataclasses import dataclass, fields

# Where the beep threshold comes from.
RPM_FROM_GT7 = "gt7"        # the car's own shift-light rpm, off the packet
RPM_MANUAL = "manual"       # a number the driver chose
RPM_SOURCES = (RPM_FROM_GT7, RPM_MANUAL)

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


@dataclass
class Settings:
    """Everything the driver can set. Small on purpose."""

    # --- push to talk
    ptt_enabled: bool = True
    ptt_key: str = "f8"
    # PTT is armed during a race because that is when it earns its keep. Arming
    # it in practice too is how you find out whether the button works at all
    # without committing to a race to test it.
    ptt_in_practice: bool = False
    speech_backend: str = SPEECH_SAPI
    # low  - acts only when sure, asks more often
    # high - acts readily, asks rarely
    speech_sensitivity: str = "medium"

    # --- shift beep
    beep_enabled: bool = True
    beep_rpm_source: str = RPM_FROM_GT7
    beep_rpm: float = 7000.0

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

    def validate(self) -> None:
        if self.beep_rpm_source not in RPM_SOURCES:
            raise ValueError(
                f"beep_rpm_source must be one of {RPM_SOURCES}, "
                f"got {self.beep_rpm_source!r}")
        for name, low, high in (("voice_length_scale", 0.5, 2.0),
                                ("voice_noise_scale", 0.0, 1.5),
                                ("voice_noise_w_scale", 0.0, 1.5)):
            value = getattr(self, name)
            if not low <= value <= high:
                raise ValueError(
                    f"{name} of {value} is outside {low}-{high}, which is the "
                    f"range Piper produces speech in at all")
        if not 1000.0 <= self.beep_rpm <= 20000.0:
            raise ValueError(
                f"a shift threshold of {self.beep_rpm} rpm is not a threshold "
                f"any GT7 car has - expected 1000-20000")
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

    @property
    def uses_game_rpm(self) -> bool:
        return self.beep_rpm_source == RPM_FROM_GT7

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
                        "0" if value is False else str(value))


def _coerce(kind, raw: str):
    if kind is bool or kind == "bool":
        return raw not in ("0", "", "False", "false")
    if kind is float or kind == "float":
        try:
            return float(raw)
        except ValueError:
            return 0.0
    return raw
