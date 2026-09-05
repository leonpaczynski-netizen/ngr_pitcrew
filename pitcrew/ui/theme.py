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
TREAD_LIGHT = "#4A443A"
# **A border token. Never text.** The rail set its group headings and every
# state note in this at 10px on RUBBER_DEEP - 2.04:1, materially worse than
# the STRUCK the design rejected for exactly this, and on the one surface used
# on every visit. It escaped both guards: the body-floor test checks six named
# inks and this was not one, and the struck-prose test greps pitcrew/ui/*.py
# while the rail lives in app.py. Both are widened; this comment is the third
# lock.     # focused border

# ------------------------------------------------------------------ registers
#
# The three marks, and the whole point of the world.

STENCIL = "#E8E4DC"         # MEASURED - came off the telemetry stream
STENCIL_DIM = "#9A948A"     # secondary, still measured
CRAYON = "#A3E635"          # DECLARED - the driver typed this
# **The brand's own green, not a marker-pen orange.** The register is
# unchanged - this is still the ink that means "he entered this himself" - but
# the hue is Next Gear Racing's now, because the app had no colour in common
# with the thing it is called.
#
# Chosen against the fixed colours rather than sampled off the logo. The logo's
# own lime runs #84B400-#C0E430, tuned to glow on black in a mark nobody reads
# at 15px; those sit 27-30 degrees of hue from WARNING and from the Racing
# Medium band, which is too close for an ink that appears beside them on the
# same row. This one is 38 degrees off both.
#
# It also fixes an inversion nobody had noticed: the orange carried 6.6:1 on
# the page ground, so the ink the driver reads most - every value he entered,
# on every screen - was the third most legible of the four registers, behind
# two he reads occasionally. This one carries 12.4:1.
#
# It shares a family with the Intermediate band (#3FA34D) and does not collide
# with it: that band is a dark desaturated mid-green painted as a block, this
# is bright acid text, and every band carries its two-letter code anyway.
DERIVED = "#B08BD8"         # DERIVED - the app worked this out
# ---- the timing marks: the motorsport convention, verbatim -----------------
#
# **Purple, green, yellow, white — and it is not ours to reinterpret.** This
# is the FIA timing convention, used on every F1 timing screen, and GT7's own
# HUD follows it:
#
#   purple  the fastest anyone has set in the session
#   green   a personal best — you improved on your own
#   yellow  slower than your own best
#   white   no reference set yet
#
# It got here in two wrong steps, both worth writing down. First the rank was
# painted as two very dark FILLS behind the number, on the argument that
# purple ink was spoken for by the DERIVED register — while purple-for-derived
# was itself argued FROM timing-screen convention. Both cannot be true, and
# the cost was that every sector on the rack came out purple, because every
# sector is the app's own cut of the lap. The driver read exactly what was
# painted: *every sector looks like it's the best sector.*
#
# Then it was rebuilt as purple / blue / white on the driver's own offhand
# description, which was his memory of GT7 rendering the personal-best green
# with a blue cast. Close, and still not the convention. **A convention is
# looked up, not recalled** — the whole value of using one is that he already
# knows how to read it, and a private variant of it is worth less than none.
#
# The one-driver mapping, which is the only interpretation this app has to
# make: the outright benchmark is the fastest ever set here in this car, and
# "your own best" is the best of the stint being driven.
BEST_EVER = "#C77DFF"       # purple - fastest ever here, in this car
BEST_STINT = "#2FD16B"      # green  - a personal best for this stint
SLOWER = "#A89A45"          # yellow - slower than the best of its stint
# Measured on `RUBBER_DEEP`: purple 7.31:1, green 9.79:1, yellow 6.91:1.
#
# **The yellow is deliberately the dimmest of the three**, and the first
# attempt at it was not - a lemon at 13.88:1, brighter than both marks and
# nearly as bright as white. The hue was right and the hierarchy was upside
# down: yellow is the ORDINARY state, most laps are slower than your best by
# definition, and on a rack of twelve laps that is fifty figures competing
# with the two that matter. A timing screen carries a handful of rows; this
# carries a stint. Same convention, sized for the density it is actually
# used at.
#
# **Yellow sits 9 degrees of hue from `WARNING`, and that is allowed here**
# because the two never appear in the same role: `WARNING` is prose — a footer
# sentence, a refused export — and never a value, and the timing yellow is
# only ever a value in a time column and never prose. The pairing to avoid is
# two meanings in one place, not two colours in one app.
#
# **Green sits 59 degrees from `CRAYON`**, which is an acid lime, and the
# argument that they cannot be confused is stronger than the distance: the
# rack's time columns contain no declared values at all. A lap time, a delta
# and three sectors are measured or computed — never typed. Everything the
# driver declares on this screen is a control on the right of the row: the
# compound picker, the fresh-set picker, the wear cell. Green in a time column
# cannot be read as "he typed this", because nothing in a time column ever is.
CHALK = "#7FC7D9"           # provisional annotation, notes, hints
STRUCK = "#807870"          # struck out: excluded, disabled, not counted
# Lifted from #6B6459, which carried 3.37:1 on the editor ground. WCAG exempts
# *disabled* controls, and this ink is used for those - but it is also every
# placeholder in the app and the "-" of an unset field, and those are live,
# meaningful state rather than something switched off. "Nothing entered" is a
# reading the driver has to be able to take. 4.5:1 now.

# Why purple for derived, in a world with no decoration in it:
#
# The thesis said three registers, and three was one short. Measured has an
# ink and declared has an ink, so everything the app *computed* had to borrow
# one - and it borrowed badly. `ASSUMED` took STRUCK, colliding with disabled
# and excluded; "Box in 3", the highest-consequence number this product emits,
# took CRAYON, the ink that means the driver typed it himself. Both are the
# failure the whole system exists to prevent.
#
# Purple is not a fourth colour picked to be different. On a timing screen it
# is already the sport's own mark for a figure the system worked out rather
# than one somebody set - the fastest sector, computed and posted. It is the
# right borrowed convention, the way DIN lettering and compound bands are.
#
# Weighted to sit alongside crayon rather than shout over it: 6.15:1 on the
# panel face against crayon's 6.02:1. Derived is not more important than
# declared. It is a different kind of claim.

WARNING = "#F2C230"
DANGER = "#E8352E"
# The same red lifted until it clears the body floor as *text*. DANGER is the
# racing red and it is 3.65:1 on the hover ground at 13px DemiBold, which is
# not large text - fine as a border, not as a word. The border keeps the
# racing red so a destructive control still reads as the dangerous one.
DANGER_INK = "#FF6B63"
# Hover for a crayon-filled button: the same lime, opened up. It was the one
# unnamed colour literal in the whole system.
CRAYON_HOT = "#BEF264"

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

# The three phases of the wear model, on the tyre gauge. Named rather than
# written inline: the flat phase used to be the literal #3FA34D, which is
# byte-identical to the Intermediate band - so one green meant "intermediate
# compound" on a stint bar and "this tyre is fine" on a gauge two screens
# away. Either meaning is defensible; sharing the hex by accident is not.
WEAR_FLAT = "#4FB06A"
WEAR_LINEAR = "#F2C230"
WEAR_CLIFF = "#E8352E"


def band_colour(code: str | None) -> QColor:
    if not code:
        return QColor(UNMARKED_BAND)
    return QColor(COMPOUND_BANDS.get(code.upper(), UNMARKED_BAND))


def _relative_luminance(colour: QColor) -> float:
    """WCAG relative luminance, which is not the same as perceived brightness."""
    channels = []
    for value in (colour.red(), colour.green(), colour.blue()):
        channel = value / 255.0
        channels.append(channel / 12.92 if channel <= 0.03928
                        else ((channel + 0.055) / 1.055) ** 2.4)
    return (0.2126 * channels[0] + 0.7152 * channels[1]
            + 0.0722 * channels[2])


def contrast_ratio(one: QColor, two: QColor) -> float:
    first, second = _relative_luminance(one), _relative_luminance(two)
    high, low = max(first, second), min(first, second)
    return (high + 0.05) / (low + 0.05)


def band_ink_for(band: QColor) -> QColor:
    """Legible ink for a code stencilled on the colour ACTUALLY painted.

    Whichever of the two inks contrasts better against that colour, measured -
    not whichever side of a brightness threshold it falls on.

    The threshold version used NTSC coefficients against a fixed 0.55, and it
    got six of the eleven compounds wrong: Intermediate green took warm white
    at 2.53:1 and Sports Soft bronze at 2.84:1, both below even the large-text
    floor. That matters more here than anywhere else in the app, because the
    two-letter code is the redundant channel - the thing that carries the
    classification for a viewer who cannot separate the hues. A code nobody
    can read leaves colour as the only channel, which is the one outcome the
    band exists to prevent.

    The argument is a colour and not a compound code because a band is not
    always painted in its own colour: an excluded lap's band is desaturated
    toward grey, and choosing the ink from the code would choose it against a
    colour that is no longer on the screen.
    """
    dark, light = QColor(RUBBER), QColor(STENCIL)
    return dark if contrast_ratio(dark, band) >= contrast_ratio(light, band) \
        else light


def band_ink(code: str | None) -> QColor:
    """Legible ink for a compound's code on that compound's own band.

    The undesaturated case of `band_ink_for`, and defined in terms of it so
    the two cannot answer differently for the same painted colour.
    """
    return band_ink_for(band_colour(code))


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
# A plate's own label has to outrank the captions inside it. It was 12px in
# STENCIL_DIM against 11px captions in the same colour - the container quieter
# than its contents - which left a 23-key form with its only chunking device
# as the least legible text on the screen.
PLATE_TITLE_PX = 15
LABEL_PX = 12
BODY_PX = 15
DATA_PX = 15
DATA_LARGE_PX = 23

# Tight groups, generous separation.
GAP_TIGHT = 6
# Width the stylesheet gives a scrollbar. Named because a layout that has to
# line up either side of one needs to reserve exactly this and not guess.
SCROLLBAR_WIDTH = 12

GAP = 12
GAP_WIDE = 22
GAP_SECTION = 34

STYLESHEET = f"""
/* No `color` on QWidget. A Qt stylesheet rule on QWidget matches every
   subclass, including QLineEdit, QComboBox and QSpinBox - and a stylesheet
   colour beats a palette role. Setting it here painted every value the driver
   typed in STENCIL, the ink that means "came off the telemetry stream", so
   declared and measured were pixel-identical everywhere in the app and the
   register system existed only in the comments.

   The editor rule below already carried a warning about exactly this
   mechanism. It guarded three rules too late. Text colour comes from the
   palette: WindowText is stencil, Text and ButtonText are crayon,
   PlaceholderText is struck. `theme.apply()` sets all four. */
QWidget {{
    background: {RUBBER};
    font-family: "{STENCIL_FAMILY}";
    font-size: {BODY_PX}px;
}}

QScrollArea, QScrollArea > QWidget > QWidget {{
    background: transparent;
    border: none;
}}

QScrollBar:vertical {{
    background: {RUBBER_DEEP};
    width: {SCROLLBAR_WIDTH}px;
    margin: 0;
}}
QScrollBar:horizontal {{
    background: {RUBBER_DEEP};
    height: {SCROLLBAR_WIDTH}px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {TREAD};
    min-width: 40px;
}}
QScrollBar::handle:horizontal:hover {{ background: {TREAD_LIGHT}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}
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
    font-family: "{STENCIL_FAMILY}";
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
/* No `::placeholder` rule here. Qt has no such selector - the
   comment twenty lines above says so, and this file carried one
   anyway. Placeholder colour comes from QPalette.PlaceholderText,
   set in `apply()`. */

/* **Mono is measurement, not a costume for "technical".** This face used to
   be on every editor without exception, which set the event name, the notes,
   the paste box and the driver's own words - the most valuable field on the
   screen, by its own label - in a typewriter. The world's ban list closes on
   "monospace anywhere it is not measurement".
   It is put back for the editors that genuinely hold a figure, keyed on a
   dynamic property so the decision is made once, by `Field`, at the point
   where the editor's kind is actually known. */
QSpinBox, QDoubleSpinBox,
QLineEdit[data="true"], QPlainTextEdit[data="true"] {{
    font-family: "{DATA_FAMILY}";
}}

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
/* **Crayon, not stencil.** A checkbox in this app is only ever the driver's
   own mark - 28 symptoms on Engineer, every toggle on Settings and Car - so a
   ticked one painting STENCIL put his declaration in the ink reserved for
   things that came off the telemetry stream. The indicator below already
   fills with crayon; the label was saying the opposite. Same
   stylesheet-beats-palette mechanism the two warnings in this file exist to
   prevent, one selector further down. */
QCheckBox:checked {{ color: {CRAYON}; }}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    background: {RUBBER_DEEP};
    border: 1px solid {TREAD_LIGHT};
}}
QCheckBox::indicator:hover {{ border-color: {CRAYON}; }}
/* Restyling the indicator suppresses Qt's own focus rect, so it has to be
   put back. The Engineer screen has 28 of these and they were focusable with
   nothing at all to show for it. Chalk, matching the button rule. */
QCheckBox:focus {{ color: {STENCIL}; }}
QCheckBox::indicator:focus {{ border: 1px solid {CHALK}; }}
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
