"""Standalone INTERACTIVE preview of the new NGR Pit Crew shell.

Opens ONLY the new shell, populated with representative sample data. It starts no
telemetry backend, binds no UDP port, and never writes to your config or database —
so it is completely safe to run at any time, including during a race weekend, and
will not affect the classic dashboard you normally use.

Run it with:

    python preview_new_shell.py

(or double-click run_new_shell_preview.bat). Click the left nav, the progress-rail
stages, and the Pit Crew Engineer card's actions to move around. Close the window
to exit. This is a visual/interaction preview with SAMPLE data — the real event,
setup and live data are wired in through the app itself (flag NGR_NEW_SHELL=1).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication

from ui.pit_crew_shell import PitCrewShell
from ui.pit_crew_controller import PitCrewController
from ui import ngr_theme as theme
from data.event_context import build_event_context


def main() -> int:
    app = QApplication.instance() or QApplication([])

    controller = PitCrewController()
    shell = PitCrewShell(controller)
    shell.setWindowTitle("NGR Pit Crew — NEW SHELL PREVIEW (sample data)")
    shell.resize(1380, 860)

    event = build_event_context(
        event={"id": 5, "name": "NGR GT Cup - Round 5"},
        strategy={"car": "Porsche 911 RSR",
                  "track_location_id": "Watkins Glen", "layout_id": "Long"},
    )
    controller.patch(
        event=event,
        programme_stage="garage",
        active_setup_label="Quali v3",
        active_setup_applied=True,
        connected=True,
        stage_states={
            "briefing": theme.STAGE_COMPLETE,
            "garage": theme.STAGE_CURRENT,
            "practice": theme.STAGE_AVAILABLE,
            "review": theme.STAGE_AVAILABLE,
            "qualifying": theme.STAGE_BLOCKED,
            "strategy": theme.STAGE_BLOCKED,
            "race": theme.STAGE_BLOCKED,
            "debrief": theme.STAGE_NOT_REQUIRED,
        },
    )
    shell.set_guidance_view({
        "ok": True,
        "next_action": {
            "headline": "Lock the qualifying setup",
            "detail": "Convergence is stable across the last 3 practice runs; "
                      "locking frees you to prepare qualifying.",
            "target_surface": "setup", "tone": "info",
        },
        "progress": {"practice_sessions": 3, "valid_laps": 42,
                     "setup_experiments": 2, "setup_confidence": "high"},
        "attention": [{"kind": "risk",
                       "message": "Rear tyres graining after lap 6", "tone": "warn"}],
        "quick_actions": [{"label": "Open Practice", "target_surface": "practice"}],
    })

    shell.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
