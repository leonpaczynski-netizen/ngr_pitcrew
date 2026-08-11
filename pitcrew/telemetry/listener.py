"""UDP listener thread that receives GT7 packets from SimHub."""
from __future__ import annotations
import socket
import threading
import time
from collections import deque
from typing import Callable


class UDPListener(threading.Thread):
    """Daemon thread that reads UDP packets and calls `callback(data: bytes)`."""

    def __init__(self, host: str, port: int, callback: Callable[[bytes], None]) -> None:
        super().__init__(daemon=True, name="UDPListener")
        self._host = host
        self._port = port
        self._callback = callback
        self._stop_event = threading.Event()
        self._packet_timestamps: deque[float] = deque(maxlen=120)
        self._total_received = 0
        self._parse_errors = 0
        self._connected = False

    @property
    def packet_rate(self) -> float:
        """Packets per second over the last ~2 seconds."""
        ts = self._packet_timestamps
        if len(ts) < 2:
            return 0.0
        return (len(ts) - 1) / (ts[-1] - ts[0])

    @property
    def total_received(self) -> int:
        return self._total_received

    @property
    def connected(self) -> bool:
        return self._connected

    def increment_errors(self) -> None:
        self._parse_errors += 1

    @property
    def parse_errors(self) -> int:
        return self._parse_errors

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            # Bind to INADDR_ANY so we receive regardless of which interface SimHub uses
            sock.bind(("0.0.0.0", self._port))
        except OSError as e:
            print(f"[UDPListener] bind failed on port {self._port}: {e}")
            return
        sock.settimeout(1.0)

        last_packet_time = time.monotonic()
        self._connected = False

        while not self._stop_event.is_set():
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                if time.monotonic() - last_packet_time > 3.0:
                    self._connected = False
                continue
            except OSError:
                break

            now = time.monotonic()
            last_packet_time = now
            self._packet_timestamps.append(now)
            self._total_received += 1
            self._connected = True

            try:
                self._callback(data)
            except Exception as exc:
                print(f"[UDPListener] callback error: {exc}")

        sock.close()
