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
from ui.components.setup_workspace import SetupWorkspace, SetupDisciplineSelector
from ui.components.gt7_settings_sheet import GT7SettingsSheet
from ui.components.setup_lineage import SetupLineageTree, LineageNode
from ui.components.setup_comparison import SetupComparison, build_comparison_rows
from ui.components.run_card import RunCard, RunCardVM
from ui.components.practice_feedback import StructuredFeedbackForm
from ui.components.practice_outcome import PracticeOutcome, PracticeOutcomeVM
from ui.components.qualifying_readiness import (
    QualifyingReadiness, QualifyingReadinessVM, ReadinessItem,
)
from ui.components.strategy_plan import (
    StrategyPlanView, StrategyPlanVM, StrategyOption, StrategyInput,
)
from ui.components.live_pit_wall import LivePitWall, LivePitWallVM

__all__ = [
    "StatusPill", "ConfidenceMeter", "TONE_BASE_COLOR",
    "PrimaryActionButton", "SecondaryActionButton",
    "Card", "SectionHeading",
    "EngineerGuidanceVM", "EngineerGuidanceCard",
    "ProgressRail", "STAGE_LABELS",
    "NavRail", "NAV_LABELS",
    "EventHeaderBar",
    "SetupWorkspace", "SetupDisciplineSelector",
    "GT7SettingsSheet", "SetupLineageTree", "LineageNode",
    "SetupComparison", "build_comparison_rows",
    "RunCard", "RunCardVM",
    "StructuredFeedbackForm", "PracticeOutcome", "PracticeOutcomeVM",
    "QualifyingReadiness", "QualifyingReadinessVM", "ReadinessItem",
    "StrategyPlanView", "StrategyPlanVM", "StrategyOption", "StrategyInput",
    "LivePitWall", "LivePitWallVM",
]
