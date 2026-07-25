"""Adaptive Per-Gear Shift Strategy — inputs dataclass and fingerprint (Phase 1).

Collects every value the strategy engine needs from the SetupSheet and the
car-specs dict, resolves optional engine data from the caller-supplied
manual_engine_data dict, and produces a stable, timestamp-free fingerprint.

Pure: no Qt, no DB, no network, no I/O.  Never raises.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional, Tuple

from strategy.shift_strategy_constants import SHIFT_STRATEGY_VERSION


def _pos_int(v) -> Optional[int]:
    """Parse a positive integer or return None."""
    try:
        n = int(round(float(v)))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _pos_float(v) -> Optional[float]:
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _norm_str(v) -> str:
    return "" if v is None else str(v).strip()


@dataclass(frozen=True)
class ShiftStrategyInputs:
    """All inputs the shift-strategy engine requires, as a typed value object.

    Construct with :func:`resolve_shift_inputs`; identify with
    :func:`compute_shift_fingerprint`.
    """

    car_id: str
    gear_ratios: Tuple[float, ...]      # ordered gear ratios, e.g. (3.5, 2.5, …)
    final_drive: float                  # final-drive ratio
    ecu_output: float                   # ECU output % (power scalar)
    power_restrictor: float             # power restrictor % (power scalar)
    ballast_kg: float                   # added ballast in kg
    weight_kg: float                    # base car weight in kg
    aspiration: str                     # 'NA', 'TC', 'SC', 'EV'

    # Optional engine data — supplied manually by the driver; absent until entered.
    peak_power_rpm: Optional[int]       # RPM at which engine peak power occurs
    peak_torque_rpm: Optional[int]      # RPM at which engine peak torque occurs
    redline: Optional[int]              # RPM limiter / redline

    active_setup_revision: int          # revision counter from ActiveSetupAuthority


def resolve_shift_inputs(
    sheet,
    car_specs: dict,
    active_revision: int,
    manual_engine_data: Optional[dict] = None,
) -> ShiftStrategyInputs:
    """Build inputs from a SetupSheet, car-specs dict, and optional engine data.

    ``sheet``       — a :class:`strategy.setup_sheet.SetupSheet`
    ``car_specs``   — dict from :func:`strategy.setup_engineering.resolve_car_specs`
    ``active_revision`` — integer revision from the applied-setup authority
    ``manual_engine_data`` — optional dict with keys peak_power_rpm /
                             peak_torque_rpm / redline, supplied by the driver
                             through the Garage UI.

    Never raises; absent / invalid values become safe defaults or None.
    """
    try:
        specs = car_specs if isinstance(car_specs, dict) else {}
        med = manual_engine_data if isinstance(manual_engine_data, dict) else {}

        # SetupSheet fields
        ratios: Tuple[float, ...] = tuple(sheet.gear_ratios) if hasattr(sheet, "gear_ratios") else ()
        final_drive = _pos_float(sheet.get("final_drive")) or 0.0
        ecu_output = float(sheet.get("ecu_ingame_output") or 100.0)
        power_restrictor = float(sheet.get("power_restrictor") or 100.0)
        ballast_kg = float(sheet.get("ballast_kg") or 0.0)

        # Car-specs fields
        car_id = _norm_str(getattr(sheet, "values", {}).get("car") or specs.get("car") or "")
        weight_kg = float(specs.get("weight_kg") or 0.0)
        aspiration = _norm_str(specs.get("aspiration") or "NA") or "NA"

        # Manual engine data
        peak_power_rpm = _pos_int(med.get("peak_power_rpm"))
        peak_torque_rpm = _pos_int(med.get("peak_torque_rpm"))
        redline = _pos_int(med.get("redline"))

        revision = int(active_revision or 0)

        return ShiftStrategyInputs(
            car_id=car_id,
            gear_ratios=ratios,
            final_drive=final_drive,
            ecu_output=ecu_output,
            power_restrictor=power_restrictor,
            ballast_kg=ballast_kg,
            weight_kg=weight_kg,
            aspiration=aspiration,
            peak_power_rpm=peak_power_rpm,
            peak_torque_rpm=peak_torque_rpm,
            redline=redline,
            active_setup_revision=revision,
        )
    except Exception:
        return ShiftStrategyInputs(
            car_id="",
            gear_ratios=(),
            final_drive=0.0,
            ecu_output=100.0,
            power_restrictor=100.0,
            ballast_kg=0.0,
            weight_kg=0.0,
            aspiration="NA",
            peak_power_rpm=None,
            peak_torque_rpm=None,
            redline=None,
            active_setup_revision=0,
        )


def compute_shift_fingerprint(inputs: ShiftStrategyInputs) -> str:
    """Deterministic sha256[:10] fingerprint over identity fields.

    TIMESTAMP-FREE — a timestamp would make two identical runs produce
    different fingerprints, which would trigger spurious "stale" warnings.

    Field list mirrors the brief exactly:
      SHIFT_STRATEGY_VERSION, car_id, gear_ratios, final_drive, ecu_output,
      power_restrictor, aspiration, ballast_kg, weight_kg, active_setup_revision.

    final_drive is included because gear selection (optimal RPM per pair)
    depends on the ratio chain; ecu_output and power_restrictor scale
    delivered power; ballast and weight affect traction and therefore the
    optimal trade-off between fuel saving and time cost.

    Never raises (FIX C): wraps its body in try/except; the happy-path hash
    is identical to before so golden vectors are unchanged.
    """
    try:
        parts = [
            SHIFT_STRATEGY_VERSION,
            _norm_str(inputs.car_id),
            "|".join(f"{r:.3f}" for r in inputs.gear_ratios),
            f"{inputs.final_drive:.3f}",
            f"{inputs.ecu_output:.1f}",
            f"{inputs.power_restrictor:.1f}",
            _norm_str(inputs.aspiration),
            f"{inputs.ballast_kg:.1f}",
            f"{inputs.weight_kg:.1f}",
            str(inputs.active_setup_revision),
        ]
        raw = "\n".join(parts)
        return hashlib.sha256(raw.encode()).hexdigest()[:10]
    except Exception:
        # Deterministic fallback: hash the version + car_id so the return
        # value is still a 10-char hex string and never empty.
        try:
            fallback = f"{SHIFT_STRATEGY_VERSION}:{_norm_str(inputs.car_id)}"
            return hashlib.sha256(fallback.encode()).hexdigest()[:10]
        except Exception:
            return "0000000000"


def inputs_snapshot(inputs: ShiftStrategyInputs) -> dict:
    """JSON-safe dict of the identity fields used in the fingerprint.

    Stored alongside the fingerprint so that on next load the VM can name
    which specific field changed rather than showing a generic stale message.
    Pure, never raises.
    """
    try:
        return {
            "car_id": _norm_str(inputs.car_id),
            "gear_ratios": list(inputs.gear_ratios),
            "final_drive": float(inputs.final_drive),
            "ecu_output": float(inputs.ecu_output),
            "power_restrictor": float(inputs.power_restrictor),
            "aspiration": _norm_str(inputs.aspiration),
            "ballast_kg": float(inputs.ballast_kg),
            "weight_kg": float(inputs.weight_kg),
            "active_setup_revision": int(inputs.active_setup_revision),
        }
    except Exception:
        return {}


def describe_fingerprint_change(
    current: ShiftStrategyInputs,
    stored_snapshot: dict,
) -> str:
    """Compare current inputs against a prior snapshot and name what changed.

    Returns a concise human-readable string such as
      "Final drive changed (4.100 -> 3.900)"
      "Gear 3 ratio changed (1.900 -> 2.000); ECU output changed (100 -> 98)"
      "Gear 1 ratio changed (3.500 -> 3.600); ...and 2 more"

    Returns "" when nothing differs, when the snapshot is missing/garbage, or
    on any error.  Pure, never raises.
    """
    try:
        if not stored_snapshot or not isinstance(stored_snapshot, dict):
            return ""

        changes: list = []

        # --- Gear ratios (per-gear) ---
        cur_ratios = list(current.gear_ratios)
        snap_ratios = list(stored_snapshot.get("gear_ratios") or [])
        try:
            snap_ratios = [float(r) for r in snap_ratios]
        except (TypeError, ValueError):
            snap_ratios = []
        max_len = max(len(cur_ratios), len(snap_ratios))
        for i in range(max_len):
            cur_r = cur_ratios[i] if i < len(cur_ratios) else None
            snap_r = snap_ratios[i] if i < len(snap_ratios) else None
            if cur_r is None and snap_r is not None:
                changes.append(f"Gear {i + 1} ratio removed")
            elif cur_r is not None and snap_r is None:
                changes.append(f"Gear {i + 1} ratio added ({cur_r:.3f})")
            elif cur_r is not None and snap_r is not None:
                if abs(cur_r - snap_r) > 1e-6:
                    changes.append(
                        f"Gear {i + 1} ratio changed ({snap_r:.3f} -> {cur_r:.3f})")

        # --- Scalar float fields ---
        def _chk_float(attr: str, label: str, fmt: str = "{:.3f}") -> None:
            try:
                cur_v = float(getattr(current, attr, 0) or 0)
                snap_v = float(stored_snapshot.get(attr) or 0)
                if abs(cur_v - snap_v) > 1e-6:
                    changes.append(
                        f"{label} changed ({fmt.format(snap_v)} -> {fmt.format(cur_v)})")
            except (TypeError, ValueError):
                pass

        _chk_float("final_drive",     "Final drive",       "{:.3f}")
        _chk_float("ecu_output",      "ECU output",        "{:.0f}")
        _chk_float("power_restrictor","Power restrictor",  "{:.0f}")
        _chk_float("ballast_kg",      "Ballast",           "{:.0f} kg")
        _chk_float("weight_kg",       "Weight",            "{:.0f} kg")

        # --- Aspiration ---
        cur_asp  = _norm_str(getattr(current, "aspiration", ""))
        snap_asp = _norm_str(stored_snapshot.get("aspiration") or "")
        if cur_asp != snap_asp:
            changes.append(f"Aspiration changed ({snap_asp} -> {cur_asp})")

        # --- Revision ---
        try:
            cur_rev  = int(getattr(current, "active_setup_revision", 0) or 0)
            snap_rev = int(stored_snapshot.get("active_setup_revision") or 0)
            if cur_rev != snap_rev:
                changes.append("Setup revision changed")
        except (TypeError, ValueError):
            pass

        if not changes:
            return ""
        if len(changes) <= 2:
            return "; ".join(changes)
        return f"{changes[0]}; {changes[1]}; ...and {len(changes) - 2} more"
    except Exception:
        return ""
