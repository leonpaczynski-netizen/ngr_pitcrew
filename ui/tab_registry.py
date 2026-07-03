"""Named tab registry — stable keys for the dashboard's top-level tabs.

Added by the **Tab Navigation Refactor — Named Tab Lookup** sprint
(2026-07-03). Pure Python, **no PyQt6 import** (the project's no-Qt test
convention).

Why this exists
---------------
Since the Product Consolidation audit, every sprint has had to work around the
fact that tab navigation was keyed to **raw numeric indices**: dispatch in
``_on_tab_changed`` compared against hard-coded ``0–12``, navigation jumps
called ``setCurrentIndex(<n>)``, and the Home Dashboard had to be *appended*
at index 13 because inserting it anywhere else would silently re-target every
comparison. This module gives each tab a stable key so the dashboard
dispatches and navigates by **key**, and the visual order lives in exactly one
place (:data:`DEFAULT_TAB_ORDER`).

Because of that, the **Home Dashboard Promotion** sprint (2026-07-03) could
move Home to the front (index 0, the default landing tab) as an order-only
edit: lead :data:`DEFAULT_TAB_ORDER` with ``TAB_HOME`` and reorder the matching
``addTab`` block together — no dispatch or navigation code changed.

Keys are registered in creation order, so lookup is by position, never by the
visible label — the ⚙ tool-tab decoration (``product_flow.decorate_tab_title``)
can never break it. :func:`key_for_title` is provided for the reverse mapping
and strips the decoration first.

Changing the visible tab order later (e.g. moving Home to the front) becomes:
reorder the ``addTab`` calls and :data:`DEFAULT_TAB_ORDER` together — no
dispatch or navigation code changes.

Nothing here mutates UI state; the dashboard owns the QTabWidget and simply
mirrors its creation order into a :class:`TabRegistry`.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple


# --------------------------------------------------------------------------- #
# Stable tab keys (never shown to the user; safe to reference from anywhere)
# --------------------------------------------------------------------------- #
TAB_LIVE = "live"
TAB_EVENT_PLANNER = "event_planner"
TAB_GARAGE = "garage"
TAB_SETUP_BUILDER = "setup_builder"
TAB_PRACTICE_REVIEW = "practice_review"
TAB_STRATEGY_BUILDER = "strategy_builder"
TAB_TELEMETRY = "telemetry"
TAB_DIAGNOSTICS = "diagnostics"
TAB_GUIDE = "guide"
TAB_SETTINGS = "settings"
TAB_HISTORY = "history"
TAB_AI_LOG = "ai_log"
TAB_TRACK_MODELLING = "track_modelling"
TAB_HOME = "home"


# The CURRENT visual tab order (must mirror the ``addTab`` calls in
# ``ui/dashboard.py`` ``_setup_ui`` exactly — a source-scan test and a runtime
# count check both guard the pairing). Indices 0–13.
#
# Home Dashboard Promotion (2026-07-03): TAB_HOME now LEADS the order (index 0)
# — it is the default landing tab. The move was order-only: because dispatch and
# navigation resolve through this positional registry, leading with TAB_HOME and
# re-numbering the comments (matched to the reordered ``addTab`` block) is the
# whole change. Every non-Home tab keeps its previous RELATIVE order.
DEFAULT_TAB_ORDER: Tuple[str, ...] = (
    TAB_HOME,              # 0  Home (Race Engineer Command Centre — default landing tab)
    TAB_LIVE,              # 1  Live Race Engineer
    TAB_EVENT_PLANNER,     # 2  Event Planner
    TAB_GARAGE,            # 3  Garage
    TAB_SETUP_BUILDER,     # 4  Setup Builder
    TAB_PRACTICE_REVIEW,   # 5  Practice Review
    TAB_STRATEGY_BUILDER,  # 6  Strategy Builder
    TAB_TELEMETRY,         # 7  Telemetry (⚙ tool)
    TAB_DIAGNOSTICS,       # 8  Diagnostics (⚙ tool)
    TAB_GUIDE,             # 9  Guide
    TAB_SETTINGS,          # 10 Settings
    TAB_HISTORY,           # 11 History
    TAB_AI_LOG,            # 12 AI Log (⚙ tool)
    TAB_TRACK_MODELLING,   # 13 Track Modelling (⚙ tool)
)


# Canonical UNDECORATED titles per key — must match the ``addTab`` title
# arguments and the keys of ``ui.product_flow.TAB_ROLES`` (tested). Lookup
# never depends on these at runtime (registration is positional); they exist
# for the reverse title→key mapping and for cross-checks against product_flow.
TAB_BASE_TITLES: Dict[str, str] = {
    TAB_LIVE: "Live Race Engineer",
    TAB_EVENT_PLANNER: "Event Planner",
    TAB_GARAGE: "Garage",
    TAB_SETUP_BUILDER: "Setup Builder",
    TAB_PRACTICE_REVIEW: "Practice Review",
    TAB_STRATEGY_BUILDER: "Strategy Builder",
    TAB_TELEMETRY: "Telemetry",
    TAB_DIAGNOSTICS: "Diagnostics",
    TAB_GUIDE: "Guide",
    TAB_SETTINGS: "Settings",
    TAB_HISTORY: "History",
    TAB_AI_LOG: "AI Log",
    TAB_TRACK_MODELLING: "Track Modelling",
    TAB_HOME: "Home",
}


def key_for_title(title: str) -> Optional[str]:
    """Reverse lookup: tab key for a (possibly ⚙-decorated) visible title.

    Strips the diagnostic decoration first so a decorated label can never
    break the mapping. Returns None for unknown titles — never raises.
    """
    try:
        from ui.product_flow import DIAGNOSTIC_TAB_PREFIX
        if isinstance(title, str) and title.startswith(DIAGNOSTIC_TAB_PREFIX):
            title = title[len(DIAGNOSTIC_TAB_PREFIX):]
    except Exception:  # pragma: no cover - defensive
        pass
    if not isinstance(title, str):
        return None
    for key, base in TAB_BASE_TITLES.items():
        if base == title:
            return key
    return None


# --------------------------------------------------------------------------- #
# The registry
# --------------------------------------------------------------------------- #
class TabRegistry:
    """Ordered key↔index mapping mirroring the QTabWidget's creation order.

    All lookups are safe: unknown keys resolve to -1, out-of-range indices to
    None — nothing here ever raises on bad input.
    """

    def __init__(self) -> None:
        self._keys: list = []

    # -- registration -------------------------------------------------------- #
    def register(self, key: str) -> int:
        """Register the next tab position under ``key``; returns its index.

        Registering an already-registered key is a safe no-op that returns the
        existing index (it never creates a duplicate entry).
        """
        key = str(key)
        if key in self._keys:
            return self._keys.index(key)
        self._keys.append(key)
        return len(self._keys) - 1

    def register_all(self, keys) -> None:
        """Register several keys in order (convenience for the default order)."""
        for key in keys or ():
            self.register(key)

    # -- lookups (never raise) ------------------------------------------------ #
    def index_of(self, key) -> int:
        """Index for ``key``, or -1 when the key is unknown."""
        try:
            return self._keys.index(key)
        except (ValueError, TypeError):
            return -1

    def key_at(self, index) -> Optional[str]:
        """Key at ``index``, or None when out of range / not an int."""
        try:
            idx = int(index)
        except (TypeError, ValueError):
            return None
        if 0 <= idx < len(self._keys):
            return self._keys[idx]
        return None

    def has(self, key) -> bool:
        return self.index_of(key) >= 0

    @property
    def count(self) -> int:
        return len(self._keys)

    def keys(self) -> Tuple[str, ...]:
        return tuple(self._keys)


def build_default_registry() -> TabRegistry:
    """A registry pre-populated with the current visual tab order."""
    registry = TabRegistry()
    registry.register_all(DEFAULT_TAB_ORDER)
    return registry
