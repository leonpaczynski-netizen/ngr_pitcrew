"""Launch helper for the new NGR Pit Crew shell, behind a flag (F1 integration).

Keeps ``main.py`` tiny and testable: decide whether to use the new shell, build it,
and do a one-shot populate from the existing canonical read models (the same
``_build_*_context`` adapters the old dashboard uses) plus the read-only Event
Command Centre view. Everything is defensive — a failure here must never stop the
app from starting; the caller falls back to the old dashboard.

The new shell runs behind this flag alongside the old dashboard until the F9
cutover. Live per-event/telemetry updates are wired in a later F1 slice; this is
the initial-state preview.
"""

from __future__ import annotations

import os
from typing import Optional


def should_use_new_shell(config: Optional[dict] = None) -> bool:
    """True when the new shell is requested via env NGR_NEW_SHELL or config.ui.new_shell."""
    env = str(os.environ.get("NGR_NEW_SHELL", "")).strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    try:
        return bool((config or {}).get("ui", {}).get("new_shell", False))
    except Exception:
        return False


def _safe_ctx(window, method: str):
    try:
        fn = getattr(window, method, None)
        return fn() if callable(fn) else None
    except Exception:
        return None


def _active_setup(window):
    """Best-effort (label, applied) from the window's setup authority. Never raises."""
    try:
        auth = getattr(window, "_setup_authority", None)
        if auth is None:
            return "", False
        active = auth.active_setup() if hasattr(auth, "active_setup") else None
        if active is None:
            return "", False
        label = getattr(active, "label", "") or getattr(active, "name", "") or ""
        applied = bool(getattr(active, "applied", False))
        return str(label), applied
    except Exception:
        return "", False


def build_initial_app_state(window=None, config=None):
    """Build an AppState from the window's canonical context adapters. Never raises."""
    from ui.app_state import build_app_state
    ev = _safe_ctx(window, "_build_event_context")
    se = _safe_ctx(window, "_build_session_context")
    st = _safe_ctx(window, "_build_strategy_context")
    label, applied = _active_setup(window)
    connected = bool(getattr(se, "connected", False)) if se is not None else False
    return build_app_state(
        event=ev, session=se, strategy=st,
        active_setup_label=label, active_setup_applied=applied,
        connected=connected,
    )


def fetch_guidance_view(db=None, config=None):
    """Fetch the read-only Event Command Centre view dict. None on any failure."""
    if db is None or not hasattr(db, "build_event_command_centre_view"):
        return None
    try:
        cyc = ""
        try:
            cyc = (config or {}).get("active_cycle_id", "") or ""
        except Exception:
            cyc = ""
        return db.build_event_command_centre_view(selected_cycle_id=cyc)
    except Exception:
        return None


def launch_new_shell(window=None, config=None, db=None, controller=None):
    """Build the shell and attach a live bridge that keeps it in sync with the real
    services. Falls back to a one-shot populate if the bridge can't start. Returns the
    shell (never raises)."""
    from ui.pit_crew_controller import PitCrewController
    from ui.pit_crew_shell import PitCrewShell
    controller = controller or PitCrewController()
    shell = PitCrewShell(controller)
    try:
        from ui.live_shell_bridge import LiveShellBridge
        bridge = LiveShellBridge(shell, controller, window=window, config=config, db=db)
        shell._live_bridge = bridge   # keep a reference so it isn't garbage-collected
        bridge.start()
        return shell
    except Exception as exc:
        print(f"[NewShell] live bridge unavailable, one-shot populate: {exc}")
    # Fallback: static one-shot populate.
    try:
        controller.set_state(build_initial_app_state(window, config))
    except Exception:
        pass
    try:
        shell.set_guidance_view(fetch_guidance_view(db, config))
    except Exception:
        pass
    return shell
