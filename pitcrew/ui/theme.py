"""Marked Set — the visual world of Pit Crew.

THESIS: A set of tyres arrives blank and black, and the crew marks it in three
registers that are never confused: moulded stencil is manufacturer fact, the
coloured band is classification read at a glance, and grease pencil is the
crew's own hand. This app carries provenance the same way, so measured, derived
and declared never look alike. It refuses the category's glowing-gauge
telemetry dashboard and its opposite, the grey admin panel with a data table.

OWN-WORLD: Warm carbon ground (rubber, not blue-black), matte tyre-shoulder
panels, moulded-groove rules. Lettering is DIN 1451 condensed caps, tracked
wide, the way sidewalls and technical plates are stencilled. Measured values
are stencil white in mono; anything the driver typed is tyre-crayon orange;
provisional annotation is chalk. Compound bands wear their real racing colours
and carry their own two-letter code, so colour is reinforcement and never the
only channel.

STORY: The driver comes back from a stint, headset off, and marks up what he
just ran — which compound, which laps do not count, what the gauge read. The
rack fills with colour and the shape of the session becomes visible.

FIRST VIEWPORT: A stencilled sidewall header naming the event, then the rack:
one row per lap, each with its compound band down the left edge at full row
height. Primary action sits at the foot of the rack, where the run ends.

FORM: Marked Set, candidate 7 of the grounded list; seed key 898a8d6e.

FINISH: unreviewed and undocumented is unfinished; this build ends with the
finish review, the verdict, and DESIGN.md.
"""
from __future__ import annotations

from PyQt6.QtGui import QColor, QFont

# --------------------------------------------------------------------- ground
#
# Warm carbon, not blue-black. A garage at night is lit by work lamps, and
# rubber is brown-black under them. The scene decided this, not the category:
# the app sits on the upper monitor at the rig with the headset just pushed up.

RUBBER = "#14120F"          # page ground
RUBBER_DEEP = "#0C0B09"     # wells the rack sits in
SHOULDER = "#1E1B17"        # panel face, matte
SHOULDER_HI = "#282420"     # hover / raised
TREAD = "#38332B"           # moulded groove: borders and rules
TREAD_LIGHT = "#4A443A"     # focused border

# ------------------------------------------------------------------ registers
#
# The three marks, and the whole point of the world.

STENCIL = "#E8E4DC"         # MEASURED - came off the telemetry stream
STENCIL_DIM = "#9A948A"     # secondary, still measured
CRAYON = "#FF6B1A"          # DECLARED - the driver typed this
CHALK = "#7FC7D9"           # provisional annotation, notes, hints
STRUCK = "#6B6459"          # struck out: excluded, disabled, not counted

WARNING = "#F2C230"
DANGER = "#E8352E"

# ------------------------------------------------------------- compound bands
#
# Real racing colours. These are not decoration - they are the classification
# system the driver already reads at a glance, and they are already the app's
# data (RH / RM / RS / IM / HW). Every band also carries its code, so a viewer
# who cannot separate the hues loses nothing.

COMPOUND_BANDS: dict[str, str] = {
    "RS": "#E8352E",   # racing soft - red
    "RM": "#F2C230",   # racing medium - yellow
    "RH": "#E8E4DC",   # racing hard - white
    "IM": "#3FA34D",   # intermediate - green
    "HW": "#2D7DD2",   # heavy wet - blue
    "SS": "#C8703C",   # sports, bronze family
    "SM": "#A9602F",
    "SH": "#8A5127",
    "CS": "#6E7B8B",   # comfort, cool grey family
    "CM": "#5C6775",
    "CH": "#4A535E",
}
UNMARKED_BAND = "#2A2620"   # a set nobody has chalked yet


def band_colour(code: str | None) -> QColor:
    if not code:
        return QColor(UNMARKED_BAND)
    return QColor(COMPOUND_BANDS.get(code.upper(), UNMARKED_BAND))


def band_ink(code: str | None) -> QColor:
    """Legible ink for the code stencilled on a band."""
    colour = band_colour(code)
    luminance = (0.299 * colour.red() + 0.587 * colour.green()
                 + 0.114 * colour.blue()) / 255.0
    return QColor(RUBBER) if luminance > 0.55 else QColor(STENCIL)


# ------------------------------------------------------------------ lettering
#
# DIN 1451 is the German industrial signage standard - the lettering of
# technical plates, stencils and moulded sidewall codes. Bahnschrift is that
# face. It is the right letter for this world, and ships with Windows.
# Measurement is set in mono because it IS measurement, not to look technical.

STENCIL_FAMILY = "Bahnschrift"
STENCIL_CONDENSED = "Bahnschrift Condensed"
DATA_FAMILY = "Cascadia Mono"
DATA_FALLBACK = "Consolas"


def stencil_font(size: int, *, weight: QFont.Weight = QFont.Weight.DemiBold,
                 tracking: float = 8.0, condensed: bool = True) -> QFont:
    """Tracked caps, the way a stencil is cut.

    Qt style sheets carry no letter-spacing, so tracking is set on the font.
    """
    font = QFont(STENCIL_CONDENSED if condensed else STENCIL_FAMILY)
    font.setPixelSize(size)
    font.setWeight(weight)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100.0 + tracking)
    font.setCapitalization(QFont.Capitalization.AllUppercase)
    return font


def text_font(size: int, *, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont(STENCIL_FAMILY)
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


def data_font(size: int, *, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont(DATA_FAMILY)
    if not font.exactMatch():
        font = QFont(DATA_FALLBACK)
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


# ---------------------------------------------------------------------- scale
#
# Read from the driving position on the upper monitor, headset just off, so
# every step runs larger than a desk app's default.

TITLE_PX = 30
HEADING_PX = 17
LABEL_PX = 12
BODY_PX = 15
DATA_PX = 15
DATA_LARGE_PX = 23

# Tight groups, generous separation.
GAP_TIGHT = 6
GAP = 12
GAP_WIDE = 22
GAP_SECTION = 34

STYLESHEET = f"""
QWidget {{
    background: {RUBBER};
    color: {STENCIL};
    font-family: "{STENCIL_FAMILY}";
    font-size: {BODY_PX}px;
}}

QScrollArea, QScrollArea > QWidget > QWidget {{
    background: transparent;
    border: none;
}}

QScrollBar:vertical {{
    background: {RUBBER_DEEP};
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {TREAD};
    min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{ background: {TREAD_LIGHT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

/* No `color` here on purpose. A stylesheet colour beats the palette's
   PlaceholderText role, so setting it makes an empty field render in crayon -
   an unfilled setting that looks declared. Text colour comes from the palette
   (Text and ButtonText are crayon; PlaceholderText is struck). */
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {RUBBER_DEEP};
    border: 1px solid {TREAD};
    border-radius: 0;
    padding: 7px 10px;
    font-family: "{DATA_FAMILY}";
    font-size: {DATA_PX}px;
    selection-background-color: {CRAYON};
    selection-color: {RUBBER};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {CRAYON};
}}
QLineEdit:disabled, QComboBox:disabled,
QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {STRUCK};
    border-color: {SHOULDER_HI};
}}
QLineEdit::placeholder {{ color: {STRUCK}; }}

QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {RUBBER_DEEP};
    border: 1px solid {TREAD};
    color: {STENCIL};
    selection-background-color: {SHOULDER_HI};
    selection-color: {CRAYON};
    outline: none;
    padding: 2px;
}}

QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    background: {SHOULDER};
    border: none;
    width: 16px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {SHOULDER_HI};
}}

/* A ticked symptom is the driver's own mark, so the box fills with crayon.
   Square, not rounded, and no tick glyph: there are no icons in this world,
   and a filled box reads at a glance from the driving position. */
QCheckBox {{
    background: transparent;
    color: {STENCIL_DIM};
    spacing: 9px;
    padding: 3px 0;
}}
QCheckBox:hover {{ color: {STENCIL}; }}
QCheckBox:checked {{ color: {STENCIL}; }}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    background: {RUBBER_DEEP};
    border: 1px solid {TREAD_LIGHT};
}}
QCheckBox::indicator:hover {{ border-color: {CRAYON}; }}
QCheckBox::indicator:checked {{
    background: {CRAYON};
    border-color: {CRAYON};
}}

QToolTip {{
    background: {SHOULDER};
    color: {STENCIL};
    border: 1px solid {TREAD};
    padding: 6px 8px;
}}
"""


def apply(app) -> None:
    """Install the world on a QApplication.

    The palette matters as much as the sheet here. Qt has no `::placeholder`
    selector, so without this a placeholder inherits the editor's text colour
    and renders in crayon - making an empty field look like a value the driver
    declared. In a product whose first principle is that measured, derived and
    declared must never look alike, that is not a cosmetic bug.
    """
    from PyQt6.QtGui import QPalette

    app.setStyleSheet(STYLESHEET)
    palette = app.palette()
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(STRUCK))
    palette.setColor(QPalette.ColorRole.Window, QColor(RUBBER))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(STENCIL))
    palette.setColor(QPalette.ColorRole.Base, QColor(RUBBER_DEEP))
    palette.setColor(QPalette.ColorRole.Text, QColor(CRAYON))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(CRAYON))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(CRAYON))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(RUBBER))
    palette.setColor(QPalette.ColorGroup.Disabled,
                     QPalette.ColorRole.Text, QColor(STRUCK))
    palette.setColor(QPalette.ColorGroup.Disabled,
                     QPalette.ColorRole.ButtonText, QColor(STRUCK))
    app.setPalette(palette)
