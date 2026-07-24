"""LivePitWall — the audio-first, low-distraction live race surface (F6).

Glanceable for PSVR2 use: a few large KPI tiles (lap / position / stint / fuel /
tyre / pit window / gap-to-plan), the current engineer instruction prominent, the
next decision point, and — always visible — data freshness and confidence plus the
map-match trust tier (a low-confidence fallback must never look like a high-confidence
match). No dense tables. Everything is advisory: the driver stays in control and no
pit/fuel/strategy command is issued from here. Pure presentation over the canonical
live race state; it renders and never commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QFrame

from ui import ngr_theme as _t
from ui.components.cards import Card
from ui.components.status import StatusPill, ConfidenceMeter


@dataclass(frozen=True)
class LivePitWallVM:
    lap: str = "—"
    position: str = "—"
    stint: str = "—"
    fuel: str = "—"
    tyre: str = "—"
    pit_window: str = "—"
    gap_to_plan: str = "—"
    engineer_instruction: str = ""
    next_decision: str = ""
    warning: str = ""
    freshness: str = "none"        # live|recent|stale|none
    confidence: str = "unknown"
    map_trust: str = "none"        # approved|fallback|low|none
    ptt_status: str = "RADIO READY"


class LivePitWall(QWidget):
    read_aloud_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ngrLivePitWall")
        self.setStyleSheet(f"#ngrLivePitWall {{ background: {_t.INK_BLACK}; }}")
        self._vm = LivePitWallVM()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(_t.SPACE_XL, _t.SPACE_LG, _t.SPACE_XL, _t.SPACE_LG)
        lay.setSpacing(_t.SPACE_MD)

        # Status strip: freshness · confidence · map trust · advisory · radio
        strip = QHBoxLayout()
        self._fresh = StatusPill("NO SIGNAL", tone="neutral", glyph="○")
        self._confidence = ConfidenceMeter("unknown")
        self._map_trust = StatusPill("Position unavailable", tone="neutral")
        self._radio = StatusPill("RADIO READY", tone="info")
        strip.addWidget(self._fresh)
        strip.addWidget(self._map_trust)
        strip.addStretch(1)
        strip.addWidget(self._confidence)
        strip.addWidget(self._radio)
        strip.addWidget(StatusPill("ADVISORY · driver in control", tone="advisory", glyph="●"))
        lay.addLayout(strip)

        # KPI tiles
        grid = QGridLayout()
        grid.setHorizontalSpacing(_t.SPACE_MD)
        grid.setVerticalSpacing(_t.SPACE_MD)
        self._tiles: dict[str, QLabel] = {}
        specs = [("Lap", "lap"), ("Position", "position"), ("Stint", "stint"),
                 ("Fuel", "fuel"), ("Tyre", "tyre"), ("Pit window", "pit_window"),
                 ("Gap to plan", "gap_to_plan")]
        for i, (cap, key) in enumerate(specs):
            tile, value = _tile(cap)
            self._tiles[key] = value
            grid.addWidget(tile, i // 4, i % 4)
        lay.addLayout(grid)

        # Engineer instruction (prominent)
        self._instr_card = Card()
        self._instr_card.setStyleSheet(
            f"#ngrCard {{ background: {_t.CARBON_RAISED}; "
            f"border: 1px solid {_t.HAIRLINE}; border-left: 4px solid {_t.NGR_GREEN}; "
            f"border-radius: {_t.RADIUS_MD}px; }}")
        head = QHBoxLayout()
        t = QLabel("ENGINEER")
        t.setStyleSheet(f"color: {_t.NGR_GREEN}; font-weight: 700; font-size: {_t.FS_CAPTION}pt;")
        head.addWidget(t)
        head.addStretch(1)
        self._read = QLabel("🔊")
        head.addWidget(self._read)
        self._instr_card.body.addLayout(head)
        self._instruction = QLabel("")
        self._instruction.setWordWrap(True)
        self._instruction.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-size: {_t.FS_H1}pt; font-weight: 600;")
        self._instr_card.add(self._instruction)
        self._next = QLabel("")
        self._next.setWordWrap(True)
        self._next.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_LABEL}pt;")
        self._instr_card.add(self._next)
        lay.addWidget(self._instr_card)

        self._warning = QLabel("")
        self._warning.setWordWrap(True)
        self._warning.setStyleSheet(
            f"color: {_t.DANGER}; font-size: {_t.FS_LABEL}pt; font-weight: 700;")
        self._warning.setVisible(False)
        lay.addWidget(self._warning)

        # The APPROVED PLAN — the pit wall showed live telemetry but nothing about the
        # plan the driver approved, so it looked empty. This is what they are racing to.
        self._plan_card = Card()
        self._plan_card.add(_caption("YOUR RACE PLAN"))
        self._plan_head = QLabel("")
        self._plan_head.setWordWrap(True)
        self._plan_head.setStyleSheet(
            f"color: {_t.TEXT_HI}; font-size: {_t.FS_H3}pt; font-weight: 700;")
        self._plan_card.add(self._plan_head)
        self._plan_stops = QLabel("")
        self._plan_stops.setWordWrap(True)
        self._plan_stops.setStyleSheet(f"color: {_t.TEXT_DIM}; font-size: {_t.FS_CAPTION}pt;")
        self._plan_card.add(self._plan_stops)
        self._plan_card.setVisible(False)
        lay.addWidget(self._plan_card)
        lay.addStretch(1)

        self.set_state(LivePitWallVM())

    def show_plan(self, plan: dict) -> None:
        """Show the approved race plan the driver is racing to (empty dict hides it)."""
        plan = plan if isinstance(plan, dict) else {}
        name = str(plan.get("name") or "")
        if not name:
            self._plan_card.setVisible(False)
            return
        bits = [name]
        if plan.get("expected_laps"):
            bits.append(str(plan["expected_laps"]))
        if plan.get("total_time"):
            bits.append(str(plan["total_time"]))
        if plan.get("pit_windows"):
            bits.append(str(plan["pit_windows"]))
        self._plan_head.setText("  ·  ".join(bits))
        stops = tuple(plan.get("pit_stops") or ())
        self._plan_stops.setText("•  " + "\n•  ".join(str(s) for s in stops) if stops
                                 else "No stops planned.")
        self._plan_card.setVisible(True)

    def set_state(self, vm: LivePitWallVM) -> None:
        """Update the live surface. Cheap enough to call per telemetry frame."""
        if not isinstance(vm, LivePitWallVM):
            vm = LivePitWallVM()
        self._vm = vm

        for key, label in self._tiles.items():
            label.setText(str(getattr(vm, key, "—")) or "—")

        fd = _t.freshness_tone(vm.freshness)
        self._fresh.set_status(fd["label"], tone=fd["tone"],
                               glyph="●" if vm.freshness in ("live", "recent") else "○")
        self._confidence.set_level(vm.confidence)
        mt = _t.match_trust(vm.map_trust)
        self._map_trust.set_status(mt["label"], tone=mt["tone"])
        self._radio.set_status(vm.ptt_status or "RADIO READY", tone="info")

        self._instruction.setText(vm.engineer_instruction or "—")
        self._next.setText(f"Next decision:  {vm.next_decision}" if vm.next_decision else "")
        self._next.setVisible(bool(vm.next_decision))

        if vm.warning:
            self._warning.setText("⚠ " + vm.warning)
            self._warning.setVisible(True)
        else:
            self._warning.setVisible(False)


def _caption(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {_t.NGR_GREEN}; font-weight: 700; font-size: {_t.FS_CAPTION}pt;")
    return lbl


def _tile(caption: str):
    box = QFrame()
    box.setObjectName("ngrKpiTile")
    box.setStyleSheet(
        f"#ngrKpiTile {{ background: {_t.CARBON_RAISED}; border: 1px solid {_t.HAIRLINE}; "
        f"border-radius: {_t.RADIUS_MD}px; }}")
    v = QVBoxLayout(box)
    v.setContentsMargins(_t.SPACE_MD, _t.SPACE_SM, _t.SPACE_MD, _t.SPACE_SM)
    v.setSpacing(0)
    cap = QLabel(caption)
    cap.setStyleSheet(f"color: {_t.TEXT_MUTE}; font-size: {_t.FS_CAPTION}pt;")
    value = QLabel("—")
    value.setStyleSheet(f"color: {_t.TEXT_HI}; font-size: {_t.FS_DISPLAY}pt; font-weight: 700;")
    v.addWidget(cap)
    v.addWidget(value)
    return box, value
