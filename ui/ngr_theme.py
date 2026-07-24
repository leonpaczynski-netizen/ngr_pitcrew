"""NGR Enterprise design system — the single source of truth for Pit Crew's look.

This module is the shared, testable foundation for the app's visual language.
It is deliberately split into two layers:

  * **Pure layer** (Qt-free): brand colour tokens, spacing/typography scale, and
    QSS *string* builders (``app_stylesheet``, ``badge_qss``, ``banner_qss`` …).
    These are importable and unit-testable without a running QApplication.
  * **Qt layer** (imports PyQt6 lazily inside functions): widget/pixmap helpers
    (``logo_pixmap``, ``heading_label``, ``status_badge``, ``advisory_banner``,
    ``empty_state_label``).

Design intent — a dark, cinematic pit-wall interface: charcoal / carbon
surfaces, clean white typography, a neon-green NGR accent, strong uppercase
headings, and touch-comfortable sizing for tablet use on the pit wall.

SAFETY: this module is presentation-only. It authors no product behaviour,
reads no telemetry, and mutates no files. The global stylesheet is *additive* —
it styles specific widget classes only (never a blanket ``QWidget {}``), so the
app's existing inline ``setStyleSheet`` calls always win for their own widgets
and nothing that already worked can break.
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Brand colour tokens — NGR Enterprise "pit-wall" palette
# ---------------------------------------------------------------------------
# Surfaces run deepest → raised so cards lift cleanly off the background.
INK_BLACK      = "#0C0E10"   # deepest pit-wall black (app frame / status bar)
CARBON         = "#141619"   # primary window surface
CARBON_RAISED  = "#1D2024"   # cards, panels, group boxes
CARBON_HI      = "#262A2F"   # inputs, hover fills
HAIRLINE       = "#333941"   # borders / dividers
HAIRLINE_SOFT  = "#2A2F35"   # low-emphasis separators

# Typography
TEXT_HI   = "#F4F6F8"        # primary white — headings, key values
TEXT      = "#D7DCE1"        # body copy
TEXT_DIM  = "#9AA1A9"        # secondary labels, captions
TEXT_MUTE = "#6E767F"        # placeholders, disabled

# NGR neon-green accent
NGR_GREEN      = "#2EE86E"   # brand accent — highlights, active nav, focus
NGR_GREEN_HI   = "#4FF588"   # hover/bright
NGR_GREEN_DIM  = "#1E9E4C"   # pressed / lower-emphasis green
NGR_GREEN_INK  = "#0C0E10"   # text that sits ON the neon green (dark, for contrast)

# Semantic status colours (each is paired with a text label elsewhere so meaning
# is never carried by colour alone — see status_badge / STATUS_TONES).
INFO    = "#4FC3F7"
SUCCESS = "#2EE86E"
WARN    = "#F5A623"
DANGER  = "#FF5B52"
NEUTRAL = "#9AA1A9"

# Advisory / read-only surfaces get a distinct cool tint so they never read as
# an actionable "Apply" control (a core Pit Crew safety principle).
ADVISORY_TINT   = "#16212B"   # cool slate — read-only advisory panels
ADVISORY_EDGE   = "#2A6E8C"   # muted teal edge for advisory panels

# ---------------------------------------------------------------------------
# Spacing & sizing scale (8pt rhythm, tablet-comfortable)
# ---------------------------------------------------------------------------
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24

RADIUS_SM = 4
RADIUS_MD = 6
RADIUS_LG = 8

# Touch-friendly minimum interactive height (px). Comfortable for tablet taps.
TOUCH_MIN_H = 34

# Type scale (pt)
FS_CAPTION = 9
FS_BODY    = 11
FS_LABEL   = 12
FS_H3      = 13
FS_H2      = 15
FS_H1      = 18
FS_DISPLAY = 22

FONT_FAMILY = "Segoe UI"

# Status tone table — maps a semantic key to (fill, text, border) hexes AND is
# the reason meaning is never colour-only: callers pass an explicit text label.
STATUS_TONES: dict[str, tuple[str, str, str]] = {
    "success":  ("#15351F", "#8FE9A8", "#2E7D46"),
    "info":     ("#12303B", "#9FDBF5", "#2A6E8C"),
    "warn":     ("#3A2C0E", "#F6CE7A", "#8A6516"),
    "danger":   ("#3A1613", "#FBA9A2", "#9E362E"),
    "neutral":  ("#22262B", "#C4CAD1", "#3A4148"),
    "advisory": ("#16212B", "#9FD4E6", "#2A6E8C"),
}


# ---------------------------------------------------------------------------
# UI-rebuild design tokens (additive — F0.4)
# ---------------------------------------------------------------------------
# Every state below is expressed as {tone, glyph?, label} so the "bouncing ball"
# surfaces convey meaning by colour + icon + text together, never colour alone
# (accessibility rule color-not-only). `tone` indexes STATUS_TONES; glyphs are
# plain typographic marks (no emoji) that Segoe UI renders crisply.

# Programme progress-rail stage states.
STAGE_COMPLETE     = "complete"
STAGE_CURRENT      = "current"
STAGE_AVAILABLE    = "available"
STAGE_BLOCKED      = "blocked"
STAGE_NOT_REQUIRED = "not_required"

STAGE_STATES: dict[str, dict[str, str]] = {
    STAGE_COMPLETE:     {"tone": "success", "glyph": "✓", "label": "Complete"},      # ✓
    STAGE_CURRENT:      {"tone": "info",    "glyph": "▶", "label": "Current"},        # ▶ (rail applies NGR_GREEN accent)
    STAGE_AVAILABLE:    {"tone": "neutral", "glyph": "○", "label": "Available"},      # ○
    STAGE_BLOCKED:      {"tone": "warn",    "glyph": "✕", "label": "Blocked"},        # ✕
    STAGE_NOT_REQUIRED: {"tone": "neutral", "glyph": "–", "label": "Not required"},   # –
}
# The rail draws the current stage with the brand accent; kept explicit so the
# widget never hard-codes a hex.
STAGE_CURRENT_ACCENT = NGR_GREEN

# Confidence ladder — colour + label + a 0..1 fill for a bar (never colour alone).
CONFIDENCE_LEVELS: dict[str, dict] = {
    "high":    {"tone": "success", "label": "High",        "fill": 1.0},
    "medium":  {"tone": "info",    "label": "Medium",      "fill": 0.66},
    "low":     {"tone": "warn",    "label": "Low",         "fill": 0.33},
    "unknown": {"tone": "neutral", "label": "No evidence", "fill": 0.0},
}

# Setup-experiment / change outcome. "Worse" is DANGER and prominent by design —
# negative feedback must be authoritative, never softened.
OUTCOME_TONES: dict[str, dict[str, str]] = {
    "improved":     {"tone": "success", "glyph": "▲", "label": "Improved"},      # ▲
    "worse":        {"tone": "danger",  "glyph": "▼", "label": "Worse"},         # ▼
    "unchanged":    {"tone": "neutral", "glyph": "–", "label": "Unchanged"},     # –
    "inconclusive": {"tone": "warn",    "glyph": "?",       "label": "Inconclusive"},
}

# Live telemetry data-freshness.
FRESHNESS_TONES: dict[str, dict[str, str]] = {
    "live":   {"tone": "success", "label": "LIVE"},
    "recent": {"tone": "info",    "label": "RECENT"},
    "stale":  {"tone": "warn",    "label": "STALE"},
    "none":   {"tone": "neutral", "label": "NO SIGNAL"},
}

# Live track-map position trust tiers — each MUST look distinct so a low-confidence
# fallback can never be mistaken for a high-confidence reference-path match.
MATCH_TRUST: dict[str, dict[str, str]] = {
    "approved": {"tone": "success", "label": "Reference path"},
    "fallback": {"tone": "warn",    "label": "Road-distance estimate"},
    "low":      {"tone": "neutral", "label": "Low confidence"},
    "none":     {"tone": "neutral", "label": "Position unavailable"},
}


def stage_state(key: str) -> dict[str, str]:
    """Resolve a stage-state descriptor, defaulting to 'available'. Never raises."""
    return STAGE_STATES.get(key, STAGE_STATES[STAGE_AVAILABLE])


def confidence_level(key: str) -> dict:
    """Resolve a confidence descriptor, defaulting to 'unknown'. Never raises."""
    return CONFIDENCE_LEVELS.get((key or "").lower(), CONFIDENCE_LEVELS["unknown"])


def outcome_tone(key: str) -> dict[str, str]:
    """Resolve an outcome descriptor, defaulting to 'unchanged'. Never raises."""
    return OUTCOME_TONES.get((key or "").lower(), OUTCOME_TONES["unchanged"])


def freshness_tone(key: str) -> dict[str, str]:
    """Resolve a freshness descriptor, defaulting to 'none'. Never raises."""
    return FRESHNESS_TONES.get((key or "").lower(), FRESHNESS_TONES["none"])


def match_trust(key: str) -> dict[str, str]:
    """Resolve a map-match trust descriptor, defaulting to 'none'. Never raises."""
    return MATCH_TRUST.get((key or "").lower(), MATCH_TRUST["none"])


# ---------------------------------------------------------------------------
# Pure QSS builders (no Qt import — unit-testable)
# ---------------------------------------------------------------------------

def focus_ring_qss(color: str = NGR_GREEN, width: int = 2) -> str:
    """QSS fragment for a visible keyboard-focus ring (never removed without a
    replacement — accessibility rule focus-states). Intended for a ``:focus``
    selector, e.g. ``f"QPushButton:focus {{ {focus_ring_qss()} }}"``."""
    return f"outline: none; border: {width}px solid {color};"

def badge_qss(tone: str = "neutral") -> str:
    """Return QSS for a small status pill in the given semantic *tone*."""
    fill, text, border = STATUS_TONES.get(tone, STATUS_TONES["neutral"])
    return (
        f"QLabel {{ background: {fill}; color: {text}; "
        f"border: 1px solid {border}; border-radius: {RADIUS_SM}px; "
        f"padding: 2px 8px; font-weight: 600; font-size: {FS_CAPTION}pt; }}"
    )


def banner_qss(tone: str = "info") -> str:
    """Return QSS for a full-width banner (left accent edge) in a *tone*."""
    fill, text, border = STATUS_TONES.get(tone, STATUS_TONES["info"])
    return (
        f"QLabel {{ background: {fill}; color: {text}; "
        f"border-left: 4px solid {border}; border-radius: {RADIUS_MD}px; "
        f"padding: {SPACE_MD}px {SPACE_LG}px; font-size: {FS_LABEL}pt; }}"
    )


def card_qss() -> str:
    """Standard raised carbon card."""
    return (
        f"background: {CARBON_RAISED}; border: 1px solid {HAIRLINE}; "
        f"border-radius: {RADIUS_MD}px;"
    )


def advisory_card_qss() -> str:
    """Read-only advisory panel — cool tint + teal edge, visibly *not* an action."""
    return (
        f"background: {ADVISORY_TINT}; border: 1px solid {ADVISORY_EDGE}; "
        f"border-left: 4px solid {ADVISORY_EDGE}; border-radius: {RADIUS_MD}px;"
    )


def heading_qss(level: int = 2) -> str:
    """QSS for an uppercase NGR section heading. level 1 = tab title, 2 = section."""
    size = {1: FS_H1, 2: FS_H2, 3: FS_H3}.get(level, FS_H2)
    ls = "1.5px" if level <= 2 else "1px"
    return (
        f"QLabel {{ color: {TEXT_HI}; font-size: {size}pt; font-weight: 700; "
        f"letter-spacing: {ls}; }}"
    )


def primary_button_qss() -> str:
    """Neon-green primary action button (the single primary CTA per screen)."""
    return (
        f"QPushButton {{ background: {NGR_GREEN}; color: {NGR_GREEN_INK}; "
        f"border: none; border-radius: {RADIUS_SM}px; padding: 6px 18px; "
        f"font-weight: 700; min-height: {TOUCH_MIN_H}px; }}"
        f"QPushButton:hover {{ background: {NGR_GREEN_HI}; }}"
        f"QPushButton:pressed {{ background: {NGR_GREEN_DIM}; }}"
        f"QPushButton:disabled {{ background: {HAIRLINE}; color: {TEXT_MUTE}; }}"
    )


def secondary_button_qss() -> str:
    """Subordinate outline button — visually quieter than the primary CTA."""
    return (
        f"QPushButton {{ background: {CARBON_HI}; color: {TEXT}; "
        f"border: 1px solid {HAIRLINE}; border-radius: {RADIUS_SM}px; "
        f"padding: 6px 16px; min-height: {TOUCH_MIN_H}px; }}"
        f"QPushButton:hover {{ background: #30353B; border-color: {NGR_GREEN_DIM}; }}"
        f"QPushButton:pressed {{ background: #24282D; }}"
        f"QPushButton:disabled {{ color: {TEXT_MUTE}; border-color: {HAIRLINE_SOFT}; }}"
    )


def app_stylesheet() -> str:
    """The global, additive application stylesheet.

    Styles only *specific* widget classes that otherwise render as generic
    default Fusion chrome (top tab bar, buttons, inputs, tables, scrollbars,
    tooltips, status bar, group boxes). It never sets a blanket ``QWidget {}``
    rule, so custom-painted widgets and the app's ~350 inline stylesheets are
    untouched — this only lifts the parts nothing else styles.
    """
    return f"""
    /* ---- Top navigation: the primary NGR pit-wall tab bar ---- */
    QTabWidget::pane {{
        border: 1px solid {HAIRLINE};
        border-radius: {RADIUS_MD}px;
        top: -1px;
        background: {CARBON};
    }}
    QTabBar {{ qproperty-drawBase: 0; }}
    QTabBar::tab {{
        background: {CARBON_RAISED};
        color: {TEXT_DIM};
        padding: 8px 16px;
        margin-right: 2px;
        min-height: 22px;
        border: 1px solid {HAIRLINE_SOFT};
        border-bottom: none;
        border-top-left-radius: {RADIUS_SM}px;
        border-top-right-radius: {RADIUS_SM}px;
        font-weight: 600;
        letter-spacing: 0.5px;
    }}
    QTabBar::tab:hover {{ color: {TEXT_HI}; background: {CARBON_HI}; }}
    QTabBar::tab:selected {{
        background: {CARBON};
        color: {TEXT_HI};
        border-color: {HAIRLINE};
        border-top: 2px solid {NGR_GREEN};
        padding-top: 7px;
    }}

    /* ---- Buttons: quiet carbon default with a neon-green hover cue ---- */
    QPushButton {{
        background: {CARBON_HI};
        color: {TEXT};
        border: 1px solid {HAIRLINE};
        border-radius: {RADIUS_SM}px;
        padding: 5px 14px;
        min-height: 28px;
    }}
    QPushButton:hover {{ border-color: {NGR_GREEN_DIM}; background: #30353B; }}
    QPushButton:pressed {{ background: #22262B; }}
    QPushButton:disabled {{ color: {TEXT_MUTE}; background: {CARBON_RAISED}; border-color: {HAIRLINE_SOFT}; }}
    /* Keyboard focus must be unmistakable when tabbing (a11y focus-states) — a
       full 2px neon ring, matching the primary/secondary CTA and nav-rail rings. */
    QPushButton:focus {{ outline: none; border: 2px solid {NGR_GREEN}; }}

    /* ---- Inputs ---- */
    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {CARBON_HI};
        color: {TEXT};
        border: 1px solid {HAIRLINE};
        border-radius: {RADIUS_SM}px;
        padding: 4px 8px;
        selection-background-color: {NGR_GREEN_DIM};
        selection-color: {TEXT_HI};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1px solid {NGR_GREEN};
    }}
    QComboBox QAbstractItemView {{
        background: {CARBON_RAISED};
        color: {TEXT};
        border: 1px solid {HAIRLINE};
        selection-background-color: {NGR_GREEN_DIM};
        selection-color: {TEXT_HI};
    }}

    /* ---- Group boxes: titled carbon cards ---- */
    QGroupBox {{
        color: {TEXT_DIM};
        border: 1px solid {HAIRLINE};
        border-radius: {RADIUS_MD}px;
        margin-top: 14px;
        padding-top: 8px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px;
        padding: 0 6px;
        color: {TEXT_HI};
        letter-spacing: 0.5px;
    }}

    /* ---- Tables ---- */
    QHeaderView::section {{
        background: {INK_BLACK};
        color: {TEXT_DIM};
        padding: 6px 8px;
        border: none;
        border-right: 1px solid {HAIRLINE_SOFT};
        border-bottom: 1px solid {HAIRLINE};
        font-weight: 600;
        letter-spacing: 0.5px;
    }}
    QTableWidget, QTableView, QTreeView, QListView {{
        background: {CARBON_RAISED};
        alternate-background-color: {CARBON};
        gridline-color: {HAIRLINE_SOFT};
        border: 1px solid {HAIRLINE};
        border-radius: {RADIUS_SM}px;
        selection-background-color: {NGR_GREEN_DIM};
        selection-color: {TEXT_HI};
    }}

    /* ---- Scrollbars: slim carbon ---- */
    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {HAIRLINE}; border-radius: 6px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {NGR_GREEN_DIM}; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0; }}
    QScrollBar::handle:horizontal {{ background: {HAIRLINE}; border-radius: 6px; min-width: 30px; }}
    QScrollBar::handle:horizontal:hover {{ background: {NGR_GREEN_DIM}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* ---- Tooltips, status bar, checks ---- */
    QToolTip {{
        background: {INK_BLACK};
        color: {TEXT_HI};
        border: 1px solid {NGR_GREEN_DIM};
        border-radius: {RADIUS_SM}px;
        padding: 4px 8px;
    }}
    QStatusBar {{ background: {INK_BLACK}; color: {TEXT_DIM}; }}
    QCheckBox, QRadioButton {{ color: {TEXT}; spacing: 6px; }}
    QProgressBar {{
        background: {CARBON_HI};
        border: 1px solid {HAIRLINE};
        border-radius: {RADIUS_SM}px;
        text-align: center;
        color: {TEXT_HI};
    }}
    QProgressBar::chunk {{ background: {NGR_GREEN_DIM}; border-radius: 3px; }}
    """


# ---------------------------------------------------------------------------
# Logo asset — official NGR logo slot
# ---------------------------------------------------------------------------
# The official supplied logo lives at the repo root (``logo.png``). We only ever
# READ it and scale a copy for display — the file itself is never modified,
# recoloured, or regenerated. If it is ever missing, callers fall back to a clean
# labelled text slot (logo_placeholder_text) rather than inventing a mark.

def logo_path() -> Path:
    """Absolute path to the official NGR logo asset (repo-root ``logo.png``)."""
    # ngr_theme.py lives in <root>/ui/, so the asset is one directory up.
    return Path(__file__).resolve().parent.parent / "logo.png"


def logo_exists() -> bool:
    return logo_path().is_file()


def logo_placeholder_text() -> str:
    """Text shown in the logo slot when the official asset is unavailable."""
    return "NEXT GEAR RACING"


def logo_pixmap(height: int = 40):
    """Return the official NGR logo scaled to *height* px (aspect preserved).

    Returns ``None`` when the asset is missing or PyQt6/QPixmap is unavailable
    (e.g. no display) so callers can fall back to the text slot. Reads the file
    read-only; never writes.
    """
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtGui import QPixmap
    except Exception:
        return None
    p = logo_path()
    if not p.is_file():
        return None
    pix = QPixmap(str(p))
    if pix.isNull():
        return None
    return pix.scaledToHeight(
        int(height),
        Qt.TransformationMode.SmoothTransformation,
    )


# ---------------------------------------------------------------------------
# Qt widget helpers (PyQt6 imported lazily)
# ---------------------------------------------------------------------------

def heading_label(text: str, level: int = 2, uppercase: bool = True):
    """A uppercase NGR section heading QLabel."""
    from PyQt6.QtWidgets import QLabel
    lbl = QLabel(text.upper() if uppercase else text)
    lbl.setStyleSheet(heading_qss(level))
    return lbl


def status_badge(text: str, tone: str = "neutral"):
    """A small status pill. Meaning is carried by the *text*, tone is secondary."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel
    lbl = QLabel(text)
    lbl.setStyleSheet(badge_qss(tone))
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl


def advisory_banner(text: str, tone: str = "advisory"):
    """A read-only advisory banner — cool-tinted so it never looks actionable."""
    from PyQt6.QtWidgets import QLabel
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(banner_qss(tone))
    return lbl


def empty_state_label(text: str):
    """A helpful empty-state message telling the user exactly what to do next."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setStyleSheet(
        f"QLabel {{ color: {TEXT_DIM}; font-size: {FS_LABEL}pt; "
        f"padding: {SPACE_XL}px; border: 1px dashed {HAIRLINE}; "
        f"border-radius: {RADIUS_MD}px; background: {CARBON}; }}"
    )
    return lbl
