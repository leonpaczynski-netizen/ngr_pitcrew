"""Reusable NGR Pit Crew UI components (UI rebuild, F0.5).

Thin PyQt widgets built over the design-system tokens/QSS in ``ui.ngr_theme`` and
pure view-models. They contain no engineering logic — they render state the shell
passes in. Import the public widgets from here:

    from ui.components import StatusPill, ConfidenceMeter, PrimaryActionButton, Card
"""

from ui.components.status import StatusPill, ConfidenceMeter, TONE_BASE_COLOR
from ui.components.buttons import PrimaryActionButton, SecondaryActionButton
from ui.components.cards import Card, SectionHeading
from ui.components.guidance_vm import EngineerGuidanceVM
from ui.components.guidance_card import EngineerGuidanceCard
from ui.components.progress_rail import ProgressRail, STAGE_LABELS
from ui.components.nav_rail import NavRail, NAV_LABELS
from ui.components.event_header import EventHeaderBar

__all__ = [
    "StatusPill", "ConfidenceMeter", "TONE_BASE_COLOR",
    "PrimaryActionButton", "SecondaryActionButton",
    "Card", "SectionHeading",
    "EngineerGuidanceVM", "EngineerGuidanceCard",
    "ProgressRail", "STAGE_LABELS",
    "NavRail", "NAV_LABELS",
    "EventHeaderBar",
]
