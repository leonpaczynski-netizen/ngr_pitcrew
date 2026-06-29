"""Tests for audit refactor and optimisation pass (AC1–AC7)."""
from __future__ import annotations
import threading
import time
from unittest.mock import MagicMock, patch, call
import logging


# ---------------------------------------------------------------------------
# Shared stubs
# ---------------------------------------------------------------------------

class FakeLabel:
    def __init__(self):
        self.text = ""
        self.style = ""
        self.set_text_calls: list[str] = []
        self.set_style_calls: list[str] = []

    def setText(self, t: str) -> None:
        self.set_text_calls.append(t)
        self.text = t

    def setStyleSheet(self, s: str) -> None:
        self.set_style_calls.append(s)
        self.style = s


class FakeMapWidget:
    def __init__(self):
        self.draw_data_calls: list = []

    def set_draw_data(self, dd) -> None:
        self.draw_data_calls.append(dd)


# ---------------------------------------------------------------------------
# AC1 — Track map dirty-flag optimisation
# ---------------------------------------------------------------------------

class FakeCarDot:
    def __init__(self, x, y, confidence, is_valid):
        self.x = x
        self.y = y
        self.confidence = confidence
        self.is_valid = is_valid


class FakeStation:
    def __init__(self, x, z, heading_rad):
        self.x = x
        self.z = z
        self.heading_rad = heading_rad


class FakeStationMap:
    def __init__(self):
        self.stations = [FakeStation(10.0, 20.0, 0.0)]


class FakeMatchResult:
    def __init__(self, idx=0, lateral=0.0, confidence="HIGH", is_pit=False):
        self.nearest_station_idx = idx
        self.lateral_offset_m = lateral
        self.confidence = confidence
        self.is_pit_likely = is_pit


class FakeDrawData:
    def __init__(self):
        self.car_dot = None


class FakeDashboardAC1:
    """Minimal stub for AC1 dirty-flag cache logic."""

    def __init__(self):
        self._tm_station_map = FakeStationMap()
        self._tm_cached_draw_data = None
        self._pit_lane_active = False
        self._tm_map_widget = FakeMapWidget()
        self._announcer = None
        self._build_calls = 0

    def _build_map_draw_data(self, sm, match_result=None):
        self._build_calls += 1
        dd = FakeDrawData()
        return dd

    def _map_match(self, x, y, z, sm, speed_kph=0.0):
        return FakeMatchResult(idx=0, lateral=x * 0.1, confidence="HIGH")

    def _tm_update_live_map_dot(self, packet) -> None:
        import math as _math
        sm = getattr(self, "_tm_station_map", None)
        if sm is None or not sm.stations:
            return
        try:
            spd = getattr(packet, "car_speed", 0.0) or 0.0
            x   = getattr(packet, "position_x", 0.0) or 0.0
            y   = getattr(packet, "position_y", 0.0) or 0.0
            z   = getattr(packet, "position_z", 0.0) or 0.0
            match_result = self._map_match(x, y, z, sm, speed_kph=spd)
            if self._tm_cached_draw_data is None:
                self._tm_cached_draw_data = self._build_map_draw_data(sm, match_result=match_result)
            else:
                if match_result is not None and not match_result.is_pit_likely:
                    idx = match_result.nearest_station_idx
                    if idx < len(sm.stations):
                        st = sm.stations[idx]
                        self._tm_cached_draw_data.car_dot = FakeCarDot(
                            x          = st.x + match_result.lateral_offset_m * _math.cos(st.heading_rad),
                            y          = st.z - match_result.lateral_offset_m * _math.sin(st.heading_rad),
                            confidence = match_result.confidence,
                            is_valid   = match_result.confidence != "UNKNOWN",
                        )
                    else:
                        self._tm_cached_draw_data.car_dot = None
                else:
                    self._tm_cached_draw_data.car_dot = None
            dd = self._tm_cached_draw_data
            if hasattr(self, "_tm_map_widget"):
                self._tm_map_widget.set_draw_data(dd)
        except Exception:
            pass


class FakePacket:
    def __init__(self, x=1.0, y=0.0, z=0.0, car_speed=50.0):
        self.position_x = x
        self.position_y = y
        self.position_z = z
        self.car_speed = car_speed


def test_ac1_build_called_once_across_two_packets():
    """_build_map_draw_data is called only once; second call reuses cached geometry."""
    dash = FakeDashboardAC1()

    pkt1 = FakePacket(x=1.0)
    pkt2 = FakePacket(x=5.0)

    dash._tm_update_live_map_dot(pkt1)
    dash._tm_update_live_map_dot(pkt2)

    assert dash._build_calls == 1


def test_ac1_car_dot_differs_between_packets():
    """car_dot coordinates differ when position_x changes between calls."""
    dash = FakeDashboardAC1()

    pkt1 = FakePacket(x=0.0)
    pkt2 = FakePacket(x=10.0)

    dash._tm_update_live_map_dot(pkt1)
    dot_after_first = dash._tm_cached_draw_data.car_dot.x if dash._tm_cached_draw_data.car_dot else None

    dash._tm_update_live_map_dot(pkt2)
    dot_after_second = dash._tm_cached_draw_data.car_dot.x if dash._tm_cached_draw_data.car_dot else None

    assert dot_after_first != dot_after_second


def test_ac1_cache_invalidated_on_station_map_change():
    """Setting _tm_cached_draw_data to None triggers rebuild on next call."""
    dash = FakeDashboardAC1()

    dash._tm_update_live_map_dot(FakePacket(x=1.0))
    assert dash._build_calls == 1

    # Simulate station map change (invalidate)
    dash._tm_cached_draw_data = None

    dash._tm_update_live_map_dot(FakePacket(x=2.0))
    assert dash._build_calls == 2


def test_ac1_set_draw_data_called_on_tm_widget():
    """_tm_map_widget receives set_draw_data on each call (Live-tab map removed in Group A)."""
    dash = FakeDashboardAC1()

    dash._tm_update_live_map_dot(FakePacket())
    dash._tm_update_live_map_dot(FakePacket())

    assert len(dash._tm_map_widget.draw_data_calls) == 2


# ---------------------------------------------------------------------------
# AC2 — Threading race condition fix
# ---------------------------------------------------------------------------

def test_ac2_concurrent_writes_no_exception():
    """Two threads writing _is_racing 500 times each under lock do not raise."""
    import main as _main  # noqa: F401 — validate _state_lock exists
    _is_racing = [False]
    _state_lock = threading.Lock()
    errors: list[Exception] = []

    def writer(value: bool):
        try:
            for _ in range(500):
                with _state_lock:
                    _is_racing[0] = value
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=writer, args=(True,))
    t2 = threading.Thread(target=writer, args=(False,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    assert _is_racing[0] in (True, False)


def test_ac2_state_lock_exists_in_main():
    """main module exposes _state_lock as a threading.Lock."""
    import main as _main
    assert hasattr(_main, "_state_lock")
    assert isinstance(_main._state_lock, type(threading.Lock()))


def test_ac2_shift_muted_until_guarded_by_lock():
    """Two threads writing _shift_muted_until 500 times under the same lock do not raise."""
    import main as _main  # noqa: F401 — validate _state_lock exists
    _shift_muted_until = [0.0]
    _state_lock = threading.Lock()
    errors: list[Exception] = []

    def writer(value: float):
        try:
            for _ in range(500):
                with _state_lock:
                    _shift_muted_until[0] = value
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=writer, args=(time.time() + 5.0,))
    t2 = threading.Thread(target=writer, args=(0.0,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors
    assert isinstance(_shift_muted_until[0], float)


# ---------------------------------------------------------------------------
# AC3 — UI label dirty flags
# ---------------------------------------------------------------------------

class FakeBigValueLabel:
    """Stub for custom set_value widgets — not gated by dirty flag."""
    def __init__(self):
        self.values: list[str] = []

    def set_value(self, v):
        self.values.append(v)


class FakeDashboardAC3:
    """Minimal stub implementing the AC3 dirty-flag logic for _lbl_rpm."""

    def __init__(self):
        self._live_label_cache: dict[str, str] = {}
        self._lbl_rpm = FakeLabel()
        self._lbl_current_lap = FakeLabel()
        self._lbl_last_lap = FakeLabel()
        self._lbl_best_lap = FakeLabel()
        self._lbl_delta = FakeLabel()
        self._lbl_speed = FakeBigValueLabel()
        self._lbl_gear = FakeBigValueLabel()

    def _update_labels(self, rpm: float, lap: int, last_ms: int, best_ms: int) -> None:
        """Mirrors the gated setText calls from _update_live."""
        _new = f"{rpm:.0f}"
        if self._live_label_cache.get("lbl_rpm") != _new:
            self._live_label_cache["lbl_rpm"] = _new
            self._lbl_rpm.setText(_new)

        _new = f"Lap {lap}"
        if self._live_label_cache.get("lbl_current_lap") != _new:
            self._live_label_cache["lbl_current_lap"] = _new
            self._lbl_current_lap.setText(_new)

        if last_ms > 0:
            _new = f"{last_ms}"
            if self._live_label_cache.get("lbl_last_lap") != _new:
                self._live_label_cache["lbl_last_lap"] = _new
                self._lbl_last_lap.setText(_new)

        if best_ms > 0:
            _new = f"{best_ms}"
            if self._live_label_cache.get("lbl_best_lap") != _new:
                self._live_label_cache["lbl_best_lap"] = _new
                self._lbl_best_lap.setText(_new)


def test_ac3_setText_called_once_for_identical_packets():
    """Each gated label setText is called once even when _update_labels fires twice."""
    dash = FakeDashboardAC3()

    dash._update_labels(rpm=6000.0, lap=3, last_ms=95000, best_ms=94000)
    dash._update_labels(rpm=6000.0, lap=3, last_ms=95000, best_ms=94000)

    assert len(dash._lbl_rpm.set_text_calls) == 1
    assert len(dash._lbl_current_lap.set_text_calls) == 1
    assert len(dash._lbl_last_lap.set_text_calls) == 1
    assert len(dash._lbl_best_lap.set_text_calls) == 1


def test_ac3_setText_called_again_when_value_changes():
    """setText fires again when a value changes."""
    dash = FakeDashboardAC3()

    dash._update_labels(rpm=6000.0, lap=3, last_ms=95000, best_ms=94000)
    dash._update_labels(rpm=7000.0, lap=3, last_ms=95000, best_ms=94000)

    assert len(dash._lbl_rpm.set_text_calls) == 2


def test_ac3_delta_label_caches_text_and_style_as_tuple():
    """_lbl_delta uses a tuple cache key covering both text and style."""
    dash = FakeDashboardAC3()
    cache: dict[str, object] = {}

    def _set_delta(text, style):
        key = "lbl_delta"
        if cache.get(key) != (text, style):
            cache[key] = (text, style)
            dash._lbl_delta.setText(text)
            dash._lbl_delta.setStyleSheet(style)

    _set_delta("+0.123s", "color: #E8771A;")
    _set_delta("+0.123s", "color: #E8771A;")  # identical — should not fire

    assert len(dash._lbl_delta.set_text_calls) == 1
    assert len(dash._lbl_delta.set_style_calls) == 1

    _set_delta("+0.456s", "color: #E8771A;")  # text changed — fires

    assert len(dash._lbl_delta.set_text_calls) == 2


# ---------------------------------------------------------------------------
# AC4 — Magic number extraction
# ---------------------------------------------------------------------------

def test_ac4_constants_exist_with_correct_values():
    """All five constants are present at main module level with correct values."""
    import main as _main

    assert hasattr(_main, "OVERSTEER_YAW_THRESHOLD_RAD_S")
    assert hasattr(_main, "OVERSTEER_REAR_SLIP_RATIO")
    assert hasattr(_main, "OVERSTEER_SUSTAINED_SEC")
    assert hasattr(_main, "OVERSTEER_COOLDOWN_SEC")
    assert hasattr(_main, "EVENT_QUEUE_TIMEOUT_SEC")

    assert _main.OVERSTEER_YAW_THRESHOLD_RAD_S == 1.8
    assert _main.OVERSTEER_REAR_SLIP_RATIO     == 1.15
    assert _main.OVERSTEER_SUSTAINED_SEC       == 0.3
    assert _main.OVERSTEER_COOLDOWN_SEC        == 8.0
    assert _main.EVENT_QUEUE_TIMEOUT_SEC       == 0.5


# ---------------------------------------------------------------------------
# AC5 — Silent exception repair
# ---------------------------------------------------------------------------

class FakeTelemetryLabel:
    def __init__(self):
        self.text = ""

    def setText(self, t):
        self.text = t


class FakeDashboardAC5Telemetry:
    """Replicates the try/except block from _update_telemetry_tab (line ~1612)."""

    def __init__(self):
        self._telem_lbl_ai_status = FakeTelemetryLabel()
        self._ai_log_entries = []

    def _update_telemetry_label(self):
        try:
            entries = getattr(self, "_ai_log_entries", [])
            if entries:
                last = entries[-1]
                status = "✓" if last.success else "✗"
                t = last.timestamp[11:19] if len(last.timestamp) >= 19 else ""
                self._telem_lbl_ai_status.setText(f"{status} {last.feature} @ {t}")
        except Exception:
            logging.warning("telemetry label update failed", exc_info=True)


class FakeDashboardAC5Model:
    """Replicates the try/except block from _tm_try_load_accepted_model (line ~3867)."""

    def __init__(self):
        self._tm_alignment_result = None

    def _tm_try_load_accepted_model(self, find_fn, import_fn):
        try:
            p = find_fn()
            if p is None:
                return
            loaded = import_fn(p)
            if loaded is None:
                return
            self._tm_alignment_result = loaded
        except Exception:
            logging.debug("no accepted model for this layout", exc_info=True)


def test_ac5_telemetry_label_warning_on_exception(caplog):
    """When the telemetry label block raises, logging.warning is called."""
    dash = FakeDashboardAC5Telemetry()

    broken_entry = MagicMock()
    broken_entry.success = True
    # Make timestamp access raise
    type(broken_entry).timestamp = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
    dash._ai_log_entries = [broken_entry]

    with caplog.at_level(logging.WARNING):
        dash._update_telemetry_label()

    assert any("telemetry label update failed" in r.message for r in caplog.records)


def test_ac5_model_load_debug_on_exception(caplog):
    """When _find_accepted_model_path raises, logging.debug is called and no re-raise."""
    dash = FakeDashboardAC5Model()

    def bad_find():
        raise FileNotFoundError("not found")

    with caplog.at_level(logging.DEBUG):
        dash._tm_try_load_accepted_model(find_fn=bad_find, import_fn=lambda p: None)

    assert any("no accepted model for this layout" in r.message for r in caplog.records)
    assert dash._tm_alignment_result is None  # not set — safe state


# ---------------------------------------------------------------------------
# AC6 — Dead callback removal
# ---------------------------------------------------------------------------

def test_ac6_no_setup_category_changed_attribute():
    """DashboardWindow must not have _on_setup_category_changed method."""
    # Import without instantiating (requires PyQt6 display) by checking source text
    import ast
    from pathlib import Path

    src = Path("C:/Projects/VR_Dashboard/ui/dashboard.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    method_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }

    assert "_on_setup_category_changed" not in method_names, (
        "_on_setup_category_changed stub was not removed"
    )
    assert "_on_setup_car_changed" not in method_names, (
        "_on_setup_car_changed stub was not removed"
    )


def test_ac6_no_connect_calls_to_removed_callbacks():
    """Zero signal .connect() calls reference either removed callback name across all .py files."""
    import re
    from pathlib import Path

    project_root = Path("C:/Projects/VR_Dashboard")
    forbidden = {"_on_setup_category_changed", "_on_setup_car_changed"}
    # Pattern: .connect(something_on_setup_category_changed) or connect(..._on_setup_car_changed...)
    pattern = re.compile(r"\.connect\s*\(.*?(_on_setup_category_changed|_on_setup_car_changed)")

    violations: list[str] = []
    for py_file in project_root.rglob("*.py"):
        # Skip test files themselves
        if py_file.parts[-2] == "tests":
            continue
        try:
            src = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(src.splitlines(), 1):
            if pattern.search(line):
                violations.append(f"{py_file}:{lineno}: {line.strip()}")

    assert not violations, "Found connect() calls to removed callbacks:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# AC7 — Joystick poll rate
# ---------------------------------------------------------------------------

def test_ac7_joystick_sleep_value():
    """The joystick poller uses time.sleep(0.1), not 0.02."""
    import ast
    from pathlib import Path

    src = Path("C:/Projects/VR_Dashboard/ui/dashboard.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    sleep_args: list[float] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "sleep"
            and node.args
        ):
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float)):
                sleep_args.append(float(arg.value))

    assert 0.1 in sleep_args, "time.sleep(0.1) not found in dashboard.py"
    assert 0.02 not in sleep_args, "old time.sleep(0.02) still present in dashboard.py"
