"""Settings — the feed, the button and the beep.

Three things the driver genuinely has to be able to change, and until now could
not: where the telemetry arrives, which button push-to-talk listens on, and
whether the shift beep sounds and at what rpm.

Both are hardware questions, and hardware is the one thing this app cannot
inspect. So both carry a **test** button. He is in a headset while driving and
cannot see this screen at all; the only way to know the wheel button is bound
to the right key, or that the beep is audible over engine noise, is to press it
here and listen. A settings page for a device you cannot hear is not a setting,
it is a guess.

Everything on this screen is declared, so everything on it is crayon. The one
piece of stencil is what the app found on the machine — which speech engine and
which hook actually loaded — because that is measured, not chosen.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QScrollArea,
    QFrame,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from dataclasses import replace

from pitcrew.engineer import audio_devices

from pitcrew.settings import (
    FEED_PS5,
    FEED_SIMHUB,
    COMMON_KEYS,
    DEFAULT_UDP_PORT,
    RPM_FROM_GT7,
    RPM_MANUAL,
    Settings,
)
from pitcrew.ui import theme
from pitcrew.ui.widgets import (
    BodyLabel,
    Field,
    MarkButton,
    Measured,
    Plate,
    StencilLabel,
    block_wheel,
    mark_unset,
)

RPM_LABELS = {
    RPM_FROM_GT7: "GT7's own shift light",
    RPM_MANUAL: "A number I choose",
}


class SettingsScreen(QWidget):
    """Set the button and the beep, and prove both of them work."""

    saved = pyqtSignal(object)          # Settings
    test_beep_requested = pyqtSignal()
    test_voice_requested = pyqtSignal()
    test_haptics_requested = pyqtSignal()
    test_feed_requested = pyqtSignal()
    capture_toggled = pyqtSignal(bool)      # raw session capture
    listen_toggled = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._listening = False
        self._build()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        page = QVBoxLayout(self)
        page.setContentsMargins(30, 26, 30, 0)
        page.setSpacing(theme.GAP_WIDE)

        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(StencilLabel("Settings", size=theme.TITLE_PX,
                                      colour=theme.STENCIL, tracking=6.0))
        header.addWidget(BodyLabel(
            "The feed, the button and the beep. Test them here — in the "
            "headset you cannot see whether any of them worked.",
            colour=theme.STENCIL_DIM))
        page.addLayout(header)

        # **This screen scrolls, and was the only one that did not.** It is
        # also the tallest: the two plates in the left column alone need
        # 1,117 px, and with the header and the fixed footer the whole thing
        # asks for 1,291. The app's own preferred window is 1,000 tall, and
        # the display it was sized for gives 501 logical pixels.
        #
        # Without a bar, "Save settings" sat 291 px below the visible area
        # with no way to reach it - on the one screen that carries the
        # recovery controls for a broken feed, where the driver goes
        # *because* something is already wrong.
        body = QWidget()
        columns = QHBoxLayout(body)
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(theme.GAP_WIDE)

        left = QVBoxLayout()
        left.setSpacing(theme.GAP_WIDE)
        left.addWidget(self._feed_plate())
        left.addWidget(self._ptt_plate(), 1)
        left.addStretch(1)
        columns.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(theme.GAP_WIDE)
        right.addWidget(self._beep_plate())
        right.addWidget(self._audio_plate())
        right.addWidget(self._rig_plate())
        right.addWidget(self._voice_plate())
        right.addStretch(1)
        columns.addLayout(right, 1)

        scroller = QScrollArea()
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.Shape.NoFrame)
        scroller.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroller.setWidget(body)
        page.addWidget(scroller, 1)

        # Outside the scroller, so the thing you came here to press cannot be
        # scrolled away from.
        page.addWidget(self._footer())

    def _feed_plate(self) -> Plate:
        """Where the telemetry comes from.

        Two sources, and the difference is who does the asking. Direct sends
        GT7's heartbeat to the console itself, because the console streams
        only to an address that has asked it to. The relay leaves that to
        SimHub and this app just binds a port and listens.

        Decryption is this app's either way - SimHub forwards the encrypted
        bytes, it does not decode them - so direct mode loses nothing.

        The source address at the bottom is a filter on what arrives, not a
        destination, which is why setting it never made a console start
        streaming.
        """
        plate = Plate("Telemetry feed")
        plate.body.addWidget(BodyLabel(
            "Direct asks the console itself and needs nothing else running. "
            "The relay takes SimHub's forwarded copy instead. Either way the "
            "decryption happens here.",
            size=13, colour=theme.STENCIL_DIM))

        # Which of the two sources. Direct removes SimHub from the chain
        # entirely; the decryption has always been in this app, because
        # SimHub relays the encrypted bytes rather than decoding them.
        self.feed_source = QComboBox()
        self.feed_source.addItem("SimHub relay", FEED_SIMHUB)
        self.feed_source.addItem("PS5 direct", FEED_PS5)
        self.feed_source.currentIndexChanged.connect(self._sync_feed_source)
        block_wheel(self.feed_source)
        plate.body.addWidget(Field(
            "Source", self.feed_source,
            hint="Direct asks the console itself and needs no SimHub. It "
                 "uses GT7's own ports, so the port below is ignored."))

        self.ps5_ip = QLineEdit()
        self.ps5_ip.setPlaceholderText("192.168.1.20")
        self.ps5_field = Field(
            "PS5 address", self.ps5_ip,
            hint="The console's address on this network. GT7 streams only "
                 "to an address that has asked it to, on a timer.")
        plate.body.addWidget(self.ps5_field)

        self.udp_port = QSpinBox()
        self.udp_port.setRange(1024, 65535)
        self.udp_port.setGroupSeparatorShown(False)
        block_wheel(self.udp_port)
        plate.body.addWidget(Field(
            "Port", self.udp_port,
            hint=f"SimHub's relay is {DEFAULT_UDP_PORT}. Ignored in direct "
                 f"mode, which uses GT7's own pair — 33739 out, 33740 back."))

        self.udp_source_ip = QLineEdit()
        self.udp_source_ip.setPlaceholderText("any address")
        plate.body.addWidget(Field(
            "Only accept from", self.udp_source_ip,
            hint="Leave empty unless something else is talking on this port. "
                 "Set wrong, nothing arrives at all."))

        # Filed against every measurement the app makes. It sits with the
        # feed rather than on the event because one console runs one version,
        # and the export refuses a payload that has no version on it - which
        # an event created without one produced, with nothing on screen to
        # connect the empty box to the refusal.
        self.game_version = QLineEdit()
        self.game_version.setPlaceholderText("1.70")
        plate.body.addWidget(Field(
            "GT7 version", self.game_version,
            hint="Filed with every measurement. The physics have been "
                 "rewritten twice in two updates, so a figure without the "
                 "version it was taken under cannot be compared with the "
                 "next one."))

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.banner_enabled = QCheckBox("Show a full-screen notice")
        self.banner_enabled.setToolTip(
            "One line, as large as the screen will carry it, when a session "
            "starts and stops. Sized to be read through a headset's "
            "passthrough from a metre away, which the lap rack is not. It "
            "never takes focus, so it cannot steal a keypress from the game.")
        plate.body.addWidget(self.banner_enabled)

        self.test_feed_button = MarkButton("Test the feed", compact=True)
        self.test_feed_button.setToolTip(
            "Opens the socket for real, asks the console if asking is "
            "required, and reports what actually decoded. A port that "
            "binds proves nothing on its own - a wrong port pair, an "
            "unasked console and a game sitting in the menus all look "
            "identical from here.")
        self.test_feed_button.clicked.connect(self.test_feed_requested.emit)
        row.addWidget(self.test_feed_button)
        row.addStretch(1)
        plate.body.addLayout(row)

        self.feed_note = BodyLabel("", size=13, colour=theme.CHALK)
        self.feed_note.setWordWrap(True)
        plate.body.addWidget(self.feed_note)

        # Raw capture. Off by default and started before going out, because a
        # 30-minute session is ~40 MB and because there is nothing here anyone
        # should be operating in a headset at speed.
        plate.body.addWidget(BodyLabel(
            "Record every packet to disk for a measurement run. Start it "
            "before you go out, stop it when you come in. Nothing here is "
            "operable at speed.",
            size=13, colour=theme.STENCIL_DIM))
        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.capture_button = MarkButton("Record raw session", compact=True)
        self.capture_button.setCheckable(True)
        self.capture_button.toggled.connect(self.capture_toggled.emit)
        row.addWidget(self.capture_button)
        row.addStretch(1)
        plate.body.addLayout(row)

        self.capture_note = BodyLabel("", size=13, colour=theme.CHALK)
        self.capture_note.setWordWrap(True)
        plate.body.addWidget(self.capture_note)
        return plate

    def _ptt_plate(self) -> Plate:
        plate = Plate("Push to talk")
        plate.body.addWidget(BodyLabel(
            "Hold the button, ask, let go. Map a wheel button to a key in the "
            "Fanatec software, then name that key here.",
            size=13, colour=theme.STENCIL_DIM))

        self.ptt_enabled = QCheckBox("Push to talk is on")
        plate.body.addWidget(self.ptt_enabled)

        self.ptt_key = QComboBox()
        self.ptt_key.setEditable(True)
        self.ptt_key.addItems(COMMON_KEYS)
        block_wheel(self.ptt_key)
        plate.body.addWidget(Field(
            "Button", self.ptt_key,
            hint="A key name, as pynput reports it."))

        self.ptt_in_practice = QCheckBox("Also arm it during practice")
        self.ptt_in_practice.setToolTip(
            "The engineer only answers during a race. Arming it in practice "
            "lets you check the button works without racing to find out.")
        plate.body.addWidget(self.ptt_in_practice)

        plate.body.addWidget(self._rule_label("What this machine has"))
        self.engine_note = Measured("—", size=14)
        plate.body.addWidget(self.engine_note)

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        self.listen_button = MarkButton("Listen for the button", compact=True)
        self.listen_button.clicked.connect(self._on_listen)
        row.addWidget(self.listen_button)
        row.addStretch(1)
        plate.body.addLayout(row)

        self.ptt_note = BodyLabel("", size=13, colour=theme.CHALK)
        plate.body.addWidget(self.ptt_note)
        plate.body.addStretch(1)
        return plate

    def _beep_plate(self) -> Plate:
        plate = Plate("Shift beep")
        plate.body.addWidget(BodyLabel(
            "One beep as the rpm crosses the threshold, re-armed once it "
            "falls back. It never sounds off track, and a downshift mutes it "
            "briefly so the throttle blip cannot trigger it.",
            size=13, colour=theme.STENCIL_DIM))

        self.beep_enabled = QCheckBox("Shift beep is on")
        plate.body.addWidget(self.beep_enabled)

        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP)

        self.rpm_source = QComboBox()
        for key, label in RPM_LABELS.items():
            self.rpm_source.addItem(label, key)
        self.rpm_source.currentIndexChanged.connect(self._sync_rpm_enabled)
        block_wheel(self.rpm_source)

        self.beep_rpm = QDoubleSpinBox()
        self.beep_rpm.setRange(1000.0, 20000.0)
        self.beep_rpm.setDecimals(0)
        self.beep_rpm.setSingleStep(50.0)
        self.beep_rpm.setValue(7000.0)

        grid.addWidget(Field("Threshold from", self.rpm_source), 0, 0)
        grid.addWidget(Field("Beep at", self.beep_rpm, suffix="RPM",
                             hint="Lower it to short-shift."), 0, 1)
        plate.body.addLayout(grid)

        plate.body.addWidget(BodyLabel(
            "GT7 sends each car's own shift-light rpm, so the game's setting "
            "follows the car without you entering anything. A number you "
            "choose applies to every car until you change it.",
            size=13, colour=theme.STENCIL_DIM))

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        beep = MarkButton("Test beep", compact=True)
        beep.clicked.connect(self.test_beep_requested.emit)
        voice = MarkButton("Test engineer voice", compact=True)
        voice.clicked.connect(self.test_voice_requested.emit)
        row.addWidget(beep)
        row.addWidget(voice)
        row.addStretch(1)
        plate.body.addLayout(row)

        self.beep_note = BodyLabel("", size=13, colour=theme.CHALK)
        plate.body.addWidget(self.beep_note)
        plate.body.addStretch(1)
        return plate

    def _rig_plate(self) -> Plate:
        """The transducer and the fans - what the app drives rather than reads.

        Both are off until switched on: the transducer puts 150 W into a piston
        under the seat, and neither is something that should start making
        itself felt because the app was updated.

        The gain exists because the amplifier is already at its maximum, 50 of
        50, so there is no knob left on the hardware. The balance BETWEEN the
        effects is the driver's own SimHub tuning and belongs in the effect
        list; this moves all of it together, which is the adjustment that
        cannot be made anywhere else.
        """
        plate = Plate("Rig")
        plate.body.addWidget(BodyLabel(
            "Wind and haptics, driven straight from the telemetry. Both need "
            "their hardware connected — a transducer that is not there stays "
            "silent rather than borrowing another card.",
            size=13, colour=theme.STENCIL_DIM))

        self.haptics_enabled = QCheckBox("Transducer is on")
        plate.body.addWidget(self.haptics_enabled)

        self.haptics_gain = QDoubleSpinBox()
        self.haptics_gain.setRange(0.0, 4.0)
        self.haptics_gain.setSingleStep(0.1)
        self.haptics_gain.setDecimals(1)
        block_wheel(self.haptics_gain)
        plate.body.addWidget(Field(
            "Strength", self.haptics_gain, suffix="x",
            hint="1.0 is the level the amplifier was calibrated against. The "
                 "limiter holds the ceiling whatever this is set to — past "
                 "about 2.5 the balance between effects is the thing to "
                 "change, not the level."))

        self.wind_enabled = QCheckBox("Wind simulator is on")
        plate.body.addWidget(self.wind_enabled)

        self.rig_note = BodyLabel("", size=13, colour=theme.STENCIL_DIM)
        self.rig_note.setWordWrap(True)
        plate.body.addWidget(self.rig_note)

        row = QHBoxLayout()
        row.setSpacing(theme.GAP)
        test = MarkButton("Test transducer", compact=True)
        test.clicked.connect(self.test_haptics_requested.emit)
        row.addWidget(test)
        row.addStretch(1)
        plate.body.addLayout(row)
        return plate

    def note_rig(self, text: str, *, warn: bool = False) -> None:
        self.rig_note.setText(text)
        self.rig_note.setStyleSheet(
            f"color: {theme.DANGER_INK};" if warn else "")

    def _audio_plate(self) -> Plate:
        """Which sound card the engineer speaks into, and which one hears him.

        This exists because of what silence looked like without it. PortAudio
        resolves "the default device" once, when it is first imported; the
        driver puts the PSVR2 on after the app is already running, so the call
        went to whatever was default at launch. A disconnected endpoint does
        not raise - measured, a full second of audio written to one completed
        and returned cleanly - so the engineer spoke, the counter went up, the
        call appeared on the race screen, and the man in the headset heard
        nothing with every indicator green.

        Named devices rather than indices: PortAudio renumbers whenever
        something is plugged in, and a stale index is how this failed before.
        """
        plate = Plate("Sound devices")
        plate.body.addWidget(BodyLabel(
            "Set these to the headset you race in. Left on the system "
            "default, a device connected after the app started will not be "
            "found, and nothing will say so.",
            size=13, colour=theme.STENCIL_DIM))

        self.audio_output = QComboBox()
        self.audio_input = QComboBox()
        for combo, kind in ((self.audio_output, "output"),
                            (self.audio_input, "input")):
            combo.addItem("System default", "")
            for _index, name in audio_devices.devices(kind):
                combo.addItem(name, name)
            mark_unset(combo, unset="")

        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP)
        grid.addWidget(Field("He hears the engineer on", self.audio_output), 0, 0)
        grid.addWidget(Field("The engineer hears him on", self.audio_input), 1, 0)
        plate.body.addLayout(grid)
        return plate

    def _voice_plate(self) -> Plate:
        """How the engineer sounds.

        Here rather than in a file because this app reads no config file, and
        at the rig rather than in code because it is settled by ear.
        """
        plate = Plate("Engineer's voice")
        plate.body.addWidget(BodyLabel(
            "A race engineer is calm. Jitter is what makes a synthetic voice "
            "sound nervous — it is the one to reach for first.",
            size=13, colour=theme.STENCIL_DIM))

        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.GAP)
        grid.setVerticalSpacing(theme.GAP)

        self.length_scale = self._tuning_box(0.5, 2.0, 0.02, 1.12)
        self.noise_scale = self._tuning_box(0.0, 1.5, 0.05, 0.60)
        self.noise_w_scale = self._tuning_box(0.0, 1.5, 0.05, 0.55)

        grid.addWidget(Field("Pace", self.length_scale,
                             hint="Higher is slower."), 0, 0)
        grid.addWidget(Field("Timbre variation", self.noise_scale), 0, 1)
        grid.addWidget(Field("Jitter", self.noise_w_scale,
                             hint="Lower is calmer."), 1, 0)
        plate.body.addLayout(grid)
        return plate

    def _tuning_box(self, low: float, high: float, step: float,
                    value: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(low, high)
        box.setSingleStep(step)
        box.setDecimals(2)
        box.setValue(value)
        block_wheel(box)
        return box

    def _rule_label(self, text: str) -> StencilLabel:
        label = StencilLabel(text, size=11, tracking=12.0)
        label.setContentsMargins(0, 8, 0, 0)
        return label

    def _footer(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(72)
        row = QHBoxLayout(bar)
        row.setContentsMargins(0, theme.GAP, 0, theme.GAP)
        row.setSpacing(theme.GAP)
        self.footer_note = BodyLabel("", size=13, colour=theme.STENCIL_DIM)
        row.addWidget(self.footer_note, 1)
        save = MarkButton("Save settings", primary=True)
        save.clicked.connect(self._on_save)
        row.addWidget(save)
        return bar

    # ---------------------------------------------------------------- state

    def load(self, settings: Settings) -> None:
        # Kept so `values()` can carry through the fields with no control on
        # this screen. Building a fresh Settings from the widgets meant every
        # Save silently rewrote `speech_backend` and `speech_sensitivity` back
        # to their defaults - settings that could be stored and never set.
        self._loaded = settings
        self.udp_port.setValue(settings.udp_port)
        self.udp_source_ip.setText(settings.udp_source_ip)
        index = self.feed_source.findData(settings.feed_source)
        self.feed_source.setCurrentIndex(max(0, index))
        self.ps5_ip.setText(settings.ps5_ip)
        self.banner_enabled.setChecked(settings.banner_enabled)
        self._sync_feed_source()
        self.game_version.setText(settings.game_version)
        for combo, chosen in ((self.audio_output, settings.audio_output_device),
                              (self.audio_input, settings.audio_input_device)):
            index = combo.findData(chosen)
            combo.setCurrentIndex(index if index >= 0 else 0)
        self.haptics_enabled.setChecked(settings.haptics_enabled)
        self.haptics_gain.setValue(settings.haptics_gain)
        self.wind_enabled.setChecked(settings.wind_enabled)
        self.ptt_enabled.setChecked(settings.ptt_enabled)
        self.ptt_key.setCurrentText(settings.ptt_key)
        self.ptt_in_practice.setChecked(settings.ptt_in_practice)
        self.beep_enabled.setChecked(settings.beep_enabled)
        index = self.rpm_source.findData(settings.beep_rpm_source)
        self.rpm_source.setCurrentIndex(max(0, index))
        self.beep_rpm.setValue(settings.beep_rpm)
        self.length_scale.setValue(settings.voice_length_scale)
        self.noise_scale.setValue(settings.voice_noise_scale)
        self.noise_w_scale.setValue(settings.voice_noise_w_scale)
        self._sync_rpm_enabled()

    def _sync_feed_source(self) -> None:
        """Show the address box only where it is read.

        In relay mode it is not a destination and never was, and leaving
        it enabled is how somebody comes to believe the app already talks
        to the console.
        """
        self.ps5_field.setVisible(self.feed_source.currentData() == FEED_PS5)

    def values(self) -> Settings:
        # `replace`, not a fresh Settings: anything this screen has no control
        # for keeps the value it was loaded with instead of reverting.
        return replace(
            getattr(self, "_loaded", Settings()),
            udp_port=self.udp_port.value(),
            udp_source_ip=self.udp_source_ip.text().strip(),
            feed_source=self.feed_source.currentData(),
            ps5_ip=self.ps5_ip.text().strip(),
            banner_enabled=self.banner_enabled.isChecked(),
            game_version=self.game_version.text().strip() or "1.70",
            ptt_enabled=self.ptt_enabled.isChecked(),
            ptt_key=self.ptt_key.currentText().strip().lower(),
            ptt_in_practice=self.ptt_in_practice.isChecked(),
            beep_enabled=self.beep_enabled.isChecked(),
            beep_rpm_source=self.rpm_source.currentData() or RPM_FROM_GT7,
            beep_rpm=self.beep_rpm.value(),
            voice_length_scale=self.length_scale.value(),
            voice_noise_scale=self.noise_scale.value(),
            voice_noise_w_scale=self.noise_w_scale.value(),
            audio_output_device=self.audio_output.currentData() or "",
            audio_input_device=self.audio_input.currentData() or "",
            haptics_enabled=self.haptics_enabled.isChecked(),
            haptics_gain=self.haptics_gain.value(),
            wind_enabled=self.wind_enabled.isChecked(),
        )

    def _sync_rpm_enabled(self) -> None:
        """A threshold the game supplies is not one the driver can type into."""
        manual = self.rpm_source.currentData() == RPM_MANUAL
        self.beep_rpm.setEnabled(manual)

    def show_capabilities(self, *, speech: str, hook: bool) -> None:
        """What actually loaded on this machine, as opposed to what was asked
        for. Measured, so it is stencilled."""
        button = "keyboard hook loaded" if hook else "NO keyboard hook"
        self.engine_note.setText(f"speech: {speech} · {button}")
        self.engine_note.setStyleSheet(
            f"color: {theme.STENCIL if hook else theme.WARNING};"
            "background: transparent;")

    def set_listening(self, listening: bool) -> None:
        self._listening = listening
        self.listen_button.setText(
            "STOP LISTENING" if listening else "LISTEN FOR THE BUTTON")
        if listening:
            self.note_ptt("Listening. Press the button on the wheel.")

    def note_ptt(self, text: str, *, warn: bool = False) -> None:
        self.ptt_note.setText(text)
        self.ptt_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};"
            "background: transparent;")

    def note_capture(self, text: str, *, warn: bool = False) -> None:
        self.capture_note.setText(text)
        self.capture_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};"
            "background: transparent;")

    def set_capturing(self, on: bool) -> None:
        """Reflect what is actually happening, not what was clicked."""
        was = self.capture_button.blockSignals(True)
        self.capture_button.setChecked(on)
        self.capture_button.setText(
            "Stop recording" if on else "Record raw session")
        self.capture_button.blockSignals(was)

    def set_feed_testing(self, testing: bool) -> None:
        """The four seconds the socket is open, said out loud."""
        self.test_feed_button.setEnabled(not testing)
        self.test_feed_button.setText(
            "Listening…" if testing else "Test the feed")
        if testing:
            self.note_feed("Listening for four seconds. If the console is "
                           "streaming, this will say what decoded.")

    def note_feed(self, text: str, *, warn: bool = False) -> None:
        self.feed_note.setText(text)
        self.feed_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};"
            "background: transparent;")

    def note_beep(self, text: str, *, warn: bool = False) -> None:
        self.beep_note.setText(text)
        self.beep_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};"
            "background: transparent;")

    def note(self, text: str, *, warn: bool = False) -> None:
        self.footer_note.setText(text)
        self.footer_note.setStyleSheet(
            f"color: {theme.WARNING if warn else theme.CHALK};")

    # --------------------------------------------------------------- actions

    def _on_listen(self) -> None:
        self.listen_toggled.emit(not self._listening)

    def _on_save(self) -> None:
        try:
            self.values().validate()
        except ValueError as exc:
            self.note(f"Refused: {exc}", warn=True)
            return
        self.note("")
        self.saved.emit(self.values())
