"""Product-flow model — single source of truth for the NGR Pit Crew user journey.

Pure Python, **no PyQt6 import** so it is unit-testable without a QApplication
(matching the project's no-Qt test convention).

This module was added by the Product Consolidation Sprint (2026-07-03). It exists
because the app grew patch-on-patch to 13 top-level tabs that mix the core
race-engineer workflow with developer/diagnostic tooling, and there was no single
place that described:

  * the intended end-to-end user journey,
  * which tabs are part of that workflow vs. which are advanced/diagnostic tools,
  * what the user should do *next* given the current app state.

The dashboard reads this module so tab presentation and any future "home / next
action" surface stay consistent, and the audit / tests assert against it.

Nothing here mutates state or touches the UI; callers pass in plain booleans.
"""

from __future__ import annotations

from typing import Dict, List, Optional


# --------------------------------------------------------------------------- #
# Tab roles
# --------------------------------------------------------------------------- #
# WORKFLOW   — a step in the normal race-engineer journey.
# SUPPORT    — always-available help / configuration (not a journey step).
# DIAGNOSTIC — developer / advanced tooling; must not be mixed into the normal
#              workflow presentation.
ROLE_WORKFLOW = "workflow"
ROLE_SUPPORT = "support"
ROLE_DIAGNOSTIC = "diagnostic"

# Canonical tab titles (base, undecorated) mapped to their role.
# NOTE: "Diagnostics" is the consolidated name for the old "Debug" tab.
# NOTE: "Home" is the Race Engineer Command Centre (Home Dashboard sprint).
# Home Dashboard Promotion (2026-07-03) moved it to the FIRST tab (index 0),
# the default landing page; roles here are position-independent.
TAB_ROLES: Dict[str, str] = {
    "Home": ROLE_WORKFLOW,
    "Live Race Engineer": ROLE_WORKFLOW,
    "Event Planner": ROLE_WORKFLOW,
    "Garage": ROLE_WORKFLOW,
    "Setup Builder": ROLE_WORKFLOW,
    "Practice Review": ROLE_WORKFLOW,
    "Strategy Builder": ROLE_WORKFLOW,
    "History": ROLE_WORKFLOW,
    "Guide": ROLE_SUPPORT,
    "Settings": ROLE_SUPPORT,
    "Telemetry": ROLE_DIAGNOSTIC,
    "Diagnostics": ROLE_DIAGNOSTIC,
    "AI Log": ROLE_DIAGNOSTIC,
    "Track Modelling": ROLE_DIAGNOSTIC,
}

# Prefix used to visually flag advanced/diagnostic tool tabs so a user can tell
# at a glance which tabs are tools rather than workflow steps. Kept as a single
# constant so it can be changed in one place.
DIAGNOSTIC_TAB_PREFIX = "⚙ "  # gear ⚙ + space


# --------------------------------------------------------------------------- #
# The intended end-to-end journey
# --------------------------------------------------------------------------- #
# Each step names the primary tab where the work happens. `gate` is the state
# key (see build_flow_state_summary) that, when True, means the step is done.
PRODUCT_JOURNEY: List[Dict[str, str]] = [
    {"step": "1",  "title": "Select or create the event",              "tab": "Event Planner",      "gate": "has_event"},
    {"step": "2",  "title": "Select car, track, layout and race rules","tab": "Event Planner",      "gate": "has_car_track"},
    {"step": "3",  "title": "Confirm tuning legality & allowed changes","tab": "Setup Builder",      "gate": "tuning_confirmed"},
    {"step": "4",  "title": "Capture practice telemetry",              "tab": "Live Race Engineer", "gate": "has_practice_laps"},
    {"step": "5",  "title": "Validate session / lap data quality",     "tab": "Practice Review",    "gate": "has_valid_laps"},
    {"step": "6",  "title": "Identify repeated issues by corner",      "tab": "Practice Review",    "gate": "has_valid_laps"},
    {"step": "7",  "title": "Recommend driver-tailored setup changes", "tab": "Setup Builder",      "gate": "has_setup"},
    {"step": "8",  "title": "Validate setup improvement vs telemetry", "tab": "Practice Review",    "gate": "has_setup"},
    {"step": "9",  "title": "Build qualifying setup (if required)",    "tab": "Setup Builder",      "gate": "has_setup"},
    {"step": "10", "title": "Build race setup (if required)",          "tab": "Setup Builder",      "gate": "has_setup"},
    {"step": "11", "title": "Build race strategy",                     "tab": "Strategy Builder",   "gate": "has_strategy"},
    {"step": "12", "title": "Live pit-crew support during the race",   "tab": "Live Race Engineer", "gate": "live_active"},
    {"step": "13", "title": "Save learning to driver/car/track history","tab": "History",           "gate": "learning_saved"},
]

# The compact ordered gate list the "next action" resolver walks. Each entry is
# (state_key, human action, tab). The first unmet gate is the suggested action.
_NEXT_ACTION_GATES = [
    ("has_event",         "Create or select an event",                       "Event Planner"),
    ("has_car_track",     "Set the car, track and layout for this event",    "Event Planner"),
    ("tuning_confirmed",  "Confirm tuning rules and allowed setup changes",  "Setup Builder"),
    ("has_practice_laps", "Drive practice laps to capture telemetry",        "Live Race Engineer"),
    ("has_valid_laps",    "Review lap data quality and tag compounds",       "Practice Review"),
    ("has_setup",         "Build or refine the car setup",                   "Setup Builder"),
    ("has_strategy",      "Build a race strategy",                           "Strategy Builder"),
    ("live_active",       "Start the race with live pit-crew support",       "Live Race Engineer"),
]


# --------------------------------------------------------------------------- #
# Classification helpers
# --------------------------------------------------------------------------- #
def _base_title(name: str) -> str:
    """Strip the diagnostic prefix so classification is prefix-insensitive."""
    if name.startswith(DIAGNOSTIC_TAB_PREFIX):
        return name[len(DIAGNOSTIC_TAB_PREFIX):]
    return name


def tab_role(name: str) -> str:
    """Return the role for a tab title. Unknown tabs default to WORKFLOW so a
    newly added tab is never silently treated as a diagnostic tool."""
    return TAB_ROLES.get(_base_title(name), ROLE_WORKFLOW)


def is_diagnostic_tab(name: str) -> bool:
    return tab_role(name) == ROLE_DIAGNOSTIC


def workflow_tabs() -> List[str]:
    return [n for n, r in TAB_ROLES.items() if r == ROLE_WORKFLOW]


def diagnostic_tabs() -> List[str]:
    return [n for n, r in TAB_ROLES.items() if r == ROLE_DIAGNOSTIC]


def support_tabs() -> List[str]:
    return [n for n, r in TAB_ROLES.items() if r == ROLE_SUPPORT]


def decorate_tab_title(name: str) -> str:
    """Return the tab title a diagnostic tab should display.

    Diagnostic tabs get the gear prefix so they read as tools, not workflow
    steps. Workflow/support tabs are returned unchanged. Idempotent — calling it
    twice never double-prefixes.
    """
    base = _base_title(name)
    if TAB_ROLES.get(base) == ROLE_DIAGNOSTIC:
        return DIAGNOSTIC_TAB_PREFIX + base
    return base


# --------------------------------------------------------------------------- #
# Flow-state summary — the "where am I / what next" surface
# --------------------------------------------------------------------------- #
def build_flow_state_summary(
    *,
    has_event: bool = False,
    has_car: bool = False,
    has_track: bool = False,
    tuning_confirmed: bool = False,
    has_practice_laps: bool = False,
    has_valid_laps: bool = False,
    has_setup: bool = False,
    has_strategy: bool = False,
    live_active: bool = False,
    learning_saved: bool = False,
) -> Dict[str, object]:
    """Summarise product-flow readiness and the single suggested next action.

    This is the logic the intended (currently missing) Dashboard/home overview
    would render. It is pure so it can be unit-tested and reused. It never
    raises; every input is an independent boolean the caller derives from real
    app state (active event present, car set, tagged laps exist, etc.).

    Returns a dict with:
      ready        list[str] of completed gate labels (human readable)
      pending      list[str] of not-yet-met gate labels
      next_action  str  — the one thing to do next
      next_tab     str  — which tab to do it on
      complete     bool — every gate met (ready to race / racing)
    """
    # `has_car_track` composes the two independent selections into the single
    # gate the journey/next-action tables reference.
    state = {
        "has_event": bool(has_event),
        "has_car_track": bool(has_car and has_track),
        "tuning_confirmed": bool(tuning_confirmed),
        "has_practice_laps": bool(has_practice_laps),
        "has_valid_laps": bool(has_valid_laps),
        "has_setup": bool(has_setup),
        "has_strategy": bool(has_strategy),
        "live_active": bool(live_active),
    }

    ready: List[str] = []
    pending: List[str] = []
    next_action: Optional[str] = None
    next_tab: Optional[str] = None

    for key, action, tab in _NEXT_ACTION_GATES:
        if state.get(key):
            ready.append(action)
        else:
            pending.append(action)
            if next_action is None:
                next_action = action
                next_tab = tab

    complete = next_action is None
    if complete:
        next_action = "Save this session's learning to history"
        next_tab = "History"
        if learning_saved:
            next_action = "All steps complete — nothing outstanding"

    return {
        "ready": ready,
        "pending": pending,
        "next_action": next_action,
        "next_tab": next_tab,
        "complete": complete,
    }
