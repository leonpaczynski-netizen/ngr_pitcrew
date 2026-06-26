"""In-memory lap and fuel data logger with thread-safe access."""
from __future__ import annotations
import threading
from typing import Optional
from telemetry.state import LapRecord


class LapDataLogger:
    """Stores LapRecord objects; accessed from dispatcher thread (writes) and
    Qt main thread (reads).  A single Lock guards all mutations and reads."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: list[LapRecord] = []

    # ------------------------------------------------------------------ writes

    def add_lap(self, record: LapRecord) -> None:
        with self._lock:
            self._records.append(record)

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    # ------------------------------------------------------------------ reads

    def records(self) -> list[LapRecord]:
        with self._lock:
            return list(self._records)

    def lap_count(self) -> int:
        with self._lock:
            return len(self._records)

    def best_lap_ms(self) -> int:
        with self._lock:
            valid = [r.lap_time_ms for r in self._records if r.lap_time_ms > 0]
            return min(valid) if valid else -1

    def avg_lap_ms(self) -> float:
        with self._lock:
            valid = [r.lap_time_ms for r in self._records if r.lap_time_ms > 0]
            return sum(valid) / len(valid) if valid else 0.0

    def avg_fuel_per_lap(self) -> float:
        with self._lock:
            valid = [r.fuel_used for r in self._records if r.fuel_used > 0]
            return sum(valid) / len(valid) if valid else 0.0

    def total_fuel_used(self) -> float:
        with self._lock:
            return sum(r.fuel_used for r in self._records)

    def pit_stop_count(self) -> int:
        with self._lock:
            return sum(1 for r in self._records if r.is_pit_lap)
